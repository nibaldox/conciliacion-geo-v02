"""Contract tests for the AI agent package (catalog, args, events, confirmations).

Anti-drift: the arg models must mirror the REAL request models bound to
the endpoints. The import of ``api`` modules is allowed ONLY here (in
tests) — ``core/ai_v2/agent`` never imports from ``api/``.

Intentional divergences (documented per the contract freeze):

- SectionAutoArgs compares against ``api.routers.sections.SectionAutoParams``
  (the model actually bound to POST /sections/auto), NOT
  ``api.schemas.SectionAutoParams``: the schema copy is stale — it
  carries an ``azimuth`` field the endpoint never reads and lacks
  ``length_up``/``length_down``, which the endpoint accepts.
- SectionDefinitionArgs (item of ``SectionManualArgs.sections``)
  compares against ``api.routers.sections.SectionCreate`` (the item
  model bound to POST /sections/manual) for the same reason;
  ``api.schemas.SectionCreate`` is the legacy duplicate without
  ``length_up``/``length_down``.
- SectionClickArgs compares against ``api.routers.sections.SectionClickParams``
  (this model only exists in the router, not in ``api.schemas``).
- RunReconciliationArgs compares against ``api.schemas.ProcessSettings``
  (the body model bound to POST /process) — exact match.
"""
from __future__ import annotations

import json
import time

import pytest
from pydantic import ValidationError

from core.ai_v2.agent.catalog import (
    AGENT_TOOLS,
    TOOL_CATALOG,
    get_tool,
    openai_tools,
    to_openai_tool,
)
from core.ai_v2.agent.confirmations import (
    PENDING_TTL_S,
    PendingRun,
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
    AchievementFilterArgs,
    BlastCorrelationArgs,
    BlastDamageArgs,
    ExportReportArgs,
    MeshIdArgs,
    NoArgs,
    ResultQueryArgs,
    RunReconciliationArgs,
    SectionAutoArgs,
    SectionClickArgs,
    SectionCurveArgs,
    SectionDefinitionArgs,
    SectionDeleteArgs,
    SectionIdArgs,
    SectionManualArgs,
    SectionUpdateArgs,
    ToolRisk,
    ToolSpec,
    ToolState,
)

EXPECTED_TOOL_NAMES = {
    "get_workflow_state",
    "list_meshes",
    "get_mesh_info",
    "list_sections",
    "add_section_click",
    "generate_sections_auto",
    "generate_sections_manual",
    "run_reconciliation",
    "get_settings",
    "get_results_summary",
    "get_profile",
    "get_design_achievement",
    "get_proposed_compliance",
    "query_results",
    "export_report",
    "get_blast_summary",
    "get_blast_correlation",
    "get_blast_damage_model",
    "update_section",
    "delete_section",
    "generate_sections_curve",
}

ALL_ARGS_MODELS = sorted(
    {spec.args_model for spec in AGENT_TOOLS} | {SectionDefinitionArgs},
    key=lambda model: model.__name__,
)

EXTRA_FIELD_PAYLOADS = {
    SectionAutoArgs: {"start": [0.0, 0.0], "end": [1.0, 1.0], "hacker": True},
    SectionManualArgs: {"sections": [{"origin": [0.0, 0.0], "azimuth": 0.0}], "spoof": 1},
    SectionClickArgs: {"origin": [0.0, 0.0], "injected": "x"},
    RunReconciliationArgs: {"resolution": 0.1, "unknown_key": 3},
    ExportReportArgs: {"format": "excel", "path": "/etc/passwd", "level": ["3065"]},
    MeshIdArgs: {"mesh_id": "abc", "session_id": "other"},
    SectionIdArgs: {"section_id": "0", "force": True},
    NoArgs: {"anything": 1},
    SectionDefinitionArgs: {"origin": [0.0, 0.0], "azimuth": 0.0, "blob": None},
    ResultQueryArgs: {"level": ["3065"], "session_id": "other"},
    AchievementFilterArgs: {"bench": [3], "force": True},
    BlastCorrelationArgs: {"tolerance": 10.0, "survey_date": "2026-06-01", "session_id": "other"},
    BlastDamageArgs: {"tolerance": 10.0, "survey_date": "2026-06-01", "section": ["S-01"]},
    SectionUpdateArgs: {"section_id": 0, "azimuth": 90.0, "hacker": True},
    SectionDeleteArgs: {"section_id": 0, "force": True},
    SectionCurveArgs: {"points": [[0.0, 0.0], [1.0, 1.0]], "spacing": 5.0, "hacker": True},
}


