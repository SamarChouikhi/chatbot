import os
import logging
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / '.env')

MCP_SERVER_URL = os.getenv('MCP_SERVER_URL', 'http://localhost:8000/sse')
DB_NAME        = os.getenv('DB_NAME', 'bw_samar')

KEY_STATE_FILE = BASE_DIR.parent / '.key_state.json'
LOG_FILE       = BASE_DIR / 'aria.log'
LOG_LEVEL      = os.getenv('LOG_LEVEL', 'INFO')

# Configure le logging uniquement si aucun handler n'a déjà été enregistré,
# pour ne pas écraser la configuration de aria_api.py si elle est chargée en premier.
if not logging.root.handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format='%(asctime)s [%(name)s] %(levelname)s : %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(),
        ]
    )
