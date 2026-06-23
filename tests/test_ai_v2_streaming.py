"""Backend tests for the AI v2 streaming / advanced-settings parity work (G12).

Covers:
- ``AIRequest`` accepts the new advanced / filters / blast_trend / stream fields.
- ``POST /ai/v1/ai/generate/stream`` returns newline-delimited JSON chunks.
- ``POST /ai/v1/ai/generate`` (non-streaming) still returns a single response.
- Per-request advanced overrides are forwarded to the provider via ``AIConfig``.

The agent itself is mocked so these stay fast / hermetic and need no live key.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import app
from core.ai_v2.config import AIConfig
from core.ai_v2.models import AIRequest, AIResponseChunk, AIUsage


def _fake_stream_factory(captured: list[AIConfig | None]):
    """Build an async-gen replacement for ``stream_report`` that records the
    config it was called with and emits a deterministic chunk sequence."""

    async def _fake_stream(
        req: AIRequest,
        *,
        provider: object | None = None,
        config: AIConfig | None = None,
    ):
        captured.append(config)
        yield AIResponseChunk(content="Hello ", chunk_index=0)
        yield AIResponseChunk(content="world", chunk_index=1)
        yield AIResponseChunk(
            content="",
            finish_reason="stop",
            usage=AIUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                duration_ms=42.0,
            ),
            chunk_index=2,
        )

    return _fake_stream


@pytest.fixture()
def client():
    return TestClient(app)


def test_ai_request_accepts_advanced_filters_blast_trend_stream():
    """All parity fields validate and default to None/True where appropriate."""
    req = AIRequest(
        provider="ollama",
        model="llama3.1",
        results={"comparisons": []},
        notes="nota operativa",
        context={"foo": "bar"},
        stream=False,
        use_cache=False,
        max_tokens=512,
        temperature=0.7,
        timeout_s=30.0,
        filters={"sector": ["N"], "section": ["S-01"], "bench": [1]},
        blast_trend={"pf_promedio": 0.42, "n_pozos_total": 12},
        metadata={"project_name": "Mina-X"},
    )
    assert req.notes == "nota operativa"
    assert req.context == {"foo": "bar"}
    assert req.stream is False
    assert req.use_cache is False
    assert req.max_tokens == 512
    assert req.temperature == 0.7
    assert req.timeout_s == 30.0
    assert req.filters["sector"] == ["N"]
    assert req.blast_trend["n_pozos_total"] == 12


def test_ai_request_advanced_defaults_are_none():
    """New optional fields default to None so existing callers keep working."""
    req = AIRequest(provider="ollama", model="m", results={})
    assert req.notes is None
    assert req.context is None
    assert req.max_tokens is None
    assert req.temperature is None
    assert req.timeout_s is None
    assert req.filters is None
    assert req.blast_trend is None
    # stream/use_cache keep their pre-existing defaults (pinned by other tests).
    assert req.stream is True
    assert req.use_cache is True


def test_ai_request_rejects_out_of_range_advanced():
    """Temperature must stay in [0, 2]; tokens/timeout must be positive."""
    with pytest.raises(ValidationError):
        AIRequest(
            provider="ollama", model="m", results={}, temperature=3.5
        )
    with pytest.raises(ValidationError):
        AIRequest(provider="ollama", model="m", results={}, max_tokens=0)
    with pytest.raises(ValidationError):
        AIRequest(provider="ollama", model="m", results={}, timeout_s=-1.0)


def test_generate_stream_returns_ndjson(client):
    """``POST /ai/generate/stream`` emits one JSON object per line."""
    captured: list[AIConfig | None] = []
    with patch(
        "api.routers.ai.stream_report",
        new=_fake_stream_factory(captured),
    ):
        resp = client.post(
            "/api/v1/ai/generate/stream",
            json={
                "results": {"comparisons": []},
                "provider": "ollama",
                "model": "llama3.1",
            },
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    lines = [ln for ln in resp.text.split("\n") if ln.strip()]
    assert len(lines) == 3
    first = AIResponseChunk.model_validate_json(lines[0])
    assert first.content == "Hello "
    last = AIResponseChunk.model_validate_json(lines[-1])
    assert last.finish_reason == "stop"
    assert last.usage is not None
    assert last.usage.total_tokens == 15


def test_generate_non_stream_returns_single_chunk(client):
    """``POST /ai/generate`` still aggregates into one ``AIResponseChunk``."""
    captured: list[AIConfig | None] = []
    with patch(
        "api.routers.ai.stream_report",
        new=_fake_stream_factory(captured),
    ):
        resp = client.post(
            "/api/v1/ai/generate",
            json={
                "results": {"comparisons": []},
                "provider": "ollama",
                "model": "llama3.1",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "Hello world"
    assert body["finish_reason"] == "stop"
    assert body["usage"]["total_tokens"] == 15


def test_generate_forwards_advanced_overrides_to_config(client):
    """Per-request temperature/max_tokens/timeout reach the provider config."""
    captured: list[AIConfig | None] = []
    with patch(
        "api.routers.ai.stream_report",
        new=_fake_stream_factory(captured),
    ):
        resp = client.post(
            "/api/v1/ai/generate",
            json={
                "results": {"comparisons": []},
                "provider": "ollama",
                "model": "llama3.1",
                "temperature": 0.9,
                "max_tokens": 256,
                "timeout_s": 45.0,
                "use_cache": False,
            },
        )

    assert resp.status_code == 200
    assert len(captured) == 1
    config = captured[0]
    assert config is not None
    assert config.temperature == 0.9
    assert config.max_tokens == 256
    assert config.timeout_s == 45.0
    assert config.enable_cache is False
