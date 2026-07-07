from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import EnergyConfig

# Regex pour détecter les suffixes de phase en fin de nom de colonne (ex: cons_en_L1, cons_en_L2)
_PHASE_RE    = re.compile(r'_(L\d+)$')
# On garde seulement L1/L2/L3 — L4/L5/L6 sont des circuits auxiliaires inactifs (valeurs à zéro)
_KEEP_PHASES = frozenset(('L1', 'L2', 'L3'))


# ── Format detection ──────────────────────────────────────────────────────────

def _is_wide_format(df: pd.DataFrame, phase_col: str) -> bool:
    """Wide = phases encoded as column suffixes (_L1/_L2/_L3), not as a 'phase' column."""
    return phase_col not in df.columns


# ── Wide → long pivot ─────────────────────────────────────────────────────────

def _wide_to_long(df_wide: pd.DataFrame, config: EnergyConfig) -> pd.DataFrame:
    """
    Pivots wide-format rows (one row per device/date, phases as column suffixes)
    into long format (one row per device/phase/date).

    Example:
        cons_en_L1, cons_en_L2, cons_en_L3
        → phase='L1', cons_en=…  |  phase='L2', cons_en=…  |  phase='L3', cons_en=…

    L4/L5/L6 are ignored — they are inactive auxiliary circuits with zero values.
    Non-phase columns (id_device, date, battery_level, degres) are carried on every row.
    """
    # Fixed columns present on every row regardless of phase
    fixed_cols = [col for col in df_wide.columns if not _PHASE_RE.search(col)]

    # Active phases present in the data (L1/L2/L3 only)
    phases = sorted({
        m.group(1)
        for col in df_wide.columns
        if (m := _PHASE_RE.search(col)) and m.group(1) in _KEEP_PHASES
    })

    chunks: list[pd.DataFrame] = []
    for phase in phases:
        suffix = f'_{phase}'
        rename_map = {
            col: col[: -len(suffix)]
            for col in df_wide.columns
            if col.endswith(suffix)
        }
        sub = df_wide[fixed_cols + list(rename_map)].copy()
        sub = sub.rename(columns=rename_map)
        sub[config.phase_col] = phase
        chunks.append(sub)

    result = pd.concat(chunks, ignore_index=True)
    result = result.sort_values(
        [config.device_col, config.phase_col, config.timestamp_col]
    ).reset_index(drop=True)
    result[config.item_col] = (
        result[config.device_col].astype(str) + '_' + result[config.phase_col]
    )
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def load_energy_data(config: EnergyConfig) -> pd.DataFrame:
    from common.logger import get_logger
    _log = get_logger(__name__)

    df = pd.read_csv(config.data_path, parse_dates=[config.timestamp_col])

    # Sanitisation : timestamps au-delà de aujourd'hui+30j sont des données corrompues
    # (ex: ibis_53_1206.csv contient des dates jusqu'en 2179)
    horizon = pd.Timestamp.now() + pd.Timedelta(days=30)
    future_mask = df[config.timestamp_col] > horizon
    if future_mask.any():
        _log.warning(
            "%d ligne(s) avec timestamp corrompu (> %s) supprimées — "
            "plage corrompue : %s → %s",
            future_mask.sum(),
            horizon.date(),
            df.loc[future_mask, config.timestamp_col].min(),
            df.loc[future_mask, config.timestamp_col].max(),
        )
        df = df[~future_mask].copy()

    # Filtre optionnel par plage de dates — si non défini dans config.yaml, on prend tout
    if config.date_debut:
        df = df[df[config.timestamp_col] >= pd.Timestamp(config.date_debut)]
    if config.date_fin:
        # On inclut la journée entière du date_fin (jusqu'à 23:59:59)
        df = df[
            df[config.timestamp_col]
            <= pd.Timestamp(config.date_fin) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        ]

    # Le CSV peut arriver en format "wide" (une colonne par phase) ou "long" (une ligne par phase)
    # selon la version de l'export de la plateforme IOIT
    if _is_wide_format(df, config.phase_col):
        df = _wide_to_long(df, config)
    else:
        # Format long déjà correct (energy_by_phase.csv legacy) — on ajoute juste item_id
        df = df.sort_values(
            [config.device_col, config.phase_col, config.timestamp_col]
        ).reset_index(drop=True)
        df[config.item_col] = (
            df[config.device_col].astype(str) + '_' + df[config.phase_col]
        )

    return df


def clean_energy_data(df: pd.DataFrame, config: EnergyConfig) -> pd.DataFrame:
    df = df.copy()

    # Le capteur THD envoie -99 quand il est inactif (valeur sentinelle, pas une vraie mesure)
    # On remplace par NaN puis on interpole linéairement sur max ffill_limit heures consécutives
    # Au-delà de ffill_limit heures de trou, le NaN reste → ces points seront dropés plus bas
    thd_cols = [c for c in df.columns if 'THD' in c]
    for col in thd_cols:
        df[col] = df[col].replace(-99, np.nan)
        df[col] = df.groupby(config.item_col)[col].transform(
            lambda x: x.interpolate(method='linear', limit=config.ffill_limit)
        )

    # On marque les heures où cons_en == 0 comme "offline" sans les supprimer :
    # zéro = appareil éteint, c'est une information utile pour le détecteur (pas une anomalie)
    df['is_offline'] = df[config.value_col] == 0
    df = df.dropna(subset=[config.value_col])
    return df


def resample_energy(df: pd.DataFrame, config: EnergyConfig) -> pd.DataFrame:
    # Chronos exige une grille temporelle régulière (1 point par heure sans trous)
    # On resamples par device_phase séparément pour éviter de mélanger les séries
    cols_to_resample = [c for c in config.value_cols if c in df.columns]
    resampled = []
    for item_id, group in df.groupby(config.item_col):
        g = group.set_index(config.timestamp_col)[cols_to_resample].copy()
        g = (
            g.resample(config.resample_freq)
            .mean()                          # plusieurs mesures dans la même heure → moyenne
            .ffill(limit=config.ffill_limit) # petits trous (≤ ffill_limit heures) → forward fill
            .reset_index()
        )
        # On réattache item_id, device et phase (perdus lors du resample sur l'index)
        g[config.item_col] = item_id
        parts = str(item_id).rsplit('_', 1)
        g[config.device_col] = parts[0]
        g[config.phase_col]  = parts[1] if len(parts) > 1 else ''
        resampled.append(g)
    return pd.concat(resampled, ignore_index=True)
