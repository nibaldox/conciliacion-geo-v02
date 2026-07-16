"""Tests for ui.tabs.profiles.traces (pure Plotly trace builders)."""
import numpy as np
import plotly.graph_objects as go
import pytest

from ui.tabs.profiles.traces import (
    add_area_traces,
    add_bench_annotations,
    add_sector_areas_traces,
)


class _FakeProfile:
    def __init__(self, distances, elevations):
        self.distances = np.asarray(distances, dtype=float)
        self.elevations = np.asarray(elevations, dtype=float)


class TestTraceBuilders:
    def test_add_area_traces_appends_over_and_under(self):
        fig = go.Figure()
        d_i = np.array([0.0, 5.0, 10.0])
        z_ref = np.array([100.0, 95.0, 90.0])
        z_eval = np.array([101.0, 94.0, 89.0])

        add_area_traces(fig, d_i, z_ref, z_eval, a_over=1.0, a_under=2.0)

        assert len(fig.data) == 2
        fillcolors = [t.fillcolor for t in fig.data]
        assert any("255,0,0" in str(c) for c in fillcolors)
        assert any("0,0,255" in str(c) for c in fillcolors)

    def test_add_sector_areas_traces_appends_filled_traces(self):
        fig = go.Figure()
        pd_prof = _FakeProfile([0.0, 10.0], [100.0, 85.0])
        pt_prof = _FakeProfile([0.0, 10.0], [101.0, 86.0])
        d_i = np.array([0.0, 10.0])
        z_ref = np.array([100.0, 85.0])
        z_eval = np.array([101.0, 86.0])

        add_sector_areas_traces(fig, pd_prof, pt_prof, d_i, z_ref, z_eval, a_over=5.0, a_under=0.0)

        assert len(fig.data) >= 1
        assert all(t.fill == "toself" for t in fig.data)

    def test_add_bench_annotations_appends_info_trace(self):
        fig = go.Figure()
        d_i = np.array([0.0, 10.0])
        z_ref = np.array([100.0, 85.0])
        z_eval = np.array([101.0, 86.0])
        bench_design = type("B", (), {
            "crest_distance": 10.0,
            "crest_elevation": 100.0,
            "toe_distance": 0.0,
            "toe_elevation": 85.0,
            "berm_width": 5.0,
            "bench_number": 1,
        })()
        bench_real = type("B", (), {
            "bench_height": 15.0,
            "face_angle": 70.0,
        })()
        sec_comps = [{
            "type": "MATCH",
            "bench_design": bench_design,
            "bench_real": bench_real,
            "delta_crest": 0.5,
            "delta_toe": -0.3,
            "height_status": "CUMPLE",
            "angle_status": "CUMPLE",
            "berm_status": "CUMPLE",
        }]

        add_bench_annotations(fig, sec_comps, d_i, z_ref, z_eval)

        assert len(fig.data) == 1
        assert fig.data[0].name == "Info Bancos"
