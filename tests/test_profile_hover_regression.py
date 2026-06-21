"""Regression tests for the UnboundLocalError on 'bt' in the profile
hover tooltip construction.

The bug occurred because 'bt' was only assigned inside the
c_type == 'EXTRA' branch, but used unconditionally further down.
This test ensures that the function builds hover data correctly when
bench_real is missing (e.g. MISSING-type comparisons) without
raising.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

REPO = Path("/home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02")
sys.path.insert(0, str(REPO))

from core.param_extractor import BenchParams
from ui.tabs.profiles import _build_profile_figure


def _make_bench_params(bench_number, crest_d=0.0, crest_e=100.0,
                       toe_d=10.0, toe_e=85.0, face_angle=70.0,
                       berm_width=8.0, bench_height=15.0):
    return BenchParams(
        bench_number=bench_number,
        crest_distance=crest_d,
        crest_elevation=crest_e,
        toe_distance=toe_d,
        toe_elevation=toe_e,
        bench_height=bench_height,
        face_angle=face_angle,
        berm_width=berm_width,
    )


class _FakeSection:
    def __init__(self, name, sector):
        self.name = name
        self.sector = sector


class TestProfileHoverRegression:
    def test_build_profile_with_missing_bench_real(self, monkeypatch):
        """Reproduces the UnboundLocalError bug when bench_real is None.

        The original code accessed 'bt.bench_height' unconditionally
        inside the MATCH branch, but 'bt' was only assigned in the
        EXTRA branch. The fix assigns bt = comp.get('bench_real')
        at the top of the MATCH branch.
        """
        bd = _make_bench_params(1)
        st_session = {
            "comparison_results": [
                {
                    "section": "S01",
                    "type": "MATCH",
                    "bench_design": bd,
                    "bench_real": None,
                    "delta_crest": 0.5,
                    "delta_toe": -0.3,
                    "height_status": "CUMPLE",
                    "angle_status": "CUMPLE",
                    "berm_status": "CUMPLE",
                }
            ],
            "params_topo": [type("R", (), {"benches": [bd]})()],
            "reconciled_design": [],
            "reconciled_topo": [],
            "area_fill_design": [],
        }
        for k, v in st_session.items():
            monkeypatch.setitem(type(st := type("S", (), {})()).__dict__, k, v) if False else None
        import streamlit as st
        for k, v in st_session.items():
            st.session_state[k] = v

        pd_prof = type("P", (), {"distances": np.array([0.0, 10.0]),
                                  "elevations": np.array([100.0, 85.0])})()
        pt_prof = type("P", (), {"distances": np.array([0.0, 10.0]),
                                  "elevations": np.array([99.5, 84.7])})()
        section = _FakeSection("S01", "Phase20")

        config = {"grid_height": 10, "grid_ref": 0}

        fig = _build_profile_figure(
            i=0, section=section, pd_prof=pd_prof, pt_prof=pt_prof,
            show_areas=False, show_spill_areas=False, show_semaphore=False,
            show_reconciled=False, show_pozos=False, blast_tolerance=None,
            config=config, show_sector_areas=False,
        )
        assert isinstance(fig, go.Figure)

    def test_build_profile_with_extra_bench(self, monkeypatch):
        """The 'EXTRA' branch sets bt and uses it — must still work."""
        bt = _make_bench_params(99, crest_d=20.0, crest_e=110.0,
                                toe_d=30.0, toe_e=95.0, face_angle=65.0)
        import streamlit as st
        st.session_state["comparison_results"] = [
            {
                "section": "S02",
                "type": "EXTRA",
                "bench_real": bt,
            }
        ]
        st.session_state["params_topo"] = [
            type("R", (), {"benches": [bt]})()
        ]
        st.session_state["reconciled_design"] = []
        st.session_state["reconciled_topo"] = []
        st.session_state["area_fill_design"] = []

        pd_prof = type("P", (), {"distances": np.array([0.0, 20.0]),
                                  "elevations": np.array([100.0, 85.0])})()
        pt_prof = type("P", (), {"distances": np.array([0.0, 30.0]),
                                  "elevations": np.array([100.0, 110.0])})()
        section = _FakeSection("S02", "Phase20")

        config = {"grid_height": 10, "grid_ref": 0}

        fig = _build_profile_figure(
            i=0, section=section, pd_prof=pd_prof, pt_prof=pt_prof,
            show_areas=False, show_spill_areas=False, show_semaphore=False,
            show_reconciled=False, show_pozos=False, blast_tolerance=None,
            config=config, show_sector_areas=False,
        )
        assert isinstance(fig, go.Figure)