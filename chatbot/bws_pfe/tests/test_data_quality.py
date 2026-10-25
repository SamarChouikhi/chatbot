"""Tests unitaires — api/pipeline/data_quality.py"""
import pandas as pd

from api.pipeline.data_quality import drop_counter_spikes, spike_mask


def _series(values, device='15002301', phase='L1'):
    return pd.DataFrame({'id_device': device, 'phase': phase, 'cons_en': values})


class TestSpikeMask:
    def test_cumulative_index_reading_is_flagged(self):
        df = _series([100_000.0] * 23 + [202_339_000.0])
        assert spike_mask(df, 'cons_en', ['id_device', 'phase']).tolist() == [False] * 23 + [True]

    def test_normal_variation_is_kept(self):
        df = _series([60_000.0, 90_000.0, 130_000.0, 250_000.0] * 6)
        assert not spike_mask(df, 'cons_en', ['id_device', 'phase']).any()

    def test_zeros_do_not_drag_median_down(self):
        # Des arrêts (0) ne doivent pas rendre une lecture normale « aberrante »
        df = _series([0.0] * 30 + [100_000.0] * 12 + [150_000.0])
        assert not spike_mask(df, 'cons_en', ['id_device', 'phase']).any()

    def test_short_series_left_untouched(self):
        df = _series([10.0] * 5 + [1_000_000.0])
        assert not spike_mask(df, 'cons_en', ['id_device', 'phase']).any()

    def test_series_are_judged_independently(self):
        small = _series([10.0] * 12, device='1')
        big = _series([100_000.0] * 12, device='15002301')
        df = pd.concat([small, big], ignore_index=True)
        assert not spike_mask(df, 'cons_en', ['id_device', 'phase']).any()

    def test_empty_frame(self):
        df = _series([])
        assert spike_mask(df, 'cons_en', ['id_device', 'phase']).empty


class TestDropCounterSpikes:
    def test_only_spike_rows_removed(self):
        df = _series([100_000.0] * 23 + [202_339_000.0])
        out = drop_counter_spikes(df, 'cons_en', ['id_device', 'phase'])
        assert len(out) == 23
        assert out['cons_en'].max() == 100_000.0
