"""NDJSON event protocol between the agent loop and the web chat.

The stream is a sequence of JSON lines; each line validates against
exactly one member of the :data:`AgentEvent` discriminated union (key
``type``). The TS mirror lives in ``web/src/api/agentChat.ts`` — keep
both in sync. A stream that asks for confirmation ends in
``confirmation_required`` and is resumed by ``POST /ai/chat/confirm``
(T4), which emits its own NDJSON stream.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator, Field, TypeAdapter, ValidationError

from core.ai_v2.models import AIUsage


class TextEvent(BaseModel):
    """A narrative text fragment produced by the model."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    content: str


class ToolCallEvent(BaseModel):
    """Announces a tool invocation the agent is about to execute.

    ``invocation_id`` correlates logs and UI cards; it is emitted here
    too, not only on confirmations.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call"] = "tool_call"
    invocation_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)
    requires_confirmation: bool


class ToolResultEvent(BaseModel):
    """Outcome of one tool execution, with summaries never blobs."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_result"] = "tool_result"
    invocation_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ok: bool
    summary: str
    duration_ms: float = Field(ge=0.0)
    error: str | None = None


class ConfirmationRequiredEvent(BaseModel):
    """The original stream terminates here when policy demands approval.

    The user approves or denies via ``POST /ai/chat/confirm`` with the
    ``invocation_id``; the PendingRun store (T3) resumes the same loop.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["confirmation_required"] = "confirmation_required"
    invocation_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    args_summary: str


class ErrorEvent(BaseModel):
    """A sanitized error message for the user (never raw internals)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["error"] = "error"
    content: str


class DoneEvent(BaseModel):
    """Terminal event of every stream."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["done"] = "done"
    finish_reason: Literal["stop", "error", "confirmation_required"]
    usage: AIUsage | None = None
    cached: bool = False


AgentEvent = Annotated[
    Union[
        TextEvent,
        ToolCallEvent,
        ToolResultEvent,
        ConfirmationRequiredEvent,
        ErrorEvent,
        DoneEvent,
    ],
    Discriminator("type"),
]


_AGENT_EVENT_ADAPTER = TypeAdapter(AgentEvent)


def event_to_ndjson(event: AgentEvent) -> str:
    """Serialize one event as a single NDJSON line (no trailing newline).

    The caller appends ``"\\n"`` when writing to a stream.
    """
    return _AGENT_EVENT_ADAPTER.dump_json(event).decode("utf-8")


def parse_event_line(line: str) -> AgentEvent:
    """Parse one NDJSON line into an ``AgentEvent``.

    Raises:
        ValueError: If the line is empty, not valid JSON, or does not
            match any event type (fail-closed: unknown types are
            rejected rather than silently dropped).
    """
    stripped = line.strip()
    if not stripped:
        raise ValueError("Empty event line")
    try:
        return _AGENT_EVENT_ADAPTER.validate_json(stripped)
    except ValidationError as exc:
        raise ValueError(f"Invalid agent event line: {exc}") from exc


__all__ = [
    "AgentEvent",
    "ConfirmationRequiredEvent",
    "DoneEvent",
    "ErrorEvent",
    "TextEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "event_to_ndjson",
    "parse_event_line",
]
