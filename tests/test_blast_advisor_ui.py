"""Tests for Phase 5 UI integration of ``core.blast_advisor``.

These tests verify the data flow that the Streamlit UI consumes from
:mod:`core.blast_advisor` without importing Streamlit itself. They focus
on:

* Global recommendation from a fitted PF→damage model.
* Per-sector recommendation grouping.
* Spanish-neutral wording in the formatted text.
* Sensitivity to the user-controlled ``target_overbreak_m`` slider.
* Graceful degradation when the model is not confident enough.

The companion tests in ``tests/test_blast_advisor.py`` already cover the
pure advisor API. The five tests here exist to lock the UI↔core contract
end-to-end (realistic DataFrame inputs → engine outputs that the UI can
render directly).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.blast_advisor import (
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INSUFFICIENT,
    format_recommendation_text,
    recommend_by_sector,
    recommend_pf_adjustment,
)
from core.blast_model import fit_powder_factor_damage_model
from core.config import ADVISOR


def _positive_model(n: int = 20, beta1: float = 1.4, beta0: float = -0.2) -> dict:
    """Model with positive slope: more PF -> more damage."""
    return {
        "beta0": beta0,
        "beta1": beta1,
        "r_squared": 0.6,
        "p_value": 0.014,
        "n": n,
        "std_err_beta1": 0.2,
        "ci_beta1_low": beta1 - 0.4,
        "ci_beta1_high": beta1 + 0.4,
        "mean_pf": 0.45,
        "confidence": "HIGH",
        "is_significant": True,
    }


def _build_synthetic_sections(n: int = 8, seed: int = 42) -> pd.DataFrame:
    """Build a DataFrame that mimics what the UI produces per cross-section."""
    rng = np.random.default_rng(seed)
    pf = np.clip(rng.normal(0.45, 0.10, size=n), 0.20, 0.80)
    sectors = rng.choice(["Norte", "Sur", "Este"], size=n)
    damage = -0.15 + 1.4 * pf + rng.normal(0, 0.10, size=n)
    return pd.DataFrame(
        {
            "section": [f"S{i + 1:02d}" for i in range(n)],
            "sector": sectors,
            "pf_vol_avg_kgm3": pf,
            "avg_over_break": damage,
        }
    )


class TestUIRecommendationFlow:
    def test_recommend_global_with_synthetic_data(self):
        df = _build_synthetic_sections(n=8)

        model = fit_powder_factor_damage_model(
            df["pf_vol_avg_kgm3"].values,
            df["avg_over_break"].values,
        )
        assert model["confidence"] != "INSUFFICIENT", (
            "Synthetic data should fit a confident model"
        )

        valid_pf_mean = float(df["pf_vol_avg_kgm3"].mean())
        rec = recommend_pf_adjustment(
            model,
            current_pf=valid_pf_mean,
            target_overbreak_m=ADVISOR.target_overbreak_m,
        )

        assert rec["feasibility"] in {FEASIBILITY_APPLICABLE, FEASIBILITY_CAUTION}
        assert np.isfinite(rec["delta_pf"])
        assert np.isfinite(rec["delta_pf_pct"])
        assert rec["current_pf"] == pytest.approx(valid_pf_mean)
        assert np.isfinite(rec["predicted_current_damage"])
        assert rec["predicted_target_damage"] == pytest.approx(ADVISOR.target_overbreak_m)

    def test_recommend_by_sector_groups_correctly(self):
        df = pd.DataFrame(
            {
                "section": [f"S{i:02d}" for i in range(1, 10)],
                "sector": [
                    "Norte", "Norte", "Norte",
                    "Sur", "Sur", "Sur",
                    "Este", "Este", "Este",
                ],
                "pf_vol_avg_kgm3": [0.55, 0.50, 0.48, 0.42, 0.40, 0.41, 0.32, 0.34, 0.33],
                "avg_over_break": [0.6, 0.55, 0.5, 0.4, 0.38, 0.42, 0.18, 0.20, 0.22],
            }
        )

        model = fit_powder_factor_damage_model(
            df["pf_vol_avg_kgm3"].values,
            df["avg_over_break"].values,
        )
        assert model["confidence"] != "INSUFFICIENT"

        df_recs = recommend_by_sector(
            df, model, group_col="sector",
            target_overbreak_m=ADVISOR.target_overbreak_m,
        )

        assert len(df_recs) == 3
        assert set(df_recs["group_value"]) == {"Norte", "Sur", "Este"}

        for feas in df_recs["feasibility"]:
            assert feas in {
                FEASIBILITY_APPLICABLE,
                FEASIBILITY_CAUTION,
                FEASIBILITY_INSUFFICIENT,
            }

        norte = df_recs.loc[df_recs["group_value"] == "Norte"].iloc[0]
        assert norte["n_wells"] == 3
        assert norte["current_pf"] == pytest.approx(
            df.loc[df["sector"] == "Norte", "pf_vol_avg_kgm3"].mean()
        )
        assert norte["delta_pf_pct"] < 0

        este = df_recs.loc[df_recs["group_value"] == "Este"].iloc[0]
        assert este["current_pf"] < norte["current_pf"]

    def test_format_message_in_spanish(self):
        df = _build_synthetic_sections(n=8)
        model = fit_powder_factor_damage_model(
            df["pf_vol_avg_kgm3"].values,
            df["avg_over_break"].values,
        )
        assert model["confidence"] != "INSUFFICIENT"

        rec = recommend_pf_adjustment(
            model,
            current_pf=float(df["pf_vol_avg_kgm3"].mean()),
        )

        raw_message = rec["message"].lower()
        assert any(verb in raw_message for verb in ("reducir", "aumentar", "mantener")), (
            f"Raw message should contain Spanish verb: {rec['message']}"
        )

        formatted = format_recommendation_text(rec, section_name="Norte").lower()
        for keyword in ("pf", "kg/m3", "objetivo"):
            assert keyword in formatted, (
                f"Formatted message should contain '{keyword}': {formatted}"
            )
        assert "ajustar" in formatted or "ajuste" in formatted, (
            f"Formatted message should describe an adjustment: {formatted}"
        )
        assert "norte" in formatted

    def test_target_slider_changes_recommendation(self):
        df = _build_synthetic_sections(n=8)
        model = fit_powder_factor_damage_model(
            df["pf_vol_avg_kgm3"].values,
            df["avg_over_break"].values,
        )
        assert model["confidence"] != "INSUFFICIENT"

        current_pf = float(df["pf_vol_avg_kgm3"].mean())
        rec_low = recommend_pf_adjustment(model, current_pf=current_pf, target_overbreak_m=0.3)
        rec_high = recommend_pf_adjustment(model, current_pf=current_pf, target_overbreak_m=0.7)

        assert rec_low["delta_pf_pct"] != rec_high["delta_pf_pct"], (
            "Different target_overbreak_m values should yield different delta_pf_pct"
        )
        assert rec_low["predicted_target_damage"] == pytest.approx(0.3)
        assert rec_high["predicted_target_damage"] == pytest.approx(0.7)

        if rec_low["feasibility"] != FEASIBILITY_INSUFFICIENT:
            assert np.isfinite(rec_low["delta_pf_pct"])
        if rec_high["feasibility"] != FEASIBILITY_INSUFFICIENT:
            assert np.isfinite(rec_high["delta_pf_pct"])

    def test_insufficient_data_degrades_gracefully(self):
        pf = np.array([0.40, 0.45, 0.50], dtype=float)
        dmg = np.array([0.30, 0.40, 0.50], dtype=float)

        model = fit_powder_factor_damage_model(pf, dmg, min_samples=5)
        assert model["confidence"] == "INSUFFICIENT"
        assert model["n"] == 3
        assert model["is_significant"] is False

        rec = recommend_pf_adjustment(model, current_pf=0.45)
        assert rec["feasibility"] == FEASIBILITY_INSUFFICIENT
        assert rec["delta_pf"] == 0.0
        assert rec["delta_pf_pct"] == 0.0
        assert np.isfinite(rec["predicted_current_damage"])

        formatted = format_recommendation_text(rec, section_name="S01")
        assert "insuficiente" in formatted.lower() or "no se puede" in formatted.lower()


class TestUIRecommendationIntegration:
    """Static checks that confirm the UI files actually wire the advisor."""

    @classmethod
    def setup_class(cls):
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[1]
        cls.blast_correlation_source = (
            repo_root / "ui" / "tabs" / "blast_correlation.py"
        ).read_text(encoding="utf-8")
        cls.ai_report_source = (
            repo_root / "ui" / "tabs" / "ai_report.py"
        ).read_text(encoding="utf-8")

    def test_blast_correlation_imports_advisor(self):
        assert "from core.blast_advisor import" in self.blast_correlation_source
        assert "recommend_pf_adjustment" in self.blast_correlation_source
        assert "recommend_by_sector" in self.blast_correlation_source
        assert "format_recommendation_text" in self.blast_correlation_source

    def test_blast_correlation_has_recommendations_expander(self):
        assert "Recomendaciones de Ajuste de Carga" in self.blast_correlation_source
        assert "advisor_target_overbreak" in self.blast_correlation_source

    @pytest.mark.skip(reason="ui/tabs/ai_report.py was replaced with a v2 stub in Phase 2; full LLM integration re-lands in Phase 4.")
    def test_ai_report_imports_advisor(self):
        assert "from core.blast_advisor import" in self.ai_report_source
        assert "from core.blast_model import" in self.ai_report_source
        assert "fit_powder_factor_damage_model" in self.ai_report_source

    @pytest.mark.skip(reason="ui/tabs/ai_report.py was replaced with a v2 stub in Phase 2; quantitative recommendations re-lands in Phase 4.")
    def test_ai_report_has_quantitative_block(self):
        assert "Recomendaciones Cuantitativas del Modelo" in self.ai_report_source
        assert "_render_quantitative_recommendations" in self.ai_report_source

    def test_ai_report_v2_stub_exists(self):
        assert "Agente IA v2" in self.ai_report_source
        assert "render_tab_ai" in self.ai_report_source