"""Tests puros para ui.tabs.ai_report.providers."""
from __future__ import annotations

import os

import pytest

from core.ai_v2.providers import ProviderType
from ui.tabs.ai_report.providers import (
    PROVIDER_ENV_VAR,
    get_default_model,
    get_provider,
    is_local_provider,
    provider_base_url,
    provider_env_var,
    provider_label,
    resolve_api_key,
)


class TestProviderCatalog:
    def test_provider_env_var_known(self):
        assert provider_env_var("openai") == "OPENAI_API_KEY"

    def test_provider_env_var_unknown(self):
        assert provider_env_var("unknown") == ""

    def test_provider_label_known(self):
        assert "OpenAI" in provider_label("openai")

    def test_provider_label_unknown(self):
        assert provider_label("unknown") == "unknown"

    def test_is_local_provider_ollama(self):
        assert is_local_provider("ollama") is True

    def test_is_local_provider_openai(self):
        assert is_local_provider("openai") is False

    def test_provider_base_url_openai(self):
        assert "openai.com" in provider_base_url("openai")


class TestResolveApiKey:
    def test_resolve_from_environment(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        ptype = ProviderType.OPENAI
        assert resolve_api_key(ptype, {}) == "env-key"
        monkeypatch.delenv("OPENAI_API_KEY")

    def test_resolve_from_session_state(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        ptype = ProviderType.OPENAI
        state = {"ai_v2_key_openai": "state-key"}
        assert resolve_api_key(ptype, state) == "state-key"

    def test_resolve_prefers_environment(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        ptype = ProviderType.OPENAI
        state = {"ai_v2_key_openai": "state-key"}
        assert resolve_api_key(ptype, state) == "env-key"
        monkeypatch.delenv("OPENAI_API_KEY")


class TestProviderInstances:
    def test_get_default_model_openai(self):
        assert get_default_model(ProviderType.OPENAI) == "gpt-4o-mini"

    def test_get_provider_without_key(self):
        provider = get_provider(ProviderType.OLLAMA)
        assert provider.name == "ollama"

    def test_get_provider_with_key(self):
        provider = get_provider(ProviderType.OPENAI, api_key="secret")
        assert provider.name == "openai"
