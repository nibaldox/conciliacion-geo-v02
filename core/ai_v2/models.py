"""Pydantic models for the AI agent v2 request/response pipeline.

These dataclasses are the public wire format between the UI / API layer
and ``core.ai_v2.service.stream_report``. They are intentionally tolerant
on input (``dict`` for free-form payloads) and strict on output
(``Literal`` finish reasons, typed usage tracking).

``provider`` is typed as ``str`` (lowercase provider name) to avoid a
circular import with ``core.ai_v2.providers.registry``. The same string
values are validated here so typos are caught at the boundary.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.ai_v2.providers.registry import PROVIDER_PRESETS

_VALID_PROVIDERS: frozenset[str] = frozenset(p.value for p in PROVIDER_PRESETS)


class AIUsage(BaseModel):
    """Token usage and timing metrics for a single AI request.

    All numeric fields default to zero so partial reports (for example,
    when a provider omits ``prompt_tokens``) still validate.

    ``is_synthetic`` is True when ``completion_tokens`` and
    ``total_tokens`` were estimated from the response text (e.g.
    word-count) rather than reported by the provider. The UI uses
    this flag to display a "(estimated)" hint next to the token
    counts so users know not to bill against them.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    is_synthetic: bool = False
    duration_ms: float = 0.0
    cost_usd: float | None = None


class AIResponseChunk(BaseModel):
    """One streamed chunk of an AI-generated report.

    Attributes:
        content: Token(s) or text fragment produced by the model.
        finish_reason: Set only on the final chunk; ``None`` while streaming.
        usage: Optional usage block, typically attached to the last chunk.
        cached: ``True`` if this chunk was served from disk cache.
        chunk_index: Zero-based position of this chunk in the stream.
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    finish_reason: Literal["stop", "length", "error"] | None = None
    usage: AIUsage | None = None
    cached: bool = False
    chunk_index: int = 0


class AIRequest(BaseModel):
    """Request payload for generating an AI reconciliation report.

    Attributes:
        results: Raw ``comparison_results`` dict from the reconciliation engine.
        sections: Optional list of cross-section dicts to enrich the prompt.
        settings: Optional tolerances / project metadata.
        provider: Lowercase provider name (validated against the registry set).
        model: Provider-specific model identifier (e.g. ``llama3.1:8b``).
        notes: Optional free-text note from the user (wire parity with the
            Streamlit tab; currently passed through, not rendered by the
            builder which is off-limits to this change).
        context: Optional free-form context dict (parity slot; the builder
            consumes ``metadata`` for rendered context today).
        stream: If ``True`` (default), yield chunks; else return one chunk.
        use_cache: If ``True`` (default), consult the disk cache when enabled.
        metadata: Free-form per-call data (``user_id``, ``session_id``, ...).
        max_tokens: Advanced override for the provider ``max_tokens``.
        temperature: Advanced override for the provider ``temperature`` (0.0-2.0).
        timeout_s: Advanced override for the provider request ``timeout_s``.
        filters: Optional active table filters (sector/section/level/bench).
        blast_trend: Optional blast-trend metadata block merged into the prompt;
            falls back to ``metadata['blast_trend']`` for backwards compat.
    """

    model_config = ConfigDict(extra="forbid")

    results: dict
    sections: list[dict] | None = None
    settings: dict | None = None
    provider: str
    model: str
    notes: str | None = None
    context: dict | None = None
    stream: bool = True
    use_cache: bool = True
    metadata: dict = Field(default_factory=dict)
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout_s: float | None = Field(default=None, gt=0)
    filters: dict | None = None
    blast_trend: dict | None = None

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        """Normalize and validate the provider name."""
        normalized = value.strip().lower()
        if normalized not in _VALID_PROVIDERS:
            raise ValueError(
                f"Unknown AI provider '{value}'. "
                f"Valid providers: {sorted(_VALID_PROVIDERS)}."
            )
        return normalized


__all__ = ["AIRequest", "AIResponseChunk", "AIUsage"]
