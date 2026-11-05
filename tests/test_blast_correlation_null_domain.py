"""D1 — Voronoi with a persisted null domain must not raise (HTTP 500).

Collinear or too-few collars yield ``domain_area_m2 = None`` once they go
through the blast upload and persistence. Re-running the Voronoi stage on
that stored frame must keep the domain unavailable (NaN), preserve the
per-hole status/warnings, and never coerce the absence into a measured 0 m²
or a conservation pass.
"""

import io
import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.database as db
from core.blast_correlation import _assign_voronoi_global, compute_blast_geotech_correlation
from core.blast_metrics import compute_influence_area_report


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

COLLINEAR_CSV = (
    "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,"
    "longitud_real,Kilos_Cargados_real,fecha_tronadura\n"
    "1000.0,2000.0,100,15.0,90.0,12.0,150.0,2026-05-01\n"
    "1003.0,2002.0,100,15.0,90.0,12.0,150.0,2026-05-02\n"
    "1006.0,2004.0,100,15.0,90.0,12.0,150.0,2026-05-03\n"
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("CONCILIACION_DATA_DIR", str(tmp_path))
    db.init_db()
    yield


@pytest.fixture()
def client():
    from api.main import app

    with TestClient(app) as c:
        yield c


def _collinear_frame(domain_value=None) -> pd.DataFrame:
    df = pd.DataFrame({
        "X": [1000.0, 1003.0, 1006.0],
        "Y": [2000.0, 2002.0, 2004.0],
        "label_pozo": ["P1", "P2", "P3"],
    })
    df["domain_area_m2"] = [domain_value, domain_value, domain_value]
    return df


def test_collinear_voronoi_with_null_domain_column_does_not_raise():
    result = _assign_voronoi_global(_collinear_frame(None))

    assert math.isnan(result["domain_area_m2"])
    assert result["conservation_ok"] is False
    assert result["residual_pct"] != result["residual_pct"]
    assert result["area_m2"].isna().all()
    assert set(result["area_status"]) == {"invalid"}
    assert "dominio no disponible" in result["messages"]


def test_stale_domain_column_is_not_trusted_as_a_measured_domain():
    report = compute_influence_area_report(_collinear_frame(None))

    assert report["area_m2"].isna().all()
    assert report["area_status"].tolist() == ["invalid"] * 3
    assert "domain_area_m2" not in report.columns or report["domain_area_m2"].isna().all()


def test_stale_finite_domain_column_is_never_carried_into_report():
    df = pd.DataFrame({
        "X": [1000.0, 1003.0, 1006.0, 1002.0, 1009.0],
        "Y": [2000.0, 2002.0, 2004.0, 2011.0, 2007.0],
    })
    df["domain_area_m2"] = 999999.0
    report = compute_influence_area_report(df)
    assert not (report["domain_area_m2"] == 999999.0).any()


def _section_obj(name, x, y, az, length=200.0):
    return type(
        "Sec",
        (),
        {"name": name, "origin": np.array([x, y]), "azimuth": az,
         "length": length, "sector": ""},
    )()


def test_correlation_with_collinear_holes_and_null_domain_does_not_raise():
    raw = pd.DataFrame([
        {"label_pozo": f"P{i}", "Latitud_Geo": 1000.0 + 3 * i, "Longitud_Geo": 2000.0 + 2 * i,
         "Nombre_Banco": 100, "Inclinacion_real": 15.0, "Azimuth_real": 90.0,
         "longitud_real": 12.0, "Kilos_Cargados_real": 150.0}
        for i in range(3)
    ])
    from core.calculo_tronadura import procesar_pozos

    holes = procesar_pozos(raw, incl_convention="from_vertical", geometry_user_confirmed=True)[0]
    holes["domain_area_m2"] = None
    sections = [_section_obj("S-01", 1000.0, 2000.0, 90.0)]
    comps = [{"section": "S-01", "delta_crest": 0.3}]
    rows = compute_blast_geotech_correlation(holes, sections, comps)
    assert isinstance(rows, list)


def test_upload_persist_readback_then_correlation_and_damage_do_not_500(client):
    session_id = db.create_session()
    resp = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(COLLINEAR_CSV.encode("utf-8")), "text/csv")},
        data={"session_id": session_id, **GEOMETRY_FORM},
    )
    assert resp.status_code == 200, resp.text

    stored = db.get_settings(session_id)["blast_holes"]
    assert len(stored) == 3
    assert all(pd.isna(h.get("domain_area_m2")) for h in stored)

    db.save_sections(session_id, [{
        "name": "S-01", "origin": [1000.0, 2000.0], "azimuth": 90.0,
        "length": 200.0, "sector": "A",
    }])
    db.save_results(session_id, [{"section": "S-01", "delta_crest": 0.3}])
    headers = {"x-session-id": session_id}

    corr = client.get("/api/v1/process/blast-correlation?survey_date=2026-05-10", headers=headers)
    assert corr.status_code == 200, corr.text

    dmg = client.get("/api/v1/process/blast-correlation/damage-model?survey_date=2026-05-10", headers=headers)
    assert dmg.status_code == 200, dmg.text
