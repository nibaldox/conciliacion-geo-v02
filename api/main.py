"""
FastAPI application for Geotechnical Reconciliation (modular).
Routes are split across api/routers/ — this file wires them together.
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from api.database import init_db, cleanup_old_sessions
from api.routers import meshes, sections, process, export, settings, ai


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
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
