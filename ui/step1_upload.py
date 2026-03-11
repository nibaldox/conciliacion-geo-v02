"""
Step 1: Load design and topographic surfaces (STL/OBJ/PLY/DXF).
Renders the file upload widgets, 3D view, and plan/contour view.
"""
import os
import tempfile

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import load_mesh, get_mesh_bounds, mesh_to_plotly, decimate_mesh
from ui.plots import draw_sections_on_figure, mesh_to_contour_data


def render_step1() -> None:
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

    if file_design and file_topo:
        fingerprint_d = (file_design.name, file_design.size)
        fingerprint_t = (file_topo.name, file_topo.size)
        if (st.session_state.get('_fp_design') != fingerprint_d or
                st.session_state.get('_fp_topo') != fingerprint_t):
            _load_meshes(file_design, file_topo)
            st.session_state['_fp_design'] = fingerprint_d
            st.session_state['_fp_topo'] = fingerprint_t

    if st.session_state.mesh_design is not None and st.session_state.mesh_topo is not None:
        _render_3d_view()
        _render_contour_view()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

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

        with st.spinner("Cargando superficies..."):
            st.session_state.mesh_design = load_mesh(f_design)
            st.session_state.mesh_topo = load_mesh(f_topo)
            st.session_state.bounds_design = get_mesh_bounds(st.session_state.mesh_design)
            st.session_state.bounds_topo = get_mesh_bounds(st.session_state.mesh_topo)

        col1, col2 = st.columns(2)
        with col1:
            bd = st.session_state.bounds_design
            st.success(f"✅ Diseño cargado: {bd['n_faces']:,} caras, {bd['n_vertices']:,} vértices")
            st.caption(
                f"X: [{bd['xmin']:.1f}, {bd['xmax']:.1f}] | "
                f"Y: [{bd['ymin']:.1f}, {bd['ymax']:.1f}] | "
                f"Z: [{bd['zmin']:.1f}, {bd['zmax']:.1f}]")
        with col2:
            bt = st.session_state.bounds_topo
            st.success(f"✅ Topografía cargada: {bt['n_faces']:,} caras, {bt['n_vertices']:,} vértices")
            st.caption(
                f"X: [{bt['xmin']:.1f}, {bt['xmax']:.1f}] | "
                f"Y: [{bt['ymin']:.1f}, {bt['ymax']:.1f}] | "
                f"Z: [{bt['zmin']:.1f}, {bt['zmax']:.1f}]")

        st.session_state.step = max(st.session_state.step, 2)
        # Invalidar caché de mallas decimadas al cargar nuevas
        st.session_state.pop('_dec_design', None)
        st.session_state.pop('_dec_topo', None)

    except Exception as e:
        st.error(f"Error al cargar: {e}")
    finally:
        for tmp in (f_design, f_topo):
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def _render_3d_view() -> None:
    with st.expander("🌐 Vista 3D de Superficies", expanded=False):
        with st.spinner("Generando vista 3D..."):
            fig = go.Figure()
            if '_dec_design' not in st.session_state:
                st.session_state['_dec_design'] = decimate_mesh(st.session_state.mesh_design, 30000)
                st.session_state['_dec_topo'] = decimate_mesh(st.session_state.mesh_topo, 30000)
            md = st.session_state['_dec_design']
            mt = st.session_state['_dec_topo']
            fig.add_trace(mesh_to_plotly(md, "Diseño", "royalblue", 1.0))
            fig.add_trace(mesh_to_plotly(mt, "Topografía Real", "forestgreen", 1.0))

            if st.session_state.sections:
                bd = st.session_state.bounds_design
                zref = (bd['zmin'] + bd['zmax']) / 2
                draw_sections_on_figure(fig, st.session_state.sections, is_3d=True, zref=zref)

            fig.update_layout(
                scene=dict(
                    aspectmode='data',
                    xaxis_title='Este (m)', yaxis_title='Norte (m)', zaxis_title='Elevación (m)'),
                height=600, margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
            )
            st.plotly_chart(fig, use_container_width=True)


def _render_contour_view() -> None:
    with st.expander("🗺️ Vista en Planta — Curvas de Nivel", expanded=False):
        with st.spinner("Generando curvas de nivel..."):
            import numpy as np
            contour_cols = st.columns(3)
            contour_surface = contour_cols[0].selectbox(
                "Superficie", ["Diseño", "Topografía", "Ambas"], key="contour_surf")
            contour_interval = contour_cols[1].number_input(
                "Intervalo curvas (m)", value=15.0, min_value=1.0, step=1.0, key="contour_int")
            contour_grid = contour_cols[2].number_input(
                "Resolución grilla", value=500, min_value=100, max_value=2000,
                step=100, key="contour_grid")

            # grid_ref comes from sidebar via session state fallback
            grid_ref = st.session_state.get('_grid_ref', 0.0)

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
            st.plotly_chart(fig_contour, use_container_width=True)
