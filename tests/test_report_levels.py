import copy
import dataclasses

import pytest

from core.report_levels import (
    NominalLevel,
    NominalLevelAssignment,
    assign_nominal_levels,
)

BENCH_3_DISTRIBUTION = (
    [3104] * 71
    + [3095] * 16
    + [3096] * 2
    + [3099] * 2
    + [3097, 3098, 3101, 3102, 3103]
)
EXTRA_LEVELS = {"S-22": 3120, "S-25": 3122}


def _row(section, bench_num, row_type, level, height_design=15.0, sector=""):
    return {
        "sector": sector,
        "section": section,
        "bench_num": bench_num,
        "type": row_type,
        "level": level,
        "height_design": height_design,
    }


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


def _by_label(assignment, sector=""):
    return {level.label: level for level in assignment.levels if level.sector == sector}


class TestRealSessionLevels:
    def test_fixture_matches_the_real_session_shape(self):
        rows = _real_session_rows()
        assert len(BENCH_3_DISTRIBUTION) == 96
        assert len(rows) == 290

    def test_groups_into_exactly_three_nominal_levels(self):
        assignment = assign_nominal_levels(_real_session_rows())

        assert isinstance(assignment, NominalLevelAssignment)
        assert [level.label for level in assignment.levels] == ["3125", "3110", "3104"]
        assert all(isinstance(level, NominalLevel) for level in assignment.levels)
        assert all(level.sector == "" for level in assignment.levels)

    def test_extra_rows_fall_in_the_bench_1_level(self):
        assignment = assign_nominal_levels(_real_session_rows())

        assert assignment.row_level[("", "S-22", 999, "EXTRA", "3120")] == "3125"
        assert assignment.row_level[("", "S-25", 999, "EXTRA", "3122")] == "3125"
        assert assignment.row_level[("", "S-22", 1, "MATCH", "3125")] == "3125"

    def test_group_statistics(self):
        levels = _by_label(assign_nominal_levels(_real_session_rows()))

        top = levels["3125"]
        assert top.elevation == pytest.approx(3125.0)
        assert (top.min_level, top.max_level) == (3120.0, 3125.0)
        assert (top.n_sections, top.n_rows) == (96, 98)

        middle = levels["3110"]
        assert middle.elevation == pytest.approx(3110.0)
        assert (middle.min_level, middle.max_level) == (3110.0, 3110.0)
        assert (middle.n_sections, middle.n_rows) == (96, 96)

        bottom = levels["3104"]
        assert bottom.elevation == pytest.approx(3104.0)
        assert (bottom.min_level, bottom.max_level) == (3095.0, 3104.0)
        assert (bottom.n_sections, bottom.n_rows) == (96, 96)

    def test_every_row_is_assigned(self):
        rows = _real_session_rows()
        assignment = assign_nominal_levels(rows)

        assert len(assignment.row_level) == len(rows)
        bench_3_labels = {
            label for key, label in assignment.row_level.items() if key[2] == 3
        }
        assert bench_3_labels == {"3104"}

    def test_extra_sharing_a_level_with_a_design_bench_is_warned(self):
        assignment = assign_nominal_levels(_real_session_rows())

        shared = [w for w in assignment.warnings if "adicional" in w]
        assert len(shared) == 1
        assert "3125" in shared[0]
        assert "S-22" in shared[0] and "S-25" in shared[0]


class TestGapThreshold:
    def test_gap_equal_to_one_third_of_bench_height_splits(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-02", 1, "MATCH", "3105"),
        ]

        assignment = assign_nominal_levels(rows)

        assert [level.label for level in assignment.levels] == ["3110", "3105"]

    def test_gap_below_one_third_of_bench_height_groups(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-02", 1, "MATCH", "3106"),
        ]

        assignment = assign_nominal_levels(rows)

        assert len(assignment.levels) == 1
        assert assignment.levels[0].elevation == pytest.approx(3108.0)
        assert assignment.levels[0].label == "3108"

    def test_threshold_uses_the_median_height_design(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110", 30.0),
            _row("S-02", 1, "MATCH", "3104", 30.0),
            _row("S-03", 1, "MATCH", "3104", 6.0),
        ]

        assignment = assign_nominal_levels(rows)

        assert len(assignment.levels) == 1

    def test_label_is_the_rounded_median(self):
        rows = [
            _row("S-01", 1, "MATCH", "3104"),
            _row("S-02", 1, "MATCH", "3104"),
            _row("S-03", 1, "MATCH", "3101"),
        ]

        assignment = assign_nominal_levels(rows)

        assert assignment.levels[0].label == "3104"
        assert assignment.levels[0].elevation == pytest.approx(3104.0)


    def test_label_rounds_a_half_up(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-02", 1, "MATCH", "3107"),
        ]

        assignment = assign_nominal_levels(rows)

        assert assignment.levels[0].elevation == pytest.approx(3108.5)
        assert assignment.levels[0].label == "3109"

    @pytest.mark.parametrize(
        ("level", "label"),
        [(3108.5, "3109"), (3109.5, "3110"), (3108.49, "3108"), (0.5, "1"), (-0.5, "0"), (-1.5, "-1")],
    )
    def test_half_up_rounding_of_a_single_level(self, level, label):
        assignment = assign_nominal_levels([_row("S-01", 1, "MATCH", level)])

        assert assignment.levels[0].label == label


