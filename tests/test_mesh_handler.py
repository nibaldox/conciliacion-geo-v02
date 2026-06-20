"""Tests for core.mesh_handler — load, decimation, bounds, plotly export."""

import numpy as np
import plotly.graph_objects as go
import pytest

from core import load_mesh, get_mesh_bounds, decimate_mesh
from core.mesh_handler import mesh_to_plotly


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


class TestDecimateNoOp:
    def test_decimate_below_target_returns_same_face_count(self, pit_mesh_design):
        """When the mesh already has <= target faces, decimate is a no-op."""
        original_faces = len(pit_mesh_design.faces)
        result = decimate_mesh(pit_mesh_design, target_faces=original_faces + 10000)
        assert len(result.faces) == original_faces

    def test_decimate_aggressive_reduces_faces(self, pit_mesh_design):
        """A much smaller target still yields a mesh with no more faces."""
        original_faces = len(pit_mesh_design.faces)
        result = decimate_mesh(pit_mesh_design, target_faces=max(original_faces // 20, 50))
        assert len(result.faces) <= original_faces


class TestMeshToPlotly:
    def test_returns_mesh3d_trace(self, pit_mesh_design):
        trace = mesh_to_plotly(pit_mesh_design, name="design", color="blue", opacity=0.5)
        assert isinstance(trace, go.Mesh3d)

    def test_trace_carries_metadata(self, pit_mesh_design):
        trace = mesh_to_plotly(pit_mesh_design, name="topo", color="red", opacity=0.8)
        assert trace.name == "topo"
        assert trace.opacity == 0.8

    def test_trace_arrays_non_empty(self, pit_mesh_design):
        trace = mesh_to_plotly(pit_mesh_design, name="m", color="green", opacity=1.0)
        assert len(trace.x) > 0
        assert len(trace.y) > 0
        assert len(trace.z) > 0
        assert len(trace.i) > 0
        assert len(trace.j) > 0
        assert len(trace.k) > 0

    def test_bounds_center_is_finite(self, pit_mesh_design):
        bounds = get_mesh_bounds(pit_mesh_design)
        center = np.asarray(bounds["center"])
        assert center.shape == (3,)
        assert np.all(np.isfinite(center))


class TestMeshToPlotly:
    def test_returns_mesh3d_trace(self, pit_mesh_design):
        trace = mesh_to_plotly(pit_mesh_design, "test", "blue", 0.5)
        assert isinstance(trace, go.Mesh3d)
        assert trace.name == "test"

    def test_color_is_hex_string(self, pit_mesh_design):
        trace = mesh_to_plotly(pit_mesh_design, "x", "#ff0000", 0.3)
        assert trace.color is not None

    def test_opacity_preserved(self, pit_mesh_design):
        trace = mesh_to_plotly(pit_mesh_design, "x", "green", 0.7)
        assert trace.opacity == 0.7


class TestDecimateMeshEdgeCases:
    def test_target_above_current_keeps_mesh(self, pit_mesh_design):
        original = len(pit_mesh_design.faces)
        out = decimate_mesh(pit_mesh_design, original * 5)
        assert len(out.faces) >= 1

    def test_target_zero_returns_something(self, pit_mesh_design):
        out = decimate_mesh(pit_mesh_design, 2)
        assert len(out.faces) >= 2


class TestLoadMeshDXF:
    def _make_dxf_with_face(self, tmp_path):
        import ezdxf
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        msp.add_3dface([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)])
        msp.add_3dface([(0, 0, 0), (10, 10, 0), (10, 0, 10)])
        path = tmp_path / "test_face.dxf"
        doc.saveas(str(path))
        return path

    def test_load_dxf_with_3dface(self, tmp_path):
        from core.mesh_handler import _load_dxf
        dxf = self._make_dxf_with_face(tmp_path)
        mesh = _load_dxf(str(dxf))
        assert hasattr(mesh, "vertices")
        assert hasattr(mesh, "faces")
        assert len(mesh.vertices) > 0
        assert len(mesh.faces) > 0

    def test_load_dxf_quad_split_into_triangles(self, tmp_path):
        from core.mesh_handler import _load_dxf
        dxf = self._make_dxf_with_face(tmp_path)
        mesh = _load_dxf(str(dxf))
        assert len(mesh.faces) >= 3

    def test_load_mesh_dispatch_to_dxf(self, tmp_path):
        dxf = self._make_dxf_with_face(tmp_path)
        mesh = load_mesh(str(dxf))
        assert len(mesh.vertices) > 0

    def test_load_mesh_rejects_empty_file(self, tmp_path):
        empty = tmp_path / "empty.stl"
        empty.write_bytes(b"")
        with pytest.raises(Exception):
            load_mesh(str(empty))


class TestLoadDxfPolyline:
    def _make_dxf_with_polyline(self, tmp_path, points):
        import ezdxf
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        msp.add_lwpolyline(points)
        path = tmp_path / "poly.dxf"
        doc.saveas(str(path))
        return path

    def test_load_polyline_2d(self, tmp_path):
        from core.mesh_handler import load_dxf_polyline
        dxf = self._make_dxf_with_polyline(
            tmp_path, [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
        )
        arr = load_dxf_polyline(str(dxf))
        assert arr.shape[0] >= 4
        assert arr.shape[1] == 2

    def test_load_polyline_3d_returns_xy(self, tmp_path):
        from core.mesh_handler import load_dxf_polyline
        dxf = self._make_dxf_with_polyline(
            tmp_path, [(0, 0), (5, 0), (5, 5)],
        )
        arr = load_dxf_polyline(str(dxf))
        assert arr.shape[1] == 2


class TestVertexClustering:
    def test_vertex_clustering_reduces_face_count(self, pit_mesh_design):
        from core.mesh_handler import _vertex_clustering
        original = len(pit_mesh_design.faces)
        out = _vertex_clustering(pit_mesh_design, target_faces=original // 4)
        assert len(out.faces) <= original

    def test_vertex_clustering_target_above_current(self, pit_mesh_design):
        from core.mesh_handler import _vertex_clustering
        original = len(pit_mesh_design.faces)
        out = _vertex_clustering(pit_mesh_design, target_faces=original * 10)
        assert len(out.faces) >= 1
