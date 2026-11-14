"""Current persisted 3D heatmap in the report model (contract C8)."""

import io
import json
from typing import Any, Dict, List

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

import api.database as db
import api.routers.export as export_router
from api.main import app
from api.routers import meshes
from core import HorizontalFaceGeometry
from core.config import HORIZONTAL_DEVIATION
from core.report_data import ReportData, ReportFilters, build_report_data

BOUNDS = {
    "xmin": 0.0,
    "xmax": 60.0,
    "ymin": 0.0,
    "ymax": 140.0,
    "zmin": 80.0,
    "zmax": 110.0,
}
NOT_COMPUTED_A = (
    "Mapa de calor no calculado para el sector A; "
    "calcúlelo en la vista 3D para incluirlo."
)
NOT_COMPUTED_NO_SECTOR = (
    "Mapa de calor no calculado; calcúlelo en la vista 3D para incluirlo."
)
OUTDATED_A = (
    "Mapa de calor del sector A desactualizado "
    "(cambiaron superficies, secciones o configuración); "
    "recalcúlelo en la vista 3D para incluirlo."
)


@pytest.fixture(autouse=True)
def clear_heatmap_caches():
    cached_functions = (
        meshes._get_decimated_vertices_cached,
        meshes._build_horizontal_deviation_cached,
    )
    for cached in cached_functions:
        cached.cache_clear()
    yield
    for cached in cached_functions:
        cached.cache_clear()


def _section(name: str, y: float, sector: str = "A") -> Dict[str, Any]:
    return {
        "name": name,
        "origin": [0.0, y],
        "azimuth": 90.0,
        "length": 60.0,
        "sector": sector,
    }


def _sections(sector: str = "A", count: int = 3) -> List[Dict[str, Any]]:
    return [_section(f"{sector}-{index + 1:02d}", index * 2.0, sector) for index in range(count)]


def _surface() -> trimesh.Trimesh:
    vertices = np.asarray(
        [(0.0, -1.0, 110.0), (60.0, -1.0, 50.0), (0.0, 141.0, 110.0), (60.0, 141.0, 50.0)],
        dtype=float,
    )
    faces = np.asarray([(0, 1, 3), (0, 3, 2)], dtype=np.int64)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _add_meshes(session_id: str) -> tuple[str, str]:
    topo_id = db.save_mesh(session_id, "topo", "topo.stl", b"mesh", 3, 1, BOUNDS)
    design_id = db.save_mesh(session_id, "design", "design.stl", b"mesh", 3, 1, BOUNDS)
    return topo_id, design_id


@pytest.fixture
def heatmap_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "heatmap-lookup-test.db")
    db.init_db()
    profile = (
        np.asarray([0.0, 10.0, 20.0, 30.0, 40.0, 60.0]),
        np.asarray([110.0, 105.0, 100.0, 95.0, 90.0, 80.0]),
    )
    face = HorizontalFaceGeometry(1, 0.0, 110.0, 20.0, 90.0, 20.0)
    surface = _surface()
    monkeypatch.setattr(db, "get_trimesh_by_id", lambda mesh_id: surface)
    monkeypatch.setattr(meshes, "_crop_mesh_to_sections", lambda mesh, sections: mesh)
    monkeypatch.setattr(
        meshes,
        "_profile_data_with_diagnostics",
        lambda mesh, section: (profile, ()),
    )
    monkeypatch.setattr(meshes, "_extract_faces", lambda profile, section, options: {1: face})


@pytest.fixture
def heatmap_session(heatmap_db):
    session_id = db.create_session()
    topo_id, design_id = _add_meshes(session_id)
    db.save_sections(session_id, _sections())
    return session_id, topo_id, design_id


def _request(session_id: str, topo_id: str, design_id: str, **params):
    response = TestClient(app).get(
        f"/api/v1/meshes/{topo_id}/horizontal-deviation",
        params={"design_mesh_id": design_id, **params},
        headers={"x-session-id": session_id},
    )
    assert response.status_code == 200, response.text
    return response


