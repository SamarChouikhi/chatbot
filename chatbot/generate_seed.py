#!/usr/bin/env python3
"""Generates data_seed.sql — rich realistic data for IoT energy platform."""

import random
from datetime import date, datetime, timedelta

random.seed(42)

def r(mn, mx, dec=2):
    return round(random.uniform(mn, mx), dec)

def ri(mn, mx):
    return random.randint(mn, mx)

lines = []
out = lines.append

out("-- ============================================================")
out("-- data_seed.sql — données réelles IoT énergie (30 jours)")
out("-- Tables: espace, device, rt_en_p, rt_wm, rt_gm,")
out("--         archive_en_p_j, archive_wm_j, archive_gm_j,")
out("--         fuel_consumption, alerts")
out("-- Periode archives: 2026-03-15 au 2026-04-13")
out("-- ============================================================")
out("")
out("SET FOREIGN_KEY_CHECKS = 0;")
out("SET NAMES utf8mb4;")
out("")

# ── 1. ESPACE ─────────────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 1. ESPACES (5 sites)")
out("-- ────────────────────────────────────────────")
out("INSERT INTO espace (id, nom, type, etat) VALUES")
out("  (1, 'Batiment Administratif', 1, 1),")
out("  (2, 'Atelier de Production',  2, 1),")
out("  (3, 'Entrepot Logistique',    3, 1),")
out("  (4, 'Residence du Personnel', 4, 1),")
out("  (5, 'Zone Technique',         5, 1);")
out("")

# ── 2. DEVICE ─────────────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 2. DEVICES (15 compteurs)")
out("-- type: 1=Elec  2=Eau  3=Gaz  4=Carburant")
out("-- ────────────────────────────────────────────")
out("INSERT INTO device (id, adresse, nom, description, type, id_espace, geometry, max_uptime, id_ls, is_general_meter, last_saved_index) VALUES")
devices = [
    (1,  '00:1A:2B:3C:4D:01', 'ELEC-ADMIN-GM',    'Compteur général Bâtiment Administratif',  1, 1, 'POINT(36.8065 10.1815)', 99, 101, 1, 48000),
    (2,  '00:1A:2B:3C:4D:02', 'ELEC-ATELIER',     'Compteur électricité Atelier Production',   1, 2, 'POINT(36.8072 10.1822)', 99, 102, 0, 72000),
    (3,  '00:1A:2B:3C:4D:03', 'ELEC-ENTREPOT',    'Compteur électricité Entrepôt',              1, 3, 'POINT(36.8080 10.1830)', 99, 103, 0, 31000),
    (4,  '00:1A:2B:3C:4D:04', 'ELEC-RESIDENCE',   'Compteur électricité Résidence',             1, 4, 'POINT(36.8058 10.1808)', 99, 104, 0, 19500),
    (5,  '00:1A:2B:3C:4D:05', 'ELEC-ZTECH',       'Compteur électricité Zone Technique',        1, 5, 'POINT(36.8090 10.1840)', 99, 105, 0, 16000),
    (6,  '00:1A:2B:3C:4D:06', 'EAU-ADMIN',        'Compteur eau Bâtiment Administratif',        2, 1, 'POINT(36.8066 10.1816)', 99, 106, 0, 125000),
    (7,  '00:1A:2B:3C:4D:07', 'EAU-ATELIER',      'Compteur eau Atelier (circuit process)',      2, 2, 'POINT(36.8073 10.1823)', 99, 107, 0, 380000),
    (8,  '00:1A:2B:3C:4D:08', 'EAU-RESIDENCE',    'Compteur eau Résidence',                     2, 4, 'POINT(36.8059 10.1809)', 99, 108, 0, 88000),
    (9,  '00:1A:2B:3C:4D:09', 'EAU-ZTECH',        'Compteur eau Zone Technique',                2, 5, 'POINT(36.8091 10.1841)', 99, 109, 0, 54000),
    (10, '00:1A:2B:3C:4D:0A', 'GAZ-CHAUDIERE',    'Compteur gaz Chaudière Centrale',            3, 1, 'POINT(36.8067 10.1817)', 99, 110, 0, 92000),
    (11, '00:1A:2B:3C:4D:0B', 'GAZ-ATELIER',      'Compteur gaz four industriel Atelier',       3, 2, 'POINT(36.8074 10.1824)', 99, 111, 0, 61000),
    (12, '00:1A:2B:3C:4D:0C', 'GAZ-CUISINE',      'Compteur gaz cuisine Résidence',             3, 4, 'POINT(36.8060 10.1810)', 99, 112, 0, 18500),
    (13, '00:1A:2B:3C:4D:0D', 'FUEL-VEH01',       'Véhicule utilitaire Ford Transit',           4, 1, 'POINT(36.8068 10.1818)', 99, 113, 0, 0),
    (14, '00:1A:2B:3C:4D:0E', 'FUEL-VEH02',       'Camion poids lourd Man TGX',                4, 2, 'POINT(36.8075 10.1825)', 99, 114, 0, 0),
    (15, '00:1A:2B:3C:4D:0F', 'FUEL-VEH03',       'Véhicule léger Renault Clio',               4, 3, 'POINT(36.8081 10.1831)', 99, 115, 0, 0),
]
drows = []
for d in devices:
    drows.append(f"  ({d[0]}, '{d[1]}', '{d[2]}', '{d[3]}', {d[4]}, {d[5]}, '{d[6]}', {d[7]}, {d[8]}, {d[9]}, {d[10]})")
out(",\n".join(drows) + ";")
out("")

# ── 3. RT_EN_P ────────────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 3. RT_EN_P — snapshot temps réel électricité")
out("-- ────────────────────────────────────────────")
now_ts = '2026-04-13 14:32:17'

