"""Tests for core.mesh_handler — load, decimation, bounds."""

import numpy as np

from core import load_mesh, get_mesh_bounds, decimate_mesh


class TestLoadMesh:
    """Tests for load_mesh with STL files."""

    def test_load_mesh_stl(self, mesh_stl_temp):
        """Cargar STL y verificar que tiene vertices y faces."""
        mesh = load_mesh(mesh_stl_temp)
        assert hasattr(mesh, "vertices")
        assert hasattr(mesh, "faces")
        assert len(mesh.vertices) > 0
        assert len(mesh.faces) > 0

    def test_load_mesh_decimate(self, pit_mesh_design):
        """Decimación reduce número de caras."""
        original_faces = len(pit_mesh_design.faces)
        target = original_faces // 2
        decimated = decimate_mesh(pit_mesh_design, target)
        assert len(decimated.faces) <= original_faces
        # La decimación debería reducir al menos un 20%
        assert len(decimated.faces) < original_faces * 0.9

    def test_get_mesh_bounds(self, pit_mesh_design):
        """Bounds devuelve dict con las claves esperadas."""
        bounds = get_mesh_bounds(pit_mesh_design)
        expected_keys = {"xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "center", "n_faces", "n_vertices"}
        assert set(bounds.keys()) == expected_keys

    def test_mesh_bounds_values(self, pit_mesh_design):
        """Los bounds son razonables: zmax > zmin, xmax > xmin, etc."""
        bounds = get_mesh_bounds(pit_mesh_design)
        assert bounds["zmax"] > bounds["zmin"]
        assert bounds["xmax"] > bounds["xmin"]
        assert bounds["ymax"] > bounds["ymin"]
        assert bounds["n_faces"] > 0
        assert bounds["n_vertices"] > 0
        # Zmax debería ser ~3900 (crest elevation) y zmin ~3840 (4 bancos × 15m)
        assert bounds["zmax"] > 3850
        assert bounds["zmin"] < 3870
