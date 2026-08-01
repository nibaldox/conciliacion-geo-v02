"""Tests for core.topo_reconciliation — grid-based design vs as-built.

Spec §6: reconcile real vs design surfaces on a common domain:
    deltaZ(x,y) = Z_real - Z_design
Sign convention: positive = over-excavation (dug too deep), negative =
remaining material (under-excavation). Volumes integrate deltaZ over the
effective cell area, not the point count.
"""
import numpy as np
import pandas as pd
import pytest

from core.topo_reconciliation import (
    classify_delta_z,
    reconcile_grid,
    reconcile_by_holes,
    grid_metrics,
)


def _flat_grid(nx=10, ny=10, cell=2.0, z0=100.0, x0=0.0, y0=0.0):
    """Regular grid over [x0, x0+nx*cell) × [y0, y0+ny*cell), flat at z0."""
    xs = x0 + cell * (np.arange(nx) + 0.5)
    ys = y0 + cell * (np.arange(ny) + 0.5)
    z = np.full((ny, nx), z0, dtype=float)
    return xs, ys, z


class TestClassifyDeltaZ:
    def test_within_tolerance(self):
        d = np.array([0.0, 0.5, -0.5, -0.99])
        s = classify_delta_z(d, tolerance_m=1.0)
        assert (s == "dentro_tolerancia").all()

    def test_symmetric_classification(self):
        d = np.array([2.0, -2.0, 0.5, -0.5])
        s = classify_delta_z(d, tolerance_m=1.0)
        assert list(s) == ["sobreexcavacion", "remanente", "dentro_tolerancia", "dentro_tolerancia"]

    def test_asymmetric_tolerance(self):
        d = np.array([1.5, -1.5, 0.5])
        s = classify_delta_z(d, tolerance_m=(0.3, 1.0))  # (neg tol, pos tol)
        assert list(s) == ["sobreexcavacion", "remanente", "dentro_tolerancia"]

    def test_nan_is_sin_cobertura(self):
        s = classify_delta_z(np.array([np.nan, 0.0]), tolerance_m=1.0)
        assert list(s) == ["sin_cobertura", "dentro_tolerancia"]


class TestGridMetrics:
    def test_identical_surfaces(self):
        xs, ys, z = _flat_grid()
        m = grid_metrics(z, z)
        assert m["mean_error_m"] == pytest.approx(0.0, abs=1e-12)
        assert m["rmse_m"] == pytest.approx(0.0, abs=1e-12)
        assert m["mae_m"] == pytest.approx(0.0, abs=1e-12)
        assert m["n_valid"] == xs.size * ys.size

    def test_constant_offset_metrics(self):
        """deltaZ = Z_real - Z_design = +2 m (real 2 m below design)."""
        _, _, z = _flat_grid()
        m = grid_metrics(z + 2.0, z)
        assert m["mean_error_m"] == pytest.approx(2.0)
        assert m["rmse_m"] == pytest.approx(2.0)
        assert m["mae_m"] == pytest.approx(2.0)
        assert m["p10_m"] == pytest.approx(2.0)
        assert m["p90_m"] == pytest.approx(2.0)
        assert m["median_m"] == pytest.approx(2.0)

    def test_nan_excluded_from_metrics(self):
        _, _, z = _flat_grid()
        z[0, 0] = np.nan
        z[1, 1] = np.nan
        m = grid_metrics(z, z + 1.0)
        assert m["n_valid"] == 100 - 2


