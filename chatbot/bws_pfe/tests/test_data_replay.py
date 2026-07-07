"""Tests unitaires — api/pipeline/data_replay.py (fonctions pures)"""
import pytest
from datetime import date, timedelta
from api.pipeline.data_replay import _source_date


# ── _source_date() ────────────────────────────────────────────────────────────

class TestSourceDate:
    def test_target_equals_dmin_gives_dmin(self):
        d_min = date(2024, 1, 1)
        result = _source_date(d_min, d_min, cycle_days=30)
        assert result == d_min

    def test_basic_offset_within_cycle(self):
        d_min = date(2024, 1, 1)
        target = date(2024, 1, 10)
        result = _source_date(target, d_min, cycle_days=30)
        assert result == date(2024, 1, 10)

    def test_wraps_exactly_at_cycle_boundary(self):
        d_min = date(2024, 1, 1)
        target = d_min + timedelta(days=30)  # offset = 30 % 30 = 0
        result = _source_date(target, d_min, cycle_days=30)
        assert result == d_min

    def test_wraps_after_one_full_cycle(self):
        d_min = date(2024, 1, 1)
        target = d_min + timedelta(days=35)  # 35 % 30 = 5
        result = _source_date(target, d_min, cycle_days=30)
        assert result == date(2024, 1, 6)

    def test_result_always_in_cycle_range(self):
        d_min = date(2024, 1, 1)
        cycle = 30
        for offset in range(120):
            target = d_min + timedelta(days=offset)
            result = _source_date(target, d_min, cycle_days=cycle)
            diff = (result - d_min).days
            assert 0 <= diff < cycle

    def test_single_day_cycle(self):
        d_min = date(2024, 1, 1)
        target = date(2024, 6, 15)
        result = _source_date(target, d_min, cycle_days=1)
        assert result == d_min

    def test_large_cycle_365_days(self):
        d_min = date(2023, 1, 1)
        target = date(2024, 6, 1)
        cycle = 365
        expected_offset = (target - d_min).days % cycle
        result = _source_date(target, d_min, cycle_days=cycle)
        assert result == d_min + timedelta(days=expected_offset)

    def test_consecutive_targets_produce_consecutive_sources(self):
        d_min = date(2024, 1, 1)
        t1 = d_min + timedelta(days=5)
        t2 = d_min + timedelta(days=6)
        r1 = _source_date(t1, d_min, cycle_days=30)
        r2 = _source_date(t2, d_min, cycle_days=30)
        assert (r2 - r1).days == 1
