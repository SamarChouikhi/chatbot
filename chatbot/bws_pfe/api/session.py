import time
from typing import Optional

_sessions: dict[str, dict] = {}
_SESSION_TTL      = 3600 * 4  # 4h d'inactivité → expiration
_CLEANUP_INTERVAL = 300        # nettoyage au plus toutes les 5 min
_last_cleanup     = 0.0


def _cleanup():
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    dead = [sid for sid, data in _sessions.items()
            if now - data['last_activity'] > _SESSION_TTL]
    for sid in dead:
        del _sessions[sid]
    _last_cleanup = now


def get_or_create_thread(
    session_id: Optional[str],
    user_id: str,
    thread_id: Optional[str] = None,
) -> tuple[str, str]:
    _cleanup()
    if thread_id and thread_id.strip():
        tid = thread_id.strip()
        sid = session_id or tid
        existing = _sessions.get(sid, {})
        _sessions[sid] = {
            'thread_id'    : tid,
            'user_id'      : user_id,
            'created_at'   : existing.get('created_at', time.time()),
            'last_activity': time.time(),
        }
        return sid, tid

    if session_id and session_id in _sessions:
        _sessions[session_id]['last_activity'] = time.time()
        return session_id, _sessions[session_id]['thread_id']

    sid = session_id or f'{user_id}-{int(time.time())}'
    tid = f'thread-{sid}'
    print(f"[DEBUG] Creating new session: {sid}, thread: {tid} for user: {user_id}", flush=True)
    _sessions[sid] = {
        'thread_id'    : tid,
        'user_id'      : user_id,
        'created_at'   : time.time(),
        'last_activity': time.time(),
    }
    return sid, tid


def new_thread(session_id: Optional[str], user_id: str) -> tuple[str, str]:
    """Force la création d'un nouveau thread pour une session donnée."""
    sid = session_id or f'{user_id}-{int(time.time())}'
    tid = f'thread-{sid}-{int(time.time())}'
    _sessions[sid] = {
        'thread_id'    : tid,
        'user_id'      : user_id,
        'created_at'   : time.time(),
        'last_activity': time.time(),
    }
    return sid, tid


def list_active_sessions() -> list[dict]:
    _cleanup()
    return [
        {'session_id': sid, **data}
        for sid, data in sorted(
            _sessions.items(),
            key=lambda x: x[1]['last_activity'],
            reverse=True,
        )
    ]


def remove_session(session_id: str) -> bool:
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
