"""
Synthetic fuel consumption generator for cold start.

Fuel specifics
--------------
- Distribution bimodale : 0 (garé) ou ~3-10 L/h (conduite active)
- Offline rate : ~46% (nuit 20h-6h + samedi + dimanche)
- Distribution active : quasi-normale (mean=5.24, std=1.99)
- Plafond physique : max=10.35 L/h (vitesse réglementée 90 km/h)

Anomalies injectées (spécifiques au carburant)
----------------------------------------------
  sur_consommation  : conso > plafond physique (véhicule défaillant)
  vol_carburant     : conso élevée SANS mouvement (vitesse=0) → siphonnage
  surconsommation_nuit : conso nocturne anormale (minuit-5h)
  arret_prolonge    : offline > 5 jours consécutifs (panne/hors service)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import FuelColdStartConfig
from .profile_builder import FuelPopulationProfile

_log = get_logger(__name__)


def generate_synthetic_series(
    profile: FuelPopulationProfile,
    config:  FuelColdStartConfig,
    item_id: str,
    col:     str | None = None,
) -> pd.DataFrame:
    if col is None:
        col = config.value_col

    rng = np.random.default_rng(config.synthetic_seed)

    n_hours  = config.synthetic_days * 24
    start    = pd.Timestamp("2025-09-01 00:00:00")
    ts_index = pd.date_range(start, periods=n_hours, freq="1h")

    hour = ts_index.hour.to_numpy()
    dow  = ts_index.dayofweek.to_numpy()  # 0=lundi … 6=dimanche

    # ── Masque offline (véhicule garé) ────────────────────────────────────
    # Nuit (20h-6h) ET weekend → offline très probable
    is_night   = (hour >= 20) | (hour < 6)
    is_weekend = dow >= 5
    # Prob offline : nuit (~80%), weekend_jour (~60%), heure ouvrable (~10%)
    prob_offline = np.where(
        is_night & is_weekend, 0.98,
        np.where(is_night, 0.82,
        np.where(is_weekend, 0.65,
        0.08))
    )
    # Ajustement global pour atteindre le taux cible (46%)
    actual_offline = float((rng.random(n_hours) < prob_offline).mean())
    adj_factor = config.synthetic_offline_rate / max(actual_offline, 1e-9)
    adj_factor = min(max(adj_factor, 0.5), 1.5)
    offline_mask = rng.random(n_hours) < (prob_offline * adj_factor)

    # ── Signal actif ──────────────────────────────────────────────────────
    # Distribution quasi-normale sur valeurs actives
    mu    = max(profile.pop_mean, 1e-9)
    sigma = max(profile.pop_std,  1e-9)

    raw_vals = rng.normal(loc=mu, scale=sigma * config.synthetic_noise_factor, size=n_hours)
    raw_vals = np.maximum(raw_vals, 0.0)

    # Saisonnalité horaire (pattern population)
    hourly_mean  = np.array(profile.hourly_mean)
    overall_mean = float(hourly_mean[hourly_mean > 0].mean()) if (hourly_mean > 0).any() else mu
    if overall_mean < 1e-9:
        overall_mean = mu
    hourly_scale = np.clip(hourly_mean / overall_mean, 0.01, 3.0)
    signal = raw_vals * hourly_scale[hour]

    # Saisonnalité hebdomadaire
    weekly_mean = np.array(profile.weekly_mean)
    weekly_dev  = weekly_mean - float(np.mean(weekly_mean))
    signal      = np.maximum(signal + weekly_dev[dow] * 0.15, 0.0)

    # Appliquer offline
    signal[offline_mask] = 0.0

    # Clip au plafond physique réel
    signal = np.clip(signal, 0.0, profile.pop_max * 1.05)

    # ── Injection anomalies carburant ─────────────────────────────────────
    anomaly_mask = np.zeros(n_hours, dtype=bool)
    n_events     = max(1, int(n_hours * config.synthetic_anomaly_rate / 4))  # ~4h/event

    event_types = ["sur_consommation", "vol_carburant", "surconso_nuit", "arret_prolonge"]
    weights     = [0.35, 0.30, 0.20, 0.15]

    for _ in range(n_events):
        event_type = rng.choice(event_types, p=weights)
        idx_start  = int(rng.integers(0, n_hours - 8))

        if event_type == "sur_consommation":
            # Consommation > plafond physique (véhicule défaillant, fuite moteur)
            duration   = int(rng.integers(2, 8))
            end_idx    = min(idx_start + duration, n_hours)
            signal[idx_start:end_idx] = profile.pop_max * rng.uniform(1.3, 2.0)
            # Assurer que le véhicule est en mouvement pendant l'anomalie
            offline_mask[idx_start:end_idx] = False
            anomaly_mask[idx_start:end_idx] = True

        elif event_type == "vol_carburant":
            # Conso > 0 avec vitesse = 0 → siphonnage ou moteur tournant à l'arrêt
            # On marque l'heure : signal actif mais offline_mask = True (ne bouge pas)
            duration = int(rng.integers(1, 5))
            end_idx  = min(idx_start + duration, n_hours)
            signal[idx_start:end_idx] = profile.pop_mean * rng.uniform(0.3, 0.8)
            offline_mask[idx_start:end_idx] = False   # conso mais garé
            anomaly_mask[idx_start:end_idx] = True

        elif event_type == "surconso_nuit":
            # Consommation nocturne anormale (minuit-4h)
            night_hours = np.where((hour >= 0) & (hour <= 4))[0]
            if len(night_hours) > 0:
                idx_night = int(rng.choice(night_hours))
                duration  = int(rng.integers(1, 4))
                end_night = min(idx_night + duration, n_hours)
                signal[idx_night:end_night] = profile.pop_mean * rng.uniform(0.5, 1.5)
                offline_mask[idx_night:end_night] = False
                anomaly_mask[idx_night:end_night] = True

        else:  # arret_prolonge
            # Véhicule hors service > 5 jours = anomalie opérationnelle
            duration = int(rng.integers(5 * 24, 8 * 24))
            end_idx  = min(idx_start + duration, n_hours)
            signal[idx_start:end_idx] = 0.0
            offline_mask[idx_start:end_idx] = True
            anomaly_mask[idx_start:end_idx] = True

    # Réappliquer offline après injections (sauf vol_carburant et sur_conso)
    signal[offline_mask & ~anomaly_mask] = 0.0
    signal = np.clip(signal, 0.0, profile.pop_max * 2.5)

    _log.info(
        "[%s] %d evenements anomaux injectes (%d points)",
        item_id, n_events, int(anomaly_mask.sum()),
    )
    _log.info(
        "[%s] Serie fuel synthetique : %d pts | mu_actif=%.3f  sigma=%.3f  offline=%.1f%%",
        item_id, n_hours,
        float(signal[signal > 0].mean()) if (signal > 0).any() else 0.0,
        float(signal[signal > 0].std())  if (signal > 0).sum() > 1 else 0.0,
        100.0 * float((signal == 0).mean()),
    )

    return pd.DataFrame({
        config.timestamp_col:  ts_index,
        col:                    signal,
        config.item_col:        item_id,
        config.device_col:      item_id,
        "is_synthetic":         True,
        "is_injected_anomaly":  anomaly_mask,
    })


def generate_all_synthetic(
    profiles: dict[str, FuelPopulationProfile],
    config:   FuelColdStartConfig,
) -> pd.DataFrame:
    item_id = str(config.new_device_id)
    chunks: list[pd.DataFrame] = []

    for col, profile in profiles.items():
        chunk = generate_synthetic_series(profile, config, item_id, col)
        chunks.append(chunk)

    if not chunks:
        raise ValueError("Aucune donnee synthetique generee.")

    result = chunks[0]
    id_cols = {config.timestamp_col, config.item_col, config.device_col,
               "is_synthetic", "is_injected_anomaly"}
    for extra in chunks[1:]:
        new_vals = [c for c in extra.columns if c not in id_cols]
        if new_vals:
            result = result.merge(
                extra[[config.timestamp_col, config.item_col] + new_vals],
                on=[config.timestamp_col, config.item_col], how="left",
            )

    _log.info(
        "Generation synthetique fuel terminee : device=%s, %d colonnes, %d lignes",
        item_id, len(profiles), len(result),
    )
    return result
