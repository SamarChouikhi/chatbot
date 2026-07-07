from __future__ import annotations

import numpy as np
import pandas as pd

from common.base_detector import ChronosDetector
from common.logger import get_logger
from .config import EnergyConfig
from .threshold import DynamicThresholdEngine

_log = get_logger(__name__)


def _classify_anomaly_type(
    flags: np.ndarray,
    threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    is_point  = np.zeros(len(flags), dtype=bool)
    is_regime = np.zeros(len(flags), dtype=bool)

    if not flags.any():
        return is_point, is_regime

    # RLE via padding : détecte les fronts False→True et True→False en O(n)
    padded = np.concatenate([[False], flags.astype(bool), [False]])
    starts = np.where(~padded[:-1] & padded[1:])[0]
    ends   = np.where( padded[:-1] & ~padded[1:])[0]

    for s, e in zip(starts, ends):
        if (e - s) > threshold:
            is_regime[s:e] = True
        else:
            is_point[s:e]  = True

    return is_point, is_regime


class EnergyAnomalyDetector(ChronosDetector):

    def __init__(self, config: EnergyConfig) -> None:
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

    # ── Sliding-window detection for one column ───────────────────────────
    def _detect_for_col(
        self,
        group:         pd.DataFrame,
        item_id:       str,
        col:           str,
        timestamp_col: str,
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

        if total >= self.context_length:
            first_win = self.context_length
        else:
            min_ctx   = max(step * 3, self.prediction_length * 2)
            first_win = min(min_ctx, max(0, total - step))
        window_positions = list(range(first_win, total, step)) if first_win > 0 else []
        if not window_positions:
            _log.warning("[%s][%s] not enough data for even one window", item_id, col)
            return group

        _log.info(
            "[%s][%s] sliding window: %d windows (step=%dh, coverage=%.0f%%)",
            item_id, col, len(window_positions), step,
            min(100.0,
                len(window_positions) * self.prediction_length
                / max(total - self.context_length, 1) * 100),
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

            bounds = self._threshold_engine.compute(
                context     = pred.context_series,
                pred_low    = pred.pred_low,
                pred_median = pred.pred_median,
                pred_high   = pred.pred_high,
            )

            group.loc[eval_idx, f"pred_median_{col}"] = pred.pred_median[:n]
            group.loc[eval_idx, f"pred_low_{col}"]    = bounds.low[:n]
            group.loc[eval_idx, f"pred_high_{col}"]   = bounds.high[:n]

            actual  = group.loc[eval_idx, col].to_numpy()
            offline = actual == 0
            is_anom = ((actual < bounds.low[:n]) | (actual > bounds.high[:n])) & ~offline
            score   = self._anomaly_score(actual, bounds.low[:n], bounds.high[:n])
            score   = np.where(offline, 0.0, score)
            is_high = (actual > bounds.high[:n]) & ~offline
            is_low  = (actual < bounds.low[:n]) & ~offline

            group.loc[eval_idx, f"is_anomaly_{col}"]      = is_anom
            group.loc[eval_idx, f"anomaly_score_{col}"]   = score
            group.loc[eval_idx, f"is_high_anomaly_{col}"] = is_high
            group.loc[eval_idx, f"is_low_anomaly_{col}"]  = is_low

        total_anom = int(group[f"is_anomaly_{col}"].sum())
        _log.info("[%s][%s] %d anomalies across full series", item_id, col, total_anom)
        return group

    # ── Public interface ──────────────────────────────────────────────────

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        self._load_pipeline()
        cfg        = self.config
        items      = df[cfg.item_col].unique()
        value_cols = cfg.value_cols

        rows_per_series  = len(df) // max(len(items), 1)
        windows_per_col  = max(0, (rows_per_series - cfg.context_length) // cfg.slide_step)
        total_calls      = windows_per_col * len(items) * len(value_cols)
        estimated_min    = total_calls * 3 / 60  # ~3s/call on CPU

        _log.info(
            "Starting detection: %d series × %d column(s) × %d windows = %d Chronos calls",
            len(items), len(value_cols), windows_per_col, total_calls,
        )
        _log.info("Columns   : %s", value_cols)
        _log.info("Strategy  : %s  |  slide_step=%dh", cfg.threshold_strategy.value, cfg.slide_step)
        _log.info("Estimated : ~%.0f min on CPU (use accelerateur: cuda to speed up)", estimated_min)

        all_results = []

        for item_id in items:
            group = df[df[cfg.item_col] == item_id].sort_values(cfg.timestamp_col).copy()

            group["is_anomaly"]    = False
            group["anomaly_score"] = 0.0
            for vis in ("pred_median", "pred_low", "pred_high"):
                group[vis] = np.nan

            for col in value_cols:
                group = self._detect_for_col(
                    group, item_id, col, cfg.timestamp_col,
                )
                group["anomaly_score"] = group[
                    ["anomaly_score", f"anomaly_score_{col}"]
                ].max(axis=1)

            # Vote : anomalie globale seulement si ≥ min_features_anomalous features simultanément
            # → évite les faux positifs d'une seule mesure bruitée (ex: THD instable)
            # Le seuil effectif est plafonné au nombre de colonnes disponibles pour
            # éviter qu'un threshold > nb_colonnes rende toute détection impossible.
            flag_cols = [f"is_anomaly_{col}" for col in value_cols if f"is_anomaly_{col}" in group.columns]
            if flag_cols:
                effective_thr = min(cfg.min_features_anomalous, len(flag_cols))
                vote = pd.concat(
                    [group[c].astype(int) for c in flag_cols], axis=1
                ).sum(axis=1)
                group["is_anomaly"] = vote >= effective_thr

            group["is_high_anomaly"] = False
            group["is_low_anomaly"]  = False
            high_fcols = [f"is_high_anomaly_{c}" for c in value_cols if f"is_high_anomaly_{c}" in group.columns]
            low_fcols  = [f"is_low_anomaly_{c}"  for c in value_cols if f"is_low_anomaly_{c}"  in group.columns]
            if high_fcols:
                h_thr  = min(cfg.min_features_anomalous, len(high_fcols))
                h_vote = pd.concat([group[c].astype(int) for c in high_fcols], axis=1).sum(axis=1)
                group["is_high_anomaly"] = (h_vote >= h_thr) & group["is_anomaly"]
            if low_fcols:
                l_thr  = min(cfg.min_features_anomalous, len(low_fcols))
                l_vote = pd.concat([group[c].astype(int) for c in low_fcols], axis=1).sum(axis=1)
                group["is_low_anomaly"] = (l_vote >= l_thr) & group["is_anomaly"]

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

        # ── Classify : point anomaly vs regime change ─────────────────────────
        threshold = cfg.regime_change_hours
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