class TestReconcileGrid:
    def test_identical_surfaces_full_compliance(self):
        xs, ys, z = _flat_grid()
        df, m = reconcile_grid(z, z, xs, ys, tolerance_m=1.0, cell_size_m=2.0)
        assert (df["status"] == "dentro_tolerancia").all()
        assert m["pct_area_compliant"] == pytest.approx(100.0)
        assert m["volume_remanente_m3"] == pytest.approx(0.0, abs=1e-9)
        assert m["volume_sobreexcavacion_m3"] == pytest.approx(0.0, abs=1e-9)
        assert m["balance_m3"] == pytest.approx(0.0, abs=1e-9)

    def test_known_remanente_volume(self):
        """Topo 2 m BELOW design over the whole domain -> V = area * 2."""
        xs, ys, z = _flat_grid(nx=10, ny=10, cell=2.0)
        df, m = reconcile_grid(z - 2.0, z, xs, ys, tolerance_m=1.0, cell_size_m=2.0)
        area = (10 * 2.0) ** 2
        assert m["volume_remanente_m3"] == pytest.approx(area * 2.0)
        assert m["volume_sobreexcavacion_m3"] == pytest.approx(0.0, abs=1e-9)
        assert m["pct_area_remanente"] == pytest.approx(100.0)
        assert m["pct_area_compliant"] == pytest.approx(0.0)

    def test_known_sobreexcavacion_volume(self):
        xs, ys, z = _flat_grid(nx=10, ny=10, cell=2.0)
        df, m = reconcile_grid(z + 1.5, z, xs, ys, tolerance_m=1.0, cell_size_m=2.0)
        area = (10 * 2.0) ** 2
        assert m["volume_sobreexcavacion_m3"] == pytest.approx(area * 1.5)
        assert m["volume_remanente_m3"] == pytest.approx(0.0, abs=1e-9)

    def test_balance_volumetrico(self):
        xs, ys, z = _flat_grid()
        z_topo = z.copy()
        z_topo[:5, :] = z[:5, :] - 2.0  # remanente half
        z_topo[5:, :] = z[5:, :] + 1.0  # sobreexcavacion half
        df, m = reconcile_grid(z_topo, z, xs, ys, tolerance_m=0.5, cell_size_m=2.0)
        assert m["volume_remanente_m3"] == pytest.approx(10 * 2.0 * 5 * 2.0 * 2.0)
        assert m["volume_sobreexcavacion_m3"] == pytest.approx(10 * 2.0 * 5 * 2.0 * 1.0)
        assert m["balance_m3"] == pytest.approx(m["volume_sobreexcavacion_m3"] - m["volume_remanente_m3"])

    def test_resolution_invariance(self):
        """Same surface at 2 m vs 1 m cells -> same volumes within tolerance."""
        xs2, ys2, z2 = _flat_grid(nx=10, ny=10, cell=2.0)
        xs1, ys1, z1 = _flat_grid(nx=20, ny=20, cell=1.0)
        _, m2 = reconcile_grid(z2 - 1.0, z2, xs2, ys2, tolerance_m=0.5, cell_size_m=2.0)
        _, m1 = reconcile_grid(z1 - 1.0, z1, xs1, ys1, tolerance_m=0.5, cell_size_m=1.0)
        assert m1["volume_remanente_m3"] == pytest.approx(m2["volume_remanente_m3"], rel=1e-9)
        assert m1["pct_area_remanente"] == pytest.approx(m2["pct_area_remanente"], rel=1e-9)

    def test_sin_cobertura_region(self):
        xs, ys, z = _flat_grid()
        z_topo = z.copy()
        z_topo[:3, :] = np.nan
        df, m = reconcile_grid(z_topo, z, xs, ys, tolerance_m=1.0, cell_size_m=2.0)
        assert (df["status"] == "sin_cobertura").sum() == 30
        assert m["pct_area_sin_cobertura"] == pytest.approx(30.0)
        assert m["n_valid"] == 70

    def test_cell_area_used_for_volumes(self):
        """Volumes must use cell area, not point count (spec §6)."""
        xs2, ys2, z2 = _flat_grid(nx=10, ny=10, cell=2.0)
        df, m = reconcile_grid(z2 - 2.0, z2, xs2, ys2, tolerance_m=1.0, cell_size_m=2.0)
        assert df["cell_area_m2"].iloc[0] == pytest.approx(4.0)
        assert m["volume_remanente_m3"] == pytest.approx((df["cell_area_m2"] * 2.0).sum())

    def test_shape_mismatch_raises(self):
        xs, ys, z = _flat_grid(nx=10, ny=10, cell=2.0)
        z_bad = np.full((9, 10), 100.0)
        with pytest.raises(ValueError, match="shape"):
            reconcile_grid(z_bad, z, xs, ys, tolerance_m=1.0, cell_size_m=2.0)

    def test_cell_size_mismatch_raises(self):
        xs, ys, z = _flat_grid(nx=10, ny=10, cell=2.0)
        with pytest.raises(ValueError, match="cell_size"):
            reconcile_grid(z, z, xs, ys, tolerance_m=1.0, cell_size_m=3.0)


