"""Tests for core.ai_v2 Pydantic models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.ai_v2.models import AIRequest, AIResponseChunk, AIUsage


def test_ai_usage_defaults():
    u = AIUsage()
    assert u.prompt_tokens == 0
    assert u.completion_tokens == 0
    assert u.total_tokens == 0
    assert u.duration_ms == 0.0
    assert u.cost_usd is None


def test_ai_usage_with_values():
    u = AIUsage(
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        duration_ms=125.5,
        cost_usd=0.001,
    )
    assert u.prompt_tokens == 10
    assert u.total_tokens == 30
    assert u.cost_usd == 0.001


def test_ai_response_chunk_minimal():
    c = AIResponseChunk(content="hello")
    assert c.content == "hello"
    assert c.finish_reason is None
    assert c.usage is None
    assert c.cached is False
    assert c.chunk_index == 0


def test_ai_response_chunk_with_usage():
    c = AIResponseChunk(
        content="",
        finish_reason="stop",
        usage=AIUsage(prompt_tokens=5, completion_tokens=10),
        cached=True,
        chunk_index=3,
    )
    assert c.finish_reason == "stop"
    assert c.usage.completion_tokens == 10
    assert c.cached is True
    assert c.chunk_index == 3


def test_ai_response_chunk_finish_reason_literal():
    with pytest.raises(ValidationError):
        AIResponseChunk(content="x", finish_reason="not_valid")
    c = AIResponseChunk(content="x", finish_reason="length")
    assert c.finish_reason == "length"


def test_ai_request_minimal():
    r = AIRequest(provider="ollama", model="llama3.1", results={})
    assert r.provider == "ollama"
    assert r.model == "llama3.1"
    assert r.stream is True
    assert r.use_cache is True
    assert r.metadata == {}
    assert r.sections is None
    assert r.settings is None


def test_ai_request_provider_normalization():
    r = AIRequest(provider="OLLAMA", model="x", results={})
    assert r.provider == "ollama"


def test_ai_request_provider_rejects_unknown():
    with pytest.raises(ValidationError):
        AIRequest(provider="bogus", model="x", results={})


def test_ai_request_extra_forbid():
    with pytest.raises(ValidationError) as exc:
        AIRequest(
            provider="ollama", model="x", results={}, made_up_field="value"
        )
    assert "made_up_field" in str(exc.value)


def test_ai_request_sections_and_settings():
    r = AIRequest(
        provider="ollama",
        model="m",
        results={},
        sections=[{"id": "S1"}],
        settings={"tolerance": 0.5},
        metadata={"project_name": "Test"},
    )
    assert r.sections == [{"id": "S1"}]
    assert r.settings == {"tolerance": 0.5}
    assert r.metadata == {"project_name": "Test"}