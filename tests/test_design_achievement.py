"""Unit tests for core.design_achievement — reusable Logro Diseño summary.

Covers the nullable/may-be-null semantics required by both the API layer and
future frontends:
- per-row evaluability (finite signed deltas or a recognized three-tier
  ``berm_status``; bools / NaN / Inf / non-numeric deltas are never credit),
- strict crest/toe/berma denominators with nullable percentages,
- signed means, and the per-sector breakdown that preserves ``''`` identity.
"""
from __future__ import annotations

import math
from typing import Dict, List

import pytest

from core.design_achievement import (
    build_design_achievement_summary,
    build_sector_achievement_summary,
)


ZERO_ROWS_EXPECTED: Dict[str, object] = {
    "global_score": None,
    "n_total": 0,
    "n_evaluable": 0,
    "crest_cumple": 0,
    "crest_denom": 0,
    "crest_pct": None,
    "toe_cumple": 0,
    "toe_denom": 0,
    "toe_pct": None,
    "berm_cumple": 0,
    "berm_denom": 0,
    "berm_pct": None,
    "delta_crest_mean": None,
    "delta_toe_mean": None,
}


def _r1() -> dict:
    return {
        "section": "S1",
        "level": "100",
        "bench_num": 1,
        "sector": "A",
        "delta_crest": 0.5,
        "delta_toe": -0.8,
        "berm_status": "CUMPLE",
    }


def _r2() -> dict:
    return {
        "section": "S2",
        "level": "200",
        "bench_num": 2,
        "sector": "A",
        "delta_crest": 2.0,
        "delta_toe": 0.0,
        "berm_status": "NO CUMPLE",
    }


@pytest.fixture()
def rows_mixed() -> List[dict]:
    """r1 (all Cumple) + r2 (crest fuera/no) + r3 (berma-only evaluable)."""
    r3 = {
        "section": "S3",
        "level": "300",
        "bench_num": 3,
        "sector": "B",
        "delta_crest": None,
        "delta_toe": None,
        "berm_status": "CUMPLE",
    }
    return [_r1(), _r2(), r3]


class TestSummaryEmptyShapes:
    def test_none_rows_returns_all_null_summary(self):
        summary = build_design_achievement_summary(None, None)
        assert summary == ZERO_ROWS_EXPECTED

    def test_empty_list_returns_all_null_summary(self):
        summary = build_design_achievement_summary([], None)
        assert summary == ZERO_ROWS_EXPECTED


class TestEvaluability:
    def test_bool_nan_inf_and_non_numeric_deltas_are_never_evaluable(self):
        rows = [
            {"delta_crest": True},
            {"delta_crest": float("nan")},
            {"delta_toe": float("inf")},
            {"delta_toe": "not-a-number"},
            {"berm_status": ""},           # empty string -> no status
            {"berm_status": "-"},
            {"berm_status": "MISSING"},    # outside the three-tier model
            {"berm_status": None},
        ]
        summary = build_design_achievement_summary(rows, None)
        assert summary["n_evaluable"] == 0
        assert summary["global_score"] is None
        assert summary["crest_denom"] == 0
        assert summary["crest_pct"] is None

    def test_recognized_three_tier_berm_status_makes_row_evaluable(self):
        rows = [{"berm_status": "FUERA DE TOLERANCIA"}]
        summary = build_design_achievement_summary(rows, None)
        assert summary["n_evaluable"] == 1
        assert summary["berm_denom"] == 1
        assert summary["berm_cumple"] == 0
        assert summary["berm_pct"] == 0
        assert summary["delta_crest_mean"] is None
        assert summary["delta_toe_mean"] is None


