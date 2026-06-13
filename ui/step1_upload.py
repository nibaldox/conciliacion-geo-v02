"""
Step 1: Load design and topographic surfaces (STL/OBJ/PLY/DXF).
Renders the file upload widgets, 3D view, and plan/contour view.
"""
import logging
import os
import tempfile

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import load_mesh, get_mesh_bounds, mesh_to_plotly, decimate_mesh
from core.config import DEFAULTS, VISUALIZATION
from ui.plots import draw_sections_on_figure, mesh_to_contour_data

logger = logging.getLogger(__name__)


@st.cache_resource(show_spinner=False)
def _cached_decimate(_mesh, target_faces):
    return decimate_mesh(_mesh, target_faces=target_faces)


def render_step1(config: dict) -> None:
    """Render Paso 1: file upload + 3D and plan visualizations."""
    st.header("📁 Paso 1: Cargar Superficies STL / DXF")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔵 Superficie de Diseño")
        file_design = st.file_uploader(
            "Cargar Diseño (STL, OBJ, PLY, DXF)",
            type=["stl", "obj", "ply", "dxf"], key="design_file")
    with col2:
        st.subheader("🟢 Superficie Topográfica (As-Built)")
        file_topo = st.file_uploader(
            "Cargar Topografía (STL, OBJ, PLY, DXF)",
            type=["stl", "obj", "ply", "dxf"], key="topo_file")

    has_meshes = st.session_state.mesh_design is not None and st.session_state.mesh_topo is not None

    if has_meshes:
        st.info("📦 Las superficies ya están cargadas en memoria. Puedes continuar al Paso 2 o subir nuevos archivos para reemplazarlas.")
        if st.button("🧹 Limpiar superficies cargadas", type="secondary"):
            st.session_state.mesh_design = None
            st.session_state.mesh_topo = None
            st.session_state.bounds_design = None
            st.session_state.bounds_topo = None
            st.session_state.decimated_mesh_design = None
            st.session_state.decimated_mesh_topo = None
            st.session_state.mesh_design_file_name = None
            st.session_state.mesh_design_file_size = None
            st.session_state.mesh_topo_file_name = None
            st.session_state.mesh_topo_file_size = None
            st.session_state.step = 1
            st.rerun()

    # Load meshes if new files are uploaded
    if file_design and file_topo:
        d_changed = (st.session_state.get('mesh_design_file_name') != file_design.name or
                     st.session_state.get('mesh_design_file_size') != file_design.size)
        t_changed = (st.session_state.get('mesh_topo_file_name') != file_topo.name or
                     st.session_state.get('mesh_topo_file_size') != file_topo.size)

        if d_changed or t_changed or not has_meshes:
            _load_meshes(file_design, file_topo)

    if st.session_state.mesh_design is not None and st.session_state.mesh_topo is not None:
        _render_mesh_info()
        _build_or_get_3d_figure()
        _render_3d_view()
        _build_or_get_contour_figure(config)
        _render_contour_view(config)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _render_mesh_info() -> None:
    col1, col2 = st.columns(2)
    with col1:
        bd = st.session_state.bounds_design
        if bd:
            st.success(f"✅ Diseño: {bd['n_faces']:,} caras, {bd['n_vertices']:,} vértices")
            st.caption(
                f"X: [{bd['xmin']:.1f}, {bd['xmax']:.1f}] | "
                f"Y: [{bd['ymin']:.1f}, {bd['ymax']:.1f}] | "
                f"Z: [{bd['zmin']:.1f}, {bd['zmax']:.1f}]")
    with col2:
        bt = st.session_state.bounds_topo
        if bt:
            st.success(f"✅ Topografía Real: {bt['n_faces']:,} caras, {bt['n_vertices']:,} vértices")
            st.caption(
                f"X: [{bt['xmin']:.1f}, {bt['xmax']:.1f}] | "
                f"Y: [{bt['ymin']:.1f}, {bt['ymax']:.1f}] | "
                f"Z: [{bt['zmin']:.1f}, {bt['zmax']:.1f}]")


