"""Tests unitaires — mcp_client/chart_builder.py"""
import json
import pytest
from mcp_client.chart_builder import (
    build_charts,
    _parse,
    _label,
    _nonzero,
    _fval,
    _normalize_battery,
    _bar,
    _doughnut,
    _ds,
    _chart_wm,
    _chart_energy,
    _chart_gm,
    _chart_fuel,
    _chart_thl,
    _chart_realtime,
    _chart_anomaly,
    _chart_trend,
)


def _ok(data: dict) -> str:
    return json.dumps({'status': 'success', **data})


# ── _parse() ──────────────────────────────────────────────────────────────────

class TestParse:
    def test_valid_success_status(self):
        raw = json.dumps({'status': 'success', 'data': 1})
        result = _parse(raw)
        assert result is not None
        assert result['status'] == 'success'

    def test_valid_ok_status(self):
        raw = json.dumps({'status': 'ok', 'count': 5})
        assert _parse(raw) is not None

    def test_invalid_json_returns_none(self):
        assert _parse("not json {{") is None

    def test_wrong_status_returns_none(self):
        raw = json.dumps({'status': 'error', 'message': 'db fail'})
        assert _parse(raw) is None

    def test_missing_status_returns_none(self):
        raw = json.dumps({'count': 3})
        assert _parse(raw) is None

    def test_array_returns_none(self):
        raw = json.dumps([{'status': 'success'}])
        assert _parse(raw) is None

    def test_empty_string_returns_none(self):
        assert _parse('') is None


# ── _label() ──────────────────────────────────────────────────────────────────

class TestLabel:
    def test_capteur_nom_has_priority(self):
        row = {'capteur_nom': 'Capteur A', 'zone': 'Zone B', 'name': 'X'}
        assert _label(row) == 'Capteur A'

    def test_zone_fallback_when_no_capteur_nom(self):
        assert _label({'zone': 'Zone 1'}) == 'Zone 1'

    def test_name_fallback(self):
        assert _label({'name': 'Sensor X'}) == 'Sensor X'

    def test_id_device_last_resort(self):
        assert _label({'id_device': 'DEV001'}) == 'DEV001'

    def test_empty_row_returns_question_mark(self):
        assert _label({}) == '?'

    def test_blank_capteur_nom_skipped(self):
        assert _label({'capteur_nom': '   ', 'zone': 'Zone 2'}) == 'Zone 2'

    def test_none_value_skipped(self):
        assert _label({'capteur_nom': None, 'name': 'Fallback'}) == 'Fallback'


# ── _nonzero() ────────────────────────────────────────────────────────────────

class TestNonzero:
    def test_empty_list_is_false(self):
        assert _nonzero([]) is False

    def test_all_zeros_is_false(self):
        assert _nonzero([0, 0.0, 0]) is False

    def test_single_nonzero_is_true(self):
        assert _nonzero([0, 5.0, 0]) is True

    def test_negative_is_nonzero(self):
        assert _nonzero([-1]) is True

    def test_none_values_ignored(self):
        assert _nonzero([None, None]) is False

    def test_strings_ignored(self):
        assert _nonzero(['hello', 'world']) is False

    def test_mixed_none_and_nonzero(self):
        assert _nonzero([None, 0, 3.0]) is True


# ── _fval() ───────────────────────────────────────────────────────────────────

class TestFval:
    def test_first_col_returned(self):
        assert _fval({'a': 5.0, 'b': 3.0}, 'a', 'b') == 5.0

    def test_fallback_to_second_col(self):
        assert _fval({'b': 3.0}, 'a', 'b') == 3.0

    def test_none_col_skipped(self):
        assert _fval({'a': None, 'b': 2.0}, 'a', 'b') == 2.0

    def test_no_col_found_returns_zero(self):
        assert _fval({'x': 9.0}, 'a', 'b') == 0.0

    def test_string_number_converted(self):
        assert _fval({'a': '7.5'}, 'a') == 7.5

    def test_non_numeric_string_returns_zero(self):
        assert _fval({'a': 'abc'}, 'a') == 0.0

    def test_integer_converted(self):
        assert _fval({'a': 10}, 'a') == 10.0


# ── _normalize_battery() ──────────────────────────────────────────────────────

