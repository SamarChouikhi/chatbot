import time
import logging

from mcp_server.db.connection import execute_sql, get_all_tables, get_active_tables
from mcp_server.tools._helpers import (
    ok, err, detect_date_col, detect_thl_cols,
    get_active_col_names, SENSOR_TABLE_PRIORITY,
    validate_period, sanitize_rows,
)
from mcp_server.device_resolver import build_realtime_query, build_aggregated_query

logger = logging.getLogger('aria.tools.sensors')


def _get_best_table(sensor_type: str, prefer_realtime: bool = False) -> str | None:
    """Retourne la meilleure table disponible pour un type de capteur.

    Par défaut, préfère les archives (données complètes). prefer_realtime=True pour les données live.
    """
    active   = get_active_tables()
    priority = list(SENSOR_TABLE_PRIORITY.get(sensor_type, []))
    if prefer_realtime:
        priority = list(reversed(priority))
    for t in priority:
        if t in active:
            return t
    return next((t for t in active if sensor_type in t.lower()), None)


def realtime_data(sensor_type: str = 'all') -> str:
    """Retourne les dernières mesures de tous les capteurs (ou d'un type spécifique)."""
    start = time.time()
    tool  = 'realtime_data'
    logger.info(f'[{tool}] sensor_type={sensor_type}')
    try:
        active    = get_active_tables()
        all_tbls  = get_all_tables()
        rt_tables = [t for t in all_tbls if t.startswith('rt_') and t in active]

        if sensor_type != 'all':
            target = [t for t in rt_tables if sensor_type in t.lower()]
            if target:
                rt_tables = target

        if not rt_tables:
            return err(tool, 'Aucune donnée temps réel disponible', 'Vérifiez la connexion des capteurs')

        # Colonnes utiles par type de capteur — évite de retourner des champs internes au LLM
        USEFUL_COLS = {
            'thl': ['t', 'h', 'l', 'battery_level', 'rssi'],
            'wm' : ['forward_flow', 'index', 'leak', 'fraud', 'battery_level', 'rssi'],
            'en' : ['rms_voltage_L1', 'cosfi_L1', 'THD_L1', 'active_power_L1', 'en_L1'],
            'gm' : ['index', 'avg_debit_per_min', 'leak', 'fraud', 'battery_level', 'rssi'],
            'sm' : ['t', 'h', 'v', 'p', 'uv'],
            'pir': ['count', 'traffic_percentage'],
            'ls' : ['status', 'battery_level', 'rssi'],
        }

        all_sensors = []
        for table in rt_tables:
            try:
                col_map     = get_active_col_names(table)
                cols_avail  = set(col_map.keys())
                ttype       = next((k for k in USEFUL_COLS if k in table), None)
                wanted      = USEFUL_COLS.get(ttype, []) if ttype else []

                sensor_cols = [col_map[c] for c in [w.lower() for w in wanted] if c in cols_avail]
                if not sensor_cols:
                    sensor_cols = [v for k, v in col_map.items()
                                   if k not in ('id_device', 'id', 'gateway', 'snr')][:6]

                date_col = detect_date_col(table)
                rows = execute_sql(build_realtime_query(table, sensor_cols, limit=50, date_col=date_col))
                all_sensors.extend(sanitize_rows(rows))
            except Exception as exc:
                logger.warning('[%s] table %s ignorée : %s', tool, table, exc)

        duration = round(time.time() - start, 3)
        if not all_sensors:
            return err(tool, 'Aucune donnée RT trouvée', 'Les capteurs sont peut-être hors ligne')

        summary = {
            'total_capteurs'   : len(all_sensors),
            'batterie_critique': sum(1 for s in all_sensors
                                     if isinstance(s.get('battery_level'), (int, float))
                                     and s['battery_level'] < 20),
            'signal_faible'    : sum(1 for s in all_sensors
                                     if isinstance(s.get('rssi'), (int, float))
                                     and s['rssi'] < -80),
            'fuites'  : sum(1 for s in all_sensors if s.get('leak') == 1),
            'fraudes' : sum(1 for s in all_sensors if s.get('fraud') == 1),
            'par_zone': _group_by_zone(all_sensors),
        }

        return ok({
            'sensor_type': sensor_type,
            'summary'    : summary,
            'capteurs'   : all_sensors,
            'count'      : len(all_sensors),
            'duration'   : duration,
        })

    except Exception as e:
        return err(tool, str(e))


def _group_by_zone(sensors: list[dict]) -> dict:
    zones: dict = {}
    for s in sensors:
        zone = s.get('zone', 'Zone inconnue')
        zones.setdefault(zone, 0)
        zones[zone] += 1
    return zones


