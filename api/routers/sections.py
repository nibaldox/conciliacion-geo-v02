"""
Sections router — CRUD and generation of section lines.

Sections are stored as an ordered list in the database (one list per session).
Section IDs are index-based strings: "0", "1", "2", …
"""

import io
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from pydantic import BaseModel

import api.database as db
from core import load_mesh, load_dxf_polyline
from core.section_cutter import (
    SectionLine,
    generate_sections_along_crest,
    generate_perpendicular_sections,
    compute_local_azimuth,
)

router = APIRouter(prefix="/sections", tags=["sections"])


# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------

def get_session_id(request: Request) -> str:
    """Extract session_id set by the session middleware."""
    return request.state.session_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_mesh_from_blob(mesh_data: bytes, filename: str):
    """Load a trimesh from database BLOB via a temporary file."""
    import trimesh as _trimesh

    suffix = Path(filename).suffix or ".stl"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(mesh_data)
        return load_mesh(tmp)
    finally:
        os.unlink(tmp)


def _section_to_dict(sec: SectionLine) -> dict:
    """Convert a SectionLine dataclass to a JSON-friendly dict for DB storage."""
    return {
        "name": sec.name,
        "origin": sec.origin.tolist() if hasattr(sec.origin, "tolist") else list(sec.origin),
        "azimuth": round(float(sec.azimuth), 2),
        "length": float(sec.length),
        "sector": sec.sector,
    }


def _section_to_response(index: int, sec_dict: dict) -> dict:
    """Convert a stored section dict to an API response with index-based ID."""
    return {
        "id": str(index),
        "name": sec_dict["name"],
        "origin": sec_dict["origin"],
        "azimuth": sec_dict["azimuth"],
        "length": sec_dict["length"],
        "sector": sec_dict["sector"],
    }


def _dict_to_section(d: dict) -> SectionLine:
    """Convert a stored section dict back into a SectionLine."""
    return SectionLine(
        name=d["name"],
        origin=np.array(d["origin"], dtype=float),
        azimuth=float(d["azimuth"]),
        length=float(d["length"]),
        sector=d.get("sector", ""),
    )


def _get_design_mesh(session_id: str):
    """Load the design mesh from DB or raise 400."""
    mesh = db.get_mesh(session_id, "design")
    if mesh is None:
        raise HTTPException(400, "Upload design mesh first")
    return _load_mesh_from_blob(mesh["data"], mesh["filename"])


def _save_sections(session_id: str, sections: List[SectionLine]):
    """Persist a list of SectionLine objects to the database."""
    db.save_sections(session_id, [_section_to_dict(s) for s in sections])


def _load_sections(session_id: str) -> List[dict]:
    """Load stored section dicts from the database."""
    return db.get_sections(session_id)


# ---------------------------------------------------------------------------
# Pydantic models for request bodies
# ---------------------------------------------------------------------------

class SectionAutoParams(BaseModel):
    """Parameters for auto-generating sections along a crest line."""
    start: List[float]       # [x, y]
    end: List[float]         # [x, y]
    n_sections: int = 5
    length: float = 200.0
    sector: str = ""
    az_method: str = "perpendicular"  # "perpendicular" | "fixed" | "local_slope"
    fixed_az: float = 0.0


class SectionCreate(BaseModel):
    """Single section definition."""
    name: Optional[str] = None
    origin: List[float]      # [x, y]
    azimuth: float
    length: float = 200.0
    sector: str = ""


class SectionClickParams(BaseModel):
    """Parameters for adding a section by click on plan view."""
    origin: List[float]      # [x, y]
    length: float = 200.0
    sector: str = ""
    az_mode: str = "auto"    # "auto" | "manual"
    azimuth: Optional[float] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_sections(request: Request):
    """Return all sections for the current session."""
    session_id = get_session_id(request)
    sections = _load_sections(session_id)
    return [_section_to_response(i, s) for i, s in enumerate(sections)]


@router.post("/auto")
def sections_auto(request: Request, params: SectionAutoParams):
    """
    Generate sections evenly spaced along a start→end line.

    Supports three azimuth methods:
    - **perpendicular**: sections perpendicular to the crest line (default).
    - **fixed**: all sections use ``fixed_az``.
    - **local_slope**: compute azimuth from design mesh slope at each section origin.
    """
    session_id = get_session_id(request)
    design_mesh = _get_design_mesh(session_id)

    start = np.array(params.start, dtype=float)
    end = np.array(params.end, dtype=float)
    n = params.n_sections
    length = params.length
    sector = params.sector

    # Determine azimuth strategy
    az: Optional[float] = None
    if params.az_method == "fixed":
        az = params.fixed_az
    elif params.az_method == "local_slope":
        az = 0.0  # placeholder, overwritten per section below

    sections = generate_sections_along_crest(
        design_mesh, start, end, n, az, length, sector
    )

    # Override azimuth with local slope if requested
    if params.az_method == "local_slope":
        for sec in sections:
            sec.azimuth = compute_local_azimuth(design_mesh, sec.origin)

    _save_sections(session_id, sections)

    stored = _load_sections(session_id)
    return {
        "sections": [_section_to_response(i, s) for i, s in enumerate(stored)],
    }


