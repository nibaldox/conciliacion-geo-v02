"""Cálculo temporal conservativo para la simulación 3D de tronadura.

La respuesta temporal representa energía por intervalo temporal, con unidades
``[J]`` en modo de energía absoluta. No representa potencia ``[J/s]`` ni un
índice adimensional. Para una contribución espacial ``e_i`` y un pulso
gaussiano normalizado, la energía del intervalo ``k`` es

``e_i × [Φ((t[k+1]-t_arrival)/σ) - Φ((t[k]-t_arrival)/σ)]``.

La suma de todos los intervalos que cubren ``(-∞, +∞)`` es exactamente
``e_i`` salvo el error numérico de la evaluación de la CDF. Un intervalo
finito representa solamente la energía contenida en esa ventana y nunca crea
energía adicional.
"""
from __future__ import annotations

import math
import warnings
from typing import Optional, Sequence

import numpy as np
from scipy.special import ndtr

from core.blast_simulation.contracts import TemporalMode


NOT_AVAILABLE = "NOT_AVAILABLE"
AVAILABLE = "AVAILABLE"
PULSE_SIGMA_FALLBACK = "PULSE_SIGMA_FALLBACK"


def _validate_velocity(propagation_velocity_m_s: float) -> float:
    """Return a finite positive propagation velocity in ``[m/s]``."""
    velocity = float(propagation_velocity_m_s)
    if not math.isfinite(velocity) or velocity <= 0.0:
        raise ValueError("propagation_velocity_m_s must be > 0")
    return velocity


def _validate_sigma(sigma_s: float) -> float:
    """Return a finite positive pulse standard deviation in ``[s]``."""
    sigma = float(sigma_s)
    if not math.isfinite(sigma) or sigma <= 0.0:
        raise ValueError("sigma_s must be > 0")
    return sigma


def arrival_time(
    *,
    distance_m: np.ndarray,
    propagation_velocity_m_s: float,
    detonation_time_s: Optional[float],
) -> np.ndarray:
    """Calculate ``t_arrival = t_det + r / v``.

    ``r`` is a distance in ``[m]`` and ``v`` is a propagation velocity in
    ``[m/s]``; therefore ``r / v`` and the result are in ``[s]``. ``None``
    denotes a simultaneous detonation at ``t_det = 0 s``.
    """
    velocity = _validate_velocity(propagation_velocity_m_s)
    t_det = 0.0 if detonation_time_s is None else float(detonation_time_s)
    if not math.isfinite(t_det):
        raise ValueError("detonation_time_s must be finite or None")
    distances = np.asarray(distance_m, dtype=np.float64)
    return t_det + distances / velocity


def gaussian_pulse(
    t: np.ndarray,
    *,
    t_arrival: np.ndarray,
    sigma_s: float,
) -> np.ndarray:
    """Evaluate ``G(t) = exp(-0.5 ((t - t_arrival) / σ)²)``.

    ``t`` and ``t_arrival`` are in ``[s]`` and ``sigma_s`` is in ``[s]``;
    consequently the exponent is dimensionless and ``G`` is dimensionless.
    This unnormalised shape is useful for diagnostics. Energy conservation is
    provided by :func:`energy_pulse_per_interval`, not by this function.
    """
    sigma = _validate_sigma(sigma_s)
    times = np.asarray(t, dtype=np.float64)
    arrivals = np.asarray(t_arrival, dtype=np.float64)
    z = (times - arrivals) / sigma
    return np.exp(-0.5 * z * z)


