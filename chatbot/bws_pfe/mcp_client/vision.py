# ══════════════════════════════════════════════════════════════════════════
# PARTIE VISION — analyse d'image via HuggingFace Inference Providers (Qwen3-VL)
# ══════════════════════════════════════════════════════════════════════════
import os
import re
import time
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

# LLM dédié à l'analyse d'image via HuggingFace Inference Providers
# (router.huggingface.co, API OpenAI-compatible — même client/pattern que
# llm_factory.py::_try_huggingface pour le chat).
#
# Migré depuis Groq (qwen/qwen3.6-27b) le 11/09/2026 : le tier gratuit Groq
# plafonne à 1000 tokens de sortie/minute PAR ORGANISATION (OTPM), partagés par
# toutes les clés — un seul appel vision consommant déjà 1000-2000+ tokens de
# raisonnement caché, ~1 appel/minute passait de façon fiable (voir historique
# git). HF Inference Providers facture à l'usage (aucun provider vision marqué
# `is_free` via GET https://router.huggingface.co/v1/models au 11/09/2026 —
# vérifier le solde de crédit HuggingFace si des 402 apparaissent) mais sans ce
# plafond agressif par minute.
#
# Qwen/Qwen3-VL-30B-A3B-Instruct : génération vision-langage Qwen3 la plus
# récente au moment du choix, MoE (30B total / ~3B actifs → rapide et économe),
# bonne lecture de texte/chiffres denses dans une image (dashboards, tableaux —
# cas d'usage principal ici). Alternative plus lourde si besoin de plus de
# précision : Qwen/Qwen2.5-VL-72B-Instruct.
_DEFAULT_MODEL       = 'Qwen/Qwen3-VL-30B-A3B-Instruct'
_PER_ATTEMPT_TIMEOUT = 30    # secondes
_MAX_TOKENS          = 2048  # Qwen3-VL supporte le mode "thinking" comme Qwen3 texte :
# un budget trop bas peut tronquer la réponse avant qu'elle ne soit écrite (content
# vide). Voir _TruncatedEmptyResponse / no_reasoning plus bas pour le filet de sécurité.


# ── Configuration & rotation des clés ────────────────────────────────────────

def _get_keys() -> list[str]:
    """Clés VISION_API_KEY_N dédiées si présentes, sinon réutilise le pool
    HF_API_KEY_N déjà configuré pour le chat (même provider : HuggingFace)."""
    keys   = [os.getenv(f'VISION_API_KEY_{i}') for i in range(1, 10)]
    keys   = [k for k in keys if k]
    single = os.getenv('VISION_API_KEY')
    if single and single not in keys:
        keys.append(single)
    if keys:
        return keys
    keys = [os.getenv(f'HF_API_KEY_{i}') for i in range(1, 10)]
    return [k for k in keys if k]


def _get_model() -> str:
    return os.getenv('VISION_MODEL', '').strip() or _DEFAULT_MODEL


def _retry_after_seconds(exc: Exception, default: float = 15.0, cap: float = 30.0) -> float:
    """Délai d'attente avant nouvel essai : header Retry-After renvoyé par le
    provider si disponible, sinon parsé du message d'erreur, sinon `default`.
    Borné à `cap` secondes pour rester sous le timeout front-end (150s, voir
    aria.service.ts) même en cumulant plusieurs clés."""
    resp = getattr(exc, 'response', None)
    if resp is not None:
        try:
            ra = resp.headers.get('retry-after')
            if ra:
                return min(float(ra), cap)
        except (TypeError, ValueError, AttributeError):
            pass
    m = re.search(r'try again in ([\d.]+)s', str(exc), re.IGNORECASE)
    if m:
        try:
            return min(float(m.group(1)), cap)
        except ValueError:
            pass
    return default


