"""
ColdStart Gaz pipeline — adapté du pipeline ColdStart water.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import GazColdStartConfig
from .detector import GazColdStartDetector
from .evaluator import (
    anomaly_summary,
    comparison_summary,
    plot_algo_comparison,
    plot_anomaly_series,
    plot_hourly_profile,
)
from .profile_builder import (
    GazPopulationProfile,
    build_population_profile,
    load_population_data,
)
from .synthetic_generator import generate_all_synthetic

_log = get_logger(__name__)


def _load_new_device_data(config: GazColdStartConfig) -> pd.DataFrame | None:
    """Charge les données réelles du nouveau device gaz (si disponibles)."""
    path = Path(config.new_device_data_path or "")
    if not path.exists() or not config.new_device_data_path:
        _log.info("Aucune donnee reelle nouveau device gaz — mode bootstrap synthetique pur")
        return None

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

    value_cols = [c for c in config.value_cols if c in df.columns]
    if not value_cols:
        _log.warning("Colonnes %s absentes du fichier nouveau device gaz", config.value_cols)
        return None

    if config.device_col not in df.columns:
        df[config.device_col] = config.new_device_id
    if config.item_col not in df.columns:
        df[config.item_col] = df[config.device_col].astype(str)

    col = config.value_col
    if col in df.columns:
        neg = df[col] < 0
        if neg.any():
            _log.warning("%d valeur(s) negative(s) -> NaN + interpolation", int(neg.sum()))
            df.loc[neg, col] = np.nan
            df[col] = df[col].interpolate(method="linear", limit=config.ffill_limit)

    resampled = []
    for item_id, grp in df.groupby(config.item_col):
        g = grp.set_index(config.timestamp_col)[value_cols].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()
            .ffill(limit=config.ffill_limit)
            .reset_index()
        )
        g[config.item_col]   = item_id
        g[config.device_col] = item_id
        g["is_synthetic"]    = False
        resampled.append(g)

    result = pd.concat(resampled, ignore_index=True)
    _log.info(
        "Donnees reelles nouveau device gaz : %d points, %d series",
        len(result), result[config.item_col].nunique(),
    )
    return result


def _save_run_summary(
    result:     pd.DataFrame,
    summary:    pd.DataFrame,
    config:     GazColdStartConfig,
    duration:   float,
    n_pop:      int,
    warmup_pct: float,
) -> None:
    per_device: dict = {}
    for _, row in summary.iterrows():
        per_device[row["item_id"]] = {
            "anomaly_count": int(row["anomaly_count"]),
            "anomaly_rate":  float(row["anomaly_rate"]),
            "offline_rate":  float(row.get("offline_rate", 0)),
        }

    algo_breakdown: dict = {}
    for col in config.value_cols:
        algo_breakdown[col] = {}
        for algo in ("zscore", "iqr", "isolation_forest", "chronos"):
            flag = f"algo_{col}_{algo}"
            if flag in result.columns:
                algo_breakdown[col][algo] = int(result[flag].sum())

    meta = {
        "run_timestamp":    datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 2),
        "mode":             "cold_start_gaz",
        "config": {
            "new_device_id":         config.new_device_id,
            "algorithm":             config.algorithm.value,
            "population_data_path":  config.population_data_path,
            "synthetic_days":        config.synthetic_days,
            "warmup_hours":          config.warmup_hours,
            "zscore_threshold":      config.zscore_threshold,
            "iqr_multiplier":        config.iqr_multiplier,
            "if_contamination":      config.if_contamination,
            "regime_change_hours":   config.regime_change_hours,
        },
        "results": {
            "population_devices":  n_pop,
            "total_rows":          len(result),
            "total_series":        result[config.item_col].nunique(),
            "total_anomalies":     int(result["is_anomaly"].sum()),
            "anomaly_rate":        round(float(result["is_anomaly"].mean()), 4),
            "point_anomalies":     int(result["is_point_anomaly"].sum()) if "is_point_anomaly" in result.columns else None,
            "regime_change_hours": int(result["is_regime_change"].sum()) if "is_regime_change" in result.columns else None,
            "offline_rate":        round(float((result[config.value_col] == 0).mean()), 4),
            "warmup_complete_pct": round(warmup_pct, 2),
            "per_device":          per_device,
            "per_algo":            algo_breakdown,
        },
    }

    out_path = os.path.join(config.output_dir, "run_summary.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    _log.info("Run summary saved: %s", out_path)


def run(
    config:     Union[GazColdStartConfig, str, Path, None] = None,
    hot_result: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Exécute le pipeline cold start gaz complet.

    Parameters
    ----------
    config     : GazColdStartConfig | str | Path | None
    hot_result : pd.DataFrame | None — résultats HotStart gaz pour comparaison

    Returns
    -------
    result  : pd.DataFrame — résultats heure par heure
    summary : pd.DataFrame — résumé par device
    """
    if config is None:
        config = GazColdStartConfig.from_file()
    elif isinstance(config, (str, Path)):
        config = GazColdStartConfig.from_yaml(config)
    else:
        config._validate()

    _log.info("=" * 60)
    _log.info("ARIA — Detection d'anomalies Cold Start GAZ")
    _log.info("Nouveau device : %s", config.new_device_id)
    _log.info("Algorithme     : %s", config.algorithm.value.upper())
    _log.info("Population     : %s", config.population_data_path)
    _log.info("Resultats      : %s", config.output_dir)
    _log.info("=" * 60)

    os.makedirs(config.output_dir, exist_ok=True)
    t_start = time.perf_counter()

    # ── Étape 1 — Chargement & profil population ──────────────────────────
    _log.info("Etape 1/6 — Chargement & profil population gaz")
    pop_df = load_population_data(config)

    profiles: dict[str, GazPopulationProfile] = {}
    for col in config.value_cols:
        if col in pop_df.columns:
            profiles[col] = build_population_profile(pop_df, config, col)

    if not profiles:
        raise ValueError(
            f"Aucun profil construit. Colonnes demandees : {config.value_cols}\n"
            f"Colonnes disponibles : {sorted(pop_df.columns.tolist())}"
        )

    # ── Étape 2 — Sauvegarde profils ──────────────────────────────────────
    _log.info("Etape 2/6 — Sauvegarde profils population")
    for col, profile in profiles.items():
        profile_path = os.path.join(config.output_dir, f"population_profile_{col}.json")
        profile.to_json(profile_path)
        _log.info(
            "Profile saved: %s  (%d devices, offline_moy=%.1f%%)",
            profile_path, profile.n_devices, profile.pop_pct_offline * 100,
        )

    # ── Étape 3 — Données synthétiques ────────────────────────────────────
    _log.info("Etape 3/6 — Generation donnees synthetiques (%d jours)", config.synthetic_days)
    synthetic_df = generate_all_synthetic(profiles, config)

    # ── Étape 4 — Fit détecteur ───────────────────────────────────────────
    _log.info("Etape 4/6 — Initialisation detecteur cold start gaz")
    detector = GazColdStartDetector(profiles=profiles, config=config)
    detector.fit(synthetic_df)

    # ── Étape 4b — Données réelles (si disponibles) ───────────────────────
    real_df      = _load_new_device_data(config)
    detection_df = real_df if (real_df is not None and not real_df.empty) else synthetic_df.copy()

    if real_df is None:
        _log.info("Mode bootstrap : detection sur synthetique (%d points)", len(detection_df))
    else:
        _log.info("Detection sur donnees reelles (%d points)", len(detection_df))

    # ── Étape 5 — Détection ───────────────────────────────────────────────
    _log.info("Etape 5/6 — Detection (algo=%s)", config.algorithm.value)
    result = detector.detect(detection_df)

    # ── Étape 6 — Résumé & export ─────────────────────────────────────────
    _log.info("Etape 6/6 — Resume, export CSV & visualisations")
    summary = anomaly_summary(result, config)

    warmup_pct = 0.0
    if "warmup_active" in result.columns:
        warmup_pct = 100.0 * float((~result["warmup_active"]).mean())

    _log.info("\n%s", summary.to_string(index=False))

    result_path  = os.path.join(config.output_dir, "coldstart_gaz_result.csv")
    summary_path = os.path.join(config.output_dir, "coldstart_gaz_summary.csv")
    result.to_csv(result_path,  index=False)
    summary.to_csv(summary_path, index=False)
    _log.info("Saved: %s", result_path)
    _log.info("Saved: %s", summary_path)

    if hot_result is not None:
        cmp = comparison_summary(result, hot_result, config)
        if not cmp.empty:
            cmp_path = os.path.join(config.output_dir, "comparison_cold_vs_hot_gaz.csv")
            cmp.to_csv(cmp_path, index=False)
            _log.info("Saved: %s", cmp_path)

    # ── Visualisations ─────────────────────────────────────────────────────
    out_path = Path(config.output_dir)
    old_pngs = list(out_path.glob("*.png"))
    if old_pngs:
        prev_dir = out_path / "prev"
        prev_dir.mkdir(exist_ok=True)
        for png in old_pngs:
            shutil.move(str(png), str(prev_dir / png.name))

    plot_anomaly_series(result, config, config.output_dir)
    plot_algo_comparison(result, config, config.output_dir)
    plot_hourly_profile(pop_df, detection_df, config, config.output_dir)

    duration = time.perf_counter() - t_start
    _save_run_summary(
        result, summary, config, duration,
        n_pop      = sum(p.n_devices for p in profiles.values()),
        warmup_pct = warmup_pct,
    )
    _log.info("Cold start gaz pipeline termine en %.1f s", duration)

    return result, summary
