"""
Agrégation horaire des DataFrames IoT → tables daily_* MySQL.
INSERT ON DUPLICATE KEY UPDATE pour l'idempotence complète.
"""
from __future__ import annotations

import logging
from datetime import date as Date
from typing import Optional

import pandas as pd
from sqlalchemy import text

logger = logging.getLogger('aria.pipeline.aggregator')


def _safe_float(val) -> Optional[float]:
    try:
        return None if pd.isna(val) else round(float(val), 4)
    except Exception:
        return None


def _upsert(engine, table: str, rows: list[dict], unique_cols: list[str]) -> int:
    if not rows:
        return 0
    cols       = list(rows[0].keys())
    col_list   = ', '.join(f'`{c}`' for c in cols)
    param_list = ', '.join(f':{c}' for c in cols)
    update_set = ', '.join(f'`{c}` = VALUES(`{c}`)' for c in cols if c not in unique_cols)
    sql = text(f"""
        INSERT INTO `{table}` ({col_list}) VALUES ({param_list})
        ON DUPLICATE KEY UPDATE {update_set}
    """)
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def _day_filter(df: pd.DataFrame, run_date: Date) -> pd.DataFrame:
    return df[df['date'].dt.date == run_date]


def aggregate_energy(engine, df: pd.DataFrame, run_date: Date) -> int:
    if df.empty:
        return 0

    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    day_df = _day_filter(df, run_date)
    if day_df.empty:
        logger.warning("aggregate_energy: aucune donnée pour %s", run_date)
        return 0

    rows = []
    for (device_id, phase, hour), grp in day_df.groupby(
        [day_df['id_device'], day_df['phase'], day_df['date'].dt.hour]
    ):
        rows.append({
            'device_id': str(device_id),
            'phase':     str(phase),
            'date':      run_date.isoformat(),
            'hour':      int(hour),
            'cons_en':   _safe_float(grp['cons_en'].sum()),
            'nb_mesures': int(len(grp)),
        })

    written = _upsert(engine, 'daily_energy', rows, ['device_id', 'phase', 'date', 'hour'])
    logger.info("aggregate_energy: %d lignes → daily_energy pour %s", written, run_date)
    return written


def aggregate_water(engine, df: pd.DataFrame, run_date: Date) -> int:
    if df.empty:
        return 0

    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    day_df = _day_filter(df, run_date)
    if day_df.empty:
        logger.warning("aggregate_water: aucune donnée pour %s", run_date)
        return 0

    has_conso  = 'conso'  in day_df.columns
    has_leak   = 'leak'   in day_df.columns
    has_fraud  = 'fraud'  in day_df.columns

    rows = []
    for (device_id, hour), grp in day_df.groupby(
        [day_df['id_device'], day_df['date'].dt.hour]
    ):
        conso_sum = grp['conso'].sum() if has_conso else None
        # forward_flow est en litres — conversion en m³
        conso_m3 = (conso_sum / 1000.0) if conso_sum is not None else None
        rows.append({
            'device_id': str(device_id),
            'date':      run_date.isoformat(),
            'hour':      int(hour),
            'conso_m3':  _safe_float(conso_m3),
            'nb_fuites': int(grp['leak'].sum())  if has_leak  else 0,
            'nb_fraudes': int(grp['fraud'].sum()) if has_fraud else 0,
            'is_offline': int(conso_sum == 0)    if has_conso else 0,
            'nb_mesures': int(len(grp)),
        })

    written = _upsert(engine, 'daily_water', rows, ['device_id', 'date', 'hour'])
    logger.info("aggregate_water: %d lignes → daily_water pour %s", written, run_date)
    return written


def aggregate_gas(engine, df: pd.DataFrame, run_date: Date) -> int:
    if df.empty:
        return 0

    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    day_df = _day_filter(df, run_date)
    if day_df.empty:
        logger.warning("aggregate_gas: aucune donnée pour %s", run_date)
        return 0

    has_conso  = 'conso'     in day_df.columns
    has_debit  = 'avg_debit' in day_df.columns
    has_leak   = 'leak'      in day_df.columns
    has_fraud  = 'fraud'     in day_df.columns

    rows = []
    for (device_id, hour), grp in day_df.groupby(
        [day_df['id_device'], day_df['date'].dt.hour]
    ):
        rows.append({
            'device_id': str(device_id),
            'date':      run_date.isoformat(),
            'hour':      int(hour),
            'conso_m3':  _safe_float(grp['conso'].sum() / 1000.0) if has_conso else None,
            'avg_debit': _safe_float(grp['avg_debit'].mean()) if has_debit else None,
            'nb_fuites': int(grp['leak'].sum())               if has_leak  else 0,
            'nb_fraudes': int(grp['fraud'].sum())             if has_fraud else 0,
            'nb_mesures': int(len(grp)),
        })

    written = _upsert(engine, 'daily_gas', rows, ['device_id', 'date', 'hour'])
    logger.info("aggregate_gas: %d lignes → daily_gas pour %s", written, run_date)
    return written


def aggregate_fuel(engine, df: pd.DataFrame, run_date: Date) -> int:
    if df.empty:
        return 0

    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    day_df = _day_filter(df, run_date)
    if day_df.empty:
        logger.warning("aggregate_fuel: aucune donnée pour %s", run_date)
        return 0

    has_level  = 'fuel_level'  in day_df.columns
    has_conso  = 'consommation' in day_df.columns
    has_speed  = 'vitesse'      in day_df.columns

    rows = []
    for (device_id, hour), grp in day_df.groupby(
        [day_df['id_device'], day_df['date'].dt.hour]
    ):
        rows.append({
            'device_id':   str(device_id),
            'date':        run_date.isoformat(),
            'hour':        int(hour),
            'fuel_level':  _safe_float(grp['fuel_level'].mean())   if has_level else None,
            'consumption': _safe_float(grp['consommation'].sum())  if has_conso else None,
            'avg_speed':   _safe_float(grp['vitesse'].mean())      if has_speed else None,
            'nb_mesures':  int(len(grp)),
        })

    written = _upsert(engine, 'daily_fuel', rows, ['device_id', 'date', 'hour'])
    logger.info("aggregate_fuel: %d lignes → daily_fuel pour %s", written, run_date)
    return written
