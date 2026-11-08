"""Tests for G09 — export endpoints honour the active UI filters.

Covers the ``filters`` JSON query param on ``GET /export/excel`` and
``GET /export/word``: bench selection, spill-area toggling, and
blast-tolerance acceptance. The Excel/Word writers are monkeypatched so
the assertions target the router's filter logic without depending on
the generated file internals.
"""

import io
import json
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.database as db
import api.routers.export as export_router


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/test_api.py isolation pattern)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
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


def _bench(num: int, spill: float = 3.0) -> Dict[str, Any]:
    return {
        "bench_number": num,
        "crest_elevation": 3900.0 - (num - 1) * 15.0,
        "crest_distance": 10.0 + num,
        "toe_elevation": 3885.0 - (num - 1) * 15.0,
        "toe_distance": 15.0 + num,
        "bench_height": 15.0,
        "face_angle": 70.0,
        "berm_width": 9.0,
        "is_ramp": False,
        "spill_width": spill,
        "spill_start_distance": 12.0,
        "spill_start_elevation": 3888.0,
        "effective_berm_width": 6.0,
    }


def _seed_results(client, headers, session_id, benches=(1, 2, 3)):
    import os
    import tempfile

    from tests.test_api import create_test_stl, _upload_mesh

    fd, path = tempfile.mkstemp(suffix=".stl")
    os.close(fd)
    create_test_stl(path)
    try:
        _upload_mesh(client, headers, path, "design")
        _upload_mesh(client, headers, path, "topo")
    finally:
        os.unlink(path)

    sections = [
        {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"}
    ]
    resp = client.post("/api/v1/sections/manual", json=sections, headers=headers)
    assert resp.status_code == 200

    results: List[Dict[str, Any]] = []
    for n in benches:
        results.append(
            {
                "section": "S-01",
                "sector": "A",
                "bench_num": n,
                "level": f"B{n}",
                "type": "MATCH",
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
                "berm_status": "CUMPLE",
                "berm_min": 6.0,
                "delta_crest": 0.1,
                "delta_toe": 0.2,
            }
        )
    db.save_results(session_id, results)

    ext = {
        "section_name": "S-01",
        "sector": "A",
        "benches": [_bench(n) for n in benches],
        "inter_ramp_angle": 45.0,
        "overall_angle": 45.0,
    }
    db.save_extraction(session_id, "S-01", "design", ext)
    db.save_extraction(session_id, "S-01", "topo", ext)
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExportExcelFilters:
    def test_accepts_filters_query_param_and_returns_header(self, client, headers, monkeypatch):
        """The endpoint parses a camelCase filters payload and echoes the
        applied filters back via the X-Export-Filters-Applied header."""
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            captured["results"] = list(results)
            captured["params_topo"] = params_t
            return None

        monkeypatch.setattr(export_router, "export_results", fake_export)

        # Seed minimal results so the 400 guard is bypassed.
        client_id_headers = headers
        session_id = client_id_headers["x-session-id"]
        db.save_results(session_id, [
            {"section": "S-01", "bench_num": 1, "height_status": "CUMPLE",
             "angle_status": "CUMPLE", "berm_status": "CUMPLE"}
        ])
        db.save_extraction(session_id, "S-01", "topo", {
            "section_name": "S-01", "sector": "A", "benches": [], "inter_ramp_angle": 0.0,
            "overall_angle": 0.0,
        })

        payload = {"selectedBenchNumbers": [1], "blastTolerance": 4.5, "showSpillAreas": False}
        resp = client.get(
            "/api/v1/export/excel",
            headers=headers,
            params={"filters": json.dumps(payload)},
        )

        assert resp.status_code == 200, resp.text
        applied = json.loads(resp.headers["X-Export-Filters-Applied"])
        assert applied["blast_tolerance"] == 4.5
        assert applied["show_spill_areas"] is False
        assert applied["selected_bench_numbers"] == [1]

    def test_header_does_not_claim_unsupported_result_filters(
        self, client, headers, monkeypatch
    ):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None):
            with open(path, "wb") as output:
                output.write(b"report")
            captured["rows"] = list(results)

        monkeypatch.setattr(export_router, "export_results", fake_export)
        _seed_multi(headers["x-session-id"])
        response = client.get(
            "/api/v1/export/excel",
            headers=headers,
            params={
                "filters": json.dumps({
                    "sector": ["A"],
                    "section": ["S-01"],
                    "level": ["L2"],
                    "selectedBenchNumbers": [1],
                })
            },
        )

        assert response.status_code == 200, response.text
        assert [(row["section"], row["bench_num"]) for row in captured["rows"]] == [
            ("S-01", 1), ("S-02", 1),
        ]
        applied = json.loads(response.headers["X-Export-Filters-Applied"])
        assert not applied.get("sectors")
        assert not applied.get("sections")
        assert not applied.get("levels")
        assert applied["selected_bench_numbers"] == [1]

    def test_selected_bench_numbers_excludes_others(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            captured["bench_nums"] = [c["bench_num"] for c in results]
            captured["topo_benches"] = [
                b.bench_number for p in params_t for b in p.benches
            ]
            return None

        monkeypatch.setattr(export_router, "export_results", fake_export)
        _seed_results(client, headers, headers["x-session-id"], benches=(1, 2, 3))

        resp = client.get(
            "/api/v1/export/excel",
            headers=headers,
            params={"filters": json.dumps({"selectedBenchNumbers": [2]})},
        )

        assert resp.status_code == 200, resp.text
        assert captured["bench_nums"] == [2]
        assert captured["topo_benches"] == [2]

    def test_empty_selected_bench_numbers_exports_all(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            captured["bench_nums"] = sorted(c["bench_num"] for c in results)
            return None

        monkeypatch.setattr(export_router, "export_results", fake_export)
        _seed_results(client, headers, headers["x-session-id"], benches=(1, 2, 3))

        resp = client.get(
            "/api/v1/export/excel",
            headers=headers,
            params={"filters": json.dumps({"selectedBenchNumbers": []})},
        )

        assert resp.status_code == 200, resp.text
        assert captured["bench_nums"] == [1, 2, 3]

    def test_show_spill_areas_false_zeroes_spill_and_blast_tolerance_parsed(
        self, client, headers, monkeypatch
    ):
        captured: Dict[str, Any] = {}

        def fake_export(results, params_d, params_t, tolerances, path, project_info=None,
                        df_pozos=None, sections=None):
            open(path, "wb").close()
            spill_values = [
                getattr(b, "spill_width")
                for p in params_t
                for b in p.benches
            ]
            captured["spill_widths"] = spill_values
            captured["df_pozos"] = df_pozos
            return None

        monkeypatch.setattr(export_router, "export_results", fake_export)
        _seed_results(client, headers, headers["x-session-id"], benches=(1, 2))

        resp = client.get(
            "/api/v1/export/excel",
            headers=headers,
            params={
                "filters": json.dumps(
                    {"showSpillAreas": False, "showBlastHoles": False, "blastTolerance": 7.5}
                )
            },
        )

        assert resp.status_code == 200, resp.text
        # Spill fields are zeroed on every bench.
        assert captured["spill_widths"] == [0.0, 0.0]
        # No blast DataFrame is fed to the writer when showBlastHoles is false.
        assert captured["df_pozos"] is None
        applied = json.loads(resp.headers["X-Export-Filters-Applied"])
        assert applied["blast_tolerance"] == 7.5
        assert applied["show_blast_holes"] is False


# ---------------------------------------------------------------------------
# Report-data (Word/PDF) filter, blast and filename wiring
# ---------------------------------------------------------------------------


def _row(section: str, sector: str, level: str, bench: int) -> Dict[str, Any]:
    return {
        "section": section,
        "sector": sector,
        "bench_num": bench,
        "level": level,
        "type": "MATCH",
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
        "berm_status": "CUMPLE",
    }


def _seed_multi(session_id: str) -> None:
    """Seed two sectors/sections with mixed levels and benches."""
    sections = [
        {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"},
        {"name": "S-02", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "B"},
    ]
    db.save_sections(session_id, sections)
    db.save_results(
        session_id,
        [
            _row("S-01", "A", "L1", 1),
            _row("S-01", "A", "L1", 2),
            _row("S-01", "A", "L2", 2),
            _row("S-02", "B", "L1", 1),
            _row("S-02", "B", "L3", 3),
        ],
    )
    for sec in sections:
        ext = {
            "section_name": sec["name"],
            "sector": sec["sector"],
            "benches": [_bench(1)],
            "inter_ramp_angle": 0.0,
            "overall_angle": 0.0,
        }
        db.save_extraction(session_id, sec["name"], "design", ext)
        db.save_extraction(session_id, sec["name"], "topo", ext)


class TestExportReportFilters:
    """Word/PDF routes build a ReportData and stream the builder output."""

    def _stub(self, monkeypatch, captured, settings=None, attr="build_word_report"):
        import core

        monkeypatch.setattr(export_router, "_load_mesh_from_db", lambda sid, kind: None)
        monkeypatch.setattr(core, "cut_both_surfaces", lambda md, mt, sec: (None, None))
        monkeypatch.setattr(
            export_router, attr,
            lambda data: (captured.__setitem__("data", data), io.BytesIO(b"bytes"))[1],
        )
        if settings is not None:
            monkeypatch.setattr(db, "get_settings", lambda sid: dict(settings))

    def _get(self, client, headers, endpoint, payload=None):
        params = {"filters": json.dumps(payload)} if payload is not None else {}
        return client.get(f"/api/v1/export/{endpoint}", headers=headers, params=params)

    def test_word_each_dimension_filters_rows(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        self._stub(monkeypatch, captured)
        _seed_multi(headers["x-session-id"])

        cases = [
            ({"sector": ["A"]}, lambda r: r.sector == "A"),
            ({"section": ["S-02"]}, lambda r: r.section == "S-02"),
            ({"level": ["L2"]}, lambda r: r.level == "L2"),
            ({"selectedBenchNumbers": [3]}, lambda r: r.bench_num == 3),
        ]
        for payload, predicate in cases:
            resp = self._get(client, headers, "word", payload)
            assert resp.status_code == 200, resp.text
            rows = captured["data"].rows
            assert rows, payload
            assert all(predicate(r) for r in rows), payload

    def test_word_combined_and_empty_filters(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        self._stub(monkeypatch, captured)
        _seed_multi(headers["x-session-id"])

        resp = self._get(client, headers, "word", {"sector": ["A"], "level": ["L1"], "selectedBenchNumbers": [2]})
        assert resp.status_code == 200, resp.text
        rows = captured["data"].rows
        assert [(r.sector, r.level, r.bench_num) for r in rows] == [("A", "L1", 2)]

        captured.clear()
        resp = self._get(client, headers, "word", {"sector": [], "section": [], "level": [], "selectedBenchNumbers": []})
        assert resp.status_code == 200, resp.text
        assert len(captured["data"].rows) == 5

    def test_word_legacy_query_without_filters_exports_all(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        self._stub(monkeypatch, captured)
        _seed_multi(headers["x-session-id"])

        resp = client.get("/api/v1/export/word", headers=headers)
        assert resp.status_code == 200, resp.text
        assert len(captured["data"].rows) == 5

    def test_word_header_includes_all_dimensions(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        self._stub(monkeypatch, captured)
        _seed_multi(headers["x-session-id"])

        resp = self._get(client, headers, "word", {"sector": ["A"], "section": ["S-01"], "level": ["L1"], "selectedBenchNumbers": [1]})
        applied = json.loads(resp.headers["X-Export-Filters-Applied"])
        assert applied["sectors"] == ["A"]
        assert applied["sections"] == ["S-01"]
        assert applied["levels"] == ["L1"]
        assert applied["selected_bench_numbers"] == [1]

    def test_word_filename_from_content_disposition(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        self._stub(monkeypatch, captured)
        _seed_multi(headers["x-session-id"])

        resp = self._get(client, headers, "word", {})
        assert "Informe_Conciliacion.docx" in resp.headers["content-disposition"]

    def test_word_blast_passthrough_when_holes_exist(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        holes = [{"hole_id": "H1", "x": 1.0, "y": 2.0, "z": 3.0}]
        self._stub(monkeypatch, captured, settings={"blast_holes": holes})
        _seed_multi(headers["x-session-id"])

        resp = self._get(client, headers, "word", {"showBlastHoles": True, "blastTolerance": 4.5})
        assert resp.status_code == 200, resp.text
        assert captured["data"].blast == {"holes": holes, "tolerance": 4.5, "data_status": "legacy_reimport_required"}

    def test_word_blast_absent_without_holes(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        self._stub(monkeypatch, captured, settings={})
        _seed_multi(headers["x-session-id"])

        resp = self._get(client, headers, "word", {"showBlastHoles": True})
        assert resp.status_code == 200, resp.text
        assert captured["data"].blast is None

    @pytest.mark.parametrize("endpoint", ["word", "pdf"])
    def test_blast_toggle_false_excludes_holes_in_reports(
        self, client, headers, monkeypatch, endpoint
    ):
        captured: Dict[str, Any] = {}
        holes = [{"hole_id": "H1", "x": 1.0, "y": 2.0, "z": 3.0}]
        self._stub(
            monkeypatch, captured, settings={"blast_holes": holes},
            attr=f"build_{endpoint}_report",
        )
        _seed_multi(headers["x-session-id"])

        resp = self._get(client, headers, endpoint, {"showBlastHoles": False})
        assert resp.status_code == 200, resp.text
        assert captured["data"].blast is None
        assert json.loads(resp.headers["X-Export-Filters-Applied"])["show_blast_holes"] is False

        captured.clear()
        resp = self._get(client, headers, endpoint, {"showBlastHoles": True})
        assert resp.status_code == 200, resp.text
        assert captured["data"].blast == {"holes": holes, "tolerance": 2.0, "data_status": "legacy_reimport_required"}
        assert json.loads(resp.headers["X-Export-Filters-Applied"])["show_blast_holes"] is True

    def test_pdf_uses_report_builder_filters_and_filename(self, client, headers, monkeypatch):
        captured: Dict[str, Any] = {}
        self._stub(monkeypatch, captured, attr="build_pdf_report")
        _seed_multi(headers["x-session-id"])

        resp = self._get(client, headers, "pdf", {"sector": ["B"]})
        assert resp.status_code == 200, resp.text
        assert all(r.sector == "B" for r in captured["data"].rows)
        assert "Informe_Ejecutivo.pdf" in resp.headers["content-disposition"]
        applied = json.loads(resp.headers["X-Export-Filters-Applied"])
        assert applied["sectors"] == ["B"]


def test_report_depth_extractions_are_unfiltered_and_reject_duplicate_names(
    session_id, monkeypatch,
):
    sections = [
        {"name": "S-01", "sector": "Norte"},
        {"name": "DUP", "sector": "Norte"},
        {"name": "DUP", "sector": "Sur"},
        {"name": "NO-SECTOR", "sector": ""},
    ]
    db.save_sections(session_id, sections)
    db.save_extraction(session_id, "S-01", "topo", {
        "sector": "Norte", "benches": [_bench(1), _bench(2)],
    })
    db.save_extraction(session_id, "DUP", "topo", {
        "sector": "Sur", "benches": [_bench(1)],
    })
    calls = []
    original = db.get_extraction

    def track_get(sid, name, kind):
        calls.append((sid, name, kind))
        return original(sid, name, kind)

    monkeypatch.setattr(db, "get_extraction", track_get)
    found = export_router._load_report_depth_extractions(session_id, sections)

    assert list(found) == [("S-01", "Norte")]
    assert [bench.bench_number for bench in found[("S-01", "Norte")]] == [1, 2]
    assert (session_id, "S-01", "topo") in calls
    assert all(name != "DUP" for _, name, _ in calls)


def test_pdf_builder_joins_persisted_rows_to_sqlite_topo_cache(
    session_id, monkeypatch,
):
    row = {
        "section": "S-01", "sector": " Norte ", "bench_num": 7,
        "bench_num_topo": 2, "type": "MATCH", "level": "90",
        "height_status": "CUMPLE", "angle_status": "CUMPLE",
        "berm_status": "CUMPLE",
    }
    topo_benches = [_bench(2)]
    topo_benches[0].update({"floor_elevation": 80.0, "crest_elevation": 90.0})
    db.save_results(session_id, [row])
    db.save_sections(session_id, [{
        "name": "S-01", "sector": "Norte", "origin": [0, 0],
        "azimuth": 0, "length": 100,
    }])
    db.save_extraction(session_id, "S-01", "topo", {
        "sector": "Norte", "benches": topo_benches,
    })

    captured = {}
    monkeypatch.setattr(export_router, "_load_mesh_from_db", lambda *_: None)
    monkeypatch.setattr(export_router, "_build_section_geometry", lambda *args: [])
    monkeypatch.setattr(export_router, "_report_meta", lambda *args: {})
    monkeypatch.setattr(export_router, "_blast_payload", lambda *args: None)

    def capture_report(data):
        captured["data"] = data
        return io.BytesIO(b"pdf")

    monkeypatch.setattr(export_router, "build_pdf_report", capture_report)
    export_router._build_pdf_payload_sync(
        session_id, None, None, None, None,
    )

    assert captured["data"].depth["profundidad"] == 10.0
