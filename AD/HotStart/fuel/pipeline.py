"""HotStart Fuel pipeline — adapté du pipeline gaz."""
from __future__ import annotations

import hashlib
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
from .calibrator import DeviceProfileStore, build_profile, check_drift
from .config import FuelConfig
from .detector import FuelAnomalyDetector
from .evaluator import (
    anomaly_summary, forecast_summary,
    plot_overview_anomaly, plot_overview_real_vs_pred, plot_overview_forecast,
)
from .forecaster import FuelForecaster
from .preprocessor import clean_fuel_data, load_fuel_data, resample_fuel

_log = get_logger(__name__)


def _fingerprint(config: FuelConfig) -> str:
    parts: dict = {}
    data_path = Path(config.data_path)
    if data_path.exists():
        stat = data_path.stat()
        parts["data_mtime"] = stat.st_mtime
        parts["data_size"]  = stat.st_size
    else:
        parts["data_path"] = config.data_path
    parts.update({
        "value_cols":             config.value_cols,
        "model_name":             config.model_name,
        "threshold_strategy":     config.threshold_strategy.value,
        "k_sigma":                config.k_sigma,
        "context_length":         config.context_length,
        "prediction_length":      config.prediction_length,
        "slide_step":             config.slide_step,
        "min_features_anomalous": config.min_features_anomalous,
        "date_debut":             config.date_debut,
        "date_fin":               config.date_fin,
        "forecast_horizon":       config.forecast_horizon,
        "calibration_active":     config.calibration_active,
        "calibration_hours":      config.calibration_hours,
    })
    return hashlib.md5(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _organize_output(df: pd.DataFrame, config: FuelConfig) -> pd.DataFrame:
    id_cols   = [c for c in (config.item_col, config.device_col, config.timestamp_col) if c in df.columns]
    vis_only  = {"pred_median", "pred_low", "pred_high"}
    generated: set[str] = {
        "is_anomaly", "anomaly_score", "is_offline", "is_point_anomaly", "is_regime_change",
    } | vis_only
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
        c for c in ("is_anomaly", "is_point_anomaly", "is_regime_change", "anomaly_score")
        if c in df.columns
    ]
    ordered   = id_cols + original + detection + global_cols
    remaining = [c for c in df.columns if c not in ordered and c not in vis_only]
    return df[ordered + remaining]


def _validate_columns(df: pd.DataFrame, config: FuelConfig) -> None:
    missing = [c for c in config.value_cols if c not in df.columns]
    if missing:
        available = [c for c in df.columns if c not in (
            config.timestamp_col, config.device_col, config.item_col,
        )]
        raise ValueError(
            f"Colonne(s) introuvable(s) dans le CSV : {missing}\n"
            f"Colonnes disponibles : {sorted(available)}\n"
            f"Verifiez la section 'detection.colonnes' dans config.yaml."
        )


