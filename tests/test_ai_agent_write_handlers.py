"""Tests for the T3 write-tool handlers (api.ai_agent_write_handlers).

Real SQLite in a tmp dir (monkeypatched DB_PATH), tiny synthetic
trimesh boxes for the pipeline path, and bounded-output assertions.
No HTTP: handlers are called directly with (session_id, args).
"""
from __future__ import annotations

import inspect
import json
from io import BytesIO
from typing import Any, Dict

from openpyxl import load_workbook

import pytest
import trimesh

import api.database as db
import api.ai_agent_write_handlers as write_handlers
from api.ai_agent_handlers import READ_HANDLERS
from api.ai_agent_write_handlers import (
    ALL_HANDLERS,
    add_section_click,
    export_report,
    generate_sections_auto,
    generate_sections_manual,
    run_reconciliation,
)
from api.main import app
from api.routers.export import _parse_filters
from core.ai_v2.agent.catalog import TOOL_CATALOG
from core.ai_v2.agent.models import (
    ExportReportArgs,
    RunReconciliationArgs,
    SectionAutoArgs,
    SectionClickArgs,
    SectionDefinitionArgs,
    SectionManualArgs,
    ToolRisk,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

SESSION_A = "sess-A"
SESSION_B = "sess-B"

_EXPECTED_WRITE_TOOLS = {
    "add_section_click",
    "generate_sections_auto",
    "generate_sections_manual",
    "run_reconciliation",
    "export_report",
}

_EXPORT_FILENAMES = {
    "excel": "Conciliacion_Geotecnica.xlsx",
    "word": "Informe_Conciliacion.docx",
    "pdf": "Informe_Ejecutivo.pdf",
    "dxf": "Perfiles_3D.dxf",
    "images": "Secciones_Imagenes.zip",
}

_EXPORT_MEDIA_TYPES = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "dxf": "application/dxf",
    "images": "application/zip",
}


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "agent-write.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    db.get_or_create_session(SESSION_A)
    db.get_or_create_session(SESSION_B)
    return db_path


def _section_dict(name: str, x: float = 0.0) -> Dict[str, Any]:
    return {
        "name": name,
        "origin": [x, 0.0],
        "azimuth": 0.0,
        "length": 60.0,
        "length_up": None,
        "length_down": None,
        "sector": "Principal",
    }


def _save_box_mesh(session_id: str, mesh_type: str) -> str:
    mesh = trimesh.creation.box(extents=[200.0, 200.0, 50.0])
    payload = trimesh.exchange.stl.export_stl(mesh)
    return db.save_mesh(
        session_id,
        mesh_type,
        f"{mesh_type}.stl",
        data=payload,
        n_vertices=len(mesh.vertices),
        n_faces=len(mesh.faces),
    )


# ---------------------------------------------------------------------------
# Mapping completeness and handler hygiene
# ---------------------------------------------------------------------------


def test_all_handlers_cover_exactly_the_catalog():
    assert set(ALL_HANDLERS.keys()) == set(TOOL_CATALOG.keys())
    assert len(ALL_HANDLERS) == len(TOOL_CATALOG) == 15


def test_read_handlers_stay_strictly_read_only():
    expected_read = {
        name
        for name, spec in TOOL_CATALOG.items()
        if spec.risk is ToolRisk.READ
    }
    assert "get_settings" in expected_read
    assert set(READ_HANDLERS.keys()) == expected_read
    assert expected_read.isdisjoint(_EXPECTED_WRITE_TOOLS)


def test_write_handlers_are_async_two_args():
    for name in _EXPECTED_WRITE_TOOLS:
        handler = ALL_HANDLERS[name]
        assert inspect.iscoroutinefunction(handler), name
        signature = inspect.signature(handler)
        assert len(signature.parameters) == 2, name


def test_write_arg_models_never_carry_session_id():
    write_args = {
        "add_section_click": SectionClickArgs,
        "generate_sections_auto": SectionAutoArgs,
        "generate_sections_manual": SectionManualArgs,
        "run_reconciliation": RunReconciliationArgs,
        "export_report": ExportReportArgs,
    }
    for name, model in write_args.items():
        assert TOOL_CATALOG[name].args_model is model, name
        assert "session_id" not in model.model_fields, name


