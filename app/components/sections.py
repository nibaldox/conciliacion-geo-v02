"""Paso 2: Definir secciones de corte — 4 tabs (archivo, interactivo, manual, automático)."""
import streamlit as st
import numpy as np
import plotly.graph_objects as go
import tempfile
import os
import io

from core import SectionLine, load_dxf_polyline
from core.section_cutter import (
    azimuth_to_direction as _az2dir,
    compute_local_azimuth,
    generate_perpendicular_sections,
    generate_sections_along_crest,
)


def render_sections_section():
    """Render the section definition UI (4 tabs).

    Returns:
        List of SectionLine if sections are defined, None otherwise.
        Sections are also stored in st.session_state.sections.
    """
    if st.session_state.step < 2:
        return None

    st.header("✂️ Paso 2: Definir Secciones de Corte")

    tab_file, tab_interactive, tab_manual, tab_auto = st.tabs([
        "📂 Archivo de Coordenadas", "🗺️ Interactivo (Clic)",
        "📌 Manual", "🔄 Automático"])

    _render_tab_file(tab_file)
    _render_tab_interactive(tab_interactive)
    _render_tab_manual(tab_manual)
    _render_tab_auto(tab_auto)

    # Show sections table
    if st.session_state.sections:
        st.subheader("📋 Secciones Definidas")
        sec_data = []
        for s in st.session_state.sections:
            sec_data.append({
                "Nombre": s.name, "Sector": s.sector,
                "Origen X": f"{s.origin[0]:.1f}", "Origen Y": f"{s.origin[1]:.1f}",
                "Azimut (°)": f"{s.azimuth:.1f}", "Longitud (m)": f"{s.length:.1f}"
            })
        st.dataframe(sec_data, use_container_width=True)

    return st.session_state.sections if st.session_state.sections else None


