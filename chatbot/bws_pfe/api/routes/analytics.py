"""
Endpoints REST pour les données agrégées et les résultats AD.
Utilisés par le dashboard Angular pour tous les domaines IoT.
"""
from __future__ import annotations

import json
import logging
from datetime import date as Date, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy import text

from api.db import get_engine

logger = logging.getLogger('aria.api.analytics')

router = APIRouter(prefix='/analytics', tags=['analytics'])


def _engine():
    e = get_engine()
    if not e:
        raise HTTPException(503, 'Base de données non disponible')
    return e


# Expression SQL qui normalise item_id vers l'identifiant device de base.
# Pour l'énergie, item_id = "{device}_L1/L2/L3" → "{device}".
# Pour tous les autres domaines, item_id reste inchangé.
# Utilisée dans /anomalies et /kpis pour garantir la cohérence du comptage.
_DEVICE_EXPR = (
    "CASE WHEN domain = 'energy' "
    "          AND RIGHT(item_id, 3) REGEXP '^_L[0-9]$' "
    "     THEN LEFT(item_id, CHAR_LENGTH(item_id) - 3) "
    "     ELSE item_id "
    "END"
)


# ─── Données agrégées ──────────────────────────────────────────────────────────

@router.get('/energy')
async def get_energy(
    date:      Optional[str] = Query(None, description='YYYY-MM-DD (défaut: hier)'),
    device_id: Optional[str] = Query(None),
    days:      int            = Query(1, ge=1, le=365),
):
    """Données énergie horaires. days > 1 pour historique."""
    end_dt   = Date.fromisoformat(date) if date else Date.today() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=days - 1)

    params: dict = {'start': str(start_dt), 'end': str(end_dt)}
    extra = ''
    if device_id:
        params['device_id'] = device_id
        extra = 'AND device_id = :device_id'

    with _engine().connect() as conn:
        rows = conn.execute(text(f"""
            SELECT device_id, phase, date, hour, cons_en, nb_mesures
            FROM daily_energy
            WHERE date BETWEEN :start AND :end {extra}
            ORDER BY device_id, phase, date, hour
            LIMIT 10000
        """), params).mappings().fetchall()

    return {'domain': 'energy', 'start': str(start_dt), 'end': str(end_dt),
            'count': len(rows), 'data': [dict(r) for r in rows]}


@router.get('/water')
async def get_water(
    date:      Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    days:      int            = Query(1, ge=1, le=365),
):
    """Données eau horaires avec fuites/fraudes."""
    end_dt   = Date.fromisoformat(date) if date else Date.today() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=days - 1)

    params: dict = {'start': str(start_dt), 'end': str(end_dt)}
    extra = ''
    if device_id:
        params['device_id'] = device_id
        extra = 'AND device_id = :device_id'

    with _engine().connect() as conn:
        rows = conn.execute(text(f"""
            SELECT device_id, date, hour, conso_m3, nb_fuites, nb_fraudes, is_offline, nb_mesures
            FROM daily_water
            WHERE date BETWEEN :start AND :end {extra}
            ORDER BY device_id, date, hour
            LIMIT 10000
        """), params).mappings().fetchall()

    return {'domain': 'water', 'start': str(start_dt), 'end': str(end_dt),
            'count': len(rows), 'data': [dict(r) for r in rows]}


@router.get('/gas')
async def get_gas(
    date:      Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    days:      int            = Query(1, ge=1, le=365),
):
    """Données gaz horaires avec débit et fuites."""
    end_dt   = Date.fromisoformat(date) if date else Date.today() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=days - 1)

    params: dict = {'start': str(start_dt), 'end': str(end_dt)}
    extra = ''
    if device_id:
        params['device_id'] = device_id
        extra = 'AND device_id = :device_id'

    with _engine().connect() as conn:
        rows = conn.execute(text(f"""
            SELECT device_id, date, hour, conso_m3, avg_debit, nb_fuites, nb_fraudes, nb_mesures
            FROM daily_gas
            WHERE date BETWEEN :start AND :end {extra}
            ORDER BY device_id, date, hour
            LIMIT 10000
        """), params).mappings().fetchall()

    return {'domain': 'gas', 'start': str(start_dt), 'end': str(end_dt),
            'count': len(rows), 'data': [dict(r) for r in rows]}


