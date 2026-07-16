"""Pure blast-hole projection and trace builders for the Profiles tab.

No Streamlit calls. Caching is explicit via the ``cache`` parameter so
callers can retain the original session-state caching behavior.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.geom_utils import find_df_column


def get_or_project_pozos(blast_df, section, tolerance: float, cache=None):
    """Project blast holes onto a section, with optional caller-supplied cache."""
    if cache is None:
        cache = {}
    key = (id(blast_df), tuple(section.origin), section.azimuth, section.length, tolerance)
    if key not in cache:
        cache[key] = proyectar_pozos_en_seccion(
            blast_df,
            origin=section.origin,
            azimuth=section.azimuth,
            length=section.length,
            tolerance=tolerance,
        )
    return cache[key]


def add_blast_holes(fig, section, tolerance: float, blast_df, cache=None) -> None:
    """Add blast-hole traces to ``fig`` from a caller-supplied DataFrame."""
    if blast_df is None or blast_df.empty:
        return

    projected = get_or_project_pozos(blast_df, section, tolerance, cache=cache)

    if projected.empty:
        return

    kg_col = find_df_column(projected, ['Kilos_Cargados_real', 'Kilos_Cargados'], raise_error=False)
    malla_col = find_df_column(projected, ['holes_polygon', 'Nombre_Malla_Original'], raise_error=False)
    label_col = find_df_column(projected, ['label_pozo'], raise_error=False)

    x_holes, y_holes = [], []
    colors = []

    has_toe = "dist_along_toe" in projected.columns
    has_kg = kg_col is not None
    for row in projected.itertuples(index=False):
        d_c = row.dist_along
        d_t = row.dist_along_toe if has_toe else d_c
        z_c = row.Z_collar
        z_t = row.Z_toe

        x_holes.extend([d_c, d_t, None])
        y_holes.extend([z_c, z_t, None])

        if has_kg:
            kg_val = getattr(row, kg_col, None)
            if pd.notna(kg_val):
                colors.append(kg_val)
                continue
        colors.append(0)

    fig.add_trace(go.Scatter(
        x=x_holes, y=y_holes,
        mode='lines',
        line=dict(color='rgba(255,100,0,0.5)', width=1.5),
        name=f'Pozos ({len(projected)})',
        hoverinfo='skip',
        showlegend=False,
    ))

    collar_x = projected['dist_along'].values
    collar_z = projected['Z_collar'].values

    if kg_col and len(set(colors)) > 1:
        marker = dict(
            size=5,
            color=colors,
            colorscale='Hot',
            showscale=True,
            colorbar=dict(title="kg", x=1.0, len=0.4),
        )
    else:
        marker = dict(size=5, color='darkorange')

    n = len(projected)
    empty = pd.Series([''] * n, index=projected.index)
    label_s = projected[label_col].fillna('').astype(str) if label_col else empty
    malla_s = projected[malla_col].fillna('').astype(str) if malla_col else empty
    collar_line = (
        "Collar: " + projected['Z_collar'].round().astype(int).astype(str)
        + "m | Toe: " + projected['Z_toe'].round().astype(int).astype(str) + "m"
    )
    length_line = "Largo: " + projected['Len'].round(1).astype(str) + "m"
    if kg_col:
        kg_vals = pd.to_numeric(projected[kg_col], errors='coerce')
        kg_suffix = " | " + kg_vals.round().astype('Int64').astype(str) + "kg"
        kg_suffix = kg_suffix.where(pd.notna(kg_vals), "")
        length_line = length_line + kg_suffix
    hover_labels = label_s.str.cat([malla_s, collar_line, length_line], sep="<br>")

    fig.add_trace(go.Scatter(
        x=collar_x, y=collar_z,
        mode='markers',
        marker=marker,
        name='Collars',
        text=hover_labels,
        hoverinfo='text',
        showlegend=False,
    ))
