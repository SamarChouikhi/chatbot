from __future__ import annotations

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import WaterColdStartConfig
from .profile_builder import WaterPopulationProfile

_log = get_logger(__name__)


def generate_synthetic_series(
    profile: WaterPopulationProfile,
    config:  WaterColdStartConfig,
    item_id: str,
    col:     str | None = None,
) -> pd.DataFrame:
    """
    Generate a synthetic water consumption series for a new device with no history.

    Water-specific strategy
    -----------------------
    Water consumption is fundamentally different from energy:
    - Bursty/sporadic: many near-zero hours + intermittent peaks
    - Daily pattern: morning peak (~7-9h), evening peak (~18-20h), near-zero at night
    - High offline rate (device unpowered or no flow) — modeled explicitly
    - Distribution is right-skewed (log-normal), not Gaussian

    The synthesis:
    1. Draw from log-normal distribution fitted to population (active values)
    2. Scale by hourly pattern (learned from existing devices)
    3. Apply offline mask (Bernoulli draws with population offline rate)
    4. Inject synthetic anomaly events (sustained high flow = leak, sudden stop = rupture)
    """
    if col is None:
        col = config.value_col

    rng = np.random.default_rng(config.synthetic_seed)

    n_hours  = config.synthetic_days * 24
    start    = pd.Timestamp("2025-01-01 00:00:00")
    ts_index = pd.date_range(start, periods=n_hours, freq="1h")

    # ── Log-normal fit to population active values ────────────────────────────
    # μ_log and σ_log from method of moments on population stats
    mu    = max(profile.pop_mean, 1e-9)
    sigma = max(profile.pop_std,  1e-9)
    cv2   = (sigma / mu) ** 2
    mu_log    = np.log(mu / np.sqrt(1 + cv2))
    sigma_log = np.sqrt(np.log(1 + cv2))

    raw_vals = rng.lognormal(mean=mu_log, sigma=sigma_log * config.synthetic_noise_factor, size=n_hours)

    # ── Hourly seasonality scaling ────────────────────────────────────────────
    hourly_mean  = np.array(profile.hourly_mean)   # shape (24,)
    overall_mean = float(np.mean(hourly_mean[hourly_mean > 0])) if (hourly_mean > 0).any() else mu
    if overall_mean < 1e-9:
        overall_mean = mu

    # Scale factor per hour: ratio of hourly pattern to overall mean
    # Clamp to [0.05, 5.0] to avoid degenerate factors on noisy patterns
    hourly_scale = np.clip(hourly_mean / overall_mean, 0.05, 5.0)
    signal = raw_vals * hourly_scale[ts_index.hour.to_numpy()]

    # ── Weekly seasonality (additive residual, attenuated) ────────────────────
    weekly_mean = np.array(profile.weekly_mean)
    weekly_dev  = weekly_mean - float(np.mean(weekly_mean))
    weekly_adj  = weekly_dev[ts_index.dayofweek.to_numpy()] * 0.25
    signal      = np.maximum(signal + weekly_adj, 0.0)

    # ── Offline mask: zero out hours where device is powered off / no flow ────
    # Use the larger of: population offline rate (realistic) vs configured floor
    offline_prob = max(profile.pop_pct_offline, config.synthetic_offline_rate)
    offline_mask = rng.random(n_hours) < offline_prob
    signal[offline_mask] = 0.0

    # ── Clip to physically plausible range ────────────────────────────────────
    upper_bound = profile.pop_q90 * 4.0
    signal      = np.clip(signal, 0.0, upper_bound)

    # ── Inject synthetic anomaly events ──────────────────────────────────────
    anomaly_mask = np.zeros(n_hours, dtype=bool)
    n_events     = int(n_hours * config.synthetic_anomaly_rate / 6)  # ~6h per event

    if n_events > 0:
        for _ in range(n_events):
            event_type = rng.choice(["leak", "rupture", "spike"])
            idx_start  = int(rng.integers(0, n_hours - 6))

            if event_type == "leak":
                # Sustained high flow over 3-12h (water leak)
                duration = int(rng.integers(3, 13))
                end_idx  = min(idx_start + duration, n_hours)
                multiplier = rng.uniform(3.0, 8.0)
                signal[idx_start:end_idx] = profile.pop_mean * multiplier
                anomaly_mask[idx_start:end_idx] = True

            elif event_type == "rupture":
                # Sudden zero after normal flow (pipe rupture / valve closed)
                duration = int(rng.integers(6, 25))
                end_idx  = min(idx_start + duration, n_hours)
                # Before rupture: normal flow; after: zero
                signal[idx_start:end_idx] = 0.0
                anomaly_mask[idx_start:end_idx] = True

            else:  # spike
                # Single-hour spike (pressure wave, meter glitch)
                magnitude = rng.uniform(5.0, 10.0) * profile.pop_std
                signal[idx_start] = profile.pop_mean + magnitude
                anomaly_mask[idx_start] = True

        # Re-clip after injection
        signal = np.clip(signal, 0.0, profile.pop_q90 * 10.0)
        _log.info(
            "[%s] %d événements anomaux synthétiques injectés (%d points flagués)",
            item_id, n_events, int(anomaly_mask.sum()),
        )

    # ── Build DataFrame ───────────────────────────────────────────────────────
    df = pd.DataFrame({
        config.timestamp_col:     ts_index,
        col:                       signal,
        config.item_col:           item_id,
        config.device_col:         item_id,
        "is_synthetic":            True,
        "is_injected_anomaly":     anomaly_mask,
    })

    _log.info(
        "[%s] Série eau synthétique : %d pts  μ_actif=%.3f  σ=%.3f  offline=%.1f%%",
        item_id, n_hours,
        float(signal[signal > 0].mean()) if (signal > 0).any() else 0.0,
        float(signal[signal > 0].std())  if (signal > 0).sum() > 1 else 0.0,
        100.0 * float((signal == 0).mean()),
    )
    return df


def generate_all_synthetic(
    profiles: dict[str, WaterPopulationProfile],
    config:   WaterColdStartConfig,
) -> pd.DataFrame:
    """
    Generate synthetic series for the new water device.
    Water has no phases → one series per value column.
    """
    item_id = str(config.new_device_id)
    chunks: list[pd.DataFrame] = []

    for col, profile in profiles.items():
        chunk = generate_synthetic_series(profile, config, item_id, col)
        chunks.append(chunk)

    if not chunks:
        raise ValueError(
            "Aucune donnée synthétique générée. "
            "Vérifiez colonnes.valeur dans config.yaml."
        )

    # Merge multiple value columns for the same item_id/timestamp
    result = chunks[0]
    for extra in chunks[1:]:
        id_cols = [config.timestamp_col, config.item_col, config.device_col,
                   "is_synthetic", "is_injected_anomaly"]
        new_val = [c for c in extra.columns if c not in id_cols]
        if new_val:
            result = result.merge(
                extra[[config.timestamp_col, config.item_col] + new_val],
                on=[config.timestamp_col, config.item_col],
                how="left",
            )

    _log.info(
        "Génération synthétique eau terminée : device=%s, %d colonnes, %d lignes",
        item_id, len(profiles), len(result),
    )
    return result
