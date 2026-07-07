"""
Synthetic gaz consumption generator for cold start.

Gaz specifics vs water
----------------------
- Distribution : quasi-normale (vs log-normale pour eau) — consommation gaz plus régulière
- Deux pics journaliers : matin (6-9h, chauffage eau/espace) et soir (17-20h)
- Très peu d'offline (~3%) — compteur gaz rarement coupé
- Anomalies injectées :
    * fuite       : flux élevé continu (3-12h) — urgence absolue
    * sur_conso   : consommation anormalement haute (chauffage défaillant)
    * arret_net   : chute brutale à zéro (robinet principal fermé)
    * spike       : pic instantané (transitoire de pression, erreur capteur)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import GazColdStartConfig
from .profile_builder import GazPopulationProfile

_log = get_logger(__name__)


def generate_synthetic_series(
    profile: GazPopulationProfile,
    config:  GazColdStartConfig,
    item_id: str,
    col:     str | None = None,
) -> pd.DataFrame:
    if col is None:
        col = config.value_col

    rng = np.random.default_rng(config.synthetic_seed)

    n_hours  = config.synthetic_days * 24
    start    = pd.Timestamp("2025-01-01 00:00:00")
    ts_index = pd.date_range(start, periods=n_hours, freq="1h")

    # ── Signal de base : distribution normale (gaz plus régulier que eau) ──
    mu    = max(profile.pop_mean, 1e-9)
    sigma = max(profile.pop_std,  1e-9)

    raw_vals = rng.normal(loc=mu, scale=sigma * config.synthetic_noise_factor, size=n_hours)
    raw_vals = np.maximum(raw_vals, 0.0)   # pas de consommation négative

    # ── Saisonnalité horaire (double pic : matin + soir) ──────────────────
    hourly_mean  = np.array(profile.hourly_mean)   # shape (24,)
    overall_mean = float(hourly_mean[hourly_mean > 0].mean()) if (hourly_mean > 0).any() else mu
    if overall_mean < 1e-9:
        overall_mean = mu

    hourly_scale = np.clip(hourly_mean / overall_mean, 0.05, 5.0)
    signal = raw_vals * hourly_scale[ts_index.hour.to_numpy()]

    # ── Saisonnalité hebdomadaire (résiduel atténué) ───────────────────────
    weekly_mean = np.array(profile.weekly_mean)
    weekly_dev  = weekly_mean - float(np.mean(weekly_mean))
    weekly_adj  = weekly_dev[ts_index.dayofweek.to_numpy()] * 0.20
    signal      = np.maximum(signal + weekly_adj, 0.0)

    # ── Masque offline (très rare pour gaz) ──────────────────────────────
    offline_prob = max(profile.pop_pct_offline, config.synthetic_offline_rate)
    offline_mask = rng.random(n_hours) < offline_prob
    signal[offline_mask] = 0.0

    # ── Clip physiquement réaliste ────────────────────────────────────────
    upper_bound = profile.pop_q90 * 4.0
    signal      = np.clip(signal, 0.0, upper_bound)

    # ── Injection d'anomalies gaz ─────────────────────────────────────────
    anomaly_mask = np.zeros(n_hours, dtype=bool)
    n_events     = max(1, int(n_hours * config.synthetic_anomaly_rate / 5))  # ~5h/event

    event_types = ["fuite", "sur_conso", "arret_net", "spike"]
    weights     = [0.35,   0.30,        0.20,        0.15]

    for _ in range(n_events):
        event_type = rng.choice(event_types, p=weights)
        idx_start  = int(rng.integers(0, n_hours - 12))

        if event_type == "fuite":
            # Fuite gaz : flux élevé constant pendant 3-12h — URGENCE
            duration   = int(rng.integers(3, 13))
            end_idx    = min(idx_start + duration, n_hours)
            multiplier = rng.uniform(4.0, 10.0)
            signal[idx_start:end_idx] = profile.pop_mean * multiplier
            anomaly_mask[idx_start:end_idx] = True

        elif event_type == "sur_conso":
            # Sur-consommation : chauffage défaillant / brûleur bloqué ouvert
            duration   = int(rng.integers(6, 25))
            end_idx    = min(idx_start + duration, n_hours)
            multiplier = rng.uniform(2.0, 4.0)
            signal[idx_start:end_idx] *= multiplier
            anomaly_mask[idx_start:end_idx] = True

        elif event_type == "arret_net":
            # Arrêt net : robinet principal coupé, panne compteur
            duration = int(rng.integers(3, 13))
            end_idx  = min(idx_start + duration, n_hours)
            signal[idx_start:end_idx] = 0.0
            anomaly_mask[idx_start:end_idx] = True

        else:  # spike
            # Pic instantané : transitoire de pression, erreur capteur
            magnitude = rng.uniform(5.0, 12.0) * profile.pop_std
            signal[idx_start] = profile.pop_mean + magnitude
            anomaly_mask[idx_start] = True

    # Re-clip après injection
    signal = np.clip(signal, 0.0, profile.pop_q90 * 12.0)

    _log.info(
        "[%s] %d evenements synthetiques injectes (%d points flags)",
        item_id, n_events, int(anomaly_mask.sum()),
    )

    # ── DataFrame final ───────────────────────────────────────────────────
    df = pd.DataFrame({
        config.timestamp_col:  ts_index,
        col:                    signal,
        config.item_col:        item_id,
        config.device_col:      item_id,
        "is_synthetic":         True,
        "is_injected_anomaly":  anomaly_mask,
    })

    _log.info(
        "[%s] Serie gaz synthetique : %d pts | mu_actif=%.3f  sigma=%.3f  offline=%.1f%%",
        item_id, n_hours,
        float(signal[signal > 0].mean()) if (signal > 0).any() else 0.0,
        float(signal[signal > 0].std())  if (signal > 0).sum() > 1 else 0.0,
        100.0 * float((signal == 0).mean()),
    )
    return df


def generate_all_synthetic(
    profiles: dict[str, GazPopulationProfile],
    config:   GazColdStartConfig,
) -> pd.DataFrame:
    """Génère les séries synthétiques pour le nouveau device gaz (sans phases)."""
    item_id = str(config.new_device_id)
    chunks: list[pd.DataFrame] = []

    for col, profile in profiles.items():
        chunk = generate_synthetic_series(profile, config, item_id, col)
        chunks.append(chunk)

    if not chunks:
        raise ValueError(
            "Aucune donnee synthetique generee. "
            "Verifiez colonnes.valeur dans config.yaml."
        )

    result = chunks[0]
    for extra in chunks[1:]:
        id_cols  = [config.timestamp_col, config.item_col, config.device_col,
                    "is_synthetic", "is_injected_anomaly"]
        new_vals = [c for c in extra.columns if c not in id_cols]
        if new_vals:
            result = result.merge(
                extra[[config.timestamp_col, config.item_col] + new_vals],
                on=[config.timestamp_col, config.item_col],
                how="left",
            )

    _log.info(
        "Generation synthetique gaz terminee : device=%s, %d colonnes, %d lignes",
        item_id, len(profiles), len(result),
    )
    return result
