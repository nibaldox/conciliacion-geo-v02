import numpy as np

from core.hole_section_geometry import classify_hole_segment_to_section
from core.section_cutter import SectionLine


def test_exact_crossing_reports_signed_distances_and_station():
    section = SectionLine("N", np.array([0.0, 0.0, 0.0]), 0.0, 20.0)
    result = classify_hole_segment_to_section(( -2, 0, 100), (2, 0, 90), section)
    assert result.relation == "exact_intersection"
    assert result.signed_distance_collar_m == -2
    assert result.signed_distance_toe_m == 2
    assert result.min_distance_to_section_m == 0
    assert result.along_section_collar_m == 0


def test_near_parallel_trace_is_proximity_not_intersection():
    section = SectionLine("N", np.array([0.0, 0.0, 0.0]), 0.0, 20.0)
    result = classify_hole_segment_to_section((3, -4, 100), (3, 4, 90), section,
                                              corridor_m=3)
    assert result.relation == "near_section"
    assert result.signed_distance_collar_m == result.signed_distance_toe_m == 3
    assert result.min_distance_to_section_m == 3


def test_plane_crossing_outside_finite_section_is_not_exact():
    section = SectionLine("N", np.array([0.0, 0.0, 0.0]), 0.0, 10.0)
    result = classify_hole_segment_to_section((-2, 8, 0), (2, 8, -5), section,
                                              corridor_m=2)
    assert result.relation == "outside"
    assert result.min_distance_to_section_m == 3


def test_endpoint_on_plane_and_asymmetric_section_endpoint_are_exact():
    section = SectionLine("N", np.array([0.0, 0.0, 0.0]), 0.0, 30.0,
                          length_up=20.0, length_down=10.0)
    result = classify_hole_segment_to_section((0, 20, 5), (4, 25, -5), section)
    assert result.relation == "exact_intersection"
    assert result.signed_distance_collar_m == 0


def test_incomplete_or_nonfinite_endpoint_is_not_inferred():
    section = SectionLine("N", np.array([0.0, 0.0, 0.0]), 0.0, 10.0)
    for toe in (None, (1, np.nan, 0)):
        result = classify_hole_segment_to_section((0, 0, 5), toe, section)
        assert result.relation == "incomplete"
        assert result.min_distance_to_section_m is None


def test_outside_limits_with_zero_corridor_and_parallel_on_plane():
    section = SectionLine("E", np.array([0.0, 0.0, 0.0]), 90.0, 10.0)
    result = classify_hole_segment_to_section((8, 0, 5), (12, 0, 0), section,
                                              corridor_m=0)
    assert result.relation == "outside"
    assert np.isclose(result.min_distance_to_section_m, 3)

    overlap = classify_hole_segment_to_section((-2, 0, 5), (2, 0, 0), section,
                                               corridor_m=0)
    assert overlap.relation == "exact_intersection"


def test_degenerate_hole_point_on_plane_is_exact_and_off_plane_uses_corridor():
    section = SectionLine("N", np.array([0.0, 0.0]), 0.0, 20.0)
    crossing_point = classify_hole_segment_to_section((0, 3, 10), (0, 3, 10), section)
    assert crossing_point.relation == "exact_intersection"
    assert crossing_point.min_distance_to_section_m == 0

    nearby_point = classify_hole_segment_to_section((2, 3, 10), (2, 3, 10), section,
                                                    corridor_m=2)
    assert nearby_point.relation == "near_section"
    assert nearby_point.min_distance_to_section_m == 2


def test_malformed_or_nonfinite_endpoints_return_incomplete():
    section = SectionLine("N", np.array([0.0, 0.0]), 0.0, 20.0)
    for point in (None, (1, np.nan, 2), (1, 2, np.nan), (np.inf, 2, 3), ("bad", 1, 2), (1,)):
        result = classify_hole_segment_to_section(point, (0, 0, 0), section)
        assert result.relation == "incomplete"
        assert result.signed_distance_collar_m is None
        assert result.min_distance_to_section_m is None


def test_asymmetric_section_includes_both_signed_finite_endpoints_only():
    section = SectionLine("N", np.array([0.0, 0.0]), 0.0, 30.0,
                          length_up=20.0, length_down=10.0)
    for station in (-10.0, 20.0):
        result = classify_hole_segment_to_section((-1, station, 1), (1, station, 0), section)
        assert result.relation == "exact_intersection"
    beyond = classify_hole_segment_to_section((-1, 20.01, 1), (1, 20.01, 0), section,
                                              corridor_m=0.009)
    assert beyond.relation == "outside"


def test_numeric_tolerance_is_distance_based_and_invalid_section_lengths_rejected():
    section = SectionLine("N", np.array([0.0, 0.0]), 0.0, 20.0)
    almost_crossing = classify_hole_segment_to_section(
        (5e-7, 0, 1), (5e-7, 0, 0), section,
        corridor_m=0, numeric_tolerance_m=1e-6,
    )
    assert almost_crossing.relation == "exact_intersection"
    assert almost_crossing.min_distance_to_section_m <= 1e-6

    invalid = SectionLine("N", np.array([0.0, 0.0]), 0.0, 30.0,
                          length_up=-1.0, length_down=31.0)
    import pytest
    with pytest.raises(ValueError):
        classify_hole_segment_to_section((-1, 0, 1), (1, 0, 0), invalid)

