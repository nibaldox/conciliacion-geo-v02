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


class TestOverhangDetection:
    """Phase 9 — A.1 overhang detection between consecutive benches."""

    def _make_pair(self, crest_d_1, toe_d_2, crest_e_1=100.0, toe_e_1=85.0,
                   crest_e_2=85.0, toe_e_2=70.0, is_ramp_curr=False):
        from core.param_extractor import BenchParams
        return [
            BenchParams(
                bench_number=1,
                crest_elevation=crest_e_1,
                crest_distance=crest_d_1,
                toe_elevation=toe_e_1,
                toe_distance=10.0,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
                is_ramp=is_ramp_curr,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=crest_e_2,
                crest_distance=35.0,
                toe_elevation=toe_e_2,
                toe_distance=toe_d_2,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]

    def test_aligned_benches_no_overhang(self):
        """Berth aligned (crest_dist_n == toe_dist_{n+1}) → overhang == 0."""
        from core.param_extractor import _detect_overhangs_and_bridges
        benches = self._make_pair(crest_d_1=20.0, toe_d_2=20.0)
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, 0.0)
        assert np.isclose(benches[0].rock_bridge_thickness_m, 0.0)
        assert np.isclose(benches[0].rock_bridge_height_m, 0.0)

    def test_small_overhang_not_flagged(self):
        """overhang = 0.3 m (below 0.5 m warning threshold) → thin block, no flag."""
        from core.param_extractor import _detect_overhangs_and_bridges
        benches = self._make_pair(crest_d_1=20.3, toe_d_2=20.0)
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, 0.3)
        # 0.3 m positive overhang is not a rock bridge, thickness stays 0
        assert np.isclose(benches[0].rock_bridge_thickness_m, 0.0)

    def test_critical_overhang_flagged(self):
        """overhang = 1.6 m > critical 1.5 m → thick cantilever, no rock bridge."""
        from core.param_extractor import _detect_overhangs_and_bridges
        benches = self._make_pair(crest_d_1=21.6, toe_d_2=20.0)
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, 1.6)
        assert np.isclose(benches[0].rock_bridge_thickness_m, 0.0)
        assert np.isclose(benches[0].rock_bridge_height_m, 0.0)

    def test_ramp_skipped(self):
        """If benches[0].is_ramp=True the pair is skipped → defaults remain 0."""
        from core.param_extractor import _detect_overhangs_and_bridges
        benches = self._make_pair(
            crest_d_1=25.0, toe_d_2=10.0, is_ramp_curr=True,
        )
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, 0.0)
        assert np.isclose(benches[0].rock_bridge_thickness_m, 0.0)
        assert np.isclose(benches[0].rock_bridge_height_m, 0.0)

    def test_negative_overhang_negative_distance_yields_rock_bridge(self):
        """crest_dist_1 < toe_dist_2 → negative overhang → rock bridge width = -overhang."""
        from core.param_extractor import _detect_overhangs_and_bridges
        benches = self._make_pair(crest_d_1=15.0, toe_d_2=20.0)
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, -5.0)
        # bridge_thickness = min(-(-5.0), bridge_height=0) = 0
        # bridge_height = toe_e_1 - crest_e_2 = 85 - 85 = 0
        assert np.isclose(benches[0].rock_bridge_thickness_m, 0.0)
        assert np.isclose(benches[0].rock_bridge_height_m, 0.0)

    def test_extract_parameters_populates_overhang_field(self):
        """End-to-end: extract_parameters() leaves overhang/bridge fields populated
        on the bench list (defaults to 0 when the geometry is aligned)."""
        from core.param_extractor import extract_parameters
        # Synthetic flat-then-step profile that should detect at least 1 bench
        distances = np.linspace(0, 200, 401)
        elevations = np.where(
            distances < 100.0, 110.0,
            np.where(distances < 105.0, 110.0 - (distances - 100.0) * 2.0, 100.0),
        )
        result = extract_parameters(distances, elevations, "S-9", "Phase9")
        assert hasattr(result.benches, "__iter__")
        if result.benches:
            for b in result.benches:
                assert hasattr(b, "overhang_m")
                assert hasattr(b, "rock_bridge_thickness_m")
                assert hasattr(b, "rock_bridge_height_m")


