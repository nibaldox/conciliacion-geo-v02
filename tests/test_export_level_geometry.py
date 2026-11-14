"""Export API: per-sector nominal level filters, cropped geometry and levels endpoint."""

import io
import json
from typing import Any, Dict, List, Optional

import openpyxl
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.database as db
import api.routers.export as export_router
from api.main import app

NORTE_BENCH3_TOES = {"S-01": 3095.0, "S-02": 3098.0, "S-03": 3101.0, "S-04": 3104.0}
NORTE_EXTRA_TOES = {"S-02": 3122.0, "S-03": 3120.0}
TOLERANCES = {
    "bench_height": {"neg": 1.0, "pos": 1.5},
    "face_angle": {"neg": 5.0, "pos": 5.0},
    "berm_width": {"min": 6.0},
    "inter_ramp_angle": {"neg": 3.0, "pos": 2.0},
    "overall_angle": {"neg": 2.0, "pos": 2.0},
}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def session_id():
    return db.create_session()


@pytest.fixture()
def headers(session_id):
    return {"x-session-id": session_id}


def _bench(
    number: int,
    crest_z: float,
    toe_z: float,
    crest_d: float,
    toe_d: float,
    height: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "bench_number": number,
        "crest_elevation": crest_z,
        "crest_distance": crest_d,
        "toe_elevation": toe_z,
        "toe_distance": toe_d,
        "bench_height": crest_z - toe_z if height is None else height,
        "face_angle": 70.0,
        "berm_width": 9.0,
        "is_ramp": False,
        "spill_width": 0.0,
        "spill_start_distance": 0.0,
        "spill_start_elevation": 0.0,
        "effective_berm_width": 9.0,
    }


def _row(
    section: str,
    sector: str,
    bench: int,
    bench_topo: Optional[int],
    level: float,
    row_type: str = "MATCH",
) -> Dict[str, Any]:
    is_match = row_type == "MATCH"
    has_design = row_type != "EXTRA"
    return {
        "section": section,
        "sector": sector,
        "bench_num": bench,
        "bench_num_topo": bench_topo,
        "type": row_type,
        "level": f"{level:.0f}",
        "height_design": 15.0 if has_design else None,
        "height_real": 15.0 if row_type != "MISSING" else None,
        "height_dev": 0.0 if is_match else None,
        "height_status": "CUMPLE" if is_match else "NO CUMPLE",
        "angle_design": 70.0 if has_design else None,
        "angle_real": 70.0 if row_type != "MISSING" else None,
        "angle_dev": 0.0 if is_match else None,
        "angle_status": "CUMPLE" if is_match else "-",
        "berm_design": 9.0 if has_design else None,
        "berm_real": 9.0 if row_type != "MISSING" else None,
        "berm_dev": 0.0 if is_match else None,
        "berm_min": 6.0,
        "berm_status": "CUMPLE" if is_match else "NO CUMPLE",
        "spill_width": 0.0,
        "effective_berm": 9.0 if is_match else None,
        "delta_crest": 0.1 if is_match else None,
        "delta_toe": 0.2 if is_match else None,
        "berm_score": 60 if is_match else 0,
        "angle_score": 10 if is_match else 0,
        "height_score": 30 if is_match else 0,
        "bench_score": 100 if is_match else 0,
        "section_score": 100.0,
    }


def _norte_design(section: str) -> List[Dict[str, Any]]:
    return [
        _bench(1, 3140.0, 3125.0, 10.0, 15.0),
        _bench(2, 3125.0, 3110.0, 25.0, 30.0),
        _bench(3, 3110.0, NORTE_BENCH3_TOES[section], 40.0, 45.0),
    ]


