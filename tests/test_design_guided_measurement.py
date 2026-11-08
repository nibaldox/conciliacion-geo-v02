"""Tests for the design-guided measurement module.

The module measures every design bench against the raw as-built profile
without relying on the as-built segmentation, so design benches whose
as-built pair was lost to a MISSING/EXTRA split still get evaluated.
"""

import math

import numpy as np
import pytest

from core.design_guided_measurement import (
    BENCH_STATE_AMBIGUOUS,
    BENCH_STATE_NOT_EXCAVATED,
    BENCH_STATE_SECTION_TRUNCATED,
    DEFAULTS,
    DesignGuidedBench,
    DesignGuidedDefaults,
    measure_design_benches,
)
from core.profile_extract import BenchParams

STATUS_MEASURED = "measured"
STATUS_NO_CROSSING = "no_crossing"
STATUS_OUT_OF_PROFILE = "out_of_profile"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_INSUFFICIENT_POINTS = "insufficient_points"


def _prof(pts, res=0.1):
    pts = np.asarray(pts, dtype=float)
    d_out, e_out = [], []
    for i in range(len(pts) - 1):
        d0, e0 = pts[i]
        d1, e1 = pts[i + 1]
        span = d1 - d0
        steps = max(1, int(math.ceil(abs(span) / res)))
        if i == 0:
            d_out.append(d0)
            e_out.append(e0)
        for s in range(1, steps + 1):
            f = s / steps
            d_out.append(d0 + f * span)
            e_out.append(e0 + f * (e1 - e0))
    return np.array(d_out), np.array(e_out)


def _bench(bench_number, crest_d, crest_e, toe_d, toe_e):
    height = abs(crest_e - toe_e)
    dx = abs(crest_d - toe_d)
    angle = math.degrees(math.atan2(height, dx)) if dx > 1e-9 else 90.0
    return BenchParams(
        bench_number=bench_number,
        crest_elevation=float(crest_e),
        crest_distance=float(crest_d),
        toe_elevation=float(toe_e),
        toe_distance=float(toe_d),
        bench_height=float(height),
        face_angle=float(angle),
        berm_width=0.0,
    )


def test_ideal_bench_zero_deltas_and_exact_angle():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([(-5, 100), (0, 100), (10, 85), (15, 85)])
    out = measure_design_benches(design, d, e)
    assert len(out) == 1
    b = out[0]
    assert b.crest_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.crest_asbuilt_d == pytest.approx(0.0)
    assert b.toe_asbuilt_d == pytest.approx(10.0)
    assert b.delta_crest == pytest.approx(0.0)
    assert b.delta_toe == pytest.approx(0.0)
    assert b.face_angle_asbuilt == pytest.approx(56.31, abs=0.1)
    assert b.face_angle_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(15.0, abs=0.01)
    assert b.height_status == STATUS_MEASURED
    assert b.berm_status == STATUS_NO_CROSSING


