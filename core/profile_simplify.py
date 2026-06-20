"""Polyline simplification (RDP) and solid-toe projection helpers.

These primitives are shared by the parameter extractor (used to simplify
the input profile before computing segment angles) and by anyone that
needs to operate on dense 2D polylines.
"""

import numpy as np

from core.config import DETECTION


def ramer_douglas_peucker(points, epsilon):
    """
    Simplifies a 2D polyline using Ramer-Douglas-Peucker algorithm.
    points: Nx2 array
    epsilon: approximate max distance error

    Iterative implementation (explicit stack + keep-mask): same output as
    the classic recursive version, without per-level array allocations or
    recursion-depth limits on dense profiles.
    """
    points = np.asarray(points)
    n = len(points)
    if n < 3:
        return points

    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[n - 1] = True

    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue

        start_pt = points[start]
        end_pt = points[end]
        line_vec = end_pt - start_pt
        line_len_sq = np.dot(line_vec, line_vec)

        seg = points[start + 1:end]
        if line_len_sq == 0:
            dists = np.linalg.norm(seg - start_pt, axis=1)
        else:
            numer = np.abs(line_vec[0] * (seg[:, 1] - start_pt[1]) -
                           line_vec[1] * (seg[:, 0] - start_pt[0]))
            dists = numer / np.sqrt(line_len_sq)

        local_idx = int(np.argmax(dists))
        if dists[local_idx] > epsilon:
            index = start + 1 + local_idx
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))

    return points[keep]


def _detect_and_project_solid_toe(sorted_face_pts: np.ndarray, face_threshold: float) -> tuple[float, float, np.ndarray]:
    n_pts = len(sorted_face_pts)
    crest = sorted_face_pts[0]
    toe = sorted_face_pts[-1]
    dz = crest[1] - toe[1]
    dx = abs(crest[0] - toe[0])
    default_angle = float(np.degrees(np.arctan2(dz, dx))) if dx > 1e-3 else face_threshold
    if n_pts < 3:
        return float(toe[0]), default_angle, toe
    dy = np.diff(sorted_face_pts[:, 1])
    dx_diff = np.diff(sorted_face_pts[:, 0])
    segs_len = np.sqrt(dx_diff**2 + dy**2)
    valid = segs_len > 1e-4
    segs_ang = np.zeros(len(dy))
    segs_ang[valid] = np.abs(np.degrees(np.arctan2(dy[valid], dx_diff[valid])))
    spill_idx = len(segs_ang)
    for i in range(len(segs_ang) - 1, -1, -1):
        if segs_ang[i] < DETECTION.spill_angle_pile and np.any(segs_ang[:i] > DETECTION.spill_angle_solid):
            spill_idx = i
        else:
            break
    if spill_idx > 0:
        solid_pts = sorted_face_pts[:spill_idx + 1]
        solid_y = solid_pts[:, 1]
        solid_x = solid_pts[:, 0]
        if len(solid_pts) >= 2 and np.var(solid_y) > 1e-4:
            poly = np.polyfit(solid_y, solid_x, 1)
            x_projected = float(poly[0] * toe[1] + poly[1])
            m_abs = abs(poly[0])
            corrected_angle = float(np.degrees(np.arctan2(1, m_abs))) if m_abs > 1e-4 else 90.0
            if crest[0] < toe[0]:
                x_projected = np.clip(x_projected, crest[0], toe[0])
            else:
                x_projected = np.clip(x_projected, toe[0], crest[0])
            return x_projected, corrected_angle, sorted_face_pts[spill_idx]
    return float(toe[0]), default_angle, toe
