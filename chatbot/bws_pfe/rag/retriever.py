"""
RAG Retriever ARIA — recherche MySQL FULLTEXT + fallback keyword.

Stratégie :
  1. MATCH AGAINST (FULLTEXT) sur title + content + keywords
  2. Si < top_k résultats, complète avec recherche LIKE par mots-clés
  3. Priorité aux documents liés au même device_id ou domain

Usage dans recommendation_engine.py :
    from rag.retriever import retrieve_context
    context = retrieve_context(engine, rec_type, domain, device_id, user_role)
    # Renvoie une string prête à injecter dans le prompt LLM
"""
from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger('aria.rag')

# Catégories prioritaires selon le type d'anomalie
_RECO_TYPE_CATEGORIES = {
    'OVERCONSUMPTION': ['anomaly_playbook', 'maintenance_procedure', 'equipment_spec'],
    'MAINTENANCE'    : ['maintenance_procedure', 'anomaly_playbook', 'equipment_spec'],
    'LEAK_RISK'      : ['anomaly_playbook', 'maintenance_procedure', 'equipment_spec'],
    'OPTIMIZATION'   : ['maintenance_procedure', 'contract_info'],
    'BUDGET_ALERT'   : ['contract_info', 'maintenance_procedure'],
    'EFFICIENCY'     : ['anomaly_playbook', 'maintenance_procedure'],
}

# Mots-clés métier par domaine — tous ≥ 4 chars pour respecter ft_min_word_len MySQL (défaut=4).
# Les termes courts comme "eau", "gaz", "m3" sont ignorés silencieusement par FULLTEXT.
_DOMAIN_KEYWORDS = {
    'energy': 'electricite energie kWh consommation HVAC climatisation compteur puissance',
    'water' : 'fuite debit canalisation robinet humide distribution reseau tuyauterie',
    'gas'   : 'chaudiere bruleur fuite chaufferie combustion methane propane gazio',
    'fuel'  : 'carburant litre vehicule consommation flotte kilometrage reservoir',
}

# Libellés lisibles pour le LLM
_CATEGORY_LABELS = {
    'equipment_spec'     : 'Fiche équipement',
    'maintenance_procedure': 'Procédure de maintenance',
    'anomaly_playbook'   : 'Playbook anomalie',
    'intervention_report': 'Rapport d\'intervention',
    'building_zone'      : 'Description zone',
    'contract_info'      : 'Contrat / Tarif',
}


def retrieve_context(
    engine,
    rec_type    : str,
    domain      : str,
    device_id   : str | None = None,
    user_role   : str        = 'gestionnaire',
    top_k       : int        = 4,
) -> str:
    """
    Retourne un bloc de texte contextuel (max top_k documents) prêt pour injection LLM.
    Renvoie une string vide si aucun document pertinent trouvé.
    """
    try:
        docs = _retrieve_docs(engine, rec_type, domain, device_id, top_k)
        if not docs:
            return ''
        return _format_context(docs)
    except Exception as exc:
        logger.warning("[rag] Retrieval échoué : %s", exc)
        return ''


def _retrieve_docs(
    engine,
    rec_type : str,
    domain   : str,
    device_id: str | None,
    top_k    : int,
) -> list[dict]:
    """Stratégie : device exact > domaine > FULLTEXT global."""
    results = []

    # 1. Document spécifique au device (s'il existe)
    if device_id:
        device_docs = _query_by_device(engine, device_id, top_k=2)
        results.extend(device_docs)

    # 2. FULLTEXT par type d'anomalie + domaine
    ft_query  = _build_ft_query(rec_type, domain)
    priorities = _RECO_TYPE_CATEGORIES.get(rec_type, ['anomaly_playbook', 'maintenance_procedure'])
    ft_docs   = _query_fulltext(engine, ft_query, priorities, domain, top_k=top_k)

    # Déduplique (garde ceux pas déjà dans results)
    existing_ids = {d['doc_id'] for d in results}
    for doc in ft_docs:
        if doc['doc_id'] not in existing_ids and len(results) < top_k:
            results.append(doc)
            existing_ids.add(doc['doc_id'])

    # 3. Si encore vide — fallback LIKE générique
    if not results:
        fallback = _query_fallback(engine, domain, rec_type, top_k)
        results.extend(fallback)

    return results[:top_k]


