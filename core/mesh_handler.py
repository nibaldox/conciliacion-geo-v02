"""Mesh loading, decimation, bounds extraction and conversion to plotly."""

import logging
import os

import trimesh
import numpy as np
import plotly.graph_objects as go
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# Default cap for mesh uploads: 200 MB. Past this size trimesh.load
# is very slow and the file is almost certainly malformed or wrong
# format.
DEFAULT_MAX_MESH_SIZE_MB = 200


class MeshValidationError(ValueError):
    """Raised when an uploaded mesh file fails pre-load validation.

    Distinct from the ValueError that trimesh may raise for a
    malformed mesh, so callers can show a clean "your file is bad"
    error to the user without stack traces.
    """


def _validate_stl_path(filepath: str, max_size_mb: int = DEFAULT_MAX_MESH_SIZE_MB) -> None:
    """Validate file path, type, and size before passing to trimesh."""
    if not filepath:
        raise MeshValidationError("Ruta de archivo vacía.")
    if not os.path.exists(filepath):
        raise MeshValidationError(f"El archivo no existe: {filepath}")
    if not os.path.isfile(filepath):
        raise MeshValidationError(f"La ruta no apunta a un archivo: {filepath}")
    size_bytes = os.path.getsize(filepath)
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        size_mb = size_bytes / (1024 * 1024)
        raise MeshValidationError(
            f"Archivo demasiado grande: {size_mb:.1f} MB "
            f"(máximo permitido: {max_size_mb} MB). "
            f"Considera exportar con menos decimales o simplificar el modelo."
        )
    if size_bytes == 0:
        raise MeshValidationError("El archivo está vacío (0 bytes).")


def _validate_stl_magic_bytes(filepath: str) -> None:
    """Check the file starts with a valid STL header.

    ASCII STL starts with "solid" (or "SOLID" for some exporters).
    Binary STL has an 80-byte preamble + 4-byte triangle count. We
    check the ASCII prefix as a fast pre-filter; for files that
    don't start with "solid" we trust the trimesh parser to handle
    the binary format.
    """
    try:
        with open(filepath, "rb") as fh:
            head = fh.read(5)
    except OSError as exc:
        raise MeshValidationError(f"No se pudo leer el archivo: {exc}") from exc
    if not head:
        raise MeshValidationError("El archivo no contiene datos (lectura devolvió 0 bytes).")
    # 5 == "solid" in ASCII STL. If it doesn't match, we trust trimesh
    # to determine if it's a valid binary STL (trimesh inspects the
    # binary header more thoroughly than this check can).
    # We only reject obvious junk like pure text files, PNG bytes, etc.
    if head.lower() == b"solid":
        return
    # Heuristic: binary STL has 80 bytes of garbage + 4-byte int count.
    # If the file is very short, it can't be a valid binary STL either.
    try:
        size = os.path.getsize(filepath)
    except OSError:
        size = 0
    if size < 84:
        raise MeshValidationError(
            "El archivo no parece un STL válido "
            f"(cabecera inesperada: {head!r}; tamaño {size} bytes)."
        )


def _validate_stl_contents(mesh: trimesh.Trimesh) -> None:
    """Verify the loaded mesh has actual geometry."""
    if not hasattr(mesh, "vertices") or not hasattr(mesh, "faces"):
        raise MeshValidationError("El archivo no contiene una malla 3D válida.")
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise MeshValidationError("La malla está vacía (0 vértices o 0 caras).")


def _load_dxf(filepath: str) -> trimesh.Trimesh:
    """Load 3D faces from a DXF file using ezdxf."""
    try:
        import ezdxf
    except ImportError:
        raise ImportError("ezdxf is required for loading DXF files. Install it with `pip install ezdxf`.")

    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    # Extract 3D FACES
    faces = []
    vertices = []
    
    # Simple approach: iterate over 3DFACE entities
    # This might be slow for huge files, but robust.
    # We collet triangles. Quads (4 pts) need to be split.
    
    raw_faces = msp.query('3DFACE')
    
    # We need to weld vertices to create a proper mesh
    # trimesh.Trimesh(vertices=..., faces=...) does this if we handle indexing
    # or we can just dump all triangles and let trimesh.merge_vertices handle it
    
    tri_verts = []
    
    for e in raw_faces:
        # 3DFACE has 4 corners (0, 1, 2, 3)
        # If 3 and 2 are same, it's a triangle.
        v = list(e.dxf.vtx0), list(e.dxf.vtx1), list(e.dxf.vtx2), list(e.dxf.vtx3)
        
        # Triangle 1: 0-1-2
        tri_verts.append(v[0])
        tri_verts.append(v[1])
        tri_verts.append(v[2])
        
        # Triangle 2: 2-3-0 (if 3 != 2)
        if v[3] != v[2]:
            tri_verts.append(v[2])
            tri_verts.append(v[3])
            tri_verts.append(v[0])
            
    if not tri_verts:
         # Try POLYLINE/MESH? most mining software uses 3DFACE
         raise ValueError("No 3DFACE entities found in DXF.")
         
    # Create mesh from raw triangles (disconnected)
    # faces = [[0,1,2], [3,4,5], ...]
    n_tris = len(tri_verts) // 3
    faces_idx = np.arange(len(tri_verts)).reshape((n_tris, 3))
    
    mesh = trimesh.Trimesh(vertices=tri_verts, faces=faces_idx)
    
    # Merge vertices to create correct topology
    mesh.merge_vertices()
    
    return mesh


