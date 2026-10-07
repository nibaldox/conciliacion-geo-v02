"""Tests for core.section_cutter — section cutting and generation."""

import numpy as np
import pytest
import trimesh

from core import SectionLine, cut_mesh_with_section
from core.section_cutter import (
    cut_mesh_with_section_diagnostics,
    ProfileResult,
    azimuth_to_direction,
    compute_local_azimuth,
    cut_both_surfaces,
    generate_perpendicular_sections,
    generate_sections_along_crest,
)
from core.horizontal_deviation import profile_intersections_at_elevation


class TestCutMesh:
    """Tests for cutting meshes with sections."""

    def test_cut_mesh_with_section(self, pit_mesh_design):
        """Cortar mesh retorna ProfileResult con distances y elevations arrays."""
        section = SectionLine(
            name="S-TEST",
            origin=np.array([250.0, 250.0]),
            azimuth=0.0,
            length=400.0,
            sector="Test",
        )
        result = cut_mesh_with_section(pit_mesh_design, section)

        assert result is not None
        assert isinstance(result, ProfileResult)
        assert isinstance(result.distances, np.ndarray)
        assert isinstance(result.elevations, np.ndarray)
        assert len(result.distances) >= 2
        assert len(result.distances) == len(result.elevations)

    def test_cut_mesh_with_asymmetric_section(self, pit_mesh_design):
        """Cortar mesh con una sección asimétrica respeta length_up y length_down."""
        section = SectionLine(
            name="S-ASYM",
            origin=np.array([250.0, 250.0]),
            azimuth=0.0,
            length=200.0,
            sector="Test",
            length_up=150.0,
            length_down=50.0,
        )
        result = cut_mesh_with_section(pit_mesh_design, section)

        assert result is not None
        assert isinstance(result, ProfileResult)
        assert result.distances.max() <= 150.001
        assert result.distances.min() >= -50.001
        assert section.length == 200.0

    def test_cut_mesh_no_intersection(self, pit_mesh_design):
        """Sección fuera del mesh retorna None."""
        section = SectionLine(
            name="S-FAR",
            origin=np.array([9999.0, 9999.0]),
            azimuth=0.0,
            length=400.0,
            sector="Test",
        )
        result = cut_mesh_with_section(pit_mesh_design, section)
        assert result is None

    def test_disconnected_intersection_components_are_rejected_with_diagnostic(self):
        first = trimesh.Trimesh(
            vertices=[[0, -1, 0], [0, 1, 0], [1, 0, 1]],
            faces=[[0, 1, 2]],
            process=False,
        )
        second = trimesh.Trimesh(
            vertices=[[5, -1, 10], [5, 1, 10], [6, 0, 11]],
            faces=[[0, 1, 2]],
            process=False,
        )
        mesh = trimesh.util.concatenate([first, second])
        section = SectionLine("S-GAP", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.profile is None
        assert diagnostic.warnings == ("disconnected_profile_components",)
        assert cut_mesh_with_section(mesh, section) is None

    def test_disconnected_component_outside_section_is_ignored(self):
        first = trimesh.Trimesh(
            vertices=[[0, -1, 0], [0, 1, 0], [1, 0, 1]],
            faces=[[0, 1, 2]],
            process=False,
        )
        second = trimesh.Trimesh(
            vertices=[[20, -1, 10], [20, 1, 10], [21, 0, 11]],
            faces=[[0, 1, 2]],
            process=False,
        )
        section = SectionLine("S-OUTSIDE", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(
            trimesh.util.concatenate([first, second]), section
        )

        assert diagnostic.warnings == ()
        assert diagnostic.profile is not None
        assert diagnostic.profile.distances.min() == pytest.approx(0.0)
        assert diagnostic.profile.distances.max() == pytest.approx(1.0)

    def test_intersection_entirely_outside_section_reports_no_intersection(self):
        mesh = trimesh.Trimesh(
            vertices=[[20, -1, 0], [20, 1, 0], [21, 0, 1]],
            faces=[[0, 1, 2]],
            process=False,
        )
        section = SectionLine("S-NO-INTERSECTION", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.profile is None
        assert diagnostic.warnings == ("no_section_intersection",)

    def test_projected_overlapping_components_are_rejected_instead_of_averaged(self):
        first = trimesh.Trimesh(
            vertices=[[0, -1, 0], [0, 1, 0], [1, 0, 1]],
            faces=[[0, 1, 2]],
            process=False,
        )
        second = trimesh.Trimesh(
            vertices=[[0, -1, 10], [0, 1, 10], [1, 0, 11]],
            faces=[[0, 1, 2]],
            process=False,
        )
        mesh = trimesh.util.concatenate([first, second])
        section = SectionLine("S-OVERLAP", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.profile is None
        assert diagnostic.warnings == ("disconnected_profile_components",)

    def test_connected_profile_with_horizontal_reversal_is_rejected_as_ambiguous(self):
        profile_points = [(0, 0), (10, 1), (4, 2)]
        vertices = [
            [distance, y, elevation]
            for distance, elevation in profile_points
            for y in (-1, 1)
        ]
        mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=[[0, 2, 3], [0, 3, 1], [2, 4, 5], [2, 5, 3]],
            process=False,
        )
        section = SectionLine("S-OVERHANG", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.profile is None
        assert diagnostic.warnings == ("ambiguous_profile_geometry",)

    def test_millimeter_scale_reversal_is_clamped_to_monotonic_distance(self):
        profile_points = [(0, 0), (1, 1), (0.9989, 2)]
        vertices = [
            [distance, y, elevation]
            for distance, elevation in profile_points
            for y in (-1, 1)
        ]
        mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=[[0, 2, 3], [0, 3, 1], [2, 4, 5], [2, 5, 3]],
            process=False,
        )
        section = SectionLine("S-MILLIMETER", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.warnings == ()
        assert diagnostic.profile is not None
        assert np.all(np.diff(diagnostic.profile.distances) >= 0.0)
        assert diagnostic.profile.distances[-1] == pytest.approx(1.0)
        assert diagnostic.profile.elevations[-1] == pytest.approx(2.0)

    def test_cumulative_reversal_beyond_profile_resolution_is_rejected(self):
        profile_points = [(0, 0), (1, 1), (0.94, 2), (0.88, 3)]
        vertices = [
            [distance, y, elevation]
            for distance, elevation in profile_points
            for y in (-1, 1)
        ]
        faces = []
        for index in range(len(profile_points) - 1):
            first = 2 * index
            following = first + 2
            faces.extend([[first, following, following + 1], [first, following + 1, first + 1]])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        section = SectionLine("S-CUMULATIVE-REVERSAL", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.profile is None
        assert diagnostic.warnings == ("ambiguous_profile_geometry",)

    def test_sub_resolution_reversal_is_preserved_as_vertical_with_warning(self):
        profile_points = [(0, 0), (1, 1), (0.95, 2), (2, 3)]
        vertices = [
            [distance, y, elevation]
            for distance, elevation in profile_points
            for y in (-1, 1)
        ]
        faces = []
        for index in range(len(profile_points) - 1):
            first = 2 * index
            following = first + 2
            faces.extend([[first, following, following + 1], [first, following + 1, first + 1]])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        section = SectionLine("S-SMALL-REVERSAL", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.profile is not None
        assert diagnostic.warnings == ("minor_profile_reversal_normalized",)
        distances = diagnostic.profile.distances
        elevations = diagnostic.profile.elevations
        assert np.all(np.diff(distances) >= 0.0)
        assert elevations[np.flatnonzero(np.isclose(distances, 1.0))].tolist() == pytest.approx([1.0, 1.5, 2.0])
        assert distances[-1] == pytest.approx(2.0)
        crossing = profile_intersections_at_elevation(distances, elevations, 1.5)
        assert crossing.status == "measured"
        assert crossing.distance_m == pytest.approx(1.0)

    def test_repair_has_physical_cap_even_if_profile_resolution_is_larger(self, monkeypatch):
        from dataclasses import replace
        import core.config

        profile_points = [(0, 0), (1, 1), (0.8, 2)]
        vertices = [
            [distance, y, elevation]
            for distance, elevation in profile_points
            for y in (-1, 1)
        ]
        mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=[[0, 2, 3], [0, 3, 1], [2, 4, 5], [2, 5, 3]],
            process=False,
        )
        monkeypatch.setattr(
            core.config,
            "DETECTION",
            replace(core.config.DETECTION, profile_resolution=1.0),
        )
        section = SectionLine("S-REPAIR-CAP", np.array([0.0, 0.0]), 90.0, 20.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.profile is None
        assert diagnostic.warnings == ("ambiguous_profile_geometry",)

    def test_reversal_outside_requested_section_does_not_reject_profile(self):
        profile_points = [(-20, 0), (-15, 5), (-16, 6), (-10, 10), (0, 11), (10, 10), (20, 0)]
        vertices = [
            [distance, y, elevation]
            for distance, elevation in profile_points
            for y in (-1, 1)
        ]
        faces = []
        for index in range(len(profile_points) - 1):
            first = 2 * index
            following = first + 2
            faces.extend([[first, following, following + 1], [first, following + 1, first + 1]])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        section = SectionLine("S-CLIPPED", np.array([0.0, 0.0]), 90.0, 18.0)

        diagnostic = cut_mesh_with_section_diagnostics(mesh, section)

        assert diagnostic.warnings == ()
        assert diagnostic.profile is not None
        assert diagnostic.profile.distances.min() == pytest.approx(-9.0)
        assert diagnostic.profile.distances.max() == pytest.approx(9.0)
        assert diagnostic.profile.elevations[0] == pytest.approx(10.1)
        assert diagnostic.profile.elevations[-1] == pytest.approx(10.1)
        assert np.all(np.diff(diagnostic.profile.distances) >= -1e-3)

    def test_connected_vertical_intersection_is_preserved(self):
        mesh = trimesh.Trimesh(
            vertices=[
                [0, -1, 0], [0, 1, 0], [0, 1, 10], [0, -1, 10],
            ],
            faces=[[0, 1, 2], [0, 2, 3]],
            process=False,
        )
        section = SectionLine("S-VERTICAL", np.array([0.0, 0.0]), 90.0, 20.0)

        profile = cut_mesh_with_section(mesh, section)

        assert profile is not None
        assert len(profile.distances) >= 2
        assert profile.distances == pytest.approx(np.zeros(len(profile.distances)))
        assert profile.elevations[0] == pytest.approx(0.0)
        assert profile.elevations[-1] == pytest.approx(10.0)

    def test_three_component_section_origin_matches_xy_origin_profile(self):
        mesh = trimesh.Trimesh(
            vertices=[
                [0, -1, 0], [0, 1, 0], [0, 1, 10], [0, -1, 10],
            ],
            faces=[[0, 1, 2], [0, 2, 3]],
            process=False,
        )
        section_xy = SectionLine("S-XY", np.array([0.0, 0.0]), 90.0, 20.0)
        section_xyz = SectionLine("S-XYZ", np.array([0.0, 0.0, 999.0]), 90.0, 20.0)

        diagnostic_xy = cut_mesh_with_section_diagnostics(mesh, section_xy)
        diagnostic_xyz = cut_mesh_with_section_diagnostics(mesh, section_xyz)

        assert diagnostic_xyz.warnings == diagnostic_xy.warnings == ()
        assert diagnostic_xyz.profile is not None
        assert diagnostic_xy.profile is not None
        assert diagnostic_xyz.profile.distances == pytest.approx(
            diagnostic_xy.profile.distances
        )
        assert diagnostic_xyz.profile.elevations == pytest.approx(
            diagnostic_xy.profile.elevations
        )
        assert diagnostic_xyz.profile.elevations[0] == pytest.approx(0.0)
        assert diagnostic_xyz.profile.elevations[-1] == pytest.approx(10.0)


class TestGenerateSections:
    """Tests for section generation."""

    def test_generate_sections_along_crest(self):
        """Genera N secciones equiespaciadas con nombres S-01, S-02, etc."""
        start = np.array([100.0, 250.0])
        end = np.array([400.0, 250.0])

        sections = generate_sections_along_crest(
            None,
            start_point=start,
            end_point=end,
            n_sections=5,
            section_azimuth=0.0,
            section_length=400.0,
            sector_name="Test",
        )

        assert len(sections) == 5
        assert sections[0].name == "S-01"
        assert sections[4].name == "S-05"

    def test_section_azimuth_perpendicular(self):
        """Si no se especifica azimuth, se calcula perpendicular a la línea de crest."""
        # Línea horizontal Este-Oeste: start(100,250) -> end(400,250)
        # Dirección de la línea: az=90° (Este puro)
        # Perpendicular (derecha +90): az=180° (Sur)
        start = np.array([100.0, 250.0])
        end = np.array([400.0, 250.0])

        sections = generate_sections_along_crest(
            None,
            start_point=start,
            end_point=end,
            n_sections=3,
            section_azimuth=None,  # Auto-compute perpendicular
            section_length=200.0,
        )

        # Azimuth perpendicular: la línea va al Este (az=90°), perpendicular +90 → 180° (Sur)
        for s in sections:
            assert s.azimuth == pytest.approx(180.0, abs=0.1)

    def test_section_azimuth_perpendicular_north_south(self):
        """Línea Norte-Sur genera perpendicular al Este/Oeste."""
        start = np.array([250.0, 100.0])
        end = np.array([250.0, 400.0])

        sections = generate_sections_along_crest(
            None,
            start_point=start,
            end_point=end,
            n_sections=3,
            section_azimuth=None,
            section_length=200.0,
        )

        # Línea va al Norte (az=0°), perpendicular +90 → 90° (Este)
        for s in sections:
            assert s.azimuth == pytest.approx(90.0, abs=0.1)


class TestSectionLine:
    """Tests for SectionLine dataclass."""

    def test_section_dataclass(self):
        """SectionLine se puede crear con todos los campos."""
        section = SectionLine(
            name="S-01",
            origin=np.array([250.0, 250.0]),
            azimuth=90.0,
            length=200.0,
            sector="Sector A",
        )
        assert section.name == "S-01"
        np.testing.assert_allclose(section.origin, [250.0, 250.0])
        assert section.azimuth == 90.0
        assert section.length == 200.0
        assert section.sector == "Sector A"

    def test_section_dataclass_defaults(self):
        """Sector tiene valor default vacío."""
        section = SectionLine(
            name="S-02",
            origin=np.array([0.0, 0.0]),
            azimuth=0.0,
            length=100.0,
        )
        assert section.sector == ""


class TestAzimuthDirection:
    """Tests for azimuth_to_direction helper."""

    def test_north(self):
        """Azimuth 0° → dirección Norte (0, 1)."""
        d = azimuth_to_direction(0.0)
        np.testing.assert_allclose(d, [0.0, 1.0], atol=1e-10)

    def test_east(self):
        """Azimuth 90° → dirección Este (1, 0)."""
        d = azimuth_to_direction(90.0)
        np.testing.assert_allclose(d, [1.0, 0.0], atol=1e-10)

    def test_south(self):
        """Azimuth 180° → dirección Sur (0, -1)."""
        d = azimuth_to_direction(180.0)
        np.testing.assert_allclose(d, [0.0, -1.0], atol=1e-10)

    def test_west(self):
        """Azimuth 270° → dirección Oeste (-1, 0)."""
        d = azimuth_to_direction(270.0)
        np.testing.assert_allclose(d, [-1.0, 0.0], atol=1e-10)


def _plane_mesh(a=0.0, b=0.0, c=1000.0, extent=100.0, step=10.0):
    xs = np.arange(-extent, extent + step, step)
    ys = np.arange(-extent, extent + step, step)
    X, Y = np.meshgrid(xs, ys)
    Z = a * X + b * Y + c
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    nx, ny = len(xs), len(ys)
    faces = []
    for i in range(ny - 1):
        for j in range(nx - 1):
            v0 = i * nx + j
            v1 = v0 + 1
            v2 = (i + 1) * nx + j
            v3 = v2 + 1
            faces.append([v0, v1, v2])
            faces.append([v1, v3, v2])
    return trimesh.Trimesh(vertices=verts, faces=np.array(faces))


class TestCutBothSurfaces:
    """Tests for cutting design + topo with the same section."""

    def test_cut_both_returns_profiles(self, pit_mesh_design, pit_mesh_asbuilt):
        section = SectionLine(
            name="S-BOTH",
            origin=np.array([250.0, 250.0]),
            azimuth=0.0,
            length=400.0,
            sector="Test",
        )
        pd_prof, pt_prof = cut_both_surfaces(pit_mesh_design, pit_mesh_asbuilt, section)

        assert pd_prof is not None
        assert pt_prof is not None
        assert isinstance(pd_prof, ProfileResult)
        assert isinstance(pt_prof, ProfileResult)
        assert len(pd_prof.distances) >= 2
        assert len(pt_prof.distances) >= 2

    def test_cut_both_far_returns_none_none(self, pit_mesh_design, pit_mesh_asbuilt):
        section = SectionLine(
            name="S-FAR",
            origin=np.array([9999.0, 9999.0]),
            azimuth=0.0,
            length=400.0,
            sector="Test",
        )
        pd_prof, pt_prof = cut_both_surfaces(pit_mesh_design, pit_mesh_asbuilt, section)
        assert pd_prof is None
        assert pt_prof is None


class TestComputeLocalAzimuth:
    """Tests for steepest-descent azimuth on a mesh surface."""

    def test_sloped_plane_returns_downhill_azimuth(self):
        mesh = _plane_mesh(a=-1.0, b=0.0, c=1000.0)
        az = compute_local_azimuth(mesh, np.array([0.0, 0.0]), radius=50.0)
        assert az == pytest.approx(90.0, abs=1.0)

    def test_flat_plane_returns_zero(self):
        mesh = _plane_mesh(a=0.0, b=0.0, c=1000.0)
        az = compute_local_azimuth(mesh, np.array([0.0, 0.0]), radius=50.0)
        assert az == 0.0

    def test_sparse_vertices_returns_zero(self):
        box = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
        az = compute_local_azimuth(box, np.array([0.0, 0.0]), radius=2.0)
        assert az == 0.0


class TestGeneratePerpendicularSections:
    """Tests for sections perpendicular to a polyline."""

    def test_basic_perpendicular_sections(self):
        pts = np.array([[0.0, 0.0], [100.0, 0.0], [200.0, 0.0]])
        sections = generate_perpendicular_sections(pts, spacing=50.0, section_length=200.0)

        assert len(sections) >= 2
        for s in sections:
            assert s.azimuth == pytest.approx(180.0, abs=0.1)
            assert s.length == 200.0

    def test_with_design_mesh_azimuth(self):
        mesh = _plane_mesh(a=-1.0, b=0.0, c=1000.0)
        pts = np.array([[0.0, 0.0], [100.0, 0.0]])
        sections = generate_perpendicular_sections(
            pts, spacing=50.0, section_length=200.0, design_mesh=mesh
        )
        assert len(sections) >= 1
        for s in sections:
            assert s.azimuth == pytest.approx(90.0, abs=2.0)

    def test_too_few_points_returns_empty(self):
        sections = generate_perpendicular_sections(
            np.array([[5.0, 5.0]]), spacing=50.0, section_length=200.0
        )
        assert sections == []

    def test_zero_length_polyline_returns_empty(self):
        sections = generate_perpendicular_sections(
            np.array([[5.0, 5.0], [5.0, 5.0]]), spacing=50.0, section_length=200.0
        )
        assert sections == []

    def test_short_line_yields_single_mid_section(self):
        pts = np.array([[0.0, 0.0], [5.0, 0.0]])
        sections = generate_perpendicular_sections(pts, spacing=50.0, section_length=200.0)
        assert len(sections) == 1

    def test_length_up_down_propagated(self):
        pts = np.array([[0.0, 0.0], [100.0, 0.0]])
        sections = generate_perpendicular_sections(
            pts, spacing=50.0, section_length=200.0, length_up=150.0, length_down=50.0
        )
        assert len(sections) >= 1
        for s in sections:
            assert s.length_up == 150.0
            assert s.length_down == 50.0
            assert s.length == 200.0


class TestGenerateSectionsAlongCrestEdgeCases:
    """Edge cases for generate_sections_along_crest."""

    def test_single_section_at_midpoint(self):
        start = np.array([100.0, 250.0])
        end = np.array([400.0, 250.0])
        sections = generate_sections_along_crest(
            None,
            start_point=start,
            end_point=end,
            n_sections=1,
            section_azimuth=0.0,
            section_length=200.0,
        )
        assert len(sections) == 1
        np.testing.assert_allclose(sections[0].origin, [250.0, 250.0], atol=1e-6)
