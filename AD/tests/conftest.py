"""Configuration pytest pour le module AD."""
import sys
from pathlib import Path

# HotStart et ColdStart dans le path pour les imports
_AD_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_AD_DIR / "HotStart"))
sys.path.insert(0, str(_AD_DIR / "ColdStart"))
sys.path.insert(0, str(_AD_DIR))
