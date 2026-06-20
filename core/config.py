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
    log_format: str = field(default_factory=lambda: os.environ.get("CONCILIATION_LOG_FORMAT", "plain"))

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
    workers: int = field(default_factory=lambda: _env_int("CONCILIATION_WORKERS", 1))
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


# Singleton instances
DEFAULTS = PipelineDefaults()
DETECTION = DetectionDefaults()
TOLERANCES = Tolerances()
VISUALIZATION = VisualizationDefaults()
RAMP = RampDetection()
DEPLOY = DeployDefaults()
