import api.routers.export as export
from core.report_figures_heatmap import heatmap_summary


def test_sections_restrict_cells_to_union_of_influence_intervals():
    entry = {'sector': 'A', 'payload': {'section_names': ['S1', 'S2', 'S3', 'S4'], 'section_stations_m': [0, 10, 20, 30], 'cells': [{'station_m': x, 'elevation_m': 100, 'deviation_m': x, 'category': 'overbreak_severe'} for x in [2, 8, 12, 18, 22, 28]]}}
    restricted, note = export._restrict_heatmap_sections(entry, {'S2', 'S4'})
    assert [c['station_m'] for c in restricted['payload']['cells']] == [8, 12, 28]
    assert heatmap_summary(restricted['payload']).max_over['deviation_m'] == 28
    assert 'secciones del informe' in restricted['scope_note']
    assert note is None


def test_restricted_figure_zooms_to_scoped_cells():
    from core.report_figures_heatmap import _build_heatmap_figure
    import matplotlib.pyplot as plt
    entry = {'sector': 'A', 'payload': {'section_names': ['S1', 'S2', 'S3'], 'section_stations_m': [0, 100, 200], 'cells': [{'station_m': 100, 'elevation_m': 100, 'deviation_m': 1, 'category': 'within_tolerance'}]}}
    scoped, _ = export._restrict_heatmap_sections(entry, {'S2'})
    fig = _build_heatmap_figure(scoped['payload'])
    left, right = fig.axes[0].get_xlim()
    plt.close(fig)
    assert right - left < 20


def test_position_note_identifies_section_restriction():
    from core.report_texts import heatmap_position_note
    summary = heatmap_summary({'report_station_ranges': [(0, 2)], 'cells': [{'station_m': 1, 'elevation_m': 100, 'deviation_m': 3, 'category': 'overbreak_severe'}]})
    assert 'en las secciones del informe' in heatmap_position_note(summary)


def test_singular_profile_uses_singular_verb():
    from types import SimpleNamespace
    from core.report_texts import headline_text
    data = SimpleNamespace(profile_counts={'CUMPLE': 0, 'FUERA': 0, 'NO_CUMPLE': 1, 'UNKNOWN': 0}, headline={})
    assert '0 de 1 perfil cumple;' in headline_text(data)


def test_noncontiguous_levels_exclude_intermediate_cells():
    from types import SimpleNamespace
    from core.report_figures_heatmap import level_window_from_geometry
    geometry = [{'view_window': (0, 1, 0, 1), 'params_design': SimpleNamespace(benches=[SimpleNamespace(toe_elevation=100, crest_elevation=105), SimpleNamespace(toe_elevation=120, crest_elevation=125)])}]
    payload = {'cells': [{'station_m': 1, 'elevation_m': z, 'deviation_m': z, 'category': 'overbreak_severe'} for z in (102, 110, 122)]}
    summary = heatmap_summary(payload, level_window=level_window_from_geometry(geometry))
    assert summary.n_cells == 2
    assert summary.median_m == 112


def test_no_cells_in_scope_omits_heatmap():
    entry = {'sector': 'A', 'payload': {'section_names': ['S1', 'S2'], 'section_stations_m': [0, 10], 'cells': [{'station_m': 9}]}}
    restricted, note = export._restrict_heatmap_sections(entry, {'S1'})
    assert restricted is None
    assert 'sin celdas' in note.lower()



def test_empty_effective_window_omits_figure():
    from core.report_figures_heatmap import LevelWindow, heatmap_page_png
    window = LevelWindow([(3095, 3104), (3120, 3125)])
    payload = {"cells": [{"station_m": 1, "elevation_m": 3110, "deviation_m": 1, "category": "within_tolerance"}]}
    assert heatmap_page_png(payload, level_window=window) is None


def test_restrict_sections_preserves_existing_scope_note():
    entry = {"sector": "A", "scope_note": "Nota anterior.", "payload": {"section_names": ["S1", "S2"], "section_stations_m": [0, 10], "cells": [{"station_m": 0}]}}
    scoped, _ = export._restrict_heatmap_sections(entry, {"S1"})
    assert "Nota anterior." in scoped["scope_note"]
    assert "secciones del informe" in scoped["scope_note"]
