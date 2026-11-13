"""Tests for the T3 write-tool handlers (api.ai_agent_write_handlers).

Real SQLite in a tmp dir (monkeypatched DB_PATH), tiny synthetic
trimesh boxes for the pipeline path, and bounded-output assertions.
No HTTP: handlers are called directly with (session_id, args).
"""
from __future__ import annotations

import inspect
from typing import Any, Dict

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
    assert len(ALL_HANDLERS) == len(TOOL_CATALOG) == 14


def test_read_handlers_stay_strictly_read_only():
    expected_read = {
        name
        for name, spec in TOOL_CATALOG.items()
        if spec.risk is ToolRisk.READ
    }
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
    assert all(isinstance(value, (str, bool)) for value in result.values())


@pytest.mark.asyncio
async def test_export_report_counts_only_own_session_results(temp_db):
    db.save_results(SESSION_B, [{"section": "S-01", "section_status": "CUMPLE"}])
    result = await export_report(SESSION_A, ExportReportArgs(format="word"))
    assert result["ok"] is False
    assert result["error"] == "no_results"
