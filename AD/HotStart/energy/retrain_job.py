"""
Job B — Retraining mensuel Chronos (energy).

Exécution indépendante du pipeline de détection.
À déclencher une fois par mois quand de nouvelles données arrivent.

Usage :
    python main.py --domain energy --retrain-only
    python main.py --domain energy --retrain        # retrain puis détection
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Union

from common.logger import get_logger
from common.monthly_retrainer import MonthlyRetrainer
from .config import EnergyConfig
from .detector import EnergyAnomalyDetector
from .preprocessor import clean_energy_data, load_energy_data, resample_energy

_log = get_logger(__name__)


def run_retrain(
    config: Union[EnergyConfig, str, Path, None] = None,
) -> dict[str, int]:
    """
    Job B — Fine-tuning mensuel par device jusqu'à M12.

    Charge les données, identifie les devices avec un nouveau mois,
    lance le fine-tuning Chronos et sauvegarde les checkpoints.

    Retourne : {device_id: months_accumulated} pour chaque device retraîné.
    """
    if config is None:
        config = EnergyConfig.from_file()
    elif isinstance(config, (str, Path)):
        config = EnergyConfig.from_yaml(config)
    else:
        config._validate()

    _log.info("═" * 55)
    _log.info("ARIA — Job B : Retraining mensuel (energy)")
    _log.info("Fichier     : %s", config.data_path)
    _log.info("Checkpoints : %s", config.checkpoint_dir)
    _log.info("État        : %s", config.retrain_state_file)
    _log.info("═" * 55)

    if not config.retrain_enabled:
        _log.info("Retraining désactivé (retrain_enabled=False) — job ignoré")
        return {}

    os.makedirs(config.output_dir, exist_ok=True)
    t_start = time.perf_counter()

    # ── Chargement & nettoyage données ────────────────────────────────────
    _log.info("Chargement des données...")
    df = load_energy_data(config)
    df = clean_energy_data(df, config)
    df = resample_energy(df, config)
    _log.info(
        "%d lignes | %d devices : %s",
        len(df), df[config.device_col].nunique(),
        sorted(df[config.device_col].unique()),
    )

    # ── Chargement modèle Chronos ─────────────────────────────────────────
    _log.info("Chargement du modèle Chronos...")
    detector = EnergyAnomalyDetector(config)
    detector._load_pipeline()

    # ── Retraining per device ─────────────────────────────────────────────
    retrainer = MonthlyRetrainer(config)
    retrained:    dict[str, int] = {}
    skipped_same: list[str]      = []
    skipped_mature: list[str]    = []

    for device_id in sorted(df[config.device_col].unique()):
        dev_str   = str(device_id)
        device_df = df[df[config.device_col] == device_id]

        if retrainer.is_mature(dev_str):
            skipped_mature.append(dev_str)
            continue

        if retrainer.should_retrain(dev_str, device_df):
            retrainer.retrain(dev_str, device_df, detector._pipeline)
            retrained[dev_str] = retrainer.months_accumulated(dev_str)
        else:
            skipped_same.append(dev_str)

    # ── Rapport final ─────────────────────────────────────────────────────
    duration = time.perf_counter() - t_start
    _log.info("─" * 55)
    _log.info("Job B terminé en %.1f s", duration)

    if retrained:
        _log.info(
            "  Retraînés  : %d device(s) — %s",
            len(retrained),
            {k: f"M{v}" for k, v in retrained.items()},
        )
    else:
        _log.info("  Retraînés  : aucun nouveau mois détecté")

    if skipped_mature:
        _log.info("  Matures    : %d device(s) — %s", len(skipped_mature), skipped_mature)
    if skipped_same:
        _log.info("  Inchangés  : %d device(s) — %s", len(skipped_same), skipped_same)

    _log.info("─" * 55)

    # ── Libération GPU ────────────────────────────────────────────────────
    try:
        import gc
        import torch
        detector._pipeline = None
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
        gc.collect()
    except Exception:
        pass

    return retrained
