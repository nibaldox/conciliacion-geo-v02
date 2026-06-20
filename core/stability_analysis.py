"""Stability analysis helpers (Phase 9 + Phase 10).

Provides summary functions that operate on :class:`BenchParams`
collections produced by :mod:`core.param_extractor`. Future phases will
add Markland test, planar factor of safety, wedge analysis, etc.

These helpers are intentionally small: the goal of Phase 9 was to wire
overhang / rock-bridge / catch-bench detection into the extractor and
expose a thin aggregation layer that downstream code (report
generator, web UI, future physics modules) can call without re-parsing
the raw ``BenchParams`` list. Phase 10 adds wedge / toppling /
angle-consistency / anisotropy proxies to the same surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.param_extractor import BenchParams
from core.config import STABILITY


@dataclass
class BenchStabilityAssessment:
    bench_number: int
    overhang_m: float
    overhang_severity: str
    rock_bridge_thickness_m: float
    rock_bridge_height_m: float
    catch_bench_adequate: bool
    catch_bench_ratio: float
    wedge_risk: bool
    toppling_risk: bool
    face_angle_inconsistent: bool
    anisotropy_dispersion_deg: float


def assess_bench_stability(bench: BenchParams) -> BenchStabilityAssessment:
    """Wrap a single bench's stability flags into a severity classification.

    Overhang severity follows :data:`core.config.STABILITY`:

    - ``overhang_m >= overhang_critical_m`` → ``'CRITICAL'`` (default 1.5 m)
    - ``overhang_m >= overhang_warning_m``  → ``'WARNING'``  (default 0.5 m)
    - otherwise                               → ``'OK'``

    Phase 10 additions: propagates ``wedge_risk``, ``toppling_risk``,
    ``face_angle_inconsistent`` and ``anisotropy_dispersion_deg``
    straight from the bench record (no further classification here —
    those are pre-computed boolean / scalar proxies).
    """
    overhang = float(bench.overhang_m)
    if overhang >= STABILITY.overhang_critical_m:
        severity = 'CRITICAL'
    elif overhang >= STABILITY.overhang_warning_m:
        severity = 'WARNING'
    else:
        severity = 'OK'
    return BenchStabilityAssessment(
        bench_number=int(bench.bench_number),
        overhang_m=overhang,
        overhang_severity=severity,
        rock_bridge_thickness_m=float(bench.rock_bridge_thickness_m),
        rock_bridge_height_m=float(bench.rock_bridge_height_m),
        catch_bench_adequate=bool(bench.catch_bench_adequate),
        catch_bench_ratio=float(bench.catch_bench_ratio),
        wedge_risk=bool(bench.wedge_risk),
        toppling_risk=bool(bench.toppling_risk),
        face_angle_inconsistent=bool(bench.face_angle_inconsistent),
        anisotropy_dispersion_deg=float(bench.anisotropy_dispersion_deg),
    )


def compute_anisotropy_dispersion(benches: list[BenchParams]) -> float:
    """Return std deviation of ``face_angle`` across all (non-ramp) benches.

    High dispersion indicates the talud has heterogeneous face
    orientations, which can be a stability concern if discontinuities
    align with the steeper faces. The proxy uses population standard
    deviation (``ddof=0``) so a single bench or all-equal faces
    return 0.0 — i.e. no dispersion, no concern.

    Parameters
    ----------
    benches : list of BenchParams
        Detected benches (typically from :func:`extract_parameters`).
        Benches flagged as ramps (``is_ramp=True``) are excluded from
        the calculation because their face angle is not representative
        of the overall slope geometry.

    Returns
    -------
    float
        Standard deviation of face angles in degrees, or ``0.0`` if
        fewer than two non-ramp benches are provided.
    """
    import numpy as np
    angles = [float(b.face_angle) for b in benches if not b.is_ramp]
    if len(angles) < 2:
        return 0.0
    return float(np.std(angles, ddof=0))


def summarize_section_stability(benches: Iterable[BenchParams]) -> dict:
    """Aggregate stability assessment over all benches in a section.

    Returns a dict with:

    - ``n_benches_total``: count of input benches
    - ``n_overhangs_warning``: benches with ``overhang_severity == 'WARNING'``
    - ``n_overhangs_critical``: benches with ``overhang_severity == 'CRITICAL'``
    - ``n_catch_bench_adequate``: benches with ``catch_bench_adequate == True``
    - ``n_wedge_risk``: benches with ``wedge_risk == True``
    - ``n_toppling_risk``: benches with ``toppling_risk == True``
    - ``n_face_angle_inconsistent``: benches with ``face_angle_inconsistent == True``
    - ``anisotropy_dispersion_deg``: std-dev of face angles across non-ramp benches
    - ``critical_bench_numbers``: ``bench_number`` of every critical bench
    """
    benches_list = list(benches)
    assessments = [assess_bench_stability(b) for b in benches_list]
    dispersion = compute_anisotropy_dispersion(benches_list)
    return {
        'n_benches_total': len(benches_list),
        'n_overhangs_warning': sum(
            1 for a in assessments if a.overhang_severity == 'WARNING'
        ),
        'n_overhangs_critical': sum(
            1 for a in assessments if a.overhang_severity == 'CRITICAL'
        ),
        'n_catch_bench_adequate': sum(
            1 for a in assessments if a.catch_bench_adequate
        ),
        'n_wedge_risk': sum(
            1 for a in assessments if a.wedge_risk
        ),
        'n_toppling_risk': sum(
            1 for a in assessments if a.toppling_risk
        ),
        'n_face_angle_inconsistent': sum(
            1 for a in assessments if a.face_angle_inconsistent
        ),
        'anisotropy_dispersion_deg': dispersion,
        'critical_bench_numbers': [
            a.bench_number for a in assessments if a.overhang_severity == 'CRITICAL'
        ],
    }
