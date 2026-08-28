"""
Pure helpers for the compliance plan view in the dashboard tab.

The plan view renders the real topographic STL surface as a ``go.Mesh3d``
in neutral gray (flatshaded, lit from the side so slopes read in the
top-down camera) and overlays one ``go.Scatter3d`` line per section,
colored green when the section complies and red otherwise.

Everything in this module is a pure function of its inputs so it stays
unit-testable without a running Streamlit server.
"""
import numpy as np
import plotly.graph_objects as go

from core import decimate_mesh
from core.section_cutter import azimuth_to_direction

PLAN_TITLE = "Plano de Cumplimiento — STL Topográfico Real + Cumplimiento por Perfil"
MESH_NAME = "STL Topográfico Real"
COMPLIANCE_THRESHOLD = 70.0
COLOR_CUMPLE = "#2E7D32"
COLOR_NO_CUMPLE = "#C62828"

# Maximum detail rendered in the plan view. Full topo is used directly up to
# PLAN_FULL_FACE_LIMIT; beyond that a high-detail plan mesh decimated to
# PLAN_TARGET_FACES is built once and reused across reruns.
PLAN_FULL_FACE_LIMIT = 500_000
PLAN_TARGET_FACES = 250_000

# Neutral gray visible on the dark theme; elevation is not used for coloring.
SURFACE_GRAY = "#9A9A9A"

PLAN_MESH_STATE_KEY = "plan_mesh_topo"
PLAN_MESH_TOKEN_KEY = "plan_mesh_topo_token"


def compute_section_status(results) -> dict:
    """Compute per-section compliance status from comparison results.

    Only MATCH rows participate. Prefers the canonical ``section_score``
    when every MATCH row of a section carries a finite numeric
    ``section_score`` and they all agree; otherwise falls back to the mean
    of the finite ``bench_score`` values. Sections with no finite
    ``bench_score`` are omitted entirely — a missing score must never be
    rendered as a red (NO CUMPLE) profile. The resulting score is rounded
    to one decimal and a section is compliant when score >= 70.
    """
    rows_by_section: dict = {}
    for r in results:
        if r.get('type') != 'MATCH':
            continue
        rows_by_section.setdefault(r.get('section', ''), []).append(r)

    status: dict = {}
    for section, rows in rows_by_section.items():
        canonical = [r['section_score'] for r in rows
                     if _is_finite_number(r.get('section_score'))]
        if len(canonical) == len(rows) and all(
                abs(c - canonical[0]) <= 1e-9 for c in canonical):
            raw = float(canonical[0])
        else:
            scores = [float(r['bench_score']) for r in rows
                      if _is_finite_number(r.get('bench_score'))]
            if not scores:
                continue
            raw = sum(scores) / len(scores)
        score = round(raw, 1)
        status[section] = {'score': score, 'cumple': score >= COMPLIANCE_THRESHOLD}
    return status


def select_plan_mesh(mesh_topo, decimated_mesh_topo, plan_mesh_topo=None,
                     max_full_faces=None):
    """Pick the mesh to render in the plan view.

    Uses the full-resolution topography when it is renderable and small
    enough (default ``PLAN_FULL_FACE_LIMIT``); when it exceeds the limit it
    prefers the high-detail ``plan_mesh_topo`` and only then falls back to
    the decimated mesh. Never uses the design mesh. Returns None when no
    renderable topo exists — empty, NaN/Inf or otherwise invalid meshes are
    never returned.
    """
    max_full_faces = PLAN_FULL_FACE_LIMIT if max_full_faces is None else max_full_faces
    if not _is_renderable_mesh(mesh_topo):
        return None
    if len(mesh_topo.faces) <= max_full_faces:
        return mesh_topo
    if _is_renderable_mesh(plan_mesh_topo):
        return plan_mesh_topo
    if _is_renderable_mesh(decimated_mesh_topo):
        return decimated_mesh_topo
    return None


def plan_high_detail_needed(mesh_topo, session_state) -> bool:
    """Whether a lazily built high-detail plan mesh is required.

    True only when the full topo exceeds ``PLAN_FULL_FACE_LIMIT`` and no
    renderable high-detail mesh is cached for the current source token.
    """
    if not _is_renderable_mesh(mesh_topo):
        return False
    if len(mesh_topo.faces) <= PLAN_FULL_FACE_LIMIT:
        return False
    cached = session_state.get(PLAN_MESH_STATE_KEY)
    return not (
        _is_renderable_mesh(cached)
        and session_state.get(PLAN_MESH_TOKEN_KEY) == _mesh_source_token(mesh_topo)
    )


def ensure_plan_mesh_topo(mesh_topo, session_state, *, full_face_limit=None,
                          target_faces=None):
    """Return the highest-detail renderable topo mesh for the plan view.

    Uses the full topo when it is renderable and at or below
    ``full_face_limit``. When the full topo is too large it builds (once) a
    high-detail ``plan_mesh_topo`` decimated to ``target_faces`` through
    the public ``core.decimate_mesh`` and caches it in ``session_state``
    next to a source token; subsequent reruns reuse it while the token
    matches. Returns None when the high-detail mesh cannot be built or is
    not renderable — the caller then falls back to the existing decimated
    topo. Never returns the design mesh.
    """
    full_face_limit = PLAN_FULL_FACE_LIMIT if full_face_limit is None else full_face_limit
    target_faces = PLAN_TARGET_FACES if target_faces is None else target_faces
    if not _is_renderable_mesh(mesh_topo):
        return None
    if len(mesh_topo.faces) <= full_face_limit:
        return mesh_topo
    token = _mesh_source_token(mesh_topo)
    cached = session_state.get(PLAN_MESH_STATE_KEY)
    if (_is_renderable_mesh(cached)
            and session_state.get(PLAN_MESH_TOKEN_KEY) == token):
        return cached
    plan = None
    try:
        plan = decimate_mesh(mesh_topo, target_faces=target_faces)
    except Exception:
        plan = None
    if not _is_renderable_mesh(plan):
        return None
    session_state[PLAN_MESH_STATE_KEY] = plan
    session_state[PLAN_MESH_TOKEN_KEY] = token
    return plan


