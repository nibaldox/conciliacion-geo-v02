"""Bounded tool-calling agent loop (T2).

Drives a ``stream_chat``-capable provider over the frozen tool catalog
and emits the T0 typed NDJSON events. Everything is dependency-
injected — provider, tool executor mapping, pending-confirmation
store and state provider — so this module stays pure ``core``: it
NEVER imports from ``api/``. In production the executor is
``api.ai_agent_handlers.READ_HANDLERS`` (T1) and the pending store is
the T3 ``PendingRunStore`` implementation; tests inject fakes.

Per-tool-call flow (plan sections 4.1/5.2):

1. Resolve the tool in the catalog. Unknown tools are fail-closed:
   never executed (not even after an approval), answered with a safe
   ``herramienta no disponible`` observation.
2. Validate arguments with the spec's Pydantic model. Invalid args
   never reach the executor; a safe observation goes back to the model.
3. Fetch the REAL session ``ToolState`` and evaluate the pure policy.
4. Confirmation required: emit ``tool_call`` + ``confirmation_required``,
   record the full resume state in the injected ``PendingRunStore`` and
   STOP the stream (finished with ``confirmation_required``).
5. Otherwise execute the injected handler (``session_id`` is injected,
   never taken from model args) and answer with a small JSON
   observation plus a ``role: tool`` message carrying the provider's
   ``tool_call_id``; the original assistant message with its raw
   ``tool_calls`` is replayed verbatim on the next iteration.
6. Handler failures become sanitized observations; the loop continues.
7. Stop conditions: final text (``stop``), iteration budget exhausted
   (``error``), provider timeout, or provider failure — surfaced as an
   explicit error event, NEVER faked text.

Every tool call of a turn is answered before the next iteration, so a
multi-tool-call turn always produces one ``role: tool`` message per
``tool_call_id``.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from core.ai_v2.agent.catalog import get_tool, openai_tools
from core.ai_v2.agent.confirmations import (
    PENDING_TTL_S,
    PendingRun,
    PendingRunStore,
    canonical_args_sha256,
    new_invocation_id,
)
from core.ai_v2.agent.events import (
    AgentEvent,
    ConfirmationRequiredEvent,
    DoneEvent,
    ErrorEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from core.ai_v2.agent.models import ToolSpec, ToolState
from core.ai_v2.agent.policy import decide, decide_unknown
from core.ai_v2.agent.turn import ToolCallRequest
from core.ai_v2.models import AIUsage
from core.ai_v2.providers.base import BaseProvider

ToolHandler = Callable[[str, BaseModel], Awaitable[dict[str, Any]]]
"""Injected handler signature: validated args model in, small dict out."""

ToolExecutor = Mapping[str, ToolHandler]
"""Tool name -> handler mapping (production: ``READ_HANDLERS``)."""

StateProvider = Callable[[str], Awaitable[ToolState]]
"""Async session_id -> real ``ToolState`` snapshot."""

DEFAULT_MAX_ITERATIONS = 8
DEFAULT_TIMEOUT_S = 120.0

_OBSERVATION_MAX_CHARS = 4000
_SUMMARY_MAX_CHARS = 200

MSG_TOOL_UNAVAILABLE = (
    "Herramienta no disponible: no está en el catálogo del agente."
)
MSG_INVALID_ARGS = "Argumentos inválidos para la herramienta."
MSG_TOOL_FAILED = "La herramienta falló durante su ejecución; inténtalo de nuevo."
MSG_TOOL_TIMEOUT = "La herramienta excedió su tiempo máximo de ejecución."
MSG_PROVIDER_UNSUPPORTED = (
    "El proveedor seleccionado no soporta llamadas a herramientas "
    "(function calling). Selecciona otro proveedor para usar el chat."
)
MSG_PROVIDER_ERROR = (
    "El proveedor de IA no está disponible en este momento; inténtalo de nuevo."
)
MSG_PROVIDER_TIMEOUT = (
    "El proveedor de IA excedió el tiempo máximo de respuesta."
)
MSG_MAX_ITERATIONS = (
    "Se alcanzó el límite de iteraciones del agente sin una respuesta final."
)
MSG_PENDING_ERROR = (
    "No se pudo registrar la confirmación pendiente; inténtalo de nuevo."
)


def _dumps_safe(payload: Any) -> str:
    """JSON-encode any handler output without ever raising."""
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}"


def _compact_summary(observation: dict[str, Any]) -> str:
    """Small bounded text summary of an observation for the UI event."""
    text = _dumps_safe(observation)
    if len(text) > _SUMMARY_MAX_CHARS:
        text = text[:_SUMMARY_MAX_CHARS] + "…"
    return text


def _observation_content(observation: dict[str, Any]) -> str:
    """Bounded JSON string for the role:tool message content."""
    text = _dumps_safe(observation)
    if len(text) > _OBSERVATION_MAX_CHARS:
        text = text[:_OBSERVATION_MAX_CHARS] + "...[truncated]"
    return text


def _assistant_tool_calls_message(
    text: str, calls: list[ToolCallRequest]
) -> dict[str, Any]:
    """Replayable assistant message carrying the RAW tool_calls."""
    return {
        "role": "assistant",
        "content": text if text else None,
        "tool_calls": [
            {
                "id": call.call_id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ],
    }


def _tool_message(call_id: str, observation: dict[str, Any]) -> dict[str, Any]:
    """role:tool answer bound to the provider's tool_call id."""
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": _observation_content(observation),
    }


