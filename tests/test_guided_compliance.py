"""Tests for the PROPOSED compliance rules (wave 9 + wave 13 user decisions).

``core.guided_compliance.apply_proposed_rules`` re-scores the rows produced by
``compare_design_vs_asbuilt_guided`` with the user-approved rules (per-magnitude
guided-when-measured with current fallback, not_excavated -> excavation debt,
truncated/unmeasured -> not evaluable) WITHOUT touching a single official
value: every legacy field of every row must stay identical.
"""

import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from core import compare_design_vs_asbuilt_guided
from core.config import TOLERANCES as CONFIG_TOLERANCES
from core.design_guided_measurement import excavation_debt_area
from core.profile_compliance import compare_design_vs_asbuilt
from core.profile_extract import BenchParams

TOLERANCES = {
    "bench_height": {"neg": 2.0, "pos": 2.0},
    "face_angle": {"neg": 5.0, "pos": 5.0},
    "berm_width": {"min": 7.0},
    "crest_toe_deviation": {"neg": 1.0, "pos": 1.0},
    "floor_vertical": {"max": 0.5},
}

PROPOSED_KEYS = {
    "proposed_source", "proposed_height", "proposed_angle",
    "proposed_delta_crest", "proposed_delta_toe", "proposed_berm",
    "proposed_height_status", "proposed_angle_status",
    "proposed_crest_status", "proposed_toe_status", "proposed_berm_status",
    "proposed_bench_score", "proposed_evaluable", "proposed_exclusion_reason",
    "proposed_height_source", "proposed_angle_source",
    "proposed_crest_source", "proposed_toe_source", "proposed_berm_source",
    "floor_offset_m", "floor_status",
    "excavation_debt_thickness_mean_m", "excavation_debt_thickness_max_m",
    "excavation_debt_area_m2",
    "berm_remnant_max_m", "berm_remnant_area_m2",
}

MAGNITUDE_FIELDS = (
    ("height", "guided_height", "guided_height_status", "height_real",
     "proposed_height", "proposed_height_source"),
    ("angle", "guided_angle", "guided_angle_status", "angle_real",
     "proposed_angle", "proposed_angle_source"),
    ("crest", "guided_delta_crest", "guided_delta_crest_status", "delta_crest",
     "proposed_delta_crest", "proposed_crest_source"),
    ("toe", "guided_delta_toe", "guided_delta_toe_status", "delta_toe",
     "proposed_delta_toe", "proposed_toe_source"),
    ("berm", "guided_berm", "guided_berm_status", "berm_real",
     "proposed_berm", "proposed_berm_source"),
)


def _row(**over):
    row = {
        "section": "S-01", "sector": "SEC", "bench_num": 1, "bench_num_topo": 1,
        "type": "MATCH", "level": "85",
        "height_design": 15.0, "height_real": 14.8, "height_dev": -0.2,
        "height_status": "CUMPLE",
        "angle_design": 56.3, "angle_real": 54.0, "angle_dev": -2.3,
        "angle_status": "CUMPLE",
        "berm_design": 8.0, "berm_real": 8.2, "berm_dev": 0.2, "berm_min": 7.0,
        "berm_status": "CUMPLE",
        "delta_crest": 0.5, "delta_toe": 0.6,
        "bench_score": 100, "section_score": 100.0, "section_status": "CUMPLE",
        "guided_delta_crest": 0.4, "guided_delta_crest_status": "measured",
        "guided_delta_toe": 0.5, "guided_delta_toe_status": "measured",
        "guided_height": 14.9, "guided_height_status": "measured",
        "guided_angle": 55.0, "guided_angle_status": "measured",
        "guided_berm": 8.4, "guided_berm_status": "measured",
        "guided_floor_offset_m": 0.0, "guided_floor_offset_status": "measured",
        "design_bench_state": "excavated",
        "split_bench": False,
        "split_of": None,
        "guided_remaining_thickness_mean_m": None,
        "guided_remaining_thickness_max_m": None,
        "guided_excavation_debt_area_m2": None,
    }
    row.update(over)
    return row


