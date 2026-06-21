"""Tests for core.stability_analysis — Phase 9 + Phase 10 stability helpers."""

import math

import pytest

from core.param_extractor import BenchParams
from core.stability_analysis import (
    BenchStabilityAssessment,
    HEALTH_THRESHOLDS,
    SectionHealthScore,
    assess_bench_stability,
    compute_anisotropy_dispersion,
    compute_planar_factor_of_safety,
    compute_planar_factor_of_safety_proxy,
    compute_section_health_score,
    summarize_section_stability,
    suggest_face_angle_for_fs,
)
from core.config import STABILITY


def _make_bench(
    bench_number=1,
    overhang_m=0.0,
    rock_bridge_thickness_m=0.0,
    rock_bridge_height_m=0.0,
    catch_bench_adequate=False,
    catch_bench_ratio=0.0,
    face_angle=70.0,
    bench_height=15.0,
    is_ramp=False,
    wedge_risk=False,
    toppling_risk=False,
    face_angle_inconsistent=False,
    anisotropy_dispersion_deg=0.0,
):
    return BenchParams(
        bench_number=bench_number,
        crest_elevation=100.0,
        crest_distance=20.0,
        toe_elevation=85.0,
        toe_distance=10.0,
        bench_height=bench_height,
        face_angle=face_angle,
        berm_width=9.0,
        is_ramp=is_ramp,
        overhang_m=overhang_m,
        rock_bridge_thickness_m=rock_bridge_thickness_m,
        rock_bridge_height_m=rock_bridge_height_m,
        catch_bench_adequate=catch_bench_adequate,
        catch_bench_ratio=catch_bench_ratio,
        wedge_risk=wedge_risk,
        toppling_risk=toppling_risk,
        face_angle_inconsistent=face_angle_inconsistent,
        anisotropy_dispersion_deg=anisotropy_dispersion_deg,
    )


