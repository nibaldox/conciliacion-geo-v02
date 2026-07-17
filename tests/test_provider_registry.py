"""Tests for ProviderRegistry.get_default_model env-var resolution."""
from __future__ import annotations

import pytest

from core.ai_v2.providers import (
    PROVIDER_PRESETS,
    ProviderRegistry,
    ProviderType,
)


def test_env_var_set_overrides_default(monkeypatch):
    monkeypatch.setenv(
        "CONCILIACION_OPENROUTER_DEFAULT_MODEL", "meta-llama/llama-3.3-70b:free"
    )
    assert (
        ProviderRegistry.get_default_model(ProviderType.OPENROUTER)
        == "meta-llama/llama-3.3-70b:free"
    )


def test_env_var_unset_uses_preset_default(monkeypatch):
    monkeypatch.delenv("CONCILIACION_OPENROUTER_DEFAULT_MODEL", raising=False)
    assert (
        ProviderRegistry.get_default_model(ProviderType.OPENROUTER)
        == PROVIDER_PRESETS[ProviderType.OPENROUTER]["default_model"]
    )


def test_env_var_blank_falls_back_to_preset(monkeypatch):
    monkeypatch.setenv("CONCILIACION_OPENROUTER_DEFAULT_MODEL", "   ")
    assert (
        ProviderRegistry.get_default_model(ProviderType.OPENROUTER)
        == PROVIDER_PRESETS[ProviderType.OPENROUTER]["default_model"]
    )


def test_env_var_value_is_stripped(monkeypatch):
    monkeypatch.setenv(
        "CONCILIACION_OPENAI_DEFAULT_MODEL", "  gpt-4o  "
    )
    assert (
        ProviderRegistry.get_default_model(ProviderType.OPENAI) == "gpt-4o"
    )


@pytest.mark.parametrize(
    "provider_type",
    [
        ProviderType.OLLAMA,
        ProviderType.OPENAI,
        ProviderType.OPENROUTER,
        ProviderType.MINIMAX,
        ProviderType.GLM,
        ProviderType.GROK,
    ],
)
def test_env_var_applies_to_multiple_providers(monkeypatch, provider_type):
    env_var = f"CONCILIACION_{provider_type.value.upper()}_DEFAULT_MODEL"
    expected = f"custom-model-for-{provider_type.value}"
    monkeypatch.setenv(env_var, expected)
    assert ProviderRegistry.get_default_model(provider_type) == expected


@pytest.mark.parametrize(
    "provider_type",
    [
        ProviderType.OLLAMA,
        ProviderType.LMSTUDIO,
        ProviderType.OPENAI,
        ProviderType.OPENROUTER,
        ProviderType.MINIMAX,
        ProviderType.GLM,
        ProviderType.GROK,
    ],
)
def test_no_env_returns_preset_default_for_every_provider(
    monkeypatch, provider_type
):
    monkeypatch.delenv(
        f"CONCILIACION_{provider_type.value.upper()}_DEFAULT_MODEL",
        raising=False,
    )
    assert ProviderRegistry.get_default_model(provider_type) == (
        PROVIDER_PRESETS[provider_type]["default_model"]
    )


def test_env_var_set_on_one_provider_does_not_affect_others(monkeypatch):
    monkeypatch.setenv("CONCILIACION_OPENAI_DEFAULT_MODEL", "gpt-4o")
    monkeypatch.delenv(
        "CONCILIACION_OPENROUTER_DEFAULT_MODEL", raising=False
    )
    assert (
        ProviderRegistry.get_default_model(ProviderType.OPENAI) == "gpt-4o"
    )
    assert (
        ProviderRegistry.get_default_model(ProviderType.OPENROUTER)
        == PROVIDER_PRESETS[ProviderType.OPENROUTER]["default_model"]
    )


def test_public_signature_unchanged():
    """ProviderRegistry.get_default_model stays a classmethod taking one ProviderType.

    The brief forbids changing the public API. We assert: (1) it is still a
    classmethod, (2) calling it positionally with a ProviderType still returns
    a str — which is what every caller relied on.
    """
    # (1) Still a classmethod: the descriptor binds ``cls`` automatically.
    assert ProviderRegistry.get_default_model.__self__ is ProviderRegistry

    # (2) Public call contract is unchanged: positional ProviderType -> str.
    result = ProviderRegistry.get_default_model(ProviderType.OPENROUTER)
    assert isinstance(result, str)
    assert result == PROVIDER_PRESETS[ProviderType.OPENROUTER]["default_model"]


def test_does_not_break_existing_callers():
    """Smoke-check that positional call sites in the codebase still work."""
    for ptype in ProviderType:
        model = ProviderRegistry.get_default_model(ptype)
        assert isinstance(model, str)
        assert model  # non-empty