class TestCatalog:
    def test_catalog_has_exactly_21_tools(self) -> None:
        assert len(AGENT_TOOLS) == 21
        assert {spec.name for spec in AGENT_TOOLS} == EXPECTED_TOOL_NAMES

    def test_get_blast_correlation_is_read_with_frozen_text(self) -> None:
        spec = TOOL_CATALOG["get_blast_correlation"]
        assert spec.args_model is BlastCorrelationArgs
        assert spec.risk is ToolRisk.READ
        assert spec.description == (
            "Correlate blast holes with the cross-sections: per section hole count, charge, "
            "powder factor (g/t) and over/under-break, with units, status and source; optional "
            "tolerance (m) and survey_date filter."
        )
        assert spec.impact_summary == "Solo lectura: sin efecto sobre los datos de la sesión"

    def test_get_blast_damage_model_is_read_with_frozen_text(self) -> None:
        spec = TOOL_CATALOG["get_blast_damage_model"]
        assert spec.args_model is BlastDamageArgs
        assert spec.risk is ToolRisk.READ
        assert spec.description == (
            "Fit of over-break versus powder factor across sections, with the number of points "
            "and fit status; optional tolerance (m) and survey_date."
        )
        assert spec.impact_summary == "Solo lectura: sin efecto sobre los datos de la sesión"

    def test_get_blast_summary_is_noargs_read_with_frozen_text(self) -> None:
        spec = TOOL_CATALOG["get_blast_summary"]
        assert spec.args_model is NoArgs
        assert spec.risk is ToolRisk.READ
        assert spec.description == (
            "Summarize the session's blast holes: hole count, data status, rock density, "
            "bench height and inclination convention with their source and status, "
            "explosive coverage (unknown explosives are never treated as ANFO), "
            "deduplication and footprint counts."
        )
        assert spec.impact_summary == "Solo lectura: sin efecto sobre los datos de la sesión"

    def test_generate_sections_curve_is_replace_with_frozen_text(self) -> None:
        spec = TOOL_CATALOG["generate_sections_curve"]
        assert spec.args_model is SectionCurveArgs
        assert spec.risk is ToolRisk.REPLACE
        assert spec.state_keys == ("n_sections",)
        assert spec.state_keys == TOOL_CATALOG["generate_sections_auto"].state_keys
        assert spec.description == (
            "Generate cross-sections perpendicular to a polyline (for example a crest "
            "or contour segment) every `spacing` metres. Sections are appended to the "
            "existing ones and invalidate the previous analysis."
        )
        assert spec.impact_summary == TOOL_CATALOG["generate_sections_auto"].impact_summary

    def test_names_are_unique(self) -> None:
        names = [spec.name for spec in AGENT_TOOLS]
        assert len(names) == len(set(names))

    def test_tool_catalog_matches_agent_tools(self) -> None:
        assert set(TOOL_CATALOG) == EXPECTED_TOOL_NAMES
        assert get_tool("run_reconciliation") is TOOL_CATALOG["run_reconciliation"]
        assert get_tool("nonexistent") is None

    def test_no_file_upload_tools(self) -> None:
        assert "generate_sections_from_file" not in TOOL_CATALOG
        assert "upload_mesh" not in TOOL_CATALOG

    @pytest.mark.parametrize(
        "name, risk, state_keys, timeout_s, idempotent",
        [
            ("get_workflow_state", ToolRisk.READ, (), 30.0, False),
            ("list_meshes", ToolRisk.READ, (), 30.0, False),
            ("get_mesh_info", ToolRisk.READ, (), 30.0, False),
            ("list_sections", ToolRisk.READ, (), 30.0, False),
            ("add_section_click", ToolRisk.ADDITIVE, (), 30.0, False),
            ("generate_sections_auto", ToolRisk.REPLACE, ("n_sections",), 30.0, False),
            ("generate_sections_manual", ToolRisk.REPLACE, ("n_sections",), 30.0, False),
            ("run_reconciliation", ToolRisk.EXPENSIVE_REPLACE, ("n_results",), 300.0, False),
            ("get_settings", ToolRisk.READ, (), 30.0, False),
            ("get_results_summary", ToolRisk.READ, (), 30.0, False),
            ("get_profile", ToolRisk.READ, (), 30.0, False),
            ("get_design_achievement", ToolRisk.READ, (), 30.0, False),
            ("get_proposed_compliance", ToolRisk.READ, (), 30.0, False),
            ("query_results", ToolRisk.READ, (), 30.0, False),
            ("export_report", ToolRisk.EXPORT, (), 30.0, True),
            ("get_blast_summary", ToolRisk.READ, (), 30.0, False),
            ("get_blast_correlation", ToolRisk.READ, (), 30.0, False),
            ("get_blast_damage_model", ToolRisk.READ, (), 30.0, False),
            ("update_section", ToolRisk.REPLACE, ("n_results",), 30.0, False),
            ("delete_section", ToolRisk.DESTRUCTIVE, ("n_results",), 30.0, False),
            ("generate_sections_curve", ToolRisk.REPLACE, ("n_sections",), 30.0, False),
        ],
    )
    def test_spec_metadata(
        self,
        name: str,
        risk: ToolRisk,
        state_keys: tuple[str, ...],
        timeout_s: float,
        idempotent: bool,
    ) -> None:
        spec = TOOL_CATALOG[name]
        assert spec.risk is risk
        assert spec.state_keys == state_keys
        assert spec.timeout_s == timeout_s
        assert spec.idempotent is idempotent
        assert "{count}" in spec.impact_summary or spec.risk in (
            ToolRisk.READ,
            ToolRisk.ADDITIVE,
            ToolRisk.EXPORT,
        )

    def test_state_keys_are_real_tool_state_fields(self) -> None:
        state_fields = set(ToolState.model_fields)
        for spec in AGENT_TOOLS:
            assert set(spec.state_keys) <= state_fields


