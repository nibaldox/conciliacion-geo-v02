"""Design-guided measurement of as-built benches.

Measures every design bench directly against the raw as-built profile
(distances + elevations) without relying on the as-built segmentation or
the Hungarian matching. Each design bench is located on the as-built
profile via its design crest/toe elevation, so a bench that the matching
step reported as MISSING (design bench with no as-built pair) or that got
split into an EXTRA is still evaluated.

The sign convention of ``delta_crest``/``delta_toe`` matches
``core.profile_compliance._build_match_row`` exactly::

    delta = (asbuilt_d - design_d) * sign_dir
    sign_dir = 1.0 if design.crest_distance >= design.toe_distance else -1.0

The sign is orientation-dependent, not a fixed overbreak/underbreak label:
positive means the as-built corner sits farther along the design
crest->toe direction, which is the overbreak side for a face whose crest
precedes its toe and the underbreak side for a mirrored face.

An excavated bench whose as-built face is horizontally displaced (bench
offset) can leave the floor walk ending at the profile edge just short of
the toe. When the as-built segmentation contains a full bench at the
design elevations (crest within ``bench_offset_crest_tol_m``, toe within
``bench_offset_toe_tol_m``) with its crest shifted at least
``bench_offset_min_shift_m``, the solid-face fit is evaluated past the
profile end - bounded by ``bench_height + floor_search_margin_m`` and by
the next lower design bench's crest elevation - so the bench is measured
as excavated, with additive ``bench_offset`` / ``toe_extrapolated``
warnings, and the excavation-debt branch never fires for it.

The toe is measured as the **solid-face toe**: the solid face line of the
as-built bench (spill pile and flat berms excluded) is fitted with the very
same projection used by :func:`core.profile_simplify._detect_and_project_solid_toe`
and intersected with the local as-built floor when that floor sits above
the design toe elevation (a high floor would otherwise make a raw elevation
crossing slide along the nearly horizontal berm far from the face), or with
the design toe elevation when the as-built descends to it.
``floor_offset_m`` reports the vertical gap between the local floor and the
design toe (positive = high floor / vertical underexcavation).

A crest is only accepted on a face: the profile must descend steeper than
``face_threshold`` right below the crest candidate, so a crest can never
land on a horizontal berm.

The module is pure, deterministic and performs no I/O.
"""

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

STATUS_MEASURED = "measured"
STATUS_NO_CROSSING = "no_crossing"
STATUS_OUT_OF_PROFILE = "out_of_profile"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_INSUFFICIENT_POINTS = "insufficient_points"
STATUS_SECTION_TRUNCATED = "section_truncated"

BENCH_STATE_EXCAVATED = "excavated"
BENCH_STATE_NOT_EXCAVATED = "not_excavated"
BENCH_STATE_SECTION_TRUNCATED = "section_truncated"
BENCH_STATE_OUT_OF_PROFILE = "out_of_profile"
BENCH_STATE_AMBIGUOUS = "ambiguous"
BENCH_STATE_UNMEASURED = "unmeasured"


@dataclass(frozen=True)
class DesignGuidedDefaults:
    """Tunable knobs for the guided measurement.

    ``crossing_window_m`` bounds the horizontal search around the design
    crest when locating the matching as-built corner or crossing.
    ``ambiguous_window_m`` marks two candidate corners closer than this as
    a near-tie (``ambiguous``) instead of picking the nearest.
    ``crest_toe_elevation_tol_m`` is the vertical tolerance that decides
    whether an as-built corner sits at the design elevation; it is also the
    descent used by the steep-face guard below a crest.
    ``face_trim_fraction`` trims this fraction of the bench height off the
    top and bottom of the face before the solid-face least-squares fit.
    ``face_threshold`` is the minimum local slope (degrees) required below a
    crest for it to count as a face crest rather than a horizontal berm.
    ``berm_threshold`` is the maximum slope (degrees) treated as a flat
    floor when walking the face and locating the local floor.
    ``max_flat_run_m`` is the longest horizontal (or near-horizontal) run
    the face walk crosses (a hidden step inside a face); anything longer is
    the local floor and stops the walk, so the walk never crosses a catch
    berm into the next bench face. ``solid_trim_angle_deg`` is the slope
    below which trailing walked points are dropped from the solid-face fit
    (the spill pile), mirroring
    :attr:`core.config.DetectionDefaults.spill_angle_pile`.
    ``spill_angle_solid_deg`` mirrors ``spill_angle_solid``: the trailing
    gentle run is only dropped while a steeper-than-this segment remains
    earlier in the face, exactly like
    :func:`core.profile_simplify._detect_and_project_solid_toe`.
    ``not_excavated_tol_m`` / ``not_excavated_frac`` decide the
    ``not_excavated`` state: the as-built must sit more than one tolerance
    above the design bench line over at least this fraction of its span.
    ``edge_eps_m`` is how close a bench span may sit to the profile edge
    before it is considered cut by the section window.
    ``floor_below_tol_m`` is how far below the design toe elevation a
    detected local floor may sit before it is rejected (a floor that deep
    belongs to the next bench down, whose berm was removed).
    ``inclined_berm_max_slope_deg`` (~ ``berm_threshold`` + 5) is the
    steepest slope still accepted as a berm/landing when the rejected
    floor must be replaced by the nearest one above, and
    ``inclined_berm_min_run_m`` the shortest run that still counts
    (a narrow berm is a berm). ``berm_remnant_min_m`` is the smallest
    remnant thickness worth reporting in ``berm_remnant_max_m``.
    ``bench_offset_crest_tol_m`` / ``bench_offset_toe_tol_m`` decide the
    excavated-displaced (bench offset) signature: an as-built bench whose
    crest/toe elevations sit within these tolerances of the design
    bench's. ``bench_offset_min_shift_m`` is the smallest horizontal crest
    displacement that counts as displaced. ``floor_search_margin_m`` is
    how far below ``bench_height`` the toe search may reach past the
    profile end for a signature bench (the search is never cut at the
    section window; it stops at the next lower design bench's crest
    elevation instead). ``toe_tail_baseline_m`` is the walk length the
    toe-curve fallback extrapolates when the straight solid-face fit is
    inconsistent with the terrain cut by the window (the fit lands short
    of the observed toe curve).
    """

    crossing_window_m: float = 5.0
    ambiguous_window_m: float = 3.0
    crest_toe_elevation_tol_m: float = 2.0
    face_trim_fraction: float = 0.10
    min_face_points: int = 5
    floor_search_tol_m: float = 5.0
    face_threshold: float = 30.0
    berm_threshold: float = 10.0
    not_excavated_tol_m: float = 1.0
    not_excavated_frac: float = 0.8
    max_flat_run_m: float = 1.2
    solid_trim_angle_deg: float = 48.0
    spill_angle_solid_deg: float = 52.0
    noise_rise_tol_m: float = 0.10
    edge_eps_m: float = 0.5
    floor_below_tol_m: float = 1.0
    inclined_berm_max_slope_deg: float = 15.0
    inclined_berm_min_run_m: float = 0.5
    berm_remnant_min_m: float = 0.05
    bench_offset_crest_tol_m: float = 1.5
    bench_offset_toe_tol_m: float = 5.0
    bench_offset_min_shift_m: float = 1.0
    floor_search_margin_m: float = 2.0
    toe_tail_baseline_m: float = 1.0


