"""Génération LLM : prompt contextuel, appel, validation et traduction EN/AR."""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re

from .config import DOMAIN_CONFIG

logger = logging.getLogger('aria.reco_engine')

# ── Prompt système — Chain-of-Thought obligatoire ─────────────────────────────
_SYSTEM_PROMPT = """Tu es ARIA, expert BMS senior. Génère une recommandation courte, concrète et personnalisée.

LANGUE OBLIGATOIRE : Réponds EXCLUSIVEMENT en français. Chaque champ (reasoning, title, description, action, root_cause) doit être rédigé en français. Aucun mot anglais n'est accepté.

PROCESSUS (dans cet ordre) :
1. reasoning   → 2-3 phrases en français : signal observé → hypothèse la plus probable → priorité justifiée
2. priority    → critical (< 4h) | high (aujourd'hui) | medium (cette semaine) | low (ce mois)
3. title       → MAX 60 chars en français : nom lisible du device + problème concis
4. description → 1-2 phrases en français UNIQUEMENT avec les chiffres présents dans le contexte — jamais inventés
5. action      → FORMAT PAR RÔLE (voir ci-dessous), en français
6. root_cause  → 1 phrase en français, cause retenue
7. estimated_saving_tnd → calcule UNIQUEMENT si les données de consommation sont présentes, sinon null

FORMAT ACTION PAR RÔLE :
- technicien   : "1. [outil/action] 2. [test] 3. [validation]" — max 3 étapes techniques
- gestionnaire : "Planifier [action] sous [délai]. Coût estimé : [TND si calculable, sinon omis]."
- directeur    : "[Statut] — [1 action décisionnelle]." (max 2 lignes)

RÈGLES ABSOLUES :
- JSON valide uniquement, rien avant ni après
- Tous les champs texte en FRANÇAIS — zéro tolérance pour l'anglais
- Si actual_26h est absent : ne calcule PAS de consommation ni d'économie — utilise le score Chronos
- Utilise le NOM du device (pas l'ID brut) dans title et description
- Si corrélation cross-domaine → mentionne dans root_cause

{
  "reasoning": "...",
  "priority": "critical|high|medium|low",
  "title": "...",
  "description": "...",
  "action": "...",
  "root_cause": "...",
  "estimated_saving_tnd": <nombre ou null>
}"""
# ══════════════════════════════════════════════════════════════════════════════
# 7. CONSTRUCTION DU PROMPT LLM
# ══════════════════════════════════════════════════════════════════════════════

