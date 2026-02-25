"""
Results tab: export to Excel, PNG images (ZIP), and DXF 3D profiles.
"""
import os
import tempfile
from datetime import datetime

import streamlit as st

from core import cut_both_surfaces, generate_section_images_zip
from core.param_extractor import build_reconciled_profile
from core.section_cutter import azimuth_to_direction


def render_tab_export(config: dict) -> None:
    _render_excel_export(config)
    st.divider()
    _render_images_export()
    st.divider()
    _render_dxf_export()


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
            config['tolerances'], output_path, project_info)

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

def _render_images_export() -> None:
    st.subheader("🖼️ Exportar Imágenes de Sección")
    st.write("Genera un archivo ZIP con todos los gráficos de perfil en formato PNG.")

    if not st.button("📦 Generar Imágenes (ZIP)", type="primary"):
        return

    with st.spinner("Generando gráficos e imágenes..."):
        all_data_for_images = []
        progress_bar = st.progress(0)
        sections = st.session_state.sections

        for i, sec in enumerate(sections):
            pd_prof, pt_prof = cut_both_surfaces(
                st.session_state.mesh_design,
                st.session_state.mesh_topo,
                sec)

            if (pd_prof and pt_prof
                    and i < len(st.session_state.params_design)
                    and i < len(st.session_state.params_topo)):
                all_data_for_images.append({
                    'section_name': sec.name,
                    'params_design': st.session_state.params_design[i],
                    'params_topo': st.session_state.params_topo[i],
                    'profile_d': (pd_prof.distances, pd_prof.elevations),
                    'profile_t': (pt_prof.distances, pt_prof.elevations),
                })
            progress_bar.progress((i + 1) / len(sections))

        zip_bytes = generate_section_images_zip(all_data_for_images)
        st.download_button(
            label="⬇️ Descargar Imágenes ZIP",
            data=zip_bytes,
            file_name="Perfiles_Secciones.zip",
            mime="application/zip")

    st.success("✅ Imágenes generadas exitosamente")


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

        progress_bar = st.progress(0)
        n_exported = 0
        sections = st.session_state.sections

        for i, sec in enumerate(sections):
            pd_prof, pt_prof = cut_both_surfaces(
                st.session_state.mesh_design,
                st.session_state.mesh_topo,
                sec)

            if pd_prof and pt_prof:
                _write_section_to_dxf(
                    msp, sec, i, pd_prof, pt_prof, section_status)
                n_exported += 1

            progress_bar.progress((i + 1) / len(sections))

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
    for j in range(len(pts) - 1):
        msp.add_line(pts[j], pts[j + 1], dxfattribs={'layer': layer})


def _write_section_to_dxf(msp, sec, i, pd_prof, pt_prof, section_status) -> None:
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

    params_design = st.session_state.params_design
    params_topo = st.session_state.params_topo

    if i < len(params_design) and params_design[i] and params_design[i].benches:
        rd, re = build_reconciled_profile(params_design[i].benches)
        if len(rd) > 0:
            conc_d = _profile_to_3d(rd, re, ox, oy, direction)
            if len(conc_d) > 1:
                _draw_3d_polyline(msp, conc_d, 'CONCILIADO_DISEÑO')

    if i < len(params_topo) and params_topo[i] and params_topo[i].benches:
        rt, ret = build_reconciled_profile(params_topo[i].benches)
        if len(rt) > 0:
            conc_t = _profile_to_3d(rt, ret, ox, oy, direction)
            if len(conc_t) > 1:
                _draw_3d_polyline(msp, conc_t, 'CONCILIADO_TOPO')

    mid_z = float(max(pd_prof.elevations.max(), pt_prof.elevations.max())) + 3
    msp.add_text(
        f"{safe_name} [{status}]",
        dxfattribs={'height': 2.0, 'layer': 'ETIQUETAS', 'insert': (ox, oy, mid_z)})
