from __future__ import annotations

import numpy as np
import pandas as pd

from common.base_detector import ChronosDetector
from common.logger import get_logger
from common.threshold import DynamicThresholdEngine
from .calibrator import DeviceProfile, DeviceProfileStore, build_profile
from .config import WaterConfig

_log = get_logger(__name__)


def _classify_anomaly_type(
    flags:     np.ndarray,
    threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    is_point  = np.zeros(len(flags), dtype=bool)
    is_regime = np.zeros(len(flags), dtype=bool)

    if not flags.any():
        return is_point, is_regime

    padded = np.concatenate([[False], flags.astype(bool), [False]])
    starts = np.where(~padded[:-1] & padded[1:])[0]
    ends   = np.where( padded[:-1] & ~padded[1:])[0]

    for s, e in zip(starts, ends):
        if (e - s) > threshold:
            is_regime[s:e] = True
        else:
            is_point[s:e]  = True

    return is_point, is_regime


class WaterAnomalyDetector(ChronosDetector):

    def __init__(self, config: WaterConfig) -> None:
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

    # ── Phase 1 helpers ───────────────────────────────────────────────────

    def _collect_errors_for_col(
        self,
        group:         pd.DataFrame,
        item_id:       str,
        col:           str,
        timestamp_col: str,
        calib_end:     int,
    ) -> np.ndarray:
        """
        Sliding window on group[:calib_end]. Returns |actual − pred_median|
        for every non-offline point where a prediction was obtained.
        """
        series = group.set_index(timestamp_col)[col]
        total  = calib_end
        step   = self.config.slide_step

        if total >= self.context_length:
            first_win = self.context_length
        else:
            min_ctx   = max(step * 3, self.prediction_length * 2)
            first_win = min(min_ctx, max(0, total - step))

        if first_win <= 0 or first_win >= total:
            _log.warning(
                "[%s][%s] calibration: données insuffisantes (%d rows)", item_id, col, total,
            )
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
        self,
        df:    pd.DataFrame,
        store: DeviceProfileStore,
        force: bool = False,
    ) -> None:
        """
        Phase 1 — Calibration.
        For each device, runs sliding-window predictions over the first
        `calibration_hours` rows and stores the resulting error distribution
        (mean, std, p95, p99) in the DeviceProfileStore.
        Skips devices that already have a profile unless force=True.
        """
        self._load_pipeline()
        cfg   = self.config
        items = df[cfg.item_col].unique()

        to_calibrate = [it for it in items if force or not store.has(str(it))]

        _log.info("═" * 55)
        _log.info(
            "Phase 1 — Calibration : %d/%d device(s)  (fenêtre=%dh)",
            len(to_calibrate), len(items), cfg.calibration_hours,
        )
        _log.info("═" * 55)

        for item_id in to_calibrate:
            group = (
                df[df[cfg.item_col] == item_id]
                .sort_values(cfg.timestamp_col)
                .reset_index(drop=True)
            )
            total     = len(group)
            calib_end = min(cfg.calibration_hours, total)

            min_rows = cfg.prediction_length * 3
            if calib_end < min_rows:
                _log.warning(
                    "[%s] calibration: données insuffisantes (%d rows < %d min) — skipped",
                    item_id, calib_end, min_rows,
                )
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
                "[%s] profil : n=%d  mean=%.4f  std=%.4f  p95=%.4f  p99=%.4f",
                item_id, profile.n_errors, profile.mean_err, profile.std_err,
                profile.p95, profile.p99,
            )

        store.save()
        _log.info("Phase 1 terminée — %d profils", len(store.ids()))

    # ── Phase 2 : detection ───────────────────────────────────────────────

    def _detect_for_col(
        self,
        group:         pd.DataFrame,
        item_id:       str,
        col:           str,
        timestamp_col: str,
        profile:       DeviceProfile | None = None,
    ) -> pd.DataFrame:
        for out in (f"pred_median_{col}", f"pred_low_{col}", f"pred_high_{col}"):
            group[out] = np.nan
        group[f"is_anomaly_{col}"]      = False
        group[f"anomaly_score_{col}"]   = 0.0
        group[f"is_high_anomaly_{col}"] = False
        group[f"is_low_anomaly_{col}"]  = False

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
            _log.warning("[%s][%s] not enough data for even one window", item_id, col)
            return group

        mode_label = "profil" if use_profile else self.config.threshold_strategy.value
        _log.info(
            "[%s][%s] sliding window: %d windows (step=%dh, mode=%s)",
            item_id, col, len(window_positions), step, mode_label,
        )

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
            offline = actual == 0

            if use_profile:
                threshold = profile.p99 * self.config.calibration_threshold_factor
                threshold = max(threshold, 1e-6)
                abs_err   = np.abs(actual - pred.pred_median[:n])
                is_anom   = (abs_err > threshold) & ~offline
                score     = np.clip(abs_err / threshold, 0.0, 10.0)
                score     = np.where(offline, 0.0, score)
                is_high   = (actual > pred.pred_median[:n] + threshold) & ~offline
                is_low    = (actual < pred.pred_median[:n] - threshold) & ~offline
                # symmetric band centred on prediction for visualisation
                group.loc[eval_idx, f"pred_low_{col}"]  = pred.pred_median[:n] - threshold
                group.loc[eval_idx, f"pred_high_{col}"] = pred.pred_median[:n] + threshold
            else:
                bounds = self._threshold_engine.compute(
                    context     = pred.context_series,
                    pred_low    = pred.pred_low,
                    pred_median = pred.pred_median,
                    pred_high   = pred.pred_high,
                )
                is_anom = ((actual < bounds.low[:n]) | (actual > bounds.high[:n])) & ~offline
                score   = self._anomaly_score(actual, bounds.low[:n], bounds.high[:n])
                score   = np.where(offline, 0.0, score)
                is_high = (actual > bounds.high[:n]) & ~offline
                is_low  = (actual < bounds.low[:n]) & ~offline
                group.loc[eval_idx, f"pred_low_{col}"]  = bounds.low[:n]
                group.loc[eval_idx, f"pred_high_{col}"] = bounds.high[:n]

            group.loc[eval_idx, f"is_anomaly_{col}"]      = is_anom
            group.loc[eval_idx, f"anomaly_score_{col}"]   = score
            group.loc[eval_idx, f"is_high_anomaly_{col}"] = is_high
            group.loc[eval_idx, f"is_low_anomaly_{col}"]  = is_low

        total_anom = int(group[f"is_anomaly_{col}"].sum())
        _log.info("[%s][%s] %d anomalies across full series", item_id, col, total_anom)
        return group

    def detect(
        self,
        df:            pd.DataFrame,
        profile_store: DeviceProfileStore | None = None,
    ) -> pd.DataFrame:
        self._load_pipeline()
        cfg        = self.config
        items      = df[cfg.item_col].unique()
        value_cols = cfg.value_cols

        rows_per_series = len(df) // max(len(items), 1)
        windows_per_col = max(0, (rows_per_series - cfg.context_length) // cfg.slide_step)
        total_calls     = windows_per_col * len(items) * len(value_cols)
        estimated_min   = total_calls * 3 / 60

        calibration_mode = cfg.calibration_active and profile_store is not None
        _log.info(
            "Starting detection: %d devices × %d column(s) × %d windows = %d Chronos calls",
            len(items), len(value_cols), windows_per_col, total_calls,
        )
        _log.info("Columns   : %s", value_cols)
        _log.info(
            "Strategy  : %s  |  slide_step=%dh",
            "PROFILE_CALIBRÉ" if calibration_mode else cfg.threshold_strategy.value.upper(),
            cfg.slide_step,
        )
        _log.info("Estimated : ~%.0f min on CPU", estimated_min)

        all_results = []

        for item_id in items:
            profile = profile_store.get(str(item_id)) if profile_store else None
            if calibration_mode and profile is not None:
                _log.info(
                    "[%s] seuil profil : p99=%.4f × %.1f = %.4f",
                    item_id, profile.p99, cfg.calibration_threshold_factor,
                    profile.p99 * cfg.calibration_threshold_factor,
                )
            elif calibration_mode:
                _log.warning(
                    "[%s] aucun profil trouvé — fallback k_sigma=%s", item_id, cfg.k_sigma,
                )

            group = df[df[cfg.item_col] == item_id].sort_values(cfg.timestamp_col).copy()

            group["is_anomaly"]    = False
            group["anomaly_score"] = 0.0
            for vis in ("pred_median", "pred_low", "pred_high"):
                group[vis] = np.nan

            for col in value_cols:
                group = self._detect_for_col(group, item_id, col, cfg.timestamp_col, profile)
                group["anomaly_score"] = group[
                    ["anomaly_score", f"anomaly_score_{col}"]
                ].max(axis=1)

            flag_cols = [f"is_anomaly_{col}" for col in value_cols if f"is_anomaly_{col}" in group.columns]
            if flag_cols:
                vote = pd.concat(
                    [group[c].astype(int) for c in flag_cols], axis=1
                ).sum(axis=1)
                group["is_anomaly"] = vote >= cfg.min_features_anomalous

            group["is_high_anomaly"] = False
            group["is_low_anomaly"]  = False
            high_fcols = [f"is_high_anomaly_{c}" for c in value_cols if f"is_high_anomaly_{c}" in group.columns]
            low_fcols  = [f"is_low_anomaly_{c}"  for c in value_cols if f"is_low_anomaly_{c}"  in group.columns]
            if high_fcols:
                h_vote = pd.concat([group[c].astype(int) for c in high_fcols], axis=1).sum(axis=1)
                group["is_high_anomaly"] = (h_vote >= cfg.min_features_anomalous) & group["is_anomaly"]
            if low_fcols:
                l_vote = pd.concat([group[c].astype(int) for c in low_fcols], axis=1).sum(axis=1)
                group["is_low_anomaly"] = (l_vote >= cfg.min_features_anomalous) & group["is_anomaly"]

            primary = cfg.value_col
            group["pred_median"] = group[f"pred_median_{primary}"]
            group["pred_low"]    = group[f"pred_low_{primary}"]
            group["pred_high"]   = group[f"pred_high_{primary}"]

            all_results.append(group)

        final = pd.concat(all_results, ignore_index=True)
        _log.info("Detection complete — %d anomalies total", int(final["is_anomaly"].sum()))
        _log.info(
            "Direction — %d anomalies élevées (pic haut)  |  %d anomalies faibles (pic bas)",
            int(final["is_high_anomaly"].sum()), int(final["is_low_anomaly"].sum()),
        )

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

        n_point  = int(final["is_point_anomaly"].sum())
        n_regime = int(final["is_regime_change"].sum())
        _log.info(
            "Classification (seuil=%dh) — %d anomalies ponctuelles  |  %d heures changement de régime",
            threshold, n_point, n_regime,
        )
        return final
