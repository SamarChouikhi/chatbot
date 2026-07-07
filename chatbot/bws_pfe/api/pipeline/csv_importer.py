"""
Importe des données CSV dans les tables daily_* de bw_samar.
Réutilise les fonctions aggregate_* du pipeline pour une cohérence totale.

Formats CSV acceptés pour energy :
  - Long  : date, id_device, phase (L1/L2/L3), cons_en
  - Large : date, id_device, cons_en_L1, cons_en_L2, cons_en_L3 [, cons_en_L4…]
            (converti automatiquement en format long avant agrégation)
Autres domaines :
  water : date, id_device, conso  [+ leak / fraud optionnels]
  gas   : date, id_device, conso  [+ avg_debit_per_min optionnel]
  fuel  : date, id_device         [+ consommation / vitesse / fuel_level]

Les noms de colonnes exacts sont flexibles — voir _COL_ALIASES.
"""
from __future__ import annotations

import logging
import re
from datetime import date as Date
from pathlib import Path
from typing import Literal

import pandas as pd

logger = logging.getLogger('aria.pipeline.csv_importer')

Domain = Literal['energy', 'water', 'gas', 'fuel']

# Candidats de noms de colonnes par domaine, par ordre de priorité.
_COL_ALIASES: dict[str, dict[str, list[str]]] = {
    'energy': {
        'date':      ['date', 'timestamp', 'ts', 'datetime', 'time'],
        'id_device': ['id_device', 'device_id', 'device', 'id'],
        'phase':     ['phase', 'phases'],
        'cons_en':   ['cons_en', 'consumption', 'conso', 'energy', 'kwh', 'kWh', 'value'],
    },
    'water': {
        'date':      ['date', 'timestamp', 'ts', 'datetime', 'time'],
        'id_device': ['id_device', 'device_id', 'device', 'id'],
        'conso':     ['conso', 'forward_flow', 'consumption', 'volume', 'flow', 'm3', 'value'],
        'leak':      ['leak', 'fuite', 'leakage'],
        'fraud':     ['fraud', 'fraude'],
    },
    'gas': {
        'date':      ['date', 'timestamp', 'ts', 'datetime', 'time'],
        'id_device': ['id_device', 'device_id', 'device', 'id'],
        'conso':     ['conso', 'forward_flow', 'consumption', 'volume', 'm3', 'value'],
        'avg_debit': ['avg_debit', 'avg_debit_per_min', 'debit', 'flow_rate'],
        'leak':      ['leak', 'fuite', 'leakage'],
        'fraud':     ['fraud', 'fraude'],
    },
    'fuel': {
        'date':         ['date', 'timestamp', 'ts', 'datetime', 'time'],
        'id_device':    ['id_device', 'device_id', 'device', 'id'],
        'consommation': ['consommation', 'consumption', 'conso', 'fuel_consumption', 'value'],
        'vitesse':      ['vitesse', 'speed', 'avg_speed', 'velocity'],
        'fuel_level':   ['fuel_level', 'niveau', 'level', 'tank_level'],
    },
}

_WIDE_ENERGY_RE = re.compile(r'^cons_en_(L\d+)$', re.IGNORECASE)


