# ══════════════════════════════════════════════════════════════════════════
# PARTIE CHART — conversion des sorties d'outils MCP en configs Chart.js
# ══════════════════════════════════════════════════════════════════════════
import json
import logging

logger = logging.getLogger('aria.chart_builder')


def _parse(raw: str) -> dict | None:
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) and d.get('status') in ('ok', 'success') else None
    except Exception:
        return None


def _label(row: dict) -> str:
    for k in ('capteur_nom', 'zone', 'name', 'id_device'):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return '?'


def build_charts(tool_name: str, raw_output: str) -> list[dict]:
    """Convertit la sortie brute d'un outil MCP en liste de configs Chart.js."""
    data = _parse(raw_output)
    if not data:
        logger.debug(f'[CHART] {tool_name}: parse failed (status not ok/success)')
        return []
    try:
        builders = {
            'wm_analysis'      : _chart_wm,
            'energy_analysis'  : _chart_energy,
            'gm_analysis'      : _chart_gm,
            'fuel_analysis'    : _chart_fuel,
            'thl_analysis'     : _chart_thl,
            'realtime_data'    : _chart_realtime,
            'anomaly_detection': _chart_anomaly,
            'wm_trend'         : _chart_trend,
            'energy_trend'     : _chart_trend,
            'gm_trend'         : _chart_trend,
            'fuel_trend'       : _chart_trend,
        }
        fn = builders.get(tool_name)
        if not fn:
            return []
        charts = fn(data)
        logger.info(f'[CHART] {tool_name} → {len(charts)} graphique(s)')
        return charts
    except Exception as e:
        logger.warning(f'[CHART] {tool_name}: {e}', exc_info=True)
        return []


# ── Helpers ──────────────────────────────────────────────────────────────────

def _bar(title: str, labels: list, datasets: list, unit: str = '') -> dict:
    return {'type': 'bar', 'title': title, 'labels': labels,
            'datasets': datasets, 'unit': unit}

def _doughnut(title: str, labels: list, datasets: list, unit: str = '') -> dict:
    return {'type': 'doughnut', 'title': title, 'labels': labels,
            'datasets': datasets, 'unit': unit}

def _line(title: str, labels: list, datasets: list, unit: str = '') -> dict:
    return {'type': 'line', 'title': title, 'labels': labels,
            'datasets': datasets, 'unit': unit}

def _ds(label: str, data: list, color: str) -> dict:
    return {'label': label, 'data': data, 'color': color}

def _nonzero(values: list) -> bool:
    return any(isinstance(v, (int, float)) and v != 0 for v in values)

def _fval(row: dict, *cols) -> float:
    """Première valeur non-None parmi les colonnes, convertie en float."""
    for c in cols:
        v = row.get(c)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0

# rétro-compat pour l'ancien nom utilisé dans les tests
_first_val = _fval


# ── Builders par outil ────────────────────────────────────────────────────────

def _chart_wm(data: dict) -> list[dict]:
    rows = data.get('analysis', [])
    if not rows:
        return []
    labels = [_label(r) for r in rows]
    # consommation_nette_m3 peut être string (résultat SUM MySQL sur certains drivers)
    values = [_fval(r, 'consommation_nette_m3', 'total_m3', 'avg_debit') for r in rows]
    if not _nonzero(values):
        return []
    period = data.get('period', '')
    return [_bar(f'Consommation eau — {period}', labels,
                 [_ds('m³', values, '#0ea5e9')], 'm³')]


def _chart_energy(data: dict) -> list[dict]:
    rows = data.get('analysis', [])
    if not rows:
        return []
    labels = [_label(r) for r in rows]
    charts = []
    period = data.get('period', '')

    # Graphique kWh par phase — groupé si plusieurs capteurs
    phase_cols = ['total_kWh_L1', 'total_kWh_L2', 'total_kWh_L3']
    phase_vals = [[_fval(r, c) for r in rows] for c in phase_cols]
    has_phases = any(_nonzero(v) for v in phase_vals)

    if has_phases and len(rows) > 1:
        # Plusieurs capteurs → groupé L1/L2/L3 par capteur
        colors = ['#0ea5e9', '#10b981', '#f59e0b']
        datasets = [_ds(c.replace('total_', ''), v, colors[i])
                    for i, (c, v) in enumerate(zip(phase_cols, phase_vals))
                    if _nonzero(v)]
        charts.append(_bar(f'Énergie par phase — {period}', labels, datasets, 'kWh'))
    elif has_phases:
        # 1 seul capteur → une barre par phase
        phase_labels = ['L1', 'L2', 'L3']
        vals = [_fval(rows[0], c) for c in phase_cols]
        charts.append(_bar(f'Énergie par phase — {period}', phase_labels,
                           [_ds(labels[0], vals, '#0ea5e9')], 'kWh'))
    else:
        # Fallback : chercher colonnes kWh génériques
        for col in ('cons_en_total', 'cons_en_L1', 'cons_en', 'total_kWh'):
            vals = [_fval(r, col) for r in rows]
            if _nonzero(vals):
                charts.append(_bar(f'Énergie — {period}', labels,
                                   [_ds('kWh', vals, '#0ea5e9')], 'kWh'))
                break

    # Doughnut cosfi uniquement si données réelles (non nulles)
    cosfi_cols = ['avg_cosfi_L1', 'avg_cosfi_L2', 'avg_cosfi_L3',
                  'cosfi_avg', 'cosfi_L1', 'cosfi']
    cosfi = [_fval(r, *cosfi_cols) for r in rows]
    if _nonzero(cosfi):
        charts.append(_doughnut('Facteur de puissance (cosfi)', labels,
                                [_ds('cosfi', cosfi, '#10b981')]))

    return charts[:2]


