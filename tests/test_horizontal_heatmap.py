import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

import api.database as db
from api.main import app
from api.routers import meshes
from core import HorizontalFaceGeometry


def _surface(x_values, y_values, elevation):
    vertices = []
    for y in y_values:
        for x in x_values:
            vertices.append((x, y, elevation(x)))
    faces = []
    width = len(x_values)
    for row in range(len(y_values) - 1):
        for column in range(width - 1):
            lower_left = row * width + column
            lower_right = lower_left + 1
            upper_left = lower_left + width
            upper_right = upper_left + 1
            faces.extend((
                (lower_left, lower_right, upper_right),
                (lower_left, upper_right, upper_left),
            ))
    return trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
    )


def _section(name, y, sector="A"):
    return {
        "name": name,
        "origin": [0.0, y],
        "azimuth": 90.0,
        "length": 60.0,
        "sector": sector,
    }


def _prepare_heatmap_session(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "heatmap-origin-test.db")
    db.init_db()
    session_id = db.create_session()
    bounds = {
        "xmin": 0.0,
        "xmax": 60.0,
        "ymin": 0.0,
        "ymax": 140.0,
        "zmin": 80.0,
        "zmax": 110.0,
    }
    topo_id = db.save_mesh(session_id, "topo", "topo.stl", b"mesh", 3, 1, bounds)
    design_id = db.save_mesh(session_id, "design", "design.stl", b"mesh", 3, 1, bounds)
    return session_id, topo_id, design_id


def _stub_heatmap_geometry(monkeypatch):
    profile = (
        np.asarray([0.0, 10.0, 20.0, 30.0, 40.0, 60.0]),
        np.asarray([110.0, 105.0, 100.0, 95.0, 90.0, 80.0]),
    )
    face = HorizontalFaceGeometry(1, 0.0, 110.0, 20.0, 90.0, 20.0)
    monkeypatch.setattr(db, "get_trimesh_by_id", lambda mesh_id: mesh_id)
    monkeypatch.setattr(meshes, "_crop_mesh_to_sections", lambda mesh, sections: mesh)
    monkeypatch.setattr(
        meshes,
        "_profile_data_with_diagnostics",
        lambda mesh, section: (profile, ()),
    )
    monkeypatch.setattr(meshes, "_extract_faces", lambda profile, section, options: {1: face})


@pytest.mark.parametrize(
    ("slope", "intercept", "crest_distance", "toe_distance", "shift", "expected"),
    [
        (-1.0, 100.0, 0.0, 10.0, -8.19, 8.19),
        (-1.0, 100.0, 0.0, 10.0, 8.19, -8.19),
        (1.0, 90.0, 10.0, 0.0, 8.19, 8.19),
        (1.0, 90.0, 10.0, 0.0, -8.19, -8.19),
    ],
)
def test_heatmap_uses_raw_topo_crossing_and_design_face_direction(
    monkeypatch, slope, intercept, crest_distance, toe_distance, shift, expected
):
    x_values = np.linspace(-30.0, 30.0, 61)
    y_values = (-1.0, 3.0)
    design = _surface(x_values, y_values, lambda x: intercept + slope * x)
    topo = _surface(
        x_values,
        y_values,
        lambda x: intercept + slope * (x - shift),
    )
    monkeypatch.setattr(
        db,
        "get_trimesh_by_id",
        lambda mesh_id: {"design": design, "topo": topo}[mesh_id],
    )
    face = HorizontalFaceGeometry(
        bench_number=1,
        crest_distance=crest_distance,
        crest_elevation=100.0,
        toe_distance=toe_distance,
        toe_elevation=90.0,
        bench_height=20.0,
    )
    monkeypatch.setattr(
        meshes,
        "_extract_faces",
        lambda profile, section, options: {1: face},
    )

    payload = meshes._build_horizontal_deviation_payload(
        "topo",
        "design",
        [_section("A-01", 0.0), _section("B-01", 0.5, "B"), _section("A-02", 2.0)],
        "A",
        1,
        2.0,
        4.0,
        {},
    )

    measured = [cell for cell in payload["cells"] if cell["deviation_m"] is not None]
    assert len(measured) == 3
    assert all(cell["deviation_m"] == pytest.approx(expected, abs=0.01) for cell in measured)
    assert {cell["category"] for cell in measured} == {
        "overbreak_severe" if expected > 0 else "underbreak_severe"
    }
    assert max(cell["elevation_m"] for cell in measured) <= 100.0
    assert len(payload["faces"]) == 2 * len(measured)
    assert len(payload["cell_index_by_face"]) == len(payload["faces"])
    assert payload["summary"]["measured"] == len(measured)
    assert payload["summary"]["total"] == len(payload["cells"])
    assert all(cell["unit"] == "m" for cell in measured)
    assert all("no_topo_bench_pairing" in cell["assumptions"] for cell in measured)