def _build_llm_prompt(
    signal          : dict,
    domain          : str,
    cfg             : dict,
    user_role       : str,
    device_ctx      : dict | None = None,
    cross_domain    : list | None = None,
    priority_boosted: bool        = False,
    rag_context     : str         = '',
    device_label    : str | None  = None,
) -> str:
    rec_type     = signal['rec_type']
    device_id    = signal.get('device_id') or 'ensemble du site'
    device_label = device_label or device_id   # fallback sur ID brut si résolution impossible
    label        = cfg['label']
    unit         = cfg['unit']

    role_ctx = {
        'technicien'  : "RÔLE TECHNICIEN : action=diagnostic technique (max 3 étapes), inclure outils et points de contrôle.",
        'gestionnaire': "RÔLE GESTIONNAIRE : action=décision opérationnelle avec délai et coût TND si calculable.",
        'directeur'   : "RÔLE DIRECTEUR : action=1 phrase décisionnelle max. description=2 lignes max.",
    }.get(user_role, "RÔLE GESTIONNAIRE : action=décision opérationnelle avec délai.")

    lines = [
        f"DOMAINE : {label}  |  DEVICE : {device_label}  |  TYPE : {rec_type}",
        role_ctx,
    ]

    if priority_boosted:
        lines.append(
            "IMPORTANT : Ce problème a été accepté mais non résolu depuis >24h — "
            "la priorité doit être rehaussée d'un cran."
        )

    def _line(label: str, val, unit_str: str = '') -> str | None:
        """Retourne une ligne de données uniquement si la valeur est disponible (non None)."""
        if val is None:
            return None
        suffix = f' {unit_str}' if unit_str else ''
        return f'  {label}: {val}{suffix}'

    lines += ["", "DONNÉES MESURÉES :"]

    if signal.get('no_consumption_data'):
        # Fallback Chronos : aucune donnée de consommation réelle disponible.
        # INTERDICTION ABSOLUE d'inventer des volumes, valeurs ou baselines.
        score = signal.get('chronos_score', 0)
        count = signal.get('ad_anomaly_count', 0)
        lines += [
            "  ⚠️  DONNÉES DE CONSOMMATION INDISPONIBLES.",
            "  RÈGLE NON NÉGOCIABLE : N'écris AUCUNE valeur numérique de consommation,",
            "  volume, baseline ou économie dans description/action/reasoning.",
            "  Base-toi UNIQUEMENT sur le score Chronos et le nombre de points anormaux.",
            f"  Score anomalie Chronos      : {score:.2f}/1.0 — ANOMALIE CONFIRMÉE",
            f"  Nombre de points anormaux   : {count}",
        ]
    elif signal.get('saving_unreliable'):
        # Volumes incohérents avec l'unité déclarée : seul l'écart relatif est exploitable.
        lines += [
            "  ⚠️  VOLUMES INCOHÉRENTS AVEC L'UNITÉ DÉCLARÉE DU COMPTEUR.",
            "  RÈGLE NON NÉGOCIABLE : N'écris AUCUN volume ni AUCUN montant en TND",
            "  dans description/action/reasoning ; estimated_saving_tnd = null.",
            "  Recommande de vérifier le paramétrage (unité, facteur d'échelle) du compteur.",
        ]
        if signal.get('deviation_pct') is not None:
            lines.append(f"  Déviation vs baseline       : +{signal['deviation_pct']}%")
    elif rec_type == 'OVERCONSUMPTION':
        raw_lines = [
            _line('Consommation réelle (26h)', signal.get('actual_26h'), unit),
            _line('Baseline normale (P50)   ', signal.get('baseline_p50_sum'), unit),
            _line('Seuil d\'alerte (P90)    ', signal.get('baseline_p90_sum'), unit),
            _line('Déviation vs baseline    ', f"+{signal.get('deviation_pct')}%" if signal.get('deviation_pct') is not None else None),
            _line('Excès consommé           ', signal.get('excess_units'), unit),
        ]
        peak = signal.get('peak_hours', [])
        if peak:
            raw_lines.append(f"  Heures de pic : {', '.join(str(h)+'h' for h in peak)}")
        lines += [l for l in raw_lines if l]
    elif rec_type == 'OPTIMIZATION':
        lines += [
            f"  Excès heures creuses ({signal.get('off_peak_hours')}) : {signal.get('off_peak_excess')} {unit}",
            f"  Tranches horaires concernées : {signal.get('hours_affected')}",
            f"  Économie mensuelle estimée   : {signal.get('estimated_saving_tnd')} TND",
        ]
    elif rec_type == 'BUDGET_ALERT':
        lines += [
            f"  Consommé ce mois (j1→j{signal.get('day_of_month')}) : {signal.get('current_month_so_far')} {unit}",
            f"  Mois précédent total        : {signal.get('last_month_total')} {unit}",
            f"  Projection fin de mois      : {signal.get('projected_total')} {unit}",
            f"  Dépassement projeté         : +{signal.get('overage_pct')}%",
        ]
    elif rec_type == 'MAINTENANCE':
        lines += [
            f"  Croissance sur 7 jours      : +{signal.get('trend_growth_pct')}%",
            f"  Valeur J-7                  : {signal.get('day1_value')} {unit}/j",
            f"  Valeur aujourd'hui          : {signal.get('day7_value')} {unit}/j",
            f"  Jours de hausse consécutifs : {signal.get('monotone_days')}/7",
        ]
    elif rec_type == 'LEAK_RISK':
        lines += [
            f"  Excès nocturne ({signal.get('hours_range')}) : {signal.get('nocturnal_excess')} {unit}",
            f"  Coût mensuel si persistant  : {signal.get('estimated_saving_tnd')} TND",
        ]
    elif rec_type == 'EFFICIENCY':
        lines += [
            f"  Consommation véhicule (7j)  : {signal.get('vehicle_conso_7d')} {unit}",
            f"  Moyenne flotte              : {signal.get('fleet_mean_7d')} {unit}",
            f"  Écart vs flotte             : +{signal.get('over_pct')}%",
        ]

    if signal.get('chronos_score') is not None:
        flag = " — ANOMALIE CONFIRMÉE" if signal.get('chronos_flagged') else ""
        lines.append(f"  Score anomalie Chronos      : {signal['chronos_score']:.2f}/1.0{flag}")

    # Contexte historique
    if device_ctx:
        has_ctx = any([
            device_ctx.get('recent_alerts'),
            device_ctx.get('chronos_trend_4w'),
            device_ctx.get('past_interventions'),
            device_ctx.get('dismissed_7d', 0) > 0,
        ])
        if has_ctx:
            lines += ["", "HISTORIQUE DU DEVICE :"]

            if device_ctx.get('recent_alerts'):
                lines.append("  Alertes récentes (7j) :")
                for a in device_ctx['recent_alerts'][:2]:
                    lines.append(f"    [{a['sev'].upper()}] {a['msg']}")

            trend = device_ctx.get('chronos_trend_4w', [])
            if len(trend) >= 2:
                scores = [w['avg_score'] for w in trend]
                if scores[-1] > scores[0] + 0.1:
                    direction = f"HAUSSE ({scores[0]:.2f} -> {scores[-1]:.2f})"
                elif scores[-1] < scores[0] - 0.1:
                    direction = f"baisse ({scores[0]:.2f} -> {scores[-1]:.2f})"
                else:
                    direction = f"stable ({scores[-1]:.2f})"
                lines.append(f"  Tendance Chronos 4 semaines : {direction}")

            if device_ctx.get('past_interventions'):
                lines.append("  Dernières interventions :")
                for i in device_ctx['past_interventions'][:2]:
                    saving_str = f" — {i['saving']:.1f} TND économisés" if i.get('saving') else ""
                    lines.append(f"    [{i['status'].upper()}] {i['title']}{saving_str}")

            if device_ctx.get('dismissed_7d', 0) > 0:
                lines.append(
                    f"  {device_ctx['dismissed_7d']} alerte(s) de ce type ignorée(s) cette semaine "
                    f"— la recommandation doit apporter une valeur nouvelle."
                )

    # Corrélation cross-domaine
    if cross_domain:
        lines += ["", "CORRÉLATION CROSS-DOMAINE (anomalies simultanées) :"]
        for cd in cross_domain[:3]:
            d_label = DOMAIN_CONFIG.get(cd['domain'], {}).get('label', cd['domain'])
            lines.append(
                f"  {d_label} : {cd['anomaly_count']} anomalie(s), score {cd['avg_score']:.2f}"
            )
        lines.append(
            "  -> Considère une origine commune possible "
            "(infrastructure partagée, événement bâtiment)."
        )

    # Base de connaissance RAG
    if rag_context:
        lines += ["", rag_context]

    lines += ["", "Génère la recommandation JSON en suivant le processus obligatoire."]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 8. APPEL LLM
