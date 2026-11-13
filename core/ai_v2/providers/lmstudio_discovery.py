"""Loaded-model discovery for the LM Studio chat provider.

LM Studio exposes two local REST surfaces that report which models are
actually LOADED (in memory), as opposed to merely downloaded:

* ``GET /api/v1/models`` — ``models[].loaded_instances[].id`` and
  ``models[].capabilities.trained_for_tool_use``. This is the preferred
  surface: each loaded instance already has the id accepted by
  ``/v1/chat/completions``.
* ``GET /api/v0/models`` — ``data[].state`` (``loaded`` /
  ``not-loaded``) and ``data[].capabilities`` (list, may include
  ``tool_use``). Used ONLY as a fallback for older LM Studio builds.

``GET /v1/models`` is deliberately NOT used: it lists every downloaded
model and says nothing about what is loaded.

Everything here is presentation-free and fail-closed: only loaded chat
instances are returned, ids are bounded/cleaned, and NO base URL, token
or raw upstream error ever reaches the payload. Requests carry the SAME
``LMSTUDIO_API_KEY`` the chat/report provider uses (never logged or
echoed). Redirects are not followed and environment proxies are ignored
so the discovery stays on the configured provider endpoint.
"""
from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass

import httpx

from core.ai_v2.providers.registry import (
    ProviderType,
    resolve_api_key,
    resolve_base_url,
)

logger = logging.getLogger(__name__)

DISCOVERY_TIMEOUT_ENV = "CONCILIACION_LMSTUDIO_DISCOVERY_TIMEOUT_S"
"""Optional discovery timeout in seconds (bounded, default 1.5)."""

DEFAULT_TIMEOUT_S = 1.5
MIN_TIMEOUT_S = 0.1
MAX_TIMEOUT_S = 5.0

MAX_MODELS = 50
MAX_ID_LENGTH = 200
MAX_LABEL_LENGTH = 120

CHAT_MODEL_TYPES = frozenset({"llm", "vlm", "chat"})
"""LM Studio model types that can serve chat completions.

Embedding/reranker models are loaded instances too, but they cannot run
the conversational agent; offering them would produce a model that looks
selectable and then fails on the first turn.
"""

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_SUPPORTED = "not_supported"
STATUS_DISABLED = "disabled"

_UNSUPPORTED_STATUS = frozenset({404, 405, 501})
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class LoadedModel:
    """One loaded chat instance, safe to show in the UI."""

    id: str
    label: str | None
    tool_use: bool | None


@dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of one discovery attempt (never carries URLs or errors)."""

    status: str
    source: str | None
    models: tuple[LoadedModel, ...]

    def as_payload(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "models": [
                {"id": m.id, "label": m.label, "tool_use": m.tool_use}
                for m in self.models
            ],
        }


def bounded_timeout(value: object) -> float:
    """Clamp a timeout to the safe range; non-finite values are rejected.

    ``float('nan')``/``float('inf')`` compare false against BOTH bounds
    and would otherwise reach ``httpx.Timeout`` as an unusable value, so
    they fall back to the default instead of leaking into the client.
    """
    try:
        timeout = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_S
    if not math.isfinite(timeout):
        return DEFAULT_TIMEOUT_S
    return max(MIN_TIMEOUT_S, min(timeout, MAX_TIMEOUT_S))


def discovery_timeout_s() -> float:
    """Read the bounded discovery timeout from the environment."""
    raw = os.environ.get(DISCOVERY_TIMEOUT_ENV)
    if raw is None:
        return DEFAULT_TIMEOUT_S
    return bounded_timeout(raw.strip())


def _auth_headers(api_key: str | None) -> dict[str, str]:
    """Authorization header for the provider's own API key (if any)."""
    key = resolve_api_key(ProviderType.LMSTUDIO) if api_key is None else api_key
    key = key.strip() if isinstance(key, str) else ""
    return {"Authorization": f"Bearer {key}"} if key else {}


def discovery_root(base_url: str | None) -> str | None:
    """Derive the LM Studio server root from the configured base URL.

    ``http://host:1234/v1`` -> ``http://host:1234``; the ``/v1`` suffix is
    the OpenAI-compatible surface, while discovery lives under ``/api``.
    Only http/https URLs with a host are accepted (no file:, no
    userinfo), so a malformed configuration can never become a local
    file read or a credentialed request.
    """
    if not base_url:
        return None
    try:
        parts = httpx.URL(base_url.strip())
    except (httpx.InvalidURL, ValueError):
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if not parts.host:
        return None
    if parts.userinfo:
        return None
    path = parts.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    root = str(
        httpx.URL(
            scheme=parts.scheme,
            host=parts.host,
            port=parts.port,
            path=path or "/",
        )
    )
    if path in ("", "/"):
        root = root.rstrip("/")
    return root


def _clean_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _CONTROL_CHARS.search(text):
        return None
    if len(text) > limit:
        return None
    return text


def _clean_model_id(value: object) -> str | None:
    return _clean_text(value, MAX_ID_LENGTH)


