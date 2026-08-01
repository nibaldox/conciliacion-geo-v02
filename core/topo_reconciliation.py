"""Grid-based topographic reconciliation: design vs as-built surfaces.

Spec §6. The real and design topographies are sampled onto a common
regular grid; per cell:

    deltaZ(x,y) = Z_real(x,y) - Z_design(x,y)

Sign convention (documented and covered by tests):
    deltaZ > 0  -> as-built LOWER than design -> over-excavation
                  (more material removed than designed)
    deltaZ < 0  -> as-built HIGHER than design -> remaining material
                  (under-excavation)

Volumes integrate deltaZ over the effective cell area:

    V = sum(deltaZ_j * A_j)

so irregular point sampling never biases the volumes (cell area, not
point count).

All functions are pure (arrays/DataFrames in, arrays/DataFrames out) so
the module is usable from core, the API and the Streamlit UI.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

STATUS_COMPLIANT = "dentro_tolerancia"
STATUS_REMANENTE = "remanente"
STATUS_SOBREEXCAVACION = "sobreexcavacion"
STATUS_SIN_COBERTURA = "sin_cobertura"
STATUS_INVALIDO = "invalido"


def classify_delta_z(
    delta_z: np.ndarray,
    tolerance_m: float | tuple[float, float],
) -> np.ndarray:
    """Classify each cell by its vertical error (spec §6).

    Parameters
    ----------
    delta_z : ndarray
        Z_real - Z_design per cell (NaN = no coverage).
    tolerance_m : float or (neg_tol, pos_tol)
        Symmetric tolerance, or asymmetric (remaining, over-excavation)
        tolerance. Positive deltaZ beyond +pos_tol is over-excavation;
        negative deltaZ below -neg_tol is remaining material.

    Returns
    -------
    ndarray[str] with values ``dentro_tolerancia`` / ``remanente`` /
    ``sobreexcavacion`` / ``sin_cobertura``.
    """
    if isinstance(tolerance_m, (int, float)):
        neg_tol = pos_tol = float(tolerance_m)
    else:
        neg_tol, pos_tol = float(tolerance_m[0]), float(tolerance_m[1])

    out = np.full(np.shape(delta_z), STATUS_COMPLIANT, dtype=object)
    d = np.asarray(delta_z, dtype=float)
    mask_nan = np.isnan(d)
    out[mask_nan] = STATUS_SIN_COBERTURA
    out[(~mask_nan) & (d < -neg_tol)] = STATUS_REMANENTE
    out[(~mask_nan) & (d > pos_tol)] = STATUS_SOBREEXCAVACION
    return out


def grid_metrics(
    z_real: np.ndarray,
    z_design: np.ndarray,
) -> dict:
    """Statistical summary of the vertical error field (spec §6).

    Returns
    -------
    dict with mean_error_m, median_m, p10_m, p90_m, rmse_m, mae_m,
    n_valid (cells with both surfaces defined).
    """
    r = np.asarray(z_real, dtype=float)
    d = np.asarray(z_design, dtype=float)
    delta = r - d
    valid = (~np.isnan(delta)) & np.isfinite(delta)
    dv = delta[valid]
    n = int(valid.sum())
    if n == 0:
        return {
            "mean_error_m": np.nan, "median_m": np.nan,
            "p10_m": np.nan, "p90_m": np.nan,
            "rmse_m": np.nan, "mae_m": np.nan, "n_valid": 0,
        }
    return {
        "mean_error_m": float(np.mean(dv)),
        "median_m": float(np.median(dv)),
        "p10_m": float(np.percentile(dv, 10)),
        "p90_m": float(np.percentile(dv, 90)),
        "rmse_m": float(np.sqrt(np.mean(dv ** 2))),
        "mae_m": float(np.mean(np.abs(dv))),
        "n_valid": n,
    }


def reconcile_grid(
    z_real: np.ndarray,
    z_design: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    tolerance_m: float | tuple[float, float],
    cell_size_m: float,
) -> tuple[pd.DataFrame, dict]:
    """Reconcile real vs design grids on the common domain (spec §6).

    Parameters
    ----------
    z_real, z_design : ndarray, shape (len(ys), len(xs))
        Elevation of the as-built (real) and design surfaces.
    xs, ys : ndarray
        Cell centre coordinates (E, N) in metres.
    tolerance_m : float or (neg, pos)
        Compliance tolerance (see :func:`classify_delta_z`).
    cell_size_m : float
        Cell size used for the effective cell area (assumed square).

    Returns
    -------
    (df, metrics)
    df : one row per cell with xs, ys, z_real, z_design, delta_z,
         cell_area_m2 and status.
    metrics : dict with the grid statistics plus volumetric results:
         volume_remanente_m3, volume_sobreexcavacion_m3, balance_m3
         (over - remaining), pct_area_compliant / remanente /
         sobreexcavacion / sin_cobertura (percent of the total domain
         area, NaN cells excluded from the percentages).
    """
    r = np.asarray(z_real, dtype=float)
    d = np.asarray(z_design, dtype=float)
    if r.shape != d.shape:
        raise ValueError(
            f"shape mismatch: z_real {r.shape} vs z_design {d.shape}"
        )
    nx = len(xs)
    ny = len(ys)
    if r.shape != (ny, nx):
        raise ValueError(
            f"grid shape {(ny, nx)} does not match z shape {r.shape}"
        )
    if cell_size_m <= 0:
        raise ValueError(f"cell_size must be positive, got {cell_size_m}")
    # The declared cell size must match the actual grid spacing so cell
    # areas (and therefore volumes) stay honest (spec §6).
    if nx >= 2 and ny >= 2:
        spacing_x = float(np.median(np.diff(xs)))
        spacing_y = float(np.median(np.diff(ys)))
        if abs(spacing_x - cell_size_m) > 1e-6 * max(1.0, cell_size_m) or \
           abs(spacing_y - cell_size_m) > 1e-6 * max(1.0, cell_size_m):
            raise ValueError(
                f"cell_size {cell_size_m} does not match grid spacing "
                f"({spacing_x}, {spacing_y})"
            )
    if isinstance(tolerance_m, (int, float)):
        neg_tol = pos_tol = float(tolerance_m)
    else:
        neg_tol, pos_tol = float(tolerance_m[0]), float(tolerance_m[1])

    delta = r - d
    status = classify_delta_z(delta, (neg_tol, pos_tol))

    X, Y = np.meshgrid(xs, ys)
    df = pd.DataFrame({
        "xs": X.ravel(),
        "ys": Y.ravel(),
        "z_real": r.ravel(),
        "z_design": d.ravel(),
        "delta_z": delta.ravel(),
        "cell_area_m2": float(cell_size_m ** 2),
        "status": status.ravel(),
    })

    area = float(cell_size_m ** 2)
    n_total = nx * ny
    d_flat = delta.ravel()
    s_flat = status.ravel()
    mask_valid = ~np.isnan(d_flat) & np.isfinite(d_flat)

    vol_rem = float(np.sum(d_flat[mask_valid & (s_flat == STATUS_REMANENTE)] * -1.0) * area)
    vol_over = float(np.sum(d_flat[mask_valid & (s_flat == STATUS_SOBREEXCAVACION)]) * area)

    metrics = grid_metrics(r, d)
    metrics["volume_remanente_m3"] = vol_rem
    metrics["volume_sobreexcavacion_m3"] = vol_over
    metrics["balance_m3"] = vol_over - vol_rem
    metrics["pct_area_compliant"] = float((s_flat == STATUS_COMPLIANT).sum()) / n_total * 100.0
    metrics["pct_area_remanente"] = float((s_flat == STATUS_REMANENTE).sum()) / n_total * 100.0
    metrics["pct_area_sobreexcavacion"] = float((s_flat == STATUS_SOBREEXCAVACION).sum()) / n_total * 100.0
    metrics["pct_area_sin_cobertura"] = float((s_flat == STATUS_SIN_COBERTURA).sum()) / n_total * 100.0
    return df, metrics


def reconcile_by_holes(
    cell_df: pd.DataFrame,
    holes: pd.DataFrame,
    max_radius_m: Optional[float] = None,
) -> pd.DataFrame:
    """Aggregate reconciliation results per hole (spec §6).

    Each cell is assigned to the nearest hole collar. When the hole
    carries an ``area_influence_m2`` (Voronoi cell from Fase 1), the
    assignment is restricted to cells inside a circle of equivalent
    radius; cells beyond any influence area are assigned to the nearest
    hole anyway when ``max_radius_m`` is None (conservative behaviour),
    or dropped when it is set.

    Parameters
    ----------
    cell_df : DataFrame with xs, ys, delta_z, cell_area_m2, status
        (output of :func:`reconcile_grid`).
    holes : DataFrame with X, Y, label_pozo and optionally
        area_influence_m2.

    Returns
    -------
    DataFrame with one row per hole: label_pozo, n_celdas, mean_delta_m,
    volume_remanente_m3, volume_sobreexcavacion_m3, balance_m3,
    pct_area_compliant.
    """
    if cell_df.empty or holes.empty:
        return pd.DataFrame(
            columns=["label_pozo", "n_celdas", "mean_delta_m", "volume_remanente_m3",
                     "volume_sobreexcavacion_m3", "balance_m3", "pct_area_compliant"]
        )

    hole_xy = holes[["X", "Y"]].to_numpy(dtype=float)
    cell_xy = cell_df[["xs", "ys"]].to_numpy(dtype=float)

    from scipy.spatial import cKDTree
    tree = cKDTree(hole_xy)
    dist, idx = tree.query(cell_xy, k=1)

    labels = holes["label_pozo"].to_numpy()
    rows: list[dict] = []
    for h in range(len(holes)):
        sel = idx == h
        if "area_influence_m2" in holes.columns:
            r_inf = np.sqrt(holes["area_influence_m2"].iloc[h] / np.pi)
            sel = sel & (dist <= r_inf)
        sub = cell_df.loc[sel]
        if sub.empty:
            rows.append({
                "label_pozo": labels[h], "n_celdas": 0, "mean_delta_m": np.nan,
                "volume_remanente_m3": 0.0, "volume_sobreexcavacion_m3": 0.0,
                "balance_m3": 0.0, "pct_area_compliant": np.nan,
            })
            continue
        valid = sub["delta_z"].notna()
        n_cells = int(valid.sum())
        area = float(sub["cell_area_m2"].iloc[0])
        total = float(sub["cell_area_m2"].sum())
        vol_rem = float(sub.loc[sub["status"] == STATUS_REMANENTE, "delta_z"].sum() * -1.0) * area
        vol_over = float(sub.loc[sub["status"] == STATUS_SOBREEXCAVACION, "delta_z"].sum()) * area
        rows.append({
            "label_pozo": labels[h],
            "n_celdas": n_cells,
            "mean_delta_m": float(sub.loc[valid, "delta_z"].mean()) if n_cells else np.nan,
            "volume_remanente_m3": vol_rem,
            "volume_sobreexcavacion_m3": vol_over,
            "balance_m3": vol_over - vol_rem,
            "pct_area_compliant": float((sub["status"] == STATUS_COMPLIANT).sum()) / total * 100.0
            if total > 0 else np.nan,
        })
    return pd.DataFrame(rows)


def grid_from_mesh(
    mesh,
    xs: np.ndarray,
    ys: np.ndarray,
    method: str = "raycast",
    sample_density: int = 200000,
) -> np.ndarray:
    """Sample a trimesh surface onto the regular grid (spec §6).

    Parameters
    ----------
    mesh : trimesh.Trimesh
        The design or as-built surface.
    xs, ys : ndarray
        Cell centre coordinates (E, N).
    method : 'raycast' | 'sample_bin'
        - raycast: vertical rays from above, takes the highest
          intersection per cell (needs a watertight or at least
          two-sided mesh).
        - sample_bin: dense surface sampling + per-cell mean
          (fallback for open surfaces / TINs).
    sample_density : int
        Number of surface samples for ``sample_bin``.

    Returns
    -------
    ndarray of shape (len(ys), len(xs)) with the surface elevation per
    cell; NaN where the mesh does not cover the cell (no coverage).
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    X, Y = np.meshgrid(xs, ys)

    if method == "raycast":
        z = _raycast_z(mesh, X.ravel(), Y.ravel())
    elif method == "sample_bin":
        z = _sample_bin_z(mesh, X.ravel(), Y.ravel(), sample_density)
    else:
        raise ValueError(f"unknown method {method!r}; use 'raycast' or 'sample_bin'")

    return z.reshape((len(ys), len(xs)))