def build_plan_view_figure(mesh_topo, sections, section_status) -> go.Figure:
    """Build the pure Plotly figure for the compliance plan view.

    Parameters
    ----------
    mesh_topo:        Already-selected real topo mesh (full or decimated),
                      possibly None. When None or not renderable (empty,
                      NaN/Inf vertices, invalid faces) no surface is drawn
                      and the section lines are placed at z=0.
    sections:         Iterable of SectionLine objects.
    section_status:   Mapping section name -> {'score', 'cumple'}.
    """
    fig = go.Figure()
    z_overlay = 0.0
    if _is_renderable_mesh(mesh_topo):
        bounds = _mesh_bounds(mesh_topo)
        xspan = bounds['x'][1] - bounds['x'][0]
        yspan = bounds['y'][1] - bounds['y'][0]
        zspan = bounds['z'][1] - bounds['z'][0]
        z_overlay = bounds['z'][1] + max(xspan, yspan, zspan) * 0.05 + 1.0
        _add_surface_trace(fig, mesh_topo)

    for sec in sections:
        status = section_status.get(sec.name)
        if status is None:
            continue
        _add_section_trace(fig, sec, status, z_overlay)

    _add_legend_traces(fig)
    _update_layout(fig)
    return fig


# ---------------------------------------------------------------------------
# Private builders
# ---------------------------------------------------------------------------

def _is_finite_number(value) -> bool:
    """True only for real, finite numbers (bool excluded)."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return bool(np.isfinite(float(value)))


def _is_renderable_mesh(mesh) -> bool:
    """Whether a mesh holds geometry safe to render as a Mesh3d surface.

    Requires non-empty triangular faces with all vertex indices in range
    and a non-empty set of finite vertices. Invalid meshes (empty, or
    carrying NaN/Inf vertices or out-of-range face indices) must never
    reach the Mesh3d builder.
    """
    if mesh is None:
        return False
    try:
        verts = np.asarray(mesh.vertices)
        faces = np.asarray(mesh.faces)
    except (TypeError, ValueError):
        return False
    if verts.ndim != 2 or verts.shape[0] == 0 or verts.shape[1] != 3:
        return False
    if faces.ndim != 2 or faces.shape[0] == 0 or faces.shape[1] != 3:
        return False
    if not np.isfinite(verts).all():
        return False
    if faces.min() < 0 or faces.max() >= verts.shape[0]:
        return False
    return True


def _mesh_source_token(mesh) -> tuple:
    """Hashable token identifying the current topo source object.

    Changes whenever a different mesh object is loaded, so a stale cached
    high-detail mesh is rebuilt after a new upload or a hot reload.
    """
    vertices = getattr(mesh, 'vertices', None)
    faces = getattr(mesh, 'faces', None)
    return (
        id(mesh),
        len(vertices) if vertices is not None else 0,
        len(faces) if faces is not None else 0,
    )


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
    """Add the real topo surface as a neutral gray Mesh3d.

    Elevation is not used for coloring: a single flat gray keeps the
    surface legible over the dark theme while flatshading plus a lateral
    light reveals faces and slopes in the top-down camera.
    """
    verts = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces)
    fig.add_trace(go.Mesh3d(
        x=verts[:, 0],
        y=verts[:, 1],
        z=verts[:, 2],
        i=faces[:, 0],
        j=faces[:, 1],
        k=faces[:, 2],
        color=SURFACE_GRAY,
        opacity=1.0,
        flatshading=True,
        showscale=False,
        name=MESH_NAME,
        showlegend=False,
        hovertemplate=(
            "Este: %{x:.1f} m<br>Norte: %{y:.1f} m<br>"
            "Elevación: %{z:.1f} m<extra></extra>"
        ),
        lighting=dict(
            ambient=0.35, diffuse=0.95, specular=0.05,
            roughness=0.9, fresnel=0.1,
        ),
        lightposition=dict(x=-9.0e4, y=9.0e4, z=4.0e4),
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
    """Add two legend traces so the Cumple / No cumple legend renders.

    Plotly drops fully empty traces (``x=[], y=[], z=[]``) from the legend,
    so each trace carries a single ``None`` point: it counts as data for the
    legend while drawing no geometry and leaving the scene bounds untouched.
    A thin lines style keeps the legend swatch visible.
    """
    for name, color in (('Cumple', COLOR_CUMPLE),
                        ('No cumple', COLOR_NO_CUMPLE)):
        fig.add_trace(go.Scatter3d(
            x=[None], y=[None], z=[None], mode='lines',
            line=dict(color=color, width=10),
            name=name, showlegend=True, hoverinfo='none',
        ))


def _update_layout(fig: go.Figure) -> None:
    """Configure a top-down orthographic plan view with Este/Norte axes.

    Camera values are normalized scene coordinates, not geographic ones:
    the center is the scene origin and the eye sits directly above it, so
    the framing is independent of where the mesh is located in the world.
    """
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
                center=dict(x=0.0, y=0.0, z=0.0),
                eye=dict(x=0.0, y=0.0, z=2.5),
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
