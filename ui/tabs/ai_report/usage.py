"""Formateo puro de métricas de uso y costo para la pestaña IA v2."""
from __future__ import annotations

from core.ai_v2.models import AIUsage
from ui.tabs.ai_report.providers import (
    CLOUD_COMPLETION_RATE_USD_PER_TOKEN,
    CLOUD_PROMPT_RATE_USD_PER_TOKEN,
    is_local_provider,
)


def estimate_cost(provider_name: str, usage: AIUsage | None) -> float:
    """USD cost estimate.

    Uses usage.cost_usd when populated; otherwise a flat cloud rate
    ($0.10/1M prompt + $0.30/1M completion). Local providers cost $0.00.
    """
    if usage is None:
        return 0.0
    if usage.cost_usd is not None:
        return usage.cost_usd
    if is_local_provider(provider_name):
        return 0.0
    return round(
        usage.prompt_tokens * CLOUD_PROMPT_RATE_USD_PER_TOKEN
        + usage.completion_tokens * CLOUD_COMPLETION_RATE_USD_PER_TOKEN,
        4,
    )


def format_usage_summary(
    provider_name: str,
    usage: AIUsage | None,
    elapsed_s: float,
) -> str:
    """One-line token + cost summary."""
    if usage is None:
        return f"⏱️ {elapsed_s:.2f}s · sin métricas de uso"
    tps = (usage.completion_tokens / elapsed_s) if elapsed_s > 0 else 0.0
    if is_local_provider(provider_name):
        cost_str = "$0.0000 (local)"
    else:
        cost_str = f"${estimate_cost(provider_name, usage):.4f}"
    suffix = " (estimado)" if usage.is_synthetic else ""
    return (
        f"⏱️ {elapsed_s:.2f}s · "
        f"Tokens: {usage.prompt_tokens:,} in / "
        f"{usage.completion_tokens:,} out / "
        f"{usage.total_tokens:,} total · "
        f"{tps:.1f} tok/s · 💰 {cost_str}{suffix}"
    )
