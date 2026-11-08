"""Tests for the additive guided integration in profile compliance.

``compare_design_vs_asbuilt_guided`` wraps ``compare_design_vs_asbuilt`` and
only ADDS guided_* / design_bench_state / split fields: every legacy value
(status, scores, deltas) must stay byte-identical.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from core import compare_design_vs_asbuilt_guided
from core.design_guided_measurement import measure_design_benches
from core.profile_compliance import compare_design_vs_asbuilt
from core.profile_extract import BenchParams

TOLERANCES = {
    "bench_height": {"neg": 2.0, "pos": 2.0},
    "face_angle": {"neg": 5.0, "pos": 5.0},
    "berm_width": {"min": 7.0},
}

GUIDED_KEYS = {
    "guided_delta_crest", "guided_delta_crest_status",
    "guided_delta_toe", "guided_delta_toe_status",
    "guided_height", "guided_height_status",
    "guided_angle", "guided_angle_status",
    "guided_berm", "guided_berm_status",
    "guided_floor_offset_m", "guided_floor_offset_status",
    "design_bench_state",
}


def _bench(num, cd, ce, td, te, **kw):
    height = abs(ce - te)
    dx = abs(td - cd)
    import math
    angle = math.degrees(math.atan2(height, dx)) if dx > 1e-9 else 90.0
    return BenchParams(
        bench_number=num, crest_elevation=ce, crest_distance=cd,
        toe_elevation=te, toe_distance=td, bench_height=height,
        face_angle=angle, berm_width=kw.get("berm_width", 0.0),
        spill_width=kw.get("spill_width", 0.0),
        effective_berm_width=kw.get("effective_berm_width", 0.0),
    )


def _params(benches, name="S-01", sector="SEC"):
    return SimpleNamespace(section_name=name, sector=sector, benches=benches)


def _prof(pts, res=0.1):
    pts = np.asarray(pts, dtype=float)
    d_out, e_out = [], []
    for i in range(len(pts) - 1):
        d0, e0 = pts[i]
        d1, e1 = pts[i + 1]
        span = d1 - d0
        steps = max(1, int(np.ceil(abs(span) / res)))
        if i == 0:
            d_out.append(d0)
            e_out.append(e0)
        for s in range(1, steps + 1):
            f = s / steps
            d_out.append(d0 + f * span)
            e_out.append(e0 + f * (e1 - e0))
    return np.array(d_out), np.array(e_out)


def _legacy_fields(row):
    return {k: v for k, v in row.items() if not k.startswith("guided_")
            and not k.startswith("proposed_")
            and k not in ("design_bench_state", "split_bench", "split_of",
                          "floor_offset_m", "floor_status",
                          "excavation_debt_thickness_mean_m",
                          "excavation_debt_thickness_max_m",
                          "excavation_debt_area_m2",
                          "berm_remnant_max_m", "berm_remnant_area_m2")}


def test_match_rows_gain_guided_fields_legacy_untouched():
    design = [_bench(1, cd=0.0, ce=100.0, td=10.0, te=85.0, berm_width=8.0)]
    topo = [_bench(1, cd=0.5, ce=100.0, td=10.6, te=85.0, berm_width=8.4)]
    d, e = _prof([(-5, 100), (0.5, 100), (10.6, 85), (20, 85)])
    legacy = compare_design_vs_asbuilt(_params(design), _params(topo), TOLERANCES)
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params(topo), TOLERANCES, d, e,
    )
    assert len(rows) == len(legacy) == 1
    assert _legacy_fields(rows[0]) == _legacy_fields(legacy[0])
    assert GUIDED_KEYS.issubset(rows[0].keys())
    assert rows[0]["type"] == "MATCH"
    assert rows[0]["design_bench_state"] == "excavated"
    assert rows[0]["guided_delta_toe"] == pytest.approx(-0.6, abs=0.3)
    assert rows[0]["guided_delta_toe_status"] == "measured"
    assert rows[0]["split_bench"] is False


def test_missing_row_carries_design_bench_state_not_excavated():
    design = [
        _bench(1, cd=0.0, ce=100.0, td=10.0, te=85.0),
        _bench(2, cd=18.0, ce=85.0, td=28.0, te=70.0),
    ]
    topo = [_bench(1, cd=0.4, ce=100.0, td=10.4, te=85.0)]
    d, e = _prof([(-5, 100), (0.4, 100), (10.4, 85), (35, 85.0)])
    legacy = compare_design_vs_asbuilt(_params(design), _params(topo), TOLERANCES)
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params(topo), TOLERANCES, d, e,
    )
    missing = [r for r in rows if r["type"] == "MISSING"]
    assert len(missing) == 1
    lm = [r for r in legacy if r["type"] == "MISSING"][0]
    assert _legacy_fields(missing[0]) == _legacy_fields(lm)
    assert missing[0]["bench_num"] == 2
    assert missing[0]["design_bench_state"] == "not_excavated"
    assert missing[0]["guided_remaining_thickness_mean_m"] > 1.0
    assert missing[0]["height_real"] is None
    assert missing[0]["bench_score"] == 0


def test_split_bench_flag_and_extra_split_of():
    design = [_bench(1, cd=0.0, ce=115.0, td=15.0, te=100.0)]
    frag_a = _bench(1, cd=0.2, ce=115.0, td=12.6, te=103.0)
    frag_b = _bench(2, cd=12.6, ce=103.0, td=15.5, te=100.2)
    d, e = _prof([
        (-5, 115), (0.2, 115), (12.6, 103.0), (13.5, 102.2),
        (15.5, 100.2), (22, 100.2),
    ])
    legacy = compare_design_vs_asbuilt(_params(design), _params([frag_a, frag_b]), TOLERANCES)
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params([frag_a, frag_b]), TOLERANCES, d, e,
    )
    assert [r["type"] for r in legacy].count("EXTRA") == 1
    match = [r for r in rows if r["type"] == "MATCH"][0]
    extra = [r for r in rows if r["type"] == "EXTRA"][0]
    assert match["split_bench"] is True
    assert match["guided_height"] == pytest.approx(14.8, abs=1.0)
    assert extra["split_of"] == 1


def test_extra_far_from_design_benches_has_no_split_of():
    design = [_bench(1, cd=0.0, ce=100.0, td=10.0, te=85.0)]
    topo = [
        _bench(1, cd=0.3, ce=100.0, td=10.3, te=85.0),
        _bench(2, cd=40.0, ce=120.0, td=50.0, te=105.0),
    ]
    d, e = _prof([(-5, 100), (0.3, 100), (10.3, 85), (20, 85)])
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params(topo), TOLERANCES, d, e,
    )
    extra = [r for r in rows if r["type"] == "EXTRA"][0]
    assert extra["split_of"] is None


def test_unmeasurable_guided_values_are_none_never_zero():
    design = [_bench(1, cd=0.0, ce=100.0, td=10.0, te=85.0)]
    d, e = _prof([(-5, 200.0), (20, 200.0)])
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params([]), TOLERANCES, d, e,
    )
    row = [r for r in rows if r["type"] == "MISSING"][0]
    assert row["guided_delta_toe"] is None
    assert row["guided_height"] is None
    assert row["guided_berm"] is None
    assert row["design_bench_state"] in ("unmeasured", "out_of_profile",
                                         "not_excavated", "section_truncated")
    assert row["design_bench_state"] == "not_excavated"


def test_guided_values_rounded():
    design = [_bench(1, cd=0.0, ce=100.0, td=10.0, te=85.0)]
    d, e = _prof([(-5, 100), (0.5, 100), (10.55, 85), (20, 85)])
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params([]), TOLERANCES, d, e,
    )
    vals = [v for k, v in rows[0].items() if k.startswith("guided_") and isinstance(v, float)]
    assert all(v == round(v, 2) for v in vals)
