import json
import time
import logging
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger('aria.history')


class MySQLHistoryManager:

    def __init__(self):
        self._memory_fallback: List[Dict] = []
        self._db_available = False
        self._init_connection()

    def _init_connection(self):
        try:
            from mcp_server.config import DB_URL
            self.engine  = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600)
            self.Session = sessionmaker(bind=self.engine)
            self._ensure_tables()
            self._db_available = True
            logger.info('MySQLHistoryManager : connecté')
        except Exception as e:
            logger.warning(f'MySQLHistoryManager : fallback mémoire ({str(e)[:60]})')
            self._db_available = False

    def _ensure_tables(self):
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    thread_id     VARCHAR(100) NOT NULL UNIQUE,
                    user_id       VARCHAR(100) NOT NULL DEFAULT 'default_user',
                    title         VARCHAR(255) NOT NULL DEFAULT 'Nouvelle conversation',
                    message_count INT NOT NULL DEFAULT 0,
                    is_favorite   TINYINT(1) NOT NULL DEFAULT 0,
                    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_updated (updated_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()

            # Migrations idempotentes
            try:
                conn.execute(text(
                    'ALTER TABLE chat_threads ADD COLUMN is_favorite TINYINT(1) NOT NULL DEFAULT 0'
                ))
                conn.commit()
            except Exception as _e:
                _msg = str(_e)
                # 1060 = Duplicate column name (MySQL) — attendu si colonne déjà présente
                if '1060' not in _msg and 'Duplicate column' not in _msg:
                    logger.warning('Migration is_favorite échouée (non-critique) : %s', _msg[:120])

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    thread_id    VARCHAR(100) NOT NULL,
                    role         ENUM('user','assistant') NOT NULL,
                    content      TEXT NOT NULL,
                    content_norm TEXT NULL,
                    level        VARCHAR(20) NULL,
                    backend      VARCHAR(100) NULL,
                    duration     FLOAT NULL,
                    chart_data   JSON NULL,
                    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_thread (thread_id),
                    INDEX idx_created (created_at),
                    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()

            # Migration chart_data pour les tables existantes
            try:
                conn.execute(text('ALTER TABLE chat_messages ADD COLUMN chart_data JSON NULL'))
                conn.commit()
            except Exception as _e2:
                _msg2 = str(_e2)
                if '1060' not in _msg2 and 'Duplicate column' not in _msg2:
                    logger.warning('Migration chart_data échouée (non-critique) : %s', _msg2[:120])

    def save_message(
        self, thread_id: str, role: str, content: str,
        content_normalized: str = None, level: str = None,
        backend: str = None, duration: float = None,
        user_id: str = 'default_user', chart_data: list = None,
    ) -> int:
        msg_id = int(time.time() * 1000)

        if not self._db_available:
            self._memory_fallback.append({
                'id': msg_id, 'thread_id': thread_id, 'role': role,
                'content': content, 'level': level, 'backend': backend,
                'duration': duration, 'created_at': time.time(),
            })
            return msg_id

        try:
            with self.engine.connect() as conn:
                if not conn.execute(
                    text('SELECT id FROM chat_threads WHERE thread_id = :tid'),
                    {'tid': thread_id}
                ).fetchone():
                    title = (content[:50] + '...') if len(content) > 50 else content
                    conn.execute(
                        text('INSERT INTO chat_threads (thread_id, user_id, title) '
                             'VALUES (:tid, :uid, :ttl)'),
                        {'tid': thread_id, 'uid': user_id, 'ttl': title}
                    )

                result = conn.execute(
                    text('INSERT INTO chat_messages '
                         '(thread_id, role, content, content_norm, level, backend, duration, chart_data) '
                         'VALUES (:tid, :role, :content, :cnorm, :level, :backend, :dur, :chart_data)'),
                    {
                        'tid': thread_id, 'role': role, 'content': content,
                        'cnorm': content_normalized, 'level': level,
                        'backend': backend, 'dur': duration,
                        'chart_data': json.dumps(chart_data) if chart_data else None,
                    }
                )
                msg_id = result.lastrowid
                conn.execute(
                    text('UPDATE chat_threads '
                         'SET message_count = message_count + 1, updated_at = NOW() '
                         'WHERE thread_id = :tid'),
                    {'tid': thread_id}
                )
                conn.commit()
                return msg_id

        except Exception as e:
            logger.error(f'Save message error: {e}')
            return msg_id

    def update_message_charts(self, msg_id: int, chart_data: list) -> None:
        """Met à jour chart_data d'un message déjà sauvegardé (appelé après asyncio.gather)."""
        if not self._db_available or not msg_id or not chart_data:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text('UPDATE chat_messages SET chart_data = :cd WHERE id = :id'),
                    {'cd': json.dumps(chart_data), 'id': msg_id}
                )
        except Exception as e:
            logger.warning('update_message_charts error: %s', e)

    def get_user_threads(self, user_id='default_user', limit=20) -> List[Dict]:
        if not self._db_available:
            return []
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text('''SELECT t.*,
                            (SELECT content FROM chat_messages
                             WHERE thread_id = t.thread_id
                             ORDER BY created_at DESC LIMIT 1) AS preview
                            FROM chat_threads t
                            WHERE t.user_id = :uid
                            ORDER BY t.is_favorite DESC, t.updated_at DESC
                            LIMIT :lim'''),
                    {'uid': user_id, 'lim': limit}
                ).fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error(f'Get threads error: {e}')
            return []

    def get_thread_by_id(self, thread_id) -> Optional[Dict]:
        if not self._db_available:
            return None
        try:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text('SELECT * FROM chat_threads WHERE thread_id = :tid'),
                    {'tid': thread_id}
                ).fetchone()
                return dict(row._mapping) if row else None
        except Exception:
            return None

    def get_conversation_history(self, thread_id, limit=50) -> List[Dict]:
        if not self._db_available:
            return [m for m in self._memory_fallback if m['thread_id'] == thread_id][-limit:]
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text('SELECT * FROM chat_messages '
                         'WHERE thread_id = :tid ORDER BY created_at ASC LIMIT :lim'),
                    {'tid': thread_id, 'lim': limit}
                ).fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error(f'Get history error: {e}')
            return []

    def delete_thread(self, thread_id) -> bool:
        if not self._db_available:
            return False
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text('DELETE FROM chat_threads WHERE thread_id = :tid'),
                    {'tid': thread_id}
                )
                conn.commit()
                return result.rowcount > 0
        except Exception:
            return False

    def update_thread_title(self, thread_id, title):
        if not self._db_available:
            return
        try:
            with self.engine.connect() as conn:
                conn.execute(
                    text('UPDATE chat_threads SET title = :ttl WHERE thread_id = :tid'),
                    {'ttl': title, 'tid': thread_id}
                )
                conn.commit()
        except Exception:
            pass

    def toggle_favorite(self, thread_id: str) -> bool:
        if not self._db_available:
            return False
        try:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text('SELECT is_favorite FROM chat_threads WHERE thread_id = :tid'),
                    {'tid': thread_id}
                ).fetchone()
                if not row:
                    return False
                new_val = 0 if row.is_favorite else 1
                conn.execute(
                    text('UPDATE chat_threads SET is_favorite = :val WHERE thread_id = :tid'),
                    {'val': new_val, 'tid': thread_id}
                )
                conn.commit()
                return bool(new_val)
        except Exception as e:
            logger.error(f'Toggle favorite error: {e}')
            return False

    def search_threads(self, user_id, query, limit=10) -> List[Dict]:
        if not self._db_available:
            return []
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text('''SELECT DISTINCT t.*
                            FROM chat_threads t
                            LEFT JOIN chat_messages m ON t.thread_id = m.thread_id
                            WHERE t.user_id = :uid
                              AND (t.title LIKE :q OR m.content LIKE :q)
                            ORDER BY t.updated_at DESC
                            LIMIT :lim'''),
                    {'uid': user_id, 'q': f'%{query}%', 'lim': limit}
                ).fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception:
            return []

    def is_available(self) -> bool:
        return self._db_available

    def get_engine(self):
        return self.engine if self._db_available else None
