"""Tests unitaires — api/pipeline/recommendation_engine.py (fonctions pures)"""
import json
import pytest
from api.pipeline.recommendation_engine import _flag_implausible_savings
from api.pipeline.reco.fallback import _rule_based_fallback
from api.pipeline.reco.llm import _parse_json_response, _validate_reasoning


# ── _parse_json_response() ────────────────────────────────────────────────────

class TestParseJsonResponse:
    def test_plain_json_with_title(self):
        raw = json.dumps({'title': 'Recommandation', 'description': 'Desc'})
        result = _parse_json_response(raw)
        assert result is not None
        assert result['title'] == 'Recommandation'

    def test_json_fenced_block(self):
        raw = '```json\n{"title": "Action corrective", "priority": "high"}\n```'
        result = _parse_json_response(raw)
        assert result is not None
        assert result['title'] == 'Action corrective'

    def test_plain_fenced_block(self):
        raw = '```\n{"title": "Test", "action": "Vérifier"}\n```'
        result = _parse_json_response(raw)
        assert result is not None

    def test_json_embedded_in_text(self):
        raw = 'Voici la recommandation : {"title": "Action", "description": "desc"}'
        result = _parse_json_response(raw)
        assert result is not None
        assert result['title'] == 'Action'

    def test_missing_title_key_returns_none(self):
        raw = json.dumps({'priority': 'high', 'description': 'no title'})
        assert _parse_json_response(raw) is None

    def test_invalid_json_returns_none(self):
        assert _parse_json_response('this is not json at all') is None

    def test_empty_string_returns_none(self):
        assert _parse_json_response('') is None

    def test_malformed_json_in_fence_returns_none(self):
        raw = '```json\n{title: missing_quotes}\n```'
        assert _parse_json_response(raw) is None

    def test_title_preserved_from_fenced(self):
        raw = '```json\n{"title": "Surconsommation", "priority": "critical"}\n```'
        result = _parse_json_response(raw)
        assert result['title'] == 'Surconsommation'


# ── _validate_reasoning() ─────────────────────────────────────────────────────

class TestValidateReasoning:
    _VALID = 'La consommation dépasse les seuils habituels depuis 3 jours consécutifs.'

    def test_valid_reasoning_returned(self):
        result = _validate_reasoning(self._VALID)
        assert result == self._VALID.strip()

    def test_none_returns_none(self):
        assert _validate_reasoning(None) is None

    def test_empty_string_returns_none(self):
        assert _validate_reasoning('') is None

    def test_too_short_returns_none(self):
        assert _validate_reasoning('Trop court.') is None

    def test_exactly_at_min_length(self):
        text = 'A' * 30
        result = _validate_reasoning(text)
        assert result == text

    def test_placeholder_keyword_rejected(self):
        text = 'This value contains a placeholder that should not be valid here abc.'
        assert _validate_reasoning(text) is None

    def test_bracket_placeholder_rejected(self):
        text = 'Analyse : [value] est supérieure à la baseline — vérifier les équipements.'
        assert _validate_reasoning(text) is None

    def test_todo_keyword_rejected(self):
        text = 'TODO: analyser la consommation et corriger les anomalies détectées maintenant.'
        assert _validate_reasoning(text) is None

    def test_example_keyword_rejected(self):
        text = 'Example of an anomaly detection result that exceeded the expected threshold here.'
        assert _validate_reasoning(text) is None

    def test_whitespace_stripped(self):
        text = '   ' + 'A' * 40 + '   '
        result = _validate_reasoning(text)
        assert result == 'A' * 40

    def test_non_string_returns_none(self):
        assert _validate_reasoning(42) is None

    def test_list_returns_none(self):
        assert _validate_reasoning(['reason']) is None


# ── _rule_based_fallback() ────────────────────────────────────────────────────

