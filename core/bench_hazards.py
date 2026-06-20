"""Geotechnical hazard detectors operating on detected benches.

These routines decorate each ``BenchParams`` in place with stability
indicators:

* :func:`_detect_overhangs_and_bridges` — overhang and rock-bridge
  geometry between consecutive non-ramp benches (Phase 9).
* :func:`_evaluate_catch_bench_adequacy` — Read & Stacey catch-bench
  width criterion (Phase 9).
* :func:`_detect_wedge_shape_in_face` — acute-dihedral wedge proxy
  (Phase 10).
* :func:`_detect_toppling_potential` — Goodman & Bray toppling proxy
  (Phase 10).
* :func:`_evaluate_angle_consistency` — flags benches whose face
  angle departs from the inter-ramp angle by more than 8°
  (Phase 10).

The ``_angle_between_segments`` helper supports :func:`_detect_wedge_shape_in_face`.
"""

import numpy as np


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


def _angle_between_segments(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    """Return the angle between two 2D segments in degrees.

    Parameters
    ----------
    v1, v2 : tuple of (dx, dy)
        Segment vectors (2D). Zero-length segments return 0.0 to avoid
        division-by-zero.
    """
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = (v1[0] ** 2 + v1[1] ** 2) ** 0.5
    mag2 = (v2[0] ** 2 + v2[1] ** 2) ** 0.5
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    cos_a = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return float(np.degrees(np.arccos(cos_a)))


def _detect_wedge_shape_in_face(
    bench,
    face_pts=None,
) -> bool:
    """Detect acute dihedral angles in the bench face.

    Wedge shape proxy: looks for pairs of consecutive segments in the
    face that form a dihedral angle < 60°. This is a weak proxy (proper
    Markland test requires discontinuity orientation, see audit E.3) but
    it flags geometric configurations that *resemble* wedges.

    Parameters
    ----------
    bench : BenchParams
        The bench to analyze.
    face_pts : list of (x, z) tuples, optional
        Optional explicit face points (for testing). When provided with
        at least 3 points, computes dihedral angles between consecutive
        segments. When ``None`` or fewer than 3 points, falls back to a
        conservative heuristic proxy: any bench with
        ``face_angle > 65°`` AND ``bench_height > 12 m`` is flagged.

    Returns
    -------
    bool
        ``True`` if wedge shape is detected.
    """
    if face_pts is not None and len(face_pts) >= 3:
        for i in range(len(face_pts) - 2):
            v1 = (
                face_pts[i + 1][0] - face_pts[i][0],
                face_pts[i + 1][1] - face_pts[i][1],
            )
            v2 = (
                face_pts[i + 2][0] - face_pts[i + 1][0],
                face_pts[i + 2][1] - face_pts[i + 1][1],
            )
            angle = _angle_between_segments(v1, v2)
            if angle < 60.0:
                return True
        return False
    return bench.face_angle > 65.0 and bench.bench_height > 12.0


def _detect_toppling_potential(
    bench,
    upper_bench_face_angle=None,
) -> bool:
    """Toppling proxy: tall bench with steep face and upper release.

    Empirical thresholds (Goodman & Bray, 1976):

    - ``face_angle > 80°`` alone → toppling potential (near-vertical face).
    - ``face_angle > 75°`` AND ``bench_height > 15 m`` → toppling potential
      (steep + tall block is unstable).
    - ``face_angle > 65°`` AND ``bench_height > 12 m`` AND the bench
      immediately above has ``face_angle > 75°`` → toppling potential
      (the upper release surface provides the kinematic freedom).

    Parameters
    ----------
    bench : BenchParams
        The bench to analyze.
    upper_bench_face_angle : float, optional
        Face angle of the bench immediately above (release condition).
        When ``None`` the third rule is skipped.

    Returns
    -------
    bool
        ``True`` if toppling risk is detected.
    """
    if bench.face_angle > 80.0:
        return True
    if bench.face_angle > 75.0 and bench.bench_height > 15.0:
        return True
    if (
        upper_bench_face_angle is not None
        and upper_bench_face_angle > 75.0
        and bench.face_angle > 65.0
        and bench.bench_height > 12.0
    ):
        return True
    return False


def _evaluate_angle_consistency(
    benches,
    inter_ramp_angle: float,
    overall_angle: float,
):
    """Flag benches whose face_angle is inconsistent with the inter-ramp angle.

    Criteria:

    - If ``|face_angle - inter_ramp_angle| > 8°`` → flag
      ``face_angle_inconsistent = True``. This indicates the bench is
      either anomalously steep or shallow relative to the overall slope
      geometry.

    ``overall_angle`` is accepted for forward compatibility (the audit
    also discussed |face_angle - overall_angle| comparisons), but the
    current rule uses ``inter_ramp_angle`` as the reference, which is
    the more conservative (steeper) reference value.

    Updates in place: ``bench.face_angle_inconsistent``. Returns the
    same list for convenience.
    """
    for b in benches:
        if abs(float(b.face_angle) - float(inter_ramp_angle)) > 8.0:
            b.face_angle_inconsistent = True
    return benches
