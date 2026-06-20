"""Parameter extraction from profiles and design vs as-built comparison."""

import logging
import warnings

import numpy as np
from dataclasses import dataclass, field
from typing import List, Literal
from scipy.interpolate import interp1d
from scipy.ndimage import uniform_filter1d

from core.blast_correlation import classify_berm_as_ramp
from core.config import DETECTION, RAMP

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


@dataclass
class ExtractionResult:
    """Result of parameter extraction for a section."""
    section_name: str
    sector: str
    benches: List[BenchParams] = field(default_factory=list)
    inter_ramp_angle: float = 0.0
    overall_angle: float = 0.0


def ramer_douglas_peucker(points, epsilon):
    """
    Simplifies a 2D polyline using Ramer-Douglas-Peucker algorithm.
    points: Nx2 array
    epsilon: approximate max distance error

    Iterative implementation (explicit stack + keep-mask): same output as
    the classic recursive version, without per-level array allocations or
    recursion-depth limits on dense profiles.
    """
    points = np.asarray(points)
    n = len(points)
    if n < 3:
        return points

    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[n - 1] = True

    # Each entry is an index range (start, end) whose endpoints are kept
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue

        start_pt = points[start]
        end_pt = points[end]
        line_vec = end_pt - start_pt
        line_len_sq = np.dot(line_vec, line_vec)

        seg = points[start + 1:end]
        if line_len_sq == 0:
            dists = np.linalg.norm(seg - start_pt, axis=1)
        else:
            # 2D cross product magnitude: |dx*py - dy*px| / line_length
            numer = np.abs(line_vec[0] * (seg[:, 1] - start_pt[1]) -
                           line_vec[1] * (seg[:, 0] - start_pt[0]))
            dists = numer / np.sqrt(line_len_sq)

        local_idx = int(np.argmax(dists))
        if dists[local_idx] > epsilon:
            index = start + 1 + local_idx
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))

    return points[keep]


