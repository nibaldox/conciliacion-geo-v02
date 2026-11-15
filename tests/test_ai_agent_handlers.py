"""Tests for the AI agent read-tool handlers (plan section 8, T1).

Every handler is exercised against a per-test isolated SQLite database
(root conftest ``api_isolated_db``): production data is never touched.
Coverage: catalog mapping completeness, session isolation, the read-only
invariant (DB file bytes unchanged), and the small-output size bound.
"""
from __future__ import annotations

import copy
import inspect
import io
import json
from pathlib import Path
from typing import Any, Dict, List, cast

import numpy as np
import pytest
import trimesh

import api.database as db
from api.ai_agent_handlers import READ_HANDLERS
from core.ai_v2.agent.catalog import TOOL_CATALOG
from core.ai_v2.agent.models import (
    AchievementFilterArgs,
    BlastCorrelationArgs,
    BlastDamageArgs,
    MeshIdArgs,
    NoArgs,
    ResultQueryArgs,
    SectionIdArgs,
    ToolRisk,
)
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
    level: str = "1000",
    angle_status: Any = STATUS_CUMPLE,
) -> Dict[str, Any]:
    """Production-shaped comparison row (mirrors core.profile_compliance)."""
    return {
        "section": section,
        "sector": sector,
        "bench_num": bench_num,
        "bench_num_topo": bench_num,
        "type": row_type,
        "level": level,
        "height_status": status,
        "angle_status": angle_status,
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


@pytest.fixture(autouse=True)
def _isolated_db_per_test(api_isolated_db):
    """Give every test in this module a fresh schema before it runs.

    ``session_a``/``session_b`` and several tests call ``db.*`` directly, so
    they must never rely on a developer's local ``data/`` database (CI has
    none). Autouse fixtures are instantiated before requested ones, so the
    patched ``DB_PATH`` and ``init_db()`` are in place by the time any
    session fixture seeds rows.
    """
    yield api_isolated_db


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
    outputs["query_results"] = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
    outputs["get_settings"] = await READ_HANDLERS["get_settings"](session_id, NoArgs())
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
        assert len(expected) == 13

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
        assert len(outputs) == 10
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


_SETTINGS_TOLERANCE_UNITS: Dict[str, str] = {
    "bench_height": "m",
    "face_angle": "deg",
    "berm_width": "m",
    "inter_ramp_angle": "deg",
    "overall_angle": "deg",
    "crest_toe_deviation": "m",
}
_SETTINGS_CLASSIFICATION_RULES: Dict[str, str] = {
    "bench_height": "CUMPLE si la desviación está dentro de −neg/+pos; FUERA DE TOLERANCIA hasta 1,5× ese límite; NO CUMPLE sobre 1,5×",
    "face_angle": "CUMPLE si la desviación está dentro de −neg/+pos; FUERA DE TOLERANCIA hasta 1,5× ese límite; NO CUMPLE sobre 1,5×",
    "berm_width": "CUMPLE si el ancho real es mayor o igual al mínimo; NO CUMPLE si es menor; sin banda FUERA DE TOLERANCIA",
    "crest_toe_deviation": "Desplazamiento de cresta y pata en el cumplimiento propuesto: misma regla de 1,5× que la altura",
    "inter_ramp_angle": "Informativo: se reporta en el Excel y no clasifica bancos",
    "overall_angle": "Informativo: se reporta en el Excel y no clasifica bancos",
}
_CUSTOM_SETTINGS: Dict[str, Any] = {
    "process": {"resolution": 0.25, "face_threshold": 40.0, "berm_threshold": 20.0},
    "tolerances": {
        "bench_height": {"neg": 1.0, "pos": 1.5},
        "face_angle": {"neg": 3.0, "pos": 4.0},
        "berm_width": {"min": 6.0},
        "crest_toe_deviation": {"neg": 0.5, "pos": 0.8},
    },
    "blast": {"rock_density_tm3": 3.0, "height_fallback_m": 12.0, "sector_density": {"A": 2.5}},
}


def _synthetic_blast_holes(count: int) -> List[Dict[str, Any]]:
    return [
        {
            "hole_id": f"H{index:05d}",
            "x": 1000.0 + index * 0.1,
            "y": 2000.0 - index * 0.1,
            "z": 15.0,
            "kg": 120.5,
            "sector": "Norte",
            "section": "S-01",
        }
        for index in range(count)
    ]


@pytest.mark.asyncio
class TestGetSettings:
    async def test_payload_keys_are_ordered_critical_first(self, api_isolated_db):
        session_id = db.create_session()
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        assert list(payload) == ["ok", "tolerances", "classification_rules", "process", "blast"]
        assert payload["ok"] is True
        assert payload["classification_rules"] == _SETTINGS_CLASSIFICATION_RULES

    async def test_classification_rules_hold_six_exact_keys(self, api_isolated_db):
        session_id = db.create_session()
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        rules = payload["classification_rules"]
        assert set(rules) == {
            "bench_height",
            "face_angle",
            "berm_width",
            "crest_toe_deviation",
            "inter_ramp_angle",
            "overall_angle",
        }
        assert "mínimo" in rules["berm_width"]
        assert "1,5" not in rules["berm_width"]
        assert "classification_rule" not in payload

    async def test_payload_with_classification_rules_stays_under_2048_bytes(self, api_isolated_db):
        session_id = db.create_session()
        for settings in (None, _CUSTOM_SETTINGS):
            if settings is not None:
                db.save_settings(session_id, settings)
            payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
            size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            assert size <= 2048, size

    async def test_tolerances_hold_six_keys_each_with_unit(self, api_isolated_db):
        session_id = db.create_session()
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        assert list(payload["tolerances"]) == list(_SETTINGS_TOLERANCE_UNITS)
        for key, unit in _SETTINGS_TOLERANCE_UNITS.items():
            assert list(payload["tolerances"][key])[-1] == "unit", key
            assert payload["tolerances"][key]["unit"] == unit, key

    async def test_custom_tolerances_are_returned_not_defaults(self, api_isolated_db):
        session_id = db.create_session()
        db.save_settings(session_id, _CUSTOM_SETTINGS)
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        assert payload["tolerances"]["bench_height"] == {"neg": 1.0, "pos": 1.5, "unit": "m"}
        assert payload["tolerances"]["face_angle"] == {"neg": 3.0, "pos": 4.0, "unit": "deg"}
        assert payload["tolerances"]["berm_width"] == {"min": 6.0, "unit": "m"}
        assert payload["tolerances"]["crest_toe_deviation"] == {
            "neg": 0.5,
            "pos": 0.8,
            "unit": "m",
        }
        assert payload["tolerances"]["overall_angle"] == {"neg": 2.0, "pos": 2.0, "unit": "deg"}
        assert payload["process"] == {"resolution": 0.25, "face_threshold": 40.0, "berm_threshold": 20.0}
        assert payload["blast"] == {"rock_density_tm3": 3.0, "height_fallback_m": 12.0}

    async def test_no_settings_returns_core_defaults_like_rest(self, api_isolated_db):
        from api.routers.settings import _get_default_settings

        session_id = db.create_session()
        defaults = _get_default_settings()
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        assert payload["process"] == defaults["process"]
        assert payload["blast"] == {
            "rock_density_tm3": defaults["blast"]["rock_density_tm3"],
            "height_fallback_m": defaults["blast"]["height_fallback_m"],
        }
        for key, unit in _SETTINGS_TOLERANCE_UNITS.items():
            entry = dict(payload["tolerances"][key])
            assert entry.pop("unit") == unit, key
            assert entry == defaults["tolerances"][key], key

    async def test_blast_holes_never_reach_the_payload(self, api_isolated_db):
        session_id = db.create_session()
        holes = _synthetic_blast_holes(11000)
        db.save_settings(
            session_id,
            {**_CUSTOM_SETTINGS, "blast_holes": holes, "accepted_rows": holes},
        )
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        text = json.dumps(payload, ensure_ascii=False)
        assert len(text.encode("utf-8")) <= 2048
        assert "blast_holes" not in text
        assert "accepted_rows" not in text
        assert payload["process"]["face_threshold"] == 40.0

    async def test_only_neg_pos_min_entries_are_exposed(self, api_isolated_db):
        session_id = db.create_session()
        db.save_settings(
            session_id,
            {"tolerances": {"face_angle": {"neg": 3.0, "pos": 4.0, "junk": 9.0}}},
        )
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        assert payload["tolerances"]["face_angle"] == {"neg": 3.0, "pos": 4.0, "unit": "deg"}

    async def test_settings_are_scoped_to_own_session(self, api_isolated_db):
        session_a = db.create_session()
        session_b = db.create_session()
        db.save_settings(session_a, _CUSTOM_SETTINGS)
        payload_a = await READ_HANDLERS["get_settings"](session_a, NoArgs())
        payload_b = await READ_HANDLERS["get_settings"](session_b, NoArgs())
        assert payload_a["process"]["face_threshold"] == 40.0
        assert payload_b["process"]["face_threshold"] == 30.0

    async def test_tolerances_survive_observation_compaction(self, api_isolated_db):
        from core.ai_v2.agent.loop import _observation_content

        session_id = db.create_session()
        db.save_settings(session_id, _CUSTOM_SETTINGS)
        payload = await READ_HANDLERS["get_settings"](session_id, NoArgs())
        observation = {**payload, "bulk": [{"pad": "y" * 100} for _ in range(200)]}
        content = json.loads(_observation_content(observation))
        assert content["tolerances"] == payload["tolerances"]


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


@pytest.mark.asyncio
class TestQueryResults:
    async def test_filters_by_level_with_aggregates(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0, bench_num=1, level="3065"),
                _comparison_row("S-01", "A", STATUS_FUERA, 45.0, bench_num=2, row_type="EXTRA", level="3065"),
                _comparison_row("S-02", "B", STATUS_NO_CUMPLE, 20.0, bench_num=3, row_type="MISSING", level="3066"),
                _comparison_row("S-03", "A", STATUS_CUMPLE, 90.0, bench_num=4, level="sin dato"),
            ],
        )
        query = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs(level=["3065"]))
        assert query["n_total_rows"] == 4
        assert query["n_matched_rows"] == 2
        assert query["filters"]["level"] == ["3065"]
        assert query["by_section_status"] == {STATUS_CUMPLE: 1, STATUS_FUERA: 1}
        assert query["by_type"] == {"MATCH": 1, "EXTRA": 1}
        assert query["status_by_parameter"]["height"] == {STATUS_CUMPLE: 1, STATUS_FUERA: 1}
        assert query["status_by_parameter"]["angle"] == {STATUS_CUMPLE: 2}
        by_section = {entry["name"]: entry for entry in query["sections"]}
        assert by_section["S-01"]["n_rows"] == 2
        assert by_section["S-01"]["worst_status"] == STATUS_FUERA
        assert by_section["S-01"]["section_score"] == 85.0
        assert query["levels"] == [
            {"level": "3065", "n_rows": 2},
            {"level": "3066", "n_rows": 1},
            {"level": "sin dato", "n_rows": 1},
        ]
        assert query["rows"] is None
        assert query["units"] == {"height": "m", "angle": "deg", "berm": "m"}
        assert query["warnings"] == []

    async def test_pct_by_parameter_uses_evaluable_denominator(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0, angle_status=STATUS_CUMPLE),
                _comparison_row("S-01", "A", STATUS_FUERA, 45.0, bench_num=2, row_type="EXTRA", angle_status=STATUS_FUERA),
                _comparison_row("S-02", "B", STATUS_NO_CUMPLE, 20.0, bench_num=3, row_type="MISSING", angle_status=STATUS_NO_CUMPLE),
                _comparison_row("S-03", "A", STATUS_CUMPLE, 80.0, bench_num=4, angle_status="-"),
            ],
        )
        query = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        pct_angle = query["pct_by_parameter"]["angle"]
        assert pct_angle["n_evaluable"] == 3
        assert pct_angle["pct"] == {
            STATUS_CUMPLE: 33.3,
            STATUS_FUERA: 33.3,
            STATUS_NO_CUMPLE: 33.3,
        }
        assert abs(sum(pct_angle["pct"].values()) - 100.0) < 0.2
        assert "-" not in pct_angle["pct"]
        assert "sin_medir" not in pct_angle["pct"]
        assert query["status_by_parameter"]["angle"] == {
            STATUS_CUMPLE: 1,
            STATUS_FUERA: 1,
            STATUS_NO_CUMPLE: 1,
            "-": 1,
        }

    async def test_pct_by_parameter_zero_evaluable_when_all_unmeasured(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0, angle_status="-"),
                _comparison_row("S-01", "A", STATUS_FUERA, 45.0, bench_num=2, row_type="EXTRA", angle_status=None),
            ],
        )
        query = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        assert query["pct_by_parameter"]["angle"] == {"n_evaluable": 0, "pct": {}}
        assert query["status_by_parameter"]["angle"] == {"-": 1, "sin_medir": 1}

    async def test_filters_by_bench_and_sector(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0, bench_num=1),
                _comparison_row("S-01", "A", STATUS_FUERA, 45.0, bench_num=2, row_type="EXTRA"),
                _comparison_row("S-02", "B", STATUS_NO_CUMPLE, 20.0, bench_num=2, row_type="MISSING"),
            ],
        )
        query = await READ_HANDLERS["query_results"](
            session_id, ResultQueryArgs(bench=[2], sector=["A"])
        )
        assert query["n_total_rows"] == 3
        assert query["n_matched_rows"] == 1
        assert query["by_type"] == {"EXTRA": 1}
        assert query["filters"] == {
            "sector": ["A"],
            "section": [],
            "level": [],
            "bench": [2],
            "parameter": None,
            "status": None,
        }

    async def test_parameter_and_status_filter(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0, berm_status="-"),
                _comparison_row("S-01", "A", STATUS_CUMPLE, 80.0, bench_num=2),
                _comparison_row("S-02", "A", STATUS_FUERA, 45.0, bench_num=3, row_type="EXTRA"),
            ],
        )
        parameter_only = await READ_HANDLERS["query_results"](
            session_id, ResultQueryArgs(parameter="berm")
        )
        assert parameter_only["n_matched_rows"] == 3
        berm = await READ_HANDLERS["query_results"](
            session_id, ResultQueryArgs(parameter="berm", status="-")
        )
        assert berm["n_matched_rows"] == 1
        assert berm["status_by_parameter"]["berm"] == {"-": 1}
        assert berm["by_section_status"] == {STATUS_CUMPLE: 1}
        height = await READ_HANDLERS["query_results"](
            session_id, ResultQueryArgs(parameter="height", status=STATUS_FUERA)
        )
        assert height["n_matched_rows"] == 1
        assert height["by_section_status"] == {STATUS_FUERA: 1}

    async def test_include_rows_respects_row_limit_and_rounds(self, api_isolated_db):
        session_id = db.create_session()
        row = _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0)
        row.update(
            {
                "height_design": 15.0,
                "height_real": 15.123456,
                "height_dev": 0.123456,
                "angle_design": 65.54,
                "angle_real": 66.1234,
                "angle_dev": 0.568,
                "berm_design": 8.0,
                "berm_real": 8.98765,
                "berm_dev": 0.98765,
                "bench_score": 88.888888,
            }
        )
        db.save_results(
            session_id,
            [
                row,
                _comparison_row("S-01", "A", STATUS_FUERA, 45.0, bench_num=2, row_type="EXTRA"),
                _comparison_row("S-02", "B", STATUS_NO_CUMPLE, 20.0, bench_num=3, row_type="MISSING"),
            ],
        )
        query = await READ_HANDLERS["query_results"](
            session_id, ResultQueryArgs(include_rows=True, row_limit=2)
        )
        assert query["n_matched_rows"] == 3
        assert len(query["rows"]) == 2
        first = query["rows"][0]
        assert first["section"] == "S-01"
        assert first["bench_num"] == 1
        assert first["level"] == "1000"
        assert set(first) == {
            "section",
            "bench_num",
            "level",
            "type",
            "height_design",
            "height_real",
            "height_dev",
            "height_status",
            "angle_design",
            "angle_real",
            "angle_dev",
            "angle_status",
            "berm_design",
            "berm_real",
            "berm_dev",
            "berm_status",
            "bench_score",
        }
        assert first["height_design"] == 15.0
        assert first["height_real"] == 15.12
        assert first["height_dev"] == 0.12
        assert first["angle_design"] == 65.5
        assert first["angle_dev"] == 0.6
        assert first["berm_real"] == 8.99
        assert first["berm_dev"] == 0.99
        assert first["bench_score"] == 88.89

    async def test_query_is_scoped_to_own_session(self, session_a, session_b):
        query_b = await READ_HANDLERS["query_results"](session_b, ResultQueryArgs(level=["1000"]))
        assert query_b["n_total_rows"] == 3
        assert query_b["n_matched_rows"] == 3
        assert {entry["name"] for entry in query_b["sections"]} == {"S-99"}
        foreign = await READ_HANDLERS["query_results"](session_b, ResultQueryArgs(section=["S-01"]))
        assert foreign["n_total_rows"] == 3
        assert foreign["n_matched_rows"] == 0
        assert foreign["warnings"] == ["all_rows_filtered_out"]
        query_a = await READ_HANDLERS["query_results"](session_a, ResultQueryArgs(sector=["Z"]))
        assert query_a["n_matched_rows"] == 0
        assert query_a["levels"] == [{"level": "1000", "n_rows": 3}]

    async def test_default_payload_stays_under_size_bound(self, session_a):
        payload = await READ_HANDLERS["query_results"](session_a, ResultQueryArgs())
        serialized = json.dumps(payload, ensure_ascii=False)
        assert len(serialized.encode("utf-8")) < SIZE_BOUND_BYTES

    async def test_design_achievement_with_level_filter(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _comparison_row("S-01", "A", STATUS_CUMPLE, 85.0, bench_num=1, level="1000"),
                _comparison_row("S-01", "A", STATUS_FUERA, 45.0, bench_num=2, level="2000"),
            ],
        )
        unfiltered = await READ_HANDLERS["get_design_achievement"](session_id, NoArgs())
        assert unfiltered["n_total_rows"] == 2
        assert unfiltered["n_evaluable"] == 2
        filtered = await READ_HANDLERS["get_design_achievement"](
            session_id, AchievementFilterArgs(level=["1000"])
        )
        assert filtered["n_total_rows"] == 1
        assert filtered["n_evaluable"] == 1
        assert filtered["global_score"] == 100
        assert filtered["crest_pct"] == 100
        assert {entry["sector"] for entry in filtered["sectors"]} == {"A"}

    async def test_all_rows_filtered_out_warning(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(session_id, [_comparison_row("S-01", "A", STATUS_CUMPLE, 85.0)])
        query = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs(level=["9999"]))
        assert query["n_total_rows"] == 1
        assert query["n_matched_rows"] == 0
        assert query["warnings"] == ["all_rows_filtered_out"]
        assert query["by_section_status"] == {}
        assert query["sections"] == []
        assert query["levels"] == [{"level": "1000", "n_rows": 1}]

    async def test_no_results_warning_on_empty_session(self, api_isolated_db):
        session_id = db.create_session()
        query = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs(level=["3065"]))
        assert query["n_total_rows"] == 0
        assert query["n_matched_rows"] == 0
        assert query["warnings"] == ["no_results"]
        assert query["levels"] == []