# ---------------------------------------------------------------------------
# add_section_click: additive + session isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_section_click_appends_without_touching_other_sessions(temp_db):
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    result = await add_section_click(
        SESSION_A,
        SectionClickArgs(origin=[10.0, 5.0], az_mode="manual", azimuth=45.0),
    )
    assert result["ok"] is True
    assert result["total"] == 2
    assert result["section"]["azimuth"] == 45.0
    stored_a = db.get_sections(SESSION_A)
    assert len(stored_a) == 2
    assert stored_a[0]["name"] == "S-01"
    assert stored_a[1]["name"] == "S-02"
    assert db.get_sections(SESSION_B) == []


@pytest.mark.asyncio
async def test_add_section_click_auto_azimuth_needs_design_mesh(temp_db):
    result = await add_section_click(
        SESSION_A,
        SectionClickArgs(origin=[0.0, 0.0], az_mode="auto"),
    )
    assert result == {
        "ok": False,
        "error": "design_mesh_missing",
        "message": "Upload design mesh first",
    }
    assert db.get_sections(SESSION_A) == []


@pytest.mark.asyncio
async def test_add_section_click_auto_uses_local_slope(temp_db):
    _save_box_mesh(SESSION_A, "design")
    result = await add_section_click(
        SESSION_A,
        SectionClickArgs(origin=[10.0, 5.0], az_mode="auto"),
    )
    assert result["ok"] is True
    assert result["total"] == 1


# ---------------------------------------------------------------------------
# generate_sections_auto / manual: REPLACE semantics + bounded summary
# ---------------------------------------------------------------------------


def _seed_analysis(session_id: str) -> None:
    db.save_results(session_id, [{"section": "S-01", "section_status": "CUMPLE"}])
    db.save_extraction(session_id, "S-01", "design", {"points": [[0.0, 0.0]]})
    db.update_process_status(session_id, "complete", 1, 1, 1)


def _assert_analysis_invalidated(session_id: str) -> None:
    assert db.get_results(session_id) == []
    assert db.get_extraction(session_id, "S-01", "design") is None
    assert db.get_process_status(session_id)["status"] == "idle"


def _assert_analysis_intact(session_id: str) -> None:
    assert len(db.get_results(session_id)) == 1
    assert db.get_extraction(session_id, "S-01", "design") is not None
    assert db.get_process_status(session_id)["status"] == "complete"


@pytest.mark.asyncio
async def test_generate_sections_auto_appends_sections(temp_db):
    _save_box_mesh(SESSION_A, "design")
    db.save_sections(SESSION_A, [_section_dict("S-01"), _section_dict("S-02", 10.0)])
    result = await generate_sections_auto(
        SESSION_A,
        SectionAutoArgs(start=[-90.0, 0.0], end=[90.0, 0.0], n_sections=4),
    )
    assert result["ok"] is True
    assert result["n_sections"] == 6
    assert result["sections_shown"] == 6
    assert result["sections_truncated"] is False
    stored = db.get_sections(SESSION_A)
    assert len(stored) == 6
    names = [section["name"] for section in stored]
    assert len(set(names)) == 6
    assert names[:2] == ["S-01", "S-02"]
    assert db.get_sections(SESSION_B) == []


@pytest.mark.asyncio
async def test_generate_sections_auto_invalidates_analysis(temp_db):
    _save_box_mesh(SESSION_A, "design")
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    _seed_analysis(SESSION_A)
    result = await generate_sections_auto(
        SESSION_A,
        SectionAutoArgs(start=[-90.0, 0.0], end=[90.0, 0.0], n_sections=2),
    )
    assert result["ok"] is True
    _assert_analysis_invalidated(SESSION_A)


@pytest.mark.asyncio
async def test_generate_sections_auto_suffixes_colliding_names(temp_db):
    _save_box_mesh(SESSION_A, "design")
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    await generate_sections_auto(
        SESSION_A,
        SectionAutoArgs(start=[-90.0, 0.0], end=[90.0, 0.0], n_sections=1),
    )
    names = [section["name"] for section in db.get_sections(SESSION_A)]
    assert len(names) == len(set(names)) == 2
    assert names[0] == "S-01"


@pytest.mark.asyncio
async def test_generate_sections_manual_invalidates_when_changed(temp_db):
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    _seed_analysis(SESSION_A)
    result = await generate_sections_manual(
        SESSION_A,
        SectionManualArgs(
            sections=[
                SectionDefinitionArgs(
                    origin=[5.0, 0.0], azimuth=90.0, length=80.0, name="M-1"
                )
            ]
        ),
    )
    assert result["ok"] is True
    assert [s["name"] for s in db.get_sections(SESSION_A)] == ["M-1"]
    _assert_analysis_invalidated(SESSION_A)