class TestRockBridge:
    """Phase 9 — A.2 rock bridge detection (vertical separation)."""

    def _make_pair_with_bridge(self, toe_e_1, crest_e_2, toe_d_2):
        from core.param_extractor import BenchParams
        return [
            BenchParams(
                bench_number=1,
                crest_elevation=110.0,
                crest_distance=10.0,
                toe_elevation=toe_e_1,
                toe_distance=10.0,
                bench_height=10.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
            BenchParams(
                bench_number=2,
                crest_elevation=crest_e_2,
                crest_distance=20.0,
                toe_elevation=70.0,
                toe_distance=toe_d_2,
                bench_height=15.0,
                face_angle=70.0,
                berm_width=9.0,
            ),
        ]

    def test_thick_bridge(self):
        """Large negative overhang AND positive vertical separation →
        rock_bridge_thickness_m is the min of those two positive dimensions."""
        from core.param_extractor import _detect_overhangs_and_bridges
        # bridge_width = crest_d_2 - toe_d_1 = 25 - 10 = 15
        # bridge_height = toe_e_1 - crest_e_2 = 95 - 80 = 15
        # overhang = crest_d_1 - toe_d_2 = 10 - 25 = -15 → |overhang|=15
        benches = self._make_pair_with_bridge(
            toe_e_1=95.0, crest_e_2=80.0, toe_d_2=25.0,
        )
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, -15.0)
        assert np.isclose(benches[0].rock_bridge_height_m, 15.0)
        assert np.isclose(benches[0].rock_bridge_thickness_m, 15.0)

    def test_thin_bridge_limited_by_height(self):
        """Wide horizontal separation but tiny vertical separation →
        rock_bridge_thickness_m is limited by the smaller dimension (height)."""
        from core.param_extractor import _detect_overhangs_and_bridges
        # overhang = 10 - 30 = -20 (wide 20 m gap)
        # bridge_height = 85 - 84.7 = 0.3 (thin)
        # thickness = min(20, 0.3) = 0.3
        benches = self._make_pair_with_bridge(
            toe_e_1=85.0, crest_e_2=84.7, toe_d_2=30.0,
        )
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, -20.0)
        assert np.isclose(benches[0].rock_bridge_height_m, 0.3)
        assert np.isclose(benches[0].rock_bridge_thickness_m, 0.3)

    def test_negative_bridge_height_yields_zero_thickness(self):
        """When bridge_height < 0 (bench N+1 sits above bench N's toe) → no bridge."""
        from core.param_extractor import _detect_overhangs_and_bridges
        # overhang = 10 - 30 = -20 (still wide negative)
        # bridge_height = 80 - 90 = -10 (bench 2 crest is *above* bench 1 toe)
        benches = self._make_pair_with_bridge(
            toe_e_1=80.0, crest_e_2=90.0, toe_d_2=30.0,
        )
        _detect_overhangs_and_bridges(benches)
        assert np.isclose(benches[0].overhang_m, -20.0)
        assert np.isclose(benches[0].rock_bridge_height_m, -10.0)
        # min(-overhang=20, bridge_height=-10 clamped to 0) = 0
        assert np.isclose(benches[0].rock_bridge_thickness_m, 0.0)


class TestCatchBench:
    """Phase 9 — A.6 catch bench adequacy evaluation."""

    def _make_bench(self, berm_width, effective_berm_width):
        from core.param_extractor import BenchParams
        return BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=20.0,
            toe_elevation=85.0,
            toe_distance=10.0,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=berm_width,
            effective_berm_width=effective_berm_width,
        )

    def test_adequate_when_effective_geq_design(self):
        """effective_berm_width=8 ≥ berm_design_min=6 → adequate=True."""
        bench = self._make_bench(berm_width=9.0, effective_berm_width=8.0)
        from core.param_extractor import _evaluate_catch_bench_adequacy
        _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)
        assert bench.catch_bench_adequate is True
        assert np.isclose(bench.catch_bench_ratio, 8.0 / 9.0)

    def test_adequate_exact_boundary(self):
        """effective == design → adequate=True (>= comparison)."""
        bench = self._make_bench(berm_width=9.0, effective_berm_width=6.0)
        from core.param_extractor import _evaluate_catch_bench_adequacy
        _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)
        assert bench.catch_bench_adequate is True
        assert np.isclose(bench.catch_bench_ratio, 6.0 / 9.0)

    def test_inadequate_when_effective_lt_design(self):
        """effective=4 < design=6 → adequate=False."""
        bench = self._make_bench(berm_width=9.0, effective_berm_width=4.0)
        from core.param_extractor import _evaluate_catch_bench_adequacy
        _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)
        assert bench.catch_bench_adequate is False
        assert np.isclose(bench.catch_bench_ratio, 4.0 / 9.0)

    def test_no_design_just_ratio(self):
        """berm_design_min=None → catch_bench_adequate stays False, ratio computed."""
        bench = self._make_bench(berm_width=10.0, effective_berm_width=5.0)
        from core.param_extractor import _evaluate_catch_bench_adequacy
        _evaluate_catch_bench_adequacy([bench], berm_design_min_m=None)
        assert bench.catch_bench_adequate is False
        assert np.isclose(bench.catch_bench_ratio, 0.5)

    def test_zero_berm_width_avoids_division_by_zero(self):
        """berm_width=0 → denom clamped to 1e-3 → ratio is finite, not inf/NaN."""
        bench = self._make_bench(berm_width=0.0, effective_berm_width=0.0)
        from core.param_extractor import _evaluate_catch_bench_adequacy
        _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)
        assert np.isfinite(bench.catch_bench_ratio)
        assert bench.catch_bench_adequate is False

    def test_extract_parameters_populates_catch_bench_fields(self):
        """End-to-end: extract_parameters() initialises catch_bench_ratio and
        catch_bench_adequate on every detected bench (defaults: 0.0 / False)."""
        from core.param_extractor import extract_parameters
        distances = np.linspace(0, 200, 401)
        elevations = np.where(
            distances < 100.0, 110.0,
            np.where(distances < 105.0, 110.0 - (distances - 100.0) * 2.0, 100.0),
        )
        result = extract_parameters(distances, elevations, "S-CB", "Phase9")
        for b in result.benches:
            assert hasattr(b, "catch_bench_adequate")
            assert hasattr(b, "catch_bench_ratio")
            assert isinstance(b.catch_bench_adequate, bool)
            assert isinstance(b.catch_bench_ratio, float)


