import numpy as np
import pytest

from core import extract_parameters
from core import profile_extract


def mixed_profile():
    distances = np.array([0.0, 10.0, 20.0, 30.0, 40.0])
    changes = 10.0 * np.tan(np.radians([35.0, 12.0, 60.0]))
    elevations = 100.0 - np.array([0.0, 0.0, changes[0], changes[0] + changes[1], sum(changes)])
    return distances, elevations


def classify_through_extraction(monkeypatch, face_threshold, berm_threshold):
    seen = []
    original = profile_extract._merge_adjacent_segments

    def capture(types):
        seen.append(types.copy())
        return original(types)

    with monkeypatch.context() as patch:
        patch.setattr(profile_extract, "_merge_adjacent_segments", capture)
        result = extract_parameters(*mixed_profile(), "mixed_angles", "baseline", face_threshold=face_threshold, berm_threshold=berm_threshold)
    return seen[0].tolist(), result


def test_face_threshold_controls_initial_classification(monkeypatch):
    low, low_result = classify_through_extraction(monkeypatch, 30, 10)
    high, high_result = classify_through_extraction(monkeypatch, 40, 10)
    assert low == [2, 1, 0, 1]
    assert high == [2, 0, 0, 1]
    assert len(low_result.benches) == 2
    assert len(high_result.benches) == 1


def test_berm_threshold_controls_initial_classification(monkeypatch):
    low, _ = classify_through_extraction(monkeypatch, 30, 10)
    high, _ = classify_through_extraction(monkeypatch, 30, 15)
    assert low == [2, 1, 0, 1]
    assert high == [2, 1, 2, 1]


def test_solid_toe_receives_configured_face_threshold(monkeypatch):
    seen = []
    original = profile_extract._detect_and_project_solid_toe

    def capture(points, threshold):
        seen.append(threshold)
        return original(points, threshold)

    monkeypatch.setattr(profile_extract, "_detect_and_project_solid_toe", capture)
    extract_parameters(*mixed_profile(), "test", "test", face_threshold=40)
    assert seen and all(value == 40 for value in seen)


def test_default_extraction_matches_prechange_golden():
    result = extract_parameters(*mixed_profile(), "mixed_angles", "baseline")
    actual = [(b.bench_height, b.face_angle, b.berm_width, b.bench_number) for b in result.benches]
    expected = [(8.064858190447211, 50.52421587479905, 0.0, 1), (17.320508075688764, 50.52421587479905, 9.124663612500282, 2)]
    assert len(actual) == len(expected)
    for actual_bench, expected_bench in zip(actual, expected):
        for actual_value, expected_value in zip(actual_bench, expected_bench):
            assert type(actual_value) is type(expected_value)
            if isinstance(expected_value, float):
                assert actual_value == pytest.approx(expected_value, rel=1e-9, abs=1e-9)
            else:
                assert actual_value == expected_value
    assert result.overall_angle == pytest.approx(41.399560806115595, rel=1e-9, abs=1e-9)
    assert result.inter_ramp_angle == pytest.approx(51.716218287195055, rel=1e-9, abs=1e-9)
