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
