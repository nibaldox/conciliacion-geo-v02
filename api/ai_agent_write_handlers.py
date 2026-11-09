"""Write-tool handlers for the AI agent (plan sections 4.4, 5.3, 8-T3).

Each handler implements exactly one non-READ tool of
``core.ai_v2.agent.catalog`` by reusing the router-internal generation
and persistence helpers — NEVER self-HTTP and NEVER reimplemented
algorithms. ``session_id`` is injected by the loop (middleware
context); it is never read from model arguments.

Semantics honored here (verified against the routers):

- ``generate_sections_auto`` / ``generate_sections_manual`` go through
  ``_save_sections`` → ``db.save_sections`` which REPLACES all sections
  of the session; the loop-level confirmation policy gates that.
- ``add_section_click`` APPENDS one section, mirroring
  ``POST /sections/click``.
- ``run_reconciliation`` reuses ``_run_pipeline_sync`` off the event
  loop, claims the session atomically via ``db.try_begin_process``
  (losing callers get a clean ``process_running`` observation), and
  resets the status to ``idle`` whenever the pipeline does not complete
  so the session can never stay stuck at ``running``.
- ``export_report`` returns download METADATA only — never binary.

The ``api.routers`` helpers are imported at the bottom of this module,
after ``ALL_HANDLERS``: a top-of-module import would create a
collection cycle (``api.routers`` imports ``ai`` at package init, and
``ai.py`` imports ``ALL_HANDLERS`` from this module back).

Aggregated with the strictly read-only ``READ_HANDLERS`` into
``ALL_HANDLERS``, which covers exactly the 13 catalog tools.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict

import api.database as db
import numpy as np
from api._async_db import run_db
from api.ai_agent_handlers import READ_HANDLERS
from fastapi import HTTPException
from core.ai_v2.agent.catalog import TOOL_CATALOG
from core.ai_v2.agent.models import (
    ExportReportArgs,
    RunReconciliationArgs,
    SectionAutoArgs,
    SectionClickArgs,
    SectionManualArgs,
)
from core.section_cutter import (
    SectionLine,
    compute_local_azimuth,
    generate_sections_along_crest,
)

Handler = Callable[[str, Any], Awaitable[Dict[str, Any]]]

_MAX_SECTION_SUMMARIES = 30

_EXPORT_FILENAMES: Dict[str, str] = {
    "excel": "Conciliacion_Geotecnica.xlsx",
    "word": "Informe_Conciliacion.docx",
    "pdf": "Informe_Ejecutivo.pdf",
    "dxf": "Perfiles_3D.dxf",
    "images": "Secciones_Imagenes.zip",
}

_EXPORT_MEDIA_TYPES: Dict[str, str] = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "dxf": "application/dxf",
    "images": "application/zip",
}

_MSG_PROCESS_RUNNING = (
    "Ya existe un proceso de conciliación en ejecución; espera a que "
    "termine antes de relanzarlo."
)
_MSG_NO_SECTIONS = (
    "No hay secciones definidas: genera secciones antes de procesar."
)
_MSG_NO_RESULTS = (
    "No hay resultados de conciliación: ejecuta el procesamiento "
    "antes de exportar."
)
_EXPORT_NOTE = (
    "El archivo se genera para su descarga en la interfaz; el "
    "contenido binario nunca viaja al modelo."
)


# ---------------------------------------------------------------------------
# Section summaries (bounded output)
# ---------------------------------------------------------------------------


async def _stored_sections_summary(session_id: str) -> Dict[str, Any]:
    """Compact bounded summary of the session's stored sections."""
    stored = await _load_sections(session_id)
    entries = [
        {
            "id": str(index),
            "name": section.get("name"),
            "origin": section.get("origin"),
            "azimuth": section.get("azimuth"),
            "length": section.get("length"),
        }
        for index, section in enumerate(stored)
    ]
    shown = entries[:_MAX_SECTION_SUMMARIES]
    return {
        "ok": True,
        "n_sections": len(stored),
        "sections_shown": len(shown),
        "sections_truncated": len(shown) < len(entries),
        "sections": shown,
    }


async def _design_mesh_or_error(session_id: str) -> tuple[Any, Dict[str, Any] | None]:
    """Load the design mesh; return (mesh, None) or (None, error dict)."""
    try:
        return await _get_design_mesh(session_id), None
    except HTTPException as exc:
        return None, {
            "ok": False,
            "error": "design_mesh_missing",
            "message": str(exc.detail)[:200],
        }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def add_section_click(session_id: str, args: SectionClickArgs) -> Dict[str, Any]:
    """Append ONE section, mirroring POST /sections/click."""
    if args.az_mode == "auto":
        design_mesh, error = await _design_mesh_or_error(session_id)
        if error is not None or design_mesh is None:
            return error if error is not None else {
                "ok": False,
                "error": "design_mesh_missing",
            }
        origin = np.array(args.origin, dtype=float)
        azimuth = await asyncio.to_thread(compute_local_azimuth, design_mesh, origin)
    else:
        azimuth = args.azimuth if args.azimuth is not None else 0.0
    existing = await _load_sections(session_id)
    section = SectionLine(
        name=f"S-{len(existing) + 1:02d}",
        origin=np.array(args.origin, dtype=float),
        azimuth=float(azimuth),
        length=float(args.length),
        length_up=args.length_up,
        length_down=args.length_down,
        sector=args.sector,
    )
    await run_db(db.save_sections, session_id, existing + [_section_to_dict(section)])
    stored = await _load_sections(session_id)
    return {
        "ok": True,
        "section": _section_to_response(len(stored) - 1, stored[-1]),
        "total": len(stored),
    }


