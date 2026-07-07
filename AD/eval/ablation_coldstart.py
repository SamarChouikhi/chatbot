"""
Ablation Study — ColdStart : Ensemble vs. Algorithmes Individuels

Implémentation standalone (n'importe pas le code production) pour garantir
une mesure indépendante et reproductible.

Protocole :
  - 5 seeds aléatoires pour estimer la variance des métriques
  - 720 points horaires (30 jours) avec 5 % d'anomalies injectées à des
    positions connues (ground truth binaire)
  - Anomalies de type "pic positif" (surproduction/défaut) uniquement :
    valeurs réalistes pour des données énergie BMS où E ≥ 0 toujours
  - Isolation Forest : contamination=0.10 (valeur standard — ne révèle pas
    le vrai taux pour éviter d'avantager artificiellement l'algorithme)
  - Métriques : Précision, Rappel, F1, AUC-ROC

Usage (depuis le répertoire AD/) :
    python eval/ablation_coldstart.py
    python eval/ablation_coldstart.py --seeds 10 --anomaly-rate 0.03
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import (
        f1_score, precision_score, recall_score, roc_auc_score,
    )
except ImportError:
    sys.exit("scikit-learn requis : pip install scikit-learn")

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas requis : pip install pandas")


# ── Génération de données synthétiques avec labels connus ─────────────────────

class SyntheticDataset:
    def __init__(self, values: np.ndarray, labels: np.ndarray, timestamps: pd.DatetimeIndex):
        self.values     = values
        self.labels     = labels
        self.timestamps = timestamps


def generate_dataset(
    n_hours:      int   = 720,
    anomaly_rate: float = 0.05,
    pop_mean:     float = 52.3,
    pop_std:      float = 18.7,
    seed:         int   = 42,
) -> SyntheticDataset:
    """
    Génère un signal énergie réaliste (saisonnalité journalière + hebdomadaire + bruit)
    et injecte des anomalies positives (pics 4–8σ) à des positions aléatoires.

    Uniquement des anomalies en direction positive (surproduction/défaut équipement)
    pour respecter la contrainte domaine E ≥ 0 kWh et garantir la détectabilité
    des seuils statistiques sans biais de clipping.
    """
    rng = np.random.default_rng(seed)
    ts  = pd.date_range("2025-01-01", periods=n_hours, freq="1h")

    hours = ts.hour.to_numpy(dtype=float)
    dows  = ts.dayofweek.to_numpy(dtype=float)
    daily   = np.sin(2 * np.pi * hours / 24) * 10.0
    weekly  = np.sin(2 * np.pi * dows  /  7) *  5.0
    noise   = rng.normal(0, pop_std * 0.25, n_hours)
    signal  = pop_mean + daily + weekly + noise
    signal  = np.clip(signal, 0.0, pop_mean + 4 * pop_std)

    n_anom   = max(1, int(n_hours * anomaly_rate))
    anom_idx = rng.choice(n_hours, size=n_anom, replace=False)
    labels   = np.zeros(n_hours, dtype=bool)
    labels[anom_idx] = True

    for idx in anom_idx:
        # Anomalies positives uniquement (pics de consommation anormaux).
        # Les anomalies négatives (dropout compteur → 0 kWh) seraient à z=-2.8
        # avec μ=52.3, σ=18.7, soit sous le seuil 3σ et non comparables entre
        # algorithmes — elles constituent un cas d'usage séparé.
        magnitude = rng.uniform(4.0, 8.0) * pop_std
        signal[idx] = min(signal[idx] + magnitude, pop_mean + 10 * pop_std)

    return SyntheticDataset(values=signal, labels=labels, timestamps=ts)


# ── Algorithmes individuels ───────────────────────────────────────────────────

def detect_zscore(
    values: np.ndarray,
    mu: float,
    sigma: float,
    threshold: float = 3.0,
) -> tuple[np.ndarray, np.ndarray]:
    z       = (values - mu) / max(sigma, 1e-9)
    is_anom = np.abs(z) > threshold
    score   = np.clip(np.abs(z) / threshold, 0.0, 10.0)
    return is_anom, score


def detect_iqr(
    values: np.ndarray,
    q25:    float,
    q75:    float,
    k:      float = 1.5,
) -> tuple[np.ndarray, np.ndarray]:
    iqr     = q75 - q25
    upper   = q75 + k * iqr
    lower   = q25 - k * iqr
    is_anom = (values < lower) | (values > upper)
    beyond  = np.maximum(values - upper, 0.0) + np.maximum(lower - values, 0.0)
    score   = np.clip(beyond / max(k * iqr, 1e-9), 0.0, 10.0)
    return is_anom, score


def detect_isolation_forest(
    values:     np.ndarray,
    timestamps: pd.DatetimeIndex,
    seed:       int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Isolation Forest sur 5 features : valeur + encodage sin/cos horaire et hebdo.
    contamination=0.10 (valeur standard sklearn — volontairement différent du vrai
    taux d'anomalies pour un test équitable sans connaissance a priori du taux réel).
    """
    hours    = timestamps.hour.to_numpy(dtype=float)
    dows     = timestamps.dayofweek.to_numpy(dtype=float)
    features = np.column_stack([
        values,
        np.sin(2 * np.pi * hours / 24), np.cos(2 * np.pi * hours / 24),
        np.sin(2 * np.pi * dows  /  7), np.cos(2 * np.pi * dows  /  7),
    ])
    clf       = IsolationForest(n_estimators=100, contamination=0.10,
                                random_state=seed, n_jobs=-1)
    clf.fit(features)
    preds      = clf.predict(features)
    raw_scores = clf.decision_function(features)
    is_anom    = preds == -1
    neg        = -raw_scores
    score      = np.clip(neg / max(float(neg.max()), 1e-9) * 10.0, 0.0, 10.0)
    return is_anom, score


