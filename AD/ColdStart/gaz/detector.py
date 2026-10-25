"""
Cold-start detector for gaz.
Ensemble : Z-score + IQR + Isolation Forest.

Gaz vs water specifics :
  - Z-score lower bound clamped to 0 (no negative flow)
  - IQR fence stricter (iqr_multiplier=1.8, gaz is less skewed)
  - IF features: [conso, hour_sin, hour_cos, dow_sin, dow_cos, is_low_period]
    → is_low_period replaces is_offline: flags hours 23h-5h (normally very low)
      This helps IF distinguish "low but normal at night" from "zero = anomalous"
  - regime_change_hours = 24h (fuite gaz = urgence absolue)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from common.chronos_detector import ChronosZeroShotDetector

from common.logger import get_logger
from .config import ColdStartAlgorithm, GazColdStartConfig
from .profile_builder import GazPopulationProfile

_log = get_logger(__name__)


@dataclass(slots=True)
class AlgoResult:
    name:          str
    is_anomaly:    np.ndarray
    anomaly_score: np.ndarray
    lower_bound:   np.ndarray | None = None
    upper_bound:   np.ndarray | None = None


# ── Z-Score ───────────────────────────────────────────────────────────────────

class _ZScoreDetector:
    def __init__(self, profile: GazPopulationProfile, threshold: float) -> None:
        self.mu        = profile.pop_mean
        self.sigma     = max(profile.pop_std, 1e-9)
        self.threshold = threshold

    def detect(self, values: np.ndarray) -> AlgoResult:
        z       = (values - self.mu) / self.sigma
        is_anom = np.abs(z) > self.threshold
        score   = np.clip(np.abs(z) / self.threshold, 0.0, 10.0)
        score   = np.where(is_anom, score, 0.0)
        lower   = np.maximum(
            np.full(len(values), self.mu - self.threshold * self.sigma), 0.0
        )
        upper   = np.full(len(values), self.mu + self.threshold * self.sigma)
        return AlgoResult("zscore", is_anom, score, lower, upper)


# ── IQR ───────────────────────────────────────────────────────────────────────

class _IQRDetector:
    def __init__(self, profile: GazPopulationProfile, multiplier: float) -> None:
        iqr          = profile.pop_q75 - profile.pop_q25
        self.lower   = max(profile.pop_q25 - multiplier * iqr, 0.0)
        self.upper   = profile.pop_q75 + multiplier * iqr
        self.iqr_range = max(multiplier * iqr, 1e-9)

    def detect(self, values: np.ndarray) -> AlgoResult:
        is_anom = (values < self.lower) | (values > self.upper)
        beyond  = np.maximum(values - self.upper, 0.0) + np.maximum(self.lower - values, 0.0)
        score   = np.clip(beyond / self.iqr_range, 0.0, 10.0)
        score   = np.where(is_anom, score, 0.0)
        return AlgoResult(
            "iqr", is_anom, score,
            np.full(len(values), self.lower),
            np.full(len(values), self.upper),
        )


# ── Isolation Forest ──────────────────────────────────────────────────────────

class _IsolationForestDetector:
    """
    IF for gaz with temporal features.
    Features: [conso, hour_sin, hour_cos, dow_sin, dow_cos, is_low_period]

    is_low_period (hours 23h-5h): gas flow very low normally at night.
    Helps IF learn night-zero is normal, day-zero is suspicious.
    """

    def __init__(
        self, n_estimators: int, max_samples: int,
        contamination: float, seed: int | None,
    ) -> None:
        self._model = IsolationForest(
            n_estimators  = n_estimators,
            max_samples   = max_samples,
            contamination = contamination,
            random_state  = seed,
            n_jobs        = -1,
        )
        self._is_fitted = False

    def fit(self, df: pd.DataFrame, value_col: str, ts_col: str) -> None:
        X = self._build_features(df, value_col, ts_col)
        self._model.fit(X)
        self._is_fitted = True
        _log.info("IF gaz entraine : %d points — contamination=%.2f", len(X), self._model.contamination)

    def detect(self, df: pd.DataFrame, value_col: str, ts_col: str) -> AlgoResult:
        if not self._is_fitted:
            raise RuntimeError("fit() must be called before detect()")
        X          = self._build_features(df, value_col, ts_col)
        labels     = self._model.predict(X)
        raw_scores = self._model.decision_function(X)
        is_anom    = labels == -1
        neg_scores = -raw_scores
        max_dev    = max(float(neg_scores.max()), 1e-9)
        score      = np.clip(neg_scores / max_dev * 10.0, 0.0, 10.0)
        score      = np.where(is_anom, score, 0.0)
        return AlgoResult("isolation_forest", is_anom, score)

    @staticmethod
    def _build_features(df: pd.DataFrame, value_col: str, ts_col: str) -> np.ndarray:
        ts  = pd.to_datetime(df[ts_col])
        val = df[value_col].fillna(0.0).to_numpy()

        hour = ts.dt.hour.to_numpy()
        dow  = ts.dt.dayofweek.to_numpy()

        hour_sin = np.sin(2 * np.pi * hour / 24.0)
        hour_cos = np.cos(2 * np.pi * hour / 24.0)
        dow_sin  = np.sin(2 * np.pi * dow  / 7.0)
        dow_cos  = np.cos(2 * np.pi * dow  / 7.0)

        # Gaz : période nocturne (23h-5h) = faible consommation normale
        is_low_period = ((hour >= 23) | (hour <= 5)).astype(float)

        return np.column_stack([val, hour_sin, hour_cos, dow_sin, dow_cos, is_low_period])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _classify_anomaly_type(flags: np.ndarray, threshold: int) -> tuple[np.ndarray, np.ndarray]:
    is_point  = np.zeros(len(flags), dtype=bool)
    is_regime = np.zeros(len(flags), dtype=bool)
    if not flags.any():
        return is_point, is_regime
    padded = np.concatenate([[False], flags.astype(bool), [False]])
    starts = np.where(~padded[:-1] &  padded[1:])[0]
    ends   = np.where( padded[:-1] & ~padded[1:])[0]
    for s, e in zip(starts, ends):
        if (e - s) > threshold:
            is_regime[s:e] = True
        else:
            is_point[s:e]  = True
    return is_point, is_regime


def _ensemble_vote(
    results: list[AlgoResult], min_votes: int, offline: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if not results:
        n = len(offline)
        return np.zeros(n, dtype=bool), np.zeros(n)
    vote_matrix  = np.stack([r.is_anomaly.astype(int) for r in results], axis=1)
    votes        = vote_matrix.sum(axis=1)
    is_anom      = votes >= min_votes
    score_matrix = np.stack([r.anomaly_score for r in results], axis=1)
    score        = score_matrix.max(axis=1)
    score        = np.where(is_anom, score, 0.0)
    return is_anom, score


def _make_fallback_training_data(
    profile: GazPopulationProfile, config: GazColdStartConfig, col: str,
) -> pd.DataFrame:
    """Fallback synthétique si données manquantes pour l'entraînement IF."""
    rng   = np.random.default_rng(config.synthetic_seed)
    n     = config.synthetic_days * 24
    start = pd.Timestamp("2025-01-01")
    ts    = pd.date_range(start, periods=n, freq="1h")
    # Gaz : distribution normale tronquée à 0
    values  = rng.normal(profile.pop_mean, profile.pop_std, n)
    values  = np.maximum(values, 0.0)
    offline = rng.random(n) < profile.pop_pct_offline
    values[offline] = 0.0
    values = np.clip(values, 0.0, profile.pop_q90 * 3)
    return pd.DataFrame({
        config.timestamp_col: ts,
        col:                   values,
        config.item_col:       str(config.new_device_id),
    })


