"""Parity tests for core.report_data against the shared web fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.report_data import (
    ReportFilters,
    build_report_data,
    filter_comparisons,
    parse_bench_status,
    worst_of_three,
)

FIXTURE = Path(__file__).parent / "fixtures" / "report_parity.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture()
def data():
    fx = _fixture()
    return fx, build_report_data(
        fx["rows"],
        {"tolerances": fx["tolerances"]},
        ReportFilters(),
        {"project": "P", "author": "A"},
    )


def _f(**kw):
    return ReportFilters(
        sectors=tuple(kw.get("sectors", ())),
        sections=tuple(kw.get("sections", ())),
        levels=tuple(kw.get("levels", ())),
        benches=tuple(kw.get("benches", ())),
    )


def test_parse_and_worst_match_web_semantics():
    assert parse_bench_status(None) == "UNKNOWN"
    assert parse_bench_status("FUERA") == "FUERA"
    assert parse_bench_status("BANCO ADICIONAL") == "NO_CUMPLE"
    assert parse_bench_status("NO CONSTRUIDO") == "NO_CUMPLE"
    assert worst_of_three("CUMPLE", "-", None) == "CUMPLE"
    assert worst_of_three("FUERA DE TOLERANCIA", "CUMPLE", "CUMPLE") == "FUERA"
    assert worst_of_three("BANCO ADICIONAL", "BANCO ADICIONAL", None) == "NO_CUMPLE"


def test_filter_counts_per_dimension(data):
    fx, _ = data
    rows = fx["rows"]
    exp = fx["expected"]["filter_counts"]
    cases = {
        "empty": _f(),
        "sector_A": _f(sectors=("A",)),
        "sector_B": _f(sectors=("B",)),
        "section_S01": _f(sections=("S-01",)),
        "section_S03": _f(sections=("S-03",)),
        "level_100": _f(levels=("100",)),
        "level_60": _f(levels=("60",)),
        "level_empty": _f(levels=("",)),
        "bench_1": _f(benches=(1,)),
        "bench_2": _f(benches=(2,)),
        "sector_A_section_S01": _f(sectors=("A",), sections=("S-01",)),
        "sector_A_bench_1": _f(sectors=("A",), benches=(1,)),
        "sector_Z": _f(sectors=("Z",)),
        "section_S01_bench_2": _f(sections=("S-01",), benches=(2,)),
    }
    for name, filters in cases.items():
        assert len(filter_comparisons(rows, filters)) == exp[name], name


def test_section_plan_states_require_unfiltered_bench_data():
    rows = [
        {"section": "S-01", "type": "MATCH", "bench_num": 1},
        {"section": "S-01", "type": "MATCH", "bench_num": 2},
        {"section": "S-02", "type": "MATCH", "bench_num": 2},
    ]
    filtered = build_report_data(
        rows, {}, _f(benches=(1,)), {},
        plan_inputs={"sections": [
            {"name": "S-01"}, {"name": "S-02"}, {"name": "S-03"},
        ]},
    )

    assert filtered.section_plan_states == (
        ("S-01", None, True, "UNKNOWN"),
        ("S-02", None, False, "UNKNOWN"),
    )
    assert filtered.resolve_section_plan_state("S-01", None) == filtered.section_plan_states[0]

    unfiltered = build_report_data(rows, {}, _f(), {})
    assert all(state[2] for state in unfiltered.section_plan_states)

    no_original_rows = build_report_data(
        [], {}, _f(benches=(1,)), {},
        plan_inputs={"sections": [{"name": "S-03"}]},
    )
    assert no_original_rows.section_plan_states == ()
    assert no_original_rows.resolve_section_plan_state("S-03", None) is None
    sector_filtered_no_rows = build_report_data([], {}, _f(sectors=("A",)), {})
    assert sector_filtered_no_rows.resolve_section_plan_state("S-03", "B") == (
        "S-03", "B", False, "UNKNOWN",
    )


def test_section_plan_states_use_sector_identity_and_leave_ambiguous_names_unresolved():
    rows = [
        {"section": "S-01", "sector": "A", "type": "MATCH", "bench_num": 1,
         "height_status": "CUMPLE", "angle_status": "CUMPLE", "berm_status": "CUMPLE"},
        {"section": "S-01", "sector": "B", "type": "MATCH", "bench_num": 1,
         "height_status": "NO CUMPLE", "angle_status": "NO CUMPLE", "berm_status": "NO CUMPLE"},
    ]
    data = build_report_data(rows, {}, _f(sectors=("A",)), {})

    assert data.section_plan_states == (
        ("S-01", "A", True, "CUMPLE"),
        ("S-01", "B", False, "UNKNOWN"),
    )
    assert data.resolve_section_plan_state("S-01", "A") == data.section_plan_states[0]
    assert data.resolve_section_plan_state("S-01", "B") == data.section_plan_states[1]
    assert data.resolve_section_plan_state("S-01", None) is None


def test_ambiguous_section_warning_preserves_existing_profile_grouping_and_scores():
    rows = [
        {"section": "S-01", "sector": "A", "type": "MATCH", "bench_num": 1,
         "height_status": "CUMPLE", "angle_status": "CUMPLE", "berm_status": "CUMPLE",
         "bench_score": 100},
        {"section": "S-01", "sector": "B", "type": "MATCH", "bench_num": 1,
         "height_status": "NO CUMPLE", "angle_status": "NO CUMPLE", "berm_status": "NO CUMPLE",
         "bench_score": 0},
    ]

    data = build_report_data(rows, {}, ReportFilters(), {})

    assert len(data.profiles) == 1
    assert data.profiles[0].section == "S-01"
    assert data.profiles[0].worst_status == "NO_CUMPLE"
    assert data.profiles[0].weighted_score == 50
    assert data.global_weighted_score == 50
    assert data.counts["n_sections"] == 1
    assert any("S-01" in warning and "más de una identidad de sector" in warning for warning in data.warnings)


def test_section_sector_filter_suppresses_resolved_ambiguity_warning():
    rows = [
        {"section": "S-01", "sector": "A", "type": "MATCH", "bench_num": 1},
        {"section": "S-01", "sector": "B", "type": "MATCH", "bench_num": 1},
    ]

    data = build_report_data(rows, {}, _f(sectors=("A",)), {})

    assert data.warnings == ()
    assert len(data.profiles) == 1


def test_same_section_and_sector_across_benches_is_not_ambiguous():
    rows = [
        {"section": "S-01", "sector": "A", "type": "MATCH", "bench_num": 1},
        {"section": "S-01", "sector": "A", "type": "MATCH", "bench_num": 2},
    ]

    data = build_report_data(rows, {}, ReportFilters(), {})

    assert not any("más de una identidad de sector" in warning for warning in data.warnings)


def test_missing_and_present_sector_identities_are_ambiguous():
    rows = [
        {"section": "S-02", "sector": None, "type": "MATCH", "bench_num": 1},
        {"section": "S-02", "sector": "A", "type": "MATCH", "bench_num": 1},
    ]

    data = build_report_data(rows, {}, ReportFilters(), {})

    assert any("S-02" in warning and "más de una identidad de sector" in warning for warning in data.warnings)


def test_counts_and_profile_statuses(data):
    fx, rd = data
    exp = fx["expected"]
    assert rd.counts["n_rows"] == exp["n_rows"]
    assert rd.counts["n_match"] == exp["n_match"]
    assert rd.counts["n_missing"] == exp["n_missing"]
    assert rd.counts["n_extra"] == exp["n_extra"]
    assert rd.counts["n_sections"] == exp["n_sections"]
    got = {p.section: p.worst_status for p in rd.profiles}
    assert got == exp["profiles"]
    assert rd.profile_counts == exp["profile_counts"]
    assert rd.profile_counts["NO_CUMPLE"] + rd.profile_counts["FUERA"] + rd.profile_counts["CUMPLE"] == len(rd.profiles)


def test_bench_status_labels(data):
    fx, rd = data
    assert [r.status_label for r in rd.rows] == fx["expected"]["bench_labels"]


@pytest.mark.parametrize("score, expected", [(69.9, "NO_CUMPLE"), (70, "CUMPLE"), (90, "CUMPLE"),
                                             (-1, "UNKNOWN"), (101, "UNKNOWN"),
                                             (float("nan"), "UNKNOWN"), (True, "UNKNOWN")])
def test_bench_status_uses_valid_score_independently_of_parameter_status(score, expected):
    row = {"type": "MATCH", "section": "S", "bench_score": score,
           "height_status": "CUMPLE", "angle_status": "NO CUMPLE", "berm_status": "CUMPLE"}
    result = build_report_data([row], {}, ReportFilters(), {})
    assert result.rows[0].worst_status == expected
    assert result.rows[0].angle_status == "NO CUMPLE"


def test_incomplete_bank_without_score_is_unknown():
    row = {"type": "MATCH", "section": "S", "berm_status": "CUMPLE"}
    result = build_report_data([row], {}, ReportFilters(), {})
    assert result.rows[0].worst_status == "UNKNOWN"
    assert result.profiles[0].weighted_score is None


def test_weighted_scores(data):
    fx, rd = data
    exp = fx["expected"]
    by_section = {p.section: p.weighted_score for p in rd.profiles}
    for section, score in exp["profile_scores"].items():
        assert by_section[section] == pytest.approx(score)
    assert by_section["S-04"] is None
    assert rd.global_weighted_score == pytest.approx(exp["global_weighted_score"])


def test_parameter_breakdown(data):
    fx, rd = data
    exp = {p["parameter"]: p for p in fx["expected"]["parameters"]}
    assert [p.parameter for p in rd.parameters] == ["height", "angle", "berm"]
    for p in rd.parameters:
        e = exp[p.parameter]
        assert p.cumple == e["cumple"], p.parameter
        assert p.no_cumple == e["no_cumple"], p.parameter
        assert p.pct_cumple == pytest.approx(e["pct_cumple"]), p.parameter
        assert p.mean_real == pytest.approx(e["mean_real"]), p.parameter


def test_top_deviations_ranked_relative_to_tolerance(data):
    fx, rd = data
    top = list(rd.top_deviations)[:3]
    for got, exp in zip(top, fx["expected"]["top_deviations_top3"]):
        assert got["section"] == exp["section"]
        assert got["parameter"] == exp["parameter"]
        assert got["deviation"] == pytest.approx(exp["deviation"])
        assert got["ratio"] == pytest.approx(exp["ratio"], abs=1e-3)
        assert "status" in got
    assert all(rd.top_deviations[i]["ratio"] >= rd.top_deviations[i + 1]["ratio"] for i in range(len(rd.top_deviations) - 1))


def test_design_achievement_matches_core_helper(data):
    fx, rd = data
    from core.design_achievement import (
        build_design_achievement_summary,
        build_sector_achievement_summary,
    )
    assert rd.design_achievement is not None
    assert rd.design_achievement["global"] == build_design_achievement_summary(fx["rows"], fx["ct_tol"])
    assert rd.design_achievement["sectors"] == build_sector_achievement_summary(fx["rows"], fx["ct_tol"])
    assert len(rd.design_achievement["sectors"]) == 2


def test_conclusions_and_warnings(data):
    fx, rd = data
    assert isinstance(rd.conclusions, tuple) and rd.conclusions
    joined = " ".join(rd.conclusions)
    for fragment in fx["expected"]["conclusions_contains"]:
        assert fragment in joined
    assert list(rd.conclusions) == list(rd.conclusions)
    rd2 = build_report_data(
        fx["rows"], {"tolerances": fx["tolerances"]}, ReportFilters(), {"project": "P"}
    )
    assert rd.conclusions == rd2.conclusions
    assert rd.warnings == ()


def test_depth_uses_existing_metric_and_none_without_geometry(data):
    _, rd = data
    assert rd.depth is None
    from types import SimpleNamespace
    bench = SimpleNamespace(floor_elevation=100.0, crest_elevation=130.0)
    rows = [{"type": "MATCH", "section": "S-01", "bench_real": bench}]
    rd2 = build_report_data(rows, {"tolerances": {}}, ReportFilters(), {})
    assert rd2.depth is not None
    assert rd2.depth["cota_piso"] == 100.0
    assert rd2.depth["cota_cresta"] == 130.0
    assert rd2.depth["profundidad"] == 30.0


def test_depth_joins_filtered_rows_to_unfiltered_topo_by_topo_bank_number():
    from types import SimpleNamespace

    rows = [
        {"type": "MATCH", "section": "S-01", "sector": "N", "bench_num": 7,
         "bench_num_topo": 2, "bench_real": None},
        {"type": "MATCH", "section": "S-01", "sector": "N", "bench_num": 8,
         "bench_num_topo": 1, "bench_real": None},
        {"type": "EXTRA", "section": "S-01", "sector": "N", "bench_num": 999,
         "bench_num_topo": 3, "bench_real": None},
    ]
    topo = {("S-01", "N"): [
        SimpleNamespace(bench_number=1, floor_elevation=90.0, crest_elevation=100.0),
        SimpleNamespace(bench_number=2, floor_elevation=80.0, crest_elevation=90.0),
        SimpleNamespace(bench_number=3, floor_elevation=70.0, crest_elevation=80.0),
    ]}

    report = build_report_data(rows, {}, _f(benches=(7,)), {}, depth_extractions=topo)

    assert report.depth == {
        "cota_piso": 80.0, "cota_cresta": 90.0, "profundidad": 10.0,
        "n_floors": 1, "n_crests": 1,
    }
    unfiltered = build_report_data(rows, {}, ReportFilters(), {}, depth_extractions=topo)
    assert unfiltered.depth["cota_piso"] == 70.0
    assert unfiltered.depth["cota_cresta"] == 100.0
    assert unfiltered.depth["profundidad"] == 30.0


def test_depth_is_unknown_when_filtered_row_cannot_be_resolved_completely():
    from types import SimpleNamespace

    rows = [
        {"type": "MATCH", "section": "S-01", "sector": "N", "bench_num": 1,
         "bench_num_topo": 1},
        {"type": "MATCH", "section": "S-01", "sector": "N", "bench_num": 2,
         "bench_num_topo": 2},
    ]
    topo = {("S-01", "N"): [
        SimpleNamespace(bench_number=1, floor_elevation=80.0, crest_elevation=90.0),
    ]}

    report = build_report_data(rows, {}, ReportFilters(), {}, depth_extractions=topo)

    assert report.depth is None


def test_depth_join_trims_sector_without_changing_report_filter_matching():
    from types import SimpleNamespace

    rows = [{
        "type": "MATCH", "section": "S-01", "sector": " Norte ",
        "bench_num": 7, "bench_num_topo": 2,
    }]
    topo = {("S-01", "Norte"): [
        SimpleNamespace(bench_number=2, floor_elevation=80.0, crest_elevation=90.0),
    ]}

    report = build_report_data(rows, {}, ReportFilters(), {}, depth_extractions=topo)

    assert report.depth["profundidad"] == 10.0
    assert filter_comparisons(rows, ReportFilters(sectors=("Norte",))) == []


def test_empty_filters_result_all_and_empty_warnings():
    empty = build_report_data([], {"tolerances": {}}, ReportFilters(), {})
    assert empty.rows == ()
    assert empty.global_weighted_score is None
    assert any("comparaciones" in w for w in empty.warnings)


def test_weighted_scores_fallback_matches_web_bench_score():
    fx = _fixture()
    rd = build_report_data(
        fx["fallback_rows"],
        {"tolerances": fx["tolerances"]},
        ReportFilters(),
        {"project": "P"},
    )
    exp = fx["fallback_expected"]
    by_section = {p.section: p.weighted_score for p in rd.profiles}
    for section, score in exp["profile_scores"].items():
        if score is None:
            assert by_section[section] is None, section
        else:
            assert by_section[section] == pytest.approx(score), section
    assert rd.global_weighted_score == pytest.approx(exp["global_weighted_score"])


MIN_WIDTH_ROWS = [
    {
        "sector": "A", "section": "S-01", "bench_num": 1, "type": "MATCH", "level": "100",
        "berm_design": 8.0, "berm_real": 8.2, "berm_dev": 0.2, "berm_min": 7.0,
        "berm_status": "CUMPLE",
    },
    {
        "sector": "A", "section": "S-02", "bench_num": 1, "type": "MATCH", "level": "90",
        "berm_design": 8.0, "berm_real": 3.5, "berm_dev": -4.5, "berm_min": 7.0,
        "berm_status": "NO CUMPLE",
    },
    {
        "sector": "B", "section": "S-03", "bench_num": 2, "type": "MATCH", "level": "80",
        "berm_design": 8.0, "berm_real": 6.3, "berm_dev": -1.7, "berm_min": 7.0,
        "berm_status": "FUERA DE TOLERANCIA",
    },
]

MIN_WIDTH_SETTINGS = {"tolerances": {"berm_width": {"min": 7.0}}}


def test_min_width_berm_rows_ranked_by_shortfall():
    rd = build_report_data(MIN_WIDTH_ROWS, MIN_WIDTH_SETTINGS, ReportFilters(), {})
    berm = [e for e in rd.top_deviations if e["parameter"] == "berm"]
    assert [e["section"] for e in berm] == ["S-02", "S-03"]
    worst = berm[0]
    assert worst["unit"] == "m"
    assert worst["design"] == pytest.approx(8.0)
    assert worst["real"] == pytest.approx(3.5)
    assert worst["deviation"] == pytest.approx(3.5 - 7.0)
    assert worst["shortfall"] == pytest.approx(3.5)
    assert worst["tolerance"] == pytest.approx(7.0)
    assert worst["tolerance_text"] == "mín 7.00 m"
    assert worst["criterion"] == "min"
    assert worst["ratio"] == pytest.approx(0.5)
    assert worst["status"] == "NO CUMPLE"
    assert berm[1]["ratio"] == pytest.approx(0.7 / 7.0)
    assert worst["ratio"] > berm[1]["ratio"]


def test_min_width_berm_uses_row_minimum_and_signed_tolerance_still_ranks():
    from_row = build_report_data(
        MIN_WIDTH_ROWS, {"tolerances": {"berm_width": {}}}, ReportFilters(), {}
    )
    assert [e["criterion"] for e in from_row.top_deviations] == ["min", "min"]
    assert [e["ratio"] for e in from_row.top_deviations] == [
        pytest.approx(0.5), pytest.approx(0.7 / 7.0),
    ]
    signed = build_report_data(
        MIN_WIDTH_ROWS,
        {"tolerances": {"berm_width": {"neg": 1.0, "pos": 1.0}}},
        ReportFilters(),
        {},
    )
    assert [e["criterion"] for e in signed.top_deviations] == ["signed"] * 3
    assert [e["deviation"] for e in signed.top_deviations] == [
        pytest.approx(-4.5), pytest.approx(-1.7), pytest.approx(0.2),
    ]


def test_min_width_berm_skips_compliant_and_unbounded_rows():
    compliant = build_report_data(MIN_WIDTH_ROWS[:1], MIN_WIDTH_SETTINGS, ReportFilters(), {})
    assert compliant.top_deviations == ()
    unbounded = build_report_data(
        [{"type": "MATCH", "section": "S-09", "berm_real": 3.0, "berm_dev": -1.0,
          "berm_status": "NO CUMPLE"}],
        {"tolerances": {"berm_width": {"neg": 1.0}}},
        ReportFilters(),
        {},
    )
    assert unbounded.top_deviations == ()


def test_blast_empty_payload_is_explicit_exclusion_and_none_keeps_settings_fallback():
    holes = [{"hole_id": "H1", "x": 1.0, "y": 2.0, "z": 3.0}]
    settings = {"tolerances": {}, "blast_holes": holes}
    rows = [{"type": "MATCH", "section": "S-01", "sector": "A", "bench_num": 1, "level": "100"}]

    excluded = build_report_data(rows, settings, ReportFilters(), {}, blast={})
    assert excluded.blast is None

    fallback = build_report_data(rows, settings, ReportFilters(), {})
    assert fallback.blast == {"holes": holes, "tolerance": None}
