"""Configuration des domaines et résolution des libellés de devices."""
from __future__ import annotations

import logging
import time as _time

from sqlalchemy import text

logger = logging.getLogger('aria.reco_engine')

_device_label_cache: dict[str, tuple[str, float]] = {}  # key → (label, timestamp)
_DEVICE_LABEL_CACHE_TTL = 300.0  # 5 minutes

# Préfixes lisibles par domaine quand aucune table de correspondance n'existe
_DOMAIN_DEVICE_PREFIX = {
    'energy': 'Compteur Élec.',
    'water' : 'Compteur Eau',
    'gas'   : 'Compteur Gaz',
    'fuel'  : 'Véhicule',
}


def _resolve_device_label(engine, device_id: str, domain: str = '') -> str:
    """Résout device_id → nom lisible.

    Stratégie double :
    1. Via device.adresse  (devices enregistrés avec adresse = id_device, ex: 1001, 1002)
    2. Via device.id       (devices avec adresse=0 mais id = device_id, ex: 6001, 6101, 6201)
    Formate proprement l'ID brut avec préfixe domaine si aucune correspondance.
    """
    if not device_id:
        return 'ensemble du site'
    cache_key = f'{domain}:{device_id}'
    cached = _device_label_cache.get(cache_key)
    if cached and (_time.monotonic() - cached[1]) < _DEVICE_LABEL_CACHE_TTL:
        return cached[0]

    base_id = device_id.split('_')[0] if '_' in device_id else device_id
    numeric_id = int(base_id) if base_id.isdigit() else -1

    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT d.nom, e.nom AS espace
                FROM device d
                LEFT JOIN espace e ON d.id_espace = e.id
                WHERE (d.adresse != 0 AND CAST(d.adresse AS CHAR) = :dev)
                   OR (d.id = :numeric_id)
                ORDER BY CASE WHEN d.adresse != 0 THEN 0 ELSE 1 END
                LIMIT 1
            """), {'dev': base_id, 'numeric_id': numeric_id}).fetchone()
        if row and row[0]:
            phase = device_id.split('_')[1] if '_' in device_id else None
            label = f"{row[0]} ({row[1] or 'Zone inconnue'})"
            if phase:
                label += f" — phase {phase}"
            _device_label_cache[cache_key] = (label, _time.monotonic())
            return label
    except Exception:
        pass

    # Formatage lisible depuis l'ID + préfixe domaine
    prefix = _DOMAIN_DEVICE_PREFIX.get(domain, 'Capteur')
    parts  = device_id.split('_')
    if len(parts) == 2:
        label = f"{prefix} #{parts[0]} — Phase {parts[1]}"
    else:
        label = f"{prefix} #{device_id}"
    _device_label_cache[cache_key] = (label, _time.monotonic())
    return label


# ── Configuration domaines ────────────────────────────────────────────────────
DOMAIN_CONFIG: dict[str, dict] = {
    'energy': {
        'table'         : 'daily_energy',
        'value_col'     : 'cons_en',
        'group_phases'  : True,
        'unit'          : 'kWh',
        'cost_per_unit' : 0.096,
        'off_peak_start': 22,
        'off_peak_end'  : 6,
        'label'         : 'Électricité',
    },
    'water': {
        'table'         : 'daily_water',
        'value_col'     : 'conso_m3',
        'group_phases'  : False,
        'unit'          : 'm³',
        'cost_per_unit' : 0.75,
        'off_peak_start': 1,
        'off_peak_end'  : 5,
        'label'         : 'Eau',
    },
    'gas': {
        'table'         : 'daily_gas',
        'value_col'     : 'conso_m3',
        'group_phases'  : False,
        'unit'          : 'm³',
        'cost_per_unit' : 0.45,
        'off_peak_start': 22,
        'off_peak_end'  : 6,
        'label'         : 'Gaz',
    },
    'fuel': {
        'table'         : 'daily_fuel',
        'value_col'     : 'consumption',
        'group_phases'  : False,
        'unit'          : 'L',
        'cost_per_unit' : 1.92,
        'off_peak_start': None,
        'off_peak_end'  : None,
        'label'         : 'Carburant',
    },
}
