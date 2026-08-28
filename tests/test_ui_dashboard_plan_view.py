"""Tests for ui.tabs.dashboard_plan_view (compliance plan view helpers)."""
import numpy as np
import plotly.graph_objects as go
import pytest
import trimesh

from core.section_cutter import SectionLine
from ui.tabs.dashboard_plan_view import (
    build_plan_view_figure,
    compute_section_status,
    select_plan_mesh,
)


def _synthetic_topo():
    return trimesh.creation.box(extents=[10.0, 10.0, 5.0])


def _sections():
    return [
        SectionLine(name="S01", origin=np.array([0.0, 0.0]), azimuth=0.0,
                    length=20.0, sector="Norte"),
        SectionLine(name="S02", origin=np.array([0.0, 5.0]), azimuth=90.0,
                    length=20.0, sector="Sur"),
    ]


def _status():
    return {
        "S01": {"score": 82.0, "cumple": True},
        "S02": {"score": 45.0, "cumple": False},
    }


def _surface_traces(fig):
    return [t for t in fig.data if t.type == "mesh3d"]


def _profile_traces(fig):
    return [t for t in fig.data if t.type == "scatter3d"
            and t.hovertemplate and "Puntaje de logro" in t.hovertemplate]


def _legend_traces(fig):
    return [t for t in fig.data if t.showlegend]


# ---------------------------------------------------------------------------
# Surface: Mesh3d from the real topo STL
# ---------------------------------------------------------------------------

