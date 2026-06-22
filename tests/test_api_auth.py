"""Tests for the API key auth middleware (D3)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from api.main import app
    return TestClient(app)


PROTECTED = "/api/v1/sections"
GOOD_KEY = "test-key-1234567890"


def test_no_auth_when_env_var_unset(monkeypatch, client):
    monkeypatch.delenv("CONCILIACION_API_KEY", raising=False)
    resp = client.get(PROTECTED)
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_auth_required_when_env_var_set(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get(PROTECTED)
    assert resp.status_code == 401
    assert "X-API-Key" in resp.json()["detail"]


def test_auth_with_correct_key(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get(PROTECTED, headers={"X-API-Key": GOOD_KEY})
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_auth_with_wrong_key(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get(PROTECTED, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 403


def test_health_endpoint_excluded(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.status_code != 401


def test_live_endpoint_excluded(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get("/api/v1/live")
    assert resp.status_code == 200


def test_docs_excluded(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get("/docs")
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_openapi_excluded(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get("/openapi.json")
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_post_protected_endpoint(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.post("/api/v1/ai/generate", json={})
    assert resp.status_code == 401


def test_uses_secrets_compare_digest(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get(PROTECTED, headers={"X-API-Key": "x" * 100})
    assert resp.status_code == 403
