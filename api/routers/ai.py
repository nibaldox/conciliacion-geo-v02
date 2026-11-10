"""AI router — exposes the core.ai_v2 agent over HTTP for the web frontend.

Endpoints:
    GET  /ai/health            Liveness probe: version + known providers
    GET  /ai/providers         List configured provider presets (+ tool support)
    POST /ai/generate          Generate a full report (aggregated, non-streaming)
    POST /ai/generate/stream   Generate the report as an NDJSON chunk stream
    POST /ai/chat              Conversational agent turn (NDJSON agent events)
    POST /ai/chat/confirm      Approve/deny a pending tool call (NDJSON stream)

Chat (T4) notes:

- Gated by ``CONCILIACION_AI_CHAT_ENABLED`` (opt-in; disabled by default).
- Conversations live server-side (``api/ai_agent_conversations.py``), the
  conversation id travels back to the client in the ``X-Conversation-Id``
  response header and is scoped to the middleware session on every request.
- The pending-confirmation store is a single process-wide
  ``InMemoryPendingRunStore`` (module singleton below). This is valid ONLY
  because every real deployment mode is single-process: ``render.yaml``
  pins ``CONCILIACION_WORKERS=1`` on purpose (SQLite stores are
  per-process), ``Dockerfile-api`` defaults to 1 worker, ``dev.sh`` and the
  Electron sidecar run a bare single uvicorn. Multi-worker deployments must
  move this store (and the sessions DB) to a shared backend first.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from core.ai_v2 import (
    AIError,
    AIRequest,
    AIResponseChunk,
    RateLimited,
    __version__,
    stream_report,
)
from core.ai_v2.agent.confirmations import (
    AlreadyClaimedPendingRun,
    ExpiredPendingRun,
    ForeignSessionPendingRun,
    InMemoryPendingRunStore,
    PendingRunNotFound,
    canonical_args_sha256,
)
from core.ai_v2.agent.events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    ToolCallEvent,
    ToolResultEvent,
    event_to_ndjson,
)
from core.ai_v2.agent.loop import (
    MSG_CONFIRMATION_CONSUMED,
    MSG_CONFIRMATION_EXPIRED,
    MSG_CONFIRMATION_NOT_FOUND,
    MSG_PROVIDER_UNSUPPORTED,
    resume_pending_turn,
    run_agent_turn,
)
from core.ai_v2.agent.models import NoArgs, ToolState
from core.ai_v2.config import AIConfig
from core.ai_v2.providers.base import BaseProvider
from core.ai_v2.providers.openai_compat import OpenAICompatibleProvider
from core.ai_v2.providers.registry import (
    PROVIDER_PRESETS,
    ProviderRegistry,
    ProviderType,
    TOOL_CALL_CAPABILITY,
    resolve_base_url,
)
from api import ai_agent_conversations as agent_conversations
import api.database as db
from api._async_db import run_db
from api.ai_agent_handlers import get_workflow_state
from api.ai_agent_write_handlers import ALL_HANDLERS

logger = logging.getLogger(__name__)

_GENERATE_TIMEOUT_S = 120

# Redact common secret patterns before echoing error messages to clients.
_KEY_PATTERNS = re.compile(
    r"sk-[A-Za-z0-9_\-]{20,}"
    r"|Bearer\s+[A-Za-z0-9._\-]+"
    r"|api[_-]?key[=:]\s*\S+",
    re.IGNORECASE,
)


def _sanitize_error(msg: object) -> str:
    """Strip API-key-like substrings and cap length for client responses."""
    redacted = _KEY_PATTERNS.sub("[REDACTED]", str(msg))
    if len(redacted) > 300:
        redacted = redacted[:297] + "…"
    return redacted


router = APIRouter(prefix="/ai", tags=["ai"])


def _build_config(req: AIRequest) -> AIConfig:
    """Translate the per-request advanced overrides into an ``AIConfig``.

    The service reads temperature / max_tokens / timeout_s / cache toggles
    from the config object. Fields left as ``None`` on the request fall back
    to the ``AIConfig`` defaults, matching the previous behaviour.
    ``_env_file=None`` keeps pydantic-settings from reading a local ``.env``
    on every request.
    """
    kwargs: dict[str, object] = {"_env_file": None}
    if req.temperature is not None:
        kwargs["temperature"] = req.temperature
    if req.max_tokens is not None:
        kwargs["max_tokens"] = req.max_tokens
    if req.timeout_s is not None:
        kwargs["timeout_s"] = req.timeout_s
    kwargs["enable_cache"] = bool(req.use_cache)
    return AIConfig(**kwargs)


async def _stream_ndjson(req: AIRequest) -> AsyncIterator[str]:
    """Yield each ``AIResponseChunk`` as a compact JSON line (NDJSON).

    Errors raised by the agent mid-stream are surfaced as a terminal
    ``finish_reason='error'`` chunk so the client can react; this keeps
    the streaming contract uniform at the cost of HTTP-level status codes
    (a streaming response has already committed a 200 by then).
    """
    config = _build_config(req)
    try:
        async with asyncio.timeout(_GENERATE_TIMEOUT_S):
            async for chunk in stream_report(req, config=config):
                yield chunk.model_dump_json() + "\n"
    except RateLimited as exc:
        retry = int(exc.retry_after_s) if exc.retry_after_s > 0 else 60
        err = AIResponseChunk(
            content=_sanitize_error(exc),
            finish_reason="error",
            chunk_index=0,
        )
        yield err.model_dump_json() + "\n"
        logger.warning("AI stream rate-limited (retry after %ss)", retry)
    except TimeoutError:
        err = AIResponseChunk(
            content=f"AI generation timed out after {_GENERATE_TIMEOUT_S}s",
            finish_reason="error",
            chunk_index=0,
        )
        yield err.model_dump_json() + "\n"
    except AIError as exc:
        logger.warning("AI stream failed: %s", exc)
        err = AIResponseChunk(
            content=_sanitize_error(exc),
            finish_reason="error",
            chunk_index=0,
        )
        yield err.model_dump_json() + "\n"


@router.get("/health")
async def health() -> dict:
    """Liveness probe. No remote checks — just version + provider registry."""
    return {
        "status": "ok",
        "version": __version__,
        "providers": [p.value for p in PROVIDER_PRESETS],
    }


@router.get("/providers")
async def providers() -> dict:
    """Return the configured provider presets with tool-calling capability.

    Backwards compatible: the ``providers`` key keeps its historical
    shape (list of names); ``supports_tool_calls`` is additive (T4) so
    the chat UI can disable tools per provider without a second call,
    and ``chat_enabled``/``chat_provider``/``chat_local_only``/
    ``chat_model`` report the chat feature state: the local-only policy
    pins the chat provider to ``lmstudio`` when active (else ``None``),
    and ``chat_model`` is the server-side model override
    (``CONCILIACION_LMSTUDIO_DEFAULT_MODEL``) or the LM Studio preset
    placeholder when unset.
    """
    return {
        "providers": [p.value for p in PROVIDER_PRESETS],
        "supports_tool_calls": {
            p.value: ProviderRegistry.supports_tool_calls(p)
            for p in PROVIDER_PRESETS
        },
        "chat_enabled": _chat_enabled(),
        "chat_provider": _LOCAL_ONLY_PROVIDER if _local_only_active() else None,
        "chat_local_only": _local_only_active(),
        "chat_model": (
            _lmstudio_model_override()
            or PROVIDER_PRESETS[ProviderType.LMSTUDIO]["default_model"]
        ),
    }


@router.post("/generate", response_model=AIResponseChunk)
async def generate(req: AIRequest) -> AIResponseChunk:
    """Generate a full reconciliation report and return it as a single chunk.

    Internally consumes the streaming ``stream_report`` generator and
    accumulates all content before responding. This keeps the wire format
    identical to the streaming chunks the agent produces (``AIResponseChunk``)
    while avoiding SSE complexity on the API boundary. The per-request
    advanced overrides (temperature, max_tokens, timeout_s, cache) are wired
    through via an ``AIConfig`` built from the request body. The corporate
    local-only policy rejects any non-LM Studio provider (400) BEFORE any
    provider call: reports carry session data that must never leave the
    machine. Under that policy, a non-empty
    ``CONCILIACION_LMSTUDIO_DEFAULT_MODEL`` replaces the client-sent model
    downstream (server-managed model, mirroring /ai/chat); when the
    variable is unset the client model passes through unchanged — the
    user may name any locally loaded LM Studio model.
    """
    if _local_only_active() and req.provider != _LOCAL_ONLY_PROVIDER:
        raise HTTPException(status_code=400, detail=_MSG_AI_LOCAL_ONLY)
    req = _apply_lmstudio_model_override(req)
    accumulated: list[str] = []
    last_usage = None
    config = _build_config(req)
    try:
        async with asyncio.timeout(_GENERATE_TIMEOUT_S):
            async for chunk in stream_report(req, config=config):
                if chunk.content:
                    accumulated.append(chunk.content)
                if chunk.usage is not None:
                    last_usage = chunk.usage
    except RateLimited as exc:
        retry = int(exc.retry_after_s) if exc.retry_after_s > 0 else 60
        raise HTTPException(
            status_code=429,
            detail=_sanitize_error(exc),
            headers={"Retry-After": str(retry)},
        )
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"AI generation timed out after {_GENERATE_TIMEOUT_S}s",
        )
    except AIError as exc:
        logger.warning("AI generate failed: %s", exc)
        raise HTTPException(status_code=502, detail=_sanitize_error(exc))

    return AIResponseChunk(
        content="".join(accumulated),
        finish_reason="stop",
        usage=last_usage,
        chunk_index=0,
    )


@router.post("/generate/stream")
async def generate_stream(req: AIRequest) -> StreamingResponse:
    """Generate the report and stream each chunk as a newline-delimited JSON.

    Same payload as ``POST /ai/generate``; the response body is a sequence of
    ``AIResponseChunk`` JSON objects, one per line. The terminal line carries
    ``finish_reason='stop'`` (success) or ``'error'`` (agent failure). The
    corporate local-only policy applies identically: any non-LM Studio
    provider is rejected (400) before the stream opens, and a non-empty
    ``CONCILIACION_LMSTUDIO_DEFAULT_MODEL`` replaces the client-sent model
    downstream (server-managed model); when the variable is unset the
    client model passes through unchanged.
    """
    if _local_only_active() and req.provider != _LOCAL_ONLY_PROVIDER:
        raise HTTPException(status_code=400, detail=_MSG_AI_LOCAL_ONLY)
    req = _apply_lmstudio_model_override(req)
    return StreamingResponse(
        _stream_ndjson(req),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Conversational agent chat (T4) — additive endpoints
# ---------------------------------------------------------------------------
# Single-process deployments only: AGENT_PENDING_STORE below is an
# in-memory singleton and conversations ride the per-process SQLite DB
# (see the module docstring for the deployment-mode evidence).

CHAT_FLAG_ENV = "CONCILIACION_AI_CHAT_ENABLED"
"""Opt-in feature flag; the chat endpoints answer 503 when unset/false."""

WORKERS_ENV = "CONCILIACION_WORKERS"
"""Deployment worker count; chat requires 1 (in-memory pending store)."""

LOCAL_ONLY_ENV = "CONCILIACION_AI_LOCAL_ONLY"
"""Corporate data-sovereignty policy; DEFAULT ON (only LM Studio allowed).