@router.post("/manual")
def sections_manual(request: Request, sections_data: List[SectionCreate]):
    """Set sections from manual input (replaces any existing sections)."""
    session_id = get_session_id(request)
    sections: List[SectionLine] = []
    for idx, s in enumerate(sections_data):
        sec = SectionLine(
            name=s.name or f"S-{idx + 1:02d}",
            origin=np.array(s.origin, dtype=float),
            azimuth=float(s.azimuth),
            length=float(s.length),
            sector=s.sector,
        )
        sections.append(sec)

    _save_sections(session_id, sections)
    stored = _load_sections(session_id)
    return {
        "message": f"{len(stored)} sections set",
        "sections": [_section_to_response(i, s) for i, s in enumerate(stored)],
    }


@router.post("/click")
def add_section_click(request: Request, params: SectionClickParams):
    """
    Add a single section by clicking on the plan view.

    If ``az_mode`` is ``"auto"``, computes azimuth from the design mesh slope.
    Appends to existing sections.
    """
    session_id = get_session_id(request)
    origin = np.array(params.origin, dtype=float)
    length = params.length
    sector = params.sector

    if params.az_mode == "auto":
        design_mesh = _get_design_mesh(session_id)
        az = compute_local_azimuth(design_mesh, origin)
    else:
        az = params.azimuth if params.azimuth is not None else 0.0

    # Load existing sections
    existing = _load_sections(session_id)
    n = len(existing) + 1
    sec = SectionLine(
        name=f"S-{n:02d}",
        origin=origin,
        azimuth=az,
        length=length,
        sector=sector,
    )

    # Append and save
    new_sections = existing + [_section_to_dict(sec)]
    db.save_sections(session_id, new_sections)

    stored = _load_sections(session_id)
    return {
        "section": _section_to_response(len(stored) - 1, stored[-1]),
        "total": len(stored),
    }


@router.post("/from-file")
async def sections_from_file(
    request: Request,
    file: UploadFile = File(...),
    spacing: str = Form("20.0"),
    length: str = Form("200.0"),
    sector: str = Form("Principal"),
    az_mode: str = Form("perpendicular"),  # "perpendicular" | "local_slope"
):
    """
    Generate sections from a CSV (X, Y columns) or DXF polyline file.

    Parses the uploaded file as a polyline, then calls
    ``generate_perpendicular_sections()``.
    """
    session_id = get_session_id(request)
    design_mesh = _get_design_mesh(session_id)

    spacing_f = float(spacing)
    length_f = float(length)

    fname = (file.filename or "").lower()
    content = await file.read()
    polyline = None

    if fname.endswith(".dxf"):
        # Write to temp file for DXF loading
        fd, tmp = tempfile.mkstemp(suffix=".dxf")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            polyline = load_dxf_polyline(tmp)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        if polyline is None or len(polyline) == 0:
            raise HTTPException(400, "No polylines found in DXF")
    else:
        # CSV / TXT
        df = pd.read_csv(io.BytesIO(content), nrows=10000)
        x_col = next(
            (c for c in df.columns if c.strip().upper() in ("X", "ESTE", "EAST", "E")),
            None,
        )
        y_col = next(
            (c for c in df.columns if c.strip().upper() in ("Y", "NORTE", "NORTH", "N")),
            None,
        )
        if x_col is None or y_col is None:
            num_cols = df.select_dtypes(include=[np.number]).columns
            if len(num_cols) >= 2:
                x_col, y_col = num_cols[0], num_cols[1]
            else:
                raise HTTPException(400, "Could not find X/Y columns")
        polyline = df[[x_col, y_col]].dropna().values.astype(float)

    if len(polyline) < 2:
        raise HTTPException(400, "Polyline must have at least 2 points")

    mesh_for_az = design_mesh if az_mode == "local_slope" else None
    sections = generate_perpendicular_sections(
        polyline, spacing_f, length_f, sector, design_mesh=mesh_for_az
    )

    _save_sections(session_id, sections)

    stored = _load_sections(session_id)
    return {
        "sections": [_section_to_response(i, s) for i, s in enumerate(stored)],
        "polyline": polyline.tolist() if hasattr(polyline, "tolist") else list(polyline),
    }


@router.put("/{section_id}")
def update_section(request: Request, section_id: str, body: SectionCreate):
    """
    Update a single section by its index-based ID.

    Replaces the section at the given index with new data.
    """
    session_id = get_session_id(request)
    sections = _load_sections(session_id)

    try:
        idx = int(section_id)
    except ValueError:
        raise HTTPException(400, "section_id must be an integer index")

    if idx < 0 or idx >= len(sections):
        raise HTTPException(404, f"Section index {idx} out of range (0-{len(sections) - 1})")

    # Preserve original name if not provided
    updated = {
        "name": body.name or sections[idx]["name"],
        "origin": list(body.origin),
        "azimuth": round(float(body.azimuth), 2),
        "length": float(body.length),
        "sector": body.sector,
    }
    sections[idx] = updated
    db.save_sections(session_id, sections)

    return _section_to_response(idx, updated)


@router.delete("/{section_id}")
def delete_section(request: Request, section_id: str):
    """Delete a single section by its index-based ID."""
    session_id = get_session_id(request)
    sections = _load_sections(session_id)

    try:
        idx = int(section_id)
    except ValueError:
        raise HTTPException(400, "section_id must be an integer index")

    if idx < 0 or idx >= len(sections):
        raise HTTPException(404, f"Section index {idx} out of range (0-{len(sections) - 1})")

    removed = sections.pop(idx)
    db.save_sections(session_id, sections)

    return {
        "message": f"Section '{removed['name']}' deleted",
        "total": len(sections),
    }


@router.delete("")
def clear_sections(request: Request):
    """Clear all sections for the current session."""
    session_id = get_session_id(request)
    db.save_sections(session_id, [])
    return {"message": "All sections cleared"}
