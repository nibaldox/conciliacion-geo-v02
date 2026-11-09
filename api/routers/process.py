"""
Process router — pipeline execution, status, profiles, and interactive editing.

Endpoints:
    POST /process                      Run full cut-extract-compare pipeline
    GET  /process/status               Return current processing status
    GET  /profiles/{section_id}        Return profile data for a section
    PUT  /results/{section_id}/reconciled  Update benches after drag & drop
"""

import asyncio
import json
import logging
import math
import os
import tempfile
import warnings
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import trimesh
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Query, Request

import api.database as db
import api.schemas as schemas
from api._async_db import run_blast_limited
from api.blast_identity import blast_data_status, blast_hole_id, blast_row_ids
from core import (
    load_mesh,
    SectionLine,
    cut_mesh_with_section_diagnostics,
    extract_parameters,
    compare_design_vs_asbuilt,
    compare_design_vs_asbuilt_guided,
    build_reconciled_profile,
    build_reconciled_profile_v2,
    compute_horizontal_deviation,
    summarize_proposed,
)
from core.param_extractor import (
    BenchParams,
    ExtractionResult,
    ReconciledPoint,
)
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.blast_correlation import compute_blast_geotech_correlation, compute_powder_factor
from core.blast_model import fit_powder_factor_damage_model
from core.column_utils import KILOS_CANDIDATES, first_present_column
from core.config import DEFAULTS, DETECTION, TOLERANCES as DEFAULT_TOLERANCES
from core.design_achievement import (
    build_design_achievement_summary,
    build_sector_achievement_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/process", tags=["process"])


def _run_in_executor(func, *args):
    """Schedule a CPU/IO-bound callable on the default executor.

    Keeps handlers ``async def`` while still letting trimesh / pandas /
    numpy / file-IO work run off the event-loop thread.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value, ndigits: int = 3) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return round(f, ndigits) if math.isfinite(f) else None


def _load_mesh_from_db(session_id: str, mesh_type: str) -> trimesh.Trimesh:
    """Load a mesh from the database, cached in memory."""
    mesh_info = db.get_mesh(session_id, mesh_type)
    if not mesh_info:
        raise HTTPException(400, f"{mesh_type} mesh not uploaded")
    try:
        return db.get_trimesh_by_id(mesh_info["id"])
    except Exception as exc:
        raise HTTPException(400, f"Error loading {mesh_type} mesh: {exc}")


def _extraction_to_dict(er: ExtractionResult) -> dict:
    """Convert an ExtractionResult to a JSON-serialisable dict."""
    return {
        "section_name": er.section_name,
        "sector": er.sector,
        "benches": [
            {
                "bench_number": b.bench_number,
                "crest_elevation": b.crest_elevation,
                "crest_distance": b.crest_distance,
                "toe_elevation": b.toe_elevation,
                "toe_distance": b.toe_distance,
                "bench_height": b.bench_height,
                "face_angle": b.face_angle,
                "berm_width": b.berm_width,
                "is_ramp": b.is_ramp,
                "spill_width": b.spill_width,
                "effective_berm_width": b.effective_berm_width,
                "spill_start_distance": b.spill_start_distance,
                "spill_start_elevation": b.spill_start_elevation,
                "floor_elevation": b.floor_elevation,
            }
            for b in er.benches
        ],
        "inter_ramp_angle": er.inter_ramp_angle,
        "overall_angle": er.overall_angle,
        "floor_elevation": er.floor_elevation,
        "crest_elevation_max": er.crest_elevation_max,
    }


def _section_from_dict(d: dict) -> SectionLine:
    """Reconstruct a SectionLine from a database dict."""
    return SectionLine(
        name=d["name"],
        origin=np.array(d["origin"]),
        azimuth=float(d["azimuth"]),
        length=float(d.get("length", 200)),
        sector=d.get("sector", ""),
        length_up=d.get("length_up"),
        length_down=d.get("length_down"),
    )


def _bench_to_dict(b: BenchParams) -> dict:
    """Serialise a single BenchParams."""
    return {
        "bench_number": b.bench_number,
        "crest_elevation": b.crest_elevation,
        "crest_distance": b.crest_distance,
        "toe_elevation": b.toe_elevation,
        "toe_distance": b.toe_distance,
        "bench_height": round(b.bench_height, 2),
        "face_angle": round(b.face_angle, 1),
        "berm_width": round(b.berm_width, 2),
        "is_ramp": b.is_ramp,
        "spill_width": round(b.spill_width, 2),
        "effective_berm_width": round(b.effective_berm_width, 2),
        "spill_start_distance": round(b.spill_start_distance, 2),
        "spill_start_elevation": round(b.spill_start_elevation, 2),
        "floor_elevation": b.floor_elevation,
    }


def _dict_to_bench(d: dict) -> BenchParams:
    """Deserialise a dict into a BenchParams."""
    return BenchParams(
        bench_number=int(d.get("bench_number", 0)),
        crest_elevation=float(d["crest_elevation"]),
        crest_distance=float(d["crest_distance"]),
        toe_elevation=float(d["toe_elevation"]),
        toe_distance=float(d["toe_distance"]),
        bench_height=float(d.get("bench_height", 0)),
        face_angle=float(d.get("face_angle", 0)),
        berm_width=float(d.get("berm_width", 0)),
        is_ramp=bool(d.get("is_ramp", False)),
        spill_width=float(d.get("spill_width", 0.0)),
        effective_berm_width=float(d.get("effective_berm_width", 0.0)),
        spill_start_distance=float(d.get("spill_start_distance", 0.0)),
        spill_start_elevation=float(d.get("spill_start_elevation", 0.0)),
        floor_elevation=float(d.get("floor_elevation", 0.0)),
    )


def _get_session_id(request_state) -> str:
    """Extract or create a session ID from the request state."""
    return db.get_or_create_session(getattr(request_state, "session_id", None))


def _reconciled_point_to_dict(p: ReconciledPoint) -> dict:
    """Serialise a ReconciledPoint for JSON transport."""
    return {
        "distance": round(float(p.distance), 3),
        "elevation": round(float(p.elevation), 3),
        "bench_number": int(p.bench_number),
        "segment_type": str(p.segment_type),
        "source": str(p.source),
    }


def _reconciled_profile_to_dict(prof) -> dict:
    """Serialise a ReconciledProfile (distances, elevations, segments)."""
    return {
        "distances": prof.distances.tolist() if len(prof.distances) > 0 else [],
        "elevations": prof.elevations.tolist() if len(prof.elevations) > 0 else [],
        "segments": [_reconciled_point_to_dict(p) for p in prof.points],
    }


def _legacy_reconciled_to_dict(
    benches,
    floor_elevation: float | None = None,
    floor_point: tuple[float, float] | None = None,
    floor_resolved_from_profile: bool = False,
) -> dict:
    """Streamlit-equivalent reconciled polyline as flat ``(distances, elevations)``
    arrays.

    Calls the legacy ``build_reconciled_profile`` path for the sorted
    crest/toe polyline. When the rich profile resolved a floor point from
    source geometry, that same point is inserted before sorting.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        distances, elevations = build_reconciled_profile(
            benches,
            floor_elevation=None if floor_resolved_from_profile else floor_elevation,
        )
    if floor_point is not None and len(distances) > 0:
        floor_d, floor_z = map(float, floor_point)
        existing = np.isclose(distances, floor_d, atol=1e-9) & np.isclose(
            elevations, floor_z, atol=1e-9,
        )
        if not np.any(existing):
            distances = np.append(distances, floor_d)
            elevations = np.append(elevations, floor_z)
            order = np.argsort(distances, kind="stable")
            distances = distances[order]
            elevations = elevations[order]
    return {
        "distances": distances.tolist(),
        "elevations": elevations.tolist(),
    }


# ---------------------------------------------------------------------------
# Proposed compliance (wave 10) — additive guided_* / proposed_* row fields
# ---------------------------------------------------------------------------

PROPOSED_ROW_KEYS = frozenset({
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
    "height_score", "angle_score", "berm_score",
    "bench_score", "section_score", "section_status",
    "spill_width", "effective_berm", "effective_berm_status", "berm_dev",
    "floor_tolerance_used",
    "proposal_status", "proposal_error",
})

_PROPOSAL_ERROR_MAXLEN = 200


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _finalize_proposal_rows(
    rows: List[Dict[str, Any]], ok: bool, error: Optional[str],
    floor_tolerance_used: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Stamp ``proposal_status`` on comparison rows and make them JSON-strict.

    ``ok=True`` rows come straight from
    :func:`core.compare_design_vs_asbuilt_guided` (they already carry the
    guided/proposed fields); ``ok=False`` rows are the untouched official
    rows of :func:`core.compare_design_vs_asbuilt` and only gain
    ``proposal_status='failed'`` plus a summarized ``proposal_error``.
    Non-finite floats among the additive keys are replaced with ``None`` so
    strict JSON never sees NaN/Infinity. ``floor_tolerance_used`` records
    the floor tolerance in effect when the row's ``floor_status`` (and the
    persisted counts derived from it) were computed, so a later settings
    change cannot be mistaken for a re-evaluation.
    """
    error_text = None
    if error is not None:
        error_text = str(error)[:_PROPOSAL_ERROR_MAXLEN] or "guided comparison failed"
    stamp = dict(floor_tolerance_used) if floor_tolerance_used else None
    out: List[Dict[str, Any]] = []
    for row in rows:
        new = dict(row)
        for key in PROPOSED_ROW_KEYS:
            if key in new:
                new[key] = _json_safe(new[key])
        new["floor_tolerance_used"] = dict(stamp) if stamp else None
        new["proposal_status"] = "current" if ok else "failed"
        if not ok:
            new["proposal_error"] = error_text
        out.append(new)
    return out


def _guided_comparison(
    p_design, p_topo, tolerances, asbuilt_profile,
):
    """Run the guided comparison, falling back to the official one per section.

    ``asbuilt_profile`` is ``(distances, elevations)`` from the section's
    already-computed as-built :class:`~core.section_cutter.ProfileResult`, or
    ``None`` when no profile is available. Returns the finalized rows
    (official values always present; ``proposal_status`` per row).
    """
    used_floor_tolerance = _resolved_floor_tolerance(tolerances)[0]
    reason = None
    if asbuilt_profile is not None:
        distances, elevations = asbuilt_profile
        try:
            rows = compare_design_vs_asbuilt_guided(
                p_design, p_topo, tolerances, distances, elevations,
            )
            return _finalize_proposal_rows(
                rows, True, None, used_floor_tolerance,
            )
        except Exception as exc:
            logger.warning("Guided comparison failed: %s", exc)
            reason = str(exc) or exc.__class__.__name__
    else:
        reason = "asbuilt profile unavailable"
    rows = compare_design_vs_asbuilt(p_design, p_topo, tolerances)
    return _finalize_proposal_rows(rows, False, reason, used_floor_tolerance)


# ---------------------------------------------------------------------------
# POST /process — Run full pipeline
# ---------------------------------------------------------------------------


def _run_pipeline_sync(
    session_id: str,
    sections_raw: list,
    body_overrides: dict,
) -> dict:
    """Run the full cut → extract → compare pipeline off the event loop.

    Synchronous helper invoked via ``run_in_executor`` from
    :func:`run_process`. Performs the same work the original sync handler
    did: load meshes, merge settings, run per-section work in a
    ``ThreadPoolExecutor``, persist extractions, and return a result dict
    ready for JSON encoding.
    """
    # Load both meshes (will raise 400 if missing)
    try:
        mesh_design = _load_mesh_from_db(session_id, "design")
        mesh_topo = _load_mesh_from_db(session_id, "topo")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Error loading meshes: {exc}")

    # Merge settings: DB defaults ← body overrides
    settings = db.get_settings(session_id) or {}
    process_cfg = settings.get("process", {})
    tolerances = settings.get("tolerances", {})

    process_cfg.update(body_overrides.get("process", {}))
    tolerances.update(body_overrides.get("tolerances", {}))

    # Fall back to DEFAULT_TOLERANCES if no tolerances were provided
    if not tolerances:
        tolerances = {
            "bench_height": DEFAULT_TOLERANCES.bench_height,
            "face_angle": DEFAULT_TOLERANCES.face_angle,
            "berm_width": DEFAULT_TOLERANCES.berm_width,
            "inter_ramp_angle": DEFAULT_TOLERANCES.inter_ramp_angle,
            "overall_angle": DEFAULT_TOLERANCES.overall_angle,
        }

    resolution = process_cfg.get("resolution", 0.1)
    face_threshold = process_cfg.get("face_threshold", DETECTION.face_threshold)
    berm_threshold = process_cfg.get("berm_threshold", DETECTION.berm_threshold)

    # Reconstruct SectionLine objects
    sections = [_section_from_dict(s) for s in sections_raw]

    # Mark processing started
    db.update_process_status(session_id, "processing", 0, len(sections))

    # Allocate result containers
    params_design_list: List[Optional[ExtractionResult]] = [None] * len(sections)
    params_topo_list: List[Optional[ExtractionResult]] = [None] * len(sections)
    comparison_results: List[Dict[str, Any]] = []

    def _process_section(args: tuple):
        """Worker: cut → extract → compare for a single section."""
        idx, sec = args
        try:
            design_cut = cut_mesh_with_section_diagnostics(mesh_design, sec)
            topo_cut = cut_mesh_with_section_diagnostics(mesh_topo, sec)
            pd_prof = design_cut.profile
            pt_prof = topo_cut.profile
            if pd_prof is not None:
                p_d = extract_parameters(
                    pd_prof.distances,
                    pd_prof.elevations,
                    sec.name,
                    sec.sector,
                    resolution,
                    face_threshold,
                    berm_threshold,
                )
            else:
                p_d = ExtractionResult(section_name=sec.name, sector=sec.sector)
            if pt_prof is not None:
                p_t = extract_parameters(
                    pt_prof.distances,
                    pt_prof.elevations,
                    sec.name,
                    sec.sector,
                    resolution,
                    face_threshold,
                    berm_threshold,
                )
            else:
                p_t = ExtractionResult(section_name=sec.name, sector=sec.sector)
            if pd_prof is not None and pt_prof is not None:
                comps = _guided_comparison(
                    p_d, p_t, tolerances,
                    (pt_prof.distances, pt_prof.elevations),
                )
            else:
                comps = []
            profile_warnings = {
                "design": list(design_cut.warnings),
                "topo": list(topo_cut.warnings),
            }
            return idx, sec, p_d, p_t, comps, profile_warnings
        except Exception as exc:
            logger.exception("Section %s processing failed: %s", sec.name, exc)
            p_d_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
            p_t_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
            return idx, sec, p_d_empty, p_t_empty, [], {
                "design": ["section_processing_error"],
                "topo": ["section_processing_error"],
            }

    # Execute in parallel (inside the executor thread, so this pool only
    # uses background threads; no event-loop blocking).
    completed = 0
    section_profile_warnings: Dict[str, Dict[str, List[str]]] = {}
    with ThreadPoolExecutor() as executor:
        for idx, sec, p_d, p_t, comps, profile_warnings in executor.map(
            _process_section, enumerate(sections)
        ):
            params_design_list[idx] = p_d
            params_topo_list[idx] = p_t
            comparison_results.extend(comps)
            section_profile_warnings[sec.name] = profile_warnings
            completed += 1
            db.update_process_status(session_id, "processing", completed, len(sections))

    # Persist results
    # Save extraction cache for each section
    for idx, sec in enumerate(sections):
        if params_design_list[idx] is not None:
            db.save_extraction(
                session_id,
                sec.name,
                "design",
                _extraction_to_dict(params_design_list[idx]),
            )
        if params_topo_list[idx] is not None:
            db.save_extraction(
                session_id,
                sec.name,
                "topo",
                _extraction_to_dict(params_topo_list[idx]),
            )

    # Make comparison results JSON-safe before saving
    safe_results = []
    for c in comparison_results:
        safe_c = {k: v for k, v in c.items() if k not in ("bench_design", "bench_real")}
        safe_results.append(safe_c)

    db.save_results(session_id, safe_results)
    db.update_process_status(session_id, "complete", len(sections), len(sections))

    return {
        "status": "complete",
        "total_sections": len(sections),
        "total_results": len(comparison_results),
        "profile_warnings": section_profile_warnings,
    }


@router.post("")
async def run_process(request: Request, body: Optional[schemas.ProcessSettings] = None):
    """
    Run the full geotechnical reconciliation pipeline:
    cut all sections → extract parameters → compare design vs as-built.

    Uses ThreadPoolExecutor for parallel section processing.
    Results and extraction cache are persisted to the database.

    The bulk of the work (mesh loading, per-section cut/extract/compare,
    DB persistence) is executed off the event loop via ``run_in_executor``.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        # Validate preconditions
        sections_raw = db.get_sections(session_id)
        if not sections_raw:
            raise HTTPException(400, "Load sections first")

        body_overrides: dict = {}
        if body is not None:
            body_dict = body.model_dump() if hasattr(body, "model_dump") else body.dict()
            body_overrides = body_dict

        return await _run_in_executor(
            _run_pipeline_sync, session_id, sections_raw, body_overrides
        )
    except HTTPException as exc:
        logger.warning("Process rejected: status=%s detail=%s", exc.status_code, exc.detail)
        raise
    except Exception as exc:
        logger.exception("Run process failed")
        raise HTTPException(500, detail=f"Run process failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/status
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status(request: Request):
    """Return the current processing status for the session.

    Three sequential DB round-trips run on the default executor so the
    event loop isn't blocked while the status + result count are read.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )

        def _fetch_status():
            raw = db.get_process_status(session_id)
            n_results = db.get_results_count(session_id)
            return schemas.ProcessStatus(
                status=raw.get("status", "idle"),
                current_section=raw.get("current_section") or None,
                total_sections=raw.get("total_sections") or None,
                completed_sections=raw.get("completed_sections", 0),
                n_results=n_results,
            )

        return await _run_in_executor(_fetch_status)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get status failed")
        raise HTTPException(500, detail=f"Get status failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/results — List all comparison results
# ---------------------------------------------------------------------------


@router.get("/results")
async def get_results(request: Request, section: Optional[str] = None):
    """Return all comparison results, optionally filtered by section.

    The SQLite read runs on the default executor so the event loop isn't
    blocked while the (potentially large) results table is fetched.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )

        def _fetch():
            return db.get_results(session_id, section=section)

        return await _run_in_executor(_fetch)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get results failed")
        raise HTTPException(500, detail=f"Get results failed: {exc}")


# ---------------------------------------------------------------------------
# GET /profiles/{section_id}
# ---------------------------------------------------------------------------


def _build_profile_payload_sync(
    session_id: str,
    sec_dict: dict,
) -> dict:
    """Compute profile / extraction payload off the event loop.

    Cuts both meshes on the section, builds reconciled profiles (legacy +
    v2), and returns a JSON-ready dict.
    """
    sec = _section_from_dict(sec_dict)

    # Load meshes and cut profiles
    try:
        mesh_design = _load_mesh_from_db(session_id, "design")
        mesh_topo = _load_mesh_from_db(session_id, "topo")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Error loading meshes: {exc}")

    design_cut = cut_mesh_with_section_diagnostics(mesh_design, sec)
    topo_cut = cut_mesh_with_section_diagnostics(mesh_topo, sec)
    pd_prof = design_cut.profile
    pt_prof = topo_cut.profile

    result: Dict[str, Any] = {
        "section_name": sec.name,
        "sector": sec.sector,
        "origin": sec.origin.tolist(),
        "azimuth": sec.azimuth,
        "profile_warnings": {
            "design": list(design_cut.warnings),
            "topo": list(topo_cut.warnings),
        },
    }

    if pd_prof is not None:
        result["design"] = {
            "distances": pd_prof.distances.tolist(),
            "elevations": pd_prof.elevations.tolist(),
        }
    if pt_prof is not None:
        result["topo"] = {
            "distances": pt_prof.distances.tolist(),
            "elevations": pt_prof.elevations.tolist(),
        }

    # Reconciled profiles from extraction cache. The v2 builder
    # returns a ReconciledProfile whose ``segments`` field carries
    # per-point metadata (bench_number, segment_type, source) that
    # the frontend uses to differentiate face / berm / ramp.
    # When the original cut profile is available (pd_prof / pt_prof)
    # we pass it to the builder so the reconciled polyline samples
    # intermediate face points from the actual as-built curvature
    # rather than drawing straight crest-toe lines.
    profile_d_arg = (
        (pd_prof.distances, pd_prof.elevations)
        if pd_prof is not None else None
    )
    profile_t_arg = (
        (pt_prof.distances, pt_prof.elevations)
        if pt_prof is not None else None
    )
    # Cota del piso y crest máxima: se calculan del perfil original ANTES
    # de construir los reconciled profiles para que el perfil conciliado
    # se extienda hasta el piso real.
    topo_floor = None
    topo_crest_max = None
    if pt_prof is not None and len(pt_prof.elevations) > 0:
        topo_floor = float(np.min(pt_prof.elevations))
        topo_crest_max = float(np.max(pt_prof.elevations))

    design_extraction = db.get_extraction(session_id, sec.name, "design")
    benches_d = []
    if design_extraction and pd_prof is not None:
        benches_d = [_dict_to_bench(b) for b in design_extraction.get("benches", [])]
        if benches_d:
            design_floor = float(np.min(pd_prof.elevations)) if pd_prof is not None else None
            prof_d = build_reconciled_profile_v2(
                benches_d, source="design", profile=profile_d_arg,
                floor_elevation=design_floor,
            )
            result["reconciled_design"] = _reconciled_profile_to_dict(prof_d)
            result["benches_design"] = [_bench_to_dict(b) for b in benches_d]
            floor_points = [p for p in prof_d.points if p.segment_type == "floor"]
            floor_point = floor_points[-1] if floor_points else None
            result["reconciled_design_legacy"] = _legacy_reconciled_to_dict(
                benches_d,
                floor_elevation=design_floor,
                floor_point=(floor_point.distance, floor_point.elevation)
                if floor_point is not None else None,
                floor_resolved_from_profile=profile_d_arg is not None,
            )

    topo_extraction = db.get_extraction(session_id, sec.name, "topo")
    if topo_extraction and pt_prof is not None:
        benches_t = [_dict_to_bench(b) for b in topo_extraction.get("benches", [])]
        if benches_t:
            prof_t = build_reconciled_profile_v2(
                benches_t, source="topo", profile=profile_t_arg,
                floor_elevation=topo_floor,
            )
            result["reconciled_topo"] = _reconciled_profile_to_dict(prof_t)
            floor_points = [p for p in prof_t.points if p.segment_type == "floor"]
            floor_point = floor_points[-1] if floor_points else None
            result["reconciled_topo_legacy"] = _legacy_reconciled_to_dict(
                benches_t,
                floor_elevation=topo_floor,
                floor_point=(floor_point.distance, floor_point.elevation)
                if floor_point is not None else None,
                floor_resolved_from_profile=profile_t_arg is not None,
            )
            result["benches_topo"] = [_bench_to_dict(b) for b in benches_t]

    if pd_prof is not None and pt_prof is not None:
        horizontal_result = compute_horizontal_deviation(
            (pd_prof.distances, pd_prof.elevations),
            (pt_prof.distances, pt_prof.elevations),
            benches_d,
        )
        result["horizontal_deviation"] = horizontal_result.to_dict()

    if topo_floor is not None:
        result["floor_elevation"] = topo_floor
    if topo_crest_max is not None:
        result["crest_elevation_max"] = topo_crest_max

    return result


@router.get("/profiles/{section_id}")
async def get_profile(request: Request, section_id: int):
    """
    Return profile data for a section by its index in the sections list.

    Includes raw design/topo profiles, reconciled profiles from the
    extraction cache, and bench data for interactive editing.

    The cut/extract work (trimesh slicing + reconciled profile building)
    runs off the event loop via ``run_in_executor``.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        sections_raw = db.get_sections(session_id)
        if section_id < 0 or section_id >= len(sections_raw):
            raise HTTPException(404, "Section index out of range")

        return await _run_in_executor(
            _build_profile_payload_sync, session_id, sections_raw[section_id]
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get profile failed")
        raise HTTPException(500, detail=f"Get profile failed: {exc}")


# ---------------------------------------------------------------------------
# PUT /results/{section_id}/reconciled — Interactive bench editing
# ---------------------------------------------------------------------------


def _update_reconciled_sync(
    session_id: str,
    section_id: int,
    body_updates: List[dict],
) -> dict:
    """Persist updated benches for a section and re-run its comparison.

    Synchronous helper invoked via ``run_in_executor`` from
    :func:`update_reconciled`. Takes the request body already serialised
    to plain ``dict`` (Pydantic parsing must stay on the event loop) and
    returns the response payload ready for JSON encoding.
    """
    sections_raw = db.get_sections(session_id)
    if section_id < 0 or section_id >= len(sections_raw):
        raise HTTPException(404, "Section index out of range")

    sec_name = sections_raw[section_id]["name"]

    # Load current topo extraction cache
    topo_extraction = db.get_extraction(session_id, sec_name, "topo")
    if not topo_extraction:
        raise HTTPException(404, f"No extraction data for section {sec_name}")

    # Reconstruct benches from cache and apply updates
    benches = [_dict_to_bench(b) for b in topo_extraction.get("benches", [])]

    for i, update_dict in enumerate(body_updates):
        if i < len(benches):
            b = benches[i]
            # Update positions
            if "crest_distance" in update_dict:
                b.crest_distance = float(update_dict["crest_distance"])
            if "crest_elevation" in update_dict:
                b.crest_elevation = float(update_dict["crest_elevation"])
            if "toe_distance" in update_dict:
                b.toe_distance = float(update_dict["toe_distance"])
            if "toe_elevation" in update_dict:
                b.toe_elevation = float(update_dict["toe_elevation"])

            # Recalculate derived values
            b.bench_height = abs(b.crest_elevation - b.toe_elevation)
            dx = b.toe_distance - b.crest_distance
            dz = b.crest_elevation - b.toe_elevation
            if abs(dx) > 0.01:
                b.face_angle = abs(float(np.degrees(np.arctan2(dz, abs(dx)))))
            else:
                b.face_angle = 90.0

    # Recalculate berm widths between adjacent benches
    for i in range(len(benches) - 1):
        benches[i].berm_width = abs(
            benches[i + 1].crest_distance - benches[i].toe_distance
        )

    # Persist updated extraction cache
    updated_extraction = _extraction_to_dict(
        ExtractionResult(
            section_name=sec_name,
            sector=sections_raw[section_id].get("sector", ""),
            benches=benches,
        )
    )
    db.save_extraction(session_id, sec_name, "topo", updated_extraction)

    # Re-run comparison for this section
    settings = db.get_settings(session_id) or {}
    tolerances = settings.get("tolerances", {})
    if not tolerances:
        tolerances = {
            "bench_height": DEFAULT_TOLERANCES.bench_height,
            "face_angle": DEFAULT_TOLERANCES.face_angle,
            "berm_width": DEFAULT_TOLERANCES.berm_width,
            "inter_ramp_angle": DEFAULT_TOLERANCES.inter_ramp_angle,
            "overall_angle": DEFAULT_TOLERANCES.overall_angle,
        }

    asbuilt_profile = None
    try:
        sec = _section_from_dict(sections_raw[section_id])
        mesh_topo = _load_mesh_from_db(session_id, "topo")
        topo_cut = cut_mesh_with_section_diagnostics(mesh_topo, sec)
        if topo_cut.profile is not None:
            asbuilt_profile = (topo_cut.profile.distances, topo_cut.profile.elevations)
    except Exception as exc:
        logger.warning("As-built profile unavailable for %s: %s", sec_name, exc)

    design_extraction = db.get_extraction(session_id, sec_name, "design")
    if design_extraction:
        benches_d = [_dict_to_bench(b) for b in design_extraction.get("benches", [])]
        p_design = ExtractionResult(
            section_name=sec_name,
            sector=sections_raw[section_id].get("sector", ""),
            benches=benches_d,
        )
        p_topo = ExtractionResult(
            section_name=sec_name,
            sector=sections_raw[section_id].get("sector", ""),
            benches=benches,
        )
        new_comps = _guided_comparison(p_design, p_topo, tolerances, asbuilt_profile)

        # Remove old comparisons for this section, add new ones
        existing = db.get_results(session_id)
        filtered = [r for r in existing if r.get("section") != sec_name]
        # Strip non-serialisable keys from new comparisons
        safe_new = [
            {k: v for k, v in c.items() if k not in ("bench_design", "bench_real")}
            for c in new_comps
        ]
        filtered.extend(safe_new)
        db.save_results(session_id, filtered)

    # Return updated reconciled profile + benches (v2: rich segments)
    prof = build_reconciled_profile_v2(benches, source="topo")
    return {
        "reconciled_topo": _reconciled_profile_to_dict(prof),
        "benches": [_bench_to_dict(b) for b in benches],
    }


@router.put("/results/{section_id}/reconciled")
async def update_reconciled(
    request: Request, section_id: int, body: List[schemas.BenchParamsSchema]
):
    """
    Update benches after drag & drop editing in the UI.

    Receives updated crest/toe positions, recalculates derived values
    (height, angle, berm width), re-runs comparison for this section,
    and returns the updated reconciled profile.

    The bench updates + comparison rerun happen off the event loop via
    ``run_in_executor`` so the SQLite writes and numpy math don't stall
    the event loop.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )

        # Pre-serialise the request body on the event loop (Pydantic parses
        # cleanly here; the worker thread receives plain dicts).
        body_updates = [
            item.model_dump() if hasattr(item, "model_dump") else item.dict()
            for item in body
        ]

        return await _run_in_executor(
            _update_reconciled_sync, session_id, section_id, body_updates
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Update reconciled failed")
        raise HTTPException(500, detail=f"Update reconciled failed: {exc}")


# ---------------------------------------------------------------------------
# Blast-hole helpers + GET /process/profiles/{section_id}/blast-holes
# ---------------------------------------------------------------------------


def _load_session_blast_holes(session_id: str) -> Optional[pd.DataFrame]:
    """Load the session's blast holes as a DataFrame.

    Holes are stored in the session settings dict under the ``"blast_holes"``
    key (a list of plain dicts). This key is populated by the blast-upload
    flow (gap G11 in ``docs/UI_PARITY_AUDIT.md``); until that flow lands the
    endpoint returns an empty hole list.

    Returns ``None`` when the key is absent, empty, or malformed; otherwise a
    DataFrame whose columns include at least ``X`` and ``Y``.
    """
    settings = db.get_settings(session_id) or {}
    raw = settings.get("blast_holes")
    if not isinstance(raw, list) or not raw:
        return None
    try:
        df = pd.DataFrame(raw)
    except Exception:
        return None
    if not {"X", "Y"}.issubset(df.columns):
        return None
    return df


def _projected_to_holes(
    projected: pd.DataFrame,
    tolerance: float,
    session_id: str,
) -> List[schemas.BlastHoleOnProfile]:
    """Map a projected blast-hole DataFrame to ``BlastHoleOnProfile`` schemas.

    ``projected`` is the output of
    :func:`core.calculo_tronadura.proyectar_pozos_en_seccion`: each row carries
    ``dist_along`` (along-section distance), ``dist_perp`` (perpendicular
    distance), and the original hole columns (``Z_collar``, ``Burden``, ``Esp``
    …) when present.

    ``spacing`` falls back to the nearest-neighbour collar distance when the
    ``Esp`` column is missing. Missing burden is null.
    """
    if projected is None or projected.empty:
        return []

    cols = set(projected.columns)
    has_burden = "Burden" in cols
    has_esp = "Esp" in cols
    has_z_collar = "Z_collar" in cols

    spacing_fallback: Optional[List[float]] = None
    if not has_esp and len(projected) > 1:
        coords = projected[["X", "Y"]].to_numpy(dtype=float)
        spacing_fallback = []
        for i in range(len(coords)):
            best = float("inf")
            for j in range(len(coords)):
                if i == j:
                    continue
                d = float(np.hypot(coords[i, 0] - coords[j, 0],
                                   coords[i, 1] - coords[j, 1]))
                if d < best:
                    best = d
            spacing_fallback.append(best)

    out: List[schemas.BlastHoleOnProfile] = []
    for i, row in enumerate(projected.itertuples(index=False)):
        row_data = projected.iloc[i].to_dict()
        d_perp = float(getattr(row, "dist_perp", 0.0))

        burden = _safe_float(getattr(row, "Burden", None)) if has_burden else None
        if has_esp:
            spacing = _safe_float(getattr(row, "Esp", None))
        elif spacing_fallback is not None:
            spacing = _safe_float(spacing_fallback[i])
        else:
            spacing = None

        profile_elevation = row_data.get("_profile_elevation", np.nan)
        if pd.notna(profile_elevation) and math.isfinite(float(profile_elevation)):
            elevation = float(profile_elevation)
        elif has_z_collar:
            z_raw = getattr(row, "Z_collar", 0.0)
            if pd.isna(z_raw) or not math.isfinite(float(z_raw)):
                continue
            elevation = float(z_raw)
        else:
            continue

        hole_id = blast_hole_id(row_data, "sin dato")
        row_id = row_data.get("_blast_row_id")
        if not row_id:
            row_id = blast_row_ids(session_id, [row_data])[0]
        section_relation = row_data.get("section_relation")
        if pd.isna(section_relation):
            section_relation = None
        profile_point_kind = (
            "intersection"
            if pd.notna(row_data.get("_profile_elevation"))
            or row_data.get("closest_point") == "segment_intersection"
            else "projected_collar"
        )

        out.append(schemas.BlastHoleOnProfile(
            row_id=row_id,
            hole_id=hole_id,
            distance=round(float(getattr(row, "dist_along", 0.0)), 3),
            elevation=round(elevation, 3),
            burden=burden,
            spacing=spacing,
            is_within_tolerance=bool(d_perp <= tolerance + 1e-9),
            section_relation=section_relation,
            profile_point_kind=profile_point_kind,
            z_collar_semantic=getattr(row, "Z_collar_semantic", None),
            surface_sample_status=getattr(row, "surface_sample_status", None),
            surface_sample_method=getattr(row, "surface_sample_method", None),
            surface_sample_mesh_id=getattr(row, "surface_sample_mesh_id", None),
            surface_sample_mesh_sha256=getattr(row, "surface_sample_mesh_sha256", None),
        ))
    return out


def _append_exact_section_crossings(
    holes: pd.DataFrame,
    projected: pd.DataFrame,
    section: SectionLine,
    corridor_m: float,
) -> pd.DataFrame:
    from core.hole_section_geometry import classify_hole_segment_to_section
    from core.section_cutter import azimuth_to_direction

    def values(column: str) -> np.ndarray:
        source = holes[column] if column in holes else pd.Series(np.nan, index=holes.index)
        return pd.to_numeric(source, errors="coerce").to_numpy(dtype=float)

    x0, y0, z0 = values("X"), values("Y"), values("Z_collar")
    x1, y1, z1 = values("X_toe"), values("Y_toe"), values("Z_toe")
    valid = np.isfinite(np.column_stack((x0, y0, z0, x1, y1, z1))).all(axis=1)
    direction = azimuth_to_direction(float(section.azimuth))
    normal = np.array([direction[1], -direction[0]])
    origin = np.asarray(section.origin, dtype=float)[:2]
    s0 = (x0 - origin[0]) * normal[0] + (y0 - origin[1]) * normal[1]
    s1 = (x1 - origin[0]) * normal[0] + (y1 - origin[1]) * normal[1]
    crosses_plane = ((s0 <= 1e-9) & (s1 >= -1e-9)) | ((s1 <= 1e-9) & (s0 >= -1e-9))
    candidate_indices = np.flatnonzero(valid & crosses_plane)
    if not len(candidate_indices):
        return projected

    projected_ids = set(projected["_blast_row_id"].astype(str)) if "_blast_row_id" in projected else set()
    extra_rows = []
    exact_projected_ids = set()
    for index in candidate_indices:
        record = holes.iloc[int(index)].to_dict()
        classification = classify_hole_segment_to_section(
            [x0[index], y0[index], z0[index]],
            [x1[index], y1[index], z1[index]],
            section,
            corridor_m=corridor_m,
        )
        if classification.relation != "exact_intersection":
            continue
        row_id = str(record.get("_blast_row_id", ""))
        if row_id in projected_ids:
            exact_projected_ids.add(row_id)
            continue

        station0 = float(classification.along_section_collar_m)
        station1 = float(classification.along_section_toe_m)
        signed0 = float(classification.signed_distance_collar_m)
        signed1 = float(classification.signed_distance_toe_m)
        if abs(signed0) <= 1e-9 and abs(signed1) <= 1e-9:
            if section.length_up is not None and section.length_down is not None:
                lower, upper = -float(section.length_down), float(section.length_up)
            else:
                lower, upper = -float(section.length) / 2.0, float(section.length) / 2.0
            overlap_lower = max(min(station0, station1), lower)
            overlap_upper = min(max(station0, station1), upper)
            station = (overlap_lower + overlap_upper) / 2.0
            fraction = 0.0 if station1 == station0 else (station - station0) / (station1 - station0)
        else:
            denominator = signed0 - signed1
            fraction = 0.0 if abs(denominator) <= 1e-9 else float(np.clip(signed0 / denominator, 0.0, 1.0))
            station = station0 + fraction * (station1 - station0)

        record.update({
            "dist_along": station,
            "dist_along_toe": station1,
            "dist_perp": abs(signed0),
            "dist_perp_toe": abs(signed1),
            "closest_point": "segment_intersection",
            "_profile_elevation": z0[index] + fraction * (z1[index] - z0[index]),
            "section_relation": "exact_intersection",
        })
        extra_rows.append(record)
        projected_ids.add(row_id)

    if exact_projected_ids:
        projected.loc[
            projected["_blast_row_id"].astype(str).isin(exact_projected_ids),
            "section_relation",
        ] = "exact_intersection"
    if not extra_rows:
        return projected
    return pd.concat((projected, pd.DataFrame(extra_rows)), ignore_index=True, sort=False).sort_values(
        "dist_along", kind="stable"
    ).reset_index(drop=True)


def _project_blast_holes_sync(
    session_id: str,
    section_id: int,
    mesh_id: str,
    tolerance: float,
) -> schemas.BlastHolesOnProfileResponse:
    """Project blast holes onto a section off the event loop.

    The ``proyectar_pozos_en_seccion`` primitive + DataFrame iter rows are
    CPU-bound (pandas + numpy hypot), so we keep them off the event loop
    by routing this through ``run_in_executor``.
    """
    status = blast_data_status(db.get_settings(session_id) or {})
    sections_raw = db.get_sections(session_id)
    if section_id < 0 or section_id >= len(sections_raw):
        return schemas.BlastHolesOnProfileResponse(
            **status,
            section_id="",
            mesh_id=mesh_id,
            tolerance=tolerance,
            holes=[],
        )

    sec = _section_from_dict(sections_raw[section_id])

    df_holes = _load_session_blast_holes(session_id)
    if df_holes is None or df_holes.empty:
        return schemas.BlastHolesOnProfileResponse(
            **status,
            section_id=sec.name,
            mesh_id=mesh_id,
            tolerance=tolerance,
            holes=[],
        )

    df_holes["_blast_row_id"] = blast_row_ids(
        session_id, df_holes.to_dict(orient="records")
    )

    if "source_row_index" not in df_holes.columns:
        df_holes["source_row_index"] = range(len(df_holes))
    else:
        missing_source_index = df_holes["source_row_index"].isna()
        df_holes.loc[missing_source_index, "source_row_index"] = np.flatnonzero(missing_source_index.to_numpy())

    inclusion_radius = max(
        float(tolerance),
        float(DEFAULTS.blast_correlation_radius_m),
    )
    projected = proyectar_pozos_en_seccion(
        df_holes,
        origin=sec.origin,
        azimuth=sec.azimuth,
        length=sec.length,
        tolerance=inclusion_radius,
    )
    projected = _append_exact_section_crossings(
        df_holes, projected, sec, inclusion_radius,
    )
    holes = _projected_to_holes(projected, float(tolerance), session_id)
    return schemas.BlastHolesOnProfileResponse(
        **status,
        section_id=sec.name,
        mesh_id=mesh_id,
        tolerance=tolerance,
        holes=holes,
    )


@router.get("/profiles/{section_id}/blast-holes")
async def get_blast_holes(
    request: Request,
    section_id: int,
    mesh_id: str = "",
    tolerance: float = 2.0,
):
    """Project the session's blast holes onto a section profile.

    Wraps :func:`core.calculo_tronadura.proyectar_pozos_en_seccion` — the same
    primitive used by the Streamlit reference (``ui/tabs/profiles.py``) — to
    project each 3D blast hole onto the section's 2D plane and emit a marker
    per hole.

    The primitive is called with ``DEFAULTS.blast_correlation_radius_m`` as the
    perpendicular inclusion radius so that holes within AND beyond the design
    tolerance are returned. ``is_within_tolerance`` is then derived per hole by
    comparing its ``dist_perp`` against the requested ``tolerance``.

    Blast holes are read from the session settings dict under the
    ``"blast_holes"`` key (populated by the blast-upload flow, gap G11). When
    the key is absent, the section has no holes, or ``section_id`` is out of
    range, the endpoint returns an empty hole list — never 404, per spec.

    Path deviation: mounted under ``/process/profiles/...`` (not
    ``/sections/...``) because only ``api/routers/process.py`` is in scope for
    this change and the process router already owns section-scoped profile
    endpoints. Full path: ``GET /api/v1/process/profiles/{section_id}/blast-holes``.

    The DataFrame projection + numpy hypot fan-out run on the default
    executor so the event loop isn't blocked while holes are scored.

    Parameters
    ----------
    section_id : int
        Index into the session's sections list (same convention as
        ``GET /process/profiles/{section_id}``).
    mesh_id : str
        Design mesh identifier, echoed back in the response. Not used for the
        projection (blast-hole projection is pure geometry on holes + section).
    tolerance : float
        Design tolerance in metres (default 2.0). Holes whose perpendicular
        distance to the section exceeds this are flagged
        ``is_within_tolerance=False``.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )
        return await run_blast_limited(
            _project_blast_holes_sync,
            session_id,
            section_id,
            mesh_id,
            tolerance,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get blast holes failed")
        raise HTTPException(500, detail=f"Get blast holes failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/blast-correlation
# ---------------------------------------------------------------------------


def _resolve_blast_correlation_rows(
    session_id: str,
    tolerance: Optional[float],
    survey_date: Optional[date] = None,
):
    """Resolve the session's ``BlastCorrelationRow`` list.

    Shared by ``GET /process/blast-correlation`` and the damage-model
    endpoint so both walk the identical data flow (holes → sections →
    comparisons → :func:`compute_blast_geotech_correlation`) and surface
    identical numbers. Returns ``(rows, sections_raw, resolved_tolerance)``
    where ``rows`` is an empty list whenever any prerequisite is missing
    (no holes / no sections / no comparisons), matching the graceful-empty
    contract of the blast-correlation endpoint.
    """
    sections_raw = db.get_sections(session_id)
    df_holes = _load_session_blast_holes(session_id)
    comparisons = db.get_results(session_id)
    temporal_filter = _build_temporal_filter(df_holes, survey_date)
    if survey_date is not None and df_holes is not None:
        df_holes = _filter_blast_holes_by_survey_date(df_holes, survey_date)

    resolved_tolerance = (
        float(tolerance) if tolerance is not None
        else float(DEFAULTS.blast_correlation_radius_m)
    )

    if (
        df_holes is None
        or df_holes.empty
        or not sections_raw
        or not comparisons
    ):
        return [], sections_raw, resolved_tolerance, temporal_filter, _blast_histogram_values(df_holes)

    settings = db.get_settings(session_id) or {}
    blast = settings.get("blast") or {}
    rock_density_tm3 = blast.get("rock_density_tm3")
    height_fallback_m = blast.get("height_fallback_m")
    sector_density = blast.get("sector_density")

    sections = [_section_from_dict(s) for s in sections_raw]
    rows = compute_blast_geotech_correlation(
        df_holes, sections, comparisons,
        tolerance=tolerance,
        rock_density_tm3=rock_density_tm3,
        height_fallback_m=height_fallback_m,
        sector_density=sector_density,
    )
    for row, sec in zip(rows, sections):
        projected = proyectar_pozos_en_seccion(
            df_holes, origin=sec.origin, azimuth=float(sec.azimuth),
            length=float(sec.length), tolerance=resolved_tolerance,
        )
        if not projected.empty and "area_influence_m2" not in projected.columns:
            sec_rho = (sector_density or {}).get(sec.sector or "", rock_density_tm3)
            projected = compute_powder_factor(projected, rock_density_tm3=sec_rho, height_fallback_m=height_fallback_m)
        if "pf_voronoi_bench_status" in projected:
            statuses = projected["pf_voronoi_bench_status"].fillna("UNKNOWN").astype(str).replace("", "UNKNOWN")
            row.pf_voronoi_bench_status_counts = {key: int(value) for key, value in statuses.value_counts().items()}
        else:
            row.pf_voronoi_bench_status_counts = {"UNKNOWN": len(projected)} if len(projected) else {}
        if "pf_voronoi_bench_source" in projected:
            sources = projected["pf_voronoi_bench_source"].fillna("").astype(str).replace("", "none")
            counts = {key: int(value) for key, value in sources.value_counts().items()}
            row.pf_voronoi_bench_source_counts = counts
            row.pf_voronoi_bench_source_dominant = max(counts, key=counts.get) if counts else None
        else:
            row.pf_voronoi_bench_source_counts = {}
            row.pf_voronoi_bench_source_dominant = None
    return rows, sections_raw, resolved_tolerance, temporal_filter, _blast_histogram_values(df_holes)


def _blast_histogram_values(df_holes: Optional[pd.DataFrame]) -> tuple[list[float], list[float], list[float]]:
    if df_holes is None or df_holes.empty:
        return [], [], []
    if "kg_per_meter" in df_holes.columns:
        carga = pd.to_numeric(df_holes["kg_per_meter"], errors="coerce")
    else:
        kg_column = first_present_column(df_holes, KILOS_CANDIDATES)
        length_column = first_present_column(
            df_holes, ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
        )
        if kg_column is not None and length_column is not None:
            kilos = pd.to_numeric(df_holes[kg_column], errors="coerce")
            length = pd.to_numeric(df_holes[length_column], errors="coerce")
            carga = (kilos / length).where(length > 0)
        else:
            carga = pd.Series(dtype=float)
    if "altura_carga_m" in df_holes.columns:
        descarga = pd.to_numeric(df_holes["altura_carga_m"], errors="coerce")
    else:
        length_column = first_present_column(
            df_holes, ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
        )
        taco_column = first_present_column(df_holes, ("Taco_m", "Taco", "Stemming"))
        if length_column is not None and taco_column is not None:
            length = pd.to_numeric(df_holes[length_column], errors="coerce")
            taco = pd.to_numeric(df_holes[taco_column], errors="coerce")
            descarga = (length - taco).where((length > 0) & (taco >= 0) & (taco <= length))
        else:
            descarga = pd.Series(dtype=float)
    loaded = pd.to_numeric(df_holes["kg_per_meter_loaded_column"], errors="coerce") if "kg_per_meter_loaded_column" in df_holes else pd.Series(dtype=float)
    length_column = first_present_column(df_holes, ("Len", "longitud_real", "Longitud", "Length", "Profundidad"))
    taco_column = first_present_column(df_holes, ("Taco_m", "Taco", "Stemming"))
    if length_column is not None and taco_column is not None:
        length = pd.to_numeric(df_holes[length_column], errors="coerce")
        taco = pd.to_numeric(df_holes[taco_column], errors="coerce")
        invalid = (length <= 0) | (taco < 0) | (taco > length)
        descarga = descarga.mask(invalid)
        loaded = loaded.mask(invalid | ((length == taco) & length.notna()))
    return (
        [float(value) for value in carga if pd.notna(value) and np.isfinite(value)],
        [float(value) for value in descarga if pd.notna(value) and np.isfinite(value)],
        [float(value) for value in loaded if pd.notna(value) and np.isfinite(value)],
    )


def _build_temporal_filter(
    df_holes: Optional[pd.DataFrame], survey_date: Optional[date]
) -> dict:
    total = 0 if df_holes is None else len(df_holes)
    date_column = "fecha_tronadura"
    if survey_date is None:
        missing = total
        if df_holes is not None and date_column in df_holes.columns:
            dates = pd.to_datetime(df_holes[date_column], errors="coerce")
            missing = int(dates.isna().sum())
        return {
            "enabled": False,
            "survey_date": None,
            "effective_cutoff_date": None,
            "buffer_days": DEFAULTS.blast_temporal_filter_days,
            "policy": "inactive: all holes are included; missing dates are reported separately",
            "included": total,
            "excluded": 0,
            "missing": missing,
            "total": total,
        }

    buffer_days = int(DEFAULTS.blast_temporal_filter_days)
    cutoff = survey_date - timedelta(days=buffer_days)
    if df_holes is None or date_column not in df_holes.columns:
        missing = total
        included = excluded = 0
    else:
        dates = pd.to_datetime(df_holes[date_column], errors="coerce").dt.date
        missing_mask = dates.isna()
        eligible_mask = dates.notna() & (dates <= cutoff)
        missing = int(missing_mask.sum())
        included = int(eligible_mask.sum())
        excluded = total - missing - included
    return {
        "enabled": True,
        "survey_date": survey_date.isoformat(),
        "effective_cutoff_date": cutoff.isoformat(),
        "buffer_days": buffer_days,
        "policy": "include known blast dates on or before effective_cutoff_date; exclude later known dates; never include missing or invalid dates",
        "included": included,
        "excluded": excluded,
        "missing": missing,
        "total": total,
    }


def _filter_blast_holes_by_survey_date(
    df_holes: pd.DataFrame, survey_date: date
) -> pd.DataFrame:
    if df_holes.empty or "fecha_tronadura" not in df_holes.columns:
        return df_holes.iloc[0:0].copy()
    cutoff = survey_date - timedelta(days=int(DEFAULTS.blast_temporal_filter_days))
    dates = pd.to_datetime(df_holes["fecha_tronadura"], errors="coerce").dt.date
    return df_holes.loc[dates.notna() & (dates <= cutoff)].copy()


def _build_blast_correlation_sync(
    session_id: str,
    tolerance: Optional[float],
    survey_date: Optional[date] = None,
) -> schemas.BlastCorrelationResponse:
    """Build the blast↔geotech correlation response off the event loop.

    All DB reads, ``compute_blast_geotech_correlation``, and the row→schema
    mapping run on the default executor so the event loop isn't blocked
    while the (potentially large) correlation table is assembled.
    """
    rows, sections_raw, resolved_tolerance, temporal_filter, histogram_values = _resolve_blast_correlation_rows(
        session_id, tolerance, survey_date
    )

    schema_rows = [
        schemas.BlastCorrelationRowSchema(
            section_name=r.section_name,
            num_wells=int(r.num_wells),
            total_kg=_safe_float(r.total_kg),
            mean_abs_deviation=_safe_float(r.mean_abs_deviation),
            avg_over_break=_safe_float(r.avg_over_break),
            avg_under_break=_safe_float(r.avg_under_break),
            n_over=int(r.n_over),
            n_under=int(r.n_under),
            pf_vol_avg_kgm3=_safe_float(r.pf_vol_avg_kgm3),
            pf_area_avg_kgm2=_safe_float(r.pf_area_avg_kgm2),
            pf_g_per_ton_avg=_safe_float(r.pf_g_per_ton_avg),
            pf_g_per_ton_net_avg=_safe_float(r.pf_g_per_ton_net_avg),
            pf_g_per_ton_inf_avg=_safe_float(r.pf_g_per_ton_inf_avg),
            pf_voronoi_bench_g_per_ton_section=_safe_float(r.pf_voronoi_bench_g_per_ton_section),
            n_pf_voronoi_bench_valid=int(r.n_pf_voronoi_bench_valid),
            pf_voronoi_bench_status_counts=getattr(r, "pf_voronoi_bench_status_counts", {}),
            pf_voronoi_bench_source_counts=getattr(r, "pf_voronoi_bench_source_counts", {}),
            pf_voronoi_bench_source_dominant=getattr(r, "pf_voronoi_bench_source_dominant", None),
            energy_coverage_kg_fraction=_safe_float(r.energy_coverage_kg_fraction),
            energy_total_mj=_safe_float(r.energy_total_mj),
            energy_known_mj=_safe_float(getattr(r, "energy_known_mj", None)),
            n_kg_known=int(getattr(r, "n_kg_known", 0)),
            n_kg_missing=int(getattr(r, "n_kg_missing", 0)),
            n_pf_valid=int(r.n_pf_valid),
            sector=str(getattr(r, "sector", "") or ""),
            rock_density_used=_safe_float(getattr(r, "rock_density_used", None)),
        )
        for r in rows
    ]

    return schemas.BlastCorrelationResponse(
        **blast_data_status(db.get_settings(session_id) or {}),
        rows=schema_rows,
        tolerance=resolved_tolerance,
        n_sections=len(sections_raw),
        temporal_filter=temporal_filter,
        carga=histogram_values[0],
        descarga=histogram_values[1],
        kg_per_meter=histogram_values[0],
        kg_per_meter_loaded_column=histogram_values[2] if len(histogram_values) > 2 else [],
    )


@router.get("/blast-correlation")
async def get_blast_correlation(
    request: Request,
    tolerance: Optional[float] = None,
    survey_date: Optional[date] = Query(default=None),
):
    """Per-section blast↔geotech correlation summary, including powder factor.

    Wraps :func:`core.blast_correlation.compute_blast_geotech_correlation` — the
    same primitive used by the Streamlit reference and the Excel/Word writers —
    so the web frontend, CLI and reports all consume identical numbers.

    Data flow (all primitives reused, none duplicated):
        session   = db.get_or_create_session(request.state.session_id)
        sections  = [_section_from_dict(s) for s in db.get_sections(session_id)]
        df_holes  = _load_session_blast_holes(session_id)        # or None
        comparisons = db.get_results(session_id)                 # List[Dict]
        rows      = compute_blast_geotech_correlation(
                        df_holes, sections, comparisons, tolerance)

    Each returned row carries the full set of powder-factor metrics surfaced by
    the underlying primitive: ``pf_vol_avg_kgm3`` (kg/m³), ``pf_area_avg_kgm2``
    (kg/m²), ``pf_g_per_ton_avg`` (g/ton — the per-mass PF) and
    ``energy_total_mj`` (total explosive energy), alongside the geotech
    deviation aggregates (``mean_abs_deviation``, ``avg_over_break`` …).

    Empty-case behaviour (matches the blast-holes endpoint philosophy): when the
    session has no blast holes, no sections, or no comparison results, the
    endpoint returns ``BlastCorrelationResponse(rows=[])`` with HTTP 200 — it
    never raises 404/500 on empty input.

    Per-session overrides: the session's ``blast.rock_density_tm3`` and
    ``blast.height_fallback_m`` settings (managed via ``PUT /settings``) are
    forwarded to :func:`compute_blast_geotech_correlation`. When unset the
    core primitive falls back to the ``BLAST`` singleton defaults
    (2.7 ton/m³, 15.0 m).

    The DB reads + correlation primitive run off the event loop via
    ``run_in_executor``.

    Parameters
    ----------
    tolerance : float | None
        Perpendicular inclusion radius in metres around each section axis.
        ``None`` (default) defers to ``DEFAULTS.blast_correlation_radius_m``
        inside the core primitive.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )
        return await run_blast_limited(
            _build_blast_correlation_sync, session_id, tolerance, survey_date
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get blast correlation failed")
        raise HTTPException(500, detail=f"Get blast correlation failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/blast-correlation/damage-model
# ---------------------------------------------------------------------------


def _build_damage_model_sync(
    session_id: str,
    tolerance: Optional[float],
    survey_date: Optional[date] = None,
) -> schemas.BlastDamageModelResponse:
    """Fit the PF↔damage OLS model off the event loop.

    DB reads, the correlation-row walk, the numpy ``polyfit`` and the
    schema assembly all happen on the default executor so the event
    loop isn't blocked while the fit is computed.
    """
    rows, _sections_raw, _tol, temporal_filter, _histogram_values = _resolve_blast_correlation_rows(
        session_id, tolerance, survey_date
    )

    # Build the (PF, overbreak) sample, dropping zero/NaN PF rows so the
    # emitted points match the samples the fitter consumes.
    points: List[schemas.BlastDamagePointSchema] = []
    pf_values_list: List[float] = []
    dmg_values_list: List[float] = []
    for r in rows:
        try:
            pf = float(r.pf_g_per_ton_avg)
            over = float(r.avg_over_break)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(pf) or not math.isfinite(over):
            continue
        if pf <= 0.0:
            continue
        points.append(schemas.BlastDamagePointSchema(
            section_name=str(r.section_name),
            pf_g_per_ton=pf,
            over_break=over,
        ))
        pf_values_list.append(pf)
        dmg_values_list.append(over)

    fit_schema: Optional[schemas.BlastDamageModelFitSchema] = None
    if pf_values_list:
        pf_arr = np.asarray(pf_values_list, dtype=float)
        dmg_arr = np.asarray(dmg_values_list, dtype=float)
        model = fit_powder_factor_damage_model(pf_arr, dmg_arr)
        confidence = str(model.get("confidence", "INSUFFICIENT"))
        if confidence != "INSUFFICIENT":
            fit_schema = schemas.BlastDamageModelFitSchema(
                beta0=_safe_float(model.get("beta0")),
                beta1=_safe_float(model.get("beta1")),
                r_squared=_safe_float(model.get("r_squared")),
                p_value=_safe_float(model.get("p_value", float("nan"))),
                n=int(model.get("n", 0)),
                confidence=confidence,
                ci_beta1_low=_safe_float(model.get("ci_beta1_low")),
                ci_beta1_high=_safe_float(model.get("ci_beta1_high")),
            )

    return schemas.BlastDamageModelResponse(
        **blast_data_status(db.get_settings(session_id) or {}),
        points=points,
        fit=fit_schema,
        x_metric="pf_g_per_ton",
        y_metric="over_break",
        temporal_filter=temporal_filter,
    )


@router.get("/blast-correlation/damage-model")
async def get_blast_correlation_damage_model(
    request: Request,
    tolerance: Optional[float] = None,
    survey_date: Optional[date] = Query(default=None),
):
    """OLS fit of mean overbreak against the per-mass powder factor.

    Completes G13 visual parity with the Streamlit reference: the
    Streamlit tab draws a PF↔damage scatter with a fitted OLS line; this
    endpoint feeds the web equivalent. The fit reuses
    :func:`core.blast_model.fit_powder_factor_damage_model` (the same OLS
    primitive Streamlit uses) so the two UIs agree to the last decimal.

    Data flow reuses :func:`_resolve_blast_correlation_rows` (the helper that
    powers ``GET /process/blast-correlation``), so ``pf_g_per_ton`` and
    ``over_break`` are read off the same ``BlastCorrelationRow`` objects the
    table renders. Rows whose powder factor is zero/NaN are dropped before
    fitting — the fitter itself also masks non-finite / non-positive PF, but
    we skip them up front so the emitted ``points`` list matches the samples
    the fit consumed.

    Under-sample behaviour: :func:`fit_powder_factor_damage_model` returns a
    ``confidence='INSUFFICIENT'`` result (zeroed scalars, ``n`` = number of
    valid samples) when fewer than ``min_samples=5`` points survive. We
    translate that into ``fit=None`` so the frontend renders the scatter
    alone with an "insufficient samples" caption. Any other confidence
    (HIGH / MEDIUM / LOW) is surfaced as a populated :class:`BlastDamageModelFitSchema`.

    Empty case (no holes / no sections / no comparisons): ``points=[]`` and
    ``fit=None`` with HTTP 200 — mirrors :func:`get_blast_correlation`. NaN
    safety: every numeric field flows through :func:`_safe_float` so NaN
    never reaches the JSON payload.

    The DB reads + numpy fit run off the event loop via
    ``run_in_executor``.

    Parameters
    ----------
    tolerance : float | None
        Perpendicular inclusion radius (m) around each section axis.
        Forwarded to :func:`_resolve_blast_correlation_rows`.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )
        return await run_blast_limited(
            _build_damage_model_sync, session_id, tolerance, survey_date
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get blast damage model failed")
        raise HTTPException(500, detail=f"Get blast damage model failed: {exc}")


_ACHIEVEMENT_STATUS_MODEL = (
    "CUMPLE=1, FUERA DE TOLERANCIA=0.5, NO CUMPLE=0 for the global score; "
    "strict percentages count CUMPLE only"
)
_ACHIEVEMENT_ASSUMPTIONS = (
    "global score = mean of evaluable row scores; available weights 0.4 crest, 0.3 toe, 0.3 berma are renormalized per row",
    "partial credit: CUMPLE=1.0, FUERA DE TOLERANCIA=0.5, NO CUMPLE=0",
    "missing deltas or non-tier berm_status are excluded without inference",
)


def _filter_comparisons(
    rows: List[dict],
    sectors: Optional[List[str]],
    sections: Optional[List[str]],
    levels: Optional[List[str]],
    benches: Optional[List[str]],
) -> List[dict]:
    """Apply repeated-query filters the same way the web table does.

    Dimensions (sector / section / level / bench) are ANDed; the values
    inside one dimension are ORed. An absent or empty dimension does not
    filter. ``''`` is a selectable value (rows without that field). Bench
    matches ``bench_num`` by its string form.
    """
    dimensions = (
        ("sector", sectors),
        ("section", sections),
        ("level", levels),
        ("bench_num", benches),
    )
    out: List[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        keep = True
        for field, values in dimensions:
            if not values:
                continue
            raw = row.get(field, "")
            if raw is None:
                raw = ""
            if str(raw) not in set(values):
                keep = False
                break
        if keep:
            out.append(row)
    return out


def _build_design_achievement_sync(
    session_id: str,
    sectors: Optional[List[str]],
    sections: Optional[List[str]],
    levels: Optional[List[str]],
    benches: Optional[List[str]],
) -> dict:
    """Read-only assembly of the Logro Diseño response off the event loop.

    Rows come from the persisted comparison results of THIS session only
    (``db.get_results(session_id)``); the caller's session id is never a
    query parameter, so one session can never read another's data.
    """
    unfiltered = db.get_results(session_id)
    rows = _filter_comparisons(unfiltered, sectors, sections, levels, benches)

    settings = db.get_settings(session_id) or {}
    session_tol = (settings.get("tolerances") or {}).get("crest_toe_deviation")

    warnings: List[str] = []
    tolerances_source = "core_default"
    ct_tol: Optional[dict] = None
    if isinstance(session_tol, dict):
        try:
            build_design_achievement_summary([], session_tol)
            ct_tol = session_tol
            tolerances_source = "session"
        except (TypeError, ValueError):
            warnings.append("session_tolerance_invalid_using_core_default")

    resolved = _resolved_ct_tol_pair(ct_tol)
    summary = build_design_achievement_summary(rows, ct_tol)
    sectors_breakdown = build_sector_achievement_summary(rows, ct_tol)

    if not unfiltered:
        warnings.append("no_results")
    elif not rows:
        warnings.append("all_rows_filtered_out")
    elif summary["n_evaluable"] == 0:
        warnings.append("no_evaluable_rows")

    return {
        "session_id": session_id,
        "n_total_rows": len(rows),
        "summary": summary,
        "sectors": sectors_breakdown,
        "tolerances": resolved,
        "tolerances_source": tolerances_source,
        "filters": {
            "sector": list(sectors or []),
            "section": list(sections or []),
            "level": list(levels or []),
            "bench": list(benches or []),
        },
        "units": {"corrections": "m", "score": "0-100"},
        "status_model": _ACHIEVEMENT_STATUS_MODEL,
        "metadata": {
            "source": "persisted_comparisons",
            "status": "computed" if summary["n_evaluable"] > 0 else "no_data",
            "assumptions": list(_ACHIEVEMENT_ASSUMPTIONS),
        },
        "warnings": warnings,
    }


def _resolved_ct_tol_pair(ct_tol: Optional[dict]) -> Dict[str, float]:
    """Validated {'neg','pos'} pair from the session value or core default.

    ``ct_tol`` is ``None`` or was already validated by the core helper;
    this only re-reads the numeric pair for the response echo.
    """
    default = DEFAULT_TOLERANCES.crest_toe_deviation
    if not isinstance(ct_tol, dict):
        return {
            "neg": float(default["neg"]),
            "pos": float(default["pos"]),
        }
    return {
        "neg": float(ct_tol.get("neg", default["neg"])),
        "pos": float(ct_tol.get("pos", default["pos"])),
    }


@router.get("/design-achievement")
async def get_design_achievement(
    request: Request,
    sector: Optional[List[str]] = Query(None, alias="sector"),
    section: Optional[List[str]] = Query(None, alias="section"),
    level: Optional[List[str]] = Query(None, alias="level"),
    bench: Optional[List[str]] = Query(None, alias="bench"),
):
    """Logro Diseño summary (cresta/pata/berma) for the request's session.

    Reuses :func:`core.design_achievement.build_design_achievement_summary`
    over the persisted comparison rows of THIS session, with the session's
    ``crest_toe_deviation`` tolerance (core default when unset). Filters
    (``?sector=``/``?section=``/``?level=``/``?bench=``, repeatable) are
    ANDed across dimensions, ORed within one; ``''`` is selectable.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )
        return await _run_in_executor(
            _build_design_achievement_sync,
            session_id,
            sector,
            section,
            level,
            bench,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get design achievement failed")
        raise HTTPException(500, detail=f"Get design achievement failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/proposed-compliance — Proposal summary (wave 10)
# ---------------------------------------------------------------------------

_PROPOSED_STATUS_MODEL = (
    "proposal_status per row: 'current' (guided proposal computed), "
    "'failed' (guided failed, official row kept), missing on legacy rows "
    "(reported as not_computed)"
)
_PROPOSED_ASSUMPTIONS = (
    "official values never change: proposed_* fields are shown alongside for validation",
    "the proposal measures design benches against the raw as-built profile of each section",
    "floor compliance: |floor_offset_m| <= floor_tolerance.max per design bench",
    "split/missing benches use guided measurements when both crest and toe are measurable",
    "rows with proposal_status='failed' keep the official row and are excluded from the summary",
    "legacy rows without guided fields are not_computed and require reprocessing",
)


def _resolved_floor_tolerance(session_tolerances: Optional[dict]) -> tuple:
    """Resolve the floor tolerance actually used by the guided proposal.

    Mirrors ``core.guided_compliance._floor_max``: the session's
    ``tolerances.floor_vertical.max`` when it is a finite number, otherwise
    the core default. Returns ``({'max': float}, 'session'|'core_default')``.
    """
    floor = (session_tolerances or {}).get("floor_vertical")
    if isinstance(floor, dict):
        raw = floor.get("max")
        try:
            value = float(raw) if raw is not None else float("nan")
        except (TypeError, ValueError):
            value = float("nan")
        if math.isfinite(value):
            return {"max": value}, "session"
    default = DEFAULT_TOLERANCES.floor_vertical
    return {"max": float(default["max"])}, "core_default"


def _build_proposed_compliance_sync(
    session_id: str,
    sectors: Optional[List[str]],
    sections: Optional[List[str]],
    levels: Optional[List[str]],
    benches: Optional[List[str]],
) -> schemas.ProposedComplianceResponse:
    """Assemble the proposed-compliance summary off the event loop."""
    unfiltered = db.get_results(session_id)
    rows = _filter_comparisons(unfiltered, sectors, sections, levels, benches)

    proposal_rows: List[dict] = []
    n_failed = 0
    n_not_computed = 0
    for row in rows:
        status = row.get("proposal_status")
        if status == "current":
            proposal_rows.append(row)
        elif status == "failed":
            n_failed += 1
        else:
            n_not_computed += 1

    warnings: List[str] = []
    if not unfiltered:
        warnings.append("no_results")
    elif not rows:
        warnings.append("all_rows_filtered_out")
    if n_not_computed:
        warnings.append("reprocess_required")
    if n_failed:
        warnings.append("proposal_failed_rows")

    if proposal_rows:
        proposal_status = "current" if (n_failed == 0 and n_not_computed == 0) else "partial"
    elif n_failed:
        proposal_status = "partial"
    else:
        proposal_status = "not_computed"

    summary = summarize_proposed(proposal_rows) if proposal_rows else None
    summary_schema = (
        schemas.ProposedSummarySchema(**summary) if summary is not None else None
    )

    used_candidates = {}
    for row in proposal_rows:
        value = row.get("floor_tolerance_used")
        if isinstance(value, dict) and value:
            used_candidates[json.dumps(value, sort_keys=True)] = value
    floor_tolerance_used = None
    if len(used_candidates) == 1:
        floor_tolerance_used = next(iter(used_candidates.values()))
    elif len(used_candidates) > 1:
        warnings.append("floor_tolerance_used_mixed")
    elif proposal_rows:
        warnings.append("floor_tolerance_used_unknown")

    settings = db.get_settings(session_id) or {}
    floor_tolerance, floor_tolerance_source = _resolved_floor_tolerance(
        settings.get("tolerances")
    )

    return schemas.ProposedComplianceResponse(
        session_id=session_id,
        proposal_status=proposal_status,
        n_total_rows=len(rows),
        n_proposal_rows=len(proposal_rows),
        n_failed_rows=n_failed,
        n_not_computed_rows=n_not_computed,
        summary=summary_schema,
        floor_tolerance=floor_tolerance,
        floor_tolerance_used=floor_tolerance_used,
        floor_tolerance_source=floor_tolerance_source,
        filters={
            "sector": list(sectors or []),
            "section": list(sections or []),
            "level": list(levels or []),
            "bench": list(benches or []),
        },
        status_model=_PROPOSED_STATUS_MODEL,
        assumptions=list(_PROPOSED_ASSUMPTIONS),
        warnings=warnings,
    )


@router.get("/proposed-compliance", response_model=schemas.ProposedComplianceResponse)
async def get_proposed_compliance(
    request: Request,
    sector: Optional[List[str]] = Query(None, alias="sector"),
    section: Optional[List[str]] = Query(None, alias="section"),
    level: Optional[List[str]] = Query(None, alias="level"),
    bench: Optional[List[str]] = Query(None, alias="bench"),
):
    """Proposed compliance summary (guided proposal) for the request's session.

    Wraps :func:`core.guided_compliance.summarize_proposed` over the
    persisted comparison rows of THIS session. Only rows with
    ``proposal_status='current'`` feed the summary; rows whose guided
    computation failed keep their official values and are counted in
    ``n_failed_rows``; legacy rows without guided fields are counted in
    ``n_not_computed_rows`` (reprocess to obtain the proposal). Filters
    (``?sector=``/``?section=``/``?level=``/``?bench=``, repeatable) follow
    the same AND/OR semantics as ``GET /process/design-achievement``.
    """
    try:
        session_id = await _run_in_executor(
            db.get_or_create_session, request.state.session_id
        )
        return await _run_in_executor(
            _build_proposed_compliance_sync,
            session_id,
            sector,
            section,
            level,
            bench,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get proposed compliance failed")
        raise HTTPException(500, detail=f"Get proposed compliance failed: {exc}")
