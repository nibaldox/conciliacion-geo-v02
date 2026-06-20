"""Tests for core.compliance_status — single source of truth for status strings.

Guards against accidental edits to the literal status / feasibility values
that the rest of the pipeline (param_extractor, excel_writer, report_generator,
ai_service, blast_advisor) compares against.
"""
import pytest

from core.compliance_status import (
    ALL_FEASIBILITY,
    ALL_STATUSES,
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INFEASIBLE,
    FEASIBILITY_INSUFFICIENT,
    PASSING_STATUSES,
    STATUS_BANCO_ADICIONAL,
    STATUS_CUMPLE,
    STATUS_EXTRA,
    STATUS_FALTA_BANCO,
    STATUS_FUERA,
    STATUS_NO_CONSTRUIDO,
    STATUS_NO_CUMPLE,
    STATUS_RAMPA_OK,
    is_passing_status,
)


class TestStatusLiterals:
    """Status strings must keep their exact published values."""

    def test_cumple(self):
        assert STATUS_CUMPLE == "CUMPLE"

    def test_fuera(self):
        assert STATUS_FUERA == "FUERA DE TOLERANCIA"

    def test_no_cumple(self):
        assert STATUS_NO_CUMPLE == "NO CUMPLE"

    def test_no_construido(self):
        assert STATUS_NO_CONSTRUIDO == "NO CONSTRUIDO"

    def test_falta_banco(self):
        assert STATUS_FALTA_BANCO == "FALTA BANCO"

    def test_extra(self):
        assert STATUS_EXTRA == "EXTRA"

    def test_banco_adicional(self):
        assert STATUS_BANCO_ADICIONAL == "BANCO ADICIONAL"

    def test_rampa_ok(self):
        assert STATUS_RAMPA_OK == "RAMPA OK"


class TestAllStatuses:
    def test_is_frozenset(self):
        assert isinstance(ALL_STATUSES, frozenset)

    def test_contains_every_defined_status(self):
        defined = {
            STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE,
            STATUS_NO_CONSTRUIDO, STATUS_FALTA_BANCO, STATUS_EXTRA,
            STATUS_BANCO_ADICIONAL, STATUS_RAMPA_OK,
        }
        assert defined == set(ALL_STATUSES)

    def test_has_eight_statuses(self):
        assert len(ALL_STATUSES) == 8

    def test_statuses_are_unique(self):
        assert len(ALL_STATUSES) == len({
            STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE,
            STATUS_NO_CONSTRUIDO, STATUS_FALTA_BANCO, STATUS_EXTRA,
            STATUS_BANCO_ADICIONAL, STATUS_RAMPA_OK,
        })


class TestPassingStatus:
    def test_cumple_passes(self):
        assert is_passing_status(STATUS_CUMPLE) is True

    def test_rampa_ok_passes(self):
        assert is_passing_status(STATUS_RAMPA_OK) is True

    @pytest.mark.parametrize("status", [
        STATUS_FUERA,
        STATUS_NO_CUMPLE,
        STATUS_NO_CONSTRUIDO,
        STATUS_FALTA_BANCO,
        STATUS_EXTRA,
        STATUS_BANCO_ADICIONAL,
    ])
    def test_non_passing_statuses(self, status):
        assert is_passing_status(status) is False

    def test_none_is_not_passing(self):
        assert is_passing_status(None) is False

    def test_empty_string_is_not_passing(self):
        assert is_passing_status("") is False

    def test_passing_subset_of_all(self):
        assert PASSING_STATUSES <= ALL_STATUSES

    def test_passing_statuses_content(self):
        assert PASSING_STATUSES == frozenset({STATUS_CUMPLE, STATUS_RAMPA_OK})


class TestFeasibilityLiterals:
    def test_applicable(self):
        assert FEASIBILITY_APPLICABLE == "APPLICABLE"

    def test_caution(self):
        assert FEASIBILITY_CAUTION == "CAUTION"

    def test_infeasible(self):
        assert FEASIBILITY_INFEASIBLE == "INFEASIBLE"

    def test_insufficient(self):
        assert FEASIBILITY_INSUFFICIENT == "INSUFFICIENT_DATA"

    def test_all_feasibility_contains_each(self):
        for value in (
            FEASIBILITY_APPLICABLE,
            FEASIBILITY_CAUTION,
            FEASIBILITY_INFEASIBLE,
            FEASIBILITY_INSUFFICIENT,
        ):
            assert value in ALL_FEASIBILITY

    def test_all_feasibility_has_four(self):
        assert len(ALL_FEASIBILITY) == 4

    def test_feasibility_values_distinct_from_statuses(self):
        assert ALL_FEASIBILITY.isdisjoint(ALL_STATUSES)