def load_dxf_polyline(file_path: str) -> np.ndarray:
    """
    Load the first POLYLINE or LWPOLYLINE found in a DXF file.
    Returns: np.ndarray of shape (N, 2) with X, Y coordinates.
    """
    try:
        import ezdxf
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()

        lwpolys = msp.query('LWPOLYLINE')
        if len(lwpolys) > 0:
            poly = lwpolys[0]
            points = []
            with poly.points("xy") as pts:
                points = list(pts)
            return np.array(points)

        polys = msp.query('POLYLINE')
        if len(polys) > 0:
            poly = polys[0]
            points = [v.dxf.location[:2] for v in poly.vertices]
            return np.array(points)

        raise ValueError("No se encontraron entidades POLYLINE o LWPOLYLINE en el DXF.")
    except (ValueError, KeyError, AttributeError) as e:
        logger.warning("DXF polyline extraction failed for %s: %s", file_path, e)
        return np.array([])


def load_mesh(filepath: str) -> trimesh.Trimesh:
    """Load a 3D surface mesh from STL, OBJ, PLY, or DXF file.

    Raises:
        MeshValidationError: when the file is missing, too large,
            empty, or doesn't pass the STL magic-byte check.
        ValueError: when trimesh can parse the file but the
            resulting mesh has no usable geometry (legacy path).
    """
    is_stl = str(filepath).lower().endswith(('.stl',))
    if is_stl:
        _validate_stl_path(filepath)
        _validate_stl_magic_bytes(filepath)

    if str(filepath).lower().endswith('.dxf'):
        mesh = _load_dxf(filepath)
    else:
        mesh = trimesh.load(filepath)

    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)

    if is_stl:
        _validate_stl_contents(mesh)
    else:
        if not hasattr(mesh, 'vertices') or not hasattr(mesh, 'faces'):
            raise ValueError("El archivo no contiene una malla 3D válida.")
        if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            raise ValueError("La malla está vacía (0 vértices o 0 caras).")

    return mesh


def get_mesh_bounds(mesh: trimesh.Trimesh) -> Dict[str, Any]:
    """Get bounding box and statistics for a mesh."""
    bounds = mesh.bounds  # [[xmin, ymin, zmin], [xmax, ymax, zmax]]
    center = mesh.centroid
    return {
        'xmin': float(bounds[0][0]), 'xmax': float(bounds[1][0]),
        'ymin': float(bounds[0][1]), 'ymax': float(bounds[1][1]),
        'zmin': float(bounds[0][2]), 'zmax': float(bounds[1][2]),
        'center': center,
        'n_faces': len(mesh.faces),
        'n_vertices': len(mesh.vertices),
    }


def _vertex_clustering(mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
    """
    Decimate via vertex clustering: group nearby vertices into grid cells,
    merge them, and rebuild faces. Preserves mesh connectivity.
    """
    target_verts = max(target_faces // 2, 500)
    bounds = mesh.bounds
    extents = bounds[1] - bounds[0]

    # Cell size so that grid has ~target_verts cells
    volume = float(np.prod(extents))
    cell_size = (volume / target_verts) ** (1.0 / 3.0) if volume > 0 else 1.0

    # Quantize vertices to grid cells
    grid = ((mesh.vertices - bounds[0]) / cell_size).astype(np.int32)

    # Encode (gx, gy, gz) into a single key per vertex
    mx = int(grid[:, 0].max()) + 1
    my = int(grid[:, 1].max()) + 1
    keys = grid[:, 0] * my * (int(grid[:, 2].max()) + 1) + \
           grid[:, 1] * (int(grid[:, 2].max()) + 1) + grid[:, 2]

    # Map each original vertex to a new cluster index
    unique_keys, inverse = np.unique(keys, return_inverse=True)

    # Average vertex positions per cluster
    new_verts = np.zeros((len(unique_keys), 3))
    counts = np.zeros(len(unique_keys))
    np.add.at(new_verts, inverse, mesh.vertices)
    np.add.at(counts, inverse, 1)
    new_verts /= counts[:, None]

    # Remap face indices
    new_faces = inverse[mesh.faces]

    # Remove degenerate faces (two or more vertices collapsed to same cluster)
    valid = ((new_faces[:, 0] != new_faces[:, 1]) &
             (new_faces[:, 1] != new_faces[:, 2]) &
             (new_faces[:, 0] != new_faces[:, 2]))
    new_faces = new_faces[valid]

    # Remove duplicate faces
    sorted_f = np.sort(new_faces, axis=1)
    _, unique_idx = np.unique(sorted_f, axis=0, return_index=True)
    new_faces = new_faces[unique_idx]

    return trimesh.Trimesh(vertices=new_verts, faces=new_faces)


def decimate_mesh(mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
    """Reduce mesh face count for visualization performance."""
    if len(mesh.faces) <= target_faces:
        return mesh
    try:
        return mesh.simplify_quadric_decimation(face_count=target_faces)
    except (ImportError, Exception):
        return _vertex_clustering(mesh, target_faces)


def mesh_to_plotly(mesh: trimesh.Trimesh, name: str, color: str, opacity: float) -> go.Mesh3d:
    """Convert a trimesh mesh to a plotly Mesh3d trace."""
    vertices = mesh.vertices
    faces = mesh.faces
    return go.Mesh3d(
        x=vertices[:, 0],
        y=vertices[:, 1],
        z=vertices[:, 2],
        i=faces[:, 0],
        j=faces[:, 1],
        k=faces[:, 2],
        name=name,
        color=color,
        opacity=opacity,
        showlegend=True,
    )
