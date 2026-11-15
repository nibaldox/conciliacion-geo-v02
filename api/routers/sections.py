"""
Sections router — CRUD and generation of section lines.

Sections are stored as an ordered list in the database (one list per session).
Section IDs are index-based strings: "0", "1", "2", …
"""

import io
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from pydantic import BaseModel

import api.database as db
from api._async_db import run_db
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


def _load_mesh_from_blob(mesh_data: bytes, filename: str, import_options: dict | None = None):
    """Load a trimesh from database BLOB via a temporary file."""
    import trimesh as _trimesh

    suffix = Path(filename).suffix or ".stl"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(mesh_data)
        if import_options and Path(filename).suffix.lower() == ".dxf":
            from core import import_dxf_surface
            mesh, _ = import_dxf_surface(
                tmp,
                layers=import_options.get("layers"),
                units=import_options.get("units"),
            )
            return mesh
        return load_mesh(tmp)
    finally:
        os.unlink(tmp)


def _section_to_dict(sec: SectionLine) -> dict:
    """Convert a SectionLine dataclass to a JSON-friendly dict for DB storage."""
    return {
        "name": sec.name,
        "origin": sec.origin.tolist()
        if hasattr(sec.origin, "tolist")
        else list(sec.origin),
        "azimuth": round(float(sec.azimuth), 2),
        "length": float(sec.length),
        "length_up": float(sec.length_up) if getattr(sec, 'length_up', None) is not None else None,
        "length_down": float(sec.length_down) if getattr(sec, 'length_down', None) is not None else None,
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
        "length_up": sec_dict.get("length_up"),
        "length_down": sec_dict.get("length_down"),
        "sector": sec_dict["sector"],
    }


def _dict_to_section(d: dict) -> SectionLine:
    """Convert a stored section dict back into a SectionLine."""
    return SectionLine(
        name=d["name"],
        origin=np.array(d["origin"], dtype=float),
        azimuth=float(d["azimuth"]),
        length=float(d["length"]),
        length_up=d.get("length_up"),
        length_down=d.get("length_down"),
        sector=d.get("sector", ""),
    )


def _read_polyline_xy_csv(content: bytes) -> np.ndarray:
    preview = pd.read_csv(io.BytesIO(content), header=None, nrows=1)
    first_row_is_data = (
        preview.shape[1] >= 2
        and not preview.empty
        and pd.to_numeric(preview.iloc[0, :2], errors="coerce").notna().all()
    )
    df = pd.read_csv(
        io.BytesIO(content),
        header=None if first_row_is_data else 0,
        nrows=10000,
    )
    x_col = next(
        (c for c in df.columns if str(c).strip().upper() in ("X", "ESTE", "EAST", "E")),
        None,
    )
    y_col = next(
        (
            c
            for c in df.columns
            if str(c).strip().upper() in ("Y", "NORTE", "NORTH", "N")
        ),
        None,
    )
    if x_col is None or y_col is None:
        num_cols = df.select_dtypes(include=[np.number]).columns
        if len(num_cols) >= 2:
            x_col, y_col = num_cols[0], num_cols[1]
        else:
            raise ValueError("Could not find X/Y columns")
    return df[[x_col, y_col]].dropna().values.astype(float)


async def _get_design_mesh(session_id: str):
    """Load the design mesh from DB or raise 400.

    Runs the SQLite ``get_mesh`` lookup on the worker thread; the
    secondary ``get_trimesh_by_id`` call is then performed inline (the
    trimesh reconstruction itself is a CPU/IO-bound chunk already handed
    off to the threadpool by FastAPI for any subsequent ``def`` caller).
    """
    mesh = await run_db(db.get_mesh, session_id, "design")
    if mesh is None:
        raise HTTPException(400, "Upload design mesh first")
    return db.get_trimesh_by_id(mesh["id"])


async def _save_sections(session_id: str, sections: List[SectionLine]):
    """Persist a list of SectionLine objects, replacing the stored list."""
    await run_db(db.save_sections, session_id, [_section_to_dict(s) for s in sections])


async def _load_sections(session_id: str) -> List[dict]:
    """Load stored section dicts from the database."""
    return await run_db(db.get_sections, session_id)


_BUSY_STATUSES = frozenset({"running", "processing"})


