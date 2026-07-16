"""3D visualization tab for processed blast holes."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import streamlit as st

from core.config import DEFAULTS
from core.geom_utils import find_df_column
from ui.modulo_tronadura.figures import (
    build_color_options,
    build_energy_grid,
    build_energy_surface_trace,
    build_line_arrays,
    build_three_d_figure,
    get_available_colorscales,
    is_discrete_color_option,
)
from ui.modulo_tronadura.state import (
    get_blast_df,
    get_decimated_mesh_design,
    get_decimated_mesh_topo,
    get_idw_grid_params,
    get_last_idw_grid,
    get_mesh_design,
    get_mesh_topo,
    set_decimated_mesh_design,
    set_decimated_mesh_topo,
    set_last_idw_grid,
)

logger = logging.getLogger(__name__)


def render_three_d_tab(df_clean: pd.DataFrame) -> None:
    """Render the "📊 Visualización 3D y Filtros" tab."""
    with st.expander("🔎 Filtros de Tronadura", expanded=False):
        df_filtered = _render_filters_and_apply(df_clean)

    if df_filtered.empty:
        st.warning("⚠️ No hay pozos que coincidan con los filtros seleccionados.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Pozos filtrados", len(df_filtered), f"{len(df_filtered) - len(df_clean)} respecto al total")
    col2.metric(
        "Elevación collar",
        f"{df_filtered['Z_collar'].min():.1f} – {df_filtered['Z_collar'].max():.1f} m",
    )
    col3.metric(
        "Profundidad promedio",
        f"{df_filtered['Len'].mean():.1f} m",
    )

    with st.expander("🎨 Opciones de Visualización 3D", expanded=True):
        color_by, sel_colorscale, show_energy_grid, show_design_mesh, show_topo_mesh = _render_3d_options(df_clean)

    x_lines, y_lines, z_lines = build_line_arrays(df_filtered)

    design_mesh_trace = _get_design_mesh_trace(show_design_mesh)
    topo_mesh_trace = _get_topo_mesh_trace(show_topo_mesh)
    energy_surface_trace = _get_energy_surface_trace(df_filtered, show_energy_grid)

    fig = build_three_d_figure(
        df_filtered,
        x_lines,
        y_lines,
        z_lines,
        color_by,
        sel_colorscale,
        design_mesh_trace=design_mesh_trace,
        topo_mesh_trace=topo_mesh_trace,
        energy_surface_trace=energy_surface_trace,
    )
    st.plotly_chart(fig, width="stretch")

    if show_energy_grid and get_last_idw_grid() is not None:
        _render_idw_download()

    with st.expander("📋 Datos procesados (Filtrados)", expanded=False):
        st.dataframe(df_filtered, width="stretch")


def _render_filters_and_apply(df_clean: pd.DataFrame) -> pd.DataFrame:
    malla_col = find_df_column(df_clean, ["Nombre_Malla_Original"], raise_error=False)
    poligono_col = find_df_column(df_clean, ["holes_polygon"], raise_error=False)
    banco_col = find_df_column(df_clean, ["Banco_Original", "Nombre_Banco", "Banco"], raise_error=False)
    fase_col = find_df_column(df_clean, ["Nombre_Fase", "Fase"], raise_error=False)
    kg_col = find_df_column(
        df_clean, ["Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"],
        raise_error=False,
    )

    filter_cols = []
    if malla_col:
        filter_cols.append("malla")
    if poligono_col:
        filter_cols.append("poligono")
    if banco_col:
        filter_cols.append("banco")
    if fase_col:
        filter_cols.append("fase")
    filter_cols.append("len")
    if kg_col:
        filter_cols.append("kg")

    f_cols = st.columns(len(filter_cols))
    col_idx = 0

    sel_mallas = []
    if malla_col:
        all_mallas = sorted(df_clean[malla_col].dropna().astype(str).unique().tolist())
        sel_mallas = f_cols[col_idx].multiselect("Filtrar por Malla (Grid):", all_mallas, default=[])
        col_idx += 1

    sel_poligonos = []
    if poligono_col:
        all_poligonos = sorted(df_clean[poligono_col].dropna().astype(str).unique().tolist())
        sel_poligonos = f_cols[col_idx].multiselect("Filtrar por Polígono:", all_poligonos, default=[])
        col_idx += 1

    sel_bancos = []
    if banco_col:
        all_bancos = sorted(df_clean[banco_col].dropna().astype(str).unique().tolist())
        sel_bancos = f_cols[col_idx].multiselect("Filtrar por Banco:", all_bancos, default=[])
        col_idx += 1

    sel_fases = []
    if fase_col:
        all_fases = sorted(df_clean[fase_col].dropna().astype(str).unique().tolist())
        sel_fases = f_cols[col_idx].multiselect("Filtrar por Fase:", all_fases, default=[])
        col_idx += 1

    min_len = float(df_clean["Len"].min())
    max_len = float(df_clean["Len"].max())
    if min_len < max_len:
        sel_len = f_cols[col_idx].slider("Profundidad (m):", min_len, max_len, (min_len, max_len))
    else:
        sel_len = (min_len, max_len)
    col_idx += 1

    sel_kg = None
    if kg_col:
        min_kg = float(df_clean[kg_col].fillna(0).min())
        max_kg = float(df_clean[kg_col].fillna(0).max())
        if min_kg < max_kg:
            sel_kg = f_cols[col_idx].slider("Explosivo (Kg):", min_kg, max_kg, (min_kg, max_kg))
        else:
            sel_kg = (min_kg, max_kg)

    df_filtered = df_clean.copy()
    if sel_mallas and malla_col:
        df_filtered = df_filtered[df_filtered[malla_col].astype(str).isin(sel_mallas)]
    if sel_poligonos and poligono_col:
        df_filtered = df_filtered[df_filtered[poligono_col].astype(str).isin(sel_poligonos)]
    if sel_bancos and banco_col:
        df_filtered = df_filtered[df_filtered[banco_col].astype(str).isin(sel_bancos)]
    if sel_fases and fase_col:
        df_filtered = df_filtered[df_filtered[fase_col].astype(str).isin(sel_fases)]
    if sel_len:
        df_filtered = df_filtered[(df_filtered["Len"] >= sel_len[0]) & (df_filtered["Len"] <= sel_len[1])]
    if sel_kg and kg_col:
        df_filtered = df_filtered[
            (df_filtered[kg_col].fillna(0) >= sel_kg[0]) &
            (df_filtered[kg_col].fillna(0) <= sel_kg[1])
        ]

    return df_filtered


def _render_3d_options(df_clean: pd.DataFrame) -> tuple[str, str, bool, bool, bool]:
    col_v1, col_v2, col_v3 = st.columns(3)

    color_options = build_color_options(df_clean)
    color_by = col_v1.selectbox(
        "Colorear pozos en 3D por:",
        color_options,
        index=0,
    )

    all_colorscales = get_available_colorscales()
    colorscale_disabled = is_discrete_color_option(color_by)
    sel_colorscale = col_v2.selectbox(
        "Paleta de Colores (Continuos):",
        all_colorscales,
        index=0,
        disabled=colorscale_disabled,
    )

    show_energy_grid = col_v3.checkbox("⚡ Mostrar Densidad de Energía 3D (IDW)", value=False)

    show_design_mesh = False
    show_topo_mesh = False
    has_d_mesh = get_mesh_design() is not None
    has_t_mesh = get_mesh_topo() is not None

    if has_d_mesh or has_t_mesh:
        st.markdown("**Superficies 3D de Referencia:**")
        col_m1, col_m2 = st.columns(2)
        if has_d_mesh:
            show_design_mesh = col_m1.checkbox("🔵 Mostrar Superficie de Diseño (Transparente)", value=False)
        if has_t_mesh:
            show_topo_mesh = col_m2.checkbox("🟢 Mostrar Topografía Real (As-Built Transparente)", value=False)

    return color_by, sel_colorscale, show_energy_grid, show_design_mesh, show_topo_mesh


def _get_design_mesh_trace(show_design_mesh: bool):
    if not show_design_mesh:
        return None
    md = get_decimated_mesh_design()
    if md is None and get_mesh_design() is not None:
        from core import decimate_mesh
        md = decimate_mesh(get_mesh_design(), DEFAULTS.target_faces_visual)
        set_decimated_mesh_design(md)
    if md is None:
        return None
    from core import mesh_to_plotly
    return mesh_to_plotly(md, "Superficie Diseño", "royalblue", 0.35)


def _get_topo_mesh_trace(show_topo_mesh: bool):
    if not show_topo_mesh:
        return None
    mt = get_decimated_mesh_topo()
    if mt is None and get_mesh_topo() is not None:
        from core import decimate_mesh
        mt = decimate_mesh(get_mesh_topo(), DEFAULTS.target_faces_visual)
        set_decimated_mesh_topo(mt)
    if mt is None:
        return None
    from core import mesh_to_plotly
    return mesh_to_plotly(mt, "Topografía Real", "forestgreen", 0.35)


def _get_energy_surface_trace(df_filtered: pd.DataFrame, show_energy_grid: bool):
    if not show_energy_grid:
        return None

    kg_col = find_df_column(
        df_filtered,
        ["Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"],
        raise_error=False,
    )

    if len(df_filtered) < 5:
        st.info("Se requieren al menos 5 pozos para generar el heatmap de densidad.")
        return None

    grid_nx, grid_ny, grid_nz, search_radius = get_idw_grid_params()
    energy_grid = build_energy_grid(df_filtered, kg_col, grid_nx, grid_ny, grid_nz, search_radius)
    set_last_idw_grid({
        "X": energy_grid["X"],
        "Y": energy_grid["Y"],
        "Z": energy_grid["Z"],
        "Energy_kg_m2": energy_grid["Energy_kg_m2"],
    })
    return build_energy_surface_trace(energy_grid)


def _render_idw_download() -> None:
    idw_grid = get_last_idw_grid()
    if idw_grid is None:
        return

    idw_df = pd.DataFrame({
        "X": idw_grid["X"],
        "Y": idw_grid["Y"],
        "Z": idw_grid["Z"],
        "Energy_kg_m2": idw_grid["Energy_kg_m2"],
    })
    st.download_button(
        "⬇️ Descargar grilla IDW como CSV",
        data=idw_df.to_csv(index=False).encode("utf-8"),
        file_name="energy_idw.csv",
        mime="text/csv",
        key="download_idw_grid",
        help=f"Grilla {len(idw_df)} puntos (X, Y, Z, energía kg/m²).",
    )
    st.caption(
        f"Grilla IDW con {len(idw_df)} puntos calculados. "
        "Cada valor es Σ Qᵢ / dᵢ² sobre los pozos cercanos."
    )

    st.caption(
        "💡 **Heatmap de densidad de energía IDW (integrada en Z)**: cada celda "
        "del plano horizontal resume la suma ponderada gaussiana (σ = radio de "
        "búsqueda) de la carga explosiva de los pozos cercanos, sumada en toda "
        "la columna vertical. El color va de **amarillo (baja)** a **rojo intenso "
        "(alta)**; las zonas rojas indican **concentración de energía** y son "
        "candidatas a revisión (potencial sobre-excavación). La escala arranca "
        "en 0 kg/m² (sin compresión de outliers)."
    )

    col_idw1, _ = st.columns(2)
    grid_nx = col_idw1.slider(
        "Resolución XY", 10, 50, 25, key="idw_nx_widget",
        help="Cantidad de nodos en X e Y del heatmap. Más resolución = más detalle pero más lento.",
    )
    st.session_state["idw_nx"] = grid_nx
    st.session_state["idw_ny"] = grid_nx

    st.slider(
        "Radio de búsqueda σ (m)", 5, 80, 30, key="idw_radius",
        help="Desviación estándar del kernel gaussiano. Mayor = más suavizado.",
    )
