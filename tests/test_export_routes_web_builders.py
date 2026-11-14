"""Export API: Excel and images ZIP routed to the web builders over the shared ReportData."""
import io
import json
import logging
import sys
import types
import zipfile
from typing import Any, Dict, List, Optional

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.routers.export as export_router
from api.main import app
from core.report_data import ReportData
from tests.test_export_level_geometry import _seed

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NORTE = ["S-01", "S-02", "S-03", "S-04"]


class _Profile:
    def __init__(self, top: float):
        self.distances = np.array([0.0, 10.0, 15.0, 25.0, 30.0, 40.0, 45.0, 60.0])
        self.elevations = top - np.array([0.0, 0.0, 15.0, 15.0, 30.0, 30.0, 45.0, 45.0])


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


@pytest.fixture(autouse=True)
def stub_meshes(monkeypatch):
    import core

    def cut(mesh_design, mesh_topo, section):
        top = 3215.0 if section.sector == "Sur" else 3140.0
        return _Profile(top), _Profile(top - 0.8)

    monkeypatch.setattr(export_router, "_load_mesh_from_db", lambda sid, kind: None)
    monkeypatch.setattr(core, "cut_both_surfaces", cut)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def session_id():
    return db.create_session()


@pytest.fixture()
def headers(session_id):
    return {"x-session-id": session_id}


