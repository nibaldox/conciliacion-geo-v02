"""B1: worst sections first, labelled counts and tolerant read-tool args.

Synthetic sessions only (isolated SQLite via ``api_isolated_db``); the
observation is measured with the loop's own ``_observation_content``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

import api.database as db
from api.ai_agent_handlers import get_results_summary, get_workflow_state, query_results
from core.ai_v2.agent.catalog import openai_tools
from core.ai_v2.agent.events import ToolResultEvent
from core.ai_v2.agent.loop import (
    _OBSERVATION_MAX_CHARS,
    _OBSERVATION_PRESERVE_KEYS,
    _observation_content,
)
from core.ai_v2.agent.models import AchievementFilterArgs, NoArgs, ResultQueryArgs
from core.ai_v2.agent.turn import ChatTurn
from core.compliance_status import STATUS_CUMPLE, STATUS_NO_CUMPLE
from tests.test_ai_v2_agent_loop import (
    RecordingHandler,
    ScriptedChatProvider,
    run_simple,
    tool_call,
)

# sha256 of {tool name: parameters schema} for every tool, captured on the
# base commit (e092175) BEFORE the tolerant validators were added. The
# validators must not change what the model sees.
_BASE_PARAMETERS_SHA256 = "b8f4ff3d85ad3434fbc2bcdd3e9253eae74066777cd394f53b59178b746d85e5"
_BASE_TOOL_COUNT = 21

N_SECTIONS = 120
WORST = ("S-095", "S-099")


@pytest.fixture(autouse=True)
def _isolated(api_isolated_db):
    yield api_isolated_db


def _row(section: str, score: float, row_type: str = "MATCH") -> Dict[str, Any]:
    status = STATUS_NO_CUMPLE
    return {
        "section": section,
        "sector": "A",
        "type": row_type,
        "level": "1000",
        "bench_num": 1,
        "section_status": status,
        "section_score": score,
        "height_status": STATUS_NO_CUMPLE,
        "angle_status": STATUS_CUMPLE if row_type == "MATCH" else "-",
        "berm_status": STATUS_CUMPLE,
        "bench_score": score,
    }


def _seed_large_session() -> str:
    sid = db.create_session()
    rows: List[Dict[str, Any]] = []
    for i in range(1, N_SECTIONS + 1):
        name = f"S-{i:03d}"
        score = 0.0 if name in WORST else 80.0 + (i % 7)
        rows.append(_row(name, score))
    # Non-compared rows: they count as result rows, never as compared benches.
    rows.append(_row("S-001", 80.0, row_type="EXTRA"))
    rows.append(_row("S-002", 81.0, row_type="MISSING"))
    db.save_results(sid, rows)
    return sid


@pytest.mark.asyncio
async def test_worst_sections_first_and_inside_observation():
    sid = _seed_large_session()
    query = await query_results(sid, ResultQueryArgs())
    summary = await get_results_summary(sid, NoArgs())
    for payload in (query, summary):
        names = [entry["name"] for entry in payload["sections"]]
        assert names[:2] == list(WORST)
        scores = [entry["section_score"] for entry in payload["sections"]]
        assert scores == sorted(scores)
        assert payload["sections_order"] == "score_asc"
        text = _observation_content(payload)
        assert len(text) <= _OBSERVATION_MAX_CHARS
        for name in WORST:
            assert 0 <= text.find(f'"{name}"') < _OBSERVATION_MAX_CHARS
    assert 0 <= _observation_content(query).find("weighted_score") < 200


@pytest.mark.asyncio
async def test_none_scores_sort_last():
    sid = db.create_session()
    rows = [_row("S-A", 50.0), _row("S-B", 10.0)]
    rows.append({**_row("S-0", 0.0), "section_score": None})
    db.save_results(sid, rows)
    for payload in (
        await query_results(sid, ResultQueryArgs()),
        await get_results_summary(sid, NoArgs()),
    ):
        assert [e["name"] for e in payload["sections"]] == ["S-B", "S-A", "S-0"]


@pytest.mark.asyncio
async def test_compared_bench_counts_are_labelled():
    sid = _seed_large_session()
    query = await query_results(sid, ResultQueryArgs())
    summary = await get_results_summary(sid, NoArgs())
    state = await get_workflow_state(sid, NoArgs())
    assert query["n_matched_rows"] == N_SECTIONS + 2
    assert summary["n_results"] == N_SECTIONS + 2
    assert state["n_results"] == N_SECTIONS + 2
    for payload in (query, summary, state):
        assert payload["n_compared_benches"] == N_SECTIONS
        assert "MATCH" in payload["counts_meaning"]
        assert "bancos comparados" in payload["counts_meaning"]
    filtered = await query_results(sid, ResultQueryArgs(section=["S-001"]))
    assert filtered["n_matched_rows"] == 2
    assert filtered["n_compared_benches"] == 1
    text = _observation_content(query)
    assert 0 <= text.find("n_compared_benches") < 600


def test_new_count_keys_survive_history_compaction():
    assert {"n_compared_benches", "counts_meaning"} <= _OBSERVATION_PRESERVE_KEYS


def test_scalar_filters_are_wrapped():
    for cls in (ResultQueryArgs, AchievementFilterArgs):
        args = cls.model_validate(
            {"section": "S-11", "sector": "A", "level": "3065", "bench": 3}
        )
        assert args.section == ["S-11"]
        assert args.sector == ["A"]
        assert args.level == ["3065"]
        assert args.bench == [3]
        assert cls.model_validate({"section": "S-11"}).section == ["S-11"]
        assert cls(section=["S-11"]).section == ["S-11"]
        assert cls().section is None
        with pytest.raises(ValidationError):
            cls.model_validate({"foo": 1})
    with pytest.raises(ValidationError):
        ResultQueryArgs.model_validate({"bench": float("inf")})


def test_row_limit_is_clamped():
    assert ResultQueryArgs(row_limit=100).row_limit == 50
    assert ResultQueryArgs(row_limit=0).row_limit == 1
    assert ResultQueryArgs(row_limit=-5).row_limit == 1
    assert ResultQueryArgs(row_limit=30).row_limit == 30
    args = ResultQueryArgs.model_validate({"include_rows": True, "row_limit": 100})
    assert args.row_limit == 50 and args.include_rows is True


def test_openai_schema_unchanged():
    tools = openai_tools()
    assert len(tools) == _BASE_TOOL_COUNT
    params = {t["function"]["name"]: t["function"]["parameters"] for t in tools}
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    assert digest == _BASE_PARAMETERS_SHA256


def test_catalog_describes_order_and_compared_benches():
    tools = {t["function"]["name"]: t["function"] for t in openai_tools()}
    description = tools["query_results"]["description"]
    assert "worst" in description and "n_compared_benches" in description


# ---------------------------------------------------------------------------
# Actionable validation errors + identical-repeat detection (loop)
# ---------------------------------------------------------------------------


def _observations(provider: ScriptedChatProvider) -> List[Dict[str, Any]]:
    last = provider.requests[-1]
    return [json.loads(m["content"]) for m in last if m.get("role") == "tool"]


@pytest.mark.asyncio
async def test_invalid_args_message_names_field():
    handler = RecordingHandler()
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call(
                        "query_results",
                        '{"foo": 1, "parameter": "volumen"}',
                        call_id="c1",
                    )
                ]
            ),
            ChatTurn(text="Corrijo."),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"query_results": handler})
    assert handler.calls == []
    result = events[1]
    assert isinstance(result, ToolResultEvent)
    assert result.error == "schema_validation"
    (observation,) = _observations(provider)
    assert observation["error"] == "invalid_arguments"
    assert observation["reason"] == "schema_validation"
    detail = observation["detail"]
    assert "'foo'" in detail and "no es un parámetro" in detail
    assert "'parameter'" in detail
    assert len(detail) <= 300
    assert "repeated" not in observation


@pytest.mark.asyncio
async def test_identical_invalid_call_is_flagged_as_repeated():
    handler = RecordingHandler()
    bad = '{"section": "S-11", "foo": true}'
    provider = ScriptedChatProvider(
        [
            ChatTurn(tool_calls=[tool_call("query_results", bad, call_id="c1")]),
            ChatTurn(tool_calls=[tool_call("query_results", bad, call_id="c2")]),
            ChatTurn(text="Respondo sin la herramienta."),
        ]
    )
    _, provider, _, _ = await run_simple(provider, {"query_results": handler})
    assert handler.calls == []
    first, second = _observations(provider)
    assert "repeated" not in first
    assert second["repeated"] is True
    assert "ya falló con los mismos argumentos" in second["detail"]
