from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from common.threshold import ThresholdStrategy

_DEFAULT_YAML = Path(__file__).parent / "config.yaml"


@dataclass
class GazConfig:
    # ── I/O ───────────────────────────────────────────────────────────────
    data_path:  str = "C:/Users/LEGION/Downloads/gaz.csv"
    output_dir: str = "outputs/gaz"

    # ── Date filter (optional) ────────────────────────────────────────────
    date_debut: str | None = None
    date_fin:   str | None = None

    # ── Anomaly voting threshold ──────────────────────────────────────────
    min_features_anomalous: int = 1

    # ── Columns ───────────────────────────────────────────────────────────
    timestamp_col: str       = "date"
    value_cols:    list[str] = field(default_factory=lambda: ["conso", "avg_debit_per_min"])
    item_col:      str       = "item_id"
    device_col:    str       = "id_device"

    # ── Chronos ───────────────────────────────────────────────────────────
    model_name:        str   = "autogluon/chronos-2-small"
    device:            str   = "cpu"
    context_length:    int   = 720
    prediction_length: int   = 24
    num_samples:       int   = 20
    q_low:             float = 0.10
    q_high:            float = 0.90

    # ── Dynamic Threshold ─────────────────────────────────────────────────
    threshold_strategy: ThresholdStrategy = ThresholdStrategy.SIGMA
    k_sigma:            float = 2.5
    alpha:              float = 0.5
    max_cv_scale:       float = 2.0

    # ── Resampling ────────────────────────────────────────────────────────
    resample_freq:        str   = "1h"
    ffill_limit:          int   = 3
    min_device_rows:      int   = 48
    rollover_iqr_factor:  float = 30.0
    max_pct_offline:      float = 0.80   # gaz : moins tolérant aux offline que eau

    # ── Sliding window ────────────────────────────────────────────────────
    slide_step: int = 24

    # ── Visualization ─────────────────────────────────────────────────────
    zoom_hours: int = 168

    # ── Regime change detection ───────────────────────────────────────────
    regime_change_hours: int = 48

    # ── Forecasting ───────────────────────────────────────────────────────
    forecast_horizon: int   = 168
    min_confidence:   float = 0.3

    # ── Adaptive Calibration ──────────────────────────────────────────────
    calibration_active:           bool  = True
    calibration_hours:            int   = 1440
    calibration_threshold_factor: float = 1.0
    calibration_drift_z:          float = 3.0
    calibration_force:            bool  = False

    @property
    def calibration_profile_path(self) -> Path:
        return Path(self.output_dir) / "device_profiles.json"

    @property
    def value_col(self) -> str:
        return self.value_cols[0]

    @classmethod
    def from_file(cls) -> "GazConfig":
        return cls.from_yaml(_DEFAULT_YAML)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "GazConfig":
        import yaml

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {path}\n"
                f"Expected location: HotStart/gaz/config.yaml"
            )

        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        defaults = cls()
        d     = raw.get("donnees",      {})
        det   = raw.get("detection",    {})
        m     = raw.get("modele",       {})
        s     = raw.get("seuil",        {})
        a     = raw.get("avance",       {})
        p     = raw.get("prevision",    {})
        calib = raw.get("calibration",  {})

        try:
            strategy = ThresholdStrategy(
                s.get("strategie", defaults.threshold_strategy.value)
            )
        except ValueError as exc:
            valid = [e.value for e in ThresholdStrategy]
            raise ValueError(
                f"Strategie invalide dans config.yaml: "
                f"{s.get('strategie')!r}. Valeurs valides : {valid}"
            ) from exc

        value_cols = det.get("colonnes", defaults.value_cols)
        if isinstance(value_cols, str):
            value_cols = [value_cols]

        instance = cls(
            data_path              = d.get("fichier",               defaults.data_path),
            output_dir             = d.get("dossier_resultats",     defaults.output_dir),
            date_debut             = d.get("date_debut",            defaults.date_debut),
            date_fin               = d.get("date_fin",              defaults.date_fin),
            value_cols             = value_cols,
            min_features_anomalous = int(det.get("min_features_anomalous", defaults.min_features_anomalous)),
            model_name             = m.get("nom",              defaults.model_name),
            device                 = m.get("accelerateur",    defaults.device),
            context_length         = int(m.get("historique_heures",  defaults.context_length)),
            prediction_length      = int(m.get("prediction_heures",  defaults.prediction_length)),
            num_samples            = int(m.get("num_echantillons",   defaults.num_samples)),
            threshold_strategy     = strategy,
            k_sigma                = float(s.get("k_sigma",                  defaults.k_sigma)),
            alpha                  = float(s.get("alpha",                    defaults.alpha)),
            max_cv_scale           = float(s.get("max_facteur_volatilite",   defaults.max_cv_scale)),
            q_low                  = float(s.get("percentile_bas",           defaults.q_low)),
            q_high                 = float(s.get("percentile_haut",          defaults.q_high)),
            resample_freq          = a.get("frequence",           defaults.resample_freq),
            ffill_limit            = int(a.get("limite_completion",   defaults.ffill_limit)),
            min_device_rows        = int(a.get("min_lignes_device",    defaults.min_device_rows)),
            rollover_iqr_factor    = float(a.get("facteur_rollover",   defaults.rollover_iqr_factor)),
            max_pct_offline        = float(a.get("max_pct_offline",    defaults.max_pct_offline)),
            slide_step             = int(a.get("pas_glissement",      defaults.slide_step)),
            zoom_hours             = int(a.get("zoom_heures",        defaults.zoom_hours)),
            regime_change_hours    = int(a.get("seuil_regime_heures",defaults.regime_change_hours)),
            forecast_horizon             = int(p.get("horizon_heures",          defaults.forecast_horizon)),
            min_confidence               = float(p.get("confiance_min",         defaults.min_confidence)),
            calibration_active           = bool(calib.get("active",             defaults.calibration_active)),
            calibration_hours            = int(calib.get("heures",              defaults.calibration_hours)),
            calibration_threshold_factor = float(calib.get("facteur_seuil",     defaults.calibration_threshold_factor)),
            calibration_drift_z          = float(calib.get("seuil_drift_z",     defaults.calibration_drift_z)),
            calibration_force            = bool(calib.get("force",              defaults.calibration_force)),
        )
        instance._validate()
        return instance

    def _validate(self) -> None:
        errors: list[str] = []
        if not self.value_cols:
            errors.append("detection.colonnes ne peut pas etre vide")
        if self.context_length <= 0:
            errors.append("historique_heures doit etre > 0")
        if self.prediction_length <= 0:
            errors.append("prediction_heures doit etre > 0")
        if self.context_length <= self.prediction_length:
            errors.append(
                f"historique_heures ({self.context_length}) doit etre "
                f"> prediction_heures ({self.prediction_length})"
            )
        if not (0 < self.q_low < self.q_high < 1):
            errors.append(
                f"percentile_bas ({self.q_low}) doit etre < percentile_haut ({self.q_high}) "
                f"et tous les deux dans ]0, 1["
            )
        if self.k_sigma <= 0:
            errors.append("k_sigma doit etre > 0")
        if self.forecast_horizon <= 0:
            errors.append("prevision.horizon_heures doit etre > 0")
        if not (0.0 <= self.min_confidence <= 1.0):
            errors.append(
                f"prevision.confiance_min ({self.min_confidence}) doit etre dans [0, 1]"
            )
        if self.min_device_rows < 1:
            errors.append("min_lignes_device doit etre >= 1")
        if self.rollover_iqr_factor <= 0:
            errors.append("facteur_rollover doit etre > 0")
        if not (0.0 < self.max_pct_offline <= 1.0):
            errors.append(
                f"max_pct_offline ({self.max_pct_offline}) doit etre dans ]0, 1]"
            )
        if self.calibration_active and self.calibration_hours < self.prediction_length * 3:
            errors.append(
                f"calibration.heures ({self.calibration_hours}) doit etre "
                f">= prediction_heures x 3 ({self.prediction_length * 3})"
            )
        if self.calibration_threshold_factor <= 0:
            errors.append("calibration.facteur_seuil doit etre > 0")
        if errors:
            raise ValueError(
                "Erreurs dans config.yaml :\n" + "\n".join(f"  - {e}" for e in errors)
            )
