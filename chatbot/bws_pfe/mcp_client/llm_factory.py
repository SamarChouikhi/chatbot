import os
import copy
import json
import shutil
import socket
import logging
import urllib.request
from pathlib import Path
from typing import Any, List, Optional, Tuple

from mcp_client.config import KEY_STATE_FILE

logger = logging.getLogger('aria.llm')


def _ping_host(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _ping_http(url: str, timeout: float = 4.0) -> bool:
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except Exception:
        return False


def _ping_groq()        -> bool: return _ping_host('api.groq.com', 443)
def _ping_gemini()      -> bool: return _ping_host('generativelanguage.googleapis.com', 443)
def _ping_huggingface() -> bool: return _ping_host('router.huggingface.co', 443)
def _ping_openrouter()  -> bool: return _ping_host('openrouter.ai', 443)
def _ping_cerebras()    -> bool: return _ping_host('api.cerebras.ai', 443)
def _ping_ollama()      -> bool:
    return _ping_http(f"{os.getenv('OLLAMA_BASE_URL','http://localhost:11434')}/")


class KeyStateManager:
    """Gère la rotation des clés API et mémorise les clés épuisées sur disque."""

    def __init__(self, key_file: Path):
        self.key_file = key_file
        self._load()

    _DEFAULTS = {
        'groq'       : {'current': 0},
        'gemini'     : {'current': 0, 'exhausted': []},
        'openrouter' : {'current': 0, 'exhausted': []},
        'huggingface': {'current': 0, 'exhausted': []},
        'cerebras'   : {'current': 0, 'exhausted': []},
    }

    def _load(self):
        if self.key_file.exists():
            try:
                self.state = json.loads(self.key_file.read_text())
                # Ajoute les providers manquants si le fichier est d'une version antérieure
                for provider, default in self._DEFAULTS.items():
                    self.state.setdefault(provider, copy.deepcopy(default))
                return
            except Exception as e:
                logger.warning(f'KeyState: fichier corrompu ({e}), sauvegarde créée, état réinitialisé')
                try:
                    shutil.copy(self.key_file, self.key_file.with_suffix('.corrupted.json'))
                except Exception:
                    pass

        self.state = copy.deepcopy(self._DEFAULTS)

    def save(self):
        try:
            self.key_file.write_text(json.dumps(self.state, indent=2))
        except Exception as e:
            logger.error(f'KeyState save error: {e}')

    @staticmethod
    def collect_keys(prefix: str) -> List[str]:
        """Collecte les clés API depuis PREFIX_1…PREFIX_9 et PREFIX (sans doublon)."""
        keys = []
        for i in range(1, 10):
            k = os.getenv(f'{prefix}_{i}', '').strip()
            if k and k not in keys:
                keys.append(k)
        single = os.getenv(prefix, '').strip()
        if single and single not in keys:
            keys.append(single)
        return keys

    def get_groq_key(self, model: str) -> Optional[str]:
        keys      = self.collect_keys('GROQ_API_KEY')
        exhausted = self.state['groq'].get(f'exhausted_{model}', [])
        for i, key in enumerate(keys):
            if key not in exhausted:
                self.state['groq']['current'] = i
                self.save()
                return key
        return None

    def mark_groq_exhausted(self, model: str, key: str):
        k = f'exhausted_{model}'
        self.state['groq'].setdefault(k, [])
        if key not in self.state['groq'][k]:
            self.state['groq'][k].append(key)
            self.save()

    def get_gemini_key(self) -> Optional[str]:
        keys      = self.collect_keys('GEMINI_API_KEY')
        exhausted = self.state['gemini'].get('exhausted', [])
        for i, key in enumerate(keys):
            if key not in exhausted:
                self.state['gemini']['current'] = i
                self.save()
                return key
        return None

    def mark_gemini_exhausted(self, key: str):
        self.state['gemini'].setdefault('exhausted', [])
        if key not in self.state['gemini']['exhausted']:
            self.state['gemini']['exhausted'].append(key)
            self.save()

    def get_openrouter_key(self) -> Optional[str]:
        keys      = self.collect_keys('OPENROUTER_API_KEY')
        exhausted = self.state['openrouter'].get('exhausted', [])
        for i, key in enumerate(keys):
            if key not in exhausted:
                self.state['openrouter']['current'] = i
                self.save()
                return key
        return None

    def mark_openrouter_exhausted(self, key: str):
        self.state['openrouter'].setdefault('exhausted', [])
        if key not in self.state['openrouter']['exhausted']:
            self.state['openrouter']['exhausted'].append(key)
            self.save()

    def get_huggingface_key(self) -> Optional[str]:
        keys      = self.collect_keys('HF_API_KEY')
        exhausted = self.state['huggingface'].get('exhausted', [])
        for i, key in enumerate(keys):
            if key not in exhausted:
                self.state['huggingface']['current'] = i
                self.save()
                return key
        return None

    def mark_huggingface_exhausted(self, key: str):
        self.state['huggingface'].setdefault('exhausted', [])
        if key not in self.state['huggingface']['exhausted']:
            self.state['huggingface']['exhausted'].append(key)
            self.save()

    def get_cerebras_key(self) -> Optional[str]:
        keys      = self.collect_keys('CEREBRAS_API_KEY')
        exhausted = self.state['cerebras'].get('exhausted', [])
        for i, key in enumerate(keys):
            if key not in exhausted:
                self.state['cerebras']['current'] = i
                self.save()
                return key
        return None

    def mark_cerebras_exhausted(self, key: str):
        self.state['cerebras'].setdefault('exhausted', [])
        if key not in self.state['cerebras']['exhausted']:
            self.state['cerebras']['exhausted'].append(key)
            self.save()

    def reset(self):
        self.state = copy.deepcopy(self._DEFAULTS)
        self.save()
        logger.info('Key state réinitialisé')


# Ordre de priorité par défaut, configurable via LLM_ORDER dans le .env
DEFAULT_LLM_ORDER = ['openrouter', 'groq', 'cerebras', 'ollama', 'gemini', 'huggingface']


class LLMFactory:

    def __init__(self):
        self.key_manager = KeyStateManager(KEY_STATE_FILE)

    def _get_order(self) -> List[str]:
        env_order = os.getenv('LLM_ORDER', '')
        if env_order:
            order = [b.strip().lower() for b in env_order.split(',') if b.strip()]
            if order:
                return order
        return DEFAULT_LLM_ORDER

    def create(self) -> Tuple[Any, str, str]:
        backend = os.getenv('LLM_BACKEND', 'auto').lower()

        dispatch = {
            'ollama'     : self._try_ollama_all,
            'groq'       : self._try_groq_all,
            
            'gemini'     : self._try_gemini,
            'openrouter' : self._try_openrouter,
            'huggingface': self._try_huggingface,
            'cerebras'   : self._try_cerebras,
        }

        if backend in dispatch:
            result = dispatch[backend]()
            if result:
                return result
            raise RuntimeError(f'{backend} indisponible (LLM_BACKEND={backend})')

        for backend_name in self._get_order():
            fn = dispatch.get(backend_name)
            if fn:
                result = fn()
                if result:
                    return result

        raise RuntimeError('Tous les backends LLM ont échoué')

    @staticmethod
    def _collect_groq_models() -> List[str]:
        models = [os.getenv(f'GROQ_MODEL_{i}', '').strip() for i in range(1, 10)]
        models = [m for m in models if m]
        return models or ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant']

    def _try_groq_all(self) -> Optional[Tuple]:
        if not _ping_groq():
            logger.warning('[PING] api.groq.com injoignable')
            return None
        for model in self._collect_groq_models():
            result = self._try_groq(model)
            if result:
                return result
        return None

    def _try_groq(self, model: str) -> Optional[Tuple]:
        key = self.key_manager.get_groq_key(model)
        if not key:
            return None
        try:
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                model=model, api_key=key,
                temperature=float(os.getenv('GROQ_TEMPERATURE', '0')),
                max_tokens=4096, timeout=30,
            )
            logger.info(f'LLM: Groq / {model}')
            return (llm, model, 'groq')
        except Exception as e:
            if any(k in str(e).lower() for k in ['quota', 'rate', '429', 'limit']):
                self.key_manager.mark_groq_exhausted(model, key)
            logger.warning(f'Groq/{model} échec: {str(e)[:80]}')
            return None

    @staticmethod
    def _collect_ollama_models() -> List[str]:
        models = [os.getenv(f'OLLAMA_MODEL_{i}', '').strip() for i in range(1, 10)]
        models = [m for m in models if m]
        single = os.getenv('OLLAMA_MODEL', 'qwen2.5:7b').strip()
        if single and single not in models:
            models.append(single)
        return models

    def _try_ollama_all(self) -> Optional[Tuple]:
        if not _ping_ollama():
            logger.warning('[PING] Ollama injoignable')
            return None
        for model in self._collect_ollama_models():
            result = self._try_ollama(model)
            if result:
                return result
        return None

    def _try_ollama(self, model: str) -> Optional[Tuple]:
        try:
            from langchain_openai import ChatOpenAI
            base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

            is_cloud = 'cloud' in model.lower()

            # Les modèles cloud ne figurent pas dans /api/tags — on skippe le check
            if not is_cloud:
                try:
                    with urllib.request.urlopen(f'{base_url}/api/tags', timeout=4) as r:
                        tags  = json.loads(r.read())
                        names = [m.get('name', '') for m in tags.get('models', [])]
                        if model not in names:
                            logger.warning(f'Ollama: modèle "{model}" non trouvé (dispo: {names})')
                            return None
                except Exception as tag_err:
                    logger.debug(f'Ollama /api/tags inaccessible: {tag_err}')

            api_key = os.getenv('OLLAMA_API_KEY', 'ollama')
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model,
                base_url=f'{base_url}/v1',
                api_key=api_key,
                temperature=0,
                max_tokens=4096,
                timeout=int(os.getenv('OLLAMA_TIMEOUT', '300')),
                max_retries=0,
            )
            logger.info(f'LLM: Ollama / {model}')
            return (llm, model, 'ollama')
        except Exception as e:
            logger.warning(f'Ollama/{model} échec: {str(e)[:80]}')
            return None

    def _try_gemini(self) -> Optional[Tuple]:
        if not _ping_gemini():
            logger.warning('[PING] Gemini injoignable')
            return None
        key   = self.key_manager.get_gemini_key()
        model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')
        if not key:
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=model, google_api_key=key, temperature=0, timeout=50, max_retries=0,
            )
            logger.info(f'LLM: Gemini / {model}')
            return (llm, model, 'gemini')
        except Exception as e:
            if any(k in str(e).lower() for k in ['quota', 'rate', '429', 'limit', 'exhausted', 'expired', 'invalid']):
                self.key_manager.mark_gemini_exhausted(key)
            logger.warning(f'Gemini échec: {str(e)[:80]}')
            return None

    def _try_openrouter(self) -> Optional[Tuple]:
        if not _ping_openrouter():
            logger.warning('[PING] OpenRouter injoignable')
            return None
        key   = self.key_manager.get_openrouter_key()
        model = os.getenv('OPENROUTER_MODEL', 'nvidia/nemotron-3-super-120b-a12b:free')
        if not key:
            return None
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model, api_key=key,
                base_url='https://openrouter.ai/api/v1',
                temperature=0, max_tokens=4096, timeout=60, max_retries=0,
                default_headers={'HTTP-Referer': 'https://localhost', 'X-Title': 'aria-app'},
            )
            logger.info(f'LLM: OpenRouter / {model}')
            return (llm, model, 'openrouter')
        except Exception as e:
            if any(k in str(e).lower() for k in ['quota', 'credits', 'invalid', 'unauthorized', '401']):
                self.key_manager.mark_openrouter_exhausted(key)
            logger.warning(f'OpenRouter échec: {str(e)[:80]}')
            return None

    def _try_cerebras(self) -> Optional[Tuple]:
        if not _ping_cerebras():
            logger.warning('[PING] api.cerebras.ai injoignable')
            return None
        key   = self.key_manager.get_cerebras_key()
        model = os.getenv('CEREBRAS_MODEL', 'llama3.1-70b')
        if not key:
            return None
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model,
                api_key=key,
                base_url='https://api.cerebras.ai/v1',
                temperature=0,
                max_tokens=4096,
                timeout=45,
                max_retries=0,
            )
            logger.info(f'LLM: Cerebras / {model}')
            return (llm, model, 'cerebras')
        except Exception as e:
            if any(k in str(e).lower() for k in [
                'quota', 'rate', '429', 'limit', 'unauthorized', '401',
                'queue_exceeded', 'too_many_requests', 'high traffic',
            ]):
                self.key_manager.mark_cerebras_exhausted(key)
            logger.warning(f'Cerebras échec: {str(e)[:80]}')
            return None

    def _try_huggingface(self) -> Optional[Tuple]:
        if not _ping_huggingface():
            logger.warning('[PING] HuggingFace injoignable')
            return None
        hf_key   = self.key_manager.get_huggingface_key()
        hf_model = os.getenv('HF_MODEL', 'Qwen/Qwen3-8B')
        if not hf_key:
            return None
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=hf_model,
                api_key=hf_key,
                base_url='https://api-inference.huggingface.co/v1',
                temperature=0,
                max_tokens=4096,
                timeout=60,
                max_retries=0,
                # Désactive le mode "thinking" de Qwen3 (évite les blocs <think>…</think>)
                model_kwargs={'chat_template_kwargs': {'enable_thinking': False}},
            )
            logger.info(f'LLM: HuggingFace / {hf_model}')
            return (llm, hf_model, 'huggingface')
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ['quota', 'rate', '429', 'limit', 'unauthorized', '401']):
                self.key_manager.mark_huggingface_exhausted(hf_key)
            logger.warning(f'HuggingFace échec: {str(e)[:80]}')
            return None
