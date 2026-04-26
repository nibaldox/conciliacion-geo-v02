"""Tests for design vs as-built comparison and status triad logic."""

import numpy as np
import pytest

from core import extract_parameters, SectionLine, cut_mesh_with_section
from core.param_extractor import _evaluate_status, BenchParams, ExtractionResult


# ---------------------------------------------------------------------------
# Status Triad Unit Tests
# ---------------------------------------------------------------------------


class TestStatusTriad:
    """Tests for the CUMPLE / FUERA DE TOLERANCIA / NO CUMPLE logic."""

    def test_cumple_positive(self):
        """Desviación dentro de tolerancia → CUMPLE."""
        assert _evaluate_status(0.5, tol_neg=1.0, tol_pos=1.5) == "CUMPLE"
        assert _evaluate_status(1.0, tol_neg=1.0, tol_pos=1.5) == "CUMPLE"
        assert _evaluate_status(1.5, tol_neg=1.0, tol_pos=1.5) == "CUMPLE"

    def test_cumple_negative(self):
        """Desviación negativa dentro de tolerancia → CUMPLE."""
        assert _evaluate_status(-0.5, tol_neg=1.0, tol_pos=1.5) == "CUMPLE"
        assert _evaluate_status(-1.0, tol_neg=1.0, tol_pos=1.5) == "CUMPLE"

    def test_fuera_de_tolerancia_positive(self):
        """Desviación > tol pero ≤ 1.5× tol → FUERA DE TOLERANCIA."""
        # tol_pos=1.5, 1.5*1.5=2.25 → entre 1.5 y 2.25
        assert _evaluate_status(1.6, tol_neg=1.0, tol_pos=1.5) == "FUERA DE TOLERANCIA"
        assert _evaluate_status(2.25, tol_neg=1.0, tol_pos=1.5) == "FUERA DE TOLERANCIA"

    def test_fuera_de_tolerancia_negative(self):
        """Desviación negativa > |tol_neg| pero ≤ 1.5× |tol_neg| → FUERA DE TOLERANCIA."""
        # tol_neg=1.0, 1.5*1.0=1.5 → entre 1.0 y 1.5
        assert _evaluate_status(-1.1, tol_neg=1.0, tol_pos=1.5) == "FUERA DE TOLERANCIA"
        assert _evaluate_status(-1.5, tol_neg=1.0, tol_pos=1.5) == "FUERA DE TOLERANCIA"

    def test_no_cumple_positive(self):
        """Desviación > 1.5× tol → NO CUMPLE."""
        # tol_pos=1.5, 1.5*1.5=2.25 → >2.25
        assert _evaluate_status(2.3, tol_neg=1.0, tol_pos=1.5) == "NO CUMPLE"
        assert _evaluate_status(5.0, tol_neg=1.0, tol_pos=1.5) == "NO CUMPLE"

    def test_no_cumple_negative(self):
        """Desviación negativa > 1.5× |tol_neg| → NO CUMPLE."""
        assert _evaluate_status(-1.6, tol_neg=1.0, tol_pos=1.5) == "NO CUMPLE"
        assert _evaluate_status(-3.0, tol_neg=1.0, tol_pos=1.5) == "NO CUMPLE"

    def test_zero_deviation(self):
        """Desviación cero → CUMPLE."""
        assert _evaluate_status(0.0, tol_neg=1.0, tol_pos=1.0) == "CUMPLE"

    def test_boundary_exact_tolerance(self):
        """Exactamente en el límite de tolerancia → CUMPLE."""
        assert _evaluate_status(1.0, tol_neg=1.0, tol_pos=1.0) == "CUMPLE"

    def test_boundary_exact_1_5x(self):
        """Exactamente en 1.5× tolerancia → FUERA DE TOLERANCIA (<=)."""
        assert _evaluate_status(1.5, tol_neg=1.0, tol_pos=1.0) == "FUERA DE TOLERANCIA"

    def test_status_triad_logic(self):
        """Verificar la lógica completa de la tríada en un solo test."""
        tol_neg, tol_pos = 1.0, 1.0
        # CUMPLE: |dev| <= 1.0
        for dev in [0.0, 0.5, 0.99, 1.0, -0.5, -1.0]:
            assert _evaluate_status(dev, tol_neg, tol_pos) == "CUMPLE", (
                f"dev={dev} debería ser CUMPLE"
            )
        # FUERA DE TOLERANCIA: 1.0 < |dev| <= 1.5
        for dev in [1.01, 1.2, 1.5, -1.01, -1.5]:
            assert _evaluate_status(dev, tol_neg, tol_pos) == "FUERA DE TOLERANCIA", (
                f"dev={dev} debería ser FUERA DE TOLERANCIA"
            )
        # NO CUMPLE: |dev| > 1.5
        for dev in [1.51, 2.0, 10.0, -1.51, -5.0]:
            assert _evaluate_status(dev, tol_neg, tol_pos) == "NO CUMPLE", (
                f"dev={dev} debería ser NO CUMPLE"
            )


# ---------------------------------------------------------------------------
# Integration: compare_design_vs_asbuilt
# ---------------------------------------------------------------------------


