"""Persistance des recommandations dans aria_recommendations."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger('aria.reco_engine')

# ══════════════════════════════════════════════════════════════════════════════
# 11. PERSISTANCE
# ══════════════════════════════════════════════════════════════════════════════

def _get_active_keys(engine, domain: str, user_role: str) -> set:
    """Retourne les (device_id, rec_type) ACCEPTÉS pour ce rôle — ne pas régénérer."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT device_id, rec_type FROM aria_recommendations "
            "WHERE domain=:d AND target_role=:role AND status='accepted' AND expires_at > NOW()"
        ), {'d': domain, 'role': user_role}).fetchall()
    return {(r[0], r[1]) for r in rows}


def _clear_stale_pending(engine, domain: str, user_role: str) -> None:
    """Supprime les 'pending' du domaine pour ce rôle avant régénération."""
    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM aria_recommendations WHERE domain=:d AND target_role=:role AND status='pending'"
        ), {'d': domain, 'role': user_role})


# Durée de validité (heures) selon le type de recommandation
_EXPIRES_HOURS: dict[str, int] = {
    'LEAK_RISK'      : 24,   # urgent, renouveler rapidement
    'OVERCONSUMPTION': 48,
    'OPTIMIZATION'   : 72,
    'BUDGET_ALERT'   : 72,
    'MAINTENANCE'    : 96,   # laisse le temps de planifier
    'EFFICIENCY'     : 72,
}
_DEFAULT_EXPIRES_HOURS = 48


def _insert_recommendations(engine, recos: list) -> int:
    if not recos:
        return 0
    # Vérifie l'existence avant d'insérer pour éviter les doublons en cas de refresh concurrent.
    # device_id peut être NULL (BUDGET_ALERT global) — comparaison IS NULL gérée explicitement.
    check_sql = text("""
        SELECT id FROM aria_recommendations
        WHERE domain = :domain
          AND rec_type = :rec_type
          AND target_role = :target_role
          AND status = 'pending'
          AND ((:device_id IS NULL AND device_id IS NULL) OR device_id = :device_id)
        LIMIT 1
    """)
    insert_sql = text("""
        INSERT INTO aria_recommendations
          (domain, device_id, rec_type, target_role, priority, title, description, action,
           reasoning, i18n, estimated_saving_tnd, deviation_pct, expires_at)
        VALUES
          (:domain, :device_id, :rec_type, :target_role, :priority, :title, :description, :action,
           :reasoning, :i18n, :estimated_saving_tnd, :deviation_pct, :expires_at)
    """)
    inserted = 0
    with engine.begin() as conn:
        for r in recos:
            # Skip si une reco pending identique existe déjà (double /refresh)
            existing = conn.execute(check_sql, {
                'domain'     : r['domain'],
                'rec_type'   : r['rec_type'],
                'target_role': r.get('target_role', 'gestionnaire'),
                'device_id'  : r.get('device_id'),
            }).fetchone()
            if existing:
                logger.debug("[reco:insert] Doublon ignoré : %s/%s/%s",
                             r['domain'], r['rec_type'], r.get('device_id'))
                continue

            hours   = _EXPIRES_HOURS.get(r['rec_type'], _DEFAULT_EXPIRES_HOURS)
            expires = datetime.utcnow() + timedelta(hours=hours)
            conn.execute(insert_sql, {
                'domain'              : r['domain'],
                'device_id'           : r.get('device_id'),
                'rec_type'            : r['rec_type'],
                'target_role'         : r.get('target_role', 'gestionnaire'),
                'priority'            : r['priority'],
                'title'               : r['title'],
                'description'         : r['description'],
                'action'              : r['action'],
                'reasoning'           : r.get('reasoning'),
                'i18n'                : json.dumps(r['i18n'], ensure_ascii=False) if r.get('i18n') else None,
                'estimated_saving_tnd': r.get('estimated_saving_tnd'),
                'deviation_pct'       : r.get('deviation_pct'),
                'expires_at'          : expires,
            })
            inserted += 1
    return inserted
