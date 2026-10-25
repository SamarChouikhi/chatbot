"""
Quality gate sur la réponse ARIA avant envoi à l'utilisateur.

Pipeline :
  1. check_output()   → QualityReport avec score [0.0–1.0]
  2. needs_retry()    → True si score < RETRY_THRESHOLD
  3. build_retry_hint() → instruction renforcée ajoutée à la question pour le retry

Règle absolue : UN SEUL retry. Si le retry échoue aussi, on retourne la meilleure réponse.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from mcp_client.preprocessor import Intent

# ── Constantes ────────────────────────────────────────────────────────────────

RETRY_THRESHOLD   = 0.60   # score en dessous duquel on retente
MIN_DATA_WORDS    = 15     # réponse data trop courte si < 15 mots
MAX_SIMPLE_WORDS  = 120    # réponse simple trop longue si > 120 mots

HALLUCINATION_SIGNALS: list[str] = [
    '[value]', '[id]', '[données]', '[capteur]', '[device]',
    'placeholder', 'n/a (', '{{', '}}',
    'données fictives', 'exemple de réponse',
    # Identifiants fictifs des few-shot du prompt système : leur présence = exemple recopié
    'exemple-',
    'je ne suis pas sûr', "je n'ai pas accès à ces données",
]

FILLER_STARTS: list[str] = [
    'Bien sûr', 'Absolument', 'Certainement', 'Parfait',
    'Bien entendu', 'Avec plaisir',
]

# Unités métier attendues par type de capteur dans une réponse data
_EXPECTED_UNITS: dict[str, list[str]] = {
    'thl' : ['°c', '%hr', '%'],
    'wm'  : ['m³', 'l/h', 'litre'],
    'en'  : ['kwh', 'kw', 'v', 'a', 'w', 'cos', 'thd'],
    'gm'  : ['m³', 'l/min'],
    'fuel': ['l/100', 'km', 'litre', ' l '],
    'pir' : ['passage', 'trafic', '%', 'count'],
    'ls'  : ['niveau', '%', 'low', 'critical', 'ok'],
}


# ── Dataclass rapport qualité ─────────────────────────────────────────────────

@dataclass
class QualityReport:
    # Dimensions binaires
    tools_called_ok:  bool = False
    length_ok:        bool = True
    is_clean:         bool = True
    has_units:        bool = True

    # Détails pour le retry hint
    missing_tools:    list[str] = field(default_factory=list)
    hallucinations:   list[str] = field(default_factory=list)
    too_short:        bool = False
    too_long:         bool = False

    # Score global [0.0–1.0]
    score:            float = 1.0

    def compute_score(self) -> None:
        """Calcule le score pondéré.

        Règle critique : si les outils n'ont pas été appelés OU si la réponse
        contient des hallucinations, le score est plafonné à 0.55 — en dessous
        du RETRY_THRESHOLD (0.60) — ce qui garantit un retry dans ces deux cas.
        """
        score = (
            (1.0 if self.tools_called_ok else 0.0) * 0.45 +
            (1.0 if self.length_ok       else 0.5) * 0.25 +
            (1.0 if self.is_clean        else 0.0) * 0.20 +
            (1.0 if self.has_units       else 0.5) * 0.10
        )
        if not self.tools_called_ok or not self.is_clean:
            score = min(score, 0.55)
        self.score = round(score, 3)


# ── Fonction principale ───────────────────────────────────────────────────────

def check_output(
    response:     str,
    tools_called: list[str],
    intent:       Intent,
) -> QualityReport:
    """
    Évalue la qualité de la réponse ARIA.

    response     : texte brut retourné par le LLM
    tools_called : liste des outils MCP effectivement appelés
    intent       : Intent produit par preprocessor.analyze()
    """
    r     = response.strip()
    r_low = r.lower()
    tools = set(tools_called)
    report = QualityReport()

    # ── 1. Outils appelés ────────────────────────────────────────────────────
    if not intent.is_data_query or not intent.sensor_type:
        report.tools_called_ok = True
    else:
        from mcp_client.preprocessor import EXPECTED_TOOLS
        expected = EXPECTED_TOOLS.get(intent.sensor_type, [])
        if not expected:
            report.tools_called_ok = True
        else:
            hits = [t for t in expected if t in tools]
            report.tools_called_ok = len(hits) >= 1
            report.missing_tools   = [t for t in expected if t not in tools]

    # ── 3. Longueur ──────────────────────────────────────────────────────────
    words = len(r.split())
    if intent.is_data_query and words < MIN_DATA_WORDS:
        report.length_ok = False
        report.too_short = True
    elif not intent.is_data_query and words > MAX_SIMPLE_WORDS:
        report.length_ok = False
        report.too_long  = True

    # ── 4. Propreté / hallucinations ─────────────────────────────────────────
    found = [s for s in HALLUCINATION_SIGNALS if s in r_low]
    bad_start = next((s for s in FILLER_STARTS if r.startswith(s)), None)
    report.hallucinations = found + ([bad_start] if bad_start else [])
    report.is_clean       = not report.hallucinations

    # ── 5. Unités métier ─────────────────────────────────────────────────────
    if intent.is_data_query and intent.sensor_type and intent.sensor_type != 'all':
        expected_units = _EXPECTED_UNITS.get(intent.sensor_type, [])
        if expected_units:
            report.has_units = any(u in r_low for u in expected_units)
        else:
            report.has_units = True
    else:
        report.has_units = True

    report.compute_score()
    return report


def needs_retry(report: QualityReport) -> bool:
    """True si la qualité est insuffisante et qu'un retry est justifié."""
    return report.score < RETRY_THRESHOLD


def build_retry_hint(question: str, report: QualityReport) -> str:
    """
    Construit la question enrichie pour le retry.
    Ajoute des instructions correctives précises sans révéler le scoring interne.
    """
    hints: list[str] = []

    if report.missing_tools:
        tools_str = ', '.join(report.missing_tools)
        hints.append(
            f'IMPORTANT: you MUST call the tool(s) [{tools_str}] '
            'before answering — do not answer from memory.'
        )
    if report.too_short:
        hints.append(
            'IMPORTANT: provide a complete analysis with a data table '
            'and interpretation — do not give a one-line answer.'
        )
    if report.hallucinations:
        hints.append(
            'IMPORTANT: only cite values retrieved from tools. '
            'Never use placeholders like [value] or fabricated data.'
        )

    if not hints:
        hints.append('IMPORTANT: call the relevant tool and provide a complete structured response.')

    hint_block = ' | '.join(hints)
    return f'[RETRY_HINT: {hint_block}]\n{question}'
