import os
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / '.env')

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from mcp_client.agent import AriaAgent
from api.db           import set_history_db, get_engine, ensure_tables, ensure_analytics_tables
from api.routes       import (chat_router, threads_router, feedback_router,
                               reports_router, system_router, employees_router, sessions_router,
                               analytics_router, proactive_router, recommendations_router)
from api.routes.chat    import set_agent as chat_set_agent
from api.routes.reports import set_agent as reports_set_agent
from api.routes.system  import set_agent as system_set_agent
from mcp_client.transcribe import transcribe_router
from mcp_client.vision     import vision_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s : %(message)s'
)
logger = logging.getLogger('aria.api')

# Agent singleton — évite une réinitialisation lors du hot-reload ou des tests
_agent: AriaAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    logger.info('ARIA API — Démarrage...')

    if _agent is None:
        _agent = AriaAgent()

    try:
        await _agent.initialize()
    except Exception as e:
        ExceptionGroup_ = getattr(__builtins__, 'ExceptionGroup', None)
        if ExceptionGroup_ is not None and isinstance(e, ExceptionGroup_):
            for sub in e.exceptions:
                logger.critical(f'Échec initialisation agent — {type(sub).__name__}: {sub}')
        else:
            logger.critical(f'Échec initialisation agent : {type(e).__name__}: {e}')
        app.state.agent_ready = False
        app.state.init_error  = str(e)
        app.state.agent       = None
        # La DB s'initialise avant le MCP — on l'enregistre même si le reste a échoué
        history = getattr(_agent, '_history', None)
        if history is not None:
            set_history_db(history)
            engine = get_engine()
            if engine:
                try:
                    ensure_tables(engine)
                    ensure_analytics_tables(engine)
                except Exception as te:
                    logger.warning(f'ensure_tables non bloquant : {te}')
        yield
        return

    chat_set_agent(_agent)
    reports_set_agent(_agent)
    system_set_agent(_agent)

    set_history_db(_agent.get_history_manager())
    engine = get_engine()
    if engine:
        try:
            ensure_tables(engine)
            ensure_analytics_tables(engine)
        except Exception as e:
            logger.warning(f'ensure_tables non bloquant : {e}')

    # Scheduler quotidien : agrégation IoT + détection d'anomalies à 03h00 UTC
    from api.pipeline import scheduler as _sched
    try:
        _sched.start(engine)
    except Exception as e:
        logger.warning(f'Scheduler non bloquant : {e}')

    app.state.agent_ready = True
    app.state.init_error  = None
    app.state.agent       = _agent

    _backend = getattr(_agent, 'backend', None) or '?'
    _model   = getattr(_agent, 'model_name', None) or '?'
    logger.info(f'ARIA READY : {_backend}/{_model}')
    yield

    logger.info('ARIA API — Arrêt en cours...')
    try:
        _sched.stop()
    except Exception:
        pass
    try:
        if _agent and _agent.is_ready() and hasattr(_agent, 'close'):
            await _agent.close()
    except Exception as e:
        logger.warning(f'Shutdown cleanup : {e}')
    logger.info('ARIA API arrêtée.')


app = FastAPI(
    title='ARIA API',
    version='6.0.0',
    lifespan=lifespan,
    # Docs désactivées en production pour ne pas exposer le schéma de l'API
    docs_url=None     if os.getenv('ENV', 'dev') == 'prod' else '/docs',
    redoc_url=None    if os.getenv('ENV', 'dev') == 'prod' else '/redoc',
    openapi_url=None  if os.getenv('ENV', 'dev') == 'prod' else '/openapi.json',
)

# allow_credentials=True est incompatible avec allow_origins=['*'] selon la spec CORS.
# En dev : wildcard + pas de credentials. En prod : origines explicites + credentials.
_raw_origins = os.getenv('CORS_ORIGINS', '').strip()
_env         = os.getenv('ENV', 'dev')

if not _raw_origins or _raw_origins == '*' or _env == 'dev':
    _allowed_origins   = ['*']
    _allow_credentials = False
    logger.warning('CORS: mode DEV — toutes les origines acceptées.')
else:
    _allowed_origins   = [o.strip() for o in _raw_origins.split(',') if o.strip()]
    _allow_credentials = True
    logger.info(f'CORS: origines autorisées → {_allowed_origins}')

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=None,
    allow_methods=['*'],
    allow_headers=['*'],
    allow_credentials=_allow_credentials,
    expose_headers=['X-Request-ID'],
)

@app.middleware('http')
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get('X-Request-ID') or str(uuid.uuid4())[:8]
    response = await call_next(request)
    response.headers['X-Request-ID'] = rid
    return response


app.include_router(chat_router)
app.include_router(threads_router)
app.include_router(feedback_router)
app.include_router(reports_router)
app.include_router(system_router)
app.include_router(employees_router)
app.include_router(sessions_router)
app.include_router(analytics_router)
app.include_router(proactive_router)
app.include_router(recommendations_router)
app.include_router(transcribe_router)
app.include_router(vision_router)


@app.get('/health', tags=['system'])
async def health(request: Request):
    ready = getattr(request.app.state, 'agent_ready', False)
    error = getattr(request.app.state, 'init_error', None)

    if not ready:
        return JSONResponse(
            status_code=503,
            content={'status': 'unavailable', 'error': error or 'Agent non initialisé'}
        )

    agent = getattr(request.app.state, 'agent', None)

    from mcp_server.db.connection import test_connection
    db = test_connection()

    return {
        'status' : 'ok',
        'backend': agent.backend    if agent else None,
        'model'  : agent.model_name if agent else None,
        'db'     : db,
    }


# Endpoint séparé pour les probes Kubernetes/Docker :
# /health = "le process répond" | /ready = "l'agent est opérationnel"
@app.get('/ready', tags=['system'])
async def ready(request: Request):
    if not getattr(request.app.state, 'agent_ready', False):
        return JSONResponse(status_code=503, content={'ready': False})
    return {'ready': True}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f'Erreur non gérée [{request.method} {request.url.path}] : {exc}', exc_info=True)
    # Stack trace en dev uniquement — ne pas exposer les détails internes en production
    detail = str(exc) if os.getenv('ENV', 'dev') == 'dev' else 'Erreur interne. Consultez les logs serveur.'
    return JSONResponse(status_code=500, content={'detail': detail})


if __name__ == '__main__':
    # Plusieurs workers partagent le même process mais pas la même mémoire MemorySaver.
    # Forcer workers=1 garantit la cohérence de l'historique en mémoire.
    workers = int(os.getenv('ARIA_WORKERS', '1'))
    if workers > 1:
        logger.warning(
            f'ARIA_WORKERS={workers} incompatible avec MemorySaver in-process. Forcé à 1.'
        )
        workers = 1

    uvicorn.run(
        'aria_api:app',
        host='0.0.0.0',
        port=int(os.getenv('ARIA_PORT', '8001')),
        reload=False,
        workers=workers,
        timeout_keep_alive=int(os.getenv('ARIA_KEEPALIVE', '30')),
        backlog=int(os.getenv('ARIA_BACKLOG', '128')),
        access_log=os.getenv('ARIA_ACCESS_LOG', 'true').lower() == 'true',
    )
