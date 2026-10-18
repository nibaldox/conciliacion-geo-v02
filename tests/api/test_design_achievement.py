"""API tests for GET /api/v1/process/design-achievement.

Each test runs against the isolated per-test SQLite database from
``tests/api/conftest.py`` (user DB is never touched). Comparison rows are
seeded with the production ``db.save_results`` so the endpoint walks the
exact data flow used after POST /process.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

import api.database as db

ENDPOINT = "/api/v1/process/design-achievement"


def _rows() -> List[dict]:
    return [
        {
            "section": "S1",
            "level": "100",
            "bench_num": 1,
            "sector": "A",
            "delta_crest": 0.5,
            "delta_toe": -0.8,
            "berm_status": "CUMPLE",
        },
        {
            "section": "S2",
            "level": "200",
            "bench_num": 2,
            "sector": "A",
            "delta_crest": 2.0,
            "delta_toe": 0.0,
            "berm_status": "NO CUMPLE",
        },
        {
            "section": "S3",
            "level": "300",
            "bench_num": 3,
            "sector": "B",
            "delta_crest": None,
            "delta_toe": None,
            "berm_status": "CUMPLE",
        },
    ]


@pytest.fixture()
def session_owner(api_test_client: TestClient) -> Tuple[TestClient, str]:
    """Client pinned to a session created through the production DB API."""
    session_id = db.create_session()
    api_test_client.headers["X-Session-ID"] = session_id
    return api_test_client, session_id


def _seed(session_id: str, rows: Optional[List[dict]] = None) -> None:
    db.save_results(session_id, rows if rows is not None else _rows())


class TestContract:
    def test_status_and_exact_top_level_keys(self, session_owner):
        session_id = session_owner[1]
        _seed(session_id)
        body = session_owner[0].get(ENDPOINT).json()

        assert set(body) == {
            "session_id",
            "n_total_rows",
            "summary",
            "sectors",
            "tolerances",
            "tolerances_source",
            "filters",
            "units",
            "status_model",
            "warnings",
            "metadata",
        }
        assert set(body["summary"]) == {
            "global_score",
            "n_total",
            "n_evaluable",
            "crest_cumple",
            "crest_denom",
            "crest_pct",
            "toe_cumple",
            "toe_denom",
            "toe_pct",
            "berm_cumple",
            "berm_denom",
            "berm_pct",
            "delta_crest_mean",
            "delta_toe_mean",
        }
        assert body["units"] == {"corrections": "m", "score": "0-100"}
        assert body["filters"] == {
            "sector": [],
            "section": [],
            "level": [],
            "bench": [],
        }
        assert body["session_id"] == session_id

    def test_summary_matches_core_semantics(self, session_owner):
        client, session_id = session_owner
        _seed(session_id)
        body = client.get(ENDPOINT).json()

        assert body["n_total_rows"] == 3
        assert body["summary"]["n_evaluable"] == 3
        assert body["summary"]["global_score"] == 53
        assert body["summary"]["crest_pct"] == 50
        assert body["summary"]["toe_pct"] == 100
        assert body["summary"]["berm_pct"] == 67
        assert body["summary"]["delta_crest_mean"] == pytest.approx(1.25)
        assert body["summary"]["delta_toe_mean"] == pytest.approx(-0.4)

        sectors = {entry["sector"]: entry for entry in body["sectors"]}
        assert set(sectors) == {"A", "B"}
        assert sectors["A"]["n_evaluable"] == 2
        assert sectors["A"]["crest_pct"] == 50
        assert sectors["B"]["n_evaluable"] == 1
        assert sectors["B"]["global_score"] == 30  # berma CUMPLE credit only


class TestSessionSettings:
    def test_core_defaults_when_no_session_settings(self, session_owner):
        client, _ = session_owner
        _seed(session_owner[1])
        body = client.get(ENDPOINT).json()
        assert body["tolerances"] == {"neg": 1.0, "pos": 1.0}
        assert body["tolerances_source"] == "core_default"

    def test_session_tolerance_override_is_used(self, session_owner):
        client, session_id = session_owner
        _seed(session_id)
        db.save_settings(
            session_id,
            {"tolerances": {"crest_toe_deviation": {"neg": 1.0, "pos": 2.5}}},
        )
        body = client.get(ENDPOINT).json()
        assert body["tolerances"] == {"neg": 1.0, "pos": 2.5}
        assert body["tolerances_source"] == "session"
        assert body["summary"]["crest_pct"] == 100


class TestFilters:
    def test_zero_bench_and_level_values_survive_the_filter(self, session_owner):
        client, session_id = session_owner
        rows = [dict(_rows()[0], bench_num=0, level=0), dict(_rows()[1])]
        _seed(session_id, rows)

        by_bench = client.get(f"{ENDPOINT}?bench=0").json()
        assert by_bench["n_total_rows"] == 1
        assert by_bench["summary"]["n_evaluable"] == 1

        by_level = client.get(f"{ENDPOINT}?level=0").json()
        assert by_level["n_total_rows"] == 1
        assert by_level["filters"]["level"] == ["0"]

    def test_repeated_params_or_within_dimension(self, session_owner):
        client, session_id = session_owner
        _seed(session_id)
        body = client.get(f"{ENDPOINT}?section=S1&section=S2").json()
        assert body["filters"]["section"] == ["S1", "S2"]
        assert body["n_total_rows"] == 2
        assert body["summary"]["n_evaluable"] == 2

    def test_empty_string_selects_rows_without_sector(self, session_owner):
        client, session_id = session_owner
        rows = [dict(_rows()[0], sector=""), dict(_rows()[1])]
        _seed(session_id, rows)
        body = client.get(f"{ENDPOINT}?sector=").json()
        assert body["filters"]["sector"] == [""]
        assert body["n_total_rows"] == 1
        assert body["summary"]["n_evaluable"] == 1

    def test_bench_and_level_filters(self, session_owner):
        client, session_id = session_owner
        _seed(session_id)
        by_bench = client.get(f"{ENDPOINT}?bench=2").json()
        assert by_bench["n_total_rows"] == 1
        assert by_bench["filters"]["bench"] == ["2"]

        by_level = client.get(f"{ENDPOINT}?level=300").json()
        assert by_level["n_total_rows"] == 1
        assert by_level["filters"]["level"] == ["300"]

    def test_dimensions_are_anded(self, session_owner):
        client, session_id = session_owner
        _seed(session_id)
        body = client.get(f"{ENDPOINT}?sector=A&bench=99").json()
        assert body["n_total_rows"] == 0
        assert body["warnings"] == ["all_rows_filtered_out"]
        assert body["summary"]["global_score"] is None

    def test_warning_when_no_row_is_evaluable(self, session_owner):
        client, session_id = session_owner
        _seed(session_id, [{"berm_status": "MISSING"}])
        body = client.get(ENDPOINT).json()
        assert body["n_total_rows"] == 1
        assert body["summary"]["n_evaluable"] == 0
        assert body["warnings"] == ["no_evaluable_rows"]


class TestSessionIsolation:
    def test_empty_session_is_never_the_owner(self, api_test_client):
        session_id = db.create_session()
        _seed(session_id)
        api_test_client.headers["X-Session-ID"] = "some-other-session"
        body = api_test_client.get(ENDPOINT).json()
        assert body["n_total_rows"] == 0
        assert body["summary"] == {
            "global_score": None,
            "n_total": 0,
            "n_evaluable": 0,
            "crest_cumple": 0,
            "crest_denom": 0,
            "crest_pct": None,
            "toe_cumple": 0,
            "toe_denom": 0,
            "toe_pct": None,
            "berm_cumple": 0,
            "berm_denom": 0,
            "berm_pct": None,
            "delta_crest_mean": None,
            "delta_toe_mean": None,
        }
        assert body["sectors"] == []
        assert body["warnings"] == ["no_results"]


class TestProvenance:
    def test_metadata_source_status_and_assumptions(self, session_owner):
        client, session_id = session_owner
        _seed(session_id)
        body = client.get(ENDPOINT).json()

        assert body["metadata"]["source"] == "persisted_comparisons"
        assert body["metadata"]["status"] == "computed"
        assert body["metadata"]["assumptions"] == [
            "global score = 0.4 * crest + 0.3 * toe + 0.3 * berma per evaluable row",
            "partial credit: CUMPLE=1.0, FUERA DE TOLERANCIA=0.5, others=0",
            "missing deltas or non-tier berm_status are excluded without inference",
        ]

        filtered_out = client.get(f"{ENDPOINT}?bench=99").json()
        assert filtered_out["metadata"]["status"] == "no_data"
