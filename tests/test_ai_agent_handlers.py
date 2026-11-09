"""Tests for the AI agent read-tool handlers (plan section 8, T1).

Every handler is exercised against a per-test isolated SQLite database
(root conftest ``api_isolated_db``): production data is never touched.
Coverage: catalog mapping completeness, session isolation, the read-only
invariant (DB file bytes unchanged), and the small-output size bound.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, cast

import numpy as np
import pytest
import trimesh

import api.database as db
from api.ai_agent_handlers import READ_HANDLERS
from core.ai_v2.agent.catalog import TOOL_CATALOG
from core.ai_v2.agent.models import MeshIdArgs, NoArgs, SectionIdArgs, ToolRisk
from core.compliance_status import STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE

SIZE_BOUND_BYTES = 4096


# ---------------------------------------------------------------------------
# Fixtures: seeded sessions
# ---------------------------------------------------------------------------


def _comparison_row(
    section: str,
    sector: str,
    status: str,
    score: float,
    bench_num: int = 1,
    row_type: str = "MATCH",
    berm_status: Any = STATUS_CUMPLE,
) -> Dict[str, Any]:
    """Production-shaped comparison row (mirrors core.profile_compliance)."""
    return {
        "section": section,
        "sector": sector,
        "bench_num": bench_num,
        "bench_num_topo": bench_num,
        "type": row_type,
        "level": "1000",
        "height_status": status,
        "angle_status": STATUS_CUMPLE,
        "berm_status": berm_status,
        "section_status": status,
        "section_score": score,
        "delta_crest": 0.5 if status == STATUS_CUMPLE else 2.0,
        "delta_toe": -0.8 if status == STATUS_CUMPLE else 0.0,
    }


def _bench_dict() -> Dict[str, Any]:
    return {
        "bench_number": 1,
        "crest_elevation": 30.0,
        "crest_distance": 0.0,
        "toe_elevation": 15.0,
        "toe_distance": 10.0,
        "bench_height": 15.0,
        "face_angle": 56.3,
        "berm_width": 10.0,
        "is_ramp": False,
        "spill_width": 0.0,
        "effective_berm_width": 10.0,
        "spill_start_distance": 0.0,
        "spill_start_elevation": 30.0,
        "floor_elevation": 0.0,
    }


def _bench_surface_mesh(shift: float = 0.0) -> trimesh.Trimesh:
    """Stepped bench profile extruded in Y (proven cut fixture geometry)."""
    profile = [(-10, 30), (0, 30), (10, 15), (20, 15), (30, 0), (50, 0)]
    vertices = [(x + shift, y, z) for x, z in profile for y in (-10, 10)]
    faces: List[List[int]] = []
    for index in range(len(profile) - 1):
        start = index * 2
        faces.extend(
            [
                [start, start + 1, start + 2],
                [start + 1, start + 3, start + 2],
            ]
        )
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _section_dict(name: str, sector: str = "A") -> Dict[str, Any]:
    return {
        "name": name,
        "origin": [20.0, 0.0],
        "azimuth": 90,
        "length": 60,
        "length_up": None,
        "length_down": None,
        "sector": sector,
    }


def _save_mesh_bytes(session_id: str, mesh_type: str, shift: float, filename: str) -> str:
    mesh = _bench_surface_mesh(shift)
    stl_bytes = cast(bytes, mesh.export(file_type="stl"))
    return db.save_mesh(
        session_id,
        mesh_type,
        filename,
        data=stl_bytes,
        n_vertices=len(mesh.vertices),
        n_faces=len(mesh.faces),
        bounds={"min_x": -10 + shift, "max_x": 50 + shift, "min_z": 0.0, "max_z": 30.0},
    )


def _seed_empty_session() -> str:
    return db.create_session()


def _seed_meshes_session() -> tuple[str, str, str]:
    session_id = db.create_session()
    design_id = _save_mesh_bytes(session_id, "design", 0.0, "design.stl")
    topo_id = _save_mesh_bytes(session_id, "topo", 0.5, "topo.stl")
    return session_id, design_id, topo_id


def _seed_full_session(session_id: str) -> None:
    db.save_sections(session_id, [_section_dict("S-01", "A"), _section_dict("S-02", "B")])
    for name, ext_type in (("S-01", "design"), ("S-01", "topo"), ("S-02", "design"), ("S-02", "topo")):
        db.save_extraction(session_id, name, ext_type, {"benches": [_bench_dict()]})
    db.save_results(
        session_id,
        [
            _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0, bench_num=1),
            _comparison_row("S-01", "A", STATUS_FUERA, 45.0, bench_num=2, row_type="EXTRA"),
            _comparison_row("S-02", "B", STATUS_NO_CUMPLE, 20.0, bench_num=3, row_type="MISSING"),
        ],
    )


def _checkpoint(db_path: Path) -> None:
    conn = db.get_connection()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


@pytest.fixture()
def checkpointed_db_path(api_isolated_db) -> Path:
    _checkpoint(Path(db.DB_PATH))
    return Path(db.DB_PATH)


@pytest.fixture()
def session_a() -> str:
    session_id = db.create_session()
    _seed_full_session(session_id)
    _save_mesh_bytes(session_id, "design", 0.0, "design.stl")
    _save_mesh_bytes(session_id, "topo", 0.5, "topo.stl")
    return session_id


@pytest.fixture()
def session_b() -> str:
    session_id = db.create_session()
    db.save_sections(session_id, [_section_dict("S-99", "Z")])
    db.save_results(
        session_id,
        [
            _comparison_row("S-99", "Z", STATUS_NO_CUMPLE, 10.0, bench_num=1),
            _comparison_row("S-99", "Z", STATUS_NO_CUMPLE, 10.0, bench_num=2),
            _comparison_row("S-99", "Z", STATUS_NO_CUMPLE, 10.0, bench_num=3),
        ],
    )
    topo_id = _save_mesh_bytes(session_id, "topo", 2.0, "topo-b.stl")
    assert topo_id
    return session_id


async def _call_all(session_id: str) -> Dict[str, Dict[str, Any]]:
    outputs: Dict[str, Dict[str, Any]] = {}
    outputs["get_workflow_state"] = await READ_HANDLERS["get_workflow_state"](session_id, NoArgs())
    outputs["list_meshes"] = await READ_HANDLERS["list_meshes"](session_id, NoArgs())
    outputs["get_mesh_info"] = await READ_HANDLERS["get_mesh_info"](
        session_id, MeshIdArgs(mesh_id="nonexistent")
    )
    outputs["list_sections"] = await READ_HANDLERS["list_sections"](session_id, NoArgs())
    outputs["get_results_summary"] = await READ_HANDLERS["get_results_summary"](session_id, NoArgs())
    outputs["get_design_achievement"] = await READ_HANDLERS["get_design_achievement"](session_id, NoArgs())
    outputs["get_proposed_compliance"] = await READ_HANDLERS["get_proposed_compliance"](session_id, NoArgs())
    return outputs


# ---------------------------------------------------------------------------
# Mapping completeness
# ---------------------------------------------------------------------------


class TestMappingCompleteness:
    def test_covers_exactly_the_catalog_read_subset(self):
        expected = {
            name for name, spec in TOOL_CATALOG.items() if spec.risk is ToolRisk.READ
        }
        assert set(READ_HANDLERS) == expected
        assert len(expected) == 8

    def test_no_non_read_tool_is_mapped(self):
        read_names = {
            name for name, spec in TOOL_CATALOG.items() if spec.risk is ToolRisk.READ
        }
        for name in READ_HANDLERS:
            assert TOOL_CATALOG[name].risk is ToolRisk.READ
        assert read_names.issuperset(READ_HANDLERS)

    @pytest.mark.asyncio
    async def test_every_handler_is_callable_async_two_args(self):
        for name, handler in READ_HANDLERS.items():
            assert callable(handler), name
            params = list(inspect.signature(handler).parameters)
            assert len(params) == 2, name
            assert inspect.iscoroutinefunction(handler), name

    @pytest.mark.asyncio
    async def test_handlers_never_read_session_from_args(self):
        for spec in TOOL_CATALOG.values():
            if spec.risk is not ToolRisk.READ:
                continue
            for field_name in spec.args_model.model_fields:
                assert field_name != "session_id"


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionIsolation:
    async def test_workflow_state_counts_only_own_session(self, session_a, session_b):
        state_a = await READ_HANDLERS["get_workflow_state"](session_a, NoArgs())
        state_b = await READ_HANDLERS["get_workflow_state"](session_b, NoArgs())
        assert state_a["n_results"] == 3
        assert state_a["n_sections"] == 2
        assert state_a["has_design_mesh"] is True
        assert state_a["has_topo_mesh"] is True
        assert state_b["n_results"] == 3
        assert state_b["n_sections"] == 1
        assert state_b["has_design_mesh"] is False
        assert state_b["has_topo_mesh"] is True
        assert state_a["design_mesh_id"] not in (None, state_b["topo_mesh_id"])

    async def test_mesh_listing_is_scoped_to_session(self, session_a, session_b):
        meshes_b = await READ_HANDLERS["list_meshes"](session_b, NoArgs())
        mesh_ids_b = [entry["id"] for entry in meshes_b["meshes"]]
        assert len(mesh_ids_b) == 1
        info_a = await READ_HANDLERS["get_mesh_info"](session_a, MeshIdArgs(mesh_id=mesh_ids_b[0]))
        assert info_a["found"] is False
        meshes_a = await READ_HANDLERS["list_meshes"](session_a, NoArgs())
        assert [entry["filename"] for entry in meshes_a["meshes"]] == ["design.stl", "topo.stl"]
        assert mesh_ids_b[0] not in [entry["id"] for entry in meshes_a["meshes"]]

    async def test_results_summary_counts_only_own_rows(self, session_a, session_b):
        summary_a = await READ_HANDLERS["get_results_summary"](session_a, NoArgs())
        assert summary_a["n_results"] == 3
        assert summary_a["by_section_status"] == {
            STATUS_CUMPLE: 1,
            STATUS_FUERA: 1,
            STATUS_NO_CUMPLE: 1,
        }
        assert set(summary_a["by_sector"]) == {"A", "B"}
        summary_b = await READ_HANDLERS["get_results_summary"](session_b, NoArgs())
        assert summary_b["n_results"] == 3
        assert summary_b["by_section_status"] == {STATUS_NO_CUMPLE: 3}
        assert set(summary_b["by_sector"]) == {"Z"}

    async def test_sections_and_profiles_are_scoped(self, session_a, session_b):
        sections_b = await READ_HANDLERS["list_sections"](session_b, NoArgs())
        assert [entry["name"] for entry in sections_b["sections"]] == ["S-99"]
        sections_a = await READ_HANDLERS["list_sections"](session_a, NoArgs())
        assert [entry["name"] for entry in sections_a["sections"]] == ["S-01", "S-02"]
        profile_a = await READ_HANDLERS["get_profile"](session_a, SectionIdArgs(section_id="1"))
        assert profile_a["found"] is True
        assert profile_a["name"] == "S-02"
        profile_b = await READ_HANDLERS["get_profile"](session_b, SectionIdArgs(section_id="1"))
        assert profile_b["found"] is False

    async def test_aggregate_summaries_use_only_own_rows(self, session_a, session_b):
        achievement_b = await READ_HANDLERS["get_design_achievement"](session_b, NoArgs())
        assert achievement_b["n_total_rows"] == 3
        achievement_a = await READ_HANDLERS["get_design_achievement"](session_a, NoArgs())
        assert achievement_a["n_total_rows"] == 3
        proposed_a = await READ_HANDLERS["get_proposed_compliance"](session_a, NoArgs())
        assert proposed_a["n_total_rows"] == 3
        proposed_b = await READ_HANDLERS["get_proposed_compliance"](session_b, NoArgs())
        assert proposed_b["n_total_rows"] == 3


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReadOnlyInvariant:
    async def test_db_file_bytes_unchanged_after_every_handler(
        self, checkpointed_db_path, session_a
    ):
        before = checkpointed_db_path.read_bytes()
        await _call_all(session_a)
        sections = db.get_sections(session_a)
        assert sections
        await READ_HANDLERS["get_profile"](session_a, SectionIdArgs(section_id="0"))
        _checkpoint(checkpointed_db_path)
        after = checkpointed_db_path.read_bytes()
        assert after == before

    async def test_row_counts_stable_after_handlers(self, checkpointed_db_path, session_a):
        n_before = db.get_results_count(session_a)
        await _call_all(session_a)
        assert db.get_results_count(session_a) == n_before


# ---------------------------------------------------------------------------
# Output size bound
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSummarySizeBound:
    async def test_every_serialized_output_stays_under_bound(self, session_a):
        sections = db.get_sections(session_a)
        outputs = await _call_all(session_a)
        outputs["get_profile"] = await READ_HANDLERS["get_profile"](
            session_a, SectionIdArgs(section_id="0")
        )
        assert len(outputs) == 8
        for name, payload in outputs.items():
            serialized = json.dumps(payload, ensure_ascii=False)
            assert len(serialized.encode("utf-8")) < SIZE_BOUND_BYTES, name

    async def test_empty_session_outputs_stay_under_bound(self, api_isolated_db):
        session_id = db.create_session()
        outputs = await _call_all(session_id)
        outputs["get_profile"] = await READ_HANDLERS["get_profile"](
            session_id, SectionIdArgs(section_id="0")
        )
        for name, payload in outputs.items():
            serialized = json.dumps(payload, ensure_ascii=False)
            assert len(serialized.encode("utf-8")) < SIZE_BOUND_BYTES, name


# ---------------------------------------------------------------------------
# Per-handler behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetWorkflowState:
    async def test_empty_session_defaults(self, api_isolated_db):
        session_id = db.create_session()
        state = await READ_HANDLERS["get_workflow_state"](session_id, NoArgs())
        assert state["n_sections"] == 0
        assert state["n_results"] == 0
        assert state["process_status"] == "idle"
        assert state["has_design_mesh"] is False
        assert state["has_topo_mesh"] is False
        assert state["ready_for_reconciliation"] is False

    async def test_ready_when_meshes_and_sections_exist(self, api_isolated_db):
        session_id, _, _ = _seed_meshes_session()
        db.save_sections(session_id, [_section_dict("S-01")])
        state = await READ_HANDLERS["get_workflow_state"](session_id, NoArgs())
        assert state["has_design_mesh"] is True
        assert state["has_topo_mesh"] is True
        assert state["ready_for_reconciliation"] is True

    async def test_process_status_reflects_session_row(self, session_a):
        db.update_process_status(session_a, "complete", 2, 2, 2)
        state = await READ_HANDLERS["get_workflow_state"](session_a, NoArgs())
        assert state["process_status"] == "complete"
        assert state["process_detail"]["completed_sections"] == 2


@pytest.mark.asyncio
class TestListMeshes:
    async def test_compact_mesh_fields(self, api_isolated_db):
        session_id, design_id, topo_id = _seed_meshes_session()
        result = await READ_HANDLERS["list_meshes"](session_id, NoArgs())
        assert result["n_meshes"] == 2
        by_type = {entry["type"]: entry for entry in result["meshes"]}
        assert set(by_type) == {"design", "topo"}
        assert by_type["design"]["id"] == design_id
        assert by_type["design"]["filename"] == "design.stl"
        assert by_type["design"]["n_vertices"] > 0
        assert by_type["design"]["n_faces"] > 0
        assert "data" not in by_type["design"]
        assert "import_report" not in by_type["design"]

    async def test_get_mesh_info_found_and_not_found(self, api_isolated_db):
        session_id, design_id, _ = _seed_meshes_session()
        info = await READ_HANDLERS["get_mesh_info"](session_id, MeshIdArgs(mesh_id=design_id))
        assert info["found"] is True
        assert info["type"] == "design"
        assert info["filename"] == "design.stl"
        assert info["bounds"]["min_z"] == 0.0
        missing = await READ_HANDLERS["get_mesh_info"](
            session_id, MeshIdArgs(mesh_id="no-such-id")
        )
        assert missing == {"found": False, "mesh_id": "no-such-id"}


@pytest.mark.asyncio
class TestListSections:
    async def test_compact_section_fields(self, session_a):
        result = await READ_HANDLERS["list_sections"](session_a, NoArgs())
        assert result["n_sections"] == 2
        assert result["sections_truncated"] is False
        first = result["sections"][0]
        assert first["id"] == "0"
        assert first["name"] == "S-01"
        assert first["sector"] == "A"
        assert first["origin"] == [20.0, 0.0]
        assert first["azimuth"] == 90
        assert first["length"] == 60
        assert first["length_up"] is None
        assert first["length_down"] is None

    async def test_empty_session(self, api_isolated_db):
        session_id = db.create_session()
        result = await READ_HANDLERS["list_sections"](session_id, NoArgs())
        assert result == {
            "n_sections": 0,
            "sections_shown": 0,
            "sections_truncated": False,
            "sections": [],
        }


@pytest.mark.asyncio
class TestGetResultsSummary:
    async def test_counts_per_status_sector_type_and_section(self, session_a):
        summary = await READ_HANDLERS["get_results_summary"](session_a, NoArgs())
        assert summary["n_results"] == 3
        assert summary["by_section_status"] == {
            STATUS_CUMPLE: 1,
            STATUS_FUERA: 1,
            STATUS_NO_CUMPLE: 1,
        }
        assert summary["by_sector"] == {"A": 2, "B": 1}
        assert summary["by_type"] == {"MATCH": 1, "EXTRA": 1, "MISSING": 1}
        by_section = {entry["name"]: entry for entry in summary["sections"]}
        assert by_section["S-01"]["n_rows"] == 2
        assert by_section["S-01"]["worst_status"] == STATUS_FUERA
        assert by_section["S-01"]["section_score"] == 85.0
        assert by_section["S-02"]["worst_status"] == STATUS_NO_CUMPLE
        assert summary["section_score"]["mean"] == pytest.approx(52.5)
        assert summary["section_score"]["max"] == pytest.approx(85.0)
        assert summary["section_score"]["min"] == pytest.approx(20.0)

    async def test_unmeasured_berm_counted_as_reported(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _comparison_row("S-01", "A", STATUS_CUMPLE, 80.0, berm_status="-"),
                _comparison_row("S-01", "A", STATUS_CUMPLE, 80.0, bench_num=2),
            ],
        )
        summary = await READ_HANDLERS["get_results_summary"](session_id, NoArgs())
        assert summary["status_by_parameter"]["berm"] == {"-": 1, STATUS_CUMPLE: 1}
        assert summary["by_section_status"] == {STATUS_CUMPLE: 2}

    async def test_json_path_agrees_with_fixture_rows(self, session_a):
        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT data FROM results WHERE session_id = ? LIMIT 1", (session_a,)
            ).fetchone()
        finally:
            conn.close()
        payload = json.loads(row["data"])
        assert set(payload) >= {"section_status", "sector", "type", "section_score"}
        summary = await READ_HANDLERS["get_results_summary"](session_a, NoArgs())
        assert summary["by_section_status"][payload["section_status"]] >= 1

    async def test_sql_and_fallback_paths_agree(self, session_a):
        summary = await READ_HANDLERS["get_results_summary"](session_a, NoArgs())
        from api.ai_agent_handlers import _results_from_rows

        counters, sections = _results_from_rows(session_a)
        assert sum(counters["section_status"].values()) == summary["n_results"]
        assert len(sections) == summary["n_sections"]

    async def test_worst_first_truncation(self, api_isolated_db):
        session_id = db.create_session()
        rows = []
        for index in range(40):
            rows.append(
                _comparison_row(f"S-{index:02d}", "A", STATUS_CUMPLE, 90.0, bench_num=index + 1)
            )
        rows.append(_comparison_row("S-WORST", "A", STATUS_NO_CUMPLE, 5.0, bench_num=99))
        db.save_results(session_id, rows)
        summary = await READ_HANDLERS["get_results_summary"](session_id, NoArgs())
        assert summary["n_results"] == 41
        assert summary["n_sections"] == 41
        assert summary["sections_truncated"] is True
        assert summary["sections"][0]["name"] == "S-WORST"


@pytest.mark.asyncio
class TestGetProfile:
    async def test_summarized_profile_of_first_section(self, api_isolated_db):
        session_id, _, _ = _seed_meshes_session()
        db.save_sections(session_id, [_section_dict("S-01")])
        db.save_extraction(session_id, "S-01", "design", {"benches": [_bench_dict()]})
        db.save_extraction(session_id, "S-01", "topo", {"benches": [_bench_dict()]})
        db.save_results(session_id, [_comparison_row("S-01", "A", STATUS_NO_CUMPLE, 30.0)])
        profile = await READ_HANDLERS["get_profile"](session_id, SectionIdArgs(section_id="0"))
        assert profile["found"] is True
        assert profile["name"] == "S-01"
        assert profile["sector"] == "A"
        assert profile["n_points_design"] > 0
        assert profile["n_points_topo"] > 0
        assert profile["n_benches_design"] == 1
        assert profile["n_benches_topo"] == 1
        assert profile["floor_elevation"] == pytest.approx(0.0)
        assert profile["worst_status"] == STATUS_NO_CUMPLE
        assert profile["section_score"] == 30.0
        assert "benches_design" not in profile
        assert "benches_topo" not in profile
        assert "design" not in profile
        assert "topo" not in profile

    async def test_out_of_range_and_invalid_ids(self, api_isolated_db):
        session_id = db.create_session()
        missing = await READ_HANDLERS["get_profile"](session_id, SectionIdArgs(section_id="3"))
        assert missing["found"] is False
        assert missing["error"] == "section_id_out_of_range"
        invalid = await READ_HANDLERS["get_profile"](session_id, SectionIdArgs(section_id="abc"))
        assert invalid["found"] is False
        assert invalid["error"] == "invalid_section_id"


@pytest.mark.asyncio
class TestGetDesignAchievement:
    async def test_reuses_core_summary_semantics(self, session_a):
        summary = await READ_HANDLERS["get_design_achievement"](session_a, NoArgs())
        assert summary["n_total_rows"] == 3
        assert summary["n_evaluable"] == 1
        assert summary["global_score"] == 100
        assert summary["crest_pct"] == 100
        assert summary["tolerances_source"] == "core_default"
        assert {entry["sector"] for entry in summary["sectors"]} == {"A", "B"}

    async def test_empty_session_reports_no_data(self, api_isolated_db):
        session_id = db.create_session()
        summary = await READ_HANDLERS["get_design_achievement"](session_id, NoArgs())
        assert summary["status"] == "no_data"
        assert "no_results" in summary["warnings"]
        assert summary["sectors"] == []


@pytest.mark.asyncio
class TestGetProposedCompliance:
    async def test_legacy_rows_reported_as_not_computed(self, session_a):
        result = await READ_HANDLERS["get_proposed_compliance"](session_a, NoArgs())
        assert result["proposal_status"] == "not_computed"
        assert result["n_total_rows"] == 3
        assert result["n_proposal_rows"] == 0
        assert result["n_not_computed_rows"] == 3
        assert result["summary"] is None
        assert "reprocess_required" in result["warnings"]

    async def test_current_rows_feed_compact_summary(self, api_isolated_db):
        session_id = db.create_session()
        row = _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0)
        row.update(
            {
                "proposal_status": "current",
                "proposed_bench_score": 90.0,
                "proposed_evaluable": True,
                "floor_status": "CUMPLE",
                "floor_offset_m": 0.2,
            }
        )
        db.save_results(session_id, [row])
        result = await READ_HANDLERS["get_proposed_compliance"](session_id, NoArgs())
        assert result["proposal_status"] == "current"
        assert result["n_proposal_rows"] == 1
        summary = result["summary"]
        assert summary is not None
        assert summary["n_evaluable"] == 1
        assert summary["per_section_scores"] == {"S-01": 90.0}
        assert summary["per_sections_truncated"] is False
