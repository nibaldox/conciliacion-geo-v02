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


class TestSectionEditTools:
    def test_delete_section_confirms_on_clean_state(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["delete_section"], ToolState(n_sections=1, n_results=0))
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_ALWAYS_CONFIRM

    def test_delete_section_confirms_with_results(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["delete_section"], WORKING_STATE)
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_ALWAYS_CONFIRM

    def test_delete_section_summary_names_section_and_invalidated_count(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(
            TOOL_CATALOG["delete_section"],
            ToolState(n_sections=10, n_results=160),
            args={"section_id": 4},
        )
        assert decision.requires_confirmation is True
        assert decision.human_summary_es == (
            "Elimina la sección con section_id 4 e invalida 160 resultados; "
            "los section_id posteriores bajan en 1."
        )

    def test_update_section_confirms_when_results_exist(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["update_section"], ToolState(n_sections=2, n_results=7))
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_REPLACE_EXISTING
        assert "7" in decision.human_summary_es

    def test_update_section_is_autonomous_without_results(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["update_section"], ToolState(n_sections=2, n_results=0))
        assert decision.requires_confirmation is False
        assert decision.reason_code == REASON_AUTONOMOUS


class TestDestructiveImpactFormatting:
    def test_zero_results_still_requires_confirmation(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(
            TOOL_CATALOG["delete_section"],
            ToolState(n_sections=1, n_results=0),
            args={"section_id": 0},
        )
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_ALWAYS_CONFIRM
        assert decision.human_summary_es == (
            "Elimina la sección con section_id 0 e invalida 0 resultados; "
            "los section_id posteriores bajan en 1."
        )

    def test_missing_args_keep_placeholder_literal(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(
            TOOL_CATALOG["delete_section"], ToolState(n_sections=10, n_results=160)
        )
        assert decision.human_summary_es == (
            "Elimina la sección con section_id {section_id} e invalida 160 resultados; "
            "los section_id posteriores bajan en 1."
        )

    def test_state_count_wins_over_an_args_count_key(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(
            TOOL_CATALOG["delete_section"],
            ToolState(n_sections=10, n_results=160),
            args={"section_id": 4, "count": 999},
        )
        assert "invalida 160 resultados" in decision.human_summary_es
        assert "999" not in decision.human_summary_es

    @pytest.mark.parametrize("template", ["Borra {0} elementos", "Borra {", "Borra } ahora"])
    def test_malformed_template_falls_back_to_generic_text(self, template: str) -> None:
        spec = _spec(ToolRisk.DESTRUCTIVE, impact_summary=template)
        decision = decide(spec, WORKING_STATE, args={"section_id": 4})
        assert decision.requires_confirmation is True
        assert decision.human_summary_es == (
            "'probe_tool' requiere confirmación explícita del usuario."
        )

    @pytest.mark.parametrize("risk", [ToolRisk.DESTRUCTIVE, ToolRisk.CONFIG])
    def test_empty_impact_summary_keeps_generic_text(self, risk: ToolRisk) -> None:
        spec = ToolSpec.model_construct(
            name="probe_tool",
            description="probe spec",
            args_model=NoArgs,
            risk=risk,
            state_keys=(),
            impact_summary="",
        )
        decision = decide(spec, WORKING_STATE, args={"section_id": 4})
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_ALWAYS_CONFIRM
        assert decision.human_summary_es == (
            "'probe_tool' requiere confirmación explícita del usuario."
        )


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


class TestGenerateSectionsCurvePolicy:
    def test_risk_and_state_keys_mirror_generate_sections_auto(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        curve = TOOL_CATALOG["generate_sections_curve"]
        auto = TOOL_CATALOG["generate_sections_auto"]
        assert curve.risk is auto.risk is ToolRisk.REPLACE
        assert curve.state_keys == auto.state_keys == ("n_sections",)

    @pytest.mark.parametrize(
        "state",
        [
            pytest.param(ToolState(), id="empty"),
            pytest.param(ToolState(n_sections=3), id="sections-only"),
            pytest.param(WORKING_STATE, id="sections-and-results"),
            pytest.param(ToolState(n_results=5), id="results-without-sections"),
        ],
    )
    def test_confirmation_matches_generate_sections_auto(self, state: ToolState) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        curve = decide(TOOL_CATALOG["generate_sections_curve"], state)
        auto = decide(TOOL_CATALOG["generate_sections_auto"], state)
        assert curve.requires_confirmation is auto.requires_confirmation
        assert curve.reason_code == auto.reason_code

    def test_clean_session_runs_without_confirmation(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["generate_sections_curve"], ToolState())
        assert decision.requires_confirmation is False
        assert decision.reason_code == REASON_AUTONOMOUS

    def test_existing_sections_confirm_with_real_count(self) -> None:
        from core.ai_v2.agent.catalog import TOOL_CATALOG

        decision = decide(TOOL_CATALOG["generate_sections_curve"], ToolState(n_sections=78))
        assert decision.requires_confirmation is True
        assert decision.reason_code == REASON_REPLACE_EXISTING
        assert "78" in decision.human_summary_es
        assert "secciones" in decision.human_summary_es
