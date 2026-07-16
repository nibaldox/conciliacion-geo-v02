"""Tests puros para ui.tabs.ai_report.prompt."""
from __future__ import annotations

import pandas as pd
import pytest

from ui.tabs.ai_report.prompt import (
    build_metadata,
    build_prompt,
    compute_blast_trend_metadata,
)


class TestBuildPrompt:
    def test_empty_prompt(self):
        assert build_prompt("", [], {}, None) == "Sin contexto adicional."

    def test_with_notes(self):
        text = build_prompt("Revisar desviaciones", [], {}, None)
        assert "Notas del usuario" in text
        assert "Revisar desviaciones" in text

    def test_with_sections(self):
        text = build_prompt("", ["S-1", "S-2"], {}, None)
        assert "Secciones" in text
        assert "S-1, S-2" in text

    def test_with_filters(self):
        text = build_prompt("", [], {"sector": ["N"], "bench": [1, 2]}, None)
        assert "Filtros activos" in text
        assert "sector=N" in text
        assert "banco=1,2" in text

    def test_with_blast_trend(self):
        trend = {"pf_promedio": 0.5, "pf_desviacion": 0.1, "n_pozos_total": 10}
        text = build_prompt("", [], {}, trend)
        assert "Tendencia de tronadura" in text
        assert "0.5" in text


class TestBuildMetadata:
    def test_default_values(self):
        meta = build_metadata([], None, None, "Proyecto", "global")
        assert meta["project_name"] == "Proyecto"
        assert meta["banco"] == "N/A"
        assert "fecha_informe" in meta

    def test_section_filter_overrides_active_section(self):
        meta = build_metadata(
            [], {"section": ["S-1", "S-2"]}, None, "P", "legacy"
        )
        assert meta["seccion"] == "S-1, S-2"

    def test_bench_filter(self):
        meta = build_metadata([], {"bench": [1, 2]}, None, "P", "global")
        assert meta["banco"] == "1, 2"

    def test_blast_trend_included(self):
        trend = {"pf_promedio": 0.5}
        meta = build_metadata([], None, trend, "P", "global")
        assert meta["blast_trend"] == trend

    def test_notes_included(self):
        meta = build_metadata([], None, None, "P", "global", notes="hola")
        assert meta["user_notes"] == "hola"


class TestComputeBlastTrendMetadata:
    def test_none_df_returns_none(self):
        assert compute_blast_trend_metadata(None, [], []) is None

    def test_empty_df_returns_none(self):
        df = pd.DataFrame()
        assert compute_blast_trend_metadata(df, [], []) is None

    def test_empty_sections_returns_none(self):
        df = pd.DataFrame({"col": [1]})
        assert compute_blast_trend_metadata(df, [], []) is None

    def test_empty_comparisons_returns_none(self):
        df = pd.DataFrame({"col": [1]})
        assert compute_blast_trend_metadata(df, ["S-1"], []) is None

    def test_exception_handling_returns_none(self):
        # Passing a non-DataFrame triggers an exception path inside the helper.
        result = compute_blast_trend_metadata("not-a-df", ["S-1"], [{}])
        assert result is None