def _detect_and_project_solid_toe(sorted_face_pts: np.ndarray, face_threshold: float) -> tuple[float, float, np.ndarray]:
    n_pts = len(sorted_face_pts)
    crest = sorted_face_pts[0]
    toe = sorted_face_pts[-1]
    dz = crest[1] - toe[1]
    dx = abs(crest[0] - toe[0])
    default_angle = float(np.degrees(np.arctan2(dz, dx))) if dx > 1e-3 else face_threshold
    if n_pts < 3:
        return float(toe[0]), default_angle, toe
    dy = np.diff(sorted_face_pts[:, 1])
    dx_diff = np.diff(sorted_face_pts[:, 0])
    segs_len = np.sqrt(dx_diff**2 + dy**2)
    valid = segs_len > 1e-4
    segs_ang = np.zeros(len(dy))
    segs_ang[valid] = np.abs(np.degrees(np.arctan2(dy[valid], dx_diff[valid])))
    spill_idx = len(segs_ang)
    for i in range(len(segs_ang) - 1, -1, -1):
        if segs_ang[i] < DETECTION.spill_angle_pile and np.any(segs_ang[:i] > DETECTION.spill_angle_solid):
            spill_idx = i
        else:
            break
    if spill_idx > 0:
        solid_pts = sorted_face_pts[:spill_idx + 1]
        solid_y = solid_pts[:, 1]
        solid_x = solid_pts[:, 0]
        if len(solid_pts) >= 2 and np.var(solid_y) > 1e-4:
            poly = np.polyfit(solid_y, solid_x, 1)
            x_projected = float(poly[0] * toe[1] + poly[1])
            m_abs = abs(poly[0])
            corrected_angle = float(np.degrees(np.arctan2(1, m_abs))) if m_abs > 1e-4 else 90.0
            if crest[0] < toe[0]:
                x_projected = np.clip(x_projected, crest[0], toe[0])
            else:
                x_projected = np.clip(x_projected, toe[0], crest[0])
            return x_projected, corrected_angle, sorted_face_pts[spill_idx]
    return float(toe[0]), default_angle, toe


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

    # Prepare points
    points = np.column_stack((distances, elevations))
    
    # 1. Simplify
    # Epsilon determines how much "noise" we ignore. 
    # For accurate crests/toes, we want high precision.
    epsilon = DETECTION.simplify_epsilon
    simplified = ramer_douglas_peucker(points, epsilon)
    
    if len(simplified) < 2:
        return result
        
    d_simp = simplified[:, 0]
    e_simp = simplified[:, 1]
    
    # 2. Compute Segment Angles
    dx = np.diff(d_simp)
    dy = np.diff(e_simp)
    dists = np.sqrt(dx**2 + dy**2)
    
    # Avoid zero-length segments
    valid_seg = dists > 1e-4
    if not np.any(valid_seg):
        return result
        
    angles = np.zeros(len(dx))
    # Angle in degrees (always positive)
    angles[valid_seg] = np.abs(np.degrees(np.arctan2(dy[valid_seg], dx[valid_seg])))
    
    # 3. Classify Segments
    # Use thresholds provided
    segment_type = np.full(len(angles), 0) # 0=Unknown, 1=Face, 2=Berm
    
    # Strict classification
    segment_type[angles >= face_threshold] = 1 # Face
    segment_type[angles <= berm_threshold] = 2 # Berm
    
    # Merge consecutive segments of same type
    # For "Unknown" segments, we can try to merge them into neighbors or ignore
    # Let's simple merge same types.
    
    merged_segments = []
    if len(segment_type) > 0:
        current_type = segment_type[0]
        start_idx = 0
        for i in range(1, len(segment_type)):
            if segment_type[i] != current_type:
                merged_segments.append({
                    'type': current_type,
                    'start_idx': start_idx, # Index in simplified array
                    'end_idx': i # Exclusive
                })
                current_type = segment_type[i]
                start_idx = i
        merged_segments.append({
            'type': current_type,
            'start_idx': start_idx,
            'end_idx': len(segment_type)
        })
        
    # 4. Extract Benches
    # A bench is usually Berm -> Face (or just Face if it's the bottom and we start there)
    # We look for Face segments.
    # Crest is the top point of a face (dist, elev at start of face segment if going left-to-right? 
    # Wait, distances are sorted? Yes usually distance along section.
    # If distance increases, and we look at profile:
    # Face goes DOWN usually? Or UP?
    # Profile is (Distance, Elevation).
    # Distance usually from Origin outwards.
    # Slopes usually go down or up.
    # Let's assume standard behavior: we just care about the segment geometry.
    # "Crest" is higher elevation point of face. "Toe" is lower elevation point.
    
    benches = []
    bench_num = 0
    
    for seg in merged_segments:
        if seg['type'] == 1: # Face
            # Indices in simplified array
            idx_start = seg['start_idx']
            idx_end = seg['end_idx'] # Exclusive, so point index is idx_end
            
            # Points defining this face sequence
            face_pts = simplified[idx_start : idx_end + 1]
            
            # Start and End of the face "macro-segment"
            p_start = face_pts[0]
            p_end = face_pts[-1]
            
            # Determine Crest and Toe based on elevation
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
            benches.append(BenchParams(
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
            ))

    _compute_berm_widths_from_profile(
        benches, simplified, d_simp, e_simp,
        max_berm_width=max_berm_width,
    )

    _apply_leading_berm(benches, distances, elevations, berm_threshold)
    _apply_trailing_berm(benches, distances, elevations, berm_threshold)

    _detect_overhangs_and_bridges(benches)
    _evaluate_catch_bench_adequacy(benches)

    result.benches = benches
    
    # Calculate angles
    if len(benches) >= 2:
        top = benches[0]
        bot = benches[-1]
        
        # Overall: Crest top to Toe bot
        dz = top.crest_elevation - bot.toe_elevation
        dx = abs(top.crest_distance - bot.toe_distance)
        if dx > 1e-3:
            result.overall_angle = float(np.degrees(np.arctan2(abs(dz), dx)))

        # Inter-ramp: same geometry but subtract horizontal distance occupied by ramps.
        # Ramps add horizontal traversal without contributing proportionally to height,
        # so excluding them yields a steeper (more representative) slope angle.
        ramp_horiz = sum(b.berm_width for b in benches if b.is_ramp)
        ir_horiz = max(dx - ramp_horiz, dx * 0.05)  # floor at 5% of total to avoid /0
        if ir_horiz > 1e-3:
            result.inter_ramp_angle = float(np.degrees(np.arctan2(abs(dz), ir_horiz)))
    elif len(benches) == 1:
        result.overall_angle = benches[0].face_angle
        result.inter_ramp_angle = benches[0].face_angle

    return result


