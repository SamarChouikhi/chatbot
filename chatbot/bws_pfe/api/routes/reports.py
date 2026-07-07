import time
import logging
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from api.helpers import clean
from api.db      import get_engine

router = APIRouter()
log    = logging.getLogger('aria.api')

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


@router.get('/reports')
async def get_reports(limit: int = Query(30, ge=1, le=100)):
    engine = get_engine()
    if not engine:
        raise HTTPException(503, 'DB non disponible')
    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT date, status, summary, generated_at, duration '
                 'FROM aria_reports ORDER BY date DESC LIMIT :l'),
            {'l': limit}
        ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get('/reports/{date}')
async def get_report(date: str):
    engine = get_engine()
    if not engine:
        raise HTTPException(503, 'DB non disponible')
    with engine.connect() as conn:
        row = conn.execute(
            text('SELECT * FROM aria_reports WHERE date = :d'),
            {'d': date}
        ).fetchone()
    if not row:
        raise HTTPException(404, f'Rapport {date} non trouvé')
    return dict(row._mapping)


@router.post('/reports/generate')
async def generate_report(period: str = Query('24h')):
    if not _agent or not _agent.is_ready():
        raise HTTPException(503, 'ARIA non disponible')

    start = time.time()
    today = time.strftime('%Y-%m-%d')

    result  = await _agent.process(
        f'Genere un rapport complet sur {period}: capteurs, anomalies, alertes, stats THL. '
        f'Verdict: nominal/attention/critique.',
        f'report-{today}'
    )
    summary  = clean(result['answer'])
    duration = round(time.time() - start, 2)

    # Détermine la sévérité du rapport selon les mots-clés présents dans le résumé
    status = (
        'critique'  if any(k in summary.lower() for k in ['critique', 'urgent'])  else
        'attention' if any(k in summary.lower() for k in ['attention', 'anomalie', 'alerte']) else
        'nominal'
    )

    engine = get_engine()
    if engine:
        with engine.connect() as conn:
            conn.execute(
                text('''INSERT INTO aria_reports (date, status, summary, duration, period)
                        VALUES (:d, :s, :sum, :dur, :p)
                        ON DUPLICATE KEY UPDATE
                        status=:s, summary=:sum, generated_at=NOW(), duration=:dur'''),
                {'d': today, 's': status, 'sum': summary, 'dur': duration, 'p': period}
            )
            conn.commit()

    log.info(f'[REPORT] {today} → {status} ({duration}s)')
    return {
        'date'        : today,
        'status'      : status,
        'summary'     : summary,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'duration'    : duration,
    }