class TestStabilityAnalysis:
    """Phase 9 — A.1/A.2/A.6 stability assessment wrappers."""

    def test_assess_bench_ok_when_no_overhang(self):
        """overhang_m=0.2 m < STABILITY.overhang_warning_m (0.5) → severity=OK."""
        bench = _make_bench(overhang_m=0.2)
        assessment = assess_bench_stability(bench)
        assert assessment.overhang_severity == 'OK'
        assert isinstance(assessment, BenchStabilityAssessment)
        assert assessment.bench_number == 1
        assert assessment.overhang_m == pytest.approx(0.2)

    def test_assess_bench_warning_at_threshold(self):
        """overhang_m exactly at warning threshold (0.5) → severity=WARNING."""
        bench = _make_bench(overhang_m=STABILITY.overhang_warning_m)
        assessment = assess_bench_stability(bench)
        assert assessment.overhang_severity == 'WARNING'

    def test_assess_bench_warning_above_threshold_below_critical(self):
        """overhang_m=0.8 m (between 0.5 and 1.5) → severity=WARNING."""
        bench = _make_bench(overhang_m=0.8)
        assessment = assess_bench_stability(bench)
        assert assessment.overhang_severity == 'WARNING'

    def test_assess_bench_critical_above_threshold(self):
        """overhang_m=1.6 m > STABILITY.overhang_critical_m (1.5) → severity=CRITICAL."""
        bench = _make_bench(overhang_m=1.6)
        assessment = assess_bench_stability(bench)
        assert assessment.overhang_severity == 'CRITICAL'

    def test_assess_bench_critical_at_threshold(self):
        """overhang_m exactly at critical threshold (1.5) → severity=CRITICAL."""
        bench = _make_bench(overhang_m=STABILITY.overhang_critical_m)
        assessment = assess_bench_stability(bench)
        assert assessment.overhang_severity == 'CRITICAL'

    def test_assess_bench_propagates_bridge_and_catch_fields(self):
        """The wrapper copies rock-bridge and catch-bench fields verbatim."""
        bench = _make_bench(
            overhang_m=1.0,
            rock_bridge_thickness_m=2.5,
            rock_bridge_height_m=3.0,
            catch_bench_adequate=True,
            catch_bench_ratio=0.85,
        )
        a = assess_bench_stability(bench)
        assert a.rock_bridge_thickness_m == pytest.approx(2.5)
        assert a.rock_bridge_height_m == pytest.approx(3.0)
        assert a.catch_bench_adequate is True
        assert a.catch_bench_ratio == pytest.approx(0.85)

    def test_summarize_section_empty_benches(self):
        """Empty input → all counts are 0 and critical list is empty."""
        summary = summarize_section_stability([])
        assert summary['n_benches_total'] == 0
        assert summary['n_overhangs_warning'] == 0
        assert summary['n_overhangs_critical'] == 0
        assert summary['n_catch_bench_adequate'] == 0
        assert summary['n_wedge_risk'] == 0
        assert summary['n_toppling_risk'] == 0
        assert summary['n_face_angle_inconsistent'] == 0
        assert summary['anisotropy_dispersion_deg'] == 0.0
        assert summary['critical_bench_numbers'] == []

    def test_summarize_section_mixed_severities(self):
        """3 benches: 1 OK, 1 WARNING, 1 CRITICAL → counts correct."""
        benches = [
            _make_bench(bench_number=1, overhang_m=0.1),
            _make_bench(bench_number=2, overhang_m=0.7),
            _make_bench(bench_number=3, overhang_m=2.0),
        ]
        summary = summarize_section_stability(benches)
        assert summary['n_benches_total'] == 3
        assert summary['n_overhangs_warning'] == 1
        assert summary['n_overhangs_critical'] == 1
        assert summary['critical_bench_numbers'] == [3]

    def test_summarize_section_multiple_critical_bench_numbers(self):
        """Two critical benches (numbers 3 and 5) → critical_bench_numbers == [3, 5]."""
        benches = [
            _make_bench(bench_number=1, overhang_m=0.2),
            _make_bench(bench_number=3, overhang_m=1.6),
            _make_bench(bench_number=5, overhang_m=2.5),
        ]
        summary = summarize_section_stability(benches)
        assert summary['n_overhangs_critical'] == 2
        assert summary['critical_bench_numbers'] == [3, 5]

    def test_summarize_section_counts_adequate_catch_benches(self):
        """3 benches with catch_bench_adequate in [True, False, True] → count=2."""
        benches = [
            _make_bench(catch_bench_adequate=True),
            _make_bench(catch_bench_adequate=False),
            _make_bench(catch_bench_adequate=True),
        ]
        summary = summarize_section_stability(benches)
        assert summary['n_catch_bench_adequate'] == 2

    def test_summarize_section_accepts_iterable(self):
        """summarize_section_stability accepts any iterable, not just lists."""
        benches_gen = (
            _make_bench(bench_number=i, overhang_m=v)
            for i, v in enumerate([0.1, 1.0, 2.0])
        )
        summary = summarize_section_stability(benches_gen)
        assert summary['n_benches_total'] == 3
        assert summary['n_overhangs_warning'] == 1
        assert summary['n_overhangs_critical'] == 1
        assert summary['critical_bench_numbers'] == [2]

    def test_assess_bench_uses_configured_thresholds(self):
        """If STABILITY defaults change, assessment honours the new thresholds."""
        from dataclasses import replace
        from core.stability_analysis import assess_bench_stability as fn

        tight = replace(STABILITY, overhang_warning_m=0.1, overhang_critical_m=0.3)
        original = STABILITY
        try:
            from core import stability_analysis as sa_mod
            sa_mod.STABILITY = tight
            bench_ok = _make_bench(overhang_m=0.05)
            bench_warn = _make_bench(overhang_m=0.2)
            bench_crit = _make_bench(overhang_m=0.5)
            assert fn(bench_ok).overhang_severity == 'OK'
            assert fn(bench_warn).overhang_severity == 'WARNING'
            assert fn(bench_crit).overhang_severity == 'CRITICAL'
        finally:
            sa_mod.STABILITY = original


class TestAssessBenchStability:
    """Phase 10 — BenchStabilityAssessment carries the 4 new geotech proxies."""

    def test_includes_new_fields(self):
        """All Phase 10 fields are present on the assessment dataclass."""
        bench = _make_bench(
            wedge_risk=True,
            toppling_risk=False,
            face_angle_inconsistent=True,
            anisotropy_dispersion_deg=8.5,
        )
        a = assess_bench_stability(bench)
        assert hasattr(a, "wedge_risk")
        assert hasattr(a, "toppling_risk")
        assert hasattr(a, "face_angle_inconsistent")
        assert hasattr(a, "anisotropy_dispersion_deg")
        assert a.wedge_risk is True
        assert a.toppling_risk is False
        assert a.face_angle_inconsistent is True
        assert a.anisotropy_dispersion_deg == pytest.approx(8.5)

    def test_assessment_propagates_bench_values_verbatim(self):
        """The wrapper is a pure passthrough for the new boolean/scalar fields."""
        bench = _make_bench(
            face_angle=68.0,
            wedge_risk=True,
            toppling_risk=True,
            face_angle_inconsistent=False,
            anisotropy_dispersion_deg=12.3,
        )
        a = assess_bench_stability(bench)
        assert a.wedge_risk is True
        assert a.toppling_risk is True
        assert a.face_angle_inconsistent is False
        assert a.anisotropy_dispersion_deg == pytest.approx(12.3)


