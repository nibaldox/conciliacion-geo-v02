"""Shared fixtures for API router tests.

Each test runs against a fresh SQLite database under a temporary directory so
production data (data/conciliacion.db) is never touched and tests are fully
isolated. The same TestClient wraps the real FastAPI app from ``api.main``,
which exercises the real routers, dependencies, and session middleware.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.routers.meshes as meshes_router
from api.main import app
from core import load_mesh


# ---------------------------------------------------------------------------
# Isolated data directory for the duration of a test
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_data_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect the DB to a fresh temp directory; restore afterwards.

    ``api.database`` reads ``CONCILIACION_DATA_DIR`` at import time to decide
    where to create ``conciliacion.db``. We point it at a per-test temp dir
    so neither the real ``data/`` directory nor other tests' state leak in.
    """
    tmp = Path(tempfile.mkdtemp(prefix="conciliacion_api_test_"))
    monkeypatch.setenv("CONCILIACION_DATA_DIR", str(tmp))
    # Re-bind the module-level constants so any code that imported them
    # before the env override still picks up the new path.
    monkeypatch.setattr(db, "_DATA_DIR", tmp, raising=False)
    monkeypatch.setattr(db, "DB_PATH", tmp / "conciliacion.db", raising=False)
    # Ensure schema exists before any handler runs.
    db.init_db()
    try:
        yield tmp
    finally:
        # Best-effort cleanup. WAL/SHM sidecars may exist alongside the DB.
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestClient bound to the real app
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(isolated_data_dir: Path) -> Iterator[TestClient]:
    """FastAPI TestClient wired to the real app + isolated DB.

    The session middleware inside ``api.main`` reads/sets ``X-Session-ID``
    automatically. Tests can pass ``headers={"X-Session-ID": "abc"}`` to
    pin a deterministic session id.
    """
    # ``with TestClient(app) as c:`` triggers FastAPI lifespan, which calls
    # init_db() and cleanup_old_sessions() — same behaviour as production.
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def stl_bytes() -> bytes:
    """In-memory STL bytes for a simple cube-like triangular mesh.

    Built via ``trimesh`` (already a project dep) instead of depending on
    files committed to the repo. The geometry is intentionally minimal —
    just enough vertices/faces for the routers to compute valid bounds,
    decimation, contours, and breaklines.
    """
    import io
    import numpy as np
    import trimesh

    # 4 triangles forming a tetrahedron-like prism — well below the
    # 8000-vertex step default in /meshes/{id}/vertices, so no decimation
    # actually drops faces.
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [5.0, 10.0, 0.0],
            [5.0, 5.0, 10.0],
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [0, 3, 1],
            [1, 3, 2],
        ],
        dtype=int,
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    return buf.getvalue()


@pytest.fixture()
def larger_stl_bytes() -> bytes:
    """A mesh with >8000 faces so decimation kicks in for /vertices tests."""
    import io
    import numpy as np
    import trimesh

    nx = ny = 100  # 100×100 grid → ~20k triangles
    x = np.linspace(0, 200, nx)
    y = np.linspace(0, 200, ny)
    X, Y = np.meshgrid(x, y)
    # Gentle slope so contours/breaklines can find sections.
    Z = 5.0 + 0.05 * X + 0.02 * Y + 1.0 * np.sin(X / 30.0)

    vertices = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    faces = []
    for i in range(ny - 1):
        for j in range(nx - 1):
            v0 = i * nx + j
            faces.append([v0, v0 + 1, v0 + nx])
            faces.append([v0 + 1, v0 + nx + 1, v0 + nx])
    faces = np.array(faces, dtype=int)

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    return buf.getvalue()


@pytest.fixture()
def uploaded_mesh_id(client: TestClient, stl_bytes: bytes) -> str:
    """Upload a tiny mesh once and return its id, for tests that only need a mesh id."""
    resp = client.post(
        "/api/v1/meshes/upload",
        files={"file": ("tiny.stl", stl_bytes, "application/octet-stream")},
        data={"type": "design"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["mesh_id"]


@pytest.fixture(autouse=True)
def _clear_lru_caches() -> Iterator[None]:
    """Reset the lru_cache-decorated helpers between tests so cached
    meshes/sections from previous tests do not bleed into new ones."""
    meshes_router._get_decimated_vertices_cached.cache_clear()
    meshes_router._get_contours_cached.cache_clear()
    meshes_router._get_breaklines_cached.cache_clear()
    # The DB layer also caches the trimesh by id.
    db.get_trimesh_by_id.cache_clear()
    yield
    meshes_router._get_decimated_vertices_cached.cache_clear()
    meshes_router._get_contours_cached.cache_clear()
    meshes_router._get_breaklines_cached.cache_clear()
    db.get_trimesh_by_id.cache_clear()
