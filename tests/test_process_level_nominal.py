"""Dashboard backend: nominal level in results and level filters (contract C6)."""
from __future__ import annotations

import asyncio
import copy
from typing import Any, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

import api.database as db
from api.ai_agent_handlers import READ_HANDLERS
from api.routers.process import _filter_comparisons
from core.ai_v2.agent.models import ResultQueryArgs

RESULTS = "/api/v1/process/results"
ACHIEVEMENT = "/api/v1/process/design-achievement"
PROPOSED = "/api/v1/process/proposed-compliance"

BENCH_3_DISTRIBUTION = (
    [3104] * 71
    + [3095] * 16
    + [3096] * 2
    + [3099] * 2
    + [3097, 3098, 3101, 3102, 3103]
)
EXTRA_LEVELS = {"S-22": 3120, "S-25": 3122}
N_SECTIONS = len(BENCH_3_DISTRIBUTION)
SECTION_AT_3095 = "S-72"


def _row(
    section: str,
    bench_num: int,
    row_type: str,
    level: Any,
    height_design: Optional[float] = 15.0,
    sector: str = "",
) -> dict:
    return {
        "sector": sector,
        "section": section,
        "bench_num": bench_num,
        "type": row_type,
        "level": level,
        "height_design": height_design,
        "delta_crest": 0.2,
        "delta_toe": -0.1,
        "berm_status": "CUMPLE",
    }


def _real_session_rows(sector: str = "") -> List[dict]:
    rows: List[dict] = []
    for index, bench_3_level in enumerate(BENCH_3_DISTRIBUTION, start=1):
        section = f"S-{index:02d}"
        rows.append(_row(section, 1, "MATCH", "3125", sector=sector))
        if section in EXTRA_LEVELS:
            rows.append(
                _row(section, 999, "EXTRA", str(EXTRA_LEVELS[section]), None, sector)
            )
        rows.append(_row(section, 2, "MATCH", "3110", sector=sector))
        rows.append(_row(section, 3, "MISSING", str(bench_3_level), 5.88, sector))
    return rows


@pytest.fixture()
def session_owner(api_test_client: TestClient) -> Tuple[TestClient, str]:
    session_id = db.create_session()
    api_test_client.headers["X-Session-ID"] = session_id
    db.save_results(session_id, _real_session_rows())
    return api_test_client, session_id


def test_fixture_matches_the_real_session_shape():
    rows = _real_session_rows()
    assert N_SECTIONS == 96
    bench_3 = [float(row["level"]) for row in rows if row["bench_num"] == 3]
    assert len(bench_3) == 96
    assert (min(bench_3), max(bench_3)) == (3095.0, 3104.0)
    assert {row["type"] for row in rows if row["bench_num"] == 3} == {"MISSING"}


