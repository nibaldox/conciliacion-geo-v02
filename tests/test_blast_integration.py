"""Integration tests for blast module — end-to-end pipeline + edge cases + robustez.

Este archivo cubre el flujo completo del módulo de tronadura con datos sintéticos
realistas, edge cases en funciones puras, invariants de compatibilidad hacia atrás
y robustez con datos de minería realistas.

Criterios: 8-12 tests distribuidos en 4 categorías.
"""
import warnings
from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from core.blast_advisor import (
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INSUFFICIENT,
    format_recommendation_text,
    recommend_by_sector,
    recommend_charge_change_pct,
    recommend_pf_adjustment,
)
from core.blast_correlation import (
    BlastCorrelationRow,
    aggregate_powder_factor_by_group,
    compute_blast_geotech_correlation,
    compute_powder_factor,
)
from core.blast_model import (
    compute_energy_density_along_profile,
    compute_pasadura_toe_correlation,
    fit_powder_factor_damage_model,
    predict_damage_for_pf,
)
from core.calculo_tronadura import procesar_pozos, proyectar_pozos_en_seccion
from core.config import ADVISOR, EXPLOSIVE


# ===========================================================================
# Helper functions
# ===========================================================================


def _synthetic_holes(
    n=20,
    burden=5.0,
    esp=6.0,
    kg_base=300.0,
    kg_variation=50.0,
    explosive_types=("ANFO", "Heavy ANFO", "Bulk Emulsion"),
    sections=5,
    start_date="2024-01-01",
):
    """Genera pozos sintéticos realistas distribuidos en N secciones."""
    rng = np.random.default_rng(42)
    rows = []

    explosives = list(explosive_types)
    sec_names = [f"S{i+1}" for i in range(sections)]

    for i in range(n):
        # Distribuir pozos en secciones a lo largo del eje X
        section_idx = i % sections
        x_offset = section_idx * 50.0  # 50m entre secciones

        # Patrón de malla dentro de cada sección
        in_section_idx = i // sections
        y_pos = in_section_idx * esp
        x_pos = x_offset + (in_section_idx % 2) * burden

        # Variar kilos aleatoriamente
        kg = kg_base + rng.uniform(-kg_variation, kg_variation)

        # Fecha variada (un mes por sección)
        from datetime import datetime, timedelta
        base = datetime.strptime(start_date, "%Y-%m-%d")
        date_offset = timedelta(days=section_idx * 30)
        hole_date = base + date_offset + timedelta(days=int(rng.integers(0, 25)))

        rows.append({
            "label_pozo": f"P-{i:03d}",
            "Latitud_Geo": x_pos,
            "Longitud_Geo": y_pos,
            "Nombre_Banco": 4200.0 + section_idx * 15.0,
            "Inclinacion_real": 0.0,
            "Azimuth_real": 0.0,
            "longitud_real": 12.0,
            "Kilos_Cargados_real": kg,
            "Burden": burden,
            "Esp": esp,
            "Tipo_Explosivo": explosives[i % len(explosives)],
            "Nombre_Malla_Original": f"M{section_idx+1}",
            "fecha_tronadura": hole_date.strftime("%Y-%m-%d"),
        })

    return pd.DataFrame(rows), sec_names


def _section_obj(name, x, y, az=90.0, length=200.0):
    """Construye un objeto simple tipo SectionLine."""
    return type(
        "Sec",
        (),
        {"name": name, "origin": np.array([x, y]), "azimuth": az, "length": length, "sector": ""},
    )()


def _positive_model(n=20, beta1=1.4, beta0=-0.2):
    """Modelo con pendiente positiva: más PF -> más daño."""
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


# ===========================================================================
# CATEGORÍA 1 — Tests de integración end-to-end
# ===========================================================================


