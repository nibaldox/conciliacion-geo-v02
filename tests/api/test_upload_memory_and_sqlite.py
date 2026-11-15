"""Upload memory and SQLite busy-timeout contracts.

Mesh upload handlers must drop trimesh's derived caches before the first
database await, so only vertices and faces stay alive while blobs are
written. Every connection to the main database must wait for
``DEPLOY.sqlite_busy_timeout_s`` instead of sqlite3's 5 s default.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterator, List

import ezdxf
import io
import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.routers.meshes as meshes_router
import core
from core import load_mesh
from core.config import DEPLOY

UPLOAD_PATH = "/api/v1/meshes/upload"
DXF_INSPECT_PATH = "/api/v1/meshes/dxf/inspect"
DXF_CONFIRM_PATH = "/api/v1/meshes/dxf/confirm"
UPLOAD_HEADERS = {"X-Session-ID": "api-upload-memory-sqlite-tests"}
DXF_HEADERS = {"X-Session-ID": "api-upload-memory-sqlite-dxf"}


def _ndarray_cache_keys(mesh: Any) -> List[str]:
    return sorted(key for key, value in mesh._cache.cache.items() if isinstance(value, np.ndarray))


def _dxf_bytes() -> bytes:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.new("SURFACE")
    msp = doc.modelspace()
    msp.add_3dface(
        [(0, 0, 0), (10, 0, 0), (10, 10, 1), (0, 10, 1)],
        dxfattribs={"layer": "SURFACE"},
    )
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


@pytest.fixture()
def handler_probe(monkeypatch: pytest.MonkeyPatch) -> Iterator[Dict[str, Any]]:
    """Record the trimesh cache state the handlers hand to the database.

    ``first_db_ndarray_keys`` is the ndarray cache keys of the most recently
    parsed mesh at the first database call that follows the parse (session
    middleware calls run before parsing and are ignored). ``saves`` records
    the cache keys, vertices and faces seen by ``db.save_mesh_arrays``.
    """
    probe: Dict[str, Any] = {
        "parsed": [],
        "first_db_ndarray_keys": None,
        "saves": [],
    }

    def keep(mesh: Any) -> Any:
        probe["parsed"].append(mesh)
        return mesh

    real_load_mesh = meshes_router.load_mesh
    monkeypatch.setattr(meshes_router, "load_mesh", lambda path: keep(real_load_mesh(path)))

    real_import_dxf = core.import_dxf_surface

    def import_and_keep(*args: Any, **kwargs: Any):
        mesh, report = real_import_dxf(*args, **kwargs)
        keep(mesh)
        return mesh, report

    monkeypatch.setattr(core, "import_dxf_surface", import_and_keep)

    def before_first_db_await(real: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if probe["parsed"] and probe["first_db_ndarray_keys"] is None:
                probe["first_db_ndarray_keys"] = _ndarray_cache_keys(probe["parsed"][-1])
            return real(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(db, "get_or_create_session", before_first_db_await(db.get_or_create_session))
    monkeypatch.setattr(db, "get_mesh", before_first_db_await(db.get_mesh))

    real_save_mesh_arrays = db.save_mesh_arrays

    def save_probe(mesh_id: str, mesh: Any) -> None:
        probe["saves"].append(
            {
                "mesh_id": mesh_id,
                "ndarray_keys": _ndarray_cache_keys(mesh),
                "vertices": np.array(mesh.vertices, copy=True),
                "faces": np.array(mesh.faces, copy=True),
            }
        )
        return real_save_mesh_arrays(mesh_id, mesh)

    monkeypatch.setattr(db, "save_mesh_arrays", save_probe)
    yield probe


class TestStlUploadDropsDerivedCaches:
    def test_stl_upload_drops_trimesh_caches_before_database(
        self,
        client: TestClient,
        larger_stl_bytes: bytes,
        handler_probe: Dict[str, Any],
        tmp_path,
    ):
        response = client.post(
            UPLOAD_PATH,
            headers=UPLOAD_HEADERS,
            files={"file": ("topo.stl", larger_stl_bytes, "application/octet-stream")},
            data={"type": "topo"},
        )
        assert response.status_code == 200, response.text
        assert handler_probe["first_db_ndarray_keys"] is not None, "probe never saw a database call"
        assert handler_probe["first_db_ndarray_keys"] == []

        (save,) = handler_probe["saves"]
        assert save["ndarray_keys"] == []

        source = tmp_path / "topo.stl"
        source.write_bytes(larger_stl_bytes)
        expected = load_mesh(str(source))
        assert np.array_equal(save["vertices"], expected.vertices)
        assert np.array_equal(save["faces"], expected.faces)

        stored = db.load_mesh_arrays(response.json()["mesh_id"])
        assert stored is not None
        assert np.array_equal(stored.vertices, expected.vertices)
        assert np.array_equal(stored.faces, expected.faces)


class TestDxfConfirmDropsDerivedCaches:
    def test_dxf_confirm_drops_trimesh_caches_before_database(
        self, client: TestClient, handler_probe: Dict[str, Any], tmp_path
    ):
        inspected = client.post(
            DXF_INSPECT_PATH,
            headers=DXF_HEADERS,
            files={"file": ("surface.dxf", _dxf_bytes(), "application/dxf")},
            data={"type": "design"},
        )
        assert inspected.status_code == 200, inspected.text
        confirmed = client.post(
            DXF_CONFIRM_PATH,
            headers=DXF_HEADERS,
            json={"upload_id": inspected.json()["upload_id"], "layers": ["SURFACE"], "units": 6},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert handler_probe["first_db_ndarray_keys"] is not None, "probe never saw a database call"
        assert handler_probe["first_db_ndarray_keys"] == []

        (save,) = handler_probe["saves"]
        assert save["ndarray_keys"] == []

        from core.dxf_import import import_dxf_surface

        source = tmp_path / "surface.dxf"
        source.write_bytes(_dxf_bytes())
        expected, _ = import_dxf_surface(str(source), layers=["SURFACE"], units=6)
        assert np.array_equal(save["vertices"], expected.vertices)
        assert np.array_equal(save["faces"], expected.faces)


class TestSqliteBusyTimeout:
    def test_get_connection_reports_deploy_busy_timeout(self, isolated_data_dir):
        conn = db.get_connection()
        try:
            busy_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        finally:
            conn.close()
        assert busy_ms == round(DEPLOY.sqlite_busy_timeout_s * 1000) == 30000

    def test_get_connection_passes_deploy_timeout_to_sqlite(
        self, isolated_data_dir, monkeypatch: pytest.MonkeyPatch
    ):
        captured: List[Dict[str, Any]] = []
        real_connect = sqlite3.connect

        def recording_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            captured.append(kwargs)
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(db.sqlite3, "connect", recording_connect)
        conn = db.get_connection()
        conn.close()
        assert len(captured) == 1
        assert captured[0].get("timeout") == DEPLOY.sqlite_busy_timeout_s == 30.0
