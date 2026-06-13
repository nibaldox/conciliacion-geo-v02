"""
Process router — pipeline execution, status, profiles, and interactive editing.

Endpoints:
    POST /process                      Run full cut-extract-compare pipeline
    GET  /process/status               Return current processing status
    GET  /profiles/{section_id}        Return profile data for a section
    PUT  /results/{section_id}/reconciled  Update benches after drag & drop
"""

import os
import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
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
)
from core.param_extractor import (
    BenchParams,
    ExtractionResult,
    ReconciledPoint,
    build_reconciled_profile_v2,
)
from core.section_cutter import azimuth_to_direction, ProfileResult


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
    """Serialise a ReconciledProfile (distances, elevations, points)."""
    return {
        "distances": prof.distances.tolist() if len(prof.distances) > 0 else [],
        "elevations": prof.elevations.tolist() if len(prof.elevations) > 0 else [],
        "segments": [_reconciled_point_to_dict(p) for p in prof.points],
    }


from core.config import DETECTION, TOLERANCES as DEFAULT_TOLERANCES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/process", tags=["process"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _profile_to_dict(prof: Optional[ProfileResult]) -> Optional[dict]:
    """Serialise a ProfileResult for the profile cache (None stays None)."""
    if prof is None:
        return None
    return {
        "distances": prof.distances.tolist(),
        "elevations": prof.elevations.tolist(),
    }


def _profile_from_dict(d: Optional[dict]) -> Optional[ProfileResult]:
    """Deserialise a cached profile dict back into a ProfileResult."""
    if d is None:
        return None
    return ProfileResult(
        distances=np.asarray(d["distances"], dtype=float),
        elevations=np.asarray(d["elevations"], dtype=float),
    )


def _profiles_for_section(
    session_id: str,
    sec: SectionLine,
    mesh_design: trimesh.Trimesh,
    mesh_topo: trimesh.Trimesh,
) -> Tuple[Optional[ProfileResult], Optional[ProfileResult]]:
    """Return (design, topo) profiles for a section.

    Uses the profile cache persisted by POST /process; falls back to cutting
    the meshes when the cache is missing (e.g. sessions processed before the
    cache existed).
    """
    cached = db.get_profile_cache(session_id, sec.name)
    if "design" in cached and "topo" in cached:
        return _profile_from_dict(cached["design"]), _profile_from_dict(cached["topo"])
    return cut_both_surfaces(mesh_design, mesh_topo, sec)


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


# ---------------------------------------------------------------------------
# POST /process — Run full pipeline
# ---------------------------------------------------------------------------


