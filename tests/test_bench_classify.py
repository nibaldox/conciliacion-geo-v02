"""Unit tests for berm and ramp classification helpers."""

from types import SimpleNamespace

import numpy as np
import pytest

from core.bench_classify import (
    _apply_leading_berm,
    _apply_trailing_berm,
    _compute_berm_widths_from_profile,
    _flat_segment_width,
    _is_ramp,
)


def _bench(crest_distance, toe_distance, crest_elevation, toe_elevation, spill_width=0.0):
    return SimpleNamespace(
        crest_distance=crest_distance,
        toe_distance=toe_distance,
        crest_elevation=crest_elevation,
        toe_elevation=toe_elevation,
        spill_width=spill_width,
        berm_width=0.0,
        effective_berm_width=0.0,
        is_ramp=False,
        ramp_segment=False,
        group_break=False,
    )


def test_compute_berm_widths_sets_width_effective_width_and_group_break():
    first = _bench(0.0, 5.0, 100.0, 85.0, spill_width=2.0)
    second = _bench(65.0, 70.0, 85.0, 70.0)

    _compute_berm_widths_from_profile(
        [first, second], None, None, None, max_berm_width=50.0
    )

    assert first.berm_width == 0.0
    assert second.berm_width == pytest.approx(60.0)
    assert second.effective_berm_width == pytest.approx(58.0)
    assert second.group_break is True


def test_compute_berm_widths_accepts_empty_bench_list():
    assert _compute_berm_widths_from_profile([], None, None, None) is None


def test_flat_segment_width_distinguishes_flat_and_steep_segments():
    assert _flat_segment_width(np.array([0.0, 8.0]), np.array([100.0, 100.5]), 10.0) == pytest.approx(8.0)
    assert _flat_segment_width(np.array([0.0, 2.0]), np.array([100.0, 98.0]), 10.0) == 0.0
    assert _flat_segment_width(np.array([0.0]), np.array([100.0]), 10.0) == 0.0


def test_is_ramp_requires_minimum_width_and_gentle_slope():
    assert _is_ramp(0.0, 10.0, 100.0, 99.0)
    assert not _is_ramp(0.0, 5.0, 100.0, 99.0)
    assert not _is_ramp(0.0, 10.0, 100.0, 95.0)


def test_leading_berm_assigns_flat_width_to_first_bench():
    bench = _bench(20.0, 25.0, 100.0, 85.0)
    distances = np.array([0.0, 8.0, 16.0, 20.0, 25.0])
    elevations = np.array([100.0, 100.0, 100.0, 100.0, 85.0])

    _apply_leading_berm([bench], distances, elevations, berm_threshold=5.0)

    assert bench.berm_width == pytest.approx(16.0)
    assert bench.is_ramp is True
    assert bench.ramp_segment is True


def test_trailing_berm_is_single_bench_fallback_only():
    bench = _bench(0.0, 5.0, 100.0, 85.0)
    distances = np.array([0.0, 5.0, 10.0, 20.0])
    elevations = np.array([100.0, 85.0, 85.0, 85.0])

    _apply_trailing_berm([bench], distances, elevations, berm_threshold=5.0)

    assert bench.berm_width == pytest.approx(10.0)
    assert bench.is_ramp is False

    second = _bench(30.0, 35.0, 85.0, 70.0)
    bench.berm_width = 0.0
    _apply_trailing_berm([bench, second], distances, elevations, berm_threshold=5.0)
    assert bench.berm_width == 0.0


def _floor_bench(crest, toe, face_angle, floor_elevation=0.0):
    from core.profile_extract import BenchParams

    return BenchParams(
        bench_number=0,
        crest_elevation=crest[1],
        crest_distance=crest[0],
        toe_elevation=toe[1],
        toe_distance=toe[0],
        bench_height=abs(crest[1] - toe[1]),
        face_angle=face_angle,
        berm_width=0.0,
        floor_elevation=floor_elevation,
    )


def _finalized(benches):
    from core.profile_extract import ExtractionResult, _finalize_ramp_angles

    result = ExtractionResult(section_name="S", sector="")
    _finalize_ramp_angles(result, benches)
    return result


def test_flat_catch_berm_below_spill_toe_is_not_a_ramp():
    upper = _floor_bench((-20.000, 3139.126), (-14.778, 3128.300), 64.44, 3125.706)
    lower = _floor_bench((-2.547, 3125.515), (4.075, 3112.257), 65.00)

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(10.991, abs=0.005)
    assert lower.is_ramp is False
    assert lower.ramp_segment is False
    result = _finalized([upper, lower])
    assert result.overall_angle == pytest.approx(48.14, abs=0.01)
    assert result.inter_ramp_angle == pytest.approx(result.overall_angle, abs=0.01)


def test_gentle_descent_from_extended_toe_point_stays_a_ramp():
    upper = _floor_bench((0.0, 115.0), (12.0, 103.0), 45.0, 100.0)
    lower = _floor_bench((27.0, 97.5), (37.0, 87.5), 45.0)

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(12.0)
    assert lower.is_ramp is True
    assert lower.ramp_segment is True
    result = _finalized([upper, lower])
    assert result.inter_ramp_angle > result.overall_angle


