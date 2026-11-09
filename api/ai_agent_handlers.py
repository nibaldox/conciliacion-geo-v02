"""Read-tool handlers for the AI agent (plan sections 4.1, 5.3 and 8-T1).

Each handler implements exactly one READ tool of
``core.ai_v2.agent.catalog`` over ``api.database`` and the router-internal
computation helpers of ``api.routers.process``. No self-HTTP, no writes:
every handler is strictly read-only against SQLite.

Conventions shared by all handlers:

- ``session_id`` is supplied by the caller (middleware context); it is
  never read from the model arguments.
- Return values are small JSON-safe dicts with stable keys: SQL counts,
  per-row status tallies and compact per-item summaries. Meshes, blobs,
  point arrays and full comparison rows never leave the database.
- Unbounded lists are capped (worst entries first) with explicit
  truncation flags so output size stays bounded on real sessions.
- Not-found lookups return ``{"found": False, ...}`` instead of raising,
  so the agent loop can surface a readable tool result.

The ``api.routers.process`` computation helpers are imported lazily
inside the handlers that use them: a module-level import would create a
collection cycle (``api.routers`` imports ``ai`` at package init, and
``ai.py`` imports this module back).
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import Counter
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypeVar

import api.database as db
from fastapi import HTTPException
from core.ai_v2.agent.catalog import TOOL_CATALOG
from core.ai_v2.agent.models import (
    MeshIdArgs,
    NoArgs,
    SectionIdArgs,
    ToolRisk,
)
from core.compliance_status import (
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_NO_CUMPLE,
    STATUS_RAMPA_OK,
)

Handler = Callable[[str, Any], Awaitable[Dict[str, Any]]]

_MAX_SECTION_ENTRIES = 30
_MAX_LIST_ENTRIES = 50

_UNMEASURED_KEY = "sin_medir"

_STATUS_FIELDS: Tuple[str, ...] = (
    "section_status",
    "height_status",
    "angle_status",
    "berm_status",
)
_GROUP_FIELDS: Tuple[str, ...] = ("sector", "type")
_ALL_FIELDS: Tuple[str, ...] = _STATUS_FIELDS + _GROUP_FIELDS

_STATUS_RANK: Dict[str, int] = {
    STATUS_NO_CUMPLE: 3,
    STATUS_FUERA: 2,
    STATUS_CUMPLE: 1,
    STATUS_RAMPA_OK: 1,
}


def _status_rank(status: Any) -> int:
    """Severity rank used to order sections worst-first."""
    if not isinstance(status, str):
        return 0
    return _STATUS_RANK.get(status, 0)


_RANK_TO_STATUS: Dict[int, Optional[str]] = {
    3: STATUS_NO_CUMPLE,
    2: STATUS_FUERA,
    1: STATUS_CUMPLE,
    0: None,
}


def _rank_to_status(rank: Any) -> Optional[str]:
    """Inverse of :func:`_status_rank` for SQL aggregate results."""
    if rank is None:
        return None
    return _RANK_TO_STATUS.get(int(rank))


def _json_key(value: Any) -> str:
    """JSON-safe counter key; missing statuses become ``sin_medir``."""
    if value is None:
        return _UNMEASURED_KEY
    return str(value)


ResultT = TypeVar("ResultT")


async def _run_off_loop(func: Callable[..., ResultT], *args: Any) -> ResultT:
    """Run a router-internal sync computation off the event loop."""
    return await asyncio.to_thread(func, *args)


# ---------------------------------------------------------------------------
# Session meshes (compact DB rows only — never trimesh)
# ---------------------------------------------------------------------------


def _mesh_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    """Compact JSON-safe projection of one persisted mesh row."""
    return {
        "id": row["id"],
        "type": row["type"],
        "filename": row["filename"],
        "n_vertices": row["n_vertices"],
        "n_faces": row["n_faces"],
        "bounds": row["bounds"],
    }


# ---------------------------------------------------------------------------
# Results aggregation (SQL json_extract with bounded-iteration fallback)
# ---------------------------------------------------------------------------


def _sql_counters(conn: sqlite3.Connection, session_id: str) -> Dict[str, Counter]:
    """Per-field status/group tallies via GROUP BY json_extract."""
    counters: Dict[str, Counter] = {}
    for field in _ALL_FIELDS:
        rows = conn.execute(
            "SELECT json_extract(data, '$." + field + "') AS value, COUNT(*) AS n "
            "FROM results WHERE session_id = ? GROUP BY value",
            (session_id,),
        ).fetchall()
        counter: Counter = Counter()
        for row in rows:
            counter[row["value"]] += row["n"]
        counters[field] = counter
    return counters


def _sql_sections(
    conn: sqlite3.Connection,
    session_id: str,
) -> Dict[str, Dict[str, Any]]:
    """Per-section row count, worst status rank and score via one GROUP BY."""
    rows = conn.execute(
        "SELECT json_extract(data, '$.section') AS name, COUNT(*) AS n_rows, "
        "MAX(CASE "
        "WHEN json_extract(data, '$.section_status') = ? THEN 3 "
        "WHEN json_extract(data, '$.section_status') = ? THEN 2 "
        "WHEN json_extract(data, '$.section_status') IN (?, ?) THEN 1 "
        "ELSE 0 END) AS worst_rank, "
        "MAX(json_extract(data, '$.section_score')) AS score "
        "FROM results WHERE session_id = ? GROUP BY name",
        (
            STATUS_NO_CUMPLE,
            STATUS_FUERA,
            STATUS_CUMPLE,
            STATUS_RAMPA_OK,
            session_id,
        ),
    ).fetchall()
    sections: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = _json_key(row["name"])
        sections[name] = {
            "n_rows": int(row["n_rows"]),
            "worst_rank": int(row["worst_rank"]) if row["worst_rank"] is not None else 0,
            "score": row["score"],
        }
    return sections


def _results_from_sql(session_id: str) -> Optional[Tuple[Dict[str, Counter], Dict[str, Dict[str, Any]]]]:
    """Aggregate results with SQL json_extract; None when JSON1 is absent."""
    conn = db.get_connection()
    try:
        counters = _sql_counters(conn, session_id)
        sections = _sql_sections(conn, session_id)
        return counters, sections
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def _absorb_row(
    fields: Dict[str, Any],
    counters: Dict[str, Counter],
    sections: Dict[str, Dict[str, Any]],
) -> None:
    """Fold one row's extracted status fields into the tallies."""
    for field in _ALL_FIELDS:
        counters[field][fields.get(field)] += 1
    name = _json_key(fields.get("section"))
    entry = sections.setdefault(name, {"n_rows": 0, "worst_rank": 0, "score": None})
    entry["n_rows"] += 1
    rank = _status_rank(fields.get("section_status"))
    entry["worst_rank"] = max(entry["worst_rank"], rank)
    score = fields.get("section_score")
    if isinstance(score, (int, float)):
        current = entry["score"]
        entry["score"] = score if current is None else max(current, score)