def energy_pulse_per_interval(
    t_edges: np.ndarray,
    *,
    t_arrival: float | np.ndarray,
    sigma_s: float,
    energy_j: float,
) -> np.ndarray:
    """Discretise a pulse as conservative energy ``[J]`` per time interval.

    For interval ``[t_k, t_{k+1}]`` the result is

    ``energy_j × ∫G(t)dt / (sqrt(2π)σ)``
    ``= energy_j × [Φ(z_{k+1}) - Φ(z_k)]``.

    Time and ``sigma_s`` have units ``[s]``. The Gaussian integral is in
    ``[s]`` and the normalisation in ``1/[s]``, so each coefficient is
    dimensionless and the output is energy in ``[J]``. With edges spanning
    ``(-∞, +∞)``, ``sum(result) == energy_j`` within floating-point
    tolerance. Finite windows contain only their represented share and never
    add energy.
    """
    sigma = _validate_sigma(sigma_s)
    energy = float(energy_j)
    if not math.isfinite(energy) or energy < 0.0:
        raise ValueError("energy_j must be finite and >= 0")
    edges = np.asarray(t_edges, dtype=np.float64)
    if edges.ndim != 1 or edges.size < 2:
        raise ValueError("t_edges must be a one-dimensional array with >= 2 edges")
    if np.any(np.isnan(edges)) or np.any(np.diff(edges) <= 0.0):
        raise ValueError("t_edges must be strictly increasing and must not contain NaN")
    arrivals = np.asarray(t_arrival, dtype=np.float64)
    if np.any(~np.isfinite(arrivals)):
        raise ValueError("t_arrival must be finite")
    z = (edges[:, None] - arrivals.reshape(1, -1)) / sigma
    probabilities = np.diff(ndtr(z), axis=0)
    result = energy * probabilities
    if arrivals.ndim == 0:
        return result[:, 0]
    return result


def _segment_mask(
    distances: np.ndarray,
    segment_mask: Optional[np.ndarray],
) -> np.ndarray:
    """Convert supported segment-selection forms to a boolean matrix."""
    finite = np.isfinite(distances)
    if segment_mask is None:
        return finite
    mask = np.asarray(segment_mask)
    if mask.dtype == bool:
        if mask.shape != distances.shape:
            raise ValueError("boolean segment_mask must match distances_per_voxel")
        return finite & mask
    if distances.ndim == 1 and mask.ndim == 1 and mask.shape == distances.shape:
        if np.issubdtype(mask.dtype, np.integer):
            selected = np.zeros((distances.size, 1), dtype=bool)
            valid = (mask >= 0) & (mask < 1)
            selected[valid, 0] = True
            return finite[:, None] & selected
        selected = np.asarray([value is not None for value in mask], dtype=bool)
        return finite[:, None] & selected[:, None]
    if mask.ndim == 1 and distances.ndim == 2 and mask.size == distances.shape[0]:
        selected = np.zeros(distances.shape, dtype=bool)
        valid = (
            np.issubdtype(mask.dtype, np.integer)
            & (mask >= 0)
            & (mask < distances.shape[1])
        )
        rows = np.flatnonzero(valid)
        selected[rows, mask[rows].astype(np.int64)] = True
        return finite & selected
    raise ValueError("segment_mask must be a boolean matrix or per-voxel segment indices")


