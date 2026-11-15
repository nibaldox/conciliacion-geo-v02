"""Section edit parity: REST ``PUT``/``DELETE /sections/{id}`` and the agent tools.

The REST golden tests pin the current status codes, error details and
response bodies of the two endpoints, so extracting their helpers cannot
change what clients receive. The agent tests run ``update_section`` and
``delete_section`` on an identical seeded session and require the same
stored state (sections, results, extraction cache, pipeline status) as the
REST call does.
"""
from __future__ import annotations

import pytest

import api.database as db
import api.ai_agent_write_handlers as write_handlers
from core.ai_v2.agent.models import SectionCurveArgs, SectionDeleteArgs, SectionUpdateArgs

SESSION_REST = "sec-parity-rest"
SESSION_AGENT = "sec-parity-agent"
PUT_URL = "/api/v1/sections/{section_id}"
DELETE_URL = "/api/v1/sections/{section_id}"


def _section(name: str, x: float = 0.0, sector: str = "Principal") -> dict:
    return {
        "name": name,
        "origin": [x, 0.0],
        "azimuth": 0.0,
        "length": 60.0,
        "length_up": None,
        "length_down": None,
        "sector": sector,
    }


def _seed(session_id: str, names: tuple[str, ...]) -> None:
    db.get_or_create_session(session_id)
    db.save_sections(
        session_id,
        [_section(name, 10.0 * index) for index, name in enumerate(names)],
    )
    db.save_results(
        session_id,
        [{"section": name, "section_status": "CUMPLE"} for name in names],
    )
    db.save_extraction(session_id, names[0], "design", {"points": [[0.0, 0.0]]})
    db.update_process_status(session_id, "complete", len(names), len(names), len(names))


def _state(session_id: str) -> dict:
    return {
        "sections": db.get_sections(session_id),
        "results": db.get_results(session_id),
        "extraction": db.get_extraction(session_id, "S-01", "design"),
        "status": db.get_process_status(session_id),
    }


def _headers(session_id: str) -> dict:
    return {"X-Session-ID": session_id}


# ---------------------------------------------------------------------------
# REST golden: current behaviour, pinned before the helper extraction
# ---------------------------------------------------------------------------


