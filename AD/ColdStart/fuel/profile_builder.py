"""
Population profile builder for fuel cold start.

Fuel specifics
--------------
- Distribution bimodale : 0 (garé) ou ~3-10 L/h (en route)
- Offline rate : ~46% (nuit 20h-6h + weekend)
- Profil horaire : actif 6h-18h semaine, quasi-nul nuit/weekend
- Distribution active : quasi-normale (mean=5.24, std=1.99, max=10.35 L/h)
- 3 véhicules identiques → profil population très cohérent
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import FuelColdStartConfig

_log = get_logger(__name__)


@dataclass
class FuelSeriesProfile:
    item_id:         str
    value_col:       str
    n_points:        int
    pct_offline:     float
    mean:            float     # moyenne sur valeurs actives (conso > 0)
    std:             float
    min:             float
    q10:             float
    q25:             float
    q50:             float
    q75:             float
    q90:             float
    max:             float
    hourly_pattern:  list[float] = field(default_factory=lambda: [0.0] * 24)
    weekly_pattern:  list[float] = field(default_factory=lambda: [0.0] * 7)


@dataclass
class FuelPopulationProfile:
    value_col:        str
    n_devices:        int
    pop_mean:         float    # stats sur valeurs actives
    pop_std:          float
    pop_q10:          float
    pop_q25:          float
    pop_q50:          float
    pop_q75:          float
    pop_q90:          float
    pop_pct_offline:  float    # fraction heures garé (objectif : 46%)
    pop_max:          float    # max observé (10.35 L/h) — plafond physique
    hourly_mean:      list[float] = field(default_factory=lambda: [0.0] * 24)
    hourly_std:       list[float] = field(default_factory=lambda: [0.0] * 24)
    weekly_mean:      list[float] = field(default_factory=lambda: [0.0] * 7)
    weekly_std:       list[float] = field(default_factory=lambda: [0.0] * 7)
    device_profiles:  list[FuelSeriesProfile] = field(default_factory=list)

    def to_json(self, path: Union[str, Path]) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def from_json(cls, path: Union[str, Path]) -> "FuelPopulationProfile":
        raw      = json.loads(Path(path).read_text(encoding="utf-8"))
        profiles = [FuelSeriesProfile(**p) for p in raw.pop("device_profiles", [])]
        instance = cls(**raw)
        instance.device_profiles = profiles
        return instance


def _correct_outliers(
    series: pd.Series, item_id: str, col: str, factor: float, ffill_limit: int,
) -> pd.Series:
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
        _log.warning("[%s][%s] %d outlier(s) (val > %.2f) -> NaN", item_id, col, len(hits), fence)
        series = series.copy()
        series.loc[hits] = np.nan
        series = series.interpolate(method="linear", limit=ffill_limit)
    return series


def load_population_data(config: FuelColdStartConfig) -> pd.DataFrame:
    path = Path(config.population_data_path)
    if not path.exists():
        raise FileNotFoundError(f"Population data not found: {path}")

    df = pd.read_csv(path, parse_dates=[config.timestamp_col])

    horizon = pd.Timestamp.now() + pd.Timedelta(days=30)
    bad = df[config.timestamp_col] > horizon
    if bad.any():
        df = df[~bad].copy()

    if config.date_debut:
        df = df[df[config.timestamp_col] >= pd.Timestamp(config.date_debut)]
    if config.date_fin:
        df = df[
            df[config.timestamp_col]
            <= pd.Timestamp(config.date_fin) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        ]

    df = df.sort_values([config.device_col, config.timestamp_col]).reset_index(drop=True)
    df[config.item_col] = df[config.device_col].astype(str)

    # Exclure le nouveau device de la population
    df = df[df[config.item_col] != str(config.new_device_id)].copy()

    col = config.value_col

    # ── Filtres qualité ───────────────────────────────────────────────────
    counts      = df.groupby(config.item_col)[col].count()
    too_few     = set(counts[counts < config.min_device_rows].index)
    pct_zero    = df.groupby(config.item_col)[col].apply(lambda x: (x == 0).mean())
    too_offline = set(pct_zero[pct_zero >= config.max_pct_offline].index)
    excluded    = sorted(too_few | too_offline)
    if excluded:
        _log.warning("Devices exclus (%d) : %s", len(excluded), excluded)
        df = df[~df[config.item_col].isin(excluded)].copy()

    if df.empty:
        raise ValueError("Aucun device valide dans la population.")

    # ── Correction outliers ───────────────────────────────────────────────
    value_cols = [c for c in config.value_cols if c in df.columns]
    for vc in value_cols:
        neg = df[vc] < 0
        if neg.any():
            df.loc[neg, vc] = 0.0
        chunks = []
        for iid, grp in df.groupby(config.item_col):
            s = _correct_outliers(grp[vc], str(iid), vc, config.rollover_iqr_factor, config.ffill_limit)
            chunks.append(s)
        df[vc] = pd.concat(chunks).reindex(df.index)

    # ── Resample grille horaire ────────────────────────────────────────────
    resampled = []
    for iid, grp in df.groupby(config.item_col):
        g = grp.set_index(config.timestamp_col)[value_cols].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()
            .ffill(limit=config.ffill_limit)
            .fillna(0.0)
            .reset_index()
        )
        g[config.item_col]   = iid
        g[config.device_col] = iid
        resampled.append(g)

    result = pd.concat(resampled, ignore_index=True)
    _log.info(
        "Population fuel chargee : %d vehicules, %d points — %s",
        result[config.item_col].nunique(), len(result),
        sorted(result[config.item_col].unique()),
    )
    return result


def _compute_fuel_series_profile(
    series: pd.Series, ts_index: pd.DatetimeIndex, item_id: str, col: str,
) -> FuelSeriesProfile:
    all_vals = series.dropna().values
    if len(all_vals) == 0:
        return FuelSeriesProfile(
            item_id=item_id, value_col=col, n_points=0, pct_offline=1.0,
            mean=0, std=1, min=0, q10=0, q25=0, q50=0, q75=0, q90=0, max=0,
        )

    pct_offline = float((all_vals == 0).mean())

    # Stats calculées sur les valeurs ACTIVES uniquement (véhicule en route)
    active = all_vals[all_vals > 0]
    if len(active) == 0:
        active = all_vals

    s_clean = series.dropna()
    hourly  = (
        s_clean.groupby(ts_index[series.notna()].hour).mean()
        .reindex(range(24), fill_value=float(np.nanmean(all_vals)))
        .tolist()
    )
    weekly  = (
        s_clean.groupby(ts_index[series.notna()].dayofweek).mean()
        .reindex(range(7), fill_value=float(np.nanmean(all_vals)))
        .tolist()
    )

    return FuelSeriesProfile(
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
    df: pd.DataFrame, config: FuelColdStartConfig, col: str | None = None,
) -> FuelPopulationProfile:
    if col is None:
        col = config.value_col

    if col not in df.columns:
        raise ValueError(
            f"Colonne '{col}' introuvable.\n"
            f"Colonnes disponibles : {sorted(df.columns.tolist())}"
        )

    series_profiles: list[FuelSeriesProfile] = []
    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col).sort_index()
        if col not in g.columns or g[col].dropna().empty:
            _log.warning("[%s] colonne '%s' vide — vehicle ignore", item_id, col)
            continue
        profile = _compute_fuel_series_profile(
            series   = g[col],
            ts_index = pd.DatetimeIndex(g.index),
            item_id  = str(item_id),
            col      = col,
        )
        series_profiles.append(profile)

    n = len(series_profiles)
    if n < config.profile_min_devices:
        raise ValueError(
            f"Seulement {n} vehicle(s) valide(s), minimum requis : {config.profile_min_devices}."
        )

    means        = np.array([p.mean        for p in series_profiles])
    stds         = np.array([p.std         for p in series_profiles])
    q10s         = np.array([p.q10         for p in series_profiles])
    q25s         = np.array([p.q25         for p in series_profiles])
    q50s         = np.array([p.q50         for p in series_profiles])
    q75s         = np.array([p.q75         for p in series_profiles])
    q90s         = np.array([p.q90         for p in series_profiles])
    maxs         = np.array([p.max         for p in series_profiles])
    pct_offlines = np.array([p.pct_offline for p in series_profiles])

    hourly_matrix = np.array([p.hourly_pattern for p in series_profiles])
    weekly_matrix = np.array([p.weekly_pattern for p in series_profiles])

    pop = FuelPopulationProfile(
        value_col        = col,
        n_devices        = n,
        pop_mean         = float(np.mean(means)),
        pop_std          = float(np.mean(stds)),
        pop_q10          = float(np.mean(q10s)),
        pop_q25          = float(np.mean(q25s)),
        pop_q50          = float(np.mean(q50s)),
        pop_q75          = float(np.mean(q75s)),
        pop_q90          = float(np.mean(q90s)),
        pop_max          = float(np.max(maxs)),
        pop_pct_offline  = float(np.mean(pct_offlines)),
        hourly_mean      = hourly_matrix.mean(axis=0).tolist(),
        hourly_std       = hourly_matrix.std(axis=0).tolist() if n > 1 else [0.0] * 24,
        weekly_mean      = weekly_matrix.mean(axis=0).tolist(),
        weekly_std       = weekly_matrix.std(axis=0).tolist() if n > 1 else [0.0] * 7,
        device_profiles  = series_profiles,
    )

    _log.info(
        "Profil population fuel '%s' — %d vehicules | "
        "mu_actif=%.3f  sigma=%.3f  q50=%.3f  max=%.3f  offline=%.1f%%",
        col, n,
        pop.pop_mean, pop.pop_std, pop.pop_q50, pop.pop_max,
        pop.pop_pct_offline * 100,
    )
    return pop
