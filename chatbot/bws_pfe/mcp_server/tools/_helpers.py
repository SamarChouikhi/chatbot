import json
import logging
import time
from threading import Lock
from mcp_server.db.connection import get_table_columns

logger = logging.getLogger('aria.tools')

# Cache de schéma de colonnes : évite N appels DB identiques par réponse.
# TTL = 5 min — acceptable pour un schéma MySQL qui change rarement.
_COL_CACHE: dict[str, tuple[list, float]] = {}
_COL_CACHE_TTL = 300
_COL_LOCK = Lock()


def _columns(table_name: str) -> list[dict]:
    """Retourne les colonnes d'une table depuis le cache ou la DB.
    L'appel DB est fait hors du lock pour ne pas bloquer les autres threads readers."""
    now = time.time()
    with _COL_LOCK:
        if table_name in _COL_CACHE:
            cols, ts = _COL_CACHE[table_name]
            if now - ts < _COL_CACHE_TTL:
                return cols
    # Appel DB HORS du lock — un double-fetch concurrent est acceptable
    cols = get_table_columns(table_name)
    with _COL_LOCK:
        _COL_CACHE[table_name] = (cols, now)
    return cols

PERIOD_MAP = {
    '1h'  : 'INTERVAL 1 HOUR',
    '24h' : 'INTERVAL 24 HOUR',
    '48h' : 'INTERVAL 48 HOUR',
    '7j'  : 'INTERVAL 7 DAY',
    '30j' : 'INTERVAL 30 DAY',
    '60j' : 'INTERVAL 60 DAY',
    '90j' : 'INTERVAL 90 DAY',
    'mois': 'INTERVAL 30 DAY',
    'tout': None,
}

THRESHOLDS = {
    'temperature' : {'min': 10.0,  'max': 35.0,  'unit': '°C'},
    'humidity'    : {'min': 20.0,  'max': 80.0,  'unit': '%HR'},
    'battery'     : {'min': 20,    'max': 100,   'unit': '%'},
    'rssi'        : {'min': -110,  'max': -30,   'unit': 'dBm'},
    'rssi_warning': -80,
    'voltage'     : {'min': 207.0, 'max': 253.0, 'unit': 'V'},
    'cosfi'       : {'min': 0.8,   'max': 1.0,   'unit': ''},
    'thd'         : {'min': 0.0,   'max': 5.0,   'unit': '%'},
    'wind_speed'  : {'min': 0.0,   'max': 30.0,  'unit': 'm/s'},
}

# Ordre de priorité des tables : archive avant rt_ car l'archive est plus complète
SENSOR_TABLE_PRIORITY = {
    'thl' : ['archive_thl',  'archive_thl_h',  'rt_thl'],
    'wm'  : ['archive_wm',   'archive_wm_h',   'rt_wm'],
    'en'  : ['archive_en_p', 'archive_en_p_h', 'rt_en_p'],
    'gm'  : ['archive_gm',   'archive_gm_h',   'rt_gm'],
    'sm'  : ['archive_sm',   'rt_sm'],
    'pir' : ['archive_pir',  'rt_pir'],
    'ls'  : ['archive_ls',   'rt_ls'],
    'fuel': ['archive_fuel', 'archive_fuel_h'],
}

# Champs à ne jamais retourner au LLM (identifiants techniques, timestamps internes)
_CONFIDENTIAL_FIELDS = {
    'id_device', 'id', 'device_id', 'gateway', 'snr',
    'date', 'created_at', 'updated_at', 'timestamp',
    'derniere_mesure', 'last_seen',
}


def ok(data: dict) -> str:
    return json.dumps({'status': 'success', **data}, ensure_ascii=False, default=str)


def err(tool: str, message: str, suggestion: str = '') -> str:
    result = {'status': 'error', 'tool': tool, 'message': message}
    if suggestion:
        result['suggestion'] = suggestion
    logger.warning(f'[{tool}] ERROR: {message}')
    return json.dumps(result, ensure_ascii=False)


