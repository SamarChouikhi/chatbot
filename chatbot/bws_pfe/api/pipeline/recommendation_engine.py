"""
PARTIE RECO — Moteur de recommandations IA personnalisées ARIA — v2 (LLM + contexte riche + feedback loop).

Ce module orchestre le pipeline ; chaque étape vit dans un sous-module de `api/pipeline/reco/` :

  reco.config     — DOMAIN_CONFIG, résolution device_id → libellé lisible
  reco.baselines  — compute_baselines() : P10/P50/P90 par (device, domain, hour_of_week)
  reco.signals    — détection statistique / Chronos / budget / maintenance + enrichissement score AD
  reco.context    — anti-fatigue (_should_suppress, _needs_priority_boost), contexte device, cross-domaine
  reco.llm        — prompt contextuel, appel LLM (CoT JSON), validation, traduction EN/AR
  reco.fallback   — recommandations rule-based (FR/EN/AR) si LLM indisponible
  reco.storage    — persistance aria_recommendations (déduplication, expiration)
  reco.roi        — measure_roi() : impact mesuré après acceptation

Ici : garde-fou de plausibilité des économies, filtrage hors-ligne, appels LLM
parallèles, assemblage des recommandations et point d'entrée du scheduler.
"""
from __future__ import annotations

import concurrent.futures
import logging

from sqlalchemy import text

from .reco.baselines import compute_baselines
from .reco.config import DOMAIN_CONFIG, _resolve_device_label
from .reco.context import (
    _get_cross_domain_anomalies,
    _get_device_context,
    _needs_priority_boost,
    _should_suppress,
)
from .reco.fallback import _rule_based_fallback
from .reco.llm import _build_llm_prompt, _call_llm, _translate_recommendation, _validate_reasoning
from .reco.roi import measure_roi
from .reco.signals import _detect_from_ad_anomalies, _detect_raw_signals, _enrich_with_ad_scores
from .reco.storage import _clear_stale_pending, _get_active_keys, _insert_recommendations

__all__ = [
    'DOMAIN_CONFIG',
    'compute_baselines',
    'generate_all',
    'generate_domain',
    'measure_roi',
    'run_recommendation_cycle',
]

logger = logging.getLogger('aria.reco_engine')

# ══════════════════════════════════════════════════════════════════════════════
# 10. ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

_ALL_ROLES = ('technicien', 'gestionnaire', 'directeur')

# Au-delà, une économie mensuelle pour un seul compteur n'est pas crédible pour un
# bâtiment : c'est le signe d'une unité incohérente (Wh ou L remontés comme kWh ou m³).
# L'écart relatif reste valable, seul le montant est retiré.
_MAX_PLAUSIBLE_SAVING_TND = 50_000.0


def _flag_implausible_savings(signals: list[dict]) -> list[dict]:
    for s in signals:
        saving = s.get('estimated_saving_tnd')
        if saving is not None and saving > _MAX_PLAUSIBLE_SAVING_TND:
            logger.warning(
                "[reco] %s/%s : économie estimée %.0f TND non plausible (> %.0f) — unité du compteur à vérifier, montant retiré.",
                s.get('device_id'), s['rec_type'], saving, _MAX_PLAUSIBLE_SAVING_TND,
            )
            s['estimated_saving_tnd'] = None
            s['saving_unreliable'] = True
    return signals


def generate_all(engine, domain: str | None = None) -> dict:
    """Génère des recommandations pour un domaine (ou les 4) et les 3 rôles."""
    results = {}
    for d in ([domain] if domain else list(DOMAIN_CONFIG)):
        total = 0
        for role in _ALL_ROLES:
            try:
                total += generate_domain(engine, d, user_role=role)
            except Exception as exc:
                logger.error("[reco:%s/%s] Erreur : %s", d, role, exc, exc_info=True)
        results[d] = total
    return results


_MAX_LLM_CALLS_PER_DOMAIN = 10  # cap par domaine pour éviter l'épuisement des quotas API


_OFFLINE_THRESHOLD_DAYS = 7  # device sans données depuis N jours → considéré hors-ligne


