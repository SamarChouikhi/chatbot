from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from common.chronos_detector import ChronosZeroShotDetector
from common.logger import get_logger
from .config import ColdStartAlgorithm, ColdStartConfig
from .profile_builder import PopulationProfile

_log = get_logger(__name__)


# ── Result container ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class AlgoResult:
    name:          str
    is_anomaly:    np.ndarray   # bool
    anomaly_score: np.ndarray   # float [0, 10]
    lower_bound:   np.ndarray | None = None
    upper_bound:   np.ndarray | None = None


# ── Individual algorithm implementations ──────────────────────────────────────

class _ZScoreDetector:
    """
    Detects anomalies using the Z-score relative to population statistics.
    z = (x - μ_pop) / σ_pop  →  |z| > threshold → anomaly
    Score = min(|z| / threshold, 10) — normalized so threshold maps to score 1.0.
    """

    def __init__(self, profile: PopulationProfile, threshold: float) -> None:
        self.mu        = profile.pop_mean
        self.sigma     = max(profile.pop_std, 1e-9)
        self.threshold = threshold

    def detect(self, values: np.ndarray) -> AlgoResult:
        z      = (values - self.mu) / self.sigma
        is_anom = np.abs(z) > self.threshold
        score   = np.clip(np.abs(z) / self.threshold, 0.0, 10.0)
        score   = np.where(is_anom, score, 0.0)
        lower   = np.full(len(values), self.mu - self.threshold * self.sigma)
        upper   = np.full(len(values), self.mu + self.threshold * self.sigma)
        return AlgoResult("zscore", is_anom, score, lower, upper)


class _IQRDetector:
    """
    Detects anomalies using Tukey IQR fences computed from population percentiles.
    Lower fence = Q25 - k × IQR
    Upper fence = Q75 + k × IQR
    Score = distance beyond fence / (k × IQR), clipped to [0, 10].
    """

    def __init__(self, profile: PopulationProfile, multiplier: float) -> None:
        iqr          = profile.pop_q75 - profile.pop_q25
        self.lower   = profile.pop_q25 - multiplier * iqr
        self.upper   = profile.pop_q75 + multiplier * iqr
        self.iqr_range = max(multiplier * iqr, 1e-9)

    def detect(self, values: np.ndarray) -> AlgoResult:
        is_anom = (values < self.lower) | (values > self.upper)
        beyond  = np.maximum(values - self.upper, 0.0) + np.maximum(self.lower - values, 0.0)
        score   = np.clip(beyond / self.iqr_range, 0.0, 10.0)
        score   = np.where(is_anom, score, 0.0)
        lower   = np.full(len(values), self.lower)
        upper   = np.full(len(values), self.upper)
        return AlgoResult("iqr", is_anom, score, lower, upper)


