"""Tests for core.blast_correlation — Drill & Blast ↔ Geotechnical correlation."""
import numpy as np
import pandas as pd
import pytest

from core.blast_correlation import (
    BlastCorrelationRow,
    aggregate_powder_factor_by_group,
    classify_berm_as_ramp,
    compute_blast_geotech_correlation,
    compute_pasadura_stats,
    compute_powder_factor,
    compute_signed_deviations,
)
from core.config import EXPLOSIVE, RAMP
from core.calculo_tronadura import procesar_pozos


def _section(name, x, y, az, length=100.0):
    """Build a SectionLine-like object."""
    return type(
        "Sec",
        (),
        {"name": name, "origin": np.array([x, y]), "azimuth": az, "length": length, "sector": ""},
    )()


def _valid_hole(lat, lon, banco=4000.0, kg=200.0):
    return pd.DataFrame(
        [
            {
                "label_pozo": f"P-{lat:.0f}-{lon:.0f}",
                "Latitud_Geo": lat,
                "Longitud_Geo": lon,
                "Nombre_Banco": banco,
                "Inclinacion_real": 0.0,
                "Azimuth_real": 0.0,
                "longitud_real": 10.0,
                "Kilos_Cargados_real": kg,
                "fecha_tronadura": "2026-05-01",
            }
        ]
    )


class TestComputePasaduraStats:
    def test_empty_dataframe(self):
        s = compute_pasadura_stats(pd.DataFrame())
        assert s == {"total": 0, "mean": 0.0, "optimal_count": 0, "optimal_pct": 0.0}

    def test_none_input(self):
        s = compute_pasadura_stats(None)
        assert s["total"] == 0

    def test_optimal_pasadura_counted(self):
        # pasadura = (Z_collar - 15) - Z_toe. With Z_collar=4200, the formula
        # gives 4185 - Z_toe. For each row pick Z_toe such that the resulting
        # pasadura is 0.5, 1.5, 0.7, 5.0 respectively.
        df = pd.DataFrame(
            {
                "Z_collar": [4200.0, 4200.0, 4200.0, 4200.0],
                "Z_toe": [4184.5, 4183.5, 4184.3, 4180.0],  # → 0.5, 1.5, 0.7, 5.0
            }
        )
        s = compute_pasadura_stats(df)
        assert s["total"] == 4
        assert s["optimal_count"] == 3  # first three are within [0.5, 1.5]
        assert s["optimal_pct"] == pytest.approx(75.0, abs=0.1)


class TestComputeBlastGeotechCorrelation:
    def test_returns_one_row_per_section(self):
        # One hole at (0,0). Two sections: S1 passes through the hole, S2 is
        # 100 m away (beyond the 15 m default tolerance).
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        sections = [_section("S1", 0.0, 0.0, 90.0), _section("S2", 100.0, 0.0, 90.0)]
        comps = [
            {"section": "S1", "delta_crest": 0.3},
            {"section": "S2", "delta_crest": 0.5},
        ]
        rows = compute_blast_geotech_correlation(df, sections, comps)
        assert len(rows) == 2
        assert {r.section_name for r in rows} == {"S1", "S2"}
        s1, s2 = sorted(rows, key=lambda r: r.section_name)
        assert isinstance(s1, BlastCorrelationRow)
        assert s1.num_wells == 1   # hole is on S1
        assert s2.num_wells == 0   # hole is 100 m from S2 (>15 m tolerance)

    def test_no_sections_returns_empty(self):
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        assert compute_blast_geotech_correlation(df, [], []) == []
        assert compute_blast_geotech_correlation(None, [], []) == []
        assert compute_blast_geotech_correlation(pd.DataFrame(), [], []) == []

    def test_comparisons_without_deviation_column_still_work(self):
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        sections = [_section("S1", 0.0, 0.0, 90.0)]
        comps = [{"section": "S1", "height_status": "CUMPLE"}]  # no delta_crest
        rows = compute_blast_geotech_correlation(df, sections, comps)
        assert len(rows) == 1
        assert rows[0].mean_abs_deviation == 0.0


