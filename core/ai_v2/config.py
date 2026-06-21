"""Configuration for the AI agent v2.

All fields can be overridden via environment variables prefixed with
``AI_V2_`` (for example, ``AI_V2_DEFAULT_MODEL=llama3.1:8b``). A local
``.env`` file is also loaded automatically.

The ``default_provider`` field accepts the provider name as a lowercase
string (``ollama``, ``lmstudio``, ``openai``, ``minimax``, ``glm``,
``grok``). It is intentionally typed as ``str`` rather than an enum so
that ``pydantic-settings`` can parse values coming from environment
variables without extra coercion. When ``core.ai_v2.providers.registry``
lands, ``ProviderType`` will re-export these same values as an enum; the
string form here remains the canonical wire format.
"""
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_PROVIDERS: frozenset[str] = frozenset(
    {"ollama", "lmstudio", "openai", "minimax", "glm", "grok"}
)


class AIConfig(BaseSettings):
    """Runtime configuration for the AI agent v2.

    Field defaults follow the blueprint (section 4.1). Override any
    field via an ``AI_V2_*`` environment variable or a ``.env`` file at
    the project root.
    """

    model_config = SettingsConfigDict(
        env_prefix="AI_V2_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    default_provider: str = "ollama"
    default_model: str = "llama3.1:8b"

    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, gt=0)
    timeout_s: float = Field(120.0, gt=0)

    enable_cache: bool = False
    cache_ttl_hours: int = Field(24, gt=0)
    cache_dir: str = ".ai_v2_cache"

    enable_usage_tracking: bool = True
    max_requests_per_minute: int = Field(5, gt=0)
    max_tokens_per_minute: int = Field(100_000, gt=0)

    @field_validator("default_provider")
    @classmethod
    def _validate_default_provider(cls, value: str) -> str:
        """Normalize and validate the provider name."""
        normalized = value.strip().lower()
        if normalized not in _VALID_PROVIDERS:
            raise ValueError(
                f"Unknown AI provider '{value}'. "
                f"Valid providers: {sorted(_VALID_PROVIDERS)}."
            )
        return normalized


__all__ = ["AIConfig"]
