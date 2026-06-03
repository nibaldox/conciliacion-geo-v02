"""
Optional rate limiting via slowapi.

Disabled by default — the user's daily Streamlit workflow must not be
affected. Enable by setting CONCILIACION_RATE_LIMIT_ENABLED=true (the
render.yaml already sets it to "true" with a generous 120 req/min
limit, so production gets DoS protection but local dev stays open).

slowapi is imported lazily — if it isn't installed in the current
environment, rate limiting silently no-ops and everything else keeps
working. The local Streamlit + FastAPI development flow does not
need slowapi.

When enabled, limits are applied per-client-IP. The X-Session-ID header
is NOT used for rate limiting because users can mint as many sessions
as they want. If you need per-user limits, switch to the API-key or
OAuth-based identifier once auth lands.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    return os.environ.get("CONCILIACION_RATE_LIMIT_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _per_minute_limit() -> str:
    n = os.environ.get("CONCILIACION_RATE_LIMIT_PER_MIN", "120").strip()
    try:
        n_int = int(n)
        return f"{max(1, n_int)}/minute"
    except ValueError:
        logger.warning("Invalid CONCILIACION_RATE_LIMIT_PER_MIN=%r, using default 120", n)
        return "120/minute"


def install_rate_limiter(app: FastAPI) -> Optional[Any]:
    """Install the rate limiter if enabled AND slowapi is importable.

    Returns the Limiter instance or None. None is returned in two cases:
      - feature flag off (CONCILIACION_RATE_LIMIT_ENABLED != true)
      - slowapi not installed in the current environment (no error)

    In both cases, requests pass through unrate-limited. Production
    deploys (Docker image, Render) include slowapi in requirements;
    local dev can install it optionally with `pip install slowapi`.
    """
    if not _is_enabled():
        logger.info("Rate limiting disabled (CONCILIACION_RATE_LIMIT_ENABLED != true)")
        return None

    try:
        from slowapi import Limiter
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.util import get_remote_address
    except ImportError:
        logger.warning(
            "CONCILIACION_RATE_LIMIT_ENABLED=true but slowapi is not installed. "
            "Run `pip install slowapi` or set CONCILIACION_RATE_LIMIT_ENABLED=false."
        )
        return None

    limit = _per_minute_limit()
    limiter = Limiter(key_func=get_remote_address, default_limits=[limit])
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):  # type: ignore[unused-ignore]
        logger.warning(
            "Rate limit exceeded: %s %s from %s",
            request.method,
            request.url.path,
            request.client.host if request.client else "?",
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Try again in a minute.",
                "limit": str(exc.detail),
            },
            headers={"Retry-After": "60"},
        )

    logger.info("Rate limiting enabled: %s per IP", limit)
    return limiter
