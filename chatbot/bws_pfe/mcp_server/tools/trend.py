"""
ARIA MCP — Courbes de consommation (séries temporelles).

Contrairement à wm_analysis/energy_analysis/gm_analysis/fuel_analysis (une ligne
agrégée par capteur sur toute la période), ces outils retournent une série de
points dans le temps — pour tracer une courbe horaire (jour courant) ou
journalière (période plus longue) d'un capteur spécifique, ou comparer
plusieurs compteurs entre eux sur le même graphique.

Source : tables daily_<domaine> (buckets horaires alimentés par le pipeline
quotidien) — un tool exposé par domaine pour respecter le filtrage par module
(_TOOL_MODULE_MAP dans mcp_client/agent.py est fail-closed par nom d'outil).
"""
import time
import logging

from mcp_server.db.connection import engine
from mcp_server.tools._helpers import ok, err
from sqlalchemy import text

logger = logging.getLogger('aria.tools.trend')

_DOMAIN_CONFIG = {
    'energy': {'table': 'daily_energy', 'value_col': 'cons_en',     'unit': 'kWh', 'label': 'Énergie'},
    'water' : {'table': 'daily_water',  'value_col': 'conso_m3',    'unit': 'm³',  'label': 'Eau'},
    'gas'   : {'table': 'daily_gas',    'value_col': 'conso_m3',    'unit': 'm³',  'label': 'Gaz'},
    'fuel'  : {'table': 'daily_fuel',   'value_col': 'consumption', 'unit': 'L',   'label': 'Carburant'},
}

# 0 = aujourd'hui uniquement (courbe horaire du jour, comme un relevé "temps réel"
# glissant) ; au-delà de 48h la courbe passe en granularité journalière.
_PERIOD_DAYS = {'24h': 0, '48h': 1, '7j': 6, '30j': 29, '60j': 59, '90j': 89}
_MAX_SERIES  = 6  # comparaison lisible sur un seul graphique


def _consumption_trend_impl(domain: str, period: str, device: str, zone: str) -> str:
    t0   = time.time()
    tool = f'{domain}_trend'
    period = (period or '24h').lower().strip()
    device = (device or '').strip()
    zone   = (zone or '').strip()
    logger.info('[%s] period=%s device=%r zone=%r', tool, period, device, zone)

    cfg = _DOMAIN_CONFIG[domain]
    if period not in _PERIOD_DAYS:
        return err(tool, f'Période invalide : {period!r}',
                   f"Valeurs acceptées : {', '.join(_PERIOD_DAYS)}")

    hourly    = period in ('24h', '48h')
    days_back = _PERIOD_DAYS[period]
    table     = cfg['table']
    value_col = cfg['value_col']

    # Filtre sur le même libellé que celui affiché (COALESCE) — sinon un capteur
    # non enregistré dans `device` (nom de repli "Capteur-<id>") ne matcherait
    # jamais, alors que c'est précisément le nom vu par l'utilisateur/le LLM.
    where  = ['dt.`date` >= CURDATE() - INTERVAL :days DAY']
    params: dict = {'days': days_back}
    if device:
        where.append("COALESCE(d.nom, CONCAT('Capteur-', dt.device_id)) LIKE :device")
        params['device'] = f'%{device}%'
    if zone:
        where.append("COALESCE(e.nom, 'Zone inconnue') LIKE :zone")
        params['zone'] = f'%{zone}%'
    where_sql = ' AND '.join(where)

    label_expr = "CONCAT(LPAD(dt.hour,2,'0'), 'h')" if hourly else "DATE_FORMAT(dt.`date`, '%d/%m')"
    group_cols = 'dt.device_id, d.nom, e.nom, dt.`date`' + (', dt.hour' if hourly else '')
    order_cols = 'dt.`date`' + (', dt.hour' if hourly else '')

    try:
        sql = text(f"""
            SELECT
                COALESCE(d.nom, CONCAT('Capteur-', dt.device_id)) AS capteur_nom,
                COALESCE(e.nom, 'Zone inconnue')                   AS zone,
                {label_expr}                                       AS bucket_label,
                ROUND(SUM(dt.`{value_col}`), 3)                    AS value
            FROM `{table}` dt
            LEFT JOIN device d ON d.adresse = dt.device_id
            LEFT JOIN espace e ON e.id = d.id_espace
            WHERE {where_sql}
            GROUP BY {group_cols}
            ORDER BY capteur_nom, {order_cols}
        """)
        with engine.connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, params).mappings().fetchall()]
    except Exception as e:
        logger.error('[%s] Exception: %s', tool, e, exc_info=True)
        return err(tool, str(e))

    if not rows:
        return err(tool, f"Aucune donnée {cfg['label'].lower()} pour cette période/filtre",
                   'Vérifiez le nom du capteur/zone ou essayez une période plus large')

    series_map: dict[str, dict] = {}
    for r in rows:
        key = r['capteur_nom']
        s = series_map.setdefault(key, {'device': key, 'zone': r['zone'], 'total': 0.0, 'points': []})
        v = float(r['value'] or 0)
        s['points'].append({'t': r['bucket_label'], 'v': v})
        s['total'] += v

    all_series = sorted(series_map.values(), key=lambda s: s['total'], reverse=True)
    truncated  = len(all_series) > _MAX_SERIES
    series     = all_series[:_MAX_SERIES]
    for s in series:
        s.pop('total', None)

    return ok({
        'domain':      domain,
        'label':       cfg['label'],
        'period':      period,
        'granularity': 'hour' if hourly else 'day',
        'unit':        cfg['unit'],
        'series':      series,
        'truncated':   truncated,
        'duration':    round(time.time() - t0, 3),
    })


