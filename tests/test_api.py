"""Integration tests for the FastAPI backend using TestClient.

Covers all 24 API endpoints across meshes, sections, process, settings,
and export routers. Uses an isolated SQLite database per test.
"""

import asyncio
import io
import os
import queue
import tempfile
import threading
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
import api.database as db
import api.ai_agent_write_handlers as write_handlers
import api.routers.process as process_router
from api.ai_agent_write_handlers import run_reconciliation
from core.ai_v2.agent.models import RunReconciliationArgs


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


def _process_section_dict(name: str = "S-01") -> dict:
    return {
        "name": name,
        "origin": [0.0, 0.0],
        "azimuth": 0.0,
        "length": 20.0,
        "sector": "A",
    }


def _make_blocking_pipeline(entered, release):
    def fake_pipeline(session_id, sections_raw, body_overrides):
        if entered is not None:
            entered.set()
        release.wait(timeout=30)
        db.update_process_status(
            session_id, "complete", len(sections_raw), len(sections_raw)
        )
        return {
            "status": "complete",
            "total_sections": len(sections_raw),
            "total_results": 0,
            "profile_warnings": {},
        }

    return fake_pipeline


def _make_idle_write_counter():
    """Wrap db.update_process_status, counting only 'idle' writes."""
    real_update = db.update_process_status
    counter = {"idle": 0}

    def counting_update(session_id, status, *args):
        if status == "idle":
            counter["idle"] += 1
        return real_update(session_id, status, *args)

    return counting_update, counter


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


