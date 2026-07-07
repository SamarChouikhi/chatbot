"""
Génère et insère les données manquantes dans archive_en_p_j
pour la période du dernier enregistrement jusqu'à aujourd'hui.

Usage :
    python generate_elec_data.py              # mode dry-run (affiche SQL)
    python generate_elec_data.py --insert     # insert direct en DB
    python generate_elec_data.py --sql        # écrit elec_test_data.sql
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# ── Connexion DB ───────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / 'chatbot' / 'bws_pfe'))

try:
    from mcp_server.db.connection import engine
    from sqlalchemy import text
    DB_AVAILABLE = True
except Exception as e:
    print(f"[WARN] DB non disponible : {e} — mode SQL uniquement")
    DB_AVAILABLE = False


# ── Paramètres ─────────────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)

# Profil horaire normalisé (facteur relatif à la moyenne)
# Simule un bâtiment : pic matin + après-midi, creux nuit
HOUR_PROFILE = {
    0: 0.3, 1: 0.25, 2: 0.22, 3: 0.20, 4: 0.20, 5: 0.25,
    6: 0.55, 7: 0.80, 8: 1.10, 9: 1.20, 10: 1.25, 11: 1.20,
    12: 1.10, 13: 1.05, 14: 1.15, 15: 1.20, 16: 1.10, 17: 0.95,
    18: 0.80, 19: 0.70, 20: 0.60, 21: 0.50, 22: 0.45, 23: 0.35,
}

# Variation semaine vs week-end
WEEKDAY_FACTOR = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.95, 5: 0.65, 6: 0.55}


def _noise(pct: float = 0.08) -> float:
    """Bruit gaussien ±pct autour de 1.0."""
    return 1.0 + random.gauss(0, pct)


def _seasonal(d: date) -> float:
    """Léger facteur saisonnier : +5 % hiver, -5 % été."""
    month = d.month
    return 1.0 + 0.05 * math.cos(math.pi * (month - 1) / 6)


def read_existing_stats(engine) -> dict:
    """Lit les devices et leur consommation moyenne depuis archive_en_p_j."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id_device,
                   AVG(cons_en_L1) as avg_l1,
                   AVG(cons_en_L2) as avg_l2,
                   AVG(cons_en_L3) as avg_l3,
                   MAX(date)       as last_date
            FROM archive_en_p_j
            GROUP BY id_device
        """)).mappings().fetchall()
    return {r['id_device']: dict(r) for r in rows}


def generate_rows(device_id: int, avg_l1: float, avg_l2: float, avg_l3: float,
                  start: date, end: date) -> list[dict]:
    """Génère des lignes journalières réalistes pour un device."""
    rows = []
    current = start
    while current <= end:
        factor = WEEKDAY_FACTOR[current.weekday()] * _seasonal(current)
        l1 = max(0.0, avg_l1 * factor * _noise())
        l2 = max(0.0, avg_l2 * factor * _noise())
        l3 = max(0.0, avg_l3 * factor * _noise())
        rows.append({
            'id_device': device_id,
            'date': current,
            'cons_l1': round(l1, 4),
            'cons_l2': round(l2, 4),
            'cons_l3': round(l3, 4),
            # Valeurs qualité réseau cohérentes
            'moy_cosfi_l1': round(random.uniform(0.88, 0.97), 3),
            'moy_cosfi_l2': round(random.uniform(0.88, 0.97), 3),
            'moy_cosfi_l3': round(random.uniform(0.88, 0.97), 3),
            'moy_thd_l1':   round(random.uniform(2.0, 6.5), 2),
            'moy_thd_l2':   round(random.uniform(2.0, 6.5), 2),
            'moy_thd_l3':   round(random.uniform(2.0, 6.5), 2),
            'battery_level': random.randint(180, 255),
        })
        current += timedelta(days=1)
    return rows


def to_sql(rows: list[dict]) -> str:
    """Convertit les lignes en SQL INSERT."""
    if not rows:
        return ''
    lines = [
        "INSERT INTO archive_en_p_j "
        "(id_device, date, cons_en_L1, cons_en_L2, cons_en_L3, "
        "moy_cosfi_L1, moy_cosfi_L2, moy_cosfi_L3, "
        "moy_THD_L1, moy_THD_L2, moy_THD_L3, battery_level) VALUES"
    ]
    values = []
    for r in rows:
        values.append(
            f"({r['id_device']}, '{r['date']}', "
            f"{r['cons_l1']}, {r['cons_l2']}, {r['cons_l3']}, "
            f"{r['moy_cosfi_l1']}, {r['moy_cosfi_l2']}, {r['moy_cosfi_l3']}, "
            f"{r['moy_thd_l1']}, {r['moy_thd_l2']}, {r['moy_thd_l3']}, "
            f"{r['battery_level']})"
        )
    lines.append(',\n'.join(values))
    lines.append('ON DUPLICATE KEY UPDATE '
                 'cons_en_L1=VALUES(cons_en_L1), cons_en_L2=VALUES(cons_en_L2), '
                 'cons_en_L3=VALUES(cons_en_L3);')
    return '\n'.join(lines)


def insert_rows(engine, rows: list[dict]) -> int:
    """Insère les lignes directement en DB."""
    if not rows:
        return 0
    sql = text("""
        INSERT INTO archive_en_p_j
            (id_device, date, cons_en_L1, cons_en_L2, cons_en_L3,
             moy_cosfi_L1, moy_cosfi_L2, moy_cosfi_L3,
             moy_THD_L1, moy_THD_L2, moy_THD_L3, battery_level)
        VALUES
            (:id_device, :date, :cons_l1, :cons_l2, :cons_l3,
             :moy_cosfi_l1, :moy_cosfi_l2, :moy_cosfi_l3,
             :moy_thd_l1, :moy_thd_l2, :moy_thd_l3, :battery_level)
        ON DUPLICATE KEY UPDATE
            cons_en_L1=VALUES(cons_en_L1),
            cons_en_L2=VALUES(cons_en_L2),
            cons_en_L3=VALUES(cons_en_L3)
    """)
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description='Génère les données électricité manquantes')
    parser.add_argument('--insert', action='store_true', help='Insère en DB')
    parser.add_argument('--sql',    action='store_true', help='Écrit elec_test_data.sql')
    parser.add_argument('--end',    default=str(date.today()), help='Date de fin (YYYY-MM-DD)')
    args = parser.parse_args()

    end_date = date.fromisoformat(args.end)

    if not DB_AVAILABLE:
        print("[ERREUR] DB non disponible. Impossible de lire les stats existantes.")
        sys.exit(1)

    print("Lecture des statistiques existantes...")
    stats = read_existing_stats(engine)

    if not stats:
        print("[ERREUR] Aucun device trouvé dans archive_en_p_j.")
        sys.exit(1)

    print(f"Devices trouvés : {sorted(stats.keys())}")

    all_rows = []
    for device_id, s in stats.items():
        last = s['last_date']
        if hasattr(last, 'date'):
            last = last.date()
        start = last + timedelta(days=1)

        if start > end_date:
            print(f"  Device {device_id} : déjà à jour (last={last})")
            continue

        avg_l1 = s['avg_l1'] or 50.0
        avg_l2 = s['avg_l2'] or 50.0
        avg_l3 = s['avg_l3'] or 50.0

        rows = generate_rows(device_id, avg_l1, avg_l2, avg_l3, start, end_date)
        print(f"  Device {device_id} : {len(rows)} jours générés ({start} → {end_date})")
        all_rows.extend(rows)

    if not all_rows:
        print("Aucune donnée à générer.")
        return

    if args.insert:
        n = insert_rows(engine, all_rows)
        print(f"\n✓ {n} lignes insérées dans archive_en_p_j")
        # Déclencher le pipeline pour mettre à jour daily_energy
        print("\nDéclenchement du pipeline...")
        import requests
        try:
            r = requests.post('http://localhost:8001/analytics/run?hours_back=1500', timeout=5)
            print(f"  Pipeline lancé : {r.json().get('message', r.status_code)}")
        except Exception as e:
            print(f"  Pipeline non déclenché (lancer manuellement) : {e}")

    elif args.sql:
        sql_content = (
            "-- Données électricité manquantes — générées automatiquement\n"
            "USE bw_samar;\n\n"
            + to_sql(all_rows)
        )
        out = Path(__file__).parent / 'elec_test_data.sql'
        out.write_text(sql_content, encoding='utf-8')
        print(f"\n✓ Fichier SQL écrit : {out}")
        print("  Exécute-le dans MySQL Workbench ou avec : mysql -u root -p bw_samar < elec_test_data.sql")

    else:
        # Dry-run : afficher les premières lignes
        print(f"\n{len(all_rows)} lignes à insérer. Exemple (5 premières) :")
        for r in all_rows[:5]:
            print(f"  {r['id_device']} | {r['date']} | L1={r['cons_l1']:.2f} L2={r['cons_l2']:.2f} L3={r['cons_l3']:.2f} kWh")
        print("\nAjoute --insert pour insérer en DB, ou --sql pour générer le fichier SQL.")


if __name__ == '__main__':
    main()
