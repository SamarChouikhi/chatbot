from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import WaterColdStartConfig

_log = get_logger(__name__)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class WaterSeriesProfile:
    """Statistical fingerprint of one water device time series."""
    item_id:          str
    value_col:        str
    n_points:         int
    pct_offline:      float   # fraction of zero values (device offline)
    mean:             float   # mean of non-zero values
    std:              float
    min:              float
    q10:              float
    q25:              float
    q50:              float
    q75:              float
    q90:              float
    max:              float
    hourly_pattern:   list[float] = field(default_factory=lambda: [0.0] * 24)
    weekly_pattern:   list[float] = field(default_factory=lambda: [0.0] * 7)


@dataclass
class WaterPopulationProfile:
    """
    Aggregated statistics across all valid water devices.
    Drives synthetic generation and cold-start detector bootstrap.
    """
    value_col:      str
    n_devices:      int
    pop_mean:       float
    pop_std:        float
    pop_q10:        float
    pop_q25:        float
    pop_q50:        float
    pop_q75:        float
    pop_q90:        float
    pop_pct_offline: float          # typical offline fraction in the population
    hourly_mean:    list[float] = field(default_factory=lambda: [0.0] * 24)
    hourly_std:     list[float] = field(default_factory=lambda: [0.0] * 24)
    weekly_mean:    list[float] = field(default_factory=lambda: [0.0] * 7)
    weekly_std:     list[float] = field(default_factory=lambda: [0.0] * 7)
    device_profiles: list[WaterSeriesProfile] = field(default_factory=list)

    def to_json(self, path: Union[str, Path]) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def from_json(cls, path: Union[str, Path]) -> "WaterPopulationProfile":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        profiles = [WaterSeriesProfile(**p) for p in raw.pop("device_profiles", [])]
        instance = cls(**raw)
        instance.device_profiles = profiles
        return instance


# ── Rollover correction ───────────────────────────────────────────────────────

def _correct_rollovers(
    series:    pd.Series,
    item_id:   str,
    col:       str,
    factor:    float,
    ffill_limit: int,
) -> pd.Series:
    """
    Replace rollover spikes with NaN + linear interpolation.
    Fence = Q3_trim + factor × IQR_trim, computed on positive non-top-5% values.
    Mirrors the HotStart water preprocessor logic.
    """
    pos = series[series > 0]
    if len(pos) < 8:
        return series

    trim = pos[pos <= pos.quantile(0.95)]
    if len(trim) < 4:
        return series

    q3  = float(trim.quantile(0.75))
    iqr = float(trim.quantile(0.75) - trim.quantile(0.25))
    if iqr < 1e-9:
        return series

    fence = q3 + factor * iqr
    hits  = series.index[series > fence]
    if len(hits) > 0:
        _log.warning(
            "[%s][%s] %d rollover(s) corrigé(s) (val > %.0f)",
            item_id, col, len(hits), fence,
        )
        series = series.copy()
        series.loc[hits] = np.nan
        series = series.interpolate(method="linear", limit=ffill_limit)

    return series


# ── Population data loader ────────────────────────────────────────────────────