class TestSummarizeSection:
    """Phase 10 — summarize_section_stability counts the new proxies."""

    def test_counts_wedge_toppling_inconsistent(self):
        """n_wedge_risk / n_toppling_risk / n_face_angle_inconsistent are counted."""
        benches = [
            _make_bench(bench_number=1, wedge_risk=True),
            _make_bench(bench_number=2, toppling_risk=True),
            _make_bench(bench_number=3, face_angle_inconsistent=True),
            _make_bench(bench_number=4, wedge_risk=True, toppling_risk=True),
        ]
        summary = summarize_section_stability(benches)
        assert summary['n_wedge_risk'] == 2
        assert summary['n_toppling_risk'] == 2
        assert summary['n_face_angle_inconsistent'] == 1

    def test_anisotropy_dispersion_in_summary(self):
        """The summary exposes anisotropy_dispersion_deg computed from the benches."""
        benches = [
            _make_bench(bench_number=1, face_angle=55.0),
            _make_bench(bench_number=2, face_angle=70.0),
            _make_bench(bench_number=3, face_angle=85.0),
        ]
        summary = summarize_section_stability(benches)
        # dispersion is recomputed from the face_angle, not read from the field
        assert summary['anisotropy_dispersion_deg'] > 5.0
        # It must match the standalone helper
        assert summary['anisotropy_dispersion_deg'] == pytest.approx(
            compute_anisotropy_dispersion(benches)
        )

    def test_ramp_excluded_from_anisotropy_dispersion(self):
        """A ramp with an extreme face_angle does not bias the dispersion."""
        benches = [
            _make_bench(bench_number=1, face_angle=70.0),
            _make_bench(bench_number=2, face_angle=70.0, is_ramp=True),
        ]
        summary = summarize_section_stability(benches)
        # Only the first (non-ramp) bench contributes; need >=2 non-ramp for nonzero.
        assert summary['anisotropy_dispersion_deg'] == 0.0

    def test_summary_keys_complete(self):
        """The summary dict exposes every documented key."""
        summary = summarize_section_stability([_make_bench()])
        for key in (
            "n_benches_total",
            "n_overhangs_warning",
            "n_overhangs_critical",
            "n_catch_bench_adequate",
            "n_wedge_risk",
            "n_toppling_risk",
            "n_face_angle_inconsistent",
            "anisotropy_dispersion_deg",
            "critical_bench_numbers",
        ):
            assert key in summary, f"Missing key: {key}"


