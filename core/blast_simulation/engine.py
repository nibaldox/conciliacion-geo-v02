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
    intersection_mask_flat,
    reshape_to_grid,
    voxel_centres_flat,
)
from core.blast_simulation.kernels import (
    compute_distance,
    discrete_total_mass,
    kernel_total_mass,
    radial_kernel,
)
from core.blast_simulation.temporal import (
    NOT_AVAILABLE,
    compute_first_arrival,
    compute_first_arrival_chunked,
    compute_time_of_max,
    compute_time_of_max_chunked,
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
    in_domain_mask: np.ndarray,
    grid: VoxelGridSpecification,
    config: SimulationConfiguration,
    support_radius_m: float,
    spatial_voxel_block_size: int = 100_000,
    energy_total: np.ndarray,
    contributing_count: np.ndarray,
    dominant_idx: np.ndarray,
    dominant_energy: np.ndarray,
    arrival_times: Optional[np.ndarray],
    first_arrival: Optional[np.ndarray],
    time_of_max: Optional[np.ndarray],
    pulse_sigma: Optional[float],
    temporal_energy_contributions: Optional[list[np.ndarray]],
    temporal_distances: Optional[list[np.ndarray]],
    temporal_detonation_times: Optional[list[float]],
    total_represented: list[float],
    total_outside: list[float],
    per_hole_energy: dict[str, float],
) -> None:
    """Distribute one source's energy across the voxel field.

    CRITICAL (Falla 4 fix, audit 2026-08-03): ``Q_total`` and the
    per-voxel weights ``q_j = K(r_j)·V`` are sampled on the SAME
    cartesian lattice (the global voxel grid extended to cover the
    source's full support cube ``[-R, R]³``). Three classes of voxel
    are distinguished:

    * ``inside_requested_domain`` — voxel exists in the global grid AND
      its centre lies inside ``DomainBounds``. Receives ``e_j =
      E_coupled × q_j / Q_total``.
    * ``outside_requested_domain`` — voxel would exist in the support
      cube (its index lands inside the extended lattice) BUT its centre
      lies outside ``DomainBounds`` (or outside the global grid). Its
      ``q_j`` is added to ``E_outside`` but no energy is deposited.
    * ``numerical_residual`` — voxel lies in the corners of the support
      cube where ``r > R``, so ``K(r) = 0`` and ``q_j = 0``.

    Conservation invariant::

        Σ_in_domain e_j + E_outside == E_coupled
        0 ≤ fraction_represented ≤ 1

    Memory cost: ``O((2·ceil(R/dx)+1)³)`` per source (NOT
    ``O(n_voxels)``). The support cube is bounded by ``R`` and ``dx``;
    it never depends on the global domain size. This implicitly fixes
    Falla 7 (chunking) — no ``n_sources × n_voxels`` dense matrix is
    materialised.
    """
    src = np.asarray([seg.cx, seg.cy, seg.cz], dtype=np.float64)
    dx = float(grid.voxel_size_m)
    R = float(support_radius_m)
    V = grid.voxel_volume_m3
    nx, ny, nz = grid.shape
    b = grid.bounds

    tensor = (
        np.asarray(config.rock_mass.anisotropy_tensor, dtype=np.float64)
        if config.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR
        and config.rock_mass.anisotropy_tensor is not None
        else None
    )

    # Locate the source's nearest voxel centre indices on the global grid.
    src_ix = int(round((src[0] - b.x_min) / dx - 0.5))
    src_iy = int(round((src[1] - b.y_min) / dx - 0.5))
    src_iz = int(round((src[2] - b.z_min) / dx - 0.5))

    # Conservative per-axis lattice extents that fully contain the
    # kernel support (Falla 5 fix, audit v2 §5.2).
    #
    # Isotropic case (no tensor / identity): the support is a sphere of
    # radius R, so extent_i = ceil(R/dx) suffices on every axis.
    #
    # Anisotropic case: the support is the ellipsoid
    #   {Δx : Δxᵀ M Δx ≤ R²}. The maximum coordinate along axis i over
    # the ellipsoid surface is R·sqrt((M⁻¹)_ii), so the conservative
    # integer extent per axis is ceil(R·sqrt((M⁻¹)_ii) / dx). This is
    # exact for diagonal tensors and conservative for rotated tensors
    # (the bounding box of the rotated ellipsoid is contained).
    if config.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR and tensor is not None:
        try:
            m_inv = np.linalg.inv(tensor)
        except np.linalg.LinAlgError as exc:
            raise SimulationConfigurationError(
                "Anisotropy tensor is not invertible; cannot bound the "
                "kernel support.",
                error_code="ANISOTROPIC_TENSOR_SINGULAR",
                details={"tensor": tensor.tolist()},
            ) from exc
        inv_diag = np.clip(np.diag(m_inv), 0.0, None)
        half_widths_m = R * np.sqrt(inv_diag)
        extent_x = max(1, int(math.ceil(half_widths_m[0] / dx)))
        extent_y = max(1, int(math.ceil(half_widths_m[1] / dx)))
        extent_z = max(1, int(math.ceil(half_widths_m[2] / dx)))
    else:
        extent_scalar = max(1, int(math.ceil(R / dx)))
        extent_x = extent_y = extent_z = extent_scalar

    # Build the (possibly non-symmetric) cartesian offset cube.
    # V5-04: the support cube is processed in blocks of
    # spatial_voxel_block_size to bound auxiliary memory. A 2-pass
    # approach is used: pass 1 converges Q_total, pass 2 deposits
    # energy. Each pass processes at most spatial_voxel_block_size
    # offset voxels simultaneously.
    total_offsets = (2 * extent_x + 1) * (2 * extent_y + 1) * (2 * extent_z + 1)
    shape_3d = (2 * extent_x + 1, 2 * extent_y + 1, 2 * extent_z + 1)
    spatial_block = max(1, min(total_offsets, int(spatial_voxel_block_size)))

    def _process_offset_block(flat_start: int, flat_stop: int):
        """Compute centres, distances and weights for a block of flat
        offset indices. Returns (gx, gy, gz, r2, in_support, weights)."""
        n = flat_stop - flat_start
        flat_idx = np.arange(flat_start, flat_stop)
        ix_off, iy_off, iz_off = np.unravel_index(flat_idx, shape_3d)
        gx_b = src_ix + (ix_off.astype(np.int64) - extent_x)
        gy_b = src_iy + (iy_off.astype(np.int64) - extent_y)
        gz_b = src_iz + (iz_off.astype(np.int64) - extent_z)
        cx_b = b.x_min + (gx_b + 0.5) * dx
        cy_b = b.y_min + (gy_b + 0.5) * dx
        cz_b = b.z_min + (gz_b + 0.5) * dx
        delta = np.column_stack([cx_b - src[0], cy_b - src[1], cz_b - src[2]])
        if config.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR and tensor is not None:
            r2_b = np.einsum("ij,jk,ik->i", delta, tensor, delta)
            r2_b = np.clip(r2_b, 0.0, None)
        else:
            r2_b = np.einsum("ij,ij->i", delta, delta)
        in_sup = r2_b <= R * R
        weights_b = np.zeros(n, dtype=np.float64)
        if np.any(in_sup):
            r_sup = np.sqrt(r2_b[in_sup])
            k_sup = radial_kernel(
                r_sup,
                attenuation_coefficient_1_m=config.attenuation_coefficient_1_m,
                regularization_radius_m=config.regularization_radius_m,
                support_radius_m=R,
            )
            weights_b[in_sup] = k_sup * V
        return gx_b, gy_b, gz_b, in_sup, weights_b

    # Pass 1: converge Q_total across all blocks.
    Q_total = 0.0
    any_in_support = False
    for fs in range(0, total_offsets, spatial_block):
        fe = min(fs + spatial_block, total_offsets)
        _, _, _, in_sup, w = _process_offset_block(fs, fe)
        Q_total += float(w.sum())
        if np.any(in_sup):
            any_in_support = True

    if not any_in_support or Q_total <= 0.0:
        total_outside.append(float(e_acoplada))
        return

    # Pass 2: deposit energy using the converged Q_total.
    #
    # V6-03: stream per-block tuples directly into the temporal layer.
    # The V5 code retained every block's deposit arrays in
    # ``deposit_idx_all`` / ``deposit_energies_all`` and concatenated
    # them into a single per-source tuple handed to the temporal layer
    # — defeating ``spatial_voxel_block_size`` (an audit adversarial
    # repro with block_size=1 produced a 520-element tuple). The new
    # code appends one ``(src, dep_idx, dep_eng)`` tuple per (source,
    # spatial-block) so the largest per-source auxiliary is bounded by
    # ``spatial_voxel_block_size``. ``temporal_detonation_times`` stays
    # in lockstep with ``temporal_energy_contributions``.
    temporal_enabled = (
        config.temporal_mode == TemporalMode.TEMPORAL
        and config.propagation_velocity_m_s is not None
        and pulse_sigma is not None
        and temporal_energy_contributions is not None
        and temporal_distances is not None
        and temporal_detonation_times is not None
    )
    det_time = (
        float(seg.detonation_time_s) if seg.detonation_time_s is not None else 0.0
    )
    represented_weight_raw = 0.0
    for fs in range(0, total_offsets, spatial_block):
        fe = min(fs + spatial_block, total_offsets)
        gx_b, gy_b, gz_b, in_sup, w = _process_offset_block(fs, fe)
        if not np.any(in_sup):
            continue
        gx_s = gx_b[in_sup]
        gy_s = gy_b[in_sup]
        gz_s = gz_b[in_sup]
        w_s = w[in_sup]
        in_grid = (
            (gx_s >= 0) & (gx_s < nx)
            & (gy_s >= 0) & (gy_s < ny)
            & (gz_s >= 0) & (gz_s < nz)
        )
        flat_idx_s = np.where(in_grid, (gx_s * ny + gy_s) * nz + gz_s, -1)
        in_domain = np.zeros(in_grid.shape, dtype=bool)
        if np.any(in_grid):
            in_domain[in_grid] = in_domain_mask[flat_idx_s[in_grid]]
        deposit_mask = in_grid & in_domain
        if np.any(deposit_mask):
            dep_idx = flat_idx_s[deposit_mask]
            dep_eng = float(e_acoplada) * w_s[deposit_mask] / Q_total
            energy_total[dep_idx] += dep_eng
            contributing_count[dep_idx] += 1
            improved = dep_eng > dominant_energy[dep_idx]
            if np.any(improved):
                dominant_energy[dep_idx[improved]] = dep_eng[improved]
                dominant_idx[dep_idx[improved]] = _stable_hole_index(seg.hole_id)
            # V6-03: feed the temporal layer per-block. No global list
            # / concatenation — the largest auxiliary per source is
            # bounded by spatial_voxel_block_size.
            if temporal_enabled and dep_idx.size > 0:
                temporal_energy_contributions.append(
                    (src.copy(), dep_idx.copy(), dep_eng.copy())
                )
                temporal_detonation_times.append(det_time)
            represented_weight_raw += float(w_s[deposit_mask].sum())

    # Conservation bookkeeping: use the raw weight sum (not a
    # back-calculation from deposit_energies) for exact float64 parity
    # across block sizes (V5-04 fix).
    represented_weight = represented_weight_raw
    outside_weight = Q_total - represented_weight
    if outside_weight < 0.0:
        outside_weight = 0.0
    represented = float(e_acoplada) * represented_weight / Q_total if Q_total > 0 else 0.0
    outside = float(e_acoplada) * outside_weight / Q_total if Q_total > 0 else float(e_acoplada)

    total_represented.append(represented)
    total_outside.append(outside)
    per_hole_energy[seg.hole_id] = per_hole_energy.get(seg.hole_id, 0.0) + represented
    # V6-03: the temporal layer is now fed per-block inside the pass-2
    # loop above. No trailing global concat — the segment tuples stay
    # bounded by ``spatial_voxel_block_size``.


