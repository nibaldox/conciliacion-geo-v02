"""Nominal-level and per-sector level filters of core.report_data (contract C4)."""
from __future__ import annotations

import copy
import dataclasses

import pytest

from core.report_data import ReportFilters, build_report_data, filter_comparisons
from core.report_levels import NominalLevel, assign_nominal_levels

BENCH_3_DISTRIBUTION = (
    [3104] * 71
    + [3095] * 16
    + [3096] * 2
    + [3099] * 2
    + [3097, 3098, 3101, 3102, 3103]
)
EXTRA_LEVELS = {"S-22": 3120, "S-25": 3122}


def _row(section, bench_num, row_type, level, height_design=15.0, sector="", **extra):
    row = {
        "sector": sector,
        "section": section,
        "bench_num": bench_num,
        "type": row_type,
        "level": level,
        "height_design": height_design,
    }
    row.update(extra)
    return row


def _real_session_rows():
    rows = []
    for index, bench_3_level in enumerate(BENCH_3_DISTRIBUTION, start=1):
        section = f"S-{index:02d}"
        rows.append(_row(section, 1, "MATCH", "3125"))
        if section in EXTRA_LEVELS:
            rows.append(_row(section, 999, "EXTRA", str(EXTRA_LEVELS[section]), None))
        rows.append(_row(section, 2, "MATCH", "3110"))
        rows.append(_row(section, 3, "MISSING", str(bench_3_level), 5.88))
    return rows


def _sector_rows(sector, prefix, shift=0):
    rows = []
    for index, offset in enumerate((0, 0, 1), start=1):
        section = f"{prefix}-{index:02d}"
        rows.append(_row(section, 1, "MATCH", str(3125 - shift - offset), sector=sector))
        rows.append(_row(section, 2, "MATCH", str(3110 - shift + offset), sector=sector))
    return rows


def _two_sector_rows():
    return _sector_rows("Norte", "N") + _sector_rows("Sur", "S") + _sector_rows("Este", "E")


def _statuses(status):
    return {"height_status": status, "angle_status": status, "berm_status": status}


def _scored_rows():
    rows = []
    for index, (low_score, level_3110) in enumerate(
        ((80.0, "3110"), (90.0, "3109"), (100.0, "3111")), start=1
    ):
        section = f"S-{index:02d}"
        rows.append(
            _row(section, 1, "MATCH", "3125", sector="A", bench_score=20.0,
                 height_real=11.0, angle_real=60.0, berm_real=4.0,
                 height_dev=-4.0, **_statuses("NO CUMPLE"))
        )
        rows.append(
            _row(section, 2, "MATCH", level_3110, sector="A", bench_score=low_score,
                 height_real=15.0, angle_real=70.0, berm_real=9.0,
                 height_dev=0.2, **_statuses("CUMPLE"))
        )
    return rows


