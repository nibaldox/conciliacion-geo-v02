"""Step 2 renderer/orchestrator."""
import logging

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import SectionLine
from core.section_cutter import compute_local_azimuth
from ui.plots import draw_sections_on_figure
from ui.step2_sections.cutting import (
    generate_auto_sections,
    generate_file_sections,
    generate_manual_section,
    get_plan_view_vertices,
    parse_coord_file,
    sections_to_rows,
)
from ui.step2_sections.state import (
    add_sections,
    advance_step,
    append_interactive_section,
    clear_all_sections,
    clear_pending_names,
    clear_pending_sections,
    get_pending_names,
    get_sections,
    invalidate_profile_cache,
)
from ui.step2_sections.widgets import (
    auto_config_inputs,
    auto_generate_button,
    file_apply_button,
    file_config_inputs,
    interactive_apply_buttons,
    interactive_config_inputs,
    manual_apply_button,
    manual_section_inputs,
    manual_top_inputs,
    table_action_buttons,
)

logger = logging.getLogger(__name__)


def render_step2_inner() -> None:
    """Render Paso 2: section definition."""
    st.header("✂️ Paso 2: Definir Secciones de Corte")

    if st.session_state.mesh_design is None:
        st.warning(
            "⚠️ Debes cargar las superficies de diseño y topografía en el Paso 1 "
            "antes de definir secciones.")
        return

    tab_file, tab_interactive, tab_manual, tab_auto = st.tabs([
        "📂 Archivo de Coordenadas", "🗺️ Interactivo (Clic)",
        "📌 Manual", "🔄 Automático"])

    with tab_file:
        _render_tab_file()
    with tab_interactive:
        _render_tab_interactive()
    with tab_manual:
        _render_tab_manual()
    with tab_auto:
        _render_tab_auto()

    _render_sections_table()


def _render_tab_file() -> None:
    st.markdown("""
    Sube un archivo **CSV** (columnas X, Y) o **DXF** (Polyline/LWPolyline).
    Las secciones se generarán perpendiculares a cada segmento de la línea.
    """)

    coord_file = st.file_uploader(
        "Cargar coordenadas (CSV, DXF)", type=["csv", "txt", "dxf"], key="coord_file")

    spacing_file, len_up_file, len_down_file, sector_file, az_mode_file = file_config_inputs()

    if coord_file is None:
        return

    try:
        polyline = parse_coord_file(coord_file)
    except Exception:
        logger.exception("Failed to read coord file")
        st.error("No se pudo leer el archivo de coordenadas. Revisa la consola para detalles.")
        return

    if polyline is None or len(polyline) < 2:
        return

    st.success(f"✅ {len(polyline)} puntos cargados desde el archivo")
    st.caption(
        f"X: [{polyline[:,0].min():.1f}, {polyline[:,0].max():.1f}] | "
        f"Y: [{polyline[:,1].min():.1f}, {polyline[:,1].max():.1f}]")

    auto_mesh = st.session_state.mesh_design if "pendiente local" in az_mode_file else None
    preview_sections = generate_file_sections(
        polyline, spacing_file, len_up_file, len_down_file, sector_file,
        auto_mesh, coord_file.name)

    _render_file_preview(polyline, preview_sections)
    st.caption(f"Se generarán **{len(preview_sections)} secciones** cada {spacing_file:.0f}m")

    if file_apply_button():
        added = add_sections(preview_sections)
        advance_step()
        invalidate_profile_cache()
        st.success(
            f"✅ {len(added)} secciones añadidas. "
            f"Total acumulado: {len(st.session_state.sections)} secciones.")


def _render_file_preview(polyline, preview_sections) -> None:
    fig = go.Figure()
    sub = get_plan_view_vertices(st.session_state.mesh_design)

    fig.add_trace(go.Scatter(
        x=sub[:, 0], y=sub[:, 1], mode='markers',
        marker=dict(size=2, color=sub[:, 2], colorscale='Earth', showscale=False),
        name='Superficie', hoverinfo='skip'))
    fig.add_trace(go.Scatter(
        x=polyline[:, 0], y=polyline[:, 1],
        mode='lines+markers',
        line=dict(color='orange', width=3),
        marker=dict(size=6, color='orange'),
        name='Línea de evaluación'))

    draw_sections_on_figure(fig, preview_sections, is_3d=False)

    fig.update_layout(
        xaxis_title='Este (m)', yaxis_title='Norte (m)',
        yaxis=dict(scaleanchor='x', scaleratio=1),
        height=500, margin=dict(l=60, r=20, t=30, b=40))
    st.plotly_chart(fig, width="stretch")