class TestNormalizeBattery:
    def test_lorawan_max_254_is_100(self):
        assert _normalize_battery(254) == 100.0

    def test_lorawan_zero_is_0(self):
        assert _normalize_battery(0) == 0.0

    def test_lorawan_127_approximately_50(self):
        result = _normalize_battery(127)
        assert 48.0 <= result <= 52.0

    def test_direct_percent_50_unchanged(self):
        assert _normalize_battery(50) == 50.0

    def test_direct_percent_100_unchanged(self):
        assert _normalize_battery(100) == 100.0

    def test_lorawan_above_100_converted_to_under_100(self):
        assert _normalize_battery(200) < 100.0

    def test_clamped_below_zero(self):
        assert _normalize_battery(-10) == 0.0


# ── _bar() / _doughnut() / _ds() ─────────────────────────────────────────────

class TestChartFactories:
    def test_bar_type(self):
        c = _bar('Title', ['A'], [_ds('ds', [1], '#fff')], 'kWh')
        assert c['type'] == 'bar'
        assert c['title'] == 'Title'
        assert c['unit'] == 'kWh'

    def test_doughnut_type(self):
        c = _doughnut('Pie', ['X'], [_ds('ds', [2], '#000')])
        assert c['type'] == 'doughnut'

    def test_ds_structure(self):
        ds = _ds('myLabel', [1, 2, 3], '#abc')
        assert ds['label'] == 'myLabel'
        assert ds['data'] == [1, 2, 3]
        assert ds['color'] == '#abc'


# ── build_charts() ────────────────────────────────────────────────────────────

class TestBuildCharts:
    def _wm_payload(self) -> str:
        return _ok({'period': '7j', 'analysis': [
            {'capteur_nom': 'WM01', 'consommation_nette_m3': 5.0}
        ]})

    def test_known_tool_returns_list(self):
        result = build_charts('wm_analysis', self._wm_payload())
        assert isinstance(result, list)
        assert len(result) > 0

    def test_unknown_tool_returns_empty(self):
        result = build_charts('unknown_tool', self._wm_payload())
        assert result == []

    def test_parse_failure_returns_empty(self):
        result = build_charts('wm_analysis', 'not json')
        assert result == []

    def test_error_status_returns_empty(self):
        payload = json.dumps({'status': 'error', 'message': 'db fail'})
        result = build_charts('wm_analysis', payload)
        assert result == []

    def test_trend_tool_dispatched(self):
        payload = _ok({
            'label': 'Eau', 'period': '24h', 'granularity': 'hour', 'unit': 'm³',
            'series': [{'device': 'WM01', 'zone': 'Z1',
                        'points': [{'t': '06h', 'v': 1.0}, {'t': '07h', 'v': 2.0}]}],
        })
        result = build_charts('wm_trend', payload)
        assert isinstance(result, list)
        assert result[0]['type'] == 'line'

    def test_energy_tool_dispatched(self):
        payload = _ok({'period': '24h', 'analysis': [
            {'capteur_nom': 'EN01', 'total_kWh_L1': 10.0,
             'total_kWh_L2': 0.0, 'total_kWh_L3': 0.0}
        ]})
        result = build_charts('energy_analysis', payload)
        assert isinstance(result, list)

    def test_anomaly_tool_dispatched(self):
        payload = _ok({'period': '24h', 'summary': {
            'extreme_values': [1], 'sensor_issues': [],
            'fluid_alerts': [], 'energy_alerts': [], 'inactive_sensors': [],
        }})
        result = build_charts('anomaly_detection', payload)
        assert isinstance(result, list)


# ── _chart_wm() ───────────────────────────────────────────────────────────────

class TestChartWm:
    def test_produces_bar_chart(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'WM01', 'consommation_nette_m3': 5.0}
        ]}
        charts = _chart_wm(data)
        assert len(charts) == 1
        assert charts[0]['type'] == 'bar'

    def test_label_in_chart(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'Compteur A', 'consommation_nette_m3': 3.0}
        ]}
        assert 'Compteur A' in _chart_wm(data)[0]['labels']

    def test_unit_is_m3(self):
        data = {'period': '30j', 'analysis': [
            {'capteur_nom': 'WM', 'consommation_nette_m3': 10.0}
        ]}
        assert _chart_wm(data)[0]['unit'] == 'm³'

    def test_empty_rows_returns_empty(self):
        assert _chart_wm({'analysis': []}) == []

    def test_all_zero_values_returns_empty(self):
        data = {'analysis': [{'capteur_nom': 'WM', 'consommation_nette_m3': 0}]}
        assert _chart_wm(data) == []

    def test_fallback_to_total_m3(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'WM', 'total_m3': 8.0}
        ]}
        assert len(_chart_wm(data)) == 1

    def test_period_in_title(self):
        data = {'period': '30j', 'analysis': [
            {'capteur_nom': 'WM', 'consommation_nette_m3': 2.0}
        ]}
        assert '30j' in _chart_wm(data)[0]['title']


