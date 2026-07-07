"""
Tests d'intégration ARIA API — FastAPI sans LLM ni MySQL réels.

Stratégie :
  - L'app FastAPI démarre via TestClient (Starlette/httpx) — même lifespan qu'en production.
  - AriaAgent est mocké : initialize() réussit, process/stream_process retournent
    des données prédéfinies.
  - MySQL, scheduler et MCP server sont patchés pour ne pas nécessiter d'infrastructure.

Note architecture: GET /health est géré par system_router (registré en premier dans
aria_api.py) qui retourne {'status': 'OK'|'NOT_READY', ...}. GET /ready (app-level)
retourne {'ready': bool} avec code 200/503.

Ce que ces tests vérifient :
  1. /health retourne status='OK' quand l'agent est prêt.
  2. /health retourne status='NOT_READY' quand l'agent n'est pas initialisé.
  3. /ready retourne 200 quand l'agent est opérationnel.
  4. /ready retourne 503 quand l'agent n'est pas prêt.
  5. POST /chat court-circuite le LLM pour les intents statiques (salutations).
  6. POST /chat retourne un ChatResponse JSON valide pour une query de données.
  7. POST /chat retourne 422 pour un body invalide.
  8. POST /chat répond gracieusement quand l'agent n'est pas prêt.
  9. GET /chat/stream retourne du text/event-stream avec les événements SSE attendus.
  10. GET /chat/stream gère une question vide par un événement SSE d'erreur.
  11. GET /chat/stream expose les événements tool_name pour les queries de données.
  12. Chaque réponse porte le header X-Request-ID.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_sse(text: str) -> list[dict]:
    """Extrait les payloads JSON d'un flux SSE (format: data: <json>\\n\\n)."""
    events = []
    for line in text.splitlines():
        if line.startswith('data: '):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def _make_agent() -> MagicMock:
    """
    Construit un AriaAgent mock complet.

    handle_static :
      - Retourne une réponse fixe pour les salutations (bonjour / salut / …).
      - Retourne None pour les queries de données → chemin LLM.
    process / stream_process : retournent des données de test déterministes.
    """
    agent = MagicMock()
    agent.is_ready.return_value    = True
    agent.initialize               = AsyncMock()
    agent.close                    = AsyncMock()
    agent.backend                  = 'mock'
    agent.model_name               = 'mock-model'
    agent.get_history_manager.return_value = MagicMock()

    _GREETINGS = {'bonjour', 'salut', 'hello', 'bonsoir', 'aide'}

    def _handle_static(q, tid, uid, t0):
        if any(g in q.lower() for g in _GREETINGS):
            return "Bonjour ! Je suis ARIA, votre assistant IoT intelligent."
        return None

    agent.handle_static.side_effect = _handle_static

    async def _process(q, tid, uid, modules, lang):
        return {
            'answer'    : '🟢 NORMAL — Température : 22.5 °C | Humidité : 45 % sur capteur THL-01.',
            'backend'   : 'mock',
            'model'     : 'mock-model',
            'duration'  : 0.12,
            'level'     : 'data',
            'message_id': 9001,
        }
    agent.process = _process

    async def _stream(q, tid, uid, modules, lang):
        yield {'type': 'thinking', 'data': 'Analyse en cours…'}
        yield {'type': 'tool',  'tool_name': 'realtime_data', 'label': 'Données temps réel'}
        yield {'type': 'chunk', 'data': '🟢 NORMAL — '}
        yield {'type': 'chunk', 'data': 'Température : 22.5 °C | Humidité : 45 %.'}
        yield {
            'type'         : 'done',
            'level'        : 'data',
            'backend'      : 'mock',
            'thread_id'    : tid,
            'message_id'   : 9002,
            'duration'     : 0.15,
            'quick_replies': None,
        }
    agent.stream_process = _stream

    return agent


