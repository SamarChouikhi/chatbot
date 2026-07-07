"""
Scheduler quotidien APScheduler (AsyncIOScheduler).
Tourne à 03h00 UTC pour agréger les données de la veille.
HotStart s'exécute dans un ThreadPool pour ne pas bloquer la boucle asyncio.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date as Date, datetime, timedelta
from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger('aria.pipeline.scheduler')

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone='UTC')
    return _scheduler


def start(engine) -> None:
    """Démarre le scheduler. Appelé depuis le lifespan FastAPI."""
    from apscheduler.triggers.interval import IntervalTrigger
    import os

    sched = get_scheduler()

    # Replay des données historiques à 01h00 UTC (avant le pipeline à 03h00)
    replay_hour   = int(os.environ.get('REPLAY_HOUR_UTC', '1'))
    replay_minute = int(os.environ.get('REPLAY_MINUTE_UTC', '0'))
    sched.add_job(
        func=partial(_sync_replay, engine),
        trigger=CronTrigger(hour=replay_hour, minute=replay_minute, timezone='UTC'),
        id='data_replay',
        name='Daily data replay — cycle historique → date courante',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Pipeline quotidien : agrégation + AD à 03h00 UTC
    sched.add_job(
        func=partial(_sync_pipeline, engine),
        trigger=CronTrigger(hour=3, minute=0, timezone='UTC'),
        id='daily_pipeline',
        name='Daily IoT aggregation + AD detection',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Proactive check toutes les 2h : analyse anomalies + prédictions → push SSE
    sched.add_job(
        func=partial(_sync_proactive_check, engine),
        trigger=IntervalTrigger(hours=2),
        id='proactive_check',
        name='ARIA Proactive — anomaly push',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Recommandations IA personnalisées à 04h00 UTC (après pipeline AD à 03h00)
    sched.add_job(
        func=partial(_sync_recommendations, engine),
        trigger=CronTrigger(hour=4, minute=0, timezone='UTC'),
        id='recommendation_cycle',
        name='ARIA Recommendations — baselines + génération + ROI',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Audit hebdomadaire ColdStart → HotStart (dimanche 02:00 UTC, avant le pipeline AD)
    sched.add_job(
        func=partial(_sync_strategy_audit, engine),
        trigger=CronTrigger(day_of_week='sun', hour=2, minute=0, timezone='UTC'),
        id='strategy_audit',
        name='ARIA Strategy Audit — ColdStart→HotStart upgrades',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    sched.start()
    logger.info(
        "Scheduler démarré — data_replay@%02d:%02d UTC | daily_pipeline@03:00 UTC | "
        "proactive_check@/2h | recommendations@04:00 UTC | strategy_audit@dim02:00 UTC",
        replay_hour, replay_minute,
    )

    # Backfill au démarrage + pipeline AD enchaîné si nécessaire (non bloquant)
    # _trigger_startup_backfill retourne True si elle a pris en charge l'AD (daily_stale or ad_stale)
    # → dans ce cas, _trigger_ad_startup_check est un no-op (évite un double run)
    ad_scheduled = _trigger_startup_backfill(engine)
    if not ad_scheduled:
        _trigger_ad_startup_check(engine)


def stop() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler arrêté")


def _trigger_startup_backfill(engine) -> None:
    """Lance un backfill 30 jours en arrière-plan si les données récentes manquent.

    Si le backfill s'exécute, il est suivi automatiquement du pipeline AD pour peupler
    ad_results — les deux étapes sont enchaînées dans le même thread pour garantir
    que daily_* est prêt avant que le pipeline AD ne le lise.
    """
    import threading
    from api.pipeline.archive_sync import needs_backfill, backfill

    daily_stale = needs_backfill(engine, threshold_days=2)
    ad_stale    = _needs_ad_backfill(engine)

    if not daily_stale and not ad_stale:
        logger.info("Startup backfill ignoré — daily_* et ad_results sont récents.")
        return False

    logger.info(
        "Startup : daily_stale=%s | ad_stale=%s — lancement du backfill en arrière-plan…",
        daily_stale, ad_stale,
    )

    def _run():
        # Étape 1 : peuple daily_* si nécessaire
        if daily_stale:
            try:
                result = backfill(engine, days=30)
                ok = sum(
                    1 for r in (result.get('sync') or {}).values()
                    if r.get('status') == 'ok'
                )
                logger.info("Startup backfill terminé — %d domaines synchronisés.", ok)
            except Exception as exc:
                logger.error("Startup backfill échoué : %s", exc, exc_info=True)

        # Étape 2 : peuple ad_results si vide/périmé (enchaîné après étape 1)
        if ad_stale:
            _run_ad_startup(engine)

    t = threading.Thread(target=_run, name='startup-backfill', daemon=True)
    t.start()
    return True  # AD sera géré dans ce thread


def _needs_ad_backfill(engine, threshold_days: int = 2) -> bool:
    """Retourne True si ad_results est vide ou si la dernière entrée a plus de threshold_days jours."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            max_run = conn.execute(text('SELECT MAX(DATE(run_at)) FROM ad_results')).scalar()
        if max_run is None:
            return True
        from datetime import date as _Date
        return (datetime.utcnow().date() - _Date.fromisoformat(str(max_run))).days > threshold_days
    except Exception:
        return True


