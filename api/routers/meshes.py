"""
Mesh router — upload, info, vertices, delete.

All endpoints operate under the session identified by ``request.state.session_id``
(which is set by the session middleware in ``api/main.py``).
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

import api.database as db
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
        "xmin": raw_bounds["xmin"], "xmax": raw_bounds["xmax"],
        "ymin": raw_bounds["ymin"], "ymax": raw_bounds["ymax"],
        "zmin": raw_bounds["zmin"], "zmax": raw_bounds["zmax"],
    }

    session_id = get_session_id(request)
    mesh_id = db.save_mesh(
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
def mesh_info(request: Request, mesh_id: str):
    """Return summary information for a stored mesh."""
    session_id = get_session_id(request)
    mesh = db.get_mesh_by_id(mesh_id)
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


@router.get("/{mesh_id}/vertices")
def mesh_vertices(request: Request, mesh_id: str, step: int = 8000):
    """
    Return subsampled vertices for plan-view scatter plot.

    ``step`` is the *maximum number of points* to return (default 8000).
    """
    mesh = db.get_mesh_by_id(mesh_id)
    if mesh is None:
        raise HTTPException(404, "Mesh not found")

    tmesh = _load_mesh_from_blob(mesh["data"], mesh["filename"])
    verts = tmesh.vertices

    stride = max(1, len(verts) // step)
    sub = verts[::stride]

    return {
        "x": sub[:, 0].tolist(),
        "y": sub[:, 1].tolist(),
        "z": sub[:, 2].tolist(),
    }


@router.delete("/{mesh_id}")
def delete_mesh(request: Request, mesh_id: str):
    """Delete a stored mesh."""
    deleted = db.delete_mesh(mesh_id)
    if not deleted:
        raise HTTPException(404, "Mesh not found")
    return {"message": "Mesh deleted"}
