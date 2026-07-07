from __future__ import annotations

import numpy as np
import pandas as pd

from .config import WaterConfig


def load_water_data(config: WaterConfig) -> pd.DataFrame:
    from common.logger import get_logger
    _log = get_logger(__name__)

    df = pd.read_csv(config.data_path, parse_dates=[config.timestamp_col])

    # Sanitisation : timestamps au-delà de aujourd'hui+30j sont des données corrompues
    horizon = pd.Timestamp.now() + pd.Timedelta(days=30)
    future_mask = df[config.timestamp_col] > horizon
    if future_mask.any():
        _log.warning(
            "%d ligne(s) avec timestamp corrompu (> %s) supprimées — "
            "plage corrompue : %s → %s",
            future_mask.sum(),
            horizon.date(),
            df.loc[future_mask, config.timestamp_col].min(),
            df.loc[future_mask, config.timestamp_col].max(),
        )
        df = df[~future_mask].copy()

    if config.date_debut:
        df = df[df[config.timestamp_col] >= pd.Timestamp(config.date_debut)]
    if config.date_fin:
        df = df[
            df[config.timestamp_col]
            <= pd.Timestamp(config.date_fin) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        ]

    df = df.sort_values([config.device_col, config.timestamp_col]).reset_index(drop=True)

    # item_id = id_device (pas de dimension phase pour l'eau)
    df[config.item_col] = df[config.device_col].astype(str)
    return df


def clean_water_data(df: pd.DataFrame, config: WaterConfig) -> pd.DataFrame:
    from common.logger import get_logger
    _log = get_logger(__name__)

    df = df.copy()

    # ── Correction 1 : devices avec données insuffisantes ou trop offline ─
    # 1a — trop peu de lignes : Chronos ne peut pas tourner de façon fiable
    counts  = df.groupby(config.item_col)[config.value_col].count()
    valid   = set(counts[counts >= config.min_device_rows].index)
    excl_rows = sorted(set(df[config.item_col].unique()) - valid)
    if excl_rows:
        _log.warning(
            "Devices exclus (< %d lignes brutes) : %s",
            config.min_device_rows, excl_rows,
        )

    # 1b — trop de zéros (compteur inactif) : aucun signal à analyser
    pct_zero = df.groupby(config.item_col)[config.value_col].apply(
        lambda x: (x == 0).mean()
    )
    excl_offline = sorted(pct_zero[pct_zero >= config.max_pct_offline].index)
    if excl_offline:
        _log.warning(
            "Devices exclus (>= %.0f%% offline) : %s",
            config.max_pct_offline * 100, excl_offline,
        )

    excluded = sorted(set(excl_rows) | set(excl_offline))
    if excluded:
        df = df[~df[config.item_col].isin(excluded)].copy()

    # ── Correction 2 : rollovers compteur (pics extrêmes positifs) ────────
    # Méthode : pour chaque device, IQR calculé sur les valeurs positives hors top-5%
    # (robuste aux quelques rollovers présents). Fence = Q3_trim + factor × IQR_trim.
    # Calibré sur les données : catch 1568 (24 M), 1501 (336 k), 3027 (516 k).
    for col in config.value_cols:
        if col not in df.columns:
            continue
        rollover_idx: list[int] = []
        for item_id, grp in df.groupby(config.item_col):
            pos = grp.loc[grp[col] > 0, col]
            if len(pos) < 8:
                continue
            trim  = pos[pos <= pos.quantile(0.95)]
            if len(trim) < 4:
                continue
            q3    = float(trim.quantile(0.75))
            iqr   = float(trim.quantile(0.75) - trim.quantile(0.25))
            if iqr < 1e-9:
                continue
            fence = q3 + config.rollover_iqr_factor * iqr
            hits  = grp.index[grp[col] > fence].tolist()
            if hits:
                _log.warning(
                    "[%s][%s] %d rollover(s) détecté(s) (val > %.0f) → NaN + interpolation",
                    item_id, col, len(hits), fence,
                )
                rollover_idx.extend(hits)

        if rollover_idx:
            df.loc[rollover_idx, col] = np.nan
            df[col] = df.groupby(config.item_col)[col].transform(
                lambda x: x.interpolate(method="linear", limit=config.ffill_limit)
            )

    # ── Correction 3 : valeurs négatives ──────────────────────────────────
    # Impossibles physiquement (compteur d'eau ne peut pas avoir conso < 0).
    # → NaN + interpolation linéaire (≤ ffill_limit heures consécutives).
    for col in config.value_cols:
        if col not in df.columns:
            continue
        neg_mask = df[col] < 0
        if neg_mask.any():
            _log.warning(
                "[%s] %d valeur(s) négative(s) → NaN + interpolation",
                col, int(neg_mask.sum()),
            )
            df.loc[neg_mask, col] = np.nan
            df[col] = df.groupby(config.item_col)[col].transform(
                lambda x: x.interpolate(method="linear", limit=config.ffill_limit)
            )

    # ── Marquage offline (conso == 0) ─────────────────────────────────────
    # Information utile conservée — le détecteur exclut ces points du scoring.
    df["is_offline"] = df[config.value_col] == 0

    # ── Suppression des NaN non récupérables ──────────────────────────────
    # Trou > ffill_limit heures consécutives → aucune interpolation possible.
    before  = len(df)
    df      = df.dropna(subset=[config.value_col])
    dropped = before - len(df)
    if dropped:
        _log.info(
            "%d ligne(s) supprimées — trou > %dh non interpolable dans '%s'",
            dropped, config.ffill_limit, config.value_col,
        )

    return df


def resample_water(df: pd.DataFrame, config: WaterConfig) -> pd.DataFrame:
    # Chronos exige une grille temporelle régulière — on resamples par device
    cols_to_resample = [c for c in config.value_cols if c in df.columns]
    resampled = []
    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col)[cols_to_resample].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()
            .ffill(limit=config.ffill_limit)
            .reset_index()
        )
        g[config.item_col]  = item_id
        g[config.device_col] = item_id
        resampled.append(g)
    return pd.concat(resampled, ignore_index=True)
