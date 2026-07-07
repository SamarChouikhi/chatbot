"""Tests unitaires — api/pipeline/aggregator.py (fonctions pures)"""
import pytest
import pandas as pd
import numpy as np
from datetime import date
from api.pipeline.aggregator import _safe_float, _day_filter


# ── _safe_float() ─────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_integer_converted(self):
        assert _safe_float(5) == 5.0

    def test_float_returned(self):
        assert _safe_float(3.14) == 3.14

    def test_string_number_converted(self):
        assert _safe_float('2.5') == 2.5

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_nan_returns_none(self):
        assert _safe_float(float('nan')) is None

    def test_pandas_na_returns_none(self):
        assert _safe_float(pd.NA) is None

    def test_pandas_nat_returns_none(self):
        assert _safe_float(pd.NaT) is None

    def test_non_numeric_string_returns_none(self):
        assert _safe_float('abc') is None

    def test_empty_string_returns_none(self):
        assert _safe_float('') is None

    def test_negative_value(self):
        assert _safe_float(-7.5) == -7.5

    def test_zero(self):
        assert _safe_float(0) == 0.0

    def test_rounded_to_4_decimals(self):
        result = _safe_float(1.23456789)
        assert result == round(1.23456789, 4)

    def test_numpy_float_converted(self):
        assert _safe_float(np.float64(9.9)) == 9.9


# ── _day_filter() ─────────────────────────────────────────────────────────────

class TestDayFilter:
    def _make_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            'date': pd.to_datetime([
                '2024-01-01', '2024-01-01',
                '2024-01-02',
                '2024-01-03',
            ]),
            'value': [10, 20, 30, 40],
        })

    def test_filters_correct_day(self):
        df = self._make_df()
        result = _day_filter(df, date(2024, 1, 1))
        assert len(result) == 2

    def test_returns_correct_values(self):
        df = self._make_df()
        result = _day_filter(df, date(2024, 1, 1))
        assert set(result['value'].tolist()) == {10, 20}

    def test_single_row_day(self):
        df = self._make_df()
        result = _day_filter(df, date(2024, 1, 2))
        assert len(result) == 1
        assert result.iloc[0]['value'] == 30

    def test_no_match_returns_empty(self):
        df = self._make_df()
        result = _day_filter(df, date(2024, 12, 31))
        assert len(result) == 0

    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame({'date': pd.to_datetime([]), 'value': []})
        result = _day_filter(df, date(2024, 1, 1))
        assert len(result) == 0

    def test_does_not_modify_original(self):
        df = self._make_df()
        original_len = len(df)
        _day_filter(df, date(2024, 1, 1))
        assert len(df) == original_len
