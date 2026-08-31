"""TDD: Logro Diseño (cresta/pata/berma) en el dashboard Streamlit.

Cubre el clasificador público firmado, el helper puro de UI
(``ui.tabs.dashboard_achievement``) y el cableado en ``dashboard.py``.
"""
import math

import pytest

from core.blast_achievement import W_BERM, W_CREST, W_TOE, classify_achievement_delta
from core.compliance_status import STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE


TOL = {"neg": 1.0, "pos": 0.5}


def _row(delta_crest=None, delta_toe=None, berm_status=STATUS_CUMPLE,
         sector="S1", section="A1", **extra):
    row = {
        "section": section,
        "type": "MATCH",
        "delta_crest": delta_crest,
        "delta_toe": delta_toe,
        "berm_status": berm_status,
        "sector": sector,
        "height_status": STATUS_CUMPLE,
        "angle_status": STATUS_CUMPLE,
        "height_dev": 0.1,
        "angle_dev": 2.0,
        "height_real": 15.0,
        "angle_real": 75.0,
        "berm_real": 6.0,
    }
    row.update(extra)
    return row


class TestClassifierSignature:
    def test_public_in_module_all(self):
        import core.blast_achievement as m

        assert "classify_achievement_delta" in m.__all__

    def test_weights_unchanged(self):
        assert (W_CREST, W_TOE, W_BERM) == (0.4, 0.3, 0.3)

    def test_signed_sides(self):
        assert classify_achievement_delta(-0.5, 1.0, 0.5) == STATUS_CUMPLE
        assert classify_achievement_delta(-0.3, 0.4, 2.0) == STATUS_CUMPLE
        assert classify_achievement_delta(-1.6, 1.0, 0.5) == STATUS_NO_CUMPLE
        assert classify_achievement_delta(0.7, 1.0, 0.5) == STATUS_FUERA

    def test_no_cumple_not_none(self):
        assert classify_achievement_delta(3.0, 1.0, 0.5) == STATUS_NO_CUMPLE

    def test_nonfinite_missing(self):
        for bad in (None, "abc", float("nan"), float("inf"), float("-inf")):
            assert classify_achievement_delta(bad, 1.0, 0.5) is None

    def test_invalid_tolerances_raise(self):
        with pytest.raises(ValueError):
            classify_achievement_delta(0.5, -1.0, 0.5)
        with pytest.raises(ValueError):
            classify_achievement_delta(0.5, 1.0, float("nan"))


class TestAchievementSummary:
    def test_no_evaluable_data_returns_none(self):
        from ui.tabs.dashboard_achievement import build_achievement_summary

        rows = [_row(None, None, berm_status=None),
                {"section": "A2", "type": "MISSING", "delta_crest": None,
                 "delta_toe": None, "berm_status": None, "sector": "S1"}]
        assert build_achievement_summary(rows, TOL) is None
        assert build_achievement_summary([], TOL) is None

    def test_global_weighted_and_strict_pcts(self):
        from ui.tabs.dashboard_achievement import build_achievement_summary

        rows = [
            _row(delta_crest=0.2, delta_toe=0.2, berm_status=STATUS_CUMPLE),
            _row(delta_crest=0.7, delta_toe=None, berm_status=STATUS_CUMPLE,
                 section="A2"),
            _row(delta_crest=5.0, delta_toe=0.2, berm_status="NO CUMPLE",
                 section="A3"),
        ]
        s = build_achievement_summary(rows, TOL)
        assert s is not None
        # fila1: todo CUMPLE -> 1.0; fila2: crest FUERA 0.5, toe None 0, berm 1
        # -> 0.4*0.5+0.3 = 0.5; fila3: crest NO 0, toe 1, berm NO 0 -> 0.3
        assert s["global"] == int(round((1.0 + 0.5 + 0.3) / 3 * 100))
        # strict: crest 1/3 finite deltas CUMPLE; toe 2/2; berm 2/3
        assert s["crest_pct"] == round(1 / 3 * 100)
        assert s["crest_denom"] == 3
        assert s["toe_pct"] == 100
        assert s["toe_denom"] == 2
        assert s["berm_pct"] == round(2 / 3 * 100)
        assert s["berm_denom"] == 3
        assert s["n_evaluable"] == 3

    def test_asymmetric_tolerances_applied(self):
        from ui.tabs.dashboard_achievement import build_achievement_summary

        # deuda -0.7 excede tol_neg 0.5 -> NO_CUMPLE; sobre +0.7 dentro de pos 2.0
        rows = [
            _row(delta_crest=-0.7, delta_toe=None, berm_status=None, section="A1"),
            _row(delta_crest=0.7, delta_toe=None, berm_status=None, section="A2"),
        ]
        s = build_achievement_summary(rows, {"neg": 0.5, "pos": 2.0})
        assert s["crest_pct"] == 50
        assert s["crest_denom"] == 2

    def test_missing_omitted_not_zero(self):
        from ui.tabs.dashboard_achievement import build_achievement_summary

        rows = [_row(delta_crest=None, delta_toe=None, berm_status=STATUS_CUMPLE)]
        s = build_achievement_summary(rows, TOL)
        assert s["crest_denom"] == 0
        assert s["crest_pct"] == 0
        assert s["global"] == 30  # solo berma CUMPLE: crédito ponderado 0.3
        assert s["n_evaluable"] == 1


