from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import ColdStartConfig

_log = get_logger(__name__)

_PHASE_RE    = re.compile(r'_(L\d+)$')
_KEEP_PHASES = frozenset(('L1', 'L2', 'L3'))


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class SeriesProfile:
    """Statistical fingerprint of a single time series (one device-phase pair)."""
    item_id:          str
    value_col:        str
    n_points:         int
    mean:             float
    std:              float
    min:              float
    q10:              float
    q25:              float
    q50:              float
    q75:              float
    q90:              float
    max:              float
    # Hourly seasonality pattern: 24-element array (mean value per hour-of-day)
    hourly_pattern:   list[float] = field(default_factory=lambda: [0.0] * 24)
    # Weekly pattern: 7-element array (mean value per day-of-week, 0=Monday)
    weekly_pattern:   list[float] = field(default_factory=lambda: [0.0] * 7)


@dataclass
class PopulationProfile:
    """
    Aggregated statistics computed across all existing devices.
    Used to generate synthetic data and bootstrap cold-start detectors
    for a new device that has no history.
    """
    value_col:       str
    n_devices:       int
    # Aggregate moments (mean of per-device stats)
    pop_mean:        float
    pop_std:         float
    pop_q10:         float
    pop_q25:         float
    pop_q50:         float
    pop_q75:         float
    pop_q90:         float
    # Per-hour-of-day mean and std (averaged across all devices)
    hourly_mean:     list[float] = field(default_factory=lambda: [0.0] * 24)
    hourly_std:      list[float] = field(default_factory=lambda: [0.0] * 24)
    # Per-day-of-week mean and std (0=Monday)
    weekly_mean:     list[float] = field(default_factory=lambda: [0.0] * 7)
    weekly_std:      list[float] = field(default_factory=lambda: [0.0] * 7)
    # Individual device profiles (for reference / outlier detection)
    device_profiles: list[SeriesProfile] = field(default_factory=list)

    def to_json(self, path: Union[str, Path]) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def from_json(cls, path: Union[str, Path]) -> "PopulationProfile":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        profiles = [SeriesProfile(**p) for p in raw.pop("device_profiles", [])]
        instance = cls(**raw)
        instance.device_profiles = profiles
        return instance


# ── Wide → long pivot (same logic as HotStart preprocessor) ──────────────────

def _is_wide_format(df: pd.DataFrame, phase_col: str) -> bool:
    return phase_col not in df.columns


def _wide_to_long(df: pd.DataFrame, config: ColdStartConfig) -> pd.DataFrame:
    fixed_cols = [col for col in df.columns if not _PHASE_RE.search(col)]
    phases = sorted({
        m.group(1)
        for col in df.columns
        if (m := _PHASE_RE.search(col)) and m.group(1) in _KEEP_PHASES
    })

    chunks: list[pd.DataFrame] = []
    for phase in phases:
        suffix = f'_{phase}'
        rename_map = {
            col: col[: -len(suffix)]
            for col in df.columns
            if col.endswith(suffix)
        }
        sub = df[fixed_cols + list(rename_map)].copy()
        sub = sub.rename(columns=rename_map)
        sub[config.phase_col] = phase
        chunks.append(sub)

    result = pd.concat(chunks, ignore_index=True)
    result = result.sort_values(
        [config.device_col, config.phase_col, config.timestamp_col]
    ).reset_index(drop=True)
    result[config.item_col] = (
        result[config.device_col].astype(str) + '_' + result[config.phase_col]
    )
    return result


# ── Population data loader ────────────────────────────────────────────────────

