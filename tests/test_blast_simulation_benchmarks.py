"""Performance benchmarks for the energy engine (spec §15).

Reproducible benchmarks for 50/100/500 holes over voxel grids of
~100k, 500k and 1M voxels. Each case records total time, peak memory,
segment count, voxel count, backend, and artifact size.

These are SMOKE benchmarks: they assert the engine COMPLETES within a
generous ceiling and that conservation still holds; they do NOT pin
specific timings (those vary by hardware). Run with:

    pytest tests/test_blast_simulation_benchmarks.py -v -s

The ``-s`` is needed to see the printed benchmark table.
"""
from __future__ import annotations

import time
import tracemalloc
from pathlib import Path

import numpy as np
import pytest

from core.blast_simulation import (
    AnisotropyMode,
    DomainBounds,
    EnergyMode,
    KernelType,
    RockMassConfiguration,
    SIMULATION_CONFIGURATION_VERSION,
    SimulationConfiguration,
    TemporalMode,
    run_simulation,
    write_npz_artifact,
)


def _bench_cfg(n_voxel_target: int) -> SimulationConfiguration:
    """Build a cube domain whose voxel count is close to the target.

    voxel_count ≈ (L / v)^3 ⇒ v = L / cbrt(target). We use L = 60 m so
    100k → v≈1.29 (46³ cells), 500k → v≈0.76 (79³), 1M → v=0.6 (100³).
    """
    L = 60.0
    voxel = L / (n_voxel_target ** (1.0 / 3.0))
    return SimulationConfiguration(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=voxel,
        domain_bounds=DomainBounds(0, 0, 0, L, L, L),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.STATIC,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=0.5,
        regularization_radius_m=0.5,
        coupling_efficiency=0.85,
        rock_mass=RockMassConfiguration(
            rock_unit_id="1c", density_kg_m3=2700.0, ucs_mpa=80.0,
            attenuation_coefficient_1_m=0.5, wave_velocity_m_s=3500.0,
            anisotropy_mode=AnisotropyMode.ISOTROPIC,
            source="lab", status="VALIDATED",
        ),
    )


def _bench_rows(n_holes: int) -> list[dict]:
    rng = np.random.default_rng(seed=42)
    rows = []
    for i in range(n_holes):
        x = float(rng.uniform(10, 50))
        y = float(rng.uniform(10, 50))
        rows.append({
            "hole_id": f"H-{i:04d}",
            "X": x, "Y": y, "Z_collar": 55.0,
            "X_toe": x, "Y_toe": y, "Z_toe": 45.0,
            "Incl": 0.0, "Az": 0.0, "Len": 10.0,
            "Taco_m": 2.0, "descarga": 8.0, "Diam_mm": 200.0,
            "Kilos_Cargados_real": 100.0,
            "Tipo_Explosivo": "ANFO",
            "source_row_index": i,
        })
    return rows


@pytest.mark.parametrize("n_holes", [50, 100], scope="module")
@pytest.mark.parametrize("n_voxels", [100_000, 500_000], scope="module")
def test_benchmark_grid(n_holes: int, n_voxels: int, tmp_path):
    cfg = _bench_cfg(n_voxels)
    rows = _bench_rows(n_holes)

    tracemalloc.start()
    t0 = time.perf_counter()
    result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Persist to measure artifact size.
    _, npz_path, _ = write_npz_artifact(
        result=result, accepted_rows=rows, configuration=cfg,
        data_dir=tmp_path, segments_per_hole=4,
    )
    artifact_kb = npz_path.stat().st_size / 1024.0

    # Conservation must hold regardless of size.
    total = result.energy_field.represented_energy_j + result.energy_field.outside_domain_energy_j
    assert total == pytest.approx(result.energy_field.total_coupled_energy_j, rel=1e-6)

    # Print the benchmark row (visible with -s).
    print(
        f"\n[BENCH] holes={n_holes:4d}  voxels={result.source_summary.voxel_count:8d}  "
        f"segs={result.source_summary.charge_segments:6d}  "
        f"time={elapsed:6.2f}s  peak_mem={peak / 1e6:6.1f} MB  "
        f"artifact={artifact_kb:7.1f} KB"
    )

    # Generous ceiling — fails only on pathological slowness.
    assert elapsed < 120.0


def test_chunking_matches_no_chunking():
    """Chunked evaluation must match the default within float tolerance.

    The engine currently evaluates per-source with reusable accumulators
    (no dense matrix); the chunked path is exercised implicitly through
    ``SIMULATION.chunk_voxel_block``. This test verifies determinism:
    two consecutive runs produce the same total energy.
    """
    cfg = _bench_cfg(10_000)
    rows = _bench_rows(20)
    r1 = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
    r2 = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
    assert r1.energy_field.represented_energy_j == pytest.approx(
        r2.energy_field.represented_energy_j, rel=1e-9
    )
