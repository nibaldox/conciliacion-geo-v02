"""Session ownership tests for mesh-ID routes (unit B).

Contract: every mesh route that receives an id — info, vertices, contours,
breaklines, delete — resolves the mesh through the requesting session. The
owner keeps access; a different session, a request without ``X-Session-ID``
(middleware-generated session) and unknown ids receive the same 404 without
filenames, geometry, or delete side effects.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.database as db

OWNER_SESSION = "mesh-owner-session"
OUTSIDER_SESSION = "mesh-outsider-session"
OWNER_HEADERS = {"X-Session-ID": OWNER_SESSION}
OUTSIDER_HEADERS = {"X-Session-ID": OUTSIDER_SESSION}
READER_SUFFIXES = ("info", "vertices", "contours", "breaklines")
CACHED_SUFFIXES = ("vertices", "contours", "breaklines")
PAYLOAD_KEYS = {
    "info": {"id", "type", "filename", "n_vertices", "n_faces", "bounds"},
    "vertices": {"x", "y", "z", "faces"},
    "contours": {"bounds", "elevation_min", "elevation_max", "interval", "lines"},
    "breaklines": {"bounds", "elevation_min", "elevation_max", "interval", "lines"},
}


def _upload(client: TestClient, stl_bytes: bytes, session: str, filename: str) -> str:
    resp = client.post(
        "/api/v1/meshes/upload",
        files={"file": (filename, stl_bytes, "application/octet-stream")},
        data={"type": "design"},
        headers={"X-Session-ID": session},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["mesh_id"]


@pytest.fixture()
def owner_mesh(client: TestClient, stl_bytes: bytes) -> str:
    return _upload(client, stl_bytes, OWNER_SESSION, "secret-pit.stl")


@pytest.mark.parametrize("suffix", READER_SUFFIXES)
class TestMeshReadersRequireOwnership:
    def test_owner_keeps_access(self, client: TestClient, owner_mesh: str, suffix: str):
        resp = client.get(f"/api/v1/meshes/{owner_mesh}/{suffix}", headers=OWNER_HEADERS)
        assert resp.status_code == 200, resp.text
        assert PAYLOAD_KEYS[suffix] <= set(resp.json())

    def test_outsider_session_gets_404_without_leaks(
        self, client: TestClient, owner_mesh: str, suffix: str
    ):
        resp = client.get(f"/api/v1/meshes/{owner_mesh}/{suffix}", headers=OUTSIDER_HEADERS)
        assert resp.status_code == 404
        assert set(resp.json()) == {"detail"}
        assert resp.json()["detail"] == "Mesh not found"
        assert "secret-pit.stl" not in resp.text

    def test_request_without_session_gets_404(
        self, client: TestClient, owner_mesh: str, suffix: str
    ):
        resp = client.get(f"/api/v1/meshes/{owner_mesh}/{suffix}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Mesh not found"
        assert "secret-pit.stl" not in resp.text

    def test_unknown_id_gets_404(self, client: TestClient, suffix: str):
        resp = client.get(f"/api/v1/meshes/does-not-exist/{suffix}", headers=OWNER_HEADERS)
        assert resp.status_code == 404


@pytest.mark.parametrize("suffix", CACHED_SUFFIXES)
def test_warmed_cache_is_not_served_to_outsiders(
    client: TestClient, owner_mesh: str, suffix: str
):
    warm = client.get(f"/api/v1/meshes/{owner_mesh}/{suffix}", headers=OWNER_HEADERS)
    assert warm.status_code == 200, warm.text
    intruder = client.get(f"/api/v1/meshes/{owner_mesh}/{suffix}", headers=OUTSIDER_HEADERS)
    assert intruder.status_code == 404
    assert intruder.json()["detail"] == "Mesh not found"


class TestDeleteRequiresOwnership:
    def test_outsider_cannot_delete(self, client: TestClient, owner_mesh: str):
        resp = client.delete(f"/api/v1/meshes/{owner_mesh}", headers=OUTSIDER_HEADERS)
        assert resp.status_code == 404
        assert "secret-pit.stl" not in resp.text
        assert db.get_mesh_by_id(owner_mesh) is not None
        owner_view = client.get(f"/api/v1/meshes/{owner_mesh}/info", headers=OWNER_HEADERS)
        assert owner_view.status_code == 200

    def test_request_without_session_cannot_delete(self, client: TestClient, owner_mesh: str):
        resp = client.delete(f"/api/v1/meshes/{owner_mesh}")
        assert resp.status_code == 404
        assert db.get_mesh_by_id(owner_mesh) is not None

    def test_owner_can_delete(self, client: TestClient, owner_mesh: str):
        resp = client.delete(f"/api/v1/meshes/{owner_mesh}", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        assert db.get_mesh_by_id(owner_mesh) is None
        gone = client.get(f"/api/v1/meshes/{owner_mesh}/info", headers=OWNER_HEADERS)
        assert gone.status_code == 404


def test_two_sessions_with_same_filename_are_isolated(
    client: TestClient, stl_bytes: bytes
):
    owner_id = _upload(client, stl_bytes, OWNER_SESSION, "pit.stl")
    outsider_id = _upload(client, stl_bytes, OUTSIDER_SESSION, "pit.stl")
    assert owner_id != outsider_id

    owner_own = client.get(f"/api/v1/meshes/{owner_id}/info", headers=OWNER_HEADERS)
    outsider_own = client.get(
        f"/api/v1/meshes/{outsider_id}/info", headers=OUTSIDER_HEADERS
    )
    assert owner_own.status_code == 200
    assert outsider_own.status_code == 200

    cross = client.get(f"/api/v1/meshes/{owner_id}/info", headers=OUTSIDER_HEADERS)
    assert cross.status_code == 404

    deletion = client.delete(f"/api/v1/meshes/{owner_id}", headers=OUTSIDER_HEADERS)
    assert deletion.status_code == 404
    still_there = client.get(f"/api/v1/meshes/{owner_id}/info", headers=OWNER_HEADERS)
    assert still_there.status_code == 200
