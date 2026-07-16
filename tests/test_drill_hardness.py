"""Parity tests for core.drill_hardness against dureza_relativa/classification.py."""
from __future__ import annotations

import math

import pytest

from core.drill_hardness import (
    DEFAULT_THRESHOLDS,
    DURATION_INDEX_UPPER_SATURATION,
    STD_EPSILON,
    Thresholds,
    classify_duracion,
    classify_with_metric,
    hardness_index,
    hardness_index_with_metric,
    penetration_rate,
    rig_mean_penetration,
    rig_normalized_penetration,
)


def test_classify_duracion_boundaries():
    assert classify_duracion(0) == "roca suave"
    assert classify_duracion(15.9) == "roca suave"
    assert classify_duracion(16) == "roca media"
    assert classify_duracion(20) == "roca media"
    assert classify_duracion(24) == "roca dura"
    assert classify_duracion(30) == "roca dura"
    assert classify_duracion(40) == "roca muy dura"
    assert classify_duracion(120) == "roca muy dura"


def test_classify_with_metric_strict_upper_at_cutoff():
    assert classify_with_metric(16.0, DEFAULT_THRESHOLDS, "duration") == "roca media"


def test_classify_with_metric_rate_inverted_cutoff():
    assert classify_with_metric(1.0, DEFAULT_THRESHOLDS, "penetration_rate") == "roca media"
    assert classify_with_metric(0.4, DEFAULT_THRESHOLDS, "penetration_rate") == "roca muy dura"
    assert classify_with_metric(0.7, DEFAULT_THRESHOLDS, "penetration_rate") == "roca dura"
    assert classify_with_metric(2.0, DEFAULT_THRESHOLDS, "penetration_rate") == "roca suave"


def test_classify_with_metric_unknown_raises():
    with pytest.raises(ValueError):
        classify_with_metric(10.0, DEFAULT_THRESHOLDS, "bogus")


def test_classify_with_metric_none_propagates():
    assert classify_with_metric(None, DEFAULT_THRESHOLDS, "duration") is None


def test_hardness_index_piecewise():
    assert hardness_index(-1) == 0.0
    assert hardness_index(0) == 0.0
    assert hardness_index(16) == pytest.approx(25.0)
    assert hardness_index(24) == pytest.approx(50.0)
    assert hardness_index(40) == pytest.approx(75.0)
    assert hardness_index(60) == pytest.approx(100.0)
    assert hardness_index(120) == 100.0


def test_hardness_index_with_metric_duration_segments():
    assert hardness_index_with_metric(0, DEFAULT_THRESHOLDS, "duration") == 0.0
    assert hardness_index_with_metric(16, DEFAULT_THRESHOLDS, "duration") == pytest.approx(25.0)
    assert hardness_index_with_metric(60, DEFAULT_THRESHOLDS, "duration") == pytest.approx(100.0)
    assert hardness_index_with_metric(120, DEFAULT_THRESHOLDS, "duration") == 100.0


def test_hardness_index_with_metric_rate_upper_saturation_zero():
    assert hardness_index_with_metric(2.5, DEFAULT_THRESHOLDS, "penetration_rate") == 0.0
    assert hardness_index_with_metric(2.0, DEFAULT_THRESHOLDS, "penetration_rate") == 0.0


def test_hardness_index_with_metric_rate_inverted():
    assert hardness_index_with_metric(1.0, DEFAULT_THRESHOLDS, "penetration_rate") == pytest.approx(25.0)
    assert hardness_index_with_metric(0.7, DEFAULT_THRESHOLDS, "penetration_rate") == pytest.approx(50.0)
    assert hardness_index_with_metric(0.4, DEFAULT_THRESHOLDS, "penetration_rate") == pytest.approx(75.0)
    assert hardness_index_with_metric(0.0, DEFAULT_THRESHOLDS, "penetration_rate") == pytest.approx(100.0)


def test_hardness_index_with_metric_none_propagates():
    assert hardness_index_with_metric(None, DEFAULT_THRESHOLDS, "duration") is None


def test_hardness_index_with_metric_rig_normalized_calls_rate_branch():
    assert (
        hardness_index_with_metric(1.0, DEFAULT_THRESHOLDS, "rig_normalized_penetration")
        == hardness_index_with_metric(1.0, DEFAULT_THRESHOLDS, "penetration_rate")
    )


def test_penetration_rate_basic():
    assert penetration_rate(17, 19) == pytest.approx(17 / 19)


def test_penetration_rate_zero_duration_returns_none():
    assert penetration_rate(10, 0) is None
    assert penetration_rate(10, -1) is None


def test_penetration_rate_non_finite():
    assert penetration_rate(float("nan"), 10) is None
    assert penetration_rate(10, float("inf")) is None


def test_penetration_rate_none_inputs():
    assert penetration_rate(None, 10) is None
    assert penetration_rate(10, None) is None


def test_rig_mean_penetration_basic():
    assert rig_mean_penetration([0.5, 0.7, 0.9]) == pytest.approx(0.7)


def test_rig_mean_penetration_skips_none_and_nan():
    assert rig_mean_penetration([0.6, None, 0.8, float("nan")]) == pytest.approx(0.7)


def test_rig_mean_penetration_empty_returns_none():
    assert rig_mean_penetration([]) is None
    assert rig_mean_penetration([None, float("nan")]) is None


def test_rig_normalized_penetration_zero_variance():
    assert rig_normalized_penetration(0.8, rig_avg=1.0, rig_std=1e-12) == 0.0
    assert rig_normalized_penetration(0.8, rig_avg=1.0, rig_std=0.0) == 0.0


def test_rig_normalized_penetration_finite_positive():
    assert rig_normalized_penetration(1.2, rig_avg=1.0, rig_std=0.4) == pytest.approx(0.5)


def test_rig_normalized_penetration_finite_negative():
    assert rig_normalized_penetration(0.8, rig_avg=1.0, rig_std=0.4) == pytest.approx(-0.5)


def test_rig_normalized_penetration_none_or_nonfinite_returns_zero():
    assert rig_normalized_penetration(None, 1.0, 0.5) == 0.0
    assert rig_normalized_penetration(float("nan"), 1.0, 0.5) == 0.0


def test_thresholds_typed_dict_shape():
    t: Thresholds = DEFAULT_THRESHOLDS
    assert t["duration"]["soft"] == 16.0
    assert t["duration"]["medium"] == 24.0
    assert t["duration"]["hard"] == 40.0
    assert t["rate"]["soft"] == 1.0
    assert t["rate"]["medium"] == 0.7
    assert t["rate"]["hard"] == 0.4


def test_parity_penetration_rate_with_source_values():
    for depth, duration in [(17, 19), (10, 5), (20, 8), (15, 30)]:
        assert penetration_rate(depth, duration) == pytest.approx(depth / duration)


def test_parity_classify_duracion_matches_source():
    for value, expected in [
        (0, "roca suave"), (10, "roca suave"), (16, "roca media"),
        (20, "roca media"), (24, "roca dura"), (30, "roca dura"),
        (40, "roca muy dura"), (60, "roca muy dura"),
    ]:
        assert classify_duracion(value) == expected


def test_module_constants():
    assert DURATION_INDEX_UPPER_SATURATION == 60.0
    assert STD_EPSILON == 1e-9