class TestParameterRows:
    def test_five_rows_with_achievement(self):
        from ui.tabs.dashboard_achievement import build_parameter_breakdown_rows

        rows = [
            _row(delta_crest=0.2, delta_toe=0.2),
            _row(delta_crest=-0.7, delta_toe=1.5, berm_status="NO CUMPLE",
                 height_status="NO CUMPLE", section="A2"),
        ]
        out = build_parameter_breakdown_rows(rows, TOL)
        labels = [r["Parámetro"] for r in out]
        assert labels[:3] == ["Altura de Banco", "Ángulo de Cara", "Ancho de Berma"]
        assert "Desviación Cresta" in labels and "Desviación Pata" in labels
        crest = next(r for r in out if r["Parámetro"] == "Desviación Cresta")
        assert crest["Total Evaluado"] == 2
        assert crest["Cumple"] == 2  # 0.2 dentro de +0.5; -0.7 dentro de -1.0
        assert crest["No Cumple"] == 0
        assert crest["% Cumplimiento"] == "100%"
        # media firmada: (0.2 - 0.7)/2 = -0.25
        assert crest["Promedio Real"].startswith("-0.2")
        toe = next(r for r in out if r["Parámetro"] == "Desviación Pata")
        assert toe["Cumple"] == 1  # 0.2 dentro; 1.5 > 1.5*0.5 → NO_CUMPLE
        assert toe["No Cumple"] == 1

    def test_positive_mean_signed_format(self):
        from ui.tabs.dashboard_achievement import build_parameter_breakdown_rows

        rows = [_row(delta_crest=0.5, delta_toe=0.5, berm_status=None)]
        out = build_parameter_breakdown_rows(rows, TOL)
        crest = next(r for r in out if r["Parámetro"] == "Desviación Cresta")
        assert crest["Promedio Real"] == "+0.5 m"

    def test_nonfinite_deltas_excluded(self):
        from ui.tabs.dashboard_achievement import build_parameter_breakdown_rows

        rows = [_row(delta_crest=float("nan"), delta_toe=float("inf"))]
        out = build_parameter_breakdown_rows(rows, TOL)
        crest = next(r for r in out if r["Parámetro"] == "Desviación Cresta")
        assert crest["Total Evaluado"] == 0


class TestSectorRows:
    def test_two_separate_metrics(self):
        from ui.tabs.dashboard_achievement import build_sector_rows

        rows = [
            _row(delta_crest=0.2, delta_toe=0.2, sector="Norte"),
            _row(delta_crest=0.7, delta_toe=0.2, sector="Norte", section="A2"),
            _row(delta_crest=None, delta_toe=None, berm_status=None,
                 sector="Sur", section="A3"),
        ]
        out = build_sector_rows(rows, TOL)
        by_sector = {r["Sector"]: r for r in out}
        norte = by_sector["Norte"]
        # geotécnico: 6 statuses, todos CUMPLE menos nada -> 100
        assert norte["% Cumplimiento"] == 100.0
        # logro diseño: fila 1 = 100, fila 2 crest FUERA 0.5 -> (0.4+0.5*0.4+0.3+0.3)
        exp = int(round((1.0 * 100 + (0.4 * 0.5 + 0.3 + 0.3) * 100) / 2))
        assert norte["Logro Diseño (%)"] == exp
        assert by_sector["Sur"]["Logro Diseño (%)"] is None

    def test_geotech_semantics_unchanged(self):
        from ui.tabs.dashboard_achievement import build_sector_rows

        rows = [
            _row(delta_crest=0.2, delta_toe=0.2, sector="N"),
            _row(height_status="NO CUMPLE", delta_crest=None, delta_toe=None,
                 berm_status=None, sector="N", section="A2"),
        ]
        out = build_sector_rows(rows, TOL)
        row = out[0]
        # fila2: height NO CUMPLE, angle CUMPLE, berma sin dato
        assert row["Total"] == 5
        assert row["Cumple"] == 4
        assert row["No Cumple"] == 1
        assert row["% Cumplimiento"] == round(4 / 5 * 100, 1)


class TestAchievementHistograms:
    def test_bands_exact_and_finite_only(self):
        from ui.tabs.dashboard_achievement import build_achievement_histograms

        rows = [
            _row(delta_crest=0.3, delta_toe=-0.4),
            _row(delta_crest=float("nan"), delta_toe=None, section="A2"),
            _row(delta_crest=1.1, delta_toe=float("inf"), section="A3"),
        ]
        specs = build_achievement_histograms(rows, TOL)
        assert [s["title"] for s in specs] == ["Δ Cresta (m)", "Δ Pata (m)"]
        assert specs[0]["values"] == [0.3, 1.1]
        assert specs[1]["values"] == [-0.4]
        assert specs[0]["x0"] == -1.0 and specs[0]["x1"] == 0.5

    def test_empty_no_crash(self):
        from ui.tabs.dashboard_achievement import build_achievement_histograms

        specs = build_achievement_histograms([], TOL)
        assert all(s["values"] == [] for s in specs)
        assert specs[0]["x0"] == -1.0 and specs[0]["x1"] == 0.5


class TestDashboardWiring:
    def test_dashboard_uses_helper_and_resolves_tol_once(self):
        import inspect

        import ui.tabs.dashboard as dash

        src = inspect.getsource(dash)
        assert "resolve_achievement_tolerances" in src
        assert "build_achievement_summary" in src
        assert "build_parameter_breakdown_rows" in src
        assert "build_sector_rows" in src
        assert "build_achievement_histograms" in src
        assert "🎯 Logro Diseño — Cresta, Pata y Berma" in src

    def test_render_global_kpi_untouched_signature(self):
        import inspect

        import ui.tabs.dashboard as dash

        sig = inspect.signature(dash._render_global_kpi)
        assert list(sig.parameters) == ["results"]