# ---------------------------------------------------------------------------
# Dashboard weighted score (parity with Dashboard.tsx computeGlobalScore)
# ---------------------------------------------------------------------------


def _scored_row(
    section: str,
    bench_score: float,
    *,
    sector: str = "A",
    level: str = "3065",
    bench_num: int = 1,
    row_type: str = "MATCH",
) -> Dict[str, Any]:
    """MATCH-shaped row carrying an explicit bench_score (dashboard input)."""
    row = _comparison_row(
        section, sector, STATUS_CUMPLE, 85.0,
        bench_num=bench_num, row_type=row_type, level=level,
    )
    row["bench_score"] = bench_score
    return row


def _seed_weighted_session() -> str:
    """Section A: 100 + 50; section B: 0; EXTRA/MISSING rows must not count."""
    session_id = db.create_session()
    db.save_results(
        session_id,
        [
            _scored_row("A", 100.0, bench_num=1),
            _scored_row("A", 50.0, bench_num=2),
            _scored_row("B", 0.0, sector="B"),
            _scored_row("A", 100.0, bench_num=3, row_type="EXTRA"),
            _scored_row("A", 100.0, bench_num=4, row_type="MISSING"),
        ],
    )
    return session_id


@pytest.mark.asyncio
class TestDashboardWeightedScore:
    async def test_weighted_score_over_synthetic_rows(self, api_isolated_db):
        from core.report_data import compute_dashboard_weighted_score

        session_id = _seed_weighted_session()
        rows = db.get_results(session_id)
        rows.append(
            {
                "section": "C",
                "sector": "A",
                "type": "MATCH",
                "level": "3065",
                "bench_num": 5,
                "height_status": STATUS_CUMPLE,
                "angle_status": STATUS_CUMPLE,
                "berm_status": "-",
                "bench_score": None,
            }
        )
        weighted = compute_dashboard_weighted_score(rows)
        assert weighted["global_score"] == pytest.approx(37.5)
        assert weighted["n_profiles"] == 2
        assert weighted["n_benches"] == 3
        assert weighted["by_section"] == {"A": 75.0, "B": 0.0}
        assert weighted["weights"] == {"berm": 60, "angle": 10, "height": 30}
        assert weighted["definition"]

        query = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        assert query["weighted_score"] == weighted

    async def test_level_filter_reduces_weighted_score(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _scored_row("A", 100.0, level="3065", bench_num=1),
                _scored_row("A", 50.0, level="3066", bench_num=2),
                _scored_row("B", 0.0, sector="B", level="3066"),
            ],
        )
        unfiltered = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        assert unfiltered["weighted_score"]["global_score"] == pytest.approx(37.5)
        assert unfiltered["weighted_score"]["n_benches"] == 3
        filtered = await READ_HANDLERS["query_results"](
            session_id, ResultQueryArgs(level=["3066"])
        )
        assert filtered["weighted_score"]["global_score"] == pytest.approx(25.0)
        assert filtered["weighted_score"]["global_score"] < unfiltered["weighted_score"]["global_score"]
        assert filtered["weighted_score"]["n_profiles"] == 2
        assert filtered["weighted_score"]["n_benches"] == 2
        assert filtered["weighted_score"]["by_section"] == {"A": 50.0, "B": 0.0}

    async def test_weighted_score_warning_when_no_scoreable_benches(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(session_id, [_scored_row("A", 100.0, row_type="EXTRA")])
        query = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        assert query["n_matched_rows"] == 1
        assert query["weighted_score"]["global_score"] is None
        assert query["weighted_score"]["n_benches"] == 0
        assert query["warnings"] == ["no hay bancos MATCH puntuables con los filtros aplicados"]

    async def test_design_achievement_score_kind_and_weighted_score(self, api_isolated_db):
        session_id = _seed_weighted_session()
        achievement = await READ_HANDLERS["get_design_achievement"](session_id, NoArgs())
        assert achievement["score_kind"] == "logro_diseno"
        assert achievement["global_score"] is not None
        assert achievement["global_score"] != achievement["weighted_score"]["global_score"]
        assert achievement["weighted_score"]["global_score"] == pytest.approx(37.5)
        assert achievement["weighted_score"]["n_profiles"] == 2
        assert achievement["weighted_score"]["n_benches"] == 3

    async def test_design_achievement_level_filter_feeds_weighted_score(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _scored_row("A", 100.0, level="3065", bench_num=1),
                _scored_row("A", 50.0, level="3066", bench_num=2),
            ],
        )
        filtered = await READ_HANDLERS["get_design_achievement"](
            session_id, AchievementFilterArgs(level=["3065"])
        )
        assert filtered["score_kind"] == "logro_diseno"
        assert filtered["weighted_score"]["global_score"] == pytest.approx(100.0)
        assert filtered["weighted_score"]["n_profiles"] == 1
        assert filtered["weighted_score"]["n_benches"] == 1

    async def test_include_rows_payload_stays_under_size_bound(self, api_isolated_db):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _scored_row(f"S-{index:02d}", 80.0 + index, bench_num=index + 1)
                for index in range(4)
            ],
        )
        payload = await READ_HANDLERS["query_results"](
            session_id, ResultQueryArgs(include_rows=True, row_limit=10)
        )
        assert len(payload["rows"]) == 4
        serialized = json.dumps(payload, ensure_ascii=False)
        assert len(serialized.encode("utf-8")) < SIZE_BOUND_BYTES
        assert "by_section" in payload["weighted_score"]

    async def test_by_section_dropped_when_payload_exceeds_bound(
        self, api_isolated_db, monkeypatch
    ):
        import api.ai_agent_handlers as handlers_module

        session_id = _seed_weighted_session()
        full = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        full_size = len(json.dumps(full, ensure_ascii=False).encode("utf-8"))
        assert "by_section" in full["weighted_score"]
        monkeypatch.setattr(handlers_module, "_MAX_PAYLOAD_BYTES", full_size)
        trimmed = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        assert "by_section" not in trimmed["weighted_score"]
        kept = trimmed["weighted_score"]
        assert kept["global_score"] == full["weighted_score"]["global_score"]
        assert kept["n_profiles"] == full["weighted_score"]["n_profiles"]
        assert kept["n_benches"] == full["weighted_score"]["n_benches"]
        assert kept["weights"] == full["weighted_score"]["weights"]
        assert kept["definition"] == full["weighted_score"]["definition"]
        trimmed_size = len(json.dumps(trimmed, ensure_ascii=False).encode("utf-8"))
        assert trimmed_size < full_size
        assert trimmed["n_matched_rows"] == full["n_matched_rows"]
        assert trimmed["warnings"] == full["warnings"]