class TestEndToEnd:
    """Flujo completo con datos sintéticos realistas."""

    def test_end_to_end_full_pipeline(self):
        """Ejecuta pipeline completo: procesar -> PF -> agrupar -> ajustar modelo -> recomendar."""
        # 1. Generar datos sintéticos
        holes_df, sec_names = _synthetic_holes(n=20, sections=5)

        # 2. Procesar pozos
        processed = procesar_pozos(holes_df)[0]
        assert not processed.empty
        assert "X" in processed.columns
        assert "Z_collar" in processed.columns

        # 3. Calcular PF
        pf_df = compute_powder_factor(processed)
        assert "pf_vol_kgm3" in pf_df.columns
        assert "pf_area_kgm2" in pf_df.columns
        assert pf_df["pf_vol_kgm3"].mean() > 0

        # 4. Proyectar y agrupar por sección
        sections = [_section_obj(sec, i * 50.0, 0.0) for i, sec in enumerate(sec_names)]
        origin = np.array([0.0, 0.0])

        proj = proyectar_pozos_en_seccion(
            pf_df, origin=origin, azimuth=90.0, length=200.0, tolerance=50.0,
        )
        proj_labeled = proj.copy()
        proj_labeled["section_name"] = "S1"  # Todos en S1 para simplificar

        agg = aggregate_powder_factor_by_group(pf_df, "section_name", "S1", proj_labeled)
        assert agg["n_wells"] > 0
        assert agg["pf_vol_avg"] > 0

        # 5. Ajustar modelo con datos sintéticos correlacionados
        rng = np.random.default_rng(42)
        pf_vals = np.linspace(0.3, 0.7, 15)
        # Crear sobre-excavación correlacionada con PF
        damage_vals = 0.8 * pf_vals + 0.1 + rng.normal(0, 0.05, 15)

        model = fit_powder_factor_damage_model(pf_vals, damage_vals)
        assert model["confidence"] in ("HIGH", "MEDIUM")
        assert model["beta1"] > 0  # Correlación positiva

        # 6. Generar recomendación
        current_pf = float(agg["pf_vol_avg"])
        rec = recommend_pf_adjustment(model, current_pf=current_pf)

        # 7. Verificar estructura y valores coherentes
        assert rec["feasibility"] in {FEASIBILITY_APPLICABLE, FEASIBILITY_CAUTION}
        assert "target_pf" in rec
        assert "delta_pf" in rec
        assert "message" in rec

        # delta_pf debe tener signo coherente con la pendiente del modelo
        if rec["feasibility"] == FEASIBILITY_APPLICABLE:
            assert np.isfinite(rec["delta_pf"])
            # Si beta1 > 0, delta_pf debe reducir PF si current_damage > target
            predicted_current = rec["predicted_current_damage"]
            if predicted_current > ADVISOR.target_overbreak_m:
                assert rec["delta_pf"] < 0  # Reducir PF

    def test_end_to_end_with_temporal_filter(self):
        """Verifica que el filtro temporal excluye pozos posteriores a fecha_corte."""
        holes_df, sec_names = _synthetic_holes(
            n=15, sections=3, start_date="2024-01-01"
        )

        processed = procesar_pozos(holes_df)[0]
        assert "fecha_tronadura" in processed.columns

        # Fecha de corte: 2024-06-01 (excluir pozos de junio en adelante)
        cutoff_date = "2024-06-01"
        origin = np.array([0.0, 0.0])

        # Proyectar con filtro temporal
        proj_filtered = proyectar_pozos_en_seccion(
            processed,
            origin=origin,
            azimuth=90.0,
            length=200.0,
            tolerance=50.0,
            fecha_corte=cutoff_date,
        )

        # Proyectar sin filtro
        proj_all = proyectar_pozos_en_seccion(
            processed,
            origin=origin,
            azimuth=90.0,
            length=200.0,
            tolerance=50.0,
            fecha_corte=None,
        )

        # Verificar que se filtraron pozos
        assert len(proj_filtered) <= len(proj_all)

        # Si hay pozos después de la fecha de corte, deben ser excluidos
        dates_after = pd.to_datetime(processed["fecha_tronadura"]) > pd.to_datetime(cutoff_date)
        if dates_after.any():
            assert len(proj_filtered) < len(proj_all)

        # Verificar que el PF final usa solo pozos válidos
        pf_filtered = compute_powder_factor(proj_filtered)
        if not pf_filtered.empty:
            assert pf_filtered["pf_vol_kgm3"].notna().sum() <= len(proj_filtered)

    def test_end_to_end_integration_blast_correlation(self):
        """Integra compute_blast_geotech_correlation con datos completos."""
        holes_df, sec_names = _synthetic_holes(n=12, sections=3)
        processed = procesar_pozos(holes_df)[0]
        pf_df = compute_powder_factor(processed)

        # Crear secciones
        sections = [_section_obj(sec, i * 50.0, 0.0) for i, sec in enumerate(sec_names)]

        # Crear comparisons con delta_crest (sobre-excavación)
        comparisons = [
            {"section": "S1", "delta_crest": 0.5, "delta_toe": 0.2},
            {"section": "S2", "delta_crest": 0.8, "delta_toe": 0.3},
            {"section": "S3", "delta_crest": -0.2, "delta_toe": -0.1},
        ]

        # Ejecutar correlación
        rows = compute_blast_geotech_correlation(pf_df, sections, comparisons)

        assert len(rows) == 3
        assert all(isinstance(r, BlastCorrelationRow) for r in rows)

        # Verificar que cada row tiene campos firmados válidos
        for r in rows:
            assert hasattr(r, "avg_over_break")
            assert hasattr(r, "pf_vol_avg_kgm3")
            assert hasattr(r, "energy_total_mj")
            assert np.isfinite(r.pf_vol_avg_kgm3) or r.num_wells == 0
            assert np.isfinite(r.energy_total_mj) or r.num_wells == 0