def _compute_berm_widths_from_profile(
    benches, simplified, d_simp, e_simp,
    max_berm_width=50.0
):
    """Compute berm widths as the horizontal distance between toe and crest of adjacent benches.

    Geotechnically, the berm of a bench (e.g. Bench i) is the horizontal platform 
    located in its UPPER part (at its crest), connecting it to the previous bench i-1.
    
    For Bench i >= 1:
      berm_width = abs(min(curr_crest, curr_toe) - max(prev_crest, prev_toe))
    """
    n_benches = len(benches)
    if n_benches == 0:
        return
        
    # Initialize the first bench's berm to 0.0 (it might be updated later by leading berm check)
    benches[0].berm_width = 0.0
    benches[0].effective_berm_width = 0.0
    benches[0].is_ramp = False
    benches[0].group_break = False
        
    for i in range(n_benches - 1):
        b_curr = benches[i]
        b_next = benches[i + 1]
        
        curr_right = max(b_curr.toe_distance, b_curr.crest_distance)
        next_left = min(b_next.toe_distance, b_next.crest_distance)
        
        width = float(abs(next_left - curr_right))
        b_next.berm_width = width
        b_next.effective_berm_width = float(max(width - b_curr.spill_width, 0.0))
        
        if classify_berm_as_ramp(width):
            b_next.is_ramp = True
        else:
            b_next.is_ramp = False
            
        if width >= max_berm_width:
            b_next.group_break = True
        else:
            b_next.group_break = False


def _flat_segment_width(d_sub, e_sub, berm_threshold):
    """Return the horizontal width of a flat (≤ berm_threshold) segment, else 0.

    Both `d_sub` and `e_sub` must be array-likes of equal length ≥ 2.
    """
    if len(d_sub) < 2:
        return 0.0
    slope = np.degrees(
        np.arctan2(
            np.abs(float(e_sub[-1]) - float(e_sub[0])),
            np.abs(float(d_sub[-1]) - float(d_sub[0])),
        )
    )
    if slope > berm_threshold:
        return 0.0
    return float(np.abs(float(d_sub[-1]) - float(d_sub[0])))


def _apply_leading_berm(benches, distances, elevations, berm_threshold):
    """If the flat area before the first bench is a berm, assign its width.

    Also flags the bench as a ramp when the width is in the ramp-detection
    range (RAMP.min_width .. RAMP.max_width).
    """
    if not benches:
        return
    first = benches[0]
    first_x = min(first.toe_distance, first.crest_distance)
    if distances[-1] > distances[0]:
        mask = distances < first_x - 0.1
    else:
        mask = distances > first_x + 0.1
    width = _flat_segment_width(distances[mask], elevations[mask], berm_threshold)
    if width > 0:
        first.berm_width = width
        if classify_berm_as_ramp(width):
            first.is_ramp = True


def _apply_trailing_berm(benches, distances, elevations, berm_threshold):
    """If the flat area after the last (only) bench is a berm, assign its width.

    Only applied when there is exactly one bench and its berm has not yet
    been set — i.e. as a fallback floor.
    """
    if len(benches) != 1 or benches[-1].berm_width > 0:
        return
    last = benches[-1]
    if distances[-1] > distances[0]:
        mask = distances > last.toe_distance + 0.1
    else:
        mask = distances < last.toe_distance - 0.1
    width = _flat_segment_width(distances[mask], elevations[mask], berm_threshold)
    if width > 0:
        last.berm_width = width
        if classify_berm_as_ramp(width):
            last.is_ramp = True


