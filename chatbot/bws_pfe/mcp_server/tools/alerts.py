import time
import logging

from mcp_server.db.connection import (
    execute_sql, get_all_tables, get_table_columns,
    get_table_row_count, get_active_tables,
)
from mcp_server.tools._helpers import ok, err, detect_date_col

logger = logging.getLogger('aria.tools.alerts')


def _find_alert_tables() -> list[str]:
    """Détecte toutes les tables d'alertes/contraintes actives."""
    all_tables = get_all_tables()
    active     = get_active_tables()
    keywords   = ['alert', 'alarm', 'constraint', 'contrainte', 'anomal']
    return [
        t for t in all_tables
        if t in active and any(kw in t.lower() for kw in keywords)
    ]


def alerts_summary(filter: str = 'recentes') -> str:
    """Résumé des alertes et anomalies. filter: 'recentes' | 'frequentes' | 'all'"""
    start = time.time()
    tool  = 'alerts_summary'
    logger.info(f'[{tool}] filter={filter}')
    try:
        alert_tables = _find_alert_tables()

        if not alert_tables:
            # Aucune table d'alertes dédiée → analyse les anomalies THL en substitut
            return _analyze_thl_anomalies()

        alerts_data = []
        for table in alert_tables:
            count     = get_table_row_count(table)
            date_col  = detect_date_col(table)
            col_names = [c['name'] for c in get_table_columns(table)]

            try:
                if filter == 'recentes' and date_col:
                    rows = execute_sql(
                        f'SELECT * FROM `{table}` ORDER BY `{date_col}` DESC LIMIT 10'
                    )
                elif filter == 'frequentes':
                    id_col = next(
                        (c for c in col_names if 'device' in c.lower() or 'id' in c.lower()),
                        None
                    )
                    if id_col:
                        rows = execute_sql(
                            f'SELECT `{id_col}`, COUNT(*) as nb FROM `{table}` '
                            f'GROUP BY `{id_col}` ORDER BY nb DESC LIMIT 10'
                        )
                    else:
                        rows = execute_sql(f'SELECT * FROM `{table}` LIMIT 10')
                else:
                    rows = execute_sql(f'SELECT * FROM `{table}` LIMIT 20')

                alerts_data.append({
                    'table' : table,
                    'count' : count,
                    'filter': filter,
                    'rows'  : rows or [],
                })

            except Exception as te:
                alerts_data.append({
                    'table': table,
                    'count': count,
                    'error': str(te),
                    'rows' : [],
                })

        duration = round(time.time() - start, 3)
        logger.info(f'[{tool}] {len(alert_tables)} tables en {duration}s')

        return ok({
            'filter'      : filter,
            'tables_count': len(alert_tables),
            'alerts'      : alerts_data,
            'duration'    : duration,
        })

    except Exception as e:
        return err(tool, str(e))


def _analyze_thl_anomalies() -> str:
    """Analyse les anomalies THL quand aucune table d'alertes dédiée n'existe."""
    tool = 'alerts_summary'
    try:
        active    = get_active_tables()
        thl_table = next(
            (t for t in ['archive_thl', 'rt_thl', 'archive_thl_h'] if t in active),
            None
        )

        if not thl_table:
            return err(tool, 'Aucune table d\'alertes ni de données THL',
                       'Vérifiez la configuration de la base')

        col_names = [c['name'].lower() for c in get_table_columns(thl_table)]
        anomalies = []

        checks = [
            ('t',             't < 10 OR t > 35',   'Températures hors plage (< 10°C ou > 35°C)'),
            ('h',             'h < 20 OR h > 90',   'Humidités hors plage (< 20%HR ou > 90%HR)'),
            ('battery_level', 'battery_level < 20', 'Capteurs batterie faible (< 20%)'),
            ('rssi',          'rssi < -100',         'Signal faible RSSI (< -100 dBm)'),
        ]

        for col, cond, label in checks:
            if col in col_names:
                rows = execute_sql(
                    f'SELECT COUNT(*) as nb FROM `{thl_table}` WHERE {cond}'
                )
                if rows:
                    anomalies.append({'type': label, 'count': rows[0].get('nb', 0), 'col': col})

        return ok({
            'source'   : thl_table,
            'note'     : 'Aucune table d\'alertes dédiée — analyse sur données THL',
            'anomalies': anomalies,
        })

    except Exception as e:
        return err(tool, str(e))


if __name__ == '__main__':
    import logging as _log
    _log.basicConfig(level=_log.INFO)
    print(alerts_summary('recentes'))
