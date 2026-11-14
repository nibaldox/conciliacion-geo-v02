"""Report model aggregates of core.report_data (contract C5, decisions D3/D5/D9/D11/D12)."""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from core import SectionLine
from core.design_achievement import build_design_achievement_summary
from core.report_data import (
    BenchRow,
    ParameterSummary,
    ReportData,
    ReportFilters,
    build_report_data,
)
from core.report_volumes import SectionExcavation

PROFILE_STATUSES = ("CUMPLE", "FUERA", "NO_CUMPLE", "UNKNOWN")
EXCAVATION_TOTAL_KEYS = {
    "area_over_m2", "area_under_m2", "volume_over_m3", "volume_under_m3",
    "n_sections", "n_without_volume",
}
MATRIX_KEYS = {
    "section", "sector", "level_nominal", "bench_num", "type", "worst_status",
    "height_status", "angle_status", "berm_status", "design_below_min",
}
SECTOR_SUMMARY_KEYS = {
    "sector", "levels", "profile_counts", "headline", "global_weighted_score",
    "parameters", "design_achievement", "excavation_totals",
}


def _statuses(status):
    return {"height_status": status, "angle_status": status, "berm_status": status}


def _match(section, bench_num, level, sector="A", ok=True, **extra):
    row = {
        "sector": sector,
        "section": section,
        "bench_num": bench_num,
        "type": "MATCH",
        "level": level,
        "height_design": 15.0,
        "bench_score": 100.0 if ok else 20.0,
        **_statuses("CUMPLE" if ok else "NO CUMPLE"),
    }
    row.update(extra)
    return row


def _missing(section, bench_num, level, sector="A", **extra):
    row = {
        "sector": sector,
        "section": section,
        "bench_num": bench_num,
        "type": "MISSING",
        "level": level,
        "height_design": 15.0,
        "height_status": "NO CONSTRUIDO",
        "angle_status": "-",
        "berm_status": "FALTA BANCO",
    }
    row.update(extra)
    return row


def _extra(section, level, sector="A", **extra):
    row = {
        "sector": sector,
        "section": section,
        "bench_num": 999,
        "type": "EXTRA",
        "level": level,
        "height_design": None,
        "height_status": "BANCO ADICIONAL",
        "angle_status": "BANCO ADICIONAL",
        "berm_status": None,
    }
    row.update(extra)
    return row


def _headline_rows():
    return [
        _match("S-01", 1, "3125"),
        _missing("S-01", 2, "3110"),
        _match("S-02", 1, "3125", ok=False),
        _match("S-02", 2, "3110"),
        _match("S-03", 1, "3125"),
        _extra("S-04", "3123"),
        {"sector": "A", "section": "S-05", "bench_num": 1, "type": "MATCH",
         "level": "3125", "height_design": 15.0},
    ]


def _build(rows, filters=None, settings=None, **kwargs):
    return build_report_data(rows, settings or {}, filters or ReportFilters(), {}, **kwargs)


def _flat(z, start=0.0, end=20.0):
    return (np.array([start, end]), np.array([z, z]))


def _geometry(section, sector, design, topo, view_window="absent"):
    entry = {
        "section_name": section,
        "params_design": None,
        "params_topo": None,
        "profile_d": design,
        "profile_t": topo,
        "sector": sector,
    }
    if view_window != "absent":
        entry["view_window"] = view_window
    return entry


def _plan(*sections):
    return {"sections": [
        {"name": name, "sector": sector, "origin": [x, 0.0]} for name, sector, x in sections
    ]}