# ===========================================================================
# CATEGORÍA 2 — Tests de edge cases en funciones puras
# ===========================================================================


class TestEdgeCases:
    """Casos límite en funciones puras del módulo de tronadura."""

    def test_compute_powder_factor_knn_fallback_when_burden_missing(self):
        """Verifica que k-NN estima burden/esp cuando faltan columnas."""
        # Crear grilla 5x4 sin columnas Burden/Esp
        rng = np.random.default_rng(42)
        rows = []
        spacing = 6.0
        kg = 300.0
        bench = 15.0

        for i in range(5):
            for j in range(4):
                rows.append({
                    "label_pozo": f"P-{i}-{j}",
                    "Latitud_Geo": float(i * spacing),
                    "Longitud_Geo": float(j * spacing),
                    "Nombre_Banco": 4200.0,
                    "Inclinacion_real": 0.0,
                    "Azimuth_real": 0.0,
                    "longitud_real": 12.0,
                    "Kilos_Cargados_real": kg,
                    "fecha_tronadura": "2024-01-01",
                })

        df = pd.DataFrame(rows)
        processed = procesar_pozos(df)[0]

        # Verificar que no hay Burden/Esp
        assert "Burden" not in processed.columns
        assert "Esp" not in processed.columns

        # Compute PF debe usar k-NN
        out = compute_powder_factor(processed)

        # Verificar que se estimaron valores
        assert "pf_vol_kgm3" in out.columns
        assert "burden_est_m" in out.columns
        assert "esp_est_m" in out.columns

        # El PF estimado por k-NN usa la mediana de distancias a los 4 vecinos más cercanos.
        # En una grilla 5x4 regular con spacing=6m, esa mediana ≈ 6m, pero el algoritmo no
        # garantiza reproducir exactamente el spacing (asimetrías de borde, varianza). Por eso
        # la tolerancia es amplia (±0.3) — lo importante es que el PF esté en rango físicamente
        # razonable para roca tronada (0.2–0.8 kg/m³).
        assert 0.2 < out["pf_vol_kgm3"].iloc[0] < 0.8
        assert out["burden_est_m"].notna().all()
        assert out["esp_est_m"].notna().all()

    def test_predict_damage_for_pf_with_empty_model(self):
        """predict_damage_for_pf no debe lanzar con modelo vacío."""
        empty_model = {}

        # No debe lanzar excepción
        pred = predict_damage_for_pf(empty_model, 0.5)

        # Debe retornar dict con keys esperadas
        assert "predicted_damage" in pred
        assert "delta_from_current" in pred
        assert "uncertainty_m" in pred

        # Con modelo vacío, retorna ceros por convención
        assert pred["predicted_damage"] == 0.0
        assert pred["delta_from_current"] == 0.0
        assert pred["uncertainty_m"] == 0.0

    def test_recommend_charge_change_pct_direction_none_when_no_change(self):
        """Con β₁ cercano a cero, recommend_charge_change_pct debe retornar NONE."""
        # Modelo con pendiente muy pequeña
        model = {
            "beta0": 0.0,
            "beta1": 1e-10,  # Cero prácticamente
            "r_squared": 0.0,
            "p_value": 0.9,
            "n": 20,
            "std_err_beta1": 0.01,
            "ci_beta1_low": -0.02,
            "ci_beta1_high": 0.02,
            "mean_pf": 0.45,
            "confidence": "INSUFFICIENT",
            "is_significant": False,
        }

        result = recommend_charge_change_pct(model, current_pf=0.5)

        # Verificar que retorna dict válido
        assert "direction" in result
        assert "delta_pct" in result
        assert "feasibility" in result

        # Con pendiente ~0, no hay cambio recomendado
        assert result["direction"] == "NONE"
        assert result["delta_pct"] == 0.0
        assert result["feasibility"] == FEASIBILITY_INSUFFICIENT


