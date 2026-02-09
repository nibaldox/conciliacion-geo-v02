"""Parameter extraction from profiles and design vs as-built comparison."""

import numpy as np
from dataclasses import dataclass, field
from typing import List
from scipy.interpolate import interp1d
from scipy.ndimage import uniform_filter1d


@dataclass
class BenchParams:
    """Parameters for a single bench."""
    bench_number: int
    crest_elevation: float
    crest_distance: float
    toe_elevation: float
    toe_distance: float
    bench_height: float
    face_angle: float
    berm_width: float


@dataclass
class ExtractionResult:
    """Result of parameter extraction for a section."""
    section_name: str
    sector: str
    benches: List[BenchParams] = field(default_factory=list)
    inter_ramp_angle: float = 0.0
    overall_angle: float = 0.0


def ramer_douglas_peucker(points, epsilon):
    """
    Simplifies a 2D polyline using Ramer-Douglas-Peucker algorithm.
    points: Nx2 array
    epsilon: approximate max distance error
    """
    if len(points) < 3:
        return points

    # Find the point with the maximum distance
    dmax = 0.0
    index = 0
    end = len(points) - 1
    
    # Line from start to end
    start_pt = points[0]
    end_pt = points[end]
    
    # Vector from start to end
    line_vec = end_pt - start_pt
    line_len_sq = np.dot(line_vec, line_vec)
    
    if line_len_sq == 0:
        dists = np.linalg.norm(points[1:end] - start_pt, axis=1)
    else:
        # Distance = |cross_product| / line_length
        # But for 2D, cross product of (dx, dy) and (px-sx, py-sy) is (dx*py - dy*px)
        # We need vector formulation
        numer = np.abs(np.cross(line_vec, points[1:end] - start_pt))
        dists = numer / np.sqrt(line_len_sq)

    if len(dists) > 0:
        dmax = np.max(dists)
        index = np.argmax(dists) + 1

    if dmax > epsilon:
        # Recursive call
        rec_results1 = ramer_douglas_peucker(points[:index+1], epsilon)
        rec_results2 = ramer_douglas_peucker(points[index:], epsilon)
        return np.vstack((rec_results1[:-1], rec_results2))
    else:
        return np.vstack((points[0], points[end]))


