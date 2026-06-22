"""Tests for the AI router (api/routers/ai.py).

Covers health, providers, validation, error sanitization, and rate limiting.
The happy path (real stream_report end-to-end) is intentionally NOT tested
here — it requires a live API key and would be slow/flaky/expensive.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.ai_v2 import ProviderUnavailable, RateLimited


@pytest.fixture()
def client():
    """FastAPI TestClient (synchronous wrapper around the async app)."""
    return TestClient(app)


def test_health(client):
    """GET /ai/health returns 200 with status ok and provider list."""
    resp = client.get("/api/v1/ai/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert isinstance(body["providers"], list)
    assert len(body["providers"]) > 0


def test_providers(client):
    """GET /ai/providers returns a dict with a providers list."""
    resp = client.get("/api/v1/ai/providers")
    assert resp.status_code == 200
    body = resp.json()
    assert "providers" in body
    assert isinstance(body["providers"], list)


def test_generate_validation_error(client):
    """POST /ai/generate without required fields returns 422."""
    resp = client.post("/api/v1/ai/generate", json={})
    assert resp.status_code == 422


def test_generate_validation_bad_provider(client):
    """POST with an unknown provider name returns 422 (Pydantic rejects it)."""
    resp = client.post("/api/v1/ai/generate", json={
        "results": {},
        "provider": "bogus_provider",
        "model": "x",
    })
    assert resp.status_code == 422


def test_generate_provider_unavailable(client):
    """A provider error surfaces as 502 with a sanitized message."""
    with patch("api.routers.ai.stream_report") as mock:
        mock.side_effect = ProviderUnavailable(
            "Connection refused to ollama at localhost:11434"
        )
        resp = client.post("/api/v1/ai/generate", json={
            "results": {"comparisons": []},
            "provider": "ollama",
            "model": "llama3.1:8b",
        })
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "Traceback" not in detail
    assert "Connection refused" in detail


def test_generate_rate_limited(client):
    """RateLimited surfaces as 429 with a Retry-After header."""
    with patch("api.routers.ai.stream_report") as mock:
        mock.side_effect = RateLimited("Too many requests", retry_after_s=30)
        resp = client.post("/api/v1/ai/generate", json={
            "results": {},
            "provider": "ollama",
            "model": "llama3.1:8b",
        })
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_generate_sanitizes_api_keys(client):
    """Error messages must not leak API-key-like secrets."""
    with patch("api.routers.ai.stream_report") as mock:
        mock.side_effect = ProviderUnavailable(
            "Auth failed for key sk-1234567890abcdef1234567890abcdef"
        )
        resp = client.post("/api/v1/ai/generate", json={
            "results": {},
            "provider": "ollama",
            "model": "llama3.1:8b",
        })
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "sk-1234" not in detail
    assert "REDACTED" in detail