elec_profiles = {
    1: dict(en1=48250, en2=41100, en3=34800, cf=0.91, thd=5.2, thdc=4.3, cur=52, volt=228, ap=4800, batt=215, rssi=-78, snr=9),
    2: dict(en1=72600, en2=69900, en3=59100, cf=0.84, thd=11.5, thdc=9.8, cur=102, volt=225, ap=12500, batt=200, rssi=-82, snr=7),
    3: dict(en1=31400, en2=27700, en3=22300, cf=0.89, thd=7.2, thdc=6.1, cur=44, volt=227, ap=5100, batt=220, rssi=-75, snr=10),
    4: dict(en1=19900, en2=17350, en3=14750, cf=0.94, thd=3.8, thdc=3.1, cur=28, volt=230, ap=2900, batt=230, rssi=-71, snr=12),
    5: dict(en1=16650, en2=15050, en3=12450, cf=0.91, thd=5.5, thdc=4.7, cur=23, volt=229, ap=2400, batt=225, rssi=-76, snr=11),
}

rt_ep_rows = []
for dev_id, p in elec_profiles.items():
    cf=p['cf']; thd=p['thd']; thdc=p['thdc']; cur=p['cur']; volt=p['volt']; ap=p['ap']
    rp = round(ap * (1-cf**2)**0.5 / cf, 1)
    app_p = round(ap / cf, 1)
    row = (
        f"  ({dev_id}, '{now_ts}', "
        # en_L1..L3
        f"{p['en1']}, {p['en2']}, {p['en3']}, "
        # cosfi L1..L3
        f"{cf:.3f}, {round(cf-0.01,3):.3f}, {round(cf+0.01,3):.3f}, "
        # THD L1..L3
        f"{thd:.2f}, {round(thd-0.3,2):.2f}, {round(thd+0.4,2):.2f}, "
        # THDC L1..L3
        f"{thdc:.2f}, {round(thdc-0.2,2):.2f}, {round(thdc+0.3,2):.2f}, "
        # rms_current L1..L3
        f"{cur:.1f}, {round(cur-2,1):.1f}, {round(cur-4,1):.1f}, "
        # rms_voltage L1..L3
        f"{volt:.1f}, {round(volt-0.5,1):.1f}, {round(volt+0.3,1):.1f}, "
        # active_power L1..L3
        f"{ap}, {round(ap*0.97,1)}, {round(ap*0.94,1)}, "
        # en_reactive L1..L3
        f"{round(p['en1']*0.18,1)}, {round(p['en2']*0.18,1)}, {round(p['en3']*0.18,1)}, "
        # en_apparent L1..L3
        f"{round(p['en1']/cf,1)}, {round(p['en2']/cf,1)}, {round(p['en3']/cf,1)}, "
        # min/max cosfi L1..L3
        f"{round(cf-0.04,3):.3f}, {round(cf+0.03,3):.3f}, {round(cf-0.05,3):.3f}, {round(cf+0.02,3):.3f}, {round(cf-0.03,3):.3f}, {round(cf+0.04,3):.3f}, "
        # min/max voltage L1..L3
        f"{round(volt-8,1):.1f}, {round(volt+6,1):.1f}, {round(volt-9,1):.1f}, {round(volt+5,1):.1f}, {round(volt-7,1):.1f}, {round(volt+7,1):.1f}, "
        # min/max current L1..L3
        f"{round(cur*0.6,1):.1f}, {round(cur*1.3,1):.1f}, {round(cur*0.58,1):.1f}, {round(cur*1.28,1):.1f}, {round(cur*0.55,1):.1f}, {round(cur*1.25,1):.1f}, "
        # moy/min/max apparent_power L1..L3
        f"{app_p:.1f}, {round(app_p*0.6,1):.1f}, {round(app_p*1.3,1):.1f}, "
        f"{round(app_p*0.97,1):.1f}, {round(app_p*0.97*0.6,1):.1f}, {round(app_p*0.97*1.3,1):.1f}, "
        f"{round(app_p*0.94,1):.1f}, {round(app_p*0.94*0.6,1):.1f}, {round(app_p*0.94*1.3,1):.1f}, "
        # moy/min/max reactive_power L1..L3
        f"{rp:.1f}, {round(rp*0.55,1):.1f}, {round(rp*1.35,1):.1f}, "
        f"{round(rp*0.98,1):.1f}, {round(rp*0.98*0.55,1):.1f}, {round(rp*0.98*1.35,1):.1f}, "
        f"{round(rp*0.95,1):.1f}, {round(rp*0.95*0.55,1):.1f}, {round(rp*0.95*1.35,1):.1f}, "
        # min/max active_power L1..L3
        f"{round(ap*0.4,1):.1f}, {round(ap*1.35,1):.1f}, {round(ap*0.97*0.4,1):.1f}, {round(ap*0.97*1.35,1):.1f}, {round(ap*0.94*0.4,1):.1f}, {round(ap*0.94*1.35,1):.1f}, "
        # min/max/moy fp L1..L3
        f"{round(cf-0.04,3):.3f}, {round(cf+0.03,3):.3f}, {cf:.3f}, {round(cf-0.05,3):.3f}, {round(cf+0.02,3):.3f}, {round(cf-0.01,3):.3f}, {round(cf-0.03,3):.3f}, {round(cf+0.04,3):.3f}, {round(cf+0.01,3):.3f}, "
        # min/max THDC L1..L3
        f"{round(thdc-1.5,2):.2f}, {round(thdc+2.0,2):.2f}, {round(thdc-1.3,2):.2f}, {round(thdc+1.8,2):.2f}, {round(thdc-1.2,2):.2f}, {round(thdc+2.1,2):.2f}, "
        # min/max THD L1..L3
        f"{round(thd-2.0,2):.2f}, {round(thd+3.0,2):.2f}, {round(thd-1.8,2):.2f}, {round(thd+2.8,2):.2f}, {round(thd-1.5,2):.2f}, {round(thd+3.2,2):.2f}, "
        # rssi, snr, ctr, battery_level, gateway, nsh, tts, di, degres
        f"{p['rssi']}, {p['snr']}, {ri(50,200)}, {p['batt']}, {ri(1,3)}, 0, 0, 0, {ri(20,38)}, "
        # en_accumulee_jour L1..L3, en_accumulee_mois L1..L3
        f"{ri(280,460)}, {ri(240,400)}, {ri(200,340)}, {ri(6500,9800)}, {ri(5500,8400)}, {ri(4500,7000)}, "
        # en_reactive_heure L1..L3
        f"{round(rp/24,2):.2f}, {round(rp/24*0.97,2):.2f}, {round(rp/24*0.94,2):.2f}, "
        # en_reactive_jour L1..L3
        f"{round(rp*0.8,2):.2f}, {round(rp*0.8*0.97,2):.2f}, {round(rp*0.8*0.94,2):.2f}, "
        # en_reactive_mois L1..L3
        f"{round(rp*18,2):.2f}, {round(rp*18*0.97,2):.2f}, {round(rp*18*0.94,2):.2f}"
        f")"
    )
    rt_ep_rows.append(row)

