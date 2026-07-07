import re
import time
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse

from api.models    import ChatRequest, ChatResponse
from api.helpers   import rate_ok, clean, confidence, map_level
from mcp_client.qr_parser import parse_quick_replies
from api.session   import get_or_create_thread
from api.db        import get_employee_modules

router = APIRouter()
log    = logging.getLogger('aria.api')

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


@router.post('/chat', response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    start = time.time()
    ip    = request.client.host if request.client else 'unknown'

    if not rate_ok(ip):
        raise HTTPException(429, 'Trop de requetes.')
    if not req.question or not req.question.strip():
        return ChatResponse(answer='Question vide.', backend='none',
                            level='0', duration=0.0, thread_id=req.threadId or 'unknown')
    if not _agent or not _agent.is_ready():
        return ChatResponse(answer='Systeme non disponible.', backend='none',
                            level='0', duration=0.0, thread_id=req.threadId or 'unknown')

    uid = req.userId or 'default_user'
    sid, tid = get_or_create_thread(req.sessionId, uid, req.threadId)
    q = req.question.strip()

    static_resp = _agent.handle_static(q, tid, uid, start)
    if static_resp is not None:
        return ChatResponse(
            answer=static_resp, backend='static', level=map_level('static'),
            duration=round(time.time() - start, 4), thread_id=tid, session_id=sid,
            confidence='haute',
        )

    # Priorité : modules fournis par le client (JWT) > base de données employés
    allowed_modules = req.allowed_modules
    if allowed_modules is None:
        allowed_modules = get_employee_modules(uid)

    try:
        result        = await _agent.process(q, tid, uid, allowed_modules, req.lang or 'fr')
        raw_answer    = clean(result.get('answer', '')) or 'Réponse indisponible.'
        answer, qr    = parse_quick_replies(raw_answer)
        dur           = round(result.get('duration', 0.0), 2)
        level         = result.get('level', '0')
        _b, _m        = result.get('backend', '?'), result.get('model', '')
        backend       = f'{_b}/{_m}' if _m else _b
        log.info('[%s/%.2fs] session=%s len=%d', level.upper(), dur, sid, len(req.question))
        return ChatResponse(
            answer=answer, quick_replies=qr or None,
            backend=backend, level=map_level(level),
            duration=dur, thread_id=tid, session_id=sid,
            message_id=result.get('message_id'),
            confidence=confidence(answer, level),
        )
    except Exception as e:
        log.error(f'Erreur chat : {e}', exc_info=True)
        return ChatResponse(answer='Erreur systeme. Reessayez.', backend='error',
                            level='0', duration=round(time.time() - start, 2),
                            thread_id=tid, session_id=sid)


@router.get('/chat/stream')
async def chat_stream(
    question      : str,
    userId        : str = 'default_user',
    threadId      : str = None,
    lang          : str = 'fr',
    allowedModules: str = None,   # modules JWT côté client, virgule-séparés ex: "eau,gaz"
    request       : Request = None,
):
    """Flux SSE — génération token par token avec phases thinking/tool/chunk.

    allowedModules : optionnel, transmis par l'Angular depuis le JWT décodé.
                     Si absent, on lit les permissions depuis la base de données.
                     Format : chaîne virgule-séparée ("eau,gaz,alertes").
    """
    ip     = request.client.host if (request and request.client) else 'unknown'
    origin = (request.headers.get('origin') or '') if request else ''
    SSE_HEADERS = {
        'Cache-Control'              : 'no-cache',
        'X-Accel-Buffering'          : 'no',
        'Access-Control-Allow-Origin': origin or '*',
    }

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    if not rate_ok(ip):
        async def _limit():
            yield _sse({'type': 'error', 'data': 'Trop de requêtes. Veuillez patienter.'})
        return StreamingResponse(_limit(), media_type='text/event-stream', headers=SSE_HEADERS)

    if not question or not question.strip():
        async def _empty():
            yield _sse({'type': 'error', 'data': 'Question vide.'})
        return StreamingResponse(_empty(), media_type='text/event-stream', headers=SSE_HEADERS)

    if not _agent or not _agent.is_ready():
        async def _unavail():
            yield _sse({'type': 'error', 'data': 'ARIA non disponible.'})
        return StreamingResponse(_unavail(), media_type='text/event-stream', headers=SSE_HEADERS)

    uid = userId or 'default_user'
    _, tid = get_or_create_thread(None, uid, threadId)

    # Priorité : modules fournis par le client (JWT) > base de données employés
    # Miroir exact du comportement du endpoint POST /chat
    if allowedModules is not None:
        modules = [m.strip() for m in allowedModules.split(',') if m.strip()]
    else:
        modules = get_employee_modules(uid)

    async def generate():
        import asyncio as _aio
        import time as _t
        t0 = _t.perf_counter()
        q  = question.strip()

        static_resp = _agent.handle_static(q, tid, uid, t0)
        if static_resp is not None:
            yield _sse({'type': 'chunk', 'data': static_resp})
            yield _sse({'type': 'done', 'level': 'static', 'backend': 'static',
                        'thread_id': tid, 'message_id': int(t0 * 1000),
                        'duration': round(_t.perf_counter() - t0, 4), 'quick_replies': None})
            return

        # Déclenchement manuel du moteur de recommandations via QR "refresh"
        if q.lower() == 'refresh':
            yield _sse({'type': 'thinking', 'data': 'Analyse des données en cours…'})
            try:
                from api.db import get_engine
                from api.pipeline.recommendation_engine import run_recommendation_cycle
                _eng = get_engine()
                if _eng is None:
                    yield _sse({'type': 'chunk', 'data': '🔴 Base de données non disponible.'})
                else:
                    result = await _aio.wait_for(
                        _aio.get_event_loop().run_in_executor(
                            None, lambda: run_recommendation_cycle(_eng)
                        ),
                        timeout=120.0,
                    )
                    generated = result.get('generated', {})
                    total = sum(v for v in generated.values() if isinstance(v, int) and v > 0)
                    lines = [f'✅ Analyse terminée — **{total} recommandation(s) générée(s)**.\n']
                    for dom, n in generated.items():
                        if isinstance(n, int) and n > 0:
                            lines.append(f'• {dom} : {n} recommandation(s)')
                    lines.append('\nDemandez **"recommandations"** pour les consulter.')
                    yield _sse({'type': 'chunk', 'data': '\n'.join(lines)})
            except _aio.TimeoutError:
                yield _sse({'type': 'chunk', 'data': '⏱️ Analyse expirée (>120s). Réessayez domaine par domaine.'})
            except Exception as _e:
                log.error('[REFRESH] %s', _e, exc_info=True)
                yield _sse({'type': 'chunk', 'data': f'🔴 Erreur lors de l\'analyse : {_e}'})
            yield _sse({'type': 'done', 'level': 'data', 'backend': 'system',
                        'thread_id': tid, 'message_id': None,
                        'duration': round(_t.perf_counter() - t0, 2), 'quick_replies': None})
            return

        log.info('[STREAM TIMING] generate_start=%.1fms modules=%s',
                 (_t.perf_counter() - t0) * 1000, modules)
        try:
            first = True
            async for event in _agent.stream_process(q, tid, uid, modules, lang):
                if first:
                    log.info('[STREAM TIMING] first_event=%.1fms type=%s',
                             (_t.perf_counter() - t0) * 1000, event.get('type'))
                    first = False
                yield _sse(event)
        except Exception as e:
            log.error('[STREAM] %s', e, exc_info=True)
            yield _sse({'type': 'error', 'data': 'Erreur système.'})

    return StreamingResponse(generate(), media_type='text/event-stream', headers=SSE_HEADERS)


@router.get('/download/{file_id}')
async def download_file(file_id: str, request: Request = None):
    """Télécharge un fichier généré par ARIA (CSV ou PDF, expire après 1h)."""
    if not re.fullmatch(r'[0-9a-f\-]{36}', file_id):
        raise HTTPException(400, 'Identifiant invalide.')

    dl_origin = (request.headers.get('origin') or '') if request else ''

    # ── CSV ────────────────────────────────────────────────────────────────
    from mcp_client.csv_export import CSV_TMP_DIR
    csv_path = CSV_TMP_DIR / f'{file_id}.csv'
    if csv_path.exists():
        return FileResponse(
            path=str(csv_path),
            filename=(csv_path.stem.split('_', 1)[-1] + '.csv'
                      if '_' in csv_path.stem else 'rapport_aria.csv'),
            media_type='text/csv; charset=utf-8-sig',
            headers={'Access-Control-Allow-Origin': dl_origin or '*'},
        )

    # ── PDF analyse ────────────────────────────────────────────────────────
    from mcp_client.pdf_export import PDF_TMP_DIR
    pdf_path = PDF_TMP_DIR / f'{file_id}.pdf'
    if pdf_path.exists():
        hint      = PDF_TMP_DIR / f'{file_id}.name'
        filename  = hint.read_text(encoding='utf-8').strip() if hint.exists() else 'rapport_aria.pdf'
        return FileResponse(
            path=str(pdf_path),
            filename=filename,
            media_type='application/pdf',
            headers={
                'Access-Control-Allow-Origin'      : dl_origin or '*',
                'Content-Disposition'              : f'attachment; filename="{filename}"',
            },
        )

    raise HTTPException(404, 'Fichier non trouvé ou expiré.')
