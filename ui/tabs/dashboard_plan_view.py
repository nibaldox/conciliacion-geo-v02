"""
Pure helpers for the compliance plan view in the dashboard tab.

The plan view renders the real topographic STL surface as a ``go.Mesh3d``
shaded in grayscale per face (geometric hillshade through a pure gray
colorscale so benches and slopes read in the top-down camera) and overlays
one ``go.Scatter3d`` line per section, colored green when the section
complies and red otherwise.

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

# Per-face grayscale shading. A lateral + zenithal light fixed in scene
# coordinates modulates intensity by face orientation (hillshade); a small
# normalized-elevation term separates horizontal benches without dominating.
# The result is an intensity per face mapped through a pure gray colorscale,
# so slopes read in the top-down camera while staying strictly grayscale.
LIGHT_DIRECTION = np.array([1.0, 0.6, 0.8])
LIGHT_DIRECTION = LIGHT_DIRECTION / np.linalg.norm(LIGHT_DIRECTION)
HILLSHADE_WEIGHT = 0.9
ELEVATION_WEIGHT = 0.1

SURFACE_COLORSCALE = [
    [0.0, "#686868"],
    [0.5, "#B8B8B8"],
    [1.0, "#F4F4F4"],
]

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


def build_topo_profile_map(processed_sections, profiles_topo) -> dict:
    """Map section name -> canonical topo ProfileResult, matched by name.

    ``processed_sections`` and ``profiles_topo`` are the parallel lists
    stashed by step 3 (``ui/step3_analysis.py``). Matching is by section
    name, never by position in the global ``sections`` list, so a processed
    subset in any order resolves correctly. None profiles and entries
    without a name are ignored, and the two lists may differ in length —
    entries beyond the shorter list simply produce no mapping.
    """
    mapping: dict = {}
    processed = list(processed_sections or [])
    profiles = list(profiles_topo or [])
    for idx, sec in enumerate(processed):
        name = getattr(sec, 'name', None)
        if not name:
            continue
        profile = profiles[idx] if idx < len(profiles) else None
        if profile is None:
            continue
        mapping[name] = profile
    return mapping


def drape_section_profile(section, profile, *, z_offset=0.0):
    """Convert a canonical topo profile into a vectorized 3D polyline.

    Reconstructs the 3D path exactly as the section was cut against the
    full topo mesh: ``direction = azimuth_to_direction(section.azimuth)``,
    ``x = origin[0] + distance * direction[0]``,
    ``y = origin[1] + distance * direction[1]`` and ``z = elevation``.
    The real distance range of the cut is preserved — asymmetric sections
    (``length_up``/``length_down``) and extremes clipped by the mesh edge
    keep their actual samples, never re-extended to the nominal
    half-length. Only ``z_offset`` is applied to the elevations.

    Returns ``(x, y, z)`` numpy arrays when the profile is valid, else
    None. Invalid means: arrays not 1D, of unequal length, with fewer than
    2 samples, containing NaN/Inf, or a section without a usable
    finite origin/azimuth.
    """
    if section is None or profile is None:
        return None
    try:
        distances = np.asarray(profile.distances, dtype=float)
        elevations = np.asarray(profile.elevations, dtype=float)
    except (TypeError, ValueError):
        return None
    if distances.ndim != 1 or elevations.ndim != 1:
        return None
    if distances.shape[0] != elevations.shape[0] or distances.shape[0] < 2:
        return None
    if not (np.isfinite(distances).all() and np.isfinite(elevations).all()):
        return None
    try:
        origin = np.asarray(section.origin, dtype=float)
        azimuth = float(section.azimuth)
    except (TypeError, ValueError, AttributeError):
        return None
    if origin.ndim != 1 or origin.shape[0] < 2:
        return None
    if not np.isfinite(origin[:2]).all() or not np.isfinite(azimuth):
        return None
    direction = azimuth_to_direction(azimuth)
    z = elevations + float(z_offset)
    if not np.isfinite(z).all():
        return None
    x = origin[0] + distances * direction[0]
    y = origin[1] + distances * direction[1]
    return x, y, z


def build_plan_view_figure(mesh_topo, sections, section_status,
                           profiles_by_name=None) -> go.Figure:
    """Build the pure Plotly figure for the compliance plan view.

    Parameters
    ----------
    mesh_topo:        Already-selected real topo mesh (full or decimated),
                      possibly None. When None or not renderable (empty,
                      NaN/Inf vertices, invalid faces) no surface is drawn
                      and the draped offset falls back to 0.05 m.
    sections:         Iterable of SectionLine objects.
    section_status:   Mapping section name -> {'score', 'cumple'}.
    profiles_by_name: Optional mapping section name -> ProfileResult from
                      the canonical topo cuts. When provided (even empty),
                      every section with a status is drawn only if it has a
                      valid drapeable profile; sections without one are
                      omitted so no floating line is ever shown. When None
                      the historical fallback is kept for legacy callers:
                      each section is drawn as a flat 2-point line at
                      ``z_overlay`` above the mesh.
    """
    fig = go.Figure()
    z_overlay = 0.0
    z_offset = 0.05
    if _is_renderable_mesh(mesh_topo):
        bounds = _mesh_bounds(mesh_topo)
        xspan = bounds['x'][1] - bounds['x'][0]
        yspan = bounds['y'][1] - bounds['y'][0]
        zspan = bounds['z'][1] - bounds['z'][0]
        z_overlay = bounds['z'][1] + max(xspan, yspan, zspan) * 0.05 + 1.0
        z_offset = max(zspan * 0.001, 0.05)
        _add_surface_trace(fig, mesh_topo)

    draped = profiles_by_name is not None
    for sec in sections:
        status = section_status.get(sec.name)
        if status is None:
            continue
        if draped:
            profile = (profiles_by_name or {}).get(sec.name)
            if profile is None:
                continue
            _add_draped_section_trace(fig, sec, status, profile, z_offset)
        else:
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


def _face_hillshade(vertices, faces) -> np.ndarray:
    """Per-face grayscale intensity that reveals relief in the plan view.

    Each face normal is computed as the cross product of its three
    vertices, normalized with a fallback of ``[0, 0, 1]`` for degenerate
    (zero-area) triangles so they never produce NaN. A fixed lateral +
    zenithal light in scene coordinates (``LIGHT_DIRECTION``) shades each
    face by the absolute cosine of the angle to the light — ``abs`` makes
    the shading robust to inverted winding. A subtle component based on the
    normalized centroid elevation separates horizontal benches (same
    normal) without dominating the hillshade. The result is finite and
    clipped to ``[0, 1]``.
    """
    verts = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=int)

    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]

    normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(normals, axis=1)
    degenerate = lengths < 1e-12
    unit = np.where(degenerate, 1.0, lengths)
    normals = np.where(degenerate[:, None], [0.0, 0.0, 1.0], normals / unit[:, None])

    hillshade = np.abs(normals @ LIGHT_DIRECTION)

    centroids_z = (v0[:, 2] + v1[:, 2] + v2[:, 2]) / 3.0
    zmin = float(centroids_z.min())
    zmax = float(centroids_z.max())
    zspan = zmax - zmin
    if zspan > 1e-12:
        elevation = (centroids_z - zmin) / zspan
    else:
        elevation = np.zeros_like(centroids_z)

    intensity = HILLSHADE_WEIGHT * hillshade + ELEVATION_WEIGHT * elevation
    return np.clip(intensity, 0.0, 1.0)


def _add_surface_trace(fig: go.Figure, mesh) -> None:
    """Add the real topo surface as a grayscale Mesh3d shaded per face.

    Per-face geometric hillshade (``_face_hillshade``) is mapped through a
    pure gray colorscale with cell intensity so benches and slopes are
    distinguishable in the top-down camera without leaving grayscale. No
    flat ``color`` is set, which would override the intensity.
    """
    verts = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces)
    intensity = _face_hillshade(verts, faces)
    fig.add_trace(go.Mesh3d(
        x=verts[:, 0],
        y=verts[:, 1],
        z=verts[:, 2],
        i=faces[:, 0],
        j=faces[:, 1],
        k=faces[:, 2],
        intensity=intensity,
        intensitymode='cell',
        colorscale=SURFACE_COLORSCALE,
        cmin=0.0,
        cmax=1.0,
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


def _add_draped_section_trace(fig: go.Figure, section, status: dict,
                              profile, z_offset: float) -> None:
    """Add one section as a 3D polyline draped on the real topo cut.

    Every sample of the canonical profile is used, with real elevation
    plus the small visual ``z_offset``; the line follows the topographic
    surface instead of floating at a constant overlay. Invalid profiles
    are silently skipped (no trace added) so an absent or broken cut never
    renders a floating line. Hover, color, width and legend behavior are
    identical to the legacy overlay trace.
    """
    xyz = drape_section_profile(section, profile, z_offset=z_offset)
    if xyz is None:
        return
    x, y, z = xyz
    color = COLOR_CUMPLE if status['cumple'] else COLOR_NO_CUMPLE
    score = status['score']

    fig.add_trace(go.Scatter3d(
        x=x,
        y=y,
        z=z,
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