class TestOpenAiSchemas:
    @pytest.mark.parametrize("spec", AGENT_TOOLS, ids=lambda spec: spec.name)
    def test_spec_produces_openai_tool_schema(self, spec: ToolSpec) -> None:
        rendered = to_openai_tool(spec)
        assert rendered["type"] == "function"
        function = rendered["function"]
        assert function["name"] == spec.name
        assert function["description"] == spec.description
        parameters = function["parameters"]
        schema = spec.args_model.model_json_schema()
        assert parameters["type"] == "object"
        assert parameters == schema

    def test_openai_tools_covers_whole_catalog(self) -> None:
        rendered_names = [tool["function"]["name"] for tool in openai_tools()]
        assert rendered_names == [spec.name for spec in AGENT_TOOLS]

    def test_export_format_literal_matches_real_routes(self) -> None:
        schema = ExportReportArgs.model_json_schema()
        assert schema["properties"]["format"]["enum"] == [
            "excel",
            "word",
            "pdf",
            "dxf",
            "images",
        ]


class TestStrictArgs:
    @pytest.mark.parametrize("model", ALL_ARGS_MODELS, ids=lambda model: model.__name__)
    def test_rejects_extra_fields(self, model: type) -> None:
        payload = EXTRA_FIELD_PAYLOADS[model]
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    @pytest.mark.parametrize("model", ALL_ARGS_MODELS, ids=lambda model: model.__name__)
    def test_accepts_valid_payload(self, model: type) -> None:
        if model is NoArgs:
            model.model_validate({})
            return
        if model is SectionManualArgs:
            model.model_validate(
                {"sections": [{"origin": [10.0, 20.0], "azimuth": 45.0}]}
            )
            return
        valid = {
            key: value
            for key, value in EXTRA_FIELD_PAYLOADS[model].items()
            if not isinstance(value, (bool, str)) or key != "hacker"
        }
        valid = {
            key: value
            for key, value in valid.items()
            if key in model.model_fields
        }
        if model is ExportReportArgs and "format" not in valid:
            valid["format"] = "excel"
        model.model_validate(valid)

    def test_export_rejects_unknown_format(self) -> None:
        with pytest.raises(ValidationError):
            ExportReportArgs.model_validate({"format": "csv"})

    def test_export_fields_follow_the_frozen_contract(self) -> None:
        assert set(ExportReportArgs.model_fields) == {
            "format",
            "sector",
            "section",
            "levels_by_sector",
            "project",
            "author",
        }
        assert ExportReportArgs.__doc__ is not None
        assert "literal" in ExportReportArgs.__doc__.lower()


