"""Nullable magnitudes on the blast-correlation tab (renderers + malla/bench data).

Dato faltante = ``None`` y se muestra «sin dato»; un 0 medido se muestra 0.
Nunca se convierte un faltante en 0.
"""

import numpy as np
import pandas as pd
import pytest

from ui.tabs.blast_correlation import data, renderers


class _Ctx:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeColumn(_Ctx):
    def metric(self, label, value, **kwargs):
        self._sink.append(f"{label}: {value}")

    def multiselect(self, label, options, default=None, key=None, **kwargs):
        return []


class _FakeSt:
    def __init__(self):
        self.texts = []

    def metric(self, label, value, **kwargs):
        self.texts.append(f"{label}: {value}")

    def markdown(self, body, **kwargs):
        self.texts.append(str(body))

    def caption(self, body, **kwargs):
        self.texts.append(str(body))

    def info(self, body, **kwargs):
        self.texts.append(str(body))

    def warning(self, body, **kwargs):
        self.texts.append(str(body))

    def success(self, body, **kwargs):
        self.texts.append(str(body))

    def subheader(self, body, **kwargs):
        self.texts.append(str(body))

    def dataframe(self, body, **kwargs):
        pass

    def plotly_chart(self, fig, **kwargs):
        pass

    def slider(self, label, *args, **kwargs):
        return kwargs.get("value", 5.0)

    def checkbox(self, label, *args, **kwargs):
        return False

    def date_input(self, *args, **kwargs):
        return None

    def expander(self, label, **kwargs):
        return _Ctx(self.texts)

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeColumn(self.texts) for _ in range(count)]

    def tabs(self, labels):
        return [_Ctx(self.texts) for _ in labels]

    def dump(self):
        return "\n".join(self.texts)


class _FakeSection:
    def __init__(self, name="S1", sector="A"):
        self.name = name
        self.sector = sector
        self.origin = np.array([0.0, 0.0])
        self.azimuth = 0.0
        self.length = 100.0


def _install_fake_st(monkeypatch):
    fake = _FakeSt()
    monkeypatch.setattr(renderers, "st", fake)
    return fake


def _sections_df(total_kg, area_over, num_pozos=None, sections=("S1", "S2", "S3")):
    n = len(sections)
    return pd.DataFrame(
        {
            "section": list(sections),
            "sector": ["A"] * n,
            "num_pozos": num_pozos if num_pozos is not None else [4] * n,
            "total_kg": total_kg,
            "area_over": area_over,
            "area_under": [0.0] * n,
            "avg_over_break": [0.2] * n,
            "avg_under_break": [0.0] * n,
            "pf_vol_avg_kgm3": [np.nan] * n,
            "pf_area_avg_kgm2": [np.nan] * n,
            "energy_total_mj": [None] * n,
            "n_pf_valid": [0] * n,
            "_pf_unavailable": [True] * n,
        }
    )


def _stub_pipeline(monkeypatch, df_sections, blast_df=None):
    blast = blast_df if blast_df is not None else pd.DataFrame(
        {"Kilos_Cargados_real": [100.0], "Z_collar": [150.0]}
    )
    comparisons = [
        {"section": "S1", "level": 150.0, "delta_crest": 0.1, "delta_toe": 0.1, "sector": "A"},
        {"section": "S2", "level": 150.0, "delta_crest": -0.1, "delta_toe": 0.1, "sector": "A"},
    ]
    monkeypatch.setattr(renderers.state, "get_blast_df", lambda: blast)
    monkeypatch.setattr(renderers.state, "get_comparison_results", lambda: comparisons)
    monkeypatch.setattr(
        renderers.state, "get_sections", lambda: [_FakeSection("S1"), _FakeSection("S2")]
    )
    monkeypatch.setattr(renderers.state, "get_mesh_design", lambda: object())
    monkeypatch.setattr(renderers.state, "get_mesh_topo", lambda: object())
    monkeypatch.setattr(renderers.data, "build_section_cache_keys", lambda *a, **k: ("c", "f"))
    monkeypatch.setattr(renderers.state, "get_cached_sections_data", lambda key: df_sections)
    monkeypatch.setattr(renderers, "_ensure_filter_values", lambda: {"levels": []})
    for name in (
        "_render_section_tab",
        "_render_bench_tab",
        "_render_malla_tab",
        "_render_pf_recommendations",
        "_render_multivariate_model",
        "_render_backbreak_predictor",
        "_render_temporal_analysis",
    ):
        monkeypatch.setattr(renderers, name, lambda *a, **k: None)
    monkeypatch.setattr(
        renderers, "_render_powder_factor_damage_model", lambda *a, **k: (None, None)
    )


