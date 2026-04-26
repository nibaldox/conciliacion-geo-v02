import sqlite3
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

DB_PATH = Path(__file__).parent.parent / "data" / "conciliacion.db"


def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            settings TEXT DEFAULT '{}',
            sections TEXT DEFAULT '[]',
            process_status TEXT DEFAULT 'idle',
            current_section INTEGER DEFAULT 0,
            total_sections INTEGER DEFAULT 0,
            completed_sections INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS meshes (
            id TEXT PRIMARY KEY,
            session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
            type TEXT CHECK(type IN ('design', 'topo')),
            filename TEXT,
            data BLOB,
            n_vertices INTEGER,
            n_faces INTEGER,
            bounds TEXT,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
            section_name TEXT,
            data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS extraction_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
            section_name TEXT,
            type TEXT CHECK(type IN ('design', 'topo')),
            data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, section_name, type)
        );
    """)
    conn.commit()
    conn.close()


def create_session() -> str:
    """Create a new session and return its ID."""
    session_id = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        "INSERT INTO sessions (id, settings, sections) VALUES (?, '{}', '[]')",
        (session_id,)
    )
    conn.commit()
    conn.close()
    return session_id


def get_or_create_session(session_id: Optional[str] = None) -> str:
    """Get existing session or create new one."""
    if session_id:
        conn = get_connection()
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()
        if row:
            return session_id
    return create_session()


def cleanup_old_sessions(max_age_hours: int = 24):
    """Delete sessions older than max_age_hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours))
    # Use same format as SQLite CURRENT_TIMESTAMP: 'YYYY-MM-DD HH:MM:SS'
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff_str,))
    conn.commit()
    conn.close()


# --- Mesh operations ---

def save_mesh(session_id: str, mesh_type: str, filename: str, data: bytes,
              n_vertices: int, n_faces: int, bounds: Dict[str, float]) -> str:
    """Save a mesh file to the database. Returns mesh ID."""
    mesh_id = str(uuid.uuid4())
    conn = get_connection()
    # Remove any existing mesh of same type for this session
    conn.execute("DELETE FROM meshes WHERE session_id = ? AND type = ?", (session_id, mesh_type))
    conn.execute(
        "INSERT INTO meshes (id, session_id, type, filename, data, n_vertices, n_faces, bounds) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (mesh_id, session_id, mesh_type, filename, data, n_vertices, n_faces, json.dumps(bounds))
    )
    conn.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return mesh_id


def get_mesh(session_id: str, mesh_type: str) -> Optional[Dict[str, Any]]:
    """Get mesh info and data by session and type."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, type, filename, data, n_vertices, n_faces, bounds, uploaded_at FROM meshes WHERE session_id = ? AND type = ?",
        (session_id, mesh_type)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "type": row["type"],
        "filename": row["filename"],
        "data": row["data"],
        "n_vertices": row["n_vertices"],
        "n_faces": row["n_faces"],
        "bounds": json.loads(row["bounds"]),
        "uploaded_at": row["uploaded_at"],
    }


def get_mesh_by_id(mesh_id: str) -> Optional[Dict[str, Any]]:
    """Get mesh by its ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, session_id, type, filename, data, n_vertices, n_faces, bounds, uploaded_at FROM meshes WHERE id = ?",
        (mesh_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "type": row["type"],
        "filename": row["filename"],
        "data": row["data"],
        "n_vertices": row["n_vertices"],
        "n_faces": row["n_faces"],
        "bounds": json.loads(row["bounds"]),
        "uploaded_at": row["uploaded_at"],
    }


def delete_mesh(mesh_id: str) -> bool:
    """Delete a mesh by ID. Returns True if deleted."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM meshes WHERE id = ?", (mesh_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_all_meshes(session_id: str) -> List[Dict[str, Any]]:
    """Get all meshes for a session (without BLOB data)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, type, filename, n_vertices, n_faces, bounds, uploaded_at FROM meshes WHERE session_id = ?",
        (session_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "filename": r["filename"],
            "n_vertices": r["n_vertices"],
            "n_faces": r["n_faces"],
            "bounds": json.loads(r["bounds"]),
            "uploaded_at": r["uploaded_at"],
        }
        for r in rows
    ]