@router.get('/fuel')
async def get_fuel(
    date:      Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    days:      int            = Query(1, ge=1, le=365),
):
    """Données carburant horaires avec niveau et consommation."""
    end_dt   = Date.fromisoformat(date) if date else Date.today() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=days - 1)

    params: dict = {'start': str(start_dt), 'end': str(end_dt)}
    extra = ''
    if device_id:
        params['device_id'] = device_id
        extra = 'AND device_id = :device_id'

    with _engine().connect() as conn:
        rows = conn.execute(text(f"""
            SELECT device_id, date, hour, fuel_level, consumption, avg_speed, nb_mesures
            FROM daily_fuel
            WHERE date BETWEEN :start AND :end {extra}
            ORDER BY device_id, date, hour
            LIMIT 10000
        """), params).mappings().fetchall()

    return {'domain': 'fuel', 'start': str(start_dt), 'end': str(end_dt),
            'count': len(rows), 'data': [dict(r) for r in rows]}


# ─── KPIs journaliers ─────────────────────────────────────────────────────────

@router.get('/kpis')
async def get_kpis(
    days: int           = Query(7,   ge=1, le=90,  description='Fenêtre pour le comptage des anomalies AD'),
    date: Optional[str] = Query(None, description='YYYY-MM-DD (défaut: hier)'),
):
    """Totaux journaliers par domaine pour les KPI cards du dashboard."""
    kpi_date  = date or str(Date.today() - timedelta(days=1))
    end_dt    = Date.fromisoformat(kpi_date)
    start_dt  = end_dt - timedelta(days=days - 1)
    engine    = _engine()

    with engine.connect() as conn:
        energy = conn.execute(text("""
            SELECT device_id, phase,
                   SUM(cons_en)    AS total_kWh,
                   SUM(nb_mesures) AS nb_mesures
            FROM daily_energy WHERE date = :d
            GROUP BY device_id, phase
        """), {'d': kpi_date}).mappings().fetchall()

        water = conn.execute(text("""
            SELECT device_id,
                   SUM(conso_m3)   AS total_m3,
                   SUM(nb_fuites)  AS fuites,
                   SUM(nb_fraudes) AS fraudes,
                   SUM(nb_mesures) AS nb_mesures
            FROM daily_water WHERE date = :d
            GROUP BY device_id
        """), {'d': kpi_date}).mappings().fetchall()

        gas = conn.execute(text("""
            SELECT device_id,
                   SUM(conso_m3)   AS total_m3,
                   AVG(avg_debit)  AS avg_debit,
                   SUM(nb_fuites)  AS fuites,
                   SUM(nb_fraudes) AS fraudes,
                   SUM(nb_mesures) AS nb_mesures
            FROM daily_gas WHERE date = :d
            GROUP BY device_id
        """), {'d': kpi_date}).mappings().fetchall()

        fuel = conn.execute(text("""
            SELECT device_id,
                   SUM(consumption) AS total_L,
                   AVG(fuel_level)  AS avg_level,
                   AVG(avg_speed)   AS avg_speed,
                   SUM(nb_mesures)  AS nb_mesures
            FROM daily_fuel WHERE date = :d
            GROUP BY device_id
        """), {'d': kpi_date}).mappings().fetchall()

        # Comptage dédupliqué (1 device = 1 anomalie/jour) — cohérent avec GET /anomalies.
        anomalies = conn.execute(text(f"""
            SELECT domain, COUNT(*) AS nb
            FROM (
                SELECT domain
                FROM ad_results
                WHERE is_anomaly = 1
                  AND DATE(data_ts) BETWEEN :start AND :end
                GROUP BY domain, ({_DEVICE_EXPR}), DATE(data_ts)
            ) AS _dedup
            GROUP BY domain
        """), {'start': str(start_dt), 'end': str(end_dt)}).mappings().fetchall()

    return {
        'date':      kpi_date,
        'energy':    [dict(r) for r in energy],
        'water':     [dict(r) for r in water],
        'gas':       [dict(r) for r in gas],
        'fuel':      [dict(r) for r in fuel],
        'anomalies': {r['domain']: r['nb'] for r in anomalies},
    }


# ─── Anomalies AD ─────────────────────────────────────────────────────────────