@pytest.mark.asyncio
async def test_generate_sections_manual_identical_keeps_analysis(temp_db):
    definitions = [
        {"origin": [5.0, 0.0], "azimuth": 90.0, "length": 80.0, "name": "M-1"}
    ]
    await generate_sections_manual(SESSION_A, SectionManualArgs(sections=[SectionDefinitionArgs(**d) for d in definitions]))
    _seed_analysis(SESSION_A)
    result = await generate_sections_manual(
        SESSION_A, SectionManualArgs(sections=[SectionDefinitionArgs(**d) for d in definitions])
    )
    assert result["ok"] is True
    assert result["n_sections"] == 1
    _assert_analysis_intact(SESSION_A)


@pytest.mark.asyncio
async def test_add_section_click_invalidates_analysis(temp_db):
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    _seed_analysis(SESSION_A)
    result = await add_section_click(
        SESSION_A,
        SectionClickArgs(origin=[10.0, 5.0], az_mode="manual", azimuth=45.0),
    )
    assert result["ok"] is True
    _assert_analysis_invalidated(SESSION_A)


@pytest.mark.asyncio
async def test_add_section_click_suffixes_colliding_name(temp_db):
    db.save_sections(SESSION_A, [_section_dict("S-02")])
    result = await add_section_click(
        SESSION_A,
        SectionClickArgs(origin=[10.0, 5.0], az_mode="manual", azimuth=45.0),
    )
    assert result["ok"] is True
    assert result["section"]["name"] == "S-02_1"
    names = [section["name"] for section in db.get_sections(SESSION_A)]
    assert names == ["S-02", "S-02_1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("busy_status", ["running", "processing"])
async def test_busy_session_rejects_every_section_mutation(temp_db, busy_status):
    _save_box_mesh(SESSION_A, "design")
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    _seed_analysis(SESSION_A)
    db.update_process_status(SESSION_A, busy_status, 0, 2)
    before = db.get_sections(SESSION_A)
    manual_defs = [{"origin": [1.0, 0.0], "azimuth": 90.0, "length": 80.0}]

    results = [
        await generate_sections_auto(
            SESSION_A,
            SectionAutoArgs(start=[-90.0, 0.0], end=[90.0, 0.0], n_sections=3),
        ),
        await generate_sections_manual(
            SESSION_A, SectionManualArgs(sections=[SectionDefinitionArgs(**d) for d in manual_defs])
        ),
        await add_section_click(
            SESSION_A,
            SectionClickArgs(origin=[10.0, 5.0], az_mode="manual", azimuth=45.0),
        ),
    ]
    for result in results:
        assert result["ok"] is False
        assert result["error"] == "process_running"
    assert db.get_sections(SESSION_A) == before
    assert len(db.get_results(SESSION_A)) == 1
    assert db.get_extraction(SESSION_A, "S-01", "design") is not None
    assert db.get_process_status(SESSION_A)["status"] == busy_status


@pytest.mark.asyncio
async def test_generate_sections_auto_without_mesh_fails_cleanly(temp_db):
    result = await generate_sections_auto(
        SESSION_A, SectionAutoArgs(start=[0.0, 0.0], end=[1.0, 0.0])
    )
    assert result["ok"] is False
    assert result["error"] == "design_mesh_missing"
    assert db.get_sections(SESSION_A) == []


@pytest.mark.asyncio
async def test_generate_sections_manual_replaces_and_bounds_summary(temp_db):
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    definitions = [
        {
            "origin": [float(index) * 10.0, 0.0],
            "azimuth": 90.0,
            "length": 80.0,
            "sector": f"S{index}",
        }
        for index in range(200)
    ]
    result = await generate_sections_manual(
        SESSION_A, SectionManualArgs(sections=[SectionDefinitionArgs(**d) for d in definitions])
    )
    assert result["ok"] is True
    assert result["n_sections"] == 200
    assert result["sections_shown"] <= 30
    assert result["sections_truncated"] is True
    assert len(result["sections"]) == result["sections_shown"]
    stored = db.get_sections(SESSION_A)
    assert len(stored) == 200
    assert stored[0]["name"] == "S-01"
    assert stored[-1]["name"] == "S-200"
    assert db.get_sections(SESSION_B) == []


# ---------------------------------------------------------------------------
# try_begin_process: atomic claim semantics
# ---------------------------------------------------------------------------


def test_try_begin_process_claims_exactly_once(temp_db):
    assert db.get_process_status(SESSION_A)["status"] == "idle"
    assert db.try_begin_process(SESSION_A) is True
    assert db.get_process_status(SESSION_A)["status"] == "running"
    assert db.try_begin_process(SESSION_A) is False
    assert db.get_process_status(SESSION_A)["status"] == "running"


def test_try_begin_process_accepts_non_busy_statuses(temp_db):
    assert db.try_begin_process(SESSION_A) is True
    db.update_process_status(SESSION_A, "complete", 2, 2, 2)
    assert db.try_begin_process(SESSION_A) is True
    conn = db.get_connection()
    conn.execute("UPDATE sessions SET process_status = NULL WHERE id = ?", (SESSION_A,))
    conn.commit()
    conn.close()
    assert db.try_begin_process(SESSION_A) is True


def test_try_begin_process_is_isolated_per_session(temp_db):
    assert db.try_begin_process(SESSION_A) is True
    assert db.try_begin_process(SESSION_B) is True
    assert db.get_process_status(SESSION_A)["status"] == "running"
    assert db.get_process_status(SESSION_B)["status"] == "running"


# ---------------------------------------------------------------------------
# run_reconciliation: atomic-guard + real pipeline reuse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_reconciliation_rejects_while_process_running(temp_db):
    db.update_process_status(SESSION_A, "running", 0, 2)
    result = await run_reconciliation(SESSION_A, RunReconciliationArgs())
    assert result["ok"] is False
    assert result["error"] == "process_running"
    assert db.get_process_status(SESSION_A)["status"] == "running"
    db.update_process_status(SESSION_A, "processing", 0, 2)
    result = await run_reconciliation(SESSION_A, RunReconciliationArgs())
    assert result["error"] == "process_running"
    assert db.get_process_status(SESSION_A)["status"] == "processing"
    assert db.get_results_count(SESSION_A) == 0


@pytest.mark.asyncio
async def test_run_reconciliation_requires_sections_and_releases_claim(temp_db):
    _save_box_mesh(SESSION_A, "design")
    _save_box_mesh(SESSION_A, "topo")
    result = await run_reconciliation(SESSION_A, RunReconciliationArgs())
    assert result["ok"] is False
    assert result["error"] == "no_sections"
    assert db.get_process_status(SESSION_A)["status"] == "idle"


@pytest.mark.asyncio
async def test_run_reconciliation_executes_router_pipeline(temp_db):
    _save_box_mesh(SESSION_A, "design")
    _save_box_mesh(SESSION_A, "topo")
    db.save_sections(
        SESSION_A, [_section_dict("S-01", -50.0), _section_dict("S-02", 0.0)]
    )
    result = await run_reconciliation(
        SESSION_A, RunReconciliationArgs(resolution=2.0)
    )
    assert result["ok"] is True
    assert result["status"] == "complete"
    assert result["total_sections"] == 2
    assert isinstance(result["total_results"], int)
    assert db.get_results_count(SESSION_A) == result["total_results"]
    status = db.get_process_status(SESSION_A)
    assert status["status"] == "complete"
    assert db.get_results_count(SESSION_B) == 0


# ---------------------------------------------------------------------------
# run_reconciliation: failure paths reset the claimed status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_reconciliation_resets_status_on_pipeline_rejection(
    temp_db, monkeypatch
):
    _save_box_mesh(SESSION_A, "design")
    _save_box_mesh(SESSION_A, "topo")
    db.save_sections(SESSION_A, [_section_dict("S-01")])

    def _raise_http(session_id, sections_raw, body_overrides):
        raise HTTPException(400, "mesh missing")

    monkeypatch.setattr(write_handlers, "_run_pipeline_sync", _raise_http)
    result = await run_reconciliation(SESSION_A, RunReconciliationArgs())
    assert result["ok"] is False
    assert result["error"] == "pipeline_rejected"
    assert "mesh missing" in result["message"]
    assert db.get_process_status(SESSION_A)["status"] == "idle"


