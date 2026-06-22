"""Tests for ui.labels — Sprint 1 issue B3+B4.

Single source of truth for UI display column labels and status colors.
"""
from __future__ import annotations

import pytest

from ui.labels import (
    DISPLAY_COLUMNS,
    STATUS_COLORS,
    highlight_status,
    select_display_columns,
)


class TestDisplayColumns:
    def test_contains_required_keys(self):
        for key in (
            "sector", "section", "bench_num", "level",
            "height_status", "angle_status", "berm_status",
            "spill_width", "effective_berm",
            "delta_crest", "delta_toe",
        ):
            assert key in DISPLAY_COLUMNS

    def test_values_are_non_empty_strings(self):
        for k, v in DISPLAY_COLUMNS.items():
            assert isinstance(v, str) and v.strip(), f"{k} -> {v!r}"


class TestStatusColors:
    def test_has_all_compliance_values(self):
        for s in (
            "CUMPLE", "FUERA DE TOLERANCIA", "NO CUMPLE",
            "NO CONSTRUIDO", "EXTRA", "FALTA BANCO",
            "BANCO ADICIONAL", "RAMPA OK",
        ):
            assert s in STATUS_COLORS

    def test_values_are_css(self):
        for s, css in STATUS_COLORS.items():
            assert "background-color" in css
            assert "color" in css


class TestHighlightStatus:
    @pytest.mark.parametrize("status", [
        "CUMPLE", "FUERA DE TOLERANCIA", "NO CUMPLE",
        "NO CONSTRUIDO", "EXTRA",
    ])
    def test_known_status_returns_css(self, status):
        css = highlight_status(status)
        assert "background-color" in css

    def test_none_returns_empty(self):
        assert highlight_status(None) == ""

    def test_unknown_returns_empty(self):
        assert highlight_status("NOT_A_STATUS") == ""

    def test_non_string_input_handled(self):
        # Substring fallback for compound labels.
        assert highlight_status("BANCO ADICIONAL extra info") != ""


class TestSelectDisplayColumns:
    def test_returns_only_available(self):
        out = select_display_columns(["sector", "height_status", "unknown_col"])
        assert out == ["sector", "height_status"]

    def test_empty_input(self):
        assert select_display_columns([]) == []

    def test_preserves_canonical_order(self):
        # Even if input order differs, output is in DISPLAY_COLUMNS order.
        out = select_display_columns(["berm_status", "sector", "height_status"])
        assert out == ["sector", "height_status", "berm_status"]