class TestReconcileByHoles:
    def test_hole_assignment_nearest_collar(self):
        """Each cell is assigned to the nearest hole (spec §6 by-hole results)."""
        xs, ys, z = _flat_grid(nx=8, ny=8, cell=2.0)  # 16×16 m domain
        holes = pd.DataFrame({
            "X": [2.0, 14.0, 2.0, 14.0],
            "Y": [2.0, 2.0, 14.0, 14.0],
            "label_pozo": ["A", "B", "C", "D"],
            "area_influence_m2": [64.0, 64.0, 64.0, 64.0],
        })
        z_topo = z.copy()
        z_topo[:4, :4] = z[:4, :4] - 2.0  # remanente near hole A
        df, m = reconcile_grid(z_topo, z, xs, ys, tolerance_m=0.5, cell_size_m=2.0)
        by_hole = reconcile_by_holes(df, holes)
        assert set(by_hole["label_pozo"]) == {"A", "B", "C", "D"}
        a = by_hole.set_index("label_pozo").loc["A"]
        assert a["volume_remanente_m3"] > 0
        b = by_hole.set_index("label_pozo").loc["B"]
        assert b["volume_remanente_m3"] == pytest.approx(0.0, abs=1e-9)

    def test_cells_inside_influence_area_only(self):
        xs, ys, z = _flat_grid(nx=8, ny=8, cell=2.0)
        holes = pd.DataFrame({
            "X": [8.0], "Y": [8.0], "label_pozo": ["CENTRO"], "area_influence_m2": [64.0],
        })
        df, _ = reconcile_grid(z, z, xs, ys, tolerance_m=1.0, cell_size_m=2.0)
        by_hole = reconcile_by_holes(df, holes)
        assert by_hole["n_celdas"].iloc[0] == 16  # 4×4 cells within 8×8 m


class TestGridFromMesh:
    def test_flat_prism_grid_values(self):
        trimesh = pytest.importorskip("trimesh")
        import trimesh.creation as tc

        mesh = tc.box(extents=(20.0, 20.0, 10.0), transform=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        mesh.apply_translation([10.0, 10.0, 100.0])  # top at z=105
        xs = np.arange(2.0, 20.0, 4.0)
        ys = np.arange(2.0, 20.0, 4.0)
        from core.topo_reconciliation import grid_from_mesh
        z_grid = grid_from_mesh(mesh, xs, ys)
        assert np.allclose(z_grid, 105.0, atol=0.1)

    def test_raycast_and_sample_agree(self):
        """Open surface (TIN-like quad): both sampling methods agree."""
        trimesh = pytest.importorskip("trimesh")

        verts = np.array([[0.0, 0.0, 105.0], [20.0, 0.0, 105.0], [20.0, 20.0, 105.0], [0.0, 20.0, 105.0]])
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        mesh = trimesh.Trimesh(vertices=verts, faces=faces)
        xs = np.arange(2.0, 20.0, 4.0)
        ys = np.arange(2.0, 20.0, 4.0)
        from core.topo_reconciliation import grid_from_mesh
        z_ray = grid_from_mesh(mesh, xs, ys, method="raycast")
        z_bin = grid_from_mesh(mesh, xs, ys, method="sample_bin")
        assert np.allclose(z_ray, z_bin, atol=0.5)
        assert np.allclose(z_ray, 105.0, atol=0.1)

    def test_outside_mesh_is_nan(self):
        trimesh = pytest.importorskip("trimesh")
        import trimesh.creation as tc

        mesh = tc.box(extents=(20.0, 20.0, 10.0), transform=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        mesh.apply_translation([10.0, 10.0, 100.0])
        from core.topo_reconciliation import grid_from_mesh
        z = grid_from_mesh(mesh, np.array([50.0]), np.array([50.0]))
        assert np.isnan(z[0, 0])
