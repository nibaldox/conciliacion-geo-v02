"""Tests for the T2 agent loop: run_agent_turn with a FAKE provider.

No real providers, no network, no HTTP: the provider is a scripted
``ChatTurn`` factory and the executor/pending/state dependencies are
recording fakes. One test per matrix case (plan section 8-T2).
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from core.ai_v2.agent.confirmations import (
    PendingRun,
    PendingRunStore,
    canonical_args_sha256,
)
from core.ai_v2.agent.events import (
    ConfirmationRequiredEvent,
    DoneEvent,
    ErrorEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
    event_to_ndjson,
    parse_event_line,
)
from core.ai_v2.agent.loop import (
    DEFAULT_MAX_ITERATIONS,
    MSG_INVALID_ARGS,
    MSG_MAX_ITERATIONS,
    MSG_PROVIDER_ERROR,
    MSG_PROVIDER_TIMEOUT,
    MSG_PROVIDER_UNSUPPORTED,
    MSG_TOOL_FAILED,
    MSG_TOOL_UNAVAILABLE,
    run_agent_turn,
)
from core.ai_v2.agent.models import NoArgs, SectionAutoArgs, ToolState
from core.ai_v2.agent.turn import ChatTurn, ToolCallRequest
from core.ai_v2.errors import ProviderUnavailable
from core.ai_v2.models import AIUsage
from core.ai_v2.providers.base import BaseProvider

SESSION = "sess-1"
BASE_MESSAGES = [
    {"role": "system", "content": "Eres el agente."},
    {"role": "user", "content": "Genera secciones"},
]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class ScriptedChatProvider(BaseProvider):
    """Returns pre-scripted ChatTurns (or raises); records requests."""

    def __init__(
        self,
        turns: list[ChatTurn | Exception],
        *,
        supports_tool_calls: bool = True,
    ) -> None:
        self._turns = list(turns)
        self._supports = supports_tool_calls
        self.requests: list[list[dict[str, Any]]] = []

    @property
    def supports_tool_calls(self) -> bool:
        return self._supports

    async def stream_chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> ChatTurn:
        self.requests.append([dict(m) for m in messages])
        item = self._turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def stream(self, messages, *, model, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("report stream() must not be used by the loop")
        yield  # noqa: unreachable - makes this an async generator

    async def list_models(self) -> list[str]:
        return []

    async def health_check(self) -> bool:
        return True


class TurnThenHangProvider(BaseProvider):
    """Answers ONE scripted tool-call turn, then blocks forever.

    Second and later ``stream_chat`` calls await a never-set event, so a
    consumer that stops mid-stream leaves the generator genuinely
    suspended instead of finished — the shape of a client disconnect.
    """

    def __init__(self, turn: ChatTurn) -> None:
        self._turn = turn
        self._never = asyncio.Event()
        self.name = "fake"
        self.calls = 0

    @property
    def supports_tool_calls(self) -> bool:
        return True

    async def stream_chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> ChatTurn:
        self.calls += 1
        if self.calls == 1:
            return self._turn
        await self._never.wait()
        raise AssertionError("unreachable: the hang event is never set")

    async def stream(self, messages, *, model, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("report stream() must not be used by the loop")
        yield  # noqa: unreachable - makes this an async generator

    async def list_models(self) -> list[str]:
        return []

    async def health_check(self) -> bool:
        return True


class DeltaChatProvider(BaseProvider):
    """Calls ``on_text_delta`` with scripted fragments, then returns.

    Shape of a real streaming provider: each scripted turn pushes its
    text fragments incrementally while the turn is still running, and
    the final ``ChatTurn`` carries the full accumulated text.
    """

    def __init__(
        self,
        turns: list[tuple[list[str], ChatTurn]],
        *,
        call_deltas: bool = True,
    ) -> None:
        self._turns = [(list(deltas), turn) for deltas, turn in turns]
        self._call_deltas = call_deltas
        self.seen_on_text_delta: list[bool] = []
        self.requests: list[list[dict[str, Any]]] = []

    @property
    def supports_tool_calls(self) -> bool:
        return True

    async def stream_chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> ChatTurn:
        self.requests.append([dict(m) for m in messages])
        on_text_delta = kwargs.get("on_text_delta")
        self.seen_on_text_delta.append(on_text_delta is not None)
        deltas, turn = self._turns.pop(0)
        if self._call_deltas and on_text_delta is not None:
            for delta in deltas:
                on_text_delta(delta)
        return turn

    async def stream(self, messages, *, model, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("report stream() must not be used by the loop")
        yield  # noqa: unreachable - makes this an async generator

    async def list_models(self) -> list[str]:
        return []

    async def health_check(self) -> bool:
        return True


class RecordingPendingStore(PendingRunStore):
    """In-memory fake of the frozen T0 interface."""

    def __init__(self) -> None:
        self.created: list[PendingRun] = []
        self.invalidated: list[str] = []

    def create(self, run: PendingRun) -> str:
        self.created.append(run)
        return run.invocation_id

    def claim(self, invocation_id: str, session_id: str) -> PendingRun:
        raise NotImplementedError("claim lands in T3")

    def invalidate(self, invocation_id: str) -> None:
        self.invalidated.append(invocation_id)


class FailingPendingStore(RecordingPendingStore):
    def create(self, run: PendingRun) -> str:
        raise RuntimeError("store down")


class RecordingHandler:
    """Async handler fake: records (session_id, args), returns or raises."""

    def __init__(
        self,
        result: dict[str, Any] | None = None,
        *,
        exc: Exception | None = None,
        sleep_s: float = 0.0,
    ) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._result = result if result is not None else {"ok": True}
        self._exc = exc
        self._sleep_s = sleep_s

    async def __call__(self, session_id: str, args: Any) -> dict[str, Any]:
        self.calls.append((session_id, args))
        if self._sleep_s:
            await asyncio.sleep(self._sleep_s)
        if self._exc is not None:
            raise self._exc
        return self._result


class StateStub:
    """Async state provider fake that records the session ids asked."""

    def __init__(self, state: ToolState) -> None:
        self._state = state
        self.asked_sessions: list[str] = []

    async def __call__(self, session_id: str) -> ToolState:
        self.asked_sessions.append(session_id)
        return self._state


def tool_call(
    name: str,
    arguments: str = "",
    *,
    call_id: str = "call_1",
    valid: bool = True,
) -> ToolCallRequest:
    return ToolCallRequest(
        call_id=call_id,
        name=name,
        arguments=arguments,
        arguments_valid=valid,
    )


async def collect(gen: Any) -> list[Any]:
    return [event async for event in gen]


async def run_simple(
    provider: BaseProvider,
    executor: dict[str, Any],
    state: ToolState | None = None,
    **kwargs: Any,
) -> tuple[list[Any], Any, RecordingPendingStore, StateStub]:
    store = RecordingPendingStore()
    stub = StateStub(state or ToolState())
    events = await collect(
        run_agent_turn(
            session_id=SESSION,
            messages=list(BASE_MESSAGES),
            provider=provider,
            model="test-model",
            executor=executor,
            pending_store=store,
            state_provider=stub,
            **kwargs,
        )
    )
    return events, provider, store, stub


# ---------------------------------------------------------------------------
# Matrix 1: fragmented tool call assembled (provider layer + loop)
# ---------------------------------------------------------------------------


def _frag_chunk(
    tool_frags: list[Any] | None = None,
    *,
    finish_reason: str | None = None,
) -> Any:
    from openai.types.chat.chat_completion_chunk import (
        ChatCompletionChunk,
        Choice,
        ChoiceDelta,
    )

    delta = ChoiceDelta(content=None, tool_calls=tool_frags)
    return ChatCompletionChunk(
        id="chatcmpl-test",
        created=0,
        model="test-model",
        object="chat.completion.chunk",
        choices=[
            Choice(index=0, delta=delta, finish_reason=finish_reason)  # type: ignore[arg-type]
        ],
        usage=None,
    )


def _frag(
    index: int,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> Any:
    from openai.types.chat.chat_completion_chunk import (
        ChoiceDeltaToolCall,
        ChoiceDeltaToolCallFunction,
    )

    function = None
    if name is not None or arguments is not None:
        function = ChoiceDeltaToolCallFunction(name=name, arguments=arguments)
    return ChoiceDeltaToolCall(
        index=index,
        id=call_id,
        type="function" if call_id else None,
        function=function,
    )


def _simulated_chat_provider(turns: list[list[Any]]) -> Any:
    """Provider whose each ``create`` call streams ONE scripted turn."""
    from core.ai_v2.providers.openai_compat import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        base_url="http://localhost:9/v1",
        api_key="test",
        name="simulated",
        supports_tool_calls=True,
    )
    remaining = [list(turn) for turn in turns]

    async def fake_create(**kwargs: Any) -> Any:
        async def _stream() -> Any:
            if remaining:
                for chunk in remaining.pop(0):
                    yield chunk
            else:
                yield _frag_chunk(finish_reason="stop")

        return _stream()

    provider._client.chat.completions.create = fake_create  # type: ignore[method-assign]
    return provider


@pytest.mark.asyncio
async def test_fragmented_arguments_assembled_before_execution():
    provider = _simulated_chat_provider(
        [
            [
                _frag_chunk(
                    tool_frags=[
                        _frag(0, call_id="call_1", name="get_mesh_info",
                              arguments='{"mesh')
                    ]
                ),
                _frag_chunk(tool_frags=[_frag(0, arguments='_id": "m-9"}')]),
                _frag_chunk(finish_reason="tool_calls"),
            ],
        ]
    )
    handler = RecordingHandler({"found": True})
    events, _, _, _ = await run_simple(provider, {"get_mesh_info": handler})
    assert len(handler.calls) == 1
    args = handler.calls[0][1]
    assert args.mesh_id == "m-9"
    tool_results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(tool_results) == 1
    assert tool_results[0].ok is True
    assert events[-1].finish_reason == "stop"


# ---------------------------------------------------------------------------
# Matrix 2 (+ READ tool autonomous execution)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_tool_runs_autonomously_then_final_text():
    handler = RecordingHandler({"n_sections": 0, "n_results": 0})
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[tool_call("get_workflow_state", "", call_id="call_1")]
            ),
            ChatTurn(text="La sesión está vacía."),
        ]
    )
    events, provider, store, stub = await run_simple(
        provider, {"get_workflow_state": handler}
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
    assert call_event.invocation_id.startswith("inv_")
    assert call_event.name == "get_workflow_state"
    assert call_event.requires_confirmation is False
    assert isinstance(result_event, ToolResultEvent)
    assert result_event.ok is True
    assert result_event.invocation_id == call_event.invocation_id
    assert handler.calls == [(SESSION, NoArgs())]
    assert stub.asked_sessions == [SESSION]
    assert store.created == []
    done = events[3]
    assert isinstance(done, DoneEvent)
    assert done.finish_reason == "stop"
    second_call_messages = provider.requests[1]
    assert second_call_messages[0]["role"] == "system"
    assert second_call_messages[1]["role"] == "user"
    assert second_call_messages[2] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_workflow_state", "arguments": ""},
            }
        ],
    }
    assert second_call_messages[3]["role"] == "tool"
    assert second_call_messages[3]["tool_call_id"] == "call_1"
    assert json.loads(second_call_messages[3]["content"]) == {
        "n_sections": 0,
        "n_results": 0,
    }


@pytest.mark.asyncio
async def test_usage_accumulates_and_duration_is_reported():
    usage = AIUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[tool_call("list_meshes", "", call_id="call_1")],
                usage=usage,
            ),
            ChatTurn(text="ok", usage=usage),
        ]
    )
    events, _, _, _ = await run_simple(provider, {"list_meshes": RecordingHandler()})
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.usage is not None
    assert done.usage.prompt_tokens == 20
    assert done.usage.completion_tokens == 10
    assert done.usage.total_tokens == 30
    assert done.usage.duration_ms >= 0.0


# ---------------------------------------------------------------------------
# Matrix 1 (provider layer + loop integration): fragmented arguments
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Matrix 3: invalid args -> no execution + safe observation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_schema_args_never_execute():
    handler = RecordingHandler()
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("get_mesh_info", '{"mesh_id": 123}', call_id="c1")
                ]
            ),
            ChatTurn(text="Reviso el identificador."),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"get_mesh_info": handler})
    assert handler.calls == []
    result = events[1]
    assert isinstance(result, ToolResultEvent)
    assert result.ok is False
    assert result.error == "schema_validation"
    assert result.summary == MSG_INVALID_ARGS
    tool_message = provider.requests[1][3]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "c1"
    observation = json.loads(tool_message["content"])
    assert observation == {
        "ok": False,
        "error": "invalid_arguments",
        "reason": "schema_validation",
        "message": MSG_INVALID_ARGS,
        "detail": "Argumentos inválidos: 'mesh_id' debe ser texto.",
    }
    assert "123" not in tool_message["content"]
    assert events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_invalid_json_args_never_execute():
    handler = RecordingHandler()
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call(
                        "get_mesh_info", '{"mesh_id": "m-', call_id="c1",
                        valid=False,
                    )
                ]
            ),
            ChatTurn(text="ok"),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"get_mesh_info": handler})
    assert handler.calls == []
    result = events[1]
    assert isinstance(result, ToolResultEvent)
    assert result.error == "invalid_json"
    observation = json.loads(provider.requests[1][3]["content"])
    assert observation["reason"] == "invalid_json"
    assert observation["message"] == MSG_INVALID_ARGS


# ---------------------------------------------------------------------------
# Matrix 4: unknown tool -> executor NOT invoked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_is_never_executed_and_answered():
    handler = RecordingHandler()
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("delete_everything", "{}", call_id="c-x")
                ]
            ),
            ChatTurn(text="No puedo hacer eso."),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"get_mesh_info": handler})
    assert handler.calls == []
    result = events[1]
    assert isinstance(result, ToolResultEvent)
    assert result.ok is False
    assert result.error == "unknown_tool"
    assert MSG_TOOL_UNAVAILABLE in result.summary
    tool_message = provider.requests[1][3]
    assert tool_message["tool_call_id"] == "c-x"
    observation = json.loads(tool_message["content"])
    assert observation["error"] == "unknown_tool"
    assert observation["message"] == MSG_TOOL_UNAVAILABLE
    assert events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_cataloged_tool_without_injected_handler_is_not_executed():
    provider = ScriptedChatProvider(
        [
            ChatTurn(tool_calls=[tool_call("list_meshes", "", call_id="c1")]),
            ChatTurn(text="ok"),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {})
    result = events[1]
    assert isinstance(result, ToolResultEvent)
    assert result.ok is False
    assert result.error == "handler_unavailable"


# ---------------------------------------------------------------------------
# Matrix 5: confirmation-required tool -> pause + pending recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_tool_with_prior_state_pauses_for_confirmation():
    handler = RecordingHandler()
    args_json = '{"start": [0, 0], "end": [100, 0], "n_sections": 5}'
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("generate_sections_auto", args_json, call_id="c-r")
                ]
            ),
        ]
    )
    state = ToolState(n_sections=3, has_design_mesh=True)
    events, _, store, stub = await run_simple(
        provider, {"generate_sections_auto": handler}, state=state
    )
    assert handler.calls == []
    assert [type(e).__name__ for e in events] == [
        "ToolCallEvent",
        "ConfirmationRequiredEvent",
        "DoneEvent",
    ]
    call_event, confirm_event, done = events
    assert isinstance(call_event, ToolCallEvent)
    assert call_event.requires_confirmation is True
    assert call_event.invocation_id.startswith("inv_")
    assert isinstance(confirm_event, ConfirmationRequiredEvent)
    assert confirm_event.invocation_id == call_event.invocation_id
    assert confirm_event.name == "generate_sections_auto"
    assert "3 secciones" in confirm_event.args_summary
    assert isinstance(done, DoneEvent)
    assert done.finish_reason == "confirmation_required"
    assert stub.asked_sessions == [SESSION]
    assert len(store.created) == 1
    pending = store.created[0]
    expected_args = SectionAutoArgs(
        start=[0.0, 0.0], end=[100.0, 0.0], n_sections=5
    ).model_dump()
    assert pending.invocation_id == call_event.invocation_id
    assert pending.session_id == SESSION
    assert pending.tool_name == "generate_sections_auto"
    assert pending.tool_call_id == "c-r"
    assert pending.args_sha256 == canonical_args_sha256(expected_args)
    assert pending.state_fingerprint == state.fingerprint()
    assert pending.expires_at > pending.created_at
    assert pending.messages[-1]["role"] == "assistant"
    assert pending.messages[-1]["tool_calls"][0]["id"] == "c-r"
    assert pending.messages[-1]["tool_calls"][0]["function"]["arguments"] == args_json


@pytest.mark.asyncio
async def test_replace_tool_in_clean_state_runs_autonomously():
    handler = RecordingHandler({"n_sections": 5})
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("generate_sections_auto", '{"start": [0, 0], "end": [100, 0]}',
                              call_id="c-a")
                ]
            ),
            ChatTurn(text="5 secciones generadas."),
        ]
    )
    events, _, store, _ = await run_simple(
        provider, {"generate_sections_auto": handler}, state=ToolState()
    )
    assert handler.calls != []
    assert store.created == []
    tool_results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert tool_results and tool_results[0].ok is True
    assert events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_delete_section_confirmation_names_section_and_invalidated_results():
    handler = RecordingHandler()
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("delete_section", '{"section_id": 4}', call_id="c-del")
                ]
            ),
        ]
    )
    state = ToolState(n_sections=10, n_results=160)
    events, _, store, _ = await run_simple(
        provider, {"delete_section": handler}, state=state
    )
    assert handler.calls == []
    confirmations = [e for e in events if isinstance(e, ConfirmationRequiredEvent)]
    assert len(confirmations) == 1
    expected = (
        "Elimina la sección con section_id 4 e invalida 160 resultados; "
        "los section_id posteriores bajan en 1. Parámetros: section_id=4"
    )
    assert confirmations[0].args_summary == expected
    assert store.created[0].args_summary == expected


@pytest.mark.asyncio
async def test_pending_store_failure_ends_in_error_not_confirmation():
    args_json = '{"start": [0, 0], "end": [100, 0]}'
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[tool_call("generate_sections_auto", args_json)]
            ),
        ]
    )
    store = FailingPendingStore()
    stub = StateStub(ToolState(n_sections=2))
    events = await collect(
        run_agent_turn(
            session_id=SESSION,
            messages=list(BASE_MESSAGES),
            provider=provider,
            model="test-model",
            executor={"generate_sections_auto": RecordingHandler()},
            pending_store=store,
            state_provider=stub,
        )
    )
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "error"
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    confirmations = [e for e in events if isinstance(e, ConfirmationRequiredEvent)]
    assert confirmations == []


# ---------------------------------------------------------------------------
# Matrix 6: multiple tool calls -> every tool_call_id answered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_tool_calls_each_get_matching_tool_response():
    handler_mesh = RecordingHandler({"found": True})
    handler_list = RecordingHandler({"n_meshes": 0})
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("get_mesh_info", '{"mesh_id": "a"}', call_id="call_a"),
                    tool_call("list_meshes", "", call_id="call_b"),
                ]
            ),
            ChatTurn(text="Listo."),
        ]
    )
    events, provider, _, _ = await run_simple(
        provider,
        {"get_mesh_info": handler_mesh, "list_meshes": handler_list},
    )
    call_events = [e for e in events if isinstance(e, ToolCallEvent)]
    result_events = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(call_events) == 2
    assert len(result_events) == 2
    assert len({e.invocation_id for e in call_events}) == 2
    assert handler_mesh.calls[0][0] == SESSION
    assert handler_mesh.calls[0][1].mesh_id == "a"
    assert handler_list.calls == [(SESSION, NoArgs())]
    tool_messages = [m for m in provider.requests[1] if m["role"] == "tool"]
    assert len(tool_messages) == 2
    assert [m["tool_call_id"] for m in tool_messages] == ["call_a", "call_b"]
    assert json.loads(tool_messages[0]["content"]) == {"found": True}
    assert json.loads(tool_messages[1]["content"]) == {"n_meshes": 0}
    assert events[-1].finish_reason == "stop"


# ---------------------------------------------------------------------------
# Matrix 7: handler error -> sanitized observation, loop continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_exception_is_sanitized_everywhere():
    secret = "SUPERSECRET-db-password"
    handler = RecordingHandler(exc=RuntimeError(f"boom {secret}"))
    provider = ScriptedChatProvider(
        [
            ChatTurn(tool_calls=[tool_call("list_meshes", "", call_id="c1")]),
            ChatTurn(text="Hubo un problema."),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"list_meshes": handler})
    result = events[1]
    assert isinstance(result, ToolResultEvent)
    assert result.ok is False
    assert result.error == "tool_execution_failed"
    assert result.summary == MSG_TOOL_FAILED
    observation = json.loads(provider.requests[1][3]["content"])
    assert observation == {
        "ok": False,
        "error": "tool_execution_failed",
        "message": MSG_TOOL_FAILED,
    }
    serialized = json.dumps(
        [
            event_to_ndjson(e) for e in events
        ] + [json.dumps(m) for m in provider.requests[1]],
        ensure_ascii=False,
    )
    assert secret not in serialized
    assert events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_handler_timeout_is_sanitized():
    handler = RecordingHandler(sleep_s=0.05, exc=asyncio.TimeoutError())
    provider = ScriptedChatProvider(
        [
            ChatTurn(tool_calls=[tool_call("list_meshes", "", call_id="c1")]),
            ChatTurn(text="ok"),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"list_meshes": handler})
    result = events[1]
    assert isinstance(result, ToolResultEvent)
    assert result.ok is False
    assert result.error == "tool_timeout"
    assert json.loads(provider.requests[1][3]["content"])["error"] == "tool_timeout"


# ---------------------------------------------------------------------------
# Matrix 8: iteration limit -> done(error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iteration_limit_stops_with_error_finish_reason():
    tool_turn = ChatTurn(
        tool_calls=[tool_call("get_workflow_state", "", call_id="c1")]
    )
    provider = ScriptedChatProvider([tool_turn, tool_turn, tool_turn])
    handler = RecordingHandler({"n_sections": 0})
    events, _, _, _ = await run_simple(
        provider,
        {"get_workflow_state": handler},
        max_iterations=3,
    )
    assert handler.calls != []
    assert len(handler.calls) == 3
    assert not any(isinstance(e, TextEvent) for e in events)
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert errors[0].content == MSG_MAX_ITERATIONS
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.finish_reason == "error"


def test_default_max_iterations_is_8():
    assert DEFAULT_MAX_ITERATIONS == 8


# ---------------------------------------------------------------------------
# Matrix 9: provider without support -> explicit error, never fake text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_provider_fails_fast_without_streaming():
    provider = ScriptedChatProvider([], supports_tool_calls=False)
    events, _, _, _ = await run_simple(provider, {})
    assert provider.requests == []
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.content == MSG_PROVIDER_UNSUPPORTED
    assert events[1].finish_reason == "error"


@pytest.mark.asyncio
async def test_provider_exception_is_sanitized():
    provider = ScriptedChatProvider(
        [ProviderUnavailable("upstream http://secret-host:9999 down")]
    )
    events, _, _, _ = await run_simple(provider, {})
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.content == MSG_PROVIDER_ERROR
    assert "secret-host" not in error.content
    assert events[1].finish_reason == "error"


@pytest.mark.asyncio
async def test_provider_timeout_is_reported():
    class SlowProvider(ScriptedChatProvider):
        async def stream_chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            self.requests.append([dict(m) for m in messages])
            await asyncio.sleep(0.5)
            raise AssertionError("should have been cancelled by the loop")

    provider = SlowProvider([])
    events, _, _, _ = await run_simple(provider, {}, timeout_s=0.05)
    assert [type(e).__name__ for e in events] == ["ErrorEvent", "DoneEvent"]
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.content == MSG_PROVIDER_TIMEOUT
    assert events[1].finish_reason == "error"


# ---------------------------------------------------------------------------
# Matrix + : typed NDJSON round trip and core/api isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_round_trip_through_ndjson():
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("generate_sections_auto", '{"start": [0, 0], "end": [1, 0]}',
                              call_id="c1")
                ]
            ),
        ]
    )
    events, _, _, _ = await run_simple(
        provider,
        {"generate_sections_auto": RecordingHandler()},
        state=ToolState(n_sections=1),
    )
    reparsed = [parse_event_line(event_to_ndjson(e)) for e in events]
    assert [type(e) for e in reparsed] == [type(e) for e in events]
    assert isinstance(reparsed[-1], DoneEvent)
    assert reparsed[-1].finish_reason == "confirmation_required"


@pytest.mark.asyncio
async def test_loop_does_not_import_api():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import core.ai_v2.agent.loop; "
            "bad = [m for m in sys.modules if m == 'api' or m.startswith('api.')]; "
            "print('API_MODULES:' + ','.join(bad))",
        ],
        cwd=str(__import__("pathlib").Path(__file__).parent.parent),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    line = next(
        l for l in result.stdout.splitlines() if l.startswith("API_MODULES:")
    )
    assert line == "API_MODULES:"


@pytest.mark.asyncio
async def test_cancelled_turn_persists_conversation_via_sink():
    """Client disconnect mid-stream (GeneratorExit) still persists the turn.

    The provider answers ONE tool-call turn and then blocks forever, so
    the generator stays genuinely suspended after the loop yields the
    ToolCallEvent (the confirmation-required pause keeps any role:tool
    message OUT of the conversation). Cancelling via ``aclose()`` must
    run the loop's ``finally`` exactly ONCE and hand the sink the
    accumulated conversation — system + user + the assistant
    ``tool_calls`` message — with nothing raised and nothing executed.
    """
    args_json = '{"start": [0, 0], "end": [100, 0], "n_sections": 5}'
    provider = TurnThenHangProvider(
        ChatTurn(
            tool_calls=[
                tool_call("generate_sections_auto", args_json, call_id="c1")
            ]
        )
    )
    handler = RecordingHandler()
    sunk: list[list[dict[str, Any]]] = []

    def sink(messages: list[dict[str, Any]]) -> None:
        sunk.append(messages)

    gen = run_agent_turn(
        session_id=SESSION,
        messages=list(BASE_MESSAGES),
        provider=provider,
        model="test-model",
        executor={"generate_sections_auto": handler},
        pending_store=RecordingPendingStore(),
        state_provider=StateStub(ToolState(n_sections=3, has_design_mesh=True)),
        conversation_sink=sink,
    )
    first = await gen.__anext__()
    assert isinstance(first, ToolCallEvent)
    assert first.requires_confirmation is True
    assert first.invocation_id.startswith("inv_")
    await gen.aclose()  # type: ignore[union-attr]
    assert len(sunk) == 1
    assert [m["role"] for m in sunk[0]] == ["system", "user", "assistant"]
    assistant = sunk[0][-1]
    assert assistant["tool_calls"][0]["id"] == "c1"
    assert assistant["tool_calls"][0]["function"]["name"] == (
        "generate_sections_auto"
    )
    assert handler.calls == []
    assert provider.calls == 1


# ---------------------------------------------------------------------------
# Style: agent text is normalized to neutral Spanish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_final_text_and_history_are_neutralized():
    provider = ScriptedChatProvider(
        [ChatTurn(text="Empezá cargando el mesh design.")]
    )
    sunk: list[list[dict[str, Any]]] = []
    events = await collect(
        run_agent_turn(
            session_id=SESSION,
            messages=list(BASE_MESSAGES),
            provider=provider,
            model="test-model",
            executor={},
            pending_store=RecordingPendingStore(),
            state_provider=StateStub(ToolState()),
            conversation_sink=sunk.append,
        )
    )
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert [e.content for e in text_events] == [
        "Empieza cargando el mesh design."
    ]
    assert sunk
    assistant = [m for m in sunk[0] if m["role"] == "assistant"]
    assert assistant[-1]["content"] == "Empieza cargando el mesh design."


@pytest.mark.asyncio
async def test_tool_calls_turn_text_is_neutralized_in_history():
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                text="Empezá con el mesh.",
                tool_calls=[tool_call("get_workflow_state", "", call_id="call_1")],
            ),
            ChatTurn(text="Listo."),
        ]
    )
    events, provider, _, _ = await run_simple(
        provider, {"get_workflow_state": RecordingHandler()}
    )
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert [e.content for e in text_events] == ["Listo."]
    assistant = provider.requests[1][2]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Empieza con el mesh."


# ---------------------------------------------------------------------------
# Streaming: incremental text deltas -> multiple TextEvents, no duplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streamed_deltas_emit_multiple_neutral_text_events():
    """Deltas stream as several TextEvents; concatenation is the final text.

    The provider pushes voseo fragments word by word: every fragment is
    neutralized at a safe word boundary (never mid-word), so the emitted
    concatenation equals the persisted neutral history exactly — with no
    duplicated tail.
    """
    provider = DeltaChatProvider(
        [(["Hola ", "tenés ", "razón"], ChatTurn(text="Hola tenés razón"))]
    )
    sunk: list[list[dict[str, Any]]] = []
    events = await collect(
        run_agent_turn(
            session_id=SESSION,
            messages=list(BASE_MESSAGES),
            provider=provider,
            model="test-model",
            executor={},
            pending_store=RecordingPendingStore(),
            state_provider=StateStub(ToolState()),
            conversation_sink=sunk.append,
        )
    )
    assert provider.seen_on_text_delta == [True]
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert len(text_events) >= 2
    assert "".join(e.content for e in text_events) == "Hola tienes razón"
    assert all("tenés" not in e.content for e in text_events)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
    assert sunk
    assistant = [m for m in sunk[0] if m["role"] == "assistant"]
    assert assistant[-1]["content"] == "Hola tienes razón"


@pytest.mark.asyncio
async def test_provider_without_deltas_falls_back_to_one_full_text_event():
    """A provider that never calls on_text_delta keeps the old behaviour."""
    provider = DeltaChatProvider(
        [([], ChatTurn(text="Empezá cargando el mesh design."))],
        call_deltas=False,
    )
    events, _, _, _ = await run_simple(provider, {})
    assert provider.seen_on_text_delta == [True]
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert [e.content for e in text_events] == [
        "Empieza cargando el mesh design."
    ]
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_streamed_tool_call_turn_text_is_not_duplicated():
    """Text streamed around a tool-call turn never re-emits at the end."""
    provider = DeltaChatProvider(
        [
            (
                ["Reviso ", "el mesh."],
                ChatTurn(
                    text="Reviso el mesh.",
                    tool_calls=[
                        tool_call("get_workflow_state", "", call_id="call_1")
                    ],
                ),
            ),
            (["Listo."], ChatTurn(text="Listo.")),
        ]
    )
    events, provider, _, _ = await run_simple(
        provider, {"get_workflow_state": RecordingHandler()}
    )
    assert provider.seen_on_text_delta == [True, True]
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert [e.content for e in text_events] == [
        "Reviso ",
        "el ",
        "mesh.",
        "Listo.",
    ]
    assert "".join(e.content for e in text_events) == "Reviso el mesh.Listo."
    assert "Reviso el mesh." not in [e.content for e in text_events]
    tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 1
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(results) == 1 and results[0].ok is True
    assert events[-1].finish_reason == "stop"
    assistant = provider.requests[1][2]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Reviso el mesh."


class TestObservationContent:
    """Structured truncation of oversized tool observations."""

    @staticmethod
    def _giant_observation() -> dict[str, Any]:
        observation: dict[str, Any] = {
            f"f{index:03d}": index for index in range(200)
        }
        observation["weighted_score"] = {
            "global_score": 65.56,
            "n_profiles": 120,
            "n_benches": 120,
            "weights": {"berm": 60, "angle": 10, "height": 30},
            "by_section": {f"S-{i:04d}": float(i % 100) for i in range(500)},
            "definition": "mean of per-section mean bench score",
        }
        observation["pct_by_parameter"] = {
            "height": {
                "cumple": 10,
                "no_cumple": 2,
                "n_evaluable": 12,
                "pct_cumple": 83.33,
            },
            "angle": {
                "cumple": 8,
                "no_cumple": 4,
                "n_evaluable": 12,
                "pct_cumple": 66.67,
            },
            "berm": {
                "cumple": 9,
                "no_cumple": 3,
                "n_evaluable": 12,
                "pct_cumple": 75.0,
            },
        }
        return observation

    def test_structured_truncation_preserves_score_keys(self):
        from core.ai_v2.agent.loop import (
            _OBSERVATION_MAX_CHARS,
            _observation_content,
        )

        observation = self._giant_observation()
        raw = json.dumps(observation, ensure_ascii=False)
        assert len(raw) > _OBSERVATION_MAX_CHARS

        result = _observation_content(observation)
        assert len(result) <= _OBSERVATION_MAX_CHARS
        parsed = json.loads(result)
        assert parsed["weighted_score"]["global_score"] == 65.56
        assert parsed["pct_by_parameter"]["height"]["pct_cumple"] == 83.33
        assert parsed["f199"] == 199

    def test_small_observation_passes_through_untouched(self):
        from core.ai_v2.agent.loop import _observation_content

        observation = {"weighted_score": {"global_score": 65.56}, "warnings": []}
        assert _observation_content(observation) == json.dumps(
            observation, ensure_ascii=False
        )

    def test_structured_truncate_tolerates_non_parseable_json(self):
        from core.ai_v2.agent.loop import _structured_truncate

        assert _structured_truncate("not json at all {", 16) is None
        assert _structured_truncate("[1, 2, 3]", 16) is None

    def test_flat_fallback_when_scalars_alone_exceed_budget(self):
        from core.ai_v2.agent.loop import (
            _OBSERVATION_MAX_CHARS,
            _observation_content,
        )

        result = _observation_content({"huge": "x" * 10000})
        assert len(result) <= _OBSERVATION_MAX_CHARS
        assert result.endswith("...[truncated]")


# ---------------------------------------------------------------------------
# T2.2a-1: export download metadata on tool_result events
# ---------------------------------------------------------------------------

EXPORT_FILTERS = '{"sector":["Norte"]}'
EXPORT_CALL_ARGS = '{"format": "excel"}'


def _export_payload(**overrides: Any) -> dict[str, Any]:
    """Handler payload whose JSON exceeds the 200-char summary cut."""
    payload: dict[str, Any] = {
        "ok": True,
        "format": "excel",
        "filler": "y" * 300,
        "query": {"filters": EXPORT_FILTERS},
    }
    payload.update(overrides)
    return payload


async def _run_export(payload: dict[str, Any]) -> tuple[list[Any], Any]:
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("export_report", EXPORT_CALL_ARGS, call_id="call_1")
                ]
            ),
            ChatTurn(text="Listo."),
        ]
    )
    events, provider, _, _ = await run_simple(
        provider, {"export_report": RecordingHandler(payload)}
    )
    return events, provider


def _single_result(events: list[Any]) -> ToolResultEvent:
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(results) == 1
    return results[0]


@pytest.mark.asyncio
async def test_export_download_meta_survives_the_summary_cut():
    events, _ = await _run_export(_export_payload())
    result = _single_result(events)
    assert result.ok is True
    assert "query" not in result.summary
    assert result.download is not None
    assert result.download.format == "excel"
    assert result.download.query == {"filters": EXPORT_FILTERS}


@pytest.mark.asyncio
async def test_export_download_meta_round_trips_through_ndjson():
    events, _ = await _run_export(_export_payload())
    result = _single_result(events)
    line = event_to_ndjson(result)
    assert json.loads(line)["download"] == {
        "format": "excel",
        "query": {"filters": EXPORT_FILTERS},
    }
    assert parse_event_line(line).download == result.download


@pytest.mark.asyncio
async def test_export_payload_with_ok_false_carries_no_download():
    events, _ = await _run_export(
        _export_payload(ok=False, error="invalid_filters")
    )
    assert _single_result(events).download is None


@pytest.mark.asyncio
async def test_other_tool_returning_format_and_query_carries_no_download():
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[tool_call("get_workflow_state", "", call_id="call_1")]
            ),
            ChatTurn(text="Listo."),
        ]
    )
    handler = RecordingHandler(
        {"ok": True, "format": "excel", "query": {"filters": EXPORT_FILTERS}}
    )
    events, _, _, _ = await run_simple(provider, {"get_workflow_state": handler})
    assert _single_result(events).download is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        {"filters": EXPORT_FILTERS, "endpoint": "/api/v1/evil"},
        {"filters": "x" * 4001},
        "filters=evil",
    ],
    ids=["extra_key", "value_over_4000", "not_a_mapping"],
)
async def test_invalid_query_drops_download_and_turn_continues(query: Any):
    from core.ai_v2.agent.loop import _compact_summary

    payload = _export_payload(query=query)
    events, provider = await _run_export(payload)
    result = _single_result(events)
    assert result.ok is True
    assert result.download is None
    assert result.summary == _compact_summary(payload)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
    assert any(isinstance(e, TextEvent) for e in events)
    tool_messages = [m for m in provider.requests[1] if m.get("role") == "tool"]
    assert json.loads(tool_messages[-1]["content"])["ok"] is True


def test_non_export_tool_result_serializes_without_download_key():
    event = ToolResultEvent(
        invocation_id="inv_abc",
        name="get_workflow_state",
        ok=True,
        summary="sin datos",
        duration_ms=1.5,
    )
    assert event_to_ndjson(event) == (
        '{"type":"tool_result","invocation_id":"inv_abc",'
        '"name":"get_workflow_state","ok":true,"summary":"sin datos",'
        '"duration_ms":1.5,"error":null}'
    )


class TestExportDownloadMeta:
    """Validation contract of the download metadata carried to the browser."""

    def test_accepts_the_three_known_query_keys(self):
        from core.ai_v2.agent.events import ExportDownloadMeta

        meta = ExportDownloadMeta(
            format="pdf",
            query={"filters": "{}", "project": "Mina", "author": "Ana"},
        )
        assert meta.query["project"] == "Mina"

    def test_query_defaults_to_empty_dict(self):
        from core.ai_v2.agent.events import ExportDownloadMeta

        assert ExportDownloadMeta(format="dxf").query == {}

    def test_value_length_bounds_are_1_to_4000(self):
        from core.ai_v2.agent.events import ExportDownloadMeta

        ExportDownloadMeta(format="excel", query={"filters": "x" * 4000})
        with pytest.raises(ValidationError):
            ExportDownloadMeta(format="excel", query={"filters": "x" * 4001})
        with pytest.raises(ValidationError):
            ExportDownloadMeta(format="excel", query={"filters": ""})

    def test_rejects_unknown_query_key(self):
        from core.ai_v2.agent.events import ExportDownloadMeta

        with pytest.raises(ValidationError):
            ExportDownloadMeta(format="excel", query={"endpoint": "/x"})

    def test_rejects_unknown_format_and_extra_fields(self):
        from core.ai_v2.agent.events import ExportDownloadMeta

        with pytest.raises(ValidationError):
            ExportDownloadMeta(format="csv")
        with pytest.raises(ValidationError):
            ExportDownloadMeta(format="excel", url="/x")


# ---------------------------------------------------------------------------
# C1 corrective (G3 review): add_section_click policy, payload-derived ok,
# confirmation args line, levels_truncated preservation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_section_click_without_results_runs_autonomously():
    handler = RecordingHandler({"ok": True, "n_added": 1})
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("add_section_click", '{"origin": [10, 20]}', call_id="c-add")
                ]
            ),
            ChatTurn(text="Listo."),
        ]
    )
    events, _, store, _ = await run_simple(
        provider, {"add_section_click": handler}, state=ToolState(n_sections=4)
    )
    assert len(handler.calls) == 1
    assert store.created == []
    assert events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_add_section_click_with_results_pauses_for_confirmation():
    handler = RecordingHandler({"ok": True, "n_added": 1})
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("add_section_click", '{"origin": [10, 20]}', call_id="c-add")
                ]
            ),
        ]
    )
    events, _, store, _ = await run_simple(
        provider,
        {"add_section_click": handler},
        state=ToolState(n_sections=4, n_results=12),
    )
    assert handler.calls == []
    assert len(store.created) == 1
    assert store.created[0].tool_name == "add_section_click"
    assert events[-1].finish_reason == "confirmation_required"
    confirm = next(e for e in events if isinstance(e, ConfirmationRequiredEvent))
    assert confirm.args_summary == (
        "Añade una sección e invalida 12 resultados del análisis actual. "
        "Parámetros: origin=[10.0, 20.0]; length=200.0; az_mode=auto"
    )


@pytest.mark.asyncio
async def test_run_reconciliation_confirmation_shows_the_override():
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("run_reconciliation", '{"face_threshold": 60}', call_id="c-rec")
                ]
            ),
        ]
    )
    events, _, store, _ = await run_simple(
        provider,
        {"run_reconciliation": RecordingHandler()},
        state=ToolState(n_results=5),
    )
    confirm = next(e for e in events if isinstance(e, ConfirmationRequiredEvent))
    assert confirm.args_summary == (
        "Sobrescribe 5 resultados existentes (~42 s) Parámetros: face_threshold=60.0"
    )
    assert store.created[0].args_summary == confirm.args_summary


@pytest.mark.asyncio
async def test_run_reconciliation_without_overrides_has_no_args_line():
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[tool_call("run_reconciliation", "{}", call_id="c-rec")]
            ),
        ]
    )
    events, _, store, _ = await run_simple(
        provider,
        {"run_reconciliation": RecordingHandler()},
        state=ToolState(n_results=5),
    )
    confirm = next(e for e in events if isinstance(e, ConfirmationRequiredEvent))
    assert confirm.args_summary == "Sobrescribe 5 resultados existentes (~42 s)"
    assert "Parámetros:" not in store.created[0].args_summary


class TestConfirmationArgsFragment:
    def test_skips_none_empty_string_and_empty_list(self):
        from core.ai_v2.agent.loop import _args_fragment

        assert _args_fragment({"a": None, "b": [], "c": "", "d": 3}) == " Parámetros: d=3"

    def test_no_remaining_args_yield_empty_fragment(self):
        from core.ai_v2.agent.loop import _args_fragment

        assert _args_fragment({"a": None, "b": []}) == ""

    def test_strings_are_unquoted_and_non_scalars_are_json_without_ascii_escapes(self):
        from core.ai_v2.agent.loop import _args_fragment

        assert _args_fragment({"section_id": "4", "sector": ["Ñandú"]}) == (
            ' Parámetros: section_id=4; sector=["Ñandú"]'
        )

    def test_each_value_is_cut_to_sixty_chars(self):
        from core.ai_v2.agent.loop import _args_fragment

        fragment = _args_fragment({"sections": ["x" * 200]})
        value = fragment.removeprefix(" Parámetros: sections=")
        assert len(value) == 60
        assert value.endswith("…")

    def test_whole_line_is_cut_to_three_hundred_chars(self):
        from core.ai_v2.agent.loop import _args_fragment

        fragment = _args_fragment({f"k{i:02d}": "y" * 55 for i in range(20)})
        assert len(fragment) == 300
        assert fragment.endswith("…")

    def test_short_line_is_kept_whole(self):
        from core.ai_v2.agent.loop import _args_fragment

        assert _args_fragment({"face_threshold": 60.0}) == (
            " Parámetros: face_threshold=60.0"
        )


@pytest.mark.asyncio
async def test_handler_payload_ok_false_is_reported_as_failed_result():
    payload = {"ok": False, "error": "section_id_out_of_range"}
    handler = RecordingHandler(payload)
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("get_profile", '{"section_id": "9"}', call_id="c-prof")
                ]
            ),
            ChatTurn(text="No existe esa sección."),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"get_profile": handler})
    result = _single_result(events)
    assert handler.calls != []
    assert result.ok is False
    assert result.error == "section_id_out_of_range"
    assert result.download is None
    tool_messages = [m for m in provider.requests[1] if m["role"] == "tool"]
    assert json.loads(tool_messages[0]["content"]) == payload
    assert events[-1].finish_reason == "stop"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", ["invalid_filters", "process_running", "no_rows_for_filters"]
)
async def test_rejected_export_is_not_reported_ok(error):
    events, _ = await _run_export(_export_payload(ok=False, error=error))
    result = _single_result(events)
    assert result.ok is False
    assert result.error == error
    assert result.download is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        pytest.param({"ok": False}, "tool_error", id="missing-error"),
        pytest.param({"ok": False, "error": "x" * 65}, "tool_error", id="error-65-chars"),
        pytest.param({"ok": False, "error": {"code": "nested"}}, "tool_error", id="non-str"),
        pytest.param({"ok": False, "error": "y" * 64}, "y" * 64, id="error-64-chars"),
    ],
)
async def test_rejected_payload_error_code_is_bounded(payload, expected_error):
    handler = RecordingHandler(payload)
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("get_profile", '{"section_id": "9"}', call_id="c-prof")
                ]
            ),
            ChatTurn(text="Hubo un problema."),
        ]
    )
    events, provider, _, _ = await run_simple(provider, {"get_profile": handler})
    result = _single_result(events)
    assert result.ok is False
    assert result.error == expected_error
    tool_messages = [m for m in provider.requests[1] if m["role"] == "tool"]
    assert json.loads(tool_messages[0]["content"]) == payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"ok": True, "section_id": "0"}, id="explicit-ok"),
        pytest.param({"section_id": "0"}, id="no-ok-key"),
    ],
)
async def test_ok_payload_is_reported_ok_without_error(payload):
    handler = RecordingHandler(payload)
    provider = ScriptedChatProvider(
        [
            ChatTurn(
                tool_calls=[
                    tool_call("get_profile", '{"section_id": "0"}', call_id="c-prof")
                ]
            ),
            ChatTurn(text="Listo."),
        ]
    )
    events, _, _, _ = await run_simple(provider, {"get_profile": handler})
    result = _single_result(events)
    assert result.ok is True
    assert result.error is None


class TestLevelsTruncatedPreservation:
    def test_levels_truncated_survives_structural_truncation(self):
        from core.ai_v2.agent.loop import _observation_content

        observation: dict[str, Any] = {f"f{i:03d}": i for i in range(200)}
        observation["levels_truncated"] = True
        observation["nominal_levels"] = {
            "Norte": [str(2900 + index) for index in range(900)]
        }
        result = _observation_content(observation)
        assert len(result) <= 4000
        assert json.loads(result)["levels_truncated"] is True

    def test_levels_truncated_survives_conversation_compaction(self):
        from api.ai_agent_conversations import compact_messages

        observation = {
            "ok": True,
            "levels_truncated": True,
            "n_total_rows": 3,
            "filler": "z" * 50,
        }
        messages = [
            {"role": "system", "content": "Eres el agente."},
            {"role": "user", "content": "consulta"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "query_results", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "c1",
                "content": json.dumps(observation, ensure_ascii=False),
            },
            {"role": "user", "content": "otra"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "última"},
        ]
        compacted = compact_messages(messages)
        parsed = json.loads(compacted[3]["content"])
        assert parsed == {"ok": True, "levels_truncated": True, "n_total_rows": 3}



def test_horizontal_deviation_survives_structured_truncation():
    from core.ai_v2.agent.loop import _structured_truncate

    hd = {"available": True, "convention": "negativo = faltante", "summary": {"measured": 10, "total": 12}, "benches_total": 10, "samples_total": 30, "rows_shown": 30, "truncated": False, "columns": ["bench", "h_m", "dH_m", "meaning", "severity"], "columns_note": "motivo", "rows": [[i, 3, -2, "faltante", "leve"] for i in range(10) for _ in range(3)]}
    result = _structured_truncate(json.dumps({"horizontal_deviation": hd}), 4)["horizontal_deviation"]
    assert result["convention"] == hd["convention"]
    assert result["summary"] == hd["summary"]
    assert result["columns"] == hd["columns"] and result["columns_note"] == hd["columns_note"]
    assert result["rows_shown"] == len(result["rows"]) and result["truncated"] is True
    assert len(result["rows"]) <= 4
    assert len(result["rows"]) % 3 == 0
