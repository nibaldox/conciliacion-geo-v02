"""
Export router — Excel, Word, DXF, image ZIP, and PDF exports.

Endpoints:
    GET /export/excel   Export comparison results to formatted Excel
    GET /export/word    Export full Word report with section plots
    GET /export/dxf     Export profiles as 3D DXF with compliance layers
    GET /export/images  Export section plot images as ZIP
    GET /export/pdf     Export unified executive PDF report
    GET /export/levels  Nominal levels per sector for the export filters
"""

import asyncio
import io
import json
import logging
import os
import math
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

import api.database as db
from api.routers.process import (
    _load_mesh_from_db,
    _section_from_dict,
    _dict_to_bench,
    _extraction_to_dict,
)
from api.schemas import ExportFilters
from core import (
    build_reconciled_profile,
    export_results,
    generate_word_report,
)
from core.report_data import ReportData, ReportFilters, build_report_data, filter_comparisons
from core.report_levels import BENCH_TYPES, assign_nominal_levels
from core.section_cutter import azimuth_to_direction
from core.param_extractor import ExtractionResult
from core.reconciliation_summary import compute_section_scores
from core.web_images_report import build_images_zip

# The ReportData-based Word/PDF builders are produced in parallel; the
# import is guarded so the API still starts (and the legacy writer keeps
# working) until those modules land. Tests stub the module attribute.
try:
    from core.web_word_report import build_word_report
except ImportError:  # pragma: no cover — module not present yet
    build_word_report = None

try:
    from core.web_pdf_report import build_pdf_report
except ImportError:  # pragma: no cover — module not present yet
    build_pdf_report = None


# Fase 1.1 cierre §3: reportlab is an optional runtime dependency of the
# PDF report; the import is LOCALISED so the API still starts without it,
# surfacing a clear error only when the PDF endpoint is used.
def _import_pdf_report():
    try:
        from core.pdf_report import generate_pdf_report
        return generate_pdf_report
    except ImportError as exc:  # pragma: no cover — dependency missing
        raise ImportError(
            "La exportación PDF requiere reportlab: instale 'pip install reportlab' "
            "o use requirements.txt / requirements-api.txt."
        ) from exc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])


def _load_excel_builder():
    """Return ``core.web_excel_report.build_excel_report`` or ``None`` if it cannot be imported."""
    try:
        from core.web_excel_report import build_excel_report
    except ImportError:
        logger.warning(
            "core.web_excel_report is unavailable; using the legacy Excel writer",
            exc_info=True,
        )
        return None
    return build_excel_report


def _run_in_executor(func, *args):
    """Schedule a CPU/IO-bound callable on the default executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)


_SPILL_BENCH_FIELDS = (
    "spill_width",
    "effective_berm_width",
    "spill_start_distance",
    "spill_start_elevation",
)


def _parse_filters(raw: Optional[str]) -> ExportFilters:
    if not raw:
        return ExportFilters()
    try:
        data = __import__("json").loads(raw)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"Invalid filters JSON: {exc}") from exc
    try:
        return ExportFilters.model_validate(data)
    except Exception as exc:
        raise HTTPException(400, f"Invalid filter values: {exc}") from exc


VIEW_WINDOW_DISTANCE_MARGIN_M = 10.0
VIEW_WINDOW_HEIGHT_MARGIN_FRACTION = 0.5

SectionKey = Tuple[str, str]
ViewWindow = Tuple[float, float, float, float]


@dataclass
class _LevelSelection:
    """Benches of one section that remain under an active level filter."""

    design: Set[int] = field(default_factory=set)
    topo: Set[int] = field(default_factory=set)
    heights: List[float] = field(default_factory=list)


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bench_number(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _sector_key(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _has_level_filter(report_filters: ReportFilters) -> bool:
    return bool(report_filters.levels) or any(
        selection for _sector, selection in report_filters.levels_by_sector
    )


def _level_filter_active(report_filters: ReportFilters, sector: Any) -> bool:
    """Whether the sector has a non-empty level selection of its own or global."""
    name = str(sector) if sector is not None and str(sector).strip() else ""
    return bool(report_filters.levels_for(name))


def _rescore_sections(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recompute ``section_score`` over the benches that remain in each section."""
    cleared = [{**row, "section_score": None} for row in rows]
    scores = compute_section_scores(cleared)
    return [{**row, "section_score": scores.get(row.get("section"))} for row in cleared]


def _export_rows(
    results: List[Dict[str, Any]], report_filters: ReportFilters
) -> List[Dict[str, Any]]:
    """Filtered comparison rows; scores are recomputed where benches were removed.

    A bench filter rescoring applies to every row; a level filter only to the
    rows of the sectors whose level selection is active.
    """
    filtered = filter_comparisons(results, report_filters)
    if report_filters.benches:
        return _rescore_sections(filtered)
    if not _has_level_filter(report_filters):
        return filtered
    cropped = [
        index
        for index, row in enumerate(filtered)
        if _level_filter_active(report_filters, row.get("sector"))
    ]
    rescored = _rescore_sections([filtered[index] for index in cropped])
    for index, row in zip(cropped, rescored):
        filtered[index] = row
    return filtered


def _level_bench_selection(
    filtered_rows: Optional[List[Dict[str, Any]]],
    report_filters: ReportFilters,
) -> Optional[Dict[SectionKey, _LevelSelection]]:
    """Per-section benches kept by the level filter, or ``None`` without one.

    Only rows of sectors with an active level selection take part.
    """
    if not _has_level_filter(report_filters):
        return None
    selection: Dict[SectionKey, _LevelSelection] = {}
    for row in filtered_rows or []:
        if not _level_filter_active(report_filters, row.get("sector")):
            continue
        key = (str(row.get("section", "")), _sector_key(row.get("sector")))
        entry = selection.setdefault(key, _LevelSelection())
        if row.get("type") != "EXTRA":
            design_number = _bench_number(row.get("bench_num"))
            if design_number is not None:
                entry.design.add(design_number)
        topo_number = _bench_number(row.get("bench_num_topo"))
        if topo_number is not None:
            entry.topo.add(topo_number)
        height = _finite(row.get("height_design"))
        if height is not None and height > 0:
            entry.heights.append(height)
    return selection