def _load_meshes(file_design, file_topo) -> None:
    from pathlib import Path

    ext_d = Path(file_design.name).suffix
    ext_t = Path(file_topo.name).suffix
    f_design = f_topo = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext_d, delete=False) as f:
            f.write(file_design.read())
            f_design = f.name
        with tempfile.NamedTemporaryFile(suffix=ext_t, delete=False) as f:
            f.write(file_topo.read())
            f_topo = f.name

        with st.spinner("Cargando y decimando superficies..."):
            mesh_d = load_mesh(f_design)
            mesh_t = load_mesh(f_topo)
            
            st.session_state.mesh_design = mesh_d
            st.session_state.mesh_topo = mesh_t
            st.session_state.bounds_design = get_mesh_bounds(mesh_d)
            st.session_state.bounds_topo = get_mesh_bounds(mesh_t)

            # Pre-decimate meshes for Plotly 3D visualization
            st.session_state.decimated_mesh_design = _cached_decimate(mesh_d, DEFAULTS.target_faces_visual)
            st.session_state.decimated_mesh_topo = _cached_decimate(mesh_t, DEFAULTS.target_faces_visual)

            # Store cache keys
            st.session_state.mesh_design_file_name = file_design.name
            st.session_state.mesh_design_file_size = file_design.size
            st.session_state.mesh_topo_file_name = file_topo.name
            st.session_state.mesh_topo_file_size = file_topo.size

        st.session_state.step = max(st.session_state.step, 2)

    except Exception as e:
        logger.exception("Failed to load mesh")
        st.error("No se pudo cargar la malla STL/DXF. Revisa la consola para detalles.")
    finally:
        for tmp in (f_design, f_topo):
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def _build_or_get_3d_figure() -> None:
    sections = st.session_state.get('sections') or []
    sections_key = tuple((s.name, tuple(s.origin), s.azimuth, s.length) for s in sections)
    cache_key = (
        id(st.session_state.mesh_design),
        id(st.session_state.mesh_topo),
        sections_key,
    )

    cached = st.session_state.get('_3d_fig')
    if cached and cached[0] == cache_key:
        return

    md = st.session_state.get('decimated_mesh_design') or _cached_decimate(
        st.session_state.mesh_design, DEFAULTS.target_faces_visual)
    mt = st.session_state.get('decimated_mesh_topo') or _cached_decimate(
        st.session_state.mesh_topo, DEFAULTS.target_faces_visual)
    st.session_state.decimated_mesh_design = md
    st.session_state.decimated_mesh_topo = mt

    fig = go.Figure()
    fig.add_trace(mesh_to_plotly(md, "Diseño", "royalblue", 1.0))
    fig.add_trace(mesh_to_plotly(mt, "Topografía Real", "forestgreen", 1.0))

    if sections:
        bd = st.session_state.bounds_design
        zref = (bd['zmin'] + bd['zmax']) / 2
        draw_sections_on_figure(fig, sections, is_3d=True, zref=zref)

    fig.update_layout(
        scene=dict(
            aspectmode='data',
            xaxis_title='Este (m)', yaxis_title='Norte (m)', zaxis_title='Elevación (m)'),
        height=600, margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    st.session_state['_3d_fig'] = (cache_key, fig)


def _render_3d_view() -> None:
    with st.expander("🌐 Vista 3D de Superficies", expanded=False):
        cached = st.session_state.get('_3d_fig')
        if not cached:
            return
        st.plotly_chart(cached[1], use_container_width=True)


def _build_or_get_contour_figure(config: dict) -> None:
    grid_ref = config.get('grid_ref', VISUALIZATION.grid_ref)
    contour_surface = st.session_state.get('contour_surf', 'Diseño')
    contour_interval = st.session_state.get('contour_int', 15.0)
    contour_grid = st.session_state.get('contour_grid', VISUALIZATION.contour_resolution)

    cache_key = (
        id(st.session_state.mesh_design),
        id(st.session_state.mesh_topo),
        grid_ref,
        contour_interval,
        int(contour_grid),
        contour_surface,
    )

    cached = st.session_state.get('_contour_fig')
    if cached and cached[0] == cache_key:
        return

    fig_contour = go.Figure()

    if contour_surface in ("Diseño", "Ambas"):
        xi, yi, _, _, zig = mesh_to_contour_data(
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
            showscale=False, name='Diseño',
            hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<br>Elev: %{z:.1f}m<extra>Diseño</extra>',
        ))

    if contour_surface in ("Topografía", "Ambas"):
        xi, yi, _, _, zig = mesh_to_contour_data(
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
            showscale=False, name='Topografía',
            hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<br>Elev: %{z:.1f}m<extra>Topo</extra>',
        ))

    if st.session_state.sections:
        draw_sections_on_figure(fig_contour, st.session_state.sections, is_3d=False)

    fig_contour.update_layout(
        xaxis_title='Este (m)', yaxis_title='Norte (m)',
        yaxis=dict(scaleanchor='x', scaleratio=1),
        height=650, margin=dict(l=60, r=20, t=30, b=40),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    st.session_state['_contour_fig'] = (cache_key, fig_contour)


def _render_contour_view(config: dict) -> None:
    with st.expander("🗺️ Vista en Planta — Curvas de Nivel", expanded=False):
        contour_cols = st.columns(3)
        contour_cols[0].selectbox(
            "Superficie", ["Diseño", "Topografía", "Ambas"], key="contour_surf")
        contour_cols[1].number_input(
            "Intervalo curvas (m)", value=15.0, min_value=1.0, step=1.0, key="contour_int")
        contour_cols[2].number_input(
            "Resolución grilla", value=VISUALIZATION.contour_resolution, min_value=100, max_value=2000,
            step=100, key="contour_grid")

        cached = st.session_state.get('_contour_fig')
        if not cached:
            return
        st.plotly_chart(cached[1], use_container_width=True)
