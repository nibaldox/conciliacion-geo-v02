from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum

from core.config import DETECTION, TOLERANCES
from core.geometry_contract import GEOMETRY_CONFIGURATION_VERSION


class MeshType(str, Enum):
    DESIGN = "design"
    TOPO = "topo"


class MeshInfo(BaseModel):
    id: str
    type: MeshType
    n_vertices: int
    n_faces: int
    bounds: Dict[str, float]
    filename: str
    uploaded_at: str
    import_report: Optional[Dict[str, Any]] = None


class SectionCreate(BaseModel):
    name: str = Field(default="S-01")
    origin: List[float] = Field(default=[0.0, 0.0], description="[x, y]")
    azimuth: float = 0.0
    length: float = 200.0
    sector: str = ""


class SectionResponse(BaseModel):
    id: str
    name: str
    origin: List[float]
    azimuth: float
    length: float
    sector: str


class SectionAutoParams(BaseModel):
    start: List[float] = Field(description="[x, y]")
    end: List[float] = Field(description="[x, y]")
    n_sections: int = 5
    azimuth: Optional[float] = None
    length: float = 200.0
    sector: str = ""
    az_method: str = "perpendicular"
    fixed_az: float = 0.0


class SectionFromFileParams(BaseModel):
    spacing: float = 20.0
    length: float = 200.0
    sector: str = "Principal"
    az_mode: str = "perpendicular"


class ProcessSettings(BaseModel):
    resolution: float = 0.1
    face_threshold: float = DETECTION.face_threshold
    berm_threshold: float = DETECTION.berm_threshold


class TolerancesSchema(BaseModel):
    bench_height: Dict[str, float] = Field(default_factory=lambda: dict(TOLERANCES.bench_height))
    face_angle: Dict[str, float] = Field(default={"neg": 5.0, "pos": 5.0})
    berm_width: Dict[str, float] = Field(default_factory=lambda: dict(TOLERANCES.berm_width))
    inter_ramp_angle: Dict[str, float] = Field(default={"neg": 3.0, "pos": 2.0})
    overall_angle: Dict[str, float] = Field(default={"neg": 2.0, "pos": 2.0})
    crest_toe_deviation: Dict[str, float] = Field(default={"neg": 1.0, "pos": 1.0})


class BlastSettingsSchema(BaseModel):
    """Per-session drill & blast tunables.

    ``rock_density_tm3`` — in-situ rock bulk density (ton/m³) used to
    convert broken volume into broken mass for the per-mass powder factor
    (``pf_g_per_ton``). Defaults match :class:`core.config.BlastDefaults`.
    ``height_fallback_m`` — vertical height used when the real hole
    geometry (``longitud_real`` / ``Inclinacion_real``) is missing.
    ``sector_density`` — optional ``{sector: rho}`` map keyed by the
    section's ``sector`` (geotechnical domain). A section whose sector is
    present uses that ρ instead of the global ``rock_density_tm3``;
    sectors not in the map keep the global fallback. Empty dict (default)
    means every sector uses the global ρ.
    """

    rock_density_tm3: float = Field(default=2.7, ge=0.0, le=20.0, examples=[2.7])
    height_fallback_m: float = Field(default=15.0, ge=0.0, le=100.0, examples=[15.0])
    sector_density: Dict[str, float] = Field(default_factory=dict)


class BenchParamsSchema(BaseModel):
    bench_number: int
    crest_elevation: float
    crest_distance: float
    toe_elevation: float
    toe_distance: float
    bench_height: float
    face_angle: float
    berm_width: float
    is_ramp: bool = False
    spill_width: float = 0.0
    effective_berm_width: float = 0.0
    spill_start_distance: float = 0.0
    spill_start_elevation: float = 0.0


class ExtractionResultSchema(BaseModel):
    section_name: str
    sector: str
    benches: List[BenchParamsSchema] = []
    inter_ramp_angle: float = 0.0
    overall_angle: float = 0.0


class ProfileData(BaseModel):
    section_name: str
    sector: str
    origin: List[float]
    azimuth: float
    design: Optional[Dict[str, List[float]]] = None
    topo: Optional[Dict[str, List[float]]] = None
    reconciled_design: Optional[Dict[str, List[float]]] = None
    reconciled_topo: Optional[Dict[str, List[float]]] = None
    reconciled_design_legacy: Optional[Dict[str, List[float]]] = None
    reconciled_topo_legacy: Optional[Dict[str, List[float]]] = None
    benches_topo: Optional[List[BenchParamsSchema]] = None
    benches_design: Optional[List[BenchParamsSchema]] = None
    horizontal_deviation: Optional[Dict[str, Any]] = None
    profile_warnings: Optional[Dict[str, List[str]]] = None


