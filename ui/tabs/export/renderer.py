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
    _render_excel_export(config)
    st.divider()
    _render_images_export(config)
    st.divider()
    _render_word_report(config)
    st.divider()
    _render_dxf_export()


def _render_excel_export(config: dict) -> None:
    widgets.section_header("💾 Exportar Resultados a Excel")

    if not widgets.generate_button("📥 Generar Excel de Conciliación"):
        return

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
        widgets.download_button(
            "⬇️ Descargar Excel",
            bytes_data,
            file_name="Conciliacion_Diseno_vs_AsBuilt.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    widgets.success("✅ Excel generado exitosamente")


def _render_images_export(config: dict) -> None:
    widgets.section_header(
        "🖼️ Exportar Imágenes de Sección",
        "Genera un archivo ZIP con todos los gráficos de perfil en formato PNG, "
        "respetando los filtros y las vistas activas.",
    )

    if not widgets.generate_button("📦 Generar Imágenes (ZIP)"):
        return

    with widgets.spinner("Generando gráficos e imágenes..."):
        filtered_comps = _get_filtered_comparisons()
        if not filtered_comps:
            widgets.warning("⚠️ No hay datos que coincidan con los filtros activos.")
            return

        matching_section_names = {c['section'] for c in filtered_comps}
        sections = st.session_state.sections

        plot_options = _plot_options(config)

        processed_secs = st.session_state.get('processed_sections', []) or sections
        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])
        design_params_map, topo_params_map = _build_param_maps(
            processed_secs, params_d_list, params_t_list
        )

        profile_pairs = _collect_profile_pairs(list(matching_section_names))

        progress_bar = widgets.progress_bar(0.0)
        for i, sec in enumerate(sections):
            if sec.name in profile_pairs:
                progress_bar.progress((i + 1) / len(sections))

        zip_bytes = build_png_zip(
            sections,
            profile_pairs,
            design_params_map,
            topo_params_map,
            plot_options,
            df_pozos=st.session_state.get('blast_df_clean'),
            sections_full=st.session_state.get('sections'),
            filtered_comps=filtered_comps,
        )
        widgets.download_button(
            "⬇️ Descargar Imágenes ZIP",
            zip_bytes,
            file_name="Perfiles_Secciones.zip",
            mime="application/zip",
        )

    widgets.success("✅ Imágenes generadas exitosamente")


def _render_word_report(config: dict) -> None:
    widgets.section_header(
        "📄 Generar Informe Word (.docx)",
        "Genera un informe ejecutivo en formato Word con resumen de cumplimiento, "
        "gráficos detallados y tablas de parámetros por sección, aplicando los filtros activos.",
    )

    if not widgets.generate_button("📝 Generar Informe Word"):
        return

    with widgets.spinner("Generando informe Word..."):
        filtered_comps = _get_filtered_comparisons()
        if not filtered_comps:
            widgets.warning("⚠️ No hay datos que coincidan con los filtros activos.")
            return

        matching_section_names = {c['section'] for c in filtered_comps}
        sections = st.session_state.sections

        plot_options = _plot_options(config)

        processed_secs = st.session_state.get('processed_sections', []) or sections
        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])
        design_params_map, topo_params_map = _build_param_maps(
            processed_secs, params_d_list, params_t_list
        )

        profile_pairs = _collect_profile_pairs(list(matching_section_names))

        project_info = _project_info(config)
        doc_bytes = build_document(
            filtered_comps,
            sections,
            profile_pairs,
            design_params_map,
            topo_params_map,
            project_info,
            df_pozos=st.session_state.get('blast_df_clean'),
            sections_full=st.session_state.get('sections'),
            plot_options=plot_options,
        )
        widgets.download_button(
            "⬇️ Descargar Informe Word",
            doc_bytes,
            file_name="Informe_Conciliacion_Geotecnica.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
        )

    widgets.success("✅ Informe Word generado exitosamente")


def _render_dxf_export() -> None:
    widgets.section_header(
        "📐 Exportar Perfiles a DXF (3D)",
        "Genera un archivo DXF con polilíneas 3D separadas por cumplimiento, "
        "incluyendo perfiles conciliados.",
    )

    if not widgets.generate_button("📊 Generar DXF de Perfiles"):
        return

    with widgets.spinner("Generando DXF 3D de perfiles..."):
        processed_secs = st.session_state.get('processed_sections', [])
        if not processed_secs:
            processed_secs = st.session_state.get('sections', [])

        params_d_list = st.session_state.get('params_design', [])
        params_t_list = st.session_state.get('params_topo', [])
        design_params_map, topo_params_map = _build_param_maps(
            processed_secs, params_d_list, params_t_list
        )

        profile_pairs = _collect_profile_pairs([sec.name for sec in processed_secs])

        progress_bar = widgets.progress_bar(0.0)
        n_exported = len(profile_pairs)
        for i, sec in enumerate(processed_secs):
            progress_bar.progress((i + 1) / len(processed_secs))

        dxf_bytes, _ = build_dxf(
            processed_secs,
            profile_pairs,
            design_params_map,
            topo_params_map,
            comparison_results=st.session_state.comparison_results,
        )

        widgets.download_button(
            f"⬇️ Descargar DXF 3D ({n_exported} secciones)",
            dxf_bytes,
            file_name="Perfiles_3D.dxf",
            mime="application/dxf",
        )

    widgets.success(f"✅ {n_exported} perfiles exportados a DXF 3D exitosamente")
