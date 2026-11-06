"""G11 phase 1 — Blast-hole uploader backend endpoints.

Tests:
    1. POST /api/v1/blast/upload with a valid CSV returns 200 and summary.
    2. POST /api/v1/blast/upload with an invalid CSV returns 400.
    3. GET /api/v1/blast/{session_id}/holes returns the persisted holes.
    4. POST /api/v1/blast/upload without session_id returns 422.
"""

import io

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
import trimesh
from openpyxl import load_workbook

import api.database as db
import api.schemas as schemas
from api.main import app


# Remediación 3.3: use the centralized SQLite lifecycle fixture. The
# previous per-test init was incomplete (it did not run the lifespan and
# depended on the order of tests). The autouse `_api_reset_state_caches`
# fixture in conftest.py also busts the trimesh lru_cache.
@pytest.fixture(autouse=True)
def isolated_db(api_isolated_db):
    yield


@pytest.fixture()
def client(api_test_client):
    return api_test_client


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

GEOMETRY_FORM = {
    "geometry_user_confirmed": "true",
    "incl_convention": "from_vertical",
    "incl_sign_convention": "ABSOLUTE_VALUE",
    "az_convention": "CLOCKWISE_FROM_NORTH",
    "angle_unit": "degrees",
    "bench_height_m": "15.0",
    "incl_source_column": "Inclinacion_real",
    "az_source_column": "Azimuth_real",
}


def _upload_csv(client: TestClient, session_id: str, csv_content: str) -> object:
    """Helper: POST a CSV to /api/v1/blast/upload with a full geometry config."""
    data = {"session_id": session_id}
    data.update(GEOMETRY_FORM)
    return client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        data=data,
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
    assert model.design_surface is None


def test_upload_dates_survive_response_and_persistence(client, session_id):
    lines = VALID_CSV.strip().splitlines()
    dated = '\n'.join([lines[0] + ',fecha_tronadura', *(line + ',2026-11-02' for line in lines[1:])])
    response = _upload_csv(client, session_id, dated)
    assert response.status_code == 200, response.text
    assert response.json()['accepted_rows'][0]['fecha_tronadura'] == '2026-11-02'
    assert db.get_settings(session_id)['blast_holes'][0]['fecha_tronadura'] == '2026-11-02'


def test_design_surface_mode_requires_explicit_crs_datum_and_metre_confirmation(client, session_id):
    data = {"session_id": session_id, **GEOMETRY_FORM, "collar_elevation_source": "design_surface"}
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(VALID_CSV.encode()), "text/csv")},
        data=data,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "DESIGN_SURFACE_CONFIRMATION_REQUIRED"


def test_design_surface_mode_never_falls_back_without_session_design_mesh(client, session_id):
    data = {
        "session_id": session_id,
        **GEOMETRY_FORM,
        "collar_elevation_source": "design_surface",
        "spatial_reference_confirmed": "true",
    }
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(VALID_CSV.encode()), "text/csv")},
        data=data,
        headers={"X-Session-ID": session_id},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "DESIGN_SURFACE_NOT_FOUND"


