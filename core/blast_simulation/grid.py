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

from core.blast_simulation.contracts import VoxelGridSpecification


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
