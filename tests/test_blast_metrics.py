"""Tests for core.blast_metrics — derived Drill & Blast ratios and indices.

Covers stemming ratio, sub-drilling ratio, S/B ratio, kg/m, decoupling
ratio, collar deviation, Kuznetsov X50, ISPU and the
`enrich_blast_dataframe` aggregator.
"""
import math

import numpy as np
import pandas as pd
import pytest

from core.blast_correlation import compute_powder_factor
from core.calculo_tronadura import procesar_pozos
from core.blast_metrics import (
    ROCK_DENSITY_DEFAULT_TM3,
    SPACING_BURDEN_RATIO_OPTIMAL,
    STEMMING_RATIO_OPTIMAL,
    SUBDRILLING_RATIO_OPTIMAL,
    compute_collar_deviation,
    compute_decoupling_ratio,
    compute_ispu,
    compute_kg_per_meter,
    compute_kuznetsov_x50,
    compute_spacing_burden_ratio,
    compute_stemming_ratio,
    compute_subdrilling_ratio,
    enrich_blast_dataframe,
)


def _proc_row(**overrides):
    """One-row post-processed DataFrame (X, Y, Z_collar, Z_toe, etc.)."""
    base = {
        "X": 0.0, "Y": 0.0, "Z_collar": 4215.0, "Z_toe": 4200.0,
        "Incl": 0.0, "Az": 0.0, "Len": 15.0,
        "Burden": 5.0, "Esp": 6.0,
        "Diam_mm": 200.0,
        "Taco_m": 4.0,
        "Kilos_Cargados_real": 300.0,
        "Tipo_Explosivo": "ANFO",
        "energy_mj": 300.0 * 3.72,
    }
    base.update(overrides)
    return pd.DataFrame([base])


def _enax_row(**overrides):
    """One-row ENAEX-format DataFrame accepted by `procesar_pozos`."""
    base = {
        "Latitud_Geo": 0.0, "Longitud_Geo": 0.0, "Nombre_Banco": 4200.0,
        "Inclinacion_real": 0.0, "Azimuth_real": 0.0, "longitud_real": 15.0,
        "Kilos_Cargados_real": 300.0,
        "Burden": 5.0, "Esp": 6.0, "Diam_mm": 200.0, "Taco_m": 4.0,
        "Tipo_Explosivo": "ANFO", "fecha_tronadura": "2026-05-01",
    }
    base.update(overrides)
    return pd.DataFrame([base])


class TestStemmingRatio:
    def test_basic(self):
        df = _proc_row(Taco_m=4.0, Burden=5.0)
        out = compute_stemming_ratio(df)
        assert out.iloc[0] == pytest.approx(0.8)

    def test_missing_burden(self):
        df = _proc_row().drop(columns=["Burden"])
        out = compute_stemming_ratio(df)
        assert pd.isna(out.iloc[0])

    def test_missing_taco(self):
        df = _proc_row().drop(columns=["Taco_m"])
        out = compute_stemming_ratio(df)
        assert pd.isna(out.iloc[0])

    def test_optimal_range_constant(self):
        assert STEMMING_RATIO_OPTIMAL == (0.7, 1.0)


class TestSubdrillingRatio:
    def test_basic(self):
        df = _proc_row(Z_collar=4215.0, Z_toe=4200.0, Burden=5.0)
        out = compute_subdrilling_ratio(df, bench_height=15.0)
        assert out.iloc[0] == pytest.approx(0.0)

    def test_with_pasadura(self):
        df = _proc_row(Z_collar=4215.0, Z_toe=4199.0, Burden=5.0)
        out = compute_subdrilling_ratio(df, bench_height=15.0)
        # pasadura = 4215 - 15 - 4199 = 1.0; 1.0/5 = 0.2
        assert out.iloc[0] == pytest.approx(0.2)

    def test_zero_burden_returns_nan(self):
        df = _proc_row(Burden=0.0)
        out = compute_subdrilling_ratio(df)
        assert pd.isna(out.iloc[0])

    def test_missing_columns_returns_nan(self):
        df = _proc_row().drop(columns=["Z_collar", "Z_toe"])
        out = compute_subdrilling_ratio(df)
        assert pd.isna(out).all()