def test_design_surface_mode_rejects_form_session_different_from_request_session(client, session_id):
    data = {
        "session_id": session_id,
        **GEOMETRY_FORM,
        "collar_elevation_source": "design_surface",
        "spatial_reference_confirmed": "true",
    }
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(VALID_CSV.encode()), "text/csv")},
        data=data,
        headers={"X-Session-ID": "another-session"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "SESSION_ID_MISMATCH"


def test_design_surface_upload_samples_xy_alias_and_preserves_per_hole_provenance(client, session_id):
    mesh = trimesh.Trimesh(
        vertices=[[990, 1990, 100], [1020, 1990, 110], [1020, 2030, 110], [990, 2030, 100]],
        faces=[[0, 1, 2], [0, 2, 3]],
        process=False,
    )
    mesh_bytes = mesh.export(file_type="stl")
    mesh_id = db.save_mesh(
        session_id, "design", "design.stl", mesh_bytes,
        len(mesh.vertices), len(mesh.faces),
        {"x_min": 990, "x_max": 1020, "y_min": 1990, "y_max": 2030, "z_min": 100, "z_max": 110},
    )
    csv_text = """Easting,Northing,Inclinacion_real,Azimuth_real,longitud_real,Kilos_Cargados_real,Taco_m,Burden,Esp
1000,2000,15,90,12,150,1.5,3,4
1100,2100,15,90,12,150,1.5,3,4
"""
    data = {
        "session_id": session_id,
        **{key: value for key, value in GEOMETRY_FORM.items() if key != "bench_height_m"},
        "collar_elevation_source": "design_surface",
        "spatial_reference_confirmed": "true",
    }
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(csv_text.encode()), "text/csv")},
        data=data,
        headers={"X-Session-ID": session_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["design_surface"]["mesh_id"] == mesh_id
    assert body["design_surface"]["counts"]["sampled"] == 1
    assert body["design_surface"]["counts"]["outside"] == 1
    assert body["design_surface"]["coverage"] == 0.5
    hole = body["accepted_rows"][0]
    assert hole["surface_sample_status"] == "sampled"
    assert hole["surface_sample_mesh_id"] == mesh_id
    assert hole["Z_collar_semantic"] == "design_surface_estimate"
    assert hole["Easting"] == 1000
    assert hole["Northing"] == 2000
    assert hole["bench_height_status"] == "MISSING"
    assert hole["pf_vol_kgm3"] is None
    assert hole["pf_g_per_ton"] is not None
    assert hole["pf_g_per_ton_net"] is None
    assert any(row["error_code"] == "DESIGN_SURFACE_OUTSIDE" for row in body["rejected_rows"])
    persisted = client.get(f"/api/v1/blast/{session_id}/holes", headers={"X-Session-ID": session_id}).json()
    assert persisted["holes"][0]["surface_sample_mesh_sha256"] == hole["surface_sample_mesh_sha256"]
    export_response = client.get("/api/v1/export/blast-diagnostics", headers={"X-Session-ID": session_id})
    assert export_response.status_code == 200
    workbook = load_workbook(io.BytesIO(export_response.content), read_only=True)
    surface_sheet = workbook["Superficie_Diseno"]
    assert any(row[0] == "mesh_id" and row[1] == mesh_id for row in surface_sheet.iter_rows(values_only=True))


# ---------------------------------------------------------------------------
# 2. Invalid CSV upload returns 400
# ---------------------------------------------------------------------------


def test_upload_invalid_csv_returns_blocking_errors(client, session_id):
    """Remediación 3.2: invalid CSV returns 422 with structured blocking_errors."""
    resp = _upload_csv(client, session_id, INVALID_CSV)
    assert resp.status_code == 422, resp.text
    body = resp.json()
    model = schemas.BlastUploadResponse.model_validate(body)
    # The structured blocking error is preserved in the body — never hidden.
    assert len(model.blocking_errors) > 0
    assert model.blocking_errors[0]["error_code"] == "MISSING_REQUIRED_COLUMN"


def test_upload_rejects_incompatible_inclination_sign_before_processing(client, session_id):
    data = {
        "session_id": session_id,
        **GEOMETRY_FORM,
        "incl_sign_convention": "NEGATIVE_IS_DOWNWARD_DIP",
    }
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(VALID_CSV.encode("utf-8")), "text/csv")},
        data=data,
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "GEOMETRY_INCOMPLETE"
    assert detail["details"]["missing_or_invalid"]["inclination_sign_convention"] == (
        "NEGATIVE_IS_DOWNWARD_DIP requires inclination_convention=DIP_FROM_HORIZONTAL"
    )


def test_upload_decodes_cp1252_csv_without_replacing_spanish_text(client, session_id):
    csv_text = VALID_CSV.replace(
        "Kilos_Cargados_real,", "Observación,Kilos_Cargados_real,"
    ).replace(
        "1000.0,2000.0,100,15.0,90.0,12.0,150.0,",
        "1000.0,2000.0,100,15.0,90.0,12.0,Fracturación,150.0,",
    ).replace(
        "1005.0,2010.0,100,20.0,95.0,13.0,180.0,",
        "1005.0,2010.0,100,20.0,95.0,13.0,Sin daño,180.0,",
    ).replace(
        "1010.0,2020.0,100,18.0,92.0,14.0,210.0,",
        "1010.0,2020.0,100,18.0,92.0,14.0,Sin daño,210.0,",
    )
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(csv_text.encode("cp1252")), "text/csv")},
        data={"session_id": session_id, **GEOMETRY_FORM},
    )

    assert response.status_code == 200, response.text
    assert response.json()["accepted_rows"][0]["Observación"] == "Fracturación"


def test_unused_csv_reader_uses_shared_cp1252_decoder():
    from api.routers.blast import _read_uploaded_csv

    upload = UploadFile(filename="observaciones.csv", file=io.BytesIO("Observación\nFracturación\n".encode("cp1252")))

    frame = _read_uploaded_csv(upload)

    assert frame.loc[0, "Observación"] == "Fracturación"


def test_upload_warns_when_all_declared_inclinations_are_zero_without_reinterpreting_them(client, session_id):
    vertical_csv = VALID_CSV.replace(
        "100,15.0,", "100,0.0,"
    ).replace(
        "100,20.0,", "100,0.0,"
    ).replace(
        "100,18.0,", "100,0.0,"
    )
    response = _upload_csv(client, session_id, vertical_csv)

    assert response.status_code == 200, response.text
    body = response.json()
    warning = next(w for w in body["event_warnings"] if w["warning_code"] == "INCLINATION_ALL_ZERO")
    assert warning["context"] == {
        "source_column": "Inclinacion_real",
        "row_count": 3,
        "inclination_convention": "FROM_VERTICAL",
    }
    assert {row["inclination_normalized_from_vertical_deg"] for row in body["accepted_rows"]} == {0}


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
    data = {}
    data.update(GEOMETRY_FORM)
    resp = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(VALID_CSV.encode("utf-8")), "text/csv")},
        data=data,
    )
    assert resp.status_code == 422
    assert "detail" in resp.json()