@pytest.mark.asyncio
class TestQueryResultsPayloadPriority:
    async def test_payload_key_order_puts_score_first(self, api_isolated_db):
        session_id = _seed_weighted_session()
        payload = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        assert list(payload.keys())[:3] == [
            "weighted_score",
            "n_total_rows",
            "n_matched_rows",
        ]
        serialized = json.dumps(payload, ensure_ascii=False)
        assert serialized.startswith('{"weighted_score":')
        for early in ("n_matched_rows", "pct_by_parameter", "status_by_parameter"):
            assert serialized.index(f'"{early}"') < serialized.index('"sections"')

    async def test_large_session_payload_fits_budget_with_critical_keys(
        self, api_isolated_db
    ):
        session_id = db.create_session()
        db.save_results(
            session_id,
            [
                _scored_row(
                    f"S-{index:04d}",
                    100.0 if index % 2 == 0 else 50.0,
                    level=str(3065 + index % 80),
                    bench_num=index % 4 + 1,
                )
                for index in range(120)
            ],
        )
        payload = await READ_HANDLERS["query_results"](session_id, ResultQueryArgs())
        assert payload["n_matched_rows"] == 120
        assert payload["weighted_score"]["global_score"] == pytest.approx(75.0)
        assert payload["weighted_score"]["n_profiles"] == 120
        serialized = json.dumps(payload, ensure_ascii=False)
        assert len(serialized.encode("utf-8")) < SIZE_BOUND_BYTES
        head = serialized[:4000]
        for critical in (
            '"n_total_rows"',
            '"n_matched_rows"',
            '"weighted_score"',
            '"global_score"',
            '"pct_by_parameter"',
            '"status_by_parameter"',
        ):
            assert critical in head


