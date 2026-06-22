"""Tests for real token-usage propagation from OpenAI-compatible providers.

Sprint 5 A5 deep: the provider must request ``stream_options={"include_usage": True}``
and surface the real ``usage`` block emitted in the final stream chunk. When the
provider emits real usage, ``is_synthetic`` stays ``False``; when it does not,
the service falls back to the word-count estimate with ``is_synthetic=True``.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.ai_v2.models import AIRequest, AIResponseChunk, AIUsage
from core.ai_v2.providers.openai_compat import OpenAICompatibleProvider
from core.ai_v2.service import stream_report


def _chunk(content=None, usage=None):
    """Build a fake OpenAI ``ChatCompletionChunk`` via ``SimpleNamespace``.

    Mirrors the attributes the provider reads: ``choices[*].delta.content``
    and top-level ``usage``. The final ``include_usage`` chunk arrives with
    ``choices=[]`` and ``usage`` populated.
    """
    choices = []
    if content is not None:
        choices = [SimpleNamespace(delta=SimpleNamespace(content=content))]
    return SimpleNamespace(choices=choices, usage=usage)


async def _aiter(items):
    for item in items:
        yield item


async def _collect(gen):
    return [c async for c in gen]


def _make_provider(mock_create):
    """Build a provider whose ``_client.chat.completions.create`` is mocked."""
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=mock_create)
        )
    )
    provider._name = "test"
    return provider


class TestStreamOptionsIncludeUsage:
    def test_stream_options_include_usage_sent(self):
        """The provider must ask the API to include usage in the stream."""
        mock_create = AsyncMock(return_value=_aiter([]))
        provider = _make_provider(mock_create)

        asyncio.run(_collect(
            provider.stream([{"role": "user", "content": "hi"}], model="m")
        ))

        assert mock_create.call_args.kwargs.get("stream") is True
        assert (
            mock_create.call_args.kwargs.get("stream_options")
            == {"include_usage": True}
        )


class TestUsagePropagationFromProvider:
    def test_usage_propagated_from_provider(self):
        """When the final chunk carries ``usage``, the provider's last
        ``AIResponseChunk`` exposes those tokens with ``is_synthetic=False``."""
        usage = SimpleNamespace(
            prompt_tokens=42, completion_tokens=13, total_tokens=55
        )
        chunks = [
            _chunk("hello "),
            _chunk("world"),
            _chunk(usage=usage),
        ]
        mock_create = AsyncMock(return_value=_aiter(chunks))
        provider = _make_provider(mock_create)

        results = asyncio.run(_collect(
            provider.stream([{"role": "user", "content": "hi"}], model="m")
        ))

        assert [c.content for c in results[:-1]] == ["hello ", "world"]
        usage_chunk = results[-1]
        assert usage_chunk.usage is not None
        assert usage_chunk.usage.prompt_tokens == 42
        assert usage_chunk.usage.completion_tokens == 13
        assert usage_chunk.usage.total_tokens == 55
        assert usage_chunk.usage.is_synthetic is False


class TestWordCountFallback:
    def test_word_count_fallback_when_no_usage(self):
        """A provider that never emits ``usage`` keeps the word-count fallback
        with ``is_synthetic=True`` (no regression)."""

        class FakeProvider:
            name = "fake"

            async def stream(self, messages, *, model, temperature=0.3,
                             max_tokens=4096, timeout_s=120.0):
                yield AIResponseChunk(content="one two", chunk_index=0)
                yield AIResponseChunk(content="three", chunk_index=1)

        request = AIRequest(results={}, provider="ollama", model="m")
        results = asyncio.run(_collect(stream_report(request, provider=FakeProvider())))

        final = results[-1]
        assert final.usage is not None
        assert final.usage.is_synthetic is True
        assert final.usage.completion_tokens == 3
        assert final.usage.total_tokens == 3
        assert final.usage.prompt_tokens == 0
        assert final.finish_reason == "stop"


class TestIsSyntheticFlag:
    def test_is_synthetic_false_when_provider_emits_usage(self):
        """When the provider emits real usage, ``stream_report`` forwards it
        with ``is_synthetic=False`` and discards the empty usage-only chunk
        so it never reaches the UI as a content chunk."""

        class FakeProvider:
            name = "fake"

            async def stream(self, messages, *, model, temperature=0.3,
                             max_tokens=4096, timeout_s=120.0):
                yield AIResponseChunk(content="hi", chunk_index=0)
                yield AIResponseChunk(
                    content="",
                    chunk_index=1,
                    usage=AIUsage(
                        prompt_tokens=100,
                        completion_tokens=20,
                        total_tokens=120,
                    ),
                )

        request = AIRequest(results={}, provider="ollama", model="m")
        results = asyncio.run(_collect(stream_report(request, provider=FakeProvider())))

        final = results[-1]
        assert final.usage is not None
        assert final.usage.is_synthetic is False
        assert final.usage.prompt_tokens == 100
        assert final.usage.completion_tokens == 20
        assert final.usage.total_tokens == 120
        assert final.finish_reason == "stop"
        # The empty usage-only chunk must NOT surface as a content chunk.
        assert all(c.content for c in results[:-1])
        # duration_ms is filled in by the service (provider reports 0.0).
        assert final.usage.duration_ms >= 0.0