def _results_from_rows(
    session_id: str,
    section: Optional[str] = None,
) -> Tuple[Dict[str, Counter], Dict[str, Dict[str, Any]]]:
    """Bounded fallback: stream rows one by one, keep only status fields.

    Only the small status/group fields and the score are extracted per
    row; the rest of each payload is discarded immediately.
    """
    counters: Dict[str, Counter] = {field: Counter() for field in _ALL_FIELDS}
    sections: Dict[str, Dict[str, Any]] = {}
    conn = db.get_connection()
    try:
        if section is None:
            cursor = conn.execute(
                "SELECT data FROM results WHERE session_id = ?", (session_id,)
            )
        else:
            cursor = conn.execute(
                "SELECT data FROM results WHERE session_id = ? AND section_name = ?",
                (session_id, section),
            )
        for row in cursor:
            payload = json.loads(row["data"])
            fields = {field: payload.get(field) for field in _ALL_FIELDS}
            fields["section"] = payload.get("section")
            fields["section_score"] = payload.get("section_score")
            _absorb_row(fields, counters, sections)
    finally:
        conn.close()
    return counters, sections


def _aggregate_results(
    session_id: str,
    section: Optional[str] = None,
) -> Tuple[Dict[str, Counter], Dict[str, Dict[str, Any]]]:
    """Aggregate tallies via SQL, falling back to bounded iteration."""
    if section is None:
        aggregated = _results_from_sql(session_id)
        if aggregated is not None:
            return aggregated
    return _results_from_rows(session_id, section=section)


