"""Shared helpers for the export tab package."""
from typing import Optional

from core import cut_both_surfaces
from core.section_cutter import ProfileResult


def _get_profile_pair(section_name: str) -> tuple[Optional[ProfileResult], Optional[ProfileResult]]:
    """Look up the cached (design, topo) ProfileResult pair for a section by name.

    Falls back to a fresh cut only when the section was not part of the
    processed batch in step 3 (e.g. legacy sessions or manual additions).
    """
    import streamlit as st

    profiles_design = st.session_state.get('profiles_design') or []
    profiles_topo = st.session_state.get('profiles_topo') or []
    processed_sections = st.session_state.get('processed_sections') or []

    for idx, sec in enumerate(processed_sections):
        if sec.name == section_name:
            pd_prof = profiles_design[idx] if idx < len(profiles_design) else None
            pt_prof = profiles_topo[idx] if idx < len(profiles_topo) else None
            return pd_prof, pt_prof

    mesh_design = st.session_state.get('mesh_design')
    mesh_topo = st.session_state.get('mesh_topo')
    sections = st.session_state.get('sections') or []
    target = next((s for s in sections if s.name == section_name), None)
    if target is not None and mesh_design is not None and mesh_topo is not None:
        return cut_both_surfaces(mesh_design, mesh_topo, target)
    return None, None


def _get_filtered_comparisons() -> list:
    """Return comparison results filtered by the active UI filters."""
    import streamlit as st
    from ui.filters import collect_active_filters_from_session_state
    from ui.filters import apply_comparison_filters

    comps = st.session_state.comparison_results
    if not comps:
        return []

    return apply_comparison_filters(
        list(comps), collect_active_filters_from_session_state()
    )


def _build_section_status_map(comp_results: list) -> dict:
    section_status = {}
    for c in comp_results:
        sec = c.get('section', '')
        statuses = [c.get('height_status', ''), c.get('angle_status', ''), c.get('berm_status', '')]
        if sec not in section_status:
            section_status[sec] = 'CUMPLE'
        if 'NO CUMPLE' in statuses:
            section_status[sec] = 'NO CUMPLE'
        elif 'FUERA DE TOLERANCIA' in statuses and section_status[sec] != 'NO CUMPLE':
            section_status[sec] = 'FUERA DE TOLERANCIA'
    return section_status


def _profile_to_3d(distances, elevations, origin_x, origin_y, direction):
    return [
        (origin_x + d * direction[0], origin_y + d * direction[1], float(e))
        for d, e in zip(distances, elevations)
    ]


def _create_dxf_layers(doc) -> None:
    layers = [
        ("DISEÑO_CUMPLE", 3), ("DISEÑO_NO_CUMPLE", 1), ("DISEÑO_FUERA_TOL", 2),
        ("TOPO_CUMPLE", 3), ("TOPO_NO_CUMPLE", 1), ("TOPO_FUERA_TOL", 2),
        ("CONCILIADO_DISEÑO", 5), ("CONCILIADO_TOPO", 6), ("ETIQUETAS", 7),
    ]
    for name, color in layers:
        doc.layers.add(name, color=color)
