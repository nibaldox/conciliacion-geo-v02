import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import core.config as config

import api.database as db
from api._async_db import run_db

router = APIRouter(prefix="/session", tags=["session"])
logger = logging.getLogger(__name__)


def require_session_list_enabled() -> None:
    if not config.DEPLOY.session_list_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/list", dependencies=[Depends(require_session_list_enabled)])
async def list_sessions(limit: int = Query(50, ge=1, le=200)) -> dict:
    deploy = config.DEPLOY
    sessions = await run_db(db.list_recent_sessions, limit)
    valid_sessions = []
    for session in sessions:
        try:
            created = datetime.fromisoformat(session["created_at"])
            last_used = datetime.fromisoformat(session["last_used_at"])
            created = (created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created.astimezone(timezone.utc))
            last_used = (last_used.replace(tzinfo=timezone.utc) if last_used.tzinfo is None else last_used.astimezone(timezone.utc))
            expires = last_used + timedelta(days=deploy.session_ttl_days)
        except (ValueError, TypeError, OverflowError):
            logger.warning("Invalid timestamp for session %s", session["session_id"])
            continue
        session["created_at"] = created.isoformat().replace("+00:00", "Z")
        session["last_used_at"] = last_used.isoformat().replace("+00:00", "Z")
        session["expires_at"] = expires.isoformat().replace("+00:00", "Z")
        valid_sessions.append(session)
    return {"ttl_days": deploy.session_ttl_days, "sessions": valid_sessions}


@router.get("/recovery")
async def recover_session(request: Request) -> dict[str, str | None]:
    session_id = request.state.session_id
    if not await run_db(db.session_exists, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    await run_db(db.touch_session, session_id)
    meshes = await run_db(db.get_all_meshes, session_id)
    mesh_ids = {mesh["type"]: mesh["id"] for mesh in meshes}
    return {
        "session_id": session_id,
        "design_mesh_id": mesh_ids.get("design"),
        "topo_mesh_id": mesh_ids.get("topo"),
    }
