"""Tests for ui.tabs.profiles.figure (pure Plotly figure builder)."""
import numpy as np
import plotly.graph_objects as go
import pytest

from ui.tabs.profiles.figure import build_profile_figure


class _FakeSection:
    def __init__(self, name="S01", sector="Test"):
        self.name = name
        self.sector = sector


class _FakeProfile:
    def __init__(self, distances, elevations):
        self.distances = np.asarray(distances, dtype=float)
        self.elevations = np.asarray(elevations, dtype=float)


def _default_config():
    return {"grid_height": 10, "grid_ref": 0, "tolerances": {"bench_height": {"pos": 1.5}}}


class TestBuildProfileFigure:
    def test_returns_figure(self):
        section = _FakeSection()
        pd_prof = _FakeProfile([0.0, 10.0], [100.0, 85.0])
        pt_prof = _FakeProfile([0.0, 10.0], [99.0, 84.0])

        fig = build_profile_figure(0, section, pd_prof, pt_prof, config=_default_config())

        assert isinstance(fig, go.Figure)

    def test_includes_design_and_topo_traces(self):
        section = _FakeSection()
        pd_prof = _FakeProfile([0.0, 10.0], [100.0, 85.0])
        pt_prof = _FakeProfile([0.0, 10.0], [99.0, 84.0])

        fig = build_profile_figure(0, section, pd_prof, pt_prof, config=_default_config())

        names = [t.name for t in fig.data]
        assert "Diseño" in names
        assert "Topografía Real" in names

    def test_sets_title_and_axes(self):
        section = _FakeSection("S42", "SectorA")
        pd_prof = _FakeProfile([0.0, 10.0], [100.0, 85.0])
        pt_prof = _FakeProfile([0.0, 10.0], [99.0, 84.0])

        fig = build_profile_figure(0, section, pd_prof, pt_prof, config=_default_config())

        assert "S42" in fig.layout.title.text
        assert "SectorA" in fig.layout.title.text
        assert fig.layout.xaxis.title.text == "Distancia (m)"
        assert fig.layout.yaxis.title.text == "Elevación (m)"

    def test_sector_areas_appends_traces(self):
        section = _FakeSection()
        pd_prof = _FakeProfile([0.0, 10.0], [100.0, 85.0])
        pt_prof = _FakeProfile([0.0, 10.0], [101.0, 86.0])

        fig = build_profile_figure(
            0, section, pd_prof, pt_prof,
            config=_default_config(),
            show_sector_areas=True,
        )

        assert any("Sector" in (t.name or "") for t in fig.data)
