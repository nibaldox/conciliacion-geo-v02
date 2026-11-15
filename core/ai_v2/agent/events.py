"""NDJSON event protocol between the agent loop and the web chat.

The stream is a sequence of JSON lines; each line validates against
exactly one member of the :data:`AgentEvent` discriminated union (key
``type``). The TS mirror lives in ``web/src/api/agentChat.ts`` — keep
both in sync. A stream that asks for confirmation ends in
``confirmation_required`` and is resumed by ``POST /ai/chat/confirm``
(T4), which emits its own NDJSON stream.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_serializer,
)

from core.ai_v2.models import AIUsage

_EXPORT_QUERY_KEYS = frozenset({"filters", "project", "author"})
_EXPORT_QUERY_VALUE_MAX_CHARS = 4000


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


class ExportDownloadMeta(BaseModel):
    """Download metadata of a successful ``export_report`` call.

    The browser builds the export URL from this field, never from the
    200-char summary. ``query`` only admits the keys the export endpoints
    take as parameters, each value 1 to 4000 characters.
    """

    model_config = ConfigDict(extra="forbid")

    format: Literal["excel", "word", "pdf", "dxf", "images"]
    query: dict[str, str] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def _query_keys_and_lengths(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(value) - _EXPORT_QUERY_KEYS)
        if unknown:
            raise ValueError(f"unsupported export query keys: {unknown}")
        for key, item in value.items():
            if not 1 <= len(item) <= _EXPORT_QUERY_VALUE_MAX_CHARS:
                raise ValueError(
                    f"export query value {key!r} must have 1 to "
                    f"{_EXPORT_QUERY_VALUE_MAX_CHARS} characters"
                )
        return value


class ToolResultEvent(BaseModel):
    """Outcome of one tool execution, with summaries never blobs.

    ``download`` is set only for a successful ``export_report``. While it
    is None the key is left out of the NDJSON line, so every other
    tool_result event keeps the exact pre-download serialization.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_result"] = "tool_result"
    invocation_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ok: bool
    summary: str
    duration_ms: float = Field(ge=0.0)
    error: str | None = None
    download: ExportDownloadMeta | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_download(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        data = handler(self)
        if self.download is None:
            data.pop("download", None)
        return data


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
    "ExportDownloadMeta",
    "TextEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "event_to_ndjson",
    "parse_event_line",
]
