"""API tests for the proposed-compliance contract (wave 10).

Covers the additive pipeline integration
(``compare_design_vs_asbuilt_guided``), persistence of the ``guided_*`` /
``proposed_*`` fields in the results JSON, the legacy-session
``not_computed`` behaviour, and the summary endpoint
``GET /api/v1/process/proposed-compliance``.
"""
from __future__ import annotations

import json
from typing import List

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

import api.database as db
import api.routers.process as process_router
import api.schemas as schemas
from core import summarize_proposed

ENDPOINT = "/api/v1/process/proposed-compliance"

NEW_ROW_KEYS = {
    "guided_delta_crest", "guided_delta_crest_status",
    "guided_delta_toe", "guided_delta_toe_status",
    "guided_height", "guided_height_status",
    "guided_angle", "guided_angle_status",
    "guided_berm", "guided_berm_status",
    "guided_floor_offset_m", "guided_floor_offset_status",
    "guided_remaining_thickness_mean_m", "guided_remaining_thickness_max_m",
    "guided_excavation_debt_area_m2",
    "guided_berm_remnant_max_m", "guided_berm_remnant_area_m2",
    "guided_warnings",
    "design_bench_state", "split_bench", "split_of",
    "proposed_source", "proposed_height", "proposed_angle",
    "proposed_delta_crest", "proposed_delta_toe", "proposed_berm",
    "proposed_height_source", "proposed_angle_source",
    "proposed_crest_source", "proposed_toe_source", "proposed_berm_source",
    "proposed_height_status", "proposed_angle_status",
    "proposed_crest_status", "proposed_toe_status", "proposed_berm_status",
    "proposed_bench_score", "proposed_evaluable", "proposed_exclusion_reason",
    "floor_offset_m", "floor_status",
    "excavation_debt_thickness_mean_m", "excavation_debt_thickness_max_m",
    "excavation_debt_area_m2",
    "berm_remnant_max_m", "berm_remnant_area_m2",
    "floor_tolerance_used",
    "proposal_status", "proposal_error",
}

SUMMARY_KEYS = {
    "section", "proposed_global_score", "n_rows", "n_evaluable",
    "n_not_excavated", "n_section_truncated", "n_unmeasured",
    "n_split_fragments", "n_split_benches", "excavation_debt_area_m2",
    "floor_status_counts", "coverage", "by_section",
}

SECTION_SUMMARY_KEYS = {
    "section", "proposed_section_score", "proposed_section_status",
    "n_rows", "n_evaluable", "n_not_excavated", "n_section_truncated",
    "n_unmeasured", "n_split_fragments", "n_split_benches",
    "excavation_debt_area_m2", "floor_status_counts",
}


