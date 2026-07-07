from __future__ import annotations

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import ColdStartConfig
from .profile_builder import PopulationProfile

_log = get_logger(__name__)


def generate_synthetic_series(
    profile:   PopulationProfile,
    config:    ColdStartConfig,
    item_id:   str,
    col:       str | None = None,
) -> pd.DataFrame:
    """
    Generate a synthetic time series for a new device with no history.

    Strategy
    --------
    1. Build a base signal from the hourly seasonality pattern (population average).
    2. Add weekly seasonality on top.
    3. Add Gaussian noise scaled by population σ × noise_factor.
    4. Optionally inject synthetic anomalies (spikes / dips) at random positions.
    5. Clip to [0, max_observed] so values stay physically plausible.

    The result has the same schema as real preprocessed data (timestamp, value_col,
    item_id, device_col, phase_col), so it can be fed directly into the detector.
    """
    if col is None:
        col = config.value_col

    rng = np.random.default_rng(config.synthetic_seed)

    n_hours   = config.synthetic_days * 24
    start     = pd.Timestamp("2025-01-01 00:00:00")   # arbitrary reference date
    ts_index  = pd.date_range(start, periods=n_hours, freq="1h")

    # ── Base signal: hourly seasonality ──────────────────────────────────────
    hourly_base  = np.array(profile.hourly_mean)      # shape (24,)
    hourly_sigma = np.array(profile.hourly_std)        # shape (24,)

    # Repeat the 24-h pattern for n_hours
    hours_of_day = ts_index.hour.to_numpy()
    base_signal  = hourly_base[hours_of_day]

    # ── Weekly seasonality layer ──────────────────────────────────────────────
    weekly_base  = np.array(profile.weekly_mean)       # shape (7,)
    # Compute weekly deviation relative to the overall mean (additive adjustment)
    overall_mean = profile.pop_mean
    weekly_dev   = weekly_base - overall_mean          # shape (7,)
    days_of_week = ts_index.dayofweek.to_numpy()
    weekly_adj   = weekly_dev[days_of_week] * 0.3      # attenuated to avoid double-counting

    # ── Gaussian noise ────────────────────────────────────────────────────────
    noise_sigma  = profile.pop_std * config.synthetic_noise_factor
    noise        = rng.normal(0.0, max(noise_sigma, 1e-6), n_hours)

    # ── Assemble signal ───────────────────────────────────────────────────────
    signal = base_signal + weekly_adj + noise

    # Clip to physically plausible range [0, p99_upper]
    upper_bound = profile.pop_q90 * 3.0   # generous ceiling based on population
    signal      = np.clip(signal, 0.0, upper_bound)

    # ── Inject synthetic anomalies ────────────────────────────────────────────
    anomaly_mask = np.zeros(n_hours, dtype=bool)
    n_anomalies  = int(n_hours * config.synthetic_anomaly_rate)

    if n_anomalies > 0:
        anomaly_indices = rng.choice(n_hours, size=n_anomalies, replace=False)
        anomaly_mask[anomaly_indices] = True

        for idx in anomaly_indices:
            # Base anomaly on pop_mean (not signal[idx]) so spikes from offline hours
            # still land well above the IQR upper fence and are detectable.
            direction = rng.choice([-1, 1])
            magnitude = rng.uniform(4.0, 8.0) * profile.pop_std  # 4–8σ excursion
            signal[idx] = max(profile.pop_mean, signal[idx]) + direction * magnitude

        # Re-clip after anomaly injection
        spike_ceiling = profile.pop_q90 * 6.0
        signal = np.clip(signal, 0.0, spike_ceiling)

        _log.info(
            "[%s] %d anomalies synthétiques injectées (%.1f%%)",
            item_id, n_anomalies, 100.0 * n_anomalies / n_hours,
        )

    # ── Build DataFrame ───────────────────────────────────────────────────────
    parts = str(item_id).rsplit('_', 1)
    device_id = parts[0]
    phase     = parts[1] if len(parts) > 1 else ''

    df = pd.DataFrame({
        config.timestamp_col:         ts_index,
        col:                           signal,
        config.item_col:               item_id,
        config.device_col:             device_id,
        config.phase_col:              phase,
        "is_synthetic":                True,
        "is_injected_anomaly":         anomaly_mask,
    })

    _log.info(
        "[%s] Série synthétique générée : %d points (%d jours)  μ=%.3f  σ=%.3f",
        item_id, n_hours, config.synthetic_days,
        float(signal.mean()), float(signal.std()),
    )
    return df


def generate_all_synthetic(
    profiles: dict[str, PopulationProfile],   # col → PopulationProfile
    config:   ColdStartConfig,
) -> pd.DataFrame:
    """
    Generate synthetic series for every (phase × column) of the new device.

    Energy specificity: each phase is a SEPARATE item_id (device_L1, device_L2, device_L3).
    → Within a phase, multiple value columns are MERGED on (timestamp, item_id).
    → Between phases, results are CONCATENATED (different item_ids).
    """
    id_cols = {
        config.timestamp_col, config.item_col, config.device_col,
        config.phase_col, "is_synthetic", "is_injected_anomaly",
    }

    phase_chunks: list[pd.DataFrame] = []

    for phase in config.new_device_phases:
        item_id   = f"{config.new_device_id}_{phase}"
        phase_df: pd.DataFrame | None = None

        for col, profile in profiles.items():
            chunk = generate_synthetic_series(profile, config, item_id, col)

            if phase_df is None:
                phase_df = chunk
            else:
                # Same phase, additional value column → merge on (timestamp, item_id)
                new_val_cols = [c for c in chunk.columns if c not in id_cols]
                if new_val_cols:
                    phase_df = phase_df.merge(
                        chunk[[config.timestamp_col, config.item_col] + new_val_cols],
                        on=[config.timestamp_col, config.item_col],
                        how="left",
                    )

        if phase_df is not None:
            phase_chunks.append(phase_df)

    if not phase_chunks:
        raise ValueError(
            "Aucune donnee synthetique generee. "
            "Verifiez nouveau_device.phases et colonnes.valeur dans config.yaml."
        )

    result = pd.concat(phase_chunks, ignore_index=True)
    _log.info(
        "Generation synthetique terminee : %d phases x %d colonne(s) = %d lignes",
        len(config.new_device_phases), len(profiles), len(result),
    )
    return result
