import os
from pathlib import Path
from dotenv import load_dotenv


def _find_env() -> Path:
    candidates = [
        Path(__file__).parent / '.env',
        Path(__file__).parent.parent / '.env',
        Path.cwd() / '.env',
        Path.cwd().parent / '.env',
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        'Fichier .env introuvable. Un .env doit exister à la racine du projet.'
    )


load_dotenv(dotenv_path=_find_env())


def _get(key: str, default=None, required=False, cast=str):
    value = os.getenv(key)
    if not value:
        if required:
            raise ValueError(f'Variable requise manquante : {key}')
        return default
    try:
        if cast == bool:
            return value.lower() in ['true', '1', 'yes', 'on']
        return cast(value)
    except Exception:
        raise ValueError(f'Variable {key} invalide : {value}')


def _collect_keys(prefix: str) -> list:
    keys   = [os.getenv(f'{prefix}_{i}') for i in range(1, 10)]
    keys   = [k for k in keys if k]
    single = os.getenv(prefix)
    if single and single not in keys:
        keys.append(single)
    return keys


DB = {
    'host'    : _get('DB_HOST',     'localhost'),
    'port'    : _get('DB_PORT',     3306, cast=int),
    'database': _get('DB_NAME',     'bw_samar'),
    'user'    : _get('DB_USER',     'root'),
    'password': _get('DB_PASSWORD', required=True),
}

DB_URL = (
    f"mysql+pymysql://{DB['user']}:{DB['password']}"
    f"@{DB['host']}:{DB['port']}/{DB['database']}"
)

LLM_BACKEND = _get('LLM_BACKEND', 'auto').lower()

GROQ = {
    'keys'       : _collect_keys('GROQ_API_KEY'),
    'model_1'    : _get('GROQ_MODEL_1',     'llama-3.1-8b-instant'),
    'model_2'    : _get('GROQ_MODEL_2',     'llama-3.3-70b-versatile'),
    'temperature': _get('GROQ_TEMPERATURE', 0.0, cast=float),
}

GEMINI = {
    'keys' : _collect_keys('GEMINI_API_KEY'),
    'model': _get('GEMINI_MODEL', 'gemini-2.0-flash'),
}

OLLAMA = {
    'model'   : _get('OLLAMA_MODEL',    'mistral'),
    'base_url': _get('OLLAMA_BASE_URL', 'http://localhost:11434'),
}

MCP_SERVER = {
    'host'   : _get('MCP_HOST', '0.0.0.0'),
    'port'   : _get('MCP_PORT', 8000, cast=int),
    'name'   : 'ARIA MCP Server',
    'version': '1.0.0',
}

API = {
    'port'     : _get('API_PORT',  8001, cast=int),
    'log_level': _get('LOG_LEVEL', 'INFO'),
}

KEY_STATE_FILE = Path(__file__).parent.parent / '.key_state.json'


def validate() -> list:
    errors = []
    if not DB['password']:
        errors.append('DB_PASSWORD manquant')
    if LLM_BACKEND == 'groq' and not GROQ['keys']:
        errors.append('Aucune GROQ_API_KEY pour backend groq')
    if LLM_BACKEND == 'gemini' and not GEMINI['keys']:
        errors.append('Aucune GEMINI_API_KEY pour backend gemini')
    if LLM_BACKEND not in ['auto', 'groq', 'gemini', 'ollama', 'openrouter', 'huggingface']:
        errors.append(f'LLM_BACKEND inconnu : {LLM_BACKEND}')
    return errors


def print_config():
    print('=' * 60)
    print('  ARIA — CONFIGURATION')
    print('=' * 60)
    print(f'  Database  : {DB["database"]} @ {DB["host"]}:{DB["port"]}')
    print(f'  Backend   : {LLM_BACKEND.upper()}')
    if LLM_BACKEND == 'auto':
        print(f'  Ollama    : {OLLAMA["model"]} ({OLLAMA["base_url"]})')
        print(f'  Groq      : {len(GROQ["keys"])} clé(s) — {GROQ["model_1"]} / {GROQ["model_2"]}')
        print(f'  Gemini    : {len(GEMINI["keys"])} clé(s) — {GEMINI["model"]}')
    elif LLM_BACKEND == 'groq':
        print(f'  Groq      : {len(GROQ["keys"])} clé(s) — {GROQ["model_1"]}')
    elif LLM_BACKEND == 'gemini':
        print(f'  Gemini    : {len(GEMINI["keys"])} clé(s) — {GEMINI["model"]}')
    elif LLM_BACKEND == 'ollama':
        print(f'  Ollama    : {OLLAMA["model"]} ({OLLAMA["base_url"]})')
    print(f'  MCP Server: {MCP_SERVER["host"]}:{MCP_SERVER["port"]}')
    print(f'  API       : port {API["port"]}')
    print(f'  Log level : {API["log_level"]}')
    errors = validate()
    if errors:
        print('\nERREURS CONFIG :')
        for e in errors:
            print(f'  x {e}')
        raise ValueError('Configuration invalide — corrige le .env')
    print('  OK Configuration valide')
    print('=' * 60)


if __name__ == '__main__':
    print_config()