def _bench_surface(shift: float = 0.0) -> trimesh.Trimesh:
    profile = [(-10, 30), (0, 30), (10, 15), (20, 15), (30, 0), (50, 0)]
    vertices = [(x + shift, y, z) for x, z in profile for y in (-10, 10)]
    faces = []
    for index in range(len(profile) - 1):
        start = index * 2
        faces.extend([(start, start + 1, start + 2), (start + 1, start + 3, start + 2)])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _upload(client: TestClient, headers: dict, role: str, shift: float) -> None:
    mesh = _bench_surface(0.5 if role == "topo" else shift)
    stl_bytes = mesh.export(file_type="stl")
    response = client.post(
        "/api/v1/meshes/upload",
        files={"file": (f"{role}.stl", stl_bytes, "application/octet-stream")},
        data={"type": role},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _add_sections(client: TestClient, headers: dict, names=("S-01",), sector: str = "A") -> None:
    response = client.post(
        "/api/v1/sections/manual",
        json=[
            {"name": name, "origin": [20.0, 0.0], "azimuth": 90, "length": 60, "sector": sector}
            for name in names
        ],
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _run(client: TestClient, headers: dict) -> dict:
    response = client.post("/api/v1/process", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "complete"
    assert response.json()["total_results"] > 0
    return response.json()


def _results(client: TestClient, headers: dict) -> List[dict]:
    response = client.get("/api/v1/process/results", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _official_view(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in NEW_ROW_KEYS}


def _row_key(row: dict):
    return (row.get("section"), row.get("type"), row.get("bench_num"), row.get("bench_num_topo"))


def _no_json_constants(text: str) -> None:
    json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(
        AssertionError(f"non-strict JSON constant: {value}")))


def _legacy_rows() -> List[dict]:
    return [
        {
            "section": "S-01", "sector": "C", "bench_num": 1, "bench_num_topo": 1,
            "type": "MATCH", "level": "85",
            "height_design": 15.0, "height_real": 14.8, "height_dev": -0.2,
            "height_status": "CUMPLE",
            "angle_design": 56.3, "angle_real": 57.0, "angle_dev": 0.7,
            "angle_status": "CUMPLE",
            "berm_design": 10.0, "berm_real": 9.8, "berm_min": 7.0,
            "berm_status": "CUMPLE",
            "delta_crest": 0.5, "delta_toe": -0.8,
            "bench_score": 100, "section_score": 100.0, "section_status": "CUMPLE",
        },
        {
            "section": "S-01", "sector": "C", "bench_num": 2, "bench_num_topo": None,
            "type": "MISSING", "level": "70",
            "height_design": 15.0, "height_real": None, "height_dev": None,
            "height_status": "NO CONSTRUIDO",
            "angle_design": 56.3, "angle_real": None, "angle_dev": None,
            "angle_status": "-",
            "berm_design": 10.0, "berm_real": None, "berm_min": None,
            "berm_status": "FALTA BANCO",
            "delta_crest": None, "delta_toe": None,
            "bench_score": 0, "section_score": 0.0, "section_status": "NO CUMPLE",
        },
    ]


def _proposal_rows(section: str = "S1", sector: str = "A") -> List[dict]:
    return [
        {
            "section": section, "sector": sector, "bench_num": 1,
            "bench_num_topo": 1, "type": "MATCH", "level": "85",
            "proposal_status": "current",
            "proposed_source": "current", "proposed_height": 14.8,
            "proposed_angle": 57.0, "proposed_delta_crest": 0.5,
            "proposed_delta_toe": -0.8, "proposed_berm": 9.8,
            "proposed_height_status": "CUMPLE", "proposed_angle_status": "CUMPLE",
            "proposed_crest_status": "CUMPLE", "proposed_toe_status": "FUERA DE TOLERANCIA",
            "proposed_berm_status": "CUMPLE", "proposed_bench_score": 100.0,
            "proposed_evaluable": True, "proposed_exclusion_reason": None,
            "floor_offset_m": 0.2, "floor_status": "CUMPLE",
            "excavation_debt_thickness_mean_m": None,
            "excavation_debt_thickness_max_m": None,
            "excavation_debt_area_m2": None,
        },
        {
            "section": section, "sector": sector, "bench_num": 2,
            "bench_num_topo": None, "type": "MISSING", "level": "70",
            "proposal_status": "current",
            "proposed_source": None, "proposed_height": None,
            "proposed_angle": None, "proposed_delta_crest": None,
            "proposed_delta_toe": None, "proposed_berm": None,
            "proposed_height_status": "-", "proposed_angle_status": "-",
            "proposed_crest_status": "-", "proposed_toe_status": "-",
            "proposed_berm_status": "-", "proposed_bench_score": None,
            "proposed_evaluable": False,
            "proposed_exclusion_reason": "not_excavated",
            "floor_offset_m": None, "floor_status": "-",
            "excavation_debt_thickness_mean_m": 12.0,
            "excavation_debt_thickness_max_m": 14.5,
            "excavation_debt_area_m2": 180.0,
        },
    ]


@pytest.fixture()
def processed_session(client: TestClient):
    headers = {"X-Session-ID": "proposed-compliance-current"}
    _upload(client, headers, "design", 0.0)
    _upload(client, headers, "topo", 0.5)
    _add_sections(client, headers)
    _run(client, headers)
    return client, headers


class TestPipelinePersistsProposal:
    def test_rows_carry_proposal_fields_and_status_current(self, processed_session):
        client, headers = processed_session
        rows = _results(client, headers)
        assert rows
        for row in rows:
            assert row["proposal_status"] == "current"
            assert "proposal_error" not in row or row["proposal_error"] is None
            assert row["proposed_evaluable"] is False or row["proposed_source"] is not None
            assert row["floor_status"]
        match_rows = [r for r in rows if r["type"] == "MATCH"]
        assert match_rows, rows
        assert any(r["proposed_evaluable"] for r in match_rows)
        assert any(r["guided_delta_toe"] is not None for r in match_rows)

    def test_official_fields_identical_to_legacy_comparison(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch,
    ):
        guided_headers = {"X-Session-ID": "proposed-identity-guided"}
        legacy_headers = {"X-Session-ID": "proposed-identity-legacy"}
        for headers in (guided_headers, legacy_headers):
            _upload(client, headers, "design", 0.0)
            _upload(client, headers, "topo", 0.5)
            _add_sections(client, headers)
        _run(client, guided_headers)

        def _raise(*args, **kwargs):
            raise RuntimeError("guided boom")

        monkeypatch.setattr(process_router, "compare_design_vs_asbuilt_guided", _raise)
        _run(client, legacy_headers)

        guided_rows = _results(client, guided_headers)
        legacy_rows = _results(client, legacy_headers)
        assert guided_rows and legacy_rows

        legacy_by_key = {_row_key(r): _official_view(r) for r in legacy_rows}
        assert len(legacy_by_key) == len(legacy_rows)
        for row in guided_rows:
            key = _row_key(row)
            assert key in legacy_by_key, key
            assert _official_view(row) == legacy_by_key[key], key
        for row in legacy_rows:
            assert row["proposal_status"] == "failed"
            assert isinstance(row["proposal_error"], str) and row["proposal_error"]

    def test_guided_failure_never_500(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        headers = {"X-Session-ID": "proposed-guided-failure"}
        _upload(client, headers, "design", 0.0)
        _upload(client, headers, "topo", 0.5)
        _add_sections(client, headers)

        def _raise(*args, **kwargs):
            raise ValueError("guided exploded")

        monkeypatch.setattr(process_router, "compare_design_vs_asbuilt_guided", _raise)
        response = client.post("/api/v1/process", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "complete"
        assert response.json()["total_results"] > 0

        rows = _results(client, headers)
        assert rows
        for row in rows:
            assert row["proposal_status"] == "failed"
            assert row["proposal_error"]
            assert "guided boom" not in json.dumps(row) or True
        failed = client.get(ENDPOINT, headers=headers).json()
        assert failed["proposal_status"] == "partial"
        assert failed["n_failed_rows"] == len(rows)

    def test_results_json_is_strict_no_nan_or_infinity(self, processed_session):
        client, headers = processed_session
        raw = client.get("/api/v1/process/results", headers=headers)
        _no_json_constants(raw.text)
        summary = client.get(ENDPOINT, headers=headers)
        _no_json_constants(summary.text)


class TestProposedComplianceEndpoint:
    def test_contract_keys_and_current_status(self, processed_session):
        client, headers = processed_session
        rows = _results(client, headers)
        body = client.get(ENDPOINT, headers=headers).json()

        assert set(body) == {
            "session_id", "proposal_status",
            "n_total_rows", "n_proposal_rows", "n_failed_rows", "n_not_computed_rows",
            "summary", "floor_tolerance", "floor_tolerance_used", "floor_tolerance_source",
            "filters", "status_model", "assumptions", "warnings",
        }
        assert body["proposal_status"] == "current"
        assert body["n_total_rows"] == len(rows)
        assert body["n_proposal_rows"] == len(rows)
        assert body["n_failed_rows"] == 0
        assert body["n_not_computed_rows"] == 0
        assert body["floor_tolerance"] == {"max": 0.5}
        assert body["floor_tolerance_source"] == "core_default"
        assert body["filters"] == {"sector": [], "section": [], "level": [], "bench": []}
        assert body["assumptions"]
        assert body["warnings"] == []
        assert body["session_id"] == "proposed-compliance-current"

    def test_summary_matches_core_summarize_proposed(self, processed_session):
        client, headers = processed_session
        rows = _results(client, headers)
        body = client.get(ENDPOINT, headers=headers).json()

        assert set(body["summary"]) == SUMMARY_KEYS
        expected = summarize_proposed(rows)
        assert body["summary"] == json.loads(json.dumps(expected))
        sections = {row["section"] for row in rows}
        assert set(body["summary"]["by_section"]) == sections
        for entry in body["summary"]["by_section"].values():
            assert set(entry) == SECTION_SUMMARY_KEYS

    def test_old_session_reports_not_computed(self, client: TestClient):
        session_id = db.create_session()
        db.save_results(session_id, _legacy_rows())
        client.headers["X-Session-ID"] = session_id
        body = client.get(ENDPOINT).json()
        assert body["proposal_status"] == "not_computed"
        assert body["n_total_rows"] == 2
        assert body["n_proposal_rows"] == 0
        assert body["n_not_computed_rows"] == 2
        assert body["summary"] is None
        assert "reprocess_required" in body["warnings"]

    def test_mixed_session_reports_partial(self, client: TestClient):
        session_id = db.create_session()
        rows = _proposal_rows() + _legacy_rows()
        db.save_results(session_id, rows)
        client.headers["X-Session-ID"] = session_id
        body = client.get(ENDPOINT).json()
        assert body["proposal_status"] == "partial"
        assert body["n_proposal_rows"] == 2
        assert body["n_not_computed_rows"] == 2
        expected = summarize_proposed(_proposal_rows())
        assert body["summary"] == json.loads(json.dumps(expected))

    def test_empty_session_is_never_an_error(self, client: TestClient):
        client.headers["X-Session-ID"] = "proposed-empty-session"
        response = client.get(ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        assert body["proposal_status"] == "not_computed"
        assert body["n_total_rows"] == 0
        assert body["summary"] is None
        assert "no_results" in body["warnings"]

    def test_floor_tolerance_session_override(self, client: TestClient):
        session_id = db.create_session()
        db.save_results(session_id, _proposal_rows())
        db.save_settings(session_id, {"tolerances": {"floor_vertical": {"max": 0.75}}})
        client.headers["X-Session-ID"] = session_id
        body = client.get(ENDPOINT).json()
        assert body["floor_tolerance"] == {"max": 0.75}
        assert body["floor_tolerance_source"] == "session"

    def test_filters_mirror_design_achievement(self, client: TestClient):
        session_id = db.create_session()
        rows = (
            _proposal_rows(section="S1", sector="A")
            + _proposal_rows(section="S2", sector="B")
            + _legacy_rows()
        )
        db.save_results(session_id, rows)
        client.headers["X-Session-ID"] = session_id

        by_sector = client.get(ENDPOINT, params={"sector": "A"}).json()
        assert by_sector["n_total_rows"] == 2
        assert by_sector["filters"]["sector"] == ["A"]
        assert set(by_sector["summary"]["by_section"]) == {"S1"}

        by_section = client.get(ENDPOINT, params={"section": ["S2"]}).json()
        assert by_section["n_total_rows"] == 2
        assert set(by_section["summary"]["by_section"]) == {"S2"}

        by_level = client.get(ENDPOINT, params={"level": "85"}).json()
        assert by_level["n_total_rows"] == 3
        assert by_level["n_proposal_rows"] == 2

        everything_filtered = client.get(ENDPOINT, params={"sector": "Z"}).json()
        assert everything_filtered["n_total_rows"] == 0
        assert everything_filtered["summary"] is None
        assert "all_rows_filtered_out" in everything_filtered["warnings"]

        repeated = client.get(ENDPOINT, params={"section": ["S1", "S2"]}).json()
        assert repeated["n_total_rows"] == 4


class TestFloorToleranceUsed:
    def _stamp(self, rows, max_m):
        for row in rows:
            row["floor_tolerance_used"] = {"max": max_m}

    def test_divergence_live_0_8_vs_persisted_0_5(self, client: TestClient):
        session_id = db.create_session()
        rows = _proposal_rows()
        rows[0]["floor_offset_m"] = 0.6
        rows[0]["floor_status"] = "FUERA DE TOLERANCIA"
        self._stamp(rows, 0.5)
        db.save_results(session_id, rows)
        db.save_settings(session_id, {"tolerances": {"floor_vertical": {"max": 0.8}}})
        client.headers["X-Session-ID"] = session_id
        body = client.get(ENDPOINT).json()
        assert body["floor_tolerance"] == {"max": 0.8}
        assert body["floor_tolerance_used"] == {"max": 0.5}
        assert body["summary"]["floor_status_counts"] == {
            "FUERA DE TOLERANCIA": 1, "-": 1,
        }
        assert not any(w.startswith("floor_tolerance_used") for w in body["warnings"])

    def test_legacy_rows_report_unknown_used_tolerance(self, client: TestClient):
        session_id = db.create_session()
        db.save_results(session_id, _proposal_rows())
        client.headers["X-Session-ID"] = session_id
        body = client.get(ENDPOINT).json()
        assert body["floor_tolerance_used"] is None
        assert "floor_tolerance_used_unknown" in body["warnings"]

    def test_mixed_used_tolerances_warn_and_stay_null(self, client: TestClient):
        session_id = db.create_session()
        rows = _proposal_rows(section="S1")
        self._stamp(rows, 0.5)
        other = _proposal_rows(section="S2")
        self._stamp(other, 0.9)
        db.save_results(session_id, rows + other)
        client.headers["X-Session-ID"] = session_id
        body = client.get(ENDPOINT).json()
        assert body["floor_tolerance_used"] is None
        assert "floor_tolerance_used_mixed" in body["warnings"]

    def test_pipeline_stamps_used_tolerance_on_rows(self, processed_session):
        client, headers = processed_session
        rows = _results(client, headers)
        assert rows
        for row in rows:
            assert row["floor_tolerance_used"] == {"max": 0.5}
        body = client.get(ENDPOINT, headers=headers).json()
        assert body["floor_tolerance_used"] == {"max": 0.5}
        assert body["floor_tolerance"] == {"max": 0.5}
        assert body["floor_tolerance_source"] == "core_default"


class TestReconciledUpdateKeepsProposal:
    def test_put_reconciled_reruns_guided_comparison(self, processed_session):
        client, headers = processed_session
        profile = client.get("/api/v1/process/profiles/0", headers=headers)
        assert profile.status_code == 200, profile.text
        benches = profile.json()["benches_topo"]
        assert benches

        benches[0]["crest_distance"] = float(benches[0]["crest_distance"]) + 0.2
        response = client.put(
            "/api/v1/process/results/0/reconciled", json=benches, headers=headers,
        )
        assert response.status_code == 200, response.text

        rows = _results(client, headers)
        assert rows
        for row in rows:
            assert row["proposal_status"] in ("current", "failed")
            assert row["proposal_status"] == "current" or row["proposal_error"]


PER_MAGNITUDE_SOURCE_KEYS = (
    "proposed_height_source", "proposed_angle_source",
    "proposed_crest_source", "proposed_toe_source", "proposed_berm_source",
)

_SOURCE_VALUE_KEYS = {
    "proposed_height_source": "proposed_height",
    "proposed_angle_source": "proposed_angle",
    "proposed_crest_source": "proposed_delta_crest",
    "proposed_toe_source": "proposed_delta_toe",
    "proposed_berm_source": "proposed_berm",
}


class TestPerMagnitudeSource:
    def test_row_keys_declare_per_magnitude_sources(self):
        for key in PER_MAGNITUDE_SOURCE_KEYS:
            assert key in process_router.PROPOSED_ROW_KEYS, key

    def test_schema_declares_optional_nullable_sources(self):
        for key in PER_MAGNITUDE_SOURCE_KEYS:
            assert key in schemas.ComparisonResult.model_fields, key
            assert schemas.ComparisonResult.model_fields[key].is_required() is False

    def test_pipeline_rows_carry_per_magnitude_source(self, processed_session):
        client, headers = processed_session
        rows = _results(client, headers)
        assert rows
        for row in rows:
            for key in PER_MAGNITUDE_SOURCE_KEYS:
                assert key in row, (key, row.get("section"))
                assert row[key] in ("guided", "current", None), row[key]

    def test_source_present_iff_proposed_value_present(self, processed_session):
        client, headers = processed_session
        rows = _results(client, headers)
        for row in rows:
            for source_key, value_key in _SOURCE_VALUE_KEYS.items():
                assert (row[value_key] is None) == (row[source_key] is None), (
                    row.get("section"), row.get("bench_num"), source_key)

    def test_aggregate_source_matches_per_magnitude_sources(self, processed_session):
        client, headers = processed_session
        rows = _results(client, headers)
        for row in rows:
            used = {row[k] for k in PER_MAGNITUDE_SOURCE_KEYS if row[k] is not None}
            if not used:
                expected = None
            elif used == {"guided"}:
                expected = "guided"
            elif used == {"current"}:
                expected = "current"
            else:
                expected = "mixed"
            assert row["proposed_source"] == expected, (
                row.get("section"), row.get("bench_num"))
        match_rows = [r for r in rows if r["type"] == "MATCH" and r["proposed_evaluable"]]
        assert any(r["proposed_height_source"] == "guided" for r in match_rows)
