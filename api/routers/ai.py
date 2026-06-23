"""AI router — exposes the core.ai_v2 agent over HTTP for the web frontend.

Endpoints:
    GET  /ai/health            Liveness probe: version + known providers
    GET  /ai/providers         List configured provider presets
    POST /ai/generate          Generate a full report (aggregated, non-streaming)
    POST /ai/generate/stream   Generate the report as an NDJSON chunk stream
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.ai_v2 import (
    AIError,
    AIRequest,
    AIResponseChunk,
    RateLimited,
    __version__,
    stream_report,
)
from core.ai_v2.config import AIConfig
from core.ai_v2.providers.registry import PROVIDER_PRESETS

logger = logging.getLogger(__name__)

_GENERATE_TIMEOUT_S = 120

# Redact common secret patterns before echoing error messages to clients.
_KEY_PATTERNS = re.compile(
    r"sk-[A-Za-z0-9_\-]{20,}"
    r"|Bearer\s+[A-Za-z0-9._\-]+"
    r"|api[_-]?key[=:]\s*\S+",
    re.IGNORECASE,
)


def _sanitize_error(msg: object) -> str:
    """Strip API-key-like substrings and cap length for client responses."""
    redacted = _KEY_PATTERNS.sub("[REDACTED]", str(msg))
    if len(redacted) > 300:
        redacted = redacted[:297] + "…"
    return redacted


router = APIRouter(prefix="/ai", tags=["ai"])


def _build_config(req: AIRequest) -> AIConfig:
    """Translate the per-request advanced overrides into an ``AIConfig``.

    The service reads temperature / max_tokens / timeout_s / cache toggles
    from the config object. Fields left as ``None`` on the request fall back
    to the ``AIConfig`` defaults, matching the previous behaviour.
    ``_env_file=None`` keeps pydantic-settings from reading a local ``.env``
    on every request.
    """
    kwargs: dict[str, object] = {"_env_file": None}
    if req.temperature is not None:
        kwargs["temperature"] = req.temperature
    if req.max_tokens is not None:
        kwargs["max_tokens"] = req.max_tokens
    if req.timeout_s is not None:
        kwargs["timeout_s"] = req.timeout_s
    kwargs["enable_cache"] = bool(req.use_cache)
    return AIConfig(**kwargs)


async def _stream_ndjson(req: AIRequest) -> AsyncIterator[str]:
    """Yield each ``AIResponseChunk`` as a compact JSON line (NDJSON).

    Errors raised by the agent mid-stream are surfaced as a terminal
    ``finish_reason='error'`` chunk so the client can react; this keeps
    the streaming contract uniform at the cost of HTTP-level status codes
    (a streaming response has already committed a 200 by then).
    """
    config = _build_config(req)
    try:
        async with asyncio.timeout(_GENERATE_TIMEOUT_S):
            async for chunk in stream_report(req, config=config):
                yield chunk.model_dump_json() + "\n"
    except RateLimited as exc:
        retry = int(exc.retry_after_s) if exc.retry_after_s > 0 else 60
        err = AIResponseChunk(
            content=_sanitize_error(exc),
            finish_reason="error",
            chunk_index=0,
        )
        yield err.model_dump_json() + "\n"
        logger.warning("AI stream rate-limited (retry after %ss)", retry)
    except TimeoutError:
        err = AIResponseChunk(
            content=f"AI generation timed out after {_GENERATE_TIMEOUT_S}s",
            finish_reason="error",
            chunk_index=0,
        )
        yield err.model_dump_json() + "\n"
    except AIError as exc:
        logger.warning("AI stream failed: %s", exc)
        err = AIResponseChunk(
            content=_sanitize_error(exc),
            finish_reason="error",
            chunk_index=0,
        )
        yield err.model_dump_json() + "\n"


@router.get("/health")
async def health() -> dict:
    """Liveness probe. No remote checks — just version + provider registry."""
    return {
        "status": "ok",
        "version": __version__,
        "providers": [p.value for p in PROVIDER_PRESETS],
    }


@router.get("/providers")
async def providers() -> dict:
    """Return the list of configured provider preset names."""
    return {"providers": [p.value for p in PROVIDER_PRESETS]}


@router.post("/generate", response_model=AIResponseChunk)
async def generate(req: AIRequest) -> AIResponseChunk:
    """Generate a full reconciliation report and return it as a single chunk.

    Internally consumes the streaming ``stream_report`` generator and
    accumulates all content before responding. This keeps the wire format
    identical to the streaming chunks the agent produces (``AIResponseChunk``)
    while avoiding SSE complexity on the API boundary. The per-request
    advanced overrides (temperature, max_tokens, timeout_s, cache) are wired
    through via an ``AIConfig`` built from the request body.
    """
    accumulated: list[str] = []
    last_usage = None
    config = _build_config(req)
    try:
        async with asyncio.timeout(_GENERATE_TIMEOUT_S):
            async for chunk in stream_report(req, config=config):
                if chunk.content:
                    accumulated.append(chunk.content)
                if chunk.usage is not None:
                    last_usage = chunk.usage
    except RateLimited as exc:
        retry = int(exc.retry_after_s) if exc.retry_after_s > 0 else 60
        raise HTTPException(
            status_code=429,
            detail=_sanitize_error(exc),
            headers={"Retry-After": str(retry)},
        )
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"AI generation timed out after {_GENERATE_TIMEOUT_S}s",
        )
    except AIError as exc:
        logger.warning("AI generate failed: %s", exc)
        raise HTTPException(status_code=502, detail=_sanitize_error(exc))

    return AIResponseChunk(
        content="".join(accumulated),
        finish_reason="stop",
        usage=last_usage,
        chunk_index=0,
    )


@router.post("/generate/stream")
async def generate_stream(req: AIRequest) -> StreamingResponse:
    """Generate the report and stream each chunk as a newline-delimited JSON.

    Same payload as ``POST /ai/generate``; the response body is a sequence of
    ``AIResponseChunk`` JSON objects, one per line. The terminal line carries
    ``finish_reason='stop'`` (success) or ``'error'`` (agent failure).
    """
    return StreamingResponse(
        _stream_ndjson(req),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