Session data (topos, sections, results) must never leave the machine:
while active, ALL four AI endpoints accept only the ``lmstudio``
provider. Set to ``0``/``false``/``no``/``off`` to relax it.
"""

LMSTUDIO_BASE_URL_ENV = "CONCILIACION_LMSTUDIO_BASE_URL"
"""Optional base_url override for the LM Studio provider.

In server deployments LM Studio runs on the app server or an internal
host reachable from the BACKEND — never on each user's browser machine.
Unset falls back to the registry preset (``http://localhost:1234/v1``).
"""

LMSTUDIO_MODEL_ENV = "CONCILIACION_LMSTUDIO_DEFAULT_MODEL"
"""Optional server-side model override under the local-only policy.

When set (non-empty), /ai/chat AND the report endpoints
(/ai/generate, /ai/generate/stream) replace the client-sent model
with this value: the client can never substitute the configured
model. Unset keeps the client's model (reports may then name any
locally loaded LM Studio model). /ai/providers reports the same
override or the LM Studio preset placeholder (``loaded-model``).
"""

_LOCAL_ONLY_PROVIDER = "lmstudio"
_MSG_CHAT_WORKER_CONFLICT = (
    "El chat con el agente de IA no está disponible en despliegues con "
    "múltiples workers: el almacén de confirmaciones pendientes vive en "
    "la memoria del proceso. Despliega con CONCILIACION_WORKERS=1 o "
    "mueve el almacén a un backend compartido."
)
_MSG_AI_LOCAL_ONLY = (
    "Modo local corporativo: solo LM Studio está permitido para IA en "
    "este despliegue."
)

_CHAT_STREAM_BUDGET_S = 300.0
"""Global wall-clock budget for one streamed turn (provider + all tools).

