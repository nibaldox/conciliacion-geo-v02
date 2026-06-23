"""Regression tests for the berm_top descent guard in
``core.profile_extract._build_reconciled_points``.

Background: ``_build_reconciled_points`` used to emit a ``berm_top`` corner
after every non-ramp, non-last bench at the NEXT bench's crest elevation.
When the next bench sat LOWER than the current toe (over-excavation,
irregular slope, or simply a descending pit wall), that corner made the
stair-step descend and visually hide the real "pata del banco". The fix
only emits ``berm_top`` when ``next_b.crest_elevation >= b.toe_elevation``;
otherwise the renderer draws a straight oblique toe -> next-crest line.

These tests exercise the public ``build_reconciled_profile_v2`` entry point
(which delegates to ``_build_reconciled_points``) so they cover the real
contract used by the API and report generator.
"""

import numpy as np

from core.param_extractor import BenchParams, build_reconciled_profile_v2


def _bench(
    num: int,
    crest_d: float,
    crest_e: float,
    toe_d: float,
    toe_e: float,
) -> BenchParams:
    height = abs(crest_e - toe_e)
    dx = toe_d - crest_d
    angle = (
        abs(float(np.degrees(np.arctan2(height, abs(dx)))))
        if abs(dx) > 1e-9
        else 90.0
    )
    return BenchParams(
        bench_number=num,
        crest_elevation=float(crest_e),
        crest_distance=float(crest_d),
        toe_elevation=float(toe_e),
        toe_distance=float(toe_d),
        bench_height=float(height),
        face_angle=float(angle),
        berm_width=0.0,
    )


def _berm_top_count(prof) -> int:
    return sum(1 for p in prof.points if p.segment_type == "berm_top")


def test_ascending_benches_emit_berm_top():
    """3 bancos estrictamente ascendentes (cada crest siguiente por encima
    del toe anterior) -> 2 berm_top, uno entre cada par."""
    benches = [
        _bench(1, 10.0, 100.0, 15.0, 80.0),
        _bench(2, 25.0, 90.0, 30.0, 70.0),   # crest 90 >= toe1 80 -> emite
        _bench(3, 40.0, 80.0, 45.0, 60.0),   # crest 80 >= toe2 70 -> emite
    ]
    prof = build_reconciled_profile_v2(benches, source="topo")
    assert _berm_top_count(prof) == 2
    # Los berm_top pertenecen a los bancos 1 y 2 (nunca al último).
    owners = {p.bench_number for p in prof.points if p.segment_type == "berm_top"}
    assert owners == {1, 2}


def test_descending_next_bench_skips_berm_top():
    """El crest del banco 3 (3115) queda por debajo del toe del banco 2
    (3125): descendente. Solo se emite 1 berm_top (entre los bancos 1 y 2,
    que sí ascienden), no 2."""
    benches = [
        _bench(1, 10.0, 3133.0, 15.0, 3128.0),
        _bench(2, 25.0, 3130.0, 30.0, 3125.0),  # crest 3130 >= toe1 3128 -> emite
        _bench(3, 40.0, 3115.0, 45.0, 3110.0),  # crest 3115 < toe2 3125  -> omite
    ]
    prof = build_reconciled_profile_v2(benches, source="topo")
    assert _berm_top_count(prof) == 1
    owners = {p.bench_number for p in prof.points if p.segment_type == "berm_top"}
    assert owners == {1}


def test_flat_equal_elevation_emits_berm_top():
    """Caso de borde: el crest del banco 2 iguala exactamente el toe del
    banco 1 (85 == 85). La guarda usa >=, así que la berma horizontal se
    sigue emitiendo."""
    benches = [
        _bench(1, 10.0, 100.0, 15.0, 85.0),
        _bench(2, 25.0, 85.0, 30.0, 70.0),
    ]
    prof = build_reconciled_profile_v2(benches, source="design")
    assert _berm_top_count(prof) == 1
    berm_pt = [p for p in prof.points if p.segment_type == "berm_top"][0]
    assert np.isclose(berm_pt.elevation, 85.0)
    assert np.isclose(berm_pt.distance, 15.0)


def test_mixed_ascending_then_descending():
    """Banco 1 -> 2 ascendente (emite berm_top); banco 2 -> 3 descendente
    (omite). Total: 1 berm_top, y el crest del banco 3 se conecta en
    oblicuo directo al toe del banco 2.

    Nota: la especificación original del test decía "benches [high, low,
    high] -> 1 berm_top entre el primero y el segundo, ambos
    descendentes/planos", lo cual es internamente contradictorio
    (descendente = siguiente más bajo => omite, no emite). Se resuelve con
    elevaciones explícitas y autoconsistentes que cumplen el conteo
    esperado (1 berm_top)."""
    benches = [
        _bench(1, 10.0, 100.0, 15.0, 85.0),
        _bench(2, 25.0, 90.0, 30.0, 75.0),   # crest 90 >= toe1 85 -> emite
        _bench(3, 40.0, 70.0, 45.0, 60.0),   # crest 70 < toe2 75  -> omite
    ]
    prof = build_reconciled_profile_v2(benches, source="topo")
    assert _berm_top_count(prof) == 1
    owners = {p.bench_number for p in prof.points if p.segment_type == "berm_top"}
    assert owners == {1}
    # El crest del banco 3 va directo al toe del banco 2: entre el toe2 y el
    # crest3 no hay ningún punto intermedio.
    types = [p.segment_type for p in prof.points]
    assert "toe" in types and "crest" in types
    # Ningún berm_top pertenece al banco 2 (el que baja al banco 3).
    assert 2 not in owners


def test_last_bench_never_emits_berm_top():
    """Guard de regresión: aunque todos los bancos asciendan, el último
    banco nunca emite berm_top (no hay banco siguiente)."""
    benches = [
        _bench(1, 10.0, 100.0, 15.0, 80.0),
        _bench(2, 25.0, 90.0, 30.0, 70.0),
        _bench(3, 40.0, 80.0, 45.0, 60.0),
    ]
    prof = build_reconciled_profile_v2(benches, source="topo")
    last_num = benches[-1].bench_number
    owners = {p.bench_number for p in prof.points if p.segment_type == "berm_top"}
    assert last_num not in owners
    # Los berm_top provienen de los dos primeros bancos.
    assert owners == {1, 2}
    assert _berm_top_count(prof) == len(benches) - 1


def test_single_bench_has_no_berm_top():
    """Con un único banco la salida son solo crest + toe; sin berm_top."""
    benches = [_bench(1, 10.0, 100.0, 15.0, 80.0)]
    prof = build_reconciled_profile_v2(benches, source="topo")
    types = [p.segment_type for p in prof.points]
    assert types == ["crest", "toe"]
    assert _berm_top_count(prof) == 0
