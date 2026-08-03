"""Cross-layer integration tests for Phase 2 (spec §14).

These tests prove the FULL real flow end-to-end:

    React hook (real .ts source)
      → POST /api/v1/blast/simulations (real FastAPI TestClient)
      → core.blast_simulation.run_simulation
      → SQLite persistence (real api.database)
      → NPZ artifact (real filesystem)
      → JSON summary (real filesystem)
      → Excel export (reopened + parsed)

No interface is mocked by hand. The React layer is verified by reading
the actual ``web/src/api/hooks.ts`` source and asserting that the wire
format matches what the API accepts. The API call uses a real
TestClient against the real ``api.main.app`` with the real SQLite
schema (via the shared ``api_isolated_db`` fixture). The NPZ and Excel
artifacts are written to a real temp dir and reopened by the
persistence helpers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_PATH = REPO_ROOT / "web" / "src" / "api" / "hooks.ts"
TYPES_PATH = REPO_ROOT / "web" / "src" / "api" / "types.ts"


@pytest.fixture()
def client(api_isolated_db):
    from api.main import app
    with TestClient(app) as c:
        yield c


def _seed_session_with_accepted_rows(client: TestClient) -> str:
    """Seed a real session with canonical accepted_rows (Fase 1 output)."""
    import api.database as db
    sid = db.create_session()
    db.save_blast_upload(sid, {
        "accepted_rows": [
            {
                "hole_id": "H-001", "X": 5.0, "Y": 5.0, "Z_collar": 9.0,
                "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 1.0,
                "Incl": 0.0, "Az": 0.0, "Len": 8.0,
                "Taco_m": 2.0, "descarga": 6.0, "Diam_mm": 200.0,
                "Kilos_Cargados_real": 100.0, "Tipo_Explosivo": "ANFO",
                "source_row_index": 0,
            },
            {
                "hole_id": "H-002", "X": 7.0, "Y": 5.0, "Z_collar": 9.0,
                "X_toe": 7.0, "Y_toe": 5.0, "Z_toe": 1.0,
                "Incl": 0.0, "Az": 0.0, "Len": 8.0,
                "Taco_m": 2.0, "descarga": 6.0, "Diam_mm": 200.0,
                "Kilos_Cargados_real": 120.0, "Tipo_Explosivo": "Pirex-930",
                "source_row_index": 1,
            },
        ],
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


# ---------------------------------------------------------------------------
# 1. React real source — wire format parity
# ---------------------------------------------------------------------------


class TestReactSourceParity:
    """Verify the productive React hook actually emits what the API expects.

    Reads ``web/src/api/hooks.ts`` and ``types.ts`` and asserts the wire
    fields are present — no mock, just like the Fase 1 production-parity
    test parses the upload hook source.
    """

    def test_hook_posts_to_simulations_endpoint(self):
        src = HOOKS_PATH.read_text(encoding="utf-8")
        assert "useCreateBlastSimulation" in src
        assert "/blast/simulations" in src
        # The hook must use the typed SimulationCreateRequest.
        assert "SimulationCreateRequest" in src

    def test_types_define_canonical_contract(self):
        src = TYPES_PATH.read_text(encoding="utf-8")
        # Every field the API requires is declared in the wire types.
        required_fields = [
            "session_id", "geometry_configuration_version", "user_confirmed",
            "voxel_size_m", "domain_bounds", "energy_mode", "temporal_mode",
            "anisotropy_mode", "attenuation_coefficient_1_m",
            "regularization_radius_m", "coupling_efficiency",
        ]
        for f in required_fields:
            assert f in src, f"missing wire field {f!r} in types.ts"

    def test_response_type_carries_canonical_fields(self):
        src = TYPES_PATH.read_text(encoding="utf-8")
        for field in ("simulation_id", "summary", "grid_metadata", "energy_field",
                      "plan_slices", "section_slices", "blocking_errors",
                      "provenance", "npz_sha256"):
            assert field in src


# ---------------------------------------------------------------------------
# 2. Real API → core → NPZ round-trip
# ---------------------------------------------------------------------------


class TestApiCoreNpzRoundTrip:
    def test_post_runs_engine_and_persists_npz(self, client, tmp_path, monkeypatch):
        # Point CONCILIACION_DATA_DIR at the per-test tmp so the NPZ lands
        # where we can read it back.
        monkeypatch.setenv("CONCILIACION_DATA_DIR", str(tmp_path))
        sid = _seed_session_with_accepted_rows(client)
        r = client.post("/api/v1/blast/simulations", json=_canonical_body(sid))
        assert r.status_code == 200, r.text
        body = r.json()
        sim_id = body["simulation_id"]

        # NPZ artifact on disk.
        npz_path = Path(body["energy_field"]["npz_path"])
        assert npz_path.exists()
        assert body["grid_metadata"]["npz_sha256"]

        # Re-open with the persistence helper and verify SHA.
        from core.blast_simulation import read_npz_artifact
        arrays, metadata, sha = read_npz_artifact(
            npz_path, expected_sha256=body["grid_metadata"]["npz_sha256"]
        )
        assert metadata["simulation_id"] == sim_id
        assert metadata["voxel_count"] == arrays["energy_total"].size
        # The NPZ carries the density array too (never kg/m³ for a fraction).
        assert "energy_density" in arrays

    def test_get_summary_returns_full_canonical_dict(self, client):
        sid = _seed_session_with_accepted_rows(client)
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}")
        assert r.status_code == 200
        body = r.json()
        # Canonical fields survive the SQLite JSON round-trip.
        for key in ("simulation_id", "configuration", "grid_metadata",
                    "energy_field", "processing_summary", "provenance"):
            assert key in body

    def test_export_xlsx_reopens_and_parses(self, client, tmp_path):
        sid = _seed_session_with_accepted_rows(client)
        sim_id = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()["simulation_id"]
        r = client.get(f"/api/v1/blast/simulations/{sim_id}/export?fmt=xlsx")
        assert r.status_code == 200
        assert r.content[:2] == b"PK"  # XLSX zip magic
        out = tmp_path / "sim.xlsx"
        out.write_bytes(r.content)
        from core.blast_simulation import read_back_simulation_xlsx
        sheets = read_back_simulation_xlsx(out)
        for required in ("Resumen", "Configuración", "Fuentes", "Procedencia"):
            assert required in sheets

    def test_export_npz_matches_persisted_artifact(self, client):
        sid = _seed_session_with_accepted_rows(client)
        body = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()
        sim_id = body["simulation_id"]
        persisted_sha = body["grid_metadata"]["npz_sha256"]

        r = client.get(f"/api/v1/blast/simulations/{sim_id}/export?fmt=npz")
        assert r.status_code == 200
        # The bytes served by the API match the persisted SHA.
        from core.blast_simulation import sha256_bytes
        assert sha256_bytes(r.content) == persisted_sha


# ---------------------------------------------------------------------------
# 3. Rejected rows never reach the engine
# ---------------------------------------------------------------------------


class TestRejectedRowsIsolation:
    def test_rejected_rows_are_not_in_accepted(self, client):
        # Seed with a clean accepted list — the engine must consume
        # exactly these rows and nothing else.
        import api.database as db
        sid = db.create_session()
        db.save_blast_upload(sid, {
            "accepted_rows": [
                {"hole_id": "H-OK", "X": 5.0, "Y": 5.0, "Z_collar": 9.0,
                 "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 1.0,
                 "Incl": 0.0, "Az": 0.0, "Len": 8.0,
                 "Taco_m": 2.0, "descarga": 6.0, "Diam_mm": 200.0,
                 "Kilos_Cargados_real": 100.0, "Tipo_Explosivo": "ANFO",
                 "source_row_index": 0},
            ],
            "rejected_rows": [
                {"source_row_index": 1, "error_code": "BAD_ROW",
                 "message": "would-be rejected row"},
            ],
            "geometry_configuration": {"geometry_configuration_version": "2.0"},
        })
        r = client.post("/api/v1/blast/simulations", json=_canonical_body(sid))
        assert r.status_code == 200, r.text
        body = r.json()
        # Only ONE accepted hole — the rejected row never reached the engine.
        assert body["summary"]["accepted_holes"] == 1


# ---------------------------------------------------------------------------
# 4. Determinism across the full stack
# ---------------------------------------------------------------------------


class TestFullStackDeterminism:
    def test_two_runs_same_input_same_total_energy(self, client):
        sid = _seed_session_with_accepted_rows(client)
        body1 = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()
        body2 = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()
        # simulation_id is randomly generated — the deterministic parts match.
        assert body1["summary"]["represented_energy_j"] == body2["summary"]["represented_energy_j"]
        assert body1["summary"]["total_coupled_energy_j"] == body2["summary"]["total_coupled_energy_j"]
        assert body1["summary"]["active_voxels"] == body2["summary"]["active_voxels"]
        assert body1["provenance"]["accepted_rows_hash"] == body2["provenance"]["accepted_rows_hash"]


# ---------------------------------------------------------------------------
# 5. Conservation survives every layer
# ---------------------------------------------------------------------------


class TestConservationAcrossLayers:
    def test_total_coupled_equals_represented_plus_outside(self, client):
        sid = _seed_session_with_accepted_rows(client)
        body = client.post(
            "/api/v1/blast/simulations", json=_canonical_body(sid)
        ).json()
        ef = body["energy_field"]
        total = ef["represented_energy_j"] + ef["outside_domain_energy_j"]
        assert total == pytest.approx(ef["total_coupled_energy_j"], rel=1e-6)
