"""GET /api/v1/process/profiles/{id} exposes ``benches_design`` (additive).

The proposal overlay layer in the web frontend needs the design bench
geometry (crest/toe distance + toe elevation per bench) to reconstruct
the guided solid toe and local floor, mirroring the Streamlit reference
``ui/tabs/profiles/proposal.py::add_proposal_traces``. The field is
additive and optional: profiles served from a cache without design
benches must keep working with ``benches_design`` null/absent.
"""
from __future__ import annotations

import trimesh
from fastapi.testclient import TestClient

import api.database as db
from api import schemas

ENDPOINT = "/api/v1/process/profiles/0"

BENCH_KEYS = {
    "bench_number", "crest_elevation", "crest_distance",
    "toe_elevation", "toe_distance", "bench_height", "face_angle",
    "berm_width", "is_ramp", "spill_width", "effective_berm_width",
    "spill_start_distance", "spill_start_elevation", "floor_elevation",
}


def _bench_surface(shift: float = 0.0) -> trimesh.Trimesh:
    profile = [(-10, 30), (0, 30), (10, 15), (20, 15), (30, 0), (50, 0)]
    vertices = [(x + shift, y, z) for x, z in profile for y in (-10, 10)]
    faces = []
    for index in range(len(profile) - 1):
        start = index * 2
        faces.extend([(start, start + 1, start + 2), (start + 1, start + 3, start + 2)])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _processed_session(client: TestClient):
    headers = {"X-Session-ID": "profile-benches-design"}
    for role, shift in (("design", 0.0), ("topo", 0.5)):
        mesh = _bench_surface(shift)
        response = client.post(
            "/api/v1/meshes/upload",
            files={"file": (f"{role}.stl", mesh.export(file_type="stl"), "application/octet-stream")},
            data={"type": role},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    response = client.post(
        "/api/v1/sections/manual",
        json=[{"name": "S-01", "origin": [20.0, 0.0], "azimuth": 90, "length": 60, "sector": "A"}],
        headers=headers,
    )
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/process", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "complete"
    return headers


class TestProfileBenchesDesign:
    def test_exposes_benches_design_with_same_schema_as_topo(self, client: TestClient):
        headers = _processed_session(client)

        response = client.get(ENDPOINT, headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["benches_topo"], "fixture must yield topo benches"
        design = payload["benches_design"]
        assert design, "processed profile must expose design benches"

        topo_keys = {key for bench in payload["benches_topo"] for key in bench}
        for bench in design:
            assert BENCH_KEYS <= set(bench)
            assert topo_keys == set(bench)
            assert isinstance(bench["bench_number"], int)
            for key in (
                "crest_elevation", "crest_distance", "toe_elevation",
                "toe_distance", "bench_height", "face_angle", "berm_width",
            ):
                assert isinstance(bench[key], (int, float))
            assert isinstance(bench["is_ramp"], bool)

        bench_numbers = [bench["bench_number"] for bench in design]
        assert len(bench_numbers) == len(set(bench_numbers)), "design bench numbers must be unique"

    def test_design_without_cache_yields_null_benches_design(self, client: TestClient, monkeypatch):
        headers = _processed_session(client)

        sections = db.get_sections(headers["X-Session-ID"])
        assert sections
        extraction = db.get_extraction(headers["X-Session-ID"], sections[0]["name"], "design")
        assert extraction

        real_get_extraction = db.get_extraction

        def _without_design_benches(session_id, section_name, ext_type):
            if ext_type != "design":
                return real_get_extraction(session_id, section_name, ext_type)
            data = real_get_extraction(session_id, section_name, ext_type)
            if data is None:
                return None
            return {k: v for k, v in data.items() if k != "benches"}

        monkeypatch.setattr(db, "get_extraction", _without_design_benches)

        response = client.get(ENDPOINT, headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert not payload.get("benches_design")
        assert payload.get("benches_topo"), "topo benches must remain available"

    def test_schema_declares_optional_benches_design(self):
        field = schemas.ProfileData.model_fields["benches_design"]
        assert not field.is_required()