DEFAULTS = DesignGuidedDefaults()


@dataclass(frozen=True)
class DesignGuidedBench:
    """Guided measurement of a single design bench against the as-built.

    Every magnitude carries a status; when it cannot be measured its value
    is ``None`` (never a silent zero). ``delta_crest``/``delta_toe`` inherit
    the status of their source ``crest_asbuilt_d``/``toe_asbuilt_d``.
    ``toe_asbuilt_d`` is the solid-face toe (spill excluded), not the raw
    elevation crossing. ``floor_offset_m`` is the local as-built floor
    minus the design toe elevation (positive = high floor).
    ``toe_extrapolated`` marks a toe recovered past the profile end (the
    floor walk was cut by the section window); such a toe never feeds the
    next lower bench's berm.
    """

    bench_number: int
    crest_design: tuple[float, float]
    toe_design: tuple[float, float]
    crest_asbuilt_d: float | None
    crest_asbuilt_status: str
    toe_asbuilt_d: float | None
    toe_asbuilt_status: str
    delta_crest: float | None
    delta_toe: float | None
    face_angle_asbuilt: float | None
    face_angle_status: str
    height_asbuilt: float | None
    height_status: str
    berm_asbuilt: float | None
    berm_status: str
    floor_offset_m: float | None
    floor_offset_status: str
    bench_state: str
    remaining_thickness_mean_m: float | None
    remaining_thickness_max_m: float | None
    berm_remnant_max_m: float | None = None
    berm_remnant_area_m2: float | None = None
    warnings: tuple[str, ...] = ()
    window_used_m: float = 0.0
    toe_extrapolated: bool = False


def _face_sign(crest_d: float, toe_d: float) -> float:
    return 1.0 if crest_d >= toe_d else -1.0


def _bench_offset_shift(
    bd,
    asbuilt_benches: Sequence | None,
    defaults: DesignGuidedDefaults,
) -> float | None:
    """Horizontal displacement of the as-built bench at the design elevations.

    A full as-built bench whose crest/toe elevations overlap the design
    bench's (within ``bench_offset_crest_tol_m`` /
    ``bench_offset_toe_tol_m``) and whose crest is displaced at least
    ``bench_offset_min_shift_m`` marks an excavated-but-displaced bench.
    Returns the smallest matching displacement, or ``None`` when no
    as-built bench overlaps (the signature needs ``asbuilt_benches``).
    """
    if not asbuilt_benches:
        return None
    best: float | None = None
    for tb in asbuilt_benches:
        if abs(float(tb.crest_elevation) - float(bd.crest_elevation)) > defaults.bench_offset_crest_tol_m:
            continue
        if abs(float(tb.toe_elevation) - float(bd.toe_elevation)) > defaults.bench_offset_toe_tol_m:
            continue
        shift = abs(float(tb.crest_distance) - float(bd.crest_distance))
        if shift >= defaults.bench_offset_min_shift_m and (best is None or shift < best):
            best = shift
    return best


def _edge_toe_reachable(
    pts: list[tuple[float, float]],
    design_toe_e: float,
    bench_height_m: float | None,
    lower_crest_e: float | None,
    offset_shift: float | None,
    floor_e: float | None,
    defaults: DesignGuidedDefaults,
) -> bool:
    """Whether the toe search may continue past the profile end.

    Only for an excavated-displaced bench (``offset_shift`` present) whose
    walk stopped at the profile edge either with a detected local floor
    (``floor_e``, the visible floor's flat run cut by the window) or still
    descending (trailing slope above ``berm_threshold`` — a floor longer
    than ``max_flat_run_m`` stops the walk as ``floor`` long before this)
    above the target elevation. The target (the design toe elevation,
    never below the next lower design bench's crest elevation) must stay
    within ``bench_height_m + floor_search_margin_m`` of the walked crest
    elevation; the fitted-face extension is bounded separately in
    :func:`_solid_toe_and_floor`.
    """
    if offset_shift is None or len(pts) < 2:
        return False
    last_z = float(pts[-1][1])
    if floor_e is None:
        if last_z <= design_toe_e:
            return False
        span = abs(float(pts[-1][0]) - float(pts[-2][0]))
        drop = abs(float(pts[-2][1]) - last_z)
        slope = math.degrees(math.atan2(drop, span)) if span > 1e-6 else 90.0
        if slope <= defaults.berm_threshold:
            return False
    if bench_height_m is None:
        return True
    target = design_toe_e if lower_crest_e is None else max(design_toe_e, float(lower_crest_e))
    depth = float(pts[0][1]) - target
    return depth <= float(bench_height_m) + defaults.floor_search_margin_m


def _tail_chord_toe(
    pts: list[tuple[float, float]],
    target_e: float,
    defaults: DesignGuidedDefaults,
) -> float:
    """Extrapolate the walked tail chord (toe curve cut by the window).

    Linear extension of the last ``toe_tail_baseline_m`` of the walk to
    ``target_e``: data-faithful continuation of the observed local slope
    when the straight solid-face fit lands inconsistent with the terrain
    (a convex toe curve bends away from the fit above the profile end).
    """
    end_d, end_z = float(pts[-1][0]), float(pts[-1][1])
    acc = 0.0
    k = len(pts) - 1
    while k > 0 and acc < defaults.toe_tail_baseline_m:
        acc += abs(float(pts[k][0]) - float(pts[k - 1][0]))
        k -= 1
    dz = end_z - float(pts[k][1])
    dd = end_d - float(pts[k][0])
    if abs(dz) <= 1e-9 or abs(dd) <= 1e-9:
        return end_d
    return end_d + (target_e - end_z) * (dd / dz)


