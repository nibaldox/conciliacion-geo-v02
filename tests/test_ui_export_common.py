"""Tests for shared helpers in ui.tabs.export.common."""
import sys
from unittest.mock import MagicMock

import pytest

from ui.tabs.export import common


class FakeSessionState:
    def __init__(self, **kwargs):
        self._data = kwargs

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getattr__(self, key):
        if key.startswith('_'):
            raise AttributeError(key)
        return self._data.get(key)


class TestBuildSectionStatusMap:
    def test_all_cumple(self):
        comps = [
            {'section': 'S1', 'height_status': 'CUMPLE', 'angle_status': 'CUMPLE', 'berm_status': 'CUMPLE'},
        ]
        assert common._build_section_status_map(comps) == {'S1': 'CUMPLE'}

    def test_fuera_tolerancia(self):
        comps = [
            {'section': 'S1', 'height_status': 'FUERA DE TOLERANCIA', 'angle_status': 'CUMPLE', 'berm_status': 'CUMPLE'},
        ]
        assert common._build_section_status_map(comps) == {'S1': 'FUERA DE TOLERANCIA'}

    def test_no_cumple_overrides_fuera(self):
        comps = [
            {'section': 'S1', 'height_status': 'FUERA DE TOLERANCIA', 'angle_status': 'NO CUMPLE', 'berm_status': 'CUMPLE'},
        ]
        assert common._build_section_status_map(comps) == {'S1': 'NO CUMPLE'}

    def test_multiple_sections(self):
        comps = [
            {'section': 'S1', 'height_status': 'CUMPLE', 'angle_status': 'CUMPLE', 'berm_status': 'CUMPLE'},
            {'section': 'S2', 'height_status': 'NO CUMPLE', 'angle_status': 'CUMPLE', 'berm_status': 'CUMPLE'},
        ]
        result = common._build_section_status_map(comps)
        assert result['S1'] == 'CUMPLE'
        assert result['S2'] == 'NO CUMPLE'


class TestProfileTo3D:
    def test_converts_profile_to_3d_points(self):
        distances = [0.0, 1.0, 2.0]
        elevations = [10.0, 11.0, 12.0]
        direction = (1.0, 0.0)
        result = common._profile_to_3d(distances, elevations, 5.0, 6.0, direction)
        expected = [(5.0, 6.0, 10.0), (6.0, 6.0, 11.0), (7.0, 6.0, 12.0)]
        assert result == expected


class TestCreateDxfLayers:
    def test_creates_expected_layers(self):
        doc = MagicMock()
        doc.layers = MagicMock()
        common._create_dxf_layers(doc)
        calls = doc.layers.add.call_args_list
        names = [call.args[0] for call in calls]
        assert names == [
            'DISEÑO_CUMPLE', 'DISEÑO_NO_CUMPLE', 'DISEÑO_FUERA_TOL',
            'TOPO_CUMPLE', 'TOPO_NO_CUMPLE', 'TOPO_FUERA_TOL',
            'CONCILIADO_DISEÑO', 'CONCILIADO_TOPO', 'ETIQUETAS',
        ]


class TestGetProfilePair:
    def test_returns_cached_profile(self, monkeypatch):
        class FakeSection:
            name = 'S1'
        class FakeProfile:
            pass
        pd_prof = FakeProfile()
        pt_prof = FakeProfile()

        fake_st = MagicMock()
        fake_st.session_state = FakeSessionState(
            profiles_design=[pd_prof],
            profiles_topo=[pt_prof],
            processed_sections=[FakeSection()],
        )
        monkeypatch.setitem(sys.modules, 'streamlit', fake_st)

        result = common._get_profile_pair('S1')
        assert result == (pd_prof, pt_prof)

    def test_falls_back_to_fresh_cut(self, monkeypatch):
        class FakeSection:
            name = 'S1'
            origin = (0.0, 0.0)
            azimuth = 0.0
        class FakeProfile:
            pass
        pd_prof = FakeProfile()
        pt_prof = FakeProfile()

        fake_st = MagicMock()
        fake_st.session_state = FakeSessionState(
            profiles_design=[],
            profiles_topo=[],
            processed_sections=[],
            mesh_design='mesh_d',
            mesh_topo='mesh_t',
            sections=[FakeSection()],
        )
        monkeypatch.setitem(sys.modules, 'streamlit', fake_st)
        monkeypatch.setattr(common, 'cut_both_surfaces', lambda d, t, s: (pd_prof, pt_prof))

        result = common._get_profile_pair('S1')
        assert result == (pd_prof, pt_prof)

    def test_returns_none_when_no_match(self, monkeypatch):
        fake_st = MagicMock()
        fake_st.session_state = FakeSessionState(
            profiles_design=[],
            profiles_topo=[],
            processed_sections=[],
            mesh_design=None,
            mesh_topo=None,
            sections=[],
        )
        monkeypatch.setitem(sys.modules, 'streamlit', fake_st)

        result = common._get_profile_pair('S1')
        assert result == (None, None)


class TestGetFilteredComparisons:
    def test_returns_empty_when_no_comps(self, monkeypatch):
        fake_st = MagicMock()
        fake_st.session_state = FakeSessionState(comparison_results=[])
        monkeypatch.setitem(sys.modules, 'streamlit', fake_st)
        assert common._get_filtered_comparisons() == []

    def test_applies_filters(self, monkeypatch):
        fake_st = MagicMock()
        fake_st.session_state = FakeSessionState(comparison_results=[{'section': 'S1'}])
        monkeypatch.setitem(sys.modules, 'streamlit', fake_st)
        monkeypatch.setitem(
            sys.modules, 'ui.filters', MagicMock(
                collect_active_filters_from_session_state=lambda: {'sector': 'A'},
                apply_comparison_filters=lambda comps, filters: comps,
            )
        )
        assert common._get_filtered_comparisons() == [{'section': 'S1'}]
