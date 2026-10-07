"""Section definition, generation and mesh cutting."""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional
import trimesh


@dataclass
class SectionLine:
    name: str
    origin: np.ndarray
    azimuth: float
    length: float
    sector: str = ""
    file_name: str = ""
    length_up: Optional[float] = None
    length_down: Optional[float] = None

    def __post_init__(self):
        if self.length_up is not None and self.length_down is not None:
            self.length = float(self.length_up + self.length_down)


@dataclass
class ProfileResult:
    """Result of cutting a mesh with a section: 2D profile."""
    distances: np.ndarray
    elevations: np.ndarray


@dataclass(frozen=True)
class ProfileCutDiagnostics:
    profile: Optional[ProfileResult]
    warnings: tuple[str, ...] = ()


def azimuth_to_direction(azimuth_deg: float) -> np.ndarray:
    """Convert azimuth (degrees from North, clockwise) to 2D direction vector."""
    az_rad = np.radians(azimuth_deg)
    return np.array([np.sin(az_rad), np.cos(az_rad)])


def cut_mesh_with_section(mesh: trimesh.Trimesh, section: SectionLine) -> Optional[ProfileResult]:
    return cut_mesh_with_section_diagnostics(mesh, section).profile


def cut_mesh_with_section_diagnostics(
    mesh: trimesh.Trimesh,
    section: SectionLine,
) -> ProfileCutDiagnostics:
    """
    Cut a mesh with a vertical plane defined by a SectionLine.
    Returns a ProfileResult with distances and elevations, or None.
    """
    direction = azimuth_to_direction(section.azimuth)

    # Plane normal (perpendicular to direction in XY plane)
    plane_normal = np.array([direction[1], -direction[0], 0.0])
    plane_origin = np.array([section.origin[0], section.origin[1], 0.0])

    try:
        lines = trimesh.intersections.mesh_plane(
            mesh, plane_normal, plane_origin
        )
    except (ValueError, np.linalg.LinAlgError, AttributeError):
        return ProfileCutDiagnostics(None, ("section_cut_error",))

    if lines is None or len(lines) == 0:
        return ProfileCutDiagnostics(None, ("no_section_intersection",))

    if getattr(section, 'length_up', None) is not None and getattr(section, 'length_down', None) is not None:
        lower_distance = -float(section.length_down)
        upper_distance = float(section.length_up)
    else:
        half_length = float(section.length) / 2.0
        lower_distance = -half_length
        upper_distance = half_length

    def section_distance(point: np.ndarray) -> float:
        return float(np.dot(point[:2] - section.origin[:2], direction))

    clipped_lines = []
    for segment in np.asarray(lines, dtype=float):
        first_point = np.asarray(segment[0], dtype=float)
        second_point = np.asarray(segment[1], dtype=float)
        first_distance = section_distance(first_point)
        second_distance = section_distance(second_point)
        delta_distance = second_distance - first_distance
        if abs(delta_distance) < 1.0e-12:
            if lower_distance <= first_distance <= upper_distance:
                clipped_lines.append((first_point, second_point))
            continue
        start_fraction = max(0.0, min(1.0, (lower_distance - first_distance) / delta_distance))
        end_fraction = max(0.0, min(1.0, (upper_distance - first_distance) / delta_distance))
        if start_fraction > end_fraction:
            start_fraction, end_fraction = end_fraction, start_fraction
        if max(first_distance, second_distance) < lower_distance or min(first_distance, second_distance) > upper_distance:
            continue
        clipped_lines.append((
            first_point + start_fraction * (second_point - first_point),
            first_point + end_fraction * (second_point - first_point),
        ))
    lines = np.asarray(clipped_lines, dtype=float)
    if len(lines) == 0:
        return ProfileCutDiagnostics(None, ("no_section_intersection",))

    endpoint_tolerance = 1.0e-3
    nodes: list[np.ndarray] = []
    buckets: dict[tuple[int, int, int], list[int]] = {}

    def node_for(point: np.ndarray) -> int:
        key = tuple(int(round(float(value) / endpoint_tolerance)) for value in point)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    neighbor = (key[0] + dx, key[1] + dy, key[2] + dz)
                    for node_id in buckets.get(neighbor, ()):
                        if float(np.linalg.norm(nodes[node_id] - point)) <= endpoint_tolerance:
                            return node_id
        node_id = len(nodes)
        nodes.append(np.asarray(point, dtype=float))
        buckets.setdefault(key, []).append(node_id)
        return node_id

    edges: set[tuple[int, int]] = set()
    for segment in np.asarray(lines, dtype=float):
        first = node_for(segment[0])
        second = node_for(segment[1])
        if first != second:
            edges.add((min(first, second), max(first, second)))
    if not edges:
        return ProfileCutDiagnostics(None, ("insufficient_section_points",))

    adjacency: dict[int, set[int]] = {}
    for first, second in edges:
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)

    components: list[set[int]] = []
    unseen = set(adjacency)
    while unseen:
        seed = unseen.pop()
        component = {seed}
        pending = [seed]
        while pending:
            current = pending.pop()
            for neighbor in adjacency[current] & unseen:
                unseen.remove(neighbor)
                component.add(neighbor)
                pending.append(neighbor)
        components.append(component)
    if len(components) != 1:
        return ProfileCutDiagnostics(None, ("disconnected_profile_components",))

    if any(len(neighbors) > 2 for neighbors in adjacency.values()):
        return ProfileCutDiagnostics(None, ("ambiguous_profile_geometry",))
    endpoints = [node_id for node_id, neighbors in adjacency.items() if len(neighbors) == 1]
    if len(endpoints) != 2:
        return ProfileCutDiagnostics(None, ("ambiguous_profile_geometry",))

    start = min(endpoints, key=lambda node_id: section_distance(nodes[node_id]))
    ordered_nodes = [start]
    previous = None
    current = start
    while True:
        following = [node_id for node_id in adjacency[current] if node_id != previous]
        if not following:
            break
        if len(following) != 1:
            return ProfileCutDiagnostics(None, ("ambiguous_profile_geometry",))
        next_node = following[0]
        if next_node in ordered_nodes:
            return ProfileCutDiagnostics(None, ("ambiguous_profile_geometry",))
        ordered_nodes.append(next_node)
        previous, current = current, next_node
    if len(ordered_nodes) != len(adjacency):
        return ProfileCutDiagnostics(None, ("ambiguous_profile_geometry",))

    ordered_points = [nodes[node_id] for node_id in ordered_nodes]
    profile_distances = np.round(
        np.asarray([section_distance(point) for point in ordered_points]), 3
    )
    profile_elevations = np.asarray([point[2] for point in ordered_points])

    if len(profile_distances) < 2:
        return ProfileCutDiagnostics(None, ("insufficient_section_points",))
    from core.config import DETECTION
    resolution = float(DETECTION.profile_resolution)
    if not np.isfinite(resolution) or resolution < 0:
        resolution = 0.0
    repair_limit = min(resolution, max(0.0, float(DETECTION.max_profile_reversal_repair)))
    highest_distance = float(profile_distances[0])
    reversal_normalized = False
    for index in range(1, len(profile_distances)):
        current_distance = float(profile_distances[index])
        if current_distance < highest_distance:
            excursion = highest_distance - current_distance
            if excursion > repair_limit + endpoint_tolerance:
                return ProfileCutDiagnostics(None, ("ambiguous_profile_geometry",))
            profile_distances[index] = highest_distance
            reversal_normalized = reversal_normalized or excursion > endpoint_tolerance + 1.0e-9
        else:
            highest_distance = current_distance

    dense_distances = [float(profile_distances[0])]
    dense_elevations = [float(profile_elevations[0])]
    for index in range(len(profile_distances) - 1):
        d0 = float(profile_distances[index])
        d1 = float(profile_distances[index + 1])
        z0 = float(profile_elevations[index])
        z1 = float(profile_elevations[index + 1])
        span = d1 - d0
        steps = max(1, int(np.ceil(span / resolution))) if resolution > 0 else 1
        for step in range(1, steps + 1):
            fraction = step / steps
            dense_distances.append(d0 + fraction * span)
            dense_elevations.append(z0 + fraction * (z1 - z0))

    profile = ProfileResult(
        distances=np.asarray(dense_distances, dtype=float),
        elevations=np.asarray(dense_elevations, dtype=float),
    )
    warnings = ("minor_profile_reversal_normalized",) if reversal_normalized else ()
    return ProfileCutDiagnostics(profile, warnings)


