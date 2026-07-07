"""
Pré-traitement de la question utilisateur avant envoi au LLM.

Rôle : analyser la question et produire un Intent structuré qui sert à :
  1. Guider le quality gate (output_guard.py) — savoir quoi vérifier
  2. Enrichir le message si la question est ambiguë (pronom "il", "ça", etc.)

Ne modifie PAS le texte envoyé au LLM — ajoute seulement du contexte structuré.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ── Termes génériques "tous capteurs" → sensor_type='all' ────────────────────

_GENERIC_ALL_TERMS = [
    'capteur', 'capteurs', 'capteurs actifs', 'capteurs inactifs',
    'appareil', 'appareils', 'dispositif', 'dispositifs',
    'inactif', 'inactifs', 'hors ligne', 'offline', 'silencieux',
    'dormant', 'dormants', 'mort', 'morts', 'déconnecté', 'déconnectés',
    'actif', 'actifs', 'tous les capteurs', 'tous les modules',
    'sensor', 'sensors', 'device', 'devices',
]

# ── Vocabulaire capteurs (FR / AR / EN / abréviations) ───────────────────────

_SENSOR_VOCAB: dict[str, list[str]] = {
    'thl' : ['température', 'temp', 'humidité', 'humidity', 'luminosité', 'lux',
             'thl', 'thermomètre', 'حرارة', 'رطوبة', 'temperature'],
    'wm'  : ['eau', 'water', 'compteur eau', 'fuite eau', 'consommation eau',
             'wm', 'débit eau', 'ماء', 'مياه', 'hydraulique'],
    'en'  : ['électricité', 'électrique', 'energie', 'énergie', 'kwh', 'watt',
             'cosfi', 'thd', 'tension', 'courant', 'puissance', 'ampère',
             'كهرباء', 'energy', 'power', 'voltage', 'en'],
    'gm'  : ['gaz', 'gas', 'débit gaz', 'fuite gaz', 'compteur gaz',
             'gm', 'غاز', 'méthane', 'm³'],
    'fuel': ['carburant', 'fuel', 'flotte', 'véhicule', 'voiture', 'diesel',
             'essence', 'km', 'kilomètre', 'vitesse', 'vehicle', 'وقود'],
    'pir' : ['présence', 'passage', 'trafic', 'pir', 'mouvement', 'détecteur',
             'occupation', 'حضور', 'people', 'count'],
    'ls'  : ['niveau', 'cuve', 'level', 'réservoir', 'tank', 'bac',
             'remplissage', 'مستوى', 'ls'],
    'sm'  : ['météo', 'meteo', 'vent', 'pression', 'uv', 'weather', 'طقس'],
}

# ── Vocabulaire périodes ──────────────────────────────────────────────────────

_PERIOD_VOCAB: dict[str, list[str]] = {
    'realtime': ['maintenant', 'actuel', 'en ce moment', 'temps réel', 'live',
                 'الآن', 'current', 'now'],
    '24h'     : ['aujourd\'hui', 'hier', '24h', 'journée', 'aujourd', 'daily'],
    '48h'     : ['48h', '48 heures', '48 dernières heures', 'deux jours', '2 jours'],
    '7j'      : ['semaine', '7 jours', '7j', 'cette semaine', 'weekly', 'أسبوع'],
    '30j'     : ['mois', '30 jours', '30j', 'ce mois', 'monthly', 'mensuel', 'شهر'],
    'tout'    : ['tout', 'historique', 'depuis le début', 'global', 'all', 'كل'],
}

# ── Type de query ─────────────────────────────────────────────────────────────

_QUERY_TYPE_PATTERNS: dict[str, list[str]] = {
    'anomaly'       : ['anomalie', 'problème', 'probleme', 'erreur', 'défaut',
                       'alerte', 'alert', 'fuite', 'fraude', 'panne', 'issue'],
    'prediction'    : ['prévision', 'prédiction', 'prévoir', 'forecast', 'demain',
                       'prochain', 'prochains', 'prochaine', 'à venir', 'risque futur',
                       'dans les prochaines', 'prochaines heures'],
    'recommendation': ['recommandation', 'recommandations', 'conseil', 'conseils',
                       'optimiser', 'que faire', 'quoi faire', 'améliorer', 'action à prendre'],
    'realtime'      : ['actuel', 'maintenant', 'en ce moment', 'état', 'status',
                       'current', 'now', 'live', 'temps réel',
                       'inactif', 'inactifs', 'actif', 'actifs',
                       'hors ligne', 'offline', 'silencieux', 'dormant',
                       'connecté', 'déconnecté', 'fonctionnel', 'en panne'],
    'historical'    : ['historique', 'analyse', 'sur 7', 'sur 30', 'ce mois',
                       'cette semaine', 'trend', 'évolution', 'moyenne'],
    'security'      : ['table', 'colonne', 'sql', 'select', 'delete', 'drop',
                       'alter', 'insert', 'update', 'schéma', 'base de données'],
    'report'        : ['rapport', 'résumé', 'état général', 'tout', 'complet',
                       'general', 'overview'],
    'simple'        : ['normale', 'normal', 'ok', 'bien', 'c\'est quoi', 'définition',
                       'qu\'est-ce', 'comment ça marche'],
}


# ── Dataclass Intent ──────────────────────────────────────────────────────────

@dataclass
class Intent:
    sensor_type:  Optional[str]  # 'thl' | 'wm' | 'en' | 'gm' | 'fuel' | 'pir' | 'ls' | 'all' | None
    period:       Optional[str]  # 'realtime' | '24h' | '7j' | '30j' | 'tout' | None
    query_type:   str             # 'realtime' | 'historical' | 'anomaly' | 'report' | 'security' | 'simple' | 'unknown'
    is_data_query: bool           # True → badge + outils attendus dans la réponse
    raw_question:  str


def analyze(question: str, history: list[dict] | None = None) -> Intent:
    """
    Analyse la question et retourne un Intent structuré.
    history : liste de {'role': 'user'|'assistant', 'content': str}
    """
    q = question.lower().strip()

    # ── Résolution des pronoms ambigus ───────────────────────────────────────
    # Détecte les questions de suivi : courtes OU commençant par un connecteur
    _FOLLOWUP_STARTS = (
        'et ', 'et le ', 'et la ', 'et les ', 'et pour ',
        "qu'en est", 'montre', 'affiche', 'donne', 'ok et ',
        'mais ', 'alors ', 'donc ', 'sinon ', 'par rapport',
    )
    is_ambiguous = len(q.split()) <= 5 or any(q.startswith(p) for p in _FOLLOWUP_STARTS)
    context_sensor: Optional[str] = None
    if is_ambiguous and history:
        for msg in reversed(history[-8:]):
            found = _detect_sensor(msg.get('content', '').lower())
            if found and found != 'all':
                context_sensor = found
                break

    # ── Détection capteur ────────────────────────────────────────────────────
    sensor = _detect_sensor(q) or context_sensor

    # ── Détection période ────────────────────────────────────────────────────
    period = _detect_period(q)

    # ── Détection type de query ──────────────────────────────────────────────
    query_type = _detect_query_type(q)

    # ── is_data_query : la réponse doit contenir des données réelles ─────────
    is_data = query_type not in ('simple', 'security') and q not in ('', ' ')

    return Intent(
        sensor_type   = sensor,
        period        = period,
        query_type    = query_type,
        is_data_query = is_data,
        raw_question  = question,
    )


# ── Helpers privés ────────────────────────────────────────────────────────────

def _detect_sensor(text: str) -> Optional[str]:
    # Termes génériques "tous capteurs" → court-circuit direct
    if any(term in text for term in _GENERIC_ALL_TERMS):
        return 'all'
    scores: dict[str, int] = {}
    for stype, keywords in _SENSOR_VOCAB.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            scores[stype] = hits
    if not scores:
        return None
    top = max(scores.values())
    winners = [k for k, v in scores.items() if v == top]
    # Plusieurs types à égalité → requête globale
    if len(winners) > 1:
        return 'all'
    return winners[0]


def _detect_period(text: str) -> Optional[str]:
    for period, keywords in _PERIOD_VOCAB.items():
        if any(kw in text for kw in keywords):
            return period
    return None


def _detect_query_type(text: str) -> str:
    # Priorité : security > report > prediction > recommendation > anomaly > realtime > historical > simple
    for qtype in ('security', 'report', 'prediction', 'recommendation', 'anomaly', 'realtime', 'historical', 'simple'):
        if any(kw in text for kw in _QUERY_TYPE_PATTERNS[qtype]):
            return qtype
    return 'unknown'


# ── Outils attendus par type de capteur ──────────────────────────────────────
# Utilisé par output_guard pour valider le routing

EXPECTED_TOOLS: dict[str, list[str]] = {
    'thl'            : ['realtime_data', 'thl_analysis'],
    'wm'             : ['realtime_data', 'wm_analysis'],
    'en'             : ['realtime_data', 'energy_analysis'],
    'gm'             : ['realtime_data', 'gm_analysis'],
    'fuel'           : ['fuel_analysis'],
    'pir'            : ['realtime_data'],
    'ls'             : ['realtime_data'],
    'sm'             : ['realtime_data'],
    'all'            : ['realtime_data', 'anomaly_detection'],
    'prediction'     : ['get_upcoming_predictions'],
    'recommendation' : ['get_recommendations'],
}
