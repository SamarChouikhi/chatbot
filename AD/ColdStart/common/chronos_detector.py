"""
Chronos zero-shot detector for ColdStart anomaly detection.

Strategy
--------
Cold start devices have no historical data to fine-tune on.
Chronos is used in zero-shot mode:
  1. At fit() time, the synthetic series (built from population profiles) is stored
     per item_id as a seeding context.
  2. At detect() time, a sliding window advances over the detection data.
     For each window position the preceding `context_length` points are fed to
     Chronos (seed synthetic tail + real data seen so far).
  3. Points outside the widened [low, high] quantile interval are flagged.

The synthetic context gives Chronos a plausible prior even on the very first
real observation — bridging the cold-start gap that defeats purely statistical methods.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from common.logger import get_logger

if TYPE_CHECKING:
    pass

_log = get_logger(__name__)

# Module-level singleton — one pipeline per model name, shared across all items
# within a single ColdStart subprocess run.
_PIPELINE_CACHE: dict[str, object] = {}


def _load_pipeline(model_name: str, device: str) -> object:
    if model_name in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[model_name]

    import torch  # noqa: PLC0415

    _log.info("Loading Chronos model: %s (device=%s)", model_name, device)
    try:
        from chronos import Chronos2Pipeline  # noqa: PLC0415
        pipeline = Chronos2Pipeline.from_pretrained(model_name, device_map=device)
        _log.info("Chronos ready (Chronos2Pipeline)")
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "Chronos2Pipeline unavailable (%s) — fallback to BaseChronosPipeline", exc
        )
        from chronos import BaseChronosPipeline  # noqa: PLC0415
        dtype = torch.bfloat16 if device in ("cuda", "mps") else torch.float32
        pipeline = BaseChronosPipeline.from_pretrained(
            model_name, device_map=device, dtype=dtype
        )
        _log.info("Chronos ready (BaseChronosPipeline)")

    _PIPELINE_CACHE[model_name] = pipeline
    return pipeline


class ChronosZeroShotDetector:
    """
    Sliding-window anomaly detector backed by a Chronos foundation model.

    Parameters
    ----------
    model_name        : HuggingFace model id — default is chronos-t5-tiny (fastest).
    device            : "cpu" | "cuda" | "mps"
    context_length    : number of past hours fed to Chronos as context.
    prediction_length : forecast horizon (also the slide step, so each point
                        is evaluated exactly once).
    num_samples       : Chronos MC samples (higher = better quantiles but slower).
    q_low / q_high    : quantile bounds for the forecast interval.
    k_sigma           : interval-widening factor.
                        Final bounds = pred_low − k × half_interval,
                                       pred_high + k × half_interval.
                        Higher k → more lenient (appropriate for synthetic context).
    item_col          : column name containing the item / series identifier.
    """

    def __init__(
        self,
        model_name:        str   = "autogluon/chronos-t5-tiny",
        device:            str   = "cpu",
        context_length:    int   = 48,
        prediction_length: int   = 12,
        num_samples:       int   = 20,
        q_low:             float = 0.1,
        q_high:            float = 0.9,
        k_sigma:           float = 1.5,
        item_col:          str   = "item_id",
    ) -> None:
        self.model_name        = model_name
        self.device            = device
        self.context_length    = context_length
        self.prediction_length = prediction_length
        self.num_samples       = num_samples
        self.q_low             = q_low
        self.q_high            = q_high
        self.k_sigma           = k_sigma
        self.item_col          = item_col

        self._pipeline = None
        # item_id → seed pd.Series (last context_length × 2 points of synthetic data)
        self._seeds: dict[str, pd.Series] = {}

    # ── Fit ──────────────────────────────────────────────────────────────────

    def fit(
        self,
        synthetic_df: pd.DataFrame,
        value_col:    str,
        ts_col:       str,
    ) -> None:
        """
        Extract a seed context from the synthetic data for each item_id.

        The seed is the tail of the synthetic series (up to 2× context_length
        points).  It is prepended to the real data at detect() time so that
        Chronos always has a meaningful context window, even for the first real
        observation.
        """
        if synthetic_df.empty or value_col not in synthetic_df.columns:
            _log.warning(
                "ChronosZeroShot: synthetic_df empty or missing col '%s' — no seed stored",
                value_col,
            )
            return

        seed_len = self.context_length * 2

        for item_id, group in synthetic_df.groupby(self.item_col):
            series = (
                group.set_index(ts_col)[value_col]
                .sort_index()
                .dropna()
            )
            self._seeds[str(item_id)] = series.tail(seed_len)

        _log.info(
            "ChronosZeroShot fit: %d seed series stored for col='%s' (each ≤ %d pts)",
            len(self._seeds), value_col, seed_len,
        )

    # ── Detect ───────────────────────────────────────────────────────────────

    def detect(
        self,
        group:     pd.DataFrame,
        value_col: str,
        ts_col:    str,
        item_id:   str,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Run zero-shot detection on one item's sorted DataFrame.

        Returns
        -------
        is_anomaly    : bool ndarray, shape (n,)
        anomaly_score : float ndarray, shape (n,)  — 0 normal … 10 extreme
        lower_bound   : float ndarray, shape (n,)
        upper_bound   : float ndarray, shape (n,)
        """
        n = len(group)
        is_anomaly    = np.zeros(n, dtype=bool)
        anomaly_score = np.zeros(n, dtype=float)
        lower_bound   = np.full(n, np.nan)
        upper_bound   = np.full(n, np.nan)

        if n == 0 or value_col not in group.columns:
            return is_anomaly, anomaly_score, lower_bound, upper_bound

        # Ensure Chronos pipeline is loaded
        if self._pipeline is None:
            try:
                self._pipeline = _load_pipeline(self.model_name, self.device)
            except Exception as exc:  # noqa: BLE001
                _log.error("ChronosZeroShot: failed to load pipeline — %s", exc)
                return is_anomaly, anomaly_score, lower_bound, upper_bound

        # Build combined series: [seed] + [detection values]
        seed = self._seeds.get(str(item_id), pd.Series(dtype=float))
        real_series = (
            group.set_index(ts_col)[value_col]
            .sort_index()
            .fillna(0.0)
        )

        if not seed.empty:
            combined = pd.concat([seed, real_series])
        else:
            combined = real_series.copy()

        combined_vals = combined.to_numpy(dtype=float)
        n_seed        = len(seed)
        n_total       = len(combined_vals)
        step          = self.prediction_length

        # Map detection-series index to combined index
        # detection point i → combined index n_seed + i
        if n < 2:
            _log.info(
                "[%s] ChronosZeroShot: too short (%d pts) — need at least 2",
                item_id, n,
            )
            return is_anomaly, anomaly_score, lower_bound, upper_bound

        n_windows = (n + step - 1) // step
        _log.info(
            "[%s] ChronosZeroShot: %d detection pts → %d windows (ctx=%d, step=%d)",
            item_id, n, n_windows, self.context_length, step,
        )

        import torch  # noqa: PLC0415

        for det_start in range(0, n, step):
            det_end  = min(det_start + step, n)
            pred_len = det_end - det_start

            # Combined context ends just before det_start in detection series
            comb_end   = n_seed + det_start
            comb_start = max(0, comb_end - self.context_length)
            ctx_vals   = combined_vals[comb_start:comb_end]

            if len(ctx_vals) < 2:
                continue

            context = torch.tensor(ctx_vals, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

            try:
                quantiles, _ = self._pipeline.predict_quantiles(  # type: ignore[union-attr]
                    context,
                    prediction_length=pred_len,
                    quantile_levels=[self.q_low, 0.5, self.q_high],
                )
                q = quantiles[0][0].numpy()
                pred_low, pred_median, pred_high = q[:, 0], q[:, 1], q[:, 2]
            except Exception as exc:  # noqa: BLE001
                _log.debug("[%s] window failed: %s", item_id, exc)
                continue

            # Widen interval by k_sigma × half_interval
            half_interval = np.maximum((pred_high - pred_low) / 2.0, 1e-6)
            margin        = self.k_sigma * half_interval
            low           = np.maximum(pred_low  - margin, 0.0)
            high          = pred_high + margin

            actual = group[value_col].iloc[det_start:det_end].fillna(0.0).to_numpy()

            offline   = actual == 0.0
            is_anom_w = ((actual < low) | (actual > high)) & ~offline

            raw_interval = np.maximum(pred_high - pred_low, 1e-6)
            score_w = np.where(
                actual > pred_high,
                (actual - pred_high) / raw_interval,
                np.where(actual < pred_low, (pred_low - actual) / raw_interval, 0.0),
            )
            score_w = np.clip(score_w, 0.0, 10.0)
            score_w = np.where(is_anom_w, score_w, 0.0)

            is_anomaly[det_start:det_end]    = is_anom_w
            anomaly_score[det_start:det_end] = score_w
            lower_bound[det_start:det_end]   = low
            upper_bound[det_start:det_end]   = high

        n_anom = int(is_anomaly.sum())
        _log.info("[%s] ChronosZeroShot detect: %d/%d anomalies", item_id, n_anom, n)

        return is_anomaly, anomaly_score, lower_bound, upper_bound
