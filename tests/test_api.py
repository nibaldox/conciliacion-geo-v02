"""Integration tests for the FastAPI backend using TestClient.

Covers all 24 API endpoints across meshes, sections, process, settings,
and export routers. Uses an isolated SQLite database per test.
"""

import io
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.database as db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_test_stl(filepath: str) -> str:
    """Create a minimal valid STL file (tetrahedron) for testing."""
    with open(filepath, "w") as f:
        f.write("solid test\n")
        vertices = [(0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)]
        faces = [
            (vertices[0], vertices[1], vertices[2]),
            (vertices[0], vertices[1], vertices[3]),
            (vertices[0], vertices[2], vertices[3]),
            (vertices[1], vertices[2], vertices[3]),
        ]
        for v1, v2, v3 in faces:
            f.write("  facet normal 0 0 1\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
            f.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
            f.write(f"      vertex {v3[0]} {v3[1]} {v3[2]}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write("endsolid test\n")
    return filepath


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    yield


@pytest.fixture()
def client():
    """FastAPI TestClient (synchronous, suitable for all endpoints)."""
    return TestClient(app)


@pytest.fixture()
def session_id():
    """Create a session in the DB and return its ID."""
    return db.create_session()


@pytest.fixture()
def headers(session_id):
    """Headers carrying the session ID for request scoping."""
    return {"x-session-id": session_id}


@pytest.fixture()
def stl_path(tmp_path):
    """Create a test STL file and return its path."""
    return create_test_stl(str(tmp_path / "test_mesh.stl"))


def _upload_mesh(client, headers, stl_path, mesh_type="design"):
    """Upload a mesh and return the upload response JSON."""
    with open(stl_path, "rb") as f:
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("test.stl", f, "application/octet-stream")},
            data={"type": mesh_type},
            headers=headers,
        )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()


# ===================================================================
# 1. Health
# ===================================================================

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ===================================================================
# 2. Meshes
# ===================================================================

class TestMeshUpload:
    def test_upload_design(self, client, headers, stl_path):
        data = _upload_mesh(client, headers, stl_path, "design")
        assert "mesh_id" in data
        assert isinstance(data["n_vertices"], int)
        assert isinstance(data["n_faces"], int)
        assert data["n_vertices"] > 0
        assert data["n_faces"] > 0

    def test_upload_topo(self, client, headers, stl_path):
        data = _upload_mesh(client, headers, stl_path, "topo")
        assert "mesh_id" in data
        assert data["n_faces"] > 0

    def test_upload_invalid_type_400(self, client, headers, stl_path):
        with open(stl_path, "rb") as f:
            resp = client.post(
                "/api/v1/meshes/upload",
                files={"file": ("test.stl", f, "application/octet-stream")},
                data={"type": "invalid"},
                headers=headers,
            )
        assert resp.status_code == 400

    def test_upload_empty_file_400(self, client, headers):
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("empty.stl", b"", "application/octet-stream")},
            data={"type": "design"},
            headers=headers,
        )
        assert resp.status_code == 400


