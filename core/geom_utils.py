"""Geometric utilities for profile analysis."""

import numpy as np
from scipy.spatial import cKDTree

def calculate_profile_deviation(profile_ref, profile_eval):
    """
    Calculate the minimum 2D Euclidean distance from each point in profile_eval
    to the closest point in profile_ref.
    
    Args:
        profile_ref: Object with .distances and .elevations arrays (The baseline/design)
        profile_eval: Object with .distances and .elevations arrays (The comparison/topo)
        
    Returns:
        np.ndarray: Array of distances (deviations) for each point in profile_eval.
                    Note: This is strictly positive distance. Directionality (inside/outside)
                    is hard to determine without closed polygons, but strict distance is enough
                    for "closeness" heatmaps.
    """
    if profile_ref is None or profile_eval is None:
        return np.array([])
        
    if len(profile_ref.distances) == 0 or len(profile_eval.distances) == 0:
        return np.zeros(len(profile_eval.distances))

    # Points (Distance, Elevation)
    pts_ref = np.column_stack((profile_ref.distances, profile_ref.elevations))
    pts_eval = np.column_stack((profile_eval.distances, profile_eval.elevations))
    
    # Use KDTree for efficient nearest neighbor search
    tree = cKDTree(pts_ref)
    distances, _ = tree.query(pts_eval)
    
    return distances


def calculate_area_between_profiles(profile_ref, profile_eval):
    """
    Calculate area between two profiles (Design vs As-Built).
    Returns:
        area_over (float): Over-excavation area (Ref > Eval) -> actually typically defined:
            If Ref is Design and Eval is Topo:
            - Over-excavation: Material removed beyond design (Empirically: Topo < Design)
            - Under-excavation (Re-fill/Deuda): Material remaining (Topo > Design)
            
            We assume profiles are (Distance, Elevation).
            We need to interpolate common X (Distance) axis.
    """
    from scipy.interpolate import interp1d

    if profile_ref is None or profile_eval is None:
        return 0.0, 0.0

    d_ref, z_ref = profile_ref.distances, profile_ref.elevations
    d_eval, z_eval = profile_eval.distances, profile_eval.elevations

    if len(d_ref) < 2 or len(d_eval) < 2:
        return 0.0, 0.0

    # Determine common range
    min_d = max(d_ref.min(), d_eval.min())
    max_d = min(d_ref.max(), d_eval.max())

    if max_d <= min_d:
        return 0.0, 0.0

    # Create common grid
    # Resolution 0.1m for accurate area integration
    common_d = np.arange(min_d, max_d, 0.1)
    
    # Interpolate
    f_ref = interp1d(d_ref, z_ref, kind='linear', bounds_error=False, fill_value="extrapolate")
    f_eval = interp1d(d_eval, z_eval, kind='linear', bounds_error=False, fill_value="extrapolate")
    
    z_ref_interp = f_ref(common_d)
    z_eval_interp = f_eval(common_d)
    
    # Difference: Topo - Design
    diff = z_eval_interp - z_ref_interp
    
    # Integration step (dx)
    dx = 0.1
    
    # Under-excavation (Deuda): Topo > Design (diff > 0)
    # Over-excavation (Sobre): Topo < Design (diff < 0)
    
    area_under_mask = diff > 0
    area_over_mask = diff < 0
    
    area_under = np.sum(diff[area_under_mask]) * dx
    area_over = np.sum(np.abs(diff[area_over_mask])) * dx
    
    return area_over, area_under, common_d, z_ref_interp, z_eval_interp
