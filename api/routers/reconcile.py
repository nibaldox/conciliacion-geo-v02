"""Topographic reconciliation router — design vs as-built (spec §6).

POST /api/v1/reconcile takes two stored meshes (design + as-built
topography), samples them onto a common grid and returns per-cell
classification, volumetric results and zonal statistics. Surface
validity (common extent, coverage, elevation plausibility) is checked
before any metric is computed.
"""
import asyncio

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import api.database as db
from api._async_db import run_db
from core.topo_reconciliation import (
    grid_from_mesh,
    reconcile_grid,
)

router = APIRouter(prefix="/reconcile", tags=["reconcile"])


class ReconcileRequest(BaseModel):
    design_mesh_id: str = Field(..., description="Stored design surface mesh")
    topo_mesh_id: str = Field(..., description="Stored as-built topography mesh")
    tolerance_m: float = Field(1.0, gt=0, description="Compliance tolerance (symmetric)")
    neg_tolerance_m: float | None = Field(None, gt=0, description="Remaining-material tolerance (asymmetric)")
    pos_tolerance_m: float | None = Field(None, gt=0, description="Over-excavation tolerance (asymmetric)")
    cell_size_m: float = Field(2.0, gt=0, description="Grid cell size (m)")
    method: str = Field("raycast", pattern="^(raycast|sample_bin)$")
    bounds: dict | None = Field(None, description="Optional {xmin,xmax,ymin,ymax} analysis window")
    max_cells: int = Field(250_000, gt=0, le=1_000_000, description="Grid cap")


def _mesh_to_grid(mesh, xs, ys, method: str) -> np.ndarray:
    import core.topo_reconciliation as tr
    return tr.grid_from_mesh(mesh, xs, ys, method=method)


@router.post("")
async def reconcile(request: Request, body: ReconcileRequest):
    """Reconcile design vs as-built topographies on a common grid."""
    neg_tol = body.neg_tolerance_m if body.neg_tolerance_m is not None else body.tolerance_m
    pos_tol = body.pos_tolerance_m if body.pos_tolerance_m is not None else body.tolerance_m

    try:
        design = await run_db(db.get_trimesh_by_id, body.design_mesh_id)
    except ValueError:
        raise HTTPException(404, "design mesh not found")
    if design is None:
        raise HTTPException(404, "design mesh not found")
    try:
        topo = await run_db(db.get_trimesh_by_id, body.topo_mesh_id)
    except ValueError:
        raise HTTPException(404, "topo mesh not found")
    if topo is None:
        raise HTTPException(404, "topo mesh not found")

    # Surface validity checks (spec §6): common extent before sampling.
    d_b = design.bounds
    t_b = topo.bounds
    xmin = max(float(d_b[0][0]), float(t_b[0][0]))
    ymin = max(float(d_b[0][1]), float(t_b[0][1]))
    xmax = min(float(d_b[1][0]), float(t_b[1][0]))
    ymax = min(float(d_b[1][1]), float(t_b[1][1]))
    if xmin >= xmax or ymin >= ymax:
        raise HTTPException(
            400,
            "Las superficies no comparten extensión común (no se solapan en X/Y): "
            f"design [{d_b[0][0]:.1f},{d_b[1][0]:.1f}]×[{d_b[0][1]:.1f},{d_b[1][1]:.1f}], "
            f"topo [{t_b[0][0]:.1f},{t_b[1][0]:.1f}]×[{t_b[0][1]:.1f},{t_b[1][1]:.1f}]",
        )

    if body.bounds is not None:
        b = body.bounds
        xmin = max(xmin, float(b.get("xmin", xmin)))
        xmax = min(xmax, float(b.get("xmax", xmax)))
        ymin = max(ymin, float(b.get("ymin", ymin)))
        ymax = min(ymax, float(b.get("ymax", ymax)))
        if xmin >= xmax or ymin >= ymax:
            raise HTTPException(400, "bounds inválidos (extensión vacía)")

    cs = body.cell_size_m
    xs = np.arange(xmin + cs / 2.0, xmax, cs)
    ys = np.arange(ymin + cs / 2.0, ymax, cs)
    if len(xs) * len(ys) > body.max_cells:
        raise HTTPException(
            400,
            f"Grilla {len(xs)}×{len(ys)} = {len(xs)*len(ys)} celdas supera "
            f"el máximo {body.max_cells}; aumente cell_size_m",
        )
    if len(xs) < 1 or len(ys) < 1:
        raise HTTPException(400, "extensión común demasiado pequeña para cell_size")

    # Heavy grid sampling off the event loop.
    z_design = await run_db(_mesh_to_grid, design, xs, ys, body.method)
    z_topo = await run_db(_mesh_to_grid, topo, xs, ys, body.method)

    df, metrics = reconcile_grid(
        z_topo, z_design, xs, ys,
        tolerance_m=(neg_tol, pos_tol), cell_size_m=cs,
    )

    counts = df["status"].value_counts().to_dict()
    coverage = float(df["z_real"].notna().mean() * 100.0)
    return {
        "n_cells": int(len(df)),
        "n_x": int(len(xs)),
        "n_y": int(len(ys)),
        "cell_size_m": cs,
        "tolerance_m": {"neg": neg_tol, "pos": pos_tol},
        "method": body.method,
        "coverage_pct_topo": coverage,
        "status_counts": {k: int(v) for k, v in counts.items()},
        "metrics": metrics,
        "surfaces": {
            "design": {"mesh_id": body.design_mesh_id, "n_vertices": int(len(design.vertices)), "n_faces": int(len(design.faces))},
            "topo": {"mesh_id": body.topo_mesh_id, "n_vertices": int(len(topo.vertices)), "n_faces": int(len(topo.faces))},
            "common_extent_m": {"xmin": float(xmin), "xmax": float(xmax), "ymin": float(ymin), "ymax": float(ymax)},
        },
        "convention": "deltaZ = Z_real - Z_design; positivo = sobreexcavación",
    }
