import asyncio
import json
import logging
from functools import partial
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.db      import get_engine, get_history_db
from api.session import new_thread

router = APIRouter()
log    = logging.getLogger('aria.api')

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


@router.get('/realtime')
async def realtime():
    try:
        from mcp_server.tools.sensors import realtime_data
        parsed = json.loads(realtime_data('thl'))
        if parsed.get('status') == 'error':
            raise HTTPException(503, parsed.get('message'))
        return parsed
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post('/new')
async def new_conversation(
    user_id   : str = Query('default_user'),
    session_id: str = Query(None),
):
    sid, tid = new_thread(session_id, user_id)
    log.info(f'[NEW THREAD] {user_id} session={sid} → {tid}')
    return {'thread_id': tid, 'session_id': sid, 'status': 'new_conversation'}


@router.post('/refresh')
async def refresh():
    if not _agent:
        raise HTTPException(503, 'Agent non disponible')
    await _agent.refresh_context()
    return {'status': 'refreshed'}


@router.post('/reset-keys')
async def reset_key_state():
    """Réinitialise l'état des clés API (à appeler après le reset journalier OpenRouter/Groq)."""
    try:
        from mcp_client.config   import KEY_STATE_FILE
        from mcp_client.llm_factory import KeyStateManager
        km = KeyStateManager(KEY_STATE_FILE)
        km.reset()
        if _agent and _agent.is_ready():
            from langgraph.prebuilt import create_react_agent
            from mcp_client.llm_factory import LLMFactory
            factory = LLMFactory()
            async with _agent._lock:
                _agent.llm, _agent.model_name, _agent.backend = factory.create()
                _agent.executor = create_react_agent(
                    model=_agent.llm, tools=_agent.tools,
                    prompt=_agent._cached_prompt,
                    checkpointer=_agent._checkpointer,
                )
                _agent._invalidate_executor_cache()
        return {'status': 'reset', 'backend': _agent.backend if _agent else 'unknown'}
    except Exception as e:
        raise HTTPException(500, f'Reset échoué : {e}')


@router.get('/health')
async def health():
    db = get_history_db()
    return {
        'status'    : 'OK' if (_agent and _agent.is_ready()) else 'NOT_READY',
        'version'   : '6.0.0',
        'backend'   : _agent.backend    if _agent else 'none',
        'model'     : _agent.model_name if _agent else 'none',
        'history_db': db.is_available() if db else False,
    }


# ── Import CSV → daily_* ───────────────────────────────────────────────────────

class CsvImportRequest(BaseModel):
    domain:   str   # energy | water | gas | fuel
    csv_path: str   # chemin absolu ou relatif au fichier CSV


@router.post('/import-csv')
async def import_csv_endpoint(req: CsvImportRequest):
    """
    Importe un fichier CSV dans les tables daily_* de bw_samar.
    Idempotent — utilise INSERT ON DUPLICATE KEY UPDATE.
    """
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    from api.pipeline.csv_importer import import_csv

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            partial(import_csv, engine, req.csv_path, req.domain),
        )
        return {'status': 'ok', **result}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.error('import_csv_endpoint : %s', e, exc_info=True)
        raise HTTPException(500, str(e))


@router.post('/import-all-csv')
async def import_all_csv_endpoint():
    """
    Importe les 4 CSV définis dans les config.yaml AD (energy, water, gas, fuel).
    Utile pour la migration initiale complète.
    """
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    from api.pipeline.csv_importer import import_all_from_config

    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            None,
            partial(import_all_from_config, engine),
        )
        ok      = sum(1 for r in results.values() if r.get('status') == 'ok')
        skipped = sum(1 for r in results.values() if r.get('status') == 'skipped')
        errors  = sum(1 for r in results.values() if r.get('status') == 'error')
        return {
            'status':  'ok' if errors == 0 else 'partial',
            'summary': {'ok': ok, 'skipped': skipped, 'errors': errors},
            'details': results,
        }
    except Exception as e:
        log.error('import_all_csv_endpoint : %s', e, exc_info=True)
        raise HTTPException(500, str(e))


@router.post('/debug/run-ad')
async def debug_run_ad(domain: str = Query('water')):
    """
    TEST ONLY — déclenche le pipeline AD pour un domaine donné et retourne le routage hot/cold.
    """
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    from sqlalchemy import text
    from api.pipeline.ad_runner import _get_device_ages, _HOT_MIN_DAYS, _load_daily_fallback
    import asyncio
    from functools import partial
    from api.pipeline.scheduler import _run_for_date
    from datetime import date

    # Lecture des anciennetés actuelles
    ages = _get_device_ages(engine, domain)
    hot  = {d: n for d, n in ages.items() if n >  _HOT_MIN_DAYS}
    cold = {d: n for d, n in ages.items() if n <= _HOT_MIN_DAYS}

    return {
        'domain'        : domain,
        'threshold_days': _HOT_MIN_DAYS,
        'hot_devices'   : hot,
        'cold_devices'  : cold,
        'total_devices' : len(ages),
    }


@router.post('/debug/trigger-proactive')
async def trigger_proactive_now(userId: str = Query(...)):
    """
    TEST ONLY — déclenche le check proactif immédiatement pour un userId.
    Met à jour run_at des anomalies existantes à NOW() pour contourner la fenêtre 2h.
    """
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible')

    from sqlalchemy import text
    from api.session import get_or_create_thread
    from api.pipeline.proactive import run_proactive_check, persist_and_broadcast
    from api.pipeline.proactive_broadcaster import get_broadcaster

    # Force run_at = NOW() sur les anomalies existantes pour passer le filtre 2h
    with engine.begin() as conn:
        updated = conn.execute(text(
            "UPDATE ad_results SET run_at = NOW() WHERE is_anomaly = 1 AND anomaly_score >= 0.65 LIMIT 10"
        )).rowcount

    # Enregistre la session de l'utilisateur si elle n'existe pas
    get_or_create_thread(None, userId)

    alerts     = run_proactive_check(engine, [userId])
    broadcaster = get_broadcaster()
    persist_and_broadcast(engine, alerts, broadcaster)

    return {
        'status':          'ok',
        'anomalies_updated': updated,
        'alerts_generated':  len(alerts),
        'alerts':           [{'domain': a.domain, 'severity': a.severity, 'message': a.message} for a in alerts],
    }