class TestSectionEditArgs:
    @pytest.mark.parametrize(
        "override",
        [
            {"name": "Norte"},
            {"origin": [1.0, 2.0]},
            {"azimuth": 0.0},
            {"length": 10.0},
            {"length_up": 5.0},
            {"length_down": 5.0},
            {"sector": ""},
        ],
    )
    def test_update_accepts_any_single_override(self, override: dict) -> None:
        args = SectionUpdateArgs.model_validate({"section_id": 3, **override})
        assert args.section_id == 3
        assert {k: getattr(args, k) for k in override} == override

    def test_update_requires_at_least_one_override(self) -> None:
        with pytest.raises(ValidationError, match="at least one field"):
            SectionUpdateArgs.model_validate({"section_id": 0})

    def test_update_explicit_nulls_count_as_no_override(self) -> None:
        with pytest.raises(ValidationError, match="at least one field"):
            SectionUpdateArgs.model_validate({"section_id": 0, "name": None, "azimuth": None})

    @pytest.mark.parametrize(
        "override",
        [
            {"azimuth": 360.5},
            {"azimuth": -0.1},
            {"length": 0.0},
            {"length": 10000.5},
            {"length_up": 0.0},
            {"length_down": 10001.0},
            {"origin": [1.0]},
            {"origin": [1.0, 2.0, 3.0]},
            {"name": "n" * 101},
            {"sector": "s" * 101},
        ],
    )
    def test_update_overrides_mirror_section_definition_bounds(self, override: dict) -> None:
        with pytest.raises(ValidationError):
            SectionUpdateArgs.model_validate({"section_id": 0, **override})

    @pytest.mark.parametrize("model", [SectionUpdateArgs, SectionDeleteArgs], ids=lambda m: m.__name__)
    @pytest.mark.parametrize("section_id", [-1, 100000])
    def test_section_id_outside_0_to_99999_is_rejected(self, model, section_id: int) -> None:
        payload = {"section_id": section_id, "azimuth": 1.0} if model is SectionUpdateArgs else {"section_id": section_id}
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    @pytest.mark.parametrize("model", [SectionUpdateArgs, SectionDeleteArgs], ids=lambda m: m.__name__)
    def test_section_id_bounds_are_inclusive(self, model) -> None:
        for section_id in (0, 99999):
            payload = {"section_id": section_id, "azimuth": 1.0} if model is SectionUpdateArgs else {"section_id": section_id}
            assert model.model_validate(payload).section_id == section_id

    def test_delete_requires_section_id(self) -> None:
        with pytest.raises(ValidationError):
            SectionDeleteArgs.model_validate({})

    def test_section_edit_tools_never_expose_session_or_path(self) -> None:
        for model in (SectionUpdateArgs, SectionDeleteArgs):
            assert "session_id" not in model.model_fields
            assert "path" not in model.model_fields


