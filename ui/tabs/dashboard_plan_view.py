"""
Pure helpers for the compliance plan view in the dashboard tab.

The plan view renders the real topographic STL surface as a ``go.Mesh3d``
colored by elevation and overlays one ``go.Scatter3d`` line per section,
colored green when the section complies and red otherwise.

Everything in this module is a pure function of its inputs so it stays
unit-testable without a running Streamlit server.
"""
import numpy as np
import plotly.graph_objects as go

from core.section_cutter import azimuth_to_direction

PLAN_TITLE = "Plano de Cumplimiento — STL Topográfico Real + Cumplimiento por Perfil"
MESH_NAME = "STL Topográfico Real"
COMPLIANCE_THRESHOLD = 70.0
COLOR_CUMPLE = "#2E7D32"
COLOR_NO_CUMPLE = "#C62828"

# Terrain-like colorscale that stays readable over a dark background:
# low ground in deep brown, mid slopes in olive, crests in pale sand.
TERRAIN_COLORSCALE = [
    [0.0, "#2E2A25"],
    [0.25, "#4E4A3F"],
    [0.5, "#558B2F"],
    [0.75, "#F9A825"],
    [1.0, "#FFF8E1"],
]


def compute_section_status(results) -> dict:
    """Compute per-section compliance status from comparison results.

    Only MATCH rows participate. Prefers the canonical ``section_score``
    when every MATCH row of a section agrees on it; otherwise falls back
    to the mean of ``bench_score``. The resulting score is rounded to one
    decimal and a section is compliant when score >= 70.
    """
    rows_by_section: dict = {}
    for r in results:
        if r.get('type') != 'MATCH':
            continue
        rows_by_section.setdefault(r.get('section', ''), []).append(r)

    status: dict = {}
    for section, rows in rows_by_section.items():
        canonical = [r['section_score'] for r in rows
                     if isinstance(r.get('section_score'), (int, float))]
        if canonical and all(abs(c - canonical[0]) <= 1e-9 for c in canonical):
            raw = float(canonical[0])
        else:
            scores = [float(r.get('bench_score', 0.0)) for r in rows]
            raw = sum(scores) / len(scores) if scores else 0.0
        score = round(raw, 1)
        status[section] = {'score': score, 'cumple': score >= COMPLIANCE_THRESHOLD}
    return status


def select_plan_mesh(mesh_topo, decimated_mesh_topo, max_full_faces: int = 100_000):
    """Pick the mesh to render in the plan view.

    Uses the full-resolution topography when it is small enough; when it
    exceeds ``max_full_faces`` falls back to the decimated mesh. Never
    uses the design mesh. Returns None when no renderable topo exists.
    """
    if mesh_topo is None:
        return None
    if len(mesh_topo.faces) <= max_full_faces:
        return mesh_topo
    if decimated_mesh_topo is not None:
        return decimated_mesh_topo
    return None


def build_plan_view_figure(mesh_topo, sections, section_status) -> go.Figure:
    """Build the pure Plotly figure for the compliance plan view.

    Parameters
    ----------
    mesh_topo:        Already-selected real topo mesh (full or decimated),
                      possibly None. When None no surface is drawn and the
                      section lines are placed at z=0.
    sections:         Iterable of SectionLine objects.
    section_status:   Mapping section name -> {'score', 'cumple'}.
    """
    fig = go.Figure()
    bounds = _mesh_bounds(mesh_topo)
    z_overlay = 0.0
    if mesh_topo is not None:
        xspan = bounds['x'][1] - bounds['x'][0]
        yspan = bounds['y'][1] - bounds['y'][0]
        zspan = bounds['z'][1] - bounds['z'][0]
        z_overlay = bounds['z'][1] + max(xspan, yspan, zspan) * 0.05 + 1.0
        _add_surface_trace(fig, mesh_topo)

    for sec in sections:
        status = section_status.get(sec.name, {'score': 0.0, 'cumple': False})
        _add_section_trace(fig, sec, status, z_overlay)

    _add_legend_traces(fig)
    _update_layout(fig, bounds)
    return fig


# ---------------------------------------------------------------------------
# Private builders
# ---------------------------------------------------------------------------

