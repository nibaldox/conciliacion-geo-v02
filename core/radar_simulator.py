"""Radar monitoring simulator for geotechnical applications.

Provides two main analysis modes:
1. Viewshed (compute_viewshed): Given a radar position, compute the visible area on the mesh.
2. Inverse (find_radar_locations): Given a target polygon, find optimal radar positions.

Algorithm: Line-of-sight (LOS) ray-casting using trimesh.
Coordinate system: East (X), North (Y), Elevation (Z) — standard mining.
"""

import numpy as np
import trimesh
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from shapely.geometry import Polygon, Point, MultiPoint, LineString
import logging

logger = logging.getLogger(__name__)


@dataclass
class RadarParams:
    """Operational parameters for a ground-based geotechnical radar."""
    max_range: float = 4000.0       # Maximum monitoring range (m)
    min_range: float = 30.0         # Minimum usable range (m)
    height_offset: float = 3.0      # Radar height above ground (tripod/tower, m)


@dataclass
class ViewshedResult:
    """Result of a viewshed analysis from a single radar position."""
    radar_position: np.ndarray          # 3D position [X, Y, Z]
    visible_points: np.ndarray          # Nx3 — visible surface points
    blocked_points: np.ndarray          # Mx3 — blocked surface points
    coverage_fraction: float            # Fraction of sampled points visible (0-1)
    coverage_area_m2: float             # Approximate visible area (m²) via convex hull
    coverage_polygon_2d: Optional[object] = None   # shapely Polygon (plan view)


@dataclass
class RadarCandidate:
    """A candidate radar position with its coverage score."""
    position: np.ndarray                # 3D position [X, Y, Z]
    coverage_score: float               # Fraction of target area visible (0-1)
    visible_count: int                  # Number of visible target sample points
    total_count: int                    # Total target sample points checked
    distance_to_centroid: float         # Horizontal distance to target centroid (m)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_ground_elevation(mesh: trimesh.Trimesh, xy: np.ndarray) -> Optional[float]:
    """Get mesh surface elevation at an XY position via downward ray-cast."""
    z_top = float(mesh.bounds[1][2]) + 100.0
    locs, _, _ = mesh.ray.intersects_location(
        ray_origins=[[xy[0], xy[1], z_top]],
        ray_directions=[[0.0, 0.0, -1.0]],
        multiple_hits=False,
    )
    if len(locs) == 0:
        return None
    return float(np.max(locs[:, 2]))