class ComparisonResult(BaseModel):
    sector: str
    section: str
    bench_num: int
    bench_num_topo: Optional[int] = None
    type: str  # "MATCH" | "MISSING" | "EXTRA"
    level: str
    height_design: Optional[float] = None
    height_real: Optional[float] = None
    height_dev: Optional[float] = None
    height_status: str
    angle_design: Optional[float] = None
    angle_real: Optional[float] = None
    angle_dev: Optional[float] = None
    angle_status: str
    berm_design: Optional[float] = None
    berm_real: Optional[float] = None
    berm_min: Optional[float] = None
    berm_status: str
    delta_crest: Optional[float] = None
    delta_toe: Optional[float] = None
    guided_delta_crest: Optional[float] = None
    guided_delta_crest_status: Optional[str] = None
    guided_delta_toe: Optional[float] = None
    guided_delta_toe_status: Optional[str] = None
    guided_height: Optional[float] = None
    guided_height_status: Optional[str] = None
    guided_angle: Optional[float] = None
    guided_angle_status: Optional[str] = None
    guided_berm: Optional[float] = None
    guided_berm_status: Optional[str] = None
    guided_floor_offset_m: Optional[float] = None
    guided_floor_offset_status: Optional[str] = None
    guided_remaining_thickness_mean_m: Optional[float] = None
    guided_remaining_thickness_max_m: Optional[float] = None
    guided_excavation_debt_area_m2: Optional[float] = None
    design_bench_state: Optional[str] = None
    split_bench: Optional[bool] = None
    split_of: Optional[int] = None
    proposed_source: Optional[str] = None
    proposed_height: Optional[float] = None
    proposed_angle: Optional[float] = None
    proposed_delta_crest: Optional[float] = None
    proposed_delta_toe: Optional[float] = None
    proposed_berm: Optional[float] = None
    proposed_height_source: Optional[str] = None
    proposed_angle_source: Optional[str] = None
    proposed_crest_source: Optional[str] = None
    proposed_toe_source: Optional[str] = None
    proposed_berm_source: Optional[str] = None
    proposed_height_status: Optional[str] = None
    proposed_angle_status: Optional[str] = None
    proposed_crest_status: Optional[str] = None
    proposed_toe_status: Optional[str] = None
    proposed_berm_status: Optional[str] = None
    proposed_bench_score: Optional[float] = None
    proposed_evaluable: Optional[bool] = None
    proposed_exclusion_reason: Optional[str] = None
    floor_offset_m: Optional[float] = None
    floor_status: Optional[str] = None
    excavation_debt_thickness_mean_m: Optional[float] = None
    excavation_debt_thickness_max_m: Optional[float] = None
    excavation_debt_area_m2: Optional[float] = None
    proposal_status: Optional[str] = None
    proposal_error: Optional[str] = None
    height_score: Optional[float] = None
    angle_score: Optional[float] = None
    berm_score: Optional[float] = None
    bench_score: Optional[float] = None
    section_score: Optional[float] = None
    section_status: Optional[str] = None
    spill_width: Optional[float] = None
    effective_berm: Optional[float] = None
    effective_berm_status: Optional[str] = None
    berm_dev: Optional[float] = None
    berm_remnant_max_m: Optional[float] = None
    berm_remnant_area_m2: Optional[float] = None
    guided_berm_remnant_max_m: Optional[float] = None
    guided_berm_remnant_area_m2: Optional[float] = None
    guided_warnings: Optional[List[str]] = None
    floor_tolerance_used: Optional[Dict[str, float]] = None


class ProposedCoverageSchema(BaseModel):
    n_evaluable: int
    n_design_benches: int
    ratio: Optional[float] = None


class ProposedSectionSummarySchema(BaseModel):
    section: Optional[str] = None
    proposed_section_score: Optional[float] = None
    proposed_section_status: Optional[str] = None
    n_rows: int = 0
    n_evaluable: int = 0
    n_not_excavated: int = 0
    n_section_truncated: int = 0
    n_unmeasured: int = 0
    n_split_fragments: int = 0
    n_split_benches: int = 0
    excavation_debt_area_m2: float = 0.0
    floor_status_counts: Dict[str, int] = Field(default_factory=dict)