class TestAdditiveContract:
    def test_new_report_data_fields_have_defaults(self):
        defaults = {f.name: f for f in dataclasses.fields(ReportData)}
        for name in ("headline", "matrix", "deviations", "trend", "excavation",
                     "excavation_totals", "sector_summaries"):
            field = defaults[name]
            assert (
                field.default is not dataclasses.MISSING
                or field.default_factory is not dataclasses.MISSING
            ), name

    def test_bench_row_and_parameter_summary_new_fields_have_defaults(self):
        bench = {f.name: f.default for f in dataclasses.fields(BenchRow)}
        assert bench["level_nominal"] is None
        assert bench["design_below_min"] is False
        parameter = {f.name: f.default for f in dataclasses.fields(ParameterSummary)}
        assert parameter["n_evaluated"] == 0
        assert parameter["n_not_compared"] == 0

    def test_empty_input_gives_empty_aggregates_and_none_totals(self):
        data = _build([])
        assert data.headline == {
            "profiles": {status: 0 for status in PROFILE_STATUSES},
            "nc_by_geometry": 0,
            "nc_only_missing_extra": 0,
            "benches": {
                "match_by_status": {status: 0 for status in PROFILE_STATUSES},
                "missing": 0,
                "extra": 0,
            },
        }
        assert data.matrix == ()
        assert data.deviations == {"height": (), "angle": (), "berm": ()}
        assert data.trend == ()
        assert data.excavation == ()
        assert data.excavation_totals == {
            "area_over_m2": None, "area_under_m2": None,
            "volume_over_m3": None, "volume_under_m3": None,
            "n_sections": 0, "n_without_volume": 0,
        }
        assert data.sector_summaries == ()


class TestHeadline:
    def test_profiles_split_by_geometry_and_by_missing_or_extra_only(self):
        data = _build(_headline_rows())

        assert {p.section: p.worst_status for p in data.profiles} == {
            "S-01": "NO_CUMPLE", "S-02": "NO_CUMPLE", "S-03": "CUMPLE",
            "S-04": "NO_CUMPLE", "S-05": "UNKNOWN",
        }
        assert data.headline["profiles"] == {
            "CUMPLE": 1, "FUERA": 0, "NO_CUMPLE": 3, "UNKNOWN": 1,
        }
        assert data.headline["nc_by_geometry"] == 1
        assert data.headline["nc_only_missing_extra"] == 2
        assert (
            data.headline["nc_by_geometry"] + data.headline["nc_only_missing_extra"]
            == data.headline["profiles"]["NO_CUMPLE"]
        )

    def test_bench_counts_split_match_statuses_from_missing_and_extra(self):
        data = _build(_headline_rows())

        assert data.headline["benches"] == {
            "match_by_status": {"CUMPLE": 3, "FUERA": 0, "NO_CUMPLE": 1, "UNKNOWN": 1},
            "missing": 1,
            "extra": 1,
        }

    def test_headline_does_not_change_existing_profile_counts(self):
        data = _build(_headline_rows())
        assert data.profile_counts == {"CUMPLE": 1, "FUERA": 0, "NO_CUMPLE": 3}

    def test_unknown_match_row_with_missing_bench_counts_as_geometry(self):
        rows = [
            {"sector": "A", "section": "S-01", "bench_num": 1, "type": "MATCH",
             "level": "3125", "height_design": 15.0},
            _missing("S-01", 2, "3110"),
        ]
        data = _build(rows)
        assert data.headline["nc_by_geometry"] == 1
        assert data.headline["nc_only_missing_extra"] == 0


