"""G03a — Backend endpoint for blast holes projected onto a section profile.

Exercises ``GET /api/v1/process/profiles/{section_id}/blast-holes`` which wraps
``core.calculo_tronadura.proyectar_pozos_en_seccion`` to expose the 3D
blast-hole pattern as 2D profile markers (the data source the Web UI's
"Mostrar Pozos de Tronadura" toggle needs — see docs/UI_PARITY_AUDIT.md).

Blast holes are seeded into the session settings dict under the
``"blast_holes"`` key (the store the endpoint reads from until the upload
flow lands in gap G11).
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.database as db
import api.schemas as schemas


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isolated SQLite DB per test (mirrors tests/test_api.py)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def _section_dict(
    name: str = "S-01",
    origin=(0.0, 0.0),
    azimuth: float = 0.0,
    length: float = 200.0,
    sector: str = "A",
) -> dict:
    return {
        "name": name,
        "origin": list(origin),
        "azimuth": azimuth,
        "length": length,
        "sector": sector,
    }


def _hole(
    hole_id: str,
    x: float,
    y: float,
    z_collar: float = 100.0,
    z_toe: float = 85.0,
    burden: float = 3.0,
    esp: float = 4.0,
    length: float = 15.0,
) -> dict:
    return {
        "hole_id": hole_id,
        "X": x,
        "Y": y,
        "Z_collar": z_collar,
        "Z_toe": z_toe,
        "X_toe": x,
        "Y_toe": y,
        "Len": length,
        "Burden": burden,
        "Esp": esp,
    }


def _seed_section_and_get_headers(client, section=None) -> dict:
    headers = {"x-session-id": db.create_session()}
    db.save_sections(headers["x-session-id"], [section or _section_dict()])
    return headers


# ---------------------------------------------------------------------------
# 1. Empty list when no blast holes
# ---------------------------------------------------------------------------


def test_returns_empty_list_when_no_blast_holes(client):
    headers = _seed_section_and_get_headers(client)
    resp = client.get("/api/v1/process/profiles/0/blast-holes", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["holes"] == []
    assert data["section_id"] == "S-01"


# ---------------------------------------------------------------------------
# 2. Returns holes when present
# ---------------------------------------------------------------------------


def test_returns_holes_when_present(client):
    headers = _seed_section_and_get_headers(client)
    session_id = headers["x-session-id"]
    db.save_settings(session_id, {
        "blast_holes": [
            _hole("H001", x=0.0, y=10.0, z_collar=100.0, burden=3.5, esp=4.5),
        ],
    })

    resp = client.get("/api/v1/process/profiles/0/blast-holes", headers=headers)
    assert resp.status_code == 200
    holes = resp.json()["holes"]
    assert len(holes) == 1

    h = holes[0]
    assert h["hole_id"] == "H001"
    assert h["distance"] == pytest.approx(10.0, abs=1e-3)
    assert h["elevation"] == pytest.approx(100.0, abs=1e-3)
    assert h["burden"] == pytest.approx(3.5, abs=1e-3)
    assert h["spacing"] == pytest.approx(4.5, abs=1e-3)
    assert h["is_within_tolerance"] is True


# ---------------------------------------------------------------------------
# 3. Tolerance filter affects is_within_tolerance
# ---------------------------------------------------------------------------


def test_tolerance_filter_works(client):
    headers = _seed_section_and_get_headers(client)
    session_id = headers["x-session-id"]
    # Section azimuth 0 → direction +Y, normal +X → dist_perp = |X|.
    db.save_settings(session_id, {
        "blast_holes": [
            _hole("H_NEAR", x=0.0, y=10.0),   # dist_perp = 0  → within 2 m
            _hole("H_FAR", x=5.0, y=20.0),    # dist_perp = 5  → beyond 2 m
        ],
    })

    resp = client.get(
        "/api/v1/process/profiles/0/blast-holes",
        params={"tolerance": 2.0},
        headers=headers,
    )
    assert resp.status_code == 200
    holes = {h["hole_id"]: h for h in resp.json()["holes"]}
    assert len(holes) == 2
    assert holes["H_NEAR"]["is_within_tolerance"] is True
    assert holes["H_FAR"]["is_within_tolerance"] is False
    assert holes["H_NEAR"]["distance"] == pytest.approx(10.0, abs=1e-3)
    assert holes["H_FAR"]["distance"] == pytest.approx(20.0, abs=1e-3)


# ---------------------------------------------------------------------------
# 4. Invalid section returns empty list (not 404)
# ---------------------------------------------------------------------------


def test_invalid_section_returns_empty_list(client):
    headers = _seed_section_and_get_headers(client)
    resp = client.get(
        "/api/v1/process/profiles/999/blast-holes", headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["holes"] == []


# ---------------------------------------------------------------------------
# 5. Response schema is correct
# ---------------------------------------------------------------------------


def test_response_schema_is_correct(client):
    headers = _seed_section_and_get_headers(client)
    session_id = headers["x-session-id"]
    db.save_settings(session_id, {
        "blast_holes": [
            _hole("H001", x=1.0, y=12.0, burden=2.0, esp=5.0),
        ],
    })

    resp = client.get(
        "/api/v1/process/profiles/0/blast-holes",
        params={"mesh_id": "mesh-abc", "tolerance": 1.5},
        headers=headers,
    )
    assert resp.status_code == 200

    model = schemas.BlastHolesOnProfileResponse.model_validate(resp.json())
    assert model.section_id == "S-01"
    assert model.mesh_id == "mesh-abc"
    assert model.tolerance == pytest.approx(1.5)
    assert len(model.holes) == 1
    assert isinstance(model.holes[0], schemas.BlastHoleOnProfile)
    assert set(schemas.BlastHoleOnProfile.model_fields.keys()) == {
        "hole_id", "distance", "elevation", "burden",
        "spacing", "is_within_tolerance",
    }