def load_population_data(config: WaterColdStartConfig) -> pd.DataFrame:
    """
    Load, sanitize, and resample the existing water devices CSV.
    Applies the same quality filters as HotStart water:
    - Remove corrupt future timestamps
    - Exclude devices with too few rows or too many offline hours
    - Correct rollover spikes
    """
    path = Path(config.population_data_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Population data not found: {path}\n"
            f"Set donnees.fichier_population in config.yaml."
        )

    df = pd.read_csv(path, parse_dates=[config.timestamp_col])

    # Sanitize corrupt future timestamps
    horizon = pd.Timestamp.now() + pd.Timedelta(days=30)
    bad = df[config.timestamp_col] > horizon
    if bad.any():
        _log.warning("%d ligne(s) timestamp corrompu supprimées", bad.sum())
        df = df[~bad].copy()

    if config.date_debut:
        df = df[df[config.timestamp_col] >= pd.Timestamp(config.date_debut)]
    if config.date_fin:
        df = df[
            df[config.timestamp_col]
            <= pd.Timestamp(config.date_fin) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        ]

    # Water: item_id = device_id (no phase dimension)
    df = df.sort_values([config.device_col, config.timestamp_col]).reset_index(drop=True)
    df[config.item_col] = df[config.device_col].astype(str)

    # Remove the new device from population to avoid contamination
    df = df[df[config.item_col] != str(config.new_device_id)].copy()

    col = config.value_col

    # ── Quality filters ────────────────────────────────────────────────────
    counts   = df.groupby(config.item_col)[col].count()
    too_few  = set(counts[counts < config.min_device_rows].index)

    pct_zero = df.groupby(config.item_col)[col].apply(lambda x: (x == 0).mean())
    too_offline = set(pct_zero[pct_zero >= config.max_pct_offline].index)

    excluded = sorted(too_few | too_offline)
    if excluded:
        _log.warning(
            "Devices exclus de la population (%d) : %s",
            len(excluded), excluded,
        )
        df = df[~df[config.item_col].isin(excluded)].copy()

    if df.empty:
        raise ValueError(
            "Aucun device valide dans la population après filtrage.\n"
            "Réduisez profil.min_lignes_device ou max_pct_offline dans config.yaml."
        )

    # ── Rollover correction + negative clamp ──────────────────────────────
    value_cols = [c for c in config.value_cols if c in df.columns]
    for vc in value_cols:
        neg_mask = df[vc] < 0
        if neg_mask.any():
            _log.warning("[pop][%s] %d valeur(s) négative(s) → NaN", vc, int(neg_mask.sum()))
            df.loc[neg_mask, vc] = np.nan

        corrected_chunks = []
        for item_id, grp in df.groupby(config.item_col):
            s = _correct_rollovers(
                grp[vc], str(item_id), vc,
                config.rollover_iqr_factor, config.ffill_limit,
            )
            corrected_chunks.append(s)
        df[vc] = pd.concat(corrected_chunks).reindex(df.index)

    # ── Resample to hourly grid ────────────────────────────────────────────
    resampled = []
    for item_id, grp in df.groupby(config.item_col):
        g = grp.set_index(config.timestamp_col)[value_cols].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()
            .ffill(limit=config.ffill_limit)
            .reset_index()
        )
        g[config.item_col]  = item_id
        g[config.device_col] = item_id
        resampled.append(g)

    result = pd.concat(resampled, ignore_index=True)
    _log.info(
        "Population eau chargée : %d devices, %d points — %s",
        result[config.item_col].nunique(),
        len(result),
        sorted(result[config.item_col].unique()),
    )
    return result


# ── Profile computation ───────────────────────────────────────────────────────

def _compute_water_series_profile(
    series:   pd.Series,
    ts_index: pd.DatetimeIndex,
    item_id:  str,
    col:      str,
) -> WaterSeriesProfile:
    all_vals = series.dropna().values
    if len(all_vals) == 0:
        return WaterSeriesProfile(
            item_id=item_id, value_col=col, n_points=0, pct_offline=1.0,
            mean=0, std=1, min=0, q10=0, q25=0, q50=0, q75=0, q90=0, max=0,
        )

    pct_offline = float((all_vals == 0).mean())

    # Stats computed on non-zero values to avoid offline-hours biasing the distribution
    active = all_vals[all_vals > 0]
    if len(active) == 0:
        active = all_vals   # all offline → use raw anyway

    # Hourly and weekly patterns include zeros (realistic for synthetic generation)
    s_clean = series.dropna()
    hourly = (
        s_clean.groupby(ts_index[series.notna()].hour).mean()
        .reindex(range(24), fill_value=float(np.nanmean(all_vals)))
        .tolist()
    )
    weekly = (
        s_clean.groupby(ts_index[series.notna()].dayofweek).mean()
        .reindex(range(7), fill_value=float(np.nanmean(all_vals)))
        .tolist()
    )

    return WaterSeriesProfile(
        item_id        = item_id,
        value_col      = col,
        n_points       = len(all_vals),
        pct_offline    = pct_offline,
        mean           = float(np.mean(active)),
        std            = float(np.std(active, ddof=1)) if len(active) > 1 else 0.0,
        min            = float(np.min(active)),
        q10            = float(np.percentile(active, 10)),
        q25            = float(np.percentile(active, 25)),
        q50            = float(np.percentile(active, 50)),
        q75            = float(np.percentile(active, 75)),
        q90            = float(np.percentile(active, 90)),
        max            = float(np.max(active)),
        hourly_pattern = hourly,
        weekly_pattern = weekly,
    )


