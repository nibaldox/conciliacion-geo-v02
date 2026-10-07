import io
import os
import sqlite3
import tempfile
from pathlib import Path

import ezdxf
import numpy as np

import api.database as db
import api.dxf_uploads as dxf_uploads
import api.routers.meshes as meshes_router


def _dxf_bytes(layer="SURFACE", x_offset=0):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.new(layer)
    msp = doc.modelspace()
    msp.add_3dface([(x_offset, 0, 0), (x_offset + 10, 0, 0), (x_offset + 10, 10, 1), (x_offset, 10, 1)], dxfattribs={"layer": layer})
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _inspect(client, payload=None, session="dxf-owner", filename="surface.dxf", mesh_type="design"):
    return client.post(
        "/api/v1/meshes/dxf/inspect",
        files={"file": (filename, payload or _dxf_bytes(), "application/dxf")},
        data={"type": mesh_type},
        headers={"X-Session-ID": session},
    )


def test_confirm_persists_import_and_rebuilds_mesh(client):
    inspected = _inspect(client)
    assert inspected.status_code == 200, inspected.text
    payload = inspected.json()
    assert payload["layers"][0]["name"] == "SURFACE"
    assert payload["upload_id"]

    confirmed = client.post(
        "/api/v1/meshes/dxf/confirm",
        json={"upload_id": payload["upload_id"], "layers": ["SURFACE"], "units": 6},
        headers={"X-Session-ID": "dxf-owner"},
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    row = db.get_mesh_by_id(result["mesh_id"])
    assert row["import_options"] == {"layers": ["SURFACE"], "units": 6}
    assert row["import_report"]["scale_factor"] == 1.0
    assert client.get(
        f"/api/v1/meshes/{result['mesh_id']}/info", headers={"X-Session-ID": "dxf-owner"}
    ).json()["import_report"] == row["import_report"]

    db.get_trimesh_by_id.cache_clear()
    rebuilt = db.get_trimesh_by_id(result["mesh_id"])
    np.testing.assert_allclose(rebuilt.bounds, [[0, 0, 0], [10, 10, 1]])
    assert db.get_mesh("dxf-owner", "design")["import_options"] == {"layers": ["SURFACE"], "units": 6}


def test_cancel_and_session_isolation(client):
    inspected = _inspect(client, session="dxf-a")
    upload_id = inspected.json()["upload_id"]
    foreign = client.delete(f"/api/v1/meshes/dxf/{upload_id}", headers={"X-Session-ID": "dxf-b"})
    assert foreign.status_code == 404
    assert db.get_mesh("dxf-a", "design") is None
    cancelled = client.delete(f"/api/v1/meshes/dxf/{upload_id}", headers={"X-Session-ID": "dxf-a"})
    assert cancelled.status_code == 200
    assert client.post(
        "/api/v1/meshes/dxf/confirm",
        json={"upload_id": upload_id, "layers": ["SURFACE"], "units": 6},
        headers={"X-Session-ID": "dxf-a"},
    ).status_code == 404


def test_failed_confirmation_keeps_existing_mesh(client, stl_bytes):
    headers = {"X-Session-ID": "dxf-existing"}
    original = client.post(
        "/api/v1/meshes/upload",
        files={"file": ("old.stl", stl_bytes, "application/octet-stream")},
        data={"type": "design"},
        headers=headers,
    ).json()["mesh_id"]
    inspected = _inspect(client, session="dxf-existing")
    bad = client.post(
        "/api/v1/meshes/dxf/confirm",
        json={"upload_id": inspected.json()["upload_id"], "layers": ["EMPTY"], "units": 6},
        headers=headers,
    )
    assert bad.status_code == 422
    assert db.get_mesh_by_id(original) is not None


def test_expiration_removes_temporary_upload(monkeypatch):
    handle, path = tempfile.mkstemp(suffix=".dxf")
    import os
    os.close(handle)
    stored = dxf_uploads.store(path, "expire-session", "surface.dxf", "topo", 0)
    with dxf_uploads._lock:
        dxf_uploads._uploads[stored["upload_id"]]["expires"] = 0
    dxf_uploads.cleanup_expired()
    assert dxf_uploads.get(stored["upload_id"], "expire-session") is None
    assert not Path(path).exists()


def test_temp_owner_detection_preserves_current_directory():
    assert dxf_uploads._process_alive(os.getpid())
    assert not dxf_uploads._process_alive(2_000_000_000)
    dxf_uploads._instance_dir.mkdir(parents=True, exist_ok=True)
    assert dxf_uploads._is_managed_directory(dxf_uploads._instance_dir)
    assert dxf_uploads._instance_dir.exists()


def test_init_db_adds_import_metadata_to_legacy_mesh_table(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy_path)
    conn.executescript("""
        CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, settings TEXT DEFAULT '{}', sections TEXT DEFAULT '[]',
            process_status TEXT DEFAULT 'idle', current_section INTEGER DEFAULT 0,
            total_sections INTEGER DEFAULT 0, completed_sections INTEGER DEFAULT 0);
        CREATE TABLE meshes (id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
            type TEXT, filename TEXT, data BLOB, n_vertices INTEGER, n_faces INTEGER, bounds TEXT,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", legacy_path)
    db.init_db()
    conn = sqlite3.connect(legacy_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(meshes)")}
    conn.close()
    assert {"import_options", "import_report"} <= columns


def test_nonoverlapping_surface_bounds_add_machine_warning(client):
    first = _inspect(client, _dxf_bytes(x_offset=100), session="dxf-overlap")
    first_body = first.json()
    uploaded = client.post(
        "/api/v1/meshes/dxf/confirm",
        json={"upload_id": first_body["upload_id"], "layers": ["SURFACE"], "units": 6},
        headers={"X-Session-ID": "dxf-overlap"},
    )
    assert uploaded.status_code == 200, uploaded.text
    second = _inspect(client, session="dxf-overlap", filename="topo.dxf", mesh_type="topo")
    second_body = second.json()
    confirmed = client.post(
        "/api/v1/meshes/dxf/confirm",
        json={"upload_id": second_body["upload_id"], "layers": ["SURFACE"], "units": 6},
        headers={"X-Session-ID": "dxf-overlap"},
    )
    assert "SURFACES_NO_XY_OVERLAP" in confirmed.json()["import_report"]["warnings"]
