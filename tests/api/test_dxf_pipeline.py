import io
import zipfile

import ezdxf
import numpy as np
import pytest
import trimesh

import api.database as db


def _bench_surface(shift: float = 0.0) -> trimesh.Trimesh:
    profile = [(-10, 30), (0, 30), (10, 15), (20, 15), (30, 0), (50, 0)]
    vertices = [(x + shift, y, z) for x, z in profile for y in (-10, 10)]
    faces = []
    for index in range(len(profile) - 1):
        start = index * 2
        faces.extend([(start, start + 1, start + 2), (start + 1, start + 3, start + 2)])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _surface_dxf(mesh: trimesh.Trimesh, representation: str) -> bytes:
    doc = ezdxf.new("R2010")
    doc.units = 4
    doc.layers.new("TERRENO")
    doc.layers.new("OTRA_SUPERFICIE")
    vertices = np.asarray(mesh.vertices) * 1000.0
    if representation == "3DFACE":
        for face in mesh.faces:
            doc.modelspace().add_3dface(vertices[face], dxfattribs={"layer": "TERRENO"})
    elif representation == "POLYFACE":
        polyface = doc.modelspace().add_polyface(dxfattribs={"layer": "TERRENO"})
        polyface.append_faces([vertices[face] for face in mesh.faces])
    else:
        block = doc.blocks.new("SUPERFICIE")
        entity = block.add_mesh()
        with entity.edit_data() as data:
            data.vertices = vertices.tolist()
            data.faces = mesh.faces.tolist()
        doc.modelspace().add_blockref("SUPERFICIE", (0, 0, 0), dxfattribs={"layer": "TERRENO"})
    doc.modelspace().add_3dface(
        [(1000000, 0, 999000), (1001000, 0, 999000), (1000000, 1000, 999000)],
        dxfattribs={"layer": "OTRA_SUPERFICIE"},
    )
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _upload_surface(client, headers: dict, role: str, representation: str) -> str:
    mesh = _bench_surface(0.5 if role == "topo" else 0.0)
    if representation == "STL":
        response = client.post(
            "/api/v1/meshes/upload",
            files={"file": (f"{role}.stl", mesh.export(file_type="stl"), "application/octet-stream")},
            data={"type": role},
            headers=headers,
        )
    else:
        inspected = client.post(
            "/api/v1/meshes/dxf/inspect",
            files={"file": (f"{role}.dxf", _surface_dxf(mesh, representation), "application/dxf")},
            data={"type": role},
            headers=headers,
        )
        assert inspected.status_code == 200, inspected.text
        assert {layer["name"] for layer in inspected.json()["layers"]} == {"TERRENO", "OTRA_SUPERFICIE"}
        response = client.post(
            "/api/v1/meshes/dxf/confirm",
            json={"upload_id": inspected.json()["upload_id"], "layers": ["TERRENO"], "units": 4},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["import_report"]["scale_factor"] == pytest.approx(0.001)
    assert response.status_code == 200, response.text
    assert response.json()["n_faces"] == len(mesh.faces)
    return response.json()["mesh_id"]


def _run_pipeline(client, headers: dict, sector: str) -> dict:
    response = client.post(
        "/api/v1/sections/manual",
        json=[
            {"name": f"DXF-{index}", "origin": [20.0, y], "azimuth": 90, "length": 60, "sector": sector}
            for index, y in enumerate((-5, 5), start=1)
        ],
        headers=headers,
    )
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/process", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "complete"
    assert response.json()["total_results"] > 0
    profile = client.get("/api/v1/process/profiles/0", headers=headers)
    assert profile.status_code == 200, profile.text
    return profile.json()


@pytest.mark.parametrize(
    ("design_format", "topo_format", "sector"),
    [("3DFACE", "POLYFACE", ""), ("MESH", "STL", "A"), ("STL", "MESH", "")],
)
def test_dxf_surfaces_match_stl_pipeline_after_cache_reload(client, design_format, topo_format, sector):
    dxf_headers = {"X-Session-ID": "dxf-pipeline"}
    baseline_headers = {"X-Session-ID": "stl-baseline"}
    design_id = _upload_surface(client, dxf_headers, "design", design_format)
    topo_id = _upload_surface(client, dxf_headers, "topo", topo_format)
    _upload_surface(client, baseline_headers, "design", "STL")
    _upload_surface(client, baseline_headers, "topo", "STL")
    db.get_trimesh_by_id.cache_clear()
    imported = _run_pipeline(client, dxf_headers, sector)
    baseline = _run_pipeline(client, baseline_headers, sector)
    for role in ("design", "topo"):
        assert imported[role] is not None
        for key in ("distances", "elevations"):
            np.testing.assert_allclose(imported[role][key], baseline[role][key], atol=1e-6, rtol=0)
    dxf_results = client.get("/api/v1/process/results", headers=dxf_headers).json()
    stl_results = client.get("/api/v1/process/results", headers=baseline_headers).json()
    assert len(dxf_results) == len(stl_results)
    for imported_row, baseline_row in zip(dxf_results, stl_results):
        for key in ("height_design", "height_real", "angle_design", "angle_real", "berm_design", "berm_real"):
            assert imported_row[key] == pytest.approx(baseline_row[key], abs=1e-6)
    heatmap = client.get(
        f"/api/v1/meshes/{topo_id}/horizontal-deviation",
        params={"design_mesh_id": design_id, "sector": sector, "longitudinal_step": 4, "vertical_step": 2},
        headers=dxf_headers,
    )
    assert heatmap.status_code == 200, heatmap.text
    assert heatmap.json()["summary"]["measured"] > 0
    measurements = [cell["deviation_m"] for cell in heatmap.json()["cells"] if cell["deviation_m"] is not None]
    assert np.max(np.abs(measurements)) == pytest.approx(0.5, abs=1e-6)


def test_dxf_processed_surfaces_export_all_formats(client):
    headers = {"X-Session-ID": "dxf-exports"}
    _upload_surface(client, headers, "design", "POLYFACE")
    _upload_surface(client, headers, "topo", "MESH")
    _run_pipeline(client, headers, "")
    for export_type in ("excel", "word", "pdf", "dxf"):
        response = client.get(f"/api/v1/export/{export_type}", headers=headers)
        assert response.status_code == 200, f"{export_type}: {response.text[:300]}"
        if export_type in ("excel", "word"):
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                assert archive.testzip() is None
                assert "[Content_Types].xml" in archive.namelist()
        elif export_type == "pdf":
            assert response.content.startswith(b"%PDF-")
        else:
            doc = ezdxf.read(io.StringIO(response.content.decode("utf-8"), newline=None))
            assert len(doc.modelspace().query("POLYLINE")) > 0, [(entity.dxftype(), entity.dxf.layer) for entity in doc.modelspace()]
