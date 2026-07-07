"""
Extraction de données IoT depuis MySQL → DataFrame par domaine.
Réutilise l'engine MCP (pool partagé, pas de double connexion).
Retourne des DataFrames au format attendu par HotStart.
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parents[3]))
from mcp_server.db.connection import engine, get_active_tables
from mcp_server.tools._helpers import (
    SENSOR_TABLE_PRIORITY,
    detect_date_col,
    get_active_col_names,
)

logger = logging.getLogger('aria.pipeline.extractor')

_DOMAIN_ALIAS = {'energy': 'en', 'water': 'wm', 'gas': 'gm', 'fuel': 'fuel'}


def _best_table(domain: str) -> Optional[str]:
    active = set(get_active_tables().keys())
    alias  = _DOMAIN_ALIAS.get(domain, domain)
    for t in SENSOR_TABLE_PRIORITY.get(alias, []):
        if t in active:
            return t
    return next((t for t in active if alias in t.lower()), None)


_SAFE_IDENT = re.compile(r'^[a-zA-Z0-9_]+$')

def _safe_ident(name: str, label: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Identifiant SQL invalide pour {label}: {name!r}")
    return name


def _fetch(table: str, select_cols: list[str], date_col: str, since: str) -> list[dict]:
    _safe_ident(table, 'table')
    _safe_ident(date_col, 'date_col')
    for col in select_cols:
        _safe_ident(col, 'colonne')
    cols_sql = ', '.join(f't.`{c}`' for c in select_cols)
    q = text(f"""
        SELECT {cols_sql}
        FROM `{table}` t
        WHERE t.`{date_col}` >= :since
        ORDER BY t.`{date_col}`
        LIMIT 100000
    """)
    with engine.connect() as conn:
        rows = conn.execute(q, {'since': since}).mappings().fetchall()
    return [dict(r) for r in rows]


def extract_energy(hours_back: int = 96) -> pd.DataFrame:
    """
    Format de sortie (long) pour HotStart:
    [date, id_device, phase, item_id, cons_en]
    """
    table = _best_table('energy')
    if not table:
        raise RuntimeError("Aucune table énergie disponible dans bw_samar")

    col_map  = get_active_col_names(table)
    date_col = detect_date_col(table)
    if not date_col:
        raise RuntimeError(f"Colonne date introuvable dans {table}")

    id_col = col_map.get('id_device', 'id_device')

    phase_map: dict[str, str] = {}
    for i in range(1, 4):
        key = f'en_l{i}'
        if key in col_map:
            phase_map[f'L{i}'] = col_map[key]

    if not phase_map:
        raise RuntimeError(f"Colonnes en_l1/l2/l3 introuvables dans {table}")

    since    = (datetime.utcnow() - timedelta(hours=hours_back)).strftime('%Y-%m-%d %H:%M:%S')
    all_cols = list(dict.fromkeys([id_col, date_col] + list(phase_map.values())))
    rows     = _fetch(table, all_cols, date_col, since)

    if not rows:
        return pd.DataFrame(columns=['date', 'id_device', 'phase', 'item_id', 'cons_en'])

    df_wide = pd.DataFrame(rows)
    df_wide.rename(columns={id_col: 'id_device', date_col: 'date'}, inplace=True)

    frames = []
    for phase, col_name in phase_map.items():
        if col_name not in df_wide.columns:
            continue
        tmp = df_wide[['id_device', 'date', col_name]].copy()
        tmp.rename(columns={col_name: 'cons_en'}, inplace=True)
        tmp['phase']   = phase
        tmp['item_id'] = tmp['id_device'].astype(str) + '_' + phase
        frames.append(tmp)

    if not frames:
        return pd.DataFrame(columns=['date', 'id_device', 'phase', 'item_id', 'cons_en'])

    result = pd.concat(frames, ignore_index=True)
    result['date'] = pd.to_datetime(result['date'])
    result.sort_values(['item_id', 'date'], inplace=True, ignore_index=True)
    logger.info("extract_energy: %d lignes, %d séries — source: %s", len(result), result['item_id'].nunique(), table)
    return result


def extract_water(hours_back: int = 96) -> pd.DataFrame:
    """
    Format de sortie pour HotStart:
    [date, id_device, item_id, conso, leak?, fraud?]
    """
    table = _best_table('water')
    if not table:
        raise RuntimeError("Aucune table eau disponible dans bw_samar")

    col_map  = get_active_col_names(table)
    date_col = detect_date_col(table)
    if not date_col:
        raise RuntimeError(f"Colonne date introuvable dans {table}")

    id_col    = col_map.get('id_device', 'id_device')
    value_key = 'forward_flow' if 'forward_flow' in col_map else 'index'
    value_col = col_map.get(value_key)
    if not value_col:
        raise RuntimeError(f"Colonne conso (forward_flow/index) introuvable dans {table}")

    select = list(dict.fromkeys([id_col, date_col, value_col]))
    if 'leak'  in col_map: select.append(col_map['leak'])
    if 'fraud' in col_map: select.append(col_map['fraud'])

    since = (datetime.now() - timedelta(hours=hours_back)).strftime('%Y-%m-%d %H:%M:%S')
    rows  = _fetch(table, select, date_col, since)

    if not rows:
        return pd.DataFrame(columns=['date', 'id_device', 'item_id', 'conso'])

    df = pd.DataFrame(rows)
    renames: dict = {id_col: 'id_device', date_col: 'date', value_col: 'conso'}
    if 'leak'  in col_map: renames[col_map['leak']]  = 'leak'
    if 'fraud' in col_map: renames[col_map['fraud']] = 'fraud'
    df.rename(columns=renames, inplace=True)

    df['date']    = pd.to_datetime(df['date'])
    df['item_id'] = df['id_device'].astype(str)
    df.sort_values(['id_device', 'date'], inplace=True, ignore_index=True)
    logger.info("extract_water: %d lignes, %d capteurs — source: %s", len(df), df['id_device'].nunique(), table)
    return df


def extract_gas(hours_back: int = 96) -> pd.DataFrame:
    """
    Format de sortie pour HotStart:
    [date, id_device, item_id, conso, avg_debit?, leak?, fraud?]
    """
    table = _best_table('gas')
    if not table:
        raise RuntimeError("Aucune table gaz disponible dans bw_samar")

    col_map  = get_active_col_names(table)
    date_col = detect_date_col(table)
    if not date_col:
        raise RuntimeError(f"Colonne date introuvable dans {table}")

    id_col    = col_map.get('id_device', 'id_device')
    value_key = next((k for k in ('forward_flow', 'avg_debit_per_min', 'index') if k in col_map), None)
    if not value_key:
        raise RuntimeError(f"Colonne conso gaz introuvable dans {table}: {list(col_map.keys())}")
    value_col = col_map[value_key]

    select = list(dict.fromkeys([id_col, date_col, value_col]))
    if 'avg_debit_per_min' in col_map: select.append(col_map['avg_debit_per_min'])
    if 'leak'              in col_map: select.append(col_map['leak'])
    if 'fraud'             in col_map: select.append(col_map['fraud'])

    since = (datetime.now() - timedelta(hours=hours_back)).strftime('%Y-%m-%d %H:%M:%S')
    rows  = _fetch(table, select, date_col, since)

    if not rows:
        return pd.DataFrame(columns=['date', 'id_device', 'item_id', 'conso'])

    df = pd.DataFrame(rows)
    renames: dict = {id_col: 'id_device', date_col: 'date', value_col: 'conso'}
    if 'avg_debit_per_min' in col_map: renames[col_map['avg_debit_per_min']] = 'avg_debit'
    if 'leak'              in col_map: renames[col_map['leak']]              = 'leak'
    if 'fraud'             in col_map: renames[col_map['fraud']]             = 'fraud'
    df.rename(columns=renames, inplace=True)

    df['date']    = pd.to_datetime(df['date'])
    df['item_id'] = df['id_device'].astype(str)
    df.sort_values(['id_device', 'date'], inplace=True, ignore_index=True)
    logger.info("extract_gas: %d lignes, %d capteurs — source: %s", len(df), df['id_device'].nunique(), table)
    return df


def extract_fuel(hours_back: int = 96) -> pd.DataFrame:
    """
    Format de sortie pour HotStart:
    [date, id_device, item_id, consommation?, vitesse?, fuel_level?]
    """
    table = _best_table('fuel')
    if not table:
        raise RuntimeError("Aucune table carburant disponible dans bw_samar")

    col_map  = get_active_col_names(table)
    date_col = detect_date_col(table)
    if not date_col:
        raise RuntimeError(f"Colonne date introuvable dans {table}")

    id_col      = col_map.get('id_device', 'id_device')
    conso_col   = col_map.get('consommation')
    vitesse_col = col_map.get('vitesse')
    fuel_col    = col_map.get('fuel_level') or col_map.get('niveau')

    select = list(dict.fromkeys(c for c in [id_col, date_col, conso_col, vitesse_col, fuel_col] if c))
    if len(select) < 3:
        raise RuntimeError(f"Colonnes carburant insuffisantes dans {table}: {list(col_map.keys())}")

    since = (datetime.now() - timedelta(hours=hours_back)).strftime('%Y-%m-%d %H:%M:%S')
    rows  = _fetch(table, select, date_col, since)

    if not rows:
        return pd.DataFrame(columns=['date', 'id_device', 'item_id'])

    df = pd.DataFrame(rows)
    renames: dict = {id_col: 'id_device', date_col: 'date'}
    if conso_col:   renames[conso_col]   = 'consommation'
    if vitesse_col: renames[vitesse_col] = 'vitesse'
    if fuel_col:    renames[fuel_col]    = 'fuel_level'
    df.rename(columns=renames, inplace=True)

    df['date']    = pd.to_datetime(df['date'])
    df['item_id'] = df['id_device'].astype(str)
    df.sort_values(['id_device', 'date'], inplace=True, ignore_index=True)
    logger.info("extract_fuel: %d lignes, %d véhicules — source: %s", len(df), df['id_device'].nunique(), table)
    return df
