"""Tests unitaires — api/pipeline/extractor.py (fonctions pures)"""
import pytest
from api.pipeline.extractor import _safe_ident


# ── _safe_ident() ─────────────────────────────────────────────────────────────

class TestSafeIdent:
    def test_valid_simple_name(self):
        assert _safe_ident('archive_thl', 'table') == 'archive_thl'

    def test_valid_alphanumeric(self):
        assert _safe_ident('rt_en_p2', 'col') == 'rt_en_p2'

    def test_valid_uppercase(self):
        assert _safe_ident('UPPER_CASE', 'col') == 'UPPER_CASE'

    def test_valid_single_word(self):
        assert _safe_ident('temperature', 'col') == 'temperature'

    def test_space_raises_value_error(self):
        with pytest.raises(ValueError, match='table'):
            _safe_ident('bad name', 'table')

    def test_hyphen_raises_value_error(self):
        with pytest.raises(ValueError):
            _safe_ident('table-name', 'col')

    def test_dot_raises_value_error(self):
        with pytest.raises(ValueError):
            _safe_ident('schema.table', 'col')

    def test_semicolon_raises_value_error(self):
        with pytest.raises(ValueError):
            _safe_ident('t; DROP TABLE t', 'col')

    def test_quote_raises_value_error(self):
        with pytest.raises(ValueError):
            _safe_ident("t' OR 1=1", 'col')

    def test_parenthesis_raises_value_error(self):
        with pytest.raises(ValueError):
            _safe_ident('sleep(5)', 'col')

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            _safe_ident('', 'table')

    def test_error_message_contains_label(self):
        with pytest.raises(ValueError, match='colonne'):
            _safe_ident('bad col!', 'colonne')
