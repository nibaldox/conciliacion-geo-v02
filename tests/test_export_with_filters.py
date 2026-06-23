"""Tests for G09 — export endpoints honour the active UI filters.

Covers the ``filters`` JSON query param on ``GET /export/excel`` and
``GET /export/word``: bench selection, spill-area toggling, and
blast-tolerance acceptance. The Excel/Word writers are monkeypatched so
the assertions target the router's filter logic without depending on
the generated file internals.
"""

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