out("INSERT INTO rt_en_p (id_device, `date`,")
out("  en_L1, en_L2, en_L3,")
out("  cosfi_L1, cosfi_L2, cosfi_L3,")
out("  THD_L1, THD_L2, THD_L3,")
out("  THDC_L1, THDC_L2, THDC_L3,")
out("  rms_current_L1, rms_current_L2, rms_current_L3,")
out("  rms_voltage_L1, rms_voltage_L2, rms_voltage_L3,")
out("  active_power_L1, active_power_L2, active_power_L3,")
out("  en_reactive_L1, en_reactive_L2, en_reactive_L3,")
out("  en_apparent_L1, en_apparent_L2, en_apparent_L3,")
out("  min_cosfi_L1, max_cosfi_L1, min_cosfi_L2, max_cosfi_L2, min_cosfi_L3, max_cosfi_L3,")
out("  min_rms_voltage_L1, max_rms_voltage_L1, min_rms_voltage_L2, max_rms_voltage_L2, min_rms_voltage_L3, max_rms_voltage_L3,")
out("  min_rms_current_L1, max_rms_current_L1, min_rms_current_L2, max_rms_current_L2, min_rms_current_L3, max_rms_current_L3,")
out("  moy_apparent_power_L1, min_apparent_power_L1, max_apparent_power_L1,")
out("  moy_apparent_power_L2, min_apparent_power_L2, max_apparent_power_L2,")
out("  moy_apparent_power_L3, min_apparent_power_L3, max_apparent_power_L3,")
out("  moy_reactive_power_L1, min_reactive_power_L1, max_reactive_power_L1,")
out("  moy_reactive_power_L2, min_reactive_power_L2, max_reactive_power_L2,")
out("  moy_reactive_power_L3, min_reactive_power_L3, max_reactive_power_L3,")
out("  min_active_power_L1, max_active_power_L1, min_active_power_L2, max_active_power_L2, min_active_power_L3, max_active_power_L3,")
out("  min_fp_L1, max_fp_L1, moy_fp_L1, min_fp_L2, max_fp_L2, moy_fp_L2, min_fp_L3, max_fp_L3, moy_fp_L3,")
out("  min_THDC_L1, max_THDC_L1, min_THDC_L2, max_THDC_L2, min_THDC_L3, max_THDC_L3,")
out("  min_THD_L1, max_THD_L1, min_THD_L2, max_THD_L2, min_THD_L3, max_THD_L3,")
out("  rssi, snr, ctr, battery_level, gateway, nsh, tts, di, degres,")
out("  en_accumulee_jour_L1, en_accumulee_jour_L2, en_accumulee_jour_L3,")
out("  en_accumulee_mois_L1, en_accumulee_mois_L2, en_accumulee_mois_L3,")
out("  en_reactive_heure_L1, en_reactive_heure_L2, en_reactive_heure_L3,")
out("  en_reactive_jour_L1, en_reactive_jour_L2, en_reactive_jour_L3,")
out("  en_reactive_mois_L1, en_reactive_mois_L2, en_reactive_mois_L3")
out(") VALUES")
out(",\n".join(rt_ep_rows) + ";")
out("")

# ── 4. RT_WM ─────────────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 4. RT_WM — snapshot temps réel eau")
out("-- ────────────────────────────────────────────")
wm_profiles = {
    6: dict(idx=125400, batt=218, rssi=-74, snr=10, n_alert=0, leak=0, fraud=0, sens=0, degres=19),
    7: dict(idx=381200, batt=205, rssi=-80, snr=8,  n_alert=0, leak=0, fraud=0, sens=0, degres=22),
    8: dict(idx=88600,  batt=222, rssi=-71, snr=12, n_alert=0, leak=0, fraud=0, sens=0, degres=17),
    9: dict(idx=54300,  batt=215, rssi=-77, snr=9,  n_alert=1, leak=0, fraud=0, sens=0, degres=18),
}
rt_wm_rows = []
for dev_id, p in wm_profiles.items():
    rt_wm_rows.append(
        f"  ({dev_id}, '{now_ts}', {p['idx']}, {p['leak']}, {p['fraud']}, "
        f"{p['sens']}, {p['batt']}, {ri(80,200)}, {p['snr']}, {p['rssi']}, "
        f"{ri(1,3)}, {p['n_alert']}, {p['degres']})"
    )
out("INSERT INTO rt_wm (id_device, `date`, `index`, leak, fraud, sens, battery_level, ctr, snr, rssi, gateway, n_alert, degres) VALUES")
out(",\n".join(rt_wm_rows) + ";")
out("")