class ProposedSummarySchema(BaseModel):
    section: Optional[str] = None
    proposed_global_score: Optional[float] = None
    n_rows: int = 0
    n_evaluable: int = 0
    n_not_excavated: int = 0
    n_section_truncated: int = 0
    n_unmeasured: int = 0
    n_split_fragments: int = 0
    n_split_benches: int = 0
    excavation_debt_area_m2: float = 0.0
    floor_status_counts: Dict[str, int] = Field(default_factory=dict)
    coverage: ProposedCoverageSchema = Field(
        default_factory=lambda: ProposedCoverageSchema(n_evaluable=0, n_design_benches=0))
    by_section: Dict[str, ProposedSectionSummarySchema] = Field(default_factory=dict)


class ProposedComplianceResponse(BaseModel):
    session_id: str
    proposal_status: str  # "current" | "not_computed" | "partial"
    n_total_rows: int = 0
    n_proposal_rows: int = 0
    n_failed_rows: int = 0
    n_not_computed_rows: int = 0
    summary: Optional[ProposedSummarySchema] = None
    floor_tolerance: Dict[str, float]
    floor_tolerance_used: Optional[Dict[str, float]] = None
    floor_tolerance_source: str  # "session" | "core_default"
    filters: Dict[str, List[str]] = Field(default_factory=dict)
    status_model: str = ""
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ProcessStatus(BaseModel):
    status: str  # "idle" | "processing" | "complete" | "error"
    current_section: Optional[int] = None
    total_sections: Optional[int] = None
    completed_sections: int = 0
    n_results: int = 0


class ExportRequest(BaseModel):
    project: str = ""
    author: str = ""
    operation: str = ""
    phase: str = ""


class ExportFilters(BaseModel):
    """Active export filters sent by the web UI as camelCase JSON.

    ``sector`` / ``section`` / ``level`` are the aliases the dashboard's
    ``ResultFilterState`` uses (singular, plural field names); they are
    accepted alongside the legacy ``selectedBenchNumbers`` for backward
    compatibility. Every empty dimension means "all", so an empty payload
    (the historical query) exports everything.
    """

    model_config = ConfigDict(populate_by_name=True)

    show_reconciled_design: bool = Field(default=True, alias="showReconciledDesign")
    show_reconciled_topo: bool = Field(default=True, alias="showReconciledTopo")
    show_spill_areas: bool = Field(default=True, alias="showSpillAreas")
    show_blast_holes: bool = Field(default=True, alias="showBlastHoles")
    blast_tolerance: float = Field(default=2.0, alias="blastTolerance")
    selected_bench_numbers: List[int] = Field(default_factory=list, alias="selectedBenchNumbers")
    sectors: List[str] = Field(default_factory=list, alias="sector")
    sections: List[str] = Field(default_factory=list, alias="section")
    levels: List[str] = Field(default_factory=list, alias="level")


class SettingsResponse(BaseModel):
    process: ProcessSettings
    tolerances: TolerancesSchema
    blast: Optional[BlastSettingsSchema] = None


class SettingsUpdate(BaseModel):
    """Partial-update body for ``PUT /settings``.

    All fields are optional so a caller can PATCH a single block (e.g.
    ``{"blast": {"rock_density_tm3": 3.0}}``) without resending the others.
    The router merges only the blocks actually present in the body.
    """

    process: Optional[ProcessSettings] = None
    tolerances: Optional[TolerancesSchema] = None
    blast: Optional[BlastSettingsSchema] = None


class MessageResponse(BaseModel):
    message: str


class UploadResponse(BaseModel):
    mesh_id: str
    n_vertices: int
    n_faces: int
    bounds: Dict[str, float]
    import_report: Optional[Dict[str, Any]] = None


class DxfImportConfirmation(BaseModel):
    upload_id: str
    layers: List[str] = Field(min_length=1)
    units: int = Field(ge=1, le=24)


class ContourLine(BaseModel):
    """A single contour level with one or more line segments."""

    elevation: float
    segments: List[List[List[float]]]  # List of polylines, each [[x,y], [x,y], ...]


class ContourResponse(BaseModel):
    bounds: Dict[str, float]
    elevation_min: float
    elevation_max: float
    interval: float
    lines: List[ContourLine]


