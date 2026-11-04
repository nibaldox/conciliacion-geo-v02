"""Tests for conservative XY sampling of the original design mesh."""

import numpy as np
import pytest
import trimesh

from core.design_surface_sampling import DesignSurfaceSample, sample_design_surface


def _mesh(vertices, faces):
    return trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
    )


def _sloped_square(z_offset=0.0):
    vertices = [
        [0, 0, z_offset + 100],
        [10, 0, z_offset + 120],
        [10, 10, z_offset + 150],
        [0, 10, z_offset + 130],
    ]
    return _mesh(vertices, [[0, 1, 2], [0, 2, 3]])


def test_samples_piecewise_linear_design_elevation_in_batch():
    mesh = _sloped_square()
    before_vertices = mesh.vertices.copy()
    before_faces = mesh.faces.copy()

    results = sample_design_surface(mesh, [[2, 3], [8, 6], [4, 4]])

    assert [result.status for result in results] == ["sampled"] * 3
    assert [result.elevation_m for result in results] == pytest.approx([113, 134, 120])
    assert all(result.method == "vertical_triangle_intersection" for result in results)
    assert all(result.reason == "unique_surface_elevation" for result in results)
    assert np.array_equal(mesh.vertices, before_vertices)
    assert np.array_equal(mesh.faces, before_faces)


def test_shared_triangle_edge_duplicate_hits_resolve_to_one_elevation():
    mesh = _sloped_square()

    result, = sample_design_surface(mesh, [5, 5])

    assert result.status == "sampled"
    assert result.elevation_m == pytest.approx(125)


def test_distinct_vertical_intersections_are_ambiguous_not_selected():
    lower = _sloped_square(0)
    upper = _sloped_square(50)
    mesh = trimesh.util.concatenate([lower, upper])

    result, = sample_design_surface(mesh, [2, 3])

    assert result.status == "ambiguous"
    assert result.elevation_m is None
    assert result.reason == "multiple_distinct_surface_elevations"


def test_outside_footprint_and_mesh_hole_have_no_extrapolated_value():
    mesh = _mesh(
        [[0, 0, 1], [1, 0, 1], [0, 1, 1], [3, 0, 2], [4, 0, 2], [3, 1, 2]],
        [[0, 1, 2], [3, 4, 5]],
    )

    outside, hole = sample_design_surface(mesh, [[5, 5], [2, 0.2]])

    assert outside.status == "outside"
    assert hole.status == "outside"
    assert outside.elevation_m is None and hole.elevation_m is None
    assert outside.reason == hole.reason == "outside_footprint_or_mesh_hole"


def test_point_just_outside_triangle_is_not_extrapolated_within_xy_tolerance():
    mesh = _mesh([[0, 0, 1], [1, 0, 2], [0, 1, 3]], [[0, 1, 2]])

    result, = sample_design_surface(mesh, [-1.0e-9, 0.2])

    assert result.status == "outside"
    assert result.elevation_m is None


def test_vertical_projected_face_is_ambiguous_at_its_xy_trace():
    mesh = _mesh([[0, 0, 0], [0, 0, 10], [0, 5, 5]], [[0, 1, 2]])

    result, off_face = sample_design_surface(mesh, [[0, 2], [1.0e-5, 2]])

    assert result.status == "ambiguous"
    assert result.elevation_m is None
    assert result.reason == "vertical_or_ill_conditioned_face"
    assert off_face.status == "outside"


def test_non_finite_and_unparseable_xy_are_invalid_per_point():
    mesh = _sloped_square()

    results = sample_design_surface(mesh, [[1, 1], [np.nan, 2], [3, np.inf], ["bad", 2]])

    assert [result.status for result in results] == ["sampled", "invalid", "invalid", "invalid"]
    assert all(results[index].elevation_m is None for index in (1, 2, 3))
    assert all(
        results[index].reason == "non_finite_or_unparseable_xy"
        for index in (1, 2, 3)
    )


def test_invalid_mesh_reports_invalid_instead_of_zero_elevation():
    results = sample_design_surface(trimesh.Trimesh(process=False), [[0, 0], [np.nan, 0]])

    assert [result.status for result in results] == ["invalid", "invalid"]
    assert results[0].reason == "invalid_or_empty_mesh"
    assert results[1].reason == "non_finite_or_unparseable_xy"
    assert all(result.elevation_m is None for result in results)


def test_result_is_immutable_and_single_xy_returns_one_result():
    result, = sample_design_surface(_sloped_square(), [2, 3])

    assert isinstance(result, DesignSurfaceSample)
    with pytest.raises((AttributeError, TypeError)):
        result.elevation_m = 0.0


@pytest.mark.parametrize("xy", [[], [1], [[1, 2, 3]], np.zeros((2, 1))])
def test_malformed_query_shape_raises_value_error(xy):
    with pytest.raises(ValueError, match="N×2"):
        sample_design_surface(_sloped_square(), xy)


def test_bad_tolerances_raise_value_error():
    with pytest.raises(ValueError, match="tolerances"):
        sample_design_surface(_sloped_square(), [1, 1], xy_tolerance_m=0)
