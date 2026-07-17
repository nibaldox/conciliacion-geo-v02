"""
Process router — pipeline execution, status, profiles, and interactive editing.

Endpoints:
    POST /process                      Run full cut-extract-compare pipeline
    GET  /process/status               Return current processing status
    GET  /profiles/{section_id}        Return profile data for a section
    PUT  /results/{section_id}/reconciled  Update benches after drag & drop
"""

import asyncio
import logging
import math
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import trimesh
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Request

import api.database as db
import api.schemas as schemas
from core import (
    load_mesh,
    SectionLine,
    cut_both_surfaces,
    extract_parameters,
    compare_design_vs_asbuilt,
    build_reconciled_profile,
)
from core.param_extractor import (
    BenchParams,
    ExtractionResult,
    ReconciledPoint,
    build_reconciled_profile_v2,
)
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.blast_correlation import compute_blast_geotech_correlation
from core.blast_model import fit_powder_factor_damage_model
from core.config import DEFAULTS, DETECTION, TOLERANCES as DEFAULT_TOLERANCES

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


def _safe_float(value, ndigits: int = 3) -> float:
    """Coerce to a JSON-safe rounded float; NaN/None -> 0.0."""
    if value is None:
        return 0.0
    f = float(value)
    return round(f, ndigits) if math.isfinite(f) else 0.0


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
            }
            for b in er.benches
        ],
        "inter_ramp_angle": er.inter_ramp_angle,
        "overall_angle": er.overall_angle,
    }


