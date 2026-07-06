"""Per-session tunable rock density (ρ) and height fallback for powder factor.

Covers the param-threading chain introduced for gap G14:

    core.blast_correlation.compute_powder_factor(rock_density_tm3=…, height_fallback_m=…)
      → aggregate_powder_factor_by_group(…)
      → compute_blast_geotech_correlation(…)
      → GET /process/blast-correlation  (reads session `blast` settings)

Backend contract:
    * `rock_density_tm3` / `height_fallback_m` default to ``None`` → the
      core falls back to the ``BLAST`` singleton (2.7 ton/m³, 15.0 m), so
      the existing behaviour is preserved.
    * ρ scales ``pf_g_per_ton`` inversely (higher ρ → lower g/ton).
    * The session's ``blast`` block is surfaced by ``GET /settings`` and
      persisted by ``PUT /settings``.
    * ``GET /process/blast-correlation`` reflects a session-customised ρ.
"""

import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.database as db
from core.blast_correlation import (
    aggregate_powder_factor_by_group,
    compute_blast_geotech_correlation,
    compute_powder_factor,
)
from core.config import BLAST


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isolated SQLite DB per test (mirrors tests/test_api.py)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def _hole(
    hole_id: str,
    x: float,
    y: float,
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
        "Z_collar": 100.0,
        "Z_toe": 85.0,
        "X_toe": x,
        "Y_toe": y,
        "longitud_real": length,
        "Inclinacion_real": inclination,
        "Len": length,
        "Burden": burden,
        "Esp": esp,
        "Kilos_Cargados_real": kg,
    }


def _section_dict(name="S-01", origin=(0.0, 0.0), azimuth=0.0, length=200.0, sector="A"):
    return {
        "name": name,
        "origin": list(origin),
        "azimuth": azimuth,
        "length": length,
        "sector": sector,
    }


# ---------------------------------------------------------------------------
# 1. Core: ρ inversely scales pf_g_per_ton; None → BLAST default
# ---------------------------------------------------------------------------


def test_powder_factor_scales_inversely_with_density():
    """pf_g_per_ton with ρ=3.0 must equal (2.7/3.0) × the default-ρ value."""
    df = pd.DataFrame({
        "Kilos_Cargados_real": [100.0],
        "longitud_real": [15.0],
        "Inclinacion_real": [0.0],
        "Burden": [4.0],
        "Esp": [5.0],
        "Nombre_Malla_Original": ["M1"],
    })
    a = compute_powder_factor(df.copy())["pf_g_per_ton"].iloc[0]
    b = compute_powder_factor(df.copy(), rock_density_tm3=3.0)["pf_g_per_ton"].iloc[0]

    assert a == pytest.approx(123.456, rel=1e-3)
    assert b == pytest.approx(a * BLAST.rock_density_tm3 / 3.0, rel=1e-6)
    # Inverse proportionality: ratio of PFs == ratio of densities (3.0/2.7).
    assert a / b == pytest.approx(3.0 / BLAST.rock_density_tm3, rel=1e-6)


def test_powder_factor_none_density_uses_blast_default():
    """Passing None for ρ must reproduce the singleton-default behaviour."""
    df = pd.DataFrame({
        "Kilos_Cargados_real": [100.0],
        "longitud_real": [15.0],
        "Inclinacion_real": [0.0],
        "Burden": [4.0],
        "Esp": [5.0],
        "Nombre_Malla_Original": ["M1"],
    })
    explicit = compute_powder_factor(df.copy(), rock_density_tm3=BLAST.rock_density_tm3)
    defaulted = compute_powder_factor(df.copy())
    assert (
        explicit["pf_g_per_ton"].iloc[0]
        == pytest.approx(defaulted["pf_g_per_ton"].iloc[0], rel=1e-9)
    )


def test_height_fallback_used_when_geometry_missing():
    """When longitud_real is NaN, height_fallback_m drives the PF denominator."""
    base = {
        "Kilos_Cargados_real": [120.0],
        "Inclinacion_real": [0.0],
        "Burden": [4.0],
        "Esp": [5.0],
        "Nombre_Malla_Original": ["M1"],
    }
    df_no_len = pd.DataFrame({**base, "longitud_real": [np.nan]})

    # Custom fallback → PF derived from that height; None → BLAST default.
    custom_h = 20.0
    pf_custom = compute_powder_factor(
        df_no_len.copy(), height_fallback_m=custom_h
    )["pf_g_per_ton"].iloc[0]
    pf_default = compute_powder_factor(df_no_len.copy())["pf_g_per_ton"].iloc[0]

    # PF ∝ 1/H → ratio == default_h / custom_h.
    assert pf_custom / pf_default == pytest.approx(
        BLAST.height_fallback_m / custom_h, rel=1e-6
    )


def test_aggregate_powder_factor_forwards_density_override():
    """aggregate_powder_factor_by_group must forward ρ to compute_powder_factor."""
    df = pd.DataFrame({
        "hole_id": ["H1"],
        "X": [0.0],
        "Y": [10.0],
        "Kilos_Cargados_real": [120.0],
        "longitud_real": [12.0],
        "Inclinacion_real": [0.0],
        "Burden": [3.0],
        "Esp": [4.0],
        "section_name": ["S-01"],
    })
    default_agg = aggregate_powder_factor_by_group(
        df.copy(), "section_name", "S-01", df.copy()
    )
    rho3_agg = aggregate_powder_factor_by_group(
        df.copy(), "section_name", "S-01", df.copy(), rock_density_tm3=3.0
    )
    assert default_agg["pf_g_per_ton_avg"] > 0
    assert rho3_agg["pf_g_per_ton_avg"] == pytest.approx(
        default_agg["pf_g_per_ton_avg"] * BLAST.rock_density_tm3 / 3.0, rel=1e-6
    )