# ── 5. RT_GM ─────────────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 5. RT_GM — snapshot temps réel gaz")
out("-- ────────────────────────────────────────────")
gm_profiles = {
    10: dict(idx=92400, batt=210, rssi=-79, snr=8,  n_alert=0, leak=0, fraud=0, sens=0, degres=21, min_d=0.8, max_d=18.5, avg_d=9.2, crc=0),
    11: dict(idx=61500, batt=198, rssi=-85, snr=6,  n_alert=1, leak=0, fraud=0, sens=0, degres=24, min_d=0.5, max_d=22.1, avg_d=11.5, crc=0),
    12: dict(idx=18650, batt=225, rssi=-69, snr=13, n_alert=0, leak=0, fraud=0, sens=0, degres=20, min_d=0.2, max_d=8.4,  avg_d=3.8, crc=0),
}
rt_gm_rows = []
for dev_id, p in gm_profiles.items():
    rt_gm_rows.append(
        f"  ({dev_id}, '{now_ts}', {p['idx']}, {p['leak']}, {p['fraud']}, "
        f"{p['sens']}, {p['batt']}, {ri(60,180)}, {p['snr']}, {p['rssi']}, "
        f"{ri(1,3)}, {p['n_alert']}, {p['degres']}, "
        f"{p['min_d']}, {p['max_d']}, {p['avg_d']}, {p['crc']})"
    )
out("INSERT INTO rt_gm (id_device, `date`, `index`, leak, fraud, sens, battery_level, ctr, snr, rssi, gateway, n_alert, degres, min_debit_per_min, max_debit_per_min, avg_debit_per_min, crc) VALUES")
out(",\n".join(rt_gm_rows) + ";")
out("")

# ── helpers ───────────────────────────────────────────────────────────────────
start_date = date(2026, 3, 15)

def is_weekend(d):
    return d.weekday() >= 5  # Saturday=5, Sunday=6

def day_factor(d):
    """Return a multiplier: 0.65 weekend, 1.0±noise weekday."""
    if is_weekend(d):
        return round(random.uniform(0.60, 0.72), 3)
    else:
        return round(random.uniform(0.88, 1.12), 3)

# ── 6. ARCHIVE_EN_P_J ─────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 6. ARCHIVE_EN_P_J — 5 devices × 30 jours")
out("-- ────────────────────────────────────────────")

# Device base daily consumption (L1, L2, L3) in kWh
elec_archive = {
    1: dict(base_cons=(35, 30, 25), cosfi=0.91, thd=5.2, thdc=4.3, cur=52, volt=228, start_idx=(48000, 41000, 34500)),
    2: dict(base_cons=(55, 52, 44), cosfi=0.84, thd=11.5, thdc=9.8, cur=102, volt=225, start_idx=(72000, 69000, 58000)),
    3: dict(base_cons=(25, 22, 18), cosfi=0.89, thd=7.2, thdc=6.1, cur=44, volt=227, start_idx=(31000, 27000, 22000)),
    4: dict(base_cons=(16, 14, 12), cosfi=0.94, thd=3.8, thdc=3.1, cur=28, volt=230, start_idx=(19500, 17000, 14500)),
    5: dict(base_cons=(13, 12, 10), cosfi=0.91, thd=5.5, thdc=4.7, cur=23, volt=229, start_idx=(16000, 14500, 12000)),
}

ep_col = ("id_device, `date`, "
          "en_L1, cons_en_L1, en_L2, cons_en_L2, en_L3, cons_en_L3, "
          "en_L4, cons_en_L4, en_L5, cons_en_L5, en_L6, cons_en_L6, "
          "min_cosfi_L1, max_cosfi_L1, moy_cosfi_L1, "
          "min_cosfi_L2, max_cosfi_L2, moy_cosfi_L2, "
          "min_cosfi_L3, max_cosfi_L3, moy_cosfi_L3, "
          "min_THD_L1, max_THD_L1, moy_THD_L1, "
          "min_THD_L2, max_THD_L2, moy_THD_L2, "
          "min_THD_L3, max_THD_L3, moy_THD_L3, "
          "min_rms_current_L1, max_rms_current_L1, moy_rms_current_L1, "
          "min_rms_current_L2, max_rms_current_L2, moy_rms_current_L2, "
          "min_rms_current_L3, max_rms_current_L3, moy_rms_current_L3, "
          "min_rms_voltage_L1, max_rms_voltage_L1, moy_rms_voltage_L1, "
          "min_rms_voltage_L2, max_rms_voltage_L2, moy_rms_voltage_L2, "
          "min_rms_voltage_L3, max_rms_voltage_L3, moy_rms_voltage_L3, "
          "min_active_power_L1, max_active_power_L1, moy_active_power_L1, "
          "min_active_power_L2, max_active_power_L2, moy_active_power_L2, "
          "min_active_power_L3, max_active_power_L3, moy_active_power_L3, "
          "en_reactive_L1, cons_en_reactive_L1, en_reactive_L2, cons_en_reactive_L2, "
          "en_reactive_L3, cons_en_reactive_L3, "
          "en_apparent_L1, en_apparent_L2, en_apparent_L3, "
          "cons_en_apparent_L1, cons_en_apparent_L2, cons_en_apparent_L3, "
          "min_fp_L1, max_fp_L1, moy_fp_L1, "
          "min_fp_L2, max_fp_L2, moy_fp_L2, "
          "min_fp_L3, max_fp_L3, moy_fp_L3, "
          "min_apparent_power_L1, max_apparent_power_L1, moy_apparent_power_L1, "
          "min_apparent_power_L2, max_apparent_power_L2, moy_apparent_power_L2, "
          "min_apparent_power_L3, max_apparent_power_L3, moy_apparent_power_L3, "
          "min_reactive_power_L1, max_reactive_power_L1, moy_reactive_power_L1, "
          "min_reactive_power_L2, max_reactive_power_L2, moy_reactive_power_L2, "
          "min_reactive_power_L3, max_reactive_power_L3, moy_reactive_power_L3, "
          "max_THDC_L1, min_THDC_L1, moy_THDC_L1, "
          "max_THDC_L2, min_THDC_L2, moy_THDC_L2, "
          "max_THDC_L3, min_THDC_L3, moy_THDC_L3, "
          "battery_level")