# ── _chart_energy() ───────────────────────────────────────────────────────────

class TestChartEnergy:
    def test_single_sensor_phase_chart(self):
        data = {'period': '24h', 'analysis': [
            {'capteur_nom': 'EN01', 'total_kWh_L1': 10.0,
             'total_kWh_L2': 5.0, 'total_kWh_L3': 3.0}
        ]}
        charts = _chart_energy(data)
        assert any(c['type'] == 'bar' for c in charts)

    def test_multiple_sensors_returns_charts(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'EN01', 'total_kWh_L1': 10.0,
             'total_kWh_L2': 0.0, 'total_kWh_L3': 0.0},
            {'capteur_nom': 'EN02', 'total_kWh_L1': 15.0,
             'total_kWh_L2': 0.0, 'total_kWh_L3': 0.0},
        ]}
        charts = _chart_energy(data)
        assert len(charts) >= 1

    def test_cosfi_doughnut_when_present(self):
        data = {'period': '24h', 'analysis': [
            {'capteur_nom': 'EN01', 'total_kWh_L1': 5.0,
             'total_kWh_L2': 0.0, 'total_kWh_L3': 0.0, 'avg_cosfi_L1': 0.92}
        ]}
        charts = _chart_energy(data)
        assert any(c['type'] == 'doughnut' for c in charts)

    def test_empty_rows_returns_empty(self):
        assert _chart_energy({'analysis': []}) == []

    def test_max_two_charts(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'EN01', 'total_kWh_L1': 5.0,
             'total_kWh_L2': 3.0, 'total_kWh_L3': 2.0, 'avg_cosfi_L1': 0.9},
        ]}
        assert len(_chart_energy(data)) <= 2

    def test_unit_is_kwh(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'EN01', 'total_kWh_L1': 10.0,
             'total_kWh_L2': 0.0, 'total_kWh_L3': 0.0}
        ]}
        bar_charts = [c for c in _chart_energy(data) if c['type'] == 'bar']
        assert len(bar_charts) > 0
        assert bar_charts[0]['unit'] == 'kWh'


# ── _chart_gm() ───────────────────────────────────────────────────────────────

class TestChartGm:
    def test_produces_bar_chart(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'GM01', 'consommation_nette_m3': 2.5}
        ]}
        charts = _chart_gm(data)
        assert len(charts) == 1
        assert charts[0]['type'] == 'bar'

    def test_unit_is_m3(self):
        data = {'period': '30j', 'analysis': [
            {'capteur_nom': 'GM', 'consommation_nette_m3': 1.0}
        ]}
        assert _chart_gm(data)[0]['unit'] == 'm³'

    def test_empty_rows_returns_empty(self):
        assert _chart_gm({'analysis': []}) == []

    def test_fallback_to_avg_debit(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'GM', 'avg_debit_min': 0.5}
        ]}
        assert len(_chart_gm(data)) == 1


# ── _chart_fuel() ─────────────────────────────────────────────────────────────

class TestChartFuel:
    def test_fuel_bar_from_total_L(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'VEH01', 'total_L': 50.0}
        ]}
        charts = _chart_fuel(data)
        assert any(c['unit'] == 'L' for c in charts)

    def test_km_chart_added_when_present(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'VEH01', 'total_L': 50.0, 'total_km': 600.0}
        ]}
        charts = _chart_fuel(data)
        assert any(c['unit'] == 'km' for c in charts)

    def test_max_two_charts(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'VEH01', 'total_L': 50.0, 'total_km': 600.0}
        ]}
        assert len(_chart_fuel(data)) <= 2

    def test_empty_rows_returns_empty(self):
        assert _chart_fuel({'analysis': []}) == []

    def test_no_fuel_no_km_returns_empty(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'VEH01', 'total_L': 0}
        ]}
        assert _chart_fuel(data) == []