class TestSectionCurveArgs:
    def test_defaults_mirror_the_rest_model(self) -> None:
        args = SectionCurveArgs.model_validate({"points": [[0.0, 0.0], [10.0, 0.0]]})
        assert args.spacing == 10.0
        assert args.length == 200.0
        assert args.length_up is None
        assert args.length_down is None
        assert args.sector == ""

    def test_docstring_marks_the_bounds_as_agent_restrictions(self) -> None:
        assert SectionCurveArgs.__doc__ is not None
        assert "agent restriction" in SectionCurveArgs.__doc__.lower()

    def test_one_point_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SectionCurveArgs.model_validate({"points": [[0.0, 0.0]]})

    def test_more_than_200_points_is_rejected(self) -> None:
        points = [[float(index), 0.0] for index in range(201)]
        with pytest.raises(ValidationError):
            SectionCurveArgs.model_validate({"points": points})

    def test_200_points_are_accepted(self) -> None:
        points = [[float(index), 0.0] for index in range(200)]
        assert len(SectionCurveArgs.model_validate({"points": points}).points) == 200

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_coordinate_is_rejected(self, value: float) -> None:
        with pytest.raises(ValidationError):
            SectionCurveArgs.model_validate({"points": [[value, 0.0], [1.0, 1.0]]})

    @pytest.mark.parametrize("point", [[0.0], [0.0, 1.0, 2.0]])
    def test_each_point_must_be_exactly_two_numbers(self, point: list) -> None:
        with pytest.raises(ValidationError):
            SectionCurveArgs.model_validate({"points": [point, [1.0, 1.0]]})

    @pytest.mark.parametrize(
        "override",
        [
            {"spacing": 0.0},
            {"spacing": -1.0},
            {"spacing": 1000.5},
            {"spacing": float("nan")},
            {"length": 0.0},
            {"length": 10000.5},
            {"length_up": 0.0},
            {"length_down": 10001.0},
            {"sector": "s" * 101},
        ],
    )
    def test_bounds_are_enforced(self, override: dict) -> None:
        with pytest.raises(ValidationError):
            SectionCurveArgs.model_validate({"points": [[0.0, 0.0], [1.0, 1.0]], **override})

    def test_spacing_upper_bound_is_inclusive(self) -> None:
        args = SectionCurveArgs.model_validate({"points": [[0.0, 0.0], [1.0, 1.0]], "spacing": 1000.0})
        assert args.spacing == 1000.0


class TestBlastArgs:
    @pytest.mark.parametrize("model", [BlastCorrelationArgs, BlastDamageArgs], ids=lambda m: m.__name__)
    @pytest.mark.parametrize("tolerance", [0.0, -1.0, 100.5, float("nan"), float("inf"), float("-inf")])
    def test_tolerance_must_be_finite_positive_and_at_most_100(self, model, tolerance) -> None:
        with pytest.raises(ValidationError):
            model.model_validate({"tolerance": tolerance})

    @pytest.mark.parametrize("model", [BlastCorrelationArgs, BlastDamageArgs], ids=lambda m: m.__name__)
    @pytest.mark.parametrize("tolerance", [0.5, 15.0, 100.0])
    def test_tolerance_accepts_meters_within_bounds(self, model, tolerance) -> None:
        assert model.model_validate({"tolerance": tolerance}).tolerance == tolerance

    @pytest.mark.parametrize("model", [BlastCorrelationArgs, BlastDamageArgs], ids=lambda m: m.__name__)
    def test_defaults_leave_tolerance_and_survey_date_unset(self, model) -> None:
        args = model.model_validate({})
        assert args.tolerance is None
        assert args.survey_date is None

    @pytest.mark.parametrize("model", [BlastCorrelationArgs, BlastDamageArgs], ids=lambda m: m.__name__)
    @pytest.mark.parametrize("value", ["2026-13-01", "01/06/2026", "2026-06-01T10:00", 20260601])
    def test_survey_date_must_be_iso_date(self, model, value) -> None:
        with pytest.raises(ValidationError):
            model.model_validate({"survey_date": value})

    def test_survey_date_parses_to_date(self) -> None:
        from datetime import date

        args = BlastCorrelationArgs.model_validate({"survey_date": "2026-06-01"})
        assert args.survey_date == date(2026, 6, 1)


class TestToolState:
    def test_fingerprint_is_stable_across_instances(self) -> None:
        assert ToolState().fingerprint() == ToolState().fingerprint()
        left = ToolState(n_sections=5, has_design_mesh=True)
        right = ToolState(has_design_mesh=True, n_sections=5)
        assert left.fingerprint() == right.fingerprint()

    def test_fingerprint_changes_with_state(self) -> None:
        assert ToolState(n_sections=1).fingerprint() != ToolState().fingerprint()

    def test_fingerprint_is_hex_sha256_length(self) -> None:
        fingerprint = ToolState(n_results=9).fingerprint()
        assert len(fingerprint) == 64
        int(fingerprint, 16)

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            ToolState(n_sections=0, spoofed=True)


class TestToolSpecFrozen:
    def test_spec_is_immutable(self) -> None:
        spec = TOOL_CATALOG["run_reconciliation"]
        with pytest.raises(ValidationError):
            spec.timeout_s = 1.0