Separate from the loop's per-iteration provider timeout and each tool's
``ToolSpec.timeout_s`` budget.
"""

_MSG_CHAT_DISABLED = (
    "El chat con el agente de IA está deshabilitado en este despliegue."
)
_MSG_CHAT_PROVIDER_UNKNOWN = "Proveedor de IA desconocido."
_MSG_CHAT_PROVIDER_UNAVAILABLE = (
    "El proveedor de IA de la confirmación no está disponible."
)
_MSG_CHAT_CONVERSATION_NOT_FOUND = (
    "No existe una conversación con ese identificador."
)
_MSG_CHAT_TIMEOUT = "El agente excedió el tiempo máximo del turno; inténtalo de nuevo."
_MSG_CHAT_STREAM_FAILED = (
    "El agente no pudo completar el turno; inténtalo de nuevo."
)


class AgentChatRequest(BaseModel):
    """Strict body of ``POST /ai/chat``: plain user text only.

    The client can NEVER send tool/assistant/system messages: the only
    free-form field is ``message``, stored verbatim as plain user text,
    so JSON role lookalikes inside it carry no structural meaning.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    conversation_id: str | None = Field(default=None, max_length=64)


class AgentChatConfirmRequest(BaseModel):
    """Strict body of ``POST /ai/chat/confirm``: the decision ONLY.

    Provider, model, tool and arguments are rebuilt server-side from the
    claimed pending run; extra fields are rejected so the client can
    never steer the resumed execution.
    """

    model_config = ConfigDict(extra="forbid")

    invocation_id: str = Field(min_length=1, max_length=128)
    approved: bool