@pytest.mark.asyncio
async def test_run_reconciliation_resets_status_on_unexpected_error(
    temp_db, monkeypatch
):
    _save_box_mesh(SESSION_A, "design")
    _save_box_mesh(SESSION_A, "topo")
    db.save_sections(SESSION_A, [_section_dict("S-01")])

    def _raise_runtime(session_id, sections_raw, body_overrides):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(write_handlers, "_run_pipeline_sync", _raise_runtime)
    with pytest.raises(RuntimeError):
        await run_reconciliation(SESSION_A, RunReconciliationArgs())
    assert db.get_process_status(SESSION_A)["status"] == "idle"


# ---------------------------------------------------------------------------
# run_reconciliation: saved detection settings are the default
# ---------------------------------------------------------------------------


@pytest.fixture
def pipeline_calls(monkeypatch):
    calls: list = []

    def _fake_pipeline(session_id, sections_raw, body_overrides):
        calls.append(body_overrides)
        return {
            "status": "complete",
            "total_sections": len(sections_raw),
            "total_results": 0,
            "profile_warnings": {},
        }

    monkeypatch.setattr(write_handlers, "_run_pipeline_sync", _fake_pipeline)
    return calls


@pytest.mark.asyncio
async def test_run_reconciliation_without_args_keeps_saved_detection_settings(
    api_isolated_db, pipeline_calls
):
    db.get_or_create_session(SESSION_A)
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    db.save_settings(
        SESSION_A,
        {"process": {"resolution": 0.2, "face_threshold": 35.0, "berm_threshold": 12.0}},
    )
    result = await run_reconciliation(SESSION_A, RunReconciliationArgs())
    assert result["ok"] is True
    assert pipeline_calls == [{"process": {}}]