def _detect_overhangs_and_bridges(benches):
    """Detect overhangs and rock bridges between consecutive non-ramp benches.

    For each pair (bench_i, bench_{i+1}):

    - ``overhang_m = bench_i.crest_distance - bench_{i+1}.toe_distance``
      * positive → overhang (the crest of bench N+1 sits behind the toe of
        bench N — there is a cantilevered block overhanging the pit).
      * negative → rock bridge (there is intact rock between the toe of
        bench N and the crest of bench N+1).
    - ``rock_bridge_height_m = bench_i.toe_elevation - bench_{i+1}.crest_elevation``
      (vertical separation; positive means the rock bridge has positive
      thickness; negative means bench N+1 sits *above* bench N's toe, i.e.
      the next bench has not yet cut down to its design toe elevation).
    - ``rock_bridge_thickness_m = min(-overhang_m if overhang_m < 0 else 0,
      rock_bridge_height_m if rock_bridge_height_m > 0 else 0)`` — the
      limiting dimension of the rock bridge.

    Updates in place: ``bench_i.overhang_m``, ``bench_i.rock_bridge_thickness_m``,
    ``bench_i.rock_bridge_height_m``. Returns ``None``.

    Skips any pair where ``benches[i].is_ramp`` is True: a ramp breaks the
    vertical bench sequence (the ramp's crest is not "above" the previous
    bench's toe in the geometric sense), so overhang/bridge geometry is
    not meaningful for that adjacency.

    Geotechnical reference (Lorig & Varona, 2004):

    - ``overhang_m >= 0.5 m`` → WARNING (yellow flag in report)
    - ``overhang_m >= 1.5 m`` → CRITICAL (red flag; classic precursor of
      planar failure per Hoek & Bray, 1981).
    """
    n = len(benches)
    if n < 2:
        return
    for i in range(n - 1):
        b_curr = benches[i]
        if b_curr.is_ramp:
            continue
        b_next = benches[i + 1]
        overhang = float(b_curr.crest_distance) - float(b_next.toe_distance)
        bridge_height = float(b_curr.toe_elevation) - float(b_next.crest_elevation)
        bridge_thickness = min(
            (-overhang) if overhang < 0 else 0.0,
            bridge_height if bridge_height > 0 else 0.0,
        )
        b_curr.overhang_m = float(overhang)
        b_curr.rock_bridge_height_m = float(bridge_height)
        b_curr.rock_bridge_thickness_m = float(bridge_thickness)


def _evaluate_catch_bench_adequacy(benches, berm_design_min_m=None):
    """Mark each bench's catch-bench adequacy.

    For every bench:

    - ``catch_bench_ratio = effective_berm_width / max(berm_width, 1e-3)``
      (always computed; 1e-3 floor avoids division by zero on degenerate
      berms).
    - ``catch_bench_adequate = True`` iff
      ``effective_berm_width >= berm_design_min_m`` AND ``berm_design_min_m``
      is not ``None``. When ``berm_design_min_m`` is ``None``, the
      boolean is left at its dataclass default (``False``) and only the
      ratio is populated for diagnostic use.

    Updates in place: ``bench.catch_bench_adequate``,
    ``bench.catch_bench_ratio``.

    Geotechnical criterion (Read & Stacey, 2009): a catch bench is
    adequate when its effective width retains the rockfall volume from
    the bench above — typically
    ``berm_design >= max(rockfall_height * 0.6, 6 m)`` for 15 m benches.
    """
    for b in benches:
        denom = max(float(b.berm_width), 1e-3)
        b.catch_bench_ratio = float(b.effective_berm_width) / denom
        if berm_design_min_m is None:
            b.catch_bench_adequate = False
        else:
            b.catch_bench_adequate = (
                float(b.effective_berm_width) >= float(berm_design_min_m)
            )


def _evaluate_status(deviation, tol_neg, tol_pos):
    """
    Evaluate compliance using tripartite system.
    """
    if deviation < 0:
        limit = tol_neg
    else:
        limit = tol_pos

    abs_dev = abs(deviation)
    if abs_dev <= limit:
        return "CUMPLE"
    elif abs_dev <= limit * 1.5:
        return "FUERA DE TOLERANCIA"
    else:
        return "NO CUMPLE"


