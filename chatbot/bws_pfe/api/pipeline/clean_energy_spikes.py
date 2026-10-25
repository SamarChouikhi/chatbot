"""
Nettoyage ponctuel de daily_energy : lectures aberrantes (index cumulé pris pour
une consommation) déjà présentes en base.

Même règle que le filtre du pipeline (api/pipeline/data_quality.py), appliquée sur
tout l'historique de chaque (device_id, phase). Les lignes concernées sont copiées
dans daily_energy_spikes_backup, puis leur cons_en passe à NULL (ignoré par SUM,
retiré par dropna côté AD).

Usage (depuis chatbot/bws_pfe) :
    python -m api.pipeline.clean_energy_spikes            # simulation, rien n'est modifié
    python -m api.pipeline.clean_energy_spikes --apply    # sauvegarde + correction
    python -m api.pipeline.clean_energy_spikes --restore  # annule depuis la sauvegarde
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parents[2]))
from api.pipeline.data_quality import SPIKE_FACTOR, spike_mask
from mcp_server.db.connection import engine

logger = logging.getLogger('aria.pipeline.clean_energy_spikes')

BACKUP_TABLE = 'daily_energy_spikes_backup'


def find_spikes(factor: float = SPIKE_FACTOR) -> pd.DataFrame:
    df = pd.read_sql(
        text("SELECT device_id, phase, date, hour, cons_en FROM daily_energy WHERE cons_en IS NOT NULL"),
        engine,
    )
    return df.loc[spike_mask(df, 'cons_en', ['device_id', 'phase'], factor=factor)]


def apply_fix(spikes: pd.DataFrame) -> int:
    keys = spikes[['device_id', 'phase', 'date', 'hour']].to_dict('records')
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS `{BACKUP_TABLE}` LIKE daily_energy"))
        # INSERT IGNORE : relancer --apply ne doit pas écraser la valeur d'origine sauvegardée
        conn.execute(text(f"""
            INSERT IGNORE INTO `{BACKUP_TABLE}`
            SELECT * FROM daily_energy
            WHERE device_id = :device_id AND phase = :phase AND date = :date AND hour = :hour
        """), keys)
        result = conn.execute(text("""
            UPDATE daily_energy SET cons_en = NULL
            WHERE device_id = :device_id AND phase = :phase AND date = :date AND hour = :hour
        """), keys)
    return result.rowcount


def restore() -> int:
    with engine.begin() as conn:
        exists = conn.execute(text("SHOW TABLES LIKE :t"), {'t': BACKUP_TABLE}).fetchone()
        if not exists:
            return 0
        result = conn.execute(text(f"""
            UPDATE daily_energy d
            JOIN `{BACKUP_TABLE}` b
              ON b.device_id = d.device_id AND b.phase = d.phase AND b.date = d.date AND b.hour = d.hour
            SET d.cons_en = b.cons_en
        """))
    return result.rowcount


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='sauvegarder puis corriger les lignes')
    mode.add_argument('--restore', action='store_true', help='restaurer les valeurs sauvegardées')
    parser.add_argument('--factor', type=float, default=SPIKE_FACTOR, help=f'seuil × médiane (défaut {SPIKE_FACTOR})')
    args = parser.parse_args()

    if args.restore:
        logger.info("%d ligne(s) restaurée(s) depuis %s", restore(), BACKUP_TABLE)
        return

    spikes = find_spikes(args.factor)
    logger.info("%d lecture(s) aberrante(s) détectée(s) (> %.0f× médiane de la série)", len(spikes), args.factor)
    if spikes.empty:
        return
    summary = spikes.groupby('device_id').agg(lignes=('cons_en', 'size'), min=('cons_en', 'min'), max=('cons_en', 'max'))
    logger.info("Par compteur :\n%s", summary.to_string())

    if not args.apply:
        logger.info("Simulation uniquement — relancer avec --apply pour corriger.")
        return
    logger.info("%d ligne(s) corrigée(s) — originaux sauvegardés dans %s", apply_fix(spikes), BACKUP_TABLE)


if __name__ == '__main__':
    main()
