"""
Contrôles de plausibilité des mesures avant écriture dans les tables daily_*.

Certains compteurs d'énergie remontent ponctuellement leur index cumulé
(~1e8–1e9) à la place de la consommation de l'intervalle (~1e5). Une seule
lecture de ce type fausse les totaux journaliers, les baselines et les
économies estimées par le moteur de recommandations.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger('aria.pipeline.data_quality')

# Une lecture supérieure à SPIKE_FACTOR × la médiane de sa série est rejetée.
# Sur l'historique réel, les lectures valides restent sous ~4× la médiane (P99)
# et les index cumulés injectés dépassent 50× : 20 laisse une marge des deux côtés.
SPIKE_FACTOR = 20.0

# En dessous de ce nombre de lectures positives, la médiane n'est pas assez fiable
# pour juger une valeur : la série est laissée intacte.
MIN_SAMPLES = 12


def spike_mask(
    df: pd.DataFrame,
    value_col: str,
    group_cols: list[str],
    factor: float = SPIKE_FACTOR,
    min_samples: int = MIN_SAMPLES,
) -> pd.Series:
    """Retourne un masque booléen (aligné sur df.index) des lectures aberrantes.

    La référence est la médiane des valeurs strictement positives de chaque série
    (les zéros correspondent à des périodes d'arrêt et écraseraient la médiane).
    """
    if df.empty:
        return pd.Series(False, index=df.index)

    values = pd.to_numeric(df[value_col], errors='coerce')
    positive = values.where(values > 0)
    grouped = positive.groupby([df[c] for c in group_cols])
    median = grouped.transform('median')
    count = grouped.transform('count')

    return (count >= min_samples) & (values > factor * median)


def drop_counter_spikes(
    df: pd.DataFrame,
    value_col: str,
    group_cols: list[str],
    factor: float = SPIKE_FACTOR,
    min_samples: int = MIN_SAMPLES,
) -> pd.DataFrame:
    """Retire les lectures aberrantes (index cumulé pris pour une consommation)."""
    mask = spike_mask(df, value_col, group_cols, factor, min_samples)
    n = int(mask.sum())
    if n:
        sample = df.loc[mask, group_cols + [value_col]].head(5).to_dict('records')
        logger.warning(
            "data_quality: %d lecture(s) aberrante(s) rejetée(s) sur %s (> %.0f× médiane) — ex: %s",
            n, value_col, factor, sample,
        )
    return df.loc[~mask]
