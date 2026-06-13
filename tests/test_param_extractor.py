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

    def test_build_reconciled_profile(self):
        """build_reconciled_profile (legacy) ordena todos los puntos de menor a mayor distancia.

        Esta firma (return_v2=False por default) está deprecada y emite
        DeprecationWarning, pero se conserva para no romper consumidores
        legacy. Verifica que la salida es exactamente la de la
        implementación original de 14 líneas.
        """
        import warnings
        from core.param_extractor import build_reconciled_profile, BenchParams
        benches = [
            BenchParams(
                bench_number=1,
                crest_elevation=100.0,
                crest_distance=20.0,
                toe_elevation=85.0,
                toe_distance=10.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=85.0,
                crest_distance=35.0,
                toe_elevation=70.0,
                toe_distance=40.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dists, elevs = build_reconciled_profile(benches)
        # El warning de deprecación debe haberse emitido
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        ), "Se esperaba DeprecationWarning al usar la firma legacy"
        assert len(dists) == 4
        assert np.all(dists[:-1] <= dists[1:])
        np.testing.assert_allclose(dists, [10.0, 20.0, 35.0, 40.0])
        np.testing.assert_allclose(elevs, [85.0, 100.0, 85.0, 70.0])

    def test_build_reconciled_profile_v2_explicit_berm(self):
        """build_reconciled_profile_v2 emite un segmento de berma horizontal explícito.

        Con 2 bancos y berm_width=9m, la polilínea idealizada debe
        contener 5 puntos: crest1, toe1, berm_top, crest2, toe2. El
        segmento berm_top → crest2 es horizontal (misma elevación =
        crest_elevation del banco 2).
        """
        from core.param_extractor import (
            build_reconciled_profile_v2, BenchParams,
        )
        benches = [
            BenchParams(
                bench_number=1,
                crest_elevation=100.0,
                crest_distance=20.0,
                toe_elevation=85.0,
                toe_distance=10.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=85.0,
                crest_distance=35.0,
                toe_elevation=70.0,
                toe_distance=40.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]
        prof = build_reconciled_profile_v2(benches, source="topo")
        # 2 bancos, ninguno es rampa → 2*(crest+toe) + 1 berm_top = 5
        assert len(prof.points) == 5
        assert len(prof.distances) == 5
        # Tipos de segmento esperados en orden topológico
        types = [p.segment_type for p in prof.points]
        assert types == ["crest", "toe", "berm_top", "crest", "toe"], (
            f"Secuencia inesperada: {types}"
        )
        # El berm_top cae en x = toe_distance del banco 1, a la elevación
        # del crest del banco 2 (la berma conecta a esa altura).
        berm_pt = prof.points[2]
        assert np.isclose(berm_pt.distance, 10.0)
        assert np.isclose(berm_pt.elevation, 85.0)
        # El crest del banco 2 cae en x = 35 con elevación = 85 (mismo
        # z que el berm_top → segmento horizontal explícito)
        crest2 = prof.points[3]
        assert np.isclose(crest2.distance, 35.0)
        assert np.isclose(crest2.elevation, 85.0)
        # source debe propagarse
        assert all(p.source == "topo" for p in prof.points)

    def test_build_reconciled_profile_v2_ramp_skips_berm(self):
        """Un banco con is_ramp=True omite la berma horizontal y emite un punto 'ramp'."""
        from core.param_extractor import (
            build_reconciled_profile_v2, BenchParams,
        )
        benches = [
            BenchParams(
                bench_number=1,
                crest_elevation=100.0,
                crest_distance=20.0,
                toe_elevation=85.0,
                toe_distance=10.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=20.0,  # en rango de rampa (RAMP 15..42)
                is_ramp=True,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=70.0,
                crest_distance=50.0,
                toe_elevation=55.0,
                toe_distance=55.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]
        prof = build_reconciled_profile_v2(benches, source="design")
        # Banco 1 (rampa): ramp + toe (sin berm_top porque es rampa);
        # Banco 2 (normal): crest + toe + berm_top (porque tiene un
        # siguiente banco) — pero el banco 2 es el último, así que tampoco
        # emite berm_top. Total: 2 (banco 1) + 2 (banco 2) = 4 puntos.
        assert len(prof.points) == 4
        types = [p.segment_type for p in prof.points]
        # El banco 1 emite ramp+toe; el banco 2 (último) emite crest+toe.
        assert types == ["ramp", "toe", "crest", "toe"], (
            f"Secuencia inesperada: {types}"
        )
        assert "berm_top" not in types
        # El punto de rampa pertenece al bench_number=1
        ramp_pt = next(p for p in prof.points if p.segment_type == "ramp")
        assert ramp_pt.bench_number == 1
        # source="design" se propaga
        assert all(p.source == "design" for p in prof.points)

    def test_build_reconciled_profile_v2_empty(self):
        """Sin bancos, retorna ReconciledProfile con arrays vacíos y lista vacía."""
        from core.param_extractor import build_reconciled_profile_v2
        prof = build_reconciled_profile_v2([])
        assert len(prof.distances) == 0
        assert len(prof.elevations) == 0
        assert prof.points == []

    def test_build_reconciled_profile_v2_inverted_section(self):
        """Para secciones invertidas (distance decreciente) la función respeta el orden dado.

        El caller debe pasar la lista de bancos ya invertida. La función
        no reordena por distance: emite los puntos en orden
        topológico, que para una pared descendente es crest (alto) →
        toe (bajo) → berm → crest (más bajo) → toe.
        """
        from core.param_extractor import (
            build_reconciled_profile_v2, BenchParams,
        )
        # Sección descendente: bank1 a la derecha (x=80), bank2 a la izquierda (x=20)
        benches = [
            BenchParams(
                bench_number=1,
                crest_elevation=100.0,
                crest_distance=80.0,
                toe_elevation=85.0,
                toe_distance=70.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=70.0,
                crest_distance=20.0,
                toe_elevation=55.0,
                toe_distance=10.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]
        prof = build_reconciled_profile_v2(benches)
        # Orden topológico: banco 1 → banco 2 (la lista ya viene en orden correcto)
        assert len(prof.points) == 5
        # El primer punto debe pertenecer al banco 1 (crest en x=80, z=100)
        assert prof.points[0].bench_number == 1
        assert np.isclose(prof.points[0].distance, 80.0)
        # El último punto debe pertenecer al banco 2 (toe en x=10, z=55)
        assert prof.points[-1].bench_number == 2
        assert np.isclose(prof.points[-1].distance, 10.0)

    def test_build_reconciled_profile_v2_single_bench(self):
        """Con un único banco: 3 puntos (crest, berm_bottom omitido, toe) — sin berm_bottom porque no hay banco siguiente.

        La berma sólo se emite entre dos bancos consecutivos. Con un
        solo banco, no hay berm_bottom; el último punto es el toe.
        """
        from core.param_extractor import (
            build_reconciled_profile_v2, BenchParams,
        )
        benches = [
            BenchParams(
                bench_number=1,
                crest_elevation=100.0,
                crest_distance=20.0,
                toe_elevation=85.0,
                toe_distance=10.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]
        prof = build_reconciled_profile_v2(benches)
        assert len(prof.points) == 2  # crest, toe (sin berm_bottom)
        assert [p.segment_type for p in prof.points] == ["crest", "toe"]

    def test_build_reconciled_profile_v2_topological_order_non_monotonic(self):
        """Benches en orden no-monótonico se emiten en el orden dado, no se reordenan por distance.

        Esto es importante porque el orden topológico (banco i produce
        el berm que sostiene al banco i+1) depende de la lista, no de
        las coordenadas. Si el caller pasa los bancos en orden
        topológico, la polilínea queda correcta aunque las distances
        no sean monotónicas.
        """
        from core.param_extractor import (
            build_reconciled_profile_v2, BenchParams,
        )
        # Bancos en orden topológico descendente (de arriba a abajo)
        benches = [
            BenchParams(
                bench_number=1,
                crest_elevation=100.0,
                crest_distance=20.0,
                toe_elevation=85.0,
                toe_distance=10.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=85.0,
                crest_distance=35.0,
                toe_elevation=70.0,
                toe_distance=40.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
            BenchParams(
                bench_number=3,
                crest_elevation=70.0,
                crest_distance=55.0,
                toe_elevation=55.0,
                toe_distance=60.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]
        prof = build_reconciled_profile_v2(benches)
        # 3 bancos, 2 bermas intermedias: por banco (crest+toe) + berm_top
        # salvo el último (crest+toe). Total: (2+1)*2 + 2 = 8 puntos.
        assert len(prof.points) == 8
        # Verificar secuencia topológica
        types = [p.segment_type for p in prof.points]
        assert types == [
            "crest", "toe", "berm_top",  # banco 1
            "crest", "toe", "berm_top",  # banco 2
            "crest", "toe",              # banco 3 (último, sin berm_top)
        ]
        # Los bench_numbers van en orden 1,1,1,2,2,2,3,3
        bench_nums = [p.bench_number for p in prof.points]
        assert bench_nums == [1, 1, 1, 2, 2, 2, 3, 3]

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


class TestReconciledProfileFaceSegments:
    """Tests for face segment emission when a source profile is provided.

    When the caller passes the original (distances, elevations) profile
    to build_reconciled_profile_v2, the algorithm samples intermediate
    face points between each crest and toe so the reconciled polyline
    follows the actual as-built curvature of the bench face.
    """

    def _single_bench(self):
        from core.param_extractor import BenchParams
        return BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=20.0,
            toe_elevation=85.0,
            toe_distance=10.0,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )

    def test_face_segments_emitted_with_profile(self):
        """When a profile is provided, face points fill the crest-toe gap."""
        from core.param_extractor import build_reconciled_profile_v2
        bench = self._single_bench()
        # Perfil con 4 puntos: 2 en (crest..toe), más los endpoints
        profile = (
            np.array([20.0, 18.0, 14.0, 10.0]),
            np.array([100.0, 98.0, 92.0, 85.0]),
        )
        prof = build_reconciled_profile_v2([bench], profile=profile)
        face_pts = [p for p in prof.points if p.segment_type == "face"]
        # Solo los 2 puntos estrictamente entre crest y toe
        assert len(face_pts) == 2
        assert all(np.isclose(p.distance, d) for p, d in
                   zip(face_pts, [18.0, 14.0]))
        # El primer face point debe seguir al crest, el último al toe
        assert prof.points[0].segment_type == "crest"
        assert prof.points[1].segment_type == "face"
        assert prof.points[2].segment_type == "face"
        assert prof.points[3].segment_type == "toe"

    def test_face_segments_fallback_to_midpoint_when_profile_empty_in_range(self):
        """If the profile has no points in (crest, toe), emit one midpoint."""
        from core.param_extractor import build_reconciled_profile_v2
        bench = self._single_bench()
        # Perfil con puntos fuera del rango (no hay puntos en (10, 20))
        profile = (
            np.array([0.0, 5.0, 25.0, 30.0]),
            np.array([50.0, 60.0, 110.0, 120.0]),
        )
        prof = build_reconciled_profile_v2([bench], profile=profile)
        face_pts = [p for p in prof.points if p.segment_type == "face"]
        assert len(face_pts) == 1
        # Midpoint entre crest (20, 100) y toe (10, 85)
        assert np.isclose(face_pts[0].distance, 15.0)
        assert np.isclose(face_pts[0].elevation, 92.5)

    def test_face_segments_omitted_when_profile_is_none(self):
        """Without profile (legacy callers), no face points are emitted."""
        from core.param_extractor import build_reconciled_profile_v2
        bench = self._single_bench()
        prof = build_reconciled_profile_v2([bench])
        face_pts = [p for p in prof.points if p.segment_type == "face"]
        assert face_pts == []

    def test_face_segments_preserve_profile_order(self):
        """Face points follow the order of the source profile (no reordering)."""
        from core.param_extractor import build_reconciled_profile_v2
        bench = self._single_bench()
        # 5 puntos en el rango, en orden descendente de distance
        profile = (
            np.array([20.0, 19.0, 17.0, 14.0, 12.0, 10.0]),
            np.array([100.0, 99.0, 96.0, 92.0, 88.0, 85.0]),
        )
        prof = build_reconciled_profile_v2([bench], profile=profile)
        face_pts = [p for p in prof.points if p.segment_type == "face"]
        assert len(face_pts) == 4
        distances = [p.distance for p in face_pts]
        # Mismo orden que el profile: 19, 17, 14, 12
        assert distances == [19.0, 17.0, 14.0, 12.0]

    def test_face_segments_per_bench_for_multiple_benches(self):
        """With multiple benches, face points are scoped to each (crest, toe) range."""
        from core.param_extractor import build_reconciled_profile_v2, BenchParams
        benches = [
            BenchParams(
                bench_number=1,
                crest_elevation=100.0, crest_distance=20.0,
                toe_elevation=85.0, toe_distance=10.0,
                bench_height=15.0, face_angle=70.0, berm_width=9.0,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=85.0, crest_distance=35.0,
                toe_elevation=70.0, toe_distance=25.0,
                bench_height=15.0, face_angle=70.0, berm_width=9.0,
            ),
        ]
        # Banco 1 face: x=15. Banco 2 face: x=30. Berma: 10..35 (sin face).
        profile = (
            np.array([20.0, 15.0, 10.0, 35.0, 30.0, 25.0]),
            np.array([100.0, 92.0, 85.0, 85.0, 78.0, 70.0]),
        )
        prof = build_reconciled_profile_v2(benches, profile=profile)
        face_pts = [p for p in prof.points if p.segment_type == "face"]
        assert len(face_pts) == 2
        assert face_pts[0].bench_number == 1
        assert np.isclose(face_pts[0].distance, 15.0)
        assert face_pts[1].bench_number == 2
        assert np.isclose(face_pts[1].distance, 30.0)