def test_ambiguous_raw_topo_crossings_remain_unmeasured_and_have_no_patch(monkeypatch):
    y_values = (-1.0, 3.0)
    first_topo = _surface((0.0, 5.0, 10.0), y_values, lambda x: 100.0 - x)
    second_topo = _surface((20.0, 25.0, 30.0), y_values, lambda x: 120.0 - x)
    design = _surface(
        np.linspace(-30.0, 30.0, 61),
        y_values,
        lambda x: 100.0 - x,
    )
    topo = trimesh.util.concatenate((first_topo, second_topo))
    monkeypatch.setattr(
        db,
        "get_trimesh_by_id",
        lambda mesh_id: {"design": design, "topo": topo}[mesh_id],
    )
    face = HorizontalFaceGeometry(1, 0.0, 100.0, 10.0, 90.0, 20.0)
    monkeypatch.setattr(
        meshes,
        "_extract_faces",
        lambda profile, section, options: {1: face},
    )

    payload = meshes._build_horizontal_deviation_payload(
        "topo",
        "design",
        [_section("A-01", 0.0), _section("A-02", 2.0)],
        "A",
        1,
        2.0,
        4.0,
        {},
    )

    assert payload["cells"]
    assert all(cell["deviation_m"] is None for cell in payload["cells"])
    assert all(cell["category"] == "unmeasured" for cell in payload["cells"])
    assert all("ambiguous" in cell["status"] for cell in payload["cells"])
    assert payload["faces"] == []
    assert payload["summary"]["measured"] == 0
    assert payload["summary"]["total"] == len(payload["cells"])


def test_valid_center_with_missing_topo_corners_does_not_close_surface_hole(monkeypatch):
    x_values = np.linspace(-30.0, 30.0, 61)
    design = _surface(x_values, (-1.0, 3.0), lambda x: 100.0 - x)
    topo = _surface(
        x_values,
        (0.25, 1.75),
        lambda x: 100.0 - (x + 2.0),
    )
    monkeypatch.setattr(
        db,
        "get_trimesh_by_id",
        lambda mesh_id: {"design": design, "topo": topo}[mesh_id],
    )
    face = HorizontalFaceGeometry(1, 0.0, 100.0, 10.0, 90.0, 10.0)
    monkeypatch.setattr(
        meshes,
        "_extract_faces",
        lambda profile, section, options: {1: face},
    )

    payload = meshes._build_horizontal_deviation_payload(
        "topo",
        "design",
        [_section("A-01", 0.0), _section("A-02", 2.0)],
        "A",
        1,
        2.0,
        4.0,
        {},
    )

    assert payload["cells"]
    assert all(cell["deviation_m"] is None for cell in payload["cells"])
    assert all(cell["status"] == "topo_corner_missing" for cell in payload["cells"])
    assert payload["faces"] == []
    assert payload["summary"]["measured"] == 0
    assert payload["summary"]["total"] == len(payload["cells"])


def test_heatmap_midpoint_lookup_uses_same_float_formula_as_station_grid(monkeypatch):
    monkeypatch.setattr(db, "get_trimesh_by_id", lambda mesh_id: mesh_id)
    monkeypatch.setattr(meshes, "_crop_mesh_to_sections", lambda mesh, sections: mesh)
    monkeypatch.setattr(
        meshes,
        "_profile_data_with_diagnostics",
        lambda mesh, section: (
            (np.array([0.0, 10.0]), np.array([110.0, 100.0])),
            (),
        ),
    )
    face = HorizontalFaceGeometry(1, 0.0, 110.0, 10.0, 100.0, 10.0)
    monkeypatch.setattr(
        meshes,
        "_extract_faces",
        lambda profile, section, options: {1: face},
    )

    payload = meshes._build_horizontal_deviation_payload(
        "topo",
        "design",
        [_section("A-01", 0.0), _section("A-02", 20.0)],
        "A",
        1,
        2.0,
        1.0,
        {},
    )

    assert len(payload["cells"]) == 100
    assert payload["summary"]["measured"] == 100
    assert all(cell["status"] == "measured" for cell in payload["cells"])
    assert all(cell["deviation_m"] == pytest.approx(0.0) for cell in payload["cells"])