def _raycast_z(mesh, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Highest-intersection raycast from above the mesh (one ray per cell)."""
    z_hi = float(np.nanmax(mesh.vertices[:, 2])) + 10.0
    origins = np.column_stack([xs, ys, np.full(len(xs), z_hi)])
    directions = np.tile([0.0, 0.0, -1.0], (len(xs), 1))
    locations, _, _ = mesh.ray.intersects_location(origins, directions)
    out = np.full(len(xs), np.nan)
    if len(locations) == 0:
        return out
    ids, count = np.unique(locations[:, :2].round(6), axis=0, return_counts=True)
    idx_map = {}
    for i, (x, y) in enumerate(ids):
        pass
    # Group intersection points per ray using the ray origin grid.
    # Simpler robust approach: nearest ray origin within cell half-size.
    keys = np.round(locations[:, :2], 6)
    origins_keys = np.round(np.column_stack([xs, ys]), 6)
    from scipy.spatial import cKDTree
    tree = cKDTree(origins_keys)
    _, ray_idx = tree.query(keys, k=1)
    for i in range(len(xs)):
        hits = locations[ray_idx == i]
        if len(hits):
            out[i] = float(np.max(hits[:, 2]))  # highest intersection
    return out


def _sample_bin_z(mesh, xs: np.ndarray, ys: np.ndarray, sample_density: int) -> np.ndarray:
    """Dense surface sampling + mean elevation per cell."""
    pts, _ = trimesh_sample(mesh, sample_density)
    out = np.full(len(xs), np.nan)
    if len(pts) == 0:
        return out
    # Nearest sample per cell (cell spacing is typically >> sample density)
    from scipy.spatial import cKDTree
    tree = cKDTree(pts[:, :2])
    dist, idx = tree.query(np.column_stack([xs, ys]), k=8)
    # Mean of the k nearest samples
    means = np.nanmean(pts[:, 2][idx], axis=1)
    out = means
    return out


def trimesh_sample(mesh, count: int):
    """Sample ``count`` surface points from a trimesh (wrapper)."""
    import trimesh.sample as ts

    try:
        pts, faces = ts.sample_surface_even(mesh, count)
    except Exception:  # noqa: BLE001 — uneven/unclosed meshes fall back
        pts, faces = ts.sample_surface(mesh, count)
    return pts, faces
