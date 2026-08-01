"""Tests for the /api/v1/reconcile endpoint (spec §6)."""
import io
import os
import tempfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _upload_mesh(client, headers, mesh, type_: str) -> str:
    """Upload a trimesh as STL and return its mesh_id."""
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    buf.seek(0)
    resp = client.post(
        "/api/v1/meshes/upload",
        headers=headers,
        files={"file": ("mesh.stl", buf, "application/octet-stream")},
        data={"type": type_},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["mesh_id"]


def _session_headers(client):
    resp = client.get("/api/v1/health")
    session_id = resp.headers.get("x-session-id", "test")
    return {"X-Session-ID": session_id}


def _flat_quad_mesh(z_top: float, size: float = 30.0, offset: float = 10.0):
    import trimesh

    x0, y0 = offset, offset
    verts = np.array([
        [x0, y0, z_top], [x0 + size, y0, z_top],
        [x0 + size, y0 + size, z_top], [x0, y0 + size, z_top],
    ], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    return trimesh.Trimesh(vertices=verts, faces=faces)


class TestReconcileEndpoint:
    def test_identical_surfaces_full_compliance(self, client):
        headers = _session_headers(client)
        design = _flat_quad_mesh(100.0)
        topo = _flat_quad_mesh(100.0)
        d_id = _upload_mesh(client, headers, design, "design")
        t_id = _upload_mesh(client, headers, topo, "topo")
        resp = client.post(
            "/api/v1/reconcile",
            headers=headers,
            json={"design_mesh_id": d_id, "topo_mesh_id": t_id, "cell_size_m": 2.0, "tolerance_m": 1.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metrics"]["mean_error_m"] == pytest.approx(0.0, abs=1e-6)
        assert body["metrics"]["volume_remanente_m3"] == pytest.approx(0.0, abs=1e-6)
        assert body["metrics"]["volume_sobreexcavacion_m3"] == pytest.approx(0.0, abs=1e-6)
        assert body["status_counts"]["dentro_tolerancia"] == body["n_cells"]
        assert body["coverage_pct_topo"] == pytest.approx(100.0)
        assert "convention" in body

    def test_known_remanente_volume(self, client):
        headers = _session_headers(client)
        design = _flat_quad_mesh(100.0)
        topo = _flat_quad_mesh(98.0)  # 2 m above design -> remaining material
        d_id = _upload_mesh(client, headers, design, "design")
        t_id = _upload_mesh(client, headers, topo, "topo")
        resp = client.post(
            "/api/v1/reconcile",
            headers=headers,
            json={"design_mesh_id": d_id, "topo_mesh_id": t_id, "cell_size_m": 2.0, "tolerance_m": 0.5},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metrics"]["volume_remanente_m3"] == pytest.approx(30.0 * 30.0 * 2.0, rel=1e-3)
        assert body["status_counts"]["remanente"] == body["n_cells"]

    def test_non_overlapping_meshes_rejected(self, client):
        headers = _session_headers(client)
        design = _flat_quad_mesh(100.0, offset=10.0)
        topo = _flat_quad_mesh(100.0, offset=500.0)
        d_id = _upload_mesh(client, headers, design, "design")
        t_id = _upload_mesh(client, headers, topo, "topo")
        resp = client.post(
            "/api/v1/reconcile",
            headers=headers,
            json={"design_mesh_id": d_id, "topo_mesh_id": t_id},
        )
        assert resp.status_code == 400
        assert "extensión común" in resp.json()["detail"]

    def test_missing_mesh_404(self, client):
        headers = _session_headers(client)
        resp = client.post(
            "/api/v1/reconcile",
            headers=headers,
            json={"design_mesh_id": "nope", "topo_mesh_id": "nope"},
        )
        assert resp.status_code == 404

    def test_asymmetric_tolerance(self, client):
        headers = _session_headers(client)
        design = _flat_quad_mesh(100.0)
        topo = _flat_quad_mesh(99.0)  # deltaZ = -1.0 (remaining material)
        d_id = _upload_mesh(client, headers, design, "design")
        t_id = _upload_mesh(client, headers, topo, "topo")
        resp = client.post(
            "/api/v1/reconcile",
            headers=headers,
            json={
                "design_mesh_id": d_id, "topo_mesh_id": t_id, "cell_size_m": 2.0,
                "neg_tolerance_m": 1.5, "pos_tolerance_m": 0.3,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # -1.0 inside the negative tolerance (1.5) -> compliant
        assert body["status_counts"]["dentro_tolerancia"] == body["n_cells"]

    def test_asymmetric_tolerance_outside(self, client):
        headers = _session_headers(client)
        design = _flat_quad_mesh(100.0)
        topo = _flat_quad_mesh(99.0)
        d_id = _upload_mesh(client, headers, design, "design")
        t_id = _upload_mesh(client, headers, topo, "topo")
        resp = client.post(
            "/api/v1/reconcile",
            headers=headers,
            json={
                "design_mesh_id": d_id, "topo_mesh_id": t_id, "cell_size_m": 2.0,
                "neg_tolerance_m": 0.5, "pos_tolerance_m": 2.0,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status_counts"]["remanente"] == body["n_cells"]
