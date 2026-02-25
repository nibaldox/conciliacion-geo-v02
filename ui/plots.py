"""
Reusable Plotly figure builders shared across UI steps.
"""
import numpy as np
import plotly.graph_objects as go
from scipy.interpolate import griddata

from core.section_cutter import azimuth_to_direction


# ---------------------------------------------------------------------------
# Section drawing helper  (used in 3D view, contour view, plan view, tab_file)
# ---------------------------------------------------------------------------

def draw_sections_on_figure(fig: go.Figure, sections, is_3d: bool = False, zref: float = 0.0) -> None:
    """Add section lines to an existing Plotly figure.

    Parameters
    ----------
    fig:      Target figure (2D Scatter or 3D Scatter3d).
    sections: List of SectionLine objects.
    is_3d:    If True, adds Scatter3d traces; otherwise adds Scatter traces.
    zref:     Reference elevation used only for 3D traces.
    """
    for sec in sections:
        d = azimuth_to_direction(sec.azimuth)
        p1 = sec.origin - d * sec.length / 2
        p2 = sec.origin + d * sec.length / 2

        if is_3d:
            fig.add_trace(go.Scatter3d(
                x=[p1[0], p2[0]], y=[p1[1], p2[1]], z=[zref, zref],
                mode='lines+text', text=[sec.name, ""],
                line=dict(color='red', width=5),
                name=sec.name, showlegend=False,
            ))
        else:
            fig.add_trace(go.Scatter(
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


# ---------------------------------------------------------------------------
# Contour / topographic grid helper
# ---------------------------------------------------------------------------

def mesh_to_contour_data(mesh, grid_size: int = 500):
    """Interpolate mesh vertices onto a regular grid for contour plotting.

    Returns (xi, yi, xi_grid, yi_grid, zi_grid) or (None,)*5 if mesh is None.
    """
    if mesh is None:
        return None, None, None, None, None

    verts = mesh.vertices
    if len(verts) > 200_000:
        step = len(verts) // 200_000
        verts = verts[::step]

    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]
    xi = np.linspace(x.min(), x.max(), grid_size)
    yi = np.linspace(y.min(), y.max(), grid_size)
    xi_grid, yi_grid = np.meshgrid(xi, yi)
    zi_grid = griddata((x, y), z, (xi_grid, yi_grid), method='linear')
    return xi, yi, xi_grid, yi_grid, zi_grid
