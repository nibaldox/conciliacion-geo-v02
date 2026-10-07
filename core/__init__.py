"""Core modules for geotechnical reconciliation pipeline."""

from core.mesh_handler import (
    load_mesh, get_mesh_bounds, mesh_to_plotly, decimate_mesh,
    load_dxf_polyline
)
from core.dxf_import import inspect_dxf_surface, import_dxf_surface
from core.section_cutter import (
    ProfileCutDiagnostics, SectionLine, cut_mesh_with_section,
    cut_mesh_with_section_diagnostics, cut_both_surfaces,
)
from core.param_extractor import (
    extract_parameters, build_reconciled_profile_v2,
    compare_design_vs_asbuilt, build_reconciled_profile,
)
from core.excel_writer import export_results
from core.report_generator import generate_word_report, generate_section_images_zip
from core.horizontal_deviation import (
    HorizontalDeviationResult,
    HorizontalFaceGeometry,
    classify_horizontal_deviation,
    compute_horizontal_deviation,
    measure_horizontal_deviation_at_elevation,
    profile_intersections_at_elevation,
)

__all__ = [
    'load_mesh', 'get_mesh_bounds', 'mesh_to_plotly', 'decimate_mesh',
    'load_dxf_polyline', 'SectionLine', 'cut_mesh_with_section',
    'ProfileCutDiagnostics', 'cut_mesh_with_section_diagnostics',
    'inspect_dxf_surface', 'import_dxf_surface',
    'cut_both_surfaces', 'extract_parameters', 'build_reconciled_profile_v2',
    'compare_design_vs_asbuilt', 'build_reconciled_profile',
    'generate_word_report', 'generate_section_images_zip',
    'HorizontalDeviationResult', 'HorizontalFaceGeometry',
    'classify_horizontal_deviation', 'compute_horizontal_deviation',
    'measure_horizontal_deviation_at_elevation',
    'profile_intersections_at_elevation',
]