AGENT_PENDING_STORE = InMemoryPendingRunStore()
"""Process-wide pending-confirmation store shared by /chat and /chat/confirm.

Single-process only — see the module docstring and ``render.yaml``
(``CONCILIACION_WORKERS=1`` on purpose).
"""


def _invalidated_conversation_of(
    invocation_id: str, session_id: str
) -> str | None:
    """Conversation binding of a pending tombstoned by a DELETE (T5).

    Store implementations that do not track conversation-scoped
    invalidation answer ``None`` (the generic consumed mapping applies).
    """
    try:
        return AGENT_PENDING_STORE.invalidated_conversation(
            invocation_id, session_id
        )
    except NotImplementedError:
        return None


def _chat_enabled() -> bool:
    """Feature-flag read at request time (env-var opt-in)."""
    return os.environ.get(CHAT_FLAG_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _chat_worker_conflict() -> str | None:
    """Return the 503 detail for multi-worker deployments, else None.

    Evaluated at request time: chat needs a process-local pending
    confirmation store AND the per-process SQLite DB, so with the
    feature enabled and more than one configured worker the turn is
    refused (503) instead of silently losing confirmations across
    processes. Inactive when the chat feature itself is disabled.
    """
    if not _chat_enabled():
        return None
    try:
        workers = int(os.environ.get(WORKERS_ENV, "1") or "1")
    except ValueError:
        return None
    if workers > 1:
        return _MSG_CHAT_WORKER_CONFLICT
    return None


def _local_only_active() -> bool:
    """Corporate local-only policy; ACTIVE unless explicitly relaxed.

    Default ON: only an explicit ``0``/``false``/``no``/``off`` (or any
    other falsy word) in ``CONCILIACION_AI_LOCAL_ONLY`` deactivates it.
    """
    value = os.environ.get(LOCAL_ONLY_ENV)
    if value is None:
        return True
    return value.strip().lower() not in ("0", "false", "no", "off")


def _lmstudio_model_override() -> str | None:
    """Configured chat model override, or None to keep the client's."""
    return os.environ.get(LMSTUDIO_MODEL_ENV, "").strip() or None


def _apply_lmstudio_model_override(req: AIRequest) -> AIRequest:
    """Server-managed model for reports under the local-only policy.

    Active ONLY when the corporate local-only policy is on, the request
    targets ``lmstudio`` and ``CONCILIACION_LMSTUDIO_DEFAULT_MODEL`` is
    set (non-empty): the configured model replaces the client-sent one,
    mirroring the chat endpoints. Otherwise the client model passes
    through untouched — with the variable unset the user may name any
    locally loaded LM Studio model.
    """
    if not _local_only_active() or req.provider != _LOCAL_ONLY_PROVIDER:
        return req
    override = _lmstudio_model_override()
    if override is None:
        return req
    return req.model_copy(update={"model": override})


def _build_chat_provider(provider: str) -> BaseProvider:
    """Build the provider for one chat turn from its preset name.

    Injection point for tests: monkeypatch this to hand back a fake
    provider; both /chat and /chat/confirm build exclusively here. The
    base_url comes from ``resolve_base_url`` — the SAME resolution the
    report path uses through ``ProviderRegistry.get`` — so the optional
    ``CONCILIACION_LMSTUDIO_BASE_URL`` override applies uniformly to
    chat and reports. The provider is constructed fresh because the
    OpenAI client binds its base_url at construction time.
    """
    provider_type = ProviderType(provider)
    api_key = os.environ.get(
        f"{provider_type.value.upper()}_API_KEY", "not-needed"
    )
    return OpenAICompatibleProvider(
        base_url=resolve_base_url(provider_type),
        api_key=api_key,
        name=provider_type.value,
        supports_tool_calls=TOOL_CALL_CAPABILITY.get(provider_type, False),
    )


async def _agent_state_provider(session_id: str) -> ToolState:
    """Map the REAL session state (get_workflow_state) onto ToolState."""
    raw = await get_workflow_state(session_id, NoArgs())
    return ToolState(
        n_sections=int(raw.get("n_sections") or 0),
        n_results=int(raw.get("n_results") or 0),
        process_status=str(raw.get("process_status") or "idle"),
        has_design_mesh=bool(raw.get("has_design_mesh")),
        has_topo_mesh=bool(raw.get("has_topo_mesh")),
    )


def _audit_line(event: AgentEvent) -> str:
    """Audit-log tool calls/results, then serialize the event line.

    Logged per plan guardrail 9: tool name, invocation id, canonical
    args hash (SHA-256 of the canonical JSON form — never the raw
    arguments, so session coordinates never reach logs), duration and
    outcome. Prompts, keys and handler outputs are never logged.
    """
    if isinstance(event, ToolCallEvent):
        logger.info(
            "agent tool_call name=%s invocation_id=%s args_sha256=%s",
            event.name,
            event.invocation_id,
            canonical_args_sha256(event.args),
        )
    elif isinstance(event, ToolResultEvent):
        logger.info(
            "agent tool_result name=%s invocation_id=%s ok=%s "
            "duration_ms=%.0f error=%s",
            event.name,
            event.invocation_id,
            event.ok,
            event.duration_ms,
            event.error,
        )
    return event_to_ndjson(event) + "\n"


async def _consume_agent_stream(
    events: AsyncIterator[AgentEvent],
) -> AsyncIterator[str]:
    """Wrap one agent stream: global budget, always a terminal ``done``.

    The loop itself ends every stream with ``done``; this wrapper adds
    the sanitized error + ``done`` pair for failures OUTSIDE the loop
    (global budget exhaustion or an unexpected exception) so the NDJSON
    contract can never end mid-stream without a terminal event.
    """
    try:
        async with asyncio.timeout(_CHAT_STREAM_BUDGET_S):
            async for event in events:
                yield _audit_line(event)
    except TimeoutError:
        logger.warning("agent chat stream timed out after %.0fs", _CHAT_STREAM_BUDGET_S)
        yield event_to_ndjson(ErrorEvent(content=_MSG_CHAT_TIMEOUT)) + "\n"
        yield event_to_ndjson(DoneEvent(finish_reason="error")) + "\n"
    except Exception as exc:
        logger.warning("agent chat stream failed: %s", type(exc).__name__)
        yield event_to_ndjson(ErrorEvent(content=_MSG_CHAT_STREAM_FAILED)) + "\n"
        yield event_to_ndjson(DoneEvent(finish_reason="error")) + "\n"


def _ndjson_response(
    stream: AsyncIterator[str], conversation_id: str | None
) -> StreamingResponse:
    """NDJSON streaming response with the chat headers."""
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    if conversation_id is not None:
        headers["X-Conversation-Id"] = conversation_id
    return StreamingResponse(
        stream,
        media_type="application/x-ndjson",
        headers=headers,
    )


@router.post("/chat")
async def chat(req: AgentChatRequest, request: Request) -> StreamingResponse:
    """Run ONE conversational agent turn as an NDJSON event stream.

    Provider capability is validated BEFORE the stream starts (unknown
    provider -> 400, no tool-calling support -> 422), the server-side
    conversation is loaded/created for the middleware session (unknown
    or foreign conversation_id -> generic 404) and the user message is
    appended as PLAIN TEXT. The conversation id is returned in the
    ``X-Conversation-Id`` response header without touching the event
    contract. The corporate local-only policy accepts only the
    ``lmstudio`` provider (400 otherwise, before any provider build) and
    the server-side model override replaces the client-sent model while
    it is active.
    """
    if not _chat_enabled():
        raise HTTPException(status_code=503, detail=_MSG_CHAT_DISABLED)
    worker_conflict = _chat_worker_conflict()
    if worker_conflict is not None:
        raise HTTPException(status_code=503, detail=worker_conflict)
    session_id = await run_db(db.get_or_create_session, request.state.session_id)
    if _local_only_active() and req.provider != _LOCAL_ONLY_PROVIDER:
        raise HTTPException(status_code=400, detail=_MSG_AI_LOCAL_ONLY)
    try:
        ProviderType(req.provider)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=_sanitize_error(_MSG_CHAT_PROVIDER_UNKNOWN)
        )
    if not ProviderRegistry.supports_tool_calls(ProviderType(req.provider)):
        raise HTTPException(status_code=422, detail=MSG_PROVIDER_UNSUPPORTED)
    loaded = agent_conversations.load_conversation(session_id, req.conversation_id)
    if loaded is None:
        raise HTTPException(
            status_code=404,
            detail=_sanitize_error(_MSG_CHAT_CONVERSATION_NOT_FOUND),
        )
    conversation_id, messages = loaded
    messages = agent_conversations.append_message(messages, "user", req.message)
    model = (
        _lmstudio_model_override() if _local_only_active() else None
    ) or req.model
    provider = _build_chat_provider(req.provider)

    def conversation_sink(final_messages: list[dict[str, Any]]) -> None:
        agent_conversations.save_conversation(
            session_id, conversation_id, final_messages
        )

    async def stream() -> AsyncIterator[str]:
        async for line in _consume_agent_stream(
            run_agent_turn(
                session_id=session_id,
                messages=messages,
                provider=provider,
                model=model,
                executor=ALL_HANDLERS,
                pending_store=AGENT_PENDING_STORE,
                state_provider=_agent_state_provider,
                conversation_id=conversation_id,
                conversation_sink=conversation_sink,
            )
        ):
            yield line

    return _ndjson_response(stream(), conversation_id)


