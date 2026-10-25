"""
Tests de AriaAgent._switch_backend (mcp_client/agent.py).

Couvre le bug corrigé le 2026-09-09 : une erreur transitoire (surcharge modèle,
timeout, connexion) ne marque volontairement PAS la clé du backend en échec comme
épuisée — mais sans mémoire des backends déjà tentés dans la requête en cours,
LLMFactory.create() re-sélectionnait le MÊME backend qui venait d'échouer, en boucle
(observé en prod : OpenRouter surchargé → "bascule" → OpenRouter à nouveau → abandon,
sans jamais toucher HuggingFace/Groq alors qu'ils étaient disponibles).

On ne touche à aucun fichier réel (.key_state.json) ni réseau : LLMFactory est
remplacée par un faux minimal qui simule create() en piochant dans LLM_ORDER effectif.
"""
import asyncio
import os

import pytest

from mcp_client.agent import AriaAgent


class _FakeKeyManager:
    """Avale silencieusement tout appel get_*_key()/mark_*_exhausted() — on ne teste
    pas ici la logique d'exhaustion des clés (déjà couverte ailleurs), seulement
    l'exclusion des backends déjà tentés."""
    def __getattr__(self, name):
        def _stub(*args, **kwargs):
            if name.startswith('get_'):
                return 'fake-key'
            return None
        return _stub


class _FakeFactory:
    """Simule LLMFactory.create() : choisit le 1er backend de LLM_ORDER effectif
    (celui que _switch_backend a temporairement filtré) — comme le fait la vraie
    factory une fois les clés déjà-épuisées écartées."""
    def __init__(self):
        self.key_manager = _FakeKeyManager()

    def _get_order(self):
        env = os.getenv('LLM_ORDER', '')
        return [b.strip() for b in env.split(',') if b.strip()]

    def create(self):
        order = self._get_order()
        if not order:
            raise RuntimeError('Tous les backends LLM ont échoué')
        chosen = order[0]
        return (f'llm-object-{chosen}', 'model-x', chosen)

    def _collect_groq_models(self):
        return ['model-x', 'model-y']

    def _try_groq(self, model):
        return None  # force le chemin factory.create() générique dans les tests


class _FakeAgent:
    """Stub exposant uniquement les attributs que _switch_backend touche."""
    def __init__(self, backend):
        self.backend         = backend
        self.model_name      = 'model-x'
        self.llm             = None
        self.executor        = None
        self.tools           = []
        self._cached_prompt  = None
        self._checkpointer   = None
        self._lock           = asyncio.Lock()

    def _cra(self, model, tools, prompt, checkpointer):
        return f'executor-for-{self.backend}'

    def _invalidate_executor_cache(self):
        pass


@pytest.fixture(autouse=True)
def _fake_factory(monkeypatch):
    monkeypatch.setattr('mcp_client.agent.LLMFactory', _FakeFactory)


def test_switch_backend_never_repicks_a_backend_already_tried(monkeypatch):
    """Reproduit exactement le bug de prod : OpenRouter surchargé (transitoire, clé
    intacte) doit basculer vers un backend DIFFÉRENT, pas se re-choisir lui-même."""
    monkeypatch.setenv('LLM_ORDER', 'openrouter,huggingface,groq')

    agent = _FakeAgent('openrouter')
    tried: set[str] = set()

    ok1 = asyncio.run(AriaAgent._switch_backend(
        agent, is_timeout=False, is_func_fail=False,
        is_connection_error=False, is_model_overloaded=True, tried=tried,
    ))
    assert ok1 is True
    assert agent.backend == 'huggingface', 'ne doit pas re-choisir openrouter'
    # tried s'enrichit à l'entrée de CHAQUE appel avec le backend qui vient d'échouer —
    # huggingface n'y entrera qu'au prochain appel, s'il échoue à son tour.
    assert tried == {'openrouter'}

    # 2e échec transitoire consécutif (sur le nouveau backend) — doit avancer vers groq,
    # pas repartir sur openrouter ni re-choisir huggingface.
    ok2 = asyncio.run(AriaAgent._switch_backend(
        agent, is_timeout=False, is_func_fail=False,
        is_connection_error=False, is_model_overloaded=True, tried=tried,
    ))
    assert ok2 is True
    assert agent.backend == 'groq'
    assert tried == {'openrouter', 'huggingface'}


def test_switch_backend_restores_llm_order_env_after_call(monkeypatch):
    """LLM_ORDER est filtré temporairement pendant l'appel mais doit revenir intact
    ensuite — sinon toute requête suivante hériterait d'un ordre tronqué."""
    monkeypatch.setenv('LLM_ORDER', 'openrouter,huggingface,groq')
    agent = _FakeAgent('openrouter')

    asyncio.run(AriaAgent._switch_backend(
        agent, is_timeout=False, is_func_fail=False,
        is_connection_error=False, is_model_overloaded=True, tried=set(),
    ))

    assert os.environ['LLM_ORDER'] == 'openrouter,huggingface,groq'


def test_switch_backend_gives_up_once_every_backend_was_tried(monkeypatch):
    """Si les 3 backends de LLM_ORDER ont déjà tous échoué dans cette requête, on ne
    boucle pas indéfiniment — on rend la main proprement (False)."""
    monkeypatch.setenv('LLM_ORDER', 'openrouter,huggingface,groq')
    agent = _FakeAgent('groq')
    tried = {'openrouter', 'huggingface', 'groq'}

    ok = asyncio.run(AriaAgent._switch_backend(
        agent, is_timeout=False, is_func_fail=False,
        is_connection_error=False, is_model_overloaded=True, tried=tried,
    ))
    assert ok is False


def test_switch_backend_defaults_tried_to_current_backend_when_none_passed():
    """Appel sans `tried` explicite (compat) : ne doit toujours pas se re-choisir lui-même."""
    import os as _os
    _os.environ['LLM_ORDER'] = 'openrouter,huggingface,groq'
    agent = _FakeAgent('openrouter')

    ok = asyncio.run(AriaAgent._switch_backend(
        agent, is_timeout=True, is_func_fail=False,
        is_connection_error=False, is_model_overloaded=False,
    ))
    assert ok is True
    assert agent.backend != 'openrouter'
