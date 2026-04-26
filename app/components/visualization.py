"""Vista 3D + curvas de nivel + plan view de las superficies cargadas."""
import streamlit as st
import numpy as np
import plotly.graph_objects as go

from core import decimate_mesh, mesh_to_plotly
from core.section_cutter import azimuth_to_direction as _az2dir


@st.cache_data(show_spinner=False)
def _mesh_to_contour_data(_mesh, grid_size=500):
    """Interpolate mesh vertices onto a regular grid for contour plotting."""
    from scipy.interpolate import griddata

    if _mesh is None:
        return None, None, None, None, None

    verts = _mesh.vertices
    # Subsample if too many vertices to avoid slow griddata
    if len(verts) > 200000:
        step = len(verts) // 200000
        verts = verts[::step]

    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]

    xi = np.linspace(x.min(), x.max(), grid_size)
    yi = np.linspace(y.min(), y.max(), grid_size)
    xi_grid, yi_grid = np.meshgrid(xi, yi)

    zi_grid = griddata((x, y), z, (xi_grid, yi_grid), method='linear')
    return xi, yi, xi_grid, yi_grid, zi_grid


def render_visualization_sections():
    """Render the two expanders: 3D surface view + contour plan view."""
    grid_ref = st.session_state.get('grid_ref', 0.0)

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
                        x=[p1[0], p2[0]], y=[p1[1], p2[1]], z=[(zmin + zmax) / 2] * 2,
                        mode='lines+text', text=[sec.name, ""],
                        line=dict(color='red', width=5),
                        name=sec.name, showlegend=False,
                    ))

            fig.update_layout(
                scene=dict(
                    aspectmode='data',
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
