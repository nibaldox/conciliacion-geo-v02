"""REST parity for ``GET /blast/{session_id}/summary`` and the agent digest.

Both surfaces read ``blast_summary_payload`` (api/routers/blast.py), so the
session counts, data status and upload reports they expose must agree.
A real CSV upload produces the stored settings; nothing is hand-seeded here.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import api.database as db
import api.schemas as schemas
from api.ai_agent_handlers import READ_HANDLERS
from api.routers.blast import blast_summary_payload
from core.ai_v2.agent.models import NoArgs

VALID_CSV = """\
Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real,Kilos_Cargados_real,Taco_m,Burden,Esp,Diam_mm
1000.0,2000.0,100,15.0,90.0,12.0,150.0,1.5,3.0,4.0,200
1005.0,2010.0,100,20.0,95.0,13.0,180.0,2.0,3.2,4.1,200
1010.0,2020.0,100,18.0,92.0,14.0,210.0,2.5,3.5,4.2,200
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


@pytest.fixture(autouse=True)
def isolated_db(api_isolated_db):
    yield


@pytest.fixture()
def client(api_test_client):
    return api_test_client


def _upload(client: TestClient, session_id: str) -> None:
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(VALID_CSV.encode("utf-8")), "text/csv")},
        data={"session_id": session_id, **GEOMETRY_FORM},
    )
    assert response.status_code == 200, response.text


def test_rest_summary_body_is_the_shared_helper_payload(client):
    session_id = db.create_session()
    _upload(client, session_id)

    response = client.get(
        f"/api/v1/blast/{session_id}/summary",
        headers={"x-session-id": session_id},
    )

    assert response.status_code == 200
    projected = schemas.BlastSessionSummary.model_validate(
        blast_summary_payload(db.get_settings(session_id))
    ).model_dump(mode="json")
    assert response.json() == projected


@pytest.mark.asyncio
async def test_agent_digest_counts_match_rest_summary(client):
    session_id = db.create_session()
    _upload(client, session_id)
    rest = client.get(
        f"/api/v1/blast/{session_id}/summary",
        headers={"x-session-id": session_id},
    ).json()

    digest = await READ_HANDLERS["get_blast_summary"](session_id, NoArgs())

    assert digest["ok"] is True
    assert digest["n_holes"] == rest["n_holes"] == 3
    assert digest["data_status"] == rest["data_status"] == "current"
    assert digest["dedup"]["rows_in"] == rest["consolidation_report"]["rows_in"]
    assert digest["dedup"]["exact_copies_removed"] == rest["consolidation_report"]["exact_copies_removed"]
    assert digest["dedup"]["holes_with_decks"] == rest["consolidation_report"]["holes_with_decks"]
    assert digest["footprint"]["mode"] == rest["footprint_report"]["mode"]
    assert digest["footprint"]["n_estimated"] == rest["footprint_report"]["n_estimated"]
    assert digest["footprint"]["n_user"] == rest["footprint_report"]["n_user"]
    assert digest["footprint"]["n_missing"] == rest["footprint_report"]["n_missing"]
