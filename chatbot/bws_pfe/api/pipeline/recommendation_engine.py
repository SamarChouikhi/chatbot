"""
Moteur de recommandations IA personnalisées ARIA — v2 (LLM + contexte riche + feedback loop).

Pipeline :
  1. compute_baselines()          — P10/P50/P90 par (device, domain, hour_of_week)
  2. _detect_raw_signals()        — détection statistique → signaux avec chiffres réels
  3. _enrich_with_ad_scores()     — score Chronos depuis ad_results
  4. _should_suppress()           — supprime si dismissé ≥ 2 fois en 7 jours (anti-fatigue)
  5. _get_device_context()        — alertes actives, tendance 4 semaines, interventions passées
  6. _get_cross_domain_anomalies()— corrélation avec d'autres domaines anomaux simultanément
  7. _needs_priority_boost()      — hausse priorité si accepté sans action depuis >24h
  8. _build_llm_prompt()          — construit le prompt contextuel complet
  9. _call_llm()                  — LLMFactory → JSON {reasoning, priority, title, …}
  10. _rule_based_fallback()      — fallback si LLM indisponible
  11. measure_roi()               — évalue l'impact 48h après acceptation
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger('aria.reco_engine')

# ── Prompt système — Chain-of-Thought obligatoire ─────────────────────────────
_SYSTEM_PROMPT = """Tu es ARIA, expert BMS senior. Génère une recommandation courte, concrète et personnalisée.

LANGUE OBLIGATOIRE : Réponds EXCLUSIVEMENT en français. Chaque champ (reasoning, title, description, action, root_cause) doit être rédigé en français. Aucun mot anglais n'est accepté.

PROCESSUS (dans cet ordre) :
1. reasoning   → 2-3 phrases en français : signal observé → hypothèse la plus probable → priorité justifiée
2. priority    → critical (< 4h) | high (aujourd'hui) | medium (cette semaine) | low (ce mois)
3. title       → MAX 60 chars en français : nom lisible du device + problème concis
4. description → 1-2 phrases en français UNIQUEMENT avec les chiffres présents dans le contexte — jamais inventés
5. action      → FORMAT PAR RÔLE (voir ci-dessous), en français
6. root_cause  → 1 phrase en français, cause retenue
7. estimated_saving_tnd → calcule UNIQUEMENT si les données de consommation sont présentes, sinon null

FORMAT ACTION PAR RÔLE :
- technicien   : "1. [outil/action] 2. [test] 3. [validation]" — max 3 étapes techniques
- gestionnaire : "Planifier [action] sous [délai]. Coût estimé : [TND si calculable, sinon omis]."
- directeur    : "[Statut] — [1 action décisionnelle]." (max 2 lignes)

RÈGLES ABSOLUES :
- JSON valide uniquement, rien avant ni après
- Tous les champs texte en FRANÇAIS — zéro tolérance pour l'anglais
- Si actual_26h est absent : ne calcule PAS de consommation ni d'économie — utilise le score Chronos
- Utilise le NOM du device (pas l'ID brut) dans title et description
- Si corrélation cross-domaine → mentionne dans root_cause

{
  "reasoning": "...",
  "priority": "critical|high|medium|low",
  "title": "...",
  "description": "...",
  "action": "...",
  "root_cause": "...",
  "estimated_saving_tnd": <nombre ou null>
}"""

import time as _time

_device_label_cache: dict[str, tuple[str, float]] = {}  # key → (label, timestamp)
_DEVICE_LABEL_CACHE_TTL = 300.0  # 5 minutes

# Préfixes lisibles par domaine quand aucune table de correspondance n'existe
_DOMAIN_DEVICE_PREFIX = {
    'energy': 'Compteur Élec.',
    'water' : 'Compteur Eau',
    'gas'   : 'Compteur Gaz',
    'fuel'  : 'Véhicule',
}


def _resolve_device_label(engine, device_id: str, domain: str = '') -> str:
    """Résout device_id → nom lisible.

    Stratégie double :
    1. Via device.adresse  (devices enregistrés avec adresse = id_device, ex: 1001, 1002)
    2. Via device.id       (devices avec adresse=0 mais id = device_id, ex: 6001, 6101, 6201)
    Formate proprement l'ID brut avec préfixe domaine si aucune correspondance.
    """
    if not device_id:
        return 'ensemble du site'
    cache_key = f'{domain}:{device_id}'
    cached = _device_label_cache.get(cache_key)
    if cached and (_time.monotonic() - cached[1]) < _DEVICE_LABEL_CACHE_TTL:
        return cached[0]

    base_id = device_id.split('_')[0] if '_' in device_id else device_id
    numeric_id = int(base_id) if base_id.isdigit() else -1

    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT d.nom, e.nom AS espace
                FROM device d
                LEFT JOIN espace e ON d.id_espace = e.id
                WHERE (d.adresse != 0 AND CAST(d.adresse AS CHAR) = :dev)
                   OR (d.id = :numeric_id)
                ORDER BY CASE WHEN d.adresse != 0 THEN 0 ELSE 1 END
                LIMIT 1
            """), {'dev': base_id, 'numeric_id': numeric_id}).fetchone()
        if row and row[0]:
            phase = device_id.split('_')[1] if '_' in device_id else None
            label = f"{row[0]} ({row[1] or 'Zone inconnue'})"
            if phase:
                label += f" — phase {phase}"
            _device_label_cache[cache_key] = (label, _time.monotonic())
            return label
    except Exception:
        pass

    # Formatage lisible depuis l'ID + préfixe domaine
    prefix = _DOMAIN_DEVICE_PREFIX.get(domain, 'Capteur')
    parts  = device_id.split('_')
    if len(parts) == 2:
        label = f"{prefix} #{parts[0]} — Phase {parts[1]}"
    else:
        label = f"{prefix} #{device_id}"
    _device_label_cache[cache_key] = (label, _time.monotonic())
    return label


