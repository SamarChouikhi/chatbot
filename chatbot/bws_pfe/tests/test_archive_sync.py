"""Tests unitaires — api/pipeline/archive_sync.py (fonctions pures)"""
import pytest
from datetime import date
from api.pipeline.archive_sync import _month_bounds, _months_in_range


# ── _month_bounds() ───────────────────────────────────────────────────────────

class TestMonthBounds:
    def test_mid_month_returns_correct_bounds(self):
        ms, nm = _month_bounds(date(2024, 6, 15))
        assert ms == date(2024, 6, 1)
        assert nm == date(2024, 7, 1)

    def test_january_next_month_is_february(self):
        ms, nm = _month_bounds(date(2024, 1, 1))
        assert ms == date(2024, 1, 1)
        assert nm == date(2024, 2, 1)

    def test_december_wraps_to_next_year(self):
        ms, nm = _month_bounds(date(2024, 12, 31))
        assert ms == date(2024, 12, 1)
        assert nm == date(2025, 1, 1)

    def test_first_day_of_month_preserved(self):
        ms, _ = _month_bounds(date(2024, 3, 1))
        assert ms == date(2024, 3, 1)

    def test_february_non_leap_year(self):
        ms, nm = _month_bounds(date(2023, 2, 14))
        assert ms == date(2023, 2, 1)
        assert nm == date(2023, 3, 1)

    def test_february_leap_year(self):
        ms, nm = _month_bounds(date(2024, 2, 29))
        assert ms == date(2024, 2, 1)
        assert nm == date(2024, 3, 1)

    def test_next_month_is_first_day(self):
        _, nm = _month_bounds(date(2024, 8, 20))
        assert nm.day == 1

    def test_month_start_is_first_day(self):
        ms, _ = _month_bounds(date(2024, 11, 7))
        assert ms.day == 1


# ── _months_in_range() ────────────────────────────────────────────────────────

class TestMonthsInRange:
    def test_same_month(self):
        result = _months_in_range(date(2024, 6, 1), date(2024, 6, 30))
        assert result == [date(2024, 6, 1)]

    def test_two_consecutive_months(self):
        result = _months_in_range(date(2024, 5, 1), date(2024, 6, 30))
        assert result == [date(2024, 5, 1), date(2024, 6, 1)]

    def test_three_months(self):
        result = _months_in_range(date(2024, 1, 15), date(2024, 3, 15))
        assert len(result) == 3
        assert result[0] == date(2024, 1, 1)
        assert result[-1] == date(2024, 3, 1)

    def test_across_year_boundary(self):
        result = _months_in_range(date(2023, 11, 1), date(2024, 1, 31))
        assert result == [date(2023, 11, 1), date(2023, 12, 1), date(2024, 1, 1)]

    def test_start_after_end_returns_empty(self):
        result = _months_in_range(date(2024, 6, 1), date(2024, 5, 1))
        assert result == []

    def test_all_results_are_first_of_month(self):
        result = _months_in_range(date(2024, 1, 15), date(2024, 6, 15))
        assert all(d.day == 1 for d in result)

    def test_results_are_chronological(self):
        result = _months_in_range(date(2024, 1, 1), date(2024, 12, 31))
        assert result == sorted(result)

    def test_twelve_months_in_year(self):
        result = _months_in_range(date(2024, 1, 1), date(2024, 12, 31))
        assert len(result) == 12