def _render_tab_interactive() -> None:
    st.markdown("Haz clic sobre la vista de planta para colocar el origen de cada sección. "
                "El azimut se calcula automáticamente según la pendiente local del diseño.")

    len_up_int, len_down_int, sector_int, az_mode, manual_az_int = interactive_config_inputs()

    mesh_d = st.session_state.mesh_design
    sub = get_plan_view_vertices(mesh_d, max_points=8000)

    fig_plan = go.Figure()
    fig_plan.add_trace(go.Scatter(
        x=sub[:, 0], y=sub[:, 1], mode='markers',
        marker=dict(size=3, color=sub[:, 2], colorscale='Earth',
                    showscale=True, colorbar=dict(title="Elev (m)")),
        name='Diseño',
        hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<extra></extra>'))

    pending_names = get_pending_names()
    if pending_names:
        pending_secs_fig = [s for s in get_sections() if s.name in pending_names]
        draw_sections_on_figure(fig_plan, pending_secs_fig, is_3d=False)

    fig_plan.update_layout(
        xaxis_title='Este (m)', yaxis_title='Norte (m)',
        yaxis=dict(scaleanchor='x', scaleratio=1),
        height=600, margin=dict(l=60, r=20, t=30, b=40))

    try:
        event = st.plotly_chart(
            fig_plan, on_select="rerun", selection_mode=["points"], key="plan_select")

        if event and event.selection and event.selection.points:
            for pt in event.selection.points:
                px_val, py_val = pt['x'], pt['y']
                already = any(
                    abs(s.origin[0] - px_val) < 1 and abs(s.origin[1] - py_val) < 1
                    for s in get_sections())
                if not already:
                    origin = np.array([px_val, py_val])
                    az = (compute_local_azimuth(mesh_d, origin)
                          if az_mode == "Auto (pendiente local)" else manual_az_int)
                    pending_secs_n = [s for s in get_sections() if s.name in pending_names]
                    n = len(pending_secs_n) + 1
                    sec = SectionLine(
                        name=f"S-{n:02d}", origin=origin,
                        azimuth=az, length=len_up_int + len_down_int, sector=sector_int,
                        length_up=len_up_int, length_down=len_down_int)
                    append_interactive_section(sec)
    except TypeError:
        st.plotly_chart(fig_plan, key="plan_fallback")
        st.info("Actualiza Streamlit a >= 1.35 para selección interactiva. "
                "Mientras tanto usa la pestaña Manual.")

    pending_secs = [s for s in get_sections() if s.name in pending_names]
    if pending_secs:
        st.subheader(f"📍 {len(pending_secs)} secciones colocadas")
        st.dataframe(sections_to_rows(pending_secs, pending_names), width="stretch")

    apply_clicked, clear_clicked = interactive_apply_buttons()
    if apply_clicked:
        if pending_secs:
            clear_pending_names()
            advance_step()
            st.success(f"✅ {len(pending_secs)} secciones aplicadas")
    if clear_clicked:
        clear_pending_sections()
        st.rerun()


def _render_tab_manual() -> None:
    st.markdown("Define cada sección con un punto de origen (X, Y), azimut y longitud.")

    n_sections, auto_az_manual = manual_top_inputs()

    bd = st.session_state.bounds_design
    cx, cy = bd['center'][0], bd['center'][1]

    sections_manual = []
    for i in range(n_sections):
        name, sector, ox, oy, az, len_up, len_down = manual_section_inputs(
            i, cx, cy, auto_az_manual, st.session_state.mesh_design)
        sections_manual.append(generate_manual_section(
            name, sector, ox, oy, az, len_up, len_down))

    if manual_apply_button():
        added = add_sections(sections_manual)
        advance_step()
        invalidate_profile_cache()
        st.success(
            f"✅ {len(added)} secciones añadidas. "
            f"Total acumulado: {len(st.session_state.sections)} secciones.")


def _render_tab_auto() -> None:
    st.markdown("Genera secciones equiespaciadas a lo largo de una línea (ej: cresta del pit).")

    bd = st.session_state.bounds_design
    x1, y1, x2, y2, n_auto, len_up_auto, len_down_auto, sector_auto, az_method, fixed_az = auto_config_inputs(bd)

    if auto_generate_button():
        sections_auto = generate_auto_sections(
            st.session_state.mesh_design,
            np.array([x1, y1]), np.array([x2, y2]),
            n_auto, az_method, fixed_az, len_up_auto, len_down_auto, sector_auto)
        added = add_sections(sections_auto)
        advance_step()
        invalidate_profile_cache()
        st.success(
            f"✅ {len(added)} secciones generadas. "
            f"Total acumulado: {len(st.session_state.sections)} secciones.")


def _render_sections_table() -> None:
    sections = get_sections()
    if sections:
        st.subheader(f"📋 Total acumulado: {len(sections)} secciones")
        cols_tbl = st.columns([5, 1, 1])
        clear_pending, clear_all = table_action_buttons(cols_tbl[1], cols_tbl[2])
        if clear_pending:
            clear_pending_sections()
            st.rerun()
        if clear_all:
            clear_all_sections()
            st.rerun()
        with cols_tbl[0]:
            st.dataframe(sections_to_rows(sections, get_pending_names()), width="stretch")
