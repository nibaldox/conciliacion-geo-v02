"""
Results tab: export to Excel, PNG images (ZIP), and DXF 3D profiles.
"""
import os
import tempfile
from datetime import datetime
from typing import Optional

import streamlit as st

from core import cut_both_surfaces, generate_section_images_zip
from core.param_extractor import build_reconciled_profile
from core.section_cutter import azimuth_to_direction, ProfileResult


def render_tab_export(config: dict) -> None:
    _render_excel_export(config)
    st.divider()
    _render_images_export(config)
    st.divider()
    _render_word_report(config)
    st.divider()
    _render_dxf_export()


def _get_profile_pair(section_name: str) -> tuple[Optional[ProfileResult], Optional[ProfileResult]]:
    """Look up the cached (design, topo) ProfileResult pair for a section by name.

    Falls back to a fresh cut only when the section was not part of the
    processed batch in step 3 (e.g. legacy sessions or manual additions).
    """
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
    comps = st.session_state.comparison_results
    if not comps:
        return []
    
    sel_sectors = st.session_state.get("table_filter_sector", [])
    sel_levels = st.session_state.get("table_filter_level", [])
    sel_sections = st.session_state.get("table_filter_section", [])
    sel_benches = st.session_state.get("table_filter_bench", [])
    
    filtered = []
    for c in comps:
        if sel_sectors and c.get('sector') not in sel_sectors:
            continue
        if sel_levels and c.get('level') not in sel_levels:
            continue
        if sel_sections and c.get('section') not in sel_sections:
            continue
        if sel_benches and c.get('bench_num') not in sel_benches:
            continue
        filtered.append(c)
    return filtered


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def _render_excel_export(config: dict) -> None:
    from core import export_results

    st.subheader("💾 Exportar Resultados a Excel")

    if not st.button("📥 Generar Excel de Conciliación", type="primary"):
        return

    with st.spinner("Generando Excel..."):
        output_path = os.path.join(tempfile.gettempdir(), "Conciliacion_Resultados.xlsx")
        project_info = {
            'project': config['project_name'],
            'operation': config['operation'],
            'phase': config['phase'],
            'author': config['author'],
            'date': datetime.now().strftime("%d/%m/%Y"),
        }
        export_results(
            st.session_state.comparison_results,
            st.session_state.params_design,
            st.session_state.params_topo,
            config['tolerances'], output_path, project_info,
            df_pozos=st.session_state.get('blast_df_clean'),
            sections=st.session_state.get('sections'))

        with open(output_path, "rb") as f:
            st.download_button(
                "⬇️ Descargar Excel", f.read(),
                file_name="Conciliacion_Diseno_vs_AsBuilt.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary")

    st.success("✅ Excel generado exitosamente")


# ---------------------------------------------------------------------------
# Images ZIP
# ---------------------------------------------------------------------------

def _render_images_export(config: dict) -> None:
    st.subheader("🖼️ Exportar Imágenes de Sección")
    st.write("Genera un archivo ZIP con todos los gráficos de perfil en formato PNG, "
             "respetando los filtros y las vistas activas.")

    if not st.button("📦 Generar Imágenes (ZIP)", type="primary"):
        return

    with st.spinner("Generando gráficos e imágenes..."):
        filtered_comps = _get_filtered_comparisons()
        if not filtered_comps:
            st.warning("⚠️ No hay datos que coincidan con los filtros activos.")
            return

        matching_section_names = {c['section'] for c in filtered_comps}
        all_data_for_images = []
        progress_bar = st.progress(0)
        sections = st.session_state.sections

        plot_options = {
            'show_reconciled': st.session_state.get('show_reconciled', True),
            'show_areas': st.session_state.get('show_areas', False),
            'show_semaphore': st.session_state.get('show_semaphore', False),
            'show_pozos': st.session_state.get('show_pozos_profile', True),
            'blast_tolerance': st.session_state.get('blast_tol_profile', 10.0),
            'grid_height': config.get('grid_height', 15.0),
            'grid_ref': config.get('grid_ref', 0.0),
            'tolerances': config.get('tolerances'),
        }

        # Build maps for robust lookup by section name
        processed_secs = st.session_state.get('processed_sections', [])
        if not processed_secs:
            processed_secs = sections

        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])

        design_params_map = {}
        topo_params_map = {}
        for idx, sec in enumerate(processed_secs):
            if idx < len(params_d_list):
                design_params_map[sec.name] = params_d_list[idx]
            if idx < len(params_t_list):
                topo_params_map[sec.name] = params_t_list[idx]

        for i, sec in enumerate(sections):
            if sec.name not in matching_section_names:
                continue

            pd_prof, pt_prof = _get_profile_pair(sec.name)

            if pd_prof and pt_prof:
                p_d = design_params_map.get(sec.name)
                p_t = topo_params_map.get(sec.name)
                all_data_for_images.append({
                    'section_name': sec.name,
                    'params_design': p_d,
                    'params_topo': p_t,
                    'profile_d': (pd_prof.distances, pd_prof.elevations),
                    'profile_t': (pt_prof.distances, pt_prof.elevations),
                })
            progress_bar.progress((i + 1) / len(sections))

        zip_bytes = generate_section_images_zip(
            all_data_for_images,
            plot_options=plot_options,
            sections=st.session_state.get('sections'),
            df_pozos=st.session_state.get('blast_df_clean'),
            filtered_comps=filtered_comps
        )
        st.download_button(
            label="⬇️ Descargar Imágenes ZIP",
            data=zip_bytes,
            file_name="Perfiles_Secciones.zip",
            mime="application/zip")

    st.success("✅ Imágenes generadas exitosamente")


