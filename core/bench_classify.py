"""Berm-classification helpers used by the parameter extractor.

Three operations live here:

* :func:`_compute_berm_widths_from_profile` — assigns each bench's
  ``berm_width`` from the horizontal distance between consecutive
  crest/toe pairs.
* :func:`_flat_segment_width` — measures the width of a near-flat
  sub-segment (used by the leading/trailing berm fallbacks).
* :func:`_apply_leading_berm` / :func:`_apply_trailing_berm` —
  detect the flat area before the first / after the last bench and
  assign its width to the corresponding bench, also flagging ramps
  when the width falls in the ramp-detection range.
"""

import math

import numpy as np

from core.blast_correlation import classify_berm_as_ramp
from core.config import DETECTION


def _extended_toe_point(b) -> tuple[float, float]:
    """Return ``(distance, elevation)`` of the extended toe of a bench.

    When the bench has a ``floor_elevation`` below its ``toe_elevation``, the
    face is prolonged at ``face_angle`` down to that floor and the returned
    point is where the prolongation ends. Otherwise the point is the toe
    itself. Distance and elevation always belong to the same point.
    """
    toe_distance = float(b.toe_distance)
    toe_elevation = float(b.toe_elevation)
    floor_elev = float(getattr(b, 'floor_elevation', 0.0))
    if 0 < floor_elev < toe_elevation:
        angle_rad = math.radians(float(b.face_angle))
        if angle_rad > 0.01:
            face_dir = 1.0 if b.toe_distance >= b.crest_distance else -1.0
            delta_d = ((toe_elevation - floor_elev) / math.tan(angle_rad)) * face_dir
            return toe_distance + delta_d, floor_elev
    return toe_distance, toe_elevation


def _extended_toe_distance(b) -> float:
    """Return the horizontal distance of the extended toe of a bench."""
    return _extended_toe_point(b)[0]


def _is_ramp(d_start: float, d_end: float, e_start: float, e_end: float,
             min_width: float = 6.0, max_slope_deg: float = 15.0) -> bool:
    """Return True when a segment is wide and gently sloped enough to be a ramp."""
    width = abs(d_end - d_start)
    if width < min_width:
        return False
    slope = abs(float(np.degrees(np.arctan2(e_end - e_start, width))))
    return slope < max_slope_deg


def _segment_is_ramp(d_start: float, d_end: float,
                     e_upper: float, e_lower: float, width: float) -> bool:
    """Classify the berm/ramp segment between two consecutive benches.

    ``e_upper`` is the elevation where the segment leaves the upper bench
    (its extended toe point) and ``e_lower`` the elevation where it reaches
    the crest of the lower bench.

    A segment is a ramp when it falls in the classic ramp width band
    (:func:`classify_berm_as_ramp`) OR when it is a genuinely descending
    gentle segment wide enough to be a ramp. The descent is signed
    (``e_upper - e_lower``): a ramp always goes down toward the lower
    bench, so a segment that rises toward it never passes this rule, and
    flat catch berms (toe of the upper bench ≈ crest of the lower bench)
    are not mislabelled as ramps.
    """
    if classify_berm_as_ramp(width):
        return True
    descent = e_upper - e_lower
    if descent > DETECTION.ramp_min_descent_m and _is_ramp(
            d_start, d_end, e_upper, e_lower,
            min_width=DETECTION.ramp_narrow_min_width,
            max_slope_deg=DETECTION.ramp_max_slope_deg):
        return True
    return False


def _ramp_segment_elevations(b_first, b_second) -> tuple[float, float]:
    """Return ``(e_upper, e_lower)`` of the segment between two benches.

    The upper bench is chosen by crest elevation, not by list order: the
    extractor emits benches in profile-distance order, which is top-down
    only when the profile descends with distance.
    """
    if float(b_second.crest_elevation) > float(b_first.crest_elevation):
        upper, lower = b_second, b_first
    else:
        upper, lower = b_first, b_second
    return _extended_toe_point(upper)[1], float(lower.crest_elevation)


def _compute_berm_widths_from_profile(
    benches, simplified, d_simp, e_simp,
    max_berm_width=50.0
):
    """Compute berm widths as the horizontal distance between toe and crest of adjacent benches.

    Geotechnically, the berm of a bench (e.g. Bench i) is the horizontal platform
    located in its UPPER part (at its crest), connecting it to the previous bench i-1.

    For Bench i >= 1:
      berm_width = abs(min(curr_crest, curr_toe) - max(prev_crest, prev_toe))

    The measurement uses the EXTENDED toe position of the current bench when
    the bench has a local ``floor_elevation`` below its toe (the face is
    prolonged at ``face_angle`` until the real terrain). This ensures the
    berm width reflects the real distance left between the extended face
    and the next crest, not the legacy idealised toe.
    """
    n_benches = len(benches)
    if n_benches == 0:
        return

    benches[0].berm_width = 0.0
    benches[0].effective_berm_width = 0.0
    benches[0].is_ramp = False
    benches[0].ramp_segment = False
    benches[0].group_break = False

    for i in range(n_benches - 1):
        b_curr = benches[i]
        b_next = benches[i + 1]

        # Usar el toe extendido del banco actual cuando exista piso local.
        # Esto reduce el ancho de berm porque la cara extendida se acerca
        # horizontalmente a la crest del banco siguiente.
        curr_toe_d = _extended_toe_distance(b_curr)
        curr_right = max(curr_toe_d, b_curr.crest_distance)
        next_left = min(b_next.toe_distance, b_next.crest_distance)

        width = float(abs(next_left - curr_right))
        b_next.berm_width = width
        b_next.effective_berm_width = float(max(width - b_curr.spill_width, 0.0))

        e_upper, e_lower = _ramp_segment_elevations(b_curr, b_next)
        is_ramp_seg = _segment_is_ramp(
            curr_right, next_left, e_upper, e_lower, width,
        )
        b_next.is_ramp = is_ramp_seg
        b_next.ramp_segment = is_ramp_seg

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
            first.ramp_segment = True


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
            last.ramp_segment = True
