"""Pure segment-to-section geometry for blast-hole traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from core.section_cutter import SectionLine, azimuth_to_direction


@dataclass(frozen=True)
class HoleSectionRelation:
    relation: str
    signed_distance_collar_m: Optional[float]
    signed_distance_toe_m: Optional[float]
    min_distance_to_section_m: Optional[float]
    along_section_collar_m: Optional[float]
    along_section_toe_m: Optional[float]


def _valid_xy(point: Optional[Sequence[float]]) -> Optional[np.ndarray]:
    if point is None:
        return None
    try:
        value = np.asarray(point, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if value.size < 3 or not np.isfinite(value[:3]).all():
        return None
    return value[:2]


def _point_segment_distance(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    delta = end - start
    denom = float(np.dot(delta, delta))
    if denom == 0.0:
        return float(np.linalg.norm(point - start))
    t = float(np.clip(np.dot(point - start, delta) / denom, 0.0, 1.0))
    return float(np.linalg.norm(point - (start + t * delta)))


def _segments_intersect(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray,
                        tolerance: float) -> bool:
    def orient(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> float:
        first, second = q - p, r - p
        return float(first[0] * second[1] - first[1] * second[0])

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    ab_length = float(np.linalg.norm(b - a))
    cd_length = float(np.linalg.norm(d - c))
    epsilon = tolerance * max(1.0, ab_length, cd_length)
    if ((o1 > epsilon and o2 < -epsilon) or (o1 < -epsilon and o2 > epsilon)) and \
       ((o3 > epsilon and o4 < -epsilon) or (o3 < -epsilon and o4 > epsilon)):
        return True

    def on_segment(p: np.ndarray, q: np.ndarray, r: np.ndarray, value: float) -> bool:
        return abs(value) <= epsilon and np.all(r >= np.minimum(p, q) - tolerance) and np.all(r <= np.maximum(p, q) + tolerance)

    return (on_segment(a, b, c, o1) or on_segment(a, b, d, o2) or
            on_segment(c, d, a, o3) or on_segment(c, d, b, o4))


def _segment_distance(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray,
                      tolerance: float) -> float:
    if _segments_intersect(a, b, c, d, tolerance):
        return 0.0
    return min(_point_segment_distance(a, c, d), _point_segment_distance(b, c, d),
               _point_segment_distance(c, a, b), _point_segment_distance(d, a, b))


def classify_hole_segment_to_section(
    collar: Optional[Sequence[float]],
    toe: Optional[Sequence[float]],
    section: SectionLine,
    *,
    corridor_m: float = 10.0,
    numeric_tolerance_m: float = 1e-9,
) -> HoleSectionRelation:
    """Classify a finite 3D hole trace against a finite vertical section plane.

    Section station is measured from ``section.origin`` along its azimuth
    (clockwise from North); bounds match ``cut_mesh_with_section``: asymmetric
    ``[-length_down, length_up]`` when both are supplied, otherwise
    ``[-length/2, length/2]``. Corridor is the XY distance to that finite
    trace. ``exact_intersection`` requires the segment to meet the bounded
    plane; ``near_section`` is a distance-only result and makes no crossing
    claim. Missing/invalid either endpoint returns ``incomplete``.
    """
    corridor = float(corridor_m)
    tol = float(numeric_tolerance_m)
    if not np.isfinite(corridor) or corridor < 0 or not np.isfinite(tol) or tol < 0:
        raise ValueError("corridor_m y numeric_tolerance_m deben ser finitos y no negativos")
    p0, p1 = _valid_xy(collar), _valid_xy(toe)
    if p0 is None or p1 is None:
        return HoleSectionRelation("incomplete", None, None, None, None, None)

    try:
        origin = np.asarray(section.origin, dtype=float).reshape(-1)[:2]
        azimuth = float(section.azimuth)
        length = float(section.length)
        up = float(section.length_up) if section.length_up is not None else None
        down = float(section.length_down) if section.length_down is not None else None
    except (TypeError, ValueError):
        raise ValueError("La sección debe tener origen, azimut y límites válidos") from None
    if origin.size != 2 or not np.isfinite(origin).all():
        raise ValueError("La sección debe tener origen, azimut y límites válidos")
    direction = azimuth_to_direction(azimuth)
    normal = np.array([direction[1], -direction[0]], dtype=float)
    if up is not None and down is not None:
        lower, upper = -down, up
    else:
        half = length / 2.0
        lower, upper = -half, half
    if (not np.isfinite([*direction, lower, upper]).all() or lower > upper
            or (up is not None and up < 0) or (down is not None and down < 0)):
        raise ValueError("La sección debe tener origen, azimut y límites válidos")

    rel0, rel1 = p0 - origin, p1 - origin
    s0, s1 = float(rel0 @ normal), float(rel1 @ normal)
    u0, u1 = float(rel0 @ direction), float(rel1 @ direction)
    crosses_plane = (s0 <= tol and s1 >= -tol) or (s1 <= tol and s0 >= -tol)
    exact = False
    if crosses_plane:
        if abs(s0) <= tol and abs(s1) <= tol:
            exact = max(min(u0, u1), lower) <= min(max(u0, u1), upper) + tol
        else:
            denom = s0 - s1
            t = 0.0 if abs(denom) <= tol else float(np.clip(s0 / denom, 0.0, 1.0))
            station = u0 + t * (u1 - u0)
            exact = lower - tol <= station <= upper + tol

    section_start, section_end = origin + lower * direction, origin + upper * direction
    distance = _segment_distance(p0, p1, section_start, section_end, tol)
    relation = "exact_intersection" if exact else ("near_section" if distance <= corridor + tol else "outside")
    return HoleSectionRelation(relation, s0, s1, distance, u0, u1)