class BlastHoleOnProfile(BaseModel):
    row_id: str
    hole_id: str
    distance: float
    elevation: float
    burden: Optional[float]
    spacing: Optional[float]
    is_within_tolerance: bool
    section_relation: Optional[str] = None
    profile_point_kind: str
    z_collar_semantic: Optional[str] = None
    surface_sample_status: Optional[str] = None
    surface_sample_method: Optional[str] = None
    surface_sample_mesh_id: Optional[str] = None
    surface_sample_mesh_sha256: Optional[str] = None


class BlastHolesOnProfileResponse(BaseModel):
    data_status: Literal["current", "legacy_reimport_required"] = "legacy_reimport_required"
    algorithm_version: Optional[str] = None
    section_id: str
    mesh_id: str
    tolerance: float
    holes: List[BlastHoleOnProfile]


class BlastCorrelationRowSchema(BaseModel):
    section_name: str
    num_wells: int = 0
    total_kg: Optional[float] = None
    mean_abs_deviation: Optional[float] = None
    avg_over_break: Optional[float] = None
    avg_under_break: Optional[float] = None
    n_over: int = 0
    n_under: int = 0
    pf_vol_avg_kgm3: Optional[float] = None
    pf_area_avg_kgm2: Optional[float] = None
    pf_g_per_ton_avg: Optional[float] = None
    pf_g_per_ton_net_avg: Optional[float] = None
    pf_g_per_ton_inf_avg: Optional[float] = None
    pf_voronoi_bench_g_per_ton_section: Optional[float] = None
    n_pf_voronoi_bench_valid: int = 0
    pf_voronoi_bench_status_counts: Dict[str, int] = Field(default_factory=dict)
    pf_voronoi_bench_source_counts: Dict[str, int] = Field(default_factory=dict)
    pf_voronoi_bench_source_dominant: Optional[str] = None
    energy_total_mj: Optional[float] = None
    energy_known_mj: Optional[float] = None
    n_kg_known: int = 0
    n_kg_missing: int = 0
    energy_coverage_kg_fraction: Optional[float] = None
    n_pf_valid: int = 0
    sector: str = ""
    rock_density_used: Optional[float] = None


class BlastDataStatus(BaseModel):
    data_status: Literal["current", "legacy_reimport_required"] = "legacy_reimport_required"
    algorithm_version: Optional[str] = None


class BlastConsolidationIssue(BaseModel):
    reason: str
    source_row_indices: List[int] = Field(default_factory=list)
    malla: Optional[str] = None
    id_pozo: Optional[str] = None


class BlastConsolidationReport(BaseModel):
    key_columns: List[str] = Field(default_factory=list)
    rows_in: int = 0
    holes_out: int = 0
    exact_copies_removed: int = 0
    copies_by_malla: Dict[str, int] = Field(default_factory=dict)
    holes_with_decks: int = 0
    deck_rows_merged: int = 0
    conflicts: List[BlastConsolidationIssue] = Field(default_factory=list)
    unmerged_missing_identity: int = 0
    version: Optional[str] = None
    warnings: List[BlastConsolidationIssue] = Field(default_factory=list)


class BlastFootprintReport(BaseModel):
    mode: str = "estimated_hull"
    n_mallas: int = 0
    n_estimated: int = 0
    n_user: int = 0
    n_missing: int = 0
    buffer_factor: Optional[float] = 0.5
    method: str = ""
    missing_reasons: Dict[str, str] = Field(default_factory=dict)


class BlastSessionSummary(BlastDataStatus):
    n_holes: int = 0
    consolidation_report: Optional[BlastConsolidationReport] = None
    footprint_report: Optional[BlastFootprintReport] = None


class BlastDeck(BaseModel):
    kg: Optional[float] = None
    explosive: Optional[str] = None
    taco_m: Optional[float] = None
    source_row_index: Optional[int] = None


class BlastHoleDetail(BlastDataStatus):
    hole_id: str
    row_id: str
    decks: List[BlastDeck] = Field(default_factory=list)
    explosive_mix: Dict[str, float] = Field(default_factory=dict)
    source_row_indices: List[int] = Field(default_factory=list)
    source_row_index_user: Optional[List[int]] = None
    duplicate_rows_removed: int = 0
    area_influence_m2: Optional[float] = None
    area_status: Optional[str] = None
    pf_voronoi_bench_area_m2: Optional[float] = None
    pf_voronoi_bench_area_status: Optional[str] = None
    pf_voronoi_bench_domain_area_m2: Optional[float] = None
    pf_voronoi_bench_g_per_ton: Optional[float] = None
    pf_voronoi_bench_status: Optional[str] = None
    pf_voronoi_bench_source: Optional[str] = None
    pf_voronoi_bench_unit: Optional[str] = None
    pf_voronoi_bench_assumptions: List[str] = Field(default_factory=list)
    pf_voronoi_bench_warnings: List[str] = Field(default_factory=list)
    bench_height_status: Optional[str] = None
    altura_carga_warning: Optional[str] = None
    energy_total_mj: Optional[float] = None
    energy_known_mj: Optional[float] = None
    energy_coverage_kg_fraction: Optional[float] = None
    kg_per_meter_loaded_column: Optional[float] = None
    kg_per_meter_loaded_column_status: Optional[str] = None


