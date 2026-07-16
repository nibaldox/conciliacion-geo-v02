"""Pure PNG/ZIP generation for export."""
from typing import Any, Optional

from core.report_generator import generate_section_images_zip


def build_png_zip(
    sections: list,
    profile_pairs: dict[str, tuple],
    design_params_map: dict[str, Any],
    topo_params_map: dict[str, Any],
    plot_options: dict,
    df_pozos: Optional[Any] = None,
    sections_full: Optional[list] = None,
    filtered_comps: Optional[list] = None,
) -> bytes:
    """Generate a ZIP with PNG section images and return its bytes."""
    all_data_for_images = []
    for sec in sections:
        pair = profile_pairs.get(sec.name)
        if pair is None:
            continue
        pd_prof, pt_prof = pair
        if pd_prof is None or pt_prof is None:
            continue
        all_data_for_images.append({
            'section_name': sec.name,
            'params_design': design_params_map.get(sec.name),
            'params_topo': topo_params_map.get(sec.name),
            'profile_d': (pd_prof.distances, pd_prof.elevations),
            'profile_t': (pt_prof.distances, pt_prof.elevations),
        })

    zip_buffer = generate_section_images_zip(
        all_data_for_images,
        plot_options=plot_options,
        sections=sections_full,
        df_pozos=df_pozos,
        filtered_comps=filtered_comps,
    )
    return zip_buffer.getvalue()
