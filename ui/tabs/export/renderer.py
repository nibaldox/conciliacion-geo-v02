"""Export tab orchestrator."""
from datetime import datetime
from typing import Any

import streamlit as st

from ui.tabs.export import widgets
from ui.tabs.export.common import _get_filtered_comparisons, _get_profile_pair
from ui.tabs.export.dxf import build_dxf
from ui.tabs.export.excel import build_workbook
from ui.tabs.export.png import build_png_zip
from ui.tabs.export.word import build_document


def _project_info(config: dict) -> dict:
    return {
        'project': config['project_name'],
        'operation': config['operation'],
        'phase': config['phase'],
        'author': config['author'],
        'date': datetime.now().strftime("%d/%m/%Y"),
    }


def _plot_options(config: dict) -> dict:
    return {
        'show_reconciled': st.session_state.get('show_reconciled', True),
        'show_areas': st.session_state.get('show_areas', False),
        'show_semaphore': st.session_state.get('show_semaphore', False),
        'show_pozos': st.session_state.get('show_pozos_profile', True),
        'blast_tolerance': st.session_state.get('blast_tol_profile', 10.0),
        'grid_height': config.get('grid_height', 15.0),
        'grid_ref': config.get('grid_ref', 0.0),
        'tolerances': config.get('tolerances'),
    }


def _build_param_maps(processed_sections: list, params_design: list, params_topo: list) -> tuple[dict, dict]:
    design_params_map = {}
    topo_params_map = {}
    for idx, sec in enumerate(processed_sections):
        if idx < len(params_design):
            design_params_map[sec.name] = params_design[idx]
        if idx < len(params_topo):
            topo_params_map[sec.name] = params_topo[idx]
    return design_params_map, topo_params_map


def _collect_profile_pairs(section_names: list) -> dict[str, tuple]:
    pairs = {}
    for name in section_names:
        pd_prof, pt_prof = _get_profile_pair(name)
        if pd_prof is not None and pt_prof is not None:
            pairs[name] = (pd_prof, pt_prof)
    return pairs


def render_tab_export(config: dict) -> None:
    """Tab Exportar — 5 botones de generación en una sola fila."""
    widgets.section_header(
        "📤 Exportar Resultados",
        "Selecciona un formato para generar el archivo de exportación correspondiente.",
    )

    cols = st.columns(5)
    generated = {}

    with cols[0]:
        if st.button("💾 Excel", type="primary", use_container_width=True):
            generated['excel'] = _generate_excel(config)

    with cols[1]:
        if st.button("📄 PDF", type="primary", use_container_width=True):
            generated['pdf'] = _generate_pdf(config)

    with cols[2]:
        if st.button("📦 Imágenes", type="primary", use_container_width=True):
            generated['images'] = _generate_images(config)

    with cols[3]:
        if st.button("📝 Word", type="primary", use_container_width=True):
            generated['word'] = _generate_word(config)

    with cols[4]:
        if st.button("📐 DXF 3D", type="primary", use_container_width=True):
            generated['dxf'] = _generate_dxf()

    st.divider()

    # Mostrar botones de descarga para lo que se generó
    for fmt, payload in generated.items():
        _render_download(fmt, payload)


def _render_download(fmt: str, payload: dict) -> None:
    """Muestra el botón de descarga para un archivo generado."""
    if payload is None:
        return  # El generator ya mostró el warning
    label = payload.get('label', 'Descargar')
    data = payload.get('data')
    file_name = payload.get('file_name')
    mime = payload.get('mime')
    icon = payload.get('icon', '⬇️')
    st.success(f"{icon} {label} listo para descargar.")
    st.download_button(
        f"⬇️ Descargar {fmt.upper()}",
        data=data,
        file_name=file_name,
        mime=mime,
        type="primary",
    )


def _generate_excel(config: dict) -> dict:
    """Genera el Excel y retorna el payload para descarga."""
    with widgets.spinner("Generando Excel..."):
        project_info = _project_info(config)
        bytes_data = build_workbook(
            st.session_state.comparison_results,
            st.session_state.params_design,
            st.session_state.params_topo,
            config['tolerances'],
            project_info,
            df_pozos=st.session_state.get('blast_df_clean'),
            sections=st.session_state.get('sections'),
        )
    return {
        'label': 'Excel de Conciliación',
        'data': bytes_data,
        'file_name': 'Conciliacion_Diseno_vs_AsBuilt.xlsx',
        'mime': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'icon': '💾',
    }


