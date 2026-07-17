"""Thin tab orchestrator for the Profiles view.

All Plotly construction lives in the sibling pure modules; this file only
reads Streamlit state and calls the pure builders.
"""
import streamlit as st

from ui.tabs.profiles.figure import build_profile_figure
from ui.tabs.profiles.state import (
    get_pozos_cache,
    get_profile_controls,
    get_profile_figure_inputs,
    render_face_angle_suggestion,
)


def render_tab_profiles(config: dict) -> None:
    controls = get_profile_controls()
    figure_inputs = get_profile_figure_inputs()
    pozos_cache = get_pozos_cache()

    display_sections = st.session_state.get('processed_sections', st.session_state.sections)

    valid_plots = []
    for i, section in enumerate(display_sections):
        pd_prof = st.session_state.profiles_design[i]
        pt_prof = st.session_state.profiles_topo[i]
        if pd_prof is None or pt_prof is None:
            st.warning(f"⚠️ Sección {section.name}: sin intersección con una o ambas superficies")
            continue
        valid_plots.append((i, section, pd_prof, pt_prof))

    fig_cache = st.session_state.setdefault('_profile_figs', {})

    for j in range(0, len(valid_plots), controls["num_cols"]):
        cols = st.columns(controls["num_cols"])
        for col_idx in range(controls["num_cols"]):
            if j + col_idx >= len(valid_plots):
                continue
            i, section, pd_prof, pt_prof = valid_plots[j + col_idx]
            cache_key = (
                i,
                id(pd_prof), id(pt_prof),
                id(st.session_state.get('reconciled_design')),
                id(st.session_state.get('area_fill_design')),
                controls["show_areas"], controls["show_spill_areas"], controls["show_semaphore"],
                controls["show_reconciled"], controls["show_pozos"], controls["blast_tolerance"],
                controls["show_sector_areas"],
                controls["num_cols"],
                "cota_labels_v1",
            )
            cached = fig_cache.get(i)
            if cached and cached[0] == cache_key:
                fig = cached[1]
            else:
                fig = build_profile_figure(
                    i, section, pd_prof, pt_prof,
                    show_areas=controls["show_areas"],
                    show_spill_areas=controls["show_spill_areas"],
                    show_semaphore=controls["show_semaphore"],
                    show_reconciled=controls["show_reconciled"],
                    show_pozos=controls["show_pozos"],
                    blast_tolerance=controls["blast_tolerance"],
                    config=config,
                    show_sector_areas=controls["show_sector_areas"],
                    **figure_inputs,
                    pozos_cache=pozos_cache,
                )
                fig_cache[i] = (cache_key, fig)
            with cols[col_idx]:
                st.plotly_chart(fig, width="stretch")
                params_topo = st.session_state.get('params_topo') or []
                if i < len(params_topo):
                    er = params_topo[i]
                    if er is not None and er.benches:
                        m_cols = st.columns(2)
                        m_cols[0].metric(
                            "Cota Piso",
                            f"{er.floor_elevation:.0f} m" if er.floor_elevation is not None else "—",
                        )
                        m_cols[1].metric(
                            "Cota Cresta",
                            f"{er.crest_elevation_max:.0f} m" if er.crest_elevation_max is not None else "—",
                        )
                if controls["show_sector_areas"]:
                    render_face_angle_suggestion(section, i)
