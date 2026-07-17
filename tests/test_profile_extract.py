"""Unit tests for profile extraction public data models and orchestrator."""

import json

import numpy as np
import pandas as pd
import pytest

from core.profile_extract import (
    BenchParams,
    ReconciledPoint,
    ReconciledProfile,
    extract_parameters,
)


def _bench(number=1, **overrides):
    values = {
        "bench_number": number,
        "crest_elevation": 100.0,
        "crest_distance": 5.0,
        "toe_elevation": 85.0,
        "toe_distance": 10.0,
        "bench_height": 15.0,
        "face_angle": 70.0,
        "berm_width": 8.0,
    }
    values.update(overrides)
    return BenchParams(**values)


def test_extract_parameters_detects_synthetic_single_bench():
    distances = np.linspace(0.0, 20.0, 41)
    elevations = np.where(
        distances <= 5.0,
        100.0,
        np.where(distances <= 10.0, 100.0 - 3.0 * (distances - 5.0), 85.0),
    )

    result = extract_parameters(distances, elevations, "S-01", "North")

    assert result.section_name == "S-01"
    assert result.sector == "North"
    assert len(result.benches) == 1
    bench = result.benches[0]
    assert bench.bench_height == pytest.approx(15.0)
    assert bench.face_angle == pytest.approx(71.565, abs=0.01)
    assert bench.crest_distance == pytest.approx(5.0)
    assert bench.toe_distance == pytest.approx(10.0)


@pytest.mark.parametrize(
    "distances,elevations",
    [
        (np.array([]), np.array([])),
        (np.array([0.0]), np.array([100.0])),
        (np.array([0.0, 1.0]), np.array([100.0, 99.0])),
    ],
)
def test_extract_parameters_short_profiles_return_empty_result(distances, elevations):
    result = extract_parameters(distances, elevations, "S-empty", "Test")
    assert result.benches == []
    assert result.inter_ramp_angle == 0.0
    assert result.overall_angle == 0.0


def test_extract_parameters_nan_sample_does_not_leak_nan_geometry():
    result = extract_parameters(
        np.array([0.0, 1.0, 2.0]),
        np.array([100.0, np.nan, 90.0]),
        "S-nan",
        "Test",
    )
    assert result.benches
    for bench in result.benches:
        assert np.isfinite(
            [
                bench.crest_distance,
                bench.crest_elevation,
                bench.toe_distance,
                bench.toe_elevation,
                bench.bench_height,
                bench.face_angle,
            ]
        ).all()


def test_reconciled_profile_round_trip_is_json_serializable():
    profile = ReconciledProfile(
        distances=np.array([0.0, 5.0]),
        elevations=np.array([100.0, 85.0]),
        points=[
            ReconciledPoint(0.0, 100.0, 1, "crest", "design"),
            ReconciledPoint(5.0, 85.0, 1, "toe", "design"),
        ],
    )

    snapshot = profile.to_dict()
    restored = ReconciledProfile.from_dict({**snapshot, "ignored": "value"})

    json.dumps(snapshot, allow_nan=False)
    np.testing.assert_allclose(restored.distances, profile.distances)
    np.testing.assert_allclose(restored.elevations, profile.elevations)
    assert restored.points == profile.points


def test_reconciled_profile_summary_and_dataframe_include_hazards():
    profile = ReconciledProfile(
        distances=np.array([0.0, 5.0, 9.0]),
        elevations=np.array([100.0, 85.0, 84.0]),
        points=[
            ReconciledPoint(0.0, 100.0, 1, "crest"),
            ReconciledPoint(5.0, 85.0, 1, "toe"),
            ReconciledPoint(9.0, 84.0, 2, "ramp"),
        ],
    )
    benches = [
        _bench(1, overhang_m=1.2, wedge_risk=True, n_detection_methods_agreeing=3),
        _bench(2, face_angle=60.0, berm_width=4.0, toppling_risk=True),
    ]

    summary = profile.summary(benches)
    frame = profile.to_dataframe(benches)

    assert summary["n_benches"] == 2
    assert summary["n_ramps"] == 1
    assert summary["n_overhangs"] == 1
    assert summary["n_wedge_risks"] == 1
    assert summary["n_toppling_risks"] == 1
    assert summary["total_berm_width_m"] == pytest.approx(12.0)
    assert list(frame.columns) == [
        "bench_number",
        "segment_type",
        "distance_m",
        "elevation_m",
        "is_ramp",
        "source",
        "overhang_m",
        "wedge_risk",
        "toppling_risk",
    ]
    assert frame.loc[2, "is_ramp"] == np.bool_(True)
    assert frame.loc[0, "overhang_m"] == pytest.approx(1.2)


def test_empty_reconciled_profile_has_stable_schema_and_defaults():
    profile = ReconciledProfile(np.array([]), np.array([]))
    assert list(profile.to_dataframe().columns) == [
        "bench_number", "segment_type", "distance_m", "elevation_m", "is_ramp", "source"
    ]
    assert profile.summary()["height_range_m"] == (0.0, 0.0)
    assert profile.to_dict()["source"] == "topo"
