"""Forecaster for gaz — same logic as water, domain label changed."""
from __future__ import annotations

import torch
import numpy as np
import pandas as pd
from typing import Any

from common.logger import get_logger
from .config import GazConfig

_log = get_logger(__name__)

_SEVERITY_HIGH   = 2.0
_SEVERITY_MEDIUM = 1.0


class GazForecaster:

    def __init__(self, config: GazConfig, pipeline: Any) -> None:
        self.config    = config
        self._pipeline = pipeline

    def forecast_all(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg   = self.config
        items = df[cfg.item_col].unique()
        _log.info(
            "Forecasting gaz %d devices x %d col(s) - horizon=%dh",
            len(items), len(cfg.value_cols), cfg.forecast_horizon,
        )
        chunks: list[pd.DataFrame] = []
        for item_id in items:
            group = df[df[cfg.item_col] == item_id].sort_values(cfg.timestamp_col)
            for col in cfg.value_cols:
                chunk = self._forecast_one(group, item_id, col)
                if chunk is not None:
                    chunks.append(chunk)

        if not chunks:
            _log.warning("No forecast produced")
            return pd.DataFrame()

        result   = pd.concat(chunks, ignore_index=True)
        n_alerts = int(result["is_alert"].sum())
        _log.info(
            "Forecast gaz complete - %d alertes preventives (HIGH=%d MEDIUM=%d LOW=%d)",
            n_alerts,
            (result["alert_severity"] == "HIGH").sum(),
            (result["alert_severity"] == "MEDIUM").sum(),
            (result["alert_severity"] == "LOW").sum(),
        )
        return result

    def _forecast_one(self, group: pd.DataFrame, item_id: str, col: str) -> pd.DataFrame | None:
        cfg     = self.config
        horizon = cfg.forecast_horizon
        series  = group.set_index(cfg.timestamp_col)[col].dropna()

        min_required = max(cfg.prediction_length * 2, cfg.forecast_horizon)
        if len(series) < min_required:
            _log.warning(
                "[%s][%s] donnees insuffisantes (%d < %d) - skipped",
                item_id, col, len(series), min_required,
            )
            return None

        ctx_series = series.tail(min(cfg.context_length, len(series)))
        context    = torch.tensor(ctx_series.values, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        try:
            quantiles, _ = self._pipeline.predict_quantiles(
                context,
                prediction_length=horizon,
                quantile_levels=[cfg.q_low, 0.5, cfg.q_high],
            )
            q = quantiles[0][0].numpy()
            low, median, high = q[:, 0], q[:, 1], q[:, 2]
        except Exception as exc:
            _log.error("[%s][%s] forecast failed: %s", item_id, col, exc)
            return None

        last_ts      = pd.to_datetime(ctx_series.index[-1])
        freq_offset  = pd.tseries.frequencies.to_offset(cfg.resample_freq)
        future_times = pd.date_range(
            start=last_ts + freq_offset, periods=horizon, freq=cfg.resample_freq,
        )

        confidence         = self._confidence(low, high, ctx_series)
        is_alert, severity = self._alerts(median, ctx_series)

        return pd.DataFrame({
            cfg.item_col:      item_id,
            cfg.device_col:    item_id,
            cfg.timestamp_col: future_times,
            "forecast_col":    col,
            "forecast_median": median,
            "forecast_low":    low,
            "forecast_high":   high,
            "confidence":      confidence,
            "is_alert":        is_alert,
            "alert_severity":  severity,
        })

    @staticmethod
    def _confidence(low: np.ndarray, high: np.ndarray, context: pd.Series) -> np.ndarray:
        if len(context) < 2:
            return np.zeros(len(low), dtype=np.float64)
        q05 = float(context.quantile(0.05))
        q95 = float(context.quantile(0.95))
        std = float(context.std(ddof=1))
        hist_range     = max(q95 - q05, std, 1e-9)
        relative_width = (high - low) / hist_range
        return np.round(np.clip(1.0 - relative_width, 0.0, 1.0), 3)

    def _alerts(
        self, forecast_median: np.ndarray, context: pd.Series,
    ) -> tuple[np.ndarray, np.ndarray]:
        mu    = float(context.mean())
        sigma = float(context.std(ddof=1)) + 1e-9
        normal_low  = mu - self.config.k_sigma * sigma
        normal_high = mu + self.config.k_sigma * sigma
        above     = np.maximum(0.0, (forecast_median - normal_high) / sigma)
        below     = np.maximum(0.0, (normal_low - forecast_median)  / sigma)
        deviation = np.maximum(above, below)
        is_alert  = deviation > 0.0
        severity  = np.where(
            deviation > _SEVERITY_HIGH,   "HIGH",
            np.where(
            deviation > _SEVERITY_MEDIUM, "MEDIUM",
            np.where(is_alert,            "LOW", "")),
        )
        return is_alert, severity
