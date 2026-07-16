"""Tests for pure helpers in ``ui.tabs.blast_correlation``.

These tests exercise the DataFrame/dict compute helpers without a Streamlit
runtime, confirming the refactor separated pure logic from UI calls.
"""

import numpy as np
import pandas as pd
import pytest

from ui.tabs.blast_correlation import (
    backbreak,
    blocks,
    data,
    energy,
    multivariate,
    powder_factor,
    temporal,
)


@pytest.fixture
def blast_df_with_kg() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Pozo": ["P01", "P02"],
            "Kilos_Cargados_real": [100.0, 200.0],
            "Z_collar": [150.0, 152.0],
        }
    )


@pytest.fixture
def empty_blast_df() -> pd.DataFrame:
    return pd.DataFrame()


class TestDataHelpers:
    def test_get_kg_col_prefers_real_column(self, blast_df_with_kg):
        assert data.get_kg_col(blast_df_with_kg) == "Kilos_Cargados_real"

    def test_get_kg_col_returns_none_when_missing(self):
        df = pd.DataFrame({"Pozo": ["P01"]})
        assert data.get_kg_col(df) is None

    def test_get_malla_col_finds_known_columns(self):
        df = pd.DataFrame({"Nombre_Malla_Original": ["M1"]})
        assert data.get_malla_col(df) == "Nombre_Malla_Original"

    def test_compute_bench_correlation_empty_comps(self, blast_df_with_kg):
        result = data.compute_bench_correlation(
            [], blast_df_with_kg, pd.DataFrame(), 15.0, "Kilos_Cargados_real"
        )
        assert result.empty

    def test_compute_bench_correlation_aggregates_level(self, blast_df_with_kg):
        df_comps = pd.DataFrame(
            {
                "section": ["S01"],
                "level": [150.0],
                "delta_crest": [0.8],
                "delta_toe": [-0.3],
            }
        )
        result = data.compute_bench_correlation(
            [], blast_df_with_kg, df_comps, 15.0, "Kilos_Cargados_real"
        )
        assert not result.empty
        assert result.iloc[0]["level"] == 150.0
        assert result.iloc[0]["avg_dev_crest_over"] == pytest.approx(0.8)
        assert result.iloc[0]["avg_dev_toe_under"] == pytest.approx(-0.3)

    def test_compute_malla_correlation_no_malla_col(self, blast_df_with_kg):
        df_out, score = data.compute_malla_correlation(
            [], blast_df_with_kg, pd.DataFrame(), 15.0, "Kilos_Cargados_real", None, []
        )
        assert df_out.empty
        assert score == 0

    def test_compute_malla_correlation_missing_column(self, blast_df_with_kg):
        df_out, score = data.compute_malla_correlation(
            [], blast_df_with_kg, pd.DataFrame(), 15.0, "Kilos_Cargados_real", "Missing", []
        )
        assert df_out.empty
        assert score == 0


class TestPowderFactorHelpers:
    def test_fit_pf_damage_model_pf_unavailable(self):
        df = pd.DataFrame({"pf_vol_avg_kgm3": [0.5], "avg_over_break": [0.2]})
        result = powder_factor.fit_pf_damage_model(df, use_pf_axis=False)
        assert result["model"] is None
        assert result["error"] == "pf_unavailable"

    def test_fit_pf_damage_model_insufficient_rows(self):
        df = pd.DataFrame(
            {
                "pf_vol_avg_kgm3": [0.5, 0.6, 0.7],
                "avg_over_break": [0.1, 0.2, 0.3],
                "section": ["S01", "S02", "S03"],
            }
        )
        result = powder_factor.fit_pf_damage_model(df, use_pf_axis=True)
        assert result["model"] is None
        assert result["error"] == "insufficient"

    def test_fit_pf_damage_model_fits_with_enough_rows(self):
        rng = np.random.default_rng(42)
        n = 10
        pf = rng.uniform(0.3, 0.9, n)
        dmg = 0.1 * pf + rng.normal(0, 0.01, n)
        df = pd.DataFrame(
            {
                "pf_vol_avg_kgm3": pf,
                "avg_over_break": dmg,
                "section": [f"S{i:02d}" for i in range(n)],
            }
        )
        result = powder_factor.fit_pf_damage_model(df, use_pf_axis=True)
        assert result["model"] is not None
        assert result["error"] is None
        assert result["fig"] is not None

    def test_predict_pf_damage_returns_prediction(self):
        model = {"beta0": 0.0, "beta1": 0.5}
        pred = powder_factor.predict_pf_damage(model, target_pf=0.5)
        assert "predicted_damage" in pred

    def test_build_pf_recommendations_insufficient_model(self):
        model = {"confidence": "INSUFFICIENT", "n": 3, "p_value": 0.5}
        result = powder_factor.build_pf_recommendations(
            model, pd.DataFrame(), pd.DataFrame(), 0.3
        )
        assert result["error"] == "insufficient"

    def test_build_pf_recommendations_no_valid_data(self):
        model = {"confidence": "HIGH"}
        result = powder_factor.build_pf_recommendations(
            model, pd.DataFrame(), pd.DataFrame(), 0.3
        )
        assert result["error"] == "no_valid_data"


