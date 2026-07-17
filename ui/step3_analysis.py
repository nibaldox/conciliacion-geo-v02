"""
Step 3: Cut surfaces, extract geotechnical parameters, and compare design vs as-built.
Separates processing logic from UI rendering.
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import streamlit as st

from core import (
    build_reconciled_profile,
    cut_mesh_with_section,
    extract_parameters,
    compare_design_vs_asbuilt,
)
from core.geom_utils import calculate_area_between_profiles


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

        _precompute_profile_artefacts(results)
        _render_summary_metrics(results)


def _precompute_profile_artefacts(results: dict) -> None:
    """Stash reconciled profile + area-fill arrays in session_state for step-4."""
    total = results['total']
    profiles_d = results['profiles_design']
    profiles_t = results['profiles_topo']
    params_d = results['params_design']
    params_t = results['params_topo']

    empty_area = (0.0, 0.0, np.array([]), np.array([]), np.array([]))
    empty_recon = (np.array([]), np.array([]))

    reconciled_design = [empty_recon] * total
    reconciled_topo = [empty_recon] * total
    area_fill_design = [empty_area] * total
    area_fill_topo = [empty_area] * total

    for i in range(total):
        pd_prof = profiles_d[i]
        pt_prof = profiles_t[i]
        ep_d = params_d[i]
        ep_t = params_t[i]

        if pd_prof is not None and pt_prof is not None:
            a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(
                pd_prof, pt_prof)
            area_fill_design[i] = (a_over, a_under, d_i, z_ref_i, z_eval_i)
            area_fill_topo[i] = (a_under, a_over, d_i, z_eval_i, z_ref_i)

        if ep_d is not None and ep_d.benches:
            design_floor = float(np.min(pd_prof.elevations)) if pd_prof is not None else None
            reconciled_design[i] = build_reconciled_profile(
                ep_d.benches,
                floor_elevation=design_floor,
            )
        if ep_t is not None and ep_t.benches:
            topo_floor = float(np.min(pt_prof.elevations)) if pt_prof is not None else None
            reconciled_topo[i] = build_reconciled_profile(
                ep_t.benches,
                floor_elevation=topo_floor,
            )

    st.session_state['reconciled_design'] = reconciled_design
    st.session_state['reconciled_topo'] = reconciled_topo
    st.session_state['area_fill_design'] = area_fill_design
    st.session_state['area_fill_topo'] = area_fill_topo


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
