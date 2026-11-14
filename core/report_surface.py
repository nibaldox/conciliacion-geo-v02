"""Plan-view topographic surface for the report figures.

Builds a regular elevation grid from the as-built mesh (linear interpolation
inside each triangle, NaN where no triangle covers a node) and derives the
shaded relief drawn under the section lines of the plan figures.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import numpy as np

from core.report_charts import _section_endpoints

Shade = tuple[np.ndarray, tuple[float, float, float, float]]

_MIN_CELL_M = 0.5
_CELL_STEP_M = 0.01
_INSIDE_TOLERANCE = 1e-9
_MIN_PLAN_AREA = 1e-12
_SMALL_BOX_NODES = 8


@dataclass(frozen=True)
class PlanSurface:
    """Regular elevation grid; ``z`` has shape ``(len(y), len(x))`` with NaN off the mesh."""

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    cell_m: float


def _section_mapping(section: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(section, Mapping):
        return section
    if section is None:
        return None
    fields = {}
    for key in ("name", "polyline", "origin", "azimuth", "length"):
        value = getattr(section, key, None)
        if value is not None:
            fields[key] = value
    return fields or None


def _section_points(section: Any) -> Optional[list]:
    mapping = _section_mapping(section)
    if mapping is None:
        return None
    try:
        points = _section_endpoints(dict(mapping))
    except (TypeError, ValueError, IndexError):
        return None
    if not points or not all(math.isfinite(c) for point in points for c in point):
        return None
    return points


def sections_bounds(
    sections, margin_m: float = 30.0,
) -> Optional[tuple[float, float, float, float]]:
    """Bounds ``(xmin, ymin, xmax, ymax)`` of every section line plus ``margin_m``."""
    xs: list[float] = []
    ys: list[float] = []
    for section in sections or ():
        points = _section_points(section)
        if not points:
            continue
        xs.extend(point[0] for point in points)
        ys.extend(point[1] for point in points)
    if not xs:
        return None
    margin = float(margin_m)
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


def _node_count(span: float, cell: float) -> int:
    return int(math.floor(span / cell + 1e-9)) + 1


def _grid_cell(width: float, height: float, max_nodes: int) -> float:
    budget = max(int(max_nodes), 1)
    area = width * height
    perimeter = width + height
    if budget <= 1:
        cell = max(width, height) * 2.0 + 1.0
    elif area > 0:
        inverse = (-perimeter + math.sqrt(perimeter * perimeter + 4.0 * area * (budget - 1))) / (2.0 * area)
        cell = 1.0 / inverse
    elif perimeter > 0:
        cell = perimeter / (budget - 1)
    else:
        cell = _MIN_CELL_M
    cell = max(_MIN_CELL_M, math.ceil(cell / _CELL_STEP_M - 1e-9) * _CELL_STEP_M)
    while _node_count(width, cell) * _node_count(height, cell) > budget:
        cell += _CELL_STEP_M
    return round(cell, 6)


def _rasterise(tri_u, tri_v, tri_z, nx: int, ny: int) -> np.ndarray:
    """Highest linearly interpolated z of the triangles covering each grid node.

    ``tri_u``/``tri_v`` are the triangle corners in grid-index units, shape
    ``(n, 3)``. Triangles with no plan area (vertical faces) are skipped.
    """
    z = np.full(nx * ny, np.nan)
    if len(tri_u) == 0:
        return z.reshape(ny, nx)

    iu0 = np.clip(np.ceil(tri_u.min(axis=1) - _INSIDE_TOLERANCE), 0, nx).astype(np.int64)
    iu1 = np.clip(np.floor(tri_u.max(axis=1) + _INSIDE_TOLERANCE), -1, nx - 1).astype(np.int64)
    iv0 = np.clip(np.ceil(tri_v.min(axis=1) - _INSIDE_TOLERANCE), 0, ny).astype(np.int64)
    iv1 = np.clip(np.floor(tri_v.max(axis=1) + _INSIDE_TOLERANCE), -1, ny - 1).astype(np.int64)
    width = iu1 - iu0 + 1
    height = iv1 - iv0 + 1

    ax, ay = tri_u[:, 0], tri_v[:, 0]
    e1x, e1y = tri_u[:, 1] - ax, tri_v[:, 1] - ay
    e2x, e2y = tri_u[:, 2] - ax, tri_v[:, 2] - ay
    det = e1x * e2y - e2x * e1y
    keep = (width > 0) & (height > 0) & (np.abs(det) > _MIN_PLAN_AREA)
    if not keep.any():
        return z.reshape(ny, nx)

    z0 = tri_z[:, 0]
    dz1 = tri_z[:, 1] - z0
    dz2 = tri_z[:, 2] - z0

    def splat(rows, node_u, node_v):
        pu = node_u - ax[rows]
        pv = node_v - ay[rows]
        w1 = (pu * e2y[rows] - e2x[rows] * pv) / det[rows]
        w2 = (e1x[rows] * pv - pu * e1y[rows]) / det[rows]
        inside = (w1 >= -_INSIDE_TOLERANCE) & (w2 >= -_INSIDE_TOLERANCE) \
            & (w1 + w2 <= 1.0 + _INSIDE_TOLERANCE)
        if not inside.any():
            return
        rows_in = rows[inside]
        values = z0[rows_in] + w1[inside] * dz1[rows_in] + w2[inside] * dz2[rows_in]
        np.fmax.at(z, node_v[inside] * nx + node_u[inside], values)

    small = keep & (width <= _SMALL_BOX_NODES) & (height <= _SMALL_BOX_NODES)
    small_rows = np.flatnonzero(small)
    if small_rows.size:
        key = width[small_rows] * (_SMALL_BOX_NODES + 1) + height[small_rows]
        for value in np.unique(key):
            rows = small_rows[key == value]
            box_w, box_h = divmod(int(value), _SMALL_BOX_NODES + 1)
            for du in range(box_w):
                for dv in range(box_h):
                    splat(rows, iu0[rows] + du, iv0[rows] + dv)

    for row in np.flatnonzero(keep & ~small):
        node_u, node_v = np.meshgrid(
            np.arange(iu0[row], iu1[row] + 1), np.arange(iv0[row], iv1[row] + 1),
        )
        node_u = node_u.ravel()
        splat(np.full(node_u.size, row, dtype=np.int64), node_u, node_v.ravel())

    return z.reshape(ny, nx)


def plan_surface_from_mesh(
    mesh,
    *,
    bounds: Optional[tuple[float, float, float, float]] = None,
    max_nodes: int = 250_000,
) -> Optional[PlanSurface]:
    """Elevation grid of ``mesh`` inside ``bounds`` ``(xmin, ymin, xmax, ymax)``.

    z is interpolated linearly inside each triangle (the highest one where
    several overlap in plan) and left as NaN where no triangle covers the
    node. The cell is the smallest value, never below 0.5 m, that keeps the
    grid within ``max_nodes``. Returns ``None`` when the mesh has no triangle
    covering a node of the window.
    """
    vertices = getattr(mesh, "vertices", None)
    faces = getattr(mesh, "faces", None)
    if vertices is None or faces is None:
        return None
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces)
    if vertices.ndim != 2 or vertices.shape[1] < 3 or faces.ndim != 2 or faces.shape[1] != 3:
        return None
    if len(vertices) == 0 or len(faces) == 0:
        return None

    face_x = vertices[:, 0][faces]
    face_y = vertices[:, 1][faces]
    usable = np.isfinite(face_x).all(axis=1) & np.isfinite(face_y).all(axis=1) \
        & np.isfinite(vertices[:, 2][faces]).all(axis=1)
    if not usable.any():
        return None

    if bounds is None:
        xmin, xmax = float(face_x[usable].min()), float(face_x[usable].max())
        ymin, ymax = float(face_y[usable].min()), float(face_y[usable].max())
    else:
        xmin, ymin, xmax, ymax = (float(value) for value in bounds)
        if not all(math.isfinite(value) for value in (xmin, ymin, xmax, ymax)):
            return None
        if xmax < xmin or ymax < ymin:
            return None
        usable &= (face_x.max(axis=1) >= xmin) & (face_x.min(axis=1) <= xmax) \
            & (face_y.max(axis=1) >= ymin) & (face_y.min(axis=1) <= ymax)
        if not usable.any():
            return None

    cell = _grid_cell(xmax - xmin, ymax - ymin, max_nodes)
    nx = _node_count(xmax - xmin, cell)
    ny = _node_count(ymax - ymin, cell)

    tri_u = (face_x[usable] - xmin) / cell
    tri_v = (face_y[usable] - ymin) / cell
    del face_x, face_y
    tri_z = vertices[:, 2][faces[usable]]
    z = _rasterise(tri_u, tri_v, tri_z, nx, ny)
    if not np.isfinite(z).any():
        return None
    return PlanSurface(
        x=xmin + np.arange(nx) * cell, y=ymin + np.arange(ny) * cell, z=z, cell_m=float(cell),
    )


def _nan_gradient(z: np.ndarray, cell: float, axis: int) -> np.ndarray:
    """Central difference using only finite neighbours; 0 where none is available."""
    step = np.diff(z, axis=axis) / cell
    pad = [(0, 0), (0, 0)]
    pad[axis] = (1, 0)
    backward = np.pad(step, pad, constant_values=np.nan)
    pad[axis] = (0, 1)
    forward = np.pad(step, pad, constant_values=np.nan)
    count = np.isfinite(backward).astype(float) + np.isfinite(forward)
    total = np.nan_to_num(backward, nan=0.0) + np.nan_to_num(forward, nan=0.0)
    return np.divide(total, count, out=np.zeros_like(total), where=count > 0)


def shaded_relief(
    surface: PlanSurface,
    *,
    azimuth_deg: float = 315.0,
    altitude_deg: float = 45.0,
    z_factor: float = 1.6,
) -> Shade:
    """Hillshade in 0..1 (NaN off the surface) and its ``imshow`` extent.

    The light comes from ``azimuth_deg`` (clockwise from North) at
    ``altitude_deg`` above the horizon; ``z_factor`` exaggerates the relief.
    The extent is ``(xmin, xmax, ymin, ymax)`` for ``imshow(origin="lower")``.
    """
    z = np.asarray(surface.z, dtype=float)
    cell = float(surface.cell_m)
    grad_x = _nan_gradient(z, cell, axis=1) * z_factor
    grad_y = _nan_gradient(z, cell, axis=0) * z_factor
    azimuth = math.radians(azimuth_deg)
    altitude = math.radians(altitude_deg)
    light_x = math.sin(azimuth) * math.cos(altitude)
    light_y = math.cos(azimuth) * math.cos(altitude)
    light_z = math.sin(altitude)
    shade = (-grad_x * light_x - grad_y * light_y + light_z) / np.sqrt(grad_x ** 2 + grad_y ** 2 + 1.0)
    shade = np.clip(shade, 0.0, 1.0)
    shade[~np.isfinite(z)] = np.nan

    half = cell / 2.0
    x = np.asarray(surface.x, dtype=float)
    y = np.asarray(surface.y, dtype=float)
    if x.size and y.size:
        extent = (float(x[0]) - half, float(x[-1]) + half, float(y[0]) - half, float(y[-1]) + half)
    else:
        extent = (0.0, 0.0, 0.0, 0.0)
    return shade, extent