class TestSectionsCurve:
    def test_curve_sections_generation(self, client, headers):
        """Test generating sections perpendicular to a curve/polyline with 3D points."""
        resp = client.post(
            "/api/v1/sections/curve",
            json={
                "points": [[100.0, 100.0, 50.0], [150.0, 100.0, 52.0], [200.0, 100.0, 54.0]],
                "spacing": 50.0,
                "length": 200.0,
                "length_up": 120.0,
                "length_down": 80.0,
                "sector": "SectorTest",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        
        # Verify sections are stored in the DB
        list_resp = client.get("/api/v1/sections", headers=headers)
        assert list_resp.status_code == 200
        sections = list_resp.json()
        assert len(sections) > 0
        assert sections[0]["sector"] == "SectorTest"




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
        assert data["process"]["resolution"] == 0.1
        assert data["process"]["face_threshold"] == 30.0
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
    def test_run_no_sections_400(self, client, headers):
        """Running process without sections returns 400 and releases the claim."""
        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 400
        session = headers["x-session-id"]
        assert db.get_process_status(session)["status"] == "idle"

    def test_run_failure_resets_status_to_idle(self, client, headers, monkeypatch):
        """An unexpected pipeline failure resets process_status to idle."""
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])

        def explode(session_id, sections_raw, body_overrides):
            raise RuntimeError("pipeline exploded")

        monkeypatch.setattr(process_router, "_run_pipeline_sync", explode)
        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 500
        assert "pipeline exploded" in resp.json()["detail"]
        assert db.get_process_status(session)["status"] == "idle"

    def test_run_mesh_rejection_resets_status_to_idle(self, client, headers):
        """An HTTPException rejection inside the pipeline resets status to idle."""
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])
        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 400
        assert "design mesh not uploaded" in resp.json()["detail"]
        assert db.get_process_status(session)["status"] == "idle"

    def test_mesh_rejection_writes_idle_exactly_once(self, client, headers, monkeypatch):
        """Mesh-rejection route performs exactly one idle write."""
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])
        counting_update, counter = _make_idle_write_counter()
        monkeypatch.setattr(db, "update_process_status", counting_update)

        resp = client.post("/api/v1/process", headers=headers)

        assert resp.status_code == 400
        assert counter["idle"] == 1
        assert db.get_process_status(session)["status"] == "idle"

    def test_pipeline_runtime_error_writes_idle_exactly_once(
        self, client, headers, monkeypatch
    ):
        """Unexpected pipeline failure performs exactly one idle write."""
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])

        def explode(session_id, sections_raw, body_overrides):
            raise RuntimeError("pipeline exploded")

        counting_update, counter = _make_idle_write_counter()
        monkeypatch.setattr(db, "update_process_status", counting_update)
        monkeypatch.setattr(process_router, "_run_pipeline_sync", explode)

        resp = client.post("/api/v1/process", headers=headers)

        assert resp.status_code == 500
        assert counter["idle"] == 1
        assert db.get_process_status(session)["status"] == "idle"

    def test_no_sections_writes_idle_exactly_once(self, client, headers, monkeypatch):
        """No-sections 400 route performs exactly one idle write."""
        session = headers["x-session-id"]
        counting_update, counter = _make_idle_write_counter()
        monkeypatch.setattr(db, "update_process_status", counting_update)

        resp = client.post("/api/v1/process", headers=headers)

        assert resp.status_code == 400
        assert counter["idle"] == 1
        assert db.get_process_status(session)["status"] == "idle"

    def test_no_route_leaves_session_busy(self, client, headers, monkeypatch):
        """Claim, no-sections, failure and rejection routes all end non-busy."""
        session = headers["x-session-id"]
        real_pipeline = process_router._run_pipeline_sync

        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 400
        assert db.get_process_status(session)["status"] == "idle"

        db.save_sections(session, [_process_section_dict("S-01")])

        def explode(session_id, sections_raw, body_overrides):
            raise RuntimeError("pipeline exploded")

        monkeypatch.setattr(process_router, "_run_pipeline_sync", explode)
        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 500
        assert db.get_process_status(session)["status"] == "idle"

        monkeypatch.setattr(process_router, "_run_pipeline_sync", real_pipeline)
        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 400
        assert db.get_process_status(session)["status"] == "idle"

    def test_run_concurrent_posts_exactly_one_succeeds(self, headers, monkeypatch):
        """Two concurrent POST /process: one 200, one 409, no stuck states."""
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])
        release = threading.Event()
        responses = queue.Queue()
        monkeypatch.setattr(
            process_router,
            "_run_pipeline_sync",
            _make_blocking_pipeline(None, release),
        )
        start = threading.Barrier(2)

        with TestClient(app) as concurrent_client:
            def fire():
                start.wait(timeout=30)
                responses.put(concurrent_client.post("/api/v1/process", headers=headers))

            threads = [threading.Thread(target=fire) for _ in range(2)]
            for thread in threads:
                thread.start()
            rejected = responses.get(timeout=30)
            assert rejected.status_code == 409
            release.set()
            accepted = responses.get(timeout=30)
            for thread in threads:
                thread.join(timeout=30)
            assert all(not thread.is_alive() for thread in threads)

        assert sorted([accepted.status_code, rejected.status_code]) == [200, 409]
        assert db.get_process_status(session)["status"] == "complete"

    def test_ui_post_rejected_while_agent_holds_claim(self, client, headers, monkeypatch):
        """Agent run_reconciliation claims first: UI POST gets 409, agent completes."""
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])
        agent_entered = threading.Event()
        release = threading.Event()
        handler_result = {}
        counting_update, counter = _make_idle_write_counter()
        monkeypatch.setattr(db, "update_process_status", counting_update)
        monkeypatch.setattr(
            write_handlers,
            "_run_pipeline_sync",
            _make_blocking_pipeline(agent_entered, release),
        )

        def agent_run():
            handler_result["value"] = asyncio.run(
                run_reconciliation(session, RunReconciliationArgs())
            )

        agent_thread = threading.Thread(target=agent_run)
        agent_thread.start()
        assert agent_entered.wait(timeout=30), "agent pipeline never started"
        assert db.get_process_status(session)["status"] == "running"

        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["detail"] == process_router._MSG_PROCESS_RUNNING
        assert counter["idle"] == 0
        assert db.get_process_status(session)["status"] == "running"

        third = client.post("/api/v1/process", headers=headers)
        assert third.status_code == 409
        assert third.json()["detail"] == process_router._MSG_PROCESS_RUNNING
        assert counter["idle"] == 0
        assert db.get_process_status(session)["status"] == "running"

        release.set()
        agent_thread.join(timeout=30)
        assert handler_result["value"]["ok"] is True
        assert handler_result["value"]["status"] == "complete"
        assert counter["idle"] == 0
        assert db.get_process_status(session)["status"] == "complete"

    def test_agent_rejected_while_ui_holds_claim(self, client, headers, monkeypatch):
        """UI POST claims first: agent run_reconciliation gets process_running."""
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])
        ui_entered = threading.Event()
        agent_may_start = threading.Event()
        release = threading.Event()
        responses = queue.Queue()
        handler_result = {}
        counting_update, counter = _make_idle_write_counter()
        monkeypatch.setattr(db, "update_process_status", counting_update)
        monkeypatch.setattr(
            process_router,
            "_run_pipeline_sync",
            _make_blocking_pipeline(ui_entered, release),
        )

        def fire_ui():
            responses.put(client.post("/api/v1/process", headers=headers))

        def agent_run():
            agent_may_start.wait(timeout=30)
            handler_result["value"] = asyncio.run(
                run_reconciliation(session, RunReconciliationArgs())
            )

        ui_thread = threading.Thread(target=fire_ui)
        agent_thread = threading.Thread(target=agent_run)
        ui_thread.start()
        assert ui_entered.wait(timeout=30), "UI pipeline never started"
        agent_may_start.set()
        agent_thread.start()
        agent_thread.join(timeout=30)
        assert handler_result["value"] == {
            "ok": False,
            "error": "process_running",
            "message": write_handlers._MSG_PROCESS_RUNNING,
        }
        assert counter["idle"] == 0
        assert db.get_process_status(session)["status"] == "running"

        release.set()
        resp = responses.get(timeout=30)
        ui_thread.join(timeout=30)
        assert resp.status_code == 200
        assert counter["idle"] == 0
        assert db.get_process_status(session)["status"] == "complete"

    @pytest.mark.parametrize(
        "raise_http", [True, False], ids=["http_rejection", "runtime_error"]
    )
    def test_agent_pipeline_failure_writes_idle_exactly_once(
        self, headers, monkeypatch, raise_http
    ):
        """Agent flow performs exactly one idle write, owned by the frozen handler.

        The wrapper no longer resets: the handler's own except clauses are
        the sole idle writer when its pipeline fails.
        """
        session = headers["x-session-id"]
        db.save_sections(session, [_process_section_dict("S-01")])

        def explode(session_id, sections_raw, body_overrides):
            if raise_http:
                raise HTTPException(400, "mesh missing")
            raise RuntimeError("pipeline exploded")

        counting_update, counter = _make_idle_write_counter()
        monkeypatch.setattr(db, "update_process_status", counting_update)
        monkeypatch.setattr(write_handlers, "_run_pipeline_sync", explode)

        if raise_http:
            result = asyncio.run(run_reconciliation(session, RunReconciliationArgs()))
            assert result["ok"] is False
            assert result["error"] == "pipeline_rejected"
            assert "mesh missing" in result["message"]
        else:
            with pytest.raises(RuntimeError):
                asyncio.run(run_reconciliation(session, RunReconciliationArgs()))

        assert counter["idle"] == 1
        assert db.get_process_status(session)["status"] == "idle"

    def test_run_reports_profile_warnings_per_section(self, client, headers, stl_path, monkeypatch):
        import numpy as np
        from core import ProfileCutDiagnostics

        _upload_mesh(client, headers, stl_path, "design")
        _upload_mesh(client, headers, stl_path, "topo")
        sections = [
            {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"},
            {"name": "S-02", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"},
        ]
        sections_response = client.post(
            "/api/v1/sections/manual", json=sections, headers=headers,
        )
        assert sections_response.status_code == 200

        class MockProfile:
            def __init__(self):
                self.distances = np.array([0.0, 1.0])
                self.elevations = np.array([100.0, 100.0])

        import api.routers.process as process_router
        monkeypatch.setattr(
            process_router,
            "cut_mesh_with_section_diagnostics",
            lambda mesh, section: (
                ProfileCutDiagnostics(None, ("no_section_intersection",))
                if section.name == "S-01"
                else ProfileCutDiagnostics(
                    MockProfile(), ("minor_profile_reversal_normalized",)
                )
            ),
        )

        resp = client.post("/api/v1/process", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert data["total_sections"] == 2
        assert data["profile_warnings"] == {
            "S-01": {
                "design": ["no_section_intersection"],
                "topo": ["no_section_intersection"],
            },
            "S-02": {
                "design": ["minor_profile_reversal_normalized"],
                "topo": ["minor_profile_reversal_normalized"],
            },
        }

    def test_run_persists_completed_sections_in_status(self, client, headers, stl_path, monkeypatch):
        """After a full run, status reports completed_sections == total_sections."""
        import numpy as np
        from core import ProfileCutDiagnostics

        _upload_mesh(client, headers, stl_path, "design")
        _upload_mesh(client, headers, stl_path, "topo")
        sections = [
            {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"},
            {"name": "S-02", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"},
        ]
        sections_response = client.post(
            "/api/v1/sections/manual", json=sections, headers=headers,
        )
        assert sections_response.status_code == 200

        class MockProfile:
            def __init__(self):
                self.distances = np.array([0.0, 1.0])
                self.elevations = np.array([100.0, 100.0])

        import api.routers.process as process_router
        monkeypatch.setattr(
            process_router,
            "cut_mesh_with_section_diagnostics",
            lambda mesh, section: ProfileCutDiagnostics(MockProfile(), ()),
        )

        resp = client.post("/api/v1/process", headers=headers)
        assert resp.status_code == 200

        status = client.get("/api/v1/process/status", headers=headers).json()
        assert status["status"] == "complete"
        assert status["total_sections"] == 2
        assert status["completed_sections"] == status["total_sections"]


class TestProcessProfiles:
    def test_profiles_out_of_range_404(self, client):
        """Profiles for nonexistent section index returns 404."""
        resp = client.get("/api/v1/process/profiles/0")
        assert resp.status_code == 404

    def test_xyz_origin_profiles_match_xy_and_all_sections_return_200(
        self, client, headers, tmp_path
    ):
        import trimesh

        mesh = trimesh.Trimesh(
            vertices=[
                [0.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [10.0, 10.0, 10.0],
                [0.0, 10.0, 10.0],
            ],
            faces=[[0, 1, 2], [0, 2, 3]],
            process=False,
        )
        stl_path = str(tmp_path / "profile_surface.stl")
        mesh.export(stl_path)
        xyz_session = headers["x-session-id"]
        xy_headers = {"x-session-id": db.create_session()}
        for session_headers in (headers, xy_headers):
            _upload_mesh(client, session_headers, stl_path, "design")
            _upload_mesh(client, session_headers, stl_path, "topo")

        def section(name, origin):
            return {
                "name": name,
                "origin": origin,
                "azimuth": 90.0,
                "length": 20.0,
                "sector": "A",
            }

        db.save_sections(xyz_session, [
            section("S-00", [5.0, 5.0, 3500.0]),
            section("S-01", [5.0, 5.0, 3600.0]),
        ])
        db.save_sections(
            xy_headers["x-session-id"],
            [section("S-00", [5.0, 5.0])],
        )

        xyz_responses = [
            client.get(f"/api/v1/process/profiles/{index}", headers=headers)
            for index in range(2)
        ]
        xy_response = client.get("/api/v1/process/profiles/0", headers=xy_headers)

        assert [response.status_code for response in xyz_responses] == [200, 200]
        assert xy_response.status_code == 200
        xyz_profile = xyz_responses[0].json()
        xy_profile = xy_response.json()
        assert xyz_profile["design"] == xy_profile["design"]
        assert xyz_profile["topo"] == xy_profile["topo"]
        assert xyz_profile["horizontal_deviation"] == xy_profile["horizontal_deviation"]
        assert xyz_profile["profile_warnings"] == xy_profile["profile_warnings"]

    def test_profiles_success(self, client, headers, stl_path, monkeypatch):
        import numpy as np
        _upload_mesh(client, headers, stl_path, "design")
        _upload_mesh(client, headers, stl_path, "topo")
        sections = [
            {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"}
        ]
        resp = client.post("/api/v1/sections/manual", json=sections, headers=headers)
        assert resp.status_code == 200

        session_id = headers["x-session-id"]
        mock_ext_design = {
            "section_name": "S-01",
            "sector": "A",
            "benches": [
                {
                    "bench_number": 1,
                    "crest_elevation": 3900.0,
                    "crest_distance": 10.0,
                    "toe_elevation": 3885.0,
                    "toe_distance": 15.0,
                    "bench_height": 15.0,
                    "face_angle": 70.0,
                    "berm_width": 9.0,
                    "is_ramp": False,
                }
            ],
            "inter_ramp_angle": 45.0,
            "overall_angle": 45.0,
        }
        db.save_extraction(session_id, "S-01", "design", mock_ext_design)
        db.save_extraction(session_id, "S-01", "topo", mock_ext_design)

        class MockProfile:
            def __init__(self):
                self.distances = np.array([0.0, 5.0, 10.0, 15.0])
                self.elevations = np.array([3900.0, 3900.0, 3885.0, 3885.0])

        import api.routers.process as process_router
        from core import ProfileCutDiagnostics
        monkeypatch.setattr(
            process_router,
            "cut_mesh_with_section_diagnostics",
            lambda mesh, sec: ProfileCutDiagnostics(MockProfile()),
        )

        resp = client.get("/api/v1/process/profiles/0", headers=headers)
        assert resp.status_code == 200, f"Profiles failed: {resp.text}"
        data = resp.json()
        assert data["section_name"] == "S-01"
        assert "design" in data
        assert "topo" in data
        assert "reconciled_design" in data
        assert "reconciled_topo" in data
        assert data["horizontal_deviation"]["method"] == "horizontal_at_equal_elevation"
        assert data["horizontal_deviation"]["unit"] == "m"
        assert data["profile_warnings"] == {"design": [], "topo": []}

        diagnostics = iter((
            ProfileCutDiagnostics(None, ("no_section_intersection",)),
            ProfileCutDiagnostics(MockProfile()),
        ))
        monkeypatch.setattr(
            process_router,
            "cut_mesh_with_section_diagnostics",
            lambda mesh, sec: next(diagnostics),
        )

        resp = client.get("/api/v1/process/profiles/0", headers=headers)
        assert resp.status_code == 200
        missing_design = resp.json()
        assert "design" not in missing_design
        assert "topo" in missing_design
        assert "reconciled_design" not in missing_design
        assert missing_design["profile_warnings"] == {
            "design": ["no_section_intersection"],
            "topo": [],
        }

        diagnostics = iter((
            ProfileCutDiagnostics(MockProfile()),
            ProfileCutDiagnostics(MockProfile(), ("minor_profile_reversal_normalized",)),
        ))
        monkeypatch.setattr(
            process_router,
            "cut_mesh_with_section_diagnostics",
            lambda mesh, sec: next(diagnostics),
        )
        recovered_response = client.get("/api/v1/process/profiles/0", headers=headers)

        assert recovered_response.status_code == 200
        recovered = recovered_response.json()
        assert "topo" in recovered
        assert recovered["topo"]["distances"] == [0.0, 5.0, 10.0, 15.0]
        assert recovered["profile_warnings"] == {
            "design": [],
            "topo": ["minor_profile_reversal_normalized"],
        }


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

    def test_export_word_success(self, client, headers, stl_path, monkeypatch):
        import numpy as np
        _upload_mesh(client, headers, stl_path, "design")
        _upload_mesh(client, headers, stl_path, "topo")
        sections = [
            {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"}
        ]
        resp = client.post("/api/v1/sections/manual", json=sections, headers=headers)
        assert resp.status_code == 200
        
        session_id = headers["x-session-id"]
        mock_results = [
            {
                "section": "S-01",
                "bench_num": 1,
                "level": 3900.0,
                "height_design": 15.0,
                "height_real": 15.0,
                "height_dev": 0.0,
                "height_status": "CUMPLE",
                "angle_design": 70.0,
                "angle_real": 70.0,
                "angle_dev": 0.0,
                "angle_status": "CUMPLE",
                "berm_design": 9.0,
                "berm_real": 9.0,
                "berm_dev": 0.0,
                "berm_status": "CUMPLE",
                "berm_min": 6.0,
            }
        ]
        db.save_results(session_id, mock_results)
        
        mock_ext_design = {
            "section_name": "S-01",
            "sector": "A",
            "benches": [
                {
                    "bench_number": 1,
                    "crest_elevation": 3900.0,
                    "crest_distance": 10.0,
                    "toe_elevation": 3885.0,
                    "toe_distance": 15.0,
                    "bench_height": 15.0,
                    "face_angle": 70.0,
                    "berm_width": 9.0,
                    "is_ramp": False,
                }
            ],
            "inter_ramp_angle": 45.0,
            "overall_angle": 45.0,
        }
        db.save_extraction(session_id, "S-01", "design", mock_ext_design)
        db.save_extraction(session_id, "S-01", "topo", mock_ext_design)

        class MockProfile:
            def __init__(self):
                self.distances = np.array([0.0, 5.0, 10.0, 15.0])
                self.elevations = np.array([3900.0, 3900.0, 3885.0, 3885.0])
        
        import core
        monkeypatch.setattr(core, "cut_both_surfaces", lambda m_d, m_t, sec: (None, None))

        resp = client.get("/api/v1/export/word", headers=headers)
        assert resp.status_code == 200, f"Export Word failed: {resp.text}"
        assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TestExportDXF:
    def test_no_meshes_error(self, client):
        """DXF export without meshes should return an error."""
        resp = client.get("/api/v1/export/dxf")
        assert resp.status_code == 400


class TestExportImages:
    def test_no_results_400(self, client):
        resp = client.get("/api/v1/export/images")
        assert resp.status_code == 400
