"""
Aplicación Streamlit para Conciliación Geotécnica: Diseño vs As-Built
Carga superficies STL, genera secciones, extrae parámetros y exporta a Excel.
"""
import streamlit as st
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import tempfile
import os
import sys
import json
import io
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from core import (
    load_mesh, get_mesh_bounds, mesh_to_plotly, decimate_mesh,
    SectionLine, cut_mesh_with_section, cut_both_surfaces,
    extract_parameters, compare_design_vs_asbuilt, build_reconciled_profile,
    export_results,
)
from core.geom_utils import calculate_profile_deviation, calculate_area_between_profiles

st.set_page_config(page_title="Conciliación Geotécnica", page_icon="⛏️", layout="wide")

# =====================================================
# CSS
# =====================================================
st.markdown("""
<style>
.main-title { font-size: 2rem; font-weight: bold; color: #2F5496; text-align: center; margin-bottom: 0.5rem; }
.subtitle { font-size: 1.1rem; color: #666; text-align: center; margin-bottom: 1.5rem; }
.metric-card {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 1rem; border-radius: 10px; text-align: center; margin: 0.5rem 0;
    border-left: 4px solid #2F5496;
}
.status-ok { background-color: #C6EFCE; color: #006100; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-warn { background-color: #FFEB9C; color: #9C5700; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-nok { background-color: #FFC7CE; color: #9C0006; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">⛏️ Conciliación Geotécnica: Diseño vs As-Built</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Extracción automática de parámetros desde superficies 3D (STL)</div>', unsafe_allow_html=True)

# =====================================================
# SESSION STATE
# =====================================================
defaults = {
    'mesh_design': None, 'mesh_topo': None,
    'bounds_design': None, 'bounds_topo': None,
    'sections': [], 'profiles_design': [], 'profiles_topo': [],
    'params_design': [], 'params_topo': [],
    'comparison_results': [], 'step': 1,
    'clicked_sections': [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =====================================================
# SIDEBAR: CONFIGURACIÓN
# =====================================================
with st.sidebar:
    st.header("⚙️ Configuración")

    st.subheader("🤖 Asistente IA")
    ai_enabled = st.checkbox("Habilitar IA", value=False)
    
    api_key = ""
    model_name = "gpt-3.5-turbo"
    base_url = None

    if ai_enabled:
        ai_provider = st.selectbox("Proveedor", ["OpenAI", "Local (LM Studio/Ollama)"])
        
        if ai_provider == "OpenAI":
            api_key = st.text_input("OpenAI API Key", type="password")
            model_name = st.selectbox("Modelo", ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"])
        else:
            base_url = st.text_input("Base URL", value="http://localhost:1234/v1")
            api_key = "lm-studio" # Dummy key for local
            model_name = st.text_input("Nombre del Modelo", value="local-model")
    
    st.divider()

    st.subheader("📐 Tolerancias")
    tol_h_neg = st.number_input("Altura banco: Tol. (-) m", value=1.0, step=0.5, key="tol_h_neg")
    tol_h_pos = st.number_input("Altura banco: Tol. (+) m", value=1.5, step=0.5, key="tol_h_pos")
    tol_a_neg = st.number_input("Ángulo cara: Tol. (-) °", value=5.0, step=1.0, key="tol_a_neg")
    tol_a_pos = st.number_input("Ángulo cara: Tol. (+) °", value=5.0, step=1.0, key="tol_a_pos")
    min_berm_width = st.number_input("Berma mínima (m)", value=6.0, step=0.5, key="min_berm")
    tol_ir_neg = st.number_input("Áng. Inter-Rampa: Tol. (-) °", value=3.0, step=1.0, key="tol_ir_neg")
    tol_ir_pos = st.number_input("Áng. Inter-Rampa: Tol. (+) °", value=2.0, step=1.0, key="tol_ir_pos")

    st.subheader("🔧 Detección de Bancos")
    face_threshold = st.slider("Ángulo mínimo cara (°)", 0, 90, 40)
    berm_threshold = st.slider("Ángulo máximo berma (°)", 5, 30, 20)
    resolution = st.slider("Resolución de perfil (m)", 0.1, 2.0, 0.5)

    st.subheader("📊 Visualización")
    grid_height = st.number_input("Grilla Vertical (m)", value=15.0, min_value=1.0, step=1.0, 
                                  help="Define la separación de líneas horizontales en los perfiles")
    grid_ref = st.number_input("Cota Referencia (m)", value=0.0, step=1.0,
                               help="Altura base para alinear la grilla (ej: pata del banco)")

    st.subheader("📋 Información del Proyecto")
    project_name = st.text_input("Proyecto", "")
    operation = st.text_input("Operación", "")
    phase = st.text_input("Fase / Pit", "")
    author = st.text_input("Elaborado por", "")

tolerances = {
    'bench_height': {'neg': tol_h_neg, 'pos': tol_h_pos},
    'face_angle': {'neg': tol_a_neg, 'pos': tol_a_pos},
    'berm_width': {'min': min_berm_width},
    'inter_ramp_angle': {'neg': tol_ir_neg, 'pos': tol_ir_pos},
    'overall_angle': {'neg': 2.0, 'pos': 2.0},
}


# =====================================================
# HELPER: Generate contour data from mesh
# =====================================================
@st.cache_data(show_spinner=False)
def _mesh_to_contour_data(_mesh, grid_size=500):
    """Interpolate mesh vertices onto a regular grid for contour plotting."""
    # Note: _mesh argument name starts with underscore to prevent hashing large object if not needed,
    # but st.cache_data hashes arguments. For Trimesh objects, hashing might be slow.
    # We might want to rely on a unique ID (like filename + hash) but here we just cache.
    # To be safe and fast, we can transform mesh to vertices array before passing or just cache this.
    
    from scipy.interpolate import griddata

    if _mesh is None: return None, None, None, None, None

    verts = _mesh.vertices
    # Subsample if too many vertices to avoid slow griddata
    # Increased limit to 200k to preserve details in design meshes
    if len(verts) > 200000:
        step = len(verts) // 200000
        verts = verts[::step]

    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]

    # Create grid
    xi = np.linspace(x.min(), x.max(), grid_size)
    yi = np.linspace(y.min(), y.max(), grid_size)
    xi_grid, yi_grid = np.meshgrid(xi, yi)

    # Linear interpolation is best for triangulation (avoids cubic overshooting)
    zi_grid = griddata((x, y), z, (xi_grid, yi_grid), method='linear')
    return xi, yi, xi_grid, yi_grid, zi_grid


# =====================================================
# PASO 1: CARGA DE SUPERFICIES
# =====================================================
st.header("📁 Paso 1: Cargar Superficies STL / DXF")

col1, col2 = st.columns(2)
with col1:
    st.subheader("🔵 Superficie de Diseño")
    file_design = st.file_uploader("Cargar Diseño (STL, OBJ, PLY, DXF)", type=["stl", "obj", "ply", "dxf"], key="design_file")

with col2:
    st.subheader("🟢 Superficie Topográfica (As-Built)")
    file_topo = st.file_uploader("Cargar Topografía (STL, OBJ, PLY, DXF)", type=["stl", "obj", "ply", "dxf"], key="topo_file")

if file_design and file_topo:
    # Save to temp files preserving extension
    import pathlib
    ext_d = pathlib.Path(file_design.name).suffix
    ext_t = pathlib.Path(file_topo.name).suffix
    
    f_design = f_topo = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext_d, delete=False) as f:
            f.write(file_design.read()); f_design = f.name
        with tempfile.NamedTemporaryFile(suffix=ext_t, delete=False) as f:
            f.write(file_topo.read()); f_topo = f.name

        with st.spinner("Cargando superficies..."):
            st.session_state.mesh_design = load_mesh(f_design)
            st.session_state.mesh_topo = load_mesh(f_topo)
            st.session_state.bounds_design = get_mesh_bounds(st.session_state.mesh_design)
            st.session_state.bounds_topo = get_mesh_bounds(st.session_state.mesh_topo)

        col1, col2 = st.columns(2)
        with col1:
            bd = st.session_state.bounds_design
            st.success(f"✅ Diseño cargado: {bd['n_faces']:,} caras, {bd['n_vertices']:,} vértices")
            st.caption(f"X: [{bd['xmin']:.1f}, {bd['xmax']:.1f}] | Y: [{bd['ymin']:.1f}, {bd['ymax']:.1f}] | Z: [{bd['zmin']:.1f}, {bd['zmax']:.1f}]")
        with col2:
            bt = st.session_state.bounds_topo
            st.success(f"✅ Topografía cargada: {bt['n_faces']:,} caras, {bt['n_vertices']:,} vértices")
            st.caption(f"X: [{bt['xmin']:.1f}, {bt['xmax']:.1f}] | Y: [{bt['ymin']:.1f}, {bt['ymax']:.1f}] | Z: [{bt['zmin']:.1f}, {bt['zmax']:.1f}]")

        st.session_state.step = max(st.session_state.step, 2)
    except Exception as e:
        st.error(f"Error al cargar: {e}")
    finally:
        for tmp in (f_design, f_topo):
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

# =====================================================
# VISUALIZACIÓN 3D Y PLANTA 2D
# =====================================================
if st.session_state.mesh_design is not None and st.session_state.mesh_topo is not None:
    from core.section_cutter import azimuth_to_direction as _az2dir

    # --- Vista 3D ---
    with st.expander("🌐 Vista 3D de Superficies", expanded=False):
        with st.spinner("Generando vista 3D..."):
            fig = go.Figure()

            md = decimate_mesh(st.session_state.mesh_design, 30000)
            mt = decimate_mesh(st.session_state.mesh_topo, 30000)

            fig.add_trace(mesh_to_plotly(md, "Diseño", "royalblue", 1.0))
            fig.add_trace(mesh_to_plotly(mt, "Topografía Real", "forestgreen", 1.0))

            # Draw sections if they exist
            if st.session_state.sections:
                for sec in st.session_state.sections:
                    d = _az2dir(sec.azimuth)
                    p1 = sec.origin - d * sec.length / 2
                    p2 = sec.origin + d * sec.length / 2
                    bd = st.session_state.bounds_design
                    zmin, zmax = bd['zmin'], bd['zmax']
                    fig.add_trace(go.Scatter3d(
                        x=[p1[0], p2[0]], y=[p1[1], p2[1]], z=[(zmin+zmax)/2]*2,
                        mode='lines+text', text=[sec.name, ""],
                        line=dict(color='red', width=5),
                        name=sec.name, showlegend=False,
                    ))

            fig.update_layout(
                scene=dict(aspectmode='data',
                    xaxis_title='Este (m)', yaxis_title='Norte (m)', zaxis_title='Elevación (m)'),
                height=600, margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
            )
            st.plotly_chart(fig, use_container_width=True)

    # --- Vista en Planta con Curvas de Nivel ---
    with st.expander("🗺️ Vista en Planta — Curvas de Nivel", expanded=False):
        with st.spinner("Generando curvas de nivel..."):
            contour_cols = st.columns(3)
            contour_surface = contour_cols[0].selectbox(
                "Superficie", ["Diseño", "Topografía", "Ambas"], key="contour_surf")
            contour_interval = contour_cols[1].number_input(
                "Intervalo curvas (m)", value=15.0, min_value=1.0, step=1.0, key="contour_int")
            contour_grid = contour_cols[2].number_input(
                "Resolución grilla", value=500, min_value=100, max_value=2000, step=100, key="contour_grid")

            fig_contour = go.Figure()

            if contour_surface in ("Diseño", "Ambas"):
                xi, yi, xig, yig, zig = _mesh_to_contour_data(
                    st.session_state.mesh_design, int(contour_grid))
                fig_contour.add_trace(go.Contour(
                    x=xi, y=yi, z=zig,
                    contours=dict(
                        start=grid_ref,
                        end=float(np.nanmax(zig)) if zig is not None else 100,
                        size=contour_interval,
                        showlabels=True,
                        labelfont=dict(size=9, color='blue'),
                        coloring='lines',
                    ),
                    line=dict(color='royalblue', width=1.0),
                    showscale=False,
                    name='Diseño',
                    hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<br>Elev: %{z:.1f}m<extra>Diseño</extra>',
                ))

            if contour_surface in ("Topografía", "Ambas"):
                xi, yi, xig, yig, zig = _mesh_to_contour_data(
                    st.session_state.mesh_topo, int(contour_grid))
                fig_contour.add_trace(go.Contour(
                    x=xi, y=yi, z=zig,
                    contours=dict(
                        start=grid_ref,
                        end=float(np.nanmax(zig)) if zig is not None else 100,
                        size=contour_interval,
                        showlabels=True,
                        labelfont=dict(size=9, color='green'),
                        coloring='lines',
                    ),
                    line=dict(color='forestgreen', width=1.0),
                    showscale=False,
                    name='Topografía',
                    hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<br>Elev: %{z:.1f}m<extra>Topo</extra>',
                ))

            # Draw sections on plan view
            if st.session_state.sections:
                for sec in st.session_state.sections:
                    d = _az2dir(sec.azimuth)
                    p1 = sec.origin - d * sec.length / 2
                    p2 = sec.origin + d * sec.length / 2
                    fig_contour.add_trace(go.Scatter(
                        x=[p1[0], sec.origin[0], p2[0]],
                        y=[p1[1], sec.origin[1], p2[1]],
                        mode='lines+markers+text',
                        text=["", sec.name, ""],
                        textposition="top center",
                        textfont=dict(size=10, color='red'),
                        line=dict(color='red', width=2),
                        marker=dict(size=[4, 7, 4], color='red'),
                        showlegend=False,
                        hovertemplate=f'{sec.name}<br>Az: {sec.azimuth:.1f}°<extra></extra>',
                    ))

            fig_contour.update_layout(
                xaxis_title='Este (m)', yaxis_title='Norte (m)',
                yaxis=dict(scaleanchor='x', scaleratio=1),
                height=650, margin=dict(l=60, r=20, t=30, b=40),
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
            )
            st.plotly_chart(fig_contour, use_container_width=True)


# =====================================================
# PASO 2: DEFINIR SECCIONES
# =====================================================
if st.session_state.step >= 2:
    st.header("✂️ Paso 2: Definir Secciones de Corte")

    tab_file, tab_interactive, tab_manual, tab_auto = st.tabs([
        "📂 Archivo de Coordenadas", "🗺️ Interactivo (Clic)",
        "📌 Manual", "🔄 Automático"])

    # --- TAB ARCHIVO ---
    with tab_file:
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
                    # Handle DXF
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
                else:
                    # Handle CSV
                    content = coord_file.read().decode('utf-8')
                    # Try to parse CSV
                    df_coords = pd.read_csv(io.StringIO(content), nrows=10000)
                    # Accept various column name formats
                    x_col = next((c for c in df_coords.columns
                                  if c.strip().upper() in ('X', 'ESTE', 'EAST', 'E')), None)
                    y_col = next((c for c in df_coords.columns
                                  if c.strip().upper() in ('Y', 'NORTE', 'NORTH', 'N')), None)

                    if x_col is None or y_col is None:
                        # Try first two numeric columns
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
                    st.caption(f"X: [{polyline[:,0].min():.1f}, {polyline[:,0].max():.1f}] | "
                               f"Y: [{polyline[:,1].min():.1f}, {polyline[:,1].max():.1f}]")

                    # Preview polyline on a small plan view
                    fig_preview = go.Figure()
                    # Background: mesh vertices
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
                    # Polyline
                    fig_preview.add_trace(go.Scatter(
                        x=polyline[:, 0], y=polyline[:, 1],
                        mode='lines+markers',
                        line=dict(color='orange', width=3),
                        marker=dict(size=6, color='orange'),
                        name='Línea de evaluación',
                    ))

                    # Generate preview sections
                    from core.section_cutter import generate_perpendicular_sections
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
                        st.success(
                            f"✅ {len(preview_sections)} secciones aplicadas")

            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    # --- TAB INTERACTIVO ---
    with tab_interactive:
        st.markdown("Haz clic sobre la vista de planta para colocar el origen de cada sección. "
                    "El azimut se calcula automáticamente según la pendiente local del diseño.")

        from core.section_cutter import compute_local_azimuth

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

    # --- TAB MANUAL ---
    with tab_manual:
        st.markdown("Define cada sección con un punto de origen (X, Y), azimut y longitud.")

        cols_top = st.columns(2)
        n_sections = cols_top[0].number_input(
            "Número de secciones a definir", min_value=1, max_value=50, value=5)
        auto_az_manual = cols_top[1].checkbox(
            "Auto-detectar azimut desde diseño", value=False, key="auto_az_manual")

        sections_manual = []
        for i in range(n_sections):
            with st.expander(f"Sección S-{i+1:02d}", expanded=(i==0)):
                cols = st.columns(5)
                name = cols[0].text_input("Nombre", f"S-{i+1:02d}", key=f"sname_{i}")
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
                    az = cols2[2].number_input("Azimut (°)", value=0.0, min_value=0.0,
                                              max_value=360.0, key=f"saz_{i}")

                length = cols2[3].number_input("Longitud (m)", value=200.0, min_value=10.0, key=f"slen_{i}")

                sections_manual.append(SectionLine(name=name, origin=np.array([ox, oy]),
                    azimuth=az, length=length, sector=sector))

        if st.button("✅ Aplicar Secciones Manuales", type="primary"):
            st.session_state.sections = sections_manual
            st.session_state.step = max(st.session_state.step, 3)
            st.success(f"✅ {len(sections_manual)} secciones definidas")

    with tab_auto:
        st.markdown("Genera secciones equiespaciadas a lo largo de una línea (ej: cresta del pit).")

        bd = st.session_state.bounds_design
        cols = st.columns(4)
        x1 = cols[0].number_input("Punto inicio X", value=float(bd['xmin']), format="%.1f")
        y1 = cols[1].number_input("Punto inicio Y", value=float(bd['center'][1]), format="%.1f")
        x2 = cols[2].number_input("Punto fin X", value=float(bd['xmax']), format="%.1f")
        y2 = cols[3].number_input("Punto fin Y", value=float(bd['center'][1]), format="%.1f")

        cols2 = st.columns(3)
        n_auto = cols2[0].number_input("N° de secciones", min_value=2, max_value=50, value=5)
        
        # New selection logic
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
            from core.section_cutter import generate_sections_along_crest, compute_local_azimuth as _calc_az2
            
            # Determine azimuth argument for generator
            # If "Perpendicular", we pass None to let generator handle it
            # If "Fixed", we pass the fixed value
            # If "Auto (local)", we pass 0.0 initially and then overwrite
            
            gen_az = None
            if az_method == "Fijo":
                gen_az = fixed_az
            elif az_method == "Auto (pendiente local - Ruidoso)":
                gen_az = 0.0 # Placeholder
                
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

# =====================================================
# PASO 3: CORTAR Y EXTRAER
# =====================================================
if st.session_state.step >= 3 and st.session_state.sections:
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
        else:
            # Filter sections
            sections_to_process = [s for s in st.session_state.sections if s.name in selected_names]
            
            progress = st.progress(0)
            status = st.empty()
    
            profiles_d = []
            profiles_t = []
            params_d = []
            params_t = []
            comparisons = []
    
            total = len(sections_to_process)
    
            for i, section in enumerate(sections_to_process):
                status.text(f"Procesando sección {section.name} ({i+1}/{total})...")
                progress.progress((i + 1) / total)

                pd_prof = cut_mesh_with_section(st.session_state.mesh_design, section)
                pt_prof = cut_mesh_with_section(st.session_state.mesh_topo, section)

                profiles_d.append(pd_prof)
                profiles_t.append(pt_prof)

                if pd_prof is not None and pt_prof is not None:
                    ep_d = extract_parameters(pd_prof.distances, pd_prof.elevations,
                        section.name, section.sector, resolution, face_threshold, berm_threshold)
                    ep_t = extract_parameters(pt_prof.distances, pt_prof.elevations,
                        section.name, section.sector, resolution, face_threshold, berm_threshold)

                    params_d.append(ep_d)
                    params_t.append(ep_t)

                    if ep_d.benches and ep_t.benches:
                        comp = compare_design_vs_asbuilt(ep_d, ep_t, tolerances)
                        comparisons.extend(comp)

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
            for k in ['height_status','angle_status','berm_status']:
                status = c.get(k)
                if status and status != "-":
                    n_total_valid += 1
                    if status == "CUMPLE" or status == "RAMPA OK":
                        n_ok += 1
        
        pct = n_ok / n_total_valid * 100 if n_total_valid > 0 else 0

        cols = st.columns(4)
        cols[0].metric("Secciones procesadas", f"{sum(1 for p in profiles_d if p is not None)}/{total}")
        cols[1].metric("Bancos detectados", len(comparisons))
        cols[2].metric("Total evaluaciones", n_total_valid)
        cols[3].metric("Cumplimiento global", f"{pct:.1f}%")

# =====================================================
# PASO 4: RESULTADOS
# =====================================================
if st.session_state.step >= 4 and st.session_state.comparison_results:
    st.header("📊 Paso 4: Resultados")

    tab_profiles, tab_table, tab_dash, tab_ai, tab_export = st.tabs([
        "📈 Perfiles", "📋 Tabla Detallada", "📊 Dashboard", "🤖 Analista IA", "💾 Exportar"
    ])

    # --- PERFILES ---
    with tab_profiles:
        show_reconciled = st.checkbox(
            "Mostrar perfil conciliado (geometría idealizada detectada)",
            value=True, key="show_reconciled")
        
        show_areas = st.checkbox(
             "Mostrar Áreas (Sobre-excavación / Deuda)",
             value=False, key="show_areas")


        show_semaphore = st.checkbox(
             "Visualización Semáforo (Verde=Cumple, Amarillo=Alerta, Rojo=No Cumple)",
             value=False, key="show_semaphore")

        # Use processed sections for iteration to maintain index alignment
        display_sections = st.session_state.get('processed_sections', st.session_state.sections)

        for i, section in enumerate(display_sections):
            pd_prof = st.session_state.profiles_design[i]
            pt_prof = st.session_state.profiles_topo[i]

            if pd_prof is None or pt_prof is None:
                st.warning(f"⚠️ Sección {section.name}: sin intersección con una o ambas superficies")
                continue

            fig = go.Figure()

            # Design profile
            fig.add_trace(go.Scatter(
                x=pd_prof.distances, y=pd_prof.elevations,
                mode='lines', name='Diseño',
                line=dict(color='royalblue', width=2)))

            # Area Visualization
            area_over, area_under = 0.0, 0.0
            if show_areas and pd_prof is not None and pt_prof is not None:
                a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)
                area_over, area_under = a_over, a_under
                
                # Plot filled areas
                # We need to construct polygons or use fill parameters
                # Plotly fill is 'tozeroy' or 'tonexty'.
                # Easiest way: Plot one line, then plot the other with fill 'tonexty' only where condition meets?
                # Actually, standard scatter with fill might be tricky for partial fills.
                # Improved approach: Create specific traces for Over and Under.
                
                # Trace for Under (Deuda) - Topo > Design
                # We plot Design as base, then Topo where Topo > Design
                # Use 'fill=tonexty' requires ordering. 
                # Simpler: Plot Design (Invisible), then plot Topo-masked-Design (Invisible), fill=tonexty? No.
                
                # Let's use the interpolated arrays.
                # Mask for Under
                mask_u = z_eval_i >= z_ref_i
                if np.any(mask_u):
                    fig.add_trace(go.Scatter(
                        x=np.concatenate([d_i[mask_u], d_i[mask_u][::-1]]),
                        y=np.concatenate([z_eval_i[mask_u], z_ref_i[mask_u][::-1]]),
                        fill='toself',
                        fillcolor='rgba(0,0,255,0.3)', # Blue for Deuda
                        line=dict(width=0),
                        name=f'Deuda ({a_under:.1f} m²)',
                        hoverinfo='skip'
                    ))
                
                # Mask for Over
                mask_o = z_eval_i < z_ref_i
                if np.any(mask_o):
                     fig.add_trace(go.Scatter(
                        x=np.concatenate([d_i[mask_o], d_i[mask_o][::-1]]),
                        y=np.concatenate([z_eval_i[mask_o], z_ref_i[mask_o][::-1]]),
                        fill='toself',
                        fillcolor='rgba(255,0,0,0.3)', # Red for Over
                        line=dict(width=0),
                        name=f'Sobre-exc. ({a_over:.1f} m²)',
                        hoverinfo='skip'
                    ))

            # Add Metrics Annotation - REMOVED per user request (confusing average)
            # But we still need sec_comps and sec_name for the next block
            sec_name = section.name
            sec_comps = [c for c in st.session_state.comparison_results if c['section'] == sec_name]
            
            
            # --- Per-Bench Metrics Annotation ---
            # If we have comparisons, iterate and annotate
            if sec_comps and 'd_i' in locals() and pd_prof is not None:
                # We need the full interpolated data if not already computed
                if not (show_areas and pd_prof is not None and pt_prof is not None):
                     # Recalculate if it wasn't done above (though we did a partial calc above, 
                     # we need d_i, z_ref_i, z_eval_i which are returned by calculate_area_between_profiles)
                     # Actually, the variable scope from previous block might not be available if show_areas was False
                     # Let's ensure we have the data
                     a_over_full, a_under_full, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)

                dx = 0.1 # Integration step from geom_utils

                # Prepare data for hover tooltips
                hover_x = []
                hover_y = []
                hover_text = []
                hover_colors = []
                hover_symbols = []

                for comp in sec_comps:
                    c_type = comp.get('type', 'MATCH')
                    
                    if c_type == 'MISSING':
                        bd = comp.get('bench_design')
                        if bd:
                            hover_x.append(bd.crest_distance)
                            hover_y.append(bd.crest_elevation)
                            hover_text.append(f"<b>Cota {bd.toe_elevation:.0f}</b><br>❌ NO CONSTRUIDO")
                            hover_colors.append("red")
                            hover_symbols.append("x")
                        continue

                    if c_type == 'EXTRA':
                        bt = comp.get('bench_real')
                        if bt:
                            hover_x.append(bt.crest_distance)
                            hover_y.append(bt.crest_elevation)
                            hover_text.append(f"<b>Cota {bt.toe_elevation:.0f}</b><br>⚠️ BANCO ADICIONAL")
                            hover_colors.append("orange")
                            hover_symbols.append("triangle-up")
                        continue

                    # valid match
                    bd = comp.get('bench_design')
                    if not bd: continue
                    
                    # Define range for this bench
                    # From Toe to Crest (Face) is the critical part for compliance
                    # But for "Over/Under" of the bench, we might want the whole step (Toe to next Toe)
                    # Let's use Toe to Crest + Berm Width
                    
                    start_dist = bd.toe_distance
                    # End distance: difficult to know next toe without looking ahead. 
                    # Approximate as Crest + Berm
                    end_dist = bd.crest_distance + bd.berm_width
                    
                    # Find indices in common grid
                    # d_i is sorted
                    idx_start = np.searchsorted(d_i, start_dist)
                    idx_end = np.searchsorted(d_i, end_dist)
                    
                    if idx_end > idx_start:
                        # Slice arrays
                        z_ref_slice = z_ref_i[idx_start:idx_end]
                        z_eval_slice = z_eval_i[idx_start:idx_end]
                        
                        # Calculate diff
                        diff_slice = z_eval_slice - z_ref_slice
                        
                        # Areas
                        a_u_b = np.sum(diff_slice[diff_slice > 0]) * dx
                        a_o_b = np.sum(np.abs(diff_slice[diff_slice < 0])) * dx
                        
                        # Compliance status for this bench (aggregate)
                        # Consolidate status: if any parameter fails, bench fails
                        statuses = [comp.get('height_status'), comp.get('angle_status'), comp.get('berm_status')]
                        if "NO CUMPLE" in statuses or "FALTA RAMPA" in statuses:
                            b_status = "❌"
                            color_s = "red"
                        elif "FUERA DE TOLERANCIA" in statuses or "RAMPA (Desv. Ancho)" in statuses:
                            b_status = "⚠️"
                            color_s = "orange"
                        else:
                            b_status = "✅"
                            color_s = "green"

                        # Distance Calculations (Pre-calculated in param_extractor)
                        d_crest = comp.get('delta_crest')
                        d_toe = comp.get('delta_toe')
                        
                        # Formatting with sign
                        txt_crest = f"{d_crest:+.2f}m" if d_crest is not None else "N/A"
                        txt_toe = f"{d_toe:+.2f}m" if d_toe is not None else "N/A"
                        
                        # Color coding for deltas
                        # Use Red if < -0.5 (Overbreak typically), Blue if > 0.5 (Underbreak)
                        c_crest = "red" if d_crest and d_crest < -0.5 else "blue" if d_crest and d_crest > 0.5 else "black"
                        c_toe = "red" if d_toe and d_toe < -0.5 else "blue" if d_toe and d_toe > 0.5 else "black"

                        # Add point data
                        hover_x.append(bd.crest_distance)
                        hover_y.append(bd.crest_elevation)
                        hover_text.append(
                            f"<b>Cota {bd.toe_elevation:.0f}</b> {b_status}<br>"
                            f"ΔCr: <span style='color:{c_crest}'>{txt_crest}</span><br>"
                            f"ΔPa: <span style='color:{c_toe}'>{txt_toe}</span>"
                        )
                        hover_colors.append(color_s)
                        hover_symbols.append("circle")

                # Add the trace with hover info
                if hover_x:
                    fig.add_trace(go.Scatter(
                        x=hover_x, y=hover_y,
                        mode='markers',
                        name='Info Bancos',
                        marker=dict(
                            color=hover_colors,
                            symbol=hover_symbols,
                            size=10,
                            line=dict(color='black', width=1)
                        ),
                        text=hover_text,
                        hoverinfo='text',
                        hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.2)", font_size=15)
                    ))

            # Topo profile
            if show_semaphore and pd_prof is not None:
                # Calculate deviations
                devs = calculate_profile_deviation(pd_prof, pt_prof)
                
                # Base Tolerance (using Height Pos Tolerance as general reference)
                T = tolerances['bench_height']['pos'] 
                
                mask_ok = devs <= T
                mask_warn = (devs > T) & (devs <= 1.5 * T)
                mask_nok = devs > 1.5 * T
                
                # Connectivity line (faint)
                fig.add_trace(go.Scatter(
                     x=pt_prof.distances, y=pt_prof.elevations,
                     mode='lines', name='Topo (Traza)',
                     line=dict(color='gray', width=0.5), showlegend=False))

                # Semaphore traces
                if np.any(mask_ok):
                    fig.add_trace(go.Scatter(
                        x=pt_prof.distances[mask_ok], y=pt_prof.elevations[mask_ok],
                        mode='markers', name=f'Cumple (<{T}m)',
                        marker=dict(color='#006100', size=3)))
                if np.any(mask_warn):
                     fig.add_trace(go.Scatter(
                        x=pt_prof.distances[mask_warn], y=pt_prof.elevations[mask_warn],
                        mode='markers', name='Alerta',
                        marker=dict(color='#FFD700', size=4))) # Gold
                if np.any(mask_nok):
                     fig.add_trace(go.Scatter(
                        x=pt_prof.distances[mask_nok], y=pt_prof.elevations[mask_nok],
                        mode='markers', name='No Cumple',
                        marker=dict(color='#FF0000', size=4))) # Red

            else:
                fig.add_trace(go.Scatter(
                    x=pt_prof.distances, y=pt_prof.elevations,
                    mode='lines', name='Topografía Real',
                    line=dict(color='forestgreen', width=2)))

            # Reconciled profiles
            if show_reconciled and i < len(st.session_state.params_design):
                # Design reconciled
                rd, re = build_reconciled_profile(
                    st.session_state.params_design[i].benches)
                if len(rd) > 0:
                    fig.add_trace(go.Scatter(
                        x=rd, y=re, mode='lines+markers',
                        name='Conciliado Diseño',
                        line=dict(color='royalblue', width=1.5, dash='dash'),
                        marker=dict(size=5, symbol='diamond', color='royalblue'),
                    ))

            if show_reconciled and i < len(st.session_state.params_topo):
                # Topo reconciled
                rd, re = build_reconciled_profile(
                    st.session_state.params_topo[i].benches)
                if len(rd) > 0:
                    fig.add_trace(go.Scatter(
                        x=rd, y=re, mode='lines+markers',
                        name='Conciliado As-Built',
                        line=dict(color='#FF7F0E', width=2.5, dash='solid'),
                        marker=dict(size=6, symbol='diamond', color='#FF7F0E'),
                    ))

            # Mark detected benches on topo
            if i < len(st.session_state.params_topo):
                for bench in st.session_state.params_topo[i].benches:
                    fig.add_annotation(
                        x=bench.crest_distance, y=bench.crest_elevation,
                        text=f"B{bench.bench_number}",
                        showarrow=True, arrowhead=2,
                        font=dict(size=10, color="red"))

            fig.update_layout(
                title=f"Sección {section.name} — {section.sector}",
                xaxis_title="Distancia (m)", yaxis_title="Elevación (m)",
                height=400, 
                yaxis=dict(scaleanchor="x", scaleratio=1, 
                           dtick=grid_height, tick0=grid_ref, gridcolor='lightgray'),
                xaxis=dict(gridcolor='lightgray'),
                legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
                margin=dict(l=60, r=20, t=40, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)

    # --- TABLA ---
    with tab_table:
        import pandas as pd

        if st.session_state.comparison_results:
            
            # Sorting Options
            sort_option = st.radio(
                "Orden de la tabla:", 
                ["Por Sección (Vertical)", "Por Nivel (Horizontal)"], 
                horizontal=True,
                key="table_sort"
            )
            
            df = pd.DataFrame(st.session_state.comparison_results)

            # --- Filtering ---
            with st.expander("🔎 Filtros (Excel-style)", expanded=False):
                cols_filter = st.columns(3)
                
                # Filter by Sector
                all_sectors = sorted(list(df['sector'].unique()))
                sel_sectors = cols_filter[0].multiselect("Filtrar por Sector:", all_sectors, default=[], key="filter_sector")
                
                # Filter by Level
                # Convert levels to numeric for sorting just for the list, but use original string for filtering
                unique_levels = df['level'].unique()
                # Sort levels numerically descending
                sorted_levels = sorted(unique_levels, key=lambda x: float(x) if x.replace('.','',1).isdigit() else -9999, reverse=True)
                sel_levels = cols_filter[1].multiselect("Filtrar por Nivel (Cota):", sorted_levels, default=[], key="filter_level")

                # Filter by Section
                all_sections = sorted(list(df['section'].unique()))
                sel_sections = cols_filter[2].multiselect("Filtrar por Sección:", all_sections, default=[], key="filter_section")
            
            # Apply Filters
            if sel_sectors:
                df = df[df['sector'].isin(sel_sectors)]
            if sel_levels:
                df = df[df['level'].isin(sel_levels)]
            if sel_sections:
                df = df[df['section'].isin(sel_sections)]

            
            # Apply sorting
            if "Por Nivel" in sort_option:
                # Create a numeric column for sorting levels correctly
                # 'level' is string "3005", "3005.5", etc.
                df['sort_level'] = pd.to_numeric(df['level'], errors='coerce').fillna(-9999)
                # Sort descending (top-down) for mining usually, but ascending might be better for list?
                # Let's do descending elevation (highest first) -> mimics pit map
                df = df.sort_values(by=['sort_level', 'section'], ascending=[False, True])
                
                # Reorder columns to put Level first
                cols = ['sector', 'level', 'section', 'bench_num'] + [c for c in df.columns if c not in ['sector', 'level', 'section', 'bench_num', 'sort_level', 'sort_bench']]
                df = df[cols]
                
            else:
                # Default: Section then Level 
                # Sort by section name then descending level (top-down within section)
                df['sort_level'] = pd.to_numeric(df['level'], errors='coerce').fillna(-9999)
                df = df.sort_values(by=['section', 'sort_level'], ascending=[True, False])
                
                # Standard column order
                cols = ['sector', 'section', 'bench_num', 'level'] + [c for c in df.columns if c not in ['sector', 'section', 'bench_num', 'level', 'sort_level', 'sort_bench']]
                df = df[cols]

            display_cols = {
                'sector': 'Sector', 'section': 'Sección', 'bench_num': 'Banco',
                'level': 'Nivel', 'height_design': 'H. Diseño', 'height_real': 'H. Real',
                'height_dev': 'Desv. H', 'height_status': 'Cumpl. H',
                'angle_design': 'Á. Diseño', 'angle_real': 'Á. Real',
                'angle_dev': 'Desv. Á', 'angle_status': 'Cumpl. Á',
                'berm_design': 'B. Diseño', 'berm_real': 'B. Real',
                'berm_min': 'B. Mínima', 'berm_status': 'Cumpl. B',
                'delta_crest': 'Δ Cresta', 'delta_toe': 'Δ Pata'
            }
            df_display = df.rename(columns=display_cols)

            def highlight_status(val):
                val = str(val)
                if val == "CUMPLE" or "RAMPA OK" in val: return 'background-color: #C6EFCE; color: #006100'
                elif val == "FUERA DE TOLERANCIA": return 'background-color: #FFEB9C; color: #9C5700'
                elif val == "NO CUMPLE" or "FALTA" in val: return 'background-color: #FFC7CE; color: #9C0006'
                elif val == "NO CONSTRUIDO": return 'background-color: #E0E0E0; color: #555555' # Grey
                elif val == "EXTRA" or "ADICIONAL" in val: return 'background-color: #E6E6FA; color: #4B0082' # Purple
                elif "RAMPA" in val: return 'background-color: #E6E6FA; color: #4B0082'
                return ''

            styled = df_display.style.map(highlight_status,
                subset=['Cumpl. H', 'Cumpl. Á', 'Cumpl. B'])
            st.dataframe(styled, use_container_width=True, height=400)

    # --- DASHBOARD ---
    with tab_dash:
        results = st.session_state.comparison_results

        cols = st.columns(3)
        for col, (param, key, label) in zip(cols, [
            ('height', 'height_status', 'Altura de Banco'),
            ('angle', 'angle_status', 'Ángulo de Cara'),
            ('berm', 'berm_status', 'Ancho de Berma'),
        ]):
            total = len(results)
            cumple = sum(1 for r in results if r[key] == "CUMPLE")
            pct = cumple / total * 100 if total > 0 else 0
            col.metric(label, f"{pct:.0f}%", f"{cumple}/{total} cumplen")

        status_counts = {'Parámetro': [], 'CUMPLE': [], 'FUERA DE TOLERANCIA': [], 'NO CUMPLE': []}
        for key, label in [('height_status','Altura'), ('angle_status','Ángulo Cara'), ('berm_status','Berma')]:
            status_counts['Parámetro'].append(label)
            status_counts['CUMPLE'].append(sum(1 for r in results if r[key] == "CUMPLE"))
            status_counts['FUERA DE TOLERANCIA'].append(sum(1 for r in results if r[key] == "FUERA DE TOLERANCIA"))
            status_counts['NO CUMPLE'].append(sum(1 for r in results if r[key] == "NO CUMPLE"))

        import pandas as pd
        df_status = pd.DataFrame(status_counts)
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(name='CUMPLE', x=df_status['Parámetro'], y=df_status['CUMPLE'],
            marker_color='#006100'))
        fig_bar.add_trace(go.Bar(name='FUERA TOL.', x=df_status['Parámetro'], y=df_status['FUERA DE TOLERANCIA'],
            marker_color='#9C5700'))
        fig_bar.add_trace(go.Bar(name='NO CUMPLE', x=df_status['Parámetro'], y=df_status['NO CUMPLE'],
            marker_color='#9C0006'))
        fig_bar.update_layout(barmode='stack', title="Cumplimiento por Parámetro",
            height=350, margin=dict(l=40, r=20, t=40, b=40))
        st.plotly_chart(fig_bar, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            devs_h = [r['height_dev'] for r in results if r['height_dev'] is not None]
            fig_h = go.Figure(go.Histogram(x=devs_h, nbinsx=15, marker_color='royalblue'))
            fig_h.update_layout(title="Distribución Desv. Altura (m)", height=300,
                xaxis_title="Desviación (m)", yaxis_title="Frecuencia")
            fig_h.add_vline(x=-tol_h_neg, line_dash="dash", line_color="orange")
            fig_h.add_vline(x=tol_h_pos, line_dash="dash", line_color="orange")
            st.plotly_chart(fig_h, use_container_width=True)
        with col2:
            devs_a = [r['angle_dev'] for r in results if r['angle_dev'] is not None]
            fig_a = go.Figure(go.Histogram(x=devs_a, nbinsx=15, marker_color='forestgreen'))
            fig_a.update_layout(title="Distribución Desv. Ángulo Cara (°)", height=300,
                xaxis_title="Desviación (°)", yaxis_title="Frecuencia")
            fig_a.add_vline(x=-tol_a_neg, line_dash="dash", line_color="orange")
            fig_a.add_vline(x=tol_a_pos, line_dash="dash", line_color="orange")
            st.plotly_chart(fig_a, use_container_width=True)
        with col3:
            berm_vals = [r['berm_real'] for r in results if r['berm_real'] is not None and r['berm_real'] > 0]
            if berm_vals:
                fig_b = go.Figure(go.Histogram(x=berm_vals, nbinsx=15, marker_color='#FF7F0E'))
                fig_b.update_layout(title="Distribución Ancho Berma (m)", height=300,
                    xaxis_title="Ancho (m)", yaxis_title="Frecuencia")
                fig_b.add_vline(x=min_berm_width, line_dash="dash", line_color="red",
                    annotation_text="Mínimo", annotation_position="top right")
                st.plotly_chart(fig_b, use_container_width=True)

    # --- INFORME IA ---
    with tab_ai:
        st.subheader("🤖 Informe Ejecutivo (IA)")
        
        if not ai_enabled:
            st.info("Habilita el Asistente IA en la configuración (barra lateral) para generar informes automáticos.")
        else:
            if st.button("📝 Generar Informe Ejecutivo", type="primary"):
                from core.ai_reporter import generate_geotech_report
                
                # Prepare stats
                df_final = pd.DataFrame(st.session_state.comparison_results)
                
                if df_final.empty:
                    st.warning("No hay resultados para analizar.")
                else:
                    n_total = len(df_final)
                    n_compliant_h = len(df_final[df_final['height_status'] == "CUMPLE"])
                    n_compliant_a = len(df_final[df_final['angle_status'] == "CUMPLE"])
                    n_compliant_b = len(df_final[df_final['berm_status'] == "CUMPLE"])
                    
                    # Convert to simple int/float types for JSON serialization safeness
                    ai_stats = {
                        'n_total': int(n_total),
                        'n_valid': int(len(df_final[df_final['type'] == 'MATCH'])),
                        'global_stats': {
                            'Cumplimiento Altura': f"{n_compliant_h}/{n_total} ({n_compliant_h/n_total:.1%})",
                            'Cumplimiento Ángulo': f"{n_compliant_a}/{n_total} ({n_compliant_a/n_total:.1%})",
                            'Cumplimiento Berma': f"{n_compliant_b}/{n_total} ({n_compliant_b/n_total:.1%})"
                        }
                    }
                    
                    st.markdown("### ⏳ Analizando datos y redactando informe...")
                    report_container = st.empty()
                    full_report = ""
                    
                    # Stream the response
                    for chunk in generate_geotech_report(ai_stats, api_key, model_name, base_url):
                        full_report += (chunk or "")
                        report_container.markdown(full_report + "▌")
                        
                    report_container.markdown(full_report)

    # --- EXPORTAR ---
    with tab_export:
        st.subheader("💾 Exportar Resultados a Excel")

        if st.button("📥 Generar Excel de Conciliación", type="primary"):
            with st.spinner("Generando Excel..."):
                output_path = os.path.join(tempfile.gettempdir(), "Conciliacion_Resultados.xlsx")
                project_info = {
                    'project': project_name, 'operation': operation,
                    'phase': phase, 'author': author,
                    'date': datetime.now().strftime("%d/%m/%Y"),
                }
                export_results(
                    st.session_state.comparison_results,
                    st.session_state.params_design,
                    st.session_state.params_topo,
                    tolerances, output_path, project_info
                )

                with open(output_path, "rb") as f:
                    st.download_button(
                        "⬇️ Descargar Excel",
                        f.read(),
                        file_name="Conciliacion_Diseno_vs_AsBuilt.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                    )
            st.success("✅ Excel generado exitosamente")

        st.divider()

        st.subheader("🖼️ Exportar Imágenes de Sección")
        st.write("Genera un archivo ZIP con todos los gráficos de perfil en formato PNG.")
        
        if st.button("📦 Generar Imágenes (ZIP)", type="primary"):
            with st.spinner("Generando gráficos e imágenes..."):
                from core import generate_section_images_zip, cut_both_surfaces
                
                # Reconstruct full profile data for plotting
                all_data_for_images = []
                progress_bar = st.progress(0)
                
                for i, sec in enumerate(st.session_state.sections):
                     pd_prof, pt_prof = cut_both_surfaces(
                        st.session_state.mesh_design, 
                        st.session_state.mesh_topo, 
                        sec
                     )
                     
                     if pd_prof and pt_prof and i < len(st.session_state.params_design) and i < len(st.session_state.params_topo):
                         all_data_for_images.append({
                             'section_name': sec.name,
                             'params_design': st.session_state.params_design[i],
                             'params_topo': st.session_state.params_topo[i],
                             'profile_d': (pd_prof.distances, pd_prof.elevations),
                             'profile_t': (pt_prof.distances, pt_prof.elevations),
                         })
                     progress_bar.progress((i + 1) / len(st.session_state.sections))

                zip_bytes = generate_section_images_zip(all_data_for_images)
                
                st.download_button(
                    label="⬇️ Descargar Imágenes ZIP",
                    data=zip_bytes,
                    file_name="Perfiles_Secciones.zip",
                    mime="application/zip",
                )
            st.success("✅ Imágenes generadas exitosamente")

        st.divider()

        st.subheader("📐 Exportar Perfiles a DXF (3D)")
        st.write("Genera un archivo DXF con polilíneas 3D separadas por cumplimiento, incluyendo perfiles conciliados.")
        
        if st.button("📊 Generar DXF de Perfiles", type="primary"):
            with st.spinner("Generando DXF 3D de perfiles..."):
                import ezdxf
                from core import cut_both_surfaces
                from core.section_cutter import azimuth_to_direction
                from core.param_extractor import build_reconciled_profile
                
                doc = ezdxf.new('R2010')
                msp = doc.modelspace()
                
                # Create layers by compliance status
                doc.layers.add("DISEÑO_CUMPLE", color=3)          # Green
                doc.layers.add("DISEÑO_NO_CUMPLE", color=1)       # Red
                doc.layers.add("DISEÑO_FUERA_TOL", color=2)       # Yellow
                doc.layers.add("TOPO_CUMPLE", color=3)            # Green
                doc.layers.add("TOPO_NO_CUMPLE", color=1)         # Red
                doc.layers.add("TOPO_FUERA_TOL", color=2)         # Yellow
                doc.layers.add("CONCILIADO_DISEÑO", color=5)      # Blue
                doc.layers.add("CONCILIADO_TOPO", color=6)        # Magenta
                doc.layers.add("ETIQUETAS", color=7)              # White
                
                # Build per-section compliance map
                comp_results = st.session_state.comparison_results
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
                
                progress_bar = st.progress(0)
                n_exported = 0
                
                for i, sec in enumerate(st.session_state.sections):
                    pd_prof, pt_prof = cut_both_surfaces(
                        st.session_state.mesh_design,
                        st.session_state.mesh_topo,
                        sec
                    )
                    
                    if pd_prof and pt_prof:
                        safe_name = sec.name.replace("/", "_").replace("\\", "_")
                        
                        # Determine compliance layer suffix
                        status = section_status.get(sec.name, 'CUMPLE')
                        if status == 'NO CUMPLE':
                            layer_suffix = 'NO_CUMPLE'
                        elif status == 'FUERA DE TOLERANCIA':
                            layer_suffix = 'FUERA_TOL'
                        else:
                            layer_suffix = 'CUMPLE'
                        
                        # Reconstruct 3D coordinates
                        direction = azimuth_to_direction(sec.azimuth)
                        ox, oy = sec.origin[0], sec.origin[1]
                        
                        def to_3d(distances, elevations):
                            return [
                                (ox + d * direction[0], oy + d * direction[1], float(e))
                                for d, e in zip(distances, elevations)
                            ]
                        
                        def draw_3d_polyline(pts, layer):
                            """Draw a 3D polyline as consecutive LINE entities."""
                            for j in range(len(pts) - 1):
                                msp.add_line(pts[j], pts[j+1], dxfattribs={'layer': layer})
                        
                        # Design profile
                        design_3d = to_3d(pd_prof.distances, pd_prof.elevations)
                        if len(design_3d) > 1:
                            draw_3d_polyline(design_3d, f'DISEÑO_{layer_suffix}')
                        
                        # Topo profile
                        topo_3d = to_3d(pt_prof.distances, pt_prof.elevations)
                        if len(topo_3d) > 1:
                            draw_3d_polyline(topo_3d, f'TOPO_{layer_suffix}')
                        
                        # Reconciled Design profile
                        if i < len(st.session_state.params_design) and st.session_state.params_design[i].benches:
                            rd, re = build_reconciled_profile(st.session_state.params_design[i].benches)
                            if len(rd) > 0:
                                conc_d_3d = to_3d(rd, re)
                                if len(conc_d_3d) > 1:
                                    draw_3d_polyline(conc_d_3d, 'CONCILIADO_DISEÑO')
                        
                        # Reconciled Topo profile
                        if i < len(st.session_state.params_topo) and st.session_state.params_topo[i].benches:
                            rt, ret = build_reconciled_profile(st.session_state.params_topo[i].benches)
                            if len(rt) > 0:
                                conc_t_3d = to_3d(rt, ret)
                                if len(conc_t_3d) > 1:
                                    draw_3d_polyline(conc_t_3d, 'CONCILIADO_TOPO')
                        
                        # Section label
                        mid_z = float(max(pd_prof.elevations.max(), pt_prof.elevations.max())) + 3
                        label_text = f"{safe_name} [{status}]"
                        msp.add_text(
                            label_text,
                            dxfattribs={
                                'height': 2.0,
                                'layer': 'ETIQUETAS',
                                'insert': (ox, oy, mid_z)
                            }
                        )
                        
                        n_exported += 1
                    
                    progress_bar.progress((i + 1) / len(st.session_state.sections))
                
                # Save to temp file
                import tempfile
                tmp_path = os.path.join(tempfile.gettempdir(), "Perfiles_3D.dxf")
                doc.saveas(tmp_path)
                
                with open(tmp_path, "rb") as f:
                    dxf_bytes = f.read()
                
                st.download_button(
                    label=f"⬇️ Descargar DXF 3D ({n_exported} secciones)",
                    data=dxf_bytes,
                    file_name="Perfiles_3D.dxf",
                    mime="application/dxf",
                )
            st.success(f"✅ {n_exported} perfiles exportados a DXF 3D exitosamente")

# =====================================================
# FOOTER
# =====================================================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    Conciliación Geotécnica v1.1 | Herramienta de análisis Diseño vs As-Built<br>
    Parámetros: Banco 15m | Cara 65°-75° | Berma 8-10m
</div>
""", unsafe_allow_html=True)
