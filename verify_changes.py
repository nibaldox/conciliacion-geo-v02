import sys
import os
from pathlib import Path
import numpy as np

# Add current directory to path
sys.path.insert(0, os.getcwd())

from core.param_extractor import extract_parameters, compare_design_vs_asbuilt, BenchParams, ExtractionResult
from core.geom_utils import calculate_profile_deviation

def test_ramp_detection():
    print("Testing Ramp Detection...")
    # Create a profile
    # (0, 100) -> (10, 100): Berm 1 (Width 10)
    # (10, 100) -> (12, 90): Face 1
    # (12, 90) -> (37, 90): Berm 2 (Width 25) -> TARGET RAMP
    # (37, 90) -> (39, 80): Face 2
    
    d = np.array([0, 10, 12, 37, 39], dtype=float)
    z = np.array([100, 100, 90, 90, 80], dtype=float)
    
    # We need to make sure extract_parameters finds these segments.
    # It simplifies first. These points are collinear per segment, so RDP will keep them (corners).
    
    res = extract_parameters(d, z, "TestSection", "TestSector", max_berm_width=50.0)
    
    found_ramp = False
    print(f"Found {len(res.benches)} benches")
    for b in res.benches:
        print(f"Bench {b.bench_number}: Width={b.berm_width:.1f}, IsRamp={b.is_ramp}")
        # Identify the 25m width bench
        if abs(b.berm_width - 25.0) < 1.0:
            if b.is_ramp:
                found_ramp = True
            else:
                print(" -> Has correct width but is_ramp=False!")
    
    if found_ramp:
        print("✅ Ramp detected successfully.")
    else:
        print("❌ Ramp NOT detected.")
        
    # Validation of status
    params_d = ExtractionResult("S1", "Sec")
    params_d.benches = [
        BenchParams(1, 100, 10, 90, 12, 10, 70, 25, is_ramp=True) # Design has ramp
    ]
    params_t = ExtractionResult("S1", "Sec")
    params_t.benches = [
        BenchParams(1, 100, 10, 90, 12, 10, 70, 25, is_ramp=True) # Topo has ramp
    ]
    
    tol = {
        'bench_height': {'neg': 1, 'pos': 1},
        'face_angle': {'neg': 5, 'pos': 5},
        'berm_width': {'min': 5},
    }
    
    comps = compare_design_vs_asbuilt(params_d, params_t, tol)
    if comps:
        print(f"Comparison Status: {comps[0]['berm_status']}")
        if comps[0]['berm_status'] == "RAMPA OK":
            print("✅ Status RAMPA OK verified.")
        else:
            print("❌ Status check failed.")

def test_deviation():
    print("\nTesting Deviation Calculation...")
    from dataclasses import dataclass
    @dataclass
    class Profile:
        distances: np.ndarray
        elevations: np.ndarray
        
    p1 = Profile(np.array([0, 10], dtype=float), np.array([0, 0], dtype=float))
    p2 = Profile(np.array([0, 10], dtype=float), np.array([1, 1], dtype=float)) # 1m higher
    
    devs = calculate_profile_deviation(p1, p2)
    print(f"Deviations: {devs}")
    
    if np.allclose(devs, 1.0):
        print("✅ Deviation calculation correct.")
    else:
        print("❌ Deviation calculation incorrect.")

def test_area_calculation():
    print("\nTesting Area Calculation...")
    from core.geom_utils import calculate_area_between_profiles
    from dataclasses import dataclass
    @dataclass
    class Profile:
        distances: np.ndarray
        elevations: np.ndarray
        
    # Design flat at Z=100, length 10m
    p_ref = Profile(np.array([0, 10]), np.array([100, 100]))
    
    # As-Built:
    # 0-5m: Z=101 (Deuda of 1m height * 5m length = 5m2)
    # 5-10m: Z=99 (Overbreak of 1m height * 5m length = 5m2)
    # We simulate this with points
    p_eval = Profile(np.array([0, 5, 5.001, 10]), np.array([101, 101, 99, 99]))
    
    over, under, _, _, _ = calculate_area_between_profiles(p_ref, p_eval)
    
    print(f"Over: {over:.2f}, Under: {under:.2f}")
    
    if abs(over - 5.0) < 0.2 and abs(under - 5.0) < 0.2:
         print("✅ Area calculation correct.")
    else:
         print("❌ Area calculation failed.")

if __name__ == "__main__":
    test_ramp_detection()
    test_deviation()
    test_area_calculation()
