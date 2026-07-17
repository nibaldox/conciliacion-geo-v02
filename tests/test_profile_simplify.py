"""Unit tests for RDP profile simplification and solid-toe projection."""

import numpy as np
import pytest

from core.profile_simplify import _detect_and_project_solid_toe, ramer_douglas_peucker


def test_rdp_removes_collinear_interior_points():
    points = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    simplified = ramer_douglas_peucker(points, epsilon=0.01)
    np.testing.assert_allclose(simplified, points[[0, -1]])


def test_rdp_keeps_corner_above_epsilon():
    points = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [2.0, 1.0]])
    simplified = ramer_douglas_peucker(points, epsilon=0.2)
    np.testing.assert_allclose(simplified, points)


@pytest.mark.parametrize(
    "points",
    [
        np.empty((0, 2)),
        np.array([[1.0, 2.0]]),
        np.array([[1.0, 2.0], [3.0, 4.0]]),
    ],
)
def test_rdp_returns_short_inputs_unchanged(points):
    simplified = ramer_douglas_peucker(points, epsilon=0.5)
    np.testing.assert_array_equal(simplified, points)


def test_rdp_handles_closed_polyline_with_coincident_endpoints():
    points = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
    simplified = ramer_douglas_peucker(points, epsilon=0.1)
    np.testing.assert_allclose(simplified, points)


def test_rdp_propagates_nan_without_crashing_and_keeps_endpoints():
    points = np.array([[0.0, 0.0], [1.0, np.nan], [2.0, 0.0]])
    simplified = ramer_douglas_peucker(points, epsilon=0.1)
    np.testing.assert_allclose(simplified, points[[0, -1]])


def test_solid_toe_projection_returns_default_for_two_points():
    face = np.array([[0.0, 15.0], [5.0, 0.0]])
    toe_x, angle, spill_point = _detect_and_project_solid_toe(face, face_threshold=40.0)
    assert toe_x == pytest.approx(5.0)
    assert angle == pytest.approx(np.degrees(np.arctan2(15.0, 5.0)))
    np.testing.assert_allclose(spill_point, face[-1])


def test_solid_toe_projection_removes_shallow_spill_tail():
    face = np.array(
        [
            [0.0, 15.0],
            [1.0, 12.0],
            [2.0, 9.0],
            [3.0, 6.0],
            [6.0, 4.5],
            [9.0, 3.0],
            [12.0, 1.5],
            [15.0, 0.0],
        ]
    )

    toe_x, angle, spill_point = _detect_and_project_solid_toe(face, face_threshold=40.0)

    assert toe_x < face[-1, 0]
    assert angle > 60.0
    np.testing.assert_allclose(spill_point, [3.0, 6.0])