def _mesh_bounds(mesh) -> dict:
    """Axis-aligned bounds of a mesh as a dict of (min, max) tuples."""
    if mesh is None:
        return {'x': (0.0, 0.0), 'y': (0.0, 0.0), 'z': (0.0, 0.0)}
    verts = np.asarray(mesh.vertices, dtype=float)
    if len(verts) == 0:
        return {'x': (0.0, 0.0), 'y': (0.0, 0.0), 'z': (0.0, 0.0)}
    return {
        'x': (float(verts[:, 0].min()), float(verts[:, 0].max())),
        'y': (float(verts[:, 1].min()), float(verts[:, 1].max())),
        'z': (float(verts[:, 2].min()), float(verts[:, 2].max())),
    }


def _add_surface_trace(fig: go.Figure, mesh) -> None:
    """Add the real topo surface as a Mesh3d colored by elevation."""
    verts = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces)
    elevations = verts[:, 2]
    fig.add_trace(go.Mesh3d(
        x=verts[:, 0],
        y=verts[:, 1],
        z=verts[:, 2],
        i=faces[:, 0],
        j=faces[:, 1],
        k=faces[:, 2],
        intensity=elevations,
        colorscale=TERRAIN_COLORSCALE,
        cmin=float(elevations.min()),
        cmax=float(elevations.max()),
        opacity=1.0,
        showscale=False,
        name=MESH_NAME,
        showlegend=False,
        hovertemplate=(
            "Este: %{x:.1f} m<br>Norte: %{y:.1f} m<br>"
            "Elevación: %{z:.1f} m<extra></extra>"
        ),
        lighting=dict(
            ambient=0.6, diffuse=0.85, specular=0.15,
            roughness=0.5, fresnel=0.2,
        ),
        lightposition=dict(x=5.0e4, y=5.0e4, z=1.0e5),
    ))


def _add_section_trace(fig: go.Figure, section, status: dict, z_overlay: float) -> None:
    """Add one section line over the surface, colored by compliance."""
    color = COLOR_CUMPLE if status['cumple'] else COLOR_NO_CUMPLE
    score = status['score']
    origin = np.asarray(section.origin, dtype=float)
    direction = azimuth_to_direction(section.azimuth)
    half_len = section.length / 2.0
    p1 = origin - direction * half_len
    p2 = origin + direction * half_len

    fig.add_trace(go.Scatter3d(
        x=[p1[0], p2[0]],
        y=[p1[1], p2[1]],
        z=[z_overlay, z_overlay],
        mode='lines',
        line=dict(color=color, width=6),
        name=section.name,
        showlegend=False,
        hovertemplate=(
            f"<b>{section.name}</b><br>"
            f"Puntaje de logro: {score:.1f}/100<br>"
            f"Estado: {'CUMPLE' if status['cumple'] else 'NO CUMPLE'}<br>"
            f"Azimut: {section.azimuth:.0f}°<br>"
            f"Sector: {section.sector or 'N/A'}"
            "<extra></extra>"
        ),
    ))


def _add_legend_traces(fig: go.Figure) -> None:
    """Add two empty legend traces so the Cumple / No cumple legend reads cleanly."""
    fig.add_trace(go.Scatter3d(
        x=[], y=[], z=[], mode='markers', name='Cumple',
        marker=dict(color=COLOR_CUMPLE, size=10), showlegend=True,
    ))
    fig.add_trace(go.Scatter3d(
        x=[], y=[], z=[], mode='markers', name='No cumple',
        marker=dict(color=COLOR_NO_CUMPLE, size=10), showlegend=True,
    ))


def _update_layout(fig: go.Figure, bounds: dict) -> None:
    """Configure a top-down orthographic plan view with Este/Norte axes."""
    cx = (bounds['x'][0] + bounds['x'][1]) / 2.0
    cy = (bounds['y'][0] + bounds['y'][1]) / 2.0
    cz = (bounds['z'][0] + bounds['z'][1]) / 2.0
    span = max(
        bounds['x'][1] - bounds['x'][0],
        bounds['y'][1] - bounds['y'][0],
        bounds['z'][1] - bounds['z'][0],
        1.0,
    )
    fig.update_layout(
        title=PLAN_TITLE,
        height=700,
        scene=dict(
            aspectmode='data',
            xaxis=dict(title='Este (m)'),
            yaxis=dict(title='Norte (m)'),
            zaxis=dict(title='Elevación (m)', visible=False),
            camera=dict(
                projection=dict(type='orthographic'),
                center=dict(x=cx, y=cy, z=cz),
                eye=dict(x=cx, y=cy, z=cz + span * 2.5),
                up=dict(x=0.0, y=1.0, z=0.0),
            ),
        ),
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='center',
            x=0.5,
            font=dict(size=12),
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#E0E0E0'),
    )
