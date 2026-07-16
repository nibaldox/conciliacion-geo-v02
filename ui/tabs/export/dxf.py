"""Pure DXF generation for export."""
import os
import tempfile
from typing import Any, Optional

import ezdxf

from core.param_extractor import build_reconciled_profile
from core.section_cutter import azimuth_to_direction
from ui.tabs.export.common import (
    _build_section_status_map,
    _create_dxf_layers,
    _profile_to_3d,
)


def _draw_3d_polyline(msp, pts, layer: str) -> None:
    msp.add_polyline3d(pts, dxfattribs={'layer': layer})


def _write_section_to_dxf(msp, sec, p_d, p_t, pd_prof, pt_prof, section_status) -> None:
    safe_name = sec.name.replace("/", "_").replace("\\", "_")
    status = section_status.get(sec.name, 'CUMPLE')
    layer_suffix = {'NO CUMPLE': 'NO_CUMPLE', 'FUERA DE TOLERANCIA': 'FUERA_TOL'}.get(
        status, 'CUMPLE')

    direction = azimuth_to_direction(sec.azimuth)
    ox, oy = sec.origin[0], sec.origin[1]

    design_3d = _profile_to_3d(pd_prof.distances, pd_prof.elevations, ox, oy, direction)
    if len(design_3d) > 1:
        _draw_3d_polyline(msp, design_3d, f'DISEÑO_{layer_suffix}')

    topo_3d = _profile_to_3d(pt_prof.distances, pt_prof.elevations, ox, oy, direction)
    if len(topo_3d) > 1:
        _draw_3d_polyline(msp, topo_3d, f'TOPO_{layer_suffix}')

    if p_d and p_d.benches:
        rd, re = build_reconciled_profile(p_d.benches)
        if len(rd) > 0:
            conc_d = _profile_to_3d(rd, re, ox, oy, direction)
            if len(conc_d) > 1:
                _draw_3d_polyline(msp, conc_d, 'CONCILIADO_DISEÑO')

    if p_t and p_t.benches:
        rt, ret = build_reconciled_profile(p_t.benches)
        if len(rt) > 0:
            conc_t = _profile_to_3d(rt, ret, ox, oy, direction)
            if len(conc_t) > 1:
                _draw_3d_polyline(msp, conc_t, 'CONCILIADO_TOPO')

    mid_z = float(max(pd_prof.elevations.max(), pt_prof.elevations.max())) + 3
    msp.add_text(
        f"{safe_name} [{status}]",
        dxfattribs={'height': 2.0, 'layer': 'ETIQUETAS', 'insert': (ox, oy, mid_z)})


def build_dxf(
    sections: list,
    profile_pairs: dict[str, tuple],
    design_params_map: dict[str, Any],
    topo_params_map: dict[str, Any],
    comparison_results: Optional[list] = None,
) -> tuple[bytes, int]:
    """Generate a DXF with 3D polylines and return its bytes plus section count."""
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()

    _create_dxf_layers(doc)
    section_status = _build_section_status_map(comparison_results or [])

    n_exported = 0
    for sec in sections:
        pair = profile_pairs.get(sec.name)
        if pair is None:
            continue
        pd_prof, pt_prof = pair
        if pd_prof is None or pt_prof is None:
            continue
        p_d = design_params_map.get(sec.name)
        p_t = topo_params_map.get(sec.name)
        _write_section_to_dxf(
            msp, sec, p_d, p_t, pd_prof, pt_prof, section_status)
        n_exported += 1

    tmp_path = os.path.join(tempfile.gettempdir(), "Perfiles_3D.dxf")
    doc.saveas(tmp_path)

    with open(tmp_path, "rb") as f:
        dxf_bytes = f.read()

    return dxf_bytes, n_exported