def load_population_data(config: ColdStartConfig) -> pd.DataFrame:
    """Load and pre-process the existing-devices CSV (population source)."""
    path = Path(config.population_data_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Population data not found: {path}\n"
            f"Set donnees.fichier_population in config.yaml."
        )

    df = pd.read_csv(path, parse_dates=[config.timestamp_col])

    # Sanitize corrupt future timestamps (same heuristic as HotStart)
    horizon = pd.Timestamp.now() + pd.Timedelta(days=30)
    future_mask = df[config.timestamp_col] > horizon
    if future_mask.any():
        _log.warning(
            "%d ligne(s) avec timestamp corrompu supprimées (> %s)",
            future_mask.sum(), horizon.date(),
        )
        df = df[~future_mask].copy()

    if config.date_debut:
        df = df[df[config.timestamp_col] >= pd.Timestamp(config.date_debut)]
    if config.date_fin:
        df = df[
            df[config.timestamp_col]
            <= pd.Timestamp(config.date_fin) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        ]

    if _is_wide_format(df, config.phase_col):
        df = _wide_to_long(df, config)
    else:
        df = df.sort_values(
            [config.device_col, config.phase_col, config.timestamp_col]
        ).reset_index(drop=True)
        df[config.item_col] = (
            df[config.device_col].astype(str) + '_' + df[config.phase_col]
        )

    # Remove new device from population to avoid contamination
    df = df[df[config.device_col].astype(str) != str(config.new_device_id)].copy()

    # ── Correction rollover / outliers ────────────────────────────────────────
    # Mirrors HotStart energy preprocessor: fence = Q3_trim + factor × IQR_trim
    # Indispensable pour cons_en qui peut contenir des pics milliardaires (rollover).
    value_cols = [c for c in config.value_cols if c in df.columns]
    _ROLLOVER_FACTOR = 30.0
    _FFILL_LIMIT     = 3
    for vc in value_cols:
        chunks = []
        for item_id_grp, grp in df.groupby(config.item_col):
            s = grp[vc].copy()
            pos = s[s > 0]
            if len(pos) >= 8:
                trim = pos[pos <= pos.quantile(0.95)]
                if len(trim) >= 4:
                    q3  = float(trim.quantile(0.75))
                    iqr = float(trim.quantile(0.75) - trim.quantile(0.25))
                    if iqr > 1e-9:
                        fence = q3 + _ROLLOVER_FACTOR * iqr
                        hits  = s.index[s > fence]
                        if len(hits) > 0:
                            _log.warning(
                                "[pop][%s][%s] %d rollover(s) (val > %.0f) -> NaN+interp",
                                item_id_grp, vc, len(hits), fence,
                            )
                            s.loc[hits] = np.nan
                            s = s.interpolate(method="linear", limit=_FFILL_LIMIT)
            chunks.append(s)
        df[vc] = pd.concat(chunks).reindex(df.index)

    # Resample to regular hourly grid
    resampled = []
    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col)[value_cols].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()
            .ffill(limit=config.ffill_limit)
            .reset_index()
        )
        g[config.item_col]  = item_id
        parts = str(item_id).rsplit('_', 1)
        g[config.device_col] = parts[0]
        g[config.phase_col]  = parts[1] if len(parts) > 1 else ''
        resampled.append(g)

    result = pd.concat(resampled, ignore_index=True)
    _log.info(
        "Population chargée : %d séries, %d points — devices: %s",
        result[config.item_col].nunique(),
        len(result),
        sorted(result[config.item_col].unique()),
    )
    return result


# ── Profile computation ───────────────────────────────────────────────────────

def _compute_series_profile(
    series:   pd.Series,
    ts_index: pd.DatetimeIndex,
    item_id:  str,
    col:      str,
) -> SeriesProfile:
    vals = series.dropna().values
    if len(vals) == 0:
        return SeriesProfile(
            item_id=item_id, value_col=col,
            n_points=0, mean=0, std=1,
            min=0, q10=0, q25=0, q50=0, q75=0, q90=0, max=0,
        )

    # Hourly pattern: group by hour-of-day, compute mean for each hour [0-23]
    s_clean = series.dropna()
    hourly = (
        s_clean.groupby(ts_index[series.notna()].hour).mean()
        .reindex(range(24), fill_value=float(np.nanmean(vals)))
        .tolist()
    )
    # Weekly pattern: group by day-of-week [0=Monday … 6=Sunday]
    weekly = (
        s_clean.groupby(ts_index[series.notna()].dayofweek).mean()
        .reindex(range(7), fill_value=float(np.nanmean(vals)))
        .tolist()
    )

    return SeriesProfile(
        item_id        = item_id,
        value_col      = col,
        n_points       = len(vals),
        mean           = float(np.mean(vals)),
        std            = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
        min            = float(np.min(vals)),
        q10            = float(np.percentile(vals, 10)),
        q25            = float(np.percentile(vals, 25)),
        q50            = float(np.percentile(vals, 50)),
        q75            = float(np.percentile(vals, 75)),
        q90            = float(np.percentile(vals, 90)),
        max            = float(np.max(vals)),
        hourly_pattern = hourly,
        weekly_pattern = weekly,
    )


