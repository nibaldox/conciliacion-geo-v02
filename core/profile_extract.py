"""Profile-level parameter extraction.

Owns the public dataclasses (:class:`ReconciledPoint`,
:class:`ReconciledProfile`, :class:`BenchParams`,
:class:`ExtractionResult`) and the orchestrator
:func:`extract_parameters`, which runs the RDP → angle-classification →
merge → bench-extraction → berm-classification → hazard-detection
pipeline on a single 2D profile.

The supporting helpers live in sibling modules:
:mod:`core.profile_simplify`, :mod:`core.bench_classify`,
:mod:`core.bench_hazards`.
"""

import json
import logging
import math
from dataclasses import dataclass, field
from typing import List, Literal, Tuple

import numpy as np
import pandas as pd

try:
    from scipy.signal import savgol_filter as _savgol_filter
except Exception:  # pragma: no cover - scipy is a declared dependency
    _savgol_filter = None

from core.bench_classify import (
    _apply_leading_berm,
    _apply_trailing_berm,
    _compute_berm_widths_from_profile,
)
from core.bench_hazards import (
    _detect_overhangs_and_bridges,
    _detect_toppling_potential,
    _detect_wedge_shape_in_face,
    _evaluate_angle_consistency,
    _evaluate_catch_bench_adequacy,
)
from core.config import DETECTION, TOLERANCES
from core.profile_simplify import (
    _detect_and_project_solid_toe,
    ramer_douglas_peucker,
)

SegmentType = Literal["crest", "berm_top", "berm_bottom", "toe", "face", "ramp"]


@dataclass
class ReconciledPoint:
    """A single point in the idealised reconciled profile.

    Attributes
    ----------
    distance : float
        Horizontal coordinate along the section (meters).
    elevation : float
        Vertical coordinate (meters above datum).
    bench_number : int
        Index of the bench this point belongs to (1-based).
    segment_type : str
        Role of this point in the geometry: ``"crest"`` (upper edge of a
        face), ``"toe"`` (lower edge of a face), ``"berm_top"`` (top of
        a horizontal berm platform), ``"berm_bottom"`` (bottom corner
        of a berm — coincides with the next bench's crest elevation),
        ``"face"`` (intermediate point on a face), or ``"ramp"``
        (point on an oblique ramp transition that replaces a berm).
    source : str
        ``"design"`` or ``"topo"`` — used by the renderer to colour
        design vs as-built traces.
    """
    distance: float
    elevation: float
    bench_number: int
    segment_type: str
    source: str = "topo"


