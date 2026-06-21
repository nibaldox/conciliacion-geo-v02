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


class ProviderRegistry:
    @classmethod
    def get(
        cls, provider_type: ProviderType, api_key: str | None = None
    ) -> OpenAICompatibleProvider:
        preset = PROVIDER_PRESETS[provider_type]
        if api_key is None:
            env_var = f"{provider_type.value.upper()}_API_KEY"
            api_key = os.environ.get(env_var, "not-needed")
        return OpenAICompatibleProvider(
            base_url=preset["base_url"],
            api_key=api_key,
            name=provider_type.value,
        )

    @classmethod
    def get_default_model(cls, provider_type: ProviderType) -> str:
        return PROVIDER_PRESETS[provider_type]["default_model"]

    @classmethod
    def list_providers(cls) -> list[str]:
        return [p.value for p in ProviderType]