class TestReportFiltersContract:
    def test_levels_by_sector_defaults_to_empty_tuple(self):
        filters = ReportFilters()
        assert filters.levels_by_sector == ()
        assert filters.is_empty()

    def test_is_empty_accounts_for_levels_by_sector(self):
        assert not ReportFilters(levels_by_sector=(("Norte", ("3110",)),)).is_empty()

    def test_filters_stay_frozen_and_hashable(self):
        filters = ReportFilters(levels=("3125",), levels_by_sector=(("Norte", ("3110",)),))
        assert hash(filters) == hash(
            ReportFilters(levels=("3125",), levels_by_sector=(("Norte", ("3110",)),))
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            filters.levels_by_sector = ()

    def test_levels_for_returns_sector_selection_or_global(self):
        filters = ReportFilters(
            levels=("3125",),
            levels_by_sector=(("Norte", ("3110", "3104")), ("Sur", ())),
        )
        assert filters.levels_for("Norte") == ("3110", "3104")
        assert filters.levels_for("Sur") == ()
        assert filters.levels_for("Este") == ("3125",)
        assert ReportFilters().levels_for("Norte") == ()


class TestNominalLevelFilter:
    def test_fixture_matches_the_real_session_shape(self):
        rows = _real_session_rows()
        assert len(rows) == 290
        assert sum(1 for row in rows if row["level"] == "3104") == 71

    def test_level_3104_keeps_all_96_missing_bench_3_rows(self):
        out = filter_comparisons(_real_session_rows(), ReportFilters(levels=("3104",)))

        assert len(out) == 96
        assert {row["type"] for row in out} == {"MISSING"}
        assert {row["bench_num"] for row in out} == {3}
        assert len({row["section"] for row in out}) == 96
        assert sorted({row["level"] for row in out}) == [
            "3095", "3096", "3097", "3098", "3099", "3101", "3102", "3103", "3104",
        ]
        assert {row["level_nominal"] for row in out} == {"3104"}

    def test_level_3125_includes_the_extra_rows_of_that_nominal_level(self):
        out = filter_comparisons(_real_session_rows(), ReportFilters(levels=("3125",)))

        assert len(out) == 98
        extras = sorted((row["section"], row["level"]) for row in out if row["type"] == "EXTRA")
        assert extras == [("S-22", "3120"), ("S-25", "3122")]

    def test_values_within_the_level_dimension_are_ored(self):
        out = filter_comparisons(
            _real_session_rows(), ReportFilters(levels=("3110", "3104"))
        )
        assert len(out) == 192
        assert {row["level_nominal"] for row in out} == {"3110", "3104"}

    def test_exact_level_fallback_for_a_value_that_is_not_a_nominal_label(self):
        out = filter_comparisons(_real_session_rows(), ReportFilters(levels=("3099",)))

        assert len(out) == 2
        assert {row["level"] for row in out} == {"3099"}
        assert {row["level_nominal"] for row in out} == {"3104"}

    def test_exact_fallback_and_nominal_label_combine_with_or(self):
        out = filter_comparisons(
            _real_session_rows(), ReportFilters(levels=("3099", "3110"))
        )
        assert len(out) == 98
        assert {row["level"] for row in out} == {"3099", "3110"}

    def test_unknown_level_matches_nothing(self):
        assert filter_comparisons(_real_session_rows(), ReportFilters(levels=("2000",))) == []

    def test_grouping_does_not_depend_on_other_filters(self):
        rows = _real_session_rows()
        section = next(row["section"] for row in rows if row["level"] == "3095")

        out = filter_comparisons(
            rows, ReportFilters(sections=(section,), levels=("3104",))
        )

        assert [(row["section"], row["level"], row["level_nominal"]) for row in out] == [
            (section, "3095", "3104")
        ]

    def test_level_is_anded_with_bench_dimension(self):
        rows = _real_session_rows()
        assert filter_comparisons(rows, ReportFilters(levels=("3104",), benches=(2,))) == []
        assert len(filter_comparisons(rows, ReportFilters(levels=("3104",), benches=(3,)))) == 96

    def test_empty_level_text_stays_selectable(self):
        rows = _real_session_rows() + [_row("S-97", 999, "EXTRA", "", None)]

        out = filter_comparisons(rows, ReportFilters(levels=("",)))

        assert [(row["section"], row["level_nominal"]) for row in out] == [("S-97", None)]

    def test_numeric_level_values_use_the_same_key_as_the_assignment(self):
        rows = [
            _row("S-01", 1, "MATCH", 3125),
            _row("S-01", 2, "MATCH", 3110.0),
            _row("S-02", 1, "MATCH", 3124),
            _row("S-02", 2, "MATCH", 3109.0),
        ]
        out = filter_comparisons(rows, ReportFilters(levels=("3110",)))
        assert [(row["section"], row["level"]) for row in out] == [
            ("S-01", 3110.0), ("S-02", 3109.0)
        ]
        assert {row["level_nominal"] for row in out} == {"3110"}


class TestLevelsBySector:
    def test_each_sector_keeps_only_its_level_and_absent_sector_keeps_all(self):
        filters = ReportFilters(
            levels_by_sector=(("Norte", ("3110",)), ("Sur", ("3125",)))
        )

        out = filter_comparisons(_two_sector_rows(), filters)

        levels = {}
        for row in out:
            levels.setdefault(row["sector"], []).append(row["level"])
        assert sorted(levels["Norte"]) == ["3110", "3110", "3111"]
        assert sorted(levels["Sur"]) == ["3124", "3125", "3125"]
        assert sorted(levels["Este"]) == ["3110", "3110", "3111", "3124", "3125", "3125"]
        assert {(row["sector"], row["level_nominal"]) for row in out} == {
            ("Norte", "3110"), ("Sur", "3125"), ("Este", "3125"), ("Este", "3110"),
        }

    def test_sector_selection_uses_the_nominal_labels_of_that_sector(self):
        rows = _sector_rows("Norte", "N") + _sector_rows("Sur", "S", shift=2)
        labels = {
            (level.sector, level.label) for level in assign_nominal_levels(rows).levels
        }
        assert labels == {
            ("Norte", "3125"), ("Norte", "3110"), ("Sur", "3123"), ("Sur", "3108"),
        }

        by_sector = filter_comparisons(
            rows, ReportFilters(levels_by_sector=(("Sur", ("3123",)),), sectors=("Sur",))
        )
        global_only = filter_comparisons(rows, ReportFilters(levels=("3125",)))

        assert sorted(row["level"] for row in by_sector) == ["3122", "3123", "3123"]
        assert {row["sector"] for row in global_only} == {"Norte"}
        assert len(global_only) == 3

    def test_sector_absent_from_the_map_uses_the_global_levels(self):
        filters = ReportFilters(
            levels=("3125",), levels_by_sector=(("Norte", ("3110",)),)
        )

        out = filter_comparisons(_two_sector_rows(), filters)

        assert {(row["sector"], row["level_nominal"]) for row in out} == {
            ("Norte", "3110"), ("Sur", "3125"), ("Este", "3125"),
        }
        assert len(out) == 9

    def test_empty_sector_selection_overrides_the_global_levels(self):
        filters = ReportFilters(levels=("3125",), levels_by_sector=(("Norte", ()),))

        out = filter_comparisons(_two_sector_rows(), filters)

        assert len([row for row in out if row["sector"] == "Norte"]) == 6
        assert len([row for row in out if row["sector"] == "Sur"]) == 3

    def test_level_map_is_anded_with_the_sector_dimension(self):
        filters = ReportFilters(
            sectors=("Sur",), levels_by_sector=(("Norte", ("3110",)), ("Sur", ("3125",)))
        )

        out = filter_comparisons(_two_sector_rows(), filters)

        assert {(row["sector"], row["level_nominal"]) for row in out} == {("Sur", "3125")}
        assert len(out) == 3

    def test_rows_without_sector_use_the_empty_sector_key(self):
        rows = _real_session_rows()
        out = filter_comparisons(rows, ReportFilters(levels_by_sector=(("", ("3110",)),)))
        assert len(out) == 96
        assert {row["level"] for row in out} == {"3110"}

        no_sector = [dict(row, sector=None) for row in rows]
        out = filter_comparisons(no_sector, ReportFilters(levels_by_sector=(("", ("3104",)),)))
        assert len(out) == 96


class TestLevelNominalKey:
    def test_empty_filters_return_every_row_with_level_nominal(self):
        rows = _real_session_rows()

        out = filter_comparisons(rows, ReportFilters())

        assert len(out) == 290
        assert all("level_nominal" in row for row in out)
        assert {row["level_nominal"] for row in out} == {"3125", "3110", "3104"}
        assert [
            {key: value for key, value in row.items() if key != "level_nominal"}
            for row in out
        ] == rows

    def test_level_nominal_matches_the_c1_assignment(self):
        rows = _real_session_rows()
        assignment = assign_nominal_levels(rows)

        for row in filter_comparisons(rows, ReportFilters()):
            key = ("", row["section"], row["bench_num"], row["type"], row["level"])
            assert row["level_nominal"] == assignment.row_level[key]

    def test_unassigned_rows_carry_none(self):
        rows = [
            _row("S-01", 1, "MATCH", "3125"),
            _row("S-01", 2, "MATCH", "sin cota"),
            _row("S-01", None, "MATCH", "3110"),
            _row("S-01", 4, "INFO", "3095"),
        ]

        out = filter_comparisons(rows, ReportFilters())

        assert [row["level_nominal"] for row in out] == ["3125", None, None, None]

    def test_input_rows_are_not_mutated(self):
        rows = _real_session_rows()
        snapshot = copy.deepcopy(rows)

        out = filter_comparisons(
            rows, ReportFilters(levels=("3104",), levels_by_sector=(("", ("3110",)),))
        )

        assert rows == snapshot
        assert all("level_nominal" not in row for row in rows)
        assert all(result is not source for result in out for source in rows)

    def test_existing_level_nominal_key_is_replaced_by_the_computed_label(self):
        rows = [dict(row, level_nominal="stale") for row in _real_session_rows()[:3]]
        out = filter_comparisons(rows, ReportFilters())
        assert "stale" not in {row["level_nominal"] for row in out}


class TestBuildReportDataByLevel:
    def test_unfiltered_baseline_is_dominated_by_the_3125_benches(self):
        report = build_report_data(_scored_rows(), {}, ReportFilters(), {})

        assert {profile.worst_status for profile in report.profiles} == {"NO_CUMPLE"}
        assert report.counts["n_rows"] == 6
        assert report.global_weighted_score == pytest.approx((50.0 + 55.0 + 60.0) / 3)

    def test_level_selection_restricts_statuses_scores_counts_and_parameters(self):
        report = build_report_data(
            _scored_rows(), {}, ReportFilters(levels=("3110",)), {}
        )

        assert [profile.section for profile in report.profiles] == ["S-01", "S-02", "S-03"]
        assert {profile.worst_status for profile in report.profiles} == {"CUMPLE"}
        assert [profile.weighted_score for profile in report.profiles] == [80.0, 90.0, 100.0]
        assert [(p.n_match, p.n_missing, p.n_extra) for p in report.profiles] == [(1, 0, 0)] * 3
        assert report.profile_counts == {"CUMPLE": 3, "FUERA": 0, "NO_CUMPLE": 0}
        assert report.global_weighted_score == pytest.approx(90.0)
        assert report.counts == {
            "n_rows": 3, "n_match": 3, "n_missing": 0, "n_extra": 0, "n_sections": 3,
        }
        assert sorted(row.level for row in report.rows) == ["3109", "3110", "3111"]
        for parameter in report.parameters:
            assert (parameter.cumple, parameter.no_cumple) == (3, 0)
            assert parameter.pct_cumple == pytest.approx(100.0)
        height = next(p for p in report.parameters if p.parameter == "height")
        assert height.mean_real == pytest.approx(15.0)

    def test_level_selection_restricts_top_deviations_and_design_achievement(self):
        settings = {"tolerances": {"bench_height": {"neg": 1.0, "pos": 1.5}}}

        full = build_report_data(_scored_rows(), settings, ReportFilters(), {})
        report = build_report_data(
            _scored_rows(), settings, ReportFilters(levels=("3110",)), {}
        )

        assert len(full.top_deviations) == 6
        assert len(report.top_deviations) == 3
        assert {entry["bench_num"] for entry in report.top_deviations} == {2}
        assert {entry["deviation"] for entry in report.top_deviations} == {0.2}
        assert full.design_achievement["global"]["n_total"] == 6
        assert full.design_achievement["global"]["berm_pct"] == 50
        assert report.design_achievement["global"]["n_total"] == 3
        assert report.design_achievement["global"]["berm_pct"] == 100
        assert [
            (sector["sector"], sector["n_total"], sector["global_score"])
            for sector in report.design_achievement["sectors"]
        ] == [("A", 3, 100)]

    def test_per_sector_levels_reach_the_report(self):
        rows = _scored_rows() + [dict(row, sector="B", section="T" + row["section"][1:])
                                 for row in _scored_rows()]
        filters = ReportFilters(levels_by_sector=(("A", ("3110",)), ("B", ("3125",))))

        report = build_report_data(rows, {}, filters, {})

        status = {(p.sector, p.worst_status) for p in report.profiles}
        assert status == {("A", "CUMPLE"), ("B", "NO_CUMPLE")}
        assert report.counts["n_rows"] == 6

    def test_report_exposes_unfiltered_nominal_levels_and_c1_warnings(self):
        rows = _real_session_rows()
        assignment = assign_nominal_levels(rows)

        report = build_report_data(rows, {}, ReportFilters(levels=("3104",)), {})

        assert report.nominal_levels == assignment.levels
        assert all(isinstance(level, NominalLevel) for level in report.nominal_levels)
        assert [level.label for level in report.nominal_levels] == ["3125", "3110", "3104"]
        assert report.level_warnings == ()
        assert report.counts["n_rows"] == 96
        assert report.counts["n_missing"] == 96

    def test_nominal_levels_default_to_empty_without_rows(self):
        report = build_report_data([], {}, ReportFilters(), {})
        assert report.nominal_levels == ()
        assert report.level_warnings == ()

    def test_plan_states_keep_unfiltered_identities_under_a_level_filter(self):
        rows = _scored_rows() + [
            _row("S-09", 1, "MATCH", "3125", sector="A", bench_score=20.0)
        ]

        report = build_report_data(rows, {}, ReportFilters(levels=("3110",)), {})

        states = {state[0]: state for state in report.section_plan_states}
        assert set(states) == {"S-01", "S-02", "S-03", "S-09"}
        assert states["S-01"] == ("S-01", "A", True, "CUMPLE")
        assert states["S-09"] == ("S-09", "A", False, "UNKNOWN")

    def test_level_filter_without_matches_warns(self):
        report = build_report_data(
            _scored_rows(), {}, ReportFilters(levels_by_sector=(("A", ("2000",)),)), {}
        )
        assert report.rows == ()
        assert any("filtros" in warning for warning in report.warnings)