# ---------------------------------------------------------------------------
# Word Report
# ---------------------------------------------------------------------------

def _render_word_report(config: dict) -> None:
    st.subheader("📄 Generar Informe Word (.docx)")
    st.write("Genera un informe ejecutivo en formato Word con resumen de cumplimiento, "
             "gráficos detallados y tablas de parámetros por sección, aplicando los filtros activos.")

    if not st.button("📝 Generar Informe Word", type="primary"):
        return

    with st.spinner("Generando informe Word..."):
        from core import generate_word_report
        
        filtered_comps = _get_filtered_comparisons()
        if not filtered_comps:
            st.warning("⚠️ No hay datos que coincidan con los filtros activos.")
            return

        matching_section_names = {c['section'] for c in filtered_comps}
        all_data_for_report = []
        sections = st.session_state.sections

        plot_options = {
            'show_reconciled': st.session_state.get('show_reconciled', True),
            'show_areas': st.session_state.get('show_areas', False),
            'show_semaphore': st.session_state.get('show_semaphore', False),
            'show_pozos': st.session_state.get('show_pozos_profile', True),
            'blast_tolerance': st.session_state.get('blast_tol_profile', 10.0),
            'grid_height': config.get('grid_height', 15.0),
            'grid_ref': config.get('grid_ref', 0.0),
            'tolerances': config.get('tolerances'),
        }

        # Build maps for robust lookup by section name
        processed_secs = st.session_state.get('processed_sections', [])
        if not processed_secs:
            processed_secs = sections

        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])

        design_params_map = {}
        topo_params_map = {}
        for idx, sec in enumerate(processed_secs):
            if idx < len(params_d_list):
                design_params_map[sec.name] = params_d_list[idx]
            if idx < len(params_t_list):
                topo_params_map[sec.name] = params_t_list[idx]

        for i, sec in enumerate(sections):
            if sec.name not in matching_section_names:
                continue

            pd_prof, pt_prof = _get_profile_pair(sec.name)

            if pd_prof and pt_prof:
                p_d = design_params_map.get(sec.name)
                p_t = topo_params_map.get(sec.name)
                all_data_for_report.append({
                    'section_name': sec.name,
                    'params_design': p_d,
                    'params_topo': p_t,
                    'profile_d': (pd_prof.distances, pd_prof.elevations),
                    'profile_t': (pt_prof.distances, pt_prof.elevations),
                })

        output_path = os.path.join(tempfile.gettempdir(), "Informe_Conciliacion.docx")
        project_info = {
            'project': config['project_name'],
            'operation': config['operation'],
            'phase': config['phase'],
            'author': config['author'],
            'date': datetime.now().strftime("%d/%m/%Y"),
        }

        generate_word_report(
            filtered_comps,
            all_data_for_report,
            output_path,
            project_info=project_info,
            df_pozos=st.session_state.get('blast_df_clean'),
            sections=st.session_state.get('sections'),
            plot_options=plot_options
        )

        with open(output_path, "rb") as f:
            st.download_button(
                "⬇️ Descargar Informe Word", f.read(),
                file_name="Informe_Conciliacion_Geotecnica.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary")

    st.success("✅ Informe Word generado exitosamente")



# ---------------------------------------------------------------------------
# DXF 3D
# ---------------------------------------------------------------------------