# ── Configuration domaines ────────────────────────────────────────────────────
DOMAIN_CONFIG: dict[str, dict] = {
    'energy': {
        'table'         : 'daily_energy',
        'value_col'     : 'cons_en',
        'group_phases'  : True,
        'unit'          : 'kWh',
        'cost_per_unit' : 0.096,
        'off_peak_start': 22,
        'off_peak_end'  : 6,
        'label'         : 'Électricité',
    },
    'water': {
        'table'         : 'daily_water',
        'value_col'     : 'conso_m3',
        'group_phases'  : False,
        'unit'          : 'm³',
        'cost_per_unit' : 0.75,
        'off_peak_start': 1,
        'off_peak_end'  : 5,
        'label'         : 'Eau',
    },
    'gas': {
        'table'         : 'daily_gas',
        'value_col'     : 'conso_m3',
        'group_phases'  : False,
        'unit'          : 'm³',
        'cost_per_unit' : 0.45,
        'off_peak_start': 22,
        'off_peak_end'  : 6,
        'label'         : 'Gaz',
    },
    'fuel': {
        'table'         : 'daily_fuel',
        'value_col'     : 'consumption',
        'group_phases'  : False,
        'unit'          : 'L',
        'cost_per_unit' : 1.92,
        'off_peak_start': None,
        'off_peak_end'  : None,
        'label'         : 'Carburant',
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. CALCUL DES BASELINES
# ══════════════════════════════════════════════════════════════════════════════

_BASELINES_TTL_SECONDS = 6 * 3600  # recalcul au plus une fois toutes les 6h


def compute_baselines(engine, days: int = 90, force: bool = False) -> dict:
    """Calcule P10/P50/P90 par (device_id, domain, hour_of_week) sur les derniers `days` jours.

    90 jours minimum pour avoir ≥12 observations par slot hour_of_week et des percentiles fiables.
    Skippé si les baselines ont été recalculées il y a moins de 6h, sauf si force=True.
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

    results = {}
    for domain, cfg in DOMAIN_CONFIG.items():
        try:
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
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT message, severity, created_at FROM aria_alerts
                WHERE device_id = :dev AND created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
                ORDER BY created_at DESC LIMIT 4
            """), {'dev': device_id}).fetchall()
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


# ══════════════════════════════════════════════════════════════════════════════
# 7. CONSTRUCTION DU PROMPT LLM
# ══════════════════════════════════════════════════════════════════════════════

