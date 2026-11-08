import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from ui.modulo_tronadura.figures import _build_collar_customdata, build_color_options, build_energy_grid, build_pf_halo_rings_3d_trace
from ui.modulo_tronadura.enrichment import enrich_processed


def test_hover_missing_is_not_zero_and_principal_status_is_visible():
    df = pd.DataFrame({"Len": [np.nan, 0.0], "pf_voronoi_bench_g_per_ton": [np.nan, 0.0], "pf_voronoi_bench_status": ["MISSING_FOOTPRINT", "VALID"]})
    data = _build_collar_customdata(df, None)
    assert data[0, 4] == "sin dato"
    assert data[1, 4] == "0.00"
    assert "sin huella de malla" in str(data[0])
    assert any("principal" in x.lower() for x in build_color_options(df))


def test_halo_omits_missing_pf_instead_of_drawing_zero():
    df = pd.DataFrame({"X": [0., 1.], "Y": [0., 1.], "Z_collar": [1., 1.], "X_toe": [0., 1.], "Y_toe": [0., 1.], "Z_toe": [0., 0.], "pf": [np.nan, 0.]})
    trace = build_pf_halo_rings_3d_trace(df, "pf", levels=2, ring_points=16)
    assert len(trace.x) == 2 * 3 * 16
    assert all(value == 0 for value in trace.line.color)


def test_enrichment_preserves_core_principal_and_deck_energy():
    df = pd.DataFrame({"Len": [10.], "Kilos_Cargados_real": [10.], "pf_voronoi_bench_g_per_ton": [123.], "pf_voronoi_bench_status": ["VALID"], "energy_mj": [20.], "energy_coverage_kg_fraction": [1.]})
    result = enrich_processed(df)
    assert result.loc[0, "pf_voronoi_bench_g_per_ton"] == 123.
    assert result.loc[0, "energy_mj"] == 20.
    assert result.loc[0, "energy_coverage_kg_fraction"] == 1.


def test_idw_omits_missing_charge_instead_of_treating_as_zero():
    df = pd.DataFrame({"X": [0., 10.], "Y": [0., 10.], "Z_collar": [1., 1.], "X_toe": [0., 10.], "Y_toe": [0., 10.], "Z_toe": [0., 0.], "kg": [10., np.nan]})
    actual = build_energy_grid(df, "kg", 2, 2, 2, 5.)
    expected = build_energy_grid(df.iloc[:1], "kg", 2, 2, 2, 5.)
    assert np.allclose(actual["X"], expected["X"])
    assert np.allclose(actual["Energy_kg_m2"], expected["Energy_kg_m2"])


def test_consolidation_and_energy_render_synthetic():
    app = AppTest.from_string('''
import pandas as pd
from ui.modulo_tronadura.upload import _render_consolidation_report
from ui.modulo_tronadura.tabular import render_metric_definitions
_render_consolidation_report({"rows_in": 4, "holes_out": 2, "exact_copies_removed": 1, "copies_by_malla": {"M1": 1}, "holes_with_decks": 1, "deck_rows_merged": 1, "conflicts": [{"reason": "geometry"}]})
render_metric_definitions(pd.DataFrame({"energy_mj": [None, 10.0], "energy_coverage_kg_fraction": [0.5, 1.0], "pf_voronoi_bench_status": ["MISSING_FOOTPRINT", "VALID"]}))
''').run()
    assert not app.exception
    text = " ".join([x.value for x in app.markdown] + [x.label for x in app.expander])
    for term in ("consolidación", "M1", "cobertura", "sin huella de malla", "por metro perforado", "por metro de columna cargada", "Q/(B*S*H)"):
        assert term.lower() in text.lower()
