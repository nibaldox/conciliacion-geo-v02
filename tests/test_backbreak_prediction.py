"""Tests for :mod:`core.backbreak_prediction` (blast back-break prediction).

Covers the empirical fallback, the multivariate round-trip, Holmberg-Persson
cross-check clamping, the confidence ladder, default substitution on bad
input, rock-factor clamping and the legacy ``predict_damage_for_pf`` safety
net required by the change spec.
"""
import math
import re

import numpy as np
import pandas as pd
import pytest

from core.backbreak_prediction import (
    BackbreakPrediction,
    predict_backbreak,
    predict_backbreak_from_design,
)
from core.blast_model import (
    fit_multivariate_damage_model,
    predict_damage_for_pf,
    fit_powder_factor_damage_model,
)
from core.config import BACKBREAK, BackbreakDefaults


def _build_synthetic_multivariate_df(n: int = 60, seed: int = 1234) -> pd.DataFrame:
    """Build a low-collinearity synthetic dataframe for fit_multivariate_damage_model."""
    rng = np.random.default_rng(seed)
    pf = rng.uniform(0.20, 0.80, n)
    burden = rng.uniform(3.0, 8.0, n)
    spacing = rng.uniform(4.0, 10.0, n)
    stemming = rng.uniform(2.0, 6.0, n)
    beta0 = 0.5
    beta_pf = 1.2
    beta_b = 0.15
    beta_sb = -0.4
    beta_t = -0.05
    sb_ratio = spacing / burden
    sigma = 0.15
    noise = rng.normal(0.0, sigma, n)
    damage = (
        beta0
        + beta_pf * pf
        + beta_b * burden
        + beta_sb * sb_ratio
        + beta_t * stemming
        + noise
    )
    return pd.DataFrame(
        {
            "avg_over_break": damage,
            "pf_vol_kgm3": pf,
            "Burden": burden,
            "Espaciamiento": spacing,
            "Taco_m": stemming,
        }
    )


class TestEmpiricalFallback:
    def test_empirical_basic(self):
        result = predict_backbreak(6.0, 7.0, 0.35, 3.0, 250.0)
        assert isinstance(result, BackbreakPrediction)
        assert result.method == "empirical_fallback"
        assert result.confidence == "MEDIUM"
        assert result.predicted_m == pytest.approx(1.8, rel=0.01)
        assert result.ci_low_m == pytest.approx(result.predicted_m * 0.85, rel=1e-6)
        assert result.ci_high_m == pytest.approx(result.predicted_m * 1.15, rel=1e-6)
        assert result.ci_low_m <= result.predicted_m <= result.ci_high_m
        assert any("Holmberg-Persson" in n for n in result.notes)

    def test_empirical_monotonicity_on_grid(self):
        pf_grid = [0.10, 0.20, 0.35, 0.50, 0.70]
        burden_grid = [3.0, 5.0, 7.0, 10.0]
        predictions_pf = [
            predict_backbreak(6.0, 7.0, pf, 3.0, 250.0).predicted_m for pf in pf_grid
        ]
        predictions_b = [
            predict_backbreak(b, 7.0, 0.35, 3.0, 250.0).predicted_m for b in burden_grid
        ]
        for prev, curr in zip(predictions_pf, predictions_pf[1:]):
            assert curr >= prev, f"empirical not monotone in PF: {prev} → {curr}"
        for prev, curr in zip(predictions_b, predictions_b[1:]):
            assert curr >= prev, f"empirical not monotone in B: {prev} → {curr}"