@pytest.mark.asyncio
class TestNominalQueryLevels:
    async def test_exact_level_cap_is_reported(self, api_isolated_db):
        sid = db.create_session()
        db.save_results(sid, [_comparison_row("S", "A", STATUS_CUMPLE, 80, bench_num=i + 1, level=str(3000 + i)) for i in range(62)])
        result = await READ_HANDLERS["query_results"](sid, ResultQueryArgs())
        assert result["levels_truncated"] is True

    async def test_labels_match_export_endpoint_and_filters(self, api_test_client):
        sid = db.create_session()
        db.save_results(sid, [_comparison_row(f"S-{i}", sector, STATUS_CUMPLE, 80, bench_num=i + 1, level=level) for i, (sector, level) in enumerate([( "A", "3065"), ("A", "3066"), ("B", "3095")])])
        response = api_test_client.get("/api/v1/export/levels", headers={"X-Session-ID": sid})
        assert response.status_code == 200
        result = await READ_HANDLERS["query_results"](sid, ResultQueryArgs())
        expected = {s["sector"]: [level["label"] for level in s["levels"]] for s in response.json()["sectors"]}
        assert {sector: [level["label"] for level in levels] for sector, levels in result["nominal_levels"].items()} == expected
        filtered = await READ_HANDLERS["query_results"](sid, ResultQueryArgs(sector=["A"], level=["3065"]))
        assert filtered["n_matched_rows"] == 1
        assert set(filtered["nominal_levels"]) == {"A"}

    async def test_large_payload_budget_and_priority(self, api_isolated_db):
        sid = db.create_session()
        db.save_results(sid, [_comparison_row(f"S-{i}", "A", STATUS_CUMPLE, 80, bench_num=i + 1, level=str(3000 + i * 15)) for i in range(150)])
        result = await READ_HANDLERS["query_results"](sid, ResultQueryArgs(include_rows=True, row_limit=50))
        text = json.dumps(result, ensure_ascii=False)
        print(f"large payload bytes={len(text.encode('utf-8'))}; chars={len(text)}")
        assert len(text.encode("utf-8")) <= 4096
        for key in ("weighted_score", "pct_by_parameter", "nominal_levels", "levels_truncated"):
            assert text.index(f'"{key}"') < 4000
        assert result["levels_truncated"] is True
        assert result["nominal_levels_truncated"] is True

    async def test_budget_trim_marks_exact_levels_below_cap(self, api_isolated_db, monkeypatch):
        import api.ai_agent_handlers as handlers

        sid = db.create_session()
        db.save_results(sid, [_comparison_row("S", "A", STATUS_CUMPLE, 80, bench_num=i + 1, level=str(3000 + 15 * i)) for i in range(20)])
        full = await READ_HANDLERS["query_results"](sid, ResultQueryArgs())
        assert full["levels_truncated"] is False
        monkeypatch.setattr(handlers, "_MAX_PAYLOAD_BYTES", 1700)
        cut = await READ_HANDLERS["query_results"](sid, ResultQueryArgs())
        assert cut["levels_truncated"] is True
        assert cut["nominal_levels_truncated"] is True
        kept = cut["nominal_levels"].get("A", [])
        assert kept == full["nominal_levels"]["A"][:len(kept)]
        assert len(json.dumps(cut, ensure_ascii=False).encode("utf-8")) < 1700


# ---------------------------------------------------------------------------
# get_blast_summary (T4.1a): audited compact digest of the blast holes
# ---------------------------------------------------------------------------

_BLAST_POLICY = "Explosivo desconocido: sin energía, nunca se asume ANFO"

