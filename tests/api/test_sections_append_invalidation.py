"""Regression tests for section append semantics and analysis invalidation.

Generating a new sector must accumulate sections (Streamlit parity,
``ui/step2_sections/state.py::add_sections``) instead of replacing the whole
list, colliding names must receive a ``_{n}`` suffix, and every effective
section mutation must drop the analysis artifacts derived from the previous
section set (``results``, ``extraction_cache`` and ``process_status``).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.database as db

SECTIONS = "/api/v1/sections"
CURVE = "/api/v1/sections/curve"


def _headers(session_id: str) -> dict:
    return {"X-Session-ID": session_id}


def _upload_design(client: TestClient, session_id: str, stl_bytes: bytes) -> None:
    resp = client.post(
        "/api/v1/meshes/upload",
        files={"file": ("design.stl", stl_bytes, "application/octet-stream")},
        data={"type": "design"},
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text


def _post_curve(client: TestClient, session_id: str, points, sector: str, spacing=50.0):
    resp = client.post(
        CURVE,
        json={
            "points": points,
            "spacing": spacing,
            "length": 200.0,
            "sector": sector,
        },
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["sections"]


def _stored(client: TestClient, session_id: str):
    resp = client.get(SECTIONS, headers=_headers(session_id))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _seed_sections(session_id: str, names=("S-01",)) -> None:
    db.get_or_create_session(session_id)
    sections = [
        {
            "name": name,
            "origin": [1000.0 + 10.0 * idx, 2000.0],
            "azimuth": 0.0,
            "length": 200.0,
            "length_up": None,
            "length_down": None,
            "sector": "Norte",
        }
        for idx, name in enumerate(names)
    ]
    db.save_sections(session_id, sections)


def _seed_analysis(session_id: str) -> None:
    db.get_or_create_session(session_id)
    db.save_results(session_id, [{"section": "S-01", "sector": "Norte", "bench": 1}])
    db.save_extraction(session_id, "S-01", "design", {"benches": [{"bench": 1}]})
    db.update_process_status(session_id, "complete", 1, 1, 1)


def _assert_analysis_cleared(session_id: str) -> None:
    assert db.get_results(session_id) == []
    assert db.get_all_extractions(session_id, "design") == []
    status = db.get_process_status(session_id)
    assert status == {
        "status": "idle",
        "current_section": 0,
        "total_sections": 0,
        "completed_sections": 0,
    }


# ---------------------------------------------------------------------------
# Append semantics
# ---------------------------------------------------------------------------


def test_curve_accumulates_sectors_and_suffixes_colliding_names(api_test_client):
    session_id = "sections-append-curve"
    client = api_test_client

    first = _post_curve(client, session_id, [[0.0, 0.0], [100.0, 0.0]], "Norte")
    assert [s["name"] for s in first] == ["S-01", "S-02"]

    second = _post_curve(client, session_id, [[0.0, 100.0], [100.0, 100.0]], "Sur")
    assert [s["sector"] for s in second] == ["Norte", "Norte", "Sur", "Sur"]
    assert [s["name"] for s in second] == ["S-01", "S-02", "S-01_1", "S-02_1"]

    third = _post_curve(client, session_id, [[0.0, 200.0], [100.0, 200.0]], "Este")
    names = [s["name"] for s in third]
    assert names == ["S-01", "S-02", "S-01_1", "S-02_1", "S-01_2", "S-02_2"]
    assert len(names) == len(set(names))

    stored = _stored(client, session_id)
    assert stored == third
    assert [s["sector"] for s in stored] == ["Norte", "Norte", "Sur", "Sur", "Este", "Este"]
    assert [s["id"] for s in stored] == [str(i) for i in range(6)]


def test_auto_appends_and_suffixes_colliding_names(api_test_client, stl_bytes):
    session_id = "sections-append-auto"
    client = api_test_client
    _upload_design(client, session_id, stl_bytes)

    first = client.post(
        "/api/v1/sections/auto",
        json={
            "start": [1.0, 5.0],
            "end": [9.0, 5.0],
            "n_sections": 2,
            "length": 50.0,
            "sector": "Norte",
        },
        headers=_headers(session_id),
    )
    assert first.status_code == 200, first.text
    assert [s["name"] for s in first.json()["sections"]] == ["S-01", "S-02"]

    second = client.post(
        "/api/v1/sections/auto",
        json={
            "start": [1.0, 6.0],
            "end": [9.0, 6.0],
            "n_sections": 1,
            "length": 50.0,
            "sector": "Sur",
        },
        headers=_headers(session_id),
    )
    assert second.status_code == 200, second.text
    combined = second.json()["sections"]
    assert [s["name"] for s in combined] == ["S-01", "S-02", "S-01_1"]
    assert [s["sector"] for s in combined] == ["Norte", "Norte", "Sur"]
    assert _stored(client, session_id) == combined


def test_from_file_appends_instead_of_replacing(api_test_client, stl_bytes):
    session_id = "sections-append-from-file"
    client = api_test_client
    _upload_design(client, session_id, stl_bytes)

    csv_north = b"X,Y\n0.0,0.0\n10.0,0.0\n10.0,10.0\n"
    resp = client.post(
        "/api/v1/sections/from-file",
        files={"file": ("north.csv", csv_north, "text/csv")},
        data={"spacing": "5.0", "length": "50.0", "sector": "Norte"},
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text
    north = resp.json()["sections"]
    assert len(north) >= 2
    assert all(s["sector"] == "Norte" for s in north)

    csv_south = b"X,Y\n0.0,20.0\n10.0,20.0\n"
    resp = client.post(
        "/api/v1/sections/from-file",
        files={"file": ("south.csv", csv_south, "text/csv")},
        data={"spacing": "5.0", "length": "50.0", "sector": "Sur"},
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text
    combined = resp.json()["sections"]
    assert len(combined) == len(north) + 2
    assert [s["sector"] for s in combined] == (
        ["Norte"] * len(north) + ["Sur"] * 2
    )
    names = [s["name"] for s in combined]
    assert len(names) == len(set(names))

    assert _stored(client, session_id) == combined


# ---------------------------------------------------------------------------
# Invalidation on every effective mutation
# ---------------------------------------------------------------------------


def _mutate_auto(client, session_id, stl_bytes):
    return client.post(
        "/api/v1/sections/auto",
        json={
            "start": [1.0, 5.0],
            "end": [9.0, 5.0],
            "n_sections": 2,
            "length": 50.0,
            "sector": "Sur",
        },
        headers=_headers(session_id),
    )


def _mutate_manual(client, session_id, stl_bytes):
    return client.post(
        "/api/v1/sections/manual",
        json=[
            {
                "name": "M-01",
                "origin": [1.0, 5.0],
                "azimuth": 90.0,
                "length": 50.0,
                "sector": "Sur",
            }
        ],
        headers=_headers(session_id),
    )


def _mutate_click(client, session_id, stl_bytes):
    return client.post(
        "/api/v1/sections/click",
        json={
            "origin": [1.0, 5.0],
            "az_mode": "manual",
            "azimuth": 90.0,
            "length": 50.0,
            "sector": "Sur",
        },
        headers=_headers(session_id),
    )


def _mutate_curve(client, session_id, stl_bytes):
    return client.post(
        CURVE,
        json={
            "points": [[0.0, 50.0], [100.0, 50.0]],
            "spacing": 50.0,
            "length": 50.0,
            "sector": "Sur",
        },
        headers=_headers(session_id),
    )


def _mutate_from_file(client, session_id, stl_bytes):
    return client.post(
        "/api/v1/sections/from-file",
        files={"file": ("south.csv", b"X,Y\n0.0,60.0\n10.0,60.0\n", "text/csv")},
        data={"spacing": "5.0", "length": "50.0", "sector": "Sur"},
        headers=_headers(session_id),
    )


def _mutate_put(client, session_id, stl_bytes):
    return client.put(
        "/api/v1/sections/0",
        json={
            "name": "S-01",
            "origin": [1000.0, 2000.0],
            "azimuth": 90.0,
            "length": 200.0,
            "sector": "Sur",
        },
        headers=_headers(session_id),
    )


def _mutate_delete(client, session_id, stl_bytes):
    return client.delete("/api/v1/sections/0", headers=_headers(session_id))


def _mutate_clear(client, session_id, stl_bytes):
    return client.delete(SECTIONS, headers=_headers(session_id))


MUTATIONS = [
    pytest.param(_mutate_auto, id="auto"),
    pytest.param(_mutate_manual, id="manual"),
    pytest.param(_mutate_click, id="click"),
    pytest.param(_mutate_curve, id="curve"),
    pytest.param(_mutate_from_file, id="from-file"),
    pytest.param(_mutate_put, id="put"),
    pytest.param(_mutate_delete, id="delete"),
    pytest.param(_mutate_clear, id="clear"),
]


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_effective_mutation_invalidates_analysis(api_test_client, stl_bytes, mutation):
    session_id = f"sections-invalidate-{mutation.__name__}"
    client = api_test_client
    _upload_design(client, session_id, stl_bytes)
    _seed_sections(session_id)
    _seed_analysis(session_id)

    resp = mutation(client, session_id, stl_bytes)
    assert resp.status_code == 200, resp.text

    _assert_analysis_cleared(session_id)


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("busy_status", ["running", "processing"])
def test_mutation_rejected_with_409_while_pipeline_is_busy(
    api_test_client, stl_bytes, mutation, busy_status
):
    session_id = f"sections-busy-{busy_status}-{mutation.__name__}"
    client = api_test_client
    _upload_design(client, session_id, stl_bytes)
    _seed_sections(session_id)
    _seed_analysis(session_id)
    db.update_process_status(session_id, busy_status, 0, 1, 0)
    before_sections = _stored(client, session_id)

    resp = mutation(client, session_id, stl_bytes)

    assert resp.status_code == 409, resp.text
    assert _stored(client, session_id) == before_sections
    assert db.get_results(session_id) != []
    assert db.get_all_extractions(session_id, "design") != []
    assert db.get_process_status(session_id)["status"] == busy_status


# ---------------------------------------------------------------------------
# No-op mutations
# ---------------------------------------------------------------------------


def test_empty_generation_batch_does_not_invalidate(api_test_client, stl_bytes):
    session_id = "sections-noop-empty-batch"
    client = api_test_client
    _upload_design(client, session_id, stl_bytes)
    _seed_sections(session_id)
    _seed_analysis(session_id)
    before = _stored(client, session_id)

    resp = client.post(
        "/api/v1/sections/auto",
        json={
            "start": [1.0, 5.0],
            "end": [9.0, 5.0],
            "n_sections": 0,
            "length": 50.0,
            "sector": "Sur",
        },
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sections"] == before

    resp = client.post(
        CURVE,
        json={
            "points": [[0.0, 0.0], [0.0, 0.0]],
            "spacing": 10.0,
            "length": 50.0,
            "sector": "Sur",
        },
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sections"] == before

    assert _stored(client, session_id) == before
    assert db.get_results(session_id) != []
    assert db.get_all_extractions(session_id, "design") != []
    assert db.get_process_status(session_id)["status"] == "complete"


def test_clear_on_empty_section_list_does_not_invalidate(api_test_client):
    session_id = "sections-noop-clear-empty"
    client = api_test_client
    _seed_analysis(session_id)
    assert _stored(client, session_id) == []

    resp = client.delete(SECTIONS, headers=_headers(session_id))
    assert resp.status_code == 200, resp.text

    assert db.get_results(session_id) != []
    assert db.get_all_extractions(session_id, "design") != []
    assert db.get_process_status(session_id)["status"] == "complete"


def test_manual_identical_payload_does_not_invalidate(api_test_client):
    session_id = "sections-noop-manual-identical"
    client = api_test_client
    payload = [
        {
            "name": "S-01",
            "origin": [1000.0, 2000.0],
            "azimuth": 0.0,
            "length": 200.0,
            "sector": "Norte",
        }
    ]
    resp = client.post("/api/v1/sections/manual", json=payload, headers=_headers(session_id))
    assert resp.status_code == 200, resp.text
    _seed_analysis(session_id)

    resp = client.post("/api/v1/sections/manual", json=payload, headers=_headers(session_id))
    assert resp.status_code == 200, resp.text

    assert db.get_results(session_id) != []
    assert db.get_all_extractions(session_id, "design") != []
    assert db.get_process_status(session_id)["status"] == "complete"


# ---------------------------------------------------------------------------
# /manual keeps replacement semantics
# ---------------------------------------------------------------------------


def test_manual_replaces_existing_sections(api_test_client):
    session_id = "sections-manual-replace"
    client = api_test_client
    _seed_sections(session_id, names=("S-01", "S-02"))
    _seed_analysis(session_id)

    resp = client.post(
        "/api/v1/sections/manual",
        json=[
            {
                "name": "R-01",
                "origin": [1.0, 2.0],
                "azimuth": 45.0,
                "length": 100.0,
                "sector": "Sur",
            }
        ],
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "1 sections set"
    assert [s["name"] for s in body["sections"]] == ["R-01"]
    assert [s["name"] for s in _stored(client, session_id)] == ["R-01"]
    _assert_analysis_cleared(session_id)


def test_click_suffixes_name_that_would_collide_without_the_middle_section(api_test_client):
    session_id = "sections-click-suffix"
    client = api_test_client
    _seed_sections(session_id, names=("S-01", "S-02", "S-03"))
    db.save_sections(
        session_id,
        [s for s in db.get_sections(session_id) if s["name"] != "S-02"],
    )

    resp = client.post(
        "/api/v1/sections/click",
        json={"origin": [5.0, 5.0], "az_mode": "manual", "azimuth": 0.0, "length": 50.0},
        headers=_headers(session_id),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["section"]["name"] == "S-03_1"
    assert body["total"] == 3
    assert [s["name"] for s in _stored(client, session_id)] == [
        "S-01",
        "S-03",
        "S-03_1",
    ]
