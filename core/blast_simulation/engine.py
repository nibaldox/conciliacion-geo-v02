"""Deterministic voxel energy engine — Phase 2 core.

Orchestrates the contracts, grid, charge-segment builder, spatial kernel
and temporal layer to produce the canonical
:class:`SimulationResult`. The engine is deterministic: identical inputs
(config + accepted_rows) produce identical outputs.

Design rules (spec §6):

* All physics lives here. Routers, React and Streamlit consume the
  result; they NEVER reimplement the engine.
* NumPy-vectorized; iteration is per-source (per charge segment), with
  per-voxel accumulator arrays reused across sources.
* No dense ``(n_sources × n_voxels)`` matrix is materialised; per-source
  evaluation writes directly into the accumulators.
* Resource ceilings (max voxel count, max segments, estimated peak
  memory) are enforced BEFORE any heavy allocation.

Conservation invariant (spec §4.2):

    Σ_voxel energy_in_domain ≤ Σ_source E_acoplada

The remainder is reported as ``outside_domain_energy_j``. Truncated
domains are NEVER silently renormalized.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from core.blast_simulation.charges import (
    build_charge_segments,
    classify_segments,
)
from core.blast_simulation.contracts import (
    AnisotropyMode,
    ChargeSegment,
    DomainBounds,
    EnergyMode,
    GridMetadata,
    PlanSlice,
    ProcessingSummary,
    RockMassConfiguration,
    SectionSlice,
    SimulationConfiguration,
    SimulationConfigurationError,
    SimulationDiagnostics,
    SimulationProvenance,
    SimulationResult,
    SimulationSourceSummary,
    TemporalMode,
    VoxelEnergyField,
    VoxelGridSpecification,
)
from core.blast_simulation.grid import (
    estimated_memory_bytes,
    reshape_to_grid,
    voxel_centres_flat,
)
from core.blast_simulation.kernels import (
    compute_distance,
    kernel_total_mass,
    radial_kernel,
)
from core.blast_simulation.temporal import (
    NOT_AVAILABLE,
    resolve_temporal_status,
)
from core.config import SIMULATION

ENGINE_VERSION = "blast-sim-1.0.0"


# ---------------------------------------------------------------------------
# Resource guards
# ---------------------------------------------------------------------------


def _estimate_voxels(grid: VoxelGridSpecification) -> int:
    return grid.voxel_count


def _check_resource_limits(
    *,
    grid: VoxelGridSpecification,
    n_segments: int,
    block_size: int,
) -> dict[str, Any]:
    """Surface a structured error before allocating any large array."""
    n_voxels = _estimate_voxels(grid)
    if n_voxels > SIMULATION.max_voxel_count:
        raise SimulationConfigurationError(
            "El número de vóxeles excede el límite de seguridad.",
            error_code="VOXEL_COUNT_OVER_LIMIT",
            details={
                "voxel_count": n_voxels,
                "limit": SIMULATION.max_voxel_count,
                "recommended_action": "aumente voxel_size_m o reduzca el dominio",
            },
        )
    if n_segments > SIMULATION.max_charge_segments:
        raise SimulationConfigurationError(
            "El número de segmentos de carga excede el límite de seguridad.",
            error_code="SEGMENT_COUNT_OVER_LIMIT",
            details={
                "segment_count": n_segments,
                "limit": SIMULATION.max_charge_segments,
            },
        )
    mem_bytes = estimated_memory_bytes(
        n_voxels=n_voxels,
        n_sources=max(1, n_segments),
        block_size=block_size,
    )
    mem_gb = mem_bytes / (1024.0 ** 3)
    if mem_gb > SIMULATION.max_estimated_memory_gb:
        raise SimulationConfigurationError(
            "La memoria estimada excede el límite de seguridad.",
            error_code="MEMORY_OVER_LIMIT",
            details={
                "estimated_memory_gb": mem_gb,
                "limit_gb": SIMULATION.max_estimated_memory_gb,
                "voxel_count": n_voxels,
                "segment_count": n_segments,
            },
        )
    return {
        "voxel_count": n_voxels,
        "segment_count": n_segments,
        "estimated_peak_memory_gb": mem_gb,
        "block_size": block_size,
    }


# ---------------------------------------------------------------------------
# Per-source energy
# ---------------------------------------------------------------------------


def _source_coupled_energy(
    seg: ChargeSegment,
    *,
    coupling_efficiency: float,
    energy_mode: str,
) -> Optional[float]:
    """Compute the per-segment coupled energy ``E_acoplada`` in joules.

    For ``ABSOLUTE`` mode, returns ``kg × MJ/kg × 1e6 × η``. For
    ``RELATIVE`` mode, returns ``kg × η`` (a kg-equivalent weight used
    only to normalize the field; the result is tagged dimensionless).
    Returns ``None`` when the segment cannot contribute (no explosive
    energy in ABSOLUTE mode, or zero mass).
    """
    if seg.mass_kg <= 0.0:
        return None
    if energy_mode == EnergyMode.ABSOLUTE:
        if seg.energy_j is None or seg.energy_j <= 0.0:
            return None
        # seg.energy_j already encodes kg × MJ/kg × 1e6 (set by charges.py);
        # we still need to apply the coupling efficiency.
        return float(seg.energy_j) * float(coupling_efficiency)
    # RELATIVE — use kg as the "energy-equivalent" weight.
    return float(seg.mass_kg) * float(coupling_efficiency)


def _accumulate_source(
    *,
    seg: ChargeSegment,
    e_acoplada: float,
    voxel_centres: np.ndarray,
    grid: VoxelGridSpecification,
    config: SimulationConfiguration,
    kernel_total: float,
    energy_total: np.ndarray,
    contributing_count: np.ndarray,
    dominant_idx: np.ndarray,
    dominant_energy: np.ndarray,
    arrival_times: Optional[np.ndarray],
    first_arrival: Optional[np.ndarray],
    time_of_max: Optional[np.ndarray],
    pulse_sigma: Optional[float],
    total_represented: list[float],
    total_outside: list[float],
    per_hole_energy: dict[str, float],
) -> None:
    """Distribute one source's energy across the voxel field.

    Updates the accumulator arrays in place. Records the represented and
    out-of-domain energy in the passed lists so the caller can compute
    the totals.

    Normalisation policy (spec §4.2): each voxel receives
    ``e_j = E_acoplada × w_j / W_inf`` where ``W_inf`` is the kernel's
    total mass integrated over all 3D space. The sum over in-domain
    voxels can therefore be strictly less than ``E_acoplada`` when the
    domain truncates the source's effective support — the remainder is
    reported as ``outside_domain_energy_j`` and NEVER silently rescaled.
    """
    src = np.asarray([seg.cx, seg.cy, seg.cz], dtype=np.float64)
    delta = voxel_centres - src
    tensor = (
        np.asarray(config.rock_mass.anisotropy_tensor, dtype=np.float64)
        if config.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR
        and config.rock_mass.anisotropy_tensor is not None
        else None
    )
    r = compute_distance(delta, anisotropy_mode=config.anisotropy_mode, tensor=tensor)

    b = grid.bounds
    in_domain = (
        (voxel_centres[:, 0] >= b.x_min)
        & (voxel_centres[:, 0] <= b.x_max)
        & (voxel_centres[:, 1] >= b.y_min)
        & (voxel_centres[:, 1] <= b.y_max)
        & (voxel_centres[:, 2] >= b.z_min)
        & (voxel_centres[:, 2] <= b.z_max)
    )

    # Kernel weights restricted to in-domain voxels.
    k = radial_kernel(
        r[in_domain],
        attenuation_coefficient_1_m=config.attenuation_coefficient_1_m,
        regularization_radius_m=config.regularization_radius_m,
    )
    w = k * grid.voxel_volume_m3
    W_in_domain = float(w.sum())

    if kernel_total <= 0.0 or W_in_domain <= 0.0:
        # Pathological: kernel is entirely out of the domain or numerical
        # underflow. Nothing reaches the domain.
        total_outside.append(float(e_acoplada))
        return

    # Per-voxel energy: e_j = E × w_j / W_inf (NOT / W_in_domain).
    # Truncated energy is reported, never silently renormalised.
    e_j = np.zeros(voxel_centres.shape[0], dtype=np.float64)
    e_j[in_domain] = float(e_acoplada) * (w / kernel_total)
    represented = float(e_j.sum())
    outside = float(e_acoplada) - represented

    # Conservation bookkeeping.
    total_represented.append(represented)
    total_outside.append(outside)

    # Accumulate into the field.
    energy_total += e_j
    contributing_count[e_j > 0.0] += 1

    # Dominant source: where this contribution exceeds the current max.
    contribution = e_j
    improved = contribution > dominant_energy
    if np.any(improved):
        dominant_energy[improved] = contribution[improved]
        # Use the hash of hole_id to keep deterministic non-negative int.
        # The hole_id string is preserved separately in the NPZ.
        dominant_idx[improved] = _stable_hole_index(seg.hole_id)

    per_hole_energy[seg.hole_id] = per_hole_energy.get(seg.hole_id, 0.0) + represented

    # Temporal layer.
    if (
        config.temporal_mode == TemporalMode.TEMPORAL
        and config.propagation_velocity_m_s is not None
        and pulse_sigma is not None
    ):
        v = float(config.propagation_velocity_m_s)
        t_det = seg.detonation_time_s if seg.detonation_time_s is not None else 0.0
        t_arr = t_det + r / v
        # Only voxels that actually receive energy from this source can
        # observe a pulse arrival.
        arriving = e_j > 0.0
        if np.any(arriving):
            t_arr_arr = t_arr[arriving]
            np.minimum.at(first_arrival, np.where(arriving)[0], t_arr_arr)


def _stable_hole_index(hole_id: str) -> int:
    """Stable non-negative int per hole_id (deterministic across runs).

    Uses the first 8 bytes of SHA-256 so the same string always maps to
    the same integer regardless of insertion order.
    """
    h = hashlib.sha256(hole_id.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "little", signed=False)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_simulation(
    *,
    accepted_rows: list[dict[str, Any]],
    configuration: SimulationConfiguration,
    segments_per_hole: int = 8,
    block_size: Optional[int] = None,
) -> SimulationResult:
    """Run the deterministic voxel energy simulation.

    Parameters
    ----------
    accepted_rows
        The accepted rows from the Fase 1 ``ProcessingResult``. Rejected
        rows MUST NOT be passed — the engine cannot run on them.
    configuration
        A fully validated :class:`SimulationConfiguration`
        (``user_confirmed=True``).
    segments_per_hole
        Number of explosive-column sub-segments per hole (default 8).
    block_size
        Voxel block size for chunked evaluation. Defaults to
        :data:`core.config.SIMULATION.chunk_voxel_block`.

    Returns
    -------
    SimulationResult
        The canonical result. The raw 3D field is NOT embedded in the
        returned object — it is written to an NPZ artifact referenced by
        ``energy_field.npz_path``. Callers (persistence layer) are
        responsible for materialising that artifact.
    """
    # 1. Validate the configuration (raises structured errors).
    configuration.validate()

    if configuration.energy_mode == EnergyMode.ABSOLUTE:
        # ABSOLUTE requires the rock mass to carry valid wave velocity
        # etc. — but the simulation itself only needs the explosive
        # energy, which is checked per segment. Rock-mass validation is
        # done by the contract. Nothing else to enforce here.
        pass

    # 2. Build the grid + charge segments.
    grid = VoxelGridSpecification(
        voxel_size_m=configuration.voxel_size_m,
        bounds=configuration.domain_bounds,
    )
    grid.validate()

    block = block_size or SIMULATION.chunk_voxel_block
    segments = build_charge_segments(
        accepted_rows,
        config=configuration,
        segments_per_hole=segments_per_hole,
    )

    # 3. Resource ceiling check (before any large allocation).
    resource_info = _check_resource_limits(
        grid=grid,
        n_segments=len(segments),
        block_size=block,
    )

    # 4. Classify segments.
    valid, invalid, seg_diag = classify_segments(
        segments,
        energy_mode=configuration.energy_mode,
    )

    # 5. ABSOLUTE mode blocking check.
    blocking_errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if configuration.energy_mode == EnergyMode.ABSOLUTE and seg_diag["invalid_no_energy_absolute"] > 0:
        blocking_errors.append({
            "error_code": "ABSOLUTE_MODE_BLOCKED",
            "message": (
                f"{seg_diag['invalid_no_energy_absolute']} segmentos no tienen energía "
                "específica resoluble; el modo ABSOLUTE está bloqueado."
            ),
            "details": seg_diag,
            "recommended_action": (
                "use energy_mode=RELATIVE, or correct the explosive product names "
                "in the accepted rows"
            ),
        })

    # 6. Allocate the accumulator arrays.
    n_voxels = grid.voxel_count
    voxel_centres = voxel_centres_flat(grid)
    energy_total = np.zeros(n_voxels, dtype=np.float64)
    contributing_count = np.zeros(n_voxels, dtype=np.int32)
    dominant_idx = np.zeros(n_voxels, dtype=np.int64)
    dominant_energy = np.zeros(n_voxels, dtype=np.float64)

    # Temporal accumulators (only allocated in TEMPORAL mode).
    is_temporal = configuration.temporal_mode == TemporalMode.TEMPORAL
    first_arrival = (
        np.full(n_voxels, np.inf, dtype=np.float64) if is_temporal else None
    )
    time_of_max = (
        np.full(n_voxels, np.nan, dtype=np.float64) if is_temporal else None
    )

    # Resolve the pulse sigma (may fall back to the SIMULATION default).
    pulse_sigma = None
    if is_temporal:
        pulse_sigma = (
            configuration.pulse_sigma_s
            if configuration.pulse_sigma_s is not None
            else SIMULATION.fallback_temporal_sigma_s
        )

    # 7. Iterate over valid sources.
    total_represented: list[float] = []
    total_outside: list[float] = []
    per_hole_energy: dict[str, float] = {}

    # Compute the kernel's total mass over all 3D space ONCE. This is
    # the normalisation denominator for every source — it lets us
    # honestly report how much of each source's energy fell outside the
    # domain without silently renormalising truncated fields (spec §4.2).
    kernel_total = kernel_total_mass(
        attenuation_coefficient_1_m=configuration.attenuation_coefficient_1_m,
        regularization_radius_m=configuration.regularization_radius_m,
    )
    # Anisotropy rescales the kernel mass: in the transformed coordinate
    # u = M^(1/2) x, the Jacobian of the inverse map is 1/sqrt(det M), so
    # the integral over all original space is W_inf_iso / sqrt(det M).
    if (
        configuration.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR
        and configuration.rock_mass.anisotropy_tensor is not None
    ):
        M = np.asarray(configuration.rock_mass.anisotropy_tensor, dtype=np.float64)
        det_M = float(np.linalg.det(M))
        if det_M > 0.0:
            kernel_total = kernel_total / math.sqrt(det_M)

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
            grid=grid,
            config=configuration,
            kernel_total=kernel_total,
            energy_total=energy_total,
            contributing_count=contributing_count,
            dominant_idx=dominant_idx,
            dominant_energy=dominant_energy,
            arrival_times=None,
            first_arrival=first_arrival,
            time_of_max=time_of_max,
            pulse_sigma=pulse_sigma,
            total_represented=total_represented,
            total_outside=total_outside,
            per_hole_energy=per_hole_energy,
        )

    # 8. Finalize the field.
    represented_energy = float(sum(total_represented))
    outside_energy = float(sum(total_outside))
    coupled_total = represented_energy + outside_energy
    fraction = (represented_energy / coupled_total) if coupled_total > 0.0 else 0.0

    active_mask = energy_total > 0.0
    active_voxels = int(active_mask.sum())
    max_energy = float(energy_total.max()) if n_voxels > 0 else 0.0
    mean_energy_active = (
        float(energy_total[active_mask].mean()) if active_voxels > 0 else 0.0
    )

    # Replace inf in first_arrival with NaN for the no-arrival voxels.
    if first_arrival is not None:
        first_arrival[~np.isfinite(first_arrival)] = np.nan

    energy_unit = "J" if configuration.energy_mode == EnergyMode.ABSOLUTE else "dimensionless"

    # 9. Temporal status.
    temporal_status = resolve_temporal_status(
        temporal_mode=configuration.temporal_mode,
        propagation_velocity_m_s=configuration.propagation_velocity_m_s,
        detonation_times=[s.detonation_time_s for s in valid],
        pulse_sigma_s=configuration.pulse_sigma_s,
        fallback_sigma_s=SIMULATION.fallback_temporal_sigma_s,
    )

    # 10. Build the canonical result.
    simulation_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    grid_metadata = GridMetadata(
        shape=grid.shape,
        voxel_size_m=grid.voxel_size_m,
        bounds=grid.bounds,
        axes_order="xyz",
        energy_unit=energy_unit,
        dtype="float32",
        voxel_count=n_voxels,
        voxel_volume_m3=grid.voxel_volume_m3,
        npz_sha256="",  # filled by the persistence layer on write
        created_at=created_at,
    )

    source_summary = SimulationSourceSummary(
        source_rows=len(accepted_rows),
        accepted_holes=len({s.hole_id for s in valid} | {s.hole_id for s in invalid}),
        rejected_holes=0,  # caller-side concern; engine never sees rejected rows
        charge_segments=len(segments),
        valid_sources=len(valid),
        invalid_sources=len(invalid),
        voxel_count=n_voxels,
        active_voxels=active_voxels,
        represented_energy_j=represented_energy,
        outside_domain_energy_j=outside_energy,
        warning_count=len(warnings),
        blocking_error_count=len(blocking_errors),
    )

    energy_field = VoxelEnergyField(
        grid=grid_metadata,
        represented_energy_j=represented_energy,
        outside_domain_energy_j=outside_energy,
        total_coupled_energy_j=coupled_total,
        fraction_represented=fraction,
        active_voxels=active_voxels,
        max_energy_j=max_energy,
        mean_energy_j_active=mean_energy_active,
        npz_path="",  # filled by the persistence layer
        energy_unit=energy_unit,
    )

    processing_summary = ProcessingSummary(
        accepted_holes=source_summary.accepted_holes,
        charge_segments=len(segments),
        valid_sources=len(valid),
        invalid_sources=len(invalid),
        voxel_count=n_voxels,
        active_voxels=active_voxels,
        represented_energy_j=represented_energy,
        outside_domain_energy_j=outside_energy,
        total_coupled_energy_j=coupled_total,
        fraction_represented=fraction,
        warning_records=len(warnings),
        blocking_error_records=len(blocking_errors),
        temporal_status=temporal_status,
        energy_mode=configuration.energy_mode,
    )

    spatial_diagnostics = {
        "resource_info": resource_info,
        "segment_diagnostics": seg_diag,
        "per_hole_represented_energy_j": dict(per_hole_energy),
    }
    temporal_diagnostics = (
        {
            "first_arrival_min_s": float(np.nanmin(first_arrival)) if first_arrival.size and np.isfinite(first_arrival).any() else None,
            "first_arrival_max_s": float(np.nanmax(first_arrival)) if first_arrival.size and np.isfinite(first_arrival).any() else None,
            "pulse_sigma_s": pulse_sigma,
        }
        if is_temporal
        else {"temporal_status": temporal_status}
    )

    provenance = SimulationProvenance(
        engine_version=ENGINE_VERSION,
        simulation_configuration_version=configuration.simulation_configuration_version,
        geometry_configuration_version=configuration.geometry_configuration_version,
        explosive_registry_source="core.explosive_properties.EXPLOSIVE_PRODUCTS",
        explosive_products_used=tuple(sorted({s.explosive_name for s in valid})),
        rock_mass_source=configuration.rock_mass.source,
        propagation_velocity_source=configuration.propagation_velocity_source,
        assumptions=configuration.rock_mass.assumptions,
        warnings=tuple(),
        accepted_rows_hash=_hash_accepted_rows(accepted_rows),
    )

    return SimulationResult(
        simulation_id=simulation_id,
        configuration=configuration.to_dict(),
        grid_metadata=grid_metadata,
        source_summary=source_summary,
        energy_field=energy_field,
        plan_slices=(),  # filled by slicing.py
        section_slices=(),  # filled by slicing.py
        processing_summary=processing_summary,
        warnings=tuple(warnings),
        blocking_errors=tuple(blocking_errors),
        spatial_diagnostics=spatial_diagnostics,
        temporal_diagnostics=temporal_diagnostics,
        provenance=provenance,
        created_at=created_at,
        engine_version=ENGINE_VERSION,
    )


def _hash_accepted_rows(accepted_rows: list[dict[str, Any]]) -> str:
    """Stable SHA-256 over the accepted rows (JSON-serialised, sorted keys)."""
    try:
        canonical = json.dumps(accepted_rows, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = repr(accepted_rows)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Field extraction helpers — used by slicing + persistence layers
# ---------------------------------------------------------------------------


def export_field_arrays(
    *,
    result: SimulationResult,
    accepted_rows: list[dict[str, Any]],
    configuration: SimulationConfiguration,
    segments_per_hole: int = 8,
) -> dict[str, np.ndarray]:
    """Recompute the canonical field arrays for NPZ persistence.

    The engine result carries only aggregate metadata; the actual 3D
    arrays are reproduced deterministically from the same inputs so the
    NPZ artifact can be SHA-256 verified on read-back.

    Returns a dict suitable for ``np.savez_compressed``.
    """
    grid = VoxelGridSpecification(
        voxel_size_m=configuration.voxel_size_m,
        bounds=configuration.domain_bounds,
    )
    voxel_centres = voxel_centres_flat(grid)

    segments = build_charge_segments(
        accepted_rows,
        config=configuration,
        segments_per_hole=segments_per_hole,
    )
    valid, _, _ = classify_segments(segments, energy_mode=configuration.energy_mode)

    kernel_total = kernel_total_mass(
        attenuation_coefficient_1_m=configuration.attenuation_coefficient_1_m,
        regularization_radius_m=configuration.regularization_radius_m,
    )
    if (
        configuration.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR
        and configuration.rock_mass.anisotropy_tensor is not None
    ):
        M = np.asarray(configuration.rock_mass.anisotropy_tensor, dtype=np.float64)
        det_M = float(np.linalg.det(M))
        if det_M > 0.0:
            kernel_total = kernel_total / math.sqrt(det_M)

    energy_total = np.zeros(grid.voxel_count, dtype=np.float32)
    contributing_count = np.zeros(grid.voxel_count, dtype=np.int32)
    dominant_idx = np.zeros(grid.voxel_count, dtype=np.int64)
    dominant_energy = np.zeros(grid.voxel_count, dtype=np.float32)

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
            grid=grid,
            config=configuration,
            kernel_total=kernel_total,
            energy_total=energy_total,
            contributing_count=contributing_count,
            dominant_idx=dominant_idx,
            dominant_energy=dominant_energy,
            arrival_times=None,
            first_arrival=None,
            time_of_max=None,
            pulse_sigma=None,
            total_represented=[],
            total_outside=[],
            per_hole_energy={},
        )

    out: dict[str, np.ndarray] = {
        "energy_total": energy_total.astype(np.float32),
        "energy_density": (energy_total / grid.voxel_volume_m3).astype(np.float32),
        "contributing_count": contributing_count,
        "dominant_idx": dominant_idx,
        "dominant_energy": dominant_energy.astype(np.float32),
        "voxel_centres": voxel_centres.astype(np.float32),
    }
    if configuration.temporal_mode == TemporalMode.TEMPORAL:
        first_arrival = np.full(grid.voxel_count, np.nan, dtype=np.float32)
        time_of_max = np.full(grid.voxel_count, np.nan, dtype=np.float32)
        # Re-evaluate temporal layer for the export. For now we expose the
        # raw first-arrival placeholder; a richer implementation would
        # recompute it identically to the engine run.
        out["first_arrival_s"] = first_arrival
        out["time_of_max_s"] = time_of_max
    return out
