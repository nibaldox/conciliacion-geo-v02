"""Tests for core.blast_advisor — PF adjustment recommendation engine."""
import warnings

import numpy as np
import pandas as pd
import pytest

from core.blast_advisor import (
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INSUFFICIENT,
    DIRECTION_INCREASE,
    DIRECTION_NONE,
    DIRECTION_REDUCE,
    format_recommendation_text,
    recommend_by_sector,
    recommend_charge_change_pct,
    recommend_pf_adjustment,
)
from core.config import ADVISOR


def _positive_model(n: int = 20, beta1: float = 1.4, beta0: float = -0.2) -> dict:
    """Build a model with positive slope: more PF -> more damage."""
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


class TestBlastAdvisor:
    def test_recommend_pf_reduce(self):
        model = _positive_model()
        target = ADVISOR.target_overbreak_m
        rec = recommend_pf_adjustment(model, current_pf=0.55, target_overbreak_m=target)
        assert rec["feasibility"] == FEASIBILITY_APPLICABLE
        assert rec["current_pf"] == pytest.approx(0.55)
        assert rec["target_pf"] < 0.55
        assert rec["delta_pf"] < 0
        assert rec["delta_pf_pct"] < 0
        assert rec["predicted_target_damage"] == pytest.approx(target)
        assert rec["predicted_current_damage"] > target
        assert rec["confidence"] == "HIGH"

    def test_recommend_pf_increase(self):
        model = _positive_model()
        target = ADVISOR.target_overbreak_m
        rec = recommend_pf_adjustment(model, current_pf=0.41, target_overbreak_m=target)
        assert rec["feasibility"] == FEASIBILITY_APPLICABLE
        assert rec["current_pf"] == pytest.approx(0.41)
        assert rec["target_pf"] > 0.41
        assert rec["delta_pf"] > 0
        assert rec["delta_pf_pct"] > 0
        assert rec["predicted_current_damage"] < target

    def test_recommend_pf_insufficient_data(self):
        model = _positive_model(n=2, beta1=0.0, beta0=0.0)
        model["confidence"] = "INSUFFICIENT"
        rec = recommend_pf_adjustment(model, current_pf=0.5)
        assert rec["feasibility"] == FEASIBILITY_INSUFFICIENT
        assert rec["delta_pf"] == 0.0
        assert rec["delta_pf_pct"] == 0.0
        assert "no se puede" in rec["message"].lower() or "insuficiente" in rec["message"].lower()

    def test_recommend_pf_zero_beta1(self):
        model = _positive_model(n=20, beta1=1e-12, beta0=0.0)
        rec = recommend_pf_adjustment(model, current_pf=0.5)
        assert rec["feasibility"] == FEASIBILITY_INSUFFICIENT
        assert rec["delta_pf"] == 0.0

    def test_recommend_pf_caution_large_change(self):
        model = _positive_model()
        rec = recommend_pf_adjustment(model, current_pf=1.20, target_overbreak_m=0.2)
        assert rec["feasibility"] == FEASIBILITY_CAUTION
        assert abs(rec["delta_pf_pct"]) > ADVISOR.max_recommendation_pct

    def test_recommend_pf_caution_negative_target(self):
        model = _positive_model(beta1=2.0, beta0=2.0)
        rec = recommend_pf_adjustment(model, current_pf=0.5, target_overbreak_m=-5.0)
        assert rec["feasibility"] == FEASIBILITY_CAUTION
        assert rec["target_pf"] < 0.0

    def test_recommend_charge_change_pct_basic(self):
        model = _positive_model()
        out_reduce = recommend_charge_change_pct(model, 0.55)
        assert out_reduce["direction"] == DIRECTION_REDUCE
        assert out_reduce["delta_pct"] < 0.0
        assert out_reduce["feasibility"] == FEASIBILITY_APPLICABLE

        out_inc = recommend_charge_change_pct(model, 0.41)
        assert out_inc["direction"] == DIRECTION_INCREASE
        assert out_inc["delta_pct"] > 0.0

        out_same = recommend_charge_change_pct(model, 0.5)
        assert out_same["direction"] == DIRECTION_NONE
        assert out_same["delta_pct"] == 0.0

    def test_recommend_by_sector_basic(self):
        model = _positive_model()
        df = pd.DataFrame(
            {
                "sector": ["Norte", "Norte", "Sur", "Sur", "Este", "Este", "Este"],
                "pf_vol_avg_kgm3": [0.55, 0.50, 0.41, 0.42, 0.35, 0.34, 0.36],
                "avg_over_break": [0.6, 0.5, 0.4, 0.45, 0.2, 0.18, 0.22],
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = recommend_by_sector(df, model)

        assert len(result) == 3
        assert set(result["group_value"]) == {"Norte", "Sur", "Este"}
        assert list(result.columns) == [
            "group_value",
            "n_wells",
            "current_pf",
            "current_damage_pred",
            "target_pf",
            "delta_pf",
            "delta_pf_pct",
            "feasibility",
            "message",
        ]
        norte = result.loc[result["group_value"] == "Norte"].iloc[0]
        assert norte["n_wells"] == 2
        assert norte["current_pf"] == pytest.approx(0.525)
        assert norte["feasibility"] == FEASIBILITY_APPLICABLE
        assert norte["delta_pf"] < 0

        este = result.loc[result["group_value"] == "Este"].iloc[0]
        assert este["feasibility"] == FEASIBILITY_CAUTION

    def test_recommend_by_sector_missing_col(self):
        model = _positive_model()
        df = pd.DataFrame(
            {
                "pf_vol_avg_kgm3": [0.5, 0.5],
                "avg_over_break": [0.3, 0.4],
            }
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = recommend_by_sector(df, model, group_col="sector")
        assert result.empty
        assert any("sector" in str(w.message) for w in caught)

    def test_format_recommendation_text_aplicable(self):
        model = _positive_model()
        rec = recommend_pf_adjustment(model, current_pf=0.55)
        text = format_recommendation_text(rec, section_name="Norte")
        assert "Norte" in text
        delta_str = f"{rec['delta_pf']:+.2f}"
        assert delta_str in text
        assert any(span in text.lower() for span in ("reducir", "aumentar", "mantener", "ajustar"))

    def test_format_recommendation_text_caution(self):
        rec = {
            "feasibility": FEASIBILITY_CAUTION,
            "current_pf": 0.5,
            "target_pf": 0.05,
            "delta_pf": -0.45,
            "delta_pf_pct": -90.0,
            "predicted_current_damage": 1.0,
            "predicted_target_damage": 0.5,
            "n": 10,
        }
        text = format_recommendation_text(rec, section_name="Sur").lower()
        assert "excede" in text or "revisar" in text

    def test_format_recommendation_text_insufficient(self):
        rec = {
            "feasibility": FEASIBILITY_INSUFFICIENT,
            "current_pf": 0.5,
            "target_pf": 0.5,
            "delta_pf": 0.0,
            "delta_pf_pct": 0.0,
            "predicted_current_damage": 0.0,
            "predicted_target_damage": 0.5,
            "n": 2,
        }
        text = format_recommendation_text(rec, section_name="Este").lower()
        assert "no se puede" in text or "insuficiente" in text
