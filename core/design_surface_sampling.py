"""Conservative point sampling of a triangulated design surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np


SampleStatus = Literal["sampled", "outside", "ambiguous", "invalid"]


@dataclass(frozen=True, slots=True)
class DesignSurfaceSample:
    """Immutable result for one XY query; elevation is in mesh units (m by contract)."""

    status: SampleStatus
    elevation_m: Optional[float]
    method: str
    reason: str


@dataclass(slots=True)
class _Node:
    bounds: tuple[float, float, float, float]
    start: int
    end: int
    left: Optional["_Node"] = None
    right: Optional["_Node"] = None


class _TriangleAABBIndex:
    """Small local 2D AABB tree over projected triangle bounds."""

    def __init__(self, vertices: np.ndarray, faces: np.ndarray, leaf_size: int = 32):
        self.vertices = vertices
        self.faces = faces
        self.triangle_min = np.minimum.reduce(
            [vertices[faces[:, corner], :2] for corner in range(3)]
        )
        self.triangle_max = np.maximum.reduce(
            [vertices[faces[:, corner], :2] for corner in range(3)]
        )
        centroids = (self.triangle_min + self.triangle_max) * 0.5
        self.order = np.arange(len(faces), dtype=np.int64)
        self.leaf_size = leaf_size
        self.root = self._build(0, len(self.order), centroids)

    def _build(self, start: int, end: int, centroids: np.ndarray) -> _Node:
        face_ids = self.order[start:end]
        bounds = (
            float(np.min(self.triangle_min[face_ids, 0])),
            float(np.min(self.triangle_min[face_ids, 1])),
            float(np.max(self.triangle_max[face_ids, 0])),
            float(np.max(self.triangle_max[face_ids, 1])),
        )
        node = _Node(bounds, start, end)
        if end - start <= self.leaf_size:
            return node

        center_bounds = np.ptp(centroids[face_ids], axis=0)
        axis = int(np.argmax(center_bounds))
        if center_bounds[axis] <= 0:
            return node
        middle = start + (end - start) // 2
        local_order = self.order[start:end]
        permutation = np.argpartition(centroids[local_order, axis], middle - start)
        self.order[start:end] = local_order[permutation]
        node.left = self._build(start, middle, centroids)
        node.right = self._build(middle, end, centroids)
        return node

    def query(self, point: np.ndarray, tolerance: float) -> list[int]:
        result: list[int] = []
        pending = [self.root]
        x, y = float(point[0]), float(point[1])
        while pending:
            node = pending.pop()
            xmin, ymin, xmax, ymax = node.bounds
            if (
                x < xmin - tolerance or x > xmax + tolerance
                or y < ymin - tolerance or y > ymax + tolerance
            ):
                continue
            if node.left is None and node.right is None:
                ids = self.order[node.start:node.end]
                bbox = self.triangle_min[ids]
                upper = self.triangle_max[ids]
                mask = (
                    (bbox[:, 0] <= x + tolerance)
                    & (upper[:, 0] >= x - tolerance)
                    & (bbox[:, 1] <= y + tolerance)
                    & (upper[:, 1] >= y - tolerance)
                )
                result.extend(int(index) for index in ids[mask])
            else:
                if node.left is not None:
                    pending.append(node.left)
                if node.right is not None:
                    pending.append(node.right)
        return result


def _point_segment_distance(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    segment = end - start
    length_squared = float(np.dot(segment, segment))
    if length_squared == 0.0:
        return float(np.linalg.norm(point - start))
    fraction = float(np.clip(np.dot(point - start, segment) / length_squared, 0.0, 1.0))
    return float(np.linalg.norm(point - (start + fraction * segment)))


def _triangle_hit(
    triangle: np.ndarray,
    point: np.ndarray,
    xy_tolerance: float,
) -> tuple[Optional[float], bool]:
    """Return (interpolated Z, vertical-face-hit) for the projected triangle."""
    projected = triangle[:, :2]
    edge_ab = projected[1] - projected[0]
    edge_ac = projected[2] - projected[0]
    area2 = float(edge_ab[0] * edge_ac[1] - edge_ab[1] * edge_ac[0])
    edge_lengths = (
        float(np.linalg.norm(projected[1] - projected[0])),
        float(np.linalg.norm(projected[2] - projected[1])),
        float(np.linalg.norm(projected[0] - projected[2])),
    )
    max_edge = max(edge_lengths)
    area3 = float(np.linalg.norm(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])))
    if max_edge == 0.0 or abs(area2) <= max_edge * xy_tolerance:
        if area3 <= max_edge * max_edge * 1.0e-14:
            return None, False
        if any(
            _point_segment_distance(point, projected[index], projected[(index + 1) % 3])
            <= xy_tolerance
            for index in range(3)
        ):
            return None, True
        return None, False

    relative = point - projected[0]
    weight_b = float((relative[0] * edge_ac[1] - relative[1] * edge_ac[0]) / area2)
    weight_c = float((edge_ab[0] * relative[1] - edge_ab[1] * relative[0]) / area2)
    weight_a = 1.0 - weight_b - weight_c
    altitudes = (
        abs(area2) / edge_lengths[1],
        abs(area2) / edge_lengths[2],
        abs(area2) / edge_lengths[0],
    )
    weights = (weight_a, weight_b, weight_c)
    if any(altitude <= xy_tolerance for altitude in altitudes):
        if min(_point_segment_distance(point, projected[i], projected[(i + 1) % 3]) for i in range(3)) <= xy_tolerance:
            return None, True
        return None, False
    else:
        numerical_epsilon = 32.0 * np.finfo(float).eps
        if any(weight < -numerical_epsilon for weight in weights):
            return None, False
        weights = tuple(max(weight, 0.0) for weight in weights)
        weight_sum = sum(weights)
        if weight_sum <= 0.0:
            return None, False
        weights = tuple(weight / weight_sum for weight in weights)

    elevation = float(np.dot(np.asarray(weights), triangle[:, 2]))
    return elevation, False


def _coerce_queries(xy) -> tuple[np.ndarray, np.ndarray]:
    try:
        values = np.asarray(xy, dtype=object)
    except (TypeError, ValueError):
        raise ValueError("xy must be one XY pair or an N×2 collection") from None
    if values.ndim == 1 and values.shape == (2,):
        values = values.reshape(1, 2)
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("xy must be one XY pair or an N×2 collection")
    points = np.full((len(values), 2), np.nan, dtype=float)
    valid = np.ones(len(values), dtype=bool)
    for index, pair in enumerate(values):
        try:
            points[index] = (float(pair[0]), float(pair[1]))
        except (TypeError, ValueError, OverflowError):
            valid[index] = False
        if valid[index] and not np.all(np.isfinite(points[index])):
            valid[index] = False
    return points, valid


def sample_design_surface(
    mesh,
    xy,
    *,
    xy_tolerance_m: float = 1.0e-8,
    elevation_tolerance_m: float = 1.0e-8,
) -> tuple[DesignSurfaceSample, ...]:
    """Sample a design mesh at XY points without selecting between elevations.

    Mesh vertices and query XY coordinates must already share a projected,
    metre-based coordinate frame. A unique vertical intersection is returned;
    distinct elevations, vertical projected faces, holes and exterior points
    never receive an extrapolated value. The result is design-surface Z, not a
    measured drill-collar elevation or a derived bench height.
    """
    if (
        not np.isfinite(xy_tolerance_m) or xy_tolerance_m <= 0
        or not np.isfinite(elevation_tolerance_m) or elevation_tolerance_m < 0
    ):
        raise ValueError("tolerances must be finite; XY > 0 and elevation >= 0")

    points, valid_points = _coerce_queries(xy)
    invalid_mesh_reason = None
    vertices = np.asarray(getattr(mesh, "vertices", ()), dtype=float)
    faces = np.asarray(getattr(mesh, "faces", ()), dtype=np.int64)
    if (
        vertices.ndim != 2 or vertices.shape[1] != 3
        or faces.ndim != 2 or faces.shape[1] != 3
        or len(vertices) == 0 or len(faces) == 0
        or not np.all(np.isfinite(vertices))
        or np.any(faces < 0) or np.any(faces >= len(vertices))
    ):
        invalid_mesh_reason = "invalid_or_empty_mesh"

    if invalid_mesh_reason is not None:
        return tuple(
            DesignSurfaceSample("invalid", None, "vertical_triangle_intersection", invalid_mesh_reason)
            if valid else DesignSurfaceSample("invalid", None, "vertical_triangle_intersection", "non_finite_or_unparseable_xy")
            for valid in valid_points
        )

    index = _TriangleAABBIndex(vertices, faces)
    results = []
    for point, valid in zip(points, valid_points):
        if not valid:
            results.append(DesignSurfaceSample(
                "invalid", None, "vertical_triangle_intersection", "non_finite_or_unparseable_xy"
            ))
            continue
        candidate_ids = index.query(point, xy_tolerance_m)
        elevations: list[float] = []
        vertical_face_hit = False
        for face_id in candidate_ids:
            triangle = vertices[faces[face_id]]
            elevation, vertical_hit = _triangle_hit(triangle, point, xy_tolerance_m)
            vertical_face_hit = vertical_face_hit or vertical_hit
            if elevation is not None:
                elevations.append(elevation)

        if vertical_face_hit:
            results.append(DesignSurfaceSample(
                "ambiguous", None, "vertical_triangle_intersection", "vertical_or_ill_conditioned_face"
            ))
            continue
        if not elevations:
            results.append(DesignSurfaceSample(
                "outside", None, "vertical_triangle_intersection", "outside_footprint_or_mesh_hole"
            ))
            continue
        elevations.sort()
        unique = [elevations[0]]
        for elevation in elevations[1:]:
            if elevation - unique[-1] > elevation_tolerance_m:
                unique.append(elevation)
        if len(unique) != 1:
            results.append(DesignSurfaceSample(
                "ambiguous", None, "vertical_triangle_intersection", "multiple_distinct_surface_elevations"
            ))
            continue
        results.append(DesignSurfaceSample(
            "sampled", float(np.mean(elevations)), "vertical_triangle_intersection", "unique_surface_elevation"
        ))
    return tuple(results)