def _build_llm_prompt(
    signal          : dict,
    domain          : str,
    cfg             : dict,
    user_role       : str,
    device_ctx      : dict | None = None,
    cross_domain    : list | None = None,
    priority_boosted: bool        = False,
    rag_context     : str         = '',
    device_label    : str | None  = None,
) -> str:
    rec_type     = signal['rec_type']
    device_id    = signal.get('device_id') or 'ensemble du site'
    device_label = device_label or device_id   # fallback sur ID brut si résolution impossible
    label        = cfg['label']
    unit         = cfg['unit']

    role_ctx = {
        'technicien'  : "RÔLE TECHNICIEN : action=diagnostic technique (max 3 étapes), inclure outils et points de contrôle.",
        'gestionnaire': "RÔLE GESTIONNAIRE : action=décision opérationnelle avec délai et coût TND si calculable.",
        'directeur'   : "RÔLE DIRECTEUR : action=1 phrase décisionnelle max. description=2 lignes max.",
    }.get(user_role, "RÔLE GESTIONNAIRE : action=décision opérationnelle avec délai.")

    lines = [
        f"DOMAINE : {label}  |  DEVICE : {device_label}  |  TYPE : {rec_type}",
        role_ctx,
    ]

    if priority_boosted:
        lines.append(
            "IMPORTANT : Ce problème a été accepté mais non résolu depuis >24h — "
            "la priorité doit être rehaussée d'un cran."
        )

    def _line(label: str, val, unit_str: str = '') -> str | None:
        """Retourne une ligne de données uniquement si la valeur est disponible (non None)."""
        if val is None:
            return None
        suffix = f' {unit_str}' if unit_str else ''
        return f'  {label}: {val}{suffix}'

    lines += ["", "DONNÉES MESURÉES :"]

    if signal.get('no_consumption_data'):
        # Fallback Chronos : aucune donnée de consommation réelle disponible.
        # INTERDICTION ABSOLUE d'inventer des volumes, valeurs ou baselines.
        score = signal.get('chronos_score', 0)
        count = signal.get('ad_anomaly_count', 0)
        lines += [
            "  ⚠️  DONNÉES DE CONSOMMATION INDISPONIBLES.",
            "  RÈGLE NON NÉGOCIABLE : N'écris AUCUNE valeur numérique de consommation,",
            "  volume, baseline ou économie dans description/action/reasoning.",
            "  Base-toi UNIQUEMENT sur le score Chronos et le nombre de points anormaux.",
            f"  Score anomalie Chronos      : {score:.2f}/1.0 — ANOMALIE CONFIRMÉE",
            f"  Nombre de points anormaux   : {count}",
        ]
    elif rec_type == 'OVERCONSUMPTION':
        raw_lines = [
            _line('Consommation réelle (26h)', signal.get('actual_26h'), unit),
            _line('Baseline normale (P50)   ', signal.get('baseline_p50_sum'), unit),
            _line('Seuil d\'alerte (P90)    ', signal.get('baseline_p90_sum'), unit),
            _line('Déviation vs baseline    ', f"+{signal.get('deviation_pct')}%" if signal.get('deviation_pct') is not None else None),
            _line('Excès consommé           ', signal.get('excess_units'), unit),
        ]
        peak = signal.get('peak_hours', [])
        if peak:
            raw_lines.append(f"  Heures de pic : {', '.join(str(h)+'h' for h in peak)}")
        lines += [l for l in raw_lines if l]
    elif rec_type == 'OPTIMIZATION':
        lines += [
            f"  Excès heures creuses ({signal.get('off_peak_hours')}) : {signal.get('off_peak_excess')} {unit}",
            f"  Tranches horaires concernées : {signal.get('hours_affected')}",
            f"  Économie mensuelle estimée   : {signal.get('estimated_saving_tnd')} TND",
        ]
    elif rec_type == 'BUDGET_ALERT':
        lines += [
            f"  Consommé ce mois (j1→j{signal.get('day_of_month')}) : {signal.get('current_month_so_far')} {unit}",
            f"  Mois précédent total        : {signal.get('last_month_total')} {unit}",
            f"  Projection fin de mois      : {signal.get('projected_total')} {unit}",
            f"  Dépassement projeté         : +{signal.get('overage_pct')}%",
        ]
    elif rec_type == 'MAINTENANCE':
        lines += [
            f"  Croissance sur 7 jours      : +{signal.get('trend_growth_pct')}%",
            f"  Valeur J-7                  : {signal.get('day1_value')} {unit}/j",
            f"  Valeur aujourd'hui          : {signal.get('day7_value')} {unit}/j",
            f"  Jours de hausse consécutifs : {signal.get('monotone_days')}/7",
        ]
    elif rec_type == 'LEAK_RISK':
        lines += [
            f"  Excès nocturne ({signal.get('hours_range')}) : {signal.get('nocturnal_excess')} {unit}",
            f"  Coût mensuel si persistant  : {signal.get('estimated_saving_tnd')} TND",
        ]
    elif rec_type == 'EFFICIENCY':
        lines += [
            f"  Consommation véhicule (7j)  : {signal.get('vehicle_conso_7d')} {unit}",
            f"  Moyenne flotte              : {signal.get('fleet_mean_7d')} {unit}",
            f"  Écart vs flotte             : +{signal.get('over_pct')}%",
        ]

    if signal.get('chronos_score') is not None:
        flag = " — ANOMALIE CONFIRMÉE" if signal.get('chronos_flagged') else ""
        lines.append(f"  Score anomalie Chronos      : {signal['chronos_score']:.2f}/1.0{flag}")

    # Contexte historique
    if device_ctx:
        has_ctx = any([
            device_ctx.get('recent_alerts'),
            device_ctx.get('chronos_trend_4w'),
            device_ctx.get('past_interventions'),
            device_ctx.get('dismissed_7d', 0) > 0,
        ])
        if has_ctx:
            lines += ["", "HISTORIQUE DU DEVICE :"]

            if device_ctx.get('recent_alerts'):
                lines.append("  Alertes récentes (7j) :")
                for a in device_ctx['recent_alerts'][:2]:
                    lines.append(f"    [{a['sev'].upper()}] {a['msg']}")

            trend = device_ctx.get('chronos_trend_4w', [])
            if len(trend) >= 2:
                scores = [w['avg_score'] for w in trend]
                if scores[-1] > scores[0] + 0.1:
                    direction = f"HAUSSE ({scores[0]:.2f} -> {scores[-1]:.2f})"
                elif scores[-1] < scores[0] - 0.1:
                    direction = f"baisse ({scores[0]:.2f} -> {scores[-1]:.2f})"
                else:
                    direction = f"stable ({scores[-1]:.2f})"
                lines.append(f"  Tendance Chronos 4 semaines : {direction}")

            if device_ctx.get('past_interventions'):
                lines.append("  Dernières interventions :")
                for i in device_ctx['past_interventions'][:2]:
                    saving_str = f" — {i['saving']:.1f} TND économisés" if i.get('saving') else ""
                    lines.append(f"    [{i['status'].upper()}] {i['title']}{saving_str}")

            if device_ctx.get('dismissed_7d', 0) > 0:
                lines.append(
                    f"  {device_ctx['dismissed_7d']} alerte(s) de ce type ignorée(s) cette semaine "
                    f"— la recommandation doit apporter une valeur nouvelle."
                )

    # Corrélation cross-domaine
    if cross_domain:
        lines += ["", "CORRÉLATION CROSS-DOMAINE (anomalies simultanées) :"]
        for cd in cross_domain[:3]:
            d_label = DOMAIN_CONFIG.get(cd['domain'], {}).get('label', cd['domain'])
            lines.append(
                f"  {d_label} : {cd['anomaly_count']} anomalie(s), score {cd['avg_score']:.2f}"
            )
        lines.append(
            "  -> Considère une origine commune possible "
            "(infrastructure partagée, événement bâtiment)."
        )

    # Base de connaissance RAG
    if rag_context:
        lines += ["", rag_context]

    lines += ["", "Génère la recommandation JSON en suivant le processus obligatoire."]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 8. APPEL LLM
