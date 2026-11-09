"""Tests for the T2 provider extension: stream_chat + capability flag.

The OpenAI SDK client is simulated (monkeypatched ``create`` returning
a scripted async stream of REAL SDK chunk objects) — no network, no
real providers, no HTTP server.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import pytest
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from openai.types.completion_usage import CompletionUsage

from core.ai_v2.agent.turn import ChatTurn, ToolCallRequest
from core.ai_v2.errors import ProviderUnavailable
from core.ai_v2.models import AIResponseChunk
from core.ai_v2.providers import PROVIDER_PRESETS, ProviderRegistry, ProviderType
from core.ai_v2.providers.base import BaseProvider
from core.ai_v2.providers.openai_compat import (
    OpenAICompatibleProvider,
    _validate_call_arguments,
)


# ---------------------------------------------------------------------------
# Simulated OpenAI SDK (no network)
# ---------------------------------------------------------------------------


def _tool_frag(
    index: int,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> ChoiceDeltaToolCall:
    function = None
    if name is not None or arguments is not None:
        function = ChoiceDeltaToolCallFunction(
            name=name, arguments=arguments
        )
    return ChoiceDeltaToolCall(
        index=index,
        id=call_id,
        type="function" if call_id else None,
        function=function,
    )


def _chunk(
    content: str | None = None,
    tool_frags: list[ChoiceDeltaToolCall] | None = None,
    finish_reason: str | None = None,
    usage: CompletionUsage | None = None,
) -> ChatCompletionChunk:
    delta = ChoiceDelta(content=content, tool_calls=tool_frags)
    return ChatCompletionChunk(
        id="chatcmpl-test",
        created=0,
        model="test-model",
        object="chat.completion.chunk",
        choices=[
            Choice(index=0, delta=delta, finish_reason=finish_reason)  # type: ignore[arg-type]
        ],
        usage=usage,
    )


def _usage_chunk(prompt: int, completion: int, total: int) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id="chatcmpl-test",
        created=0,
        model="test-model",
        object="chat.completion.chunk",
        choices=[],
        usage=CompletionUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
        ),
    )


class SimulatedClient:
    """Stands in for ``AsyncOpenAI``: scripted chunk stream + capture."""

    def __init__(self, chunks: list[ChatCompletionChunk]) -> None:
        self.chunks = chunks
        self.captured_kwargs: dict[str, Any] = {}

    async def fake_create(self, **kwargs: Any) -> AsyncIterator[ChatCompletionChunk]:
        self.captured_kwargs = kwargs

        async def _stream() -> AsyncIterator[ChatCompletionChunk]:
            for chunk in self.chunks:
                yield chunk

        return _stream()


def make_provider(
    chunks: list[ChatCompletionChunk], *, supports_tool_calls: bool = True
) -> tuple[OpenAICompatibleProvider, SimulatedClient]:
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:9/v1",
        api_key="test",
        name="simulated",
        supports_tool_calls=supports_tool_calls,
    )
    client = SimulatedClient(chunks)
    provider._client.chat.completions.create = client.fake_create  # type: ignore[method-assign]
    return provider, client


TOOLS = [
    {
        "type": "function",
        "function": {"name": "get_mesh_info", "parameters": {}},
    }
]


# ---------------------------------------------------------------------------
# Capability flag defaults
# ---------------------------------------------------------------------------


class _BareProvider(BaseProvider):
    async def stream(self, messages, *, model, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("not used here")
        yield  # noqa: unreachable - makes this an async generator

    async def list_models(self) -> list[str]:
        return []

    async def health_check(self) -> bool:
        return False


def test_base_provider_capability_defaults_to_false():
    assert _BareProvider().supports_tool_calls is False


@pytest.mark.asyncio
async def test_base_provider_stream_chat_signals_unsupported():
    with pytest.raises(ProviderUnavailable):
        await _BareProvider().stream_chat([], model="m", tools=[])


def test_openai_compat_capability_default_false_and_injectable():
    default = OpenAICompatibleProvider(base_url="http://localhost:9/v1")
    assert default.supports_tool_calls is False
    enabled = OpenAICompatibleProvider(
        base_url="http://localhost:9/v1", supports_tool_calls=True
    )
    assert enabled.supports_tool_calls is True


def test_registry_capability_openai_format_defaults():
    expected = {
        ProviderType.OLLAMA: True,
        ProviderType.LMSTUDIO: True,
        ProviderType.OPENAI: True,
        ProviderType.OPENROUTER: True,
        ProviderType.MINIMAX: False,
        ProviderType.GLM: False,
        ProviderType.GROK: True,
    }
    for ptype, capability in expected.items():
        assert ProviderRegistry.supports_tool_calls(ptype) is capability, ptype


def test_registry_get_carries_capability_flag():
    assert (
        ProviderRegistry.get(ProviderType.OPENAI, api_key="k").supports_tool_calls
        is True
    )
    assert (
        ProviderRegistry.get(ProviderType.OLLAMA, api_key="k").supports_tool_calls
        is True
    )
    assert (
        ProviderRegistry.get(ProviderType.GLM, api_key="k").supports_tool_calls
        is False
    )


def test_registry_presets_unchanged_by_capability_map():
    preset = PROVIDER_PRESETS[ProviderType.OLLAMA]
    assert preset["default_model"] == "llama3.1:8b"
    assert preset["base_url"] == "http://localhost:11434/v1"
    for values in PROVIDER_PRESETS.values():
        assert all(isinstance(v, str) for v in values.values())


# ---------------------------------------------------------------------------
# stream_chat accumulation over simulated chunks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fragmented_tool_call_arguments_are_assembled():
    provider, _ = make_provider(
        [
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="call_1", name="get_mesh_info",
                               arguments='{"mesh')
                ]
            ),
            _chunk(tool_frags=[_tool_frag(0, arguments='_id": "mesh-42"}')]),
            _chunk(tool_frags=[_tool_frag(0, arguments="")],
                   finish_reason="tool_calls"),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    assert turn.text == ""
    assert turn.finish_reason == "tool_calls"
    assert len(turn.tool_calls) == 1
    call = turn.tool_calls[0]
    assert call.call_id == "call_1"
    assert call.name == "get_mesh_info"
    assert call.arguments == '{"mesh_id": "mesh-42"}'
    assert call.arguments_valid is True
    assert call.arguments_error is None
    assert call.parse_arguments() == {"mesh_id": "mesh-42"}


@pytest.mark.asyncio
async def test_multiple_tool_calls_are_all_accumulated():
    provider, _ = make_provider(
        [
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="call_a", name="get_mesh_info",
                               arguments='{"mesh_id": "'),
                    _tool_frag(1, call_id="call_b", name="list_meshes",
                               arguments=""),
                ]
            ),
            _chunk(
                tool_frags=[
                    _tool_frag(1, arguments="{}"),
                    _tool_frag(0, arguments='a-1"}'),
                ]
            ),
            _chunk(finish_reason="tool_calls"),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    assert [c.call_id for c in turn.tool_calls] == ["call_a", "call_b"]
    assert turn.tool_calls[0].arguments == '{"mesh_id": "a-1"}'
    assert turn.tool_calls[0].arguments_valid is True
    assert turn.tool_calls[0].parse_arguments() == {"mesh_id": "a-1"}
    assert turn.tool_calls[1].name == "list_meshes"
    assert turn.tool_calls[1].arguments == "{}"
    assert turn.tool_calls[1].arguments_valid is True


@pytest.mark.asyncio
async def test_nameless_continuation_fragments_do_not_crash_stream_chat():
    provider, _ = make_provider(
        [
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="call_1", name="get_mesh_info",
                               arguments='{"mesh')
                ]
            ),
            _chunk(tool_frags=[_tool_frag(0, arguments='_id": "m-1"}')]),
            _chunk(finish_reason="tool_calls"),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    assert turn.tool_calls[0].name == "get_mesh_info"
    assert turn.tool_calls[0].parse_arguments() == {"mesh_id": "m-1"}

    degraded, _ = make_provider(
        [
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="call_x", arguments="{}"),
                ],
                finish_reason="tool_calls",
            )
        ]
    )
    turn_x = await degraded.stream_chat([], model="test-model", tools=TOOLS)
    assert turn_x.tool_calls[0].name == ""
    assert turn_x.tool_calls[0].call_id == "call_x"
    assert turn_x.tool_calls[0].arguments_valid is True


@pytest.mark.asyncio
async def test_text_and_usage_are_accumulated():
    provider, _ = make_provider(
        [
            _chunk(content="Generando "),
            _chunk(content="secciones…"),
            _chunk(finish_reason="stop"),
            _usage_chunk(prompt=12, completion=34, total=46),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    assert turn.text == "Generando secciones…"
    assert turn.tool_calls == []
    assert turn.finish_reason == "stop"
    assert turn.usage is not None
    assert turn.usage.prompt_tokens == 12
    assert turn.usage.completion_tokens == 34
    assert turn.usage.total_tokens == 46
    assert turn.usage.is_synthetic is False


@pytest.mark.asyncio
async def test_truncated_json_arguments_surface_raw_and_invalid_flag():
    raw = '{"mesh_id": "mesh-4'
    provider, _ = make_provider(
        [
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="call_1", name="get_mesh_info",
                               arguments=raw)
                ],
                finish_reason="length",
            ),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    call = turn.tool_calls[0]
    assert call.arguments == raw
    assert call.arguments_valid is False
    assert call.arguments_error == "invalid_json"
    with pytest.raises(ValueError):
        call.parse_arguments()


@pytest.mark.asyncio
async def test_non_object_json_arguments_flagged():
    provider, _ = make_provider(
        [
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="call_1", name="get_mesh_info",
                               arguments='"just a string"')
                ]
            ),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    call = turn.tool_calls[0]
    assert call.arguments_valid is False
    assert call.arguments_error == "not_an_object"


@pytest.mark.asyncio
async def test_empty_arguments_are_valid_empty_object():
    provider, _ = make_provider(
        [
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="call_1", name="list_meshes")
                ],
                finish_reason="tool_calls",
            ),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    call = turn.tool_calls[0]
    assert call.arguments == ""
    assert call.arguments_valid is True
    assert call.parse_arguments() == {}


@pytest.mark.asyncio
async def test_stream_chat_request_carries_tools_and_auto_choice():
    provider, client = make_provider([_chunk(finish_reason="stop")])
    await provider.stream_chat(
        [{"role": "user", "content": "hola"}], model="test-model", tools=TOOLS
    )
    assert client.captured_kwargs["tools"] == TOOLS
    assert client.captured_kwargs["tool_choice"] == "auto"
    assert client.captured_kwargs["stream"] is True
    assert client.captured_kwargs["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_stream_report_path_sends_no_tools():
    provider, client = make_provider([_chunk(content="hola")])
    chunks = [chunk async for chunk in provider.stream(
        [{"role": "user", "content": "hola"}], model="test-model"
    )]
    assert "tools" not in client.captured_kwargs
    assert "tool_choice" not in client.captured_kwargs
    assert all(isinstance(chunk, AIResponseChunk) for chunk in chunks)
    assert "".join(chunk.content for chunk in chunks) == "hola"


@pytest.mark.asyncio
async def test_stream_chat_returns_chat_turn_not_response_chunk():
    provider, _ = make_provider(
        [
            _chunk(content="texto"),
            _chunk(
                tool_frags=[
                    _tool_frag(0, call_id="c1", name="list_meshes",
                               arguments="{}")
                ],
                finish_reason="tool_calls",
            ),
        ]
    )
    turn = await provider.stream_chat([], model="test-model", tools=TOOLS)
    assert isinstance(turn, ChatTurn)
    assert not isinstance(turn, AIResponseChunk)
    assert set(ChatTurn.model_fields) == {
        "text",
        "tool_calls",
        "finish_reason",
        "usage",
    }


def test_validate_call_arguments_reason_codes():
    assert _validate_call_arguments("") == (True, None)
    assert _validate_call_arguments(None) == (True, None)
    assert _validate_call_arguments("  {}  ") == (True, None)
    assert _validate_call_arguments('{"a": 1}') == (True, None)
    valid, error = _validate_call_arguments('{"a": ')
    assert (valid, error) == (False, "invalid_json")
    valid, error = _validate_call_arguments("[1, 2]")
    assert (valid, error) == (False, "not_an_object")


def test_chat_turn_raw_arguments_never_reserialized():
    raw = '{"mesh_id": "m-1"}'
    call = ToolCallRequest(
        call_id="c1",
        name="get_mesh_info",
        arguments=raw,
        arguments_valid=True,
    )
    assert json.loads(call.arguments) == {"mesh_id": "m-1"}
    assert call.arguments == raw
