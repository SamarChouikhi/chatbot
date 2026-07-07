import logging
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from api.models import FeedbackRequest
from api.db     import get_engine

router = APIRouter()
log    = logging.getLogger('aria.api')


@router.post('/feedback')
async def post_feedback(req: FeedbackRequest):
    if req.vote not in ('up', 'down'):
        raise HTTPException(400, 'vote doit être "up" ou "down"')
    engine = get_engine()
    if not engine:
        raise HTTPException(503, 'DB non disponible')
    with engine.connect() as conn:
        conn.execute(
            text('''INSERT INTO chat_feedback (message_id, thread_id, user_id, vote, comment)
                    VALUES (:mid, :tid, :uid, :vote, :comment)
                    ON DUPLICATE KEY UPDATE vote=:vote, comment=:comment'''),
            {
                'mid'    : req.message_id,
                'tid'    : req.thread_id,
                'uid'    : req.user_id or 'default_user',
                'vote'   : req.vote,
                'comment': req.comment,
            }
        )
        conn.commit()
    log.info(f'[FEEDBACK] msg={req.message_id} vote={req.vote}')
    return {'status': 'ok', 'vote': req.vote}


@router.get('/feedback/stats')
async def feedback_stats():
    engine = get_engine()
    if not engine:
        raise HTTPException(503, 'DB non disponible')
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) total, SUM(vote='up') up, SUM(vote='down') down "
                 "FROM chat_feedback")
        ).fetchone()
    return dict(row._mapping)
