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

Two transversal guardrails (plan section 5.4) gate EVERY new
confirmation: at most ``MAX_TURN_CONFIRMATIONS`` pauses per user turn
(an excess call is answered with a ``confirmation_limit_reached``
observation and NEVER executes), and a call already denied by the
user in the same turn is never requested again (``denied_by_user``
observation with ``MSG_DENIED_NO_RETRY``).

Every tool call of a turn is answered before the next iteration, so a
multi-tool-call turn always produces one ``role: tool`` message per
``tool_call_id``.

Final text is streamed incrementally: each ``stream_chat`` iteration
forwards every non-empty text fragment through the provider's
``on_text_delta`` callback into an in-loop queue, and the loop yields
one ``TextEvent`` per word-boundary segment (voseo-neutralized at safe
word boundaries, since ``neutralize_spanish`` may change fragment
lengths). The remaining tail is flushed when the turn completes and NO
full-text event is emitted again, so the concatenation of all
``TextEvent`` fragments equals the persisted text exactly. Providers
that never call the callback keep the previous single full-text
``TextEvent``.

Resumption (plan sections 4.3/5-T3): ``resume_pending_turn`` atomically
claims the pending confirmation, revalidates the approved arguments
(canonical SHA-256) and the session ``ToolState`` fingerprint —
invalidating and re-evaluating the pure policy when the state changed —
then executes or denies EXACTLY the confirmed call, answers every
remaining unanswered ``tool_call_id`` of the paused assistant message
and continues the same bounded loop. The approve/deny decision arrives
as a parameter from the caller (T4 confirm endpoint): the model can
never approve itself.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from core.ai_v2.agent.catalog import get_tool, openai_tools
from core.ai_v2.agent.confirmations import (
    PENDING_TTL_S,
    AlreadyClaimedPendingRun,
    ExpiredPendingRun,
    ForeignSessionPendingRun,
    PendingRun,
    PendingRunError,
    PendingRunNotFound,
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
from core.ai_v2.agent.style import neutralize_spanish
from core.ai_v2.agent.turn import ToolCallRequest
from core.ai_v2.models import AIUsage
from core.ai_v2.providers.base import BaseProvider

logger = logging.getLogger(__name__)

ToolHandler = Callable[[str, BaseModel], Awaitable[dict[str, Any]]]
"""Injected handler signature: validated args model in, small dict out."""

ToolExecutor = Mapping[str, ToolHandler]
"""Tool name -> handler mapping (production: ``READ_HANDLERS``)."""

StateProvider = Callable[[str], Awaitable[ToolState]]
"""Async session_id -> real ``ToolState`` snapshot."""

ConversationSink = Callable[[list[dict[str, Any]]], None]
"""Sync sink invoked ONCE at stream end with the final conversation copy.

Additive (T4): the API layer passes a callback that persists the
conversation server-side. The loop NEVER mutates the caller's ``messages``
list; the sink receives a fresh shallow copy of the loop's own
conversation, so storing it cannot alias the caller's input.
"""

DEFAULT_MAX_ITERATIONS = 8
DEFAULT_TIMEOUT_S = 120.0
MAX_TURN_CONFIRMATIONS = 2
"""Guardrail 4: max REPLACE/EXPENSIVE_REPLACE pauses per user turn."""

_STREAM_POLL_S = 0.05
"""Max idle wait per queue poll while a provider turn is streaming.

Short enough that turn completion (and the per-iteration timeout
deadline) is noticed promptly, long enough to avoid busy-waiting.
"""

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
MSG_CONFIRMATION_NOT_FOUND = (
    "No hay una confirmación pendiente con ese identificador."
)
MSG_CONFIRMATION_EXPIRED = (
    "La confirmación expiró; solicita la acción nuevamente."
)
MSG_CONFIRMATION_FOREIGN = (
    "Esta confirmación pertenece a otra sesión."
)
MSG_CONFIRMATION_CONSUMED = (
    "Esta confirmación ya fue procesada."
)
MSG_CONFIRMATION_ARGS_CHANGED = (
    "Los argumentos aprobados ya no coinciden con los registrados; "
    "la confirmación fue invalidada."
)
MSG_CONFIRMATION_CORRUPT = (
    "El estado de la confirmación es inconsistente; solicita la "
    "acción nuevamente."
)
MSG_CONFIRMATION_STATE_CHANGED = (
    "El estado de la sesión cambió desde la solicitud; se requiere "
    "confirmar nuevamente."
)
MSG_CONFIRMATION_CONVERSATION_DELETED = (
    "La conversación asociada fue eliminada; la acción no se ejecutará."
)
MSG_DENIED_BY_USER = "El usuario denegó la ejecución de esta herramienta."
MSG_DENIED_NO_RETRY = (
    "Ya fue denegada en este turno y no se reintentará."
)
MSG_TURN_CANCELLED = (
    "El usuario canceló la acción; esta operación del turno no se ejecutó."
)
MSG_CONFIRMATION_LIMIT = (
    "Se alcanzó el límite de confirmaciones por turno; solicita lo que "
    "falte en lenguaje natural."
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
    conversation_id: str | None = None,
    conversation_sink: ConversationSink | None = None,
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
        conversation_id: Additive (T4) server-side conversation id
            stamped into every pending confirmation created this turn,
            so ``POST /ai/chat/confirm`` can resume the right
            conversation. ``None`` keeps the pre-T4 behaviour.
        conversation_sink: Additive (T4) sync callback invoked at most
            once when the stream ends, with a copy of the final
            conversation. Sink failures are logged and swallowed: they
            must never corrupt the event stream after ``done``.

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
    try:
        async for event in _drive_iterations(
            session_id=session_id,
            conversation=conversation,
            provider=provider,
            model=model,
            executor=executor,
            pending_store=pending_store,
            state_provider=state_provider,
            resolved_tools=resolved_tools,
            max_iterations=max_iterations,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
            turn_confirmations=0,
            conversation_id=conversation_id,
        ):
            yield event
    finally:
        if conversation_sink is not None:
            _emit_conversation(conversation_sink, conversation)


def _emit_conversation(
    sink: ConversationSink, conversation: list[dict[str, Any]]
) -> None:
    """Hand a copy of the final conversation to the sink; never raises.

    A failing sink must not corrupt the event stream (it runs in the
    generator's ``finally``, after ``done`` may already be yielded), so
    failures are logged with the exception type only — never the
    conversation content.
    """
    try:
        sink([dict(message) for message in conversation])
    except Exception as exc:
        logger.warning(
            "agent conversation sink failed: %s", type(exc).__name__
        )


async def _drive_iterations(
    *,
    session_id: str,
    conversation: list[dict[str, Any]],
    provider: BaseProvider,
    model: str,
    executor: ToolExecutor,
    pending_store: PendingRunStore,
    state_provider: StateProvider,
    resolved_tools: list[dict[str, Any]],
    max_iterations: int,
    timeout_s: float,
    temperature: float,
    max_tokens: int,
    turn_confirmations: int,
    conversation_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Bounded provider iterations over one conversation.

    Shared by ``run_agent_turn`` and ``resume_pending_turn``: calls the
    provider, answers every tool call of the turn (stopping early on a
    recorded confirmation or a store failure) and terminates with a
    ``done`` event on stop, provider failure or budget exhaustion.
    ``turn_confirmations`` is the count of confirmation pauses already
    presented in this user turn; every new pause created here stores
    ``turn_confirmations + 1`` and the guardrails evaluate against it.
    """
    usage_total: AIUsage | None = None
    start_ns = time.perf_counter_ns()

    for _iteration in range(max_iterations):
        queue: asyncio.Queue[str] = asyncio.Queue()

        def _push_delta(chunk: str) -> None:
            queue.put_nowait(chunk)

        turn_task = asyncio.create_task(
            provider.stream_chat(
                conversation,
                model=model,
                tools=resolved_tools,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
                on_text_delta=_push_delta,
            )
        )
        deadline = asyncio.get_running_loop().time() + timeout_s
        buffer = ""
        streamed_text = False
        timed_out = False
        try:
            while not (turn_task.done() and queue.empty()):
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    chunk = await asyncio.wait_for(
                        queue.get(),
                        timeout=min(_STREAM_POLL_S, remaining),
                    )
                except asyncio.TimeoutError:
                    continue
                buffer += chunk
                cut = max(
                    buffer.rfind(" "),
                    buffer.rfind("\n"),
                    buffer.rfind("\t"),
                ) + 1
                if cut > 0:
                    segment = buffer[:cut]
                    buffer = buffer[cut:]
                    normalized = neutralize_spanish(segment)
                    if normalized:
                        streamed_text = True
                        yield TextEvent(content=normalized)
        finally:
            if not turn_task.done():
                turn_task.cancel()
                try:
                    await turn_task
                except BaseException:
                    pass

        if timed_out:
            yield ErrorEvent(content=MSG_PROVIDER_TIMEOUT)
            yield DoneEvent(
                finish_reason="error",
                usage=_with_duration(usage_total, _elapsed_ms(start_ns)),
            )
            return
        try:
            turn = await turn_task
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

        if buffer:
            tail = neutralize_spanish(buffer)
            if tail:
                streamed_text = True
                yield TextEvent(content=tail)

        usage_total = _accumulate_usage(usage_total, turn.usage)

        if not turn.tool_calls:
            final_text = neutralize_spanish(turn.text)
            if turn.text:
                conversation.append(
                    {"role": "assistant", "content": final_text}
                )
            if not streamed_text and final_text:
                yield TextEvent(content=final_text)
            yield DoneEvent(
                finish_reason="stop",
                usage=_with_duration(usage_total, _elapsed_ms(start_ns)),
            )
            return

        conversation.append(
            _assistant_tool_calls_message(
                neutralize_spanish(turn.text), turn.tool_calls
            )
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
                turn_confirmations=turn_confirmations,
                conversation_id=conversation_id,
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
    turn_confirmations: int,
    conversation_id: str | None = None,
) -> tuple[list[AgentEvent], Literal["confirmation_required", "error"] | None]:
    """Process one tool call and append its role:tool answer.

    Returns the events for this call and, when the stream must STOP,
    the ``done`` finish reason (``confirmation_required`` after a
    recorded pending run, ``error`` when recording failed); None to
    continue the loop. Confirmation-gated calls first pass the
    guardrails: a call denied by the user in this turn and a pause
    beyond ``MAX_TURN_CONFIRMATIONS`` are answered with a safe
    observation and NEVER execute nor create a pending.
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
        block = _pending_block_reason(
            conversation=conversation,
            spec=spec,
            validated_args=args_for_event,
            turn_confirmations=turn_confirmations,
        )
        if block is not None:
            error, message = block
            observation = {
                "ok": False,
                "error": error,
                "message": message,
            }
            events = _denial_events(
                invocation_id, call.name, args_for_event, error, message
            )
            conversation.append(_tool_message(call.call_id, observation))
            return events, None
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
            turn_confirmations=turn_confirmations + 1,
            conversation_id=conversation_id,
            args_summary=decision.human_summary_es[:500],
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

    events, observation = await _execute_tool(
        invocation_id=invocation_id,
        call=call,
        spec=spec,
        handler=handler,
        validated=validated,
        session_id=session_id,
    )
    conversation.append(_tool_message(call.call_id, observation))
    return events, None


async def _execute_tool(
    *,
    invocation_id: str,
    call: ToolCallRequest,
    spec: ToolSpec,
    handler: ToolHandler,
    validated: BaseModel,
    session_id: str,
) -> tuple[list[AgentEvent], dict[str, Any]]:
    """Execute one validated call under the per-tool timeout budget.

    Shared by the live loop and the resume path: handler failures and
    timeouts become sanitized observations, never raised; the returned
    events announce the call and its bounded outcome.
    """
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
            args=validated.model_dump(),
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
    return events, observation


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


def _turn_messages(conversation: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Slice of the conversation belonging to the CURRENT user turn.

    Everything after the LAST ``role: user`` message: denials recorded
    in earlier turns must never leak into the no-retry block.
    """
    start = 0
    for index, message in enumerate(conversation):
        if isinstance(message, dict) and message.get("role") == "user":
            start = index + 1
    return conversation[start:]


def _observation_error(content: Any) -> str | None:
    """``error`` field of a role:tool observation payload, if parseable."""
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except ValueError:
        return None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str):
            return error
    return None


def _denied_call_keys(
    conversation: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    """(tool_name, canonical args sha256) pairs denied by the user.

    Scans the CURRENT user turn only: a ``role:tool`` observation with
    ``error == 'denied_by_user'`` marks its ``tool_call_id`` as denied,
    and the raw assistant entry carrying that id contributes its
    canonical args hash (via the spec args model, when parseable).
    Unparseable or uncataloged entries are skipped, never guessed.
    """
    denied_ids = {
        message["tool_call_id"]
        for message in _turn_messages(conversation)
        if isinstance(message, dict)
        and message.get("role") == "tool"
        and isinstance(message.get("tool_call_id"), str)
        and _observation_error(message.get("content")) == "denied_by_user"
    }
    keys: set[tuple[str, str]] = set()
    for message in _turn_messages(conversation):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for entry in message.get("tool_calls") or []:
            entry_id = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(entry_id, str) or entry_id not in denied_ids:
                continue
            function = (entry.get("function") or {}) if isinstance(entry, dict) else {}
            spec = get_tool(str(function.get("name") or ""))
            if spec is None:
                continue
            try:
                raw = json.loads(str(function.get("arguments") or ""))
            except ValueError:
                continue
            try:
                validated = spec.args_model.model_validate(raw)
            except ValidationError:
                continue
            keys.add((spec.name, canonical_args_sha256(validated.model_dump())))
    return keys


def _was_denied_in_turn(
    conversation: list[dict[str, Any]],
    spec: ToolSpec,
    validated_args: dict[str, Any],
) -> bool:
    """True when the IDENTICAL call was already denied in this turn."""
    key = (spec.name, canonical_args_sha256(validated_args))
    return key in _denied_call_keys(conversation)


def _pending_block_reason(
    *,
    conversation: list[dict[str, Any]],
    spec: ToolSpec,
    validated_args: dict[str, Any],
    turn_confirmations: int,
) -> tuple[str, str] | None:
    """Guardrails 5 + 4: why a NEW pending must NOT be created, if so.

    A call already denied by the user in this turn is never re-asked
    (hard no-retry block), and a pause beyond ``MAX_TURN_CONFIRMATIONS``
    exceeds the per-turn cap. Returns ``(error, message)`` so the caller
    can answer the call without executing it and without a pending.
    """
    if _was_denied_in_turn(conversation, spec, validated_args):
        return "denied_by_user", MSG_DENIED_NO_RETRY
    if turn_confirmations + 1 > MAX_TURN_CONFIRMATIONS:
        return "confirmation_limit_reached", MSG_CONFIRMATION_LIMIT
    return None


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
    turn_confirmations: int,
    conversation_id: str | None = None,
    args_summary: str = "",
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
        turn_confirmations=turn_confirmations,
        conversation_id=conversation_id,
        args_summary=args_summary,
    )
    try:
        return pending_store.create(pending)
    except Exception:
        return None


def _pending_assistant_message(
    conversation: list[dict[str, Any]], tool_call_id: str
) -> dict[str, Any] | None:
    """Assistant message carrying the pending tool_call id, if any."""
    for message in reversed(conversation):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for entry in message.get("tool_calls") or []:
            if isinstance(entry, dict) and entry.get("id") == tool_call_id:
                return message
    return None


def _call_entry(message: dict[str, Any], tool_call_id: str) -> dict[str, Any] | None:
    """Raw tool_call entry for one id inside an assistant message."""
    for entry in message.get("tool_calls") or []:
        if isinstance(entry, dict) and entry.get("id") == tool_call_id:
            return entry
    return None


def _answered_call_ids(conversation: list[dict[str, Any]]) -> set[str]:
    """Ids that already carry a role:tool answer in the conversation."""
    return {
        message["tool_call_id"]
        for message in conversation
        if isinstance(message, dict)
        and message.get("role") == "tool"
        and isinstance(message.get("tool_call_id"), str)
    }


def _entry_to_request(entry: dict[str, Any], call_id: str) -> ToolCallRequest:
    """Rebuild a ToolCallRequest from a raw replayed tool_call entry."""
    function = entry.get("function") or {}
    return ToolCallRequest(
        call_id=call_id,
        name=str(function.get("name") or ""),
        arguments=str(function.get("arguments") or ""),
        arguments_valid=True,
    )


def _denial_events(
    invocation_id: str,
    name: str,
    args: dict[str, Any],
    error: str,
    message: str,
) -> list[AgentEvent]:
    """Announce + close a call that will NOT run because the user denied."""
    return [
        ToolCallEvent(
            invocation_id=invocation_id,
            name=name,
            args=args,
            requires_confirmation=False,
        ),
        ToolResultEvent(
            invocation_id=invocation_id,
            name=name,
            ok=False,
            summary=message,
            error=error,
            duration_ms=0.0,
        ),
    ]


async def resume_pending_turn(
    *,
    session_id: str,
    invocation_id: str,
    approved: bool,
    provider: BaseProvider,
    executor: ToolExecutor,
    pending_store: PendingRunStore,
    state_provider: StateProvider,
    model: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    conversation_sink: ConversationSink | None = None,
    claimed: PendingRun | None = None,
    conversation_exists: Callable[[str, str], bool] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Resume ONE paused turn after the user's approve/deny decision.

    Unless ``claimed`` is provided, the pending run is claimed atomically
    (single-use; denial consumes it too) and revalidated before anything
    executes:

    - the raw arguments replayed from the stored assistant message must
      re-validate and hash to the approved ``args_sha256``;
    - the session ``ToolState`` is RE-QUERIED now: an unchanged
      fingerprint honors the approval, a changed one re-evaluates the
      pure policy — which either executes autonomously (prior work
      disappeared) or re-arms a fresh confirmation with a NEW
      invocation id.

    APPROVED: the confirmed tool executes exactly once and every other
    unanswered ``tool_call_id`` of the paused assistant message goes
    through the normal flow (validate -> policy -> execute/observe), so
    the provider receives one ``role: tool`` message per id before the
    next iteration. DENIED: nothing executes — the confirmed call and
    the unanswered siblings receive safe denial observations and the
    loop continues with a fresh provider iteration. The per-turn
    confirmation counter travels inside the pending run: every re-arm
    or sibling pause is created with ``turn_confirmations + 1`` and
    refused once ``MAX_TURN_CONFIRMATIONS`` is exceeded, and a call
    already denied by the user in this turn is never re-asked.

    Args:
        session_id: Active session id from the middleware; must match
            the pending run's session or the claim is rejected.
        invocation_id: Pending confirmation identifier shown to the UI.
        approved: The user's decision; the model cannot set it.
        provider: Live provider to continue the conversation with (the
            caller re-instantiates it from the pending run's
            ``provider``/``model``).
        executor: Tool name -> async handler mapping.
        pending_store: Injected pending-confirmation store.
        state_provider: Async ``session_id`` -> real ``ToolState``.
        model: Provider model identifier; defaults to the pending run's.
        max_iterations: Fresh budget of provider iterations.
        timeout_s: Per-iteration provider budget.
        tools: OpenAI tools payload; defaults to the whole catalog.
        temperature: Sampling temperature for provider calls.
        max_tokens: Provider max_tokens for provider calls.
        conversation_sink: Additive (T4) sync callback invoked at most
            once when the stream ends after a successful claim, with a
            copy of the final conversation. Claim rejections end the
            stream before any conversation exists, so the sink is NOT
            invoked for them. Sink failures are logged and swallowed.
        claimed: Additive (T4) already-claimed pending run. When given,
            the internal atomic claim is SKIPPED — the HTTP endpoint
            claimed it just before, mapping the typed claim failures to
            status codes before any 200 stream starts — and this run is
            used directly, so a confirmation can never be streamed after
            a concurrent consumer consumed it. ``None`` keeps the
            internal claim (backwards compatible).
        conversation_exists: Additive (T5) predicate
            ``(session_id, conversation_id) -> bool`` evaluated after the
            claim and the corrupt-state checks. When the pending belongs
            to a conversation that no longer exists (deleted between the
            pause and the approval), the pending is invalidated and the
            stream ends with an explicit error — NOTHING executes, so a
            deleted conversation can never be resurrected by an
            approval. ``None`` skips the check (backwards compatible).

    Yields:
        T0 agent events; the stream ALWAYS ends with a ``done`` event
        (never an unhandled exception for typed claim rejections).
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")

    pending: PendingRun | None = claimed
    if pending is None:
        try:
            pending = pending_store.claim(invocation_id, session_id)
        except PendingRunNotFound:
            yield ErrorEvent(content=MSG_CONFIRMATION_NOT_FOUND)
            yield DoneEvent(finish_reason="error")
            return
        except ExpiredPendingRun:
            yield ErrorEvent(content=MSG_CONFIRMATION_EXPIRED)
            yield DoneEvent(finish_reason="error")
            return
        except ForeignSessionPendingRun:
            yield ErrorEvent(content=MSG_CONFIRMATION_FOREIGN)
            yield DoneEvent(finish_reason="error")
            return
        except AlreadyClaimedPendingRun:
            yield ErrorEvent(content=MSG_CONFIRMATION_CONSUMED)
            yield DoneEvent(finish_reason="error")
            return
        except PendingRunError:
            yield ErrorEvent(content=MSG_PENDING_ERROR)
            yield DoneEvent(finish_reason="error")
            return
        except Exception:
            yield ErrorEvent(content=MSG_PENDING_ERROR)
            yield DoneEvent(finish_reason="error")
            return

    resolved_model = model if model is not None else pending.model
    conversation = [dict(message) for message in pending.messages]
    assistant_message = _pending_assistant_message(conversation, pending.tool_call_id)
    if assistant_message is None:
        pending_store.invalidate(invocation_id)
        yield ErrorEvent(content=MSG_CONFIRMATION_CORRUPT)
        yield DoneEvent(finish_reason="error")
        return
    entry = _call_entry(assistant_message, pending.tool_call_id)
    if entry is None:
        pending_store.invalidate(invocation_id)
        yield ErrorEvent(content=MSG_CONFIRMATION_CORRUPT)
        yield DoneEvent(finish_reason="error")
        return

    if (
        pending.conversation_id
        and conversation_exists is not None
        and not conversation_exists(session_id, pending.conversation_id)
    ):
        pending_store.invalidate(invocation_id)
        yield ErrorEvent(content=MSG_CONFIRMATION_CONVERSATION_DELETED)
        yield DoneEvent(finish_reason="error")
        return
    call = _entry_to_request(entry, pending.tool_call_id)

    spec = get_tool(call.name)
    if spec is None or spec.name != pending.tool_name:
        pending_store.invalidate(invocation_id)
        yield ErrorEvent(content=MSG_CONFIRMATION_CORRUPT)
        yield DoneEvent(finish_reason="error")
        return

    validated, _raw_args, arg_error = _validated_args(spec, call)
    if arg_error is not None or validated is None:
        pending_store.invalidate(invocation_id)
        yield ErrorEvent(content=MSG_CONFIRMATION_ARGS_CHANGED)
        yield DoneEvent(finish_reason="error")
        return
    validated_args = validated.model_dump()
    if canonical_args_sha256(validated_args) != pending.args_sha256:
        pending_store.invalidate(invocation_id)
        yield ErrorEvent(content=MSG_CONFIRMATION_ARGS_CHANGED)
        yield DoneEvent(finish_reason="error")
        return

    state_now = await state_provider(session_id)
    decision = decide(spec, state_now)
    confirmed_block: tuple[str, str] | None = None
    if state_now.fingerprint() != pending.state_fingerprint:
        if decision.requires_confirmation:
            confirmed_block = _pending_block_reason(
                conversation=conversation,
                spec=spec,
                validated_args=validated_args,
                turn_confirmations=pending.turn_confirmations,
            )
            if confirmed_block is None:
                re_invocation = new_invocation_id()
                recorded = _record_pending(
                    pending_store=pending_store,
                    invocation_id=re_invocation,
                    session_id=session_id,
                    provider=provider,
                    model=resolved_model,
                    conversation=conversation,
                    call=call,
                    spec=spec,
                    args=validated_args,
                    state=state_now,
                    turn_confirmations=pending.turn_confirmations + 1,
                    conversation_id=pending.conversation_id,
                    args_summary=decision.human_summary_es[:500],
                )
                if recorded is None:
                    yield ErrorEvent(content=MSG_PENDING_ERROR)
                    yield DoneEvent(finish_reason="error")
                    return
                yield ToolCallEvent(
                    invocation_id=re_invocation,
                    name=spec.name,
                    args=validated_args,
                    requires_confirmation=True,
                )
                yield ConfirmationRequiredEvent(
                    invocation_id=re_invocation,
                    name=spec.name,
                    args_summary=decision.human_summary_es,
                )
                yield DoneEvent(finish_reason="confirmation_required")
                return
            block_error, block_message = confirmed_block
            block_observation = {
                "ok": False,
                "error": block_error,
                "message": block_message,
            }
            for event in _denial_events(
                invocation_id, spec.name, validated_args, block_error, block_message
            ):
                yield event
            conversation.append(_tool_message(pending.tool_call_id, block_observation))

    if confirmed_block is None and approved:
        handler = executor.get(spec.name)
        if handler is None:
            observation = {
                "ok": False,
                "error": "handler_unavailable",
                "message": MSG_TOOL_UNAVAILABLE,
            }
            for event in _denial_events(
                invocation_id,
                spec.name,
                validated_args,
                "handler_unavailable",
                MSG_TOOL_UNAVAILABLE,
            ):
                yield event
            conversation.append(_tool_message(pending.tool_call_id, observation))
        else:
            events, observation = await _execute_tool(
                invocation_id=invocation_id,
                call=call,
                spec=spec,
                handler=handler,
                validated=validated,
                session_id=session_id,
            )
            conversation.append(_tool_message(pending.tool_call_id, observation))
            for event in events:
                yield event
    elif confirmed_block is None:
        observation = {
            "ok": False,
            "error": "denied_by_user",
            "message": MSG_DENIED_BY_USER,
        }
        for event in _denial_events(
            invocation_id,
            spec.name,
            validated_args,
            "denied_by_user",
            MSG_DENIED_BY_USER,
        ):
            yield event
        conversation.append(_tool_message(pending.tool_call_id, observation))

    if approved:
        for sibling in _unanswered_siblings(conversation, assistant_message, pending):
            sibling_call = _entry_to_request(sibling, str(sibling.get("id")))
            events, stop_reason = await _handle_tool_call(
                call=sibling_call,
                session_id=session_id,
                conversation=conversation,
                executor=executor,
                pending_store=pending_store,
                state_provider=state_provider,
                model=resolved_model,
                provider=provider,
                turn_confirmations=pending.turn_confirmations,
                conversation_id=pending.conversation_id,
            )
            for event in events:
                yield event
            if stop_reason is not None:
                yield DoneEvent(finish_reason=stop_reason)
                if conversation_sink is not None:
                    _emit_conversation(conversation_sink, conversation)
                return
    else:
        for event in _answer_siblings_denied(conversation, assistant_message, pending):
            yield event

    resolved_tools = tools if tools is not None else openai_tools()
    try:
        async for event in _drive_iterations(
            session_id=session_id,
            conversation=conversation,
            provider=provider,
            model=resolved_model,
            executor=executor,
            pending_store=pending_store,
            state_provider=state_provider,
            resolved_tools=resolved_tools,
            max_iterations=max_iterations,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
            turn_confirmations=pending.turn_confirmations,
            conversation_id=pending.conversation_id,
        ):
            yield event
    finally:
        if conversation_sink is not None:
            _emit_conversation(conversation_sink, conversation)


def _unanswered_siblings(
    conversation: list[dict[str, Any]],
    assistant_message: dict[str, Any],
    pending: PendingRun,
) -> list[dict[str, Any]]:
    """Raw tool_call entries of the paused message still unanswered."""
    answered = _answered_call_ids(conversation)
    siblings: list[dict[str, Any]] = []
    for candidate in assistant_message.get("tool_calls") or []:
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get("id")
        if (
            isinstance(candidate_id, str)
            and candidate_id
            and candidate_id != pending.tool_call_id
            and candidate_id not in answered
        ):
            siblings.append(candidate)
    return siblings


def _answer_siblings_denied(
    conversation: list[dict[str, Any]],
    assistant_message: dict[str, Any],
    pending: PendingRun,
) -> list[AgentEvent]:
    """Safe denial observations for every unanswered sibling call."""
    events: list[AgentEvent] = []
    observation = {
        "ok": False,
        "error": "skipped_turn_denied",
        "message": MSG_TURN_CANCELLED,
    }
    for sibling in _unanswered_siblings(conversation, assistant_message, pending):
        sibling_call = _entry_to_request(sibling, str(sibling.get("id")))
        try:
            sibling_args: dict[str, Any] = sibling_call.parse_arguments()
        except ValueError:
            sibling_args = {}
        events.extend(
            _denial_events(
                new_invocation_id(),
                sibling_call.name,
                sibling_args,
                "skipped_turn_denied",
                MSG_TURN_CANCELLED,
            )
        )
        conversation.append(_tool_message(sibling_call.call_id, observation))
    return events


__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_TIMEOUT_S",
    "MAX_TURN_CONFIRMATIONS",
    "ConversationSink",
    "StateProvider",
    "ToolExecutor",
    "ToolHandler",
    "resume_pending_turn",
    "run_agent_turn",
]
