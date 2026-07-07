import re
import time
from collections import defaultdict

_rate_counts: dict = defaultdict(list)
_rate_last_cleanup = 0.0
_RATE_MAX_IPS      = 10_000   # au-delà, nettoyage forcé
_RATE_CLEANUP_IVTL = 120.0    # nettoyage global toutes les 2 min max


def rate_ok(ip: str, limit: int = 30) -> bool:
    global _rate_last_cleanup
    now = time.time()
    _rate_counts[ip] = [t for t in _rate_counts[ip] if now - t < 60]
    if len(_rate_counts[ip]) >= limit:
        return False
    _rate_counts[ip].append(now)
    # Nettoyage global throttlé — évite O(N) à chaque appel
    if len(_rate_counts) > _RATE_MAX_IPS or now - _rate_last_cleanup > _RATE_CLEANUP_IVTL:
        dead = [k for k, v in _rate_counts.items() if not v]
        for k in dead:
            del _rate_counts[k]
        _rate_last_cleanup = now
    return True


def clean(txt: str) -> str:
    """Supprime les artefacts internes (tool_calls, placeholders) de la réponse LLM."""
    txt = re.sub(r'\{[^{}]*"(role|content|tool_call)"[^{}]*\}', '', txt)
    txt = re.sub(r'<tool_call>.*?</tool_call>', '', txt, flags=re.DOTALL)
    txt = re.sub(r'\[ID\d*\]|\[valeur\d*\]', '', txt)
    return re.sub(r'\n{3,}', '\n\n', txt).strip()


def confidence(answer: str, level: str) -> str:
    """Estime la fiabilité de la réponse selon son contenu et son niveau."""
    low_signals = ['je ne sais pas', "i don't know", 'erreur', 'error',
                   'لا أعرف', 'indisponible', 'unavailable', 'reessayez']
    if any(m in answer.lower() for m in low_signals):
        return 'faible'
    if level == 'static':
        return 'haute'
    if level == 'data' or any(m in answer.lower() for m in ['°c', '%hr', 'lux', 'dbm']):
        return 'haute'
    return 'moyenne'


def map_level(level: str) -> str:
    """Convertit le niveau interne ('static', 'data'…) en code numérique pour le client."""
    return {'static': '1', 'knowledge': '1', 'data': '2', 'error': '0'}.get(level, '2')
