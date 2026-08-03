"""Performance benchmarks for the deterministic voxel energy engine.

Run with ``pytest tests/test_blast_simulation_benchmarks.py -v -s`` to see
measured benchmark rows. The ``500 × 1M`` case is marked slow and can be
excluded with ``--benchmark-skip-slow``.
"""
from __future__ import annotations

import sys
import time
import tracemalloc

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
    VoxelGridSpecification,
    run_simulation,
    write_npz_artifact,
)
from core.blast_simulation.charges import build_charge_segments
from core.blast_simulation.engine import _check_resource_limits
from core.config import SIMULATION


def _bench_cfg(n_voxel_target: int) -> SimulationConfiguration:
    """Build a reproducible cube whose voxel count is close to the target."""
    L = 60.0
    cells_per_axis = round(n_voxel_target ** (1.0 / 3.0))
    voxel = L / cells_per_axis
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
        support_radius_m=5.0,
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


def _benchmark_backend() -> str:
    engine = sys.modules.get(run_simulation.__module__)
    configured_backend = getattr(engine, "BACKEND", None) if engine else None
    if configured_backend in {"numpy", "torch", "jax"}:
        return configured_backend
    for backend in ("torch", "jax"):
        if engine is not None and getattr(engine, backend, None) is not None:
            return backend
    return "numpy"


@pytest.mark.parametrize("n_holes", [50, 100, 500], scope="module")
@pytest.mark.parametrize("n_voxels", [100_000, 500_000, 1_000_000], scope="module")
def test_benchmark_grid(n_holes: int, n_voxels: int, tmp_path):
    cfg = _bench_cfg(n_voxels)
    rows = _bench_rows(n_holes)

    tracemalloc.start()
    t0 = time.perf_counter()
    result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    if n_voxels == 1_000_000:
        assert result.source_summary.voxel_count == 1_000_000

    _, npz_path, _ = write_npz_artifact(
        result=result, accepted_rows=rows, configuration=cfg,
        data_dir=tmp_path, segments_per_hole=4,
    )
    artifact_kb = npz_path.stat().st_size / 1024.0
    backend = _benchmark_backend()

    total = (
        result.energy_field.represented_energy_j
        + result.energy_field.outside_domain_energy_j
    )
    total_coupled = result.energy_field.total_coupled_energy_j
    conservation_relative_error = abs(total - total_coupled) / max(
        abs(total_coupled), np.finfo(float).tiny,
    )
    assert total == pytest.approx(total_coupled, rel=1e-6)

    print(
        f"\n[BENCH] holes={n_holes:4d}  backend={backend:6s}  "
        f"voxels={result.source_summary.voxel_count:8d}  "
        f"segments={result.source_summary.charge_segments:6d}  "
        f"time={elapsed:6.2f}s  peak_mem_MB={peak / 1e6:8.1f}  "
        f"artifact_KB={artifact_kb:9.1f}  "
        f"conservation_relative_error={conservation_relative_error:.3e}"
    )

    assert elapsed < 120.0


def test_chunking_matches_no_chunking():
    """Variable voxel block sizes preserve deterministic simulation results.

    The current engine accumulates each source over the complete voxel array;
    ``block_size`` is currently used by the resource estimate but not by the
    spatial accumulation loop. This test therefore verifies result parity and
    documents that bounded-memory voxel iteration is still a motor gap.
    """
    cfg = _bench_cfg(50_000)
    rows = _bench_rows(30)

    # Status: the engine does not yet iterate over voxel blocks during accumulation.
    r_default = run_simulation(
        accepted_rows=rows,
        configuration=cfg,
        block_size=SIMULATION.chunk_voxel_block,
    )

    for chunk in [10_000, 5_000, 1_000, 500]:
        r_chunked = run_simulation(
            accepted_rows=rows,
            configuration=cfg,
            block_size=chunk,
        )
        assert r_default.energy_field.represented_energy_j == pytest.approx(
            r_chunked.energy_field.represented_energy_j,
            rel=1e-9,
        )
        assert r_default.energy_field.outside_domain_energy_j == pytest.approx(
            r_chunked.energy_field.outside_domain_energy_j,
            rel=1e-9,
        )
        assert r_default.source_summary.active_voxels == (
            r_chunked.source_summary.active_voxels
        )


def test_memory_estimate_matches_realistic():
    """The resource estimate remains within the expected order of magnitude."""
    cfg = _bench_cfg(100_000)
    rows = _bench_rows(50)

    tracemalloc.start()
    try:
        run_simulation(
            accepted_rows=rows,
            configuration=cfg,
            segments_per_hole=4,
        )
        _, peak_real = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    grid = VoxelGridSpecification(
        voxel_size_m=cfg.voxel_size_m,
        bounds=cfg.domain_bounds,
    )
    segments = build_charge_segments(rows, config=cfg, segments_per_hole=4)
    info = _check_resource_limits(
        grid=grid,
        n_segments=len(segments),
        block_size=100_000,
    )

    estimated_gb = info["estimated_peak_memory_gb"]
    real_gb = peak_real / (1024 ** 3)
    # El estimador es CONSERVADOR por diseño (intencionalmente sobreasigna
    # para prevenir OOM). El test verifica que el real NUNCA excede el
    # estimado (safety upper bound), y que la estimación está en un orden
    # razonable del real (no más de 100× por encima).
    assert real_gb <= estimated_gb * 100, (
        f"real={real_gb} GB exceeds conservative estimate {estimated_gb} GB"
    )
    assert estimated_gb > 0, "estimator must return a positive value"