def _is_device_offline(engine, table: str, device_id: str) -> bool:
    """True si le device est silencieux depuis plus de OFFLINE_THRESHOLD_DAYS.

    Comparaison relative à MAX(date) global de la table (pas à utcnow()) —
    robuste quand les données sont historiques (replay, démo, backfill).
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(f"""
                    SELECT
                        MAX(date) AS dev_last,
                        (SELECT MAX(date) FROM `{table}`) AS table_last
                    FROM `{table}`
                    WHERE device_id = :d
                """),
                {'d': device_id},
            ).fetchone()
        if row is None or row[0] is None:
            return True
        dev_last   = row[0].date() if hasattr(row[0], 'date') else row[0]
        table_last = row[1].date() if hasattr(row[1], 'date') else row[1]
        return (table_last - dev_last).days > _OFFLINE_THRESHOLD_DAYS
    except Exception:
        return False


def _process_signal(engine, signal, domain, cfg, user_role, cross_domain, llm):
    """Prépare contexte + appelle LLM pour un signal. Soumis via ThreadPoolExecutor."""
    device           = signal.get('device_id')
    device_ctx       = _get_device_context(engine, device, domain) if device else None
    priority_boosted = _needs_priority_boost(engine, device, signal['rec_type'])
    device_label     = _resolve_device_label(engine, device, domain) if device else None
    rag_context      = ''
    try:
        from rag.retriever import retrieve_context
        rag_context = retrieve_context(engine, signal['rec_type'], domain, device, user_role)
    except Exception:
        pass
    prompt     = _build_llm_prompt(signal, domain, cfg, user_role, device_ctx, cross_domain, priority_boosted, rag_context, device_label)
    llm_result = _call_llm(prompt, llm)
    i18n       = _translate_recommendation(llm_result, llm) if llm_result else None
    return signal, device_label, priority_boosted, llm_result, i18n


def generate_domain(engine, domain: str, user_role: str = 'gestionnaire') -> int:
    """
    Pipeline complet pour un domaine :
    détection -> enrichissement Chronos -> feedback suppression
    -> contexte device -> cross-domaine -> LLM parallèle (CoT) -> insertion
    """
    cfg = DOMAIN_CONFIG.get(domain)
    if not cfg:
        return 0

    # Nettoyage systématique des pending AVANT détection — garantit qu'un cycle
    # sans signal supprime quand même les recos obsolètes du cycle précédent.
    _clear_stale_pending(engine, domain, user_role)

    signals = _detect_raw_signals(engine, domain, cfg)
    if not signals:
        logger.info("[reco:%s] Aucun signal statistique — fallback sur anomalies Chronos.", domain)
        signals = _detect_from_ad_anomalies(engine, domain, cfg)
    if not signals:
        logger.info("[reco:%s] Aucun signal détecté (statistique + Chronos).", domain)
        return 0

    signals = _flag_implausible_savings(signals)
    signals = _enrich_with_ad_scores(engine, signals, domain)

    # Exclure les devices hors-ligne — évite de générer des recos pour des capteurs débranchés
    table = cfg['table']
    active_signals = []
    for s in signals:
        dev = s.get('device_id')
        if dev and _is_device_offline(engine, table, dev):
            logger.info("[reco:%s] Device %s hors-ligne depuis >%dd — ignoré.", domain, dev, _OFFLINE_THRESHOLD_DAYS)
            continue
        active_signals.append(s)
    if not active_signals:
        logger.info("[reco:%s] Tous les devices détectés sont hors-ligne — aucune reco générée.", domain)
        return 0
    signals = active_signals

    existing     = _get_active_keys(engine, domain, user_role)  # uniquement les accepted pour ce rôle
    cross_domain = _get_cross_domain_anomalies(engine, domain)

    candidates = [
        s for s in signals
        if (s.get('device_id'), s['rec_type']) not in existing
        and not _should_suppress(engine, s.get('device_id'), s['rec_type'])
    ]
    candidates.sort(key=lambda s: s.get('estimated_saving_tnd') or 0, reverse=True)
    candidates = candidates[:_MAX_LLM_CALLS_PER_DOMAIN]

    # Chaque thread reçoit llm=None et crée sa propre instance LLM (thread-safety).
    # LangChain LLM objects ne sont pas thread-safe — ne pas partager entre workers.
    recos  = []
    llm_ok = 0
    llm_fb = 0

    # Appels LLM parallèles (max 3 threads simultanés)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futs = {
            executor.submit(_process_signal, engine, sig, domain, cfg, user_role, cross_domain, None): sig
            for sig in candidates
        }
        for fut in concurrent.futures.as_completed(futs):
            try:
                signal, device_label, priority_boosted, llm_result, i18n = fut.result()
            except Exception as exc:
                logger.warning("[reco:%s] Exception thread LLM : %s", domain, exc)
                continue

            device   = signal.get('device_id')
            rec_type = signal['rec_type']

            if llm_result:
                llm_ok  += 1
                priority = llm_result.get('priority', 'medium')
                if priority_boosted:
                    priority = {'medium': 'high', 'low': 'medium'}.get(priority, priority)
                fr_reasoning = _validate_reasoning(llm_result.get('reasoning'))
                if i18n and fr_reasoning is None:
                    # Le français a été rejeté (placeholder/trop court) — ne pas laisser
                    # une traduction "fantôme" incohérente subsister dans les autres langues.
                    for lang_fields in i18n.values():
                        lang_fields['reasoning'] = None
                rec = {
                    'domain'              : domain,
                    'device_id'           : device,
                    'rec_type'            : rec_type,
                    'target_role'         : user_role,
                    'priority'            : priority,
                    'title'               : llm_result.get('title', '—'),
                    'description'         : llm_result.get('description', '—'),
                    'action'              : llm_result.get('action', '—'),
                    'reasoning'           : fr_reasoning,
                    'i18n'                : i18n,
                    # Le LLM peut recalculer un montant à partir des volumes : même garde-fou
                    'estimated_saving_tnd': None if signal.get('saving_unreliable')
                                            else llm_result.get('estimated_saving_tnd') or signal.get('estimated_saving_tnd'),
                    'deviation_pct'       : signal.get('deviation_pct'),
                }
            else:
                llm_fb += 1
                fb = _rule_based_fallback(signal, domain)
                if not fb:
                    continue
                priority = fb['priority']
                if priority_boosted:
                    priority = {'medium': 'high', 'low': 'medium'}.get(priority, priority)
                rec = {
                    'domain'              : domain,
                    'device_id'           : device,
                    'rec_type'            : rec_type,
                    'target_role'         : user_role,
                    'priority'            : priority,
                    'title'               : fb['title'],
                    'description'         : fb['description'],
                    'action'              : fb['action'],
                    'reasoning'           : None,
                    'i18n'                : fb.get('i18n'),
                    'estimated_saving_tnd': None if signal.get('saving_unreliable')
                                            else fb.get('estimated_saving_tnd') or signal.get('estimated_saving_tnd'),
                    'deviation_pct'       : signal.get('deviation_pct'),
                }

            recos.append(rec)

    n = _insert_recommendations(engine, recos)
    logger.info(
        "[reco:%s] %d candidat(s) -> %d reco(s) | LLM: %d OK / %d fallback",
        domain, len(candidates), n, llm_ok, llm_fb,
    )
    return n
# ── Entrypoint scheduler ──────────────────────────────────────────────────────

def run_recommendation_cycle(engine, domain: str | None = None) -> dict:
    """Cycle complet (baselines + génération + ROI). `domain` restreint à energy|water|gas|fuel."""
    logger.info("[reco] Cycle IA démarré (contexte riche + CoT + feedback loop)… domain=%s", domain or 'all')
    print(f"[reco] Cycle IA démarré (contexte riche + CoT + feedback loop)… domain={domain or 'all'}")
    baselines = compute_baselines(engine, domain=domain)
    print(f"[reco] Baselines calculées : {baselines}")
    generated = generate_all(engine, domain=domain)
    print(f"[reco] Recommandations générées : {generated}")
    roi_count = measure_roi(engine)
    print(f"[reco] ROI évalué pour {roi_count} recommandation(s).")
    result    = {'baselines': baselines, 'generated': generated, 'roi_evaluated': roi_count}
    print(f"[reco] Cycle terminé : {result}")
    logger.info("[reco] Cycle terminé : %s", result)
    return result