class _IsolationForestDetector:
    """
    Isolation Forest trained on synthetic population data.

    Features: [value, hour_of_day, day_of_week]
    — The temporal features are critical: they let IF learn that a high value
      at 2 AM is more anomalous than the same value at 2 PM.

    Score: decision_function output remapped to [0, 10] via:
      raw IF score is negative for anomalies, positive for normal points
      anomaly_score = clip(-(raw_score) / max_deviation × 10, 0, 10)
    """

    def __init__(
        self,
        n_estimators:  int,
        max_samples:   int,
        contamination: float,
        seed:          int | None,
    ) -> None:
        self._model = IsolationForest(
            n_estimators = n_estimators,
            max_samples  = max_samples,
            contamination= contamination,
            random_state = seed,
            n_jobs       = -1,
        )
        self._is_fitted = False

    def fit(self, df: pd.DataFrame, value_col: str, ts_col: str) -> None:
        """Train on synthetic data with temporal features."""
        X = self._build_features(df, value_col, ts_col)
        self._model.fit(X)
        self._is_fitted = True
        _log.info(
            "Isolation Forest entraîné : %d points — contamination=%.2f",
            len(X), self._model.contamination,
        )

    def detect(
        self,
        df:       pd.DataFrame,
        value_col: str,
        ts_col:    str,
    ) -> AlgoResult:
        if not self._is_fitted:
            raise RuntimeError("IsolationForestDetector.fit() must be called before detect()")

        X          = self._build_features(df, value_col, ts_col)
        labels     = self._model.predict(X)          # +1 = normal, -1 = anomaly
        raw_scores = self._model.decision_function(X)  # lower = more anomalous

        is_anom = labels == -1

        # Normalize: map decision_function to [0, 10] where 0=normal, 10=most anomalous
        # decision_function ∈ [~-0.5, ~0.5]; anomalies have negative values
        neg_scores = -raw_scores                     # higher = more anomalous
        max_dev    = max(float(neg_scores.max()), 1e-9)
        score      = np.clip(neg_scores / max_dev * 10.0, 0.0, 10.0)
        score      = np.where(is_anom, score, 0.0)

        return AlgoResult("isolation_forest", is_anom, score)

    @staticmethod
    def _build_features(
        df:        pd.DataFrame,
        value_col: str,
        ts_col:    str,
    ) -> np.ndarray:
        ts  = pd.to_datetime(df[ts_col])
        val = df[value_col].fillna(0.0).to_numpy()

        # Cyclical encoding of hour and day-of-week to preserve periodicity
        hour = ts.dt.hour.to_numpy()
        dow  = ts.dt.dayofweek.to_numpy()

        hour_sin = np.sin(2 * np.pi * hour / 24.0)
        hour_cos = np.cos(2 * np.pi * hour / 24.0)
        dow_sin  = np.sin(2 * np.pi * dow  / 7.0)
        dow_cos  = np.cos(2 * np.pi * dow  / 7.0)

        return np.column_stack([val, hour_sin, hour_cos, dow_sin, dow_cos])


# ── Ensemble detector ─────────────────────────────────────────────────────────