def _extra_row(**over):
    row = _row(
        type="EXTRA", bench_num=999, bench_num_topo=3, level="103",
        height_design=None, height_real=4.0, height_dev=None,
        height_status="EXTRA", angle_design=None, angle_real=48.0,
        angle_dev=None, angle_status="-", berm_design=None, berm_real=None,
        berm_dev=None, berm_min=None, berm_status="BANCO ADICIONAL",
        delta_crest=None, delta_toe=None, bench_score=0,
        split_bench=None,
    )
    row.pop("guided_delta_crest", None)
    row.pop("guided_delta_toe", None)
    row.pop("guided_height", None)
    row.pop("guided_angle", None)
    row.pop("guided_berm", None)
    row.pop("guided_floor_offset_m", None)
    row.pop("design_bench_state", None)
    row.update(over)
    return row


# ---------------------------------------------------------------- rule: per-magnitude source (wave 13)


def test_match_all_measured_proposes_guided_values_with_guided_sources():
    from core.guided_compliance import apply_proposed_rules

    row = _row()
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert PROPOSED_KEYS.issubset(out.keys())
    assert out["proposed_source"] == "guided"
    assert out["proposed_height"] == row["guided_height"]
    assert out["proposed_angle"] == row["guided_angle"]
    assert out["proposed_delta_crest"] == row["guided_delta_crest"]
    assert out["proposed_delta_toe"] == row["guided_delta_toe"]
    assert out["proposed_berm"] == row["guided_berm"]
    for _, _, _, _, _, source_key in MAGNITUDE_FIELDS:
        assert out[source_key] == "guided"
    assert out["proposed_evaluable"] is True
    assert out["proposed_exclusion_reason"] is None


def test_match_guided_not_measured_falls_back_to_current_values():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        guided_height=None, guided_height_status="ambiguous",
        guided_angle=None, guided_angle_status="insufficient_points",
        guided_delta_crest=None, guided_delta_crest_status="no_crossing",
        guided_delta_toe=None, guided_delta_toe_status="no_crossing",
        guided_berm=None, guided_berm_status="no_crossing",
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "current"
    assert out["proposed_height"] == row["height_real"]
    assert out["proposed_angle"] == row["angle_real"]
    assert out["proposed_delta_crest"] == row["delta_crest"]
    assert out["proposed_delta_toe"] == row["delta_toe"]
    assert out["proposed_berm"] == row["berm_real"]
    for _, _, _, _, _, source_key in MAGNITUDE_FIELDS:
        assert out[source_key] == "current"
    assert out["proposed_height_status"] == row["height_status"]
    assert out["proposed_angle_status"] == row["angle_status"]
    assert out["proposed_berm_status"] == row["berm_status"]
    assert out["proposed_bench_score"] == row["bench_score"]


@pytest.mark.parametrize(
    "name,guided_key,status_key,official_key,proposed_key,source_key",
    MAGNITUDE_FIELDS)
def test_each_magnitude_switches_source_independently(
        name, guided_key, status_key, official_key, proposed_key, source_key):
    from core.guided_compliance import apply_proposed_rules

    row = _row()
    for guided_field in ("guided_height", "guided_angle", "guided_delta_crest",
                         "guided_delta_toe", "guided_berm"):
        row[guided_field] = None
        row[guided_field + "_status"] = "no_crossing"
    row[guided_key] = 21.5
    row[status_key] = "measured"
    row[official_key] = 9.9
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out[proposed_key] == 21.5
    assert out[source_key] == "guided"
    for _, other_guided, _, _, other_proposed, other_source in MAGNITUDE_FIELDS:
        if other_proposed == proposed_key:
            continue
        assert out[other_proposed] is not None
        assert out[other_source] == "current"

    row[guided_key] = None
    row[status_key] = "no_crossing"
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out[proposed_key] == 9.9
    assert out[source_key] == "current"
    assert out["proposed_source"] == "current"

    row[official_key] = None
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out[proposed_key] is None
    assert out[source_key] is None


def test_proposed_source_none_when_no_magnitude_has_any_value():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        height_real=None, angle_real=None, delta_crest=None,
        delta_toe=None, berm_real=None,
        guided_height=None, guided_height_status="no_crossing",
        guided_angle=None, guided_angle_status="no_crossing",
        guided_delta_crest=None, guided_delta_crest_status="no_crossing",
        guided_delta_toe=None, guided_delta_toe_status="no_crossing",
        guided_berm=None, guided_berm_status="no_crossing",
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] is None
    for _, _, _, _, _, source_key in MAGNITUDE_FIELDS:
        assert out[source_key] is None
    assert out["proposed_bench_score"] is None
    assert out["proposed_evaluable"] is True


