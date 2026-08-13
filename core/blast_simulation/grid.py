"""Voxel grid numerical utilities.

Pure NumPy helpers that turn a :class:`VoxelGridSpecification` into the
array structures the engine consumes. Nothing here depends on FastAPI,
Streamlit, Plotly or SQLite — the module is pure domain math.

Conventions:

* The grid is right-handed with axes ``(nx, ny, nz)`` corresponding to
  ``(East, North, Elevation)`` (mining standard).
* Voxel centres are stored as a flat ``(n_voxels, 3)`` float32 array —
  this keeps memory predictable for million-voxel grids
  (1e6 voxels × 3 × 4 B = 12 MB).
* ``iter_voxel_blocks`` yields contiguous slices over the flat axis so
  the engine never has to materialise an ``(n_sources, n_voxels)``
  dense matrix at once.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np

from core.blast_simulation.contracts import DomainBounds, VoxelGridSpecification


def voxel_centres_flat(grid: VoxelGridSpecification) -> np.ndarray:
    """Return voxel centres as a flat ``(n_voxels, 3)`` float32 array.

    The flat axis is C-contiguous over ``(nx, ny, nz)`` so voxel index
    ``i`` corresponds to ``(ix, iy, iz)`` via ``np.unravel_index``.
    """
    nx, ny, nz = grid.shape
    dx = grid.voxel_size_m
    x0, y0, z0 = grid.bounds.x_min, grid.bounds.y_min, grid.bounds.z_min
    # Centres sit at the middle of each voxel.
    xs = x0 + (np.arange(nx, dtype=np.float32) + 0.5) * dx
    ys = y0 + (np.arange(ny, dtype=np.float32) + 0.5) * dx
    zs = z0 + (np.arange(nz, dtype=np.float32) + 0.5) * dx
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])


def iter_voxel_blocks(
    n_voxels: int,
    *,
    block_size: int,
) -> Iterator[tuple[int, int]]:
    """Yield ``(start, stop)`` index ranges over ``[0, n_voxels)``.

    The last block may be smaller than ``block_size``. Used by the engine
    to evaluate the kernel one voxel-block at a time, keeping peak memory
    bounded by ``n_sources × block_size`` instead of ``n_sources × n_voxels``.
    """
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    for start in range(0, n_voxels, block_size):
        yield start, min(start + block_size, n_voxels)


def estimated_memory_bytes(
    n_voxels: int,
    n_sources: int,
    *,
    block_size: int,
    n_accumulator_fields: int = 5,
) -> int:
    """Conservative peak-memory estimate for the engine.

    The dominant allocations are:

    * Voxel centres array: ``n_voxels × 3 × 4`` bytes.
    * Per-voxel accumulator fields: ``n_accumulator_fields × n_voxels × 4``.
    * Per-block distance matrix: ``n_sources × block_size × 4``.
    * Per-block kernel weights: ``n_sources × block_size × 4``.
    """
    centres = n_voxels * 3 * 4
    accumulators = n_accumulator_fields * n_voxels * 4
    block = 2 * n_sources * min(block_size, n_voxels) * 4
    return centres + accumulators + block


def point_in_domain_mask(
    points: np.ndarray,
    grid: VoxelGridSpecification,
) -> np.ndarray:
    """Boolean mask: True where each point is inside the domain bounds."""
    b = grid.bounds
    return (
        (points[:, 0] >= b.x_min)
        & (points[:, 0] <= b.x_max)
        & (points[:, 1] >= b.y_min)
        & (points[:, 1] <= b.y_max)
        & (points[:, 2] >= b.z_min)
        & (points[:, 2] <= b.z_max)
    )


def reshape_to_grid(flat: np.ndarray, grid: VoxelGridSpecification) -> np.ndarray:
    """Reshape a flat per-voxel array back to its 3D ``(nx, ny, nz)`` grid."""
    nx, ny, nz = grid.shape
    if flat.size != nx * ny * nz:
        raise ValueError(
            f"flat size {flat.size} does not match grid shape {(nx, ny, nz)}"
        )
    return flat.reshape((nx, ny, nz))


def voxel_grid_with_effective_bounds(
    grid: VoxelGridSpecification,
) -> tuple[np.ndarray, DomainBounds, np.ndarray]:
    """Return ``(centres_flat, effective_bounds, partial_boundary_mask)``."""
    if grid.bounds is None:
        empty = np.empty((0, 3), dtype=np.float32)
        empty_mask = np.empty((0,), dtype=bool)
        return empty, DomainBounds(0.0, 0.0, 0.0, 0.0, 0.0, 0.0), empty_mask

    nx, ny, nz = grid.shape
    dx = grid.voxel_size_m
    b = grid.bounds

    effective_bounds = DomainBounds(
        x_min=b.x_min,
        y_min=b.y_min,
        z_min=b.z_min,
        x_max=b.x_min + nx * dx,
        y_max=b.y_min + ny * dx,
        z_max=b.z_min + nz * dx,
    )

    centres = voxel_centres_flat(grid)
    half_dx = dx / 2.0
    cx, cy, cz = centres[:, 0], centres[:, 1], centres[:, 2]
    partial_boundary = (
        ((cx - half_dx < b.x_min) | (cx + half_dx > b.x_max))
        | ((cy - half_dx < b.y_min) | (cy + half_dx > b.y_max))
        | ((cz - half_dx < b.z_min) | (cz + half_dx > b.z_max))
    ) & ~(
        (cx >= b.x_min) & (cx <= b.x_max)
        & (cy >= b.y_min) & (cy <= b.y_max)
        & (cz >= b.z_min) & (cz <= b.z_max)
    )
    return centres, effective_bounds, partial_boundary


def intersection_mask_flat(grid: VoxelGridSpecification) -> np.ndarray:
    """Boolean ``(n_voxels,)`` mask — intersection semantics (Brecha 3.4).

    A voxel is considered part of the domain if its **box** (centre ±
    ``dx/2`` along each axis) intersects the requested bounds. This
    captures the partial-boundary voxels that the ``ceil``-shaped grid
    produces near the requested ``DomainBounds`` edges.
    """
    centres, effective_bounds, partial = voxel_grid_with_effective_bounds(grid)
    if centres.size == 0:
        return np.empty((0,), dtype=bool)
    b = grid.bounds
    cx, cy, cz = centres[:, 0], centres[:, 1], centres[:, 2]
    half = effective_bounds  # ensure dependency
    inside = (
        (cx >= b.x_min) & (cx <= b.x_max)
        & (cy >= b.y_min) & (cy <= b.y_max)
        & (cz >= b.z_min) & (cz <= b.z_max)
    )
    return inside | partial
