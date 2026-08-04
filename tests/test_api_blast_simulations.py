"""API tests for the blast simulation endpoints (spec §9)."""
from __future__ import annotations

import pytest

from fastapi.testclient import TestClient


@pytest.fixture()
def client(api_isolated_db):
    from api.main import app
    with TestClient(app) as c:
        yield c


def _seed_session(client: TestClient, accepted_rows: list[dict]) -> str:
    """Create a session with the given accepted_rows persisted."""
    import api.database as db
    sid = db.create_session()
    db.save_blast_upload(sid, {
        "accepted_rows": accepted_rows,
        "geometry_configuration": {"geometry_configuration_version": "2.0"},
    })
    return sid


def _canonical_body(session_id: str, **overrides) -> dict:
    body = {
        "session_id": session_id,
        "geometry_configuration_version": "2.0",
        "user_confirmed": True,
        "voxel_size_m": 1.0,
        "domain_bounds": {
            "x_min": 0.0, "y_min": 0.0, "z_min": 0.0,
            "x_max": 10.0, "y_max": 10.0, "z_max": 10.0,
        },
        "energy_mode": "ABSOLUTE",
        "temporal_mode": "STATIC",
        "anisotropy_mode": "ISOTROPIC",
        "kernel_type": "EXPONENTIAL_INVERSE_SQUARE",
        "attenuation_coefficient_1_m": 2.0,
        "regularization_radius_m": 0.5,
        "support_radius_m": 5.0,
        "coupling_efficiency": 0.85,
        "rock_mass": {
            "rock_unit_id": "1c", "density_kg_m3": 2700.0, "ucs_mpa": 80.0,
            "attenuation_coefficient_1_m": 2.0, "wave_velocity_m_s": 3500.0,
            "anisotropy_mode": "ISOTROPIC", "source": "lab", "status": "VALIDATED",
        },
        "plan_elevations": [5.0],
        "section_coordinates": [["x", 5.0]],
    }
    body.update(overrides)
    return body


def _single_hole() -> dict:
    return {
        "hole_id": "H-001", "X": 5.0, "Y": 5.0, "Z_collar": 9.0,
        "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 1.0,
        "Incl": 0.0, "Az": 0.0, "Len": 8.0,
        "Taco_m": 2.0, "descarga": 6.0, "Diam_mm": 200.0,
        "Kilos_Cargados_real": 100.0, "Tipo_Explosivo": "ANFO",
        "source_row_index": 0,
    }


# ---------------------------------------------------------------------------
# POST happy path
# ---------------------------------------------------------------------------


