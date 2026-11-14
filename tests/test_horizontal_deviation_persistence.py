import hashlib
import json

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

import api.database as db
from api.main import app
from api.routers import meshes
from core import HorizontalFaceGeometry

BOUNDS = {
    "xmin": 0.0,
    "xmax": 60.0,
    "ymin": 0.0,
    "ymax": 140.0,
    "zmin": 80.0,
    "zmax": 110.0,
}


@pytest.fixture(autouse=True)
def clear_heatmap_caches():
    cached_functions = (
        meshes._get_decimated_vertices_cached,
        meshes._build_horizontal_deviation_cached,
    )
    for cached in cached_functions:
        cached.cache_clear()
    yield
    for cached in cached_functions:
        cached.cache_clear()


def _section(name, y, sector="A"):
    return {
        "name": name,
        "origin": [0.0, y],
        "azimuth": 90.0,
        "length": 60.0,
        "sector": sector,
    }


def _sections(sector="A", count=3):
    return [_section(f"{sector}-{index + 1:02d}", index * 2.0, sector) for index in range(count)]


def _surface():
    vertices = np.asarray(
        [(0.0, -1.0, 110.0), (60.0, -1.0, 50.0), (0.0, 141.0, 110.0), (60.0, 141.0, 50.0)],
        dtype=float,
    )
    faces = np.asarray([(0, 1, 3), (0, 3, 2)], dtype=np.int64)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _add_meshes(session_id):
    topo_id = db.save_mesh(session_id, "topo", "topo.stl", b"mesh", 3, 1, BOUNDS)
    design_id = db.save_mesh(session_id, "design", "design.stl", b"mesh", 3, 1, BOUNDS)
    return topo_id, design_id


@pytest.fixture
def heatmap_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "heatmap-persistence-test.db")
    db.init_db()
    profile = (
        np.asarray([0.0, 10.0, 20.0, 30.0, 40.0, 60.0]),
        np.asarray([110.0, 105.0, 100.0, 95.0, 90.0, 80.0]),
    )
    face = HorizontalFaceGeometry(1, 0.0, 110.0, 20.0, 90.0, 20.0)
    surface = _surface()
    monkeypatch.setattr(db, "get_trimesh_by_id", lambda mesh_id: surface)
    monkeypatch.setattr(meshes, "_crop_mesh_to_sections", lambda mesh, sections: mesh)
    monkeypatch.setattr(
        meshes,
        "_profile_data_with_diagnostics",
        lambda mesh, section: (profile, ()),
    )
    monkeypatch.setattr(meshes, "_extract_faces", lambda profile, section, options: {1: face})


@pytest.fixture
def heatmap_session(heatmap_db):
    session_id = db.create_session()
    topo_id, design_id = _add_meshes(session_id)
    db.save_sections(session_id, _sections())
    return session_id, topo_id, design_id


def _request(session_id, topo_id, design_id, **params):
    return TestClient(app).get(
        f"/api/v1/meshes/{topo_id}/horizontal-deviation",
        params={"design_mesh_id": design_id, **params},
        headers={"x-session-id": session_id},
    )