# ══════════════════════════════════════════════════════════════════════════════

_LLM_CALL_TIMEOUT = 90  # secondes max par appel LLM dans le moteur de reco

_REASONING_MIN_LEN = 30
_REASONING_PLACEHOLDER = re.compile(
    r'\b(placeholder|valeur|value|\[.*?\]|\{.*?\}|xxx|todo|tbd|exemple|example)\b',
    re.IGNORECASE,
)


def _validate_reasoning(reasoning: str | None) -> str | None:
    """Valide le champ reasoning avant persistance — rejette les placeholders et textes vides."""
    if not reasoning or not isinstance(reasoning, str):
        return None
    cleaned = reasoning.strip()
    if len(cleaned) < _REASONING_MIN_LEN:
        return None
    if _REASONING_PLACEHOLDER.search(cleaned):
        return None
    return cleaned


def _call_llm(prompt: str, llm=None) -> dict | None:
    def _invoke():
        from langchain_core.messages import SystemMessage, HumanMessage
        _llm = llm
        if _llm is None:
            from mcp_client.llm_factory import LLMFactory
            _llm, _model, _backend = LLMFactory().create()
            logger.info("[reco:LLM] Instance %s/%s (thread %s)", _backend, _model,
                        __import__('threading').current_thread().name)
        response = _llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        content = response.content if hasattr(response, 'content') else str(response)
        return _parse_json_response(content)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke)
            return future.result(timeout=_LLM_CALL_TIMEOUT)
    except concurrent.futures.TimeoutError:
        logger.warning("[reco:LLM] Timeout après %ds.", _LLM_CALL_TIMEOUT)
        return None
    except Exception as exc:
        logger.warning("[reco:LLM] Appel échoué : %s", exc)
        return None


def _parse_json_response(raw: str) -> dict | None:
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'(\{[\s\S]*\})',
    ]
    for pattern in patterns:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1).strip())
                if isinstance(parsed, dict) and 'title' in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, dict) and 'title' in parsed:
            return parsed
    except Exception:
        pass
    return None


