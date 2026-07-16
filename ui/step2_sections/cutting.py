"""Pure geometry / cutting helpers for step 2 (no Streamlit calls)."""
import io
import os
import tempfile
from typing import List, Optional

import numpy as np
import pandas as pd

from core import load_dxf_polyline
from core.section_cutter import (
    SectionLine,
    compute_local_azimuth,
    generate_perpendicular_sections,
    generate_sections_along_crest,
)


def parse_coord_file(coord_file) -> Optional[np.ndarray]:
    """Parse a CSV/TXT/DXF coordinate file and return an Nx2 numpy array."""
    filename = coord_file.name.lower()
    if filename.endswith('.dxf'):
        return _parse_dxf_coord_file(coord_file)
    return _parse_csv_coord_file(coord_file)


def _parse_dxf_coord_file(coord_file) -> Optional[np.ndarray]:
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(coord_file.read())
        tmp_path = f.name
    try:
        polyline = load_dxf_polyline(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    if len(polyline) == 0:
        return None
    return polyline


def _parse_csv_coord_file(coord_file) -> Optional[np.ndarray]:
    content = coord_file.read().decode('utf-8')
    df_coords = pd.read_csv(io.StringIO(content), nrows=10000)

    x_col = next((c for c in df_coords.columns
                  if c.strip().upper() in ('X', 'ESTE', 'EAST', 'E')), None)
    y_col = next((c for c in df_coords.columns
                  if c.strip().upper() in ('Y', 'NORTE', 'NORTH', 'N')), None)

    if x_col is None or y_col is None:
        num_cols = df_coords.select_dtypes(include=[np.number]).columns
        if len(num_cols) >= 2:
            x_col, y_col = num_cols[0], num_cols[1]
        else:
            return None

    return df_coords[[x_col, y_col]].dropna().values.astype(float)


def find_df_column(df, aliases):
    """Find the first column in df whose uppercase name matches one of aliases."""
    return next((c for c in df.columns if c.strip().upper() in aliases), None)


def generate_file_sections(
    polyline: np.ndarray,
    spacing: float,
    len_up: float,
    len_down: float,
    sector: str,
    design_mesh,
    file_name: str,
) -> List[SectionLine]:
    """Generate perpendicular sections from a loaded polyline."""
    auto_mesh = design_mesh if design_mesh is not None else None
    preview_sections = generate_perpendicular_sections(
        polyline, spacing, len_up + len_down, sector,
        design_mesh=auto_mesh, length_up=len_up, length_down=len_down)

    file_base, _ = os.path.splitext(file_name)
    for j, sec in enumerate(preview_sections):
        sec.file_name = file_name
        sec.name = f"S{j+1:02d}-{file_base}"
    return preview_sections


def generate_manual_section(
    name: str,
    sector: str,
    ox: float,
    oy: float,
    az: float,
    len_up: float,
    len_down: float,
) -> SectionLine:
    """Build a SectionLine from manual inputs."""
    return SectionLine(
        name=name, origin=np.array([ox, oy]),
        azimuth=az, length=len_up + len_down, sector=sector,
        length_up=len_up, length_down=len_down)


def compute_manual_azimuth(
    mesh_design,
    ox: float,
    oy: float,
    auto_detect: bool,
) -> Optional[float]:
    """Return the local azimuth if auto_detect is True, otherwise None."""
    if auto_detect:
        return compute_local_azimuth(mesh_design, np.array([ox, oy]))
    return None


def generate_auto_sections(
    mesh_design,
    start: np.ndarray,
    end: np.ndarray,
    n: int,
    az_method: str,
    fixed_az: float,
    len_up: float,
    len_down: float,
    sector: str,
) -> List[SectionLine]:
    """Generate evenly spaced sections along a crest/evaluation line."""
    gen_az = None
    if az_method == "Fijo":
        gen_az = fixed_az
    elif az_method == "Auto (pendiente local - Ruidoso)":
        gen_az = 0.0

    sections = generate_sections_along_crest(
        mesh_design, start, end, n, gen_az, len_up + len_down, sector,
        length_up=len_up, length_down=len_down)

    if az_method == "Auto (pendiente local - Ruidoso)":
        for sec in sections:
            sec.azimuth = compute_local_azimuth(mesh_design, sec.origin)
    return sections


def sections_to_rows(sections: List[SectionLine], pending_names: set) -> List[dict]:
    """Convert SectionLine objects into display rows."""
    rows = []
    for s in sections:
        length_up = getattr(s, 'length_up', None)
        length_down = getattr(s, 'length_down', None)
        rows.append({
            "Estado": "⚠ Pendiente" if s.name in pending_names else "Aplicada",
            "Nombre": s.name,
            "Archivo": getattr(s, 'file_name', ''),
            "Sector": s.sector,
            "Origen X": f"{s.origin[0]:.1f}",
            "Origen Y": f"{s.origin[1]:.1f}",
            "Azimut (°)": f"{s.azimuth:.1f}",
            "Long. Arriba (m)": (
                f"{length_up:.1f}" if length_up is not None else f"{s.length/2:.1f}"),
            "Long. Abajo (m)": (
                f"{length_down:.1f}" if length_down is not None else f"{s.length/2:.1f}"),
            "Longitud Total (m)": f"{s.length:.1f}",
        })
    return rows


def get_plan_view_vertices(mesh, max_points: int = 5000) -> np.ndarray:
    """Subsample mesh vertices for a plan-view Plotly scatter."""
    verts = mesh.vertices
    step_v = max(1, len(verts) // max_points)
    return verts[::step_v]


def cut_both_surfaces(mesh_design, mesh_topo, section) -> tuple:
    """Thin wrapper around core.section_cutter.cut_both_surfaces."""
    from core.section_cutter import cut_both_surfaces as _cut_both
    return _cut_both(mesh_design, mesh_topo, section)