class TestMultivariateHelpers:
    def test_build_multivariate_model_insufficient(self):
        df = pd.DataFrame({"pf_vol_avg_kgm3": [0.5], "avg_over_break": [0.2]})
        result = multivariate.build_multivariate_model(df)
        assert result["error"] == "insufficient"
        assert result["coef_rows"].empty


class TestBackbreakHelpers:
    def test_compute_backbreak_prediction_uses_multivariate_when_valid(self):
        class FakePred:
            predicted_m = 1.0
            ci_low_m = 0.8
            ci_high_m = 1.2
            method = "multivariate"
            confidence = "HIGH"
            notes = []

        original = backbreak.predict_backbreak
        try:
            calls = []

            def fake_predict(*args, model=None, rock_factor=1.0):
                calls.append((model, rock_factor))
                return FakePred()

            backbreak.predict_backbreak = fake_predict
            pred = backbreak.compute_backbreak_prediction(
                5.0, 6.0, 0.5, 3.0, 250, 1.0, {"confidence": "HIGH"}
            )
            assert pred is not None
            assert calls[0][0] is not None
        finally:
            backbreak.predict_backbreak = original

    def test_compute_backbreak_prediction_ignores_low_confidence_model(self):
        class FakePred:
            predicted_m = 1.0
            ci_low_m = 0.8
            ci_high_m = 1.2
            method = "heuristic"
            confidence = "MEDIUM"
            notes = []

        original = backbreak.predict_backbreak
        try:
            calls = []

            def fake_predict(*args, model=None, rock_factor=1.0):
                calls.append((model, rock_factor))
                return FakePred()

            backbreak.predict_backbreak = fake_predict
            pred = backbreak.compute_backbreak_prediction(
                5.0, 6.0, 0.5, 3.0, 250, 1.0, {"confidence": "INSUFFICIENT"}
            )
            assert pred is not None
            assert calls[0][0] is None
        finally:
            backbreak.predict_backbreak = original


class TestBlocksHelpers:
    def test_build_pasadura_toe_table_empty_when_few_benches(self):
        table = blocks.build_pasadura_toe_table({"n_benches": 1})
        assert table.empty

    def test_build_stemming_crest_table_empty_when_few_benches(self):
        table = blocks.build_stemming_crest_table({"n_benches": 0})
        assert table.empty

    def test_build_pasadura_toe_table_sorts_descending(self):
        corr = {
            "n_benches": 2,
            "pasadura_per_bench": {150.0: 1.0, 148.0: 1.5},
            "toe_per_bench": {150.0: 0.2, 148.0: 0.3},
        }
        table = blocks.build_pasadura_toe_table(corr)
        assert len(table) == 2
        assert table.iloc[0]["Nivel (cota)"] == 150.0


class TestEnergyHelpers:
    def test_get_search_radius_returns_positive(self):
        assert energy.get_search_radius() > 0


class TestTemporalHelpers:
    def test_build_monthly_trend_data_empty_df(self, empty_blast_df):
        trend_df, outliers = temporal.build_monthly_trend_data(empty_blast_df)
        assert trend_df.empty
        assert outliers.empty

    def test_split_campaign_data_empty_df(self, empty_blast_df):
        cohort = temporal.split_campaign_data(empty_blast_df, "2024-01-01")
        assert cohort["has_campaign"] is False
        assert cohort["before"].empty
        assert cohort["after"].empty

    def test_build_temporal_figure_with_two_rows(self):
        trend_df = pd.DataFrame(
            {
                "mes": ["2024-01", "2024-02"],
                "pf_promedio": [0.5, 0.6],
                "damage_promedio": [0.1, 0.2],
            }
        )
        fig = temporal.build_temporal_figure(trend_df)
        assert fig is not None
        assert len(fig.data) == 2
