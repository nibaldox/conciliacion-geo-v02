"""G11 phase 1 — Blast-hole uploader backend endpoints.

Tests:
    1. POST /api/v1/blast/upload with a valid CSV returns 200 and summary.
    2. POST /api/v1/blast/upload with an invalid CSV returns 400.
    3. GET /api/v1/blast/{session_id}/holes returns the persisted holes.
    4. POST /api/v1/blast/upload without session_id returns 422.
"""

import io

import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.schemas as schemas
from api.main import app


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Use a temporary SQLite database per test."""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def session_id():
    return db.create_session()


VALID_CSV = """\
Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real,Kilos_Cargados_real,Taco_m,Burden,Esp,Diam_mm
1000.0,2000.0,100,15.0,90.0,12.0,150.0,1.5,3.0,4.0,200
1005.0,2010.0,100,20.0,95.0,13.0,180.0,2.0,3.2,4.1,200
1010.0,2020.0,100,18.0,92.0,14.0,210.0,2.5,3.5,4.2,200
"""

INVALID_CSV = """\
foo,bar,baz
1,2,3
4,5,6
"""


def _upload_csv(client: TestClient, session_id: str, csv_content: str) -> object:
    """Helper: POST a CSV to /api/v1/blast/upload."""
    return client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        data={"session_id": session_id},
    )


# ---------------------------------------------------------------------------
# 1. Valid CSV upload
# ---------------------------------------------------------------------------


def test_upload_valid_csv_returns_summary(client, session_id):
    resp = _upload_csv(client, session_id, VALID_CSV)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    model = schemas.BlastUploadResponse.model_validate(data)
    assert model.session_id == session_id
    assert model.n_holes == 3
    assert model.n_rows_loaded == 3
    assert model.n_rows_skipped == 0
    assert model.carga_mean > 0
    assert model.descarga_mean > 0
    assert isinstance(model.hardness_distribution, dict)


# ---------------------------------------------------------------------------
# 2. Invalid CSV upload returns 400
# ---------------------------------------------------------------------------


def test_upload_invalid_csv_returns_400(client, session_id):
    resp = _upload_csv(client, session_id, INVALID_CSV)
    assert resp.status_code == 400
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# 3. GET holes returns persisted holes
# ---------------------------------------------------------------------------


def test_get_holes_returns_persisted_holes(client, session_id):
    upload_resp = _upload_csv(client, session_id, VALID_CSV)
    assert upload_resp.status_code == 200

    resp = client.get(f"/api/v1/blast/{session_id}/holes")
    assert resp.status_code == 200

    data = resp.json()
    model = schemas.BlastHolesResponse.model_validate(data)
    assert model.session_id == session_id
    assert len(model.holes) == 3

    for hole in model.holes:
        assert isinstance(hole, schemas.BlastHoleSummary)
        assert hole.hole_id
        assert hole.length > 0
        assert hole.carga > 0
        assert hole.descarga > 0


# ---------------------------------------------------------------------------
# 4. POST without session_id returns 422
# ---------------------------------------------------------------------------


def test_upload_without_session_id_returns_422(client):
    resp = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(VALID_CSV.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 422
    assert "detail" in resp.json()
