"""Streamlit wiring tests for configurable signed achievement tolerances.

Covers:
- sidebar exposes crest_toe_deviation (neg/pos) with stable keys
- compute_malla_correlation propagates achievement tolerances to core
- the audit caption next to 'Logro Diseño Global' shows effective limits
"""

import ast
import math
from pathlib import Path

import pandas as pd
import pytest

from ui.tabs.blast_correlation import data as bc_data

UI_DIR = Path(__file__).resolve().parents[1] / "ui"
SIDEBAR_PATH = UI_DIR / "sidebar.py"
RENDERERS_PATH = UI_DIR / "tabs" / "blast_correlation" / "renderers.py"


def _section_rows():
    class _Sec:
        def __init__(self, name):
            self.name = name
            self.sector = "S"
            self.origin = (0.0, 0.0, 0.0)
            self.azimuth = 0.0
            self.length = 10.0

    return [_Sec("S1")]


class TestSidebarSignedTolerances:
    def test_sidebar_has_both_number_inputs_with_keys(self):
        src = SIDEBAR_PATH.read_text(encoding="utf-8")
        assert "'Deuda cresta/pata: Tol. (-) m'" in src or '"Deuda cresta/pata: Tol. (-) m"' in src
        assert (
            "'Sobre-excavación cresta/pata: Tol. (+) m'" in src
            or '"Sobre-excavación cresta/pata: Tol. (+) m"' in src
        )
        assert 'key="tol_crest_toe_neg"' in src
        assert 'key="tol_crest_toe_pos"' in src

    def test_sidebar_inputs_use_config_defaults_zero_min(self):
        src = SIDEBAR_PATH.read_text(encoding="utf-8")
        assert "TOLERANCES.crest_toe_deviation['neg']" in src
        assert "TOLERANCES.crest_toe_deviation['pos']" in src
        assert "min_value=0.0" in src

    def test_sidebar_config_includes_crest_toe_deviation(self):
        src = SIDEBAR_PATH.read_text(encoding="utf-8")
        assert "'crest_toe_deviation'" in src


class TestComputeMallaCorrelationPropagation:
    @staticmethod
    def _blast_df():
        return pd.DataFrame(
            {
                "Pozo": ["P01"],
                "Kilos_Cargados_real": [100.0],
                "X": [0.0],
                "Y": [0.0],
                "Z_collar": [150.0],
                "Z_toe": [140.0],
                "Len": [10.0],
                "Nombre_Malla_Original": ["M1"],
            }
        )

    def test_accepts_achievement_tolerances_kwarg_and_propagates(self):
        from core.blast_achievement import compute_design_achievement_score
        from ui.tabs.blast_correlation import data as data_mod

        captured = {}

        orig = data_mod.compute_design_achievement_score

        def spy(*args, **kwargs):
            captured.update(kwargs)
            return orig(*args, **kwargs)

        data_mod.compute_design_achievement_score = spy
        try:
            blast_df = self._blast_df()
            comps = [
                {"section": "S1", "delta_crest": -1.2, "delta_toe": 0.0, "berm_status": "CUMPLE"},
            ]
            tolerances = {"neg": 1.5, "pos": 0.8}
            _, score = data_mod.compute_malla_correlation(
                _section_rows(),
                blast_df,
                pd.DataFrame({"section": []}),
                15.0,
                "Kilos_Cargados_real",
                "Nombre_Malla_Original",
                comps,
                None,
                achievement_tolerances=tolerances,
            )
        finally:
            data_mod.compute_design_achievement_score = orig

        # exactly the same dict values propagated, no invented defaults
        assert captured.get("crest_tolerance_neg_m") == 1.5
        assert captured.get("crest_tolerance_pos_m") == 0.8
        assert captured.get("toe_tolerance_neg_m") == 1.5
        assert captured.get("toe_tolerance_pos_m") == 0.8

    def test_default_callers_still_work(self):
        blast_df = self._blast_df()
        df_out, score = bc_data.compute_malla_correlation(
            _section_rows(),
            blast_df,
            pd.DataFrame({"section": []}),
            15.0,
            "Kilos_Cargados_real",
            "Nombre_Malla_Original",
            [],
        )
        assert score == 0


class TestAchievementCaption:
    def test_format_achievement_caption_default(self):
        from ui.tabs.blast_correlation.renderers import format_achievement_caption

        caption = format_achievement_caption({"neg": 1.0, "pos": 1.0})
        assert caption == (
            "Criterio cresta/pata: deuda hasta −1.0 m · sobre-excavación hasta +1.0 m"
        )

    def test_format_achievement_caption_effective_values(self):
        from ui.tabs.blast_correlation.renderers import format_achievement_caption

        caption = format_achievement_caption({"neg": 1.5, "pos": 0.8})
        assert caption == (
            "Criterio cresta/pata: deuda hasta −1.5 m · sobre-excavación hasta +0.8 m"
        )

    def test_caption_source_renders_metric_and_caption(self):
        src = RENDERERS_PATH.read_text(encoding="utf-8")
        assert 'st.metric("Logro Diseño Global"' in src
        assert "format_achievement_caption" in src
        assert "crest_toe_deviation" in src