class TestSpacingBurdenRatio:
    def test_basic(self):
        df = _proc_row(Burden=5.0, Esp=6.0)
        out = compute_spacing_burden_ratio(df)
        assert out.iloc[0] == pytest.approx(1.2)

    def test_optimal_range_constant(self):
        assert SPACING_BURDEN_RATIO_OPTIMAL == (1.0, 1.5)
        assert SUBDRILLING_RATIO_OPTIMAL == (0.2, 0.4)


class TestKgPerMeter:
    def test_basic(self):
        df = _proc_row(Kilos_Cargados_real=300.0, Len=15.0)
        out = compute_kg_per_meter(df)
        assert out.iloc[0] == pytest.approx(20.0)

    def test_zero_length_returns_nan(self):
        df = _proc_row(Len=0.0)
        out = compute_kg_per_meter(df)
        assert pd.isna(out.iloc[0])


class TestDecouplingRatio:
    def test_basic_anfo_default(self):
        df = _proc_row(Diam_mm=200.0, Len=15.0, Kilos_Cargados_real=300.0, Tipo_Explosivo="ANFO")
        out = compute_decoupling_ratio(df)
        kg_per_m = 300.0 / 15.0
        hole_area = (math.pi / 4.0) * (0.2 ** 2)
        rho_e_kgm3 = 0.80 * 1000.0
        expected_vl = kg_per_m / (hole_area * rho_e_kgm3)
        assert out["volume_load_kgm3"].iloc[0] == pytest.approx(expected_vl, rel=1e-3)
        assert out["coupling_ratio"].iloc[0] == pytest.approx(
            expected_vl / (ROCK_DENSITY_DEFAULT_TM3 * 1000.0), rel=1e-3
        )

    def test_with_heavy_anfo(self):
        df = _proc_row(Diam_mm=250.0, Len=10.0, Kilos_Cargados_real=400.0, Tipo_Explosivo="Heavy ANFO")
        out = compute_decoupling_ratio(df)
        kg_per_m = 400.0 / 10.0
        hole_area = (math.pi / 4.0) * (0.25 ** 2)
        rho_e_kgm3 = 1.05 * 1000.0
        expected_vl = kg_per_m / (hole_area * rho_e_kgm3)
        assert out["volume_load_kgm3"].iloc[0] == pytest.approx(expected_vl, rel=1e-3)

    def test_missing_diameter(self):
        df = _proc_row().drop(columns=["Diam_mm"])
        out = compute_decoupling_ratio(df)
        assert pd.isna(out["volume_load_kgm3"]).all()
        assert pd.isna(out["coupling_ratio"]).all()

    def test_default_rock_density_constant(self):
        assert ROCK_DENSITY_DEFAULT_TM3 == 2.7


class TestCollarDeviation:
    def test_perfect_alignment(self):
        df = _proc_row(Az=90.0, Incl=10.0, Az_Diseno=90.0, Incl_Diseno=10.0)
        out = compute_collar_deviation(df)
        assert out.iloc[0] == pytest.approx(0.0, abs=1e-6)

    def test_known_angle(self):
        df = _proc_row(Az=0.0, Incl=0.0, Az_Diseno=0.0, Incl_Diseno=10.0)
        out = compute_collar_deviation(df)
        assert out.iloc[0] == pytest.approx(10.0, abs=1e-6)

    def test_known_angle_inclined(self):
        df = _proc_row(Az=0.0, Incl=10.0, Az_Diseno=180.0, Incl_Diseno=10.0)
        out = compute_collar_deviation(df)
        assert out.iloc[0] == pytest.approx(20.0, abs=1e-6)

    def test_missing_design_columns(self):
        df = _proc_row()
        out = compute_collar_deviation(df)
        assert pd.isna(out).all()

    def test_does_not_raise_when_minimal(self):
        df = pd.DataFrame({"X": [0.0, 1.0]})
        out = compute_collar_deviation(df)
        assert len(out) == 2
        assert pd.isna(out).all()


