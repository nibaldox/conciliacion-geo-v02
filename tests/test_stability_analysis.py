"""Tests for core.stability_analysis — Phase 9 + Phase 10 stability helpers."""

import pytest

from core.param_extractor import BenchParams
from core.stability_analysis import (
    BenchStabilityAssessment,
    assess_bench_stability,
    compute_anisotropy_dispersion,
    summarize_section_stability,
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
        bench_height=15.0,
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
