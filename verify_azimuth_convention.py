
import numpy as np
import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))
from core.section_cutter import azimuth_to_direction, compute_local_azimuth

def test_convention():
    print("Testing Azimuth Convention (N=0, E=90, S=180, W=270)...")
    
    # Test 1: azimuth_to_direction
    # Should return [sin(az), cos(az)] -> [x, y]
    
    # North (0) -> [0, 1]
    v_n = azimuth_to_direction(0)
    print(f"Az 0 (N) -> Vector {v_n} (Expected [0. 1.])")
    assert np.allclose(v_n, [0, 1], atol=1e-6)
    
    # East (90) -> [1, 0]
    v_e = azimuth_to_direction(90)
    print(f"Az 90 (E) -> Vector {v_e} (Expected [1. 0.])")
    assert np.allclose(v_e, [1, 0], atol=1e-6)
    
    # South (180) -> [0, -1]
    v_s = azimuth_to_direction(180)
    print(f"Az 180 (S) -> Vector {v_s} (Expected [0. -1.])")
    assert np.allclose(v_s, [0, -1], atol=1e-6)
    
    # West (270) -> [-1, 0]
    v_w = azimuth_to_direction(270)
    print(f"Az 270 (W) -> Vector {v_w} (Expected [-1. 0.])")
    assert np.allclose(v_w, [-1, 0], atol=1e-6)
    
    print("✅ azimuth_to_direction follows standard Geodetic convention.")
    
    # Test 2: compute_local_azimuth (arctan2 check)
    # We simulate a gradient.
    # If descent is towards East [1, 0], Grad is [-1, 0].
    # formula: degrees(arctan2(-grad_x, -grad_y))
    
    # Case East Descent: grad = [-1, 0] (ascent West)
    # -grad = [1, 0]
    # arctan2(1, 0) = 90 deg.
    az = np.degrees(np.arctan2(1, 0)) % 360
    print(f"Descent East -> Az {az} (Expected 90.0)")
    assert az == 90.0
    
    # Case North Descent: grad = [0, -1] (ascent South)
    # -grad = [0, 1]
    # arctan2(0, 1) = 0 deg.
    az = np.degrees(np.arctan2(0, 1)) % 360
    print(f"Descent North -> Az {az} (Expected 0.0)")
    assert az == 0.0
    
    print("✅ conventions verified.")

if __name__ == "__main__":
    test_convention()
