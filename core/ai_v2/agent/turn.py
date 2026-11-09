"""Neutral chat-turn response type for tool-calling providers (T2).

A :class:`ChatTurn` is ONE COMPLETE provider response — narrative text
plus every tool call the model emitted — never a stream fragment. It is
deliberately separate from :class:`core.ai_v2.models.AIResponseChunk`
(the report-streaming wire format of ``stream_report``) so the two
contracts cannot mix semantically: reports stream text chunks, the
agent loop consumes whole turns.
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from core.ai_v2.models import AIUsage


class ToolCallRequest(BaseModel):
    """One complete tool call requested by the model.

    Attributes:
        call_id: Provider ``tool_call`` id; the loop must echo it back
            in the ``role: tool`` message that answers this call.
        name: Function name chosen by the model; empty when the
            provider never sent one (the loop resolves empty names
            through the catalog and answers them as unavailable, so a
            malformed stream never crashes the provider layer).
        arguments: RAW arguments JSON string exactly as the provider
            sent it — never re-serialized — so the assistant message
            can be replayed verbatim on the next iteration.
        arguments_valid: True when ``arguments`` parsed as a JSON
            object (empty string counts as ``{}``).
        arguments_error: Stable reason code when invalid
            (``invalid_json`` or ``not_an_object``), else None.
    """

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1)
    name: str = ""
    arguments: str = ""
    arguments_valid: bool = False
    arguments_error: Optional[str] = None

    def parse_arguments(self) -> dict:
        """Parse ``arguments`` into a plain dict.

        Empty arguments parse as ``{}`` because providers omit the
        field entirely for parameterless tools.

        Raises:
            ValueError: If the raw string is not valid JSON or is not
                a JSON object (truncated fragments land here too).
        """
        raw = (self.arguments or "").strip()
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Tool call arguments must be a JSON object")
        return parsed


class ChatTurn(BaseModel):
    """One complete provider chat response (text + tool calls).

    Attributes:
        text: Narrative content produced this turn; empty when the
            model only requested tool calls.
        tool_calls: Every tool call in provider order; empty for
            plain-text turns. Multiple calls per turn are supported.
        finish_reason: Raw provider finish reason (``tool_calls``,
            ``stop``, ``length``, ...) or None when the provider did
            not send one; informational — the loop branches on
            ``tool_calls`` being non-empty.
        usage: Token usage reported by the provider for this turn.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[AIUsage] = None


__all__ = ["ChatTurn", "ToolCallRequest"]
