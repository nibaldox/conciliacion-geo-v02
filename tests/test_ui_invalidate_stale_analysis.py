"""Regression tests for the HIGH: stale draped profiles after mesh/section changes.

Audit finding: ``ui/tabs/dashboard.py`` consumed the canonical ``profiles_topo``
and ``processed_sections`` stashed by step 3 without any provenance or
invalidation. After loading another topography, or changing / deleting /
recreating sections (even under the same name), the plan view could drape the
previous profiles over the current mesh or section.

The fix lives at the Streamlit state root: a central
``ui.state.invalidate_analysis_results`` is invoked whenever the surfaces or
the section list change, so a stale profile can never be draped again. These
tests lock that behaviour without asserting internal structure: they verify
session_state outcomes and the rendered figure behaviour (no profile traces
with a stale name after invalidation), plus a real cut -> drape integration
using actual mesh geometry (no mocks for the geometry path).
"""
from __future__ import annotations

import numpy as np
import pytest
import streamlit as st
import trimesh

import ui.state
import ui.step1_upload as step1
from core import SectionLine, cut_mesh_with_section
from core.section_cutter import azimuth_to_direction
from ui.step2_sections import state as s2_state
from ui.tabs.dashboard_plan_view import (
    build_plan_view_figure,
    build_topo_profile_map,
    drape_section_profile,
)

# Every key holding an analysis-derived artifact. Invalidating all of them
# together is the contract tested here.
ANALYSIS_KEYS = (
    "profiles_design", "profiles_topo",
    "params_design", "params_topo",
    "comparison_results", "processed_sections",
    "reconciled_design", "reconciled_topo",
    "area_fill_design", "area_fill_topo",
)


@pytest.fixture(autouse=True)
def _clean_session_state():
    """Real Streamlit session_state works in bare mode; keep it isolated."""
    st.session_state.clear()
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    yield
    st.session_state.clear()


def _section(name="S01", az=0.0, origin=(100.0, 200.0), length=40.0):
    return SectionLine(name=name, origin=np.array(origin, dtype=float),
                       azimuth=az, length=length, sector="Norte")


def _seed_analysis():
    """Populate every derived key with a stale sentinel value."""
    for key in ANALYSIS_KEYS:
        st.session_state[key] = ["stale-value"]
    st.session_state["_profile_figs"] = {0: ("cache-key", object())}


def _profile_traces(fig):
    return [t for t in fig.data if t.type == "scatter3d"
            and t.hovertemplate and "Puntaje de logro" in t.hovertemplate]


# ---------------------------------------------------------------------------
# Central invalidation: ui.state.invalidate_analysis_results
# ---------------------------------------------------------------------------

class TestInvalidateAnalysisResults:
    def test_clears_every_analysis_derived_key(self):
        _seed_analysis()

        ui.state.invalidate_analysis_results()

        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == [], f"{key} not invalidated"
        assert st.session_state.get("_profile_figs") == {}

    def test_does_not_touch_surfaces_or_sections(self):
        design, topo = object(), object()
        sec = _section()
        st.session_state.mesh_design = design
        st.session_state.mesh_topo = topo
        st.session_state.sections = [sec]
        st.session_state.comparison_results = ["stale"]

        ui.state.invalidate_analysis_results()

        assert st.session_state.mesh_design is design
        assert st.session_state.mesh_topo is topo
        assert st.session_state.sections == [sec]

    def test_idempotent_when_keys_absent(self):
        ui.state.invalidate_analysis_results()  # must not raise

        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) is None


# ---------------------------------------------------------------------------
# _load_meshes: invalidate only after a fully successful replacement
# ---------------------------------------------------------------------------

class _FakeUploadedFile:
    def __init__(self, name):
        self.name = name
        self.size = 123

    def read(self):
        return b"design-bytes" if "design" in self.name else b"topo-bytes"