def extract_parameters(distances, elevations, section_name, sector,
                       resolution=0.5, face_threshold=40.0,
                       berm_threshold=20.0, max_berm_width=50.0):
    """
    Extract geotechnical parameters using Vector Simplification (RDP).
    
    1. Simplify profile using Ramer-Douglas-Peucker (epsilon=resolution/2)
    2. Compute angles of simplified segments
    3. Classify and merge segments
    4. Extract bench geometry
    """
    result = ExtractionResult(section_name=section_name, sector=sector)

    if len(distances) < 3:
        return result

    # Prepare points
    points = np.column_stack((distances, elevations))
    
    # 1. Simplify
    # Epsilon determines how much "noise" we ignore. 
    # For accurate crests/toes, we want high precision.
    epsilon = 0.1  # 10cm tolerance
    simplified = ramer_douglas_peucker(points, epsilon)
    
    if len(simplified) < 2:
        return result
        
    d_simp = simplified[:, 0]
    e_simp = simplified[:, 1]
    
    # 2. Compute Segment Angles
    dx = np.diff(d_simp)
    dy = np.diff(e_simp)
    dists = np.sqrt(dx**2 + dy**2)
    
    # Avoid zero-length segments
    valid_seg = dists > 1e-4
    if not np.any(valid_seg):
        return result
        
    angles = np.zeros(len(dx))
    # Angle in degrees (always positive)
    angles[valid_seg] = np.abs(np.degrees(np.arctan2(dy[valid_seg], dx[valid_seg])))
    
    # 3. Classify Segments
    # Use thresholds provided
    segment_type = np.full(len(angles), 0) # 0=Unknown, 1=Face, 2=Berm
    
    # Strict classification
    segment_type[angles >= face_threshold] = 1 # Face
    segment_type[angles <= berm_threshold] = 2 # Berm
    
    # Merge consecutive segments of same type
    # For "Unknown" segments, we can try to merge them into neighbors or ignore
    # Let's simple merge same types.
    
    merged_segments = []
    if len(segment_type) > 0:
        current_type = segment_type[0]
        start_idx = 0
        for i in range(1, len(segment_type)):
            if segment_type[i] != current_type:
                merged_segments.append({
                    'type': current_type,
                    'start_idx': start_idx, # Index in simplified array
                    'end_idx': i # Exclusive
                })
                current_type = segment_type[i]
                start_idx = i
        merged_segments.append({
            'type': current_type,
            'start_idx': start_idx,
            'end_idx': len(segment_type)
        })
        
    # 4. Extract Benches
    # A bench is usually Berm -> Face (or just Face if it's the bottom and we start there)
    # We look for Face segments.
    # Crest is the top point of a face (dist, elev at start of face segment if going left-to-right? 
    # Wait, distances are sorted? Yes usually distance along section.
    # If distance increases, and we look at profile:
    # Face goes DOWN usually? Or UP?
    # Profile is (Distance, Elevation).
    # Distance usually from Origin outwards.
    # Slopes usually go down or up.
    # Let's assume standard behavior: we just care about the segment geometry.
    # "Crest" is higher elevation point of face. "Toe" is lower elevation point.
    
    benches = []
    bench_num = 0
    
    for seg in merged_segments:
        if seg['type'] == 1: # Face
            # Indices in simplified array
            idx_start = seg['start_idx']
            idx_end = seg['end_idx'] # Exclusive, so point index is idx_end
            
            # Points defining this face sequence
            face_pts = simplified[idx_start : idx_end + 1]
            
            # Start and End of the face "macro-segment"
            p_start = face_pts[0]
            p_end = face_pts[-1]
            
            # Determine Crest and Toe based on elevation
            if p_start[1] > p_end[1]:
                crest = p_start
                toe = p_end
            else:
                crest = p_end
                toe = p_start
            
            bench_height = abs(crest[1] - toe[1])
            
            if bench_height < 2.0:
                continue
                
            # Weighted average angle for the face (weighted by segment length)
            # segs in this face group
            local_dx = dx[idx_start:idx_end]
            local_dy = dy[idx_start:idx_end]
            local_len = dists[idx_start:idx_end]
            local_ang = angles[idx_start:idx_end]
            
            # We filter for only "steep" sub-segments to avoid calculating average with small flat steps if any
            steep_mask = local_ang > (face_threshold - 10)
            if np.sum(local_len[steep_mask]) > 0.1:
                weighted_angle = np.average(local_ang[steep_mask], weights=local_len[steep_mask])
            else:
                weighted_angle = np.average(local_ang, weights=local_len)
                
            bench_num += 1
            benches.append(BenchParams(
                bench_number=bench_num,
                crest_elevation=float(crest[1]),
                crest_distance=float(crest[0]),
                toe_elevation=float(toe[1]),
                toe_distance=float(toe[0]),
                bench_height=float(bench_height),
                face_angle=float(weighted_angle),
                berm_width=0.0
            ))

    # Calculate Berm Widths
    # Berm is horizontal distance between Toe of Bench N and Crest of Bench N+1 (if N+1 is below N)
    # Since we sorted by elevation descending:
    # Bench i is above Bench i+1
    for i in range(len(benches) - 1):
        # Distance from toe of upper bench to crest of lower bench
        # We use 3D distance or horizontal? Usually "Berm Width" is horizontal distance.
        b_upper = benches[i]
        b_lower = benches[i+1]
        
        # Horizontal dist
        h_dist = abs(b_upper.toe_distance - b_lower.crest_distance)
        b_upper.berm_width = float(h_dist)

    # Filter unrealistically large berms (ramps/pit floor)
    # Similar logic to before but simplified
    if max_berm_width and max_berm_width > 0 and len(benches) > 1:
        valid_benches = []
        # We reconstruct groups based on connectivity
        current_group = [benches[0]]
        for i in range(len(benches) - 1):
            if benches[i].berm_width > max_berm_width:
                # Break in group
                # Decide which group to keep? 
                # Usually we want the main pit wall. 
                # Let's store groups and pick largest.
                benches[i].berm_width = 0.0 # Clear berm width for last bench of group
                valid_benches.append(current_group)
                current_group = [benches[i+1]]
            else:
                current_group.append(benches[i+1])
        valid_benches.append(current_group)
        
        # Pick largest group
        benches = max(valid_benches, key=len)
        # Renumber
        for idx, b in enumerate(benches):
            b.bench_number = idx + 1

    result.benches = benches
    
    # Calculate angles
    if len(benches) >= 2:
        top = benches[0]
        bot = benches[-1]
        
        # Overall: Crest top to Toe bot
        dz = top.crest_elevation - bot.toe_elevation
        dx = abs(top.crest_distance - bot.toe_distance)
        if dx > 1e-3:
            result.overall_angle = float(np.degrees(np.arctan2(abs(dz), dx)))
        
        # Inter-ramp (approx): same as overall for now unless we detect ramps
        result.inter_ramp_angle = result.overall_angle
    elif len(benches) == 1:
        result.overall_angle = benches[0].face_angle
        result.inter_ramp_angle = benches[0].face_angle

    return result


