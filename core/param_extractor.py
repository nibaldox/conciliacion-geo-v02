"""Backward-compat re-exports. Prefer importing from the specific module:

    from core.profile_extract import extract_parameters, BenchParams
    from core.bench_hazards import _detect_overhangs_and_bridges
    from core.profile_compliance import compare_design_vs_asbuilt
    from core.profile_simplify import ramer_douglas_peucker

This shim is kept for legacy imports. New code should use the
specific modules directly.
"""
from core.bench_classify import (
    _apply_leading_berm,
    _apply_trailing_berm,
    _compute_berm_widths_from_profile,
    _flat_segment_width,
)
from core.bench_hazards import (
    _angle_between_segments,
    _detect_overhangs_and_bridges,
    _detect_toppling_potential,
    _detect_wedge_shape_in_face,
    _evaluate_angle_consistency,
    _evaluate_catch_bench_adequacy,
)
from core.profile_compliance import (
    _evaluate_status,
    build_reconciled_profile,
    build_reconciled_profile_v2,
    compare_design_vs_asbuilt,
)
from core.profile_extract import (
    BenchParams,
    ExtractionResult,
    ReconciledPoint,
    ReconciledProfile,
    _build_reconciled_points,
    extract_parameters,
)
from core.profile_simplify import (
    _detect_and_project_solid_toe,
    ramer_douglas_peucker,
)

__all__ = [
    "ReconciledPoint", "ReconciledProfile", "BenchParams", "ExtractionResult",
    "extract_parameters", "_build_reconciled_points",
    "ramer_douglas_peucker", "_detect_and_project_solid_toe",
    "_compute_berm_widths_from_profile", "_flat_segment_width",
    "_apply_leading_berm", "_apply_trailing_berm",
    "_detect_overhangs_and_bridges", "_evaluate_catch_bench_adequacy",
    "_angle_between_segments", "_detect_wedge_shape_in_face",
    "_detect_toppling_potential", "_evaluate_angle_consistency",
    "_evaluate_status", "build_reconciled_profile", "build_reconciled_profile_v2",
    "compare_design_vs_asbuilt",
]
