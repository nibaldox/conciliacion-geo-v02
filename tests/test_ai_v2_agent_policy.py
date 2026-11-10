"""Truth-table tests for the pure confirmation policy (plan section 5.2)."""
from __future__ import annotations

import pytest

from core.ai_v2.agent.models import (
    MeshIdArgs,
    NoArgs,
    RunReconciliationArgs,
    SectionAutoArgs,
    ToolRisk,
    ToolSpec,
    ToolState,
)
from core.ai_v2.agent.policy import (
    REASON_ALWAYS_CONFIRM,
    REASON_AUTONOMOUS,
    REASON_REPLACE_EXISTING,
    REASON_UNKNOWN_TOOL,
    decide,
    decide_unknown,
)


def _spec(
    risk: ToolRisk,
    *,
    name: str = "probe_tool",
    state_keys: tuple[str, ...] = (),
    args_model: type = NoArgs,
    impact_summary: str = "Sobrescribe {count} elementos existentes",
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="probe spec",
        args_model=args_model,
        risk=risk,
        state_keys=state_keys,
        impact_summary=impact_summary,
    )


EMPTY_STATE = ToolState()
WORKING_STATE = ToolState(
    n_sections=78,
    n_results=42,
    process_status="complete",
    has_design_mesh=True,
    has_topo_mesh=True,
)


class TestNeverConfirmRisks:
    @pytest.mark.parametrize("risk", [ToolRisk.READ, ToolRisk.ADDITIVE, ToolRisk.EXPORT])
    def test_never_confirms_on_empty_state(self, risk: ToolRisk) -> None:
        decision = decide(_spec(risk), EMPTY_STATE)
        assert decision.requires_confirmation is False
        assert decision.reason_code == REASON_AUTONOMOUS
        assert decision.human_summary_es

    @pytest.mark.parametrize("risk", [ToolRisk.READ, ToolRisk.ADDITIVE, ToolRisk.EXPORT])
    def test_never_confirms_on_working_state(self, risk: ToolRisk) -> None:
        decision = decide(_spec(risk), WORKING_STATE)
        assert decision.requires_confirmation is False
        assert decision.reason_code == REASON_AUTONOMOUS

    def test_catalog_read_tool_decides_autonomous(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["list_sections"], WORKING_STATE)
        assert decision.requires_confirmation is False


class TestReplaceRisk:
    def test_replace_with_zero_sections_is_autonomous(self) -> None:
        spec = _spec(
            ToolRisk.REPLACE,
            name="generate_sections_auto",
            state_keys=("n_sections",),
            args_model=SectionAutoArgs,
        )
        decision = decide(spec, ToolState(n_sections=0))
        assert decision.requires_confirmation is False
        assert decision.reason_code == REASON_AUTONOMOUS
        assert "sin confirmación" in decision.human_summary_es

    def test_replace_with_existing_sections_requires_confirmation(self) -> None:
        spec = _spec(
            ToolRisk.REPLACE,
            name="generate_sections_auto",
            state_keys=("n_sections",),
            args_model=SectionAutoArgs,
            impact_summary="Sobrescribe {count} secciones existentes",
        )
        decision = decide(spec, ToolState(n_sections=78))
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_REPLACE_EXISTING
        assert "78" in decision.human_summary_es
        assert "secciones" in decision.human_summary_es

    def test_replace_confirms_on_any_nonzero_state_key(self) -> None:
        spec = _spec(
            ToolRisk.REPLACE,
            state_keys=("n_sections", "n_results"),
        )
        decision = decide(spec, ToolState(n_sections=0, n_results=3))
        assert decision.requires_confirmation is True
        assert "3" in decision.human_summary_es


class TestExpensiveReplaceRisk:
    def test_reconciliation_with_zero_results_is_autonomous(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["run_reconciliation"], ToolState(n_results=0))
        assert decision.requires_confirmation is False
        assert decision.reason_code == REASON_AUTONOMOUS

    def test_reconciliation_with_results_requires_confirmation(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["run_reconciliation"], ToolState(n_results=78))
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_REPLACE_EXISTING
        assert "78" in decision.human_summary_es
        assert "resultados" in decision.human_summary_es
        assert "~42 s" in decision.human_summary_es


class TestAlwaysConfirmRisks:
    @pytest.mark.parametrize("risk", [ToolRisk.DESTRUCTIVE, ToolRisk.CONFIG])
    def test_always_confirms_on_clean_state(self, risk: ToolRisk) -> None:
        decision = decide(_spec(risk), EMPTY_STATE)
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_ALWAYS_CONFIRM

    @pytest.mark.parametrize("risk", [ToolRisk.DESTRUCTIVE, ToolRisk.CONFIG])
    def test_always_confirms_on_working_state(self, risk: ToolRisk) -> None:
        decision = decide(_spec(risk), WORKING_STATE)
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_ALWAYS_CONFIRM


class TestUnknownTool:
    def test_unknown_tool_fails_closed(self) -> None:
        decision = decide_unknown("delete_everything")
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_UNKNOWN_TOOL
        assert "delete_everything" in decision.human_summary_es

    def test_unknown_tool_is_never_autonomous(self) -> None:
        decision = decide_unknown("mystery")
        assert decision.reason_code != REASON_AUTONOMOUS


class TestReplaceWithoutStateKeys:
    def test_replace_missing_state_keys_fails_closed(self) -> None:
        decision = decide(_spec(ToolRisk.REPLACE), WORKING_STATE)
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_REPLACE_EXISTING

    def test_expensive_replace_missing_state_keys_fails_closed(self) -> None:
        decision = decide(
            _spec(ToolRisk.EXPENSIVE_REPLACE, args_model=RunReconciliationArgs),
            EMPTY_STATE,
        )
        assert decision.requires_confirmation is True


class TestSummaryContent:
    def test_summaries_are_non_empty_spanish(self) -> None:
        from core.ai_v2.agent.catalog import AGENT_TOOLS

        for spec in AGENT_TOOLS:
            decision = decide(spec, WORKING_STATE)
            assert decision.human_summary_es
            assert decision.reason_code in {
                REASON_AUTONOMOUS,
                REASON_REPLACE_EXISTING,
                REASON_ALWAYS_CONFIRM,
            }

    def test_read_tool_summary_mentions_no_replacement(self) -> None:
        spec = _spec(
            ToolRisk.READ,
            name="get_mesh_info",
            args_model=MeshIdArgs,
            impact_summary="Solo lectura",
        )
        decision = decide(spec, WORKING_STATE)
        assert decision.human_summary_es == (
            "'get_mesh_info' no reemplaza datos de la sesión: "
            "se ejecuta sin confirmación."
        )
