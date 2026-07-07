"""
Configuration pytest pour bws_pfe.
On injecte un faux .env avant tout import pour éviter que les modules
qui lisent os.getenv au niveau module ne lèvent d'erreur.
"""
import os
import sys
from pathlib import Path

# Racine du projet dans le sys.path pour que les imports fonctionnent
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Variables d'environnement minimales — évite les erreurs d'import des modules DB/LLM
os.environ.setdefault("DB_HOST",     "localhost")
os.environ.setdefault("DB_PORT",     "3306")
os.environ.setdefault("DB_NAME",     "test_db")
os.environ.setdefault("DB_USER",     "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("ENV",         "test")
