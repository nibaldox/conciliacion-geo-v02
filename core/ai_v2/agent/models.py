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
from datetime import date
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_FilterSectorName = Annotated[str, Field(min_length=1, max_length=120)]
_FilterSectionName = Annotated[str, Field(min_length=1, max_length=60)]
_FilterLevelLabel = Annotated[str, Field(min_length=1, max_length=20)]
_QueryText = Annotated[str, Field(max_length=120)]

_ROW_LIMIT_MIN = 1
_ROW_LIMIT_MAX = 50
_FILTER_LIST_FIELDS = ("sector", "section", "level", "bench")


def _wrap_scalar(value: object) -> object:
    """Wrap one bare filter value into a one-item list (``"S-11"`` → ``["S-11"]``).

    Lists, tuples, dicts and ``None`` pass through untouched so the normal
    validation still applies to them; only JSON scalars are wrapped.
    """
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return [value]
    return value


def _clamped_row_limit(value: object) -> object:
    """Clamp an integer-like ``row_limit`` into ``[1, 50]`` instead of rejecting it."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return max(_ROW_LIMIT_MIN, min(_ROW_LIMIT_MAX, value))
    return value


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
    """Base for all tool argument models: unknown keys and non-finite floats are rejected."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


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


_CurvePoint = Annotated[
    list[Annotated[float, Field(allow_inf_nan=False)]],
    Field(min_length=2, max_length=2),
]


class SectionCurveArgs(_StrictArgs):
    """Arguments for ``generate_sections_curve`` (POST /sections/curve).

    Field names mirror ``api.routers.sections.SectionCurveParams``. The 2-200
    point limit and the spacing bounds are agent restrictions: the REST
    endpoint accepts any polyline, so these limits do not describe it.
    """

    points: list[_CurvePoint] = Field(min_length=2, max_length=200)
    spacing: float = Field(default=10.0, ge=0.1, le=1000.0, allow_inf_nan=False)
    length: float = Field(default=200.0, gt=0.0, le=10000.0, allow_inf_nan=False)
    length_up: Optional[float] = Field(default=None, gt=0.0, le=10000.0, allow_inf_nan=False)
    length_down: Optional[float] = Field(default=None, gt=0.0, le=10000.0, allow_inf_nan=False)
    sector: str = Field(default="", max_length=100)


_SECTION_OVERRIDE_FIELDS: tuple[str, ...] = (
    "name",
    "origin",
    "azimuth",
    "length",
    "length_up",
    "length_down",
    "sector",
)


class SectionUpdateArgs(_StrictArgs):
    """Arguments for ``update_section``: one section by index plus overrides.

    ``section_id`` is the index returned by ``list_sections``. Each override
    mirrors :class:`SectionDefinitionArgs`; ``None`` keeps the stored value,
    so at least one override must be given.
    """

    section_id: int = Field(ge=0, le=99999)
    name: Optional[str] = Field(default=None, max_length=100)
    origin: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    azimuth: Optional[float] = Field(default=None, ge=0.0, le=360.0)
    length: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    length_up: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    length_down: Optional[float] = Field(default=None, gt=0.0, le=10000.0)
    sector: Optional[str] = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _requires_one_override(self) -> "SectionUpdateArgs":
        if all(getattr(self, field) is None for field in _SECTION_OVERRIDE_FIELDS):
            raise ValueError("update_section needs at least one field to change")
        return self


