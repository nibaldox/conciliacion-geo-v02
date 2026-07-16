"""Tests for the pure cutting helpers in ui.step2_sections.cutting."""
import io

import numpy as np
import pytest
import trimesh

from core.section_cutter import SectionLine
from ui.step2_sections.cutting import (
    compute_manual_azimuth,
    find_df_column,
    generate_auto_sections,
    generate_file_sections,
    generate_manual_section,
    get_plan_view_vertices,
    parse_coord_file,
    sections_to_rows,
)


class MockUploadedFile:
    """Minimal UploadedFile stand-in."""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def read(self):
        return self._content


def test_parse_coord_file_csv_with_xy_columns():
    content = "X,Y,note\n0,0,a\n10,0,b\n10,10,c\n"
    f = MockUploadedFile("line.csv", content.encode("utf-8"))
    polyline = parse_coord_file(f)
    assert polyline is not None
    np.testing.assert_array_equal(polyline, np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]))


def test_parse_coord_file_csv_with_numeric_fallback():
    content = "este,norte\n5,5\n15,5\n"
    f = MockUploadedFile("coords.txt", content.encode("utf-8"))
    polyline = parse_coord_file(f)
    assert polyline is not None
    np.testing.assert_array_equal(polyline, np.array([[5.0, 5.0], [15.0, 5.0]]))


def test_generate_file_sections_names_and_lengths():
    polyline = np.array([[0.0, 0.0], [100.0, 0.0]])
    sections = generate_file_sections(
        polyline, spacing=20.0, len_up=30.0, len_down=50.0,
        sector="Principal", design_mesh=None, file_name="ruta.csv")
    assert len(sections) == 5
    for sec in sections:
        assert sec.length == 80.0
        assert sec.length_up == 30.0
        assert sec.length_down == 50.0
        assert sec.sector == "Principal"
        assert sec.file_name == "ruta.csv"
        assert sec.name.startswith("S") and "ruta" in sec.name


def test_generate_auto_sections_perpendicular():
    mesh = trimesh.creation.box(extents=[200.0, 200.0, 50.0])
    start = np.array([0.0, 0.0])
    end = np.array([100.0, 0.0])
    sections = generate_auto_sections(
        mesh, start, end, n=3, az_method="Perpendicular a la línea (Recomendado)",
        fixed_az=0.0, len_up=40.0, len_down=40.0, sector="Cresta")
    assert len(sections) == 3
    for sec in sections:
        assert sec.length == 80.0
        assert sec.sector == "Cresta"
        assert 0 <= sec.azimuth < 360


def test_generate_auto_sections_fixed_azimuth():
    mesh = trimesh.creation.box(extents=[200.0, 200.0, 50.0])
    start = np.array([0.0, 0.0])
    end = np.array([100.0, 0.0])
    sections = generate_auto_sections(
        mesh, start, end, n=2, az_method="Fijo",
        fixed_az=45.0, len_up=30.0, len_down=30.0, sector="Test")
    assert len(sections) == 2
    for sec in sections:
        assert sec.azimuth == pytest.approx(45.0)


def test_compute_manual_azimuth_on_flat_mesh():
    mesh = trimesh.creation.box(extents=[10.0, 10.0, 1.0])
    az = compute_manual_azimuth(mesh, 0.0, 0.0, auto_detect=True)
    assert az == pytest.approx(0.0)
    assert compute_manual_azimuth(mesh, 0.0, 0.0, auto_detect=False) is None


def test_generate_manual_section_defaults():
    sec = generate_manual_section("S-01", "Sector A", 100.0, 200.0, 90.0, 50.0, 30.0)
    assert isinstance(sec, SectionLine)
    assert sec.name == "S-01"
    assert sec.length == 80.0
    assert sec.length_up == 50.0
    assert sec.length_down == 30.0
    np.testing.assert_array_equal(sec.origin, np.array([100.0, 200.0]))


def test_sections_to_rows_pending_state():
    sec = SectionLine(name="S-01", origin=np.array([0.0, 0.0]), azimuth=90.0, length=100.0,
                      sector="S", length_up=60.0, length_down=40.0)
    rows = sections_to_rows([sec], pending_names={"S-01"})
    assert len(rows) == 1
    assert rows[0]["Estado"] == "⚠ Pendiente"
    assert rows[0]["Nombre"] == "S-01"
    assert rows[0]["Long. Arriba (m)"] == "60.0"
    assert rows[0]["Long. Abajo (m)"] == "40.0"


def test_sections_to_rows_without_asymmetric_lengths():
    sec = SectionLine(name="S-02", origin=np.array([1.0, 2.0]), azimuth=0.0, length=100.0)
    rows = sections_to_rows([sec], pending_names=set())
    assert rows[0]["Estado"] == "Aplicada"
    assert rows[0]["Long. Arriba (m)"] == "50.0"
    assert rows[0]["Long. Abajo (m)"] == "50.0"


def test_find_df_column_finds_alias():
    import pandas as pd
    df = pd.DataFrame({"Este": [1, 2], "Norte": [3, 4]})
    assert find_df_column(df, {'X', 'ESTE', 'EAST', 'E'}) == "Este"
    assert find_df_column(df, {'Y', 'NORTE'}) == "Norte"


def test_get_plan_view_vertices_subsamples():
    mesh = trimesh.creation.box(extents=[10.0, 10.0, 10.0])
    verts = get_plan_view_vertices(mesh, max_points=4)
    assert len(verts) <= len(mesh.vertices)
    assert verts.shape[1] == 3