# ══════════════════════════════════════════════════════════════════════════════

_LLM_CALL_TIMEOUT = 90  # secondes max par appel LLM dans le moteur de reco

_REASONING_MIN_LEN = 30
_REASONING_PLACEHOLDER = re.compile(
    r'\b(placeholder|valeur|value|\[.*?\]|\{.*?\}|xxx|todo|tbd|exemple|example)\b',
    re.IGNORECASE,
)


def _validate_reasoning(reasoning: str | None) -> str | None:
    """Valide le champ reasoning avant persistance — rejette les placeholders et textes vides."""
    if not reasoning or not isinstance(reasoning, str):
        return None
    cleaned = reasoning.strip()
    if len(cleaned) < _REASONING_MIN_LEN:
        return None
    if _REASONING_PLACEHOLDER.search(cleaned):
        return None
    return cleaned


def _call_llm(prompt: str, llm=None) -> dict | None:
    def _invoke():
        from langchain_core.messages import SystemMessage, HumanMessage
        _llm = llm
        if _llm is None:
            from mcp_client.llm_factory import LLMFactory
            _llm, _model, _backend = LLMFactory().create()
            logger.info("[reco:LLM] Instance %s/%s (thread %s)", _backend, _model,
                        __import__('threading').current_thread().name)
        response = _llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        content = response.content if hasattr(response, 'content') else str(response)
        return _parse_json_response(content)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke)
            return future.result(timeout=_LLM_CALL_TIMEOUT)
    except concurrent.futures.TimeoutError:
        logger.warning("[reco:LLM] Timeout après %ds.", _LLM_CALL_TIMEOUT)
        return None
    except Exception as exc:
        logger.warning("[reco:LLM] Appel échoué : %s", exc)
        return None


def _parse_json_response(raw: str) -> dict | None:
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'(\{[\s\S]*\})',
    ]
    for pattern in patterns:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1).strip())
                if isinstance(parsed, dict) and 'title' in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, dict) and 'title' in parsed:
            return parsed
    except Exception:
        pass
    return None


