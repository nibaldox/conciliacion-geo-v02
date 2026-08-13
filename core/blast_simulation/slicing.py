"""Slicing utilities — horizontal (plan) and vertical (section) cuts.

Turn the 3D energy field into 2D representations consumable by the UI.

Dimensional contract (Brecha 4 + Brecha 6 fixes)
------------------------------------------------

``energy_total_flat`` is the **energy per voxel** in joules that the
engine accumulates (see :func:`core.blast_simulation.engine._accumulate_source`
where ``w = k * voxel_volume_m3`` is folded into the per-voxel weight).
The slicing layer must NEVER re-multiply by ``voxel_volume_m3`` to obtain
the represented energy — that would inflate units into ``J·m³``.

Each slicer accepts ``field_type``:

* ``"energy_j"`` (default): the 2D ``values`` array stores J/voxel. The
  represented energy is ``Σ values · vol_ratio`` where ``vol_ratio`` is
  the intersection-volume fraction of each voxel (``1`` for voxels whose
  centre lies inside the requested bounds, ``<1`` for partial-boundary
  voxels under ceil semantics).
* ``"energy_density_j_m3"``: the 2D ``values`` array stores J/m³. The
  represented energy is ``Σ values · voxel_volume_intersected`` which
  folds ``J/m³ × m³ = J`` once and only once.

Both modes honour the partial-boundary voxels of Brecha 3.4 (ceil
coverage): a voxel that overlaps the requested bounds by 50 % counts as
50 % of its nominal volume in the integration.

Bounded cuts are also returned when the requested elevation / coordinate
sits outside the grid: the index is clipped to the nearest existing
voxel, the actual coordinate used is reported in
``elevation_m`` / ``coordinate_m``, and the SHA-256 of the raw 2D data
keeps the audit trail.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable

import numpy as np

from core.blast_simulation.contracts import (
    DomainBounds,
    PlanSlice,
    SectionSlice,
    SimulationResult,
    VoxelGridSpecification,
)
from core.blast_simulation.grid import (
    reshape_to_grid,
    voxel_centres_flat,
)

_FIELD_TYPES = ("energy_j", "energy_density_j_m3")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sha256_bytes(data: np.ndarray) -> str:
    """SHA-256 hex digest of a NumPy array (float32, C-contiguous)."""
    return hashlib.sha256(
        np.ascontiguousarray(data, dtype=np.float32).tobytes()
    ).hexdigest()


def _intersection_mask_flat(grid: VoxelGridSpecification) -> np.ndarray:
    """Voxel-by-voxel mask using intersection semantics.

    ``True`` where the voxel's box (centre ± ``dx/2``) intersects the
    requested bounds. Falls back to point-in-domain semantics when the
    grid has no bounds (degenerate / empty). This is the locally-defined
    helper that drives the dimensional check in every plan / section
    slice: partial-boundary voxels get their volume ratio scaled by the
    fraction of the cube that lies inside the requested bounds.
    """
    if grid.bounds is None:
        return np.zeros(grid.voxel_count, dtype=bool)
    centres = voxel_centres_flat(grid)
    if centres.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    dx = float(grid.voxel_size_m)
    half = dx / 2.0
    b = grid.bounds
    cx, cy, cz = centres[:, 0], centres[:, 1], centres[:, 2]
    return (
        (cx + half >= b.x_min) & (cx - half <= b.x_max)
        & (cy + half >= b.y_min) & (cy - half <= b.y_max)
        & (cz + half >= b.z_min) & (cz - half <= b.z_max)
    )


def _percentiles(arr: np.ndarray) -> dict[str, float]:
    """p5, p50, p90, p99 — returned as a plain ``dict`` so it serialises."""
    if arr.size == 0:
        return {"p5": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0}
    flat = np.asarray(arr, dtype=np.float64).ravel()
    p5, p50, p90, p99 = np.percentile(flat, [5, 50, 90, 99])
    return {
        "p5": float(p5),
        "p50": float(p50),
        "p90": float(p90),
        "p99": float(p99),
    }


def _voxel_index(coord: float, vmin: float, dx: float, n: int) -> int:
    """Index of the voxel whose centre is closest to ``coord``.

    Out-of-range coordinates are clipped to ``[0, n - 1]`` — the returned
    coordinate is reported back to the caller in the dataclass fields so
    the UI knows the slice was clipped.
    """
    if n <= 0 or dx <= 0.0:
        return 0
    raw = int(np.floor((float(coord) - float(vmin)) / float(dx)))
    return int(np.clip(raw, 0, n - 1))


def _voxel_centres(vmin: float, dx: float, n: int) -> np.ndarray:
    """Float64 array of voxel centres along one axis."""
    if n <= 0 or dx <= 0.0:
        return np.empty(0, dtype=np.float64)
    return vmin + (np.arange(n, dtype=np.float64) + 0.5) * dx


def _partial_voxel_volumes_flat(grid: VoxelGridSpecification) -> np.ndarray:
    """Per-voxel volume (m³) actually intersecting the requested bounds.

    For voxels entirely inside the requested bounds the returned value is
    ``voxel_volume_m3``. For partial-boundary voxels (Brecha 3.4, ceil
    coverage) the value is the fraction of the voxel's cube that
    intersects the bounds. This is the canonical helper that drives
    every dimensional check in :mod:`core.blast_simulation.slicing`.
    """
    if grid.bounds is None:
        return np.empty(0, dtype=np.float64)
    centres = voxel_centres_flat(grid)
    n = centres.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    dx = float(grid.voxel_size_m)
    if dx <= 0.0:
        return np.zeros(n, dtype=np.float64)
    b = grid.bounds
    full_volume = float(grid.voxel_volume_m3)
    half = dx / 2.0
    cx, cy, cz = centres[:, 0], centres[:, 1], centres[:, 2]

    def frac(c: np.ndarray, mn: float, mx: float) -> np.ndarray:
        i_lo = np.maximum(c - half, mn)
        i_hi = np.minimum(c + half, mx)
        length = np.clip(i_hi - i_lo, 0.0, dx)
        return length / dx

    fx = frac(cx, b.x_min, b.x_max)
    fy = frac(cy, b.y_min, b.y_max)
    fz = frac(cz, b.z_min, b.z_max)
    return full_volume * (fx * fy * fz)


def _intersection_mask_from_grid(
    grid: VoxelGridSpecification,
    provided: np.ndarray | None,
) -> np.ndarray:
    """Boolean ``(n_voxels,)`` mask — intersection semantics.

    Uses the value supplied by the caller when present; otherwise derives
    it from the grid via :func:`intersection_mask_flat`.
    """
    if provided is not None:
        return np.asarray(provided, dtype=bool)
    return _intersection_mask_flat(grid)


def _project_holes_plan(
    *,
    holes_xy: tuple[tuple[str, float, float], ...],
    x_min: float,
    y_min: float,
    dx: float,
    slice_2d: np.ndarray,
) -> tuple[dict[str, Any], ...]:
    """Project ``(hole_id, x, y)`` onto a plan slice (shape ``(nx, ny)``).

    Returns one dict per hole with the resolved voxel index and the value
    found in the slice at that index. Out-of-grid coordinates are
    clipped; the explicit ``inside_grid`` flag distinguishes holes whose
    voxel centre really lies inside the slice from those that were
    clamped to the border.
    """
    out: list[dict[str, Any]] = []
    if slice_2d.size == 0 or not holes_xy:
        return tuple(out)
    nx, ny = slice_2d.shape
    for entry in holes_xy:
        hole_id, x, y = entry[0], float(entry[1]), float(entry[2])
        ix = _voxel_index(x, x_min, dx, nx)
        iy = _voxel_index(y, y_min, dx, ny)
        value = (
            float(slice_2d[ix, iy]) if 0 <= ix < nx and 0 <= iy < ny else 0.0
        )
        out.append({
            "hole_id": str(hole_id),
            "x_m": float(x),
            "y_m": float(y),
            "ix": int(ix),
            "iy": int(iy),
            "value_at_voxel": value,
            "inside_grid": bool(
                ix < nx and iy < ny
                and (x >= x_min - dx / 2.0) and (y >= y_min - dx / 2.0)
                and (x <= x_min + nx * dx + dx / 2.0)
                and (y <= y_min + ny * dx + dx / 2.0)
            ),
        })
    return tuple(out)


def _project_holes_section(
    *,
    holes_xyz: tuple[tuple[str, float, float, float], ...],
    axis: str,
    x_min: float,
    y_min: float,
    z_min: float,
    dx: float,
    slice_2d: np.ndarray,
) -> tuple[dict[str, Any], ...]:
    """Project ``(hole_id, x, y, z)`` onto a section slice.

    The slice is shaped ``(along, vertical)``:

    * ``axis == "x"`` ⇒ ``(ny, nz)``
    * ``axis == "y"`` ⇒ ``(nx, nz)``

    The returned dict carries the resolved voxel indices plus the value
    at that voxel.
    """
    out: list[dict[str, Any]] = []
    if slice_2d.size == 0 or not holes_xyz:
        return tuple(out)
    n_along, nz = slice_2d.shape
    for entry in holes_xyz:
        hole_id = entry[0]
        x = float(entry[1])
        y = float(entry[2])
        z = float(entry[3])
        if axis == "x":
            i_along = _voxel_index(y, y_min, dx, n_along)
        else:
            i_along = _voxel_index(x, x_min, dx, n_along)
        i_vert = _voxel_index(z, z_min, dx, nz)
        value = (
            float(slice_2d[i_along, i_vert])
            if 0 <= i_along < n_along and 0 <= i_vert < nz
            else 0.0
        )
        out.append({
            "hole_id": str(hole_id),
            "axis": axis,
            "x_m": x,
            "y_m": y,
            "z_m": z,
            "i_along": int(i_along),
            "i_vertical": int(i_vert),
            "value_at_voxel": value,
        })
    return tuple(out)


def _empty_plan_slice(
    *,
    elevation_m: float,
    unit: str,
    field_type: str,
) -> PlanSlice:
    return PlanSlice(
        elevation_m=float(elevation_m),
        unit=unit,
        field_type=field_type,
        grid_shape=(0, 0),
        values=(),
        x_coordinates_m=(),
        y_coordinates_m=(),
        valid_mask=(),
        min=0.0,
        max=0.0,
        mean=0.0,
        percentiles={"p5": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0},
        source_holes_projection=(),
        data_sha256=_sha256_bytes(np.zeros(0, dtype=np.float32)),
        represented_energy_j=0.0,
    )


def _empty_section_slice(
    *,
    axis: str,
    coordinate_m: float,
    unit: str,
    field_type: str,
) -> SectionSlice:
    return SectionSlice(
        axis=axis,
        coordinate_m=float(coordinate_m),
        unit=unit,
        field_type=field_type,
        grid_shape=(0, 0),
        values=(),
        along_coordinates_m=(),
        vertical_coordinates_m=(),
        valid_mask=(),
        min=0.0,
        max=0.0,
        mean=0.0,
        percentiles={"p5": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0},
        source_holes_projection=(),
        data_sha256=_sha256_bytes(np.zeros(0, dtype=np.float32)),
        represented_energy_j=0.0,
    )


# ---------------------------------------------------------------------------
# Public API — discrete slices
# ---------------------------------------------------------------------------


def plan_slice(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
    elevation_m: float,
    energy_unit: str,
    field_type: str = "energy_j",
    source_holes_xy: tuple[tuple[str, float, float], ...] = (),
    intersection_mask_flat: np.ndarray | None = None,
) -> PlanSlice:
    """Horizontal slice at the elevation closest to ``elevation_m``.

    The returned 2D array has shape ``(nx, ny)``. ``values`` is the
    matrix flattened in C order; ``x_coordinates_m`` /
    ``y_coordinates_m`` carry the matching voxel centres (East / North,
    mining standard). ``valid_mask`` is the in-domain mask for that
    slice (slice-by-slice intersection of the global mask). The
    dimensionally-correct ``represented_energy_j`` is computed by
    :func:`_represented_energy` from the field type — see the module
    docstring for the contract.
    """
    if field_type not in _FIELD_TYPES:
        raise ValueError(
            f"field_type must be one of {_FIELD_TYPES}, got {field_type!r}"
        )
    bounds = grid.bounds
    flat = np.asarray(energy_total_flat, dtype=np.float64).ravel()
    expected = int(np.prod(grid.shape)) if grid.shape != (0, 0, 0) else 0
    if expected == 0 or bounds is None or flat.size != expected:
        return _empty_plan_slice(
            elevation_m=float(elevation_m),
            unit=energy_unit,
            field_type=field_type,
        )
    field_3d = reshape_to_grid(flat, grid)
    nx, ny, nz = field_3d.shape
    dx = float(grid.voxel_size_m)
    z_index = _voxel_index(elevation_m, bounds.z_min, dx, nz)
    actual_elev = bounds.z_min + (z_index + 0.5) * dx

    raw_slice = np.asarray(field_3d[:, :, z_index], dtype=np.float64)
    if field_type == "energy_density_j_m3":
        slice_2d = raw_slice / dx ** 3 if dx > 0.0 else raw_slice * 0.0
    else:
        slice_2d = raw_slice

    in_domain = _intersection_mask_from_grid(grid, intersection_mask_flat)
    in_domain_3d = (
        in_domain.reshape((nx, ny, nz))
        if in_domain.size == expected
        else np.ones((nx, ny, nz), dtype=bool)
    )
    slice_mask = in_domain_3d[:, :, z_index]
    valid_values = (
        slice_2d[slice_mask] if slice_mask.any() else slice_2d.ravel()
    )

    if slice_2d.size > 0:
        amin = float(slice_2d.min())
        amax = float(slice_2d.max())
        amean = float(slice_2d.mean())
    else:
        amin = amax = amean = 0.0
    perc = _percentiles(valid_values)

    per_voxel_vol = _partial_voxel_volumes_flat(grid).reshape((nx, ny, nz))
    slice_vol = np.asarray(per_voxel_vol[:, :, z_index], dtype=np.float64)
    full_vol = float(grid.voxel_volume_m3) if dx > 0.0 else 0.0
    vol_ratio = np.where(full_vol > 0.0, slice_vol / full_vol, 0.0)
    if field_type == "energy_j":
        represented = float(np.sum(slice_2d * vol_ratio))
    else:
        represented = float(np.sum(slice_2d * slice_vol))

    holes_proj = _project_holes_plan(
        holes_xy=source_holes_xy,
        x_min=bounds.x_min,
        y_min=bounds.y_min,
        dx=dx,
        slice_2d=slice_2d,
    )

    values_f32 = slice_2d.astype(np.float32, copy=False)
    return PlanSlice(
        elevation_m=float(actual_elev),
        unit=energy_unit,
        field_type=field_type,
        grid_shape=(nx, ny),
        values=tuple(float(v) for v in values_f32.ravel()),
        x_coordinates_m=tuple(
            float(v) for v in _voxel_centres(bounds.x_min, dx, nx)
        ),
        y_coordinates_m=tuple(
            float(v) for v in _voxel_centres(bounds.y_min, dx, ny)
        ),
        valid_mask=tuple(bool(v) for v in slice_mask.ravel()),
        min=amin,
        max=amax,
        mean=amean,
        percentiles=perc,
        source_holes_projection=holes_proj,
        data_sha256=_sha256_bytes(values_f32),
        max_value=amax,
        mean_value=amean,
        represented_energy_j=represented,
    )


def section_slice(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
    axis: str,
    coordinate_m: float,
    energy_unit: str,
    field_type: str = "energy_j",
    source_holes_xyz: tuple[tuple[str, float, float, float], ...] = (),
    intersection_mask_flat: np.ndarray | None = None,
) -> SectionSlice:
    """Vertical section along ``axis`` ∈ ``{'x', 'y'}`` at ``coordinate_m``.

    The returned 2D array has shape ``(n_along, n_vertical)``:

    * ``axis == "x"`` ⇒ ``(ny, nz)`` — North × Elevation.
    * ``axis == "y"`` ⇒ ``(nx, nz)`` — East × Elevation.

    The same dimensional contract used by :func:`plan_slice` applies to
    ``represented_energy_j`` for the section aggregate.
    """
    if axis not in ("x", "y"):
        raise ValueError("axis must be 'x' or 'y'")
    if field_type not in _FIELD_TYPES:
        raise ValueError(
            f"field_type must be one of {_FIELD_TYPES}, got {field_type!r}"
        )
    bounds = grid.bounds
    flat = np.asarray(energy_total_flat, dtype=np.float64).ravel()
    expected = int(np.prod(grid.shape)) if grid.shape != (0, 0, 0) else 0
    if expected == 0 or bounds is None or flat.size != expected:
        return _empty_section_slice(
            axis=axis,
            coordinate_m=float(coordinate_m),
            unit=energy_unit,
            field_type=field_type,
        )
    field_3d = reshape_to_grid(flat, grid)
    nx, ny, nz = field_3d.shape
    dx = float(grid.voxel_size_m)

    if axis == "x":
        idx = _voxel_index(coordinate_m, bounds.x_min, dx, nx)
        actual_coord = bounds.x_min + (idx + 0.5) * dx
        raw_slice = np.asarray(field_3d[idx, :, :], dtype=np.float64)
        n_along = ny
        if field_type == "energy_density_j_m3":
            slice_2d = raw_slice / dx ** 3 if dx > 0.0 else raw_slice * 0.0
        else:
            slice_2d = raw_slice
        along_centres = _voxel_centres(bounds.y_min, dx, n_along)
    else:
        idx = _voxel_index(coordinate_m, bounds.y_min, dx, ny)
        actual_coord = bounds.y_min + (idx + 0.5) * dx
        raw_slice = np.asarray(field_3d[:, idx, :], dtype=np.float64)
        n_along = nx
        if field_type == "energy_density_j_m3":
            slice_2d = raw_slice / dx ** 3 if dx > 0.0 else raw_slice * 0.0
        else:
            slice_2d = raw_slice
        along_centres = _voxel_centres(bounds.x_min, dx, n_along)

    full_vol = float(grid.voxel_volume_m3) if dx > 0.0 else 0.0
    vertical_centres = _voxel_centres(bounds.z_min, dx, nz)

    in_domain = _intersection_mask_from_grid(grid, intersection_mask_flat)
    in_domain_3d = (
        in_domain.reshape((nx, ny, nz))
        if in_domain.size == expected
        else np.ones((nx, ny, nz), dtype=bool)
    )
    if axis == "x":
        slice_mask = in_domain_3d[idx, :, :]
    else:
        slice_mask = in_domain_3d[:, idx, :]
    valid_values = (
        slice_2d[slice_mask] if slice_mask.any() else slice_2d.ravel()
    )

    if slice_2d.size > 0:
        amin = float(slice_2d.min())
        amax = float(slice_2d.max())
        amean = float(slice_2d.mean())
    else:
        amin = amax = amean = 0.0
    perc = _percentiles(valid_values)

    per_voxel_vol = _partial_voxel_volumes_flat(grid).reshape((nx, ny, nz))
    if axis == "x":
        slice_vol = np.asarray(per_voxel_vol[idx, :, :], dtype=np.float64)
    else:
        slice_vol = np.asarray(per_voxel_vol[:, idx, :], dtype=np.float64)
    vol_ratio = np.where(full_vol > 0.0, slice_vol / full_vol, 0.0)
    if field_type == "energy_j":
        represented = float(np.sum(slice_2d * vol_ratio))
    else:
        represented = float(np.sum(slice_2d * slice_vol))

    holes_proj = _project_holes_section(
        holes_xyz=source_holes_xyz,
        axis=axis,
        x_min=bounds.x_min,
        y_min=bounds.y_min,
        z_min=bounds.z_min,
        dx=dx,
        slice_2d=slice_2d,
    )

    values_f32 = slice_2d.astype(np.float32, copy=False)
    return SectionSlice(
        axis=axis,
        coordinate_m=float(actual_coord),
        unit=energy_unit,
        field_type=field_type,
        grid_shape=(n_along, nz),
        values=tuple(float(v) for v in values_f32.ravel()),
        along_coordinates_m=tuple(float(v) for v in along_centres),
        vertical_coordinates_m=tuple(float(v) for v in vertical_centres),
        valid_mask=tuple(bool(v) for v in slice_mask.ravel()),
        min=amin,
        max=amax,
        mean=amean,
        percentiles=perc,
        source_holes_projection=holes_proj,
        data_sha256=_sha256_bytes(values_f32),
        max_value=amax,
        mean_value=amean,
        represented_energy_j=represented,
    )


def profile_slice(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
    start_xyz: tuple[float, float, float],
    end_xyz: tuple[float, float, float],
    n_samples: int = 200,
    energy_unit: str = "J",
    field_type: str = "energy_j",
    source_holes_xyz: tuple[tuple[str, float, float, float], ...] = (),
) -> dict[str, Any]:
    """Linear profile between ``start_xyz`` and ``end_xyz``.

    The profile is a deterministic nearest-centre sampling along the
    straight segment joining the two endpoints (NOT a projection of
    source holes — only the geometry). Returns a JSON-serialisable dict
    with cumulative distance, sampled value (J/voxel or J/m³, matching
    ``field_type``), coordinates and summary statistics. The source
    holes (when supplied) are reported as a per-hole list with the
    value at the hole's voxel centre, useful for QC overlays.
    """
    if field_type not in _FIELD_TYPES:
        raise ValueError(
            f"field_type must be one of {_FIELD_TYPES}, got {field_type!r}"
        )
    if int(n_samples) <= 1:
        n_samples = 2
    bounds = grid.bounds
    flat = np.asarray(energy_total_flat, dtype=np.float64).ravel()
    expected = int(np.prod(grid.shape)) if grid.shape != (0, 0, 0) else 0
    if expected == 0 or bounds is None or flat.size != expected:
        return {
            "unit": energy_unit,
            "field_type": field_type,
            "n_samples": 0,
            "distances_m": (),
            "x_m": (),
            "y_m": (),
            "z_m": (),
            "values": (),
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "data_sha256": _sha256_bytes(np.zeros(0, dtype=np.float32)),
            "source_holes_projection": (),
        }

    field_3d = reshape_to_grid(flat, grid)
    nx, ny, nz = field_3d.shape
    dx = float(grid.voxel_size_m)
    raw_slice = np.asarray(field_3d, dtype=np.float64)
    if field_type == "energy_density_j_m3" and dx > 0.0:
        field_values = raw_slice / dx ** 3
    else:
        field_values = raw_slice

    sx, sy, sz = float(start_xyz[0]), float(start_xyz[1]), float(start_xyz[2])
    ex, ey, ez = float(end_xyz[0]), float(end_xyz[1]), float(end_xyz[2])
    t = np.linspace(0.0, 1.0, int(n_samples), dtype=np.float64)
    xs = sx + (ex - sx) * t
    ys = sy + (ey - sy) * t
    zs = sz + (ez - sz) * t
    diffs = np.diff(np.stack([xs, ys, zs], axis=1), axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    distances = np.concatenate(([0.0], np.cumsum(seg_lengths)))

    fx = (xs - bounds.x_min) / dx
    fy = (ys - bounds.y_min) / dx
    fz = (zs - bounds.z_min) / dx
    ix = np.clip(np.floor(fx).astype(np.int64), 0, nx - 1)
    iy = np.clip(np.floor(fy).astype(np.int64), 0, ny - 1)
    iz = np.clip(np.floor(fz).astype(np.int64), 0, nz - 1)
    in_x = (fx >= 0.0) & (fx <= nx)
    in_y = (fy >= 0.0) & (fy <= ny)
    in_z = (fz >= 0.0) & (fz <= nz)
    in_grid = in_x & in_y & in_z

    values = np.zeros(int(n_samples), dtype=np.float64)
    if in_grid.any():
        values[in_grid] = field_values[ix[in_grid], iy[in_grid], iz[in_grid]]

    proj: list[dict[str, Any]] = []
    if source_holes_xyz:
        for entry in source_holes_xyz:
            hole_id = entry[0]
            hx = float(entry[1])
            hy = float(entry[2])
            hz = float(entry[3])
            h_ix = _voxel_index(hx, bounds.x_min, dx, nx)
            h_iy = _voxel_index(hy, bounds.y_min, dx, ny)
            h_iz = _voxel_index(hz, bounds.z_min, dx, nz)
            proj.append({
                "hole_id": str(hole_id),
                "x_m": hx,
                "y_m": hy,
                "z_m": hz,
                "value_at_voxel": float(field_values[h_ix, h_iy, h_iz]),
            })

    valid = values[in_grid] if in_grid.any() else values
    if valid.size:
        amin = float(valid.min())
        amax = float(valid.max())
        amean = float(valid.mean())
    else:
        amin = amax = amean = 0.0

    values_f32 = values.astype(np.float32, copy=False)
    return {
        "unit": energy_unit,
        "field_type": field_type,
        "n_samples": int(n_samples),
        "distances_m": tuple(float(v) for v in distances),
        "x_m": tuple(float(v) for v in xs),
        "y_m": tuple(float(v) for v in ys),
        "z_m": tuple(float(v) for v in zs),
        "values": tuple(float(v) for v in values_f32),
        "min": amin,
        "max": amax,
        "mean": amean,
        "data_sha256": _sha256_bytes(values_f32),
        "source_holes_projection": tuple(proj),
    }


# ---------------------------------------------------------------------------
# Batch entry points
# ---------------------------------------------------------------------------


def compute_slices(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
    energy_unit: str,
    plan_elevations: Iterable[float] = (),
    section_coords: Iterable[tuple[str, float]] = (),
    field_type: str = "energy_j",
    source_holes_xy: tuple[tuple[str, float, float], ...] = (),
    source_holes_xyz: tuple[tuple[str, float, float, float], ...] = (),
    intersection_mask_flat: np.ndarray | None = None,
) -> tuple[tuple[PlanSlice, ...], tuple[SectionSlice, ...]]:
    """Build the plan + section slices requested by the operator.

    The optional ``source_holes_*`` and ``intersection_mask_flat``
    arguments are forwarded to every cut; this keeps the projection and
    the in-domain mask consistent across the full slice catalogue.
    """
    plans = tuple(
        plan_slice(
            energy_total_flat=energy_total_flat,
            grid=grid,
            elevation_m=elev,
            energy_unit=energy_unit,
            field_type=field_type,
            source_holes_xy=source_holes_xy,
            intersection_mask_flat=intersection_mask_flat,
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
            field_type=field_type,
            source_holes_xyz=source_holes_xyz,
            intersection_mask_flat=intersection_mask_flat,
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
    field_type: str = "energy_j",
    source_holes_xy: tuple[tuple[str, float, float], ...] = (),
    source_holes_xyz: tuple[tuple[str, float, float, float], ...] = (),
    intersection_mask_flat: np.ndarray | None = None,
) -> SimulationResult:
    """Return a new :class:`SimulationResult` with plan / section slices attached.

    The energy unit is taken from the result's grid metadata so the
    caller cannot mix absolute and relative scales. The keyword-only
    ``field_type``, hole projections and intersection mask keep the
    Brecha 4 + Brecha 6 invariants visible in the call site.
    """
    from dataclasses import replace
    grid = VoxelGridSpecification(
        voxel_size_m=result.grid_metadata.voxel_size_m,
        bounds=result.grid_metadata.bounds,
    )
    energy_unit = result.grid_metadata.energy_unit or "J"
    plans, sections = compute_slices(
        energy_total_flat=energy_total_flat,
        grid=grid,
        energy_unit=energy_unit,
        plan_elevations=plan_elevations,
        section_coords=section_coords,
        field_type=field_type,
        source_holes_xy=source_holes_xy,
        source_holes_xyz=source_holes_xyz,
        intersection_mask_flat=intersection_mask_flat,
    )
    return replace(result, plan_slices=plans, section_slices=sections)
