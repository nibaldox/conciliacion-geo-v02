"""Centralized configuration defaults for the geotechnical pipeline."""

import os
from dataclasses import dataclass, field
from typing import Dict


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean env var (true/1/yes/on = True)."""
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to default on parse error."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Tolerances:
    """Default tolerances for compliance evaluation."""
    bench_height: Dict[str, float] = field(default_factory=lambda: {'neg': 1.0, 'pos': 1.5})
    face_angle: Dict[str, float] = field(default_factory=lambda: {'neg': 5.0, 'pos': 5.0})
    berm_width: Dict[str, float] = field(default_factory=lambda: {'min': 6.0})
    inter_ramp_angle: Dict[str, float] = field(default_factory=lambda: {'neg': 3.0, 'pos': 2.0})
    overall_angle: Dict[str, float] = field(default_factory=lambda: {'neg': 2.0, 'pos': 2.0})
    crest_toe_deviation: Dict[str, float] = field(default_factory=lambda: {'neg': 1.0, 'pos': 1.0})


@dataclass(frozen=True)
class DetectionDefaults:
    """Defaults for bank/berm detection algorithm."""
    face_threshold: float = 40.0      # degrees, minimum angle to classify as face
    berm_threshold: float = 20.0      # degrees, maximum angle to classify as berm
    max_berm_width: float = 50.0      # meters, filter unrealistically large berms
    min_bench_height: float = 2.0     # meters, minimum bench height to be detected
    simplify_epsilon: float = 0.05    # meters, RDP simplification tolerance (was 0.1)
    profile_resolution: float = 0.1   # meters, profile resampling resolution (was 0.5)
    # Spill-pile detection (used by _detect_and_project_solid_toe)
    spill_angle_solid: float = 52.0   # degrees, segments above this are solid face
    spill_angle_pile: float = 48.0    # degrees, segments below this are spill pile
    # Face angle weight: when computing weighted face angle, use the segments
    # whose angle is within (face_threshold - face_threshold_margin) of vertical
    face_threshold_margin: float = 10.0  # degrees
    # Final toe-X refinement RDP tolerance
    face_refine_epsilon: float = 0.03  # meters
    # Multi-method bench detection (Phase 20)
    curvature_threshold: float = 15.0   # degrees, discrete curvature for inflection candidates
    extrema_window: int = 3             # half-window for local crest/toe extrema search
    smoothing_min_window: int = 5       # min Savitzky-Golay window for adaptive smoothing
    smoothing_max_window: int = 11      # max Savitzky-Golay window for adaptive smoothing
    consensus_quorum: int = 3           # methods that must agree for "consensus" classification
    confidence_density_floor: int = 10  # source points needed for full confidence
    max_single_bench_width: float = 25.0  # meters, faces wider than this are split into sub-benches
    sub_bench_min_prominence: float = 1.0  # meters, min elevation drop to count a split point
    sub_bench_confidence_factor: float = 0.85  # confidence penalty for inferred sub-benches
    ramp_narrow_min_width: float = 6.0   # meters, min width for the gentle-slope ramp test
    ramp_max_slope_deg: float = 15.0     # degrees, max longitudinal slope for a ramp segment
    ramp_min_descent_m: float = 0.5      # meters, min crest-to-toe descent to call a segment a ramp
    gap_match_threshold: float = 8.0     # meters, elevation window for matching design vs as-built


@dataclass(frozen=True)
class PipelineDefaults:
    """Defaults for the processing pipeline."""
    section_length: float = 200.0     # meters
    section_spacing: float = 20.0     # meters (for auto-generation)
    target_faces_visual: int = 30000  # target faces for mesh decimation
    max_upload_mb: int = 500          # max file upload size
    match_threshold: float = 5.0      # meters, bench matching by elevation
    # Drill & Blast / geotech correlation
    blast_correlation_radius_m: float = 15.0   # meters — projection radius
    blast_correlation_pasadura_optimal: tuple = (0.5, 1.5)  # meters
    blast_default_bench_height: float = 15.0   # meters — used for pasadura
    blast_temporal_filter_days: int = 7       # days — blast must precede topo by >= N days


@dataclass(frozen=True)
class DeployDefaults:
    """Production-deployment knobs. All read from env vars at import time.

    Every value has a sensible default that preserves the original
    behaviour of the local-dev / Streamlit workflow. Production opt-ins
    (Supabase, R2, auth) default to False so enabling them requires
    an explicit decision.
    """
    # Logging
    log_level: str = field(default_factory=lambda: os.environ.get("CONCILIACION_LOG_LEVEL", "INFO"))
    log_format: str = field(default_factory=lambda: os.environ.get("CONCILIACION_LOG_FORMAT", "plain"))

    # Rate limiting (slowapi)
    rate_limit_enabled: bool = field(default_factory=lambda: _env_bool("CONCILIACION_RATE_LIMIT_ENABLED", False))
    rate_limit_per_min: int = field(default_factory=lambda: _env_int("CONCILIACION_RATE_LIMIT_PER_MIN", 120))

    # Phase 2.9 opt-ins (all default False → SQLite + local FS + open access)
    use_supabase: bool = field(default_factory=lambda: _env_bool("CONCILIACION_USE_SUPABASE", False))
    use_r2: bool = field(default_factory=lambda: _env_bool("CONCILIACION_USE_R2", False))
    auth_required: bool = field(default_factory=lambda: _env_bool("CONCILIACION_AUTH_REQUIRED", False))

    # CORS
    cors_origins_env: str = field(default_factory=lambda: os.environ.get("CONCILIACION_CORS_ORIGINS", ""))

    # Runtime
    workers: int = field(default_factory=lambda: _env_int("CONCILIACION_WORKERS", 1))
    data_dir: str = field(default_factory=lambda: os.environ.get("CONCILIACION_DATA_DIR", ""))


@dataclass(frozen=True)
class VisualizationDefaults:
    """Defaults for UI visualization."""
    grid_height: float = 15.0         # meters, vertical grid spacing
    grid_ref: float = 0.0             # meters, grid reference elevation
    contour_resolution: int = 500     # grid size for contour plots


@dataclass(frozen=True)
class RampDetection:
    """Ramp detection parameters."""
    min_width: float = 15.0           # meters
    max_width: float = 42.0           # meters


@dataclass(frozen=True)
class ExplosiveEnergy:
    """Reference specific energy per explosive type (MJ/kg) and density (g/cm³).

    Used to convert total_kg to total energy (MJ) when comparing blasts with
    different explosive products. Typical values from ENAEX product catalog.

    ``pirex_energy_by_grade`` / ``pirex_density_by_grade`` are the single
    source of truth for the per-grade Pirex emulsion values consumed by
    :mod:`core.explosive_properties` (formerly hardcoded there in
    parallel ``PIREX_ENERGY_MJ_KG`` / ``PIREX_DENSITY_G_CM3`` dicts).
    """
    anfo_energy: float = 3.72
    emulsion_energy: float = 2.78
    heavy_anfo_energy: float = 3.40
    bulk_emulsion_energy: float = 3.05

    anfo_density: float = 0.80
    emulsion_density: float = 1.20
    heavy_anfo_density: float = 1.05
    bulk_emulsion_density: float = 1.15

    pirex_energy_by_grade: Dict[str, float] = field(default_factory=lambda: {
        'Pirex-930': 3.05,
        'Pirex-920': 2.95,
        'Pirex-950': 3.15,
        'Pirex-970': 3.25,
    })
    pirex_density_by_grade: Dict[str, float] = field(default_factory=lambda: {
        'Pirex-930': 1.20,
        'Pirex-920': 1.15,
        'Pirex-950': 1.23,
        'Pirex-970': 1.25,
    })

    def energy_mj_per_kg(self, explosive_type: str) -> float:
        """Return MJ/kg for a given explosive type string (case-insensitive)."""
        et = (explosive_type or '').strip().upper()
        if 'HEAVY' in et or 'H-ANFO' in et:
            return self.heavy_anfo_energy
        if 'EMULSION' in et or 'BULK' in et or 'EMUL' in et:
            return self.bulk_emulsion_energy
        if 'ANFO' in et:
            return self.anfo_energy
        return self.anfo_energy

    def density_g_per_cm3(self, explosive_type: str) -> float:
        """Return density (g/cm³) for a given explosive type string (case-insensitive)."""
        et = (explosive_type or '').strip().upper()
        if 'HEAVY' in et or 'H-ANFO' in et:
            return self.heavy_anfo_density
        if 'EMULSION' in et or 'BULK' in et or 'EMUL' in et:
            return self.bulk_emulsion_density
        if 'ANFO' in et:
            return self.anfo_density
        return self.anfo_density


@dataclass(frozen=True)
class PowderFactor:
    """Powder-factor thresholds for advisories."""
    pf_high_alert_kgm3: float = 0.45
    pf_optimal_kgm3: float = 0.35
    pf_low_warn_kgm3: float = 0.20


@dataclass(frozen=True)
class BlastAdvisorDefaults:
    """Tuning knobs for the recommendation engine."""
    target_overbreak_m: float = 0.5
    target_underbreak_m: float = -0.3
    pf_optimal_default_kgm3: float = 0.35
    max_recommendation_pct: float = 30.0
    min_samples_for_advice: int = 5
    high_confidence_n: int = 15
    medium_confidence_n: int = 8
    pf_upper_bound_factor: float = 1.5
    pf_max_operational_kgm3: float = 1.50


@dataclass(frozen=True)
class StabilityDefaults:
    """Stability analysis thresholds for overhang and catch bench detection."""
    overhang_warning_m: float = 0.5
    overhang_critical_m: float = 1.5
    berm_design_min_m: float = 6.0
    rockfall_catch_factor: float = 0.6


@dataclass(frozen=True)
class BlastDefaults:
    """Rock-mass and blast-hole defaults for explosive-charge metrics.

    ``rock_density_tm3`` is the in-situ rock bulk density (ton/m^3) used to
    convert broken volume into broken mass for the per-mass powder factor
    (``pf_g_per_ton``). It defaults to the canonical medium-rock value
    shared with :mod:`core.blast_metrics`.

    ``height_fallback_m`` is the per-hole vertical height used when the
    real hole geometry (``longitud_real`` / ``Inclinacion_real``) is
    missing or invalid.
    """
    rock_density_tm3: float = 2.7
    height_fallback_m: float = 15.0


@dataclass(frozen=True)
class SectorDeviationDefaults:
    """Phase 21 — per-sector overbreak / underbreak reconciliation thresholds.

    Controls :func:`core.profile_compliance.compute_sector_deviations`:

    - ``tolerance_m`` is the vertical tolerance used to flag a sector as
      ``"compliant"`` (sectors whose integrated deviation stays below
      ``tolerance_m * width`` are compliant).
    - ``grid_resolution_m`` is the spacing of the common distance grid used
      to interpolate design and topo before integrating areas.
    - ``face_angle_suggestion`` knobs bound :func:`suggest_face_angle_for_fs`.
    """
    tolerance_m: float = 0.3
    grid_resolution_m: float = 0.1
    suggested_face_angle_floor_deg: float = 5.0
    suggested_face_angle_ceiling_deg: float = 89.0
    suggested_face_angle_unreachable_deg: float = 30.0
    suggested_face_angle_tolerance_deg: float = 0.01
    rockmass_cohesion_scale: float = 0.001


@dataclass(frozen=True)
class DrillComplianceDefaults:
    delta_x_m: float = 0.5
    delta_y_m: float = 0.5
    delta_z_m: float = 0.3
    delta_incl_deg: float = 3.0
    delta_az_deg: float = 5.0
    delta_len_m: float = 0.5
    delta_kg_pct: float = 10.0
    nearest_radius_m: float = 5.0


@dataclass(frozen=True)
class DrillHardnessDefaults:
    """Knobs for :mod:`core.drill_hardness_processor`.

    - ``radius_m`` — spatial join radius for the cKDTree query.
    - ``duration_soft_min`` / ``duration_medium_min`` / ``duration_hard_min`` —
      duration metric cutoffs (minutes).
    - ``rate_soft_m_min`` / ``rate_medium_m_min`` / ``rate_hard_m_min`` —
      rate metric cutoffs (m/min).
    - ``strict_parity`` — reserved for downstream parity guards.
    """
    radius_m: float = 2.0
    duration_soft_min: float = 16.0
    duration_medium_min: float = 24.0
    duration_hard_min: float = 40.0
    rate_soft_m_min: float = 1.0
    rate_medium_m_min: float = 0.7
    rate_hard_m_min: float = 0.4
    strict_parity: bool = True


@dataclass(frozen=True)
class BackbreakDefaults:
    """Knobs for :mod:`core.backbreak_prediction.predict_backbreak`.

    All defaults are calibrated for typical open-pit hard-rock designs:
    burden ~ 6 m, spacing ~ 7 m, PF ~ 0.35 kg/m³, bench ~ 15 m.

    The empirical back-break formula mirrors a simple geometric scaling
    (``empirical_k * burden * (pf / pf_optimal_default_kgm3)``); the
    Holmberg-Persson cross-check uses a constant ``hp_constant`` scaled by
    the total charge per hole and is clamped to a plausible range
    ``[clamp_low_factor_b · B, clamp_high_factor_b · B]``.
    """
    empirical_k: float = 0.3
    hp_constant: float = 0.6
    pf_optimal_default_kgm3: float = 0.35
    ci_band_pct: float = 0.15
    clamp_low_factor_b: float = 0.5
    clamp_high_factor_b: float = 4.0
    bench_height_m: float = 15.0
    default_burden_m: float = 6.0
    default_spacing_m: float = 7.0
    default_stemming_m: float = 6.0
    default_diameter_mm: float = 250.0
    rock_factor_min: float = 0.7
    rock_factor_max: float = 1.3


# Singleton instances
DEFAULTS = PipelineDefaults()
DETECTION = DetectionDefaults()
TOLERANCES = Tolerances()
VISUALIZATION = VisualizationDefaults()
RAMP = RampDetection()
DEPLOY = DeployDefaults()
EXPLOSIVE = ExplosiveEnergy()
POWDER_FACTOR = PowderFactor()
ADVISOR = BlastAdvisorDefaults()
STABILITY = StabilityDefaults()
SECTOR_DEVIATION = SectorDeviationDefaults()
BLAST = BlastDefaults()
DRILL_COMPLIANCE = DrillComplianceDefaults()
DRILL_HARDNESS = DrillHardnessDefaults()
BACKBREAK = BackbreakDefaults()
