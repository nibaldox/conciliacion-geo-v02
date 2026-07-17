"""Unit tests for mesh breakline extraction."""

import numpy as np
import trimesh

from core.breaklines import extract_breaklines


def _two_face_mesh(*, convex: bool) -> trimesh.Trimesh:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    faces = np.array([[0, 2, 1], [0, 1, 3]]) if convex else np.array([[0, 1, 2], [0, 3, 1]])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def test_extract_breaklines_classifies_convex_edge_as_crest():
    result = extract_breaklines(_two_face_mesh(convex=True), angle_threshold_deg=20.0)

    assert result["toes"] == []
    assert len(result["crests"]) == 1
    assert result["crests"][0] == [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]


def test_extract_breaklines_classifies_concave_edge_as_toe():
    result = extract_breaklines(_two_face_mesh(convex=False), angle_threshold_deg=20.0)

    assert result["crests"] == []
    assert len(result["toes"]) == 1
    assert result["toes"][0] == [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]


def test_extract_breaklines_filters_edges_below_threshold():
    result = extract_breaklines(_two_face_mesh(convex=True), angle_threshold_deg=100.0)
    assert result == {"crests": [], "toes": []}


def test_extract_breaklines_handles_single_face_without_adjacency():
    mesh = trimesh.Trimesh(
        vertices=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        faces=np.array([[0, 1, 2]]),
        process=False,
    )
    assert extract_breaklines(mesh) == {"crests": [], "toes": []}


def test_extract_breaklines_returns_float_coordinate_lists():
    result = extract_breaklines(_two_face_mesh(convex=True))
    coordinate = result["crests"][0][0]
    assert all(isinstance(value, float) for value in coordinate)
