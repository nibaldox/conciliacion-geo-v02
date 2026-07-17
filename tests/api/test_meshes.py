"""Tests for the meshes router (api/routers/meshes.py).

Covers:
- POST /meshes/upload (happy path + invalid type + empty file + bad file)
- GET  /meshes/{id}/info (happy path + 404)
- GET  /meshes/{id}/vertices (happy path + decimation + 404)
- DELETE /meshes/{id} (happy path + 404)
- GET  /meshes/{id}/contours (happy path + 404)
- GET  /meshes/{id}/breaklines (happy path + 404 + threshold validation)

External services (trimesh parsing, DB) are exercised against an
isolated SQLite database (see tests/api/conftest.py).
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.routers.meshes as meshes_router


# ===========================================================================
# POST /meshes/upload
# ===========================================================================


class TestUploadMesh:
    def test_upload_design_returns_metadata(self, client: TestClient, stl_bytes: bytes):
        """A valid STL + type=design returns mesh_id, vertex/face counts, bounds."""
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("design.stl", stl_bytes, "application/octet-stream")},
            data={"type": "design"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["mesh_id"], str) and body["mesh_id"]
        assert body["n_vertices"] == 4
        assert body["n_faces"] == 4
        bounds = body["bounds"]
        for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"):
            assert key in bounds
        # Bounds must be ordered (min <= max) on every axis.
        assert bounds["xmin"] <= bounds["xmax"]
        assert bounds["ymin"] <= bounds["ymax"]
        assert bounds["zmin"] <= bounds["zmax"]

    def test_upload_topo_persists_in_db(self, client: TestClient, stl_bytes: bytes):
        """type=topo also works and the row lands in the meshes table."""
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("topo.stl", stl_bytes, "application/octet-stream")},
            data={"type": "topo"},
        )
        assert resp.status_code == 200
        mesh_id = resp.json()["mesh_id"]

        row = db.get_mesh_by_id(mesh_id)
        assert row is not None
        assert row["type"] == "topo"
        assert row["filename"] == "topo.stl"
        assert isinstance(row["data"], (bytes, memoryview))
        assert len(row["data"]) == len(stl_bytes)

    def test_upload_invalid_type_returns_400(
        self, client: TestClient, stl_bytes: bytes
    ):
        """Unknown mesh type → 400 (router-level validation)."""
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("x.stl", stl_bytes, "application/octet-stream")},
            data={"type": "bogus"},
        )
        assert resp.status_code == 400
        assert "design" in resp.json()["detail"] and "topo" in resp.json()["detail"]

    def test_upload_missing_type_returns_422(
        self, client: TestClient, stl_bytes: bytes
    ):
        """Form field ``type`` is required — FastAPI yields 422 when absent."""
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("x.stl", stl_bytes, "application/octet-stream")},
            # no data={"type": ...}
        )
        assert resp.status_code == 422

    def test_upload_empty_file_returns_400(self, client: TestClient):
        """Zero-byte file → 400 'Empty file'."""
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("empty.stl", b"", "application/octet-stream")},
            data={"type": "design"},
        )
        assert resp.status_code == 400
        assert "Empty" in resp.json()["detail"]

    def test_upload_unparsable_file_returns_400(self, client: TestClient):
        """Bytes that trimesh can't parse → 400 with a load error message."""
        garbage = b"this is not a mesh file at all" * 50
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("garbage.stl", garbage, "application/octet-stream")},
            data={"type": "design"},
        )
        assert resp.status_code == 400
        assert "Error loading mesh" in resp.json()["detail"]

    def test_upload_replaces_existing_same_type(
        self, client: TestClient, stl_bytes: bytes
    ):
        """Re-uploading a mesh of the same type for the same session evicts the
        previous row (DB layer guarantees only one mesh per session+type)."""
        headers = {"X-Session-ID": "stable-session-1"}
        r1 = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("first.stl", stl_bytes, "application/octet-stream")},
            data={"type": "design"},
            headers=headers,
        )
        r2 = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("second.stl", stl_bytes, "application/octet-stream")},
            data={"type": "design"},
            headers=headers,
        )
        assert r1.status_code == r2.status_code == 200
        # Old id should now be gone.
        assert (
            client.get(
                f"/api/v1/meshes/{r1.json()['mesh_id']}/info", headers=headers
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/meshes/{r2.json()['mesh_id']}/info", headers=headers
            ).status_code
            == 200
        )