class TestSummaryMetrics:
    def test_score_strict_counts_pct_and_signed_means(self, rows_mixed):
        summary = build_design_achievement_summary(rows_mixed, {"neg": 1.0, "pos": 1.0})

        assert summary["n_total"] == 3
        assert summary["n_evaluable"] == 3
        assert summary["global_score"] == 53
        assert summary["crest_cumple"] == 1
        assert summary["crest_denom"] == 2
        assert summary["crest_pct"] == 50
        assert summary["toe_cumple"] == 2
        assert summary["toe_denom"] == 2
        assert summary["toe_pct"] == 100
        assert summary["berm_cumple"] == 2
        assert summary["berm_denom"] == 3
        assert summary["berm_pct"] == 67

        assert summary["delta_crest_mean"] == pytest.approx(1.25)
        assert summary["delta_toe_mean"] == pytest.approx(-0.4)

    def test_respects_core_defaults_without_tol_dict(self):
        summary = build_design_achievement_summary([_r1(), _r2()], None)
        assert summary["crest_cumple"] == 1
        assert summary["crest_denom"] == 2
        assert summary["crest_pct"] == 50

    def test_signed_side_tolerances_neg_overrides(self, rows_mixed):
        row = {
            "sector": "A",
            "delta_crest": -1.5,
            "delta_toe": None,
            "berm_status": "CUMPLE",
        }
        with_default = build_design_achievement_summary([row], None)
        assert with_default["crest_cumple"] == 0
        with_neg = build_design_achievement_summary(
            [row], {"neg": 2.0, "pos": 1.0}
        )
        assert with_neg["crest_cumple"] == 1
        assert with_neg["crest_pct"] == 100
        assert with_neg["toe_pct"] is None

    def test_nan_rows_total_tracks_input_not_evaluable(self):
        rows = [
            _r1(),
            {"delta_crest": float("nan"), "delta_toe": "x"},
            {"berm_status": "NO CONSTRUIDO"},
            "not-a-dict",
        ]
        summary = build_design_achievement_summary(rows, None)
        assert summary["n_total"] == 4
        assert summary["n_evaluable"] == 1
        assert summary["global_score"] == 100
        assert summary["crest_cumple"] == 1
        assert summary["berm_denom"] == 1
        assert summary["berm_cumple"] == 1

    def test_pct_and_means_nullable_when_no_evidence(self):
        rows = [{"berm_status": "MISSING"}]
        summary = build_design_achievement_summary(rows, None)
        assert summary["crest_pct"] is None
        assert summary["toe_pct"] is None
        assert summary["delta_crest_mean"] is None


class TestToleranceValidation:
    @pytest.mark.parametrize("bad", [
        {"neg": -1.0, "pos": 1.0},
        {"neg": True, "pos": 1.0},
        {"neg": "x", "pos": 1.0},
        {"neg": float("nan"), "pos": 1.0},
        "not-a-dict",
    ])
    def test_invalid_tolerance_raises(self, bad):
        with pytest.raises((ValueError, TypeError)):
            build_design_achievement_summary([_r1()], bad)


class TestSectorBreakdown:
    def test_sectors_preserve_empty_string_identity(self, rows_mixed):
        empty_sector = {
            "section": "S9",
            "level": "900",
            "bench_num": 9,
            "sector": "",
            "delta_crest": 0.0,
            "delta_toe": 0.0,
            "berm_status": "CUMPLE",
        }
        breakdown = build_sector_achievement_summary(
            [*rows_mixed, empty_sector], {"neg": 1.0, "pos": 1.0}
        )
        by_sector = {entry["sector"]: entry for entry in breakdown}

        assert set(by_sector) == {"A", "B", ""}
        assert by_sector["A"]["n_evaluable"] == 2
        assert by_sector["A"]["crest_pct"] == 50
        assert by_sector["B"]["n_evaluable"] == 1
        assert by_sector[""]["crest_denom"] == 1
        assert by_sector[""]["crest_pct"] == 100
        assert math.isfinite(by_sector["A"]["delta_crest_mean"])
        assert breakdown == sorted(breakdown, key=lambda entry: str(entry["sector"]))

    def test_sector_without_evaluable_rows_has_null_score(self):
        rows = [
            {"sector": "DEAD", "delta_crest": float("nan"), "berm_status": "MISSING"},
            {"sector": "LIVE", "delta_crest": 0.0, "delta_toe": 0.0,
             "berm_status": "CUMPLE"},
        ]
        breakdown = build_sector_achievement_summary(rows, None)
        by_sector = {entry["sector"]: entry for entry in breakdown}
        assert by_sector["DEAD"]["global_score"] is None
        assert by_sector["DEAD"]["n_evaluable"] == 0
        assert by_sector["LIVE"]["global_score"] == 100

    def test_rows_without_sector_key_land_in_empty_string(self):
        breakdown = build_sector_achievement_summary([_r1()], None)
        assert [entry["sector"] for entry in breakdown] == ["A"]


class TestInvalidDeltaSanitization:
    def test_bool_delta_next_to_valid_berma_gets_no_credit(self):
        rows = [
            {
                "section": "S1",
                "level": "100",
                "bench_num": 1,
                "sector": "A",
                "delta_crest": True,
                "delta_toe": None,
                "berm_status": "CUMPLE",
            }
        ]
        summary = build_design_achievement_summary(rows, {"neg": 1.0, "pos": 1.0})

        assert summary["n_evaluable"] == 1
        assert summary["global_score"] == 30
        assert summary["crest_denom"] == 0
        assert summary["crest_pct"] is None
        assert summary["delta_crest_mean"] is None
