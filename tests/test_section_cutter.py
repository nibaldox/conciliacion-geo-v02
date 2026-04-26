"""Tests for core.section_cutter — section cutting and generation."""

import numpy as np
import pytest

from core import SectionLine, cut_mesh_with_section
from core.section_cutter import (
    ProfileResult,
    generate_sections_along_crest,
    azimuth_to_direction,
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
