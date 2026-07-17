"""
Mesh router — upload, info, vertices, delete.

All endpoints operate under the session identified by ``request.state.session_id``
(which is set by the session middleware in ``api/main.py``).

Performance: every handler is ``async def`` and off-loads DB round-trips
(``api.database`` is synchronous SQLite) to the default executor via
:func:`api._async_db.run_db`. The cached heavy helpers (``_get_decimated_*``,
``_get_contours_*``, ``_get_breaklines_*``) stay synchronous so tests can still
call ``.cache_clear()`` on them, but the handler awaits them through
``run_db`` so trimesh decimation / sectioning / breakline extraction never
blocks the event loop.
"""

import asyncio
import os
import tempfile
import functools
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

import api.database as db
from api._async_db import run_db
from core import load_mesh, get_mesh_bounds

router = APIRouter(prefix="/meshes", tags=["meshes"])


# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------


def get_session_id(request: Request) -> str:
    """Extract session_id set by the session middleware."""
    return request.state.session_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_mesh_from_blob(mesh_data: bytes, filename: str) -> trimesh.Trimesh:
    """Load a trimesh from database BLOB via a temporary file."""
    suffix = Path(filename).suffix or ".stl"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(mesh_data)
        return load_mesh(tmp)
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_mesh(
    request: Request,
    file: UploadFile = File(...),
    type: str = Form(...),  # "design" | "topo"
):
    """
    Upload a mesh file (STL / OBJ / PLY / DXF).

    Saves raw bytes to the database and returns summary info.
    """
    if type not in ("design", "topo"):
        raise HTTPException(400, "type must be 'design' or 'topo'")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    filename = file.filename or "mesh.stl"

    # Load mesh to validate and extract metadata
    suffix = Path(filename).suffix or ".stl"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        mesh = load_mesh(tmp)
    except Exception as exc:
        raise HTTPException(400, f"Error loading mesh: {exc}")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    raw_bounds = get_mesh_bounds(mesh)
    clean_bounds = {
        "xmin": raw_bounds["xmin"],
        "xmax": raw_bounds["xmax"],
        "ymin": raw_bounds["ymin"],
        "ymax": raw_bounds["ymax"],
        "zmin": raw_bounds["zmin"],
        "zmax": raw_bounds["zmax"],
    }

    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    mesh_id = await run_db(
        db.save_mesh,
        session_id=session_id,
        mesh_type=type,
        filename=filename,
        data=content,
        n_vertices=len(mesh.vertices),
        n_faces=len(mesh.faces),
        bounds=clean_bounds,
    )

    return {
        "mesh_id": mesh_id,
        "n_vertices": len(mesh.vertices),
        "n_faces": len(mesh.faces),
        "bounds": clean_bounds,
    }


@router.get("/{mesh_id}/info")
async def mesh_info(request: Request, mesh_id: str):
    """Return summary information for a stored mesh."""
    session_id = get_session_id(request)
    mesh = await run_db(db.get_mesh_by_id, mesh_id)
    if mesh is None:
        raise HTTPException(404, "Mesh not found")
    return {
        "id": mesh["id"],
        "type": mesh["type"],
        "filename": mesh["filename"],
        "n_vertices": mesh["n_vertices"],
        "n_faces": mesh["n_faces"],
        "bounds": mesh["bounds"],
        "uploaded_at": mesh["uploaded_at"],
    }