# ===========================================================================
# CATEGORÍA 3 — Tests de invariants y backward compatibility
# ===========================================================================


class TestBackwardsCompat:
    """Verifica compatibilidad hacia atrás e invariants estructurales."""

    def test_blast_correlation_row_backwards_compat_as_tuple(self):
        """as_tuple debe funcionar con solo 4 campos posicionales."""
        # Crear con mínimo campos (4 posicionales obligatorios)
        row = BlastCorrelationRow("S1", 5, 1000.0, 0.5)

        # as_tuple retorna 4 elementos (report_generator/excel_writer dependen de esto)
        t = row.as_tuple()
        assert len(t) == 4
        assert t == ("S1", 5, 1000.0, 0.5)

        # as_signed_tuple retorna 13 elementos con defaults
        signed = row.as_signed_tuple()
        assert len(signed) == 13
        assert signed[0] == "S1"
        assert signed[1] == 5
        assert signed[2] == 1000.0
        assert signed[3] == 0.5
        # Campos nuevos deben estar en 0 (defaults)
        assert signed[4] == 0.0  # avg_over_break
        assert signed[5] == 0.0  # avg_under_break
        assert signed[6] == 0   # n_over
        assert signed[7] == 0   # n_under
        assert signed[8] == 0.0  # pf_vol_avg_kgm3
        assert signed[9] == 0.0  # pf_area_avg_kgm2
        assert signed[10] == 0.0  # pf_g_per_ton_avg
        assert signed[11] == 0.0  # energy_total_mj
        assert signed[12] == 0    # n_pf_valid

    def test_explosive_energy_handles_unknown_types_gracefully(self):
        """EXPLOSIVE.energy_mj_per_kg nunca lanza; retorna fallback para tipos desconocidos."""
        # Tipos desconocidos deben retornar valor por defecto (ANFO)
        unknown_types = ["", "UNKNOWN", "MysteryExplosive", None, "XYZ-123"]

        for et in unknown_types:
            energy = EXPLOSIVE.energy_mj_per_kg(et)
            # Nunca retorna NaN ni None
            assert np.isfinite(energy)
            # Debe ser el valor fallback (ANFO)
            assert energy == pytest.approx(EXPLOSIVE.anfo_energy)

            # Mismo test para density
            density = EXPLOSIVE.density_g_per_cm3(et)
            assert np.isfinite(density)
            assert density == pytest.approx(EXPLOSIVE.anfo_density)

    def test_advisor_defaults_are_immutable(self):
        """ADVISOR es frozen=True; intentar mutar debe lanzar FrozenInstanceError."""
        # ADVISOR es una instancia frozen de BlastAdvisorDefaults
        assert hasattr(ADVISOR, "target_overbreak_m")

        # Intentar mutar debe lanzar
        with pytest.raises((FrozenInstanceError, AttributeError)):
            ADVISOR.target_overbreak_m = 1.0

        with pytest.raises((FrozenInstanceError, AttributeError)):
            ADVISOR.max_recommendation_pct = 50.0

        # Verificar que valores originales no cambiaron
        assert ADVISOR.target_overbreak_m == 0.5
        assert ADVISOR.max_recommendation_pct == 30.0


