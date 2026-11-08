"""Nullable berma on the Profiles tab traces.

A bench without a real berm must not raise (``None``/``NaN <= 0``) and must
not draw a fake berm indicator.
"""
import numpy as np
import plotly.graph_objects as go
import pytest

from ui.tabs.profiles.traces import add_bench_annotations, add_berm_width_indicators


def _bench_design(berm_width):
    return type("B", (), {
        "crest_distance": 10.0,
        "crest_elevation": 100.0,
        "toe_distance": 0.0,
        "toe_elevation": 85.0,
        "berm_width": berm_width,
        "bench_number": 1,
    })()


def _bench_real():
    return type("B", (), {
        "bench_height": 15.0,
        "face_angle": 70.0,
    })()


def _comp(berm_width):
    return {
        "type": "MATCH",
        "bench_design": _bench_design(berm_width),
        "bench_real": _bench_real(),
        "delta_crest": 0.5,
        "delta_toe": -0.3,
        "height_status": "CUMPLE",
        "angle_status": "CUMPLE",
        "berm_status": "-",
    }


def _topo_bench(berm_width):
    return type("B", (), {
        "toe_distance": 5.0,
        "crest_distance": 12.0,
        "toe_elevation": 85.0,
        "crest_elevation": 100.0,
        "berm_width": berm_width,
    })()


def _bench_and_comps(berm_width):
    bench = _topo_bench(berm_width)
    return bench, [{
        "type": "MATCH",
        "bench_design": _bench_design(berm_width),
        "bench_real": bench,
        "delta_crest": 0.5,
        "delta_toe": -0.3,
        "height_status": "CUMPLE",
        "angle_status": "CUMPLE",
        "berm_status": "-",
    }]


class TestBenchAnnotationsNullableBerm:
    @pytest.mark.parametrize("berm", [None, float("nan"), float("inf")])
    def test_missing_design_berm_does_not_raise(self, berm):
        fig = go.Figure()
        add_bench_annotations(
            fig, [_comp(berm)],
            np.array([0.0, 10.0]), np.array([100.0, 85.0]), np.array([101.0, 86.0]),
        )
        assert len(fig.data) == 1
        assert fig.data[0].name == "Info Bancos"

    def test_finite_design_berm_keeps_trace(self):
        fig = go.Figure()
        add_bench_annotations(
            fig, [_comp(5.0)],
            np.array([0.0, 10.0]), np.array([100.0, 85.0]), np.array([101.0, 86.0]),
        )
        assert len(fig.data) == 1


class TestBermWidthIndicatorsNullable:
    @pytest.mark.parametrize("berm", [None, float("nan"), float("inf")])
    def test_missing_berm_skips_annotation(self, berm):
        bench, comps = _bench_and_comps(berm)
        fig = go.Figure()
        add_berm_width_indicators(fig, [bench], comps)
        assert list(fig.layout.annotations) == []
        assert list(fig.layout.shapes) == []

    def test_zero_berm_skips_annotation(self):
        bench, comps = _bench_and_comps(0.0)
        fig = go.Figure()
        add_berm_width_indicators(fig, [bench], comps)
        assert list(fig.layout.annotations) == []

    def test_finite_berm_annotates(self):
        bench, comps = _bench_and_comps(5.0)
        fig = go.Figure()
        add_berm_width_indicators(fig, [bench], comps)
        assert len(fig.layout.annotations) == 1
        assert fig.layout.annotations[0].text == "B1=5.0m"
