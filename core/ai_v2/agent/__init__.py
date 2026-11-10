"""Conversational AI agent contracts (T0 freeze) — pure ``core``.

Re-exports the frozen contract surface: tool risk/state/spec models,
the NDJSON event protocol, the pure confirmation policy, the v1
13-tool catalog and the pending-confirmation interface. No HTTP, no
agent loop, no tool handlers, no provider calls — those land in later
deliveries (T1-T4 in ``api/``). This package never imports from
``api/``.

    from core.ai_v2.agent import ToolSpec, decide, AGENT_TOOLS
"""
from __future__ import annotations

from core.ai_v2.agent.catalog import (
    AGENT_TOOLS,
    TOOL_CATALOG,
    get_tool,
    openai_tools,
    to_openai_tool,
)
from core.ai_v2.agent.confirmations import (
    AlreadyClaimedPendingRun,
    ExpiredPendingRun,
    ForeignSessionPendingRun,
    PENDING_TTL_S,
    PendingRun,
    PendingRunError,
    PendingRunNotFound,
    PendingRunStore,
    canonical_args_sha256,
    new_invocation_id,
)
from core.ai_v2.agent.events import (
    AgentEvent,
    ConfirmationRequiredEvent,
    DoneEvent,
    ErrorEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
    event_to_ndjson,
    parse_event_line,
)
from core.ai_v2.agent.models import (
    ExportReportArgs,
    MeshIdArgs,
    NoArgs,
    PolicyDecision,
    RunReconciliationArgs,
    SectionAutoArgs,
    SectionClickArgs,
    SectionDefinitionArgs,
    SectionIdArgs,
    SectionManualArgs,
    ToolRisk,
    ToolSpec,
    ToolState,
)
from core.ai_v2.agent.policy import decide, decide_unknown

__all__: list[str] = [
    "AGENT_TOOLS",
    "AgentEvent",
    "AlreadyClaimedPendingRun",
    "ConfirmationRequiredEvent",
    "DoneEvent",
    "ErrorEvent",
    "ExpiredPendingRun",
    "ExportReportArgs",
    "ForeignSessionPendingRun",
    "MeshIdArgs",
    "NoArgs",
    "PENDING_TTL_S",
    "PendingRun",
    "PendingRunError",
    "PendingRunNotFound",
    "PendingRunStore",
    "PolicyDecision",
    "RunReconciliationArgs",
    "SectionAutoArgs",
    "SectionClickArgs",
    "SectionDefinitionArgs",
    "SectionIdArgs",
    "SectionManualArgs",
    "TextEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "ToolRisk",
    "ToolSpec",
    "ToolState",
    "TOOL_CATALOG",
    "canonical_args_sha256",
    "decide",
    "decide_unknown",
    "event_to_ndjson",
    "get_tool",
    "new_invocation_id",
    "openai_tools",
    "parse_event_line",
    "to_openai_tool",
]
