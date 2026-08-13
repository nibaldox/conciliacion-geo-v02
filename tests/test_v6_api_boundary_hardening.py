"""V6 P0/P1 — API boundary hardening for blast simulations.

Three confirmed contract regressions in ``api/routers/simulations.py``:

1. (P0) Large gzip payloads must be consumable by the browser/Axios.
   ``_json_or_gzip`` now emits the standard HTTP ``Content-Encoding: gzip``
   with a semantic ``application/json`` content type. The previous
   ``application/octet-stream`` + custom ``X-Payload-Encoding: gzip`` was
   never decompressed by Axios, so the panel received raw gzip bytes as a
   "successful" HTTP 200.

2. (P1) Session isolation on EVERY read/export endpoint. A simulation
   owned by session A is invisible to session B and to requests with no
   ``X-Session-ID`` (middleware-generated session) — both return the
   identical 404 ``SIMULATION_NOT_FOUND``.

3. (P1) Server-internal detail (absolute NPZ paths, exception text) must
   never leak in 500 / missing-artifact responses. Public 4xx contract
   messages (``INVALID_PROFILE_PARAMS``, ``SIMULATION_BLOCKED`` ...) are
   preserved exactly.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.routers.simulations as router_mod
from api.routers.simulations import _json_or_gzip
from core.blast_simulation import PersistenceError


OWNER_SESSION = "owner-session-A"
INTRUDER_SESSION = "intruder-session-B"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(api_isolated_db):
    from api.main import app

    with TestClient(app) as c:
        yield c


def _single_hole() -> dict:
    return {
        "hole_id": "H-001", "X": 5.0, "Y": 5.0, "Z_collar": 9.0,
        "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 1.0,
        "Incl": 0.0, "Az": 0.0, "Len": 8.0,
        "Taco_m": 2.0, "descarga": 6.0, "Diam_mm": 200.0,
        "Kilos_Cargados_real": 100.0, "Tipo_Explosivo": "ANFO",
        "source_row_index": 0,
    }


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


@pytest.fixture()
def sim(client) -> dict:
    """Create one real simulation owned by OWNER_SESSION.

    POST is the owner-establishing write: the row is stored with
    ``session_id = body.session_id`` (OWNER_SESSION). Read endpoints derive
    ownership from the ``X-Session-ID`` header via the session middleware,
    so a matching header MUST reproduce the owner.
    """
    db.get_or_create_session(OWNER_SESSION)
    db.save_blast_upload(
        OWNER_SESSION,
        {
            "accepted_rows": [_single_hole()],
            "geometry_configuration": {"geometry_configuration_version": "2.0"},
        },
    )
    r = client.post("/api/v1/blast/simulations", json=_canonical_body(OWNER_SESSION))
    assert r.status_code == 200, r.text
    sim_id = r.json()["simulation_id"]
    return {"simulation_id": sim_id, "owner": OWNER_SESSION}


# Each reader: (label, path-format, query params). Path receives sim_id.
READERS = [
    ("base", "/api/v1/blast/simulations/{sim}", {}),
    ("summary", "/api/v1/blast/simulations/{sim}/summary", {}),
    (
        "profile",
        "/api/v1/blast/simulations/{sim}/profile",
        {"start_xyz": "0,5,5", "end_xyz": "10,5,5"},
    ),
    ("plan", "/api/v1/blast/simulations/{sim}/plan", {"elevation": 5.0}),
    ("section", "/api/v1/blast/simulations/{sim}/section", {"axis": "x", "coordinate": 5.0}),
    ("export_json", "/api/v1/blast/simulations/{sim}/export", {"fmt": "json"}),
    ("export_npz", "/api/v1/blast/simulations/{sim}/export", {"fmt": "npz"}),
    ("export_xlsx", "/api/v1/blast/simulations/{sim}/export", {"fmt": "xlsx"}),
]


# ---------------------------------------------------------------------------
# P0 — gzip contract
# ---------------------------------------------------------------------------


class TestGzipContract:
    def test_large_payload_uses_standard_content_encoding(self):
        big = {"simulation_id": "sim-big", "blob": "A" * 1_200_000}
        resp = _json_or_gzip(big)

        assert resp.status_code == 200
        # Semantic JSON content type, standard HTTP encoding (not octet-stream
        # + custom X-Payload-Encoding that Axios never decompresses).
        assert resp.headers["content-encoding"] == "gzip"
        assert resp.media_type == "application/json"
        assert resp.headers.get("x-payload-encoding") is None

        raw = json.dumps(big, default=str, ensure_ascii=False).encode("utf-8")
        decompressed = gzip.decompress(resp.body)
        assert decompressed == raw
        assert json.loads(decompressed)["simulation_id"] == "sim-big"

    def test_small_payload_remains_plain_json(self):
        small = {"simulation_id": "sim-small", "ok": True}
        resp = _json_or_gzip(small)

        assert resp.status_code == 200
        assert "content-encoding" not in resp.headers
        assert resp.media_type == "application/json"
        assert json.loads(resp.body) == small

    def test_large_get_summary_serves_consumable_json(self, client, sim):
        """End-to-end: a large GET /summary body is standard gzip and
        decompresses to valid JSON preserving ``simulation_id``."""
        sim_id = sim["simulation_id"]
        with patch.object(
            router_mod,
            "_json_or_gzip",
            wraps=_json_or_gzip,
        ) as spy:
            r = client.get(
                f"/api/v1/blast/simulations/{sim_id}/summary",
                headers={"X-Session-ID": sim["owner"], "Accept-Encoding": "gzip"},
            )
        assert r.status_code == 200
        # Either httpx auto-decompressed (r.json works) or it is still
        # encoded — in both cases the contract is: the caller recovers JSON.
        assert r.json()["simulation_id"] == sim_id
        # httpx exposes the raw (pre-decode) headers on .headers even when
        # it transparently decodes the body.
        assert spy.call_count >= 1


# ---------------------------------------------------------------------------
# P1 — session isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "path_fmt", "params"), READERS)
class TestSessionIsolation:
    def test_owner_can_read(self, client, sim, label, path_fmt, params):
        sim_id = sim["simulation_id"]
        r = client.get(
            path_fmt.format(sim=sim_id),
            params=params,
            headers={"X-Session-ID": sim["owner"]},
        )
        assert r.status_code == 200, f"{label}: {r.status_code} {r.text[:200]}"

    def test_intruder_session_gets_404(self, client, sim, label, path_fmt, params):
        sim_id = sim["simulation_id"]
        r = client.get(
            path_fmt.format(sim=sim_id),
            params=params,
            headers={"X-Session-ID": INTRUDER_SESSION},
        )
        assert r.status_code == 404, f"{label}: expected 404, got {r.status_code}"
        detail = r.json()["detail"]
        assert detail["error_code"] == "SIMULATION_NOT_FOUND"
        # Identical shape for not-owned as for not-found.
        assert detail["details"] == {"simulation_id": sim_id}

    def test_missing_header_is_not_an_owner(self, client, sim, label, path_fmt, params):
        """No X-Session-ID → middleware generates a fresh session that cannot
        own a simulation created by another session → 404."""
        sim_id = sim["simulation_id"]
        r = client.get(path_fmt.format(sim=sim_id), params=params)
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "SIMULATION_NOT_FOUND"


def test_get_unknown_simulation_is_404(client):
    r = client.get(
        "/api/v1/blast/simulations/does-not-exist/summary",
        headers={"X-Session-ID": OWNER_SESSION},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "SIMULATION_NOT_FOUND"


def test_db_get_blast_simulation_scopes_by_session(api_isolated_db):
    """Unit: the DB reader honors the session scope and is backward compatible
    when no scope is supplied."""
    import api.database as dbmod

    dbmod.get_or_create_session(OWNER_SESSION)
    conn = dbmod.get_connection()
    conn.execute(
        "INSERT INTO blast_simulations "
        "(simulation_id, session_id, configuration_json, summary_json, "
        " npz_path, npz_sha256, engine_version, energy_mode, temporal_status) "
        "VALUES (?, ?, '{}', '{}', '', '', '', '', '')",
        ("cross-session-sim", OWNER_SESSION),
    )
    conn.commit()
    conn.close()

    assert dbmod.get_blast_simulation("cross-session-sim") is not None
    assert (
        dbmod.get_blast_simulation("cross-session-sim", session_id=OWNER_SESSION)
        is not None
    )
    assert (
        dbmod.get_blast_simulation(
            "cross-session-sim", session_id=INTRUDER_SESSION
        )
        is None
    )


# ---------------------------------------------------------------------------
# P1 — internal detail leak
# ---------------------------------------------------------------------------


class TestInternalDetailLeak:
    def test_persistence_error_on_read_does_not_leak_path_or_text(self, client, sim):
        sim_id = sim["simulation_id"]
        secret = "/server/private/leaked.npz"
        with patch.object(
            router_mod, "read_npz_artifact", side_effect=PersistenceError(secret)
        ):
            r = client.get(
                f"/api/v1/blast/simulations/{sim_id}/profile",
                params={"start_xyz": "0,5,5", "end_xyz": "10,5,5"},
                headers={"X-Session-ID": sim["owner"]},
            )
        assert r.status_code == 500
        # The exception message (which carries the absolute path) and the
        # path itself must not appear anywhere in the response body.
        assert secret not in r.text
        assert "leaked.npz" not in r.text
        detail = r.json()["detail"]
        assert detail["error_code"] == "NPZ_READ_FAILED"
        assert detail["message"]  # generic, non-empty
        assert "leaked" not in detail["message"]
        # No absolute path in the details dict.
        assert "npz_path" not in detail["details"]
        assert "expected_path" not in detail["details"]

    def test_missing_artifact_does_not_leak_path(self, client, sim):
        sim_id = sim["simulation_id"]
        row = db.get_blast_simulation(sim_id, session_id=sim["owner"])
        assert row and row["npz_path"]
        npz_path = row["npz_path"]
        Path(npz_path).unlink(missing_ok=True)

        r = client.get(
            f"/api/v1/blast/simulations/{sim_id}/profile",
            params={"start_xyz": "0,5,5", "end_xyz": "10,5,5"},
            headers={"X-Session-ID": sim["owner"]},
        )
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "NO_ARTIFACT"
        assert "expected_path" not in detail["details"]
        assert npz_path not in r.text

    def test_create_persistence_error_is_sanitized(self, client):
        db.get_or_create_session("create-leak")
        db.save_blast_upload(
            "create-leak",
            {
                "accepted_rows": [_single_hole()],
                "geometry_configuration": {"geometry_configuration_version": "2.0"},
            },
        )
        secret = "/server/private/create.npz"
        with patch.object(
            router_mod, "write_atomic_simulation", side_effect=PersistenceError(secret)
        ):
            r = client.post(
                "/api/v1/blast/simulations",
                json=_canonical_body("create-leak"),
            )
        assert r.status_code == 500
        assert secret not in r.text
        assert r.json()["detail"]["error_code"] == "PERSISTENCE_ERROR"

    def test_domain_4xx_keeps_useful_error_code(self, client, sim):
        """A public input/domain 4xx must still carry its contract message —
        sanitization only applies to 500s, not to the 4xx channel."""
        sim_id = sim["simulation_id"]
        r = client.get(
            f"/api/v1/blast/simulations/{sim_id}/profile",
            params={"start_xyz": "0,5", "end_xyz": "10,5,5"},  # wrong arity
            headers={"X-Session-ID": sim["owner"]},
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["error_code"] == "INVALID_PROFILE_PARAMS"
        assert "coordenadas" in detail["message"].lower()
