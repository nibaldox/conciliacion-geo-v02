"""Core modules for geotechnical reconciliation pipeline."""

from core.mesh_handler import (
    load_mesh, get_mesh_bounds, mesh_to_plotly, decimate_mesh,
    load_dxf_polyline
)
from core.section_cutter import (
    SectionLine, cut_mesh_with_section, cut_both_surfaces,
)
from core.param_extractor import (
    extract_parameters, compare_design_vs_asbuilt, build_reconciled_profile,
)
from core.excel_writer import export_results
from core.report_generator import generate_word_report, generate_section_images_zip

__all__ = [
    'load_mesh', 'get_mesh_bounds', 'mesh_to_plotly', 'decimate_mesh',
    'load_dxf_polyline', 'SectionLine', 'cut_mesh_with_section',
    'cut_both_surfaces', 'extract_parameters', 'compare_design_vs_asbuilt',
    'generate_word_report', 'generate_section_images_zip',
]
