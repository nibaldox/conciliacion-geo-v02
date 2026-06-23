"""
Export router — Excel, Word, DXF, and image ZIP exports.

Endpoints:
    GET /export/excel   Export comparison results to formatted Excel
    GET /export/word    Export full Word report with section plots
    GET /export/dxf     Export profiles as 3D DXF with compliance layers
    GET /export/images  Export section plot images as ZIP
"""

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

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
)
from core.section_cutter import azimuth_to_direction
from core.excel_writer import export_results
from core.report_generator import generate_word_report, generate_section_images_zip
from core.param_extractor import ExtractionResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])


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


def _filter_comparisons(
    comparisons: List[Dict[str, Any]],
    filters: ExportFilters,
) -> List[Dict[str, Any]]:
    selected = filters.selected_bench_numbers
    if not selected:
        return comparisons
    allowed = set(selected)
    return [c for c in comparisons if c.get("bench_num") in allowed]


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


def _filters_header(filters: ExportFilters) -> Dict[str, str]:
    summary = {
        "selected_bench_numbers": filters.selected_bench_numbers,
        "show_spill_areas": filters.show_spill_areas,
        "show_blast_holes": filters.show_blast_holes,
        "blast_tolerance": filters.blast_tolerance,
        "show_reconciled_design": filters.show_reconciled_design,
        "show_reconciled_topo": filters.show_reconciled_topo,
    }
    return {"X-Export-Filters-Applied": __import__("json").dumps(summary)}


# ---------------------------------------------------------------------------
# GET /export/excel
# ---------------------------------------------------------------------------


@router.get("/excel")
def export_excel(
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
    """Export comparison results to a formatted Excel workbook."""
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        export_filters = _parse_filters(filters)

        results = db.get_results(session_id)
        if not results:
            raise HTTPException(400, "No results to export — run the pipeline first")

        results = _filter_comparisons(results, export_filters)

        settings = db.get_settings(session_id) or {}
        tolerances = settings.get("tolerances", {})

        # Reconstruct ExtractionResult objects from extraction cache
        sections_raw = db.get_sections(session_id)
        params_design: List[ExtractionResult] = []
        params_topo: List[ExtractionResult] = []

        for sec in sections_raw:
            sec_name = sec["name"]
            sector = sec.get("sector", "")

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

        params_design = _apply_bench_filters(params_design, export_filters)
        params_topo = _apply_bench_filters(params_topo, export_filters)

        project_info = {
            "project": project or "",
            "author": author or "",
            "operation": operation or "",
            "phase": phase or "",
            "date": __import__("datetime").datetime.now().strftime("%d/%m/%Y"),
        }

        tmp = os.path.join(tempfile.gettempdir(), f"conciliacion_{session_id[:8]}.xlsx")
        export_results(results, params_design, params_topo, tolerances, tmp, project_info)

        return FileResponse(
            tmp,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="Conciliacion_Geotecnica.xlsx",
            headers=_filters_header(export_filters),
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


@router.get("/word")
def export_word(
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
    """Export a full Word report with summary tables and section plots."""
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        export_filters = _parse_filters(filters)

        results = db.get_results(session_id)
        if not results:
            raise HTTPException(400, "No results to export — run the pipeline first")

        results = _filter_comparisons(results, export_filters)

        sections_raw = db.get_sections(session_id)
        mesh_design = _load_mesh_from_db(session_id, "design")
        mesh_topo = _load_mesh_from_db(session_id, "topo")

        # Build all_data structure expected by generate_word_report
        from core import cut_both_surfaces

        all_data: List[Dict[str, Any]] = []
        for sec_dict in sections_raw:
            sec = _section_from_dict(sec_dict)
            pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sec)

            # Reconstruct ExtractionResult objects from cache
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

            p_design, p_topo = _apply_bench_filters([p_design, p_topo], export_filters)

            all_data.append(
                {
                    "section_name": sec.name,
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

        project_info = {
            "project": project or "",
            "author": author or "",
            "operation": operation or "",
            "phase": phase or "",
        }

        tmp = os.path.join(tempfile.gettempdir(), f"report_{session_id[:8]}.docx")
        generate_word_report(results, all_data, tmp, project_info)

        return FileResponse(
            tmp,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="Informe_Conciliacion.docx",
            headers=_filters_header(export_filters),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Word export failed")
        raise HTTPException(500, detail=f"Word export failed: {exc}")


# ---------------------------------------------------------------------------
# GET /export/dxf — Migrated from api/main.py lines 576-658
# ---------------------------------------------------------------------------


@router.get("/dxf")
def export_dxf(request: Request):
    """Export profiles as 3D DXF with compliance layers."""
    try:
        session_id = db.get_or_create_session(request.state.session_id)

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
        return FileResponse(tmp, media_type="application/dxf", filename="Perfiles_3D.dxf")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("DXF export failed")
        raise HTTPException(500, detail=f"DXF export failed: {exc}")


# ---------------------------------------------------------------------------
# GET /export/images
# ---------------------------------------------------------------------------


@router.get("/images")
def export_images(request: Request):
    """Export section plot images as a ZIP file."""
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        results = db.get_results(session_id)
        if not results:
            raise HTTPException(400, "No results to export — run the pipeline first")

        sections_raw = db.get_sections(session_id)
        mesh_design = _load_mesh_from_db(session_id, "design")
        mesh_topo = _load_mesh_from_db(session_id, "topo")

        from core import cut_both_surfaces

        # Build all_data structure expected by generate_section_images_zip
        all_data: List[Dict[str, Any]] = []
        for sec_dict in sections_raw:
            sec = _section_from_dict(sec_dict)
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

            all_data.append(
                {
                    "section_name": sec.name,
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

        zip_buffer = generate_section_images_zip(all_data)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=Secciones_Imagenes.zip"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Images export failed")
        raise HTTPException(500, detail=f"Images export failed: {exc}")