def _section_compliance(
    session_id: str,
    section_name: str,
) -> Dict[str, Any]:
    """Worst status + score of one section, from its comparison rows only."""
    counters, sections = _aggregate_results(session_id, section=section_name)
    entry = sections.get(_json_key(section_name))
    score = entry["score"] if entry else None
    worst_rank = entry["worst_rank"] if entry else 0
    return {
        "worst_status": _rank_to_status(worst_rank),
        "section_score": score,
        "n_rows": entry["n_rows"] if entry else 0,
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def get_workflow_state(session_id: str, args: NoArgs) -> Dict[str, Any]:
    """Aggregate session state from SQL counts and small JSON columns."""
    status = db.get_process_status(session_id)
    n_results = db.get_results_count(session_id)
    sections = db.get_sections(session_id)
    meshes = db.get_all_meshes(session_id)
    design = next((m for m in meshes if m["type"] == "design"), None)
    topo = next((m for m in meshes if m["type"] == "topo"), None)
    return {
        "n_sections": len(sections),
        "n_results": n_results,
        "process_status": status["status"],
        "has_design_mesh": design is not None,
        "has_topo_mesh": topo is not None,
        "process_detail": {
            "current_section": status["current_section"],
            "total_sections": status["total_sections"],
            "completed_sections": status["completed_sections"],
        },
        "design_mesh_id": design["id"] if design else None,
        "topo_mesh_id": topo["id"] if topo else None,
        "ready_for_reconciliation": design is not None and topo is not None and len(sections) > 0,
    }


async def list_meshes(session_id: str, args: NoArgs) -> Dict[str, Any]:
    """List the session's persisted mesh rows without BLOB data."""
    meshes = db.get_all_meshes(session_id)
    return {
        "n_meshes": len(meshes),
        "meshes": [_mesh_summary(row) for row in meshes],
    }


async def get_mesh_info(session_id: str, args: MeshIdArgs) -> Dict[str, Any]:
    """Compact info for one mesh; scoped to the session for isolation."""
    meshes = db.get_all_meshes(session_id)
    row = next((m for m in meshes if m["id"] == args.mesh_id), None)
    if row is None:
        return {"found": False, "mesh_id": args.mesh_id}
    summary = _mesh_summary(row)
    summary["found"] = True
    return summary


async def list_sections(session_id: str, args: NoArgs) -> Dict[str, Any]:
    """Compact per-section summaries from the small sessions JSON list."""
    sections = db.get_sections(session_id)
    entries: List[Dict[str, Any]] = []
    for index, sec in enumerate(sections):
        entries.append(
            {
                "id": str(index),
                "name": sec.get("name"),
                "sector": sec.get("sector", ""),
                "origin": sec.get("origin"),
                "azimuth": sec.get("azimuth"),
                "length": sec.get("length"),
                "length_up": sec.get("length_up"),
                "length_down": sec.get("length_down"),
            }
        )
    shown = entries[:_MAX_LIST_ENTRIES]
    return {
        "n_sections": len(sections),
        "sections_shown": len(shown),
        "sections_truncated": len(shown) < len(entries),
        "sections": shown,
    }


async def get_results_summary(session_id: str, args: NoArgs) -> Dict[str, Any]:
    """Aggregate comparison results: counts per status, sector and section."""
    counters, sections = _aggregate_results(session_id)
    ranked = sorted(
        sections.items(),
        key=lambda item: (-item[1]["worst_rank"], item[0]),
    )
    shown = ranked[:_MAX_SECTION_ENTRIES]
    scores = [
        entry["score"]
        for entry in sections.values()
        if isinstance(entry["score"], (int, float))
    ]
    score_stats: Optional[Dict[str, float]] = None
    if scores:
        score_stats = {
            "mean": round(sum(scores) / len(scores), 1),
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
        }
    section_status = counters["section_status"]
    return {
        "n_results": sum(section_status.values()),
        "by_section_status": {_json_key(k): v for k, v in section_status.items()},
        "by_type": {_json_key(k): v for k, v in counters["type"].items()},
        "by_sector": {_json_key(k): v for k, v in counters["sector"].items()},
        "status_by_parameter": {
            "height": {_json_key(k): v for k, v in counters["height_status"].items()},
            "angle": {_json_key(k): v for k, v in counters["angle_status"].items()},
            "berm": {_json_key(k): v for k, v in counters["berm_status"].items()},
        },
        "n_sections": len(sections),
        "sections_shown": len(shown),
        "sections_truncated": len(shown) < len(ranked),
        "sections": [
            {
                "name": name,
                "n_rows": entry["n_rows"],
                "worst_status": _rank_to_status(entry["worst_rank"]),
                "section_score": entry["score"],
            }
            for name, entry in shown
        ],
        "section_score": score_stats,
    }


async def get_profile(session_id: str, args: SectionIdArgs) -> Dict[str, Any]:
    """One section summarized via the router's own profile computation."""
    from api.routers.process import _build_profile_payload_sync

    try:
        index = int(args.section_id)
    except ValueError:
        return {"found": False, "section_id": args.section_id, "error": "invalid_section_id"}
    sections = db.get_sections(session_id)
    if index < 0 or index >= len(sections):
        return {"found": False, "section_id": args.section_id, "error": "section_id_out_of_range"}
    try:
        payload = await _run_off_loop(_build_profile_payload_sync, session_id, sections[index])
    except HTTPException as exc:
        return {
            "found": False,
            "section_id": args.section_id,
            "error": "profile_unavailable",
            "detail": str(exc.detail)[:200],
        }
    compliance = _section_compliance(session_id, sections[index].get("name", ""))
    warnings = payload.get("profile_warnings") or {}
    design_points = len((payload.get("design") or {}).get("distances", []))
    topo_points = len((payload.get("topo") or {}).get("distances", []))
    return {
        "found": True,
        "section_id": args.section_id,
        "name": payload.get("section_name"),
        "sector": payload.get("sector"),
        "origin": payload.get("origin"),
        "azimuth": payload.get("azimuth"),
        "n_points_design": design_points,
        "n_points_topo": topo_points,
        "n_benches_design": len(payload.get("benches_design") or []),
        "n_benches_topo": len(payload.get("benches_topo") or []),
        "floor_elevation": payload.get("floor_elevation"),
        "crest_elevation_max": payload.get("crest_elevation_max"),
        "n_warnings_design": len(warnings.get("design") or []),
        "n_warnings_topo": len(warnings.get("topo") or []),
        "worst_status": compliance["worst_status"],
        "section_score": compliance["section_score"],
    }


async def get_design_achievement(session_id: str, args: NoArgs) -> Dict[str, Any]:
    """Logro Diseño summary via the router's computation, compacted."""
    from api.routers.process import _build_design_achievement_sync

    response = await _run_off_loop(_build_design_achievement_sync, session_id, None, None, None, None)
    summary = response.get("summary") or {}
    sectors = [
        {
            "sector": entry.get("sector"),
            "n_evaluable": entry.get("n_evaluable"),
            "global_score": entry.get("global_score"),
            "crest_pct": entry.get("crest_pct"),
            "toe_pct": entry.get("toe_pct"),
            "berm_pct": entry.get("berm_pct"),
        }
        for entry in response.get("sectors") or []
    ]
    return {
        "n_total_rows": response.get("n_total_rows"),
        "status": (response.get("metadata") or {}).get("status"),
        "global_score": summary.get("global_score"),
        "n_total": summary.get("n_total"),
        "n_evaluable": summary.get("n_evaluable"),
        "coverage": summary.get("coverage"),
        "crest_pct": summary.get("crest_pct"),
        "toe_pct": summary.get("toe_pct"),
        "berm_pct": summary.get("berm_pct"),
        "delta_crest_mean": summary.get("delta_crest_mean"),
        "delta_toe_mean": summary.get("delta_toe_mean"),
        "tolerances": response.get("tolerances"),
        "tolerances_source": response.get("tolerances_source"),
        "sectors": sectors,
        "warnings": response.get("warnings"),
    }


async def get_proposed_compliance(session_id: str, args: NoArgs) -> Dict[str, Any]:
    """Proposed-parameters compliance summary via the router's helper."""
    from api.routers.process import _build_proposed_compliance_sync

    response = await _run_off_loop(_build_proposed_compliance_sync, session_id, None, None, None, None)
    payload = response.model_dump()
    out: Dict[str, Any] = {
        "proposal_status": payload.get("proposal_status"),
        "n_total_rows": payload.get("n_total_rows"),
        "n_proposal_rows": payload.get("n_proposal_rows"),
        "n_failed_rows": payload.get("n_failed_rows"),
        "n_not_computed_rows": payload.get("n_not_computed_rows"),
        "floor_tolerance_source": payload.get("floor_tolerance_source"),
        "warnings": payload.get("warnings"),
    }
    summary = payload.get("summary")
    if summary is not None:
        coverage = summary.get("coverage") or {}
        by_section = summary.get("by_section") or {}
        ranked = sorted(
            by_section.items(),
            key=lambda item: -(item[1].get("proposed_section_score") if isinstance(item[1].get("proposed_section_score"), (int, float)) else -1.0),
        )
        shown = ranked[:_MAX_SECTION_ENTRIES]
        out["summary"] = {
            "proposed_global_score": summary.get("proposed_global_score"),
            "n_rows": summary.get("n_rows"),
            "n_evaluable": summary.get("n_evaluable"),
            "n_not_excavated": summary.get("n_not_excavated"),
            "n_unmeasured": summary.get("n_unmeasured"),
            "n_split_benches": summary.get("n_split_benches"),
            "excavation_debt_area_m2": summary.get("excavation_debt_area_m2"),
            "floor_status_counts": summary.get("floor_status_counts"),
            "coverage": {
                "n_evaluable": coverage.get("n_evaluable"),
                "n_design_benches": coverage.get("n_design_benches"),
                "ratio": coverage.get("ratio"),
            },
            "per_sections_shown": len(shown),
            "per_sections_truncated": len(shown) < len(by_section),
            "per_section_scores": {name: entry.get("proposed_section_score") for name, entry in shown},
        }
    else:
        out["summary"] = None
    return out


_HANDLERS: Dict[str, Handler] = {
    "get_workflow_state": get_workflow_state,
    "list_meshes": list_meshes,
    "get_mesh_info": get_mesh_info,
    "list_sections": list_sections,
    "get_results_summary": get_results_summary,
    "get_profile": get_profile,
    "get_design_achievement": get_design_achievement,
    "get_proposed_compliance": get_proposed_compliance,
}

READ_HANDLERS: Dict[str, Handler] = {
    name: _HANDLERS[name]
    for name, spec in TOOL_CATALOG.items()
    if spec.risk is ToolRisk.READ
}


__all__ = [
    "READ_HANDLERS",
    "get_design_achievement",
    "get_mesh_info",
    "get_profile",
    "get_proposed_compliance",
    "get_results_summary",
    "get_workflow_state",
    "list_meshes",
    "list_sections",
]