class TestComputeSignedDeviations:
    """Over- vs under-excavation split (sign convention: +over / -under)."""

    def test_splits_positive_and_negative(self):
        comps = [
            {"section": "S1", "delta_crest": 0.6},
            {"section": "S1", "delta_crest": 1.2},
            {"section": "S1", "delta_crest": -0.8},
            {"section": "S1", "delta_crest": None},
            {"section": "S2", "delta_crest": 5.0},
        ]
        r = compute_signed_deviations(comps, "S1")
        assert r["n_over"] == 2
        assert r["n_under"] == 1
        assert r["avg_over"] == pytest.approx(0.9)
        assert r["avg_under"] == pytest.approx(-0.8)

    def test_empty_or_missing_section(self):
        assert compute_signed_deviations([], "S1") == {
            "avg_over": 0.0, "avg_under": 0.0, "n_over": 0, "n_under": 0,
        }
        assert compute_signed_deviations([{"section": "X", "delta_crest": 1.0}], "S1")["n_over"] == 0

    def test_falls_back_to_delta_toe(self):
        r = compute_signed_deviations(
            [{"section": "S1", "delta_toe": -0.5}], "S1"
        )
        assert r["n_under"] == 1 and r["avg_under"] == pytest.approx(-0.5)


class TestBlastCorrelationRowBackwardsCompat:
    def test_as_tuple_returns_four_elements(self):
        """as_tuple must stay a 4-tuple: report_generator/excel_writer unpack it."""
        row = BlastCorrelationRow(
            "S1", 3, 1000.0, 0.5,
            avg_over_break=0.7, avg_under_break=-0.4, n_over=2, n_under=1,
        )
        sec_name, num_wells, total_kg, avg_dev = row.as_tuple()
        assert (sec_name, num_wells, total_kg, avg_dev) == ("S1", 3, 1000.0, 0.5)

    def test_as_signed_tuple_carries_new_fields(self):
        row = BlastCorrelationRow(
            "S1", 3, 1000.0, 0.5,
            avg_over_break=0.7, avg_under_break=-0.4, n_over=2, n_under=1,
            pf_vol_avg_kgm3=0.45, pf_area_avg_kgm2=2.1,
            pf_g_per_ton_avg=120.0, energy_total_mj=400.0, n_pf_valid=3,
            pf_g_per_ton_net_avg=130.0,
        )
        signed = row.as_signed_tuple()
        assert len(signed) == 14
        assert signed[4] == 0.7 and signed[5] == -0.4
        assert signed[6] == 2 and signed[7] == 1
        assert signed[8] == 0.45
        assert signed[9] == 2.1
        assert signed[10] == 120.0
        assert signed[11] == 130.0  # pf_g_per_ton_net_avg
        assert signed[12] == 400.0
        assert signed[13] == 3

    def test_new_fields_default_to_zero(self):
        row = BlastCorrelationRow("S1", 0, 0.0, 0.0)
        assert row.avg_over_break == 0.0
        assert row.avg_under_break == 0.0
        assert row.n_over == 0 and row.n_under == 0

    def test_correlation_rows_carry_signed_fields(self):
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        sections = [_section("S1", 0.0, 0.0, 90.0)]
        comps = [
            {"section": "S1", "delta_crest": 0.8},
            {"section": "S1", "delta_crest": -0.3},
        ]
        rows = compute_blast_geotech_correlation(df, sections, comps)
        assert rows[0].num_wells == 1
        assert rows[0].avg_over_break == pytest.approx(0.8)
        assert rows[0].avg_under_break == pytest.approx(-0.3)
        assert rows[0].n_over == 1 and rows[0].n_under == 1


class TestClassifyBermAsRamp:
    def test_within_ramp_range(self):
        assert classify_berm_as_ramp(RAMP.min_width) is True
        assert classify_berm_as_ramp((RAMP.min_width + RAMP.max_width) / 2) is True
        assert classify_berm_as_ramp(RAMP.max_width) is True

    def test_outside_ramp_range(self):
        assert classify_berm_as_ramp(0.0) is False
        assert classify_berm_as_ramp(RAMP.min_width - 1) is False
        assert classify_berm_as_ramp(RAMP.max_width + 1) is False