def test_mixed_row_combines_guided_and_current_sources():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        guided_angle=None, guided_angle_status="insufficient_points",
        guided_delta_toe=None, guided_delta_toe_status="no_crossing",
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "mixed"
    assert out["proposed_height_source"] == "guided"
    assert out["proposed_angle_source"] == "current"
    assert out["proposed_angle"] == row["angle_real"]
    assert out["proposed_crest_source"] == "guided"
    assert out["proposed_toe_source"] == "current"
    assert out["proposed_toe_status"] == "CUMPLE"
    assert out["proposed_berm_source"] == "guided"


def test_guided_value_with_non_measured_status_is_ignored():
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_height=17.5, guided_height_status="ambiguous")
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_height"] == row["height_real"]
    assert out["proposed_height_source"] == "current"


def test_match_recomputes_fuera_status_with_official_formula():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        height_real=11.0, height_status="NO CUMPLE",
        angle_real=49.0, angle_status="FUERA DE TOLERANCIA",
        bench_score=0, berm_real=5.0, berm_status="NO CUMPLE",
        guided_height=None, guided_height_status="ambiguous",
        guided_angle=None, guided_angle_status="insufficient_points",
        guided_berm=None, guided_berm_status="no_crossing",
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_height_status"] == "NO CUMPLE"
    assert out["proposed_angle_status"] == "FUERA DE TOLERANCIA"
    assert out["proposed_berm_status"] == "NO CUMPLE"
    assert out["proposed_bench_score"] == 0


def test_floor_status_is_evaluated_apart_from_guided_height():
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_floor_offset_m=1.9)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["floor_status"] == "NO CUMPLE"
    assert out["proposed_height_source"] == "guided"
    assert out["proposed_height"] == row["guided_height"]
    assert out["proposed_bench_score"] is not None
    assert out["proposed_bench_score"] != 0


# ---------------------------------------------------------------- high floor (wave 13)


def test_match_high_floor_uses_guided_toe_and_berm():
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_floor_offset_m=1.2, guided_delta_toe=-1.9,
               guided_berm=9.4, delta_toe=3.3, berm_real=6.1)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "guided"
    assert out["proposed_delta_toe"] == -1.9
    assert out["proposed_berm"] == 9.4
    assert out["proposed_height"] == row["guided_height"]
    assert out["proposed_angle"] == row["guided_angle"]
    assert out["proposed_crest_status"] == "CUMPLE"
    assert out["proposed_toe_status"] == "NO CUMPLE"


def test_match_high_floor_keeps_current_toe_when_guided_toe_missing():
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_floor_offset_m=1.2, guided_delta_toe=None,
               guided_delta_toe_status="no_crossing", delta_toe=0.6,
               guided_berm=None, guided_berm_status="no_crossing",
               berm_real=8.2)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_delta_toe"] == 0.6
    assert out["proposed_berm"] == 8.2
    assert out["proposed_toe_status"] == "CUMPLE"
    assert out["proposed_toe_source"] == "current"
    assert out["proposed_berm_source"] == "current"
    assert out["proposed_source"] == "mixed"


def test_match_zero_floor_offset_still_uses_measured_guided_toe_and_berm():
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_floor_offset_m=0.0, guided_delta_toe=-1.9,
               guided_berm=9.4)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_delta_toe"] == -1.9
    assert out["proposed_berm"] == 9.4
    assert out["proposed_toe_source"] == "guided"
    assert out["proposed_berm_source"] == "guided"


# ---------------------------------------------------------------- rule 1: split bench -> guided


def test_match_split_bench_uses_guided_with_current_fallback():
    from core.guided_compliance import apply_proposed_rules

    row = _row(split_bench=True, height_real=3.44, guided_height=15.71,
               angle_real=44.0, guided_angle=57.1, delta_toe=3.23,
               guided_delta_toe=3.49, berm_real=0.26, guided_berm=None,
               guided_berm_status="no_crossing")
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "mixed"
    assert out["proposed_height"] == 15.71
    assert out["proposed_height_source"] == "guided"
    assert out["proposed_angle"] == 57.1
    assert out["proposed_delta_toe"] == 3.49
    assert out["proposed_berm"] == 0.26
    assert out["proposed_berm_source"] == "current"
    assert out["proposed_berm_status"] == "NO CUMPLE"
    assert out["proposed_evaluable"] is True
    assert out["proposed_bench_score"] == 40
    height_dev = 15.71 - 15.0
    expected = "CUMPLE" if abs(height_dev) <= 2.0 else "NO CUMPLE"
    assert out["proposed_height_status"] == expected