async def _ensure_sections_mutable(session_id: str) -> None:
    """Reject mutations while the processing pipeline owns the session."""
    status = await run_db(db.get_process_status, session_id)
    if status["status"] in _BUSY_STATUSES:
        raise HTTPException(
            409,
            "Analysis is running; wait for it to finish before changing sections",
        )


def _unique_section_name(name: str, used: set) -> str:
    """Return ``name`` or the first free ``name_{n}`` suffix."""
    if name not in used:
        return name
    index = 1
    while f"{name}_{index}" in used:
        index += 1
    return f"{name}_{index}"


async def _append_sections(session_id: str, new_sections: List[SectionLine]) -> List[dict]:
    """Append sections to the stored list, suffixing colliding names.

    Mirrors ``ui/step2_sections/state.py::add_sections``: names already in
    the list (or used earlier in the same batch) receive the first free
    ``_{n}`` suffix. Any non-empty batch invalidates the analysis.
    """
    stored = await _load_sections(session_id)
    if not new_sections:
        return stored
    used = {s["name"] for s in stored}
    appended: List[dict] = []
    for sec in new_sections:
        sec.name = _unique_section_name(sec.name, used)
        used.add(sec.name)
        appended.append(_section_to_dict(sec))
    await run_db(db.save_sections, session_id, stored + appended)
    await run_db(db.invalidate_analysis, session_id)
    return stored + appended


async def _replace_sections(session_id: str, sections: List[SectionLine]) -> List[dict]:
    """Replace the stored list, invalidating analysis only on a real change."""
    stored = await _load_sections(session_id)
    replacement = [_section_to_dict(s) for s in sections]
    if replacement == stored:
        return stored
    await run_db(db.save_sections, session_id, replacement)
    await run_db(db.invalidate_analysis, session_id)
    return replacement


def _section_index(section_id: str, count: int) -> int:
    """Parse an index-based section id and check it against ``count`` sections."""
    try:
        idx = int(section_id)
    except ValueError:
        raise HTTPException(400, "section_id must be an integer index")
    if idx < 0 or idx >= count:
        raise HTTPException(
            404, f"Section index {idx} out of range (0-{count - 1})"
        )
    return idx


def _section_dict_from_body(body: "SectionCreate", fallback_name: str) -> dict:
    """Normalize an edit body the way PUT /sections/{id} stores it."""
    return {
        "name": body.name or fallback_name,
        "origin": list(body.origin),
        "azimuth": round(float(body.azimuth), 2),
        "length": float(body.length),
        "length_up": float(body.length_up) if body.length_up is not None else None,
        "length_down": float(body.length_down) if body.length_down is not None else None,
        "sector": body.sector,
    }


_SECTION_EDIT_FIELDS: tuple[str, ...] = (
    "name",
    "origin",
    "azimuth",
    "length",
    "length_up",
    "length_down",
    "sector",
)


