"""Tests unitaires — mcp_server/tools/_helpers.py (fonctions pures, sans DB)"""
import json
import pytest

from mcp_server.tools._helpers import (
    ok,
    err,
    validate_period,
    sanitize_row,
    sanitize_rows,
    count_anomalies,
    build_period_filter,
    add_condition,
    PERIOD_MAP,
    THRESHOLDS,
)


# ── ok() / err() ──────────────────────────────────────────────────────────────

class TestOkErr:
    def test_ok_returns_success_status(self):
        result = json.loads(ok({"count": 5}))
        assert result["status"] == "success"
        assert result["count"] == 5

    def test_ok_ensure_ascii_false(self):
        raw = ok({"zone": "Salle réunion"})
        assert "réunion" in raw

    def test_err_contains_tool_and_message(self):
        raw = json.loads(err("get_sensors", "Table introuvable"))
        assert raw["status"] == "error"
        assert raw["tool"] == "get_sensors"
        assert raw["message"] == "Table introuvable"

    def test_err_includes_suggestion_when_given(self):
        raw = json.loads(err("get_data", "Période invalide", "Utilisez 24h"))
        assert raw["suggestion"] == "Utilisez 24h"

    def test_err_no_suggestion_key_when_empty(self):
        raw = json.loads(err("tool", "msg"))
        assert "suggestion" not in raw


# ── validate_period() ────────────────────────────────────────────────────────

class TestValidatePeriod:
    @pytest.mark.parametrize("period,expected_sql", [
        ("1h",   "INTERVAL 1 HOUR"),
        ("24h",  "INTERVAL 24 HOUR"),
        ("7j",   "INTERVAL 7 DAY"),
        ("30j",  "INTERVAL 30 DAY"),
        ("60j",  "INTERVAL 60 DAY"),
        ("90j",  "INTERVAL 90 DAY"),
        ("mois", "INTERVAL 30 DAY"),
        ("tout", None),
    ])
    def test_valid_period(self, period, expected_sql):
        interval, error = validate_period("tool", period)
        assert error is None
        assert interval == expected_sql

    def test_invalid_period_returns_error(self):
        interval, error = validate_period("tool", "semaine")
        assert interval is None
        assert error is not None
        parsed = json.loads(error)
        assert parsed["status"] == "error"

    def test_case_insensitive(self):
        interval, error = validate_period("tool", "24H")
        assert error is None
        assert interval == "INTERVAL 24 HOUR"

    def test_with_spaces(self):
        interval, error = validate_period("tool", "  7j  ")
        assert error is None


# ── sanitize_row() / sanitize_rows() ─────────────────────────────────────────

class TestSanitize:
    def test_removes_confidential_fields(self):
        row = {"id_device": "ABC123", "temperature": 22.5, "id": 1}
        result = sanitize_row(row)
        assert "id_device" not in result
        assert "id" not in result
        assert result["temperature"] == 22.5

    def test_removes_timestamp_fields(self):
        row = {"timestamp": "2025-01-01", "value": 10}
        assert "timestamp" not in sanitize_row(row)

    def test_keep_fields_overrides_blacklist(self):
        row = {"id_device": "SENSOR-1", "value": 5}
        result = sanitize_row(row, keep_fields={"id_device"})
        assert result["id_device"] == "SENSOR-1"

    def test_empty_row(self):
        assert sanitize_row({}) == {}

    def test_sanitize_rows_applies_to_all(self):
        rows = [
            {"id": 1, "temp": 20.0},
            {"id": 2, "temp": 21.0},
        ]
        result = sanitize_rows(rows)
        assert all("id" not in r for r in result)
        assert result[0]["temp"] == 20.0

    def test_case_sensitive_confidential_check(self):
        # La vérification est sur .lower() donc "ID_DEVICE" doit aussi être filtré
        row = {"ID_DEVICE": "X", "val": 9}
        result = sanitize_row(row)
        assert "ID_DEVICE" not in result


# ── count_anomalies() ────────────────────────────────────────────────────────

class TestCountAnomalies:
    def test_zero_rows(self):
        r = count_anomalies([])
        assert r["count"] == 0
        assert r["severity"] == "LOW"

    def test_low_severity(self):
        rows = [{}] * 2
        r = count_anomalies(rows)
        assert r["severity"] == "LOW"

    def test_medium_severity(self):
        rows = [{}] * 5
        r = count_anomalies(rows)
        assert r["severity"] == "MEDIUM"

    def test_high_severity(self):
        rows = [{}] * 11
        r = count_anomalies(rows)
        assert r["severity"] == "HIGH"

    def test_boundary_medium_at_4(self):
        assert count_anomalies([{}] * 4)["severity"] == "MEDIUM"

    def test_boundary_high_at_11(self):
        assert count_anomalies([{}] * 11)["severity"] == "HIGH"


# ── build_period_filter() / add_condition() ──────────────────────────────────

class TestSQLFragments:
    def test_build_period_filter_with_both(self):
        result = build_period_filter("created_at", "INTERVAL 24 HOUR")
        assert "WHERE" in result
        assert "`created_at`" in result
        assert "INTERVAL 24 HOUR" in result

    def test_build_period_filter_no_date_col(self):
        assert build_period_filter(None, "INTERVAL 24 HOUR") == ""

    def test_build_period_filter_no_interval(self):
        assert build_period_filter("created_at", None) == ""

    def test_add_condition_creates_where(self):
        result = add_condition("", "temperature > 35")
        assert result == "WHERE (temperature > 35)"

    def test_add_condition_appends_and(self):
        result = add_condition("WHERE zone = 'A'", "battery < 20")
        assert "AND" in result
        assert "battery < 20" in result

    def test_add_condition_existing_where_preserved(self):
        existing = "WHERE zone = 'B'"
        result = add_condition(existing, "value > 0")
        assert existing in result


# ── Cohérence des constantes ──────────────────────────────────────────────────

class TestConstants:
    def test_period_map_has_all_expected_keys(self):
        expected = {"1h", "24h", "48h", "7j", "30j", "60j", "90j", "mois", "tout"}
        assert expected == set(PERIOD_MAP.keys())

    def test_tout_maps_to_none(self):
        assert PERIOD_MAP["tout"] is None

    def test_thresholds_temperature_range(self):
        t = THRESHOLDS["temperature"]
        assert t["min"] < t["max"]
        assert t["unit"] == "°C"

    def test_thresholds_battery_range(self):
        b = THRESHOLDS["battery"]
        assert b["min"] == 20
        assert b["max"] == 100
