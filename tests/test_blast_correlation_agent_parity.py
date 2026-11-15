"""REST parity for the agent's blast correlation and damage-model digests.

``get_blast_correlation`` and ``get_blast_damage_model`` read the same sync
helpers as ``GET /process/blast-correlation`` and
``GET /process/blast-correlation/damage-model``. A real CSV upload produces the
stored holes (with a real survey-date column) and every number here is checked
against the REST body of the same session, so the digest cannot drift from the
endpoint it summarizes.
"""
from __future__ import annotations

import io
from datetime import date

import pytest
from fastapi.testclient import TestClient

import api.database as db
from api.ai_agent_handlers import READ_HANDLERS
from core.ai_v2.agent.models import BlastCorrelationArgs, BlastDamageArgs
from core.compliance_status import STATUS_CUMPLE

_HEADER = (
    "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,"
    "longitud_real,Kilos_Cargados_real,Taco_m,Burden,Esp,Diam_mm,fecha_tronadura"
)

_FORM = {
    "geometry_user_confirmed": "true",
    "incl_convention": "from_vertical",
    "incl_sign_convention": "ABSOLUTE_VALUE",
    "az_convention": "CLOCKWISE_FROM_NORTH",
    "angle_unit": "degrees",
    "bench_height_m": "15.0",
    "incl_source_column": "Inclinacion_real",
    "az_source_column": "Azimuth_real",
    "date_source_column": "fecha_tronadura",
    "date_format": "ISO",
}


@pytest.fixture(autouse=True)
def isolated_db(api_isolated_db):
    yield


@pytest.fixture()
def client(api_test_client):
    return api_test_client


def _grid_csv() -> str:
    lines = [_HEADER]
    for row in range(10):
        blast_date = "2026-05-01" if row < 5 else "2026-06-20"
        for column in range(6):
            x = 1000.0 + 2.0 * column
            y = 2000.0 + 1.0 * row
            kilos = 100.0 + 50.0 * column
            lines.append(
                f"{x:.3f},{y:.3f},100,0.0,0.0,12.0,{kilos:.1f},1.5,3.0,4.0,200,{blast_date}"
            )
    return "\n".join(lines) + "\n"


def _seed(client: TestClient) -> str:
    session_id = db.create_session()
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(_grid_csv().encode("utf-8")), "text/csv")},
        data={"session_id": session_id, **_FORM},
    )
    assert response.status_code == 200, response.text
    sections = []
    results = []
    for k in range(6):
        name = f"S-0{k + 1}"
        sections.append(
            {
                "name": name,
                "origin": [1000.0 + 2.0 * k, 2000.0],
                "azimuth": 0.0,
                "length": 20.0,
                "length_up": None,
                "length_down": None,
                "sector": "Norte",
            }
        )
        results.append(
            {
                "section": name,
                "sector": "Norte",
                "bench_num": 1,
                "bench_num_topo": 1,
                "type": "MATCH",
                "level": "1000",
                "height_status": STATUS_CUMPLE,
                "angle_status": STATUS_CUMPLE,
                "berm_status": STATUS_CUMPLE,
                "section_status": STATUS_CUMPLE,
                "section_score": 85.0,
                "delta_crest": 0.4 + 0.2 * k,
                "delta_toe": -0.8,
            }
        )
    db.save_sections(session_id, sections)
    db.save_results(session_id, results)
    return session_id


def _rest(client: TestClient, session_id: str, path: str, **params):
    response = client.get(
        f"/api/v1/process/{path}",
        params=params,
        headers={"x-session-id": session_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_correlation_rows_match_rest_with_survey_date_filter(client):
    session_id = _seed(client)
    rest = _rest(
        client, session_id, "blast-correlation", tolerance=1.0, survey_date="2026-06-01"
    )
    digest = await READ_HANDLERS["get_blast_correlation"](
        session_id, BlastCorrelationArgs(tolerance=1.0, survey_date=date(2026, 6, 1))
    )

    assert digest["ok"] is True
    assert digest["data_status"] == rest["data_status"]
    assert digest["n_sections"] == rest["n_sections"] == 6
    assert digest["tolerance"]["value"] == rest["tolerance"] == 1.0
    for key in ("enabled", "survey_date", "effective_cutoff_date", "included", "excluded", "missing"):
        assert digest["temporal_filter"][key] == rest["temporal_filter"][key], key
    assert digest["temporal_filter"]["included"] == 30
    assert digest["temporal_filter"]["excluded"] == 30

    rest_rows = {row["section_name"]: row for row in rest["rows"]}
    assert len(digest["rows"]) == len(rest_rows)
    for row in digest["rows"]:
        source = rest_rows[row["section"]]
        assert row["wells"] == source["num_wells"]
        assert row["kg"] == pytest.approx(source["total_kg"], abs=0.051)
        assert row["pf_g_per_ton"] == pytest.approx(source["pf_g_per_ton_avg"], abs=0.051)
        if source["avg_over_break"] is None:
            assert row["over_break"] is None
        else:
            assert row["over_break"] == pytest.approx(source["avg_over_break"], abs=0.006)


@pytest.mark.asyncio
async def test_correlation_rows_report_pf_voronoi_missing_density_as_rest_does(client):
    session_id = _seed(client)
    rest = _rest(client, session_id, "blast-correlation", tolerance=1.0)
    digest = await READ_HANDLERS["get_blast_correlation"](
        session_id, BlastCorrelationArgs(tolerance=1.0)
    )

    assert digest["magnitudes"]["rock_density"]["status"] == "DEFAULT"
    rest_rows = {row["section_name"]: row for row in rest["rows"]}
    for row in digest["rows"]:
        counts = rest_rows[row["section"]]["pf_voronoi_bench_status_counts"]
        blockers = set(row["pf_voronoi_status"].split(","))
        assert "VALID" not in blockers
        assert "MISSING_DENSITY" in blockers
        assert blockers == {"MISSING_DENSITY"} | (set(counts) - {"VALID"})


@pytest.mark.asyncio
async def test_damage_model_points_and_fit_match_rest(client):
    session_id = _seed(client)
    rest = _rest(client, session_id, "blast-correlation/damage-model", tolerance=1.0)
    digest = await READ_HANDLERS["get_blast_damage_model"](
        session_id, BlastDamageArgs(tolerance=1.0)
    )

    assert digest["ok"] is True
    assert digest["data_status"] == rest["data_status"]
    assert digest["n_points"] == len(rest["points"]) == 6
    rest_points = rest["points"][:12]
    assert len(digest["points"]) == len(rest_points)
    for row, point in zip(digest["points"], rest_points):
        assert row["section"] == point["section_name"]
        assert row["pf_g_per_ton"] == pytest.approx(point["pf_g_per_ton"], abs=0.051)
        assert row["over_break"] == pytest.approx(point["over_break"], abs=0.006)

    assert rest["fit"] is not None
    assert digest["fit_status"] == "FIT"
    assert digest["fit"]["n"] == rest["fit"]["n"]
    assert digest["fit"]["beta0_m"] == pytest.approx(rest["fit"]["beta0"], rel=1e-3, abs=1e-6)
    assert digest["fit"]["beta1_m_per_gt"] == pytest.approx(rest["fit"]["beta1"], rel=1e-3, abs=1e-9)
    assert digest["fit"]["confidence"] == rest["fit"]["confidence"]
    assert digest["temporal_filter"]["enabled"] == rest["temporal_filter"]["enabled"]
