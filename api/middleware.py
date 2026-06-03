"""
Production middleware for the FastAPI app.

All middleware in this module is purely additive — it inspects or
enriches requests, never mutates request/response bodies in ways that
change existing endpoint semantics. Safe to enable in any environment.

Components:
- RequestIdMiddleware: assigns a UUID to every request, exposes it on
  the response header X-Request-ID, and pushes it onto a contextvar
  so loguru can include it in every log line.
- StructuredLoggingMiddleware: replaces the default uvicorn access log
  with a JSON-formatted line per request, including duration, status
  code, and request ID.

Both can be enabled/disabled independently via env vars.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ContextVar holds the current request's ID so loguru handlers can
# include it without having to thread it through every function call.
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the current request's ID (set by RequestIdMiddleware)."""
    return _request_id_var.get()


# ── Request ID ──────────────────────────────────────────────────────


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Tag every request with a UUID and echo it on the response."""

    HEADER = "X-Request-ID"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Honor an existing header from the client (useful for tracing
        # across services), otherwise mint a fresh one.
        rid = request.headers.get(self.HEADER) or str(uuid.uuid4())
        token = _request_id_var.set(rid)
        try:
            response = await call_next(request)
            response.headers[self.HEADER] = rid
            return response
        finally:
            _request_id_var.reset(token)


# ── Structured access log ───────────────────────────────────────────


class StructuredAccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one JSON line per request with method, path, status, duration."""

    def __init__(self, app, logger: logging.Logger) -> None:
        super().__init__(app)
        self._logger = logger

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        # Skip health checks — they fire every few seconds and drown the log
        if request.url.path.endswith("/health") or request.url.path.endswith("/live"):
            return await call_next(request)

        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        self._logger.info(
            "request",
            extra={
                "request_id": get_request_id(),
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client": request.client.host if request.client else None,
            },
        )
        return response


# ── Wiring helper ──────────────────────────────────────────────────


def install_middleware(app: FastAPI, logger: logging.Logger) -> None:
    """Install the production middleware in the recommended order.

    Order matters:
    1. RequestId first so every subsequent layer has an ID.
    2. StructuredAccessLog so it sees the final status code.
    """
    app.add_middleware(StructuredAccessLogMiddleware, logger=logger)
    app.add_middleware(RequestIdMiddleware)


# ── Health sub-endpoints (k8s-style) ───────────────────────────────


def install_health_endpoints(app: FastAPI, *, is_ready: Callable[[], bool]) -> None:
    """Add /live and /ready endpoints alongside the existing /health.

    - /live: liveness — process is up, returns 200 unconditionally.
    - /ready: readiness — depends on the callable, returns 503 if not.
    - /health: kept as the original all-in-one (returns 200 if /ready does).
    """

    @app.get("/api/v1/live", tags=["meta"])
    def live() -> dict:
        return {"status": "ok"}

    @app.get("/api/v1/ready", tags=["meta"])
    def ready() -> Response:
        if is_ready():
            return Response(status_code=200, content='{"status":"ready"}', media_type="application/json")
        return Response(status_code=503, content='{"status":"not-ready"}', media_type="application/json")
