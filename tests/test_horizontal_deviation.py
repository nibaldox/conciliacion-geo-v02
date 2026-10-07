import pytest

from core import (
    HorizontalFaceGeometry,
    classify_horizontal_deviation,
    compute_horizontal_deviation,
    measure_horizontal_deviation_at_elevation,
    profile_intersections_at_elevation,
)


def _face(crest_distance=10.0, toe_distance=0.0, height=10.0):
    return HorizontalFaceGeometry(
        bench_number=1,
        crest_distance=crest_distance,
        crest_elevation=10.0,
        toe_distance=toe_distance,
        toe_elevation=0.0,
        bench_height=height,
    )


def test_horizontal_debt_is_measured_at_equal_elevation_without_bench_pairing():
    result = compute_horizontal_deviation(
        ([0.0, 10.0], [0.0, 10.0]),
        ([8.0, 18.0], [0.0, 10.0]),
        [_face()],
    )

    assert [point.deviation_m for point in result.points] == pytest.approx([8.0, 8.0])
    assert all(point.category == "overbreak_severe" for point in result.points)


@pytest.mark.parametrize(
    ("crest_distance", "toe_distance", "topo_distance", "expected"),
    [
        (10.0, 0.0, 7.0, 2.0),
        (0.0, 10.0, 3.0, 2.0),
        (10.0, 0.0, 3.0, -2.0),
        (0.0, 10.0, 7.0, -2.0),
    ],
)
def test_sign_uses_design_crest_to_toe_orientation(
    crest_distance, toe_distance, topo_distance, expected
):
    face = _face(crest_distance=crest_distance, toe_distance=toe_distance)
    design_x = [0.0, 10.0]
    design_z = [0.0, 10.0] if crest_distance == 10.0 else [10.0, 0.0]
    measurement = measure_horizontal_deviation_at_elevation(
        design_x, design_z, 5.0, topo_distance, face
    )

    assert measurement.deviation_m == pytest.approx(expected)


def test_zero_offset_is_within_tolerance():
    measurement = measure_horizontal_deviation_at_elevation(
        [0.0, 10.0], [0.0, 10.0], 5.0, 5.0, _face()
    )

    assert measurement.deviation_m == pytest.approx(0.0)
    assert measurement.category == "within_tolerance"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_deviation_is_unmeasured(value):
    assert classify_horizontal_deviation(value) == "unmeasured"


def test_inclined_plane_with_constant_horizontal_offset_keeps_that_offset():
    design_d = [0.0, 10.0]
    design_z = [100.0, 110.0]
    face = HorizontalFaceGeometry(1, 10.0, 110.0, 0.0, 100.0, 10.0)
    measurement = measure_horizontal_deviation_at_elevation(
        design_d, design_z, 105.0, 7.0, face
    )

    assert measurement.design_distance_m == pytest.approx(5.0)
    assert measurement.deviation_m == pytest.approx(2.0)


def test_intersection_deduplicates_shared_vertex():
    hit = profile_intersections_at_elevation([0.0, 5.0, 10.0], [0.0, 5.0, 10.0], 5.0)

    assert hit.status == "measured"
    assert hit.distance_m == pytest.approx(5.0)
    assert hit.candidate_distances_m == pytest.approx((5.0,))


def test_ambiguous_and_missing_crossings_are_unassessed_without_extrapolation():
    face = HorizontalFaceGeometry(1, 20.0, 10.0, 0.0, 0.0, 10.0)
    ambiguous = measure_horizontal_deviation_at_elevation(
        [0.0, 10.0, 20.0], [0.0, 10.0, 0.0], 5.0, 7.0, face
    )
    missing = measure_horizontal_deviation_at_elevation(
        [0.0, 10.0, 20.0], [0.0, 10.0, 0.0], 11.0, 7.0, face
    )

    assert ambiguous.status == "ambiguous"
    assert ambiguous.deviation_m is None
    assert ambiguous.category == "unmeasured"
    assert missing.status == "missing"
    assert missing.deviation_m is None


