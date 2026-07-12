"""
Step 2: Define cut sections via four input methods:
  - File (CSV / DXF polyline)
  - Interactive (click on plan)
  - Manual (form per section)
  - Auto (equispaced along a crest line)
"""
import io
import logging
import os
import tempfile

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import SectionLine
from core.section_cutter import (
    azimuth_to_direction,
    compute_local_azimuth,
    generate_perpendicular_sections,
    generate_sections_along_crest,
)
from ui.plots import draw_sections_on_figure

logger = logging.getLogger(__name__)


def render_step2() -> None:
    """Render Paso 2: section definition."""
    st.header("✂️ Paso 2: Definir Secciones de Corte")

    if st.session_state.mesh_design is None:
        st.warning("⚠️ Debes cargar las superficies de diseño y topografía en el Paso 1 antes de definir secciones.")
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


# ---------------------------------------------------------------------------
# Tab: File
# ---------------------------------------------------------------------------

def _render_tab_file() -> None:
    st.markdown("""
    Sube un archivo **CSV** (columnas X, Y) o **DXF** (Polyline/LWPolyline).
    Las secciones se generarán perpendiculares a cada segmento de la línea.
    """)

    coord_file = st.file_uploader(
        "Cargar coordenadas (CSV, DXF)", type=["csv", "txt", "dxf"], key="coord_file")

    cols_file = st.columns(5)
    spacing_file = cols_file[0].number_input(
        "Distancia entre perfiles (m)", value=20.0, min_value=1.0, step=5.0, key="spacing_file")
    len_up_file = cols_file[1].number_input(
        "Long. Arriba (m)", value=100.0, min_value=5.0, key="len_up_file")
    len_down_file = cols_file[2].number_input(
        "Long. Abajo (m)", value=100.0, min_value=5.0, key="len_down_file")
    sector_file = cols_file[3].text_input("Sector", "Principal", key="sector_file")
    az_mode_file = cols_file[4].selectbox(
        "Azimut",
        ["Perpendicular a la línea (Recomendado)", "Auto (pendiente local - Ruidoso)"],
        key="az_mode_file")

    if coord_file is None:
        return

    try:
        polyline = _parse_coord_file(coord_file)
    except Exception as e:
        logger.exception("Failed to read coord file")
        st.error("No se pudo leer el archivo de coordenadas. Revisa la consola para detalles.")
        return

    if polyline is None or len(polyline) < 2:
        return

    st.success(f"✅ {len(polyline)} puntos cargados desde el archivo")
    st.caption(
        f"X: [{polyline[:,0].min():.1f}, {polyline[:,0].max():.1f}] | "
        f"Y: [{polyline[:,1].min():.1f}, {polyline[:,1].max():.1f}]")

    auto_mesh = (st.session_state.mesh_design if "pendiente local" in az_mode_file else None)
    preview_sections = generate_perpendicular_sections(
        polyline, spacing_file, len_up_file + len_down_file, sector_file,
        design_mesh=auto_mesh, length_up=len_up_file, length_down=len_down_file)

    file_base, _ = os.path.splitext(coord_file.name)
    for j, sec in enumerate(preview_sections):
        sec.file_name = coord_file.name
        sec.name = f"S{j+1:02d}-{file_base}"

    _render_file_preview(polyline, preview_sections)
    st.caption(f"Se generarán **{len(preview_sections)} secciones** cada {spacing_file:.0f}m")

    if st.button("✅ Aplicar Secciones desde Archivo", type="primary", key="apply_file"):
        if not st.session_state.get('sections'):
            st.session_state.sections = []
        existing_names = {s.name for s in st.session_state.sections}
        added_count = 0
        for sec in preview_sections:
            target_name = sec.name
            if target_name in existing_names:
                col_idx = 1
                while f"{target_name}_{col_idx}" in existing_names:
                    col_idx += 1
                sec.name = f"{target_name}_{col_idx}"
            st.session_state.sections.append(sec)
            existing_names.add(sec.name)
            st.session_state.pending_section_names.add(sec.name)
            added_count += 1
        st.session_state.step = max(st.session_state.step, 3)
        st.success(f"✅ {added_count} secciones añadidas. Total acumulado: {len(st.session_state.sections)} secciones.")


