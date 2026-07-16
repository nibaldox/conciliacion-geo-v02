"""Pure Plotly figure builders for the tronadura module.

None of these functions call Streamlit APIs. They take DataFrames / arrays
and return ``go.Figure`` instances or trace/grid data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.config import DEFAULTS
from core.geom_utils import find_df_column
from ui.ref_lines import add_ref_lines_3d


_COLLAR_HOVERTEMPLATE = (
    "<b>%{customdata[0]}</b><br>"
    "X: %{x:.1f}<br>"
    "Y: %{y:.1f}<br>"
    "Z (collar): %{z:.1f}<br>"
    "<b>📊 Datos del Pozo</b><br>"
    "Explosivo: %{customdata[1]}<br>"
    "Kilos cargados: %{customdata[2]:.0f} kg<br>"
    "Diámetro: %{customdata[3]:.0f} mm / %{customdata[10]:.1f} pulg<br>"
    "Longitud real: %{customdata[4]:.2f} m<br>"
    "Stemming: %{customdata[5]:.2f} m<br>"
    "Altura de carga: %{customdata[6]:.2f} m<br>"
    "Densidad lineal: %{customdata[7]:.1f} kg/m<br>"
    "Inclinación: %{customdata[8]:.1f}°<br>"
    "Azimut: %{customdata[9]:.0f}°<br>"
    "%{customdata[11]}<br>"
    "%{customdata[12]}<br>"
    "<extra></extra>"
)

_SECTOR_FACE_ANGLE_NOTE = (
    "Ángulo de talud sugerido por detrás del perfil conciliado para alcanzar "
    "el FS objetivo, considerando el macizo rocoso (RMR) y la altura de banco."
)

_COLOR_CYCLE = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
]

_ALL_COLORSCALES = [
    "Inferno", "Hot", "Viridis", "Plasma", "Magma", "Cividis",
    "Rainbow", "Jet", "Earth", "YlOrRd", "RdBu", "Spectral",
    "Balance", "Electric", "Bluered", "Greens", "Reds", "Blues",
]

_DUREZA_MAP = {
    "roca suave": 1,
    "roca media": 2,
    "roca dura": 3,
    "roca muy dura": 4,
}


# ---------------------------------------------------------------------------
# Safe coercion helpers
# ---------------------------------------------------------------------------

def _safe_numeric(series, default=0.0):
    if series is None:
        return pd.Series([default])
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _safe_str(series, default="?"):
    if series is None:
        return pd.Series([default])
    return series.fillna(default).astype(str)


# ---------------------------------------------------------------------------
# Collar hover customdata
# ---------------------------------------------------------------------------

def _build_collar_customdata(df: pd.DataFrame, kg_col: str | None):
    """Return customdata array for collar hovertemplate enrichment."""
    n = len(df)
    if n == 0:
        return np.empty((0, 13), dtype=object)

    label = (
        _safe_str(df["label_pozo"]).values
        if "label_pozo" in df.columns
        else np.array(["?"] * n, dtype=object)
    )
    expl = (
        _safe_str(df["Tipo_Explosivo"]).values
        if "Tipo_Explosivo" in df.columns
        else np.array(["?"] * n, dtype=object)
    )
    kilos = (
        _safe_numeric(df[kg_col]).values
        if kg_col and kg_col in df.columns
        else np.zeros(n, dtype=float)
    )
    diam = (
        _safe_numeric(df["Diam_mm"]).values
        if "Diam_mm" in df.columns
        else np.zeros(n, dtype=float)
    )
    length = (
        _safe_numeric(df["Len"]).values
        if "Len" in df.columns
        else np.zeros(n, dtype=float)
    )
    taco = (
        _safe_numeric(df["Taco_m"]).values
        if "Taco_m" in df.columns
        else np.zeros(n, dtype=float)
    )
    altura = (
        _safe_numeric(df["altura_carga_m"]).values
        if "altura_carga_m" in df.columns
        else np.zeros(n, dtype=float)
    )
    kgpm = (
        _safe_numeric(df["kg_per_meter"]).values
        if "kg_per_meter" in df.columns
        else np.zeros(n, dtype=float)
    )
    incl = (
        _safe_numeric(df["Incl"]).values
        if "Incl" in df.columns
        else np.zeros(n, dtype=float)
    )
    az = (
        _safe_numeric(df["Az"]).values
        if "Az" in df.columns
        else np.zeros(n, dtype=float)
    )
    diam_inch = diam / 25.4

    if "dureza" in df.columns:
        dureza_raw = df["dureza"]
        dureza_idx = (
            pd.to_numeric(df["indice_dureza"], errors="coerce")
            if "indice_dureza" in df.columns
            else pd.Series([np.nan] * n)
        )
        dureza_strings = np.array([
            "Dureza: " + ("" if pd.isna(d) else str(d)) +
            (" (idx " + f"{float(idx):.1f})" if pd.notna(idx) else "")
            for d, idx in zip(dureza_raw, dureza_idx)
        ], dtype=object)
    else:
        dureza_strings = np.array([""] * n, dtype=object)

    if "tasa_penetracion" in df.columns:
        tasa = pd.to_numeric(df["tasa_penetracion"], errors="coerce")
        tasa_strings = np.array([
            "Tasa perf.: " + (f"{float(t):.2f} m/min" if pd.notna(t) else "—")
            for t in tasa
        ], dtype=object)
    else:
        tasa_strings = np.array([""] * n, dtype=object)

    return np.column_stack([
        label, expl, kilos, diam, length, taco, altura, kgpm,
        incl, az, diam_inch, dureza_strings, tasa_strings,
    ])


# ---------------------------------------------------------------------------
# 3D figure
# ---------------------------------------------------------------------------

def _plot_discrete_traces(
    fig: go.Figure,
    df: pd.DataFrame,
    category_col: str,
    unique_vals: list[str],
    label_prefix: str,
) -> None:
    """Add per-category discrete 3D traces to an existing figure."""
    kg_col = find_df_column(
        df, ["Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"],
        raise_error=False,
    )
    sub_custom = _build_collar_customdata(df, kg_col)

    for idx, val_name in enumerate(unique_vals):
        mask = (df[category_col].astype(str) == val_name).values
        df_sub = df[mask]
        color = _COLOR_CYCLE[idx % len(_COLOR_CYCLE)]

        n_s = len(df_sub)
        m_x = np.empty(n_s * 3, dtype=object)
        m_y = np.empty(n_s * 3, dtype=object)
        m_z = np.empty(n_s * 3, dtype=object)

        xc = df_sub["X"].values
        yc = df_sub["Y"].values
        zc = df_sub["Z_collar"].values
        xt = df_sub["X_toe"].values
        yt = df_sub["Y_toe"].values
        zt = df_sub["Z_toe"].values

        for i in range(n_s):
            j = i * 3
            m_x[j] = xc[i]
            m_x[j + 1] = xt[i]
            m_x[j + 2] = None
            m_y[j] = yc[i]
            m_y[j + 1] = yt[i]
            m_y[j + 2] = None
            m_z[j] = zc[i]
            m_z[j + 1] = zt[i]
            m_z[j + 2] = None

        if sub_custom.shape[0] == len(df) and len(df) > 0:
            line_custom = np.repeat(sub_custom[mask], 3, axis=0)
            collar_custom = sub_custom[mask]
        else:
            line_custom = np.empty((0, 13))
            collar_custom = np.empty((0, 13))

        fig.add_trace(go.Scatter3d(
            x=m_x, y=m_y, z=m_z,
            mode="lines",
            line=dict(color=color, width=2),
            name=f"Trayectorias {val_name}",
            customdata=line_custom,
            hovertemplate=_COLLAR_HOVERTEMPLATE,
            showlegend=False,
        ))

        fig.add_trace(go.Scatter3d(
            x=df_sub["X"].values,
            y=df_sub["Y"].values,
            z=df_sub["Z_collar"].values,
            mode="markers",
            marker=dict(size=4, color=color),
            name=f"{label_prefix}: {val_name}",
            customdata=collar_custom,
            hovertemplate=_COLLAR_HOVERTEMPLATE,
        ))


def build_line_arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the x/y/z line arrays for collar-toe segments."""
    n = len(df)
    if n == 0:
        empty = np.empty(0, dtype=object)
        return empty, empty, empty

    x_lines = np.empty(n * 3, dtype=object)
    y_lines = np.empty(n * 3, dtype=object)
    z_lines = np.empty(n * 3, dtype=object)

    xc = df["X"].values
    yc = df["Y"].values
    zc = df["Z_collar"].values
    xt = df["X_toe"].values
    yt = df["Y_toe"].values
    zt = df["Z_toe"].values

    for i in range(n):
        j = i * 3
        x_lines[j] = xc[i]
        x_lines[j + 1] = xt[i]
        x_lines[j + 2] = None
        y_lines[j] = yc[i]
        y_lines[j + 1] = yt[i]
        y_lines[j + 2] = None
        z_lines[j] = zc[i]
        z_lines[j + 1] = zt[i]
        z_lines[j + 2] = None

    return x_lines, y_lines, z_lines


