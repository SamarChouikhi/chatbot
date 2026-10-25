"""
Tests de la classification d'erreur LLM dans stream_process (mcp_client/agent.py).

Couvre le bug corrigé le 2026-09-09 : une erreur de surcharge amont
('Upstream error from Nvidia: Service temporarily overloaded', via OpenRouter)
n'était reconnue par aucun mot-clé de is_quota, donc aucun fallback vers un
autre backend n'était tenté et le chat renvoyait 'Erreur système. Réessayez.'
directement à l'utilisateur au lieu de basculer de backend.
"""
from mcp_client.agent import _classify_stream_error


def test_nvidia_overload_triggers_fallback():
    """Message réel observé en prod (OpenRouter / nvidia nemotron free tier)."""
    err = 'openai.APIError: Upstream error from Nvidia: Service temporarily overloaded'
    result = _classify_stream_error(err)

    assert result.is_quota is True, (
        'Une erreur de surcharge amont doit déclencher le fallback multi-backend, '
        'pas un system_error direct.'
    )
    assert result.is_model_overloaded is True
    assert result.is_timeout is False
    assert result.is_func_fail is False
    assert result.is_connection_error is False


def test_generic_503_and_502_are_treated_as_overload():
    for msg in [
        'HTTP 503 Service Unavailable',
        'Bad Gateway (502)',
        'The model is temporarily unavailable, please retry',
    ]:
        result = _classify_stream_error(msg)
        assert result.is_model_overloaded is True, msg
        assert result.is_quota is True, msg


def test_timeout_still_classified_as_timeout():
    result = _classify_stream_error('Request timed out after 120s')
    assert result.is_timeout is True
    assert result.is_quota is True
    assert result.is_model_overloaded is False


def test_asyncio_timeout_exception_flag_is_honored_even_without_keyword():
    # Certains asyncio.TimeoutError ont un message vide — on doit se fier au flag,
    # pas uniquement au texte.
    result = _classify_stream_error('', is_timeout_exc=True)
    assert result.is_timeout is True
    assert result.is_quota is True


def test_rate_limit_429_triggers_fallback():
    result = _classify_stream_error('429 Too Many Requests: rate_limit exceeded')
    assert result.is_quota is True
    assert result.is_model_overloaded is False  # vraie clé épuisée, pas une surcharge modèle


def test_connection_error_does_not_mark_key_exhausted_path():
    result = _classify_stream_error('APIConnectionError: connection refused')
    assert result.is_connection_error is True
    assert result.is_quota is True


def test_func_call_failure_triggers_fallback():
    result = _classify_stream_error('Failed to call a function. Please adjust your prompt.')
    assert result.is_func_fail is True
    assert result.is_quota is True


def test_cerebras_402_payment_required_triggers_fallback():
    """Bug observé le 2026-09-09 : 402 Payment Required (crédit Cerebras épuisé) ne
    matchait aucun mot-clé -> pas de fallback, system_error direct à l'utilisateur."""
    err = ("Error code: 402 - {'message': 'Payment required to access this resource. "
           "Visit your billing tab.', 'type': 'payment_required_error', "
           "'param': 'quota', 'code': 'payment_required'}")
    result = _classify_stream_error(err)

    assert result.is_quota is True, (
        'Un 402 payment_required doit déclencher le fallback vers le backend suivant.'
    )
    # Vraie exhaustion de crédit, pas une surcharge transitoire : la clé doit pouvoir
    # être marquée exhausted (donc ne pas être classée is_model_overloaded).
    assert result.is_model_overloaded is False


def test_truly_unknown_error_does_not_trigger_fallback():
    """Garde-fou : une erreur non reconnue doit toujours produire system_error direct
    (comportement d'avant le fix, préservé pour les cas non transitoires)."""
    result = _classify_stream_error('KeyError: unexpected field "foo" in response')
    assert result.is_quota is False
    assert result.is_model_overloaded is False