def _forbid_computation(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("the report lookup must never compute a heatmap")

    monkeypatch.setattr(meshes, "_build_horizontal_deviation_payload", fail)
    monkeypatch.setattr(meshes, "_build_horizontal_deviation_cached", fail)


def _result_row(section: str, sector: str, bench: int = 1) -> Dict[str, Any]:
    return {
        "section": section,
        "sector": sector,
        "bench_num": bench,
        "bench_num_topo": bench,
        "type": "MATCH",
        "level": "3125",
        "height_design": 15.0,
        "height_real": 15.0,
        "height_dev": 0.0,
        "height_status": "CUMPLE",
        "angle_design": 70.0,
        "angle_real": 70.0,
        "angle_dev": 0.0,
        "angle_status": "CUMPLE",
        "berm_design": 9.0,
        "berm_real": 9.0,
        "berm_dev": 0.0,
        "berm_min": 6.0,
        "berm_status": "CUMPLE",
        "spill_width": 0.0,
        "effective_berm": 9.0,
        "delta_crest": 0.1,
        "delta_toe": 0.2,
        "berm_score": 60,
        "angle_score": 10,
        "height_score": 30,
        "bench_score": 100,
        "section_score": 100.0,
    }


class TestReportDataFields:
    def test_defaults_are_empty_tuples(self):
        data = build_report_data([], {}, ReportFilters(), {})

        assert isinstance(data, ReportData)
        assert data.heatmaps == ()
        assert data.heatmap_notes == ()

    def test_stores_heatmaps_and_notes_as_tuples(self):
        heatmap = {
            "sector": "A",
            "payload": {"cells": []},
            "params": {"bench_num": None},
            "created_at": "2026-11-13 10:00:00",
            "cache_key": "key",
        }

        data = build_report_data(
            [], {}, ReportFilters(), {},
            heatmaps=[heatmap],
            heatmap_notes=["nota"],
        )

        assert data.heatmaps == (heatmap,)
        assert data.heatmaps[0] is heatmap
        assert data.heatmap_notes == ("nota",)

    def test_new_arguments_are_keyword_only(self):
        with pytest.raises(TypeError):
            build_report_data([], {}, ReportFilters(), {}, None, None, None, None, [], [])


class TestListHorizontalDeviations:
    def test_returns_newest_first_with_the_latest_shape(self, heatmap_db):
        session_id = db.create_session()
        db.save_horizontal_deviation(session_id, "A", "key-1", {"n": 1}, {"p": 1})
        db.save_horizontal_deviation(session_id, "A", "key-2", {"n": 2}, {"p": 2})
        db.save_horizontal_deviation(session_id, "B", "key-b", {"n": "b"}, {"p": "b"})

        listed = db.list_horizontal_deviations(session_id, "A")

        assert [item["cache_key"] for item in listed] == ["key-2", "key-1"]
        assert listed[0] == db.get_latest_horizontal_deviation(session_id, "A")
        assert set(listed[1]) == {"cache_key", "params", "payload", "created_at"}
        assert listed[1]["params"] == {"n": 1}
        assert listed[1]["payload"] == {"p": 1}

    def test_is_scoped_by_session_and_sector(self, heatmap_db):
        session_id = db.create_session()
        other_session = db.create_session()
        db.save_horizontal_deviation(session_id, "A", "key", {"n": 1}, {"p": 1})

        assert db.list_horizontal_deviations(other_session, "A") == []
        assert db.list_horizontal_deviations(session_id, "B") == []
        assert db.list_horizontal_deviations("missing-session", "A") == []


class TestCurrentHeatmaps:
    def test_null_sector_persists_under_empty_string(self, heatmap_session):
        session_id, topo_id, design_id = heatmap_session
        sections = _sections()
        for section in sections:
            section['sector'] = None
        db.save_sections(session_id, sections)
        _request(session_id, topo_id, design_id)
        assert db.get_latest_horizontal_deviation(session_id, '') is not None

    def test_without_stored_result_adds_the_not_computed_note(self, heatmap_session, monkeypatch):
        session_id, _, _ = heatmap_session
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["A"])

        assert heatmaps == []
        assert notes == [NOT_COMPUTED_A]

    def test_blank_sector_uses_the_no_sector_text(self, heatmap_db):
        session_id = db.create_session()

        heatmaps, notes = export_router._current_heatmaps(session_id, [""])

        assert heatmaps == []
        assert notes == [NOT_COMPUTED_NO_SECTOR]

    def test_current_result_is_included_with_its_payload(self, heatmap_session, monkeypatch):
        session_id, topo_id, design_id = heatmap_session
        response = _request(session_id, topo_id, design_id, sector="A")
        stored = db.get_latest_horizontal_deviation(session_id, "A")
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["A"])

        assert notes == []
        assert len(heatmaps) == 1
        heatmap = heatmaps[0]
        assert set(heatmap) == {"sector", "payload", "params", "created_at", "cache_key", "computed_at_text"}
        assert heatmap["sector"] == "A"
        assert heatmap["params"] == stored["params"]
        assert heatmap["created_at"] == stored["created_at"]
        assert heatmap["cache_key"] == stored["cache_key"]
        payload = dict(heatmap["payload"])
        assert payload.pop("section_names") == ["A-01", "A-02", "A-03"]
        assert payload.pop("section_stations_m") == pytest.approx([0.0, 2.0, 4.0])
        assert payload == response.json()

    def test_result_is_excluded_as_outdated_after_sections_change(
        self, heatmap_session, monkeypatch
    ):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A")
        db.save_sections(session_id, _sections(count=4))
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["A"])

        assert heatmaps == []
        assert notes == [OUTDATED_A]

    def test_whole_wall_result_is_preferred_over_a_newer_bench_result(
        self, heatmap_session, monkeypatch
    ):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A")
        _request(session_id, topo_id, design_id, sector="A", bench_num=1)
        assert db.get_latest_horizontal_deviation(session_id, "A")["params"]["bench_num"] == 1
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["A"])

        assert notes == []
        assert [item["params"]["bench_num"] for item in heatmaps] == [None]
        assert heatmaps[0]["payload"]["bench_num"] is None

    def test_newest_current_result_wins_when_no_whole_wall_result_is_current(
        self, heatmap_session, monkeypatch
    ):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A", bench_num=1, longitudinal_step=1.0)
        _request(session_id, topo_id, design_id, sector="A", bench_num=1, longitudinal_step=2.0)
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["A"])

        assert notes == [OUTDATED_A]
        assert heatmaps == []

    def test_outdated_whole_wall_result_does_not_hide_a_current_bench_result(
        self, heatmap_session, monkeypatch
    ):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A")
        db.save_sections(session_id, _sections(count=4))
        meshes._build_horizontal_deviation_cached.cache_clear()
        _request(session_id, topo_id, design_id, sector="A", bench_num=1)
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["A"])

        assert notes == [OUTDATED_A]
        assert heatmaps == []

    def test_other_session_results_are_never_used(self, heatmap_session, monkeypatch):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A")
        other_session = db.create_session()
        _add_meshes(other_session)
        db.save_sections(other_session, _sections())
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(other_session, ["A"])

        assert heatmaps == []
        assert notes == [NOT_COMPUTED_A]

    def test_sectors_keep_their_order_with_one_entry_or_note_each(
        self, heatmap_db, monkeypatch
    ):
        session_id = db.create_session()
        topo_id, design_id = _add_meshes(session_id)
        db.save_sections(session_id, _sections("A") + _sections("B"))
        _request(session_id, topo_id, design_id, sector="B")
        _forbid_computation(monkeypatch)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["B", "A"])

        assert [item["sector"] for item in heatmaps] == ["B"]
        assert heatmaps[0]["payload"]["section_names"] == ["B-01", "B-02", "B-03"]
        assert notes == [NOT_COMPUTED_A]

    def test_lookup_exception_becomes_the_not_computed_note(
        self, heatmap_session, monkeypatch
    ):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A")

        def broken(*args, **kwargs):
            raise RuntimeError("corrupt payload")

        monkeypatch.setattr(db, "list_horizontal_deviation_metadata", broken)

        heatmaps, notes = export_router._current_heatmaps(session_id, ["A"])

        assert heatmaps == []
        assert notes == [NOT_COMPUTED_A]


