"""Diagnostics — band classification and statistical summaries.

Classifies voxels into relative energy bands and computes aggregate
statistics consumed by the UI/export. The bands are RELATIVE to the
field's own maximum so they apply equally to ABSOLUTE (joules) and
RELATIVE (dimensionless) results.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from core.blast_simulation.contracts import SimulationResult, VoxelGridSpecification
from core.blast_simulation.grid import reshape_to_grid


DEFAULT_BAND_EDGES = (
    (0.0, 0.05),
    (0.05, 0.20),
    (0.20, 0.50),
    (0.50, 0.80),
    (0.80, 1.01),
)


def classify_energy_bands(
    *,
    energy_total_flat: np.ndarray,
    active_mask: np.ndarray | None = None,
    band_edges: tuple[tuple[float, float], ...] = DEFAULT_BAND_EDGES,
) -> list[dict[str, Any]]:
    """Group voxels into relative energy bands (fraction of field max).

    Returns a list of dicts with the band edges, voxel count, fraction
    of active voxels, and the integrated energy in the band.
    """
    arr = np.asarray(energy_total_flat, dtype=np.float64)
    if active_mask is None:
        active_mask = arr > 0.0
    if not active_mask.any() or arr.max() <= 0.0:
        return [
            {
                "band": list(edge),
                "voxel_count": 0,
                "fraction_active": 0.0,
                "integrated_energy": 0.0,
            }
            for edge in band_edges
        ]
    max_e = float(arr[active_mask].max())
    norm = arr[active_mask] / max_e
    integrated = arr[active_mask]
    bands = []
    n_active = int(active_mask.sum())
    for lo, hi in band_edges:
        mask = (norm >= lo) & (norm < hi)
        cnt = int(mask.sum())
        bands.append({
            "band": [lo, hi],
            "voxel_count": cnt,
            "fraction_active": cnt / n_active if n_active else 0.0,
            "integrated_energy": float(integrated[mask].sum()),
        })
    return bands


def statistical_summary(
    *,
    energy_total_flat: np.ndarray,
    active_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """Mean / std / percentiles over the active voxels."""
    arr = np.asarray(energy_total_flat, dtype=np.float64)
    if active_mask is None:
        active_mask = arr > 0.0
    if not active_mask.any():
        return {
            "active_voxels": 0,
            "mean": 0.0,
            "std": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    active = arr[active_mask]
    return {
        "active_voxels": int(active.size),
        "mean": float(active.mean()),
        "std": float(active.std()),
        "p50": float(np.percentile(active, 50)),
        "p90": float(np.percentile(active, 90)),
        "p99": float(np.percentile(active, 99)),
        "max": float(active.max()),
    }


def coverage_report(
    *,
    energy_total_flat: np.ndarray,
    grid: VoxelGridSpecification,
) -> dict[str, Any]:
    """Coverage diagnostics — what fraction of the domain received energy."""
    arr = np.asarray(energy_total_flat, dtype=np.float64)
    active = arr > 0.0
    return {
        "voxel_count": int(arr.size),
        "active_voxels": int(active.sum()),
        "inactive_voxels": int((~active).sum()),
        "active_fraction": float(active.mean()) if arr.size else 0.0,
        "voxel_volume_m3": grid.voxel_volume_m3,
        "active_volume_m3": float(active.sum() * grid.voxel_volume_m3),
    }
