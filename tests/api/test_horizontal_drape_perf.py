import math
import numpy as np
import pytest
import trimesh

from api.routers import meshes
from api.routers.meshes import HORIZONTAL_DEVIATION, _horizontal_drape_index


def _oracle_drape_horizontal_cell(topo_mesh, corners, spatial_index=None):
    points = np.asarray(corners, dtype=float)
    step = HORIZONTAL_DEVIATION.drape_max_step_m
    cap = HORIZONTAL_DEVIATION.drape_max_subdivisions
    nx = min(cap, max(1, math.ceil(max(
        np.linalg.norm(points[1, :2] - points[0, :2]),
        np.linalg.norm(points[2, :2] - points[3, :2]),
    ) / step)))
    ny = min(cap, max(1, math.ceil(max(
        np.linalg.norm(points[3, :2] - points[0, :2]),
        np.linalg.norm(points[2, :2] - points[1, :2]),
    ) / step)))
    grid = []
    for j in range(ny + 1):
        v = j / ny
        for i in range(nx + 1):
            u = i / nx
            grid.append((1 - v) * ((1 - u) * points[0] + u * points[1])
                        + v * ((1 - u) * points[3] + u * points[2]))
    grid = np.asarray(grid)
    trees = spatial_index if spatial_index is not None else _horizontal_drape_index(topo_mesh)
    heights = np.full(len(grid), np.nan)
    candidates_by_point = [[] for _ in grid]
    for tree, indices, radius in trees:
        for candidates, local in zip(candidates_by_point, tree.query_ball_point(grid[:, :2], radius + 1e-8)):
            candidates.extend(indices[local])
    for index, candidates in enumerate(candidates_by_point):
        if not candidates:
            continue
        triangles = topo_mesh.vertices[topo_mesh.faces[candidates]]
        a = triangles[:, 0, :2]
        ab = triangles[:, 1, :2] - a
        ac = triangles[:, 2, :2] - a
        ap = grid[index, :2] - a
        denominator = ab[:, 0] * ac[:, 1] - ab[:, 1] * ac[:, 0]
        nondegenerate = np.abs(denominator) > 1e-12
        safe = np.where(nondegenerate, denominator, 1.0)
        u = (ap[:, 0] * ac[:, 1] - ap[:, 1] * ac[:, 0]) / safe
        v = (ab[:, 0] * ap[:, 1] - ab[:, 1] * ap[:, 0]) / safe
        inside = nondegenerate & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        if np.any(inside):
            z = triangles[:, 0, 2] + u * (triangles[:, 1, 2] - triangles[:, 0, 2]) + v * (triangles[:, 2, 2] - triangles[:, 0, 2])
            heights[index] = np.max(z[inside])
    covered = np.isfinite(heights)
    grid[covered, 2] = heights[covered] + HORIZONTAL_DEVIATION.drape_lift_m
    faces = []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            b = a + 1
            d = a + nx + 1
            c = d + 1
            faces.extend(((a, b, c), (a, c, d)))
    return grid.tolist(), faces, int(np.count_nonzero(~covered))


@pytest.mark.parametrize("case", ["inside", "outside", "degenerate", "overlap", "capped"])
def test_drape_exactly_matches_original(case):
    vertices = [[0, 0, 2], [10, 0, 4], [0, 10, 6], [10, 10, 8]]
    faces = [[0, 1, 2], [1, 3, 2]]
    if case == "degenerate":
        vertices += [[0, 0, 100], [1, 1, 100], [2, 2, 100]]
        faces += [[4, 5, 6]]
    if case == "overlap":
        vertices += [[0, 0, 20], [10, 0, 20], [0, 10, 20], [10, 10, 20]]
        faces += [[4, 5, 6], [5, 7, 6]]
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    size = 50 if case == "capped" else 4
    start = 8 if case == "outside" else 1
    corners = [[start, start, 0], [start + size, start, 0],
               [start + size, start + size, 0], [start, start + size, 0]]
    index = _horizontal_drape_index(mesh)
    actual = meshes._drape_horizontal_cell(mesh, corners, index)
    assert actual == _oracle_drape_horizontal_cell(mesh, corners, index)
    if case == "outside":
        assert actual[2] > 0
    if case == "overlap":
        assert all(point[2] == 20 + HORIZONTAL_DEVIATION.drape_lift_m for point in actual[0])
    if case == "capped":
        assert len(actual[0]) == (HORIZONTAL_DEVIATION.drape_max_subdivisions + 1) ** 2


