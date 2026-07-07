"""Tests unitaires — mcp_client/history.py (mode fallback mémoire sans DB)"""
import pytest
from mcp_client.history import MySQLHistoryManager


def _make_fallback_manager() -> MySQLHistoryManager:
    """Crée un MySQLHistoryManager en mode fallback mémoire (sans DB réelle)."""
    mgr = MySQLHistoryManager.__new__(MySQLHistoryManager)
    mgr._memory_fallback = []
    mgr._db_available = False
    mgr.engine = None
    mgr.Session = None
    return mgr


# ── is_available() / get_engine() ─────────────────────────────────────────────

class TestAvailability:
    def test_unavailable_when_db_down(self):
        mgr = _make_fallback_manager()
        assert mgr.is_available() is False

    def test_get_engine_returns_none_when_unavailable(self):
        mgr = _make_fallback_manager()
        assert mgr.get_engine() is None


# ── save_message() — fallback mémoire ─────────────────────────────────────────

class TestSaveMessageFallback:
    def test_returns_integer_id(self):
        mgr = _make_fallback_manager()
        msg_id = mgr.save_message('thread-1', 'user', 'Bonjour ARIA')
        assert isinstance(msg_id, int)

    def test_message_stored_in_memory(self):
        mgr = _make_fallback_manager()
        mgr.save_message('thread-1', 'user', 'Test message')
        assert len(mgr._memory_fallback) == 1

    def test_correct_thread_id_stored(self):
        mgr = _make_fallback_manager()
        mgr.save_message('t-42', 'user', 'Hello')
        assert mgr._memory_fallback[0]['thread_id'] == 't-42'

    def test_correct_role_stored(self):
        mgr = _make_fallback_manager()
        mgr.save_message('t1', 'assistant', 'Réponse')
        assert mgr._memory_fallback[0]['role'] == 'assistant'

    def test_correct_content_stored(self):
        mgr = _make_fallback_manager()
        mgr.save_message('t1', 'user', 'Contenu exact')
        assert mgr._memory_fallback[0]['content'] == 'Contenu exact'

    def test_multiple_messages_accumulate(self):
        mgr = _make_fallback_manager()
        mgr.save_message('t1', 'user', 'msg1')
        mgr.save_message('t1', 'assistant', 'msg2')
        mgr.save_message('t1', 'user', 'msg3')
        assert len(mgr._memory_fallback) == 3

    def test_id_is_positive_integer(self):
        mgr = _make_fallback_manager()
        msg_id = mgr.save_message('t1', 'user', 'msg')
        assert isinstance(msg_id, int)
        assert msg_id > 0

    def test_different_threads_stored_together(self):
        mgr = _make_fallback_manager()
        mgr.save_message('thread-A', 'user', 'msg A')
        mgr.save_message('thread-B', 'user', 'msg B')
        assert len(mgr._memory_fallback) == 2


# ── get_user_threads() — fallback mémoire ─────────────────────────────────────

class TestGetUserThreadsFallback:
    def test_returns_empty_list(self):
        mgr = _make_fallback_manager()
        mgr.save_message('t1', 'user', 'message')
        result = mgr.get_user_threads('user1')
        assert result == []


# ── get_thread_by_id() — fallback mémoire ─────────────────────────────────────

class TestGetThreadByIdFallback:
    def test_returns_none_when_unavailable(self):
        mgr = _make_fallback_manager()
        assert mgr.get_thread_by_id('any-id') is None


# ── get_conversation_history() — fallback mémoire ────────────────────────────

class TestGetConversationHistoryFallback:
    def test_returns_messages_for_thread(self):
        mgr = _make_fallback_manager()
        mgr.save_message('thread-X', 'user', 'q1')
        mgr.save_message('thread-X', 'assistant', 'a1')
        mgr.save_message('thread-Y', 'user', 'autre')
        result = mgr.get_conversation_history('thread-X')
        assert len(result) == 2

    def test_only_matching_thread_returned(self):
        mgr = _make_fallback_manager()
        mgr.save_message('t1', 'user', 'msg1')
        mgr.save_message('t2', 'user', 'msg2')
        result = mgr.get_conversation_history('t1')
        assert all(m['thread_id'] == 't1' for m in result)

    def test_empty_thread_returns_empty(self):
        mgr = _make_fallback_manager()
        assert mgr.get_conversation_history('nonexistent') == []

    def test_limit_applied(self):
        mgr = _make_fallback_manager()
        for i in range(10):
            mgr.save_message('t1', 'user', f'msg{i}')
        result = mgr.get_conversation_history('t1', limit=3)
        assert len(result) == 3

    def test_limit_returns_last_messages(self):
        mgr = _make_fallback_manager()
        for i in range(5):
            mgr.save_message('t1', 'user', f'msg{i}')
        result = mgr.get_conversation_history('t1', limit=2)
        assert result[-1]['content'] == 'msg4'


# ── delete_thread() — fallback mémoire ───────────────────────────────────────

class TestDeleteThreadFallback:
    def test_returns_false_when_unavailable(self):
        mgr = _make_fallback_manager()
        assert mgr.delete_thread('any-thread') is False


# ── toggle_favorite() — fallback mémoire ─────────────────────────────────────

class TestToggleFavoriteFallback:
    def test_returns_false_when_unavailable(self):
        mgr = _make_fallback_manager()
        assert mgr.toggle_favorite('any-thread') is False


# ── search_threads() — fallback mémoire ──────────────────────────────────────

class TestSearchThreadsFallback:
    def test_returns_empty_when_unavailable(self):
        mgr = _make_fallback_manager()
        assert mgr.search_threads('user1', 'query') == []


# ── update_message_charts() — fallback mémoire ───────────────────────────────

class TestUpdateMessageChartsFallback:
    def test_noop_when_unavailable(self):
        mgr = _make_fallback_manager()
        mgr.update_message_charts(12345, [{'type': 'bar'}])
        assert mgr._memory_fallback == []

    def test_noop_with_none_msg_id(self):
        mgr = _make_fallback_manager()
        mgr._db_available = True
        mgr.engine = None
        mgr.update_message_charts(None, [{'type': 'bar'}])


# ── update_thread_title() — fallback mémoire ─────────────────────────────────

class TestUpdateThreadTitleFallback:
    def test_noop_when_unavailable(self):
        mgr = _make_fallback_manager()
        mgr.update_thread_title('t1', 'New Title')
        assert mgr._memory_fallback == []
