"""
ARIA MCP — Analyse intelligente des résultats de détection d'anomalies ML.

Expose la table ad_results (résultats HotStart/ColdStart) avec 5 modes d'analyse :

  summary     — Vue globale : taux d'anomalies, health scores par domaine/device,
                              pire device, timestamp dernière anomalie.
  top_devices — Classement des devices les plus problématiques avec score de santé
                composite (taux × score × récence).
  trend       — Évolution quotidienne + direction (amélioration/dégradation) calculée
                par régression linéaire sur les 7 derniers jours.
  incidents   — Clustering temporel : anomalies consécutives (gap ≤ 3h) regroupées
                en incidents avec durée, sévérité max, device(s) impacté(s).
  correlation — Précision rétroactive du forecasting Chronos : recall, lead-time moyen,
                taux de fausses alertes — Chronos avait-il prévu les anomalies réelles ?
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from mcp_server.db.connection import engine
from mcp_server.tools._helpers import ok, err
from sqlalchemy import text

logger = logging.getLogger('aria.tools.ad_analysis')

_VALID_DOMAINS  = {'energy', 'water', 'gas', 'fuel', 'all'}
_VALID_MODES    = {'summary', 'top_devices', 'trend', 'incidents', 'correlation'}
_DOMAIN_UNITS   = {'energy': 'kWh', 'water': 'm³', 'gas': 'm³', 'fuel': 'L'}
_DOMAIN_LABELS  = {'energy': 'Énergie', 'water': 'Eau', 'gas': 'Gaz', 'fuel': 'Carburant'}

_PERIOD_MAP: dict[str, Optional[str]] = {
    '24h' : 'NOW() - INTERVAL 24 HOUR',
    '7j'  : 'NOW() - INTERVAL 7 DAY',
    '30j' : 'NOW() - INTERVAL 30 DAY',
    '90j' : 'NOW() - INTERVAL 90 DAY',
    'tout': None,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _since_clause(period: str) -> str:
    """Retourne la condition WHERE pour la période, ou '' si 'tout'."""
    expr = _PERIOD_MAP.get(period, _PERIOD_MAP['7j'])
    return f"AND data_ts >= {expr}" if expr else ""


def _domain_clause(domain: str) -> str:
    return "" if domain == 'all' else "AND domain = :domain"


def _health_score(anomaly_rate_pct: float, peak_score: float,
                  hours_since_last: Optional[float]) -> int:
    """
    Score de santé 0–100 par device.
      100 = parfait (aucune anomalie)
      0   = critique (anomalies fréquentes, score élevé, très récent)

    Trois composantes pondérées :
      - Taux d'anomalie   (50 %) — impact principal
      - Score de pic      (30 %) — intensité de la pire anomalie
      - Récence           (20 %) — anomalie dans les 24h = pénalité max
    """
    rate   = min(anomaly_rate_pct / 100, 1.0)
    score  = min(peak_score or 0.0, 1.0)
    recent = 1.0 if (hours_since_last is not None and hours_since_last < 24) else 0.0
    penalty = rate * 0.50 + score * 0.30 + recent * 0.20
    return max(0, min(100, round((1.0 - penalty) * 100)))


def _health_label(score: int) -> str:
    if score >= 80: return 'BON'
    if score >= 55: return 'ATTENTION'
    if score >= 30: return 'DÉGRADÉ'
    return 'CRITIQUE'


def _linear_trend(values: list[float]) -> float:
    """Pente de régression linéaire (unités/step). Positive = dégradation."""
    n = len(values)
    if n < 2:
        return 0.0
    sx  = sum(range(n))
    sy  = sum(values)
    sxy = sum(i * v for i, v in enumerate(values))
    sxx = sum(i * i for i in range(n))
    denom = n * sxx - sx * sx
    return 0.0 if denom == 0 else (n * sxy - sx * sy) / denom


def _cluster_incidents(rows: list[dict], gap_hours: int = 3) -> list[dict]:
    """
    Regroupe les anomalies consécutives (écart ≤ gap_hours) en incidents.
    Retourne une liste d'incidents avec {start, end, duration_h, peak_score,
    anomaly_count, items}.
    """
    if not rows:
        return []

    def _ts(r) -> datetime:
        v = r['data_ts']
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v))

    rows = sorted(rows, key=lambda r: (_ts(r), r.get('item_id', '')))
    incidents: list[dict] = []
    group: list[dict] = [rows[0]]

    for r in rows[1:]:
        gap = (_ts(r) - _ts(group[-1])).total_seconds() / 3600
        if gap <= gap_hours:
            group.append(r)
        else:
            incidents.append(_summarise_incident(group))
            group = [r]
    incidents.append(_summarise_incident(group))
    return incidents


def _summarise_incident(group: list[dict]) -> dict:
    def _ts(r):
        v = r['data_ts']
        return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))

    start    = _ts(group[0])
    end      = _ts(group[-1])
    duration = round((end - start).total_seconds() / 3600, 1)
    scores   = [r.get('anomaly_score') or 0 for r in group]
    items    = sorted({r.get('item_id', '?') for r in group})
    domains  = sorted({r.get('domain', '?') for r in group})
    peak     = round(max(scores), 3)
    severity = 'HIGH' if peak > 0.8 else ('MEDIUM' if peak > 0.5 else 'LOW')
    return {
        'start':         str(start),
        'end':           str(end),
        'duration_h':    duration,
        'anomaly_count': len(group),
        'peak_score':    peak,
        'severity':      severity,
        'domains':       domains,
        'items':         items[:5],   # max 5 devices pour la lisibilité
    }


# ── Requêtes SQL ───────────────────────────────────────────────────────────────

def _q_summary(domain: str, period: str) -> tuple[str, dict]:
    params: dict = {}
    if domain != 'all':
        params['domain'] = domain
    sql = f"""
        SELECT
            domain, strategy,
            COUNT(*)                                                   AS total_points,
            SUM(is_anomaly)                                            AS anomaly_count,
            ROUND(AVG(CAST(is_anomaly AS DECIMAL(5,4))) * 100, 2)     AS anomaly_rate_pct,
            ROUND(MAX(anomaly_score), 3)                               AS peak_score,
            ROUND(AVG(CASE WHEN is_anomaly = 1 THEN anomaly_score END), 3) AS avg_score,
            COUNT(DISTINCT item_id)                                    AS devices_monitored,
            COUNT(DISTINCT CASE WHEN is_anomaly = 1 THEN item_id END)  AS devices_anomalous,
            MIN(data_ts)                                               AS period_start,
            MAX(data_ts)                                               AS period_end,
            MAX(CASE WHEN is_anomaly = 1 THEN data_ts END)             AS last_anomaly_ts
        FROM ad_results
        WHERE 1=1
          {_domain_clause(domain)}
          {_since_clause(period)}
        GROUP BY domain, strategy
        ORDER BY domain, strategy
    """
    return sql, params


def _q_top_devices(domain: str, period: str, limit: int = 15) -> tuple[str, dict]:
    params: dict = {'limit': limit}
    if domain != 'all':
        params['domain'] = domain
    sql = f"""
        SELECT
            domain, item_id, strategy,
            COUNT(*)                                                   AS total_points,
            SUM(is_anomaly)                                            AS anomaly_count,
            ROUND(AVG(CAST(is_anomaly AS DECIMAL(5,4))) * 100, 2)     AS anomaly_rate_pct,
            ROUND(MAX(anomaly_score), 3)                               AS peak_score,
            ROUND(AVG(CASE WHEN is_anomaly = 1 THEN anomaly_score END), 3) AS avg_score,
            MAX(CASE WHEN is_anomaly = 1 THEN data_ts END)             AS last_anomaly_ts,
            TIMESTAMPDIFF(HOUR,
                MAX(CASE WHEN is_anomaly = 1 THEN data_ts END),
                NOW())                                                 AS hours_since_last
        FROM ad_results
        WHERE 1=1
          {_domain_clause(domain)}
          {_since_clause(period)}
        GROUP BY domain, item_id, strategy
        HAVING anomaly_count > 0
        ORDER BY anomaly_count DESC, peak_score DESC
        LIMIT :limit
    """
    return sql, params


def _q_trend(domain: str, period: str) -> tuple[str, dict]:
    params: dict = {}
    if domain != 'all':
        params['domain'] = domain
    sql = f"""
        SELECT
            DATE(data_ts)                                              AS day,
            domain,
            SUM(is_anomaly)                                            AS anomaly_count,
            COUNT(*)                                                   AS total_points,
            ROUND(AVG(CAST(is_anomaly AS DECIMAL(5,4))) * 100, 2)     AS anomaly_rate_pct,
            COUNT(DISTINCT CASE WHEN is_anomaly = 1 THEN item_id END)  AS affected_devices
        FROM ad_results
        WHERE 1=1
          {_domain_clause(domain)}
          {_since_clause(period)}
        GROUP BY DATE(data_ts), domain
        ORDER BY day ASC
    """
    return sql, params


def _q_incidents(domain: str, period: str) -> tuple[str, dict]:
    params: dict = {}
    if domain != 'all':
        params['domain'] = domain
    sql = f"""
        SELECT domain, item_id, strategy, data_ts, anomaly_score
        FROM ad_results
        WHERE is_anomaly = 1
          {_domain_clause(domain)}
          {_since_clause(period)}
        ORDER BY domain, item_id, data_ts
        LIMIT 5000
    """
    return sql, params


def _q_correlation(domain: str, period: str) -> tuple[str, dict]:
    params: dict = {}
    if domain != 'all':
        params['domain'] = domain
    # Pour chaque anomalie réelle, cherche une prédiction dans les 48h précédentes
    sql = f"""
        SELECT
            a.domain,
            a.item_id,
            a.data_ts                                                  AS anomaly_ts,
            ROUND(a.anomaly_score, 3)                                  AS anomaly_score,
            MIN(p.run_at)                                              AS predicted_at,
            MIN(p.forecast_ts)                                         AS forecast_ts,
            ROUND(MAX(p.confidence), 2)                                AS confidence,
            TIMESTAMPDIFF(HOUR, MIN(p.run_at), a.data_ts)              AS lead_hours,
            CASE WHEN MIN(p.item_id) IS NOT NULL THEN 1 ELSE 0 END     AS was_predicted
        FROM ad_results a
        LEFT JOIN aria_predictions p
            ON  p.domain   = a.domain
            AND p.item_id  = a.item_id
            AND p.is_alert = 1
            AND p.forecast_ts BETWEEN
                DATE_SUB(a.data_ts, INTERVAL 48 HOUR) AND
                DATE_ADD(a.data_ts, INTERVAL 6 HOUR)
        WHERE a.is_anomaly = 1
          {_domain_clause(domain)}
          {_since_clause(period)}
        GROUP BY a.domain, a.item_id, a.data_ts, a.anomaly_score
        ORDER BY a.data_ts DESC
        LIMIT 500
    """
    return sql, params


# ── Modes ──────────────────────────────────────────────────────────────────────

def _mode_summary(domain: str, period: str) -> dict:
    sql, params = _q_summary(domain, period)
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), params).mappings().fetchall()]

    if not rows:
        return {'message': 'Aucune donnée AD disponible pour cette période.', 'rows': []}

    # Agrège par domaine (hotstart + coldstart fusionnés)
    domains_agg: dict[str, dict] = {}
    for r in rows:
        d = r['domain']
        if d not in domains_agg:
            domains_agg[d] = {
                'domain': d, 'label': _DOMAIN_LABELS.get(d, d),
                'total_points': 0, 'anomaly_count': 0,
                'devices_monitored': 0, 'devices_anomalous': 0,
                'peak_score': 0.0, 'last_anomaly_ts': None,
                'strategies': [],
            }
        agg = domains_agg[d]
        agg['total_points']      += int(r['total_points'] or 0)
        agg['anomaly_count']     += int(r['anomaly_count'] or 0)
        agg['devices_monitored'] = max(agg['devices_monitored'], int(r['devices_monitored'] or 0))
        agg['devices_anomalous'] = max(agg['devices_anomalous'], int(r['devices_anomalous'] or 0))
        agg['peak_score']        = max(agg['peak_score'], float(r['peak_score'] or 0))
        if r.get('last_anomaly_ts'):
            lt = str(r['last_anomaly_ts'])
            if agg['last_anomaly_ts'] is None or lt > agg['last_anomaly_ts']:
                agg['last_anomaly_ts'] = lt
        agg['strategies'].append(r['strategy'])

    # Health score + tri
    result_domains = []
    for d, agg in domains_agg.items():
        rate = round(agg['anomaly_count'] / agg['total_points'] * 100, 2) if agg['total_points'] else 0
        hs   = _health_score(rate, agg['peak_score'], None)
        agg['anomaly_rate_pct'] = rate
        agg['health_score']     = hs
        agg['health_label']     = _health_label(hs)
        result_domains.append(agg)

    result_domains.sort(key=lambda x: x['health_score'])
    worst = result_domains[0] if result_domains else None

    total_anomalies = sum(d['anomaly_count'] for d in result_domains)
    total_points    = sum(d['total_points']  for d in result_domains)
    global_rate     = round(total_anomalies / total_points * 100, 2) if total_points else 0
    global_health   = round(sum(d['health_score'] for d in result_domains) / len(result_domains)) if result_domains else 100

    return {
        'period':          period,
        'global_health':   global_health,
        'global_label':    _health_label(global_health),
        'total_points':    total_points,
        'total_anomalies': total_anomalies,
        'global_rate_pct': global_rate,
        'domains':         result_domains,
        'most_affected':   worst['domain'] if worst else None,
        'insight': (
            f"Système {_health_label(global_health).lower()} — "
            f"{total_anomalies} anomalies ML sur {total_points} points analysés "
            f"({global_rate:.1f}%). "
            f"Domaine le plus touché : {worst['label'] if worst else 'N/A'} "
            f"(santé {worst['health_score'] if worst else '?'}/100)."
        ),
    }


def _mode_top_devices(domain: str, period: str) -> dict:
    sql, params = _q_top_devices(domain, period)
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), params).mappings().fetchall()]

    if not rows:
        return {'message': 'Aucun device anomalique pour cette période.', 'devices': []}

    devices = []
    for r in rows:
        rate = float(r.get('anomaly_rate_pct') or 0)
        peak = float(r.get('peak_score') or 0)
        hrs  = r.get('hours_since_last')
        hrs_f = float(hrs) if hrs is not None else None
        hs   = _health_score(rate, peak, hrs_f)
        devices.append({
            'domain':           r['domain'],
            'item_id':          r['item_id'],
            'strategy':         r['strategy'],
            'total_points':     int(r['total_points'] or 0),
            'anomaly_count':    int(r['anomaly_count'] or 0),
            'anomaly_rate_pct': rate,
            'peak_score':       peak,
            'avg_score':        round(float(r.get('avg_score') or 0), 3),
            'last_anomaly_ts':  str(r['last_anomaly_ts']) if r.get('last_anomaly_ts') else None,
            'hours_since_last': round(hrs_f, 1) if hrs_f is not None else None,
            'health_score':     hs,
            'health_label':     _health_label(hs),
        })

    critical = [d for d in devices if d['health_score'] < 30]
    return {
        'period':     period,
        'domain':     domain,
        'devices':    devices,
        'critical_count': len(critical),
        'insight': (
            f"{len(devices)} device(s) anomalique(s) détecté(s). "
            f"{len(critical)} en état CRITIQUE (santé < 30/100). "
            f"Device le plus problématique : {devices[0]['item_id']} "
            f"({devices[0]['anomaly_count']} anomalies, santé {devices[0]['health_score']}/100)."
            if devices else "Aucun device anomalique."
        ),
    }


def _mode_trend(domain: str, period: str) -> dict:
    sql, params = _q_trend(domain, period)
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), params).mappings().fetchall()]

    if not rows:
        return {'message': 'Pas de données de tendance pour cette période.', 'daily': []}

    # Grouper par domaine
    by_domain: dict[str, list] = {}
    for r in rows:
        d = r['domain']
        by_domain.setdefault(d, []).append({
            'day':              str(r['day']),
            'anomaly_count':    int(r['anomaly_count'] or 0),
            'total_points':     int(r['total_points'] or 0),
            'anomaly_rate_pct': float(r['anomaly_rate_pct'] or 0),
            'affected_devices': int(r['affected_devices'] or 0),
        })

    domain_trends: list[dict] = []
    for d, days in by_domain.items():
        counts = [x['anomaly_count'] for x in days]
        slope  = _linear_trend(counts[-7:]) if len(counts) >= 2 else 0.0
        if   slope >  0.5: direction, dir_label = slope, 'DÉGRADATION'
        elif slope < -0.5: direction, dir_label = slope, 'AMÉLIORATION'
        else:              direction, dir_label = slope, 'STABLE'

        worst_day = max(days, key=lambda x: x['anomaly_count'])
        domain_trends.append({
            'domain':    d,
            'label':     _DOMAIN_LABELS.get(d, d),
            'daily':     days,
            'slope':     round(slope, 3),
            'direction': dir_label,
            'worst_day': worst_day,
            'total_anomalies': sum(counts),
            'avg_daily':       round(sum(counts) / len(counts), 1),
        })

    domain_trends.sort(key=lambda x: abs(x['slope']), reverse=True)

    return {
        'period':  period,
        'domain':  domain,
        'trends':  domain_trends,
        'insight': ' | '.join(
            f"{t['label']} : {t['direction']} (pente {t['slope']:+.1f}/j, "
            f"pire jour : {t['worst_day']['day']} avec {t['worst_day']['anomaly_count']} anomalies)"
            for t in domain_trends
        ) or 'Pas de tendance détectable.',
    }


def _mode_incidents(domain: str, period: str) -> dict:
    sql, params = _q_incidents(domain, period)
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), params).mappings().fetchall()]

    if not rows:
        return {'message': 'Aucune anomalie à regrouper en incidents.', 'incidents': []}

    # Cluster par (domain, item_id) puis fusionner
    item_groups: dict[str, list] = {}
    for r in rows:
        key = f"{r['domain']}::{r['item_id']}"
        item_groups.setdefault(key, []).append(r)

    all_incidents: list[dict] = []
    for grp in item_groups.values():
        all_incidents.extend(_cluster_incidents(grp, gap_hours=3))

    # Trier par sévérité puis durée
    sev_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    all_incidents.sort(key=lambda x: (sev_order.get(x['severity'], 9), -x['duration_h']))

    high   = [i for i in all_incidents if i['severity'] == 'HIGH']
    medium = [i for i in all_incidents if i['severity'] == 'MEDIUM']
    long_  = [i for i in all_incidents if i['duration_h'] >= 12]

    return {
        'period':         period,
        'domain':         domain,
        'total_incidents':len(all_incidents),
        'high_count':     len(high),
        'medium_count':   len(medium),
        'long_incidents': len(long_),
        'incidents':      all_incidents[:30],  # max 30 pour le contexte LLM
        'insight': (
            f"{len(all_incidents)} incident(s) détecté(s) — "
            f"{len(high)} CRITIQUE(S), {len(medium)} MOYEN(S). "
            f"{len(long_)} incident(s) long(s) (≥ 12h). "
            f"Incident le plus sévère : {all_incidents[0]['duration_h']}h sur "
            f"{', '.join(all_incidents[0]['items'][:3])} "
            f"(score max {all_incidents[0]['peak_score']})."
            if all_incidents else "Aucun incident détecté."
        ),
    }


def _mode_correlation(domain: str, period: str) -> dict:
    sql, params = _q_correlation(domain, period)
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), params).mappings().fetchall()]

    if not rows:
        return {
            'message': 'Aucune anomalie dans cette période, ou table aria_predictions vide.',
            'note': 'Lancer le pipeline AD (POST /system/run-pipeline) pour peupler les prédictions.',
        }

    total        = len(rows)
    predicted    = [r for r in rows if int(r.get('was_predicted') or 0) == 1]
    not_predicted = total - len(predicted)
    recall       = round(len(predicted) / total * 100, 1) if total else 0.0

    lead_times  = [int(r['lead_hours']) for r in predicted if r.get('lead_hours') is not None]
    avg_lead    = round(sum(lead_times) / len(lead_times), 1) if lead_times else None
    max_lead    = max(lead_times) if lead_times else None

    # Précision : prédictions qui avaient effectivement une anomalie
    # On a les anomalies réelles — on ne peut calculer les fausses alarmes que si on
    # a le total des prédictions émises. On le récupère séparément.
    with engine.connect() as conn2:
        pred_params: dict = {}
        pred_domain_clause = '' if domain == 'all' else 'AND domain = :domain'
        pred_since_clause  = _since_clause(period).replace('data_ts', 'forecast_ts')
        if domain != 'all':
            pred_params['domain'] = domain
        total_preds = conn2.execute(text(f"""
            SELECT COUNT(*) FROM aria_predictions
            WHERE is_alert = 1
              {pred_domain_clause}
              {pred_since_clause}
        """), pred_params).scalar() or 0

    precision = round(len(predicted) / int(total_preds) * 100, 1) if int(total_preds) > 0 else None

    # Par domaine
    by_domain: dict[str, dict] = {}
    for r in rows:
        d = r['domain']
        if d not in by_domain:
            by_domain[d] = {'total': 0, 'predicted': 0, 'lead_times': []}
        by_domain[d]['total'] += 1
        if int(r.get('was_predicted') or 0):
            by_domain[d]['predicted'] += 1
            if r.get('lead_hours') is not None:
                by_domain[d]['lead_times'].append(int(r['lead_hours']))

    domain_stats = []
    for d, s in by_domain.items():
        d_recall = round(s['predicted'] / s['total'] * 100, 1) if s['total'] else 0
        d_lead   = round(sum(s['lead_times']) / len(s['lead_times']), 1) if s['lead_times'] else None
        domain_stats.append({
            'domain':     d,
            'label':      _DOMAIN_LABELS.get(d, d),
            'total':      s['total'],
            'predicted':  s['predicted'],
            'recall_pct': d_recall,
            'avg_lead_h': d_lead,
        })
    domain_stats.sort(key=lambda x: -x['recall_pct'])

    _prec_str = f"Précision : {precision:.0f}% (des alertes émises étaient fondées). " if precision is not None else ""
    _lead_str = f"Avance moyenne du warning : {avg_lead}h avant l'anomalie." if avg_lead else "Aucune prédiction corrélée trouvée."
    return {
        'period':           period,
        'domain':           domain,
        'total_anomalies':  total,
        'predicted_count':  len(predicted),
        'unpredicted_count':not_predicted,
        'recall_pct':       recall,
        'precision_pct':    precision,
        'avg_lead_hours':   avg_lead,
        'max_lead_hours':   max_lead,
        'total_predictions_issued': int(total_preds),
        'by_domain':        domain_stats,
        'insight': f"Chronos a prédit {recall:.0f}% des anomalies réelles (recall). {_prec_str}{_lead_str}",
    }


# ── Point d'entrée MCP ────────────────────────────────────────────────────────

def ad_analysis(
    domain: str = 'all',
    period: str = '7j',
    mode:   str = 'summary',
) -> str:
    """
    Analyse intelligente des anomalies détectées par l'IA (HotStart Chronos + ColdStart).
    Utiliser OBLIGATOIREMENT pour toute question sur les anomalies ML passées,
    les devices problématiques, l'évolution des anomalies ou la fiabilité des prévisions.

    domain : 'energy' | 'water' | 'gas' | 'fuel' | 'all'
    period : '24h' | '7j' | '30j' | '90j' | 'tout'
    mode   :
      'summary'     → Vue globale + health score par domaine + pire device
      'top_devices' → Classement des devices les plus anomaliques avec score de santé
      'trend'       → Évolution quotidienne + direction (amélioration/dégradation)
      'incidents'   → Regroupement en incidents (anomalies consécutives ≤ 3h)
      'correlation' → Recall/précision/lead-time du forecasting Chronos
    """
    t0   = time.time()
    tool = 'ad_analysis'
    logger.info('[%s] domain=%s period=%s mode=%s', tool, domain, period, mode)

    # Validation
    domain = (domain or 'all').lower().strip()
    period = (period or '7j').lower().strip()
    mode   = (mode   or 'summary').lower().strip()

    if domain not in _VALID_DOMAINS:
        return err(tool, f"Domaine invalide : {domain!r}. Valeurs : {sorted(_VALID_DOMAINS)}")
    if period not in _PERIOD_MAP:
        return err(tool, f"Période invalide : {period!r}. Valeurs : {sorted(_PERIOD_MAP)}")
    if mode not in _VALID_MODES:
        return err(tool, f"Mode invalide : {mode!r}. Valeurs : {sorted(_VALID_MODES)}")

    try:
        _MODES = {
            'summary'    : _mode_summary,
            'top_devices': _mode_top_devices,
            'trend'      : _mode_trend,
            'incidents'  : _mode_incidents,
            'correlation': _mode_correlation,
        }
        result = _MODES[mode](domain, period)
        result['_meta'] = {
            'tool'    : tool,
            'mode'    : mode,
            'domain'  : domain,
            'period'  : period,
            'duration': round(time.time() - t0, 3),
        }
        return ok(result)

    except Exception as e:
        logger.error('[%s] Exception mode=%s : %s', tool, mode, e, exc_info=True)
        return err(tool, str(e))
