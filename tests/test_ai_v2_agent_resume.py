"""Tests for the T3 loop resumption: resume_pending_turn.

Reuses the T2 fake-provider harness (ScriptedChatProvider,
RecordingHandler) and drives the REAL InMemoryPendingRunStore through
a pause -> resume round trip. No HTTP, no real providers.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from core.ai_v2.agent.confirmations import (
    AlreadyClaimedPendingRun,
    InMemoryPendingRunStore,
    PendingRun,
)
from core.ai_v2.agent.events import (
    ConfirmationRequiredEvent,
    DoneEvent,
    ErrorEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from core.ai_v2.agent.loop import (
    MAX_TURN_CONFIRMATIONS,
    MSG_CONFIRMATION_ARGS_CHANGED,
    MSG_CONFIRMATION_CONSUMED,
    MSG_CONFIRMATION_CORRUPT,
    MSG_CONFIRMATION_EXPIRED,
    MSG_CONFIRMATION_FOREIGN,
    MSG_CONFIRMATION_LIMIT,
    MSG_CONFIRMATION_NOT_FOUND,
    MSG_DENIED_BY_USER,
    MSG_DENIED_NO_RETRY,
    MSG_PROVIDER_ERROR,
    MSG_TURN_CANCELLED,
    resume_pending_turn,
    run_agent_turn,
)
from core.ai_v2.agent.models import NoArgs, SectionAutoArgs, ToolState
from core.ai_v2.agent.turn import ChatTurn
from tests.test_ai_v2_agent_loop import (
    BASE_MESSAGES,
    RecordingHandler,
    ScriptedChatProvider,
    SESSION,
    collect,
    tool_call,
)

AUTO_ARGS_JSON = '{"start": [0, 0], "end": [100, 0], "n_sections": 5}'
MANUAL_ARGS_JSON = '{"sections": [{"origin": [1, 2], "azimuth": 45}]}'
OTHER_ARGS_JSON = '{"start": [0, 0], "end": [100, 0], "n_sections": 9}'


class CountingStore(InMemoryPendingRunStore):
    """Real store that also records every created PendingRun."""

    def __init__(self) -> None:
        super().__init__()
        self.created_runs: list[PendingRun] = []

    def create(self, run: PendingRun) -> str:
        self.created_runs.append(run)
        return super().create(run)


class MutableStateStub:
    """Async state provider fake whose ToolState can be swapped."""

    def __init__(self, state: ToolState) -> None:
        self.state = state
        self.asked_sessions: list[str] = []

    async def __call__(self, session_id: str) -> ToolState:
        self.asked_sessions.append(session_id)
        return self.state


async def pause_for_confirmation(
    executor: dict[str, Any],
    state: ToolState,
    *,
    tool_calls: list[Any] | None = None,
    store: InMemoryPendingRunStore | None = None,
) -> tuple[ScriptedChatProvider, InMemoryPendingRunStore, str]:
    """Run one turn that pauses on a confirmation; return id + store."""
    calls = tool_calls if tool_calls is not None else [
        tool_call("generate_sections_auto", AUTO_ARGS_JSON, call_id="c-conf")
    ]
    provider = ScriptedChatProvider([ChatTurn(tool_calls=calls)])
    store = store or InMemoryPendingRunStore()
    stub = MutableStateStub(state)
    events = await collect(
        run_agent_turn(
            session_id=SESSION,
            messages=list(BASE_MESSAGES),
            provider=provider,
            model="test-model",
            executor=executor,
            pending_store=store,
            state_provider=stub,
        )
    )
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "confirmation_required"
    pending_id = next(
        e.invocation_id
        for e in events
        if isinstance(e, ConfirmationRequiredEvent)
    )
    return provider, store, pending_id


async def resume(
    store: InMemoryPendingRunStore,
    invocation_id: str,
    executor: dict[str, Any],
    state: ToolState,
    *,
    approved: bool,
    provider: ScriptedChatProvider,
    session_id: str = SESSION,
    model: str | None = None,
) -> list[Any]:
    kwargs: dict[str, Any] = {}
    if model is not None:
        kwargs["model"] = model
    return await collect(
        resume_pending_turn(
            session_id=session_id,
            invocation_id=invocation_id,
            approved=approved,
            provider=provider,
            executor=executor,
            pending_store=store,
            state_provider=MutableStateStub(state),
            **kwargs,
        )
    )


# ---------------------------------------------------------------------------
# Approve: executes exactly once and continues the same loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_executes_once_and_continues():
    handler = RecordingHandler({"n_sections": 5})
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    continuation = ScriptedChatProvider([ChatTurn(text="5 secciones generadas.")])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert [type(e).__name__ for e in events] == [
        "ToolCallEvent",
        "ToolResultEvent",
        "TextEvent",
        "DoneEvent",
    ]
    call_event = events[0]
    result_event = events[1]
    assert isinstance(call_event, ToolCallEvent)
    assert call_event.invocation_id == invocation_id
    assert call_event.name == "generate_sections_auto"
    assert isinstance(result_event, ToolResultEvent)
    assert result_event.ok is True
    assert handler.calls == [(SESSION, SectionAutoArgs(
        start=[0.0, 0.0], end=[100.0, 0.0], n_sections=5
    ))]
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
    sent = continuation.requests[0]
    assert sent[-2]["role"] == "assistant"
    assert sent[-2]["tool_calls"][0]["id"] == "c-conf"
    assert sent[-2]["tool_calls"][0]["function"]["arguments"] == AUTO_ARGS_JSON
    assert sent[-1]["role"] == "tool"
    assert sent[-1]["tool_call_id"] == "c-conf"
    assert json.loads(sent[-1]["content"]) == {"n_sections": 5}
    with pytest.raises(AlreadyClaimedPendingRun):
        store.claim(invocation_id, SESSION)


# ---------------------------------------------------------------------------
# Deny: no execution, safe denial observation, loop continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deny_continues_without_executing():
    handler = RecordingHandler({"n_sections": 5})
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    continuation = ScriptedChatProvider([ChatTurn(text="Entendido, no lo hago.")])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=False, provider=continuation,
    )
    assert handler.calls == []
    assert [type(e).__name__ for e in events] == [
        "ToolCallEvent",
        "ToolResultEvent",
        "TextEvent",
        "DoneEvent",
    ]
    result_event = events[1]
    assert isinstance(result_event, ToolResultEvent)
    assert result_event.ok is False
    assert result_event.error == "denied_by_user"
    assert result_event.summary == MSG_DENIED_BY_USER
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
    sent = continuation.requests[0]
    observation = json.loads(sent[-1]["content"])
    assert observation == {
        "ok": False,
        "error": "denied_by_user",
        "message": MSG_DENIED_BY_USER,
    }


# ---------------------------------------------------------------------------
# State fingerprint: re-evaluate policy when the session changed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_changed_rearms_confirmation_without_executing():
    handler = RecordingHandler({"n_sections": 5})
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    continuation = ScriptedChatProvider([])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=7), approved=True, provider=continuation,
    )
    assert handler.calls == []
    assert continuation.requests == []
    assert [type(e).__name__ for e in events] == [
        "ToolCallEvent",
        "ConfirmationRequiredEvent",
        "DoneEvent",
    ]
    rearm_call, rearm_confirm, done = events
    assert isinstance(rearm_confirm, ConfirmationRequiredEvent)
    assert rearm_confirm.invocation_id != invocation_id
    assert "7 secciones" in rearm_confirm.args_summary
    assert isinstance(done, DoneEvent)
    assert done.finish_reason == "confirmation_required"
    fresh = store.claim(rearm_confirm.invocation_id, SESSION)
    assert fresh.state_fingerprint == ToolState(n_sections=7).fingerprint()
    with pytest.raises(AlreadyClaimedPendingRun):
        store.claim(invocation_id, SESSION)


@pytest.mark.asyncio
async def test_state_changed_to_clean_state_runs_autonomously_on_approval():
    handler = RecordingHandler({"n_sections": 5})
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    continuation = ScriptedChatProvider([ChatTurn(text="Listo.")])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(), approved=True, provider=continuation,
    )
    assert len(handler.calls) == 1
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"


# ---------------------------------------------------------------------------
# Typed claim rejections surface as explicit error events, never crashes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_pending_is_rejected_without_execution():
    handler = RecordingHandler()
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    pending = store.claim(invocation_id, SESSION)
    store.create(pending.model_copy(update={"expires_at": pending.created_at - 1.0}))
    continuation = ScriptedChatProvider([])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert handler.calls == []
    assert continuation.requests == []
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.content == MSG_CONFIRMATION_EXPIRED
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "error"


@pytest.mark.asyncio
async def test_foreign_session_is_rejected_without_execution():
    handler = RecordingHandler()
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    continuation = ScriptedChatProvider([])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=True, provider=continuation,
        session_id="sess-other",
    )
    assert handler.calls == []
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    assert isinstance(events[0], ErrorEvent)
    assert events[0].content == MSG_CONFIRMATION_FOREIGN


@pytest.mark.asyncio
async def test_double_claim_is_rejected_as_consumed():
    handler = RecordingHandler()
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    continuation = ScriptedChatProvider([ChatTurn(text="ok")])
    first = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=False, provider=continuation,
    )
    assert isinstance(first[-1], DoneEvent)
    assert handler.calls == []
    second = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert handler.calls == []
    assert [type(e).__name__ for e in second] == ["ErrorEvent", "DoneEvent"]
    assert isinstance(second[0], ErrorEvent)
    assert second[0].content == MSG_CONFIRMATION_CONSUMED


@pytest.mark.asyncio
async def test_unknown_invocation_id_is_rejected():
    handler = RecordingHandler()
    _, store, _ = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    continuation = ScriptedChatProvider([])
    events = await resume(
        store, "inv_unknown", {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    assert isinstance(events[0], ErrorEvent)
    assert events[0].content == MSG_CONFIRMATION_NOT_FOUND


@pytest.mark.asyncio
async def test_args_changed_invalidation_is_rejected_without_execution():
    handler = RecordingHandler()
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    pending = store.claim(invocation_id, SESSION)
    store.create(pending.model_copy(update={"args_sha256": "0" * 64}))
    continuation = ScriptedChatProvider([])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert handler.calls == []
    assert continuation.requests == []
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    assert isinstance(events[0], ErrorEvent)
    assert events[0].content == MSG_CONFIRMATION_ARGS_CHANGED


@pytest.mark.asyncio
async def test_corrupt_pending_messages_fail_closed():
    handler = RecordingHandler()
    _, store, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3)
    )
    pending = store.claim(invocation_id, SESSION)
    store.create(
        pending.model_copy(update={"messages": [{"role": "user", "content": "x"}]})
    )
    continuation = ScriptedChatProvider([])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert handler.calls == []
    assert isinstance(events[0], ErrorEvent)
    assert events[0].content == MSG_CONFIRMATION_CORRUPT


# ---------------------------------------------------------------------------
# Multi-call turn: EVERY unanswered tool_call_id is answered on resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multicall_resume_answers_every_id_and_continues():
    handler_replace = RecordingHandler({"n_sections": 5})
    handler_state = RecordingHandler({"n_sections": 5, "n_results": 0})
    handler_meshes = RecordingHandler({"n_meshes": 0})
    executor = {
        "generate_sections_auto": handler_replace,
        "get_workflow_state": handler_state,
        "list_meshes": handler_meshes,
    }
    calls = [
        tool_call("generate_sections_auto", AUTO_ARGS_JSON, call_id="c-conf"),
        tool_call("get_workflow_state", "", call_id="c-read1"),
        tool_call("list_meshes", "", call_id="c-read2"),
    ]
    _, store, invocation_id = await pause_for_confirmation(
        executor, ToolState(n_sections=3), tool_calls=calls
    )
    continuation = ScriptedChatProvider([ChatTurn(text="Listo.")])
    events = await resume(
        store, invocation_id, executor,
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert handler_replace.calls == [(SESSION, SectionAutoArgs(
        start=[0.0, 0.0], end=[100.0, 0.0], n_sections=5
    ))]
    assert handler_state.calls == [(SESSION, NoArgs())]
    assert handler_meshes.calls == [(SESSION, NoArgs())]
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert [r.ok for r in results] == [True, True, True]
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
    sent = continuation.requests[0]
    tool_messages = [m for m in sent if m.get("role") == "tool"]
    assert len(tool_messages) == 3
    assert [m["tool_call_id"] for m in tool_messages] == [
        "c-conf",
        "c-read1",
        "c-read2",
    ]
    assistant_messages = [
        m for m in sent
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert len(assistant_messages) == 1
    assert [c["id"] for c in assistant_messages[0]["tool_calls"]] == [
        "c-conf",
        "c-read1",
        "c-read2",
    ]


@pytest.mark.asyncio
async def test_multicall_deny_answers_every_id_without_executing():
    handler_replace = RecordingHandler()
    handler_state = RecordingHandler()
    handler_meshes = RecordingHandler()
    executor = {
        "generate_sections_auto": handler_replace,
        "get_workflow_state": handler_state,
        "list_meshes": handler_meshes,
    }
    calls = [
        tool_call("generate_sections_auto", AUTO_ARGS_JSON, call_id="c-conf"),
        tool_call("get_workflow_state", "", call_id="c-read1"),
        tool_call("list_meshes", "", call_id="c-read2"),
    ]
    _, store, invocation_id = await pause_for_confirmation(
        executor, ToolState(n_sections=3), tool_calls=calls
    )
    continuation = ScriptedChatProvider([ChatTurn(text="Cancelado.")])
    events = await resume(
        store, invocation_id, executor,
        ToolState(n_sections=3), approved=False, provider=continuation,
    )
    assert handler_replace.calls == []
    assert handler_state.calls == []
    assert handler_meshes.calls == []
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(results) == 3
    assert [r.error for r in results] == [
        "denied_by_user",
        "skipped_turn_denied",
        "skipped_turn_denied",
    ]
    assert results[0].summary == MSG_DENIED_BY_USER
    assert results[1].summary == MSG_TURN_CANCELLED
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
    sent = continuation.requests[0]
    tool_messages = [m for m in sent if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == [
        "c-conf",
        "c-read1",
        "c-read2",
    ]
    for message in tool_messages:
        payload = json.loads(message["content"])
        assert payload["ok"] is False


@pytest.mark.asyncio
async def test_multicall_resume_stops_on_sibling_confirmation():
    handler_auto = RecordingHandler({"n_sections": 5})
    handler_manual = RecordingHandler({"n_sections": 5})
    executor = {
        "generate_sections_auto": handler_auto,
        "generate_sections_manual": handler_manual,
    }
    calls = [
        tool_call("generate_sections_auto", AUTO_ARGS_JSON, call_id="c-1"),
        tool_call(
            "generate_sections_manual",
            '{"sections": [{"origin": [1, 2], "azimuth": 45}]}',
            call_id="c-2",
        ),
    ]
    _, store, invocation_id = await pause_for_confirmation(
        executor, ToolState(n_sections=3), tool_calls=calls
    )
    continuation = ScriptedChatProvider([])
    events = await resume(
        store, invocation_id, executor,
        ToolState(n_sections=3), approved=True, provider=continuation,
    )
    assert len(handler_auto.calls) == 1
    assert handler_manual.calls == []
    assert continuation.requests == []
    confirms = [e for e in events if isinstance(e, ConfirmationRequiredEvent)]
    assert len(confirms) == 1
    assert confirms[0].invocation_id != invocation_id
    assert confirms[0].name == "generate_sections_manual"
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "confirmation_required"


# ---------------------------------------------------------------------------
# Provider degradation regression: flag True but provider rejects tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_rejection_at_runtime_degrades_without_fake_text():
    class RejectingProvider(ScriptedChatProvider):
        async def stream_chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            self.requests.append([dict(m) for m in messages])
            raise RuntimeError("tools not supported by the loaded model")

    provider = RejectingProvider([])
    store = InMemoryPendingRunStore()
    events = await collect(
        run_agent_turn(
            session_id=SESSION,
            messages=list(BASE_MESSAGES),
            provider=provider,
            model="test-model",
            executor={"list_meshes": RecordingHandler()},
            pending_store=store,
            state_provider=MutableStateStub(ToolState()),
        )
    )
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.content == MSG_PROVIDER_ERROR
    assert "loaded model" not in error.content
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "error"


# ---------------------------------------------------------------------------
# Guardrail 5: a call denied in this turn is never re-requested
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_denied_call_is_not_retried_in_same_turn():
    handler = RecordingHandler({"n_sections": 5})
    store = CountingStore()
    _, _, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3), store=store
    )
    continuation = ScriptedChatProvider([
        ChatTurn(tool_calls=[
            tool_call("generate_sections_auto", AUTO_ARGS_JSON, call_id="c-retry")
        ]),
        ChatTurn(text="Entendido, sigo con lo demás."),
    ])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=False, provider=continuation,
    )
    assert handler.calls == []
    assert len(store.created_runs) == 1
    assert [type(e).__name__ for e in events] == [
        "ToolCallEvent",
        "ToolResultEvent",
        "ToolCallEvent",
        "ToolResultEvent",
        "TextEvent",
        "DoneEvent",
    ]
    retry_call, retry_result = events[2], events[3]
    assert isinstance(retry_call, ToolCallEvent)
    assert retry_call.name == "generate_sections_auto"
    assert retry_call.requires_confirmation is False
    assert isinstance(retry_result, ToolResultEvent)
    assert retry_result.ok is False
    assert retry_result.error == "denied_by_user"
    assert retry_result.summary == MSG_DENIED_NO_RETRY
    assert not any(isinstance(e, ConfirmationRequiredEvent) for e in events)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
    assert len(continuation.requests) == 2
    answered = continuation.requests[1]
    assert answered[-1]["role"] == "tool"
    assert answered[-1]["tool_call_id"] == "c-retry"
    assert json.loads(answered[-1]["content"]) == {
        "ok": False,
        "error": "denied_by_user",
        "message": MSG_DENIED_NO_RETRY,
    }


@pytest.mark.asyncio
async def test_denial_of_different_args_does_not_block_distinct_call():
    handler = RecordingHandler({"n_sections": 5})
    store = CountingStore()
    _, _, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3), store=store
    )
    continuation = ScriptedChatProvider([
        ChatTurn(tool_calls=[
            tool_call("generate_sections_auto", OTHER_ARGS_JSON, call_id="c-dist")
        ]),
    ])
    events = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=False, provider=continuation,
    )
    assert handler.calls == []
    confirms = [e for e in events if isinstance(e, ConfirmationRequiredEvent)]
    assert len(confirms) == 1
    assert confirms[0].invocation_id != invocation_id
    assert confirms[0].name == "generate_sections_auto"
    assert len(store.created_runs) == 2
    assert store.created_runs[0].turn_confirmations == 1
    assert store.created_runs[1].turn_confirmations == 2
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "confirmation_required"
    fresh = store.claim(confirms[0].invocation_id, SESSION)
    assert fresh.tool_call_id == "c-dist"
    assert fresh.turn_confirmations == 2


@pytest.mark.asyncio
async def test_prior_turn_denial_does_not_block_a_new_turn():
    handler = RecordingHandler({"n_sections": 5})
    store = CountingStore()
    _, _, invocation_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3), store=store
    )
    first_turn = ScriptedChatProvider([ChatTurn(text="Entendido.")])
    denied = await resume(
        store, invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=3), approved=False, provider=first_turn,
    )
    assert isinstance(denied[-1], DoneEvent)
    assert denied[-1].finish_reason == "stop"
    history = [dict(message) for message in first_turn.requests[0]]
    history.append({"role": "user", "content": "Insiste: genera secciones"})
    new_store = CountingStore()
    new_provider = ScriptedChatProvider([
        ChatTurn(tool_calls=[
            tool_call("generate_sections_auto", AUTO_ARGS_JSON, call_id="c-new")
        ]),
    ])
    events = await collect(
        run_agent_turn(
            session_id=SESSION,
            messages=history,
            provider=new_provider,
            model="test-model",
            executor={"generate_sections_auto": handler},
            pending_store=new_store,
            state_provider=MutableStateStub(ToolState(n_sections=3)),
        )
    )
    assert handler.calls == []
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "confirmation_required"
    assert len(new_store.created_runs) == 1
    assert new_store.created_runs[0].turn_confirmations == 1


# ---------------------------------------------------------------------------
# Guardrail 4: max confirmations per user turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_confirmation_cap_blocks_third_rearm_pause():
    assert MAX_TURN_CONFIRMATIONS == 2
    handler = RecordingHandler({"n_sections": 5})
    store = CountingStore()
    _, _, first_id = await pause_for_confirmation(
        {"generate_sections_auto": handler}, ToolState(n_sections=3), store=store
    )
    rearm_provider = ScriptedChatProvider([])
    first = await resume(
        store, first_id, {"generate_sections_auto": handler},
        ToolState(n_sections=7), approved=True, provider=rearm_provider,
    )
    confirms = [e for e in first if isinstance(e, ConfirmationRequiredEvent)]
    assert len(confirms) == 1
    assert store.created_runs[1].turn_confirmations == 2
    final_provider = ScriptedChatProvider([ChatTurn(text="Sigo sin eso.")])
    second = await resume(
        store, confirms[0].invocation_id, {"generate_sections_auto": handler},
        ToolState(n_sections=9), approved=True, provider=final_provider,
    )
    assert handler.calls == []
    assert len(store.created_runs) == 2
    assert [type(e).__name__ for e in second] == [
        "ToolCallEvent",
        "ToolResultEvent",
        "TextEvent",
        "DoneEvent",
    ]
    blocked_call, blocked_result = second[0], second[1]
    assert isinstance(blocked_call, ToolCallEvent)
    assert blocked_call.requires_confirmation is False
    assert isinstance(blocked_result, ToolResultEvent)
    assert blocked_result.ok is False
    assert blocked_result.error == "confirmation_limit_reached"
    assert blocked_result.summary == MSG_CONFIRMATION_LIMIT
    assert not any(isinstance(e, ConfirmationRequiredEvent) for e in second)
    assert isinstance(second[-1], DoneEvent)
    assert second[-1].finish_reason == "stop"
    sent = final_provider.requests[0]
    assert sent[-1]["role"] == "tool"
    assert json.loads(sent[-1]["content"]) == {
        "ok": False,
        "error": "confirmation_limit_reached",
        "message": MSG_CONFIRMATION_LIMIT,
    }


@pytest.mark.asyncio
async def test_sibling_pause_increments_counter_and_cap_blocks_last_sibling():
    handler_auto = RecordingHandler({"n_sections": 5})
    handler_manual = RecordingHandler({"n_sections": 5})
    executor = {
        "generate_sections_auto": handler_auto,
        "generate_sections_manual": handler_manual,
    }
    calls = [
        tool_call("generate_sections_auto", AUTO_ARGS_JSON, call_id="c-1"),
        tool_call("generate_sections_manual", MANUAL_ARGS_JSON, call_id="c-2"),
        tool_call("generate_sections_auto", OTHER_ARGS_JSON, call_id="c-3"),
    ]
    store = CountingStore()
    _, _, first_id = await pause_for_confirmation(
        executor, ToolState(n_sections=3), tool_calls=calls, store=store
    )
    sibling_provider = ScriptedChatProvider([])
    first = await resume(
        store, first_id, executor, ToolState(n_sections=3),
        approved=True, provider=sibling_provider,
    )
    confirms = [e for e in first if isinstance(e, ConfirmationRequiredEvent)]
    assert len(confirms) == 1
    assert confirms[0].name == "generate_sections_manual"
    assert store.created_runs[0].turn_confirmations == 1
    assert store.created_runs[1].turn_confirmations == 2
    assert len(handler_auto.calls) == 1
    assert handler_manual.calls == []
    final_provider = ScriptedChatProvider([ChatTurn(text="Listo.")])
    second = await resume(
        store, confirms[0].invocation_id, executor, ToolState(n_sections=3),
        approved=True, provider=final_provider,
    )
    assert len(handler_auto.calls) == 1
    assert len(handler_manual.calls) == 1
    assert len(store.created_runs) == 2
    results = [e for e in second if isinstance(e, ToolResultEvent)]
    assert len(results) == 2
    assert results[0].ok is True
    assert results[1].ok is False
    assert results[1].error == "confirmation_limit_reached"
    assert results[1].summary == MSG_CONFIRMATION_LIMIT
    assert not any(isinstance(e, ConfirmationRequiredEvent) for e in second)
    assert isinstance(second[-1], DoneEvent)
    assert second[-1].finish_reason == "stop"