_BLAST_GEOMETRY: Dict[str, Any] = {
    "geometry_configuration_version": "2.0",
    "geometry_user_confirmed": True,
    "inclination_source_column": "Inclinacion_real",
    "inclination_convention": "FROM_VERTICAL",
    "inclination_sign_convention": "ABSOLUTE_VALUE",
    "inclination_unit": "DEGREES",
    "inclination_source_rule": "",
    "azimuth_source_column": "Azimuth_real",
    "azimuth_convention": "CLOCKWISE_FROM_NORTH",
    "azimuth_unit": "DEGREES",
}

_BLAST_UPLOAD_META: Dict[str, Any] = {
    "consolidation_report": {
        "rows_in": 20939,
        "holes_out": 14204,
        "exact_copies_removed": 6702,
        "holes_with_decks": 33,
        "conflicts": [],
    },
    "footprint_report": {
        "mode": "estimated_hull",
        "n_estimated": 99,
        "n_user": 0,
        "n_missing": 0,
    },
}


def _blast_hole(
    index: int,
    explosive_status: str = "UNVALIDATED_REFERENCE",
    bench_height_m: Any = 15.0,
) -> Dict[str, Any]:
    confirmed = bench_height_m is not None
    return {
        "id_pozo": str(6400000 + index),
        "source_row_index": index,
        "X": 92300.0 + index,
        "Y": 21300.0 + index,
        "Z_collar": 3000.0,
        "bench_height_m": bench_height_m,
        "bench_height_status": "PROVIDED" if confirmed else "MISSING",
        "bench_height_source": "data_column" if confirmed else "",
        "bench_height_assumption_flag": not confirmed,
        "bench_height_user_confirmed": confirmed,
        "explosive_status": explosive_status,
        "explosive_source": "" if explosive_status == "UNKNOWN" else "Catálogo ENAEX",
        "pf_voronoi_bench_status": "MISSING_DENSITY",
    }


def _seed_blast_session(
    holes: List[Dict[str, Any]],
    *,
    blast: Any = None,
    event_warnings: Any = None,
    geometry: Any = None,
    upload_meta: Any = None,
) -> str:
    from core.blast_hole_consolidation import BLAST_ALGORITHM_VERSION

    session_id = db.create_session()
    settings: Dict[str, Any] = {
        "blast_holes": holes,
        "blast_algorithm_version": BLAST_ALGORITHM_VERSION,
        "blast_upload_meta": copy.deepcopy(
            _BLAST_UPLOAD_META if upload_meta is None else upload_meta
        ),
        "geometry_configuration": copy.deepcopy(
            _BLAST_GEOMETRY if geometry is None else geometry
        ),
        "event_warnings": event_warnings if event_warnings is not None else [],
    }
    if blast is not None:
        settings["blast"] = blast
    db.save_settings(session_id, settings)
    return session_id


async def _blast_summary(session_id: str) -> Dict[str, Any]:
    return await READ_HANDLERS["get_blast_summary"](session_id, NoArgs())


def _json_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


