"""Tests unitaires — mcp_client/preprocessor.py"""
import pytest
from mcp_client.preprocessor import (
    analyze,
    _detect_sensor,
    _detect_period,
    _detect_query_type,
    Intent,
    EXPECTED_TOOLS,
)


# ── _detect_sensor() ──────────────────────────────────────────────────────────

class TestDetectSensor:
    def test_temperature_is_thl(self):
        assert _detect_sensor("température actuelle") == 'thl'

    def test_humidity_is_thl(self):
        assert _detect_sensor("humidité") == 'thl'

    def test_lux_is_thl(self):
        assert _detect_sensor("luminosité lux") == 'thl'

    def test_eau_is_wm(self):
        assert _detect_sensor("consommation eau") == 'wm'

    def test_fuite_eau_is_wm(self):
        assert _detect_sensor("fuite eau") == 'wm'

    def test_electricite_is_en(self):
        assert _detect_sensor("consommation électrique kwh") == 'en'

    def test_kwh_alone_is_en(self):
        assert _detect_sensor("données kwh") == 'en'

    def test_gaz_is_gm(self):
        assert _detect_sensor("fuite gaz") == 'gm'

    def test_carburant_is_fuel(self):
        assert _detect_sensor("consommation carburant") == 'fuel'

    def test_vehicule_is_fuel(self):
        assert _detect_sensor("véhicule vitesse") == 'fuel'

    def test_passage_is_pir(self):
        assert _detect_sensor("comptage passage") == 'pir'

    def test_presence_is_pir(self):
        assert _detect_sensor("détecteur présence") == 'pir'

    def test_niveau_cuve_is_ls(self):
        assert _detect_sensor("niveau cuve") == 'ls'

    def test_reservoir_is_ls(self):
        assert _detect_sensor("réservoir tank") == 'ls'

    def test_meteo_is_sm(self):
        assert _detect_sensor("météo vent pression") == 'sm'

    def test_multiple_types_returns_all(self):
        result = _detect_sensor("eau et gaz")
        assert result == 'all'

    def test_no_keyword_returns_none(self):
        assert _detect_sensor("rapport général de la journée") is None

    def test_arabic_temperature(self):
        assert _detect_sensor("حرارة") == 'thl'

    def test_english_water(self):
        assert _detect_sensor("water consumption") == 'wm'

    def test_english_energy(self):
        assert _detect_sensor("power voltage") == 'en'


# ── _detect_period() ──────────────────────────────────────────────────────────

class TestDetectPeriod:
    def test_maintenant_is_realtime(self):
        assert _detect_period("température maintenant") == 'realtime'

    def test_actuel_is_realtime(self):
        assert _detect_period("état actuel") == 'realtime'

    def test_aujourd_is_24h(self):
        assert _detect_period("consommation aujourd'hui") == '24h'

    def test_hier_is_24h(self):
        assert _detect_period("données d'hier") == '24h'

    def test_semaine_is_7j(self):
        assert _detect_period("cette semaine") == '7j'

    def test_7j_is_7j(self):
        assert _detect_period("sur 7 jours") == '7j'

    def test_mois_is_30j(self):
        assert _detect_period("ce mois") == '30j'

    def test_mensuel_is_30j(self):
        assert _detect_period("rapport mensuel") == '30j'

    def test_historique_is_tout(self):
        assert _detect_period("historique complet") == 'tout'

    def test_no_period_returns_none(self):
        assert _detect_period("température capteur") is None


# ── _detect_query_type() ──────────────────────────────────────────────────────

class TestDetectQueryType:
    def test_anomalie_is_anomaly(self):
        assert _detect_query_type("anomalie détectée") == 'anomaly'

    def test_fuite_is_anomaly(self):
        assert _detect_query_type("fuite gaz") == 'anomaly'

    def test_fraude_is_anomaly(self):
        assert _detect_query_type("fraude compteur") == 'anomaly'

    def test_rapport_is_report(self):
        assert _detect_query_type("rapport complet") == 'report'

    def test_actuel_is_realtime(self):
        assert _detect_query_type("état actuel") == 'realtime'

    def test_historique_is_historical(self):
        assert _detect_query_type("analyse historique") == 'historical'

    def test_select_is_security(self):
        assert _detect_query_type("select * from table") == 'security'

    def test_drop_is_security(self):
        assert _detect_query_type("drop table users") == 'security'

    def test_sql_keyword_is_security(self):
        assert _detect_query_type("schéma base de données") == 'security'

    def test_definition_is_simple(self):
        assert _detect_query_type("c'est quoi le kwh") == 'simple'

    def test_unknown_is_unknown(self):
        assert _detect_query_type("blabla xyz 123") == 'unknown'

    def test_security_has_priority_over_anomaly(self):
        # "alerte" est anomaly, "sql" est security → security gagne
        assert _detect_query_type("sql alerte") == 'security'


# ── analyze() ─────────────────────────────────────────────────────────────────

class TestAnalyze:
    def test_returns_intent_instance(self):
        assert isinstance(analyze("température actuelle"), Intent)

    def test_sensor_detected(self):
        result = analyze("humidité THL")
        assert result.sensor_type == 'thl'

    def test_period_detected(self):
        result = analyze("consommation eau cette semaine")
        assert result.period == '7j'

    def test_query_type_detected(self):
        result = analyze("anomalie détectée sur le réseau")
        assert result.query_type == 'anomaly'

    def test_is_data_query_for_sensor_question(self):
        assert analyze("consommation eau ce mois").is_data_query is True

    def test_not_data_query_for_simple(self):
        assert analyze("c'est quoi le kwh").is_data_query is False

    def test_not_data_query_for_security(self):
        assert analyze("select * from users").is_data_query is False

    def test_raw_question_preserved(self):
        q = "Température actuelle ?"
        result = analyze(q)
        assert result.raw_question == q

    def test_no_history_no_crash(self):
        result = analyze("et ça ?")
        assert isinstance(result, Intent)

    def test_history_resolves_ambiguous_pronoun(self):
        history = [
            {'role': 'user', 'content': 'consommation gaz'},
            {'role': 'assistant', 'content': 'La consommation gaz est normale.'},
        ]
        result = analyze("et la semaine dernière ?", history=history)
        # "gaz" détecté dans l'historique
        assert result.sensor_type == 'gm'

    def test_empty_question_is_not_data(self):
        result = analyze("  ")
        assert result.is_data_query is False


# ── EXPECTED_TOOLS cohérence ──────────────────────────────────────────────────

class TestExpectedTools:
    def test_thl_has_realtime_and_thl_analysis(self):
        assert 'realtime_data' in EXPECTED_TOOLS['thl']
        assert 'thl_analysis' in EXPECTED_TOOLS['thl']

    def test_wm_has_wm_analysis(self):
        assert 'wm_analysis' in EXPECTED_TOOLS['wm']

    def test_en_has_energy_analysis(self):
        assert 'energy_analysis' in EXPECTED_TOOLS['en']

    def test_fuel_has_fuel_analysis(self):
        assert 'fuel_analysis' in EXPECTED_TOOLS['fuel']

    def test_all_keys_covered(self):
        expected_keys = {
            'thl', 'wm', 'en', 'gm', 'fuel', 'pir', 'ls', 'sm', 'all',
            'prediction', 'recommendation',   # query types avec tools dédiés
        }
        assert expected_keys == set(EXPECTED_TOOLS.keys())