class TestKuznetsovX50:
    def test_basic(self):
        # Use larger V to push X50 comfortably into the typical 10-50 cm range.
        df = _proc_row(Burden=8.0, Esp=10.0, Kilos_Cargados_real=300.0, Tipo_Explosivo="ANFO")
        out = compute_kuznetsov_x50(df)
        V, Q = 8.0 * 10.0 * 15.0, 300.0
        E = 3.72 * 1000.0 / 4.184
        expected = 11.0 * (V / Q) ** 0.8 * Q ** (1.0 / 6.0) * (E / 115.0) ** (-0.633)
        assert out.iloc[0] == pytest.approx(expected, rel=1e-3)

    def test_in_range(self):
        """Typical X50 for medium-rock D&B should fall in 10-50 cm range."""
        df = _proc_row(Burden=8.0, Esp=10.0, Kilos_Cargados_real=300.0, Tipo_Explosivo="ANFO")
        out = compute_kuznetsov_x50(df)
        val = out.iloc[0]
        assert 10.0 <= val <= 50.0, f"X50={val} cm outside typical 10-50 cm range"

    def test_missing_burden(self):
        df = _proc_row().drop(columns=["Burden"])
        out = compute_kuznetsov_x50(df)
        assert pd.isna(out).all()

    def test_missing_kilos(self):
        df = _proc_row().drop(columns=["Kilos_Cargados_real"])
        out = compute_kuznetsov_x50(df)
        assert pd.isna(out).all()

    def test_explicit_energy(self):
        df = _proc_row(Burden=8.0, Esp=10.0, Kilos_Cargados_real=300.0)
        energy = pd.Series([3.72], index=df.index)
        out = compute_kuznetsov_x50(df, explosive_energy_mj_kg=energy)
        assert pd.notna(out.iloc[0])

    def test_rock_factor(self):
        df = _proc_row(Burden=8.0, Esp=10.0, Kilos_Cargados_real=300.0, Tipo_Explosivo="ANFO")
        a = compute_kuznetsov_x50(df, rock_factor=10.0).iloc[0]
        b = compute_kuznetsov_x50(df, rock_factor=12.0).iloc[0]
        assert b > a  # higher A -> larger X50


class TestISPU:
    def test_with_scalar_ucs(self):
        df = _proc_row(Burden=5.0, Esp=6.0, Kilos_Cargados_real=300.0, Tipo_Explosivo="ANFO")
        out = compute_ispu(df, ucs_mpa=100.0)
        # V = 5*6*15 = 450 m^3; rho=2.7; UCS=100; E=300*3.72=1116 MJ
        expected = (450.0 * 2.7 * 100.0) / (300.0 * 3.72)
        assert out.iloc[0] == pytest.approx(expected, rel=1e-3)

    def test_with_series_ucs(self):
        df = _proc_row(Burden=5.0, Esp=6.0, Kilos_Cargados_real=300.0, Tipo_Explosivo="ANFO")
        df = pd.concat([df, df.copy()], ignore_index=True)
        ucs = pd.Series([50.0, 200.0], index=df.index)
        out = compute_ispu(df, ucs_mpa=ucs)
        assert out.iloc[0] < out.iloc[1]  # higher UCS -> higher ISPU

    def test_missing_ucs(self):
        df = _proc_row()
        out_none = compute_ispu(df, ucs_mpa=None)
        assert pd.isna(out_none).all()
        out_nan = compute_ispu(df, ucs_mpa=float("nan"))
        assert pd.isna(out_nan).all()

    def test_missing_energy(self):
        df = _proc_row().drop(columns=["energy_mj"])
        out = compute_ispu(df, ucs_mpa=100.0)
        assert pd.isna(out).all()