out(f"INSERT INTO archive_en_p_j ({ep_col}) VALUES")

ep_rows = []
for dev_id, p in elec_archive.items():
    bc = p['base_cons']
    cf = p['cosfi']
    thd = p['thd']
    thdc = p['thdc']
    cur = p['cur']
    volt = p['volt']
    cumul = list(p['start_idx'])
    cumul_r = [round(x * 0.18, 1) for x in cumul]
    cumul_a = [round(x / cf, 1) for x in cumul]

    for d_off in range(30):
        cur_date = start_date + timedelta(days=d_off)
        f = day_factor(cur_date)
        # Daily consumption per phase
        c = [round(bc[i] * f + random.uniform(-1.5, 1.5), 2) for i in range(3)]
        # Update cumul
        cumul = [round(cumul[i] + c[i], 2) for i in range(3)]
        cumul_r = [round(cumul_r[i] + c[i]*0.18, 2) for i in range(3)]
        cumul_a = [round(cumul_a[i] + c[i]/cf, 2) for i in range(3)]

        # cosfi variation per day
        cf_day = round(cf + random.uniform(-0.03, 0.03), 3)
        cf_min = round(cf_day - random.uniform(0.03, 0.06), 3)
        cf_max = round(cf_day + random.uniform(0.01, 0.04), 3)

        # THD variation
        thd_day = round(thd + random.uniform(-1.5, 2.5), 2)
        thd_min = round(thd_day - random.uniform(0.8, 1.5), 2)
        thd_max = round(thd_day + random.uniform(1.0, 2.5), 2)

        # THDC variation
        thdc_day = round(thdc + random.uniform(-1.0, 2.0), 2)
        thdc_min = round(thdc_day - random.uniform(0.5, 1.2), 2)
        thdc_max = round(thdc_day + random.uniform(0.8, 2.0), 2)

        # Current & voltage (per phase, scaled by factor)
        cur_day = [round(cur * f + random.uniform(-3, 3), 1) for _ in range(3)]
        volt_day = round(volt + random.uniform(-3, 3), 1)

        # Active power (W)
        ap_day = [round(cur_day[i] * volt_day * cf_day, 0) for i in range(3)]

        rp_day = [round(ap_day[i] * (1 - cf_day**2)**0.5 / cf_day, 1) for i in range(3)]
        app_day = [round(ap_day[i] / cf_day, 1) for i in range(3)]

        row = (
            f"  ({dev_id}, '{cur_date}', "
            # en_L1, cons_en_L1, en_L2, cons_en_L2, en_L3, cons_en_L3
            f"{cumul[0]}, {c[0]}, {cumul[1]}, {c[1]}, {cumul[2]}, {c[2]}, "
            # en_L4..L6 (not used, 0)
            f"0, 0, 0, 0, 0, 0, "
            # cosfi min/max/moy L1..L3
            f"{cf_min:.3f}, {cf_max:.3f}, {cf_day:.3f}, "
            f"{round(cf_min-0.01,3):.3f}, {round(cf_max-0.01,3):.3f}, {round(cf_day-0.005,3):.3f}, "
            f"{round(cf_min+0.01,3):.3f}, {round(cf_max+0.01,3):.3f}, {round(cf_day+0.005,3):.3f}, "
            # THD min/max/moy L1..L3
            f"{thd_min:.2f}, {thd_max:.2f}, {thd_day:.2f}, "
            f"{round(thd_min-0.2,2):.2f}, {round(thd_max-0.2,2):.2f}, {round(thd_day-0.1,2):.2f}, "
            f"{round(thd_min+0.1,2):.2f}, {round(thd_max+0.1,2):.2f}, {round(thd_day+0.1,2):.2f}, "
            # rms_current min/max/moy L1..L3
            f"{round(cur_day[0]*0.55,1):.1f}, {round(cur_day[0]*1.32,1):.1f}, {cur_day[0]:.1f}, "
            f"{round(cur_day[1]*0.55,1):.1f}, {round(cur_day[1]*1.32,1):.1f}, {cur_day[1]:.1f}, "
            f"{round(cur_day[2]*0.55,1):.1f}, {round(cur_day[2]*1.32,1):.1f}, {cur_day[2]:.1f}, "
            # rms_voltage min/max/moy L1..L3
            f"{round(volt_day-8,1):.1f}, {round(volt_day+6,1):.1f}, {volt_day:.1f}, "
            f"{round(volt_day-9,1):.1f}, {round(volt_day+5,1):.1f}, {round(volt_day-0.5,1):.1f}, "
            f"{round(volt_day-7,1):.1f}, {round(volt_day+7,1):.1f}, {round(volt_day+0.5,1):.1f}, "
            # active_power min/max/moy L1..L3
            f"{round(ap_day[0]*0.35,1):.1f}, {round(ap_day[0]*1.4,1):.1f}, {ap_day[0]:.1f}, "
            f"{round(ap_day[1]*0.35,1):.1f}, {round(ap_day[1]*1.4,1):.1f}, {ap_day[1]:.1f}, "
            f"{round(ap_day[2]*0.35,1):.1f}, {round(ap_day[2]*1.4,1):.1f}, {ap_day[2]:.1f}, "
            # en_reactive + cons, L1..L3
            f"{cumul_r[0]}, {round(c[0]*0.18,2)}, {cumul_r[1]}, {round(c[1]*0.18,2)}, {cumul_r[2]}, {round(c[2]*0.18,2)}, "
            # en_apparent L1..L3
            f"{cumul_a[0]}, {cumul_a[1]}, {cumul_a[2]}, "
            # cons_en_apparent L1..L3
            f"{round(c[0]/cf,2)}, {round(c[1]/cf,2)}, {round(c[2]/cf,2)}, "
            # fp min/max/moy L1..L3
            f"{cf_min:.3f}, {cf_max:.3f}, {cf_day:.3f}, "
            f"{round(cf_min-0.01,3):.3f}, {round(cf_max-0.01,3):.3f}, {round(cf_day-0.005,3):.3f}, "
            f"{round(cf_min+0.01,3):.3f}, {round(cf_max+0.01,3):.3f}, {round(cf_day+0.005,3):.3f}, "
            # apparent_power min/max/moy L1..L3
            f"{round(app_day[0]*0.35,1):.1f}, {round(app_day[0]*1.4,1):.1f}, {app_day[0]:.1f}, "
            f"{round(app_day[1]*0.35,1):.1f}, {round(app_day[1]*1.4,1):.1f}, {app_day[1]:.1f}, "
            f"{round(app_day[2]*0.35,1):.1f}, {round(app_day[2]*1.4,1):.1f}, {app_day[2]:.1f}, "
            # reactive_power min/max/moy L1..L3
            f"{round(rp_day[0]*0.35,1):.1f}, {round(rp_day[0]*1.4,1):.1f}, {rp_day[0]:.1f}, "
            f"{round(rp_day[1]*0.35,1):.1f}, {round(rp_day[1]*1.4,1):.1f}, {rp_day[1]:.1f}, "
            f"{round(rp_day[2]*0.35,1):.1f}, {round(rp_day[2]*1.4,1):.1f}, {rp_day[2]:.1f}, "
            # THDC max/min/moy L1..L3
            f"{thdc_max:.2f}, {thdc_min:.2f}, {thdc_day:.2f}, "
            f"{round(thdc_max-0.2,2):.2f}, {round(thdc_min-0.2,2):.2f}, {round(thdc_day-0.1,2):.2f}, "
            f"{round(thdc_max+0.2,2):.2f}, {round(thdc_min+0.2,2):.2f}, {round(thdc_day+0.1,2):.2f}, "
            # battery_level
            f"{ri(180, 240)})"
        )
        ep_rows.append(row)