def _save_run_summary(
    result: pd.DataFrame, summary: pd.DataFrame, forecast_df: pd.DataFrame,
    config: FuelConfig, duration: float, fingerprint: str = "",
    profile_store: DeviceProfileStore | None = None,
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

    calibration_info: dict = {}
    if config.calibration_active and profile_store is not None:
        profiles = {
            did: {
                "n_errors":  p.n_errors,
                "mean_err":  round(p.mean_err, 4),
                "p95":       round(p.p95, 4),
                "p99":       round(p.p99, 4),
                "threshold": round(p.p99 * config.calibration_threshold_factor, 4),
                "calibrated_at": p.calibrated_at,
            }
            for did in profile_store.ids()
            if (p := profile_store.get(did)) is not None
        }
        calibration_info = {
            "active":            True,
            "calibration_hours": config.calibration_hours,
            "threshold_factor":  config.calibration_threshold_factor,
            "profile_file":      str(config.calibration_profile_path),
            "devices":           profiles,
        }

    meta = {
        "run_timestamp":    datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 2),
        "fingerprint":      fingerprint,
        "domain":           "fuel",
        "config": {
            "data_path":    config.data_path,
            "value_cols":   config.value_cols,
            "k_sigma":      config.k_sigma,
            "context_length":             config.context_length,
            "forecast_horizon":           config.forecast_horizon,
            "calibration_active":         config.calibration_active,
            "calibration_threshold_factor": config.calibration_threshold_factor,
        },
        "calibration": calibration_info,
        "results": {
            "total_rows":          len(result),
            "total_devices":       result[config.item_col].nunique(),
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
    config: Union[FuelConfig, str, Path, None] = None,
    generate_plots: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if config is None:
        config = FuelConfig.from_file()
    elif isinstance(config, (str, Path)):
        config = FuelConfig.from_yaml(config)
    else:
        config._validate()

    _log.info("=" * 55)
    _log.info("ARIA - Detection d'anomalies Carburant (Fuel)")
    _log.info(
        "Strategie  : %s",
        "PROFIL_CALIBRE" if config.calibration_active else config.threshold_strategy.value.upper(),
    )
    _log.info("Fichier    : %s", config.data_path)
    _log.info("Colonnes   : %s", config.value_cols)
    _log.info("Resultats  : %s", config.output_dir)
    _log.info("=" * 55)

    os.makedirs(config.output_dir, exist_ok=True)
    current_fp = _fingerprint(config)

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

    # ── Étape 1 — Chargement & Nettoyage ─────────────────────────────────
    _log.info("Etape 1/5 - Chargement & Nettoyage")
    df = load_fuel_data(config)
    df = clean_fuel_data(df, config)
    df = resample_fuel(df, config)
    _log.info(
        "%d lignes | %d vehicules : %s",
        len(df), df[config.item_col].nunique(), sorted(df[config.item_col].unique()),
    )
    _validate_columns(df, config)

    detector      = FuelAnomalyDetector(config)
    profile_store: DeviceProfileStore | None = None

    # ── Phase 1 — Calibration adaptative ─────────────────────────────────
    if config.calibration_active:
        _log.info("Etape 1.5/5 - Calibration adaptative")
        profile_store = DeviceProfileStore(config.calibration_profile_path)
        profile_store.load()
        devices_in_data      = {str(d) for d in df[config.item_col].unique()}
        devices_with_profile = set(profile_store.ids())
        missing              = devices_in_data - devices_with_profile
        if missing or config.calibration_force:
            detector.calibrate_all(df, profile_store, force=config.calibration_force)
        else:
            _log.info(
                "Profils existants pour %d vehicule(s) - calibration ignoree",
                len(devices_with_profile),
            )

    # ── Étape 2a — Détection ─────────────────────────────────────────────
    _log.info("Etape 2a/5 - Detection Chronos (fenetre glissante)")
    result = detector.detect(df, profile_store=profile_store)

    # ── Phase 3 — Drift ───────────────────────────────────────────────────
    if config.calibration_active and profile_store is not None:
        _log.info("Etape 2a.5 - Drift detection")
        drift_updated = False
        for item_id in result[config.item_col].unique():
            profile = profile_store.get(str(item_id))
            if profile is None:
                continue
            group      = result[result[config.item_col] == item_id]
            all_errors: list[np.ndarray] = []
            for col in config.value_cols:
                pred_col = f"pred_median_{col}"
                if pred_col not in group.columns:
                    continue
                actual = group[col].to_numpy()
                pred   = group[pred_col].to_numpy()
                mask   = np.isfinite(pred) & (actual != 0)
                if mask.sum() == 0:
                    continue
                all_errors.append(np.abs(actual[mask] - pred[mask]))
            if not all_errors:
                continue
            combined = np.concatenate(all_errors)
            if check_drift(profile, combined, config.calibration_drift_z):
                updated = build_profile(combined, str(item_id), len(combined))
                profile_store.put(updated)
                drift_updated = True
                _log.warning("[%s] profil mis a jour (drift detecte)", item_id)
        if drift_updated:
            profile_store.save()

    # ── Étape 2b — Prévision préventive ──────────────────────────────────
    _log.info("Etape 2b/5 - Prevision preventive (%dh)", config.forecast_horizon)
    forecaster  = FuelForecaster(config, detector.pipeline)
    forecast_df = forecaster.forecast_all(df)

    # ── Étape 3 — Résumé ─────────────────────────────────────────────────
    _log.info("Etape 3/5 - Resume")
    summary           = anomaly_summary(result, config)
    forecast_summary_ = forecast_summary(forecast_df, config)
    _log.info("\n%s", summary.to_string(index=False))

    # ── Étape 4 — Export CSV ─────────────────────────────────────────────
    _log.info("Etape 4/5 - Export CSV")
    result_path     = os.path.join(config.output_dir, "anomalies_result.csv")
    summary_path    = os.path.join(config.output_dir, "anomalies_summary.csv")
    forecast_path   = os.path.join(config.output_dir, "forecast_result.csv")
    fc_alerts_path  = os.path.join(config.output_dir, "forecast_alerts.csv")
    fc_summary_path = os.path.join(config.output_dir, "forecast_summary.csv")

    _organize_output(result, config).to_csv(result_path, index=False)
    summary.to_csv(summary_path, index=False)
    _log.info("Saved: %s", result_path)

    if not forecast_df.empty:
        forecast_df.to_csv(forecast_path, index=False)
        forecast_df[forecast_df["is_alert"]].to_csv(fc_alerts_path, index=False)
        forecast_summary_.to_csv(fc_summary_path, index=False)
        _log.info("Forecast alerts: %s", fc_alerts_path)

    # ── Étape 5 — Visualisations ─────────────────────────────────────────
    if generate_plots:
        _log.info("Etape 5/5 - Visualisations")
        out_path = Path(config.output_dir)
        old_pngs = list(out_path.glob("*.png"))

        if nothing_changed and old_pngs:
            _log.info("Visualisations ignorees - PNG existants conserves (fingerprint identique)")
        else:
            if old_pngs:
                prev_dir = out_path / "prev"
                prev_dir.mkdir(exist_ok=True)
                for png in old_pngs:
                    shutil.move(str(png), str(prev_dir / png.name))
            plot_overview_anomaly(result, config)
            plot_overview_real_vs_pred(result, config)
            plot_overview_forecast(result, forecast_df, config)
    else:
        _log.info("Etape 5/5 - Visualisations ignorees (generate_plots=False)")

    duration = time.perf_counter() - t_start
    _save_run_summary(
        result, summary, forecast_df, config, duration,
        fingerprint=current_fp, profile_store=profile_store,
    )
    _log.info("Pipeline fuel termine en %.1f s", duration)
    return result, summary