class TestExplosiveEnergy:
    def test_known_types(self):
        assert EXPLOSIVE.energy_mj_per_kg("ANFO") == pytest.approx(3.72)
        assert EXPLOSIVE.energy_mj_per_kg("anfo") == pytest.approx(3.72)
        assert EXPLOSIVE.energy_mj_per_kg("Heavy ANFO") == pytest.approx(3.40)
        assert EXPLOSIVE.energy_mj_per_kg("H-ANFO") == pytest.approx(3.40)
        assert EXPLOSIVE.energy_mj_per_kg("Emulsion") == pytest.approx(3.05)
        assert EXPLOSIVE.energy_mj_per_kg("Bulk Emulsion") == pytest.approx(3.05)
        assert EXPLOSIVE.energy_mj_per_kg("Emuline 8000") == pytest.approx(3.05)

    def test_unknown_type_falls_back_to_anfo(self):
        assert EXPLOSIVE.energy_mj_per_kg("mystery") == pytest.approx(3.72)
        assert EXPLOSIVE.energy_mj_per_kg("") == pytest.approx(3.72)
        assert EXPLOSIVE.energy_mj_per_kg(None) == pytest.approx(3.72)

    def test_density_lookup(self):
        assert EXPLOSIVE.density_g_per_cm3("ANFO") == pytest.approx(0.80)
        assert EXPLOSIVE.density_g_per_cm3("Heavy ANFO") == pytest.approx(1.05)
        assert EXPLOSIVE.density_g_per_cm3("Bulk Emulsion") == pytest.approx(1.15)


def _holes_grid_with_pattern(burden=5.0, esp=6.0, kg=300.0,
                             n=9, explosive="ANFO", malla="M1"):
    """Build a 3×3 grid of blast holes at (0,0), (0,B), (0,2B), (S,0)... with B=burden, S=esp."""
    rows = []
    for ix in range(3):
        for iy in range(3):
            rows.append({
                "label_pozo": f"P-{ix}-{iy}",
                "Latitud_Geo": float(ix * burden),
                "Longitud_Geo": float(iy * esp),
                "Nombre_Banco": 4200.0,
                "Inclinacion_real": 0.0,
                "Azimuth_real": 0.0,
                "longitud_real": 12.0,
                "Kilos_Cargados_real": kg,
                "Burden": burden,
                "Esp": esp,
                "Tipo_Explosivo": explosive,
                "Nombre_Malla_Original": malla,
                "fecha_tronadura": "2026-05-01",
            })
    return pd.DataFrame(rows[:n])


class TestComputePowderFactor:
    def test_basic_burden_esp_columns(self):
        """Burden=5, Esp=6, Kilos=300, bench=15 → pf_vol = 300 / (5×6×15) = 0.6667."""
        df = _holes_grid_with_pattern(burden=5.0, esp=6.0, kg=300.0)
        out = compute_powder_factor(df)
        assert "pf_vol_kgm3" in out.columns
        assert "pf_area_kgm2" in out.columns
        assert "energy_mj" in out.columns
        assert out["pf_vol_kgm3"].iloc[0] == pytest.approx(0.6667, abs=1e-3)
        assert out["pf_area_kgm2"].iloc[0] == pytest.approx(10.0, abs=1e-6)
        assert out["energy_mj"].iloc[0] == pytest.approx(300.0 * 3.72, abs=1e-3)
        assert out["burden_est_m"].iloc[0] == pytest.approx(5.0)
        assert out["esp_est_m"].iloc[0] == pytest.approx(6.0)

    def test_knn_estimation_when_missing(self):
        """Without Burden/Esp, k-NN estimates median nearest-neighbour spacing."""
        df = _holes_grid_with_pattern(burden=4.0, esp=4.0, kg=200.0)
        df = df.drop(columns=["Burden", "Esp"])
        processed = procesar_pozos(df)[0]
        out = compute_powder_factor(processed)
        assert out["pf_vol_kgm3"].iloc[0] > 0
        assert out["burden_est_m"].iloc[0] == pytest.approx(4.0, abs=1.5)
        assert out["esp_est_m"].iloc[0] == pytest.approx(4.0, abs=1.5)

    def test_energy_mj_with_explosive_type(self):
        """energy_mj per kilo: ANFO 3.72 MJ/kg, Heavy ANFO 3.40, Emulsion 3.05."""
        df_anfo = _holes_grid_with_pattern(kg=100.0, explosive="ANFO")
        df_heavy = _holes_grid_with_pattern(kg=100.0, explosive="Heavy ANFO")
        df_emul = _holes_grid_with_pattern(kg=100.0, explosive="Bulk Emulsion")
        assert compute_powder_factor(df_anfo)["energy_mj"].iloc[0] == pytest.approx(372.0, abs=1e-3)
        assert compute_powder_factor(df_heavy)["energy_mj"].iloc[0] == pytest.approx(340.0, abs=1e-3)
        assert compute_powder_factor(df_emul)["energy_mj"].iloc[0] == pytest.approx(305.0, abs=1e-3)

    def test_returns_nan_gracefully(self):
        """With only 1 row and no group column, B/S estimation is impossible → NaN."""
        df = pd.DataFrame(
            [{
                "label_pozo": "solo",
                "Latitud_Geo": 0.0,
                "Longitud_Geo": 0.0,
                "Nombre_Banco": 4200.0,
                "Inclinacion_real": 0.0,
                "Azimuth_real": 0.0,
                "longitud_real": 12.0,
                "Kilos_Cargados_real": 100.0,
                "fecha_tronadura": "2026-05-01",
            }]
        )
        out = compute_powder_factor(df)
        assert pd.isna(out["pf_vol_kgm3"].iloc[0])
        assert pd.isna(out["burden_est_m"].iloc[0])

    def test_none_input_returns_empty(self):
        assert compute_powder_factor(None) is None

    def test_empty_input(self):
        df = pd.DataFrame(columns=["X", "Y", "Kilos_Cargados_real"])
        out = compute_powder_factor(df)
        assert out.empty