class TestHealthScore:
    """Phase 11 — C.6 compute_section_health_score aggregates all axes."""

    def test_perfect_section_is_green(self):
        """All-clean section with gentle slopes → score near 100, category GREEN.

        Uses face_angle=25° (well below phi_typical=35°) so the FS_proxy
        is ~1.5 (FS_score=75) and the aggregate exceeds the GREEN threshold.
        """
        benches = [
            _make_bench(bench_number=i, overhang_m=0.0, catch_bench_adequate=True,
                        catch_bench_ratio=1.0, face_angle=25.0)
            for i in range(1, 4)
        ]
        score = compute_section_health_score('S-clean', benches)
        assert isinstance(score, SectionHealthScore)
        assert score.health_score >= HEALTH_THRESHOLDS['GREEN']
        assert score.health_category == 'GREEN'
        assert score.section_name == 'S-clean'

    def test_section_with_critical_overhang(self):
        """A bench with overhang >= critical threshold drags score to RED."""
        benches = [
            _make_bench(bench_number=1, overhang_m=0.0, catch_bench_adequate=True,
                        catch_bench_ratio=1.0, face_angle=65.0),
            _make_bench(bench_number=2, overhang_m=2.5, catch_bench_adequate=False,
                        catch_bench_ratio=0.2, face_angle=75.0,
                        toppling_risk=True, wedge_risk=True),
        ]
        score = compute_section_health_score('S-bad', benches)
        assert score.health_score < HEALTH_THRESHOLDS['ORANGE']
        assert score.health_category == 'RED'
        assert 2 in score.critical_bench_numbers

    def test_score_components_breakdown(self):
        """The components dict exposes all 6 axes with 0-100 values."""
        benches = [_make_bench(bench_number=1, catch_bench_ratio=0.8,
                               face_angle=68.0, overhang_m=0.3)]
        score = compute_section_health_score('S1', benches)
        for axis in ('FS', 'berm', 'overhang', 'wedge', 'toppling', 'anisotropy'):
            assert axis in score.components, f"Missing axis: {axis}"
            assert 0.0 <= score.components[axis] <= 100.0

    def test_empty_benches_returns_zero(self):
        """Empty bench list → score=0, category=RED, no critical benches."""
        score = compute_section_health_score('S-empty', [])
        assert score.health_score == 0.0
        assert score.health_category == 'RED'
        assert score.critical_bench_numbers == []

    def test_recommended_action_present(self):
        """Every result carries a non-empty Spanish action string."""
        score = compute_section_health_score('S', [_make_bench()])
        assert isinstance(score.recommended_action, str)
        assert len(score.recommended_action) > 0
        assert score.recommended_action == {
            'GREEN': 'Operación normal. Mantener monitoreo de rutina.',
            'YELLOW': 'Revisar bancos críticos en próximo turno.',
            'ORANGE': 'Investigar causa de los flags. Considerar instrumentación.',
            'RED': 'Detener trabajo en zona. Instrumentar y reevaluar.',
        }[score.health_category]


class TestPlanarFS:
    """Phase 11 — B.1 planar factor of safety (proxy + Hoek-Bray form)."""

    def test_proxy_basic(self):
        """face_angle=60° → FS_proxy = tan(35°)/tan(60°) ≈ 0.404."""
        import math
        bench = _make_bench(face_angle=60.0)
        fs = compute_planar_factor_of_safety_proxy(bench)
        expected = math.tan(math.radians(35.0)) / math.tan(math.radians(60.0))
        assert fs == pytest.approx(expected, abs=1e-6)
        assert fs == pytest.approx(0.4043, abs=1e-3)

    def test_face_angle_90_returns_zero(self):
        """Degenerate vertical face returns 0.0 (no FS)."""
        bench = _make_bench(face_angle=90.0)
        assert compute_planar_factor_of_safety_proxy(bench) == 0.0

    def test_face_angle_above_90_returns_zero(self):
        """Angle > 90° is treated as degenerate and returns 0.0."""
        bench = _make_bench(face_angle=95.0)
        assert compute_planar_factor_of_safety_proxy(bench) == 0.0

    def test_with_cohesion_and_friction(self):
        """c=50 kPa, φ=35°, H=5m, ψ=60° → FS > 1 (stable)."""
        bench = _make_bench(face_angle=60.0, bench_height=5.0)
        fs = compute_planar_factor_of_safety(bench, cohesion_kpa=50.0,
                                             friction_angle_deg=35.0)
        assert fs > 1.0

    def test_water_pressure_reduces_FS(self):
        """Adding ru=0.3 strictly reduces FS (other inputs equal)."""
        bench = _make_bench(face_angle=60.0, bench_height=15.0)
        fs_dry = compute_planar_factor_of_safety(bench, 50.0, 35.0, water_pressure_ratio=0.0)
        fs_wet = compute_planar_factor_of_safety(bench, 50.0, 35.0, water_pressure_ratio=0.3)
        assert fs_wet < fs_dry

    def test_full_FS_zero_height_returns_zero(self):
        """Degenerate H=0 returns 0.0 (no sliding mass)."""
        bench = _make_bench(face_angle=60.0, bench_height=0.0)
        assert compute_planar_factor_of_safety(bench, 50.0, 35.0) == 0.0


class TestRMRGSI:
    """Phase 11 — E.1 + E.2 RMR → GSI lookup helpers."""

    def test_rmr_to_gsi(self):
        """RMR=65 → GSI=60 (offset of 5)."""
        from core.geology import rmr_to_gsi
        assert rmr_to_gsi(65.0) == pytest.approx(60.0)