class BlastCorrelationResponse(BlastDataStatus):
    """Response envelope for ``GET /process/blast-correlation``.

    ``rows`` is empty (never an error) when the session has no blast holes, no
    sections, or no comparison results. ``tolerance`` echoes the inclusion
    radius used (``None`` → core default ``DEFAULTS.blast_correlation_radius_m``).
    """

    rows: List[BlastCorrelationRowSchema] = Field(default_factory=list)
    tolerance: Optional[float] = None
    n_sections: int = 0
    temporal_filter: Dict[str, Any] = Field(default_factory=dict)
    carga: List[float] = Field(default_factory=list)
    descarga: List[float] = Field(default_factory=list)
    kg_per_meter: List[float] = Field(default_factory=list)
    kg_per_meter_loaded_column: List[float] = Field(default_factory=list)


class BlastDamagePointSchema(BaseModel):
    """One scatter point (section) for the PF↔damage chart.

    ``pf_g_per_ton`` is the per-mass powder factor (the highlighted g/ton
    metric surfaced by ``BlastCorrelationRowSchema``). ``over_break`` is the
    mean overbreak (m) for that section.
    """

    section_name: str
    pf_g_per_ton: Optional[float] = None
    over_break: Optional[float] = None


class BlastDamageModelFitSchema(BaseModel):
    """Fitted OLS regression ``damage = beta0 + beta1 * PF`` summary.

    ``confidence`` is one of ``'HIGH'`` / ``'MEDIUM'`` / ``'LOW'`` /
    ``'INSUFFICIENT'``. The full fit dict from
    :func:`core.blast_model.fit_powder_factor_damage_model` also carries
    ``std_err_beta1`` / ``mean_pf`` / ``is_significant``; we surface the
    fields the web chart actually renders.
    """

    beta0: Optional[float] = None
    beta1: Optional[float] = None
    r_squared: Optional[float] = None
    p_value: Optional[float] = None
    n: int = 0
    confidence: str = "INSUFFICIENT"
    ci_beta1_low: Optional[float] = None
    ci_beta1_high: Optional[float] = None


class BlastDamageModelResponse(BlastDataStatus):
    """Response envelope for ``GET /process/blast-correlation/damage-model``.

    ``points`` carries one entry per section (PF, overbreak). ``fit`` is the
    OLS regression summary, or ``None`` when the fitter returned
    ``confidence='INSUFFICIENT'`` / fewer than ``min_samples`` valid points.
    ``x_metric`` / ``y_metric`` echo the metrics plotted so the frontend does
    not hardcode the axis meaning. Empty case: ``points=[]``, ``fit=None``,
    HTTP 200 (never 500) — mirrors :class:`BlastCorrelationResponse`.
    """

    points: List[BlastDamagePointSchema] = Field(default_factory=list)
    fit: Optional[BlastDamageModelFitSchema] = None
    x_metric: str = "pf_g_per_ton"
    y_metric: str = "over_break"
    temporal_filter: Dict[str, Any] = Field(default_factory=dict)


class BlastHoleSummary(BaseModel):
    """One persisted blast hole as returned by ``GET /api/v1/blast/{id}/holes``.

    Coordinates follow the mining convention (X=East, Y=North, Z=Elevation).
    ``carga`` maps to the charge density (kg of explosive per metre of hole)
    when the source CSV includes a kilogram column; ``descarga`` maps to the
    explosive column length (``altura_carga_m`` = drilled length - stemming).
    Missing numeric fields are represented as null.
    """

    hole_id: str
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    carga: Optional[float] = None
    descarga: Optional[float] = None
    hardness: Optional[str] = None
    bench: Optional[str] = None
    length: Optional[float] = None
    inclination: Optional[float] = None
    azimuth: Optional[float] = None
    z_collar_semantic: Optional[str] = None
    surface_sample_status: Optional[str] = None
    surface_sample_reason: Optional[str] = None
    surface_sample_method: Optional[str] = None
    surface_sample_mesh_id: Optional[str] = None
    surface_sample_mesh_sha256: Optional[str] = None
    surface_sample_unit: Optional[str] = None
    surface_sample_assumption: Optional[str] = None


