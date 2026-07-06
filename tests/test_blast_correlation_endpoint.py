"""G13 — Backend endpoint for blast↔geotech correlation (incl. PF in g/ton).

Exercises ``GET /api/v1/process/blast-correlation`` which wraps
``core.blast_correlation.compute_blast_geotech_correlation`` — the same
primitive used by the Streamlit reference and the Excel/Word writers — so the
web frontend, CLI and reports consume identical numbers.

The endpoint surfaces the per-mass powder factor (``pf_g_per_ton_avg``, g/ton)
alongside the volume/area/energy metrics.

Blast holes are seeded into the session settings dict under the ``"blast_holes"``
key (read by ``_load_session_blast_holes``). Comparison rows are seeded via
``db.save_results`` (read back by ``db.get_results`` as ``List[Dict]``).
"""

import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.database as db
import api.schemas as schemas
from core.blast_correlation import compute_blast_geotech_correlation
from core.calculo_tronadura import procesar_pozos


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
    length: float = 12.0,
    inclination: float = 0.0,
    kg: float = 200.0,
) -> dict:
    return {
        "hole_id": hole_id,
        "X": x,
        "Y": y,
        "Z_collar": z_collar,
        "Z_toe": z_toe,
        "X_toe": x,
        "Y_toe": y,
        "longitud_real": length,
        "Inclinacion_real": inclination,
        "Len": length,
        "Burden": burden,
        "Esp": esp,
        "Kilos_Cargados_real": kg,
    }


def _seed_session(client, sections=None) -> dict:
    headers = {"x-session-id": db.create_session()}
    db.save_sections(headers["x-session-id"], sections or [_section_dict()])
    return headers


# ---------------------------------------------------------------------------
# 1. Empty case: no blast holes / no results → 200 with empty rows
# ---------------------------------------------------------------------------


def test_empty_when_no_blast_holes_and_no_results(client):
    headers = _seed_session(client)
    resp = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows"] == []
    assert data["n_sections"] == 1


def test_empty_when_results_but_no_blast_holes(client):
    headers = _seed_session(client)
    session_id = headers["x-session-id"]
    db.save_results(session_id, [{"section": "S-01", "delta_crest": 0.4}])
    resp = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["rows"] == []


def test_empty_when_blast_holes_but_no_results(client):
    headers = _seed_session(client)
    session_id = headers["x-session-id"]
    db.save_settings(session_id, {"blast_holes": [_hole("H001", 0.0, 10.0)]})
    resp = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["rows"] == []


def test_empty_when_no_sections(client):
    headers = {"x-session-id": db.create_session()}
    db.save_settings(headers["x-session-id"], {"blast_holes": [_hole("H001", 0.0, 10.0)]})
    db.save_results(headers["x-session-id"], [{"section": "S-01", "delta_crest": 0.4}])
    resp = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["rows"] == []


# ---------------------------------------------------------------------------
# 2. Happy path: holes + sections + comparisons → rows with pf_g_per_ton_avg
# ---------------------------------------------------------------------------


def test_happy_path_returns_rows_with_pf_g_per_ton(client):
    headers = _seed_session(client, [_section_dict(name="S-01", origin=(0.0, 0.0), azimuth=0.0)])
    session_id = headers["x-session-id"]

    db.save_settings(session_id, {
        "blast_holes": [
            _hole("H001", x=0.0, y=10.0, kg=180.0, burden=3.0, esp=4.0, length=12.0),
            _hole("H002", x=0.0, y=12.0, kg=220.0, burden=3.0, esp=4.0, length=12.0),
        ],
    })
    db.save_results(session_id, [
        {"section": "S-01", "delta_crest": 0.3},
        {"section": "S-01", "delta_crest": -0.5},
    ])

    resp = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 1

    row = data["rows"][0]
    assert row["section_name"] == "S-01"
    assert row["num_wells"] == 2
    assert row["mean_abs_deviation"] == pytest.approx(0.4, abs=1e-3)
    assert isinstance(row["pf_g_per_ton_avg"], float)
    assert row["pf_g_per_ton_avg"] > 0
    assert row["total_kg"] == pytest.approx(400.0, abs=1e-3)
    assert row["n_over"] == 1
    assert row["n_under"] == 1


def test_response_schema_is_correct(client):
    headers = _seed_session(client, [_section_dict(name="S-01", origin=(0.0, 0.0), azimuth=0.0)])
    session_id = headers["x-session-id"]
    db.save_settings(session_id, {"blast_holes": [_hole("H001", x=0.0, y=10.0)]})
    db.save_results(session_id, [{"section": "S-01", "delta_crest": 0.3}])

    resp = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert resp.status_code == 200

    model = schemas.BlastCorrelationResponse.model_validate(resp.json())
    assert len(model.rows) == 1
    assert isinstance(model.rows[0], schemas.BlastCorrelationRowSchema)
    assert set(schemas.BlastCorrelationRowSchema.model_fields.keys()) == {
        "section_name", "num_wells", "total_kg", "mean_abs_deviation",
        "avg_over_break", "avg_under_break", "n_over", "n_under",
        "pf_vol_avg_kgm3", "pf_area_avg_kgm2", "pf_g_per_ton_avg",
        "energy_total_mj", "n_pf_valid",
    }


# ---------------------------------------------------------------------------
# 3. Contract guard: the core primitive emits pf_g_per_ton_avg on every row
# ---------------------------------------------------------------------------