def _seed_results(session_id: str) -> None:
    db.save_settings(session_id, {"tolerances": {"berm_width": {"min": 6.0}}})
    db.save_results(
        session_id,
        [_result_row(section["name"], "A") for section in _sections()],
    )


def _stub_report(monkeypatch, captured: Dict[str, Any], attr: str) -> None:
    import core

    monkeypatch.setattr(export_router, "_load_mesh_from_db", lambda sid, kind: None)
    monkeypatch.setattr(core, "cut_both_surfaces", lambda md, mt, sec: (None, None))
    monkeypatch.setattr(
        export_router, attr,
        lambda data: (captured.__setitem__("data", data), io.BytesIO(b"bytes"))[1],
    )


ENDPOINTS = [("word", "build_word_report"), ("pdf", "build_pdf_report")]


class TestExportEndpoints:
    @pytest.mark.parametrize("endpoint,attr", ENDPOINTS)
    def test_report_data_carries_the_current_heatmap(
        self, heatmap_session, monkeypatch, endpoint, attr
    ):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A")
        stored_key = db.get_latest_horizontal_deviation(session_id, "A")["cache_key"]
        _seed_results(session_id)
        captured: Dict[str, Any] = {}
        _stub_report(monkeypatch, captured, attr)
        _forbid_computation(monkeypatch)

        response = TestClient(app).get(
            f"/api/v1/export/{endpoint}", headers={"x-session-id": session_id}
        )

        assert response.status_code == 200, response.text
        data = captured["data"]
        assert isinstance(data.heatmaps, tuple)
        assert [item["sector"] for item in data.heatmaps] == ["A"]
        assert data.heatmaps[0]["cache_key"] == stored_key
        assert data.heatmaps[0]["payload"]["section_names"] == ["A-01", "A-02", "A-03"]
        assert data.heatmap_notes == ()

    @pytest.mark.parametrize("endpoint,attr", ENDPOINTS)
    def test_report_data_carries_the_note_when_nothing_was_computed(
        self, heatmap_session, monkeypatch, endpoint, attr
    ):
        session_id, _, _ = heatmap_session
        _seed_results(session_id)
        captured: Dict[str, Any] = {}
        _stub_report(monkeypatch, captured, attr)

        response = TestClient(app).get(
            f"/api/v1/export/{endpoint}", headers={"x-session-id": session_id}
        )

        assert response.status_code == 200, response.text
        assert captured["data"].heatmaps == ()
        assert captured["data"].heatmap_notes == (NOT_COMPUTED_A,)

    @pytest.mark.parametrize("endpoint,attr", ENDPOINTS)
    def test_only_sectors_of_the_filtered_rows_are_looked_up(
        self, heatmap_db, monkeypatch, endpoint, attr
    ):
        session_id = db.create_session()
        _add_meshes(session_id)
        db.save_sections(session_id, _sections("A") + _sections("B"))
        db.save_settings(session_id, {"tolerances": {"berm_width": {"min": 6.0}}})
        db.save_results(
            session_id,
            [_result_row("B-01", "B"), _result_row("A-01", "A")],
        )
        captured: Dict[str, Any] = {}
        _stub_report(monkeypatch, captured, attr)

        response = TestClient(app).get(
            f"/api/v1/export/{endpoint}",
            headers={"x-session-id": session_id},
            params={"filters": json.dumps({"sector": ["B"]})},
        )

        assert response.status_code == 200, response.text
        assert captured["data"].heatmap_notes == (
            "Mapa de calor no calculado para el sector B; "
            "calcúlelo en la vista 3D para incluirlo.",
        )

    @pytest.mark.parametrize("endpoint,attr", ENDPOINTS)
    def test_lookup_exception_keeps_the_export_working(
        self, heatmap_session, monkeypatch, endpoint, attr
    ):
        session_id, topo_id, design_id = heatmap_session
        _request(session_id, topo_id, design_id, sector="A")
        _seed_results(session_id)
        captured: Dict[str, Any] = {}
        _stub_report(monkeypatch, captured, attr)

        def broken(*args, **kwargs):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(db, "list_horizontal_deviation_metadata", broken)

        response = TestClient(app).get(
            f"/api/v1/export/{endpoint}", headers={"x-session-id": session_id}
        )

        assert response.status_code == 200, response.text
        assert captured["data"].heatmaps == ()
        assert captured["data"].heatmap_notes == (NOT_COMPUTED_A,)