@pytest.mark.asyncio
async def test_run_reconciliation_explicit_threshold_overrides_saved(
    api_isolated_db, pipeline_calls
):
    db.get_or_create_session(SESSION_A)
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    db.save_settings(SESSION_A, {"process": {"face_threshold": 35.0}})
    result = await run_reconciliation(
        SESSION_A, RunReconciliationArgs(face_threshold=40)
    )
    assert result["ok"] is True
    assert pipeline_calls == [{"process": {"face_threshold": 40.0}}]


@pytest.mark.asyncio
async def test_run_reconciliation_zero_override_is_not_dropped(
    api_isolated_db, pipeline_calls
):
    db.get_or_create_session(SESSION_A)
    db.save_sections(SESSION_A, [_section_dict("S-01")])
    await run_reconciliation(
        SESSION_A, RunReconciliationArgs(face_threshold=0.0, resolution=2.0)
    )
    assert pipeline_calls == [
        {"process": {"face_threshold": 0.0, "resolution": 2.0}}
    ]


def test_run_reconciliation_args_default_to_no_override():
    assert RunReconciliationArgs().model_dump(exclude_none=True) == {}


@pytest.mark.parametrize(
    "field", ["resolution", "face_threshold", "berm_threshold"]
)
@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf")]
)
def test_run_reconciliation_args_reject_non_finite_values(field, value):
    with pytest.raises(ValidationError):
        RunReconciliationArgs(**{field: value})


@pytest.mark.parametrize(
    "payload",
    [
        {"resolution": 0.0},
        {"resolution": 10.5},
        {"face_threshold": -0.1},
        {"face_threshold": 90.5},
        {"berm_threshold": 91.0},
    ],
)
def test_run_reconciliation_args_keep_existing_bounds(payload):
    with pytest.raises(ValidationError):
        RunReconciliationArgs(**payload)


# ---------------------------------------------------------------------------
# export_report: metadata only, per format, no bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_report_without_results_reports_no_results(temp_db):
    result = await export_report(SESSION_A, ExportReportArgs(format="excel"))
    assert result["ok"] is False
    assert result["error"] == "no_results"


@pytest.mark.asyncio
@pytest.mark.parametrize("format_name", sorted(_EXPORT_FILENAMES))
async def test_export_report_returns_metadata_only(temp_db, format_name):
    db.save_results(SESSION_A, [{"section": "S-01", "section_status": "CUMPLE"}])
    result = await export_report(SESSION_A, ExportReportArgs(format=format_name))
    assert result["ok"] is True
    assert result["format"] == format_name
    assert result["filename"] == _EXPORT_FILENAMES[format_name]
    assert result["endpoint"] == f"/api/v1/export/{format_name}"
    assert result["method"] == "GET"
    assert result["content_type"] == _EXPORT_MEDIA_TYPES[format_name]
    assert isinstance(result["note"], str) and result["note"]
    forbidden = {"bytes", "content", "data", "blob", "payload"}
    assert forbidden.isdisjoint(result.keys())
    assert all(isinstance(value, (str, bool, int)) for value in result.values())


@pytest.mark.asyncio
async def test_export_report_counts_only_own_session_results(temp_db):
    db.save_results(SESSION_B, [{"section": "S-01", "section_status": "CUMPLE"}])
    result = await export_report(SESSION_A, ExportReportArgs(format="word"))
    assert result["ok"] is False
    assert result["error"] == "no_results"


