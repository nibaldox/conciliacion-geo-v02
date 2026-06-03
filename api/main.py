"""
FastAPI application for Geotechnical Reconciliation (modular).
Routes are split across api/routers/ — this file wires them together.
"""

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from api.database import init_db, cleanup_old_sessions
from api.routers import meshes, sections, process, export, settings, ai
from core.config import DEFAULTS


# ---------------------------------------------------------------------------
# Lifespan: init DB on startup, cleanup on shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    cleanup_old_sessions()


app = FastAPI(
    title="Conciliación Geotécnica API",
    version="2.0.0",
    description="API para análisis de conciliación geotécnica: Diseño vs As-Built",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Session middleware: X-Session-ID header → request.state.session_id
# ---------------------------------------------------------------------------

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        session_id = str(uuid.uuid4())
    request.state.session_id = session_id
    response: Response = await call_next(request)
    response.headers["X-Session-ID"] = session_id
    return response


# ---------------------------------------------------------------------------
# Body-size guard: reject oversized payloads before routers see them
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = DEFAULTS.max_upload_mb * 1024 * 1024


@app.middleware("http")
async def body_size_middleware(request: Request, call_next):
    """Reject requests whose Content-Length exceeds max_upload_mb.

    Acts as a defense-in-depth check; FastAPI/Starlette will still enforce
    per-route limits via its own mechanisms.
    """
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_UPLOAD_BYTES:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=413,
            content={
                "detail": (
                    f"Payload too large: {int(cl) / (1024 * 1024):.1f} MB "
                    f"exceeds limit of {DEFAULTS.max_upload_mb} MB"
                )
            },
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Default allow-list covers local dev (Streamlit :8501, Vite :5173, docker
# :80). Production deployments should set the CONCILIACION_CORS_ORIGINS env
# var to a comma-separated list of allowed origins. We do NOT use a wildcard
# with credentials=True — browsers reject that combination and it is also a
# CSRF risk.
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8501",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8501",
    "http://127.0.0.1:3000",
]
_cors_env = os.environ.get("CONCILIACION_CORS_ORIGINS", "").strip()
_allow_origins = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env
    else _DEFAULT_CORS_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check (kept here — lightweight, no router needed)
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# Routers — all mounted under /api/v1
# ---------------------------------------------------------------------------

app.include_router(meshes.router, prefix="/api/v1")
app.include_router(sections.router, prefix="/api/v1")
app.include_router(process.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