def _generate_pdf(config: dict) -> dict:
    """Genera el PDF ejecutivo y retorna el payload para descarga."""
    from core.pdf_report import generate_pdf_report
    import tempfile

    with widgets.spinner("Generando PDF..."):
        project_info = _project_info(config)
        tmp_path = tempfile.mktemp(suffix=".pdf")
        mesh_topo = st.session_state.get('mesh_topo')
        grid_ref = float(config.get('grid_ref', 0.0))
        sections = st.session_state.get('sections', [])
        generate_pdf_report(
            st.session_state.comparison_results,
            [{"section_name": s.name} for s in sections],
            tmp_path,
            project_info=project_info,
            sections=sections,
            mesh_topo=mesh_topo,
            grid_ref=grid_ref,
        )
        with open(tmp_path, "rb") as f:
            pdf_bytes = f.read()
    return {
        'label': 'PDF Ejecutivo',
        'data': pdf_bytes,
        'file_name': 'Conciliacion_Geotecnica.pdf',
        'mime': 'application/pdf',
        'icon': '📄',
    }


def _generate_images(config: dict) -> dict | None:
    """Genera el ZIP de imágenes y retorna el payload para descarga."""
    with widgets.spinner("Generando gráficos e imágenes..."):
        filtered_comps = _get_filtered_comparisons()
        if not filtered_comps:
            st.warning("⚠️ No hay datos que coincidan con los filtros activos.")
            return None

        matching_section_names = {c['section'] for c in filtered_comps}
        sections = st.session_state.sections
        plot_options = _plot_options(config)
        processed_secs = st.session_state.get('processed_sections', []) or sections
        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])
        design_params_map, topo_params_map = _build_param_maps(
            processed_secs, params_d_list, params_t_list)
        profile_pairs = _collect_profile_pairs(list(matching_section_names))

        zip_bytes = build_png_zip(
            sections, profile_pairs, design_params_map, topo_params_map,
            plot_options,
            df_pozos=st.session_state.get('blast_df_clean'),
            sections_full=st.session_state.get('sections'),
            filtered_comps=filtered_comps,
        )
    return {
        'label': 'Imágenes ZIP',
        'data': zip_bytes,
        'file_name': 'Perfiles_Secciones.zip',
        'mime': 'application/zip',
        'icon': '📦',
    }


def _generate_word(config: dict) -> dict | None:
    """Genera el informe Word y retorna el payload para descarga."""
    with widgets.spinner("Generando informe Word..."):
        filtered_comps = _get_filtered_comparisons()
        if not filtered_comps:
            st.warning("⚠️ No hay datos que coincidan con los filtros activos.")
            return None

        matching_section_names = {c['section'] for c in filtered_comps}
        sections = st.session_state.sections
        plot_options = _plot_options(config)
        processed_secs = st.session_state.get('processed_sections', []) or sections
        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])
        design_params_map, topo_params_map = _build_param_maps(
            processed_secs, params_d_list, params_t_list)
        profile_pairs = _collect_profile_pairs(list(matching_section_names))

        project_info = _project_info(config)
        doc_bytes = build_document(
            filtered_comps, sections, profile_pairs,
            design_params_map, topo_params_map,
            project_info,
            df_pozos=st.session_state.get('blast_df_clean'),
            sections_full=st.session_state.get('sections'),
            plot_options=plot_options,
        )
    return {
        'label': 'Informe Word',
        'data': doc_bytes,
        'file_name': 'Informe_Conciliacion_Geotecnica.docx',
        'mime': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'icon': '📝',
    }


def _generate_dxf() -> dict:
    """Genera el DXF 3D y retorna el payload para descarga."""
    with widgets.spinner("Generando DXF 3D..."):
        processed_secs = st.session_state.get('processed_sections', [])
        if not processed_secs:
            processed_secs = st.session_state.get('sections', [])

        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])
        design_params_map, topo_params_map = _build_param_maps(
            processed_secs, params_d_list, params_t_list)
        profile_pairs = _collect_profile_pairs([sec.name for sec in processed_secs])

        dxf_bytes, _ = build_dxf(
            processed_secs, profile_pairs,
            design_params_map, topo_params_map,
            comparison_results=st.session_state.comparison_results,
        )
        n_exported = len(profile_pairs)
    return {
        'label': f'DXF 3D ({n_exported} secciones)',
        'data': dxf_bytes,
        'file_name': 'Perfiles_3D.dxf',
        'mime': 'application/dxf',
        'icon': '📐',
    }