def detect_ensemble(
    results:   list[tuple[np.ndarray, np.ndarray]],
    min_votes: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    vote_matrix  = np.column_stack([r[0].astype(int) for r in results])
    votes        = vote_matrix.sum(axis=1)
    is_anom      = votes >= min_votes
    score_matrix = np.column_stack([r[1] for r in results])
    score        = np.where(is_anom, score_matrix.max(axis=1), 0.0)
    return is_anom, score


# ── Métriques ─────────────────────────────────────────────────────────────────

def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    scores: np.ndarray,
) -> dict[str, float]:
    p   = float(precision_score(y_true, y_pred, zero_division=0))
    r   = float(recall_score(y_true, y_pred, zero_division=0))
    f1  = float(f1_score(y_true, y_pred, zero_division=0))
    try:
        auc = float(roc_auc_score(y_true, scores))
    except Exception:
        auc = 0.0
    return {"precision": p, "recall": r, "f1": f1, "auc_roc": auc}


# ── Runner ────────────────────────────────────────────────────────────────────

def run_ablation(n_seeds: int = 5, anomaly_rate: float = 0.05) -> None:
    POP_MEAN = 52.3
    POP_STD  = 18.7
    POP_Q25  = 38.1
    POP_Q75  = 65.4

    algo_names = [
        "Z-Score (seul)",
        "IQR (seul)",
        "Isolation Forest (seul)",
        "Ensemble (vote ≥ 2/3)",
    ]
    algo_runs: dict[str, list[dict]] = {name: [] for name in algo_names}

    for seed in range(42, 42 + n_seeds):
        ds = generate_dataset(
            n_hours=720, anomaly_rate=anomaly_rate,
            pop_mean=POP_MEAN, pop_std=POP_STD, seed=seed,
        )

        r_z   = detect_zscore(ds.values, POP_MEAN, POP_STD, threshold=3.0)
        r_iqr = detect_iqr(ds.values, POP_Q25, POP_Q75, k=1.5)
        r_if  = detect_isolation_forest(ds.values, ds.timestamps, seed=seed)
        r_ens = detect_ensemble([r_z, r_iqr, r_if], min_votes=2)

        for name, result in zip(algo_names, [r_z, r_iqr, r_if, r_ens]):
            algo_runs[name].append(compute_metrics(ds.labels, result[0], result[1]))

    # ── Calcul des moyennes/std ───────────────────────────────────────────────
    avgs = {
        name: {k: float(np.mean([r[k] for r in runs])) for k in runs[0]}
        for name, runs in algo_runs.items()
    }
    stds = {
        name: {k: float(np.std([r[k] for r in runs])) for k in runs[0]}
        for name, runs in algo_runs.items()
    }

    best_f1   = max(v["f1"] for v in avgs.values())
    best_name = max(avgs, key=lambda n: avgs[n]["f1"])

    # ── Affichage ─────────────────────────────────────────────────────────────
    W = 72
    print()
    print("=" * W)
    print("ARIA — Ablation Study : ColdStart Ensemble vs. Algorithmes Individuels")
    print("=" * W)
    print(f"  Profil : μ={POP_MEAN} kWh | σ={POP_STD} | Q25={POP_Q25} | Q75={POP_Q75}")
    print(f"  Dataset : 720 h (30 j) × {n_seeds} seeds | taux anomalies = {anomaly_rate*100:.0f}%")
    print(f"  Anomalies : pics positifs 4–8σ (ground truth exact) | IF contamination=0.10")
    print()
    print(f"  {'Algorithme':<30} {'Précision':>10} {'Rappel':>8} {'F1':>8} {'AUC-ROC':>9}")
    print("  " + "-" * 68)

    for name in algo_names:
        avg    = avgs[name]
        std    = stds[name]
        marker = " ✓" if abs(avg["f1"] - best_f1) < 1e-6 else "  "
        print(
            f"  {name + marker:<32} "
            f"{avg['precision']:>8.3f}   "
            f"{avg['recall']:>6.3f}   "
            f"{avg['f1']:>6.3f}   "
            f"{avg['auc_roc']:>7.3f}"
        )
        print(
            f"  {'(±std)':>32} "
            f"{std['precision']:>8.3f}   "
            f"{std['recall']:>6.3f}   "
            f"{std['f1']:>6.3f}   "
            f"{std['auc_roc']:>7.3f}"
        )

    # ── Observations dynamiques basées sur les résultats réels ───────────────
    ens = avgs["Ensemble (vote ≥ 2/3)"]
    z   = avgs["Z-Score (seul)"]
    iqr = avgs["IQR (seul)"]
    ifo = avgs["Isolation Forest (seul)"]

    print()
    print("  Observations (issues des résultats ci-dessus) :")

    if ens["precision"] >= max(z["precision"], iqr["precision"], ifo["precision"]) - 0.01:
        print("  • L'ensemble maintient une précision maximale (pas de faux positifs)")
        print("    par vote majoritaire : seuls les points approuvés par ≥ 2/3 algos sont signalés.")

    if ens["recall"] >= z["recall"] - 0.02 and ens["recall"] >= iqr["recall"] - 0.02:
        print("  • Le rappel de l'ensemble est comparable ou supérieur aux algos individuels.")
    else:
        worst_recall = min(z["recall"], iqr["recall"])
        if ens["recall"] < ifo["recall"] - 0.05:
            print(f"  • Le rappel ensemble ({ens['recall']:.3f}) est inférieur à IF ({ifo['recall']:.3f})")
            print("    car le vote ≥ 2/3 filtre les détections que seul IF identifie")
            print("    (pics à fort contexte temporel non capturés par Z-Score/IQR).")
            print(f"  • Sur des anomalies de type 'pic positif pur', {best_name} est le plus performant.")
            print("    L'ensemble est à privilégier lorsque les types d'anomalies sont diversifiés")
            print("    (voir detection_metrics.py pour la comparaison multi-type).")

    print(f"  • Résultats moyennés sur {n_seeds} seeds — écart-type indiqué en (±std).")
    print("=" * W)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds",        type=int,   default=5,    help="Nombre de seeds (défaut: 5)")
    p.add_argument("--anomaly-rate", type=float, default=0.05, help="Taux anomalies (défaut: 0.05)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_ablation(n_seeds=args.seeds, anomaly_rate=args.anomaly_rate)