def _run_ad_startup(engine) -> None:
    """Exécute le pipeline AD pour les 4 domaines (synchrone — à appeler depuis un thread)."""
    try:
        import pandas as pd
        from api.pipeline.ad_runner import run_ad_domain
        run_date = datetime.utcnow().date()
        totals   = {}
        for domain in ('energy', 'water', 'gas', 'fuel'):
            try:
                n = run_ad_domain(engine, pd.DataFrame(), domain, run_date)
                totals[domain] = n
                logger.info("[AD startup:%s] %d anomalies détectées.", domain, n)
            except Exception as exc:
                logger.error("[AD startup:%s] Erreur : %s", domain, exc, exc_info=True)
                totals[domain] = -1
        ok_count = sum(1 for v in totals.values() if v >= 0)
        logger.info("Startup AD terminé — %d/%d domaines OK | %s", ok_count, len(totals), totals)
    except Exception as exc:
        logger.error("Startup AD check échoué : %s", exc, exc_info=True)


def _trigger_ad_startup_check(engine) -> None:
    """Lance le pipeline AD seul si daily_* est récent mais ad_results est périmé.

    Cas d'usage : redéploiement sans changement de daily_* (daily_stale=False).
    La fonction est un no-op si _trigger_startup_backfill a déjà planifié l'AD.
    """
    import threading

    if not _needs_ad_backfill(engine):
        logger.info("Startup AD check ignoré — ad_results récent.")
        return

    logger.info("ad_results vide ou périmé — lancement du pipeline AD au démarrage…")
    t = threading.Thread(target=_run_ad_startup, args=(engine,), name='startup-ad-check', daemon=True)
    t.start()


async def run_replay_now(engine, domains: list | None = None) -> dict:
    """Déclenche le replay manuellement depuis un endpoint async."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_sync_replay, engine, domains))


async def run_now(engine, run_date: Date | None = None, hours_back: int = 96) -> dict:
    """Déclenche le pipeline manuellement depuis un endpoint async."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_sync_pipeline, engine, run_date, hours_back))


def _sync_pipeline(engine, run_date: Date | None = None, hours_back: int = 96) -> dict:
    """
    Point d'entrée synchrone pour le scheduler et run_in_executor.
    run_date = hier par défaut (le job tourne à 03h UTC, données de la veille complètes).
    """
    if run_date is None:
        run_date = datetime.utcnow().date() - timedelta(days=1)
    return _run_for_date(engine, run_date, hours_back)


def _run_for_date(engine, run_date: Date, hours_back: int = 96) -> dict:
    import pandas as pd
    from api.pipeline.extractor  import extract_energy, extract_water, extract_gas, extract_fuel
    from api.pipeline.aggregator import aggregate_energy, aggregate_water, aggregate_gas, aggregate_fuel
    from api.pipeline.ad_runner  import run_ad_domain
    from sqlalchemy import text

    run_id  = _start_run(engine)
    results = {}

    domains = [
        ('energy', extract_energy, aggregate_energy),
        ('water',  extract_water,  aggregate_water),
        ('gas',    extract_gas,    aggregate_gas),
        ('fuel',   extract_fuel,   aggregate_fuel),
    ]

    for domain, extractor, aggregator in domains:
        try:
            logger.info("[%s] Extraction (%dh)...", domain, hours_back)
            df = extractor(hours_back=hours_back)

            logger.info("[%s] Agrégation → daily_%s...", domain, domain)
            n_agg = aggregator(engine, df, run_date)

            # AD utilise TOUJOURS les tables daily_* (historique complet) pour que
            # HotStart/Chronos ait assez de contexte (context_length pouvant atteindre
            # 1440h), indépendamment de la fenêtre d'extraction (hours_back=96).
            logger.info("[%s] Détection d'anomalies (AD — HotStart + ColdStart)...", domain)
            n_ad = run_ad_domain(engine, pd.DataFrame(), domain, run_date)

            results[domain] = {'status': 'ok', 'aggregated': n_agg, 'anomalies': n_ad}
            logger.info("[%s] ✓ %d lignes agrégées | %d anomalies", domain, n_agg, n_ad)

        except Exception as exc:
            logger.error("[%s] ERREUR : %s", domain, exc, exc_info=True)
            results[domain] = {'status': 'error', 'error': str(exc)}

    has_ok    = any(r['status'] == 'ok'    for r in results.values())
    all_ok    = all(r['status'] == 'ok'    for r in results.values())
    overall   = 'success' if all_ok else ('partial' if has_ok else 'failed')

    _end_run(engine, run_id, overall, results)
    logger.info("Pipeline terminé — run_date=%s statut=%s", run_date, overall)
    return {'run_id': run_id, 'status': overall, 'run_date': str(run_date), 'results': results}