# ---------------------------------------------------------------------------
# Streaming temporal computation — bounded memory (Falla 7 v4 fix, audit §7)
# ---------------------------------------------------------------------------


def _compute_temporal_fields_streaming(
    *,
    voxel_centres: np.ndarray,
    energy_total: np.ndarray,
    segment_infos: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    detonation_times: list[float],
    velocity: float,
    sigma: float,
    anisotropy_mode: str,
    tensor: Optional[np.ndarray],
    n_voxels: int,
    voxel_block_size: int = 4096,
    n_time_bins: int = 64,
    t_window_factor: float = 6.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute first_arrival and time_of_max from compact segment info.

    Processes voxels in blocks. For each block, iterates segments and
    computes distances ON-THE-FLY from the segment's source position to
    the block's voxel centres. NO full-length per-segment arrays are
    materialised.

    Peak auxiliary memory: O(voxel_block_size × n_contributing_segments)
    where n_contributing_segments is the number of segments that have
    at least one deposit voxel in the current block — typically a small
    fraction of the total.

    Parameters
    ----------
    segment_infos
        List of ``(source_position, deposit_indices, deposit_energies)``
        tuples, one per contributing segment. ``deposit_indices`` are
        flat indices into the global voxel grid; only voxels that
        received energy are included (compact representation).
    """
    from scipy.special import ndtr

    first_arrival = np.full(n_voxels, np.inf, dtype=np.float64)
    time_of_max = np.full(n_voxels, np.nan, dtype=np.float64)

    if not segment_infos or n_voxels == 0:
        return first_arrival, time_of_max

    half_window = float(t_window_factor) / 2.0 * sigma
    unit_edges = np.linspace(0.0, 1.0, n_time_bins + 1, dtype=np.float64)
    block = max(1, int(voxel_block_size))

    for start in range(0, n_voxels, block):
        stop = min(start + block, n_voxels)
        block_size = stop - start

        # Collect per-segment data for voxels in THIS block only.
        # Each entry: (local_indices, distances, energies, detonation).
        block_segments: list[tuple[np.ndarray, np.ndarray, np.ndarray, float]] = []
        for seg_idx, (src_pos, dep_idx, dep_energies) in enumerate(segment_infos):
            if dep_idx.size == 0:
                continue
            in_block = (dep_idx >= start) & (dep_idx < stop)
            if not np.any(in_block):
                continue
            local_idx = dep_idx[in_block] - start
            local_energy = dep_energies[in_block]
            # Compute distances ON-THE-FLY for these few voxels.
            local_centres = voxel_centres[start + local_idx]
            delta = local_centres - src_pos
            r = compute_distance(delta, anisotropy_mode=anisotropy_mode, tensor=tensor)
            det = float(detonation_times[seg_idx]) if seg_idx < len(detonation_times) else 0.0
            block_segments.append((local_idx, r, local_energy, det))

            # Update first_arrival at the global indices.
            global_idx = dep_idx[in_block]
            arrivals_seg = det + r / velocity
            first_arrival[global_idx] = np.minimum(
                first_arrival[global_idx], arrivals_seg,
            )

        if not block_segments:
            continue

        # Compute time_of_max for each active voxel in this block.
        all_local = np.concatenate([d[0] for d in block_segments])
        unique_local = np.unique(all_local)

        for vl in unique_local:
            arrivals_v = []
            energies_v = []
            for local_idx, r, energy, det in block_segments:
                mask = local_idx == vl
                if np.any(mask):
                    arrivals_v.append(det + r[mask][0] / velocity)
                    energies_v.append(energy[mask][0])

            if not arrivals_v:
                continue

            arrivals_arr = np.array(arrivals_v, dtype=np.float64)
            energies_arr = np.array(energies_v, dtype=np.float64)

            t_min = float(arrivals_arr.min())
            t_max = float(arrivals_arr.max())

            if np.isclose(t_min, t_max, atol=1e-14):
                time_of_max[start + vl] = t_min
                continue

            starts_w = max(0.0, t_min - half_window)
            stops_w = t_max + half_window
            edges = starts_w + (stops_w - starts_w) * unit_edges
            z = (edges[:, None] - arrivals_arr[None, :]) / sigma
            fractions = np.diff(ndtr(z), axis=0)
            # V5-03: normalise fractions per source so that Σ_t f = 1.0
            # within the finite window. Without normalisation, sources
            # whose gaussian extends beyond the window boundaries (especially
            # near t=0) lose energy — the audit measured residuals up to
            # 15.9%.
            frac_sums = fractions.sum(axis=0)
            safe_sums = np.where(frac_sums > 1e-30, frac_sums, 1.0)
            fractions = fractions / safe_sums[None, :]
            response = np.sum(energies_arr[None, :] * fractions, axis=1)
            best_bin = int(np.argmax(response))
            time_of_max[start + vl] = 0.5 * (edges[best_bin] + edges[best_bin + 1])

    return first_arrival, time_of_max


def _stable_hole_index(hole_id: str) -> int:
    """Stable non-negative int per hole_id (deterministic across runs).

    Uses the first 8 bytes of SHA-256 masked to 63 bits so the result
    always fits in a signed int64 numpy array (the dominant_idx dtype).
    The same string always maps to the same integer regardless of
    insertion order.
    """
    h = hashlib.sha256(hole_id.encode("utf-8")).digest()
    raw = int.from_bytes(h[:8], "little", signed=False)
    return raw & ((1 << 63) - 1)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_simulation(
    *,
    accepted_rows: list[dict[str, Any]],
    configuration: SimulationConfiguration,
    segments_per_hole: int = 8,
    block_size: Optional[int] = None,
    support_radius_m: Optional[float] = None,
) -> SimulationResult:
    """Run the deterministic voxel energy simulation.

    Parameters
    ----------
    accepted_rows
        The accepted rows from the Fase 1 ``ProcessingResult``. Rejected
        rows MUST NOT be passed — the engine cannot run on them.
    configuration
        A fully validated :class:`SimulationConfiguration`
        (``user_confirmed=True``). The configuration's
        ``support_radius_m`` is the authoritative kernel support; the
        engine reads it directly from the contract (Falla 5 fix).
    segments_per_hole
        Number of explosive-column sub-segments per hole (default 8).
    block_size
        Voxel block size for chunked evaluation. Defaults to
        :data:`core.config.SIMULATION.chunk_voxel_block`.
    support_radius_m
        DEPRECATED — kept for backwards compatibility. When provided
        AND ``configuration.support_radius_m`` is None, the engine
        uses this value; otherwise the contract wins. New callers
        SHOULD set ``configuration.support_radius_m`` and leave this
        argument as ``None``.

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
    in_domain_mask = intersection_mask_flat(grid)
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
    temporal_energy_contributions: Optional[list[np.ndarray]] = [] if is_temporal else None
    temporal_distances: Optional[list[np.ndarray]] = [] if is_temporal else None
    temporal_detonation_times: Optional[list[float]] = [] if is_temporal else None

    # Authoritative support radius: the contract wins over the legacy
    # parameter. The validate() call above guarantees R > r0 > 0.
    # No hidden default: the contract is authoritative (Falla 4.1 fix).
    if configuration.support_radius_m is not None:
        R_runtime = float(configuration.support_radius_m)
    elif support_radius_m is not None:
        R_runtime = float(support_radius_m)
    else:
        raise SimulationConfigurationError(
            "run_simulation requires configuration.support_radius_m to "
            "be set (Falla 4.1: no hidden default allowed).",
            error_code="SUPPORT_RADIUS_REQUIRED",
            details={"recommended_action": "set configuration.support_radius_m"},
        )

    # Compute the DISCRETE kernel mass Q_total ONCE on the SAME cartesian
    # lattice the per-source accumulation uses (the global voxel grid).
    # This is position-INDEPENDENT because the lattice offsets relative
    # to a source at a voxel centre are fixed; the engine recomputes
    # the actual per-source Q_total on the same lattice when the source
    # sits off-grid (handled inside _accumulate_source).
    anisotropy_tensor = (
        np.asarray(configuration.rock_mass.anisotropy_tensor, dtype=np.float64)
        if configuration.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR
        and configuration.rock_mass.anisotropy_tensor is not None
        else None
    )
    # The constant Q_total is no longer used directly by _accumulate_source;
    # it remains available for diagnostics (resource_info) only.
    _ = discrete_total_mass(
        attenuation_coefficient_1_m=configuration.attenuation_coefficient_1_m,
        regularization_radius_m=configuration.regularization_radius_m,
        support_radius_m=R_runtime,
        voxel_size_m=grid.voxel_size_m,
        anisotropy_mode=configuration.anisotropy_mode,
        tensor=anisotropy_tensor,
    )

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
            spatial_voxel_block_size=block,
            energy_total=energy_total,
            contributing_count=contributing_count,
            dominant_idx=dominant_idx,
            dominant_energy=dominant_energy,
            arrival_times=None,
            first_arrival=first_arrival,
            time_of_max=time_of_max,
            pulse_sigma=pulse_sigma,
            temporal_energy_contributions=temporal_energy_contributions,
            temporal_distances=temporal_distances,
            temporal_detonation_times=temporal_detonation_times,
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

    # Compute temporal fields using STREAMING per-block processing
    # (Falla 7 v4 fix, audit §7). NO full-length per-segment arrays
    # are retained; the compact segment info is used to compute
    # distances and arrivals on-the-fly for each voxel block.
    # Peak auxiliary memory: O(voxel_block_size × n_active_segments).
    if is_temporal and temporal_energy_contributions and len(temporal_energy_contributions) > 0:
        detonation_array = (
            temporal_detonation_times
            if temporal_detonation_times is not None
            else []
        )
        velocity = float(configuration.propagation_velocity_m_s)
        sigma_value = float(pulse_sigma) if pulse_sigma is not None else 1e-3
        first_arrival, time_of_max = _compute_temporal_fields_streaming(
            voxel_centres=voxel_centres,
            energy_total=energy_total,
            segment_infos=temporal_energy_contributions,
            detonation_times=detonation_array,
            velocity=velocity,
            sigma=sigma_value,
            anisotropy_mode=configuration.anisotropy_mode,
            tensor=anisotropy_tensor,
            n_voxels=n_voxels,
            voxel_block_size=block,
        )
        first_arrival[~np.isfinite(first_arrival)] = np.nan

    energy_unit = "J" if configuration.energy_mode == EnergyMode.ABSOLUTE else "dimensionless"

    # Compute per-grid temporal scalars for the canonical dataclass.
    first_arrival_scalar: Optional[float] = None
    time_of_max_scalar: Optional[float] = None
    if first_arrival is not None and np.any(np.isfinite(first_arrival)):
        first_arrival_scalar = float(np.nanmin(first_arrival))
    if time_of_max is not None and np.any(np.isfinite(time_of_max)):
        time_of_max_scalar = float(np.nanmin(time_of_max[np.isfinite(time_of_max)]))
    # Dominant hole: the hole_id whose aggregate represented energy is largest.
    dominant_hole_id_str: Optional[str] = None
    if per_hole_energy:
        dominant_hole_id_str = max(per_hole_energy.items(), key=lambda kv: kv[1])[0]

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
        first_arrival_s=first_arrival_scalar,
        time_of_max_s=time_of_max_scalar,
        dominant_hole_id=dominant_hole_id_str,
        contributor_count=active_voxels,
        units={"energy": energy_unit, "density": "J/m3" if energy_unit == "J" else "1/m3",
               "time": "s", "length": "m"},
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

    # 11. Build the canonical field_arrays dict (Falla 4 fix, audit v3 §4).
    # Persistence consumes these directly; it MUST NOT call
    # compute_field_arrays to recalculate. Every array produced here is
    # the single authority for downstream layers.
    idx_to_hole: dict[int, str] = {}
    for seg in valid:
        idx = _stable_hole_index(seg.hole_id)
        idx_to_hole.setdefault(idx, seg.hole_id)
    if n_voxels > 0:
        dominant_hole_id_arr = np.array(
            [idx_to_hole.get(int(idx), "") for idx in dominant_idx],
            dtype="U",
        )
    else:
        dominant_hole_id_arr = np.array([], dtype="U")

    import json as _json
    field_arrays: dict[str, Any] = {
        "energy_total": energy_total.astype(np.float32),
        "energy_density_j_m3": (energy_total / grid.voxel_volume_m3).astype(np.float32),
        "contributing_count": contributing_count,
        "dominant_idx": dominant_idx,
        "dominant_hole_id": dominant_hole_id_arr,
        "dominant_energy": dominant_energy.astype(np.float32),
        "voxel_centres": voxel_centres.astype(np.float32),
        "grid_shape": np.array(
            [grid.shape[0], grid.shape[1], grid.shape[2]], dtype=np.int32
        ),
        "axis_order": np.array(["x", "y", "z"], dtype="U"),
        "dtype": np.array("float32", dtype="U"),
        "units": np.array(
            _json.dumps({"energy": energy_unit, "density": "J/m3", "time": "s"}),
            dtype="U",
        ),
    }
    if is_temporal and first_arrival is not None and time_of_max is not None:
        field_arrays["first_arrival_s"] = first_arrival.astype(np.float32)
        field_arrays["time_of_max_s"] = time_of_max.astype(np.float32)

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
        field_arrays=field_arrays,
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
    support_radius_m: Optional[float] = None,
) -> dict[str, np.ndarray]:
    """Recompute the canonical field arrays for NPZ persistence.

    The engine result carries only aggregate metadata; the actual 3D
    arrays are reproduced deterministically from the same inputs so the
    NPZ artifact can be SHA-256 verified on read-back.

    Returns a dict suitable for ``np.savez_compressed``.

    V5-02: delegates to ``result.field_arrays`` when available. The
    canonical result is the single authority; recalculation is
    prohibited.
    """
    if result.field_arrays is not None:
        return dict(result.field_arrays)

    raise ValueError(
        "export_field_arrays requires result.field_arrays to be "
        "populated (call run_simulation first). Recalculation is "
        "prohibited (V5-01/V5-02)."
    )