def _rows(session_id=None):
    conn = db.get_connection()
    try:
        if session_id is None:
            return conn.execute(
                "SELECT * FROM horizontal_deviation_results ORDER BY id"
            ).fetchall()
        return conn.execute(
            "SELECT * FROM horizontal_deviation_results WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()


def test_successful_request_persists_one_row_matching_the_response(heatmap_session):
    session_id, topo_id, design_id = heatmap_session

    response = _request(session_id, topo_id, design_id, sector="A")

    assert response.status_code == 200
    rows = _rows(session_id)
    assert len(rows) == 1
    assert rows[0]["sector"] == "A"
    assert isinstance(rows[0]["payload"], bytes)
    latest = db.get_latest_horizontal_deviation(session_id, "A")
    assert set(latest) == {"cache_key", "params", "payload", "created_at"}
    assert latest["payload"] == response.json()
    assert latest["payload"]["summary"]["measured"] > 0
    assert latest["cache_key"] == rows[0]["cache_key"]
    assert latest["created_at"]
    assert latest["params"] == {
        "topo_id": topo_id,
        "design_mesh_id": design_id,
        "sector": "A",
        "bench_num": None,
        "longitudinal_step": 2.0,
        "vertical_step": 1.0,
    }


def test_repeated_identical_request_keeps_a_single_row(heatmap_session):
    session_id, topo_id, design_id = heatmap_session

    first = _request(session_id, topo_id, design_id, sector="A")
    second = _request(session_id, topo_id, design_id, sector="A")

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert len(_rows(session_id)) == 1


def test_cache_key_is_sha256_of_the_cached_call_arguments(heatmap_session, monkeypatch):
    session_id, topo_id, design_id = heatmap_session
    captured = []
    cached = meshes._build_horizontal_deviation_cached

    def recording_cached(*args):
        captured.append(args)
        return cached(*args)

    monkeypatch.setattr(meshes, "_build_horizontal_deviation_cached", recording_cached)

    response = _request(session_id, topo_id, design_id, sector="A", bench_num=1)

    assert response.status_code == 200
    assert len(captured) == 1
    expected = hashlib.sha256(
        json.dumps(list(captured[0]), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert db.get_latest_horizontal_deviation(session_id, "A")["cache_key"] == expected
    assert meshes.horizontal_deviation_cache_key(session_id, "A", 1, 2.0, 1.0) == expected


def test_current_key_matches_stored_key_and_changes_with_sections(heatmap_session):
    session_id, topo_id, design_id = heatmap_session
    assert _request(session_id, topo_id, design_id, sector="A").status_code == 200
    stored_key = db.get_latest_horizontal_deviation(session_id, "A")["cache_key"]

    assert meshes.horizontal_deviation_cache_key(session_id, "A", None, 2.0, 1.0) == stored_key
    assert meshes.horizontal_deviation_cache_key(session_id, None, None, 2.0, 1.0) == stored_key
    assert meshes.horizontal_deviation_cache_key(session_id, "A", None, 4.0, 1.0) != stored_key
    assert meshes.horizontal_deviation_cache_key(session_id, "A", None, 2.0, 0.5) != stored_key
    assert meshes.horizontal_deviation_cache_key(session_id, "A", 1, 2.0, 1.0) != stored_key

    db.save_sections(session_id, _sections(count=4))

    changed_key = meshes.horizontal_deviation_cache_key(session_id, "A", None, 2.0, 1.0)
    assert changed_key is not None
    assert changed_key != stored_key


def test_current_key_changes_when_a_mesh_is_replaced(heatmap_session):
    session_id, topo_id, design_id = heatmap_session
    assert _request(session_id, topo_id, design_id, sector="A").status_code == 200
    stored_key = db.get_latest_horizontal_deviation(session_id, "A")["cache_key"]

    db.save_mesh(session_id, "topo", "topo-v2.stl", b"mesh", 3, 1, BOUNDS)

    replaced_key = meshes.horizontal_deviation_cache_key(session_id, "A", None, 2.0, 1.0)
    assert replaced_key is not None
    assert replaced_key != stored_key


def test_current_key_changes_with_detection_settings(heatmap_session):
    session_id, topo_id, design_id = heatmap_session
    before = meshes.horizontal_deviation_cache_key(session_id, "A", None, 2.0, 1.0)

    db.save_settings(session_id, {"process": {"face_threshold": 41.0}})

    after = meshes.horizontal_deviation_cache_key(session_id, "A", None, 2.0, 1.0)
    assert before is not None and after is not None
    assert after != before


def test_current_key_does_not_compute_anything(heatmap_session, monkeypatch):
    session_id, _, _ = heatmap_session

    def fail(*args, **kwargs):
        raise AssertionError("cache key lookup must not compute the heatmap")

    monkeypatch.setattr(meshes, "_build_horizontal_deviation_payload", fail)
    monkeypatch.setattr(meshes, "_build_horizontal_deviation_cached", fail)
    monkeypatch.setattr(db, "get_trimesh_by_id", fail)

    assert meshes.horizontal_deviation_cache_key(session_id, "A", None, 2.0, 1.0) is not None
    assert _rows(session_id) == []


def test_current_key_is_none_without_meshes_or_enough_sections(heatmap_db):
    no_meshes = db.create_session()
    db.save_sections(no_meshes, _sections())
    assert meshes.horizontal_deviation_cache_key(no_meshes, "A", None, 2.0, 1.0) is None

    only_topo = db.create_session()
    db.save_mesh(only_topo, "topo", "topo.stl", b"mesh", 3, 1, BOUNDS)
    db.save_sections(only_topo, _sections())
    assert meshes.horizontal_deviation_cache_key(only_topo, "A", None, 2.0, 1.0) is None

    one_section = db.create_session()
    _add_meshes(one_section)
    db.save_sections(one_section, _sections(count=1))
    assert meshes.horizontal_deviation_cache_key(one_section, "A", None, 2.0, 1.0) is None

    no_sections = db.create_session()
    _add_meshes(no_sections)
    assert meshes.horizontal_deviation_cache_key(no_sections, "A", None, 2.0, 1.0) is None

    two_sectors = db.create_session()
    _add_meshes(two_sectors)
    db.save_sections(two_sectors, _sections("A") + _sections("B"))
    assert meshes.horizontal_deviation_cache_key(two_sectors, None, None, 2.0, 1.0) is None
    assert meshes.horizontal_deviation_cache_key(two_sectors, "C", None, 2.0, 1.0) is None
    assert meshes.horizontal_deviation_cache_key(two_sectors, "B", None, 2.0, 1.0) is not None


def test_failing_request_stores_nothing(heatmap_db):
    session_id = db.create_session()
    topo_id, design_id = _add_meshes(session_id)
    db.save_sections(session_id, _sections(count=1))

    insufficient = _request(session_id, topo_id, design_id, sector="A")
    invalid_step = _request(session_id, topo_id, design_id, sector="A", vertical_step=99)

    assert insufficient.status_code == 422
    assert invalid_step.status_code == 422
    assert _rows() == []
    assert db.get_latest_horizontal_deviation(session_id, "A") is None


def test_calculation_error_stores_nothing(heatmap_session, monkeypatch):
    session_id, topo_id, design_id = heatmap_session

    def fail(*args):
        raise ValueError("no_measurable_faces")

    monkeypatch.setattr(meshes, "_build_horizontal_deviation_payload", fail)

    response = _request(session_id, topo_id, design_id, sector="A")

    assert response.status_code == 422
    assert _rows() == []


def test_retention_keeps_the_four_newest_results_per_session_and_sector(heatmap_session):
    session_id, topo_id, design_id = heatmap_session
    steps = [1.0, 2.0, 3.0, 4.0, 5.0]
    responses = [
        _request(session_id, topo_id, design_id, sector="A", longitudinal_step=step)
        for step in steps
    ]

    assert [response.status_code for response in responses] == [200] * 5
    rows = _rows(session_id)
    assert len(rows) == 4
    assert sorted(json.loads(row["params"])["longitudinal_step"] for row in rows) == steps[1:]
    latest = db.get_latest_horizontal_deviation(session_id, "A")
    assert latest["params"]["longitudinal_step"] == 5.0
    assert latest["payload"] == responses[-1].json()


def test_retention_is_scoped_per_sector_and_resaving_refreshes_recency(heatmap_db):
    session_id = db.create_session()
    for index in range(4):
        db.save_horizontal_deviation(session_id, "A", f"key-{index}", {"n": index}, {"n": index})
    db.save_horizontal_deviation(session_id, "B", "key-b", {"n": "b"}, {"n": "b"})

    db.save_horizontal_deviation(session_id, "A", "key-0", {"n": 0}, {"n": "refreshed"})
    db.save_horizontal_deviation(session_id, "A", "key-4", {"n": 4}, {"n": 4})

    keys_a = {row["cache_key"] for row in _rows(session_id) if row["sector"] == "A"}
    assert keys_a == {"key-0", "key-2", "key-3", "key-4"}
    assert db.get_latest_horizontal_deviation(session_id, "A")["cache_key"] == "key-4"
    assert db.get_latest_horizontal_deviation(session_id, "B")["payload"] == {"n": "b"}
    refreshed = [row for row in _rows(session_id) if row["cache_key"] == "key-0"]
    assert len(refreshed) == 1


def test_save_failure_leaves_response_unchanged(heatmap_session, monkeypatch):
    session_id, topo_id, design_id = heatmap_session
    baseline = _request(session_id, topo_id, design_id, sector="A")
    assert baseline.status_code == 200
    calls = []

    def failing_save(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "save_horizontal_deviation", failing_save)
    meshes._build_horizontal_deviation_cached.cache_clear()

    response = _request(session_id, topo_id, design_id, sector="A")

    assert calls
    assert response.status_code == 200
    assert response.json() == baseline.json()


def test_rows_are_removed_with_their_session_by_cleanup(heatmap_session):
    session_id, topo_id, design_id = heatmap_session
    assert _request(session_id, topo_id, design_id, sector="A").status_code == 200
    survivor = db.create_session()
    db.save_horizontal_deviation(survivor, "A", "key", {"n": 1}, {"n": 1})
    conn = db.get_connection()
    conn.execute(
        "UPDATE sessions SET created_at = '2000-01-01 00:00:00' WHERE id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()

    db.cleanup_old_sessions()

    assert not db.session_exists(session_id)
    assert _rows(session_id) == []
    assert len(_rows(survivor)) == 1


def test_other_session_cannot_read_stored_rows(heatmap_session):
    session_id, topo_id, design_id = heatmap_session
    assert _request(session_id, topo_id, design_id, sector="A").status_code == 200
    other_session = db.create_session()

    assert db.get_latest_horizontal_deviation(session_id, "A") is not None
    assert db.get_latest_horizontal_deviation(other_session, "A") is None
    assert db.get_latest_horizontal_deviation(session_id, "B") is None


def test_init_db_adds_table_to_existing_database_idempotently(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "heatmap-migration-test.db")
    db.init_db()
    conn = db.get_connection()
    conn.execute("DROP TABLE horizontal_deviation_results")
    conn.commit()
    conn.close()
    session_id = db.create_session()

    db.init_db()
    db.init_db()

    db.save_horizontal_deviation(session_id, "A", "key", {"n": 1}, {"n": 1})
    assert db.get_latest_horizontal_deviation(session_id, "A")["payload"] == {"n": 1}
