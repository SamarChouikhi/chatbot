"""
Génération des rapports d'évaluation ARIA.

  print_report(results)   → rapport coloré dans le terminal
  save_json(results)      → fichier JSON horodaté pour suivi de régression
  diff_runs(old, new)     → comparaison avant/après (Δ scores)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from eval.metrics import CaseResult, aggregate_by_type, global_scores, WEIGHTS

# ── Constantes visuelles ──────────────────────────────────────────────────────

_W  = 72          # largeur totale du rapport
_BW = 22          # largeur de la barre de progression

DIMENSION_LABELS: dict[str, str] = {
    'tool_routing_score': 'Routing outils MCP',
    'badge_score'       : 'Badge sévérité',
    'format_score'      : 'Format réponse',
    'cleanliness_score' : 'Propreté (anti-halluc.)',
    'content_score'     : 'Contenu attendu',
    'overall_score'     : 'SCORE GLOBAL',
}

WEIGHT_LABELS: dict[str, str] = {
    'tool_routing_score': f"({int(WEIGHTS['tool_routing']*100)}%)",
    'badge_score'       : f"({int(WEIGHTS['badge']*100)}%)",
    'format_score'      : f"({int(WEIGHTS['format']*100)}%)",
    'cleanliness_score' : f"({int(WEIGHTS['cleanliness']*100)}%)",
    'content_score'     : f"({int(WEIGHTS['content']*100)}%)",
    'overall_score'     : '',
}


# ── Helpers visuels ───────────────────────────────────────────────────────────

def _bar(score: float, width: int = _BW) -> str:
    filled = round(score * width)
    color  = (
        '\033[92m' if score >= 0.80 else
        '\033[93m' if score >= 0.60 else
        '\033[91m'
    )
    return f'{color}{"█" * filled}{"░" * (width - filled)}\033[0m'


def _pct(score: float) -> str:
    color = (
        '\033[92m' if score >= 0.80 else
        '\033[93m' if score >= 0.60 else
        '\033[91m'
    )
    return f'{color}{score:5.1%}\033[0m'


def _sep(char: str = '─') -> str:
    return '  ' + char * _W


# ── Rapport principal ─────────────────────────────────────────────────────────

def print_report(results: list[CaseResult]) -> None:
    valid  = [r for r in results if not r.error]
    errors = [r for r in results if r.error]

    print('\n' + '  ' + '═' * _W)
    print(f'  {"ARIA — RAPPORT D\'ÉVALUATION":^{_W}}')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M:%S"):^{_W}}')
    print('  ' + '═' * _W)

    # ── Par type de capteur ───────────────────────────────────────────────────
    print(f'\n  {"Type":<10} {"Score global":<{_BW+8}} {"N":>3}  {"Erreurs":>7}  {"Routing":>8}  {"Badge":>7}')
    print(_sep())

    by_type = aggregate_by_type(results)
    for stype, data in by_type.items():
        if data.get('errors', 0) == data['n']:
            print(f'  {stype:<10} \033[91m{"TOUTES ERREURS":<{_BW+8}}\033[0m {data["n"]:>3}  {data["errors"]:>7}')
            continue
        bar     = _bar(data['overall'])
        routing = _pct(data.get('tool_routing', 0))
        badge   = _pct(data.get('badge', 0))
        print(
            f'  {stype:<10} {bar} {_pct(data["overall"])}  '
            f'{data["n"]:>3}  {data.get("errors",0):>7}  {routing}  {badge}'
        )

    # ── Scores globaux par dimension ──────────────────────────────────────────
    print(f'\n  {"Dimension":<28} {"Poids":>6}  {"Score":<{_BW+8}}')
    print(_sep())

    gscores = global_scores(results)
    for dim, label in DIMENSION_LABELS.items():
        if dim not in gscores:
            continue
        score  = gscores[dim]
        weight = WEIGHT_LABELS.get(dim, '')
        sep    = '  ' + '─' * _W if dim == 'overall_score' else ''
        if sep:
            print(sep)
        print(
            f'  {label:<28} {weight:>6}  '
            f'{_bar(score)} {_pct(score)}'
        )

    # ── Cas échoués ───────────────────────────────────────────────────────────
    failed = [r for r in valid if r.overall_score < 0.70]
    if failed:
        print(f'\n  CAS NÉCESSITANT ATTENTION ({len(failed)}) :')
        print(_sep('─'))
        for r in sorted(failed, key=lambda x: x.overall_score):
            q = r.case.question[:55] + ('…' if len(r.case.question) > 55 else '')
            print(
                f'  [{r.case.id}] {_pct(r.overall_score)}  '
                f'{r.case.sensor_type:<8}  {q}'
            )
            # Affiche la dimension la plus faible
            worst_dim = min(
                ['tool_routing_score', 'badge_score', 'format_score',
                 'cleanliness_score', 'content_score'],
                key=lambda d: getattr(r, d),
            )
            worst_val = getattr(r, worst_dim)
            detail    = r.details.get(worst_dim.replace('_score', ''), '')
            print(
                f'  {"":14} ↳ faiblesse: {DIMENSION_LABELS[worst_dim]} '
                f'({worst_val:.0%})  {detail}'
            )

    # ── Cas en erreur ─────────────────────────────────────────────────────────
    if errors:
        print(f'\n  ERREURS DE CONNEXION / TIMEOUT ({len(errors)}) :')
        print(_sep('─'))
        for r in errors:
            print(f'  [{r.case.id}]  {r.case.sensor_type:<8}  {r.error}')

    # ── Score final ───────────────────────────────────────────────────────────
    overall = gscores.get('overall_score', 0.0)
    verdict = (
        '★ Excellent'   if overall >= 0.90 else
        '✓ Bon'         if overall >= 0.80 else
        '△ Acceptable'  if overall >= 0.65 else
        '✗ À améliorer'
    )
    print(f'\n  {"VERDICT":^{_W}}')
    print('  ' + '═' * _W)
    print(
        f'  {_bar(overall, _W - 12)} {_pct(overall)}'
    )
    print(f'  {verdict:^{_W}}')
    print(
        f'  {len(valid)} cas valides  |  '
        f'{len(failed)} sous seuil  |  '
        f'{len(errors)} erreurs\n'
    )
    print('  ' + '═' * _W + '\n')


# ── Export JSON ───────────────────────────────────────────────────────────────

def save_json(results: list[CaseResult], path: Path | None = None) -> Path:
    if path is None:
        Path('eval/results').mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = Path(f'eval/results/aria_eval_{ts}.json')

    gscores  = global_scores(results)
    by_type  = aggregate_by_type(results)

    payload = {
        'timestamp'    : datetime.now().isoformat(),
        'total_cases'  : len(results),
        'valid_cases'  : sum(1 for r in results if not r.error),
        'error_cases'  : sum(1 for r in results if r.error),
        'global_scores': {k: round(v, 4) for k, v in gscores.items()},
        'by_type'      : {
            t: {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}
            for t, d in by_type.items()
        },
        'cases': [
            {
                'id'           : r.case.id,
                'sensor_type'  : r.case.sensor_type,
                'question'     : r.case.question,
                'description'  : r.case.description,
                'overall_score': round(r.overall_score, 4),
                'dimensions'   : {
                    'tool_routing' : round(r.tool_routing_score, 4),
                    'badge'        : round(r.badge_score, 4),
                    'format'       : round(r.format_score, 4),
                    'cleanliness'  : round(r.cleanliness_score, 4),
                    'content'      : round(r.content_score, 4),
                },
                'tools_called' : r.tools_called,
                'duration_s'   : r.duration,
                'error'        : r.error,
                'details'      : r.details,
                'response_len' : len(r.response.split()),
            }
            for r in results
        ],
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


# ── Comparaison de runs (régression) ──────────────────────────────────────────

def diff_runs(old_path: str | Path, new_path: str | Path) -> None:
    """Affiche le delta entre deux fichiers JSON de résultats."""
    old = json.loads(Path(old_path).read_text(encoding='utf-8'))
    new = json.loads(Path(new_path).read_text(encoding='utf-8'))

    print('\n  COMPARAISON AVANT → APRÈS')
    print(_sep('═'))

    old_g = old.get('global_scores', {})
    new_g = new.get('global_scores', {})

    dims = ['tool_routing_score', 'badge_score', 'format_score',
            'cleanliness_score', 'content_score', 'overall_score']

    for dim in dims:
        label = DIMENSION_LABELS.get(dim, dim)
        o     = old_g.get(dim, 0)
        n     = new_g.get(dim, 0)
        delta = n - o
        arrow = '\033[92m▲\033[0m' if delta > 0.005 else '\033[91m▼\033[0m' if delta < -0.005 else '='
        print(f'  {label:<28}  {o:.1%} → {n:.1%}  {arrow} {delta:+.1%}')

    print()
