"""Tests for core.section_cutter — section cutting and generation."""

import numpy as np
import pytest
import trimesh

from core import SectionLine, cut_mesh_with_section
from core.section_cutter import (
    ProfileResult,
    azimuth_to_direction,
    compute_local_azimuth,
    cut_both_surfaces,
    generate_perpendicular_sections,
    generate_sections_along_crest,
)


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
