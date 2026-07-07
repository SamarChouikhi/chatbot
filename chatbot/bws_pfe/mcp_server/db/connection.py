import os
import re
import sys
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from mcp_server.config import DB, DB_URL

logger = logging.getLogger('aria.db')

# Noms de table valides : lettres, chiffres, underscore, tiret. Max 64 chars (MySQL limit).
_SAFE_TABLE_RE = re.compile(r'^[A-Za-z0-9_\-]{1,64}$')


def _assert_safe_table(name: str) -> str:
    """Lève ValueError si le nom de table contient des caractères suspects."""
    if not _SAFE_TABLE_RE.match(name):
        raise ValueError(f"Nom de table invalide : {name!r}")
    return name

engine = create_engine(
    DB_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={
        'connect_timeout': 10,  # timeout de connexion TCP (s)
        'read_timeout'   : 30,  # timeout d'exécution de requête MySQL (s)
        'write_timeout'  : 10,
    },
)

Session = sessionmaker(bind=engine)


def get_connection():
    return engine.connect()


def execute_sql(query: str, params: dict = None) -> list[dict]:
    """Exécute une requête SQL et retourne une liste de dicts. Ajoute LIMIT 200 si absent."""
    q = query.strip().rstrip(';')
    if 'limit' not in q.lower():
        q = f'{q} LIMIT 200'
    with engine.connect() as conn:
        result  = conn.execute(text(q), params or {})
        columns = list(result.keys())
        rows    = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]


def get_all_tables() -> list[str]:
    with engine.connect() as conn:
        result = conn.execute(text('SHOW TABLES'))
        return [row[0] for row in result.fetchall()]


def get_table_columns(table_name: str) -> list[dict]:
    """Retourne les colonnes d'une table via information_schema (utilise le pool partagé)."""
    with engine.connect() as conn:
        result = conn.execute(
            text('SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE '
                 'FROM information_schema.COLUMNS '
                 'WHERE TABLE_SCHEMA = DATABASE() '
                 '  AND TABLE_NAME = :table '
                 'ORDER BY ORDINAL_POSITION'),
            {'table': table_name}
        )
        return [
            {'name': row[0], 'type': row[1], 'nullable': row[2] == 'YES'}
            for row in result.fetchall()
        ]


def get_table_row_count(table_name: str) -> int:
    try:
        _assert_safe_table(table_name)
        with engine.connect() as conn:
            result = conn.execute(text(f'SELECT COUNT(*) FROM `{table_name}`'))
            return result.fetchone()[0]
    except Exception:
        return 0


def get_active_tables() -> dict[str, int]:
    """Retourne {table: row_count} pour les tables non vides.

    Stratégie hybride :
    - tables archive_* et rt_* (capteurs IoT) : COUNT(*) exact, car TABLE_ROWS
      InnoDB est une estimation peu fiable qui peut retourner 0 sur des tables
      non vides après des INSERT/DELETE sans ANALYZE TABLE.
    - autres tables : estimation information_schema (suffisamment fiable).
    """
    try:
        with engine.connect() as conn:
            # Récupère toutes les tables (sans filtrer sur TABLE_ROWS)
            # pour ne pas exclure les tables capteurs dont l'estimation est 0
            result = conn.execute(text(
                'SELECT TABLE_NAME, TABLE_ROWS '
                'FROM information_schema.TABLES '
                'WHERE TABLE_SCHEMA = DATABASE() '
                'ORDER BY TABLE_ROWS DESC'
            ))
            rows = result.fetchall()

        active = {}
        for table_name, est_count in rows:
            if table_name.startswith('archive_') or table_name.startswith('rt_'):
                # COUNT exact pour les tables capteurs (InnoDB estimate peu fiable)
                exact = get_table_row_count(table_name)
                if exact > 0:
                    active[table_name] = exact
            elif est_count and int(est_count) > 0:
                active[table_name] = int(est_count)
        return active

    except Exception as e:
        # Fallback si information_schema n'est pas accessible
        logger.warning(f'get_active_tables fallback : {e}')
        tables = get_all_tables()
        active = {}
        for table in tables:
            count = get_table_row_count(table)
            if count > 0:
                active[table] = count
        return active


def test_connection() -> dict:
    try:
        with engine.connect() as conn:
            version = conn.execute(text('SELECT VERSION()')).fetchone()[0]
            tables  = get_all_tables()
            active  = get_active_tables()
        return {
            'status'  : 'ok',
            'version' : version,
            'tables'  : len(tables),
            'active'  : len(active),
            'database': DB['database'],
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    result = test_connection()
    if result['status'] == 'ok':
        print(f'OK  MySQL {result["version"]}')
        print(f'    Base    : {result["database"]}')
        print(f'    Tables  : {result["tables"]}')
        print(f'    Actives : {result["active"]}')
    else:
        print(f'ERR {result["error"]}')
