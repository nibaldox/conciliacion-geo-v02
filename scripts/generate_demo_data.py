"""
Generate the synthetic demo data for the React frontend.

Produces a coherent dataset (design + as-built pit meshes, sample
sections, and pre-computed comparison results) so visitors to the
GitHub Pages site can interact with the app without uploading
anything.

Outputs (under web/public/demo/):
- design.stl:     synthetic pit design (no noise)
- topo.stl:       synthetic pit as-built (noise std 0.3m)
- crest.dxf:      sample polyline of 5 section origins
- precomputed.json: extracted parameters + comparison results for
                    the sample data, used by the Results/Dashboard
                    tabs in demo mode
- README.md:      human-readable description of the synthetic data

The meshes use the SAME geometry as the test fixtures
(tests/conftest.py::create_pit_surface) so what visitors see in
demo mode matches what pytest sees. Mesh resolution is lower (60x60
vs 100x100) to keep download size small — typically ~150 KB per STL.

Run:  python scripts/generate_demo_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import trimesh

# Re-use the canonical test fixture so demo data and tests stay in sync.
_REPO = Path(__file__).resolve().parent.parent
# Both the project root (for `core` imports) and `tests/` (for
# `conftest.create_pit_surface`) need to be on sys.path.
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests"))
from conftest import create_pit_surface  # type: ignore  # noqa: E402

# Re-use the actual production pipeline.
from core import cut_both_surfaces, extract_parameters, compare_design_vs_asbuilt
from core.section_cutter import SectionLine


# ── Output paths ────────────────────────────────────────────────────
OUT_DIR = _REPO / "web" / "public" / "demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Synthetic pit geometry (matches test fixtures) ─────────────────
MESH_RES = 60          # 60×60 grid = 3600 vertices (vs 100×100 in tests)
BENCH_HEIGHT = 15.0
BERM_WIDTH = 9.0
FACE_ANGLE = 70.0
N_BENCHES = 4
CREST_ELEV = 3900.0
NOISE_STD = 0.3        # metres — realistic for survey-grade topography


# ── 1. Generate meshes ─────────────────────────────────────────────

def make_meshes() -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    print("→ generating design mesh (no noise)…")
    design = create_pit_surface(
        nx=MESH_RES, ny=MESH_RES,
        bench_height=BENCH_HEIGHT, berm_width=BERM_WIDTH,
        face_angle_deg=FACE_ANGLE, n_benches=N_BENCHES,
        crest_elevation=CREST_ELEV, noise_std=0.0,
    )
    print("→ generating as-built mesh (noise=%.1fm)… " % NOISE_STD)
    topo = create_pit_surface(
        nx=MESH_RES, ny=MESH_RES,
        bench_height=BENCH_HEIGHT, berm_width=BERM_WIDTH,
        face_angle_deg=FACE_ANGLE, n_benches=N_BENCHES,
        crest_elevation=CREST_ELEV, noise_std=NOISE_STD,
    )
    return design, topo


# ── 2. Generate sample sections ────────────────────────────────────

def make_sections(design_mesh: trimesh.Trimesh) -> list[SectionLine]:
    """5 perpendicular sections along an East-West crest at y=250m."""
    return [
        SectionLine(name=f"DEMO-S{i+1:02d}", origin=np.array([100.0 + i * 75.0, 250.0]),
                    azimuth=0.0, length=400.0, sector="Demo")
        for i in range(5)
    ]


# ── 3. Run the real pipeline ───────────────────────────────────────

def run_pipeline(design: trimesh.Trimesh, topo: trimesh.Trimesh,
                 sections: list[SectionLine]) -> dict:
    """Cut + extract + compare. Returns a JSON-serialisable dict.

    The output includes:
      - the actual 3D mesh vertices (for the CesiumJS 3D viewer and
        the Plotly plan view, which both need (x, y, z) points on the
        mesh surface, NOT the 2D profile arrays);
      - the per-section cut profiles (for the per-section chart tab);
      - pre-computed comparison results (for the Results table).
    """
    tolerances = {
        "bench_height": {"neg": 1.0, "pos": 1.5},
        "face_angle": {"neg": 5.0, "pos": 5.0},
        "berm_width": {"min": 6.0},
        "inter_ramp_angle": {"neg": 3.0, "pos": 2.0},
        "overall_angle": {"neg": 2.0, "pos": 2.0},
    }

    bench_payloads = []
    comparison_results = []

    for sec in sections:
        pd_prof, pt_prof = cut_both_surfaces(design, topo, sec)
        if pd_prof is None or pt_prof is None:
            print(f"  {sec.name}: SKIP (no intersection)")
            continue
        p_d = extract_parameters(pd_prof.distances, pd_prof.elevations, sec.name, sec.sector)
        p_t = extract_parameters(pt_prof.distances, pt_prof.elevations, sec.name, sec.sector)
        comps = compare_design_vs_asbuilt(p_d, p_t, tolerances)
        comparison_results.extend(comps)
        from core.param_extractor import build_reconciled_profile
        rd, re_ = build_reconciled_profile(p_t.benches) if p_t.benches else (np.array([]), np.array([]))
        bench_payloads.append({
            "section_name": sec.name,
            "sector": sec.sector,
            "origin": sec.origin.tolist(),
            "azimuth": sec.azimuth,
            "design_profile": {
                "distances": pd_prof.distances.tolist(),
                "elevations": pd_prof.elevations.tolist(),
            },
            "topo_profile": {
                "distances": pt_prof.distances.tolist(),
                "elevations": pt_prof.elevations.tolist(),
            },
            "reconciled_topo": {
                "distances": rd.tolist() if len(rd) else [],
                "elevations": re_.tolist() if len(re_) else [],
            },
            "benches_topo": [
                {
                    "bench_number": b.bench_number,
                    "crest_elevation": b.crest_elevation,
                    "crest_distance": b.crest_distance,
                    "toe_elevation": b.toe_elevation,
                    "toe_distance": b.toe_distance,
                    "bench_height": b.bench_height,
                    "face_angle": b.face_angle,
                    "berm_width": b.berm_width,
                    "is_ramp": b.is_ramp,
                }
                for b in p_t.benches
            ],
        })

    # Drop non-serialisable objects
    safe_comparisons = []
    for c in comparison_results:
        safe_comparisons.append({k: v for k, v in c.items() if k not in ("bench_design", "bench_real")})

    match = [c for c in safe_comparisons if c["type"] == "MATCH"]
    summary = {
        "n_sections": len(sections),
        "n_comparisons": len(safe_comparisons),
        "n_match": len(match),
        "compliance": {},
    }
    for key, label in [("height_status", "Altura de banco"),
                       ("angle_status", "Ángulo de cara"),
                       ("berm_status", "Ancho de berma")]:
        n_ok = sum(1 for c in match if c.get(key) == "CUMPLE")
        n_warn = sum(1 for c in match if c.get(key) == "FUERA DE TOLERANCIA")
        n_nok = sum(1 for c in match if c.get(key) == "NO CUMPLE")
        total = len(match) or 1
        summary["compliance"][key] = {
            "label": label,
            "cumple": n_ok,
            "fuera": n_warn,
            "no_cumple": n_nok,
            "pct": round(n_ok / total * 100, 1) if total else 0.0,
        }

    # 3D mesh vertices (what the CesiumJS viewer and Plotly plan view
    # need). Subsample dense meshes so the bundle stays small.
    def _vertices_payload(m: trimesh.Trimesh, max_points: int = 6000) -> dict:
        v = m.vertices
        if len(v) > max_points:
            stride = max(1, len(v) // max_points)
            v = v[::stride]
        return {
            "x": v[:, 0].tolist(),
            "y": v[:, 1].tolist(),
            "z": v[:, 2].tolist(),
        }

    return {
        "summary": summary,
        "vertices": {
            "design": _vertices_payload(design),
            "topo": _vertices_payload(topo),
        },
        "sections": bench_payloads,
        "comparisons": safe_comparisons,
    }


# ── 4. Generate sample DXF polyline (the crest) ────────────────────

def write_crest_dxf(path: Path, sections: list[SectionLine]) -> None:
    """Write the section origins as a LWPOLYLINE in a minimal DXF."""
    try:
        import ezdxf
    except ImportError:
        print("  ezdxf not installed, skipping DXF export")
        return
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    pts = [(float(s.origin[0]), float(s.origin[1])) for s in sections]
    msp.add_lwpolyline(pts, close=False)
    doc.saveas(str(path))


# ── 5. Main ────────────────────────────────────────────────────────

def main() -> None:
    print("=== Conciliación Geotécnica — demo data generator ===")

    design, topo = make_meshes()

    design_path = OUT_DIR / "design.stl"
    topo_path = OUT_DIR / "topo.stl"
    design.export(str(design_path))
    topo.export(str(topo_path))
    print(f"✓ wrote {design_path.relative_to(_REPO)} ({design_path.stat().st_size // 1024} KB)")
    print(f"✓ wrote {topo_path.relative_to(_REPO)}  ({topo_path.stat().st_size // 1024} KB)")

    sections = make_sections(design)
    write_crest_dxf(OUT_DIR / "crest.dxf", sections)
    dxf_path = OUT_DIR / "crest.dxf"
    if dxf_path.exists():
        print(f"✓ wrote {dxf_path.relative_to(_REPO)}  ({dxf_path.stat().st_size} B)")

    print("→ running full pipeline to pre-compute results…")
    payload = run_pipeline(design, topo, sections)

    # Strip bulky profile arrays if total payload > 1 MB; keep enough
    # for the demo dashboards to look right.
    json_blob = json.dumps(payload, separators=(",", ":"))
    if len(json_blob) > 2_000_000:
        # Keep only the first 200 points of each profile to stay under 2 MB
        for sec in payload["sections"]:
            for key in ("design_profile", "topo_profile"):
                p = sec[key]
                p["distances"] = p["distances"][::5]
                p["elevations"] = p["elevations"][::5]
        json_blob = json.dumps(payload, separators=(",", ":"))

    pre_path = OUT_DIR / "precomputed.json"
    pre_path.write_text(json_blob)
    print(f"✓ wrote {pre_path.relative_to(_REPO)}  ({pre_path.stat().st_size // 1024} KB)")
    print(f"   {payload['summary']['n_sections']} sections, "
          f"{payload['summary']['n_comparisons']} comparisons, "
          f"{payload['summary']['n_match']} matches")

    # Human-readable README
    readme = OUT_DIR / "README.md"
    readme.write_text(f"""# Demo data

