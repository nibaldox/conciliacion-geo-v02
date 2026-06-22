"""Stream AI agent v2 reports end-to-end."""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from core.ai_v2.builder import build_analysis_prompt
from core.ai_v2.cache import DiskCache, _cache_key
from core.ai_v2.models import AIRequest, AIResponseChunk, AIUsage
from core.ai_v2.providers import ProviderType

if TYPE_CHECKING:
    from core.ai_v2.providers.base import BaseProvider


async def stream_report(
    request: AIRequest | dict,
    *,
    provider: "BaseProvider | None" = None,
    config: Any = None,
) -> AsyncIterator[AIResponseChunk]:
    """Generate the executive report as an async stream of chunks."""
    if not isinstance(request, AIRequest):
        request = AIRequest(**request) if isinstance(request, dict) else request

    if config is None:
        temperature = 0.3
        max_tokens = 4096
        timeout_s = 120.0
        enable_cache = False
        cache_dir = ".ai_v2_cache"
        cache_ttl_hours = 24
        enable_usage_tracking = True
    else:
        temperature = getattr(config, "temperature", 0.3)
        max_tokens = getattr(config, "max_tokens", 4096)
        timeout_s = getattr(config, "timeout_s", 120.0)
        enable_cache = getattr(config, "enable_cache", False)
        cache_dir = getattr(config, "cache_dir", ".ai_v2_cache")
        cache_ttl_hours = getattr(config, "cache_ttl_hours", 24)
        enable_usage_tracking = getattr(config, "enable_usage_tracking", True)

    provider = provider or _default_provider(request)
    blast_trend = request.metadata.get("blast_trend") if request.metadata else None
    metadata = request.metadata or {}
    system, user = build_analysis_prompt(
        results=request.results.get("comparisons", [])
        if isinstance(request.results, dict)
        else list(request.results),
        sections=request.sections,
        settings=request.settings,
        blast_trend=blast_trend,
        project_name=metadata.get("project_name", "Sin nombre"),
        fecha_informe=metadata.get("fecha_informe", "N/A"),
        seccion=metadata.get("seccion", "global"),
        banco=metadata.get("banco", "N/A"),
    )

    cache = DiskCache(cache_dir=cache_dir, ttl_s=cache_ttl_hours * 3600)
    cache_key = _cache_key(system + user, request.provider, request.model)

    if request.use_cache and enable_cache:
        cached = await cache.get(cache_key)
        if cached:
            for i, chunk in enumerate(cached):
                yield AIResponseChunk(
                    content=chunk, chunk_index=i, cached=True
                )
            return

    start = time.monotonic()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    accumulated: list[str] = []
    chunk_index = 0
    real_usage: AIUsage | None = None

    async for chunk in provider.stream(
        messages,
        model=request.model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    ):
        if chunk.usage is not None and not chunk.usage.is_synthetic:
            real_usage = chunk.usage
        if chunk.content:
            accumulated.append(chunk.content)
            yield AIResponseChunk(content=chunk.content, chunk_index=chunk_index)
            chunk_index += 1

    duration_ms = (time.monotonic() - start) * 1000

    if request.use_cache and enable_cache:
        await cache.put(cache_key, accumulated)

    if enable_usage_tracking:
        if real_usage is not None:
            real_usage.duration_ms = duration_ms
            yield AIResponseChunk(
                content="",
                finish_reason="stop",
                usage=real_usage,
                chunk_index=chunk_index + 1,
            )
        else:
            word_count = sum(len(c.split()) for c in accumulated)
            yield AIResponseChunk(
                content="",
                finish_reason="stop",
                usage=AIUsage(
                    prompt_tokens=0,
                    completion_tokens=word_count,
                    total_tokens=word_count,
                    duration_ms=duration_ms,
                    is_synthetic=True,
                ),
                chunk_index=chunk_index + 1,
            )


def _default_provider(request: AIRequest) -> "BaseProvider":
    from core.ai_v2.providers import ProviderRegistry

    ptype = ProviderType(request.provider)
    return ProviderRegistry.get(ptype)