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

import logging
from dataclasses import dataclass, field
from typing import List, Literal

import numpy as np

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
from core.config import DETECTION
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


@dataclass
class ExtractionResult:
    """Result of parameter extraction for a section."""
    section_name: str
    sector: str
    benches: List[BenchParams] = field(default_factory=list)
    inter_ramp_angle: float = 0.0
    overall_angle: float = 0.0


def extract_parameters(distances, elevations, section_name, sector,
                       resolution=DETECTION.profile_resolution,
                       face_threshold=DETECTION.face_threshold,
                       berm_threshold=DETECTION.berm_threshold,
                       max_berm_width=DETECTION.max_berm_width):
    """
    Extract geotechnical parameters using Vector Simplification (RDP).

    1. Simplify profile using Ramer-Douglas-Peucker (epsilon=DETECTION.simplify_epsilon)
    2. Compute angles of simplified segments
    3. Classify and merge segments
    4. Extract bench geometry
    """
    result = ExtractionResult(section_name=section_name, sector=sector)

    if len(distances) < 3:
        return result

    points = np.column_stack((distances, elevations))

    epsilon = DETECTION.simplify_epsilon
    simplified = ramer_douglas_peucker(points, epsilon)

    if len(simplified) < 2:
        return result

    d_simp = simplified[:, 0]
    e_simp = simplified[:, 1]

    dx = np.diff(d_simp)
    dy = np.diff(e_simp)
    dists = np.sqrt(dx**2 + dy**2)

    valid_seg = dists > 1e-4
    if not np.any(valid_seg):
        return result

    angles = np.zeros(len(dx))
    angles[valid_seg] = np.abs(np.degrees(np.arctan2(dy[valid_seg], dx[valid_seg])))

    segment_type = np.full(len(angles), 0)

    segment_type[angles >= face_threshold] = 1
    segment_type[angles <= berm_threshold] = 2

    merged_segments = []
    if len(segment_type) > 0:
        current_type = segment_type[0]
        start_idx = 0
        for i in range(1, len(segment_type)):
            if segment_type[i] != current_type:
                merged_segments.append({
                    'type': current_type,
                    'start_idx': start_idx,
                    'end_idx': i,
                })
                current_type = segment_type[i]
                start_idx = i
        merged_segments.append({
            'type': current_type,
            'start_idx': start_idx,
            'end_idx': len(segment_type),
        })

    benches = []
    bench_num = 0

    for seg in merged_segments:
        if seg['type'] == 1:
            idx_start = seg['start_idx']
            idx_end = seg['end_idx']

            face_pts = simplified[idx_start : idx_end + 1]

            p_start = face_pts[0]
            p_end = face_pts[-1]

            sorted_face_pts = face_pts[np.argsort(-face_pts[:, 1])]
            crest = sorted_face_pts[0]
            toe = sorted_face_pts[-1]

            bench_height = abs(crest[1] - toe[1])

            if bench_height < DETECTION.min_bench_height:
                continue

            local_dx = dx[idx_start:idx_end]
            local_dy = dy[idx_start:idx_end]
            local_len = dists[idx_start:idx_end]
            local_ang = angles[idx_start:idx_end]

            steep_mask = local_ang > (face_threshold - DETECTION.face_threshold_margin)
            if np.sum(local_len[steep_mask]) > 0.1:
                weighted_angle = np.average(local_ang[steep_mask], weights=local_len[steep_mask])
            else:
                weighted_angle = np.average(local_ang, weights=local_len)

            d_min = min(crest[0], toe[0])
            d_max = max(crest[0], toe[0])
            mask_raw = (
                (elevations > toe[1] + 0.1) &
                (elevations < crest[1] - 0.1) &
                (distances > d_min - 0.1) &
                (distances < d_max + 0.1)
            )
            raw_d = distances[mask_raw]
            raw_e = elevations[mask_raw]
            face_pts_for_analysis = sorted_face_pts
            if len(raw_d) >= 3:
                raw_face_pts = np.column_stack((raw_d, raw_e))
                raw_face_pts = raw_face_pts[np.argsort(-raw_face_pts[:, 1])]
                simplified_face = ramer_douglas_peucker(raw_face_pts, DETECTION.face_refine_epsilon)
                if len(simplified_face) >= 3:
                    face_pts_for_analysis = simplified_face
            corrected_toe_x, corrected_angle, spill_pt = _detect_and_project_solid_toe(face_pts_for_analysis, face_threshold)
            final_toe_x = corrected_toe_x
            spill_w = 0.0
            if abs(corrected_toe_x - toe[0]) > 1e-3:
                final_angle = corrected_angle
                spill_w = abs(toe[0] - corrected_toe_x)
            else:
                final_angle = weighted_angle

            bench_num += 1
            prev_face_angle = benches[-1].face_angle if benches else None
            new_bench = BenchParams(
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
                spill_start_elevation=float(spill_pt[1])
            )
            new_bench.wedge_risk = _detect_wedge_shape_in_face(new_bench)
            new_bench.toppling_risk = _detect_toppling_potential(new_bench, prev_face_angle)
            benches.append(new_bench)

    _compute_berm_widths_from_profile(
        benches, simplified, d_simp, e_simp,
        max_berm_width=max_berm_width,
    )

    _apply_leading_berm(benches, distances, elevations, berm_threshold)
    _apply_trailing_berm(benches, distances, elevations, berm_threshold)

    _detect_overhangs_and_bridges(benches)
    _evaluate_catch_bench_adequacy(benches)

    result.benches = benches

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

    if benches:
        _evaluate_angle_consistency(
            benches, result.inter_ramp_angle, result.overall_angle,
        )
        from core.stability_analysis import compute_anisotropy_dispersion
        dispersion = compute_anisotropy_dispersion(benches)
        for b in benches:
            b.anisotropy_dispersion_deg = dispersion

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
        if not b.is_ramp and idx + 1 < len(benches):
            next_b = benches[idx + 1]
            pts.append(ReconciledPoint(
                distance=float(b.toe_distance),
                elevation=float(next_b.crest_elevation),
                bench_number=int(b.bench_number),
                segment_type="berm_top",
                source=source,
            ))
    return pts