# ---------------------------------------------------------------------------
# export_report filters (T2.2a): sector / section / levels_by_sector / metadata
# ---------------------------------------------------------------------------

_MSG_DXF = "El DXF no admite filtros ni metadatos."
_MSG_TOO_MANY = "Demasiadas cotas o secciones para un solo informe; acota el filtro."
_NO_FILTERS_SUMMARY = "Sin filtros: informe completo"


def _bench_row(
    section: str,
    sector: str,
    bench_num: int,
    level: str,
    *,
    row_type: str = "MATCH",
) -> Dict[str, Any]:
    return {
        "section": section,
        "sector": sector,
        "bench_num": bench_num,
        "level": level,
        "type": row_type,
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
        "section_status": "CUMPLE",
    }


def _seed_filter_results(session_id: str) -> None:
    db.save_results(
        session_id,
        [
            _bench_row("S-02", "Norte", 1, "3065"),
            _bench_row("S-03", "Norte", 2, "3050"),
            _bench_row("S-04", "Sur", 1, "3040"),
        ],
    )


@pytest.mark.asyncio
async def test_export_report_without_filters_keeps_base_payload(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(SESSION_A, ExportReportArgs(format="excel"))
    assert set(result) == {
        "ok",
        "format",
        "filename",
        "endpoint",
        "method",
        "content_type",
        "note",
        "filters_summary",
        "n_rows",
    }
    assert result["n_rows"] == 3
    assert result["filters_summary"] == _NO_FILTERS_SUMMARY
    assert "query" not in result


@pytest.mark.asyncio
async def test_export_report_empty_lists_are_no_filter(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", sector=[], section=[], levels_by_sector={})
    )
    assert result["ok"] is True
    assert "query" not in result
    assert result["filters_summary"] == _NO_FILTERS_SUMMARY


@pytest.mark.asyncio
async def test_export_report_sector_and_section_build_query_filters(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A, ExportReportArgs(format="pdf", sector=["Norte"], section=["S-02"])
    )
    assert result["ok"] is True
    assert set(result["query"]) == {"filters"}
    assert result["query"]["filters"] == '{"sector":["Norte"],"section":["S-02"]}'
    assert result["filters_summary"] == "Sector Norte; sección S-02"
    parsed = _parse_filters(result["query"]["filters"])
    assert parsed.sectors == ["Norte"]
    assert parsed.sections == ["S-02"]
    assert parsed.levels_by_sector == {}


@pytest.mark.asyncio
async def test_export_report_deduplicates_repeated_sectors(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", sector=["Norte", "Norte"])
    )
    assert result["query"]["filters"] == '{"sector":["Norte"]}'


@pytest.mark.asyncio
async def test_export_report_levels_by_sector_round_trip(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A,
        ExportReportArgs(format="excel", levels_by_sector={"Norte": ["3065", "3050"]}),
    )
    assert result["ok"] is True
    assert result["query"]["filters"] == (
        '{"levelsBySector":{"Norte":["3065","3050"]}}'
    )
    assert result["filters_summary"] == "Cotas Norte: 3065, 3050"
    parsed = _parse_filters(result["query"]["filters"])
    assert parsed.levels_by_sector == {"Norte": ["3065", "3050"]}


@pytest.mark.asyncio
async def test_export_report_levels_are_checked_per_sector(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector={"Sur": ["3065"]})
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_level"
    assert "3040" in result["message"]
    assert "3065" not in result["message"].split("Cotas válidas")[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"sector": ["Norte"]},
        {"section": ["S-02"]},
        {"levels_by_sector": {"Norte": ["3065"]}},
        {"project": "Proyecto Norte"},
        {"author": "Ana"},
    ],
    ids=["sector", "section", "levels", "project", "author"],
)
async def test_export_report_dxf_rejects_filters_and_metadata(temp_db, extra):
    _seed_filter_results(SESSION_A)
    result = await export_report(SESSION_A, ExportReportArgs(format="dxf", **extra))
    assert result == {
        "ok": False,
        "error": "invalid_filters",
        "message": _MSG_DXF,
    }


