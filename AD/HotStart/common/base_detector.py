from __future__ import annotations

import torch
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .logger import get_logger

_log = get_logger(__name__)


@dataclass(slots=True)
class ChronosPrediction:
    pred_low:       np.ndarray
    pred_median:    np.ndarray
    pred_high:      np.ndarray
    context_series: pd.Series


class ChronosDetector(ABC):

    def __init__(
        self,
        model_name:        str   = "autogluon/chronos-2-small",
        device:            str   = "cpu",
        context_length:    int   = 64,
        prediction_length: int   = 12,
        num_samples:       int   = 20,
        q_low:             float = 0.1,
        q_high:            float = 0.9,
    ) -> None:
        self.model_name        = model_name
        self.device            = device
        self.context_length    = context_length
        self.prediction_length = prediction_length
        self.num_samples       = num_samples
        if not (0 < q_low < 0.5 < q_high < 1):
            raise ValueError(
                f"q_low et q_high doivent vérifier 0 < q_low < 0.5 < q_high < 1, "
                f"reçu : q_low={q_low}, q_high={q_high}"
            )
        self.q_low  = q_low
        self.q_high = q_high
        self._pipeline = None

    # ── Model lifecycle ───────────────────────────────────────────────────

    def _load_pipeline(self) -> None:
        if self._pipeline is not None:
            return
        _log.info("Loading Chronos model: %s", self.model_name)
        try:
            from chronos import Chronos2Pipeline
            self._pipeline = Chronos2Pipeline.from_pretrained(
                self.model_name,
                device_map=self.device,
            )
            _log.info("Chronos model ready (Chronos2Pipeline)")
        except (ImportError, Exception) as exc:
            _log.warning(
                "Chronos2Pipeline unavailable (%s) — fallback to BaseChronosPipeline", exc
            )
            from chronos import BaseChronosPipeline
            dtype = torch.bfloat16 if self.device in ("cuda", "mps") else torch.float32
            self._pipeline = BaseChronosPipeline.from_pretrained(
                self.model_name,
                device_map=self.device,
                dtype=dtype,
            )
            _log.info("Chronos model ready (BaseChronosPipeline)")

    # ── Chronos calls ─────────────────────────────────────────────────────

    def _predict_window(
        self,
        ctx_series: pd.Series,
        item_id:    str,
        pred_len:   int,
    ) -> ChronosPrediction | None:
        if len(ctx_series) < 2:
            return None

        context = torch.tensor(
            ctx_series.tail(self.context_length).values,
            dtype=torch.float32,
        ).unsqueeze(0).unsqueeze(0)

        try:
            quantiles, _ = self._pipeline.predict_quantiles(  # type: ignore[union-attr]
                context,
                prediction_length=pred_len,
                quantile_levels=[self.q_low, 0.5, self.q_high],
            )
            q = quantiles[0][0].numpy()
            low, median, high = q[:, 0], q[:, 1], q[:, 2]
            return ChronosPrediction(
                pred_low=low, pred_median=median, pred_high=high,
                context_series=ctx_series,
            )
        except Exception as exc:  # noqa: BLE001
            _log.error("[%s] window prediction failed: %s", item_id, exc)
            return None

    # ── Score ─────────────────────────────────────────────────────────────

    @staticmethod
    def _anomaly_score(
        actual:       np.ndarray,
        chronos_low:  np.ndarray,
        chronos_high: np.ndarray,
    ) -> np.ndarray:
        """Score normalisé par l'intervalle Chronos brut (pas l'intervalle élargi SIGMA)."""
        interval = np.maximum(
            chronos_high - chronos_low,
            np.abs(actual) * 0.01 + 1e-3,
        )
        raw = np.where(
            actual > chronos_high,
            (actual - chronos_high) / interval,
            np.where(actual < chronos_low, (chronos_low - actual) / interval, 0.0),
        )
        return np.clip(raw, 0.0, 10.0)

    # ── Public interface ──────────────────────────────────────────────────

    @abstractmethod
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run full detection on df. Returns df with anomaly columns added."""