def _classify_anomaly_type(
    flags:     np.ndarray,
    threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Classify continuous anomaly runs as point anomaly vs regime change."""
    is_point  = np.zeros(len(flags), dtype=bool)
    is_regime = np.zeros(len(flags), dtype=bool)

    if not flags.any():
        return is_point, is_regime

    padded = np.concatenate([[False], flags.astype(bool), [False]])
    starts = np.where(~padded[:-1] & padded[1:])[0]
    ends   = np.where( padded[:-1] & ~padded[1:])[0]

    for s, e in zip(starts, ends):
        if (e - s) > threshold:
            is_regime[s:e] = True
        else:
            is_point[s:e]  = True

    return is_point, is_regime


class ColdStartDetector:
    """
    Lightweight anomaly detector for devices with no historical data.

    Fits on synthetic population-derived data, then detects anomalies in the
    new device's real data using an ensemble of Z-Score, IQR, and Isolation Forest.

    The fit/detect separation mirrors sklearn's API, allowing the fitted model
    to be reused across multiple new-device data batches without re-training.
    """

    def __init__(
        self,
        profiles: dict[str, PopulationProfile],   # col → PopulationProfile
        config:   ColdStartConfig,
    ) -> None:
        self.profiles = profiles
        self.config   = config
        self._fitted: dict[str, dict[str, object]] = {}   # col → algo_name → detector

    # ── Fit ──────────────────────────────────────────────────────────────────

    def fit(self, synthetic_df: pd.DataFrame) -> None:
        """
        Initialize detectors from population statistics and optionally
        train Isolation Forest on synthetic_df.
        """
        cfg = self.config

        for col, profile in self.profiles.items():
            self._fitted[col] = {}

            if cfg.algorithm in (ColdStartAlgorithm.ZSCORE, ColdStartAlgorithm.ENSEMBLE):
                self._fitted[col]["zscore"] = _ZScoreDetector(
                    profile, cfg.zscore_threshold
                )

            if cfg.algorithm in (ColdStartAlgorithm.IQR, ColdStartAlgorithm.ENSEMBLE):
                self._fitted[col]["iqr"] = _IQRDetector(
                    profile, cfg.iqr_multiplier
                )

            if cfg.algorithm in (ColdStartAlgorithm.ISOLATION_FOREST, ColdStartAlgorithm.ENSEMBLE):
                if_det = _IsolationForestDetector(
                    n_estimators  = cfg.if_n_estimators,
                    max_samples   = cfg.if_max_samples,
                    contamination = cfg.if_contamination,
                    seed          = cfg.synthetic_seed,
                )
                # Train on synthetic data for this column (item_id-agnostic)
                col_data = synthetic_df[synthetic_df[cfg.item_col].str.endswith(
                    tuple(cfg.new_device_phases)
                )].copy() if not synthetic_df.empty else synthetic_df

                if col_data.empty or col not in col_data.columns:
                    _log.warning(
                        "Données synthétiques vides pour '%s' — IF entraîné sur distribution artificielle",
                        col,
                    )
                    col_data = _make_fallback_training_data(profile, cfg, col)

                if_det.fit(col_data, col, cfg.timestamp_col)
                self._fitted[col]["isolation_forest"] = if_det

            include_chronos = (
                cfg.algorithm == ColdStartAlgorithm.CHRONOS
                or (cfg.algorithm == ColdStartAlgorithm.ENSEMBLE and cfg.use_chronos_in_ensemble)
            )
            if include_chronos:
                ch_det = ChronosZeroShotDetector(
                    model_name        = cfg.chronos_model,
                    device            = cfg.chronos_device,
                    context_length    = cfg.chronos_context_length,
                    prediction_length = cfg.chronos_prediction_length,
                    num_samples       = cfg.chronos_num_samples,
                    q_low             = cfg.chronos_q_low,
                    q_high            = cfg.chronos_q_high,
                    k_sigma           = cfg.chronos_k_sigma,
                    item_col          = cfg.item_col,
                )
                ch_det.fit(synthetic_df, col, cfg.timestamp_col)
                self._fitted[col]["chronos"] = ch_det

            _log.info(
                "Détecteurs cold start prêts pour '%s' : %s",
                col, list(self._fitted[col].keys()),
            )

    # ── Detect ───────────────────────────────────────────────────────────────

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run detection on the new device's data (real or partially real).

        Returns df augmented with:
          - is_anomaly_{col}, anomaly_score_{col}, algo_{col}_{name} per value column
          - is_anomaly, anomaly_score  (global vote)
          - is_point_anomaly, is_regime_change (run-length classification)
          - warmup_active (bool: True while real data < warmup_hours)
        """
        if not self._fitted:
            raise RuntimeError("ColdStartDetector.fit() must be called before detect()")

        cfg = self.config
        all_results: list[pd.DataFrame] = []

        for item_id, group in df.groupby(cfg.item_col):
            group = group.sort_values(cfg.timestamp_col).copy()
            group["is_anomaly"]    = False
            group["anomaly_score"] = 0.0

            for col, detectors in self._fitted.items():
                if col not in group.columns:
                    _log.warning("[%s] colonne '%s' absente — ignorée", item_id, col)
                    continue

                values   = group[col].fillna(0.0).to_numpy()
                offline  = values == 0.0

                results: list[AlgoResult] = []

                for algo_name, det in detectors.items():
                    if algo_name == "isolation_forest":
                        r = det.detect(group, col, cfg.timestamp_col)   # type: ignore[union-attr]
                    elif algo_name == "chronos":
                        is_a, sc, lb, ub = det.detect(group, col, cfg.timestamp_col, str(item_id))  # type: ignore[union-attr]
                        r = AlgoResult("chronos", is_a, sc, lb, ub)
                    else:
                        r = det.detect(values)                          # type: ignore[union-attr]
                    # Offline points are never anomalous (device powered off)
                    r.is_anomaly[offline]    = False
                    r.anomaly_score[offline] = 0.0
                    results.append(r)

                    group[f"algo_{col}_{algo_name}"] = r.is_anomaly.astype(int)
                    if r.lower_bound is not None:
                        group[f"bound_low_{col}_{algo_name}"]  = r.lower_bound
                        group[f"bound_high_{col}_{algo_name}"] = r.upper_bound

                is_anom_col, score_col = _ensemble_vote(results, cfg.min_votes, offline)
                group[f"is_anomaly_{col}"]    = is_anom_col
                group[f"anomaly_score_{col}"] = score_col
                group["anomaly_score"] = group[
                    ["anomaly_score", f"anomaly_score_{col}"]
                ].max(axis=1)

            # Global anomaly flag = any column flagged (can tighten with min_features if needed)
            flag_cols = [f"is_anomaly_{col}" for col in self._fitted if f"is_anomaly_{col}" in group.columns]
            if flag_cols:
                vote = pd.concat(
                    [group[c].astype(int) for c in flag_cols], axis=1
                ).sum(axis=1)
                group["is_anomaly"] = vote >= 1

            group["is_offline"] = group[cfg.value_col] == 0

            # Warmup flag: first warmup_hours of real data → model is still in cold state
            real_mask = ~group.get("is_synthetic", pd.Series(False, index=group.index))
            n_real    = int(real_mask.sum())
            group["warmup_active"] = n_real < cfg.warmup_hours

            all_results.append(group)

        if not all_results:
            return df

        final = pd.concat(all_results, ignore_index=True)

        # ── Classify point vs regime change ───────────────────────────────────
        items      = final[cfg.item_col].unique()
        threshold  = cfg.regime_change_hours
        point_all  = np.zeros(len(final), dtype=bool)
        regime_all = np.zeros(len(final), dtype=bool)

        for item_id in items:
            mask  = (final[cfg.item_col] == item_id).to_numpy()
            flags = final.loc[mask, "is_anomaly"].to_numpy()
            pt, rg = _classify_anomaly_type(flags, threshold)
            point_all[mask]  = pt
            regime_all[mask] = rg

        final["is_point_anomaly"] = point_all
        final["is_regime_change"] = regime_all

        n_total  = int(final["is_anomaly"].sum())
        n_point  = int(point_all.sum())
        n_regime = int(regime_all.sum())
        _log.info(
            "Cold start detection : %d anomalies  (%d ponctuelles, %d régime)",
            n_total, n_point, n_regime,
        )

        return final


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensemble_vote(
    results:   list[AlgoResult],
    min_votes: int,
    offline:   np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Majority vote across algorithm results + max score aggregation."""
    if not results:
        n = len(offline)
        return np.zeros(n, dtype=bool), np.zeros(n)

    vote_matrix = np.stack([r.is_anomaly.astype(int) for r in results], axis=1)  # (n, k)
    votes       = vote_matrix.sum(axis=1)
    is_anom     = votes >= min_votes
    is_anom     = is_anom & ~offline

    # Aggregate score: max across all algorithms (conservative, keeps the strongest signal)
    score_matrix = np.stack([r.anomaly_score for r in results], axis=1)
    score        = score_matrix.max(axis=1)
    score        = np.where(is_anom, score, 0.0)

    return is_anom, score


def _make_fallback_training_data(
    profile: PopulationProfile,
    config:  ColdStartConfig,
    col:     str,
) -> pd.DataFrame:
    """Minimal synthetic data when the generator output is unavailable."""
    rng     = np.random.default_rng(config.synthetic_seed)
    n       = config.synthetic_days * 24
    start   = pd.Timestamp("2025-01-01")
    ts      = pd.date_range(start, periods=n, freq="1h")
    values  = rng.normal(profile.pop_mean, max(profile.pop_std, 1e-9), n)
    values  = np.clip(values, 0.0, profile.pop_q90 * 3)
    return pd.DataFrame({
        config.timestamp_col: ts,
        col:                   values,
        config.item_col:       f"{config.new_device_id}_L1",
    })
