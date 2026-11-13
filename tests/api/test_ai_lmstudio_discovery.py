"""Loaded-model discovery for the LM Studio chat provider.

Covers the real LM Studio REST surface (``GET /api/v1/models`` with
``loaded_instances`` and ``GET /api/v0/models`` with ``state``), the
v1→v0 fallback, bounded failures, redirect refusal and the additive
``chat_models`` contract of ``GET /ai/providers``. All HTTP is faked
with ``httpx.MockTransport``: no network, no real LM Studio.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

import api.routers.ai as ai_router
from core.ai_v2.providers import lmstudio_discovery
from core.ai_v2.providers.lmstudio_discovery import (
    DEFAULT_TIMEOUT_S,
    DiscoveryResult,
    LoadedModel,
    bounded_timeout,
    discover_lmstudio_models,
    discovery_root,
    discovery_timeout_s,
    parse_models_v0,
    parse_models_v1,
)

BASE = "http://lmstudio.test/v1"


def v1_body(*models: dict) -> dict:
    return {"models": list(models)}


def v0_body(*models: dict) -> dict:
    return {"data": list(models)}


def llm_model(
    key: str,
    *,
    instances: list[str] | None = None,
    model_type: str = "llm",
    tool_use: bool | None = True,
    display_name: str | None = None,
) -> dict:
    capabilities: dict = {}
    if tool_use is not None:
        capabilities["trained_for_tool_use"] = tool_use
    return {
        "key": key,
        "type": model_type,
        "display_name": display_name or key,
        "loaded_instances": [{"id": i} for i in (instances or [])],
        "capabilities": capabilities,
    }


def v0_model(
    model_id: str,
    *,
    state: str = "loaded",
    model_type: str = "llm",
    capabilities: list[str] | None = None,
) -> dict:
    entry: dict = {"id": model_id, "type": model_type, "state": state}
    if capabilities is not None:
        entry["capabilities"] = capabilities
    return entry


def make_transport(routes: dict[str, tuple[int, object]], calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        status, body = routes.get(request.url.path, (404, {"error": "not found"}))
        if isinstance(body, Exception):
            raise body
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


async def run_discovery(routes, calls, *, base_url: str = BASE):
    return await discover_lmstudio_models(
        base_url=base_url,
        timeout_s=0.5,
        transport=make_transport(routes, calls),
    )


@pytest.mark.asyncio
async def test_v1_lists_only_loaded_chat_instances():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (
                200,
                v1_body(
                    llm_model("alpha", instances=["alpha", "alpha:2"]),
                    llm_model("downloaded-only", instances=[]),
                    llm_model("embed", instances=["embed"], model_type="embedding"),
                    llm_model(
                        "vision",
                        instances=["vision"],
                        model_type="vlm",
                        tool_use=False,
                    ),
                ),
            )
        },
        calls,
    )

    assert result.status == "ok"
    assert result.source == "v1"
    assert [m.id for m in result.models] == ["alpha", "alpha:2", "vision"]
    assert result.models[0].tool_use is True
    assert result.models[0].label == "alpha"
    assert result.models[2].tool_use is False
    assert calls == ["http://lmstudio.test/api/v1/models"]


@pytest.mark.asyncio
async def test_v1_unsupported_falls_back_to_v0_loaded_only():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v0/models": (
                200,
                v0_body(
                    v0_model("chat-a", capabilities=["tool_use"]),
                    v0_model("chat-b", state="not-loaded", capabilities=["tool_use"]),
                    v0_model("embed", model_type="embeddings", capabilities=[]),
                    v0_model("rerank", model_type="rerank"),
                ),
            )
        },
        calls,
    )

    assert result.status == "ok"
    assert result.source == "v0"
    assert [m.id for m in result.models] == ["chat-a"]
    assert result.models[0].tool_use is True
    assert calls == [
        "http://lmstudio.test/api/v1/models",
        "http://lmstudio.test/api/v0/models",
    ]


@pytest.mark.asyncio
async def test_v1_malformed_body_falls_back_to_v0():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (200, {"unexpected": True}),
            "/api/v0/models": (200, v0_body(v0_model("chat-a"))),
        },
        calls,
    )

    assert result.status == "ok"
    assert result.source == "v0"
    assert [m.id for m in result.models] == ["chat-a"]


@pytest.mark.asyncio
async def test_v0_loaded_without_capabilities_reports_unknown_tool_use():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (404, {"error": "not found"}),
            "/api/v0/models": (200, v0_body(v0_model("chat-a"))),
        },
        calls,
    )

    assert [m.id for m in result.models] == ["chat-a"]
    assert result.models[0].tool_use is None


@pytest.mark.asyncio
async def test_both_endpoints_failing_is_unavailable_without_leaking_details():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (500, {"error": "boom at http://secret"}),
            "/api/v0/models": (500, {"error": "boom"}),
        },
        calls,
    )

    assert result.status == "unavailable"
    assert result.models == ()
    assert result.source is None
    payload = json.dumps(result.as_payload())
    assert "http" not in payload
    assert "secret" not in payload


@pytest.mark.asyncio
async def test_transport_timeout_is_unavailable():
    calls: list[str] = []
    result = await run_discovery(
        {"/api/v1/models": (0, httpx.ConnectTimeout("timeout"))},
        calls,
    )

    assert result.status == "unavailable"
    assert result.models == ()


@pytest.mark.asyncio
async def test_redirects_are_not_followed():
    calls: list[str] = []
    redirect = httpx.Response(
        302, headers={"Location": "http://lmstudio.test/api/v1/models-redirect"}
    )
    result = await run_discovery(
        {"/api/v1/models": (302, redirect)},
        calls,
    )

    assert result.status == "unavailable"
    assert calls == [
        "http://lmstudio.test/api/v1/models",
        "http://lmstudio.test/api/v0/models",
    ]


@pytest.mark.asyncio
async def test_v1_server_error_still_falls_back_to_v0():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (500, {"error": "boom"}),
            "/api/v0/models": (200, v0_body(v0_model("chat-a"))),
        },
        calls,
    )

    assert result.status == "ok"
    assert result.source == "v0"
    assert [m.id for m in result.models] == ["chat-a"]
    assert calls == [
        "http://lmstudio.test/api/v1/models",
        "http://lmstudio.test/api/v0/models",
    ]


@pytest.mark.asyncio
async def test_v1_transport_failure_still_falls_back_to_v0():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (0, httpx.ConnectError("refused")),
            "/api/v0/models": (200, v0_body(v0_model("chat-a"))),
        },
        calls,
    )

    assert result.status == "ok"
    assert result.source == "v0"
    assert [m.id for m in result.models] == ["chat-a"]


@pytest.mark.asyncio
async def test_non_finite_timeout_argument_never_breaks_discovery():
    calls: list[str] = []
    result = await run_discovery(
        {"/api/v1/models": (200, v1_body(llm_model("alpha", instances=["alpha"])))},
        calls,
    )
    assert result.status == "ok"

    result = await discover_lmstudio_models(
        base_url=BASE,
        timeout_s=float("nan"),
        transport=make_transport(
            {"/api/v1/models": (200, v1_body(llm_model("alpha", instances=["alpha"])))},
            calls,
        ),
    )
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_both_unknown_endpoints_are_not_supported_not_disconnected():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (404, {"error": "not found"}),
            "/api/v0/models": (405, {"error": "method not allowed"}),
        },
        calls,
    )

    assert result.status == "not_supported"
    assert result.models == ()
    assert result.source is None


@pytest.mark.asyncio
async def test_transport_failure_is_unavailable_not_not_supported():
    calls: list[str] = []
    result = await run_discovery(
        {
            "/api/v1/models": (0, httpx.ConnectError("refused")),
            "/api/v0/models": (404, {"error": "not found"}),
        },
        calls,
    )

    assert result.status == "unavailable"
    assert result.models == ()


@pytest.mark.asyncio
async def test_discovery_uses_the_provider_api_key_without_leaking_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LMSTUDIO_API_KEY", "secret-lmstudio-key")
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200, json=v1_body(llm_model("alpha", instances=["alpha"]))
        )

    result = await discover_lmstudio_models(
        base_url=BASE,
        timeout_s=0.5,
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "ok"
    assert seen["authorization"] == "Bearer secret-lmstudio-key"
    payload = json.dumps(result.as_payload())
    assert "secret-lmstudio-key" not in payload


def test_discovery_timeout_rejects_non_finite_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for raw in ("nan", "inf", "-inf", "Infinity", "1e999"):
        monkeypatch.setenv(lmstudio_discovery.DISCOVERY_TIMEOUT_ENV, raw)
        assert discovery_timeout_s() == DEFAULT_TIMEOUT_S

    monkeypatch.delenv(lmstudio_discovery.DISCOVERY_TIMEOUT_ENV, raising=False)
    for value in (float("nan"), float("inf"), float("-inf")):
        assert bounded_timeout(value) == DEFAULT_TIMEOUT_S
    assert bounded_timeout(-3.0) == lmstudio_discovery.MIN_TIMEOUT_S
    assert bounded_timeout(99.0) == lmstudio_discovery.MAX_TIMEOUT_S


@pytest.mark.asyncio
async def test_non_http_base_url_makes_no_request():
    calls: list[str] = []
    result = await discover_lmstudio_models(
        base_url="file:///etc/passwd/v1",
        timeout_s=0.5,
        transport=make_transport({}, calls),
    )

    assert result.status == "unavailable"
    assert calls == []


def test_discovery_root_strips_only_the_api_suffix():
    assert discovery_root("http://host:1234/v1") == "http://host:1234"
    assert discovery_root("http://host:1234/v1/") == "http://host:1234"
    assert discovery_root("http://host:1234") == "http://host:1234"
    assert discovery_root("https://host/lmstudio/v1") == "https://host/lmstudio"
    assert discovery_root("file:///tmp/v1") is None
    assert discovery_root("") is None


def test_parser_rejects_non_list_payloads():
    assert parse_models_v1({"models": "nope"}) is None
    assert parse_models_v1([]) is None
    assert parse_models_v0({"data": {}}) is None
    assert parse_models_v0(None) is None


def test_parser_drops_unusable_instance_ids():
    payload = v1_body(
        llm_model("ok", instances=["ok"]),
        llm_model("bad-control", instances=["bad\u0000id"]),
        llm_model("too-long", instances=["x" * 300]),
    )
    parsed = parse_models_v1(payload)
    assert [m.id for m in parsed or []] == ["ok"]


class _FakeDiscovery:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.result


def providers_body(client: TestClient) -> dict:
    resp = client.get("/api/v1/ai/providers")
    assert resp.status_code == 200
    return resp.json()


def enable_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ai_router.CHAT_FLAG_ENV, "true")
    monkeypatch.setenv(ai_router.LOCAL_ONLY_ENV, "1")
    monkeypatch.delenv(ai_router.LMSTUDIO_MODEL_ENV, raising=False)


def test_providers_auto_selects_the_single_loaded_instance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    enable_chat(monkeypatch)
    fake = _FakeDiscovery(
        DiscoveryResult(
            status="ok",
            source="v1",
            models=(LoadedModel(id="alpha:2", label="Alpha", tool_use=True),),
        )
    )
    monkeypatch.setattr(ai_router, "discover_lmstudio_models", fake)

    body = providers_body(client)

    assert fake.calls == 1
    assert body["chat_model"] == "alpha:2"
    assert body["chat_models"] == {
        "status": "ok",
        "source": "v1",
        "models": [{"id": "alpha:2", "label": "Alpha", "tool_use": True}],
        "selected": "alpha:2",
        "selected_source": "auto",
    }
    assert "http" not in json.dumps(body)


def test_providers_never_auto_selects_between_several_models(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    enable_chat(monkeypatch)
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(
                status="ok",
                source="v0",
                models=(
                    LoadedModel(id="alpha", label=None, tool_use=True),
                    LoadedModel(id="beta", label=None, tool_use=True),
                ),
            )
        ),
    )

    body = providers_body(client)

    assert body["chat_model"] == "loaded-model"
    assert body["chat_models"]["selected"] is None
    assert body["chat_models"]["selected_source"] is None
    assert [m["id"] for m in body["chat_models"]["models"]] == ["alpha", "beta"]


def test_providers_reports_zero_loaded_models_honestly(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    enable_chat(monkeypatch)
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(status="ok", source="v1", models=())
        ),
    )

    body = providers_body(client)

    assert body["chat_model"] == "loaded-model"
    assert body["chat_models"]["status"] == "ok"
    assert body["chat_models"]["models"] == []
    assert body["chat_models"]["selected"] is None


def test_providers_reports_disconnected_without_faking_connectivity(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    enable_chat(monkeypatch)
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(status="unavailable", source=None, models=())
        ),
    )

    body = providers_body(client)

    assert body["chat_models"]["status"] == "unavailable"
    assert body["chat_models"]["models"] == []
    assert body["chat_models"]["selected"] is None
    assert body["chat_model"] == "loaded-model"


def test_providers_override_wins_over_any_detected_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    enable_chat(monkeypatch)
    monkeypatch.setenv(ai_router.LMSTUDIO_MODEL_ENV, "server-pinned")
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(
                status="ok",
                source="v1",
                models=(
                    LoadedModel(id="alpha", label=None, tool_use=True),
                    LoadedModel(id="beta", label=None, tool_use=True),
                ),
            )
        ),
    )

    body = providers_body(client)

    assert body["chat_model"] == "server-pinned"
    assert body["chat_models"]["selected"] == "server-pinned"
    assert body["chat_models"]["selected_source"] == "override"


def test_providers_override_is_ignored_when_local_only_is_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_chat(monkeypatch)
    monkeypatch.setenv(ai_router.LOCAL_ONLY_ENV, "0")
    monkeypatch.setenv(ai_router.LMSTUDIO_MODEL_ENV, "server-pinned")
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(
                status="ok",
                source="v1",
                models=(LoadedModel(id="alpha", label=None, tool_use=True),),
            )
        ),
    )

    body = providers_body(client)

    assert body["chat_local_only"] is False
    assert body["chat_provider"] is None
    assert body["chat_model"] == "alpha"
    assert body["chat_models"]["selected"] == "alpha"
    assert body["chat_models"]["selected_source"] == "auto"


def test_providers_never_expose_the_placeholder_as_a_model_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_chat(monkeypatch)
    monkeypatch.setenv(
        ai_router.LMSTUDIO_MODEL_ENV, f"  {ai_router.LMSTUDIO_PLACEHOLDER_MODEL}  "
    )
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(
                status="ok",
                source="v1",
                models=(LoadedModel(id="alpha", label=None, tool_use=True),),
            )
        ),
    )

    body = providers_body(client)

    assert body["chat_model"] == "alpha"
    assert body["chat_models"]["selected"] == "alpha"
    assert body["chat_models"]["selected_source"] == "auto"


def test_providers_skips_discovery_when_chat_is_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ai_router.CHAT_FLAG_ENV, raising=False)
    monkeypatch.delenv(ai_router.LMSTUDIO_MODEL_ENV, raising=False)
    fake = _FakeDiscovery(AssertionError("must not be awaited"))
    monkeypatch.setattr(ai_router, "discover_lmstudio_models", fake)

    body = providers_body(client)

    assert fake.calls == 0
    assert body["chat_models"]["status"] == "disabled"
    assert body["chat_models"]["models"] == []
    assert body["chat_model"] == "loaded-model"


def test_providers_reflects_a_changing_loaded_model_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    class _SequenceDiscovery:
        def __init__(self, results):
            self.results = list(results)
            self.calls = 0

        async def __call__(self, *args, **kwargs):
            self.calls += 1
            index = min(self.calls - 1, len(self.results) - 1)
            return self.results[index]

    enable_chat(monkeypatch)
    fake = _SequenceDiscovery(
        [
            DiscoveryResult(
                status="ok",
                source="v1",
                models=(LoadedModel(id="alpha", label=None, tool_use=True),),
            ),
            DiscoveryResult(
                status="ok",
                source="v1",
                models=(
                    LoadedModel(id="alpha", label=None, tool_use=True),
                    LoadedModel(id="beta", label=None, tool_use=True),
                ),
            ),
            DiscoveryResult(status="unavailable", source=None, models=()),
        ]
    )
    monkeypatch.setattr(ai_router, "discover_lmstudio_models", fake)

    first = providers_body(client)
    assert first["chat_model"] == "alpha"
    assert first["chat_models"]["selected_source"] == "auto"

    second = providers_body(client)
    assert second["chat_model"] == "loaded-model"
    assert second["chat_models"]["selected"] is None
    assert len(second["chat_models"]["models"]) == 2

    third = providers_body(client)
    assert third["chat_models"]["status"] == "unavailable"
    assert third["chat_model"] == "loaded-model"
    assert fake.calls == 3


def test_providers_survives_an_unexpected_discovery_crash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _RaisingDiscovery:
        async def __call__(self, *args, **kwargs):
            raise RuntimeError("boom at http://secret")

    enable_chat(monkeypatch)
    monkeypatch.setattr(
        ai_router, "discover_lmstudio_models", _RaisingDiscovery()
    )

    body = providers_body(client)

    assert body["chat_models"]["status"] == "unavailable"
    assert body["chat_models"]["models"] == []
    assert body["chat_model"] == "loaded-model"
    assert "secret" not in json.dumps(body)


@pytest.mark.asyncio
async def test_placeholder_model_resolves_to_the_loaded_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    monkeypatch.setenv(ai_router.CHAT_FLAG_ENV, "true")
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(
                status="ok",
                source="v1",
                models=(LoadedModel(id="alpha:2", label=None, tool_use=True),),
            )
        ),
    )

    resolved = await ai_router._resolve_placeholder_chat_model(
        ai_router.LMSTUDIO_PLACEHOLDER_MODEL
    )
    assert resolved == "alpha:2"


@pytest.mark.asyncio
async def test_placeholder_model_without_a_loaded_model_is_a_clear_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    monkeypatch.setenv(ai_router.CHAT_FLAG_ENV, "true")
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(DiscoveryResult(status="ok", source="v1", models=())),
    )

    with pytest.raises(HTTPException) as excinfo:
        await ai_router._resolve_placeholder_chat_model(
            ai_router.LMSTUDIO_PLACEHOLDER_MODEL
        )
    assert excinfo.value.status_code == 400
    assert "modelo" in excinfo.value.detail.lower()


@pytest.mark.asyncio
async def test_placeholder_model_with_disconnected_lmstudio_is_a_clear_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from core.ai_v2.providers.lmstudio_discovery import DiscoveryResult

    monkeypatch.setenv(ai_router.CHAT_FLAG_ENV, "true")
    monkeypatch.setattr(
        ai_router,
        "discover_lmstudio_models",
        _FakeDiscovery(
            DiscoveryResult(status="unavailable", source=None, models=())
        ),
    )

    with pytest.raises(HTTPException) as excinfo:
        await ai_router._resolve_placeholder_chat_model(
            ai_router.LMSTUDIO_PLACEHOLDER_MODEL
        )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_concrete_model_ids_are_passed_through_without_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeDiscovery(AssertionError("must not be awaited"))
    monkeypatch.setattr(ai_router, "discover_lmstudio_models", fake)

    resolved = await ai_router._resolve_placeholder_chat_model("qwen3-32b")

    assert resolved == "qwen3-32b"
    assert fake.calls == 0


@pytest.mark.asyncio
async def test_real_http_round_trip_uses_the_provider_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    routes = {
        "/api/v1/models": (
            200,
            v1_body(llm_model("alpha", instances=["alpha"], display_name="Alpha")),
        )
    }
    monkeypatch.setenv(
        ai_router.LMSTUDIO_BASE_URL_ENV, "http://lmstudio.test/v1"
    )

    result = await discover_lmstudio_models(
        timeout_s=0.5, transport=make_transport(routes, calls)
    )

    assert result.status == "ok"
    assert [m.id for m in result.models] == ["alpha"]
    assert calls == ["http://lmstudio.test/api/v1/models"]
