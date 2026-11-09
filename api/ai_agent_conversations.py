"""Server-side conversation store for the AI agent chat (plan section 4.7, T4).

Conversations are persisted in SQLite (``ai_conversations`` table) and
scoped to the middleware session: the client only ever sends back the
opaque server-generated ``conversation_id`` and the server re-binds it
to ``X-Session-ID`` on every request. Unknown ids, foreign sessions and
corrupt payloads are all treated as NOT FOUND — the API never reveals
whether a conversation exists under another session.

Guarantees and limits:

- Opaque ids (``conv_`` + ``secrets.token_urlsafe``), generated
  server-side only; the client can never pick one.
- Server-side system message: the agent system prompt
  (``core/ai_v2/prompts/agent_system.md``) is ensured at position 0 of
  every conversation served to the loop. The client sends only plain
  user text — never roles.
- TTL: conversations not updated within
  :data:`CONVERSATION_TTL_HOURS` are deleted opportunistically on
  access (same SQLite timestamp format as ``cleanup_old_sessions``).
- Cap: at most :data:`MAX_CONVERSATION_MESSAGES` messages and
  :data:`MAX_CONVERSATION_CHARS` JSON-encoded characters are kept per
  conversation. Trimming is GROUP-AWARE: an assistant
  ``tool_calls`` message and all its ``role:tool`` answers form one
  atomic group (never split), the system message is preserved intact
  at position 0, and only the oldest complete groups are dropped.

Single-process by design: the store rides the same SQLite database as
the sessions (see ``api/database.py``); deployments are pinned to one
worker (``render.yaml`` / ``Dockerfile-api``).
"""
from __future__ import annotations

import json
import secrets
from typing import Any, Optional

import api.database as db
from core.ai_v2.prompts import load_prompt_template

CONVERSATION_TTL_HOURS = 24
"""Conversations older than this (by ``updated_at``) are purged on access."""

MAX_CONVERSATION_MESSAGES = 200
"""Hard cap on stored messages per conversation (system message kept)."""

MAX_CONVERSATION_CHARS = 24000
"""Hard cap on the JSON-encoded size of the stored conversation.

Measured as the sum of ``json.dumps(message, ensure_ascii=False)``
lengths over the whole stored list (system message included).
"""

_CONVERSATION_ID_PREFIX = "conv_"

_AGENT_PROMPT_TEMPLATE = "agent_system.md"

_agent_system_prompt_cache: Optional[str] = None


def new_conversation_id() -> str:
    """Return a fresh opaque server-generated conversation id."""
    return _CONVERSATION_ID_PREFIX + secrets.token_urlsafe(16)


def agent_system_prompt() -> str:
    """Load (and cache) the agent system prompt from the prompts dir."""
    global _agent_system_prompt_cache
    if _agent_system_prompt_cache is None:
        _agent_system_prompt_cache = load_prompt_template(_AGENT_PROMPT_TEMPLATE)
    return _agent_system_prompt_cache


def _copy_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(message) for message in messages]