# ── Traduction EN/AR de la recommandation générée (best-effort, un seul appel) ──
# La plateforme ARIA affiche l'UI en fr/en/ar (LanguageService Angular) mais le
# moteur de recommandations raisonne et génère toujours en français (cf. _SYSTEM_PROMPT
# ci-dessus) — un seul "cerveau" garantit une reasoning/priorité cohérente quelle que
# soit la langue lue. On traduit ensuite la surface textuelle (title/description/
# action/reasoning) en un seul appel bon marché, stockée dans la colonne `i18n`.
# Best-effort : en cas d'échec, la lecture retombe sur le français (voir routes/recommendations.py).
_TRANSLATE_TIMEOUT = 30  # secondes — traduction courte, doit rester rapide

_TRANSLATE_SYSTEM_PROMPT = """Tu es un traducteur technique pour une plateforme de gestion de bâtiment (BMS).
Traduis les champs JSON fournis (title, description, action, reasoning) du français vers l'anglais ET l'arabe.

RÈGLES ABSOLUES :
- Conserve EXACTEMENT tous les nombres, unités (kWh, m³, TND, %) et noms de devices — ne les traduis jamais, ne les recalcule jamais
- Conserve le ton et le niveau de détail de chaque champ (ne résume pas, ne développe pas)
- Si "reasoning" est null ou absent, renvoie null pour reasoning dans les deux langues
- JSON valide uniquement, rien avant ni après, exactement cette forme :

{
  "en": {"title": "...", "description": "...", "action": "...", "reasoning": "..." | null},
  "ar": {"title": "...", "description": "...", "action": "...", "reasoning": "..." | null}
}"""


def _parse_translation_response(raw: str) -> dict | None:
    """Extrait {"en": {...}, "ar": {...}} de la réponse LLM. None si structure invalide."""
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'(\{[\s\S]*\})',
    ]
    parsed = None
    for pattern in patterns:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                candidate = json.loads(m.group(1).strip())
                if isinstance(candidate, dict) and 'en' in candidate and 'ar' in candidate:
                    parsed = candidate
                    break
            except json.JSONDecodeError:
                continue
    if parsed is None:
        try:
            candidate = json.loads(raw.strip())
            if isinstance(candidate, dict) and 'en' in candidate and 'ar' in candidate:
                parsed = candidate
        except Exception:
            return None
    if parsed is None:
        return None

    result = {}
    for lang in ('en', 'ar'):
        fields = parsed.get(lang)
        if not isinstance(fields, dict):
            continue
        if not fields.get('title') or not fields.get('description') or not fields.get('action'):
            continue  # traduction incomplète — inutilisable, on la rejette pour ce lang
        result[lang] = {
            'title'      : str(fields['title']).strip(),
            'description': str(fields['description']).strip(),
            'action'     : str(fields['action']).strip(),
            'reasoning'  : (str(fields['reasoning']).strip() if fields.get('reasoning') else None),
        }
    return result or None


def _translate_recommendation(fr_fields: dict, llm=None) -> dict | None:
    """Traduit title/description/action/reasoning FR -> EN/AR en un seul appel LLM.

    Best-effort : ne bloque jamais la génération de la recommandation. En cas
    d'échec/timeout, retourne None — la lecture (routes/recommendations.py) retombe
    alors sur le contenu français canonique, sans jamais mélanger les langues."""
    payload = json.dumps({
        'title'      : fr_fields.get('title'),
        'description': fr_fields.get('description'),
        'action'     : fr_fields.get('action'),
        'reasoning'  : fr_fields.get('reasoning'),
    }, ensure_ascii=False)

    def _invoke():
        from langchain_core.messages import SystemMessage, HumanMessage
        _llm = llm
        if _llm is None:
            from mcp_client.llm_factory import LLMFactory
            _llm, _model, _backend = LLMFactory().create()
        response = _llm.invoke([
            SystemMessage(content=_TRANSLATE_SYSTEM_PROMPT),
            HumanMessage(content=payload),
        ])
        content = response.content if hasattr(response, 'content') else str(response)
        return _parse_translation_response(content)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke)
            return future.result(timeout=_TRANSLATE_TIMEOUT)
    except concurrent.futures.TimeoutError:
        logger.warning("[reco:translate] Timeout après %ds — contenu servi en français uniquement.", _TRANSLATE_TIMEOUT)
        return None
    except Exception as exc:
        logger.warning("[reco:translate] Échec traduction (contenu servi en français) : %s", exc)
        return None