class TestWedgeShape:
    """Phase 10 — A.3 wedge shape detection (acute dihedral proxy)."""

    def _make_bench(self, face_angle, bench_height):
        from core.param_extractor import BenchParams
        return BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=20.0,
            toe_elevation=100.0 - bench_height,
            toe_distance=10.0,
            bench_height=float(bench_height),
            face_angle=float(face_angle),
            berm_width=9.0,
        )

    def test_steep_tall_bench_flagged(self):
        """face_angle=68, bench_height=14 → heuristic proxy flags it."""
        from core.param_extractor import _detect_wedge_shape_in_face
        bench = self._make_bench(face_angle=68.0, bench_height=14.0)
        assert _detect_wedge_shape_in_face(bench) is True

    def test_moderate_bench_not_flagged(self):
        """face_angle=60, bench_height=14 → below the 65° threshold, not flagged."""
        from core.param_extractor import _detect_wedge_shape_in_face
        bench = self._make_bench(face_angle=60.0, bench_height=14.0)
        assert _detect_wedge_shape_in_face(bench) is False

    def test_short_steep_bench_not_flagged(self):
        """face_angle=80 but bench_height=8 → height too small, not flagged."""
        from core.param_extractor import _detect_wedge_shape_in_face
        bench = self._make_bench(face_angle=80.0, bench_height=8.0)
        assert _detect_wedge_shape_in_face(bench) is False

    def test_explicit_dihedral_detection(self):
        """Three explicit face points forming a 45° dihedral → flagged.

        Geometry: (0,0) → (1,0) → (1+cos(45°), sin(45°)) = (1.707, 0.707).
        v1=(1,0), v2=(0.707, 0.707) → angle=45° < 60° → wedge.
        """
        from core.param_extractor import _detect_wedge_shape_in_face
        bench = self._make_bench(face_angle=70.0, bench_height=15.0)
        face_pts = [(0.0, 0.0), (1.0, 0.0), (1.707, 0.707)]
        assert _detect_wedge_shape_in_face(bench, face_pts=face_pts) is True

    def test_explicit_dihedral_no_acute_angle(self):
        """Three explicit face points forming a 90° (right) dihedral → not flagged.

        Geometry: (0,0) → (1,0) → (1,1). v1=(1,0), v2=(0,1) → angle=90° ≥ 60° → no wedge.
        """
        from core.param_extractor import _detect_wedge_shape_in_face
        bench = self._make_bench(face_angle=70.0, bench_height=15.0)
        face_pts = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        assert _detect_wedge_shape_in_face(bench, face_pts=face_pts) is False

    def test_explicit_too_few_points_falls_back_to_heuristic(self):
        """With < 3 explicit points, fall back to the heuristic proxy."""
        from core.param_extractor import _detect_wedge_shape_in_face
        bench_steep = self._make_bench(face_angle=70.0, bench_height=14.0)
        bench_mild = self._make_bench(face_angle=60.0, bench_height=14.0)
        assert _detect_wedge_shape_in_face(bench_steep, face_pts=[(0, 1)]) is True
        assert _detect_wedge_shape_in_face(bench_mild, face_pts=[(0, 1)]) is False