def _chart_gm(data: dict) -> list[dict]:
    rows = data.get('analysis', [])
    if not rows:
        return []
    labels = [_label(r) for r in rows]
    values = [_fval(r, 'consommation_nette_m3', 'total_m3', 'avg_debit_min') for r in rows]
    if not _nonzero(values):
        return []
    period = data.get('period', '')
    return [_bar(f'Consommation gaz — {period}', labels,
                 [_ds('m³', values, '#f59e0b')], 'm³')]


def _chart_fuel(data: dict) -> list[dict]:
    rows = data.get('analysis', [])
    if not rows:
        return []
    labels = [_label(r) for r in rows]
    charts = []
    period = data.get('period', '')

    for col in ('total_L', 'avg_L', 'total_fuel', 'avg_fuel', 'fuel_consumed'):
        values = [_fval(r, col) for r in rows]
        if _nonzero(values):
            charts.append(_bar(f'Carburant — {period}', labels,
                               [_ds('Litres', values, '#e74c3c')], 'L'))
            break

    # Graphique distance si disponible
    km_vals = [_fval(r, 'total_km', 'avg_km') for r in rows]
    if _nonzero(km_vals):
        charts.append(_bar(f'Distance parcourue — {period}', labels,
                           [_ds('km', km_vals, '#8b5cf6')], 'km'))

    return charts[:2]


def _chart_thl(data: dict) -> list[dict]:
    rows = data.get('analysis', [])
    if not rows:
        return []
    labels = [_label(r) for r in rows]
    period = data.get('period', '')
    charts = []

    temps = [_fval(r, 't_avg', 'temp_avg', 'temperature_avg') for r in rows]
    if _nonzero(temps):
        charts.append(_bar(f'Température — {period}', labels,
                           [_ds('°C', temps, '#e74c3c')], '°C'))

    humid = [_fval(r, 'h_avg', 'humidity_avg', 'hum_avg') for r in rows]
    if _nonzero(humid):
        charts.append(_bar(f'Humidité — {period}', labels,
                           [_ds('%', humid, '#0ea5e9')], '%'))

    return charts[:2]


def _normalize_battery(raw) -> float:
    """Convertit le niveau batterie LoRaWAN (0–254) en pourcentage 0–100.
    Spec LoRaWAN : 0=alim externe, 1=min, 254=max, 255=inconnu."""
    v = float(raw)
    if v > 100:
        return round(max(0.0, min(100.0, v / 254 * 100)), 1)
    return max(0.0, min(100.0, v))


def _chart_realtime(data: dict) -> list[dict]:
    capteurs = data.get('capteurs', [])
    bat = [
        (_label(c), _normalize_battery(c['battery_level']))
        for c in capteurs
        if c.get('battery_level') is not None
    ]
    if not bat:
        return []
    labels, values = zip(*bat)
    colors = ['#10b981' if v >= 50 else '#f59e0b' if v >= 20 else '#e74c3c'
              for v in values]
    return [{
        'type'    : 'bar',
        'title'   : 'Batterie des capteurs',
        'labels'  : list(labels),
        'datasets': [{'label': 'Batterie (%)', 'data': list(values), 'colors': colors}],
        'unit'    : '%',
        'yMax'    : 100,
    }]


def _chart_trend(data: dict) -> list[dict]:
    series = data.get('series', [])
    if not series:
        return []

    # Axe X : union ordonnée des buckets vus (au cas où un capteur aurait
    # des trous), dans l'ordre d'apparition.
    labels: list = []
    seen = set()
    for s in series:
        for p in s.get('points', []):
            t = p.get('t')
            if t not in seen:
                seen.add(t)
                labels.append(t)
    if not labels:
        return []

    colors = ['#0ea5e9', '#10b981', '#f59e0b', '#e74c3c', '#8b5cf6', '#06b6d4']
    datasets = []
    for i, s in enumerate(series):
        by_label = {p['t']: p['v'] for p in s.get('points', [])}
        datasets.append(_ds(s.get('device', '?'),
                             [by_label.get(l, 0) for l in labels],
                             colors[i % len(colors)]))

    granularity = 'horaire' if data.get('granularity') == 'hour' else 'journalière'
    title = f"Courbe {data.get('label', '')} — évolution {granularity} ({data.get('period', '')})"
    return [_line(title, labels, datasets, data.get('unit', ''))]


def _chart_anomaly(data: dict) -> list[dict]:
    summary = data.get('summary', {})
    cats = {
        'Valeurs extrêmes': len(summary.get('extreme_values', [])),
        'Capteurs'        : len(summary.get('sensor_issues', [])),
        'Fluides'         : len(summary.get('fluid_alerts', [])),
        'Énergie'         : len(summary.get('energy_alerts', [])),
        'Inactifs'        : len(summary.get('inactive_sensors', [])),
    }
    pairs = [(k, v) for k, v in cats.items() if v > 0]
    if not pairs:
        return []
    labels, values = zip(*pairs)
    colors = ['#e74c3c', '#f59e0b', '#0ea5e9', '#f97316', '#8b5cf6']
    return [{
        'type'    : 'doughnut',
        'title'   : f'Anomalies — {data.get("period", "")}',
        'labels'  : list(labels),
        'datasets': [{'label': 'Anomalies', 'data': list(values), 'colors': colors[:len(values)]}],
        'unit'    : '',
    }]
