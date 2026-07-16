"""Pure Word document generation for export."""
import os
import tempfile
from typing import Any, Optional

from core.report_generator import generate_word_report


def build_document(
    filtered_comps: list,
    sections: list,
    profile_pairs: dict[str, tuple],
    design_params_map: dict[str, Any],
    topo_params_map: dict[str, Any],
    project_info: dict,
    df_pozos: Optional[Any] = None,
    sections_full: Optional[list] = None,
    plot_options: Optional[dict] = None,
) -> bytes:
    """Generate a Word report and return its bytes."""
    if plot_options is None:
        plot_options = {}

    all_data_for_report = []
    for sec in sections:
        pair = profile_pairs.get(sec.name)
        if pair is None:
            continue
        pd_prof, pt_prof = pair
        if pd_prof is None or pt_prof is None:
            continue
        all_data_for_report.append({
            'section_name': sec.name,
            'params_design': design_params_map.get(sec.name),
            'params_topo': topo_params_map.get(sec.name),
            'profile_d': (pd_prof.distances, pd_prof.elevations),
            'profile_t': (pt_prof.distances, pt_prof.elevations),
        })

    output_path = os.path.join(tempfile.gettempdir(), "Informe_Conciliacion.docx")
    generate_word_report(
        filtered_comps,
        all_data_for_report,
        output_path,
        project_info=project_info,
        df_pozos=df_pozos,
        sections=sections_full,
        plot_options=plot_options,
    )
    with open(output_path, "rb") as f:
        return f.read()
