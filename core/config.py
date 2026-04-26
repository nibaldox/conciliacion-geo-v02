"""Centralized configuration defaults for the geotechnical pipeline."""

from dataclasses import dataclass, field
from typing import Dict


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
    simplify_epsilon: float = 0.1     # meters, RDP simplification tolerance
    profile_resolution: float = 0.5   # meters, profile resampling resolution


@dataclass(frozen=True)
class PipelineDefaults:
    """Defaults for the processing pipeline."""
    section_length: float = 200.0     # meters
    section_spacing: float = 20.0     # meters (for auto-generation)
    target_faces_visual: int = 30000  # target faces for mesh decimation
    max_upload_mb: int = 500          # max file upload size
    match_threshold: float = 5.0      # meters, bench matching by elevation


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