def _check_visibility_batch(
    mesh: trimesh.Trimesh,
    origin: np.ndarray,
    targets: np.ndarray,
    tol_fraction: float = 0.02,
    min_tol: float = 1.5,
) -> np.ndarray:
    """
    Batch visibility test from `origin` to each point in `targets`.

    A target is considered visible when the first mesh intersection along the
    ray lies within `tol` metres of the target itself (i.e. nothing blocks the
    path before reaching the surface).

    Returns
    -------
    visible : np.ndarray of bool, shape (N,)
    """
    n = len(targets)
    if n == 0:
        return np.array([], dtype=bool)

    directions = targets - origin                          # (N, 3)
    distances = np.linalg.norm(directions, axis=1)         # (N,)

    valid = distances > 0.5
    norm_dirs = np.where(
        valid[:, np.newaxis],
        directions / np.maximum(distances[:, np.newaxis], 1e-9),
        np.tile([0.0, 0.0, 1.0], (n, 1)),
    )

    origins_batch = np.tile(origin, (n, 1))

    locs, idx_ray, _ = mesh.ray.intersects_location(
        ray_origins=origins_batch,
        ray_directions=norm_dirs,
        multiple_hits=False,
    )

    # Default: visible (no blocking intersection found)
    visible = np.ones(n, dtype=bool)
    visible[~valid] = False

    if len(locs) > 0:
        # Vectorised: compute distance of each hit from origin
        hit_dists = np.linalg.norm(locs - origin, axis=1)      # (K,)

        # Per-ray minimum hit distance
        min_hit = np.full(n, np.inf)
        np.minimum.at(min_hit, idx_ray, hit_dists)

        # A ray is blocked when the first mesh hit is significantly closer than
        # the target point (i.e. something stands in between).
        tol = np.maximum(tol_fraction * distances, min_tol)
        blocked = min_hit < (distances - tol)
        visible[blocked] = False

    return visible


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_viewshed(
    mesh: trimesh.Trimesh,
    radar_xy: np.ndarray,
    params: RadarParams,
    n_samples: int = 3000,
) -> ViewshedResult:
    """
    Compute the area visible from a radar placed at `radar_xy`.

    Parameters
    ----------
    mesh      : terrain surface (trimesh.Trimesh)
    radar_xy  : [X, Y] horizontal position of the radar
    params    : RadarParams (range, height above ground)
    n_samples : number of surface points to sample for LOS testing

    Returns
    -------
    ViewshedResult
    """
    radar_xy = np.asarray(radar_xy, dtype=float)

    # Radar elevation = ground + height offset
    ground_z = _get_ground_elevation(mesh, radar_xy)
    if ground_z is None:
        ground_z = float(mesh.centroid[2])
        logger.warning("No ground elevation found at radar XY; using mesh centroid Z.")

    radar_pos = np.array([radar_xy[0], radar_xy[1], ground_z + params.height_offset])

    # Sample surface points
    surface_pts, _ = trimesh.sample.sample_surface(mesh, n_samples)

    # Filter by horizontal range
    horiz = np.linalg.norm(surface_pts[:, :2] - radar_xy, axis=1)
    in_range = (horiz >= params.min_range) & (horiz <= params.max_range)
    targets = surface_pts[in_range]

    if len(targets) == 0:
        return ViewshedResult(
            radar_position=radar_pos,
            visible_points=np.empty((0, 3)),
            blocked_points=np.empty((0, 3)),
            coverage_fraction=0.0,
            coverage_area_m2=0.0,
        )

    vis_mask = _check_visibility_batch(mesh, radar_pos, targets)
    visible_pts = targets[vis_mask]
    blocked_pts = targets[~vis_mask]

    frac = float(vis_mask.sum()) / len(targets)

    # 2D coverage polygon (convex hull of visible points in plan view)
    cov_poly = None
    cov_area = 0.0
    if len(visible_pts) >= 3:
        try:
            mp = MultiPoint(visible_pts[:, :2])
            cov_poly = mp.convex_hull
            cov_area = float(cov_poly.area)
        except Exception:
            pass

    return ViewshedResult(
        radar_position=radar_pos,
        visible_points=visible_pts,
        blocked_points=blocked_pts,
        coverage_fraction=frac,
        coverage_area_m2=cov_area,
        coverage_polygon_2d=cov_poly,
    )


def sample_polygon_on_mesh(
    mesh: trimesh.Trimesh,
    polygon_2d: Polygon,
    n_samples: int = 300,
    oversample_factor: int = 15,
) -> np.ndarray:
    """
    Sample 3D points on the mesh surface that fall inside `polygon_2d` (XY plane).

    Returns Nx3 array. Returns empty (0,3) array if polygon has no overlap with mesh.
    """
    raw_pts, _ = trimesh.sample.sample_surface(mesh, n_samples * oversample_factor)
    mask = np.array([polygon_2d.contains(Point(p[0], p[1])) for p in raw_pts])
    inside = raw_pts[mask]

    if len(inside) == 0:
        return np.empty((0, 3))
    if len(inside) > n_samples:
        idx = np.random.default_rng(42).choice(len(inside), n_samples, replace=False)
        inside = inside[idx]
    return inside