class TestPostCreate:
    def test_creates_simulation_with_npz_and_slices(self, client):
        sid = _seed_session(client, [_single_hole()])
        r = client.post("/api/v1/blast/simulations", json=_canonical_body(sid))
        assert r.status_code == 200, r.text
        body = r.json()
        assert "simulation_id" in body
        assert len(body["npz_sha256"]) == 64
        assert body["summary"]["energy_mode"] == "ABSOLUTE"
        assert len(body["plan_slices"]) == 1
        assert len(body["section_slices"]) == 1
        assert body["provenance"]["engine_version"] == "blast-sim-1.0.0"

    def test_temporal_mode_with_velocity(self, client):
        sid = _seed_session(client, [_single_hole()])
        body = _canonical_body(
            sid,
            temporal_mode="TEMPORAL",
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="lab",
            pulse_sigma_s=0.025,
        )
        r = client.post("/api/v1/blast/simulations", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["summary"]["temporal_status"] in ("AVAILABLE", "NOT_AVAILABLE")


# ---------------------------------------------------------------------------
# POST error paths
# ---------------------------------------------------------------------------


class TestPostErrors:
    def test_unconfirmed_returns_400(self, client):
        sid = _seed_session(client, [_single_hole()])
        body = _canonical_body(sid, user_confirmed=False)
        r = client.post("/api/v1/blast/simulations", json=body)
        assert r.status_code == 400
        assert r.json()["detail"]["error_code"] == "SIMULATION_REJECTED"

    def test_missing_energy_mode_returns_422(self, client):
        """V6-01: invalid energy_mode enum is now rejected at the
        contract level (HTTP 422) instead of HTTP 400 via the engine."""
        sid = _seed_session(client, [_single_hole()])
        body = _canonical_body(sid)
        body["energy_mode"] = "JOULES"
        r = client.post("/api/v1/blast/simulations", json=body)
        assert r.status_code == 422
        assert r.json()["detail"]["error_code"] == "INVALID_REQUEST"

    def test_coupling_out_of_range_returns_422(self, client):
        """V5-07: invalid coupling is now rejected at the contract level
        (HTTP 422) instead of being passed to the engine (HTTP 400)."""
        sid = _seed_session(client, [_single_hole()])
        body = _canonical_body(sid, coupling_efficiency=1.5)
        r = client.post("/api/v1/blast/simulations", json=body)
        assert r.status_code == 422

    def test_inverted_bounds_returns_422(self, client):
        """V6-01: inverted domain_bounds are now rejected at the contract
        level (HTTP 422) instead of HTTP 400 via the engine."""
        sid = _seed_session(client, [_single_hole()])
        body = _canonical_body(sid)
        body["domain_bounds"] = {
            "x_min": 10.0, "y_min": 0.0, "z_min": 0.0,
            "x_max": 0.0, "y_max": 10.0, "z_max": 10.0,
        }
        r = client.post("/api/v1/blast/simulations", json=body)
        assert r.status_code == 422

    def test_no_accepted_rows_returns_400(self, client):
        sid = _seed_session(client, [])
        r = client.post("/api/v1/blast/simulations", json=_canonical_body(sid))
        assert r.status_code == 400
        assert r.json()["detail"]["error_code"] == "NO_ACCEPTED_ROWS"

    def test_temporal_without_velocity_returns_400(self, client):
        sid = _seed_session(client, [_single_hole()])
        body = _canonical_body(sid, temporal_mode="TEMPORAL")
        r = client.post("/api/v1/blast/simulations", json=body)
        assert r.status_code == 400
        assert r.json()["detail"]["error_code"] == "SIMULATION_INVALID"


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------


class TestGetEndpoints:
    def test_get_simulation_returns_summary(self, client):
        sid = _seed_session(client, [_single_hole()])
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}")
        assert r.status_code == 200
        assert r.json()["simulation_id"] == sim_id

    def test_get_unknown_returns_404(self, client):
        r = client.get("/api/v1/blast/simulations/does-not-exist")
        assert r.status_code == 404

    def test_get_plan_returns_nearest_slice(self, client):
        sid = _seed_session(client, [_single_hole()])
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}/plan?elevation=5.0")
        assert r.status_code == 200
        assert "elevation_m" in r.json()

    def test_get_section_returns_nearest_slice(self, client):
        sid = _seed_session(client, [_single_hole()])
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}/section?axis=x&coordinate=5.0")
        assert r.status_code == 200
        assert "coordinate_m" in r.json()

    def test_get_plan_unknown_simulation_404(self, client):
        r = client.get("/api/v1/blast/simulations/nope/plan?elevation=0")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------


class TestExportEndpoints:
    def test_export_npz_returns_binary(self, client):
        sid = _seed_session(client, [_single_hole()])
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}/export?fmt=npz")
        assert r.status_code == 200
        assert len(r.content) > 0
        assert r.headers["content-type"] == "application/octet-stream"

    def test_export_xlsx_returns_workbook(self, client):
        sid = _seed_session(client, [_single_hole()])
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}/export?fmt=xlsx")
        assert r.status_code == 200
        assert len(r.content) > 0
        # XLSX magic bytes: PK zip header.
        assert r.content[:2] == b"PK"

    def test_export_json_returns_summary(self, client):
        sid = _seed_session(client, [_single_hole()])
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}/export?fmt=json")
        assert r.status_code == 200
        assert r.json()["simulation_id"] == sim_id