def test_match_split_bench_all_measured_is_pure_guided():
    from core.guided_compliance import apply_proposed_rules

    row = _row(split_bench=True, height_real=3.44, guided_height=15.71,
               angle_real=44.0, guided_angle=57.1, delta_toe=3.23,
               guided_delta_toe=3.49, berm_real=0.26, guided_berm=9.02)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "guided"
    for _, _, _, _, _, source_key in MAGNITUDE_FIELDS:
        assert out[source_key] == "guided"
    assert out["proposed_berm"] == 9.02


def test_extra_split_fragment_is_not_evaluable_and_never_zero():
    from core.guided_compliance import apply_proposed_rules

    extra = _extra_row(split_of=1)
    out = apply_proposed_rules([extra], TOLERANCES)[0]
    assert out["proposed_evaluable"] is False
    assert out["proposed_exclusion_reason"] == "split_fragment"
    assert out["proposed_bench_score"] is None
    assert out["proposed_source"] is None
    assert out["proposed_height"] is None
    assert out["proposed_height_status"] == "-"


# ---------------------------------------------------------------- MISSING


def test_missing_excavated_with_guided_measurement_becomes_evaluable():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        type="MISSING", bench_num_topo=None, height_real=None,
        height_dev=None, height_status="NO CONSTRUIDO", angle_real=None,
        angle_dev=None, berm_real=None, berm_dev=None, berm_status="FALTA BANCO",
        delta_crest=None, delta_toe=None, bench_score=0, guided_height=6.83,
        guided_angle=55.0, guided_delta_toe=0.4, guided_berm=8.0,
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "guided"
    assert out["proposed_evaluable"] is True
    assert out["proposed_height"] == 6.83
    height_dev = 6.83 - 15.0
    assert out["proposed_height_status"] == "NO CUMPLE"
    assert out["proposed_bench_score"] is not None
    assert out["proposed_bench_score"] != 0
    assert height_dev < -2.0 * 1.5


def test_missing_without_complete_guided_stays_not_evaluable():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        type="MISSING", bench_num_topo=None, height_real=None,
        height_status="NO CONSTRUIDO", angle_real=None, berm_real=None,
        berm_status="FALTA BANCO", delta_crest=None, delta_toe=None,
        bench_score=0, design_bench_state="unmeasured",
        guided_delta_crest=None, guided_delta_toe=None, guided_height=None,
        guided_angle=None, guided_berm=None,
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_evaluable"] is False
    assert out["proposed_exclusion_reason"] == "unmeasured"
    assert out["proposed_bench_score"] is None
    assert out["proposed_height_status"] == "-"


# ---------------------------------------------------------------- rule 2: not_excavated


def test_not_excavated_excluded_and_reported_as_excavation_debt():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        type="MISSING", bench_num_topo=None, height_real=None,
        height_status="NO CONSTRUIDO", angle_real=None, berm_real=None,
        berm_status="FALTA BANCO", delta_crest=None, delta_toe=None,
        bench_score=0, design_bench_state="not_excavated",
        guided_remaining_thickness_mean_m=8.62,
        guided_remaining_thickness_max_m=16.98,
        guided_excavation_debt_area_m2=141.3,
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_evaluable"] is False
    assert out["proposed_exclusion_reason"] == "not_excavated"
    assert out["proposed_bench_score"] is None
    assert out["excavation_debt_thickness_mean_m"] == 8.62
    assert out["excavation_debt_thickness_max_m"] == 16.98
    assert out["excavation_debt_area_m2"] == 141.3


# ---------------------------------------------------------------- rule 4: truncated / unmeasured


@pytest.mark.parametrize("state,reason,row_type", [
    ("section_truncated", "section_truncated", "MATCH"),
    ("section_truncated", "section_truncated", "MISSING"),
    ("unmeasured", "unmeasured", "MISSING"),
])
def test_truncated_and_unmeasured_are_not_evaluable(state, reason, row_type):
    from core.guided_compliance import apply_proposed_rules

    row = _row(design_bench_state=state, type=row_type)
    if row_type == "MISSING":
        row.update(height_real=None, height_status="NO CONSTRUIDO",
                   angle_real=None, angle_status="-", berm_real=None,
                   berm_status="FALTA BANCO", bench_score=0, delta_crest=None,
                   delta_toe=None, bench_num_topo=None)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_evaluable"] is False
    assert out["proposed_exclusion_reason"] == reason
    assert out["proposed_bench_score"] is None
    assert out["proposed_height"] is None
    assert out["proposed_height_status"] == "-"
    for _, _, _, _, _, source_key in MAGNITUDE_FIELDS:
        assert out[source_key] is None