def _accumulate_usage(
    total: AIUsage | None, incoming: AIUsage | None
) -> AIUsage | None:
    """Sum per-turn provider usage across iterations."""
    if incoming is None:
        return total
    if total is None:
        total = AIUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    total.prompt_tokens += incoming.prompt_tokens
    total.completion_tokens += incoming.completion_tokens
    total.total_tokens += incoming.total_tokens
    return total


def _with_duration(usage: AIUsage | None, duration_ms: float) -> AIUsage | None:
    if usage is None:
        return None
    usage.duration_ms = duration_ms
    return usage


def _provider_name(provider: BaseProvider) -> str:
    return str(getattr(provider, "name", "unknown") or "unknown")


async def run_agent_turn(
    *,
    session_id: str,
    messages: list[dict[str, Any]],
    provider: BaseProvider,
    model: str,
    executor: ToolExecutor,
    pending_store: PendingRunStore,
    state_provider: StateProvider,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> AsyncIterator[AgentEvent]:
    """Run ONE bounded agent turn, yielding typed events.

    Args:
        session_id: Active session id from the middleware; injected
            into handlers, never read from model arguments.
        messages: Conversation so far in OpenAI chat format; the loop
            appends assistant/tool messages to its own copy.
        provider: ``stream_chat``-capable provider.
        model: Provider model identifier.
        executor: Tool name -> async handler mapping (validated args).
        pending_store: Injected pending-confirmation store (T3 impl).
        state_provider: Async ``session_id`` -> real ``ToolState``.
        max_iterations: Upper bound of provider iterations (default 8).
        timeout_s: Per-iteration provider budget (separate from the
            per-tool ``ToolSpec.timeout_s`` budget).
        tools: OpenAI tools payload; defaults to the whole catalog.
        temperature: Sampling temperature for provider calls.
        max_tokens: Provider max_tokens for provider calls.

    Yields:
        T0 agent events; the stream ALWAYS ends with a ``done`` event.
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")

    if not provider.supports_tool_calls:
        yield ErrorEvent(content=MSG_PROVIDER_UNSUPPORTED)
        yield DoneEvent(finish_reason="error")
        return

    resolved_tools = tools if tools is not None else openai_tools()
    conversation = list(messages)
    usage_total: AIUsage | None = None
    start_ns = time.perf_counter_ns()

    for _iteration in range(max_iterations):
        try:
            turn = await asyncio.wait_for(
                provider.stream_chat(
                    conversation,
                    model=model,
                    tools=resolved_tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_s=timeout_s,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            yield ErrorEvent(content=MSG_PROVIDER_TIMEOUT)
            yield DoneEvent(
                finish_reason="error",
                usage=_with_duration(usage_total, _elapsed_ms(start_ns)),
            )
            return
        except Exception:
            yield ErrorEvent(content=MSG_PROVIDER_ERROR)
            yield DoneEvent(
                finish_reason="error",
                usage=_with_duration(usage_total, _elapsed_ms(start_ns)),
            )
            return

        usage_total = _accumulate_usage(usage_total, turn.usage)

        if not turn.tool_calls:
            yield TextEvent(content=turn.text)
            yield DoneEvent(
                finish_reason="stop",
                usage=_with_duration(usage_total, _elapsed_ms(start_ns)),
            )
            return

        conversation.append(
            _assistant_tool_calls_message(turn.text, turn.tool_calls)
        )

        for call in turn.tool_calls:
            events, stop_reason = await _handle_tool_call(
                call=call,
                session_id=session_id,
                conversation=conversation,
                executor=executor,
                pending_store=pending_store,
                state_provider=state_provider,
                model=model,
                provider=provider,
            )
            for event in events:
                yield event
            if stop_reason is not None:
                yield DoneEvent(
                    finish_reason=stop_reason,
                    usage=_with_duration(usage_total, _elapsed_ms(start_ns)),
                )
                return

    yield ErrorEvent(content=MSG_MAX_ITERATIONS)
    yield DoneEvent(
        finish_reason="error",
        usage=_with_duration(usage_total, _elapsed_ms(start_ns)),
    )


def _elapsed_ms(start_ns: int) -> float:
    return (time.perf_counter_ns() - start_ns) / 1_000_000


async def _handle_tool_call(
    *,
    call: ToolCallRequest,
    session_id: str,
    conversation: list[dict[str, Any]],
    executor: ToolExecutor,
    pending_store: PendingRunStore,
    state_provider: StateProvider,
    model: str,
    provider: BaseProvider,
) -> tuple[list[AgentEvent], Literal["confirmation_required", "error"] | None]:
    """Process one tool call and append its role:tool answer.

    Returns the events for this call and, when the stream must STOP,
    the ``done`` finish reason (``confirmation_required`` after a
    recorded pending run, ``error`` when recording failed); None to
    continue the loop.
    """
    invocation_id = new_invocation_id()
    spec = get_tool(call.name)
    handler = executor.get(call.name) if spec is not None else None
    if spec is None or handler is None:
        reason = "unknown_tool" if spec is None else "handler_unavailable"
        events: list[AgentEvent] = [
            ToolCallEvent(
                invocation_id=invocation_id,
                name=call.name,
                args={},
                requires_confirmation=False,
            ),
            ToolResultEvent(
                invocation_id=invocation_id,
                name=call.name,
                ok=False,
                summary=MSG_TOOL_UNAVAILABLE,
                error=reason,
                duration_ms=0.0,
            ),
        ]
        conversation.append(
            _tool_message(
                call.call_id,
                {
                    "ok": False,
                    "error": reason,
                    "message": MSG_TOOL_UNAVAILABLE,
                },
            )
        )
        return events, None

    validated, raw_args, arg_error = _validated_args(spec, call)
    if arg_error is not None or validated is None:
        events = [
            ToolCallEvent(
                invocation_id=invocation_id,
                name=call.name,
                args=raw_args if raw_args is not None else {},
                requires_confirmation=False,
            ),
            ToolResultEvent(
                invocation_id=invocation_id,
                name=call.name,
                ok=False,
                summary=MSG_INVALID_ARGS,
                error=arg_error,
                duration_ms=0.0,
            ),
        ]
        conversation.append(
            _tool_message(
                call.call_id,
                {
                    "ok": False,
                    "error": "invalid_arguments",
                    "reason": arg_error,
                    "message": MSG_INVALID_ARGS,
                },
            )
        )
        return events, None

    state = await state_provider(session_id)
    decision = decide(spec, state)
    args_for_event = validated.model_dump()
    if decision.requires_confirmation:
        recorded = _record_pending(
            pending_store=pending_store,
            invocation_id=invocation_id,
            session_id=session_id,
            provider=provider,
            model=model,
            conversation=conversation,
            call=call,
            spec=spec,
            args=args_for_event,
            state=state,
        )
        if recorded is None:
            return [ErrorEvent(content=MSG_PENDING_ERROR)], "error"
        events = [
            ToolCallEvent(
                invocation_id=invocation_id,
                name=call.name,
                args=args_for_event,
                requires_confirmation=True,
            ),
            ConfirmationRequiredEvent(
                invocation_id=invocation_id,
                name=call.name,
                args_summary=decision.human_summary_es,
            ),
        ]
        return events, "confirmation_required"

    started_ns = time.perf_counter_ns()
    try:
        result = await asyncio.wait_for(
            handler(session_id, validated), timeout=spec.timeout_s
        )
        observation = result if isinstance(result, dict) else {"result": result}
        ok = True
        reason = None
        summary = _compact_summary(observation)
    except asyncio.TimeoutError:
        observation = {
            "ok": False,
            "error": "tool_timeout",
            "message": MSG_TOOL_TIMEOUT,
        }
        ok = False
        reason = "tool_timeout"
        summary = MSG_TOOL_TIMEOUT
    except Exception:
        observation = {
            "ok": False,
            "error": "tool_execution_failed",
            "message": MSG_TOOL_FAILED,
        }
        ok = False
        reason = "tool_execution_failed"
        summary = MSG_TOOL_FAILED
    duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    events = [
        ToolCallEvent(
            invocation_id=invocation_id,
            name=call.name,
            args=args_for_event,
            requires_confirmation=False,
        ),
        ToolResultEvent(
            invocation_id=invocation_id,
            name=call.name,
            ok=ok,
            summary=summary,
            error=reason,
            duration_ms=duration_ms,
        ),
    ]
    conversation.append(_tool_message(call.call_id, observation))
    return events, None


def _validated_args(
    spec: ToolSpec, call: ToolCallRequest
) -> tuple[BaseModel | None, dict[str, Any] | None, str | None]:
    """Validate raw provider arguments against the spec model.

    Returns ``(validated_model, raw_args_for_event, None)`` on success;
    ``(None, raw_or_None, reason_code)`` when the raw JSON is
    unparseable or fails the schema. Raw args are surfaced (for the UI
    event) exactly as the provider sent them, never executed.
    """
    try:
        raw = call.parse_arguments()
    except ValueError:
        return None, None, "invalid_json"
    try:
        return spec.args_model.model_validate(raw), raw, None
    except ValidationError:
        return None, raw, "schema_validation"


def _record_pending(
    *,
    pending_store: PendingRunStore,
    invocation_id: str,
    session_id: str,
    provider: BaseProvider,
    model: str,
    conversation: list[dict[str, Any]],
    call: ToolCallRequest,
    spec: ToolSpec,
    args: dict[str, Any],
    state: ToolState,
) -> str | None:
    """Persist the full resume state; None when the store rejects it."""
    now = time.time()
    pending = PendingRun(
        invocation_id=invocation_id,
        session_id=session_id,
        run_id=f"run_{secrets.token_urlsafe(12)}",
        provider=_provider_name(provider),
        model=model,
        messages=list(conversation),
        tool_call_id=call.call_id,
        tool_name=spec.name,
        args_sha256=canonical_args_sha256(args),
        state_fingerprint=state.fingerprint(),
        created_at=now,
        expires_at=now + PENDING_TTL_S,
    )
    try:
        return pending_store.create(pending)
    except Exception:
        return None


__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_TIMEOUT_S",
    "StateProvider",
    "ToolExecutor",
    "ToolHandler",
    "run_agent_turn",
]
