import json

import numpy as np
import pytest
import trimesh

import api.database as db
from api.routers import meshes
from core import HorizontalFaceGeometry
from core.config import HORIZONTAL_DEVIATION


@pytest.fixture(autouse=True)
def clear_decimated_cache():
    meshes._get_decimated_vertices_cached.cache_clear()
    yield
    meshes._get_decimated_vertices_cached.cache_clear()


def make_case(monkeypatch):
    xs = np.linspace(-20, 30, 51)
    ys = [-1, 0, 1, 2, 3]
    def surface(offset, mound):
        vertices = [(x, y, 100 - x + offset + (mound if y == 1 else 0)) for y in ys for x in xs]
        faces = []
        for j in range(len(ys) - 1):
            for i in range(len(xs) - 1):
                a = j * len(xs) + i
                faces.extend([(a, a + 1, a + len(xs) + 1), (a, a + len(xs) + 1, a + len(xs))])
        return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    design, topo = surface(0, 0), surface(-2, 0.5)
    monkeypatch.setattr(db, 'get_trimesh_by_id', lambda mesh_id: {'topo': topo, 'design': design}[mesh_id])
    face = HorizontalFaceGeometry(1, 0, 100, 10, 90, 10)
    monkeypatch.setattr(meshes, '_extract_faces', lambda profile, section, options: {1: face})
    sections = [{'name': f'A-{y}', 'origin': [0, y], 'azimuth': 90, 'length': 60, 'sector': 'A'} for y in (0, 2)]
    return meshes._build_horizontal_deviation_payload('topo', 'design', sections, 'A', 1, 2, 4, {})


def test_draped_vertices_follow_topo_and_retain_cell_contract(monkeypatch):
    payload = make_case(monkeypatch)
    vertices = payload['vertices']
    assert payload['summary'] == {
        'measured': 3, 'total': 3, 'within_percent': 0.0, 'max_abs_deviation': 1.5,
    }
    assert [(cell['deviation_m'], cell['category']) for cell in payload['cells']] == [
        (1.5, 'overbreak_minor'), (1.5, 'overbreak_minor'), (1.5, 'overbreak_minor'),
    ]
    assert len(vertices['x']) > 18
    for x, y, z in zip(vertices['x'], vertices['y'], vertices['z']):
        expected = 98 - x + 0.5 * (1 - abs(y - 1)) + HORIZONTAL_DEVIATION.drape_lift_m
        assert z == pytest.approx(expected, abs=1e-6)
    assert len(payload['faces']) == len(payload['cell_index_by_face'])
    for face, cell_index in zip(payload['faces'], payload['cell_index_by_face']):
        assert len(face) == 3 and all(0 <= i < len(vertices['x']) for i in face)
        assert payload['cells'][cell_index]['deviation_m'] is not None
    assert len(vertices['x']) <= payload['summary']['measured'] * (HORIZONTAL_DEVIATION.drape_max_subdivisions + 1) ** 2
    assert len(json.dumps(payload)) < 100000


def test_drape_uses_viewer_decimation_without_changing_measurements(monkeypatch):
    from core import mesh_handler

    original_decimate = mesh_handler.decimate_mesh
    monkeypatch.setattr(mesh_handler, 'decimate_mesh', lambda mesh, step: original_decimate(mesh, 20))
    meshes._get_decimated_vertices_cached.cache_clear()
    payload = make_case(monkeypatch)
    viewer = meshes._get_decimated_vertices_cached('topo', 150000)
    decimated = trimesh.Trimesh(
        vertices=np.column_stack((viewer['x'], viewer['y'], viewer['z'])),
        faces=viewer['faces'], process=False,
    )
    points = np.column_stack(tuple(payload['vertices'][axis] for axis in ('x', 'y', 'z')))
    index = meshes._horizontal_drape_index(decimated)
    differences = []
    for point in points:
        projected, _, outside = meshes._drape_horizontal_cell(decimated, [point] * 4, index)
        assert outside == 0
        differences.append(abs(point[2] - projected[0][2]))
    assert max(differences) < 1e-6
    assert payload['summary'] == {'measured': 3, 'total': 3, 'within_percent': 0.0, 'max_abs_deviation': 1.5}
    assert [(cell['deviation_m'], cell['category']) for cell in payload['cells']] == [(1.5, 'overbreak_minor')] * 3
    meshes._get_decimated_vertices_cached.cache_clear()


def test_drape_cache_version_is_incremented():
    assert HORIZONTAL_DEVIATION.drape_version >= 2


def test_drape_outside_uses_interpolated_bench_elevation_and_counts():
    topo = trimesh.Trimesh(vertices=[[0, 0, 4], [1, 0, 4], [0, 1, 4]], faces=[[0, 1, 2]], process=False)
    corners = [(0, 0, 10), (2, 0, 10), (2, 2, 20), (0, 2, 20)]
    vertices, faces, outside = meshes._drape_horizontal_cell(topo, corners)
    assert outside > 0
    for x, y, z in vertices:
        if x + y > 1 + 1e-8:
            assert z == pytest.approx(10 + 5 * y)
        else:
            assert z == pytest.approx(4 + HORIZONTAL_DEVIATION.drape_lift_m)
    assert faces


def test_large_cell_has_capped_subdivisions():
    topo = trimesh.Trimesh(vertices=[[0, 0, 1], [100, 0, 1], [0, 100, 1]], faces=[[0, 1, 2]], process=False)
    corners = [(0, 0, 0), (100, 0, 0), (100, 100, 0), (0, 100, 0)]
    vertices, faces, _ = meshes._drape_horizontal_cell(topo, corners)
    cap = HORIZONTAL_DEVIATION.drape_max_subdivisions
    assert len(vertices) == (cap + 1) ** 2
    assert len(faces) == 2 * cap ** 2


def test_drape_cache_key_has_geometry_version(monkeypatch):
    calls = []
    monkeypatch.setattr(meshes, '_build_horizontal_deviation_payload', lambda *args: calls.append(args) or {'call': len(calls)})
    cached = meshes._build_horizontal_deviation_cached
    cached.cache_clear()
    config = {'detection': {}, 'horizontal_deviation': vars(HORIZONTAL_DEVIATION).copy()}
    args = ('topo', 'design', '[]', 'A', 1, 2, 4)
    first = cached(*args, json.dumps(config, sort_keys=True))
    assert cached(*args, json.dumps(config, sort_keys=True)) == first
    config['horizontal_deviation']['drape_version'] += 1
    assert cached(*args, json.dumps(config, sort_keys=True)) != first
    assert len(calls) == 2
    cached.cache_clear()


def test_payload_reports_outside_count(monkeypatch):
    original = meshes._drape_horizontal_cell
    outside_total = []
    empty = trimesh.Trimesh(vertices=[[1000, 1000, 0], [1001, 1000, 0], [1000, 1001, 0]], faces=[[0, 1, 2]], process=False)
    def drape(_mesh, corners, _index):
        result = original(empty, corners)
        outside_total.append(result[2])
        return result
    monkeypatch.setattr(meshes, '_drape_horizontal_cell', drape)
    payload = make_case(monkeypatch)
    assert sum(outside_total) > 0
    assert f'drape_outside_topo_count:{sum(outside_total)}' in payload['warnings']
