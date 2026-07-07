import logging
from datetime import datetime

from mcp_server.tools._helpers import ok, err
from sqlalchemy import text

logger = logging.getLogger('aria.tools.predictions')

_SEVERITY_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
_DOMAIN_UNITS   = {
    'energy': 'kWh',
    'water':  'm³',
    'gas':    'm³',
    'fuel':   'L',
}
_VALID_DOMAINS = {'energy', 'water', 'gas', 'fuel'}


def get_upcoming_predictions(domain: str = 'all', horizon_hours: int = 24) -> str:
    """
    Retourne les prédictions d'anomalies Chronos pour les prochaines heures.
    ARIA anticipe les problèmes AVANT qu'ils arrivent grâce au forecasting Chronos.

    domain: 'energy' | 'water' | 'gas' | 'fuel' | 'all'
    horizon_hours: combien d'heures dans le futur analyser (défaut 24, max 48)
    """
    tool = 'get_upcoming_predictions'
    logger.info('[%s] domain=%s horizon=%dh', tool, domain, horizon_hours)

    horizon_hours = min(max(horizon_hours, 1), 48)

    try:
        from mcp_server.db.connection import engine  # lazy — évite un crash au démarrage si DB down

        # Validation domaine par whitelist — jamais injecté directement dans le SQL
        domain_low = (domain or '').lower().strip()
        use_domain = domain_low if domain_low in _VALID_DOMAINS else None

        params: dict = {'horizon': horizon_hours}
        domain_clause = ''
        if use_domain:
            domain_clause = 'AND domain = :domain'
            params['domain'] = use_domain

        # Référence = run_at le plus récent (et non NOW()) pour fonctionner
        # aussi bien sur données historiques qu'en production temps réel.
        sql = text(f"""
            SELECT domain, item_id, forecast_ts, horizon_hours,
                   forecast_median, forecast_low, forecast_high,
                   confidence, is_alert, alert_severity, run_at
            FROM aria_predictions
            WHERE run_at = (SELECT MAX(run_at) FROM aria_predictions)
              AND is_alert = 1
              AND forecast_ts <= DATE_ADD(
                    (SELECT MIN(forecast_ts) FROM aria_predictions
                     WHERE run_at = (SELECT MAX(run_at) FROM aria_predictions)),
                    INTERVAL :horizon HOUR)
              {domain_clause}
            ORDER BY
                FIELD(alert_severity, 'HIGH', 'MEDIUM', 'LOW'),
                forecast_ts ASC
            LIMIT 100
        """)
        with engine.connect() as conn:
            result = conn.execute(sql, params)
            cols   = list(result.keys())
            rows   = [dict(zip(cols, row)) for row in result.fetchall()]

        if not rows:
            return ok({
                'horizon_hours': horizon_hours,
                'domain':        domain,
                'total_alerts':  0,
                'message':       f'Aucune anomalie préventive prévue dans les {horizon_hours}h à venir.',
                'predictions':   [],
            })

        # Grouper par sévérité pour le résumé narratif
        by_severity: dict[str, list] = {'HIGH': [], 'MEDIUM': [], 'LOW': []}
        for r in rows:
            sev = (r.get('alert_severity') or 'LOW').upper()
            by_severity.setdefault(sev, []).append(r)

        # Référence temporelle = timestamp du premier point prédit du dernier run
        all_ts = [r['forecast_ts'] for r in rows if r.get('forecast_ts')]
        ref_dt = min(datetime.fromisoformat(str(t)) for t in all_ts) if all_ts else datetime.utcnow()

        alerts_desc = []
        for sev in ('HIGH', 'MEDIUM', 'LOW'):
            group = by_severity.get(sev, [])
            if not group:
                continue
            for r in group[:5]:  # max 5 par sévérité dans le résumé
                try:
                    fts       = datetime.fromisoformat(str(r['forecast_ts']))
                    delta_h   = max(1, int((fts - ref_dt).total_seconds() / 3600))
                    unit      = _DOMAIN_UNITS.get(str(r.get('domain', '')), '')
                    median    = r.get('forecast_median')
                    conf      = r.get('confidence')
                    conf_pct  = f'{round(float(conf) * 100)}%' if conf is not None else '?'
                    median_s  = f'{round(float(median), 2)} {unit}' if median is not None else '?'
                    alerts_desc.append({
                        'severity':      sev,
                        'domain':        r.get('domain'),
                        'item_id':       r.get('item_id'),
                        'in_hours':      delta_h,
                        'forecast_ts':   str(r['forecast_ts']),
                        'predicted_val': median_s,
                        'confidence':    conf_pct,
                        'message': (
                            f"[{sev}] {r.get('domain','?').upper()} · {r.get('item_id','?')} — "
                            f"dans ~{delta_h}h ({fts.strftime('%d/%m %H:%M')}) : "
                            f"valeur prévue {median_s} — confiance {conf_pct}"
                        ),
                    })
                except Exception:
                    continue

        return ok({
            'horizon_hours': horizon_hours,
            'domain':        domain,
            'total_alerts':  len(rows),
            'high_count':    len(by_severity.get('HIGH', [])),
            'medium_count':  len(by_severity.get('MEDIUM', [])),
            'low_count':     len(by_severity.get('LOW', [])),
            'predictions':   alerts_desc,
        })

    except Exception as e:
        logger.error('[%s] Exception: %s', tool, e)
        return err(tool, str(e))