# ---------------------------------------------------------------- EXTRA without split


def test_extra_without_split_keeps_current_treatment():
    from core.guided_compliance import apply_proposed_rules

    extra = _extra_row(split_of=None)
    out = apply_proposed_rules([extra], TOLERANCES)[0]
    assert out["proposed_evaluable"] is False
    assert out["proposed_exclusion_reason"] is None
    assert out["proposed_source"] is None
    assert out["proposed_bench_score"] == 0
    assert out["proposed_height"] is None
    assert out["proposed_height_status"] == "-"
    assert out["floor_offset_m"] is None
    assert out["floor_status"] == "-"


# ---------------------------------------------------------------- floor status levels


@pytest.mark.parametrize("offset,expected", [
    (0.0, "CUMPLE"), (0.4, "CUMPLE"), (0.5, "CUMPLE"),
    (0.51, "FUERA DE TOLERANCIA"), (0.75, "FUERA DE TOLERANCIA"),
    (0.76, "NO CUMPLE"), (1.9, "NO CUMPLE"),
    (-0.9, "NO CUMPLE"), (-0.3, "CUMPLE"),
])
def test_floor_status_three_levels(offset, expected):
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_floor_offset_m=offset)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["floor_offset_m"] == offset
    assert out["floor_status"] == expected


def test_floor_status_dash_when_not_measured():
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_floor_offset_m=None,
               guided_floor_offset_status="no_crossing")
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["floor_offset_m"] is None
    assert out["floor_status"] == "-"


def test_floor_status_uses_configured_tolerance():
    from core.guided_compliance import apply_proposed_rules

    tols = dict(TOLERANCES, floor_vertical={"max": 1.0})
    row = _row(guided_floor_offset_m=1.2)
    out = apply_proposed_rules([row], tols)[0]
    assert out["floor_status"] == "FUERA DE TOLERANCIA"


# ---------------------------------------------------------------- no missing -> 0


def test_no_missing_value_is_ever_converted_to_zero():
    from core.guided_compliance import apply_proposed_rules

    row = _row(type="MISSING", design_bench_state="excavated",
               bench_num_topo=None, height_real=None, angle_real=None,
               berm_real=None, height_status="NO CONSTRUIDO",
               angle_status="-", berm_status="FALTA BANCO", bench_score=0,
               delta_crest=None, delta_toe=None,
               guided_berm=None, guided_berm_status="no_crossing",
               guided_height=None, guided_height_status="ambiguous",
               guided_angle=None, guided_angle_status="insufficient_points")
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "guided"
    assert out["proposed_height"] is None
    assert out["proposed_height_status"] == "-"
    assert out["proposed_berm"] is None
    assert out["proposed_berm_status"] == "-"
    assert out["proposed_bench_score"] is None


# ---------------------------------------------------------------- official values untouched


def test_apply_proposed_rules_returns_copies_and_never_mutates_input():
    from core.guided_compliance import apply_proposed_rules

    rows = [_row(split_bench=True), _extra_row(split_of=1),
            _row(type="MISSING", bench_num_topo=None, height_real=None,
                 angle_real=None, berm_real=None, height_status="NO CONSTRUIDO",
                 angle_status="-", berm_status="FALTA BANCO", bench_score=0,
                 delta_crest=None, delta_toe=None,
                 design_bench_state="not_excavated",
                 guided_delta_crest=None, guided_delta_toe=None,
                 guided_height=None, guided_angle=None, guided_berm=None,
                 guided_floor_offset_m=None)]
    snapshot = copy.deepcopy(rows)
    out = apply_proposed_rules(rows, TOLERANCES)
    assert rows == snapshot
    for original, proposed in zip(rows, out):
        for key, value in original.items():
            assert proposed[key] == value
        assert proposed is not original


# ---------------------------------------------------------------- summaries