def build_three_d_figure(
    df: pd.DataFrame,
    x_lines,
    y_lines,
    z_lines,
    color_by: str,
    sel_colorscale: str = "Inferno",
    *,
    design_mesh_trace=None,
    topo_mesh_trace=None,
    energy_surface_trace=None,
    ref_lines_z_value: float | None = None,
) -> go.Figure:
    """Build the 3D blast-hole visualization figure.

    Pure: no Streamlit calls, no session_state access.
    """
    fig = go.Figure()

    z_ref = ref_lines_z_value if ref_lines_z_value is not None else float(df["Z_collar"].max()) + 5
    add_ref_lines_3d(fig, z_value=z_ref)

    malla_col = find_df_column(df, ["Nombre_Malla_Original"], raise_error=False)
    poligono_col = find_df_column(df, ["holes_polygon"], raise_error=False)
    fase_col = find_df_column(df, ["Nombre_Fase", "Fase"], raise_error=False)
    banco_col = find_df_column(df, ["Banco_Original", "Nombre_Banco", "Banco"], raise_error=False)

    if design_mesh_trace is not None:
        fig.add_trace(design_mesh_trace)
    if topo_mesh_trace is not None:
        fig.add_trace(topo_mesh_trace)
    if energy_surface_trace is not None:
        fig.add_trace(energy_surface_trace)

    if color_by == "Mallas de Tronadura (Grid)" and malla_col:
        unique_vals = sorted(df[malla_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, malla_col, unique_vals, "Malla")
    elif color_by == "Polígonos Tronados" and poligono_col:
        unique_vals = sorted(df[poligono_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, poligono_col, unique_vals, "Polígono")
    elif color_by == "Fase" and fase_col:
        unique_vals = sorted(df[fase_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, fase_col, unique_vals, "Fase")
    elif color_by == "Banco" and banco_col:
        unique_vals = sorted(df[banco_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, banco_col, unique_vals, "Banco")
    else:
        kg_col = find_df_column(
            df, ["Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"],
            raise_error=False,
        )
        trajectory_custom = _build_collar_customdata(df, kg_col)
        if trajectory_custom.shape[0] == len(df) and len(df) > 0:
            trajectory_custom_repeat = np.repeat(trajectory_custom, 3, axis=0)
        else:
            trajectory_custom_repeat = trajectory_custom

        fig.add_trace(go.Scatter3d(
            x=x_lines, y=y_lines, z=z_lines,
            mode="lines",
            line=dict(color="rgba(150,150,150,0.5)", width=2),
            name="Trayectorias",
            customdata=trajectory_custom_repeat,
            hovertemplate=_COLLAR_HOVERTEMPLATE,
            showlegend=True,
        ))

        if color_by == "Carga Explosiva (Kg)" and kg_col:
            colors = df[kg_col].values.astype(float)
            title = "kg"
        elif color_by == "Diámetro (mm)" and "Diam_mm" in df.columns:
            colors = df["Diam_mm"].values.astype(float)
            title = "mm"
        elif color_by == "Dureza" and "dureza" in df.columns:
            colors = df["dureza"].map(_DUREZA_MAP).fillna(0).astype(float).values
            title = "Dureza (1-4)"
        elif color_by == "Índice de Dureza" and "indice_dureza" in df.columns:
            colors = pd.to_numeric(df["indice_dureza"], errors="coerce").fillna(0).astype(float).values
            title = "Índice (0-100)"
        elif color_by == "Tasa de Penetración" and "tasa_penetracion" in df.columns:
            colors = pd.to_numeric(df["tasa_penetracion"], errors="coerce").fillna(0).astype(float).values
            title = "m/min"
        elif color_by == "Profundidad (m)":
            colors = df["Len"].values
            title = "m (Largo)"
        elif color_by == "Inclinación (°)":
            colors = df["Incl"].values
            title = "Grados (°)"
        else:
            colors = df["Z_collar"].values
            title = "Collar Z"

        marker = dict(
            size=4,
            color=colors,
            colorscale=sel_colorscale,
            showscale=True,
            colorbar=dict(title=title, x=1.0, len=0.6),
        )

        fig.add_trace(go.Scatter3d(
            x=df["X"].values,
            y=df["Y"].values,
            z=df["Z_collar"].values,
            mode="markers",
            marker=marker,
            name="Collars",
            customdata=_build_collar_customdata(df, kg_col),
            hovertemplate=_COLLAR_HOVERTEMPLATE,
        ))

    fig.update_layout(
        scene=dict(
            aspectmode="data",
            xaxis_title="Este (m)",
            yaxis_title="Norte (m)",
            zaxis_title="Elevación (m)",
        ),
        height=700,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )

    return fig


# ---------------------------------------------------------------------------
# Energy grid / surface
# ---------------------------------------------------------------------------

def build_energy_grid(
    df: pd.DataFrame,
    kg_col: str | None,
    grid_nx: int,
    grid_ny: int,
    grid_nz: int,
    search_radius: float,
) -> dict:
    """Compute the IDW energy grid from collar-toe segments.

    Returns a dict with ``X, Y, Z, Energy_kg_m2`` arrays plus helper
    fields ``xs, ys, Z_collar_mean, E_xy, E_max`` needed by the surface
    trace builder.
    """
    grid_nx = max(2, min(50, int(grid_nx)))
    grid_ny = max(2, min(50, int(grid_ny)))
    grid_nz = max(2, min(15, int(grid_nz)))
    if search_radius <= 0:
        search_radius = 30.0

    C = df[["X", "Y", "Z_collar"]].values.astype(float)
    T = df[["X_toe", "Y_toe", "Z_toe"]].values.astype(float)
    V = T - C
    V_len_sq = np.sum(V**2, axis=1)
    V_len_sq[V_len_sq == 0] = 1e-6
    Q = df[kg_col].fillna(0).values if kg_col else np.ones(len(df))

    x_min, x_max = float(C[:, 0].min()), float(C[:, 0].max())
    y_min, y_max = float(C[:, 1].min()), float(C[:, 1].max())
    z_min, z_max = float(T[:, 2].min()), float(C[:, 2].max())

    xs = np.linspace(x_min, x_max, grid_nx)
    ys = np.linspace(y_min, y_max, grid_ny)
    zs = np.linspace(z_min, z_max, grid_nz)
    grid_x, grid_y, grid_z = np.meshgrid(xs, ys, zs)
    points = np.vstack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()]).T

    energies = np.empty(len(points), dtype=float)
    for i, gp in enumerate(points):
        W = gp - C
        t = np.sum(W * V, axis=1) / V_len_sq
        t_c = np.clip(t, 0.0, 1.0)
        closest = C + t_c[:, np.newaxis] * V
        d_sq = np.sum((gp - closest) ** 2, axis=1)
        d_sq = np.maximum(d_sq, 1e-4)
        weights = np.exp(-d_sq / (2.0 * search_radius ** 2))
        energies[i] = float(np.sum(Q * weights))

    Z_collar_mean = float(df["Z_collar"].mean())
    E_xy = energies.reshape(grid_nx, grid_ny, grid_nz).sum(axis=2)
    E_max = float(E_xy.max()) if E_xy.max() > 0 else 1.0

    return {
        "X": points[:, 0].copy(),
        "Y": points[:, 1].copy(),
        "Z": points[:, 2].copy(),
        "Energy_kg_m2": energies.copy(),
        "xs": xs,
        "ys": ys,
        "Z_collar_mean": Z_collar_mean,
        "E_xy": E_xy,
        "E_max": E_max,
    }


def build_energy_surface_trace(energy_grid: dict) -> go.Surface:
    """Build the Surface trace for the IDW energy grid."""
    xs = energy_grid["xs"]
    ys = energy_grid["ys"]
    E_xy = energy_grid["E_xy"]
    Z_collar_mean = energy_grid["Z_collar_mean"]
    E_max = energy_grid["E_max"]

    return go.Surface(
        x=xs, y=ys, z=np.full_like(E_xy, Z_collar_mean),
        surfacecolor=E_xy,
        colorscale="YlOrRd",
        cmin=0,
        cmax=E_max,
        showscale=True,
        opacity=0.55,
        name="Heatmap densidad energía (kg/m²)",
        colorbar=dict(
            title=dict(
                text="Densidad Energía<br>integrada en Z<br>(kg/m²)",
                font=dict(size=11),
                side="right",
            ),
            x=1.12,
            len=0.6,
            thickness=18,
        ),
        hovertemplate=(
            "X: %{x:.1f} m<br>"
            "Y: %{y:.1f} m<br>"
            "Densidad integrada: %{surfacecolor:.2f} kg/m²<br>"
            f"Plano Z={Z_collar_mean:.0f} m<br>"
            "<extra></extra>"
        ),
        showlegend=True,
    )


# ---------------------------------------------------------------------------
# Pasadura figure
# ---------------------------------------------------------------------------

def compute_pasadura_series(df: pd.DataFrame) -> pd.Series:
    """Return the sub-drilling (pasadura) series for a blast dataframe."""
    return (df["Z_collar"] - DEFAULTS.blast_default_bench_height) - df["Z_toe"]


def build_pasadura_figure(
    pasadura_series: pd.Series,
    p_min: float,
    p_max: float,
) -> go.Figure:
    """Build the histogram of sub-drilling values."""
    fig = go.Figure(go.Histogram(
        x=pasadura_series.values,
        nbinsx=20,
        marker_color="mediumpurple",
        opacity=0.75,
        name="Pasadura real",
    ))
    fig.add_vline(x=p_min, line_dash="dash", line_color="green", annotation_text=f"Óptimo Mín ({p_min}m)")
    fig.add_vline(x=p_max, line_dash="dash", line_color="green", annotation_text=f"Óptimo Máx ({p_max}m)")
    fig.add_vline(x=0.0, line_dash="solid", line_color="red", annotation_text="Nivel Piso (0.0m)")
    fig.update_layout(
        title="Distribución de Pasaduras (m)",
        xaxis_title="Pasadura (m)",
        yaxis_title="Cantidad de Pozos",
        height=350,
        margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Sector deviation figure
# ---------------------------------------------------------------------------

def _sector_fill_color(classification: str) -> str:
    if classification == "overbreak":
        return "rgba(220, 50, 50, 0.45)"
    if classification == "underbreak":
        return "rgba(255, 200, 50, 0.45)"
    if classification == "compliant":
        return "rgba(80, 200, 120, 0.35)"
    return "rgba(180, 80, 180, 0.45)"


def build_sector_deviation_figure(
    sectors: list,
    design_d: np.ndarray,
    design_e: np.ndarray,
    topo_d: np.ndarray,
    topo_e: np.ndarray,
) -> go.Figure:
    """Build the sector deviation filled-area figure."""
    fig = go.Figure()
    for s in sectors:
        mask = (topo_d >= s.d_start) & (topo_d <= s.d_end)
        if not np.any(mask):
            continue
        d_clip = topo_d[mask]
        e_design_clip = np.interp(d_clip, design_d, design_e)
        e_topo_clip = topo_e[mask]

        fig.add_trace(go.Scatter(
            x=np.concatenate([d_clip, d_clip[::-1]]),
            y=np.concatenate([e_design_clip, e_topo_clip[::-1]]),
            fill="toself",
            fillcolor=_sector_fill_color(s.classification),
            line=dict(width=0),
            name=f"Sector {s.sector_id} ({s.classification})",
            hoveron="fills",
            hovertemplate=(
                f"<b>Sector {s.sector_id}</b><br>"
                f"Clase: {s.classification}<br>"
                f"Rango: [{s.d_start:.1f}, {s.d_end:.1f}] m<br>"
                f"Δh medio: {s.mean_delta_h:+.2f} m<br>"
                f"Δh máx: {s.max_delta_h:+.2f} m<br>"
                f"Área sobre: {s.area_above_m2:.2f} m²<br>"
                f"Área deuda: {s.area_below_m2:.2f} m²<br>"
                f"<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.add_trace(go.Scatter(
        x=design_d, y=design_e, mode="lines", name="Diseño",
        line=dict(color="royalblue", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=topo_d, y=topo_e, mode="lines", name="Topografía",
        line=dict(color="forestgreen", width=2),
    ))

    fig.update_layout(
        title=(
            "Sectores con desviaciones clasificadas "
            "(rojo=sobre-excavación, amarillo=deuda, verde=cumplimiento)"
        ),
        xaxis_title="Distancia (m)",
        yaxis_title="Elevación (m)",
        height=450,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    return fig


def build_sector_table_rows(sectors: list) -> list[dict]:
    """Return the table rows rendered below the sector deviation figure."""
    rows = []
    for s in sectors:
        rows.append({
            "Sector": s.sector_id,
            "Rango (m)": f"[{s.d_start:.1f}, {s.d_end:.1f}]",
            "Clase": s.classification,
            "Δh medio (m)": f"{s.mean_delta_h:+.2f}",
            "Δh máx (m)": f"{s.max_delta_h:+.2f}",
            "Área sobre (m²)": f"{s.area_above_m2:.2f}",
            "Área deuda (m²)": f"{s.area_below_m2:.2f}",
        })
    return rows


# ---------------------------------------------------------------------------
# Color / option helpers
# ---------------------------------------------------------------------------

def build_color_options(df: pd.DataFrame) -> list[str]:
    """Build the list of 3D color-by options matching the original UI."""
    options = []
    kg_col = find_df_column(
        df, ["Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"],
        raise_error=False,
    )
    malla_col = find_df_column(df, ["Nombre_Malla_Original"], raise_error=False)
    poligono_col = find_df_column(df, ["holes_polygon"], raise_error=False)
    fase_col = find_df_column(df, ["Nombre_Fase", "Fase"], raise_error=False)
    banco_col = find_df_column(df, ["Banco_Original", "Nombre_Banco", "Banco"], raise_error=False)
    diam_col = find_df_column(df, ["Diam_mm", "Diametro", "Diameter"], raise_error=False)

    if kg_col:
        options.append("Carga Explosiva (Kg)")
    if malla_col:
        options.append("Mallas de Tronadura (Grid)")
    if poligono_col:
        options.append("Polígonos Tronados")
    if fase_col:
        options.append("Fase")
    if banco_col:
        options.append("Banco")
    if diam_col:
        options.append("Diámetro (mm)")
    if "dureza" in df.columns:
        options.append("Dureza")
    if "indice_dureza" in df.columns:
        options.append("Índice de Dureza")
    if "tasa_penetracion" in df.columns:
        options.append("Tasa de Penetración")
    options.extend([
        "Profundidad (m)", "Inclinación (°)", "Elevación Collar (m)",
    ])
    return options


def get_available_colorscales() -> list[str]:
    return _ALL_COLORSCALES.copy()


def is_discrete_color_option(color_by: str) -> bool:
    return color_by in {
        "Mallas de Tronadura (Grid)",
        "Polígonos Tronados",
        "Fase",
        "Banco",
    }


def get_sector_face_angle_note() -> str:
    return _SECTOR_FACE_ANGLE_NOTE