def _make_patches(aria_module, mock_ag):
    """Retourne la liste de patches à appliquer pour démarrer l'app sans infrastructure."""
    return [
        patch.object(aria_module, 'AriaAgent',               return_value=mock_ag),
        patch.object(aria_module, 'get_engine',              return_value=None),
        patch.object(aria_module, 'ensure_tables',           return_value=None),
        patch.object(aria_module, 'ensure_analytics_tables', return_value=None),
        patch.object(aria_module, 'set_history_db',          return_value=None),
        patch('api.pipeline.scheduler.start'),
        patch('mcp_server.db.connection.test_connection',    return_value=True),
    ]


# ── Fixture principale ────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def client():
    """
    Client TestClient avec AriaAgent mocké et infrastructure patchée.
    scope='module' : le lifespan ne tourne qu'une fois pour tous les tests du fichier.
    """
    import aria_api as _aria

    mock_ag       = _make_agent()
    _aria._agent  = None   # reset du singleton avant le démarrage

    patches = _make_patches(_aria, mock_ag)
    for p in patches:
        p.start()

    try:
        with TestClient(_aria.app, raise_server_exceptions=False) as tc:
            yield tc, mock_ag
    finally:
        for p in patches:
            p.stop()
        _aria._agent = None


# ── /health & /ready ──────────────────────────────────────────────────────────

class TestHealthEndpoints:
    def test_health_ok(self, client):
        """system_router.GET /health doit retourner status='OK' quand le mock est prêt."""
        tc, _ = client
        r = tc.get('/health')
        assert r.status_code == 200
        body = r.json()
        # system_router retourne 'OK' (majuscules) — pas l'endpoint app-level
        assert body['status'] == 'OK'
        assert body['backend'] == 'mock'

    def test_ready_ok(self, client):
        """GET /ready doit retourner {ready: True} avec code 200."""
        tc, _ = client
        r = tc.get('/ready')
        assert r.status_code == 200
        assert r.json()['ready'] is True

    def test_health_not_ready_when_agent_fails(self):
        """
        Quand initialize() lève une exception, system_router /health doit retourner
        status='NOT_READY' et /ready doit retourner 503.
        """
        import aria_api         as _aria
        import api.routes.system as _sys

        failing_ag = MagicMock()
        failing_ag.initialize = AsyncMock(side_effect=ConnectionRefusedError("MCP unreachable"))
        failing_ag._history   = None

        original_sys_agent = _sys._agent
        _sys._agent        = None   # reset pour que /health reflète l'état réel
        _aria._agent       = None

        patches = _make_patches(_aria, failing_ag)
        for p in patches:
            p.start()

        try:
            with TestClient(_aria.app, raise_server_exceptions=False) as tc:
                r_ready  = tc.get('/ready')
                r_health = tc.get('/health')

            assert r_ready.status_code == 503,          f"Attendu 503, reçu {r_ready.status_code}"
            assert r_health.json()['status'] == 'NOT_READY', (
                f"Attendu NOT_READY, reçu {r_health.json()}"
            )
        finally:
            for p in patches:
                p.stop()
            _sys._agent  = original_sys_agent
            _aria._agent = None

    def test_ready_503_when_agent_fails(self):
        """Variante explicite /ready — doit retourner 503 si l'agent n'est pas initialisé."""
        import aria_api         as _aria
        import api.routes.system as _sys

        failing_ag = MagicMock()
        failing_ag.initialize = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        failing_ag._history   = None

        original_sys_agent = _sys._agent
        _sys._agent        = None
        _aria._agent       = None

        patches = _make_patches(_aria, failing_ag)
        for p in patches:
            p.start()

        try:
            with TestClient(_aria.app, raise_server_exceptions=False) as tc:
                r = tc.get('/ready')
            assert r.status_code == 503
            assert r.json()['ready'] is False
        finally:
            for p in patches:
                p.stop()
            _sys._agent  = original_sys_agent
            _aria._agent = None


# ── POST /chat ────────────────────────────────────────────────────────────────

