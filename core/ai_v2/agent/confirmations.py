"""Pending-confirmation resume state: interface frozen in T0.

A ``PendingRun`` stores EVERYTHING needed to resume the agent loop
after the user approves or denies a replace-type tool: the raw provider
messages (including ``assistant.tool_calls``), the tool call id, the
canonical args hash, the provider/model, and the state fingerprint at
request time. The frontend can only approve or deny with the
``invocation_id`` — it can never auto-approve (anti-spoofing, plan
section 4.3).

Only the abstract store interface and helpers live here; the concrete
in-memory implementation lands in T3. ``claim`` MUST be atomic and
single-use: an unknown, expired, foreign-session or already-claimed
run is rejected with the matching exception.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PENDING_TTL_S: float = 900.0
"""Time-to-live of a pending confirmation (15 minutes)."""


class PendingRun(BaseModel):
    """Full resume state of one tool call awaiting user confirmation."""

    model_config = ConfigDict(extra="forbid")

    invocation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    messages: list[dict[str, Any]]
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    args_sha256: str = Field(min_length=64, max_length=64)
    state_fingerprint: str = Field(min_length=1)
    created_at: float = Field(gt=0.0)
    expires_at: float = Field(gt=0.0)
    confirmations_used: int = Field(default=0, ge=0)


class PendingRunError(Exception):
    """Base class for pending-confirmation failures."""


class PendingRunNotFound(PendingRunError):
    """The invocation_id does not exist in the store."""


class ExpiredPendingRun(PendingRunError):
    """The pending run passed its TTL."""


class AlreadyClaimedPendingRun(PendingRunError):
    """The pending run was already claimed (single-use violated)."""


class ForeignSessionPendingRun(PendingRunError):
    """The pending run belongs to another session."""


class PendingRunStore(ABC):
    """Abstract store of pending confirmations.

    Implementations (T3) must guarantee:

    - ``create`` persists the run and returns its ``invocation_id``.
    - ``claim`` is atomic and single-use: the first caller gets the
      run; concurrent or repeated claims raise
      :class:`AlreadyClaimedPendingRun`. Unknown ids raise
      :class:`PendingRunNotFound`, expired runs
      :class:`ExpiredPendingRun`, and runs of another session
      :class:`ForeignSessionPendingRun`.
    - ``invalidate`` removes the run (e.g. after denial or state
      change); invalidating an unknown id is a no-op.
    """

    @abstractmethod
    def create(self, run: PendingRun) -> str:
        """Persist ``run`` and return its ``invocation_id``."""
        ...

    @abstractmethod
    def claim(self, invocation_id: str, session_id: str) -> PendingRun:
        """Atomically consume the pending run for this session."""
        ...

    @abstractmethod
    def invalidate(self, invocation_id: str) -> None:
        """Drop the pending run; unknown ids are ignored."""
        ...


def new_invocation_id() -> str:
    """Return a fresh unpredicatable invocation id (``inv_``-prefixed)."""
    return f"inv_{secrets.token_urlsafe(16)}"


def canonical_args_sha256(args: dict) -> str:
    """Return the SHA-256 of the canonical JSON form of ``args``.

    Canonical form: ``json.dumps`` with sorted keys, compact separators
    and UTF-8 encoding, so any argument reordering hashes identically.
    A confirmation is only valid for the exact arguments approved.
    """
    payload = json.dumps(
        args,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "PENDING_TTL_S",
    "AlreadyClaimedPendingRun",
    "ExpiredPendingRun",
    "ForeignSessionPendingRun",
    "PendingRun",
    "PendingRunError",
    "PendingRunNotFound",
    "PendingRunStore",
    "canonical_args_sha256",
    "new_invocation_id",
]