def test_reference_heights_follow_each_detected_design_bench_height():
    faces = [
        HorizontalFaceGeometry(1, 10.0, 10.0, 0.0, 0.0, 10.0),
        HorizontalFaceGeometry(2, 30.0, 30.0, 10.0, 10.0, 20.0),
    ]
    result = compute_horizontal_deviation(
        ([0.0, 10.0, 20.0, 30.0], [0.0, 10.0, 20.0, 30.0]),
        ([1.0, 11.0, 21.0, 31.0], [0.0, 10.0, 20.0, 30.0]),
        faces,
    )

    assert [sample.height_above_toe_m for sample in result.samples] == pytest.approx(
        [2.0, 5.0, 8.0, 4.0, 10.0, 16.0]
    )
    assert [sample.elevation_m for sample in result.samples] == pytest.approx(
        [2.0, 5.0, 8.0, 14.0, 20.0, 26.0]
    )
    assert [sample.deviation_m for sample in result.samples] == pytest.approx([1.0] * 6)


def test_invalid_reference_height_serializes_as_no_data():
    face = HorizontalFaceGeometry(1, 10.0, 10.0, 0.0, float("nan"), 10.0)
    result = compute_horizontal_deviation(
        ([0.0, 10.0], [0.0, 10.0]),
        ([1.0, 11.0], [0.0, 10.0]),
        [face],
    )

    assert all(sample.height_above_toe_m is None for sample in result.samples)
    assert all(sample.elevation_m is None for sample in result.samples)
    assert all(item["value"] is None for item in result.to_dict()["samples"])


def test_face_height_uses_toe_to_crest_geometry_when_bench_height_includes_floor():
    face = HorizontalFaceGeometry(1, 15.0, 115.0, 0.0, 100.0, 20.0)
    result = compute_horizontal_deviation(
        ([0.0, 15.0], [100.0, 115.0]),
        ([1.0, 16.0], [100.0, 115.0]),
        [face],
    )

    assert [sample.height_above_toe_m for sample in result.samples] == pytest.approx(
        [3.0, 7.5, 12.0]
    )
    assert [sample.elevation_m for sample in result.samples] == pytest.approx(
        [103.0, 107.5, 112.0]
    )
    assert [sample.deviation_m for sample in result.samples] == pytest.approx(
        [1.0, 1.0, 1.0]
    )


@pytest.mark.parametrize(
    ("topo_profile", "expected_status", "expected_deviation"),
    [
        (([0.0, 10.0], [0.0, 10.0]), "measured", [0.0, 0.0, 0.0]),
        (([2.0, 12.0], [0.0, 10.0]), "measured", [2.0, 2.0, 2.0]),
        (([0.0, 10.0, 20.0, 30.0], [0.0, 10.0, 0.0, 10.0]), "ambiguous", [None, None, None]),
        (([0.0, 10.0], [20.0, 30.0]), "missing", [None, None, None]),
    ],
)
def test_ramp_face_keeps_horizontal_measurement_when_profile_crossings_allow_it(
    topo_profile, expected_status, expected_deviation
):
    ramp_face = HorizontalFaceGeometry(
        bench_number=1,
        crest_distance=10.0,
        crest_elevation=10.0,
        toe_distance=0.0,
        toe_elevation=0.0,
        bench_height=10.0,
        is_ramp=True,
    )
    result = compute_horizontal_deviation(
        ([0.0, 10.0], [0.0, 10.0]),
        topo_profile,
        [ramp_face],
    )

    assert [sample.status for sample in result.samples] == [expected_status] * 3
    for sample, expected in zip(result.samples, expected_deviation):
        if expected is None:
            assert sample.deviation_m is None
        else:
            assert sample.deviation_m == pytest.approx(expected)