# ── _chart_thl() ──────────────────────────────────────────────────────────────

class TestChartThl:
    def test_temperature_chart_produced(self):
        data = {'period': '24h', 'analysis': [
            {'capteur_nom': 'THL01', 't_avg': 22.5}
        ]}
        charts = _chart_thl(data)
        assert any('Température' in c['title'] for c in charts)

    def test_humidity_chart_produced(self):
        data = {'period': '24h', 'analysis': [
            {'capteur_nom': 'THL01', 'h_avg': 55.0}
        ]}
        charts = _chart_thl(data)
        assert any('Humidité' in c['title'] for c in charts)

    def test_both_charts_when_both_data(self):
        data = {'period': '24h', 'analysis': [
            {'capteur_nom': 'THL01', 't_avg': 22.0, 'h_avg': 60.0}
        ]}
        charts = _chart_thl(data)
        assert len(charts) == 2

    def test_empty_rows_returns_empty(self):
        assert _chart_thl({'analysis': []}) == []

    def test_max_two_charts(self):
        data = {'period': '7j', 'analysis': [
            {'capteur_nom': 'THL01', 't_avg': 22.0, 'h_avg': 55.0}
        ]}
        assert len(_chart_thl(data)) <= 2

    def test_temp_unit_is_celsius(self):
        data = {'period': '24h', 'analysis': [
            {'capteur_nom': 'THL01', 't_avg': 25.0}
        ]}
        bar = [c for c in _chart_thl(data) if 'Température' in c['title']][0]
        assert bar['unit'] == '°C'


# ── _chart_realtime() ─────────────────────────────────────────────────────────

class TestChartRealtime:
    def test_battery_chart_produced(self):
        data = {'capteurs': [
            {'capteur_nom': 'C1', 'battery_level': 200},
            {'capteur_nom': 'C2', 'battery_level': 100},
        ]}
        charts = _chart_realtime(data)
        assert len(charts) == 1
        assert charts[0]['title'] == 'Batterie des capteurs'

    def test_no_battery_returns_empty(self):
        data = {'capteurs': [{'capteur_nom': 'C1'}]}
        assert _chart_realtime(data) == []

    def test_empty_capteurs_returns_empty(self):
        assert _chart_realtime({'capteurs': []}) == []

    def test_ymax_is_100(self):
        data = {'capteurs': [{'capteur_nom': 'C1', 'battery_level': 200}]}
        assert _chart_realtime(data)[0]['yMax'] == 100

    def test_color_green_for_high_battery(self):
        data = {'capteurs': [{'capteur_nom': 'C1', 'battery_level': 254}]}  # 100%
        chart = _chart_realtime(data)[0]
        assert chart['datasets'][0]['colors'][0] == '#10b981'

    def test_color_red_for_low_battery(self):
        data = {'capteurs': [{'capteur_nom': 'C1', 'battery_level': 15}]}  # 15% direct
        chart = _chart_realtime(data)[0]
        assert chart['datasets'][0]['colors'][0] == '#e74c3c'

    def test_color_orange_for_medium_battery(self):
        data = {'capteurs': [{'capteur_nom': 'C1', 'battery_level': 30}]}  # 30% direct
        chart = _chart_realtime(data)[0]
        assert chart['datasets'][0]['colors'][0] == '#f59e0b'


# ── _chart_trend() ────────────────────────────────────────────────────────────

