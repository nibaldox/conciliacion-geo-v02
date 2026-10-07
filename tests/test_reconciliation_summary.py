import math

import pytest

from core.reconciliation_summary import compute_global_compliance, compute_section_scores
from ui.tabs.dashboard_plan_view import compute_section_status


def test_global_averages_profiles_not_first_profile_or_all_banks():
    rows = [
        {"type": "MATCH", "section": "A", "bench_score": 100, "section_score": 90},
        {"type": "MATCH", "section": "A", "bench_score": 80, "section_score": 90},
        {"type": "MATCH", "section": "B", "bench_score": 40, "section_score": 40},
        {"type": "MISSING", "section": "A", "bench_score": 0},
        {"type": "EXTRA", "section": "C", "bench_score": 0},
    ]
    assert compute_global_compliance(rows) == (65, "NO CUMPLE")


@pytest.mark.parametrize("score,status", [(70, "CUMPLE"), (69.9, "NO CUMPLE")])
def test_inclusive_threshold(score, status):
    assert compute_global_compliance([{"type": "MATCH", "section": "A", "bench_score": score}]) == (score, status)


def test_filters_recompute_global_from_selected_banks():
    assert compute_global_compliance([{"type": "MATCH", "section": "A", "bench_score": 40, "section_score": 90}]) == (40, "NO CUMPLE")


@pytest.mark.parametrize("rows", [[], [{"type": "MISSING", "bench_score": 0}], [{"type": "MATCH", "bench_score": math.nan}]])
def test_absent_score_is_not_a_failed_profile(rows):
    assert compute_global_compliance(rows) == (0, "SIN DATOS")


def test_plan_scores_match_streamlit_canonical_and_fallback_rules():
    rows = [
        {"type": "MATCH", "section": "A", "bench_score": 40, "section_score": 70},
        {"type": "MATCH", "section": "B", "bench_score": 69.96},
        {"type": "MATCH", "section": "C", "bench_score": None},
    ]
    expected = compute_section_status(rows)
    scores = compute_section_scores(rows, prefer_canonical=True)
    assert {name: {"score": round(score, 1), "cumple": round(score, 1) >= 70} for name, score in scores.items()} == expected
