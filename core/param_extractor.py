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
    is_ramp: bool = False


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
    Extract geotechnical parameters using Slope-Transition Detection.
    
    Improved algorithm:
    1. Simplify profile using RDP with epsilon = resolution / 2
    2. Compute angles of simplified segments
    3. Smooth angles with moving average (window=3) to reduce noise
    4. Detect transitions: where smoothed angle crosses face_threshold
       - Berm→Face crossing = Crest (last flat point)
       - Face→Berm crossing = Toe (first flat point)
    5. Build benches from Crest→Toe pairs
    6. Post-process: merge micro-benches, validate ordering, filter short faces
    """
    result = ExtractionResult(section_name=section_name, sector=sector)

    if len(distances) < 3:
        return result

    # Prepare points
    points = np.column_stack((distances, elevations))
    
    # 1. Simplify with configurable epsilon
    epsilon = max(resolution / 2.0, 0.05)  # minimum 5cm
    simplified = ramer_douglas_peucker(points, epsilon)
    
    if len(simplified) < 3:
        return result
        
    d_simp = simplified[:, 0]
    e_simp = simplified[:, 1]
    n_pts = len(d_simp)
    
    # 2. Compute Segment Angles
    dx = np.diff(d_simp)
    dy = np.diff(e_simp)
    seg_lengths = np.sqrt(dx**2 + dy**2)
    
    # Avoid zero-length segments
    valid_seg = seg_lengths > 1e-4
    if not np.any(valid_seg):
        return result
        
    angles = np.zeros(len(dx))
    # Absolute angle in degrees (0° = horizontal, 90° = vertical)
    angles[valid_seg] = np.abs(np.degrees(np.arctan2(dy[valid_seg], dx[valid_seg])))
    
    # 3. Smooth angles with moving average (window=3) to reduce noise
    if len(angles) >= 3:
        smoothed_angles = uniform_filter1d(angles, size=3, mode='nearest')
    else:
        smoothed_angles = angles.copy()
    
    # 4. Detect Transitions (Slope Crossings)
    # A segment is "steep" if its smoothed angle >= face_threshold
    is_steep = smoothed_angles >= face_threshold
    
    # Find transition points:
    # - Rising edge (False→True): start of a face → the vertex before is the CREST
    # - Falling edge (True→False): end of a face → the vertex after is the TOE
    
    crests = []  # List of vertex indices (crest points)
    toes = []    # List of vertex indices (toe points)
    
    for i in range(1, len(is_steep)):
        if is_steep[i] and not is_steep[i-1]:
            # Rising edge: segment i is steep, segment i-1 was flat
            # Crest vertex is point i (shared between segment i-1 and segment i)
            crests.append(i)
        elif not is_steep[i] and is_steep[i-1]:
            # Falling edge: segment i is flat, segment i-1 was steep
            # Toe vertex is point i (shared between segment i-1 and segment i)
            toes.append(i)
    
    # Handle edge case: profile starts steep (no leading berm)
    if len(is_steep) > 0 and is_steep[0]:
        crests.insert(0, 0)  # First point is crest
    
    # Handle edge case: profile ends steep (no trailing berm)
    if len(is_steep) > 0 and is_steep[-1]:
        toes.append(n_pts - 1)  # Last point is toe
    
    # 5. Build Benches from Crest→Toe Pairs
    # Match each crest with the next toe to form a bench face
    benches = []
    bench_num = 0
    
    crest_idx = 0
    toe_idx = 0
    
    while crest_idx < len(crests) and toe_idx < len(toes):
        c_vertex = crests[crest_idx]
        
        # Find the next toe AFTER this crest
        while toe_idx < len(toes) and toes[toe_idx] <= c_vertex:
            toe_idx += 1
        
        if toe_idx >= len(toes):
            break
            
        t_vertex = toes[toe_idx]
        
        # Crest and Toe points
        crest_pt = simplified[c_vertex]
        toe_pt = simplified[t_vertex]
        
        # Determine which is higher (crest) and which is lower (toe)
        if crest_pt[1] > toe_pt[1]:
            crest = crest_pt
            toe = toe_pt
        else:
            crest = toe_pt
            toe = crest_pt
        
        bench_height = abs(crest[1] - toe[1])
        
        # Filter: minimum bench height
        if bench_height < 2.0:
            crest_idx += 1
            toe_idx += 1
            continue
        
        # Filter: minimum face length (distance between crest and toe)
        face_length = np.sqrt((crest[0] - toe[0])**2 + (crest[1] - toe[1])**2)
        if face_length < 1.5:
            crest_idx += 1
            toe_idx += 1
            continue
        
        # Calculate weighted average face angle for segments between crest and toe
        seg_start = min(c_vertex, t_vertex)
        seg_end = max(c_vertex, t_vertex)
        
        if seg_end > seg_start:
            local_ang = angles[seg_start:seg_end]
            local_len = seg_lengths[seg_start:seg_end]
            
            # Weight by segment length, prefer steep segments
            steep_mask = local_ang > (face_threshold - 10)
            if np.any(steep_mask) and np.sum(local_len[steep_mask]) > 0.1:
                weighted_angle = np.average(local_ang[steep_mask], weights=local_len[steep_mask])
            elif np.sum(local_len) > 0:
                weighted_angle = np.average(local_ang, weights=local_len)
            else:
                weighted_angle = face_threshold
        else:
            weighted_angle = face_threshold
                
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
        
        crest_idx += 1
        toe_idx += 1

    # 6. Post-Processing
    
    # 6a. Merge micro-benches (consecutive benches that are too close)
    if len(benches) > 1:
        merged = [benches[0]]
        for i in range(1, len(benches)):
            prev = merged[-1]
            curr = benches[i]
            
            # Check if they should be merged
            crest_gap = abs(prev.toe_elevation - curr.crest_elevation)
            combined_height = prev.crest_elevation - curr.toe_elevation
            
            if crest_gap < 2.0 and (prev.bench_height < 3.0 or curr.bench_height < 3.0):
                # Merge: keep the wider range
                merged[-1] = BenchParams(
                    bench_number=prev.bench_number,
                    crest_elevation=max(prev.crest_elevation, curr.crest_elevation),
                    crest_distance=prev.crest_distance if prev.crest_elevation >= curr.crest_elevation else curr.crest_distance,
                    toe_elevation=min(prev.toe_elevation, curr.toe_elevation),
                    toe_distance=prev.toe_distance if prev.toe_elevation <= curr.toe_elevation else curr.toe_distance,
                    bench_height=float(abs(max(prev.crest_elevation, curr.crest_elevation) - min(prev.toe_elevation, curr.toe_elevation))),
                    face_angle=float(np.average([prev.face_angle, curr.face_angle], 
                                                weights=[prev.bench_height, curr.bench_height])),
                    berm_width=0.0
                )
            else:
                merged.append(curr)
        
        benches = merged
        # Renumber
        for idx, b in enumerate(benches):
            b.bench_number = idx + 1
    
    # 6b. Sort benches by elevation (descending crest)
    benches.sort(key=lambda b: b.crest_elevation, reverse=True)
    for idx, b in enumerate(benches):
        b.bench_number = idx + 1

    # Calculate Berm Widths
    for i in range(len(benches) - 1):
        b_upper = benches[i]
        b_lower = benches[i+1]
        h_dist = abs(b_upper.toe_distance - b_lower.crest_distance)
        b_upper.berm_width = float(h_dist)
        
        # Ramp Detection: Width 15m - 42m
        if 15.0 <= b_upper.berm_width <= 42.0:
            b_upper.is_ramp = True

    # Filter unrealistically large berms (group breaking)
    if max_berm_width and max_berm_width > 0 and len(benches) > 1:
        valid_groups = []
        current_group = [benches[0]]
        for i in range(len(benches) - 1):
            if benches[i].berm_width > max_berm_width:
                benches[i].berm_width = 0.0
                valid_groups.append(current_group)
                current_group = [benches[i+1]]
            else:
                current_group.append(benches[i+1])
        valid_groups.append(current_group)
        
        benches = max(valid_groups, key=len)
        for idx, b in enumerate(benches):
            b.bench_number = idx + 1

    # Trailing berm detection (flat area after last bench)
    if len(benches) > 0:
        last_bench = benches[-1]
        
        if distances[-1] > distances[0]:
            mask_after = distances > last_bench.toe_distance + 0.1
        else:
            mask_after = distances < last_bench.toe_distance - 0.1
            
        d_after = distances[mask_after]
        e_after = elevations[mask_after]
        
        if len(d_after) > 1:
            slope_deg = np.degrees(np.arctan2(
                np.abs(e_after[-1] - e_after[0]), 
                np.abs(d_after[-1] - d_after[0])
            ))
            
            if slope_deg <= berm_threshold:
                width = np.abs(d_after[-1] - d_after[0])
                last_bench.berm_width = float(width)
                if 15.0 <= width <= 42.0:
                    last_bench.is_ramp = True

    result.benches = benches
    
    # Calculate overall angles
    if len(benches) >= 2:
        top = benches[0]
        bot = benches[-1]
        
        dz = top.crest_elevation - bot.toe_elevation
        dx_total = abs(top.crest_distance - bot.toe_distance)
        if dx_total > 1e-3:
            result.overall_angle = float(np.degrees(np.arctan2(abs(dz), dx_total)))
        
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
    Compare design vs as-built parameters using Global Best-Fit Matching (Hungarian Algorithm).
    Now returns matches, missing design benches, and extra topo benches.
    """
    from scipy.optimize import linear_sum_assignment

    comparisons = []
    
    benches_design = params_design.benches
    benches_topo = params_topo.benches
    
    n_d = len(benches_design)
    n_t = len(benches_topo)
    
    if n_d == 0 and n_t == 0:
        return []

    # Create Cost Matrix (Absolute Elevation Difference)
    # Rows: Design, Cols: Topo
    cost_matrix = np.zeros((n_d, n_t))
    
    for i, bd in enumerate(benches_design):
        bd_z = (bd.crest_elevation + bd.toe_elevation) / 2
        for j, bt in enumerate(benches_topo):
            bt_z = (bt.crest_elevation + bt.toe_elevation) / 2
            cost_matrix[i, j] = abs(bd_z - bt_z)
            
    # Solve Assignment Problem (Minimize total elevation difference)
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    
    # Threshold for valid match (e.g. half bench height ~8m)
    match_threshold = 8.0
    
    matched_design_indices = set()
    matched_topo_indices = set()
    
    # Process Matches
    for r, c in zip(row_ind, col_ind):
        diff = cost_matrix[r, c]
        if diff < match_threshold:
            # Valid Match
            bd = benches_design[r]
            bt = benches_topo[c]
            
            matched_design_indices.add(r)
            matched_topo_indices.add(c)
            
            # --- Comparison Logic ---
            height_dev = bt.bench_height - bd.bench_height
            angle_dev = bt.face_angle - bd.face_angle
            
            tol_h = tolerances['bench_height']
            tol_a = tolerances['face_angle']
            tol_b = tolerances['berm_width']
            
            min_berm = tol_b.get('min', 0.0)
            if bt.berm_width == 0.0 and bd.berm_width == 0.0:
                berm_status = "CUMPLE"
            elif bt.berm_width >= min_berm:
                berm_status = "CUMPLE"
            elif bt.berm_width >= min_berm * 0.8:
                berm_status = "FUERA DE TOLERANCIA"
            else:
                berm_status = "NO CUMPLE"
            
            # Override status if it's a detected ramp
            if bt.is_ramp:
                berm_status = "RAMPA DETECTADA"
                if bd.is_ramp or bd.berm_width > 15.0:
                    if abs(bt.berm_width - bd.berm_width) < 3.0:
                        berm_status = "RAMPA OK"
                    else:
                        berm_status = "RAMPA (Desv. Ancho)"
            elif bd.is_ramp:
                berm_status = "FALTA RAMPA"
            
            comparisons.append({
                'sector': params_design.sector,
                'section': params_design.section_name,
                'bench_num': bd.bench_number,
                'type': 'MATCH',
                'level': f"{bd.toe_elevation:.0f}",
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
                'delta_crest': round(bt.crest_distance - bd.crest_distance, 2),
                'delta_toe': round(bt.toe_distance - bd.toe_distance, 2),
                'bench_design': bd,
                'bench_real': bt,
            })
    
    # Process Unmatched Design (Missing Benches)
    for i in range(n_d):
        if i not in matched_design_indices:
            bd = benches_design[i]
            comparisons.append({
                'sector': params_design.sector,
                'section': params_design.section_name,
                'bench_num': bd.bench_number,
                'type': 'MISSING',
                'level': f"{bd.toe_elevation:.0f}",
                'height_design': round(bd.bench_height, 2),
                'height_real': None,
                'height_dev': None,
                'height_status': "NO CONSTRUIDO",
                'angle_design': round(bd.face_angle, 1),
                'angle_real': None,
                'angle_dev': None,
                'angle_status': "-",
                'berm_design': round(bd.berm_width, 2),
                'berm_real': None,
                'berm_min': None,
                'berm_status': "FALTA BANCO",
                'delta_crest': None,
                'delta_toe': None,
                'bench_design': bd,
                'bench_real': None,
            })
            
    # Process Unmatched Topo (Extra Benches)
    for j in range(n_t):
        if j not in matched_topo_indices:
            bt = benches_topo[j]
            comparisons.append({
                'sector': params_design.sector,
                'section': params_design.section_name,
                'bench_num': 999, # Placeholder
                'type': 'EXTRA',
                'level': f"{bt.toe_elevation:.0f}",
                'height_design': None,
                'height_real': round(bt.bench_height, 2),
                'height_dev': None,
                'height_status': "EXTRA",
                'angle_design': None,
                'angle_real': round(bt.face_angle, 1),
                'angle_dev': None,
                'angle_status': "-",
                'berm_design': None,
                'berm_real': round(bt.berm_width, 2),
                'berm_min': None,
                'berm_status': "BANCO ADICIONAL",
                'delta_crest': None, # Meaningless without design? Or could compare to "nearest"? Keep None.
                'delta_toe': None,
                'bench_design': None,
                'bench_real': bt,
            })
            
    # Sort by Level (Descending) for display
    comparisons.sort(key=lambda x: float(x['level']) if x['level'].replace('.','',1).isdigit() else 0, reverse=True)
    
    return comparisons
