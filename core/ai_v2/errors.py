"""Error hierarchy for the AI agent v2.

All errors raised by ``core.ai_v2.*`` derive from :class:`AIError`, so
callers can catch the entire family with a single ``except AIError:``
clause. Each subclass that carries extra state (currently only
:class:`RateLimited`) accepts the standard ``message`` first, followed
by keyword-only extras, and forwards the message to
``Exception.__init__`` so ``str(err)`` stays useful.
"""
from __future__ import annotations


class AIError(Exception):
    """Base class for every error raised by the AI agent v2."""


class ProviderUnavailable(AIError):
    """Raised when an AI provider is unreachable or returns no response.

    Typical causes: network failure, wrong ``base_url``, provider process
    not running, or an HTTP 5xx from the upstream endpoint.
    """


class RateLimited(AIError):
    """Raised when a per-user rate limit has been exceeded.

    Attributes:
        retry_after_s: Suggested wait time in seconds before retrying.
            Defaults to ``0.0`` when the upstream gives no guidance.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded.",
        *,
        retry_after_s: float = 0.0,
    ) -> None:
        self.retry_after_s = float(retry_after_s)
        suffix = f" Retry after {self.retry_after_s}s." if self.retry_after_s > 0 else ""
        super().__init__(f"{message}{suffix}")


class ContextTooLong(AIError):
    """Raised when the rendered prompt exceeds the model's context window."""


class InvalidResponse(AIError):
    """Raised when the provider response cannot be parsed into the expected shape."""


class CacheError(AIError):
    """Raised on non-fatal cache failures.

    Callers should log and continue rather than aborting the request,
    since a cache miss must not break report generation.
    """


__all__ = [
    "AIError",
    "ProviderUnavailable",
    "RateLimited",
    "ContextTooLong",
    "InvalidResponse",
    "CacheError",
]
