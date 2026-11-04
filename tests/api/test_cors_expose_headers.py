from __future__ import annotations

import io

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api import database as db
from api.main import app
from api.routers import export as export_router
from api.schemas import ExportFilters


def run_immediate_coroutine(coroutine):
    while True:
        try:
            yielded = coroutine.send(None)
        except StopIteration as finished:
            return finished.value
        if yielded is not None:
            raise RuntimeError(f"ASGI request suspended on an unsupported awaitable: {yielded!r}")


def test_word_export_exposes_download_headers_to_allowed_origin(monkeypatch):
    monkeypatch.setattr(db, "get_or_create_session", lambda session_id: session_id)

    async def build_word_payload(*args):
        return io.BytesIO(b"test report"), ExportFilters()

    monkeypatch.setattr(export_router, "_run_in_executor", build_word_payload)
    monkeypatch.setattr(
        export_router, "StreamingResponse",
        lambda buffer, media_type, headers: Response(
            content=buffer.getvalue(), media_type=media_type, headers=headers,
        ),
    )

    export_app = FastAPI()
    export_app.include_router(export_router.router, prefix="/api/v1")
    cors_middleware = next(
        middleware for middleware in app.user_middleware
        if middleware.cls is CORSMiddleware
    )
    asgi_app = CORSMiddleware(export_app, **cors_middleware.kwargs)

    async def request_export():
        messages = []
        received_request = False

        async def receive():
            nonlocal received_request
            if received_request:
                return {"type": "http.disconnect"}
            received_request = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/export/word",
            "raw_path": b"/api/v1/export/word",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"origin", b"http://localhost:5173"), (b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {"session_id": "cors-test-session"},
        }
        await asgi_app(scope, receive, send)
        return messages

    messages = run_immediate_coroutine(request_export())
    response_start = next(message for message in messages if message["type"] == "http.response.start")
    response_headers = {key.decode().lower(): value.decode() for key, value in response_start["headers"]}
    exposed_headers = {
        header.strip().lower()
        for header in response_headers["access-control-expose-headers"].split(",")
    }

    assert response_start["status"] == 200
    assert response_headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "content-disposition" in exposed_headers
    assert "x-export-filters-applied" in exposed_headers
    assert response_headers["content-disposition"].startswith("attachment;")
    assert response_headers["x-export-filters-applied"]