class TestSameSectionConstraint:
    def test_two_benches_of_one_section_never_share_a_level(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-01", 2, "MATCH", "3107"),
        ]

        assignment = assign_nominal_levels(rows)

        assert len(assignment.levels) == 2
        assert assignment.row_level[("", "S-01", 1, "MATCH", "3110")] == "3110"
        assert assignment.row_level[("", "S-01", 2, "MATCH", "3107")] == "3107"

    def test_split_uses_the_largest_gap_between_the_two_rows(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-01", 2, "MISSING", "3106"),
            _row("S-02", 1, "MATCH", "3109"),
        ]

        assignment = assign_nominal_levels(rows)

        assert assignment.row_level[("", "S-01", 1, "MATCH", "3110")] == assignment.row_level[
            ("", "S-02", 1, "MATCH", "3109")
        ]
        assert (
            assignment.row_level[("", "S-01", 2, "MISSING", "3106")]
            != assignment.row_level[("", "S-01", 1, "MATCH", "3110")]
        )
        levels = _by_label(assignment)
        assert levels["3106"].n_rows == 1
        assert (levels["3110"].min_level, levels["3110"].max_level) == (3109.0, 3110.0)

    def test_three_benches_of_one_section_end_in_three_levels(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-01", 2, "MATCH", "3108"),
            _row("S-01", 3, "MATCH", "3105"),
            _row("S-02", 1, "MATCH", "3109"),
        ]

        assignment = assign_nominal_levels(rows)

        labels = {
            assignment.row_level[("", "S-01", bench, "MATCH", level)]
            for bench, level in ((1, "3110"), (2, "3108"), (3, "3105"))
        }
        assert len(labels) == 3

    def test_same_exact_level_in_one_section_cannot_be_split_and_warns(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-01", 2, "MATCH", "3110"),
        ]

        assignment = assign_nominal_levels(rows)

        assert len(assignment.levels) == 1
        assert assignment.levels[0].n_rows == 2
        assert assignment.levels[0].n_sections == 1
        assert any("S-01" in w and "3110" in w for w in assignment.warnings)


class TestMissingHeightDesign:
    @pytest.mark.parametrize("height", [None, "", "abc", float("nan"), 0.0, -15.0, True])
    def test_no_valid_height_gives_one_group_per_exact_level_and_warns(self, height):
        rows = [
            _row("S-01", 1, "MATCH", "3110", height),
            _row("S-02", 1, "MATCH", "3109", height),
            _row("S-03", 1, "MATCH", "3109", height),
        ]

        assignment = assign_nominal_levels(rows)

        assert [level.label for level in assignment.levels] == ["3110", "3109"]
        assert [level.n_rows for level in assignment.levels] == [1, 2]
        assert any("altura" in w for w in assignment.warnings)

    def test_valid_height_does_not_warn(self):
        assignment = assign_nominal_levels([_row("S-01", 1, "MATCH", "3110")])

        assert assignment.warnings == ()


class TestInvalidLevel:
    @pytest.mark.parametrize(
        "level", [None, "", "  ", "abc", float("nan"), float("inf"), True]
    )
    def test_invalid_level_is_excluded_with_warning(self, level):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-02", 1, "MATCH", level),
        ]

        assignment = assign_nominal_levels(rows)

        assert all(key[1] != "S-02" for key in assignment.row_level)
        assert assignment.row_level == {("", "S-01", 1, "MATCH", "3110"): "3110"}
        assert [level.label for level in assignment.levels] == ["3110"]
        assert assignment.levels[0].n_rows == 1
        assert any("S-02" in w for w in assignment.warnings)

    def test_missing_level_key_is_excluded_and_never_becomes_zero(self):
        row = _row("S-02", 1, "MATCH", "3110")
        del row["level"]

        assignment = assign_nominal_levels([row])

        assert assignment.levels == ()
        assert assignment.row_level == {}
        assert "0" not in {level.label for level in assignment.levels}
        assert len(assignment.warnings) == 1

    def test_numeric_level_is_accepted(self):
        assignment = assign_nominal_levels([_row("S-01", 1, "MATCH", 3110.4)])

        assert assignment.levels[0].label == "3110"
        assert assignment.levels[0].elevation == pytest.approx(3110.4)

    def test_real_zero_level_is_kept(self):
        assignment = assign_nominal_levels([_row("S-01", 1, "MATCH", "0")])

        assert assignment.levels[0].label == "0"
        assert assignment.warnings == ()


