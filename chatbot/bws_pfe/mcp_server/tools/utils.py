import os
import time
import logging

from mcp_server.db.connection import (
    execute_sql, get_all_tables, get_table_columns,
    get_table_row_count, get_active_tables,
)
from mcp_server.tools._helpers import ok, err, detect_text_cols

logger = logging.getLogger('aria.tools.utils')


def count_rows(table_name: str) -> str:
    """Retourne le nombre exact de lignes d'une table."""
    start = time.time()
    tool  = 'count_rows'
    logger.info(f'[{tool}] table={table_name}')
    try:
        all_tables = get_all_tables()
        if table_name not in all_tables:
            similar    = [t for t in all_tables if table_name.lower()[:4] in t.lower()][:5]
            suggestion = (
                f'Tables similaires : {", ".join(similar)}'
                if similar else 'Utilisez list_tables("actives") pour voir les tables'
            )
            return err(tool, f'Table "{table_name}" introuvable', suggestion)

        count    = get_table_row_count(table_name)
        duration = round(time.time() - start, 3)
        return ok({'table': table_name, 'rows': count, 'has_data': count > 0, 'duration': duration})

    except Exception as e:
        return err(tool, str(e))


def search_in_table(params: str) -> str:
    """Recherche un terme dans une table. params: "table_name|search_term" """
    start = time.time()
    tool  = 'search_in_table'
    logger.info(f'[{tool}] params={params}')
    try:
        if '|' not in params:
            return err(tool, 'Format incorrect',
                       'Format attendu : "table_name|search_term" — Ex: "device|capteur_A"')

        table_name, term = params.split('|', 1)
        table_name = table_name.strip()
        term       = term.strip()

        if not term:
            return err(tool, 'Terme de recherche vide')

        if table_name not in get_all_tables():
            return err(tool, f'Table "{table_name}" introuvable', 'Utilisez list_tables("actives")')

        columns = get_table_columns(table_name)
        if not columns:
            return err(tool, f'Impossible de lire les colonnes de "{table_name}"')

        text_cols = detect_text_cols(table_name)

        if not text_cols:
            num_cols = [
                c['name'] for c in columns
                if any(t in c['type'].lower() for t in ['int', 'double', 'float', 'decimal'])
            ]
            if num_cols and term.replace('.', '').lstrip('-').isdigit():
                conditions = ' OR '.join([f'`{c}` = :val' for c in num_cols[:5]])
                rows = execute_sql(
                    f'SELECT * FROM `{table_name}` WHERE {conditions} LIMIT 50',
                    {'val': term}
                )
            else:
                return err(tool, f'Aucune colonne texte dans "{table_name}"',
                           'Utilisez execute_query pour une recherche personnalisée')
        else:
            conditions = ' OR '.join([f'`{c}` LIKE :term' for c in text_cols])
            rows = execute_sql(
                f'SELECT * FROM `{table_name}` WHERE {conditions} LIMIT 50',
                {'term': f'%{term}%'}
            )

        duration = round(time.time() - start, 3)

        if not rows:
            return ok({'table': table_name, 'search_term': term, 'rows': [], 'count': 0,
                       'message': f'Aucun résultat pour "{term}"', 'duration': duration})

        return ok({'table': table_name, 'search_term': term, 'rows': rows,
                   'count': len(rows), 'duration': duration})

    except Exception as e:
        return err(tool, str(e))


def database_summary() -> str:
    """Vue d'ensemble complète de la base par catégorie de table."""
    start = time.time()
    tool  = 'database_summary'
    logger.info(f'[{tool}] called')
    try:
        all_tables    = get_all_tables()
        active        = get_active_tables()
        sorted_active = sorted(active.items(), key=lambda x: x[1], reverse=True)
        total_rows    = sum(active.values())

        def _cat(t):
            if t.startswith('rt_'):      return 'realtime'
            if t.startswith('archive_'): return 'archive'
            if any(k in t for k in ['constraint', 'alert', 'anomal']): return 'alerts'
            if any(k in t for k in ['config', 'device', 'espace', 'group',
                                     'produit', 'period', 'user']): return 'config'
            return 'other'

        rt_tables     = [t for t in active if t.startswith('rt_')]
        arch_tables   = [t for t in active if t.startswith('archive_')]
        alert_tables  = [t for t in active if any(k in t for k in ['constraint', 'alert', 'anomal'])]
        config_tables = [t for t in active if any(k in t for k in
                          ['config', 'device', 'espace', 'group', 'produit', 'period', 'user'])]

        duration = round(time.time() - start, 3)
        logger.info(f'[{tool}] {len(all_tables)} tables en {duration}s')

        return ok({
            'database'     : os.getenv('DB_NAME', 'bw_samar'),
            'total_tables' : len(all_tables),
            'active_tables': len(active),
            'empty_tables' : len(all_tables) - len(active),
            'total_rows'   : total_rows,
            'categories'   : {
                'realtime': rt_tables,
                'archive' : arch_tables,
                'alerts'  : alert_tables,
                'config'  : config_tables,
            },
            'tables'  : [{'name': t, 'rows': c, 'category': _cat(t)} for t, c in sorted_active],
            'duration': duration,
        })

    except Exception as e:
        return err(tool, str(e))


if __name__ == '__main__':
    import logging as _log
    _log.basicConfig(level=_log.INFO)
    print(count_rows('archive_thl'))
    print(search_in_table('device|capteur'))
    print(database_summary())