@router.post("/chat/confirm")
async def chat_confirm(
    req: AgentChatConfirmRequest, request: Request
) -> StreamingResponse:
    """Approve or deny ONE pending tool call; streams the resumed turn.

    The decision is the ONLY client input: the provider instance and the
    model are rebuilt exclusively from the claimed pending run
    (``pending.provider`` -> ``ProviderType`` -> ``ProviderRegistry.get``;
    the loop falls back to ``pending.model``). CLAIM-THEN-STREAM: the
    atomic single-use claim runs FIRST and its typed outcome is mapped
    to a status code BEFORE any 200 stream starts — unknown and
    foreign-session ids both answer the same generic 404 (existence is
    never revealed), expired -> 410, already consumed -> 409; on success
    the claimed run is handed to ``resume_pending_turn`` (which skips its
    internal claim), so a confirmation can NEVER start a 200 stream for
    an already-consumed confirmation. Under the corporate local-only
    policy the claimed provider is re-checked as defence in depth: the
    provider was already validated at creation (a pending run can only
    be created from a local-only-approved /chat turn), so the rebuild
    path is safe.
    """
    if not _chat_enabled():
        raise HTTPException(status_code=503, detail=_MSG_CHAT_DISABLED)
    worker_conflict = _chat_worker_conflict()
    if worker_conflict is not None:
        raise HTTPException(status_code=503, detail=worker_conflict)
    session_id = await run_db(db.get_or_create_session, request.state.session_id)
    try:
        claimed = AGENT_PENDING_STORE.claim(req.invocation_id, session_id)
    except (PendingRunNotFound, ForeignSessionPendingRun):
        raise HTTPException(
            status_code=404,
            detail=_sanitize_error(MSG_CONFIRMATION_NOT_FOUND),
        )
    except ExpiredPendingRun:
        raise HTTPException(
            status_code=410,
            detail=_sanitize_error(MSG_CONFIRMATION_EXPIRED),
        )
    except AlreadyClaimedPendingRun:
        bound_conversation = _invalidated_conversation_of(
            req.invocation_id, session_id
        )
        if (
            bound_conversation is not None
            and db.get_ai_conversation(bound_conversation, session_id) is None
        ):
            raise HTTPException(
                status_code=404,
                detail=_sanitize_error(MSG_CONFIRMATION_NOT_FOUND),
            )
        raise HTTPException(
            status_code=409,
            detail=_sanitize_error(MSG_CONFIRMATION_CONSUMED),
        )
    if _local_only_active() and claimed.provider != _LOCAL_ONLY_PROVIDER:
        raise HTTPException(status_code=400, detail=_MSG_AI_LOCAL_ONLY)
    try:
        provider = _build_chat_provider(claimed.provider)
    except ValueError:
        raise HTTPException(
            status_code=502, detail=_sanitize_error(_MSG_CHAT_PROVIDER_UNAVAILABLE)
        )
    conversation_id = claimed.conversation_id

    def _conversation_exists(sid: str, cid: str) -> bool:
        return db.get_ai_conversation(cid, sid) is not None

    def _make_sink(
        conv_id: str,
    ) -> Callable[[list[dict[str, Any]]], None]:
        def sink(final_messages: list[dict[str, Any]]) -> None:
            agent_conversations.save_conversation(session_id, conv_id, final_messages)

        return sink

    conversation_sink = (
        _make_sink(conversation_id) if conversation_id is not None else None
    )

    async def stream() -> AsyncIterator[str]:
        async for line in _consume_agent_stream(
            resume_pending_turn(
                session_id=session_id,
                invocation_id=req.invocation_id,
                approved=req.approved,
                provider=provider,
                executor=ALL_HANDLERS,
                pending_store=AGENT_PENDING_STORE,
                state_provider=_agent_state_provider,
                conversation_sink=conversation_sink,
                claimed=claimed,
                conversation_exists=_conversation_exists,
            )
        ):
            yield line

    return _ndjson_response(stream(), conversation_id)