def _evaluate_status(deviation, tol_neg, tol_pos):
    """
    Evaluate compliance using tripartite system.
    """
    if deviation < 0:
        limit = tol_neg
    else:
        limit = tol_pos

    abs_dev = abs(deviation)
    if abs_dev <= limit:
        return "CUMPLE"
    elif abs_dev <= limit * 1.5:
        return "FUERA DE TOLERANCIA"
    else:
        return "NO CUMPLE"


def build_reconciled_profile(benches):
    """
    Build an idealized profile from detected crest/toe points.
    """
    if not benches:
        return np.array([]), np.array([])
    distances = []
    elevations = []
    # Assumes benches are sorted by elevation descending
    # We want to plot them in order of distance if possible, or just connectivity
    # Let's sort by distance for plotting
    sorted_b = sorted(benches, key=lambda b: b.crest_distance)
    
    for bench in sorted_b:
        distances.append(bench.crest_distance)
        elevations.append(bench.crest_elevation)
        distances.append(bench.toe_distance)
        elevations.append(bench.toe_elevation)
        
    return np.array(distances), np.array(elevations)


def compare_design_vs_asbuilt(params_design, params_topo, tolerances):
    """
    Compare design vs as-built parameters using ELEVATION MATCHING.
    """
    comparisons = []
    
    # Create valid pairs based on elevation proximity
    # We assume benches should be roughly at same elevation
    
    # Threshold for matching: half bench height (approx 7m)
    match_threshold = 8.0 
    
    used_topo_indices = set()
    
    for bd in params_design.benches:
        # Find best matching topo bench
        best_idx = -1
        min_diff = float('inf')
        
        bd_center_z = (bd.crest_elevation + bd.toe_elevation) / 2
        
        for i, bt in enumerate(params_topo.benches):
            if i in used_topo_indices:
                continue
            bt_center_z = (bt.crest_elevation + bt.toe_elevation) / 2
            diff = abs(bd_center_z - bt_center_z)
            if diff < min_diff:
                min_diff = diff
                best_idx = i
        
        if best_idx != -1 and min_diff < match_threshold:
            # Match found
            used_topo_indices.add(best_idx)
            bt = params_topo.benches[best_idx]
            
            # --- Comparison Logic ---
            height_dev = bt.bench_height - bd.bench_height
            angle_dev = bt.face_angle - bd.face_angle
            
            tol_h = tolerances['bench_height']
            tol_a = tolerances['face_angle']
            tol_b = tolerances['berm_width']
            
             # Berm: evaluate against minimum matching tolerances
            min_berm = tol_b.get('min', 0.0)
            if bt.berm_width == 0.0 and bd.berm_width == 0.0:
                berm_status = "CUMPLE"
            elif bt.berm_width >= min_berm:
                berm_status = "CUMPLE"
            elif bt.berm_width >= min_berm * 0.8:
                berm_status = "FUERA DE TOLERANCIA"
            else:
                 berm_status = "NO CUMPLE"
            
            comparisons.append({
                'sector': params_design.sector,
                'section': params_design.section_name,
                'bench_num': bd.bench_number, # Use design number
                'level': f"{bd.crest_elevation:.0f}",
                'height_design': round(bd.bench_height, 2),
                'height_real': round(bt.bench_height, 2),
                'height_dev': round(height_dev, 2),
                'height_status': _evaluate_status(height_dev, tol_h['neg'], tol_h['pos']),
                'angle_design': round(bd.face_angle, 1),
                'angle_real': round(bt.face_angle, 1),
                'angle_dev': round(angle_dev, 1),
                'angle_status': _evaluate_status(angle_dev, tol_a['neg'], tol_a['pos']),
                'berm_design': round(bd.berm_width, 2),
                'berm_real': round(bt.berm_width, 2),
                'berm_min': min_berm,
                'berm_status': berm_status,
            })
        else:
            # No match found in topo for this design bench
            # We could report "Missing Bench" or just skip
            pass
            
    return comparisons
