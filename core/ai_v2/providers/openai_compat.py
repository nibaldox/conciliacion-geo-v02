"""OpenAI-compatible provider. Works with Ollama, LM Studio, OpenAI,
MiniMax, GLM, Grok — anything that exposes an OpenAI-style /v1 endpoint."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import httpx

from openai import APIConnectionError, APIError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from core.ai_v2.providers.base import BaseProvider

if TYPE_CHECKING:
    from openai.types.chat import (
        ChatCompletionToolChoiceOptionParam,
        ChatCompletionToolUnionParam,
    )

    from core.ai_v2.agent.turn import ChatTurn


def _validate_call_arguments(raw_arguments: str | None) -> tuple[bool, str | None]:
    """Validate raw streamed tool-call arguments without mutating them.

    Empty arguments are valid (providers omit the field for
    parameterless tools). Truncated or non-object JSON is reported as
    invalid with a stable reason code, while the RAW string is kept
    untouched so it can be replayed verbatim to the provider.
    """
    stripped = (raw_arguments or "").strip()
    if not stripped:
        return True, None
    try:
        parsed = json.loads(stripped)
    except ValueError:
        return False, "invalid_json"
    if not isinstance(parsed, dict):
        return False, "not_an_object"
    return True, None


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str = "not-needed",
        name: str = "unknown",
        timeout_s: float = 120.0,
        supports_tool_calls: bool = False,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout_s
        )
        self._name = name
        self._supports_tool_calls = bool(supports_tool_calls)

    @property
    def name(self) -> str:
        return self._name

    @property
    def supports_tool_calls(self) -> bool:
        """Tool-calling capability flag, injected per registry preset."""
        return self._supports_tool_calls

    def stream(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 120.0,
    ):
        return self._stream_impl(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )

    async def _stream_impl(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
    ):
        from core.ai_v2.models import AIResponseChunk, AIUsage

        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout_s,
        )
        chunk_index = 0
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield AIResponseChunk(
                    content=chunk.choices[0].delta.content,
                    chunk_index=chunk_index,
                )
                chunk_index += 1
            elif chunk.usage is not None:
                yield AIResponseChunk(
                    content="",
                    chunk_index=chunk_index,
                    usage=AIUsage(
                        prompt_tokens=chunk.usage.prompt_tokens or 0,
                        completion_tokens=chunk.usage.completion_tokens or 0,
                        total_tokens=chunk.usage.total_tokens or 0,
                        is_synthetic=False,
                    ),
                )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        tools: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 120.0,
        tool_choice: str = "auto",
        on_text_delta: Callable[[str], None] | None = None,
    ) -> "ChatTurn":
        """Complete one chat turn with tools, accumulating the stream.

        Tool-call deltas are accumulated per ``index``: id and name come
        from the first fragment that carries them (OpenAI semantics),
        argument fragments are concatenated in arrival order, so a call
        fragmented across many chunks is assembled exactly once. ALL
        tool calls of the response are returned, in index order. The
        raw arguments string is preserved verbatim together with a
        validity flag — truncated or invalid JSON is surfaced, never
        silently re-serialized (imported lazily to avoid an import
        cycle with ``core.ai_v2.models``).

        ``on_text_delta`` (see
        :meth:`core.ai_v2.providers.base.BaseProvider.stream_chat`) is
        invoked immediately with every non-empty text fragment as the
        stream produces it; the fragment is still accumulated into the
        returned ``ChatTurn``. A raising consumer is swallowed so a
        failing callback can never break the turn.
        """
        from core.ai_v2.agent.turn import ChatTurn, ToolCallRequest
        from core.ai_v2.models import AIUsage

        response = await self._client.chat.completions.create(
            model=model,
            messages=cast("list[ChatCompletionMessageParam]", messages),
            stream=True,
            stream_options={"include_usage": True},
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout_s,
            tools=cast("list[ChatCompletionToolUnionParam]", tools),
            tool_choice=cast("ChatCompletionToolChoiceOptionParam", tool_choice),
        )
        text_parts: list[str] = []
        calls_by_index: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage: AIUsage | None = None
        async for chunk in response:
            if chunk.choices:
                choice = chunk.choices[0]
                delta = choice.delta
                if delta is not None:
                    if delta.content:
                        text_parts.append(delta.content)
                        if on_text_delta is not None:
                            try:
                                on_text_delta(delta.content)
                            except Exception:
                                pass
                    for fragment in delta.tool_calls or []:
                        index = int(fragment.index)
                        slot = calls_by_index.setdefault(
                            index, {"id": "", "name": "", "arguments": ""}
                        )
                        if fragment.id:
                            slot["id"] = fragment.id
                        if fragment.function is not None:
                            if fragment.function.name and not slot["name"]:
                                slot["name"] = fragment.function.name
                            if fragment.function.arguments:
                                slot["arguments"] += fragment.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
            if chunk.usage is not None:
                usage = AIUsage(
                    prompt_tokens=chunk.usage.prompt_tokens or 0,
                    completion_tokens=chunk.usage.completion_tokens or 0,
                    total_tokens=chunk.usage.total_tokens or 0,
                    is_synthetic=False,
                )
        tool_calls: list[ToolCallRequest] = []
        for index in sorted(calls_by_index):
            slot = calls_by_index[index]
            valid, error = _validate_call_arguments(slot["arguments"])
            tool_calls.append(
                ToolCallRequest(
                    call_id=slot["id"] or f"call_{index}",
                    name=slot["name"],
                    arguments=slot["arguments"],
                    arguments_valid=valid,
                    arguments_error=error,
                )
            )
        return ChatTurn(
            text="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    async def list_models(self) -> list[str]:
        try:
            models = await self._client.models.list()
            return [m.id for m in models.data]
        except (APIConnectionError, APIError, httpx.HTTPError, OSError, ValueError):
            return []

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except (APIConnectionError, APIError, httpx.HTTPError, OSError, ValueError):
            return False