def _reshape_energy_wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convertit un CSV énergie en format large (cons_en_L1, cons_en_L2…)
    vers le format long (phase, cons_en) attendu par aggregate_energy.
    Retourne df inchangé si déjà en format long.
    """
    phase_cols = {
        m.group(1).upper(): col
        for col in df.columns
        if (m := _WIDE_ENERGY_RE.match(col))
    }
    if not phase_cols:
        return df  # déjà en format long

    base_cols = [c for c in ('date', 'id_device') if c in df.columns]
    frames = []
    for phase, col in sorted(phase_cols.items()):
        tmp = df[base_cols + [col]].copy()
        tmp.rename(columns={col: 'cons_en'}, inplace=True)
        tmp['phase'] = phase
        frames.append(tmp)

    result = pd.concat(frames, ignore_index=True)
    logger.info(
        "[CSV→DB] Reshape énergie : format large → long (%d phases : %s)",
        len(phase_cols), sorted(phase_cols),
    )
    return result


_REQUIRED_COLS: dict[str, set[str]] = {
    'energy': {'date', 'id_device', 'phase', 'cons_en'},
    'water':  {'date', 'id_device', 'conso'},
    'gas':    {'date', 'id_device', 'conso'},
    'fuel':   {'date', 'id_device'},
}


def _resolve_columns(df: pd.DataFrame, aliases: dict[str, list[str]]) -> dict[str, str]:
    """Retourne {canonical_name: actual_col_in_df} pour les colonnes trouvées."""
    lower_cols = {c.lower(): c for c in df.columns}
    mapping: dict[str, str] = {}
    for canonical, candidates in aliases.items():
        for cand in candidates:
            if cand in df.columns:
                mapping[canonical] = cand
                break
            if cand.lower() in lower_cols:
                mapping[canonical] = lower_cols[cand.lower()]
                break
    return mapping


def import_csv(engine, csv_path: str | Path, domain: Domain) -> dict:
    """
    Importe un CSV dans les tables daily_* de bw_samar.

    Returns:
        {domain, source_file, dates_processed, rows_inserted, first_date, last_date}
    Raises:
        FileNotFoundError  — fichier introuvable
        ValueError         — domaine invalide ou colonnes manquantes
    """
    from api.pipeline.aggregator import (
        aggregate_energy, aggregate_water, aggregate_gas, aggregate_fuel,
    )

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {csv_path}")

    if domain not in _COL_ALIASES:
        raise ValueError(
            f"Domaine inconnu : {domain!r}. Valeurs acceptées : {list(_COL_ALIASES)}"
        )

    logger.info("[CSV→DB] Chargement %s (%s)...", csv_path.name, domain)

    header       = pd.read_csv(csv_path, nrows=0).columns.tolist()
    date_cands   = [c for c in header if c.lower() in ('date', 'timestamp', 'ts', 'datetime', 'time')]
    df_raw       = pd.read_csv(csv_path, parse_dates=date_cands or False)

    logger.info("[CSV→DB] %d lignes | colonnes : %s", len(df_raw), list(df_raw.columns))

    # Pour l'énergie en format large, convertir d'abord wide → long
    if domain == 'energy':
        df_raw = _reshape_energy_wide_to_long(df_raw)

    col_map = _resolve_columns(df_raw, _COL_ALIASES[domain])
    missing = _REQUIRED_COLS[domain] - set(col_map.keys())
    if missing:
        raise ValueError(
            f"Colonnes requises introuvables pour le domaine '{domain}' : {missing}\n"
            f"Colonnes disponibles dans le CSV : {list(df_raw.columns)}\n"
            f"Colonnes détectées : {col_map}"
        )

    # Renommage vers les noms canoniques attendus par les aggregators
    rename = {actual: canonical for canonical, actual in col_map.items()}
    df     = df_raw.rename(columns=rename).copy()
    df['date'] = pd.to_datetime(df['date'])

    dates_in_csv = sorted(df['date'].dt.date.unique())
    logger.info("[CSV→DB] %d dates distinctes à traiter", len(dates_in_csv))

    _AGG = {
        'energy': aggregate_energy,
        'water':  aggregate_water,
        'gas':    aggregate_gas,
        'fuel':   aggregate_fuel,
    }
    agg_fn = _AGG[domain]

    total_rows      = 0
    processed_dates = []

    for run_date in dates_in_csv:
        try:
            n = agg_fn(engine, df, run_date)
            total_rows += n
            processed_dates.append(str(run_date))
        except Exception as exc:
            logger.error("[CSV→DB] %s / %s : %s", domain, run_date, exc)

    logger.info(
        "[CSV→DB] Terminé — domaine=%s | %d/%d dates | %d lignes insérées",
        domain, len(processed_dates), len(dates_in_csv), total_rows,
    )
    return {
        'domain':          domain,
        'source_file':     csv_path.name,
        'dates_processed': len(processed_dates),
        'rows_inserted':   total_rows,
        'first_date':      processed_dates[0]  if processed_dates else None,
        'last_date':       processed_dates[-1] if processed_dates else None,
    }


def import_all_from_config(engine) -> dict:
    """
    Importe les 4 CSV référencés dans les config.yaml AD/HotStart/<domain>/config.yaml.
    Utile pour la migration initiale.

    Returns:
        {domain: {status, ...}}
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML requis : pip install pyyaml")

    _AD_DIR = Path(__file__).parents[4] / 'AD'
    _CONFIG_PATHS: dict[str, Path] = {
        'energy': _AD_DIR / 'HotStart' / 'energy' / 'config.yaml',
        'water':  _AD_DIR / 'HotStart' / 'water'  / 'config.yaml',
        'gas':    _AD_DIR / 'HotStart' / 'gaz'    / 'config.yaml',
        'fuel':   _AD_DIR / 'HotStart' / 'fuel'   / 'config.yaml',
    }

    results: dict = {}
    for domain, config_path in _CONFIG_PATHS.items():
        if not config_path.exists():
            logger.warning("[CSV→DB] config.yaml introuvable : %s — skip", config_path)
            results[domain] = {'status': 'skipped', 'reason': 'config_not_found'}
            continue
        try:
            with open(config_path, encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            csv_path = Path(cfg['donnees']['fichier'])
            if not csv_path.exists():
                logger.warning("[CSV→DB] CSV introuvable : %s — skip", csv_path)
                results[domain] = {'status': 'skipped', 'reason': 'file_not_found', 'path': str(csv_path)}
                continue
            result = import_csv(engine, csv_path, domain)
            results[domain] = {'status': 'ok', **result}
        except Exception as exc:
            logger.error("[CSV→DB] Erreur domaine %s : %s", domain, exc)
            results[domain] = {'status': 'error', 'error': str(exc)}

    return results