def _section_from_dict(d: dict) -> SectionLine:
    """Reconstruct a SectionLine from a database dict."""
    return SectionLine(
        name=d["name"],
        origin=np.array(d["origin"]),
        azimuth=float(d["azimuth"]),
        length=float(d.get("length", 200)),
        sector=d.get("sector", ""),
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


def _legacy_reconciled_to_dict(benches) -> dict:
    """Streamlit-equivalent reconciled polyline as flat ``(distances, elevations)``
    arrays.

    Calls the legacy ``build_reconciled_profile`` path (the exact builder
    used by ``ui/step3_analysis.py``) so the Web UI can render the same
    crest/toe polyline that Streamlit draws. The ``DeprecationWarning`` is
    expected here by design and silenced, since the legacy shape is being
    produced deliberately for cross-UI parity (see docs/UI_PARITY_AUDIT.md,
    Causa 2).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        distances, elevations = build_reconciled_profile(benches)
    return {
        "distances": distances.tolist(),
        "elevations": elevations.tolist(),
    }


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
            pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sec)
            if pd_prof is not None and pt_prof is not None:
                p_d = extract_parameters(
                    pd_prof.distances,
                    pd_prof.elevations,
                    sec.name,
                    sec.sector,
                    resolution,
                    face_threshold,
                    berm_threshold,
                )
                p_t = extract_parameters(
                    pt_prof.distances,
                    pt_prof.elevations,
                    sec.name,
                    sec.sector,
                    resolution,
                    face_threshold,
                    berm_threshold,
                )
                comps = compare_design_vs_asbuilt(p_d, p_t, tolerances)
                return idx, sec, p_d, p_t, comps
            else:
                p_d_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
                p_t_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
                return idx, sec, p_d_empty, p_t_empty, []
        except Exception as exc:
            logger.exception("Section %s processing failed: %s", sec.name, exc)
            p_d_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
            p_t_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
            return idx, sec, p_d_empty, p_t_empty, []

    # Execute in parallel (inside the executor thread, so this pool only
    # uses background threads; no event-loop blocking).
    completed = 0
    with ThreadPoolExecutor() as executor:
        for idx, sec, p_d, p_t, comps in executor.map(
            _process_section, enumerate(sections)
        ):
            params_design_list[idx] = p_d
            params_topo_list[idx] = p_t
            comparison_results.extend(comps)
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
    except HTTPException:
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

    pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sec)

    result: Dict[str, Any] = {
        "section_name": sec.name,
        "sector": sec.sector,
        "origin": sec.origin.tolist(),
        "azimuth": sec.azimuth,
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
    design_extraction = db.get_extraction(session_id, sec.name, "design")
    if design_extraction:
        benches_d = [_dict_to_bench(b) for b in design_extraction.get("benches", [])]
        if benches_d:
            prof_d = build_reconciled_profile_v2(
                benches_d, source="design", profile=profile_d_arg,
            )
            result["reconciled_design"] = _reconciled_profile_to_dict(prof_d)
            result["reconciled_design_legacy"] = _legacy_reconciled_to_dict(benches_d)

    topo_extraction = db.get_extraction(session_id, sec.name, "topo")
    if topo_extraction:
        benches_t = [_dict_to_bench(b) for b in topo_extraction.get("benches", [])]
        if benches_t:
            prof_t = build_reconciled_profile_v2(
                benches_t, source="topo", profile=profile_t_arg,
            )
            result["reconciled_topo"] = _reconciled_profile_to_dict(prof_t)
            result["reconciled_topo_legacy"] = _legacy_reconciled_to_dict(benches_t)
            result["benches_topo"] = [_bench_to_dict(b) for b in benches_t]

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
        new_comps = compare_design_vs_asbuilt(p_design, p_topo, tolerances)

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
) -> List[schemas.BlastHoleOnProfile]:
    """Map a projected blast-hole DataFrame to ``BlastHoleOnProfile`` schemas.

    ``projected`` is the output of
    :func:`core.calculo_tronadura.proyectar_pozos_en_seccion`: each row carries
    ``dist_along`` (along-section distance), ``dist_perp`` (perpendicular
    distance), and the original hole columns (``Z_collar``, ``Burden``, ``Esp``
    …) when present.

    ``spacing`` falls back to the nearest-neighbour collar distance when the
    ``Esp`` column is missing. ``burden`` defaults to 0 when absent.
    """
    if projected is None or projected.empty:
        return []

    cols = set(projected.columns)
    has_hole_id = "hole_id" in cols
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
        d_perp = float(getattr(row, "dist_perp", 0.0))

        if has_burden:
            burden_raw = getattr(row, "Burden", 0.0)
            burden = float(burden_raw) if pd.notna(burden_raw) else 0.0
        else:
            burden = 0.0

        if has_esp:
            esp_raw = getattr(row, "Esp", None)
            spacing = float(esp_raw) if esp_raw is not None and pd.notna(esp_raw) else 0.0
        elif spacing_fallback is not None:
            spacing = spacing_fallback[i]
        else:
            spacing = 0.0

        if has_z_collar:
            z_raw = getattr(row, "Z_collar", 0.0)
            elevation = float(z_raw) if pd.notna(z_raw) else 0.0
        else:
            elevation = 0.0

        hole_id = str(getattr(row, "hole_id", i)) if has_hole_id else str(i)

        out.append(schemas.BlastHoleOnProfile(
            hole_id=hole_id,
            distance=round(float(getattr(row, "dist_along", 0.0)), 3),
            elevation=round(elevation, 3),
            burden=round(burden, 3),
            spacing=round(spacing, 3),
            is_within_tolerance=bool(d_perp <= tolerance + 1e-9),
        ))
    return out


@router.get("/profiles/{section_id}/blast-holes")
def get_blast_holes(
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
        session_id = db.get_or_create_session(request.state.session_id)

        sections_raw = db.get_sections(session_id)
        if section_id < 0 or section_id >= len(sections_raw):
            return schemas.BlastHolesOnProfileResponse(
                section_id="",
                mesh_id=mesh_id,
                tolerance=tolerance,
                holes=[],
            )

        sec = _section_from_dict(sections_raw[section_id])

        df_holes = _load_session_blast_holes(session_id)
        if df_holes is None or df_holes.empty:
            return schemas.BlastHolesOnProfileResponse(
                section_id=sec.name,
                mesh_id=mesh_id,
                tolerance=tolerance,
                holes=[],
            )

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
        holes = _projected_to_holes(projected, float(tolerance))
        return schemas.BlastHolesOnProfileResponse(
            section_id=sec.name,
            mesh_id=mesh_id,
            tolerance=tolerance,
            holes=holes,
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
        return [], sections_raw, resolved_tolerance

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
    return rows, sections_raw, resolved_tolerance


@router.get("/blast-correlation")
def get_blast_correlation(
    request: Request,
    tolerance: Optional[float] = None,
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

    Parameters
    ----------
    tolerance : float | None
        Perpendicular inclusion radius in metres around each section axis.
        ``None`` (default) defers to ``DEFAULTS.blast_correlation_radius_m``
        inside the core primitive.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        rows, sections_raw, resolved_tolerance = _resolve_blast_correlation_rows(
            session_id, tolerance
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
                energy_total_mj=_safe_float(r.energy_total_mj),
                n_pf_valid=int(r.n_pf_valid),
                sector=str(getattr(r, "sector", "") or ""),
                rock_density_used=_safe_float(getattr(r, "rock_density_used", 0.0)),
            )
            for r in rows
        ]

        return schemas.BlastCorrelationResponse(
            rows=schema_rows,
            tolerance=resolved_tolerance,
            n_sections=len(sections_raw),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get blast correlation failed")
        raise HTTPException(500, detail=f"Get blast correlation failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/blast-correlation/damage-model
# ---------------------------------------------------------------------------


@router.get("/blast-correlation/damage-model")
def get_blast_correlation_damage_model(
    request: Request,
    tolerance: Optional[float] = None,
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

    Parameters
    ----------
    tolerance : float | None
        Perpendicular inclusion radius (m) around each section axis.
        Forwarded to :func:`_resolve_blast_correlation_rows`.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)
        rows, _sections_raw, _tol = _resolve_blast_correlation_rows(
            session_id, tolerance
        )

        # Build the (PF, overbreak) sample, dropping zero/NaN PF rows so the
        # emitted points match the samples the fitter consumes.
        points: List[schemas.BlastDamagePointSchema] = []
        pf_values_list: List[float] = []
        dmg_values_list: List[float] = []
        for r in rows:
            pf = float(r.pf_g_per_ton_avg)
            over = float(r.avg_over_break)
            if not math.isfinite(pf) or not math.isfinite(over):
                continue
            if pf <= 0.0:
                continue
            points.append(schemas.BlastDamagePointSchema(
                section_name=str(r.section_name),
                pf_g_per_ton=_safe_float(pf),
                over_break=_safe_float(over),
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
                    beta0=_safe_float(model.get("beta0", 0.0)),
                    beta1=_safe_float(model.get("beta1", 0.0)),
                    r_squared=_safe_float(model.get("r_squared", 0.0)),
                    p_value=_safe_float(model.get("p_value", float("nan"))),
                    n=int(model.get("n", 0)),
                    confidence=confidence,
                    ci_beta1_low=_safe_float(model.get("ci_beta1_low", 0.0)),
                    ci_beta1_high=_safe_float(model.get("ci_beta1_high", 0.0)),
                )

        return schemas.BlastDamageModelResponse(
            points=points,
            fit=fit_schema,
            x_metric="pf_g_per_ton",
            y_metric="over_break",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get blast damage model failed")
        raise HTTPException(500, detail=f"Get blast damage model failed: {exc}")
