"""
HotStart Fuel Detector — adapté du détecteur gaz.
Fuel specifics:
  - Offline = véhicule garé (consommation==0, vitesse==0) → exclu du scoring
  - Anomalies : sur-consommation, vitesse excessive, comportement erratique
  - regime_change_hours = 72h (arrêt weekend = normal, dérive > 3j = anomalie)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common.base_detector import ChronosDetector
from common.logger import get_logger
from common.threshold import DynamicThresholdEngine
from .calibrator import DeviceProfile, DeviceProfileStore, build_profile
from .config import FuelConfig

_log = get_logger(__name__)


def _classify_anomaly_type(flags: np.ndarray, threshold: int) -> tuple[np.ndarray, np.ndarray]:
    is_point  = np.zeros(len(flags), dtype=bool)
    is_regime = np.zeros(len(flags), dtype=bool)
    if not flags.any():
        return is_point, is_regime
    padded = np.concatenate([[False], flags.astype(bool), [False]])
    starts = np.where(~padded[:-1] &  padded[1:])[0]
    ends   = np.where( padded[:-1] & ~padded[1:])[0]
    for s, e in zip(starts, ends):
        if (e - s) > threshold:
            is_regime[s:e] = True
        else:
            is_point[s:e]  = True
    return is_point, is_regime


class FuelAnomalyDetector(ChronosDetector):

    def __init__(self, config: FuelConfig) -> None:
        super().__init__(
            model_name        = config.model_name,
            device            = config.device,
            context_length    = config.context_length,
            prediction_length = config.prediction_length,
            num_samples       = config.num_samples,
            q_low             = config.q_low,
            q_high            = config.q_high,
        )
        self.config            = config
        self._threshold_engine = DynamicThresholdEngine(
            strategy     = config.threshold_strategy,
            k_sigma      = config.k_sigma,
            alpha        = config.alpha,
            max_cv_scale = config.max_cv_scale,
        )

    @property
    def pipeline(self):
        return self._pipeline

    # ── Calibration ───────────────────────────────────────────────────────

    def _collect_errors_for_col(
        self, group: pd.DataFrame, item_id: str, col: str,
        timestamp_col: str, calib_end: int,
    ) -> np.ndarray:
        series = group.set_index(timestamp_col)[col]
        total  = calib_end
        step   = self.config.slide_step
        if total >= self.context_length:
            first_win = self.context_length
        else:
            min_ctx   = max(step * 3, self.prediction_length * 2)
            first_win = min(min_ctx, max(0, total - step))
        if first_win <= 0 or first_win >= total:
            return np.array([], dtype=float)
        error_chunks: list[np.ndarray] = []
        for w_start in range(first_win, total, step):
            w_end    = min(w_start + self.prediction_length, total)
            pred_len = w_end - w_start
            if pred_len < 1:
                break
            ctx_series = series.iloc[max(0, w_start - self.context_length): w_start].dropna()
            pred = self._predict_window(ctx_series, item_id, pred_len)
            if pred is None:
                continue
            actual  = series.iloc[w_start:w_end].to_numpy()
            offline = actual == 0
            err     = np.where(offline, np.nan, np.abs(actual - pred.pred_median))
            error_chunks.append(err)
        return np.concatenate(error_chunks) if error_chunks else np.array([], dtype=float)

    def calibrate_all(
        self, df: pd.DataFrame, store: DeviceProfileStore, force: bool = False,
    ) -> None:
        self._load_pipeline()
        cfg   = self.config
        items = df[cfg.item_col].unique()
        to_calibrate = [it for it in items if force or not store.has(str(it))]
        _log.info(
            "Phase 1 - Calibration fuel : %d/%d device(s) (fenetre=%dh)",
            len(to_calibrate), len(items), cfg.calibration_hours,
        )
        for item_id in to_calibrate:
            group = (
                df[df[cfg.item_col] == item_id]
                .sort_values(cfg.timestamp_col).reset_index(drop=True)
            )
            calib_end = min(cfg.calibration_hours, len(group))
            if calib_end < cfg.prediction_length * 3:
                _log.warning("[%s] donnees insuffisantes pour calibration - skipped", item_id)
                continue
            all_errors: list[np.ndarray] = []
            for col in cfg.value_cols:
                errs = self._collect_errors_for_col(
                    group, str(item_id), col, cfg.timestamp_col, calib_end,
                )
                all_errors.append(errs)
            combined = np.concatenate(all_errors) if all_errors else np.array([], dtype=float)
            profile  = build_profile(combined, str(item_id), calib_end)
            store.put(profile)
            _log.info(
                "[%s] profil : n=%d  mean=%.4f  p95=%.4f  p99=%.4f",
                item_id, profile.n_errors, profile.mean_err, profile.p95, profile.p99,
            )
        store.save()

    # ── Detection ─────────────────────────────────────────────────────────

    def _detect_for_col(
        self, group: pd.DataFrame, item_id: str, col: str,
        timestamp_col: str, profile: DeviceProfile | None = None,
    ) -> pd.DataFrame:
        for out in (f"pred_median_{col}", f"pred_low_{col}", f"pred_high_{col}"):
            group[out] = np.nan
        group[f"is_anomaly_{col}"]    = False
        group[f"anomaly_score_{col}"] = 0.0

        series = group.set_index(timestamp_col)[col]
        total  = len(series)
        step   = self.config.slide_step

        use_profile = (
            profile is not None
            and self.config.calibration_active
            and profile.n_errors > 0
            and profile.p99 > 0
        )

        if total >= self.context_length:
            first_win = self.context_length
        else:
            min_ctx   = max(step * 3, self.prediction_length * 2)
            first_win = min(min_ctx, max(0, total - step))

        window_positions = list(range(first_win, total, step)) if first_win > 0 else []
        if not window_positions:
            _log.warning("[%s][%s] pas assez de donnees", item_id, col)
            return group

        for w_start in window_positions:
            w_end    = min(w_start + self.prediction_length, total)
            pred_len = w_end - w_start
            if pred_len < 1:
                break
            eval_idx   = group.index[w_start:w_end]
            n          = len(eval_idx)
            ctx_series = series.iloc[max(0, w_start - self.context_length): w_start].dropna()
            pred       = self._predict_window(ctx_series, item_id, pred_len)
            if pred is None:
                continue

            group.loc[eval_idx, f"pred_median_{col}"] = pred.pred_median[:n]
            actual  = group.loc[eval_idx, col].to_numpy()
            offline = actual == 0   # véhicule garé

            if use_profile:
                threshold = max(profile.p99 * self.config.calibration_threshold_factor, 1e-6)
                abs_err   = np.abs(actual - pred.pred_median[:n])
                is_anom   = (abs_err > threshold) & ~offline
                score     = np.clip(abs_err / threshold, 0.0, 10.0)
                score     = np.where(offline, 0.0, score)
                group.loc[eval_idx, f"pred_low_{col}"]  = pred.pred_median[:n] - threshold
                group.loc[eval_idx, f"pred_high_{col}"] = pred.pred_median[:n] + threshold
            else:
                bounds = self._threshold_engine.compute(
                    context=pred.context_series, pred_low=pred.pred_low,
                    pred_median=pred.pred_median, pred_high=pred.pred_high,
                )
                is_anom = ((actual < bounds.low[:n]) | (actual > bounds.high[:n])) & ~offline
                score   = self._anomaly_score(actual, bounds.low[:n], bounds.high[:n])
                score   = np.where(offline, 0.0, score)
                group.loc[eval_idx, f"pred_low_{col}"]  = bounds.low[:n]
                group.loc[eval_idx, f"pred_high_{col}"] = bounds.high[:n]

            group.loc[eval_idx, f"is_anomaly_{col}"]    = is_anom
            group.loc[eval_idx, f"anomaly_score_{col}"] = score

        _log.info("[%s][%s] %d anomalies", item_id, col, int(group[f"is_anomaly_{col}"].sum()))
        return group

    def detect(
        self, df: pd.DataFrame, profile_store: DeviceProfileStore | None = None,
    ) -> pd.DataFrame:
        self._load_pipeline()
        cfg   = self.config
        items = df[cfg.item_col].unique()

        all_results = []
        for item_id in items:
            profile = profile_store.get(str(item_id)) if profile_store else None
            group   = df[df[cfg.item_col] == item_id].sort_values(cfg.timestamp_col).copy()

            group["is_anomaly"]    = False
            group["anomaly_score"] = 0.0
            for vis in ("pred_median", "pred_low", "pred_high"):
                group[vis] = np.nan

            for col in cfg.value_cols:
                group = self._detect_for_col(group, item_id, col, cfg.timestamp_col, profile)
                group["anomaly_score"] = group[
                    ["anomaly_score", f"anomaly_score_{col}"]
                ].max(axis=1)

            flag_cols = [f"is_anomaly_{col}" for col in cfg.value_cols if f"is_anomaly_{col}" in group.columns]
            if flag_cols:
                vote = pd.concat([group[c].astype(int) for c in flag_cols], axis=1).sum(axis=1)
                group["is_anomaly"] = vote >= cfg.min_features_anomalous

            primary = cfg.value_col
            group["pred_median"] = group[f"pred_median_{primary}"]
            group["pred_low"]    = group[f"pred_low_{primary}"]
            group["pred_high"]   = group[f"pred_high_{primary}"]

            all_results.append(group)

        final = pd.concat(all_results, ignore_index=True)
        _log.info("Detection complete - %d anomalies total", int(final["is_anomaly"].sum()))

        threshold  = cfg.regime_change_hours
        point_all  = np.zeros(len(final), dtype=bool)
        regime_all = np.zeros(len(final), dtype=bool)
        for item_id in items:
            mask  = (final[cfg.item_col] == item_id).to_numpy()
            flags = final.loc[mask, "is_anomaly"].to_numpy()
            pt, rg = _classify_anomaly_type(flags, threshold)
            point_all[mask]  = pt
            regime_all[mask] = rg

        final["is_point_anomaly"] = point_all
        final["is_regime_change"] = regime_all
        final["is_offline"]       = final[cfg.value_col] == 0
        return final