class TestMatrix:
    def test_rows_follow_plan_section_order_and_carry_nominal_level(self):
        plan = _plan(("S-03", "A", 0.0), ("S-01", "A", 10.0), ("S-02", "A", 20.0))
        data = _build(_headline_rows(), plan_inputs=plan)

        assert all(set(entry) == MATRIX_KEYS for entry in data.matrix)
        assert [
            (e["section"], e["bench_num"], e["type"], e["level_nominal"]) for e in data.matrix
        ] == [
            ("S-03", 1, "MATCH", "3125"),
            ("S-01", 1, "MATCH", "3125"),
            ("S-01", 2, "MISSING", "3110"),
            ("S-02", 1, "MATCH", "3125"),
            ("S-02", 2, "MATCH", "3110"),
            ("S-04", 999, "EXTRA", "3125"),
            ("S-05", 1, "MATCH", "3125"),
        ]

    def test_matrix_carries_the_official_statuses_of_each_row(self):
        data = _build(_headline_rows())
        by_key = {(e["section"], e["bench_num"]): e for e in data.matrix}

        assert by_key[("S-02", 1)]["worst_status"] == "NO_CUMPLE"
        assert by_key[("S-02", 1)]["berm_status"] == "NO CUMPLE"
        assert by_key[("S-01", 2)]["worst_status"] == "NO_CUMPLE"
        assert by_key[("S-01", 2)]["height_status"] == "NO CONSTRUIDO"
        assert by_key[("S-01", 2)]["angle_status"] == "-"
        assert by_key[("S-04", 999)]["berm_status"] is None
        assert by_key[("S-05", 1)]["worst_status"] == "UNKNOWN"
        assert by_key[("S-01", 1)]["sector"] == "A"
        assert [e["worst_status"] for e in data.matrix] == [r.worst_status for r in data.rows]

    def test_without_plan_inputs_order_is_row_appearance(self):
        rows = [_match("S-09", 1, "3125"), _match("S-02", 1, "3125"), _match("S-09", 2, "3110")]
        data = _build(rows)
        assert [(e["section"], e["bench_num"]) for e in data.matrix] == [
            ("S-09", 1), ("S-09", 2), ("S-02", 1),
        ]

    def test_plan_sections_may_be_section_line_objects(self):
        plan = {"sections": [
            SectionLine(name="S-02", origin=np.array([0.0, 0.0]), azimuth=0.0, length=100.0, sector="A"),
            SectionLine(name="S-01", origin=np.array([10.0, 0.0]), azimuth=0.0, length=100.0, sector="A"),
        ]}
        rows = [_match("S-01", 1, "3125"), _match("S-02", 1, "3125")]
        data = _build(rows, plan_inputs=plan)
        assert [e["section"] for e in data.matrix] == ["S-02", "S-01"]
        assert [e["section"] for e in data.trend] == ["S-02", "S-01"]

    def test_bench_rows_carry_level_nominal(self):
        data = _build(_headline_rows())
        assert [r.level_nominal for r in data.rows] == [
            "3125", "3110", "3125", "3110", "3125", "3125", "3125",
        ]
        without_level = _build([{"section": "S", "type": "MATCH", "bench_num": 1}])
        assert without_level.rows[0].level_nominal is None
        assert without_level.matrix[0]["level_nominal"] is None


class TestDeviations:
    def test_only_match_rows_with_finite_values_contribute(self):
        rows = [
            _match("S-01", 1, "3125", height_real=14.0, angle_design=70.0, angle_real=73.0,
                   berm_design=8.0, berm_real=6.5),
            _match("S-01", 2, "3110", height_real=17.0, angle_design=70.0, angle_real=None,
                   berm_design=8.0, berm_real=float("nan")),
            _match("S-02", 1, "3125", height_real=float("inf"), angle_design=None,
                   angle_real=65.0, berm_design="x", berm_real=7.0),
            _missing("S-02", 2, "3110", height_real=None, angle_design=70.0, berm_design=8.0),
            _extra("S-03", "3123", height_design=15.0, height_real=6.0, angle_design=70.0,
                   angle_real=60.0, berm_design=8.0, berm_real=2.0),
        ]
        data = _build(rows)

        assert set(data.deviations) == {"height", "angle", "berm"}
        assert data.deviations["height"] == pytest.approx((-1.0, 2.0))
        assert data.deviations["angle"] == pytest.approx((3.0,))
        assert data.deviations["berm"] == pytest.approx((-1.5,))
        assert all(isinstance(values, tuple) for values in data.deviations.values())


