"""v1 agent tool catalog (14 tools) — plan section 5.3.

Each :class:`ToolSpec` derives its JSON schema from the arg model that
mirrors the REAL router request parameters. No imports from ``api/``:
this catalog is pure ``core`` and the API layer (T1) provides the
handlers. ``upload_mesh`` and ``generate_sections_from_file`` are
deliberately NOT tools: uploads and file-based section generation are
frontend-driven actions that hand the result to the agent as an
observation (plan sections 4.5 and 5.3).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.ai_v2.agent.models import (
    AchievementFilterArgs,
    ExportReportArgs,
    MeshIdArgs,
    NoArgs,
    ResultQueryArgs,
    RunReconciliationArgs,
    SectionAutoArgs,
    SectionClickArgs,
    SectionIdArgs,
    SectionManualArgs,
    ToolRisk,
    ToolSpec,
)

AGENT_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_workflow_state",
        description=(
            "Return the aggregate state of the active session: number of "
            "sections, number of results, process status, and whether "
            "design/topo meshes are loaded. Use before any write."
        ),
        args_model=NoArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="list_meshes",
        description=(
            "List the meshes uploaded in the active session (design and "
            "topo) with their mesh_id."
        ),
        args_model=NoArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="get_mesh_info",
        description=(
            "Return summary info (vertices, faces, bounds, filename) for "
            "one mesh by its mesh_id."
        ),
        args_model=MeshIdArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="list_sections",
        description="List the cross-sections defined in the active session.",
        args_model=NoArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="add_section_click",
        description=(
            "Append ONE cross-section at an origin point on the plan view. "
            "Additive: existing sections are kept."
        ),
        args_model=SectionClickArgs,
        risk=ToolRisk.ADDITIVE,
        impact_summary="Añade una sección sin eliminar las existentes",
    ),
    ToolSpec(
        name="generate_sections_auto",
        description=(
            "Generate sections evenly spaced along a start-end line over "
            "the design mesh. Replaces ALL existing sections of the session."
        ),
        args_model=SectionAutoArgs,
        risk=ToolRisk.REPLACE,
        state_keys=("n_sections",),
        impact_summary="Sobrescribe {count} secciones existentes",
    ),
    ToolSpec(
        name="generate_sections_manual",
        description=(
            "Set sections from an explicit list of definitions. Replaces "
            "ALL existing sections of the session."
        ),
        args_model=SectionManualArgs,
        risk=ToolRisk.REPLACE,
        state_keys=("n_sections",),
        impact_summary="Sobrescribe {count} secciones existentes",
    ),
    ToolSpec(
        name="run_reconciliation",
        description=(
            "Run the full reconciliation pipeline (cut sections, extract "
            "bench parameters, compare design vs as-built) over all "
            "sections. Replaces ALL previous results of the session; "
            "typically takes about 42 seconds."
        ),
        args_model=RunReconciliationArgs,
        risk=ToolRisk.EXPENSIVE_REPLACE,
        state_keys=("n_results",),
        timeout_s=300.0,
        impact_summary="Sobrescribe {count} resultados existentes (~42 s)",
    ),
    ToolSpec(
        name="get_results_summary",
        description=(
            "Return an aggregate summary of the reconciliation results "
            "(counts per status, sector and section), never full datasets."
        ),
        args_model=NoArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="get_profile",
        description=(
            "Return summarized profile data for ONE section by its "
            "index-based section_id (0, 1, 2, ...)."
        ),
        args_model=SectionIdArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="get_design_achievement",
        description=(
            "Return the DESIGN ACHIEVEMENT summary: design vs as-built "
            "compliance rates per sector and parameter. Its global_score "
            "is the logro de diseño (0.4 crest + 0.3 toe + 0.3 berm over "
            "evaluable rows) — a different indicator from the dashboard's "
            "weighted score; call it \"logro de diseño\", never the "
            "dashboard score. Accepts optional filters by sector, "
            "section, level (bench floor elevation as text) and bench "
            "number. It also returns weighted_score with the dashboard's "
            "weighted score over the same filtered rows."
        ),
        args_model=AchievementFilterArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="get_proposed_compliance",
        description=(
            "Return the proposed-parameters compliance summary with "
            "coverage, per-section scores and floor status counts. "
            "Accepts optional filters by sector, section, level (bench "
            "floor elevation as text) and bench number."
        ),
        args_model=AchievementFilterArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="query_results",
        description=(
            "Filter reconciliation result rows by level (bench floor "
            "elevation as text, e.g. ['3065']), bench number, sector, "
            "section, parameter (height/angle/berm) and exact status. "
            "Returns aggregates (status by section/parameter/type), "
            "pct_by_parameter with precomputed percentages over evaluable "
            "rows (statuses other than \"-\") so you never have to compute "
            "them yourself, weighted_score with the DASHBOARD'S WEIGHTED "
            "SCORE (the global figure the user sees in the UI; per bench "
            "berma 60 + ángulo 10 + altura 30 when CUMPLE, averaged per "
            "section then across sections) — use it whenever the user "
            "asks for the weighted score or how a level is doing, the "
            "list of available levels with counts, and optionally "
            "(include_rows=true) up to row_limit rows with "
            "design vs as-built values and deviations. Use it when the "
            "user asks about a specific level, bench, sector or status."
        ),
        args_model=ResultQueryArgs,
        risk=ToolRisk.READ,
        impact_summary="Solo lectura: sin efecto sobre los datos de la sesión",
    ),
    ToolSpec(
        name="export_report",
        description=(
            "Generate a report export (excel, word, pdf, dxf or images) "
            "and return its download metadata; never file bytes."
        ),
        args_model=ExportReportArgs,
        risk=ToolRisk.EXPORT,
        idempotent=True,
        impact_summary=(
            "Genera un archivo descargable sin modificar datos de la sesión"
        ),
    ),
)

TOOL_CATALOG: dict[str, ToolSpec] = {spec.name: spec for spec in AGENT_TOOLS}


def get_tool(name: str) -> ToolSpec | None:
    """Return the cataloged tool by name, or None when not cataloged."""
    return TOOL_CATALOG.get(name)


def to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    """Render one spec in OpenAI tools format for provider requests."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.args_model.model_json_schema(),
        },
    }


def openai_tools() -> list[dict[str, Any]]:
    """Return the whole catalog in OpenAI tools format."""
    return [to_openai_tool(spec) for spec in AGENT_TOOLS]


__all__ = [
    "AGENT_TOOLS",
    "ExportReportArgs",
    "TOOL_CATALOG",
    "get_tool",
    "openai_tools",
    "to_openai_tool",
]