class TestResultsCarryNominalLevel:
    def test_every_row_has_level_nominal(self, session_owner):
        body = session_owner[0].get(RESULTS).json()
        assert len(body) == len(_real_session_rows())
        assert all("level_nominal" in row for row in body)

    def test_bench_3_rows_are_all_labelled_3104(self, session_owner):
        body = session_owner[0].get(RESULTS).json()
        bench_3 = [row for row in body if row["bench_num"] == 3]
        assert len(bench_3) == 96
        assert {row["level_nominal"] for row in bench_3} == {"3104"}
        assert {row["level"] for row in bench_3} == {
            str(level) for level in BENCH_3_DISTRIBUTION
        }

    def test_other_benches_and_extras(self, session_owner):
        body = session_owner[0].get(RESULTS).json()
        assert {row["level_nominal"] for row in body if row["bench_num"] == 1} == {"3125"}
        assert {row["level_nominal"] for row in body if row["bench_num"] == 2} == {"3110"}
        assert {row["level_nominal"] for row in body if row["type"] == "EXTRA"} == {"3125"}

    def test_existing_keys_values_and_order_are_unchanged(self, session_owner):
        seeded = _real_session_rows()
        body = session_owner[0].get(RESULTS).json()
        for original, returned in zip(seeded, body):
            assert list(returned) == list(original) + ["level_nominal"]
            assert {key: returned[key] for key in original} == original

    def test_section_filter_uses_the_assignment_of_all_session_rows(self, session_owner):
        body = session_owner[0].get(RESULTS, params={"section": SECTION_AT_3095}).json()
        assert [row["section"] for row in body] == [SECTION_AT_3095] * 3
        by_bench = {row["bench_num"]: row for row in body}
        assert by_bench[3]["level"] == "3095"
        assert by_bench[3]["level_nominal"] == "3104"

    def test_row_without_numeric_level_gets_none(self, session_owner):
        client, session_id = session_owner
        rows = _real_session_rows() + [
            _row("S-97", 1, "MATCH", "sin dato"),
            _row("S-98", 1, "MATCH", None),
        ]
        db.save_results(session_id, rows)
        body = client.get(RESULTS).json()
        by_section = {row["section"]: row for row in body if row["section"] in ("S-97", "S-98")}
        assert by_section["S-97"]["level_nominal"] is None
        assert by_section["S-98"]["level_nominal"] is None
        assert by_section["S-98"]["level"] is None

    def test_persisted_rows_are_not_modified(self, session_owner):
        client, session_id = session_owner
        client.get(RESULTS)
        assert db.get_results(session_id) == _real_session_rows()

    def test_empty_session_returns_empty_list(self, api_test_client):
        api_test_client.headers["X-Session-ID"] = db.create_session()
        response = api_test_client.get(RESULTS)
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.parametrize("endpoint", [ACHIEVEMENT, PROPOSED])
class TestLevelFilterOnEndpoints:
    def test_nominal_level_includes_all_bench_3_rows(self, session_owner, endpoint):
        body = session_owner[0].get(endpoint, params={"level": "3104"}).json()
        assert body["n_total_rows"] == 96
        assert body["filters"]["level"] == ["3104"]

    def test_exact_fallback_for_a_value_that_is_not_a_nominal_label(
        self, session_owner, endpoint
    ):
        body = session_owner[0].get(endpoint, params={"level": "3099"}).json()
        assert body["n_total_rows"] == 2

    def test_repeated_levels_are_ored(self, session_owner, endpoint):
        body = session_owner[0].get(
            endpoint, params=[("level", "3104"), ("level", "3110")]
        ).json()
        assert body["n_total_rows"] == 192

    def test_extras_follow_their_nominal_level(self, session_owner, endpoint):
        body = session_owner[0].get(endpoint, params={"level": "3125"}).json()
        assert body["n_total_rows"] == 98

    def test_level_and_section_are_anded_with_session_wide_assignment(
        self, session_owner, endpoint
    ):
        body = session_owner[0].get(
            endpoint, params={"level": "3104", "section": SECTION_AT_3095}
        ).json()
        assert body["n_total_rows"] == 1

    def test_unknown_level_filters_everything_out(self, session_owner, endpoint):
        body = session_owner[0].get(endpoint, params={"level": "9999"}).json()
        assert body["n_total_rows"] == 0
        assert "all_rows_filtered_out" in body["warnings"]

    def test_cross_session_isolation(self, session_owner, endpoint):
        client, session_a = session_owner
        session_b = db.create_session()
        db.save_results(
            session_b,
            [
                _row("B-01", 1, "MATCH", "3104"),
                _row("B-02", 1, "MATCH", "3099"),
            ],
        )

        body_a = client.get(endpoint, params={"level": "3104"}).json()
        assert body_a["n_total_rows"] == 96

        body_b = client.get(
            endpoint, params={"level": "3099"}, headers={"X-Session-ID": session_b}
        ).json()
        assert body_b["n_total_rows"] == 1
        body_b_nominal = client.get(
            endpoint, params={"level": "3104"}, headers={"X-Session-ID": session_b}
        ).json()
        assert body_b_nominal["n_total_rows"] == 1


def test_results_cross_session_isolation(session_owner):
    client, _session_a = session_owner
    session_b = db.create_session()
    db.save_results(session_b, [_row("B-01", 1, "MATCH", "3095")])
    body_b = client.get(RESULTS, headers={"X-Session-ID": session_b}).json()
    assert [(row["section"], row["level_nominal"]) for row in body_b] == [("B-01", "3095")]
    body_a = client.get(RESULTS).json()
    assert "B-01" not in {row["section"] for row in body_a}


