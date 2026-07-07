import json
import time
from sqlalchemy import text

_MODULE_CACHE: dict[str, tuple[list | None, float]] = {}
_MODULE_CACHE_TTL = 60.0

_history_db = None


def set_history_db(db):
    global _history_db
    _history_db = db


def get_history_db():
    return _history_db


def get_engine():
    return _history_db.get_engine() if _history_db and _history_db.is_available() else None


REPORTS_DDL = '''CREATE TABLE IF NOT EXISTS aria_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    status ENUM("nominal","attention","critique") NOT NULL,
    summary TEXT NOT NULL,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration FLOAT NULL,
    period VARCHAR(20) DEFAULT "24h",
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

FEEDBACK_DDL = '''CREATE TABLE IF NOT EXISTS chat_feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message_id INT NOT NULL,
    thread_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100) NOT NULL DEFAULT 'default_user',
    vote ENUM('up','down') NOT NULL,
    comment TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_msg_user (message_id, user_id),
    INDEX idx_thread (thread_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

EMPLOYEES_DDL = '''CREATE TABLE IF NOT EXISTS aria_employees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    allowed_modules JSON NOT NULL,
    is_admin TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''


DAILY_ENERGY_DDL = '''CREATE TABLE IF NOT EXISTS daily_energy (
    id         BIGINT      AUTO_INCREMENT PRIMARY KEY,
    device_id  VARCHAR(50) NOT NULL,
    phase      CHAR(2)     NOT NULL,
    date       DATE        NOT NULL,
    hour       TINYINT     NOT NULL,
    cons_en    FLOAT       NULL,
    nb_mesures INT         NOT NULL DEFAULT 0,
    UNIQUE KEY uq_energy (device_id, phase, date, hour),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

DAILY_WATER_DDL = '''CREATE TABLE IF NOT EXISTS daily_water (
    id         BIGINT      AUTO_INCREMENT PRIMARY KEY,
    device_id  VARCHAR(50) NOT NULL,
    date       DATE        NOT NULL,
    hour       TINYINT     NOT NULL,
    conso_m3   FLOAT       NULL,
    nb_fuites  INT         NOT NULL DEFAULT 0,
    nb_fraudes INT         NOT NULL DEFAULT 0,
    is_offline TINYINT(1)  NOT NULL DEFAULT 0,
    nb_mesures INT         NOT NULL DEFAULT 0,
    UNIQUE KEY uq_water (device_id, date, hour),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

DAILY_FUEL_DDL = '''CREATE TABLE IF NOT EXISTS daily_fuel (
    id          BIGINT      AUTO_INCREMENT PRIMARY KEY,
    device_id   VARCHAR(50) NOT NULL,
    date        DATE        NOT NULL,
    hour        TINYINT     NOT NULL,
    fuel_level  FLOAT       NULL,
    consumption FLOAT       NULL,
    avg_speed   FLOAT       NULL,
    nb_mesures  INT         NOT NULL DEFAULT 0,
    UNIQUE KEY uq_fuel (device_id, date, hour),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

DAILY_GAS_DDL = '''CREATE TABLE IF NOT EXISTS daily_gas (
    id         BIGINT      AUTO_INCREMENT PRIMARY KEY,
    device_id  VARCHAR(50) NOT NULL,
    date       DATE        NOT NULL,
    hour       TINYINT     NOT NULL,
    conso_m3   FLOAT       NULL,
    avg_debit  FLOAT       NULL,
    nb_fuites  INT         NOT NULL DEFAULT 0,
    nb_fraudes INT         NOT NULL DEFAULT 0,
    nb_mesures INT         NOT NULL DEFAULT 0,
    UNIQUE KEY uq_gas (device_id, date, hour),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

AD_RESULTS_DDL = '''CREATE TABLE IF NOT EXISTS ad_results (
    id            BIGINT      AUTO_INCREMENT PRIMARY KEY,
    run_at        DATETIME    NOT NULL,
    domain        VARCHAR(20) NOT NULL,
    item_id       VARCHAR(50) NOT NULL,
    strategy      VARCHAR(10) NOT NULL,
    is_anomaly    TINYINT(1)  NOT NULL,
    anomaly_score FLOAT       NULL,
    data_ts       DATETIME    NOT NULL,
    value         FLOAT       NULL,
    q10           FLOAT       NULL,
    q90           FLOAT       NULL,
    INDEX idx_run_domain (run_at, domain),
    INDEX idx_item_ts    (item_id, data_ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

PIPELINE_RUNS_DDL = '''CREATE TABLE IF NOT EXISTS pipeline_runs (
    id         INT         AUTO_INCREMENT PRIMARY KEY,
    started_at DATETIME    NOT NULL,
    ended_at   DATETIME    NULL,
    status     ENUM("running","success","partial","failed") NOT NULL DEFAULT "running",
    summary    JSON        NULL,
    INDEX idx_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

PREDICTIONS_DDL = '''CREATE TABLE IF NOT EXISTS aria_predictions (
    id              BIGINT      AUTO_INCREMENT PRIMARY KEY,
    run_at          DATETIME    NOT NULL,
    domain          VARCHAR(20) NOT NULL,
    item_id         VARCHAR(50) NOT NULL,
    forecast_ts     DATETIME    NOT NULL,
    horizon_hours   SMALLINT    NOT NULL,
    forecast_col    VARCHAR(50) NOT NULL DEFAULT "",
    forecast_median FLOAT       NULL,
    forecast_low    FLOAT       NULL,
    forecast_high   FLOAT       NULL,
    confidence      FLOAT       NULL,
    is_alert        TINYINT(1)  NOT NULL DEFAULT 0,
    alert_severity  VARCHAR(10) NULL,
    UNIQUE KEY uq_pred (run_at, domain, item_id, forecast_ts),
    INDEX idx_domain_ts (domain, forecast_ts),
    INDEX idx_alert     (is_alert, forecast_ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

PREDICTIONS_UNIQUE_MIGRATION = '''
    ALTER TABLE aria_predictions
    ADD CONSTRAINT uq_pred UNIQUE (run_at, domain, item_id, forecast_ts)
'''


BASELINES_DDL = '''CREATE TABLE IF NOT EXISTS device_baselines (
    id           INT          AUTO_INCREMENT PRIMARY KEY,
    device_id    VARCHAR(50)  NOT NULL,
    domain       VARCHAR(20)  NOT NULL,
    hour_of_week SMALLINT     NOT NULL,
    p10          FLOAT        NULL,
    p50          FLOAT        NULL,
    p90          FLOAT        NULL,
    sample_count INT          NOT NULL DEFAULT 0,
    computed_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_baseline (device_id, domain, hour_of_week),
    INDEX idx_domain (domain, device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

RECOMMENDATIONS_DDL = '''CREATE TABLE IF NOT EXISTS aria_recommendations (
    id                   INT          AUTO_INCREMENT PRIMARY KEY,
    domain               VARCHAR(20)  NOT NULL,
    device_id            VARCHAR(50)  NULL,
    rec_type             VARCHAR(30)  NOT NULL,
    target_role          VARCHAR(20)  NOT NULL DEFAULT "gestionnaire",
    priority             VARCHAR(10)  NOT NULL,
    title                VARCHAR(255) NOT NULL,
    description          TEXT         NOT NULL,
    action               TEXT         NOT NULL,
    reasoning            TEXT         NULL,
    i18n                 JSON         NULL,
    estimated_saving_tnd FLOAT        NULL,
    deviation_pct        FLOAT        NULL,
    status               ENUM("pending","accepted","dismissed","done") NOT NULL DEFAULT "pending",
    generated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at           DATETIME     NOT NULL,
    acted_at             DATETIME     NULL,
    measured_saving_tnd  FLOAT        NULL,
    INDEX idx_domain_status (domain, status, expires_at),
    INDEX idx_device        (device_id, domain),
    INDEX idx_role          (target_role, domain, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

RECOMMENDATIONS_REASONING_MIGRATION = '''
    ALTER TABLE aria_recommendations ADD COLUMN reasoning TEXT NULL AFTER action
'''

RECOMMENDATIONS_ROLE_MIGRATION = '''
    ALTER TABLE aria_recommendations
    ADD COLUMN target_role VARCHAR(20) NOT NULL DEFAULT "gestionnaire" AFTER rec_type
'''

RECOMMENDATIONS_I18N_MIGRATION = '''
    ALTER TABLE aria_recommendations ADD COLUMN i18n JSON NULL AFTER reasoning
'''

PROACTIVE_DDL = '''CREATE TABLE IF NOT EXISTS aria_proactive_messages (
    id                BIGINT      AUTO_INCREMENT PRIMARY KEY,
    user_id           VARCHAR(100) NOT NULL,
    domain            VARCHAR(20)  NOT NULL,
    severity          VARCHAR(10)  NOT NULL,
    message           TEXT         NOT NULL,
    source_type       VARCHAR(20)  NOT NULL,
    source_ref        VARCHAR(150) NULL,
    quick_reply_label VARCHAR(80)  NOT NULL DEFAULT "Analyser",
    quick_reply_value TEXT         NULL,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at           DATETIME     NULL,
    dismissed         TINYINT(1)   NOT NULL DEFAULT 0,
    INDEX idx_user_pending (user_id, dismissed, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''


USER_PREFERENCES_DDL = '''CREATE TABLE IF NOT EXISTS user_reco_preferences (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    user_id       VARCHAR(128) NOT NULL,
    rec_type      VARCHAR(30)  NOT NULL,
    domain        VARCHAR(20)  NOT NULL,
    accept_count  INT          NOT NULL DEFAULT 0,
    dismiss_count INT          NOT NULL DEFAULT 0,
    last_updated  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_type_domain (user_id, rec_type, domain),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''

RAG_DDL = '''CREATE TABLE IF NOT EXISTS rag_documents (
    id          INT          AUTO_INCREMENT PRIMARY KEY,
    doc_id      VARCHAR(100) NOT NULL UNIQUE,
    category    VARCHAR(50)  NOT NULL,
    domain      VARCHAR(20)  NULL,
    device_id   VARCHAR(50)  NULL,
    title       VARCHAR(255) NOT NULL,
    content     TEXT         NOT NULL,
    keywords    VARCHAR(500) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FULLTEXT  idx_ft      (title, content, keywords),
    INDEX     idx_device  (device_id),
    INDEX     idx_category(category),
    INDEX     idx_domain  (domain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''


def ensure_tables(engine):
    with engine.connect() as conn:
        conn.execute(text(REPORTS_DDL))
        conn.execute(text(FEEDBACK_DDL))
        conn.execute(text(EMPLOYEES_DDL))
        conn.execute(text(PROACTIVE_DDL))
        conn.execute(text(BASELINES_DDL))
        conn.execute(text(RECOMMENDATIONS_DDL))
        # Migration idempotente : ajoute reasoning si absent (tables créées avant ce champ)
        try:
            conn.execute(text(RECOMMENDATIONS_REASONING_MIGRATION))
        except Exception:
            pass
        # Migration idempotente : ajoute target_role si absent
        try:
            conn.execute(text(RECOMMENDATIONS_ROLE_MIGRATION))
        except Exception:
            pass
        # Migration idempotente : ajoute i18n (traductions en/ar) si absent
        try:
            conn.execute(text(RECOMMENDATIONS_I18N_MIGRATION))
        except Exception:
            pass
        conn.execute(text(USER_PREFERENCES_DDL))
        conn.execute(text(RAG_DDL))
        conn.commit()


def ensure_analytics_tables(engine):
    with engine.connect() as conn:
        conn.execute(text(DAILY_ENERGY_DDL))
        conn.execute(text(DAILY_WATER_DDL))
        conn.execute(text(DAILY_FUEL_DDL))
        conn.execute(text(DAILY_GAS_DDL))
        conn.execute(text(AD_RESULTS_DDL))
        conn.execute(text(PIPELINE_RUNS_DDL))
        conn.execute(text(PREDICTIONS_DDL))
        # Migration idempotente : ajoute la UNIQUE KEY si absente (tables créées avant ce fix)
        try:
            conn.execute(text(PREDICTIONS_UNIQUE_MIGRATION))
        except Exception:
            pass  # contrainte déjà présente
        conn.commit()


def get_employee_modules(user_id: str) -> list | None:
    """Retourne les modules autorisés d'un employé, ou None si admin/inconnu (= accès total).

    Résultat mis en cache 60 s par user_id pour éviter une requête DB à chaque message.
    """
    now = time.time()
    cached = _MODULE_CACHE.get(user_id)
    if cached and (now - cached[1]) < _MODULE_CACHE_TTL:
        return cached[0]

    engine = get_engine()
    if engine is None:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text('SELECT allowed_modules, is_admin FROM aria_employees WHERE user_id = :uid'),
            {'uid': user_id}
        ).fetchone()

    if row is None:
        modules = None  # utilisateur inconnu → accès total
    elif row.is_admin:
        modules = None  # admin → accès total
    else:
        modules = row.allowed_modules
        if isinstance(modules, str):
            try:
                modules = json.loads(modules)
            except (json.JSONDecodeError, TypeError):
                modules = None

    _MODULE_CACHE[user_id] = (modules, now)
    return modules


# ── Préférences utilisateur ──────────────────────────────────────────────────

def get_user_preferences(engine, user_id: str) -> dict:
    """Retourne {(rec_type, domain): {'accept': int, 'dismiss': int, 'score': float}}.

    score = accept / (accept + dismiss + 1)  — entre 0 (jamais aimé) et ~1 (toujours aimé).
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT rec_type, domain, accept_count, dismiss_count '
                 'FROM user_reco_preferences WHERE user_id = :uid'),
            {'uid': user_id},
        ).fetchall()
    return {
        (r[0], r[1]): {
            'accept' : r[2],
            'dismiss': r[3],
            'score'  : r[2] / (r[2] + r[3] + 1),
        }
        for r in rows
    }


def upsert_user_preference(engine, user_id: str, rec_type: str,
                           domain: str, action: str) -> None:
    """Incrémente le compteur accept ou dismiss pour ce (user, rec_type, domain).

    action : 'accepted' | 'dismissed'
    """
    col = 'accept_count' if action == 'accepted' else 'dismiss_count'
    with engine.begin() as conn:
        conn.execute(text(f'''
            INSERT INTO user_reco_preferences (user_id, rec_type, domain, {col})
            VALUES (:uid, :rt, :dom, 1)
            ON DUPLICATE KEY UPDATE {col} = {col} + 1
        '''), {'uid': user_id, 'rt': rec_type, 'dom': domain})