class TestTrend:
    def test_mean_deviation_per_section_and_none_without_values(self):
        plan = _plan(("S-02", "A", 0.0), ("S-01", "A", 10.0), ("S-03", "A", 20.0))
        rows = [
            _match("S-01", 1, "3125", height_real=14.0, angle_design=70.0, angle_real=73.0),
            _match("S-01", 2, "3110", height_real=17.0, angle_design=70.0, angle_real=None),
            _match("S-02", 1, "3125", height_design=None, height_real=12.0),
            _extra("S-03", "3123", height_design=15.0, height_real=6.0,
                   angle_design=70.0, angle_real=60.0),
        ]
        data = _build(rows, plan_inputs=plan)

        assert [entry["section"] for entry in data.trend] == ["S-02", "S-01", "S-03"]
        assert all(
            set(entry) == {"section", "sector", "height_dev_mean", "angle_dev_mean", "n"}
            for entry in data.trend
        )
        s02, s01, s03 = data.trend
        assert s01["sector"] == "A"
        assert s01["height_dev_mean"] == pytest.approx(0.5)
        assert s01["angle_dev_mean"] == pytest.approx(3.0)
        assert s01["n"] == 2
        assert s02["height_dev_mean"] is None
        assert s02["angle_dev_mean"] is None
        assert s02["n"] == 1
        assert s03["height_dev_mean"] is None
        assert s03["angle_dev_mean"] is None
        assert s03["n"] == 0


class TestExcavation:
    def _rows(self):
        return [_match("S-01", 1, "3125"), _match("S-02", 1, "3125"), _match("S-03", 1, "3125")]

    def _plan(self):
        return _plan(("S-01", "A", 0.0), ("S-02", "A", 10.0), ("S-03", "A", 20.0))

    def test_areas_and_volumes_with_ten_metre_spacing(self):
        geometry = [
            _geometry("S-01", "A", _flat(100.0), _flat(98.0)),
            _geometry("S-02", "A", _flat(100.0), _flat(101.0)),
            _geometry("S-03", "A", _flat(100.0), _flat(99.0), view_window=None),
        ]
        data = _build(self._rows(), section_geometry=geometry, plan_inputs=self._plan())

        assert all(isinstance(entry, SectionExcavation) for entry in data.excavation)
        assert [(e.section, e.sector) for e in data.excavation] == [
            ("S-01", "A"), ("S-02", "A"), ("S-03", "A"),
        ]
        first, second, third = data.excavation
        assert first.area_over_m2 == pytest.approx(40.0)
        assert first.area_under_m2 == pytest.approx(0.0)
        assert first.influence_width_m == pytest.approx(10.0)
        assert first.volume_over_m3 == pytest.approx(400.0)
        assert first.volume_under_m3 == pytest.approx(0.0)
        assert first.window is None
        assert second.area_over_m2 == pytest.approx(0.0)
        assert second.area_under_m2 == pytest.approx(20.0)
        assert second.volume_under_m3 == pytest.approx(200.0)
        assert third.area_over_m2 == pytest.approx(20.0)
        assert third.volume_over_m3 == pytest.approx(200.0)

        assert set(data.excavation_totals) == EXCAVATION_TOTAL_KEYS
        assert data.excavation_totals["area_over_m2"] == pytest.approx(60.0)
        assert data.excavation_totals["area_under_m2"] == pytest.approx(20.0)
        assert data.excavation_totals["volume_over_m3"] == pytest.approx(600.0)
        assert data.excavation_totals["volume_under_m3"] == pytest.approx(200.0)
        assert data.excavation_totals["n_sections"] == 3
        assert data.excavation_totals["n_without_volume"] == 0

    def test_view_window_restricts_the_area(self):
        geometry = [
            _geometry("S-01", "A", _flat(100.0), _flat(98.0),
                      view_window=(0.0, 10.0, 90.0, 110.0)),
        ]
        data = _build(self._rows(), section_geometry=geometry, plan_inputs=self._plan())

        assert data.excavation[0].window == (0.0, 10.0, 90.0, 110.0)
        assert data.excavation[0].area_over_m2 == pytest.approx(20.0)
        assert data.excavation[0].volume_over_m3 == pytest.approx(200.0)

    def test_totals_skip_none_and_count_sections_without_volume(self):
        empty = (np.array([]), np.array([]))
        geometry = [
            _geometry("S-01", "A", _flat(100.0), _flat(98.0)),
            _geometry("S-02", "A", empty, empty),
            _geometry("S-03", "A", _flat(100.0), _flat(101.0)),
        ]
        data = _build(self._rows(), section_geometry=geometry, plan_inputs=self._plan())

        assert data.excavation[1].area_over_m2 is None
        assert data.excavation[1].volume_over_m3 is None
        assert data.excavation_totals["area_over_m2"] == pytest.approx(40.0)
        assert data.excavation_totals["area_under_m2"] == pytest.approx(20.0)
        assert data.excavation_totals["volume_over_m3"] == pytest.approx(400.0)
        assert data.excavation_totals["volume_under_m3"] == pytest.approx(200.0)
        assert data.excavation_totals["n_sections"] == 3
        assert data.excavation_totals["n_without_volume"] == 1

    def test_without_plan_sections_areas_are_kept_and_volumes_are_none(self):
        geometry = [_geometry("S-01", "A", _flat(100.0), _flat(98.0))]
        data = _build(self._rows(), section_geometry=geometry)

        assert data.excavation[0].area_over_m2 == pytest.approx(40.0)
        assert data.excavation[0].influence_width_m is None
        assert data.excavation[0].volume_over_m3 is None
        assert data.excavation_totals["area_over_m2"] == pytest.approx(40.0)
        assert data.excavation_totals["volume_over_m3"] is None
        assert data.excavation_totals["volume_under_m3"] is None
        assert data.excavation_totals["n_without_volume"] == 1

    def test_only_sections_of_the_filtered_rows_are_measured(self):
        geometry = [
            _geometry("S-01", "A", _flat(100.0), _flat(98.0)),
            _geometry("S-02", "A", _flat(100.0), _flat(98.0)),
            _geometry("S-99", "A", _flat(100.0), _flat(98.0)),
        ]
        data = _build(
            self._rows(), ReportFilters(sections=("S-02",)),
            section_geometry=geometry, plan_inputs=self._plan(),
        )

        assert [e.section for e in data.excavation] == ["S-02"]
        assert data.excavation[0].influence_width_m == pytest.approx(10.0)
        assert data.excavation_totals["n_sections"] == 1

    def test_sector_falls_back_to_params_design_and_section_line_plan(self):
        from types import SimpleNamespace

        entry = _geometry("S-01", "A", _flat(100.0), _flat(98.0))
        del entry["sector"]
        entry["params_design"] = SimpleNamespace(sector="A")
        plan = {"sections": [
            SectionLine(name="S-01", origin=np.array([0.0, 0.0]), azimuth=0.0, length=100.0, sector="A"),
            SectionLine(name="S-02", origin=np.array([0.0, 10.0]), azimuth=0.0, length=100.0, sector="A"),
        ]}
        data = _build(self._rows(), section_geometry=[entry], plan_inputs=plan)

        assert data.excavation[0].sector == "A"
        assert data.excavation[0].influence_width_m == pytest.approx(10.0)
        assert data.excavation[0].volume_over_m3 == pytest.approx(400.0)