class TestChatPost:
    def _post(self, tc: TestClient, question: str, **extra) -> object:
        payload = {'question': question, 'allowed_modules': ['équipements/capteurs'], **extra}
        return tc.post('/chat', json=payload)

    def test_static_greeting_no_llm(self, client):
        """
        Une salutation doit retourner via handle_static (backend='static'),
        sans appeler agent.process().
        """
        tc, mock_ag = client
        mock_ag.process = AsyncMock()   # ne doit PAS être appelé

        r = self._post(tc, 'bonjour')
        assert r.status_code == 200
        body = r.json()
        assert body['backend'] == 'static'
        assert 'ARIA' in body['answer']
        mock_ag.process.assert_not_called()

    def test_data_query_returns_llm_response(self, client):
        """Une query données retourne la réponse de agent.process()."""
        tc, mock_ag = client

        async def _proc(*a, **kw):
            return {
                'answer'    : '🟢 NORMAL — Température : 22.5 °C | Humidité : 45 %.',
                'backend'   : 'mock',
                'model'     : 'mock-model',
                'duration'  : 0.12,
                'level'     : 'data',
                'message_id': 9001,
            }
        mock_ag.process = _proc

        r = self._post(tc, 'quelle est la température du capteur THL-01 ?')
        assert r.status_code == 200
        body = r.json()
        assert body['answer']          # réponse non vide
        assert 'backend'  in body
        assert 'duration' in body
        assert 'thread_id' in body

    def test_invalid_body_missing_question_returns_422(self, client):
        """Body sans le champ requis 'question' → 422 Unprocessable Entity."""
        tc, _ = client
        r = tc.post('/chat', json={'userId': 'test'})
        assert r.status_code == 422

    def test_question_too_long_returns_422(self, client):
        """question > 4000 caractères → 422 (max_length Pydantic)."""
        tc, _ = client
        r = self._post(tc, 'a' * 4001)
        assert r.status_code == 422

    def test_invalid_lang_returns_422(self, client):
        """lang hors (fr|en|ar) → 422 (pattern Pydantic)."""
        tc, _ = client
        r = tc.post('/chat', json={'question': 'test', 'lang': 'es'})
        assert r.status_code == 422

    def test_agent_not_ready_returns_degraded_response(self, client):
        """Quand is_ready() retourne False, le chat répond gracieusement (pas d'erreur 5xx)."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = False
        try:
            r = self._post(tc, 'bonjour')
            assert r.status_code == 200
            body = r.json()
            # La réponse doit indiquer l'indisponibilité — pas de 500
            assert body['backend'] in ('none', 'error', 'static', 'mock')
        finally:
            mock_ag.is_ready.return_value = True

    def test_response_shape_complete(self, client):
        """Tous les champs du modèle ChatResponse doivent être présents."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = True

        async def _proc(*a, **kw):
            return {'answer': '🟢 test.', 'backend': 'mock', 'model': '',
                    'duration': 0.1, 'level': 'data', 'message_id': 1}
        mock_ag.process = _proc

        r = self._post(tc, 'état des capteurs ?')
        assert r.status_code == 200
        body = r.json()
        for field in ('answer', 'backend', 'level', 'duration', 'thread_id'):
            assert field in body, f"Champ requis '{field}' absent de la réponse"

    def test_lang_ar_accepted(self, client):
        """lang=ar doit être accepté (regex ^(fr|en|ar)$)."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = True
        r = tc.post('/chat', json={'question': 'bonjour', 'lang': 'ar',
                                   'allowed_modules': []})
        assert r.status_code == 200   # pas de 422


# ── GET /chat/stream ──────────────────────────────────────────────────────────

class TestChatStream:
    # Modules encodés URL — évite l'appel DB get_employee_modules
    BASE_PARAMS = 'allowedModules=%C3%A9quipements%2Fcapteurs'

    def _get_events(self, tc: TestClient, question: str, extra: str = '') -> list[dict]:
        """Envoie une requête SSE, lit tout le flux et retourne la liste d'événements parsés."""
        url = f'/chat/stream?question={question}&{self.BASE_PARAMS}'
        if extra:
            url += f'&{extra}'
        with tc.stream('GET', url) as r:
            raw = r.read()   # lit tout le flux dans le context manager
        return _parse_sse(raw.decode('utf-8'))

    def test_content_type_is_event_stream(self, client):
        tc, _ = client
        with tc.stream('GET', f'/chat/stream?question=bonjour&{self.BASE_PARAMS}') as r:
            ct = r.headers.get('content-type', '')
        assert 'text/event-stream' in ct

    def test_static_greeting_emits_chunk_and_done(self, client):
        """Une salutation (intent statique) doit émettre au moins chunk + done."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = True
        events = self._get_events(tc, 'bonjour')
        types  = [e.get('type') for e in events]
        assert 'chunk' in types, f"Événement 'chunk' attendu — reçu : {types}"
        assert 'done'  in types, f"Événement 'done'  attendu — reçu : {types}"
        done = next(e for e in events if e.get('type') == 'done')
        assert done.get('backend') == 'static'

    def test_data_query_emits_thinking_tool_chunk_done(self, client):
        """Une query de données doit émettre thinking, tool, chunk et done."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = True
        events = self._get_events(tc, 'température+capteurs')
        types  = [e.get('type') for e in events]
        for expected in ('thinking', 'tool', 'chunk', 'done'):
            assert expected in types, f"Événement '{expected}' attendu — reçu : {types}"

    def test_data_query_tool_name_is_realtime_data(self, client):
        """Le premier événement tool doit reporter tool_name='realtime_data'."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = True
        events      = self._get_events(tc, 'température+capteurs')
        tool_events = [e for e in events if e.get('type') == 'tool']
        assert tool_events, "Aucun événement 'tool' dans le flux SSE"
        assert tool_events[0].get('tool_name') == 'realtime_data'

    def test_empty_question_returns_error_event(self, client):
        """Question vide (espace seul) → événement SSE de type 'error'."""
        tc, _ = client
        events = self._get_events(tc, '%20')   # espace URL-encodé → strip → vide
        types  = [e.get('type') for e in events]
        assert 'error' in types, f"Événement 'error' attendu pour question vide — reçu : {types}"

    def test_agent_not_ready_returns_error_event(self, client):
        """Quand is_ready()=False, le flux SSE doit contenir un événement 'error'."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = False
        try:
            events = self._get_events(tc, 'bonjour')
            types  = [e.get('type') for e in events]
            assert 'error' in types, f"Événement 'error' attendu — reçu : {types}"
        finally:
            mock_ag.is_ready.return_value = True

    def test_done_event_contains_required_fields(self, client):
        """L'événement 'done' doit contenir level, backend, thread_id, duration."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = True
        events = self._get_events(tc, 'température+capteurs')
        done_events = [e for e in events if e.get('type') == 'done']
        assert done_events, "Aucun événement 'done' dans le flux SSE"
        done = done_events[0]
        for field in ('level', 'backend', 'thread_id', 'duration'):
            assert field in done, f"Champ '{field}' absent de l'événement 'done' — reçu : {done}"

    def test_stream_ordering_chunk_before_done(self, client):
        """'chunk' doit toujours précéder 'done' dans le flux."""
        tc, mock_ag = client
        mock_ag.is_ready.return_value = True
        events = self._get_events(tc, 'température+capteurs')
        types  = [e.get('type') for e in events]
        if 'chunk' in types and 'done' in types:
            assert types.index('chunk') < types.index('done'), (
                f"'chunk' doit précéder 'done' — ordre reçu : {types}"
            )


# ── Robustesse générale ───────────────────────────────────────────────────────

class TestRobustness:
    def test_x_request_id_header_present(self, client):
        """Chaque réponse doit porter le header X-Request-ID (middleware aria_api.py)."""
        tc, _ = client
        r = tc.get('/health')
        assert 'x-request-id' in r.headers, "Header X-Request-ID absent"

    def test_unknown_route_returns_404(self, client):
        tc, _ = client
        r = tc.get('/aria-does-not-exist')
        assert r.status_code == 404

    def test_chat_missing_required_field_returns_422(self, client):
        """POST /chat sans 'question' → 422, pas 500."""
        tc, _ = client
        r = tc.post('/chat', json={})
        assert r.status_code == 422