@pytest.mark.asyncio
async def test_export_report_dxf_without_filters_has_no_query(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(SESSION_A, ExportReportArgs(format="dxf"))
    assert result["ok"] is True
    assert "query" not in result
    assert result["filters_summary"] == _NO_FILTERS_SUMMARY


@pytest.mark.asyncio
async def test_export_report_images_omit_project_and_author(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A,
        ExportReportArgs(format="images", sector=["Norte"], project="Proy", author="Ana"),
    )
    assert result["ok"] is True
    assert result["query"] == {"filters": '{"sector":["Norte"]}'}
    assert "author" not in result["query"]
    assert "project" not in result["query"]
    assert "proyecto ni autor" in result["filters_summary"]
    assert "se omiten" in result["filters_summary"]


@pytest.mark.asyncio
async def test_export_report_images_with_author_only_has_no_query(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A, ExportReportArgs(format="images", author="Ana")
    )
    assert result["ok"] is True
    assert "query" not in result
    assert "Imágenes no admite autor" in result["filters_summary"]


@pytest.mark.asyncio
async def test_export_report_excel_project_and_author_go_to_query(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A,
        ExportReportArgs(format="excel", project="Proyecto Norte", author="Ana Pérez"),
    )
    assert result["ok"] is True
    assert result["query"] == {"project": "Proyecto Norte", "author": "Ana Pérez"}
    assert result["filters_summary"] == _NO_FILTERS_SUMMARY


@pytest.mark.asyncio
async def test_export_report_unknown_sector_lists_session_sectors(temp_db):
    _seed_filter_results(SESSION_A)
    by_sector = await export_report(
        SESSION_A, ExportReportArgs(format="excel", sector=["Oeste"])
    )
    assert by_sector["ok"] is False
    assert by_sector["error"] == "unknown_sector"
    assert "Norte" in by_sector["message"] and "Sur" in by_sector["message"]

    by_levels = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector={"Oeste": ["3065"]})
    )
    assert by_levels["ok"] is False
    assert by_levels["error"] == "unknown_sector"


@pytest.mark.asyncio
async def test_export_report_empty_level_list_is_rejected(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector={"Norte": []})
    )
    assert result["ok"] is False
    assert result["error"] == "empty_level_list"


@pytest.mark.asyncio
async def test_export_report_label_9999_is_invalid_level(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector={"Norte": ["9999"]})
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_level"
    assert "3065" in result["message"] and "3050" in result["message"]


@pytest.mark.asyncio
async def test_export_report_exact_toe_level_is_not_nominal(temp_db):
    db.save_results(
        SESSION_A,
        [
            _bench_row("S-02", "Norte", 1, "3065.4"),
            _bench_row("S-03", "Norte", 2, "3050.2"),
        ],
    )
    nominal = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector={"Norte": ["3065"]})
    )
    assert nominal["ok"] is True
    exact = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector={"Norte": ["3065.4"]})
    )
    assert exact["ok"] is False
    assert exact["error"] == "invalid_level"


@pytest.mark.asyncio
async def test_export_report_more_than_20_level_sectors_is_invalid(temp_db):
    _seed_filter_results(SESSION_A)
    levels = {f"Sector {index:02d}": ["3065"] for index in range(21)}
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector=levels)
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_filters"


@pytest.mark.asyncio
async def test_export_report_fifty_by_fifty_levels_is_invalid_filters(temp_db):
    _seed_filter_results(SESSION_A)
    levels = {
        f"Sector {index:02d}": [f"{3000 + 30 * level}" for level in range(50)]
        for index in range(50)
    }
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector=levels)
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_filters"
    assert result["message"]


@pytest.mark.asyncio
async def test_export_report_more_than_50_levels_in_one_sector_is_invalid(temp_db):
    rows = [
        _bench_row(f"S-{level:02d}", "Norte", level + 1, f"{3000 + 30 * level}")
        for level in range(51)
    ]
    db.save_results(SESSION_A, rows)
    labels = [f"{3000 + 30 * level}" for level in range(51)]
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector={"Norte": labels})
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_filters"
    assert result["message"] == _MSG_TOO_MANY


@pytest.mark.asyncio
async def test_export_report_oversized_filter_json_is_invalid_filters(temp_db):
    rows = [
        _bench_row(f"S-{index:02d}", f"Sector {index:02d}", level + 1, f"{3000 + 30 * level}")
        for index in range(20)
        for level in range(50)
    ]
    db.save_results(SESSION_A, rows)
    levels = {
        f"Sector {index:02d}": [f"{3000 + 30 * level}" for level in range(50)]
        for index in range(20)
    }
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", levels_by_sector=levels)
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_filters"
    assert result["message"] == _MSG_TOO_MANY