def _norte_topo(section: str) -> List[Dict[str, Any]]:
    toe3 = NORTE_BENCH3_TOES[section]
    if section in NORTE_EXTRA_TOES:
        return [
            _bench(1, 3140.0, 3125.0, 11.0, 16.0),
            _bench(2, 3125.0, NORTE_EXTRA_TOES[section], 18.0, 19.0),
            _bench(3, 3125.0, 3110.0, 26.0, 31.0),
            _bench(4, 3110.0, toe3, 41.0, 46.0),
        ]
    return [
        _bench(1, 3140.0, 3125.0, 11.0, 16.0),
        _bench(2, 3125.0, 3110.0, 26.0, 31.0),
        _bench(3, 3110.0, toe3, 41.0, 46.0),
    ]


def _norte_rows(section: str) -> List[Dict[str, Any]]:
    toe3 = NORTE_BENCH3_TOES[section]
    if section in NORTE_EXTRA_TOES:
        return [
            _row(section, "Norte", 1, 1, 3125.0),
            _row(section, "Norte", 2, 3, 3110.0),
            _row(section, "Norte", 3, 4, toe3),
            _row(section, "Norte", 999, 2, NORTE_EXTRA_TOES[section], "EXTRA"),
        ]
    return [
        _row(section, "Norte", 1, 1, 3125.0),
        _row(section, "Norte", 2, 2, 3110.0),
        _row(section, "Norte", 3, 3, toe3),
    ]


def _seed(
    session_id: str,
    height_override: Optional[float] = None,
    sur_unmatched_bench: bool = False,
) -> List[Dict[str, Any]]:
    sections = [
        {
            "name": name,
            "origin": [100.0 + 10.0 * index, 200.0],
            "azimuth": 0.0,
            "length": 100.0,
            "sector": "Norte",
        }
        for index, name in enumerate(NORTE_BENCH3_TOES)
    ]
    sections.append(
        {"name": "S-05", "origin": [200.0, 200.0], "azimuth": 0.0, "length": 100.0, "sector": "Sur"}
    )
    db.save_sections(session_id, sections)
    db.save_settings(session_id, {"tolerances": TOLERANCES})

    rows: List[Dict[str, Any]] = []
    for name in NORTE_BENCH3_TOES:
        rows.extend(_norte_rows(name))
        design = _norte_design(name)
        if height_override is not None:
            for bench in design:
                bench["bench_height"] = height_override
        db.save_extraction(session_id, name, "design", {
            "section_name": name, "sector": "Norte", "benches": design,
            "inter_ramp_angle": 48.0, "overall_angle": 42.0,
        })
        db.save_extraction(session_id, name, "topo", {
            "section_name": name, "sector": "Norte", "benches": _norte_topo(name),
            "inter_ramp_angle": 47.0, "overall_angle": 41.0,
        })

    sur = [_bench(1, 3215.0, 3200.0, 10.0, 15.0), _bench(2, 3200.0, 3185.0, 25.0, 30.0)]
    rows.extend([_row("S-05", "Sur", 1, 1, 3200.0), _row("S-05", "Sur", 2, 2, 3185.0)])
    if sur_unmatched_bench:
        sur.append(_bench(3, 3185.0, 3170.0, 40.0, 45.0))
    for kind in ("design", "topo"):
        db.save_extraction(session_id, "S-05", kind, {
            "section_name": "S-05", "sector": "Sur", "benches": sur,
            "inter_ramp_angle": 48.0, "overall_angle": 42.0,
        })
    if height_override is not None:
        for row in rows:
            row["height_design"] = None
    db.save_results(session_id, rows)
    return rows


def _stub_report(monkeypatch, captured: Dict[str, Any], attr: str = "build_word_report") -> None:
    import core

    monkeypatch.setattr(export_router, "_load_mesh_from_db", lambda sid, kind: None)
    monkeypatch.setattr(core, "cut_both_surfaces", lambda md, mt, sec: (None, None))
    monkeypatch.setattr(
        export_router, attr,
        lambda data: (captured.__setitem__("data", data), io.BytesIO(b"bytes"))[1],
    )