def _section_level_selection(
    selection: Optional[Dict[SectionKey, _LevelSelection]],
    report_filters: ReportFilters,
    sector: Any,
) -> Optional[Dict[SectionKey, _LevelSelection]]:
    """Level selection that applies to a section of ``sector``, or ``None``."""
    if selection is None or not _level_filter_active(report_filters, sector):
        return None
    return selection


def _section_selected(
    name: str,
    sector: Any,
    report_filters: ReportFilters,
    filtered_sections: Set[Any],
) -> bool:
    if report_filters.sections and name not in report_filters.sections:
        return False
    if report_filters.sectors and (sector or "") not in report_filters.sectors:
        return False
    if not report_filters.is_empty() and name not in filtered_sections:
        return False
    return True


def _crop_to_level_selection(
    params_design: ExtractionResult,
    params_topo: ExtractionResult,
    selection: Optional[Dict[SectionKey, _LevelSelection]],
    key: SectionKey,
) -> None:
    if selection is None:
        return
    kept = selection.get(key, _LevelSelection())
    params_design.benches = [b for b in params_design.benches if b.bench_number in kept.design]
    params_topo.benches = [b for b in params_topo.benches if b.bench_number in kept.topo]


def _view_window(
    params_design: ExtractionResult,
    params_topo: ExtractionResult,
    selection: Optional[Dict[SectionKey, _LevelSelection]],
    key: SectionKey,
) -> Tuple[Optional[ViewWindow], List[str]]:
    """Window (d_min, d_max, z_min, z_max) around the benches left by the level filter."""
    if selection is None:
        return None, []
    benches = list(params_design.benches) + list(params_topo.benches)
    distances = [
        value
        for bench in benches
        for value in (_finite(bench.crest_distance), _finite(bench.toe_distance))
        if value is not None
    ]
    toes = [v for v in (_finite(b.toe_elevation) for b in benches) if v is not None]
    crests = [v for v in (_finite(b.crest_elevation) for b in benches) if v is not None]
    if not distances or not toes or not crests:
        return None, []

    heights = [
        value
        for value in (_finite(bench.bench_height) for bench in params_design.benches)
        if value is not None and value > 0
    ]
    if not heights:
        heights = list(selection.get(key, _LevelSelection()).heights)
    if not heights:
        heights = [h for entry in selection.values() for h in entry.heights]

    warnings: List[str] = []
    if heights:
        margin = VIEW_WINDOW_HEIGHT_MARGIN_FRACTION * float(median(heights))
    else:
        margin = 0.0
        warnings.append(
            f"Sección {key[0]}: sin altura de banco de diseño válida; la ventana "
            "vertical del perfil no lleva margen."
        )
    window = (
        min(distances) - VIEW_WINDOW_DISTANCE_MARGIN_M,
        max(distances) + VIEW_WINDOW_DISTANCE_MARGIN_M,
        min(toes) - margin,
        max(crests) + margin,
    )
    return window, warnings


def _apply_bench_filters(
    params_list: List[ExtractionResult],
    filters: ExportFilters,
) -> List[ExtractionResult]:
    selected = filters.selected_bench_numbers
    allowed = set(selected) if selected else None
    for params in params_list:
        if allowed is not None:
            params.benches = [b for b in params.benches if b.bench_number in allowed]
        if not filters.show_spill_areas:
            for bench in params.benches:
                for field_name in _SPILL_BENCH_FIELDS:
                    if hasattr(bench, field_name):
                        setattr(bench, field_name, 0.0)
    return params_list


def _filters_header(
    filters: ExportFilters, *, include_result_filters: bool = True,
) -> Dict[str, str]:
    """Echo only filter dimensions supported by the export endpoint."""
    summary = {
        "sectors": filters.sectors if include_result_filters else [],
        "sections": filters.sections if include_result_filters else [],
        "levels": filters.levels if include_result_filters else [],
        "levels_by_sector": filters.levels_by_sector if include_result_filters else {},
        "selected_bench_numbers": filters.selected_bench_numbers,
        "show_spill_areas": filters.show_spill_areas,
        "show_blast_holes": filters.show_blast_holes,
        "blast_tolerance": filters.blast_tolerance,
        "show_reconciled_design": filters.show_reconciled_design,
        "show_reconciled_topo": filters.show_reconciled_topo,
    }
    return {"X-Export-Filters-Applied": json.dumps(summary)}


def _report_filters(filters: ExportFilters) -> ReportFilters:
    """Map the API filter model onto the shared report filter model."""
    return ReportFilters(
        sectors=tuple(filters.sectors),
        sections=tuple(filters.sections),
        levels=tuple(filters.levels),
        benches=tuple(filters.selected_bench_numbers),
        levels_by_sector=tuple(
            (sector, tuple(dict.fromkeys(filters.levels_by_sector[sector])))
            for sector in sorted(filters.levels_by_sector)
        ),
    )


