
# Contient tous les paramètres du module energy — chargés depuis config.yaml.
# Si on ne passe pas de fichier, Python utilise les valeurs par défaut du dataclass.
from __future__ import annotations

from dataclasses import dataclass, field  # génère __init__, __repr__ automatiquement
from pathlib import Path
from typing import Union

from .threshold import ThresholdStrategy

# Chemin vers le config.yaml situé dans le même dossier que ce fichier
_DEFAULT_YAML = Path(__file__).parent / "config.yaml"


@dataclass
class EnergyConfig:
    # ── I/O ───────────────────────────────────────────────────────────────
    data_path:  str = "energy_by_phase.csv"
    output_dir: str = "outputs/energy"

    # ── Date filter (optional) ────────────────────────────────────────────
    date_debut: str | None = None   # "YYYY-MM-DD" inclusive, None = pas de filtre
    date_fin:   str | None = None   # "YYYY-MM-DD" inclusive, None = pas de filtre

    # ── Anomaly voting threshold ──────────────────────────────────────────
    min_features_anomalous: int = 1  # nb minimum de features anormales pour déclencher une alerte

    # ── Columns ───────────────────────────────────────────────────────────
    timestamp_col: str       = "date"
    value_cols:    list[str] = field(default_factory=lambda: ["cons_en"])
    item_col:      str       = "item_id"   # built as: id_device + "_" + phase
    device_col:    str       = "id_device"
    phase_col:     str       = "phase"
    

    # ── Chronos ───────────────────────────────────────────────────────────
    model_name:        str   = "autogluon/chronos-2-small"
    device:            str   = "cpu"
    context_length:    int   = 64
    prediction_length: int   = 12
    num_samples:       int   = 20
    q_low:             float = 0.1
    q_high:            float = 0.9

    # ── Dynamic Threshold ─────────────────────────────────────────────────
    threshold_strategy: ThresholdStrategy = ThresholdStrategy.SIGMA
    k_sigma:            float = 3.0
    alpha:              float = 0.5
    max_cv_scale:       float = 2.0

    # ── Resampling ────────────────────────────────────────────────────────
    resample_freq: str = "1h"
    ffill_limit:   int = 3

    # ── Sliding window ────────────────────────────────────────────────────
    slide_step: int = 168  # hours between detection windows (168 = weekly)

    # ── Visualization ─────────────────────────────────────────────────────
    zoom_hours: int = 76  # rows shown in the zoom panel (context + prediction)

    # ── Regime change detection ───────────────────────────────────────────
    regime_change_hours: int = 24  # consecutive anomaly run > this → regime change

    # ── Forecasting ───────────────────────────────────────────────────────
    forecast_horizon: int   = 48   # hours ahead to forecast
    min_confidence:   float = 0.3  # flag forecast as low-confidence below this

    # ── Monthly retraining (M1 → M12) ────────────────────────────────────
    retrain_enabled:    bool  = True
    fine_tune_epochs:   int   = 3
    fine_tune_lr:       float = 1e-4
    checkpoint_dir:     str   = "outputs/energy/checkpoints"
    retrain_state_file: str   = "outputs/energy/retrain_state.json"


    # ── Derived ───────────────────────────────────────────────────────────

    @property
    def value_col(self) -> str:
        """Primary column: used for visualization and preprocessing."""
        return self.value_cols[0]

    # ── Loaders ───────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls) -> "EnergyConfig":
        """Load from the canonical config.yaml co-located with this module."""
        return cls.from_yaml(_DEFAULT_YAML)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "EnergyConfig":
        """
        Load configuration from a YAML file.
        Missing keys fall back to dataclass defaults.
        """
        import yaml

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {path}\n"
                f"Expected location: HotStart/energy/config.yaml"
            )

        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        defaults = cls()
        # Les sections du YAML correspondent aux blocs logiques de la config :
        # donnees = chemins I/O | detection = colonnes analysées | modele = Chronos
        # seuil = stratégie de détection | avance = resampling/fenêtre | prevision = forecast
        d   = raw.get("donnees",    {})
        det = raw.get("detection",  {})
        m   = raw.get("modele",     {})
        s   = raw.get("seuil",      {})
        a   = raw.get("avance",     {})
        p   = raw.get("prevision",  {})
        r   = raw.get("retraining", {})

        try:
            strategy = ThresholdStrategy(
                s.get("strategie", defaults.threshold_strategy.value)
            )
        except ValueError as exc:
            valid = [e.value for e in ThresholdStrategy]
            raise ValueError(
                f"Stratégie invalide dans config.yaml: "
                f"{s.get('strategie')!r}. Valeurs valides : {valid}"
            ) from exc

        # Dans le YAML on peut écrire colonnes: "cons_en" (str) ou colonnes: ["cons_en", "moy_rms_current"] (liste)
        # On normalise toujours en liste pour que le reste du code n'ait pas à vérifier le type
        value_cols = det.get("colonnes", defaults.value_cols)
        if isinstance(value_cols, str):
            value_cols = [value_cols]

        instance = cls(
            data_path           = d.get("fichier",               defaults.data_path),
            output_dir          = d.get("dossier_resultats",     defaults.output_dir),
            date_debut              = d.get("date_debut",            defaults.date_debut),
            date_fin                = d.get("date_fin",              defaults.date_fin),
            value_cols              = value_cols,
            min_features_anomalous  = int(det.get("min_features_anomalous", defaults.min_features_anomalous)),
            model_name          = m.get("nom",                    defaults.model_name),
            device              = m.get("accelerateur",           defaults.device),
            context_length      = int(m.get("historique_heures",   defaults.context_length)),
            prediction_length   = int(m.get("prediction_heures",   defaults.prediction_length)),
            num_samples         = int(m.get("num_echantillons",    defaults.num_samples)),
            threshold_strategy  = strategy,
            k_sigma             = float(s.get("k_sigma",                   defaults.k_sigma)),
            alpha               = float(s.get("alpha",                     defaults.alpha)),
            max_cv_scale        = float(s.get("max_facteur_volatilite",    defaults.max_cv_scale)),
            q_low               = float(s.get("percentile_bas",            defaults.q_low)),
            q_high              = float(s.get("percentile_haut",           defaults.q_high)),
            resample_freq       = a.get("frequence",         defaults.resample_freq),
            ffill_limit         = int(a.get("limite_completion", defaults.ffill_limit)),
            slide_step          = int(a.get("pas_glissement",    defaults.slide_step)),
            zoom_hours          = int(a.get("zoom_heures",          defaults.zoom_hours)),
            regime_change_hours = int(a.get("seuil_regime_heures",   defaults.regime_change_hours)),
            forecast_horizon    = int(p.get("horizon_heures",        defaults.forecast_horizon)),
            min_confidence      = float(p.get("confiance_min",   defaults.min_confidence)),
            retrain_enabled     = bool(r.get("actif",             defaults.retrain_enabled)),
            fine_tune_epochs    = int(r.get("epochs",             defaults.fine_tune_epochs)),
            fine_tune_lr        = float(r.get("taux_apprentissage", defaults.fine_tune_lr)),
            checkpoint_dir      = r.get("dossier_checkpoints",    defaults.checkpoint_dir),
            retrain_state_file  = r.get("fichier_etat",           defaults.retrain_state_file),
        )
        instance._validate()
        return instance

    def _validate(self) -> None:
        """Catch configuration mistakes early, before any model loading."""
        errors: list[str] = []

        if not self.value_cols:
            errors.append("detection.colonnes ne peut pas être vide")
        if self.context_length <= 0:
            errors.append("historique_heures doit être > 0")
        if self.prediction_length <= 0:
            errors.append("prediction_heures doit être > 0")
        # On a besoin de plus d'historique que de prédiction : Chronos apprend le pattern
        # sur le contexte pour prédire les N prochaines heures — si contexte ≤ prédiction,
        # le modèle n'a pas assez d'information pour être fiable
        if self.context_length <= self.prediction_length:
            errors.append(
                f"historique_heures ({self.context_length}) doit être "
                f"> prediction_heures ({self.prediction_length})"
            )
        if not (0 < self.q_low < self.q_high < 1):
            errors.append(
                f"percentile_bas ({self.q_low}) doit être < percentile_haut ({self.q_high}) "
                f"et tous les deux dans ]0, 1["
            )
        if self.k_sigma <= 0:
            errors.append("k_sigma doit être > 0")
        if self.forecast_horizon <= 0:
            errors.append("prevision.horizon_heures doit être > 0")
        if not (0.0 <= self.min_confidence <= 1.0):
            errors.append(
                f"prevision.confiance_min ({self.min_confidence}) doit être dans [0, 1]"
            )

        if errors:
            raise ValueError(
                "Erreurs dans config.yaml :\n" + "\n".join(f"  • {e}" for e in errors)
            )
