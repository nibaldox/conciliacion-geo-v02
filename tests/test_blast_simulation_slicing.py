"""Tests for slicing.py — Falla 4 (matriz 2D real) + Falla 6 (dimensional check).

The contract:

* :func:`plan_slice` / :func:`section_slice` populate the full 2D matrix
  in ``values`` (not just max / mean / sha256 — that is Falla 4).
* The ``represented_energy_j`` aggregation reflects the field type:

    - ``energy_j``: ``sum(values * vol_ratio)``; regular voxels with
      ratio = 1 give ``sum(values)``.
    - ``energy_density_j_m3``: ``sum(values * voxel_volume_intersected)``
      which folds ``J/m³ × m³ = J`` once and only once.

* ``values``, ``x_coordinates_m``, ``y_coordinates_m``,
  ``along_coordinates_m``, ``vertical_coordinates_m``, ``valid_mask``,
  ``percentiles`` and ``source_holes_projection`` are all populated.
* The SHA-256 of the raw 2D array is stable across re-runs.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.blast_simulation.contracts import (
    DomainBounds,
    PlanSlice,
    SectionSlice,
    VoxelGridSpecification,
)
from core.blast_simulation.slicing import (
    _percentiles,
    _partial_voxel_volumes_flat,
    _sha256_bytes,
    compute_slices,
    plan_slice,
    profile_slice,
    section_slice,
)


def _build_grid() -> VoxelGridSpecification:
    return VoxelGridSpecification(
        voxel_size_m=5.0,
        bounds=DomainBounds(0, 0, 0, 10, 10, 10),
    )


def _expected_shape(grid: VoxelGridSpecification) -> tuple[int, int, int]:
    nx = max(1, int(np.floor(10 / 5)))
    ny = nx
    nz = nx
    return (nx, ny, nz)


def test_plan_slice_poplates_full_2d_matrix():
    g = _build_grid()
    nx, ny, nz = g.shape
    n = int(np.prod(g.shape))
    field = np.ones(n, dtype=np.float32)
    p = plan_slice(
        energy_total_flat=field,
        grid=g,
        elevation_m=2.5,
        energy_unit="J",
    )
    assert p.field_type == "energy_j"
    assert p.grid_shape == (nx, ny)
    assert len(p.values) == nx * ny
    assert all(v == 1.0 for v in p.values)
    assert len(p.x_coordinates_m) == nx
    assert len(p.y_coordinates_m) == ny
    assert len(p.valid_mask) == nx * ny
    assert all(p.valid_mask)
    assert set(p.percentiles.keys()) >= {"p5", "p50", "p90", "p99"}
    assert p.data_sha256 != ""
    assert p.source_holes_projection == ()


def test_plan_slice_dimensional_check_energy_j():
    g = _build_grid()
    nx, ny, _ = g.shape
    n = int(np.prod(g.shape))
    field = np.ones(n, dtype=np.float64)
    p = plan_slice(
        energy_total_flat=field,
        grid=g,
        elevation_m=2.5,
        energy_unit="J",
    )
    assert abs(p.represented_energy_j - (nx * ny)) < 1e-6


def test_plan_slice_dimensional_check_density():
    g = _build_grid()
    nx, ny, _ = g.shape
    vox_vol = g.voxel_volume_m3
    n = int(np.prod(g.shape))
    field = np.full(n, vox_vol, dtype=np.float64)
    p = plan_slice(
        energy_total_flat=field,
        grid=g,
        elevation_m=2.5,
        energy_unit="J/m3",
        field_type="energy_density_j_m3",
    )
    assert abs(p.represented_energy_j - (nx * ny * vox_vol)) < 1e-6


def test_plan_slice_real_field_matches_sum_at_z():
    g = _build_grid()
    nx, ny, nz = g.shape
    energy = np.arange(1, nx * ny * nz + 1, dtype=np.float64) * 100.0
    p = plan_slice(
        energy_total_flat=energy,
        grid=g,
        elevation_m=2.5,
        energy_unit="J",
    )
    expected = energy.reshape(nx, ny, nz)[:, :, 0].sum()
    assert abs(p.represented_energy_j - expected) < 1e-6


def test_section_slice_x_poplates_full_2d_matrix():
    g = _build_grid()
    nx, ny, nz = g.shape
    n = int(np.prod(g.shape))
    field = np.ones(n, dtype=np.float32)
    s = section_slice(
        energy_total_flat=field,
        grid=g,
        axis="x",
        coordinate_m=2.5,
        energy_unit="J",
    )
    assert s.field_type == "energy_j"
    assert s.grid_shape == (ny, nz)
    assert len(s.values) == ny * nz
    assert len(s.along_coordinates_m) == ny
    assert len(s.vertical_coordinates_m) == nz
    assert len(s.valid_mask) == ny * nz
    assert s.data_sha256 != ""
    assert abs(s.represented_energy_j - (ny * nz)) < 1e-6


def test_section_slice_y_poplates_full_2d_matrix():
    g = _build_grid()
    nx, ny, nz = g.shape
    n = int(np.prod(g.shape))
    field = np.ones(n, dtype=np.float32)
    s = section_slice(
        energy_total_flat=field,
        grid=g,
        axis="y",
        coordinate_m=2.5,
        energy_unit="J",
    )
    assert s.grid_shape == (nx, nz)
    assert abs(s.represented_energy_j - (nx * nz)) < 1e-6


def test_section_slice_real_field_matches_sum():
    g = _build_grid()
    nx, ny, nz = g.shape
    energy = np.arange(1, nx * ny * nz + 1, dtype=np.float64) * 100.0
    s_x = section_slice(
        energy_total_flat=energy, grid=g, axis="x", coordinate_m=2.5,
        energy_unit="J",
    )
    expected_x = energy.reshape(nx, ny, nz)[0, :, :].sum()
    assert abs(s_x.represented_energy_j - expected_x) < 1e-6
    s_y = section_slice(
        energy_total_flat=energy, grid=g, axis="y", coordinate_m=2.5,
        energy_unit="J",
    )
    expected_y = energy.reshape(nx, ny, nz)[:, 0, :].sum()
    assert abs(s_y.represented_energy_j - expected_y) < 1e-6


def test_plan_slice_holes_projection():
    g = _build_grid()
    n = int(np.prod(g.shape))
    field = np.ones(n, dtype=np.float32)
    holes = (("H1", 2.5, 7.5), ("H2", 100.0, 100.0))
    p = plan_slice(
        energy_total_flat=field, grid=g, elevation_m=2.5,
        energy_unit="J", source_holes_xy=holes,
    )
    assert len(p.source_holes_projection) == 2
    assert p.source_holes_projection[0]["hole_id"] == "H1"
    assert p.source_holes_projection[0]["inside_grid"] is True


def test_invalid_field_type_raises():
    g = _build_grid()
    field = np.ones(int(np.prod(g.shape)), dtype=np.float32)
    with pytest.raises(ValueError):
        plan_slice(
            energy_total_flat=field, grid=g, elevation_m=2.5,
            energy_unit="J", field_type="bogus",
        )


def test_invalid_axis_raises():
    g = _build_grid()
    field = np.ones(int(np.prod(g.shape)), dtype=np.float32)
    with pytest.raises(ValueError):
        section_slice(
            energy_total_flat=field, grid=g, axis="z", coordinate_m=2.5,
            energy_unit="J",
        )


def test_clipping_out_of_range_elevation():
    g = _build_grid()
    field = np.ones(int(np.prod(g.shape)), dtype=np.float32)
    p_high = plan_slice(
        energy_total_flat=field, grid=g, elevation_m=999.0,
        energy_unit="J",
    )
    assert p_high.elevation_m == 7.5
    p_low = plan_slice(
        energy_total_flat=field, grid=g, elevation_m=-999.0,
        energy_unit="J",
    )
    assert p_low.elevation_m == 2.5


def test_sha256_stable():
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    h1 = _sha256_bytes(arr)
    h2 = _sha256_bytes(np.ascontiguousarray(arr.astype(np.float32)))
    assert h1 == h2
    assert len(h1) == 64
    h3 = _sha256_bytes(np.array([1.0, 2.0, 3.5], dtype=np.float32))
    assert h1 != h3


def test_percentiles_keys():
    arr = np.arange(100, dtype=np.float32)
    perc = _percentiles(arr)
    assert set(perc.keys()) >= {"p5", "p50", "p90", "p99"}


def test_partial_voxel_volumes_regular_grid():
    g = _build_grid()
    pv = _partial_voxel_volumes_flat(g)
    assert np.allclose(pv, g.voxel_volume_m3)


def test_empty_grid_returns_empty_slice():
    g = VoxelGridSpecification(
        voxel_size_m=5.0, bounds=DomainBounds(0, 0, 0, 0, 0, 0),
    )
    p = plan_slice(
        energy_total_flat=np.array([], dtype=np.float64),
        grid=g, elevation_m=0.0, energy_unit="J",
    )
    assert p.grid_shape == (0, 0)
    assert p.values == ()
    assert p.represented_energy_j == 0.0


def test_profile_slice_returns_distances_and_values():
    g = _build_grid()
    field = np.ones(int(np.prod(g.shape)), dtype=np.float32)
    prof = profile_slice(
        energy_total_flat=field, grid=g,
        start_xyz=(2.5, 2.5, 2.5), end_xyz=(7.5, 7.5, 7.5),
        n_samples=10, energy_unit="J", field_type="energy_j",
    )
    assert prof["n_samples"] == 10
    assert len(prof["values"]) == 10
    assert len(prof["distances_m"]) == 10
    assert prof["distances_m"][0] == 0.0
    assert prof["distances_m"][-1] > 0.0


def test_compute_slices_batch():
    g = _build_grid()
    field = np.ones(int(np.prod(g.shape)), dtype=np.float32)
    plans, secs = compute_slices(
        energy_total_flat=field, grid=g, energy_unit="J",
        plan_elevations=(2.5, 7.5),
        section_coords=(("x", 2.5), ("y", 5.0)),
    )
    assert len(plans) == 2
    assert len(secs) == 2


def test_intersection_mask_caller_supplied():
    g = _build_grid()
    n = int(np.prod(g.shape))
    field = np.arange(1, n + 1, dtype=np.float64) * 10.0
    mask = np.ones(n, dtype=bool)
    mask[0] = False
    p = plan_slice(
        energy_total_flat=field, grid=g, elevation_m=2.5,
        energy_unit="J", intersection_mask_flat=mask,
    )
    nx, ny, _ = g.shape
    assert sum(p.valid_mask) == nx * ny - 1
