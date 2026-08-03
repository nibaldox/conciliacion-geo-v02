"""Slicing utilities — horizontal (plan) and vertical (section) cuts.

Turn the 3D energy field into 2D representations consumable by the UI.
Both functions return JSON-serialisable :class:`PlanSlice` /
:class:`SectionSlice` objects that reference the underlying 2D data by
SHA-256 (the raw 2D array is persisted separately or sent via the API
as a base64 payload, never embedded in the JSON metadata).
"""
from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np

from core.blast_simulation.contracts import (
    PlanSlice,
    SectionSlice,
    SimulationResult,
    VoxelGridSpecification,
)
from core.blast_simulation.grid import reshape_to_grid


def _sha256_bytes(data: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(data).tobytes()).hexdigest()


def plan_slice(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
    elevation_m: float,
    energy_unit: str,
) -> PlanSlice:
    """Horizontal slice at the elevation closest to ``elevation_m``.

    The returned 2D array has shape ``(nx, ny)`` (East × North). Voxels
    at the closest z-index are summed into the slice.
    """
    field_3d = reshape_to_grid(np.asarray(energy_total_flat), grid)
    nz = grid.shape[2]
    z_index = int(
        np.clip(
            int((elevation_m - grid.bounds.z_min) / grid.voxel_size_m),
            0,
            nz - 1,
        )
    )
    slice_2d = field_3d[:, :, z_index]
    represented = float(slice_2d.sum() * grid.voxel_volume_m3 / grid.voxel_size_m)
    actual_elev = grid.bounds.z_min + (z_index + 0.5) * grid.voxel_size_m
    return PlanSlice(
        elevation_m=actual_elev,
        unit=energy_unit,
        grid_shape=slice_2d.shape,
        data_sha256=_sha256_bytes(slice_2d.astype(np.float32)),
        max_value=float(slice_2d.max()) if slice_2d.size else 0.0,
        mean_value=float(slice_2d.mean()) if slice_2d.size else 0.0,
        represented_energy_j=represented,
    )


def section_slice(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
    axis: str,
    coordinate_m: float,
    energy_unit: str,
) -> SectionSlice:
    """Vertical section along ``axis`` ('x' or 'y') at ``coordinate_m``."""
    if axis not in ("x", "y"):
        raise ValueError("axis must be 'x' or 'y'")
    field_3d = reshape_to_grid(np.asarray(energy_total_flat), grid)
    if axis == "x":
        nx = grid.shape[0]
        idx = int(np.clip(int((coordinate_m - grid.bounds.x_min) / grid.voxel_size_m), 0, nx - 1))
        slice_2d = field_3d[idx, :, :]  # (ny, nz)
    else:
        ny = grid.shape[1]
        idx = int(np.clip(int((coordinate_m - grid.bounds.y_min) / grid.voxel_size_m), 0, ny - 1))
        slice_2d = field_3d[:, idx, :]  # (nx, nz)
    actual_coord = (
        grid.bounds.x_min + (idx + 0.5) * grid.voxel_size_m
        if axis == "x"
        else grid.bounds.y_min + (idx + 0.5) * grid.voxel_size_m
    )
    return SectionSlice(
        axis=axis,
        coordinate_m=actual_coord,
        unit=energy_unit,
        grid_shape=slice_2d.shape,
        data_sha256=_sha256_bytes(slice_2d.astype(np.float32)),
        max_value=float(slice_2d.max()) if slice_2d.size else 0.0,
        mean_value=float(slice_2d.mean()) if slice_2d.size else 0.0,
    )


def compute_slices(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
    energy_unit: str,
    plan_elevations: Iterable[float] = (),
    section_coords: Iterable[tuple[str, float]] = (),
) -> tuple[tuple[PlanSlice, ...], tuple[SectionSlice, ...]]:
    """Build the plan + section slices requested by the operator."""
    plans = tuple(
        plan_slice(
            energy_total_flat=energy_total_flat,
            grid=grid,
            elevation_m=elev,
            energy_unit=energy_unit,
        )
        for elev in plan_elevations
    )
    sections = tuple(
        section_slice(
            energy_total_flat=energy_total_flat,
            grid=grid,
            axis=ax,
            coordinate_m=coord,
            energy_unit=energy_unit,
        )
        for ax, coord in section_coords
    )
    return plans, sections


def attach_slices_to_result(
    result: SimulationResult,
    *,
    energy_total_flat: np.ndarray,
    plan_elevations: Iterable[float] = (),
    section_coords: Iterable[tuple[str, float]] = (),
) -> SimulationResult:
    """Return a new SimulationResult with plan/section slices attached.

    The energy unit is taken from the result's grid metadata so the
    caller cannot mix absolute and relative scales.
    """
    from dataclasses import replace
    grid = VoxelGridSpecification(
        voxel_size_m=result.grid_metadata.voxel_size_m,
        bounds=result.grid_metadata.bounds,
    )
    plans, sections = compute_slices(
        energy_total_flat=energy_total_flat,
        grid=grid,
        energy_unit=result.grid_metadata.energy_unit,
        plan_elevations=plan_elevations,
        section_coords=section_coords,
    )
    return replace(result, plan_slices=plans, section_slices=sections)