def _parse_coord_file(coord_file):
    """Parse CSV or DXF coordinate file and return Nx2 numpy array."""
    import pandas as pd

    filename = coord_file.name.lower()

    if filename.endswith('.dxf'):
        from core import load_dxf_polyline
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            f.write(coord_file.read())
            tmp_path = f.name
        try:
            polyline = load_dxf_polyline(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        if len(polyline) == 0:
            st.error("No se encontraron polilíneas válidas en el DXF.")
            return None
        return polyline

    # CSV / TXT
    content = coord_file.read().decode('utf-8')
    df_coords = pd.read_csv(io.StringIO(content), nrows=10000)

    x_col = next((c for c in df_coords.columns
                  if c.strip().upper() in ('X', 'ESTE', 'EAST', 'E')), None)
    y_col = next((c for c in df_coords.columns
                  if c.strip().upper() in ('Y', 'NORTE', 'NORTH', 'N')), None)

    if x_col is None or y_col is None:
        num_cols = df_coords.select_dtypes(include=[np.number]).columns
        if len(num_cols) >= 2:
            x_col, y_col = num_cols[0], num_cols[1]
        else:
            st.error("No se encontraron columnas X, Y en el archivo.")
            return None

    return df_coords[[x_col, y_col]].dropna().values.astype(float)


def _render_file_preview(polyline, preview_sections) -> None:
    fig = go.Figure()
    mesh_d = st.session_state.mesh_design
    verts = mesh_d.vertices
    step_v = max(1, len(verts) // 5000)
    sub = verts[::step_v]

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


# ---------------------------------------------------------------------------
# Tab: Interactive
# ---------------------------------------------------------------------------

def _render_tab_interactive() -> None:
    st.markdown("Haz clic sobre la vista de planta para colocar el origen de cada sección. "
                "El azimut se calcula automáticamente según la pendiente local del diseño.")

    cols_cfg = st.columns(4)
    len_up_int = cols_cfg[0].number_input(
        "Long. Arriba (m)", value=100.0, min_value=5.0, key="len_up_int")
    len_down_int = cols_cfg[1].number_input(
        "Long. Abajo (m)", value=100.0, min_value=5.0, key="len_down_int")
    sector_int = cols_cfg[2].text_input("Sector", "Principal", key="sector_int")
    az_mode = cols_cfg[3].selectbox(
        "Azimut", ["Auto (pendiente local)", "Manual"], key="az_mode_int")
    manual_az_int = 0.0
    if az_mode == "Manual":
        manual_az_int = st.number_input("Azimut manual (°)", 0.0, 360.0, 0.0, key="man_az_int")

    mesh_d = st.session_state.mesh_design
    verts = mesh_d.vertices
    step_v = max(1, len(verts) // 8000)
    sub = verts[::step_v]

    fig_plan = go.Figure()
    fig_plan.add_trace(go.Scatter(
        x=sub[:, 0], y=sub[:, 1], mode='markers',
        marker=dict(size=3, color=sub[:, 2], colorscale='Earth',
                    showscale=True, colorbar=dict(title="Elev (m)")),
        name='Diseño',
        hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<extra></extra>'))

    if st.session_state.pending_section_names:
        pending_secs_fig = [s for s in st.session_state.sections
                            if s.name in st.session_state.pending_section_names]
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
                    for s in st.session_state.sections)
                if not already:
                    origin = np.array([px_val, py_val])
                    az = (compute_local_azimuth(mesh_d, origin)
                          if az_mode == "Auto (pendiente local)" else manual_az_int)
                    pending_secs_n = [s for s in st.session_state.sections
                                      if s.name in st.session_state.pending_section_names]
                    n = len(pending_secs_n) + 1
                    sec = SectionLine(
                        name=f"S-{n:02d}", origin=origin,
                        azimuth=az, length=len_up_int + len_down_int, sector=sector_int,
                        length_up=len_up_int, length_down=len_down_int)
                    st.session_state.sections.append(sec)
                    st.session_state.pending_section_names.add(sec.name)
    except TypeError:
        st.plotly_chart(fig_plan, key="plan_fallback")
        st.info("Actualiza Streamlit a >= 1.35 para selección interactiva. "
                "Mientras tanto usa la pestaña Manual.")

    pending_secs = [s for s in st.session_state.sections
                    if s.name in st.session_state.pending_section_names]
    if pending_secs:
        st.subheader(f"📍 {len(pending_secs)} secciones colocadas")
        st.dataframe(_sections_to_rows(pending_secs), width="stretch")

    cols_btn = st.columns(2)
    if cols_btn[0].button("✅ Aplicar Secciones", type="primary", key="apply_int"):
        if pending_secs:
            st.session_state.pending_section_names.clear()
            st.session_state.step = max(st.session_state.step, 3)
            st.success(f"✅ {len(pending_secs)} secciones aplicadas")
    if cols_btn[1].button("🗑️ Limpiar", key="clear_int"):
        st.session_state.sections = [
            s for s in st.session_state.sections
            if s.name not in st.session_state.pending_section_names
        ]
        st.session_state.pending_section_names.clear()
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Manual
# ---------------------------------------------------------------------------

def _render_tab_manual() -> None:
    st.markdown("Define cada sección con un punto de origen (X, Y), azimut y longitud.")

    cols_top = st.columns(2)
    n_sections = cols_top[0].number_input(
        "Número de secciones a definir", min_value=1, max_value=50, value=5)
    auto_az_manual = cols_top[1].checkbox(
        "Auto-detectar azimut desde diseño", value=False, key="auto_az_manual")

    bd = st.session_state.bounds_design
    cx, cy = bd['center'][0], bd['center'][1]

    sections_manual = []
    for i in range(n_sections):
        with st.expander(f"Sección S-{i+1:02d}", expanded=(i == 0)):
            cols = st.columns(5)
            name = cols[0].text_input("Nombre", f"S-{i+1:02d}", key=f"sname_{i}")
            sector = cols[1].text_input("Sector", "", key=f"ssector_{i}")

            cols2 = st.columns(5)
            ox = cols2[0].number_input("Origen X", value=float(cx), format="%.1f", key=f"sox_{i}")
            oy = cols2[1].number_input("Origen Y", value=float(cy), format="%.1f", key=f"soy_{i}")

            if auto_az_manual:
                az = compute_local_azimuth(st.session_state.mesh_design, np.array([ox, oy]))
                cols2[2].text_input("Azimut (°)", value=f"{az:.1f}", disabled=True, key=f"saz_{i}")
            else:
                az = cols2[2].number_input("Azimut (°)", value=0.0, min_value=0.0,
                                           max_value=360.0, key=f"saz_{i}")

            len_up = cols2[3].number_input("Long. Arriba (m)", value=100.0, min_value=5.0, key=f"slen_up_{i}")
            len_down = cols2[4].number_input("Long. Abajo (m)", value=100.0, min_value=5.0, key=f"slen_down_{i}")
            sections_manual.append(SectionLine(
                name=name, origin=np.array([ox, oy]),
                azimuth=az, length=len_up + len_down, sector=sector,
                length_up=len_up, length_down=len_down))

    if st.button("✅ Aplicar Secciones Manuales", type="primary"):
        if not st.session_state.get('sections'):
            st.session_state.sections = []
        existing_names = {s.name for s in st.session_state.sections}
        added_count = 0
        for sec in sections_manual:
            target_name = sec.name
            if target_name in existing_names:
                col_idx = 1
                while f"{target_name}_{col_idx}" in existing_names:
                    col_idx += 1
                sec.name = f"{target_name}_{col_idx}"
            st.session_state.sections.append(sec)
            existing_names.add(sec.name)
            st.session_state.pending_section_names.add(sec.name)
            added_count += 1
        st.session_state.step = max(st.session_state.step, 3)
        st.success(f"✅ {added_count} secciones añadidas. Total acumulado: {len(st.session_state.sections)} secciones.")


# ---------------------------------------------------------------------------
# Tab: Auto
# ---------------------------------------------------------------------------

def _render_tab_auto() -> None:
    st.markdown("Genera secciones equiespaciadas a lo largo de una línea (ej: cresta del pit).")

    bd = st.session_state.bounds_design
    cols = st.columns(4)
    x1 = cols[0].number_input("Punto inicio X", value=float(bd['xmin']), format="%.1f")
    y1 = cols[1].number_input("Punto inicio Y", value=float(bd['center'][1]), format="%.1f")
    x2 = cols[2].number_input("Punto fin X", value=float(bd['xmax']), format="%.1f")
    y2 = cols[3].number_input("Punto fin Y", value=float(bd['center'][1]), format="%.1f")

    cols2 = st.columns(4)
    n_auto = cols2[0].number_input("N° de secciones", min_value=2, max_value=50, value=5)
    len_up_auto = cols2[1].number_input("Long. Arriba (m)", value=100.0, min_value=5.0)
    len_down_auto = cols2[2].number_input("Long. Abajo (m)", value=100.0, min_value=5.0)
    sector_auto = cols2[3].text_input("Sector", "Sector Principal", key="sector_auto_txt")

    az_method = st.radio(
        "Método de Azimut",
        ["Perpendicular a la línea (Recomendado)", "Fijo", "Auto (pendiente local - Ruidoso)"],
        index=0, horizontal=True)

    fixed_az = 0.0
    if az_method == "Fijo":
        fixed_az = st.number_input("Azimut fijo (°)", value=0.0, min_value=0.0, max_value=360.0)

    if st.button("🔄 Generar Secciones Automáticas", type="primary"):
        gen_az = None
        if az_method == "Fijo":
            gen_az = fixed_az
        elif az_method == "Auto (pendiente local - Ruidoso)":
            gen_az = 0.0

        sections_auto = generate_sections_along_crest(
            st.session_state.mesh_design,
            np.array([x1, y1]), np.array([x2, y2]),
            n_auto, gen_az, len_up_auto + len_down_auto, sector_auto,
            length_up=len_up_auto, length_down=len_down_auto)

        if az_method == "Auto (pendiente local - Ruidoso)":
            for sec in sections_auto:
                sec.azimuth = compute_local_azimuth(st.session_state.mesh_design, sec.origin)

        if not st.session_state.get('sections'):
            st.session_state.sections = []
        existing_names = {s.name for s in st.session_state.sections}
        added_count = 0
        for sec in sections_auto:
            target_name = sec.name
            if target_name in existing_names:
                col_idx = 1
                while f"{target_name}_{col_idx}" in existing_names:
                    col_idx += 1
                sec.name = f"{target_name}_{col_idx}"
            st.session_state.sections.append(sec)
            existing_names.add(sec.name)
            st.session_state.pending_section_names.add(sec.name)
            added_count += 1
        st.session_state.step = max(st.session_state.step, 3)
        st.success(f"✅ {added_count} secciones generadas. Total acumulado: {len(st.session_state.sections)} secciones.")


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

def _sections_to_rows(sections) -> list:
    pending = st.session_state.get('pending_section_names', set())
    return [
        {"Estado": "⚠ Pendiente" if s.name in pending else "Aplicada",
         "Nombre": s.name, "Archivo": getattr(s, 'file_name', ''), "Sector": s.sector,
         "Origen X": f"{s.origin[0]:.1f}", "Origen Y": f"{s.origin[1]:.1f}",
         "Azimut (°)": f"{s.azimuth:.1f}",
         "Long. Arriba (m)": f"{s.length_up:.1f}" if getattr(s, 'length_up', None) is not None else f"{s.length/2:.1f}",
         "Long. Abajo (m)": f"{s.length_down:.1f}" if getattr(s, 'length_down', None) is not None else f"{s.length/2:.1f}",
         "Longitud Total (m)": f"{s.length:.1f}"}
        for s in sections
    ]


def _render_sections_table() -> None:
    if st.session_state.sections:
        st.subheader(f"📋 Total acumulado: {len(st.session_state.sections)} secciones")
        cols_tbl = st.columns([5, 1, 1])
        with cols_tbl[0]:
            st.dataframe(_sections_to_rows(st.session_state.sections), width="stretch")
        with cols_tbl[1]:
            if st.button("🗑️ Limpiar Pendientes", key="clear_pending_btn", type="secondary"):
                st.session_state.sections = [
                    s for s in st.session_state.sections
                    if s.name not in st.session_state.pending_section_names
                ]
                st.session_state.pending_section_names.clear()
                st.rerun()
        with cols_tbl[2]:
            if st.button("🗑️ Limpiar Todas", key="clear_all_sections_btn", type="secondary"):
                st.session_state.sections = []
                st.session_state.pending_section_names.clear()
                st.rerun()
