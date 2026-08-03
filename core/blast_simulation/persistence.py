"""Persistence layer — NPZ artifact + JSON metadata with SHA-256.

The raw 3D energy field is persisted as a compressed NPZ binary artifact
(spec §8); only metadata + summary live in SQLite. Every artifact is
verifiable on read-back via its SHA-256 hash.

Layout on disk::

    {DATA_DIR}/blast_sims/
        {simulation_id}/
            energy_field.npz         ← compressed arrays + metadata
            simulation_summary.json  ← canonical SimulationResult.to_dict()

The NPZ stores the volumetric arrays (energy_total, energy_density,
contributing_count, dominant_idx, dominant_energy, voxel_centres, and
optionally first_arrival_s / time_of_max_s when temporal_mode=TEMPORAL)
alongside a JSON-serialised metadata block.

Conservation / hash invariants verified on read-back by tests:

* ``read_npz_artifact(..., expected_sha256=...)`` raises if the file
  was tampered with or the hash does not match.
* The voxel count, shape, dtype, axes order and energy unit declared
  in the metadata must match the array shapes actually stored.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from core.blast_simulation.contracts import SimulationResult
from core.blast_simulation.engine import export_field_arrays


class PersistenceError(RuntimeError):
    """Raised when an artifact cannot be written, read or verified."""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _default_data_dir() -> Path:
    return Path(
        os.environ.get(
            "CONCILIACION_DATA_DIR",
            Path(__file__).resolve().parent.parent.parent / "data",
        )
    )


def simulation_dir(simulation_id: str, *, data_dir: Path | str | None = None) -> Path:
    base = Path(data_dir) if data_dir else _default_data_dir()
    return base / "blast_sims" / simulation_id


def npz_path_for(simulation_id: str, *, data_dir: Path | str | None = None) -> Path:
    return simulation_dir(simulation_id, data_dir=data_dir) / "energy_field.npz"


def summary_path_for(simulation_id: str, *, data_dir: Path | str | None = None) -> Path:
    return simulation_dir(simulation_id, data_dir=data_dir) / "simulation_summary.json"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """SHA-256 hex of a file's bytes (deterministic, tamper-evident)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# NPZ write / read
# ---------------------------------------------------------------------------


def write_npz_artifact(
    *,
    result: SimulationResult,
    accepted_rows: list[dict[str, Any]],
    configuration,
    data_dir: Path | str | None = None,
    segments_per_hole: int = 8,
) -> tuple[SimulationResult, Path, str]:
    """Materialise the field arrays into a compressed NPZ artifact.

    Returns ``(updated_result, npz_path, sha256)``. The returned result
    is a new :class:`SimulationResult` with ``energy_field.npz_path``
    and ``grid_metadata.npz_sha256`` filled in.
    """
    arrays = export_field_arrays(
        result=result,
        accepted_rows=accepted_rows,
        configuration=configuration,
        segments_per_hole=segments_per_hole,
    )

    sim_dir = simulation_dir(result.simulation_id, data_dir=data_dir)
    sim_dir.mkdir(parents=True, exist_ok=True)
    out_path = sim_dir / "energy_field.npz"

    metadata = {
        "simulation_id": result.simulation_id,
        "engine_version": result.engine_version,
        "grid_shape": list(result.grid_metadata.shape),
        "voxel_size_m": result.grid_metadata.voxel_size_m,
        "bounds": result.grid_metadata.bounds.to_dict(),
        "axes_order": result.grid_metadata.axes_order,
        "energy_unit": result.grid_metadata.energy_unit,
        "dtype": result.grid_metadata.dtype,
        "voxel_count": result.grid_metadata.voxel_count,
        "voxel_volume_m3": result.grid_metadata.voxel_volume_m3,
        "created_at": result.grid_metadata.created_at,
        "represented_energy_j": result.energy_field.represented_energy_j,
        "outside_domain_energy_j": result.energy_field.outside_domain_energy_j,
        "total_coupled_energy_j": result.energy_field.total_coupled_energy_j,
        "fraction_represented": result.energy_field.fraction_represented,
        "energy_mode": result.processing_summary.energy_mode,
        "temporal_status": result.processing_summary.temporal_status,
    }

    # np.savez_compressed writes the arrays + a JSON metadata blob.
    payload: dict[str, Any] = dict(arrays)
    payload["metadata_json"] = np.array(json.dumps(metadata, sort_keys=True))
    np.savez_compressed(out_path, **payload)

    digest = sha256_file(out_path)

    # Return a new SimulationResult with the artifact references filled in.
    new_grid = replace(
        result.grid_metadata,
        npz_sha256=digest,
    )
    new_energy_field = replace(
        result.energy_field,
        grid=new_grid,
        npz_path=str(out_path),
    )
    updated = replace(
        result,
        grid_metadata=new_grid,
        energy_field=new_energy_field,
    )
    return updated, out_path, digest


def read_npz_artifact(
    npz_path: Path | str,
    *,
    expected_sha256: str | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any], str]:
    """Read and verify a simulation NPZ artifact.

    Parameters
    ----------
    npz_path
        Path written by :func:`write_npz_artifact`.
    expected_sha256
        If provided, the file's actual SHA-256 must match exactly —
        otherwise :class:`PersistenceError` is raised.

    Returns
    -------
    (arrays, metadata, sha256)
    """
    p = Path(npz_path)
    if not p.exists():
        raise PersistenceError(f"NPZ artifact not found: {p}")
    digest = sha256_file(p)
    if expected_sha256 is not None and digest != expected_sha256:
        raise PersistenceError(
            f"NPZ SHA-256 mismatch: expected {expected_sha256}, got {digest}"
        )
    with np.load(p, allow_pickle=False) as data:
        arrays = {k: data[k] for k in data.files if k != "metadata_json"}
        metadata_raw = data["metadata_json"]
    metadata = json.loads(str(metadata_raw.item()))

    # Cross-check declared vs actual shapes.
    expected_count = int(metadata["voxel_count"])
    if "energy_total" in arrays and arrays["energy_total"].size != expected_count:
        raise PersistenceError(
            f"voxel count mismatch: metadata declares {expected_count}, "
            f"array has {arrays['energy_total'].size}"
        )
    return arrays, metadata, digest


# ---------------------------------------------------------------------------
# JSON summary write / read
# ---------------------------------------------------------------------------


def write_summary_json(
    *,
    result: SimulationResult,
    data_dir: Path | str | None = None,
) -> Path:
    """Write the canonical result as a JSON summary file."""
    out = summary_path_for(result.simulation_id, data_dir=data_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    out.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    return out


def read_summary_json(path: Path | str) -> dict[str, Any]:
    """Read a simulation summary JSON and return the parsed dict."""
    p = Path(path)
    if not p.exists():
        raise PersistenceError(f"Summary JSON not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))
