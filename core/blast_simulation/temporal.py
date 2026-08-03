"""Temporal layer — detonation delays, arrival times, normalized pulse.

The temporal dimension modulates WHEN the energy reaches each voxel; it
never creates additional energy. The discretization of the temporal
pulse is a partition of unity (the Gaussian pulse integrates to
``sqrt(2π) × sigma`` over the time axis), so summing it across time
bins reconstructs the same energy already distributed in space by the
kernel.

Arrival time (spec §4.4):

    t_llegada = t_detonacion + distancia / velocidad_propagacion

The propagation velocity MUST be supplied with provenance by the
caller; it is never invented here.

Normalized pulse (spec §4.4):

    G(t) = exp(-0.5 × ((t - t_llegada) / σt)²)

``σt`` defaults to :data:`core.config.SIMULATION.fallback_temporal_sigma_s`
when the caller did not supply one; the engine then tags
``temporal_status=PULSE_SIGMA_FALLBACK`` so the result is explicit
about which sigma was used.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from core.blast_simulation.contracts import TemporalMode


NOT_AVAILABLE = "NOT_AVAILABLE"
AVAILABLE = "AVAILABLE"
PULSE_SIGMA_FALLBACK = "PULSE_SIGMA_FALLBACK"


def arrival_time(
    *,
    distance_m: np.ndarray,
    propagation_velocity_m_s: float,
    detonation_time_s: Optional[float],
) -> np.ndarray:
    """Per-voxel arrival time ``t_det + r/v``.

    ``detonation_time_s`` defaults to 0.0 when ``None`` (simultaneous
    detonation); the caller is responsible for declaring whether the
    simultaneity was assumed or measured via the configuration contract.
    """
    if propagation_velocity_m_s <= 0.0:
        raise ValueError("propagation_velocity_m_s must be > 0")
    t_det = 0.0 if detonation_time_s is None else float(detonation_time_s)
    r = np.asarray(distance_m, dtype=np.float64)
    return t_det + r / float(propagation_velocity_m_s)


def gaussian_pulse(
    t: np.ndarray,
    *,
    t_arrival: np.ndarray,
    sigma_s: float,
) -> np.ndarray:
    """Normalized Gaussian pulse ``G(t) = exp(-0.5 ((t-t_arrival)/σ)²)``.

    ``t`` and ``t_arrival`` broadcast against each other. The pulse is
    NOT normalized to integrate to 1 over ``t`` — the caller composes it
    with the spatial energy field which is already energy-conservative.
    """
    if sigma_s <= 0.0:
        raise ValueError("sigma_s must be > 0")
    tt = np.asarray(t, dtype=np.float64)
    ta = np.asarray(t_arrival, dtype=np.float64)
    z = (tt - ta) / float(sigma_s)
    return np.exp(-0.5 * z * z)


def resolve_temporal_status(
    *,
    temporal_mode: str,
    propagation_velocity_m_s: Optional[float],
    detonation_times: list[Optional[float]],
    pulse_sigma_s: Optional[float],
    fallback_sigma_s: float,
) -> str:
    """Decide the ``temporal_status`` flag for the simulation result.

    * ``NOT_AVAILABLE`` — static mode OR no source carries a delay.
    * ``PULSE_SIGMA_FALLBACK`` — temporal mode but ``pulse_sigma_s``
      was not supplied; the engine used the fallback sigma.
    * ``AVAILABLE`` — temporal mode with at least one real delay and an
      explicit sigma.
    """
    if temporal_mode == TemporalMode.STATIC:
        return NOT_AVAILABLE
    if propagation_velocity_m_s is None:
        return NOT_AVAILABLE
    has_real_delay = any(t is not None and math.isfinite(float(t)) for t in detonation_times)
    if not has_real_delay:
        return NOT_AVAILABLE
    if pulse_sigma_s is None:
        return PULSE_SIGMA_FALLBACK
    return AVAILABLE
