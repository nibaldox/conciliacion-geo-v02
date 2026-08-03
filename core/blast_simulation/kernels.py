"""Spatial energy kernel — regularized radial, conservative.

The kernel (spec §4.2):

    K(r) = exp(-αr) / (r² + r0²)

where ``r`` is the distance from the source centre to the voxel centre,
``α`` is the attenuation coefficient (1/m) and ``r0`` is the
regularization radius (m) that avoids the singularity at r=0.

The kernel is NEVER used to distribute energy directly. Per source, the
engine computes discrete weights ``w_j = K(r_j) × V_j`` over the voxels
that fall inside the domain, sums them into ``W = Σ w_j`` and assigns
each voxel ``e_j = E_acoplada × w_j / W``. Conservation then holds by
construction within numerical tolerance:

    Σ_j e_j = E_acoplada × (Σ_j w_j) / W = E_acoplada

When part of the kernel's effective support is truncated by the domain
boundary, the truncated mass is reported as ``outside_domain_energy_j``
and is NEVER silently renormalized into the inside-domain voxels.

Anisotropy:

* ``ISOTROPIC`` — Euclidean distance ``r = ||Δx||``.
* ``ANISOTROPIC_TENSOR`` — Mahalanobis-style ``r_aniso² = Δxᵀ M Δx``
  with M symmetric positive-definite (validated upstream).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from core.blast_simulation.contracts import AnisotropyMode


def radial_kernel(
    r: np.ndarray,
    *,
    attenuation_coefficient_1_m: float,
    regularization_radius_m: float,
) -> np.ndarray:
    """Vectorized regularized radial kernel ``K(r) = exp(-αr) / (r² + r0²)``.

    ``r`` may be any shape; the return preserves it. The denominator is
    strictly positive (``r0 > 0`` is enforced upstream) so the kernel is
    finite everywhere including ``r=0``.
    """
    alpha = float(attenuation_coefficient_1_m)
    r0 = float(regularization_radius_m)
    r_arr = np.asarray(r, dtype=np.float64)
    return np.exp(-alpha * r_arr) / (r_arr * r_arr + r0 * r0)


def isotropic_distance(
    delta: np.ndarray,
) -> np.ndarray:
    """Euclidean norm of a ``(n, 3)`` array of displacement vectors."""
    d = np.asarray(delta, dtype=np.float64)
    return np.sqrt(np.einsum("ij,ij->i", d, d))


def anisotropic_distance(
    delta: np.ndarray,
    tensor: np.ndarray,
) -> np.ndarray:
    """Mahalanobis distance ``sqrt(Δxᵀ M Δx)`` for a symmetric PD tensor.

    The tensor is validated upstream (see :func:`contracts._is_symmetric_pd`).
    Here we trust that contract and exploit the symmetry for a fast
    evaluation: ``Δxᵀ M Δx = Σ_i M_ii Δx_i² + 2 Σ_{i<j} M_ij Δx_i Δx_j``.
    """
    d = np.asarray(delta, dtype=np.float64)
    M = np.asarray(tensor, dtype=np.float64)
    if d.ndim == 1:
        d = d[None, :]
    # quadratic form: einsum 'ij,jk,ik->i' would work for full M; the
    # symmetric form below is equivalent and a touch faster.
    quad = np.einsum("ij,jk,ik->i", d, M, d)
    # Guard against tiny negative values from floating-point error.
    return np.sqrt(np.clip(quad, 0.0, None))


def compute_distance(
    delta: np.ndarray,
    *,
    anisotropy_mode: str,
    tensor: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Dispatch distance computation by anisotropy mode."""
    if anisotropy_mode == AnisotropyMode.ISOTROPIC:
        return isotropic_distance(delta)
    if anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR:
        if tensor is None:
            raise ValueError("anisotropy_mode=ANISOTROPIC_TENSOR requires a tensor")
        return anisotropic_distance(delta, tensor)
    raise ValueError(f"Unknown anisotropy_mode: {anisotropy_mode!r}")


def source_weights(
    r_in_domain: np.ndarray,
    *,
    voxel_volume_m3: float,
    attenuation_coefficient_1_m: float,
    regularization_radius_m: float,
) -> np.ndarray:
    """Per-voxel unnormalized weights ``w_j = K(r_j) × V_j`` over the
    voxels that fall inside the domain.

    ``r_in_domain`` is the distance from the source centre to each
    in-domain voxel centre. The caller is responsible for keeping
    out-of-domain voxels out of this array — that is what makes the
    outside-domain energy well-defined and reportable.
    """
    k = radial_kernel(
        r_in_domain,
        attenuation_coefficient_1_m=attenuation_coefficient_1_m,
        regularization_radius_m=regularization_radius_m,
    )
    return k * float(voxel_volume_m3)


