"""Pure confirmation policy for agent tools.

Decides whether a tool call needs explicit user approval, from the tool
spec and the session state snapshot only. No I/O, no HTTP, no clock —
fully deterministic and unit-tested as a truth table
(``docs/AI_CHAT_AGENT_PLAN.md`` section 5.2).

Truth table:

===========================  =========================  ==============
Risk class                   Prior work in state_keys   Confirmation
===========================  =========================  ==============
READ / ADDITIVE / EXPORT     (ignored)                  never
REPLACE                      all zero                   never
REPLACE                      any non-zero               yes
EXPENSIVE_REPLACE            all zero                   never
EXPENSIVE_REPLACE            any non-zero               yes
DESTRUCTIVE / CONFIG         (ignored)                  always
Unknown tool                 (ignored)                  fail-closed
===========================  =========================  ==============

Reason codes: ``autonomous_clean_state``, ``replace_existing_state``,
``always_confirm``, ``unknown_tool``.
"""
from __future__ import annotations

from typing import Any

from core.ai_v2.agent.models import PolicyDecision, ToolRisk, ToolSpec, ToolState

REASON_AUTONOMOUS = "autonomous_clean_state"
REASON_REPLACE_EXISTING = "replace_existing_state"
REASON_ALWAYS_CONFIRM = "always_confirm"
REASON_UNKNOWN_TOOL = "unknown_tool"

_NEVER_CONFIRM_RISKS: frozenset[ToolRisk] = frozenset(
    {ToolRisk.READ, ToolRisk.ADDITIVE, ToolRisk.EXPORT}
)
_ALWAYS_CONFIRM_RISKS: frozenset[ToolRisk] = frozenset(
    {ToolRisk.DESTRUCTIVE, ToolRisk.CONFIG}
)
_REPLACE_RISKS: frozenset[ToolRisk] = frozenset(
    {ToolRisk.REPLACE, ToolRisk.EXPENSIVE_REPLACE}
)


def _state_key_active(value: Any) -> bool:
    """Return True when a ToolState field indicates prior work exists."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value not in ("", "idle")
    return bool(value)


def _active_counts(spec: ToolSpec, state: ToolState) -> list[int]:
    """Return the non-zero values of the spec's gating state keys."""
    counts: list[int] = []
    for key in spec.state_keys:
        value = getattr(state, key)
        if _state_key_active(value):
            if isinstance(value, bool):
                counts.append(1)
            elif isinstance(value, (int, float)):
                counts.append(int(value))
            else:
                counts.append(1)
    return counts


def decide(spec: ToolSpec, state: ToolState) -> PolicyDecision:
    """Return the policy decision for one tool call.

    Args:
        spec: The tool being invoked, from the frozen catalog.
        state: Aggregate snapshot of the session at decision time.
    """
    if spec.risk in _NEVER_CONFIRM_RISKS:
        return PolicyDecision(
            requires_confirmation=False,
            reason_code=REASON_AUTONOMOUS,
            human_summary_es=(
                f"'{spec.name}' no reemplaza datos de la sesión: "
                "se ejecuta sin confirmación."
            ),
        )

    if spec.risk in _ALWAYS_CONFIRM_RISKS:
        return PolicyDecision(
            requires_confirmation=True,
            reason_code=REASON_ALWAYS_CONFIRM,
            human_summary_es=(
                f"'{spec.name}' requiere confirmación explícita del usuario."
            ),
        )

    if not spec.state_keys:
        return PolicyDecision(
            requires_confirmation=True,
            reason_code=REASON_REPLACE_EXISTING,
            human_summary_es=(
                f"'{spec.name}' reemplaza datos de la sesión y no se pudo "
                "verificar el estado previo: se requiere confirmación."
            ),
        )

    active = _active_counts(spec, state)
    if active:
        count = max(active)
        summary = spec.impact_summary.format(count=count)
    else:
        summary = (
            f"'{spec.name}' se ejecuta sin confirmación: "
            "no hay trabajo previo que sobrescribir."
        )
    return PolicyDecision(
        requires_confirmation=bool(active),
        reason_code=REASON_REPLACE_EXISTING if active else REASON_AUTONOMOUS,
        human_summary_es=summary,
    )


def decide_unknown(name: str) -> PolicyDecision:
    """Fail-closed decision for a tool outside the catalog.

    The model cannot self-authorize an uncataloged call: it is never
    executed silently and always surfaces to the user.
    """
    return PolicyDecision(
        requires_confirmation=True,
        reason_code=REASON_UNKNOWN_TOOL,
        human_summary_es=(
            f"Herramienta desconocida '{name}': no se ejecutará sin "
            "confirmación explícita del usuario."
        ),
    )


__all__ = [
    "REASON_ALWAYS_CONFIRM",
    "REASON_AUTONOMOUS",
    "REASON_REPLACE_EXISTING",
    "REASON_UNKNOWN_TOOL",
    "decide",
    "decide_unknown",
]