class TestEnrichBlastDataframe:
    def test_adds_all_columns_when_all_inputs_present(self):
        df = _proc_row(
            Carga_Fondo_kg=80.0, Carga_Columna_kg=220.0,
            Az_Diseno=0.0, Incl_Diseno=0.0,
        )
        out = enrich_blast_dataframe(df, ucs_mpa=100.0)
        expected_cols = {
            "stemming_ratio", "subdrilling_ratio", "spacing_burden_ratio",
            "kg_per_meter", "volume_load_kgm3", "coupling_ratio",
            "collar_deviation_deg", "kuznetsov_x50_cm", "ispu",
            "bottom_column_ratio",
        }
        assert expected_cols.issubset(set(out.columns))

    def test_passes_through_unknown_columns(self):
        df = _proc_row()
        df["custom_col"] = [42.0]
        out = enrich_blast_dataframe(df)
        assert "custom_col" in out.columns
        assert out["custom_col"].iloc[0] == 42.0

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["Burden", "Esp"])
        out = enrich_blast_dataframe(df)
        assert out.empty

    def test_does_not_mutate_input(self):
        df = _proc_row()
        original_cols = set(df.columns)
        enrich_blast_dataframe(df)
        assert set(df.columns) == original_cols

    def test_partial_inputs_skip_silently(self):
        # No Taco_m -> no stemming_ratio; no Diam_mm -> no decoupling;
        # no design cols -> no collar_deviation_deg.
        df = _proc_row().drop(columns=["Taco_m", "Diam_mm"])
        out = enrich_blast_dataframe(df)
        assert "stemming_ratio" not in out.columns
        assert "volume_load_kgm3" not in out.columns
        assert "collar_deviation_deg" not in out.columns
        assert "spacing_burden_ratio" in out.columns

    def test_no_ucs_omits_ispu(self):
        df = _proc_row()
        out = enrich_blast_dataframe(df, ucs_mpa=None)
        assert "ispu" not in out.columns

    def test_wired_into_compute_powder_factor(self):
        """compute_powder_factor now also emits the new ratio columns."""
        df = _proc_row(Burden=5.0, Esp=6.0, Taco_m=4.0, Kilos_Cargados_real=300.0)
        out = compute_powder_factor(df)
        assert "stemming_ratio" in out.columns
        assert "spacing_burden_ratio" in out.columns
        assert "kg_per_meter" in out.columns
        assert "kuznetsov_x50_cm" in out.columns


class TestCalculoTronaduraNewColumns:
    def test_loads_new_columns(self):
        df = _enax_row(
            Secuencia=3,
            Retardo_ms=25.0,
            Numero_Fila=2,
            Carga_Fondo_kg=80.0,
            Carga_Columna_kg=220.0,
            Longitud_Carga_m=11.0,
            Tipo_Pozo="produccion",
            Azimuth_Diseno=0.0,
            Inclinacion_Diseno=0.0,
        )
        out, *_ = procesar_pozos(df)
        for col in (
            "Secuencia", "Retardo_ms", "Fila", "Carga_Fondo_kg",
            "Carga_Columna_kg", "Longitud_Carga_m", "Tipo_Pozo",
            "Az_Diseno", "Incl_Diseno",
        ):
            assert col in out.columns, f"{col} should be loaded"

    def test_handles_missing_new_columns(self):
        df = _enax_row()
        out, *_ = procesar_pozos(df)
        for col in (
            "Secuencia", "Retardo_ms", "Fila", "Carga_Fondo_kg",
            "Carga_Columna_kg", "Longitud_Carga_m", "Tipo_Pozo",
            "Az_Diseno", "Incl_Diseno",
        ):
            assert col not in out.columns, f"{col} should be absent when not provided"

    def test_alternative_names_picked_up(self):
        df = _enax_row(
            Secuencia_Iniciacion=7,
            Delay_ms=42.0,
            Fila_Pozo=1,
            Kilos_Fondo=60.0,
            Kilos_Columna=240.0,
            Charge_Length=12.0,
            Hole_Type="buffer",
            Design_Azimuth=5.0,
            Design_Dip=3.0,
        )
        out, *_ = procesar_pozos(df)
        assert int(out["Secuencia"].iloc[0]) == 7
        assert out["Retardo_ms"].iloc[0] == pytest.approx(42.0)
        assert int(out["Fila"].iloc[0]) == 1
        assert out["Carga_Fondo_kg"].iloc[0] == pytest.approx(60.0)
        assert out["Carga_Columna_kg"].iloc[0] == pytest.approx(240.0)
        assert out["Longitud_Carga_m"].iloc[0] == pytest.approx(12.0)
        assert out["Tipo_Pozo"].iloc[0] == "buffer"
        assert out["Az_Diseno"].iloc[0] == pytest.approx(5.0)
        assert out["Incl_Diseno"].iloc[0] == pytest.approx(3.0)

    def test_secuencia_is_integer_dtype(self):
        df = _enax_row(Secuencia=3)
        out, *_ = procesar_pozos(df)
        assert pd.api.types.is_integer_dtype(out["Secuencia"])
        assert int(out["Secuencia"].iloc[0]) == 3
