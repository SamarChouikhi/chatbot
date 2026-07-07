"""
Preprocessor for fuel HotStart.

Fuel specifics vs gaz/water:
  - Véhicule garé (nuit + weekend) = offline NORMAL → max_pct_offline=0.70
  - Pas de rollover compteur (consommation horaire, pas index cumulatif)
  - Valeurs négatives impossibles (consommation, vitesse >= 0)
  - Pas de colonne 'index' → pas de rollover IQR nécessaire sur consommation
  - Rollover appliqué uniquement comme protection sur outliers extrêmes
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FuelConfig


def load_fuel_data(config: FuelConfig) -> pd.DataFrame:
    from common.logger import get_logger
    _log = get_logger(__name__)

    df = pd.read_csv(config.data_path, parse_dates=[config.timestamp_col])

    horizon = pd.Timestamp.now() + pd.Timedelta(days=30)
    bad = df[config.timestamp_col] > horizon
    if bad.any():
        _log.warning("%d ligne(s) timestamp corrompu supprimees", bad.sum())
        df = df[~bad].copy()

    if config.date_debut:
        df = df[df[config.timestamp_col] >= pd.Timestamp(config.date_debut)]
    if config.date_fin:
        df = df[
            df[config.timestamp_col]
            <= pd.Timestamp(config.date_fin) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        ]

    df = df.sort_values([config.device_col, config.timestamp_col]).reset_index(drop=True)
    # Fuel : item_id = id_device (pas de phase)
    df[config.item_col] = df[config.device_col].astype(str)
    return df


def clean_fuel_data(df: pd.DataFrame, config: FuelConfig) -> pd.DataFrame:
    from common.logger import get_logger
    _log = get_logger(__name__)

    df = df.copy()

    # ── Devices avec trop peu de lignes ───────────────────────────────────
    counts    = df.groupby(config.item_col)[config.value_col].count()
    valid     = set(counts[counts >= config.min_device_rows].index)
    excl_rows = sorted(set(df[config.item_col].unique()) - valid)
    if excl_rows:
        _log.warning("Devices exclus (< %d lignes) : %s", config.min_device_rows, excl_rows)

    # ── Devices trop souvent offline (véhicule hors service) ─────────────
    pct_zero     = df.groupby(config.item_col)[config.value_col].apply(lambda x: (x == 0).mean())
    excl_offline = sorted(pct_zero[pct_zero >= config.max_pct_offline].index)
    if excl_offline:
        _log.warning(
            "Devices exclus (>= %.0f%% offline) : %s",
            config.max_pct_offline * 100, excl_offline,
        )

    excluded = sorted(set(excl_rows) | set(excl_offline))
    if excluded:
        df = df[~df[config.item_col].isin(excluded)].copy()

    # ── Outliers extrêmes (protection rollover) ───────────────────────────
    for col in config.value_cols:
        if col not in df.columns:
            continue
        for item_id, grp in df.groupby(config.item_col):
            pos = grp.loc[grp[col] > 0, col]
            if len(pos) < 8:
                continue
            trim = pos[pos <= pos.quantile(0.95)]
            if len(trim) < 4:
                continue
            q3  = float(trim.quantile(0.75))
            iqr = float(trim.quantile(0.75) - trim.quantile(0.25))
            if iqr < 1e-9:
                continue
            fence = q3 + config.rollover_iqr_factor * iqr
            hits  = grp.index[grp[col] > fence].tolist()
            if hits:
                _log.warning("[%s][%s] %d outlier(s) (val > %.1f) -> NaN", item_id, col, len(hits), fence)
                df.loc[hits, col] = np.nan
                df[col] = df.groupby(config.item_col)[col].transform(
                    lambda x: x.interpolate(method="linear", limit=config.ffill_limit)
                )

    # ── Valeurs négatives impossibles ─────────────────────────────────────
    for col in config.value_cols:
        if col not in df.columns:
            continue
        neg_mask = df[col] < 0
        if neg_mask.any():
            _log.warning("[%s] %d valeur(s) negative(s) -> 0", col, int(neg_mask.sum()))
            df.loc[neg_mask, col] = 0.0

    # ── Offline = véhicule garé (consommation == 0) ───────────────────────
    df["is_offline"] = df[config.value_col] == 0

    # ── Suppression NaN non récupérables ──────────────────────────────────
    before  = len(df)
    df      = df.dropna(subset=[config.value_col])
    dropped = before - len(df)
    if dropped:
        _log.info("%d ligne(s) supprimees (trou > %dh)", dropped, config.ffill_limit)

    return df


def resample_fuel(df: pd.DataFrame, config: FuelConfig) -> pd.DataFrame:
    """Resample to regular hourly grid per vehicle."""
    cols_to_resample = [c for c in config.value_cols if c in df.columns]
    resampled = []
    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col)[cols_to_resample].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()
            .ffill(limit=config.ffill_limit)
            .fillna(0.0)   # fuel : NaN restants = véhicule garé → 0
            .reset_index()
        )
        g[config.item_col]   = item_id
        g[config.device_col] = item_id
        resampled.append(g)
    return pd.concat(resampled, ignore_index=True)
