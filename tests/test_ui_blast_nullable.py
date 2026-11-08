"""Nullable blast payloads: carga, energía y logro faltantes no se vuelven 0."""
import numpy as np
import pandas as pd
import pytest

import ui.blast_analysis as ba
import ui.tabs.blast_correlation.data as bdata


class _FakeSection:
    def __init__(self, name="S1"):
        self.name = name
        self.origin = np.array([0.0, 0.0])
        self.azimuth = 0.0
        self.length = 100.0


def _projected(order):
    return pd.DataFrame({"X": np.zeros(order), "Y": np.zeros(order)})


class TestProjectoneNullableCharge:
    def test_missing_charge_is_none(self, monkeypatch):
        monkeypatch.setattr(ba, "proyectar_pozos_en_seccion",
                            lambda *a, **k: pd.DataFrame({"Kilos": [np.nan, np.nan]}))
        monkeypatch.setattr(ba, "aggregate_powder_factor_by_group",
                            lambda *a, **k: {"energy_total_mj": None})
        row = ba._project_one(
            pd.DataFrame({"Kilos": [np.nan]}), pd.DataFrame({"Kilos": [np.nan]}),
            origin=np.array([0.0, 0.0]), azimuth=0.0, length=100.0,
            kg_col="Kilos", tolerance=10.0, fecha_corte=None,
            label_col="section_name", label_value="S1",
        )
        assert row["num_pozos"] == 2
        assert row["total_kg"] is None
        assert row["energy_total_mj"] is None

    def test_finite_charge_sums_and_keeps_zero(self, monkeypatch):
        monkeypatch.setattr(ba, "proyectar_pozos_en_seccion",
                            lambda *a, **k: pd.DataFrame({"Kilos": [100.0, np.nan, 50.0]}))
        monkeypatch.setattr(ba, "aggregate_powder_factor_by_group",
                            lambda *a, **k: {"energy_total_mj": 12.5})
        row = ba._project_one(
            pd.DataFrame({"Kilos": [100.0]}), pd.DataFrame({"Kilos": [100.0]}),
            origin=np.array([0.0, 0.0]), azimuth=0.0, length=100.0,
            kg_col="Kilos", tolerance=10.0, fecha_corte=None,
            label_col="section_name", label_value="S1",
        )
        assert row["total_kg"] == pytest.approx(150.0)
        assert row["energy_total_mj"] == pytest.approx(12.5)

    def test_zero_charge_stays_zero(self, monkeypatch):
        monkeypatch.setattr(ba, "proyectar_pozos_en_seccion",
                            lambda *a, **k: pd.DataFrame({"Kilos": [0.0, 0.0]}))
        monkeypatch.setattr(ba, "aggregate_powder_factor_by_group",
                            lambda *a, **k: {"energy_total_mj": 0.0})
        row = ba._project_one(
            pd.DataFrame({"Kilos": [0.0]}), pd.DataFrame({"Kilos": [0.0]}),
            origin=np.array([0.0, 0.0]), azimuth=0.0, length=100.0,
            kg_col="Kilos", tolerance=10.0, fecha_corte=None,
            label_col="section_name", label_value="S1",
        )
        assert row["total_kg"] == 0.0
        assert row["energy_total_mj"] == 0.0


class TestScatterNullablePoints:
    def _df(self):
        return pd.DataFrame({
            "Sección": ["S1", "S2", "S3", "S4"],
            "Kg": [100.0, np.nan, 300.0, 400.0],
            "Sobre-excavación_Media_m": [0.5, 0.4, np.nan, 0.6],
            "Deuda/Relleno_Media_m": [0.0, 0.0, 0.0, np.nan],
        })

    def test_missing_points_excluded_and_counted(self):
        fig = ba.build_pf_deviation_scatter(
            self._df(), x_col="Kg", x_label="kg", radius_m=10.0)
        plotted = sum(len(trace.x) for trace in fig.data)
        assert plotted == 2
        texts = " ".join(str(a.text) for a in fig.layout.annotations)
        assert "Excluidos 2 de 4 puntos sin dato" in texts

    def test_no_annotation_when_all_points_plotted(self):
        df = pd.DataFrame({
            "Sección": ["S1", "S2"],
            "Kg": [100.0, 200.0],
            "Sobre-excavación_Media_m": [0.5, 0.6],
            "Deuda/Relleno_Media_m": [0.0, 0.0],
        })
        fig = ba.build_pf_deviation_scatter(df, x_col="Kg", x_label="kg", radius_m=10.0)
        texts = " ".join(str(a.text) for a in fig.layout.annotations)
        assert "Excluidos" not in texts

    def test_ols_uses_only_finite_points(self):
        fig = ba.build_pf_deviation_scatter(
            self._df(), x_col="Kg", x_label="kg", radius_m=10.0, show_ols=True)
        trend = [t for t in fig.data if t.mode == "lines"]
        assert len(trend) == 1
        assert all(np.isfinite(np.asarray(trend[0].x, dtype=float)))


class TestMallaAchievementNullable:
    def _blast_df(self):
        return pd.DataFrame({
            "Nombre_Malla_Original": ["M1", "M2"],
            "Kilos_Cargados_real": [100.0, 120.0],
        })

    def _patch_projection(self, monkeypatch, comparisons_row):
        monkeypatch.setattr(bdata, "proyectar_pozos_en_seccion",
                            lambda *a, **k: pd.DataFrame({"X": [0.0], "Y": [0.0]}))
        monkeypatch.setattr(
            bdata, "aggregate_powder_factor_by_group",
            lambda *a, **k: {"pf_vol_avg": None, "energy_total_mj": None, "n_pf_valid": 0},
        )

    def test_no_comparisons_keeps_achievement_null(self):
        df_out, score = bdata.compute_malla_correlation(
            [], self._blast_df(), pd.DataFrame({"section": []}), 15.0,
            "Kilos_Cargados_real", "Nombre_Malla_Original", [],
        )
        assert not df_out.empty
        assert score is None
        assert df_out["score_pct"].tolist() == [None, None]

    def test_malla_without_evaluable_rows_is_none(self, monkeypatch):
        self._patch_projection(monkeypatch, None)
        df_out, score = bdata.compute_malla_correlation(
            [_FakeSection()], self._blast_df(), pd.DataFrame({"section": []}), 15.0,
            "Kilos_Cargados_real", "Nombre_Malla_Original",
            [{"section": "S1", "delta_crest": None, "delta_toe": None,
              "berm_status": None}],
        )
        assert df_out["score_pct"].tolist() == [None, None]

    def test_evaluable_malla_keeps_score(self, monkeypatch):
        self._patch_projection(monkeypatch, None)
        df_out, score = bdata.compute_malla_correlation(
            [_FakeSection()], self._blast_df(), pd.DataFrame({"section": []}), 15.0,
            "Kilos_Cargados_real", "Nombre_Malla_Original",
            [{"section": "S1", "delta_crest": 0.2, "delta_toe": 0.2,
              "berm_status": "CUMPLE"}],
        )
        assert score == 100
        assert df_out["score_pct"].tolist() == [100, 100]
