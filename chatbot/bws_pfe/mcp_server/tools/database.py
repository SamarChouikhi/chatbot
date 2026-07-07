import time
import logging

from mcp_server.db.connection import (
    execute_sql, get_all_tables, get_table_columns,
    get_table_row_count, get_active_tables, _assert_safe_table,
)
from mcp_server.tools._helpers import ok, err

logger = logging.getLogger('aria.tools.database')

MAX_ROWS = 200

FORBIDDEN_KEYWORDS = [
    'drop', 'delete', 'truncate', 'insert', 'update',
    'alter', 'create', 'grant', 'revoke', 'exec',
    'execute', '--', ';drop', ';delete',
    'union',                      # exfiltration inter-tables via UNION SELECT
    'load_file', 'into outfile', 'into dumpfile',  # accès filesystem MySQL
    'sleep(', 'benchmark(',       # time-based blind injection
]

# Regex pour détecter et remplacer/valider la clause LIMIT existante
import re as _re
_LIMIT_RE = _re.compile(r'\bLIMIT\s+(\d+)', _re.IGNORECASE)


def _is_safe_sql(query: str) -> tuple[bool, str]:
    q = query.lower().strip()
    if not q.startswith('select'):
        return False, 'Seules les requêtes SELECT sont autorisées'
    for kw in FORBIDDEN_KEYWORDS:
        if kw in q:
            return False, f'Mot-clé interdit : {kw!r}'
    return True, ''


def _force_limit(query: str) -> str:
    """Force LIMIT MAX_ROWS, qu'une clause LIMIT existe ou non.

    Si la requête contient déjà un LIMIT, on le remplace s'il dépasse MAX_ROWS.
    Cela évite qu'un LLM génère LIMIT 100000 pour contourner la limite.
    """
    q = query.strip().rstrip(';')
    m = _LIMIT_RE.search(q)
    if m:
        existing = int(m.group(1))
        if existing > MAX_ROWS:
            q = _LIMIT_RE.sub(f'LIMIT {MAX_ROWS}', q)
    else:
        q = f'{q} LIMIT {MAX_ROWS}'
    return q


def _check_table_exists(table_name: str, tool_name: str) -> str | None:
    """Retourne None si la table existe, sinon un JSON d'erreur avec suggestion."""
    all_tables = get_all_tables()
    if table_name not in all_tables:
        similar    = [t for t in all_tables if table_name[:4].lower() in t.lower()][:5]
        suggestion = (
            f'Tables similaires : {", ".join(similar)}'
            if similar else
            'Utilisez list_tables("actives") pour voir les tables disponibles'
        )
        return err(tool_name, f'Table "{table_name}" introuvable', suggestion)
    return None


def list_tables(filter: str = 'all') -> str:
    """Liste les tables de la base. filter: 'all' | 'actives' | 'empty'"""
    start = time.time()
    tool  = 'list_tables'
    logger.info(f'[{tool}] filter={filter}')
    try:
        all_tables = get_all_tables()
        active     = get_active_tables()

        if filter == 'actives':
            if not active:
                return err(tool, 'Aucune table avec données', 'La base semble vide')
            return ok({
                'filter'  : 'actives',
                'count'   : len(active),
                'tables'  : [{'name': t, 'rows': c}
                              for t, c in sorted(active.items(), key=lambda x: x[1], reverse=True)],
                'duration': round(time.time() - start, 3),
            })

        if filter == 'empty':
            empty = sorted([t for t in all_tables if t not in active])
            return ok({
                'filter'  : 'empty',
                'count'   : len(empty),
                'tables'  : empty,
                'duration': round(time.time() - start, 3),
            })

        return ok({
            'filter'      : 'all',
            'total'       : len(all_tables),
            'active_count': len(active),
            'empty_count' : len(all_tables) - len(active),
            'tables'      : [
                {'name': t, 'rows': active.get(t, 0), 'has_data': t in active}
                for t in sorted(all_tables)
            ],
            'duration': round(time.time() - start, 3),
        })

    except Exception as e:
        return err(tool, str(e))


def describe_table(table_name: str) -> str:
    """Décrit la structure d'une table : colonnes, types, aperçu. À appeler avant execute_query."""
    start = time.time()
    tool  = 'describe_table'
    logger.info(f'[{tool}] table={table_name}')
    try:
        check = _check_table_exists(table_name, tool)
        if check:
            return check

        columns   = get_table_columns(table_name)
        row_count = get_table_row_count(table_name)

        if not columns:
            return err(tool, f'Impossible de lire la structure de "{table_name}"')

        result = {
            'table'   : table_name,
            'rows'    : row_count,
            'columns' : [{'name': c['name'], 'type': c['type'], 'nullable': c['nullable']}
                          for c in columns],
            'duration': round(time.time() - start, 3),
        }

        if row_count > 0:
            try:
                result['preview'] = execute_sql(f'SELECT * FROM `{_assert_safe_table(table_name)}` LIMIT 3')
            except Exception:
                pass

        return ok(result)

    except Exception as e:
        return err(tool, str(e))


def execute_query(query: str) -> str:
    """Exécute une requête SELECT sur la base. LIMIT 200 forcé. Mots-clés dangereux bloqués."""
    start = time.time()
    tool  = 'execute_query'
    logger.info(f'[{tool}] {query[:80]}')
    try:
        safe, reason = _is_safe_sql(query)
        if not safe:
            return err(tool, reason, 'Utilisez uniquement des requêtes SELECT')

        query_safe = _force_limit(query)
        t_exec     = time.time()
        rows       = execute_sql(query_safe)
        t_exec     = round(time.time() - t_exec, 3)
        duration   = round(time.time() - start, 3)

        logger.info(f'[{tool}] {len(rows)} lignes en {t_exec}s')

        if not rows:
            return ok({'query': query_safe, 'rows': [], 'count': 0,
                       'message': 'Requête exécutée — aucun résultat', 'duration': duration})

        return ok({'query': query_safe, 'rows': rows, 'count': len(rows),
                   'exec_time': t_exec, 'duration': duration})

    except Exception as e:
        logger.error(f'[{tool}] SQL error: {e}')
        return err(tool, f'Erreur SQL : {str(e)}',
                   'Vérifiez la syntaxe. Appelez describe_table pour connaître les colonnes exactes')


if __name__ == '__main__':
    import logging as _log
    _log.basicConfig(level=_log.INFO)
    print(list_tables('actives'))
    print(describe_table('archive_thl'))
    print(execute_query('SELECT id_device, t, h FROM archive_thl LIMIT 3'))
