"""Tests unitaires — mcp_server/db/connection.py :: _assert_safe_table

Vérifie que la validation anti-injection SQL rejette les noms de table malveillants
et accepte les noms légitimes. Aucun accès DB requis.
"""
import pytest
from mcp_server.db.connection import _assert_safe_table


# ── Noms valides — doivent être acceptés ──────────────────────────────────────

class TestAssertSafeTableValid:
    @pytest.mark.parametrize("name", [
        "aria_devices",
        "daily_energy",
        "daily_water",
        "daily_gaz",
        "daily_fuel",
        "aria_anomalies",
        "aria_alerts",
        "aria_employees",
        "pipeline_runs",
        "chat_feedback",
        "aria_proactive_messages",
        "tbl123",
        "A",                        # 1 caractère
        "a" * 64,                   # 64 caractères — limite MySQL
        "table-with-dash",          # tiret autorisé
        "TABLE_UPPER",              # majuscules autorisées
    ])
    def test_valid_name_returned_unchanged(self, name):
        assert _assert_safe_table(name) == name


# ── Noms invalides — doivent lever ValueError ─────────────────────────────────

class TestAssertSafeTableInvalid:
    @pytest.mark.parametrize("name", [
        "aria_devices; DROP TABLE users--",   # injection classique
        "users' OR '1'='1",                  # injection SQL quote
        "table name",                         # espace
        "../etc/passwd",                      # path traversal
        "table`injection",                    # backtick
        "; DELETE FROM aria_devices; --",     # injection multi-statement
        "a" * 65,                             # 65 chars — dépasse limite
        "",                                   # vide
        "table\x00name",                      # null byte
        "table\nname",                        # newline
        "SELECT * FROM users",               # SQL keyword
    ])
    def test_invalid_name_raises_value_error(self, name):
        with pytest.raises(ValueError, match="invalide"):
            _assert_safe_table(name)

    def test_error_message_contains_table_name(self):
        bad = "evil; DROP"
        with pytest.raises(ValueError) as exc_info:
            _assert_safe_table(bad)
        assert "evil" in str(exc_info.value) or "invalide" in str(exc_info.value)

    def test_dot_separator_rejected(self):
        # "schema.table" n'est pas autorisé — le point est dangereux en SQL
        with pytest.raises(ValueError):
            _assert_safe_table("schema.table")

    def test_unicode_rejected(self):
        with pytest.raises(ValueError):
            _assert_safe_table("café_table")

    def test_wildcard_rejected(self):
        with pytest.raises(ValueError):
            _assert_safe_table("*")

    def test_parenthesis_rejected(self):
        with pytest.raises(ValueError):
            _assert_safe_table("func()")

    def test_hash_rejected(self):
        with pytest.raises(ValueError):
            _assert_safe_table("table#comment")
