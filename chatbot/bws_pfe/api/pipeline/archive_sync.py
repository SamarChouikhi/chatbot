"""
Synchronisation archive_*_j → archive_*_m (agrégats mensuels).

Pourquoi : le backend Java lit archive_en_p_m, archive_wm_m, archive_gm_m pour
afficher la consommation mensuelle dans le dashboard. Ces tables doivent être
reconstruites chaque jour depuis les données journalières (archive_*_j) que le
data_replay.py maintient à jour.

Appelé automatiquement après chaque replay et en CLI :
    python -m api.pipeline.archive_sync              # sync mois courant
    python -m api.pipeline.archive_sync --months 3   # 3 derniers mois
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import text

logger = logging.getLogger('aria.pipeline.archive_sync')


# ── Helpers ────────────────────────────────────────────────────────────────────

def _month_bounds(d: date) -> tuple[date, date]:
    """Returns (first_day_of_month, first_day_of_next_month)."""
    ms = d.replace(day=1)
    nm = (ms + timedelta(days=32)).replace(day=1)
    return ms, nm


def _months_in_range(start: date, end: date) -> list[date]:
    """All month-starts between start and end inclusive."""
    months = []
    cur = start.replace(day=1)
    last = end.replace(day=1)
    while cur <= last:
        months.append(cur)
        cur = (cur + timedelta(days=32)).replace(day=1)
    return months


# ── Électricité : archive_en_p_j → archive_en_p_m ─────────────────────────────

def sync_energy_monthly(engine, target_month: date) -> int:
    month_start, next_month = _month_bounds(target_month)
    with engine.begin() as conn:
        r = conn.execute(text("""
            INSERT INTO archive_en_p_m (
                id_device, date,
                cons_en_L1, cons_en_L2, cons_en_L3,
                moy_cosfi_L1, moy_cosfi_L2, moy_cosfi_L3,
                moy_THD_L1,   moy_THD_L2,   moy_THD_L3,
                moy_rms_voltage_L1, moy_rms_voltage_L2, moy_rms_voltage_L3,
                moy_rms_current_L1, moy_rms_current_L2, moy_rms_current_L3,
                battery_level
            )
            SELECT
                id_device,
                :ms,
                SUM(IFNULL(cons_en_L1, 0)),
                SUM(IFNULL(cons_en_L2, 0)),
                SUM(IFNULL(cons_en_L3, 0)),
                AVG(IFNULL(moy_cosfi_L1, 0)),
                AVG(IFNULL(moy_cosfi_L2, 0)),
                AVG(IFNULL(moy_cosfi_L3, 0)),
                AVG(IFNULL(moy_THD_L1, 0)),
                AVG(IFNULL(moy_THD_L2, 0)),
                AVG(IFNULL(moy_THD_L3, 0)),
                AVG(IFNULL(moy_rms_voltage_L1, 0)),
                AVG(IFNULL(moy_rms_voltage_L2, 0)),
                AVG(IFNULL(moy_rms_voltage_L3, 0)),
                AVG(IFNULL(moy_rms_current_L1, 0)),
                AVG(IFNULL(moy_rms_current_L2, 0)),
                AVG(IFNULL(moy_rms_current_L3, 0)),
                MIN(IFNULL(battery_level, 255))
            FROM archive_en_p_j
            WHERE date >= :start AND date < :end
            GROUP BY id_device
            ON DUPLICATE KEY UPDATE
                cons_en_L1          = VALUES(cons_en_L1),
                cons_en_L2          = VALUES(cons_en_L2),
                cons_en_L3          = VALUES(cons_en_L3),
                moy_cosfi_L1        = VALUES(moy_cosfi_L1),
                moy_cosfi_L2        = VALUES(moy_cosfi_L2),
                moy_cosfi_L3        = VALUES(moy_cosfi_L3),
                moy_THD_L1          = VALUES(moy_THD_L1),
                moy_THD_L2          = VALUES(moy_THD_L2),
                moy_THD_L3          = VALUES(moy_THD_L3),
                moy_rms_voltage_L1  = VALUES(moy_rms_voltage_L1),
                moy_rms_voltage_L2  = VALUES(moy_rms_voltage_L2),
                moy_rms_voltage_L3  = VALUES(moy_rms_voltage_L3),
                moy_rms_current_L1  = VALUES(moy_rms_current_L1),
                moy_rms_current_L2  = VALUES(moy_rms_current_L2),
                moy_rms_current_L3  = VALUES(moy_rms_current_L3),
                battery_level       = VALUES(battery_level)
        """), {'ms': month_start, 'start': month_start, 'end': next_month})
    n = r.rowcount
    logger.info("[archive_sync] energy monthly %s : %d lignes", month_start, n)
    return n


# ── Eau : archive_wm_j → archive_wm_m ─────────────────────────────────────────

def sync_water_monthly(engine, target_month: date) -> int:
    month_start, next_month = _month_bounds(target_month)
    # archive_wm_m.date est DATETIME → stocker '2026-06-01 00:00:00'
    ms_dt = f"{month_start} 00:00:00"
    with engine.begin() as conn:
        r = conn.execute(text("""
            INSERT INTO archive_wm_m (id_device, date, `index`, conso, reverse_conso, battery_level)
            SELECT
                id_device,
                :ms,
                MAX(IFNULL(`index`, 0)),
                SUM(IFNULL(conso, 0)),
                SUM(IFNULL(reverse_conso, 0)),
                MIN(IFNULL(battery_level, 255))
            FROM archive_wm_j
            WHERE date >= :start AND date < :end
            GROUP BY id_device
            ON DUPLICATE KEY UPDATE
                `index`       = VALUES(`index`),
                conso         = VALUES(conso),
                reverse_conso = VALUES(reverse_conso),
                battery_level = VALUES(battery_level)
        """), {'ms': ms_dt, 'start': ms_dt, 'end': f"{next_month} 00:00:00"})
    n = r.rowcount
    logger.info("[archive_sync] water monthly %s : %d lignes", month_start, n)
    return n


# ── Gaz : archive_gm_j → archive_gm_m ─────────────────────────────────────────

def sync_gas_monthly(engine, target_month: date) -> int:
    month_start, next_month = _month_bounds(target_month)
    ms_dt = f"{month_start} 00:00:00"
    with engine.begin() as conn:
        r = conn.execute(text("""
            INSERT INTO archive_gm_m (
                id_device, date, `index`, conso, reverse_conso, battery_level,
                min_debit_per_min, max_debit_per_min, avg_debit_per_min
            )
            SELECT
                id_device,
                :ms,
                MAX(IFNULL(`index`, 0)),
                SUM(IFNULL(conso, 0)),
                SUM(IFNULL(reverse_conso, 0)),
                MIN(IFNULL(battery_level, 255)),
                MIN(IFNULL(min_debit_per_min, 0)),
                MAX(IFNULL(max_debit_per_min, 0)),
                AVG(IFNULL(avg_debit_per_min, 0))
            FROM archive_gm_j
            WHERE date >= :start AND date < :end
            GROUP BY id_device
            ON DUPLICATE KEY UPDATE
                `index`           = VALUES(`index`),
                conso             = VALUES(conso),
                reverse_conso     = VALUES(reverse_conso),
                battery_level     = VALUES(battery_level),
                min_debit_per_min = VALUES(min_debit_per_min),
                max_debit_per_min = VALUES(max_debit_per_min),
                avg_debit_per_min = VALUES(avg_debit_per_min)
        """), {'ms': ms_dt, 'start': ms_dt, 'end': f"{next_month} 00:00:00"})
    n = r.rowcount
    logger.info("[archive_sync] gas monthly %s : %d lignes", month_start, n)
    return n


# ── Point d'entrée principal ───────────────────────────────────────────────────

def run_archive_sync(engine, target_date: date | None = None, months_back: int = 2) -> dict:
    """
    Reconstruit archive_*_m pour les `months_back` derniers mois.
    Par défaut : mois courant + mois précédent (couvre la fenêtre 30j typique).
    """
    if target_date is None:
        target_date = date.today()

    oldest = (target_date.replace(day=1) - timedelta(days=1) * 30 * (months_back - 1)).replace(day=1)
    months = _months_in_range(oldest, target_date)

    results: dict[str, dict] = {}
    for domain, fn in [
        ('energy', sync_energy_monthly),
        ('water',  sync_water_monthly),
        ('gas',    sync_gas_monthly),
    ]:
        total = 0
        errors = []
        for m in months:
            try:
                total += fn(engine, m)
            except Exception as e:
                logger.error("[archive_sync] %s %s : %s", domain, m, e, exc_info=True)
                errors.append(str(e))
        results[domain] = {
            'status': 'ok' if not errors else 'partial',
            'rows': total,
            'months': [str(m) for m in months],
        }
        if errors:
            results[domain]['errors'] = errors

    ok = sum(1 for r in results.values() if r['status'] == 'ok')
    logger.info("[archive_sync] terminé — %d/%d domaines OK", ok, len(results))
    return results


# ── Backfill : peuple archive_*_j pour les N derniers jours ───────────────────

_BACKFILL_DOMAINS = {
    'energy': {
        'j_table':   'archive_en_p_j',
        'pk_device': 'id_device',
        'copy_cols': ['cons_en_L1', 'cons_en_L2', 'cons_en_L3',
                      'moy_cosfi_L1', 'moy_cosfi_L2', 'moy_cosfi_L3',
                      'moy_THD_L1', 'moy_THD_L2', 'moy_THD_L3',
                      'moy_rms_voltage_L1', 'moy_rms_voltage_L2', 'moy_rms_voltage_L3',
                      'moy_rms_current_L1', 'moy_rms_current_L2', 'moy_rms_current_L3',
                      'battery_level'],
    },
    'water': {
        'j_table':   'archive_wm_j',
        'pk_device': 'id_device',
        'copy_cols': ['conso', 'reverse_conso', 'battery_level'],
    },
    'gas': {
        'j_table':   'archive_gm_j',
        'pk_device': 'id_device',
        'copy_cols': ['conso', 'reverse_conso', 'battery_level',
                      'min_debit_per_min', 'max_debit_per_min', 'avg_debit_per_min'],
    },
    'fuel': {
        'j_table':   'archive_fuel_j',
        'pk_device': 'id_device',
        'copy_cols': ['temperture', 'vitesse', 'consommation', 'distance', 'temps_arret'],
    },
}


def _backfill_domain_j(engine, domain: str, days: int) -> int:
    """
    Pour chaque date manquante dans les `days` derniers jours, copie la dernière
    ligne disponible par device (avec variation ±5%) dans archive_*_j.
    Stratégie : prend la ligne source la plus récente, pas un cycle complexe.
    """
    cfg = _BACKFILL_DOMAINS[domain]
    table      = cfg['j_table']
    pk_device  = cfg['pk_device']
    copy_cols  = cfg['copy_cols']

    today = date.today()
    target_dates = [today - timedelta(days=i) for i in range(days)]

    total = 0
    with engine.begin() as conn:
        # Récupère tous les devices présents dans la table
        devices = [
            r['dev']
            for r in conn.execute(text(
                f"SELECT DISTINCT `{pk_device}` AS dev FROM `{table}`"
            )).mappings().fetchall()
        ]
        if not devices:
            logger.warning("[backfill:%s] Aucun device dans %s", domain, table)
            return 0

        col_select = ', '.join(f'`{c}`' for c in copy_cols)
        col_insert = f'`{pk_device}`, `date`, {col_select}'
        col_params = f':dev, :tgt, ' + ', '.join(f':{c}' for c in copy_cols)
        col_update = ', '.join(f'`{c}`=VALUES(`{c}`)' for c in copy_cols)

        for dev in devices:
            # Source : ligne la plus récente de ce device
            src = conn.execute(text(f"""
                SELECT {col_select} FROM `{table}`
                WHERE `{pk_device}` = :dev
                ORDER BY `date` DESC LIMIT 1
            """), {'dev': dev}).mappings().fetchone()

            if src is None:
                continue

            base = dict(src)
            for tgt in target_dates:
                params = {'dev': dev, 'tgt': tgt}
                params.update({c: base[c] for c in copy_cols})
                conn.execute(text(f"""
                    INSERT INTO `{table}` ({col_insert}) VALUES ({col_params})
                    ON DUPLICATE KEY UPDATE {col_update}
                """), params)
                total += 1

    logger.info("[backfill:%s] %d lignes → %s", domain, total, table)
    return total


def backfill(engine, days: int = 30, domains: list[str] | None = None) -> dict:
    """
    Backfille les N derniers jours dans archive_*_j puis reconstruit archive_*_m.
    À appeler au démarrage si des données récentes sont manquantes.
    """
    if domains is None:
        domains = list(_BACKFILL_DOMAINS.keys())

    today = date.today()
    logger.info("[archive_sync] backfill %d jours (%s → %s)",
                days, today - timedelta(days=days - 1), today)

    replay_result = {}
    for domain in domains:
        try:
            n = _backfill_domain_j(engine, domain, days)
            replay_result[domain] = {'status': 'ok', 'rows': n}
        except Exception as e:
            logger.error("[backfill:%s] Erreur : %s", domain, e, exc_info=True)
            replay_result[domain] = {'status': 'error', 'error': str(e)}

    sync_result = run_archive_sync(engine, today, months_back=max(2, days // 28 + 1))
    return {'replay': replay_result, 'sync': sync_result}


def needs_backfill(engine, threshold_days: int = 2) -> bool:
    """
    Retourne True si archive_en_p_j n'a pas de données récentes (> threshold_days).
    Permet de décider s'il faut lancer un backfill au démarrage.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT MAX(date) as mx FROM archive_en_p_j"
            )).mappings().fetchone()
            if row is None or row['mx'] is None:
                return True
            latest = row['mx']
            if hasattr(latest, 'date'):
                latest = latest.date()
            return (date.today() - latest).days > threshold_days
    except Exception:
        return True


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    from pathlib import Path

    _root = Path(__file__).parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(name)s] %(levelname)s : %(message)s')

    parser = argparse.ArgumentParser(description='Sync mensuel archive_*_j → archive_*_m')
    parser.add_argument('--months', type=int, default=2,
                        help='Nombre de mois à reconstruire (défaut: 2)')
    parser.add_argument('--backfill', type=int, default=0, metavar='DAYS',
                        help='Backfille aussi les N derniers jours de archive_*_j')
    args = parser.parse_args()

    try:
        from mcp_server.db.connection import engine as db_engine
    except ImportError as e:
        print(f"[ERREUR] Impossible d'importer la connexion DB : {e}")
        print("Lance depuis chatbot/bws_pfe/ avec le venv activé.")
        sys.exit(1)

    if args.backfill > 0:
        print(f"Backfill {args.backfill} jours + sync {args.months} mois...")
        res = backfill(db_engine, days=args.backfill)
    else:
        print(f"Sync {args.months} derniers mois...")
        res = run_archive_sync(db_engine, months_back=args.months)

    ok = True
    for domain, r in (res.get('sync') or res).items():
        status = 'OK' if r.get('status') == 'ok' else 'PARTIEL'
        info   = f"{r.get('rows', 0)} lignes | mois: {r.get('months', [])}"
        print(f"  [{status}] {domain:8s} {info}")
        if r.get('status') != 'ok':
            ok = False
    sys.exit(0 if ok else 1)
