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

    match_threshold = 8.0

    cost_matrix = np.zeros((n_d, n_t))

    for i, bd in enumerate(benches_design):
        bd_z = (bd.crest_elevation + bd.toe_elevation) / 2
        bd_x = (bd.crest_distance + bd.toe_distance) / 2
        for j, bt in enumerate(benches_topo):
            bt_z = (bt.crest_elevation + bt.toe_elevation) / 2
            bt_x = (bt.crest_distance + bt.toe_distance) / 2

            diff_z = abs(bd_z - bt_z)
            if diff_z >= match_threshold:
                cost_matrix[i, j] = 1e9
            else:
                cost_matrix[i, j] = np.sqrt(1.5 * (bd_z - bt_z)**2 + 1.0 * (bd_x - bt_x)**2)

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    candidates = []
    for r, c in zip(row_ind, col_ind):
        bd = benches_design[r]
        bt = benches_topo[c]
        bd_z = (bd.crest_elevation + bd.toe_elevation) / 2
        bt_z = (bt.crest_elevation + bt.toe_elevation) / 2
        diff_z = abs(bd_z - bt_z)
        if diff_z < match_threshold:
            candidates.append((r, c, cost_matrix[r, c]))

    candidates.sort(key=lambda x: x[0])

    valid_matches = []
    for cand in candidates:
        r, c, cost = cand
        conflicts = [v for v in valid_matches if c <= v[1]]
        if not conflicts:
            valid_matches.append(cand)
        else:
            total_conflict_cost = sum(x[2] for x in conflicts)
            if cost < total_conflict_cost:
                valid_matches = [x for x in valid_matches if x not in conflicts]
                valid_matches.append(cand)

    valid_matches.sort(key=lambda x: x[0])

    matched_design_indices = {r for r, c, _ in valid_matches}
    matched_topo_indices = {c for r, c, _ in valid_matches}
    design_to_topo = {r: c for r, c, _ in valid_matches}

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
            berm_status = STATUS_CUMPLE if berm_complies else STATUS_NO_CUMPLE
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
                'berm_score': 0,
                'angle_score': 0,
                'height_score': 0,
                'bench_score': 0,
            })

    for j in range(n_t):
        if j not in matched_topo_indices:
            bt = benches_topo[j]
            comparisons.append({
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
                'berm_score': 0,
                'angle_score': 0,
                'height_score': 0,
                'bench_score': 0,
            })

    match_scores = [c['bench_score'] for c in comparisons if c['type'] == 'MATCH']
    section_score = round(sum(match_scores) / len(match_scores), 1) if match_scores else 0.0
    section_status = STATUS_CUMPLE if section_score >= 70 else STATUS_NO_CUMPLE

    for c in comparisons:
        c['section_score'] = section_score
        c['section_status'] = section_status

    comparisons.sort(key=lambda x: float(x['level']) if x['level'].replace('.','',1).isdigit() else 0, reverse=True)

    return comparisons