class TestSectors:
    def test_sectors_are_grouped_independently(self):
        rows = [
            _row("S-01", 1, "MATCH", "3125", sector="Norte"),
            _row("S-02", 1, "MATCH", "3125", sector="Norte"),
            _row("S-03", 1, "MATCH", "3125", sector="Sur"),
            _row("S-03", 2, "MATCH", "3110", sector="Sur"),
        ]

        assignment = assign_nominal_levels(rows)

        assert [(level.sector, level.label) for level in assignment.levels] == [
            ("Norte", "3125"),
            ("Sur", "3125"),
            ("Sur", "3110"),
        ]
        assert _by_label(assignment, "Norte")["3125"].n_rows == 2
        assert _by_label(assignment, "Norte")["3125"].n_sections == 2
        assert _by_label(assignment, "Sur")["3125"].n_rows == 1
        assert _by_label(assignment, "Sur")["3125"].n_sections == 1
        assert assignment.row_level[("Norte", "S-01", 1, "MATCH", "3125")] == "3125"
        assert assignment.row_level[("Sur", "S-03", 1, "MATCH", "3125")] == "3125"

    def test_each_sector_uses_its_own_height_design(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110", 15.0, sector="Norte"),
            _row("S-02", 1, "MATCH", "3104", 15.0, sector="Norte"),
            _row("S-03", 1, "MATCH", "3110", 30.0, sector="Sur"),
            _row("S-04", 1, "MATCH", "3104", 30.0, sector="Sur"),
        ]

        assignment = assign_nominal_levels(rows)

        assert len(_by_label(assignment, "Norte")) == 2
        assert len(_by_label(assignment, "Sur")) == 1

    def test_same_section_name_in_two_sectors_is_not_a_conflict(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110", sector="Norte"),
            _row("S-01", 1, "MATCH", "3110", sector="Sur"),
        ]

        assignment = assign_nominal_levels(rows)

        assert assignment.warnings == ()
        assert len(assignment.levels) == 2

    @pytest.mark.parametrize("sector", [None, "", "   "])
    def test_absent_sector_is_the_empty_string(self, sector):
        row = _row("S-01", 1, "MATCH", "3110", sector=sector)

        assignment = assign_nominal_levels([row])

        assert assignment.levels[0].sector == ""
        assert ("", "S-01", 1, "MATCH", "3110") in assignment.row_level

    def test_missing_sector_key_is_the_empty_string(self):
        row = _row("S-01", 1, "MATCH", "3110")
        del row["sector"]

        assignment = assign_nominal_levels([row])

        assert assignment.levels[0].sector == ""