class BlastHolesResponse(BlastDataStatus):
    """Response envelope for ``GET /api/v1/blast/{session_id}/holes``."""

    session_id: str
    holes: List[BlastHoleSummary] = Field(default_factory=list)


class BlastHole3D(BaseModel):
    row_id: str
    hole_id: str
    source_row_index: Optional[int] = None
    source_row_index_user: Optional[List[int]] = None
    collar: Optional[List[float]] = None
    toe: Optional[List[float]] = None
    geometry_status: str
    provenance: Dict[str, Any] = Field(default_factory=dict)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    section_relation: Optional[str] = None
    section_distance_m: Optional[float] = None


class BlastHoles3DSummary(BaseModel):
    total_loaded: int = 0
    drawable: int = 0
    complete_geometry: int = 0
    collar_only: int = 0
    without_geometry: int = 0
    rejected: int = 0


class BlastHoles3DResponse(BlastDataStatus):
    session_id: str
    section_id: Optional[int] = None
    corridor_m: Optional[float] = None
    data_revision: Optional[str] = None
    holes: List[BlastHole3D] = Field(default_factory=list)
    rejected_rows: List[Dict[str, Any]] = Field(default_factory=list)
    summary: BlastHoles3DSummary


class GeometryConfigurationSchema(BaseModel):
    """Versioned geometric configuration — single contract across layers.

    Mirrors :class:`core.geometry_contract.GeometryConfiguration`. The UI,
    the API and the backend serialize EXACTLY the same fields so the
    operator sees one consistent configuration object end-to-end.
    """

    geometry_configuration_version: str = GEOMETRY_CONFIGURATION_VERSION
    geometry_user_confirmed: Optional[bool] = None

    inclination_source_column: str = ""
    inclination_convention: Optional[str] = None
    inclination_sign_convention: Optional[str] = None
    inclination_unit: Optional[str] = None
    inclination_source_rule: str = ""

    azimuth_source_column: str = ""
    azimuth_convention: Optional[str] = None
    azimuth_unit: Optional[str] = None


class RejectedRowSchema(BaseModel):
    """Structured per-row rejection record (remediación 3.2/4.2).

    Every rejection preserves the full diagnosis: hole_id, source row,
    source column, original value, error_code, rejection_reason, the
    affected downstream calculations, the recommended action and the row
    processing status. Multiple errors per row emit multiple records.
    """

    hole_id: str
    source_row_index: int = 0
    source_column: str = ""
    original_value: Optional[Any] = None
    error_code: str = ""
    rejection_reason: str = ""
    affected_calculations: str = ""
    recommended_action: str = ""
    row_processing_status: str = "rejected"


class BlockingErrorSchema(BaseModel):
    """Structured blocking error (zero accepted rows, invalid geometry, etc.)."""

    error_code: str
    message: str = ""
    recommended_action: str = ""


class BlastUploadResponse(BlastDataStatus):
    """Response envelope for ``POST /api/v1/blast/upload``.

    Remediación 3.2/4.2 + integración 3.6: the structured
    ``accepted_rows``, ``rejected_rows`` and ``blocking_errors`` survive
    even when zero rows are accepted — the endpoint returns HTTP 422
    (not 400) in that case so the operator can read the structured
    diagnosis in the body.
    """

    session_id: str
    n_holes: int
    n_rows_loaded: int
    n_rows_skipped: int
    carga_mean: Optional[float]
    descarga_mean: Optional[float]
    hardness_distribution: Dict[str, int] = Field(default_factory=dict)
    # Structured processing output — single canonical contract across API,
    # backend, persistence and export (integración §3.6/4.6).
    data_warnings: str = ""
    processing_summary: Dict[str, Any] = Field(default_factory=dict)
    consolidation_report: BlastConsolidationReport = Field(default_factory=BlastConsolidationReport)
    footprint_report: BlastFootprintReport = Field(default_factory=BlastFootprintReport)
    accepted_rows: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_rows: List[Dict[str, Any]] = Field(default_factory=list)
    event_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    blocking_errors: List[Dict[str, Any]] = Field(default_factory=list)
    geometry_configuration: Dict[str, Any] = Field(default_factory=dict)
    spatial_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    design_surface: Optional[Dict[str, Any]] = None