@pytest.mark.parametrize("lower_crest_elevation", [100.0, 99.8, 96.0, 104.0])
def test_width_band_ramp_stays_a_ramp_regardless_of_elevation(lower_crest_elevation):
    upper = _floor_bench((0.0, 115.0), (12.0, 103.0), 45.0, 100.0)
    lower = _floor_bench(
        (31.3, lower_crest_elevation), (41.3, lower_crest_elevation - 10.0), 45.0
    )

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(16.3)
    assert lower.is_ramp is True


@pytest.mark.parametrize("floor_elevation", [0.0, 103.0, 105.0])
@pytest.mark.parametrize(
    "lower_crest_elevation, expected_ramp", [(100.5, True), (102.8, False)]
)
def test_bench_without_floor_extension_uses_the_toe_point(
    floor_elevation, lower_crest_elevation, expected_ramp
):
    upper = _floor_bench((0.0, 115.0), (12.0, 103.0), 45.0, floor_elevation)
    lower = _floor_bench(
        (24.0, lower_crest_elevation), (34.0, lower_crest_elevation - 10.0), 45.0
    )

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(12.0)
    assert lower.is_ramp is expected_ramp


def test_floor_below_toe_with_unusable_face_angle_is_not_extended():
    upper = _floor_bench((0.0, 115.0), (12.0, 103.0), 0.0, 100.0)
    lower = _floor_bench((24.0, 100.5), (34.0, 90.5), 45.0)

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(12.0)
    assert lower.is_ramp is True


def test_extended_toe_point_gives_distance_and_elevation_of_one_point():
    from core.bench_classify import _extended_toe_distance, _extended_toe_point

    extended = _floor_bench((0.0, 115.0), (12.0, 103.0), 45.0, 100.0)
    reversed_face = _floor_bench((12.0, 115.0), (0.0, 103.0), 45.0, 100.0)
    plain = _floor_bench((0.0, 115.0), (12.0, 103.0), 45.0)

    assert _extended_toe_point(extended) == pytest.approx((15.0, 100.0))
    assert _extended_toe_point(reversed_face) == pytest.approx((-3.0, 100.0))
    assert _extended_toe_point(plain) == pytest.approx((12.0, 103.0))
    for bench in (extended, reversed_face, plain):
        assert _extended_toe_distance(bench) == pytest.approx(_extended_toe_point(bench)[0])


def test_rising_segment_toward_the_lower_bench_is_not_a_ramp():
    upper = _floor_bench((0.0, 115.0), (12.0, 103.0), 45.0)
    lower = _floor_bench((24.0, 103.74), (34.0, 93.74), 45.0)

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(12.0)
    assert lower.is_ramp is False
    assert lower.ramp_segment is False


def test_rise_above_the_extended_toe_point_is_not_a_ramp():
    upper = _floor_bench((-20.000, 3135.999), (-16.728, 3128.907), 64.356, 3122.404)
    lower = _floor_bench((-0.202, 3123.144), (3.941, 3113.568), 66.816)

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(13.404, abs=0.005)
    assert lower.is_ramp is False
    assert lower.ramp_segment is False
    result = _finalized([upper, lower])
    assert result.inter_ramp_angle == pytest.approx(result.overall_angle, abs=0.01)


def test_descending_segment_of_twelve_metres_stays_a_ramp():
    upper = _floor_bench((0.0, 115.0), (12.0, 103.0), 45.0)
    lower = _floor_bench((24.0, 100.5), (34.0, 90.5), 45.0)

    _compute_berm_widths_from_profile([upper, lower], None, None, None)

    assert lower.berm_width == pytest.approx(12.0)
    assert lower.is_ramp is True
    assert lower.ramp_segment is True


@pytest.mark.parametrize(
    "lower_crest_elevation, expected_ramp",
    [(100.5, True), (102.8, False), (103.74, False)],
)
def test_reversed_bench_order_uses_elevation_to_find_the_upper_bench(
    lower_crest_elevation, expected_ramp
):
    lower = _floor_bench(
        (-24.0, lower_crest_elevation), (-34.0, lower_crest_elevation - 10.0), 45.0
    )
    upper = _floor_bench((0.0, 115.0), (-12.0, 103.0), 45.0)

    _compute_berm_widths_from_profile([lower, upper], None, None, None)

    assert upper.berm_width == pytest.approx(12.0)
    assert upper.is_ramp is expected_ramp
    assert upper.ramp_segment is expected_ramp


def test_segment_is_ramp_takes_signed_descent_from_upper_to_lower():
    from core.bench_classify import _segment_is_ramp

    assert _segment_is_ramp(0.0, 12.0, 103.0, 100.5, 12.0) is True
    assert _segment_is_ramp(0.0, 12.0, 103.0, 103.74, 12.0) is False
    assert _segment_is_ramp(0.0, 16.3, 103.0, 103.74, 16.3) is True
