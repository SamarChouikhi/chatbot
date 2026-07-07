"""
ARIA — Import CSV → MySQL bw_samar

Charge un fichier CSV de données IoT et l'insère dans les tables daily_*
via les mêmes fonctions d'agrégation que le pipeline FastAPI.

Usage:
    # Import un CSV spécifique
    python import_to_db.py --domain energy --data /path/to/energy.csv

    # Import tous les CSV définis dans les config.yaml AD
    python import_to_db.py --all

    # Avec un .env différent de celui par défaut
    python import_to_db.py --domain water --data water.csv --env /autre/.env
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── Résolution des chemins ─────────────────────────────────────────────────────
_SCRIPT_DIR  = Path(__file__).parent.resolve()
_BWS_PFE_DIR = _SCRIPT_DIR.parent / 'chatbot' / 'bws_pfe'

# Rend les modules FastAPI importables depuis ce script standalone
sys.path.insert(0, str(_BWS_PFE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
_log = logging.getLogger('aria.ad.import_to_db')


def _load_env(env_path: str | None) -> None:
    try:
        from dotenv import load_dotenv
        path = Path(env_path) if env_path else _BWS_PFE_DIR / '.env'
        if path.exists():
            load_dotenv(dotenv_path=path)
            _log.info("Env chargé depuis %s", path)
        else:
            _log.warning(".env introuvable : %s — variables d'environnement utilisées telles quelles", path)
    except ImportError:
        _log.warning("python-dotenv non installé — variables d'environnement utilisées telles quelles")


def _get_engine():
    from mcp_server.db.connection import engine
    return engine


def _ensure_tables(engine) -> None:
    """Crée les tables daily_* si elles n'existent pas (idempotent)."""
    from api.db import ensure_analytics_tables
    try:
        ensure_analytics_tables(engine)
        _log.info("Tables daily_* vérifiées / créées")
    except Exception as exc:
        _log.warning("ensure_analytics_tables : %s (tables déjà créées ?)", exc)


def _run_import(domain: str, csv_path: str) -> None:
    from api.pipeline.csv_importer import import_csv

    engine = _get_engine()
    _ensure_tables(engine)
    _log.info("═" * 60)
    _log.info("Import CSV → bw_samar | domaine: %s | fichier: %s", domain, csv_path)
    _log.info("═" * 60)

    result = import_csv(engine, csv_path, domain)

    _log.info("═" * 60)
    _log.info("Terminé")
    _log.info("  ► Domaine          : %s", result['domain'])
    _log.info("  ► Fichier source   : %s", result['source_file'])
    _log.info("  ► Dates traitées   : %s", result['dates_processed'])
    _log.info("  ► Lignes insérées  : %s", result['rows_inserted'])
    _log.info("  ► Période          : %s → %s", result['first_date'], result['last_date'])
    _log.info("═" * 60)


def _run_import_all() -> None:
    from api.pipeline.csv_importer import import_all_from_config

    engine = _get_engine()
    _ensure_tables(engine)
    _log.info("═" * 60)
    _log.info("Import tous les CSV (config.yaml AD) → bw_samar")
    _log.info("═" * 60)

    results = import_all_from_config(engine)

    _log.info("═" * 60)
    _log.info("Résumé final")
    for domain, r in results.items():
        status = r.get('status', '?')
        if status == 'ok':
            _log.info(
                "  ✓ %-8s : %d dates | %d lignes (%s → %s)",
                domain, r['dates_processed'], r['rows_inserted'],
                r['first_date'], r['last_date'],
            )
        elif status == 'skipped':
            _log.info("  - %-8s : ignoré (%s)", domain, r.get('reason', ''))
        else:
            _log.error("  ✗ %-8s : erreur — %s", domain, r.get('error', ''))
    _log.info("═" * 60)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='ARIA — Import CSV → MySQL bw_samar (tables daily_*)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        '--all',
        action='store_true',
        help='Importe les 4 CSV définis dans les config.yaml AD',
    )
    mode.add_argument(
        '--domain',
        choices=['energy', 'water', 'gas', 'fuel'],
        help='Domaine à importer',
    )
    p.add_argument(
        '--data',
        metavar='CSV',
        help='Chemin vers le fichier CSV source (requis si --domain)',
    )
    p.add_argument(
        '--env',
        metavar='ENV_FILE',
        default=None,
        help='Chemin vers le fichier .env (défaut: chatbot/bws_pfe/.env)',
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    _load_env(args.env)

    if args.all:
        _run_import_all()
    else:
        if not args.data:
            print("Erreur : --data requis avec --domain", file=sys.stderr)
            sys.exit(1)
        try:
            _run_import(args.domain, args.data)
        except FileNotFoundError as e:
            _log.error("%s", e)
            sys.exit(1)
        except ValueError as e:
            _log.error("%s", e)
            sys.exit(1)


if __name__ == '__main__':
    main()
