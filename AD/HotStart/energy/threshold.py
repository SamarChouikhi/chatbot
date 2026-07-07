from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class ThresholdStrategy(str, Enum):
    # FIXED    → on utilise directement les bornes Chronos (q10/q90), sans ajustement
    FIXED    = "fixed"
    # SIGMA    → intersection des bornes Chronos ET de la bande μ ± k·σ de l'historique
    #            une anomalie doit sortir des DEUX zones à la fois → moins de faux positifs
    SIGMA    = "sigma"
    # ADAPTIVE → on élargit la bande Chronos proportionnellement à la volatilité du capteur
    #            un capteur très variable a une bande plus large → moins sensible aux petites variations
    ADAPTIVE = "adaptive"


@dataclass(frozen=True)
class ThresholdBounds:
    low:      np.ndarray
    high:     np.ndarray
    strategy: ThresholdStrategy


class DynamicThresholdEngine:
    """
    Computes per-series anomaly bounds that adapt to each series' historical statistics.

    Takes raw Chronos quantile predictions and adjusts the detection interval
    based on context window statistics (mean, std, coefficient of variation).
    Called once per series per detection run — O(context_length) overhead only.

    Strategies
    ----------
    FIXED    : pass-through, no adjustment (deterministic baseline)
    SIGMA    : intersection of Chronos interval with μ ± k·σ of the context.
               Flags only points that deviate on BOTH temporal pattern (Chronos)
               AND magnitude distribution (σ-bound). Robust against noisy sensors.
    ADAPTIVE : scales Chronos half-width by (1 + α·CV). High-volatility series get
               wider bounds (less sensitive); stable series get tighter bounds.
               CV is capped at max_cv_scale to prevent unbounded widening.

    Note: when fuel domain is added, move this module to common/.
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
        """
        Rejoue le calcul de seuil à partir des statistiques de contexte pré-calculées
        (ctx_mu, ctx_sigma) au lieu de la série de contexte complète.

        Utilisé par le cache : évite de recharger les 720h de contexte pour chaque
        fenêtre — on a juste besoin de mu et sigma qui sont stockés dans le cache.
        Résultat identique à compute() pour les mêmes paramètres.
        """
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
        """Stratégie SIGMA avec mu/std déjà calculés (chemin rapide cache)."""
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
        """Stratégie ADAPTIVE avec mu/std déjà calculés (chemin rapide cache)."""
        cv         = std / (abs(mu) + 1e-9)
        scale      = 1.0 + self.alpha * min(cv, self.max_cv_scale)
        half_width = (pred_high - pred_low) / 2.0
        return ThresholdBounds(
            low      = pred_median - scale * half_width,
            high     = pred_median + scale * half_width,
            strategy = self.strategy,
        )

    # ── Private strategies ────────────────────────────────────────────────

    def _sigma(
        self,
        context:   pd.Series,
        pred_low:  np.ndarray,
        pred_high: np.ndarray,
    ) -> ThresholdBounds:
        mu  = float(context.mean())
        std = float(context.std(ddof=1))

        sigma_low  = np.full(len(pred_low),  mu - self.k_sigma * std)
        sigma_high = np.full(len(pred_high), mu + self.k_sigma * std)

        # Union des deux intervalles : un point est anormal seulement s'il sort
        # à la fois de l'intervalle Chronos ET de la bande σ → beaucoup moins de faux positifs
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
        std = float(context.std(ddof=1))
        # CV élevé = capteur instable → bande plus large, moins de faux positifs
        cv  = std / (abs(mu) + 1e-9)
        # max_cv_scale borne le facteur pour éviter une bande infinie sur les séries très bruitées
        scale      = 1.0 + self.alpha * min(cv, self.max_cv_scale)
        half_width = (pred_high - pred_low) / 2.0
        # Centré sur la médiane Chronos, pas sur la borne originale
        return ThresholdBounds(
            low      = pred_median - scale * half_width,
            high     = pred_median + scale * half_width,
            strategy = self.strategy,
        )