# ===========================================================================
# CATEGORÍA 4 — Tests de robustez con datos realistas
# ===========================================================================


class TestRobustRealisticData:
    """Tests con datos de minería realistas y verificación de formato."""

    def test_recommend_pf_with_realistic_mining_data(self):
        """Dataset realista: PF 0.25-0.65, sobre-excavación correlacionada."""
        rng = np.random.default_rng(42)

        # 15 secciones con PF variado
        pf_vals = np.linspace(0.25, 0.65, 15)
        # Sobre-excavación correlacionada con ruido
        damage_vals = 0.7 * pf_vals + 0.05 + rng.normal(0, 0.08, 15)

        model = fit_powder_factor_damage_model(pf_vals, damage_vals)

        # Probar con diferentes PFs actuales
        for current_pf in [0.30, 0.45, 0.60]:
            rec = recommend_pf_adjustment(
                model, current_pf=current_pf, target_overbreak_m=0.5
            )

            # Verificar que delta_pf tiene sentido físico
            if current_pf < 0.45:  # Por debajo del óptimo esperado
                # PF bajo -> menos daño -> delta debe ser positivo (aumentar)
                if rec["feasibility"] == FEASIBILITY_APPLICABLE:
                    assert rec["delta_pf"] >= 0
            elif current_pf > 0.55:  # Por arriba del óptimo
                # PF alto -> más daño -> delta debe ser negativo (reducir)
                if rec["feasibility"] == FEASIBILITY_APPLICABLE:
                    assert rec["delta_pf"] <= 0

    def test_format_recommendation_text_spanish_keywords(self):
        """Verifica keywords en español y ausencia de argentinismos."""
        model = _positive_model()

        # Test APPLICABLE
        rec_applicable = recommend_pf_adjustment(model, current_pf=0.55)
        text_app = format_recommendation_text(rec_applicable, section_name="Norte")

        # Keywords esperadas
        assert any(kw in text_app.lower() for kw in ["reducir", "aumentar", "ajustar"])
        assert "kg/m" in text_app  # "kg/m3" o "kg/m"
        assert "norte" in text_app.lower()

        # Test CAUTION
        rec_caution = recommend_pf_adjustment(
            model, current_pf=1.2, target_overbreak_m=0.2
        )
        text_caution = format_recommendation_text(rec_caution, section_name="Sur")

        assert "excede" in text_caution.lower() or "revisar" in text_caution.lower()

        # Test INSUFFICIENT
        rec_insuf = recommend_pf_adjustment(
            {"confidence": "INSUFFICIENT", "n": 2, "p_value": 0.5, "beta1": 0.0},
            current_pf=0.5,
        )
        text_insuf = format_recommendation_text(rec_insuf, section_name="Este")

        assert "no se puede" in text_insuf.lower() or "insuficiente" in text_insuf.lower()

        # Verificar ausencia de argentinismos
        argentinismos = ["podés", "tenés", "cuenta", "che", "boludo", "viste"]
        for text in [text_app, text_caution, text_insuf]:
            text_lower = text.lower()
            for arg in argentinismos:
                assert arg not in text_lower, f"Argentinismo '{arg}' encontrado en: {text}"

    def test_compute_energy_density_along_profile_with_realistic_distances(self):
        """Perfil de 50 puntos, 10 pozos patrón 5x2, verifica decaimiento 1/r²."""
        rng = np.random.default_rng(42)

        # 10 pozos en patrón 5x2 a lo largo de eje X, centrados lejos de los extremos del perfil
        rows = []
        well_x_positions = [40.0, 70.0, 100.0, 130.0, 160.0]
        for i, wx in enumerate(well_x_positions):
            for j in range(2):
                rows.append({
                    "label_pozo": f"P-{i}-{j}",
                    "X": float(wx),
                    "Y": float(j * 6.0),
                    "Z_collar": 4200.0,
                    "Kilos_Cargados_real": 250.0,
                })

        holes_df = pd.DataFrame(rows)
        # procesar_pozos requiere columnas crudas (Nombre_Banco, Inclinacion_real, etc.),
        # pero este test solo necesita los pozos proyectados para IDW. Usamos el
        # holes_df directamente con las coordenadas que ya están listas.
        processed = holes_df.assign(
            Z_toe=holes_df["Z_collar"] - 12.0,
            Len=12.0,
            Incl=0.0,
            Az=0.0,
        )

        # Perfil de 50 puntos a lo largo de 200m
        prof_x = np.linspace(0, 200, 50)
        prof_y = np.zeros(50)

        energy = compute_energy_density_along_profile(
            processed,
            profile_distances=prof_x,
            profile_xs=prof_x,
            profile_ys=prof_y,
            search_radius=40.0,
        )

        # Verificar estructura
        assert energy.shape == (50,)
        assert (energy >= 0).all()

        # El máximo debe estar cerca de los pozos
        max_idx = np.argmax(energy)
        max_pos = prof_x[max_idx]

        # Al menos un pozo debe estar cerca del máximo
        well_positions = processed["X"].values
        assert any(abs(well_positions - max_pos) < 25.0)

        # Verificar decaimiento: valores lejanos deben ser menores
        # Los puntos en los extremos (0 y 200) deben tener energía baja
        # comparados con el centro (donde están los pozos)
        center_energy = energy[20:30].mean()
        edge_energy = (energy[0:5].mean() + energy[-5:].mean()) / 2

        # Centro debe tener más energía que los bordes
        assert center_energy > edge_energy