class TestEvents:
    def _sample_events(self) -> list[AgentEvent]:
        return [
            TextEvent(content="Voy a generar 78 secciones…"),
            ToolCallEvent(
                invocation_id="inv_abc",
                name="generate_sections_auto",
                args={"start": [0.0, 0.0], "end": [1.0, 1.0]},
                requires_confirmation=False,
            ),
            ToolResultEvent(
                invocation_id="inv_abc",
                name="generate_sections_auto",
                ok=True,
                summary="78 secciones creadas",
                duration_ms=1200.0,
                error=None,
            ),
            ConfirmationRequiredEvent(
                invocation_id="inv_def",
                name="run_reconciliation",
                args_summary="Procesar 78 secciones (sobrescribe 78 resultados existentes)",
            ),
            ErrorEvent(content="Proveedor sin soporte de herramientas"),
            DoneEvent(finish_reason="stop", usage=None, cached=False),
        ]

    def test_round_trip_through_ndjson(self) -> None:
        for event in self._sample_events():
            line = event_to_ndjson(event)
            assert "\n" not in line
            parsed = parse_event_line(line)
            assert parsed == event

    def test_discriminated_union_types(self) -> None:
        text, call, result, confirm, error, done = self._sample_events()
        assert isinstance(text, TextEvent) and text.type == "text"
        assert isinstance(call, ToolCallEvent) and call.type == "tool_call"
        assert isinstance(result, ToolResultEvent) and result.type == "tool_result"
        assert isinstance(confirm, ConfirmationRequiredEvent)
        assert confirm.type == "confirmation_required"
        assert isinstance(error, ErrorEvent) and error.type == "error"
        assert isinstance(done, DoneEvent) and done.type == "done"

    def test_done_finish_reason_literal(self) -> None:
        for reason in ("stop", "error", "confirmation_required"):
            event = DoneEvent(finish_reason=reason)
            assert parse_event_line(event_to_ndjson(event)).finish_reason == reason
        with pytest.raises(ValidationError):
            DoneEvent(finish_reason="length")

    def test_done_event_with_usage(self) -> None:
        from core.ai_v2.models import AIUsage

        done = DoneEvent(
            finish_reason="stop",
            usage=AIUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        parsed = parse_event_line(event_to_ndjson(done))
        assert isinstance(parsed, DoneEvent)
        assert parsed.usage is not None and parsed.usage.total_tokens == 15

    def test_invalid_lines_raise_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_event_line("")
        with pytest.raises(ValueError):
            parse_event_line("   ")
        with pytest.raises(ValueError):
            parse_event_line("not json {")
        with pytest.raises(ValueError):
            parse_event_line(json.dumps({"type": "unknown_event", "x": 1}))
        with pytest.raises(ValueError):
            parse_event_line(json.dumps({"type": "text"}))

    def test_events_reject_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            TextEvent(content="hi", smuggled="payload")
        with pytest.raises(ValidationError):
            ToolCallEvent(
                invocation_id="inv_1",
                name="t",
                args={},
                requires_confirmation=False,
                auto_approve=True,
            )


class TestConfirmations:
    def _pending_run(self, invocation_id: str, session_id: str = "sess-1") -> PendingRun:
        now = time.time()
        return PendingRun(
            invocation_id=invocation_id,
            session_id=session_id,
            run_id="run-1",
            provider="openai",
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "go"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "run_reconciliation", "arguments": "{}"},
                        }
                    ],
                },
            ],
            tool_call_id="call_1",
            tool_name="run_reconciliation",
            args_sha256=canonical_args_sha256({"resolution": 0.1}),
            state_fingerprint=ToolState().fingerprint(),
            created_at=now,
            expires_at=now + PENDING_TTL_S,
        )

    def test_ttl_is_15_minutes(self) -> None:
        assert PENDING_TTL_S == 900.0

    def test_invocation_ids_are_unique_and_prefixed(self) -> None:
        ids = {new_invocation_id() for _ in range(100)}
        assert len(ids) == 100
        for invocation_id in ids:
            assert invocation_id.startswith("inv_")

    def test_canonical_args_hash_is_order_insensitive(self) -> None:
        left = canonical_args_sha256({"a": 1, "b": [1, 2]})
        right = canonical_args_sha256({"b": [1, 2], "a": 1})
        assert left == right
        assert len(left) == 64
        assert canonical_args_sha256({"a": 1}) != canonical_args_sha256({"a": 2})

    def test_pending_run_rejects_bad_hashes_and_empty_ids(self) -> None:
        run = self._pending_run("inv_x")
        assert run.confirmations_used == 0
        good = run.model_dump()
        with pytest.raises(ValidationError):
            PendingRun(**{**good, "args_sha256": "short"})
        with pytest.raises(ValidationError):
            PendingRun(**{**good, "invocation_id": ""})

    def test_store_interface_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            PendingRunStore()

    def test_minimal_store_contract(self) -> None:
        class InMemoryStore(PendingRunStore):
            def __init__(self) -> None:
                self.runs: dict[str, PendingRun] = {}
                self.claimed: set[str] = set()

            def create(self, run: PendingRun) -> str:
                self.runs[run.invocation_id] = run
                return run.invocation_id

            def claim(self, invocation_id: str, session_id: str) -> PendingRun:
                run = self.runs.get(invocation_id)
                if run is None:
                    raise KeyError(invocation_id)
                if run.session_id != session_id:
                    raise PermissionError(invocation_id)
                if invocation_id in self.claimed:
                    raise RuntimeError(invocation_id)
                self.claimed.add(invocation_id)
                return run

            def invalidate(self, invocation_id: str) -> None:
                self.runs.pop(invocation_id, None)
                self.claimed.discard(invocation_id)

        store = InMemoryStore()
        run = self._pending_run("inv_1", session_id="sess-1")
        assert store.create(run) == "inv_1"
        assert store.claim("inv_1", "sess-1") is run
        with pytest.raises(RuntimeError):
            store.claim("inv_1", "sess-1")
        store.invalidate("inv_1")
        with pytest.raises(KeyError):
            store.claim("inv_1", "sess-1")

        foreign = self._pending_run("inv_2", session_id="sess-2")
        store.create(foreign)
        with pytest.raises(PermissionError):
            store.claim("inv_2", "sess-1")


