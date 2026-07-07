from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

import pandas as pd

from common.logger import get_logger
from .config import ColdStartConfig
from .detector import ColdStartDetector
from .evaluator import (
    anomaly_summary,
    comparison_summary,
    plot_algo_comparison,
    plot_anomaly_series,
    plot_population_vs_new_device,
)
from .profile_builder import (
    PopulationProfile,
    build_population_profile,
    load_population_data,
)
from .synthetic_generator import generate_all_synthetic

_log = get_logger(__name__)


def _load_new_device_data(config: ColdStartConfig) -> pd.DataFrame | None:
    """
    Load real data for the new device if a CSV path is provided and non-empty.
    Returns None when the device has no real data yet (pure cold start scenario).
    """
    path = Path(config.new_device_data_path or "")
    if not path.exists() or not config.new_device_data_path:
        _log.info(
            "Aucune donnée réelle pour le nouveau device — mode bootstrap pur (synthétique uniquement)"
        )
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

    # Resample to regular hourly grid
    value_cols = [c for c in config.value_cols if c in df.columns]
    if not value_cols:
        _log.warning(
            "Colonnes %s absentes du fichier nouveau device — données ignorées",
            config.value_cols,
        )
        return None

    if config.device_col not in df.columns:
        df[config.device_col] = config.new_device_id
    if config.phase_col not in df.columns:
        df[config.phase_col] = config.new_device_phases[0] if config.new_device_phases else "L1"
    if config.item_col not in df.columns:
        df[config.item_col] = df[config.device_col].astype(str) + "_" + df[config.phase_col].astype(str)

    resampled = []
    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col)[value_cols].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()
            .ffill(limit=config.ffill_limit)
            .reset_index()
        )
        g[config.item_col]   = item_id
        parts = str(item_id).rsplit("_", 1)
        g[config.device_col] = parts[0]
        g[config.phase_col]  = parts[1] if len(parts) > 1 else ""
        g["is_synthetic"]    = False
        resampled.append(g)

    result = pd.concat(resampled, ignore_index=True)
    _log.info(
        "Données réelles nouveau device chargées : %d points, %d séries",
        len(result), result[config.item_col].nunique(),
    )
    return result