class SectionNameTakenError(ValueError):
    """An agent edit asked for a name that another section already has."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _merge_section_overrides(current: dict, overrides: Mapping[str, Any]) -> "SectionCreate":
    """Return the stored section with every non-None override applied."""
    values: Dict[str, Any] = {
        "name": current["name"],
        "origin": current["origin"],
        "azimuth": current["azimuth"],
        "length": current["length"],
        "length_up": current.get("length_up"),
        "length_down": current.get("length_down"),
        "sector": current.get("sector", ""),
    }
    values.update(
        {
            field: overrides[field]
            for field in _SECTION_EDIT_FIELDS
            if overrides.get(field) is not None
        }
    )
    return SectionCreate(**values)


def _update_section_sync(
    session_id: str,
    section_id: str,
    body: Optional["SectionCreate"] = None,
    overrides: Optional[Mapping[str, Any]] = None,
    *,
    reject_duplicate_name: bool = False,
) -> tuple[dict, bool]:
    """Apply one section edit off the event loop.

    REST passes the full ``body``. The agent passes ``overrides`` (only the
    fields to change) and the merge with the stored section happens here, in
    the same call that writes, so a concurrent edit is never overwritten with
    stale values. With ``reject_duplicate_name`` (agent only) a new name equal
    to another section's name raises :class:`SectionNameTakenError`; REST keeps
    accepting duplicates. Returns the response body and whether the stored
    section changed; the analysis is invalidated only on a real change.
    """
    sections = db.get_sections(session_id)
    idx = _section_index(section_id, len(sections))
    current = sections[idx]
    if body is None:
        body = _merge_section_overrides(current, overrides or {})
    updated = _section_dict_from_body(body, current["name"])
    if (
        reject_duplicate_name
        and updated["name"] != current["name"]
        and any(
            other["name"] == updated["name"]
            for position, other in enumerate(sections)
            if position != idx
        )
    ):
        raise SectionNameTakenError(updated["name"])
    changed = updated != current
    if changed:
        sections[idx] = updated
        db.save_sections(session_id, sections)
        db.invalidate_analysis(session_id)
    return _section_to_response(idx, updated), changed


def _delete_section_sync(session_id: str, section_id: str) -> tuple[str, int]:
    """Remove one section off the event loop; returns (removed name, total left)."""
    sections = db.get_sections(session_id)
    idx = _section_index(section_id, len(sections))
    removed = sections.pop(idx)
    db.save_sections(session_id, sections)
    db.invalidate_analysis(session_id)
    return removed["name"], len(sections)


def _curve_sections(
    points: List[List[float]],
    spacing: float,
    length: float,
    sector: str,
    length_up: Optional[float],
    length_down: Optional[float],
) -> List[SectionLine]:
    """Build the perpendicular sections of a polyline without touching the DB.

    Shared by POST /sections/curve and the generate_sections_curve agent tool.
    """
    points_array = np.array(points, dtype=float)
    if len(points_array) < 2:
        raise HTTPException(400, "Curve must have at least 2 points")
    return generate_perpendicular_sections(
        points=points_array,
        spacing=spacing,
        section_length=length,
        sector_name=sector,
        length_up=length_up,
        length_down=length_down,
    )


# ---------------------------------------------------------------------------
# Pydantic models for request bodies
# ---------------------------------------------------------------------------


class SectionAutoParams(BaseModel):
    """Parameters for auto-generating sections along a crest line."""

    start: List[float]  # [x, y]
    end: List[float]  # [x, y]
    n_sections: int = 5
    length: float = 200.0
    length_up: Optional[float] = None
    length_down: Optional[float] = None
    sector: str = ""
    az_method: str = "perpendicular"  # "perpendicular" | "fixed" | "local_slope"
    fixed_az: float = 0.0



class SectionCurveParams(BaseModel):
    """Parameters for auto-generating sections along a polyline (curve)."""
    points: List[List[float]]  # List of [x, y]
    spacing: float = 10.0
    length: float = 200.0
    length_up: Optional[float] = None
    length_down: Optional[float] = None
    sector: str = ""

class SectionCreate(BaseModel):
    """Single section definition."""

    name: Optional[str] = None
    origin: List[float]  # [x, y]
    azimuth: float
    length: float = 200.0
    length_up: Optional[float] = None
    length_down: Optional[float] = None
    sector: str = ""


class SectionClickParams(BaseModel):
    """Parameters for adding a section by click on plan view."""

    origin: List[float]  # [x, y]
    length: float = 200.0
    length_up: Optional[float] = None
    length_down: Optional[float] = None
    sector: str = ""
    az_mode: str = "auto"  # "auto" | "manual"
    azimuth: Optional[float] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_sections(request: Request):
    """Return all sections for the current session."""
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    sections = await _load_sections(session_id)
    return [_section_to_response(i, s) for i, s in enumerate(sections)]


@router.post("/auto")
async def sections_auto(request: Request, params: SectionAutoParams):
    """
    Generate sections evenly spaced along a start→end line.

    Supports three azimuth methods:
    - **perpendicular**: sections perpendicular to the crest line (default).
    - **fixed**: all sections use ``fixed_az``.
    - **local_slope**: compute azimuth from design mesh slope at each section origin.
    """
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)
    design_mesh = await _get_design_mesh(session_id)

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
        design_mesh, start, end, n, az, length, sector,
        length_up=params.length_up, length_down=params.length_down
    )

    # Override azimuth with local slope if requested
    if params.az_method == "local_slope":
        for sec in sections:
            sec.azimuth = compute_local_azimuth(design_mesh, sec.origin)

    await _append_sections(session_id, sections)

    stored = await _load_sections(session_id)
    return {
        "sections": [_section_to_response(i, s) for i, s in enumerate(stored)],
    }


@router.post("/manual")
async def sections_manual(request: Request, sections_data: List[SectionCreate]):
    """Set sections from manual input (replaces any existing sections)."""
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)
    sections: List[SectionLine] = []
    for idx, s in enumerate(sections_data):
        sec = SectionLine(
            name=s.name or f"S-{idx + 1:02d}",
            origin=np.array(s.origin, dtype=float),
            azimuth=float(s.azimuth),
            length=float(s.length),
            length_up=s.length_up,
            length_down=s.length_down,
            sector=s.sector,
        )
        sections.append(sec)

    stored = await _replace_sections(session_id, sections)
    return {
        "message": f"{len(stored)} sections set",
        "sections": [_section_to_response(i, s) for i, s in enumerate(stored)],
    }


@router.post("/click")
async def add_section_click(request: Request, params: SectionClickParams):
    """
    Add a single section by clicking on the plan view.

    If ``az_mode`` is ``"auto"``, computes azimuth from the design mesh slope.
    Appends to existing sections.
    """
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)
    origin = np.array(params.origin, dtype=float)
    length = params.length
    sector = params.sector

    if params.az_mode == "auto":
        design_mesh = await _get_design_mesh(session_id)
        az = compute_local_azimuth(design_mesh, origin)
    else:
        az = params.azimuth if params.azimuth is not None else 0.0

    existing = await _load_sections(session_id)
    n = len(existing) + 1
    sec = SectionLine(
        name=f"S-{n:02d}",
        origin=origin,
        azimuth=az,
        length=length,
        length_up=params.length_up,
        length_down=params.length_down,
        sector=sector,
    )

    stored = await _append_sections(session_id, [sec])
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
    length_up: str = Form(""),
    length_down: str = Form(""),
    sector: str = Form("Principal"),
    az_mode: str = Form("perpendicular"),  # "perpendicular" | "local_slope"
):
    """
    Generate sections from a CSV (X, Y columns) or DXF polyline file.

    Parses the uploaded file as a polyline, then calls
    ``generate_perpendicular_sections()``.
    """
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)
    design_mesh = await _get_design_mesh(session_id)

    spacing_f = float(spacing)
    length_f = float(length)
    l_up_f = float(length_up) if length_up.strip() else None
    l_down_f = float(length_down) if length_down.strip() else None

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
        try:
            polyline = _read_polyline_xy_csv(content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    if len(polyline) < 2:
        raise HTTPException(400, "Polyline must have at least 2 points")

    mesh_for_az = design_mesh if az_mode == "local_slope" else None
    sections = generate_perpendicular_sections(
        polyline, spacing_f, length_f, sector, design_mesh=mesh_for_az,
        length_up=l_up_f, length_down=l_down_f
    )

    await _append_sections(session_id, sections)

    stored = await _load_sections(session_id)
    return {
        "sections": [_section_to_response(i, s) for i, s in enumerate(stored)],
        "polyline": polyline.tolist()
        if hasattr(polyline, "tolist")
        else list(polyline),
    }


@router.put("/{section_id}")
async def update_section(request: Request, section_id: str, body: SectionCreate):
    """
    Update a single section by its index-based ID.

    Replaces the section at the given index with new data.
    """
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)
    response, _changed = await run_db(_update_section_sync, session_id, section_id, body)
    return response


@router.delete("/{section_id}")
async def delete_section(request: Request, section_id: str):
    """Delete a single section by its index-based ID."""
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)
    name, total = await run_db(_delete_section_sync, session_id, section_id)
    return {
        "message": f"Section '{name}' deleted",
        "total": total,
    }


@router.delete("")
async def clear_sections(request: Request):
    """Clear all sections for the current session."""
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)
    sections = await _load_sections(session_id)
    if sections:
        await run_db(db.save_sections, session_id, [])
        await run_db(db.invalidate_analysis, session_id)
    return {"message": "All sections cleared"}


@router.post("/curve")
async def sections_curve(request: Request, params: SectionCurveParams):
    """
    Generate sections perpendicular to an arbitrary polyline (e.g. contour curve segment).
    """
    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    await _ensure_sections_mutable(session_id)

    sections = _curve_sections(
        params.points,
        params.spacing,
        params.length,
        params.sector,
        params.length_up,
        params.length_down,
    )

    stored = await _append_sections(session_id, sections)
    return {
        "sections": [_section_to_response(i, s) for i, s in enumerate(stored)],
    }

