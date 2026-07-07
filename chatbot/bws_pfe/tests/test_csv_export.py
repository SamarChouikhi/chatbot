"""Tests unitaires — mcp_client/csv_export.py"""
import pytest
from mcp_client.csv_export import _extract_csv_text, save_csv, CSV_TMP_DIR


# ── _extract_csv_text() ───────────────────────────────────────────────────────

class TestExtractCsvText:
    def test_explicit_csv_block(self):
        text = "Données :\n```csv\ndate,valeur\n2025-01-01,22.5\n2025-01-02,23.0\n```"
        result = _extract_csv_text(text)
        assert result is not None
        assert "date,valeur" in result
        assert "22.5" in result

    def test_explicit_block_case_insensitive_tag(self):
        text = "```CSV\ndate,valeur\n2025-01-01,22.5\n```"
        assert _extract_csv_text(text) is not None

    def test_no_csv_returns_none(self):
        text = "Réponse sans données tabulaires."
        assert _extract_csv_text(text) is None

    def test_implicit_csv_data_not_extracted(self):
        # Données CSV sans bloc explicite → ignorées (export à la demande uniquement)
        text = "\n".join([
            "date,device,valeur",
            "2025-01-01,SENSOR-01,22.5",
            "2025-01-02,SENSOR-01,23.0",
            "2025-01-03,SENSOR-01,21.8",
        ])
        assert _extract_csv_text(text) is None

    def test_only_explicit_block_extracted_when_mixed(self):
        # Seul le bloc ```csv est extrait même si du CSV implicite est présent
        csv_block = "```csv\nid,name\n1,Alpha\n2,Beta\n```"
        implicit_data = "a,b,c\n1,2,3\n4,5,6\n7,8,9\n10,11,12"
        text = implicit_data + "\n" + csv_block
        result = _extract_csv_text(text)
        assert "id,name" in result

    def test_result_stripped(self):
        text = "```csv\n  date,valeur  \n2025-01-01,22.5\n```"
        result = _extract_csv_text(text)
        assert result == result.strip()


# ── save_csv() ────────────────────────────────────────────────────────────────

class TestSaveCsv:
    def test_returns_none_when_no_csv(self):
        assert save_csv("Réponse sans données CSV.") is None

    def test_returns_tuple_file_id_and_name(self):
        text = "```csv\ndate,valeur\n2025-01-01,22.5\n2025-01-02,23.0\n```"
        result = save_csv(text)
        assert result is not None
        file_id, filename = result
        assert len(file_id) == 36       # UUID v4
        assert filename.endswith('.csv')

    def test_file_written_to_tmp_dir(self):
        text = "```csv\ndate,valeur\n2025-01-01,22.5\n2025-01-02,23.0\n```"
        result = save_csv(text)
        assert result is not None
        file_id, _ = result
        path = CSV_TMP_DIR / f'{file_id}.csv'
        assert path.exists()
        path.unlink()

    def test_custom_label_appears_in_filename(self):
        text = "```csv\ndate,valeur\n2025-01-01,22.5\n2025-01-02,23.0\n```"
        _, filename = save_csv(text, label='energie')
        assert 'energie' in filename

    def test_default_label_in_filename(self):
        text = "```csv\ndate,valeur\n2025-01-01,22.5\n2025-01-02,23.0\n```"
        _, filename = save_csv(text)
        assert 'rapport' in filename

    def test_file_has_utf8_bom(self):
        text = "```csv\ndate,zone\n2025-01-01,Salle réunion\n2025-01-02,Bureau\n```"
        result = save_csv(text)
        assert result is not None
        file_id, _ = result
        path = CSV_TMP_DIR / f'{file_id}.csv'
        raw = path.read_bytes()
        assert raw[:3] == b'\xef\xbb\xbf'  # BOM utf-8-sig pour Excel
        path.unlink()

    def test_csv_content_in_file(self):
        text = "```csv\ndate,valeur\n2025-01-01,99.9\n2025-01-02,88.8\n```"
        file_id, _ = save_csv(text)
        path = CSV_TMP_DIR / f'{file_id}.csv'
        content = path.read_text(encoding='utf-8-sig')
        assert "99.9" in content
        path.unlink()

    def test_implicit_csv_data_not_saved(self):
        # Sans bloc ```csv explicite → aucun fichier généré
        text = "\n".join([
            "date,device,valeur",
            "2025-01-01,SENSOR-01,22.5",
            "2025-01-02,SENSOR-01,23.0",
            "2025-01-03,SENSOR-01,21.8",
        ])
        assert save_csv(text) is None
