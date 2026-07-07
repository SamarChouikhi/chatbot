"""
ARIA AD — Unified CLI entry point (HotStart + ColdStart).

Routing rule:
    device has > --min-context rows → HotStart  (Chronos time-series forecasting)
    device has ≤ --min-context rows → ColdStart (statistical ensemble, synthetic bootstrap)

Default threshold: 192 rows = 8 days of hourly measurements.

Usage:
    # Analyse complète (auto-routing)
    python main.py --domain energy --data /path/to/energy.csv

    # Sans graphiques (mode production/API)
    python main.py --domain water --data water.csv --no-plots

    # Avec GPU et fine-tuning Chronos
    python main.py --domain energy --data energy.csv --device cuda --retrain

    # Seuil personnalisé (ex: 5 jours = 120h)
    python main.py --domain fuel --data fuel.csv --min-context 120

Output (dans --output-dir) :
    anomalies_result.csv   — résultats unifiés avec colonne 'strategy' (hotstart|coldstart)
    anomalies_summary.csv  — résumé par device et stratégie
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

_AD_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_AD_DIR))

from runner import COLD_THRESHOLD_HOURS, run_domain  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger("aria.ad.main")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "ARIA AD — Runner unifié HotStart + ColdStart\n"
            f"Seuil par défaut : {COLD_THRESHOLD_HOURS} h "
            f"({COLD_THRESHOLD_HOURS // 24} jours)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--domain",
        default="energy",
        choices=["energy", "water", "gaz", "fuel"],
        help="Domaine IoT à analyser (défaut: energy)",
    )
    p.add_argument(
        "--data",
        required=True,
        metavar="CSV",
        help="CSV source contenant tous les devices (colonnes requises: date, id_device, ...)",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="Dossier de sortie (défaut: outputs/<domain>/)",
    )
    p.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda", "mps"],
        help="Accélérateur Torch pour HotStart/Chronos (défaut: cpu)",
    )
    p.add_argument(
        "--no-plots",
        action="store_true",
        help="Ignorer la génération de graphiques PNG (plus rapide, recommandé en production)",
    )
    p.add_argument(
        "--retrain",
        action="store_true",
        help="Relancer le fine-tuning mensuel Chronos avant la détection (HotStart uniquement)",
    )
    p.add_argument(
        "--min-context",
        type=int,
        default=COLD_THRESHOLD_HOURS,
        metavar="HOURS",
        dest="min_context",
        help=(
            f"Seuil hot/cold en nombre de lignes brutes dans le CSV "
            f"(défaut: {COLD_THRESHOLD_HOURS} ≈ 8 jours horaires)"
        ),
    )
    return p


def main() -> None:
    args       = _build_parser().parse_args()
    data_path  = Path(args.data)
    output_dir = (
        Path(args.output_dir) if args.output_dir
        else _AD_DIR / "outputs" / args.domain
    )

    if not data_path.exists():
        _log.error("Fichier introuvable : %s", data_path)
        sys.exit(1)

    _log.info("═" * 60)
    _log.info("ARIA AD — Runner unifié  |  domaine: %s", args.domain)
    _log.info("Données  : %s", data_path)
    _log.info("Sortie   : %s", output_dir)
    _log.info("Seuil    : %d h (%d jours)", args.min_context, args.min_context // 24)
    _log.info("═" * 60)

    # ── Chargement ────────────────────────────────────────────────────────────
    header     = pd.read_csv(data_path, nrows=0).columns.tolist()
    date_cols  = [c for c in header if c.lower() in ("date", "timestamp", "ts", "datetime")]
    df         = pd.read_csv(data_path, parse_dates=date_cols or False)
    _log.info("Chargement : %d lignes | %d colonnes", len(df), len(df.columns))

    if df.empty:
        _log.error("Le fichier CSV est vide.")
        sys.exit(1)

    # ── Exécution ─────────────────────────────────────────────────────────────
    result, summary = run_domain(
        domain          = args.domain,
        df              = df,
        output_dir      = output_dir,
        generate_plots  = not args.no_plots,
        retrain         = args.retrain,
        accelerator     = args.device,
        threshold_hours = args.min_context,
    )

    if result.empty:
        _log.error("Aucun résultat produit — consulter les logs ci-dessus.")
        sys.exit(1)

    # ── Résumé final ──────────────────────────────────────────────────────────
    n_hot  = int((result["strategy"] == "hotstart").sum())
    n_cold = int((result["strategy"] == "coldstart").sum())
    n_anom = int((result["is_anomaly"] == 1).sum()) if "is_anomaly" in result.columns else 0

    _log.info("═" * 60)
    _log.info("Terminé")
    _log.info("  ► Total lignes   : %d", len(result))
    _log.info("  ► HotStart       : %d lignes", n_hot)
    _log.info("  ► ColdStart      : %d lignes", n_cold)
    _log.info("  ► Anomalies      : %d détectées", n_anom)
    _log.info("  ► Résultats      : %s/anomalies_result.csv", output_dir)
    _log.info("  ► Résumé         : %s/anomalies_summary.csv", output_dir)
    _log.info("═" * 60)


if __name__ == "__main__":
    main()