class TestChartTrend:
    def test_produces_line_chart(self):
        data = {'label': 'Eau', 'period': '24h', 'granularity': 'hour', 'unit': 'm³',
                'series': [{'device': 'WM01', 'points': [{'t': '06h', 'v': 1.0}]}]}
        charts = _chart_trend(data)
        assert len(charts) == 1
        assert charts[0]['type'] == 'line'

    def test_empty_series_returns_empty(self):
        assert _chart_trend({'series': []}) == []

    def test_labels_follow_bucket_order(self):
        data = {'label': 'Eau', 'period': '24h', 'granularity': 'hour', 'unit': 'm³',
                'series': [{'device': 'WM01', 'points': [
                    {'t': '06h', 'v': 1.0}, {'t': '07h', 'v': 2.0}, {'t': '08h', 'v': 3.0},
                ]}]}
        assert _chart_trend(data)[0]['labels'] == ['06h', '07h', '08h']

    def test_one_dataset_per_series(self):
        data = {'label': 'Énergie', 'period': '7j', 'granularity': 'day', 'unit': 'kWh',
                'series': [
                    {'device': 'EN01', 'points': [{'t': '01/01', 'v': 5.0}]},
                    {'device': 'EN02', 'points': [{'t': '01/01', 'v': 8.0}]},
                ]}
        datasets = _chart_trend(data)[0]['datasets']
        assert {d['label'] for d in datasets} == {'EN01', 'EN02'}

    def test_missing_bucket_filled_with_zero(self):
        data = {'label': 'Eau', 'period': '24h', 'granularity': 'hour', 'unit': 'm³',
                'series': [
                    {'device': 'WM01', 'points': [{'t': '06h', 'v': 1.0}, {'t': '07h', 'v': 2.0}]},
                    {'device': 'WM02', 'points': [{'t': '06h', 'v': 5.0}]},
                ]}
        chart = _chart_trend(data)[0]
        wm02 = next(d for d in chart['datasets'] if d['label'] == 'WM02')
        assert wm02['data'] == [5.0, 0]

    def test_unit_propagated(self):
        data = {'label': 'Gaz', 'period': '30j', 'granularity': 'day', 'unit': 'm³',
                'series': [{'device': 'GM01', 'points': [{'t': '01/01', 'v': 1.0}]}]}
        assert _chart_trend(data)[0]['unit'] == 'm³'

    def test_title_mentions_granularity(self):
        hourly = {'label': 'Eau', 'period': '24h', 'granularity': 'hour', 'unit': 'm³',
                  'series': [{'device': 'WM01', 'points': [{'t': '06h', 'v': 1.0}]}]}
        daily = {'label': 'Eau', 'period': '7j', 'granularity': 'day', 'unit': 'm³',
                 'series': [{'device': 'WM01', 'points': [{'t': '01/01', 'v': 1.0}]}]}
        assert 'horaire' in _chart_trend(hourly)[0]['title']
        assert 'journalière' in _chart_trend(daily)[0]['title']


# ── _chart_anomaly() ──────────────────────────────────────────────────────────

class TestChartAnomaly:
    def test_doughnut_chart_produced(self):
        data = {'period': '24h', 'summary': {
            'extreme_values': [1, 2],
            'sensor_issues': [],
            'fluid_alerts': [1],
            'energy_alerts': [],
            'inactive_sensors': [],
        }}
        charts = _chart_anomaly(data)
        assert len(charts) == 1
        assert charts[0]['type'] == 'doughnut'

    def test_empty_summary_returns_empty(self):
        data = {'summary': {
            'extreme_values': [], 'sensor_issues': [],
            'fluid_alerts': [], 'energy_alerts': [], 'inactive_sensors': [],
        }}
        assert _chart_anomaly(data) == []

    def test_only_nonzero_categories_in_labels(self):
        data = {'period': '', 'summary': {
            'extreme_values': [1],
            'sensor_issues': [],
            'fluid_alerts': [],
            'energy_alerts': [],
            'inactive_sensors': [],
        }}
        chart = _chart_anomaly(data)[0]
        assert 'Valeurs extrêmes' in chart['labels']
        assert 'Capteurs' not in chart['labels']

    def test_all_categories_when_all_nonzero(self):
        data = {'period': 'all', 'summary': {
            'extreme_values': [1], 'sensor_issues': [1],
            'fluid_alerts': [1], 'energy_alerts': [1], 'inactive_sensors': [1],
        }}
        chart = _chart_anomaly(data)[0]
        assert len(chart['labels']) == 5

    def test_count_in_data_matches_list_length(self):
        data = {'period': '', 'summary': {
            'extreme_values': [1, 2, 3], 'sensor_issues': [],
            'fluid_alerts': [1], 'energy_alerts': [], 'inactive_sensors': [],
        }}
        chart = _chart_anomaly(data)[0]
        idx_extreme = chart['labels'].index('Valeurs extrêmes')
        assert chart['datasets'][0]['data'][idx_extreme] == 3