def wm_trend(period: str = '24h', device: str = '', zone: str = '') -> str:
    """
    Courbe de consommation eau dans le temps — évolution horaire (jour courant)
    ou journalière (période plus longue) d'un compteur spécifique, ou
    comparaison de plusieurs compteurs sur le même graphique.

    period : '24h' (courbe horaire du jour) | '48h' | '7j' | '30j' | '60j' | '90j'
    device : nom (ou partie du nom) du capteur à isoler — vide = compare
             automatiquement les compteurs les plus consommateurs
    zone   : nom (ou partie du nom) de la zone/espace pour comparer un groupe
             de compteurs (ex: tous les compteurs d'un bâtiment)
    """
    return _consumption_trend_impl('water', period, device, zone)


def energy_trend(period: str = '24h', device: str = '', zone: str = '') -> str:
    """
    Courbe de consommation électrique dans le temps (toutes phases L1/L2/L3
    cumulées) — évolution horaire (jour courant) ou journalière (période plus
    longue) d'un compteur spécifique, ou comparaison de plusieurs compteurs.

    period : '24h' (courbe horaire du jour) | '48h' | '7j' | '30j' | '60j' | '90j'
    device : nom (ou partie du nom) du capteur à isoler — vide = compare
             automatiquement les compteurs les plus consommateurs
    zone   : nom (ou partie du nom) de la zone/espace pour comparer un groupe
             de compteurs (ex: tous les compteurs d'un bâtiment)
    """
    return _consumption_trend_impl('energy', period, device, zone)


def gm_trend(period: str = '24h', device: str = '', zone: str = '') -> str:
    """
    Courbe de consommation gaz dans le temps — évolution horaire (jour courant)
    ou journalière (période plus longue) d'un compteur spécifique, ou
    comparaison de plusieurs compteurs sur le même graphique.

    period : '24h' (courbe horaire du jour) | '48h' | '7j' | '30j' | '60j' | '90j'
    device : nom (ou partie du nom) du capteur à isoler — vide = compare
             automatiquement les compteurs les plus consommateurs
    zone   : nom (ou partie du nom) de la zone/espace pour comparer un groupe
             de compteurs (ex: tous les compteurs d'un bâtiment)
    """
    return _consumption_trend_impl('gas', period, device, zone)


def fuel_trend(period: str = '24h', device: str = '', zone: str = '') -> str:
    """
    Courbe de consommation carburant dans le temps — évolution horaire (jour
    courant) ou journalière (période plus longue) d'un véhicule spécifique, ou
    comparaison de plusieurs véhicules sur le même graphique.

    period : '24h' (courbe horaire du jour) | '48h' | '7j' | '30j' | '60j' | '90j'
    device : nom (ou partie du nom) du véhicule à isoler — vide = compare
             automatiquement les véhicules les plus consommateurs
    zone   : nom (ou partie du nom) de la zone/espace pour comparer un groupe
             de véhicules
    """
    return _consumption_trend_impl('fuel', period, device, zone)