def cut_both_surfaces(mesh_design: trimesh.Trimesh, mesh_topo: trimesh.Trimesh,
                      section: SectionLine) -> tuple[Optional[ProfileResult], Optional[ProfileResult]]:
    """Cut both design and topo meshes with the same section."""
    pd = cut_mesh_with_section(mesh_design, section)
    pt = cut_mesh_with_section(mesh_topo, section)
    return pd, pt


def compute_local_azimuth(design_mesh: trimesh.Trimesh, point_xy: np.ndarray,
                          radius: float = 50.0) -> float:
    """
    Compute the steepest descent azimuth at a point on the DESIGN mesh surface.
    Fits a plane to nearby vertices and returns the downhill direction.
    
    Args:
        design_mesh: Trimesh object representing the DESIGN surface.
        point_xy: (x, y) coordinates of the point.
        radius: Search radius for vertices.

    Returns:
        float: Azimuth in degrees (0=N, 90=E). Returns 0.0 if not enough neighbors.
    """
    verts = design_mesh.vertices
    dx = verts[:, 0] - point_xy[0]
    dy = verts[:, 1] - point_xy[1]
    dists_sq = dx ** 2 + dy ** 2

    mask = dists_sq < radius ** 2
    if mask.sum() < 10:
        mask = dists_sq < (radius * 3) ** 2
        if mask.sum() < 10:
            # Fallback: cannot determine slope, return 0.0 (North)
            return 0.0

    local_verts = verts[mask]

    # Fit plane z = a*x + b*y + c via least squares
    A = np.column_stack([local_verts[:, 0], local_verts[:, 1],
                         np.ones(len(local_verts))])
    z = local_verts[:, 2]
    # Use lstsq with valid rcond
    coeffs, _, _, _ = np.linalg.lstsq(A, z, rcond=None)

    # Gradient (steepest ascent) = (a, b); descent = (-a, -b)
    grad_x, grad_y = coeffs[0], coeffs[1]
    
    # If gradient is flat (zero), return 0.0
    if abs(grad_x) < 1e-6 and abs(grad_y) < 1e-6:
        return 0.0

    # Azimuth from North, clockwise: arctan2(east_component, north_component)
    # North component (Y) is -grad_y (descent)
    # East component (X) is -grad_x (descent)
    azimuth = np.degrees(np.arctan2(-grad_x, -grad_y)) % 360
    return float(azimuth)


