"""API key authentication middleware.

If the env var ``CONCILIACION_API_KEY`` is set, all requests to
``/api/v1/*`` must include the same value in the ``X-API-Key`` header.
Public endpoints (``/api/v1/health``, ``/api/v1/live``, ``/api/v1/ready``,
and the OpenAPI/docs assets) are always exempt.

Behaviour:

- CORS preflight requests (``OPTIONS`` + ``Origin`` +
  ``Access-Control-Request-Method``) are passed through to the CORS
  middleware — browsers cannot attach the API key to a preflight, and the
  preflight response never executes a route handler. Real requests keep
  the full check.
- Env var unset + ``CONCILIACION_AUTH_REQUIRED`` unset/false → middleware
  is a no-op (local dev). A warning is logged once at install time.
- Env var unset + ``CONCILIACION_AUTH_REQUIRED`` set to a truthy value →
  fail closed: protected endpoints answer 503 with an explicit
  misconfiguration diagnostic; public health endpoints stay available.
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
_REQUIRED_ENV_VAR = "CONCILIACION_AUTH_REQUIRED"
_TRUTHY_VALUES = ("1", "true", "yes", "on")

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


def _auth_required() -> bool:
    return os.environ.get(_REQUIRED_ENV_VAR, "false").strip().lower() in _TRUTHY_VALUES


def _is_cors_preflight(request: Request) -> bool:
    return (
        request.method == "OPTIONS"
        and "origin" in request.headers
        and "access-control-request-method" in request.headers
    )


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):
        if _is_cors_preflight(request):
            return await call_next(request)

        if not request.url.path.startswith("/api/") or _is_public(request.url.path):
            return await call_next(request)

        expected = os.environ.get(_ENV_VAR)
        if not expected:
            if _auth_required():
                logger.error(
                    "Rejected %s %s: %s is enabled but %s is not set",
                    request.method,
                    request.url.path,
                    _REQUIRED_ENV_VAR,
                    _ENV_VAR,
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": (
                            f"Authentication misconfigured: {_REQUIRED_ENV_VAR} "
                            f"is enabled but {_ENV_VAR} is not set; configure "
                            f"the API key or disable {_REQUIRED_ENV_VAR}"
                        )
                    },
                )
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

    The middleware reads ``CONCILIACION_API_KEY`` and
    ``CONCILIACION_AUTH_REQUIRED`` on every request, so it works even if
    the env vars are set after import time (useful for tests). When the
    key is unset the middleware passes through unless the required flag
    is enabled, in which case protected endpoints fail closed with 503.
    """
    app.add_middleware(ApiKeyAuthMiddleware)
    if os.environ.get(_ENV_VAR):
        logger.info("API key auth enabled (header: %s)", _HEADER)
    elif _auth_required():
        logger.error(
            "%s is enabled but %s is not set: protected endpoints will fail "
            "closed with 503 until configured.",
            _REQUIRED_ENV_VAR,
            _ENV_VAR,
        )
    else:
        logger.warning(
            "API key auth disabled: set %s env var to enable.",
            _ENV_VAR,
        )