class TestFilterComparisons:
    def test_nominal_label_matches_all_rows_of_the_group(self):
        rows = _real_session_rows()
        kept = _filter_comparisons(rows, None, None, ["3104"], None)
        assert len(kept) == 96
        assert {row["bench_num"] for row in kept} == {3}

    def test_exact_fallback(self):
        kept = _filter_comparisons(_real_session_rows(), None, None, ["3099"], None)
        assert [row["level"] for row in kept] == ["3099", "3099"]

    def test_returns_the_same_row_objects_in_order_without_mutation(self):
        rows = _real_session_rows()
        snapshot = copy.deepcopy(rows)
        kept = _filter_comparisons(rows, None, None, ["3104"], None)
        expected = [row for row in rows if row["bench_num"] == 3]
        assert len(kept) == len(expected)
        assert all(a is b for a, b in zip(kept, expected))
        assert rows == snapshot

    def test_no_level_filter_keeps_every_row(self):
        rows = _real_session_rows()
        for levels in (None, []):
            kept = _filter_comparisons(rows, None, None, levels, None)
            assert len(kept) == len(rows)
            assert all(a is b for a, b in zip(kept, rows))

    def test_other_dimensions_keep_string_semantics(self):
        rows = _real_session_rows()
        kept = _filter_comparisons(rows, [""], ["S-01", "S-72"], ["3104"], ["3"])
        assert [(row["section"], row["level"]) for row in kept] == [
            ("S-01", "3104"),
            ("S-72", "3095"),
        ]
        assert _filter_comparisons(rows, None, None, ["3104"], ["1"]) == []

    def test_empty_string_selects_rows_without_level(self):
        rows = [
            _row("S-01", 1, "MATCH", "3104"),
            _row("S-02", 1, "MATCH", None),
            _row("S-03", 1, "MATCH", ""),
        ]
        missing_key = _row("S-04", 1, "MATCH", "3104")
        del missing_key["level"]
        rows.append(missing_key)
        kept = _filter_comparisons(rows, None, None, [""], None)
        assert [row["section"] for row in kept] == ["S-02", "S-03", "S-04"]

    def test_non_numeric_level_matches_by_exact_text(self):
        rows = [
            _row("S-01", 1, "MATCH", "3104"),
            _row("S-02", 1, "MATCH", "sin dato"),
        ]
        kept = _filter_comparisons(rows, None, None, ["sin dato"], None)
        assert [row["section"] for row in kept] == ["S-02"]

    def test_numeric_level_matches_by_its_string_form(self):
        rows = [_row("S-01", 1, "MATCH", 3104, None)]
        assert len(_filter_comparisons(rows, None, None, ["3104"], None)) == 1

    def test_label_of_one_sector_falls_back_to_exact_text_in_another(self):
        rows = [
            _row("N-01", 1, "MATCH", "3104", sector="Norte"),
            _row("N-02", 1, "MATCH", "3102", sector="Norte"),
            _row("S-01", 1, "MATCH", "3103", sector="Sur"),
            _row("S-02", 1, "MATCH", "3100", sector="Sur"),
        ]
        kept = _filter_comparisons(rows, None, None, ["3103"], None)
        assert [row["section"] for row in kept] == ["N-01", "N-02", "S-01"]

    def test_assignment_uses_the_rows_passed_in_not_the_filtered_subset(self):
        rows = _real_session_rows()
        kept = _filter_comparisons(rows, None, [SECTION_AT_3095], ["3104"], None)
        assert [(row["section"], row["level"]) for row in kept] == [
            (SECTION_AT_3095, "3095")
        ]

    def test_non_dict_rows_are_skipped(self):
        rows = [_row("S-01", 1, "MATCH", "3104"), None, "x"]
        assert len(_filter_comparisons(rows, None, None, ["3104"], None)) == 1
        assert len(_filter_comparisons(rows, None, None, None, None)) == 1


def test_ai_agent_query_results_follows_the_nominal_level(api_isolated_db):
    session_id = db.create_session()
    db.save_results(session_id, _real_session_rows())
    query = asyncio.run(
        READ_HANDLERS["query_results"](session_id, ResultQueryArgs(level=["3104"]))
    )
    assert query["n_matched_rows"] == 96