def _build_reconciled_points(
    benches,
    source: str = "topo",
    profile: tuple[np.ndarray, np.ndarray] | None = None,
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
        # 1) Crest / ramp start
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
        # 2) Face points (only when a profile was supplied). Sample
        #    the profile points that fall strictly between crest and
        #    toe; if none, fall back to a single midpoint so the
        #    face is always represented by at least one point.
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
        # 3) Toe (end of the face / ramp)
        pts.append(ReconciledPoint(
            distance=float(b.toe_distance),
            elevation=float(b.toe_elevation),
            bench_number=int(b.bench_number),
            segment_type="toe",
            source=source,
        ))
        # 4) Berm top — only when there is a following bench AND
        #    this bench is not itself flagged as a ramp. The berm
        #    corner is placed at the next bench's crest elevation,
        #    at this bench's toe distance, so the segment from
        #    toe_i to berm_top is a step up and berm_top to
        #    crest_{i+1} is horizontal.
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


def build_reconciled_profile(benches, *, source: str = "topo",
                             return_v2: bool = False,
                             profile: tuple[np.ndarray, np.ndarray] | None = None):
    """Build an idealised profile from detected crest/toe points.

    Parameters
    ----------
    benches : list[BenchParams]
        Detected benches, typically in the order returned by
        :func:`extract_parameters`.
    source : str
        ``"design"`` or ``"topo"`` — recorded in each
        :class:`ReconciledPoint` so the renderer can colour the
        trace accordingly. Only honoured when ``return_v2=True``.
    return_v2 : bool
        If ``True`` (default in new code), returns a
        :class:`ReconciledProfile` with structured points. If
        ``False``, returns the legacy ``(distances, elevations)`` tuple
        of ``np.array`` for backward compatibility — but emits a
        :class:`DeprecationWarning` and still draws berms as
        straight lines (legacy behaviour).
    profile : tuple of (distances, elevations) | None
        Original as-built (or design) profile. When supplied AND
        ``return_v2=True``, the function samples this profile to emit
        ``face`` segments between each crest and toe, so the reconciled
        polyline follows the actual curvature of the bench face
        rather than a straight crest-toe line. Ignored by the legacy
        ``return_v2=False`` path.

    Returns
    -------
    tuple[np.ndarray, np.ndarray] | ReconciledProfile
        ``(distances, elevations)`` when ``return_v2=False``; a
        :class:`ReconciledProfile` instance when ``return_v2=True``.

    Notes
    -----
    The legacy path (``return_v2=False``) is preserved for one release
    cycle. New code should use :func:`build_reconciled_profile_v2`
    which always returns the rich structure.
    """
    if not return_v2:
        warnings.warn(
            "build_reconciled_profile(return_v2=False) is deprecated: "
            "use build_reconciled_profile_v2() to receive the rich "
            "ReconciledProfile with explicit berm segments.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not benches:
            return np.array([]), np.array([])
        pts_legacy = []
        for bench in benches:
            pts_legacy.append((bench.crest_distance, bench.crest_elevation))
            pts_legacy.append((bench.toe_distance, bench.toe_elevation))
        pts_sorted = sorted(pts_legacy, key=lambda p: p[0])
        return (
            np.array([p[0] for p in pts_sorted], dtype=float),
            np.array([p[1] for p in pts_sorted], dtype=float),
        )

    pts = _build_reconciled_points(benches, source=source, profile=profile)
    if not pts:
        return ReconciledProfile(
            distances=np.array([], dtype=float),
            elevations=np.array([], dtype=float),
            points=[],
        )
    distances = np.array([p.distance for p in pts], dtype=float)
    elevations = np.array([p.elevation for p in pts], dtype=float)
    return ReconciledProfile(
        distances=distances,
        elevations=elevations,
        points=pts,
    )


def build_reconciled_profile_v2(
    benches, *, source: str = "topo",
    profile: tuple[np.ndarray, np.ndarray] | None = None,
) -> ReconciledProfile:
    """Convenience wrapper that always returns a :class:`ReconciledProfile`.

    Equivalent to ``build_reconciled_profile(benches, source=source,
    return_v2=True, profile=profile)``. Provided so call sites do not
    need to remember the keyword argument.

    If ``profile`` is provided, the returned
    :class:`ReconciledProfile` includes ``face`` segments sampled
    from the profile between each crest and toe.
    """
    return build_reconciled_profile(
        benches, source=source, return_v2=True, profile=profile,
    )


def compare_design_vs_asbuilt(params_design, params_topo, tolerances):
    """
    Compare design vs as-built parameters using Global Best-Fit Matching (Hungarian Algorithm).
    Now returns matches, missing design benches, and extra topo benches.
    """
    from scipy.optimize import linear_sum_assignment

    comparisons = []
    
    benches_design = params_design.benches
    benches_topo = params_topo.benches
    
    n_d = len(benches_design)
    n_t = len(benches_topo)
    
    if n_d == 0 and n_t == 0:
        return []

    # Threshold for valid match (e.g. vertical difference < 8.0m)
    match_threshold = 8.0

    # Create Cost Matrix (Weighted 2D Euclidean Distance between Bench Centroids)
    # Rows: Design, Cols: Topo
    cost_matrix = np.zeros((n_d, n_t))
    
    for i, bd in enumerate(benches_design):
        bd_z = (bd.crest_elevation + bd.toe_elevation) / 2
        bd_x = (bd.crest_distance + bd.toe_distance) / 2
        for j, bt in enumerate(benches_topo):
            bt_z = (bt.crest_elevation + bt.toe_elevation) / 2
            bt_x = (bt.crest_distance + bt.toe_distance) / 2
            
            # If vertical difference is too large, assign a massive cost
            # to prevent matching across different vertical levels!
            diff_z = abs(bd_z - bt_z)
            if diff_z >= match_threshold:
                cost_matrix[i, j] = 1e9
            else:
                # 2D Euclidean distance: Z has 1.5x weight for vertical priority, X has 1.0x weight
                cost_matrix[i, j] = np.sqrt(1.5 * (bd_z - bt_z)**2 + 1.0 * (bd_x - bt_x)**2)
            
    # Solve Assignment Problem (Minimize total 2D distance cost)
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    
    # Gather valid match candidates
    candidates = []
    for r, c in zip(row_ind, col_ind):
        bd = benches_design[r]
        bt = benches_topo[c]
        bd_z = (bd.crest_elevation + bd.toe_elevation) / 2
        bt_z = (bt.crest_elevation + bt.toe_elevation) / 2
        diff_z = abs(bd_z - bt_z)
        if diff_z < match_threshold:
            candidates.append((r, c, cost_matrix[r, c]))
            
    # Sort candidates by design index r to enforce sequential monotonicity
    candidates.sort(key=lambda x: x[0])
    
    # Resolve cross-matching conflicts greedily based on cost
    valid_matches = []
    for cand in candidates:
        r, c, cost = cand
        # Since candidates are sorted by r, any already accepted match v has v_r < r.
        # Therefore, to be monotonic, we must have v_c < c.
        # Any match v with c <= v_c is a cross-matching violation!
        conflicts = [v for v in valid_matches if c <= v[1]]
        if not conflicts:
            valid_matches.append(cand)
        else:
            total_conflict_cost = sum(x[2] for x in conflicts)
            if cost < total_conflict_cost:
                # Replace conflicting matches with the better one
                valid_matches = [x for x in valid_matches if x not in conflicts]
                valid_matches.append(cand)
                
    # Sort final matches by design index r
    valid_matches.sort(key=lambda x: x[0])

    matched_design_indices = {r for r, c, _ in valid_matches}
    matched_topo_indices = {c for r, c, _ in valid_matches}
    design_to_topo = {r: c for r, c, _ in valid_matches}

    # Process Matches
    for r in range(n_d):
        if r in matched_design_indices:
            c = design_to_topo[r]
            bd = benches_design[r]
            bt = benches_topo[c]

            height_dev = bt.bench_height - bd.bench_height
            angle_dev = bt.face_angle - bd.face_angle

            tol_h = tolerances['bench_height']
            tol_a = tolerances['face_angle']
            tol_b = tolerances['berm_width']

            min_berm = tol_b.get('min', 0.0)

            berm_real = round(bt.berm_width, 2)

            berm_complies = berm_real >= min_berm
            berm_status = "CUMPLE" if berm_complies else "NO CUMPLE"
            berm_score = 60 if berm_complies else 0

            angle_complies = abs(angle_dev) <= (tol_a['neg'] if angle_dev < 0 else tol_a['pos'])
            angle_status = _evaluate_status(angle_dev, tol_a['neg'], tol_a['pos'])
            angle_score = 10 if angle_complies else 0

            height_complies = abs(height_dev) <= (tol_h['neg'] if height_dev < 0 else tol_h['pos'])
            height_status = _evaluate_status(height_dev, tol_h['neg'], tol_h['pos'])
            height_score = 30 if height_complies else 0

            bench_score = berm_score + angle_score + height_score

            comparisons.append({
                'sector': params_design.sector,
                'section': params_design.section_name,
                'bench_num': bd.bench_number,
                'type': 'MATCH',
                'level': f"{bd.toe_elevation:.0f}",
                'height_design': round(bd.bench_height, 2),
                'height_real': round(bt.bench_height, 2),
                'height_dev': round(height_dev, 2),
                'height_status': height_status,
                'angle_design': round(bd.face_angle, 1),
                'angle_real': round(bt.face_angle, 1),
                'angle_dev': round(angle_dev, 1),
                'angle_status': angle_status,
                'berm_design': round(bd.berm_width, 2),
                'berm_real': berm_real,
                'berm_min': min_berm,
                'berm_status': berm_status,
                'spill_width': round(bt.spill_width, 2),
                'effective_berm': round(bt.effective_berm_width, 2),
                'delta_crest': round((bt.crest_distance - bd.crest_distance) * (1.0 if bd.crest_distance >= bd.toe_distance else -1.0), 2),
                'delta_toe': round((bt.toe_distance - bd.toe_distance) * (1.0 if bd.crest_distance >= bd.toe_distance else -1.0), 2),
                'bench_design': bd,
                'bench_real': bt,
                'berm_score': berm_score,
                'angle_score': angle_score,
                'height_score': height_score,
                'bench_score': bench_score,
            })
    
    # Process Unmatched Design (Missing Benches)
    for i in range(n_d):
        if i not in matched_design_indices:
            bd = benches_design[i]
            comparisons.append({
                'sector': params_design.sector,
                'section': params_design.section_name,
                'bench_num': bd.bench_number,
                'type': 'MISSING',
                'level': f"{bd.toe_elevation:.0f}",
                'height_design': round(bd.bench_height, 2),
                'height_real': None,
                'height_dev': None,
                'height_status': "NO CONSTRUIDO",
                'angle_design': round(bd.face_angle, 1),
                'angle_real': None,
                'angle_dev': None,
                'angle_status': "-",
                'berm_design': round(bd.berm_width, 2),
                'berm_real': None,
                'berm_min': None,
                'berm_status': "FALTA BANCO",
                'spill_width': None,
                'effective_berm': None,
                'delta_crest': None,
                'delta_toe': None,
                'bench_design': bd,
                'bench_real': None,
                'berm_score': 0,
                'angle_score': 0,
                'height_score': 0,
                'bench_score': 0,
            })
            
    # Process Unmatched Topo (Extra Benches)
    for j in range(n_t):
        if j not in matched_topo_indices:
            bt = benches_topo[j]
            comparisons.append({
                'sector': params_design.sector,
                'section': params_design.section_name,
                'bench_num': 999, # Placeholder
                'type': 'EXTRA',
                'level': f"{bt.toe_elevation:.0f}",
                'height_design': None,
                'height_real': round(bt.bench_height, 2),
                'height_dev': None,
                'height_status': "EXTRA",
                'angle_design': None,
                'angle_real': round(bt.face_angle, 1),
                'angle_dev': None,
                'angle_status': "-",
                'berm_design': None,
                'berm_real': round(bt.berm_width, 2),
                'berm_min': None,
                'berm_status': "BANCO ADICIONAL",
                'spill_width': round(bt.spill_width, 2),
                'effective_berm': round(bt.effective_berm_width, 2),
                'delta_crest': None,
                'delta_toe': None,
                'bench_design': None,
                'bench_real': bt,
                'berm_score': 0,
                'angle_score': 0,
                'height_score': 0,
                'bench_score': 0,
            })
            
    # Calculate section-level compliance score (average of MATCH bench scores)
    match_scores = [c['bench_score'] for c in comparisons if c['type'] == 'MATCH']
    section_score = round(sum(match_scores) / len(match_scores), 1) if match_scores else 0.0
    section_status = "CUMPLE" if section_score >= 70 else "NO CUMPLE"

    for c in comparisons:
        c['section_score'] = section_score
        c['section_status'] = section_status
            
    # Sort by Level (Descending) for display
    comparisons.sort(key=lambda x: float(x['level']) if x['level'].replace('.','',1).isdigit() else 0, reverse=True)
    
    return comparisons