class TestCompareDesignVsAsbuilt:
    """Integration tests for compare_design_vs_asbuilt."""

    def _make_params(self, benches, section_name="S-01", sector="Test"):
        """Helper: crea ExtractionResult con bancos dados."""
        return ExtractionResult(
            section_name=section_name,
            sector=sector,
            benches=benches,
        )

    def test_compare_cumple(self, sample_tolerances):
        """Cuando diseño ≈ as-built, status = CUMPLE."""
        bench_d = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3885.0,
            toe_distance=105.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        bench_a = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.2,
            toe_elevation=3885.1,
            toe_distance=105.6,
            bench_height=14.9,
            face_angle=69.5,
            berm_width=8.8,
        )

        params_d = self._make_params([bench_d])
        params_a = self._make_params([bench_a])

        from core import compare_design_vs_asbuilt

        comparisons = compare_design_vs_asbuilt(params_d, params_a, sample_tolerances)
        assert len(comparisons) >= 1
        match = [c for c in comparisons if c["type"] == "MATCH"]
        assert len(match) >= 1
        assert match[0]["height_status"] == "CUMPLE"
        assert match[0]["angle_status"] == "CUMPLE"

    def test_compare_fuera_de_tolerancia(self, sample_tolerances):
        """Desviación moderada → FUERA DE TOLERANCIA."""
        bench_d = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3885.0,
            toe_distance=105.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        # Desviación en altura: 1.6m (fuera de tol_pos=1.5, dentro de 1.5× tol_pos=2.25)
        bench_a = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3883.4,
            toe_distance=105.5,
            bench_height=16.6,
            face_angle=70.0,
            berm_width=9.0,
        )

        params_d = self._make_params([bench_d])
        params_a = self._make_params([bench_a])

        from core import compare_design_vs_asbuilt

        comparisons = compare_design_vs_asbuilt(params_d, params_a, sample_tolerances)
        match = [c for c in comparisons if c["type"] == "MATCH"]
        assert len(match) >= 1
        assert match[0]["height_status"] == "FUERA DE TOLERANCIA"

    def test_compare_no_cumple(self, sample_tolerances):
        """Desviación grande → NO CUMPLE."""
        bench_d = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3885.0,
            toe_distance=105.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        # Desviación en altura: 4.0m > 1.5 × tol_pos(1.5) = 2.25
        bench_a = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3881.0,
            toe_distance=105.5,
            bench_height=19.0,
            face_angle=70.0,
            berm_width=9.0,
        )

        params_d = self._make_params([bench_d])
        params_a = self._make_params([bench_a])

        from core import compare_design_vs_asbuilt

        comparisons = compare_design_vs_asbuilt(params_d, params_a, sample_tolerances)
        match = [c for c in comparisons if c["type"] == "MATCH"]
        assert len(match) >= 1
        assert match[0]["height_status"] == "NO CUMPLE"

    def test_compare_missing_bench(self, sample_tolerances):
        """Banco diseñado no construido → tipo MISSING."""
        bench_d1 = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3885.0,
            toe_distance=105.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        bench_d2 = BenchParams(
            bench_number=2,
            crest_elevation=3885.0,
            crest_distance=105.5,
            toe_elevation=3870.0,
            toe_distance=111.0,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        # Solo un banco as-built (el segundo no se construyó)
        bench_a1 = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3885.0,
            toe_distance=105.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )

        params_d = self._make_params([bench_d1, bench_d2])
        params_a = self._make_params([bench_a1])

        from core import compare_design_vs_asbuilt

        comparisons = compare_design_vs_asbuilt(params_d, params_a, sample_tolerances)
        missing = [c for c in comparisons if c["type"] == "MISSING"]
        assert len(missing) >= 1
        assert missing[0]["height_status"] == "NO CONSTRUIDO"

    def test_compare_extra_bench(self, sample_tolerances):
        """Banco adicional no diseñado → tipo EXTRA."""
        bench_d = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3885.0,
            toe_distance=105.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        # Dos bancos as-built (el segundo es extra)
        bench_a1 = BenchParams(
            bench_number=1,
            crest_elevation=3900.0,
            crest_distance=100.0,
            toe_elevation=3885.0,
            toe_distance=105.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        bench_a2 = BenchParams(
            bench_number=2,
            crest_elevation=3860.0,
            crest_distance=108.0,
            toe_elevation=3845.0,
            toe_distance=113.5,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )

        params_d = self._make_params([bench_d])
        params_a = self._make_params([bench_a1, bench_a2])

        from core import compare_design_vs_asbuilt

        comparisons = compare_design_vs_asbuilt(params_d, params_a, sample_tolerances)
        extra = [c for c in comparisons if c["type"] == "EXTRA"]
        assert len(extra) >= 1

    def test_compare_both_empty(self, sample_tolerances):
        """Ambos sin bancos → lista vacía."""
        params_d = self._make_params([])
        params_a = self._make_params([])

        from core import compare_design_vs_asbuilt

        comparisons = compare_design_vs_asbuilt(params_d, params_a, sample_tolerances)
        assert comparisons == []
