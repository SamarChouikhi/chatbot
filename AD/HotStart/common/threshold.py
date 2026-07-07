from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class ThresholdStrategy(str, Enum):
    FIXED    = "fixed"
    SIGMA    = "sigma"
    ADAPTIVE = "adaptive"


@dataclass(frozen=True)
class ThresholdBounds:
    low:      np.ndarray
    high:     np.ndarray
    strategy: ThresholdStrategy


class DynamicThresholdEngine:
    """
    Computes per-series anomaly bounds that adapt to each series' historical statistics.

    Strategies
    ----------
    FIXED    : pass-through, no adjustment (deterministic baseline)
    SIGMA    : intersection of Chronos interval with μ ± k·σ of the context.
               Flags only points that deviate on BOTH temporal pattern (Chronos)
               AND magnitude distribution (σ-bound). Robust against noisy sensors.
    ADAPTIVE : scales Chronos half-width by (1 + α·CV). High-volatility series get
               wider bounds; stable series get tighter bounds.
               CV is capped at max_cv_scale to prevent unbounded widening.
    """

    def __init__(
        self,
        strategy:     ThresholdStrategy = ThresholdStrategy.SIGMA,
        k_sigma:      float = 3.0,
        alpha:        float = 0.5,
        max_cv_scale: float = 2.0,
    ) -> None:
        self.strategy     = strategy
        self.k_sigma      = k_sigma
        self.alpha        = alpha
        self.max_cv_scale = max_cv_scale

    def compute(
        self,
        context:      pd.Series,
        pred_low:     np.ndarray,
        pred_median:  np.ndarray,
        pred_high:    np.ndarray,
    ) -> ThresholdBounds:
        match self.strategy:
            case ThresholdStrategy.FIXED:
                return ThresholdBounds(pred_low.copy(), pred_high.copy(), self.strategy)
            case ThresholdStrategy.SIGMA:
                return self._sigma(context, pred_low, pred_high)
            case ThresholdStrategy.ADAPTIVE:
                return self._adaptive(context, pred_median, pred_low, pred_high)
            case _:
                raise ValueError(f"Unknown ThresholdStrategy: {self.strategy!r}")

    def compute_from_stats(
        self,
        ctx_mu:      float,
        ctx_sigma:   float,
        pred_low:    np.ndarray,
        pred_median: np.ndarray,
        pred_high:   np.ndarray,
    ) -> ThresholdBounds:
        match self.strategy:
            case ThresholdStrategy.FIXED:
                return ThresholdBounds(pred_low.copy(), pred_high.copy(), self.strategy)
            case ThresholdStrategy.SIGMA:
                return self._sigma_from_stats(ctx_mu, ctx_sigma, pred_low, pred_high)
            case ThresholdStrategy.ADAPTIVE:
                return self._adaptive_from_stats(ctx_mu, ctx_sigma, pred_median, pred_low, pred_high)
            case _:
                raise ValueError(f"Unknown ThresholdStrategy: {self.strategy!r}")

    def _sigma_from_stats(
        self,
        mu:        float,
        std:       float,
        pred_low:  np.ndarray,
        pred_high: np.ndarray,
    ) -> ThresholdBounds:
        sigma_low  = np.full(len(pred_low),  mu - self.k_sigma * std)
        sigma_high = np.full(len(pred_high), mu + self.k_sigma * std)
        dyn_low  = np.minimum(pred_low,  sigma_low)
        dyn_high = np.maximum(pred_high, sigma_high)
        return ThresholdBounds(dyn_low, dyn_high, self.strategy)

    def _adaptive_from_stats(
        self,
        mu:          float,
        std:         float,
        pred_median: np.ndarray,
        pred_low:    np.ndarray,
        pred_high:   np.ndarray,
    ) -> ThresholdBounds:
        cv         = std / (abs(mu) + 1e-9)
        scale      = 1.0 + self.alpha * min(cv, self.max_cv_scale)
        half_width = (pred_high - pred_low) / 2.0
        return ThresholdBounds(
            low      = pred_median - scale * half_width,
            high     = pred_median + scale * half_width,
            strategy = self.strategy,
        )

    def _sigma(
        self,
        context:   pd.Series,
        pred_low:  np.ndarray,
        pred_high: np.ndarray,
    ) -> ThresholdBounds:
        mu  = float(context.mean())
        std = float(context.std(ddof=1)) if len(context) >= 2 else 0.0

        sigma_low  = np.full(len(pred_low),  mu - self.k_sigma * std)
        sigma_high = np.full(len(pred_high), mu + self.k_sigma * std)

        dyn_low  = np.minimum(pred_low,  sigma_low)
        dyn_high = np.maximum(pred_high, sigma_high)

        return ThresholdBounds(dyn_low, dyn_high, self.strategy)

    def _adaptive(
        self,
        context:     pd.Series,
        pred_median: np.ndarray,
        pred_low:    np.ndarray,
        pred_high:   np.ndarray,
    ) -> ThresholdBounds:
        mu  = float(context.mean())
        std = float(context.std(ddof=1)) if len(context) >= 2 else 0.0
        cv  = std / (abs(mu) + 1e-9)
        scale      = 1.0 + self.alpha * min(cv, self.max_cv_scale)
        half_width = (pred_high - pred_low) / 2.0
        return ThresholdBounds(
            low      = pred_median - scale * half_width,
            high     = pred_median + scale * half_width,
            strategy = self.strategy,
        )
