import dataclasses
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import trimesh


def test_defaults_are_frozen():
    from core.config import SECTION_INDEX
    assert (SECTION_INDEX.cell_size_m, SECTION_INDEX.min_faces, SECTION_INDEX.pad_m) == (5.0, 50000, 1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        SECTION_INDEX.pad_m = 2


@pytest.mark.parametrize('angle', [0, 45, 90, 137, 270])
def test_candidates_are_sorted_superset(angle):
    from core.section_index import build_face_grid_index, candidate_faces
    rng = np.random.default_rng(123)
    vertices = rng.uniform(-100, 100, (900, 3))
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.arange(900).reshape(-1, 3), process=False)
    index = build_face_grid_index(mesh, 5)
    direction = np.array([np.sin(np.radians(angle)), np.cos(np.radians(angle))])
    for center in rng.uniform(-120, 120, (12, 2)):
        a, b = center - 23 * direction, center + 57 * direction
        result = candidate_faces(index, a, b, 1.0)
        triangles = mesh.vertices[mesh.faces][:, :, :2]
        lo, hi = np.minimum(a, b) - 1, np.maximum(a, b) + 1
        mask = np.all(triangles.max(axis=1) >= lo, axis=1) & np.all(triangles.min(axis=1) <= hi, axis=1)
        assert set(np.flatnonzero(mask)).issubset(set(result))
        assert result.dtype == np.int64
        assert np.array_equal(result, np.unique(result))


def test_small_and_outside_queries():
    from core.section_index import build_face_grid_index, candidate_faces
    mesh = trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]], faces=[[0, 1, 2], [0, 1, 2]], process=False)
    index = build_face_grid_index(mesh)
    assert np.array_equal(candidate_faces(index, np.zeros(2), np.ones(2), 0), [0, 1])
    outside = candidate_faces(index, np.array([100., 100.]), np.array([101., 101.]), 0)
    assert outside.dtype == np.int64 and outside.size == 0
    single = trimesh.Trimesh(vertices=mesh.vertices.copy(), faces=[[0, 1, 2]], process=False)
    assert np.array_equal(candidate_faces(build_face_grid_index(single), np.zeros(2), np.ones(2), 0), [0])


def test_cache_invalidation_and_distinct_mesh():
    from core.section_index import get_face_grid_index
    mesh = trimesh.creation.box()
    first = get_face_grid_index(mesh)
    assert get_face_grid_index(mesh) is first
    assert get_face_grid_index(mesh.copy()) is not first
    mesh.vertices[0, 0] += 1
    assert get_face_grid_index(mesh) is not first


def test_concurrent_index_build_once(monkeypatch):
    import core.section_index as si
    import time
    mesh = trimesh.creation.box()
    original = si.build_face_grid_index
    calls = []
    def build(mesh):
        calls.append(1)
        time.sleep(0.05)
        return original(mesh)
    monkeypatch.setattr(si, 'build_face_grid_index', build)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(si.get_face_grid_index, [mesh] * 8))
    assert len(calls) == 1
    assert all(item is results[0] for item in results)


def test_indexed_cuts_never_rehash_big_mesh_arrays(monkeypatch):
    import core.section_cutter as cutter
    from core.config import SECTION_INDEX
    from core.section_cutter import SectionLine, cut_mesh_with_section_diagnostics
    mesh = trimesh.creation.icosphere(subdivisions=6, radius=500.0)
    assert len(mesh.faces) > SECTION_INDEX.min_faces
    cut_mesh_with_section_diagnostics(mesh, SectionLine('warm', np.array([0.0, 0.0]), 0.0, 200.0))
    big_bytes = min(np.asarray(mesh.faces).nbytes, np.asarray(mesh.vertices).nbytes)

    hashed = []
    original_hash = trimesh.caching.hash_fast

    def counting_hash(item):
        hashed.append(memoryview(item).nbytes)
        return original_hash(item)

    candidates = []
    original_candidates = cutter.candidate_faces

    def counting_candidates(*args, **kwargs):
        result = original_candidates(*args, **kwargs)
        candidates.append(len(result))
        return result

    monkeypatch.setattr(trimesh.caching, 'hash_fast', counting_hash)
    monkeypatch.setattr(cutter, 'candidate_faces', counting_candidates)
    for i in range(10):
        origin = np.array([-300.0 + 60.0 * i, 40.0 * (i % 3 - 1)])
        cut_mesh_with_section_diagnostics(mesh, SectionLine(f'S{i}', origin, 15.0 * i, 200.0))

    assert len(candidates) == 10 and all(0 < n < len(mesh.faces) for n in candidates)
    assert hashed, 'no hashing observed; the guard would be vacuous'
    assert [n for n in hashed if n >= big_bytes] == []
