"""Face-angle consistency: as-built face vs design face of the same matched bench."""
import math

import numpy as np
import pytest

from core import (
    compare_design_vs_asbuilt,
    compare_design_vs_asbuilt_guided,
    extract_parameters,
)
from core.alert_system import aggregate_section_alerts, evaluate_bench_health
from core.config import STABILITY, TOLERANCES
from core.param_extractor import (
    BenchParams,
    ExtractionResult,
    _evaluate_angle_consistency,
)

TOL = {
    "bench_height": TOLERANCES.bench_height,
    "face_angle": TOLERANCES.face_angle,
    "berm_width": TOLERANCES.berm_width,
    "inter_ramp_angle": TOLERANCES.inter_ramp_angle,
    "overall_angle": TOLERANCES.overall_angle,
}


def _bench(number, crest_elevation, face_angle, *, crest_distance=50.0, height=15.0,
           flagged=False):
    run = height / math.tan(math.radians(face_angle))
    return BenchParams(
        bench_number=number,
        crest_elevation=crest_elevation,
        crest_distance=crest_distance,
        toe_elevation=crest_elevation - height,
        toe_distance=crest_distance + run,
        bench_height=height,
        face_angle=float(face_angle),
        berm_width=9.0,
        effective_berm_width=9.0,
        catch_bench_adequate=True,
        catch_bench_ratio=1.0,
        face_angle_inconsistent=flagged,
    )


def _params(benches, inter_ramp_angle=48.0):
    return ExtractionResult(
        section_name="S-01", sector="N", benches=list(benches),
        inter_ramp_angle=inter_ramp_angle, overall_angle=inter_ramp_angle,
    )


def _staircase_profile(face_angle=70.0, n_benches=4, height=15.0, berm=8.0):
    run = height / math.tan(math.radians(face_angle))
    d, e = [0.0], [200.0]
    x, z = 5.0, 200.0
    for _ in range(n_benches):
        d.append(x)
        e.append(z)
        x += run
        z -= height
        d.append(x)
        e.append(z)
        x += berm
    d.append(x + 20.0)
    e.append(z)
    grid = np.arange(0.0, d[-1], 0.1)
    return grid, np.interp(grid, d, e)


class TestThresholdConfig:
    def test_threshold_is_a_named_stability_default(self):
        assert STABILITY.face_angle_consistency_threshold_deg == 8.0


class TestMatchedBench:
    def test_six_degrees_from_design_face_is_not_flagged(self):
        design = _params([_bench(1, 100.0, 70.0)])
        topo = _params([_bench(1, 100.0, 64.0)])
        rows = compare_design_vs_asbuilt(design, topo, TOL)
        assert [r["type"] for r in rows] == ["MATCH"]
        assert topo.benches[0].face_angle_inconsistent is False

    def test_ten_degrees_from_design_face_is_flagged(self):
        design = _params([_bench(1, 100.0, 70.0)])
        topo = _params([_bench(1, 100.0, 60.0)])
        rows = compare_design_vs_asbuilt(design, topo, TOL)
        assert [r["type"] for r in rows] == ["MATCH"]
        assert topo.benches[0].face_angle_inconsistent is True

    def test_steeper_than_design_by_more_than_threshold_is_flagged(self):
        design = _params([_bench(1, 100.0, 65.0)])
        topo = _params([_bench(1, 100.0, 76.0)])
        compare_design_vs_asbuilt(design, topo, TOL)
        assert topo.benches[0].face_angle_inconsistent is True

    def test_exactly_threshold_is_not_flagged(self):
        design = _params([_bench(1, 100.0, 70.0)])
        topo = _params([_bench(1, 100.0, 62.0)])
        compare_design_vs_asbuilt(design, topo, TOL)
        assert topo.benches[0].face_angle_inconsistent is False

    def test_far_from_inter_ramp_but_close_to_design_is_not_flagged(self):
        design = _params([_bench(1, 100.0, 70.0)], inter_ramp_angle=50.0)
        topo = _params([_bench(1, 100.0, 66.0)], inter_ramp_angle=48.0)
        compare_design_vs_asbuilt(design, topo, TOL)
        assert topo.benches[0].face_angle_inconsistent is False

    def test_stale_flag_on_consistent_matched_bench_is_cleared(self):
        design = _params([_bench(1, 100.0, 70.0)])
        topo = _params([_bench(1, 100.0, 64.0, flagged=True)])
        compare_design_vs_asbuilt(design, topo, TOL)
        assert topo.benches[0].face_angle_inconsistent is False

    def test_each_bench_uses_its_own_matched_design_face(self):
        design = _params([_bench(1, 100.0, 70.0), _bench(2, 85.0, 55.0, crest_distance=65.0)])
        topo = _params([_bench(1, 100.0, 60.0), _bench(2, 85.0, 58.0, crest_distance=65.0)])
        rows = compare_design_vs_asbuilt(design, topo, TOL)
        assert sorted(r["type"] for r in rows) == ["MATCH", "MATCH"]
        assert [b.face_angle_inconsistent for b in topo.benches] == [True, False]

    def test_guided_comparison_applies_the_same_rule(self):
        design = _params([_bench(1, 100.0, 70.0)])
        topo = _params([_bench(1, 100.0, 60.0)])
        distances = np.array([0.0, 50.0, topo.benches[0].toe_distance, 120.0])
        elevations = np.array([100.0, 100.0, 85.0, 85.0])
        compare_design_vs_asbuilt_guided(design, topo, TOL, distances, elevations)
        assert topo.benches[0].face_angle_inconsistent is True


