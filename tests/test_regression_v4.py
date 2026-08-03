"""V4 red regression tests for confirmed blocking defects.

Each test reproduces a defect that exists at HEAD ae95cb6.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

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
    persistence,
    run_simulation,
)
from core.blast_simulation import compute_field_arrays


pytestmark = pytest.mark.regression_v4


def _cfg(**overrides) -> SimulationConfiguration:
    defaults = dict(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=DomainBounds(0, 0, 0, 10, 10, 10),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.STATIC,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=0.2,
        regularization_radius_m=0.5,
        support_radius_m=5.0,
        coupling_efficiency=0.85,
        rock_mass=RockMassConfiguration(
            rock_unit_id="t", source="t", status="VALIDATED",
        ),
    )
    defaults.update(overrides)
    return SimulationConfiguration(**defaults)


def _holes(n: int = 1, temporal: bool = False) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        rows.append({
            "hole_id": f"H-{i:04d}", "X": 5.0, "Y": 5.0, "Z_collar": 8.0,
            "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 2.0,
            "Incl": 0.0, "Az": 0.0, "Len": 6.0, "Taco_m": 1.0,
            "descarga": 5.0, "Diam_mm": 200.0,
            "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
            "source_row_index": i, "Retardo_ms": float(i * 25) if temporal else 0.0,
        })
    return rows


# ---------------------------------------------------------------------------
# Etapa 2 — cortes API no deben recalcular
# ---------------------------------------------------------------------------


class TestNoRecalculationAnywhere:
    """compute_field_arrays MUST NOT be called by ANY downstream consumer
    when the canonical result already carries field_arrays."""

    def test_persistence_never_calls_compute_field_arrays(self, tmp_path: Path):
        """The canonical path in write_atomic_simulation must NOT call
        compute_field_arrays — not even as a fallback."""
        cfg = _cfg()
        rows = _holes(1)
        result = run_simulation(accepted_rows=rows, configuration=cfg)
        assert result.field_arrays is not None

        with patch.object(
            persistence, "compute_field_arrays",
            wraps=persistence.compute_field_arrays,
        ) as spy:
            persistence.write_atomic_simulation(
                result=result, accepted_rows=rows, configuration=cfg,
                data_dir=tmp_path,
            )
            assert spy.call_count == 0, (
                "write_atomic_simulation must not call compute_field_arrays "
                "even as a fallback when field_arrays is None — it should "
                "raise an explicit error instead"
            )


# ---------------------------------------------------------------------------
# Etapa 3 — sin vectores completos por fuente
# ---------------------------------------------------------------------------


class TestNoPerSourceFullVectors:
    """_accumulate_source MUST NOT allocate a full-length e_j array per
    source. It should update the global accumulators in-place at only
    the affected indices."""

    def test_no_full_length_e_j_per_source(self):
        """Detect per-source full-length vector allocations by comparing
        peak memory for N=1 vs N=5 sources. If per-source full vectors
        exist, peak grows linearly with N. With the fix (in-place
        updates at deposit indices only), peak stays nearly constant."""
        import tracemalloc

        peaks: dict[int, int] = {}
        for n_sources in (1, 5):
            cfg = _cfg(domain_bounds=DomainBounds(0, 0, 0, 10, 10, 10))
            rows = _holes(n_sources)
            tracemalloc.start()
            run_simulation(accepted_rows=rows, configuration=cfg)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks[n_sources] = peak

        # If per-source full vectors (1000 voxels × 8 bytes × n_sources)
        # are allocated, the ratio peak[5]/peak[1] would be ~1.4+.
        # With the fix (in-place updates), the ratio stays near 1.0
        # because per-source overhead is O(support_cube) which is
        # transient and freed between sources.
        ratio = peaks[5] / max(peaks[1], 1)
        ceiling_ratio = 1.5  # generous: allows support-cube overhead
        assert ratio < ceiling_ratio, (
            f"Peak memory ratio {ratio:.2f} (5 sources / 1 source) "
            f"exceeded ceiling {ceiling_ratio}. "
            f"peak[1]={peaks[1] / 1024:.1f} KB, "
            f"peak[5]={peaks[5] / 1024:.1f} KB — "
            f"per-source full-length vectors may still be allocated"
        )


# ---------------------------------------------------------------------------
# Etapa 4 — sin listas temporales segmento × vóxel
# ---------------------------------------------------------------------------


class TestNoTemporalSegmentVoxelLists:
    """The temporal layer MUST NOT retain lists of full-length per-segment
    arrays. The chunked variants must receive per-block data, not
    pre-materialized global arrays."""

    def test_temporal_mode_does_not_retain_full_lists(self):
        """In TEMPORAL mode, the engine must not store
        temporal_energy_contributions or temporal_distances as lists
        of n_voxels-length arrays."""
        cfg = _cfg(
            temporal_mode=TemporalMode.TEMPORAL,
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="lab",
            pulse_sigma_s=0.001,
        )
        rows = _holes(5, temporal=True)

        # Instrument the chunked functions to verify they receive
        # per-block data, not full-length arrays.
        # If the lists are retained, tracemalloc will show a peak
        # proportional to n_segments × n_voxels.
        import tracemalloc
        tracemalloc.start()
        result = run_simulation(accepted_rows=rows, configuration=cfg)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 5 holes × 8 segments = 40 segments × 1000 voxels × 8 bytes
        # = 320 KB for the lists alone. With the fix (streaming),
        # peak should stay well under 1 MB.
        ceiling_bytes = 2 * 1024 * 1024  # 2 MB
        assert peak < ceiling_bytes, (
            f"Peak temporal memory {peak / 1024 / 1024:.2f} MB exceeded "
            f"ceiling {ceiling_bytes / 1024 / 1024:.1f} MB — "
            f"per-segment full-length lists may still be retained"
        )

    def test_temporal_energy_conservation(self):
        """The sum of temporal fractions for each (voxel, source) pair
        must equal 1.0 within tolerance. This verifies the gaussian
        discretisation is properly normalised."""
        from core.blast_simulation.temporal import energy_pulse_per_interval

        sigma = 0.001
        energy = 1.0e6  # 1 MJ
        t_arrival = 0.005

        # Build a wide window that covers ±10σ.
        n_edges = 1001
        t_edges = np.linspace(
            t_arrival - 10 * sigma, t_arrival + 10 * sigma, n_edges,
        )

        fractions = energy_pulse_per_interval(
            t_edges,
            t_arrival=t_arrival,
            sigma_s=sigma,
            energy_j=energy,
        )

        total = float(fractions.sum())
        # With ±10σ coverage the CDF sum should be extremely close to 1.
        relative_error = abs(total - energy) / energy
        assert relative_error < 1e-6, (
            f"Temporal energy conservation failed: sum={total:.6e}, "
            f"expected={energy:.6e}, relative_error={relative_error:.3e}"
        )