@dataclass
class ReconciledProfile:
    """Rich output of the idealised-profile builder.

    Provides the two flat arrays expected by legacy consumers
    (``distances`` / ``elevations``) plus a structured list of
    :class:`ReconciledPoint` entries that downstream code can use to
    colour, label, or group points by bench / segment type.
    """
    distances: np.ndarray
    elevations: np.ndarray
    points: List[ReconciledPoint] = field(default_factory=list)

    def summary(self, benches=None) -> dict:
        """Return a flat, JSON-safe summary of the reconciled profile.

        Always populates ``n_benches``, ``n_ramps``, ``height_range_m``,
        and ``source`` from ``self.points``. Hazard counters
        (``n_overhangs``, ``n_wedge_risks``, ``n_toppling_risks``,
        ``n_consensus_benches``) and aggregate metrics
        (``total_berm_width_m``, ``avg_face_angle_deg``,
        ``max_overhang_m``) are enriched from the optional ``benches``
        list of :class:`BenchParams` when supplied.

        When ``benches`` is ``None`` (or omitted), the aggregate metrics
        default to safe no-data values: hazard counts to ``0``,
        ``n_consensus_benches`` equals ``n_benches``,
        ``total_berm_width_m`` and ``max_overhang_m`` to ``0.0``, and
        ``avg_face_angle_deg`` to ``None``. This keeps the dict
        JSON-serializable (including strict mode ``json.dumps(...,
        allow_nan=False)``) without leaking numpy scalars or dataclasses.
        """
        n_benches = len({int(p.bench_number) for p in self.points})
        n_ramps = sum(1 for p in self.points if p.segment_type == "ramp")

        elevations_f = [float(p.elevation) for p in self.points]
        if elevations_f:
            height_range = (min(elevations_f), max(elevations_f))
        else:
            height_range = (0, 0)

        source = str(self.points[0].source) if self.points else "topo"

        if benches is None:
            return {
                "n_benches": int(n_benches),
                "n_ramps": int(n_ramps),
                "n_overhangs": 0,
                "n_wedge_risks": 0,
                "n_toppling_risks": 0,
                "n_consensus_benches": int(n_benches),
                "height_range_m": (float(height_range[0]), float(height_range[1])),
                "total_berm_width_m": 0.0,
                "avg_face_angle_deg": None,
                "max_overhang_m": 0.0,
                "source": source,
            }

        benches_list = list(benches)
        n_overhangs = sum(1 for b in benches_list if float(b.overhang_m) > 0.0)
        n_wedge = sum(1 for b in benches_list if bool(b.wedge_risk))
        n_topple = sum(1 for b in benches_list if bool(b.toppling_risk))
        n_consensus = sum(
            1 for b in benches_list
            if int(b.n_detection_methods_agreeing) >= 2
        )
        total_berm = float(sum(float(b.berm_width) for b in benches_list))
        angles = [float(b.face_angle) for b in benches_list]
        avg_angle = float(np.mean(angles)) if angles else math.nan
        max_overhang = float(max(
            (float(b.overhang_m) for b in benches_list), default=0.0
        ))

        return {
            "n_benches": int(n_benches),
            "n_ramps": int(n_ramps),
            "n_overhangs": int(n_overhangs),
            "n_wedge_risks": int(n_wedge),
            "n_toppling_risks": int(n_topple),
            "n_consensus_benches": int(n_consensus),
            "height_range_m": (float(height_range[0]), float(height_range[1])),
            "total_berm_width_m": total_berm,
            "avg_face_angle_deg": avg_angle,
            "max_overhang_m": max_overhang,
            "source": source,
        }

    def to_dataframe(self, benches=None) -> "pd.DataFrame":
        """Return a :class:`pandas.DataFrame` with one row per point.

        Base columns (always present, English snake_case): ``bench_number``,
        ``segment_type``, ``distance_m``, ``elevation_m``, ``is_ramp``,
        ``source``. ``is_ramp`` is ``True`` for points whose
        ``segment_type == "ramp"``.

        When ``benches`` is supplied, three hazard columns are appended
        by bench-number match: ``overhang_m`` (NaN when the bench number
        is absent in the supplied benches), ``wedge_risk`` (``False``
        when absent), ``toppling_risk`` (``False`` when absent).
        """
        rows = [
            {
                "bench_number": int(p.bench_number),
                "segment_type": str(p.segment_type),
                "distance_m": float(p.distance),
                "elevation_m": float(p.elevation),
                "is_ramp": bool(p.segment_type == "ramp"),
                "source": str(p.source),
            }
            for p in self.points
        ]
        base_cols = [
            "bench_number", "segment_type", "distance_m",
            "elevation_m", "is_ramp", "source",
        ]
        df = pd.DataFrame(rows, columns=base_cols)

        if benches is not None:
            by_num = {int(b.bench_number): b for b in benches}
            overhang_col = []
            wedge_col = []
            toppling_col = []
            for p in self.points:
                b = by_num.get(int(p.bench_number))
                if b is None:
                    overhang_col.append(math.nan)
                    wedge_col.append(False)
                    toppling_col.append(False)
                else:
                    overhang_col.append(float(b.overhang_m))
                    wedge_col.append(bool(b.wedge_risk))
                    toppling_col.append(bool(b.toppling_risk))
            df["overhang_m"] = overhang_col
            df["wedge_risk"] = wedge_col
            df["toppling_risk"] = toppling_col

        return df

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict snapshot of the profile.

        Shape: ``{"distances": list[float], "elevations": list[float],
        "points": list[dict], "source": str}``. Each point dict has
        keys ``bench_number``, ``segment_type``, ``distance_m``,
        ``elevation_m``, ``is_ramp``, ``source``. ``is_ramp`` is derived
        from ``segment_type == "ramp"``.
        """
        points = [
            {
                "bench_number": int(p.bench_number),
                "segment_type": str(p.segment_type),
                "distance_m": float(p.distance),
                "elevation_m": float(p.elevation),
                "is_ramp": bool(p.segment_type == "ramp"),
                "source": str(p.source),
            }
            for p in self.points
        ]
        source = str(self.points[0].source) if self.points else "topo"
        return {
            "distances": [float(x) for x in self.distances],
            "elevations": [float(x) for x in self.elevations],
            "points": points,
            "source": source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReconciledProfile":
        """Reconstruct a :class:`ReconciledProfile` from a :meth:`to_dict` snapshot.

        Unknown fields in ``d`` (and unknown keys inside point dicts) are
        silently dropped. Point dicts MUST contain at least
        ``distance_m``, ``elevation_m``, ``bench_number``, and
        ``segment_type``; ``source`` defaults to ``"topo"``.
        """
        distances = np.asarray(d.get("distances", []), dtype=float)
        elevations = np.asarray(d.get("elevations", []), dtype=float)
        points: List[ReconciledPoint] = []
        for pt in d.get("points", []) or []:
            points.append(ReconciledPoint(
                distance=float(pt["distance_m"]),
                elevation=float(pt["elevation_m"]),
                bench_number=int(pt["bench_number"]),
                segment_type=str(pt["segment_type"]),
                source=str(pt.get("source", "topo")),
            ))
        return cls(distances=distances, elevations=elevations, points=points)


logger = logging.getLogger(__name__)


@dataclass
class BenchParams:
    bench_number: int
    crest_elevation: float
    crest_distance: float
    toe_elevation: float
    toe_distance: float
    bench_height: float
    face_angle: float
    berm_width: float
    is_ramp: bool = False
    group_break: bool = False
    spill_width: float = 0.0
    effective_berm_width: float = 0.0
    spill_start_distance: float = 0.0
    spill_start_elevation: float = 0.0
    overhang_m: float = 0.0
    rock_bridge_thickness_m: float = 0.0
    rock_bridge_height_m: float = 0.0
    catch_bench_adequate: bool = False
    catch_bench_ratio: float = 0.0
    wedge_risk: bool = False
    toppling_risk: bool = False
    face_angle_inconsistent: bool = False
    anisotropy_dispersion_deg: float = 0.0
    confidence_score: float = 1.0
    detection_method: str = "angle_only"
    n_detection_methods_agreeing: int = 1
    source_points: int = 0
    ramp_segment: bool = False


@dataclass
class ReconciliationGap:
    section_name: str
    sector: str
    d_start: float
    d_end: float
    expected_bench_height: float
    actual_height: float
    delta_h: float
    location: str
    severity: str


@dataclass
class ExtractionResult:
    """Result of parameter extraction for a section."""
    section_name: str
    sector: str
    benches: List[BenchParams] = field(default_factory=list)
    inter_ramp_angle: float = 0.0
    overall_angle: float = 0.0
    gaps: List[ReconciliationGap] = field(default_factory=list)


def _adaptive_smooth(elevations) -> np.ndarray:
    """Savitzky-Golay smoothing with a window scaled to profile length."""
    e = np.asarray(elevations, dtype=float)
    n = len(e)
    if n < 5 or _savgol_filter is None:
        return e
    window = min(DETECTION.smoothing_max_window,
                 max(DETECTION.smoothing_min_window, n // 30))
    if window % 2 == 0:
        window += 1
    if window >= n:
        window = n if n % 2 == 1 else n - 1
    if window < DETECTION.smoothing_min_window:
        return e
    polyorder = min(3, window - 1)
    try:
        return _savgol_filter(e, window, polyorder=polyorder)
    except Exception:  # pragma: no cover - defensive
        return e


def _discrete_curvature(distances, elevations) -> np.ndarray:
    """Absolute change in local slope (degrees) at each profile point."""
    d = np.asarray(distances, dtype=float)
    e = np.asarray(elevations, dtype=float)
    n = len(d)
    curv = np.zeros(n)
    if n < 3:
        return curv
    a_next = np.arctan2(e[2:] - e[1:-1], d[2:] - d[1:-1])
    a_prev = np.arctan2(e[1:-1] - e[:-2], d[1:-1] - d[:-2])
    curv[1:-1] = np.degrees(np.abs(a_next - a_prev))
    return curv


def _find_local_extrema(distances, elevations, window: int = 3) -> Tuple[List[int], List[int]]:
    """Return ``(crests, toes)`` as index lists.

    A crest is a slope sign change from non-descending to descending
    (the corner at the top of a face, including the flat-berm → face
    transition). A toe is the symmetric change at the bottom. Flat
    berms (zero-slope plateaus) are handled correctly: an interior
    plateau point is neither a crest nor a toe.
    """
    d = np.asarray(distances, dtype=float)
    e = np.asarray(elevations, dtype=float)
    n = len(d)
    crests: List[int] = []
    toes: List[int] = []
    if n < 2 * window + 1:
        return crests, toes
    slope_sign = np.sign(np.diff(e))
    for i in range(window, n - window):
        incoming = slope_sign[i - 1]
        outgoing = slope_sign[i]
        if incoming >= 0 and outgoing < 0:
            crests.append(i)
        if incoming < 0 and outgoing >= 0:
            toes.append(i)
    return crests, toes


def _vote_bench_detection(
    d_min: float,
    d_max: float,
    distances,
    elevations,
    face_threshold: float,
) -> Tuple[int, str]:
    """Count how many detection methods agree a ``[d_min, d_max]`` span is a face.

    Method A (RDP + angle) always agrees because it produced the candidate.
    Methods B (curvature), C (local extrema) and D (smoothed slope) vote
    independently. Returns ``(n_agreeing, method_label)``.
    """
    d = np.asarray(distances, dtype=float)
    e = np.asarray(elevations, dtype=float)
    n_agree = 1
    labels = ["angle"]

    lo = min(d_min, d_max)
    hi = max(d_min, d_max)
    span = max(hi - lo, 1e-6)
    zone = span * 0.4 + 2.0

    curv = _discrete_curvature(d, e)
    left_mask = (d >= lo - zone) & (d <= lo + zone)
    right_mask = (d >= hi - zone) & (d <= hi + zone)
    left_curv = np.any(curv[left_mask] > DETECTION.curvature_threshold) if np.any(left_mask) else False
    right_curv = np.any(curv[right_mask] > DETECTION.curvature_threshold) if np.any(right_mask) else False
    if left_curv and right_curv:
        n_agree += 1
        labels.append("curvature")

    crests, toes = _find_local_extrema(d, e, window=DETECTION.extrema_window)
    has_crest = any(lo - zone <= d[c] <= hi + zone for c in crests)
    has_toe = any(lo - zone <= d[t] <= hi + zone for t in toes)
    if has_crest and has_toe:
        n_agree += 1
        labels.append("extrema")

    e_smooth = _adaptive_smooth(e)
    band = (d >= lo) & (d <= hi)
    if np.sum(band) >= 2:
        seg_d = d[band]
        seg_e = e_smooth[band]
        denom = abs(float(seg_d[-1] - seg_d[0]))
        if denom > 1e-6:
            slope = abs(float(np.degrees(np.arctan2(seg_e[-1] - seg_e[0], denom))))
            if slope >= face_threshold - DETECTION.face_threshold_margin:
                n_agree += 1
                labels.append("smooth")

    label = "consensus" if n_agree >= DETECTION.consensus_quorum else "disputed"
    return n_agree, label


def _confidence_from_vote(n_agree: int, source_points: int) -> float:
    """Map method agreement + point density to a 0..1 confidence score."""
    if n_agree < DETECTION.consensus_quorum:
        return 0.5
    density = min(1.0, source_points / float(DETECTION.confidence_density_floor))
    return min(1.0, (n_agree / 4.0) * density)


def _detect_sub_benches(face_pts: np.ndarray, max_width: float) -> List[np.ndarray]:
    """Split a wide face at intermediate elevation minima (hidden berms).

    Returns a list of point arrays, one per sub-bank. When the face is
    narrower than ``max_width`` or has no usable split points, a single
    array (the input) is returned unchanged.
    """
    pts = np.asarray(face_pts, dtype=float)
    if len(pts) < 4:
        return [pts]
    d = pts[:, 0]
    e = pts[:, 1]
    span = abs(float(d.max() - d.min()))
    if span <= max_width:
        return [pts]

    order = np.argsort(d)
    d = d[order]
    e = e[order]
    split_idx = []
    for i in range(1, len(d) - 1):
        if e[i] <= e[i - 1] and e[i] <= e[i + 1]:
            left_top = e[:i].max()
            right_top = e[i + 1:].max()
            prominence = min(left_top - e[i], right_top - e[i])
            if prominence >= DETECTION.sub_bench_min_prominence:
                split_idx.append(i)
    if not split_idx:
        return [pts]
    boundaries = [0] + split_idx + [len(d)]
    sub_arrays = []
    for a, b in zip(boundaries[:-1], boundaries[1:]):
        chunk = pts[order][a:b + 1]
        if len(chunk) >= 2:
            sub_arrays.append(chunk)
    return sub_arrays if sub_arrays else [pts]


def _bench_from_points(
    pts: np.ndarray,
    distances,
    elevations,
    face_threshold: float,
    bench_number: int,
    detection_method: str,
    confidence_score: float,
    n_agreeing: int,
) -> BenchParams:
    """Build a :class:`BenchParams` from a face point cloud (sub-bank path)."""
    pts = np.asarray(pts, dtype=float)
    sorted_pts = pts[np.argsort(-pts[:, 1])]
    crest = sorted_pts[0]
    toe = sorted_pts[-1]
    bench_height = float(abs(crest[1] - toe[1]))
    dx = abs(float(crest[0] - toe[0]))
    if dx > 1e-3:
        face_angle = float(np.degrees(np.arctan2(abs(crest[1] - toe[1]), dx)))
    else:
        face_angle = face_threshold
    d_lo = min(float(crest[0]), float(toe[0]))
    d_hi = max(float(crest[0]), float(toe[0]))
    d_arr = np.asarray(distances, dtype=float)
    source_points = int(np.sum((d_arr >= d_lo - 0.1) & (d_arr <= d_hi + 0.1)))
    return BenchParams(
        bench_number=bench_number,
        crest_elevation=float(crest[1]),
        crest_distance=float(crest[0]),
        toe_elevation=float(toe[1]),
        toe_distance=float(toe[0]),
        bench_height=bench_height,
        face_angle=face_angle,
        berm_width=0.0,
        detection_method=detection_method,
        confidence_score=float(confidence_score),
        n_detection_methods_agreeing=int(n_agreeing),
        source_points=source_points,
    )


def _emit_reconciliation_gaps(
    detected: List[BenchParams],
    design_benches: List[BenchParams],
    tolerances,
    section_name: str,
    sector: str,
) -> List[ReconciliationGap]:
    """Compare detected benches against design and emit deviation gaps."""
    gaps: List[ReconciliationGap] = []
    if not design_benches:
        return gaps

    tol_h = tolerances.get("bench_height", {"neg": 1.0, "pos": 1.5})
    tol_pos = float(tol_h.get("pos", 1.5))
    tol_neg = float(tol_h.get("neg", 1.0))
    tol_mag = max(tol_pos, tol_neg)

    matched_topo: set = set()
    for bd in design_benches:
        bd_mid = 0.5 * (bd.crest_elevation + bd.toe_elevation)
        best_j = None
        best_dz = DETECTION.gap_match_threshold
        for j, bt in enumerate(detected):
            if j in matched_topo:
                continue
            bt_mid = 0.5 * (bt.crest_elevation + bt.toe_elevation)
            dz = abs(bt_mid - bd_mid)
            if dz < best_dz:
                best_dz = dz
                best_j = j
        if best_j is None:
            d_start = min(bd.crest_distance, bd.toe_distance)
            d_end = max(bd.crest_distance, bd.toe_distance)
            gaps.append(ReconciliationGap(
                section_name=section_name,
                sector=sector,
                d_start=float(d_start),
                d_end=float(d_end),
                expected_bench_height=float(bd.bench_height),
                actual_height=0.0,
                delta_h=float(-bd.bench_height),
                location="missing_crest",
                severity="severe",
            ))
            continue
        matched_topo.add(best_j)
        bt = detected[best_j]
        delta_h = float(bt.bench_height - bd.bench_height)
        if abs(delta_h) > tol_mag:
            location = "overbreak" if delta_h > 0 else "extra_material"
            if abs(delta_h) > 2.0 * tol_mag:
                severity = "severe"
            elif abs(delta_h) > 1.5 * tol_mag:
                severity = "moderate"
            else:
                severity = "minor"
            d_start = min(bt.crest_distance, bt.toe_distance, bd.crest_distance, bd.toe_distance)
            d_end = max(bt.crest_distance, bt.toe_distance, bd.crest_distance, bd.toe_distance)
            gaps.append(ReconciliationGap(
                section_name=section_name,
                sector=sector,
                d_start=float(d_start),
                d_end=float(d_end),
                expected_bench_height=float(bd.bench_height),
                actual_height=float(bt.bench_height),
                delta_h=delta_h,
                location=location,
                severity=severity,
            ))
    return gaps


_GAP_TOLERANCES = {
    "bench_height": {
        "neg": TOLERANCES.bench_height["neg"],
        "pos": TOLERANCES.bench_height["pos"],
    },
}


def _simplify_and_classify_segments(
    distances, elevations,
) -> tuple[np.ndarray, np.ndarray, list[dict]] | None:
    """Run RDP simplification and merge segments into face/berm buckets.

    Returns ``(simplified, angles, merged_segments)`` on success, or
    ``None`` when the profile is too short / degenerate to extract
    anything (caller short-circuits and returns an empty result).
    """
    if len(distances) < 3:
        return None
    points = np.column_stack((distances, elevations))
    epsilon = DETECTION.simplify_epsilon
    simplified = ramer_douglas_peucker(points, epsilon)
    if len(simplified) < 2:
        return None

    d_simp = simplified[:, 0]
    e_simp = simplified[:, 1]
    dx = np.diff(d_simp)
    dy = np.diff(e_simp)
    dists = np.sqrt(dx**2 + dy**2)

    valid_seg = dists > 1e-4
    if not np.any(valid_seg):
        return None

    angles = np.zeros(len(dx))
    angles[valid_seg] = np.abs(np.degrees(np.arctan2(dy[valid_seg], dx[valid_seg])))

    segment_type = np.full(len(angles), 0)
    segment_type[angles >= DETECTION.face_threshold] = 1
    segment_type[angles <= DETECTION.berm_threshold] = 2

    merged_segments = _merge_adjacent_segments(segment_type)
    return simplified, angles, merged_segments


def _merge_adjacent_segments(segment_type: np.ndarray) -> list[dict]:
    """Coalesce consecutive equal-type segments into {start_idx, end_idx} dicts."""
    merged: list[dict] = []
    if len(segment_type) == 0:
        return merged
    current_type = segment_type[0]
    start_idx = 0
    for i in range(1, len(segment_type)):
        if segment_type[i] != current_type:
            merged.append({
                'type': current_type,
                'start_idx': start_idx,
                'end_idx': i,
            })
            current_type = segment_type[i]
            start_idx = i
    merged.append({
        'type': current_type,
        'start_idx': start_idx,
        'end_idx': len(segment_type),
    })
    return merged


def _build_face_bench(
    face_pts: np.ndarray,
    simplified: np.ndarray,
    distances, elevations,
    face_threshold: float,
    dx: np.ndarray, dy: np.ndarray,
    dists: np.ndarray, angles: np.ndarray,
    bench_num: int,
    prev_face_angle: float | None,
) -> BenchParams:
    """Build a single BenchParams from a face segment, including toe/spill.

    Returns a BenchParams with confidence_score, detection_method and
    n_detection_methods_agreeing already filled (via the multi-method
    vote on the same span).
    """
    crest = face_pts[np.argmax(face_pts[:, 1])]
    toe = face_pts[np.argmin(face_pts[:, 1])]
    bench_height = abs(crest[1] - toe[1])

    idx_start = 0
    idx_end = len(dx)

    local_len = dists[idx_start:idx_end]
    local_ang = angles[idx_start:idx_end]
    weighted_angle = _weighted_face_angle(
        local_ang, local_len, face_threshold
    )

    final_toe_x, final_angle, spill_w, spill_pt = _correct_toe_with_spill(
        face_pts, crest, toe, distances, elevations, weighted_angle,
    )

    face_mask = _face_span_mask(distances, crest, toe)
    source_points_total = int(np.sum(face_mask))

    n_agree, method_label = _vote_bench_detection(
        min(crest[0], toe[0]), max(crest[0], toe[0]),
        distances, elevations, face_threshold,
    )
    confidence = _confidence_from_vote(n_agree, source_points_total)

    return BenchParams(
        bench_number=bench_num,
        crest_elevation=float(crest[1]),
        crest_distance=float(crest[0]),
        toe_elevation=float(toe[1]),
        toe_distance=final_toe_x,
        bench_height=float(bench_height),
        face_angle=float(final_angle),
        berm_width=0.0,
        spill_width=float(spill_w),
        effective_berm_width=0.0,
        spill_start_distance=float(spill_pt[0]),
        spill_start_elevation=float(spill_pt[1]),
        confidence_score=float(confidence),
        detection_method=method_label,
        n_detection_methods_agreeing=int(n_agree),
        source_points=int(source_points_total),
    )


def _weighted_face_angle(
    local_ang: np.ndarray, local_len: np.ndarray, face_threshold: float,
) -> float:
    """Average face angle weighted by segment length, focusing on steep parts."""
    steep_mask = local_ang > (face_threshold - DETECTION.face_threshold_margin)
    if np.sum(local_len[steep_mask]) > 0.1:
        return float(np.average(local_ang[steep_mask], weights=local_len[steep_mask]))
    return float(np.average(local_ang, weights=local_len))


def _correct_toe_with_spill(
    face_pts: np.ndarray, crest: np.ndarray, toe: np.ndarray,
    distances, elevations, weighted_angle: float,
) -> tuple[float, float, float, np.ndarray]:
    """Detect a corrected toe and spill point; return (toe_x, angle, spill_w, spill_pt)."""
    corrected_toe_x, corrected_angle, spill_pt = _detect_and_project_solid_toe(
        face_pts, DETECTION.face_threshold
    )
    if abs(corrected_toe_x - toe[0]) > 1e-3:
        return corrected_toe_x, corrected_angle, abs(toe[0] - corrected_toe_x), spill_pt
    return toe[0], weighted_angle, 0.0, spill_pt


def _face_span_mask(distances, crest: np.ndarray, toe: np.ndarray) -> np.ndarray:
    """Boolean mask of points that fall in the [d_min, d_max] span of a bench."""
    d_min = min(crest[0], toe[0])
    d_max = max(crest[0], toe[0])
    return (distances >= d_min - 0.1) & (distances <= d_max + 0.1)


def _finalize_ramp_angles(result: ExtractionResult, benches: list[BenchParams]) -> None:
    """Set overall + inter-ramp angles on ``result``."""
    if len(benches) >= 2:
        top = benches[0]
        bot = benches[-1]
        dz = top.crest_elevation - bot.toe_elevation
        dx = abs(top.crest_distance - bot.toe_distance)
        if dx > 1e-3:
            result.overall_angle = float(np.degrees(np.arctan2(abs(dz), dx)))
        ramp_horiz = sum(b.berm_width for b in benches if b.is_ramp)
        ir_horiz = max(dx - ramp_horiz, dx * 0.05)
        if ir_horiz > 1e-3:
            result.inter_ramp_angle = float(np.degrees(np.arctan2(abs(dz), ir_horiz)))
    elif len(benches) == 1:
        result.overall_angle = benches[0].face_angle
        result.inter_ramp_angle = benches[0].face_angle


def extract_parameters(distances, elevations, section_name, sector,
                       resolution=DETECTION.profile_resolution,
                       face_threshold=DETECTION.face_threshold,
                       berm_threshold=DETECTION.berm_threshold,
                       max_berm_width=DETECTION.max_berm_width,
                       design_benches=None,
                       max_single_bench_width=DETECTION.max_single_bench_width,
                       tolerances=None):
    """
    Extract geotechnical parameters using Vector Simplification (RDP).

    1. Simplify profile using Ramer-Douglas-Peucker (epsilon=DETECTION.simplify_epsilon)
    2. Compute angles of simplified segments
    3. Classify and merge segments
    4. Extract bench geometry
    """
    result = ExtractionResult(section_name=section_name, sector=sector)

    simplified_info = _simplify_and_classify_segments(distances, elevations)
    if simplified_info is None:
        return result
    simplified, angles, merged_segments = simplified_info

    d_simp = simplified[:, 0]
    e_simp = simplified[:, 1]
    dx = np.diff(d_simp)
    dy = np.diff(e_simp)
    dists = np.sqrt(dx**2 + dy**2)

    benches: list[BenchParams] = []
    bench_num = 0

    for seg in merged_segments:
        if seg['type'] != 1:
            continue
        idx_start = seg['start_idx']
        idx_end = seg['end_idx']
        face_pts = simplified[idx_start : idx_end + 1]
        if abs(face_pts[0, 1] - face_pts[-1, 1]) < DETECTION.min_bench_height:
            continue

        # Sub-bench split (multi-method vote) when face is wider than max_single_bench_width
        prev_face_angle = benches[-1].face_angle if benches else None
        new_bench = _build_face_bench(
            face_pts, simplified, distances, elevations,
            face_threshold, dx, dy, dists, angles,
            bench_num + 1, prev_face_angle,
        )
        new_bench.wedge_risk = _detect_wedge_shape_in_face(new_bench)
        new_bench.toppling_risk = _detect_toppling_potential(new_bench, prev_face_angle)
        benches.append(new_bench)
        bench_num += 1

    _compute_berm_widths_from_profile(
        benches, simplified, d_simp, e_simp,
        max_berm_width=max_berm_width,
    )

    _apply_leading_berm(benches, distances, elevations, berm_threshold)
    _apply_trailing_berm(benches, distances, elevations, berm_threshold)

    _detect_overhangs_and_bridges(benches)
    _evaluate_catch_bench_adequacy(benches)

    result.benches = benches

    _finalize_ramp_angles(result, benches)

    if benches:
        _evaluate_angle_consistency(
            benches, result.inter_ramp_angle, result.overall_angle,
        )
        from core.stability_analysis import compute_anisotropy_dispersion
        dispersion = compute_anisotropy_dispersion(benches)
        for b in benches:
            b.anisotropy_dispersion_deg = dispersion

    if design_benches is not None:
        tols = tolerances if tolerances is not None else _GAP_TOLERANCES
        result.gaps = _emit_reconciliation_gaps(
            benches, list(design_benches), tols, section_name, sector,
        )

    return result


def _build_reconciled_points(
    benches,
    source: str = "topo",
    profile=None,
) -> List[ReconciledPoint]:
    """Return ordered :class:`ReconciledPoint` entries for ``benches``.

    The output polyline honours the geotechnical convention:

    * A normal bench emits **two points** — its crest and its toe.
      The horizontal berm platform that connects this bench's toe
      to the next bench's crest is modelled by an extra ``berm_top``
      point inserted *after* this bench's toe, at the same elevation
      as the next bench's crest. This way the renderer can draw the
      berm as an explicit horizontal segment between
      ``toe_i → berm_top → crest_{i+1}``.
    * A bench flagged as a ramp (``is_ramp=True``) does not emit a
      ``berm_top`` corner — the previous toe connects directly to
      this ramp's crest with an oblique segment. The previous
      bench's toe and this bench's crest are still emitted so the
      polyline is continuous.
    * The last bench never emits a ``berm_top`` (no following bench).
    * Benches are emitted in the order they appear in the list, which
      is the topological order produced by :func:`extract_parameters`.
      For inverted sections (distances decreasing) the caller is
      expected to have already reversed the bench list — this
      function does not silently flip it.

    If ``profile`` is provided as a ``(distances, elevations)`` pair of
    arrays, the function additionally emits ``face`` segments between
    each crest and toe by sampling the profile points that fall in
    the open interval ``(min(crest, toe), max(crest, toe))``. This
    makes the reconciled polyline follow the actual as-built (or
    design) curvature of the bench face, rather than a straight
    crest-toe line. When no profile points fall in the face interval,
    a single midpoint is emitted so the face is never collapsed.
    """
    if not benches:
        return []
    profile_d = None
    profile_e = None
    if profile is not None:
        profile_d = np.asarray(profile[0])
        profile_e = np.asarray(profile[1])
    pts: List[ReconciledPoint] = []
    for idx, b in enumerate(benches):
        if b.is_ramp:
            pts.append(ReconciledPoint(
                distance=float(b.crest_distance),
                elevation=float(b.crest_elevation),
                bench_number=int(b.bench_number),
                segment_type="ramp",
                source=source,
            ))
        else:
            pts.append(ReconciledPoint(
                distance=float(b.crest_distance),
                elevation=float(b.crest_elevation),
                bench_number=int(b.bench_number),
                segment_type="crest",
                source=source,
            ))
        if profile_d is not None:
            d_min = min(b.crest_distance, b.toe_distance)
            d_max = max(b.crest_distance, b.toe_distance)
            mask = (profile_d > d_min) & (profile_d < d_max)
            face_d = profile_d[mask]
            face_e = profile_e[mask]
            if face_d.size == 0:
                mid_d = 0.5 * (b.crest_distance + b.toe_distance)
                mid_e = 0.5 * (b.crest_elevation + b.toe_elevation)
                pts.append(ReconciledPoint(
                    distance=float(mid_d),
                    elevation=float(mid_e),
                    bench_number=int(b.bench_number),
                    segment_type="face",
                    source=source,
                ))
            else:
                for fd, fe in zip(face_d, face_e):
                    pts.append(ReconciledPoint(
                        distance=float(fd),
                        elevation=float(fe),
                        bench_number=int(b.bench_number),
                        segment_type="face",
                        source=source,
                    ))
        pts.append(ReconciledPoint(
            distance=float(b.toe_distance),
            elevation=float(b.toe_elevation),
            bench_number=int(b.bench_number),
            segment_type="toe",
            source=source,
        ))
        # Only emit a berm_top corner when the next bench's crest sits at
        # or above this bench's toe. When the next bench is lower
        # (over-excavation, irregular slope), emitting berm_top would
        # make the stair-step descend from the current toe down to the
        # next crest and hide the real pata del banco. Skipping it lets
        # the renderer draw a straight oblique toe -> next-crest line,
        # which matches the expected geometry.
        if not b.is_ramp and idx + 1 < len(benches):
            next_b = benches[idx + 1]
            if next_b.crest_elevation >= b.toe_elevation:
                pts.append(ReconciledPoint(
                    distance=float(b.toe_distance),
                    elevation=float(next_b.crest_elevation),
                    bench_number=int(b.bench_number),
                    segment_type="berm_top",
                    source=source,
                ))
    return pts
