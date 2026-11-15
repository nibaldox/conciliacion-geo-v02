"""Write-tool handlers for the AI agent (plan sections 4.4, 5.3, 8-T3).

Each handler implements exactly one non-READ tool of
``core.ai_v2.agent.catalog`` by reusing the router-internal generation
and persistence helpers — NEVER self-HTTP and NEVER reimplemented
algorithms. ``session_id`` is injected by the loop (middleware
context); it is never read from model arguments.

Section semantics mirror the REST router (``api.routers.sections``):

- ``generate_sections_auto`` APPENDS to the stored sections, mirroring
  ``POST /sections/auto``; colliding names get a ``_{n}`` suffix.
- ``generate_sections_manual`` REPLACES the stored sections, mirroring
  ``POST /sections/manual``; analysis is invalidated only on a real change.
- ``add_section_click`` APPENDS one section, mirroring
  ``POST /sections/click``; colliding names get a ``_{n}`` suffix.
- ``generate_sections_curve`` APPENDS sections along a polyline, mirroring
  ``POST /sections/curve``. The section count is checked before anything is
  generated: more than 200 sections returns ``too_many_sections`` and writes
  nothing; a zero-length polyline returns ``invalid_curve``.
- ``update_section`` and ``delete_section`` mirror ``PUT``/``DELETE
  /sections/{section_id}`` through the router's sync helpers
  (``_update_section_sync``, ``_delete_section_sync``). They use index ids,
  return ``section_id_out_of_range`` / ``no_sections`` for bad ids, and
  invalidate the analysis (update only on a real change).
- Every effective section mutation invalidates the previous analysis
  (``db.invalidate_analysis``). Mutations are rejected with
  ``process_running`` while the session is ``running`` or ``processing``.
- ``run_reconciliation`` reuses ``_run_pipeline_sync`` off the event
  loop, claims the session atomically via ``db.try_begin_process``
  (losing callers get a clean ``process_running`` observation), and
  resets the status to ``idle`` whenever the pipeline does not complete
  so the session can never stay stuck at ``running``.
- ``export_report`` returns download METADATA only — never binary. Its
  ``sector``/``levels_by_sector`` filters are checked against the session's
  real sectors and nominal levels before they reach the router.

The ``api.routers`` helpers are imported at the bottom of this module,
after ``ALL_HANDLERS``: a top-of-module import would create a
collection cycle (``api.routers`` imports ``ai`` at package init, and
``ai.py`` imports ``ALL_HANDLERS`` from this module back).

Aggregated with the strictly read-only ``READ_HANDLERS`` into
``ALL_HANDLERS``, which covers exactly the catalog tools.
"""
from __future__ import annotations

import asyncio
import json
import math
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Sequence