@pytest.mark.asyncio
class TestGetBlastSummary:
    async def test_session_without_holes_reports_no_blast_data(self, api_isolated_db):
        session_id = db.create_session()
        payload = await _blast_summary(session_id)
        assert payload == {
            "ok": False,
            "error": "no_blast_data",
            "message": "La sesión no tiene pozos de tronadura cargados.",
        }

    async def test_empty_hole_list_reports_no_blast_data(self, api_isolated_db):
        session_id = _seed_blast_session([])
        payload = await _blast_summary(session_id)
        assert payload["ok"] is False
        assert payload["error"] == "no_blast_data"

    async def test_defaulted_density_is_never_valid_and_fits_budget(self, api_isolated_db):
        from core.config import BLAST

        holes = [_blast_hole(i) for i in range(11184)]
        session_id = _seed_blast_session(holes)
        payload = await _blast_summary(session_id)
        assert payload["ok"] is True
        assert payload["n_holes"] == 11184
        assert payload["rock_density"] == {
            "value": BLAST.rock_density_tm3,
            "unit": "t/m³",
            "status": "DEFAULT",
            "source": "core.config default",
        }
        assert payload["rock_density"]["value"] == 2.7
        assert "MISSING_DENSITY" in payload["warnings"]
        assert _json_size(payload) <= 4096

    async def test_user_density_is_reported_as_saved(self, api_isolated_db):
        session_id = _seed_blast_session(
            [_blast_hole(i) for i in range(50)], blast={"rock_density_tm3": 2.6}
        )
        payload = await _blast_summary(session_id)
        assert payload["rock_density"] == {
            "value": 2.6,
            "unit": "t/m³",
            "status": "SAVED",
            "source": "settings.blast.rock_density_tm3",
        }
        assert "MISSING_DENSITY" not in payload["warnings"]
        assert "DENSITY_EQUALS_DEFAULT" not in payload["warnings"]

    async def test_stored_value_equal_to_core_default_is_saved_and_flagged(self, api_isolated_db):
        session_id = _seed_blast_session(
            [_blast_hole(i) for i in range(50)], blast={"rock_density_tm3": 2.7}
        )
        payload = await _blast_summary(session_id)
        assert payload["rock_density"]["status"] == "SAVED"
        assert payload["rock_density"]["source"] == "settings.blast.rock_density_tm3"
        assert "DENSITY_EQUALS_DEFAULT" in payload["warnings"]
        assert "MISSING_DENSITY" not in payload["warnings"]

    async def test_stored_zero_density_is_invalid_and_missing(self, api_isolated_db):
        session_id = _seed_blast_session(
            [_blast_hole(i) for i in range(50)], blast={"rock_density_tm3": 0.0}
        )
        payload = await _blast_summary(session_id)
        assert payload["rock_density"]["status"] == "INVALID"
        assert payload["rock_density"]["value"] is None
        assert "INVALID_DENSITY" in payload["warnings"]
        assert "MISSING_DENSITY" in payload["warnings"]

    async def test_unknown_explosives_are_counted_and_never_anfo(self, api_isolated_db):
        holes = [_blast_hole(i, explosive_status="UNKNOWN") for i in range(199)]
        holes += [_blast_hole(199 + i) for i in range(300)]
        session_id = _seed_blast_session(holes)
        payload = await _blast_summary(session_id)
        assert payload["explosives"] == {
            "unknown_holes": 199,
            "unvalidated_reference_holes": 300,
            "unknown_policy": _BLAST_POLICY,
        }
        strings_with_anfo = [text for text in _walk_strings(payload) if "ANFO" in text]
        assert strings_with_anfo == [_BLAST_POLICY]
        assert "ANFO" not in json.dumps(
            {k: v for k, v in payload.items() if k != "explosives"}, ensure_ascii=False
        )

    async def test_heavy_work_runs_through_run_blast_limited(self, api_isolated_db, monkeypatch):
        from api import _async_db

        original = _async_db.run_blast_limited
        calls = []

        async def spy(fn, /, *args):
            calls.append((fn, args))
            return await original(fn, *args)

        monkeypatch.setattr(_async_db, "run_blast_limited", spy)
        session_id = _seed_blast_session([_blast_hole(i) for i in range(5)])
        payload = await _blast_summary(session_id)
        assert payload["ok"] is True
        assert len(calls) == 1
        assert calls[0][1] == (session_id,)

    async def test_hole_records_are_never_mutated(self, api_isolated_db):
        holes = [_blast_hole(i, explosive_status="UNKNOWN" if i % 7 == 0 else "UNVALIDATED_REFERENCE") for i in range(200)]
        session_id = _seed_blast_session(holes, blast={"rock_density_tm3": 2.6})
        before = copy.deepcopy(db.get_settings(session_id))
        await _blast_summary(session_id)
        assert db.get_settings(session_id) == before

    async def test_key_order_follows_the_contract(self, api_isolated_db):
        session_id = _seed_blast_session([_blast_hole(i) for i in range(5)])
        payload = await _blast_summary(session_id)
        assert list(payload) == [
            "ok",
            "data_status",
            "n_holes",
            "rock_density",
            "bench_height",
            "inclination",
            "explosives",
            "dedup",
            "footprint",
            "warnings",
        ]

    async def test_bench_height_comes_from_the_confirmed_hole_attribute(self, api_isolated_db):
        session_id = _seed_blast_session([_blast_hole(i) for i in range(20)])
        payload = await _blast_summary(session_id)
        assert payload["bench_height"] == {
            "value": 15.0,
            "unit": "m",
            "status": "PROVIDED",
            "source": "data_column",
            "user_confirmed": True,
        }

    async def test_missing_bench_height_is_null_and_flagged(self, api_isolated_db):
        holes = [_blast_hole(i, bench_height_m=None) for i in range(20)]
        session_id = _seed_blast_session(holes)
        payload = await _blast_summary(session_id)
        assert payload["bench_height"] == {
            "value": None,
            "unit": "m",
            "status": "MISSING",
            "source": "",
            "user_confirmed": False,
        }
        assert "MISSING_BENCH_HEIGHT" in payload["warnings"]

    async def test_mixed_bench_heights_are_null_and_flagged(self, api_isolated_db):
        holes = [_blast_hole(i, bench_height_m=15.0) for i in range(10)]
        holes += [_blast_hole(10 + i, bench_height_m=12.0) for i in range(10)]
        session_id = _seed_blast_session(holes)
        payload = await _blast_summary(session_id)
        assert payload["bench_height"]["value"] is None
        assert payload["bench_height"]["status"] == "MIXED"
        assert payload["bench_height"]["user_confirmed"] is False
        assert "MIXED_BENCH_HEIGHT" in payload["warnings"]

    async def test_partially_missing_bench_height_is_not_confirmed(self, api_isolated_db):
        holes = [_blast_hole(i) for i in range(10)]
        holes += [_blast_hole(10 + i, bench_height_m=None) for i in range(5)]
        session_id = _seed_blast_session(holes)
        payload = await _blast_summary(session_id)
        assert payload["bench_height"]["value"] == 15.0
        assert payload["bench_height"]["status"] == "MIXED"
        assert payload["bench_height"]["user_confirmed"] is False
        assert "MISSING_BENCH_HEIGHT" in payload["warnings"]

    async def test_inclination_reads_geometry_configuration(self, api_isolated_db):
        session_id = _seed_blast_session([_blast_hole(i) for i in range(5)])
        payload = await _blast_summary(session_id)
        assert payload["inclination"] == {
            "convention": "FROM_VERTICAL",
            "sign": "ABSOLUTE_VALUE",
            "unit": "DEGREES",
            "user_confirmed": True,
        }

    async def test_dedup_and_footprint_counts_come_from_upload_meta(self, api_isolated_db):
        session_id = _seed_blast_session([_blast_hole(i) for i in range(5)])
        payload = await _blast_summary(session_id)
        assert payload["data_status"] == "current"
        assert payload["dedup"] == {
            "rows_in": 20939,
            "exact_copies_removed": 6702,
            "holes_with_decks": 33,
            "conflicts": 0,
        }
        assert payload["footprint"] == {
            "mode": "estimated_hull",
            "n_estimated": 99,
            "n_user": 0,
            "n_missing": 0,
        }

    async def test_warnings_are_deduplicated_and_capped_at_ten(self, api_isolated_db):
        event_warnings = [{"warning_code": f"CODE_{i}"} for i in range(12)]
        event_warnings += [{"warning_code": "CODE_0"}, {"warning_code": None}]
        session_id = _seed_blast_session([_blast_hole(i) for i in range(5)], event_warnings=event_warnings)
        payload = await _blast_summary(session_id)
        assert len(payload["warnings"]) == 10
        assert payload["warnings"][0] == "MISSING_DENSITY"
        assert len(set(payload["warnings"])) == 10

    async def test_digest_keeps_its_magnitudes_through_history_compaction(self, api_isolated_db):
        from api.ai_agent_conversations import _compact_tool_content

        holes = [
            _blast_hole(i, explosive_status="UNKNOWN" if i < 199 else "UNVALIDATED_REFERENCE")
            for i in range(14204)
        ]
        event_warnings = [
            {"warning_code": "EXPLOSIVE_UNKNOWN"},
            {"warning_code": "EXPLOSIVE_UNVALIDATED_REFERENCE"},
            {"warning_code": "INCLINATION_ALL_ZERO"},
        ]
        session_id = _seed_blast_session(holes, event_warnings=event_warnings)
        payload = await _blast_summary(session_id)
        compacted = _compact_tool_content(json.dumps(payload, ensure_ascii=False))
        assert len(compacted) <= 600
        restored = json.loads(compacted)
        assert restored["rock_density"]["status"] == "DEFAULT"
        assert restored["bench_height"]["status"] == "PROVIDED"
        assert restored["inclination"]["convention"] == "FROM_VERTICAL"
        assert restored["explosives"]["unknown_holes"] == 199
        assert restored["explosives"]["unknown_policy"] == _BLAST_POLICY
        assert "MISSING_DENSITY" in restored["warnings"]

    async def test_full_real_scale_payload_stays_under_budget(self, api_isolated_db):
        holes = [
            _blast_hole(i, explosive_status="UNKNOWN" if i < 199 else "UNVALIDATED_REFERENCE")
            for i in range(14204)
        ]
        event_warnings = [
            {"warning_code": "EXPLOSIVE_UNKNOWN"},
            {"warning_code": "EXPLOSIVE_UNVALIDATED_REFERENCE"},
            {"warning_code": "INCLINATION_ALL_ZERO"},
        ]
        session_id = _seed_blast_session(holes, event_warnings=event_warnings)
        payload = await _blast_summary(session_id)
        assert _json_size(payload) <= 4096
        assert payload["explosives"]["unknown_holes"] == 199
        assert payload["explosives"]["unvalidated_reference_holes"] == 14005
        assert payload["warnings"] == [
            "MISSING_DENSITY",
            "EXPLOSIVE_UNKNOWN",
            "EXPLOSIVE_UNVALIDATED_REFERENCE",
            "INCLINATION_ALL_ZERO",
        ]


# ---------------------------------------------------------------------------
# get_blast_correlation / get_blast_damage_model (T4.1b)
# ---------------------------------------------------------------------------

_CORRELATION_CSV_HEADER = (
    "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,"
    "longitud_real,Kilos_Cargados_real,Taco_m,Burden,Esp,Diam_mm"
)

_CORRELATION_UPLOAD_FORM: Dict[str, str] = {
    "geometry_user_confirmed": "true",
    "incl_convention": "from_vertical",
    "incl_sign_convention": "ABSOLUTE_VALUE",
    "az_convention": "CLOCKWISE_FROM_NORTH",
    "angle_unit": "degrees",
    "bench_height_m": "15.0",
    "incl_source_column": "Inclinacion_real",
    "az_source_column": "Azimuth_real",
}

_NO_BLAST_MESSAGE = "La sesión no tiene pozos de tronadura cargados."
_CORRELATION_KEYS = {"carga", "descarga", "kg_per_meter", "kg_per_meter_loaded_column"}


def _grid_holes(columns: int, rows: int, x0: float = 1000.0, y0: float = 2000.0) -> List[tuple]:
    """Vertical holes on a grid: column k sits at x0 + 2k with charge 100 + 50k."""
    return [
        (x0 + 2.0 * column, y0 + 1.0 * row, 100.0 + 50.0 * column)
        for row in range(rows)
        for column in range(columns)
    ]


