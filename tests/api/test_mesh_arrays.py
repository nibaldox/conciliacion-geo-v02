import numpy as np
import pytest
import trimesh

import api.database as db


def test_arrays_roundtrip(isolated_data_dir):
    db.get_or_create_session('arrays')
    mesh = trimesh.creation.box()
    mesh_id = db.save_mesh('arrays', 'design', 'box.stl', data=mesh.export(file_type='stl'))
    db.save_mesh_arrays(mesh_id, mesh)
    result = db.load_mesh_arrays(mesh_id)
    assert np.array_equal(result.vertices, mesh.vertices)
    assert np.array_equal(result.faces, mesh.faces)
    assert result.vertices.dtype == np.float64
    assert result.faces.dtype == np.int64
    assert np.array_equal(result.face_normals, mesh.face_normals)


def test_read_path_parses_without_writing_arrays(isolated_data_dir, monkeypatch, stl_bytes):
    db.get_or_create_session("legacy")
    mesh_id = db.save_mesh("legacy", "design", "old.stl", data=stl_bytes)
    real_load_mesh = db.load_mesh
    parsed = []

    def counting_load_mesh(path):
        parsed.append(path)
        return real_load_mesh(path)

    monkeypatch.setattr(db, "load_mesh", counting_load_mesh)
    assert db.get_trimesh_by_id(mesh_id) is not None
    db.get_trimesh_by_id.cache_clear()
    assert db.get_trimesh_by_id(mesh_id) is not None
    assert len(parsed) == 2
    conn = db.get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM mesh_arrays WHERE mesh_id = ?", (mesh_id,)).fetchone()[0]
    finally:
        conn.close()
    assert count == 0
    assert db.load_mesh_arrays(mesh_id) is None


def test_arrays_cascade(isolated_data_dir):
    db.get_or_create_session("cascade")
    mesh = trimesh.creation.box()
    mesh_id = db.save_mesh("cascade", "design", "box.stl", data=b"old")
    db.save_mesh_arrays(mesh_id, mesh)
    db.save_mesh("cascade", "design", "new.stl", data=b"new")
    assert db.load_mesh_arrays(mesh_id) is None


def test_eager_index_for_cached_arrays(isolated_data_dir, monkeypatch):
    import dataclasses
    import core.config as config
    db.get_or_create_session("eager")
    mesh = trimesh.creation.box()
    mesh_id = db.save_mesh("eager", "design", "box.stl", data=b"ignored")
    db.save_mesh_arrays(mesh_id, mesh)
    monkeypatch.setattr(config, "SECTION_INDEX", dataclasses.replace(config.SECTION_INDEX, min_faces=1))
    result = db.get_trimesh_by_id(mesh_id)
    assert "conciliacion_face_grid" in result._cache.cache


def test_upload_persists_arrays(client, stl_bytes):
    response = client.post("/api/v1/meshes/upload", files={"file": ("box.stl", stl_bytes)}, data={"type": "design"})
    assert response.status_code == 200
    assert db.load_mesh_arrays(response.json()["mesh_id"]) is not None


def test_trimesh_cache_has_own_byte_budget():
    from api.byte_cache import ByteLruCache
    assert isinstance(db.get_trimesh_by_id.cache, ByteLruCache)
    assert db.get_trimesh_by_id.cache_info().limit_bytes > 0


@pytest.mark.parametrize("sql", ["UPDATE mesh_arrays SET format=99", "UPDATE mesh_arrays SET faces=x'00'"])
def test_corrupt_arrays_reparse(isolated_data_dir, stl_bytes, sql):
    db.get_or_create_session("bad")
    mesh_id = db.save_mesh("bad", "design", "old.stl", data=stl_bytes)
    db.save_mesh_arrays(mesh_id, db.get_trimesh_by_id(mesh_id))
    db.get_trimesh_by_id.cache_clear()
    conn = db.get_connection()
    assert conn.execute(sql).rowcount == 1
    conn.commit()
    conn.close()
    assert db.load_mesh_arrays(mesh_id) is None
    assert db.get_trimesh_by_id(mesh_id) is not None
    assert db.load_mesh_arrays(mesh_id) is None


def test_stored_arrays_skip_original_parser(isolated_data_dir, monkeypatch):
    db.get_or_create_session("stored")
    mesh = trimesh.creation.box()
    mesh_id = db.save_mesh("stored", "design", "box.stl", data=b"bad")
    db.save_mesh_arrays(mesh_id, mesh)
    monkeypatch.setattr(db, "load_mesh", lambda *args: pytest.fail("parsed source"))
    assert np.array_equal(db.get_trimesh_by_id(mesh_id).faces, mesh.faces)
