"""Horizontal design-to-as-built deviation at matching elevations."""

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

import numpy as np

from core.config import HORIZONTAL_DEVIATION, HorizontalDeviationDefaults


@dataclass(frozen=True)
class HorizontalFaceGeometry:
    bench_number: int
    crest_distance: float
    crest_elevation: float
    toe_distance: float
    toe_elevation: float
    bench_height: float
    is_ramp: bool = False


@dataclass(frozen=True)
class HorizontalProfileIntersection:
    distance_m: float | None
    status: str
    candidate_distances_m: tuple[float, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HorizontalDeviationMeasurement:
    elevation_m: float | None
    design_distance_m: float | None
    topo_distance_m: float | None
    deviation_m: float | None
    bench_number: int | None
    status: str
    category: str
    source: str
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HorizontalDeviationPoint:
    distance_m: float | None
    elevation_m: float | None
    deviation_m: float | None
    category: str
    bench_number: int | None
    status: str
    source: str
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HorizontalDeviationSample:
    bench_number: int
    toe_elevation_m: float | None
    height_above_toe_m: float | None
    elevation_m: float | None
    design_distance_m: float | None
    topo_distance_m: float | None
    deviation_m: float | None
    category: str
    status: str
    source: str
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HorizontalDeviationResult:
    points: tuple[HorizontalDeviationPoint, ...]
    samples: tuple[HorizontalDeviationSample, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(
        self,
        defaults: HorizontalDeviationDefaults = HORIZONTAL_DEVIATION,
    ) -> dict[str, Any]:
        measured = [point for point in self.points if point.deviation_m is not None]
        within = sum(
            abs(point.deviation_m) <= defaults.within_tolerance_m
            for point in measured
        )
        return {
            "unit": "m",
            "method": "horizontal_at_equal_elevation",
            "direction": "positive_overbreak_negative_underbreak",
            "thresholds": {
                "within": defaults.within_tolerance_m,
                "moderate": defaults.moderate_tolerance_m,
                "severe": defaults.severe_tolerance_m,
            },
            "points": [
                {
                    "distance": point.distance_m,
                    "elevation": point.elevation_m,
                    "deviation": point.deviation_m,
                    "value": point.deviation_m,
                    "unit": "m",
                    "category": point.category,
                    "design_bench_num": point.bench_number,
                    "status": point.status,
                    "source": point.source,
                    "assumptions": list(point.assumptions),
                    "warnings": list(point.warnings),
                }
                for point in self.points
            ],
            "samples": [
                {
                    "design_bench_num": sample.bench_number,
                    "toe_elevation": sample.toe_elevation_m,
                    "height_above_toe": sample.height_above_toe_m,
                    "elevation": sample.elevation_m,
                    "reference_elevation": sample.elevation_m,
                    "design_distance": sample.design_distance_m,
                    "topo_distance": sample.topo_distance_m,
                    "deviation": sample.deviation_m,
                    "value": sample.deviation_m,
                    "unit": "m",
                    "category": sample.category,
                    "status": sample.status,
                    "source": sample.source,
                    "assumptions": list(sample.assumptions),
                    "warnings": list(sample.warnings),
                }
                for sample in self.samples
            ],
            "summary": {
                "measured": len(measured),
                "total": len(self.points),
                "within_percent": (
                    round(100.0 * within / len(measured), 2) if measured else None
                ),
                "max_abs_deviation": (
                    max(abs(point.deviation_m) for point in measured)
                    if measured else None
                ),
            },
            "warnings": list(self.warnings),
        }


def _as_arrays(distances: Sequence[float], elevations: Sequence[float]):
    x = np.asarray(distances, dtype=float).reshape(-1)
    z = np.asarray(elevations, dtype=float).reshape(-1)
    if x.size != z.size:
        raise ValueError("Profile distances and elevations must have equal length")
    return x, z


def _face_geometry(face: HorizontalFaceGeometry | Any) -> HorizontalFaceGeometry:
    if isinstance(face, HorizontalFaceGeometry):
        return face
    if isinstance(face, Mapping):
        read = face.__getitem__
        optional = face.get
    else:
        read = lambda key: getattr(face, key)
        optional = lambda key, default=None: getattr(face, key, default)
    return HorizontalFaceGeometry(
        bench_number=int(read("bench_number")),
        crest_distance=float(read("crest_distance")),
        crest_elevation=float(read("crest_elevation")),
        toe_distance=float(read("toe_distance")),
        toe_elevation=float(read("toe_elevation")),
        bench_height=float(optional("bench_height", 0.0)),
        is_ramp=bool(optional("is_ramp", False)),
    )


def profile_intersections_at_elevation(
    distances: Sequence[float],
    elevations: Sequence[float],
    elevation_m: float,
    *,
    min_distance: float | None = None,
    max_distance: float | None = None,
    defaults: HorizontalDeviationDefaults = HORIZONTAL_DEVIATION,
) -> HorizontalProfileIntersection:
    """Find unique piecewise-linear profile crossings at one elevation.

    Optional distance bounds restrict ownership to a detected design face.
    The function never extends a profile beyond its measured endpoints.
    """
    x, z = _as_arrays(distances, elevations)
    level = float(elevation_m)
    eps = float(defaults.intersection_epsilon_m)
    if not isfinite(level):
        return HorizontalProfileIntersection(None, "missing", warnings=("invalid_elevation",))
    if x.size == 0:
        return HorizontalProfileIntersection(None, "missing", warnings=("empty_profile",))

    lower = min_distance
    upper = max_distance
    if lower is not None and upper is not None and lower > upper:
        lower, upper = upper, lower
    if x.size == 1:
        if (
            isfinite(float(x[0])) and isfinite(float(z[0]))
            and abs(float(z[0]) - level) <= eps
            and (lower is None or x[0] >= lower - eps)
            and (upper is None or x[0] <= upper + eps)
        ):
            value = float(x[0])
            return HorizontalProfileIntersection(value, "measured", (value,))
        return HorizontalProfileIntersection(None, "missing")

    x0, x1 = x[:-1], x[1:]
    z0, z1 = z[:-1], z[1:]
    finite = np.isfinite(x0) & np.isfinite(x1) & np.isfinite(z0) & np.isfinite(z1)
    dz = z1 - z0
    flat = finite & (np.abs(dz) <= eps) & (np.abs(z0 - level) <= eps)
    horizontal_interval = False
    candidates: list[float] = []

    if np.any(flat):
        flat_low = np.minimum(x0[flat], x1[flat])
        flat_high = np.maximum(x0[flat], x1[flat])
        if lower is not None:
            flat_low = np.maximum(flat_low, lower - eps)
        if upper is not None:
            flat_high = np.minimum(flat_high, upper + eps)
        keep = flat_high >= flat_low - eps
        if np.any(keep):
            horizontal_interval = bool(np.any(flat_high[keep] - flat_low[keep] > eps))
            candidates.extend(float(v) for v in flat_low[keep] if isfinite(float(v)))
            candidates.extend(float(v) for v in flat_high[keep] if isfinite(float(v)))

    nonflat = finite & (np.abs(dz) > eps)
    if np.any(nonflat):
        t = (level - z0[nonflat]) / dz[nonflat]
        t_eps = eps / np.maximum(np.abs(dz[nonflat]), eps)
        valid = (t >= -t_eps) & (t <= 1.0 + t_eps)
        clamped_t = np.clip(t[valid], 0.0, 1.0)
        hit_x = x0[nonflat][valid] + clamped_t * (x1[nonflat][valid] - x0[nonflat][valid])
        if lower is not None:
            keep = hit_x >= lower - eps
            hit_x = hit_x[keep]
        if upper is not None:
            keep = hit_x <= upper + eps
            hit_x = hit_x[keep]
        candidates.extend(float(v) for v in hit_x if isfinite(float(v)))

    unique: list[float] = []
    for candidate in sorted(candidates):
        if not unique or abs(candidate - unique[-1]) > eps:
            unique.append(candidate)
    if horizontal_interval:
        return HorizontalProfileIntersection(
            None, "horizontal_segment", tuple(unique), ("profile_is_horizontal_at_elevation",)
        )
    if not unique:
        return HorizontalProfileIntersection(None, "missing")
    if len(unique) > 1:
        return HorizontalProfileIntersection(
            None, "ambiguous", tuple(unique), ("multiple_profile_crossings",)
        )
    return HorizontalProfileIntersection(unique[0], "measured", tuple(unique))


def classify_horizontal_deviation(
    deviation_m: float,
    defaults: HorizontalDeviationDefaults = HORIZONTAL_DEVIATION,
) -> str:
    value = float(deviation_m)
    if not isfinite(value):
        return "unmeasured"
    magnitude = abs(value)
    if magnitude <= defaults.within_tolerance_m:
        return "within_tolerance"
    if magnitude <= defaults.moderate_tolerance_m:
        return "overbreak_minor" if value > 0 else "underbreak_minor"
    if magnitude <= defaults.severe_tolerance_m:
        return "overbreak_moderate" if value > 0 else "underbreak_moderate"
    return "overbreak_severe" if value > 0 else "underbreak_severe"


def measure_horizontal_deviation_at_elevation(
    design_distances: Sequence[float],
    design_elevations: Sequence[float],
    elevation_m: float,
    topo_distance_m: float,
    face: HorizontalFaceGeometry | Any,
    defaults: HorizontalDeviationDefaults = HORIZONTAL_DEVIATION,
    source: str = "section_profile",
) -> HorizontalDeviationMeasurement:
    """Compare topo and design horizontal positions along one detected face."""
    geometry = _face_geometry(face)
    assumptions = (
        "piecewise_linear_profile_intersections",
        "ownership_from_detected_design_face",
        "no_topo_bench_pairing",
        "sign_from_design_crest_to_toe_orientation",
    )
    z = float(elevation_m)
    topo_d = float(topo_distance_m)
    warnings: list[str] = []
    safe_z = z if isfinite(z) else None
    safe_topo_d = topo_d if isfinite(topo_d) else None
    face_geometry_values = (
        geometry.crest_distance,
        geometry.crest_elevation,
        geometry.toe_distance,
        geometry.toe_elevation,
    )
    face_min_z = min(geometry.crest_elevation, geometry.toe_elevation)
    face_max_z = max(geometry.crest_elevation, geometry.toe_elevation)
    if not all(isfinite(value) for value in face_geometry_values):
        warnings.append("invalid_design_face_geometry")
        status = "missing"
        intersection = HorizontalProfileIntersection(None, status, warnings=tuple(warnings))
    elif not isfinite(z) or z < face_min_z - defaults.intersection_epsilon_m or z > face_max_z + defaults.intersection_epsilon_m:
        warnings.append("elevation_outside_design_face")
        status = "missing"
        intersection = HorizontalProfileIntersection(None, status, warnings=tuple(warnings))
    elif abs(geometry.crest_distance - geometry.toe_distance) <= defaults.intersection_epsilon_m:
        warnings.append("design_face_has_no_horizontal_direction")
        status = "missing"
        intersection = HorizontalProfileIntersection(None, status, warnings=tuple(warnings))
    else:
        intersection = profile_intersections_at_elevation(
            design_distances,
            design_elevations,
            z,
            min_distance=min(geometry.crest_distance, geometry.toe_distance),
            max_distance=max(geometry.crest_distance, geometry.toe_distance),
            defaults=defaults,
        )
        status = intersection.status
        warnings.extend(intersection.warnings)

    if status != "measured" or intersection.distance_m is None or not isfinite(topo_d):
        if not isfinite(topo_d):
            warnings.append("invalid_topo_distance")
        return HorizontalDeviationMeasurement(
            elevation_m=safe_z,
            design_distance_m=None,
            topo_distance_m=safe_topo_d,
            deviation_m=None,
            bench_number=geometry.bench_number,
            status=status if isfinite(topo_d) else "missing",
            category="unmeasured",
            source=source,
            assumptions=assumptions,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    direction = 1.0 if geometry.crest_distance > geometry.toe_distance else -1.0
    deviation = (topo_d - intersection.distance_m) * direction
    return HorizontalDeviationMeasurement(
        elevation_m=safe_z,
        design_distance_m=float(intersection.distance_m),
        topo_distance_m=safe_topo_d,
        deviation_m=float(deviation),
        bench_number=geometry.bench_number,
        status="measured",
        category=classify_horizontal_deviation(deviation, defaults),
        source=source,
        assumptions=assumptions,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _unassessed_point(
    distance: float | None,
    elevation: float | None,
    warning: str,
    source: str,
) -> HorizontalDeviationPoint:
    return HorizontalDeviationPoint(
        distance_m=distance,
        elevation_m=elevation,
        deviation_m=None,
        category="unmeasured",
        bench_number=None,
        status="ambiguous" if warning.startswith("ambiguous") else "missing",
        source=source,
        assumptions=("design_face_ownership_required", "no_topo_bench_pairing"),
        warnings=(warning,),
    )


def compute_horizontal_deviation(
    design_profile: tuple[Sequence[float], Sequence[float]] | None,
    topo_profile: tuple[Sequence[float], Sequence[float]] | None,
    design_benches: Sequence[HorizontalFaceGeometry | Any],
    defaults: HorizontalDeviationDefaults = HORIZONTAL_DEVIATION,
    source: str = "section_profile",
) -> HorizontalDeviationResult:
    """Measure horizontal deviations at topo vertices and design-face heights.

    Ownership comes only from detected design faces. Topo geometry is used to
    sample the as-built trace and to find the reference-height annotations.
    """
    warnings: list[str] = []
    faces = tuple(_face_geometry(face) for face in design_benches)
    if design_profile is None or topo_profile is None:
        return HorizontalDeviationResult((), (), ("design_or_topo_profile_unavailable",))
    design_x, design_z = _as_arrays(*design_profile)
    topo_x, topo_z = _as_arrays(*topo_profile)
    if not faces:
        warnings.append("no_design_faces_available")
    points: list[HorizontalDeviationPoint] = []

    for distance, elevation in zip(topo_x, topo_z):
        d = float(distance)
        z = float(elevation)
        if not isfinite(d) or not isfinite(z):
            points.append(_unassessed_point(
                d if isfinite(d) else None,
                z if isfinite(z) else None,
                "invalid_topo_profile_point",
                source,
            ))
            continue
        face_candidates = [
            face for face in faces
            if min(face.crest_elevation, face.toe_elevation) - defaults.intersection_epsilon_m
            <= z
            <= max(face.crest_elevation, face.toe_elevation) + defaults.intersection_epsilon_m
        ]
        if len(face_candidates) == 0:
            points.append(_unassessed_point(d, z, "no_design_face_at_elevation", source))
            continue
        if len(face_candidates) > 1:
            points.append(_unassessed_point(
                d, z, "ambiguous_design_face_ownership", source
            ))
            continue
        measurement = measure_horizontal_deviation_at_elevation(
            design_x, design_z, z, d, face_candidates[0], defaults, source
        )
        points.append(HorizontalDeviationPoint(
            distance_m=d,
            elevation_m=z,
            deviation_m=measurement.deviation_m,
            category=measurement.category,
            bench_number=measurement.bench_number,
            status=measurement.status,
            source=measurement.source,
            assumptions=measurement.assumptions,
            warnings=measurement.warnings,
        ))

    samples: list[HorizontalDeviationSample] = []
    topo_query_warnings: set[str] = set()
    for face in faces:
        z_span = abs(face.crest_elevation - face.toe_elevation)
        direction_z = 1.0 if face.crest_elevation >= face.toe_elevation else -1.0
        for fraction in defaults.reference_height_fractions:
            fraction_value = float(fraction)
            finite_height = isfinite(z_span) and isfinite(fraction_value)
            height = z_span * fraction_value if finite_height else None
            finite_toe = isfinite(float(face.toe_elevation))
            level = (
                float(face.toe_elevation) + direction_z * height
                if finite_height and finite_toe and height is not None else None
            )
            sample_warnings: list[str] = []
            design_hit = HorizontalProfileIntersection(None, "missing")
            topo_hit = HorizontalProfileIntersection(None, "missing")
            status = "missing"
            measurement: HorizontalDeviationMeasurement | None = None
            face_values_valid = all(isfinite(value) for value in (
                face.crest_distance,
                face.crest_elevation,
                face.toe_distance,
                face.toe_elevation,
            ))
            if not face_values_valid or not finite_height or not finite_toe:
                sample_warnings.append("invalid_design_face_geometry")
                status = "invalid_design_height"
            elif z_span <= 0:
                sample_warnings.append("invalid_detected_design_height")
                status = "invalid_design_height"
            elif height is None or height < 0 or height > z_span + defaults.intersection_epsilon_m:
                sample_warnings.append("reference_height_outside_design_face")
                status = "missing"
            else:
                design_hit = profile_intersections_at_elevation(
                    design_x, design_z, level,
                    min_distance=min(face.crest_distance, face.toe_distance),
                    max_distance=max(face.crest_distance, face.toe_distance),
                    defaults=defaults,
                )
                if design_hit.status != "measured" or design_hit.distance_m is None:
                    status = design_hit.status
                    sample_warnings.extend(design_hit.warnings)
                else:
                    topo_hit = profile_intersections_at_elevation(
                        topo_x, topo_z, level, defaults=defaults
                    )
                    if topo_hit.status != "measured" or topo_hit.distance_m is None:
                        status = topo_hit.status
                        sample_warnings.extend(topo_hit.warnings)
                        topo_query_warnings.update(topo_hit.warnings)
                    else:
                        measurement = measure_horizontal_deviation_at_elevation(
                            design_x,
                            design_z,
                            level,
                            topo_hit.distance_m,
                            face,
                            defaults,
                            source,
                        )
                        status = measurement.status
                        sample_warnings.extend(measurement.warnings)
            samples.append(HorizontalDeviationSample(
                bench_number=face.bench_number,
                toe_elevation_m=(
                    float(face.toe_elevation) if isfinite(float(face.toe_elevation)) else None
                ),
                height_above_toe_m=height,
                elevation_m=level,
                design_distance_m=design_hit.distance_m,
                topo_distance_m=topo_hit.distance_m,
                deviation_m=measurement.deviation_m if measurement else None,
                category=measurement.category if measurement else "unmeasured",
                status=status,
                source=source,
                assumptions=(
                    "height_reference_from_design_toe",
                    "face_height_from_design_crest_to_toe",
                    "no_topo_bench_pairing",
                    "topo_intersection_must_be_unique",
                    "no_extrapolation",
                ),
                warnings=tuple(dict.fromkeys(sample_warnings)),
            ))

    if topo_query_warnings:
        warnings.extend(sorted(topo_query_warnings))
    return HorizontalDeviationResult(tuple(points), tuple(samples), tuple(dict.fromkeys(warnings)))