Synthetic pit mine dataset used by the React frontend's **demo mode**.
Generated by `scripts/generate_demo_data.py`. The geometry is the same
as the test fixtures (`tests/conftest.py::create_pit_surface`) so what
visitors see in the browser matches what pytest asserts.

## Contents

| File | Size | Description |
|---|---|---|
| `design.stl` | ~{design_path.stat().st_size // 1024} KB | Pit design surface, no noise. Conical pit with 4 benches at {BENCH_HEIGHT} m height, {BERM_WIDTH} m berms, {FACE_ANGLE}° face angle. |
| `topo.stl`   | ~{topo_path.stat().st_size // 1024} KB | As-built topography, Gaussian noise σ = {NOISE_STD} m on the design grid. |
| `crest.dxf` | tiny | A 5-vertex LWPOLYLINE showing the section origins. |
| `precomputed.json` | ~{pre_path.stat().st_size // 1024} KB | Output of running the full cut → extract → compare pipeline over the sample data, with safe-for-JSON comparison rows. |

## When to regenerate

Run `python scripts/generate_demo_data.py` whenever:
- The synthetic geometry changes (resolution, bench count, etc.)
- The pipeline's output schema changes (new fields in `BenchParams`,
  new keys in `ComparisonResult`)
- A new sample section line is added

Commit the regenerated `web/public/demo/` files. The build step
copies the whole `public/` tree to the dist root.
""")
    print(f"✓ wrote {readme.relative_to(_REPO)}")
    print("\nDone. Files are ready to be served as static assets.")


if __name__ == "__main__":
    main()