# ── Main detector ─────────────────────────────────────────────────────────────

class GazColdStartDetector:
    """
    Cold-start detector for gaz devices.
    Ensemble Z-score + IQR + Isolation Forest.
    No phase dimension: item_id = device_id.
    """

    def __init__(
        self, profiles: dict[str, GazPopulationProfile], config: GazColdStartConfig,
    ) -> None:
        self.profiles = profiles
        self.config   = config
        self._fitted: dict[str, dict[str, object]] = {}

    def fit(self, synthetic_df: pd.DataFrame) -> None:
        cfg = self.config

        for col, profile in self.profiles.items():
            self._fitted[col] = {}

            if cfg.algorithm in (ColdStartAlgorithm.ZSCORE, ColdStartAlgorithm.ENSEMBLE):
                self._fitted[col]["zscore"] = _ZScoreDetector(profile, cfg.zscore_threshold_for(col))

            if cfg.algorithm in (ColdStartAlgorithm.IQR, ColdStartAlgorithm.ENSEMBLE):
                self._fitted[col]["iqr"] = _IQRDetector(profile, cfg.iqr_multiplier_for(col))

            if cfg.algorithm in (ColdStartAlgorithm.ISOLATION_FOREST, ColdStartAlgorithm.ENSEMBLE):
                if_det = _IsolationForestDetector(
                    n_estimators  = cfg.if_n_estimators,
                    max_samples   = cfg.if_max_samples,
                    contamination = cfg.if_contamination,
                    seed          = cfg.synthetic_seed,
                )
                col_data = synthetic_df if (not synthetic_df.empty and col in synthetic_df.columns) \
                           else pd.DataFrame()
                if col_data.empty:
                    _log.warning("Donnees synthetiques vides pour '%s' — fallback", col)
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

            _log.info("Detecteurs gaz prets pour '%s' : %s", col, list(self._fitted[col].keys()))

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit() must be called before detect()")

        cfg         = self.config
        all_results: list[pd.DataFrame] = []

        for item_id, group in df.groupby(cfg.item_col):
            group = group.sort_values(cfg.timestamp_col).copy()
            group["is_anomaly"]    = False
            group["anomaly_score"] = 0.0

            for col, detectors in self._fitted.items():
                if col not in group.columns:
                    continue

                values  = group[col].fillna(0.0).to_numpy()
                offline = values == 0.0   # heure offline gaz

                results: list[AlgoResult] = []
                for algo_name, det in detectors.items():
                    if algo_name == "isolation_forest":
                        r = det.detect(group, col, cfg.timestamp_col)
                    elif algo_name == "chronos":
                        is_a, sc, lb, ub = det.detect(group, col, cfg.timestamp_col, str(item_id))  # type: ignore[union-attr]
                        r = AlgoResult("chronos", is_a, sc, lb, ub)
                    else:
                        r = det.detect(values)

                    # Z-score, IQR, Chronos : ne pas pénaliser les heures normalement offline
                    if algo_name in ("zscore", "iqr", "chronos"):
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

            flag_cols = [
                f"is_anomaly_{col}" for col in self._fitted
                if f"is_anomaly_{col}" in group.columns
            ]
            if flag_cols:
                vote = pd.concat(
                    [group[c].astype(int) for c in flag_cols], axis=1
                ).sum(axis=1)
                group["is_anomaly"] = vote >= 1

            group["is_offline"] = group[cfg.value_col] == 0

            real_mask = ~group.get("is_synthetic", pd.Series(False, index=group.index))
            n_real    = int(real_mask.sum())
            group["warmup_active"] = n_real < cfg.warmup_hours

            all_results.append(group)

        if not all_results:
            return df

        final = pd.concat(all_results, ignore_index=True)

        # ── Classify point vs regime change ──────────────────────────────
        items      = final[cfg.item_col].unique()
        threshold  = cfg.regime_change_hours   # gaz : 24h = urgence
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

        _log.info(
            "Detection cold start gaz : %d anomalies (%d ponctuelles, %d regime)",
            int(final["is_anomaly"].sum()),
            int(point_all.sum()),
            int(regime_all.sum()),
        )
        return final
