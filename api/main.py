"""
FastAPI application for Geotechnical Reconciliation.
Wraps the existing core/ module as a REST API.
"""

import os
import sys
import uuid
import tempfile
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import numpy as np

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mesh_handler import load_mesh, load_dxf_polyline
from core.section_cutter import (
    SectionLine, cut_both_surfaces, cut_mesh_with_section,
    azimuth_to_direction,
)
from core.param_extractor import (
    extract_parameters, compare_design_vs_asbuilt, build_reconciled_profile,
    BenchParams, ExtractionResult,
)

app = FastAPI(
    title="Conciliación Geotécnica API",
    version="2.0.0",
    description="API para análisis de conciliación geotécnica: Diseño vs As-Built",
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session store (one session at a time for simplicity)
# ---------------------------------------------------------------------------

class SessionStore:
    """Holds loaded meshes, sections, and results for the active session."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.mesh_design = None
        self.mesh_topo = None
        self.sections: List[SectionLine] = []
        self.params_design: List[ExtractionResult] = []
        self.params_topo: List[ExtractionResult] = []
        self.comparison_results: List[Dict] = []
        self.tolerances: Dict = {}
        self.settings: Dict = {
            "resolution": 0.5,
            "face_threshold": 40.0,
            "berm_threshold": 20.0,
        }


store = SessionStore()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "has_design": store.mesh_design is not None,
        "has_topo": store.mesh_topo is not None,
        "n_sections": len(store.sections),
        "n_results": len(store.comparison_results),
    }


# ---------------------------------------------------------------------------
# Upload Meshes
# ---------------------------------------------------------------------------

@app.post("/api/upload/design")
async def upload_design(file: UploadFile = File(...)):
    """Upload the design surface mesh (STL)."""
    tmp = _save_temp(file)
    try:
        store.mesh_design = load_mesh(tmp)
    except Exception as e:
        raise HTTPException(400, f"Error loading design mesh: {e}")
    finally:
        os.unlink(tmp)
    return {"message": "Design mesh loaded", "vertices": len(store.mesh_design.vertices)}


@app.post("/api/upload/topo")
async def upload_topo(file: UploadFile = File(...)):
    """Upload the topography (as-built) surface mesh (STL)."""
    tmp = _save_temp(file)
    try:
        store.mesh_topo = load_mesh(tmp)
    except Exception as e:
        raise HTTPException(400, f"Error loading topo mesh: {e}")
    finally:
        os.unlink(tmp)
    return {"message": "Topo mesh loaded", "vertices": len(store.mesh_topo.vertices)}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

@app.post("/api/sections/load")
async def load_sections(file: UploadFile = File(...)):
    """Load sections from a JSON file."""
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")

    sections = []
    for s in data.get("sections", data if isinstance(data, list) else []):
        sec = SectionLine(
            name=s["name"],
            origin=np.array(s["origin"]),
            azimuth=s["azimuth"],
            length=s["length"],
            sector=s.get("sector", ""),
        )
        sections.append(sec)

    store.sections = sections
    return {"message": f"{len(sections)} sections loaded"}


@app.get("/api/sections")
def get_sections():
    """Get all loaded sections."""
    return [
        {
            "name": s.name,
            "origin": s.origin.tolist(),
            "azimuth": s.azimuth,
            "length": s.length,
            "sector": s.sector,
        }
        for s in store.sections
    ]


# ---------------------------------------------------------------------------
# Settings / Tolerances
# ---------------------------------------------------------------------------

@app.post("/api/settings")
def update_settings(settings: Dict[str, Any]):
    """Update extraction settings."""
    store.settings.update(settings)
    return {"message": "Settings updated", "settings": store.settings}


@app.post("/api/tolerances")
def update_tolerances(tolerances: Dict[str, Any]):
    """Update comparison tolerances."""
    store.tolerances = tolerances
    return {"message": "Tolerances updated"}


# ---------------------------------------------------------------------------
# Process: Cut profiles + extract params + compare
# ---------------------------------------------------------------------------

@app.post("/api/process")
def process_all():
    """Cut all sections, extract parameters, and compare."""
    if store.mesh_design is None or store.mesh_topo is None:
        raise HTTPException(400, "Upload both meshes first")
    if not store.sections:
        raise HTTPException(400, "Load sections first")

    res = store.settings.get("resolution", 0.5)
    ft = store.settings.get("face_threshold", 40.0)
    bt = store.settings.get("berm_threshold", 20.0)

    store.params_design = []
    store.params_topo = []
    store.comparison_results = []

    for sec in store.sections:
        pd_prof, pt_prof = cut_both_surfaces(
            store.mesh_design, store.mesh_topo, sec
        )
        if pd_prof and pt_prof:
            p_d = extract_parameters(
                pd_prof.distances, pd_prof.elevations,
                sec.name, sec.sector, res, ft, bt,
            )
            p_t = extract_parameters(
                pt_prof.distances, pt_prof.elevations,
                sec.name, sec.sector, res, ft, bt,
            )
            store.params_design.append(p_d)
            store.params_topo.append(p_t)

            comps = compare_design_vs_asbuilt(
                p_d, p_t, store.tolerances
            )
            store.comparison_results.extend(comps)
        else:
            # Empty placeholder so indices stay aligned
            store.params_design.append(ExtractionResult(sec.name, sec.sector))
            store.params_topo.append(ExtractionResult(sec.name, sec.sector))

    return {
        "message": "Processing complete",
        "n_sections": len(store.sections),
        "n_results": len(store.comparison_results),
    }


# ---------------------------------------------------------------------------
# Profile data (for charts)
# ---------------------------------------------------------------------------

@app.get("/api/profiles/{section_index}")
def get_profile(section_index: int):
    """Get profile data for a single section including reconciled profiles."""
    if section_index >= len(store.sections):
        raise HTTPException(404, "Section index out of range")

    sec = store.sections[section_index]
    pd_prof, pt_prof = cut_both_surfaces(
        store.mesh_design, store.mesh_topo, sec
    )

    result = {
        "section_name": sec.name,
        "sector": sec.sector,
        "origin": sec.origin.tolist(),
        "azimuth": sec.azimuth,
    }

    if pd_prof:
        result["design"] = {
            "distances": pd_prof.distances.tolist(),
            "elevations": pd_prof.elevations.tolist(),
        }
    if pt_prof:
        result["topo"] = {
            "distances": pt_prof.distances.tolist(),
            "elevations": pt_prof.elevations.tolist(),
        }

    # Reconciled profiles
    if section_index < len(store.params_design):
        rd, re = build_reconciled_profile(store.params_design[section_index].benches)
        result["reconciled_design"] = {
            "distances": rd.tolist() if len(rd) > 0 else [],
            "elevations": re.tolist() if len(re) > 0 else [],
        }

    if section_index < len(store.params_topo):
        p_topo = store.params_topo[section_index]
        rt, ret = build_reconciled_profile(p_topo.benches)
        result["reconciled_topo"] = {
            "distances": rt.tolist() if len(rt) > 0 else [],
            "elevations": ret.tolist() if len(ret) > 0 else [],
        }
        # Send bench data for interactive editing
        result["benches_topo"] = [
            {
                "bench_number": b.bench_number,
                "crest_distance": b.crest_distance,
                "crest_elevation": b.crest_elevation,
                "toe_distance": b.toe_distance,
                "toe_elevation": b.toe_elevation,
                "bench_height": b.bench_height,
                "face_angle": b.face_angle,
                "berm_width": b.berm_width,
            }
            for b in p_topo.benches
        ]

    return result


# ---------------------------------------------------------------------------
# Interactive: Update reconciled profile (drag & drop)
# ---------------------------------------------------------------------------

@app.put("/api/reconciled/{section_index}")
def update_reconciled(section_index: int, benches: List[Dict[str, float]]):
    """
    Update the reconciled profile for a section after user drag edits.
    Receives updated crest/toe positions and recalculates parameters.
    """
    if section_index >= len(store.params_topo):
        raise HTTPException(404, "Section index out of range")

    p_topo = store.params_topo[section_index]

    # Update bench positions from user edits
    for i, bench_update in enumerate(benches):
        if i < len(p_topo.benches):
            b = p_topo.benches[i]
            # Update positions
            if "crest_distance" in bench_update:
                b.crest_distance = bench_update["crest_distance"]
            if "crest_elevation" in bench_update:
                b.crest_elevation = bench_update["crest_elevation"]
            if "toe_distance" in bench_update:
                b.toe_distance = bench_update["toe_distance"]
            if "toe_elevation" in bench_update:
                b.toe_elevation = bench_update["toe_elevation"]

            # Recalculate derived values
            b.bench_height = abs(b.crest_elevation - b.toe_elevation)
            dx = b.toe_distance - b.crest_distance
            dz = b.crest_elevation - b.toe_elevation
            if abs(dx) > 0.01:
                b.face_angle = abs(np.degrees(np.arctan2(dz, abs(dx))))
            else:
                b.face_angle = 90.0

    # Recalculate berm widths
    for i in range(len(p_topo.benches) - 1):
        current = p_topo.benches[i]
        next_b = p_topo.benches[i + 1]
        current.berm_width = abs(next_b.crest_distance - current.toe_distance)

    # Re-run comparison for this section
    if section_index < len(store.params_design):
        p_design = store.params_design[section_index]
        # Remove old comparisons for this section
        sec_name = store.sections[section_index].name
        store.comparison_results = [
            c for c in store.comparison_results if c.get("section") != sec_name
        ]
        # Add new comparisons
        new_comps = compare_design_vs_asbuilt(p_design, p_topo, store.tolerances)
        store.comparison_results.extend(new_comps)

    # Return updated profile
    rd, re = build_reconciled_profile(p_topo.benches)
    return {
        "reconciled_topo": {
            "distances": rd.tolist() if len(rd) > 0 else [],
            "elevations": re.tolist() if len(re) > 0 else [],
        },
        "benches": [
            {
                "bench_number": b.bench_number,
                "crest_distance": b.crest_distance,
                "crest_elevation": b.crest_elevation,
                "toe_distance": b.toe_distance,
                "toe_elevation": b.toe_elevation,
                "bench_height": round(b.bench_height, 2),
                "face_angle": round(b.face_angle, 1),
                "berm_width": round(b.berm_width, 2),
            }
            for b in p_topo.benches
        ],
    }


# ---------------------------------------------------------------------------
# Comparison results
# ---------------------------------------------------------------------------

@app.get("/api/results")
def get_results():
    """Get all comparison results."""
    return store.comparison_results


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

@app.get("/api/export/excel")
def export_excel():
    """Export results to Excel."""
    if not store.comparison_results:
        raise HTTPException(400, "No results to export")

    from core.excel_writer import export_results

    tmp = os.path.join(tempfile.gettempdir(), "conciliacion.xlsx")
    export_results(store.comparison_results, tmp, store.tolerances)

    return FileResponse(
        tmp,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Conciliacion_Geotecnica.xlsx",
    )


@app.get("/api/export/dxf")
def export_dxf():
    """Export profiles as 3D DXF with compliance layers."""
    if store.mesh_design is None or store.mesh_topo is None:
        raise HTTPException(400, "Meshes not loaded")

    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Layers
    doc.layers.add("DISEÑO_CUMPLE", color=3)
    doc.layers.add("DISEÑO_NO_CUMPLE", color=1)
    doc.layers.add("DISEÑO_FUERA_TOL", color=2)
    doc.layers.add("TOPO_CUMPLE", color=3)
    doc.layers.add("TOPO_NO_CUMPLE", color=1)
    doc.layers.add("TOPO_FUERA_TOL", color=2)
    doc.layers.add("CONCILIADO_DISEÑO", color=5)
    doc.layers.add("CONCILIADO_TOPO", color=6)
    doc.layers.add("ETIQUETAS", color=7)

    # Per-section compliance
    section_status = {}
    for c in store.comparison_results:
        sec = c.get("section", "")
        statuses = [c.get("height_status", ""), c.get("angle_status", ""), c.get("berm_status", "")]
        if sec not in section_status:
            section_status[sec] = "CUMPLE"
        if "NO CUMPLE" in statuses:
            section_status[sec] = "NO CUMPLE"
        elif "FUERA DE TOLERANCIA" in statuses and section_status[sec] != "NO CUMPLE":
            section_status[sec] = "FUERA DE TOLERANCIA"

    n_exported = 0
    for i, sec in enumerate(store.sections):
        pd_prof, pt_prof = cut_both_surfaces(store.mesh_design, store.mesh_topo, sec)
        if not (pd_prof and pt_prof):
            continue

        direction = azimuth_to_direction(sec.azimuth)
        ox, oy = sec.origin[0], sec.origin[1]

        status = section_status.get(sec.name, "CUMPLE")
        suffix = {"NO CUMPLE": "NO_CUMPLE", "FUERA DE TOLERANCIA": "FUERA_TOL"}.get(status, "CUMPLE")

        def to_3d(dists, elevs):
            return [(ox + d * direction[0], oy + d * direction[1], float(e))
                    for d, e in zip(dists, elevs)]

        def draw_lines(pts, layer):
            for j in range(len(pts) - 1):
                msp.add_line(pts[j], pts[j + 1], dxfattribs={"layer": layer})

        # Design + Topo profiles
        d3d = to_3d(pd_prof.distances, pd_prof.elevations)
        t3d = to_3d(pt_prof.distances, pt_prof.elevations)
        if len(d3d) > 1:
            draw_lines(d3d, f"DISEÑO_{suffix}")
        if len(t3d) > 1:
            draw_lines(t3d, f"TOPO_{suffix}")

        # Reconciled profiles
        if i < len(store.params_design) and store.params_design[i].benches:
            rd, re = build_reconciled_profile(store.params_design[i].benches)
            if len(rd) > 0:
                draw_lines(to_3d(rd, re), "CONCILIADO_DISEÑO")
        if i < len(store.params_topo) and store.params_topo[i].benches:
            rt, ret = build_reconciled_profile(store.params_topo[i].benches)
            if len(rt) > 0:
                draw_lines(to_3d(rt, ret), "CONCILIADO_TOPO")

        # Label
        mid_z = float(max(pd_prof.elevations.max(), pt_prof.elevations.max())) + 3
        msp.add_text(
            f"{sec.name} [{status}]",
            dxfattribs={"height": 2.0, "layer": "ETIQUETAS", "insert": (ox, oy, mid_z)},
        )
        n_exported += 1

    tmp = os.path.join(tempfile.gettempdir(), "Perfiles_3D.dxf")
    doc.saveas(tmp)
    return FileResponse(tmp, media_type="application/dxf", filename="Perfiles_3D.dxf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_temp(file: UploadFile) -> str:
    """Save UploadFile to a temp path and return the path."""
    suffix = Path(file.filename or "mesh.stl").suffix
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(file.file.read())
    return tmp