def _build_ft_query(rec_type: str, domain: str) -> str:
    domain_kw = _DOMAIN_KEYWORDS.get(domain, '')
    type_kw   = {
        'OVERCONSUMPTION': 'surconsommation pic consommation anormale dépassement',
        'MAINTENANCE'    : 'maintenance dégradation progressive dérive usure',
        'LEAK_RISK'      : 'fuite nuit nocturne débit résiduel',
        'OPTIMIZATION'   : 'optimisation heures creuses nocturne veille',
        'BUDGET_ALERT'   : 'budget dépassement mensuel projection',
        'EFFICIENCY'     : 'efficacité carburant flotte L/100km consommation',
    }.get(rec_type, rec_type.lower())
    return f"{type_kw} {domain_kw}"


def _query_by_device(engine, device_id: str, top_k: int) -> list[dict]:
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT doc_id, category, title, content
                FROM rag_documents
                WHERE device_id = :dev
                ORDER BY category DESC
                LIMIT :k
            """), {'dev': device_id, 'k': top_k}).fetchall()
        return [{'doc_id': r[0], 'category': r[1], 'title': r[2], 'content': r[3]} for r in rows]
    except Exception:
        return []


def _query_fulltext(engine, query: str, categories: list, domain: str, top_k: int) -> list[dict]:
    try:
        cat_placeholders = ', '.join(f':cat{i}' for i in range(len(categories)))
        params = {'q': query, 'dom': domain, 'k': top_k + 2}
        for i, cat in enumerate(categories):
            params[f'cat{i}'] = cat

        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT doc_id, category, title, content,
                       MATCH(title, content, keywords) AGAINST (:q IN BOOLEAN MODE) AS score
                FROM rag_documents
                WHERE MATCH(title, content, keywords) AGAINST (:q IN BOOLEAN MODE)
                  AND (domain = :dom OR domain IS NULL)
                  AND category IN ({cat_placeholders})
                ORDER BY
                    CASE WHEN category = :cat0 THEN 0
                         WHEN category = :cat1 THEN 1
                         ELSE 2 END,
                    score DESC
                LIMIT :k
            """), params).fetchall()

        return [{'doc_id': r[0], 'category': r[1], 'title': r[2], 'content': r[3]} for r in rows]
    except Exception:
        return []


def _query_fallback(engine, domain: str, rec_type: str, top_k: int) -> list[dict]:
    """LIKE-based fallback quand FULLTEXT ne retourne rien."""
    try:
        kw = rec_type.lower().replace('_', ' ')
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT doc_id, category, title, content
                FROM rag_documents
                WHERE (domain = :dom OR domain IS NULL)
                  AND (title LIKE :kw OR keywords LIKE :kw)
                ORDER BY category
                LIMIT :k
            """), {'dom': domain, 'kw': f'%{kw}%', 'k': top_k}).fetchall()
        return [{'doc_id': r[0], 'category': r[1], 'title': r[2], 'content': r[3]} for r in rows]
    except Exception:
        return []


def _format_context(docs: list[dict]) -> str:
    """Formate les documents récupérés en bloc texte pour injection dans le prompt LLM."""
    if not docs:
        return ''

    parts = ["CONTEXTE BASE DE CONNAISSANCE (documents récupérés) :"]
    for i, doc in enumerate(docs, 1):
        label = _CATEGORY_LABELS.get(doc['category'], doc['category'])
        parts.append(f"\n[{i}] {label} — {doc['title']}")
        # Tronque à 600 chars pour ne pas exploser le contexte LLM
        content = doc['content'].strip()
        if len(content) > 600:
            content = content[:597] + '...'
        parts.append(content)

    return '\n'.join(parts)


def count_documents(engine) -> dict:
    """Retourne le nombre de documents par catégorie (utile pour diagnostics)."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT category, COUNT(*) FROM rag_documents GROUP BY category ORDER BY category"
            )).fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception as exc:
        return {'error': str(exc)}