class TestParameterDenominator:
    def _rows(self):
        return [
            _match("S-01", 1, "3125", height_real=15.0),
            _match("S-01", 2, "3110", height_real=14.0),
            _match("S-02", 1, "3125", height_status="FUERA DE TOLERANCIA",
                   angle_status="-", berm_status=None, height_real=12.0),
            _missing("S-02", 2, "3110"),
            _extra("S-03", "3123", height_real=6.0),
        ]

    def test_percentage_is_computed_over_match_rows_only(self):
        data = _build(self._rows())
        by_parameter = {p.parameter: p for p in data.parameters}

        height = by_parameter["height"]
        assert (height.cumple, height.no_cumple) == (2, 1)
        assert height.n_evaluated == 3
        assert height.n_not_compared == 2
        assert height.pct_cumple == pytest.approx(100.0 * 2 / 3)

        angle = by_parameter["angle"]
        assert (angle.cumple, angle.no_cumple) == (2, 0)
        assert angle.n_evaluated == 2
        assert angle.n_not_compared == 2
        assert angle.pct_cumple == pytest.approx(100.0)

        berm = by_parameter["berm"]
        assert berm.n_evaluated == 2
        assert berm.n_not_compared == 2
        assert berm.pct_cumple == pytest.approx(100.0)

    def test_without_match_rows_percentage_is_none(self):
        data = _build([_missing("S-01", 1, "3125"), _extra("S-01", "3110")])

        for parameter in data.parameters:
            assert parameter.pct_cumple is None
            assert parameter.n_evaluated == 0
            assert parameter.n_not_compared == 2
            assert (parameter.cumple, parameter.no_cumple) == (0, 0)