class TestAggregatePowderFactorByGroup:
    def test_group_by_section(self):
        """PF and energy aggregate by section via projected_pozos."""
        df = _holes_grid_with_pattern(burden=5.0, esp=6.0, kg=300.0, malla="M1")
        processed = procesar_pozos(df)[0]
        out = compute_powder_factor(processed)
        sec_origin = np.array([0.0, 0.0])
        from core.calculo_tronadura import proyectar_pozos_en_seccion
        proj = proyectar_pozos_en_seccion(
            processed, origin=sec_origin, azimuth=90.0, length=200.0, tolerance=50.0,
        )
        proj_labeled = proj.copy()
        proj_labeled["section_name"] = "S1"
        agg = aggregate_powder_factor_by_group(out, "section_name", "S1", proj_labeled)
        assert agg["n_wells"] == len(proj_labeled)
        assert agg["n_pf_valid"] > 0
        assert agg["pf_vol_avg"] == pytest.approx(0.6667, abs=1e-3)
        assert agg["energy_total_mj"] > 0
        assert agg["kg_total"] > 0

    def test_empty_inputs(self):
        agg = aggregate_powder_factor_by_group(
            pd.DataFrame(), "section_name", "S1", pd.DataFrame(),
        )
        assert agg["n_wells"] == 0
        assert pd.isna(agg["pf_vol_avg"])


class TestBlastCorrelationRowPF:
    def test_pf_fields_default_to_zero(self):
        row = BlastCorrelationRow("S1", 0, 0.0, 0.0)
        assert row.pf_vol_avg_kgm3 == 0.0
        assert row.pf_area_avg_kgm2 == 0.0
        assert row.energy_total_mj == 0.0
        assert row.n_pf_valid == 0

    def test_as_signed_tuple_includes_pf(self):
        row = BlastCorrelationRow(
            "S1", 5, 1500.0, 0.8,
            pf_vol_avg_kgm3=0.42, pf_area_avg_kgm2=2.5,
            pf_g_per_ton_avg=110.0, energy_total_mj=900.0, n_pf_valid=5,
            pf_g_per_ton_net_avg=115.0,
        )
        signed = row.as_signed_tuple()
        assert len(signed) == 14
        assert signed[8] == 0.42
        assert signed[9] == 2.5
        assert signed[10] == 110.0
        assert signed[11] == 115.0  # pf_g_per_ton_net_avg
        assert signed[12] == 900.0
        assert signed[13] == 5

    def test_correlation_function_populates_pf(self):
        """compute_blast_geotech_correlation should fill PF fields when data allows."""
        df = procesar_pozos(_holes_grid_with_pattern())[0]
        sections = [_section("S1", 0.0, 0.0, 90.0)]
        rows = compute_blast_geotech_correlation(df, sections, [])
        assert len(rows) == 1
        assert rows[0].pf_vol_avg_kgm3 > 0
        assert rows[0].energy_total_mj > 0
        assert rows[0].n_pf_valid > 0


