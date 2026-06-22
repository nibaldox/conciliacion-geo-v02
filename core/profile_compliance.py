"""Compliance evaluation and design-vs-as-built reconciliation.

Three public functions live here:

* :func:`_evaluate_status` — tripartite compliance status from a
  signed deviation and asymmetric tolerances.
* :func:`build_reconciled_profile` (legacy) /
  :func:`build_reconciled_profile_v2` (preferred) — turn a list of
  detected benches into an idealised polyline.
* :func:`compare_design_vs_asbuilt` — global best-fit (Hungarian)
  matching between design and as-built benches, with the per-bench
  compliance scoring used by the Excel/Word reports.
"""

import warnings
from dataclasses import dataclass
from typing import List

import numpy as np

from core.compliance_status import (
    STATUS_BANCO_ADICIONAL,
    STATUS_CUMPLE,
    STATUS_EXTRA,
    STATUS_FALTA_BANCO,
    STATUS_NO_CONSTRUIDO,
    STATUS_NO_CUMPLE,
    STATUS_FUERA,
)
from core.config import SECTOR_DEVIATION
from core.profile_extract import (
    ReconciledPoint,
    ReconciledProfile,
    _build_reconciled_points,
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
        return STATUS_CUMPLE
    elif abs_dev <= limit * 1.5:
        return STATUS_FUERA
    else:
        return STATUS_NO_CUMPLE


def build_reconciled_profile(benches, *, source: str = "topo",
                             return_v2: bool = False,
                             profile=None):
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
    profile=None,
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


def _build_cost_matrix(
    benches_design: list, benches_topo: list, match_threshold: float = 8.0,
) -> np.ndarray:
    """Pairwise cost matrix (design x topo). Pairs above threshold are
    blocked with a huge cost so the Hungarian solver won't pair them.
    Cost = sqrt(1.5 * dz**2 + 1.0 * dx**2) (z-weighted)."""
    n_d = len(benches_design)
    n_t = len(benches_topo)
    cost = np.zeros((n_d, n_t))
    for i, bd in enumerate(benches_design):
        bd_z = (bd.crest_elevation + bd.toe_elevation) / 2
        bd_x = (bd.crest_distance + bd.toe_distance) / 2
        for j, bt in enumerate(benches_topo):
            bt_z = (bt.crest_elevation + bt.toe_elevation) / 2
            bt_x = (bt.crest_distance + bt.toe_distance) / 2
            diff_z = abs(bd_z - bt_z)
            if diff_z >= match_threshold:
                cost[i, j] = 1e9
            else:
                cost[i, j] = np.sqrt(1.5 * (bd_z - bt_z) ** 2 + 1.0 * (bd_x - bt_x) ** 2)
    return cost


def _build_match_row(
    bd, bt, params_design, tolerances,
) -> dict:
    """Build a single MATCH comparison row (design + topo benches paired)."""
    height_dev = bt.bench_height - bd.bench_height
    angle_dev = bt.face_angle - bd.face_angle

    tol_h = tolerances['bench_height']
    tol_a = tolerances['face_angle']
    tol_b = tolerances['berm_width']

    min_berm = tol_b.get('min', 0.0)
    berm_real = round(bt.berm_width, 2)

    berm_complies = berm_real >= min_berm
    berm_status = STATUS_CUMPLE if berm_complies else STATUS_NO_CUMPLE
    berm_score = 60 if berm_complies else 0

    angle_complies = abs(angle_dev) <= (tol_a['neg'] if angle_dev < 0 else tol_a['pos'])
    angle_status = _evaluate_status(angle_dev, tol_a['neg'], tol_a['pos'])
    angle_score = 10 if angle_complies else 0

    height_complies = abs(height_dev) <= (tol_h['neg'] if height_dev < 0 else tol_h['pos'])
    height_status = _evaluate_status(height_dev, tol_h['neg'], tol_h['pos'])
    height_score = 30 if height_complies else 0

    return {
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
        'delta_crest': round(
            (bt.crest_distance - bd.crest_distance) *
            (1.0 if bd.crest_distance >= bd.toe_distance else -1.0), 2),
        'delta_toe': round(
            (bt.toe_distance - bd.toe_distance) *
            (1.0 if bd.crest_distance >= bd.toe_distance else -1.0), 2),
        'bench_design': bd,
        'bench_real': bt,
        'berm_score': berm_score,
        'angle_score': angle_score,
        'height_score': height_score,
        'bench_score': berm_score + angle_score + height_score,
    }


def _build_missing_row(bd, params_design) -> dict:
    """Build a MISSING comparison row (design has bench, topo doesn't)."""
    return {
        'sector': params_design.sector,
        'section': params_design.section_name,
        'bench_num': bd.bench_number,
        'type': 'MISSING',
        'level': f"{bd.toe_elevation:.0f}",
        'height_design': round(bd.bench_height, 2),
        'height_real': None,
        'height_dev': None,
        'height_status': STATUS_NO_CONSTRUIDO,
        'angle_design': round(bd.face_angle, 1),
        'angle_real': None,
        'angle_dev': None,
        'angle_status': "-",
        'berm_design': round(bd.berm_width, 2),
        'berm_real': None,
        'berm_min': None,
        'berm_status': STATUS_FALTA_BANCO,
        'spill_width': None,
        'effective_berm': None,
        'delta_crest': None,
        'delta_toe': None,
        'bench_design': bd,
        'bench_real': None,
        'berm_score': 0, 'angle_score': 0, 'height_score': 0, 'bench_score': 0,
    }


def _build_extra_row(bt, params_design) -> dict:
    """Build an EXTRA comparison row (topo has bench, design doesn't)."""
    return {
        'sector': params_design.sector,
        'section': params_design.section_name,
        'bench_num': 999,
        'type': 'EXTRA',
        'level': f"{bt.toe_elevation:.0f}",
        'height_design': None,
        'height_real': round(bt.bench_height, 2),
        'height_dev': None,
        'height_status': STATUS_EXTRA,
        'angle_design': None,
        'angle_real': round(bt.face_angle, 1),
        'angle_dev': None,
        'angle_status': "-",
        'berm_design': None,
        'berm_real': round(bt.berm_width, 2),
        'berm_min': None,
        'berm_status': STATUS_BANCO_ADICIONAL,
        'spill_width': round(bt.spill_width, 2),
        'effective_berm': round(bt.effective_berm_width, 2),
        'delta_crest': None,
        'delta_toe': None,
        'bench_design': None,
        'bench_real': bt,
        'berm_score': 0, 'angle_score': 0, 'height_score': 0, 'bench_score': 0,
    }


def _resolve_optimal_matches(
    cost_matrix: np.ndarray, match_threshold: float = 8.0,
) -> list[tuple[int, int, float]]:
    """Run Hungarian assignment and filter to pairs below match_threshold."""
    from scipy.optimize import linear_sum_assignment
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    candidates: list[tuple[int, int, float]] = []
    for r, c in zip(row_ind, col_ind):
        if cost_matrix[r, c] < match_threshold:
            candidates.append((r, c, cost_matrix[r, c]))
    candidates.sort(key=lambda x: x[0])
    return candidates


def _greedy_match_filter(candidates: list[tuple[int, int, float]]) -> list[tuple[int, int, float]]:
    """Greedy conflict resolution: prefer earlier-row / lower-cost matches.
    If a new candidate conflicts with a selected one, replace iff strictly
    cheaper in total."""
    valid: list[tuple[int, int, float]] = []
    for cand in candidates:
        r, c, cost = cand
        conflicts = [v for v in valid if c <= v[1]]
        if not conflicts:
            valid.append(cand)
            continue
        total_conflict_cost = sum(x[2] for x in conflicts)
        if cost < total_conflict_cost:
            valid = [x for x in valid if x not in conflicts]
            valid.append(cand)
    valid.sort(key=lambda x: x[0])
    return valid


def compare_design_vs_asbuilt(params_design, params_topo, tolerances):
    """
    Compare design vs as-built parameters using Global Best-Fit Matching (Hungarian Algorithm).
    Now returns matches, missing design benches, and extra topo benches.
    """
    comparisons: list[dict] = []

    benches_design = params_design.benches
    benches_topo = params_topo.benches

    n_d = len(benches_design)
    n_t = len(benches_topo)

    if n_d == 0 and n_t == 0:
        return []

    match_threshold = 8.0
    cost_matrix = _build_cost_matrix(benches_design, benches_topo, match_threshold)
    candidates = _resolve_optimal_matches(cost_matrix, match_threshold)
    valid_matches = _greedy_match_filter(candidates)

    matched_design_indices = {r for r, c, _ in valid_matches}
    matched_topo_indices = {c for r, c, _ in valid_matches}
    design_to_topo = {r: c for r, c, _ in valid_matches}

    for r in range(n_d):
        if r in matched_design_indices:
            c = design_to_topo[r]
            comparisons.append(
                _build_match_row(benches_design[r], benches_topo[c], params_design, tolerances)
            )

    for i in range(n_d):
        if i not in matched_design_indices:
            comparisons.append(_build_missing_row(benches_design[i], params_design))

    for j in range(n_t):
        if j not in matched_topo_indices:
            comparisons.append(_build_extra_row(benches_topo[j], params_design))

    match_scores = [c['bench_score'] for c in comparisons if c['type'] == 'MATCH']
    section_score = round(sum(match_scores) / len(match_scores), 1) if match_scores else 0.0
    section_status = STATUS_CUMPLE if section_score >= 70 else STATUS_NO_CUMPLE

    for c in comparisons:
        c['section_score'] = section_score
        c['section_status'] = section_status

    comparisons.sort(key=lambda x: float(x['level']) if x['level'].replace('.','',1).isdigit() else 0, reverse=True)

    return comparisons


@dataclass
class SectorDeviation:
    """Integrated deviations for a single sector between two profile points.

    A sector is a contiguous span ``[d_start, d_end]`` of the design
    profile (delimited by design crests/toes, or the whole profile when
    the design has no inflection points). The fields integrate the signed
    vertical gap ``topo - design`` over that span.

    ``area_above_m2`` follows the convention used in Phase 21: positive
    gap (as-built above design) is **overbreak** (sobre-excavación), and
    negative gap (as-built below design) is **underbreak** (deuda).
    """
    sector_id: int
    d_start: float
    d_end: float
    area_above_m2: float
    area_below_m2: float
    net_area_m2: float
    classification: str
    mean_delta_h: float
    max_delta_h: float
    centroid_d: float
    centroid_delta_h: float


def _design_sector_boundaries(design_d: np.ndarray, design_e: np.ndarray) -> List[float]:
    """Return sorted distance values of design local extrema (crests/toes).

    A crest is a local maximum and a toe a local minimum of the design
    elevation. Endpoints are never reported. The returned distances are
    interpolated to the exact crossing of consecutive slope signs so the
    boundary lands on the apex rather than the nearest grid node.
    """
    d = np.asarray(design_d, dtype=float)
    e = np.asarray(design_e, dtype=float)
    n = len(d)
    if n < 3:
        return []
    de = np.diff(e)
    sign = np.sign(de)
    sign[sign == 0] = 1
    boundaries: List[float] = []
    for i in range(1, n - 1):
        if sign[i - 1] > 0 and sign[i] < 0:
            boundaries.append(float(d[i]))
        elif sign[i - 1] < 0 and sign[i] > 0:
            boundaries.append(float(d[i]))
    boundaries = sorted(set(boundaries))
    return boundaries


def _classify_sector(area_above: float, area_below: float, width: float, tolerance_m: float) -> str:
    """Classify a sector from its over/under-break areas and width."""
    threshold = tolerance_m * width
    over = area_above > threshold
    under = area_below > threshold
    if over and under:
        return "mixed"
    if over:
        return "overbreak"
    if under:
        return "underbreak"
    return "compliant"


def compute_sector_deviations(
    design_d: np.ndarray,
    design_e: np.ndarray,
    topo_d: np.ndarray,
    topo_e: np.ndarray,
    tolerance_m: float = SECTOR_DEVIATION.tolerance_m,
) -> List[SectorDeviation]:
    """Segment a profile into sectors and compute integrated deviations.

    The design and topo curves are interpolated onto a common distance
    grid (resolution :attr:`SECTOR_DEVIATION.grid_resolution_m`) over the
    overlap of their distance ranges. The design is then split into
    sectors at its local extrema (crests/toes); when the design is
    monotonic (no inflection points) a single whole-profile sector is
    returned.

    For every sector:

    - ``delta = topo_interp - design_interp`` (positive = overbreak).
    - ``area_above_m2`` = ``trapz(max(delta, 0))`` (overbreak area).
    - ``area_below_m2`` = ``trapz(max(-delta, 0))`` (deuda area).
    - ``net_area_m2`` = ``trapz(delta)`` (signed, positive = net overbreak).
    - ``mean_delta_h`` / ``max_delta_h`` from the per-node delta.
    - ``centroid_d`` = area-weighted centroid distance (midpoint when the
      sector is flat); ``centroid_delta_h`` = delta sampled there.

    Classification uses ``tolerance_m * width`` as the area threshold:

    - ``"overbreak"`` if ``area_above`` alone exceeds it,
    - ``"underbreak"`` if ``area_below`` alone exceeds it,
    - ``"mixed"`` if both exceed it,
    - ``"compliant"`` otherwise.

    Parameters
    ----------
    design_d, design_e
        Design profile (crests, faces, toes).
    topo_d, topo_e
        As-built (topographic) profile.
    tolerance_m
        Vertical tolerance for the ``"compliant"`` classification.

    Returns
    -------
    list[SectorDeviation]
        Sectors ordered by distance, or an empty list when the two
        profiles do not overlap.
    """
    design_d = np.asarray(design_d, dtype=float)
    design_e = np.asarray(design_e, dtype=float)
    topo_d = np.asarray(topo_d, dtype=float)
    topo_e = np.asarray(topo_e, dtype=float)

    if design_d.size < 2 or topo_d.size < 2:
        return []

    d_lo = float(max(design_d.min(), topo_d.min()))
    d_hi = float(min(design_d.max(), topo_d.max()))
    if d_hi <= d_lo:
        return []

    res = float(SECTOR_DEVIATION.grid_resolution_m)
    n_nodes = max(2, int(np.ceil((d_hi - d_lo) / res)) + 1)
    common_d = np.linspace(d_lo, d_hi, n_nodes)

    order_d = np.argsort(design_d)
    design_interp = np.interp(common_d, design_d[order_d], design_e[order_d])
    order_t = np.argsort(topo_d)
    topo_interp = np.interp(common_d, topo_d[order_t], topo_e[order_t])

    boundaries = _design_sector_boundaries(design_d[order_d], design_e[order_d])
    edges = [d_lo] + [b for b in boundaries if d_lo < b < d_hi] + [d_hi]
    edges = sorted(set(edges))

    sectors: List[SectorDeviation] = []
    for i in range(len(edges) - 1):
        start = edges[i]
        end = edges[i + 1]
        mask = (common_d >= start) & (common_d <= end)
        if not np.any(mask):
            continue
        d_seg = common_d[mask]
        delta = topo_interp[mask] - design_interp[mask]
        width = float(d_seg[-1] - d_seg[0])
        if width <= 0:
            continue
        positive = np.clip(delta, 0.0, None)
        negative = np.clip(-delta, 0.0, None)
        area_above = float(np.trapezoid(positive, d_seg))
        area_below = float(np.trapezoid(negative, d_seg))
        net_area = float(np.trapezoid(delta, d_seg))
        mean_delta = float(np.mean(delta))
        max_delta = float(np.max(np.abs(delta)))
        weight = np.abs(delta)
        if weight.sum() > 1e-9:
            centroid_d = float(np.sum(d_seg * weight) / np.sum(weight))
        else:
            centroid_d = float(0.5 * (start + end))
        centroid_delta = float(np.interp(centroid_d, d_seg, delta))
        classification = _classify_sector(area_above, area_below, width, float(tolerance_m))
        sectors.append(SectorDeviation(
            sector_id=len(sectors) + 1,
            d_start=float(start),
            d_end=float(end),
            area_above_m2=area_above,
            area_below_m2=area_below,
            net_area_m2=net_area,
            classification=classification,
            mean_delta_h=mean_delta,
            max_delta_h=max_delta,
            centroid_d=centroid_d,
            centroid_delta_h=centroid_delta,
        ))

    return sectors
