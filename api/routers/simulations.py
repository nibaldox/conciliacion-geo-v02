"""Phase 2 — blast energy simulation endpoints.

Endpoints (spec §9):

    POST /api/v1/blast/simulations
    GET  /api/v1/blast/simulations/{simulation_id}
    GET  /api/v1/blast/simulations/{simulation_id}/plan
    GET  /api/v1/blast/simulations/{simulation_id}/section
    GET  /api/v1/blast/simulations/{simulation_id}/export

The POST endpoint is the only one that touches the engine. It:

1. Receives an unambiguous reference to the canonical Fase 1 result
   (``session_id`` → reads ``accepted_rows`` from SQLite).
2. Validates the :class:`SimulationConfiguration` contract.
3. Runs the engine on a worker thread.
4. Persists the NPZ artifact + JSON summary + SQLite metadata row.
5. Returns the canonical summary + diagnostics + slice links.

HTTP 400/422 errors carry the structured diagnostics from
:class:`SimulationConfigurationError` so the UI can render precise
guidance (never a bare string).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from core.blast_simulation import (
    AnisotropyMode,
    DomainBounds,
    EnergyMode,
    KernelType,
    PersistenceError,
    RockMassConfiguration,
    SIMULATION_CONFIGURATION_VERSION,
    SimulationConfiguration,
    SimulationConfigurationError,
    TemporalMode,
    attach_slices_to_result,
    compute_field_arrays,
    export_simulation_xlsx,
    npz_path_for,
    read_npz_artifact,
    run_simulation,
    should_persist,
    write_atomic_simulation,
    write_summary_json,
)
from core.config import SIMULATION

import api.database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/blast/simulations", tags=["blast-simulation"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RockMassSchema(BaseModel):
    rock_unit_id: str = ""
    density_kg_m3: Optional[float] = None
    ucs_mpa: Optional[float] = None
    attenuation_coefficient_1_m: Optional[float] = None
    wave_velocity_m_s: Optional[float] = None
    anisotropy_mode: str = AnisotropyMode.ISOTROPIC
    anisotropy_tensor: Optional[List[List[float]]] = None
    source: str = ""
    status: str = "MISSING"
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class SimulationCreateRequest(BaseModel):
    """Body for ``POST /blast/simulations``.

    Every physical decision must be supplied explicitly — there are no
    silent defaults. The geometry is consumed from the Fase 1
    ``accepted_rows`` persisted on the session.
    """
    session_id: str
    geometry_configuration_version: str
    user_confirmed: bool

    voxel_size_m: float
    domain_bounds: Dict[str, float]

    energy_mode: str
    temporal_mode: str
    anisotropy_mode: str

    kernel_type: str = KernelType.EXPONENTIAL_INVERSE_SQUARE
    attenuation_coefficient_1_m: float
    regularization_radius_m: float
    coupling_efficiency: float

    propagation_velocity_m_s: Optional[float] = None
    propagation_velocity_source: str = ""
    pulse_sigma_s: Optional[float] = None

    segments_per_hole: int = 8
    plan_elevations: List[float] = Field(default_factory=list)
    section_coordinates: List[List[Any]] = Field(default_factory=list)  # [[axis, coord], ...]

    rock_mass: RockMassSchema = Field(default_factory=RockMassSchema)


class SimulationCreateResponse(BaseModel):
    simulation_id: str
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_from_request(req: SimulationCreateRequest) -> SimulationConfiguration:
    bounds = DomainBounds(
        x_min=float(req.domain_bounds["x_min"]),
        y_min=float(req.domain_bounds["y_min"]),
        z_min=float(req.domain_bounds["z_min"]),
        x_max=float(req.domain_bounds["x_max"]),
        y_max=float(req.domain_bounds["y_max"]),
        z_max=float(req.domain_bounds["z_max"]),
    )
    rock = RockMassConfiguration(
        rock_unit_id=req.rock_mass.rock_unit_id,
        density_kg_m3=req.rock_mass.density_kg_m3,
        ucs_mpa=req.rock_mass.ucs_mpa,
        attenuation_coefficient_1_m=req.rock_mass.attenuation_coefficient_1_m,
        wave_velocity_m_s=req.rock_mass.wave_velocity_m_s,
        anisotropy_mode=req.rock_mass.anisotropy_mode,
        anisotropy_tensor=(
            tuple(tuple(r) for r in req.rock_mass.anisotropy_tensor)
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
        coupling_efficiency=req.coupling_efficiency,
        propagation_velocity_m_s=req.propagation_velocity_m_s,
        propagation_velocity_source=req.propagation_velocity_source,
        pulse_sigma_s=req.pulse_sigma_s,
        rock_mass=rock,
    )


def _run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)


def _structured_error(status: int, exc: Exception | str, *, error_code: str, details: dict | None = None) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "error_code": error_code,
            "message": str(exc),
            "details": details or {},
        },
    )


# ---------------------------------------------------------------------------
# POST /blast/simulations
# ---------------------------------------------------------------------------


@router.post("", response_class=JSONResponse)
async def create_simulation(req: SimulationCreateRequest) -> JSONResponse:
    """Create and run a blast energy simulation.

    The simulation consumes the canonical Fase 1 ``accepted_rows``
    persisted on the session — rejected rows are NEVER passed to the
    engine. Configuration errors surface as HTTP 400 with structured
    diagnostics; engine resource ceilings surface as HTTP 422.
    """
    # 1. Validate the configuration contract.
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
        # 4. Persist the NPZ artifact + JSON summary ONLY when the
        # simulation is not blocked (Falla 7). A blocked simulation
        # does not produce an artifact on disk; the SQLite metadata row
        # still records the attempt so the UI can show the diagnostics.
        if should_persist(result):
            result, npz_path, sha, _summary_path = write_atomic_simulation(
                result=result,
                accepted_rows=accepted_rows,
                configuration=config,
                segments_per_hole=req.segments_per_hole,
            )
            # 5. Attach plan / section slices if requested.
            if req.plan_elevations or req.section_coordinates:
                arrays = compute_field_arrays(
                    result=result,
                    accepted_rows=accepted_rows,
                    configuration=config,
                    segments_per_hole=req.segments_per_hole,
                )
                section_coords = [(str(c[0]), float(c[1])) for c in req.section_coordinates]
                result = attach_slices_to_result(
                    result,
                    energy_total_flat=arrays["energy_total"],
                    plan_elevations=req.plan_elevations,
                    section_coords=section_coords,
                )
        write_summary_json(result=result)
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
        raise _structured_error(422, exc, error_code=exc.error_code, details=exc.details)
    except PersistenceError as exc:
        raise _structured_error(500, exc, error_code="PERSISTENCE_ERROR")
    except Exception as exc:
        logger.exception("Simulation failed")
        raise _structured_error(500, exc, error_code="SIMULATION_FAILED")

    body = SimulationCreateResponse(
        simulation_id=result.simulation_id,
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
    )
    # 422 when blocking errors exist (e.g. ABSOLUTE mode with unknown explosive).
    status = 422 if result.blocking_errors else 200
    return JSONResponse(status_code=status, content=body.model_dump())


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}
# ---------------------------------------------------------------------------


@router.get("/{simulation_id}")
async def get_simulation(simulation_id: str) -> JSONResponse:
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(
            404, f"Simulation {simulation_id} not found",
            error_code="SIMULATION_NOT_FOUND",
        )
    return JSONResponse(status_code=200, content=row["summary"])


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/plan
# ---------------------------------------------------------------------------


@router.get("/{simulation_id}/plan")
async def get_plan_slice(
    simulation_id: str,
    elevation: float = Query(..., description="Elevation (m) for the plan slice"),
) -> JSONResponse:
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(404, "not found", error_code="SIMULATION_NOT_FOUND")
    summary = row["summary"]
    plans = summary.get("plan_slices") or []
    if not plans:
        raise _structured_error(
            404, "No plan slices were computed for this simulation",
            error_code="NO_PLAN_SLICES",
        )
    # Return the slice whose elevation is closest to the requested one.
    best = min(plans, key=lambda p: abs(float(p["elevation_m"]) - elevation))
    return JSONResponse(status_code=200, content=best)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/section
# ---------------------------------------------------------------------------


@router.get("/{simulation_id}/section")
async def get_section_slice(
    simulation_id: str,
    axis: str = Query(..., description="'x' or 'y'"),
    coordinate: float = Query(..., description="Coordinate (m) along the axis"),
) -> JSONResponse:
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(404, "not found", error_code="SIMULATION_NOT_FOUND")
    summary = row["summary"]
    sections = summary.get("section_slices") or []
    if not sections:
        raise _structured_error(
            404, "No section slices were computed for this simulation",
            error_code="NO_SECTION_SLICES",
        )
    candidates = [s for s in sections if s["axis"] == axis]
    if not candidates:
        raise _structured_error(
            404, f"No sections along axis {axis!r}",
            error_code="AXIS_NOT_FOUND",
            details={"requested_axis": axis, "available_axes": list({s["axis"] for s in sections})},
        )
    best = min(candidates, key=lambda s: abs(float(s["coordinate_m"]) - coordinate))
    return JSONResponse(status_code=200, content=best)


# ---------------------------------------------------------------------------
# GET /blast/simulations/{simulation_id}/export
# ---------------------------------------------------------------------------


@router.get("/{simulation_id}/export")
async def export_simulation(simulation_id: str, fmt: str = Query("xlsx", pattern="^(xlsx|npz|json)$")):
    row = db.get_blast_simulation(simulation_id)
    if row is None:
        raise _structured_error(404, "not found", error_code="SIMULATION_NOT_FOUND")
    npz_path = row.get("npz_path") or ""
    if fmt == "npz":
        if not npz_path:
            raise _structured_error(404, "NPZ artifact path missing", error_code="NO_ARTIFACT")
        return FileResponse(npz_path, media_type="application/octet-stream",
                            filename=f"{simulation_id}_energy_field.npz")
    if fmt == "json":
        return JSONResponse(status_code=200, content=row["summary"])
    # xlsx — rebuild from the persisted summary.
    from core.blast_simulation.contracts import (
        GridMetadata, ProcessingSummary, SimulationProvenance,
        SimulationResult, SimulationSourceSummary, VoxelEnergyField,
    )
    summary_dict = row["summary"]
    # Minimal reconstruction sufficient for the Excel writer.
    grid_meta = GridMetadata(
        shape=tuple(summary_dict["grid_metadata"]["shape"]),
        voxel_size_m=summary_dict["grid_metadata"]["voxel_size_m"],
        bounds=DomainBounds(**summary_dict["grid_metadata"]["bounds"]),
        axes_order=summary_dict["grid_metadata"]["axes_order"],
        energy_unit=summary_dict["grid_metadata"]["energy_unit"],
        dtype=summary_dict["grid_metadata"]["dtype"],
        voxel_count=summary_dict["grid_metadata"]["voxel_count"],
        voxel_volume_m3=summary_dict["grid_metadata"]["voxel_volume_m3"],
        npz_sha256=summary_dict["grid_metadata"].get("npz_sha256", ""),
        created_at=summary_dict["grid_metadata"].get("created_at", ""),
    )
    src = SimulationSourceSummary(
        source_rows=summary_dict["source_summary"]["source_rows"],
        accepted_holes=summary_dict["source_summary"]["accepted_holes"],
        rejected_holes=summary_dict["source_summary"]["rejected_holes"],
        charge_segments=summary_dict["source_summary"]["charge_segments"],
        valid_sources=summary_dict["source_summary"]["valid_sources"],
        invalid_sources=summary_dict["source_summary"]["invalid_sources"],
        voxel_count=summary_dict["source_summary"]["voxel_count"],
        active_voxels=summary_dict["source_summary"]["active_voxels"],
        represented_energy_j=summary_dict["source_summary"]["represented_energy_j"],
        outside_domain_energy_j=summary_dict["source_summary"]["outside_domain_energy_j"],
        warning_count=summary_dict["source_summary"]["warning_count"],
        blocking_error_count=summary_dict["source_summary"]["blocking_error_count"],
    )
    ef = summary_dict["energy_field"]
    energy_field = VoxelEnergyField(
        grid=grid_meta,
        represented_energy_j=ef["represented_energy_j"],
        outside_domain_energy_j=ef["outside_domain_energy_j"],
        total_coupled_energy_j=ef["total_coupled_energy_j"],
        fraction_represented=ef["fraction_represented"],
        active_voxels=ef["active_voxels"],
        max_energy_j=ef["max_energy_j"],
        mean_energy_j_active=ef["mean_energy_j_active"],
        npz_path=ef.get("npz_path", ""),
        energy_unit=ef.get("energy_unit", "J"),
    )
    ps = summary_dict["processing_summary"]
    processing = ProcessingSummary(
        accepted_holes=ps["accepted_holes"], charge_segments=ps["charge_segments"],
        valid_sources=ps["valid_sources"], invalid_sources=ps["invalid_sources"],
        voxel_count=ps["voxel_count"], active_voxels=ps["active_voxels"],
        represented_energy_j=ps["represented_energy_j"],
        outside_domain_energy_j=ps["outside_domain_energy_j"],
        total_coupled_energy_j=ps["total_coupled_energy_j"],
        fraction_represented=ps["fraction_represented"],
        warning_records=ps["warning_records"],
        blocking_error_records=ps["blocking_error_records"],
        temporal_status=ps["temporal_status"], energy_mode=ps["energy_mode"],
    )
    prov_dict = summary_dict["provenance"]
    provenance = SimulationProvenance(
        engine_version=prov_dict["engine_version"],
        simulation_configuration_version=prov_dict["simulation_configuration_version"],
        geometry_configuration_version=prov_dict["geometry_configuration_version"],
        explosive_registry_source=prov_dict["explosive_registry_source"],
        explosive_products_used=tuple(prov_dict.get("explosive_products_used") or ()),
        rock_mass_source=prov_dict.get("rock_mass_source", ""),
        propagation_velocity_source=prov_dict.get("propagation_velocity_source", ""),
        assumptions=tuple(prov_dict.get("assumptions") or ()),
        warnings=tuple(prov_dict.get("warnings") or ()),
        accepted_rows_hash=prov_dict.get("accepted_rows_hash", ""),
    )
    from core.blast_simulation.contracts import PlanSlice, SectionSlice
    result = SimulationResult(
        simulation_id=simulation_id,
        configuration=summary_dict["configuration"],
        grid_metadata=grid_meta,
        source_summary=src,
        energy_field=energy_field,
        plan_slices=tuple(PlanSlice(**p) for p in summary_dict.get("plan_slices") or ()),
        section_slices=tuple(SectionSlice(**s) for s in summary_dict.get("section_slices") or ()),
        processing_summary=processing,
        warnings=tuple(summary_dict.get("warnings") or ()),
        blocking_errors=tuple(summary_dict.get("blocking_errors") or ()),
        spatial_diagnostics=summary_dict.get("spatial_diagnostics") or {},
        temporal_diagnostics=summary_dict.get("temporal_diagnostics") or {},
        provenance=provenance,
        created_at=summary_dict.get("created_at", ""),
        engine_version=summary_dict.get("engine_version", ""),
    )
    import tempfile
    out = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    out.close()
    export_simulation_xlsx(result, out.name)
    return FileResponse(out.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=f"{simulation_id}_simulation.xlsx")