class TestLoadMeshesInvalidation:
    def _successful_load(self, monkeypatch):
        design = trimesh.creation.box(extents=[10.0, 10.0, 5.0])
        topo = trimesh.creation.icosphere(subdivisions=1, radius=7.0)
        calls = []

        def fake_load(path):
            calls.append(path)
            return design if len(calls) == 1 else topo

        monkeypatch.setattr(step1, "load_mesh", fake_load)
        monkeypatch.setattr(step1, "decimate_mesh",
                            lambda mesh, target_faces=None: mesh)
        return design, topo

    def test_successful_upload_clears_analysis_and_lowers_step(self, monkeypatch):
        design, topo = self._successful_load(monkeypatch)
        st.session_state.sections = [_section()]
        st.session_state.step = 4
        _seed_analysis()

        step1._load_meshes(_FakeUploadedFile("design.stl"),
                           _FakeUploadedFile("topo.stl"))

        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == [], f"{key} not invalidated"
        assert st.session_state.get("_profile_figs") == {}
        assert st.session_state.step == 3, \
            "with sections the workflow must land on step 3, never keep step 4"
        assert st.session_state.mesh_design is design
        assert st.session_state.mesh_topo is topo
        # Sections are NOT wiped when the surfaces are replaced.
        assert [s.name for s in st.session_state.sections] == ["S01"]

    def test_successful_upload_without_sections_goes_to_step2(self, monkeypatch):
        self._successful_load(monkeypatch)
        st.session_state.step = 4  # stale step from a previous session
        _seed_analysis()

        step1._load_meshes(_FakeUploadedFile("design.stl"),
                           _FakeUploadedFile("topo.stl"))

        assert st.session_state.step == 2
        assert st.session_state.get("profiles_topo") == []

    def test_failed_upload_preserves_previous_analysis_and_step(self, monkeypatch):
        old_design, old_topo = object(), object()
        st.session_state.mesh_design = old_design
        st.session_state.mesh_topo = old_topo
        st.session_state.step = 4
        _seed_analysis()
        calls = []

        def fake_load(path):
            calls.append(path)
            if len(calls) == 2:
                raise ValueError("corrupt STL")
            return trimesh.creation.box(extents=[1.0, 1.0, 1.0])

        monkeypatch.setattr(step1, "load_mesh", fake_load)
        monkeypatch.setattr(step1, "decimate_mesh",
                            lambda mesh, target_faces=None: mesh)

        step1._load_meshes(_FakeUploadedFile("design.stl"),
                           _FakeUploadedFile("topo.stl"))

        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == ["stale-value"], \
                f"failed upload must not destroy {key}"
        assert st.session_state.step == 4
        assert st.session_state.mesh_design is old_design
        assert st.session_state.mesh_topo is old_topo

    def test_clear_surface_state_invalidates_analysis(self, monkeypatch):
        st.session_state.mesh_design = trimesh.creation.box()
        st.session_state.mesh_topo = trimesh.creation.box()
        _seed_analysis()

        step1._clear_surface_state()

        assert st.session_state.get("mesh_design") is None
        assert st.session_state.get("mesh_topo") is None
        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == []


# ---------------------------------------------------------------------------
# Section mutations: every real change invalidates derived results
# ---------------------------------------------------------------------------

class TestSectionMutationsInvalidate:
    def _seed_sections(self, names=("S01", "S02"), pending=()):
        st.session_state.sections = [_section(n) for n in names]
        st.session_state.pending_section_names = set(pending)

    def test_add_sections_invalidates_derived_results(self):
        self._seed_sections()
        _seed_analysis()

        added = s2_state.add_sections([_section("S03")])

        assert [s.name for s in added] == ["S03"]
        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == []

    def test_add_sections_noop_does_not_invalidate(self):
        self._seed_sections()
        _seed_analysis()

        s2_state.add_sections([])

        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == ["stale-value"], \
                f"no-op add must keep {key}"

    def test_clear_pending_sections_invalidates(self):
        self._seed_sections(pending=("S01",))
        _seed_analysis()

        s2_state.clear_pending_sections()

        assert [s.name for s in st.session_state.sections] == ["S02"]
        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == []

    def test_clear_pending_sections_noop_does_not_invalidate(self):
        self._seed_sections(pending=())
        _seed_analysis()

        s2_state.clear_pending_sections()

        assert [s.name for s in st.session_state.sections] == ["S01", "S02"]
        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == ["stale-value"]

    def test_clear_all_sections_invalidates(self):
        self._seed_sections()
        _seed_analysis()

        s2_state.clear_all_sections()

        assert st.session_state.sections == []
        assert st.session_state.pending_section_names == set()
        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == []

    def test_clear_all_sections_noop_does_not_invalidate(self):
        self._seed_sections(names=())
        _seed_analysis()

        s2_state.clear_all_sections()

        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == ["stale-value"]

    def test_append_interactive_section_invalidates(self):
        self._seed_sections()
        _seed_analysis()

        s2_state.append_interactive_section(_section("S09"))

        assert "S09" in st.session_state.pending_section_names
        for key in ANALYSIS_KEYS:
            assert st.session_state.get(key) == []

    def test_recreate_section_with_same_name_never_restores_old_profile(self):
        # The audit scenario: clear everything, then re-add a section with the
        # SAME name. The old canonical profile for that name must never come
        # back, and the dashboard must draw no profile for it.
        self._seed_sections(names=("S01",))
        _seed_analysis()

        s2_state.clear_all_sections()
        s2_state.add_sections([_section("S01")])

        assert st.session_state.get("profiles_topo") == []
        assert st.session_state.get("processed_sections") == []
        assert st.session_state.get("comparison_results") == []

        # Dashboard consumption path: empty mapping -> no old profile drawn.
        mapping = build_topo_profile_map(
            st.session_state.get("processed_sections") or [],
            st.session_state.get("profiles_topo") or [])
        assert mapping == {}
        status = {"S01": {"score": 80.0, "cumple": True}}
        fig = build_plan_view_figure(
            trimesh.creation.box(extents=[10.0, 10.0, 5.0]),
            [_section("S01", origin=(0.0, 0.0))], status,
            profiles_by_name=mapping)
        assert _profile_traces(fig) == [], \
            "stale profile with the same section name must not be draped"


