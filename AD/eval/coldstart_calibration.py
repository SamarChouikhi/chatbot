"""
ARIA — ColdStart Calibration Check

Contrairement à ablation_coldstart.py / detection_metrics.py (études indépendantes,
données génériques réinventées), ce script exécute le VRAI pipeline de production
(subprocess vers ColdStart/main.py, même mécanisme que ad_runner.py) pour chacun
des 4 domaines, avec leur config.yaml réel — afin de détecter une régression de
calibration après un changement de seuil, d'algo, ou du générateur synthétique.

Principe : en mode bootstrap synthétique (--synthetic-only), le générateur de
chaque domaine injecte des anomalies à des positions connues et les marque dans
la colonne `is_injected_anomaly` du CSV résultat — une vérité terrain gratuite,
déjà présente dans chaque run. On la croise avec `is_anomaly` (colonne globale)
et `is_anomaly_<col>` (par colonne de valeur) pour calculer précision/rappel/F1,
moyennés sur plusieurs graines pour lisser le bruit d'échantillonnage.

Nécessite un CSV de population réel par domaine (le générateur synthétique a
besoin des stats de population pour produire un signal réaliste) — non fourni
dans le repo, à passer via --population-dir ou --population-map.

Usage (depuis n'importe où) :
    python coldstart_calibration.py --population-dir "C:/Users/LEGION/Downloads"
    python coldstart_calibration.py --domains fuel gaz --seeds 5
    python coldstart_calibration.py --population-map energy=/path/energy_by_phase.csv water=/path/comdemo_water.csv
    python coldstart_calibration.py --min-precision 0.85 --min-recall 0.60
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_COLDSTART_DIR = (Path(__file__).parents[1] / "ColdStart").resolve()
_MAIN_PY       = _COLDSTART_DIR / "main.py"

# domaine CLI → (fichier résultat, colonnes de valeur, nom de fichier population par défaut)
_DOMAIN_SPEC: dict[str, dict] = {
    "energy": {"result_file": "coldstart_result.csv",       "value_cols": ["cons_en"],                     "default_pop": "energy_by_phase.csv"},
    "water":  {"result_file": "coldstart_water_result.csv", "value_cols": ["conso"],                        "default_pop": "comdemo_water.csv"},
    "gaz":    {"result_file": "coldstart_gaz_result.csv",   "value_cols": ["conso", "avg_debit_per_min"],   "default_pop": "gaz.csv"},
    "fuel":   {"result_file": "coldstart_fuel_result.csv",  "value_cols": ["consommation", "vitesse"],      "default_pop": "fuel.csv"},
}


def _run_one(domain: str, population_csv: Path, seed: int, out_dir: Path) -> Path | None:
    cmd = [
        sys.executable, str(_MAIN_PY),
        "--domain", domain,
        "--synthetic-only",
        "--population", str(population_csv),
        "--seed", str(seed),
        "--output", str(out_dir),
    ]
    proc = subprocess.run(
        cmd, cwd=str(_COLDSTART_DIR), capture_output=True, text=True, timeout=600,
    )
    result_path = out_dir / _DOMAIN_SPEC[domain]["result_file"]
    if proc.returncode != 0 or not result_path.exists():
        print(f"  [ERREUR] {domain} seed={seed} exit={proc.returncode}")
        print("  " + (proc.stderr.strip().splitlines() or ["(pas de stderr)"])[-1])
        return None
    return result_path


def _metrics(injected: pd.Series, detected: pd.Series) -> dict[str, float]:
    injected = injected.astype(bool)
    detected = detected.astype(bool)
    tp = int((injected & detected).sum())
    fp = int((~injected & detected).sum())
    fn = int((injected & ~detected).sum())
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall    = tp / (tp + fn) if (tp + fn) else 1.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def run_calibration(
    domains:        list[str],
    population_map: dict[str, Path],
    n_seeds:        int,
    min_precision:  float,
    min_recall:     float,
) -> bool:
    all_ok = True
    print()
    print("=" * 78)
    print("ARIA — ColdStart Calibration Check (vrai pipeline, config réelle)")
    print("=" * 78)

    with tempfile.TemporaryDirectory(prefix="aria_coldstart_calib_") as tmp:
        tmp_path = Path(tmp)

        for domain in domains:
            spec = _DOMAIN_SPEC[domain]
            pop_csv = population_map.get(domain)
            if pop_csv is None or not pop_csv.exists():
                print(f"\n[{domain}] SKIP — CSV population introuvable : {pop_csv}")
                all_ok = False
                continue

            print(f"\n[{domain}]  population={pop_csv.name}  seeds={n_seeds}")

            # per-run metrics, per column + global
            cols_to_check = spec["value_cols"] + ["__global__"]
            runs: dict[str, list[dict]] = {c: [] for c in cols_to_check}

            for i in range(n_seeds):
                seed    = 42 + i
                out_dir = tmp_path / f"{domain}_seed{seed}"
                out_dir.mkdir(parents=True, exist_ok=True)

                result_path = _run_one(domain, pop_csv, seed, out_dir)
                if result_path is None:
                    continue

                df = pd.read_csv(result_path)
                if "is_injected_anomaly" not in df.columns:
                    print(f"  [WARN] is_injected_anomaly absent du résultat — run ignoré")
                    continue

                injected = df["is_injected_anomaly"]
                for col in spec["value_cols"]:
                    det_col = f"is_anomaly_{col}"
                    if det_col in df.columns:
                        runs[col].append(_metrics(injected, df[det_col]))
                if "is_anomaly" in df.columns:
                    runs["__global__"].append(_metrics(injected, df["is_anomaly"]))

            print(f"  {'Colonne':<22} {'Precision':>10} {'Rappel':>8} {'F1':>8}   Verdict")
            print("  " + "-" * 66)
            for col in cols_to_check:
                if not runs[col]:
                    continue
                avg_p = float(np.mean([r["precision"] for r in runs[col]]))
                avg_r = float(np.mean([r["recall"]    for r in runs[col]]))
                avg_f = float(np.mean([r["f1"]        for r in runs[col]]))
                std_p = float(np.std([r["precision"]  for r in runs[col]]))
                std_r = float(np.std([r["recall"]     for r in runs[col]]))

                ok = avg_p >= min_precision and avg_r >= min_recall
                all_ok = all_ok and ok
                verdict = "OK" if ok else "MAL CALIBRÉ"
                label = "ENSEMBLE (global)" if col == "__global__" else col
                print(
                    f"  {label:<22} {avg_p:>8.1%}   {avg_r:>6.1%}   {avg_f:>6.1%}   {verdict}"
                    f"   (±{std_p:.1%} / ±{std_r:.1%})"
                )
                if not ok:
                    reasons = []
                    if avg_p < min_precision:
                        reasons.append(f"précision {avg_p:.1%} < seuil {min_precision:.0%} (sur-détection)")
                    if avg_r < min_recall:
                        reasons.append(f"rappel {avg_r:.1%} < seuil {min_recall:.0%} (sous-détection)")
                    print(f"    → {' ; '.join(reasons)}")

    print()
    print("=" * 78)
    print("RÉSULTAT GLOBAL : " + ("✓ TOUS LES DOMAINES CALIBRÉS" if all_ok else "✗ AU MOINS UN DOMAINE MAL CALIBRÉ"))
    print("=" * 78)
    print()
    return all_ok


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--domains", nargs="+", choices=list(_DOMAIN_SPEC), default=list(_DOMAIN_SPEC))
    p.add_argument("--seeds", type=int, default=5, help="Nombre de graines à moyenner (défaut: 5)")
    p.add_argument("--population-dir", default=None, help="Dossier contenant les CSV population (noms par défaut)")
    p.add_argument("--population-map", nargs="*", default=[], metavar="DOMAIN=PATH", help="Surcharge par domaine, ex: fuel=/path/fuel.csv")
    p.add_argument("--min-precision", type=float, default=0.85)
    p.add_argument("--min-recall", type=float, default=0.60)
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    population_map: dict[str, Path] = {}
    if args.population_dir:
        base = Path(args.population_dir)
        for d, spec in _DOMAIN_SPEC.items():
            population_map[d] = base / spec["default_pop"]
    for entry in args.population_map:
        d, _, p = entry.partition("=")
        population_map[d] = Path(p)

    ok = run_calibration(
        domains        = args.domains,
        population_map = population_map,
        n_seeds        = args.seeds,
        min_precision  = args.min_precision,
        min_recall     = args.min_recall,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
