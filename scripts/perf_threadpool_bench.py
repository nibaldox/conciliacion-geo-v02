import time
import numpy as np
import trimesh
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.section_cutter import cut_mesh_with_section, SectionLine
from core.param_extractor import extract_parameters

mesh = trimesh.creation.icosphere(subdivisions=6, radius=100.0)
sections = [SectionLine(name=f"S-{i:02d}", origin=np.array([i, 0]), azimuth=0.0, length=200.0) for i in range(100)]

def process_single(s):
    res = cut_mesh_with_section(mesh, s)
    if res:
        return extract_parameters(res.distances, res.elevations, s.name, s.sector, 0.5, 40.0, 20.0)
    return None

t0 = time.time()
with ThreadPoolExecutor() as executor:
    futures = [executor.submit(process_single, s) for s in sections]
    for _ in as_completed(futures):
        pass
t1 = time.time()
print(f"ThreadPoolExecutor took {t1-t0:.4f}s")
