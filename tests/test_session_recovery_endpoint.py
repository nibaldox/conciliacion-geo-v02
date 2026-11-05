import uuid

import api.database as db
from api.main import app


def _save_mesh(session_id: str, mesh_type: str) -> str:
    return db.save_mesh(
        session_id=session_id,
        mesh_type=mesh_type,
        filename=f"{mesh_type}.stl",
        data=b"mesh-data",
        n_vertices=3,
        n_faces=1,
        bounds={"xmin": 0.0, "xmax": 1.0, "ymin": 0.0, "ymax": 1.0, "zmin": 0.0, "zmax": 1.0},
    )


def test_recovery_returns_only_mesh_ids_for_header_session(api_test_client):
    session_id = db.create_session()
    design_id = _save_mesh(session_id, "design")
    topo_id = _save_mesh(session_id, "topo")

    response = api_test_client.get(
        "/api/v1/session/recovery",
        headers={"x-session-id": session_id},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "design_mesh_id": design_id,
        "topo_mesh_id": topo_id,
    }
    assert response.headers["x-session-id"] == session_id


def test_recovery_does_not_expose_meshes_from_another_session(api_test_client):
    stored_session_id = db.create_session()
    _save_mesh(stored_session_id, "design")
    active_session_id = db.create_session()

    response = api_test_client.get(
        "/api/v1/session/recovery",
        headers={"x-session-id": active_session_id},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": active_session_id,
        "design_mesh_id": None,
        "topo_mesh_id": None,
    }


def test_recovery_returns_404_without_creating_unknown_session(api_test_client):
    unknown_session_id = str(uuid.uuid4())

    response = api_test_client.get(
        "/api/v1/session/recovery",
        headers={"x-session-id": unknown_session_id},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
    assert db.session_exists(unknown_session_id) is False
