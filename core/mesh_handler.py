"""Mesh loading, decimation, bounds extraction and conversion to plotly."""

import trimesh
import numpy as np
import plotly.graph_objects as go


def _load_dxf(filepath):
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


def load_dxf_polyline(file_path):
    """
    Load the first POLYLINE or LWPOLYLINE found in a DXF file.
    Returns: np.ndarray of shape (N, 2) with X, Y coordinates.
    """
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
        
        # Look for LWPOLYLINE (most common in 2D) or POLYLINE (3D/Legacy)
        # We take the first one we find.
        
        # 1. Try LWPOLYLINE
        lwpolys = msp.query('LWPOLYLINE')
        if len(lwpolys) > 0:
            poly = lwpolys[0]
            # LWPolyline vertices are typically (x, y, start_width, end_width, bulge)
            # We just want x, y
            points = []
            with poly.points("xy") as pts:
                points = list(pts)
            return np.array(points)
            
        # 2. Try POLYLINE (2D or 3D)
        polys = msp.query('POLYLINE')
        if len(polys) > 0:
            poly = polys[0]
            # iterate vertices
            points = [v.dxf.location[:2] for v in poly.vertices]
            return np.array(points)
            
        raise ValueError("No se encontraron entidades POLYLINE o LWPOLYLINE en el DXF.")
        
    except Exception as e:
        print(f"Error loading DXF polyline: {e}")
        return np.array([])


def load_mesh(filepath):
    """Load a 3D surface mesh from STL, OBJ, PLY, or DXF file."""
    if str(filepath).lower().endswith('.dxf'):
        mesh = _load_dxf(filepath)
    else:
        mesh = trimesh.load(filepath)
        
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
        
    if not hasattr(mesh, 'vertices') or not hasattr(mesh, 'faces'):
        raise ValueError("El archivo no contiene una malla 3D válida.")
        
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("La malla está vacía (0 vértices o 0 caras).")
        
    return mesh


def get_mesh_bounds(mesh):
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


def _vertex_clustering(mesh, target_faces):
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


def decimate_mesh(mesh, target_faces):
    """Reduce mesh face count for visualization performance."""
    if len(mesh.faces) <= target_faces:
        return mesh
    try:
        return mesh.simplify_quadric_decimation(target_faces)
    except (ImportError, Exception):
        return _vertex_clustering(mesh, target_faces)


def mesh_to_plotly(mesh, name, color, opacity):
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