class TestBlastModel:
    """Tests for core.blast_model — quantitative PF/damage and pasadura models."""

    def test_fit_powder_factor_damage_model_basic(self):
        from core.blast_model import fit_powder_factor_damage_model

        rng = np.random.default_rng(42)
        pf = np.linspace(0.2, 1.2, 10)
        dmg = 0.5 * pf + 0.05 + rng.normal(0, 0.02, size=10)

        model = fit_powder_factor_damage_model(pf, dmg)
        assert model["n"] == 10
        assert model["beta1"] == pytest.approx(0.5, abs=0.05)
        assert model["is_significant"] is True
        assert model["p_value"] < 0.05
        assert model["r_squared"] > 0.9
        assert model["confidence"] in ("HIGH", "MEDIUM")
        assert model["ci_beta1_low"] < model["beta1"] < model["ci_beta1_high"]
        assert model["std_err_beta1"] > 0
        assert model["mean_pf"] == pytest.approx(float(pf.mean()))

    def test_fit_powder_factor_damage_model_insufficient(self):
        from core.blast_model import fit_powder_factor_damage_model

        model = fit_powder_factor_damage_model(
            np.array([0.3, 0.5, 0.7]), np.array([0.1, 0.2, 0.3]),
        )
        assert model["confidence"] == "INSUFFICIENT"
        assert model["is_significant"] is False
        assert model["n"] == 3
        assert model["beta1"] == 0.0
        assert model["r_squared"] == 0.0

    def test_fit_powder_factor_damage_model_nan_handling(self):
        from core.blast_model import fit_powder_factor_damage_model

        pf = np.array([0.2, np.nan, 0.4, 0.5, 0.6, 0.7])
        dmg = np.array([0.1, 0.2, np.nan, 0.4, 0.5, 0.6])
        model = fit_powder_factor_damage_model(pf, dmg)
        assert model["n"] == 4
        assert np.isfinite(model["beta1"])

    def test_fit_powder_factor_damage_model_zero_variance_pf(self):
        from core.blast_model import fit_powder_factor_damage_model

        pf = np.array([0.5] * 10)
        dmg = np.linspace(0.1, 1.0, 10)
        model = fit_powder_factor_damage_model(pf, dmg)
        assert model["confidence"] == "INSUFFICIENT"
        assert model["n"] == 10

    def test_predict_damage_for_pf_basic(self):
        from core.blast_model import (
            fit_powder_factor_damage_model, predict_damage_for_pf,
        )

        pf = np.linspace(0.2, 1.0, 8)
        dmg = 0.5 * pf + 0.1
        model = fit_powder_factor_damage_model(pf, dmg)
        pred = predict_damage_for_pf(model, 1.0)
        assert pred["predicted_damage"] == pytest.approx(0.6, abs=0.05)
        assert pred["delta_from_current"] == pred["predicted_damage"]
        assert pred["uncertainty_m"] >= 0

    def test_predict_damage_for_pf_insufficient_returns_zero(self):
        from core.blast_model import predict_damage_for_pf

        pred = predict_damage_for_pf({"confidence": "INSUFFICIENT"}, 1.0)
        assert pred == {"predicted_damage": 0.0, "delta_from_current": 0.0, "uncertainty_m": 0.0}

    def test_compute_pasadura_toe_correlation_basic(self):
        from core.blast_model import compute_pasadura_toe_correlation

        df = pd.DataFrame({
            "X": [0.0, 0.0, 10.0, 10.0],
            "Y": [0.0, 0.0, 0.0, 0.0],
            "Z_collar": [4215.0, 4215.0, 4230.0, 4230.0],
            "Z_toe": [4198.0, 4198.0, 4210.0, 4210.0],
        })
        comps = [
            {"level": "4200", "delta_toe": 0.1},
            {"level": "4215", "delta_toe": -0.5},
        ]
        res = compute_pasadura_toe_correlation(df, comps, bench_height=15.0)
        assert res["n_benches"] == 2
        assert res["r"] == pytest.approx(-1.0, abs=1e-6)
        assert 4215.0 in res["pasadura_per_bench"]
        assert 4215.0 in res["toe_per_bench"]

    def test_compute_pasadura_toe_correlation_no_data(self):
        from core.blast_model import compute_pasadura_toe_correlation

        res = compute_pasadura_toe_correlation(pd.DataFrame(), [])
        assert res["r"] == 0.0
        assert res["n_benches"] == 0
        assert "interpretacion" in res["interpretation"].lower() or "datos" in res["interpretation"].lower()

    def test_compute_pasadura_toe_correlation_only_one_bench(self):
        from core.blast_model import compute_pasadura_toe_correlation

        df = pd.DataFrame({
            "X": [0.0, 0.0],
            "Y": [0.0, 0.0],
            "Z_collar": [4215.0, 4215.0],
            "Z_toe": [4198.0, 4198.0],
        })
        comps = [{"level": "4200", "delta_toe": 0.5}]
        res = compute_pasadura_toe_correlation(df, comps, bench_height=15.0)
        assert res["n_benches"] == 1
        assert res["r"] == 0.0
        assert "2" in res["interpretation"] or "dos" in res["interpretation"].lower()

    def test_compute_pasadura_toe_correlation_missing_columns(self):
        from core.blast_model import compute_pasadura_toe_correlation

        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        comps = [{"level": "4200", "delta_toe": 0.1}]
        res = compute_pasadura_toe_correlation(df, comps)
        assert res["n_benches"] == 0

    def test_compute_energy_density_along_profile_basic(self):
        from core.blast_model import compute_energy_density_along_profile

        df = pd.DataFrame({
            "X": [0.0, 50.0],
            "Y": [0.0, 0.0],
            "Z_collar": [4215.0, 4215.0],
            "Kilos_Cargados_real": [200.0, 300.0],
        })
        prof_x = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        prof_y = np.zeros(5)
        energy = compute_energy_density_along_profile(
            df, prof_x, prof_x.copy(), prof_y, search_radius=30.0,
        )
        assert energy.shape == (5,)
        assert (energy > 0).all()

    def test_compute_energy_density_along_profile_radius_filter(self):
        from core.blast_model import compute_energy_density_along_profile

        df = pd.DataFrame({
            "X": [0.0, 100.0],
            "Y": [0.0, 0.0],
            "Z_collar": [4215.0, 4215.0],
            "Kilos_Cargados_real": [200.0, 300.0],
        })
        prof_x = np.array([10.0, 50.0, 90.0])
        prof_y = np.zeros(3)
        energy_wide = compute_energy_density_along_profile(
            df, prof_x, prof_x.copy(), prof_y, search_radius=150.0,
        )
        energy_tight = compute_energy_density_along_profile(
            df, prof_x, prof_x.copy(), prof_y, search_radius=5.0,
        )
        assert energy_wide[0] > 0
        assert energy_wide[1] > 0
        assert energy_wide[2] > 0
        assert energy_tight[0] == 0.0
        assert energy_tight[1] == 0.0
        assert energy_tight[2] == 0.0

    def test_compute_energy_density_along_profile_empty(self):
        from core.blast_model import compute_energy_density_along_profile

        empty = compute_energy_density_along_profile(
            pd.DataFrame(), np.array([]), np.array([]), np.array([]),
        )
        assert empty.size == 0

    def test_compute_energy_density_along_profile_no_kg_column(self):
        from core.blast_model import compute_energy_density_along_profile

        df = pd.DataFrame({
            "X": [0.0, 10.0],
            "Y": [0.0, 0.0],
            "Z_collar": [4215.0, 4215.0],
        })
        prof_x = np.array([5.0, 5.0, 5.0])
        prof_y = np.zeros(3)
        energy = compute_energy_density_along_profile(
            df, prof_x, prof_x.copy(), prof_y, search_radius=30.0,
        )
        assert energy.shape == (3,)
        assert (energy > 0).all()


