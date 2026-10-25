"""Détection des signaux (statistiques, Chronos, budget, maintenance, efficacité)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from .baselines import _load_domain_data

logger = logging.getLogger('aria.reco_engine')

# ══════════════════════════════════════════════════════════════════════════════
# 2. DÉTECTION DE SIGNAUX (statistique pure — sans texte)
# ══════════════════════════════════════════════════════════════════════════════

def _detect_raw_signals(engine, domain: str, cfg: dict) -> list[dict]:
    try:
        import pandas as pd

        actual_df = _load_domain_data(engine, domain, cfg, days=2)
        if actual_df.empty:
            return []

        actual_df['date'] = pd.to_datetime(actual_df['date'])
        # Ancre sur la date max réelle — pas sur datetime.utcnow() — pour rester
        # fonctionnel quand les données ont du retard ou sont historiques.
        max_date = actual_df['date'].max()
        cutoff   = max_date - timedelta(hours=26)
        actual_df = actual_df[actual_df['date'] >= cutoff]
        if actual_df.empty:
            return []

        actual_df['hour_of_week'] = actual_df['date'].dt.dayofweek * 24 + actual_df['hour']

        with engine.connect() as conn:
            bl_rows = conn.execute(text(
                "SELECT device_id, hour_of_week, p10, p50, p90, sample_count "
                "FROM device_baselines WHERE domain = :d AND sample_count >= 4"
            ), {'d': domain}).fetchall()

        if not bl_rows:
            return []

        baseline_df = pd.DataFrame(
            bl_rows, columns=['device_id', 'hour_of_week', 'p10', 'p50', 'p90', 'sample_count']
        )
        merged  = actual_df.merge(baseline_df, on=['device_id', 'hour_of_week'], how='inner')
        signals = []

        # OVERCONSUMPTION : valeur > P90
        over = merged[merged['value'] > merged['p90']].copy()
        for device_id, grp in over.groupby('device_id'):
            p50_mean = grp['p50'].mean()
            if p50_mean <= 0:
                continue
            deviation  = float((grp['value'] - grp['p50']).mean() / p50_mean * 100)
            excess     = float((grp['value'] - grp['p50']).clip(lower=0).sum())
            peak_hours = grp.nlargest(3, 'value')['hour'].astype(int).tolist()
            signals.append({
                'rec_type'            : 'OVERCONSUMPTION',
                'device_id'           : str(device_id),
                'actual_26h'          : round(float(grp['value'].sum()), 3),
                'baseline_p50_sum'    : round(float(grp['p50'].sum()), 3),
                'baseline_p90_sum'    : round(float(grp['p90'].sum()), 3),
                'deviation_pct'       : round(deviation, 1),
                'excess_units'        : round(excess, 3),
                'peak_hours'          : peak_hours,
                'estimated_saving_tnd': round(excess * cfg['cost_per_unit'], 2),
                'unit'                : cfg['unit'],
                'label'               : cfg['label'],
            })

        # OPTIMIZATION : heures creuses > P50
        off_start = cfg.get('off_peak_start')
        if off_start is not None:
            off_end = cfg['off_peak_end']

            def _is_off_peak(h):
                return (h >= off_start or h < off_end) if off_start > off_end else (off_start <= h < off_end)

            off_mask = merged['hour'].apply(_is_off_peak)
            off_data = merged[off_mask & (merged['value'] > merged['p50'])]
            for device_id, grp in off_data.groupby('device_id'):
                if len(grp) < 3:
                    continue
                excess = float((grp['value'] - grp['p50']).clip(lower=0).sum())
                if excess * cfg['cost_per_unit'] < 1.0:
                    continue
                signals.append({
                    'rec_type'            : 'OPTIMIZATION',
                    'device_id'           : str(device_id),
                    'off_peak_excess'     : round(excess, 3),
                    'off_peak_hours'      : f"{off_start}h–{off_end}h",
                    'hours_affected'      : len(grp),
                    'deviation_pct'       : None,
                    'estimated_saving_tnd': round(excess * cfg['cost_per_unit'] * 30, 2),
                    'unit'                : cfg['unit'],
                    'label'               : cfg['label'],
                })

        # BUDGET_ALERT
        budget = _detect_budget_signal(engine, domain, cfg)
        if budget:
            signals.append(budget)

        # MAINTENANCE
        signals += _detect_maintenance_signals(engine, domain, cfg)

        # LEAK_RISK
        if domain in ('water', 'gas'):
            night = merged[
                (merged['hour'] >= 1) & (merged['hour'] <= 5) & (merged['value'] > merged['p50'])
            ]
            for device_id, grp in night.groupby('device_id'):
                excess = float((grp['value'] - grp['p50']).clip(lower=0).sum())
                if excess < 0.01:
                    continue
                signals.append({
                    'rec_type'            : 'LEAK_RISK',
                    'device_id'           : str(device_id),
                    'nocturnal_excess'    : round(excess, 4),
                    'hours_range'         : '1h–5h',
                    'deviation_pct'       : None,
                    'estimated_saving_tnd': round(excess * cfg['cost_per_unit'] * 30, 2),
                    'unit'                : cfg['unit'],
                    'label'               : cfg['label'],
                })

        # EFFICIENCY (fuel)
        if domain == 'fuel':
            signals += _detect_efficiency_signals(engine, cfg)

        return signals

    except Exception as exc:
        logger.error("[signals:%s] Erreur : %s", domain, exc, exc_info=True)
        return []


def _detect_from_ad_anomalies(engine, domain: str, cfg: dict) -> list[dict]:
    """Fallback : génère des signaux depuis les anomalies Chronos (ad_results) quand
    la détection statistique ne trouve rien. Évite que le moteur reste muet quand
    les données récentes sont dans la fenêtre de baseline."""
    try:
        with engine.connect() as conn:
            # Fenêtre : dernières 72h relatives à MAX(run_at) dans ad_results
            rows = conn.execute(text("""
                SELECT item_id,
                       ROUND(AVG(anomaly_score), 3) AS avg_score,
                       SUM(is_anomaly)              AS anomaly_count,
                       MAX(value)                   AS peak_value,
                       MAX(run_at)                  AS latest_run
                FROM ad_results
                WHERE domain  = :dom
                  AND is_anomaly = 1
                  AND run_at >= DATE_SUB(
                        (SELECT MAX(run_at) FROM ad_results WHERE domain = :dom),
                        INTERVAL 72 HOUR
                      )
                GROUP BY item_id
                HAVING anomaly_count >= 2 AND avg_score >= 0.55
                ORDER BY avg_score DESC
                LIMIT 10
            """), {'dom': domain}).fetchall()

        signals = []
        for r in rows:
            device_id, avg_score, anomaly_count, peak_value, latest_run = r
            rec_type = 'OVERCONSUMPTION' if avg_score >= 0.75 else 'MAINTENANCE'
            # peak_value est une lecture brute du capteur (index cumulatif ou valeur ponctuelle),
            # pas une consommation sur 26h. Ne jamais l'exposer dans le signal — le LLM
            # l'utiliserait comme volume de conso et produirait des chiffres absurdes.
            signals.append({
                'rec_type'            : rec_type,
                'device_id'           : str(device_id),
                'actual_26h'          : None,
                'baseline_p50_sum'    : None,
                'baseline_p90_sum'    : None,
                'deviation_pct'       : round((avg_score - 0.5) * 200, 1),
                'excess_units'        : None,
                'peak_hours'          : [],
                'estimated_saving_tnd': None,
                'chronos_score'       : float(avg_score),
                'chronos_flagged'     : True,
                'no_consumption_data' : True,   # bloque toute hallucination de volume LLM
                'ad_anomaly_count'    : int(anomaly_count),
                'unit'                : cfg['unit'],
                'label'               : cfg['label'],
            })
        return signals
    except Exception as exc:
        logger.warning("[signals:%s] Fallback AD échoué : %s", domain, exc)
        return []


def _detect_budget_signal(engine, domain: str, cfg: dict) -> dict | None:
    try:
        table   = cfg['table']
        val_col = cfg['value_col']
        agg     = f"SUM(COALESCE({val_col}, 0))"

        sql = text(f"""
            SELECT
              SUM(CASE WHEN date >= DATE_FORMAT(NOW(),'%%Y-%%m-01')
                       THEN {agg} ELSE 0 END) AS current_month,
              SUM(CASE WHEN date >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 1 MONTH),'%%Y-%%m-01')
                        AND date <  DATE_FORMAT(NOW(),'%%Y-%%m-01')
                       THEN {agg} ELSE 0 END) AS last_month
            FROM {table}
            WHERE date >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 1 MONTH),'%%Y-%%m-01')
        """)
        with engine.connect() as conn:
            row = conn.execute(sql).fetchone()

        if not row or not row[1]:
            return None

        current   = float(row[0] or 0)
        last      = float(row[1])
        day       = datetime.utcnow().day
        projected = (current / max(day, 1)) * 30
        overage   = (projected - last) / last * 100 if last > 0 else 0

        if overage < 10:
            return None

        return {
            'rec_type'            : 'BUDGET_ALERT',
            'device_id'           : None,
            'current_month_so_far': round(current, 1),
            'last_month_total'    : round(last, 1),
            'projected_total'     : round(projected, 1),
            'overage_pct'         : round(overage, 1),
            'day_of_month'        : day,
            'deviation_pct'       : round(overage, 1),
            'estimated_saving_tnd': round(max(0, projected - last) * cfg['cost_per_unit'] * 0.5, 2),
            'unit'                : cfg['unit'],
            'label'               : cfg['label'],
        }
    except Exception:
        return None


def _detect_maintenance_signals(engine, domain: str, cfg: dict) -> list:
    try:
        import pandas as pd
        table   = cfg['table']
        val_col = cfg['value_col']
        # Ancre sur MAX(date) — cohérent avec _load_domain_data, fonctionnel en mode replay
        anchor  = f"(SELECT COALESCE(MAX(date), CURDATE()) FROM {table})"

        sql = text(f"""
            SELECT device_id, date, SUM(COALESCE({val_col}, 0)) AS daily_total
            FROM {table}
            WHERE date >= DATE_SUB({anchor}, INTERVAL 8 DAY)
            GROUP BY device_id, date ORDER BY device_id, date
        """)
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)

        if df.empty:
            return []

        signals = []
        for device_id, grp in df.groupby('device_id'):
            grp  = grp.sort_values('date')
            if len(grp) < 5:
                continue
            vals = grp['daily_total'].tolist()
            monotone = sum(1 for i in range(1, len(vals)) if vals[i] > vals[i - 1])
            if monotone < 4:
                continue
            growth = (vals[-1] - vals[0]) / (vals[0] + 1e-6) * 100
            if growth < 15:
                continue
            signals.append({
                'rec_type'            : 'MAINTENANCE',
                'device_id'           : str(device_id),
                'trend_growth_pct'    : round(growth, 1),
                'day1_value'          : round(vals[0], 2),
                'day7_value'          : round(vals[-1], 2),
                'monotone_days'       : monotone,
                'deviation_pct'       : round(growth, 1),
                'estimated_saving_tnd': round((vals[-1] - vals[0]) * cfg['cost_per_unit'] * 30, 2),
                'unit'                : cfg['unit'],
                'label'               : cfg['label'],
            })
        return signals
    except Exception:
        return []


def _detect_efficiency_signals(engine, cfg: dict) -> list:
    try:
        import pandas as pd
        sql = text("""
            SELECT device_id, SUM(COALESCE(consumption, 0)) AS total_conso
            FROM daily_fuel
            WHERE date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY device_id HAVING total_conso > 0
        """)
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)

        if df.empty or len(df) < 2:
            return []

        mean_conso = df['total_conso'].mean()
        signals = []
        for _, row in df[df['total_conso'] > mean_conso * 1.35].iterrows():
            over_pct = (row['total_conso'] / mean_conso - 1) * 100
            signals.append({
                'rec_type'            : 'EFFICIENCY',
                'device_id'           : str(row['device_id']),
                'vehicle_conso_7d'    : round(float(row['total_conso']), 1),
                'fleet_mean_7d'       : round(float(mean_conso), 1),
                'over_pct'            : round(over_pct, 1),
                'deviation_pct'       : round(over_pct, 1),
                'estimated_saving_tnd': round((row['total_conso'] - mean_conso) * cfg['cost_per_unit'], 2),
                'unit'                : cfg['unit'],
                'label'               : cfg['label'],
            })
        return signals
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 3. ENRICHISSEMENT CHRONOS
# ══════════════════════════════════════════════════════════════════════════════

def _enrich_with_ad_scores(engine, signals: list, domain: str) -> list:
    if not signals:
        return signals
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT item_id, AVG(anomaly_score) AS avg_score, MAX(is_anomaly) AS flagged
                FROM ad_results
                WHERE domain = :dom AND run_at >= DATE_SUB(NOW(), INTERVAL 2 DAY)
                GROUP BY item_id
            """), {'dom': domain}).fetchall()
        score_map = {r[0]: {'score': float(r[1] or 0), 'flagged': bool(r[2])} for r in rows}
        for sig in signals:
            device = sig.get('device_id')
            if device and device in score_map:
                sig['chronos_score']   = round(score_map[device]['score'], 3)
                sig['chronos_flagged'] = score_map[device]['flagged']
    except Exception:
        pass
    return signals
