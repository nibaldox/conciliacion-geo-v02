"""Phase 2 simulation contracts — single source of truth.

These frozen dataclasses are the canonical types consumed by every layer
(API, React, Streamlit, persistence, export). They mirror the discipline
of :mod:`core.geometry_contract`:

* No silent physical defaults. Every field that selects a model
  (``energy_mode``, ``temporal_mode``, ``anisotropy_mode``,
  ``kernel_type``, ``coupling_efficiency``, ``attenuation_coefficient_1_m``,
  ``regularization_radius_m``) MUST be declared explicitly by the caller
  when the configuration is confirmed.
* Confirmation is mandatory. ``user_confirmed`` MUST be exactly ``True``
  to run a simulation; any other value blocks execution.
* Validation surfaces structured diagnostics. Each ``validate()`` either
  returns ``self`` or raises :class:`SimulationConfigurationError` with
  ``error_code`` and ``details`` so the API/UI can render a precise
  diagnosis (HTTP 400/422).
* Units are explicit. Energy in joules, length in metres, time in
  seconds, density in kg/m³, velocity in m/s. No implicit conversions.

A dimensionless fraction is NEVER named ``kg/m³`` (audit H-09). Energy
density is always ``J/m³``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


SIMULATION_CONFIGURATION_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Closed literal enums
# ---------------------------------------------------------------------------

class EnergyMode:
    """How explosive energy is resolved when product data is incomplete.

    * ``ABSOLUTE`` — physical joules. Requires the explosive to resolve
      to a known product (no UNKNOWN, no MISSING, no ANFO fallback).
    * ``RELATIVE`` — dimensionless comparative field. Used when the
      explosive is unknown or its specific energy is unavailable; the
      field is normalized so its integral over the domain equals the
      total coupled "energy-equivalent" expressed in arbitrary units.
      The result is tagged ``energy_mode=RELATIVE`` and may NEVER be
      reported as J/m³.
    """
    ABSOLUTE = "ABSOLUTE"
    RELATIVE = "RELATIVE"


class TemporalMode:
    """Whether detonation delays are exercised.

    * ``STATIC`` — energy field only. ``temporal_status`` will be
      ``NOT_AVAILABLE`` if no delays were supplied.
    * ``TEMPORAL`` — delays must be present and validated; the engine
      produces arrival-time and time-of-maximum maps.
    """
    STATIC = "STATIC"
    TEMPORAL = "TEMPORAL"


class AnisotropyMode:
    """Distance metric used by the spatial kernel.

    * ``ISOTROPIC`` — Euclidean distance.
    * ``ANISOTROPIC_TENSOR`` — Mahalanobis-style metric using a symmetric
      positive-definite 3×3 tensor ``M`` (``r_aniso² = Δxᵀ M Δx``).
    """
    ISOTROPIC = "ISOTROPIC"
    ANISOTROPIC_TENSOR = "ANISOTROPIC_TENSOR"


class KernelType:
    """Supported spatial kernels. The default regularized radial kernel
    is ``EXPONENTIAL_INVERSE_SQUARE`` (``K(r) = exp(-αr)/(r²+r0²)``)."""
    EXPONENTIAL_INVERSE_SQUARE = "EXPONENTIAL_INVERSE_SQUARE"


_VALID_ENERGY_MODES = (EnergyMode.ABSOLUTE, EnergyMode.RELATIVE)
_VALID_TEMPORAL_MODES = (TemporalMode.STATIC, TemporalMode.TEMPORAL)
_VALID_ANISOTROPY_MODES = (AnisotropyMode.ISOTROPIC, AnisotropyMode.ANISOTROPIC_TENSOR)
_VALID_KERNEL_TYPES = (KernelType.EXPONENTIAL_INVERSE_SQUARE,)


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class SimulationConfigurationError(ValueError):
    """Raised when a simulation contract is incomplete or invalid.

    Carries a structured ``details`` dict so the API/UI can surface the
    exact offending field instead of an opaque message.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _is_symmetric_pd(matrix: Any) -> bool:
    """Validate a 3x3 matrix is symmetric and positive-definite.

    Accepts nested lists or a numpy array. Uses Sylvester's criterion
    (all leading principal minors > 0) — equivalent to PD for symmetric
    matrices.
    """
    import numpy as np

    try:
        m = np.asarray(matrix, dtype=float)
    except Exception:
        return False
    if m.shape != (3, 3):
        return False
    if not np.all(np.isfinite(m)):
        return False
    if not np.allclose(m, m.T, atol=1e-12):
        return False
    # Leading principal minors
    d1 = m[0, 0]
    d2 = m[0, 0] * m[1, 1] - m[0, 1] * m[1, 0]
    d3 = float(np.linalg.det(m))
    return (d1 > 0.0) and (d2 > 0.0) and (d3 > 0.0)