# ---------------------------------------------------------------------------
# 2. compute_blast_geotech_correlation forwards ρ
# ---------------------------------------------------------------------------


def _section_obj(name, x, y, az, length=200.0):
    return type(
        "Sec",
        (),
        {"name": name, "origin": np.array([x, y]), "azimuth": az,
         "length": length, "sector": ""},
    )()


def test_compute_blast_geotech_correlation_forwards_density():
    df = pd.DataFrame([
        {"X": 0.0, "Y": 10.0, "longitud_real": 12.0, "Inclinacion_real": 0.0,
         "Burden": 3.0, "Esp": 4.0, "Kilos_Cargados_real": 200.0},
        {"X": 0.0, "Y": 14.0, "longitud_real": 12.0, "Inclinacion_real": 0.0,
         "Burden": 3.0, "Esp": 4.0, "Kilos_Cargados_real": 200.0},
    ])
    sections = [_section_obj("S-01", 0.0, 0.0, 0.0)]
    comps = [{"section": "S-01", "delta_crest": 0.4}]

    default_rows = compute_blast_geotech_correlation(df, sections, comps)
    rho3_rows = compute_blast_geotech_correlation(
        df, sections, comps, rock_density_tm3=3.0
    )

    pf_default = default_rows[0].pf_g_per_ton_avg
    pf_rho3 = rho3_rows[0].pf_g_per_ton_avg
    assert pf_default > 0
    assert pf_rho3 == pytest.approx(pf_default * BLAST.rock_density_tm3 / 3.0, rel=1e-6)


# ---------------------------------------------------------------------------
# 3. Settings round-trip: GET defaults, PUT blast, GET persists
# ---------------------------------------------------------------------------


def test_get_settings_includes_blast_defaults(client):
    headers = {"x-session-id": db.create_session()}
    resp = client.get("/api/v1/settings", headers=headers)
    assert resp.status_code == 200
    blast = resp.json()["blast"]
    assert blast == {
        "rock_density_tm3": BLAST.rock_density_tm3,
        "height_fallback_m": BLAST.height_fallback_m,
    }


def test_put_settings_blast_persists_and_is_returned(client):
    headers = {"x-session-id": db.create_session()}
    # PUT a custom blast block.
    resp = client.put(
        "/api/v1/settings",
        headers=headers,
        json={"blast": {"rock_density_tm3": 3.1, "height_fallback_m": 14.0}},
    )
    assert resp.status_code == 200
    assert resp.json()["settings"]["blast"] == {
        "rock_density_tm3": 3.1,
        "height_fallback_m": 14.0,
    }

    # A subsequent GET must echo the persisted values (deep-merged over defaults).
    get_resp = client.get("/api/v1/settings", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["blast"] == {
        "rock_density_tm3": 3.1,
        "height_fallback_m": 14.0,
    }


def test_put_settings_blast_partial_update_preserves_other_keys(client):
    """PUT-ing only rock_density_tm3 must preserve a previously set height."""
    headers = {"x-session-id": db.create_session()}
    client.put(
        "/api/v1/settings",
        headers=headers,
        json={"blast": {"rock_density_tm3": 2.9, "height_fallback_m": 13.0}},
    )
    client.put(
        "/api/v1/settings",
        headers=headers,
        json={"blast": {"rock_density_tm3": 3.2}},
    )
    blast = client.get("/api/v1/settings", headers=headers).json()["blast"]
    assert blast["rock_density_tm3"] == 3.2
    assert blast["height_fallback_m"] == 13.0  # preserved


# ---------------------------------------------------------------------------
# 4. Endpoint reflects a session-customised ρ in pf_g_per_ton_avg
# ---------------------------------------------------------------------------


def _seed_happy_path(client):
    headers = {"x-session-id": db.create_session()}
    db.save_sections(headers["x-session-id"], [_section_dict()])
    db.save_settings(headers["x-session-id"], {
        "blast_holes": [
            _hole("H001", x=0.0, y=10.0, kg=180.0, burden=3.0, esp=4.0, length=12.0),
            _hole("H002", x=0.0, y=12.0, kg=220.0, burden=3.0, esp=4.0, length=12.0),
        ],
    })
    db.save_results(headers["x-session-id"], [{"section": "S-01", "delta_crest": 0.3}])
    return headers


def test_blast_correlation_endpoint_reflects_session_density(client):
    headers = _seed_happy_path(client)

    # Baseline PF with default ρ.
    base = client.get("/api/v1/process/blast-correlation", headers=headers).json()
    pf_base = base["rows"][0]["pf_g_per_ton_avg"]
    assert pf_base > 0

    # Override ρ to 3.0 via PUT /settings.
    client.put(
        "/api/v1/settings",
        headers=headers,
        json={"blast": {"rock_density_tm3": 3.0, "height_fallback_m": 15.0}},
    )

    after = client.get("/api/v1/process/blast-correlation", headers=headers).json()
    pf_after = after["rows"][0]["pf_g_per_ton_avg"]

    # Higher ρ → lower PF, ratio == 2.7/3.0.
    assert pf_after == pytest.approx(pf_base * BLAST.rock_density_tm3 / 3.0, rel=1e-3)
    assert pf_after < pf_base