class TestTopMetricsNullableCharge:
    def _render(self, monkeypatch, df):
        fake = _install_fake_st(monkeypatch)
        _stub_pipeline(monkeypatch, df)
        renderers.render_tab_blast_correlation({})
        return fake.dump()

    def test_all_missing_charge_shows_sin_dato(self, monkeypatch):
        text = self._render(
            monkeypatch, _sections_df([None, None, None], [1.0, 2.0, 3.0])
        )
        assert "Carga Proyectada Total: sin dato" in text
        assert "Carga Proyectada Total: 0 Kg" not in text

    def test_all_missing_area_shows_sin_dato(self, monkeypatch):
        text = self._render(
            monkeypatch, _sections_df([100.0, 200.0, 300.0], [None, None, None])
        )
        assert "Sobre-excavación Media: sin dato" in text
        assert "m²" not in text.split("Sobre-excavación Media:")[1].splitlines()[0]

    def test_measured_zero_charge_stays_zero(self, monkeypatch):
        text = self._render(monkeypatch, _sections_df([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]))
        assert "Carga Proyectada Total: 0 Kg" in text

    def test_partial_missing_charge_sums_finite_only(self, monkeypatch):
        text = self._render(
            monkeypatch, _sections_df([100.0, None, 50.0], [1.0, 2.0, 3.0])
        )
        assert "Carga Proyectada Total: 150 Kg" in text

    def test_correlation_excludes_missing_charge_instead_of_zero(self, monkeypatch):
        text = self._render(
            monkeypatch, _sections_df([100.0, None, 300.0], [1.0, 2.0, 3.0])
        )
        assert "Fuerte Positiva (r=1.00)" in text


class TestMallaGlobalAchievementNullable:
    def _render(self, monkeypatch, score):
        fake = _install_fake_st(monkeypatch)
        df = pd.DataFrame(
            {
                "malla": ["M1"],
                "num_pozos": [4],
                "total_kg": [100.0],
                "avg_dev_crest_over": [0.1],
                "avg_dev_crest_under": [0.0],
                "avg_dev_toe_over": [0.0],
                "avg_dev_toe_under": [0.0],
                "avg_overbreak": [1.0],
                "pf_vol_avg_kgm3": [np.nan],
                "energy_total_mj": [None],
                "score_pct": [score],
            }
        )
        monkeypatch.setattr(
            renderers.data, "compute_malla_correlation", lambda *a, **k: (df, score)
        )
        renderers._render_malla_tab(
            [_FakeSection()],
            pd.DataFrame({"Kilos_Cargados_real": [100.0]}),
            pd.DataFrame({"section": ["S1"]}),
            pd.DataFrame({"section": ["S1"]}),
            15.0,
            "Kilos_Cargados_real",
            "Nombre_Malla_Original",
            [],
            None,
            [],
            {"neg": 0.5, "pos": 0.5},
        )
        return fake.dump()

    def test_missing_global_score_shows_sin_dato(self, monkeypatch):
        text = self._render(monkeypatch, None)
        assert "Logro Diseño Global: sin dato" in text
        assert "None%" not in text

    def test_measured_global_score_keeps_percent(self, monkeypatch):
        text = self._render(monkeypatch, 100)
        assert "Logro Diseño Global: 100%" in text


class TestMallaChargeNullable:
    def _blast_df(self):
        return pd.DataFrame(
            {
                "Nombre_Malla_Original": ["M1", "M2", "M3"],
                "Kilos_Cargados_real": [np.nan, 0.0, np.nan],
            }
        )

    def test_all_missing_charge_is_none(self):
        blast = pd.DataFrame(
            {"Nombre_Malla_Original": ["M1", "M2"], "Kilos_Cargados_real": [np.nan, np.nan]}
        )
        df_out, _ = data.compute_malla_correlation(
            [], blast, pd.DataFrame({"section": []}), 15.0,
            "Kilos_Cargados_real", "Nombre_Malla_Original", [],
        )
        assert df_out["total_kg"].tolist() == [None, None]

    def test_measured_zero_charge_stays_zero(self):
        blast = pd.DataFrame(
            {"Nombre_Malla_Original": ["M1", "M2"], "Kilos_Cargados_real": [0.0, 0.0]}
        )
        df_out, _ = data.compute_malla_correlation(
            [], blast, pd.DataFrame({"section": []}), 15.0,
            "Kilos_Cargados_real", "Nombre_Malla_Original", [],
        )
        assert df_out["total_kg"].tolist() == [0.0, 0.0]

    def test_partial_missing_charge_sums_finite_only(self):
        blast = pd.DataFrame(
            {
                "Nombre_Malla_Original": ["M1", "M1", "M2"],
                "Kilos_Cargados_real": [100.0, np.nan, 50.0],
            }
        )
        df_out, _ = data.compute_malla_correlation(
            [], blast, pd.DataFrame({"section": []}), 15.0,
            "Kilos_Cargados_real", "Nombre_Malla_Original", [],
        )
        assert df_out["total_kg"].tolist() == [100.0, 50.0]


class TestBenchChargeNullable:
    def test_all_missing_charge_is_none(self, monkeypatch):
        monkeypatch.setattr(
            data, "proyectar_pozos_en_seccion",
            lambda *a, **k: pd.DataFrame({"Kilos_Cargados_real": [np.nan, np.nan]}),
        )
        monkeypatch.setattr(
            data, "aggregate_powder_factor_by_group",
            lambda *a, **k: {"pf_vol_avg": None, "pf_area_avg": None, "energy_total_mj": None},
        )
        blast = pd.DataFrame(
            {"Kilos_Cargados_real": [np.nan, np.nan], "Z_collar": [150.0, 150.0]}
        )
        df_comps = pd.DataFrame(
            {"section": ["S1"], "level": [150.0], "delta_crest": [0.1], "delta_toe": [0.1]}
        )
        df_out = data.compute_bench_correlation(
            [_FakeSection()], blast, df_comps, 15.0, "Kilos_Cargados_real"
        )
        assert df_out["total_kg"].tolist() == [None]
