"""Tests unitaires — HotStart/common/monthly_retrainer.py

Couvre les transitions d'état de retrain() : un fine-tuning réussi adopte le
nouveau checkpoint et avance months_accumulated ; un échec laisse l'état
intact pour que le même mois soit retenté au prochain run.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "HotStart"))

import numpy as np
import pandas as pd

from common.monthly_retrainer import MonthlyRetrainer, DeviceRetrainState, RetrainOutcome


@dataclass
class _FakeConfig:
    timestamp_col:       str   = "date"
    device_col:          str   = "id_device"
    retrain_enabled:     bool  = True
    fine_tune_epochs:    int   = 1
    fine_tune_lr:        float = 1e-4
    context_length:      int   = 24
    prediction_length:   int   = 12
    checkpoint_dir:      str   = ""
    retrain_state_file:  str   = ""


def _fake_df(n: int = 20) -> pd.DataFrame:
    return pd.DataFrame({
        "date":       pd.date_range("2026-01-01", periods=n, freq="h"),
        "id_device":  ["DEV_1"] * n,
        "value":      np.linspace(1, n, n),
    })


def _make_retrainer(
    tmp_path, monkeypatch, *, months_now=3, fine_tune_success=True,
) -> MonthlyRetrainer:
    """Build a MonthlyRetrainer with fine-tuning mocked out — only the
    state-transition logic in retrain() is under test."""
    config = _FakeConfig(
        checkpoint_dir     = str(tmp_path / "checkpoints"),
        retrain_state_file = str(tmp_path / "retrain_state.json"),
    )
    retrainer = MonthlyRetrainer(config)

    monkeypatch.setattr(retrainer, "_extract_series", lambda df: [np.zeros(20, dtype=np.float32)])
    monkeypatch.setattr(retrainer, "_fine_tune",
                         lambda pipeline, series_list, ckpt_path: fine_tune_success)
    monkeypatch.setattr(retrainer, "_count_months", lambda df: months_now)
    return retrainer


class TestRetrainAdopted:
    def test_returns_adopted_outcome(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=4)
        outcome = retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        assert outcome is RetrainOutcome.ADOPTED

    def test_state_advances_and_adopts_new_checkpoint(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=4)
        retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        state = retrainer._states["DEV_1"]
        assert state.months_accumulated == 4
        assert state.checkpoint_filename == "DEV_1_m04.pt"

    def test_old_checkpoint_removed_on_adoption(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=3)
        ckpt_dir = tmp_path / "checkpoints"
        ckpt_dir.mkdir()
        old_ckpt = ckpt_dir / "DEV_1_m02.pt"
        old_ckpt.write_bytes(b"old")
        retrainer._states["DEV_1"] = DeviceRetrainState(
            months_accumulated  = 2,
            last_retrain_date   = "2026-05-01",
            checkpoint_filename = old_ckpt.name,
            is_mature           = False,
        )
        retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        assert not old_ckpt.exists()

    def test_no_immediate_retry_same_month(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=3)
        retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        assert retrainer.should_retrain("DEV_1", _fake_df()) is False

    def test_is_mature_set_at_m12(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=12)
        retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        assert retrainer._states["DEV_1"].is_mature is True

    def test_state_persisted_to_disk(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=5)
        retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        reloaded = MonthlyRetrainer(retrainer.config)
        assert reloaded._states["DEV_1"].months_accumulated == 5


class TestRetrainFineTuneFailed:
    """Régression pour AD/HotStart/energy(|water)/retrain_job.py : le job
    créditait un device de retrained[dev]=months_accumulated même quand le
    fine-tuning avait échoué, faisant croire à un nouveau modèle inexistant.
    retrain() doit renvoyer FAILED pour que l'appelant ne le compte pas comme
    "retraîné"."""

    def test_returns_failed_outcome(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=3, fine_tune_success=False)
        outcome = retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        assert outcome is RetrainOutcome.FAILED

    def test_state_left_untouched_on_failure(self, tmp_path, monkeypatch):
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=3, fine_tune_success=False)
        retrainer._states["DEV_1"] = DeviceRetrainState(
            months_accumulated  = 2,
            last_retrain_date   = "2026-04-01",
            checkpoint_filename = "DEV_1_m02.pt",
            is_mature           = False,
        )
        retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        state = retrainer._states["DEV_1"]
        assert state.months_accumulated == 2
        assert state.checkpoint_filename == "DEV_1_m02.pt"

    def test_should_retrain_stays_true_after_failure(self, tmp_path, monkeypatch):
        """A genuine fine-tune failure (transient error) must be retried on
        the very next run."""
        retrainer = _make_retrainer(tmp_path, monkeypatch, months_now=3, fine_tune_success=False)
        retrainer.retrain("DEV_1", _fake_df(), pipeline=object())

        assert retrainer.should_retrain("DEV_1", _fake_df()) is True
