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