def _dedupe(models: list[LoadedModel]) -> list[LoadedModel]:
    seen: set[str] = set()
    unique: list[LoadedModel] = []
    for model in models:
        if model.id in seen:
            continue
        seen.add(model.id)
        unique.append(model)
        if len(unique) >= MAX_MODELS:
            break
    return unique


def parse_models_v1(payload: object) -> list[LoadedModel] | None:
    """Parse ``/api/v1/models``; ``None`` means the shape is unusable."""
    if not isinstance(payload, dict):
        return None
    entries = payload.get("models")
    if not isinstance(entries, list):
        return None
    models: list[LoadedModel] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") not in CHAT_MODEL_TYPES:
            continue
        instances = entry.get("loaded_instances")
        if not isinstance(instances, list):
            continue
        capabilities = entry.get("capabilities")
        tool_use: bool | None = None
        if isinstance(capabilities, dict) and isinstance(
            capabilities.get("trained_for_tool_use"), bool
        ):
            tool_use = capabilities["trained_for_tool_use"]
        label = _clean_text(entry.get("display_name"), MAX_LABEL_LENGTH) or _clean_text(
            entry.get("key"), MAX_LABEL_LENGTH
        )
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            model_id = _clean_model_id(instance.get("id"))
            if model_id is None:
                continue
            models.append(LoadedModel(id=model_id, label=label, tool_use=tool_use))
    return _dedupe(models)


def parse_models_v0(payload: object) -> list[LoadedModel] | None:
    """Parse ``/api/v0/models``; ``None`` means the shape is unusable."""
    if not isinstance(payload, dict):
        return None
    entries = payload.get("data")
    if not isinstance(entries, list):
        return None
    models: list[LoadedModel] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("state") != "loaded":
            continue
        if entry.get("type") not in CHAT_MODEL_TYPES:
            continue
        model_id = _clean_model_id(entry.get("id"))
        if model_id is None:
            continue
        capabilities = entry.get("capabilities")
        tool_use: bool | None = None
        if isinstance(capabilities, list):
            tool_use = "tool_use" in capabilities
        models.append(LoadedModel(id=model_id, label=None, tool_use=tool_use))
    return _dedupe(models)


async def _fetch_models(
    client: httpx.AsyncClient, url: str, parser
) -> tuple[str, list[LoadedModel] | None]:
    """Fetch one endpoint: (``ok``|``unsupported``|``error``, models|None).

    ``unsupported`` means the server ANSWERED but does not expose this
    shape (404/405/501, invalid JSON or an unusable body): the other LM
    Studio fallback surface may still work. ``error`` is a transport
    failure, redirect or any other HTTP status and makes the host
    effectively unreachable for discovery.
    """
    try:
        response = await client.get(url)
    except Exception:
        logger.debug("LM Studio model discovery request failed")
        return "error", None
    if response.status_code in _UNSUPPORTED_STATUS:
        return "unsupported", None
    if response.status_code != 200:
        logger.debug(
            "LM Studio model discovery answered HTTP %s", response.status_code
        )
        return "error", None
    try:
        payload = response.json()
    except ValueError:
        return "unsupported", None
    models = parser(payload)
    if models is None:
        return "unsupported", None
    return "ok", models


async def discover_lmstudio_models(
    base_url: str | None = None,
    *,
    timeout_s: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    api_key: str | None = None,
) -> DiscoveryResult:
    """Discover loaded chat instances on the configured LM Studio host.

    Tries ``/api/v1/models`` first and falls back to ``/api/v0/models``
    whenever v1 is not usable (unsupported OR a server/transport error):
    older builds and reverse proxies can fail v1 while still serving v0.
    ``not_supported`` is reported ONLY when the server answered and BOTH
    surfaces are unknown; any transport failure is ``unavailable``.

    The request reuses the provider's own API key, never follows
    redirects, never trusts proxy env vars and never raises: any failure
    is reported with an empty model list and no upstream details.
    """
    root = discovery_root(
        base_url if base_url is not None else resolve_base_url(ProviderType.LMSTUDIO)
    )
    if root is None:
        return DiscoveryResult(STATUS_UNAVAILABLE, None, ())
    timeout = (
        discovery_timeout_s() if timeout_s is None else bounded_timeout(timeout_s)
    )
    try:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers=_auth_headers(api_key),
        )
    except Exception:
        return DiscoveryResult(STATUS_UNAVAILABLE, None, ())
    async with client:
        status_v1, models = await _fetch_models(
            client, f"{root.rstrip('/')}/api/v1/models", parse_models_v1
        )
        if status_v1 == "ok":
            return DiscoveryResult(STATUS_OK, "v1", tuple(models or ()))
        status_v0, models = await _fetch_models(
            client, f"{root.rstrip('/')}/api/v0/models", parse_models_v0
        )
        if status_v0 == "ok":
            return DiscoveryResult(STATUS_OK, "v0", tuple(models or ()))
        if status_v1 == "unsupported" and status_v0 == "unsupported":
            return DiscoveryResult(STATUS_NOT_SUPPORTED, None, ())
        return DiscoveryResult(STATUS_UNAVAILABLE, None, ())
