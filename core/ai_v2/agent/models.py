"""Pydantic contracts for the AI agent tools: risk, state, specs, args.

Pure ``core`` models — no imports from ``api/``. The arg models mirror
the REAL router request parameters field-for-field (see
``api/routers/sections.py`` and ``api.schemas.ProcessSettings``) and
reject unknown keys via ``extra="forbid"`` so the model cannot smuggle
extra parameters past the policy layer.
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ToolRisk(str, Enum):
    """Risk class of a tool, driving the confirmation policy.

    See ``docs/AI_CHAT_AGENT_PLAN.md`` section 5.2: READ/ADDITIVE/EXPORT
    never require confirmation; REPLACE and EXPENSIVE_REPLACE require it
    only when prior work exists; DESTRUCTIVE and CONFIG always do.
    """

    READ = "read"
    ADDITIVE = "additive"
    EXPORT = "export"
    REPLACE = "replace"
    EXPENSIVE_REPLACE = "expensive_replace"
    DESTRUCTIVE = "destructive"
    CONFIG = "config"


class ToolState(BaseModel):
    """Aggregate snapshot of the active session, from SQL counts only.

    Never carries datasets or blobs: the numbers come from aggregate
    queries (e.g. ``db.get_results_count``) so the policy can gate
    replace-type tools without loading any data.
    """

    model_config = ConfigDict(extra="forbid")

    n_sections: int = 0
    n_results: int = 0
    process_status: str = "idle"
    has_design_mesh: bool = False
    has_topo_mesh: bool = False

    def fingerprint(self) -> str:
        """Return a stable SHA-256 hash string of the state fields.

        Deterministic across processes: canonical JSON (sorted keys,
        compact separators) hashed with SHA-256. Used to invalidate a
        confirmation when the session state changed since the request.
        """
        payload = json.dumps(
            self.model_dump(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ToolSpec(BaseModel):
    """Static declaration of one agent tool.

    Attributes:
        name: Tool name exposed to the provider (snake_case, unique).
        description: English description shown to the provider.
        args_model: Pydantic model class validating the tool arguments;
            its JSON schema becomes the OpenAI ``parameters`` schema.
        risk: Risk class driving the confirmation policy.
        state_keys: ``ToolState`` fields that gate REPLACE-type
            confirmation (non-zero value means prior work exists).
        timeout_s: Per-tool execution budget, separate from the
            provider request timeout.
        idempotent: True when repeating the call has no additional
            effect (e.g. exports produce a fresh download each time).
        impact_summary: Spanish template of what the tool overwrites;
            ``{count}`` is filled by the policy with the real state
            count (e.g. "Sobrescribe 78 resultados existentes (~42 s)").
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=2000)
    args_model: type[BaseModel]
    risk: ToolRisk
    state_keys: tuple[str, ...] = ()
    timeout_s: float = Field(default=30.0, gt=0.0)
    idempotent: bool = False
    impact_summary: str = Field(min_length=1, max_length=500)


class PolicyDecision(BaseModel):
    """Outcome of the pure confirmation policy for one tool call.

    Attributes:
        requires_confirmation: Whether the user must approve execution.
        reason_code: Stable machine code (``autonomous_clean_state``,
            ``replace_existing_state``, ``always_confirm``,
            ``unknown_tool``).
        human_summary_es: Spanish summary for the UI confirmation card,
            including real counts when overwriting prior work.
    """

    model_config = ConfigDict(extra="forbid")

    requires_confirmation: bool
    reason_code: str
    human_summary_es: str


class _StrictArgs(BaseModel):
    """Base for all tool argument models: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


class SectionDefinitionArgs(_StrictArgs):
    """One section definition, mirroring the /sections/manual item model.

    Field names mirror ``api.routers.sections.SectionCreate`` exactly.
    """

    name: Optional[str] = Field(default=None, max_length=100)
    origin: list[float] = Field(min_length=2, max_length=2)
    azimuth: float = Field(ge=0.0, le=360.0)
    length: float = Field(default=200.0, gt=0.0, le=10000.0)
    length_up: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    length_down: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    sector: str = Field(default="", max_length=100)


class SectionAutoArgs(_StrictArgs):
    """Arguments for ``generate_sections_auto`` (POST /sections/auto).

    Field names mirror ``api.routers.sections.SectionAutoParams``.
    """

    start: list[float] = Field(min_length=2, max_length=2)
    end: list[float] = Field(min_length=2, max_length=2)
    n_sections: int = Field(default=5, ge=1, le=200)
    length: float = Field(default=200.0, gt=0.0, le=10000.0)
    length_up: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    length_down: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    sector: str = Field(default="", max_length=100)
    az_method: Literal["perpendicular", "fixed", "local_slope"] = "perpendicular"
    fixed_az: float = Field(default=0.0, ge=0.0, le=360.0)


class SectionManualArgs(_StrictArgs):
    """Arguments for ``generate_sections_manual`` (POST /sections/manual).

    ``sections`` items mirror the endpoint's item model exactly.
    """

    sections: list[SectionDefinitionArgs] = Field(min_length=1, max_length=200)


class SectionClickArgs(_StrictArgs):
    """Arguments for ``add_section_click`` (POST /sections/click).

    Field names mirror ``api.routers.sections.SectionClickParams``.
    """

    origin: list[float] = Field(min_length=2, max_length=2)
    length: float = Field(default=200.0, gt=0.0, le=10000.0)
    length_up: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    length_down: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    sector: str = Field(default="", max_length=100)
    az_mode: Literal["auto", "manual"] = "auto"
    azimuth: Optional[float] = Field(default=None, ge=0.0, le=360.0)


class RunReconciliationArgs(_StrictArgs):
    """Arguments for ``run_reconciliation`` (POST /process).

    Optional overrides mirroring ``api.schemas.ProcessSettings``; every
    field omitted keeps the session's current setting.
    """

    resolution: float = Field(default=0.1, gt=0.0, le=10.0)
    face_threshold: float = Field(default=30.0, ge=0.0, le=90.0)
    berm_threshold: float = Field(default=10.0, ge=0.0, le=90.0)


class ExportReportArgs(_StrictArgs):
    """Arguments for ``export_report`` (GET /export/{format}).

    ``format`` matches the real export routes: excel, word, pdf, dxf
    and images.
    """

    format: Literal["excel", "word", "pdf", "dxf", "images"]


class MeshIdArgs(_StrictArgs):
    """Arguments for tools addressing one mesh by id."""

    mesh_id: str = Field(min_length=1, max_length=64)


class SectionIdArgs(_StrictArgs):
    """Arguments for tools addressing one section by its index id."""

    section_id: str = Field(min_length=1, max_length=32)


class NoArgs(_StrictArgs):
    """Arguments for tools that take no parameters."""


__all__ = [
    "ExportReportArgs",
    "MeshIdArgs",
    "NoArgs",
    "PolicyDecision",
    "RunReconciliationArgs",
    "SectionAutoArgs",
    "SectionClickArgs",
    "SectionDefinitionArgs",
    "SectionManualArgs",
    "SectionIdArgs",
    "ToolRisk",
    "ToolSpec",
    "ToolState",
]