def _params(payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
    return {"filters": json.dumps(payload)} if payload is not None else {}


def _archive(response) -> zipfile.ZipFile:
    assert response.status_code == 200, response.text
    return zipfile.ZipFile(io.BytesIO(response.content))


def _section_members(archive: zipfile.ZipFile) -> List[str]:
    return [name for name in archive.namelist() if name[:2].isdigit()]


def _install_excel_builder(monkeypatch, captured: Dict[str, Any], payload: bytes = b"web-xlsx"):
    def build_excel_report(data):
        captured.setdefault("calls", []).append(data)
        captured["data"] = data
        return io.BytesIO(payload)

    module = types.ModuleType("core.web_excel_report")
    module.build_excel_report = build_excel_report
    monkeypatch.setitem(sys.modules, "core.web_excel_report", module)


def _remove_excel_builder(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "core.web_excel_report", None)


class TestImagesRoute:
    def test_unfiltered_zip_has_every_section_plan_matrix_and_readme(
        self, client, headers, session_id
    ):
        _seed(session_id)
        response = client.get("/api/v1/export/images", headers=headers)
        archive = _archive(response)

        assert archive.namelist() == [
            "LEEME.txt", "plano.png", "matriz.png",
            "01_S-01.png", "02_S-02.png", "03_S-03.png", "04_S-04.png", "05_S-05.png",
        ]
        for name in archive.namelist():
            if name.endswith(".png"):
                assert archive.read(name).startswith(PNG_SIGNATURE), name
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["content-disposition"] == (
            "attachment; filename=Secciones_Imagenes.zip"
        )

    def test_level_filter_returns_only_the_filtered_sections_and_crops_them(
        self, client, headers, session_id
    ):
        _seed(session_id)
        unfiltered = _archive(client.get("/api/v1/export/images", headers=headers))
        response = client.get(
            "/api/v1/export/images", headers=headers, params=_params({"level": ["3110"]})
        )
        filtered = _archive(response)

        assert _section_members(filtered) == [
            "01_S-01.png", "02_S-02.png", "03_S-03.png", "04_S-04.png",
        ]
        assert _section_members(unfiltered)[-1] == "05_S-05.png"
        assert filtered.read("01_S-01.png") != unfiltered.read("01_S-01.png")
        assert filtered.read("matriz.png") != unfiltered.read("matriz.png")
        assert response.content != client.get("/api/v1/export/images", headers=headers).content
        readme = filtered.read("LEEME.txt").decode("utf-8")
        assert "cota 3110" in readme
        assert "S-05" not in readme

    def test_per_sector_level_and_section_filters(self, client, headers, session_id):
        _seed(session_id)
        archive = _archive(client.get(
            "/api/v1/export/images", headers=headers,
            params=_params({"section": ["S-02", "S-05"], "levelsBySector": {"Norte": ["3125"]}}),
        ))
        assert _section_members(archive) == ["01_S-02.png", "02_S-05.png"]

    def test_builder_receives_the_filtered_report_data(
        self, client, headers, session_id, monkeypatch
    ):
        captured: Dict[str, Any] = {}

        def fake_zip(data):
            captured["data"] = data
            return io.BytesIO(b"zip-bytes")

        monkeypatch.setattr(export_router, "build_images_zip", fake_zip)
        _seed(session_id)
        response = client.get(
            "/api/v1/export/images", headers=headers,
            params=_params({"levelsBySector": {"Norte": ["3110"]}, "sector": ["Norte"]}),
        )

        assert response.status_code == 200, response.text
        assert response.content == b"zip-bytes"
        data = captured["data"]
        assert isinstance(data, ReportData)
        assert [entry["section_name"] for entry in data.section_geometry] == NORTE
        assert all(entry["view_window"] is not None for entry in data.section_geometry)
        assert {row.level_nominal for row in data.rows} == {"3110"}
        assert data.filters.levels_by_sector == (("Norte", ("3110",)),)

    def test_filters_are_echoed_in_the_header(self, client, headers, session_id):
        _seed(session_id)
        response = client.get(
            "/api/v1/export/images", headers=headers, params=_params({"level": ["3110"]})
        )
        applied = json.loads(response.headers["X-Export-Filters-Applied"])
        assert applied["levels"] == ["3110"]

    def test_invalid_filters_return_400(self, client, headers, session_id):
        _seed(session_id)
        response = client.get(
            "/api/v1/export/images", headers=headers, params={"filters": "{not json"}
        )
        assert response.status_code == 400

    def test_without_results_returns_400(self, client, headers):
        assert client.get("/api/v1/export/images", headers=headers).status_code == 400

    def test_legacy_zip_generator_is_no_longer_used(self, client, headers, session_id, monkeypatch):
        def forbidden(*args, **kwargs):
            raise AssertionError("legacy images generator must not be called")

        monkeypatch.setattr(
            export_router, "generate_section_images_zip", forbidden, raising=False
        )
        _seed(session_id)
        assert client.get("/api/v1/export/images", headers=headers).status_code == 200


class TestExcelRoute:
    def test_web_builder_receives_the_filtered_report_data(
        self, client, headers, session_id, monkeypatch
    ):
        captured: Dict[str, Any] = {}
        _install_excel_builder(monkeypatch, captured)

        def forbidden(*args, **kwargs):
            raise AssertionError("legacy Excel writer must not be called")

        monkeypatch.setattr(export_router, "export_results", forbidden)
        _seed(session_id)
        response = client.get(
            "/api/v1/export/excel", headers=headers,
            params=_params({"levelsBySector": {"Norte": ["3110"]}, "sector": ["Norte"]}),
        )

        assert response.status_code == 200, response.text
        assert response.content == b"web-xlsx"
        assert response.headers["content-type"] == XLSX_MEDIA
        assert "Conciliacion_Geotecnica.xlsx" in response.headers["content-disposition"]
        applied = json.loads(response.headers["X-Export-Filters-Applied"])
        assert applied["sectors"] == ["Norte"]
        assert applied["levels_by_sector"] == {"Norte": ["3110"]}

        data = captured["data"]
        assert isinstance(data, ReportData)
        assert [(row.section, row.bench_num) for row in data.rows] == [
            (name, 2) for name in NORTE
        ]
        assert [entry["section_name"] for entry in data.section_geometry] == NORTE
        assert all(entry["view_window"] is not None for entry in data.section_geometry)

    def test_web_builder_gets_project_meta(self, client, headers, session_id, monkeypatch):
        captured: Dict[str, Any] = {}
        _install_excel_builder(monkeypatch, captured)
        _seed(session_id)
        response = client.get(
            "/api/v1/export/excel", headers=headers,
            params={"project": "Mina X", "author": "Ana", "operation": "Op", "phase": "F3"},
        )
        assert response.status_code == 200, response.text
        meta = captured["data"].meta
        assert (meta["project"], meta["author"], meta["operation"], meta["phase"]) == (
            "Mina X", "Ana", "Op", "F3",
        )

    def test_falls_back_to_the_legacy_writer_when_the_module_is_missing(
        self, client, headers, session_id, monkeypatch, caplog
    ):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            with open(path, "wb") as output:
                output.write(b"legacy-xlsx")
            captured["rows"] = [(row["section"], row["bench_num"]) for row in results]

        _remove_excel_builder(monkeypatch)
        monkeypatch.setattr(export_router, "export_results", fake_export)
        _seed(session_id)
        with caplog.at_level(logging.WARNING, logger=export_router.logger.name):
            response = client.get(
                "/api/v1/export/excel", headers=headers,
                params=_params({"levelsBySector": {"Norte": ["3110"]}, "sector": ["Norte"]}),
            )

        assert response.status_code == 200, response.text
        assert response.content == b"legacy-xlsx"
        assert response.headers["content-type"] == XLSX_MEDIA
        assert captured["rows"] == [(name, 2) for name in NORTE]
        assert any("web_excel_report" in record.getMessage() for record in caplog.records)

    def test_legacy_fallback_does_not_need_meshes(self, client, headers, session_id, monkeypatch):
        def no_mesh(sid, kind):
            raise AssertionError("the legacy Excel writer must not load meshes")

        _remove_excel_builder(monkeypatch)
        monkeypatch.setattr(export_router, "_load_mesh_from_db", no_mesh)
        _seed(session_id)
        response = client.get("/api/v1/export/excel", headers=headers)
        assert response.status_code == 200, response.text
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert "[Content_Types].xml" in archive.namelist()

    def test_builder_error_is_not_masked_by_the_legacy_writer(
        self, client, headers, session_id, monkeypatch
    ):
        def broken(data):
            raise RuntimeError("boom")

        def forbidden(*args, **kwargs):
            raise AssertionError("legacy Excel writer must not be called")

        module = types.ModuleType("core.web_excel_report")
        module.build_excel_report = broken
        monkeypatch.setitem(sys.modules, "core.web_excel_report", module)
        monkeypatch.setattr(export_router, "export_results", forbidden)
        _seed(session_id)
        response = client.get("/api/v1/export/excel", headers=headers)
        assert response.status_code == 500
        assert response.json()["detail"] == "Excel export failed"

    def test_invalid_filters_and_missing_results_return_400(
        self, client, headers, session_id, monkeypatch
    ):
        _install_excel_builder(monkeypatch, {})
        assert client.get("/api/v1/export/excel", headers=headers).status_code == 400
        _seed(session_id)
        response = client.get(
            "/api/v1/export/excel", headers=headers, params={"filters": "{not json"}
        )
        assert response.status_code == 400


class TestExcelWithoutMeshes:
    @pytest.fixture(autouse=True)
    def real_mesh_loader(self, monkeypatch):
        from api.routers.process import _load_mesh_from_db

        monkeypatch.setattr(export_router, "_load_mesh_from_db", _load_mesh_from_db)

    def test_web_excel_builds_with_empty_geometry(self, client, headers, session_id, monkeypatch):
        captured: Dict[str, Any] = {}
        _install_excel_builder(monkeypatch, captured)
        _seed(session_id)
        response = client.get("/api/v1/export/excel", headers=headers)
        assert response.status_code == 200, response.text
        data = captured["data"]
        assert len(data.rows) > 0
        assert tuple(data.section_geometry) == ()
        assert tuple(data.excavation) == ()
        assert (data.plan_inputs or {}).get("mesh_topo") is None

    def test_real_web_workbook_states_the_missing_geometry(self, client, headers, session_id):
        from openpyxl import load_workbook

        _seed(session_id)
        response = client.get(
            "/api/v1/export/excel", headers=headers,
            params=_params({"levelsBySector": {"Norte": ["3110"]}, "sector": ["Norte"]}),
        )
        assert response.status_code == 200, response.text
        book = load_workbook(io.BytesIO(response.content))
        assert book.sheetnames[:5] == ["Léeme", "Resumen", "Bancos", "Secciones", "Sector-Nivel"]
        text = "\n".join(
            str(cell.value) for row in book["Léeme"].iter_rows() for cell in row if cell.value
        )
        assert "Sin geometría de secciones" in text
        assert book["Bancos"].max_row == 1 + len(NORTE)

    @pytest.mark.parametrize("kind", ["word", "pdf", "images"])
    def test_other_routes_still_require_meshes(self, client, headers, session_id, monkeypatch, kind):
        def forbidden(data):
            raise AssertionError("builder must not run without meshes")

        monkeypatch.setattr(export_router, "build_word_report", forbidden)
        monkeypatch.setattr(export_router, "build_pdf_report", forbidden)
        monkeypatch.setattr(export_router, "build_images_zip", forbidden)
        _seed(session_id)
        response = client.get(f"/api/v1/export/{kind}", headers=headers)
        assert response.status_code == 400
        assert "mesh not uploaded" in response.json()["detail"]

    def test_shared_helper_requires_meshes_by_default(self, session_id):
        from fastapi import HTTPException

        _seed(session_id)
        with pytest.raises(HTTPException) as error:
            export_router._build_report_data_sync(session_id, None, None, None, None, None)
        assert error.value.status_code == 400
        data, _filters = export_router._build_report_data_sync(
            session_id, None, None, None, None, None, require_meshes=False
        )
        assert tuple(data.section_geometry) == ()


class TestSharedReportData:
    FILTERS = {"levelsBySector": {"Norte": ["3110"]}, "selectedBenchNumbers": [2]}

    def _capture_all(self, monkeypatch) -> Dict[str, Any]:
        captured: Dict[str, Any] = {}

        def builder(kind):
            def build(data):
                captured[kind] = data
                return io.BytesIO(kind.encode())
            return build

        excel: Dict[str, Any] = {}
        _install_excel_builder(monkeypatch, excel)
        captured["_excel"] = excel
        monkeypatch.setattr(export_router, "build_word_report", builder("word"))
        monkeypatch.setattr(export_router, "build_pdf_report", builder("pdf"))
        monkeypatch.setattr(export_router, "build_images_zip", builder("images"))
        return captured

    def test_helper_returns_report_data_and_parsed_filters(self, session_id):
        _seed(session_id)
        data, export_filters = export_router._build_report_data_sync(
            session_id, "P", "A", "O", "F", json.dumps(self.FILTERS)
        )
        assert isinstance(data, ReportData)
        assert export_filters.levels_by_sector == {"Norte": ["3110"]}
        assert export_filters.selected_bench_numbers == [2]
        assert data.meta["project"] == "P"
        assert {row.bench_num for row in data.rows} == {2}

    def test_four_routes_build_the_same_filtered_report_data(
        self, client, headers, session_id, monkeypatch
    ):
        captured = self._capture_all(monkeypatch)
        calls: List[tuple] = []
        original = export_router._build_report_data_sync

        def spy(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(export_router, "_build_report_data_sync", spy)
        monkeypatch.setattr(
            export_router, "_report_meta",
            lambda *args: {"project": "fixed", "generated_at": "2026-11-14T00:00:00"},
        )
        _seed(session_id)
        for endpoint in ("excel", "word", "pdf", "images"):
            response = client.get(
                f"/api/v1/export/{endpoint}", headers=headers, params=_params(self.FILTERS)
            )
            assert response.status_code == 200, (endpoint, response.text)
        captured["excel"] = captured.pop("_excel")["data"]

        assert len(calls) == 4
        assert {call[0] for call in calls} == {session_id}
        reference = captured["word"]
        for kind in ("excel", "pdf", "images"):
            data = captured[kind]
            assert data.rows == reference.rows, kind
            assert data.profiles == reference.profiles, kind
            assert data.matrix == reference.matrix, kind
            assert data.headline == reference.headline, kind
            assert data.filters == reference.filters, kind
            assert [
                (entry["section_name"], entry["view_window"]) for entry in data.section_geometry
            ] == [
                (entry["section_name"], entry["view_window"])
                for entry in reference.section_geometry
            ], kind

    @pytest.mark.parametrize("endpoint", ["excel", "images", "word", "pdf"])
    def test_heatmap_lookup_stays_in_the_shared_helper(
        self, client, headers, session_id, monkeypatch, endpoint
    ):
        captured = self._capture_all(monkeypatch)
        looked_up: List[Any] = []

        def fake_heatmaps(sid, sectors):
            looked_up.append((sid, list(sectors)))
            return [{"sector": "Norte", "payload": {}, "params": {}, "created_at": "",
                     "cache_key": "k"}], ["nota de mapa"]

        monkeypatch.setattr(export_router, "_current_heatmaps", fake_heatmaps)
        _seed(session_id)
        response = client.get(
            f"/api/v1/export/{endpoint}", headers=headers, params=_params({"sector": ["Norte"]})
        )
        assert response.status_code == 200, response.text
        data = captured["_excel"]["data"] if endpoint == "excel" else captured[endpoint]
        if endpoint in ("excel", "images"):
            assert looked_up == []
            assert data.heatmaps == ()
            assert data.heatmap_notes == ()
        else:
            assert looked_up == [(session_id, ["Norte"])]
            assert data.heatmaps[0]["cache_key"] == "k"
            assert data.heatmap_notes == ("nota de mapa",)

    @pytest.mark.parametrize("endpoint", ["word", "pdf"])
    def test_word_and_pdf_keep_their_headers(
        self, client, headers, session_id, monkeypatch, endpoint
    ):
        self._capture_all(monkeypatch)
        _seed(session_id)
        response = client.get(
            f"/api/v1/export/{endpoint}", headers=headers, params=_params(self.FILTERS)
        )
        assert response.status_code == 200, response.text
        filename = "Informe_Conciliacion.docx" if endpoint == "word" else "Informe_Ejecutivo.pdf"
        assert response.headers["content-disposition"] == f"attachment; filename={filename}"
        applied = json.loads(response.headers["X-Export-Filters-Applied"])
        assert applied["levels_by_sector"] == {"Norte": ["3110"]}


class TestCrossSessionIsolation:
    def _seed_other(self, session_id: str) -> None:
        from tests.test_export_level_geometry import TOLERANCES, _bench, _row

        db.save_sections(session_id, [
            {"name": "X-01", "origin": [500.0, 900.0], "azimuth": 0.0, "length": 100.0,
             "sector": "Sur"},
        ])
        db.save_settings(session_id, {"tolerances": TOLERANCES})
        benches = [_bench(1, 3215.0, 3200.0, 10.0, 15.0)]
        for kind in ("design", "topo"):
            db.save_extraction(session_id, "X-01", kind, {
                "section_name": "X-01", "sector": "Sur", "benches": benches,
                "inter_ramp_angle": 48.0, "overall_angle": 42.0,
            })
        db.save_results(session_id, [_row("X-01", "Sur", 1, 1, 3200.0)])

    def test_images_only_contain_the_sections_of_the_requesting_session(self, client):
        first, second = db.create_session(), db.create_session()
        _seed(first)
        self._seed_other(second)

        first_zip = _archive(client.get("/api/v1/export/images", headers={"x-session-id": first}))
        second_zip = _archive(
            client.get("/api/v1/export/images", headers={"x-session-id": second})
        )

        assert _section_members(second_zip) == ["01_X-01.png"]
        assert not any("X-01" in name for name in first_zip.namelist())
        assert "X-01" not in first_zip.read("LEEME.txt").decode("utf-8")
        assert "S-01" not in second_zip.read("LEEME.txt").decode("utf-8")

    def test_excel_data_only_contains_the_rows_of_the_requesting_session(
        self, client, monkeypatch
    ):
        captured: Dict[str, Any] = {}
        _install_excel_builder(monkeypatch, captured)
        first, second = db.create_session(), db.create_session()
        _seed(first)
        self._seed_other(second)

        assert client.get(
            "/api/v1/export/excel", headers={"x-session-id": second}
        ).status_code == 200
        assert {row.section for row in captured["data"].rows} == {"X-01"}
        assert client.get(
            "/api/v1/export/excel", headers={"x-session-id": first}
        ).status_code == 200
        assert {row.section for row in captured["data"].rows} == {*NORTE, "S-05"}

    def test_session_without_results_gets_400_while_another_has_data(self, client):
        seeded, empty = db.create_session(), db.create_session()
        _seed(seeded)
        for endpoint in ("images", "excel"):
            response = client.get(
                f"/api/v1/export/{endpoint}", headers={"x-session-id": empty}
            )
            assert response.status_code == 400, endpoint
