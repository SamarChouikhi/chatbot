"""Tests unitaires — mcp_client/output_guard.py"""
import pytest
from mcp_client.output_guard import (
    check_output,
    needs_retry,
    build_retry_hint,
    QualityReport,
    RETRY_THRESHOLD,
)
from mcp_client.preprocessor import Intent


def _intent(sensor_type=None, query_type='realtime', is_data_query=True) -> Intent:
    return Intent(
        sensor_type=sensor_type,
        period=None,
        query_type=query_type,
        is_data_query=is_data_query,
        raw_question='test',
    )


def _data_response(badge='🟢', words=20, units='°c') -> str:
    """Génère une réponse data valide minimale."""
    return f"{badge} NORMAL — " + f" {units} ".join(["valeur"] * words)


# ── QualityReport.compute_score() ────────────────────────────────────────────

class TestComputeScore:
    def test_perfect_score_is_1(self):
        r = QualityReport(tools_called_ok=True, length_ok=True,
                          is_clean=True, has_units=True)
        r.compute_score()
        assert r.score == 1.0

    def test_score_in_range(self):
        r = QualityReport()
        r.compute_score()
        assert 0.0 <= r.score <= 1.0

    def test_missing_tools_lowers_score(self):
        r = QualityReport(tools_called_ok=False, length_ok=True,
                          is_clean=True, has_units=True)
        r.compute_score()
        assert r.score < 1.0

    def test_all_failures_below_threshold(self):
        r = QualityReport(tools_called_ok=False, length_ok=False,
                          is_clean=False, has_units=False)
        r.compute_score()
        assert r.score < RETRY_THRESHOLD

    def test_score_rounded_to_3_decimals(self):
        r = QualityReport(tools_called_ok=False, length_ok=True,
                          is_clean=True, has_units=True)
        r.compute_score()
        assert r.score == round(r.score, 3)


# ── check_output() ────────────────────────────────────────────────────────────

class TestCheckOutputIntegration:
    def test_returns_quality_report(self):
        intent = _intent(sensor_type='thl')
        response = _data_response(units='°c')
        report = check_output(response, ['realtime_data', 'thl_analysis'], intent)
        assert isinstance(report, QualityReport)

    def test_perfect_response_score_above_threshold(self):
        intent = _intent(sensor_type='thl')
        response = _data_response(units='°c')
        report = check_output(response, ['realtime_data', 'thl_analysis'], intent)
        assert report.score >= RETRY_THRESHOLD

    def test_non_data_query_tools_ok(self):
        intent = _intent(query_type='simple', is_data_query=False)
        report = check_output("ARIA est un assistant IoT.", [], intent)
        assert report.tools_called_ok is True

    def test_missing_tool_triggers_retry(self):
        intent = _intent(sensor_type='wm')
        response = _data_response(units='m³')
        report = check_output(response, [], intent)
        assert needs_retry(report) is True


class TestCheckOutputTools:
    def test_correct_tool_satisfies_check(self):
        intent = _intent(sensor_type='gm')
        resp = _data_response(units='m³')
        report = check_output(resp, ['gm_analysis'], intent)
        assert report.tools_called_ok is True

    def test_no_tool_fails_for_sensor_query(self):
        intent = _intent(sensor_type='en')
        resp = _data_response(units='kwh')
        report = check_output(resp, [], intent)
        assert report.tools_called_ok is False

    def test_missing_tools_recorded(self):
        intent = _intent(sensor_type='thl')
        resp = _data_response(units='°c')
        report = check_output(resp, [], intent)
        assert len(report.missing_tools) > 0

    def test_tools_ok_when_no_sensor_type(self):
        intent = _intent(sensor_type=None)
        report = check_output("Réponse générale.", [], intent)
        assert report.tools_called_ok is True

    def test_tools_ok_for_non_data_query(self):
        intent = _intent(query_type='simple', is_data_query=False)
        report = check_output("Une explication.", [], intent)
        assert report.tools_called_ok is True


class TestCheckOutputLength:
    def test_too_short_data_response(self):
        intent = _intent(sensor_type='en')
        response = "🟢 NORMAL — 22 kWh"  # < 15 mots
        report = check_output(response, ['energy_analysis'], intent)
        assert report.too_short is True
        assert report.length_ok is False

    def test_adequate_length_ok(self):
        intent = _intent(sensor_type='thl')
        response = _data_response(units='°c')
        report = check_output(response, ['realtime_data'], intent)
        assert report.too_short is False

    def test_too_long_simple_response(self):
        intent = _intent(query_type='simple', is_data_query=False)
        response = " ".join(["mot"] * 130)
        report = check_output(response, [], intent)
        assert report.too_long is True
        assert report.length_ok is False

    def test_simple_response_within_limit(self):
        intent = _intent(query_type='simple', is_data_query=False)
        response = "ARIA est un assistant de monitoring IoT en temps réel."
        report = check_output(response, [], intent)
        assert report.too_long is False


