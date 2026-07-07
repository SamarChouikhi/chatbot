"""
Déclenche le pipeline AD (HotStart + ColdStart) pour les 4 domaines.

Lance depuis le répertoire chatbot/bws_pfe :
    python run_ad_now.py
    python run_ad_now.py --domain energy
    python run_ad_now.py --domain energy water
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

# Chargement .env avant tout import applicatif
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('run_ad_now')


def main():
    parser = argparse.ArgumentParser(description='Pipeline AD manuel')
    parser.add_argument(
        '--domain', nargs='+',
        choices=['energy', 'water', 'gas', 'fuel'],
        default=['energy', 'water', 'gas', 'fuel'],
        help='Domaine(s) à traiter (défaut : tous)',
    )
    args = parser.parse_args()

    # Connexion DB directe (sans lifespan FastAPI)
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '3306')
    db_name = os.environ.get('DB_NAME', 'bw_samar')
    db_user = os.environ.get('DB_USER', 'root')
    db_pass = os.environ.get('DB_PASSWORD', '')

    if not db_pass:
        logger.error("DB_PASSWORD non défini — vérifier .env")
        sys.exit(1)

    from sqlalchemy import create_engine
    url = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"
    try:
        engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=5)
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text('SELECT 1'))
        logger.info("Connexion DB OK — %s@%s:%s/%s", db_user, db_host, db_port, db_name)
    except Exception as exc:
        logger.error("Connexion DB impossible : %s", exc)
        sys.exit(1)

    import pandas as pd
    from api.pipeline.ad_runner import run_ad_domain

    run_date = datetime.utcnow().date()
    logger.info("Pipeline AD — date=%s | domaines=%s", run_date, args.domain)

    totals: dict[str, int] = {}
    for domain in args.domain:
        logger.info("─── %s ────────────────────────────────", domain.upper())
        try:
            n = run_ad_domain(engine, pd.DataFrame(), domain, run_date)
            totals[domain] = n
            logger.info("[%s] ✓ %d anomalies détectées", domain, n)
        except Exception as exc:
            logger.error("[%s] ERREUR : %s", domain, exc, exc_info=True)
            totals[domain] = -1

    ok = sum(1 for v in totals.values() if v >= 0)
    logger.info("═══ Terminé — %d/%d domaines OK | %s", ok, len(totals), totals)


if __name__ == '__main__':
    main()