class SectionDeleteArgs(_StrictArgs):
    """Arguments for ``delete_section``: one section by its index id."""

    section_id: int = Field(ge=0, le=99999)


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

    Optional per-run overrides mirroring ``api.schemas.ProcessSettings``.
    A field left as ``None`` keeps the session's saved detection setting.
    """

    resolution: Optional[float] = Field(
        default=None, gt=0.0, le=10.0, allow_inf_nan=False
    )
    face_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=90.0, allow_inf_nan=False
    )
    berm_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=90.0, allow_inf_nan=False
    )


class ExportReportArgs(_StrictArgs):
    """Arguments for ``export_report`` (GET /export/{format}).

    ``format`` matches the real export routes: excel, word, pdf, dxf
    and images. The filters do NOT mirror the REST query parameters
    literally: ``sector``, ``section`` and ``levels_by_sector`` are checked
    against the session's real sectors and nominal level labels, then sent
    as one camelCase ``filters`` document, while ``project`` and ``author``
    map to the router's metadata parameters. There is no flat ``level``
    filter because nominal labels are grouped per sector.
    """

    format: Literal["excel", "word", "pdf", "dxf", "images"]
    sector: Optional[list[_FilterSectorName]] = Field(default=None, max_length=20)
    section: Optional[list[_FilterSectionName]] = Field(default=None, max_length=50)
    levels_by_sector: Optional[dict[_FilterSectorName, list[_FilterLevelLabel]]] = None
    project: Optional[str] = Field(default=None, max_length=120)
    author: Optional[str] = Field(default=None, max_length=120)


class MeshIdArgs(_StrictArgs):
    """Arguments for tools addressing one mesh by id."""

    mesh_id: str = Field(min_length=1, max_length=64)


class SectionIdArgs(_StrictArgs):
    """Arguments for tools addressing one section by its index id."""

    section_id: str = Field(min_length=1, max_length=32)


class NoArgs(_StrictArgs):
    """Arguments for tools that take no parameters."""


class ResultQueryArgs(_StrictArgs):
    """Arguments for ``query_results`` (filtered READ over result rows).

    ``level`` values are the design bench floor elevations exactly as the
    web table shows them (text, e.g. ``['3065', '3066']``); ``bench``
    values are design bench numbers matched by their string form, like
    the web table filter. Each sector, section and level item is capped at
    120 characters.
    """

    sector: Optional[list[_QueryText]] = Field(default=None, max_length=20)
    section: Optional[list[_QueryText]] = Field(default=None, max_length=20)
    level: Optional[list[_QueryText]] = Field(default=None, max_length=60)
    bench: Optional[list[int]] = Field(default=None, max_length=50)
    parameter: Optional[Literal["height", "angle", "berm"]] = None
    status: Optional[str] = Field(default=None, max_length=40)
    include_rows: bool = False
    row_limit: int = Field(default=20, ge=_ROW_LIMIT_MIN, le=_ROW_LIMIT_MAX)

    # Tolerant inputs (mode="before" leaves the JSON schema untouched): a bare
    # filter value becomes a one-item list and row_limit is clamped.
    @field_validator(*_FILTER_LIST_FIELDS, mode="before")
    @classmethod
    def _wrap_filter_scalars(cls, value: object) -> object:
        return _wrap_scalar(value)

    @field_validator("row_limit", mode="before")
    @classmethod
    def _clamp_row_limit(cls, value: object) -> object:
        return _clamped_row_limit(value)


class AchievementFilterArgs(_StrictArgs):
    """Optional dimension filters for the two summary tools.

    Same semantics as the web table filters (ANDed across dimensions,
    ORed within one; ``''`` selectable): mirrors the repeatable query
    parameters of GET /process/design-achievement and
    GET /process/proposed-compliance.
    """

    sector: Optional[list[str]] = Field(default=None, max_length=20)
    section: Optional[list[str]] = Field(default=None, max_length=20)
    level: Optional[list[str]] = Field(default=None, max_length=60)
    bench: Optional[list[int]] = Field(default=None, max_length=50)

    # A bare filter value becomes a one-item list (schema unchanged).
    @field_validator(*_FILTER_LIST_FIELDS, mode="before")
    @classmethod
    def _wrap_filter_scalars(cls, value: object) -> object:
        return _wrap_scalar(value)


class BlastCorrelationArgs(_StrictArgs):
    """Arguments for ``get_blast_correlation`` (GET /process/blast-correlation).

    ``tolerance`` is the perpendicular inclusion radius in metres; ``None``
    keeps the core default. ``survey_date`` applies the same temporal filter
    as the REST query parameter.
    """

    tolerance: Optional[float] = Field(
        default=None, gt=0.0, le=100.0, allow_inf_nan=False
    )
    survey_date: Optional[date] = None


class BlastDamageArgs(_StrictArgs):
    """Arguments for ``get_blast_damage_model`` (GET /process/blast-correlation/damage-model).

    Same fields and semantics as :class:`BlastCorrelationArgs`.
    """

    tolerance: Optional[float] = Field(
        default=None, gt=0.0, le=100.0, allow_inf_nan=False
    )
    survey_date: Optional[date] = None


__all__ = [
    "AchievementFilterArgs",
    "BlastCorrelationArgs",
    "BlastDamageArgs",
    "ExportReportArgs",
    "MeshIdArgs",
    "NoArgs",
    "PolicyDecision",
    "ResultQueryArgs",
    "RunReconciliationArgs",
    "SectionAutoArgs",
    "SectionClickArgs",
    "SectionCurveArgs",
    "SectionDefinitionArgs",
    "SectionDeleteArgs",
    "SectionManualArgs",
    "SectionIdArgs",
    "SectionUpdateArgs",
    "ToolRisk",
    "ToolSpec",
    "ToolState",
]