def thl_analysis(period: str = '24h') -> str:
    """Analyse statistique des capteurs température/humidité/luminosité sur une période."""
    start = time.time()
    tool  = 'thl_analysis'
    logger.info(f'[{tool}] period={period}')
    try:
        interval, error = validate_period(tool, period)
        if error:
            return error

        table = _get_best_table('thl')
        if not table:
            return err(tool, 'Aucune table THL disponible')

        date_col = detect_date_col(table)
        thl_cols = detect_thl_cols(table)
        if not date_col or not thl_cols:
            return err(tool, f'Structure THL introuvable dans "{table}"')

        agg_cols = []
        if 't' in thl_cols:
            c = thl_cols['t']
            agg_cols += [f'ROUND(MIN(t.`{c}`),2) AS t_min',
                         f'ROUND(AVG(t.`{c}`),2) AS t_avg',
                         f'ROUND(MAX(t.`{c}`),2) AS t_max']
        if 'h' in thl_cols:
            c = thl_cols['h']
            agg_cols += [f'ROUND(MIN(t.`{c}`),2) AS h_min',
                         f'ROUND(AVG(t.`{c}`),2) AS h_avg',
                         f'ROUND(MAX(t.`{c}`),2) AS h_max']
        if 'l' in thl_cols:
            c = thl_cols['l']
            agg_cols += [f'ROUND(MIN(t.`{c}`),2) AS l_min',
                         f'ROUND(AVG(t.`{c}`),2) AS l_avg',
                         f'ROUND(MAX(t.`{c}`),2) AS l_max']
        agg_cols.append('COUNT(*) AS nb_mesures')

        rows     = sanitize_rows(execute_sql(build_aggregated_query(table, agg_cols, date_col, interval)))
        duration = round(time.time() - start, 3)

        if not rows or all(r.get('nb_mesures', 0) == 0 for r in rows):
            return err(tool, f'Aucune donnée THL pour "{period}"', 'Essayez thl_analysis("tout")')

        logger.info(f'[{tool}] {len(rows)} capteurs en {duration}s')
        return ok({'period': period, 'analysis': rows, 'duration': duration})

    except Exception as e:
        return err(tool, str(e))


def wm_analysis(period: str = '24h') -> str:
    """Analyse de la consommation et des anomalies eau sur une période."""
    start = time.time()
    tool  = 'wm_analysis'
    logger.info(f'[{tool}] period={period}')
    try:
        interval, error = validate_period(tool, period)
        if error:
            return error

        table = _get_best_table('wm')
        if not table:
            return err(tool, 'Aucune table WM disponible')

        date_col = detect_date_col(table)
        col_map  = get_active_col_names(table)
        cols     = set(col_map.keys())

        agg_cols = []
        if 'forward_flow'  in cols: agg_cols += ['ROUND(SUM(t.forward_flow),2) AS total_m3',
                                                   'ROUND(AVG(t.forward_flow),2) AS avg_debit']
        if 'index'         in cols: agg_cols += ['MIN(t.`index`) AS index_debut',
                                                   'MAX(t.`index`) AS index_fin']
        if 'leak'          in cols: agg_cols.append('SUM(t.leak)  AS nb_fuites')
        if 'fraud'         in cols: agg_cols.append('SUM(t.fraud) AS nb_fraudes')
        if 'tamp'          in cols: agg_cols.append('SUM(t.tamp)  AS nb_tampering')
        if 'battery_level' in cols: agg_cols.append('ROUND(AVG(t.battery_level),0) AS avg_batterie')
        agg_cols.append('COUNT(*) AS nb_mesures')

        rows     = sanitize_rows(execute_sql(build_aggregated_query(table, agg_cols, date_col, interval)))
        duration = round(time.time() - start, 3)

        if not rows or all(r.get('nb_mesures', 0) == 0 for r in rows):
            return err(tool, f'Aucune donnée WM pour "{period}"', 'Essayez wm_analysis("tout")')

        for r in rows:
            if r.get('index_debut') is not None and r.get('index_fin') is not None:
                r['consommation_nette_m3'] = round(r['index_fin'] - r['index_debut'], 3)

        return ok({'period': period, 'analysis': rows, 'duration': duration})

    except Exception as e:
        return err(tool, str(e))


