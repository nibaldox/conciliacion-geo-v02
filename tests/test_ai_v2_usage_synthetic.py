"""Tests for AIUsage.is_synthetic flag — Sprint 4 A5."""
from __future__ import annotations

from core.ai_v2.models import AIUsage


class TestAIUsageSynthetic:
    def test_default_is_synthetic_false(self):
        usage = AIUsage(
            prompt_tokens=10, completion_tokens=20, total_tokens=30
        )
        assert usage.is_synthetic is False

    def test_is_synthetic_can_be_set_true(self):
        usage = AIUsage(
            prompt_tokens=0,
            completion_tokens=150,
            total_tokens=150,
            is_synthetic=True,
        )
        assert usage.is_synthetic is True

    def test_is_synthetic_extras_forbidden(self):
        """extra=forbid in model_config must reject unknown fields."""
        from pydantic import ValidationError
        with __import__("pytest").raises(ValidationError):
            AIUsage(prompt_tokens=10, bogus_field=True)

    def test_usage_serializes_with_flag(self):
        usage = AIUsage(
            prompt_tokens=0, completion_tokens=5, total_tokens=5,
            is_synthetic=True,
        )
        # model_dump must include the new flag
        dumped = usage.model_dump()
        assert "is_synthetic" in dumped
        assert dumped["is_synthetic"] is True