def _summary_rows():
    return [
        _row(section="S-01"),
        _row(section="S-01", height_real=11.0, bench_score=40,
             height_status="NO CUMPLE", angle_real=49.0,
             angle_status="FUERA DE TOLERANCIA", berm_real=5.0,
             berm_status="NO CUMPLE", bench_num=2, bench_num_topo=2,
             guided_floor_offset_m=0.9),
        _row(section="S-01", type="MISSING", bench_num=3, bench_num_topo=None,
             height_real=None, height_status="NO CONSTRUIDO", angle_real=None,
             angle_status="-", berm_real=None, berm_status="FALTA BANCO",
             delta_crest=None, delta_toe=None, bench_score=0,
             design_bench_state="not_excavated",
             guided_delta_crest=None, guided_delta_toe=None,
             guided_height=None, guided_angle=None, guided_berm=None,
             guided_floor_offset_m=None,
             guided_excavation_debt_area_m2=100.0,
             guided_remaining_thickness_mean_m=8.0,
             guided_remaining_thickness_max_m=16.0),
        _extra_row(section="S-01", split_of=2),
        _row(section="S-01", type="MISSING", bench_num=4, bench_num_topo=None,
             height_real=None, height_status="NO CONSTRUIDO", angle_real=None,
             angle_status="-", berm_real=None, berm_status="FALTA BANCO",
             delta_crest=None, delta_toe=None, bench_score=0,
             design_bench_state="section_truncated",
             guided_delta_crest=None, guided_delta_toe=None,
             guided_height=None, guided_angle=None, guided_berm=None,
             guided_floor_offset_m=None),
        _row(section="S-01", type="MISSING", bench_num=5, bench_num_topo=None,
             height_real=None, height_status="NO CONSTRUIDO", angle_real=None,
             angle_status="-", berm_real=None, berm_status="FALTA BANCO",
             delta_crest=None, delta_toe=None, bench_score=0,
             design_bench_state="unmeasured",
             guided_delta_crest=None, guided_delta_toe=None,
             guided_height=None, guided_angle=None, guided_berm=None,
             guided_floor_offset_m=None),
        _row(section="S-01", bench_num=6, bench_num_topo=6, split_bench=True,
             height_real=3.44, guided_height=15.71, guided_berm=None,
             berm_real=0.26, guided_angle=56.0, guided_delta_toe=0.3),
    ]


def test_summarize_proposed_section_counts_and_score():
    from core.guided_compliance import apply_proposed_rules, summarize_proposed_section

    rows = apply_proposed_rules(_summary_rows(), TOLERANCES)
    s = summarize_proposed_section(rows)
    assert s["section"] == "S-01"
    assert s["n_rows"] == 7
    assert s["n_evaluable"] == 3
    assert s["n_not_excavated"] == 1
    assert s["n_section_truncated"] == 1
    assert s["n_unmeasured"] == 1
    assert s["n_split_fragments"] == 1
    assert s["n_split_benches"] == 1
    assert s["excavation_debt_area_m2"] == pytest.approx(100.0)
    scores = [100.0, 100.0, 40.0]
    assert s["proposed_section_score"] == pytest.approx(sum(scores) / len(scores))
    assert s["proposed_section_status"] == "CUMPLE"
    assert s["floor_status_counts"]["CUMPLE"] >= 1
    assert s["floor_status_counts"]["NO CUMPLE"] >= 1
    assert s["floor_status_counts"]["-"] >= 1


def test_summarize_proposed_section_none_when_zero_evaluable():
    from core.guided_compliance import apply_proposed_rules, summarize_proposed_section

    rows = apply_proposed_rules(
        [_row(type="MISSING", bench_num_topo=None, height_real=None,
              angle_real=None, berm_real=None, height_status="NO CONSTRUIDO",
              angle_status="-", berm_status="FALTA BANCO", bench_score=0,
              delta_crest=None, delta_toe=None,
              design_bench_state="not_excavated",
              guided_delta_crest=None, guided_delta_toe=None,
              guided_height=None, guided_angle=None, guided_berm=None,
              guided_floor_offset_m=None)],
        TOLERANCES,
    )
    s = summarize_proposed_section(rows)
    assert s["proposed_section_score"] is None
    assert s["proposed_section_status"] is None
    assert s["n_evaluable"] == 0


def test_summarize_proposed_global_counts_score_and_coverage():
    from core.guided_compliance import apply_proposed_rules, summarize_proposed

    rows = apply_proposed_rules(
        _summary_rows() + _summary_rows(), TOLERANCES,
    )
    for i, r in enumerate(rows):
        if r["section"] == "S-01" and i >= 7:
            r["section"] = "S-02"
    g = summarize_proposed(rows)
    assert g["n_rows"] == 14
    assert g["n_evaluable"] == 6
    assert g["n_not_excavated"] == 2
    assert g["n_split_fragments"] == 2
    assert g["n_split_benches"] == 2
    assert g["excavation_debt_area_m2"] == pytest.approx(200.0)
    assert g["proposed_global_score"] == pytest.approx(80.0)
    cov = g["coverage"]
    assert cov["n_evaluable"] == 6
    assert cov["n_design_benches"] == 12
    assert cov["ratio"] == pytest.approx(0.5)
    assert set(g["by_section"].keys()) == {"S-01", "S-02"}


