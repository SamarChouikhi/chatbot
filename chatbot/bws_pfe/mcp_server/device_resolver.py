# ============================================================
# device_resolver.py — Résolution id_device → nom lisible
# Centralise tous les JOINs device/espace pour les tools ARIA
# ============================================================

import logging
import time
from mcp_server.db.connection import execute_sql

logger = logging.getLogger('aria.resolver')

# ══════════════════════════════════════════════════════════════
# CACHE — évite de requêter device/espace à chaque tool call
# ══════════════════════════════════════════════════════════════
_device_cache: dict = {}
_cache_ts: float    = 0.0
_CACHE_TTL: int     = 300  # 5 minutes


def _load_device_map() -> dict:
    """
    Charge le mapping complet id_device → {nom, espace} depuis la DB.
    Relation : rt_*/archive_*.id_device = device.adresse
    device.id_espace → espace.nom
    """
    global _device_cache, _cache_ts

    now = time.time()
    if _device_cache and (now - _cache_ts) < _CACHE_TTL:
        return _device_cache

    try:
        rows = execute_sql("""
            SELECT
                d.adresse        AS id_device,
                d.nom            AS device_nom,
                d.type           AS device_type,
                e.nom            AS espace_nom,
                e.id             AS espace_id
            FROM device d
            LEFT JOIN espace e ON d.id_espace = e.id
            WHERE d.adresse IS NOT NULL
            ORDER BY d.adresse
        """)

        mapping = {}
        for r in rows:
            mapping[r['id_device']] = {
                'nom'       : r.get('device_nom')  or f'Capteur {r["id_device"]}',
                'espace'    : r.get('espace_nom')  or 'Zone inconnue',
                'espace_id' : r.get('espace_id'),
                'type'      : r.get('device_type'),
            }

        _device_cache = mapping
        _cache_ts     = now
        logger.info(f'[resolver] {len(mapping)} capteurs chargés')
        return mapping

    except Exception as e:
        logger.warning(f'[resolver] Erreur chargement device map: {e}')
        return _device_cache or {}


def resolve_device(id_device) -> dict:
    """Retourne {nom, espace} pour un id_device — jamais l'ID brut."""
    mapping = _load_device_map()
    info = mapping.get(id_device) or mapping.get(str(id_device))
    if info:
        return {'nom': info['nom'], 'espace': info['espace']}
    return {'nom': 'Capteur inconnu', 'espace': 'Zone inconnue'}


def resolve_devices(id_list: list) -> list[dict]:
    """Résout une liste d'IDs → liste de {nom, espace}."""
    return [resolve_device(i) for i in id_list]


def invalidate_cache():
    """Force le rechargement au prochain appel."""
    global _cache_ts
    _cache_ts = 0.0


# ══════════════════════════════════════════════════════════════
# REQUÊTES AVEC JOIN INTÉGRÉ
# ══════════════════════════════════════════════════════════════

def build_named_select(
    data_table: str,
    data_cols: list[str],
    date_col: str | None = None,
    where: str = '',
    group_by_device: bool = True,
    order_by: str = '',
    limit: int = 50,
) -> str:
    """
    Construit une requête SELECT avec JOIN device/espace.
    Retourne device.nom et espace.nom à la place de id_device.
    """
    safe_data_cols = [
        f't.`{c}`'
        for c in data_cols
        if c.lower() != 'id_device'
    ]

    select_parts = [
        'COALESCE(d.nom, CONCAT(\'Capteur-\', t.id_device)) AS capteur_nom',
        'COALESCE(e.nom, \'Zone inconnue\') AS zone',
    ] + safe_data_cols

    if date_col:
        select_parts.append(f't.`{date_col}` AS mesure_date')

    select_str   = ',\n        '.join(select_parts)
    where_clause = f'WHERE {where}' if where else ''
    group_clause = 'GROUP BY t.id_device, d.nom, e.nom' if group_by_device else ''
    order_clause = order_by or (
        f'ORDER BY t.`{date_col}` DESC' if date_col and not group_by_device else ''
    )

    return f"""
    SELECT
        {select_str}
    FROM `{data_table}` t
    LEFT JOIN device d ON d.adresse = t.id_device
    LEFT JOIN espace e ON e.id = d.id_espace
    {where_clause}
    {group_clause}
    {order_clause}
    LIMIT {limit}
    """.strip()


