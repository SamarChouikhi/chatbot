"""
Moteur de scoring pour un CaseResult ARIA.

Dimensions évaluées (pondérées) :
  tool_routing   30% — ARIA a-t-elle appelé les bons outils ?
  badge          20% — badge de sévérité présent pour les queries 'data' ?
  format         15% — longueur cohérente avec le type de query ?
  cleanliness    20% — pas d'hallucinations / patterns interdits ?
  content        15% — mots-clés attendus présents, interdits absents ?
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from eval.cases import EvalCase

# ── Constantes ────────────────────────────────────────────────────────────────

BADGES = {'🔴', '🟠', '🟡', '🟢'}

# Patterns qui indiquent une hallucination ou une réponse bâclée
HALLUCINATION_PATTERNS: list[str] = [
    '[value]', '[ID]', '[données]', '[capteur]', '[device]',
    'placeholder', 'N/A (', '{{', '}}',
    'je ne suis pas sûr', "je n'ai pas accès",
    'données fictives', 'exemple de réponse',
]

# Débuts de réponse interdits (filler phrases)
FORBIDDEN_STARTS: list[str] = [
    'Bien sûr', 'Absolument', 'Certainement', 'Parfait',
    'Bien entendu', 'Avec plaisir',
]

# Poids par dimension
WEIGHTS = {
    'tool_routing': 0.30,
    'badge':        0.20,
    'format':       0.15,
    'cleanliness':  0.20,
    'content':      0.15,
}


# ── Dataclass résultat ────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case:         EvalCase
    tools_called: list[str]      # noms des outils MCP (pas les labels)
    response:     str
    duration:     float
    error:        Optional[str] = None

    # Scores par dimension [0.0 – 1.0]
    tool_routing_score:  float = field(default=0.0, init=False)
    badge_score:         float = field(default=0.0, init=False)
    format_score:        float = field(default=0.0, init=False)
    cleanliness_score:   float = field(default=0.0, init=False)
    content_score:       float = field(default=0.0, init=False)
    overall_score:       float = field(default=0.0, init=False)

    # Détail humain (pour le rapport)
    details: dict = field(default_factory=dict, init=False)

    def compute(self) -> None:
        """Calcule tous les scores et le score global pondéré."""
        if self.error:
            self.details['error'] = self.error
            return

        r     = self.response
        tools = set(self.tools_called)

        # ── 1. Tool routing ───────────────────────────────────────────────────
        if not self.case.expected_tools:
            self.tool_routing_score = 1.0
            self.details['tool_routing'] = 'n/a (aucun outil attendu)'
        else:
            hits = [t for t in self.case.expected_tools if t in tools]
            self.tool_routing_score = len(hits) / len(self.case.expected_tools)
            self.details['tool_routing'] = (
                f'{len(hits)}/{len(self.case.expected_tools)} outils appelés: {hits}'
            )

        # ── 2. Badge de sévérité ──────────────────────────────────────────────
        has_badge = any(b in r for b in BADGES)
        if self.case.format_type == 'data':
            self.badge_score = 1.0 if has_badge else 0.0
            self.details['badge'] = 'présent' if has_badge else 'ABSENT (query data — requis)'
        else:
            self.badge_score = 1.0   # non requis pour les queries simples
            self.details['badge'] = 'n/a (query simple)'

        # Badge spécifique attendu (override si précisé)
        if self.case.expected_badge and has_badge:
            badge_ok = self.case.expected_badge in r
            if not badge_ok:
                self.badge_score = max(self.badge_score * 0.5, 0.0)
                self.details['badge'] += f' — mauvais badge (attendu {self.case.expected_badge})'

        # ── 3. Format / longueur ─────────────────────────────────────────────
        words = len(r.split())
        if self.case.format_type == 'simple':
            if words <= self.case.max_words:
                self.format_score = 1.0
                self.details['format'] = f'OK ({words} mots ≤ {self.case.max_words})'
            else:
                self.format_score = 0.5
                self.details['format'] = f'TROP LONG ({words} mots > {self.case.max_words})'
        else:
            if words >= self.case.min_words:
                self.format_score = 1.0
                self.details['format'] = f'OK ({words} mots ≥ {self.case.min_words})'
            else:
                self.format_score = 0.5
                self.details['format'] = f'TROP COURT ({words} mots < {self.case.min_words})'

        # ── 4. Propreté / anti-hallucination ─────────────────────────────────
        found_halluc = [p for p in HALLUCINATION_PATTERNS if p.lower() in r.lower()]
        bad_start    = next((s for s in FORBIDDEN_STARTS if r.startswith(s)), None)
        issues = found_halluc + ([f'début interdit: "{bad_start}"'] if bad_start else [])

        self.cleanliness_score = 0.0 if issues else 1.0
        self.details['cleanliness'] = f'issues: {issues}' if issues else 'OK'

        # ── 5. Contenu attendu ───────────────────────────────────────────────
        r_lower = r.lower()
        must_hits     = [k for k in self.case.must_contain     if k.lower() in r_lower]
        must_not_hits = [k for k in self.case.must_not_contain if k.lower() in r_lower]

        contain_ratio = (
            len(must_hits) / len(self.case.must_contain)
            if self.case.must_contain else 1.0
        )
        not_contain_ok = 1.0 if not must_not_hits else 0.0

        self.content_score = contain_ratio * not_contain_ok
        self.details['content'] = (
            f'must_contain: {len(must_hits)}/{len(self.case.must_contain)} | '
            f'must_not: {must_not_hits or "OK"}'
        )

        # ── Score global pondéré ─────────────────────────────────────────────
        self.overall_score = (
            self.tool_routing_score * WEIGHTS['tool_routing'] +
            self.badge_score        * WEIGHTS['badge']        +
            self.format_score       * WEIGHTS['format']       +
            self.cleanliness_score  * WEIGHTS['cleanliness']  +
            self.content_score      * WEIGHTS['content']
        )


# ── Agrégats par type de capteur ──────────────────────────────────────────────

def aggregate_by_type(results: list[CaseResult]) -> dict[str, dict]:
    """Retourne les moyennes par type de capteur."""
    from collections import defaultdict
    buckets: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        buckets[r.case.sensor_type].append(r)

    out = {}
    for stype, rs in sorted(buckets.items()):
        valid = [r for r in rs if not r.error]
        if not valid:
            out[stype] = {'n': len(rs), 'errors': len(rs), 'overall': 0.0}
            continue
        out[stype] = {
            'n'            : len(rs),
            'errors'       : len(rs) - len(valid),
            'overall'      : sum(r.overall_score      for r in valid) / len(valid),
            'tool_routing' : sum(r.tool_routing_score for r in valid) / len(valid),
            'badge'        : sum(r.badge_score        for r in valid) / len(valid),
            'format'       : sum(r.format_score       for r in valid) / len(valid),
            'cleanliness'  : sum(r.cleanliness_score  for r in valid) / len(valid),
            'content'      : sum(r.content_score      for r in valid) / len(valid),
        }
    return out


def global_scores(results: list[CaseResult]) -> dict[str, float]:
    """Moyennes globales sur tous les cas valides."""
    valid = [r for r in results if not r.error]
    if not valid:
        return {}
    dims = ['tool_routing_score', 'badge_score', 'format_score',
            'cleanliness_score', 'content_score', 'overall_score']
    return {d: sum(getattr(r, d) for r in valid) / len(valid) for d in dims}