class TestDesignBelowMin:
    def test_flag_requires_finite_design_below_finite_minimum(self):
        rows = [
            _match("S-01", 1, "3125", berm_design=6.0, berm_min=7.0, berm_real=6.1),
            _match("S-02", 1, "3125", berm_design=8.0, berm_min=7.0),
            _match("S-03", 1, "3125", berm_design=7.0, berm_min=7.0),
            _match("S-04", 1, "3125", berm_design=6.0, berm_min=None),
            _match("S-05", 1, "3125", berm_design=float("nan"), berm_min=7.0),
            _match("S-06", 1, "3125", berm_min=7.0),
        ]
        data = _build(rows)

        assert [r.design_below_min for r in data.rows] == [True, False, False, False, False, False]
        assert [e["design_below_min"] for e in data.matrix] == [
            True, False, False, False, False, False,
        ]

    def test_flag_never_changes_a_status(self):
        base = _match("S-01", 1, "3125", berm_design=6.0, berm_real=6.1)
        flagged = _build([dict(base, berm_min=7.0)])
        plain = _build([dict(base, berm_min=5.0)])

        assert flagged.rows[0].design_below_min is True
        assert plain.rows[0].design_below_min is False
        assert flagged.rows[0].worst_status == plain.rows[0].worst_status == "CUMPLE"
        assert flagged.rows[0].berm_status == plain.rows[0].berm_status == "CUMPLE"
        assert flagged.profile_counts == plain.profile_counts
        assert flagged.headline == plain.headline
        assert flagged.parameters == plain.parameters