def _invoke_with_deadline(llm, message, deadline: float):
    """Impose une échéance dure sur l'appel bloquant `llm.invoke`, pour ne
    jamais bloquer la requête HTTP au-delà de `deadline` secondes même si le
    client HTTP ne respecte pas son propre timeout."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future   = executor.submit(llm.invoke, [message])
    try:
        return future.result(timeout=deadline)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f'Délai de {deadline}s dépassé')
    finally:
        executor.shutdown(wait=False)


# ── Appel LLM vision (essai unique + logique multi-clés) ─────────────────────

class _TruncatedEmptyResponse(RuntimeError):
    """Le modèle a renvoyé un contenu vide — budget de tokens épuisé (raisonnement
    "thinking" de Qwen3) avant d'écrire la moindre réponse visible. Déterministe
    à temperature=0 : retenter la même clé/config redonnerait le même résultat
    vide, il faut changer de stratégie de génération (voir `no_reasoning`)."""


_RETRYABLE_MARKERS = (
    '429', 'rate limit', 'rate_limit', 'timeout', 'timed out',
    '502', '503', '504', 'délai de', 'model is loading', 'model_loading',
)


def _try_one_key(model: str, key: str, message: HumanMessage, *, no_reasoning: bool = False) -> str:
    """Un seul essai d'appel vision sur une clé donnée. Laisse remonter
    l'exception d'origine (pas de str() ici) pour que l'appelant puisse
    inspecter `.response` (header Retry-After) le cas échéant.

    `no_reasoning=True` désactive le mode "thinking" de Qwen3 via extra_body
    (même mécanisme que llm_factory.py::_try_huggingface pour le chat) —
    dernier recours quand le raisonnement a épuisé tout le budget de tokens
    sans jamais produire de réponse visible (cf. _TruncatedEmptyResponse)."""
    from langchain_openai import ChatOpenAI
    kwargs: dict = dict(
        model=model, api_key=key,
        base_url='https://router.huggingface.co/v1',
        temperature=0, max_tokens=_MAX_TOKENS, timeout=_PER_ATTEMPT_TIMEOUT,
        max_retries=0,
    )
    if no_reasoning:
        kwargs['extra_body'] = {'chat_template_kwargs': {'enable_thinking': False}}

    llm  = ChatOpenAI(**kwargs)
    resp = _invoke_with_deadline(llm, message, _PER_ATTEMPT_TIMEOUT)
    text = (resp.content or '').strip()

    if not text and not no_reasoning:
        finish = (getattr(resp, 'response_metadata', None) or {}).get('finish_reason')
        raise _TruncatedEmptyResponse(
            f"Réponse vide — budget de {_MAX_TOKENS} tokens épuisé avant d'écrire "
            f"une réponse (finish_reason={finish})."
        )
    return text


def _analyze_sync(image_bytes: bytes, mime: str, question: str) -> tuple[str, str]:
    """Essaie chaque clé du pool jusqu'à succès — bascule sur la clé suivante
    en cas de quota/rate-limit plutôt que d'échouer directement."""
    keys = _get_keys()
    if not keys:
        raise RuntimeError('Aucune clé VISION_API_KEY_N ni HF_API_KEY_N trouvée dans le .env')

    model    = _get_model()
    b64      = base64.b64encode(image_bytes).decode('utf-8')
    data_url = f'data:{mime};base64,{b64}'
    message  = HumanMessage(content=[
        {'type': 'image_url', 'image_url': {'url': data_url}},
        {'type': 'text',      'text': question},
    ])
    last_err: str = ''
    last_exc: Exception | None = None

    for idx, key in enumerate(keys, 1):
        try:
            text = _try_one_key(model, key, message)
            logger.info(f'[VISION] clé #{idx} OK  modèle={model}')
            return text, model

        except _TruncatedEmptyResponse as e:
            # Déterministe (temperature=0) : cycler les clés redonnerait le même
            # vide. Dernier recours immédiat sur la MÊME clé, raisonnement coupé —
            # accepte un léger risque d'hallucination plutôt qu'une réponse vide.
            logger.warning(f'[VISION] {model} clé #{idx} : {e} — nouvel essai sans '
                            f'raisonnement (dernier recours)...')
            try:
                text = _try_one_key(model, key, message, no_reasoning=True)
                logger.info(f'[VISION] clé #{idx} OK sans raisonnement  modèle={model}')
                return text, model
            except Exception as e2:
                last_err, last_exc = str(e2), e2
                if any(k in last_err.lower() for k in _RETRYABLE_MARKERS):
                    logger.warning(f'[VISION] {model} clé #{idx} indisponible ({last_err[:100]}), '
                                    f'clé suivante...')
                    continue
                raise RuntimeError(last_err)

        except Exception as e:
            last_err, last_exc = str(e), e
            if any(k in last_err.lower() for k in _RETRYABLE_MARKERS):
                logger.warning(f'[VISION] {model} clé #{idx} indisponible ({last_err[:100]}), clé suivante...')
                continue
            raise RuntimeError(last_err)

    # Toutes les clés ont échoué avec une erreur retryable (429/timeout/5xx) : une
    # dernière attente + un dernier essai avant d'abandonner pour de bon.
    if last_exc is not None:
        wait = _retry_after_seconds(last_exc)
        logger.warning(f'[VISION] {model} : toutes les clés indisponibles, attente '
                        f'{wait:.0f}s puis 1 dernier essai...')
        time.sleep(wait)
        try:
            text = _try_one_key(model, keys[0], message)
            logger.info(f'[VISION] clé #1 OK après attente  modèle={model}')
            return text, model
        except Exception as e2:
            last_err = str(e2)
            logger.warning(f'[VISION] {model} : toujours indisponible après attente ({last_err[:100]})')

    raise RuntimeError(f'Toutes les clés vision HuggingFace sont indisponibles. Dernière erreur : {last_err}')


# ── Route /analyze-image ─────────────────────────────────────────────────────

@vision_router.post('/analyze-image', tags=['vision'])
async def analyze_image(
    file    : UploadFile = File(...),
    question: str        = Form(_DEFAULT_QUESTION),
):
    """Analyse une image via HuggingFace Inference Providers (Qwen3-VL)."""

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
        if 'toutes les clés vision huggingface sont indisponibles' in err_low:
            raise HTTPException(
                status_code=503,
                detail="Le service vision HuggingFace est congestionné sur toutes les clés. Réessayez dans une minute."
            )
        if any(k in err_low for k in ('402', 'payment required', 'insufficient', 'credit')):
            raise HTTPException(
                status_code=402,
                detail="Crédit HuggingFace insuffisant pour l'analyse d'image "
                       "(huggingface.co/settings/billing)."
            )
        if any(k in err_low for k in ('429', 'rate limit', 'rate_limit')):
            raise HTTPException(status_code=429, detail='Quota HuggingFace atteint, réessayez dans un instant.')
        if any(k in err_low for k in ('api_key_invalid', 'invalid_api_key', 'api key not valid', 'unauthorized', '401')):
            raise HTTPException(status_code=401, detail='Clé VISION_API_KEY / HF_API_KEY invalide.')
        if any(k in err_low for k in ('not found', 'does not exist', 'notfound')):
            raise HTTPException(status_code=502, detail=f'Modèle vision indisponible : {err[:200]}')
        raise HTTPException(status_code=500, detail=f'Erreur analyse image : {err[:200]}')