class TestMultivariatePath:
    def test_multivariate_roundtrip_three_features(self):
        df = _build_synthetic_multivariate_df(n=80, seed=7)
        model = fit_multivariate_damage_model(df)
        assert model["confidence"] != "INSUFFICIENT"
        assert len(model.get("features_used", [])) >= 2

        pf = 0.45
        burden = 5.5
        spacing = 7.0
        stemming = 4.0
        sb_ratio = spacing / burden
        beta0 = 0.5
        beta_pf = 1.2
        beta_b = 0.15
        beta_sb = -0.4
        beta_t = -0.05
        true_signal = (
            beta0
            + beta_pf * pf
            + beta_b * burden
            + beta_sb * sb_ratio
            + beta_t * stemming
        )

        result = predict_backbreak(burden, spacing, pf, stemming, 250.0, model=model)
        assert result.method == "multivariate"
        assert result.confidence in {"HIGH", "MEDIUM"}
        se_combined = (result.ci_high_m - result.ci_low_m) / (2.0 * 1.96)
        assert se_combined > 0.0
        assert abs(result.predicted_m - true_signal) <= 2.0 * se_combined + 0.5

    def test_multivariate_ci_coverage_monte_carlo(self):
        df = _build_synthetic_multivariate_df(n=200, seed=42)
        model = fit_multivariate_damage_model(df)
        assert model["confidence"] != "INSUFFICIENT"

        rng = np.random.default_rng(99)
        pf_q = float(rng.uniform(0.25, 0.7))
        burden_q = float(rng.uniform(3.5, 7.5))
        spacing_q = float(rng.uniform(5.0, 9.0))
        stemming_q = float(rng.uniform(2.5, 5.5))
        sigma_true = 0.15

        true_signal = (
            0.5
            + 1.2 * pf_q
            + 0.15 * burden_q
            + (-0.4) * (spacing_q / burden_q)
            + (-0.05) * stemming_q
        )

        result = predict_backbreak(
            burden_q, spacing_q, pf_q, stemming_q, 250.0, model=model
        )
        assert result.method == "multivariate"
        half = (result.ci_high_m - result.ci_low_m) / 2.0

        n_draws = 200
        draws = true_signal + rng.normal(0.0, sigma_true, n_draws)
        coverage = float(np.mean((draws >= result.ci_low_m) & (draws <= result.ci_high_m)))
        assert half >= 1.5 * sigma_true, (
            f"CI half-width too narrow ({half:.3f}) for sigma={sigma_true}"
        )
        assert coverage >= 0.85, f"CI coverage {coverage:.2f} below 0.85 floor"

    def test_multivariate_insufficient_falls_back(self):
        tiny = pd.DataFrame({
            "avg_over_break": [0.1, 0.2, 0.3],
            "pf_vol_kgm3": [0.3, 0.4, 0.5],
            "Burden": [5.0, 5.0, 5.0],
        })
        model = fit_multivariate_damage_model(tiny)
        assert model["confidence"] == "INSUFFICIENT"
        result = predict_backbreak(6.0, 7.0, 0.35, 3.0, 250.0, model=model)
        assert result.method == "empirical_fallback"
        assert any("multivariate_not_available" in n for n in result.notes)


class TestHolmbergPerssonCrossCheck:
    def test_holmberg_persson_cross_check_calibrated_band(self):
        result = predict_backbreak(6.0, 7.0, 0.35, 3.0, 250.0)
        hp_notes = [n for n in result.notes if "Holmberg-Persson" in n]
        assert hp_notes, f"HP cross-check missing from notes: {result.notes}"
        hp_note = hp_notes[0]
        match = re.search(r"([0-9]+\.[0-9]+|[0-9]+)\s*m\s*\(", hp_note)
        assert match, f"Could not parse r_damage from HP note: {hp_note!r}"
        r_damage = float(match.group(1))
        low = BACKBREAK.clamp_low_factor_b * 6.0
        high = BACKBREAK.clamp_high_factor_b * 6.0
        assert low - 1e-9 <= r_damage <= high + 1e-9, (
            f"r_damage={r_damage} not in [{low}, {high}]"
        )

    def test_holmberg_persson_clamps_when_extreme(self):
        huge_burden = 10.0
        huge_pf = 10.0
        huge_spacing = 20.0
        result = predict_backbreak(
            huge_burden, huge_spacing, huge_pf, 5.0, 311.0
        )
        r_damage_raw = 0.6 * math.sqrt(
            huge_pf * huge_burden * huge_spacing * 15.0
        )
        high = BACKBREAK.clamp_high_factor_b * huge_burden
        hp_note = next(n for n in result.notes if "Holmberg-Persson" in n)
        match = re.search(r"([0-9]+\.[0-9]+|[0-9]+)\s*m\s*\(", hp_note)
        assert match
        r_in_note = float(match.group(1))
        assert r_damage_raw > high, "Test setup: r_damage_raw must exceed high clamp"
        assert math.isclose(r_in_note, high, rel_tol=1e-6), (
            f"HP value {r_in_note} should be clamped to high={high}"
        )