class TestAntiDriftAgainstRealRouters:
    """Agent arg models must mirror the REAL endpoint request models.

    See module docstring for the documented divergences (router-local
    models over stale ``api.schemas`` copies). Imports from ``api`` are
    allowed ONLY in tests — never in ``core``.
    """

    def _field_names(self, model: type) -> set[str]:
        return set(model.model_fields)

    def test_section_auto_args_match_real_endpoint_model(self) -> None:
        from api.routers.sections import SectionAutoParams as RealAutoParams

        assert self._field_names(SectionAutoArgs) == self._field_names(RealAutoParams)

    def test_section_manual_args_match_real_endpoint_model(self) -> None:
        from api.routers.sections import SectionCreate as RealManualItem

        assert self._field_names(SectionDefinitionArgs) == self._field_names(
            RealManualItem
        )
        assert set(SectionManualArgs.model_fields) == {"sections"}

    def test_section_click_args_match_real_endpoint_model(self) -> None:
        from api.routers.sections import SectionClickParams as RealClickParams

        assert self._field_names(SectionClickArgs) == self._field_names(RealClickParams)

    def test_section_update_args_match_rest_section_body(self) -> None:
        from api.routers.sections import SectionCreate as RealSectionBody

        assert self._field_names(SectionUpdateArgs) - {"section_id"} == self._field_names(
            RealSectionBody
        )

    def test_run_reconciliation_args_match_process_settings(self) -> None:
        from api.schemas import ProcessSettings as RealProcessSettings

        assert self._field_names(RunReconciliationArgs) == self._field_names(
            RealProcessSettings
        )

    def test_core_agent_never_imports_api(self) -> None:
        import re
        from pathlib import Path

        import core.ai_v2.agent as agent_pkg

        package_dir = Path(agent_pkg.__file__).resolve().parent
        import_line = re.compile(r"^\s*(from|import)\s+api", re.MULTILINE)
        for py_file in sorted(package_dir.glob("*.py")):
            source = py_file.read_text(encoding="utf-8")
            assert not import_line.search(source), f"{py_file.name} imports from api"