def test_horizontal_displacement_exact_signed_delta():
    design = [_bench(1, crest_d=10.0, crest_e=100.0, toe_d=0.0, toe_e=85.0)]
    d, e = _prof([(0, 85), (2, 85), (12, 100), (14, 100)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.crest_asbuilt_d == pytest.approx(12.0)
    assert b.toe_asbuilt_d == pytest.approx(2.0)
    assert b.delta_crest == pytest.approx(2.0)
    assert b.delta_toe == pytest.approx(2.0)


def test_negative_displacement_flips_sign():
    design = [_bench(1, crest_d=10.0, crest_e=100.0, toe_d=0.0, toe_e=85.0)]
    d, e = _prof([(-2, 85), (0, 85), (8, 100), (10, 100)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.crest_asbuilt_d == pytest.approx(8.0)
    assert b.toe_asbuilt_d == pytest.approx(0.0)
    assert b.delta_crest == pytest.approx(-2.0)
    assert b.delta_toe == pytest.approx(0.0)


def test_intermediate_step_still_single_bench():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([
        (-5, 100), (0, 100), (4, 90), (4.5, 87.5), (10, 85), (15, 85),
    ])
    out = measure_design_benches(design, d, e)
    assert len(out) == 1
    b = out[0]
    assert b.crest_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.face_angle_status == STATUS_MEASURED
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(15.0, abs=0.01)


def test_split_bench_height_not_fragmented():
    design = [_bench(1, crest_d=0.0, crest_e=315.0, toe_d=15.0, toe_e=300.0)]
    d, e = _prof([
        (-5, 315), (0, 315), (12.64, 302.36), (13.44, 302.36),
        (16.88, 300), (20, 300),
    ])
    out = measure_design_benches(design, d, e)
    assert len(out) == 1
    b = out[0]
    assert b.height_asbuilt == pytest.approx(15.0, abs=0.05)
    assert b.height_status == STATUS_MEASURED
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_d == pytest.approx(15.88, abs=0.5)


def test_profile_below_target_out_of_profile():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([(0, 95), (10, 80)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.crest_asbuilt_status == STATUS_OUT_OF_PROFILE
    assert b.crest_asbuilt_d is None
    assert b.delta_crest is None
    assert b.height_asbuilt is None
    assert b.height_status == STATUS_OUT_OF_PROFILE


def test_two_crossings_nearest_selected():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([
        (-6, 99), (-4, 100), (-2, 99), (1, 100), (2, 99), (10, 85), (12, 85),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.crest_asbuilt_status == STATUS_MEASURED
    assert b.crest_asbuilt_d == pytest.approx(1.0, abs=0.01)


def test_two_crossings_ambiguous_within_ambiguous_window():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([
        (-5, 100), (1, 100), (2, 98), (3.5, 100), (4.5, 98),
        (10, 85), (12, 85),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.crest_asbuilt_status == STATUS_AMBIGUOUS
    assert b.crest_asbuilt_d is None


def test_insufficient_points_face_angle():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=0.0, toe_e=85.0)]
    d, e = _prof([(0, 100), (0, 85)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.face_angle_status == STATUS_INSUFFICIENT_POINTS
    assert b.face_angle_asbuilt is None


def test_berm_width_two_benches():
    design = [
        _bench(1, crest_d=0.0, crest_e=115.0, toe_d=10.0, toe_e=100.0),
        _bench(2, crest_d=18.0, crest_e=100.0, toe_d=28.0, toe_e=85.0),
    ]
    d, e = _prof([
        (-5, 115), (0, 115), (10, 100), (18, 100), (28, 85), (33, 85),
    ])
    out = measure_design_benches(design, d, e)
    assert len(out) == 2
    top, low = out
    assert top.berm_status == STATUS_NO_CROSSING
    assert top.berm_asbuilt is None
    assert low.berm_status == STATUS_MEASURED
    assert low.berm_asbuilt == pytest.approx(8.0, abs=0.01)


def test_empty_design_returns_empty():
    assert measure_design_benches([], np.array([0.0, 1.0]), np.array([1.0, 2.0])) == []


def test_defaults_frozen_and_window_recorded():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([(-5, 100), (0, 100), (10, 85), (15, 85)])
    out = measure_design_benches(design, d, e)
    assert out[0].window_used_m == DEFAULTS.crossing_window_m
    custom = DesignGuidedDefaults(crossing_window_m=3.0)
    out2 = measure_design_benches(design, d, e, defaults=custom)
    assert out2[0].window_used_m == 3.0


def test_solid_toe_on_high_floor_intersects_local_floor():
    design = [_bench(1, crest_d=0.0, crest_e=3095.0, toe_d=14.02, toe_e=3080.0)]
    d, e = _prof([
        (-5, 3096), (0.5, 3095.5), (13.0, 3081.3), (40, 3081.3),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_d == pytest.approx(13.0, abs=0.3)
    assert b.toe_asbuilt_d < 18.0
    assert b.floor_offset_m == pytest.approx(1.3, abs=0.15)
    assert b.floor_offset_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(14.2, abs=0.4)


def test_solid_toe_when_floor_slightly_below_design_toe_uses_design_toe():
    design = [_bench(1, crest_d=0.0, crest_e=3095.0, toe_d=14.02, toe_e=3080.0)]
    d, e = _prof([
        (-5, 3096), (0.5, 3095.5), (12.4, 3079.9), (14.0, 3079.9), (40, 3079.9),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_d == pytest.approx(12.4, abs=0.3)
    assert b.floor_offset_m == pytest.approx(-0.1, abs=0.05)
    assert b.toe_asbuilt_d < 18.0


def test_walk_does_not_cross_wide_berm_into_next_bench():
    design = [
        _bench(1, crest_d=0.0, crest_e=3095.0, toe_d=14.02, toe_e=3080.0),
        _bench(2, crest_d=21.8, crest_e=3080.8, toe_d=35.0, toe_e=3065.0),
    ]
    d, e = _prof([
        (-5, 3096), (0.5, 3095.5), (13.0, 3081.3), (21.8, 3080.8),
        (35.0, 3064.0), (40, 3064.0),
    ])
    out = measure_design_benches(design, d, e)
    top, low = out
    assert top.toe_asbuilt_status == STATUS_MEASURED
    assert top.toe_asbuilt_d == pytest.approx(13.0, abs=0.3)
    assert top.toe_asbuilt_d < 18.0
    assert top.floor_offset_m == pytest.approx(1.3, abs=0.15)
    assert low.berm_status == STATUS_MEASURED
    assert low.berm_asbuilt == pytest.approx(8.8, abs=0.6)


def test_crest_rejects_corner_on_horizontal_berm():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=12.0, toe_e=85.0)]
    d, e = _prof([
        (-8, 105), (-3, 99.5), (2, 99.5), (12, 85), (16, 85),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.crest_asbuilt_status == STATUS_MEASURED
    assert b.crest_asbuilt_d == pytest.approx(2.0, abs=0.3)


def test_not_excavated_reports_remaining_thickness():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([(-5, 100.2), (20, 100.2)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.bench_state == BENCH_STATE_NOT_EXCAVATED
    assert b.crest_asbuilt_d is None
    assert b.remaining_thickness_mean_m == pytest.approx(7.7, abs=0.8)
    assert b.remaining_thickness_max_m == pytest.approx(15.2, abs=0.3)


def test_section_truncated_when_bench_range_touches_profile_edge():
    design = [_bench(1, crest_d=-25.0, crest_e=3109.35, toe_d=-21.1, toe_e=3095.0)]
    d, e = _prof([(-25, 3098.6), (-10, 3081.3), (10, 3081.3)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.crest_asbuilt_status == STATUS_OUT_OF_PROFILE
    assert b.bench_state == BENCH_STATE_SECTION_TRUNCATED


def test_ambiguous_corners_yield_ambiguous_state():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([
        (-5, 100), (1, 100), (2, 90), (3.5, 100), (4.5, 90),
        (10, 85), (12, 85),
    ])
    out = measure_design_benches(design, d, e)
    assert out[0].bench_state == BENCH_STATE_AMBIGUOUS


def test_solid_toe_parity_with_detect_and_project_solid_toe():
    from core.profile_simplify import _detect_and_project_solid_toe
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=9.0, toe_e=85.0)]
    d, e = _prof([(-4, 100), (0, 100), (7, 86), (11, 84.5), (14, 84.5)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.toe_asbuilt_status == STATUS_MEASURED
    crest_i = int(np.argmin(np.abs(d - b.crest_asbuilt_d)))
    stop_i = crest_i
    while stop_i < len(d) - 1 and e[stop_i + 1] > 85.0:
        stop_i += 1
    t = (85.0 - e[stop_i]) / (e[stop_i + 1] - e[stop_i])
    d_cross = d[stop_i] + t * (d[stop_i + 1] - d[stop_i])
    pts = np.column_stack([d[crest_i:stop_i + 1], e[crest_i:stop_i + 1]])
    pts = np.vstack([pts, [d_cross, 85.0]])
    reference_toe, _, _ = _detect_and_project_solid_toe(pts, 30.0)
    assert b.toe_asbuilt_d == pytest.approx(reference_toe, abs=0.05)


# ---------------------------------------------------------------- wave 12
# Crest elevation = top of the last steep segment upstream (never the upper
# bench floor via max(profile)); floors below the design toe are rejected;
# an inclined remnant berm is reported via floor_offset/warnings/remnant.


def test_s01_b2_upper_floor_not_leaked_and_incline_remnant_reported():
    design = [
        _bench(2, crest_d=-12.563, crest_e=3095.0, toe_d=-8.535, toe_e=3080.0),
        _bench(3, crest_d=0.0, crest_e=3080.0, toe_d=4.033, toe_e=3065.0),
    ]
    d, e = _prof([
        (-25.0, 3097.1), (-19.0, 3097.1),
        (-15.7, 3095.6),
        (-10.5, 3084.4),
        (-0.9, 3080.0),
        (3.5, 3066.0), (12.0, 3066.0),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(15.6, abs=0.25)
    assert b.height_asbuilt < 16.5
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.floor_offset_status == STATUS_MEASURED
    assert b.floor_offset_m == pytest.approx(3.4, abs=0.6)
    assert "incline_berm" in b.warnings
    assert "floor_below_design" not in b.warnings
    assert b.berm_remnant_max_m == pytest.approx(3.5, abs=0.5)
    assert b.berm_remnant_area_m2 is not None
    assert b.berm_remnant_area_m2 > 10.0
    low = out[1]
    assert low.berm_remnant_max_m is None
    assert low.berm_remnant_area_m2 is None


def test_s77_b2_rejects_lower_bench_floor_uses_narrow_inclined_berm():
    design = [_bench(2, crest_d=-9.803, crest_e=3095.0, toe_d=-4.444, toe_e=3080.0)]
    d, e = _prof([
        (-25.0, 3095.8), (-16.0, 3095.8),
        (-13.5, 3094.6),
        (-7.6, 3082.3),
        (-2.9, 3080.8),
        (-1.95, 3080.65),
        (2.0, 3075.5), (10.0, 3075.5),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(14.3, abs=0.4)
    assert b.height_asbuilt < 16.0
    assert b.floor_offset_status == STATUS_MEASURED
    assert 0.3 <= b.floor_offset_m <= 1.1
    assert "floor_below_design" not in b.warnings
    assert b.berm_remnant_max_m is None


def test_rejected_lower_floor_without_berm_uses_design_toe_with_warning():
    design = [_bench(2, crest_d=-9.803, crest_e=3095.0, toe_d=-4.444, toe_e=3080.0)]
    d, e = _prof([
        (-25.0, 3095.8), (-16.0, 3095.8),
        (-13.5, 3094.6),
        (-7.6, 3082.3),
        (-1.0, 3080.2),
        (2.5, 3075.5), (10.0, 3075.5),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(15.0, abs=0.35)
    assert b.floor_offset_m is None
    assert "floor_below_design" in b.warnings
    assert b.berm_remnant_max_m is None
    assert b.berm_remnant_area_m2 is None


def test_s25_b2_step_edge_recovered_as_crest_elevation():
    design = [_bench(2, crest_d=0.0, crest_e=3080.0, toe_d=4.022, toe_e=3065.0)]
    d, e = _prof([
        (-12.0, 3082.1), (-6.2, 3082.1),
        (-2.65, 3079.9),
        (3.3, 3064.5),
        (10.0, 3064.5),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(17.1, abs=0.25)
    assert b.floor_offset_m == pytest.approx(-0.5, abs=0.1)
    assert "floor_below_design" not in b.warnings
    assert "incline_berm" not in b.warnings


def test_s23_b2_high_floor_step_crest_no_upper_edge_leak():
    design = [_bench(2, crest_d=0.0, crest_e=3080.0, toe_d=4.03, toe_e=3065.0)]
    d, e = _prof([
        (-10.0, 3081.7), (-5.9, 3081.7),
        (-4.5, 3080.74),
        (-2.9, 3080.74),
        (-1.95, 3080.0),
        (2.2, 3067.0),
        (4.0, 3065.83),
        (12.0, 3065.83),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(14.9, abs=0.2)
    assert b.height_asbuilt < 15.3
    assert b.floor_offset_m == pytest.approx(0.83, abs=0.1)
    assert "incline_berm" not in b.warnings
    assert "floor_below_design" not in b.warnings


def test_crest_elevation_ambiguous_when_no_steep_segment_identifiable():
    from core.design_guided_measurement import _crest_elevation
    d, e = _prof([(-8.0, 100.6), (-2.0, 100.2), (3.0, 99.8), (9.0, 99.4), (14.0, 99.4)])
    z, status = _crest_elevation(d, e, 0.5, 1.0, DEFAULTS)
    assert z is None
    assert status == STATUS_AMBIGUOUS


def test_s78_b2_high_landing_rejected_uses_design_toe():
    design = [_bench(2, crest_d=-8.937, crest_e=3095.0, toe_d=-3.591, toe_e=3080.0)]
    d, e = _prof([
        (-25.0, 3097.1), (-18.0, 3097.1),
        (-13.5, 3094.6),
        (-7.6, 3083.3),
        (-4.6, 3082.0),
        (-3.7, 3081.9),
        (-1.0, 3080.2),
        (2.5, 3076.2), (10.0, 3076.2),
    ])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(15.0, abs=0.35)
    assert b.floor_offset_m is None
    assert "floor_below_design" in b.warnings
    assert b.berm_remnant_max_m is None


# ---------------------------------------------------------------- wave 16
# Excavated-but-displaced benches (S-49..S-54 B2): the as-built bench sits at
# the design elevations with its crest shifted horizontally, and the floor
# walk hits the profile end just short of the toe. With the as-built
# segmentation passed in, the walk recovers the toe past the profile end
# (bounded by bench height + margin / the lower bench crest), the bench is
# classified excavated with an additive bench_offset warning, and genuine
# not_excavated benches keep their state and debt.


def _topo_bench(bench_number, crest_d, crest_e, toe_d, toe_e):
    return _bench(bench_number, crest_d, crest_e, toe_d, toe_e)


def test_displaced_excavated_bench_recovered_past_profile_end():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=4.0, toe_e=85.0)]
    d, e = _prof([(-5.0, 100.2), (1.7, 100.7), (10.0, 85.56)])
    asbuilt = [_topo_bench(1, crest_d=2.59, crest_e=100.71, toe_d=7.64, toe_e=86.75)]
    out = measure_design_benches(design, d, e, asbuilt_benches=asbuilt)
    b = out[0]
    assert b.bench_state == "excavated"
    assert b.crest_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_d is not None and b.toe_asbuilt_d > 10.0
    assert b.toe_asbuilt_d < 11.0
    assert b.toe_extrapolated is True
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(15.7, abs=0.25)
    offset = [w for w in b.warnings if w.startswith("bench_offset")]
    assert offset and "2.59" in offset[0]
    assert "toe_extrapolated" in b.warnings
    assert b.remaining_thickness_mean_m is None
    assert b.remaining_thickness_max_m is None
    assert b.floor_offset_m is None


def test_displaced_bench_with_signature_but_unreachable_toe_not_not_excavated():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=4.0, toe_e=85.0)]
    d, e = _prof([(-5.0, 101.2), (3.0, 101.4), (10.0, 100.0)])
    asbuilt = [_topo_bench(1, crest_d=3.0, crest_e=101.4, toe_d=8.0, toe_e=86.0)]
    out = measure_design_benches(design, d, e, asbuilt_benches=asbuilt)
    b = out[0]
    assert b.bench_state != BENCH_STATE_NOT_EXCAVATED
    assert b.toe_asbuilt_status != STATUS_MEASURED
    assert b.remaining_thickness_mean_m is None
    assert b.remaining_thickness_max_m is None
    assert any(w.startswith("bench_offset") for w in b.warnings)


def test_displaced_bench_toe_curve_tail_recovered():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=4.0, toe_e=85.0)]
    d, e = _prof([(-5.0, 101.2), (3.0, 101.4), (9.5, 91.0), (10.0, 90.72)])
    asbuilt = [_topo_bench(1, crest_d=3.0, crest_e=101.4, toe_d=8.0, toe_e=86.0)]
    out = measure_design_benches(design, d, e, asbuilt_benches=asbuilt)
    b = out[0]
    assert b.bench_state == "excavated"
    assert b.crest_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.toe_extrapolated is True
    assert 12.5 < b.toe_asbuilt_d < 13.6
    assert b.height_status == STATUS_MEASURED
    assert any(w.startswith("bench_offset") for w in b.warnings)


def test_displaced_bench_floor_visible_at_edge_measured_at_floor():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=4.0, toe_e=85.0)]
    d, e = _prof([(-5.0, 101.2), (3.0, 101.4), (9.0, 90.5), (10.0, 90.5)])
    asbuilt = [_topo_bench(1, crest_d=3.0, crest_e=101.4, toe_d=8.0, toe_e=86.0)]
    out = measure_design_benches(design, d, e, asbuilt_benches=asbuilt)
    b = out[0]
    assert b.bench_state == "excavated"
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.floor_offset_status == STATUS_MEASURED
    assert b.floor_offset_m == pytest.approx(5.5, abs=0.2)
    assert any(w.startswith("bench_offset") for w in b.warnings)


def test_displaced_bench_without_asbuilt_segmentation_keeps_not_excavated():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=4.0, toe_e=85.0)]
    d, e = _prof([(-5.0, 101.2), (3.0, 101.4), (9.5, 91.0), (10.0, 90.72)])
    out = measure_design_benches(design, d, e)
    b = out[0]
    assert b.bench_state == BENCH_STATE_NOT_EXCAVATED
    assert b.remaining_thickness_mean_m == pytest.approx(8.7, abs=1.0)
    assert not any(w.startswith("bench_offset") for w in b.warnings)


def test_displaced_excavated_bench_with_deep_floor_uses_design_toe():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=4.0, toe_e=85.0)]
    d, e = _prof([
        (-5.0, 100.2), (3.0, 100.2), (10.5, 83.2), (16.0, 83.2),
    ])
    asbuilt = [_topo_bench(1, crest_d=3.0, crest_e=100.2, toe_d=9.0, toe_e=84.2)]
    out = measure_design_benches(design, d, e, asbuilt_benches=asbuilt)
    b = out[0]
    assert b.bench_state == "excavated"
    assert b.crest_asbuilt_status == STATUS_MEASURED
    assert b.toe_asbuilt_status == STATUS_MEASURED
    assert b.toe_extrapolated is False
    assert "floor_below_design" in b.warnings
    assert b.floor_offset_m is None
    assert b.height_status == STATUS_MEASURED
    assert b.height_asbuilt == pytest.approx(15.2, abs=0.3)
    assert any(w.startswith("bench_offset") for w in b.warnings)


def test_genuine_not_excavated_unchanged_with_segmentation_present():
    design = [_bench(1, crest_d=0.0, crest_e=100.0, toe_d=10.0, toe_e=85.0)]
    d, e = _prof([(-5.0, 100.2), (20.0, 100.2)])
    asbuilt = [_topo_bench(1, crest_d=-20.0, crest_e=115.0, toe_d=-10.0, toe_e=100.0)]
    out = measure_design_benches(design, d, e, asbuilt_benches=asbuilt)
    b = out[0]
    assert b.bench_state == BENCH_STATE_NOT_EXCAVATED
    assert b.remaining_thickness_max_m == pytest.approx(15.2, abs=0.3)
    assert not any(w.startswith("bench_offset") for w in b.warnings)


def test_section_truncated_wins_even_with_offset_signature():
    design = [_bench(1, crest_d=-25.0, crest_e=3109.35, toe_d=-21.1, toe_e=3095.0)]
    d, e = _prof([(-25.0, 3098.6), (-10.0, 3081.3), (10.0, 3081.3)])
    asbuilt = [_topo_bench(1, crest_d=-20.0, crest_e=3109.0, toe_d=-15.0, toe_e=3096.0)]
    out = measure_design_benches(design, d, e, asbuilt_benches=asbuilt)
    b = out[0]
    assert b.bench_state == BENCH_STATE_SECTION_TRUNCATED
    assert b.toe_extrapolated is False
