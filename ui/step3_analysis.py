"""
Step 3: Cut surfaces, extract geotechnical parameters, and compare design vs as-built.
Separates processing logic from UI rendering.
"""
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from core import (
    cut_mesh_with_section,
    extract_parameters,
    compare_design_vs_asbuilt,
)


def render_step3(config: dict) -> None:
    """Render Paso 3: section processing and parameter extraction."""
    st.header("🔬 Paso 3: Cortar Superficies y Extraer Parámetros")

    if not st.session_state.sections:
        return

    all_names = [s.name for s in st.session_state.sections]
    selected_names = st.multiselect(
        "Seleccionar secciones a procesar:",
        options=all_names, default=all_names, key="section_selector")

    if st.button("🚀 Ejecutar Análisis", type="primary"):
        if not selected_names:
            st.error("Debes seleccionar al menos una sección.")
            return

        sections_to_process = [s for s in st.session_state.sections if s.name in selected_names]
        results = _run_parallel_analysis(sections_to_process, config)

        st.session_state.profiles_design = results['profiles_design']
        st.session_state.profiles_topo = results['profiles_topo']
        st.session_state.params_design = results['params_design']
        st.session_state.params_topo = results['params_topo']
        st.session_state.comparison_results = results['comparisons']
        st.session_state.processed_sections = sections_to_process
        st.session_state.step = 4

        _render_summary_metrics(results)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _run_parallel_analysis(sections_to_process, config: dict) -> dict:
    """Run mesh cutting and parameter extraction in parallel. Returns results dict."""
    total = len(sections_to_process)
    profiles_d = [None] * total
    profiles_t = [None] * total
    params_d = [None] * total
    params_t = [None] * total
    comparisons = []

    # Capture state locally to avoid Streamlit ThreadContext errors in workers
    local_mesh_design = st.session_state.mesh_design
    local_mesh_topo = st.session_state.mesh_topo
    resolution = config['resolution']
    face_threshold = config['face_threshold']
    berm_threshold = config['berm_threshold']
    tolerances = config['tolerances']

    progress = st.progress(0)
    status = st.empty()
    status.text(f"Procesando {total} secciones en paralelo...")

    def _process_single(args):
        i, section = args
        pd_prof = cut_mesh_with_section(local_mesh_design, section)
        pt_prof = cut_mesh_with_section(local_mesh_topo, section)

        ep_d = ep_t = None
        comp = []
        if pd_prof is not None and pt_prof is not None:
            ep_d = extract_parameters(
                pd_prof.distances, pd_prof.elevations,
                section.name, section.sector, resolution, face_threshold, berm_threshold)
            ep_t = extract_parameters(
                pt_prof.distances, pt_prof.elevations,
                section.name, section.sector, resolution, face_threshold, berm_threshold)
            if ep_d.benches and ep_t.benches:
                comp = compare_design_vs_asbuilt(ep_d, ep_t, tolerances)
        return i, pd_prof, pt_prof, ep_d, ep_t, comp

    completed = 0
    with ThreadPoolExecutor() as executor:
        for i, pd_prof, pt_prof, ep_d, ep_t, comp in executor.map(
                _process_single, enumerate(sections_to_process)):
            profiles_d[i] = pd_prof
            profiles_t[i] = pt_prof
            if ep_d and ep_t:
                params_d[i] = ep_d
                params_t[i] = ep_t
                comparisons.extend(comp)
            completed += 1
            status.text(
                f"Procesando sección {sections_to_process[i].name} ({completed}/{total})...")
            progress.progress(completed / total)

    status.text("✅ Análisis completado")
    return {
        'profiles_design': profiles_d,
        'profiles_topo': profiles_t,
        'params_design': params_d,
        'params_topo': params_t,
        'comparisons': comparisons,
        'total': total,
    }


def _render_summary_metrics(results: dict) -> None:
    profiles_d = results['profiles_design']
    comparisons = results['comparisons']
    total = results['total']

    n_ok = n_total_valid = 0
    for c in comparisons:
        for k in ('height_status', 'angle_status', 'berm_status'):
            s = c.get(k)
            if s and s != "-":
                n_total_valid += 1
                if s in ("CUMPLE", "RAMPA OK"):
                    n_ok += 1

    pct = n_ok / n_total_valid * 100 if n_total_valid > 0 else 0

    cols = st.columns(4)
    cols[0].metric("Secciones procesadas",
                   f"{sum(1 for p in profiles_d if p is not None)}/{total}")
    cols[1].metric("Bancos detectados", len(comparisons))
    cols[2].metric("Total evaluaciones", n_total_valid)
    cols[3].metric("Cumplimiento global", f"{pct:.1f}%")
