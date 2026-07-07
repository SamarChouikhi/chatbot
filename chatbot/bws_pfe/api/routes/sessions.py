import logging
from fastapi import APIRouter, HTTPException, Query

from api.session import list_active_sessions, remove_session
from api.db      import get_history_db

router = APIRouter()
log    = logging.getLogger('aria.api')


@router.get('/sessions')
async def get_sessions(user_id: str = Query(None, description='Filtrer par utilisateur')):
    sessions = list_active_sessions()
    if user_id:
        sessions = [s for s in sessions if s.get('user_id') == user_id]
    return sessions


@router.get('/sessions/{session_id}/messages')
async def get_session_messages(session_id: str, limit: int = Query(50, ge=1, le=200)):
    sessions = {s['session_id']: s for s in list_active_sessions()}
    if session_id not in sessions:
        raise HTTPException(404, f'Session {session_id} non trouvée')

    thread_id = sessions[session_id]['thread_id']
    db        = get_history_db()
    if not db:
        raise HTTPException(503, 'Historique non disponible')

    messages = db.get_conversation_history(thread_id, limit)
    return {
        'session_id': session_id,
        'thread_id' : thread_id,
        'user_id'   : sessions[session_id]['user_id'],
        'messages'  : messages,
    }


@router.delete('/sessions/{session_id}')
async def end_session(session_id: str):
    if remove_session(session_id):
        log.info(f'[SESSION END] {session_id}')
        return {'status': 'ended', 'session_id': session_id}
    raise HTTPException(404, f'Session {session_id} non trouvée')