class TestSectorSummaries:
    def _rows(self):
        rows = []
        for index in (1, 2):
            rows.append(_match(f"N-{index:02d}", 1, "3125", sector="Norte", ok=False,
                               height_real=11.0))
            rows.append(_match(f"N-{index:02d}", 2, "3110", sector="Norte", height_real=15.0))
        for index in (1, 2, 3):
            rows.append(_match(f"S-{index:02d}", 1, "3095", sector="Sur", height_real=15.0,
                               bench_score=80.0))
            rows.append(_missing(f"S-{index:02d}", 2, "3080", sector="Sur"))
        return rows

    def _plan(self):
        return _plan(
            ("N-01", "Norte", 0.0), ("N-02", "Norte", 10.0),
            ("S-01", "Sur", 100.0), ("S-02", "Sur", 120.0), ("S-03", "Sur", 140.0),
        )

    def _geometry(self):
        return [
            _geometry("N-01", "Norte", _flat(100.0), _flat(98.0)),
            _geometry("N-02", "Norte", _flat(100.0), _flat(99.0)),
            _geometry("S-01", "Sur", _flat(100.0), _flat(101.0)),
        ]

    def test_two_sectors_with_their_own_level_selection(self):
        filters = ReportFilters(
            levels=("3125",),
            levels_by_sector=(("Norte", ("3110",)), ("Sur", ("3080", "3095"))),
        )
        settings = {"tolerances": {"crest_toe_deviation": {"neg": 1.0, "pos": 1.0}}}
        data = _build(
            self._rows(), filters, settings,
            section_geometry=self._geometry(), plan_inputs=self._plan(),
        )

        assert [s["sector"] for s in data.sector_summaries] == ["Norte", "Sur"]
        assert all(set(s) == SECTOR_SUMMARY_KEYS for s in data.sector_summaries)
        norte, sur = data.sector_summaries

        assert norte["levels"] == ("3110",)
        assert norte["profile_counts"] == {"CUMPLE": 2, "FUERA": 0, "NO_CUMPLE": 0}
        assert norte["headline"]["profiles"] == {
            "CUMPLE": 2, "FUERA": 0, "NO_CUMPLE": 0, "UNKNOWN": 0,
        }
        assert norte["headline"]["benches"]["missing"] == 0
        assert norte["global_weighted_score"] == pytest.approx(100.0)
        assert [p.parameter for p in norte["parameters"]] == ["height", "angle", "berm"]
        assert norte["parameters"][0].n_evaluated == 2
        assert norte["parameters"][0].n_not_compared == 0
        assert norte["parameters"][0].pct_cumple == pytest.approx(100.0)
        assert norte["excavation_totals"]["n_sections"] == 2
        assert norte["excavation_totals"]["area_over_m2"] == pytest.approx(60.0)
        assert norte["excavation_totals"]["volume_over_m3"] == pytest.approx(600.0)

        assert sur["levels"] == ("3080", "3095")
        assert sur["profile_counts"] == {"CUMPLE": 0, "FUERA": 0, "NO_CUMPLE": 3}
        assert sur["headline"]["nc_by_geometry"] == 0
        assert sur["headline"]["nc_only_missing_extra"] == 3
        assert sur["headline"]["benches"]["missing"] == 3
        assert sur["global_weighted_score"] == pytest.approx(80.0)
        assert sur["parameters"][0].n_evaluated == 3
        assert sur["parameters"][0].n_not_compared == 3
        assert sur["excavation_totals"]["n_sections"] == 1
        assert sur["excavation_totals"]["area_under_m2"] == pytest.approx(20.0)
        assert sur["excavation_totals"]["volume_under_m3"] == pytest.approx(400.0)

        assert data.excavation_totals["n_sections"] == 3
        assert data.headline["profiles"]["CUMPLE"] == 2
        assert data.headline["profiles"]["NO_CUMPLE"] == 3

    def test_sector_design_achievement_uses_the_sector_rows(self):
        ct_tol = {"neg": 1.0, "pos": 1.0}
        data = _build(self._rows(), settings={"tolerances": {"crest_toe_deviation": ct_tol}})
        norte = data.sector_summaries[0]

        expected_rows = [dict(row) for row in self._rows() if row["sector"] == "Norte"]
        expected = build_design_achievement_summary(expected_rows, ct_tol)
        assert norte["design_achievement"] == expected
        assert norte["levels"] == ()

    def test_sector_without_own_entry_uses_the_global_levels(self):
        filters = ReportFilters(levels=("3125",), levels_by_sector=(("Sur", ()),))
        data = _build(self._rows(), filters)
        by_sector = {s["sector"]: s for s in data.sector_summaries}

        assert by_sector["Norte"]["levels"] == ("3125",)
        assert by_sector["Sur"]["levels"] == ()
        assert by_sector["Norte"]["profile_counts"]["NO_CUMPLE"] == 2

    def test_single_sector_gives_one_entry_equal_to_the_global_figures(self):
        data = _build(_headline_rows())

        assert len(data.sector_summaries) == 1
        only = data.sector_summaries[0]
        assert only["sector"] == "A"
        assert only["levels"] == ()
        assert only["profile_counts"] == data.profile_counts
        assert only["headline"] == data.headline
        assert only["global_weighted_score"] == pytest.approx(data.global_weighted_score)
        assert only["parameters"] == data.parameters
        assert only["excavation_totals"] == data.excavation_totals

    def test_missing_sector_is_summarised_as_empty_string(self):
        rows = [
            {"section": "S-01", "type": "MATCH", "bench_num": 1, "level": "3125",
             "height_design": 15.0, "sector": None},
        ]
        data = _build(rows)
        assert [s["sector"] for s in data.sector_summaries] == [""]


BENCH_3_DISTRIBUTION = (
    [3104] * 71
    + [3095] * 16
    + [3096] * 2
    + [3099] * 2
    + [3097, 3098, 3101, 3102, 3103]
)
EXTRA_LEVELS = {"S-22": 3120, "S-25": 3122}