def build_population_profile(
    df:     pd.DataFrame,
    config: WaterColdStartConfig,
    col:    str | None = None,
) -> WaterPopulationProfile:
    if col is None:
        col = config.value_col

    if col not in df.columns:
        raise ValueError(
            f"Colonne '{col}' introuvable dans les données de population.\n"
            f"Colonnes disponibles : {sorted(df.columns.tolist())}"
        )

    series_profiles: list[WaterSeriesProfile] = []

    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col).sort_index()
        if col not in g.columns or g[col].dropna().empty:
            _log.warning("[%s] colonne '%s' vide — device ignoré", item_id, col)
            continue
        profile = _compute_water_series_profile(
            series   = g[col],
            ts_index = pd.DatetimeIndex(g.index),
            item_id  = str(item_id),
            col      = col,
        )
        series_profiles.append(profile)

    n = len(series_profiles)
    if n < config.profile_min_devices:
        raise ValueError(
            f"Seulement {n} device(s) valide(s) dans la population, "
            f"minimum requis : {config.profile_min_devices}."
        )

    means        = np.array([p.mean        for p in series_profiles])
    stds         = np.array([p.std         for p in series_profiles])
    q10s         = np.array([p.q10         for p in series_profiles])
    q25s         = np.array([p.q25         for p in series_profiles])
    q50s         = np.array([p.q50         for p in series_profiles])
    q75s         = np.array([p.q75         for p in series_profiles])
    q90s         = np.array([p.q90         for p in series_profiles])
    pct_offlines = np.array([p.pct_offline for p in series_profiles])

    hourly_matrix = np.array([p.hourly_pattern for p in series_profiles])
    weekly_matrix = np.array([p.weekly_pattern for p in series_profiles])

    pop = WaterPopulationProfile(
        value_col       = col,
        n_devices       = n,
        pop_mean        = float(np.mean(means)),
        pop_std         = float(np.mean(stds)),
        pop_q10         = float(np.mean(q10s)),
        pop_q25         = float(np.mean(q25s)),
        pop_q50         = float(np.mean(q50s)),
        pop_q75         = float(np.mean(q75s)),
        pop_q90         = float(np.mean(q90s)),
        pop_pct_offline = float(np.mean(pct_offlines)),
        hourly_mean     = hourly_matrix.mean(axis=0).tolist(),
        hourly_std      = hourly_matrix.std(axis=0).tolist() if n > 1 else [0.0] * 24,
        weekly_mean     = weekly_matrix.mean(axis=0).tolist(),
        weekly_std      = weekly_matrix.std(axis=0).tolist() if n > 1 else [0.0] * 7,
        device_profiles = series_profiles,
    )

    _log.info(
        "Profil population eau '%s' — %d devices  |  μ_actif=%.3f  σ=%.3f  "
        "q50=%.3f  offline_moy=%.1f%%",
        col, n,
        pop.pop_mean, pop.pop_std, pop.pop_q50,
        pop.pop_pct_offline * 100,
    )
    return pop