@router.delete("/chat/conversation/{conversation_id}")
async def delete_chat_conversation(
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=64),
) -> dict:
    """Delete ONE server-side conversation owned by this session.

    Corporate data retention (T5): the "limpiar conversación" button in
    the chat panel must really remove the stored messages, not just
    reset the client view. Gated by the SAME chat flag and worker guard
    as the other chat endpoints. Unknown and foreign ids answer
    ``{"deleted": false}`` — existence is never revealed. When the row
    is removed, every pending confirmation bound to this session +
    conversation is invalidated AND tombstoned first (additive
    ``pendings_invalidated`` count), so a later approval can never
    resurrect a deleted conversation.
    """
    if not _chat_enabled():
        raise HTTPException(status_code=503, detail=_MSG_CHAT_DISABLED)
    worker_conflict = _chat_worker_conflict()
    if worker_conflict is not None:
        raise HTTPException(status_code=503, detail=worker_conflict)
    session_id = await run_db(db.get_or_create_session, request.state.session_id)
    deleted = db.delete_ai_conversation(conversation_id, session_id)
    response: dict[str, Any] = {"deleted": deleted, "pendings_invalidated": 0}
    if deleted:
        try:
            response["pendings_invalidated"] = (
                AGENT_PENDING_STORE.invalidate_for_conversation(
                    session_id, conversation_id
                )
            )
        except NotImplementedError:
            del response["pendings_invalidated"]
    return response