def find_radar_locations(
    mesh: trimesh.Trimesh,
    target_polygon: Polygon,
    search_polygon: Polygon,
    params: RadarParams,
    grid_spacing: float = 100.0,
    min_coverage: float = 0.25,
    n_target_samples: int = 200,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> List[RadarCandidate]:
    """
    Search for radar positions inside `search_polygon` that can monitor `target_polygon`.

    Parameters
    ----------
    mesh             : terrain surface
    target_polygon   : shapely Polygon — area to monitor (plan view, XY coords)
    search_polygon   : shapely Polygon — area where radar may be placed (XY coords)
    params           : RadarParams
    grid_spacing     : spacing between candidate positions (m) — finer = slower
    min_coverage     : minimum fraction of target visible to include a candidate (0-1)
    n_target_samples : sample points in target area for LOS testing
    progress_callback: optional callable(float 0-1) for progress updates

    Returns
    -------
    List of RadarCandidate sorted by coverage_score descending.
    """
    # Sample target 3D points
    target_pts = sample_polygon_on_mesh(mesh, target_polygon, n_target_samples)
    if len(target_pts) == 0:
        logger.warning("No mesh points found inside target polygon.")
        return []

    centroid = np.array([target_polygon.centroid.x, target_polygon.centroid.y])

    # Build candidate grid
    bds = search_polygon.bounds  # (minx, miny, maxx, maxy)
    xs = np.arange(bds[0], bds[2] + grid_spacing, grid_spacing)
    ys = np.arange(bds[1], bds[3] + grid_spacing, grid_spacing)

    candidate_xys = [
        (x, y)
        for x in xs
        for y in ys
        if search_polygon.contains(Point(x, y))
    ]

    total = max(len(candidate_xys), 1)
    results: List[RadarCandidate] = []

    for k, (x, y) in enumerate(candidate_xys):
        if progress_callback:
            progress_callback(k / total)

        ground_z = _get_ground_elevation(mesh, np.array([x, y]))
        if ground_z is None:
            continue

        radar_pos = np.array([x, y, ground_z + params.height_offset])

        # Range filter on target points
        horiz = np.linalg.norm(target_pts[:, :2] - np.array([x, y]), axis=1)
        in_range = (horiz >= params.min_range) & (horiz <= params.max_range)
        range_pts = target_pts[in_range]

        if len(range_pts) == 0:
            continue

        vis_mask = _check_visibility_batch(mesh, radar_pos, range_pts)
        # Coverage relative to ALL target points (not just in-range subset)
        coverage = float(vis_mask.sum()) / len(target_pts)

        if coverage >= min_coverage:
            dist = float(np.linalg.norm(np.array([x, y]) - centroid))
            results.append(
                RadarCandidate(
                    position=radar_pos,
                    coverage_score=coverage,
                    visible_count=int(vis_mask.sum()),
                    total_count=len(target_pts),
                    distance_to_centroid=dist,
                )
            )

    if progress_callback:
        progress_callback(1.0)

    results.sort(key=lambda c: c.coverage_score, reverse=True)
    return results


def polygon_from_text(text: str) -> Optional[Polygon]:
    """
    Parse a shapely Polygon from a multiline text block.

    Accepted formats (one vertex per line):
        X,Y
        X Y
        X;Y

    Returns None on parse failure.
    """
    coords = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sep in (",", ";", "\t", " "):
            parts = line.split(sep)
            if len(parts) >= 2:
                try:
                    x, y = float(parts[0].strip()), float(parts[1].strip())
                    coords.append((x, y))
                    break
                except ValueError:
                    continue
    if len(coords) < 3:
        return None
    try:
        return Polygon(coords)
    except Exception:
        return None


def polygon_from_csv_bytes(data: bytes) -> Optional[Polygon]:
    """Parse a Polygon from CSV file bytes with X and Y columns (or two unnamed columns)."""
    import io
    import pandas as pd

    try:
        df = pd.read_csv(io.BytesIO(data))
        # Accept columns named X/Y, x/y, Este/Norte, E/N, etc.
        col_map = {c.strip().upper(): c for c in df.columns}
        xcol = next(
            (col_map[k] for k in ["X", "ESTE", "E", "LON", "LONGITUDE"] if k in col_map),
            df.columns[0],
        )
        ycol = next(
            (col_map[k] for k in ["Y", "NORTE", "N", "LAT", "LATITUDE"] if k in col_map),
            df.columns[1],
        )
        coords = list(zip(df[xcol].astype(float), df[ycol].astype(float)))
        if len(coords) < 3:
            return None
        return Polygon(coords)
    except Exception as e:
        logger.warning(f"Error parsing CSV polygon: {e}")
        return None