@router.get('/anomalies')
async def get_anomalies(
    domain:    Optional[str] = Query(None, description='energy | water | gas | fuel'),
    date:      Optional[str] = Query(None),
    days:      int            = Query(30,  ge=1, le=365),
    only_true: bool           = Query(True, description='Seulement is_anomaly=1'),
    page:      int            = Query(0,   ge=0),
    size:      int            = Query(200, ge=1, le=1000),
):
    """Résultats de détection d'anomalies, dédupliqués par device + jour.

    Pour l'énergie, les 3 phases (item_id = "{device}_L1/L2/L3") sont fusionnées
    en une seule ligne par device : on conserve le score d'anomalie le plus élevé,
    les stratégies distinctes (ex: "HotStart+ColdStart"), et les bornes les plus larges.
    Cette déduplication s'applique à tous les domaines : si un device a plusieurs
    entrées sur le même jour, une seule ligne est retournée (le pire cas).
    """
    if date:
        end_dt = Date.fromisoformat(date)
    else:
        with _engine().connect() as conn:
            max_ts = conn.execute(text('SELECT MAX(DATE(data_ts)) FROM ad_results')).scalar()
        end_dt = Date.fromisoformat(str(max_ts)) if max_ts else Date.today()
    start_dt = end_dt - timedelta(days=days - 1)

    params: dict  = {'start': str(start_dt), 'end': str(end_dt)}
    where_parts   = ['DATE(data_ts) BETWEEN :start AND :end']

    if domain:
        params['domain'] = domain
        where_parts.append('domain = :domain')
    if only_true:
        where_parts.append('is_anomaly = 1')

    where = ' AND '.join(where_parts)

    with _engine().connect() as conn:
        # COUNT sur les groupes dédupliqués pour la pagination correcte
        total = conn.execute(text(f"""
            SELECT COUNT(*) FROM (
                SELECT 1 FROM ad_results
                WHERE {where}
                GROUP BY domain, ({_DEVICE_EXPR}), DATE(data_ts)
            ) AS _dedup
        """), params).scalar()

        rows = conn.execute(text(f"""
            SELECT
                domain,
                ({_DEVICE_EXPR})                                              AS item_id,
                GROUP_CONCAT(DISTINCT strategy ORDER BY strategy SEPARATOR '+') AS strategy,
                MAX(is_anomaly)                                               AS is_anomaly,
                MAX(anomaly_score)                                            AS anomaly_score,
                MAX(data_ts)                                                  AS data_ts,
                MAX(value)                                                    AS value,
                MIN(q10)                                                      AS q10,
                MAX(q90)                                                      AS q90,
                MAX(run_at)                                                   AS run_at
            FROM ad_results
            WHERE {where}
            GROUP BY domain, ({_DEVICE_EXPR}), DATE(data_ts)
            ORDER BY MAX(anomaly_score) DESC, MAX(data_ts) DESC
            LIMIT :size OFFSET :offset
        """), {**params, 'size': size, 'offset': page * size}).mappings().fetchall()

    return {
        'start':      str(start_dt),
        'end':        str(end_dt),
        'domain':     domain,
        'total':      int(total),
        'page':       page,
        'size':       size,
        'pages':      -(-int(total) // size),
        'count':      len(rows),
        'anomalies':  [dict(r) for r in rows],
    }


# ─── Prédictions préventives ──────────────────────────────────────────────────

@router.get('/predictions')
async def get_predictions(
    domain:       Optional[str] = Query(None,  description='energy | water | gas | fuel'),
    hours:        int            = Query(48,    ge=1, le=87600, description='Fenêtre temporelle en heures'),
    only_alert:   bool           = Query(True,  description='Seulement is_alert=1'),
    severity:     Optional[str]  = Query(None,  description='HIGH | MEDIUM | LOW'),
    include_past: bool           = Query(False, description='Inclure les prédictions passées (utile en dev/test)'),
    page:         int            = Query(0,     ge=0),
    size:         int            = Query(200,   ge=1, le=1000),
):
    """
    Prédictions préventives ARIA pour les prochaines *hours* heures.
    Par défaut : prédictions futures uniquement (forecast_ts >= NOW()).
    Avec include_past=true : toutes les prédictions du dernier run, utile pour les tests sur données historiques.
    """
    params: dict = {'hours': hours}
    where_parts: list[str] = []

    if not include_past:
        where_parts.append('forecast_ts >= NOW()')
        where_parts.append('forecast_ts <= DATE_ADD(NOW(), INTERVAL :hours HOUR)')
    else:
        where_parts.append('run_at >= (SELECT MAX(run_at) - INTERVAL 2 HOUR FROM aria_predictions)')

    if domain:
        params['domain'] = domain
        where_parts.append('domain = :domain')
    if only_alert:
        where_parts.append('is_alert = 1')
    if severity:
        params['severity'] = severity.upper()
        where_parts.append('alert_severity = :severity')

    where = ' AND '.join(where_parts) if where_parts else '1=1'

    with _engine().connect() as conn:
        total = conn.execute(text(f'SELECT COUNT(*) FROM aria_predictions WHERE {where}'), params).scalar()
        rows  = conn.execute(text(f"""
            SELECT domain, item_id, forecast_ts, horizon_hours, forecast_col,
                   forecast_median, forecast_low, forecast_high,
                   confidence, is_alert, alert_severity, run_at
            FROM aria_predictions
            WHERE {where}
            ORDER BY FIELD(alert_severity, 'HIGH', 'MEDIUM', 'LOW'), forecast_ts ASC
            LIMIT :size OFFSET :offset
        """), {**params, 'size': size, 'offset': page * size}).mappings().fetchall()

    return {
        'horizon_hours': hours,
        'domain':        domain,
        'total':         total,
        'page':          page,
        'size':          size,
        'pages':         -(-int(total) // size),
        'count':         len(rows),
        'predictions':   [dict(r) for r in rows],
    }


# ─── Contrôle du pipeline ─────────────────────────────────────────────────────

@router.post('/run')
async def trigger_run(
    background_tasks: BackgroundTasks,
    run_date:   Optional[str] = Query(None,  description='YYYY-MM-DD cible (défaut: hier)'),
    hours_back: int            = Query(96,    ge=1, le=87600, description='Fenêtre extraction (h)'),
):
    """
    Déclenche le pipeline manuellement. Retourne immédiatement.
    Exemples : /analytics/run?hours_back=8760  (1 an, pour tester avec données historiques)
               /analytics/run?run_date=2025-06-01&hours_back=720
    """
    engine = _engine()
    rd = Date.fromisoformat(run_date) if run_date else None
    background_tasks.add_task(_run_background, engine, rd, hours_back)
    return {'message': 'Pipeline lancé en arrière-plan', 'check': '/analytics/status'}


async def _run_background(engine, run_date, hours_back: int) -> None:
    try:
        from api.pipeline.scheduler import run_now
        result = await run_now(engine, run_date=run_date, hours_back=hours_back)
        logger.info("Run manuel terminé : %s", result.get('status'))
    except Exception as exc:
        logger.error("Run manuel échoué : %s", exc, exc_info=True)


@router.get('/status')
async def get_status():
    """Derniers runs du pipeline avec leur statut et résumé par domaine."""
    with _engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT id, started_at, ended_at, status, summary
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT 10
        """)).mappings().fetchall()

    result = []
    for r in rows:
        row = dict(r)
        if isinstance(row.get('summary'), str):
            try:
                row['summary'] = json.loads(row['summary'])
            except Exception:
                pass
        result.append(row)

    return {'runs': result}


# ─── Replay données historiques ───────────────────────────────────────────────

@router.post('/replay')
async def trigger_replay(
    background_tasks: BackgroundTasks,
    domain: Optional[str] = Query(None, description='energy | water | gas | fuel (défaut: tous)'),
    days:   int            = Query(1,    ge=1, le=365, description='Rejouer les N derniers jours'),
):
    """
    Rejoue les données historiques en les réinsérant avec les dates récentes.
    Utile quand les tables archive_*_j n'ont plus de données nouvelles.
    Le job automatique tourne à 01h00 UTC; cet endpoint le déclenche manuellement.
    """
    engine  = _engine()
    domains = [domain] if domain else None
    background_tasks.add_task(_replay_background, engine, domains, days)
    return {
        'message': f'Replay lancé en arrière-plan pour {days} jour(s)',
        'domains': domains or 'tous',
        'check':   '/analytics/status',
    }


async def _replay_background(engine, domains, days: int) -> None:
    try:
        from datetime import date, timedelta
        from api.pipeline.data_replay import run_replay
        today  = date.today()
        dates  = [today - timedelta(days=i) for i in range(days)]
        result = run_replay(engine, target_dates=dates, domains=domains)
        logger.info("Replay manuel terminé : %s", result)
    except Exception as exc:
        logger.error("Replay manuel échoué : %s", exc, exc_info=True)


# ─── Backfill historique ───────────────────────────────────────────────────────

@router.post('/backfill')
async def backfill():
    """
    Migration one-shot : remplit daily_* depuis les tables archive_*_h/_j.
    Idempotent (ON DUPLICATE KEY UPDATE). Retourne le nombre de lignes par domaine.
    """
    engine = _engine()
    results = {}

    sqls: dict[str, list[str]] = {

        'water': ["""
            INSERT INTO daily_water (device_id, date, hour, conso_m3, nb_mesures)
            SELECT
                id_device,
                DATE(`date`)  AS date,
                HOUR(`date`)  AS hour,
                ROUND(SUM(conso) / 1000, 4) AS conso_m3,
                COUNT(*)      AS nb_mesures
            FROM archive_wm_h
            GROUP BY id_device, DATE(`date`), HOUR(`date`)
            ON DUPLICATE KEY UPDATE
                conso_m3   = VALUES(conso_m3),
                nb_mesures = VALUES(nb_mesures)
        """],

        'gas': ["""
            INSERT INTO daily_gas (device_id, date, hour, conso_m3, avg_debit, nb_mesures)
            SELECT
                id_device,
                DATE(`date`)              AS date,
                HOUR(`date`)              AS hour,
                ROUND(SUM(conso), 4)      AS conso_m3,
                ROUND(AVG(avg_debit_per_min), 4) AS avg_debit,
                COUNT(*)                  AS nb_mesures
            FROM archive_gm_h
            GROUP BY id_device, DATE(`date`), HOUR(`date`)
            ON DUPLICATE KEY UPDATE
                conso_m3   = VALUES(conso_m3),
                avg_debit  = VALUES(avg_debit),
                nb_mesures = VALUES(nb_mesures)
        """],

        'fuel': ["""
            INSERT INTO daily_fuel (device_id, date, hour, consumption, avg_speed, nb_mesures)
            SELECT
                id_device,
                DATE(`date`)                  AS date,
                HOUR(`date`)                  AS hour,
                ROUND(SUM(consommation), 4)   AS consumption,
                ROUND(AVG(vitesse), 4)        AS avg_speed,
                COUNT(*)                      AS nb_mesures
            FROM archive_fuel_h
            GROUP BY id_device, DATE(`date`), HOUR(`date`)
            ON DUPLICATE KEY UPDATE
                consumption = VALUES(consumption),
                avg_speed   = VALUES(avg_speed),
                nb_mesures  = VALUES(nb_mesures)
        """],

        'energy': [
            # L1
            """
            INSERT INTO daily_energy (device_id, phase, date, hour, cons_en, nb_mesures)
            SELECT id_device, 'L1', `date`, 0,
                   ROUND(cons_en_l1, 4), 1
            FROM archive_en_p_j
            WHERE cons_en_l1 IS NOT NULL
            ON DUPLICATE KEY UPDATE
                cons_en    = VALUES(cons_en),
                nb_mesures = VALUES(nb_mesures)
            """,
            # L2
            """
            INSERT INTO daily_energy (device_id, phase, date, hour, cons_en, nb_mesures)
            SELECT id_device, 'L2', `date`, 0,
                   ROUND(cons_en_l2, 4), 1
            FROM archive_en_p_j
            WHERE cons_en_l2 IS NOT NULL
            ON DUPLICATE KEY UPDATE
                cons_en    = VALUES(cons_en),
                nb_mesures = VALUES(nb_mesures)
            """,
            # L3
            """
            INSERT INTO daily_energy (device_id, phase, date, hour, cons_en, nb_mesures)
            SELECT id_device, 'L3', `date`, 0,
                   ROUND(cons_en_l3, 4), 1
            FROM archive_en_p_j
            WHERE cons_en_l3 IS NOT NULL
            ON DUPLICATE KEY UPDATE
                cons_en    = VALUES(cons_en),
                nb_mesures = VALUES(nb_mesures)
            """,
        ],
    }

    with engine.begin() as conn:
        for domain, queries in sqls.items():
            total = 0
            try:
                for q in queries:
                    r = conn.execute(text(q))
                    total += r.rowcount
                results[domain] = {'status': 'ok', 'rows_affected': total}
                logger.info("backfill %s: %d lignes", domain, total)
            except Exception as exc:
                logger.error("backfill %s: %s", domain, exc, exc_info=True)
                results[domain] = {'status': 'error', 'error': str(exc)}

    overall = 'success' if all(v['status'] == 'ok' for v in results.values()) else 'partial'
    return {'status': overall, 'results': results}