def _upload_holes(client, session_id: str, holes: List[tuple]) -> None:
    lines = [_CORRELATION_CSV_HEADER]
    lines += [
        f"{x:.3f},{y:.3f},100,0.0,0.0,12.0,{kilos:.1f},1.5,3.0,4.0,200"
        for x, y, kilos in holes
    ]
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    response = client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(payload), "text/csv")},
        data={"session_id": session_id, **_CORRELATION_UPLOAD_FORM},
    )
    assert response.status_code == 200, response.text


def _section(name: str, x: float, y0: float = 2000.0, length: float = 20.0) -> Dict[str, Any]:
    return {
        "name": name,
        "origin": [float(x), float(y0)],
        "azimuth": 0.0,
        "length": float(length),
        "length_up": None,
        "length_down": None,
        "sector": "Norte",
    }


def _delta_row(section: str, crest: float) -> Dict[str, Any]:
    row = _comparison_row(section, "Norte", STATUS_CUMPLE, 85.0)
    row["delta_crest"] = crest
    return row


def _six_column_fixture():
    holes = _grid_holes(columns=6, rows=10)
    sections = [_section(f"S-0{k + 1}", 1000.0 + 2.0 * k) for k in range(6)]
    results = [_delta_row(f"S-0{k + 1}", 0.4 + 0.2 * k) for k in range(6)]
    return holes, sections, results


def _seed_projection(client, holes, sections, results, *, blast=None, sector_density=None) -> str:
    session_id = db.create_session()
    _upload_holes(client, session_id, holes)
    db.save_sections(session_id, sections)
    db.save_results(session_id, results)
    if blast is not None or sector_density is not None:
        settings = db.get_settings(session_id)
        settings["blast"] = {**(blast or {}), **({"sector_density": sector_density} if sector_density else {})}
        db.save_settings(session_id, settings)
    return session_id


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _row(payload: Dict[str, Any], section: str) -> Dict[str, Any]:
    return next(row for row in payload["rows"] if row["section"] == section)


