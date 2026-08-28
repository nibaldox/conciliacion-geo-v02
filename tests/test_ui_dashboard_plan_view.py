"""Tests for ui.tabs.dashboard_plan_view (compliance plan view helpers)."""
import contextlib
import numpy as np
import plotly.graph_objects as go
import pytest
import trimesh

from core.section_cutter import SectionLine
from ui.tabs.dashboard_plan_view import (
    build_plan_view_figure,
    compute_section_status,
    ensure_plan_mesh_topo,
    plan_high_detail_needed,
    select_plan_mesh,
    SURFACE_GRAY,
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


def _empty_topo():
    return trimesh.Trimesh(vertices=[], faces=[])


def _nan_topo():
    mesh = _synthetic_topo()
    verts = np.asarray(mesh.vertices, dtype=float).copy()
    verts[0, 2] = np.nan
    mesh.vertices = verts
    return mesh


def _inf_topo():
    mesh = _synthetic_topo()
    verts = np.asarray(mesh.vertices, dtype=float).copy()
    verts[0, 2] = np.inf
    mesh.vertices = verts
    return mesh


def _out_of_range_faces_topo():
    base = _synthetic_topo()
    faces = np.asarray(base.faces, dtype=int).copy()
    faces[0, 0] = 9999
    return trimesh.Trimesh(vertices=base.vertices, faces=faces, process=False)


def _profile_traces(fig):
    return [t for t in fig.data if t.type == "scatter3d"
            and t.hovertemplate and "Puntaje de logro" in t.hovertemplate]


def _legend_traces(fig):
    return [t for t in fig.data if t.showlegend]


def _big_topo():
    return trimesh.creation.icosphere(subdivisions=3, radius=25.0)


def _source_token(mesh):
    return (id(mesh), len(mesh.vertices), len(mesh.faces))


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

    def test_mesh_has_no_elevation_intensity_or_colorscale(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        surface = _surface_traces(fig)[0]
        assert surface.intensity is None
        assert surface.colorscale is None
        assert surface.cmin is None
        assert surface.cmax is None

    def test_mesh_is_neutral_gray(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        surface = _surface_traces(fig)[0]
        assert surface.color == SURFACE_GRAY

    def test_mesh_flatshading_true(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        surface = _surface_traces(fig)[0]
        assert surface.flatshading is True

    def test_mesh_lighting_reveals_relief(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        light = _surface_traces(fig)[0].lighting
        assert light.ambient <= 0.5
        assert light.diffuse >= 0.8
        assert light.specular <= 0.15
        assert light.roughness >= 0.6

    def test_mesh_lateral_lightposition(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        position = _surface_traces(fig)[0].lightposition
        assert position.x != 0 or position.y != 0

    def test_mesh_hover_labels_and_hidden_scale_legend(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        surface = _surface_traces(fig)[0]
        assert "Este" in surface.hovertemplate
        assert "Norte" in surface.hovertemplate
        assert "Elevación" in surface.hovertemplate
        assert surface.showscale is False
        assert surface.showlegend is False
        assert surface.opacity == 1.0


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
        assert by_name["Cumple"].line.color == "#2E7D32"
        assert by_name["No cumple"].line.color == "#C62828"

    def test_legend_traces_carry_a_single_none_point(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        for trace in _legend_traces(fig):
            assert list(trace.x) == [None]
            assert list(trace.y) == [None]
            assert list(trace.z) == [None]

    def test_legend_traces_are_lines_with_visible_width(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        for trace in _legend_traces(fig):
            assert trace.mode == "lines"
            assert trace.line is not None
            assert trace.line.width > 0

    def test_legend_traces_have_hover_disabled(self):
        fig = build_plan_view_figure(_synthetic_topo(), _sections(), _status())

        for trace in _legend_traces(fig):
            assert trace.hoverinfo == "none"


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

    def test_omits_section_when_only_nan_bench_score(self):
        status = compute_section_status([self._row("A", np.nan)])

        assert "A" not in status

    def test_omits_section_when_only_nan_section_score(self):
        status = compute_section_status([self._row("A", np.nan, section_score=np.nan)])

        assert "A" not in status

    def test_fallback_uses_only_finite_bench_scores(self):
        results = [
            self._row("A", 80.0),
            self._row("A", np.nan),
            self._row("A", 60.0),
        ]

        status = compute_section_status(results)

        assert status["A"]["score"] == 70.0
        assert status["A"]["cumple"] is True

    def test_canonical_requires_all_finite_section_scores(self):
        results = [
            self._row("A", 80.0, section_score=95.0),
            self._row("A", 60.0, section_score=np.nan),
        ]

        status = compute_section_status(results)

        assert status["A"]["score"] == 70.0

    def test_nan_section_score_falls_back_to_finite_bench(self):
        results = [
            self._row("A", 80.0, section_score=np.nan),
            self._row("A", 60.0, section_score=np.nan),
        ]

        status = compute_section_status(results)

        assert status["A"]["score"] == 70.0
        assert status["A"]["cumple"] is True

    def test_omitted_nan_section_is_not_painted_red(self):
        results = [self._row("A", np.nan)]
        status = compute_section_status(results)
        sections = [SectionLine(name="A", origin=np.array([0.0, 0.0]),
                                azimuth=0.0, length=20.0, sector="Norte")]
        fig = build_plan_view_figure(_synthetic_topo(), sections, status)

        assert _profile_traces(fig) == []


# ---------------------------------------------------------------------------
# select_plan_mesh: full > high-detail plan > decimated, never design
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

    def test_returns_none_for_empty_mesh(self):
        assert select_plan_mesh(_empty_topo(), None) is None

    def test_returns_none_for_empty_mesh_even_with_renderable_decimated(self):
        assert select_plan_mesh(_empty_topo(), _synthetic_topo()) is None

    def test_returns_none_for_nan_vertices(self):
        assert select_plan_mesh(_nan_topo(), None) is None

    def test_returns_none_for_inf_vertices(self):
        assert select_plan_mesh(_inf_topo(), None) is None

    def test_returns_none_for_out_of_range_face_indices(self):
        assert select_plan_mesh(_out_of_range_faces_topo(), None) is None

    def test_default_full_limit_is_plan_full_face_limit(self):
        from ui.tabs.dashboard_plan_view import PLAN_FULL_FACE_LIMIT
        assert PLAN_FULL_FACE_LIMIT == 500_000

        full = _synthetic_topo()
        assert select_plan_mesh(full, None) is full

    def test_prefers_plan_high_detail_over_decimated_when_over_cap(self):
        full = _synthetic_topo()
        plan = _synthetic_topo()
        decimated = _synthetic_topo()

        assert select_plan_mesh(full, decimated, plan, max_full_faces=6) is plan
        assert select_plan_mesh(full, decimated, None, max_full_faces=6) is decimated

    def test_never_returns_design_mesh_as_fallback(self):
        design_like = _synthetic_topo()

        assert select_plan_mesh(None, design_like, plan_mesh_topo=design_like) is None
        assert select_plan_mesh(_empty_topo(), design_like, plan_mesh_topo=design_like) is None


# ---------------------------------------------------------------------------
# ensure_plan_mesh_topo / plan_high_detail_needed: lazy high-detail plan mesh
# ---------------------------------------------------------------------------

class TestEnsurePlanMeshTopo:
    def test_returns_full_when_under_limit_without_decimating(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        session = {}
        calls = []

        def fake_decimate(mesh, target_faces=None):
            calls.append(target_faces)
            return mesh

        monkeypatch.setattr(dpv, "decimate_mesh", fake_decimate)

        topo = _synthetic_topo()
        assert dpv.ensure_plan_mesh_topo(topo, session, full_face_limit=100) is topo
        assert calls == []
        assert session.get('plan_mesh_topo') is None

    def test_returns_none_for_missing_or_invalid_topo(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "decimate_mesh", lambda mesh, target_faces=None: mesh)
        assert dpv.ensure_plan_mesh_topo(None, {}) is None
        assert dpv.ensure_plan_mesh_topo(_empty_topo(), {}) is None
        assert dpv.ensure_plan_mesh_topo(_nan_topo(), {}) is None

    def test_builds_high_detail_once_and_reuses(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        topo = _big_topo()
        calls = []

        def fake_decimate(mesh, target_faces=None):
            calls.append(target_faces)
            out = trimesh.Trimesh(vertices=mesh.vertices.copy(),
                                  faces=mesh.faces.copy(), process=False)
            out._plan_tag = "high-detail"
            return out

        monkeypatch.setattr(dpv, "decimate_mesh", fake_decimate)

        session = {}
        first = dpv.ensure_plan_mesh_topo(topo, session,
                                          full_face_limit=50, target_faces=30)
        second = dpv.ensure_plan_mesh_topo(topo, session,
                                           full_face_limit=50, target_faces=30)

        assert getattr(first, "_plan_tag", None) == "high-detail"
        assert first is second
        assert calls == [30]
        assert session.get('plan_mesh_topo') is first
        assert session.get('plan_mesh_topo_token') == _source_token(topo)

    def test_stale_token_rebuilds(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        calls = []

        def fake_decimate(mesh, target_faces=None):
            calls.append(target_faces)
            out = trimesh.Trimesh(vertices=mesh.vertices.copy(),
                                  faces=mesh.faces.copy(), process=False)
            out._plan_tag = "high-detail"
            return out

        monkeypatch.setattr(dpv, "decimate_mesh", fake_decimate)

        session = {}
        topo_a = _big_topo()
        first = dpv.ensure_plan_mesh_topo(topo_a, session,
                                          full_face_limit=50, target_faces=30)

        topo_b = _big_topo()
        second = dpv.ensure_plan_mesh_topo(topo_b, session,
                                           full_face_limit=50, target_faces=30)

        assert calls == [30, 30]
        assert second is not first
        assert session.get('plan_mesh_topo') is second
        assert session.get('plan_mesh_topo_token') == _source_token(topo_b)

    def test_returns_none_when_decimation_fails(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        def boom(mesh, target_faces=None):
            raise RuntimeError("decimation failed")

        monkeypatch.setattr(dpv, "decimate_mesh", boom)

        session = {}
        result = dpv.ensure_plan_mesh_topo(_big_topo(), session,
                                           full_face_limit=50, target_faces=30)

        assert result is None
        assert session.get('plan_mesh_topo') is None
        assert session.get('plan_mesh_topo_token') is None

    def test_returns_none_when_high_detail_not_renderable(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        def empty(mesh, target_faces=None):
            return _empty_topo()

        monkeypatch.setattr(dpv, "decimate_mesh", empty)

        assert dpv.ensure_plan_mesh_topo(_big_topo(), {},
                                         full_face_limit=50, target_faces=30) is None


class TestPlanHighDetailNeeded:
    def test_false_when_no_renderable_topo(self):
        assert plan_high_detail_needed(None, {}) is False
        assert plan_high_detail_needed(_empty_topo(), {}) is False

    def test_false_when_full_under_limit(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 100)
        assert plan_high_detail_needed(_synthetic_topo(), {}) is False

    def test_true_when_full_over_limit_and_nothing_cached(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        assert plan_high_detail_needed(_big_topo(), {}) is True

    def test_false_when_cached_plan_matches_token(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        topo = _big_topo()
        session = {
            'plan_mesh_topo': _synthetic_topo(),
            'plan_mesh_topo_token': _source_token(topo),
        }
        assert plan_high_detail_needed(topo, session) is False

    def test_true_when_cached_token_is_stale(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        topo = _big_topo()
        session = {
            'plan_mesh_topo': _synthetic_topo(),
            'plan_mesh_topo_token': _source_token(_big_topo()),
        }
        assert plan_high_detail_needed(topo, session) is True

    def test_true_when_cached_plan_is_not_renderable(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        topo = _big_topo()
        session = {'plan_mesh_topo': _empty_topo(), 'plan_mesh_topo_token': _source_token(topo)}
        assert plan_high_detail_needed(topo, session) is True


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
# build_plan_view_figure with invalid mesh: no crash, no Mesh3d, z=0 profiles
# ---------------------------------------------------------------------------

class TestBuildWithInvalidMesh:
    def test_empty_mesh_no_crash_no_surface(self):
        fig = build_plan_view_figure(_empty_topo(), _sections(), _status())

        assert _surface_traces(fig) == []
        assert len(_profile_traces(fig)) == 2
        assert len(_legend_traces(fig)) == 2

    def test_empty_mesh_profiles_at_z0(self):
        fig = build_plan_view_figure(_empty_topo(), _sections(), _status())

        for trace in _profile_traces(fig):
            assert list(trace.z) == [0.0, 0.0]

    def test_nan_vertices_no_crash_no_surface(self):
        fig = build_plan_view_figure(_nan_topo(), _sections(), _status())

        assert _surface_traces(fig) == []
        assert len(_profile_traces(fig)) == 2
        for trace in _profile_traces(fig):
            assert list(trace.z) == [0.0, 0.0]

    def test_inf_vertices_no_crash_no_surface(self):
        fig = build_plan_view_figure(_inf_topo(), _sections(), _status())

        assert _surface_traces(fig) == []
        assert len(_profile_traces(fig)) == 2
        for trace in _profile_traces(fig):
            assert list(trace.z) == [0.0, 0.0]

    def test_out_of_range_faces_no_crash_no_surface(self):
        fig = build_plan_view_figure(_out_of_range_faces_topo(), _sections(), _status())

        assert _surface_traces(fig) == []
        assert len(_profile_traces(fig)) == 2


# ---------------------------------------------------------------------------
# Adapter behaviour (no Streamlit server needed)
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self, data):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value


class _FakeSt:
    def __init__(self, session_data):
        self.session_state = _FakeSession(session_data)
        self.warnings = []
        self.infos = []
        self.subheaders = []
        self.charts = []
        self.spinners = []

    def subheader(self, text):
        self.subheaders.append(text)

    def warning(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def plotly_chart(self, fig, use_container_width=None):
        self.charts.append(fig)

    @contextlib.contextmanager
    def spinner(self, text):
        self.spinners.append(text)
        yield


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

    def test_warns_when_topo_mesh_is_unrenderable(self, monkeypatch):
        st = self._render(monkeypatch, {
            "sections": _sections(),
            "mesh_topo": _empty_topo(),
            "decimated_mesh_topo": None,
        })

        assert st.warnings
        assert any("geometría renderizable" in w for w in st.warnings)
        assert len(st.charts) == 1
        fig = st.charts[0]
        assert [t.type for t in fig.data].count("mesh3d") == 0

    def test_warns_when_nan_topo_mesh_is_unrenderable(self, monkeypatch):
        st = self._render(monkeypatch, {
            "sections": _sections(),
            "mesh_topo": _nan_topo(),
            "decimated_mesh_topo": None,
        })

        assert st.warnings
        assert any("geometría renderizable" in w for w in st.warnings)
        assert [t.type for t in st.charts[0].data].count("mesh3d") == 0


# ---------------------------------------------------------------------------
# Adapter lazy high-detail plan mesh (hot reload / big STL)
# ---------------------------------------------------------------------------

class TestRenderPlanViewHighDetail:
    def _render(self, monkeypatch, session_data, results=None):
        import ui.tabs.dashboard as dashboard

        st = _FakeSt(session_data)
        monkeypatch.setattr(dashboard, "st", st)
        dashboard._render_plan_view(results or [], {})
        return st

    def _big_session(self):
        return {
            "sections": _sections(),
            "mesh_topo": _big_topo(),
            "decimated_mesh_topo": None,
        }

    def test_builds_high_detail_lazily_with_spanish_spinner(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        monkeypatch.setattr(dpv, "PLAN_TARGET_FACES", 30)
        calls = []

        def fake_decimate(mesh, target_faces=None):
            calls.append(target_faces)
            out = trimesh.Trimesh(vertices=mesh.vertices.copy(),
                                  faces=mesh.faces.copy(), process=False)
            out._plan_tag = "high-detail"
            return out

        monkeypatch.setattr(dpv, "decimate_mesh", fake_decimate)

        session_data = self._big_session()
        st = self._render(monkeypatch, session_data)

        assert calls == [30]
        assert st.spinners and "Preparando superficie" in st.spinners[0]
        plan = st.session_state.data.get('plan_mesh_topo')
        assert getattr(plan, "_plan_tag", None) == "high-detail"
        assert (st.session_state.data.get('plan_mesh_topo_token')
                == _source_token(session_data['mesh_topo']))

    def test_reuses_cached_high_detail_on_second_rerun(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        monkeypatch.setattr(dpv, "PLAN_TARGET_FACES", 30)
        calls = []

        def fake_decimate(mesh, target_faces=None):
            calls.append(target_faces)
            out = trimesh.Trimesh(vertices=mesh.vertices.copy(),
                                  faces=mesh.faces.copy(), process=False)
            out._plan_tag = "high-detail"
            return out

        monkeypatch.setattr(dpv, "decimate_mesh", fake_decimate)

        session_data = self._big_session()
        first = self._render(monkeypatch, session_data)
        plan = first.session_state.data.get('plan_mesh_topo')
        assert calls == [30]

        second = self._render(monkeypatch, session_data)

        assert calls == [30]
        assert second.session_state.data.get('plan_mesh_topo') is plan
        assert second.spinners == []

    def test_stale_token_rebuilds_after_hot_reload(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        monkeypatch.setattr(dpv, "PLAN_TARGET_FACES", 30)
        calls = []

        def fake_decimate(mesh, target_faces=None):
            calls.append(target_faces)
            out = trimesh.Trimesh(vertices=mesh.vertices.copy(),
                                  faces=mesh.faces.copy(), process=False)
            out._plan_tag = "high-detail"
            return out

        monkeypatch.setattr(dpv, "decimate_mesh", fake_decimate)

        session_data = self._big_session()
        first = self._render(monkeypatch, session_data)
        first_plan = first.session_state.data.get('plan_mesh_topo')
        assert calls == [30]

        session_data['mesh_topo'] = _big_topo()
        second = self._render(monkeypatch, session_data)

        assert calls == [30, 30]
        plan = second.session_state.data.get('plan_mesh_topo')
        assert plan is not first_plan
        assert second.session_state.data.get('plan_mesh_topo_token') == _source_token(session_data['mesh_topo'])

    def test_falls_back_to_decimated_when_high_detail_fails(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        monkeypatch.setattr(dpv, "PLAN_TARGET_FACES", 30)

        def boom(mesh, target_faces=None):
            raise RuntimeError("decimation failed")

        monkeypatch.setattr(dpv, "decimate_mesh", boom)

        decimated = _synthetic_topo()
        st = self._render(monkeypatch, {
            "sections": _sections(),
            "mesh_topo": _big_topo(),
            "decimated_mesh_topo": decimated,
        })

        assert st.session_state.data.get('plan_mesh_topo') is None
        fig = st.charts[0]
        surface = _surface_traces(fig)
        assert len(surface) == 1
        assert len(surface[0].x) == len(decimated.vertices)

    def test_never_renders_design_mesh_when_high_detail_fails(self, monkeypatch):
        import ui.tabs.dashboard_plan_view as dpv

        monkeypatch.setattr(dpv, "PLAN_FULL_FACE_LIMIT", 50)
        monkeypatch.setattr(dpv, "PLAN_TARGET_FACES", 30)

        def boom(mesh, target_faces=None):
            raise RuntimeError("decimation failed")

        monkeypatch.setattr(dpv, "decimate_mesh", boom)

        design = _synthetic_topo()
        st = self._render(monkeypatch, {
            "sections": _sections(),
            "mesh_topo": _big_topo(),
            "decimated_mesh_topo": design,
        })

        fig = st.charts[0]
        surface = _surface_traces(fig)
        assert len(surface) == 1
        assert len(surface[0].x) == len(design.vertices)
