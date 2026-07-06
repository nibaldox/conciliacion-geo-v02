"""G13 visual — PF↔damage OLS model endpoint.

Exercises ``GET /api/v1/process/blast-correlation/damage-model``, which
wraps :func:`core.blast_model.fit_powder_factor_damage_model` over the
per-section ``pf_g_per_ton`` and ``avg_over_break`` metrics resolved by the
same data flow as ``GET /process/blast-correlation``.

The fixture pattern mirrors ``tests/test_blast_correlation_endpoint.py``
(isolated SQLite + TestClient + seeded sections / results / blast-holes).
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
# 1. Empty cases → 200 with points=[] and fit=null
# ---------------------------------------------------------------------------


def test_empty_when_no_blast_holes_and_no_results(client):
    headers = _seed_session(client)
    resp = client.get(
        "/api/v1/process/blast-correlation/damage-model", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["points"] == []
    assert data["fit"] is None
    assert data["x_metric"] == "pf_g_per_ton"
    assert data["y_metric"] == "over_break"


def test_empty_when_results_but_no_blast_holes(client):
    headers = _seed_session(client)
    session_id = headers["x-session-id"]
    db.save_results(session_id, [{"section": "S-01", "delta_crest": 0.4}])
    resp = client.get(
        "/api/v1/process/blast-correlation/damage-model", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["points"] == []
    assert resp.json()["fit"] is None


def test_empty_when_blast_holes_but_no_results(client):
    headers = _seed_session(client)
    session_id = headers["x-session-id"]
    db.save_settings(session_id, {"blast_holes": [_hole("H001", 0.0, 10.0)]})
    resp = client.get(
        "/api/v1/process/blast-correlation/damage-model", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["points"] == []


# ---------------------------------------------------------------------------
# 2. Seeded case: ≥5 sections each with pf_g_per_ton + overbreak → fit present
# ---------------------------------------------------------------------------


def test_seeded_session_returns_points_and_fit(client):
    """Five sections, each with positive delta_crest (overbreak), should
    produce a populated points list and a non-null fit with n>=5 and a
    set confidence label."""
    # 5 sections along the X axis; each gets 2 blast holes nearby so the
    # powder factor is non-zero, and a positive delta_crest so overbreak>0.
    sections = [
        _section_dict(
            name=f"S-{i:02d}",
            origin=(float(i * 50.0), 0.0),
            azimuth=0.0,
        )
        for i in range(5)
    ]
    headers = _seed_session(client, sections)
    session_id = headers["x-session-id"]

    # Two holes per section, offset along the section axis, distinct kg so
    # the per-section PF varies across sections.
    holes = []
    for i in range(5):
        x = float(i * 50.0)
        holes.append(_hole(f"H-{i}-a", x=x + 1.0, y=10.0, kg=150.0 + i * 20.0))
        holes.append(_hole(f"H-{i}-b", x=x + 3.0, y=10.0, kg=180.0 + i * 15.0))
    db.save_settings(session_id, {"blast_holes": holes})

    # Distinct positive delta_crest per section so overbreak varies.
    results = []
    for i in range(5):
        results.append({"section": f"S-{i:02d}", "delta_crest": 0.3 + i * 0.15})
    db.save_results(session_id, results)

    resp = client.get(
        "/api/v1/process/blast-correlation/damage-model", headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert isinstance(data["points"], list)
    assert len(data["points"]) == 5
    for pt in data["points"]:
        assert pt["section_name"].startswith("S-")
        assert pt["pf_g_per_ton"] > 0
        assert pt["over_break"] > 0
        # NaN-safety
        assert math.isfinite(pt["pf_g_per_ton"])
        assert math.isfinite(pt["over_break"])

    fit = data["fit"]
    assert fit is not None, "expected a non-null fit with 5 valid points"
    assert fit["n"] >= 5
    assert fit["confidence"] in {"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"}
    assert fit["confidence"] != "INSUFFICIENT", (
        f"expected a real fit, got INSUFFICIENT: {fit}"
    )
    for f in ("beta0", "beta1", "r_squared", "p_value",
              "ci_beta1_low", "ci_beta1_high"):
        assert math.isfinite(fit[f]), f"non-finite {f}: {fit[f]!r}"


def test_response_schema_is_correct(client):
    """The response validates against BlastDamageModelResponse and the
    fit shape matches BlastDamageModelFitSchema fields."""
    sections = [
        _section_dict(name=f"S-{i:02d}", origin=(float(i * 50.0), 0.0))
        for i in range(6)
    ]
    headers = _seed_session(client, sections)
    session_id = headers["x-session-id"]

    holes = []
    for i in range(6):
        x = float(i * 50.0)
        holes.append(_hole(f"H-{i}-a", x=x + 1.0, y=10.0, kg=160.0 + i * 10.0))
        holes.append(_hole(f"H-{i}-b", x=x + 3.0, y=10.0, kg=190.0 + i * 10.0))
    db.save_settings(session_id, {"blast_holes": holes})

    results = [
        {"section": f"S-{i:02d}", "delta_crest": 0.4 + i * 0.1}
        for i in range(6)
    ]
    db.save_results(session_id, results)

    resp = client.get(
        "/api/v1/process/blast-correlation/damage-model", headers=headers
    )
    assert resp.status_code == 200

    model = schemas.BlastDamageModelResponse.model_validate(resp.json())
    assert len(model.points) == 6
    assert model.fit is not None
    assert set(schemas.BlastDamageModelFitSchema.model_fields.keys()) == {
        "beta0", "beta1", "r_squared", "p_value", "n",
        "confidence", "ci_beta1_low", "ci_beta1_high",
    }
    assert set(schemas.BlastDamagePointSchema.model_fields.keys()) == {
        "section_name", "pf_g_per_ton", "over_break",
    }


# ---------------------------------------------------------------------------
# 3. Under-sample guard: <5 valid points → fit is null even with rows
# ---------------------------------------------------------------------------


def test_under_sample_returns_null_fit(client):
    """Four sections with valid PF + overbreak: points are returned but the
    fit must be null because the fitter requires min_samples=5."""
    sections = [
        _section_dict(name=f"S-{i:02d}", origin=(float(i * 50.0), 0.0))
        for i in range(4)
    ]
    headers = _seed_session(client, sections)
    session_id = headers["x-session-id"]

    holes = []
    for i in range(4):
        x = float(i * 50.0)
        holes.append(_hole(f"H-{i}-a", x=x + 1.0, y=10.0, kg=150.0))
    db.save_settings(session_id, {"blast_holes": holes})

    results = [
        {"section": f"S-{i:02d}", "delta_crest": 0.3 + i * 0.1}
        for i in range(4)
    ]
    db.save_results(session_id, results)

    resp = client.get(
        "/api/v1/process/blast-correlation/damage-model", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) == 4
    assert data["fit"] is None


# ---------------------------------------------------------------------------
# 4. Zero-PF rows are dropped from the points list
# ---------------------------------------------------------------------------


def _hole_no_geometry(
    hole_id: str,
    x: float,
    y: float,
    z_collar: float = 100.0,
    kg: float = 200.0,
) -> dict:
    """Blast hole that projects onto a section but yields zero/NaN PF."""
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


def test_zero_pf_rows_dropped_from_points(client):
    """Sections whose PF is zero (no valid geometry) must NOT appear in the
    points list — they are dropped before fitting, so the emitted points
    match the samples the fit consumed."""
    sections = [
        _section_dict(name=f"S-{i:02d}", origin=(float(i * 50.0), 0.0))
        for i in range(2)
    ]
    headers = _seed_session(client, sections)
    session_id = headers["x-session-id"]

    # Section S-00 gets a hole with no geometry → PF=0 (dropped).
    # Section S-01 gets a valid hole → PF>0 (kept).
    db.save_settings(session_id, {
        "blast_holes": [
            _hole_no_geometry("H-bad", x=1.0, y=10.0),
            _hole("H-good", x=51.0, y=10.0, kg=200.0),
        ],
    })
    db.save_results(session_id, [
        {"section": "S-00", "delta_crest": 0.5},
        {"section": "S-01", "delta_crest": 0.5},
    ])

    resp = client.get(
        "/api/v1/process/blast-correlation/damage-model", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) == 1
    assert data["points"][0]["section_name"] == "S-01"
    assert data["fit"] is None  # only 1 valid point → INSUFFICIENT