# ── Traduction EN/AR de la recommandation générée (best-effort, un seul appel) ──
# La plateforme ARIA affiche l'UI en fr/en/ar (LanguageService Angular) mais le
# moteur de recommandations raisonne et génère toujours en français (cf. _SYSTEM_PROMPT
# ci-dessus) — un seul "cerveau" garantit une reasoning/priorité cohérente quelle que
# soit la langue lue. On traduit ensuite la surface textuelle (title/description/
# action/reasoning) en un seul appel bon marché, stockée dans la colonne `i18n`.
# Best-effort : en cas d'échec, la lecture retombe sur le français (voir routes/recommendations.py).
_TRANSLATE_TIMEOUT = 30  # secondes — traduction courte, doit rester rapide

_TRANSLATE_SYSTEM_PROMPT = """Tu es un traducteur technique pour une plateforme de gestion de bâtiment (BMS).
Traduis les champs JSON fournis (title, description, action, reasoning) du français vers l'anglais ET l'arabe.

RÈGLES ABSOLUES :
- Conserve EXACTEMENT tous les nombres, unités (kWh, m³, TND, %) et noms de devices — ne les traduis jamais, ne les recalcule jamais
- Conserve le ton et le niveau de détail de chaque champ (ne résume pas, ne développe pas)
- Si "reasoning" est null ou absent, renvoie null pour reasoning dans les deux langues
- JSON valide uniquement, rien avant ni après, exactement cette forme :

{
  "en": {"title": "...", "description": "...", "action": "...", "reasoning": "..." | null},
  "ar": {"title": "...", "description": "...", "action": "...", "reasoning": "..." | null}
}"""


def _parse_translation_response(raw: str) -> dict | None:
    """Extrait {"en": {...}, "ar": {...}} de la réponse LLM. None si structure invalide."""
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'(\{[\s\S]*\})',
    ]
    parsed = None
    for pattern in patterns:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                candidate = json.loads(m.group(1).strip())
                if isinstance(candidate, dict) and 'en' in candidate and 'ar' in candidate:
                    parsed = candidate
                    break
            except json.JSONDecodeError:
                continue
    if parsed is None:
        try:
            candidate = json.loads(raw.strip())
            if isinstance(candidate, dict) and 'en' in candidate and 'ar' in candidate:
                parsed = candidate
        except Exception:
            return None
    if parsed is None:
        return None

    result = {}
    for lang in ('en', 'ar'):
        fields = parsed.get(lang)
        if not isinstance(fields, dict):
            continue
        if not fields.get('title') or not fields.get('description') or not fields.get('action'):
            continue  # traduction incomplète — inutilisable, on la rejette pour ce lang
        result[lang] = {
            'title'      : str(fields['title']).strip(),
            'description': str(fields['description']).strip(),
            'action'     : str(fields['action']).strip(),
            'reasoning'  : (str(fields['reasoning']).strip() if fields.get('reasoning') else None),
        }
    return result or None