def compute_first_arrival(
    *,
    distances_per_voxel: np.ndarray,
    propagation_velocity_m_s: float,
    detonation_times_per_segment: Sequence[Optional[float]],
    segment_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Find the earliest arrival and its contributing segment for each voxel.

    ``distances_per_voxel`` is ``(n_voxels, n_segments)`` in the general
    case, or ``(n_voxels,)`` for one segment. ``segment_mask`` may be a
    boolean matrix of the same shape or one selected segment index per voxel;
    ``None``/``-1`` means no contribution. Detonation times are ``[s]`` and
    distances are ``[m]``, so ``t_det + distance / velocity`` is ``[s]``.

    A voxel without a selected finite distance returns ``np.inf`` and index
    ``-1``. The caller may convert the former to ``NaN`` for serialized maps.
    """
    velocity = _validate_velocity(propagation_velocity_m_s)
    distances = np.asarray(distances_per_voxel, dtype=np.float64)
    if distances.ndim not in (1, 2):
        raise ValueError("distances_per_voxel must have one or two dimensions")
    one_segment = distances.ndim == 1
    matrix = distances[:, None] if one_segment else distances
    detonation = np.asarray(
        [0.0 if value is None else float(value) for value in detonation_times_per_segment],
        dtype=np.float64,
    )
    if detonation.ndim != 1 or detonation.size != matrix.shape[1]:
        raise ValueError("detonation_times_per_segment must match the segment axis")
    if np.any(~np.isfinite(detonation)):
        raise ValueError("detonation_times_per_segment must contain finite values or None")
    selected = _segment_mask(distances, segment_mask)
    arrivals = matrix / velocity + detonation[None, :]
    valid = selected & np.isfinite(arrivals)
    masked_arrivals = np.where(valid, arrivals, np.inf)
    indices = np.argmin(masked_arrivals, axis=1).astype(np.int64)
    first = masked_arrivals[np.arange(matrix.shape[0]), indices]
    indices[first == np.inf] = -1
    return first.astype(np.float64), indices


def compute_time_of_max(
    *,
    energy_total_per_voxel: np.ndarray,
    first_arrival_per_voxel: np.ndarray,
    distances_per_voxel: np.ndarray,
    propagation_velocity_m_s: float,
    sigma_s: float,
    n_time_bins: int = 64,
    t_window_factor: float = 6.0,
    energy_per_segment_per_voxel: Optional[np.ndarray] = None,
    detonation_times_per_segment: Optional[Sequence[Optional[float]]] = None,
    segment_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Return the time of the maximum aggregated interval energy per voxel.

    The physical response is the superposition

    ``A_i[k] = Σ_s e_{i,s} × [Φ(z_{k+1,s}) - Φ(z_{k,s})]``

    where ``e_{i,s}`` is the spatially deposited energy in ``[J]`` and the
    bracket is the fraction of that energy in interval ``k``. Thus ``A_i[k]``
    is energy per interval ``[J]``, never power ``[J/s]`` or an index. The
    temporal integral cannot create energy: over all real-time intervals its
    sum is ``Σ_s e_{i,s}``; over the finite search window it is less than or
    equal to that quantity up to floating-point error.

    The public compact form accepts one distance per voxel. For the full
    superposition form, ``distances_per_voxel`` is ``(n_voxels, n_segments)``
    and ``energy_per_segment_per_voxel`` supplies ``e_{i,s}``. For backwards
    compatibility, a two-dimensional ``energy_total_per_voxel`` is also
    interpreted as the per-segment energy matrix. If only a one-dimensional
    total is supplied for multiple distances, it is distributed equally over
    the selected segments; callers that have source contributions should use
    the explicit matrix.

    Computation is blocked over voxels. Each block uses NumPy broadcasting
    over ``(n_block, n_time_bins, n_segments)`` and never materialises the
    prohibited ``(n_voxels, n_time_bins)`` temporal field. No Python loop runs
    over individual voxels.
    """
    velocity = _validate_velocity(propagation_velocity_m_s)
    sigma = _validate_sigma(sigma_s)
    if isinstance(n_time_bins, bool) or int(n_time_bins) != n_time_bins or n_time_bins < 2:
        raise ValueError("n_time_bins must be an integer >= 2")
    bins = int(n_time_bins)
    factor = float(t_window_factor)
    if not math.isfinite(factor) or factor <= 0.0:
        raise ValueError("t_window_factor must be > 0")

    distances = np.asarray(distances_per_voxel, dtype=np.float64)
    if distances.ndim not in (1, 2):
        raise ValueError("distances_per_voxel must have one or two dimensions")
    matrix = distances[:, None] if distances.ndim == 1 else distances
    n_voxels, n_segments = matrix.shape

    first = np.asarray(first_arrival_per_voxel, dtype=np.float64)
    total = np.asarray(energy_total_per_voxel, dtype=np.float64)
    if first.shape != (n_voxels,):
        raise ValueError("first_arrival_per_voxel must have shape (n_voxels,)")
    if total.shape not in ((n_voxels,), (n_voxels, n_segments)):
        raise ValueError("energy_total_per_voxel has an incompatible shape")

    selected = _segment_mask(matrix, segment_mask)
    finite_distances = np.isfinite(matrix)
    selected &= finite_distances

    if energy_per_segment_per_voxel is not None:
        contributions = np.asarray(energy_per_segment_per_voxel, dtype=np.float64)
        if contributions.shape != matrix.shape:
            raise ValueError("energy_per_segment_per_voxel must match distances_per_voxel")
    elif total.ndim == 2:
        contributions = total
    elif n_segments == 1:
        contributions = total[:, None]
    else:
        selected_count = selected.sum(axis=1)
        contributions = np.divide(
            total[:, None],
            selected_count[:, None],
            out=np.zeros((n_voxels, n_segments), dtype=np.float64),
            where=selected_count[:, None] > 0,
        )
    contributions = np.where(selected & np.isfinite(contributions) & (contributions > 0.0), contributions, 0.0)

    if detonation_times_per_segment is None:
        minimum_distance = np.min(np.where(selected, matrix, np.inf), axis=1)
        safe_first = np.where(np.isfinite(first), first, 0.0)
        arrivals = safe_first[:, None] + (matrix - minimum_distance[:, None]) / velocity
    else:
        detonation = np.asarray(
            [0.0 if value is None else float(value) for value in detonation_times_per_segment],
            dtype=np.float64,
        )
        if detonation.shape != (n_segments,) or np.any(~np.isfinite(detonation)):
            raise ValueError("detonation_times_per_segment must match the segment axis")
        arrivals = matrix / velocity + detonation[None, :]
    valid = (contributions > 0.0) & np.isfinite(arrivals)
    arrivals = np.where(valid, arrivals, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        computed_first = np.nanmin(np.where(valid, arrivals, np.nan), axis=1)
        computed_first = np.where(np.any(valid, axis=1), computed_first, np.nan)
    first = np.where(np.isfinite(first), first, computed_first)
    result = np.full(n_voxels, np.nan, dtype=np.float64)

    same_arrival = np.zeros(n_voxels, dtype=bool)
    valid_count = valid.sum(axis=1)
    if n_segments:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            arrival_min = np.nanmin(np.where(valid, arrivals, np.nan), axis=1)
            arrival_max = np.nanmax(np.where(valid, arrivals, np.nan), axis=1)
        same_arrival = (valid_count > 0) & np.isclose(arrival_min, arrival_max, rtol=0.0, atol=1.0e-14)
        result[same_arrival] = arrival_min[same_arrival]

    half_window = factor / 2.0 * sigma
    block_size = max(1, min(4096, n_voxels))
    unit_edges = np.linspace(0.0, 1.0, bins + 1, dtype=np.float64)
    for start in range(0, n_voxels, block_size):
        stop = min(start + block_size, n_voxels)
        active = valid[start:stop].any(axis=1) & ~same_arrival[start:stop]
        if not np.any(active):
            continue
        block_arrivals = arrivals[start:stop]
        block_contributions = contributions[start:stop]
        block_first = first[start:stop]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            block_max = np.nan_to_num(
                np.nanmax(np.where(valid[start:stop], block_arrivals, np.nan), axis=1),
                nan=0.0,
            )
        block_first_safe = np.where(np.isfinite(block_first), block_first, 0.0)
        starts = block_first_safe - half_window
        # Time cannot be negative — detonation is the origin of the
        # temporal axis. Clamp the search window to ``[0, +inf)`` so
        # ``time_of_max`` is always a non-negative scalar.
        starts = np.clip(starts, 0.0, None)
        stops = block_max + half_window
        edges = starts[:, None] + (stops - starts)[:, None] * unit_edges[None, :]
        z = (edges[:, :, None] - block_arrivals[:, None, :]) / sigma
        fractions = np.diff(ndtr(z), axis=1)
        # V5-03: normalise per source so Σ_t f = 1 within the window.
        frac_sums = fractions.sum(axis=1, keepdims=True)
        frac_sums = np.where(frac_sums > 1e-30, frac_sums, 1.0)
        fractions = fractions / frac_sums
        response = np.sum(block_contributions[:, None, :] * fractions, axis=2)
        centres = 0.5 * (edges[:, 1:] + edges[:, :-1])
        local_indices = np.argmax(response, axis=1)
        block_result = centres[np.arange(stop - start), local_indices]
        result[start:stop] = np.where(active, block_result, result[start:stop])
    return result


# ---------------------------------------------------------------------------
# Chunked variants — process per-segment lists without materialising a
# dense (n_voxels × n_segments) matrix (Falla 7 fix, audit v2 §6.2).
# ---------------------------------------------------------------------------


def compute_first_arrival_chunked(
    *,
    distances_per_segment: Sequence[np.ndarray],
    energy_per_segment: Sequence[np.ndarray],
    propagation_velocity_m_s: float,
    detonation_times_per_segment: Sequence[Optional[float]],
    n_voxels: int,
) -> np.ndarray:
    """First-arrival per voxel computed from per-segment arrays.

    Inputs are LISTS of 1D arrays, one entry per contributing segment.
    Each entry has shape ``(n_voxels,)``. The function maintains a
    single ``first_arrival`` accumulator of size ``n_voxels`` and folds
    segments one at a time — peak memory ``O(n_voxels)`` instead of
    ``O(n_voxels × n_segments)``.

    Voxels with no contributing segment stay at ``np.inf``. Callers
    convert to NaN downstream if desired.
    """
    velocity = _validate_velocity(propagation_velocity_m_s)
    if not distances_per_segment:
        return np.full(n_voxels, np.inf, dtype=np.float64)
    detonation = np.asarray(
        [0.0 if value is None else float(value) for value in detonation_times_per_segment],
        dtype=np.float64,
    )
    if detonation.shape != (len(distances_per_segment),):
        raise ValueError(
            "detonation_times_per_segment must match the number of segments"
        )
    if np.any(~np.isfinite(detonation)):
        raise ValueError("detonation_times_per_segment must be finite or None")

    first = np.full(n_voxels, np.inf, dtype=np.float64)
    for s, dist_s in enumerate(distances_per_segment):
        d = np.asarray(dist_s, dtype=np.float64)
        e = (
            np.asarray(energy_per_segment[s], dtype=np.float64)
            if s < len(energy_per_segment)
            else np.ones_like(d)
        )
        contributing = (e > 0.0) & np.isfinite(d)
        arrival_s = np.where(
            contributing,
            detonation[s] + d / velocity,
            np.inf,
        )
        first = np.minimum(first, arrival_s)
    return first


def compute_time_of_max_chunked(
    *,
    energy_total_per_voxel: np.ndarray,
    first_arrival_per_voxel: np.ndarray,
    distances_per_segment: Sequence[np.ndarray],
    energy_per_segment: Sequence[np.ndarray],
    propagation_velocity_m_s: float,
    sigma_s: float,
    detonation_times_per_segment: Sequence[Optional[float]],
    voxel_block_size: int = 4096,
    n_time_bins: int = 64,
    t_window_factor: float = 6.0,
) -> np.ndarray:
    """time_of_max computed without dense (n_voxels × n_segments) matrix.

    For each voxel block, stacks the per-segment contributions ONLY for
    that block, computes the temporal response via CDF differences, and
    writes the argmax bin centre back into the global ``result`` array.

    Peak memory: ``O(voxel_block_size × n_segments)`` plus
    ``O(voxel_block_size × n_time_bins)`` — bounded by the configured
    ``voxel_block_size`` regardless of the global voxel count.
    """
    velocity = _validate_velocity(propagation_velocity_m_s)
    sigma = _validate_sigma(sigma_s)
    n_segments = len(distances_per_segment)
    n_voxels = int(energy_total_per_voxel.size)
    if n_segments == 0:
        return np.full(n_voxels, np.nan, dtype=np.float64)

    detonation = np.asarray(
        [0.0 if v is None else float(v) for v in detonation_times_per_segment],
        dtype=np.float64,
    )
    if detonation.shape != (n_segments,):
        raise ValueError("detonation_times_per_segment must match segments")

    block = max(1, int(voxel_block_size))
    half_window = float(t_window_factor) / 2.0 * sigma
    unit_edges = np.linspace(0.0, 1.0, int(n_time_bins) + 1, dtype=np.float64)

    result = np.full(n_voxels, np.nan, dtype=np.float64)

    for start in range(0, n_voxels, block):
        stop = min(start + block, n_voxels)
        # Stack per-segment contributions ONLY for this voxel block.
        # Bounded memory: (block_size × n_segments) instead of
        # (n_voxels × n_segments).
        block_dist = np.empty((stop - start, n_segments), dtype=np.float64)
        block_energy = np.empty((stop - start, n_segments), dtype=np.float64)
        for s in range(n_segments):
            block_dist[:, s] = np.asarray(
                distances_per_segment[s][start:stop], dtype=np.float64,
            )
            block_energy[:, s] = np.asarray(
                energy_per_segment[s][start:stop], dtype=np.float64,
            )

        arrivals_block = block_dist / velocity + detonation[None, :]
        valid = (block_energy > 0.0) & np.isfinite(arrivals_block)
        arrivals_block = np.where(valid, arrivals_block, np.nan)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            arrival_min = np.nanmin(np.where(valid, arrivals_block, np.nan), axis=1)
            arrival_max = np.nanmax(np.where(valid, arrivals_block, np.nan), axis=1)
            any_valid = np.any(valid, axis=1)
            arrival_min = np.where(any_valid, arrival_min, 0.0)
            arrival_max = np.where(any_valid, arrival_max, 0.0)

        same_arrival = any_valid & np.isclose(
            arrival_min, arrival_max, rtol=0.0, atol=1.0e-14,
        )
        # When all arrivals coincide the peak time IS that arrival.
        result[start:stop] = np.where(same_arrival, arrival_min, result[start:stop])

        active = any_valid & ~same_arrival
        if not np.any(active):
            continue

        starts_w = np.clip(arrival_min - half_window, 0.0, None)
        stops_w = arrival_max + half_window
        edges = starts_w[:, None] + (stops_w - starts_w)[:, None] * unit_edges[None, :]
        # edges shape: (block_size, n_time_bins+1)
        # arrivals_block shape: (block_size, n_segments)
        z = (edges[:, :, None] - arrivals_block[:, None, :]) / sigma
        fractions = np.diff(ndtr(z), axis=1)
        # V5-03: normalise per source so Σ_t f = 1 within the window.
        frac_sums = fractions.sum(axis=1, keepdims=True)
        frac_sums = np.where(frac_sums > 1e-30, frac_sums, 1.0)
        fractions = fractions / frac_sums
        # response shape: (block_size, n_time_bins)
        response = np.sum(block_energy[:, None, :] * fractions, axis=2)
        centres = 0.5 * (edges[:, 1:] + edges[:, :-1])
        local_indices = np.argmax(response, axis=1)
        block_result = centres[np.arange(stop - start), local_indices]
        result[start:stop] = np.where(active, block_result, result[start:stop])

    return result


def resolve_temporal_status(
    *,
    temporal_mode: str,
    propagation_velocity_m_s: Optional[float],
    detonation_times: Sequence[Optional[float]],
    pulse_sigma_s: Optional[float],
    fallback_sigma_s: float,
) -> str:
    """Resolve the temporal availability status without inventing physics."""
    if temporal_mode == TemporalMode.STATIC:
        return NOT_AVAILABLE
    if propagation_velocity_m_s is None:
        return NOT_AVAILABLE
    has_real_delay = any(
        value is not None and math.isfinite(float(value))
        for value in detonation_times
    )
    if not has_real_delay:
        return NOT_AVAILABLE
    if pulse_sigma_s is None:
        return PULSE_SIGMA_FALLBACK
    return AVAILABLE