def test_recoverable_profile_warning_does_not_invalidate_heatmap_measurements(monkeypatch):
    monkeypatch.setattr(db, "get_trimesh_by_id", lambda mesh_id: mesh_id)
    monkeypatch.setattr(meshes, "_crop_mesh_to_sections", lambda mesh, sections: mesh)
    profile = (np.array([0.0, 10.0]), np.array([110.0, 100.0]))
    monkeypatch.setattr(
        meshes,
        "_profile_data_with_diagnostics",
        lambda mesh, section: (
            profile,
            ("minor_profile_reversal_normalized",) if mesh == "topo" else (),
        ),
    )
    face = HorizontalFaceGeometry(1, 0.0, 110.0, 10.0, 100.0, 10.0)
    monkeypatch.setattr(
        meshes,
        "_extract_faces",
        lambda profile, section, options: {1: face},
    )

    payload = meshes._build_horizontal_deviation_payload(
        "topo",
        "design",
        [_section("A-01", 0.0), _section("A-02", 20.0)],
        "A",
        1,
        2.0,
        1.0,
        {},
    )

    assert payload["summary"]["measured"] == len(payload["cells"]) == 100
    assert all(cell["status"] == "measured" for cell in payload["cells"])
    assert all(cell["deviation_m"] == pytest.approx(0.0) for cell in payload["cells"])


def test_heatmap_mesh_ids_are_scoped_to_request_session(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "heatmap-session-test.db")
    db.init_db()
    owner_session = db.create_session()
    other_session = db.create_session()
    bounds = {
        "xmin": 0.0,
        "xmax": 1.0,
        "ymin": 0.0,
        "ymax": 1.0,
        "zmin": 0.0,
        "zmax": 1.0,
    }
    topo_id = db.save_mesh(owner_session, "topo", "topo.stl", b"mesh", 3, 1, bounds)
    design_id = db.save_mesh(owner_session, "design", "design.stl", b"mesh", 3, 1, bounds)

    response = TestClient(app).get(
        f"/api/v1/meshes/{topo_id}/horizontal-deviation",
        params={"design_mesh_id": design_id},
        headers={"x-session-id": other_session},
    )

    assert response.status_code == 404


def test_heatmap_accepts_three_coordinate_origins_and_matches_xy_payload(
    tmp_path, monkeypatch
):
    session_id, topo_id, design_id = _prepare_heatmap_session(monkeypatch, tmp_path)
    _stub_heatmap_geometry(monkeypatch)
    sections_xyz = [
        {**_section(f"A-{index + 1:02d}", index * 2.0), "origin": [0.0, index * 2.0, 2940.0]}
        for index in range(70)
    ]
    db.save_sections(session_id, sections_xyz)
    client = TestClient(app)

    xyz_response = client.get(
        f"/api/v1/meshes/{topo_id}/horizontal-deviation",
        params={"design_mesh_id": design_id, "sector": "A"},
        headers={"x-session-id": session_id},
    )
    assert xyz_response.status_code == 200
    xyz_payload = xyz_response.json()
    assert xyz_payload["summary"]["total"] == 1380
    assert xyz_payload["summary"]["measured"] == 690

    db.save_sections(
        session_id,
        [{**section, "origin": section["origin"][:2]} for section in sections_xyz],
    )
    xy_response = client.get(
        f"/api/v1/meshes/{topo_id}/horizontal-deviation",
        params={"design_mesh_id": design_id, "sector": "A"},
        headers={"x-session-id": session_id},
    )

    assert xy_response.status_code == 200
    assert xy_response.json() == xyz_payload


def test_heatmap_rejects_invalid_origin_coordinate_counts_with_422(tmp_path, monkeypatch):
    session_id, topo_id, design_id = _prepare_heatmap_session(monkeypatch, tmp_path)
    sections = [_section("A-01", 0.0), _section("A-02", 2.0)]
    sections[0]["origin"] = [0.0, 0.0, 2940.0, 1.0]
    db.save_sections(session_id, sections)

    response = TestClient(app).get(
        f"/api/v1/meshes/{topo_id}/horizontal-deviation",
        params={"design_mesh_id": design_id, "sector": "A"},
        headers={"x-session-id": session_id},
    )

    assert response.status_code == 422
    assert "two or three finite coordinates" in response.json()["detail"]