def build_realtime_query(
    data_table: str,
    sensor_cols: list[str],
    limit: int = 30,
    date_col: str | None = None,
) -> str:
    """Requête temps réel avec noms lisibles — dernières valeurs par capteur."""
    cols_str     = ', '.join([f't.`{c}`' for c in sensor_cols])
    order_clause = f'ORDER BY t.`{date_col}` DESC' if date_col else ''
    return f"""
    SELECT
        COALESCE(d.nom, CONCAT('Capteur-', t.id_device)) AS capteur_nom,
        COALESCE(e.nom, 'Zone inconnue') AS zone,
        {cols_str}
    FROM `{data_table}` t
    LEFT JOIN device d ON d.adresse = t.id_device
    LEFT JOIN espace e ON e.id = d.id_espace
    {order_clause}
    LIMIT {limit}
    """.strip()


def build_aggregated_query(
    data_table: str,
    agg_cols: list[str],
    date_col: str | None,
    interval: str | None,
    limit: int = 100,
) -> str:
    """Requête agrégée (MIN/AVG/MAX/COUNT) groupée par capteur avec noms."""
    agg_str = ',\n        '.join(agg_cols)
    where   = f'WHERE t.`{date_col}` >= NOW() - {interval}' if date_col and interval else ''

    # GROUP BY t.id_device pour que chaque capteur physique ait sa propre ligne,
    # même si d.adresse est NULL (LEFT JOIN sans correspondance dans device).
    return f"""
    SELECT
        COALESCE(d.nom, CONCAT('Capteur-', t.id_device)) AS capteur_nom,
        COALESCE(e.nom, 'Zone inconnue') AS zone,
        {agg_str}
    FROM `{data_table}` t
    LEFT JOIN device d ON d.adresse = t.id_device
    LEFT JOIN espace e ON e.id = d.id_espace
    {where}
    GROUP BY t.id_device, d.nom, e.nom
    ORDER BY capteur_nom
    LIMIT {limit}
    """.strip()


def build_anomaly_query(
    data_table: str,
    condition: str,
    date_col: str | None,
    interval: str | None,
    extra_cols: list[str] | None = None,
    limit: int = 20,
) -> str:
    """Requête anomalies avec noms lisibles — jamais l'ID dans le résultat."""
    extra      = ', '.join([f't.`{c}`' for c in (extra_cols or [])])
    extra_str  = f', {extra}' if extra else ''
    extra_grp  = (', ' + extra) if extra else ''
    where_time = f'AND t.`{date_col}` >= NOW() - {interval}' if date_col and interval else ''

    return f"""
    SELECT
        COALESCE(d.nom, CONCAT('Capteur-', t.id_device)) AS capteur_nom,
        COALESCE(e.nom, 'Zone inconnue') AS zone{extra_str}
    FROM `{data_table}` t
    LEFT JOIN device d ON d.adresse = t.id_device
    LEFT JOIN espace e ON e.id = d.id_espace
    WHERE ({condition})
    {where_time}
    GROUP BY t.id_device, d.nom, e.nom{extra_grp}
    LIMIT {limit}
    """.strip()


def build_inactive_query(data_table: str, date_col: str, limit: int = 20) -> str:
    """Capteurs inactifs > 24h — avec nom lisible et durée d'inactivité."""
    return f"""
    SELECT
        COALESCE(d.nom, CONCAT('Capteur-', t.id_device))        AS capteur_nom,
        COALESCE(e.nom, 'Zone inconnue')                         AS zone,
        TIMESTAMPDIFF(HOUR, MAX(t.`{date_col}`), NOW())         AS heures_silence
    FROM `{data_table}` t
    LEFT JOIN device d ON d.adresse = t.id_device
    LEFT JOIN espace e ON e.id = d.id_espace
    GROUP BY t.id_device, d.nom, e.nom
    HAVING heures_silence > 24
    ORDER BY heures_silence DESC
    LIMIT {limit}
    """.strip()