def detect_date_col(table_name: str) -> str | None:
    """Détecte la colonne datetime/timestamp d'une table (type exact avant nom)."""
    try:
        columns = _columns(table_name)
        for col in columns:
            if any(t in col['type'].lower() for t in ['datetime', 'timestamp']):
                return col['name']
        for col in columns:
            if 'date' in col['name'].lower():
                return col['name']
        return None
    except Exception:
        return None


def detect_thl_cols(table_name: str) -> dict:
    """Retourne un mapping {'t': col_T, 'h': col_H, 'l': col_L} pour une table THL."""
    try:
        columns = _columns(table_name)
        col_map = {c['name'].lower(): c['name'] for c in columns}
        result  = {}
        for alias in ['t', 'temp', 'temperature', 't_avg']:
            if alias in col_map:
                result['t'] = col_map[alias]
                break
        for alias in ['h', 'hum', 'humidity', 'h_avg']:
            if alias in col_map:
                result['h'] = col_map[alias]
                break
        for alias in ['l', 'lux', 'light', 'luminosity', 'l_avg']:
            if alias in col_map:
                result['l'] = col_map[alias]
                break
        return result
    except Exception:
        return {}


def detect_device_col(table_name: str) -> str | None:
    try:
        columns = _columns(table_name)
        for col in columns:
            if any(k in col['name'].lower() for k in ['id_device', 'device', 'sensor', 'capteur']):
                return col['name']
        return None
    except Exception:
        return None


def detect_text_cols(table_name: str) -> list[str]:
    try:
        columns = _columns(table_name)
        return [
            c['name'] for c in columns
            if any(t in c['type'].lower() for t in ['varchar', 'text', 'char', 'enum'])
        ]
    except Exception:
        return []


def get_col_original(table_name: str, col_lower: str) -> str | None:
    """Retourne le nom original d'une colonne à partir de son nom en lowercase."""
    try:
        columns = _columns(table_name)
        for c in columns:
            if c['name'].lower() == col_lower:
                return c['name']
        return None
    except Exception:
        return None


def get_active_col_names(table_name: str) -> dict:
    """Retourne {lowercase: original} pour toutes les colonnes d'une table."""
    try:
        return {c['name'].lower(): c['name'] for c in get_table_columns(table_name)}
    except Exception:
        return {}


def build_period_filter(date_col: str | None, interval: str | None) -> str:
    if date_col and interval:
        return f'WHERE `{date_col}` >= NOW() - {interval}'
    return ''


def add_condition(where: str, condition: str) -> str:
    if where:
        return f'{where} AND ({condition})'
    return f'WHERE ({condition})'


def sanitize_row(row: dict, keep_fields: set | None = None) -> dict:
    """Supprime les champs confidentiels avant envoi au LLM."""
    allowed = keep_fields or set()
    return {
        k: v for k, v in row.items()
        if k.lower() not in _CONFIDENTIAL_FIELDS or k in allowed
    }


def sanitize_rows(rows: list[dict], keep_fields: set | None = None) -> list[dict]:
    return [sanitize_row(r, keep_fields) for r in rows]


def validate_period(tool: str, period: str) -> tuple:
    """Valide la période et retourne (interval_sql, None) ou (None, json_error)."""
    p = period.lower().strip()
    if p not in PERIOD_MAP:
        valeurs = ', '.join(PERIOD_MAP.keys())
        return None, err(tool, f'Période "{period}" inconnue', f'Valeurs acceptées : {valeurs}')
    return PERIOD_MAP[p], None


def count_anomalies(rows: list[dict]) -> dict:
    """Résumé agrégé d'anomalies sans données sensibles."""
    return {
        'count'   : len(rows),
        'severity': 'HIGH' if len(rows) > 10 else 'MEDIUM' if len(rows) > 3 else 'LOW',
    }