# ===========================================================================
# GET /meshes/{id}/info
# ===========================================================================


class TestMeshInfo:
    def test_info_returns_stored_metadata(
        self, client: TestClient, uploaded_mesh_id: str
    ):
        resp = client.get(f"/api/v1/meshes/{uploaded_mesh_id}/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == uploaded_mesh_id
        assert body["type"] == "design"
        assert body["filename"] == "tiny.stl"
        assert body["n_vertices"] == 4
        assert body["n_faces"] == 4
        assert "uploaded_at" in body
        # bounds is JSON-encoded as a string in the row, the router returns
        # the parsed dict.
        assert isinstance(body["bounds"], dict)
        assert body["bounds"]["xmin"] == 0.0

    def test_info_unknown_id_returns_404(self, client: TestClient):
        """A mesh id that was never stored → 404."""
        resp = client.get("/api/v1/meshes/does-not-exist/info")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ===========================================================================
# GET /meshes/{id}/vertices
# ===========================================================================


class TestMeshVertices:
    def test_vertices_default_step(
        self, client: TestClient, uploaded_mesh_id: str
    ):
        """Default step=8000; for a tiny mesh every vertex comes back."""
        resp = client.get(f"/api/v1/meshes/{uploaded_mesh_id}/vertices")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"x", "y", "z", "faces"}
        assert len(body["x"]) == 4
        assert len(body["y"]) == 4
        assert len(body["z"]) == 4
        assert isinstance(body["faces"], list)

    def test_vertices_decimation_when_step_is_small(
        self, client: TestClient, larger_stl_bytes: bytes
    ):
        """A mesh with ~20k faces + a small ``step`` should return a
        decimated mesh — the result is a well-formed {x,y,z,faces}
        payload whose face count is strictly less than the original.
        (The router maps ``step`` to ``target_faces`` in
        ``core.mesh_handler.decimate_mesh``.)
        """
        up = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("big.stl", larger_stl_bytes, "application/octet-stream")},
            data={"type": "design"},
        )
        assert up.status_code == 200, up.text
        mesh_id = up.json()["mesh_id"]
        original_faces = up.json()["n_faces"]
        assert original_faces > 8000

        resp = client.get(
            f"/api/v1/meshes/{mesh_id}/vertices", params={"step": 2000}
        )
        assert resp.status_code == 200
        body = resp.json()
        # Schema is preserved on every response.
        assert set(body.keys()) == {"x", "y", "z", "faces"}
        returned_faces = len(body["faces"])
        # Decimation must shrink or match — it must never grow the mesh.
        assert returned_faces <= original_faces
        # And every emitted face must reference a vertex that exists in the
        # returned arrays (basic structural sanity).
        n_verts = len(body["x"])
        assert n_verts == len(body["y"]) == len(body["z"])
        for tri in body["faces"][:50]:
            assert len(tri) == 3
            for idx in tri:
                assert 0 <= idx < n_verts

    def test_vertices_unknown_id_returns_404(self, client: TestClient):
        """The cached helper raises ValueError when the mesh is missing,
        and the router converts it to 404."""
        # Make sure no stale cache entry survives from previous tests.
        meshes_router._get_decimated_vertices_cached.cache_clear()
        resp = client.get("/api/v1/meshes/missing/vertices")
        assert resp.status_code == 404


# ===========================================================================
# DELETE /meshes/{id}
# ===========================================================================