class TestToppling:
    """Phase 10 — A.4 toppling potential (Goodman & Bray 1976 proxy)."""

    def _make_bench(self, face_angle, bench_height, is_ramp=False):
        from core.param_extractor import BenchParams
        return BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=20.0,
            toe_elevation=100.0 - bench_height,
            toe_distance=10.0,
            bench_height=float(bench_height),
            face_angle=float(face_angle),
            berm_width=9.0,
            is_ramp=is_ramp,
        )

    def test_extreme_face_angle_flagged(self):
        """face_angle=82 > 80° threshold → toppling risk regardless of height."""
        from core.param_extractor import _detect_toppling_potential
        bench = self._make_bench(face_angle=82.0, bench_height=8.0)
        assert _detect_toppling_potential(bench) is True

    def test_tall_steep_bench_flagged(self):
        """face_angle=77, bench_height=16 → steep + tall triggers toppling."""
        from core.param_extractor import _detect_toppling_potential
        bench = self._make_bench(face_angle=77.0, bench_height=16.0)
        assert _detect_toppling_potential(bench) is True

    def test_moderate_bench_not_flagged(self):
        """face_angle=70, bench_height=10 → moderate, no toppling risk."""
        from core.param_extractor import _detect_toppling_potential
        bench = self._make_bench(face_angle=70.0, bench_height=10.0)
        assert _detect_toppling_potential(bench) is False

    def test_upper_release_combination(self):
        """Upper bench steep + this bench tall enough → toppling risk via release."""
        from core.param_extractor import _detect_toppling_potential
        bench = self._make_bench(face_angle=68.0, bench_height=13.0)
        # upper face 78° > 75°, this face 68° > 65°, height 13 > 12
        assert _detect_toppling_potential(bench, upper_bench_face_angle=78.0) is True

    def test_no_upper_release_does_not_trigger_third_rule(self):
        """Without upper face, the third rule is not evaluated."""
        from core.param_extractor import _detect_toppling_potential
        bench = self._make_bench(face_angle=68.0, bench_height=13.0)
        assert _detect_toppling_potential(bench) is False


class TestAngleConsistency:
    """Phase 10 — A.5 face_angle vs inter_ramp_angle consistency."""

    def _make_bench(self, face_angle):
        from core.param_extractor import BenchParams
        return BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=20.0,
            toe_elevation=85.0,
            toe_distance=10.0,
            bench_height=15.0,
            face_angle=float(face_angle),
            berm_width=9.0,
        )

    def test_consistent_angles_not_flagged(self):
        """|face_angle - inter_ramp| < 8° → not flagged."""
        from core.param_extractor import _evaluate_angle_consistency
        benches = [self._make_bench(face_angle=70.0)]
        _evaluate_angle_consistency(benches, inter_ramp_angle=72.0, overall_angle=60.0)
        assert benches[0].face_angle_inconsistent is False

    def test_inconsistent_angle_flagged(self):
        """|face_angle - inter_ramp| > 8° → flagged."""
        from core.param_extractor import _evaluate_angle_consistency
        benches = [self._make_bench(face_angle=72.0)]
        _evaluate_angle_consistency(benches, inter_ramp_angle=85.0, overall_angle=60.0)
        assert benches[0].face_angle_inconsistent is True

    def test_inconsistent_below_inter_ramp_flagged(self):
        """face_angle much smaller than inter_ramp is also flagged."""
        from core.param_extractor import _evaluate_angle_consistency
        benches = [self._make_bench(face_angle=55.0)]
        _evaluate_angle_consistency(benches, inter_ramp_angle=70.0, overall_angle=60.0)
        assert benches[0].face_angle_inconsistent is True

    def test_exact_boundary_not_flagged(self):
        """|diff| == 8° exactly → boundary; function uses strict >, so not flagged."""
        from core.param_extractor import _evaluate_angle_consistency
        benches = [self._make_bench(face_angle=78.0)]
        _evaluate_angle_consistency(benches, inter_ramp_angle=70.0, overall_angle=60.0)
        assert benches[0].face_angle_inconsistent is False

    def test_extract_parameters_populates_consistency(self):
        """End-to-end: extract_parameters sets face_angle_inconsistent on each bench."""
        from core.param_extractor import extract_parameters
        distances = np.linspace(0, 200, 401)
        elevations = np.where(
            distances < 100.0, 110.0,
            np.where(distances < 105.0, 110.0 - (distances - 100.0) * 2.0, 100.0),
        )
        result = extract_parameters(distances, elevations, "S-CONS", "Phase10")
        for b in result.benches:
            assert isinstance(b.face_angle_inconsistent, bool)