def _render_tab_file(tab):
    """Tab: Load sections from CSV or DXF coordinate file."""
    with tab:
        st.markdown("""
        Sube un archivo **CSV** (columnas X, Y) o **DXF** (Polyline/LWPolyline).
        Las secciones se generarán perpendiculares a cada segmento de la línea.
        """)

        coord_file = st.file_uploader(
            "Cargar coordenadas (CSV, DXF)", type=["csv", "txt", "dxf"], key="coord_file")

        cols_file = st.columns(4)
        spacing_file = cols_file[0].number_input(
            "Distancia entre perfiles (m)", value=20.0, min_value=1.0, step=5.0,
            key="spacing_file")
        length_file = cols_file[1].number_input(
            "Longitud de sección (m)", value=200.0, min_value=10.0, key="len_file")
        sector_file = cols_file[2].text_input(
            "Sector", "Principal", key="sector_file")
        az_mode_file = cols_file[3].selectbox(
            "Azimut", ["Perpendicular a la línea (Recomendado)", "Auto (pendiente local - Ruidoso)"],
            key="az_mode_file")

        if coord_file is not None:
            try:
                import pandas as pd
                filename = coord_file.name.lower()
                polyline = None

                if filename.endswith('.dxf'):
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
                else:
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
                            x_col = y_col = None

                    if x_col is not None and y_col is not None:
                        polyline = df_coords[[x_col, y_col]].dropna().values.astype(float)

                if polyline is not None and len(polyline) > 1:
                    st.success(f"✅ {len(polyline)} puntos cargados desde el archivo")
                    st.caption(
                        f"X: [{polyline[:, 0].min():.1f}, {polyline[:, 0].max():.1f}] | "
                        f"Y: [{polyline[:, 1].min():.1f}, {polyline[:, 1].max():.1f}]")

                    # Preview polyline on a small plan view
                    fig_preview = go.Figure()
                    mesh_d = st.session_state.mesh_design
                    verts = mesh_d.vertices
                    step_v = max(1, len(verts) // 5000)
                    sub = verts[::step_v]
                    fig_preview.add_trace(go.Scatter(
                        x=sub[:, 0], y=sub[:, 1], mode='markers',
                        marker=dict(size=2, color=sub[:, 2], colorscale='Earth',
                                    showscale=False),
                        name='Superficie', hoverinfo='skip',
                    ))
                    fig_preview.add_trace(go.Scatter(
                        x=polyline[:, 0], y=polyline[:, 1],
                        mode='lines+markers',
                        line=dict(color='orange', width=3),
                        marker=dict(size=6, color='orange'),
                        name='Línea de evaluación',
                    ))

                    auto_mesh = (st.session_state.mesh_design
                                 if "pendiente local" in az_mode_file else None)
                    preview_sections = generate_perpendicular_sections(
                        polyline, spacing_file, length_file, sector_file, design_mesh=auto_mesh)

                    for sec in preview_sections:
                        d = _az2dir(sec.azimuth)
                        p1 = sec.origin - d * sec.length / 2
                        p2 = sec.origin + d * sec.length / 2
                        fig_preview.add_trace(go.Scatter(
                            x=[p1[0], sec.origin[0], p2[0]],
                            y=[p1[1], sec.origin[1], p2[1]],
                            mode='lines+text',
                            text=["", sec.name, ""],
                            textposition="top center",
                            textfont=dict(size=9, color='red'),
                            line=dict(color='red', width=1.5),
                            showlegend=False,
                        ))

                    st.caption(f"Se generarán **{len(preview_sections)} secciones** "
                               f"cada {spacing_file:.0f}m")

                    fig_preview.update_layout(
                        xaxis_title='Este (m)', yaxis_title='Norte (m)',
                        yaxis=dict(scaleanchor='x', scaleratio=1),
                        height=500, margin=dict(l=60, r=20, t=30, b=40),
                    )
                    st.plotly_chart(fig_preview, use_container_width=True)

                    if st.button("✅ Aplicar Secciones desde Archivo", type="primary",
                                 key="apply_file"):
                        st.session_state.sections = preview_sections
                        st.session_state.step = max(st.session_state.step, 3)
                        st.success(f"✅ {len(preview_sections)} secciones aplicadas")

            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")


def _render_tab_interactive(tab):
    """Tab: Interactive section placement via click on plan view."""
    with tab:
        st.markdown("Haz clic sobre la vista de planta para colocar el origen de cada sección. "
                     "El azimut se calcula automáticamente según la pendiente local del diseño.")

        cols_cfg = st.columns(3)
        sec_length_int = cols_cfg[0].number_input(
            "Longitud de sección (m)", value=200.0, min_value=10.0, key="len_int")
        sector_int = cols_cfg[1].text_input("Sector", "Principal", key="sector_int")
        az_mode = cols_cfg[2].selectbox(
            "Azimut", ["Auto (pendiente local)", "Manual"], key="az_mode_int")
        if az_mode == "Manual":
            manual_az_int = st.number_input(
                "Azimut manual (°)", 0.0, 360.0, 0.0, key="man_az_int")

        # Build plan view
        mesh_d = st.session_state.mesh_design
        verts = mesh_d.vertices
        step_v = max(1, len(verts) // 8000)
        sub = verts[::step_v]

        fig_plan = go.Figure()
        fig_plan.add_trace(go.Scatter(
            x=sub[:, 0], y=sub[:, 1],
            mode='markers',
            marker=dict(size=3, color=sub[:, 2], colorscale='Earth',
                        showscale=True, colorbar=dict(title="Elev (m)")),
            name='Diseño',
            hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<extra></extra>',
        ))

        # Draw placed sections on map
        for sec in st.session_state.clicked_sections:
            d = _az2dir(sec.azimuth)
            p1 = sec.origin - d * sec.length / 2
            p2 = sec.origin + d * sec.length / 2
            fig_plan.add_trace(go.Scatter(
                x=[p1[0], sec.origin[0], p2[0]],
                y=[p1[1], sec.origin[1], p2[1]],
                mode='lines+markers+text',
                text=["", sec.name, ""],
                textposition="top center",
                line=dict(color='red', width=3),
                marker=dict(size=[4, 8, 4], color='red'),
                showlegend=False,
            ))

        fig_plan.update_layout(
            xaxis_title='Este (m)', yaxis_title='Norte (m)',
            yaxis=dict(scaleanchor='x', scaleratio=1),
            height=600, margin=dict(l=60, r=20, t=30, b=40),
        )

        # Interactive selection
        try:
            event = st.plotly_chart(
                fig_plan, on_select="rerun",
                selection_mode=["points"], key="plan_select")

            if event and event.selection and event.selection.points:
                for pt in event.selection.points:
                    px_val, py_val = pt['x'], pt['y']
                    already = any(
                        abs(s.origin[0] - px_val) < 1 and abs(s.origin[1] - py_val) < 1
                        for s in st.session_state.clicked_sections)
                    if not already:
                        origin = np.array([px_val, py_val])
                        if az_mode == "Auto (pendiente local)":
                            az = compute_local_azimuth(mesh_d, origin)
                        else:
                            az = manual_az_int
                        n = len(st.session_state.clicked_sections) + 1
                        st.session_state.clicked_sections.append(SectionLine(
                            name=f"S-{n:02d}", origin=origin,
                            azimuth=az, length=sec_length_int,
                            sector=sector_int))
                        st.rerun()
        except TypeError:
            st.plotly_chart(fig_plan, key="plan_fallback")
            st.info("Actualiza Streamlit a >= 1.35 para selección interactiva. "
                     "Mientras tanto usa la pestaña Manual.")

        # Table + buttons
        if st.session_state.clicked_sections:
            st.subheader(f"📍 {len(st.session_state.clicked_sections)} secciones colocadas")
            sec_data_int = []
            for s in st.session_state.clicked_sections:
                sec_data_int.append({
                    "Nombre": s.name, "Sector": s.sector,
                    "Origen X": f"{s.origin[0]:.1f}",
                    "Origen Y": f"{s.origin[1]:.1f}",
                    "Azimut (°)": f"{s.azimuth:.1f}",
                    "Longitud (m)": f"{s.length:.1f}",
                })
            st.dataframe(sec_data_int, use_container_width=True)

        cols_btn = st.columns(2)
        if cols_btn[0].button("✅ Aplicar Secciones", type="primary", key="apply_int"):
            if st.session_state.clicked_sections:
                st.session_state.sections = list(st.session_state.clicked_sections)
                st.session_state.step = max(st.session_state.step, 3)
                st.success(f"✅ {len(st.session_state.clicked_sections)} secciones aplicadas")
        if cols_btn[1].button("🗑️ Limpiar", key="clear_int"):
            st.session_state.clicked_sections = []
            st.rerun()


def _render_tab_manual(tab):
    """Tab: Manual section definition by entering coordinates."""
    with tab:
        st.markdown("Define cada sección con un punto de origen (X, Y), azimut y longitud.")

        cols_top = st.columns(2)
        n_sections = cols_top[0].number_input(
            "Número de secciones a definir", min_value=1, max_value=50, value=5)
        auto_az_manual = cols_top[1].checkbox(
            "Auto-detectar azimut desde diseño", value=False, key="auto_az_manual")

        sections_manual = []
        for i in range(n_sections):
            with st.expander(f"Sección S-{i + 1:02d}", expanded=(i == 0)):
                cols = st.columns(5)
                name = cols[0].text_input("Nombre", f"S-{i + 1:02d}", key=f"sname_{i}")
                sector = cols[1].text_input("Sector", "", key=f"ssector_{i}")

                bd = st.session_state.bounds_design
                cx, cy = bd['center'][0], bd['center'][1]

                cols2 = st.columns(4)
                ox = cols2[0].number_input("Origen X", value=float(cx), format="%.1f", key=f"sox_{i}")
                oy = cols2[1].number_input("Origen Y", value=float(cy), format="%.1f", key=f"soy_{i}")

                if auto_az_manual:
                    from core.section_cutter import compute_local_azimuth as _calc_az
                    az = _calc_az(st.session_state.mesh_design, np.array([ox, oy]))
                    cols2[2].text_input("Azimut (°)", value=f"{az:.1f}", disabled=True, key=f"saz_{i}")
                else:
                    az = cols2[2].number_input(
                        "Azimut (°)", value=0.0, min_value=0.0,
                        max_value=360.0, key=f"saz_{i}")

                length = cols2[3].number_input("Longitud (m)", value=200.0, min_value=10.0, key=f"slen_{i}")

                sections_manual.append(SectionLine(
                    name=name, origin=np.array([ox, oy]),
                    azimuth=az, length=length, sector=sector))

        if st.button("✅ Aplicar Secciones Manuales", type="primary"):
            st.session_state.sections = sections_manual
            st.session_state.step = max(st.session_state.step, 3)
            st.success(f"✅ {len(sections_manual)} secciones definidas")


def _render_tab_auto(tab):
    """Tab: Auto-generate equally-spaced sections along a line."""
    with tab:
        st.markdown("Genera secciones equiespaciadas a lo largo de una línea (ej: cresta del pit).")

        bd = st.session_state.bounds_design
        cols = st.columns(4)
        x1 = cols[0].number_input("Punto inicio X", value=float(bd['xmin']), format="%.1f")
        y1 = cols[1].number_input("Punto inicio Y", value=float(bd['center'][1]), format="%.1f")
        x2 = cols[2].number_input("Punto fin X", value=float(bd['xmax']), format="%.1f")
        y2 = cols[3].number_input("Punto fin Y", value=float(bd['center'][1]), format="%.1f")

        cols2 = st.columns(3)
        n_auto = cols2[0].number_input("N° de secciones", min_value=2, max_value=50, value=5)

        az_method = st.radio(
            "Método de Azimut",
            ["Perpendicular a la línea (Recomendado)", "Fijo", "Auto (pendiente local - Ruidoso)"],
            index=0, horizontal=True)

        fixed_az = 0.0
        if az_method == "Fijo":
            fixed_az = st.number_input("Azimut fijo (°)", value=0.0, min_value=0.0, max_value=360.0)

        len_auto = cols2[1].number_input("Longitud de sección (m)", value=200.0, min_value=10.0)
        sector_auto = cols2[2].text_input("Sector", "Sector Principal", key="sector_auto_txt")

        if st.button("🔄 Generar Secciones Automáticas", type="primary"):
            from core.section_cutter import compute_local_azimuth as _calc_az2

            gen_az = None
            if az_method == "Fijo":
                gen_az = fixed_az
            elif az_method == "Auto (pendiente local - Ruidoso)":
                gen_az = 0.0  # Placeholder

            sections_auto = generate_sections_along_crest(
                st.session_state.mesh_design,
                np.array([x1, y1]),
                np.array([x2, y2]),
                n_auto, gen_az, len_auto, sector_auto
            )

            # Post-process if Local Slope selected
            if az_method == "Auto (pendiente local - Ruidoso)":
                for sec in sections_auto:
                    sec.azimuth = _calc_az2(st.session_state.mesh_design, sec.origin)

            st.session_state.sections = sections_auto
            st.session_state.step = max(st.session_state.step, 3)
            st.success(f"✅ {len(sections_auto)} secciones generadas")
