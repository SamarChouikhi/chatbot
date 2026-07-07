"""
ARIA Proactive — Analyse autonome + push dans le chat.

Toutes les 2h, analyse :
  1. Nouvelles anomalies AD (score >= 0.65) détectées depuis le dernier check
  2. Prédictions HIGH imminentes (dans les 12h)

Pour chaque condition déclenchante, génère un message ARIA et le pousse
dans le chat de l'utilisateur concerné via SSE (ProactiveBroadcaster).

Règles :
  - Cooldown 4h par (user_id, domain) — pas de spam
  - Filtre sur allowed_modules de l'employé
  - Messages en français, template-based (pas d'appel LLM → fiable et rapide)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger('aria.proactive')

# ── Seuils ────────────────────────────────────────────────────────────────────
_ANOMALY_SCORE_MIN = 0.65   # score AD minimum pour déclencher une alerte
_PRED_HORIZON_H    = 12     # fenêtre prédictions (heures dans le futur)
_COOLDOWN_H        = 4      # intervalle min entre deux alertes pour (user, domain)
_CHECK_WINDOW_H    = 2      # fenêtre de recherche des nouvelles anomalies (= fréquence du job)

# ── Templates ─────────────────────────────────────────────────────────────────
_MSG_ANOMALY: dict[str, str] = {
    'energy': "⚡ J'ai détecté une anomalie électrique sur **{item}** (score {score:.0%}). Voulez-vous que j'analyse les 48 dernières heures ?",
    'water':  "💧 J'ai détecté une anomalie de consommation eau sur **{item}** (score {score:.0%}). Voulez-vous que j'analyse les 48 dernières heures ?",
    'gas':    "🔥 J'ai détecté une anomalie gaz sur **{item}** (score {score:.0%}). Voulez-vous que j'analyse les 48 dernières heures ?",
    'fuel':   "⛽ J'ai détecté une anomalie carburant sur **{item}** (score {score:.0%}). Voulez-vous que j'analyse les 48 dernières heures ?",
}

_MSG_PREDICTION: dict[str, str] = {
    'energy': "🔮 Une anomalie électrique est prévue sur **{item}** dans ~{h}h (confiance {conf:.0%}). Voulez-vous un diagnostic préventif ?",
    'water':  "🔮 Une anomalie eau est prévue sur **{item}** dans ~{h}h (confiance {conf:.0%}). Voulez-vous un diagnostic préventif ?",
    'gas':    "🔮 Une anomalie gaz est prévue sur **{item}** dans ~{h}h (confiance {conf:.0%}). Voulez-vous un diagnostic préventif ?",
    'fuel':   "🔮 Une anomalie carburant est prévue sur **{item}** dans ~{h}h (confiance {conf:.0%}). Voulez-vous un diagnostic préventif ?",
}

# Quick reply envoyée à ARIA quand l'utilisateur clique "Analyser"
_ANALYSE_QUESTION: dict[str, str] = {
    'energy': 'analyse les 48 dernières heures d\'énergie électrique',
    'water':  'analyse les 48 dernières heures de consommation eau',
    'gas':    'analyse les 48 dernières heures de gaz',
    'fuel':   'analyse les 48 dernières heures de carburant',
}

# module allowed_modules → domaines couverts
_MODULE_DOMAINS: dict[str, list[str]] = {
    'eau'                : ['water'],
    'énergie électrique' : ['energy'],
    'gaz'                : ['gas'],
    'carburant'          : ['fuel'],
    'alertes'            : ['energy', 'water', 'gas', 'fuel'],
    'dashboard'          : ['energy', 'water', 'gas', 'fuel'],
    'rapports'           : ['energy', 'water', 'gas', 'fuel'],
    'équipements/capteurs': [],
}


@dataclass
class ProactiveAlert:
    user_id:     str
    domain:      str
    severity:    str
    message:     str
    source_type: str   # 'anomaly' | 'prediction'
    source_ref:  str   # '{item_id}@{timestamp}'
    qr_label:    str
    qr_value:    str


# ── Entrée principale ─────────────────────────────────────────────────────────

def run_proactive_check(engine, user_ids: list[str]) -> list[ProactiveAlert]:
    """
    Analyse les anomalies récentes et prédictions imminentes.
    Retourne la liste des alertes à pousser pour chaque utilisateur.
    """
    if not user_ids:
        return []

    since          = datetime.utcnow() - timedelta(hours=_CHECK_WINDOW_H)
    new_anomalies  = _fetch_new_anomalies(engine, since)
    new_preds      = _fetch_upcoming_predictions(engine)

    logger.info('[PROACTIVE] %d anomalies + %d prédictions à évaluer pour %d users',
                len(new_anomalies), len(new_preds), len(user_ids))

    alerts: list[ProactiveAlert] = []

    for uid in user_ids:
        allowed_domains = _user_domains(engine, uid)  # None = accès total
        # Domaines déjà alertés dans ce batch — évite les doublons intra-run
        alerted_this_run: set[str] = set()

        for a in new_anomalies:
            dom = a['domain']
            if allowed_domains is not None and dom not in allowed_domains:
                continue
            if dom in alerted_this_run:
                continue
            if _on_cooldown(engine, uid, dom):
                continue
            tpl = _MSG_ANOMALY.get(dom)
            if not tpl:
                continue
            score = float(a.get('anomaly_score') or 0)
            msg   = tpl.format(item=a['item_id'], score=score)
            sev   = 'HIGH' if score >= 0.85 else 'MEDIUM'
            alerts.append(ProactiveAlert(
                user_id     = uid,
                domain      = dom,
                severity    = sev,
                message     = msg,
                source_type = 'anomaly',
                source_ref  = f"{a['item_id']}@{a['data_ts']}",
                qr_label    = 'Analyser 48h',
                qr_value    = _ANALYSE_QUESTION.get(dom, 'analyser'),
            ))
            alerted_this_run.add(dom)

        for p in new_preds:
            dom = p['domain']
            if allowed_domains is not None and dom not in allowed_domains:
                continue
            if dom in alerted_this_run:
                continue
            if _on_cooldown(engine, uid, dom):
                continue
            tpl = _MSG_PREDICTION.get(dom)
            if not tpl:
                continue
            try:
                fts = datetime.fromisoformat(str(p['forecast_ts']))
                in_h = max(1, round((fts - datetime.utcnow()).total_seconds() / 3600))
            except Exception:
                in_h = _PRED_HORIZON_H
            conf = float(p.get('confidence') or 0)
            msg  = tpl.format(item=p['item_id'], h=in_h, conf=conf)
            alerts.append(ProactiveAlert(
                user_id     = uid,
                domain      = dom,
                severity    = str(p.get('alert_severity', 'MEDIUM')),
                message     = msg,
                source_type = 'prediction',
                source_ref  = f"{p['item_id']}@{p['forecast_ts']}",
                qr_label    = 'Diagnostic préventif',
                qr_value    = _ANALYSE_QUESTION.get(dom, 'analyser'),
            ))
            alerted_this_run.add(dom)

    logger.info('[PROACTIVE] %d alertes générées', len(alerts))
    return alerts


def persist_and_broadcast(engine, alerts: list[ProactiveAlert], broadcaster) -> None:
    """Persiste en DB et envoie via SSE à tous les clients connectés."""
    if not alerts:
        return
    with engine.begin() as conn:
        for a in alerts:
            r = conn.execute(text("""
                INSERT INTO aria_proactive_messages
                    (user_id, domain, severity, message, source_type, source_ref,
                     quick_reply_label, quick_reply_value)
                VALUES
                    (:uid, :dom, :sev, :msg, :src_t, :src_r, :qrl, :qrv)
            """), {
                'uid':   a.user_id,
                'dom':   a.domain,
                'sev':   a.severity,
                'msg':   a.message,
                'src_t': a.source_type,
                'src_r': a.source_ref,
                'qrl':   a.qr_label,
                'qrv':   a.qr_value,
            })
            broadcaster.push(a.user_id, {
                'id':         r.lastrowid,
                'domain':     a.domain,
                'severity':   a.severity,
                'message':    a.message,
                'source_type': a.source_type,
                'qr_label':   a.qr_label,
                'qr_value':   a.qr_value,
                'created_at': datetime.utcnow().isoformat(),
            })
    logger.info('[PROACTIVE] %d alertes persistées et broadcastées', len(alerts))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_new_anomalies(engine, since: datetime) -> list[dict]:
    """Anomalies AD récentes non encore notifiées de façon proactive."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT domain, item_id, data_ts, anomaly_score
            FROM ad_results
            WHERE is_anomaly   = 1
              AND anomaly_score >= :min_score
              AND run_at        >= :since
            ORDER BY anomaly_score DESC
            LIMIT 30
        """), {'min_score': _ANOMALY_SCORE_MIN, 'since': since}).mappings().fetchall()
    return [dict(r) for r in rows]


def _fetch_upcoming_predictions(engine) -> list[dict]:
    """Prédictions HIGH dans les prochaines heures (dernier run uniquement)."""
    horizon = datetime.utcnow() + timedelta(hours=_PRED_HORIZON_H)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT domain, item_id, forecast_ts, confidence, alert_severity
            FROM aria_predictions
            WHERE run_at = (SELECT MAX(run_at) FROM aria_predictions)
              AND is_alert       = 1
              AND alert_severity = 'HIGH'
              AND forecast_ts    BETWEEN NOW() AND :horizon
            ORDER BY confidence DESC
            LIMIT 20
        """), {'horizon': horizon}).mappings().fetchall()
    return [dict(r) for r in rows]


def _on_cooldown(engine, user_id: str, domain: str) -> bool:
    """True si une alerte proactive a déjà été envoyée pour ce (user, domain) dans les 4h."""
    with engine.connect() as conn:
        n = conn.execute(text("""
            SELECT COUNT(*) FROM aria_proactive_messages
            WHERE user_id  = :uid
              AND domain   = :dom
              AND dismissed = 0
              AND created_at >= DATE_SUB(NOW(), INTERVAL :h HOUR)
        """), {'uid': user_id, 'dom': domain, 'h': _COOLDOWN_H}).scalar()
    return int(n or 0) > 0


def _user_domains(engine, user_id: str) -> set[str] | None:
    """None = accès total. Set vide = aucun domaine IoT autorisé."""
    from api.db import get_employee_modules
    modules = get_employee_modules(user_id)
    if modules is None:
        return None  # admin / inconnu → accès total
    domains: set[str] = set()
    for m in modules:
        domains.update(_MODULE_DOMAINS.get(m, []))
    return domains
