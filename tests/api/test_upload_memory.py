"""Memory-contract tests for POST /api/v1/meshes/upload.

The upload path must stream the request body to a temporary file in
bounded chunks (never materializing it with an unbounded ``file.read()``),
parse off the event loop, stream the blob into SQLite from the temp file,
keep the response contract identical, reject oversized uploads with a
413 before doing heavy work, and leave no temporary files behind on
parse errors.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

import api.database as db
import api.routers.meshes as meshes_router

UPLOAD_PATH = "/api/v1/meshes/upload"
UPLOAD_HEADERS = {"X-Session-ID": "api-upload-memory-tests"}

RESPONSE_CONTRACT_KEYS = {"mesh_id", "n_vertices", "n_faces", "bounds"}
BOUNDS_CONTRACT_KEYS = {"xmin", "xmax", "ymin", "ymax", "zmin", "zmax"}

NO_MEMORY_MESSAGE = (
    "The instance cannot hold a file this size in memory: "
    "upload a lighter surface or use a larger instance."
)


@pytest.fixture()
def temp_watch(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect the endpoint's tempfile.mkstemp calls to a watched dir."""
    watch_dir = Path(tempfile.mkdtemp(prefix="upload_memory_watch_"))
    original_mkstemp = tempfile.mkstemp

    def fake_mkstemp(*args, **kwargs):
        kwargs.setdefault("dir", str(watch_dir))
        return original_mkstemp(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", fake_mkstemp)
    yield watch_dir
    shutil.rmtree(watch_dir, ignore_errors=True)


@pytest.fixture()
def read_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[list]:
    """Record the ``size`` argument of every UploadFile.read call."""
    calls: list = []
    original_read = UploadFile.read

    async def spy_read(self, size=None):
        calls.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", spy_read)
    yield calls


@pytest.fixture()
def save_mesh_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[list]:
    """Record the kwargs of every db.save_mesh call."""
    calls: list = []
    original = db.save_mesh

    def spy(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "save_mesh", spy)
    yield calls


@pytest.fixture()
def to_thread_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[list]:
    """Record the functions dispatched through asyncio.to_thread."""
    calls: list = []
    original = asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        calls.append(fn)
        return await original(fn, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", spy)
    yield calls


class TestUploadStreamsInChunks:
    def test_reads_are_bounded_and_never_unsized(
        self,
        client: TestClient,
        stl_bytes: bytes,
        read_spy: list,
        save_mesh_spy: list,
        to_thread_spy: list,
        temp_watch: Path,
    ):
        resp = client.post(
            UPLOAD_PATH,
            headers=UPLOAD_HEADERS,
            files={"file": ("topo.stl", stl_bytes, "application/octet-stream")},
            data={"type": "topo"},
        )
        assert resp.status_code == 200, resp.text
        assert len(read_spy) >= 1
        for size in read_spy:
            assert isinstance(size, int), "file.read() was called without a size bound"
            assert 0 < size <= meshes_router._UPLOAD_CHUNK_BYTES
        assert to_thread_spy == [meshes_router.load_mesh]
        assert len(save_mesh_spy) == 1
        kwargs = save_mesh_spy[0]["kwargs"]
        assert kwargs.get("data") is None
        assert Path(kwargs["data_path"]).parent == temp_watch
        leftovers = list(temp_watch.iterdir())
        assert leftovers == [], f"temp files left behind: {leftovers}"

    def test_response_keeps_legacy_contract(
        self, client: TestClient, stl_bytes: bytes, read_spy: list
    ):
        resp = client.post(
            UPLOAD_PATH,
            headers=UPLOAD_HEADERS,
            files={"file": ("design.stl", stl_bytes, "application/octet-stream")},
            data={"type": "design"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == RESPONSE_CONTRACT_KEYS
        assert isinstance(body["mesh_id"], str) and body["mesh_id"]
        assert body["n_vertices"] == 4
        assert body["n_faces"] == 4
        assert set(body["bounds"].keys()) == BOUNDS_CONTRACT_KEYS
        bounds = body["bounds"]
        assert bounds["xmin"] <= bounds["xmax"]
        assert bounds["ymin"] <= bounds["ymax"]
        assert bounds["zmin"] <= bounds["zmax"]


class TestUploadSizeLimit:
    def test_oversized_stream_rejected_413_without_temp(
        self,
        client: TestClient,
        stl_bytes: bytes,
        read_spy: list,
        temp_watch: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        header = stl_bytes[:80]
        tri = stl_bytes[80:130]
        assert len(tri) == 50
        big_stl = header + tri * 30000
        assert len(big_stl) > 1024 * 1024

        monkeypatch.setattr(
            meshes_router, "DEFAULTS", SimpleNamespace(max_upload_mb=1)
        )
        resp = client.post(
            UPLOAD_PATH,
            headers=UPLOAD_HEADERS,
            files={"file": ("big.stl", big_stl, "application/octet-stream")},
            data={"type": "topo"},
        )
        assert resp.status_code == 413, resp.text
        assert NO_MEMORY_MESSAGE in resp.json()["detail"]
        assert list(temp_watch.iterdir()) == []


class TestUploadParseFailure:
    def test_unparsable_file_400_and_no_temp_left(
        self, client: TestClient, temp_watch: Path, save_mesh_spy: list
    ):
        resp = client.post(
            UPLOAD_PATH,
            headers=UPLOAD_HEADERS,
            files={"file": ("broken.stl", b"this is not a mesh", "application/octet-stream")},
            data={"type": "topo"},
        )
        assert resp.status_code == 400, resp.text
        assert "Error loading mesh" in resp.json()["detail"]
        assert save_mesh_spy == []
        assert list(temp_watch.iterdir()) == []

    def test_empty_file_400(self, client: TestClient, temp_watch: Path):
        resp = client.post(
            UPLOAD_PATH,
            headers=UPLOAD_HEADERS,
            files={"file": ("empty.stl", b"", "application/octet-stream")},
            data={"type": "topo"},
        )
        assert resp.status_code == 400, resp.text
        assert list(temp_watch.iterdir()) == []


class TestSaveMeshStreamingBlob:
    def test_streamed_blob_is_byte_identical(
        self, isolated_data_dir: Path, stl_bytes: bytes
    ):
        source = isolated_data_dir / "source.stl"
        source.write_bytes(stl_bytes)
        sid = db.get_or_create_session("stream-blob-session")
        bounds = {"xmin": 0.0, "xmax": 10.0, "ymin": 0.0, "ymax": 10.0, "zmin": 0.0, "zmax": 10.0}
        mesh_id = db.save_mesh(
            sid, "topo", "source.stl", n_vertices=4, n_faces=4, bounds=bounds,
            data_path=str(source),
        )
        row = db.get_mesh_by_id(mesh_id)
        assert row is not None
        assert bytes(row["data"]) == stl_bytes

    def test_legacy_bytes_still_accepted(self, isolated_data_dir: Path):
        sid = db.get_or_create_session("legacy-blob-session")
        bounds = {"xmin": 0.0, "xmax": 10.0, "ymin": 0.0, "ymax": 10.0, "zmin": 0.0, "zmax": 10.0}
        mesh_id = db.save_mesh(sid, "design", "x.stl", b"raw-bytes", 3, 1, bounds)
        assert db.get_mesh_by_id(mesh_id)["data"] == b"raw-bytes"

    def test_requires_exactly_one_source(self, isolated_data_dir: Path):
        sid = db.get_or_create_session("guard-session")
        bounds = {"xmin": 0.0, "xmax": 1.0, "ymin": 0.0, "ymax": 1.0, "zmin": 0.0, "zmax": 1.0}
        with pytest.raises(ValueError):
            db.save_mesh(sid, "design", "x.stl", n_vertices=1, n_faces=1, bounds=bounds)
        with pytest.raises(ValueError):
            db.save_mesh(sid, "design", "x.stl", b"abc", 1, 1, bounds, data_path="/tmp/unused")