def _geometry(client, headers, monkeypatch, payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    captured: Dict[str, Any] = {}
    _stub_report(monkeypatch, captured)
    params = {"filters": json.dumps(payload)} if payload is not None else {}
    response = client.get("/api/v1/export/word", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return {entry["section_name"]: entry for entry in captured["data"].section_geometry}


def _numbers(params: Any) -> List[int]:
    return [bench.bench_number for bench in params.benches]


class TestLevelsBySectorParsing:
    def test_reaches_report_filters_as_hashable_tuple(self):
        parsed = export_router._parse_filters(json.dumps({
            "levelsBySector": {"Sur": ["3185"], "Norte": ["3125", "3110", "3125"], "Este": []},
        }))
        assert parsed.levels_by_sector == {
            "Sur": ["3185"], "Norte": ["3125", "3110", "3125"], "Este": [],
        }

        report_filters = export_router._report_filters(parsed)
        assert report_filters.levels_by_sector == (
            ("Este", ()),
            ("Norte", ("3125", "3110")),
            ("Sur", ("3185",)),
        )
        assert isinstance(hash(report_filters), int)
        assert report_filters.levels_for("Norte") == ("3125", "3110")
        assert report_filters.is_empty() is False

    def test_default_is_empty(self):
        parsed = export_router._parse_filters(None)
        assert parsed.levels_by_sector == {}
        assert export_router._report_filters(parsed).levels_by_sector == ()

    @pytest.mark.parametrize(
        "value",
        [
            ["3125"],
            "3125",
            {"Norte": "3125"},
            {"Norte": [3125]},
            {"Norte": [None]},
            {"Norte": {"3125": True}},
            {f"S{i}": [] for i in range(51)},
            {"Norte": [str(3000 + i) for i in range(51)]},
        ],
    )
    def test_invalid_shapes_raise_400(self, value):
        with pytest.raises(HTTPException) as error:
            export_router._parse_filters(json.dumps({"levelsBySector": value}))
        assert error.value.status_code == 400

    def test_limits_are_inclusive(self):
        parsed = export_router._parse_filters(json.dumps({
            "levelsBySector": {
                f"S{i}": [str(3000 + j) for j in range(50)] for i in range(50)
            },
        }))
        assert len(parsed.levels_by_sector) == 50

    @pytest.mark.parametrize("endpoint", ["excel", "word", "pdf"])
    def test_endpoint_returns_400_for_invalid_shape(
        self, client, headers, session_id, monkeypatch, endpoint
    ):
        _seed(session_id)
        _stub_report(monkeypatch, {}, attr=f"build_{'pdf' if endpoint == 'pdf' else 'word'}_report")
        valid = client.get(
            f"/api/v1/export/{endpoint}",
            headers=headers,
            params={"filters": json.dumps({"levelsBySector": {"Norte": ["3125"]}})},
        )
        assert valid.status_code == 200, valid.text
        response = client.get(
            f"/api/v1/export/{endpoint}",
            headers=headers,
            params={"filters": json.dumps({"levelsBySector": {"Norte": [3125]}})},
        )
        assert response.status_code == 400, response.text


class TestGeometryLevelFilter:
    def test_without_level_filter_keeps_benches_and_has_no_window(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id)
        geometry = _geometry(client, headers, monkeypatch, None)

        assert list(geometry) == ["S-01", "S-02", "S-03", "S-04", "S-05"]
        assert _numbers(geometry["S-02"]["params_design"]) == [1, 2, 3]
        assert _numbers(geometry["S-02"]["params_topo"]) == [1, 2, 3, 4]
        for entry in geometry.values():
            assert entry["view_window"] is None
        assert geometry["S-02"]["sector"] == "Norte"
        assert geometry["S-05"]["sector"] == "Sur"

    def test_sector_filter_alone_does_not_crop(self, client, headers, session_id, monkeypatch):
        _seed(session_id)
        geometry = _geometry(client, headers, monkeypatch, {"sector": ["Norte"]})

        assert list(geometry) == ["S-01", "S-02", "S-03", "S-04"]
        assert _numbers(geometry["S-02"]["params_topo"]) == [1, 2, 3, 4]
        assert all(entry["view_window"] is None for entry in geometry.values())

    def test_per_sector_level_keeps_selected_benches_and_sets_window(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id)
        geometry = _geometry(
            client, headers, monkeypatch, {"levelsBySector": {"Norte": ["3110"]}}
        )

        assert _numbers(geometry["S-01"]["params_design"]) == [2]
        assert _numbers(geometry["S-01"]["params_topo"]) == [2]
        assert _numbers(geometry["S-02"]["params_design"]) == [2]
        assert _numbers(geometry["S-02"]["params_topo"]) == [3]
        for name in NORTE_BENCH3_TOES:
            assert geometry[name]["view_window"] == (15.0, 41.0, 3102.5, 3132.5)
            assert geometry[name]["sector"] == "Norte"
            assert geometry[name]["warnings"] == []

        assert _numbers(geometry["S-05"]["params_design"]) == [1, 2]
        assert _numbers(geometry["S-05"]["params_topo"]) == [1, 2]
        assert geometry["S-05"]["view_window"] is None
        assert geometry["S-05"]["warnings"] == []

    def test_sector_absent_from_levels_by_sector_is_left_untouched(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id, sur_unmatched_bench=True)
        payload = {"levelsBySector": {"Norte": ["3110"]}}
        geometry = _geometry(client, headers, monkeypatch, payload)
        unfiltered = _geometry(client, headers, monkeypatch, None)

        assert list(geometry) == ["S-01", "S-02", "S-03", "S-04", "S-05"]
        for name in NORTE_BENCH3_TOES:
            assert _numbers(geometry[name]["params_design"]) == [2]
            assert geometry[name]["view_window"] == (15.0, 41.0, 3102.5, 3132.5)
        assert _numbers(geometry["S-02"]["params_topo"]) == [3]

        sur = geometry["S-05"]
        assert sur["view_window"] is None
        assert _numbers(sur["params_design"]) == [1, 2, 3]
        assert _numbers(sur["params_topo"]) == [1, 2, 3]
        assert _numbers(sur["params_design"]) == _numbers(unfiltered["S-05"]["params_design"])
        assert _numbers(sur["params_topo"]) == _numbers(unfiltered["S-05"]["params_topo"])

    def test_sector_with_empty_selection_overrides_global_levels(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id, sur_unmatched_bench=True)
        geometry = _geometry(
            client, headers, monkeypatch,
            {"level": ["3110"], "levelsBySector": {"Sur": []}},
        )

        assert _numbers(geometry["S-01"]["params_design"]) == [2]
        assert geometry["S-01"]["view_window"] == (15.0, 41.0, 3102.5, 3132.5)
        assert geometry["S-05"]["view_window"] is None
        assert _numbers(geometry["S-05"]["params_design"]) == [1, 2, 3]
        assert _numbers(geometry["S-05"]["params_topo"]) == [1, 2, 3]

    def test_both_sectors_selected_crop_each_to_its_own_level(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id, sur_unmatched_bench=True)
        geometry = _geometry(
            client, headers, monkeypatch,
            {"levelsBySector": {"Norte": ["3110"], "Sur": ["3200"]}},
        )

        assert _numbers(geometry["S-01"]["params_design"]) == [2]
        assert _numbers(geometry["S-05"]["params_design"]) == [1]
        assert _numbers(geometry["S-05"]["params_topo"]) == [1]
        assert geometry["S-05"]["view_window"] == (0.0, 25.0, 3192.5, 3222.5)

    def test_extra_bench_shares_the_nominal_level_window(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id)
        geometry = _geometry(
            client, headers, monkeypatch, {"levelsBySector": {"Norte": ["3125"]}, "sector": ["Norte"]}
        )

        assert list(geometry) == ["S-01", "S-02", "S-03", "S-04"]
        assert _numbers(geometry["S-02"]["params_design"]) == [1]
        assert _numbers(geometry["S-02"]["params_topo"]) == [1, 2]
        d_min, d_max, z_min, z_max = geometry["S-02"]["view_window"]
        assert (d_min, d_max) == (0.0, 29.0)
        assert (z_min, z_max) == (3122.0 - 7.5, 3140.0 + 7.5)
        assert geometry["S-01"]["view_window"] == (0.0, 26.0, 3117.5, 3147.5)

    def test_window_contains_selected_crest_and_toe_points(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id)
        geometry = _geometry(
            client, headers, monkeypatch, {"levelsBySector": {"Norte": ["3110", "3125"]}}
        )

        for name in NORTE_BENCH3_TOES:
            entry = geometry[name]
            d_min, d_max, z_min, z_max = entry["view_window"]
            benches = entry["params_design"].benches + entry["params_topo"].benches
            assert benches
            for bench in benches:
                for distance in (bench.crest_distance, bench.toe_distance):
                    assert d_min + 10.0 <= distance <= d_max - 10.0
                for elevation in (bench.crest_elevation, bench.toe_elevation):
                    assert z_min + 7.5 <= elevation <= z_max - 7.5

    def test_global_level_drops_sections_without_rows(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id)
        geometry = _geometry(client, headers, monkeypatch, {"level": ["3110"]})

        assert list(geometry) == ["S-01", "S-02", "S-03", "S-04"]
        assert _numbers(geometry["S-03"]["params_design"]) == [2]
        assert _numbers(geometry["S-03"]["params_topo"]) == [3]

    def test_selected_bench_numbers_still_applies(self, client, headers, session_id, monkeypatch):
        _seed(session_id)
        geometry = _geometry(
            client, headers, monkeypatch,
            {"levelsBySector": {"Norte": ["3110", "3125"]}, "selectedBenchNumbers": [1], "sector": ["Norte"]},
        )

        assert _numbers(geometry["S-01"]["params_design"]) == [1]
        assert _numbers(geometry["S-01"]["params_topo"]) == [1]
        assert geometry["S-01"]["view_window"] == (0.0, 26.0, 3117.5, 3147.5)

    def test_missing_bench_height_gives_zero_margin_and_warning(
        self, client, headers, session_id, monkeypatch
    ):
        _seed(session_id, height_override=float("nan"))
        geometry = _geometry(
            client, headers, monkeypatch, {"levelsBySector": {"Norte": ["3110"]}, "sector": ["Norte"]}
        )

        entry = geometry["S-01"]
        assert entry["view_window"] == (15.0, 41.0, 3110.0, 3125.0)
        assert len(entry["warnings"]) == 1
        assert "S-01" in entry["warnings"][0]

    def test_height_falls_back_to_filtered_rows(self, client, headers, session_id, monkeypatch):
        rows = _seed(session_id, height_override=float("nan"))
        for row in rows:
            if row["type"] != "EXTRA":
                row["height_design"] = 12.0
        db.save_results(session_id, rows)
        geometry = _geometry(
            client, headers, monkeypatch, {"levelsBySector": {"Norte": ["3110"]}, "sector": ["Norte"]}
        )

        assert geometry["S-01"]["view_window"] == (15.0, 41.0, 3104.0, 3131.0)
        assert geometry["S-01"]["warnings"] == []


class TestExcelFilters:
    FILTERS = {
        "sector": ["Norte"],
        "section": ["S-01", "S-02"],
        "levelsBySector": {"Norte": ["3125"]},
    }

    @pytest.fixture(autouse=True)
    def legacy_excel_writer(self, monkeypatch):
        monkeypatch.setattr(export_router, "_load_excel_builder", lambda: None)

    def test_real_workbook_matches_filtered_rows(self, client, headers, session_id):
        _seed(session_id)
        response = client.get(
            "/api/v1/export/excel", headers=headers, params={"filters": json.dumps(self.FILTERS)}
        )
        assert response.status_code == 200, response.text

        workbook = openpyxl.load_workbook(io.BytesIO(response.content))
        bench_rows = list(workbook["Bancos"].iter_rows(min_row=2, values_only=True))
        assert [(row[1], row[2], row[3]) for row in bench_rows] == [
            ("S-01", 1, "3125"),
            ("S-02", 1, "3125"),
            ("S-02", 999, "3122"),
        ]
        ramp_rows = list(workbook["Inter-Rampa"].iter_rows(min_row=2, values_only=True))
        assert [row[0] for row in ramp_rows] == ["S-01", "S-02"]

        applied = json.loads(response.headers["X-Export-Filters-Applied"])
        assert applied["sectors"] == ["Norte"]
        assert applied["sections"] == ["S-01", "S-02"]
        assert applied["levels_by_sector"] == {"Norte": ["3125"]}

    def test_writer_receives_filtered_rows_and_cropped_params(
        self, client, headers, session_id, monkeypatch
    ):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            captured["rows"] = [(row["section"], row["bench_num"], row["type"]) for row in results]
            captured["design"] = {p.section_name: _numbers(p) for p in params_d}
            captured["topo"] = {p.section_name: _numbers(p) for p in params_t}

        monkeypatch.setattr(export_router, "export_results", fake_export)
        _seed(session_id)
        response = client.get(
            "/api/v1/export/excel", headers=headers, params={"filters": json.dumps(self.FILTERS)}
        )

        assert response.status_code == 200, response.text
        assert captured["rows"] == [
            ("S-01", 1, "MATCH"), ("S-02", 1, "MATCH"), ("S-02", 999, "EXTRA"),
        ]
        assert captured["design"] == {"S-01": [1], "S-02": [1]}
        assert captured["topo"] == {"S-01": [1], "S-02": [1, 2]}

    def test_level_crop_is_decided_per_sector(self, client, headers, session_id, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            captured["rows"] = [(row["section"], row["bench_num"]) for row in results]
            captured["scores"] = {row["section"]: row["section_score"] for row in results}
            captured["design"] = {p.section_name: _numbers(p) for p in params_d}
            captured["topo"] = {p.section_name: _numbers(p) for p in params_t}

        monkeypatch.setattr(export_router, "export_results", fake_export)
        rows = _seed(session_id, sur_unmatched_bench=True)
        for row in rows:
            if row["sector"] == "Sur":
                row["section_score"] = 77.0
        db.save_results(session_id, rows)
        response = client.get(
            "/api/v1/export/excel", headers=headers,
            params={"filters": json.dumps({"levelsBySector": {"Norte": ["3110"]}})},
        )

        assert response.status_code == 200, response.text
        assert captured["rows"] == [
            ("S-01", 2), ("S-02", 2), ("S-03", 2), ("S-04", 2), ("S-05", 1), ("S-05", 2),
        ]
        assert captured["design"] == {
            "S-01": [2], "S-02": [2], "S-03": [2], "S-04": [2], "S-05": [1, 2, 3],
        }
        assert captured["topo"] == {
            "S-01": [2], "S-02": [3], "S-03": [3], "S-04": [2], "S-05": [1, 2, 3],
        }
        assert captured["scores"]["S-05"] == 77.0

    def test_global_level_filter_applies_to_excel(self, client, headers, session_id, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            captured["rows"] = [(row["section"], row["bench_num"]) for row in results]
            captured["sections"] = [p.section_name for p in params_d]

        monkeypatch.setattr(export_router, "export_results", fake_export)
        _seed(session_id)
        response = client.get(
            "/api/v1/export/excel", headers=headers,
            params={"filters": json.dumps({"level": ["3185"]})},
        )

        assert response.status_code == 200, response.text
        assert captured["rows"] == [("S-05", 2)]
        assert captured["sections"] == ["S-05"]
        applied = json.loads(response.headers["X-Export-Filters-Applied"])
        assert applied["levels"] == ["3185"]
        assert applied["levels_by_sector"] == {}

    def test_without_filters_exports_everything(self, client, headers, session_id, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            captured["n_rows"] = len(results)
            captured["topo"] = {p.section_name: _numbers(p) for p in params_t}

        monkeypatch.setattr(export_router, "export_results", fake_export)
        rows = _seed(session_id)
        response = client.get("/api/v1/export/excel", headers=headers)

        assert response.status_code == 200, response.text
        assert captured["n_rows"] == len(rows)
        assert captured["topo"]["S-02"] == [1, 2, 3, 4]
        assert len(captured["topo"]) == 5


class TestFiltersHeader:
    @pytest.mark.parametrize("endpoint", ["word", "pdf"])
    def test_reports_echo_levels_by_sector(self, client, headers, session_id, monkeypatch, endpoint):
        _seed(session_id)
        _stub_report(monkeypatch, {}, attr=f"build_{endpoint}_report")
        response = client.get(
            f"/api/v1/export/{endpoint}", headers=headers,
            params={"filters": json.dumps({"levelsBySector": {"Sur": ["3185"], "Norte": ["3110"]}})},
        )

        assert response.status_code == 200, response.text
        applied = json.loads(response.headers["X-Export-Filters-Applied"])
        assert applied["levels_by_sector"] == {"Sur": ["3185"], "Norte": ["3110"]}


class TestLevelsEndpoint:
    def test_returns_nominal_levels_per_sector(self, client, headers, session_id):
        _seed(session_id)
        response = client.get("/api/v1/export/levels", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()

        assert set(body) == {"sectors", "warnings"}
        assert [entry["sector"] for entry in body["sectors"]] == ["Norte", "Sur"]

        norte = body["sectors"][0]["levels"]
        assert len(norte) == 3
        assert [level["label"] for level in norte[:2]] == ["3125", "3110"]
        assert set(norte[0]) == {
            "label", "elevation", "min_level", "max_level", "n_sections", "n_rows",
        }
        assert (norte[0]["min_level"], norte[0]["max_level"]) == (3120.0, 3125.0)
        assert (norte[0]["n_sections"], norte[0]["n_rows"]) == (4, 6)
        assert (norte[1]["min_level"], norte[1]["max_level"]) == (3110.0, 3110.0)
        assert (norte[1]["n_sections"], norte[1]["n_rows"]) == (4, 4)
        assert (norte[2]["min_level"], norte[2]["max_level"]) == (3095.0, 3104.0)
        assert norte[2]["label"] == "3100"
        assert norte[2]["elevation"] == 3099.5
        assert (norte[2]["n_sections"], norte[2]["n_rows"]) == (4, 4)

        sur = body["sectors"][1]["levels"]
        assert [level["label"] for level in sur] == ["3200", "3185"]
        assert isinstance(body["warnings"], list)
        assert any("3125" in warning for warning in body["warnings"])

    def test_sectors_follow_first_appearance_order(self, client, headers, session_id):
        rows = _seed(session_id)
        db.save_results(session_id, list(reversed(rows)))
        body = client.get("/api/v1/export/levels", headers=headers).json()

        assert [entry["sector"] for entry in body["sectors"]] == ["Sur", "Norte"]
        assert [level["label"] for level in body["sectors"][1]["levels"]] == ["3125", "3110", "3100"]

    def test_is_session_scoped(self, client, headers, session_id):
        _seed(session_id)
        other = {"x-session-id": db.create_session()}

        assert client.get("/api/v1/export/levels", headers=headers).status_code == 200
        response = client.get("/api/v1/export/levels", headers=other)
        assert response.status_code == 400
        assert "No results" in response.json()["detail"]


@pytest.mark.parametrize("endpoint", ["word", "pdf"])
def test_reports_render_with_level_filters(client, headers, session_id, monkeypatch, endpoint):
    from tests.conftest import create_pit_surface

    _seed(session_id)
    mesh = create_pit_surface(nx=12, ny=12)
    monkeypatch.setattr(export_router, "_load_mesh_from_db", lambda *args: mesh)
    response = client.get(
        f"/api/v1/export/{endpoint}", headers=headers,
        params={"filters": json.dumps({"levelsBySector": {"Norte": ["3110"], "Sur": ["3200"]}})},
    )

    assert response.status_code == 200, response.text
    assert len(response.content) > 1000
    applied = json.loads(response.headers["X-Export-Filters-Applied"])
    assert applied["levels_by_sector"] == {"Norte": ["3110"], "Sur": ["3200"]}
