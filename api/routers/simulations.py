"""Phase 2 — blast energy simulation endpoints.

Endpoints (spec §9):

    POST /api/v1/blast/simulations
    GET  /api/v1/blast/simulations/{simulation_id}             legacy alias of /summary
    GET  /api/v1/blast/simulations/{simulation_id}/summary     canonical JSON
    GET  /api/v1/blast/simulations/{simulation_id}/profile     linear profile
    GET  /api/v1/blast/simulations/{simulation_id}/plan        full 2D slice
    GET  /api/v1/blast/simulations/{simulation_id}/section     full 2D slice
    GET  /api/v1/blast/simulations/{simulation_id}/export      xlsx | npz | json | json_gz

Discipline (Brecha 3.1, Falla 4, Falla 7):

* Request bodies use Pydantic v2 ``extra="forbid"`` on every nested
  schema. Unknown fields raise HTTP 422 with ``error_code="UNKNOWN_FIELD"``
  (manual JSON parsing keeps the conversion self-contained — no app-level
  exception handler required).
* ``/plan`` and ``/section`` return the FULL Falla-4 payload: ``values``
  (flattened 2D), coordinates, ``valid_mask``, ``percentiles``,
  ``source_holes_projection`` and ``data_sha256``. Never only aggregates.
* ``/profile`` interpolates the canonical 3D field between two endpoints
  via :func:`core.blast_simulation.profile_slice` — no physics in this
  router.
* Blocked simulations (engine rejected the configuration at runtime,
  e.g. ``energy_mode=ABSOLUTE`` with an unknown explosive) emit HTTP 422
  with ``error_code="SIMULATION_BLOCKED"`` and DO NOT write the NPZ
  artifact, the JSON summary, or insert a SQLite row (Falla 7).
* When the JSON payload exceeds 1 MB, it is gzip-compressed and served
  with ``Content-Type: application/octet-stream`` plus
  ``X-Payload-Encoding: gzip`` and ``X-Original-Size``.

The router is a presentation layer only — every physical decision lives
in :mod:`core.blast_simulation`. This module never re-implements the
engine.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import math
import tempfile
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from core.blast_simulation import (
    DomainBounds,
    KernelType,
    PersistenceError,
    PlanSlice,
    RockMassConfiguration,
    SIMULATION_CONFIGURATION_VERSION,
    SectionSlice,
    SimulationConfiguration,
    SimulationConfigurationError,
    VoxelGridSpecification,
    attach_slices_to_result,
    compute_field_arrays,
    export_simulation_xlsx,
    npz_path_for,
    profile_slice,
    read_npz_artifact,
    run_simulation,
    should_persist,
    write_atomic_simulation,
)
from core.config import SIMULATION

import api.database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/blast/simulations", tags=["blast-simulation"])


# ---------------------------------------------------------------------------
# Request / response schemas — Brecha 3.1: extra="forbid"
# ---------------------------------------------------------------------------
#
# V6-01: Every scientific numeric field uses ``StrictNumericFloat`` (or
# ``StrictInt`` for counts) so Pydantic rejects ``str`` and ``bool``
# payloads *before* lax coercion accepts them. Enumerated scientific
# choices (energy_mode, temporal_mode, anisotropy_mode, kernel_type and
# the section axis) use ``Literal[...]`` so any value outside the
# closed set raises HTTP 422 at the body parser. Semantic body failures
# (bounds ordering, tensor symmetry / positive-definiteness, support
# radius relationship) live in Pydantic ``model_validator`` /
# ``field_validator`` so they also surface as HTTP 422 rather than the
# HTTP 400 channel fed by ``SimulationConfigurationError``.

EnergyModeLiteral = Literal["ABSOLUTE", "RELATIVE"]
TemporalModeLiteral = Literal["STATIC", "TEMPORAL"]
AnisotropyModeLiteral = Literal["ISOTROPIC", "ANISOTROPIC_TENSOR"]
KernelTypeLiteral = Literal["EXPONENTIAL_INVERSE_SQUARE"]
SectionAxisLiteral = Literal["x", "y"]


def _reject_str_or_bool(v: Any) -> Any:
    """BeforeValidator: reject ``str`` and ``bool`` payloads for numeric
    fields before Pydantic lax mode coerces them.

    JSON numbers (Python ``int`` / ``float``) are passed through untouched
    so an integer like ``1`` still satisfies a ``float`` annotation
    (lax int→float coercion is preserved). ``None`` is passed through so
    ``Optional`` fields keep working.
    """
    if v is None:
        return v
    if isinstance(v, bool):
        raise ValueError("valor debe ser un número JSON, no bool")
    if isinstance(v, str):
        raise ValueError("valor debe ser un número JSON, no str")
    return v


StrictNumericFloat = Annotated[float, BeforeValidator(_reject_str_or_bool)]


def _finite_float(v: Any) -> float:
    """Coerce to float and reject NaN / ±Infinity."""
    f = float(v)
    if not math.isfinite(f):
        raise ValueError("value must be finite (no NaN/inf)")
    return f


def _positive_finite(v: Any, *, allow_zero: bool = False) -> float:
    """Reject NaN/inf and enforce positivity."""
    f = _finite_float(v)
    if allow_zero:
        if f < 0.0:
            raise ValueError("value must be >= 0")
    else:
        if f <= 0.0:
            raise ValueError("value must be > 0")
    return f


class RockMassSchema(BaseModel):
    """Fase 1 → Fase 2 rock-mass carrier. ``extra='forbid'`` rejects any
    field not enumerated here. All numeric fields reject NaN/inf and
    str/bool coercion (V6-01).
    """
    model_config = ConfigDict(extra="forbid", validate_default=True)

    rock_unit_id: str = ""
    density_kg_m3: Optional[StrictNumericFloat] = None
    ucs_mpa: Optional[StrictNumericFloat] = None
    attenuation_coefficient_1_m: Optional[StrictNumericFloat] = None
    wave_velocity_m_s: Optional[StrictNumericFloat] = None
    anisotropy_mode: AnisotropyModeLiteral = "ISOTROPIC"
    anisotropy_tensor: Optional[List[List[StrictNumericFloat]]] = None
    source: str = ""
    status: str = "MISSING"
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @field_validator("density_kg_m3")
    @classmethod
    def _density_positive(cls, v):
        if v is not None:
            return _positive_finite(v)
        return v

    @field_validator("ucs_mpa")
    @classmethod
    def _ucs_positive(cls, v):
        if v is not None:
            return _positive_finite(v)
        return v

    @field_validator("attenuation_coefficient_1_m")
    @classmethod
    def _att_finite(cls, v):
        if v is not None:
            return _positive_finite(v, allow_zero=True)
        return v

    @field_validator("wave_velocity_m_s")
    @classmethod
    def _velocity_positive(cls, v):
        if v is not None:
            return _positive_finite(v)
        return v

    @field_validator("anisotropy_tensor")
    @classmethod
    def _validate_anisotropy_tensor(cls, v, info):
        """Validate the 3×3 anisotropy tensor: required (symmetric +
        positive-definite) when the rock mass is in
        ``ANISOTROPIC_TENSOR`` mode, and shape/finiteness/symmetry/PD
        checked whenever supplied.

        Runs even when the field is at its default ``None`` thanks to
        ``validate_default=True`` on the model config, so the
        *required-when-mode* check fires at parse time. The raised
        ``ValueError`` is reported with loc
        ``body.rock_mass.anisotropy_tensor`` (V6 contract test).
        """
        mode = info.data.get("anisotropy_mode", "ISOTROPIC")
        if v is None:
            if mode == "ANISOTROPIC_TENSOR":
                raise ValueError(
                    "anisotropy_tensor es obligatorio cuando "
                    "anisotropy_mode=ANISOTROPIC_TENSOR"
                )
            return v

        if len(v) != 3 or any(len(row) != 3 for row in v):
            raise ValueError("anisotropy_tensor debe ser una matriz 3x3")
        flat = [float(c) for row in v for c in row]
        if not all(math.isfinite(x) for x in flat):
            raise ValueError("anisotropy_tensor debe ser finito (sin NaN/inf)")
        m = np.array(flat, dtype=float).reshape(3, 3)
        if not np.allclose(m, m.T, atol=1e-12):
            raise ValueError("anisotropy_tensor debe ser simétrica")
        d1 = m[0, 0]
        d2 = m[0, 0] * m[1, 1] - m[0, 1] * m[1, 0]
        d3 = float(np.linalg.det(m))
        if not (d1 > 0.0 and d2 > 0.0 and d3 > 0.0):
            raise ValueError(
                "anisotropy_tensor debe ser definida positiva "
                "(menores principales leading > 0)"
            )
        return v


class DomainBoundsSchema(BaseModel):
    """Typed replacement for the free-form ``Dict[str, float]`` that
    previously carried the domain bounds (Falla 9 fix, audit v2 §9).

    ``extra='forbid'`` rejects unknown axes (e.g. ``w_axis``) with HTTP
    422 + ``UNKNOWN_FIELD``. Numeric values reject ``str``/``bool``
    coercion (V6-01) and NaN/inf via the ``finite`` validator. Bounds
    ordering (``x_min < x_max`` etc.) is enforced here in Pydantic so
    inverted or degenerate bounds return HTTP 422 instead of the
    HTTP 400 channel fed by ``DomainBounds.validate()``.
    """
    model_config = ConfigDict(extra="forbid")

    x_min: StrictNumericFloat
    y_min: StrictNumericFloat
    z_min: StrictNumericFloat
    x_max: StrictNumericFloat
    y_max: StrictNumericFloat
    z_max: StrictNumericFloat

    @field_validator("x_min", "y_min", "z_min", "x_max", "y_max", "z_max")
    @classmethod
    def _reject_non_finite(cls, v: float) -> float:
        v_f = float(v)
        if not math.isfinite(v_f):
            raise ValueError("domain_bounds values must be finite (no NaN/inf)")
        return v_f

    @model_validator(mode="after")
    def _bounds_ordered(self):
        """Enforce strictly ordered, non-degenerate bounds on every axis.

        Raises ``ValueError`` from the model so the failure is reported
        with loc ``body.domain_bounds`` and HTTP 422.
        """
        if self.x_max <= self.x_min:
            raise ValueError("x_max debe ser > x_min")
        if self.y_max <= self.y_min:
            raise ValueError("y_max debe ser > y_min")
        if self.z_max <= self.z_min:
            raise ValueError("z_max debe ser > z_min")
        return self


class SimulationCreateRequest(BaseModel):
    """Body for ``POST /blast/simulations``.

    Every physical decision must be supplied explicitly. All numeric
    fields reject NaN / ±Infinity and ``str`` / ``bool`` coercion
    (V6-01). Enumerated scientific choices use ``Literal[...]``.
    ``extra='forbid'`` rejects unknown fields.
    """
    model_config = ConfigDict(extra="forbid")

    session_id: str
    geometry_configuration_version: str
    user_confirmed: bool

    voxel_size_m: StrictNumericFloat
    domain_bounds: DomainBoundsSchema

    energy_mode: EnergyModeLiteral
    temporal_mode: TemporalModeLiteral
    anisotropy_mode: AnisotropyModeLiteral

    kernel_type: KernelTypeLiteral = "EXPONENTIAL_INVERSE_SQUARE"
    attenuation_coefficient_1_m: StrictNumericFloat
    regularization_radius_m: StrictNumericFloat
    support_radius_m: StrictNumericFloat
    coupling_efficiency: StrictNumericFloat

    propagation_velocity_m_s: Optional[StrictNumericFloat] = None
    propagation_velocity_source: str = ""
    pulse_sigma_s: Optional[StrictNumericFloat] = None

    segments_per_hole: StrictInt = 8
    plan_elevations: List[StrictNumericFloat] = Field(default_factory=list)
    section_coordinates: List[Tuple[SectionAxisLiteral, StrictNumericFloat]] = Field(default_factory=list)

    rock_mass: RockMassSchema = Field(default_factory=RockMassSchema)

    @field_validator("voxel_size_m")
    @classmethod
    def _voxel_positive(cls, v):
        return _positive_finite(v)

    @field_validator("attenuation_coefficient_1_m")
    @classmethod
    def _att_positive_or_zero(cls, v):
        return _positive_finite(v, allow_zero=True)

    @field_validator("regularization_radius_m")
    @classmethod
    def _reg_positive(cls, v):
        return _positive_finite(v)

    @field_validator("support_radius_m")
    @classmethod
    def _support_positive(cls, v):
        return _positive_finite(v)

    @field_validator("coupling_efficiency")
    @classmethod
    def _coupling_range(cls, v):
        f = _finite_float(v)
        if not (0.0 <= f <= 1.0):
            raise ValueError("coupling_efficiency must be in [0, 1]")
        return f

    @field_validator("segments_per_hole")
    @classmethod
    def _segments_positive(cls, v):
        if v <= 0:
            raise ValueError("segments_per_hole must be > 0")
        return v

    @field_validator("plan_elevations")
    @classmethod
    def _plan_elevations_finite(cls, v):
        return [_finite_float(x) for x in v]

    @field_validator("section_coordinates")
    @classmethod
    def _section_coords_finite(cls, v):
        out = []
        for pair in v:
            axis, coord = pair
            if axis not in ("x", "y"):
                raise ValueError(f"section_coordinates axis must be 'x' or 'y'; got {axis!r}")
            out.append((axis, _finite_float(coord)))
        return out

    @field_validator("propagation_velocity_m_s")
    @classmethod
    def _velocity_optional_positive(cls, v):
        if v is not None:
            return _positive_finite(v)
        return v

    @field_validator("pulse_sigma_s")
    @classmethod
    def _sigma_optional_positive(cls, v):
        if v is not None:
            return _positive_finite(v)
        return v

    @model_validator(mode="after")
    def _support_gt_regularization(self):
        if self.support_radius_m <= self.regularization_radius_m:
            raise ValueError(
                "support_radius_m must be > regularization_radius_m"
            )
        return self


class SimulationCreateResponse(BaseModel):
    """Top-level response for ``POST /blast/simulations``.

    ``persisted`` is ``False`` when the engine rejected the simulation
    (Falla 7) — in that case ``npz_sha256`` is the empty string and no
    SQLite row exists for the returned ``simulation_id``.
    """
    simulation_id: str
    persisted: bool = True
    summary: Dict[str, Any]
    configuration: Dict[str, Any]
    grid_metadata: Dict[str, Any]
    energy_field: Dict[str, Any]
    plan_slices: List[Dict[str, Any]]
    section_slices: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    blocking_errors: List[Dict[str, Any]]
    provenance: Dict[str, Any]
    npz_sha256: str


class ProfileResponse(BaseModel):
    """Response for ``GET /profile``."""
    simulation_id: str
    field_type: str
    unit: str
    distances_m: List[float]
    values: List[float]
    min: float
    max: float
    mean: float
    start_xyz: List[float]
    end_xyz: List[float]
    n_samples: int
    data_sha256: str


# ---------------------------------------------------------------------------
# Helpers — structured errors, validation translation, gzip, executor
# ---------------------------------------------------------------------------


def _structured_error(
    status: int,
    exc: Exception | str,
    *,
    error_code: str,
    details: Optional[Dict[str, Any]] = None,
) -> HTTPException:
    """Build a uniform HTTPException with structured diagnostic detail.

    Every diagnostic returned by this router flows through here so the
    UI / tests can rely on a single shape::

        {"detail": {"error_code": "...", "message": "...", "details": {...}}}
    """
    return HTTPException(
        status_code=status,
        detail={
            "error_code": error_code,
            "message": str(exc),
            "details": details or {},
        },
    )


def _translate_validation_error(exc: ValidationError) -> HTTPException:
    """Translate a Pydantic v2 ``ValidationError`` into our structured 422.

    * ``extra_forbidden`` errors → ``UNKNOWN_FIELD`` (422). The list of
      offending field paths is collected under ``details.unknown_fields``.
    * everything else (``missing``, ``json_invalid``, ``model_type``,
      nested schema violations) → ``INVALID_REQUEST`` (422) with the raw
      error list preserved under ``details.validation_errors``.
    """
    errors = exc.errors()
    extra = [e for e in errors if e.get("type") == "extra_forbidden"]
    if extra:
        fields: List[str] = []
        for e in extra:
            loc = e.get("loc") or ()
            # Drop the synthetic "body" prefix added by FastAPI when the
            # schema is a request body; keep every other path segment.
            parts = [str(p) for p in loc if str(p) != "body"]
            fields.append(".".join(parts) if parts else "<root>")
        return _structured_error(
            422,
            "Request body contiene campos no permitidos.",
            error_code="UNKNOWN_FIELD",
            details={"unknown_fields": sorted(set(fields)) or ["<root>"]},
        )
    return _structured_error(
        422,
        "Request body inválido.",
        error_code="INVALID_REQUEST",
        details={"validation_errors": _sanitize_errors(errors)},
    )


def _sanitize_value(v: Any) -> Any:
    """Recursively replace NaN/Infinity floats with their repr string."""
    if isinstance(v, float):
        if not math.isfinite(v):
            return repr(v)
        return v
    if isinstance(v, dict):
        return {k: _sanitize_value(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_sanitize_value(x) for x in v]
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    return str(v)


def _sanitize_errors(errors: list) -> list:
    """Make Pydantic validation errors JSON-serializable and normalize
    their ``loc`` to start with ``"body"``.

    Pydantic v2 error dicts may carry non-serializable values in
    ``ctx`` and ``input`` (e.g. ``ValueError`` instances, NaN, Infinity).
    We recursively sanitize anything that standard JSON cannot handle.

    The router parses the request body via
    ``SimulationCreateRequest.model_validate_json(...)`` instead of
    FastAPI's default body parser, so Pydantic reports ``loc`` paths
    starting at the schema root (``("domain_bounds",)``) rather than
    including the conventional ``"body"`` prefix FastAPI emits
    (``("body", "domain_bounds")``). V6-01 normalises every error to
    the FastAPI convention so callers and tests can rely on a single
    shape.
    """
    safe: list = []
    for e in errors:
        se = dict(e)
        loc = list(se.get("loc") or ())
        if not loc or str(loc[0]) != "body":
            loc = ["body", *loc]
        se["loc"] = tuple(loc)
        ctx = se.get("ctx")
        if ctx and isinstance(ctx, dict):
            se["ctx"] = {k: _sanitize_value(v) for k, v in ctx.items()}
        se["input"] = _sanitize_value(se.get("input"))
        safe.append(se)
    return safe


def _json_or_gzip(
    payload: Dict[str, Any],
    *,
    status_code: int = 200,
    threshold_bytes: int = 1_000_000,
) -> Response:
    """Serialise the JSON; gzip it when the body exceeds ``threshold_bytes``.

    Large payloads (typical for full plan/section matrices) are served
    with ``Content-Type: application/octet-stream`` plus headers
    ``X-Payload-Encoding: gzip`` and ``X-Original-Size: <bytes>``. Small
    payloads remain plain ``application/json`` so the existing tests and
    clients keep working without changes.
    """
    body_bytes = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
    if len(body_bytes) > threshold_bytes:
        return Response(
            content=gzip.compress(body_bytes),
            status_code=status_code,
            media_type="application/octet-stream",
            headers={
                "X-Payload-Encoding": "gzip",
                "X-Original-Size": str(len(body_bytes)),
            },
        )
    return JSONResponse(status_code=status_code, content=payload)


def _run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)


# ---------------------------------------------------------------------------
# Domain adapters — request → configuration; summary → frozen dataclass
# ---------------------------------------------------------------------------


def _config_from_request(req: SimulationCreateRequest) -> SimulationConfiguration:
    bounds = DomainBounds(
        x_min=float(req.domain_bounds.x_min),
        y_min=float(req.domain_bounds.y_min),
        z_min=float(req.domain_bounds.z_min),
        x_max=float(req.domain_bounds.x_max),
        y_max=float(req.domain_bounds.y_max),
        z_max=float(req.domain_bounds.z_max),
    )
    rock = RockMassConfiguration(
        rock_unit_id=req.rock_mass.rock_unit_id,
        density_kg_m3=req.rock_mass.density_kg_m3,
        ucs_mpa=req.rock_mass.ucs_mpa,
        attenuation_coefficient_1_m=req.rock_mass.attenuation_coefficient_1_m,
        wave_velocity_m_s=req.rock_mass.wave_velocity_m_s,
        anisotropy_mode=req.rock_mass.anisotropy_mode,
        anisotropy_tensor=(
            tuple(tuple(float(c) for c in row) for row in req.rock_mass.anisotropy_tensor)
            if req.rock_mass.anisotropy_tensor
            else None
        ),
        source=req.rock_mass.source,
        status=req.rock_mass.status,
        assumptions=tuple(req.rock_mass.assumptions),
        warnings=tuple(req.rock_mass.warnings),
    )
    return SimulationConfiguration(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version=req.geometry_configuration_version,
        user_confirmed=req.user_confirmed,
        voxel_size_m=req.voxel_size_m,
        domain_bounds=bounds,
        energy_mode=req.energy_mode,
        temporal_mode=req.temporal_mode,
        anisotropy_mode=req.anisotropy_mode,
        kernel_type=req.kernel_type,
        attenuation_coefficient_1_m=req.attenuation_coefficient_1_m,
        regularization_radius_m=req.regularization_radius_m,
        support_radius_m=req.support_radius_m,
        coupling_efficiency=req.coupling_efficiency,
        propagation_velocity_m_s=req.propagation_velocity_m_s,
        propagation_velocity_source=req.propagation_velocity_source,
        pulse_sigma_s=req.pulse_sigma_s,
        rock_mass=rock,
    )


def _plan_slice_from_dict(p: Dict[str, Any]) -> PlanSlice:
    """Rebuild a :class:`PlanSlice` from its ``to_dict()`` representation.

    Every Falla-4 field is forwarded explicitly with an empty default so
    the XLSX export keeps working with legacy summaries that pre-date
    the Falla-4 schema (Brecha 4 + Brecha 6 back-compat). Legacy
    ``max_value`` / ``mean_value`` / ``represented_energy_j`` aliases are
    preserved via the dataclass ``__post_init__`` whenever the modern
    ``max`` / ``mean`` fields are non-zero.
    """
    return PlanSlice(
        elevation_m=float(p.get("elevation_m", 0.0)),
        unit=str(p.get("unit", "J")),
        field_type=str(p.get("field_type", "energy_j")),
        grid_shape=tuple(int(v) for v in (p.get("grid_shape") or (0, 0))),
        values=tuple(float(v) for v in (p.get("values") or ())),
        x_coordinates_m=tuple(float(v) for v in (p.get("x_coordinates_m") or ())),
        y_coordinates_m=tuple(float(v) for v in (p.get("y_coordinates_m") or ())),
        valid_mask=tuple(bool(v) for v in (p.get("valid_mask") or ())),
        min=float(p.get("min", 0.0)),
        max=float(p.get("max", 0.0)),
        mean=float(p.get("mean", 0.0)),
        percentiles=dict(p.get("percentiles") or {}),
        source_holes_projection=tuple(
            dict(h) for h in (p.get("source_holes_projection") or ())
        ),
        data_sha256=str(p.get("data_sha256", "")),
        max_value=float(p.get("max_value", 0.0)),
        mean_value=float(p.get("mean_value", 0.0)),
        represented_energy_j=float(p.get("represented_energy_j", 0.0)),
    )


def _section_slice_from_dict(s: Dict[str, Any]) -> SectionSlice:
    """Rebuild a :class:`SectionSlice` from its ``to_dict()`` representation.

    Same back-compat strategy as :func:`_plan_slice_from_dict`. Defaults
    are explicit so a missing Falla-4 field never crashes the XLSX export.
    """
    return SectionSlice(
        axis=str(s.get("axis", "x")),
        coordinate_m=float(s.get("coordinate_m", 0.0)),
        unit=str(s.get("unit", "J")),
        field_type=str(s.get("field_type", "energy_j")),
        grid_shape=tuple(int(v) for v in (s.get("grid_shape") or (0, 0))),
        values=tuple(float(v) for v in (s.get("values") or ())),
        along_coordinates_m=tuple(float(v) for v in (s.get("along_coordinates_m") or ())),
        vertical_coordinates_m=tuple(
            float(v) for v in (s.get("vertical_coordinates_m") or ())
        ),
        valid_mask=tuple(bool(v) for v in (s.get("valid_mask") or ())),
        min=float(s.get("min", 0.0)),
        max=float(s.get("max", 0.0)),
        mean=float(s.get("mean", 0.0)),
        percentiles=dict(s.get("percentiles") or {}),
        source_holes_projection=tuple(
            dict(h) for h in (s.get("source_holes_projection") or ())
        ),
        data_sha256=str(s.get("data_sha256", "")),
        max_value=float(s.get("max_value", 0.0)),
        mean_value=float(s.get("mean_value", 0.0)),
        represented_energy_j=float(s.get("represented_energy_j", 0.0)),
    )


def _parse_xyz(raw: str, field_name: str) -> np.ndarray:
    """Parse ``"x,y,z"`` into a ``(3,)`` float64 array.

    Returns a structured HTTP 422 ``INVALID_PROFILE_PARAMS`` on any
    malformation (wrong arity, non-numeric token, NaN/inf).
    """
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise _structured_error(
            422,
            f"{field_name} debe tener exactamente 3 coordenadas separadas por comas.",
            error_code="INVALID_PROFILE_PARAMS",
            details={"field": field_name, "value": raw, "expected": "x,y,z"},
        )
    try:
        coords = np.array([float(p) for p in parts], dtype=np.float64)
    except ValueError:
        raise _structured_error(
            422,
            f"{field_name} contiene valores no numéricos.",
            error_code="INVALID_PROFILE_PARAMS",
            details={"field": field_name, "value": raw},
        )
    if not np.all(np.isfinite(coords)):
        raise _structured_error(
            422,
            f"{field_name} contiene NaN/inf.",
            error_code="INVALID_PROFILE_PARAMS",
            details={"field": field_name, "value": raw},
        )
    return coords


# ---------------------------------------------------------------------------
# POST /blast/simulations
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_class=JSONResponse,
    summary="Crear y ejecutar una simulación de energía de tronadura",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": SimulationCreateRequest.model_json_schema(
                        ref_template="#/components/schemas/{model}",
                    ),
                }
            },
        }
    },
)
async def create_simulation(request: Request) -> JSONResponse:
    """Create and run a blast energy simulation.

    Manual body parsing via ``SimulationCreateRequest.model_validate_json``
    lets the router convert Pydantic ``extra_forbidden`` errors into a
    structured ``UNKNOWN_FIELD`` 422 response **without** installing an
    app-level exception handler — the router stays self-contained
    (Brecha 3.1).

    The simulation consumes the canonical Fase 1 ``accepted_rows``
    persisted on the session — rejected rows are NEVER passed to the
    engine. Configuration errors surface as HTTP 400 with structured
    diagnostics; engine blocking errors surface as HTTP 422 with
    ``error_code="SIMULATION_BLOCKED"`` (Falla 7) and DO NOT write the
    NPZ artifact, the JSON summary or insert a SQLite row.
    """
    body_bytes = await request.body()
    try:
        req = SimulationCreateRequest.model_validate_json(body_bytes or b"null")
    except ValidationError as exc:
        raise _translate_validation_error(exc)

    # 1. Validate the configuration contract (HTTP 400 — caller-side error).
    try:
        config = _config_from_request(req)
        config.validate()
    except SimulationConfigurationError as exc:
        raise _structured_error(400, exc, error_code=exc.error_code, details=exc.details)

    # 2. Resolve the session + canonical accepted rows.
    db.get_or_create_session(req.session_id)
    settings = db.get_settings(req.session_id) or {}
    accepted_rows = settings.get("accepted_rows") or settings.get("blast_holes") or []
    if not accepted_rows:
        raise _structured_error(
            400,
            "La sesión no tiene filas aceptadas de Fase 1.",
            error_code="NO_ACCEPTED_ROWS",
            details={"session_id": req.session_id},
        )

    # 3. Run the engine on a worker thread.
    def _run():
        result = run_simulation(
            accepted_rows=accepted_rows,
            configuration=config,
            segments_per_hole=req.segments_per_hole,
        )

        # Falla 7 — persistence gate. Blocked simulations MUST NOT
        # produce an NPZ artifact, a JSON summary or a SQLite row.
        if not should_persist(result):
            logger.info(
                "Simulation %s blocked with %d error(es); skipping persistence",
                result.simulation_id,
                len(result.blocking_errors),
            )
            return result

        # 4. Persist the NPZ + JSON atomically.
        result, npz_path, sha, _summary_path = write_atomic_simulation(
            result=result,
            accepted_rows=accepted_rows,
            configuration=config,
            segments_per_hole=req.segments_per_hole,
        )

        # 5. Attach plan / section slices when requested.
        # V5-01: consume the CANONICAL field_arrays directly — no
        # recalculation via compute_field_arrays.
        if req.plan_elevations or req.section_coordinates:
            if result.field_arrays is None:
                raise _structured_error(
                    500,
                    "Canonical field_arrays missing from result",
                    error_code="CANONICAL_RESULT_MISSING",
                )
            arrays = result.field_arrays
            section_coords = [
                (axis, coord) for axis, coord in req.section_coordinates
            ]
            result = attach_slices_to_result(
                result,
                energy_total_flat=arrays["energy_total"],
                plan_elevations=req.plan_elevations,
                section_coords=section_coords,
            )

        # 6. Persist the SQLite metadata row.
        db.save_blast_simulation(
            session_id=req.session_id,
            simulation_id=result.simulation_id,
            configuration=config.to_dict(),
            summary=result.to_dict(),
            npz_path=result.energy_field.npz_path,
            npz_sha256=result.grid_metadata.npz_sha256,
            engine_version=result.engine_version,
            energy_mode=result.processing_summary.energy_mode,
            temporal_status=result.processing_summary.temporal_status,
        )
        return result

    try:
        result = await _run_in_executor(_run)
    except SimulationConfigurationError as exc:
        raise _structured_error(400, exc, error_code=exc.error_code, details=exc.details)
    except PersistenceError as exc:
        raise _structured_error(500, exc, error_code="PERSISTENCE_ERROR")
    except Exception as exc:
        logger.exception("Simulation failed")
        raise _structured_error(500, exc, error_code="SIMULATION_FAILED")

    # Falla 7 — blocked simulation: 422 + SIMULATION_BLOCKED, no NPZ,
    # no SQLite row. We surface the structured diagnostic + a subset of
    # the result metadata under ``detail.details`` so the caller can
    # react without a second round-trip to ``GET /summary``.
    if result.blocking_errors:
        raise _structured_error(
            422,
            "Simulation rechazada por el motor.",
            error_code="SIMULATION_BLOCKED",
            details={
                "simulation_id": result.simulation_id,
                "persisted": False,
                "blocking_errors": list(result.blocking_errors),
                "warnings": list(result.warnings),
                "engine_version": result.engine_version,
                "configuration": result.configuration,
                "summary": result.processing_summary.to_dict(),
                "grid_metadata": result.grid_metadata.to_dict(),
                "energy_field": result.energy_field.to_dict(),
                "provenance": result.provenance.to_dict(),
            },
        )

    body = SimulationCreateResponse(
        simulation_id=result.simulation_id,
        persisted=True,
        summary=result.processing_summary.to_dict(),
        configuration=result.configuration,
        grid_metadata=result.grid_metadata.to_dict(),
        energy_field=result.energy_field.to_dict(),
        plan_slices=[s.to_dict() for s in result.plan_slices],
        section_slices=[s.to_dict() for s in result.section_slices],
        warnings=list(result.warnings),
        blocking_errors=list(result.blocking_errors),
        provenance=result.provenance.to_dict(),
        npz_sha256=result.grid_metadata.npz_sha256,
    ).model_dump()
    return _json_or_gzip(body, status_code=200)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}            (legacy alias of /summary)
# ---------------------------------------------------------------------------


@router.get(
    "/{simulation_id}",
    response_class=JSONResponse,
    summary="Obtener el resumen canónico de la simulación (alias)",
)
async def get_simulation(simulation_id: str) -> Response:
    """Return the canonical ``SimulationResult.to_dict()`` payload.

    Kept as a backwards-compatible alias of ``GET /summary`` — the
    maintainer's Streamlit app reads this endpoint.
    """
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(
            404,
            f"Simulation {simulation_id} not found",
            error_code="SIMULATION_NOT_FOUND",
            details={"simulation_id": simulation_id},
        )
    return _json_or_gzip(row["summary"], status_code=200)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/summary
# ---------------------------------------------------------------------------


@router.get(
    "/{simulation_id}/summary",
    response_class=JSONResponse,
    summary="Obtener el resumen canónico (SimulationResult.to_dict())",
)
async def get_simulation_summary(simulation_id: str) -> Response:
    """Return the canonical summary as a JSON document.

    Useful for cross-layer tests that need to verify the full canonical
    payload (configuration, slices, diagnostics, provenance) without
    re-running the engine. The body is the persisted
    ``SimulationResult.to_dict()`` exactly as it was written to SQLite
    by :func:`api.database.save_blast_simulation`.
    """
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(
            404,
            f"Simulation {simulation_id} not found",
            error_code="SIMULATION_NOT_FOUND",
            details={"simulation_id": simulation_id},
        )
    return _json_or_gzip(row["summary"], status_code=200)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/profile
# ---------------------------------------------------------------------------


@router.get(
    "/{simulation_id}/profile",
    response_class=JSONResponse,
    summary="Perfil interpolado entre dos puntos a lo largo del campo 3D",
)
async def get_simulation_profile(
    simulation_id: str,
    start_xyz: str = Query(
        ...,
        description='Coordenada de inicio, formato "x,y,z" (metros).',
    ),
    end_xyz: str = Query(
        ...,
        description='Coordenada de fin, formato "x,y,z" (metros).',
    ),
    n_samples: int = Query(
        200,
        ge=2,
        le=10_000,
        description="Número de muestras a lo largo del segmento.",
    ),
) -> Response:
    """Interpolate ``energy_total`` along the segment ``start_xyz → end_xyz``.

    The endpoint loads the persisted NPZ (SHA-256 verified against
    ``row.npz_sha256``), reconstructs the voxel grid from the summary
    metadata and delegates the actual interpolation to
    :func:`core.blast_simulation.profile_slice`. **No physics runs in
    this router** — geometry, voxel-centre resolution and the
    dimensionally-correct energy sampling all live in the core.

    Returns the cumulative distance, the sampled value at each point,
    summary statistics and the SHA-256 of the resulting profile (the
    canonical audit trail for the derived data).
    """
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(
            404,
            f"Simulation {simulation_id} not found",
            error_code="SIMULATION_NOT_FOUND",
            details={"simulation_id": simulation_id},
        )

    npz_path = row.get("npz_path") or ""
    if not npz_path:
        raise _structured_error(
            404,
            "Simulation has no NPZ artifact (was it blocked?).",
            error_code="NO_ARTIFACT",
            details={"simulation_id": simulation_id},
        )
    npz_p = Path(npz_path)
    if not npz_p.exists():
        raise _structured_error(
            404,
            "NPZ artifact not found on disk.",
            error_code="NO_ARTIFACT",
            details={"simulation_id": simulation_id, "expected_path": npz_path},
        )

    start = _parse_xyz(start_xyz, "start_xyz")
    end = _parse_xyz(end_xyz, "end_xyz")

    direction = end - start
    length_m = float(np.linalg.norm(direction))
    if not math.isfinite(length_m) or length_m <= 0.0:
        raise _structured_error(
            422,
            "start_xyz y end_xyz deben ser puntos distintos.",
            error_code="INVALID_PROFILE_PARAMS",
            details={
                "start_xyz": start.tolist(),
                "end_xyz": end.tolist(),
                "length_m": length_m,
            },
        )

    # Load the NPZ artifact with SHA-256 verification (Falla 7).
    expected_sha = row.get("npz_sha256") or None
    try:
        arrays, metadata, actual_sha = read_npz_artifact(
            npz_path, expected_sha256=expected_sha,
        )
    except PersistenceError as exc:
        raise _structured_error(
            500,
            exc,
            error_code="NPZ_READ_FAILED",
            details={
                "simulation_id": simulation_id,
                "expected_sha256": expected_sha,
                "npz_path": npz_path,
            },
        )

    # Rebuild the voxel grid spec from the persisted summary metadata.
    grid_meta = row["summary"].get("grid_metadata") or {}
    bounds_dict = grid_meta.get("bounds") or {}
    try:
        bounds = DomainBounds(
            x_min=float(bounds_dict["x_min"]),
            y_min=float(bounds_dict["y_min"]),
            z_min=float(bounds_dict["z_min"]),
            x_max=float(bounds_dict["x_max"]),
            y_max=float(bounds_dict["y_max"]),
            z_max=float(bounds_dict["z_max"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _structured_error(
            500,
            f"Persisted grid bounds are malformed: {exc}",
            error_code="GRID_METADATA_INVALID",
            details={"grid_metadata": grid_meta},
        )
    voxel_size_m = float(grid_meta.get("voxel_size_m", 1.0))
    grid = VoxelGridSpecification(voxel_size_m=voxel_size_m, bounds=bounds)

    # Delegate to the canonical core function — no physics in this router.
    energy_total = np.asarray(
        arrays.get("energy_total", np.zeros(0, dtype=np.float32)),
        dtype=np.float64,
    )
    energy_unit = str(metadata.get("energy_unit", "J"))
    profile = profile_slice(
        energy_total_flat=energy_total,
        grid=grid,
        start_xyz=(float(start[0]), float(start[1]), float(start[2])),
        end_xyz=(float(end[0]), float(end[1]), float(end[2])),
        n_samples=n_samples,
        energy_unit=energy_unit,
        field_type="energy_j",
    )

    body = ProfileResponse(
        simulation_id=simulation_id,
        field_type=str(profile.get("field_type", "energy_j")),
        unit=str(profile.get("unit", energy_unit)),
        distances_m=[float(v) for v in profile.get("distances_m", ())],
        values=[float(v) for v in profile.get("values", ())],
        min=float(profile.get("min", 0.0)),
        max=float(profile.get("max", 0.0)),
        mean=float(profile.get("mean", 0.0)),
        start_xyz=[float(v) for v in start.tolist()],
        end_xyz=[float(v) for v in end.tolist()],
        n_samples=int(profile.get("n_samples", n_samples)),
        data_sha256=str(profile.get("data_sha256", actual_sha)),
    ).model_dump()
    return _json_or_gzip(body, status_code=200)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/plan
# ---------------------------------------------------------------------------


@router.get(
    "/{simulation_id}/plan",
    response_class=JSONResponse,
    summary="Slice horizontal — Falla 4: matriz 2D completa",
)
async def get_plan_slice(
    simulation_id: str,
    elevation: float = Query(..., description="Elevación (m) para el corte horizontal."),
) -> Response:
    """Return the plan slice whose elevation is closest to ``elevation``.

    The full Falla-4 payload is returned: ``values`` (flattened 2D
    matrix), ``x_coordinates_m``, ``y_coordinates_m``, ``valid_mask``,
    ``percentiles``, ``source_holes_projection`` and ``data_sha256`` —
    never only shape + aggregates.
    """
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(
            404,
            f"Simulation {simulation_id} not found",
            error_code="SIMULATION_NOT_FOUND",
            details={"simulation_id": simulation_id},
        )
    summary = row["summary"]
    plans = summary.get("plan_slices") or []
    if not plans:
        raise _structured_error(
            404,
            "No plan slices were computed for this simulation",
            error_code="NO_PLAN_SLICES",
            details={"simulation_id": simulation_id},
        )
    best = min(plans, key=lambda p: abs(float(p["elevation_m"]) - elevation))
    return _json_or_gzip(best, status_code=200)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/section
# ---------------------------------------------------------------------------


@router.get(
    "/{simulation_id}/section",
    response_class=JSONResponse,
    summary="Slice vertical — Falla 4: matriz 2D completa",
)
async def get_section_slice(
    simulation_id: str,
    axis: str = Query(..., description="'x' o 'y'"),
    coordinate: float = Query(..., description="Coordenada (m) sobre el eje."),
) -> Response:
    """Return the section slice nearest to ``coordinate`` along ``axis``.

    Same Falla-4 payload as ``/plan``: ``values``, ``along_coordinates_m``,
    ``vertical_coordinates_m``, ``valid_mask``, ``percentiles``,
    ``source_holes_projection`` and ``data_sha256``.
    """
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(
            404,
            f"Simulation {simulation_id} not found",
            error_code="SIMULATION_NOT_FOUND",
            details={"simulation_id": simulation_id},
        )
    summary = row["summary"]
    sections = summary.get("section_slices") or []
    if not sections:
        raise _structured_error(
            404,
            "No section slices were computed for this simulation",
            error_code="NO_SECTION_SLICES",
            details={"simulation_id": simulation_id},
        )
    candidates = [s for s in sections if s["axis"] == axis]
    if not candidates:
        raise _structured_error(
            404,
            f"No sections along axis {axis!r}",
            error_code="AXIS_NOT_FOUND",
            details={
                "requested_axis": axis,
                "available_axes": sorted({s["axis"] for s in sections}),
            },
        )
    best = min(
        candidates,
        key=lambda s: abs(float(s["coordinate_m"]) - coordinate),
    )
    return _json_or_gzip(best, status_code=200)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/export
# ---------------------------------------------------------------------------


@router.get("/{simulation_id}/export")
async def export_simulation(
    simulation_id: str,
    fmt: str = Query("xlsx", pattern="^(xlsx|npz|json|json_gz)$"),
):
    """Export the simulation result.

    * ``fmt=xlsx``    — rebuild ``SimulationResult`` from the persisted
      summary (Falla 4: every new field forwarded to ``PlanSlice`` /
      ``SectionSlice`` with empty defaults for legacy summaries) and
      write the canonical workbook.
    * ``fmt=npz``     — binary NPZ artifact (SHA-256 protected).
    * ``fmt=json``    — canonical ``SimulationResult.to_dict()`` JSON.
      Auto-gzipped when the payload exceeds 1 MB.
    * ``fmt=json_gz`` — always-gzipped canonical JSON.
    """
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(
            404,
            f"Simulation {simulation_id} not found",
            error_code="SIMULATION_NOT_FOUND",
            details={"simulation_id": simulation_id},
        )
    npz_path = row.get("npz_path") or ""

    if fmt == "npz":
        if not npz_path:
            raise _structured_error(
                404,
                "NPZ artifact path missing (was the simulation blocked?)",
                error_code="NO_ARTIFACT",
                details={"simulation_id": simulation_id},
            )
        return FileResponse(
            npz_path,
            media_type="application/octet-stream",
            filename=f"{simulation_id}_energy_field.npz",
        )

    if fmt == "json":
        return _json_or_gzip(row["summary"], status_code=200)

    if fmt == "json_gz":
        body_bytes = json.dumps(
            row["summary"], default=str, ensure_ascii=False
        ).encode("utf-8")
        return Response(
            content=gzip.compress(body_bytes),
            media_type="application/octet-stream",
            headers={
                "X-Payload-Encoding": "gzip",
                "X-Original-Size": str(len(body_bytes)),
                "Content-Disposition": (
                    f'attachment; filename="{simulation_id}_summary.json.gz"'
                ),
            },
        )

    # fmt == "xlsx" — rebuild a SimulationResult from the persisted summary.
    from core.blast_simulation.contracts import (
        GridMetadata,
        ProcessingSummary,
        SimulationProvenance,
        SimulationResult,
        SimulationSourceSummary,
        VoxelEnergyField,
    )

    summary_dict = row["summary"]

    # Tolerate a missing grid_metadata (should not happen for successful sims).
    grid_meta_dict = summary_dict.get("grid_metadata") or {}
    bounds_dict = grid_meta_dict.get("bounds") or {}
    grid_meta = GridMetadata(
        shape=tuple(int(v) for v in (grid_meta_dict.get("shape") or (0, 0, 0))),
        voxel_size_m=float(grid_meta_dict.get("voxel_size_m", 1.0)),
        bounds=DomainBounds(
            x_min=float(bounds_dict.get("x_min", 0.0)),
            y_min=float(bounds_dict.get("y_min", 0.0)),
            z_min=float(bounds_dict.get("z_min", 0.0)),
            x_max=float(bounds_dict.get("x_max", 0.0)),
            y_max=float(bounds_dict.get("y_max", 0.0)),
            z_max=float(bounds_dict.get("z_max", 0.0)),
        ),
        axes_order=str(grid_meta_dict.get("axes_order", "xyz")),
        energy_unit=str(grid_meta_dict.get("energy_unit", "J")),
        dtype=str(grid_meta_dict.get("dtype", "float32")),
        voxel_count=int(grid_meta_dict.get("voxel_count", 0)),
        voxel_volume_m3=float(grid_meta_dict.get("voxel_volume_m3", 0.0)),
        npz_sha256=str(grid_meta_dict.get("npz_sha256", "")),
        created_at=str(grid_meta_dict.get("created_at", "")),
    )

    src_dict = summary_dict.get("source_summary") or {}
    src = SimulationSourceSummary(
        source_rows=int(src_dict.get("source_rows", 0)),
        accepted_holes=int(src_dict.get("accepted_holes", 0)),
        rejected_holes=int(src_dict.get("rejected_holes", 0)),
        charge_segments=int(src_dict.get("charge_segments", 0)),
        valid_sources=int(src_dict.get("valid_sources", 0)),
        invalid_sources=int(src_dict.get("invalid_sources", 0)),
        voxel_count=int(src_dict.get("voxel_count", 0)),
        active_voxels=int(src_dict.get("active_voxels", 0)),
        represented_energy_j=float(src_dict.get("represented_energy_j", 0.0)),
        outside_domain_energy_j=float(src_dict.get("outside_domain_energy_j", 0.0)),
        warning_count=int(src_dict.get("warning_count", 0)),
        blocking_error_count=int(src_dict.get("blocking_error_count", 0)),
    )

    ef_dict = summary_dict.get("energy_field") or {}
    energy_field = VoxelEnergyField(
        grid=grid_meta,
        represented_energy_j=float(ef_dict.get("represented_energy_j", 0.0)),
        outside_domain_energy_j=float(ef_dict.get("outside_domain_energy_j", 0.0)),
        total_coupled_energy_j=float(ef_dict.get("total_coupled_energy_j", 0.0)),
        fraction_represented=float(ef_dict.get("fraction_represented", 0.0)),
        active_voxels=int(ef_dict.get("active_voxels", 0)),
        max_energy_j=float(ef_dict.get("max_energy_j", 0.0)),
        mean_energy_j_active=float(ef_dict.get("mean_energy_j_active", 0.0)),
        npz_path=str(ef_dict.get("npz_path", "")),
        energy_unit=str(ef_dict.get("energy_unit", "J")),
    )

    ps_dict = summary_dict.get("processing_summary") or {}
    processing = ProcessingSummary(
        accepted_holes=int(ps_dict.get("accepted_holes", 0)),
        charge_segments=int(ps_dict.get("charge_segments", 0)),
        valid_sources=int(ps_dict.get("valid_sources", 0)),
        invalid_sources=int(ps_dict.get("invalid_sources", 0)),
        voxel_count=int(ps_dict.get("voxel_count", 0)),
        active_voxels=int(ps_dict.get("active_voxels", 0)),
        represented_energy_j=float(ps_dict.get("represented_energy_j", 0.0)),
        outside_domain_energy_j=float(ps_dict.get("outside_domain_energy_j", 0.0)),
        total_coupled_energy_j=float(ps_dict.get("total_coupled_energy_j", 0.0)),
        fraction_represented=float(ps_dict.get("fraction_represented", 0.0)),
        warning_records=int(ps_dict.get("warning_records", 0)),
        blocking_error_records=int(ps_dict.get("blocking_error_records", 0)),
        temporal_status=str(ps_dict.get("temporal_status", "NOT_AVAILABLE")),
        energy_mode=str(ps_dict.get("energy_mode", "RELATIVE")),
    )

    prov_dict = summary_dict.get("provenance") or {}
    provenance = SimulationProvenance(
        engine_version=str(prov_dict.get("engine_version", "")),
        simulation_configuration_version=str(
            prov_dict.get("simulation_configuration_version", "")
        ),
        geometry_configuration_version=str(
            prov_dict.get("geometry_configuration_version", "")
        ),
        explosive_registry_source=str(prov_dict.get("explosive_registry_source", "")),
        explosive_products_used=tuple(prov_dict.get("explosive_products_used") or ()),
        rock_mass_source=str(prov_dict.get("rock_mass_source", "")),
        propagation_velocity_source=str(prov_dict.get("propagation_velocity_source", "")),
        assumptions=tuple(prov_dict.get("assumptions") or ()),
        warnings=tuple(prov_dict.get("warnings") or ()),
        accepted_rows_hash=str(prov_dict.get("accepted_rows_hash", "")),
    )

    plan_dicts = list(summary_dict.get("plan_slices") or ())
    section_dicts = list(summary_dict.get("section_slices") or ())
    result = SimulationResult(
        simulation_id=simulation_id,
        configuration=summary_dict.get("configuration") or {},
        grid_metadata=grid_meta,
        source_summary=src,
        energy_field=energy_field,
        plan_slices=tuple(_plan_slice_from_dict(p) for p in plan_dicts),
        section_slices=tuple(_section_slice_from_dict(s) for s in section_dicts),
        processing_summary=processing,
        warnings=tuple(summary_dict.get("warnings") or ()),
        blocking_errors=tuple(summary_dict.get("blocking_errors") or ()),
        spatial_diagnostics=summary_dict.get("spatial_diagnostics") or {},
        temporal_diagnostics=summary_dict.get("temporal_diagnostics") or {},
        provenance=provenance,
        created_at=str(summary_dict.get("created_at", "")),
        engine_version=str(summary_dict.get("engine_version", "")),
    )

    out = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    out.close()
    try:
        export_simulation_xlsx(result, out.name)
        return FileResponse(
            out.name,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            filename=f"{simulation_id}_simulation.xlsx",
        )
    except Exception as exc:
        Path(out.name).unlink(missing_ok=True)
        logger.exception("XLSX export failed for %s", simulation_id)
        raise _structured_error(
            500, exc,
            error_code="XLSX_EXPORT_FAILED",
            details={"simulation_id": simulation_id},
        )