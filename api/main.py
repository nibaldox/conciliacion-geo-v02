"""
FastAPI application for Geotechnical Reconciliation (modular).
Routes are split across api/routers/ — this file wires them together.
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from api.database import init_db, cleanup_old_sessions
from api.middleware import install_health_endpoints, install_middleware
from api.middleware_ratelimit import install_rate_limiter
from api.routers import meshes, sections, process, export, settings, ai
from core.config import DEFAULTS, DEPLOY

logger = logging.getLogger(__name__)

# ── Logging setup (plain text locally, JSON in production) ────────────
logging.basicConfig(
    level=getattr(logging, DEPLOY.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s [%(funcName)s] %(message)s"
    if DEPLOY.log_format == "plain"
    else '{"ts":"%(asctime)s","lvl":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}',
)


# ---------------------------------------------------------------------------
# Observability — Sentry (opt-in via SENTRY_DSN)
# ---------------------------------------------------------------------------
#
# The Sentry SDK is imported lazily so environments without the
# dependency still work. When SENTRY_DSN is unset (the default for
# local dev), this is a no-op. Set the env var in Render / CI to
# enable error capture + performance monitoring.

_SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            release=os.environ.get("SENTRY_RELEASE", "conciliacion-api@dev"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            # Don't send PII (the user's mesh filenames contain
            # project names that the maintainer may not want
            # shared with Sentry's third-party processor).
            send_default_pii=False,
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
            ],
        )
        logger.info("Sentry enabled (dsn host: %s)", _SENTRY_DSN.split("@")[-1])
    except ImportError:
        logger.warning("SENTRY_DSN set but sentry-sdk not installed; pip install sentry-sdk[fastapi]")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to init Sentry: %s", exc)
else:
    logger.info("Sentry disabled (SENTRY_DSN not set)")


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
_cors_env = DEPLOY.cors_origins_env
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
    expose_headers=["X-Session-ID", "x-session-id"],
)



# ---------------------------------------------------------------------------
# Health check (kept here — lightweight, no router needed)
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# Production middleware (additive — request ID, access log, /ready /live,
# rate limiting). All opt-in via env vars; defaults preserve the original
# behaviour of local dev and the Streamlit workflow.
# ---------------------------------------------------------------------------

install_middleware(app, logger)
install_health_endpoints(
    app,
    is_ready=lambda: True,  # always ready when DB is up (init_db ran in lifespan)
)
install_rate_limiter(app)


# ---------------------------------------------------------------------------
# Routers — all mounted under /api/v1
# ---------------------------------------------------------------------------

app.include_router(meshes.router, prefix="/api/v1")
app.include_router(sections.router, prefix="/api/v1")
app.include_router(process.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Static mount: serve the React build at / when web/dist/ exists.
# This is the "portable" mode (Electron + sidecar) where the same process
# serves both the API and the SPA. Dev workflow (Vite on :5173) is
# unaffected because the React dev server runs separately.
# ---------------------------------------------------------------------------

from pathlib import Path
from fastapi.staticfiles import StaticFiles

_web_dist = Path(__file__).parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
