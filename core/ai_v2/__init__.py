"""Agente IA v2 — provider-agnostic, async-first, Pydantic v2.

Reemplaza a los antiguos ``core.ai_service`` (moderno FastAPI) y
``core.ai_reporter`` (legacy Streamlit). Ver
``docs/AI_AGENT_V2_BLUEPRINT.md`` para el diseño completo y
``docs/AI_AGENT.md`` para la guía de uso.

Quick start::

    from core.ai_v2 import AIRequest, AIConfig, stream_report
    import asyncio

    async def main():
        async for chunk in stream_report(AIRequest(
            provider="openai", model="gpt-4o-mini",
            results={"comparisons": [...]},
        )):
            if chunk.content:
                print(chunk.content, end="", flush=True)

    asyncio.run(main())
"""
from __future__ import annotations

from core.ai_v2.cache import DiskCache, _cache_key
from core.ai_v2.config import AIConfig
from core.ai_v2.errors import (
    AIError,
    CacheError,
    ContextTooLong,
    InvalidResponse,
    ProviderUnavailable,
    RateLimited,
)
from core.ai_v2.models import AIRequest, AIResponseChunk, AIUsage
from core.ai_v2.providers import (
    PROVIDER_PRESETS,
    BaseProvider,
    OpenAICompatibleProvider,
    ProviderRegistry,
    ProviderType,
)
from core.ai_v2.service import stream_report

__version__ = "2.0.0"
__status__ = "stable"

__all__: list[str] = [
    "__version__",
    "__status__",
    "AIConfig",
    "AIRequest",
    "AIResponseChunk",
    "AIUsage",
    "AIError",
    "ProviderUnavailable",
    "RateLimited",
    "ContextTooLong",
    "InvalidResponse",
    "CacheError",
    "BaseProvider",
    "OpenAICompatibleProvider",
    "ProviderRegistry",
    "ProviderType",
    "PROVIDER_PRESETS",
    "DiskCache",
    "_cache_key",
    "stream_report",
]