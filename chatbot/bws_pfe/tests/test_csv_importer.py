"""Tests unitaires — api/pipeline/csv_importer.py (fonctions pures)"""
import pytest
import pandas as pd
from api.pipeline.csv_importer import _reshape_energy_wide_to_long, _resolve_columns


# ── _reshape_energy_wide_to_long() ────────────────────────────────────────────

class TestReshapeEnergyWideToLong:
    def _wide_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            'date':      ['2024-01-01', '2024-01-01'],
            'id_device': ['DEV001',     'DEV002'],
            'cons_en_L1': [10.0, 20.0],
            'cons_en_L2': [5.0,  8.0],
            'cons_en_L3': [3.0,  4.0],
        })

    def test_phase_column_created(self):
        result = _reshape_energy_wide_to_long(self._wide_df())
        assert 'phase' in result.columns

    def test_cons_en_column_created(self):
        result = _reshape_energy_wide_to_long(self._wide_df())
        assert 'cons_en' in result.columns

    def test_row_count_multiplied_by_phases(self):
        result = _reshape_energy_wide_to_long(self._wide_df())
        assert len(result) == 6  # 2 devices × 3 phases

    def test_phases_are_L1_L2_L3(self):
        result = _reshape_energy_wide_to_long(self._wide_df())
        assert set(result['phase'].unique()) == {'L1', 'L2', 'L3'}

    def test_values_preserved_for_L1(self):
        result = _reshape_energy_wide_to_long(self._wide_df())
        l1_rows = result[result['phase'] == 'L1']
        assert set(l1_rows['cons_en'].tolist()) == {10.0, 20.0}

    def test_already_long_returned_unchanged(self):
        df = pd.DataFrame({
            'date':      ['2024-01-01'],
            'id_device': ['DEV001'],
            'phase':     ['L1'],
            'cons_en':   [10.0],
        })
        result = _reshape_energy_wide_to_long(df)
        assert list(result.columns) == list(df.columns)
        assert len(result) == 1

    def test_no_phase_cols_returned_unchanged(self):
        df = pd.DataFrame({'date': ['2024-01-01'], 'value': [5.0]})
        result = _reshape_energy_wide_to_long(df)
        assert 'phase' not in result.columns

    def test_base_cols_preserved(self):
        result = _reshape_energy_wide_to_long(self._wide_df())
        assert 'date' in result.columns
        assert 'id_device' in result.columns

    def test_original_phase_cols_removed(self):
        result = _reshape_energy_wide_to_long(self._wide_df())
        assert 'cons_en_L1' not in result.columns
        assert 'cons_en_L2' not in result.columns

    def test_single_phase_handled(self):
        df = pd.DataFrame({
            'date': ['2024-01-01'],
            'id_device': ['D1'],
            'cons_en_L1': [7.0],
        })
        result = _reshape_energy_wide_to_long(df)
        assert len(result) == 1
        assert result.iloc[0]['phase'] == 'L1'


# ── _resolve_columns() ────────────────────────────────────────────────────────

class TestResolveColumns:
    def _df(self, cols: list) -> pd.DataFrame:
        return pd.DataFrame(columns=cols)

    def test_exact_match(self):
        df = self._df(['date', 'id_device', 'conso'])
        aliases = {
            'date':      ['date', 'timestamp'],
            'id_device': ['id_device', 'device_id'],
        }
        mapping = _resolve_columns(df, aliases)
        assert mapping['date'] == 'date'
        assert mapping['id_device'] == 'id_device'

    def test_alias_fallback(self):
        df = self._df(['timestamp', 'device_id'])
        aliases = {
            'date':      ['date', 'timestamp'],
            'id_device': ['id_device', 'device_id'],
        }
        mapping = _resolve_columns(df, aliases)
        assert mapping['date'] == 'timestamp'
        assert mapping['id_device'] == 'device_id'

    def test_case_insensitive_match(self):
        df = self._df(['Date', 'ID_Device'])
        aliases = {
            'date':      ['date', 'timestamp'],
            'id_device': ['id_device', 'device_id'],
        }
        mapping = _resolve_columns(df, aliases)
        assert mapping.get('date') == 'Date'

    def test_missing_col_not_in_result(self):
        df = self._df(['date'])
        aliases = {
            'date':  ['date'],
            'conso': ['conso', 'volume'],
        }
        mapping = _resolve_columns(df, aliases)
        assert 'conso' not in mapping

    def test_empty_df_returns_empty_mapping(self):
        df = self._df([])
        aliases = {'date': ['date'], 'conso': ['conso']}
        assert _resolve_columns(df, aliases) == {}

    def test_first_alias_wins(self):
        df = self._df(['date', 'timestamp'])
        aliases = {'date': ['date', 'timestamp']}
        mapping = _resolve_columns(df, aliases)
        assert mapping['date'] == 'date'

    def test_multiple_canonicals_all_resolved(self):
        df = self._df(['date', 'id_device', 'conso', 'leak'])
        aliases = {
            'date':      ['date'],
            'id_device': ['id_device'],
            'conso':     ['conso', 'volume'],
            'leak':      ['leak', 'fuite'],
        }
        mapping = _resolve_columns(df, aliases)
        assert len(mapping) == 4