# ---------------------------------------------------------------- excavation debt area


def test_excavation_debt_area_triangle_and_rectangle():
    d = np.linspace(-5.0, 15.0, 401)
    crest, toe = (0.0, 100.0), (10.0, 85.0)
    design_e = 100.0 - 1.5 * np.clip(d, 0.0, 10.0)
    e = np.where((d >= 0) & (d <= 10), 100.0, design_e)
    area = excavation_debt_area(crest, toe, d, e)
    assert area == pytest.approx(0.5 * 10.0 * 15.0, rel=0.02)

    d2 = np.linspace(-5.0, 15.0, 401)
    e2 = np.full_like(d2, 102.0)
    area2 = excavation_debt_area((0.0, 100.0), (10.0, 100.0), d2, e2)
    assert area2 == pytest.approx(20.0, rel=0.01)


def test_excavation_debt_area_none_outside_profile_and_clamps_negative():
    d = np.linspace(50.0, 60.0, 11)
    e = np.full_like(d, 90.0)
    assert excavation_debt_area((0.0, 100.0), (10.0, 85.0), d, e) is None

    d2 = np.linspace(-5.0, 15.0, 201)
    e2 = np.full_like(d2, 80.0)
    assert excavation_debt_area((0.0, 100.0), (10.0, 100.0), d2, e2) == pytest.approx(0.0)


# ---------------------------------------------------------------- config + wrapper integration


def test_config_tolerances_gain_floor_vertical_additively():
    assert CONFIG_TOLERANCES.floor_vertical == {"max": 0.5}
    data = {f.name: getattr(CONFIG_TOLERANCES, f.name)
            for f in CONFIG_TOLERANCES.__dataclass_fields__.values()
            if f.name != "floor_vertical"}
    legacy = type(CONFIG_TOLERANCES)(**data)
    assert legacy.bench_height == CONFIG_TOLERANCES.bench_height


def _bench(num, cd, ce, td, te, **kw):
    height = abs(ce - te)
    dx = abs(td - cd)
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


def _split_fixture():
    design = [_bench(1, cd=0.0, ce=115.0, td=15.0, te=100.0)]
    frag_a = _bench(1, cd=0.2, ce=115.0, td=12.6, te=103.0)
    frag_b = _bench(2, cd=12.6, ce=103.0, td=15.5, te=100.2)
    d, e = _prof([
        (-5, 115), (0.2, 115), (12.6, 103.0), (13.5, 102.2),
        (15.5, 100.2), (22, 100.2),
    ])
    return _params(design), _params([frag_a, frag_b]), d, e


def test_guided_wrapper_returns_rows_with_proposal_by_default():
    p_d, p_t, d, e = _split_fixture()
    rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
    assert rows
    assert all(PROPOSED_KEYS.issubset(r.keys()) for r in rows)
    match = [r for r in rows if r["type"] == "MATCH"][0]
    extra = [r for r in rows if r["type"] == "EXTRA"][0]
    assert match["proposed_source"] == "mixed"
    assert match["proposed_height"] == match["guided_height"]
    assert match["proposed_height_source"] == "guided"
    assert match["proposed_berm_source"] == "current"
    assert extra["proposed_exclusion_reason"] == "split_fragment"


def test_guided_wrapper_official_fields_identical_with_and_without_proposal():
    p_d, p_t, d, e = _split_fixture()
    legacy = compare_design_vs_asbuilt(p_d, p_t, TOLERANCES)
    without = compare_design_vs_asbuilt_guided(
        p_d, p_t, TOLERANCES, d, e, apply_proposal=False,
    )
    with_proposal = compare_design_vs_asbuilt_guided(
        p_d, p_t, TOLERANCES, d, e, apply_proposal=True,
    )
    assert len(without) == len(with_proposal) == len(legacy)
    for lw, lp in zip(legacy, with_proposal):
        for key, value in lw.items():
            assert lp[key] == value
    for rw, rp in zip(without, with_proposal):
        for key, value in rw.items():
            assert rp[key] == value
        assert not any(k.startswith("proposed_") for k in rw)


