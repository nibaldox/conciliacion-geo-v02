"""Simulador de Monitoreo Radar Geotécnico.

Página Streamlit con dos modos de análisis:
  Tab 1 — Cobertura desde Radar : ingresa posición del radar → visualiza área visible
  Tab 2 — Ubicación del Radar   : ingresa área objetivo → sugiere mejores posiciones

Algoritmo central: Line-of-Sight (LOS) ray-casting sobre malla 3D (trimesh).
"""

import io
import tempfile
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from shapely.geometry import Polygon, Point

from core.mesh_handler import load_mesh, get_mesh_bounds, decimate_mesh
from core.radar_simulator import (
    RadarParams,
    ViewshedResult,
    RadarCandidate,
    compute_viewshed,
    find_radar_locations,
    polygon_from_text,
    polygon_from_csv_bytes,
    sample_polygon_on_mesh,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Simulador Radar Geotécnico",
    page_icon="📡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

QUALITY_OPTIONS = {
    "Rápido (500 puntos)": 500,
    "Normal (2 000 puntos)": 2000,
    "Alta precisión (5 000 puntos)": 5000,
}

_POLYGON_HELP = (
    "Una coordenada por línea, separadas por coma, espacio o punto y coma.\n"
    "Ejemplo:\n"
    "  365000, 7645000\n"
    "  365500, 7645000\n"
    "  365500, 7645500\n"
    "  365000, 7645500"
)


def _load_mesh_from_upload(uploaded_file) -> tuple:
    """Load trimesh from Streamlit UploadedFile. Returns (mesh, bounds) or (None, None)."""
    suffix = os.path.splitext(uploaded_file.name)[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    try:
        mesh = load_mesh(tmp_path)
        bounds = get_mesh_bounds(mesh)
        return mesh, bounds
    except Exception as e:
        st.error(f"Error al cargar la malla: {e}")
        return None, None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _mesh_plotly_trace(mesh, name="Topografía", color="#8B7355", opacity=0.55):
    """Return a go.Mesh3d trace for the (decimated) mesh."""
    disp = decimate_mesh(mesh, target_faces=20_000)
    v = disp.vertices
    f = disp.faces
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=f[:, 0], j=f[:, 1], k=f[:, 2],
        color=color, opacity=opacity,
        name=name, showlegend=True,
        lighting=dict(diffuse=0.8, ambient=0.4),
    )


def _polygon_outline_trace(polygon: Polygon, z_val: float, name: str, color: str, dash="solid"):
    """Return a go.Scatter3d trace drawing the polygon outline at fixed Z."""
    if polygon is None or polygon.is_empty:
        return None
    xs, ys = polygon.exterior.xy
    zs = [z_val] * len(xs)
    return go.Scatter3d(
        x=list(xs), y=list(ys), z=zs,
        mode="lines",
        line=dict(color=color, width=4, dash=dash),
        name=name,
    )


def _radar_marker_trace(pos: np.ndarray, name="Radar"):
    """Return a go.Scatter3d marker for the radar position."""
    return go.Scatter3d(
        x=[pos[0]], y=[pos[1]], z=[pos[2]],
        mode="markers+text",
        marker=dict(symbol="diamond", size=10, color="yellow",
                    line=dict(color="black", width=2)),
        text=[name], textposition="top center",
        name=name,
    )


def _build_viewshed_figure(mesh, result: ViewshedResult) -> go.Figure:
    """Build 3D Plotly figure showing visible / blocked areas from the radar."""
    fig = go.Figure()

    # Mesh background
    fig.add_trace(_mesh_plotly_trace(mesh))

    # Blocked points (red, semi-transparent)
    if len(result.blocked_points) > 0:
        bp = result.blocked_points
        fig.add_trace(go.Scatter3d(
            x=bp[:, 0], y=bp[:, 1], z=bp[:, 2],
            mode="markers",
            marker=dict(size=2, color="red", opacity=0.3),
            name="Sin visibilidad",
        ))

    # Visible points (green)
    if len(result.visible_points) > 0:
        vp = result.visible_points
        fig.add_trace(go.Scatter3d(
            x=vp[:, 0], y=vp[:, 1], z=vp[:, 2],
            mode="markers",
            marker=dict(size=3, color="limegreen", opacity=0.8),
            name="Área visible",
        ))

    # Radar position
    fig.add_trace(_radar_marker_trace(result.radar_position))

    # Coverage polygon projected at mesh bottom
    z_ref = float(mesh.bounds[0][2]) - 5
    if result.coverage_polygon_2d is not None:
        tr = _polygon_outline_trace(
            result.coverage_polygon_2d, z_ref,
            "Contorno cobertura (planta)", "limegreen", dash="dot"
        )
        if tr:
            fig.add_trace(tr)

    fig.update_layout(
        scene=dict(
            xaxis_title="Este (m)", yaxis_title="Norte (m)", zaxis_title="Elevación (m)",
            aspectmode="data",
        ),
        legend=dict(x=0, y=1),
        margin=dict(l=0, r=0, t=30, b=0),
        height=600,
    )
    return fig


def _build_candidates_figure(mesh, candidates: list, target_poly: Polygon,
                              top_n: int = 20) -> go.Figure:
    """Build 3D Plotly figure showing top radar candidate positions."""
    fig = go.Figure()
    fig.add_trace(_mesh_plotly_trace(mesh))

    # Target polygon outline
    z_mid = float(mesh.centroid[2])
    tr = _polygon_outline_trace(target_poly, z_mid, "Área objetivo", "red")
    if tr:
        fig.add_trace(tr)

    shown = candidates[:top_n]
    if shown:
        scores = np.array([c.coverage_score for c in shown])
        # Normalise for colour scale
        s_min, s_max = scores.min(), scores.max()
        norm = (scores - s_min) / max(s_max - s_min, 1e-9)

        positions = np.array([c.position for c in shown])
        fig.add_trace(go.Scatter3d(
            x=positions[:, 0], y=positions[:, 1], z=positions[:, 2],
            mode="markers",
            marker=dict(
                size=8,
                color=scores * 100,
                colorscale="RdYlGn",
                cmin=0, cmax=100,
                colorbar=dict(title="Cobertura %", x=1.02),
                line=dict(color="black", width=1),
            ),
            customdata=np.column_stack([scores * 100,
                                        [c.distance_to_centroid for c in shown]]),
            hovertemplate=(
                "<b>X:</b> %{x:.1f} m<br>"
                "<b>Y:</b> %{y:.1f} m<br>"
                "<b>Z:</b> %{z:.1f} m<br>"
                "<b>Cobertura:</b> %{customdata[0]:.1f}%<br>"
                "<b>Dist. al objetivo:</b> %{customdata[1]:.0f} m<extra></extra>"
            ),
            name="Candidatos",
        ))

    fig.update_layout(
        scene=dict(
            xaxis_title="Este (m)", yaxis_title="Norte (m)", zaxis_title="Elevación (m)",
            aspectmode="data",
        ),
        legend=dict(x=0, y=1),
        margin=dict(l=0, r=0, t=30, b=0),
        height=600,
    )
    return fig


def _polygon_input_widget(key_prefix: str, bounds: dict) -> Polygon | None:
    """Render a polygon input UI and return a shapely Polygon or None."""
    input_method = st.radio(
        "Método de entrada",
        ["Texto manual", "Archivo CSV", "Bounding box"],
        horizontal=True,
        key=f"{key_prefix}_method",
    )

    polygon = None

    if input_method == "Texto manual":
        txt = st.text_area(
            "Coordenadas del polígono (X,Y — una por línea)",
            height=160,
            key=f"{key_prefix}_text",
            help=_POLYGON_HELP,
        )
        if txt.strip():
            polygon = polygon_from_text(txt)
            if polygon is None:
                st.warning("No se pudo parsear el polígono. Verifica el formato.")

    elif input_method == "Archivo CSV":
        csv_file = st.file_uploader(
            "CSV con columnas X, Y (o Este, Norte)",
            type=["csv", "txt"],
            key=f"{key_prefix}_csv",
        )
        if csv_file:
            polygon = polygon_from_csv_bytes(csv_file.getvalue())
            if polygon is None:
                st.warning("No se pudo parsear el CSV. Asegúrate de tener columnas X e Y.")

    else:  # Bounding box
        if bounds:
            cx = (bounds["x_min"] + bounds["x_max"]) / 2
            cy = (bounds["y_min"] + bounds["y_max"]) / 2
            dx = (bounds["x_max"] - bounds["x_min"]) * 0.15
            dy = (bounds["y_max"] - bounds["y_min"]) * 0.15
        else:
            cx, cy, dx, dy = 0.0, 0.0, 200.0, 200.0

        col1, col2 = st.columns(2)
        with col1:
            x_min = st.number_input("X mínimo (Este)", value=cx - dx, key=f"{key_prefix}_xmin", format="%.2f")
            y_min = st.number_input("Y mínimo (Norte)", value=cy - dy, key=f"{key_prefix}_ymin", format="%.2f")
        with col2:
            x_max = st.number_input("X máximo (Este)", value=cx + dx, key=f"{key_prefix}_xmax", format="%.2f")
            y_max = st.number_input("Y máximo (Norte)", value=cy + dy, key=f"{key_prefix}_ymax", format="%.2f")

        if x_max > x_min and y_max > y_min:
            polygon = Polygon([
                (x_min, y_min), (x_max, y_min),
                (x_max, y_max), (x_min, y_max),
            ])

    if polygon is not None and not polygon.is_valid:
        polygon = polygon.buffer(0)

    return polygon


# ---------------------------------------------------------------------------
# Main page layout
# ---------------------------------------------------------------------------

st.title("📡 Simulador de Monitoreo Radar Geotécnico")
st.markdown(
    "Herramienta para análisis de línea de visión (LOS) de radares "
    "de deformación (IBIS, GroundProbe SSR, etc.) sobre topografía 3D."
)

# ---------------------------------------------------------------------------
# Shared: upload topography
# ---------------------------------------------------------------------------
st.markdown("---")
st.subheader("1. Cargar topografía")

with st.container():
    col_up, col_info = st.columns([2, 3])
    with col_up:
        topo_file = st.file_uploader(
            "Topografía (STL / OBJ / PLY / DXF)",
            type=["stl", "obj", "ply", "dxf"],
            help="Superficie 3D de la mina exportada desde Vulcan, Surpac u otro software.",
        )

mesh = None
bounds = None

if topo_file:
    if (
        "radar_mesh_name" not in st.session_state
        or st.session_state.get("radar_mesh_name") != topo_file.name
    ):
        with col_info:
            with st.spinner("Cargando malla..."):
                mesh, bounds = _load_mesh_from_upload(topo_file)
        if mesh is not None:
            st.session_state["radar_mesh"] = mesh
            st.session_state["radar_bounds"] = bounds
            st.session_state["radar_mesh_name"] = topo_file.name
    else:
        mesh = st.session_state.get("radar_mesh")
        bounds = st.session_state.get("radar_bounds")

if mesh is not None and bounds is not None:
    with col_info:
        st.success(
            f"✅ Malla cargada — "
            f"{bounds['n_faces']:,} caras · "
            f"E: {bounds['x_min']:.0f}–{bounds['x_max']:.0f} m · "
            f"N: {bounds['y_min']:.0f}–{bounds['y_max']:.0f} m · "
            f"Z: {bounds['z_min']:.0f}–{bounds['z_max']:.0f} m"
        )

    st.markdown("---")

    tab1, tab2 = st.tabs(
        ["📡 Cobertura desde Radar", "🔍 Ubicación Óptima del Radar"]
    )

    # -----------------------------------------------------------------------
    # TAB 1 — Viewshed: posición del radar → área visible
    # -----------------------------------------------------------------------
    with tab1:
        st.markdown(
            "**Modo:** Ingresa la posición del radar y obtén el área que puede monitorear."
        )
        st.markdown("---")

        lcol, rcol = st.columns([1, 2])

        with lcol:
            st.subheader("Parámetros del radar")

            cx = (bounds["x_min"] + bounds["x_max"]) / 2
            cy = (bounds["y_min"] + bounds["y_max"]) / 2

            radar_x = st.number_input(
                "X — Este (m)", value=float(cx), format="%.2f", key="vs_x"
            )
            radar_y = st.number_input(
                "Y — Norte (m)", value=float(cy), format="%.2f", key="vs_y"
            )

            with st.expander("Parámetros operacionales", expanded=False):
                max_range = st.slider("Alcance máximo (m)", 100, 6000, 4000, 100, key="vs_maxr")
                min_range = st.slider("Alcance mínimo (m)", 10, 500, 30, 10, key="vs_minr")
                height_off = st.slider("Altura del radar sobre terreno (m)", 1.0, 20.0, 3.0, 0.5, key="vs_hoff")

            quality = st.selectbox("Calidad de análisis", list(QUALITY_OPTIONS.keys()), index=1, key="vs_qual")
            n_samp = QUALITY_OPTIONS[quality]

            run_vs = st.button("▶ Calcular Cobertura", use_container_width=True, type="primary", key="btn_vs")

        with rcol:
            if run_vs:
                params = RadarParams(
                    max_range=max_range, min_range=min_range, height_offset=height_off
                )
                with st.spinner("Calculando líneas de visión... esto puede tomar unos segundos."):
                    result = compute_viewshed(
                        mesh,
                        np.array([radar_x, radar_y]),
                        params,
                        n_samples=n_samp,
                    )
                st.session_state["vs_result"] = result
                st.session_state["vs_mesh"] = mesh

            result = st.session_state.get("vs_result")

            if result is not None:
                # Metrics
                m1, m2, m3, m4 = st.columns(4)
                n_vis = len(result.visible_points)
                n_blk = len(result.blocked_points)
                total_pts = n_vis + n_blk
                m1.metric("Cobertura LOS", f"{result.coverage_fraction * 100:.1f}%")
                m2.metric("Puntos visibles", f"{n_vis:,}")
                m3.metric("Puntos bloqueados", f"{n_blk:,}")
                m4.metric("Área aprox. visible", f"{result.coverage_area_m2 / 1e6:.2f} km²"
                          if result.coverage_area_m2 > 1e6 else f"{result.coverage_area_m2:,.0f} m²")

                st.markdown(
                    f"📍 **Posición del radar:** "
                    f"E={result.radar_position[0]:.1f} m, "
                    f"N={result.radar_position[1]:.1f} m, "
                    f"Z={result.radar_position[2]:.1f} m"
                )

                fig = _build_viewshed_figure(mesh, result)
                st.plotly_chart(fig, use_container_width=True)

                # Download visible points as CSV
                if len(result.visible_points) > 0:
                    df_vis = pd.DataFrame(
                        result.visible_points, columns=["Este_m", "Norte_m", "Elev_m"]
                    )
                    csv_bytes = df_vis.to_csv(index=False).encode()
                    st.download_button(
                        "⬇ Descargar puntos visibles (CSV)",
                        data=csv_bytes,
                        file_name="cobertura_radar.csv",
                        mime="text/csv",
                    )
            else:
                st.info(
                    "Configura los parámetros del radar y presiona **Calcular Cobertura** "
                    "para ver el área de monitoreo."
                )
                # Show mesh preview
                with st.spinner("Generando vista previa..."):
                    prev_fig = go.Figure()
                    prev_fig.add_trace(_mesh_plotly_trace(mesh))
                    prev_fig.add_trace(go.Scatter3d(
                        x=[cx], y=[cy], z=[bounds["z_max"] + 5],
                        mode="markers+text",
                        marker=dict(symbol="diamond", size=10, color="yellow",
                                    line=dict(color="black", width=2)),
                        text=["Radar (posición inicial)"], textposition="top center",
                        name="Radar",
                    ))
                    prev_fig.update_layout(
                        scene=dict(aspectmode="data",
                                   xaxis_title="Este", yaxis_title="Norte", zaxis_title="Elev"),
                        height=500, margin=dict(l=0, r=0, t=20, b=0)
                    )
                st.plotly_chart(prev_fig, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 2 — Inverse: área objetivo → mejores posiciones del radar
    # -----------------------------------------------------------------------
    with tab2:
        st.markdown(
            "**Modo:** Define el área a monitorear y el área de búsqueda. "
            "El sistema evalúa una grilla de posibles ubicaciones del radar "
            "y ordena las mejores por porcentaje de cobertura."
        )
        st.markdown("---")

        col_left, col_right = st.columns([1, 2])

        with col_left:
            st.subheader("Área objetivo (a monitorear)")
            target_poly = _polygon_input_widget("target", bounds)

            if target_poly is not None:
                st.success(
                    f"Polígono objetivo cargado — "
                    f"área ≈ {target_poly.area:,.0f} m²"
                )
            else:
                st.info("Define el polígono del área a monitorear.")

            st.markdown("---")
            st.subheader("Área de búsqueda (donde puede ubicarse el radar)")
            search_poly = _polygon_input_widget("search", bounds)

            if search_poly is not None:
                st.success(
                    f"Polígono de búsqueda cargado — "
                    f"área ≈ {search_poly.area:,.0f} m²"
                )

            st.markdown("---")
            st.subheader("Configuración de búsqueda")

            with st.expander("Parámetros del radar", expanded=False):
                inv_max_range = st.slider("Alcance máximo (m)", 100, 6000, 4000, 100, key="inv_maxr")
                inv_min_range = st.slider("Alcance mínimo (m)", 10, 500, 30, 10, key="inv_minr")
                inv_height = st.slider("Altura radar s/ terreno (m)", 1.0, 20.0, 3.0, 0.5, key="inv_hoff")

            grid_spacing = st.slider(
                "Espaciado de grilla (m)",
                min_value=20, max_value=500, value=100, step=10,
                help="Menor espaciado = más candidatos evaluados = más lento.",
                key="inv_grid",
            )
            min_cov = st.slider(
                "Cobertura mínima (%)", 0, 100, 25, 5, key="inv_mincov"
            ) / 100.0
            n_target_samp = st.selectbox(
                "Muestras en área objetivo",
                [100, 200, 400],
                index=1,
                help="Más muestras = más preciso pero más lento.",
                key="inv_nsamp",
            )

            run_inv = st.button(
                "▶ Buscar Ubicaciones", use_container_width=True, type="primary", key="btn_inv",
                disabled=(target_poly is None or search_poly is None),
            )
            if target_poly is None or search_poly is None:
                st.caption("⚠ Define ambos polígonos para habilitar la búsqueda.")

        with col_right:
            if run_inv and target_poly is not None and search_poly is not None:
                params_inv = RadarParams(
                    max_range=inv_max_range,
                    min_range=inv_min_range,
                    height_offset=inv_height,
                )

                # Estimate candidate count
                bds = search_poly.bounds
                nx = max(1, int((bds[2] - bds[0]) / grid_spacing))
                ny = max(1, int((bds[3] - bds[1]) / grid_spacing))
                est = nx * ny
                st.info(f"Evaluando ≈ {est} posiciones candidatas con {n_target_samp} puntos de muestra en el objetivo...")

                progress_bar = st.progress(0.0)

                def _progress(v: float):
                    progress_bar.progress(min(v, 1.0))

                with st.spinner("Analizando visibilidad..."):
                    candidates = find_radar_locations(
                        mesh=mesh,
                        target_polygon=target_poly,
                        search_polygon=search_poly,
                        params=params_inv,
                        grid_spacing=grid_spacing,
                        min_coverage=min_cov,
                        n_target_samples=n_target_samp,
                        progress_callback=_progress,
                    )

                progress_bar.progress(1.0)
                st.session_state["inv_candidates"] = candidates
                st.session_state["inv_target_poly"] = target_poly
                st.session_state["inv_mesh"] = mesh

            candidates = st.session_state.get("inv_candidates")
            target_poly_stored = st.session_state.get("inv_target_poly")

            if candidates is not None:
                if len(candidates) == 0:
                    st.warning(
                        "No se encontraron ubicaciones con la cobertura mínima requerida. "
                        "Intenta reducir la cobertura mínima, ampliar el área de búsqueda "
                        "o aumentar el alcance máximo del radar."
                    )
                else:
                    st.success(
                        f"✅ Se encontraron **{len(candidates)} ubicaciones** con "
                        f"cobertura ≥ {min_cov * 100:.0f}%"
                    )

                    # --- 3D Figure ---
                    fig2 = _build_candidates_figure(mesh, candidates, target_poly_stored or target_poly)
                    st.plotly_chart(fig2, use_container_width=True)

                    # --- Results table ---
                    st.subheader("Top ubicaciones")
                    top_n = min(50, len(candidates))
                    rows = []
                    for i, c in enumerate(candidates[:top_n]):
                        rows.append({
                            "Rank": i + 1,
                            "Este (m)": f"{c.position[0]:.1f}",
                            "Norte (m)": f"{c.position[1]:.1f}",
                            "Elevación (m)": f"{c.position[2]:.1f}",
                            "Cobertura (%)": f"{c.coverage_score * 100:.1f}",
                            "Puntos visibles": c.visible_count,
                            "Total evaluados": c.total_count,
                            "Dist. al objetivo (m)": f"{c.distance_to_centroid:.0f}",
                        })
                    df_cands = pd.DataFrame(rows)
                    st.dataframe(df_cands, use_container_width=True, hide_index=True)

                    # --- Coverage bar chart ---
                    st.subheader("Distribución de cobertura — Top 20")
                    top20 = candidates[:20]
                    fig_bar = go.Figure(go.Bar(
                        x=[f"C{i+1}" for i in range(len(top20))],
                        y=[c.coverage_score * 100 for c in top20],
                        marker_color=[
                            f"rgb({int(255*(1-c.coverage_score))},{int(200*c.coverage_score)},50)"
                            for c in top20
                        ],
                        text=[f"{c.coverage_score*100:.1f}%" for c in top20],
                        textposition="outside",
                    ))
                    fig_bar.update_layout(
                        yaxis_title="Cobertura (%)",
                        xaxis_title="Candidato",
                        height=300,
                        margin=dict(l=20, r=20, t=10, b=20),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

                    # --- Download ---
                    all_rows = [
                        {
                            "Rank": i + 1,
                            "Este_m": c.position[0],
                            "Norte_m": c.position[1],
                            "Elevacion_m": c.position[2],
                            "Cobertura_pct": round(c.coverage_score * 100, 2),
                            "Puntos_visibles": c.visible_count,
                            "Total_evaluados": c.total_count,
                            "Dist_objetivo_m": round(c.distance_to_centroid, 1),
                        }
                        for i, c in enumerate(candidates)
                    ]
                    df_all = pd.DataFrame(all_rows)
                    st.download_button(
                        "⬇ Descargar todas las ubicaciones (CSV)",
                        data=df_all.to_csv(index=False).encode(),
                        file_name="ubicaciones_radar.csv",
                        mime="text/csv",
                    )
            else:
                st.info(
                    "Define el área objetivo y el área de búsqueda, "
                    "luego presiona **Buscar Ubicaciones**."
                )
                # Show mesh preview
                with st.spinner("Generando vista previa..."):
                    prev_fig2 = go.Figure()
                    prev_fig2.add_trace(_mesh_plotly_trace(mesh))
                    prev_fig2.update_layout(
                        scene=dict(aspectmode="data",
                                   xaxis_title="Este", yaxis_title="Norte", zaxis_title="Elev"),
                        height=500, margin=dict(l=0, r=0, t=20, b=0)
                    )
                st.plotly_chart(prev_fig2, use_container_width=True)

else:
    st.info(
        "⬆ Carga un archivo de topografía (STL / OBJ / PLY / DXF) "
        "para comenzar el análisis de monitoreo radar."
    )
    st.markdown("""
    ---
    ### ¿Cómo funciona?

    #### 📡 Modo Cobertura (Viewshed)
    Ingresa la posición **(X, Y)** donde está o se planea instalar el radar.
    El sistema lanza rayos desde esa posición hacia la superficie topográfica y
    determina qué zonas tienen **línea de visión directa (LOS)**.

    #### 🔍 Modo Ubicación Inversa
    Define **dónde quieres monitorear** (polígono objetivo) y
    **en qué zona puede ubicarse el radar** (polígono de búsqueda).
    El sistema evalúa una grilla de posiciones candidatas y las ordena
    por porcentaje de cobertura del área objetivo.

    ---
    ### Parámetros típicos para radares geotécnicos

    | Parámetro | IBIS-FM | GroundProbe SSR |
    |-----------|---------|-----------------|
    | Alcance máximo | 4 000 m | 3 000 m |
    | Alcance mínimo | 30 m | 30 m |
    | Apertura (az.) | ~17° | ~120° |
    | Resolución LOS | ~4 mm | ~1 mm |

    > **Nota:** Este simulador analiza visibilidad geométrica (LOS) sin modelar
    > atenuación por polvo, lluvia o características de la antena.
    """)
