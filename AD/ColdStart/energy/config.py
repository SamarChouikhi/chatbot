from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Union

_DEFAULT_YAML = Path(__file__).parent / "config.yaml"


class ColdStartAlgorithm(str, Enum):
    ZSCORE           = "zscore"
    IQR              = "iqr"
    ISOLATION_FOREST = "isolation_forest"
    CHRONOS          = "chronos"
    ENSEMBLE         = "ensemble"


@dataclass
class ColdStartConfig:
    # ── I/O ───────────────────────────────────────────────────────────────
    new_device_data_path: str        = ""
    population_data_path: str        = "energy.csv"
    output_dir:           str        = "outputs/coldstart"

    # ── Date filter ───────────────────────────────────────────────────────
    date_debut: str | None = None
    date_fin:   str | None = None

    # ── New device identity ────────────────────────────────────────────────
    new_device_id: str       = "NEW_DEVICE_001"
    new_device_phases: list[str] = field(default_factory=lambda: ["L1", "L2", "L3"])

    # ── Column names (mirror HotStart) ────────────────────────────────────
    timestamp_col: str       = "date"
    value_cols:    list[str] = field(default_factory=lambda: ["cons_en"])
    item_col:      str       = "item_id"
    device_col:    str       = "id_device"
    phase_col:     str       = "phase"

    # ── Algorithms ────────────────────────────────────────────────────────
    algorithm:             ColdStartAlgorithm = ColdStartAlgorithm.ENSEMBLE
    min_votes:             int                = 2

    # Z-Score
    zscore_threshold:      float = 3.0

    # IQR
    iqr_multiplier:        float = 1.5

    # Isolation Forest
    if_contamination:      float = 0.05
    if_n_estimators:       int   = 100
    if_max_samples:        int   = 256

    # Chronos zero-shot
    chronos_model:             str   = "autogluon/chronos-t5-tiny"
    chronos_device:            str   = "cpu"
    chronos_context_length:    int   = 48
    chronos_prediction_length: int   = 12
    chronos_num_samples:       int   = 20
    chronos_q_low:             float = 0.1
    chronos_q_high:            float = 0.9
    chronos_k_sigma:           float = 1.5
    use_chronos_in_ensemble:   bool  = True

    # ── Population profile ────────────────────────────────────────────────
    profile_min_devices:   int       = 2
    profile_excluded_cols: list[str] = field(
        default_factory=lambda: ["item_id", "id_device", "phase", "date"]
    )

    # ── Synthetic generation ──────────────────────────────────────────────
    synthetic_days:                  int   = 30
    synthetic_seed:                  int | None = 42
    synthetic_noise_factor:          float = 0.8
    synthetic_anomaly_rate:          float = 0.03

    # ── Progressive warmup ────────────────────────────────────────────────
    warmup_hours:          int   = 168

    # ── Resampling ────────────────────────────────────────────────────────
    resample_freq:         str   = "1h"
    ffill_limit:           int   = 3

    # ── Regime change ─────────────────────────────────────────────────────
    regime_change_hours:   int   = 24

    # ── Derived ───────────────────────────────────────────────────────────

    @property
    def value_col(self) -> str:
        return self.value_cols[0]

    # ── Loaders ───────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls) -> "ColdStartConfig":
        return cls.from_yaml(_DEFAULT_YAML)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "ColdStartConfig":
        import yaml

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {path}\n"
                f"Expected location: ColdStart/energy/config.yaml"
            )

        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        defaults = cls()

        d   = raw.get("donnees",        {})
        nd  = raw.get("nouveau_device", {})
        col = raw.get("colonnes",       {})
        alg = raw.get("algorithmes",    {})
        prf = raw.get("profil",         {})
        syn = raw.get("synthese",       {})
        wup = raw.get("warmup",         {})
        adv = raw.get("avance",         {})

        try:
            algorithm = ColdStartAlgorithm(
                alg.get("mode", defaults.algorithm.value)
            )
        except ValueError as exc:
            valid = [e.value for e in ColdStartAlgorithm]
            raise ValueError(
                f"Mode invalide dans config.yaml: "
                f"{alg.get('mode')!r}. Valeurs valides : {valid}"
            ) from exc

        value_cols = col.get("valeur", defaults.value_cols)
        if isinstance(value_cols, str):
            value_cols = [value_cols]

        phases = nd.get("phases", defaults.new_device_phases)
        if isinstance(phases, str):
            phases = [phases]

        excluded = prf.get("colonnes_exclues", defaults.profile_excluded_cols)

        zscore_cfg  = alg.get("zscore",            {})
        iqr_cfg     = alg.get("iqr",               {})
        if_cfg      = alg.get("isolation_forest",  {})
        chronos_cfg = raw.get("chronos",           {})

        seed_raw = syn.get("graine", defaults.synthetic_seed)
        seed: int | None = None if seed_raw is None else int(seed_raw)

        instance = cls(
            new_device_data_path      = d.get("fichier_nouveau_device", defaults.new_device_data_path),
            population_data_path      = d.get("fichier_population",     defaults.population_data_path),
            output_dir                = d.get("dossier_resultats",      defaults.output_dir),
            date_debut                = d.get("date_debut",             defaults.date_debut),
            date_fin                  = d.get("date_fin",               defaults.date_fin),
            new_device_id             = nd.get("id",     defaults.new_device_id),
            new_device_phases         = phases,
            timestamp_col             = col.get("timestamp", defaults.timestamp_col),
            value_cols                = value_cols,
            item_col                  = col.get("item_id",   defaults.item_col),
            device_col                = col.get("device",    defaults.device_col),
            phase_col                 = col.get("phase",     defaults.phase_col),
            algorithm                 = algorithm,
            min_votes                 = int(alg.get("min_votes_anomalie",       defaults.min_votes)),
            zscore_threshold          = float(zscore_cfg.get("seuil",           defaults.zscore_threshold)),
            iqr_multiplier            = float(iqr_cfg.get("multiplicateur",     defaults.iqr_multiplier)),
            if_contamination          = float(if_cfg.get("contamination",       defaults.if_contamination)),
            if_n_estimators           = int(if_cfg.get("n_estimateurs",         defaults.if_n_estimators)),
            if_max_samples            = int(if_cfg.get("max_samples",           defaults.if_max_samples)),
            chronos_model             = chronos_cfg.get("modele",               defaults.chronos_model),
            chronos_device            = chronos_cfg.get("accelerateur",         defaults.chronos_device),
            chronos_context_length    = int(chronos_cfg.get("contexte",         defaults.chronos_context_length)),
            chronos_prediction_length = int(chronos_cfg.get("horizon",          defaults.chronos_prediction_length)),
            chronos_num_samples       = int(chronos_cfg.get("num_samples",      defaults.chronos_num_samples)),
            chronos_q_low             = float(chronos_cfg.get("q_bas",          defaults.chronos_q_low)),
            chronos_q_high            = float(chronos_cfg.get("q_haut",         defaults.chronos_q_high)),
            chronos_k_sigma           = float(chronos_cfg.get("k_sigma",        defaults.chronos_k_sigma)),
            use_chronos_in_ensemble   = bool(chronos_cfg.get("actif",           defaults.use_chronos_in_ensemble)),
            profile_min_devices       = int(prf.get("min_devices",              defaults.profile_min_devices)),
            profile_excluded_cols     = excluded,
            synthetic_days            = int(syn.get("jours",                    defaults.synthetic_days)),
            synthetic_seed            = seed,
            synthetic_noise_factor    = float(syn.get("facteur_bruit",          defaults.synthetic_noise_factor)),
            synthetic_anomaly_rate    = float(syn.get("taux_anomalies_synthetiques", defaults.synthetic_anomaly_rate)),
            warmup_hours              = int(wup.get("heures",                   defaults.warmup_hours)),
            resample_freq             = adv.get("frequence",                    defaults.resample_freq),
            ffill_limit               = int(adv.get("limite_completion",        defaults.ffill_limit)),
            regime_change_hours       = int(adv.get("seuil_regime_heures",      defaults.regime_change_hours)),
        )
        instance._validate()
        return instance

    def _validate(self) -> None:
        errors: list[str] = []

        if not self.value_cols:
            errors.append("colonnes.valeur ne peut pas être vide")
        if self.synthetic_days <= 0:
            errors.append("synthese.jours doit être > 0")
        if not (0.0 < self.if_contamination < 0.5):
            errors.append(f"isolation_forest.contamination ({self.if_contamination}) doit être dans ]0, 0.5[")
        if not (0.0 <= self.synthetic_anomaly_rate < 1.0):
            errors.append(f"synthese.taux_anomalies_synthetiques ({self.synthetic_anomaly_rate}) doit être dans [0, 1[")
        if self.warmup_hours <= 0:
            errors.append("warmup.heures doit être > 0")
        if self.zscore_threshold <= 0:
            errors.append("zscore.seuil doit être > 0")
        if self.iqr_multiplier <= 0:
            errors.append("iqr.multiplicateur doit être > 0")
        if self.min_votes < 1:
            errors.append("algorithmes.min_votes_anomalie doit être >= 1")

        if errors:
            raise ValueError(
                "Erreurs dans config.yaml :\n" + "\n".join(f"  • {e}" for e in errors)
            )
