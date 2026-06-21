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

_VALID_PROVIDERS: frozenset[str] = frozenset(
    {"ollama", "lmstudio", "openai", "minimax", "glm", "grok"}
)


class AIUsage(BaseModel):
    """Token usage and timing metrics for a single AI request.

    All numeric fields default to zero so partial reports (for example,
    when a provider omits ``prompt_tokens``) still validate.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
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
        stream: If ``True`` (default), yield chunks; else return one chunk.
        use_cache: If ``True`` (default), consult the disk cache when enabled.
        metadata: Free-form per-call data (``user_id``, ``session_id``, ...).
    """

    model_config = ConfigDict(extra="forbid")

    results: dict
    sections: list[dict] | None = None
    settings: dict | None = None
    provider: str
    model: str
    stream: bool = True
    use_cache: bool = True
    metadata: dict = Field(default_factory=dict)

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