class TestMeshInfo:
    def test_info_after_upload(self, client, headers, stl_path):
        upload = _upload_mesh(client, headers, stl_path)
        mesh_id = upload["mesh_id"]

        resp = client.get(f"/api/v1/meshes/{mesh_id}/info", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == mesh_id
        assert data["type"] == "design"
        assert "bounds" in data

    def test_info_not_found_404(self, client, headers):
        resp = client.get("/api/v1/meshes/nonexistent/info", headers=headers)
        assert resp.status_code == 404


class TestMeshVertices:
    def test_vertices_after_upload(self, client, headers, stl_path):
        upload = _upload_mesh(client, headers, stl_path)
        mesh_id = upload["mesh_id"]

        resp = client.get(f"/api/v1/meshes/{mesh_id}/vertices", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "x" in data and "y" in data and "z" in data
        assert len(data["x"]) > 0


class TestMeshDelete:
    def test_delete_existing(self, client, headers, stl_path):
        upload = _upload_mesh(client, headers, stl_path)
        mesh_id = upload["mesh_id"]

        resp = client.delete(f"/api/v1/meshes/{mesh_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "Mesh deleted"

        # Verify it's gone
        resp = client.get(f"/api/v1/meshes/{mesh_id}/info", headers=headers)
        assert resp.status_code == 404

    def test_delete_not_found_404(self, client, headers):
        resp = client.delete("/api/v1/meshes/nonexistent", headers=headers)
        assert resp.status_code == 404


# ===================================================================
# 3. Sections
# ===================================================================

class TestSectionsList:
    def test_empty_list(self, client, headers):
        resp = client.get("/api/v1/sections", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []


class TestSectionsManual:
    def test_create_sections(self, client, headers):
        sections = [
            {"name": "S-01", "origin": [100.0, 200.0], "azimuth": 45.0, "length": 200.0, "sector": "A"},
            {"name": "S-02", "origin": [150.0, 200.0], "azimuth": 90.0, "length": 300.0, "sector": "B"},
        ]
        resp = client.post("/api/v1/sections/manual", json=sections, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "2 sections set" in data["message"]
        assert len(data["sections"]) == 2
        assert data["sections"][0]["name"] == "S-01"

    def test_list_after_create(self, client, headers):
        client.post(
            "/api/v1/sections/manual",
            json=[{"origin": [100.0, 200.0], "azimuth": 45.0}],
            headers=headers,
        )
        resp = client.get("/api/v1/sections", headers=headers)
        assert len(resp.json()) == 1


class TestSectionsClick:
    def test_click_manual_azimuth(self, client, headers):
        resp = client.post(
            "/api/v1/sections/click",
            json={"origin": [100.0, 200.0], "az_mode": "manual", "azimuth": 90.0},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "section" in data
        assert data["section"]["azimuth"] == 90.0
        assert data["total"] == 1

    def test_click_appends_to_existing(self, client, headers):
        # Create one section first
        client.post(
            "/api/v1/sections/manual",
            json=[{"origin": [50.0, 50.0], "azimuth": 0.0}],
            headers=headers,
        )
        # Click adds a second
        resp = client.post(
            "/api/v1/sections/click",
            json={"origin": [100.0, 200.0], "az_mode": "manual", "azimuth": 45.0},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2


class TestSectionsUpdate:
    def test_update_section(self, client, headers):
        client.post(
            "/api/v1/sections/manual",
            json=[{"name": "S-01", "origin": [100.0, 200.0], "azimuth": 45.0, "sector": "Old"}],
            headers=headers,
        )
        resp = client.put(
            "/api/v1/sections/0",
            json={"origin": [200.0, 300.0], "azimuth": 90.0, "sector": "New"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sector"] == "New"
        assert data["azimuth"] == 90.0

    def test_update_out_of_range_404(self, client, headers):
        resp = client.put(
            "/api/v1/sections/99",
            json={"origin": [0.0, 0.0], "azimuth": 0.0},
            headers=headers,
        )
        assert resp.status_code == 404


class TestSectionsDelete:
    def test_delete_section(self, client, headers):
        client.post(
            "/api/v1/sections/manual",
            json=[
                {"origin": [100.0, 200.0], "azimuth": 45.0},
                {"origin": [200.0, 300.0], "azimuth": 90.0},
            ],
            headers=headers,
        )
        resp = client.delete("/api/v1/sections/0", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_delete_out_of_range_404(self, client, headers):
        resp = client.delete("/api/v1/sections/99", headers=headers)
        assert resp.status_code == 404


class TestSectionsClear:
    def test_clear_all(self, client, headers):
        client.post(
            "/api/v1/sections/manual",
            json=[
                {"origin": [100.0, 200.0], "azimuth": 45.0},
                {"origin": [200.0, 300.0], "azimuth": 90.0},
            ],
            headers=headers,
        )
        resp = client.delete("/api/v1/sections", headers=headers)
        assert resp.status_code == 200

        # Verify empty
        resp = client.get("/api/v1/sections", headers=headers)
        assert resp.json() == []


class TestSectionsAuto:
    def test_auto_requires_design_mesh_400(self, client, headers):
        """Auto sections need a design mesh uploaded first."""
        resp = client.post(
            "/api/v1/sections/auto",
            json={"start": [100.0, 200.0], "end": [400.0, 200.0], "n_sections": 5},
            headers=headers,
        )
        assert resp.status_code == 400


class TestSectionsFromFile:
    def test_from_csv(self, client, headers, stl_path):
        """Upload a CSV file with X,Y columns to generate sections."""
        # Need design mesh first
        _upload_mesh(client, headers, stl_path, "design")

        csv_content = b"X,Y\n100.0,200.0\n200.0,200.0\n300.0,200.0\n400.0,200.0\n"
        resp = client.post(
            "/api/v1/sections/from-file",
            files={"file": ("sections.csv", csv_content, "text/csv")},
            data={"spacing": "50.0", "length": "200.0", "sector": "Test", "az_mode": "perpendicular"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        assert len(data["sections"]) > 0

    def test_from_csv_bad_columns_400(self, client, headers, stl_path):
        """CSV without recognizable X/Y columns returns 400."""
        _upload_mesh(client, headers, stl_path, "design")

        csv_content = b"foo,bar\naaa,bbb\n"
        resp = client.post(
            "/api/v1/sections/from-file",
            files={"file": ("bad.csv", csv_content, "text/csv")},
            data={"spacing": "50.0", "length": "200.0"},
            headers=headers,
        )
        assert resp.status_code == 400


# ===================================================================
# 4. Settings
# ===================================================================

class TestSettings:
    def test_get_defaults(self, client):
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "process" in data
        assert "tolerances" in data
        assert data["process"]["resolution"] == 0.5
        assert data["process"]["face_threshold"] == 40.0
        assert "bench_height" in data["tolerances"]

    def test_update_settings(self, client):
        new_settings = {
            "process": {"resolution": 1.0},
            "tolerances": {"bench_height": {"neg": 2.0, "pos": 3.0}},
        }
        resp = client.put("/api/v1/settings", json=new_settings)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Settings updated"
        assert data["settings"]["process"]["resolution"] == 1.0
        assert data["settings"]["tolerances"]["bench_height"]["neg"] == 2.0


# ===================================================================
# 5. Process
# ===================================================================

class TestProcessStatus:
    def test_status_idle(self, client):
        resp = client.get("/api/v1/process/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "idle"
        assert data["n_results"] == 0


class TestProcessResults:
    def test_results_empty(self, client):
        resp = client.get("/api/v1/process/results")
        assert resp.status_code == 200
        assert resp.json() == []


class TestProcessRun:
    def test_run_no_sections_400(self, client):
        """Running process without sections returns 400."""
        resp = client.post("/api/v1/process")
        assert resp.status_code == 400


class TestProcessProfiles:
    def test_profiles_out_of_range_404(self, client):
        """Profiles for nonexistent section index returns 404."""
        resp = client.get("/api/v1/process/profiles/0")
        assert resp.status_code == 404


# ===================================================================
# 6. Export
# ===================================================================

class TestExportExcel:
    def test_no_results_400(self, client):
        resp = client.get("/api/v1/export/excel")
        assert resp.status_code == 400


class TestExportWord:
    def test_no_results_400(self, client):
        resp = client.get("/api/v1/export/word")
        assert resp.status_code == 400


class TestExportDXF:
    def test_no_meshes_error(self, client):
        """DXF export without meshes should return an error."""
        resp = client.get("/api/v1/export/dxf")
        assert resp.status_code == 400


class TestExportImages:
    def test_no_results_400(self, client):
        resp = client.get("/api/v1/export/images")
        assert resp.status_code == 400