class TestCountsOrderAndKeys:
    def test_levels_are_sorted_by_sector_then_descending_elevation(self):
        rows = [
            _row("S-01", 3, "MATCH", "3095", sector="B"),
            _row("S-01", 1, "MATCH", "3125", sector="B"),
            _row("S-01", 2, "MATCH", "3110", sector="B"),
            _row("S-02", 2, "MATCH", "3110", sector="A"),
            _row("S-02", 1, "MATCH", "3125", sector="A"),
        ]

        assignment = assign_nominal_levels(rows)

        assert [(level.sector, level.label) for level in assignment.levels] == [
            ("A", "3125"),
            ("A", "3110"),
            ("B", "3125"),
            ("B", "3110"),
            ("B", "3095"),
        ]

    def test_counts_rows_and_distinct_sections(self):
        rows = [
            _row("S-01", 1, "MATCH", "3125"),
            _row("S-01", 999, "EXTRA", "3122", None),
            _row("S-02", 1, "MATCH", "3124"),
            _row("S-03", 1, "MISSING", "3125"),
        ]

        level = assign_nominal_levels(rows).levels[0]

        assert (level.n_sections, level.n_rows) == (3, 4)
        assert (level.min_level, level.max_level) == (3122.0, 3125.0)

    def test_row_level_key_uses_int_bench_num(self):
        rows = [
            _row("S-01", "2", "MATCH", "3110"),
            _row("S-02", 3.0, "MISSING", "3110"),
        ]

        assignment = assign_nominal_levels(rows)

        assert set(assignment.row_level) == {
            ("", "S-01", 2, "MATCH", "3110"),
            ("", "S-02", 3, "MISSING", "3110"),
        }
        assert all(type(key[2]) is int for key in assignment.row_level)

    def test_row_without_integer_bench_num_is_excluded_with_warning(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-02", None, "MATCH", "3110"),
        ]

        assignment = assign_nominal_levels(rows)

        assert list(assignment.row_level) == [("", "S-01", 1, "MATCH", "3110")]
        assert assignment.levels[0].n_rows == 1
        assert any("S-02" in w for w in assignment.warnings)

    def test_rows_of_other_types_are_ignored(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110"),
            _row("S-01", 2, "SUMMARY", "3090"),
            _row("S-01", 3, None, "3080"),
        ]

        assignment = assign_nominal_levels(rows)

        assert [level.label for level in assignment.levels] == ["3110"]
        assert assignment.warnings == ()

    def test_empty_input(self):
        assignment = assign_nominal_levels([])

        assert assignment == NominalLevelAssignment(levels=(), row_level={}, warnings=())

    def test_accepts_a_one_shot_iterable(self):
        rows = [_row("S-01", 1, "MATCH", "3110"), _row("S-02", 1, "MATCH", "3110")]

        assignment = assign_nominal_levels(iter(rows))

        assert assignment.levels[0].n_rows == 2

    def test_two_extra_rows_of_one_section_at_different_levels_do_not_collide(self):
        rows = [
            _row("S-01", 999, "EXTRA", "3125", None),
            _row("S-01", 999, "EXTRA", "3095", None),
            _row("S-02", 1, "MATCH", "3110"),
        ]

        assignment = assign_nominal_levels(rows)

        assert [level.label for level in assignment.levels] == ["3125", "3110", "3095"]
        assert assignment.row_level[("", "S-01", 999, "EXTRA", "3125")] == "3125"
        assert assignment.row_level[("", "S-01", 999, "EXTRA", "3095")] == "3095"
        assert len(assignment.row_level) == 3
        assert assignment.warnings == ()

    def test_row_level_key_keeps_the_original_level_text(self):
        rows = [
            _row("S-01", 1, "MATCH", "3110.40"),
            _row("S-02", 1, "MATCH", " 3110 "),
            _row("S-03", 1, "MATCH", 3110.4),
            _row("S-04", 1, "MATCH", 3110),
        ]

        assignment = assign_nominal_levels(rows)

        assert assignment.row_level == {
            ("", "S-01", 1, "MATCH", "3110.40"): "3110",
            ("", "S-02", 1, "MATCH", " 3110 "): "3110",
            ("", "S-03", 1, "MATCH", "3110.4"): "3110",
            ("", "S-04", 1, "MATCH", "3110"): "3110",
        }
        assert all(type(key[4]) is str for key in assignment.row_level)

    def test_fully_duplicated_rows_share_one_key_without_warning(self):
        rows = [
            _row("S-01", 999, "EXTRA", "3125", None),
            _row("S-01", 999, "EXTRA", "3125", None),
            _row("S-02", 1, "MATCH", "3110"),
        ]

        assignment = assign_nominal_levels(rows)

        assert assignment.row_level[("", "S-01", 999, "EXTRA", "3125")] == "3125"
        assert len(assignment.row_level) == 2
        assert _by_label(assignment)["3125"].n_rows == 2
        assert not any("identificador" in w for w in assignment.warnings)


class TestPurity:
    def test_input_rows_are_not_mutated(self):
        rows = _real_session_rows()
        rows.append(_row("S-97", 1, "MATCH", "abc"))
        snapshot = copy.deepcopy(rows)

        assign_nominal_levels(rows)

        assert rows == snapshot

    def test_repeated_calls_give_equal_results(self):
        rows = _real_session_rows()

        assert assign_nominal_levels(rows) == assign_nominal_levels(rows)

    def test_result_dataclasses_are_frozen(self):
        assignment = assign_nominal_levels([_row("S-01", 1, "MATCH", "3110")])

        with pytest.raises(dataclasses.FrozenInstanceError):
            assignment.levels[0].label = "x"
        with pytest.raises(dataclasses.FrozenInstanceError):
            assignment.warnings = ()
