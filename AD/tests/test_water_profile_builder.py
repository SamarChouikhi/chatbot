"""Tests unitaires — ColdStart/water/profile_builder.py

Régression pour le bug : le seuil d'exclusion "échelle incohérente"
(off_scale) était calculé sur device_means AVANT l'exclusion des devices
too_few / too_offline. Un device peu fiable (trop peu de lignes) mais avec
une moyenne extrême pouvait donc gonfler la médiane inter-devices et
masquer un vrai device hors-échelle (ex. compteur collectif mélangé avec
des compteurs individuels), qui restait alors dans la population finale.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ColdStart"))

import numpy as np
import pandas as pd
import pytest

from water.config import WaterColdStartConfig
from water.profile_builder import load_population_data


def _make_population_csv(tmp_path: Path) -> Path:
    """4 devices, 1h resolution:
    - DEV_A, DEV_B : population "normale", moyenne ~10-11
    - DEV_C        : trop peu de lignes (3 < min_device_rows=10) et moyenne
                      extrême (1000) — doit être exclu par too_few, et ne doit
                      pas contaminer le calcul de la médiane inter-devices
    - DEV_D        : device réellement hors-échelle (moyenne ~200, ~19x la
                      médiane propre ~10.5) — doit être détecté et exclu
    """
    rng = np.random.default_rng(0)
    rows = []

    def _add(device: str, n: int, base: float):
        ts = pd.date_range("2026-01-01", periods=n, freq="h")
        vals = base + rng.normal(0, base * 0.02, size=n)
        for t, v in zip(ts, vals):
            rows.append({"date": t, "id_device": device, "conso": float(v)})

    _add("DEV_A", 20, 10.0)
    _add("DEV_B", 20, 11.0)
    _add("DEV_C", 3, 1000.0)
    _add("DEV_D", 20, 200.0)

    df = pd.DataFrame(rows)
    csv_path = tmp_path / "population.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


def _make_config(csv_path: Path) -> WaterColdStartConfig:
    return WaterColdStartConfig(
        population_data_path   = str(csv_path),
        new_device_id           = "NEW_WATER_TEST",
        min_device_rows          = 10,
        max_pct_offline           = 0.90,
        max_device_scale_ratio    = 10.0,
    )


class TestOffScaleExclusion:
    def test_off_scale_device_is_excluded(self, tmp_path):
        config = _make_config(_make_population_csv(tmp_path))
        result = load_population_data(config)

        assert "DEV_D" not in set(result["item_id"].unique())

    def test_too_few_device_does_not_contaminate_threshold(self, tmp_path):
        """DEV_C (3 lignes, moyenne 1000) doit être exclu par too_few — et ne
        doit pas gonfler la médiane au point de laisser passer DEV_D."""
        config = _make_config(_make_population_csv(tmp_path))
        result = load_population_data(config)

        remaining = set(result["item_id"].unique())
        assert "DEV_C" not in remaining
        assert "DEV_D" not in remaining

    def test_reliable_devices_are_kept(self, tmp_path):
        config = _make_config(_make_population_csv(tmp_path))
        result = load_population_data(config)

        remaining = set(result["item_id"].unique())
        assert remaining == {"DEV_A", "DEV_B"}