def _translate_recommendation(fr_fields: dict, llm=None) -> dict | None:
    """Traduit title/description/action/reasoning FR -> EN/AR en un seul appel LLM.

    Best-effort : ne bloque jamais la génération de la recommandation. En cas
    d'échec/timeout, retourne None — la lecture (routes/recommendations.py) retombe
    alors sur le contenu français canonique, sans jamais mélanger les langues."""
    payload = json.dumps({
        'title'      : fr_fields.get('title'),
        'description': fr_fields.get('description'),
        'action'     : fr_fields.get('action'),
        'reasoning'  : fr_fields.get('reasoning'),
    }, ensure_ascii=False)

    def _invoke():
        from langchain_core.messages import SystemMessage, HumanMessage
        _llm = llm
        if _llm is None:
            from mcp_client.llm_factory import LLMFactory
            _llm, _model, _backend = LLMFactory().create()
        response = _llm.invoke([
            SystemMessage(content=_TRANSLATE_SYSTEM_PROMPT),
            HumanMessage(content=payload),
        ])
        content = response.content if hasattr(response, 'content') else str(response)
        return _parse_translation_response(content)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke)
            return future.result(timeout=_TRANSLATE_TIMEOUT)
    except concurrent.futures.TimeoutError:
        logger.warning("[reco:translate] Timeout après %ds — contenu servi en français uniquement.", _TRANSLATE_TIMEOUT)
        return None
    except Exception as exc:
        logger.warning("[reco:translate] Échec traduction (contenu servi en français) : %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 9. FALLBACK RÈGLES
# ══════════════════════════════════════════════════════════════════════════════

_FALLBACK_TEXTS: dict[str, dict] = {
    'OVERCONSUMPTION': {
        'title_tpl'  : "Surconsommation {label} — {device_id}",
        'desc_tpl'   : "Consommation {actual_26h} {unit} sur 26h (+{deviation_pct}% vs baseline {baseline_p50_sum} {unit}). Pics : {peak_hours_str}.",
        'action'     : "Identifier les équipements actifs lors du pic. Vérifier les consignes de régulation.",
        'priority_fn': lambda s: 'critical' if s.get('deviation_pct', 0) > 100 else 'high' if s.get('deviation_pct', 0) > 50 else 'medium',
    },
    'OPTIMIZATION': {
        'title_tpl'  : "Optimisation nocturne — {device_id}",
        'desc_tpl'   : "Excès de {off_peak_excess} {unit} en heures creuses ({off_peak_hours}). Économie mensuelle estimée : {estimated_saving_tnd} TND.",
        'action'     : "Programmer des arrêts automatiques via le GTB pendant les heures creuses.",
        'priority_fn': lambda s: 'medium',
    },
    'BUDGET_ALERT': {
        'title_tpl'  : "Dépassement budgétaire {label}",
        'desc_tpl'   : "Projection fin de mois : {projected_total} {unit} (+{overage_pct}% vs {last_month_total} {unit} le mois précédent).",
        'action'     : "Activer les mesures d'économie sur les équipements non critiques.",
        'priority_fn': lambda s: 'critical' if s.get('overage_pct', 0) > 30 else 'high' if s.get('overage_pct', 0) > 15 else 'medium',
    },
    'MAINTENANCE': {
        'title_tpl'  : "Signal de dégradation — {device_id}",
        'desc_tpl'   : "Consommation en hausse continue 7 jours (+{trend_growth_pct}%). Valeur actuelle : {day7_value} {unit}/j vs {day1_value} {unit}/j.",
        'action'     : "Programmer une inspection préventive de l'équipement.",
        'priority_fn': lambda s: 'high' if s.get('trend_growth_pct', 0) > 40 else 'medium',
    },
    'LEAK_RISK': {
        'title_tpl'  : "Risque de fuite {label} — {device_id}",
        'desc_tpl'   : "Consommation anormale entre {hours_range} ({nocturnal_excess} {unit} au-dessus baseline). Coût mensuel : {estimated_saving_tnd} TND.",
        'action'     : "Inspecter le réseau de nuit. Tester l'étanchéité sur le circuit concerné.",
        'priority_fn': lambda s: 'critical',
    },
    'EFFICIENCY': {
        'title_tpl'  : "Efficacité carburant dégradée — {device_id}",
        'desc_tpl'   : "Véhicule {device_id} : {vehicle_conso_7d} {unit}/7j (+{over_pct}% vs flotte {fleet_mean_7d} {unit}).",
        'action'     : "Vérifier pression pneus, filtre à air. Programmer un entretien préventif.",
        'priority_fn': lambda s: 'high' if s.get('over_pct', 0) > 60 else 'medium',
    },
}

# Traductions statiques des gabarits de secours (pas d'appel LLM — le fallback existe
# précisément pour le cas où le LLM est indisponible, donc sa traduction doit l'être aussi).
_FALLBACK_TEXTS_EN: dict[str, dict] = {
    'OVERCONSUMPTION': {
        'title_tpl': "Overconsumption {label} — {device_id}",
        'desc_tpl' : "Consumption {actual_26h} {unit} over 26h (+{deviation_pct}% vs baseline {baseline_p50_sum} {unit}). Peaks: {peak_hours_str}.",
        'action'   : "Identify equipment active during the peak. Check regulation setpoints.",
    },
    'OPTIMIZATION': {
        'title_tpl': "Off-peak optimization — {device_id}",
        'desc_tpl' : "Excess of {off_peak_excess} {unit} during off-peak hours ({off_peak_hours}). Estimated monthly saving: {estimated_saving_tnd} TND.",
        'action'   : "Schedule automatic shutdowns via the BMS during off-peak hours.",
    },
    'BUDGET_ALERT': {
        'title_tpl': "Budget overrun {label}",
        'desc_tpl' : "End-of-month projection: {projected_total} {unit} (+{overage_pct}% vs {last_month_total} {unit} last month).",
        'action'   : "Activate saving measures on non-critical equipment.",
    },
    'MAINTENANCE': {
        'title_tpl': "Degradation signal — {device_id}",
        'desc_tpl' : "Consumption rising continuously over 7 days (+{trend_growth_pct}%). Current value: {day7_value} {unit}/day vs {day1_value} {unit}/day.",
        'action'   : "Schedule a preventive inspection of the equipment.",
    },
    'LEAK_RISK': {
        'title_tpl': "Leak risk {label} — {device_id}",
        'desc_tpl' : "Abnormal consumption between {hours_range} ({nocturnal_excess} {unit} above baseline). Monthly cost: {estimated_saving_tnd} TND.",
        'action'   : "Inspect the network at night. Test the circuit for leaks.",
    },
    'EFFICIENCY': {
        'title_tpl': "Degraded fuel efficiency — {device_id}",
        'desc_tpl' : "Vehicle {device_id}: {vehicle_conso_7d} {unit}/7d (+{over_pct}% vs fleet {fleet_mean_7d} {unit}).",
        'action'   : "Check tire pressure and air filter. Schedule preventive maintenance.",
    },
}

_FALLBACK_TEXTS_AR: dict[str, dict] = {
    'OVERCONSUMPTION': {
        'title_tpl': "استهلاك مفرط {label} — {device_id}",
        'desc_tpl' : "استهلاك {actual_26h} {unit} خلال 26 ساعة (+{deviation_pct}% مقارنة بالمرجع {baseline_p50_sum} {unit}). الذروات: {peak_hours_str}.",
        'action'   : "حدد المعدات النشطة أثناء الذروة. تحقق من إعدادات التحكم.",
    },
    'OPTIMIZATION': {
        'title_tpl': "تحسين خارج ساعات الذروة — {device_id}",
        'desc_tpl' : "فائض {off_peak_excess} {unit} خلال ساعات الانخفاض ({off_peak_hours}). التوفير الشهري المقدر: {estimated_saving_tnd} دينار.",
        'action'   : "برمج إيقافات تلقائية عبر نظام إدارة المبنى خلال ساعات الانخفاض.",
    },
    'BUDGET_ALERT': {
        'title_tpl': "تجاوز الميزانية {label}",
        'desc_tpl' : "توقع نهاية الشهر: {projected_total} {unit} (+{overage_pct}% مقارنة بـ {last_month_total} {unit} الشهر الماضي).",
        'action'   : "فعّل إجراءات التوفير على المعدات غير الحرجة.",
    },
    'MAINTENANCE': {
        'title_tpl': "إشارة تدهور — {device_id}",
        'desc_tpl' : "ارتفاع مستمر في الاستهلاك على مدى 7 أيام (+{trend_growth_pct}%). القيمة الحالية: {day7_value} {unit}/يوم مقابل {day1_value} {unit}/يوم.",
        'action'   : "برمج فحصاً وقائياً للمعدة.",
    },
    'LEAK_RISK': {
        'title_tpl': "خطر تسرب {label} — {device_id}",
        'desc_tpl' : "استهلاك غير طبيعي بين {hours_range} ({nocturnal_excess} {unit} فوق المرجع). التكلفة الشهرية: {estimated_saving_tnd} دينار.",
        'action'   : "افحص الشبكة ليلاً. اختبر شبكة الأنابيب بحثاً عن تسربات.",
    },
    'EFFICIENCY': {
        'title_tpl': "كفاءة وقود متدهورة — {device_id}",
        'desc_tpl' : "المركبة {device_id}: {vehicle_conso_7d} {unit}/7أيام (+{over_pct}% مقارنة بالأسطول {fleet_mean_7d} {unit}).",
        'action'   : "تحقق من ضغط الإطارات وفلتر الهواء. برمج صيانة وقائية.",
    },
}

_FALLBACK_NO_DATA_I18N = {
    'en': {
        'title_tpl': "Anomaly {label} detected — {dev}",
        'desc_tpl' : (
            "The Chronos model identified {count} abnormal point(s) "
            "with an anomaly score of {score:.2f}/1.0. "
            "Historical consumption data is insufficient to quantify the deviation — "
            "a preventive inspection is recommended."
        ),
    },
    'ar': {
        'title_tpl': "تم اكتشاف شذوذ {label} — {dev}",
        'desc_tpl' : (
            "حدد نموذج Chronos {count} نقطة (نقاط) غير طبيعية "
            "بدرجة شذوذ {score:.2f}/1.0. "
            "بيانات الاستهلاك التاريخية غير كافية لتحديد حجم الانحراف — "
            "يُنصح بإجراء فحص وقائي."
        ),
    },
}


def _build_fallback_i18n(signal: dict, domain: str, fb_action_fr: str) -> dict | None:
    """Construit les traductions en/ar du fallback règles — statiques, sans appel LLM.

    Le fallback existe pour le cas où le LLM est indisponible ; sa traduction ne
    peut donc pas dépendre du LLM non plus. `action` reste identique aux 3 langues
    quand la traduction n'est pas listée (verbe/consigne courte, moindre impact UX)."""
    rec_type = signal['rec_type']

    if signal.get('no_consumption_data'):
        score = signal.get('chronos_score', 0)
        count = signal.get('ad_anomaly_count', 0)
        dev   = signal.get('device_id', domain)
        label = signal.get('label', domain)
        out = {}
        for lang, tpl in _FALLBACK_NO_DATA_I18N.items():
            out[lang] = {
                'title'      : tpl['title_tpl'].format(label=label, dev=dev),
                'description': tpl['desc_tpl'].format(count=count, score=score),
                'action'     : fb_action_fr,
                'reasoning'  : None,
            }
        return out

    ctx = {**signal, 'peak_hours_str': ', '.join(f"{h}h" for h in signal.get('peak_hours', [])[:3])}
    out = {}
    for lang, table in (('en', _FALLBACK_TEXTS_EN), ('ar', _FALLBACK_TEXTS_AR)):
        fb = table.get(rec_type)
        if not fb:
            continue
        try:
            out[lang] = {
                'title'      : fb['title_tpl'].format(**ctx),
                'description': fb['desc_tpl'].format(**ctx),
                'action'     : fb['action'],
                'reasoning'  : None,
            }
        except Exception:
            continue
    return out or None


def _rule_based_fallback(signal: dict, domain: str) -> dict | None:
    rec_type = signal['rec_type']
    fb       = _FALLBACK_TEXTS.get(rec_type)
    if not fb:
        return None

    # Signals Chronos sans données de consommation : description générique sans chiffres inventés
    if signal.get('no_consumption_data'):
        score  = signal.get('chronos_score', 0)
        count  = signal.get('ad_anomaly_count', 0)
        dev    = signal.get('device_id', domain)
        label  = signal.get('label', domain)
        return {
            'priority'            : 'high' if score >= 0.75 else 'medium',
            'title'               : f"Anomalie {label} détectée — {dev}",
            'description'         : (
                f"Le modèle Chronos a identifié {count} point(s) anormal(aux) "
                f"avec un score d'anomalie de {score:.2f}/1.0. "
                f"Les données de consommation historiques sont insuffisantes pour quantifier l'écart — "
                f"une inspection préventive est recommandée."
            ),
            'action'              : fb['action'],
            'reasoning'           : None,
            'root_cause'          : None,
            'estimated_saving_tnd': None,
            'i18n'                : _build_fallback_i18n(signal, domain, fb['action']),
        }

    ctx = {**signal, 'peak_hours_str': ', '.join(f"{h}h" for h in signal.get('peak_hours', [])[:3])}
    try:
        return {
            'priority'            : fb['priority_fn'](signal),
            'title'               : fb['title_tpl'].format(**ctx),
            'description'         : fb['desc_tpl'].format(**ctx),
            'action'              : fb['action'],
            'reasoning'           : None,
            'root_cause'          : None,
            'estimated_saving_tnd': signal.get('estimated_saving_tnd'),
            'i18n'                : _build_fallback_i18n(signal, domain, fb['action']),
        }
    except Exception:
        return {
            'priority'            : 'medium',
            'title'               : f"{rec_type} — {signal.get('device_id', domain)}",
            'description'         : f"Anomalie détectée sur domaine {domain}.",
            'action'              : "Vérifier l'équipement concerné.",
            'reasoning'           : None,
            'root_cause'          : None,
            'estimated_saving_tnd': signal.get('estimated_saving_tnd'),
            'i18n'                : None,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 10. ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

_ALL_ROLES = ('technicien', 'gestionnaire', 'directeur')


def generate_all(engine) -> dict:
    """Génère des recommandations pour tous les domaines et les 3 rôles."""
    results = {}
    for domain in DOMAIN_CONFIG:
        total = 0
        for role in _ALL_ROLES:
            try:
                total += generate_domain(engine, domain, user_role=role)
            except Exception as exc:
                logger.error("[reco:%s/%s] Erreur : %s", domain, role, exc, exc_info=True)
        results[domain] = total
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
                    'estimated_saving_tnd': llm_result.get('estimated_saving_tnd') or signal.get('estimated_saving_tnd'),
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
                    'estimated_saving_tnd': fb.get('estimated_saving_tnd') or signal.get('estimated_saving_tnd'),
                    'deviation_pct'       : signal.get('deviation_pct'),
                }

            recos.append(rec)

    n = _insert_recommendations(engine, recos)
    logger.info(
        "[reco:%s] %d candidat(s) -> %d reco(s) | LLM: %d OK / %d fallback",
        domain, len(candidates), n, llm_ok, llm_fb,
    )
    return n


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


# ── Entrypoint scheduler ──────────────────────────────────────────────────────

def run_recommendation_cycle(engine) -> dict:
    logger.info("[reco] Cycle IA démarré (contexte riche + CoT + feedback loop)…")
    baselines = compute_baselines(engine)
    generated = generate_all(engine)
    roi_count = measure_roi(engine)
    result    = {'baselines': baselines, 'generated': generated, 'roi_evaluated': roi_count}
    logger.info("[reco] Cycle terminé : %s", result)
    return result
