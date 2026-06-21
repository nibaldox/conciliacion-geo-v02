"""Tests for core.ai_v2 configuration."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.ai_v2.config import AIConfig


def test_defaults():
    cfg = AIConfig(_env_file=None)
    assert cfg.default_model == "llama3.1:8b"
    assert cfg.temperature == 0.3
    assert cfg.max_tokens == 4096
    assert cfg.timeout_s == 120.0
    assert cfg.enable_cache is False
    assert cfg.cache_ttl_hours == 24
    assert cfg.cache_dir == ".ai_v2_cache"
    assert cfg.enable_usage_tracking is True
    assert cfg.max_requests_per_minute == 5
    assert cfg.max_tokens_per_minute == 100_000


def test_provider_normalization():
    cfg = AIConfig(default_provider="OLLAMA", _env_file=None)
    assert cfg.default_provider == "ollama"


def test_provider_validation_accepts_known():
    for p in ("ollama", "lmstudio", "openai", "minimax", "glm", "grok"):
        cfg = AIConfig(default_provider=p, _env_file=None)
        assert cfg.default_provider == p


def test_provider_validation_rejects_unknown():
    with pytest.raises(ValidationError) as exc_info:
        AIConfig(default_provider="not-a-provider", _env_file=None)
    assert "default_provider" in str(exc_info.value).lower()


def test_temperature_bounds():
    with pytest.raises(ValidationError):
        AIConfig(temperature=2.5, _env_file=None)
    with pytest.raises(ValidationError):
        AIConfig(temperature=-0.1, _env_file=None)


def test_max_tokens_positive():
    with pytest.raises(ValidationError):
        AIConfig(max_tokens=0, _env_file=None)


def test_cache_ttl_positive():
    with pytest.raises(ValidationError):
        AIConfig(cache_ttl_hours=0, _env_file=None)


def test_env_prefix(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("AI_V2_DEFAULT_MODEL=custom-model\nAI_V2_TEMPERATURE=0.7\n")
    cfg = AIConfig(_env_file=str(env_file))
    assert cfg.default_model == "custom-model"
    assert cfg.temperature == 0.7