def _signed_delta(asbuilt_d: float, design_d: float, sign_dir: float) -> float:
    return (asbuilt_d - design_d) * sign_dir


def _extrema(
    d: np.ndarray, e: np.ndarray, berm_threshold: float = 10.0, face_threshold: float = 30.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return crest and toe indices (local maxima / minima of the profile).

    A crest is a slope transition from ascending/flat to descending
    (left sign > right sign); a toe is the mirror. Flat berms produce
    exactly one crest and one toe corner each, which is what a face
    boundary requires. Additionally, a slope-magnitude transition between a
    gentle run (``<= berm_threshold``, e.g. a berma with drainage grade)
    and a steep face segment (``> face_threshold``) is a corner too: the
    gentle-to-steep-descending kink is a crest, the descending-to-gentle
    kink a toe.
    """
    n = len(d)
    if n < 2:
        return np.array([], dtype=int), np.array([], dtype=int)
    ds = np.diff(e)
    s = np.where(ds > 0, 1, np.where(ds < 0, -1, 0)).astype(int)
    crests: list[int] = []
    toes: list[int] = []
    for i in range(1, n - 1):
        left, right = s[i - 1], s[i]
        if left > right:
            crests.append(i)
        elif left < right:
            toes.append(i)
    if s[0] < 0:
        crests.append(0)
    elif s[0] > 0:
        toes.append(0)
    if s[-1] < 0:
        toes.append(n - 1)
    elif s[-1] > 0:
        crests.append(n - 1)
    dx = np.abs(np.diff(d))
    dy = np.abs(ds)
    ang = np.zeros(len(ds))
    valid = dx > 1e-6
    ang[valid] = np.degrees(np.arctan2(dy[valid], dx[valid]))
    ang[~valid] = 90.0
    for i in range(1, n - 1):
        gentle_prev = ang[i - 1] <= berm_threshold
        gentle_next = ang[i] <= berm_threshold
        steep_prev = ang[i - 1] > face_threshold
        steep_next = ang[i] > face_threshold
        descending = ds[i] < 0
        if gentle_prev and steep_next and descending:
            crests.append(i)
        elif steep_prev and gentle_next and descending:
            toes.append(i)
    return (
        np.array(sorted(set(crests)), dtype=int),
        np.array(sorted(set(toes)), dtype=int),
    )


def _elevation_crossings(d: np.ndarray, e: np.ndarray, z: float) -> np.ndarray:
    """Interior crossings of a horizontal line ``z`` through the profile."""
    out: list[float] = []
    n = len(d)
    for i in range(n - 1):
        z0, z1 = e[i], e[i + 1]
        if z0 == z1:
            continue
        lo, hi = min(z0, z1), max(z0, z1)
        if lo < z < hi:
            t = (z - z0) / (z1 - z0)
            out.append(d[i] + t * (d[i + 1] - d[i]))
    if not out:
        return np.array([], dtype=float)
    arr = np.array(sorted(out), dtype=float)
    return arr


def _pick_nearest(
    candidates: np.ndarray, ref: float, ambiguous_window: float,
) -> tuple[float | None, str]:
    if candidates.size == 0:
        return None, STATUS_NO_CROSSING
    dist = np.abs(candidates - ref)
    order = np.argsort(dist)
    nearest = float(candidates[order[0]])
    if candidates.size >= 2 and abs(float(candidates[order[1]]) - nearest) <= ambiguous_window:
        return None, STATUS_AMBIGUOUS
    return nearest, STATUS_MEASURED


def _face_slope_below_ok(
    d: np.ndarray, e: np.ndarray, crest_d: float, face_dir: float,
    defaults: DesignGuidedDefaults,
) -> bool:
    """Whether a steep face exists immediately below a crest candidate.

    The profile must descend by ``crest_toe_elevation_tol_m`` below the
    candidate without rising more than ``noise_rise_tol_m``, and the local
    slope over that descent must exceed ``face_threshold``; otherwise the
    candidate sits on a horizontal berm and is not a face crest.
    """
    idx = int(np.argmin(np.abs(d - crest_d)))
    n = len(d)
    step = 1 if face_dir > 0 else -1
    start_e = float(e[idx])
    i = idx
    while 0 <= i < n - 1:
        ni = i + step
        if ni < 0 or ni >= n:
            return False
        eni = float(e[ni])
        if eni > float(e[i]) + defaults.noise_rise_tol_m:
            return False
        if start_e - eni >= defaults.crest_toe_elevation_tol_m:
            span = abs(float(d[ni] - d[idx]))
            if span <= 1e-6:
                return False
            slope = math.degrees(math.atan2(abs(float(start_e - eni)), span))
            return slope > defaults.face_threshold
        i = ni
    return False


def _locate_crest(
    d: np.ndarray,
    e: np.ndarray,
    crest_idx: np.ndarray,
    ref_d: float,
    ref_z: float,
    face_dir: float,
    defaults: DesignGuidedDefaults,
) -> tuple[float | None, str]:
    """Locate the as-built crest with a steep-face guard.

    Only interior crest corners (or elevation crossings) that lie inside the
    search window, within the elevation tolerance of the design crest, and
    with a steep face below them are eligible, so the crest can never land
    on a horizontal berm nor on the section edge. When nothing eligible is
    found at the base window the search retries once with a four-times
    wider window (a crest displaced by several metres of overbreak).
    """
    n = len(d)
    interior = crest_idx[(crest_idx > 0) & (crest_idx < n - 1)]
    for window in (defaults.crossing_window_m, 4.0 * defaults.crossing_window_m):
        guarded: list[float] = []
        if interior.size:
            cd = d[interior]
            ce = e[interior]
            mask = (
                (np.abs(cd - ref_d) <= window)
                & (np.abs(ce - ref_z) <= defaults.crest_toe_elevation_tol_m)
            )
            for cand in cd[mask]:
                if _face_slope_below_ok(d, e, float(cand), face_dir, defaults):
                    guarded.append(float(cand))
        if guarded:
            return _pick_nearest(np.array(sorted(guarded)), ref_d, defaults.ambiguous_window_m)
        crossings = _elevation_crossings(d, e, ref_z)
        if crossings.size:
            crossings = crossings[np.abs(crossings - ref_d) <= window]
            for cand in crossings:
                if _face_slope_below_ok(d, e, float(cand), face_dir, defaults):
                    guarded.append(float(cand))
        if guarded:
            return _pick_nearest(np.array(sorted(guarded)), ref_d, defaults.ambiguous_window_m)
    if ref_z > float(np.max(e)) or ref_z < float(np.min(e)):
        return None, STATUS_OUT_OF_PROFILE
    return None, STATUS_NO_CROSSING


def _crest_elevation(
    d: np.ndarray,
    e: np.ndarray,
    crest_asbuilt_d: float | None,
    face_dir: float,
    defaults: DesignGuidedDefaults,
) -> tuple[float | None, str]:
    """Elevation of the top edge of the last steep segment of the face.

    Walks upstream (away from the face) from the located crest while the
    segments are steeper than ``face_threshold``; the crest elevation is
    where that steep run ends (its top edge), never the maximum of the
    profile around the crest (that maximum is the upper bench floor and
    would inflate the bench height). When the first upstream segment is
    already gentle the located point itself already sits at/above the face
    top and its own elevation is used. With no steep segment identifiable
    on either side the crest elevation is ``ambiguous`` (``None``), never
    an arbitrary maximum. The walk is capped at four times
    ``crossing_window_m``.
    """
    if crest_asbuilt_d is None:
        return None, STATUS_NO_CROSSING
    n = len(d)
    i = int(np.argmin(np.abs(d - crest_asbuilt_d)))
    up = -1 if face_dir > 0 else 1
    z_top = float(e[i])
    steep_seen = False
    walked = 0.0
    j = i
    while 0 <= j + up < n and walked < 4.0 * defaults.crossing_window_m:
        span = abs(float(d[j + up] - d[j]))
        drop = abs(float(e[j + up] - e[j]))
        slope = math.degrees(math.atan2(drop, span)) if span > 1e-6 else 90.0
        if slope <= defaults.face_threshold:
            break
        steep_seen = True
        z_top = float(e[j + up])
        j += up
        walked += span
    if not steep_seen:
        down = -up
        k = i
        walked_down = 0.0
        while 0 <= k + down < n and walked_down < 4.0 * defaults.crossing_window_m:
            span = abs(float(d[k + down] - d[k]))
            drop = abs(float(e[k + down] - e[k]))
            slope = math.degrees(math.atan2(drop, span)) if span > 1e-6 else 90.0
            if slope > defaults.face_threshold:
                break
            walked_down += span
            k += down
        else:
            return None, STATUS_AMBIGUOUS
    return z_top, STATUS_MEASURED


def _nearest_berm_above(
    d: np.ndarray,
    e: np.ndarray,
    from_d: float,
    up: int,
    min_z: float,
    max_z: float,
    defaults: DesignGuidedDefaults,
) -> float | None:
    """Median elevation of the nearest berm/landing at or above ``min_z``.

    Walks upstream from ``from_d`` collecting consecutive segments no
    steeper than ``inclined_berm_max_slope_deg``; a run at least
    ``inclined_berm_min_run_m`` long whose median elevation lies in
    ``[min_z, max_z]`` is the replacement floor of a bench whose detected
    floor fell through into the next bench down. The search stops once the
    profile rises above ``max_z`` (anything higher belongs to the face or
    the upper bench, not to this bench's berm).
    """
    n = len(d)
    i = int(np.argmin(np.abs(d - from_d)))
    run_e: list[float] = []
    run_len = 0.0
    while 0 <= i + up < n:
        if float(e[i]) > max_z:
            break
        span = abs(float(d[i + up] - d[i]))
        drop = abs(float(e[i + up] - e[i]))
        slope = math.degrees(math.atan2(drop, span)) if span > 1e-6 else 90.0
        if slope <= defaults.inclined_berm_max_slope_deg:
            run_e.append(float(e[i + up]))
            run_len += span
            if run_len >= defaults.inclined_berm_min_run_m:
                median = float(np.median(run_e))
                if min_z <= median <= max_z:
                    return median
                run_e = []
                run_len = 0.0
        else:
            run_e = []
            run_len = 0.0
        i += up
    return None


def _walk_face(
    d: np.ndarray,
    e: np.ndarray,
    start_d: float,
    step: int,
    design_toe_e: float,
    defaults: DesignGuidedDefaults,
) -> tuple[list[tuple[float, float]], str]:
    """Walk the as-built face from a crest down to its local floor.

    Returns the walked points (crest first, descending) plus the stop
    reason: ``design_toe`` (the face reached the design toe elevation),
    ``floor`` (a horizontal run longer than ``max_flat_run_m`` — the local
    floor), ``edge`` (the profile ended while still on a steep face) or
    ``rise``. A short flat step inside the face is crossed; a catch berm is
    not, so the walk never leaks into the next bench face. Gentle (spill)
    runs are walked through and only excluded later from the solid fit by
    ``solid_trim_angle_deg``.
    """
    n = len(d)
    i = int(np.argmin(np.abs(d - start_d)))
    pts: list[tuple[float, float]] = [(float(d[i]), float(e[i]))]
    flat_run = 0.0
    while 0 <= i < n - 1:
        ni = i + step
        if ni < 0 or ni >= n:
            return pts, "edge"
        z0, z1 = float(e[i]), float(e[ni])
        d0, d1 = float(d[i]), float(d[ni])
        if z1 > z0 + defaults.noise_rise_tol_m:
            return pts, "rise"
        if z1 <= design_toe_e:
            if abs(z1 - z0) <= 1e-9:
                dc = d1
            else:
                t = (design_toe_e - z0) / (z1 - z0)
                dc = d0 + t * (d1 - d0)
            if abs(dc - d0) > 1e-9:
                pts.append((dc, design_toe_e))
            else:
                pts.append((d1, z1))
            return pts, "design_toe"
        seg_span = abs(d1 - d0)
        seg_drop = abs(z0 - z1)
        seg_slope = math.degrees(math.atan2(seg_drop, seg_span)) if seg_span > 1e-6 else 90.0
        if seg_slope <= defaults.berm_threshold:
            flat_run += seg_span
            if flat_run > defaults.max_flat_run_m:
                return pts, "floor"
        else:
            flat_run = 0.0
        pts.append((d1, z1))
        i = ni
    return pts, "edge"


def _trailing_flat_median(
    pts: list[tuple[float, float]], berm_threshold: float,
) -> float | None:
    """Median elevation of the trailing flat run of a walked face."""
    if len(pts) < 2:
        return None
    elevs: list[float] = []
    for k in range(len(pts) - 1, 0, -1):
        d0, z0 = pts[k - 1]
        d1, z1 = pts[k]
        span = abs(d1 - d0)
        if span <= 1e-6:
            break
        slope = math.degrees(math.atan2(abs(z1 - z0), span))
        if slope <= berm_threshold:
            elevs.append(z1)
        else:
            break
    if not elevs:
        return None
    return float(np.median(elevs))


def _floor_after(
    d: np.ndarray,
    e: np.ndarray,
    from_d: float,
    step: int,
    defaults: DesignGuidedDefaults,
) -> float | None:
    """Median elevation of the flat run that follows a distance, if any.

    Any steep descent still remaining right after ``from_d`` (up to
    ``floor_search_tol_m`` vertically) is skipped first, so the floor is
    found even when the face crosses the design toe mid-segment.
    """
    n = len(d)
    i = int(np.argmin(np.abs(d - from_d)))
    start_e = float(e[i])
    while 0 <= i < n - 1:
        ni = i + step
        if ni < 0 or ni >= n:
            break
        span = abs(float(d[ni] - d[i]))
        drop = abs(float(e[ni] - e[i]))
        slope = math.degrees(math.atan2(drop, span)) if span > 1e-6 else 0.0
        if slope <= defaults.berm_threshold:
            break
        if start_e - float(e[ni]) > defaults.floor_search_tol_m:
            return None
        i = ni
    elevs: list[float] = []
    while 0 <= i < n - 1:
        ni = i + step
        if ni < 0 or ni >= n:
            break
        span = abs(float(d[ni] - d[i]))
        drop = abs(float(e[ni] - e[i]))
        slope = math.degrees(math.atan2(drop, span)) if span > 1e-6 else 0.0
        if slope > defaults.berm_threshold:
            break
        elevs.append(float(e[ni]))
        i = ni
        if len(elevs) > 400:
            break
    if not elevs:
        return None
    return float(np.median(elevs))


def _solid_toe_and_floor(
    d: np.ndarray,
    e: np.ndarray,
    crest_asbuilt_d: float,
    design_toe_e: float,
    face_dir: float,
    defaults: DesignGuidedDefaults,
    *,
    bench_height_m: float | None = None,
    lower_crest_e: float | None = None,
    offset_shift: float | None = None,
) -> tuple[
    float | None, str, float | None, str, float | None, np.ndarray, float | None,
    list[str], bool, bool,
]:
    """Measure the solid-face toe and the local floor under a bench.

    Walks the as-built face from the crest down to the local floor or the
    design toe elevation, drops the trailing spill/flats, fits the solid
    face line with the same least-squares projection used by
    :func:`core.profile_simplify._detect_and_project_solid_toe` and
    evaluates it at the local floor elevation when that floor sits above
    the design toe, or at the design toe elevation otherwise.

    When the walk ends at the profile edge while still on a steep face and
    ``offset_shift`` marks an excavated-displaced bench, the solid-face
    fit is evaluated past the profile end instead of returning
    ``section_truncated``: the search goes down to the design toe
    elevation (never below the next lower design bench's crest elevation
    ``lower_crest_e``) and the total depth from the walked crest stays
    within ``bench_height_m + floor_search_margin_m``; the extrapolated
    stretch must remain at least face-steep. ``floor_offset_m`` stays
    unmeasured for a toe beyond the profile (nothing is interpolated past
    the data).

    A detected floor more than ``floor_below_tol_m`` below the design toe
    elevation is rejected: it belongs to the next bench down (a removed
    berm leaves a double-height front), never to this bench. The nearest
    berm/landing above (narrow or inclined up to
    ``inclined_berm_max_slope_deg``) replaces it; without one the design
    toe elevation is used and ``floor_below_design`` is warned. When no
    horizontal floor exists at all but as-built material sits above the
    design toe at the solid toe, ``floor_offset_m`` reports that thickness
    (an inclined remnant on the berm) with the ``incline_berm`` warning —
    the height itself stays measured against the design toe elevation.

    Returns ``(toe_d, toe_status, floor_offset, floor_offset_status,
    floor_e, face_pts, height_ref, floor_warnings, incline_berm,
    toe_extrapolated)`` where ``height_ref`` is the elevation the bench
    height is measured against (the accepted floor, never below the design
    toe) and ``toe_extrapolated`` flags a toe recovered past the profile
    end for the caller's berm chaining.
    """
    n = len(d)
    empty = np.array([])
    if n < 2:
        return (
            None, STATUS_OUT_OF_PROFILE, None, STATUS_OUT_OF_PROFILE, None,
            empty, None, [], False, False,
        )
    step = 1 if face_dir > 0 else -1
    pts, mode = _walk_face(
        d, e, crest_asbuilt_d, step, design_toe_e, defaults,
    )
    if len(pts) < 2:
        return (
            None, STATUS_NO_CROSSING, None, STATUS_NO_CROSSING, None,
            np.array(pts), None, [], False, False,
        )

    floor_warnings: list[str] = []
    floor_rejected = False
    floor_e = _trailing_flat_median(pts, defaults.berm_threshold)
    if floor_e is None and mode in ("design_toe", "floor"):
        floor_e = _floor_after(d, e, pts[-1][0], step, defaults)
    if floor_e is not None and floor_e < design_toe_e - defaults.floor_below_tol_m:
        berm_e = _nearest_berm_above(
            d, e, pts[-1][0], -step,
            design_toe_e - defaults.floor_below_tol_m,
            design_toe_e + defaults.floor_below_tol_m,
            defaults,
        )
        if berm_e is not None:
            floor_e = berm_e
        else:
            floor_e = None
            floor_rejected = True
            floor_warnings.append("floor_below_design")
    floor_offset = None if floor_e is None else float(floor_e - design_toe_e)
    floor_status = STATUS_MEASURED if floor_e is not None else STATUS_NO_CROSSING

    extrapolated = False
    if mode == "edge":
        if not _edge_toe_reachable(
            pts, design_toe_e, bench_height_m, lower_crest_e, offset_shift,
            floor_e, defaults,
        ):
            return (
                None, STATUS_SECTION_TRUNCATED, floor_offset, floor_status, floor_e,
                np.array(pts), floor_e, floor_warnings, False, False,
            )
        extrapolated = True
    if mode == "rise":
        return (
            None, STATUS_NO_CROSSING, floor_offset, floor_status, floor_e,
            np.array(pts), floor_e, floor_warnings, False, False,
        )

    solid = list(pts)
    while len(solid) > 2:
        d0, z0 = solid[-2]
        d1, z1 = solid[-1]
        span = abs(d1 - d0)
        if span <= 1e-6:
            break
        slope = math.degrees(math.atan2(abs(z1 - z0), span))
        if slope <= defaults.berm_threshold:
            solid.pop()
            continue
        has_solid_steeper = False
        for k in range(len(solid) - 2):
            s0, z0k = solid[k]
            s1, z1k = solid[k + 1]
            sp = abs(s1 - s0)
            if sp <= 1e-6:
                has_solid_steeper = True
                break
            sl = math.degrees(math.atan2(abs(z1k - z0k), sp))
            if sl > defaults.spill_angle_solid_deg:
                has_solid_steeper = True
                break
        if slope < defaults.solid_trim_angle_deg and has_solid_steeper:
            solid.pop()
        else:
            break
    face_arr = np.array(solid, dtype=float)
    if len(face_arr) < 2 or float(np.max(face_arr[:, 1]) - np.min(face_arr[:, 1])) <= 0.5:
        return (
            None, STATUS_NO_CROSSING, None, STATUS_NO_CROSSING, None,
            np.array(pts), floor_e, floor_warnings, False, False,
        )

    target_e = design_toe_e if floor_e is None else max(floor_e, design_toe_e)
    if extrapolated and lower_crest_e is not None:
        target_e = max(target_e, float(lower_crest_e))
    solid_z = face_arr[:, 1]
    solid_d = face_arr[:, 0]
    toe_d: float | None
    if float(np.var(solid_z)) <= 1e-4:
        toe_d = float(solid_d[-1])
    else:
        poly = np.polyfit(solid_z, solid_d, 1)
        toe_d = float(poly[0] * target_e + poly[1])
        if extrapolated:
            depth_remaining = float(pts[-1][1]) - target_e
            max_extension = (
                depth_remaining / math.tan(math.radians(defaults.face_threshold))
                if depth_remaining > 0.0 else 0.0
            )
            if (
                not np.isfinite(toe_d)
                or abs(toe_d - float(pts[-1][0])) > max_extension + defaults.noise_rise_tol_m
            ):
                max_extension_tail = (
                    depth_remaining / math.tan(math.radians(defaults.berm_threshold))
                    if depth_remaining > 0.0 else 0.0
                )
                toe_d = _tail_chord_toe(pts, target_e, defaults)
                if (
                    not np.isfinite(toe_d)
                    or abs(toe_d - float(pts[-1][0])) > max_extension_tail + defaults.noise_rise_tol_m
                ):
                    return (
                        None, STATUS_SECTION_TRUNCATED, floor_offset, floor_status, floor_e,
                        np.array(pts), floor_e, floor_warnings, False, False,
                    )
        else:
            walked_lo = min(pts[0][0], pts[-1][0])
            walked_hi = max(pts[0][0], pts[-1][0])
            toe_d = float(np.clip(toe_d, walked_lo, walked_hi))
    if not np.isfinite(toe_d):
        return (
            None, STATUS_NO_CROSSING, floor_offset, floor_status, floor_e,
            np.array(pts), floor_e, floor_warnings, False, False,
        )

    incline_berm = False
    if (
        floor_e is None and not floor_rejected
        and float(d[0]) <= toe_d <= float(d[-1])
    ):
        z_at_toe = float(np.interp(toe_d, d, e))
        if z_at_toe - design_toe_e > defaults.noise_rise_tol_m:
            floor_offset = float(z_at_toe - design_toe_e)
            floor_status = STATUS_MEASURED
            floor_warnings.append("incline_berm")
            incline_berm = True

    height_ref = design_toe_e if floor_e is None else float(max(floor_e, design_toe_e))
    if extrapolated and target_e > height_ref:
        height_ref = float(target_e)
    if extrapolated:
        floor_warnings.append("toe_extrapolated")
    return (
        toe_d, STATUS_MEASURED, floor_offset, floor_status, floor_e,
        np.array(pts), height_ref, floor_warnings, incline_berm, extrapolated,
    )


def _measure_face_angle(
    face_pts: np.ndarray,
    crest_e: float,
    floor_e: float,
    defaults: DesignGuidedDefaults,
) -> tuple[float | None, str]:
    """Least-squares face angle over the walked solid face, trimmed."""
    if face_pts is None or len(face_pts) < 2 or floor_e is None:
        return None, STATUS_INSUFFICIENT_POINTS
    height = crest_e - floor_e
    if height <= 0:
        return None, STATUS_INSUFFICIENT_POINTS
    frac = defaults.face_trim_fraction
    lo = floor_e + frac * height
    hi = crest_e - frac * height
    mask = (face_pts[:, 1] >= lo) & (face_pts[:, 1] <= hi)
    pts = face_pts[mask]
    if len(pts) < defaults.min_face_points:
        pts = face_pts
    if len(pts) < defaults.min_face_points:
        return None, STATUS_INSUFFICIENT_POINTS
    a = np.column_stack([pts[:, 0], np.ones(len(pts))])
    slope, _ = np.linalg.lstsq(a, pts[:, 1], rcond=None)[0]
    angle = math.degrees(math.atan(abs(float(slope))))
    return float(min(90.0, max(0.0, angle))), STATUS_MEASURED


def _classify_bench_state(
    d: np.ndarray,
    e: np.ndarray,
    bd,
    crest_status: str,
    toe_status: str,
    defaults: DesignGuidedDefaults,
    *,
    offset_shift: float | None = None,
) -> tuple[str, float | None, float | None]:
    """Classify a design bench that lacks a complete measurement.

    Returns ``(state, remaining_mean, remaining_max)``. A bench whose
    horizontal span is cut by (or reaches) the section edge, or is not
    covered by the profile, is ``section_truncated`` — the window hides
    part of the bench, so no measurement of it can be complete. A bench
    with both crest and toe measured (away from the edges) is
    ``excavated``. A bench where the as-built exists across its span and
    sits more than one tolerance above the design bench line over at least
    ``not_excavated_frac`` of it is ``not_excavated`` (mean and max
    remaining thickness reported) — unless ``offset_shift`` marks an
    excavated-displaced bench: a full as-built bench exists at the design
    elevations, so the rock above the design line is displacement, not
    missing excavation, and no debt is reported (the state falls through to
    ``out_of_profile`` when the toe stays unmeasured). When the failure to
    measure came from tied corners the state is ``ambiguous``; everything
    else is ``out_of_profile``.
    """
    d_lo = min(float(bd.crest_distance), float(bd.toe_distance))
    d_hi = max(float(bd.crest_distance), float(bd.toe_distance))
    profile_lo = float(d[0])
    profile_hi = float(d[-1])
    eps = defaults.edge_eps_m
    if d_lo <= profile_lo + eps or d_hi >= profile_hi - eps:
        return BENCH_STATE_SECTION_TRUNCATED, None, None

    if crest_status == STATUS_MEASURED and toe_status == STATUS_MEASURED:
        return BENCH_STATE_EXCAVATED, None, None

    mask = (d >= d_lo) & (d <= d_hi)
    if not np.any(mask):
        return BENCH_STATE_SECTION_TRUNCATED, None, None

    d_span = d[mask]
    e_span = e[mask]
    span = d_hi - d_lo
    if span > 1e-6:
        frac = (d_span - d_lo) / span
        design_e = float(bd.crest_elevation) + frac * (float(bd.toe_elevation) - float(bd.crest_elevation))
    else:
        design_e = np.full_like(e_span, float(bd.crest_elevation))
    remaining = e_span - design_e

    above = remaining > defaults.not_excavated_tol_m
    if offset_shift is None and float(np.mean(above)) >= defaults.not_excavated_frac:
        return (
            BENCH_STATE_NOT_EXCAVATED,
            float(np.mean(remaining)),
            float(np.max(remaining)),
        )

    if crest_status == STATUS_AMBIGUOUS or toe_status == STATUS_AMBIGUOUS:
        return BENCH_STATE_AMBIGUOUS, None, None
    return BENCH_STATE_OUT_OF_PROFILE, None, None


def excavation_debt_area(
    design_crest: tuple[float, float],
    design_toe: tuple[float, float],
    asbuilt_distances,
    asbuilt_elevations,
) -> float | None:
    """Section-plane area (m2) of as-built material above a design bench line.

    Integrates (trapezoids) ``max(asbuilt - design, 0)`` over the design
    bench's horizontal span ``[min(crest_d, toe_d), max(crest_d, toe_d)]``,
    with the design line interpolated linearly between ``design_crest`` and
    ``design_toe`` (the same line ``_classify_bench_state`` compares
    against). Negative gaps (as-built below the design line) are clamped to
    zero: the debt can never be negative. Returns ``None`` when the span is
    degenerate or not covered at all by the as-built profile. Pure.
    """
    d = np.asarray(asbuilt_distances, dtype=float)
    e = np.asarray(asbuilt_elevations, dtype=float)
    dc, zc = float(design_crest[0]), float(design_crest[1])
    dt, zt = float(design_toe[0]), float(design_toe[1])
    d_lo, d_hi = min(dc, dt), max(dc, dt)
    if d.size < 2 or d_hi - d_lo <= 1e-9:
        return None
    mask = (d >= d_lo) & (d <= d_hi)
    if not np.any(mask):
        return None
    ds = list(d[mask])
    if d_lo >= float(d[0]) and d_lo <= float(d[-1]):
        ds.append(d_lo)
    if d_hi >= float(d[0]) and d_hi <= float(d[-1]):
        ds.append(d_hi)
    ds = np.array(sorted(set(ds)), dtype=float)
    es = np.interp(ds, d, e)
    frac = (ds - dc) / (dt - dc) if abs(dt - dc) > 1e-9 else np.zeros_like(ds)
    design_e = zc + frac * (zt - zc)
    remaining = np.clip(es - design_e, 0.0, None)
    return float(np.trapezoid(remaining, ds))


def _berm_remnant(
    design_toe: tuple[float, float],
    next_crest_d: float | None,
    asbuilt_distances,
    asbuilt_elevations,
    min_m: float,
) -> tuple[float | None, float | None]:
    """Max thickness (m) and section-plane area (m2) of the berm remnant.

    Material of the as-built profile above the design berm elevation (the
    design toe elevation) inside the design berm width (from this bench's
    design toe to the next lower bench's design crest): the inclined wedge
    a blast leaves resting on the catch berm against the face. Returns
    ``(None, None)`` when the span is degenerate, not covered by the
    profile, or nothing meaningful sits above the berm elevation.
    """
    if next_crest_d is None:
        return None, None
    d = np.asarray(asbuilt_distances, dtype=float)
    e = np.asarray(asbuilt_elevations, dtype=float)
    lo = min(float(design_toe[0]), float(next_crest_d))
    hi = max(float(design_toe[0]), float(next_crest_d))
    if d.size < 2 or hi - lo <= 1e-9:
        return None, None
    mask = (d >= lo) & (d <= hi)
    if not np.any(mask):
        return None, None
    ds = list(d[mask])
    ds.extend(x for x in (lo, hi) if float(d[0]) <= x <= float(d[-1]))
    ds_arr = np.array(sorted(set(ds)), dtype=float)
    es = np.interp(ds_arr, d, e)
    above = es - float(design_toe[1])
    max_m = float(np.max(above))
    if max_m < min_m:
        return None, None
    area_m2 = float(np.trapezoid(np.clip(above, 0.0, None), ds_arr))
    return max_m, area_m2


def measure_design_benches(
    design_benches: Sequence,
    asbuilt_distances,
    asbuilt_elevations,
    *,
    defaults: DesignGuidedDefaults = DEFAULTS,
    asbuilt_benches: Sequence | None = None,
) -> list[DesignGuidedBench]:
    """Measure every design bench against the raw as-built profile.

    ``design_benches`` are :class:`core.profile_extract.BenchParams`
    objects; they are processed top-to-bottom (descending crest elevation)
    so the berm of a lower bench can reuse the upper bench's solid toe.
    ``asbuilt_benches`` optionally carries the as-built segmentation (the
    topo profile's ``BenchParams``); it enables the excavated-displaced
    (bench offset) signature and, with it, the toe recovery past the
    profile end and the ``bench_offset`` warning. ``None`` (default)
    keeps the plain walk behaviour.

    Returns one :class:`DesignGuidedBench` per design bench, in the same
    top-to-bottom order. Pure and deterministic.
    """
    d = np.asarray(asbuilt_distances, dtype=float)
    e = np.asarray(asbuilt_elevations, dtype=float)
    results: list[DesignGuidedBench] = []

    def empty_bench(bd, status: str, warnings: tuple[str, ...] = ()) -> DesignGuidedBench:
        return DesignGuidedBench(
            bench_number=bd.bench_number,
            crest_design=(float(bd.crest_distance), float(bd.crest_elevation)),
            toe_design=(float(bd.toe_distance), float(bd.toe_elevation)),
            crest_asbuilt_d=None,
            crest_asbuilt_status=status,
            toe_asbuilt_d=None,
            toe_asbuilt_status=status,
            delta_crest=None,
            delta_toe=None,
            face_angle_asbuilt=None,
            face_angle_status=status,
            height_asbuilt=None,
            height_status=status,
            berm_asbuilt=None,
            berm_status=status,
            floor_offset_m=None,
            floor_offset_status=status,
            bench_state=BENCH_STATE_UNMEASURED,
            remaining_thickness_mean_m=None,
            remaining_thickness_max_m=None,
            warnings=warnings,
            window_used_m=defaults.crossing_window_m,
        )

    if not design_benches:
        return results
    if d.size != e.size or d.size < 2 or not np.all(np.isfinite(d)) or not np.all(np.isfinite(e)):
        for bd in design_benches:
            results.append(empty_bench(bd, STATUS_OUT_OF_PROFILE, ("insufficient as-built profile",)))
        return results

    crest_idx, toe_idx = _extrema(d, e)
    ordered = sorted(design_benches, key=lambda b: -float(b.crest_elevation))

    prev_bench: DesignGuidedBench | None = None
    for bi, bd in enumerate(ordered):
        crest_design = (float(bd.crest_distance), float(bd.crest_elevation))
        toe_design = (float(bd.toe_distance), float(bd.toe_elevation))
        sign_dir = _face_sign(crest_design[0], toe_design[0])
        face_dir = 1.0 if toe_design[0] >= crest_design[0] else -1.0

        crest_asbuilt_d, crest_status = _locate_crest(
            d, e, crest_idx, crest_design[0], crest_design[1], face_dir, defaults,
        )
        offset_shift = _bench_offset_shift(bd, asbuilt_benches, defaults)
        (
            toe_asbuilt_d, toe_status, floor_offset, floor_offset_status,
            floor_e, face_pts, height_ref, floor_warnings, incline_berm,
            toe_extrapolated,
        ) = _solid_toe_and_floor(
            d, e,
            crest_asbuilt_d if crest_asbuilt_d is not None else crest_design[0],
            toe_design[1], face_dir, defaults,
            bench_height_m=abs(float(bd.crest_elevation) - float(bd.toe_elevation)),
            lower_crest_e=(
                float(ordered[bi + 1].crest_elevation)
                if bi + 1 < len(ordered) else None
            ),
            offset_shift=offset_shift,
        )

        delta_crest = (
            _signed_delta(crest_asbuilt_d, crest_design[0], sign_dir)
            if crest_asbuilt_d is not None else None
        )
        delta_toe = (
            _signed_delta(toe_asbuilt_d, toe_design[0], sign_dir)
            if toe_asbuilt_d is not None else None
        )

        z_crest: float | None = None
        z_crest_status: str = crest_status
        if crest_asbuilt_d is not None:
            z_crest, z_crest_status = _crest_elevation(
                d, e, crest_asbuilt_d, face_dir, defaults,
            )
        if z_crest is None and len(face_pts):
            z_crest = float(face_pts[0, 1])

        face_angle_asbuilt, face_angle_status = _measure_face_angle(
            face_pts, z_crest if z_crest is not None else crest_design[1],
            height_ref if height_ref is not None else toe_design[1], defaults,
        )

        height_asbuilt: float | None = None
        height_status: str
        if crest_status != STATUS_MEASURED:
            height_asbuilt, height_status = None, crest_status
        elif z_crest_status == STATUS_AMBIGUOUS:
            height_asbuilt, height_status = None, STATUS_AMBIGUOUS
        elif toe_status != STATUS_MEASURED:
            height_asbuilt, height_status = None, toe_status
        else:
            height_asbuilt = float(z_crest - height_ref) if (
                z_crest is not None and height_ref is not None
            ) else None
            height_status = STATUS_MEASURED if height_asbuilt is not None else STATUS_NO_CROSSING
            if height_asbuilt is not None and height_asbuilt <= 0:
                height_asbuilt, height_status = None, STATUS_INSUFFICIENT_POINTS

        warnings: list[str] = list(floor_warnings)
        if offset_shift is not None:
            warnings.append(f"bench_offset {offset_shift:.2f} m")
        berm_asbuilt: float | None = None
        berm_status = STATUS_NO_CROSSING
        if prev_bench is not None:
            if (
                prev_bench.toe_asbuilt_status == STATUS_MEASURED
                and prev_bench.toe_asbuilt_d is not None
                and not prev_bench.toe_extrapolated
                and crest_asbuilt_d is not None
            ):
                berm_asbuilt = float(abs(crest_asbuilt_d - prev_bench.toe_asbuilt_d))
                berm_status = STATUS_MEASURED
            else:
                warnings.append("berm not measurable: upper bench toe not measured")
        else:
            warnings.append("berm not measurable: no upper bench")

        if crest_status == STATUS_AMBIGUOUS or toe_status == STATUS_AMBIGUOUS:
            warnings.append("ambiguous crest/toe crossing")

        remnant_max = remnant_area = None
        if incline_berm:
            next_bd = ordered[bi + 1] if bi + 1 < len(ordered) else None
            remnant_max, remnant_area = _berm_remnant(
                toe_design,
                float(next_bd.crest_distance) if next_bd is not None else None,
                d, e, defaults.berm_remnant_min_m,
            )

        bench_state, rem_mean, rem_max = _classify_bench_state(
            d, e, bd, crest_status, toe_status, defaults,
            offset_shift=offset_shift,
        )

        results.append(DesignGuidedBench(
            bench_number=bd.bench_number,
            crest_design=crest_design,
            toe_design=toe_design,
            crest_asbuilt_d=crest_asbuilt_d,
            crest_asbuilt_status=crest_status,
            toe_asbuilt_d=toe_asbuilt_d,
            toe_asbuilt_status=toe_status,
            delta_crest=delta_crest,
            delta_toe=delta_toe,
            face_angle_asbuilt=face_angle_asbuilt,
            face_angle_status=face_angle_status,
            height_asbuilt=height_asbuilt,
            height_status=height_status,
            berm_asbuilt=berm_asbuilt,
            berm_status=berm_status,
            floor_offset_m=floor_offset,
            floor_offset_status=floor_offset_status,
            bench_state=bench_state,
            remaining_thickness_mean_m=rem_mean,
            remaining_thickness_max_m=rem_max,
            berm_remnant_max_m=remnant_max,
            berm_remnant_area_m2=remnant_area,
            warnings=tuple(warnings),
            window_used_m=defaults.crossing_window_m,
            toe_extrapolated=toe_extrapolated,
        ))
        prev_bench = results[-1]

    return results
