"""
Routes ARIA Proactive.

GET  /proactive/messages        → messages non rejetés pour un utilisateur
GET  /proactive/stream          → SSE temps réel
POST /proactive/read/{id}       → marquer comme lu
POST /proactive/dismiss/{id}    → rejeter (ne plus afficher)
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from api.db import get_engine
from api.pipeline.proactive_broadcaster import get_broadcaster

logger = logging.getLogger('aria.api.proactive')
router = APIRouter(prefix='/proactive', tags=['proactive'])


def _engine():
    e = get_engine()
    if not e:
        raise HTTPException(503, 'Base de données non disponible')
    return e


@router.get('/messages')
async def get_proactive_messages(
    userId: str = Query(..., min_length=1, max_length=100),
    limit:  int = Query(20, ge=1, le=100),
):
    """Messages proactifs non rejetés pour un utilisateur, du plus récent au plus ancien."""
    with _engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT id, domain, severity, message, source_type,
                   quick_reply_label, quick_reply_value, created_at, read_at
            FROM aria_proactive_messages
            WHERE user_id = :uid AND dismissed = 0
            ORDER BY created_at DESC
            LIMIT :lim
        """), {'uid': userId, 'lim': limit}).mappings().fetchall()
    return {'count': len(rows), 'messages': [dict(r) for r in rows]}


@router.get('/stream')
async def proactive_stream(
    userId:  str = Query(..., min_length=1, max_length=100),
    request: Request = None,
):
    """
    SSE — Flux en temps réel des messages proactifs ARIA.
    Angular maintient cette connexion ouverte ; dès qu'une anomalie est détectée
    par le scheduler, le message apparaît instantanément dans le chat.
    Heartbeat toutes les 25s pour prévenir les timeouts proxy/nginx.
    """
    origin = (request.headers.get('origin') or '') if request else ''
    SSE_HEADERS = {
        'Cache-Control'              : 'no-cache',
        'X-Accel-Buffering'          : 'no',
        'Access-Control-Allow-Origin': origin or '*',
    }

    broadcaster = get_broadcaster()
    queue       = broadcaster.register(userId)
    logger.info('[PROACTIVE/SSE] user=%s connecté (total=%d)', userId, broadcaster.connection_count())

    async def event_stream():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield 'data: {"type":"heartbeat"}\n\n'
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unregister(userId, queue)
            logger.info('[PROACTIVE/SSE] user=%s déconnecté', userId)

    return StreamingResponse(event_stream(), media_type='text/event-stream', headers=SSE_HEADERS)


@router.post('/read/{msg_id}')
async def mark_read(msg_id: int):
    """Marque un message proactif comme lu (reste visible)."""
    with _engine().begin() as conn:
        conn.execute(text(
            'UPDATE aria_proactive_messages SET read_at = NOW() WHERE id = :id'
        ), {'id': msg_id})
    return {'ok': True}


@router.post('/dismiss/{msg_id}')
async def dismiss_message(
    msg_id: int,
    userId: str = Query(..., min_length=1, max_length=100),
):
    """Rejette un message proactif — il disparaît de l'interface et ne revient pas."""
    with _engine().begin() as conn:
        conn.execute(text("""
            UPDATE aria_proactive_messages
            SET dismissed = 1
            WHERE id = :id AND user_id = :uid
        """), {'id': msg_id, 'uid': userId})
    return {'ok': True}
