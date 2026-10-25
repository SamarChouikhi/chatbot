"""Mesure du ROI des recommandations acceptées."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from .config import DOMAIN_CONFIG

logger = logging.getLogger('aria.reco_engine')

# ══════════════════════════════════════════════════════════════════════════════
# 12. MESURE ROI
# ══════════════════════════════════════════════════════════════════════════════

# Fenêtre de mesure ROI (heures avant/après acted_at) selon le type de recommandation.
# Les actions de maintenance ou de budget nécessitent plus de temps pour produire un effet.
_ROI_WINDOW_HOURS: dict[str, int] = {
    'OVERCONSUMPTION': 72,
    'LEAK_RISK'      : 72,
    'OPTIMIZATION'   : 120,   # 5 jours — ajustements planifiés
    'MAINTENANCE'    : 168,   # 7 jours — intervention + stabilisation
    'BUDGET_ALERT'   : 168,
    'EFFICIENCY'     : 168,
}
_ROI_DEFAULT_WINDOW  = 72   # fallback pour tout type non listé
_ROI_MIN_DELTA_PCT   = 2.0  # ignorer si la variation < 2 % (bruit statistique)

# Requêtes ROI pré-écrites par domaine — aucune interpolation de chaîne dynamique.
_ROI_QUERIES: dict[str, str] = {
    'energy': """
        SELECT
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :bf AND :at
                   THEN COALESCE(cons_en, 0) ELSE 0 END)  AS before_v,
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :at AND :ato
                   THEN COALESCE(cons_en, 0) ELSE 0 END)  AS after_v
        FROM daily_energy
        WHERE device_id = :dev AND date BETWEEN DATE(:bf) AND DATE(:ato)
    """,
    'water': """
        SELECT
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :bf AND :at
                   THEN COALESCE(conso_m3, 0) ELSE 0 END) AS before_v,
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :at AND :ato
                   THEN COALESCE(conso_m3, 0) ELSE 0 END) AS after_v
        FROM daily_water
        WHERE device_id = :dev AND date BETWEEN DATE(:bf) AND DATE(:ato)
    """,
    'gas': """
        SELECT
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :bf AND :at
                   THEN COALESCE(conso_m3, 0) ELSE 0 END) AS before_v,
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :at AND :ato
                   THEN COALESCE(conso_m3, 0) ELSE 0 END) AS after_v
        FROM daily_gas
        WHERE device_id = :dev AND date BETWEEN DATE(:bf) AND DATE(:ato)
    """,
    'fuel': """
        SELECT
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :bf AND :at
                   THEN COALESCE(consumption, 0) ELSE 0 END) AS before_v,
          SUM(CASE WHEN TIMESTAMP(date, SEC_TO_TIME(hour*3600)) BETWEEN :at AND :ato
                   THEN COALESCE(consumption, 0) ELSE 0 END) AS after_v
        FROM daily_fuel
        WHERE device_id = :dev AND date BETWEEN DATE(:bf) AND DATE(:ato)
    """,
}


def measure_roi(engine) -> int:
    try:
        with engine.connect() as conn:
            # Sélectionne aussi rec_type pour adapter la fenêtre de mesure
            rows = conn.execute(text("""
                SELECT id, domain, device_id, rec_type, acted_at FROM aria_recommendations
                WHERE status = 'accepted'
                  AND acted_at IS NOT NULL
                  AND measured_saving_tnd IS NULL
            """)).fetchall()

        if not rows:
            return 0

        count = 0
        for row in rows:
            rec_id, domain, device_id, rec_type, acted_at = row
            if not device_id:
                continue
            cfg = DOMAIN_CONFIG.get(domain)
            roi_sql = _ROI_QUERIES.get(domain)
            if not cfg or not roi_sql:
                continue

            # Fenêtre adaptive selon le type d'action
            window_hours = _ROI_WINDOW_HOURS.get(rec_type or '', _ROI_DEFAULT_WINDOW)
            # N'évalue qu'une fois la fenêtre after écoulée
            if datetime.utcnow() < acted_at + timedelta(hours=window_hours):
                continue

            before_from = acted_at - timedelta(hours=window_hours)
            after_to    = acted_at + timedelta(hours=window_hours)

            try:
                with engine.connect() as conn:
                    res = conn.execute(text(roi_sql), {
                        'dev': device_id, 'bf': before_from, 'at': acted_at, 'ato': after_to,
                    }).fetchone()

                if res and res[0] and res[1]:
                    before_v = float(res[0])
                    after_v  = float(res[1])
                    delta    = before_v - after_v
                    # Ignore les variations inférieures au seuil minimal (bruit statistique)
                    delta_pct = (delta / before_v * 100) if before_v > 0 else 0
                    if abs(delta_pct) < _ROI_MIN_DELTA_PCT:
                        measured = 0.0
                    else:
                        measured = round(max(0.0, delta) * cfg['cost_per_unit'], 2)
                    with engine.begin() as conn:
                        conn.execute(text(
                            "UPDATE aria_recommendations SET measured_saving_tnd=:m WHERE id=:id"
                        ), {'m': measured, 'id': rec_id})
                    count += 1
            except Exception:
                pass

        logger.info("[reco:ROI] %d recommandation(s) évaluées.", count)
        return count

    except Exception as exc:
        logger.error("[reco:ROI] Erreur : %s", exc, exc_info=True)
        return 0