def energy_analysis(period: str = '24h') -> str:
    """Analyse de la consommation électrique (puissance, tension, cosfi, THD) sur une période."""
    start = time.time()
    tool  = 'energy_analysis'
    logger.info(f'[{tool}] period={period}')
    try:
        interval, error = validate_period(tool, period)
        if error:
            return error

        table = _get_best_table('en')
        if not table:
            return err(tool, 'Aucune table énergie disponible')

        date_col = detect_date_col(table)
        col_map  = get_active_col_names(table)
        cols     = set(col_map.keys())

        agg_cols = []
        for i in range(1, 4):
            if f'en_l{i}'           in cols: agg_cols.append(f'ROUND(SUM(t.`{col_map[f"en_l{i}"]}`),2) AS total_kWh_L{i}')
            if f'active_power_l{i}' in cols: agg_cols.append(f'ROUND(AVG(t.`{col_map[f"active_power_l{i}"]}`),2) AS avg_W_L{i}')
            if f'rms_voltage_l{i}'  in cols: agg_cols.append(f'ROUND(AVG(t.`{col_map[f"rms_voltage_l{i}"]}`),2) AS avg_V_L{i}')
            if f'cosfi_l{i}'        in cols: agg_cols.append(f'ROUND(AVG(t.`{col_map[f"cosfi_l{i}"]}`),3) AS avg_cosfi_L{i}')
            if f'thd_l{i}'          in cols: agg_cols.append(f'ROUND(AVG(t.`{col_map[f"thd_l{i}"]}`),2) AS avg_THD_L{i}')
        agg_cols.append('COUNT(*) AS nb_mesures')

        if len(agg_cols) <= 1:
            return err(tool, 'Colonnes énergie introuvables')

        rows     = sanitize_rows(execute_sql(build_aggregated_query(table, agg_cols, date_col, interval)))
        duration = round(time.time() - start, 3)

        if not rows or all(r.get('nb_mesures', 0) == 0 for r in rows):
            return err(tool, f'Aucune donnée énergie pour "{period}"', 'Essayez energy_analysis("tout")')

        return ok({'period': period, 'analysis': rows, 'duration': duration})

    except Exception as e:
        return err(tool, str(e))


def gm_analysis(period: str = '24h') -> str:
    """Analyse de la consommation gaz (débit, index, fuites) sur une période."""
    start = time.time()
    tool  = 'gm_analysis'
    logger.info(f'[{tool}] period={period}')
    try:
        interval, error = validate_period(tool, period)
        if error:
            return error

        table = _get_best_table('gm')
        if not table:
            return err(tool, 'Aucune table GM disponible')

        date_col = detect_date_col(table)
        col_map  = get_active_col_names(table)
        cols     = set(col_map.keys())

        agg_cols = []
        if 'forward_flow'      in cols: agg_cols.append('ROUND(SUM(t.forward_flow),2) AS total_m3')
        if 'index'             in cols: agg_cols += ['MIN(t.`index`) AS index_debut',
                                                      'MAX(t.`index`) AS index_fin']
        if 'avg_debit_per_min' in cols: agg_cols.append('ROUND(AVG(t.avg_debit_per_min),4) AS avg_debit_min')
        if 'leak'              in cols: agg_cols.append('SUM(t.leak)  AS nb_fuites')
        if 'fraud'             in cols: agg_cols.append('SUM(t.fraud) AS nb_fraudes')
        if 'battery_level'     in cols: agg_cols.append('ROUND(AVG(t.battery_level),0) AS avg_batterie')
        agg_cols.append('COUNT(*) AS nb_mesures')

        rows     = sanitize_rows(execute_sql(build_aggregated_query(table, agg_cols, date_col, interval)))
        duration = round(time.time() - start, 3)

        if not rows or all(r.get('nb_mesures', 0) == 0 for r in rows):
            return err(tool, f'Aucune donnée GM pour "{period}"', 'Essayez gm_analysis("tout")')

        for r in rows:
            if r.get('index_debut') is not None and r.get('index_fin') is not None:
                r['consommation_nette_m3'] = round(r['index_fin'] - r['index_debut'], 3)

        return ok({'period': period, 'analysis': rows, 'duration': duration})

    except Exception as e:
        return err(tool, str(e))


def fuel_analysis(period: str = '24h') -> str:
    """Analyse de la consommation carburant (litres, distance, vitesse) sur une période."""
    start = time.time()
    tool  = 'fuel_analysis'
    logger.info(f'[{tool}] period={period}')
    try:
        interval, error = validate_period(tool, period)
        if error:
            return error

        table = _get_best_table('fuel')
        if not table:
            return err(tool, 'Aucune table fuel disponible')

        date_col = detect_date_col(table)
        col_map  = get_active_col_names(table)
        cols     = set(col_map.keys())

        agg_cols = []
        if 'consommation' in cols: agg_cols += ['ROUND(SUM(t.consommation),2) AS total_L',
                                                  'ROUND(AVG(t.consommation),2) AS avg_L']
        if 'distance'     in cols: agg_cols += ['ROUND(SUM(t.distance),2) AS total_km',
                                                  'ROUND(AVG(t.distance),2) AS avg_km']
        if 'vitesse'      in cols: agg_cols += ['ROUND(AVG(t.vitesse),2) AS avg_kmh',
                                                  'ROUND(MAX(t.vitesse),2) AS max_kmh']
        if 'temps_arret'  in cols: agg_cols.append('ROUND(SUM(t.temps_arret),0) AS total_arret_min')
        agg_cols.append('COUNT(*) AS nb_mesures')

        rows     = sanitize_rows(execute_sql(build_aggregated_query(table, agg_cols, date_col, interval)))
        duration = round(time.time() - start, 3)

        if not rows or all(r.get('nb_mesures', 0) == 0 for r in rows):
            return err(tool, f'Aucune donnée fuel pour "{period}"', 'Essayez fuel_analysis("tout")')

        return ok({'period': period, 'analysis': rows, 'duration': duration})

    except Exception as e:
        return err(tool, str(e))
