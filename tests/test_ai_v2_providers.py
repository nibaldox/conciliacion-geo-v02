"""Tests for core.ai_v2 provider registry and OpenAI-compatible wrapper."""
from __future__ import annotations

import os

import pytest

from core.ai_v2.providers import (
    PROVIDER_PRESETS,
    ProviderRegistry,
    ProviderType,
)
from core.ai_v2.providers.openai_compat import OpenAICompatibleProvider


def test_provider_type_values():
    assert ProviderType.OLLAMA.value == "ollama"
    assert ProviderType.LMSTUDIO.value == "lmstudio"
    assert ProviderType.OPENAI.value == "openai"
    assert ProviderType.MINIMAX.value == "minimax"
    assert ProviderType.GLM.value == "glm"
    assert ProviderType.GROK.value == "grok"


def test_list_providers():
    names = ProviderRegistry.list_providers()
    assert "ollama" in names
    assert "grok" in names
    assert len(names) == 6


def test_get_default_model():
    assert ProviderRegistry.get_default_model(ProviderType.OLLAMA) == "llama3.1:8b"
    assert ProviderRegistry.get_default_model(ProviderType.OPENAI) == "gpt-4o-mini"
    assert ProviderRegistry.get_default_model(ProviderType.GLM) == "glm-5.2"
    assert ProviderRegistry.get_default_model(ProviderType.GROK) == "grok-4.20"


def test_provider_presets_have_base_url_and_default_model():
    for ptype, preset in PROVIDER_PRESETS.items():
        assert "base_url" in preset, ptype
        assert "default_model" in preset, ptype
        assert preset["base_url"].startswith("http"), ptype


def test_get_provider_default_uses_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    p = ProviderRegistry.get(ProviderType.OPENAI)
    assert isinstance(p, OpenAICompatibleProvider)
    assert p._client.api_key == "sk-test-123"
    assert p.name == "openai"


def test_get_provider_explicit_key():
    p = ProviderRegistry.get(ProviderType.OPENAI, api_key="sk-explicit")
    assert p._client.api_key == "sk-explicit"


def test_get_provider_no_env_falls_back_to_placeholder(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    p = ProviderRegistry.get(ProviderType.OLLAMA)
    assert p._client.api_key == "not-needed"


def test_openai_compat_provider_init():
    p = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        name="ollama",
        timeout_s=60.0,
    )
    assert p.name == "ollama"
    assert p._client.api_key == "test-key"
    assert str(p._client.base_url).rstrip("/") == "http://localhost:11434/v1"


def test_openai_compat_provider_name_property():
    p = OpenAICompatibleProvider(base_url="http://x", name="custom")
    assert p.name == "custom"


def test_openai_compat_provider_default_timeout():
    p = OpenAICompatibleProvider(base_url="http://x")
    assert p._client.timeout == 120.0


def test_health_check_returns_false_on_connection_error():
    p = OpenAICompatibleProvider(base_url="http://localhost:1", name="dead")
    import asyncio
    result = asyncio.run(p.health_check())
    assert result is False


def test_list_models_returns_empty_on_error():
    p = OpenAICompatibleProvider(base_url="http://localhost:1", name="dead")
    import asyncio
    result = asyncio.run(p.list_models())
    assert result == []