def _load_report_depth_extractions(
    session_id: str, sections: List[Dict[str, Any]]
) -> Dict[tuple[str, str], List[Any]]:
    """Load unfiltered topo benches where section identity is unambiguous."""
    name_counts: Dict[str, int] = {}
    for section in sections:
        name = str(section.get("name", ""))
        name_counts[name] = name_counts.get(name, 0) + 1

    extractions: Dict[tuple[str, str], List[Any]] = {}
    for section in sections:
        name = str(section.get("name", ""))
        sector = section.get("sector")
        sector_key = str(sector).strip() if sector is not None else ""
        if name_counts[name] != 1 or not sector_key:
            continue
        extraction = db.get_extraction(session_id, name, "topo")
        if not extraction:
            continue
        cached_sector = extraction.get("sector")
        if cached_sector and str(cached_sector).strip() != sector_key:
            continue
        extractions[(name, sector_key)] = [
            _dict_to_bench(bench) for bench in extraction.get("benches", [])
        ]
    return extractions


def _report_meta(
    session_id: str,
    project: Optional[str],
    author: Optional[str],
    operation: Optional[str],
    phase: Optional[str],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the report cover meta, including mesh filenames and settings."""
    design_mesh = db.get_mesh(session_id, "design") or {}
    topo_mesh = db.get_mesh(session_id, "topo") or {}
    return {
        "project": project or "",
        "author": author or "",
        "operation": operation or "",
        "phase": phase or "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "design_filename": design_mesh.get("filename", ""),
        "topo_filename": topo_mesh.get("filename", ""),
        "process": settings.get("process") or {},
    }


def _blast_payload(
    settings: Dict[str, Any],
    filters: ExportFilters,
) -> Optional[Dict[str, Any]]:
    """Blast-hole payload, with an empty mapping for explicit exclusion."""
    if not filters.show_blast_holes:
        return {}
    if not settings.get("blast_holes"):
        return None
    return {"holes": settings["blast_holes"], "tolerance": filters.blast_tolerance}


def _row_sectors(rows: Sequence[Mapping[str, Any]]) -> List[str]:
    """Sectors of the rows in order of first appearance; no sector is ``''``."""
    return list(dict.fromkeys(_sector_key(row.get("sector")) for row in rows))


def _heatmap_note(sector: str, outdated: bool) -> str:
    if outdated:
        return (
            f"Mapa de calor{' del sector ' + sector if sector else ''} desactualizado "
            "(cambiaron superficies, secciones o configuración); "
            "recalcúlelo en la vista 3D para incluirlo."
        )
    if sector:
        return (
            f"Mapa de calor no calculado para el sector {sector}; "
            "calcúlelo en la vista 3D para incluirlo."
        )
    return "Mapa de calor no calculado; calcúlelo en la vista 3D para incluirlo."


def _current_sector_heatmap(
    session_id: str, sector: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    from api.routers.meshes import (
        horizontal_deviation_cache_key,
        horizontal_deviation_section_stations,
    )

    stored = db.list_horizontal_deviation_metadata(session_id, sector)
    if not stored:
        return None, _heatmap_note(sector, outdated=False)
    current = []
    for result in stored:
        params = result["params"]
        if params.get("bench_num") is not None:
            continue
        key = horizontal_deviation_cache_key(
            session_id,
            sector,
            params["bench_num"],
            params["longitudinal_step"],
            params["vertical_step"],
        )
        if key is not None and key == result["cache_key"]:
            current.append(result)
    if not current:
        return None, _heatmap_note(sector, outdated=True)
    chosen = db.get_horizontal_deviation_by_key(session_id, sector, current[0]["cache_key"])
    if chosen is None:
        return None, _heatmap_note(sector, outdated=True)
    names, stations = horizontal_deviation_section_stations(
        db.get_sections(session_id), sector
    )
    payload = dict(chosen["payload"])
    payload["section_names"] = names
    payload["section_stations_m"] = stations
    from datetime import datetime, timezone
    try:
        timestamp = datetime.fromisoformat(chosen["created_at"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        computed_at_text = timestamp.astimezone().strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        computed_at_text = None
    return {
        "sector": sector,
        "payload": payload,
        "computed_at_text": computed_at_text,
        "params": chosen["params"],
        "created_at": chosen["created_at"],
        "cache_key": chosen["cache_key"],
    }, None


def _restrict_heatmap_sections(entry: Dict[str, Any], selected: set[str]):
    payload = entry["payload"]
    names = payload.get("section_names", [])
    stations = payload.get("section_stations_m", [])
    pairs = sorted(zip(stations, names))
    intervals = []
    for index, (station, name) in enumerate(pairs):
        if name not in selected or len(pairs) < 2:
            continue
        left = (pairs[index - 1][0] + station) / 2 if index else station - (pairs[1][0] - station) / 2
        right = (pairs[index + 1][0] + station) / 2 if index + 1 < len(pairs) else station + (station - pairs[index - 1][0]) / 2
        if left < right:
            intervals.append((left, right))
    cells = [cell for cell in payload.get("cells", []) if cell.get("station_m") is not None
             and any(left <= cell["station_m"] <= right for left, right in intervals)]
    if not cells:
        return None, "Mapa de calor omitido: sin celdas en las secciones del informe."
    scoped = dict(entry)
    scoped["payload"] = dict(payload, cells=cells, report_station_ranges=intervals)
    selected_names = [name for _, name in pairs if name in selected]
    ranges = ", ".join(f"{left:g}–{right:g} m" for left, right in intervals)
    note = f"Mapa de calor restringido a las secciones del informe: {', '.join(selected_names)} (estaciones {ranges})."
    scoped["scope_note"] = " ".join(filter(None, (entry.get("scope_note"), note)))
    return scoped, None


def _current_heatmaps(
    session_id: str, sectors: Sequence[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Persisted 3D heatmaps still valid for the session state, one per sector.

    Never computes a heatmap: a sector without a stored result whose cache key
    matches the current meshes, sections and configuration yields a scope note.
    """
    heatmaps: List[Dict[str, Any]] = []
    notes: List[str] = []
    for sector in sectors:
        try:
            heatmap, note = _current_sector_heatmap(session_id, sector)
        except Exception:
            logger.exception("Heatmap lookup failed for sector %r", sector)
            heatmap, note = None, _heatmap_note(sector, outdated=False)
        if heatmap is not None:
            heatmaps.append(heatmap)
        if note is not None:
            notes.append(note)
    return heatmaps, notes


def _build_section_geometry(
    session_id: str,
    sections_raw: List[Dict[str, Any]],
    mesh_design: Any,
    mesh_topo: Any,
    filters: ExportFilters,
    report_filters: ReportFilters,
    filtered_sections: set,
    filtered_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Rebuild the per-section geometry list, honouring the active filters.

    Sections excluded by the sector/section/level/bench filters are dropped
    so the report's section detail matches the exported comparison rows.
    The level filter is decided per section sector: where
    ``report_filters.levels_for(sector)`` is not empty the section keeps only
    the benches of its filtered rows (design by ``bench_num``, as-built by
    ``bench_num_topo``) and gets a ``view_window`` around them; any other
    section keeps all its benches and ``view_window`` is ``None``.
    """
    from core import cut_both_surfaces

    level_selection = _level_bench_selection(filtered_rows, report_filters)
    all_data: List[Dict[str, Any]] = []
    for sec_dict in sections_raw:
        sec = _section_from_dict(sec_dict)
        if not _section_selected(sec.name, sec.sector, report_filters, filtered_sections):
            continue
        section_key = (sec.name, _sector_key(sec.sector))

        pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sec)
        design_ext = db.get_extraction(session_id, sec.name, "design")
        topo_ext = db.get_extraction(session_id, sec.name, "topo")

        benches_d = (
            [_dict_to_bench(b) for b in design_ext.get("benches", [])]
            if design_ext
            else []
        )
        benches_t = (
            [_dict_to_bench(b) for b in topo_ext.get("benches", [])] if topo_ext else []
        )

        p_design = ExtractionResult(
            section_name=sec.name,
            sector=sec.sector,
            benches=benches_d,
            inter_ramp_angle=design_ext.get("inter_ramp_angle", 0.0)
            if design_ext
            else 0.0,
            overall_angle=design_ext.get("overall_angle", 0.0) if design_ext else 0.0,
        )
        p_topo = ExtractionResult(
            section_name=sec.name,
            sector=sec.sector,
            benches=benches_t,
            inter_ramp_angle=topo_ext.get("inter_ramp_angle", 0.0) if topo_ext else 0.0,
            overall_angle=topo_ext.get("overall_angle", 0.0) if topo_ext else 0.0,
        )

        section_levels = _section_level_selection(
            level_selection, report_filters, sec.sector
        )
        _crop_to_level_selection(p_design, p_topo, section_levels, section_key)
        p_design, p_topo = _apply_bench_filters([p_design, p_topo], filters)
        view_window, window_warnings = _view_window(
            p_design, p_topo, section_levels, section_key
        )

        all_data.append(
            {
                "section_name": sec.name,
                "sector": sec.sector or "",
                "view_window": view_window,
                "warnings": window_warnings,
                "params_design": p_design,
                "params_topo": p_topo,
                "profile_d": (
                    (pd_prof.distances, pd_prof.elevations)
                    if pd_prof is not None
                    else (np.array([]), np.array([]))
                ),
                "profile_t": (
                    (pt_prof.distances, pt_prof.elevations)
                    if pt_prof is not None
                    else (np.array([]), np.array([]))
                ),
            }
        )
    return all_data


def _build_report_data_sync(
    session_id: str,
    project: Optional[str],
    author: Optional[str],
    operation: Optional[str],
    phase: Optional[str],
    filters: Optional[str],
    *,
    require_meshes: bool = True,
    include_heatmaps: bool = True,
) -> tuple[ReportData, ExportFilters]:
    """Build the filtered ``ReportData`` shared by Excel, Word, PDF and images.

    Loads comparisons, settings, sections and meshes, applies every active
    filter, rebuilds the section geometry and attaches the persisted
    heatmaps that are still current. Runs off the event loop.

    With ``require_meshes=False`` a session whose meshes cannot be loaded
    still gets its report, with empty section geometry and no plan surface.
    """
    export_filters = _parse_filters(filters)

    results = db.get_results(session_id)
    if not results:
        raise HTTPException(400, "No results to export — run the pipeline first")

    settings = db.get_settings(session_id) or {}
    sections_raw = db.get_sections(session_id)
    has_meshes = True
    try:
        mesh_design = _load_mesh_from_db(session_id, "design")
        mesh_topo = _load_mesh_from_db(session_id, "topo")
    except HTTPException as exc:
        if require_meshes:
            raise
        logger.info("Report built without section geometry: %s", exc.detail)
        mesh_design = mesh_topo = None
        has_meshes = False

    report_filters = _report_filters(export_filters)
    filtered = filter_comparisons(results, report_filters)
    filtered_sections = {row.get("section") for row in filtered}

    all_data = (
        _build_section_geometry(
            session_id, sections_raw, mesh_design, mesh_topo,
            export_filters, report_filters, filtered_sections, filtered,
        )
        if has_meshes
        else []
    )

    meta = _report_meta(session_id, project, author, operation, phase, settings)
    plan_inputs = {
        "comparisons": filtered,
        "sections": [_section_from_dict(section) for section in sections_raw],
        "mesh_topo": mesh_topo,
        "grid_ref": settings.get("grid_ref", 0.0),
    }

    heatmaps, heatmap_notes = (
        _current_heatmaps(session_id, _row_sectors(filtered)) if include_heatmaps else ([], [])
    )
    if report_filters.sections:
        restricted = []
        for entry in heatmaps:
            scoped, note = _restrict_heatmap_sections(entry, filtered_sections)
            if scoped is not None:
                restricted.append(scoped)
            if note:
                heatmap_notes.append(note)
        heatmaps = restricted
    if export_filters.selected_bench_numbers:
        for entry in heatmaps:
            note = "El filtro de bancos no se aplica al mapa de calor de pared completa."
            entry["scope_note"] = " ".join(filter(None, (entry.get("scope_note"), note)))
    data = build_report_data(
        results,
        settings,
        report_filters,
        meta,
        section_geometry=all_data,
        plan_inputs=plan_inputs,
        blast=_blast_payload(settings, export_filters),
        depth_extractions=_load_report_depth_extractions(session_id, sections_raw),
        heatmaps=heatmaps,
        heatmap_notes=heatmap_notes,
    )
    return data, export_filters


def _legacy_report_inputs(
    session_id: str, data: ReportData, export_filters: ExportFilters
) -> Dict[str, Any]:
    """Arguments of the legacy Word/PDF writers, taken from the shared model."""
    import pandas as pd

    settings = db.get_settings(session_id) or {}
    plan_inputs = data.plan_inputs or {}
    holes = settings.get("blast_holes") if export_filters.show_blast_holes else None
    return {
        "comparisons": plan_inputs.get("comparisons") or [],
        "all_data": list(data.section_geometry),
        "kwargs": {
            "df_pozos": pd.DataFrame(holes) if holes else None,
            "consolidation_report": (
                (settings.get("blast_upload_meta") or {}).get("consolidation_report")
                if holes else None
            ),
            "crest_toe_tolerance": (settings.get("tolerances") or {}).get("crest_toe_deviation"),
            "sections": plan_inputs.get("sections") or [],
            "mesh_topo": plan_inputs.get("mesh_topo"),
            "grid_ref": plan_inputs.get("grid_ref", 0.0),
        },
    }


# ---------------------------------------------------------------------------
# GET /export/excel
# ---------------------------------------------------------------------------


def _build_excel_payload_sync(
    session_id: str,
    project: Optional[str],
    author: Optional[str],
    operation: Optional[str],
    phase: Optional[str],
    filters: Optional[str],
) -> tuple[io.BytesIO, ExportFilters]:
    """Build the Excel workbook off the event loop.

    Uses the ``ReportData`` builder of ``core.web_excel_report`` over the same
    filtered model as Word and PDF; the legacy writer only runs while that
    module cannot be imported. Returns ``(tmp_path, export_filters)``.
    """
    builder = _load_excel_builder()
    if builder is None:
        return _build_legacy_excel_payload_sync(
            session_id, project, author, operation, phase, filters
        )
    data, export_filters = _build_report_data_sync(
        session_id, project, author, operation, phase, filters, require_meshes=False,
        include_heatmaps=False,
    )
    workbook = builder(data)
    workbook.seek(0)
    return workbook, export_filters


def _build_legacy_excel_payload_sync(
    session_id: str,
    project: Optional[str],
    author: Optional[str],
    operation: Optional[str],
    phase: Optional[str],
    filters: Optional[str],
) -> tuple[io.BytesIO, ExportFilters]:
    """Build the workbook with the legacy writer.

    Returns ``(tmp_path, export_filters)`` so the async handler can wrap the
    result in a ``FileResponse`` once the executor task resolves.
    """
    export_filters = _parse_filters(filters)

    results = db.get_results(session_id)
    if not results:
        raise HTTPException(400, "No results to export — run the pipeline first")

    report_filters = _report_filters(export_filters)
    results = _export_rows(results, report_filters)
    filtered_sections = {row.get("section") for row in results}
    level_selection = _level_bench_selection(results, report_filters)

    settings = db.get_settings(session_id) or {}
    tolerances = settings.get("tolerances", {})

    # Reconstruct ExtractionResult objects from extraction cache
    sections_raw = db.get_sections(session_id)
    params_design: List[ExtractionResult] = []
    params_topo: List[ExtractionResult] = []

    for sec in sections_raw:
        sec_name = sec["name"]
        sector = sec.get("sector", "")
        if not _section_selected(sec_name, sector, report_filters, filtered_sections):
            continue

        design_ext = db.get_extraction(session_id, sec_name, "design")
        if design_ext:
            benches_d = [_dict_to_bench(b) for b in design_ext.get("benches", [])]
            params_design.append(
                ExtractionResult(
                    section_name=sec_name,
                    sector=sector,
                    benches=benches_d,
                    inter_ramp_angle=design_ext.get("inter_ramp_angle", 0.0),
                    overall_angle=design_ext.get("overall_angle", 0.0),
                )
            )
        else:
            params_design.append(ExtractionResult(section_name=sec_name, sector=sector))

        topo_ext = db.get_extraction(session_id, sec_name, "topo")
        if topo_ext:
            benches_t = [_dict_to_bench(b) for b in topo_ext.get("benches", [])]
            params_topo.append(
                ExtractionResult(
                    section_name=sec_name,
                    sector=sector,
                    benches=benches_t,
                    inter_ramp_angle=topo_ext.get("inter_ramp_angle", 0.0),
                    overall_angle=topo_ext.get("overall_angle", 0.0),
                )
            )
        else:
            params_topo.append(ExtractionResult(section_name=sec_name, sector=sector))

        _crop_to_level_selection(
            params_design[-1], params_topo[-1],
            _section_level_selection(level_selection, report_filters, sector),
            (sec_name, _sector_key(sector)),
        )

    params_design = _apply_bench_filters(params_design, export_filters)
    params_topo = _apply_bench_filters(params_topo, export_filters)

    project_info = {
        "project": project or "",
        "author": author or "",
        "operation": operation or "",
        "phase": phase or "",
        "date": __import__("datetime").datetime.now().strftime("%d/%m/%Y"),
    }

    import inspect
    import pandas as pd

    holes = settings.get("blast_holes") if export_filters.show_blast_holes else None
    kwargs = {
        "df_pozos": pd.DataFrame(holes) if holes else None,
        "sections": [_section_from_dict(section) for section in sections_raw],
        "consolidation_report": (settings.get("blast_upload_meta") or {}).get("consolidation_report") if holes else None,
    }
    parameters = inspect.signature(export_results).parameters
    if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        kwargs = {key: value for key, value in kwargs.items() if key in parameters}
    with tempfile.TemporaryDirectory() as directory:
        tmp = os.path.join(directory, "report.xlsx")
        export_results(results, params_design, params_topo, tolerances, tmp, project_info, **kwargs)
        with open(tmp, "rb") as handle:
            workbook = io.BytesIO(handle.read())

    return workbook, export_filters


@router.get("/excel")
async def export_excel(
    request: Request,
    project: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    operation: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    filters: Optional[str] = Query(
        None,
        description="JSON-encoded ExportFilters (camelCase keys). "
        "When omitted, all benches and default toggles apply.",
    ),
):
    """Export comparison results to a formatted Excel workbook.

    The Excel build (DB reads + openpyxl write) runs on the default executor
    so multi-section workbooks don't stall the event loop.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        buffer, export_filters = await _run_in_executor(
            _build_excel_payload_sync,
            session_id,
            project,
            author,
            operation,
            phase,
            filters,
        )

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=Conciliacion_Geotecnica.xlsx",
                     **_filters_header(export_filters, include_result_filters=True)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Excel export failed")
        # Surface a sanitized message; the full stack is in server logs.
        raise HTTPException(500, detail="Excel export failed") from exc


# ---------------------------------------------------------------------------
# GET /export/word
# ---------------------------------------------------------------------------


def _build_word_payload_sync(
    session_id: str,
    project: Optional[str],
    author: Optional[str],
    operation: Optional[str],
    phase: Optional[str],
    filters: Optional[str],
) -> tuple[io.BytesIO, ExportFilters]:
    """Build the Word report bytes off the event loop.

    Loads comparisons, settings and sections, applies every active filter,
    assembles the shared ``ReportData`` and hands it to the report builder.
    Returns ``(buffer, export_filters)`` for the async handler.
    """
    data, export_filters = _build_report_data_sync(
        session_id, project, author, operation, phase, filters
    )

    if build_word_report is not None:
        return build_word_report(data), export_filters

    # Legacy writer while core.web_word_report is unavailable.
    project_info = {
        "project": project or "",
        "author": author or "",
        "operation": operation or "",
        "phase": phase or "",
    }
    tmp = os.path.join(tempfile.gettempdir(), f"report_{session_id[:8]}.docx")
    legacy = _legacy_report_inputs(session_id, data, export_filters)
    generate_word_report(
        legacy["comparisons"], legacy["all_data"], tmp, project_info, **legacy["kwargs"]
    )
    with open(tmp, "rb") as handle:
        return io.BytesIO(handle.read()), export_filters


@router.get("/word")
async def export_word(
    request: Request,
    project: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    operation: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    filters: Optional[str] = Query(
        None,
        description="JSON-encoded ExportFilters (camelCase keys).",
    ),
):
    """Export a full Word report with summary tables and section plots.

    The Word build (trimesh cuts + python-docx writes) runs on the default
    executor so multi-section reports don't stall the event loop.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        buffer, export_filters = await _run_in_executor(
            _build_word_payload_sync,
            session_id,
            project,
            author,
            operation,
            phase,
            filters,
        )

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": "attachment; filename=Informe_Conciliacion.docx",
                **_filters_header(export_filters),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Word export failed")
        raise HTTPException(500, detail="Word export failed") from exc


# ---------------------------------------------------------------------------
# GET /export/dxf — Migrated from api/main.py lines 576-658
# ---------------------------------------------------------------------------


def _build_dxf_payload_sync(session_id: str) -> str:
    """Build the 3D DXF file off the event loop.

    Returns the absolute path to the generated ``.dxf``.
    """
    try:
        mesh_design = _load_mesh_from_db(session_id, "design")
        mesh_topo = _load_mesh_from_db(session_id, "topo")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Error loading meshes: {exc}")

    import ezdxf
    from core import cut_both_surfaces

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Create compliance layers
    doc.layers.add("DISEÑO_CUMPLE", color=3)
    doc.layers.add("DISEÑO_NO_CUMPLE", color=1)
    doc.layers.add("DISEÑO_FUERA_TOL", color=2)
    doc.layers.add("TOPO_CUMPLE", color=3)
    doc.layers.add("TOPO_NO_CUMPLE", color=1)
    doc.layers.add("TOPO_FUERA_TOL", color=2)
    doc.layers.add("CONCILIADO_DISEÑO", color=5)
    doc.layers.add("CONCILIADO_TOPO", color=6)
    doc.layers.add("ETIQUETAS", color=7)

    # Determine per-section compliance status from results
    results = db.get_results(session_id)
    section_status: Dict[str, str] = {}
    for c in results:
        sec_name = c.get("section", "")
        statuses = [
            c.get("height_status", ""),
            c.get("angle_status", ""),
            c.get("berm_status", ""),
        ]
        if sec_name not in section_status:
            section_status[sec_name] = "CUMPLE"
        if "NO CUMPLE" in statuses:
            section_status[sec_name] = "NO CUMPLE"
        elif (
            "FUERA DE TOLERANCIA" in statuses
            and section_status[sec_name] != "NO CUMPLE"
        ):
            section_status[sec_name] = "FUERA DE TOLERANCIA"

    sections_raw = db.get_sections(session_id)
    n_exported = 0

    for i, sec_dict in enumerate(sections_raw):
        sec = _section_from_dict(sec_dict)
        pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sec)
        if not (pd_prof and pt_prof):
            continue

        direction = azimuth_to_direction(sec.azimuth)
        ox, oy = sec.origin[0], sec.origin[1]

        status = section_status.get(sec.name, "CUMPLE")
        suffix = {"NO CUMPLE": "NO_CUMPLE", "FUERA DE TOLERANCIA": "FUERA_TOL"}.get(
            status, "CUMPLE"
        )

        def _to_3d(dists, elevs):
            return [
                (ox + d * direction[0], oy + d * direction[1], float(e))
                for d, e in zip(dists, elevs)
            ]

        def _draw_lines(pts, layer):
            msp.add_polyline3d(pts, dxfattribs={"layer": layer})

        # Design + Topo raw profiles
        d3d = _to_3d(pd_prof.distances, pd_prof.elevations)
        t3d = _to_3d(pt_prof.distances, pt_prof.elevations)
        if len(d3d) > 1:
            _draw_lines(d3d, f"DISEÑO_{suffix}")
        if len(t3d) > 1:
            _draw_lines(t3d, f"TOPO_{suffix}")

        # Reconciled profiles from extraction cache
        design_ext = db.get_extraction(session_id, sec.name, "design")
        topo_ext = db.get_extraction(session_id, sec.name, "topo")

        if design_ext:
            benches_d = [_dict_to_bench(b) for b in design_ext.get("benches", [])]
            if benches_d:
                rd, re = build_reconciled_profile(benches_d)
                if len(rd) > 0:
                    _draw_lines(_to_3d(rd, re), "CONCILIADO_DISEÑO")

        if topo_ext:
            benches_t = [_dict_to_bench(b) for b in topo_ext.get("benches", [])]
            if benches_t:
                rt, ret = build_reconciled_profile(benches_t)
                if len(rt) > 0:
                    _draw_lines(_to_3d(rt, ret), "CONCILIADO_TOPO")

        # Section label
        mid_z = float(max(pd_prof.elevations.max(), pt_prof.elevations.max())) + 3
        msp.add_text(
            f"{sec.name} [{status}]",
            dxfattribs={"height": 2.0, "layer": "ETIQUETAS", "insert": (ox, oy, mid_z)},
        )
        n_exported += 1

    if n_exported == 0:
        raise HTTPException(400, "No profiles could be exported")

    tmp = os.path.join(tempfile.gettempdir(), f"Perfiles_3D_{session_id[:8]}.dxf")
    doc.saveas(tmp)
    return tmp


@router.get("/dxf")
async def export_dxf(request: Request):
    """Export profiles as 3D DXF with compliance layers.

    The ezdxf document build runs on the default executor so multi-section
    exports don't stall the event loop.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)
        tmp = await _run_in_executor(_build_dxf_payload_sync, session_id)
        return FileResponse(tmp, media_type="application/dxf", filename="Perfiles_3D.dxf")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("DXF export failed")
        raise HTTPException(500, detail=f"DXF export failed: {exc}")


# ---------------------------------------------------------------------------
# GET /export/images
# ---------------------------------------------------------------------------


def _build_images_zip_sync(
    session_id: str,
    filters: Optional[str] = None,
) -> tuple[io.BytesIO, ExportFilters]:
    """Build the section-images ZIP off the event loop.

    Same filtered ``ReportData`` as Word, PDF and Excel: one cropped profile
    per filtered section plus the plan view, the status matrix and the scope.
    """
    data, export_filters = _build_report_data_sync(
        session_id, None, None, None, None, filters, include_heatmaps=False
    )
    return build_images_zip(data), export_filters


@router.get("/images")
async def export_images(
    request: Request,
    filters: Optional[str] = Query(
        None,
        description="JSON-encoded ExportFilters (camelCase keys).",
    ),
):
    """Export the filtered section images as a ZIP file.

    Mesh cutting + matplotlib rendering run on the default executor so a
    multi-section ZIP build doesn't stall the event loop.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        zip_buffer, export_filters = await _run_in_executor(
            _build_images_zip_sync, session_id, filters
        )

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=Secciones_Imagenes.zip",
                **_filters_header(export_filters),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Images export failed")
        raise HTTPException(500, detail="Images export failed") from exc


# ---------------------------------------------------------------------------
# GET /export/pdf
# ---------------------------------------------------------------------------


def _build_pdf_payload_sync(
    session_id: str,
    project: Optional[str],
    author: Optional[str],
    operation: Optional[str],
    phase: Optional[str],
    filters: Optional[str] = None,
) -> tuple[io.BytesIO, ExportFilters]:
    """Build the executive PDF bytes off the event loop.

    Mirrors the Word builder: same ``ReportData`` model, same filters, same
    geometry list, so the two reports show identical numbers.
    """
    data, export_filters = _build_report_data_sync(
        session_id, project, author, operation, phase, filters
    )

    if build_pdf_report is not None:
        return build_pdf_report(data), export_filters

    # Legacy writer while core.web_pdf_report is unavailable.
    project_info = {
        "project": project or "N/A",
        "author": author or "N/A",
        "operation": operation or "N/A",
        "phase": phase or "N/A",
    }
    tmp = os.path.join(tempfile.gettempdir(), f"Conciliacion_PDF_{session_id[:8]}.pdf")
    legacy = _legacy_report_inputs(session_id, data, export_filters)
    _import_pdf_report()(
        legacy["comparisons"], legacy["all_data"], tmp, project_info=project_info,
        **legacy["kwargs"],
    )
    with open(tmp, "rb") as handle:
        return io.BytesIO(handle.read()), export_filters


@router.get("/pdf")
async def export_pdf(
    request: Request,
    project: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    operation: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    filters: Optional[str] = Query(None),
):
    """Export a unified executive PDF report.

    The PDF build (reportlab + matplotlib pie chart) runs on the default
    executor so the event loop stays responsive.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)
        buffer, export_filters = await _run_in_executor(
            _build_pdf_payload_sync,
            session_id,
            project,
            author,
            operation,
            phase,
            filters,
        )
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=Informe_Ejecutivo.pdf",
                **_filters_header(export_filters),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("PDF export failed")
        raise HTTPException(500, detail="PDF export failed") from exc


