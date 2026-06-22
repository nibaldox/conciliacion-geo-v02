"""API key authentication middleware.

If the env var ``CONCILIACION_API_KEY`` is set, all requests to
``/api/v1/*`` must include the same value in the ``X-API-Key`` header.
Public endpoints (``/api/v1/health``, ``/api/v1/live``, ``/api/v1/ready``,
and the OpenAPI/docs assets) are always exempt.

Behaviour:

- Env var unset → middleware is a no-op (local dev). A warning is
  logged once at install time so the operator notices the gap.
- Env var set + no header → 401
- Env var set + wrong header → 403
- Env var set + correct header → request proceeds

The comparison uses ``secrets.compare_digest`` to avoid timing
side-channels.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_HEADER = "X-API-Key"
_ENV_VAR = "CONCILIACION_API_KEY"

_PUBLIC_EXACT = frozenset({
    "/api/v1/health",
    "/api/v1/live",
    "/api/v1/ready",
})

_PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/assets/",
)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):
        expected = os.environ.get(_ENV_VAR)
        if not expected:
            return await call_next(request)

        if not request.url.path.startswith("/api/") or _is_public(request.url.path):
            return await call_next(request)

        provided = request.headers.get(_HEADER)
        if not provided:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-API-Key header"},
            )
        if not secrets.compare_digest(provided, expected):
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key"},
            )
        return await call_next(request)


def install_api_key_auth(app: FastAPI) -> None:
    """Install API key auth.

    The middleware reads ``CONCILIACION_API_KEY`` on every request, so
    it works even if the env var is set after import time (useful for
    tests). When the var is unset, requests pass through unchanged.
    """
    app.add_middleware(ApiKeyAuthMiddleware)
    if os.environ.get(_ENV_VAR):
        logger.info("API key auth enabled (header: %s)", _HEADER)
    else:
        logger.warning(
            "API key auth disabled: set %s env var to enable.",
            _ENV_VAR,
        )
