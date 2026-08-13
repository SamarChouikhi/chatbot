import os
import base64
import logging
import concurrent.futures
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from langchain_core.messages import HumanMessage

logger = logging.getLogger('aria.vision')
vision_router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 Mo

ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png',
    'image/gif',  'image/webp',
}

_DEFAULT_QUESTION = "Analyse cette image en détail et décris ce que tu vois."

# LLM dédié à l'analyse d'image via Groq. meta-llama/llama-4-scout-17b-16e-instruct
# a été déprécié par Groq le 17/06/2026 pour les tiers gratuit/développeur (voir
# console.groq.com/docs/deprecations) ; qwen/qwen3.6-27b est, à ce jour, le seul
# modèle du catalogue Groq avec input_modalities incluant "image" (confirmé via
# GET /v1/models) — c'est aussi le modèle de migration recommandé par Groq.
_DEFAULT_MODEL       = 'qwen/qwen3.6-27b'
_PER_ATTEMPT_TIMEOUT = 30    # secondes
_MAX_TOKENS          = 2048  # qwen3.6-27b est un modèle "reasoning" : son raisonnement
# (caché via reasoning_format='hidden') consomme ~1000-1500 tokens avant la réponse
# finale — un budget trop bas tronque la réponse (finish_reason='length'). Le
# reasoning est volontairement gardé actif (vs reasoning_effort='none') car les
# tests montrent qu'il évite les hallucinations sur des détails non visibles à
# l'image (ex. inventer l'origine d'un logo inconnu).


def _get_keys() -> list[str]:
    """Clés VISION_API_KEY_N dédiées si présentes, sinon réutilise le pool
    GROQ_API_KEY_N déjà configuré pour le chat (même provider)."""
    keys   = [os.getenv(f'VISION_API_KEY_{i}') for i in range(1, 10)]
    keys   = [k for k in keys if k]
    single = os.getenv('VISION_API_KEY')
    if single and single not in keys:
        keys.append(single)
    if keys:
        return keys
    keys = [os.getenv(f'GROQ_API_KEY_{i}') for i in range(1, 10)]
    return [k for k in keys if k]


def _get_model() -> str:
    return os.getenv('VISION_MODEL', '').strip() or _DEFAULT_MODEL


def _invoke_with_deadline(llm, message, deadline: float):
    """Impose une échéance dure sur l'appel bloquant `llm.invoke`, pour ne
    jamais bloquer la requête HTTP au-delà de `deadline` secondes même si le
    client Groq ne respecte pas son propre timeout."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future   = executor.submit(llm.invoke, [message])
    try:
        return future.result(timeout=deadline)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f'Délai de {deadline}s dépassé')
    finally:
        executor.shutdown(wait=False)


def _analyze_sync(image_bytes: bytes, mime: str, question: str) -> tuple[str, str]:
    """Essaie chaque clé du pool jusqu'à succès — bascule sur la clé suivante
    en cas de quota/rate-limit plutôt que d'échouer directement."""
    from langchain_groq import ChatGroq

    keys = _get_keys()
    if not keys:
        raise RuntimeError('Aucune clé VISION_API_KEY_N ni GROQ_API_KEY_N trouvée dans le .env')

    model    = _get_model()
    b64      = base64.b64encode(image_bytes).decode('utf-8')
    data_url = f'data:{mime};base64,{b64}'
    message  = HumanMessage(content=[
        {'type': 'image_url', 'image_url': {'url': data_url}},
        {'type': 'text',      'text': question},
    ])
    last_err = ''

    for idx, key in enumerate(keys, 1):
        try:
            llm = ChatGroq(
                model=model, api_key=key,
                temperature=0, max_tokens=_MAX_TOKENS, timeout=_PER_ATTEMPT_TIMEOUT,
                max_retries=0, reasoning_format='hidden',
            )
            resp = _invoke_with_deadline(llm, message, _PER_ATTEMPT_TIMEOUT)
            text = (resp.content or '').strip()
            logger.info(f'[VISION] clé #{idx} OK  modèle={model}')
            return text, model

        except Exception as e:
            last_err = str(e)
            retryable = ('429', 'rate limit', 'rate_limit', 'timeout', 'timed out', '504', 'délai de')
            if any(k in last_err.lower() for k in retryable):
                logger.warning(f'[VISION] {model} clé #{idx} indisponible ({last_err[:100]}), clé suivante...')
                continue
            raise RuntimeError(last_err)

    raise RuntimeError(f'Toutes les clés vision Groq sont indisponibles. Dernière erreur : {last_err}')


@vision_router.post('/analyze-image', tags=['vision'])
async def analyze_image(
    file    : UploadFile = File(...),
    question: str        = Form(_DEFAULT_QUESTION),
):
    """Analyse une image via Groq (qwen/qwen3.6-27b, inférence rapide sur LPU)."""

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
        err_low = err.lower()
        if 'toutes les clés vision groq sont indisponibles' in err_low:
            raise HTTPException(
                status_code=503,
                detail='Le service vision Groq est congestionné ou en quota sur toutes les clés. Réessayez dans une minute.'
            )
        if any(k in err_low for k in ('429', 'rate limit', 'rate_limit')):
            raise HTTPException(
                status_code=429,
                detail='Quota gratuit Groq épuisé pour aujourd\'hui.'
            )
        if any(k in err_low for k in ('api_key_invalid', 'api key not valid', 'unauthorized', '401')):
            raise HTTPException(status_code=401, detail='Clé VISION_API_KEY / GROQ_API_KEY invalide.')
        if any(k in err_low for k in ('not found', 'does not exist', 'notfound')):
            raise HTTPException(status_code=502, detail=f'Modèle vision indisponible : {err[:200]}')
        raise HTTPException(status_code=500, detail=f'Erreur analyse image : {err[:200]}')
