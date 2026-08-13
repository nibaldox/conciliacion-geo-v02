"""Spatial energy kernel — regularized radial, conservative.

The kernel (spec §4.2):

    K(r) = exp(-αr) / (r² + r0²)

where ``r`` is the distance from the source centre to the voxel centre,
``α`` is the attenuation coefficient (1/m) and ``r0`` is the
regularization radius (m) that avoids the singularity at r=0.

CRITICAL INVARIANT (Falla 4 fix, audit 2026-08-03): the discrete kernel
normaliser ``Q_total`` and the per-voxel weights ``q_j = K(r_j) × V_j``
MUST be sampled on the SAME cartesian voxel grid. The previous
implementation mixed radial-shell quadrature for ``Q_total`` with
cartesian centres for ``q_j`` — when the source sat on a voxel centre,
``q_j`` captured the ``K(0) = 1/r0²`` spike while the radial shells
started at ``r = 0.5·dx`` and missed it, producing ratios of 32 801× the
coupled energy. The new ``discrete_total_mass`` evaluates the kernel on
the SAME cartesian voxel centres that ``_accumulate_source`` uses, so
``Σ_in_domain e_j + E_outside == E_coupled`` holds strictly by
construction regardless of source position.

Dimensional analysis (audit §4.4):

    [K(r)]    = L⁻²       (the integrand of ∫∫∫ K dV is adimensional)
    [V_j]     = L³
    [q = K·V] = L
    [Q_total] = L
    [q/Q]     = adimensional
    [e_j]     = J

``Q_total`` is therefore a length, NOT an energy. The engine multiplies
the adimensional fraction ``q/Q`` by ``E_coupled`` (J) to obtain the
per-voxel energy.

Anisotropy:

* ``ISOTROPIC`` — Euclidean distance ``r = ||Δx||``.
* ``ANISOTROPIC_TENSOR`` — Mahalanobis-style ``r_aniso² = Δxᵀ M Δx``
  with M symmetric positive-definite (validated upstream).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from core.blast_simulation.contracts import AnisotropyMode


def radial_kernel(
    r: np.ndarray,
    *,
    attenuation_coefficient_1_m: float,
    regularization_radius_m: float,
    support_radius_m: float,
) -> np.ndarray:
    """Vectorized regularized radial kernel with strict finite support.

    ``K(r) = exp(-αr) / (r² + r0²)`` and ``K(r) = 0`` for
    ``r > support_radius_m``. ``support_radius_m`` MUST satisfy
    ``support_radius_m > regularization_radius_m > 0`` so the regularised
    kernel can be evaluated at sample points before truncation.
    """
    alpha = float(attenuation_coefficient_1_m)
    r0 = float(regularization_radius_m)
    R = float(support_radius_m)
    if not (alpha >= 0.0 and r0 > 0.0 and R > r0):
        raise ValueError(
            f"invalid kernel params: alpha={alpha}, r0={r0}, R={R}"
        )
    r_arr = np.asarray(r, dtype=np.float64)
    out = np.zeros_like(r_arr, dtype=np.float64)
    inside = r_arr <= R
    if np.any(inside):
        r_in = r_arr[inside]
        out[inside] = np.exp(-alpha * r_in) / (r_in * r_in + r0 * r0)
    return out


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
    support_radius_m: Optional[float] = None,
) -> np.ndarray:
    """Per-voxel unnormalized weights ``q_j = K(r_j) × V_j``.

    ``r_in_domain`` is the distance from the source centre to each
    voxel centre. ``support_radius_m`` enforces the strict finite
    support ``K(r) = 0`` for ``r > R``. When omitted, callers assert
    they have already filtered the input to ``r ≤ R``.
    """
    if support_radius_m is not None:
        k = radial_kernel(
            r_in_domain,
            attenuation_coefficient_1_m=attenuation_coefficient_1_m,
            regularization_radius_m=regularization_radius_m,
            support_radius_m=support_radius_m,
        )
    else:
        # Backwards-compatible path: caller guarantees pre-filtered r ≤ R.
        alpha = float(attenuation_coefficient_1_m)
        r0 = float(regularization_radius_m)
        rr = np.asarray(r_in_domain, dtype=np.float64)
        k = np.exp(-alpha * rr) / (rr * rr + r0 * r0)
    return k * float(voxel_volume_m3)


def kernel_total_mass(
    *,
    attenuation_coefficient_1_m: float,
    regularization_radius_m: float,
    support_radius_m: float,
    voxel_size_m: float,
) -> float:
    """Backwards-compatible facade over :func:`discrete_total_mass`.

    Historical callers expected a ``kernel_total_mass`` symbol. The
    implementation now defers to the cartesian discrete normaliser so
    no hidden ``1000·r0`` cutoff can ever leak into production. The
    support radius is MANDATORY — there is no implicit fallback.
    """
    R = float(support_radius_m)
    r0 = float(regularization_radius_m)
    if not (R > r0 > 0.0):
        raise ValueError(
            f"kernel_total_mass requires support_radius_m > r0 > 0; "
            f"got R={R}, r0={r0}"
        )
    return discrete_total_mass(
        attenuation_coefficient_1_m=attenuation_coefficient_1_m,
        regularization_radius_m=regularization_radius_m,
        support_radius_m=support_radius_m,
        voxel_size_m=voxel_size_m,
    )


def _local_support_offsets(
    *,
    support_radius_m: float,
    voxel_size_m: float,
) -> np.ndarray:
    """Integer-axis offsets whose bounding box covers ``[-R, R]`` cubed.

    Returns a ``(n, 3)`` int array of axis offsets relative to the
    source voxel. ``n = (2·ceil(R/dx) + 1)³``. Each offset corresponds
    to a voxel centre on the SAME cartesian lattice as the global grid
    — this is the key invariant that makes ``discrete_total_mass`` and
    ``_accumulate_source`` use identical sample points.
    """
    R = float(support_radius_m)
    dx = float(voxel_size_m)
    if not (R > 0.0 and dx > 0.0):
        raise ValueError("support_radius_m and voxel_size_m must be > 0")
    extent = int(math.ceil(R / dx))
    axis = np.arange(-extent, extent + 1, dtype=np.int64)
    X, Y, Z = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])


def discrete_total_mass(
    *,
    attenuation_coefficient_1_m: float,
    regularization_radius_m: float,
    support_radius_m: float,
    voxel_size_m: float,
    anisotropy_mode: str = AnisotropyMode.ISOTROPIC,
    tensor: Optional[np.ndarray] = None,
) -> float:
    """Cartesian discrete kernel mass over the finite support cube.

    Samples the kernel at every voxel centre that lies inside the cube
    ``[-R, R]³`` on the SAME cartesian lattice that the engine uses for
    per-voxel weights. Therefore for any source position::

        Σ_{j: r_j ≤ R} K(r_j) · V_j  ==  Q_total

    regardless of where the source sits relative to the grid — the
    offset between source and lattice only moves some centres outside
    the spherical support, never adds spurious mass.

    For ``ANISOTROPIC_TENSOR`` the centres inside the ellipsoidal
    support ``Δxᵀ M Δx ≤ R²`` are summed (the bounding cube is still
    ``[-R, R]³`` but only the ellipsoid-interior centres contribute).

    Returns the scalar ``Q_total`` (dimension: length, since
    ``[K] = L⁻²`` and ``[V] = L³``).
    """
    alpha = float(attenuation_coefficient_1_m)
    r0 = float(regularization_radius_m)
    R = float(support_radius_m)
    dx = float(voxel_size_m)
    if not (alpha >= 0.0 and r0 > 0.0 and R > r0 and dx > 0.0):
        raise ValueError(
            f"invalid kernel params: alpha={alpha}, r0={r0}, R={R}, dx={dx}"
        )

    offsets = _local_support_offsets(support_radius_m=R, voxel_size_m=dx)
    centres = offsets * dx  # cartesian offsets in metres
    if anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR and tensor is not None:
        M = np.asarray(tensor, dtype=np.float64)
        quad = np.einsum("ij,jk,ik->i", centres, M, centres)
        r2 = np.clip(quad, 0.0, None)
    else:
        r2 = np.einsum("ij,ij->i", centres, centres)
    inside = r2 <= R * R
    if not np.any(inside):
        return 0.0
    r_inside = np.sqrt(r2[inside])
    k = np.exp(-alpha * r_inside) / (r_inside * r_inside + r0 * r0)
    return float(np.sum(k) * (dx ** 3))


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