def generate_sections_along_crest(mesh: trimesh.Trimesh, start_point: np.ndarray,
                                   end_point: np.ndarray, n_sections: int,
                                   section_azimuth: Optional[float] = None,
                                   section_length: float = 200.0,
                                   sector_name: str = "",
                                   length_up: Optional[float] = None,
                                   length_down: Optional[float] = None) -> List[SectionLine]:
    """
    Generate evenly spaced sections along a line (e.g., pit crest).
    If section_azimuth is None, computes azimuth perpendicular to the line (Right Hand Rule).
    """
    sections = []
    
    computed_az = section_azimuth
    if computed_az is None:
        # Vector from start to end
        diff = end_point - start_point
        # Azimuth of the line
        line_az = np.degrees(np.arctan2(diff[0], diff[1])) % 360
        # Perpendicular (Right side? or Left? Let's use Right +90)
        computed_az = (line_az + 90) % 360
        
    for i in range(n_sections):
        t = i / (n_sections - 1) if n_sections > 1 else 0.5
        origin = start_point + t * (end_point - start_point)
        sections.append(SectionLine(
            name=f"S-{i+1:02d}",
            origin=origin,
            azimuth=computed_az,
            length=section_length,
            sector=sector_name,
            length_up=length_up,
            length_down=length_down,
        ))
    return sections


def generate_perpendicular_sections(points: np.ndarray, spacing: float,
                                     section_length: float, sector_name: str = "",
                                     design_mesh: Optional[trimesh.Trimesh] = None,
                                     length_up: Optional[float] = None,
                                     length_down: Optional[float] = None) -> List[SectionLine]:
    """
    Generate sections perpendicular to a polyline at specified spacing.

    Parameters:
        points: Nx2 array of (X, Y) coordinates defining the evaluation line
        spacing: Distance between sections in meters
        section_length: Length of each section in meters
        sector_name: Sector name for labeling
        design_mesh: If provided, compute azimuth from this mesh's slope
                     instead of line perpendicular. MUST be the DESIGN mesh.
        length_up: Optional asymmetric length in positive direction
        length_down: Optional asymmetric length in negative direction
    Returns:
        List of SectionLine objects
    """
    points = np.atleast_2d(points)
    if len(points) < 2:
        return []

    # Cumulative distance along polyline
    diffs = np.diff(points, axis=0)
    seg_lengths = np.sqrt((diffs ** 2).sum(axis=1))
    cum_dist = np.concatenate([[0], np.cumsum(seg_lengths)])
    total_length = cum_dist[-1]

    if total_length < 1e-6:
        return []

    # Section positions along the polyline
    if total_length < spacing:
        section_dists = [total_length / 2]
    else:
        section_dists = np.arange(spacing / 2, total_length, spacing)

    sections = []
    for i, d in enumerate(section_dists):
        # Find which segment we're on
        seg_idx = int(np.searchsorted(cum_dist, d, side='right')) - 1
        seg_idx = max(0, min(seg_idx, len(points) - 2))

        # Interpolate position
        t = ((d - cum_dist[seg_idx]) / seg_lengths[seg_idx]
             if seg_lengths[seg_idx] > 0 else 0)
        origin = points[seg_idx] + t * diffs[seg_idx]

        if design_mesh is not None:
            # Enforce using the provided design mesh for azimuth
            az = compute_local_azimuth(design_mesh, origin)
        else:
            # Perpendicular to the polyline tangent
            tangent = diffs[seg_idx]
            tangent_az = np.degrees(np.arctan2(tangent[0], tangent[1])) % 360
            az = (tangent_az + 90) % 360

        sections.append(SectionLine(
            name=f"S-{i + 1:02d}",
            origin=origin,
            azimuth=az,
            length=section_length,
            sector=sector_name,
            length_up=length_up,
            length_down=length_down,
        ))

    return sections