def test_guided_wrapper_not_excavated_row_carries_debt_area():
    design = [
        _bench(1, cd=0.0, ce=100.0, td=10.0, te=85.0),
        _bench(2, cd=18.0, ce=85.0, td=28.0, te=70.0),
    ]
    topo = [_bench(1, cd=0.4, ce=100.0, td=10.4, te=85.0)]
    d, e = _prof([(-5, 100), (0.4, 100), (10.4, 85), (35, 85.0)])
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params(topo), TOLERANCES, d, e,
    )
    missing = [r for r in rows if r["type"] == "MISSING"][0]
    assert missing["design_bench_state"] == "not_excavated"
    assert missing["guided_excavation_debt_area_m2"] is not None
    assert missing["guided_excavation_debt_area_m2"] > 0.0
    assert missing["proposed_exclusion_reason"] == "not_excavated"
    assert missing["excavation_debt_area_m2"] == pytest.approx(
        missing["guided_excavation_debt_area_m2"])
    assert missing["proposed_bench_score"] is None


# ---------------------------------------------------------------- wave 12
# Berm remnant fields propagate additively to the proposal rows.


def test_berm_remnant_fields_propagate_to_proposal_row():
    from core.guided_compliance import apply_proposed_rules

    row = _row(guided_berm_remnant_max_m=3.5, guided_berm_remnant_area_m2=13.2)
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["berm_remnant_max_m"] == 3.5
    assert out["berm_remnant_area_m2"] == 13.2
    assert out["proposed_bench_score"] == row["bench_score"]


def test_berm_remnant_fields_default_none_when_absent():
    from core.guided_compliance import apply_proposed_rules

    out = apply_proposed_rules([_row()], TOLERANCES)[0]
    assert out["berm_remnant_max_m"] is None
    assert out["berm_remnant_area_m2"] is None


def test_guided_wrapper_rows_carry_berm_remnant_fields():
    design = [
        _bench(2, cd=-12.563, ce=3095.0, td=-8.535, te=3080.0),
        _bench(3, cd=0.0, ce=3080.0, td=4.033, te=3065.0),
    ]
    d, e = _prof([
        (-25.0, 3097.1), (-19.0, 3097.1),
        (-15.7, 3095.6),
        (-10.5, 3084.4),
        (-0.9, 3080.0),
        (3.5, 3066.0), (12.0, 3066.0),
    ])
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params([]), TOLERANCES, d, e,
    )
    row = [r for r in rows if r["bench_num"] == 2][0]
    assert row["guided_berm_remnant_max_m"] == pytest.approx(3.5, abs=0.6)
    assert row["guided_berm_remnant_area_m2"] > 10.0
    assert row["berm_remnant_max_m"] == row["guided_berm_remnant_max_m"]
    assert row["berm_remnant_area_m2"] == row["guided_berm_remnant_area_m2"]


def test_match_with_flagged_base_proposes_guided_after_user_decision():
    from core.guided_compliance import apply_proposed_rules

    row = _row(
        guided_warnings=["incline_berm"], guided_height=15.47,
        height_real=13.29, guided_delta_toe=-0.97, guided_berm=8.02,
        guided_floor_offset_m=3.68,
    )
    out = apply_proposed_rules([row], TOLERANCES)[0]
    assert out["proposed_source"] == "guided"
    assert out["proposed_height"] == 15.47
    assert out["proposed_height_source"] == "guided"
    assert out["floor_status"] == "NO CUMPLE"
    assert out["floor_offset_m"] == 3.68
    assert out["proposed_height_status"] == "CUMPLE"


def test_guided_wrapper_rows_carry_guided_warnings():
    design = [
        _bench(2, cd=-12.563, ce=3095.0, td=-8.535, te=3080.0),
        _bench(3, cd=0.0, ce=3080.0, td=4.033, te=3065.0),
    ]
    d, e = _prof([
        (-25.0, 3097.1), (-19.0, 3097.1),
        (-15.7, 3095.6),
        (-10.5, 3084.4),
        (-0.9, 3080.0),
        (3.5, 3066.0), (12.0, 3066.0),
    ])
    rows = compare_design_vs_asbuilt_guided(
        _params(design), _params([]), TOLERANCES, d, e,
    )
    row = [r for r in rows if r["bench_num"] == 2][0]
    assert "incline_berm" in row["guided_warnings"]