import api.database as db
import numpy as np
from api._async_db import run_db
from api.ai_agent_handlers import READ_HANDLERS
from api.schemas import ExportFilters
from fastapi import HTTPException
from pydantic import ValidationError
from core.ai_v2.agent.catalog import TOOL_CATALOG
from core.ai_v2.agent.models import (
    ExportReportArgs,
    RunReconciliationArgs,
    SectionAutoArgs,
    SectionClickArgs,
    SectionCurveArgs,
    SectionDeleteArgs,
    SectionManualArgs,
    SectionUpdateArgs,
)
from core.report_levels import assign_nominal_levels
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
_MSG_SECTIONS_BUSY = (
    "Hay un proceso de conciliación en ejecución; espera a que termine "
    "antes de modificar las secciones."
)
_MSG_NO_SECTIONS = (
    "No hay secciones definidas: genera secciones antes de procesar."
)
_MSG_NO_RESULTS = (
    "No hay resultados de conciliación: ejecuta el procesamiento "
    "antes de exportar."
)
_MSG_NO_SECTIONS_SESSION = "No hay secciones definidas en esta sesión."
_MSG_SECTION_OUT_OF_RANGE = (
    "El section_id {section_id} no existe: la sesión tiene {count} secciones "
    "(válidos: 0 a {last})."
)
_MSG_SECTION_CHANGED = (
    "La lista de secciones cambió mientras se procesaba el section_id "
    "{section_id}; consulta list_sections antes de reintentar."
)
_EXPORT_NOTE = (
    "El archivo se genera para su descarga en la interfaz; el "
    "contenido binario nunca viaja al modelo."
)
_MSG_DXF_FILTERS = "El DXF no admite filtros ni metadatos."
_MSG_TOO_MANY_FILTERS = (
    "Demasiadas cotas o secciones para un solo informe; acota el filtro."
)
_MSG_LEVEL_SECTOR_LIMIT = "El filtro de cotas admite como máximo 20 sectores."
_MSG_UNKNOWN_SECTOR = (
    "El sector «{sector}» no existe en esta sesión. Sectores válidos: {valid}."
)
_MSG_EMPTY_LEVEL_LIST = (
    "La lista de cotas del sector «{sector}» está vacía: indique al menos "
    "una cota o quite el sector."
)
_MSG_INVALID_LEVEL = (
    "La cota «{label}» no es una cota nominal del sector «{sector}». "
    "Cotas válidas: {valid}."
)
_MSG_NO_SECTOR_LEVELS = (
    "El sector «{sector}» no tiene cotas nominales en esta sesión."
)
_MAX_LEVEL_SECTORS = 20
_MAX_LISTED_SECTORS = 20
_MAX_LISTED_LEVELS = 30
_MAX_FILTER_JSON_CHARS = 4000
_MAX_PAYLOAD_BYTES = 4096
_EXPORT_QUERY_KEYS: Dict[str, tuple[str, ...]] = {
    "excel": ("filters", "project", "author"),
    "word": ("filters", "project", "author"),
    "pdf": ("filters", "project", "author"),
    "images": ("filters",),
    "dxf": (),
}
_MAX_CURVE_SECTIONS = 200
_MIN_CURVE_LENGTH_M = 1e-6
_MSG_TOO_MANY_SECTIONS = (
    "La curva generaría más de 200 secciones; aumenta el espaciamiento."
)
_MSG_INVALID_CURVE = (
    "La curva no tiene longitud: los puntos consecutivos se repiten. "
    "Indica al menos dos puntos distintos."
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


async def _sections_busy_error(session_id: str) -> Dict[str, Any] | None:
    """Return a ``process_running`` observation when sections are locked."""
    try:
        await _ensure_sections_mutable(session_id)
    except HTTPException:
        return {
            "ok": False,
            "error": "process_running",
            "message": _MSG_SECTIONS_BUSY,
        }
    return None


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


def _polyline_length(points: Sequence[Sequence[float]]) -> float:
    vertices = np.asarray(points, dtype=float)
    return float(np.sqrt((np.diff(vertices, axis=0) ** 2).sum(axis=1)).sum())


def _curve_section_count(length: float, spacing: float) -> int:
    """Sections that ``generate_perpendicular_sections`` places on a polyline.

    One section sits at the midpoint when the polyline is shorter than the
    spacing; otherwise one every ``spacing`` metres from ``spacing / 2``, which
    is ``ceil((length - spacing / 2) / spacing)`` sections.
    """
    if length < spacing:
        return 1
    return math.ceil((length - spacing / 2) / spacing)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def add_section_click(session_id: str, args: SectionClickArgs) -> Dict[str, Any]:
    """Append ONE section, mirroring POST /sections/click.

    Rejected with ``process_running`` while the session is busy. A colliding
    name receives a ``_{n}`` suffix and the previous analysis is invalidated.
    """
    busy = await _sections_busy_error(session_id)
    if busy is not None:
        return busy
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
    stored = await _append_sections(session_id, [section])
    return {
        "ok": True,
        "section": _section_to_response(len(stored) - 1, stored[-1]),
        "total": len(stored),
    }


async def generate_sections_auto(
    session_id: str, args: SectionAutoArgs
) -> Dict[str, Any]:
    """Generate sections along a start-end line, APPENDING to the stored ones.

    Mirrors POST /sections/auto: colliding names get a ``_{n}`` suffix and
    the previous analysis is invalidated. Rejected with ``process_running``
    while the session is busy.
    """
    busy = await _sections_busy_error(session_id)
    if busy is not None:
        return busy
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
    await _append_sections(session_id, sections)
    return await _stored_sections_summary(session_id)


async def generate_sections_manual(
    session_id: str, args: SectionManualArgs
) -> Dict[str, Any]:
    """Set sections from explicit definitions, REPLACING the stored ones.

    Mirrors POST /sections/manual. The analysis is invalidated only when the
    resulting list differs from the stored one. Rejected with
    ``process_running`` while the session is busy.
    """
    busy = await _sections_busy_error(session_id)
    if busy is not None:
        return busy
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
    await _replace_sections(session_id, sections)
    return await _stored_sections_summary(session_id)


async def generate_sections_curve(
    session_id: str, args: SectionCurveArgs
) -> Dict[str, Any]:
    """Generate sections across a polyline, APPENDING to the stored ones.

    Mirrors POST /sections/curve through the router's ``_curve_sections``
    helper. The section count is checked before anything is generated: a
    curve that would place more than 200 sections returns ``too_many_sections``
    and writes nothing, and a zero-length polyline returns ``invalid_curve``.
    Colliding names get a ``_{n}`` suffix and the previous analysis is
    invalidated. Rejected with ``process_running`` while the session is busy.
    """
    busy = await _sections_busy_error(session_id)
    if busy is not None:
        return busy
    length = _polyline_length(args.points)
    if length < _MIN_CURVE_LENGTH_M:
        return _error("invalid_curve", _MSG_INVALID_CURVE)
    if _curve_section_count(length, args.spacing) > _MAX_CURVE_SECTIONS:
        return _error("too_many_sections", _MSG_TOO_MANY_SECTIONS)
    sections = await asyncio.to_thread(
        _curve_sections,
        args.points,
        args.spacing,
        args.length,
        args.sector,
        args.length_up,
        args.length_down,
    )
    await _append_sections(session_id, sections)
    summary = await _stored_sections_summary(session_id)
    return {"ok": True, "n_added": len(sections), **summary}


async def _section_index_error(
    session_id: str, section_id: int
) -> tuple[list[dict], Dict[str, Any] | None]:
    """Return the stored sections, or a bounded error for a missing/bad index."""
    stored = await _load_sections(session_id)
    if not stored:
        return stored, _error("no_sections", _MSG_NO_SECTIONS_SESSION)
    if not 0 <= section_id < len(stored):
        return stored, _error(
            "section_id_out_of_range",
            _MSG_SECTION_OUT_OF_RANGE.format(
                section_id=section_id, count=len(stored), last=len(stored) - 1
            ),
        )
    return stored, None


async def update_section(session_id: str, args: SectionUpdateArgs) -> Dict[str, Any]:
    """Edit one section by index, mirroring PUT /sections/{section_id}.

    Only the fields given in ``args`` change; the rest of the stored section
    is kept. The router's sync helper applies the same normalization as the
    REST endpoint, and the analysis is invalidated only on a real change.
    Rejected with ``process_running`` while the session is busy.
    """
    busy = await _sections_busy_error(session_id)
    if busy is not None:
        return busy
    stored, error = await _section_index_error(session_id, args.section_id)
    if error is not None:
        return error
    current = stored[args.section_id]
    body = SectionCreate(
        name=current["name"] if args.name is None else args.name,
        origin=current["origin"] if args.origin is None else args.origin,
        azimuth=current["azimuth"] if args.azimuth is None else args.azimuth,
        length=current["length"] if args.length is None else args.length,
        length_up=(
            current.get("length_up") if args.length_up is None else args.length_up
        ),
        length_down=(
            current.get("length_down") if args.length_down is None else args.length_down
        ),
        sector=current["sector"] if args.sector is None else args.sector,
    )
    try:
        section, changed = await run_db(
            _update_section_sync, session_id, str(args.section_id), body
        )
    except HTTPException:
        return _error(
            "section_id_out_of_range",
            _MSG_SECTION_CHANGED.format(section_id=args.section_id),
        )
    return {"ok": True, "section": section, "invalidated": changed}


async def delete_section(session_id: str, args: SectionDeleteArgs) -> Dict[str, Any]:
    """Delete one section by index, mirroring DELETE /sections/{section_id}.

    Always reached only after the policy confirmed the call. The analysis is
    always invalidated and the later section ids shift down by one. Rejected
    with ``process_running`` while the session is busy.
    """
    busy = await _sections_busy_error(session_id)
    if busy is not None:
        return busy
    _, error = await _section_index_error(session_id, args.section_id)
    if error is not None:
        return error
    try:
        name, total = await run_db(
            _delete_section_sync, session_id, str(args.section_id)
        )
    except HTTPException:
        return _error(
            "section_id_out_of_range",
            _MSG_SECTION_CHANGED.format(section_id=args.section_id),
        )
    return {
        "ok": True,
        "deleted": {"section_id": args.section_id, "name": name},
        "total": total,
        "invalidated": True,
        "note": "Los section_id posteriores bajan en 1.",
    }


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
    body_overrides = {"process": args.model_dump(exclude_none=True)}
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


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "error": code, "message": message}


