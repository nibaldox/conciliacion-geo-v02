from dataclasses import dataclass
from threading import Lock

import numpy as np
import trimesh

from core.config import SECTION_INDEX


@dataclass(frozen=True, eq=False)
class FaceGridIndex:
    origin_xy: np.ndarray
    cell_size_m: float
    ny: int
    max_face_span_m: float
    sorted_keys: np.ndarray
    order: np.ndarray


_INDEX_LOCK = Lock()


def build_face_grid_index(mesh: trimesh.Trimesh, cell_size_m: float | None = None) -> FaceGridIndex:
    cell_size = float(SECTION_INDEX.cell_size_m if cell_size_m is None else cell_size_m)
    if not np.isfinite(cell_size) or cell_size <= 0:
        raise ValueError('cell_size_m must be positive and finite')
    triangles = np.asarray(mesh.vertices)[np.asarray(mesh.faces)][:, :, :2]
    if not len(triangles):
        empty = np.empty(0, dtype=np.int64)
        return FaceGridIndex(np.zeros(2, dtype=np.float64), cell_size, 1, 0.0, empty, empty.copy())
    fmin, fmax = triangles.min(axis=1), triangles.max(axis=1)
    origin = fmin.min(axis=0)
    span = float((fmax - fmin).max())
    cells = np.floor(((fmin + fmax) / 2 - origin) / cell_size).astype(np.int64)
    ny = int(cells[:, 1].max()) + 1
    keys = cells[:, 0] * ny + cells[:, 1]
    order = np.argsort(keys, kind='stable').astype(np.int64, copy=False)
    return FaceGridIndex(origin, cell_size, ny, span, keys[order], order)


def get_face_grid_index(mesh: trimesh.Trimesh) -> FaceGridIndex:
    result = mesh._cache['conciliacion_face_grid']
    if result is None:
        with _INDEX_LOCK:
            result = mesh._cache['conciliacion_face_grid']
            if result is None:
                result = build_face_grid_index(mesh)
                mesh._cache['conciliacion_face_grid'] = result
    return result


def candidate_faces(index: FaceGridIndex, start_xy: np.ndarray, end_xy: np.ndarray, pad_m: float) -> np.ndarray:
    if not len(index.sorted_keys):
        return np.empty(0, dtype=np.int64)
    padding = pad_m + index.max_face_span_m / 2
    lo = np.minimum(start_xy, end_xy) - padding
    hi = np.maximum(start_xy, end_xy) + padding
    low = np.floor((lo - index.origin_xy) / index.cell_size_m).astype(np.int64)
    high = np.floor((hi - index.origin_xy) / index.cell_size_m).astype(np.int64)
    max_x = int(index.sorted_keys[-1] // index.ny)
    x0, x1 = max(int(low[0]), 0), min(int(high[0]), max_x)
    y0, y1 = max(int(low[1]), 0), min(int(high[1]), index.ny - 1)
    if x0 > x1 or y0 > y1:
        return np.empty(0, dtype=np.int64)
    parts = []
    for x in range(x0, x1 + 1):
        start = np.searchsorted(index.sorted_keys, x * index.ny + y0)
        end = np.searchsorted(index.sorted_keys, x * index.ny + y1, side='right')
        parts.append(index.order[start:end])
    return np.sort(np.concatenate(parts))
