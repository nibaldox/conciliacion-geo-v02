"""AI router — streaming reports via SSE from local LLMs."""

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from core.ai_service import (
    stream_report,
    build_analysis_prompt,
    check_provider_health,
    get_available_models,
    PROVIDERS,
)
import api.database as db

router = APIRouter(prefix="/ai", tags=["ai"])


class AIReportRequest(BaseModel):
    provider: str = "ollama"  # "ollama" | "lmstudio"
    model: str = ""  # Empty = use default


class AIProviderStatus(BaseModel):
    ollama: dict
    lmstudio: dict


@router.get("/providers")
def list_providers(request: Request):
    """Check which AI providers are available."""
    session_id = db.get_or_create_session(request.state.session_id)

    return {
        "providers": {
            name: check_provider_health(name)
            for name in PROVIDERS
        },
        "default_provider": "ollama",
    }


@router.get("/models/{provider}")
def list_models(provider: str):
    """List available models for a provider."""
    if provider not in PROVIDERS:
        return {"models": [], "error": f"Unknown provider: {provider}"}
    models = get_available_models(provider)
    return {"provider": provider, "models": models}


@router.post("/report")
async def generate_report(request: Request, body: AIReportRequest):
    """Generate an AI report using SSE streaming."""
    session_id = db.get_or_create_session(request.state.session_id)

    # Get analysis data
    results = db.get_results(session_id)
    sections = db.get_sections(session_id)
    settings = db.get_settings(session_id)

    # Determine model
    provider_config = PROVIDERS.get(body.provider)
    if not provider_config:
        return {"error": f"Unknown provider: {body.provider}"}

    model = body.model or provider_config["default_model"]

    # Build prompt from data
    prompt = build_analysis_prompt(results, sections, settings)

    def event_stream():
        for chunk in stream_report(body.provider, model, prompt):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