async def generate_sections_auto(
    session_id: str, args: SectionAutoArgs
) -> Dict[str, Any]:
    """Generate sections along a start-end line; REPLACES all sections."""
    design_mesh, error = await _design_mesh_or_error(session_id)
    if error is not None or design_mesh is None:
        return error if error is not None else {
            "ok": False,
            "error": "design_mesh_missing",
        }

    def _generate() -> list[SectionLine]:
        start = np.array(args.start, dtype=float)
        end = np.array(args.end, dtype=float)
        fixed_azimuth: float | None = None
        if args.az_method == "fixed":
            fixed_azimuth = args.fixed_az
        elif args.az_method == "local_slope":
            fixed_azimuth = 0.0
        sections = generate_sections_along_crest(
            design_mesh,
            start,
            end,
            args.n_sections,
            fixed_azimuth,
            args.length,
            args.sector,
            length_up=args.length_up,
            length_down=args.length_down,
        )
        if args.az_method == "local_slope":
            for section in sections:
                section.azimuth = compute_local_azimuth(design_mesh, section.origin)
        return sections

    sections = await asyncio.to_thread(_generate)
    await _save_sections(session_id, sections)
    return await _stored_sections_summary(session_id)


async def generate_sections_manual(
    session_id: str, args: SectionManualArgs
) -> Dict[str, Any]:
    """Set sections from explicit definitions; REPLACES all sections."""
    sections = [
        SectionLine(
            name=definition.name or f"S-{index + 1:02d}",
            origin=np.array(definition.origin, dtype=float),
            azimuth=float(definition.azimuth),
            length=float(definition.length),
            length_up=definition.length_up,
            length_down=definition.length_down,
            sector=definition.sector,
        )
        for index, definition in enumerate(args.sections)
    ]
    await _save_sections(session_id, sections)
    return await _stored_sections_summary(session_id)


async def run_reconciliation(
    session_id: str, args: RunReconciliationArgs
) -> Dict[str, Any]:
    """Run the full pipeline via the router's own sync helper.

    Guarded against concurrent runs with an atomic claim
    (``db.try_begin_process``): the conditional UPDATE lets exactly one
    caller transition the session to ``running``, so the expensive
    pipeline is never launched twice. Whenever the pipeline does not
    complete (rejection or unexpected failure) the status is reset to
    ``idle`` so the session is never left stuck at ``running``.
    """
    claimed = await run_db(db.try_begin_process, session_id)
    if not claimed:
        return {
            "ok": False,
            "error": "process_running",
            "message": _MSG_PROCESS_RUNNING,
        }
    sections_raw = await run_db(db.get_sections, session_id)
    if not sections_raw:
        await run_db(db.update_process_status, session_id, "idle")
        return {
            "ok": False,
            "error": "no_sections",
            "message": _MSG_NO_SECTIONS,
        }
    body_overrides = {
        "process": {
            "resolution": args.resolution,
            "face_threshold": args.face_threshold,
            "berm_threshold": args.berm_threshold,
        }
    }
    try:
        result = await asyncio.to_thread(
            _run_pipeline_sync, session_id, sections_raw, body_overrides
        )
    except HTTPException as exc:
        await run_db(db.update_process_status, session_id, "idle")
        return {
            "ok": False,
            "error": "pipeline_rejected",
            "message": str(exc.detail)[:200],
        }
    except Exception:
        await run_db(db.update_process_status, session_id, "idle")
        raise
    warnings = result.get("profile_warnings") or {}
    n_sections_with_warnings = sum(
        1
        for entry in warnings.values()
        if isinstance(entry, dict) and (entry.get("design") or entry.get("topo"))
    )
    return {
        "ok": True,
        "status": result.get("status"),
        "total_sections": result.get("total_sections"),
        "total_results": result.get("total_results"),
        "n_sections_with_warnings": n_sections_with_warnings,
    }


async def export_report(session_id: str, args: ExportReportArgs) -> Dict[str, Any]:
    """Return download metadata for one export format; never bytes."""
    n_results = await run_db(db.get_results_count, session_id)
    if n_results < 1:
        return {
            "ok": False,
            "error": "no_results",
            "message": _MSG_NO_RESULTS,
        }
    return {
        "ok": True,
        "format": args.format,
        "filename": _EXPORT_FILENAMES[args.format],
        "endpoint": f"/api/v1/export/{args.format}",
        "method": "GET",
        "content_type": _EXPORT_MEDIA_TYPES[args.format],
        "note": _EXPORT_NOTE,
    }


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------


_WRITE_HANDLERS: Dict[str, Handler] = {
    "add_section_click": add_section_click,
    "generate_sections_auto": generate_sections_auto,
    "generate_sections_manual": generate_sections_manual,
    "run_reconciliation": run_reconciliation,
    "export_report": export_report,
}

ALL_HANDLERS: Dict[str, Handler] = {**READ_HANDLERS, **_WRITE_HANDLERS}


__all__ = [
    "ALL_HANDLERS",
    "add_section_click",
    "export_report",
    "generate_sections_auto",
    "generate_sections_manual",
    "run_reconciliation",
]


from api.routers.process import _run_pipeline_sync
from api.routers.sections import (
    _get_design_mesh,
    _load_sections,
    _save_sections,
    _section_to_dict,
    _section_to_response,
)
