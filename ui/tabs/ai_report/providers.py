"""Catálogo puro de providers y modelos para la pestaña IA v2."""
from __future__ import annotations

import os
from typing import Any

from core.ai_v2.providers import (
    PROVIDER_PRESETS,
    OpenAICompatibleProvider,
    ProviderRegistry,
    ProviderType,
)
from ui.state_keys import ai_v2_key_for


PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (local)",
    "lmstudio": "LM Studio (local)",
    "openai": "OpenAI",
    "openrouter": "OpenRouter (cloud)",
    "minimax": "MiniMax",
    "glm": "GLM",
    "grok": "Grok",
}


PROVIDERS_NEEDING_KEY: frozenset[str] = frozenset(
    {"openai", "openrouter", "minimax", "glm", "grok"}
)


PROVIDER_ENV_VAR: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "glm": "GLM_API_KEY",
    "grok": "GROK_API_KEY",
}


LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "lmstudio"})


CLOUD_PROMPT_RATE_USD_PER_TOKEN: float = 0.10 / 1_000_000.0
CLOUD_COMPLETION_RATE_USD_PER_TOKEN: float = 0.30 / 1_000_000.0


def provider_env_var(provider_name: str) -> str:
    """Return the environment variable name expected for a provider."""
    return PROVIDER_ENV_VAR.get(provider_name, "")


def resolve_api_key(
    ptype: ProviderType,
    session_state: dict[str, Any] | None = None,
) -> str:
    """Resolve API key from environment first, then Streamlit session state."""
    env_var = provider_env_var(ptype.value)
    env_val = os.environ.get(env_var, "")
    if env_val:
        return env_val
    state = session_state or {}
    return state.get(ai_v2_key_for(ptype.value), "")


def get_default_model(ptype: ProviderType) -> str:
    """Return the default model for the selected provider."""
    return ProviderRegistry.get_default_model(ptype)


def get_provider(
    ptype: ProviderType,
    api_key: str | None = None,
) -> OpenAICompatibleProvider:
    """Build an OpenAI-compatible provider instance."""
    if api_key:
        return ProviderRegistry.get(ptype, api_key=api_key)
    return ProviderRegistry.get(ptype)


def is_local_provider(provider_name: str) -> bool:
    """Return True if the provider runs locally (no cloud billing)."""
    return provider_name in LOCAL_PROVIDERS


def provider_label(provider_name: str) -> str:
    """Return the human-readable label for a provider."""
    return PROVIDER_LABELS.get(provider_name, provider_name)


def provider_base_url(provider_name: str) -> str:
    """Return the configured base URL for a provider."""
    ptype = ProviderType(provider_name)
    return PROVIDER_PRESETS[ptype]["base_url"]
