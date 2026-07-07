from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

import pandas as pd

from common.logger import get_logger
from common.monthly_retrainer import MonthlyRetrainer
from .config import EnergyConfig
from .detector import EnergyAnomalyDetector
from .evaluator import (
    anomaly_summary,
    forecast_summary,
    plot_all_combined,
    plot_all_devices,
    plot_all_forecasts,
    plot_all_real_vs_pred,
)
from .forecaster import EnergyForecaster
from .preprocessor import clean_energy_data, load_energy_data, resample_energy

_log = get_logger(__name__)


def _compute_fingerprint(config: EnergyConfig) -> str:
    """Hash des paramètres + données pour détecter si quelque chose a changé entre deux runs."""
    parts: dict = {}

    data_path = Path(config.data_path)
    if data_path.exists():
        stat = data_path.stat()
        parts["data_mtime"] = stat.st_mtime
        parts["data_size"]  = stat.st_size
    else:
        parts["data_path"] = config.data_path

    parts.update({
        "value_cols":            config.value_cols,
        "model_name":            config.model_name,
        "threshold_strategy":    config.threshold_strategy.value,
        "k_sigma":               config.k_sigma,
        "context_length":        config.context_length,
        "prediction_length":     config.prediction_length,
        "slide_step":            config.slide_step,
        "min_features_anomalous": config.min_features_anomalous,
        "date_debut":            config.date_debut,
        "date_fin":              config.date_fin,
        "forecast_horizon":      config.forecast_horizon,
        "q_low":                 config.q_low,
        "q_high":                config.q_high,
        "alpha":                 config.alpha,
        "resample_freq":         config.resample_freq,
    })

    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _organize_output(df: pd.DataFrame, config: EnergyConfig) -> pd.DataFrame:
    id_cols = [
        c for c in (
            config.item_col, config.device_col,
            config.phase_col, config.timestamp_col,
        )
        if c in df.columns
    ]

    # pred_median/low/high sans suffixe → visualization uniquement, non exportées
    visualization_only = {"pred_median", "pred_low", "pred_high"}
    generated: set[str] = {
        "is_anomaly", "anomaly_score", "is_offline",
        "is_point_anomaly", "is_regime_change",
    } | visualization_only
    for col in config.value_cols:
        generated.update({
            f"pred_median_{col}", f"pred_low_{col}", f"pred_high_{col}",
            f"is_anomaly_{col}",  f"anomaly_score_{col}",
        })

    original  = [c for c in df.columns if c not in generated and c not in id_cols]
    detection: list[str] = []
    for col in config.value_cols:
        for prefix in ("pred_median", "pred_low", "pred_high", "is_anomaly", "anomaly_score"):
            named = f"{prefix}_{col}"
            if named in df.columns:
                detection.append(named)

    global_cols = [
        c for c in (
            "is_anomaly", "is_point_anomaly", "is_regime_change", "anomaly_score",
        )
        if c in df.columns
    ]

    ordered    = id_cols + original + detection + global_cols
    remaining  = [c for c in df.columns if c not in ordered and c not in visualization_only]

    return df[ordered + remaining]


def _validate_columns(df: pd.DataFrame, config: EnergyConfig) -> None:
    missing = [c for c in config.value_cols if c not in df.columns]
    if missing:
        available = [c for c in df.columns if c not in (
            config.timestamp_col, config.device_col,
            config.phase_col, config.item_col,
        )]
        raise ValueError(
            f"Colonne(s) introuvable(s) dans le CSV : {missing}\n"
            f"Colonnes disponibles : {sorted(available)}\n"
            f"Vérifiez la section 'detection.colonnes' dans config.yaml."
        )


