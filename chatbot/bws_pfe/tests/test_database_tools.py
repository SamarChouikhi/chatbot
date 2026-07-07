"""Tests unitaires — mcp_server/tools/database.py (fonctions pures)"""
import pytest
from mcp_server.tools.database import _is_safe_sql, _force_limit, MAX_ROWS


# ── _is_safe_sql() ────────────────────────────────────────────────────────────

class TestIsSafeSql:
    def test_valid_select(self):
        ok, reason = _is_safe_sql('SELECT * FROM archive_thl')
        assert ok is True
        assert reason == ''

    def test_lowercase_select_accepted(self):
        ok, _ = _is_safe_sql('select id from users limit 10')
        assert ok is True

    def test_non_select_rejected(self):
        ok, reason = _is_safe_sql('UPDATE t SET x=1')
        assert ok is False
        assert 'SELECT' in reason

    def test_insert_rejected(self):
        ok, _ = _is_safe_sql('INSERT INTO t VALUES (1)')
        assert ok is False

    def test_drop_keyword_rejected(self):
        ok, _ = _is_safe_sql('SELECT * FROM t; DROP TABLE t')
        assert ok is False

    def test_delete_statement_rejected(self):
        ok, _ = _is_safe_sql('DELETE FROM t WHERE id=1')
        assert ok is False

    def test_truncate_rejected(self):
        ok, _ = _is_safe_sql('SELECT 1; truncate table t')
        assert ok is False

    def test_union_exfiltration_rejected(self):
        ok, _ = _is_safe_sql('SELECT * FROM t UNION SELECT * FROM passwords')
        assert ok is False

    def test_sleep_injection_rejected(self):
        ok, _ = _is_safe_sql('SELECT * FROM t WHERE sleep(5)=0')
        assert ok is False

    def test_load_file_rejected(self):
        ok, _ = _is_safe_sql("SELECT load_file('/etc/passwd')")
        assert ok is False

    def test_into_outfile_rejected(self):
        ok, _ = _is_safe_sql("SELECT * FROM t INTO OUTFILE '/tmp/x'")
        assert ok is False

    def test_double_dash_comment_rejected(self):
        ok, _ = _is_safe_sql("SELECT * FROM t -- comment")
        assert ok is False

    def test_exec_rejected(self):
        ok, _ = _is_safe_sql('SELECT exec()')
        assert ok is False

    def test_empty_query_rejected(self):
        ok, _ = _is_safe_sql('')
        assert ok is False

    def test_reason_mentions_forbidden_keyword(self):
        _, reason = _is_safe_sql('SELECT * FROM t UNION SELECT 1')
        assert 'union' in reason.lower()


# ── _force_limit() ────────────────────────────────────────────────────────────

class TestForceLimit:
    def test_no_limit_adds_max_limit(self):
        q = 'SELECT * FROM t'
        result = _force_limit(q)
        assert f'LIMIT {MAX_ROWS}' in result

    def test_small_limit_preserved(self):
        q = 'SELECT * FROM t LIMIT 10'
        result = _force_limit(q)
        assert 'LIMIT 10' in result
        assert f'LIMIT {MAX_ROWS}' not in result

    def test_large_limit_replaced_with_max(self):
        q = f'SELECT * FROM t LIMIT {MAX_ROWS + 1}'
        result = _force_limit(q)
        assert f'LIMIT {MAX_ROWS}' in result
        assert f'LIMIT {MAX_ROWS + 1}' not in result

    def test_exact_max_limit_preserved(self):
        q = f'SELECT * FROM t LIMIT {MAX_ROWS}'
        result = _force_limit(q)
        assert f'LIMIT {MAX_ROWS}' in result

    def test_trailing_semicolon_stripped(self):
        q = 'SELECT * FROM t;'
        result = _force_limit(q)
        assert not result.rstrip().endswith(';')

    def test_very_large_limit_replaced(self):
        q = 'SELECT * FROM t LIMIT 100000'
        result = _force_limit(q)
        assert 'LIMIT 100000' not in result
        assert f'LIMIT {MAX_ROWS}' in result

    def test_limit_1_preserved(self):
        q = 'SELECT * FROM t LIMIT 1'
        result = _force_limit(q)
        assert 'LIMIT 1' in result

    def test_original_query_columns_preserved(self):
        q = 'SELECT id, name, value FROM sensors'
        result = _force_limit(q)
        assert 'SELECT id, name, value' in result

    @pytest.mark.parametrize('n', [1, 50, 100, 200])
    def test_limit_at_or_below_max_preserved(self, n):
        q = f'SELECT * FROM t LIMIT {n}'
        result = _force_limit(q)
        assert f'LIMIT {n}' in result
