"""Tests for the API key auth middleware (D3)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(api_isolated_db):
    """Build a TestClient against the isolated per-test SQLite DB.

    Depends on the shared ``api_isolated_db`` fixture so the ``sessions``
    table is created deterministically (remediación 3.3) — without this,
    ``TestClient(app)`` does not run the lifespan and ``init_db()`` is
    never called, leaving the schema empty and any endpoint that touches
    ``sessions`` failing with ``sqlite3.OperationalError: no such table``.
    """
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


# ---------------------------------------------------------------------------
# Unit B — CORS preflight passthrough + fail-closed auth semantics
# ---------------------------------------------------------------------------

CORS_ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    """Start every test in this module with both auth env vars cleared."""
    monkeypatch.delenv("CONCILIACION_API_KEY", raising=False)
    monkeypatch.delenv("CONCILIACION_AUTH_REQUIRED", raising=False)


def _preflight(client, path=PROTECTED, origin=CORS_ORIGIN):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-session-id",
        },
    )


def test_cors_preflight_allowed_when_api_key_enabled(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = _preflight(client)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == CORS_ORIGIN


def test_cors_preflight_from_disallowed_origin_is_not_allowed(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = _preflight(client, origin="http://evil.example.com")
    assert resp.status_code == 400
    assert resp.headers.get("access-control-allow-origin") is None


def test_preflight_passthrough_does_not_open_real_requests(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    assert _preflight(client).status_code == 200
    assert client.get(PROTECTED).status_code == 401
    assert client.get(PROTECTED, headers={"X-API-Key": "wrong-key"}).status_code == 403
    assert client.get(PROTECTED, headers={"X-API-Key": GOOD_KEY}).status_code == 200


def test_plain_options_without_preflight_headers_stays_protected(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.options(PROTECTED)
    assert resp.status_code == 401


def test_auth_required_without_key_fails_closed(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "true")
    resp = client.get(PROTECTED)
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "CONCILIACION_API_KEY" in detail
    assert "CONCILIACION_AUTH_REQUIRED" in detail


def test_auth_required_with_empty_key_fails_closed(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CONCILIACION_API_KEY", "")
    assert client.get(PROTECTED).status_code == 503


@pytest.mark.parametrize("flag_value", ["1", "true", "yes", "on", "TRUE"])
def test_auth_required_accepts_truthy_values(monkeypatch, client, flag_value):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", flag_value)
    assert client.get(PROTECTED).status_code == 503


def test_auth_required_without_key_keeps_health_public(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "true")
    for path in ("/api/v1/health", "/api/v1/live", "/api/v1/ready"):
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_auth_required_without_key_still_serves_preflight(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "true")
    resp = _preflight(client)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == CORS_ORIGIN


def test_auth_required_with_key_is_enforced(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    assert client.get(PROTECTED).status_code == 401
    assert client.get(PROTECTED, headers={"X-API-Key": GOOD_KEY}).status_code == 200


def test_auth_not_required_keeps_open_local_mode(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "false")
    resp = client.get(PROTECTED)
    assert resp.status_code not in (401, 403, 503)


@pytest.fixture()
def mini_probe():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from api.middleware_auth import ApiKeyAuthMiddleware

    app = FastAPI()
    hits = {"options": 0, "get": 0}

    @app.options("/api/v1/probe")
    def probe_options():
        hits["options"] += 1
        return {"handler": "options"}

    @app.get("/api/v1/probe")
    def probe_get():
        hits["get"] += 1
        return {"handler": "get"}

    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[CORS_ORIGIN],
        allow_credentials=True,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["X-API-Key"],
    )
    return TestClient(app), hits


def test_malformed_preflight_without_origin_does_not_execute_protected_options_handler(
    mini_probe, monkeypatch
):
    client, hits = mini_probe
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.options(
        "/api/v1/probe", headers={"Access-Control-Request-Method": "GET"}
    )
    assert resp.status_code == 401
    assert hits["options"] == 0


def test_malformed_preflight_without_origin_fails_closed_when_auth_required(
    mini_probe, monkeypatch
):
    client, hits = mini_probe
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "true")
    resp = client.options(
        "/api/v1/probe", headers={"Access-Control-Request-Method": "GET"}
    )
    assert resp.status_code == 503
    assert hits["options"] == 0


def test_true_preflight_is_answered_by_cors_and_never_reaches_handlers(
    mini_probe, monkeypatch
):
    client, hits = mini_probe
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    allowed = client.options(
        "/api/v1/probe",
        headers={"Origin": CORS_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == CORS_ORIGIN
    disallowed = client.options(
        "/api/v1/probe",
        headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert disallowed.status_code == 400
    assert disallowed.headers.get("access-control-allow-origin") is None
    assert hits["options"] == 0
    assert hits["get"] == 0


def test_main_app_malformed_preflight_without_origin_requires_auth(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.options(PROTECTED, headers={"Access-Control-Request-Method": "GET"})
    assert resp.status_code == 401


def test_missing_key_401_carries_cors_headers_for_allowed_origin(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get(PROTECTED, headers={"Origin": CORS_ORIGIN})
    assert resp.status_code == 401
    assert resp.headers.get("access-control-allow-origin") == CORS_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"
    assert resp.json()["detail"] == "Missing X-API-Key header"


def test_invalid_key_403_carries_cors_headers_for_allowed_origin(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get(
        PROTECTED, headers={"Origin": CORS_ORIGIN, "X-API-Key": "wrong-key-value"}
    )
    assert resp.status_code == 403
    assert resp.headers.get("access-control-allow-origin") == CORS_ORIGIN
    assert resp.json()["detail"] == "Invalid API key"
    assert GOOD_KEY not in resp.text
    assert "wrong-key-value" not in resp.text


def test_misconfigured_503_carries_cors_headers_for_allowed_origin(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_AUTH_REQUIRED", "true")
    resp = client.get(PROTECTED, headers={"Origin": CORS_ORIGIN})
    assert resp.status_code == 503
    assert resp.headers.get("access-control-allow-origin") == CORS_ORIGIN
    detail = resp.json()["detail"]
    assert "CONCILIACION_API_KEY" in detail
    assert "CONCILIACION_AUTH_REQUIRED" in detail


def test_cors_wrap_keeps_real_auth_enforcement(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    allowed = client.get(
        PROTECTED, headers={"Origin": CORS_ORIGIN, "X-API-Key": GOOD_KEY}
    )
    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == CORS_ORIGIN
    assert client.get(PROTECTED).status_code == 401
    assert client.get(PROTECTED, headers={"X-API-Key": "wrong"}).status_code == 403
    assert client.get(PROTECTED, headers={"X-API-Key": GOOD_KEY}).status_code == 200


def test_auth_error_for_disallowed_origin_stays_without_cors_headers(monkeypatch, client):
    monkeypatch.setenv("CONCILIACION_API_KEY", GOOD_KEY)
    resp = client.get(PROTECTED, headers={"Origin": "http://evil.example.com"})
    assert resp.status_code == 401
    assert resp.headers.get("access-control-allow-origin") is None