@functools.lru_cache(maxsize=16)
def _get_decimated_vertices_cached(mesh_id: str, step: int) -> dict:
    tmesh = db.get_trimesh_by_id(mesh_id)

    from core.mesh_handler import decimate_mesh
    if len(tmesh.faces) > 0:
        dec = decimate_mesh(tmesh, step)
        verts = dec.vertices
        faces = dec.faces
    else:
        verts = tmesh.vertices
        stride = max(1, len(verts) // step)
        verts = verts[::stride]
        faces = []

    return {
        "x": verts[:, 0].tolist(),
        "y": verts[:, 1].tolist(),
        "z": verts[:, 2].tolist(),
        "faces": faces.tolist() if len(faces) > 0 else [],
    }


@functools.lru_cache(maxsize=16)
def _get_contours_cached(mesh_id: str, interval: float, grid_size: int) -> dict:
    tmesh = db.get_trimesh_by_id(mesh_id)
    z_min, z_max = tmesh.bounds[0][2], tmesh.bounds[1][2]

    # Round to nearest interval
    levels = np.arange(
        np.floor(z_min / interval) * interval, z_max + interval, interval
    )

    contour_lines: list[dict] = []

    # We use exact trimesh sectioning instead of griddata interpolation!
    # This prevents staircases and produces geometrically perfect contours.
    for z in levels:
        slice_path = tmesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if slice_path is not None:
            segs = []
            # slice_path.discrete gives ordered polylines (requires networkx)
            for poly in slice_path.discrete:
                if len(poly) < 2:
                    continue
                poly_2d = [[float(v[0]), float(v[1])] for v in poly]
                segs.append(poly_2d)

            if segs:
                contour_lines.append({
                    "elevation": float(z),
                    "segments": segs
                })

    bounds = {
        "xmin": float(tmesh.bounds[0][0]),
        "xmax": float(tmesh.bounds[1][0]),
        "ymin": float(tmesh.bounds[0][1]),
        "ymax": float(tmesh.bounds[1][1]),
        "zmin": float(tmesh.bounds[0][2]),
        "zmax": float(tmesh.bounds[1][2]),
    }

    return {
        "bounds": bounds,
        "elevation_min": z_min,
        "elevation_max": z_max,
        "interval": interval,
        "lines": contour_lines,
    }


@router.get("/{mesh_id}/vertices")
async def mesh_vertices(request: Request, mesh_id: str, step: int = 8000):
    """
    Return decimated mesh vertices and faces for 3D visualization.

    ``step`` is the *maximum number of faces/points* to return (default 8000).
    """
    try:
        return await run_db(_get_decimated_vertices_cached, mesh_id, step)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/{mesh_id}")
async def delete_mesh(request: Request, mesh_id: str):
    """Delete a stored mesh."""
    deleted = await run_db(db.delete_mesh, mesh_id)
    if not deleted:
        raise HTTPException(404, "Mesh not found")
    return {"message": "Mesh deleted"}


@router.get("/{mesh_id}/contours")
async def mesh_contours(
    request: Request,
    mesh_id: str,
    interval: float = 15.0,
    grid_size: int = 1500,
):
    """
    Return contour/isoline data for a mesh.

    ``interval`` is the elevation step between contour lines (default 15 m).
    ``grid_size`` controls the interpolation resolution (default 400×400).

    Returns contour line segments grouped by elevation level, suitable for
    rendering with Chart.js or any line chart library.
    """
    try:
        return await run_db(_get_contours_cached, mesh_id, interval, grid_size)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@functools.lru_cache(maxsize=16)
def _get_breaklines_cached(mesh_id: str, angle_threshold: float) -> dict:
    from core.breaklines import extract_breaklines
    tmesh = db.get_trimesh_by_id(mesh_id)

    # Extract breaklines
    result = extract_breaklines(tmesh, angle_threshold_deg=angle_threshold)

    contour_lines = []
    if result["crests"]:
        contour_lines.append({
            "elevation": 1.0,
            "type": "crest",
            "segments": result["crests"]
        })
    if result["toes"]:
        contour_lines.append({
            "elevation": -1.0,
            "type": "toe",
            "segments": result["toes"]
        })

    bounds = {
        "xmin": float(tmesh.bounds[0][0]),
        "xmax": float(tmesh.bounds[1][0]),
        "ymin": float(tmesh.bounds[0][1]),
        "ymax": float(tmesh.bounds[1][1]),
        "zmin": float(tmesh.bounds[0][2]),
        "zmax": float(tmesh.bounds[1][2]),
    }

    return {
        "bounds": bounds,
        "elevation_min": bounds["zmin"],
        "elevation_max": bounds["zmax"],
        "interval": 0,
        "lines": contour_lines,
    }


@router.get("/{mesh_id}/breaklines")
async def mesh_breaklines(
    request: Request,
    mesh_id: str,
    angle_threshold: float = 20.0,
):
    """
    Return analytic structural breaklines (crests, toes) extracted from the mesh dihedral angles.
    """
    try:
        return await run_db(_get_breaklines_cached, mesh_id, angle_threshold)
    except ValueError as exc:
        raise HTTPException(404, str(exc))