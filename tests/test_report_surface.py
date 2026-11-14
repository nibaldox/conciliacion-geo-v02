"""Tests for core.report_surface — plan surface grid and shaded relief."""
import numpy as np
import pytest
import trimesh

from core.report_surface import (
    PlanSurface,
    plan_surface_from_mesh,
    sections_bounds,
    shaded_relief,
)

X0, Y0 = 93_000.0, 20_400.0
A, B, C = 0.25, -0.4, 3100.0


def _plane_z(x, y):
    return A * (x - X0) + B * (y - Y0) + C


def _square_mesh(size_x=40.0, size_y=20.0):
    xy = np.array([
        [X0, Y0], [X0 + size_x, Y0], [X0 + size_x, Y0 + size_y], [X0, Y0 + size_y],
    ])
    vertices = np.column_stack([xy, _plane_z(xy[:, 0], xy[:, 1])])
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _triangle_mesh():
    vertices = np.array([
        [X0, Y0, _plane_z(X0, Y0)],
        [X0 + 20.0, Y0, _plane_z(X0 + 20.0, Y0)],
        [X0, Y0 + 20.0, _plane_z(X0, Y0 + 20.0)],
    ])
    return trimesh.Trimesh(vertices=vertices, faces=np.array([[0, 1, 2]]), process=False)


def _surface(z, cell=1.0):
    z = np.asarray(z, dtype=float)
    return PlanSurface(
        x=np.arange(z.shape[1]) * cell, y=np.arange(z.shape[0]) * cell, z=z, cell_m=cell,
    )


def _plane_surface(gx, gy, n=12):
    xs = np.arange(n, dtype=float)
    grid_x, grid_y = np.meshgrid(xs, xs)
    return _surface(gx * grid_x + gy * grid_y + 100.0)


class TestPlanSurfaceFromMesh:
    def test_two_triangle_plane_is_reproduced_inside(self):
        surface = plan_surface_from_mesh(_square_mesh())
        assert isinstance(surface, PlanSurface)
        assert surface.z.shape == (len(surface.y), len(surface.x))
        grid_x, grid_y = np.meshgrid(surface.x, surface.y)
        assert np.all(np.isfinite(surface.z))
        np.testing.assert_allclose(surface.z, _plane_z(grid_x, grid_y), atol=1e-6)

    def test_nan_outside_any_triangle(self):
        surface = plan_surface_from_mesh(_triangle_mesh())
        grid_x, grid_y = np.meshgrid(surface.x, surface.y)
        local = (grid_x - X0) + (grid_y - Y0)
        inside = local < 20.0 - 1e-6
        outside = local > 20.0 + 1e-6
        assert outside.any() and inside.any()
        assert np.all(np.isnan(surface.z[outside]))
        np.testing.assert_allclose(
            surface.z[inside], _plane_z(grid_x[inside], grid_y[inside]), atol=1e-6,
        )

    def test_nan_where_bounds_exceed_the_mesh(self):
        bounds = (X0 - 10.0, Y0 - 10.0, X0 + 50.0, Y0 + 30.0)
        surface = plan_surface_from_mesh(_square_mesh(), bounds=bounds)
        grid_x, grid_y = np.meshgrid(surface.x, surface.y)
        outside = (grid_x < X0 - 1e-6) | (grid_x > X0 + 40.0 + 1e-6) \
            | (grid_y < Y0 - 1e-6) | (grid_y > Y0 + 20.0 + 1e-6)
        assert outside.any()
        assert np.all(np.isnan(surface.z[outside]))
        assert np.all(np.isfinite(surface.z[~outside & (grid_x > X0 + 1e-6) & (grid_y > Y0 + 1e-6)
                                            & (grid_x < X0 + 40.0 - 1e-6) & (grid_y < Y0 + 20.0 - 1e-6)]))

    def test_cell_has_half_metre_floor(self):
        surface = plan_surface_from_mesh(_square_mesh())
        assert surface.cell_m == pytest.approx(0.5)
        assert np.allclose(np.diff(surface.x), 0.5)
        assert np.allclose(np.diff(surface.y), 0.5)
        assert surface.x.size == 81 and surface.y.size == 41

    def test_cell_grows_to_respect_max_nodes(self):
        surface = plan_surface_from_mesh(_square_mesh(), max_nodes=200)
        assert surface.z.size <= 200
        assert surface.cell_m > 0.5
        tighter = surface.cell_m * 0.9
        assert (int(40.0 / tighter) + 1) * (int(20.0 / tighter) + 1) > 200
        assert np.allclose(np.diff(surface.x), surface.cell_m)

    def test_default_max_nodes_on_large_extent(self):
        surface = plan_surface_from_mesh(_square_mesh(2000.0, 1000.0))
        assert surface.z.size <= 250_000
        assert surface.cell_m > 0.5

    def test_bounds_crop(self):
        bounds = (X0 + 10.0, Y0 + 5.0, X0 + 20.0, Y0 + 12.0)
        surface = plan_surface_from_mesh(_square_mesh(), bounds=bounds)
        assert surface.x[0] == pytest.approx(bounds[0])
        assert surface.y[0] == pytest.approx(bounds[1])
        assert surface.x[-1] <= bounds[2] + 1e-9
        assert surface.y[-1] <= bounds[3] + 1e-9
        assert surface.x[-1] > bounds[2] - surface.cell_m
        grid_x, grid_y = np.meshgrid(surface.x, surface.y)
        np.testing.assert_allclose(surface.z, _plane_z(grid_x, grid_y), atol=1e-6)

    def test_overlapping_triangles_keep_the_highest(self):
        low = _square_mesh()
        high = low.copy()
        high.vertices = low.vertices + np.array([0.0, 0.0, 7.0])
        mesh = trimesh.util.concatenate([high, low])
        surface = plan_surface_from_mesh(mesh)
        grid_x, grid_y = np.meshgrid(surface.x, surface.y)
        np.testing.assert_allclose(surface.z, _plane_z(grid_x, grid_y) + 7.0, atol=1e-6)

    def test_vertical_and_degenerate_triangles_are_ignored(self):
        base = _square_mesh()
        wall = np.array([
            [X0 + 5.0, Y0 + 5.0, 0.0], [X0 + 15.0, Y0 + 15.0, 0.0], [X0 + 15.0, Y0 + 15.0, 9000.0],
        ])
        vertices = np.vstack([base.vertices, wall])
        faces = np.vstack([base.faces, [[4, 5, 6]]])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        surface = plan_surface_from_mesh(mesh)
        grid_x, grid_y = np.meshgrid(surface.x, surface.y)
        np.testing.assert_allclose(surface.z, _plane_z(grid_x, grid_y), atol=1e-6)

    def test_none_without_usable_mesh(self):
        assert plan_surface_from_mesh(None) is None
        empty = trimesh.Trimesh(vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=int))
        assert plan_surface_from_mesh(empty) is None

    def test_none_when_bounds_miss_the_mesh(self):
        bounds = (X0 + 500.0, Y0 + 500.0, X0 + 600.0, Y0 + 600.0)
        assert plan_surface_from_mesh(_square_mesh(), bounds=bounds) is None

    def test_plan_surface_is_frozen(self):
        surface = plan_surface_from_mesh(_square_mesh())
        with pytest.raises(Exception):
            surface.cell_m = 2.0


