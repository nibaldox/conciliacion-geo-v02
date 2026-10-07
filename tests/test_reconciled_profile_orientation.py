import numpy as np
import pytest

from api.routers.process import _legacy_reconciled_to_dict, _reconciled_profile_to_dict
from core.profile_compliance import build_reconciled_profile_v2
from core.profile_extract import BenchParams


def _bench(number, crest_d, crest_e, toe_d, toe_e, *, is_ramp=False):
    return BenchParams(
        bench_number=number,
        crest_elevation=crest_e,
        crest_distance=crest_d,
        toe_elevation=toe_e,
        toe_distance=toe_d,
        bench_height=abs(crest_e - toe_e),
        face_angle=float(np.degrees(np.arctan2(abs(crest_e - toe_e), abs(crest_d - toe_d)))),
        berm_width=0.0,
        is_ramp=is_ramp,
    )


@pytest.mark.parametrize(
    ("distances", "elevations", "bench", "floor_elevation", "expected_direction"),
    [
        (
            np.linspace(-30.0, 27.0, 58),
            np.linspace(2929.0, 2974.0, 58),
            _bench(1, 27.0, 2974.0, -28.0, 2930.6),
            2929.0,
            -1.0,
        ),
        (
            np.linspace(10.0, 0.0, 11),
            np.linspace(110.0, 100.0, 11),
            _bench(1, 10.0, 110.0, 1.0, 101.0),
            100.0,
            -1.0,
        ),
    ],
)
def test_profile_traversal_and_floor_follow_source_profile_edge(
    distances, elevations, bench, floor_elevation, expected_direction,
):
    profile = build_reconciled_profile_v2(
        [bench],
        source="topo",
        profile=(distances, elevations),
        floor_elevation=floor_elevation,
    )
    payload = _reconciled_profile_to_dict(profile)

    assert len(profile.points) == len(profile.distances) == len(profile.elevations)
    assert len(payload["segments"]) == len(payload["distances"])
    assert payload["distances"] == pytest.approx([point.distance for point in profile.points])
    assert payload["elevations"] == pytest.approx([point.elevation for point in profile.points])
    assert all(
        (second - first) * expected_direction >= -1e-9
        for first, second in zip(profile.distances, profile.distances[1:])
    )
    assert profile.points[-1].segment_type == "floor"
    floor_index = int(np.argmin(np.abs(elevations - floor_elevation)))
    assert profile.points[-1].distance == pytest.approx(distances[floor_index])
    assert profile.points[-1].elevation == pytest.approx(floor_elevation)
    assert profile.points[-1].distance != pytest.approx(
        distances[-1 if floor_index == 0 else 0],
    )


def test_profile_traversal_reverses_monotonic_bench_list_without_global_sort():
    distances = np.linspace(0.0, 20.0, 21)
    elevations = 100.0 + distances
    benches = [
        _bench(1, 5.0, 105.0, 0.0, 100.0),
        _bench(2, 15.0, 115.0, 10.0, 110.0),
    ]

    profile = build_reconciled_profile_v2(
        benches,
        profile=(distances, elevations),
        floor_elevation=100.0,
    )

    assert profile.points[0].bench_number == 2
    assert profile.points[-1].segment_type in {"toe", "floor"}
    assert profile.points[-1].distance == pytest.approx(distances[0])
    assert profile.points[-1].elevation == pytest.approx(elevations[0])
    assert [point.bench_number for point in profile.points if point.segment_type == "crest"] == [2, 1]
    assert all(np.diff(profile.distances) <= 1e-9)
    assert len(profile.points) == len(profile.distances) == len(profile.elevations)


def test_legacy_api_inserts_floor_at_source_endpoint_in_sorted_arrays():
    distances = np.linspace(-30.0, 27.0, 58)
    elevations = np.linspace(2929.0, 2974.0, 58)
    bench = _bench(1, 27.0, 2974.0, -28.0, 2930.6)
    rich = build_reconciled_profile_v2(
        [bench],
        profile=(distances, elevations),
        floor_elevation=2929.0,
    )
    floor_point = [point for point in rich.points if point.segment_type == "floor"][-1]

    legacy = _legacy_reconciled_to_dict(
        [bench],
        floor_elevation=2929.0,
        floor_point=(floor_point.distance, floor_point.elevation),
        floor_resolved_from_profile=True,
    )

    assert legacy["distances"] == sorted(legacy["distances"])
    assert legacy["distances"][0] == pytest.approx(distances[0])
    assert legacy["elevations"][0] == pytest.approx(2929.0)
    assert legacy["distances"][-1] == pytest.approx(27.0)
    assert legacy["elevations"][-1] == pytest.approx(2974.0)


def test_profile_order_keeps_ramp_transition_without_berm_corner():
    distances = np.array([0.0, 2.0, 5.0, 10.0, 12.0, 15.0, 20.0])
    elevations = np.array([100.0, 105.0, 112.0, 110.0, 115.0, 120.0, 120.0])
    benches = [
        _bench(1, 5.0, 112.0, 0.0, 100.0, is_ramp=True),
        _bench(2, 15.0, 120.0, 10.0, 110.0),
    ]

    profile = build_reconciled_profile_v2(
        benches,
        profile=(distances, elevations),
        floor_elevation=100.0,
    )

    assert any(point.segment_type == "ramp" for point in profile.points)
    assert not any(point.segment_type == "berm_top" for point in profile.points)