def _sync_replay(engine, domains: list | None = None) -> dict:
    """
    Replay des données pour aujourd'hui + sync mensuel.
    Utilise _backfill_domain_j (copie directe) plutôt que le mécanisme cyclique.
    """
    from api.pipeline.archive_sync import _backfill_domain_j, run_archive_sync
    from api.pipeline.data_replay  import DOMAIN_CONFIG

    today   = datetime.utcnow().date()
    domains = domains or list(DOMAIN_CONFIG.keys())
    results = {}

    for domain in domains:
        try:
            n = _backfill_domain_j(engine, domain, days=1)
            results[domain] = {'status': 'ok', 'rows': n}
        except Exception as exc:
            logger.error("[replay:%s] Erreur : %s", domain, exc, exc_info=True)
            results[domain] = {'status': 'error', 'error': str(exc)}

    # Reconstruction des agrégats mensuels
    try:
        sync_res = run_archive_sync(engine, today)
        results['_monthly_sync'] = sync_res
    except Exception as exc:
        logger.error("[replay] Erreur sync mensuel : %s", exc, exc_info=True)

    ok = sum(1 for k, v in results.items() if k != '_monthly_sync' and v.get('status') == 'ok')
    logger.info("Data replay terminé pour %s — %d/%d domaines OK", today, ok, len(domains))
    return results


def _sync_recommendations(engine) -> None:
    """Cycle complet recommandations : baselines + génération + ROI."""
    try:
        from api.pipeline.recommendation_engine import run_recommendation_cycle
        run_recommendation_cycle(engine)
    except Exception as exc:
        logger.error('[RECO] Erreur cycle recommandations : %s', exc, exc_info=True)


def _sync_strategy_audit(engine) -> None:
    """
    Détecte et log les devices ColdStart ayant accumulé assez d'historique
    pour passer en HotStart (> _HOT_MIN_DAYS jours distincts dans daily_*).

    Le routage lui-même est automatique à chaque run AD — ce job sert uniquement
    à surfacer les transitions pour les opérateurs avant qu'elles se produisent.
    """
    try:
        from api.pipeline.ad_runner import check_strategy_upgrades
        transitions = check_strategy_upgrades(engine)
        total = sum(len(v) for v in transitions.values())
        logger.info(
            '[STRATEGY_AUDIT] Terminé — %d upgrade(s) détecté(s) : %s',
            total,
            {k: [t['device_id'] for t in v] for k, v in transitions.items() if v} or 'aucun',
        )
    except Exception as exc:
        logger.error('[STRATEGY_AUDIT] Erreur : %s', exc, exc_info=True)


def _sync_proactive_check(engine) -> None:
    """Analyse proactive — détecte anomalies récentes/prédictions et push aux utilisateurs."""
    try:
        from api.pipeline.proactive            import run_proactive_check, persist_and_broadcast
        from api.pipeline.proactive_broadcaster import get_broadcaster
        from api.session                        import list_active_sessions

        # Cible : utilisateurs ayant eu une activité récente (session active)
        active = list_active_sessions()
        user_ids = list({s['user_id'] for s in active if s.get('user_id')})

        if not user_ids:
            logger.debug('[PROACTIVE] Aucun utilisateur actif — skip')
            return

        broadcaster = get_broadcaster()
        alerts      = run_proactive_check(engine, user_ids)
        persist_and_broadcast(engine, alerts, broadcaster)

    except Exception as exc:
        logger.error('[PROACTIVE] Erreur check proactif : %s', exc, exc_info=True)


def _start_run(engine) -> int:
    from sqlalchemy import text
    with engine.begin() as conn:
        r = conn.execute(text(
            "INSERT INTO pipeline_runs (started_at, status) VALUES (NOW(), 'running')"
        ))
        return r.lastrowid


def _end_run(engine, run_id: int, status: str, summary: dict) -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE pipeline_runs SET ended_at=NOW(), status=:s, summary=:sum WHERE id=:id"),
            {'s': status, 'sum': json.dumps(summary, ensure_ascii=False), 'id': run_id},
        )