def _real_session_rows():
    rows = []
    for index, bench_3_level in enumerate(BENCH_3_DISTRIBUTION, start=1):
        section = f"S-{index:02d}"
        rows.append(_match(section, 1, "3125", sector="", ok=False, height_real=11.0,
                           angle_design=70.0, angle_real=60.0, berm_design=8.0, berm_real=4.0))
        if section in EXTRA_LEVELS:
            rows.append(_extra(section, str(EXTRA_LEVELS[section]), sector=""))
        rows.append(_match(section, 2, "3110", sector="", height_real=15.5,
                           angle_design=70.0, angle_real=71.0, berm_design=8.0, berm_real=8.5))
        rows.append(_missing(section, 3, str(bench_3_level), sector="", height_design=5.88))
    return rows


@pytest.fixture(scope="module")
def real_session_data():
    rows = _real_session_rows()
    sections = [f"S-{index:02d}" for index in range(1, 97)]
    plan = _plan(*[(name, "", 10.0 * index) for index, name in enumerate(sections)])
    geometry = [
        _geometry("S-01", "", _flat(100.0), _flat(98.0)),
        _geometry("S-02", "", _flat(100.0), _flat(98.0)),
        _geometry("S-999", "", _flat(100.0), _flat(98.0)),
    ]
    return build_report_data(
        rows, {}, ReportFilters(levels=("3110",)), {},
        section_geometry=geometry, plan_inputs=plan,
    )


class TestRealSessionLikeLevelFilter:
    @pytest.fixture()
    def data(self, real_session_data):
        return real_session_data

    def test_rows_and_matrix_hold_only_bench_2(self, data):
        assert len(data.rows) == 96
        assert {r.bench_num for r in data.rows} == {2}
        assert {r.level_nominal for r in data.rows} == {"3110"}
        assert len(data.matrix) == 96
        assert {e["bench_num"] for e in data.matrix} == {2}
        assert {e["type"] for e in data.matrix} == {"MATCH"}
        assert {e["level_nominal"] for e in data.matrix} == {"3110"}
        assert [e["section"] for e in data.matrix] == [f"S-{i:02d}" for i in range(1, 97)]

    def test_headline_and_parameters_ignore_the_other_benches(self, data):
        assert data.headline["profiles"] == {
            "CUMPLE": 96, "FUERA": 0, "NO_CUMPLE": 0, "UNKNOWN": 0,
        }
        assert data.headline["nc_by_geometry"] == 0
        assert data.headline["nc_only_missing_extra"] == 0
        assert data.headline["benches"] == {
            "match_by_status": {"CUMPLE": 96, "FUERA": 0, "NO_CUMPLE": 0, "UNKNOWN": 0},
            "missing": 0,
            "extra": 0,
        }
        for parameter in data.parameters:
            assert parameter.n_evaluated == 96
            assert parameter.n_not_compared == 0
            assert parameter.pct_cumple == pytest.approx(100.0)

    def test_deviations_and_trend_hold_only_bench_2(self, data):
        assert data.deviations["height"] == pytest.approx((0.5,) * 96)
        assert data.deviations["angle"] == pytest.approx((1.0,) * 96)
        assert data.deviations["berm"] == pytest.approx((0.5,) * 96)
        assert len(data.trend) == 96
        assert {entry["n"] for entry in data.trend} == {1}
        assert all(entry["height_dev_mean"] == pytest.approx(0.5) for entry in data.trend)

    def test_excavation_and_sector_summary_follow_the_filter(self, data):
        assert [e.section for e in data.excavation] == ["S-01", "S-02"]
        assert all(e.influence_width_m == pytest.approx(10.0) for e in data.excavation)
        assert data.excavation_totals["volume_over_m3"] == pytest.approx(800.0)
        assert len(data.sector_summaries) == 1
        summary = data.sector_summaries[0]
        assert summary["sector"] == ""
        assert summary["levels"] == ("3110",)
        assert summary["headline"] == data.headline
        assert summary["profile_counts"] == {"CUMPLE": 96, "FUERA": 0, "NO_CUMPLE": 0}
