"""Provider registry and presets."""
from __future__ import annotations

import os
from enum import Enum

from core.ai_v2.providers.openai_compat import OpenAICompatibleProvider


class ProviderType(str, Enum):
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    MINIMAX = "minimax"
    GLM = "glm"
    GROK = "grok"


def _resolve_default_model(provider_type: ProviderType) -> str:
    """Resolve the default model for ``provider_type``.

    Order of precedence:
      1. Environment variable ``CONCILIACION_<PROVIDER>_DEFAULT_MODEL``
         (e.g. ``CONCILIACION_OPENROUTER_DEFAULT_MODEL``).
      2. Hardcoded value in ``PROVIDER_PRESETS``.

    Whitespace around the env var value is stripped; a variable set to an
    empty string is treated as unset so operators can safely blank a value
    without breaking the registry.
    """
    env_var = f"CONCILIACION_{provider_type.value.upper()}_DEFAULT_MODEL"
    raw = os.environ.get(env_var)
    if raw is not None:
        candidate = raw.strip()
        if candidate:
            return candidate
    return PROVIDER_PRESETS[provider_type]["default_model"]


PROVIDER_PRESETS: dict[ProviderType, dict[str, str]] = {
    ProviderType.OLLAMA: {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.1:8b",
    },
    ProviderType.LMSTUDIO: {
        "base_url": "http://localhost:1234/v1",
        "default_model": "loaded-model",
    },
    ProviderType.OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    ProviderType.OPENROUTER: {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    },
    ProviderType.MINIMAX: {
        "base_url": "https://api.minimax.io/anthropic",
        "default_model": "MiniMax-M3",
    },
    ProviderType.GLM: {
        "base_url": "https://api.z.ai/api/anthropic",
        "default_model": "glm-5.2",
    },
    ProviderType.GROK: {
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-4.20",
    },
}

TOOL_CALL_CAPABILITY: dict[ProviderType, bool] = {
    ProviderType.OLLAMA: True,
    ProviderType.LMSTUDIO: True,
    ProviderType.OPENAI: True,
    ProviderType.OPENROUTER: True,
    ProviderType.MINIMAX: False,
    ProviderType.GLM: False,
    ProviderType.GROK: True,
}
"""Tool-calling capability per preset (T3 design correction).

True for providers speaking the OpenAI chat-completions tool-calls
format: OpenAI, Grok (xAI, ``/v1``) plus the OpenAI-compatible local /
relay presets (Ollama, LM Studio, OpenRouter), whose loaded models are
expected to support function calling over ``/v1/chat/completions``.
False ONLY for the Anthropic-format presets (MiniMax and GLM), whose
endpoints use ``anthropic-version`` semantics this loop does not speak.
A wrong True degrades gracefully at runtime: when the provider rejects
tool calls mid-stream the loop surfaces a sanitized error event and
stops — no crash, no faked text (see the loop regression test).
"""

LMSTUDIO_BASE_URL_ENV = "CONCILIACION_LMSTUDIO_BASE_URL"
"""Optional base_url override for the LM Studio preset.

Deployment override for corporate setups where LM Studio runs on the
app server or an internal host. Read by :func:`resolve_base_url` so
the chat endpoints AND the report endpoints resolve the SAME URL.
Whitespace is stripped; a blank value counts as unset.
"""


def resolve_base_url(provider_type: ProviderType) -> str:
    """Resolve the base_url for ``provider_type``.

    Only LM Studio honours ``CONCILIACION_LMSTUDIO_BASE_URL``; every
    other provider returns its preset base_url unchanged.
    """
    preset = PROVIDER_PRESETS[provider_type]["base_url"]
    if provider_type is not ProviderType.LMSTUDIO:
        return preset
    raw = os.environ.get(LMSTUDIO_BASE_URL_ENV)
    if raw is None:
        return preset
    candidate = raw.strip()
    return candidate or preset


class ProviderRegistry:
    @classmethod
    def get(
        cls, provider_type: ProviderType, api_key: str | None = None
    ) -> OpenAICompatibleProvider:
        if api_key is None:
            env_var = f"{provider_type.value.upper()}_API_KEY"
            api_key = os.environ.get(env_var, "not-needed")
        return OpenAICompatibleProvider(
            base_url=resolve_base_url(provider_type),
            api_key=api_key,
            name=provider_type.value,
            supports_tool_calls=TOOL_CALL_CAPABILITY.get(provider_type, False),
        )

    @classmethod
    def get_default_model(cls, provider_type: ProviderType) -> str:
        return _resolve_default_model(provider_type)

    @classmethod
    def supports_tool_calls(cls, provider_type: ProviderType) -> bool:
        """Conservative per-preset tool-calling capability default."""
        return TOOL_CALL_CAPABILITY.get(provider_type, False)

    @classmethod
    def list_providers(cls) -> list[str]:
        return [p.value for p in ProviderType]
