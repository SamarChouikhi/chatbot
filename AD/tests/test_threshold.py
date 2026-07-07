"""Tests unitaires — HotStart/common/threshold.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "HotStart"))

import pytest
import numpy as np
import pandas as pd

from common.threshold import DynamicThresholdEngine, ThresholdStrategy, ThresholdBounds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _arrays(n=10, low=10.0, median=15.0, high=20.0):
    return np.full(n, low), np.full(n, median), np.full(n, high)


def _context(mean=15.0, std=2.0, n=50) -> pd.Series:
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(loc=mean, scale=std, size=n))


# ── ThresholdBounds ───────────────────────────────────────────────────────────

class TestThresholdBounds:
    def test_is_immutable(self):
        low, med, high = _arrays()
        b = ThresholdBounds(low=low, high=high, strategy=ThresholdStrategy.FIXED)
        with pytest.raises((AttributeError, TypeError)):
            b.strategy = ThresholdStrategy.SIGMA

    def test_stores_strategy(self):
        low, med, high = _arrays()
        b = ThresholdBounds(low=low, high=high, strategy=ThresholdStrategy.ADAPTIVE)
        assert b.strategy == ThresholdStrategy.ADAPTIVE


# ── FIXED ─────────────────────────────────────────────────────────────────────

class TestFixedStrategy:
    def test_passthrough_low(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.FIXED)
        low, med, high = _arrays(low=5.0, high=25.0)
        bounds = engine.compute_from_stats(15.0, 2.0, low, med, high)
        np.testing.assert_array_equal(bounds.low, low)

    def test_passthrough_high(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.FIXED)
        low, med, high = _arrays(low=5.0, high=25.0)
        bounds = engine.compute_from_stats(15.0, 2.0, low, med, high)
        np.testing.assert_array_equal(bounds.high, high)

    def test_strategy_label(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.FIXED)
        low, med, high = _arrays()
        bounds = engine.compute_from_stats(15.0, 1.0, low, med, high)
        assert bounds.strategy == ThresholdStrategy.FIXED

    def test_shape_preserved(self):
        n = 24
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.FIXED)
        low, med, high = _arrays(n=n)
        bounds = engine.compute_from_stats(15.0, 1.0, low, med, high)
        assert bounds.low.shape == (n,)
        assert bounds.high.shape == (n,)


# ── SIGMA ──────────────────────────────────────────────────────────────────────

class TestSigmaStrategy:
    def test_widens_bounds_when_sigma_wide(self):
        # k_sigma=3, std=5 → sigma interval [-0, 30] pour mean=15
        # pred interval [12, 18] → dyn_low = min(12, 0)=0 ; dyn_high = max(18, 30)=30
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.SIGMA, k_sigma=3.0)
        low, med, high = _arrays(low=12.0, high=18.0)
        bounds = engine.compute_from_stats(ctx_mu=15.0, ctx_sigma=5.0,
                                           pred_low=low, pred_median=med, pred_high=high)
        assert bounds.high.max() >= high.max()
        assert bounds.low.min() <= low.min()

    def test_zero_std_no_widening(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.SIGMA, k_sigma=3.0)
        low, med, high = _arrays(low=12.0, high=18.0)
        # std=0 → sigma_low = 15, sigma_high = 15
        # dyn_low = min(12, 15) = 12 ; dyn_high = max(18, 15) = 18
        bounds = engine.compute_from_stats(ctx_mu=15.0, ctx_sigma=0.0,
                                           pred_low=low, pred_median=med, pred_high=high)
        np.testing.assert_array_equal(bounds.low, low)
        np.testing.assert_array_equal(bounds.high, high)

    def test_output_shape(self):
        n = 48
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.SIGMA)
        low, med, high = _arrays(n=n)
        bounds = engine.compute_from_stats(15.0, 2.0, low, med, high)
        assert bounds.low.shape == (n,)
        assert bounds.high.shape == (n,)

    def test_strategy_label(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.SIGMA)
        low, med, high = _arrays()
        bounds = engine.compute_from_stats(15.0, 2.0, low, med, high)
        assert bounds.strategy == ThresholdStrategy.SIGMA

    def test_compute_from_series(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.SIGMA)
        ctx = _context(mean=15.0, std=2.0)
        low, med, high = _arrays()
        bounds = engine.compute(ctx, low, med, high)
        assert bounds.strategy == ThresholdStrategy.SIGMA


# ── ADAPTIVE ──────────────────────────────────────────────────────────────────

class TestAdaptiveStrategy:
    def test_high_cv_wider_than_low_cv(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.ADAPTIVE, alpha=0.5)
        low, med, high = _arrays(low=10.0, median=15.0, high=20.0)
        # CV élevé : std/mean ≈ 10 (capé à max_cv_scale=2 → scale=2.0)
        b_high = engine.compute_from_stats(ctx_mu=1.0, ctx_sigma=10.0,
                                           pred_low=low, pred_median=med, pred_high=high)
        # CV faible : std/mean ≈ 0.001 → scale≈1.0005
        b_low  = engine.compute_from_stats(ctx_mu=100.0, ctx_sigma=0.1,
                                           pred_low=low, pred_median=med, pred_high=high)
        width_high = float((b_high.high - b_high.low)[0])
        width_low  = float((b_low.high  - b_low.low)[0])
        assert width_high > width_low

    def test_max_cv_scale_caps_widening(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.ADAPTIVE,
                                        alpha=0.5, max_cv_scale=2.0)
        low, med, high = _arrays(low=10.0, median=15.0, high=20.0)
        # CV = 1000 → capé à 2 → scale = 1 + 0.5*2 = 2.0
        b_extreme = engine.compute_from_stats(ctx_mu=1.0, ctx_sigma=1000.0,
                                              pred_low=low, pred_median=med, pred_high=high)
        # CV = 2 → scale = 1 + 0.5*2 = 2.0 (exactement au cap)
        b_at_cap = engine.compute_from_stats(ctx_mu=1.0, ctx_sigma=2.0,
                                             pred_low=low, pred_median=med, pred_high=high)
        np.testing.assert_array_almost_equal(b_extreme.low, b_at_cap.low, decimal=5)
        np.testing.assert_array_almost_equal(b_extreme.high, b_at_cap.high, decimal=5)

    def test_strategy_label(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.ADAPTIVE)
        low, med, high = _arrays()
        bounds = engine.compute_from_stats(15.0, 2.0, low, med, high)
        assert bounds.strategy == ThresholdStrategy.ADAPTIVE

    def test_output_shape(self):
        n = 24
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.ADAPTIVE)
        low, med, high = _arrays(n=n)
        bounds = engine.compute_from_stats(15.0, 2.0, low, med, high)
        assert bounds.low.shape == (n,)
        assert bounds.high.shape == (n,)

    def test_compute_from_series(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.ADAPTIVE)
        ctx = _context(mean=15.0, std=2.0)
        low, med, high = _arrays()
        bounds = engine.compute(ctx, low, med, high)
        assert bounds.strategy == ThresholdStrategy.ADAPTIVE


# ── Dispatch via compute() ────────────────────────────────────────────────────

class TestComputeDispatch:
    def test_fixed_via_compute(self):
        engine = DynamicThresholdEngine(strategy=ThresholdStrategy.FIXED)
        ctx = _context()
        low, med, high = _arrays()
        bounds = engine.compute(ctx, low, med, high)
        np.testing.assert_array_equal(bounds.low, low)

    def test_unknown_strategy_raises_via_compute_from_stats(self):
        engine = DynamicThresholdEngine.__new__(DynamicThresholdEngine)
        engine.strategy = "invalid_strategy"
        engine.k_sigma = 3.0
        engine.alpha = 0.5
        engine.max_cv_scale = 2.0
        low, med, high = _arrays()
        with pytest.raises(ValueError):
            engine.compute_from_stats(15.0, 2.0, low, med, high)

    def test_low_is_always_below_high(self):
        for strategy in ThresholdStrategy:
            engine = DynamicThresholdEngine(strategy=strategy)
            low, med, high = _arrays(low=10.0, median=15.0, high=20.0)
            bounds = engine.compute_from_stats(15.0, 2.0, low, med, high)
            assert (bounds.low <= bounds.high).all(), f"Failed for {strategy}"