class TestSurfaceTrace:
    def test_surface_is_mesh3d_with_face_indices(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        surfaces = _surface_traces(fig)
        assert len(surfaces) == 1
        mesh = surfaces[0]
        assert len(mesh.x) == 8
        assert mesh.i is not None and len(mesh.i) == 12
        assert mesh.j is not None and len(mesh.j) == 12
        assert mesh.k is not None and len(mesh.k) == 12

    def test_no_contour_or_heatmap_traces(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        types = [t.type for t in fig.data]
        assert "contour" not in types
        assert "heatmap" not in types

    def test_mesh_intensity_is_elevation(self):
        mesh = _synthetic_topo()
        fig = build_plan_view_figure(mesh, _sections(), _status())

        surface = _surface_traces(fig)[0]
        np.testing.assert_allclose(surface.intensity, mesh.vertices[:, 2])

    def test_mesh_hover_labels_and_hidden_scale_legend(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        surface = _surface_traces(fig)[0]
        assert "Este" in surface.hovertemplate
        assert "Norte" in surface.hovertemplate
        assert "Elevación" in surface.hovertemplate
        assert surface.showscale is False
        assert surface.showlegend is False
        assert surface.opacity == 1.0

    def test_mesh_has_colorscale_and_lighting(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        surface = _surface_traces(fig)[0]
        assert surface.colorscale is not None
        assert len(surface.colorscale) >= 2
        assert surface.lighting is not None


# ---------------------------------------------------------------------------
# Camera / layout: exact top-down orthographic plan view
# ---------------------------------------------------------------------------

class TestCameraAndLayout:
    def test_top_down_orthographic_camera(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        cam = fig.layout.scene.camera
        assert cam.projection.type == "orthographic"
        assert cam.up.to_plotly_json() == dict(x=0.0, y=1.0, z=0.0)
        assert cam.eye.z > cam.center.z
        assert abs(cam.eye.x - cam.center.x) < 1e-9
        assert abs(cam.eye.y - cam.center.y) < 1e-9

    def test_camera_normalized_for_large_coordinates(self):
        mesh = _synthetic_topo()
        mesh.apply_translation([93378.6, 20810.2, 3046.1])
        fig = build_plan_view_figure(mesh, _sections(), _status())

        cam = fig.layout.scene.camera
        assert cam.center.to_plotly_json() == dict(x=0.0, y=0.0, z=0.0)
        assert cam.eye.x == 0.0
        assert cam.eye.y == 0.0
        assert cam.eye.z > 0.0

    def test_axes_titled_and_z_hidden(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        scene = fig.layout.scene
        assert scene.xaxis.title.text == "Este (m)"
        assert scene.yaxis.title.text == "Norte (m)"
        assert scene.zaxis.visible is False

    def test_height_and_aspectmode(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        assert fig.layout.height >= 650
        assert fig.layout.scene.aspectmode == "data"

    def test_title_reflects_stl_topo_and_compliance(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        assert "STL Topográfico Real" in fig.layout.title.text
        assert "Cumplimiento por Perfil" in fig.layout.title.text


# ---------------------------------------------------------------------------
# Profiles: Scatter3d lines over the mesh, colored by status
# ---------------------------------------------------------------------------

class TestProfileTraces:
    def test_profiles_are_lines_without_persistent_text(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        profiles = _profile_traces(fig)
        assert len(profiles) == 2
        for trace in profiles:
            assert trace.mode == "lines"
            assert trace.text is None

    def test_profile_z_overlay_above_mesh_zmax(self):
        mesh = _synthetic_topo()
        fig = build_plan_view_figure(mesh, _sections(), _status())

        zmax = float(mesh.vertices[:, 2].max())
        for trace in _profile_traces(fig):
            assert float(trace.z[0]) > zmax
            assert float(trace.z[1]) > zmax

    def test_profile_hover_includes_score_and_state(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        by_name = {t.name: t for t in _profile_traces(fig)}
        cumple_hover = by_name["S01"].hovertemplate
        assert "S01" in cumple_hover
        assert "Puntaje de logro: 82.0/100" in cumple_hover
        assert "Estado: CUMPLE" in cumple_hover
        assert "Azimut" in cumple_hover
        assert "Sector" in cumple_hover
        assert cumple_hover.endswith("<extra></extra>")

        no_cumple_hover = by_name["S02"].hovertemplate
        assert "Puntaje de logro: 45.0/100" in no_cumple_hover
        assert "Estado: NO CUMPLE" in no_cumple_hover

    def test_profile_colors_by_status(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        by_name = {t.name: t for t in _profile_traces(fig)}
        assert by_name["S01"].line.color == "#2E7D32"
        assert by_name["S02"].line.color == "#C62828"

    def test_profiles_have_no_legend(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        assert all(t.showlegend is False for t in _profile_traces(fig))

    def test_omits_sections_missing_from_status(self):
        sections = _sections()
        status = {"S01": {"score": 82.0, "cumple": True}}
        fig = build_plan_view_figure(_synthetic_topo(), sections, status)

        profiles = _profile_traces(fig)
        assert [t.name for t in profiles] == ["S01"]
        assert all("NO CUMPLE" not in t.hovertemplate for t in profiles)


# ---------------------------------------------------------------------------
# Legend: exactly two dummy traces Cumple / No cumple
# ---------------------------------------------------------------------------

class TestLegend:
    def test_exactly_two_legend_traces(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        legends = _legend_traces(fig)
        assert len(legends) == 2
        assert {t.name for t in legends} == {"Cumple", "No cumple"}

    def test_legend_trace_colors(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        by_name = {t.name: t for t in _legend_traces(fig)}
        assert by_name["Cumple"].marker.color == "#2E7D32"
        assert by_name["No cumple"].marker.color == "#C62828"


# ---------------------------------------------------------------------------
# compute_section_status: MATCH-only mean with canonical section_score
# ---------------------------------------------------------------------------

class TestComputeSectionStatus:
    def _row(self, section, score, type_="MATCH", section_score=None):
        row = {"section": section, "type": type_, "bench_score": score}
        if section_score is not None:
            row["section_score"] = section_score
        return row

    def test_mean_of_bench_score_rounded_one_decimal(self):
        results = [
            self._row("A", 80.0),
            self._row("A", 66.0),
        ]

        status = compute_section_status(results)

        assert status["A"]["score"] == 73.0
        assert status["A"]["cumple"] is True

    def test_only_match_rows_participate(self):
        results = [
            self._row("C", 90.0),
            self._row("C", 0.0, type_="MISSING"),
            self._row("C", 0.0, type_="EXTRA"),
        ]

        status = compute_section_status(results)

        assert status["C"]["score"] == 90.0

    def test_canonical_section_score_when_coherent(self):
        results = [
            self._row("A", 80.0, section_score=95.0),
            self._row("A", 60.0, section_score=95.0),
        ]

        status = compute_section_status(results)

        assert status["A"]["score"] == 95.0

    def test_fallback_to_mean_when_canonical_incoherent(self):
        results = [
            self._row("G", 80.0, section_score=95.0),
            self._row("G", 80.0, section_score=10.0),
        ]

        status = compute_section_status(results)

        assert status["G"]["score"] == 80.0

    def test_fallback_to_mean_when_one_row_missing_section_score(self):
        results = [
            self._row("H", 80.0, section_score=95.0),
            self._row("H", 60.0),
        ]

        status = compute_section_status(results)

        assert status["H"]["score"] == 70.0
        assert status["H"]["cumple"] is True

    def test_threshold_cumple_at_70(self):
        status = compute_section_status([self._row("E", 70.0)])
        assert status["E"]["score"] == 70.0
        assert status["E"]["cumple"] is True

        status = compute_section_status([self._row("F", 69.0)])
        assert status["F"]["score"] == 69.0
        assert status["F"]["cumple"] is False

    def test_ignores_rows_without_match(self):
        results = [
            self._row("M", 0.0, type_="MISSING"),
            self._row("M", 0.0, type_="EXTRA"),
        ]

        assert compute_section_status(results) == {}


# ---------------------------------------------------------------------------
# select_plan_mesh: full vs decimated, never design
# ---------------------------------------------------------------------------

class TestSelectPlanMesh:
    def test_returns_full_when_under_cap(self):
        full = _synthetic_topo()
        decimated = _synthetic_topo()

        assert select_plan_mesh(full, decimated) is full

    def test_returns_decimated_when_over_cap(self):
        full = _synthetic_topo()
        decimated = _synthetic_topo()

        assert select_plan_mesh(full, decimated, max_full_faces=6) is decimated

    def test_returns_none_when_over_cap_without_decimated(self):
        full = _synthetic_topo()

        assert select_plan_mesh(full, None, max_full_faces=6) is None

    def test_returns_none_when_no_topo_even_with_decimated(self):
        assert select_plan_mesh(None, _synthetic_topo()) is None

    def test_returns_none_when_both_none(self):
        assert select_plan_mesh(None, None) is None


# ---------------------------------------------------------------------------
# build_plan_view_figure with no mesh: no fabricated surface
# ---------------------------------------------------------------------------

class TestBuildWithoutMesh:
    def test_no_surface_and_profiles_still_drawn(self):
        fig = build_plan_view_figure(None, _sections(), _status())

        assert _surface_traces(fig) == []
        assert len(_profile_traces(fig)) == 2
        assert len(_legend_traces(fig)) == 2

    def test_handles_none_sections(self):
        fig = build_plan_view_figure(_synthetic_topo(), [], {})

        assert len(_surface_traces(fig)) == 1
        assert len(_legend_traces(fig)) == 2


# ---------------------------------------------------------------------------
# Adapter behaviour (no Streamlit server needed)
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self, data):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)


class _FakeSt:
    def __init__(self, session_data):
        self.session_state = _FakeSession(session_data)
        self.warnings = []
        self.infos = []
        self.subheaders = []
        self.charts = []

    def subheader(self, text):
        self.subheaders.append(text)

    def warning(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def plotly_chart(self, fig, use_container_width=None):
        self.charts.append(fig)


class TestRenderPlanView:
    def _render(self, monkeypatch, session_data, results=None):
        import ui.tabs.dashboard as dashboard

        st = _FakeSt(session_data)
        monkeypatch.setattr(dashboard, "st", st)
        dashboard._render_plan_view(results or [], {})
        return st

    def test_warns_when_no_topo_mesh(self, monkeypatch):
        st = self._render(monkeypatch, {
            "sections": _sections(),
            "mesh_topo": None,
            "decimated_mesh_topo": None,
        })

        assert st.warnings
        assert st.charts
        assert "STL Topográfico Real" in st.charts[0].layout.title.text

    def test_keeps_no_sections_guard(self, monkeypatch):
        st = self._render(monkeypatch, {})

        assert st.infos
        assert st.charts == []

    def test_renders_surface_when_mesh_available(self, monkeypatch):
        st = self._render(monkeypatch, {
            "sections": _sections(),
            "mesh_topo": _synthetic_topo(),
            "decimated_mesh_topo": None,
        })

        assert not st.warnings
        assert len(st.charts) == 1
        fig = st.charts[0]
        assert [t.type for t in fig.data].count("mesh3d") == 1
