"""
Routes REST pour les recommandations IA personnalisées.

GET  /recommendations          — liste les recommandations actives (filtrées par domaine/statut/rôle)
PATCH /recommendations/{id}    — met à jour le statut (accepted/dismissed/done)
POST /recommendations/refresh  — déclenche manuellement un cycle de génération
GET  /recommendations/summary  — résumé agrégé pour le dashboard
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from api.db import get_engine, get_employee_modules, get_user_preferences, upsert_user_preference

# Mapping module Angular → domaine recommendation_engine
_MODULE_TO_DOMAIN: dict[str, str] = {
    'eau'                 : 'water',
    'énergie électrique'  : 'energy',
    'gaz'                 : 'gas',
    'carburant'           : 'fuel',
}

logger = logging.getLogger('aria.routes.recommendations')

router = APIRouter(prefix='/recommendations', tags=['recommendations'])


# ── Pydantic models ──────────────────────────────────────────────────────────

class RecommendationOut(BaseModel):
    id                   : int
    domain               : str
    device_id            : Optional[str]
    rec_type             : str
    target_role          : str
    priority             : str
    title                : str
    description          : str
    action               : str
    reasoning            : Optional[str]
    estimated_saving_tnd : Optional[float]
    deviation_pct        : Optional[float]
    status               : str
    generated_at         : str
    expires_at           : str
    acted_at             : Optional[str]
    measured_saving_tnd  : Optional[float]


def _localize(lang: str, title: str, description: str, action: str,
              reasoning: Optional[str], i18n_raw) -> tuple[str, str, str, Optional[str]]:
    """Résout title/description/action/reasoning dans la langue demandée.

    Le contenu canonique est toujours généré en français (voir recommendation_engine.py) ;
    `i18n_raw` contient au mieux les traductions en/ar produites à la génération.
    Retombe silencieusement sur le français si la traduction est absente/invalide —
    ne jamais faire planter la requête ni afficher un mélange de langues incohérent."""
    if lang == 'fr' or not i18n_raw:
        return title, description, action, reasoning
    try:
        i18n = json.loads(i18n_raw) if isinstance(i18n_raw, str) else i18n_raw
        fields = i18n.get(lang) if isinstance(i18n, dict) else None
    except Exception:
        fields = None
    if not fields:
        return title, description, action, reasoning
    return (
        fields.get('title') or title,
        fields.get('description') or description,
        fields.get('action') or action,
        fields.get('reasoning'),  # peut être légitimement None même si le fr en a un
    )


class StatusUpdate(BaseModel):
    status  : str            # accepted | dismissed | done
    user_id : Optional[str] = None   # login de l'utilisateur pour apprendre ses préférences


class RefreshRequest(BaseModel):
    user_role : str = 'gestionnaire'   # technicien | gestionnaire | directeur
    domain    : str | None = None      # None = tous les domaines
    force     : bool = False           # True = recalcule les baselines même si fraîches


class RefreshResult(BaseModel):
    baselines : dict
    generated : dict
    roi_evaluated: int


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get('', response_model=list[RecommendationOut])
def list_recommendations(
    domain          : Optional[str]       = Query(None, description="energy|water|gas|fuel"),
    status          : Optional[str]       = Query('pending', description="pending|accepted|dismissed|done|all"),
    priority        : Optional[str]       = Query(None, description="critical|high|medium|low"),
    user_role       : str                 = Query('gestionnaire', description="technicien|gestionnaire|directeur"),
    user_id         : Optional[str]       = Query(None, description="Login utilisateur — résout allowed_modules + personnalise l'ordre"),
    allowed_modules : Optional[List[str]] = Query(None, description="Liste des modules autorisés"),
    lang            : str                 = Query('fr', pattern=r'^(fr|en|ar)$', description="Langue d'affichage — fr|en|ar"),
    limit           : int                 = Query(20, ge=1, le=100),
):
    """
    Retourne les recommandations actives (non expirées) filtrées par :
    - user_role   : retourne uniquement les recos générées pour ce rôle
    - user_id     : résout les allowed_modules depuis aria_employees si allowed_modules absent
    - allowed_modules : restreint aux domaines accessibles (eau→water, énergie électrique→energy, etc.)
    """
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    # Résolution des modules autorisés : paramètre direct > lookup DB > accès total
    effective_modules = allowed_modules
    if effective_modules is None and user_id:
        effective_modules = get_employee_modules(user_id)

    # Convertir les modules en domaines autorisés (None = tous les domaines)
    allowed_domains: Optional[list[str]] = None
    if effective_modules is not None:
        allowed_domains = [
            _MODULE_TO_DOMAIN[m] for m in effective_modules if m in _MODULE_TO_DOMAIN
        ]

    filters = ["expires_at > NOW()"]
    params: dict = {}

    # Filtre sur le rôle cible
    valid_roles = {'technicien', 'gestionnaire', 'directeur'}
    if user_role not in valid_roles:
        raise HTTPException(400, f"user_role invalide. Valeurs : {valid_roles}")
    filters.append("target_role = :user_role")
    params['user_role'] = user_role

    # Filtre domaine explicite (prioritaire sur allowed_modules)
    if domain:
        filters.append("domain = :domain")
        params['domain'] = domain
    elif allowed_domains is not None:
        if not allowed_domains:
            return []  # aucun domaine autorisé → liste vide
        placeholders = ', '.join(f':ad{i}' for i in range(len(allowed_domains)))
        filters.append(f"domain IN ({placeholders})")
        for i, d in enumerate(allowed_domains):
            params[f'ad{i}'] = d

    if status and status != 'all':
        statuses = [s.strip() for s in status.split(',')]
        placeholders = ', '.join(f':st{i}' for i in range(len(statuses)))
        filters.append(f"status IN ({placeholders})")
        for i, s in enumerate(statuses):
            params[f'st{i}'] = s

    if priority:
        filters.append("priority = :priority")
        params['priority'] = priority

    # ── Personnalisation par utilisateur ─────────────────────────────────────
    # Charge les préférences AVANT de construire le WHERE (pour la suppression)
    user_prefs: dict = {}
    if user_id:
        try:
            user_prefs = get_user_preferences(engine, user_id)
        except Exception:
            pass  # dégradation gracieuse : pas de personnalisation si DB inaccessible

    # Suppression des rec_types massivement rejetés par cet utilisateur
    # Condition : score < 0.15 ET au moins 3 dismissals sur ce domaine
    suppressed_types: list[str] = []
    for (rt, dom), p in user_prefs.items():
        if p['score'] < 0.15 and p['dismiss'] >= 3:
            # Filtre global si aucun domaine précis demandé, sinon uniquement sur le domaine concerné
            if domain is None or dom == domain:
                suppressed_types.append(rt)
    suppressed_types = list(set(suppressed_types))  # déduplique

    if suppressed_types:
        placeholders = ', '.join(f':sup{i}' for i in range(len(suppressed_types)))
        filters.append(f"rec_type NOT IN ({placeholders})")
        for i, rt in enumerate(suppressed_types):
            params[f'sup{i}'] = rt

    where = ' AND '.join(filters)

    from sqlalchemy import text
    sql = text(f"""
        SELECT id, domain, device_id, rec_type, target_role, priority, title, description, action,
               reasoning, i18n, estimated_saving_tnd, deviation_pct, status,
               generated_at, expires_at, acted_at, measured_saving_tnd
        FROM aria_recommendations
        WHERE {where}
        ORDER BY
          FIELD(priority,'critical','high','medium','low'),
          generated_at DESC
        LIMIT :limit
    """)
    params['limit'] = limit

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    results = []
    for r in rows:
        title, description, action, reasoning = _localize(lang, r[6], r[7], r[8], r[9], r[10])
        results.append(RecommendationOut(
            id=r[0], domain=r[1], device_id=r[2], rec_type=r[3], target_role=r[4],
            priority=r[5], title=title, description=description, action=action,
            reasoning=reasoning,
            estimated_saving_tnd=r[11], deviation_pct=r[12], status=r[13],
            generated_at=str(r[14]), expires_at=str(r[15]),
            acted_at=str(r[16]) if r[16] else None,
            measured_saving_tnd=r[17],
        ))

    # Réordonnancement personnalisé en Python : les rec_types préférés remontent
    # (score > 0.6 = l'utilisateur les accepte régulièrement)
    if user_prefs:
        _PRIORITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

        def _sort_key(rec: RecommendationOut) -> tuple:
            pref = user_prefs.get((rec.rec_type, rec.domain), {})
            score = pref.get('score', 0.5)
            # Les préférés (score > 0.6) obtiennent boost = 0, les autres = 1
            boost = 0 if score > 0.6 else 1
            return (boost, _PRIORITY_ORDER.get(rec.priority, 9))

        results.sort(key=_sort_key)

    return results


@router.patch('/{rec_id}', response_model=RecommendationOut)
def update_status(
    rec_id: int,
    body  : StatusUpdate,
    lang  : str = Query('fr', pattern=r'^(fr|en|ar)$', description="Langue d'affichage — fr|en|ar"),
):
    """Met à jour le statut d'une recommandation (accepted/dismissed/done)."""
    valid_statuses = {'accepted', 'dismissed', 'done'}
    if body.status not in valid_statuses:
        raise HTTPException(400, f"Statut invalide. Valeurs : {valid_statuses}")

    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    from sqlalchemy import text
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE aria_recommendations SET status = :s, acted_at = NOW() WHERE id = :id"
        ), {'s': body.status, 'id': rec_id})

    if result.rowcount == 0:
        raise HTTPException(404, f"Recommandation {rec_id} introuvable")

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, domain, device_id, rec_type, target_role, priority, title, description, action, "
            "reasoning, i18n, estimated_saving_tnd, deviation_pct, status, generated_at, expires_at, acted_at, "
            "measured_saving_tnd FROM aria_recommendations WHERE id = :id"
        ), {'id': rec_id}).fetchone()

    if not row:
        raise HTTPException(404)

    # Apprentissage des préférences utilisateur
    if body.user_id and body.status in ('accepted', 'dismissed'):
        try:
            upsert_user_preference(engine, body.user_id, row[3], row[1], body.status)
        except Exception as exc:
            logger.warning("[reco] Préférence non enregistrée pour %s : %s", body.user_id, exc)

    logger.info("[reco] Recommandation %d -> %s (user=%s)", rec_id, body.status, body.user_id or '?')
    title, description, action, reasoning = _localize(lang, row[6], row[7], row[8], row[9], row[10])
    return RecommendationOut(
        id=row[0], domain=row[1], device_id=row[2], rec_type=row[3], target_role=row[4],
        priority=row[5], title=title, description=description, action=action,
        reasoning=reasoning,
        estimated_saving_tnd=row[11], deviation_pct=row[12], status=row[13],
        generated_at=str(row[14]), expires_at=str(row[15]),
        acted_at=str(row[16]) if row[16] else None,
        measured_saving_tnd=row[17],
    )


