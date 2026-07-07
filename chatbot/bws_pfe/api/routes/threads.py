import json
import logging
from typing import List
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from api.models import ThreadInfo, MessageOut
from api.db     import get_history_db, get_engine

router = APIRouter()
log    = logging.getLogger('aria.api')


@router.get('/threads/search')
async def search_threads(
    q      : str = Query(..., min_length=1),
    user_id: str = Query('default_user'),
    limit  : int = Query(10, ge=1, le=50),
):
    db = get_history_db()
    if not db:
        raise HTTPException(503, 'Historique non disponible')
    return db.search_threads(user_id, q, limit)


@router.get('/threads', response_model=List[ThreadInfo])
async def get_threads(
    user_id: str = Query('default_user'),
    limit  : int = Query(20, ge=1, le=100),
):
    db = get_history_db()
    if not db:
        raise HTTPException(503, 'Historique non disponible')
    return [
        ThreadInfo(
            thread_id    =t['thread_id'],
            title        =t['title'],
            message_count=t['message_count'],
            created_at   =str(t['created_at']),
            updated_at   =str(t['updated_at']),
            preview      =t.get('preview'),
            is_favorite  =bool(t.get('is_favorite', 0)),
        )
        for t in db.get_user_threads(user_id, limit)
    ]


@router.put('/threads/{thread_id}/favorite')
async def toggle_favorite(thread_id: str):
    db = get_history_db()
    if not db:
        raise HTTPException(503, 'Historique non disponible')
    if not db.get_thread_by_id(thread_id):
        raise HTTPException(404, f'Thread {thread_id} non trouvé')
    is_fav = db.toggle_favorite(thread_id)
    return {'status': 'updated', 'thread_id': thread_id, 'is_favorite': is_fav}


@router.get('/threads/{thread_id}/messages', response_model=List[MessageOut])
async def get_messages(thread_id: str, limit: int = Query(50, ge=1, le=200)):
    db = get_history_db()
    if not db:
        raise HTTPException(503, 'Historique non disponible')
    if not db.get_thread_by_id(thread_id):
        raise HTTPException(404, f'Thread {thread_id} non trouvé')

    messages  = db.get_conversation_history(thread_id, limit)
    feedbacks = {}

    # Charge les votes en une seule requête pour éviter le N+1
    engine = get_engine()
    if engine:
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text('SELECT message_id, vote FROM chat_feedback WHERE thread_id = :tid'),
                    {'tid': thread_id}
                ).fetchall()
                feedbacks = {r.message_id: r.vote for r in rows}
        except Exception:
            pass

    return [
        MessageOut(
            id        =m.get('id'),
            role      =m['role'],
            content   =m['content'],
            level     =m.get('level'),
            backend   =m.get('backend'),
            created_at=str(m['created_at']),
            feedback  =feedbacks.get(m.get('id')),
            chart_data=_parse_json(m.get('chart_data')),
        )
        for m in messages
    ]


def _parse_json(val):
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return None


@router.delete('/threads/{thread_id}')
async def delete_thread(thread_id: str):
    db = get_history_db()
    if not db:
        raise HTTPException(503, 'Historique non disponible')
    if db.delete_thread(thread_id):
        return {'status': 'deleted', 'thread_id': thread_id}
    raise HTTPException(404, f'Thread {thread_id} non trouvé')


@router.put('/threads/{thread_id}/title')
async def update_title(thread_id: str, title: str = Query(..., min_length=1)):
    db = get_history_db()
    if not db:
        raise HTTPException(503, 'Historique non disponible')
    if not db.get_thread_by_id(thread_id):
        raise HTTPException(404, f'Thread {thread_id} non trouvé')
    db.update_thread_title(thread_id, title)
    return {'status': 'updated', 'thread_id': thread_id, 'title': title}