def _ensure_system_message(
    messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return messages with the server-side system prompt at position 0.

    A conversation loaded from the store already carries the system
    message it was created with, so it is kept verbatim; a fresh
    conversation gets it injected here. The loop itself never sees a
    conversation without the system prompt.
    """
    if messages and messages[0].get("role") == "system":
        return _copy_messages(messages)
    return [
        {"role": "system", "content": agent_system_prompt()}
    ] + _copy_messages(messages)


def _message_chars(message: dict[str, Any]) -> int:
    """JSON-encoded size of one message (matches the storage payload)."""
    return len(json.dumps(message, ensure_ascii=False))


def _tool_call_ids(message: dict[str, Any]) -> set[str]:
    """Call ids announced by an assistant ``tool_calls`` message."""
    ids: set[str] = set()
    for call in message.get("tool_calls") or []:
        call_id = call.get("id") if isinstance(call, dict) else None
        if call_id:
            ids.add(str(call_id))
    return ids


def _split_groups(
    body: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Group messages so a tool_calls assistant and its answers stay atomic.

    One group = one assistant message carrying ``tool_calls`` plus ALL
    its ``role:tool`` answers (matched by ``tool_call_id``, up to the
    next assistant/user message); a plain assistant/user message is its
    own group; a ``role:tool`` answer with no open parent starts its own
    group instead of gluing onto unrelated content.
    """
    groups: list[list[dict[str, Any]]] = []
    open_group: Optional[list[dict[str, Any]]] = None
    pending_ids: set[str] = set()
    for message in body:
        role = message.get("role")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if open_group is not None and str(call_id) in pending_ids:
                open_group.append(message)
                pending_ids.discard(str(call_id))
                continue
            groups.append([message])
            open_group = None
            pending_ids = set()
            continue
        group = [message]
        groups.append(group)
        if role == "assistant":
            pending_ids = _tool_call_ids(message)
            open_group = group if pending_ids else None
        else:
            pending_ids = set()
            open_group = None
    return groups


def _cap_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim to the message + char caps, preserving whole tool-calls groups.

    The system message is always kept intact at position 0. Walking from
    the NEWEST group backwards, a group is kept while it fits BOTH the
    message cap (:data:`MAX_CONVERSATION_MESSAGES`) and the char budget
    (:data:`MAX_CONVERSATION_CHARS`); the first group that does not fit
    ends the kept window, so only OLDEST complete groups are dropped and
    a group is NEVER split — an assistant ``tool_calls`` message can
    never be separated from its ``role:tool`` answers (which would make
    the conversation provider-invalid).
    """
    head: list[dict[str, Any]] = []
    body = messages
    if messages and messages[0].get("role") == "system":
        head = [dict(messages[0])]
        body = messages[1:]
    kept: list[list[dict[str, Any]]] = []
    used_msgs = len(head)
    used_chars = sum(_message_chars(message) for message in head)
    for group in reversed(_split_groups(body)):
        group_msgs = len(group)
        group_chars = sum(_message_chars(message) for message in group)
        if used_msgs + group_msgs > MAX_CONVERSATION_MESSAGES:
            break
        if used_chars + group_chars > MAX_CONVERSATION_CHARS:
            break
        kept.append(group)
        used_msgs += group_msgs
        used_chars += group_chars
    trimmed = head
    for group in reversed(kept):
        trimmed.extend(group)
    return trimmed


def load_conversation(
    session_id: str, conversation_id: Optional[str]
) -> Optional[tuple[str, list[dict[str, Any]]]]:
    """Load or create the server-side conversation for this session.

    Returns ``(conversation_id, messages)`` with the system message
    ensured, or ``None`` when a ``conversation_id`` was supplied that is
    unknown or belongs to another session (NOT FOUND semantics — never
    distinguish the two). Expired conversations are purged on access.
    """
    db.delete_old_ai_conversations(CONVERSATION_TTL_HOURS)
    if conversation_id is None:
        return new_conversation_id(), _ensure_system_message([])
    stored = db.get_ai_conversation(conversation_id, session_id)
    if stored is None:
        return None
    return conversation_id, _ensure_system_message(stored)


def append_message(
    messages: list[dict[str, Any]], role: str, content: str
) -> list[dict[str, Any]]:
    """Return a new list with one plain-text message appended.

    ``content`` is stored verbatim as a plain string: a user message
    containing JSON role lookalikes stays plain text end to end.
    """
    return messages + [{"role": role, "content": content}]


def save_conversation(
    session_id: str,
    conversation_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Persist the final conversation (bounded), scoped to the session."""
    db.save_ai_conversation(
        conversation_id, session_id, _cap_messages(_copy_messages(messages))
    )


__all__ = [
    "CONVERSATION_TTL_HOURS",
    "MAX_CONVERSATION_CHARS",
    "MAX_CONVERSATION_MESSAGES",
    "agent_system_prompt",
    "append_message",
    "load_conversation",
    "new_conversation_id",
    "save_conversation",
]
