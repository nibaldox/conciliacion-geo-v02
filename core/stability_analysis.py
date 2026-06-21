"""Stability analysis helpers (Phase 9 + Phase 10 + Phase 11).

Provides summary functions that operate on :class:`BenchParams`
collections produced by :mod:`core.param_extractor`. Future phases will
add Markland test, planar factor of safety, wedge analysis, etc.

These helpers are intentionally small: the goal of Phase 9 was to wire
overhang / rock-bridge / catch-bench detection into the extractor and
expose a thin aggregation layer that downstream code (report
generator, web UI, future physics modules) can call without re-parsing
the raw ``BenchParams`` list. Phase 10 adds wedge / toppling /
angle-consistency / anisotropy proxies to the same surface. Phase 11
adds planar factor of safety (proxy and full Hoek-Bray form) plus a
section-level health score and recommended action.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from core.param_extractor import BenchParams
from core.config import STABILITY, SECTOR_DEVIATION


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


HEALTH_THRESHOLDS = {
    'GREEN': 90,
    'YELLOW': 75,
    'ORANGE': 50,
    'RED': 0,
}
"""Score ranges: 90-100 GREEN, 75-89 YELLOW, 50-74 ORANGE, <50 RED."""


HEALTH_ACTIONS = {
    'GREEN': 'Operación normal. Mantener monitoreo de rutina.',
    'YELLOW': 'Revisar bancos críticos en próximo turno.',
    'ORANGE': 'Investigar causa de los flags. Considerar instrumentación.',
    'RED': 'Detener trabajo en zona. Instrumentar y reevaluar.',
}


@dataclass
class SectionHealthScore:
    """Aggregate health score for a section."""
    section_name: str
    health_score: float
    health_category: str
    components: dict = field(default_factory=dict)
    critical_bench_numbers: list = field(default_factory=list)
    recommended_action: str = ''


def _classify_health(score: float) -> str:
    if score >= HEALTH_THRESHOLDS['GREEN']:
        return 'GREEN'
    if score >= HEALTH_THRESHOLDS['YELLOW']:
        return 'YELLOW'
    if score >= HEALTH_THRESHOLDS['ORANGE']:
        return 'ORANGE'
    return 'RED'


def _fs_to_score(fs: float) -> float:
    if fs >= 2.0:
        return 100.0
    if fs <= 0.0:
        return 0.0
    if fs >= 1.0:
        return 50.0 + 50.0 * (fs - 1.0)
    return 50.0 * fs


def compute_section_health_score(section_name: str, benches: list[BenchParams]) -> SectionHealthScore:
    """Compute a 0-100 health score combining all stability metrics.

    Formula (per audit recommendation):
        health = 0.30*FS_score + 0.20*berm_score + 0.20*overhang_score +
                 0.15*wedge_score + 0.10*toppling_score + 0.05*anisotropy_score

    Each component_score is 0-100 (100 = perfect, 0 = worst). The aggregate
    is clamped to [0, 100].

    - FS_score (0.30): use ``compute_planar_factor_of_safety_proxy`` on the
      steepest face angle in the section (conservative). Convert: FS>=2 → 100,
      FS=1 → 50, FS<1 → 0 linearly.
    - berm_score (0.20): mean(catch_bench_ratio) * 100 across benches (already
      0-1 normalized); penalize sub-design berms.
    - overhang_score (0.20): 100 - 100*(mean(overhang_m)/overhang_critical_m),
      clamped [0, 100].
    - wedge_score (0.15): 100 * (1 - n_wedge_risk / n_benches).
    - toppling_score (0.10): 100 * (1 - n_toppling_risk / n_benches).
    - anisotropy_score (0.05): 100 - 100*(anisotropy_dispersion_deg/30.0),
      clamped [0, 100]. (30° dispersion = worst case.)

    Recommended action thresholds:
      GREEN:  'Operación normal. Mantener monitoreo de rutina.'
      YELLOW: 'Revisar bancos críticos en próximo turno.'
      ORANGE: 'Investigar causa de los flags. Considerar instrumentación.'
      RED:    'Detener trabajo en zona. Instrumentar y reevaluar.'
    """
    benches_list = list(benches)
    n = len(benches_list)

    if n == 0:
        return SectionHealthScore(
            section_name=section_name,
            health_score=0.0,
            health_category='RED',
            components={
                'FS': 0.0,
                'berm': 0.0,
                'overhang': 0.0,
                'wedge': 0.0,
                'toppling': 0.0,
                'anisotropy': 0.0,
            },
            critical_bench_numbers=[],
            recommended_action=HEALTH_ACTIONS['RED'],
        )

    steepest = max(benches_list, key=lambda b: float(b.face_angle))
    fs_proxy = compute_planar_factor_of_safety_proxy(steepest)
    fs_score = _fs_to_score(fs_proxy)

    berm_scores = [float(b.catch_bench_ratio) for b in benches_list]
    berm_score = max(0.0, min(100.0, (sum(berm_scores) / n) * 100.0))

    overhang_values = [float(b.overhang_m) for b in benches_list]
    mean_overhang = sum(overhang_values) / n
    critical_overhang = STABILITY.overhang_critical_m
    overhang_score = max(0.0, min(100.0, 100.0 - 100.0 * mean_overhang / critical_overhang))

    n_wedge = sum(1 for b in benches_list if b.wedge_risk)
    n_toppling = sum(1 for b in benches_list if b.toppling_risk)
    wedge_score = max(0.0, min(100.0, 100.0 * (1.0 - n_wedge / n)))
    toppling_score = max(0.0, min(100.0, 100.0 * (1.0 - n_toppling / n)))

    dispersion = compute_anisotropy_dispersion(benches_list)
    anisotropy_score = max(0.0, min(100.0, 100.0 - 100.0 * dispersion / 30.0))

    components = {
        'FS': fs_score,
        'berm': berm_score,
        'overhang': overhang_score,
        'wedge': wedge_score,
        'toppling': toppling_score,
        'anisotropy': anisotropy_score,
    }

    weights = {
        'FS': 0.30,
        'berm': 0.20,
        'overhang': 0.20,
        'wedge': 0.15,
        'toppling': 0.10,
        'anisotropy': 0.05,
    }
    aggregate = sum(weights[k] * components[k] for k in weights)
    aggregate = max(0.0, min(100.0, aggregate))

    category = _classify_health(aggregate)

    critical_bench_numbers = [
        int(b.bench_number)
        for b in benches_list
        if float(b.overhang_m) >= STABILITY.overhang_critical_m
    ]

    return SectionHealthScore(
        section_name=section_name,
        health_score=aggregate,
        health_category=category,
        components=components,
        critical_bench_numbers=critical_bench_numbers,
        recommended_action=HEALTH_ACTIONS[category],
    )


def compute_planar_factor_of_safety_proxy(bench: BenchParams) -> float:
    """Conservative FS proxy from face angle alone (no rock strength inputs).

    FS_proxy = tan(phi_typical) / tan(face_angle) where phi_typical = 35°.
    Always underestimates real FS (safe side).

    Returns FS_proxy in [0, +inf). For face_angle >= 90° returns 0.0.
    """
    import math
    if bench.face_angle >= 90.0:
        return 0.0
    phi_typical = 35.0
    return math.tan(math.radians(phi_typical)) / math.tan(math.radians(bench.face_angle))


def compute_planar_factor_of_safety(
    bench: BenchParams,
    cohesion_kpa: float,
    friction_angle_deg: float,
    water_pressure_ratio: float = 0.0,
) -> float:
    """Planar factor of safety for an infinite slope (Hoek & Bray 1981, ch 4).

    FS = (c·A + W·cos(ψ_f)·tan(φ)) / (W·sin(ψ_f))
    where ψ_f = face_angle, W = weight per unit area, A = unit area.

    Simplified to dimensionless form using unit bench geometry:
      FS = (c / (γ·H·sin(ψ_f)·cos(ψ_f))) + (tan(φ) / tan(ψ_f)) · (1 - r_u)

    Parameters
    ----------
    bench : BenchParams
        The bench to analyze (uses face_angle, bench_height).
    cohesion_kpa : float
        Cohesion of the rock mass (kPa).
    friction_angle_deg : float
        Friction angle of the rock mass (degrees).
    water_pressure_ratio : float
        Pore pressure ratio ru (0 = dry, 0.3 = typical wet slope). Default 0.

    Returns
    -------
    float
        Factor of safety (>=1 is stable).
    """
    import math
    gamma = 27.0
    psi_f = bench.face_angle
    H = bench.bench_height
    c = cohesion_kpa
    phi = friction_angle_deg
    ru = water_pressure_ratio

    if psi_f >= 90.0 or H <= 0:
        return 0.0

    sin_psi = math.sin(math.radians(psi_f))
    cos_psi = math.cos(math.radians(psi_f))
    tan_phi = math.tan(math.radians(phi))

    cohesion_term = c / (gamma * H * sin_psi * cos_psi) if (sin_psi * cos_psi) > 0 else 0.0
    friction_term = (tan_phi / math.tan(math.radians(psi_f))) * (1.0 - ru)

    return cohesion_term + friction_term


def _resolve_face_angle_strength(
    rock_mass_rating,
    cohesion_kpa,
    friction_angle_deg,
):
    """Resolve (cohesion_kpa, friction_angle_deg) for the face-angle solver.

    When explicit cohesion / friction are given they win. Otherwise the
    Hoek-Brown estimator (:func:`estimate_rock_strength_from_gsi`) is fed
    ``rmr_to_gsi(rmr)`` with the default UCS of 100 MPa, as specified by
    Phase 21. The estimator's cohesion is fit over the full confinement
    range (up to σci) and therefore returns an intact-rock-regime value
    that is several orders of magnitude above a rock-mass bench face; we
    scale it down by :attr:`SECTOR_DEVIATION.rockmass_cohesion_scale` so
    the infinite-slope equation behaves in the physically meaningful
    (non-saturated) regime. The friction angle is used verbatim.
    """
    from core.geology import estimate_rock_strength_from_gsi, rmr_to_gsi

    if cohesion_kpa is not None and friction_angle_deg is not None:
        return float(cohesion_kpa), float(friction_angle_deg)

    if rock_mass_rating is None:
        raise ValueError(
            "Either (cohesion_kpa, friction_angle_deg) or rock_mass_rating "
            "must be provided."
        )

    gsi = rmr_to_gsi(float(rock_mass_rating))
    c_est, phi_est = estimate_rock_strength_from_gsi(gsi, ucs_mpa=100.0)
    phi = float(friction_angle_deg) if friction_angle_deg is not None else float(phi_est)
    if cohesion_kpa is not None:
        c = float(cohesion_kpa)
    else:
        c = max(0.0, float(c_est)) * float(SECTOR_DEVIATION.rockmass_cohesion_scale)
    return c, phi


def _hoek_bray_factor_of_safety(
    face_angle_deg,
    cohesion_kpa,
    friction_angle_deg,
    bench_height_m,
    unit_weight_kn_m3,
    water_pressure_ratio,
):
    """Hoek & Bray (1981) infinite-slope FS for a face angle.

    FS = c / (γ·H·sin(ψ)·cos(ψ)) + (tan(φ) / tan(ψ)) · (1 - r_u)

    Returns ``+inf`` at the degenerate endpoints where the slope is
    frictionless-flat or perfectly vertical (sin·cos → 0).
    """
    psi = math.radians(face_angle_deg)
    sin_psi = math.sin(psi)
    cos_psi = math.cos(psi)
    denom = unit_weight_kn_m3 * bench_height_m * sin_psi * cos_psi
    if denom <= 0.0:
        return float('inf')
    cohesion_term = cohesion_kpa / denom
    friction_term = (math.tan(math.radians(friction_angle_deg)) / math.tan(psi)) * (
        1.0 - water_pressure_ratio
    )
    return cohesion_term + friction_term


def suggest_face_angle_for_fs(
    fs_target: float = 1.3,
    rock_mass_rating: float | None = None,
    cohesion_kpa: float | None = None,
    friction_angle_deg: float | None = None,
    bench_height_m: float = 15.0,
    unit_weight_kn_m3: float = 27.0,
    water_pressure_ratio: float = 0.0,
) -> float:
    """Suggest the maximum stable face angle to achieve a target FS.

    Solves the Hoek-Bray 1981 infinite-slope equation for the face angle
    ``ψ`` that still satisfies ``FS >= fs_target``:

        FS = (c / (γ·H·sin(ψ)·cos(ψ))) + (tan(φ) / tan(ψ)) · (1 - r_u)

    ``FS(ψ)`` is U-shaped over (0°, 90°): it is large for shallow angles,
    decreases to a minimum around mid-range, then rises again toward 90°
    as the cohesion term ``c / (γ·H·sin·cos)`` blows up (a numerical
    artifact of the simplified form, not a real gain in stability). The
    physically meaningful "steepest stable face" is therefore the angle
    on the **descending branch**, found by bisection on ``[ψ_floor, ψ_min]``
    where ``ψ_min`` is the angle of minimum FS. The cohesion artifact
    near 90° is excluded by construction.

    Parameters
    ----------
    fs_target
        Target factor of safety (must be >= 1.0; <1.0 is failure by
        design and is rejected).
    rock_mass_rating
        RMR of the rock mass. Used to derive cohesion / friction via the
        Hoek-Brown estimator when the explicit values are not supplied.
    cohesion_kpa, friction_angle_deg
        Explicit material strength. When both are given they override the
        RMR-derived estimates.
    bench_height_m
        Bench height (m).
    unit_weight_kn_m3
        Rock unit weight (kN/m³).
    water_pressure_ratio
        Pore-pressure ratio ``r_u`` (0 = dry, <1).

    Returns
    -------
    float
        Maximum face angle in degrees that satisfies ``fs_target`` on the
        descending branch. If even the shallowest admissible angle cannot
        reach the target, returns
        :attr:`SECTOR_DEVIATION.suggested_face_angle_unreachable_deg`
        (30°) and emits a warning.
    """
    if fs_target < 1.0:
        raise ValueError("fs_target must be >= 1.0 (FS < 1.0 is failure by design).")
    if bench_height_m <= 0.0:
        raise ValueError("bench_height_m must be positive.")
    if not (0.0 <= water_pressure_ratio < 1.0):
        raise ValueError("water_pressure_ratio must be in [0, 1).")

    cohesion, phi = _resolve_face_angle_strength(
        rock_mass_rating, cohesion_kpa, friction_angle_deg,
    )

    floor = SECTOR_DEVIATION.suggested_face_angle_floor_deg
    ceiling = SECTOR_DEVIATION.suggested_face_angle_ceiling_deg
    tol = SECTOR_DEVIATION.suggested_face_angle_tolerance_deg

    def fs_of(psi_deg):
        return _hoek_bray_factor_of_safety(
            psi_deg, cohesion, phi, bench_height_m,
            unit_weight_kn_m3, water_pressure_ratio,
        )

    grid = np.arange(floor, ceiling + 1e-9, 0.5)
    fs_grid = np.array([fs_of(float(p)) for p in grid])
    i_min = int(np.argmin(fs_grid))
    psi_min = float(grid[i_min])
    fs_at_floor = float(fs_grid[0])
    fs_at_min = float(fs_grid[i_min])

    if fs_at_floor < fs_target:
        warnings.warn(
            f"Target FS={fs_target} is unreachable even at the shallowest "
            f"admissible face angle ({floor}°, FS={fs_at_floor:.2f}). "
            f"Returning the fallback angle "
            f"{SECTOR_DEVIATION.suggested_face_angle_unreachable_deg}°.",
            UserWarning,
            stacklevel=2,
        )
        return SECTOR_DEVIATION.suggested_face_angle_unreachable_deg

    if fs_at_min >= fs_target:
        return psi_min

    lo, hi = floor, psi_min
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid - lo < tol:
            break
        if fs_of(mid) >= fs_target:
            lo = mid
        else:
            hi = mid
    return float(lo)


@dataclass
class BenchAngleSuggestion:
    bench_number: int
    detected_face_angle_deg: float
    target_face_angle_deg: float
    satisfies_target_fs: bool
    fs_at_detected_angle: float
    safety_margin_deg: float
    confidence: float


def suggest_face_angles_for_benches(
    benches: list[BenchParams],
    fs_target: float = 1.3,
    rock_mass_rating: float | None = None,
    cohesion_kpa: float | None = None,
    friction_angle_deg: float | None = None,
    unit_weight_kn_m3: float = 27.0,
    water_pressure_ratio: float = 0.0,
) -> list[BenchAngleSuggestion]:
    """Suggest a target face angle per bench for the given FS target.

    Resolves the rock-mass strength once (explicit ``cohesion_kpa`` /
    ``friction_angle_deg`` win over ``rock_mass_rating``, same rule as
    :func:`suggest_face_angle_for_fs`) and reuses it for every bench so the
    per-bench target angle and the FS computed at the detected angle stay on
    the same resistance basis. Benches with a non-positive height cannot be
    solved and are returned with ``NaN`` numeric fields and
    ``confidence = 0.0``.

    Returns a list parallel to ``benches`` (one :class:`BenchAngleSuggestion`
    per input bench, in order).
    """
    cohesion, phi = _resolve_face_angle_strength(
        rock_mass_rating, cohesion_kpa, friction_angle_deg,
    )

    suggestions: list[BenchAngleSuggestion] = []
    for bench in benches:
        detected = float(bench.face_angle)
        height = float(bench.bench_height)

        if height <= 0.0:
            suggestions.append(BenchAngleSuggestion(
                bench_number=int(bench.bench_number),
                detected_face_angle_deg=detected,
                target_face_angle_deg=float('nan'),
                satisfies_target_fs=False,
                fs_at_detected_angle=float('nan'),
                safety_margin_deg=float('nan'),
                confidence=0.0,
            ))
            continue

        target = suggest_face_angle_for_fs(
            fs_target=fs_target,
            cohesion_kpa=cohesion,
            friction_angle_deg=phi,
            bench_height_m=height,
            unit_weight_kn_m3=unit_weight_kn_m3,
            water_pressure_ratio=water_pressure_ratio,
        )
        fs_detected = compute_planar_factor_of_safety(
            bench, cohesion, phi, water_pressure_ratio,
        )
        margin = float(target) - detected

        suggestions.append(BenchAngleSuggestion(
            bench_number=int(bench.bench_number),
            detected_face_angle_deg=detected,
            target_face_angle_deg=float(target),
            satisfies_target_fs=bool(detected <= float(target)),
            fs_at_detected_angle=float(fs_detected),
            safety_margin_deg=margin,
            confidence=max(0.0, min(1.0, float(bench.confidence_score))),
        ))

    return suggestions