@router.post("")
def run_process(request: Request, body: Optional[schemas.ProcessSettings] = None):
    """
    Run the full geotechnical reconciliation pipeline:
    cut all sections → extract parameters → compare design vs as-built.

    Uses ThreadPoolExecutor for parallel section processing.
    Results and extraction cache are persisted to the database.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        # Validate preconditions
        sections_raw = db.get_sections(session_id)
        if not sections_raw:
            raise HTTPException(400, "Load sections first")

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

        if body is not None:
            body_dict = body.model_dump() if hasattr(body, "model_dump") else body.dict()
            process_cfg.update(body_dict.get("process", {}))
            tolerances.update(body_dict.get("tolerances", {}))

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

        # Pre-warm trimesh lazy caches in the main thread so worker threads
        # don't race to compute them (results are unaffected).
        for _mesh in (mesh_design, mesh_topo):
            _ = _mesh.vertices
            _ = _mesh.faces

        # Allocate result containers
        params_design_list: List[Optional[ExtractionResult]] = [None] * len(sections)
        params_topo_list: List[Optional[ExtractionResult]] = [None] * len(sections)
        profile_design_list: List[Optional[ProfileResult]] = [None] * len(sections)
        profile_topo_list: List[Optional[ProfileResult]] = [None] * len(sections)
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
                    return idx, sec, p_d, p_t, comps, pd_prof, pt_prof
                else:
                    p_d_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
                    p_t_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
                    return idx, sec, p_d_empty, p_t_empty, [], pd_prof, pt_prof
            except Exception as exc:
                logger.exception("Section %s processing failed: %s", sec.name, exc)
                p_d_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
                p_t_empty = ExtractionResult(section_name=sec.name, sector=sec.sector)
                return idx, sec, p_d_empty, p_t_empty, [], None, None

        # Execute in parallel. Status updates are throttled to avoid one
        # SQLite commit per section (a major cost with many sections).
        completed = 0
        last_status = 0.0
        with ThreadPoolExecutor() as executor:
            for idx, sec, p_d, p_t, comps, pd_prof, pt_prof in executor.map(
                _process_section, enumerate(sections)
            ):
                params_design_list[idx] = p_d
                params_topo_list[idx] = p_t
                profile_design_list[idx] = pd_prof
                profile_topo_list[idx] = pt_prof
                comparison_results.extend(comps)
                completed += 1
                now = time.monotonic()
                if now - last_status >= 0.5 or completed == len(sections):
                    db.update_process_status(
                        session_id, "processing", completed, len(sections)
                    )
                    last_status = now

        # Persist results
        # Save extraction + raw profile caches in bulk (single transaction
        # each) instead of one commit per section.
        extraction_rows: List[Tuple[str, str, dict]] = []
        profile_rows: List[Tuple[str, str, Optional[dict]]] = []
        for idx, sec in enumerate(sections):
            if params_design_list[idx] is not None:
                extraction_rows.append(
                    (sec.name, "design", _extraction_to_dict(params_design_list[idx]))
                )
            if params_topo_list[idx] is not None:
                extraction_rows.append(
                    (sec.name, "topo", _extraction_to_dict(params_topo_list[idx]))
                )
            profile_rows.append(
                (sec.name, "design", _profile_to_dict(profile_design_list[idx]))
            )
            profile_rows.append(
                (sec.name, "topo", _profile_to_dict(profile_topo_list[idx]))
            )
        db.save_extractions_bulk(session_id, extraction_rows)
        db.save_profiles_bulk(session_id, profile_rows)

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
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Run process failed")
        raise HTTPException(500, detail=f"Run process failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/status
# ---------------------------------------------------------------------------


@router.get("/status")
def get_status(request: Request):
    """Return the current processing status for the session."""
    try:
        session_id = db.get_or_create_session(request.state.session_id)
        raw = db.get_process_status(session_id)
        n_results = db.get_results_count(session_id)
        return schemas.ProcessStatus(
            status=raw.get("status", "idle"),
            current_section=raw.get("current_section") or None,
            total_sections=raw.get("total_sections") or None,
            completed_sections=raw.get("completed_sections", 0),
            n_results=n_results,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get status failed")
        raise HTTPException(500, detail=f"Get status failed: {exc}")


# ---------------------------------------------------------------------------
# GET /process/results — List all comparison results
# ---------------------------------------------------------------------------


@router.get("/results")
def get_results(request: Request, section: Optional[str] = None):
    """Return all comparison results, optionally filtered by section."""
    try:
        session_id = db.get_or_create_session(request.state.session_id)
        results = db.get_results(session_id, section=section)
        return results
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get results failed")
        raise HTTPException(500, detail=f"Get results failed: {exc}")


# ---------------------------------------------------------------------------
# GET /profiles/{section_id}
# ---------------------------------------------------------------------------


@router.get("/profiles/{section_id}")
def get_profile(request: Request, section_id: int):
    """
    Return profile data for a section by its index in the sections list.

    Includes raw design/topo profiles, reconciled profiles from the
    extraction cache, and bench data for interactive editing.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

        sections_raw = db.get_sections(session_id)
        if section_id < 0 or section_id >= len(sections_raw):
            raise HTTPException(404, "Section index out of range")

        sec = _section_from_dict(sections_raw[section_id])

        # Load meshes and resolve profiles (cache first, cut as fallback)
        try:
            mesh_design = _load_mesh_from_db(session_id, "design")
            mesh_topo = _load_mesh_from_db(session_id, "topo")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"Error loading meshes: {exc}")

        pd_prof, pt_prof = _profiles_for_section(session_id, sec, mesh_design, mesh_topo)

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

        # Reconciled profiles from extraction cache. We use the v2
        # builder so the response carries the structured ``segments``
        # list (with explicit berm/ramp classifications) in addition
        # to the legacy ``distances``/``elevations`` arrays.
        design_extraction = db.get_extraction(session_id, sec.name, "design")
        if design_extraction:
            benches_d = [_dict_to_bench(b) for b in design_extraction.get("benches", [])]
            if benches_d:
                prof_d = build_reconciled_profile_v2(benches_d, source="design")
                result["reconciled_design"] = _reconciled_profile_to_dict(prof_d)

        topo_extraction = db.get_extraction(session_id, sec.name, "topo")
        if topo_extraction:
            benches_t = [_dict_to_bench(b) for b in topo_extraction.get("benches", [])]
            if benches_t:
                prof_t = build_reconciled_profile_v2(benches_t, source="topo")
                result["reconciled_topo"] = _reconciled_profile_to_dict(prof_t)
                result["benches_topo"] = [_bench_to_dict(b) for b in benches_t]

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get profile failed")
        raise HTTPException(500, detail=f"Get profile failed: {exc}")


# ---------------------------------------------------------------------------
# PUT /results/{section_id}/reconciled — Interactive bench editing
# ---------------------------------------------------------------------------


@router.put("/results/{section_id}/reconciled")
def update_reconciled(
    request: Request, section_id: int, body: List[schemas.BenchParamsSchema]
):
    """
    Update benches after drag & drop editing in the UI.

    Receives updated crest/toe positions, recalculates derived values
    (height, angle, berm width), re-runs comparison for this section,
    and returns the updated reconciled profile.
    """
    try:
        session_id = db.get_or_create_session(request.state.session_id)

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

        for i, bench_update in enumerate(body):
            update_dict = (
                bench_update.model_dump()
                if hasattr(bench_update, "model_dump")
                else bench_update.dict()
            )
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Update reconciled failed")
        raise HTTPException(500, detail=f"Update reconciled failed: {exc}")