# ---------------------------------------------------------------------------
# GET /export/levels
# ---------------------------------------------------------------------------


def _build_levels_payload_sync(session_id: str) -> Dict[str, Any]:
    """Nominal levels of the session's unfiltered results, grouped by sector."""
    results = db.get_results(session_id)
    if not results:
        raise HTTPException(400, "No results available — run the pipeline first")

    rows = [row for row in results if isinstance(row, Mapping)]
    assignment = assign_nominal_levels(rows)

    levels_by_sector: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if row.get("type") not in BENCH_TYPES:
            continue
        sector = row.get("sector")
        name = "" if sector is None or not str(sector).strip() else str(sector)
        levels_by_sector.setdefault(name, [])
    for level in sorted(assignment.levels, key=lambda item: item.elevation, reverse=True):
        levels_by_sector.setdefault(level.sector, []).append(
            {
                "label": level.label,
                "elevation": level.elevation,
                "min_level": level.min_level,
                "max_level": level.max_level,
                "n_sections": level.n_sections,
                "n_rows": level.n_rows,
            }
        )
    return {
        "sectors": [
            {"sector": sector, "levels": levels}
            for sector, levels in levels_by_sector.items()
        ],
        "warnings": list(assignment.warnings),
    }


@router.get("/levels")
async def export_levels(request: Request):
    """List the nominal levels of every sector, for the export level filter."""
    try:
        session_id = db.get_or_create_session(request.state.session_id)
        return await _run_in_executor(_build_levels_payload_sync, session_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Levels listing failed")
        raise HTTPException(500, detail="Levels listing failed") from exc


# ---------------------------------------------------------------------------
# GET /export/blast-diagnostics — structured processing diagnostics
# ---------------------------------------------------------------------------


def _build_blast_diagnostics_payload_sync(session_id: str) -> str:
    """Build the multi-sheet blast-processing diagnostics workbook.

    Reads the persisted structured payload (``accepted_rows``,
    ``rejected_rows``, ``processing_summary``, ``event_warnings``,
    ``blocking_errors``, ``spatial_diagnostics``,
    ``geometry_configuration``) from the session settings and writes it
    to a temp xlsx via :func:`core.blast_export.export_processing_diagnostics_excel`.
    """
    from core.blast_export import export_processing_diagnostics_excel

    settings = db.get_settings(session_id) or {}
    if not settings.get("blast_upload_meta") and not settings.get("accepted_rows"):
        raise HTTPException(
            404,
            "La sesión no tiene un upload de tronadura persistido.",
        )

    payload = {
        "accepted_rows": settings.get("accepted_rows") or settings.get("blast_holes") or [],
        "rejected_rows": settings.get("rejected_rows") or [],
        "event_warnings": settings.get("event_warnings") or [],
        "blocking_errors": settings.get("blocking_errors") or [],
        "processing_summary": settings.get("processing_summary") or {},
        "geometry_configuration": settings.get("geometry_configuration") or {},
        "spatial_diagnostics": settings.get("spatial_diagnostics") or {},
        "design_surface": settings.get("design_surface") or settings.get("blast_upload_meta", {}).get("design_surface"),
    }
    tmp = tempfile.NamedTemporaryFile(
        prefix=f"blast_diag_{session_id}_",
        suffix=".xlsx",
        delete=False,
    )
    tmp.close()
    export_processing_diagnostics_excel(payload, tmp.name)
    surface = payload.get("design_surface")
    if surface:
        from openpyxl import load_workbook
        workbook = load_workbook(tmp.name)
        sheet = workbook.create_sheet("Superficie_Diseno")
        for key, value in surface.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    sheet.append([f"{key}.{subkey}", subvalue])
            else:
                sheet.append([key, value])
        workbook.save(tmp.name)
    return tmp.name


@router.get("/blast-diagnostics")
async def export_blast_diagnostics(request: Request):
    """Export the structured blast-processing diagnostics workbook.

    Returns a multi-sheet xlsx with: Pozos_Aceptados, Filas_Rechazadas,
    Advertencias, Errores_Bloqueantes, Resumen_Procesamiento,
    Configuracion_Geometrica, Diagnostico_Espacial. Returns HTTP 404
    when the session has no blast upload persisted.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)
        tmp = await _run_in_executor(_build_blast_diagnostics_payload_sync, session_id)
        return FileResponse(
            str(tmp),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="Diagnostico_Tronadura.xlsx",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Blast diagnostics export failed")
        raise HTTPException(500, detail=f"Export failed: {exc}") from exc


@router.get("/blast-rejections")
async def export_blast_rejections(request: Request):
    """Export ONLY the rejected rows (standalone audit artifact)."""
    from core.blast_export import export_rejected_rows_excel

    try:
        session_id = db.get_or_create_session(request.state.session_id)
        settings = db.get_settings(session_id) or {}
        rejected = settings.get("rejected_rows") or []
        config = settings.get("geometry_configuration") or {}
        if not rejected and not settings.get("blast_upload_meta"):
            raise HTTPException(404, "Sin upload persistido para esta sesión.")

        tmp = tempfile.NamedTemporaryFile(
            prefix=f"blast_rej_{session_id}_", suffix=".xlsx", delete=False
        )
        tmp_path = tmp.name
        tmp.close()
        await _run_in_executor(
            lambda: export_rejected_rows_excel(rejected, tmp_path, config=config)
        )
        return FileResponse(
            str(tmp_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="Filas_Rechazadas.xlsx",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Blast rejections export failed")
        raise HTTPException(500, detail=f"Export failed: {exc}") from exc