class TestRestSectionEditGolden:
    def test_put_replaces_fields_and_invalidates_analysis(self, api_test_client):
        _seed(SESSION_REST, ("S-01", "S-02"))
        body = {
            "name": "S-02b",
            "origin": [5.0, 6.0],
            "azimuth": 45.678,
            "length": 80.0,
            "length_up": 40.0,
            "length_down": None,
            "sector": "Norte",
        }
        response = api_test_client.put(
            PUT_URL.format(section_id=1), json=body, headers=_headers(SESSION_REST)
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": "1",
            "name": "S-02b",
            "origin": [5.0, 6.0],
            "azimuth": 45.68,
            "length": 80.0,
            "length_up": 40.0,
            "length_down": None,
            "sector": "Norte",
        }
        state = _state(SESSION_REST)
        assert state["sections"][1] == {
            "name": "S-02b",
            "origin": [5.0, 6.0],
            "azimuth": 45.68,
            "length": 80.0,
            "length_up": 40.0,
            "length_down": None,
            "sector": "Norte",
        }
        assert state["results"] == []
        assert state["extraction"] is None
        assert state["status"]["status"] == "idle"

    def test_put_identical_body_keeps_analysis(self, api_test_client):
        _seed(SESSION_REST, ("S-01", "S-02"))
        body = {
            "name": "S-02",
            "origin": [10.0, 0.0],
            "azimuth": 0.0,
            "length": 60.0,
            "length_up": None,
            "length_down": None,
            "sector": "Principal",
        }
        response = api_test_client.put(
            PUT_URL.format(section_id=1), json=body, headers=_headers(SESSION_REST)
        )
        assert response.status_code == 200
        assert len(db.get_results(SESSION_REST)) == 2
        assert db.get_extraction(SESSION_REST, "S-01", "design") is not None
        assert db.get_process_status(SESSION_REST)["status"] == "complete"

    def test_put_without_name_keeps_stored_name(self, api_test_client):
        _seed(SESSION_REST, ("S-01", "S-02"))
        body = {"origin": [1.0, 1.0], "azimuth": 0.0}
        response = api_test_client.put(
            PUT_URL.format(section_id=0), json=body, headers=_headers(SESSION_REST)
        )
        assert response.status_code == 200
        assert response.json()["name"] == "S-01"
        assert response.json()["sector"] == ""

    def test_put_duplicate_name_is_still_accepted_by_rest(self, api_test_client):
        _seed(SESSION_REST, ("S-01", "S-02"))
        response = api_test_client.put(
            PUT_URL.format(section_id=1),
            json={"name": "S-01", "origin": [10.0, 0.0], "azimuth": 0.0, "sector": "Principal"},
            headers=_headers(SESSION_REST),
        )
        assert response.status_code == 200
        assert response.json()["name"] == "S-01"
        assert [section["name"] for section in db.get_sections(SESSION_REST)] == ["S-01", "S-01"]

    def test_put_out_of_range_is_404_and_writes_nothing(self, api_test_client):
        _seed(SESSION_REST, ("S-01", "S-02"))
        before = _state(SESSION_REST)
        response = api_test_client.put(
            PUT_URL.format(section_id=2),
            json={"origin": [0.0, 0.0], "azimuth": 0.0},
            headers=_headers(SESSION_REST),
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Section index 2 out of range (0-1)"}
        assert _state(SESSION_REST) == before

    def test_put_non_integer_id_is_400(self, api_test_client):
        _seed(SESSION_REST, ("S-01",))
        response = api_test_client.put(
            PUT_URL.format(section_id="abc"),
            json={"origin": [0.0, 0.0], "azimuth": 0.0},
            headers=_headers(SESSION_REST),
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "section_id must be an integer index"}

    def test_put_while_running_is_409(self, api_test_client):
        _seed(SESSION_REST, ("S-01",))
        db.update_process_status(SESSION_REST, "running", 0, 1)
        response = api_test_client.put(
            PUT_URL.format(section_id=0),
            json={"origin": [0.0, 0.0], "azimuth": 0.0},
            headers=_headers(SESSION_REST),
        )
        assert response.status_code == 409
        assert response.json() == {
            "detail": "Analysis is running; wait for it to finish before changing sections"
        }
        assert db.get_sections(SESSION_REST)[0]["origin"] == [0.0, 0.0]

    def test_delete_removes_section_and_invalidates_analysis(self, api_test_client):
        _seed(SESSION_REST, ("S-01", "S-02"))
        response = api_test_client.delete(
            DELETE_URL.format(section_id=0), headers=_headers(SESSION_REST)
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Section 'S-01' deleted", "total": 1}
        state = _state(SESSION_REST)
        assert [section["name"] for section in state["sections"]] == ["S-02"]
        assert state["results"] == []
        assert state["extraction"] is None
        assert state["status"]["status"] == "idle"

    def test_delete_out_of_range_is_404_and_writes_nothing(self, api_test_client):
        _seed(SESSION_REST, ("S-01", "S-02"))
        before = _state(SESSION_REST)
        response = api_test_client.delete(
            DELETE_URL.format(section_id=5), headers=_headers(SESSION_REST)
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Section index 5 out of range (0-1)"}
        assert _state(SESSION_REST) == before

    def test_delete_non_integer_id_is_400(self, api_test_client):
        _seed(SESSION_REST, ("S-01",))
        response = api_test_client.delete(
            DELETE_URL.format(section_id="x1"), headers=_headers(SESSION_REST)
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "section_id must be an integer index"}

    def test_delete_while_processing_is_409(self, api_test_client):
        _seed(SESSION_REST, ("S-01",))
        db.update_process_status(SESSION_REST, "processing", 0, 1)
        response = api_test_client.delete(
            DELETE_URL.format(section_id=0), headers=_headers(SESSION_REST)
        )
        assert response.status_code == 409
        assert len(db.get_sections(SESSION_REST)) == 1
        assert db.get_process_status(SESSION_REST)["status"] == "processing"


# ---------------------------------------------------------------------------
# Agent parity: same seeded state, same stored outcome as the REST endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_update_with_overrides_matches_rest_put(api_test_client):
    _seed(SESSION_REST, ("S-01", "S-02"))
    _seed(SESSION_AGENT, ("S-01", "S-02"))
    rest_body = {
        "name": "S-02",
        "origin": [10.0, 0.0],
        "azimuth": 45.678,
        "length": 60.0,
        "length_up": 40.0,
        "length_down": None,
        "sector": "Norte",
    }
    rest = api_test_client.put(
        PUT_URL.format(section_id=1), json=rest_body, headers=_headers(SESSION_REST)
    )
    assert rest.status_code == 200, rest.text

    result = await write_handlers.update_section(
        SESSION_AGENT,
        SectionUpdateArgs(section_id=1, azimuth=45.678, length_up=40.0, sector="Norte"),
    )

    assert result == {"ok": True, "section": rest.json(), "invalidated": True}
    assert _state(SESSION_AGENT) == _state(SESSION_REST)


@pytest.mark.asyncio
async def test_agent_update_no_op_matches_rest_identical_put(api_test_client):
    _seed(SESSION_REST, ("S-01", "S-02"))
    _seed(SESSION_AGENT, ("S-01", "S-02"))
    rest = api_test_client.put(
        PUT_URL.format(section_id=0),
        json={
            "name": "S-01",
            "origin": [0.0, 0.0],
            "azimuth": 0.0,
            "length": 60.0,
            "length_up": None,
            "length_down": None,
            "sector": "Principal",
        },
        headers=_headers(SESSION_REST),
    )
    assert rest.status_code == 200, rest.text

    result = await write_handlers.update_section(
        SESSION_AGENT, SectionUpdateArgs(section_id=0, azimuth=0.0)
    )

    assert result == {"ok": True, "section": rest.json(), "invalidated": False}
    assert _state(SESSION_AGENT) == _state(SESSION_REST)
    assert len(db.get_results(SESSION_AGENT)) == 2


@pytest.mark.asyncio
async def test_agent_delete_matches_rest_delete(api_test_client):
    _seed(SESSION_REST, ("S-01", "S-02", "S-03"))
    _seed(SESSION_AGENT, ("S-01", "S-02", "S-03"))
    rest = api_test_client.delete(
        DELETE_URL.format(section_id=0), headers=_headers(SESSION_REST)
    )
    assert rest.status_code == 200, rest.text

    result = await write_handlers.delete_section(
        SESSION_AGENT, SectionDeleteArgs(section_id=0)
    )

    assert result["ok"] is True
    assert result["deleted"] == {"section_id": 0, "name": "S-01"}
    assert result["total"] == rest.json()["total"] == 2
    assert result["invalidated"] is True
    assert _state(SESSION_AGENT) == _state(SESSION_REST)


@pytest.mark.asyncio
async def test_agent_delete_last_section_matches_rest_delete(api_test_client):
    _seed(SESSION_REST, ("S-01",))
    _seed(SESSION_AGENT, ("S-01",))
    rest = api_test_client.delete(
        DELETE_URL.format(section_id=0), headers=_headers(SESSION_REST)
    )
    assert rest.status_code == 200, rest.text

    result = await write_handlers.delete_section(
        SESSION_AGENT, SectionDeleteArgs(section_id=0)
    )

    assert result["ok"] is True and result["total"] == 0
    assert _state(SESSION_AGENT) == _state(SESSION_REST)


# ---------------------------------------------------------------------------
# Curve parity: POST /sections/curve and the generate_sections_curve tool
# ---------------------------------------------------------------------------

CURVE_URL = "/api/v1/sections/curve"


def _curve_args(**overrides):
    fields = {"points": [[0.0, 0.0], [100.0, 0.0]], "spacing": 10.0}
    fields.update(overrides)
    return SectionCurveArgs(**fields)


def _curve_rest_body(points, spacing, sector="Principal") -> dict:
    return {
        "points": points,
        "spacing": spacing,
        "length": 200.0,
        "length_up": None,
        "length_down": None,
        "sector": sector,
    }


def _summary_entry(section: dict) -> dict:
    return {key: section[key] for key in ("id", "name", "origin", "azimuth", "length")}


class TestRestCurveGolden:
    def test_curve_with_one_point_is_400_and_writes_nothing(self, api_test_client):
        _seed(SESSION_REST, ("S-01",))
        before = _state(SESSION_REST)
        response = api_test_client.post(
            CURVE_URL,
            json=_curve_rest_body([[0.0, 0.0]], 10.0),
            headers=_headers(SESSION_REST),
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Curve must have at least 2 points"}
        assert _state(SESSION_REST) == before

    def test_curve_while_running_is_409_and_writes_nothing(self, api_test_client):
        _seed(SESSION_REST, ("S-01",))
        db.update_process_status(SESSION_REST, "running", 0, 1)
        before = _state(SESSION_REST)
        response = api_test_client.post(
            CURVE_URL,
            json=_curve_rest_body([[0.0, 0.0], [100.0, 0.0]], 10.0),
            headers=_headers(SESSION_REST),
        )
        assert response.status_code == 409
        assert response.json() == {
            "detail": "Analysis is running; wait for it to finish before changing sections"
        }
        assert _state(SESSION_REST) == before


@pytest.mark.asyncio
async def test_agent_curve_matches_rest_post_on_identical_session(api_test_client):
    _seed(SESSION_REST, ("S-01", "S-02"))
    _seed(SESSION_AGENT, ("S-01", "S-02"))
    points = [[0.0, 100.0], [100.0, 100.0], [100.0, 160.0]]
    rest = api_test_client.post(
        CURVE_URL,
        json=_curve_rest_body(points, 20.0, sector="Norte"),
        headers=_headers(SESSION_REST),
    )
    assert rest.status_code == 200, rest.text

    result = await write_handlers.generate_sections_curve(
        SESSION_AGENT, _curve_args(points=points, spacing=20.0, sector="Norte")
    )

    rest_sections = rest.json()["sections"]
    assert result["ok"] is True
    assert result["n_sections"] == len(rest_sections) == 10
    assert result["sections"] == [_summary_entry(section) for section in rest_sections]
    assert _state(SESSION_AGENT) == _state(SESSION_REST)


@pytest.mark.asyncio
async def test_agent_rejects_a_duplicate_name_that_rest_accepts(api_test_client):
    _seed(SESSION_REST, ("S-01", "S-02"))
    _seed(SESSION_AGENT, ("S-01", "S-02"))
    rest = api_test_client.put(
        PUT_URL.format(section_id=1),
        json={"name": "S-01", "origin": [10.0, 0.0], "azimuth": 0.0, "sector": "Principal"},
        headers=_headers(SESSION_REST),
    )
    assert rest.status_code == 200, rest.text

    result = await write_handlers.update_section(
        SESSION_AGENT, SectionUpdateArgs(section_id=1, name="S-01")
    )

    assert result == {
        "ok": False,
        "error": "duplicate_section_name",
        "message": "Ya existe otra sección llamada «S-01».",
    }
    assert [s["name"] for s in db.get_sections(SESSION_AGENT)] == ["S-01", "S-02"]

