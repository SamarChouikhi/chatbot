"""
ARIA Evaluation Runner

Lance tous les cas de test contre l'API ARIA en streaming SSE,
collecte les outils appelés + la réponse finale, calcule les scores.

Usage:
    cd bws_pfe
    python -m eval.runner                          # tous les cas, fr
    python -m eval.runner --type WM                # filtrer par type de capteur
    python -m eval.runner --lang en                # tester en anglais
    python -m eval.runner --save                   # exporter JSON
    python -m eval.runner --base-url http://...    # ARIA sur autre hôte
    python -m eval.runner --delay 2.0              # pause entre requêtes (évite rate limit)
    python -m eval.runner --case thl_001,wm_003    # cas spécifiques
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from typing import AsyncIterator

import httpx

from eval.cases   import CASES, EvalCase
from eval.metrics import CaseResult
from eval.report  import print_report, save_json

DEFAULT_BASE_URL = 'http://localhost:8001'
DEFAULT_LANG     = 'fr'
DEFAULT_USER_ID  = 'eval_runner'

# Reverse-map tool_name depuis le champ 'tool_name' injecté dans agent.py.
# Si absent (vieille version), on tente de matcher sur le label partiel.
_LABEL_FRAGMENTS: dict[str, str] = {
    'eau'         : 'wm_analysis',
    'électrique'  : 'energy_analysis',
    'gaz'         : 'gm_analysis',
    'carburant'   : 'fuel_analysis',
    'thl'         : 'thl_analysis',
    'alerte'      : 'alerts_summary',
    'temps réel'  : 'realtime_data',
    'anomalie'    : 'anomaly_detection',
    'base de données': 'database_summary',
    'requête'     : 'execute_query',
    'table'       : 'list_tables',
    'description' : 'describe_table',
}


def _tool_from_event(payload: dict) -> str:
    """Extrait le nom de l'outil depuis un événement SSE de type 'tool'."""
    # Champ injecté par agent.py (après notre modification)
    if 'tool_name' in payload and payload['tool_name']:
        return payload['tool_name']
    # Fallback : heuristique sur le label humain
    label = payload.get('data', '').lower()
    for fragment, tool_name in _LABEL_FRAGMENTS.items():
        if fragment in label:
            return tool_name
    return payload.get('data', 'unknown_tool')


async def run_case(
    client:   httpx.AsyncClient,
    case:     EvalCase,
    base_url: str,
    lang:     str,
    delay:    float = 0.0,
) -> CaseResult:
    """Exécute un cas de test et retourne le CaseResult scoré."""
    if delay > 0:
        await asyncio.sleep(delay)

    thread_id  = f'eval_{case.id}_{uuid.uuid4().hex[:6]}'
    tools_seen: list[str] = []
    chunks:     list[str] = []
    start       = time.time()
    error: str | None     = None

    params = {
        'question': case.question,
        'userId'  : DEFAULT_USER_ID,
        'threadId': thread_id,
        'lang'    : lang,
    }

    try:
        async with client.stream(
            'GET', f'{base_url}/chat/stream',
            params=params,
            timeout=90.0,
        ) as resp:
            if resp.status_code != 200:
                error = f'HTTP {resp.status_code}'
            else:
                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith('data:'):
                        continue
                    try:
                        payload = json.loads(raw_line[5:].strip())
                    except json.JSONDecodeError:
                        continue

                    etype = payload.get('type')

                    if etype == 'tool':
                        tools_seen.append(_tool_from_event(payload))

                    elif etype == 'chunk':
                        chunk = payload.get('data', '')
                        if chunk:
                            chunks.append(chunk)

                    elif etype == 'error':
                        error = payload.get('data', 'erreur inconnue')
                        break

    except httpx.ConnectError:
        error = f'Connexion refusée — ARIA en ligne sur {base_url} ?'
    except httpx.TimeoutException:
        error = 'Timeout (90s dépassé)'
    except Exception as exc:
        error = str(exc)[:120]

    result = CaseResult(
        case         = case,
        tools_called = tools_seen,
        response     = ''.join(chunks).strip(),
        duration     = round(time.time() - start, 2),
        error        = error,
    )
    result.compute()
    return result


async def run_all(
    base_url:    str,
    lang:        str,
    save:        bool,
    type_filter: str | None,
    case_filter: list[str] | None,
    delay:       float,
) -> list[CaseResult]:

    # Sélection des cas
    cases = CASES
    if type_filter:
        cases = [c for c in cases if c.sensor_type == type_filter.upper()]
    if case_filter:
        ids   = {i.strip() for i in case_filter}
        cases = [c for c in cases if c.id in ids]

    if not cases:
        print('Aucun cas correspondant aux filtres.')
        return []

    print(f'\n  ARIA Eval  ·  {len(cases)} cas  ·  {base_url}  ·  lang={lang}')
    print(f'  {"ID":<14} {"Question":<52} {"Score":>6}  {"Dur":>6}')
    print('  ' + '─' * 82)

    results: list[CaseResult] = []

    async with httpx.AsyncClient() as client:
        for i, case in enumerate(cases):
            q_short = case.question[:50] + ('…' if len(case.question) > 50 else '')
            print(f'  {case.id:<14} {q_short:<52} ', end='', flush=True)

            result = await run_case(client, case, base_url, lang, delay if i > 0 else 0)
            results.append(result)

            score   = result.overall_score
            dur_str = f'{result.duration}s'

            if result.error:
                status = '\033[91mERR\033[0m'
                print(f'{status}  {dur_str:>6}  {result.error[:40]}')
            else:
                color  = '\033[92m' if score >= 0.8 else '\033[93m' if score >= 0.6 else '\033[91m'
                symbol = '✓' if score >= 0.7 else '✗'
                print(f'{color}{symbol} {score:.0%}\033[0m  {dur_str:>6}')

    from eval.report import print_report, save_json
    print_report(results)

    if save:
        path = save_json(results)
        print(f'  Résultats JSON → {path}\n')

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description='ARIA Evaluation Runner')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL,
                        help='URL de base de l\'API ARIA (défaut: %(default)s)')
    parser.add_argument('--lang',     default=DEFAULT_LANG,
                        help='Langue de test : fr | en | ar (défaut: %(default)s)')
    parser.add_argument('--save',     action='store_true',
                        help='Exporter les résultats en JSON')
    parser.add_argument('--type',     default=None,
                        help='Filtrer par sensor_type : THL | WM | EN | GM | FUEL | ...')
    parser.add_argument('--case',     default=None,
                        help='Cas spécifiques (virgule-séparés) : thl_001,wm_003')
    parser.add_argument('--delay',    type=float, default=1.0,
                        help='Pause (s) entre chaque requête (défaut: %(default)s)')
    args = parser.parse_args()

    case_list = [c.strip() for c in args.case.split(',')] if args.case else None

    asyncio.run(run_all(
        base_url    = args.base_url,
        lang        = args.lang,
        save        = args.save,
        type_filter = args.type,
        case_filter = case_list,
        delay       = args.delay,
    ))


if __name__ == '__main__':
    main()
