"""Persistence layer — atomic NPZ artifact + JSON metadata with SHA-256.

The raw 3D energy field is persisted as a compressed NPZ binary artifact
(spec §8); only metadata + summary live in SQLite. Every artifact is
verifiable on read-back via its SHA-256 hash.

Layout on disk::

    {DATA_DIR}/blast_sims/
        {simulation_id}/
            energy_field.npz         ← compressed arrays + metadata
            simulation_summary.json  ← canonical SimulationResult.to_dict()

The NPZ stores the volumetric arrays ``energy_total``,
``energy_density_j_m3``, ``contributing_count``, ``dominant_idx``,
``dominant_hole_id``, ``dominant_energy``, ``voxel_centres``,
``grid_shape``, ``axis_order``, ``dtype`` and ``units`` (JSON-encoded
string) alongside a JSON-serialised metadata block. In TEMPORAL mode
the arrays ``first_arrival_s`` and ``time_of_max_s`` are added. All
arrays are stored as native numpy dtypes — no pickle is ever used on
the read path.

Conservation / hash invariants verified on read-back by tests:

* ``read_npz_artifact(..., expected_sha256=...)`` raises if the file
  was tampered with or the hash does not match.
* ``voxel_count`` declared in the metadata matches the array sizes.
* ``dtype`` declared in the metadata matches the stored array dtype.
* ``axes_order`` is the canonical ``"xyz"``.
* ``first_arrival_s`` (when present) is float32.
* No pickle is used to load any array (``allow_pickle=False``).

Atomicity (Falla 7)
-------------------

``write_atomic_simulation`` writes the NPZ + JSON under a temporary
``{simulation_id}.tmp/`` directory, validates both files, and renames
the directory onto the final location. If anything fails **before** the
rename, the entire ``.tmp/`` directory is removed and the canonical
``{simulation_id}/`` directory is never created. After the rename there
is no rollback path — the artifact is committed.

Blocked simulations (Falla 7)
-----------------------------

A simulation with ``blocking_errors`` is rejected by the engine and
MUST NOT produce an artifact on disk. The API uses
``should_persist(result)`` to gate the call to
``write_atomic_simulation``.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

import numpy as np

from core.blast_simulation.charges import (
    build_charge_segments,
    classify_segments,
)
from core.blast_simulation.contracts import (
    AnisotropyMode,
    SimulationConfiguration,
    SimulationResult,
    TemporalMode,
    VoxelGridSpecification,
)
from core.blast_simulation.engine import (
    _accumulate_source,
    _source_coupled_energy,
    _stable_hole_index,
)
from core.blast_simulation.grid import (
    intersection_mask_flat,
    voxel_centres_flat,
)
from core.blast_simulation.kernels import (
    compute_distance,
    discrete_total_mass,
)
from core.blast_simulation.temporal import (
    compute_first_arrival,
    compute_time_of_max,
)
from core.config import SIMULATION


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


def _tmp_dir_for(simulation_id: str, *, data_dir: Path | str | None = None) -> Path:
    """Sibling directory used for atomic writes.

    Lives next to the final ``{simulation_id}/`` directory so the rename
    is always on the same filesystem.
    """
    base = Path(data_dir) if data_dir else _default_data_dir()
    return base / "blast_sims" / f"{simulation_id}.tmp"


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
# Persistability gate (Falla 7)
# ---------------------------------------------------------------------------


def should_persist(result: SimulationResult) -> bool:
    """Return ``False`` when the simulation was blocked.

    The engine rejected a configuration (e.g. ``ABSOLUTE`` mode with an
    unknown explosive, or unconfirmed / out-of-version configuration).
    Persisting the artifact would create a misleading cache of an
    un-runnable result. The API MUST call :func:`write_atomic_simulation`
    only when this function returns ``True``.
    """
    return len(result.blocking_errors) == 0


# ---------------------------------------------------------------------------
# Field-array computation (Falla 3)
# ---------------------------------------------------------------------------


def _build_metadata(result: SimulationResult) -> dict[str, Any]:
    """Build the canonical metadata dict embedded in the NPZ."""
    return {
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
        "units": {"energy": "J", "density": "J/m3", "time": "s"},
    }


def compute_field_arrays(
    *,
    result: SimulationResult,
    accepted_rows: list[dict[str, Any]],
    configuration: SimulationConfiguration,
    segments_per_hole: int = 8,
    support_radius_m: Optional[float] = None,
) -> dict[str, np.ndarray]:
    """Recompute the canonical field arrays for NPZ persistence.

    The engine result carries only aggregate metadata; the actual 3D
    arrays are reproduced deterministically from the same inputs so the
    NPZ artifact can be SHA-256 verified on read-back.

    Returns a dict suitable for ``np.savez_compressed``. All arrays are
    stored as native numpy dtypes — no pickle is required to read them
    back, and ``np.load(..., allow_pickle=False)`` succeeds.

    Canonical arrays (always present):

    * ``energy_total``         float32, shape ``(n_voxels,)``
    * ``energy_density_j_m3``  float32, shape ``(n_voxels,)``
    * ``contributing_count``   int32,   shape ``(n_voxels,)``
    * ``dominant_idx``         int64,   shape ``(n_voxels,)`` (stable hash of hole_id)
    * ``dominant_hole_id``     Unicode string, shape ``(n_voxels,)`` (real hole_id)
    * ``dominant_energy``      float32, shape ``(n_voxels,)``
    * ``voxel_centres``        float32, shape ``(n_voxels, 3)``
    * ``grid_shape``           int32,   shape ``(3,)``
    * ``axis_order``           Unicode string, shape ``(3,)``
    * ``dtype``                Unicode scalar (the canonical dtype name)
    * ``units``                Unicode scalar (JSON-encoded units dict)

    In TEMPORAL mode the following arrays are added (Falla 3):

    * ``first_arrival_s``      float32, shape ``(n_voxels,)`` (NaN where no contribution)
    * ``time_of_max_s``        float32, shape ``(n_voxels,)``

    In STATIC mode ``first_arrival_s`` and ``time_of_max_s`` are NOT
    present in the returned dict.
    """
    grid = VoxelGridSpecification(
        voxel_size_m=configuration.voxel_size_m,
        bounds=configuration.domain_bounds,
    )
    voxel_centres = voxel_centres_flat(grid)
    in_domain_mask = intersection_mask_flat(grid)

    segments = build_charge_segments(
        accepted_rows,
        config=configuration,
        segments_per_hole=segments_per_hole,
    )
    valid, _, _ = classify_segments(segments, energy_mode=configuration.energy_mode)

    R_runtime = (
        float(support_radius_m)
        if support_radius_m is not None
        else float(SIMULATION.default_support_radius_m)
    )

    anisotropy_tensor = (
        np.asarray(configuration.rock_mass.anisotropy_tensor, dtype=np.float64)
        if configuration.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR
        and configuration.rock_mass.anisotropy_tensor is not None
        else None
    )
    kernel_total = discrete_total_mass(
        attenuation_coefficient_1_m=configuration.attenuation_coefficient_1_m,
        regularization_radius_m=configuration.regularization_radius_m,
        support_radius_m=R_runtime,
        voxel_size_m=grid.voxel_size_m,
        anisotropy_mode=configuration.anisotropy_mode,
        tensor=anisotropy_tensor,
    )

    n_voxels = grid.voxel_count
    is_temporal = configuration.temporal_mode == TemporalMode.TEMPORAL

    energy_total = np.zeros(n_voxels, dtype=np.float64)
    contributing_count = np.zeros(n_voxels, dtype=np.int32)
    dominant_idx = np.zeros(n_voxels, dtype=np.int64)
    dominant_energy = np.zeros(n_voxels, dtype=np.float64)

    # Temporal accumulators — only populated when temporal_mode=TEMPORAL.
    # The engine records per-source contributions and computes the
    # aggregated first_arrival / time_of_max once per voxel after the
    # source loop, so we mirror that exact pattern here.
    pulse_sigma = None
    if is_temporal:
        pulse_sigma = (
            configuration.pulse_sigma_s
            if configuration.pulse_sigma_s is not None
            else SIMULATION.fallback_temporal_sigma_s
        )

    total_represented: list[float] = []
    total_outside: list[float] = []
    per_hole_energy: dict[str, float] = {}
    temporal_energy_contributions: Optional[list[np.ndarray]] = []
    temporal_distances: Optional[list[np.ndarray]] = []
    temporal_detonation_times: Optional[list[float]] = []
    if not is_temporal:
        temporal_energy_contributions = None
        temporal_distances = None
        temporal_detonation_times = None

    for seg in valid:
        e_acoplada = _source_coupled_energy(
            seg,
            coupling_efficiency=configuration.coupling_efficiency,
            energy_mode=configuration.energy_mode,
        )
        if e_acoplada is None or e_acoplada <= 0.0:
            continue
        _accumulate_source(
            seg=seg,
            e_acoplada=e_acoplada,
            voxel_centres=voxel_centres,
            in_domain_mask=in_domain_mask,
            grid=grid,
            config=configuration,
            support_radius_m=R_runtime,
            kernel_total=kernel_total,
            energy_total=energy_total,
            contributing_count=contributing_count,
            dominant_idx=dominant_idx,
            dominant_energy=dominant_energy,
            arrival_times=None,
            first_arrival=None,
            time_of_max=None,
            pulse_sigma=pulse_sigma,
            temporal_energy_contributions=temporal_energy_contributions,
            temporal_distances=temporal_distances,
            temporal_detonation_times=temporal_detonation_times,
            total_represented=total_represented,
            total_outside=total_outside,
            per_hole_energy=per_hole_energy,
        )

    # Build the dominant_hole_id array via a reverse map from the
    # stable hash (dominant_idx) to the original hole_id. We use
    # Unicode string dtype (``dtype="U"``) so the array CAN be loaded
    # with ``allow_pickle=False`` — an object dtype array would require
    # pickle on read and is explicitly forbidden by the persistence
    # contract.
    idx_to_hole: dict[int, str] = {}
    for seg in valid:
        idx = _stable_hole_index(seg.hole_id)
        idx_to_hole.setdefault(idx, seg.hole_id)

    if n_voxels > 0:
        dominant_hole_id = np.array(
            [idx_to_hole.get(int(idx), "") for idx in dominant_idx],
            dtype="U",
        )
    else:
        dominant_hole_id = np.array([], dtype="U")

    out: dict[str, np.ndarray] = {
        "energy_total": energy_total.astype(np.float32),
        "energy_density_j_m3": (energy_total / grid.voxel_volume_m3).astype(np.float32),
        "contributing_count": contributing_count,
        "dominant_idx": dominant_idx,
        "dominant_hole_id": dominant_hole_id,
        "dominant_energy": dominant_energy.astype(np.float32),
        "voxel_centres": voxel_centres.astype(np.float32),
        "grid_shape": np.array(
            [grid.shape[0], grid.shape[1], grid.shape[2]], dtype=np.int32
        ),
        "axis_order": np.array(["x", "y", "z"], dtype="U"),
        "dtype": np.array("float32", dtype="U"),
        "units": np.array(
            json.dumps({"energy": "J", "density": "J/m3", "time": "s"}),
            dtype="U",
        ),
    }

    # Falla 3 — compute the actual temporal arrays from the per-source
    # contributions. NaN here means no source reached the voxel — the
    # values are no longer placeholders.
    if (
        is_temporal
        and temporal_energy_contributions
        and temporal_distances
        and temporal_detonation_times is not None
        and configuration.propagation_velocity_m_s is not None
    ):
        n_segments = len(temporal_energy_contributions)
        if n_segments > 0:
            distances_matrix = np.column_stack(temporal_distances)
            energy_matrix = np.column_stack(temporal_energy_contributions)
            segment_mask = energy_matrix > 0.0
            first_arrival_array, _ = compute_first_arrival(
                distances_per_voxel=distances_matrix,
                propagation_velocity_m_s=float(configuration.propagation_velocity_m_s),
                detonation_times_per_segment=temporal_detonation_times,
                segment_mask=segment_mask,
            )
            first_arrival_array[~np.isfinite(first_arrival_array)] = np.nan
            time_of_max_array = compute_time_of_max(
                energy_total_per_voxel=energy_total,
                first_arrival_per_voxel=first_arrival_array,
                distances_per_voxel=distances_matrix,
                propagation_velocity_m_s=float(configuration.propagation_velocity_m_s),
                sigma_s=float(pulse_sigma),
                energy_per_segment_per_voxel=energy_matrix,
                detonation_times_per_segment=temporal_detonation_times,
                segment_mask=segment_mask,
            )
            out["first_arrival_s"] = first_arrival_array.astype(np.float32)
            out["time_of_max_s"] = time_of_max_array.astype(np.float32)

    return out


# ---------------------------------------------------------------------------
# Atomic write (Falla 7)
# ---------------------------------------------------------------------------


def write_atomic_simulation(
    *,
    result: SimulationResult,
    accepted_rows: list[dict[str, Any]],
    configuration: SimulationConfiguration,
    data_dir: Path | str | None = None,
    segments_per_hole: int = 8,
    support_radius_m: Optional[float] = None,
) -> tuple[SimulationResult, Path, str, Path]:
    """Write the NPZ artifact + JSON summary atomically.

    Algorithm:

    1. Compute the field arrays via :func:`compute_field_arrays`.
    2. Create a temporary ``{simulation_id}.tmp/`` directory (sibling
       of the final ``{simulation_id}/``).
    3. Write the NPZ to ``{tmp_dir}/energy_field.npz.tmp``.
    4. Compute the SHA-256 of the NPZ.
    5. Write the JSON summary to ``{tmp_dir}/simulation_summary.json.tmp``.
    6. Validate the NPZ (re-read with ``allow_pickle=False``; verify
       file exists, energy_total dtype, voxel_count, declared dtype,
       axes_order, SHA-256 and ``first_arrival_s`` dtype when present).
    7. Validate the JSON (re-read and verify ``simulation_id``).
    8. If everything checks out, rename the temporary files inside the
       ``.tmp/`` directory to their final names, then rename the
       ``.tmp/`` directory onto the final ``{simulation_id}/`` location.
    9. If any step fails, the entire ``.tmp/`` directory is removed and
       the canonical ``{simulation_id}/`` directory is never created.

    Returns ``(updated_result, npz_path, sha256, summary_path)``.

    Raises
    ------
    PersistenceError
        If any validation check fails. The ``.tmp/`` directory is
        cleaned up before the exception propagates.
    """
    arrays = compute_field_arrays(
        result=result,
        accepted_rows=accepted_rows,
        configuration=configuration,
        segments_per_hole=segments_per_hole,
        support_radius_m=support_radius_m,
    )

    sim_dir = simulation_dir(result.simulation_id, data_dir=data_dir)
    tmp_dir = _tmp_dir_for(result.simulation_id, data_dir=data_dir)
    final_npz = sim_dir / "energy_field.npz"
    final_summary = sim_dir / "simulation_summary.json"
    tmp_npz = tmp_dir / "energy_field.npz.tmp"
    tmp_summary = tmp_dir / "simulation_summary.json.tmp"

    # Clean up any stale .tmp directory from a previous failed attempt.
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Build the metadata and attach to the payload.
        metadata = _build_metadata(result)
        payload: dict[str, Any] = dict(arrays)
        # Native Unicode scalar — loads without pickle.
        payload["metadata_json"] = np.array(
            json.dumps(metadata, sort_keys=True, ensure_ascii=False),
            dtype="U",
        )

        # 2. Write the NPZ (still .tmp). NumPy's savez_compressed
        # appends ".npz" if the path doesn't end in it, so we save to
        # a path that already has the canonical extension and rename
        # atomically below.
        np.savez_compressed(tmp_dir / "energy_field.npz", **payload)
        npz_just_written = tmp_dir / "energy_field.npz"
        npz_just_written.replace(tmp_npz)

        # 3. Compute SHA-256.
        digest = sha256_file(tmp_npz)

        # 4. Validate the NPZ (re-read with allow_pickle=False).
        with np.load(tmp_npz, allow_pickle=False) as data:
            files = set(data.files)
            if "energy_total" not in files:
                raise PersistenceError(
                    "NPZ artifact missing 'energy_total' array"
                )
            energy_arr = data["energy_total"]
            expected_count = int(result.grid_metadata.voxel_count)
            if energy_arr.size != expected_count:
                raise PersistenceError(
                    f"NPZ voxel count mismatch: file has {energy_arr.size}, "
                    f"metadata declares {expected_count}"
                )
            if energy_arr.dtype != np.float32:
                raise PersistenceError(
                    f"NPZ energy_total dtype must be float32, "
                    f"got {energy_arr.dtype}"
                )
            # Cross-check metadata JSON.
            meta_arr = data["metadata_json"]
            meta = json.loads(str(meta_arr.item()))
            if meta.get("dtype") != "float32":
                raise PersistenceError(
                    f"NPZ metadata dtype mismatch: expected 'float32', "
                    f"got {meta.get('dtype')!r}"
                )
            if meta.get("axes_order") != "xyz":
                raise PersistenceError(
                    f"NPZ metadata axes_order mismatch: expected 'xyz', "
                    f"got {meta.get('axes_order')!r}"
                )
            # Verify SHA-256 unchanged after re-read.
            actual_digest = sha256_file(tmp_npz)
            if actual_digest != digest:
                raise PersistenceError(
                    f"NPZ SHA-256 mismatch after write: "
                    f"expected {digest}, got {actual_digest}"
                )
            # Verify first_arrival_s dtype if present.
            if "first_arrival_s" in files:
                t_arr = data["first_arrival_s"]
                if t_arr.dtype != np.float32:
                    raise PersistenceError(
                        f"NPZ first_arrival_s dtype must be float32, "
                        f"got {t_arr.dtype}"
                    )

        # 5. Build the updated result with the artifact references.
        new_grid = replace(
            result.grid_metadata,
            npz_sha256=digest,
        )
        new_energy_field = replace(
            result.energy_field,
            grid=new_grid,
            npz_path=str(final_npz),
        )
        updated_result = replace(
            result,
            grid_metadata=new_grid,
            energy_field=new_energy_field,
        )

        # 6. Write the JSON summary.
        summary_payload = updated_result.to_dict()
        tmp_summary.write_text(
            json.dumps(summary_payload, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )

        # 7. Validate the JSON.
        re_read = json.loads(tmp_summary.read_text(encoding="utf-8"))
        if re_read.get("simulation_id") != result.simulation_id:
            raise PersistenceError(
                f"JSON simulation_id mismatch: expected "
                f"{result.simulation_id!r}, got "
                f"{re_read.get('simulation_id')!r}"
            )

        # 8. Atomic rename — first inside the tmp dir (.tmp → real names),
        # then the tmp dir itself → sim_dir.
        inner_npz = tmp_dir / "energy_field.npz"
        inner_summary = tmp_dir / "simulation_summary.json"
        tmp_npz.rename(inner_npz)
        tmp_summary.rename(inner_summary)

        # 9. Replace the final sim_dir in one atomic step.
        if sim_dir.exists():
            shutil.rmtree(sim_dir)
        tmp_dir.rename(sim_dir)

        return updated_result, final_npz, digest, final_summary

    except Exception:
        # 10. Cleanup on any failure: remove the .tmp directory entirely.
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        raise


# ---------------------------------------------------------------------------
# Backwards-compat wrapper
# ---------------------------------------------------------------------------


def write_npz_artifact(
    *,
    result: SimulationResult,
    accepted_rows: list[dict[str, Any]],
    configuration: SimulationConfiguration,
    data_dir: Path | str | None = None,
    segments_per_hole: int = 8,
    support_radius_m: Optional[float] = None,
) -> tuple[SimulationResult, Path, str]:
    """Backwards-compatible wrapper around :func:`write_atomic_simulation`.

    Returns ``(updated_result, npz_path, sha256)`` — the JSON summary
    path is omitted for callers that don't need it. The atomic-write
    semantics and SHA-256 protected-NPZ contract are identical to
    :func:`write_atomic_simulation`.
    """
    updated, npz_path, sha, _summary_path = write_atomic_simulation(
        result=result,
        accepted_rows=accepted_rows,
        configuration=configuration,
        data_dir=data_dir,
        segments_per_hole=segments_per_hole,
        support_radius_m=support_radius_m,
    )
    return updated, npz_path, sha


# ---------------------------------------------------------------------------
# Read-back
# ---------------------------------------------------------------------------


def read_npz_artifact(
    npz_path: Path | str,
    *,
    expected_sha256: str | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any], str]:
    """Read and verify a simulation NPZ artifact.

    Validates (in order):

    * The file exists.
    * ``expected_sha256`` matches the file's actual SHA-256 (if provided).
    * ``voxel_count`` declared in metadata matches the array sizes.
    * ``dtype`` declared in metadata matches the stored array dtype.
    * ``axes_order`` declared in metadata is the canonical ``"xyz"``.
    * ``first_arrival_s`` dtype (when present) is float32.
    * No pickle is used (``allow_pickle=False``).

    Returns ``(arrays, metadata, sha256)``.
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
    # Verify dtype matches metadata.
    if "energy_total" in arrays:
        actual_dtype = str(arrays["energy_total"].dtype)
        declared_dtype = metadata.get("dtype", "")
        if declared_dtype and actual_dtype != declared_dtype:
            raise PersistenceError(
                f"energy_total dtype mismatch: declared {declared_dtype}, "
                f"actual {actual_dtype}"
            )
    # Verify axes_order.
    declared_axes = metadata.get("axes_order", "")
    if declared_axes and declared_axes != "xyz":
        raise PersistenceError(
            f"axes_order mismatch: expected 'xyz', got {declared_axes!r}"
        )
    # Verify first_arrival_s dtype if present.
    if "first_arrival_s" in arrays:
        t_arr = arrays["first_arrival_s"]
        if t_arr.dtype != np.float32:
            raise PersistenceError(
                f"first_arrival_s dtype must be float32, got {t_arr.dtype}"
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
    out.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


def read_summary_json(path: Path | str) -> dict[str, Any]:
    """Read a simulation summary JSON and return the parsed dict."""
    p = Path(path)
    if not p.exists():
        raise PersistenceError(f"Summary JSON not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


__all__ = [
    "PersistenceError",
    "compute_field_arrays",
    "npz_path_for",
    "read_npz_artifact",
    "read_summary_json",
    "sha256_bytes",
    "sha256_file",
    "should_persist",
    "simulation_dir",
    "summary_path_for",
    "write_atomic_simulation",
    "write_npz_artifact",
    "write_summary_json",
]