def _listing(items: Sequence[str], limit: int) -> str:
    shown = ", ".join(items[:limit])
    hidden = len(items) - limit
    return f"{shown} y {hidden} más" if hidden > 0 else shown


def _session_sectors_and_levels(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[set[str], dict[str, list[str]]]:
    """Real sector names of the rows and their nominal labels per sector."""
    sectors: set[str] = set()
    for row in rows:
        raw = row.get("sector")
        if raw is not None and str(raw).strip():
            sectors.add(str(raw))
    labels: dict[str, list[str]] = {}
    for level in assign_nominal_levels(rows).levels:
        labels.setdefault(level.sector, []).append(level.label)
    return sectors, {
        name: list(dict.fromkeys(values)) for name, values in labels.items()
    }


def _filters_summary(
    sectors: Sequence[str],
    sections: Sequence[str],
    levels_by_sector: Mapping[str, Sequence[str]],
    omitted: str,
) -> str:
    parts: list[str] = []
    if sectors:
        label = "Sector" if len(sectors) == 1 else "Sectores"
        parts.append(f"{label} {', '.join(sectors)}")
    if sections:
        label = "sección" if len(sections) == 1 else "secciones"
        parts.append(f"{label} {', '.join(sections)}")
    for sector, labels in levels_by_sector.items():
        parts.append(f"cotas {sector}: {', '.join(labels)}")
    text = "; ".join(parts) if parts else "Sin filtros: informe completo"
    text = text[:1].upper() + text[1:]
    if omitted:
        text = f"{text}. Imágenes no admite {omitted}; se omiten"
    return text


async def export_report(session_id: str, args: ExportReportArgs) -> Dict[str, Any]:
    """Return download metadata for one export format; never bytes.

    ``sector`` and ``levels_by_sector`` are checked against the session's
    real sectors and nominal level labels (``core.report_levels``), the same
    labels ``GET /export/levels`` lists. Accepted filters travel as one
    camelCase ``filters`` document that ``GET /export/{format}`` parses with
    ``api.routers.export._parse_filters``. ``query`` carries only the keys the
    format accepts and is absent when there is nothing to send. Rejections
    are observations; nothing is raised.
    """
    n_results = await run_db(db.get_results_count, session_id)
    if n_results < 1:
        return _error("no_results", _MSG_NO_RESULTS)

    sectors = list(dict.fromkeys(args.sector or []))
    sections = list(dict.fromkeys(args.section or []))
    levels_input = dict(args.levels_by_sector or {})
    project = (args.project or "").strip() or None
    author = (args.author or "").strip() or None
    has_filters = bool(sectors or sections or levels_input)

    if args.format == "dxf" and (has_filters or project or author):
        return _error("invalid_filters", _MSG_DXF_FILTERS)

    omitted: list[str] = []
    if args.format == "images":
        omitted = [
            name for name, value in (("proyecto", project), ("autor", author)) if value
        ]
        project = author = None

    if len(levels_input) > _MAX_LEVEL_SECTORS:
        return _error("invalid_filters", _MSG_LEVEL_SECTOR_LIMIT)

    raw_rows = await run_db(db.get_results, session_id)
    rows = [row for row in raw_rows if isinstance(row, Mapping)]
    if sectors or levels_input:
        valid_sectors, labels_by_sector = _session_sectors_and_levels(rows)
        valid_text = _listing(sorted(valid_sectors), _MAX_LISTED_SECTORS) or "ninguno"
        for name in [*sectors, *levels_input]:
            if name not in valid_sectors:
                return _error(
                    "unknown_sector",
                    _MSG_UNKNOWN_SECTOR.format(sector=name, valid=valid_text),
                )
        for sector, labels in levels_input.items():
            if not labels:
                return _error(
                    "empty_level_list",
                    _MSG_EMPTY_LEVEL_LIST.format(sector=sector),
                )
        for sector, labels in levels_input.items():
            valid_labels = labels_by_sector.get(sector, [])
            for label in labels:
                if label in valid_labels:
                    continue
                if valid_labels:
                    message = _MSG_INVALID_LEVEL.format(
                        label=label,
                        sector=sector,
                        valid=_listing(valid_labels, _MAX_LISTED_LEVELS),
                    )
                else:
                    message = _MSG_NO_SECTOR_LEVELS.format(sector=sector)
                return _error("invalid_level", message)

    levels_by_sector = {
        sector: list(dict.fromkeys(labels)) for sector, labels in levels_input.items()
    }
    export_filters = ExportFilters()
    filters_json: Optional[str] = None
    if has_filters:
        try:
            export_filters = ExportFilters.model_validate(
                {
                    "sector": sectors,
                    "section": sections,
                    "levelsBySector": levels_by_sector,
                }
            )
        except ValidationError:
            return _error("invalid_filters", _MSG_TOO_MANY_FILTERS)
        filters_json = json.dumps(
            export_filters.model_dump(by_alias=True, exclude_defaults=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(filters_json) > _MAX_FILTER_JSON_CHARS:
            return _error("invalid_filters", _MSG_TOO_MANY_FILTERS)

    from api.routers.export import _report_filters
    from core.report_data import filter_comparisons
    from core.report_levels import BENCH_TYPES

    valid_sections = {str(row["section"]) for row in rows if row.get("section") is not None}
    for section in sections:
        if section not in valid_sections:
            valid_text = _listing(sorted(valid_sections), 20) or "ninguna"
            return _error(
                "unknown_section",
                f"La sección «{section}» no existe en esta sesión. Secciones válidas: {valid_text}.",
            )

    filtered = filter_comparisons(rows, _report_filters(export_filters)) if has_filters else rows
    n_rows = sum(1 for row in filtered if row.get("type") in BENCH_TYPES)
    if has_filters and not n_rows:
        return _error(
            "no_rows_for_filters",
            "Los filtros no seleccionan ningún banco; revisa el sector, las secciones y las cotas.",
        )

    candidates: Dict[str, Optional[str]] = {
        "filters": filters_json,
        "project": project,
        "author": author,
    }
    query = {
        key: candidates[key]
        for key in _EXPORT_QUERY_KEYS[args.format]
        if candidates[key]
    }
    payload: Dict[str, Any] = {
        "ok": True,
        "format": args.format,
        "filename": _EXPORT_FILENAMES[args.format],
        "endpoint": f"/api/v1/export/{args.format}",
        "method": "GET",
        "content_type": _EXPORT_MEDIA_TYPES[args.format],
        "note": _EXPORT_NOTE,
        "filters_summary": _filters_summary(
            sectors, sections, levels_by_sector, " ni ".join(omitted)
        ),
        "n_rows": n_rows,
    }
    if query:
        payload["query"] = query
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        return _error("invalid_filters", _MSG_TOO_MANY_FILTERS)
    return payload


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------


_WRITE_HANDLERS: Dict[str, Handler] = {
    "add_section_click": add_section_click,
    "generate_sections_auto": generate_sections_auto,
    "generate_sections_manual": generate_sections_manual,
    "update_section": update_section,
    "delete_section": delete_section,
    "generate_sections_curve": generate_sections_curve,
    "run_reconciliation": run_reconciliation,
    "export_report": export_report,
}

ALL_HANDLERS: Dict[str, Handler] = {**READ_HANDLERS, **_WRITE_HANDLERS}


__all__ = [
    "ALL_HANDLERS",
    "add_section_click",
    "delete_section",
    "export_report",
    "generate_sections_auto",
    "generate_sections_curve",
    "generate_sections_manual",
    "run_reconciliation",
    "update_section",
]


from api.routers.process import _run_pipeline_sync
from api.routers.sections import (
    SectionCreate,
    _append_sections,
    _curve_sections,
    _delete_section_sync,
    _ensure_sections_mutable,
    _get_design_mesh,
    _load_sections,
    _replace_sections,
    _section_to_response,
    _update_section_sync,
)