@router.post('/refresh', response_model=RefreshResult)
async def refresh_recommendations(body: RefreshRequest = RefreshRequest()):
    """
    Déclenche manuellement un cycle baselines + génération IA.
    Exécuté dans un thread pool (non-bloquant pour l'event loop uvicorn).
    Timeout 120s — retourne HTTP 504 si dépassé.

    user_role : technicien | gestionnaire | directeur
    domain    : limiter à un seul domaine (None = tous)
    """
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    from api.pipeline.recommendation_engine import (
        compute_baselines, generate_domain, measure_roi, DOMAIN_CONFIG,
    )

    valid_roles = {'technicien', 'gestionnaire', 'directeur'}
    if body.user_role not in valid_roles:
        raise HTTPException(400, f"user_role invalide : '{body.user_role}'. Valeurs : {sorted(valid_roles)}")

    if body.domain and body.domain not in DOMAIN_CONFIG:
        raise HTTPException(400, f"Domaine inconnu : {body.domain}. Valeurs : {list(DOMAIN_CONFIG)}")

    def _run() -> tuple[dict, dict, int]:
        baselines = compute_baselines(engine, force=body.force)
        if body.domain:
            generated = {body.domain: generate_domain(engine, body.domain, user_role=body.user_role)}
        else:
            generated = {
                dom: generate_domain(engine, dom, user_role=body.user_role)
                for dom in DOMAIN_CONFIG
            }
        return baselines, generated, measure_roi(engine)

    loop = asyncio.get_event_loop()
    try:
        baselines, generated, roi = await asyncio.wait_for(
            loop.run_in_executor(None, _run),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, 'Génération expirée (>120s). Réessayez ou limitez à un domaine.')

    return RefreshResult(baselines=baselines, generated=generated, roi_evaluated=roi)


@router.get('/summary')
def recommendations_summary():
    """Résumé agrégé : total par priorité, économies potentielles, ROI réalisé."""
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    from sqlalchemy import text
    sql = text("""
        SELECT
          domain,
          COUNT(*) AS total,
          SUM(CASE WHEN priority='critical' THEN 1 ELSE 0 END) AS critical_count,
          SUM(CASE WHEN priority='high'     THEN 1 ELSE 0 END) AS high_count,
          SUM(CASE WHEN priority='medium'   THEN 1 ELSE 0 END) AS medium_count,
          ROUND(SUM(COALESCE(estimated_saving_tnd, 0)), 2)      AS total_potential_tnd,
          ROUND(SUM(COALESCE(measured_saving_tnd,  0)), 2)      AS total_realized_tnd
        FROM aria_recommendations
        WHERE status IN ('pending','accepted') AND expires_at > NOW()
        GROUP BY domain
        ORDER BY critical_count DESC, high_count DESC
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()

    return [
        {
            'domain'             : r[0],
            'total'              : r[1],
            'critical_count'     : r[2],
            'high_count'         : r[3],
            'medium_count'       : r[4],
            'total_potential_tnd': r[5],
            'total_realized_tnd' : r[6],
        }
        for r in rows
    ]
