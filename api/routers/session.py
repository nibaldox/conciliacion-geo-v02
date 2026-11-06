from fastapi import APIRouter, HTTPException, Request

import api.database as db
from api._async_db import run_db

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/recovery")
async def recover_session(request: Request) -> dict[str, str | None]:
    session_id = request.state.session_id
    if not await run_db(db.session_exists, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    meshes = await run_db(db.get_all_meshes, session_id)
    mesh_ids = {mesh["type"]: mesh["id"] for mesh in meshes}
    return {
        "session_id": session_id,
        "design_mesh_id": mesh_ids.get("design"),
        "topo_mesh_id": mesh_ids.get("topo"),
    }
