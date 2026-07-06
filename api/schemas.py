from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from enum import Enum


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
    face_threshold: float = 40.0
    berm_threshold: float = 20.0


class TolerancesSchema(BaseModel):
    bench_height: Dict[str, float] = Field(default={"neg": 1.0, "pos": 1.5})
    face_angle: Dict[str, float] = Field(default={"neg": 5.0, "pos": 5.0})
    berm_width: Dict[str, float] = Field(default={"min": 6.0})
    inter_ramp_angle: Dict[str, float] = Field(default={"neg": 3.0, "pos": 2.0})
    overall_angle: Dict[str, float] = Field(default={"neg": 2.0, "pos": 2.0})


class BlastSettingsSchema(BaseModel):
    """Per-session drill & blast tunables.

    ``rock_density_tm3`` — in-situ rock bulk density (ton/m³) used to
    convert broken volume into broken mass for the per-mass powder factor
    (``pf_g_per_ton``). Defaults match :class:`core.config.BlastDefaults`.
    ``height_fallback_m`` — vertical height used when the real hole
    geometry (``longitud_real`` / ``Inclinacion_real``) is missing.
    """

    rock_density_tm3: float = Field(default=2.7, ge=0.0, le=20.0, examples=[2.7])
    height_fallback_m: float = Field(default=15.0, ge=0.0, le=100.0, examples=[15.0])


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


class ComparisonResult(BaseModel):
    sector: str
    section: str
    bench_num: int
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
    model_config = ConfigDict(populate_by_name=True)

    show_reconciled_design: bool = Field(default=True, alias="showReconciledDesign")
    show_reconciled_topo: bool = Field(default=True, alias="showReconciledTopo")
    show_spill_areas: bool = Field(default=True, alias="showSpillAreas")
    show_blast_holes: bool = Field(default=True, alias="showBlastHoles")
    blast_tolerance: float = Field(default=2.0, alias="blastTolerance")
    selected_bench_numbers: List[int] = Field(default_factory=list, alias="selectedBenchNumbers")


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
    hole_id: str
    distance: float
    elevation: float
    burden: float
    spacing: float
    is_within_tolerance: bool


class BlastHolesOnProfileResponse(BaseModel):
    section_id: str
    mesh_id: str
    tolerance: float
    holes: List[BlastHoleOnProfile]


class BlastCorrelationRowSchema(BaseModel):
    """One row of blast↔geotech correlation for a single section.

    Mirrors :class:`core.blast_correlation.BlastCorrelationRow`. Numeric metrics
    default to ``0.0`` so empty / no-data sections serialise cleanly. Floats are
    rounded to 3 decimals at the mapping site (matching ``BlastHoleOnProfile``).
    """

    section_name: str
    num_wells: int = 0
    total_kg: float = 0.0
    mean_abs_deviation: float = 0.0
    avg_over_break: float = 0.0
    avg_under_break: float = 0.0
    n_over: int = 0
    n_under: int = 0
    pf_vol_avg_kgm3: float = 0.0
    pf_area_avg_kgm2: float = 0.0
    pf_g_per_ton_avg: float = 0.0
    pf_g_per_ton_net_avg: float = 0.0
    energy_total_mj: float = 0.0
    n_pf_valid: int = 0


class BlastCorrelationResponse(BaseModel):
    """Response envelope for ``GET /process/blast-correlation``.

    ``rows`` is empty (never an error) when the session has no blast holes, no
    sections, or no comparison results. ``tolerance`` echoes the inclusion
    radius used (``None`` → core default ``DEFAULTS.blast_correlation_radius_m``).
    """

    rows: List[BlastCorrelationRowSchema] = Field(default_factory=list)
    tolerance: Optional[float] = None
    n_sections: int = 0


class BlastDamagePointSchema(BaseModel):
    """One scatter point (section) for the PF↔damage chart.

    ``pf_g_per_ton`` is the per-mass powder factor (the highlighted g/ton
    metric surfaced by ``BlastCorrelationRowSchema``). ``over_break`` is the
    mean overbreak (m) for that section.
    """

    section_name: str
    pf_g_per_ton: float = 0.0
    over_break: float = 0.0


class BlastDamageModelFitSchema(BaseModel):
    """Fitted OLS regression ``damage = beta0 + beta1 * PF`` summary.

    ``confidence`` is one of ``'HIGH'`` / ``'MEDIUM'`` / ``'LOW'`` /
    ``'INSUFFICIENT'``. The full fit dict from
    :func:`core.blast_model.fit_powder_factor_damage_model` also carries
    ``std_err_beta1`` / ``mean_pf`` / ``is_significant``; we surface the
    fields the web chart actually renders.
    """

    beta0: float = 0.0
    beta1: float = 0.0
    r_squared: float = 0.0
    p_value: float = 0.0
    n: int = 0
    confidence: str = "INSUFFICIENT"
    ci_beta1_low: float = 0.0
    ci_beta1_high: float = 0.0


class BlastDamageModelResponse(BaseModel):
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
