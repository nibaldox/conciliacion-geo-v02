"""Shared fixtures for Conciliación Geotécnica test suite."""

import os
import tempfile

import numpy as np
import pytest
import trimesh

from core import SectionLine, cut_mesh_with_section
from core.section_cutter import generate_sections_along_crest


def create_pit_surface(
    nx=100,
    ny=100,
    x_range=(0, 500),
    y_range=(0, 500),
    bench_height=15.0,
    berm_width=9.0,
    face_angle_deg=70.0,
    n_benches=4,
    crest_elevation=3900.0,
    noise_std=0.0,
):
    """
    Genera una superficie sintética de pit abierto con bancos, bermas y cara.
    El pit es un cono escalonado centrado en la malla.
    (Copiado de test_pipeline.py — fuente de verdad.)
    """
    x = np.linspace(x_range[0], x_range[1], nx)
    y = np.linspace(y_range[0], y_range[1], ny)
    X, Y = np.meshgrid(x, y)

    cx = (x_range[0] + x_range[1]) / 2
    cy = (y_range[0] + y_range[1]) / 2

    R = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)

    face_width = bench_height / np.tan(np.radians(face_angle_deg))
    bench_total_width = berm_width + face_width

    Z = np.full_like(R, crest_elevation)

    for i in range(n_benches):
        r_outer = 200.0 - i * bench_total_width
        r_face_inner = r_outer - face_width
        r_inner = r_face_inner - berm_width

        if r_outer <= 0:
            break

        elev_top = crest_elevation - i * bench_height
        elev_bot = elev_top - bench_height

        mask_face = (R >= max(r_face_inner, 0)) & (R < r_outer)
        if mask_face.any():
            t = (r_outer - R[mask_face]) / face_width
            t = np.clip(t, 0, 1)
            Z[mask_face] = np.minimum(Z[mask_face], elev_top - t * bench_height)

        mask_berm = R < max(r_face_inner, 0)
        if mask_berm.any():
            Z[mask_berm] = np.minimum(Z[mask_berm], elev_bot)

    if noise_std > 0:
        rng = np.random.default_rng(42)
        Z += rng.normal(0, noise_std, Z.shape)

    vertices = []
    faces = []

    for i in range(ny):
        for j in range(nx):
            vertices.append([X[i, j], Y[i, j], Z[i, j]])

    for i in range(ny - 1):
        for j in range(nx - 1):
            v0 = i * nx + j
            v1 = v0 + 1
            v2 = (i + 1) * nx + j
            v3 = v2 + 1
            faces.append([v0, v1, v2])
            faces.append([v1, v3, v2])

    mesh = trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces))
    return mesh


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pit_mesh_design():
    """Mesh sintético de pit sin ruido (diseño)."""
    return create_pit_surface(
        nx=100,
        ny=100,
        bench_height=15.0,
        berm_width=9.0,
        face_angle_deg=70.0,
        n_benches=4,
        crest_elevation=3900.0,
        noise_std=0.0,
    )


@pytest.fixture()
def pit_mesh_asbuilt():
    """Mesh sintético de pit con ruido std=0.3m (as-built)."""
    return create_pit_surface(
        nx=100,
        ny=100,
        bench_height=15.0,
        berm_width=9.0,
        face_angle_deg=70.0,
        n_benches=4,
        crest_elevation=3900.0,
        noise_std=0.3,
    )


@pytest.fixture()
def sample_sections(pit_mesh_design):
    """5 secciones generadas con generate_sections_along_crest."""
    return generate_sections_along_crest(
        pit_mesh_design,
        start_point=np.array([100.0, 250.0]),
        end_point=np.array([400.0, 250.0]),
        n_sections=5,
        section_azimuth=0.0,
        section_length=400.0,
        sector_name="Sector Test",
    )


@pytest.fixture()
def sample_tolerances():
    """Tolerancias por parámetro para comparación."""
    return {
        "bench_height": {"neg": 1.0, "pos": 1.5},
        "face_angle": {"neg": 5.0, "pos": 5.0},
        "berm_width": {"min": 6.0},
        "inter_ramp_angle": {"neg": 3.0, "pos": 2.0},
        "overall_angle": {"neg": 2.0, "pos": 2.0},
    }


@pytest.fixture()
def mesh_stl_temp(pit_mesh_design):
    """
    Helper: crea un archivo STL temporal y lo elimina al finalizar el test.
    Returns the file path (str).
    """
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        pit_mesh_design.export(f.name)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)
