# ══════════════════════════════════════════════════════════════════════════
# PARTIE STT (Speech-To-Text) — transcription audio via AssemblyAI
# ══════════════════════════════════════════════════════════════════════════
import os
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import httpx

logger = logging.getLogger('aria.transcribe')
transcribe_router = APIRouter()

MAX_FILE_SIZE       = 25 * 1024 * 1024  # 25 Mo
SUPPORTED_LANGUAGES = {'fr', 'ar', 'en', 'auto'}

ALLOWED_MIME_TYPES = {
    'audio/webm', 'audio/webm;codecs=opus',
    'audio/wav',  'audio/x-wav',
    'audio/mpeg', 'audio/mp3',
    'audio/ogg',  'audio/mp4',
    'audio/flac', 'audio/x-m4a',
    'application/octet-stream',
}

_EXT_MAP = {
    'audio/wav' : '.wav', 'audio/x-wav': '.wav',
    'audio/mpeg': '.mp3', 'audio/mp3'  : '.mp3',
    'audio/ogg' : '.ogg', 'audio/mp4'  : '.mp4',
    'audio/flac': '.flac', 'audio/x-m4a': '.m4a',
}

# None = détection automatique par AssemblyAI
_LANG_MAP = {'fr': 'fr', 'en': 'en_us', 'ar': 'ar', 'auto': None}

ASSEMBLYAI_BASE = 'https://api.assemblyai.com/v2'


# ── Appels AssemblyAI (upload → création job → polling) ─────────────────────

def _headers() -> dict:
    key = os.getenv('ASSEMBLYAI_API_KEY')
    if not key:
        raise RuntimeError('ASSEMBLYAI_API_KEY absent du .env')
    return {'authorization': key, 'content-type': 'application/json'}


async def _upload_audio(audio_bytes: bytes) -> str:
    """Upload le fichier audio et retourne l'URL temporaire AssemblyAI."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f'{ASSEMBLYAI_BASE}/upload',
            headers={'authorization': os.getenv('ASSEMBLYAI_API_KEY', '')},
            content=audio_bytes,
        )
    if resp.status_code != 200:
        raise RuntimeError(f'Upload échoué ({resp.status_code}): {resp.text[:200]}')
    return resp.json()['upload_url']


async def _create_transcript(upload_url: str, language: str) -> str:
    """Soumet la transcription et retourne l'ID du job AssemblyAI."""
    lang_code       = _LANG_MAP.get(language)
    payload: dict   = {'audio_url': upload_url, 'speech_models': ['universal-2']}
    if lang_code:
        payload['language_code'] = lang_code
    else:
        payload['language_detection'] = True  # auto-détection si langue non spécifiée

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f'{ASSEMBLYAI_BASE}/transcript',
            headers=_headers(),
            json=payload,
        )
    if resp.status_code != 200:
        raise RuntimeError(f'Création transcript échouée ({resp.status_code}): {resp.text[:200]}')
    return resp.json()['id']


async def _poll_transcript(transcript_id: str) -> str:
    """Interroge AssemblyAI jusqu'à completion (max 2 minutes, toutes les 2 secondes)."""
    url = f'{ASSEMBLYAI_BASE}/transcript/{transcript_id}'
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(60):
            resp   = await client.get(url, headers=_headers())
            data   = resp.json()
            status = data.get('status')

            if status == 'completed':
                return (data.get('text') or '').strip()
            if status == 'error':
                raise RuntimeError(f'Transcription échouée : {data.get("error", "?")}')

            await asyncio.sleep(2)

    raise RuntimeError('Timeout : transcription trop longue (> 2 min)')


# ── Route /transcribe ────────────────────────────────────────────────────────

@transcribe_router.post('/transcribe', tags=['stt'])
async def transcribe_audio(
    file    : UploadFile = File(...),
    language: str        = Form('fr'),
):
    """Transcrit un fichier audio via AssemblyAI (gratuit 5h/mois, FR/EN/AR)."""

    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Langue non supportée : '{language}'. Valeurs : {', '.join(sorted(SUPPORTED_LANGUAGES))}"
        )

    content_type = (file.content_type or '').lower()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        logger.warning(f'[STT] MIME inhabituel : {content_type}')

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail='Fichier audio vide.')
    if len(audio_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f'Fichier trop grand : {len(audio_bytes) // (1024*1024)} Mo (max 25 Mo).'
        )

    ext      = _EXT_MAP.get(content_type, '.webm')
    filename = file.filename or f'recording{ext}'
    logger.info(f'[STT] fichier={filename}  taille={len(audio_bytes)//1024}Ko  langue={language}')

    try:
        upload_url    = await _upload_audio(audio_bytes)
        transcript_id = await _create_transcript(upload_url, language)
        text          = await _poll_transcript(transcript_id)
        logger.info(f'[STT] OK — {len(text)} caractères')
        return {'text': text, 'language': language}

    except HTTPException:
        raise
    except Exception as e:
        err = str(e)
        logger.error(f'[STT] Erreur AssemblyAI : {err[:300]}')
        if '401' in err or 'unauthorized' in err.lower():
            raise HTTPException(status_code=401, detail='Clé AssemblyAI invalide.')
        if '429' in err or 'rate' in err.lower():
            raise HTTPException(status_code=429, detail='Quota AssemblyAI dépassé.')
        raise HTTPException(status_code=500, detail=f'Erreur transcription : {err[:150]}')