class TestShadedRelief:
    def test_flat_surface_is_uniform(self):
        shade, extent = shaded_relief(_surface(np.full((8, 10), 3100.0), cell=2.0))
        assert shade.shape == (8, 10)
        np.testing.assert_allclose(shade, np.sin(np.radians(45.0)), atol=1e-12)
        assert extent == pytest.approx((-1.0, 19.0, -1.0, 15.0))

    def test_slope_facing_the_light_is_brighter(self):
        facing, _ = shaded_relief(_plane_surface(0.5, -0.5))
        away, _ = shaded_relief(_plane_surface(-0.5, 0.5))
        flat, _ = shaded_relief(_plane_surface(0.0, 0.0))
        assert np.ptp(facing) < 1e-9 and np.ptp(away) < 1e-9
        assert facing.mean() > flat.mean() > away.mean()

    def test_values_stay_in_unit_range(self):
        rng = np.random.default_rng(7)
        shade, _ = shaded_relief(_surface(rng.normal(0.0, 30.0, (20, 20))))
        assert np.nanmin(shade) >= 0.0 and np.nanmax(shade) <= 1.0

    def test_light_direction_and_exaggeration_are_parameters(self):
        surface = _plane_surface(0.5, -0.5)
        default, _ = shaded_relief(surface)
        from_se, _ = shaded_relief(surface, azimuth_deg=135.0)
        gentle, _ = shaded_relief(surface, z_factor=0.2)
        assert from_se.mean() < default.mean()
        assert abs(gentle.mean() - np.sin(np.radians(45.0))) < abs(default.mean() - np.sin(np.radians(45.0)))

    def test_nan_is_preserved_and_neighbours_stay_finite(self):
        xs = np.arange(12, dtype=float)
        grid_x, grid_y = np.meshgrid(xs, xs)
        z = 0.3 * grid_x + 0.1 * grid_y
        z[4:7, 5:8] = np.nan
        z[0, 0] = np.nan
        shade, _ = shaded_relief(_surface(z))
        np.testing.assert_array_equal(np.isnan(shade), np.isnan(z))
        assert np.ptp(shade[np.isfinite(shade)]) < 1e-9

    def test_all_nan_surface(self):
        shade, _ = shaded_relief(_surface(np.full((4, 5), np.nan)))
        assert shade.shape == (4, 5)
        assert np.all(np.isnan(shade))


class TestSectionsBounds:
    def test_margin_around_every_section_line(self):
        sections = [
            {"name": "S-01", "x0": 100.0, "y0": 200.0, "x1": 160.0, "y1": 200.0},
            {"name": "S-02", "polyline": [[90.0, 150.0], [120.0, 260.0], [130.0, 255.0]]},
        ]
        assert sections_bounds(sections) == pytest.approx((60.0, 120.0, 190.0, 290.0))
        assert sections_bounds(sections, margin_m=5.0) == pytest.approx((85.0, 145.0, 165.0, 265.0))

    def test_origin_azimuth_length_sections(self):
        sections = [{"name": "S-01", "origin": [1000.0, 2000.0], "azimuth": 90.0, "length": 200.0}]
        assert sections_bounds(sections, margin_m=0.0) == pytest.approx((900.0, 2000.0, 1100.0, 2000.0))

    def test_sections_without_endpoints_are_skipped(self):
        sections = [
            {"name": "S-00"},
            None,
            {"name": "S-01", "x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 20.0},
        ]
        assert sections_bounds(sections, margin_m=1.0) == pytest.approx((-1.0, -1.0, 11.0, 21.0))

    def test_none_when_no_section_has_endpoints(self):
        assert sections_bounds([]) is None
        assert sections_bounds(None) is None
        assert sections_bounds([{"name": "S-01"}]) is None