out(",\n".join(ep_rows) + ";")
out("")

# ── 7. ARCHIVE_WM_J ───────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 7. ARCHIVE_WM_J — 4 devices × 30 jours")
out("-- ────────────────────────────────────────────")

# base daily conso in liters
wm_archive = {
    6: dict(base=3500, start_idx=125000, batt_base=218),
    7: dict(base=8000, start_idx=380000, batt_base=205),
    8: dict(base=2000, start_idx=88000,  batt_base=222),
    9: dict(base=1200, start_idx=54000,  batt_base=215),
}

out("INSERT INTO archive_wm_j (id_device, `date`, `index`, conso, reverse_conso, battery_level) VALUES")
wm_rows = []
for dev_id, p in wm_archive.items():
    idx = p['start_idx']
    for d_off in range(30):
        cur_date = start_date + timedelta(days=d_off)
        f = day_factor(cur_date)
        conso = int(p['base'] * f + random.uniform(-150, 150))
        if conso < 100: conso = 100
        idx += conso
        rev = ri(0, 2)
        batt = p['batt_base'] + ri(-15, 15)
        wm_rows.append(f"  ({dev_id}, '{cur_date} 00:00:00', {idx}, {conso}, {rev}, {batt})")
out(",\n".join(wm_rows) + ";")
out("")

# ── 8. ARCHIVE_GM_J ───────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 8. ARCHIVE_GM_J — 3 devices × 30 jours")
out("-- ────────────────────────────────────────────")

gm_archive = {
    10: dict(base=1200, start_idx=92000, min_d=0.5, max_d=22.0, avg_d=9.0, batt=210),
    11: dict(base=800,  start_idx=61000, min_d=0.3, max_d=25.0, avg_d=11.0, batt=198),
    12: dict(base=250,  start_idx=18500, min_d=0.1, max_d=9.0,  avg_d=3.5,  batt=225),
}

out("INSERT INTO archive_gm_j (id_device, `date`, `index`, conso, reverse_conso, battery_level, min_debit_per_min, max_debit_per_min, avg_debit_per_min, crc) VALUES")
gm_rows = []
for dev_id, p in gm_archive.items():
    idx = p['start_idx']
    for d_off in range(30):
        cur_date = start_date + timedelta(days=d_off)
        f = day_factor(cur_date)
        conso = int(p['base'] * f + random.uniform(-50, 50))
        if conso < 20: conso = 20
        idx += conso
        rev = ri(0, 1)
        batt = p['batt'] + ri(-20, 10)
        min_d = round(p['min_d'] + random.uniform(-0.1, 0.1), 2)
        max_d = round(p['max_d'] * f + random.uniform(-1, 1), 2)
        avg_d = round(p['avg_d'] * f + random.uniform(-0.5, 0.5), 2)
        gm_rows.append(f"  ({dev_id}, '{cur_date} 00:00:00', {idx}, {conso}, {rev}, {batt}, {min_d}, {max_d}, {avg_d}, 0)")
out(",\n".join(gm_rows) + ";")
out("")

# ── 9. FUEL_CONSUMPTION ───────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 9. FUEL_CONSUMPTION — 3 véhicules × 30 jours")
out("-- ────────────────────────────────────────────")

# vehicle profiles
fuel_profiles = {
    13: dict(fuel_type='Diesel', base_km=180, base_l=35, tank=80,  batt=95, mileage=42500),
    14: dict(fuel_type='Diesel', base_km=320, base_l=65, tank=200, batt=98, mileage=185000),
    15: dict(fuel_type='Essence', base_km=120, base_l=18, tank=50, batt=92, mileage=28000),
}

# CO2 factors: Diesel 2.65 kg/L, Essence 2.31 kg/L
co2_factor = {'Diesel': 2.65, 'Essence': 2.31}
# price per liter TND: Diesel 2.15, Essence 2.45
fuel_price = {'Diesel': 2.15, 'Essence': 2.45}

