"""Contexte d’un signal : anti-fatigue, historique device, corrélations cross-domaine."""
from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger('aria.reco_engine')

# ══════════════════════════════════════════════════════════════════════════════
# 4. FEEDBACK LOOP
# ══════════════════════════════════════════════════════════════════════════════

# Types critiques qui ne doivent jamais être supprimés par anti-fatigue
_NEVER_SUPPRESS = frozenset({'LEAK_RISK'})


def _should_suppress(engine, device_id: str | None, rec_type: str) -> bool:
    """
    Supprime la re-génération si dismissé >= 2 fois en 7 jours.
    Anti-fatigue : l'utilisateur a consciemment ignoré ce signal.
    Les types LEAK_RISK ne sont jamais supprimés (risque sécurité).
    """
    if rec_type in _NEVER_SUPPRESS:
        return False
    if not device_id:
        return False
    try:
        with engine.connect() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM aria_recommendations
                WHERE device_id = :dev AND rec_type = :type AND status = 'dismissed'
                  AND generated_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
            """), {'dev': device_id, 'type': rec_type}).scalar()
        return (count or 0) >= 2
    except Exception:
        return False


def _needs_priority_boost(engine, device_id: str | None, rec_type: str) -> bool:
    """
    True si une reco acceptée de ce type existe depuis >24h sans être 'done'.
    Le problème persiste malgré l'acceptation -> hausse de priorité.
    """
    if not device_id:
        return False
    try:
        with engine.connect() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM aria_recommendations
                WHERE device_id = :dev AND rec_type = :type AND status = 'accepted'
                  AND acted_at < DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """), {'dev': device_id, 'type': rec_type}).scalar()
        return (count or 0) > 0
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONTEXTE HISTORIQUE DU DEVICE
# ══════════════════════════════════════════════════════════════════════════════

def _get_device_context(engine, device_id: str, domain: str) -> dict:
    """
    Charge le contexte historique riche du device :
    alertes actives, tendance Chronos 4 semaines, interventions passées, compteurs feedback.
    """
    ctx = {
        'recent_alerts'     : [],
        'chronos_trend_4w'  : [],
        'past_interventions': [],
        'dismissed_7d'      : 0,
        'accepted_7d'       : 0,
    }

    try:
        base_id = device_id.split('_')[0] if '_' in device_id else device_id
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT message, type, date FROM alerts
                WHERE id_device = :dev AND date > DATE_SUB(NOW(), INTERVAL 7 DAY)
                ORDER BY date DESC LIMIT 4
            """), {'dev': base_id}).fetchall()
        ctx['recent_alerts'] = [
            {'msg': str(r[0])[:100], 'sev': str(r[1]), 'at': str(r[2])} for r in rows
        ]
    except Exception:
        pass

    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    CONCAT('S', LPAD(WEEK(run_at), 2, '0')) AS week_label,
                    ROUND(AVG(anomaly_score), 2)             AS avg_score,
                    SUM(is_anomaly)                          AS anomaly_count
                FROM ad_results
                WHERE item_id = :dev AND domain = :dom
                  AND run_at > DATE_SUB(NOW(), INTERVAL 28 DAY)
                GROUP BY WEEK(run_at)
                ORDER BY WEEK(run_at)
            """), {'dev': device_id, 'dom': domain}).fetchall()
        ctx['chronos_trend_4w'] = [
            {'week': r[0], 'avg_score': float(r[1] or 0), 'anomalies': int(r[2] or 0)}
            for r in rows
        ]
    except Exception:
        pass

    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT title, action, status, measured_saving_tnd, acted_at
                FROM aria_recommendations
                WHERE device_id = :dev AND status IN ('accepted', 'done')
                ORDER BY acted_at DESC LIMIT 3
            """), {'dev': device_id}).fetchall()
        ctx['past_interventions'] = [
            {'title': str(r[0])[:80], 'status': str(r[2]),
             'saving': float(r[3]) if r[3] else None, 'at': str(r[4]) if r[4] else None}
            for r in rows
        ]
    except Exception:
        pass

    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    SUM(CASE WHEN status='dismissed' THEN 1 ELSE 0 END) AS dismissed,
                    SUM(CASE WHEN status='accepted'  THEN 1 ELSE 0 END) AS accepted
                FROM aria_recommendations
                WHERE device_id = :dev AND domain = :dom
                  AND generated_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
            """), {'dev': device_id, 'dom': domain}).fetchone()
        if row:
            ctx['dismissed_7d'] = int(row[0] or 0)
            ctx['accepted_7d']  = int(row[1] or 0)
    except Exception:
        pass

    return ctx


# ══════════════════════════════════════════════════════════════════════════════
# 6. CORRÉLATION CROSS-DOMAINE
# ══════════════════════════════════════════════════════════════════════════════

def _get_cross_domain_anomalies(engine, current_domain: str) -> list[dict]:
    """
    Retourne les autres domaines avec anomalies actives dans les 26h.
    Permet au LLM de raisonner sur une origine commune éventuelle.
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT domain, COUNT(*) AS cnt, ROUND(AVG(anomaly_score), 2) AS avg_score
                FROM ad_results
                WHERE run_at >= DATE_SUB(NOW(), INTERVAL 26 HOUR)
                  AND is_anomaly = 1
                  AND domain != :d
                GROUP BY domain
                HAVING cnt > 0
                ORDER BY avg_score DESC
            """), {'d': current_domain}).fetchall()
        return [
            {'domain': r[0], 'anomaly_count': int(r[1]), 'avg_score': float(r[2] or 0)}
            for r in rows
        ]
    except Exception:
        return []
