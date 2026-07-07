"""Tests unitaires — api/helpers.py"""
import time
import pytest

from api.helpers import clean, confidence, map_level, rate_ok, _rate_counts


# ── clean() ──────────────────────────────────────────────────────────────────

class TestClean:
    def test_removes_json_tool_call_block(self):
        txt = 'Voici la réponse. {"role": "assistant", "content": "blah"}'
        assert '{"role"' not in clean(txt)

    def test_removes_xml_tool_call_tags(self):
        txt = 'Réponse<tool_call>{"name":"get_data"}</tool_call>suite'
        result = clean(txt)
        assert '<tool_call>' not in result
        assert 'suite' in result

    def test_removes_placeholder_ids(self):
        result = clean('valeur: [ID12] et [valeur3]')
        assert '[ID12]' not in result
        assert '[valeur3]' not in result
        assert 'valeur:' in result

    def test_collapses_excess_newlines(self):
        txt = 'ligne1\n\n\n\nligne2'
        assert clean(txt) == 'ligne1\n\nligne2'

    def test_passthrough_clean_text(self):
        txt = 'Température actuelle : 22 °C'
        assert clean(txt) == txt

    def test_strips_whitespace(self):
        assert clean('  bonjour  ') == 'bonjour'


# ── confidence() ─────────────────────────────────────────────────────────────

class TestConfidence:
    def test_low_when_contains_je_ne_sais_pas(self):
        assert confidence("je ne sais pas", "data") == "faible"

    def test_low_when_contains_error(self):
        assert confidence("Une erreur s'est produite", "data") == "faible"

    def test_low_when_unavailable(self):
        assert confidence("Données indisponibles.", "static") == "faible"

    def test_high_for_static_level(self):
        assert confidence("Les modules disponibles sont : eau, gaz.", "static") == "haute"

    def test_high_for_data_level(self):
        assert confidence("La température est 22 °c.", "data") == "haute"

    def test_high_when_sensor_unit_present(self):
        assert confidence("Humidité : 55 %hr", "knowledge") == "haute"

    def test_moyenne_default(self):
        assert confidence("Voici un résumé.", "knowledge") == "moyenne"

    def test_case_insensitive_low_signal(self):
        assert confidence("I DON'T KNOW the answer", "data") == "faible"


# ── map_level() ───────────────────────────────────────────────────────────────

class TestMapLevel:
    def test_static_maps_to_1(self):
        assert map_level("static") == "1"

    def test_knowledge_maps_to_1(self):
        assert map_level("knowledge") == "1"

    def test_data_maps_to_2(self):
        assert map_level("data") == "2"

    def test_error_maps_to_0(self):
        assert map_level("error") == "0"

    def test_unknown_defaults_to_2(self):
        assert map_level("anything_else") == "2"

    def test_empty_string_defaults_to_2(self):
        assert map_level("") == "2"


# ── rate_ok() ─────────────────────────────────────────────────────────────────

class TestRateOk:
    def setup_method(self):
        _rate_counts.clear()

    def test_allows_first_request(self):
        assert rate_ok("1.2.3.4") is True

    def test_allows_up_to_limit(self):
        ip = "10.0.0.1"
        for _ in range(30):
            assert rate_ok(ip, limit=30) is True

    def test_blocks_at_limit(self):
        ip = "10.0.0.2"
        for _ in range(5):
            rate_ok(ip, limit=5)
        assert rate_ok(ip, limit=5) is False

    def test_different_ips_are_independent(self):
        for _ in range(5):
            rate_ok("192.168.0.1", limit=5)
        assert rate_ok("192.168.0.2", limit=5) is True

    def test_old_entries_are_pruned(self):
        ip = "172.16.0.1"
        now = time.time()
        # Injecte 5 timestamps périmés (>60s) directement
        _rate_counts[ip] = [now - 70] * 5
        assert rate_ok(ip, limit=5) is True