@pytest.mark.asyncio
class TestGetBlastCorrelation:
    async def test_session_without_holes_reports_no_blast_data(self, api_isolated_db):
        session_id = db.create_session()
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert payload == {"ok": False, "error": "no_blast_data", "message": _NO_BLAST_MESSAGE}

    async def test_holes_without_sections_or_results_report_no_results(self, api_test_client):
        session_id = db.create_session()
        _upload_holes(api_test_client, session_id, _grid_holes(columns=2, rows=2))
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert payload["ok"] is False
        assert payload["error"] == "no_results"
        assert payload["message"]

    async def test_default_density_is_default_and_pf_voronoi_is_never_valid(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert payload["ok"] is True
        assert payload["magnitudes"]["rock_density"] == {
            "value": 2.7,
            "unit": "t/m³",
            "status": "DEFAULT",
            "source": "core.config default",
        }
        assert "MISSING_DENSITY" in payload["warnings"]
        statuses = [row["pf_voronoi_status"] for row in payload["rows"]]
        assert statuses and all("VALID" not in status for status in statuses)
        assert all(status.split(",")[0] == "MISSING_DENSITY" for status in statuses)

    async def test_saved_density_is_used_and_reported_as_saved(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        default_id = _seed_projection(api_test_client, holes, sections, results)
        saved_id = _seed_projection(
            api_test_client, holes, sections, results, blast={"rock_density_tm3": 2.6}
        )
        default = await READ_HANDLERS["get_blast_correlation"](default_id, BlastCorrelationArgs())
        saved = await READ_HANDLERS["get_blast_correlation"](saved_id, BlastCorrelationArgs())
        assert saved["magnitudes"]["rock_density"]["status"] == "SAVED"
        assert saved["magnitudes"]["pf_g_per_ton"]["status"] == "RHO_SAVED"
        assert "MISSING_DENSITY" not in saved["warnings"]
        for saved_row in saved["rows"]:
            default_row = _row(default, saved_row["section"])
            assert saved_row["pf_g_per_ton"] == pytest.approx(
                default_row["pf_g_per_ton"] * 2.7 / 2.6, rel=2e-3
            )
            assert saved_row["pf_voronoi_status"] != "MISSING_DENSITY"

    async def test_rows_sorted_by_wells_with_rows_omitted_count(self, api_test_client):
        holes = _grid_holes(columns=2, rows=10)
        sections = [_section("S-SHORT", 1000.0, length=4.0), _section("S-LONG", 1000.0, length=20.0)]
        results = [_delta_row("S-SHORT", 0.2), _delta_row("S-LONG", 0.3)]
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](
            session_id, BlastCorrelationArgs(tolerance=1.0)
        )
        assert [row["section"] for row in payload["rows"]] == ["S-LONG", "S-SHORT"]
        assert [row["wells"] for row in payload["rows"]] == [10, 3]
        assert payload["rows_omitted"] == 0

    async def test_every_magnitude_declares_unit_status_and_source(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        magnitudes = payload["magnitudes"]
        assert magnitudes["pf_g_per_ton"]["unit"] == "g/t"
        assert magnitudes["pf_voronoi_g_per_ton"]["unit"] == "g/t"
        assert magnitudes["kg"]["unit"] == "kg"
        assert magnitudes["over_break"]["unit"] == "m"
        assert magnitudes["under_break"]["unit"] == "m"
        assert magnitudes["energy_coverage_fraction"]["unit"] == "fracción 0–1"
        assert "kg/m" not in json.dumps(magnitudes["energy_coverage_fraction"], ensure_ascii=False)
        for name, entry in magnitudes.items():
            assert entry["status"], name
            assert entry["source"], name
        assert "energy_coverage_kg_fraction" not in json.dumps(payload, ensure_ascii=False)

    async def test_over_and_under_break_values_are_metres(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        results.append(_delta_row("S-01", -0.3))
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        row = _row(payload, "S-01")
        assert row["over_break"] == pytest.approx(0.4)
        assert row["under_break"] == pytest.approx(-0.3)

    async def test_tolerance_declares_requested_or_default(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        default = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert default["tolerance"] == {
            "value": 15.0,
            "unit": "m",
            "status": "DEFAULT",
            "source": "core.config DEFAULTS.blast_correlation_radius_m",
        }
        requested = await READ_HANDLERS["get_blast_correlation"](
            session_id, BlastCorrelationArgs(tolerance=1.0)
        )
        assert requested["tolerance"] == {
            "value": 1.0,
            "unit": "m",
            "status": "REQUESTED",
            "source": "tool arg",
        }

    async def test_survey_date_passes_the_rest_temporal_filter_through(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](
            session_id, BlastCorrelationArgs(survey_date="2026-06-01")
        )
        assert payload["temporal_filter"]["enabled"] is True
        assert payload["temporal_filter"]["survey_date"] == "2026-06-01"
        assert payload["temporal_filter"]["effective_cutoff_date"] == "2026-05-25"
        assert payload["temporal_filter"]["missing"] == 60

    async def test_per_hole_arrays_never_reach_the_payload(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert _CORRELATION_KEYS.isdisjoint(set(_walk_keys(payload)))

    async def test_heavy_work_runs_through_run_blast_limited(self, api_test_client, monkeypatch):
        from api import _async_db

        original = _async_db.run_blast_limited
        calls = []

        async def spy(fn, /, *args):
            calls.append((fn, args))
            return await original(fn, *args)

        monkeypatch.setattr(_async_db, "run_blast_limited", spy)
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert payload["ok"] is True
        assert len(calls) == 1
        assert calls[0][1][0] == session_id

    async def test_forty_sections_fit_budget_and_keep_critical_keys_first(self, api_test_client):
        holes = _grid_holes(columns=6, rows=10)
        sections = [
            _section(f"SECTOR-NORTE-LONG-NAME-{i:03d}-ABCDEFGHIJKLMNOPQRST", 1000.0 + 0.25 * i)
            for i in range(40)
        ]
        results = [_delta_row(section["name"], 0.1 * (i + 1)) for i, section in enumerate(sections)]
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](
            session_id, BlastCorrelationArgs(tolerance=1.0)
        )
        text = json.dumps(payload, ensure_ascii=False)
        assert len(text.encode("utf-8")) <= 4096
        head = text[:4000]
        for key in ('"ok"', '"data_status"', '"magnitudes"', '"warnings"'):
            assert key in head
        assert payload["n_sections"] == 40
        assert payload["rows_omitted"] > 0
        assert len(payload["rows"]) + payload["rows_omitted"] == 40

    async def test_sector_density_override_is_flagged_and_mixed(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        default_id = _seed_projection(api_test_client, holes, sections, results)
        sector_id = _seed_projection(
            api_test_client, holes, sections, results, sector_density={"Norte": 2.5}
        )
        default = await READ_HANDLERS["get_blast_correlation"](default_id, BlastCorrelationArgs())
        sector = await READ_HANDLERS["get_blast_correlation"](sector_id, BlastCorrelationArgs())
        assert "SECTOR_DENSITY_OVERRIDE" in sector["warnings"]
        assert sector["magnitudes"]["rock_density"]["status"] == "DEFAULT"
        assert sector["magnitudes"]["pf_g_per_ton"]["status"] == "RHO_MIXED"
        for row in sector["rows"]:
            assert "MISSING_DENSITY" not in row["pf_voronoi_status"]
            assert row["pf_g_per_ton"] == pytest.approx(
                _row(default, row["section"])["pf_g_per_ton"] * 2.7 / 2.5, rel=2e-3
            )

    async def test_invalid_stored_density_yields_no_pf_values(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(
            api_test_client, holes, sections, results, blast={"rock_density_tm3": 0.0}
        )
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert payload["magnitudes"]["rock_density"]["status"] == "INVALID"
        assert payload["magnitudes"]["rock_density"]["value"] is None
        assert payload["magnitudes"]["pf_g_per_ton"]["status"] == "RHO_INVALID"
        assert all(row["pf_g_per_ton"] is None for row in payload["rows"])
        assert all("VALID" not in row["pf_voronoi_status"] for row in payload["rows"])
        assert "INVALID_DENSITY" in payload["warnings"]

    async def test_observation_reaches_the_model_without_structural_truncation(self, api_test_client):
        from core.ai_v2.agent.loop import _observation_content

        holes = _grid_holes(columns=6, rows=10)
        sections = [
            _section(f"SECTOR-NORTE-LONG-NAME-{i:03d}-ABCDEFGHIJKLMNOPQRST", 1000.0 + 0.25 * i)
            for i in range(40)
        ]
        results = [_delta_row(section["name"], 0.1 * (i + 1)) for i, section in enumerate(sections)]
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](
            session_id, BlastCorrelationArgs(tolerance=1.0)
        )
        observation = _observation_content({"ok": True, "result": payload})
        assert json.loads(observation)["result"] == payload

    async def test_digest_keeps_its_magnitudes_through_history_compaction(self, api_test_client):
        from api.ai_agent_conversations import _compact_tool_content

        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        compacted = _compact_tool_content(json.dumps(payload, ensure_ascii=False))
        assert len(compacted) <= 600 + len("...[compacted]")
        assert compacted.startswith('{"ok":true')
        assert '"tolerance":{"value":15.0,"unit":"m","status":"DEFAULT"' in compacted
        assert '"rock_density":{"value":2.7,"unit":"t/m³","status":"DEFAULT"' in compacted

    async def test_eleven_thousand_holes_stay_under_budget(self, api_test_client):
        session_id = _seed_projection(api_test_client, _grid_holes(columns=6, rows=10), [], [])
        settings = db.get_settings(session_id)
        template = list(settings["blast_holes"])
        settings["blast_holes"] = [
            {
                **template[index % len(template)],
                "id_pozo": str(6400000 + index),
                "X": float(template[index % len(template)]["X"]) + 0.001 * (index // len(template)),
            }
            for index in range(11184)
        ]
        sections = [_section(f"S-{k:02d}", 1005.0 + 0.1 * k, length=60.0) for k in range(12)]
        db.save_sections(session_id, sections)
        db.save_results(session_id, [_delta_row(section["name"], 0.5) for section in sections])
        db.save_settings(session_id, settings)
        payload = await READ_HANDLERS["get_blast_correlation"](session_id, BlastCorrelationArgs())
        assert payload["ok"] is True
        assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= 4096
        assert payload["n_sections"] == 12
        assert _CORRELATION_KEYS.isdisjoint(set(_walk_keys(payload)))


@pytest.mark.asyncio
class TestGetBlastDamageModel:
    async def test_session_without_holes_reports_no_blast_data(self, api_isolated_db):
        session_id = db.create_session()
        payload = await READ_HANDLERS["get_blast_damage_model"](session_id, BlastDamageArgs())
        assert payload == {"ok": False, "error": "no_blast_data", "message": _NO_BLAST_MESSAGE}

    async def test_holes_without_results_report_no_results(self, api_test_client):
        session_id = db.create_session()
        _upload_holes(api_test_client, session_id, _grid_holes(columns=2, rows=2))
        payload = await READ_HANDLERS["get_blast_damage_model"](session_id, BlastDamageArgs())
        assert payload["ok"] is False
        assert payload["error"] == "no_results"

    async def test_one_section_has_insufficient_samples_and_units(self, api_test_client):
        holes = _grid_holes(columns=6, rows=10)
        session_id = _seed_projection(
            api_test_client, holes, [_section("S-01", 1000.0)], [_delta_row("S-01", 0.4)]
        )
        payload = await READ_HANDLERS["get_blast_damage_model"](session_id, BlastDamageArgs())
        assert payload["ok"] is True
        assert payload["n_points"] == 1
        assert payload["fit_status"] == "INSUFFICIENT_SAMPLES"
        assert payload["fit"] is None
        assert payload["magnitudes"]["pf_g_per_ton"]["unit"] == "g/t"
        assert payload["magnitudes"]["over_break"]["unit"] == "m"
        assert payload["magnitudes"]["pf_g_per_ton"]["status"] == "RHO_DEFAULT"
        assert payload["tolerance"]["status"] == "DEFAULT"
        assert "MISSING_DENSITY" in payload["warnings"]

    async def test_six_sections_fit_declares_fit_units(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_damage_model"](
            session_id, BlastDamageArgs(tolerance=1.0)
        )
        assert payload["n_points"] == 6
        assert payload["fit_status"] == "FIT"
        assert payload["fit"]["beta0_m"] is not None
        assert payload["fit"]["beta1_m_per_gt"] is not None
        assert payload["fit"]["n"] == 6
        assert payload["tolerance"] == {
            "value": 1.0,
            "unit": "m",
            "status": "REQUESTED",
            "source": "tool arg",
        }

    async def test_points_are_capped_and_budgeted(self, api_test_client):
        holes = _grid_holes(columns=6, rows=10)
        sections = [_section(f"SECTOR-NORTE-LONG-NAME-{i:03d}-ABCDEFGHIJKLMNOPQRST", 1000.0 + 0.25 * i) for i in range(40)]
        results = [_delta_row(section["name"], 0.1 * (i + 1)) for i, section in enumerate(sections)]
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_damage_model"](
            session_id, BlastDamageArgs(tolerance=1.0)
        )
        text = json.dumps(payload, ensure_ascii=False)
        assert len(text.encode("utf-8")) <= 4096
        assert '"fit_status"' in text[:4000]
        assert len(payload["points"]) == 12
        assert payload["points_omitted"] == payload["n_points"] - 12
        assert payload["n_points"] == 40

    async def test_per_hole_arrays_never_reach_the_payload(self, api_test_client):
        holes, sections, results = _six_column_fixture()
        session_id = _seed_projection(api_test_client, holes, sections, results)
        payload = await READ_HANDLERS["get_blast_damage_model"](session_id, BlastDamageArgs())
        assert _CORRELATION_KEYS.isdisjoint(set(_walk_keys(payload)))
