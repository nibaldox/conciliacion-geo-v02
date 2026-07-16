"""Tests puros para ui.tabs.ai_report.usage."""
from __future__ import annotations

from core.ai_v2.models import AIUsage
from ui.tabs.ai_report.usage import estimate_cost, format_usage_summary


class TestEstimateCost:
    def test_none_usage(self):
        assert estimate_cost("openai", None) == 0.0

    def test_local_provider(self):
        usage = AIUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        assert estimate_cost("ollama", usage) == 0.0

    def test_cloud_with_usage(self):
        usage = AIUsage(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            total_tokens=2_000_000,
        )
        cost = estimate_cost("openai", usage)
        assert cost == round(0.10 + 0.30, 4)

    def test_cloud_with_cost_usd(self):
        usage = AIUsage(cost_usd=1.23)
        assert estimate_cost("openai", usage) == 1.23


class TestFormatUsageSummary:
    def test_no_usage(self):
        line = format_usage_summary("openai", None, 1.5)
        assert "sin métricas de uso" in line
        assert "1.50s" in line

    def test_local_usage(self):
        usage = AIUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        line = format_usage_summary("ollama", usage, 1.0)
        assert "local" in line
        assert "100" in line
        assert "50.0 tok/s" in line

    def test_cloud_synthetic(self):
        usage = AIUsage(
            prompt_tokens=0,
            completion_tokens=100,
            total_tokens=100,
            is_synthetic=True,
        )
        line = format_usage_summary("openai", usage, 2.0)
        assert "estimado" in line
        assert "100" in line
        assert "50.0 tok/s" in line