def _save_run_summary(
    result:      pd.DataFrame,
    summary:     pd.DataFrame,
    forecast_df: pd.DataFrame,
    config:      EnergyConfig,
    duration:    float,
    fingerprint: str = "",
) -> None:
    per_col: dict = {}
    for col in config.value_cols:
        flag = f"is_anomaly_{col}"
        if flag in result.columns:
            per_col[col] = {"anomaly_count": int(result[flag].sum())}

    forecast_info: dict = {}
    if not forecast_df.empty:
        forecast_info = {
            "horizon_hours":  config.forecast_horizon,
            "total_alerts":   int(forecast_df["is_alert"].sum()),
            "HIGH":           int((forecast_df["alert_severity"] == "HIGH").sum()),
            "MEDIUM":         int((forecast_df["alert_severity"] == "MEDIUM").sum()),
            "LOW":            int((forecast_df["alert_severity"] == "LOW").sum()),
            "avg_confidence": round(float(forecast_df["confidence"].mean()), 3),
        }

    meta = {
        "run_timestamp":    datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 2),
        "fingerprint":      fingerprint,
        "config": {
            "data_path":           config.data_path,
            "value_cols":          config.value_cols,
            "threshold_strategy":  config.threshold_strategy.value,
            "k_sigma":             config.k_sigma,
            "context_length":      config.context_length,
            "prediction_length":   config.prediction_length,
            "forecast_horizon":    config.forecast_horizon,
        },
        "results": {
            "total_rows":          len(result),
            "total_series":        result[config.item_col].nunique(),
            "total_anomalies":     int(result["is_anomaly"].sum()),
            "anomaly_rate":        round(float(result["is_anomaly"].mean()), 4),
            "point_anomalies":     int(result["is_point_anomaly"].sum()) if "is_point_anomaly" in result.columns else None,
            "regime_change_hours": int(result["is_regime_change"].sum()) if "is_regime_change" in result.columns else None,
            "per_column":          per_col,
            "forecast":            forecast_info,
        },
    }

    out_path = os.path.join(config.output_dir, "run_summary.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    _log.info("Run summary saved: %s", out_path)


def run(
    config: Union[EnergyConfig, str, Path, None] = None,
    generate_plots: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the full energy anomaly detection pipeline.

    config : EnergyConfig   → use as-is (programmatic / CLI override)
             str | Path      → load from that YAML file
             None            → load from the canonical energy/config.yaml
    """
    if config is None:
        config = EnergyConfig.from_file()
    elif isinstance(config, (str, Path)):
        config = EnergyConfig.from_yaml(config)
    else:
        config._validate()

    _log.info("═" * 55)
    _log.info("ARIA — Détection d'anomalies énergétiques")
    _log.info("Stratégie  : %s", config.threshold_strategy.value.upper())
    _log.info("Fichier    : %s", config.data_path)
    _log.info("Colonnes   : %s", config.value_cols)
    _log.info("Résultats  : %s", config.output_dir)
    _log.info("═" * 55)

    os.makedirs(config.output_dir, exist_ok=True)
    current_fp = _compute_fingerprint(config)

    summary_json_path = os.path.join(config.output_dir, "run_summary.json")
    last_fp: str | None = None
    if os.path.exists(summary_json_path):
        try:
            with open(summary_json_path, encoding="utf-8") as fh:
                last_fp = json.load(fh).get("fingerprint")
        except (json.JSONDecodeError, KeyError):
            pass

    nothing_changed = last_fp is not None and last_fp == current_fp

    t_start = time.perf_counter()

    # ── Étape 1 — Chargement & Nettoyage ──────────────────────────────────
    _log.info("Étape 1/5 — Chargement & Nettoyage")
    df = load_energy_data(config)
    df = clean_energy_data(df, config)
    df = resample_energy(df, config)
    _log.info(
        "%d lignes | %d séries : %s",
        len(df), df[config.item_col].nunique(), sorted(df[config.item_col].unique()),
    )

    _validate_columns(df, config)

    # ── Étape 2a — Détection ──────────────────────────────────────────────
    _log.info("Étape 2a/5 — Détection Chronos (fenêtre glissante)")
    retrainer    = MonthlyRetrainer(config)
    detector     = EnergyAnomalyDetector(config)
    detector._load_pipeline()
    base_weights = retrainer.snapshot_base_weights(detector._pipeline)

    all_device_results: list[pd.DataFrame] = []
    for device_id in df[config.device_col].unique():
        device_df = df[df[config.device_col] == device_id]
        retrainer.load_checkpoint(str(device_id), detector._pipeline)
        device_result = detector.detect(device_df)
        all_device_results.append(device_result)
        retrainer.restore_base_weights(detector._pipeline, base_weights)

    result = pd.concat(all_device_results, ignore_index=True)

    # ── Étape 2b — Prévision préventive ───────────────────────────────────
    _log.info("Étape 2b/5 — Prévision préventive (%dh)", config.forecast_horizon)
    forecaster   = EnergyForecaster(config, detector.pipeline)
    forecast_df  = forecaster.forecast_all(df)

    # ── Étape 3 — Résumé ───────────────────────────────────────────────────
    _log.info("Étape 3/5 — Résumé")
    summary          = anomaly_summary(result, config)
    forecast_summary_ = forecast_summary(forecast_df, config)
    _log.info("\n%s", summary.to_string(index=False))
    if not forecast_summary_.empty:
        _log.info("Résumé prévisions :\n%s", forecast_summary_.to_string(index=False))

    # ── Étape 4 — Export CSV ───────────────────────────────────────────────
    _log.info("Étape 4/5 — Export CSV")
    result_path    = os.path.join(config.output_dir, "anomalies_result.csv")
    summary_path   = os.path.join(config.output_dir, "anomalies_summary.csv")
    forecast_path  = os.path.join(config.output_dir, "forecast_result.csv")
    fc_alerts_path = os.path.join(config.output_dir, "forecast_alerts.csv")
    fc_summary_path = os.path.join(config.output_dir, "forecast_summary.csv")

    _organize_output(result, config).to_csv(result_path, index=False)
    summary.to_csv(summary_path, index=False)
    _log.info("Saved: %s", result_path)
    _log.info("Saved: %s", summary_path)

    if not forecast_df.empty:
        forecast_df.to_csv(forecast_path, index=False)
        forecast_df[forecast_df["is_alert"]].to_csv(fc_alerts_path, index=False)
        forecast_summary_.to_csv(fc_summary_path, index=False)
        _log.info("Saved: %s", forecast_path)
        _log.info("Saved: %s  (%d alertes)", fc_alerts_path, int(forecast_df["is_alert"].sum()))
        _log.info("Saved: %s", fc_summary_path)

    # ── Libération mémoire GPU avant matplotlib ───────────────────────────
    try:
        import gc, torch
        detector._pipeline = None
        forecaster._pipeline = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
    except Exception:
        pass

    # ── Étape 5 — Visualisations ───────────────────────────────────────────
    if generate_plots:
        _log.info("Étape 5/5 — Visualisations")

        out_path = Path(config.output_dir)
        old_pngs = list(out_path.glob("*.png"))

        if nothing_changed and old_pngs:
            _log.info(
                "Visualisations ignorées — %d PNG existants conservés (fingerprint identique)",
                len(old_pngs),
            )
        else:
            if old_pngs:
                prev_dir = out_path / "prev"
                prev_dir.mkdir(exist_ok=True)
                for png in old_pngs:
                    shutil.move(str(png), str(prev_dir / png.name))
                _log.info(
                    "%d ancien(s) PNG déplacé(s) vers %s",
                    len(old_pngs), prev_dir,
                )

            plot_all_real_vs_pred(result, config)
            plot_all_combined(result, config)
            plot_all_forecasts(result, forecast_df, config)
            plot_all_devices(result, config)
    else:
        _log.info("Étape 5/5 — Visualisations ignorées (generate_plots=False)")

    duration = time.perf_counter() - t_start
    _save_run_summary(result, summary, forecast_df, config, duration, fingerprint=current_fp)
    _log.info("Pipeline terminé en %.1f s", duration)

    return result, summary