def _render_dxf_export() -> None:
    st.subheader("📐 Exportar Perfiles a DXF (3D)")
    st.write("Genera un archivo DXF con polilíneas 3D separadas por cumplimiento, "
             "incluyendo perfiles conciliados.")

    if not st.button("📊 Generar DXF de Perfiles", type="primary"):
        return

    with st.spinner("Generando DXF 3D de perfiles..."):
        import ezdxf

        doc = ezdxf.new('R2010')
        msp = doc.modelspace()

        _create_dxf_layers(doc)
        section_status = _build_section_status_map(st.session_state.comparison_results)

        processed_secs = st.session_state.get('processed_sections', [])
        if not processed_secs:
            processed_secs = st.session_state.get('sections', [])

        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])

        design_params_map = {}
        topo_params_map = {}
        for idx, sec in enumerate(processed_secs):
            if idx < len(params_d_list):
                design_params_map[sec.name] = params_d_list[idx]
            if idx < len(params_t_list):
                topo_params_map[sec.name] = params_t_list[idx]

        progress_bar = st.progress(0)
        n_exported = 0

        for i, sec in enumerate(processed_secs):
            pd_prof, pt_prof = _get_profile_pair(sec.name)

            if pd_prof and pt_prof:
                p_d = design_params_map.get(sec.name)
                p_t = topo_params_map.get(sec.name)
                _write_section_to_dxf(
                    msp, sec, p_d, p_t, pd_prof, pt_prof, section_status)
                n_exported += 1

            progress_bar.progress((i + 1) / len(processed_secs))

        tmp_path = os.path.join(tempfile.gettempdir(), "Perfiles_3D.dxf")
        doc.saveas(tmp_path)

        with open(tmp_path, "rb") as f:
            dxf_bytes = f.read()

        st.download_button(
            label=f"⬇️ Descargar DXF 3D ({n_exported} secciones)",
            data=dxf_bytes,
            file_name="Perfiles_3D.dxf",
            mime="application/dxf")

    st.success(f"✅ {n_exported} perfiles exportados a DXF 3D exitosamente")


def _create_dxf_layers(doc) -> None:
    layers = [
        ("DISEÑO_CUMPLE", 3), ("DISEÑO_NO_CUMPLE", 1), ("DISEÑO_FUERA_TOL", 2),
        ("TOPO_CUMPLE", 3), ("TOPO_NO_CUMPLE", 1), ("TOPO_FUERA_TOL", 2),
        ("CONCILIADO_DISEÑO", 5), ("CONCILIADO_TOPO", 6), ("ETIQUETAS", 7),
    ]
    for name, color in layers:
        doc.layers.add(name, color=color)


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


def _draw_3d_polyline(msp, pts, layer: str) -> None:
    msp.add_polyline3d(pts, dxfattribs={'layer': layer})


def _write_section_to_dxf(msp, sec, p_d, p_t, pd_prof, pt_prof, section_status) -> None:
    safe_name = sec.name.replace("/", "_").replace("\\", "_")
    status = section_status.get(sec.name, 'CUMPLE')
    layer_suffix = {'NO CUMPLE': 'NO_CUMPLE', 'FUERA DE TOLERANCIA': 'FUERA_TOL'}.get(
        status, 'CUMPLE')

    direction = azimuth_to_direction(sec.azimuth)
    ox, oy = sec.origin[0], sec.origin[1]

    design_3d = _profile_to_3d(pd_prof.distances, pd_prof.elevations, ox, oy, direction)
    if len(design_3d) > 1:
        _draw_3d_polyline(msp, design_3d, f'DISEÑO_{layer_suffix}')

    topo_3d = _profile_to_3d(pt_prof.distances, pt_prof.elevations, ox, oy, direction)
    if len(topo_3d) > 1:
        _draw_3d_polyline(msp, topo_3d, f'TOPO_{layer_suffix}')

    if p_d and p_d.benches:
        rd, re = build_reconciled_profile(p_d.benches)
        if len(rd) > 0:
            conc_d = _profile_to_3d(rd, re, ox, oy, direction)
            if len(conc_d) > 1:
                _draw_3d_polyline(msp, conc_d, 'CONCILIADO_DISEÑO')

    if p_t and p_t.benches:
        rt, ret = build_reconciled_profile(p_t.benches)
        if len(rt) > 0:
            conc_t = _profile_to_3d(rt, ret, ox, oy, direction)
            if len(conc_t) > 1:
                _draw_3d_polyline(msp, conc_t, 'CONCILIADO_TOPO')

    mid_z = float(max(pd_prof.elevations.max(), pt_prof.elevations.max())) + 3
    msp.add_text(
        f"{safe_name} [{status}]",
        dxfattribs={'height': 2.0, 'layer': 'ETIQUETAS', 'insert': (ox, oy, mid_z)})