def _save_run_summary(
    result:     pd.DataFrame,
    summary:    pd.DataFrame,
    config:     ColdStartConfig,
    duration:   float,
    n_pop:      int,
    warmup_pct: float,
) -> None:
    per_series: dict = {}
    for _, row in summary.iterrows():
        per_series[row["item_id"]] = {
            "anomaly_count": int(row["anomaly_count"]),
            "anomaly_rate":  float(row["anomaly_rate"]),
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
        "mode":             "cold_start",
        "config": {
            "new_device_id":         config.new_device_id,
            "algorithm":             config.algorithm.value,
            "population_data_path":  config.population_data_path,
            "synthetic_days":        config.synthetic_days,
            "warmup_hours":          config.warmup_hours,
            "zscore_threshold":      config.zscore_threshold,
            "iqr_multiplier":        config.iqr_multiplier,
            "if_contamination":      config.if_contamination,
        },
        "results": {
            "population_devices":  n_pop,
            "total_rows":          len(result),
            "total_series":        result[config.item_col].nunique(),
            "total_anomalies":     int(result["is_anomaly"].sum()),
            "anomaly_rate":        round(float(result["is_anomaly"].mean()), 4),
            "point_anomalies":     int(result["is_point_anomaly"].sum()) if "is_point_anomaly" in result.columns else None,
            "regime_change_hours": int(result["is_regime_change"].sum()) if "is_regime_change" in result.columns else None,
            "warmup_complete_pct": round(warmup_pct, 2),
            "per_series":          per_series,
            "per_algo":            algo_breakdown,
        },
    }

    out_path = os.path.join(config.output_dir, "run_summary.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    _log.info("Run summary saved: %s", out_path)


def run(
    config:     Union[ColdStartConfig, str, Path, None] = None,
    hot_result: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the full cold-start anomaly detection pipeline.

    Parameters
    ----------
    config : ColdStartConfig | str | Path | None
        Configuration object or path to a YAML file.
        None loads from the canonical ColdStart/energy/config.yaml.
    hot_result : pd.DataFrame | None
        Optional HotStart detection results for the same time period.
        If provided, a cold-vs-hot comparison CSV is exported.

    Returns
    -------
    result  : pd.DataFrame  — per-hour detection results for the new device
    summary : pd.DataFrame  — per-series summary statistics
    """
    if config is None:
        config = ColdStartConfig.from_file()
    elif isinstance(config, (str, Path)):
        config = ColdStartConfig.from_yaml(config)
    else:
        config._validate()

    _log.info("═" * 60)
    _log.info("ARIA — Détection d'anomalies Cold Start")
    _log.info("Nouveau device : %s  |  Phases : %s", config.new_device_id, config.new_device_phases)
    _log.info("Algorithme     : %s", config.algorithm.value.upper())
    _log.info("Population     : %s", config.population_data_path)
    _log.info("Résultats      : %s", config.output_dir)
    _log.info("═" * 60)

    os.makedirs(config.output_dir, exist_ok=True)
    t_start = time.perf_counter()

    # ── Étape 1 — Chargement population ──────────────────────────────────────
    _log.info("Étape 1/6 — Chargement & profil population")
    pop_df = load_population_data(config)

    profiles: dict[str, PopulationProfile] = {}
    for col in config.value_cols:
        if col in pop_df.columns:
            profiles[col] = build_population_profile(pop_df, config, col)

    if not profiles:
        raise ValueError(
            f"Aucun profil construit. Colonnes demandées : {config.value_cols}\n"
            f"Colonnes disponibles dans le CSV population : {sorted(pop_df.columns.tolist())}"
        )

    # ── Étape 2 — Sauvegarde des profils ─────────────────────────────────────
    _log.info("Étape 2/6 — Sauvegarde profils population")
    for col, profile in profiles.items():
        profile_path = os.path.join(config.output_dir, f"population_profile_{col}.json")
        profile.to_json(profile_path)
        _log.info("Profile saved: %s  (%d devices)", profile_path, profile.n_devices)

    # ── Étape 3 — Génération données synthétiques ─────────────────────────────
    _log.info("Étape 3/6 — Génération données synthétiques (%d jours)", config.synthetic_days)
    synthetic_df = generate_all_synthetic(profiles, config)

    # ── Étape 4 — Initialisation & fit détecteur ──────────────────────────────
    _log.info("Étape 4/6 — Initialisation détecteur cold start")
    detector = ColdStartDetector(profiles=profiles, config=config)
    detector.fit(synthetic_df)

    # ── Étape 4b — Données réelles du nouveau device (si disponibles) ─────────
    real_df = _load_new_device_data(config)

    if real_df is not None and not real_df.empty:
        # Detect on real data only
        _log.info("Détection sur données réelles (%d points)", len(real_df))
        detection_df = real_df.copy()
    else:
        # No real data → detect on synthetic (demo / evaluation mode)
        _log.info(
            "Pas de données réelles — détection sur synthétique (%d points)",
            len(synthetic_df),
        )
        detection_df = synthetic_df.copy()

    # ── Étape 5 — Détection ────────────────────────────────────────────────────
    _log.info("Étape 5/6 — Détection (algo=%s)", config.algorithm.value)
    result = detector.detect(detection_df)

    # ── Résumé & export CSV ────────────────────────────────────────────────────
    _log.info("Étape 6/6 — Résumé, export CSV & visualisations")
    summary = anomaly_summary(result, config)

    warmup_pct = 0.0
    if "warmup_active" in result.columns:
        warmup_pct = 100.0 * float((~result["warmup_active"]).mean())

    _log.info("\n%s", summary.to_string(index=False))

    result_path  = os.path.join(config.output_dir, "coldstart_result.csv")
    summary_path = os.path.join(config.output_dir, "coldstart_summary.csv")
    result.to_csv(result_path,  index=False)
    summary.to_csv(summary_path, index=False)
    _log.info("Saved: %s", result_path)
    _log.info("Saved: %s", summary_path)

    # Optional cold vs hot comparison
    if hot_result is not None:
        cmp = comparison_summary(result, hot_result, config)
        if not cmp.empty:
            cmp_path = os.path.join(config.output_dir, "comparison_cold_vs_hot.csv")
            cmp.to_csv(cmp_path, index=False)
            _log.info("Saved: %s", cmp_path)

    # ── Visualisations ─────────────────────────────────────────────────────────
    out_path = Path(config.output_dir)
    old_pngs = list(out_path.glob("*.png"))
    if old_pngs:
        prev_dir = out_path / "prev"
        prev_dir.mkdir(exist_ok=True)
        for png in old_pngs:
            shutil.move(str(png), str(prev_dir / png.name))

    plot_anomaly_series(result,     config, config.output_dir)
    plot_algo_comparison(result,    config, config.output_dir)
    plot_population_vs_new_device(
        pop_df, detection_df, config, config.output_dir
    )

    duration = time.perf_counter() - t_start
    _save_run_summary(
        result, summary, config, duration,
        n_pop      = sum(p.n_devices for p in profiles.values()),
        warmup_pct = warmup_pct,
    )
    _log.info("Cold start pipeline terminé en %.1f s", duration)

    return result, summary