# ---------------------------------------------------------------------------
# Real cut -> drape integration (no mocks for the geometry path)
# ---------------------------------------------------------------------------

# Coefficients of the analytic plane used as the "true" surface, so the
# drape can be verified against real geometry without needing trimesh's
# optional rtree dependency (trimesh.proximity.closest_point).
PLANE_A, PLANE_B, PLANE_C = 0.05, -0.02, 10.0


def _inclined_plane(nx=60, ny=60, a=PLANE_A, b=PLANE_B, c=PLANE_C,
                    x_range=(0.0, 100.0), y_range=(0.0, 100.0)):
    """A triangulated plane z = a*x + b*y + c over [0,100]x[0,100]."""
    xs = np.linspace(x_range[0], x_range[1], nx)
    ys = np.linspace(y_range[0], y_range[1], ny)
    X, Y = np.meshgrid(xs, ys)
    Z = a * X + b * Y + c
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    faces = []
    for i in range(ny - 1):
        for j in range(nx - 1):
            v0 = i * nx + j
            faces.append([v0, v0 + 1, v0 + nx])
            faces.append([v0 + 1, v0 + nx + 1, v0 + nx])
    return trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=False)


class TestCutToDrapeIntegration:
    def _check_drape_follows_cut(self, mesh, section, z_offset):
        profile = cut_mesh_with_section(mesh, section)
        assert profile is not None, "the section must cut the mesh"
        assert len(profile.distances) >= 2
        assert not np.allclose(profile.elevations, profile.elevations[0]), \
            "sloped surface must yield a non-constant cut"

        x, y, z = drape_section_profile(section, profile, z_offset=z_offset)
        assert x is not None

        direction = azimuth_to_direction(section.azimuth)
        ox, oy = float(section.origin[0]), float(section.origin[1])

        # XY are reconstructed from the same origin + distance + direction
        # the cutter used, so every sample lies back on the section line.
        assert np.allclose(x, ox + profile.distances * direction[0])
        assert np.allclose(y, oy + profile.distances * direction[1])

        # The drape applies only the visual offset to the elevations.
        assert np.allclose(z, profile.elevations + z_offset)

        # The draped samples sit on the real surface (offset aside): the
        # analytic plane coincides with the triangulated mesh.
        plane_z = PLANE_A * x + PLANE_B * y + PLANE_C
        assert np.allclose(plane_z, z - z_offset, atol=1e-4)

        # Cumulative path length matches the profile distance span: the line
        # follows the cut monotonically instead of floating over it.
        span = profile.distances[-1] - profile.distances[0]
        path = float(np.hypot(np.diff(x), np.diff(y)).sum())
        assert np.isclose(path, span, rtol=1e-6)

        # It is a drape, not a flat overlay.
        assert float(np.max(z) - np.min(z)) > 0.5
        return x, y, z

    def test_azimuth_0_north_cut_is_reconstructed_on_the_section_line(self):
        mesh = _inclined_plane()
        section = _section(name="S-N", az=0.0, origin=(50.0, 50.0), length=80.0)

        x, y, _ = self._check_drape_follows_cut(mesh, section, z_offset=0.05)

        # North cut: X fixed at the origin, Y walks the distances.
        assert np.allclose(x, 50.0)
        assert float(np.min(y)) < 50.0 < float(np.max(y))

    def test_azimuth_90_east_cut_is_reconstructed_on_the_section_line(self):
        mesh = _inclined_plane()
        section = _section(name="S-E", az=90.0, origin=(50.0, 50.0), length=80.0)

        x, y, _ = self._check_drape_follows_cut(mesh, section, z_offset=0.05)

        # East cut: Y fixed at the origin, X walks the distances.
        assert np.allclose(y, 50.0)
        assert float(np.min(x)) < 50.0 < float(np.max(x))
