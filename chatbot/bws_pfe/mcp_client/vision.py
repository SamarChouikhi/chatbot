import os
import base64
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from groq import Groq

logger = logging.getLogger('aria.vision')
vision_router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 Mo

ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png',
    'image/gif',  'image/webp',
}

_DEFAULT_QUESTION = "Analyse cette image en détail et décris ce que tu vois."


def _get_keys() -> list[str]:
    """Collecte toutes les clés VISION_API_KEY_N disponibles."""
    keys   = [os.getenv(f'VISION_API_KEY_{i}') for i in range(1, 10)]
    keys   = [k for k in keys if k]
    single = os.getenv('VISION_API_KEY')
    if single and single not in keys:
        keys.append(single)
    return keys


def _get_model() -> str:
    return os.getenv('VISION_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')


def _analyze_sync(image_bytes: bytes, mime: str, question: str) -> tuple[str, str]:
    """Essaie chaque clé en rotation jusqu'à succès (gestion 429)."""
    keys = _get_keys()
    if not keys:
        raise RuntimeError('Aucune clé VISION_API_KEY_N trouvée dans le .env')

    model    = _get_model()
    b64      = base64.b64encode(image_bytes).decode('utf-8')
    data_url = f'data:{mime};base64,{b64}'
    last_err = ''

    for idx, key in enumerate(keys, 1):
        try:
            client = Groq(api_key=key)
            resp   = client.chat.completions.create(
                model=model,
                messages=[{
                    'role'   : 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {'url': data_url}},
                        {'type': 'text',      'text': question},
                    ],
                }],
                max_tokens=1024,
                temperature=0,
            )
            text = (resp.choices[0].message.content or '').strip()
            logger.info(f'[VISION] clé #{idx} OK  modèle={model}')
            return text, model

        except Exception as e:
            last_err = str(e)
            if '429' in last_err or 'rate' in last_err.lower():
                logger.warning(f'[VISION] clé #{idx} quota dépassé, rotation...')
                continue
            raise RuntimeError(last_err)

    raise RuntimeError(f'Toutes les clés VISION sont en quota. Dernière erreur : {last_err}')


@vision_router.post('/analyze-image', tags=['vision'])
async def analyze_image(
    file    : UploadFile = File(...),
    question: str        = Form(_DEFAULT_QUESTION),
):
    """Analyse une image via Groq Llama-4-Scout (vision multimodale, gratuit)."""

    content_type = (file.content_type or '').lower().split(';')[0].strip()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Format non supporté : '{content_type}'. Acceptés : jpeg, png, gif, webp."
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail='Fichier image vide.')
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f'Image trop grande : {len(image_bytes) // (1024*1024)} Mo (max 20 Mo).'
        )

    mime     = content_type if content_type in ALLOWED_MIME_TYPES else 'image/jpeg'
    filename = file.filename or 'image'
    logger.info(f'[VISION] fichier={filename}  taille={len(image_bytes)//1024}Ko  mime={mime}')

    try:
        import asyncio
        analysis, model_used = await asyncio.to_thread(_analyze_sync, image_bytes, mime, question)
        logger.info(f'[VISION] OK — {len(analysis)} caractères')
        return {'analysis': analysis, 'model': model_used}

    except HTTPException:
        raise
    except Exception as e:
        err = str(e)
        logger.error(f'[VISION] Erreur : {err[:300]}')
        if '429' in err or 'quota' in err.lower():
            raise HTTPException(status_code=429, detail='Quota Vision dépassé sur toutes les clés.')
        if '401' in err or 'invalid' in err.lower() or 'api_key' in err.lower():
            raise HTTPException(status_code=401, detail='Clé VISION_API_KEY invalide.')
        raise HTTPException(status_code=500, detail=f'Erreur analyse image : {err[:200]}')