class TestConfidenceLadder:
    def test_none_inputs_return_insufficient(self):
        result = predict_backbreak(None, None, None, None, None)
        assert isinstance(result, BackbreakPrediction)
        assert result.method == "empirical_fallback"
        assert result.confidence == "INSUFFICIENT"
        assert result.predicted_m == 0.0
        assert result.ci_low_m == 0.0
        assert result.ci_high_m == 0.0

    def test_none_design_dict_returns_insufficient(self):
        result = predict_backbreak_from_design(None)
        assert result.confidence == "INSUFFICIENT"
        assert result.predicted_m == 0.0

    def test_nan_and_negative_parameters_substituted(self):
        result = predict_backbreak(
            float("nan"), -1.0, float("nan"), -3.0, 250.0
        )
        assert math.isfinite(result.predicted_m)
        assert math.isfinite(result.ci_low_m)
        assert math.isfinite(result.ci_high_m)
        assert result.method == "empirical_fallback"
        assert result.confidence == "LOW"
        substituted = [n for n in result.notes if n.startswith("substituted:")]
        assert "substituted:burden_m" in substituted
        assert "substituted:pf_kgm3" in substituted
        assert "substituted:stemming_m" in substituted


class TestRockFactorClamp:
    def test_rock_factor_clamped_to_bounds(self):
        result = predict_backbreak(
            6.0, 7.0, 0.35, 3.0, 250.0, rock_factor=5.0
        )
        clamp_notes = [n for n in result.notes if n.startswith("clamped:rock_factor")]
        assert clamp_notes
        assert any("5.0→1.3" in n for n in clamp_notes)
        assert math.isclose(
            result.predicted_m,
            BACKBREAK.empirical_k * 6.0 * 1.0 * BACKBREAK.rock_factor_max,
            rel_tol=1e-6,
        )

    def test_rock_factor_below_minimum_clamped(self):
        result = predict_backbreak(
            6.0, 7.0, 0.35, 3.0, 250.0, rock_factor=0.1
        )
        clamp_notes = [n for n in result.notes if n.startswith("clamped:rock_factor")]
        assert clamp_notes
        assert any("0.1→0.7" in n for n in clamp_notes)
        assert math.isclose(
            result.predicted_m,
            BACKBREAK.empirical_k * 6.0 * 1.0 * BACKBREAK.rock_factor_min,
            rel_tol=1e-6,
        )


class TestLegacySurfaceUnchanged:
    def test_legacy_predict_damage_for_pf_unchanged(self):
        pf = np.linspace(0.2, 1.0, 8)
        dmg = 0.5 * pf + 0.1
        model = fit_powder_factor_damage_model(pf, dmg)
        pred = predict_damage_for_pf(model, 1.0)
        assert set(pred.keys()) == {"predicted_damage", "delta_from_current", "uncertainty_m"}
        assert pred["predicted_damage"] == pytest.approx(0.6, abs=0.05)
        assert pred["delta_from_current"] == pred["predicted_damage"]
        assert pred["uncertainty_m"] >= 0.0

        empty = predict_damage_for_pf({"confidence": "INSUFFICIENT"}, 1.0)
        assert empty == {
            "predicted_damage": 0.0,
            "delta_from_current": 0.0,
            "uncertainty_m": 0.0,
        }

        empty_none = predict_damage_for_pf(None, 1.0)
        assert empty_none == {
            "predicted_damage": 0.0,
            "delta_from_current": 0.0,
            "uncertainty_m": 0.0,
        }


class TestConfigSurface:
    def test_backbreak_defaults_singleton(self):
        assert isinstance(BACKBREAK, BackbreakDefaults)
        assert BACKBREAK.rock_factor_min == 0.7
        assert BACKBREAK.rock_factor_max == 1.3
        assert BACKBREAK.pf_optimal_default_kgm3 == 0.35
        assert BACKBREAK.ci_band_pct == 0.15
        assert BACKBREAK.empirical_k == 0.3
        assert BACKBREAK.hp_constant == 0.6
        assert BACKBREAK.clamp_low_factor_b == 0.5
        assert BACKBREAK.clamp_high_factor_b == 4.0