out("INSERT INTO fuel_consumption (device_id, `date`, fuel_type, mileage_km, quantity_added_liters, consumption_liters, consumption_percentage, tank_capacity_liters, carbone, cost) VALUES")
fuel_rows = []
for dev_id, p in fuel_profiles.items():
    mileage = p['mileage']
    for d_off in range(30):
        cur_date = start_date + timedelta(days=d_off)
        f = day_factor(cur_date)
        km = int(p['base_km'] * f + random.uniform(-15, 15))
        if km < 5: km = 5
        mileage += km
        liters = round(p['base_l'] * f + random.uniform(-3, 3), 2)
        if liters < 2: liters = 2.0
        # added liters (refueling every ~7 days)
        added = round(liters * random.choice([0, 0, 0, 0, 1, 0, 0]) * (random.uniform(0.8, 1.2)), 2)
        pct = round((liters / p['tank']) * 100, 2)
        co2 = round(liters * co2_factor[p['fuel_type']], 3)
        cost = round(liters * fuel_price[p['fuel_type']], 3)
        fuel_rows.append(
            f"  ({dev_id}, '{cur_date}', '{p['fuel_type']}', {mileage}, {added}, {liters}, {pct}, {p['tank']}, {co2}, {cost})"
        )
out(",\n".join(fuel_rows) + ";")
out("")

# ── 10. ALERTS ───────────────────────────────────────────────────────────────
out("-- ────────────────────────────────────────────")
out("-- 10. ALERTS — ~55 alertes variées")
out("-- ────────────────────────────────────────────")

out("INSERT INTO alerts (`date`, id_device, `type`, valeur, diff, val_min, val_max, temps_infraction, message, message_en, recommendation_en, recommendation_fr, `from`) VALUES")

alert_defs = []

# COSFI_LOW — device 2 (Atelier, mauvais cosfi)
for d_off in [2, 9, 16, 23]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(8,20), minutes=ri(0,59))
    val = round(random.uniform(0.78, 0.82), 3)
    alert_defs.append((dt, 2, 'COSFI_LOW', val, round(val-0.85, 3), 0.85, 1.0, ri(15,120),
        f"Facteur de puissance trop bas: {val} (seuil 0.85)",
        f"Power factor too low: {val} (threshold 0.85)",
        "Install capacitor banks to compensate reactive power. Schedule maintenance.",
        "Installer des condensateurs pour compenser l'énergie réactive. Planifier la maintenance.",
        'ELEC-ATELIER'))

# THD_HIGH — device 2 (Atelier)
for d_off in [3, 11, 18, 25]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(6,22), minutes=ri(0,59))
    val = round(random.uniform(14.5, 16.8), 2)
    alert_defs.append((dt, 2, 'THD_HIGH', val, round(val-10, 2), 0, 10.0, ri(10,90),
        f"Distorsion harmonique élevée: {val}% (seuil 10%)",
        f"High harmonic distortion: {val}% (threshold 10%)",
        "Check variable speed drives and non-linear loads. Consider harmonic filters.",
        "Vérifier les variateurs de fréquence et charges non linéaires. Envisager des filtres harmoniques.",
        'ELEC-ATELIER'))

# THD_HIGH — device 1 (Admin, picots)
for d_off in [5, 19]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(9,18), minutes=ri(0,59))
    val = round(random.uniform(9.2, 11.5), 2)
    alert_defs.append((dt, 1, 'THD_HIGH', val, round(val-8, 2), 0, 8.0, ri(5,30),
        f"THD ponctuel: {val}%",
        f"Punctual THD spike: {val}%",
        "Check UPS, servers, and IT equipment. Apply filtering if persistent.",
        "Vérifier UPS, serveurs et équipements IT. Appliquer un filtre si persistant.",
        'ELEC-ADMIN-GM'))

# OVERCONSUMPTION — device 2 (Atelier)
for d_off in [4, 12, 21, 26]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(7,19), minutes=ri(0,59))
    val = round(random.uniform(18500, 22000), 0)
    alert_defs.append((dt, 2, 'OVERCONSUMPTION', val, round(val-15000, 0), 0, 15000, ri(20,180),
        f"Consommation excessive: {val:.0f} W (seuil 15 kW)",
        f"Excessive consumption: {val:.0f} W (threshold 15 kW)",
        "Identify high-load equipment. Check for process anomalies or unauthorized usage.",
        "Identifier les équipements haute charge. Vérifier anomalies process ou usages non autorisés.",
        'ELEC-ATELIER'))

# OVERCONSUMPTION — device 1 (Admin, climatisation été)
for d_off in [7, 16, 24]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(11,16), minutes=ri(0,59))
    val = round(random.uniform(8200, 9800), 0)
    alert_defs.append((dt, 1, 'OVERCONSUMPTION', val, round(val-7000, 0), 0, 7000, ri(15,60),
        f"Pic de consommation: {val:.0f} W",
        f"Consumption peak: {val:.0f} W",
        "Optimize HVAC scheduling. Implement demand response strategy.",
        "Optimiser la planification CVC. Mettre en place une stratégie d'effacement.",
        'ELEC-ADMIN-GM'))

# LEAK — water device 9 (Zone Tech)
for d_off in [1, 8, 15, 22, 29]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(0,23), minutes=ri(0,59))
    val = round(random.uniform(25, 85), 1)
    alert_defs.append((dt, 9, 'LEAK', val, val, 0, 15.0, ri(5,60),
        f"Fuite détectée: débit anormal {val} L/h",
        f"Leak detected: abnormal flow {val} L/h",
        "Inspect pipes at the technical area. Locate and repair the leak immediately.",
        "Inspecter les canalisations de la zone technique. Localiser et réparer la fuite immédiatement.",
        'EAU-ZTECH'))

