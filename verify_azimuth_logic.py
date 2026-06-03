
import numpy as np
import trimesh
import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))
from core.section_cutter import compute_local_azimuth

def create_tilted_plane(tilt_axis='x', angle_deg=45):
    """
    Creates a simple 100x100 plane tilted.
    If tilt_axis='x', it dips along X axis.
    """
    x = np.linspace(0, 100, 10)
    y = np.linspace(0, 100, 10)
    X, Y = np.meshgrid(x, y)
    
    # Plane z = -x (dips East) if angle=45
    # angle_rad = np.radians(angle_deg)
    # z = -tan(angle) * x
    
    slope = np.tan(np.radians(angle_deg))
    if tilt_axis == 'x':
        # Dips East (positive X)
        Z = -slope * X
        expected_az = 90.0
    elif tilt_axis == 'y':
        # Dips North (positive Y)
        Z = -slope * Y
        expected_az = 0.0
    elif tilt_axis == '-y':
        # Dips South (negative Y)
        Z = slope * Y
        expected_az = 180.0
        
    vertices = []
    for i in range(10):
        for j in range(10):
            vertices.append([X[i, j], Y[i, j], Z[i, j]])
            
    # Create simple faces
    faces = []
    for i in range(9):
        for j in range(9):
            v0 = i * 10 + j
            v1 = v0 + 1
            v2 = (i + 1) * 10 + j
            v3 = v2 + 1
            faces.append([v0, v1, v2])
            faces.append([v1, v3, v2])
            
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    return mesh, expected_az

def test_azimuth():
    print("Testing compute_local_azimuth...")
    
    # Case 1: Dip East (Azimuth 90)
    mesh1, exp1 = create_tilted_plane('x', 45)
    az1 = compute_local_azimuth(mesh1, np.array([50, 50]))
    print(f"Case 1 (Dip East): Expected {exp1}, Got {az1:.1f}")
    assert abs(az1 - exp1) < 1.0, f"Failed Case 1: {az1} != {exp1}"
    
    # Case 2: Dip North (Azimuth 0)
    mesh2, exp2 = create_tilted_plane('y', 30)
    az2 = compute_local_azimuth(mesh2, np.array([50, 50]))
    print(f"Case 2 (Dip North): Expected {exp2}, Got {az2:.1f}")
    assert abs(az2 - exp2) < 1.0, f"Failed Case 2: {az2} != {exp2}"

    # Case 3: Dip South (Azimuth 180)
    mesh3, exp3 = create_tilted_plane('-y', 30)
    az3 = compute_local_azimuth(mesh3, np.array([50, 50]))
    print(f"Case 3 (Dip South): Expected {exp3}, Got {az3:.1f}")
    assert abs(az3 - exp3) < 1.0, f"Failed Case 3: {az3} != {exp3}"

    print("✅ All azimuth tests passed.")

if __name__ == "__main__":
    test_azimuth()
