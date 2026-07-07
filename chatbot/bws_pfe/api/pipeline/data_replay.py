"""
Replay des données historiques vers les dates courantes.

Principe : on prend les anciennes données (archive_*_j) et on les réinsère
avec la date d'aujourd'hui en les faisant "cycler" sur la plage historique.
Cela simule un flux IoT continu sans avoir besoin de vraies mesures.

Appelé par le scheduler APScheduler en complément du pipeline quotidien.
Peut aussi être lancé manuellement :
    python -m api.pipeline.data_replay              # replay aujourd'hui
    python -m api.pipeline.data_replay --days 30    # replay les 30 derniers jours
    python -m api.pipeline.data_replay --domain energy
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import text

logger = logging.getLogger('aria.pipeline.replay')


# ── Config par domaine ─────────────────────────────────────────────────────────

DOMAIN_CONFIG = {
    'energy': {
        'archive_j': 'archive_en_p_j',
        'pk_device': 'id_device',
        'pk_date':   'date',
        'copy_cols': ['cons_en_L1', 'cons_en_L2', 'cons_en_L3',
                      'moy_cosfi_L1', 'moy_cosfi_L2', 'moy_cosfi_L3',
                      'moy_THD_L1',   'moy_THD_L2',   'moy_THD_L3',
                      'battery_level'],
        'update_rt': {
            'table':  'rt_en_p',
            'pk':     'id_device',
            'fields': [('date', 'NOW()')],
        },
    },
    'water': {
        'archive_j': 'archive_wm_j',
        'pk_device': 'id_device',
        'pk_date':   'date',
        'copy_cols': ['conso', 'reverse_conso', 'battery_level'],
        'update_rt': {
            'table':  'rt_wm',
            'pk':     'id_device',
            'fields': [('date', 'NOW()')],
        },
    },
    'gas': {
        'archive_j': 'archive_gm_j',
        'pk_device': 'id_device',
        'pk_date':   'date',
        'copy_cols': ['conso', 'reverse_conso', 'battery_level',
                      'min_debit_per_min', 'max_debit_per_min', 'avg_debit_per_min'],
        'update_rt': {
            'table':  'rt_gm',
            'pk':     'id_device',
            'fields': [('date', 'NOW()')],
        },
    },
    'fuel': {
        'archive_j': 'archive_fuel_j',
        'pk_device': 'id_device',
        'pk_date':   'date',
        'copy_cols': ['temperture', 'vitesse', 'consommation', 'distance', 'temps_arret'],
        'update_rt': None,
    },
}


def _get_historical_range(conn, table: str, pk_device: str, pk_date: str) -> dict:
    """Retourne {device_id: (min_date, max_date, nb_jours)} pour chaque device."""
    rows = conn.execute(text(f"""
        SELECT `{pk_device}` as dev,
               MIN(`{pk_date}`) as d_min,
               MAX(`{pk_date}`) as d_max,
               COUNT(*)         as nb
        FROM `{table}`
        GROUP BY `{pk_device}`
    """)).mappings().fetchall()
    result = {}
    for r in rows:
        d_min = r['d_min']
        d_max = r['d_max']
        if hasattr(d_min, 'date'): d_min = d_min.date()
        if hasattr(d_max, 'date'): d_max = d_max.date()
        nb = (d_max - d_min).days + 1
        result[r['dev']] = (d_min, d_max, nb)
    return result


def _source_date(target: date, d_min: date, cycle_days: int) -> date:
    """
    Mappe une date cible vers une date source dans la plage historique.
    Utilise un modulo pour cycler indéfiniment sur les données historiques.
    """
    offset = (target - d_min).days % cycle_days
    return d_min + timedelta(days=offset)


def replay_domain(engine, domain: str, target_dates: list[date]) -> int:
    """
    Pour chaque date cible, copie les données de la date source correspondante
    dans la table archive_*_j avec la date cible.
    Retourne le nombre de lignes insérées/mises à jour.
    """
    cfg = DOMAIN_CONFIG.get(domain)
    if cfg is None:
        raise ValueError(f"Domaine inconnu : {domain}")

    table      = cfg['archive_j']
    pk_device  = cfg['pk_device']
    pk_date    = cfg['pk_date']
    copy_cols  = cfg['copy_cols']

    total = 0
    with engine.begin() as conn:
        ranges = _get_historical_range(conn, table, pk_device, pk_date)
        if not ranges:
            logger.warning("[replay:%s] Aucune donnée historique dans %s", domain, table)
            return 0

        for target in target_dates:
            rows_inserted = 0
            for device_id, (d_min, d_max, cycle_days) in ranges.items():
                src_date = _source_date(target, d_min, cycle_days)

                # Récupérer la ligne source
                src_row = conn.execute(text(f"""
                    SELECT {', '.join(f'`{c}`' for c in copy_cols)}
                    FROM `{table}`
                    WHERE `{pk_device}` = :dev AND `{pk_date}` = :dt
                    LIMIT 1
                """), {'dev': device_id, 'dt': src_date}).mappings().fetchone()

                if src_row is None:
                    logger.debug("[replay:%s] Pas de source pour device=%s date=%s", domain, device_id, src_date)
                    continue

                # Insérer avec la date cible (idempotent via ON DUPLICATE KEY)
                col_list    = f'`{pk_device}`, `{pk_date}`, ' + ', '.join(f'`{c}`' for c in copy_cols)
                param_list  = ':dev, :target, ' + ', '.join(f':{c}' for c in copy_cols)
                update_list = ', '.join(f'`{c}`=VALUES(`{c}`)' for c in copy_cols)

                params = {'dev': device_id, 'target': target}
                params.update({c: src_row[c] for c in copy_cols})

                conn.execute(text(f"""
                    INSERT INTO `{table}` ({col_list})
                    VALUES ({param_list})
                    ON DUPLICATE KEY UPDATE {update_list}
                """), params)
                rows_inserted += 1

            logger.debug("[replay:%s] %s → %d devices mis à jour", domain, target, rows_inserted)
            total += rows_inserted

        # Mettre à jour la date des tables rt_* pour afficher "en direct"
        rt_cfg = cfg.get('update_rt')
        if rt_cfg:
            rt_table = rt_cfg['table']
            for device_id in ranges:
                conn.execute(text(f"""
                    UPDATE `{rt_table}` SET date = NOW()
                    WHERE `{rt_cfg['pk']}` = :dev
                """), {'dev': device_id})

    logger.info("[replay:%s] %d lignes replay → %s", domain, total, table)
    return total


def run_replay(engine, target_dates: list[date] | None = None,
               domains: list[str] | None = None,
               skip_monthly_sync: bool = False) -> dict:
    """
    Point d'entrée principal.
    Par défaut : replay d'aujourd'hui pour tous les domaines, puis sync mensuel.
    """
    import time
    if target_dates is None:
        target_dates = [date.today()]
    if domains is None:
        domains = list(DOMAIN_CONFIG.keys())

    results = {}
    t0 = time.monotonic()
    for domain in domains:
        try:
            n = replay_domain(engine, domain, target_dates)
            results[domain] = {'status': 'ok', 'rows': n}
        except Exception as e:
            logger.error("[replay:%s] Erreur : %s", domain, e, exc_info=True)
            results[domain] = {'status': 'error', 'error': str(e)}

    elapsed   = time.monotonic() - t0
    ok_count  = sum(1 for r in results.values() if r['status'] == 'ok')
    err_count = len(results) - ok_count
    total_rows = sum(r.get('rows', 0) for r in results.values())

    if err_count == 0:
        logger.info(
            "*** REPLAY SUCCES — %d/%d domaines OK | %d lignes insérées | %.2fs ***",
            ok_count, len(results), total_rows, elapsed,
        )
    else:
        failed = [d for d, r in results.items() if r['status'] != 'ok']
        logger.error(
            "*** REPLAY PARTIEL — %d/%d OK | %d ERREURS (%s) | %.2fs ***",
            ok_count, len(results), err_count, ', '.join(failed), elapsed,
        )

    # Reconstruire les agrégats mensuels après chaque replay
    if not skip_monthly_sync and ok_count > 0:
        try:
            from api.pipeline.archive_sync import run_archive_sync
            latest = max(target_dates)
            sync_res = run_archive_sync(engine, latest)
            results['_monthly_sync'] = sync_res
        except Exception as e:
            logger.error("[replay] Erreur sync mensuel : %s", e, exc_info=True)

    return results


# ── Point d'entrée CLI ─────────────────────────────────────────────────────────
# Lancer depuis chatbot/bws_pfe/ :
#   python api/pipeline/data_replay.py
#   python api/pipeline/data_replay.py --days 7 --domain energy water

if __name__ == '__main__':
    import sys
    from pathlib import Path

    # Ajoute chatbot/bws_pfe au path pour trouver mcp_server sans charger api/__init__.py
    _root = Path(__file__).parents[2]  # chatbot/bws_pfe
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(name)s] %(levelname)s : %(message)s')

    parser = argparse.ArgumentParser(description='Replay données IoT historiques')
    parser.add_argument('--days',   type=int, default=1,
                        help="Nombre de jours à rejouer en arrière (défaut: 1 = aujourd'hui)")
    parser.add_argument('--domain', nargs='+', choices=list(DOMAIN_CONFIG.keys()),
                        help='Domaines à rejouer (défaut: tous)')
    args = parser.parse_args()

    try:
        from mcp_server.db.connection import engine as db_engine
    except ImportError as _e:
        print(f"[ERREUR] Impossible d'importer la connexion DB : {_e}")
        print("Vérifie que tu es dans chatbot/bws_pfe/ et que le venv est activé.")
        sys.exit(1)

    today = date.today()
    dates = [today - timedelta(days=i) for i in range(args.days)]

    print(f"Replay {len(dates)} jour(s) pour domaines : {args.domain or 'tous'}")
    results = run_replay(db_engine, dates, args.domain)
    ok = True
    for domain, r in results.items():
        status = 'OK' if r['status'] == 'ok' else 'ERREUR'
        info   = f"{r.get('rows', 0)} lignes" if r['status'] == 'ok' else r.get('error', '')
        print(f"  [{status}] {domain:10s} {info}")
        if r['status'] != 'ok':
            ok = False
    sys.exit(0 if ok else 1)
