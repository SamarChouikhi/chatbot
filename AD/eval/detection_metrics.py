"""
Évaluation quantitative de la détection d'anomalies ARIA — ColdStart Pipeline

Génère des données synthétiques avec ground truth binaire et évalue les 3 types
d'anomalies rencontrés en BMS énergie :
  1. Point       — pic isolé positif (4–8σ, surconsommation soudaine)
  2. Contextual  — consommation anormalement haute hors plage horaire habituelle
  3. Collective  — plateau élevé sur 3–6 h consécutives (défaut durable)

Métriques produites :
  - Précision, Rappel, F1-score (global + par type d'anomalie)
  - AUC-ROC (score continu) pour chaque algorithme et l'ensemble
  - Délai de détection moyen (en heures) pour les anomalies détectées

Isolation Forest : contamination=0.10 (non calqué sur le vrai taux → test équitable).

Usage (depuis le répertoire AD/) :
    python eval/detection_metrics.py
    python eval/detection_metrics.py --n-devices 5 --seeds 3
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

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


ANOMALY_TYPES = ("point", "contextual", "collective")


# ── Générateur multi-type ─────────────────────────────────────────────────────

@dataclass
class LabeledDataset:
    values:     np.ndarray
    labels:     np.ndarray          # bool
    anom_type:  np.ndarray          # str ("point" | "contextual" | "collective" | "")
    timestamps: pd.DatetimeIndex


def generate_multianomaly_dataset(
    n_hours:      int   = 720,
    anomaly_rate: float = 0.05,
    pop_mean:     float = 52.3,
    pop_std:      float = 18.7,
    seed:         int   = 42,
) -> LabeledDataset:
    """
    Signal BMS réaliste avec 3 familles d'anomalies en proportions égales.

    Point (1/3)      : pic positif isolé 4–8σ
    Contextual (1/3) : surconsom. nocturne (00h–05h) hors pattern journalier normal
    Collective (1/3) : plateau élevé sur 3–6 h consécutives (défaut durable)
    """
    rng = np.random.default_rng(seed)
    ts  = pd.date_range("2025-01-01", periods=n_hours, freq="1h")

    hours  = ts.hour.to_numpy(dtype=float)
    dows   = ts.dayofweek.to_numpy(dtype=float)
    daily  = np.sin(2 * np.pi * hours / 24) * 12.0
    weekly = np.sin(2 * np.pi * dows  /  7) *  5.0
    noise  = rng.normal(0, pop_std * 0.2, n_hours)
    signal = pop_mean + daily + weekly + noise
    signal = np.clip(signal, 0.0, pop_mean + 4 * pop_std)

    # anomaly_rate=0 → série propre (sert de contexte d'amorçage à Chronos)
    if anomaly_rate <= 0:
        return LabeledDataset(values=signal, labels=np.zeros(n_hours, dtype=bool),
                              anom_type=np.full(n_hours, "", dtype=object), timestamps=ts)

    n_total = max(3, int(n_hours * anomaly_rate))
    n_each  = max(1, n_total // 3)

    labels    = np.zeros(n_hours, dtype=bool)
    anom_type = np.full(n_hours, "", dtype=object)
    used: set[int] = set()

    def _pick(pool: list[int], n: int) -> list[int]:
        available = [i for i in pool if i not in used]
        chosen    = rng.choice(available, size=min(n, len(available)), replace=False).tolist()
        used.update(chosen)
        return chosen

    all_idx = list(range(n_hours))

    # 1. Point anomalies — pics positifs
    for idx in _pick(all_idx, n_each):
        magnitude   = rng.uniform(4.0, 8.0) * pop_std
        signal[idx] = min(signal[idx] + magnitude, pop_mean + 10 * pop_std)
        labels[idx] = True
        anom_type[idx] = "point"

    # 2. Contextual — haute consommation nocturne (00h–05h)
    night_idx = [i for i in range(n_hours) if ts[i].hour <= 5]
    for idx in _pick(night_idx, n_each):
        # Valeur haute mais plausible en journée → anormale la nuit
        signal[idx] = pop_mean + pop_std * rng.uniform(2.5, 4.5)
        labels[idx] = True
        anom_type[idx] = "contextual"

    # 3. Collective — plateau élevé sur 3–6 h consécutives
    collective_count = 0
    attempts = 0
    while collective_count < n_each and attempts < 300:
        attempts += 1
        start  = int(rng.integers(1, n_hours - 7))
        length = int(rng.integers(3, 7))
        span   = list(range(start, min(start + length, n_hours)))
        if any(i in used for i in span):
            continue
        plateau = pop_mean + pop_std * rng.uniform(2.0, 3.5)
        for i in span:
            signal[i] = plateau + rng.normal(0, pop_std * 0.05)
            labels[i] = True
            anom_type[i] = "collective"
            used.add(i)
        collective_count += 1

    signal = np.clip(signal, 0.0, pop_mean + 12 * pop_std)
    return LabeledDataset(values=signal, labels=labels,
                          anom_type=anom_type, timestamps=ts)


# ── Algorithmes ───────────────────────────────────────────────────────────────

def detect_zscore(values, mu, sigma, threshold=3.0):
    z       = (values - mu) / max(sigma, 1e-9)
    is_anom = np.abs(z) > threshold
    score   = np.clip(np.abs(z) / threshold, 0.0, 10.0)
    return is_anom, score


def detect_iqr(values, q25, q75, k=1.5):
    iqr     = q75 - q25
    lower   = q25 - k * iqr
    upper   = q75 + k * iqr
    is_anom = (values < lower) | (values > upper)
    beyond  = np.maximum(values - upper, 0.0) + np.maximum(lower - values, 0.0)
    score   = np.clip(beyond / max(k * iqr, 1e-9), 0.0, 10.0)
    return is_anom, score


def detect_isolation_forest(values, timestamps, seed=42):
    hours    = timestamps.hour.to_numpy(dtype=float)
    dows     = timestamps.dayofweek.to_numpy(dtype=float)
    features = np.column_stack([
        values,
        np.sin(2 * np.pi * hours / 24), np.cos(2 * np.pi * hours / 24),
        np.sin(2 * np.pi * dows  /  7), np.cos(2 * np.pi * dows  /  7),
    ])
    clf = IsolationForest(n_estimators=100, contamination=0.10,
                          random_state=seed, n_jobs=-1)
    clf.fit(features)
    preds      = clf.predict(features)
    raw_scores = clf.decision_function(features)
    is_anom    = preds == -1
    neg        = -raw_scores
    score      = np.clip(neg / max(float(neg.max()), 1e-9) * 10.0, 0.0, 10.0)
    return is_anom, score


_CHRONOS_DETECTOR = None


def detect_chronos(values, timestamps, seed_ds: LabeledDataset):
    """
    Chronos-T5 Tiny zero-shot — même classe et mêmes paramètres que le ColdStart
    de production (cf. ColdStart/fuel/config.yaml). Le contexte d'amorçage est une
    série propre issue du même générateur, comme la série synthétique en production.
    """
    global _CHRONOS_DETECTOR
    if _CHRONOS_DETECTOR is None:
        from pathlib import Path
        coldstart_dir = str(Path(__file__).resolve().parents[1] / "ColdStart")
        if coldstart_dir not in sys.path:
            sys.path.insert(0, coldstart_dir)
        from common.chronos_detector import ChronosZeroShotDetector  # noqa: PLC0415
        _CHRONOS_DETECTOR = ChronosZeroShotDetector(
            model_name="autogluon/chronos-t5-tiny", device="cpu",
            context_length=72, prediction_length=12, num_samples=20,
            q_low=0.1, q_high=0.9, k_sigma=1.5,
        )

    det = _CHRONOS_DETECTOR
    det.fit(pd.DataFrame({"item_id": "eval", "ts": seed_ds.timestamps, "v": seed_ds.values}),
            "v", "ts")
    group = pd.DataFrame({"ts": timestamps, "v": values})
    is_anom, score, _, _ = det.detect(group, "v", "ts", "eval")
    return is_anom, score


def detect_ensemble(results, min_votes=2):
    vote_matrix  = np.column_stack([r[0].astype(int) for r in results])
    votes        = vote_matrix.sum(axis=1)
    is_anom      = votes >= min_votes
    score_matrix = np.column_stack([r[1] for r in results])
    score        = np.where(is_anom, score_matrix.max(axis=1), 0.0)
    return is_anom, score


# ── Métriques ─────────────────────────────────────────────────────────────────

def detection_delay(labels: np.ndarray, preds: np.ndarray, max_delay: int = 3) -> float:
    delays = []
    n = len(labels)
    for i in np.where(labels)[0]:
        for d in range(max_delay + 1):
            if i + d < n and preds[i + d]:
                delays.append(d)
                break
    return float(np.mean(delays)) if delays else float("nan")


def metrics_by_type(
    labels:    np.ndarray,
    anom_type: np.ndarray,
    preds:     np.ndarray,
    scores:    np.ndarray,
) -> dict[str, dict]:
    out = {}
    for at in ANOMALY_TYPES:
        # Masque : anomalies de ce type + tous les points normaux
        mask = (anom_type == at) | (~labels)
        yt = labels[mask]
        yp = preds[mask]
        ys = scores[mask]
        try:
            auc = float(roc_auc_score(yt, ys)) if yt.sum() > 0 else 0.0
        except Exception:
            auc = 0.0
        out[at] = {
            "precision": float(precision_score(yt, yp, zero_division=0)),
            "recall":    float(recall_score(yt, yp, zero_division=0)),
            "f1":        float(f1_score(yt, yp, zero_division=0)),
            "auc_roc":   auc,
        }
    return out


# ── Runner ────────────────────────────────────────────────────────────────────

def run_evaluation(
    n_devices: int = 3, n_seeds: int = 3, anomaly_rate: float = 0.05,
    with_chronos: bool = False,
) -> None:
    POP_MEAN = 52.3
    POP_STD  = 18.7
    POP_Q25  = 38.1
    POP_Q75  = 65.4

    algo_names = ["Z-Score", "IQR", "Isolation Forest"]
    if with_chronos:
        algo_names.append("Chronos-T5 Tiny")
    algo_names.append("Ensemble (vote≥2)")
    cumul: dict[str, dict[str, list]] = {
        n: {"p": [], "r": [], "f1": [], "auc": [], "delay": []} for n in algo_names
    }
    per_type_cumul: dict[str, dict[str, list]] = {
        at: {n: {"f1": []} for n in algo_names} for at in ANOMALY_TYPES
    }

    total_runs = n_devices * n_seeds
    for device_i in range(n_devices):
        for seed_i in range(n_seeds):
            seed = 42 + seed_i + device_i * 1000
            ds = generate_multianomaly_dataset(
                n_hours=720, anomaly_rate=anomaly_rate,
                pop_mean=POP_MEAN, pop_std=POP_STD, seed=seed,
            )

            r_z   = detect_zscore(ds.values, POP_MEAN, POP_STD)
            r_iqr = detect_iqr(ds.values, POP_Q25, POP_Q75)
            r_if  = detect_isolation_forest(ds.values, ds.timestamps, seed=seed)
            voters = [r_z, r_iqr, r_if]
            if with_chronos:
                seed_ds = generate_multianomaly_dataset(
                    n_hours=720, anomaly_rate=0.0,
                    pop_mean=POP_MEAN, pop_std=POP_STD, seed=seed + 500,
                )
                voters.append(detect_chronos(ds.values, ds.timestamps, seed_ds))
            r_ens = detect_ensemble(voters)

            for name, (is_anom, score) in zip(algo_names, [*voters, r_ens]):
                c = cumul[name]
                c["p"].append(float(precision_score(ds.labels, is_anom, zero_division=0)))
                c["r"].append(float(recall_score(ds.labels, is_anom, zero_division=0)))
                c["f1"].append(float(f1_score(ds.labels, is_anom, zero_division=0)))
                try:
                    c["auc"].append(float(roc_auc_score(ds.labels, score)))
                except Exception:
                    c["auc"].append(0.0)
                c["delay"].append(detection_delay(ds.labels, is_anom))

                pt = metrics_by_type(ds.labels, ds.anom_type, is_anom, score)
                for at in ANOMALY_TYPES:
                    per_type_cumul[at][name]["f1"].append(pt[at]["f1"])

    # ── Moyennes ──────────────────────────────────────────────────────────────
    avgs = {
        name: {
            "p":     float(np.nanmean(c["p"])),
            "r":     float(np.nanmean(c["r"])),
            "f1":    float(np.nanmean(c["f1"])),
            "auc":   float(np.nanmean(c["auc"])),
            "delay": float(np.nanmean([d for d in c["delay"] if not np.isnan(d)])),
        }
        for name, c in cumul.items()
    }
    per_type_avgs = {
        at: {name: float(np.nanmean(per_type_cumul[at][name]["f1"])) for name in algo_names}
        for at in ANOMALY_TYPES
    }

    # ── Affichage global ──────────────────────────────────────────────────────
    W = 72
    print()
    print("=" * W)
    print("ARIA — Métriques de Détection d'Anomalies (ColdStart Pipeline)")
    print("=" * W)
    print(f"  Devices simulés : {n_devices} | Seeds/device : {n_seeds} | "
          f"Runs : {total_runs} | Anomalies : {anomaly_rate*100:.0f}%")
    print(f"  Types : point (pic 4–8σ) | contextual (nuit) | collective (plateau 3–6h)")
    print(f"  IF contamination=0.10 (standard — non calqué sur le vrai taux)")
    print()

    best_f1 = max(v["f1"] for v in avgs.values())

    print(f"  {'Algorithme':<24} {'Précision':>10} {'Rappel':>8} {'F1':>8} {'AUC-ROC':>9} {'Délai':>7}")
    print("  " + "-" * 70)
    for name in algo_names:
        a     = avgs[name]
        mark  = " ✓" if abs(a["f1"] - best_f1) < 1e-6 else "  "
        delay = f"{a['delay']:.2f}h" if not np.isnan(a["delay"]) else "n/a"
        print(f"  {name + mark:<26} {a['p']:>8.3f}   {a['r']:>6.3f}   "
              f"{a['f1']:>6.3f}   {a['auc']:>7.3f}   {delay:>5}")

    # ── Affichage par type ────────────────────────────────────────────────────
    print()
    print(f"  F1-score par type d'anomalie :")
    print(f"  {'Algorithme':<24} {'Point':>10} {'Contextual':>12} {'Collective':>12}")
    print("  " + "-" * 62)
    for name in algo_names:
        f1s = {at: per_type_avgs[at][name] for at in ANOMALY_TYPES}
        best_marks = {
            at: " ✓" if f1s[at] == max(per_type_avgs[at].values()) else ""
            for at in ANOMALY_TYPES
        }
        print(f"  {name:<24} "
              f"{f1s['point']:>8.3f}{best_marks['point']:<2} "
              f"{f1s['contextual']:>10.3f}{best_marks['contextual']:<2} "
              f"{f1s['collective']:>10.3f}{best_marks['collective']:<2}")

    # ── Observations dynamiques basées sur les résultats réels ───────────────
    best_point       = max(algo_names, key=lambda n: per_type_avgs["point"][n])
    best_contextual  = max(algo_names, key=lambda n: per_type_avgs["contextual"][n])
    best_collective  = max(algo_names, key=lambda n: per_type_avgs["collective"][n])
    best_overall     = max(algo_names, key=lambda n: avgs[n]["f1"])

    ens_point = per_type_avgs["point"]["Ensemble (vote≥2)"]
    if_point  = per_type_avgs["point"]["Isolation Forest"]

    print()
    print("  Observations (issues des résultats ci-dessus) :")

    print(f"  • Point anomalies : {best_point} obtient le meilleur F1 ({per_type_avgs['point'][best_point]:.3f}).")
    if "Isolation Forest" in best_point or per_type_avgs["point"]["Isolation Forest"] > per_type_avgs["point"]["Z-Score"] + 0.05:
        print("    IF bénéficie de ses features temporelles (sin/cos heure) pour contextualiser")
        print("    les pics par rapport à la consommation attendue à ce moment de la journée.")

    print(f"  • Anomalies contextuelles : {best_contextual} obtient le meilleur F1 ({per_type_avgs['contextual'][best_contextual]:.3f}).")
    z_ctx  = per_type_avgs["contextual"]["Z-Score"]
    if_ctx = per_type_avgs["contextual"]["Isolation Forest"]
    if z_ctx > if_ctx + 0.03:
        print("    Z-Score et IQR détectent mieux les valeurs absolues hautes (surconsom. nocturne)")
        print("    car leurs seuils ne dépendent pas du contexte — tout ce qui dépasse ±3σ est signalé.")

    print(f"  • Anomalies collectives : {best_collective} obtient le meilleur F1 ({per_type_avgs['collective'][best_collective]:.3f}).")

    ens_f1  = avgs["Ensemble (vote≥2)"]["f1"]
    best_f1_val = avgs[best_overall]["f1"]
    print(f"  • Global — meilleur algo : {best_overall} (F1={best_f1_val:.3f}) | "
          f"Ensemble F1={ens_f1:.3f}.")
    if ens_f1 >= best_f1_val - 0.03:
        print("    L'ensemble est le choix le plus robuste : ses performances restent stables")
        print("    à travers les 3 types d'anomalies sans nécessiter de tuning par type.")
    else:
        print(f"    L'ensemble ne domine pas {best_overall} sur ce dataset.")
        # Pondération dérivée des meilleurs F1 par type — jamais codée en dur
        print(f"    Piste d'amélioration : vote pondéré (poids {best_point} plus élevé pour pics isolés,")
        print(f"    poids {best_contextual} pour contextuelles, {best_collective} pour collectives).")

    print("=" * W)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n-devices",    type=int,   default=3,    help="Devices simulés (défaut: 3)")
    p.add_argument("--seeds",        type=int,   default=3,    help="Seeds/device (défaut: 3)")
    p.add_argument("--anomaly-rate", type=float, default=0.05, help="Taux anomalies (défaut: 0.05)")
    p.add_argument("--with-chronos", action="store_true",
                   help="Ajoute Chronos-T5 Tiny zero-shot comme 4e votant (comme en production)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_evaluation(
        n_devices=args.n_devices,
        n_seeds=args.seeds,
        anomaly_rate=args.anomaly_rate,
        with_chronos=args.with_chronos,
    )