class TestComputePowderFactorGPerTon:
    """pf_g_per_ton = (Kilos × 1000) / (Burden × Esp × H_real × rho)."""

    def test_known_value_vertical_hole(self):
        """kg=100, B=4, S=5, vertical hole len=15, rho=2.7.

        H_real = 15 * cos(0) = 15
        pf_g_per_ton = 100000 / (4 * 5 * 15 * 2.7) = 123.456790...
        """
        df = pd.DataFrame([{
            "Kilos_Cargados_real": 100.0,
            "Burden": 4.0,
            "Esp": 5.0,
            "longitud_real": 15.0,
            "Inclinacion_real": 0.0,
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        assert out["pf_g_per_ton"].iloc[0] == pytest.approx(123.45679012, rel=1e-6)
        assert out["height_real_m"].iloc[0] == pytest.approx(15.0)

    def test_height_from_inclined_hole(self):
        """Inclined hole: H_real = 16 * cos(radians(20))."""
        df = pd.DataFrame([{
            "Kilos_Cargados_real": 100.0,
            "Burden": 4.0,
            "Esp": 5.0,
            "longitud_real": 16.0,
            "Inclinacion_real": 20.0,
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        expected_h = 16.0 * np.cos(np.radians(20.0))
        assert out["height_real_m"].iloc[0] == pytest.approx(expected_h)
        expected_pf = 100000.0 / (4.0 * 5.0 * expected_h * 2.7)
        assert out["pf_g_per_ton"].iloc[0] == pytest.approx(expected_pf, rel=1e-6)

    def test_fallback_when_longitud_missing(self):
        """When longitud_real is NaN, height falls back to BLAST.height_fallback_m."""
        from core.config import BLAST
        df = pd.DataFrame([{
            "Kilos_Cargados_real": 100.0,
            "Burden": 4.0,
            "Esp": 5.0,
            "longitud_real": np.nan,
            "Inclinacion_real": 0.0,
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        assert out["height_real_m"].iloc[0] == pytest.approx(BLAST.height_fallback_m)
        expected = 100000.0 / (4.0 * 5.0 * BLAST.height_fallback_m * BLAST.rock_density_tm3)
        assert out["pf_g_per_ton"].iloc[0] == pytest.approx(expected, rel=1e-6)

    def test_nan_propagation_when_kilos_missing(self):
        """Missing kg -> pf_g_per_ton is NaN even if geometry is valid."""
        df = pd.DataFrame([{
            "Kilos_Cargados_real": np.nan,
            "Burden": 4.0,
            "Esp": 5.0,
            "longitud_real": 15.0,
            "Inclinacion_real": 0.0,
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        assert pd.isna(out["pf_g_per_ton"].iloc[0])

    def test_existing_pf_columns_unchanged(self):
        """pf_vol_kgm3 / pf_area_kgm2 still computed with bench height, not H_real."""
        df = pd.DataFrame([{
            "Kilos_Cargados_real": 300.0,
            "Burden": 5.0,
            "Esp": 6.0,
            "longitud_real": 12.0,
            "Inclinacion_real": 0.0,
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        assert out["pf_vol_kgm3"].iloc[0] == pytest.approx(0.6667, abs=1e-3)
        assert out["pf_area_kgm2"].iloc[0] == pytest.approx(10.0, abs=1e-6)

    def test_pf_g_per_ton_in_aggregate(self):
        """aggregate_powder_factor_by_group exposes pf_g_per_ton_avg."""
        df = _holes_grid_with_pattern(burden=5.0, esp=6.0, kg=300.0, malla="M1")
        processed = procesar_pozos(df)[0]
        out = compute_powder_factor(processed)
        from core.calculo_tronadura import proyectar_pozos_en_seccion
        proj = proyectar_pozos_en_seccion(
            processed, origin=np.array([0.0, 0.0]), azimuth=90.0,
            length=200.0, tolerance=50.0,
        )
        proj_labeled = proj.copy()
        proj_labeled["section_name"] = "S1"
        agg = aggregate_powder_factor_by_group(out, "section_name", "S1", proj_labeled)
        assert "pf_g_per_ton_avg" in agg
        assert "pf_g_per_ton_weighted" in agg
        assert not pd.isna(agg["pf_g_per_ton_avg"])
        assert agg["pf_g_per_ton_avg"] > 0


class TestComputePowderFactorGPerTonNet:
    """pf_g_per_ton_net = (Kilos × 1000) / (Burden × Esp × H_net × rho).

    H_net = H_real - pasadura, where pasadura = (Z_collar - bench_height) - Z_toe.
    The pasadura term reuses the existing ``_pasadura`` helper with
    ``bench_height = height_fallback_m`` (the configured bench height, 15 m).
    When Z_collar/Z_toe are missing, pasadura = 0 → H_net = H_real (graceful
    fallback). H_net is clamped to NaN when non-positive.
    """

    def test_known_value_with_pasadura(self):
        """kg=100, B=4, S=5, vertical hole len=18, rho=2.7.

        pasadura = (1015 - 15) - 997 = 3
        H_net = 18 - 3 = 15
        pf_g_per_ton_net = 100000 / (4 × 5 × 15 × 2.7) = 123.456790...
        (primary pf_g_per_ton uses H_real=18 → 103.08...)
        """
        df = pd.DataFrame([{
            "Kilos_Cargados_real": 100.0,
            "Burden": 4.0,
            "Esp": 5.0,
            "longitud_real": 18.0,
            "Inclinacion_real": 0.0,
            "Z_collar": 1015.0,
            "Z_toe": 997.0,
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        assert out["height_real_m"].iloc[0] == pytest.approx(18.0)
        assert out["height_net_m"].iloc[0] == pytest.approx(15.0)
        # Primary PF unchanged: uses H_real=18
        assert out["pf_g_per_ton"].iloc[0] == pytest.approx(100000.0 / (4.0 * 5.0 * 18.0 * 2.7), rel=1e-6)
        # Net PF: uses H_net=15
        assert out["pf_g_per_ton_net"].iloc[0] == pytest.approx(100000.0 / (4.0 * 5.0 * 15.0 * 2.7), rel=1e-6)

    def test_fallback_equals_full_when_collar_toe_missing(self):
        """No Z_collar/Z_toe → pasadura = 0 → pf_g_per_ton_net == pf_g_per_ton."""
        df = pd.DataFrame([{
            "Kilos_Cargados_real": 100.0,
            "Burden": 4.0,
            "Esp": 5.0,
            "longitud_real": 15.0,
            "Inclinacion_real": 0.0,
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        assert out["height_net_m"].iloc[0] == pytest.approx(out["height_real_m"].iloc[0])
        assert out["pf_g_per_ton_net"].iloc[0] == pytest.approx(out["pf_g_per_ton"].iloc[0])

    def test_negative_pasadura_falls_back_to_zero(self):
        """If pasadura computes negative (Z_toe below floor), treat as 0.

        Z_collar=1015, bench=15 → floor=1000; Z_toe=1001 → pasadura = -1
        (toe is above floor, not sub-drill) → clamp to 0 → H_net = H_real.
        """
        df = pd.DataFrame([{
            "Kilos_Cargados_real": 100.0,
            "Burden": 4.0,
            "Esp": 5.0,
            "longitud_real": 15.0,
            "Inclinacion_real": 0.0,
            "Z_collar": 1015.0,
            "Z_toe": 1001.0,  # pasadura = (1015-15) - 1001 = -1 → clamped to 0
            "Nombre_Malla_Original": "M1",
            "Tipo_Explosivo": "ANFO",
        }])
        out = compute_powder_factor(df)
        assert out["height_net_m"].iloc[0] == pytest.approx(15.0)
        assert out["pf_g_per_ton_net"].iloc[0] == pytest.approx(out["pf_g_per_ton"].iloc[0])

    def test_pf_g_per_ton_net_in_aggregate(self):
        """aggregate_powder_factor_by_group exposes pf_g_per_ton_net_avg."""
        df = _holes_grid_with_pattern(burden=5.0, esp=6.0, kg=300.0, malla="M1")
        processed = procesar_pozos(df)[0]
        out = compute_powder_factor(processed)
        from core.calculo_tronadura import proyectar_pozos_en_seccion
        proj = proyectar_pozos_en_seccion(
            processed, origin=np.array([0.0, 0.0]), azimuth=90.0,
            length=200.0, tolerance=50.0,
        )
        proj_labeled = proj.copy()
        proj_labeled["section_name"] = "S1"
        agg = aggregate_powder_factor_by_group(out, "section_name", "S1", proj_labeled)
        assert "pf_g_per_ton_net_avg" in agg
        assert "pf_g_per_ton_net_weighted" in agg
        # procesar_pozos derives Z_collar/Z_toe, so net is finite and > 0.
        assert not pd.isna(agg["pf_g_per_ton_net_avg"])
        assert agg["pf_g_per_ton_net_avg"] > 0
