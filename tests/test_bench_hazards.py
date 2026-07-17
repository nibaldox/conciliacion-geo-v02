"""Unit tests for geotechnical bench hazard detectors."""

from types import SimpleNamespace

import pytest

from core.bench_hazards import (
    _angle_between_segments,
    _detect_overhangs_and_bridges,
    _detect_toppling_potential,
    _detect_wedge_shape_in_face,
    _evaluate_angle_consistency,
    _evaluate_catch_bench_adequacy,
)


def _bench(**overrides):
    values = {
        "crest_distance": 10.0,
        "toe_distance": 5.0,
        "crest_elevation": 100.0,
        "toe_elevation": 85.0,
        "berm_width": 10.0,
        "effective_berm_width": 8.0,
        "face_angle": 70.0,
        "bench_height": 15.0,
        "is_ramp": False,
        "overhang_m": 0.0,
        "rock_bridge_height_m": 0.0,
        "rock_bridge_thickness_m": 0.0,
        "catch_bench_adequate": False,
        "catch_bench_ratio": 0.0,
        "face_angle_inconsistent": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_detect_overhangs_and_bridges_computes_pair_geometry():
    current = _bench(crest_distance=10.0, toe_elevation=90.0)
    next_bench = _bench(toe_distance=12.0, crest_elevation=85.0)

    _detect_overhangs_and_bridges([current, next_bench])

    assert current.overhang_m == pytest.approx(-2.0)
    assert current.rock_bridge_height_m == pytest.approx(5.0)
    assert current.rock_bridge_thickness_m == pytest.approx(2.0)


def test_detect_overhangs_skips_ramp_adjacency_and_short_inputs():
    ramp = _bench(is_ramp=True, overhang_m=123.0)
    _detect_overhangs_and_bridges([ramp, _bench(toe_distance=0.0)])
    assert ramp.overhang_m == 123.0
    assert _detect_overhangs_and_bridges([]) is None
    assert _detect_overhangs_and_bridges([_bench()]) is None


def test_catch_bench_adequacy_handles_design_threshold_and_zero_width():
    adequate = _bench(berm_width=10.0, effective_berm_width=8.0)
    degenerate = _bench(berm_width=0.0, effective_berm_width=0.5)

    _evaluate_catch_bench_adequacy([adequate, degenerate], berm_design_min_m=6.0)

    assert adequate.catch_bench_ratio == pytest.approx(0.8)
    assert adequate.catch_bench_adequate is True
    assert degenerate.catch_bench_ratio == pytest.approx(500.0)
    assert degenerate.catch_bench_adequate is False


def test_angle_between_segments_handles_right_angle_and_zero_vector():
    assert _angle_between_segments((1.0, 0.0), (0.0, 1.0)) == pytest.approx(90.0)
    assert _angle_between_segments((0.0, 0.0), (1.0, 0.0)) == 0.0


def test_wedge_shape_uses_points_or_fallback_geometry():
    bench = _bench(face_angle=70.0, bench_height=13.0)
    assert _detect_wedge_shape_in_face(bench, [(0.0, 0.0), (1.0, 0.0), (2.0, 0.1)])
    assert not _detect_wedge_shape_in_face(bench, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    assert _detect_wedge_shape_in_face(bench)


def test_toppling_rules_and_angle_consistency_boundaries():
    assert _detect_toppling_potential(_bench(face_angle=81.0, bench_height=5.0))
    assert _detect_toppling_potential(_bench(face_angle=76.0, bench_height=16.0))
    assert _detect_toppling_potential(
        _bench(face_angle=66.0, bench_height=13.0), upper_bench_face_angle=76.0
    )
    assert not _detect_toppling_potential(_bench(face_angle=75.0, bench_height=15.0))

    within = _bench(face_angle=78.0)
    outside = _bench(face_angle=78.1)
    returned = _evaluate_angle_consistency([within, outside], 70.0, 65.0)
    assert returned == [within, outside]
    assert within.face_angle_inconsistent is False
    assert outside.face_angle_inconsistent is True
