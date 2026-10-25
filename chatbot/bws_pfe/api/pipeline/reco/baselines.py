"""Baselines P10/P50/P90 par (device, domaine, heure de la semaine)."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text

from .config import DOMAIN_CONFIG

logger = logging.getLogger('aria.reco_engine')

# ══════════════════════════════════════════════════════════════════════════════
# 1. CALCUL DES BASELINES
# ══════════════════════════════════════════════════════════════════════════════

_BASELINES_TTL_SECONDS = 6 * 3600  # recalcul au plus une fois toutes les 6h


def compute_baselines(engine, days: int = 90, force: bool = False, domain: str | None = None) -> dict:
    """Calcule P10/P50/P90 par (device_id, domain, hour_of_week) sur les derniers `days` jours.

    90 jours minimum pour avoir ≥12 observations par slot hour_of_week et des percentiles fiables.
    Skippé si les baselines ont été recalculées il y a moins de 6h, sauf si force=True.
    `domain` restreint le calcul à un seul domaine (energy|water|gas|fuel) au lieu des 4.
    """
    if not force:
        try:
            with engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT MIN(computed_at) FROM device_baselines"
                )).fetchone()
            if row and row[0]:
                age = (datetime.now() - row[0]).total_seconds()
                if age < _BASELINES_TTL_SECONDS:
                    logger.info("[baselines] Fraîches (%.0fmin < 360min) — skip recalcul.", age / 60)
                    return {'skipped': True, 'age_minutes': round(age / 60)}
        except Exception:
            pass

    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas requis pour compute_baselines")
        return {}

    domains = {domain: DOMAIN_CONFIG[domain]} if domain else DOMAIN_CONFIG
    results = {}
    for domain, cfg in domains.items():
        try:
            print(f"[DEBUG] Computing baselines for domain: {domain} with config: {cfg}", flush=True)
            df = _load_domain_data(engine, domain, cfg, days)
            if df.empty:
                results[domain] = 0
                continue

            df['date'] = pd.to_datetime(df['date'])
            df['hour_of_week'] = df['date'].dt.dayofweek * 24 + df['hour']

            grp = df.groupby(['device_id', 'hour_of_week'])['value']
            baselines = pd.DataFrame({
                'p10'         : grp.quantile(0.10),
                'p50'         : grp.quantile(0.50),
                'p90'         : grp.quantile(0.90),
                'sample_count': grp.count(),
            }).reset_index()

            n = _upsert_baselines(engine, domain, baselines)
            results[domain] = n
            logger.info("[baselines:%s] %d lignes upsertées.", domain, n)

        except Exception as exc:
            logger.error("[baselines:%s] Erreur : %s", domain, exc, exc_info=True)
            results[domain] = -1

    return results


def _load_domain_data(engine, domain: str, cfg: dict, days: int):
    import pandas as pd
    table   = cfg['table']
    val_col = cfg['value_col']
    # Ancre sur MAX(date) et non CURDATE() — robuste quand le pipeline de données
    # a du retard ou utilise des données historiques (replay, démo, back-fill).
    anchor = f"(SELECT MAX(date) FROM {table})"

    if cfg['group_phases']:
        sql = text(f"""
            SELECT device_id, date, hour, SUM(COALESCE({val_col}, 0)) AS value
            FROM   {table}
            WHERE  date >= DATE_SUB({anchor}, INTERVAL :days DAY)
            GROUP BY device_id, date, hour
        """)
    else:
        sql = text(f"""
            SELECT device_id, date, hour, COALESCE({val_col}, 0) AS value
            FROM   {table}
            WHERE  date >= DATE_SUB({anchor}, INTERVAL :days DAY)
        """)

    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={'days': days})


def _upsert_baselines(engine, domain: str, df) -> int:
    if df.empty:
        return 0
    sql = text("""
        INSERT INTO device_baselines (device_id, domain, hour_of_week, p10, p50, p90, sample_count)
        VALUES (:dev, :dom, :how, :p10, :p50, :p90, :cnt)
        ON DUPLICATE KEY UPDATE
            p10=VALUES(p10), p50=VALUES(p50), p90=VALUES(p90),
            sample_count=VALUES(sample_count), computed_at=NOW()
    """)
    rows = df.to_dict(orient='records')
    with engine.begin() as conn:
        for row in rows:
            conn.execute(sql, {
                'dev': str(row['device_id']),
                'dom': domain,
                'how': int(row['hour_of_week']),
                'p10': float(row['p10']) if row['p10'] == row['p10'] else None,
                'p50': float(row['p50']) if row['p50'] == row['p50'] else None,
                'p90': float(row['p90']) if row['p90'] == row['p90'] else None,
                'cnt': int(row['sample_count']),
            })
    return len(rows)
