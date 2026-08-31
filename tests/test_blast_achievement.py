"""Tests for core.blast_achievement — design-achievement score (Gap 5)."""
import pytest

from core.compliance_status import STATUS_CUMPLE, STATUS_FUERA


class TestAchievementWeights:
    def test_weights_sum_to_one(self):
        from core.blast_achievement import W_BERM, W_CREST, W_TOE

        assert W_CREST == pytest.approx(0.4)
        assert W_TOE == pytest.approx(0.3)
        assert W_BERM == pytest.approx(0.3)
        assert (W_CREST + W_TOE + W_BERM) == pytest.approx(1.0)


class TestComputeDesignAchievementScore:
    def _row(self, section: str, delta_crest: float, delta_toe: float, berm_status: str) -> dict:
        return {
            "section": section,
            "delta_crest": delta_crest,
            "delta_toe": delta_toe,
            "berm_status": berm_status,
        }

    def test_all_cumple_returns_100(self):
        from core.blast_achievement import compute_design_achievement_score

        comps = [
            self._row("S1", 0.5, 0.3, STATUS_CUMPLE),
            self._row("S1", 0.4, 0.2, STATUS_CUMPLE),
            self._row("S2", 1.0, 0.5, STATUS_CUMPLE),
            self._row("S2", 0.2, 0.1, STATUS_CUMPLE),
        ]
        res = compute_design_achievement_score(comps, crest_tolerance_m=1.5, toe_tolerance_m=1.5)
        assert res["global"] == 100
        assert res["breakdown"]["crest"] == 100
        assert res["breakdown"]["toe"] == 100
        assert res["breakdown"]["berm"] == 100
        assert res["n_passing_crest"] == 4
        assert res["per_malla"] is None

    def test_fuera_partial_credit_0_5(self):
        from core.blast_achievement import compute_design_achievement_score

        comps = []
        for _ in range(5):
            comps.append(self._row("S1", 0.5, 0.3, STATUS_CUMPLE))
        for _ in range(5):
            comps.append(self._row("S2", 0.5, 5.0, "NO CUMPLE"))

        res = compute_design_achievement_score(comps, crest_tolerance_m=1.5, toe_tolerance_m=1.5)
        assert res["global"] == pytest.approx(70, abs=1)
        assert res["breakdown"]["crest"] == 100
        assert res["breakdown"]["toe"] == 50
        assert res["breakdown"]["berm"] == 50
        assert res["n_passing_crest"] == 10
        assert res["n_passing_toe"] == 5
        assert res["n_passing_berm"] == 5

    def test_fuera_status_gives_half_credit(self):
        from core.blast_achievement import compute_design_achievement_score

        comps = [
            self._row("S1", 2.0, 0.3, STATUS_CUMPLE),
        ]
        res_cumple = compute_design_achievement_score(
            [self._row("S1", 0.5, 0.3, STATUS_CUMPLE)],
            crest_tolerance_m=1.5, toe_tolerance_m=1.5,
        )
        res_fuera = compute_design_achievement_score(
            [self._row("S1", 2.0, 0.3, STATUS_CUMPLE)],
            crest_tolerance_m=1.5, toe_tolerance_m=1.5,
        )
        res_no = compute_design_achievement_score(
            [self._row("S1", 5.0, 0.3, STATUS_CUMPLE)],
            crest_tolerance_m=1.5, toe_tolerance_m=1.5,
        )
        assert res_cumple["global"] == 100
        assert res_fuera["global"] == 80
        assert res_no["global"] == 60

    def test_per_malla_breakdown(self):
        from core.blast_achievement import compute_design_achievement_score

        comps = [
            self._row("S_A1", 0.5, 0.3, STATUS_CUMPLE),
            self._row("S_A2", 0.4, 0.2, STATUS_CUMPLE),
            self._row("S_B1", 2.0, 0.3, STATUS_CUMPLE),
            self._row("S_B2", 2.5, 0.2, STATUS_CUMPLE),
        ]
        malla_map = {
            "A": ["S_A1", "S_A2"],
            "B": ["S_B1", "S_B2"],
        }
        res = compute_design_achievement_score(
            comps, malla_to_section=malla_map,
            crest_tolerance_m=1.5, toe_tolerance_m=1.5,
        )
        assert res["per_malla"] is not None
        assert res["per_malla"]["A"] == 100
        assert res["per_malla"]["B"] == pytest.approx(70, abs=1)

    def test_missing_malla_returns_none(self):
        from core.blast_achievement import compute_design_achievement_score

        comps = [
            self._row("S1", 0.5, 0.3, STATUS_CUMPLE),
        ]
        res = compute_design_achievement_score(comps)
        assert res["per_malla"] is None
        assert res["global"] == 100

    def test_empty_returns_zero(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score([])
        assert res["global"] == 0
        assert res["n_total"] == 0
        assert res["per_malla"] is None

    def test_none_comparisons_returns_zero(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score(None)
        assert res["global"] == 0
        assert res["n_total"] == 0


# ---------------------------------------------------------------------------
# Signed (per-side) crest/toe tolerances
# ---------------------------------------------------------------------------


class TestSignedToleranceClassification:
    """Core classification: delta<0 uses tol_neg, delta>=0 uses tol_pos."""

    def _row(self, delta_crest, delta_toe, berm_status=STATUS_CUMPLE, section="S1"):
        return {
            "section": section,
            "delta_crest": delta_crest,
            "delta_toe": delta_toe,
            "berm_status": berm_status,
        }

    def test_default_symmetric_signed(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score(
            [self._row(-1.0, 1.0), self._row(-1.2, 1.2)]
        )
        # -1.0/+1.0 CUMPLE (credit 1.0); -1.2/+1.2 FUERA (credit 0.5)
        # row2 = 0.4*0.5 + 0.3*0.5 + 0.3*1.0 = 0.65; mean = 0.825 -> 82 (round-half-even)
        assert res["global"] == 82
        assert res["n_passing_crest"] == 1
        assert res["n_passing_toe"] == 1

    def test_default_beyond_1_5x_no_credit(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score(
            [self._row(-1.6, 1.6)]
        )
        # ±1.6 > 1.5 -> NO CUMPLE both sides; berm still CUMPLE -> 0.3 -> 30
        assert res["global"] == 30
        assert res["n_passing_crest"] == 0
        assert res["n_passing_toe"] == 0

    def test_asymmetric_tolerance(self):
        from core.blast_achievement import compute_design_achievement_score

        # neg=1.5, pos=0.8 per contract:
        # -1.2 CUMPLE; +0.9 FUERA; +0.8 CUMPLE; -1.6 FUERA; -2.3 NO CUMPLE
        crest_deltas = [-1.2, 0.9, 0.8, -1.6, -2.3]
        comps = [self._row(d, 0.0) for d in crest_deltas]
        res = compute_design_achievement_score(
            comps,
            crest_tolerance_neg_m=1.5,
            crest_tolerance_pos_m=0.8,
            toe_tolerance_neg_m=1.0,
            toe_tolerance_pos_m=1.0,
        )
        assert res["n_passing_crest"] == 2  # -1.2 and +0.8
        assert res["n_passing_toe"] == 5  # all 0.0 within symmetric 1.0

    def test_legacy_scalar_equivalent_to_signed_kwargs(self):
        from core.blast_achievement import compute_design_achievement_score

        rows = [self._row(-1.2, 1.2), self._row(0.9, -0.9), self._row(-1.6, 1.6)]
        res_scalar = compute_design_achievement_score(
            [dict(r) for r in rows], crest_tolerance_m=1.0, toe_tolerance_m=1.0
        )
        res_signed = compute_design_achievement_score(
            [dict(r) for r in rows],
            crest_tolerance_neg_m=1.0,
            crest_tolerance_pos_m=1.0,
            toe_tolerance_neg_m=1.0,
            toe_tolerance_pos_m=1.0,
        )
        assert res_scalar["global"] == res_signed["global"]
        assert res_scalar["n_passing_crest"] == res_signed["n_passing_crest"]
        assert res_scalar["n_passing_toe"] == res_signed["n_passing_toe"]

    def test_legacy_scalar_symmetric_by_side(self):
        from core.blast_achievement import compute_design_achievement_score

        # scalar 1.5 -> -1.2 CUMPLE, +1.5 CUMPLE (inclusive)
        res = compute_design_achievement_score(
            [self._row(-1.2, 1.5)], crest_tolerance_m=1.5, toe_tolerance_m=1.5
        )
        assert res["n_passing_crest"] == 1
        assert res["n_passing_toe"] == 1

    def test_precedence_signed_over_scalar(self):
        from core.blast_achievement import compute_design_achievement_score

        # signed kwarg wins over legacy scalar for that side
        res = compute_design_achievement_score(
            [self._row(-1.2, 0.0)],
            crest_tolerance_m=1.0,
            crest_tolerance_neg_m=1.5,
        )
        assert res["n_passing_crest"] == 1

    def test_precedence_scalar_over_config_default(self):
        from core.blast_achievement import compute_design_achievement_score

        # scalar 0.5: -0.8 FUERA (<=0.75? no, 0.8 > 0.75 -> NO CUMPLE)
        res = compute_design_achievement_score(
            [self._row(-0.8, 0.0)], crest_tolerance_m=0.5
        )
        assert res["n_passing_crest"] == 0
        # but with default (1.0) it would CUMPLE
        res2 = compute_design_achievement_score([self._row(-0.8, 0.0)])
        assert res2["n_passing_crest"] == 1

    def test_single_signed_kwarg_other_side_falls_back(self):
        from core.blast_achievement import compute_design_achievement_score

        # only crest_tolerance_neg_m=1.5 -> crest pos side falls back to config 1.0
        res = compute_design_achievement_score(
            [self._row(-1.2, 0.0)], crest_tolerance_neg_m=1.5
        )
        assert res["n_passing_crest"] == 1
        # and toe unaffected (default symmetric 1.0)
        assert res["n_passing_toe"] == 1

    def test_invalid_tolerance_negative_raises(self):
        from core.blast_achievement import compute_design_achievement_score

        with pytest.raises(ValueError):
            compute_design_achievement_score(
                [self._row(0.0, 0.0)], crest_tolerance_neg_m=-1.0
            )

    def test_invalid_tolerance_nan_raises(self):
        from core.blast_achievement import compute_design_achievement_score

        with pytest.raises(ValueError):
            compute_design_achievement_score(
                [self._row(0.0, 0.0)], toe_tolerance_pos_m=float("nan")
            )

    def test_invalid_tolerance_inf_raises(self):
        from core.blast_achievement import compute_design_achievement_score

        with pytest.raises(ValueError):
            compute_design_achievement_score(
                [self._row(0.0, 0.0)], crest_tolerance_pos_m=float("inf")
            )

    def test_zero_tolerance_semantics(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score(
            [self._row(0.0, 0.0), self._row(0.01, -0.01)],
            crest_tolerance_neg_m=0.0,
            crest_tolerance_pos_m=0.0,
            toe_tolerance_neg_m=0.0,
            toe_tolerance_pos_m=0.0,
        )
        assert res["n_passing_crest"] == 1
        assert res["n_passing_toe"] == 1

    def test_none_nan_string_no_crash_zero_credit(self):
        from core.blast_achievement import compute_design_achievement_score

        comps = [
            self._row(None, None),
            self._row(float("nan"), float("nan")),
            self._row("abc", None),
        ]
        res = compute_design_achievement_score(comps)
        assert res["n_total"] == 3
        # crest/toe sin crédito; berm CUMPLE en las 3 filas -> 30
        assert res["global"] == 30
        assert res["n_passing_crest"] == 0
        assert res["n_passing_toe"] == 0

    def test_tolerances_key_returned(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score([self._row(0.5, 0.5)])
        assert res["tolerances"] == {
            "crest": {"neg": 1.0, "pos": 1.0},
            "toe": {"neg": 1.0, "pos": 1.0},
        }

    def test_tolerances_key_reflects_resolution(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score(
            [self._row(0.5, 0.5)],
            crest_tolerance_m=1.2,
            toe_tolerance_neg_m=0.7,
        )
        assert res["tolerances"]["crest"] == {"neg": 1.2, "pos": 1.2}
        assert res["tolerances"]["toe"] == {"neg": 0.7, "pos": 1.0}

    def test_empty_input_returns_tolerances_structure(self):
        from core.blast_achievement import compute_design_achievement_score

        res = compute_design_achievement_score([])
        assert res["tolerances"] == {
            "crest": {"neg": 1.0, "pos": 1.0},
            "toe": {"neg": 1.0, "pos": 1.0},
        }

    def test_per_malla_uses_signed_limits(self):
        from core.blast_achievement import compute_design_achievement_score

        comps = [
            self._row(-1.2, -1.2, section="S1"),
            self._row(-1.6, -1.6, section="S2"),
        ]
        m2s = {"A": ["S1"], "B": ["S2"]}
        res = compute_design_achievement_score(
            comps,
            malla_to_section=m2s,
            crest_tolerance_neg_m=1.5,
            crest_tolerance_pos_m=1.5,
            toe_tolerance_neg_m=1.5,
            toe_tolerance_pos_m=1.5,
        )
        assert res["per_malla"]["A"] == 100  # deuda CUMPLE both sides
        assert res["per_malla"]["B"] == 65  # FUERA both sides: (0.5*0.4 + 0.5*0.3 + 1.0*0.3)

    def test_weights_and_formula_unchanged(self):
        from core.blast_achievement import W_BERM, W_CREST, W_TOE

        assert W_CREST == 0.4
        assert W_TOE == 0.3
        assert W_BERM == 0.3

    def test_invalid_tolerance_bool_true_raises(self):
        from core.blast_achievement import compute_design_achievement_score

        with pytest.raises(ValueError):
            compute_design_achievement_score(
                [self._row(0.0, 0.0)], crest_tolerance_neg_m=True
            )

    def test_invalid_tolerance_bool_false_raises(self):
        from core.blast_achievement import compute_design_achievement_score

        with pytest.raises(ValueError):
            compute_design_achievement_score(
                [self._row(0.0, 0.0)], toe_tolerance_pos_m=False
            )


class TestClassifyAchievementDelta:
    """Public signed-side classifier (shared by core score and dashboard)."""

    def test_in_module_all(self):
        import core.blast_achievement as m

        assert "classify_achievement_delta" in m.__all__

    def test_negative_within_neg_tolerance_cumple(self):
        from core.blast_achievement import classify_achievement_delta as c

        assert c(-0.5, 1.0, 0.5) == STATUS_CUMPLE

    def test_exact_limits_inclusive(self):
        from core.blast_achievement import classify_achievement_delta as c

        assert c(-1.0, 1.0, 0.5) == STATUS_CUMPLE
        assert c(0.5, 1.0, 0.5) == STATUS_CUMPLE

    def test_beyond_pos_goes_fuera_then_no_cumple(self):
        from core.blast_achievement import classify_achievement_delta as c
        from core.compliance_status import STATUS_NO_CUMPLE

        assert c(0.7, 1.0, 0.5) == STATUS_FUERA
        assert c(0.75, 1.0, 0.5) == STATUS_FUERA
        assert c(1.0, 1.0, 0.5) == STATUS_NO_CUMPLE

    def test_fuera_limit_inclusive_at_1_5x(self):
        from core.blast_achievement import classify_achievement_delta as c
        from core.compliance_status import STATUS_NO_CUMPLE

        assert c(-1.5, 1.0, 0.5) == STATUS_FUERA
        assert c(-1.51, 1.0, 0.5) == STATUS_NO_CUMPLE

    def test_zero_is_cumple(self):
        from core.blast_achievement import classify_achievement_delta as c

        assert c(0.0, 1.0, 0.5) == STATUS_CUMPLE

    def test_missing_and_nonfinite_return_none(self):
        import math

        from core.blast_achievement import classify_achievement_delta as c

        assert c(None, 1.0, 0.5) is None
        assert c("abc", 1.0, 0.5) is None
        assert c(float("nan"), 1.0, 0.5) is None
        assert c(float("inf"), 1.0, 0.5) is None
        assert c(float("-inf"), 1.0, 0.5) is None
        assert c(math.nan, 1.0, 0.5) is None

    def test_invalid_tolerances_raise(self):
        from core.blast_achievement import classify_achievement_delta as c

        with pytest.raises(ValueError):
            c(0.5, -1.0, 0.5)
        with pytest.raises(ValueError):
            c(0.5, 1.0, float("nan"))
        with pytest.raises(ValueError):
            c(0.5, "x", 0.5)

    def test_score_uses_same_classification_no_drift(self):
        from core import blast_achievement as m

        row = {"section": "S1", "delta_crest": 0.7, "delta_toe": 0.3,
               "berm_status": STATUS_CUMPLE}
        res = m.compute_design_achievement_score(
            [row], crest_tolerance_neg_m=1.0, crest_tolerance_pos_m=0.5,
            toe_tolerance_neg_m=1.0, toe_tolerance_pos_m=0.5)
        # crest FUERA -> 0.5 credit; toe CUMPLE; berm CUMPLE
        assert res["global"] == int(round((0.4 * 0.5 + 0.3 + 0.3) * 100))