def build_population_profile(
    df:     pd.DataFrame,
    config: ColdStartConfig,
    col:    str | None = None,
) -> PopulationProfile:
    """
    Compute aggregated population statistics for `col` across all devices in df.
    Each device contributes one SeriesProfile; the PopulationProfile aggregates them.
    """
    if col is None:
        col = config.value_col

    if col not in df.columns:
        raise ValueError(
            f"Colonne '{col}' introuvable dans les données de population.\n"
            f"Colonnes disponibles : {sorted(df.columns.tolist())}"
        )

    series_profiles: list[SeriesProfile] = []

    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col).sort_index()
        if col not in g.columns or g[col].dropna().empty:
            _log.warning("[%s] colonne '%s' vide — device ignoré", item_id, col)
            continue
        profile = _compute_series_profile(
            series   = g[col],
            ts_index = pd.DatetimeIndex(g.index),
            item_id  = str(item_id),
            col      = col,
        )
        series_profiles.append(profile)

    n = len(series_profiles)
    if n < config.profile_min_devices:
        raise ValueError(
            f"Seulement {n} device(s) dans la population, "
            f"minimum requis : {config.profile_min_devices}.\n"
            f"Réduisez profil.min_devices ou ajoutez plus de données."
        )

    # Aggregate across devices
    means  = np.array([p.mean  for p in series_profiles])
    stds   = np.array([p.std   for p in series_profiles])
    q10s   = np.array([p.q10   for p in series_profiles])
    q25s   = np.array([p.q25   for p in series_profiles])
    q50s   = np.array([p.q50   for p in series_profiles])
    q75s   = np.array([p.q75   for p in series_profiles])
    q90s   = np.array([p.q90   for p in series_profiles])

    # Hourly / weekly patterns: mean and std across devices (shape: 24 or 7)
    hourly_matrix = np.array([p.hourly_pattern for p in series_profiles])   # (n, 24)
    weekly_matrix = np.array([p.weekly_pattern for p in series_profiles])   # (n, 7)

    hourly_mean = hourly_matrix.mean(axis=0).tolist()
    hourly_std  = hourly_matrix.std(axis=0).tolist() if n > 1 else [0.0] * 24
    weekly_mean = weekly_matrix.mean(axis=0).tolist()
    weekly_std  = weekly_matrix.std(axis=0).tolist() if n > 1 else [0.0] * 7

    pop = PopulationProfile(
        value_col      = col,
        n_devices      = n,
        pop_mean       = float(np.mean(means)),
        pop_std        = float(np.mean(stds)),     # mean of individual σ (better than σ of means for noise level)
        pop_q10        = float(np.mean(q10s)),
        pop_q25        = float(np.mean(q25s)),
        pop_q50        = float(np.mean(q50s)),
        pop_q75        = float(np.mean(q75s)),
        pop_q90        = float(np.mean(q90s)),
        hourly_mean    = hourly_mean,
        hourly_std     = hourly_std,
        weekly_mean    = weekly_mean,
        weekly_std     = weekly_std,
        device_profiles= series_profiles,
    )

    _log.info(
        "Profil population '%s' — %d devices  |  μ=%.3f  σ=%.3f  "
        "q10=%.3f  q50=%.3f  q90=%.3f",
        col, n,
        pop.pop_mean, pop.pop_std,
        pop.pop_q10, pop.pop_q50, pop.pop_q90,
    )
    return pop
