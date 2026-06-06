import numpy as np
import trimesh
import networkx as nx

def extract_breaklines(mesh: trimesh.Trimesh, angle_threshold_deg: float = 20.0) -> dict:
    """
    Extract breaklines (crests and toes) from a trimesh object based on dihedral angles.
    Returns a dict with 'crests' and 'toes' containing lists of polylines.
    """
    if not hasattr(mesh, 'face_adjacency') or mesh.face_adjacency is None:
        return {"crests": [], "toes": []}
        
    normals1 = mesh.face_normals[mesh.face_adjacency[:, 0]]
    normals2 = mesh.face_normals[mesh.face_adjacency[:, 1]]
    
    dots = np.clip(np.sum(normals1 * normals2, axis=1), -1.0, 1.0)
    angles = np.degrees(np.arccos(dots))
    
    mask = angles >= angle_threshold_deg
    is_convex = mesh.face_adjacency_convex
    
    def get_polylines(edge_mask):
        edges = mesh.face_adjacency_edges[edge_mask]
        if len(edges) == 0:
            return []
            
        subgraph = [tuple(edge) for edge in edges]
        g = nx.Graph(subgraph)
        
        polylines = []
        while g.number_of_edges() > 0:
            isolated = [n for n, d in g.degree() if d == 0]
            g.remove_nodes_from(isolated)
            
            if g.number_of_edges() == 0:
                break
                
            degrees = dict(g.degree())
            endpoints = [node for node, degree in degrees.items() if degree == 1]
            
            start_node = endpoints[0] if endpoints else list(g.nodes())[0]
            path = [start_node]
            curr = start_node
            
            while True:
                neighbors = list(g.neighbors(curr))
                if not neighbors:
                    break
                    
                nxt = neighbors[0]
                g.remove_edge(curr, nxt)
                path.append(nxt)
                curr = nxt
                
                if curr == start_node:
                    break
                
            if len(path) > 1:
                poly_coords = [[float(mesh.vertices[idx][0]), float(mesh.vertices[idx][1]), float(mesh.vertices[idx][2])] for idx in path]
                polylines.append(poly_coords)
                
        return polylines

    return {
        "crests": get_polylines(mask & is_convex),
        "toes": get_polylines(mask & ~is_convex)
    }