class TestRuleBasedFallback:
    def _overconsumption(self, deviation_pct: float = 55.0) -> dict:
        return {
            'rec_type':          'OVERCONSUMPTION',
            'device_id':         'EN_001',
            'label':             'Compteur Principal',
            'actual_26h':        120.5,
            'baseline_p50_sum':  80.0,
            'deviation_pct':     deviation_pct,
            'peak_hours':        [8, 9, 10],
            'unit':              'kWh',
            'estimated_saving_tnd': 45.0,
        }

    def test_valid_signal_returns_dict(self):
        result = _rule_based_fallback(self._overconsumption(), 'energy')
        assert result is not None
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        result = _rule_based_fallback(self._overconsumption(), 'energy')
        for key in ('priority', 'title', 'description', 'action'):
            assert key in result

    def test_priority_medium_below_50pct(self):
        result = _rule_based_fallback(self._overconsumption(deviation_pct=30), 'energy')
        assert result['priority'] == 'medium'

    def test_priority_high_at_55pct(self):
        result = _rule_based_fallback(self._overconsumption(deviation_pct=55), 'energy')
        assert result['priority'] == 'high'

    def test_priority_critical_above_100pct(self):
        result = _rule_based_fallback(self._overconsumption(deviation_pct=110), 'energy')
        assert result['priority'] == 'critical'

    def test_unknown_rec_type_returns_none(self):
        signal = {'rec_type': 'UNKNOWN_TYPE', 'device_id': 'X'}
        assert _rule_based_fallback(signal, 'energy') is None

    def test_no_consumption_data_generic_response(self):
        signal = {
            'rec_type':          'OVERCONSUMPTION',
            'no_consumption_data': True,
            'chronos_score':     0.8,
            'ad_anomaly_count':  3,
            'device_id':         'EN_002',
            'label':             'Compteur B',
        }
        result = _rule_based_fallback(signal, 'energy')
        assert result is not None
        assert result['priority'] == 'high'  # score >= 0.75
        assert 'Chronos' in result['description']

    def test_no_consumption_data_medium_priority_below_075(self):
        signal = {
            'rec_type':          'OVERCONSUMPTION',
            'no_consumption_data': True,
            'chronos_score':     0.5,
            'ad_anomaly_count':  1,
            'device_id':         'EN_003',
            'label':             'Capteur X',
        }
        result = _rule_based_fallback(signal, 'energy')
        assert result['priority'] == 'medium'

    def test_leak_risk_always_critical(self):
        signal = {
            'rec_type':          'LEAK_RISK',
            'device_id':         'WM_01',
            'label':             'Compteur eau',
            'hours_range':       '02h-05h',
            'nocturnal_excess':  2.5,
            'unit':              'm³',
            'estimated_saving_tnd': 120.0,
        }
        result = _rule_based_fallback(signal, 'water')
        assert result['priority'] == 'critical'

    def test_optimization_always_medium(self):
        signal = {
            'rec_type':          'OPTIMIZATION',
            'device_id':         'EN_001',
            'off_peak_excess':   20.0,
            'off_peak_hours':    '22h-06h',
            'unit':              'kWh',
            'estimated_saving_tnd': 30.0,
        }
        result = _rule_based_fallback(signal, 'energy')
        assert result['priority'] == 'medium'

    def test_maintenance_high_above_40pct_growth(self):
        signal = {
            'rec_type':          'MAINTENANCE',
            'device_id':         'EN_004',
            'trend_growth_pct':  50,
            'day7_value':        150.0,
            'day1_value':        100.0,
            'unit':              'kWh',
        }
        result = _rule_based_fallback(signal, 'energy')
        assert result['priority'] == 'high'

    def test_maintenance_medium_below_40pct_growth(self):
        signal = {
            'rec_type':          'MAINTENANCE',
            'device_id':         'EN_004',
            'trend_growth_pct':  20,
            'day7_value':        120.0,
            'day1_value':        100.0,
            'unit':              'kWh',
        }
        result = _rule_based_fallback(signal, 'energy')
        assert result['priority'] == 'medium'

    def test_missing_template_keys_falls_back_to_generic(self):
        signal = {'rec_type': 'OVERCONSUMPTION', 'device_id': 'X'}  # missing most keys
        result = _rule_based_fallback(signal, 'energy')
        assert result is not None
        assert result['priority'] == 'medium'

    def test_estimated_saving_preserved(self):
        signal = self._overconsumption()
        signal['estimated_saving_tnd'] = 99.5
        result = _rule_based_fallback(signal, 'energy')
        assert result['estimated_saving_tnd'] == 99.5

    def test_reasoning_is_none(self):
        result = _rule_based_fallback(self._overconsumption(), 'energy')
        assert result['reasoning'] is None

    def test_root_cause_is_none(self):
        result = _rule_based_fallback(self._overconsumption(), 'energy')
        assert result['root_cause'] is None


# ── _flag_implausible_savings() ───────────────────────────────────────────────

class TestImplausibleSavings:
    def _leak(self, saving):
        return {
            'rec_type':             'LEAK_RISK',
            'device_id':            '4065',
            'label':                'Eau',
            'hours_range':          '1h–5h',
            'nocturnal_excess':     78050.0,
            'unit':                 'm³',
            'estimated_saving_tnd': saving,
        }

    def test_plausible_saving_kept(self):
        [s] = _flag_implausible_savings([self._leak(120.0)])
        assert s['estimated_saving_tnd'] == 120.0
        assert not s.get('saving_unreliable')

    def test_implausible_saving_removed(self):
        [s] = _flag_implausible_savings([self._leak(1_756_125.0)])
        assert s['estimated_saving_tnd'] is None
        assert s['saving_unreliable'] is True

    def test_missing_saving_untouched(self):
        [s] = _flag_implausible_savings([self._leak(None)])
        assert not s.get('saving_unreliable')

    def test_fallback_has_no_amount_nor_volume(self):
        [s] = _flag_implausible_savings([self._leak(1_756_125.0)])
        result = _rule_based_fallback(s, 'water')
        assert result['estimated_saving_tnd'] is None
        assert 'TND' not in result['description']
        assert '78050' not in result['description']
        assert set(result['i18n']) == {'en', 'ar'}

    def test_fallback_keeps_leak_priority(self):
        [s] = _flag_implausible_savings([self._leak(1_756_125.0)])
        assert _rule_based_fallback(s, 'water')['priority'] == 'critical'

    def test_fallback_mentions_relative_deviation(self):
        signal = {'rec_type': 'OVERCONSUMPTION', 'device_id': '4065', 'label': 'Eau',
                  'unit': 'm³', 'deviation_pct': 110.6, 'estimated_saving_tnd': 87_960.0}
        [s] = _flag_implausible_savings([signal])
        assert '+110.6 %' in _rule_based_fallback(s, 'water')['description']