# ---------------------------------------------------------------------------
# Rock mass configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RockMassConfiguration:
    """Geotechnical properties of the simulated rock volume.

    All magnitudes are OPTIONAL with explicit ``status``:

    * ``VALIDATED`` — supplied by a trusted source (lab, geological model).
    * ``UNVALIDATED_REFERENCE`` — supplied from a generic reference table.
    * ``PROXY_EMPIRICAL_LOCAL`` — derived from a local empirical proxy
      (e.g. drilling-time → UCS heuristic for unit ``1c (13)``).
    * ``UNKNOWN`` / ``MISSING`` — absent.

    A ``MISSING`` critical property (density, attenuation, wave velocity)
    blocks ``ABSOLUTE`` energy mode; the operator may still run
    ``RELATIVE`` mode but the result is tagged accordingly.
    """
    rock_unit_id: str = ""
    density_kg_m3: Optional[float] = None
    ucs_mpa: Optional[float] = None
    attenuation_coefficient_1_m: Optional[float] = None
    wave_velocity_m_s: Optional[float] = None
    anisotropy_mode: str = AnisotropyMode.ISOTROPIC
    anisotropy_tensor: Optional[tuple[tuple[float, float, float], ...]] = None
    source: str = ""
    status: str = "MISSING"
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def validate(self) -> "RockMassConfiguration":
        details: dict[str, Any] = {}
        if self.density_kg_m3 is not None and (
            not _is_finite_number(self.density_kg_m3) or self.density_kg_m3 <= 0.0
        ):
            details["density_kg_m3"] = "must be > 0"
        if self.ucs_mpa is not None and (
            not _is_finite_number(self.ucs_mpa) or self.ucs_mpa <= 0.0
        ):
            details["ucs_mpa"] = "must be > 0"
        if self.attenuation_coefficient_1_m is not None and (
            not _is_finite_number(self.attenuation_coefficient_1_m)
            or self.attenuation_coefficient_1_m < 0.0
        ):
            details["attenuation_coefficient_1_m"] = "must be >= 0"
        if self.wave_velocity_m_s is not None and (
            not _is_finite_number(self.wave_velocity_m_s)
            or self.wave_velocity_m_s <= 0.0
        ):
            details["wave_velocity_m_s"] = "must be > 0"
        if self.anisotropy_mode not in _VALID_ANISOTROPY_MODES:
            details["anisotropy_mode"] = self.anisotropy_mode
        if self.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR:
            if not _is_symmetric_pd(self.anisotropy_tensor):
                details["anisotropy_tensor"] = (
                    "required, symmetric, positive-definite 3x3 when "
                    "anisotropy_mode=ANISOTROPIC_TENSOR"
                )
        if details:
            raise SimulationConfigurationError(
                "Configuración de macizo rocoso inválida.",
                error_code="ROCK_MASS_INVALID",
                details=details,
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.anisotropy_tensor is not None:
            d["anisotropy_tensor"] = [list(row) for row in self.anisotropy_tensor]
        return d


# ---------------------------------------------------------------------------
# Domain bounds + voxel grid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainBounds:
    """Axis-aligned rock-mass domain in mining coordinates.

    Convention (project-wide): X=East, Y=North, Z=Elevation (m).
    """
    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float

    def validate(self) -> "DomainBounds":
        if not all(_is_finite_number(v) for v in asdict(self).values()):
            raise SimulationConfigurationError(
                "Domain bounds contienen NaN/inf.",
                error_code="DOMAIN_NON_FINITE",
                details={"bounds": asdict(self)},
            )
        if self.x_max <= self.x_min or self.y_max <= self.y_min or self.z_max <= self.z_min:
            raise SimulationConfigurationError(
                "Domain bounds invertidos o degenerados.",
                error_code="DOMAIN_INVERTED",
                details={
                    "x_span": self.x_max - self.x_min,
                    "y_span": self.y_max - self.y_min,
                    "z_span": self.z_max - self.z_min,
                },
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VoxelGridSpecification:
    """Regular Cartesian voxel grid covering ``DomainBounds``.

    The voxel size MUST be positive; the resulting voxel volume MUST be
    non-zero. The grid is right-handed with shape ``(nx, ny, nz)``.
    """
    voxel_size_m: float
    bounds: DomainBounds

    def validate(self) -> "VoxelGridSpecification":
        if not _is_finite_number(self.voxel_size_m) or self.voxel_size_m <= 0.0:
            raise SimulationConfigurationError(
                "voxel_size_m debe ser positivo y finito.",
                error_code="VOXEL_SIZE_INVALID",
                details={"voxel_size_m": self.voxel_size_m},
            )
        self.bounds.validate()
        return self

    @property
    def shape(self) -> tuple[int, int, int]:
        nx = max(1, int(math.floor((self.bounds.x_max - self.bounds.x_min) / self.voxel_size_m)))
        ny = max(1, int(math.floor((self.bounds.y_max - self.bounds.y_min) / self.voxel_size_m)))
        nz = max(1, int(math.floor((self.bounds.z_max - self.bounds.z_min) / self.voxel_size_m)))
        return (nx, ny, nz)

    @property
    def voxel_count(self) -> int:
        nx, ny, nz = self.shape
        return nx * ny * nz

    @property
    def voxel_volume_m3(self) -> float:
        return float(self.voxel_size_m) ** 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "voxel_size_m": self.voxel_size_m,
            "bounds": self.bounds.to_dict(),
            "shape": list(self.shape),
            "voxel_count": self.voxel_count,
            "voxel_volume_m3": self.voxel_volume_m3,
        }


# ---------------------------------------------------------------------------
# Propagation + temporal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnergyPropagationConfiguration:
    """Spatial-energy propagation parameters.

    ``coupling_efficiency`` is dimensionless in ``[0, 1]``.
    ``attenuation_coefficient_1_m`` (α) is the exponential decay rate in
    1/m; zero means "no geometric attenuation beyond the inverse-square
    regularized term".
    ``regularization_radius_m`` (r0) avoids the singularity at r=0.
    """
    kernel_type: str = KernelType.EXPONENTIAL_INVERSE_SQUARE
    attenuation_coefficient_1_m: Optional[float] = None
    regularization_radius_m: Optional[float] = None
    coupling_efficiency: Optional[float] = None

    def validate(self) -> "EnergyPropagationConfiguration":
        details: dict[str, Any] = {}
        if self.kernel_type not in _VALID_KERNEL_TYPES:
            details["kernel_type"] = self.kernel_type
        if self.attenuation_coefficient_1_m is None:
            details["attenuation_coefficient_1_m"] = "required"
        elif (
            not _is_finite_number(self.attenuation_coefficient_1_m)
            or self.attenuation_coefficient_1_m < 0.0
        ):
            details["attenuation_coefficient_1_m"] = "must be >= 0"
        if self.regularization_radius_m is None:
            details["regularization_radius_m"] = "required"
        elif (
            not _is_finite_number(self.regularization_radius_m)
            or self.regularization_radius_m <= 0.0
        ):
            details["regularization_radius_m"] = "must be > 0"
        if self.coupling_efficiency is None:
            details["coupling_efficiency"] = "required"
        elif (
            not _is_finite_number(self.coupling_efficiency)
            or self.coupling_efficiency < 0.0
            or self.coupling_efficiency > 1.0
        ):
            details["coupling_efficiency"] = "must be in [0, 1]"
        if details:
            raise SimulationConfigurationError(
                "Configuración de propagación energética inválida o incompleta.",
                error_code="PROPAGATION_INVALID",
                details=details,
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TemporalSimulationConfiguration:
    """Temporal simulation parameters.

    ``temporal_mode=STATIC`` requires only the mode itself.
    ``temporal_mode=TEMPORAL`` requires ``propagation_velocity_m_s``
    (with provenance) and optionally ``pulse_sigma_s``; if sigma is
    absent the engine falls back to ``SIMULATION.fallback_temporal_sigma_s``
    but tags ``temporal_status=PULSE_SIGMA_FALLBACK``.
    """
    temporal_mode: str = TemporalMode.STATIC
    propagation_velocity_m_s: Optional[float] = None
    propagation_velocity_source: str = ""
    pulse_sigma_s: Optional[float] = None

    def validate(self) -> "TemporalSimulationConfiguration":
        details: dict[str, Any] = {}
        if self.temporal_mode not in _VALID_TEMPORAL_MODES:
            details["temporal_mode"] = self.temporal_mode
        if self.temporal_mode == TemporalMode.TEMPORAL:
            if self.propagation_velocity_m_s is None:
                details["propagation_velocity_m_s"] = "required when temporal_mode=TEMPORAL"
            elif (
                not _is_finite_number(self.propagation_velocity_m_s)
                or self.propagation_velocity_m_s <= 0.0
            ):
                details["propagation_velocity_m_s"] = "must be > 0"
            if not self.propagation_velocity_source:
                details["propagation_velocity_source"] = (
                    "required provenance when temporal_mode=TEMPORAL"
                )
            if (
                self.pulse_sigma_s is not None
                and (not _is_finite_number(self.pulse_sigma_s) or self.pulse_sigma_s <= 0.0)
            ):
                details["pulse_sigma_s"] = "must be > 0 when provided"
        if details:
            raise SimulationConfigurationError(
                "Configuración temporal inválida.",
                error_code="TEMPORAL_INVALID",
                details=details,
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Top-level configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulationConfiguration:
    """Canonical, versioned simulation configuration (spec §7).

    Aggregates rock mass, grid, propagation and temporal sub-configs.
    ``user_confirmed`` MUST be exactly ``True`` for the engine to run;
    any other value blocks execution and surfaces a structured error.

    ``energy_mode`` selects ABSOLUTE (joules) or RELATIVE (dimensionless)
    output. ``geometry_configuration_version`` ties the simulation to
    the Fase 1 contract version that produced the accepted rows.
    """
    simulation_configuration_version: str = SIMULATION_CONFIGURATION_VERSION
    geometry_configuration_version: str = ""
    user_confirmed: Optional[bool] = None

    voxel_size_m: Optional[float] = None
    domain_bounds: Optional[DomainBounds] = None

    energy_mode: Optional[str] = None
    temporal_mode: Optional[str] = None
    anisotropy_mode: Optional[str] = None

    kernel_type: str = KernelType.EXPONENTIAL_INVERSE_SQUARE
    attenuation_coefficient_1_m: Optional[float] = None
    regularization_radius_m: Optional[float] = None
    coupling_efficiency: Optional[float] = None

    propagation_velocity_m_s: Optional[float] = None
    propagation_velocity_source: str = ""
    pulse_sigma_s: Optional[float] = None

    rock_mass: RockMassConfiguration = field(default_factory=RockMassConfiguration)

    def validate(self) -> "SimulationConfiguration":
        details: dict[str, Any] = {}

        if self.user_confirmed is None:
            raise SimulationConfigurationError(
                "Configuración no confirmada (user_confirmed=None): "
                "la simulación está bloqueada.",
                error_code="SIMULATION_NOT_CONFIRMED",
                details={"state": "UNCONFIRMED"},
            )
        if self.user_confirmed is False:
            raise SimulationConfigurationError(
                "Configuración rechazada (user_confirmed=False): "
                "la simulación está bloqueada.",
                error_code="SIMULATION_REJECTED",
                details={"state": "REJECTED"},
            )
        if self.simulation_configuration_version != SIMULATION_CONFIGURATION_VERSION:
            details["simulation_configuration_version"] = (
                f"expected {SIMULATION_CONFIGURATION_VERSION!r}, "
                f"got {self.simulation_configuration_version!r}"
            )
        if not self.geometry_configuration_version:
            details["geometry_configuration_version"] = (
                "required: tie to the Fase 1 contract that produced accepted_rows"
            )
        if self.energy_mode not in _VALID_ENERGY_MODES:
            details["energy_mode"] = self.energy_mode
        if self.temporal_mode not in _VALID_TEMPORAL_MODES:
            details["temporal_mode"] = self.temporal_mode
        if self.anisotropy_mode not in _VALID_ANISOTROPY_MODES:
            details["anisotropy_mode"] = self.anisotropy_mode
        if self.kernel_type not in _VALID_KERNEL_TYPES:
            details["kernel_type"] = self.kernel_type
        if self.voxel_size_m is None or not _is_finite_number(self.voxel_size_m) or self.voxel_size_m <= 0.0:
            details["voxel_size_m"] = "required, > 0"
        if self.domain_bounds is None:
            details["domain_bounds"] = "required"
        if self.attenuation_coefficient_1_m is None or self.attenuation_coefficient_1_m < 0.0:
            details["attenuation_coefficient_1_m"] = "required, >= 0"
        if self.regularization_radius_m is None or self.regularization_radius_m <= 0.0:
            details["regularization_radius_m"] = "required, > 0"
        if self.coupling_efficiency is None or not (0.0 <= self.coupling_efficiency <= 1.0):
            details["coupling_efficiency"] = "required, in [0, 1]"
        if self.temporal_mode == TemporalMode.TEMPORAL:
            if self.propagation_velocity_m_s is None or self.propagation_velocity_m_s <= 0.0:
                details["propagation_velocity_m_s"] = "required > 0 when temporal_mode=TEMPORAL"
            if not self.propagation_velocity_source:
                details["propagation_velocity_source"] = "required provenance when temporal_mode=TEMPORAL"
        if self.anisotropy_mode == AnisotropyMode.ANISOTROPIC_TENSOR:
            if not _is_symmetric_pd(self.rock_mass.anisotropy_tensor):
                details["anisotropy_tensor"] = (
                    "required symmetric PD 3x3 when anisotropy_mode=ANISOTROPIC_TENSOR"
                )

        if details:
            raise SimulationConfigurationError(
                "Configuración de simulación incompleta o inválida. "
                "La ejecución está bloqueada.",
                error_code="SIMULATION_INVALID",
                details={"missing_or_invalid": details},
            )

        # Cross-validate sub-contracts
        self.rock_mass.validate()
        EnergyPropagationConfiguration(
            kernel_type=self.kernel_type,
            attenuation_coefficient_1_m=self.attenuation_coefficient_1_m,
            regularization_radius_m=self.regularization_radius_m,
            coupling_efficiency=self.coupling_efficiency,
        ).validate()
        TemporalSimulationConfiguration(
            temporal_mode=self.temporal_mode,
            propagation_velocity_m_s=self.propagation_velocity_m_s,
            propagation_velocity_source=self.propagation_velocity_source,
            pulse_sigma_s=self.pulse_sigma_s,
        ).validate()
        VoxelGridSpecification(
            voxel_size_m=self.voxel_size_m,
            bounds=self.domain_bounds,
        ).validate()
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_configuration_version": self.simulation_configuration_version,
            "geometry_configuration_version": self.geometry_configuration_version,
            "user_confirmed": self.user_confirmed,
            "voxel_size_m": self.voxel_size_m,
            "domain_bounds": self.domain_bounds.to_dict() if self.domain_bounds else None,
            "energy_mode": self.energy_mode,
            "temporal_mode": self.temporal_mode,
            "anisotropy_mode": self.anisotropy_mode,
            "kernel_type": self.kernel_type,
            "attenuation_coefficient_1_m": self.attenuation_coefficient_1_m,
            "regularization_radius_m": self.regularization_radius_m,
            "coupling_efficiency": self.coupling_efficiency,
            "propagation_velocity_m_s": self.propagation_velocity_m_s,
            "propagation_velocity_source": self.propagation_velocity_source,
            "pulse_sigma_s": self.pulse_sigma_s,
            "rock_mass": self.rock_mass.to_dict(),
        }


# ---------------------------------------------------------------------------
# Result-side contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChargeSegment:
    """A discretized explosive-charge segment inside a hole cylinder.

    A hole is split into:
      * ``taco`` — stemming (no explosive, skipped).
      * one or more ``charge`` segments — explosive mass distributed
        along the collar-to-toe axis.
      * ``deck_gap`` — inert gap between decks (no explosive, skipped).
      * ``partial`` — a charge segment truncated by the domain boundary.

    ``mass_kg`` is the explosive mass attributed to this segment. For
    ``RELATIVE`` mode it is the raw ``kg`` (the engine normalizes later);
    for ``ABSOLUTE`` mode it is converted to joules using the resolved
    explosive energy.
    """
    hole_id: str
    segment_type: str  # "charge" | "taco" | "deck_gap" | "partial"
    cx: float
    cy: float
    cz: float
    length_m: float
    diameter_mm: float
    mass_kg: float
    energy_j: Optional[float]
    explosive_name: str
    explosive_status: str
    detonation_time_s: Optional[float]
    in_domain: bool
    source_row_index: Optional[int] = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["warnings"] = list(self.warnings)
        return d


@dataclass(frozen=True)
class GridMetadata:
    """Axes order, shape, dtype and units of the persisted field."""
    shape: tuple[int, int, int]
    voxel_size_m: float
    bounds: DomainBounds
    axes_order: str  # e.g. "xyz" (mining convention)
    energy_unit: str  # "J" | "dimensionless"
    dtype: str  # numpy dtype name
    voxel_count: int
    voxel_volume_m3: float
    npz_sha256: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["shape"] = list(self.shape)
        d["bounds"] = self.bounds.to_dict()
        return d


@dataclass(frozen=True)
class SimulationSourceSummary:
    """Aggregate source counts for the simulation diagnostics."""
    source_rows: int = 0
    accepted_holes: int = 0
    rejected_holes: int = 0
    charge_segments: int = 0
    valid_sources: int = 0
    invalid_sources: int = 0
    voxel_count: int = 0
    active_voxels: int = 0
    represented_energy_j: float = 0.0
    outside_domain_energy_j: float = 0.0
    warning_count: int = 0
    blocking_error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProcessingSummary:
    """Stable, non-overlapping execution counts."""
    accepted_holes: int
    charge_segments: int
    valid_sources: int
    invalid_sources: int
    voxel_count: int
    active_voxels: int
    represented_energy_j: float
    outside_domain_energy_j: float
    total_coupled_energy_j: float
    fraction_represented: float
    warning_records: int
    blocking_error_records: int
    temporal_status: str  # "AVAILABLE" | "NOT_AVAILABLE" | "PULSE_SIGMA_FALLBACK"
    energy_mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationDiagnostics:
    """Spatial and temporal diagnostics carried alongside the field."""
    spatial_diagnostics: dict[str, Any] = field(default_factory=dict)
    temporal_diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationProvenance:
    """Where every input and decision came from."""
    engine_version: str
    simulation_configuration_version: str
    geometry_configuration_version: str
    explosive_registry_source: str
    explosive_products_used: tuple[str, ...] = ()
    rock_mass_source: str = ""
    propagation_velocity_source: str = ""
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    accepted_rows_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["explosive_products_used"] = list(self.explosive_products_used)
        d["assumptions"] = list(self.assumptions)
        d["warnings"] = list(self.warnings)
        return d


@dataclass(frozen=True)
class VoxelEnergyField:
    """The 3D energy field metadata. The raw array is persisted separately
    as a compressed NPZ artifact (SHA-256 verified on read-back).

    ``dominant_hole_id`` and ``contributing_sources`` are stored as
    separate arrays in the NPZ; the JSON metadata keeps only aggregate
    counts to avoid bloating SQLite.
    """
    grid: GridMetadata
    represented_energy_j: float
    outside_domain_energy_j: float
    total_coupled_energy_j: float
    fraction_represented: float
    active_voxels: int
    max_energy_j: float
    mean_energy_j_active: float
    npz_path: str = ""
    energy_unit: str = "J"

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid": self.grid.to_dict(),
            "represented_energy_j": self.represented_energy_j,
            "outside_domain_energy_j": self.outside_domain_energy_j,
            "total_coupled_energy_j": self.total_coupled_energy_j,
            "fraction_represented": self.fraction_represented,
            "active_voxels": self.active_voxels,
            "max_energy_j": self.max_energy_j,
            "mean_energy_j_active": self.mean_energy_j_active,
            "npz_path": self.npz_path,
            "energy_unit": self.energy_unit,
        }


@dataclass(frozen=True)
class PlanSlice:
    """Horizontal energy slice at a given elevation."""
    elevation_m: float
    unit: str
    grid_shape: tuple[int, int]
    data_sha256: str
    max_value: float
    mean_value: float
    represented_energy_j: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["grid_shape"] = list(self.grid_shape)
        return d


@dataclass(frozen=True)
class SectionSlice:
    """Vertical energy slice along an in-plane axis."""
    axis: str  # "x" | "y"
    coordinate_m: float
    unit: str
    grid_shape: tuple[int, int]
    data_sha256: str
    max_value: float
    mean_value: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["grid_shape"] = list(self.grid_shape)
        return d


@dataclass(frozen=True)
class SimulationResult:
    """Canonical simulation result — single authority (spec §8).

    Every layer (API, React, Streamlit, export, persistence) consumes
    this object. It is NEVER reconstructed downstream. Large volumetric
    arrays live in the NPZ artifact referenced by ``energy_field.npz_path``;
    SQLite stores only metadata + summary.
    """
    simulation_id: str
    configuration: dict[str, Any]
    grid_metadata: GridMetadata
    source_summary: SimulationSourceSummary
    energy_field: VoxelEnergyField
    plan_slices: tuple[PlanSlice, ...]
    section_slices: tuple[SectionSlice, ...]
    processing_summary: ProcessingSummary
    warnings: tuple[dict[str, Any], ...]
    blocking_errors: tuple[dict[str, Any], ...]
    spatial_diagnostics: dict[str, Any]
    temporal_diagnostics: dict[str, Any]
    provenance: SimulationProvenance
    created_at: str
    engine_version: str

    def to_dict(self, *, include_artifacts: bool = False) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "configuration": self.configuration,
            "grid_metadata": self.grid_metadata.to_dict(),
            "source_summary": self.source_summary.to_dict(),
            "energy_field": self.energy_field.to_dict(),
            "plan_slices": [s.to_dict() for s in self.plan_slices],
            "section_slices": [s.to_dict() for s in self.section_slices],
            "processing_summary": self.processing_summary.to_dict(),
            "warnings": list(self.warnings),
            "blocking_errors": list(self.blocking_errors),
            "spatial_diagnostics": self.spatial_diagnostics,
            "temporal_diagnostics": self.temporal_diagnostics,
            "provenance": self.provenance.to_dict(),
            "created_at": self.created_at,
            "engine_version": self.engine_version,
        }