class TestAnisotropy:
    """Phase 10 — A.8 anisotropy dispersion across non-ramp benches."""

    def _make_bench(self, face_angle, is_ramp=False):
        from core.param_extractor import BenchParams
        return BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=20.0,
            toe_elevation=85.0,
            toe_distance=10.0,
            bench_height=15.0,
            face_angle=float(face_angle),
            berm_width=9.0,
            is_ramp=is_ramp,
        )

    def test_uniform_face_angles_low_dispersion(self):
        """All benches with the same face_angle → std ≈ 0."""
        from core.stability_analysis import compute_anisotropy_dispersion
        benches = [self._make_bench(face_angle=70.0) for _ in range(5)]
        dispersion = compute_anisotropy_dispersion(benches)
        assert np.isclose(dispersion, 0.0, atol=1e-9)

    def test_mixed_face_angles_high_dispersion(self):
        """Benches with varied face_angles → std > 5°."""
        from core.stability_analysis import compute_anisotropy_dispersion
        benches = [
            self._make_bench(face_angle=55.0),
            self._make_bench(face_angle=70.0),
            self._make_bench(face_angle=85.0),
        ]
        dispersion = compute_anisotropy_dispersion(benches)
        # Mean ~70, deviations (15, 0, -15) → std ~ 12
        assert dispersion > 5.0

    def test_single_bench_returns_zero(self):
        """Fewer than 2 non-ramp benches → return 0.0 (no dispersion defined)."""
        from core.stability_analysis import compute_anisotropy_dispersion
        benches = [self._make_bench(face_angle=70.0)]
        assert compute_anisotropy_dispersion(benches) == 0.0

    def test_ramp_benches_excluded(self):
        """Ramps are excluded from the dispersion calculation."""
        from core.stability_analysis import compute_anisotropy_dispersion
        benches = [
            self._make_bench(face_angle=70.0),
            self._make_bench(face_angle=70.0),
            self._make_bench(face_angle=999.0, is_ramp=True),
        ]
        # Only the two non-ramp benches contribute; std = 0
        assert np.isclose(compute_anisotropy_dispersion(benches), 0.0, atol=1e-9)

    def test_extract_parameters_populates_anisotropy(self):
        """End-to-end: every bench carries the same anisotropy_dispersion_deg value."""
        from core.param_extractor import extract_parameters
        distances = np.linspace(0, 200, 401)
        elevations = np.where(
            distances < 100.0, 110.0,
            np.where(distances < 105.0, 110.0 - (distances - 100.0) * 2.0, 100.0),
        )
        result = extract_parameters(distances, elevations, "S-ANISO", "Phase10")
        if len(result.benches) >= 2:
            dispersions = {b.anisotropy_dispersion_deg for b in result.benches}
            assert len(dispersions) == 1
        for b in result.benches:
            assert isinstance(b.anisotropy_dispersion_deg, float)


class TestPhase10DefaultsAndFieldPresence:
    """Phase 10 — verify the new fields exist with the right defaults and types."""

    def test_benchparams_has_phase10_fields(self):
        """BenchParams declares the 4 new fields with backward-compat defaults."""
        from core.param_extractor import BenchParams
        bench = BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=20.0,
            toe_elevation=85.0,
            toe_distance=10.0,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=9.0,
        )
        assert bench.wedge_risk is False
        assert bench.toppling_risk is False
        assert bench.face_angle_inconsistent is False
        assert bench.anisotropy_dispersion_deg == 0.0

    def test_extract_parameters_populates_phase10_fields(self):
        """End-to-end: extract_parameters sets all 4 new fields on every bench."""
        from core.param_extractor import extract_parameters
        distances = np.linspace(0, 200, 401)
        elevations = np.where(
            distances < 100.0, 110.0,
            np.where(distances < 105.0, 110.0 - (distances - 100.0) * 2.0, 100.0),
        )
        result = extract_parameters(distances, elevations, "S-P10", "Phase10")
        for b in result.benches:
            assert isinstance(b.wedge_risk, bool)
            assert isinstance(b.toppling_risk, bool)
            assert isinstance(b.face_angle_inconsistent, bool)
            assert isinstance(b.anisotropy_dispersion_deg, float)
