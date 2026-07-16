"""Tests for the additive multivariate blast-damage model and burden advisor."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.blast_advisor import (
    recommend_burden_adjustment,
    recommend_multivariate,
    recommend_pf_adjustment,
)
from core.blast_model import (
    fit_multivariate_damage_model,
    fit_powder_factor_damage_model,
)
from core.compliance_status import (
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INSUFFICIENT,
)

TRUE_BETAS = {"pf_vol": 1.2, "burden": -0.5, "spacing_burden_ratio": 0.1, "stemming": -0.2}
INTERCEPT = 0.3


def _synth(n=40, seed=0, noise=0.05, positive_pf=False):
    rng = np.random.default_rng(seed)
    center = 0.35 if positive_pf else 0.0
    pf = rng.normal(center, 0.05 if positive_pf else 1.0, n)
    burden = rng.normal(5.0 if positive_pf else 0.0, 0.5 if positive_pf else 1.0, n)
    sb = rng.normal(0.0, 1.0, n)
    stemming = rng.normal(0.0, 1.0, n)
    y = (
        INTERCEPT
        + TRUE_BETAS["pf_vol"] * pf
        + TRUE_BETAS["burden"] * burden
        + TRUE_BETAS["spacing_burden_ratio"] * sb
        + TRUE_BETAS["stemming"] * stemming
        + rng.normal(0.0, noise, n)
    )
    return pd.DataFrame({
        "pf_vol_kgm3": pf,
        "Burden": burden,
        "spacing_burden_ratio": sb,
        "Taco_m": stemming,
        "avg_over_break": y,
    })


@pytest.fixture
def strong_model():
    return fit_multivariate_damage_model(_synth(n=40, seed=1))


@pytest.mark.parametrize("feature", list(TRUE_BETAS))
def test_truth_recovery(strong_model, feature):
    est = strong_model["coefficients"][feature]
    se = strong_model["std_errors"][feature]
    assert abs(est - TRUE_BETAS[feature]) < 2.0 * se


def test_r_squared_lift_vs_mono():
    df = _synth(n=40, seed=2, positive_pf=True)
    multi = fit_multivariate_damage_model(df)
    mono = fit_powder_factor_damage_model(
        df["pf_vol_kgm3"].to_numpy(), df["avg_over_break"].to_numpy()
    )
    assert multi["r_squared"] >= mono["r_squared"] + 0.05


@pytest.mark.parametrize("n,expected", [(8, {"INSUFFICIENT"}), (12, {"MEDIUM", "HIGH"})])
def test_sample_size_gate(n, expected):
    model = fit_multivariate_damage_model(_synth(n=n, seed=3))
    assert model["confidence"] in expected


def test_collinearity_downgrades_confidence():
    rng = np.random.default_rng(4)
    n = 40
    burden = rng.uniform(4.0, 6.0, n)
    pf = 1.0 / burden
    sb = rng.normal(1.2, 0.1, n)
    stemming = rng.normal(3.0, 0.3, n)
    y = INTERCEPT + 1.2 * pf - 0.5 * burden + 0.1 * sb - 0.2 * stemming + rng.normal(0, 0.05, n)
    df = pd.DataFrame({
        "pf_vol_kgm3": pf, "Burden": burden,
        "spacing_burden_ratio": sb, "Taco_m": stemming, "avg_over_break": y,
    })
    model = fit_multivariate_damage_model(df)
    assert model["condition_number"] >= 20.0  # standardized-predictor threshold
    assert model["confidence"] != "HIGH"
    assert model["confidence"] == "CAUTION"
    assert model["collinearity_warning"]


def test_missing_columns_insufficient():
    df = _synth(n=20, seed=5)[["pf_vol_kgm3", "avg_over_break"]]
    model = fit_multivariate_damage_model(df)
    assert model["confidence"] == "INSUFFICIENT"
    assert len(model["features_used"]) < 2


def test_constant_column_dropped():
    df = _synth(n=20, seed=6)
    df["Burden"] = 5.0
    df["spacing_burden_ratio"] = 1.2
    df["Taco_m"] = 3.0
    model = fit_multivariate_damage_model(df)
    assert model["confidence"] == "INSUFFICIENT"
    assert "burden" not in model["features_used"]


def test_missing_damage_column_no_raise():
    df = _synth(n=20, seed=7).drop(columns=["avg_over_break"])
    model = fit_multivariate_damage_model(df)
    assert model["confidence"] == "INSUFFICIENT"


def test_advisor_recovers_burden():
    df = _synth(n=30, seed=8, positive_pf=True)
    model = fit_multivariate_damage_model(df)
    cur_b = model["feature_means"]["burden"]
    means = model["feature_means"]
    target = model["beta0"] + sum(model["coefficients"][k] * means[k] for k in means)
    rec = recommend_burden_adjustment(model, current_burden=cur_b, target_overbreak_m=target)
    assert abs(rec["target_burden"] - cur_b) <= 0.05 * cur_b
    assert rec["feasibility"] in {FEASIBILITY_APPLICABLE, FEASIBILITY_CAUTION}


def test_advisor_boundary_caution():
    df = _synth(n=30, seed=9, positive_pf=True)
    model = fit_multivariate_damage_model(df)
    cur_b = model["feature_means"]["burden"]
    means = model["feature_means"]
    base = model["beta0"] + sum(
        model["coefficients"][k] * means[k] for k in means if k != "burden"
    )
    target = base + model["coefficients"]["burden"] * (2.1 * cur_b)
    rec = recommend_burden_adjustment(model, current_burden=cur_b, target_overbreak_m=target)
    assert rec["feasibility"] == FEASIBILITY_CAUTION


def test_advisor_zero_burden_coefficient_insufficient():
    model = {
        "confidence": "HIGH", "n": 20, "beta0": 0.3,
        "coefficients": {"pf_vol": 1.2, "burden": 0.0, "stemming": -0.2},
        "feature_means": {"pf_vol": 0.35, "burden": 5.0, "stemming": 3.0},
        "f_pvalue": 0.001,
    }
    rec = recommend_burden_adjustment(model, current_burden=5.0)
    assert rec["feasibility"] == FEASIBILITY_INSUFFICIENT


@pytest.mark.parametrize("n,expect_dispatch", [(15, True), (5, False)])
def test_dispatcher_routing(n, expect_dispatch):
    model = fit_multivariate_damage_model(_synth(n=max(n, 4), seed=10, positive_pf=True))
    if n < 12:
        model["n"] = n
    rec = recommend_multivariate(model, current_burden=5.0)
    if expect_dispatch:
        assert "target_burden" in rec and rec["feasibility"] != FEASIBILITY_INSUFFICIENT or rec["confidence"] != "INSUFFICIENT"
    else:
        assert rec["feasibility"] == FEASIBILITY_INSUFFICIENT
        assert rec["confidence"] == "INSUFFICIENT"


def test_legacy_pf_advisor_unchanged():
    pf = np.array([0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65])
    dmg = np.array([0.20, 0.28, 0.33, 0.41, 0.52, 0.58, 0.66, 0.71])
    model = fit_powder_factor_damage_model(pf, dmg)
    first = recommend_pf_adjustment(model, current_pf=0.45, target_overbreak_m=0.5)
    second = recommend_pf_adjustment(model, current_pf=0.45, target_overbreak_m=0.5)
    assert first == second
    assert set(first) == {
        "target_pf", "current_pf", "delta_pf", "delta_pf_pct",
        "predicted_current_damage", "predicted_target_damage",
        "feasibility", "message", "confidence",
    }
