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
