import numpy as np

from api.routers.sections import _read_polyline_xy_csv


def test_headerless_xyz_csv_preserves_first_point():
    content = (
        b"92364.642565,21785.600252,2945.000000\n"
        b"92354.749498,21787.058755,2945.000000\n"
        b"92344.856432,21788.517259,2945.000000\n"
    )

    points = _read_polyline_xy_csv(content)

    assert points.shape == (3, 2)
    np.testing.assert_allclose(points[0], [92364.642565, 21785.600252])
    np.testing.assert_allclose(points[-1], [92344.856432, 21788.517259])


def test_headered_xy_csv_preserves_existing_behavior():
    content = b"X,Y,Z\n100.0,200.0,10.0\n300.0,400.0,12.0\n"

    points = _read_polyline_xy_csv(content)

    assert points.shape == (2, 2)
    np.testing.assert_allclose(points, [[100.0, 200.0], [300.0, 400.0]])