_HISTORY_SUMMARY_MAX_CHARS = 200
"""Bound for sanitized tool summaries (mirrors the loop's event summary)."""


def _history_tool_entry(message: dict[str, Any]) -> dict[str, Any]:
    """Sanitized {role, ok, summary, error} for one stored tool answer.

    Parsed from the stored observation JSON ONLY: the raw arguments are
    never echoed back. The summary is the human ``message`` verbatim
    (bounded); an observation without one — or with unparseable content
    — yields an EMPTY summary, so no JSON dump of the observation can
    leak args fragments through the history endpoint.
    """
    content = message.get("content")
    payload: Any = None
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except ValueError:
            payload = None
    if isinstance(payload, dict):
        summary = payload.get("message")
        if not isinstance(summary, str):
            summary = ""
        error = payload.get("error")
        return {
            "role": "tool",
            "ok": bool(payload.get("ok")),
            "summary": summary[:_HISTORY_SUMMARY_MAX_CHARS],
            "error": error if isinstance(error, str) else None,
        }
    return {
        "role": "tool",
        "ok": False,
        "summary": "",
        "error": None,
    }


def _sanitize_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Client-safe projection of a stored conversation (T5).

    The server-side system prompt is EXCLUDED (it never leaves the
    server); user and assistant messages keep only their plain text;
    assistant ``tool_calls`` are reduced to the list of function NAMES
    (the raw arguments stay server-side); ``role:tool`` answers become
    {ok, summary, error} parsed from the stored observation. This is the
    exact shape served by GET /ai/chat/conversation/{id}.
    """
    sanitized: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            sanitized.append(_history_tool_entry(message))
            continue
        content = message.get("content")
        entry: dict[str, Any] = {
            "role": "assistant" if role == "assistant" else "user",
            "content": content if isinstance(content, str) else "",
        }
        if role == "assistant":
            tools = [
                str((call.get("function") or {}).get("name") or "")
                for call in message.get("tool_calls") or []
                if isinstance(call, dict)
            ]
            tools = [name for name in tools if name]
            if tools:
                entry["tools"] = tools
        sanitized.append(entry)
    return sanitized


@router.get("/chat/conversation/{conversation_id}")
async def get_chat_conversation(
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=64),
) -> Any:
    """Sanitized history + live pending of ONE conversation (T5).

    Restores the chat view after a page reload WITHOUT persisting
    anything client-side: the conversation id already in the browser is
    re-bound to the middleware session and the server answers the
    sanitized message list (see :func:`_sanitize_history` — no system
    prompt, no raw tool arguments) plus the conversation's pending
    confirmation {invocation_id, tool_name, args_summary} so the card
    can be re-armed against POST /ai/chat/confirm. Unknown and foreign
    ids answer the SAME generic ``{"exists": false}`` with a 404 status
    — existence is never revealed. Gated by the SAME chat flag and
    worker guard as the other chat endpoints.
    """
    if not _chat_enabled():
        raise HTTPException(status_code=503, detail=_MSG_CHAT_DISABLED)
    worker_conflict = _chat_worker_conflict()
    if worker_conflict is not None:
        raise HTTPException(status_code=503, detail=worker_conflict)
    session_id = await run_db(db.get_or_create_session, request.state.session_id)
    stored = db.get_ai_conversation(conversation_id, session_id)
    if stored is None:
        return JSONResponse(status_code=404, content={"exists": False})
    try:
        pending = AGENT_PENDING_STORE.peek_for_conversation(
            session_id, conversation_id
        )
    except NotImplementedError:
        pending = None
    return {
        "exists": True,
        "conversation_id": conversation_id,
        "messages": _sanitize_history(stored),
        "pending": None
        if pending is None
        else {
            "invocation_id": pending.invocation_id,
            "tool_name": pending.tool_name,
            "args_summary": pending.args_summary,
        },
    }
