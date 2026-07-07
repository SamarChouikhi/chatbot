import re
import uuid
import tempfile
from datetime import datetime
from pathlib import Path

CSV_TMP_DIR = Path(tempfile.gettempdir()) / 'aria_csv'
CSV_TMP_DIR.mkdir(exist_ok=True)

# Durée de vie max d'un fichier CSV temp (en secondes) — nettoyé à chaque génération
_MAX_AGE_SEC = 3600


def _cleanup_old_files():
    now = datetime.now().timestamp()
    for f in CSV_TMP_DIR.glob('*.csv'):
        try:
            if now - f.stat().st_mtime > _MAX_AGE_SEC:
                f.unlink(missing_ok=True)
        except Exception:
            pass


def _extract_csv_text(text: str) -> str | None:
    # Uniquement les blocs ```csv explicites — jamais de détection heuristique.
    # Le LLM ne doit émettre ce bloc que si l'utilisateur demande explicitement un export.
    m = re.search(r'```csv\s*\n(.*?)\n```', text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def save_csv(answer: str, label: str = 'rapport') -> tuple[str, str] | None:
    """Extrait le CSV de la réponse, sauvegarde en fichier temp.
    Retourne (file_id, filename) ou None si pas de CSV détecté."""
    _cleanup_old_files()
    csv_text = _extract_csv_text(answer)
    if not csv_text:
        return None

    file_id = str(uuid.uuid4())
    date_str = datetime.now().strftime('%Y%m%d_%H%M')
    filename = f'{label}_{date_str}.csv'

    path = CSV_TMP_DIR / f'{file_id}.csv'
    # utf-8-sig : BOM pour que Excel ouvre correctement les accents
    path.write_text(csv_text, encoding='utf-8-sig')

    return file_id, filename
