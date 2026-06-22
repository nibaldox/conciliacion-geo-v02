"""AI router — exposes the core.ai_v2 agent over HTTP for the web frontend.

Endpoints:
    GET  /ai/health       Liveness probe: version + known providers
    GET  /ai/providers     List configured provider presets
    POST /ai/generate      Generate a full report (aggregated, non-streaming)
"""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException

from core.ai_v2 import (
    AIError,
    AIRequest,
    AIResponseChunk,
    RateLimited,
    __version__,
    stream_report,
)
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
    while avoiding SSE complexity on the API boundary for now.
    """
    accumulated: list[str] = []
    last_usage = None
    try:
        async with asyncio.timeout(_GENERATE_TIMEOUT_S):
            async for chunk in stream_report(req):
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