class TestRockStrength:
    """Phase 11 — Hoek-Brown strength estimator from GSI+UCS."""

    def test_zero_inputs_returns_fallback(self):
        """gsi=0 or ucs=0 → conservative (0, 30°)."""
        from core.geology import estimate_rock_strength_from_gsi
        assert estimate_rock_strength_from_gsi(0.0, 100.0) == (0.0, 30.0)
        assert estimate_rock_strength_from_gsi(70.0, 0.0) == (0.0, 30.0)

    def test_high_gsi_reasonable_strength(self):
        """gsi=70, ucs=150 MPa → c > 0 and phi > 30°."""
        from core.geology import estimate_rock_strength_from_gsi
        c, phi = estimate_rock_strength_from_gsi(70.0, 150.0)
        assert c > 0.0
        assert phi > 30.0


class TestSuggestFaceAngle:
    """Phase 21 — suggest_face_angle_for_fs solves Hoek-Bray for max ψ."""

    def test_basic_input(self):
        """RMR=60, H=15, FS=1.3 → reasonable angle between 50° and 80°."""
        angle = suggest_face_angle_for_fs(
            fs_target=1.3, rock_mass_rating=60, bench_height_m=15,
        )
        assert isinstance(angle, float)
        assert math.isfinite(angle)
        assert 50.0 <= angle <= 80.0

    def test_higher_rmr_allows_steeper_angle(self):
        """RMR=80 yields a steeper suggested angle than RMR=40 (same FS, H)."""
        angle_80 = suggest_face_angle_for_fs(fs_target=1.3, rock_mass_rating=80)
        angle_40 = suggest_face_angle_for_fs(fs_target=1.3, rock_mass_rating=40)
        assert angle_80 > angle_40

    def test_taller_bench_requires_smaller_angle(self):
        """H=20 yields a flatter suggested angle than H=10 (same RMR)."""
        angle_h20 = suggest_face_angle_for_fs(
            fs_target=1.3, rock_mass_rating=60, bench_height_m=20,
        )
        angle_h10 = suggest_face_angle_for_fs(
            fs_target=1.3, rock_mass_rating=60, bench_height_m=10,
        )
        assert angle_h20 < angle_h10

    def test_higher_fs_target_smaller_angle(self):
        """FS=1.5 yields a flatter suggested angle than FS=1.2 (same RMR)."""
        angle_15 = suggest_face_angle_for_fs(fs_target=1.5, rock_mass_rating=60)
        angle_12 = suggest_face_angle_for_fs(fs_target=1.2, rock_mass_rating=60)
        assert angle_15 < angle_12

    def test_water_pressure_reduces_angle(self):
        """ru=0.3 yields a flatter suggested angle than ru=0 (same RMR)."""
        angle_wet = suggest_face_angle_for_fs(
            fs_target=1.3, rock_mass_rating=60, water_pressure_ratio=0.3,
        )
        angle_dry = suggest_face_angle_for_fs(
            fs_target=1.3, rock_mass_rating=60, water_pressure_ratio=0.0,
        )
        assert angle_wet < angle_dry

    def test_explicit_strength_overrides_rmr(self):
        """Explicit (c, phi) are used verbatim and reach FS>=target at the angle."""
        angle = suggest_face_angle_for_fs(
            fs_target=1.3,
            cohesion_kpa=50.0,
            friction_angle_deg=35.0,
            bench_height_m=15.0,
        )
        fs = math.tan(math.radians(35.0)) / math.tan(math.radians(angle))
        fs_full = 50.0 / (27.0 * 15.0 * math.sin(math.radians(angle)) * math.cos(math.radians(angle))) + fs
        assert fs_full >= 1.3 - 1e-6

    def test_fs_target_below_one_raises(self):
        """fs_target < 1.0 is failure by design and is rejected."""
        with pytest.raises(ValueError):
            suggest_face_angle_for_fs(fs_target=0.9, rock_mass_rating=60)

    def test_unreachable_target_returns_fallback(self, recwarn):
        """A target above FS at the shallowest angle returns the 30° fallback.

        With a weak, cohesionless material (φ=15°) the FS at 5° is
        tan(15°)/tan(5°)≈3.06, so an FS target of 4.0 is unreachable.
        """
        angle = suggest_face_angle_for_fs(
            fs_target=4.0, cohesion_kpa=0.0, friction_angle_deg=15.0,
            bench_height_m=15.0,
        )
        assert angle == 30.0
        assert any(issubclass(w.category, UserWarning) for w in recwarn.list)