@pytest.mark.asyncio
async def test_export_report_payload_stays_within_4096_bytes(temp_db):
    long_sectors = [f"Sector {index:02d} " + "x" * 100 for index in range(20)]
    db.save_results(
        SESSION_A, [_bench_row("S-02", sector, 1, "3065") for sector in long_sectors]
    )
    too_big = await export_report(
        SESSION_A, ExportReportArgs(format="excel", sector=long_sectors)
    )
    assert too_big["ok"] is False
    assert too_big["error"] == "invalid_filters"

    fits = await export_report(
        SESSION_A, ExportReportArgs(format="excel", sector=long_sectors[:5])
    )
    assert fits["ok"] is True
    serialized = json.dumps(fits, ensure_ascii=False)
    assert len(serialized.encode("utf-8")) <= 4096
    assert serialized.index("filters_summary") < serialized.index('"query"')


def test_export_report_has_no_flat_level_argument():
    assert "level" not in ExportReportArgs.model_fields
    with pytest.raises(ValidationError):
        ExportReportArgs.model_validate({"format": "excel", "level": ["3065"]})


def test_export_report_argument_bounds_are_enforced():
    with pytest.raises(ValidationError, match="at most 20 items"):
        ExportReportArgs(format="excel", sector=[f"S{i}" for i in range(21)])
    with pytest.raises(ValidationError, match="at most 50 items"):
        ExportReportArgs(format="excel", section=[f"S{i}" for i in range(51)])
    with pytest.raises(ValidationError, match="at least 1 character"):
        ExportReportArgs(format="excel", sector=[""])
    with pytest.raises(ValidationError, match="at most 120 characters"):
        ExportReportArgs(format="excel", sector=["s" * 121])
    with pytest.raises(ValidationError, match="at most 20 characters"):
        ExportReportArgs(format="excel", levels_by_sector={"Norte": ["x" * 21]})
    with pytest.raises(ValidationError, match="at most 120 characters"):
        ExportReportArgs(format="excel", levels_by_sector={"n" * 121: ["3065"]})
    with pytest.raises(ValidationError, match="at most 120 characters"):
        ExportReportArgs(format="excel", project="p" * 121)
    with pytest.raises(ValidationError, match="at most 120 characters"):
        ExportReportArgs(format="excel", author="a" * 121)


@pytest.mark.asyncio
async def test_export_report_query_is_accepted_by_real_excel_route(temp_db):
    _seed_filter_results(SESSION_A)
    result = await export_report(
        SESSION_A,
        ExportReportArgs(
            format="excel",
            sector=["Norte"],
            section=["S-02"],
            levels_by_sector={"Norte": ["3065"]},
            project="Proyecto Norte",
            author="Ana",
        ),
    )
    assert result["ok"] is True
    client = TestClient(app)
    response = client.get(
        "/api/v1/export/excel",
        params=result["query"],
        headers={"X-Session-ID": SESSION_A},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml"
    )


@pytest.fixture
def cross_sector_results(api_isolated_db):
    db.get_or_create_session(SESSION_A)
    db.save_results(SESSION_A, [
        _bench_row("S-01", "A", 1, "3065"),
        _bench_row("S-01", "A", 2, "3050"),
        _bench_row("S-02", "B", 1, "3040"),
        _bench_row("S-01", "A", 3, "3035", row_type="INTER_RAMP"),
    ])


@pytest.mark.asyncio
async def test_export_report_disjoint_real_filters_select_no_rows(cross_sector_results):
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", sector=["A"], section=["S-02"])
    )
    assert result == {
        "ok": False,
        "error": "no_rows_for_filters",
        "message": "Los filtros no seleccionan ningún banco; revisa el sector, las secciones y las cotas.",
    }


@pytest.mark.asyncio
async def test_export_report_unknown_section_lists_valid_sections(cross_sector_results):
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", section=["S-99"])
    )
    assert result["ok"] is False
    assert result["error"] == "unknown_section"
    assert "S-01" in result["message"] and "S-02" in result["message"]


@pytest.mark.asyncio
async def test_export_report_row_count_matches_real_excel_bancos(cross_sector_results):
    result = await export_report(
        SESSION_A, ExportReportArgs(format="excel", sector=["A"], section=["S-01"])
    )
    assert result["ok"] is True
    response = TestClient(app).get(
        "/api/v1/export/excel", params=result["query"],
        headers={"X-Session-ID": SESSION_A},
    )
    assert response.status_code == 200, response.text
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    sheet = workbook["Bancos"]
    assert sheet.max_row - 1 == 2
    assert result["n_rows"] == sheet.max_row - 1
    workbook.close()