class TestCheckOutputCleanliness:
    def test_placeholder_detected(self):
        intent = _intent(sensor_type='thl')
        response = "🟢 — La valeur est [value] et le capteur est [capteur] données."
        report = check_output(response, ['realtime_data'], intent)
        assert report.is_clean is False
        assert len(report.hallucinations) > 0

    def test_filler_start_flagged(self):
        intent = _intent(sensor_type=None, is_data_query=False)
        response = "Bien sûr, voici les informations."
        report = check_output(response, [], intent)
        assert report.is_clean is False

    def test_clean_response_passes(self):
        intent = _intent(sensor_type='thl')
        response = _data_response(units='°c')
        report = check_output(response, ['realtime_data'], intent)
        assert report.is_clean is True
        assert report.hallucinations == []

    def test_double_braces_flagged(self):
        intent = _intent()
        response = "🟢 — {{valeur}} données " + " mot " * 15
        report = check_output(response, [], intent)
        assert report.is_clean is False


class TestCheckOutputUnits:
    def test_has_units_for_thl(self):
        intent = _intent(sensor_type='thl')
        response = _data_response(units='°c')
        report = check_output(response, ['realtime_data'], intent)
        assert report.has_units is True

    def test_has_units_for_en_with_kwh(self):
        # Les unités énergie incluent 'v','a','w' (1 car) présents dans tout texte FR.
        # On vérifie le cas positif explicite avec 'kwh'.
        intent = _intent(sensor_type='en')
        response = "🟢 NORMAL — consommation 45.2 kwh ce matin sur le réseau principal."
        report = check_output(response, ['energy_analysis'], intent)
        assert report.has_units is True

    def test_units_not_required_for_non_data(self):
        intent = _intent(query_type='simple', is_data_query=False)
        report = check_output("Une définition.", [], intent)
        assert report.has_units is True

    def test_wm_units_recognized(self):
        intent = _intent(sensor_type='wm')
        response = _data_response(units='m³')
        report = check_output(response, ['wm_analysis'], intent)
        assert report.has_units is True


# ── needs_retry() ─────────────────────────────────────────────────────────────

class TestNeedsRetry:
    def test_good_report_no_retry(self):
        r = QualityReport(tools_called_ok=True, length_ok=True,
                          is_clean=True, has_units=True)
        r.compute_score()
        assert needs_retry(r) is False

    def test_bad_report_needs_retry(self):
        r = QualityReport(tools_called_ok=False)
        r.compute_score()
        assert needs_retry(r) is True

    def test_score_at_threshold_no_retry(self):
        r = QualityReport()
        r.score = RETRY_THRESHOLD  # égal → pas de retry
        assert needs_retry(r) is False

    def test_score_just_below_threshold_retry(self):
        r = QualityReport()
        r.score = RETRY_THRESHOLD - 0.001
        assert needs_retry(r) is True


# ── build_retry_hint() ────────────────────────────────────────────────────────

class TestBuildRetryHint:
    def test_question_preserved_at_end(self):
        r = QualityReport()
        hint = build_retry_hint("Quelle est la température ?", r)
        assert hint.endswith("Quelle est la température ?")

    def test_retry_hint_prefix_present(self):
        r = QualityReport()
        hint = build_retry_hint("question", r)
        assert "[RETRY_HINT:" in hint

    def test_too_short_and_missing_tools_both_in_hint(self):
        r = QualityReport(too_short=True, missing_tools=['energy_analysis'])
        hint = build_retry_hint("question", r)
        assert "energy_analysis" in hint
        assert "table" in hint.lower() or "complete" in hint.lower()

    def test_missing_tools_named_in_hint(self):
        r = QualityReport(missing_tools=['energy_analysis', 'realtime_data'])
        hint = build_retry_hint("question", r)
        assert "energy_analysis" in hint
        assert "realtime_data" in hint

    def test_too_short_adds_table_instruction(self):
        r = QualityReport(too_short=True)
        hint = build_retry_hint("question", r)
        assert "table" in hint.lower() or "complete" in hint.lower()

    def test_hallucination_adds_placeholder_warning(self):
        r = QualityReport(hallucinations=["[value]"])
        hint = build_retry_hint("question", r)
        assert "placeholder" in hint.lower() or "tool" in hint.lower()

    def test_clean_report_still_returns_hint(self):
        r = QualityReport()
        hint = build_retry_hint("question", r)
        assert "[RETRY_HINT:" in hint

    def test_multiple_issues_all_appear(self):
        r = QualityReport(missing_tools=['energy_analysis'], too_short=True)
        hint = build_retry_hint("question", r)
        assert "|" in hint  # séparateur entre les hints
