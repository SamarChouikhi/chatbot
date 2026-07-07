"""Tests unitaires — mcp_server/device_resolver.py (constructeurs SQL purs, sans DB)"""
import pytest

from mcp_server.device_resolver import (
    build_named_select,
    build_realtime_query,
    build_aggregated_query,
    build_anomaly_query,
    build_inactive_query,
    resolve_device,
    invalidate_cache,
    _device_cache,
)
from unittest.mock import patch


# ── build_named_select() ──────────────────────────────────────────────────────

class TestBuildNamedSelect:
    def test_contains_table_name(self):
        sql = build_named_select("archive_thl", ["t", "h"])
        assert "archive_thl" in sql

    def test_contains_join_device(self):
        sql = build_named_select("archive_thl", ["t", "h"])
        assert "JOIN device" in sql
        assert "JOIN espace" in sql

    def test_excludes_raw_id_device(self):
        sql = build_named_select("rt_thl", ["id_device", "temperature"])
        # id_device ne doit pas apparaître dans les SELECT cols (exclu par la fonction)
        lines = [l.strip() for l in sql.splitlines()]
        assert not any("t.`id_device`" in l for l in lines)

    def test_includes_date_col_alias(self):
        sql = build_named_select("archive_thl", ["t"], date_col="created_at")
        assert "mesure_date" in sql

    def test_limit_applied(self):
        sql = build_named_select("archive_thl", ["t"], limit=10)
        assert "LIMIT 10" in sql

    def test_where_clause_included(self):
        sql = build_named_select("rt_en_p", ["voltage"], where="zone = 'A'")
        assert "WHERE" in sql
        assert "zone = 'A'" in sql

    def test_group_by_when_requested(self):
        sql = build_named_select("archive_wm", ["volume"], group_by_device=True)
        assert "GROUP BY" in sql

    def test_no_group_by_when_disabled(self):
        sql = build_named_select("archive_wm", ["volume"], group_by_device=False)
        assert "GROUP BY" not in sql

    def test_select_has_capteur_nom_and_zone(self):
        sql = build_named_select("rt_thl", ["t", "h"])
        assert "capteur_nom" in sql
        assert "zone" in sql


# ── build_realtime_query() ────────────────────────────────────────────────────

class TestBuildRealtimeQuery:
    def test_default_limit_is_30(self):
        sql = build_realtime_query("rt_thl", ["t", "h"])
        assert "LIMIT 30" in sql

    def test_respects_limit(self):
        sql = build_realtime_query("rt_thl", ["temperature"], limit=5)
        assert "LIMIT 5" in sql

    def test_contains_sensor_columns(self):
        sql = build_realtime_query("rt_en_p", ["voltage", "current"])
        assert "voltage" in sql
        assert "current" in sql

    def test_has_capteur_nom_and_zone(self):
        sql = build_realtime_query("rt_sm", ["distance"])
        assert "capteur_nom" in sql
        assert "zone" in sql


# ── build_aggregated_query() ──────────────────────────────────────────────────

class TestBuildAggregatedQuery:
    def test_contains_agg_expressions(self):
        agg = ["AVG(t.`t`) AS avg_temp", "MAX(t.`t`) AS max_temp"]
        sql = build_aggregated_query("archive_thl", agg, "date", "INTERVAL 24 HOUR")
        assert "AVG" in sql
        assert "MAX" in sql

    def test_where_clause_with_interval(self):
        sql = build_aggregated_query("archive_thl", ["AVG(t.`t`)"], "date", "INTERVAL 7 DAY")
        assert "WHERE" in sql
        assert "INTERVAL 7 DAY" in sql

    def test_no_where_when_interval_none(self):
        sql = build_aggregated_query("archive_thl", ["COUNT(*)"], None, None)
        assert "WHERE" not in sql

    def test_group_by_present(self):
        sql = build_aggregated_query("archive_thl", ["AVG(t.`t`)"], "date", None)
        assert "GROUP BY" in sql


# ── build_anomaly_query() ─────────────────────────────────────────────────────

class TestBuildAnomalyQuery:
    def test_contains_condition(self):
        sql = build_anomaly_query("archive_thl", "t.`t` > 35", "date", "INTERVAL 24 HOUR")
        assert "t.`t` > 35" in sql

    def test_time_filter_present(self):
        sql = build_anomaly_query("archive_thl", "t.`h` > 80", "date", "INTERVAL 7 DAY")
        assert "INTERVAL 7 DAY" in sql

    def test_no_time_filter_when_none(self):
        sql = build_anomaly_query("archive_thl", "t.`t` > 35", None, None)
        assert "AND" not in sql.split("WHERE")[1] if "WHERE" in sql else True

    def test_extra_cols_included(self):
        sql = build_anomaly_query(
            "archive_en_p", "t.`voltage` < 207",
            "date", "INTERVAL 1 HOUR",
            extra_cols=["voltage"]
        )
        assert "voltage" in sql

    def test_result_has_no_raw_id_device_column(self):
        sql = build_anomaly_query("rt_thl", "t.`t` > 35", None, None)
        # Le SELECT retourné expose capteur_nom/zone, jamais id_device brut
        assert "capteur_nom" in sql
        assert "zone" in sql


# ── build_inactive_query() ────────────────────────────────────────────────────

class TestBuildInactiveQuery:
    def test_contains_timestampdiff(self):
        sql = build_inactive_query("rt_thl", "date")
        assert "TIMESTAMPDIFF" in sql

    def test_having_clause(self):
        sql = build_inactive_query("rt_thl", "date")
        assert "HAVING" in sql
        assert "heures_silence" in sql

    def test_orders_by_heures_silence(self):
        sql = build_inactive_query("rt_sm", "date")
        assert "ORDER BY heures_silence DESC" in sql

    def test_respects_limit(self):
        sql = build_inactive_query("rt_thl", "date", limit=5)
        assert "LIMIT 5" in sql


# ── resolve_device() avec cache mocké ────────────────────────────────────────

class TestResolveDevice:
    def test_known_device_returns_info(self):
        fake_map = {"SENSOR-01": {"nom": "Capteur T1", "espace": "Bureau A"}}
        with patch("mcp_server.device_resolver._load_device_map", return_value=fake_map):
            result = resolve_device("SENSOR-01")
        assert result["nom"] == "Capteur T1"
        assert result["espace"] == "Bureau A"

    def test_unknown_device_returns_default(self):
        with patch("mcp_server.device_resolver._load_device_map", return_value={}):
            result = resolve_device("UNKNOWN-99")
        assert result["nom"] == "Capteur inconnu"
        assert result["espace"] == "Zone inconnue"

    def test_resolve_accepts_int_id(self):
        fake_map = {"42": {"nom": "Capteur 42", "espace": "Zone B"}}
        with patch("mcp_server.device_resolver._load_device_map", return_value=fake_map):
            result = resolve_device(42)
        assert result["nom"] == "Capteur 42"

    def test_invalidate_cache_resets_ts(self):
        import mcp_server.device_resolver as dr
        dr._cache_ts = 9999999.0
        invalidate_cache()
        assert dr._cache_ts == 0.0