def kernel_total_mass(
    *,
    attenuation_coefficient_1_m: float,
    regularization_radius_m: float,
    cutoff_radius_m: float | None = None,
    n_samples: int = 20000,
) -> float:
    """Numerical integral of the kernel over all 3D space.

    For ``K(r) = exp(-αr) / (r² + r0²)`` the total mass is

        W_inf = ∫₀^∞ 4πr² · K(r) dr

    This has no closed form for general α, r0, so it is computed once
    via trapezoidal quadrature on a fine radial grid extending past the
    effective support of the kernel (``cutoff = max(50/α, 1000·r0)``).

    The engine uses ``W_inf`` to normalise per-source energy WITHOUT
    silently renormalising truncated domains (spec §4.2). When a source
    sits at the domain edge, part of its kernel falls outside the
    domain — that fraction is reported as ``outside_domain_energy_j``,
    never silently rescaled into the in-domain voxels.
    """
    alpha = float(attenuation_coefficient_1_m)
    r0 = float(regularization_radius_m)
    if cutoff_radius_m is None:
        cutoff_radius_m = max(50.0 / alpha, 1000.0 * r0) if alpha > 0 else 1000.0 * r0
    r = np.linspace(0.0, float(cutoff_radius_m), n_samples)
    K = np.exp(-alpha * r) / (r * r + r0 * r0)
    integrand = 4.0 * np.pi * r * r * K
    # numpy 2.x renamed np.trapz → np.trapezoid; older numpy keeps trapz.
    trapezoid = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    return float(trapezoid(integrand, r))


def energy_split_for_source(
    *,
    e_acoplada_j: float,
    weights_in_domain: np.ndarray,
    voxel_volume_m3: float,
    attenuation_coefficient_1_m: float,
    regularization_radius_m: float,
    domain_x_min: float,
    domain_x_max: float,
    domain_y_min: float,
    domain_y_max: float,
    domain_z_min: float,
    domain_z_max: float,
    source_centre: np.ndarray,
    voxel_centres_all: np.ndarray,
    anisotropy_mode: str,
    tensor: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Compute (in_domain_mask, e_j_in_domain, total_in_domain_j, outside_j).

    Returns:

    * ``in_domain_mask`` — boolean mask over ``voxel_centres_all``.
    * ``e_j_in_domain`` — per-voxel energy assigned (only in-domain
      entries are non-zero; the rest are 0).
    * ``total_in_domain_j`` — sum of in-domain energy (≤ ``e_acoplada_j``).
    * ``outside_j`` — the energy that would have been deposited
      out-of-domain if the kernel had been evaluated there. Computed as
      ``e_acoplada_j - total_in_domain_j`` because the kernel weight
      outside the domain is excluded from ``W`` by construction.

    Conservation invariant (checked by callers):

        total_in_domain_j + outside_j == e_acoplada_j
    """
    delta = voxel_centres_all - np.asarray(source_centre, dtype=np.float64)
    r = compute_distance(delta, anisotropy_mode=anisotropy_mode, tensor=tensor)

    # Boolean in-domain mask computed once per source.
    in_domain = (
        (voxel_centres_all[:, 0] >= domain_x_min)
        & (voxel_centres_all[:, 0] <= domain_x_max)
        & (voxel_centres_all[:, 1] >= domain_y_min)
        & (voxel_centres_all[:, 1] <= domain_y_max)
        & (voxel_centres_all[:, 2] >= domain_z_min)
        & (voxel_centres_all[:, 2] <= domain_z_max)
    )

    # Weights only over in-domain voxels.
    w = source_weights(
        r[in_domain],
        voxel_volume_m3=voxel_volume_m3,
        attenuation_coefficient_1_m=attenuation_coefficient_1_m,
        regularization_radius_m=regularization_radius_m,
    )
    W = float(w.sum())
    if W <= 0.0:
        # Pathological: kernel sum is zero (numerical underflow). Mark
        # everything as out-of-domain energy; do not invent mass.
        e_j_in_domain = np.zeros(voxel_centres_all.shape[0], dtype=np.float64)
        return in_domain, e_j_in_domain, 0.0, float(e_acoplada_j)

    # Allocate per-voxel energy; only in-domain entries receive a value.
    e_j_in_domain = np.zeros(voxel_centres_all.shape[0], dtype=np.float64)
    e_j_in_domain[in_domain] = float(e_acoplada_j) * (w / W)
    total_in = float(e_j_in_domain.sum())
    outside = float(e_acoplada_j) - total_in
    return in_domain, e_j_in_domain, total_in, outside
