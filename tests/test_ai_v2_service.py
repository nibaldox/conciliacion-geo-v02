"""Tests for core.ai_v2 service.stream_report."""
from __future__ import annotations

import pytest

from core.ai_v2.config import AIConfig
from core.ai_v2.models import AIRequest, AIResponseChunk
from core.ai_v2.service import stream_report


class FakeProvider:
    def __init__(self, chunks: list[str], fail: bool = False):
        self._chunks = chunks
        self._fail = fail
        self.calls: list = []
        self.name = "fake"

    def stream(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})

        async def gen():
            for i, c in enumerate(self._chunks):
                if self._fail and i == 1:
                    raise RuntimeError("simulated LLM error")
                yield AIResponseChunk(content=c, chunk_index=i)

        return gen()


@pytest.mark.asyncio
async def test_stream_report_yields_chunks():
    provider = FakeProvider(["Hello ", "world", "!"])
    req = AIRequest(
        provider="ollama", model="m", results={"comparisons": []}
    )
    chunks = []
    async for c in stream_report(req, provider=provider):
        chunks.append(c)
    assert "".join(c.content for c in chunks if c.content) == "Hello world!"


@pytest.mark.asyncio
async def test_stream_report_sends_messages_to_provider():
    provider = FakeProvider(["ok"])
    req = AIRequest(
        provider="ollama", model="llama3.1", results={"comparisons": []}
    )
    async for _ in stream_report(req, provider=provider):
        pass
    assert len(provider.calls) == 1
    msgs = provider.calls[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "Ingeniero" in msgs[0]["content"]


@pytest.mark.asyncio
async def test_stream_report_respects_config_temperature():
    provider = FakeProvider(["x"])
    req = AIRequest(provider="ollama", model="m", results={})
    config = AIConfig(temperature=0.7, _env_file=None)
    async for _ in stream_report(req, provider=provider, config=config):
        pass
    assert provider.calls[0]["kwargs"]["temperature"] == 0.7


@pytest.mark.asyncio
async def test_stream_report_respects_config_max_tokens():
    provider = FakeProvider(["x"])
    req = AIRequest(provider="ollama", model="m", results={})
    config = AIConfig(max_tokens=512, _env_file=None)
    async for _ in stream_report(req, provider=provider, config=config):
        pass
    assert provider.calls[0]["kwargs"]["max_tokens"] == 512


@pytest.mark.asyncio
async def test_stream_report_emits_final_usage_chunk():
    provider = FakeProvider(["a", "b", "c"])
    req = AIRequest(provider="ollama", model="m", results={})
    config = AIConfig(_env_file=None)
    chunks = []
    async for c in stream_report(req, provider=provider, config=config):
        chunks.append(c)
    last = chunks[-1]
    assert last.finish_reason == "stop"
    assert last.usage is not None
    assert last.usage.completion_tokens > 0
    assert last.usage.duration_ms > 0


@pytest.mark.asyncio
async def test_stream_report_with_cache_hit_yields_cached(tmp_path):
    provider = FakeProvider(["alpha", "beta"])
    req = AIRequest(provider="ollama", model="m-cache-test", results={}, use_cache=True)
    config = AIConfig(enable_cache=True, cache_dir=str(tmp_path), _env_file=None)
    chunks_first = []
    async for c in stream_report(req, provider=provider, config=config):
        chunks_first.append(c)
    assert any(c.cached for c in chunks_first) is False
    assert provider.calls
    provider.calls.clear()
    chunks_second = []
    async for c in stream_report(req, provider=provider, config=config):
        chunks_second.append(c)
    assert any(c.cached for c in chunks_second) is True
    assert provider.calls == []


@pytest.mark.asyncio
async def test_stream_report_accepts_dict_request():
    provider = FakeProvider(["ok"])
    req_dict = {"provider": "ollama", "model": "m", "results": {}}
    chunks = []
    async for c in stream_report(req_dict, provider=provider):
        chunks.append(c)
    assert any(c.content == "ok" for c in chunks)


@pytest.mark.asyncio
async def test_stream_report_metadata_propagates_to_prompt():
    provider = FakeProvider(["x"])
    req = AIRequest(
        provider="ollama", model="m", results={},
        metadata={"project_name": "Mina-X", "seccion": "S-99"},
    )
    async for _ in stream_report(req, provider=provider):
        pass
    user_msg = provider.calls[0]["messages"][1]["content"]
    assert "Mina-X" in user_msg
    assert "S-99" in user_msg