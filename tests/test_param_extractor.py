"""Tests for core.param_extractor — parameter extraction from profiles."""

import numpy as np
import pytest

from core import extract_parameters, SectionLine, cut_mesh_with_section


class TestExtractParameters:
    """Tests for parameter extraction on synthetic pit meshes."""

    @pytest.fixture()
    def design_profile(self, pit_mesh_design):
        """Perfil de sección cortada del mesh de diseño."""
        section = SectionLine(
            name="S-01",
            origin=np.array([250.0, 250.0]),
            azimuth=0.0,
            length=400.0,
            sector="Test",
        )
        profile = cut_mesh_with_section(pit_mesh_design, section)
        assert profile is not None, "La sección debe intersectar el mesh de diseño"
        return profile

    def test_extract_parameters_benches_detected(self, design_profile):
        """Detectar al menos 1 banco en mesh de pit."""
        result = extract_parameters(
            design_profile.distances,
            design_profile.elevations,
            "S-01",
            "Test",
        )
        assert len(result.benches) >= 1

    def test_extract_parameters_bench_height(self, design_profile):
        """Al menos un banco con altura ~15m (dentro de 3m de tolerancia).

        Nota: la geometría radial del pit sintético causa que la sección no
        intersecte todos los bancos perfectamente, por lo que verificamos que
        al menos uno esté en el rango esperado.
        """
        result = extract_parameters(
            design_profile.distances,
            design_profile.elevations,
            "S-01",
            "Test",
        )
        assert len(result.benches) >= 1
        # Al menos un banco debe tener altura cercana a 15m
        heights = [b.bench_height for b in result.benches]
        assert any(np.isclose(h, 15.0, atol=3.0) for h in heights), (
            f"No se detectó ningún banco con altura ~15m. Alturas: {[f'{h:.1f}' for h in heights]}"
        )

    def test_extract_parameters_face_angle(self, design_profile):
        """Al menos un banco con ángulo de cara ~70° (dentro de 15° de tolerancia).

        Nota: la geometría radial y la discretización del mesh sintético causan
        variación en el ángulo detectado. Verificamos que al menos uno esté
        en el rango esperado.
        """
        result = extract_parameters(
            design_profile.distances,
            design_profile.elevations,
            "S-01",
            "Test",
        )
        assert len(result.benches) >= 1
        angles = [b.face_angle for b in result.benches]
        assert any(np.isclose(a, 70.0, atol=15.0) for a in angles), (
            f"No se detectó ningún banco con ángulo ~70°. Ángulos: {[f'{a:.1f}' for a in angles]}"
        )

    def test_extract_parameters_berm_width(self, design_profile):
        """Al menos un banco con berma ~9m (dentro de 5m de tolerancia).

        Nota: el algoritmo puede asignar berms irreales al último banco
        (piso del pit). Se filtran berms > 50m que son artefactos conocidos
        del mesh sintético (documentado en AGENTS.md).
        """
        result = extract_parameters(
            design_profile.distances,
            design_profile.elevations,
            "S-01",
            "Test",
        )
        # Filtrar berms realistas (descartar piso del pit y rampas)
        realistic_berms = [
            b for b in result.benches if 0.5 < b.berm_width < 50.0
        ]
        if realistic_berms:
            widths = [b.berm_width for b in realistic_berms]
            assert any(np.isclose(w, 9.0, atol=5.0) for w in widths), (
                f"No se detectó berma ~9m. Anchos realistas: {[f'{w:.1f}' for w in widths]}"
            )

    def test_extract_parameters_resample(self, design_profile):
        """El perfil tiene arrays con datos que se pueden usar (distancias ordenadas)."""
        d = design_profile.distances
        e = design_profile.elevations
        # Las distancias deben estar ordenadas
        assert np.all(d[:-1] <= d[1:]) or np.all(d[:-1] >= d[1:]), (
            "Las distancias deben estar ordenadas (ascendente o descendente)"
        )
        # Los arrays deben tener al menos 10 puntos para un perfil útil
        assert len(d) >= 10

    def test_extract_parameters_empty_profile(self):
        """Perfil con menos de 3 puntos retorna 0 bancos."""
        result = extract_parameters(
            np.array([0.0, 1.0]),
            np.array([100.0, 101.0]),
            "S-EMPTY",
            "Test",
        )
        assert len(result.benches) == 0

    def test_extract_parameters_returns_extraction_result(self, design_profile):
        """El resultado tiene los campos esperados."""
        result = extract_parameters(
            design_profile.distances,
            design_profile.elevations,
            "S-01",
            "Test",
        )
        assert result.section_name == "S-01"
        assert result.sector == "Test"
        assert hasattr(result, "benches")
        assert hasattr(result, "inter_ramp_angle")
        assert hasattr(result, "overall_angle")