# --- Section operations ---

def save_sections(session_id: str, sections: List[Dict]):
    """Replace all sections for a session."""
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET sections = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(sections), session_id)
    )
    conn.commit()
    conn.close()


def get_sections(session_id: str) -> List[Dict]:
    """Get all sections for a session."""
    conn = get_connection()
    row = conn.execute("SELECT sections FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not row or not row["sections"]:
        return []
    return json.loads(row["sections"])


# --- Settings operations ---

def save_settings(session_id: str, settings: Dict):
    """Save process settings + tolerances for a session."""
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET settings = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(settings), session_id)
    )
    conn.commit()
    conn.close()


def get_settings(session_id: str) -> Dict:
    """Get settings for a session."""
    conn = get_connection()
    row = conn.execute("SELECT settings FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not row or not row["settings"]:
        return {}
    return json.loads(row["settings"])


# --- Process status operations ---

def update_process_status(session_id: str, status: str, current: int = 0, total: int = 0, completed: int = 0):
    """Update processing status."""
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET process_status = ?, current_section = ?, total_sections = ?, completed_sections = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, current, total, completed, session_id)
    )
    conn.commit()
    conn.close()


def get_process_status(session_id: str) -> Dict:
    """Get current processing status."""
    conn = get_connection()
    row = conn.execute(
        "SELECT process_status, current_section, total_sections, completed_sections FROM sessions WHERE id = ?",
        (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"status": "idle", "current_section": 0, "total_sections": 0, "completed_sections": 0}
    return {
        "status": row["process_status"],
        "current_section": row["current_section"],
        "total_sections": row["total_sections"],
        "completed_sections": row["completed_sections"],
    }


# --- Results operations ---

def save_results(session_id: str, results: List[Dict]):
    """Replace all results for a session."""
    conn = get_connection()
    conn.execute("DELETE FROM results WHERE session_id = ?", (session_id,))
    for r in results:
        section_name = r.get("section", "")
        conn.execute(
            "INSERT INTO results (session_id, section_name, data) VALUES (?, ?, ?)",
            (session_id, section_name, json.dumps(r))
        )
    conn.commit()
    conn.close()


def get_results(session_id: str, section: Optional[str] = None) -> List[Dict]:
    """Get results, optionally filtered by section."""
    conn = get_connection()
    if section:
        rows = conn.execute(
            "SELECT data FROM results WHERE session_id = ? AND section_name = ?",
            (session_id, section)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT data FROM results WHERE session_id = ?",
            (session_id,)
        ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


def get_results_count(session_id: str) -> int:
    """Count results for a session."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM results WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return row["cnt"] if row else 0


# --- Extraction cache ---

def save_extraction(session_id: str, section_name: str, ext_type: str, data: Dict):
    """Save extraction result to cache."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO extraction_cache (session_id, section_name, type, data) VALUES (?, ?, ?, ?)",
        (session_id, section_name, ext_type, json.dumps(data))
    )
    conn.commit()
    conn.close()


def get_extraction(session_id: str, section_name: str, ext_type: str) -> Optional[Dict]:
    """Get cached extraction result."""
    conn = get_connection()
    row = conn.execute(
        "SELECT data FROM extraction_cache WHERE session_id = ? AND section_name = ? AND type = ?",
        (session_id, section_name, ext_type)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["data"])


def get_all_extractions(session_id: str, ext_type: str) -> List[Dict]:
    """Get all cached extractions of a type for a session."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT section_name, data FROM extraction_cache WHERE session_id = ? AND type = ?",
        (session_id, ext_type)
    ).fetchall()
    conn.close()
    return [(r["section_name"], json.loads(r["data"])) for r in rows]