class TestSectionStations:
    def test_accumulates_gaps_of_the_sector_in_configured_order(self):
        sections = [
            _section("A-01", 0.0),
            _section("B-01", 1000.0, "B"),
            _section("A-02", 2.0),
            _section("A-03", 7.0),
            _section("B-02", 1003.0, "B"),
        ]

        names, stations = meshes.horizontal_deviation_section_stations(sections, "A")

        assert names == ["A-01", "A-02", "A-03"]
        assert stations == pytest.approx([0.0, 2.0, 7.0])
        assert all(isinstance(value, float) for value in stations)
        assert meshes.horizontal_deviation_section_stations(sections, "B") == (
            ["B-01", "B-02"],
            pytest.approx([0.0, 3.0]),
        )

    def test_uses_planar_distance_between_origins(self):
        sections = [
            {"name": "S1", "origin": [0.0, 0.0, 500.0], "azimuth": 0.0, "length": 50.0, "sector": ""},
            {"name": "S2", "origin": [3.0, 4.0, 900.0], "azimuth": 0.0, "length": 50.0},
        ]

        names, stations = meshes.horizontal_deviation_section_stations(sections, "")

        assert names == ["S1", "S2"]
        assert stations == pytest.approx([0.0, 5.0])

    def test_unknown_sector_and_empty_input_give_empty_lists(self):
        assert meshes.horizontal_deviation_section_stations([], "A") == ([], [])
        assert meshes.horizontal_deviation_section_stations(_sections("A"), "Z") == ([], [])

    def test_matches_the_producer_offsets_including_skipped_pairs(
        self, heatmap_db, monkeypatch
    ):
        too_far = HORIZONTAL_DEVIATION.heatmap_max_section_gap_m + 25.0
        rotated = _section("A-07", 21.0 + too_far)
        rotated["azimuth"] = 90.0 + HORIZONTAL_DEVIATION.heatmap_max_azimuth_delta_deg + 5.0
        sections = [
            _section("A-01", 0.0),
            _section("B-01", 400.0, "B"),
            _section("A-02", 3.0),
            _section("A-03", 3.0),
            _section("A-04", 8.0),
            _section("A-05", 8.0 + too_far),
            _section("B-02", 404.0, "B"),
            _section("A-06", 14.0 + too_far),
            rotated,
            _section("A-08", 25.0 + too_far),
        ]
        session_id = db.create_session()
        topo_id, design_id = _add_meshes(session_id)
        db.save_sections(session_id, sections)
        produced: Dict[str, float] = {}
        original = meshes._section_at_fraction

        def recording(left, right, fraction, station_m):
            if fraction == 0.0:
                produced[left.name] = station_m
            elif fraction == 1.0:
                produced[right.name] = station_m
            return original(left, right, fraction, station_m)

        monkeypatch.setattr(meshes, "_section_at_fraction", recording)
        payload = _request(session_id, topo_id, design_id, sector="A").json()

        names, stations = meshes.horizontal_deviation_section_stations(sections, "A")
        by_name = dict(zip(names, stations))

        assert names == ["A-01", "A-02", "A-03", "A-04", "A-05", "A-06", "A-07", "A-08"]
        assert {"A-01", "A-02", "A-03", "A-04", "A-05", "A-06"} <= set(produced)
        for name, station in produced.items():
            assert by_name[name] == pytest.approx(station, abs=1.0e-9), name
        assert by_name["A-05"] == pytest.approx(8.0 + too_far)
        assert by_name["A-08"] == pytest.approx(25.0 + too_far)
        cell_stations = [cell["station_m"] for cell in payload["cells"]]
        assert min(cell_stations) > by_name["A-01"]
        assert max(cell_stations) < by_name["A-06"]