class TestUnmatchedAndDesignBenches:
    def test_extra_asbuilt_bench_is_not_flagged(self):
        design = _params([_bench(1, 100.0, 70.0)])
        topo = _params([
            _bench(1, 100.0, 69.0),
            _bench(2, 60.0, 40.0, crest_distance=90.0, flagged=True),
        ])
        rows = compare_design_vs_asbuilt(design, topo, TOL)
        assert sorted(r["type"] for r in rows) == ["EXTRA", "MATCH"]
        assert topo.benches[1].face_angle_inconsistent is False

    def test_asbuilt_benches_without_any_design_bench_are_not_flagged(self):
        design = _params([])
        topo = _params([_bench(1, 100.0, 80.0, flagged=True)])
        rows = compare_design_vs_asbuilt(design, topo, TOL)
        assert [r["type"] for r in rows] == ["EXTRA"]
        assert topo.benches[0].face_angle_inconsistent is False

    def test_design_benches_are_never_flagged(self):
        design = _params([
            _bench(1, 100.0, 70.0, flagged=True),
            _bench(2, 40.0, 70.0, crest_distance=120.0, flagged=True),
        ])
        topo = _params([_bench(1, 100.0, 55.0)])
        rows = compare_design_vs_asbuilt(design, topo, TOL)
        assert sorted(r["type"] for r in rows) == ["MATCH", "MISSING"]
        assert [b.face_angle_inconsistent for b in design.benches] == [False, False]


class TestExtractionAlone:
    def test_extraction_does_not_flag_from_inter_ramp_angle(self):
        distances, elevations = _staircase_profile(face_angle=70.0)
        result = extract_parameters(distances, elevations, "S-EXT", "N")
        assert len(result.benches) >= 3
        gaps = [abs(b.face_angle - result.inter_ramp_angle) for b in result.benches]
        assert max(gaps) > STABILITY.face_angle_consistency_threshold_deg
        assert [b.face_angle_inconsistent for b in result.benches] == [False] * len(result.benches)

    def test_extracted_design_and_asbuilt_follow_the_matched_design_rule(self):
        d_design, e_design = _staircase_profile(face_angle=70.0)
        d_topo, e_topo = _staircase_profile(face_angle=66.0)
        design = extract_parameters(d_design, e_design, "S-EXT", "N")
        topo = extract_parameters(d_topo, e_topo, "S-EXT", "N")
        rows = compare_design_vs_asbuilt(design, topo, TOL)
        assert any(r["type"] == "MATCH" for r in rows)
        assert not any(b.face_angle_inconsistent for b in design.benches)
        assert not any(b.face_angle_inconsistent for b in topo.benches)


class TestHelperContract:
    def test_design_face_angles_assign_the_flag_per_bench(self):
        benches = [
            _bench(1, 100.0, 64.0),
            _bench(2, 85.0, 60.0),
            _bench(3, 70.0, 30.0, flagged=True),
        ]
        returned = _evaluate_angle_consistency(
            benches, design_face_angles=[70.0, 70.0, None],
        )
        assert returned is benches
        assert [b.face_angle_inconsistent for b in benches] == [False, True, False]

    def test_non_finite_angles_are_not_evaluated_as_zero(self):
        benches = [_bench(1, 100.0, 64.0, flagged=True), _bench(2, 85.0, 60.0)]
        benches[1].face_angle = float("nan")
        _evaluate_angle_consistency(benches, design_face_angles=[float("nan"), 70.0])
        assert [b.face_angle_inconsistent for b in benches] == [False, False]

    def test_custom_threshold_is_honoured(self):
        benches = [_bench(1, 100.0, 64.0)]
        _evaluate_angle_consistency(benches, design_face_angles=[70.0], threshold_deg=5.0)
        assert benches[0].face_angle_inconsistent is True

    def test_design_face_angles_length_must_match(self):
        with pytest.raises(ValueError):
            _evaluate_angle_consistency([_bench(1, 100.0, 64.0)], design_face_angles=[])

    def test_legacy_positional_call_form_still_works(self):
        benches = [_bench(1, 100.0, 70.0), _bench(2, 85.0, 55.0)]
        returned = _evaluate_angle_consistency(benches, 70.0, 65.0)
        assert returned is benches
        assert [b.face_angle_inconsistent for b in benches] == [False, True]


class TestAlertFollowsTheFlag:
    def test_angle_alert_fires_only_for_benches_flagged_by_the_comparison(self):
        design = _params([_bench(1, 100.0, 70.0), _bench(2, 85.0, 70.0, crest_distance=65.0)])
        topo = _params([
            _bench(1, 100.0, 64.0),
            _bench(2, 85.0, 60.0, crest_distance=65.0),
            _bench(3, 40.0, 45.0, crest_distance=120.0),
        ])
        compare_design_vs_asbuilt(design, topo, TOL)
        flagged = {
            b.bench_number
            for b in topo.benches
            if any(a.code == "ANGLE_INCONSISTENT" for a in evaluate_bench_health(b))
        }
        assert flagged == {2}
        report = aggregate_section_alerts("S-01", topo.benches)
        assert [a.bench_number for a in report.alerts
                if a.code == "ANGLE_INCONSISTENT"] == [2]
        for b in design.benches:
            assert not any(
                a.code == "ANGLE_INCONSISTENT" for a in evaluate_bench_health(b)
            )

    def test_extraction_alone_raises_no_angle_alert(self):
        distances, elevations = _staircase_profile(face_angle=70.0)
        result = extract_parameters(distances, elevations, "S-EXT", "N")
        assert result.benches
        for b in result.benches:
            assert not any(
                a.code == "ANGLE_INCONSISTENT" for a in evaluate_bench_health(b)
            )