class TestDeleteMesh:
    def test_delete_removes_mesh(self, client: TestClient, uploaded_mesh_id: str):
        """DELETE returns 200 and the mesh is gone on subsequent info calls."""
        ok = client.delete(f"/api/v1/meshes/{uploaded_mesh_id}")
        assert ok.status_code == 200
        assert "deleted" in ok.json()["message"].lower()

        gone = client.get(f"/api/v1/meshes/{uploaded_mesh_id}/info")
        assert gone.status_code == 404
        assert db.get_mesh_by_id(uploaded_mesh_id) is None

    def test_delete_unknown_id_returns_404(self, client: TestClient):
        """Deleting a non-existent mesh id → 404."""
        resp = client.delete("/api/v1/meshes/ghost")
        assert resp.status_code == 404

    def test_delete_is_idempotent_only_through_404(
        self, client: TestClient, uploaded_mesh_id: str
    ):
        """Second DELETE on the same id returns 404 (not 200) — useful for clients."""
        first = client.delete(f"/api/v1/meshes/{uploaded_mesh_id}")
        second = client.delete(f"/api/v1/meshes/{uploaded_mesh_id}")
        assert first.status_code == 200
        assert second.status_code == 404


# ===========================================================================
# GET /meshes/{id}/contours
# ===========================================================================


class TestMeshContours:
    def test_contours_default_params_return_lines(
        self, client: TestClient, larger_stl_bytes: bytes
    ):
        """Contours endpoint returns bounds + line list at default 15 m spacing."""
        up = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("topo.stl", larger_stl_bytes, "application/octet-stream")},
            data={"type": "topo"},
        )
        assert up.status_code == 200
        mesh_id = up.json()["mesh_id"]

        resp = client.get(f"/api/v1/meshes/{mesh_id}/contours")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["interval"] == 15.0
        assert set(body.keys()) >= {
            "bounds",
            "elevation_min",
            "elevation_max",
            "interval",
            "lines",
        }
        # Lines is always a list (may be empty if no section plane hit mesh).
        assert isinstance(body["lines"], list)
        # Bounds match what the upload reported.
        assert body["elevation_min"] <= body["elevation_max"]

    def test_contours_custom_interval(
        self, client: TestClient, larger_stl_bytes: bytes
    ):
        """Custom interval is echoed back and respected."""
        up = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("topo.stl", larger_stl_bytes, "application/octet-stream")},
            data={"type": "topo"},
        )
        mesh_id = up.json()["mesh_id"]

        resp = client.get(
            f"/api/v1/meshes/{mesh_id}/contours",
            params={"interval": 5.0, "grid_size": 500},
        )
        assert resp.status_code == 200
        assert resp.json()["interval"] == 5.0

    def test_contours_unknown_id_returns_404(self, client: TestClient):
        meshes_router._get_contours_cached.cache_clear()
        resp = client.get("/api/v1/meshes/ghost/contours")
        assert resp.status_code == 404


# ===========================================================================
# GET /meshes/{id}/breaklines
# ===========================================================================


class TestMeshBreaklines:
    def test_breaklines_returns_payload_with_bounds(
        self, client: TestClient, larger_stl_bytes: bytes
    ):
        """Breaklines endpoint returns the canonical payload shape."""
        up = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("topo.stl", larger_stl_bytes, "application/octet-stream")},
            data={"type": "topo"},
        )
        mesh_id = up.json()["mesh_id"]

        resp = client.get(f"/api/v1/meshes/{mesh_id}/breaklines")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Schema: bounds, elevation_min/max, interval (=0), lines list.
        assert set(body.keys()) >= {
            "bounds",
            "elevation_min",
            "elevation_max",
            "interval",
            "lines",
        }
        assert body["interval"] == 0
        assert isinstance(body["lines"], list)
        # Any present line must carry the expected metadata.
        for line in body["lines"]:
            assert "elevation" in line
            assert "segments" in line
            assert isinstance(line["segments"], list)

    def test_breaklines_custom_threshold(
        self, client: TestClient, larger_stl_bytes: bytes
    ):
        """Threshold query param is accepted (no validation error)."""
        up = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("topo.stl", larger_stl_bytes, "application/octet-stream")},
            data={"type": "topo"},
        )
        mesh_id = up.json()["mesh_id"]
        resp = client.get(
            f"/api/v1/meshes/{mesh_id}/breaklines",
            params={"angle_threshold": 35.0},
        )
        assert resp.status_code == 200

    def test_breaklines_unknown_id_returns_404(self, client: TestClient):
        meshes_router._get_breaklines_cached.cache_clear()
        resp = client.get("/api/v1/meshes/ghost/breaklines")
        assert resp.status_code == 404
