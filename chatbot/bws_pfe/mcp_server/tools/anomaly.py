import time
import logging

from mcp_server.db.connection import execute_sql, get_active_tables
from mcp_server.tools._helpers import (
    ok, detect_date_col, get_active_col_names,
    THRESHOLDS, SENSOR_TABLE_PRIORITY,
    validate_period, sanitize_rows,
)
from mcp_server.device_resolver import build_anomaly_query, build_inactive_query

logger = logging.getLogger('aria.tools.anomaly')


def _get_table(sensor_type: str) -> str | None:
    active = get_active_tables()
    return next((t for t in SENSOR_TABLE_PRIORITY.get(sensor_type, []) if t in active), None)


def _cols(table: str) -> set[str]:
    return set(get_active_col_names(table).keys())


def _col(table: str, name: str) -> str:
    return get_active_col_names(table).get(name, name)


def _run(query: str) -> list[dict]:
    return sanitize_rows(execute_sql(query))


def anomaly_detection(period: str = 'tout') -> str:
    """Détecte les anomalies sur tous les capteurs. period: 'tout' | '24h' | '7j' | '30j'"""
    start = time.time()
    tool  = 'anomaly_detection'
    logger.info(f'[{tool}] period={period}')

    interval, error = validate_period(tool, period)
    if error:
        return error

    summary = {
        'extreme_values'  : [],
        'sensor_issues'   : [],
        'fluid_alerts'    : [],
        'energy_alerts'   : [],
        'inactive_sensors': [],
    }

    thl_table = wm_table = gm_table = en_table = sm_table = pir_table = ls_table = None

    # ── THL ──────────────────────────────────────────────────────────────────
    try:
        thl_table = _get_table('thl')
        if thl_table:
            cols     = _cols(thl_table)
            date_col = detect_date_col(thl_table)
            t_col    = _col(thl_table, 't')
            h_col    = _col(thl_table, 'h')

            if 't' in cols:
                th   = THRESHOLDS['temperature']
                rows = _run(build_anomaly_query(
                    thl_table,
                    f't.`{t_col}` < {th["min"]} OR t.`{t_col}` > {th["max"]}',
                    date_col, interval, extra_cols=[t_col],
                ))
                if rows:
                    summary['extreme_values'].append({
                        'sensor_type': 'THL', 'type': 'température_hors_plage',
                        'seuil': f'{th["min"]}–{th["max"]} {th["unit"]}',
                        'count': len(rows), 'capteurs': rows,
                        'severity': 'HIGH' if len(rows) > 5 else 'MEDIUM',
                    })

            if 'h' in cols:
                th   = THRESHOLDS['humidity']
                rows = _run(build_anomaly_query(
                    thl_table,
                    f't.`{h_col}` < {th["min"]} OR t.`{h_col}` > {th["max"]}',
                    date_col, interval, extra_cols=[h_col],
                ))
                if rows:
                    summary['extreme_values'].append({
                        'sensor_type': 'THL', 'type': 'humidité_hors_plage',
                        'seuil': f'{th["min"]}–{th["max"]} {th["unit"]}',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })

            if 'battery_level' in cols:
                bat_col = _col(thl_table, 'battery_level')
                rows    = _run(build_anomaly_query(
                    thl_table,
                    f't.`{bat_col}` < {THRESHOLDS["battery"]["min"]}',
                    date_col, interval, extra_cols=[bat_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'THL', 'type': 'batterie_faible',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })

            if 'rssi' in cols:
                rssi_col = _col(thl_table, 'rssi')
                rows     = _run(build_anomaly_query(
                    thl_table,
                    f't.`{rssi_col}` < {THRESHOLDS["rssi"]["min"]}',
                    date_col, interval, extra_cols=[rssi_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'THL', 'type': 'signal_faible',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })
    except Exception as exc:
        logger.warning('[%s] THL ignoré : %s', tool, exc)

    # ── WM ───────────────────────────────────────────────────────────────────
    try:
        wm_table = _get_table('wm')
        if wm_table:
            cols     = _cols(wm_table)
            date_col = detect_date_col(wm_table)

            for flag, label, sev in [
                ('leak',  'fuite_eau',    'HIGH'),
                ('fraud', 'fraude_eau',   'HIGH'),
                ('tamp',  'tampering_wm', 'MEDIUM'),
            ]:
                if flag in cols:
                    rows = _run(build_anomaly_query(wm_table, f't.{flag} = 1', date_col, interval))
                    if rows:
                        summary['fluid_alerts'].append({
                            'sensor_type': 'WM', 'type': label,
                            'count': len(rows), 'capteurs': rows, 'severity': sev,
                        })

            if 'battery_level' in cols:
                bat_col = _col(wm_table, 'battery_level')
                rows    = _run(build_anomaly_query(
                    wm_table,
                    f't.`{bat_col}` > 0 AND t.`{bat_col}` < {THRESHOLDS["battery"]["min"]}',
                    date_col, interval, extra_cols=[bat_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'WM', 'type': 'batterie_faible',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })
    except Exception as exc:
        logger.warning('[%s] WM ignoré : %s', tool, exc)

    #GM
    try:
        gm_table = _get_table('gm')
        if gm_table:
            cols     = _cols(gm_table)
            date_col = detect_date_col(gm_table)

            for flag, label, sev in [
                ('leak',  'fuite_gaz',    'HIGH'),
                ('fraud', 'fraude_gaz',   'HIGH'),
                ('tamp',  'tampering_gm', 'MEDIUM'),
            ]:
                if flag in cols:
                    rows = _run(build_anomaly_query(gm_table, f't.{flag} = 1', date_col, interval))
                    if rows:
                        summary['fluid_alerts'].append({
                            'sensor_type': 'GM', 'type': label,
                            'count': len(rows), 'capteurs': rows, 'severity': sev,
                        })
    except Exception as exc:
        logger.warning('[%s] GM ignoré : %s', tool, exc)

    #EN
    try:
        en_table = _get_table('en')
        if en_table:
            col_map  = get_active_col_names(en_table)
            cols     = set(col_map.keys())
            date_col = detect_date_col(en_table)

            for i in range(1, 4):
                if f'rms_voltage_l{i}' in cols:
                    orig = col_map[f'rms_voltage_l{i}']
                    th   = THRESHOLDS['voltage']
                    rows = _run(build_anomaly_query(
                        en_table,
                        f't.`{orig}` > 0 AND (t.`{orig}` < {th["min"]} OR t.`{orig}` > {th["max"]})',
                        date_col, interval, extra_cols=[orig],
                    ))
                    if rows:
                        summary['energy_alerts'].append({
                            'sensor_type': 'EN', 'type': f'tension_hors_plage_L{i}',
                            'count': len(rows), 'capteurs': rows, 'severity': 'HIGH',
                        })

                if f'cosfi_l{i}' in cols:
                    orig = col_map[f'cosfi_l{i}']
                    rows = _run(build_anomaly_query(
                        en_table,
                        f't.`{orig}` > 0 AND t.`{orig}` < {THRESHOLDS["cosfi"]["min"]}',
                        date_col, interval, extra_cols=[orig],
                    ))
                    if rows:
                        summary['energy_alerts'].append({
                            'sensor_type': 'EN', 'type': f'cosfi_faible_L{i}',
                            'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                        })

                if f'thd_l{i}' in cols:
                    orig = col_map[f'thd_l{i}']
                    # THD > 10 % → HIGH (risque dommages équipements, norme IEC)
                    rows_high = _run(build_anomaly_query(
                        en_table,
                        f't.`{orig}` > 10.0',
                        date_col, interval, extra_cols=[orig],
                    ))
                    if rows_high:
                        summary['energy_alerts'].append({
                            'sensor_type': 'EN', 'type': f'THD_critique_L{i}',
                            'count': len(rows_high), 'capteurs': rows_high, 'severity': 'HIGH',
                        })
                    # THD 5–10 % → MEDIUM (filtre harmonique recommandé)
                    rows_med = _run(build_anomaly_query(
                        en_table,
                        f't.`{orig}` > {THRESHOLDS["thd"]["max"]} AND t.`{orig}` <= 10.0',
                        date_col, interval, extra_cols=[orig],
                    ))
                    if rows_med:
                        summary['energy_alerts'].append({
                            'sensor_type': 'EN', 'type': f'THD_élevé_L{i}',
                            'count': len(rows_med), 'capteurs': rows_med, 'severity': 'MEDIUM',
                        })
    except Exception as exc:
        logger.warning('[%s] EN ignoré : %s', tool, exc)

    #SM
    try:
        sm_table = _get_table('sm')
        if sm_table:
            cols     = _cols(sm_table)
            date_col = detect_date_col(sm_table)
            if 'v' in cols:
                v_col = _col(sm_table, 'v')
                th    = THRESHOLDS['wind_speed']
                rows  = _run(build_anomaly_query(
                    sm_table,
                    f't.`{v_col}` > {th["max"]}',
                    date_col, interval, extra_cols=[v_col],
                ))
                if rows:
                    summary['extreme_values'].append({
                        'sensor_type': 'SM', 'type': 'vent_violent',
                        'seuil': f'>{th["max"]} {th["unit"]}',
                        'count': len(rows), 'capteurs': rows, 'severity': 'HIGH',
                    })
            if 'vitesse_rafale' in cols:
                vr_col = _col(sm_table, 'vitesse_rafale')
                rows   = _run(build_anomaly_query(
                    sm_table,
                    f't.`{vr_col}` > {THRESHOLDS["wind_speed"]["max"] * 1.5}',
                    date_col, interval, extra_cols=[vr_col],
                ))
                if rows:
                    summary['extreme_values'].append({
                        'sensor_type': 'SM', 'type': 'rafale_extreme',
                        'seuil': f'>{THRESHOLDS["wind_speed"]["max"] * 1.5} m/s',
                        'count': len(rows), 'capteurs': rows, 'severity': 'HIGH',
                    })
            if 'battery_level' in cols:
                bat_col = _col(sm_table, 'battery_level')
                rows    = _run(build_anomaly_query(
                    sm_table,
                    f't.`{bat_col}` > 0 AND t.`{bat_col}` < {THRESHOLDS["battery"]["min"]}',
                    date_col, interval, extra_cols=[bat_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'SM', 'type': 'batterie_faible',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })
            if 'rssi' in cols:
                rssi_col = _col(sm_table, 'rssi')
                rows     = _run(build_anomaly_query(
                    sm_table,
                    f't.`{rssi_col}` < {THRESHOLDS["rssi"]["min"]}',
                    date_col, interval, extra_cols=[rssi_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'SM', 'type': 'signal_faible',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })
    except Exception as exc:
        logger.warning('[%s] SM ignoré : %s', tool, exc)

    # PIR
    try:
        pir_table = _get_table('pir')
        if pir_table:
            cols     = _cols(pir_table)
            date_col = detect_date_col(pir_table)
            if 'traffic_percentage' in cols:
                tp_col = _col(pir_table, 'traffic_percentage')
                rows   = _run(build_anomaly_query(
                    pir_table,
                    f't.`{tp_col}` > 80',
                    date_col, interval, extra_cols=[tp_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'PIR', 'type': 'saturation_trafic',
                        'seuil': '>80%', 'count': len(rows), 'capteurs': rows,
                        'severity': 'MEDIUM',
                    })
    except Exception as exc:
        logger.warning('[%s] PIR ignoré : %s', tool, exc)

    #LS
    try:
        ls_table = _get_table('ls')
        if ls_table:
            cols     = _cols(ls_table)
            date_col = detect_date_col(ls_table)
            if 'status' in cols:
                st_col = _col(ls_table, 'status')
                rows = _run(build_anomaly_query(
                    ls_table,
                    f't.`{st_col}` = 1',
                    date_col, interval,
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'LS', 'type': 'niveau_bas',
                        'count': len(rows), 'capteurs': rows, 'severity': 'HIGH',
                    })
            if 'battery_level' in cols:
                bat_col = _col(ls_table, 'battery_level')
                rows    = _run(build_anomaly_query(
                    ls_table,
                    f't.`{bat_col}` > 0 AND t.`{bat_col}` < {THRESHOLDS["battery"]["min"]}',
                    date_col, interval, extra_cols=[bat_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'LS', 'type': 'batterie_faible',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })
            if 'rssi' in cols:
                rssi_col = _col(ls_table, 'rssi')
                rows     = _run(build_anomaly_query(
                    ls_table,
                    f't.`{rssi_col}` < {THRESHOLDS["rssi"]["min"]}',
                    date_col, interval, extra_cols=[rssi_col],
                ))
                if rows:
                    summary['sensor_issues'].append({
                        'sensor_type': 'LS', 'type': 'signal_faible',
                        'count': len(rows), 'capteurs': rows, 'severity': 'MEDIUM',
                    })
    except Exception as exc:
        logger.warning('[%s] LS ignoré : %s', tool, exc)

    #Capteurs inactifs
    for stype, table in [('THL', thl_table), ('WM', wm_table),
                          ('GM', gm_table),   ('EN', en_table),
                          ('SM', sm_table),   ('PIR', pir_table),
                          ('LS', ls_table)]:
        if not table:
            continue
        date_col = detect_date_col(table)
        if not date_col:
            continue
        try:
            rows = _run(build_inactive_query(table, date_col))
            if rows:
                summary['inactive_sensors'].append({
                    'sensor_type': stype,
                    'count'      : len(rows),
                    'capteurs'   : rows,
                    'severity'   : 'HIGH' if len(rows) > 3 else 'MEDIUM',
                })
        except Exception as e:
            logger.warning(f'[{tool}] inactive check échoué pour {stype}: {e}')

    # Résultat toujours retourné
    total = sum(sum(a.get('count', 0) for a in v) for v in summary.values())

    if total == 0:   verdict, severity = 'Système nominal',                           'OK'
    elif total < 5:  verdict, severity = 'Anomalies mineures',                        'LOW'
    elif total < 20: verdict, severity = 'Anomalies significatives',                  'MEDIUM'
    else:            verdict, severity = 'Anomalies critiques — intervention urgente', 'HIGH'

    duration = round(time.time() - start, 3)
    logger.info(f'[{tool}] {total} anomalies ({severity}) en {duration}s')

    return ok({
        'period'         : period,
        'total_anomalies': total,
        'severity'       : severity,
        'verdict'        : verdict,
        'summary'        : summary,
        'duration'       : duration,
    })
