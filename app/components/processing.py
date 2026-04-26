"""Paso 3: Cortar superficies y extraer parámetros con ThreadPoolExecutor."""
import streamlit as st
from concurrent.futures import ThreadPoolExecutor

from core import (
    cut_mesh_with_section,
    extract_parameters,
    compare_design_vs_asbuilt,
)


def render_processing_section(config: dict):
    """Render the processing UI and run analysis.

    Args:
        config: dict with keys tolerances, face_threshold, berm_threshold, resolution.

    Returns:
        Tuple of (profiles_design, profiles_topo, params_design, params_topo, comparisons)
        or None if not yet processed.
    """
    if st.session_state.step < 3 or not st.session_state.sections:
        return None

    tolerances = config['tolerances']
    face_threshold = config['face_threshold']
    berm_threshold = config['berm_threshold']
    resolution = config['resolution']

    st.header("🔬 Paso 3: Cortar Superficies y Extraer Parámetros")

    if st.session_state.sections:
        all_names = [s.name for s in st.session_state.sections]
        selected_names = st.multiselect(
            "Seleccionar secciones a procesar:",
            options=all_names,
            default=all_names,
            key="section_selector"
        )
    else:
        selected_names = []

    if st.button("🚀 Ejecutar Análisis", type="primary"):
        if not selected_names:
            st.error("Debes seleccionar al menos una sección.")
            return None

        # Filter sections
        sections_to_process = [s for s in st.session_state.sections if s.name in selected_names]

        progress = st.progress(0)
        status = st.empty()

        total = len(sections_to_process)

        # Prepare lists to preserve order
        profiles_d = [None] * total
        profiles_t = [None] * total
        params_d = [None] * total
        params_t = [None] * total
        comparisons = []

        # Extract state to local variables to avoid Streamlit ThreadContext errors in workers
        local_mesh_design = st.session_state.mesh_design
        local_mesh_topo = st.session_state.mesh_topo

        def process_single(args):
            i, section = args
            pd_prof = cut_mesh_with_section(local_mesh_design, section)
            pt_prof = cut_mesh_with_section(local_mesh_topo, section)

            ep_d, ep_t, comp = None, None, []
            if pd_prof is not None and pt_prof is not None:
                ep_d = extract_parameters(pd_prof.distances, pd_prof.elevations,
                                          section.name, section.sector, resolution, face_threshold, berm_threshold)
                ep_t = extract_parameters(pt_prof.distances, pt_prof.elevations,
                                          section.name, section.sector, resolution, face_threshold, berm_threshold)
                if ep_d.benches and ep_t.benches:
                    comp = compare_design_vs_asbuilt(ep_d, ep_t, tolerances)

            return i, pd_prof, pt_prof, ep_d, ep_t, comp

        status.text(f"Procesando {total} secciones en paralelo...")

        completed = 0
        with ThreadPoolExecutor() as executor:
            for i, pd_prof, pt_prof, ep_d, ep_t, comp in executor.map(
                    process_single, enumerate(sections_to_process)):
                profiles_d[i] = pd_prof
                profiles_t[i] = pt_prof

                if ep_d and ep_t:
                    params_d[i] = ep_d
                    params_t[i] = ep_t
                    comparisons.extend(comp)

                completed += 1
                status.text(f"Procesando sección {sections_to_process[i].name} ({completed}/{total})...")
                progress.progress(completed / total)

        st.session_state.profiles_design = profiles_d
        st.session_state.profiles_topo = profiles_t
        st.session_state.params_design = params_d
        st.session_state.params_topo = params_t
        st.session_state.comparison_results = comparisons
        st.session_state.processed_sections = sections_to_process
        st.session_state.step = 4

        status.text("✅ Análisis completado")

        n_ok = 0
        n_total_valid = 0
        for c in comparisons:
            for k in ['height_status', 'angle_status', 'berm_status']:
                s = c.get(k)
                if s and s != "-":
                    n_total_valid += 1
                    if s == "CUMPLE" or s == "RAMPA OK":
                        n_ok += 1

        pct = n_ok / n_total_valid * 100 if n_total_valid > 0 else 0

        cols = st.columns(4)
        cols[0].metric("Secciones procesadas", f"{sum(1 for p in profiles_d if p is not None)}/{total}")
        cols[1].metric("Bancos detectados", len(comparisons))
        cols[2].metric("Total evaluaciones", n_total_valid)
        cols[3].metric("Cumplimiento global", f"{pct:.1f}%")

        return profiles_d, profiles_t, params_d, params_t, comparisons

    return None