def _section_obj(name, x, y, az, length=200.0):
    return type(
        "Sec",
        (),
        {"name": name, "origin": np.array([x, y]), "azimuth": az,
         "length": length, "sector": ""},
    )()


def test_compute_blast_geotech_correlation_emits_pf_g_per_ton():
    raw = pd.DataFrame([
        {"label_pozo": "P-1", "Latitud_Geo": 10.0, "Longitud_Geo": 0.0,
         "Nombre_Banco": 4000.0, "Inclinacion_real": 0.0, "Azimuth_real": 0.0,
         "longitud_real": 10.0, "Kilos_Cargados_real": 200.0,
         "fecha_tronadura": "2026-07-01"},
        {"label_pozo": "P-2", "Latitud_Geo": 14.0, "Longitud_Geo": 0.0,
         "Nombre_Banco": 4000.0, "Inclinacion_real": 0.0, "Azimuth_real": 0.0,
         "longitud_real": 10.0, "Kilos_Cargados_real": 200.0,
         "fecha_tronadura": "2026-07-01"},
    ])
    df = procesar_pozos(raw)[0]
    sections = [_section_obj("S-01", 0.0, 0.0, 0.0)]
    comps = [{"section": "S-01", "delta_crest": 0.4}]

    rows = compute_blast_geotech_correlation(df, sections, comps)
    assert len(rows) == 1
    r = rows[0]
    assert r.section_name == "S-01"
    assert r.num_wells == 2
    assert hasattr(r, "pf_g_per_ton_avg")
    assert isinstance(r.pf_g_per_ton_avg, float)
    assert r.pf_g_per_ton_avg > 0


# ---------------------------------------------------------------------------
# 4. Regression: NaN powder-factor must not crash the endpoint (HTTP 500).
#    Holes that project onto the section but lack Burden/Esp/longitud_real
#    produce NaN PF in the aggregate; the endpoint must serialise 0.0 instead.
# ---------------------------------------------------------------------------


def _hole_no_geometry(
    hole_id: str,
    x: float,
    y: float,
    z_collar: float = 100.0,
    kg: float = 200.0,
) -> dict:
    """Blast hole that projects onto a section but yields NaN PF (no geometry)."""
    return {
        "hole_id": hole_id,
        "X": x,
        "Y": y,
        "Z_collar": z_collar,
        "Z_toe": z_collar,
        "X_toe": x,
        "Y_toe": y,
        "longitud_real": np.nan,
        "Inclinacion_real": np.nan,
        "Len": np.nan,
        "Burden": np.nan,
        "Esp": np.nan,
        "Kilos_Cargados_real": kg,
    }


def test_nan_powder_factor_returns_200_with_finite_fields(client):
    headers = _seed_session(client, [_section_dict(name="S-01", origin=(0.0, 0.0), azimuth=0.0)])
    session_id = headers["x-session-id"]

    db.save_settings(session_id, {
        "blast_holes": [_hole_no_geometry("H001", x=0.0, y=10.0)],
    })
    db.save_results(session_id, [{"section": "S-01", "delta_crest": 0.3}])

    resp = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["rows"], list)
    assert len(data["rows"]) == 1

    row = data["rows"][0]
    numeric_fields = [
        "total_kg", "mean_abs_deviation", "avg_over_break", "avg_under_break",
        "pf_vol_avg_kgm3", "pf_area_avg_kgm2", "pf_g_per_ton_avg",
        "energy_total_mj",
    ]
    for f in numeric_fields:
        assert math.isfinite(row[f]), f"non-finite value for {f}: {row[f]!r}"

    assert row["pf_vol_avg_kgm3"] == 0.0
    assert row["pf_area_avg_kgm2"] == 0.0
    assert row["pf_g_per_ton_avg"] == 0.0
    assert row["n_pf_valid"] == 0


def test_compute_blast_geotech_correlation_never_emits_nan_pf_when_geometry_missing():
    """Holes that survive procesar_pozos but yield NaN PF (kg missing) must
    not leak NaN into the BlastCorrelationRow — they become 0.0, with
    n_pf_valid==0 conveying the no-valid-PF signal."""
    raw = pd.DataFrame([
        {"label_pozo": "P-1", "Latitud_Geo": 10.0, "Longitud_Geo": 0.0,
         "Nombre_Banco": 4000.0, "Inclinacion_real": 0.0, "Azimuth_real": 0.0,
         "longitud_real": 10.0, "Kilos_Cargados_real": np.nan,
         "fecha_tronadura": "2026-07-01"},
        {"label_pozo": "P-2", "Latitud_Geo": 14.0, "Longitud_Geo": 0.0,
         "Nombre_Banco": 4000.0, "Inclinacion_real": 0.0, "Azimuth_real": 0.0,
         "longitud_real": 10.0, "Kilos_Cargados_real": np.nan,
         "fecha_tronadura": "2026-07-01"},
    ])
    df = procesar_pozos(raw)[0]
    assert len(df) > 0
    sections = [_section_obj("S-01", 0.0, 0.0, 0.0)]
    comps = [{"section": "S-01", "delta_crest": 0.4}]

    rows = compute_blast_geotech_correlation(df, sections, comps)
    assert len(rows) == 1
    r = rows[0]
    for f in ("pf_vol_avg_kgm3", "pf_area_avg_kgm2", "pf_g_per_ton_avg",
              "energy_total_mj"):
        v = getattr(r, f)
        assert math.isfinite(v), f"non-finite {f}: {v!r}"
        assert v == 0.0
    assert r.n_pf_valid == 0