# LEAK — water device 7 (Atelier)
for d_off in [10, 20]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(1,6), minutes=ri(0,59))
    val = round(random.uniform(40, 120), 1)
    alert_defs.append((dt, 7, 'LEAK', val, val, 0, 20.0, ri(10,120),
        f"Fuite circuit process: {val} L/h en dehors des heures de production",
        f"Process circuit leak: {val} L/h outside production hours",
        "Close isolation valves on inactive process lines. Inspect joints and valves.",
        "Fermer les vannes des lignes process inactives. Inspecter joints et robinetterie.",
        'EAU-ATELIER'))

# FRAUD — water device 8 (Résidence)
for d_off in [14, 27]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(2,5), minutes=ri(0,59))
    val = round(random.uniform(200, 450), 1)
    alert_defs.append((dt, 8, 'FRAUD', val, val, 0, 0, ri(30,180),
        f"Débit inverse détecté: {val} L — possible fraude ou retour réseau",
        f"Reverse flow detected: {val} L — possible tampering or network backflow",
        "Inspect check valve. Verify meter integrity and report to utility if persistent.",
        "Inspecter le clapet anti-retour. Vérifier l'intégrité du compteur et signaler au distributeur.",
        'EAU-RESIDENCE'))

# BATTERY_LOW — various devices
batt_low_cases = [
    (11, 6,  'GAZ-ATELIER'),
    (7,  13, 'EAU-ATELIER'),
    (2,  17, 'ELEC-ATELIER'),
    (9,  20, 'EAU-ZTECH'),
    (11, 24, 'GAZ-ATELIER'),
]
for dev_id, d_off, src in batt_low_cases:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(6,10), minutes=ri(0,59))
    val = ri(15, 35)
    alert_defs.append((dt, dev_id, 'BATTERY_LOW', val, None, None, 50, ri(0,10),
        f"Batterie faible: niveau {val}% — remplacement nécessaire",
        f"Low battery: level {val}% — replacement needed",
        "Replace battery within 72h to avoid data loss.",
        "Remplacer la batterie dans les 72h pour éviter toute perte de données.",
        src))

# REVERSE_FLOW — gas device 11
for d_off in [9, 22]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(22,23), minutes=ri(0,59))
    val = round(random.uniform(5, 20), 1)
    alert_defs.append((dt, 11, 'REVERSE_FLOW', val, -val, 0, 0, ri(2,15),
        f"Débit inverse gaz: {val} m³/h — possible retour process",
        f"Reverse gas flow: {val} m³/h — possible process backflow",
        "Check furnace isolation valves. Verify burner shut-off sequence.",
        "Vérifier les vannes d'isolation du four. Contrôler la séquence d'arrêt des brûleurs.",
        'GAZ-ATELIER'))

# HIGH_CONSUMPTION_WATER — device 7 (Atelier, process intensif)
for d_off in [3, 10, 17, 24]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(9,15), minutes=ri(0,59))
    val = round(random.uniform(9500, 12000), 0)
    alert_defs.append((dt, 7, 'OVERCONSUMPTION', val, round(val-8000, 0), 0, 8000, ri(20,120),
        f"Consommation eau élevée: {val:.0f} L (seuil 8000 L/période)",
        f"High water consumption: {val:.0f} L (threshold 8000 L/period)",
        "Audit process water usage. Check cooling tower blowdown and leaks.",
        "Auditer l'utilisation d'eau process. Vérifier la purge de la tour de refroidissement et les fuites.",
        'EAU-ATELIER'))

# FUEL HIGH CONSUMPTION — device 14 (Camion)
for d_off in [5, 14, 22]:
    dt = datetime(2026, 3, 15) + timedelta(days=d_off, hours=ri(7,18), minutes=ri(0,59))
    val = round(random.uniform(75, 95), 2)
    alert_defs.append((dt, 14, 'OVERCONSUMPTION', val, round(val-60, 2), 0, 60, ri(30,240),
        f"Consommation carburant élevée: {val} L (seuil 60 L/jour)",
        f"High fuel consumption: {val} L (threshold 60 L/day)",
        "Check tire pressure, engine health, and load weight. Review route efficiency.",
        "Vérifier pression pneus, état moteur et charge. Analyser l'efficacité de la route.",
        'FUEL-VEH02'))

# Build INSERT
alert_rows = []
for a in alert_defs:
    dt_str = a[0].strftime('%Y-%m-%d %H:%M:%S')
    dev_id = a[1]
    atype  = a[2]
    valeur = a[3]
    diff   = a[4]
    val_min = a[5]
    val_max = a[6]
    temps  = a[7]
    msg    = a[8].replace("'", "\\'")
    msg_en = a[9].replace("'", "\\'")
    rec_en = a[10].replace("'", "\\'")
    rec_fr = a[11].replace("'", "\\'")
    src    = a[12]

    valeur_s = f"{valeur}" if valeur is not None else "NULL"
    diff_s   = f"{diff}"   if diff   is not None else "NULL"
    vmin_s   = f"{val_min}" if val_min is not None else "NULL"
    vmax_s   = f"{val_max}" if val_max is not None else "NULL"

    alert_rows.append(
        f"  ('{dt_str}', {dev_id}, '{atype}', {valeur_s}, {diff_s}, {vmin_s}, {vmax_s}, {temps}, "
        f"'{msg}', '{msg_en}', '{rec_en}', '{rec_fr}', '{src}')"
    )

out(",\n".join(alert_rows) + ";")
out("")
out("SET FOREIGN_KEY_CHECKS = 1;")
out("")
out("-- ── Statistics summary ──────────────────────────────────────────")
out(f"-- Total rows: espace=5, device=15, rt_en_p=5, rt_wm=4, rt_gm=3")
out(f"-- archive_en_p_j=150, archive_wm_j=120, archive_gm_j=90, fuel_consumption=90")
out(f"-- alerts={len(alert_defs)}")
out("-- ─────────────────────────────────────────────────────────────────")

import sys, os
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_seed.sql')
with open(out_path, 'w', encoding='utf-8') as fout:
    fout.write("\n".join(lines))
print(f"Written {len(lines)} lines to {out_path}")
