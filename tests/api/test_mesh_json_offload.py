import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

import api.database as db
import api.routers.meshes as meshes


@pytest.fixture
def session(client, stl_bytes):
    sid = "json-offload"
    headers = {"X-Session-ID": sid}
    ids = {}
    for kind in ("topo", "design"):
        response = client.post("/api/v1/meshes/upload", headers=headers,
                               files={"file": ("mesh.stl", stl_bytes)}, data={"type": kind})
        assert response.status_code == 200
        ids[kind] = response.json()["mesh_id"]
    db.save_sections(sid, [
        {"name": "A", "origin": [2, 2], "azimuth": 0, "length": 10, "sector": "S"},
        {"name": "B", "origin": [4, 2], "azimuth": 0, "length": 10, "sector": "S"},
    ])
    return sid, headers, ids


@pytest.mark.parametrize("kind", ["vertices", "roi", "contours", "breaklines", "horizontal"])
def test_body_matches_legacy(client, session, kind):
    sid, headers, ids = session
    topo, design = ids["topo"], ids["design"]
    root = f"/api/v1/meshes/{topo}"
    if kind == "vertices":
        path = root + "/vertices"
        payload = meshes._get_decimated_vertices_cached(topo, 8000)
    elif kind == "roi":
        path = root + "/vertices/roi?xmin=0&ymin=0&xmax=10&ymax=10"
        payload = meshes._get_roi_vertices_cached(sid, topo, 0.0, 0.0, 10.0, 10.0, 60000)
    elif kind == "contours":
        path = root + "/contours?interval=2"
        payload = meshes._get_contours_cached(topo, 2.0, 1500)
    elif kind == "breaklines":
        path = root + "/breaklines"
        payload = meshes._get_breaklines_cached(topo, 20.0)
    else:
        path = root + f"/horizontal-deviation?design_mesh_id={design}&sector=S"
        args = meshes._horizontal_deviation_cached_args(sid, topo, design, "S", None, 2.0, 1.0)
        payload = meshes._build_horizontal_deviation_cached(*args)
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.content == JSONResponse(jsonable_encoder(payload)).body


def test_encoding_does_not_block_health(client, session, monkeypatch):
    _, headers, ids = session
    started = threading.Event()
    original = getattr(meshes, "_encode_mesh_json", None)

    def slow(payload):
        started.set()
        time.sleep(0.5)
        return original(payload)

    monkeypatch.setattr(meshes, "_encode_mesh_json", slow, raising=False)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.get, f"/api/v1/meshes/{ids['topo']}/vertices", headers=headers)
        assert started.wait(2), "encoder was not invoked"
        start = time.monotonic()
        health = client.get("/api/v1/health", headers=headers)
        elapsed = time.monotonic() - start
        assert health.status_code == 200
        assert elapsed < 0.25
        assert future.result().status_code == 200


def test_warm_vertices_skips_encoder(client, session, monkeypatch):
    _, headers, ids = session
    original = getattr(meshes, "_encode_mesh_json", None)
    calls = []

    def count(payload):
        calls.append(1)
        return original(payload)

    monkeypatch.setattr(meshes, "_encode_mesh_json", count, raising=False)
    path = f"/api/v1/meshes/{ids['topo']}/vertices"
    first = client.get(path, headers=headers)
    second = client.get(path, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert len(calls) == 1


@pytest.mark.parametrize("endpoint", ["vertices", "contours", "breaklines"])
def test_unknown_mesh(client, session, endpoint):
    response = client.get(f"/api/v1/meshes/missing/{endpoint}", headers=session[1])
    assert response.status_code == 404


def test_invalid_roi(client, session):
    response = client.get(f"/api/v1/meshes/{session[2]['topo']}/vertices/roi?xmin=2&ymin=0&xmax=1&ymax=1", headers=session[1])
    assert response.status_code == 422
    assert response.json()["detail"] == "ROI minimum bounds must be below maximum bounds"


def test_horizontal_insufficient_sections(client, session):
    sid, headers, ids = session
    db.save_sections(sid, [{"name": "A", "origin": [2, 2], "azimuth": 0, "length": 10, "sector": "S"}])
    response = client.get(f"/api/v1/meshes/{ids['topo']}/horizontal-deviation?design_mesh_id={ids['design']}&sector=S", headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"] == "insufficient_sections: sector 'S' needs at least two configured sections for the 3D comparison"