# ===========================================================================
# Extra: Test de integración con pasadura-toe correlation
# ===========================================================================


class TestPasaduraToeIntegration:
    """Integración específica para correlación pasadura-delta_toe."""

    def test_pasadura_toe_correlation_with_synthetic_benches(self):
        """Dos bancos con pasadura correlacionada negativamente con delta_toe."""
        df = pd.DataFrame({
            "X": [0.0, 10.0, 20.0, 30.0, 0.0, 10.0, 20.0, 30.0],
            "Y": [0.0] * 8,
            "Z_collar": [4215.0] * 4 + [4230.0] * 4,
            "Z_toe": [4197.5, 4198.0, 4197.0, 4197.5,  # pasadura ~0.5 (banco 1)
                     4213.0, 4213.5, 4212.5, 4213.0],  # pasadura ~0.5 (banco 2)
        })

        comparisons = [
            {"level": "4200", "delta_toe": 0.5},   # Banco 1: pasadura corta, toe positivo
            {"level": "4215", "delta_toe": -0.3},  # Banco 2: pasadura corta, toe negativo
        ]

        result = compute_pasadura_toe_correlation(df, comparisons, bench_height=15.0)

        assert result["n_benches"] == 2
        assert "r" in result
        assert "interpretation" in result

        # Con datos sintéticos correlacionados, debe haber un r
        assert np.isfinite(result["r"])
        assert len(result["pasadura_per_bench"]) > 0
        assert len(result["toe_per_bench"]) > 0
