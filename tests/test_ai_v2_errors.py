"""Tests for core.ai_v2 error hierarchy."""
from __future__ import annotations

from core.ai_v2.errors import (
    AIError,
    CacheError,
    ContextTooLong,
    InvalidResponse,
    ProviderUnavailable,
    RateLimited,
)


def test_ai_error_basic():
    e = AIError("oops")
    assert str(e) == "oops"
    assert isinstance(e, Exception)


def test_provider_unavailable():
    e = ProviderUnavailable("server down")
    assert isinstance(e, AIError)
    assert str(e) == "server down"


def test_rate_limited_default_retry():
    e = RateLimited("too many requests")
    assert isinstance(e, AIError)
    assert e.retry_after_s == 0.0
    assert "too many requests" in str(e)


def test_rate_limited_with_retry_after():
    e = RateLimited(retry_after_s=42.5)
    assert e.retry_after_s == 42.5
    assert "42.5" in str(e)


def test_rate_limited_retry_coerced_to_float():
    e = RateLimited("msg", retry_after_s="15")
    assert e.retry_after_s == 15.0
    assert isinstance(e.retry_after_s, float)


def test_rate_limited_positive_retry_in_message():
    e = RateLimited(retry_after_s=30.0)
    assert "30.0" in str(e)


def test_context_too_long():
    e = ContextTooLong("prompt is 1M tokens")
    assert isinstance(e, AIError)


def test_invalid_response():
    e = InvalidResponse("not JSON")
    assert isinstance(e, AIError)


def test_cache_error():
    e = CacheError("disk full")
    assert isinstance(e, AIError)


def test_catch_all_ai_errors():
    errors = [
        ProviderUnavailable("a"),
        RateLimited("b"),
        ContextTooLong("c"),
        InvalidResponse("d"),
        CacheError("e"),
    ]
    for err in errors:
        try:
            raise err
        except AIError as caught:
            assert caught is err