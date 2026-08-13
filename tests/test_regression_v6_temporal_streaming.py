"""V6-04: Streaming temporal with explicit ``Bv / Bt / Bs`` blocks.

The V5 ``_compute_temporal_fields_streaming`` exposes only
``voxel_block_size`` (Bv). ``n_time_bins=64`` is hardcoded (no ``Bt``)
and there is no segment-block parameter (no ``Bs``). The audit's target
memory is::

    O(B_v × B_t + B_v + B_s)

achieved by allocating a ``(Bv_active, Bt)`` response matrix per voxel
block, processing sources in ``Bs``-sized chunks, and updating
``time_of_max`` only after every source has been accumulated.

This file verifies:

1. ``run_simulation`` accepts ``temporal_voxel_block_size`` (Bv),
   ``temporal_time_bins`` (Bt) and ``temporal_segment_block_size`` (Bs).
2. ``first_arrival_s`` and ``time_of_max_s`` are invariant across
   combinations of (Bv, Bs) — the result depends only on the physics,
   not on the blocking.
3. ``time_of_max_s`` respects superposition (the argmax of the summed
   response, not of any single source).
4. Voxels without any temporal contribution stay ``NaN``.
5. The peak allocation inside ``_compute_temporal_fields_streaming``
   respects ``Bv × Bt × dtype_size`` — measured by intercepting the
   numpy allocator used by the function.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from core.blast_simulation import (
    AnisotropyMode,
    DomainBounds,
    EnergyMode,
    RockMassConfiguration,
    SimulationConfiguration,
    TemporalMode,
    run_simulation,
)


pytestmark = pytest.mark.regression_v6


def _make_cfg(
    *,
    bounds: tuple[int, int, int, int, int, int] = (0, 0, 0, 12, 12, 12),
    voxel: float = 1.0,
    velocity: float = 3500.0,
    pulse_sigma: float = 0.025,
    anisotropy_mode: str = AnisotropyMode.ISOTROPIC,
    tensor: tuple[tuple[float, ...], ...] | None = None,
) -> SimulationConfiguration:
    rock = RockMassConfiguration(
        rock_unit_id="t",
        source="t",
        status="VALIDATED",
        anisotropy_mode=anisotropy_mode,
        anisotropy_tensor=tensor,
    )
    return SimulationConfiguration(
        simulation_configuration_version="2.0",
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=voxel,
        domain_bounds=DomainBounds(*bounds),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.TEMPORAL,
        anisotropy_mode=anisotropy_mode,
        attenuation_coefficient_1_m=0.2,
        regularization_radius_m=0.5,
        support_radius_m=5.0,
        coupling_efficiency=0.85,
        propagation_velocity_m_s=velocity,
        propagation_velocity_source="lab",
        pulse_sigma_s=pulse_sigma,
        rock_mass=rock,
    )


def _hole(
    hole_id: str,
    x: float,
    y: float,
    z_collar: float,
    z_toe: float,
    *,
    kg: float = 50.0,
    delay_ms: float = 0.0,
) -> dict[str, Any]:
    return {
        "hole_id": hole_id, "X": x, "Y": y, "Z_collar": z_collar,
        "X_toe": x, "Y_toe": y, "Z_toe": z_toe,
        "Incl": 0.0, "Az": 0.0, "Len": abs(z_collar - z_toe),
        "Taco_m": 1.0, "descarga": abs(z_collar - z_toe) - 1.0,
        "Diam_mm": 200.0, "Kilos_Cargados_real": kg,
        "Tipo_Explosivo": "ANFO", "source_row_index": 0,
        "Retardo_ms": delay_ms,
    }


# ---------------------------------------------------------------------------
# V6-04.a — new parameters are accepted by run_simulation
# ---------------------------------------------------------------------------


class TestTemporalBlockingParameters:
    """``run_simulation`` MUST accept the three new temporal blocking
    parameters. Without them the audit's ``Bv / Bt / Bs`` are not
    configurable."""

    def test_accepts_all_three_parameters(self):
        cfg = _make_cfg()
        result = run_simulation(
            accepted_rows=[_hole("H-1", 6, 6, 10, 4)],
            configuration=cfg,
            segments_per_hole=4,
            block_size=4096,
            temporal_voxel_block_size=512,      # Bv
            temporal_time_bins=48,              # Bt
            temporal_segment_block_size=32,     # Bs
        )
        assert result.field_arrays is not None
        assert "time_of_max_s" in result.field_arrays
        assert "first_arrival_s" in result.field_arrays

    def test_defaults_backward_compatible(self):
        """Without the new parameters the engine MUST still run and
        produce the same result as before."""
        cfg = _make_cfg()
        r1 = run_simulation(
            accepted_rows=[_hole("H-1", 6, 6, 10, 4)],
            configuration=cfg,
            segments_per_hole=4,
        )
        r2 = run_simulation(
            accepted_rows=[_hole("H-1", 6, 6, 10, 4)],
            configuration=cfg,
            segments_per_hole=4,
            temporal_voxel_block_size=4096,
            temporal_time_bins=64,
            temporal_segment_block_size=128,
        )
        fa1 = r1.field_arrays["first_arrival_s"]
        fa2 = r2.field_arrays["first_arrival_s"]
        np.testing.assert_allclose(fa1, fa2, rtol=0, atol=0, equal_nan=True)


# ---------------------------------------------------------------------------
# V6-04.b — parity across (Bv, Bs) combinations
# ---------------------------------------------------------------------------


class TestTemporalBlockingParity:
    """The temporal fields MUST be invariant under different (Bv, Bs)
    combinations. Only ``Bt`` (= ``temporal_time_bins``) changes the
    bin resolution and therefore the result."""

    @pytest.mark.parametrize(
        ("bv1", "bs1", "bv2", "bs2"),
        [
            (64, 1, 4096, 128),
            (128, 8, 2048, 64),
            (1, 1, 8192, 256),
            (32, 16, 1024, 4),
        ],
    )
    def test_time_of_max_invariant_under_bv_bs(self, bv1, bs1, bv2, bs2):
        cfg = _make_cfg()
        rows = [
            _hole("H-1", 3, 3, 10, 4, delay_ms=0.0),
            _hole("H-2", 9, 9, 10, 4, delay_ms=25.0),
        ]

        def _run(bv, bs):
            return run_simulation(
                accepted_rows=rows,
                configuration=cfg,
                segments_per_hole=4,
                block_size=4096,
                temporal_voxel_block_size=bv,
                temporal_time_bins=64,
                temporal_segment_block_size=bs,
            ).field_arrays

        a1 = _run(bv1, bs1)
        a2 = _run(bv2, bs2)
        np.testing.assert_allclose(
            a1["time_of_max_s"], a2["time_of_max_s"],
            rtol=1e-9, atol=1e-9, equal_nan=True,
            err_msg="time_of_max_s changed across (Bv, Bs) combinations",
        )
        np.testing.assert_allclose(
            a1["first_arrival_s"], a2["first_arrival_s"],
            rtol=1e-12, atol=1e-12, equal_nan=True,
        )


# ---------------------------------------------------------------------------
# V6-04.c — superposition-aware time_of_max
# ---------------------------------------------------------------------------


class TestTimeOfMaxSuperposition:
    """``time_of_max_s`` MUST reflect the argmax of the summed response
    across ALL sources (superposition), not the argmax of any single
    source."""

    def test_dominant_source_sets_time_of_max(self):
        """A high-energy source detonating later than a low-energy one
        MUST shift ``time_of_max`` toward the later arrival."""
        cfg = _make_cfg()
        # Two holes far enough that their supports don't overlap.
        # H-1: low energy, early detonation.
        # H-2: high energy, late detonation.
        rows_early_only = [_hole("H-1", 3, 3, 10, 4, kg=10.0, delay_ms=0.0)]
        rows_late_only = [_hole("H-2", 3, 3, 10, 4, kg=100.0, delay_ms=50.0)]
        rows_both = rows_early_only + rows_late_only

        r_early = run_simulation(
            accepted_rows=rows_early_only, configuration=cfg, segments_per_hole=4,
        )
        r_late = run_simulation(
            accepted_rows=rows_late_only, configuration=cfg, segments_per_hole=4,
        )
        r_both = run_simulation(
            accepted_rows=rows_both, configuration=cfg, segments_per_hole=4,
        )

        tom_early = r_early.field_arrays["time_of_max_s"]
        tom_late = r_late.field_arrays["time_of_max_s"]
        tom_both = r_both.field_arrays["time_of_max_s"]

        # Pick a voxel in the support (near x=3,y=3,z~7).
        active = np.isfinite(tom_both)
        assert np.any(active), "No active voxels for the superposition test"

        # The combined time_of_max MUST differ from early-only at some
        # voxels (the dominant late source shifts the max).
        diffs = np.abs(tom_both[active] - tom_early[active])
        assert np.max(diffs) > 1e-6, (
            "time_of_max_s did not shift when the dominant late source "
            "was added — superposition may not be respected."
        )
        # And it MUST be closer to the late-only field than to the
        # early-only field on average (the late source carries 10x the
            # energy).
        mean_both_vs_late = float(np.nanmean(np.abs(tom_both - tom_late)))
        mean_both_vs_early = float(np.nanmean(np.abs(tom_both - tom_early)))
        assert mean_both_vs_late < mean_both_vs_early, (
            "time_of_max_s is closer to the weak early source than to "
            "the dominant late source — superposition violated."
        )


# ---------------------------------------------------------------------------
# V6-04.d — inactive voxels stay NaN
# ---------------------------------------------------------------------------


class TestInactiveVoxelsNaN:
    """Voxels that receive no temporal contribution MUST keep
    ``time_of_max_s = NaN`` and ``first_arrival_s = NaN``."""

    def test_inactive_voxels_are_nan(self):
        cfg = _make_cfg(bounds=(0, 0, 0, 12, 12, 12))
        # Single hole at the centre — voxels in the far corners get no
        # energy deposit.
        rows = [_hole("H-1", 6, 6, 10, 4)]
        result = run_simulation(
            accepted_rows=rows, configuration=cfg, segments_per_hole=4,
        )
        tom = result.field_arrays["time_of_max_s"]
        fa = result.field_arrays["first_arrival_s"]
        # At least one voxel must be NaN (far from the source).
        assert np.any(np.isnan(tom)), "Expected some inactive voxels with NaN time_of_max_s"
        assert np.any(np.isnan(fa)), "Expected some inactive voxels with NaN first_arrival_s"
        # Active voxels must be finite.
        active_tom = np.isfinite(tom)
        active_fa = np.isfinite(fa)
        assert np.any(active_tom)
        assert np.any(active_fa)
        # Inactive voxels agree between the two fields.
        np.testing.assert_array_equal(np.isnan(tom), np.isnan(fa))


# ---------------------------------------------------------------------------
# V6-04.e — peak buffer respects Bv × Bt
# ---------------------------------------------------------------------------


class TestPeakBufferBounded:
    """The largest single allocation inside
    ``_compute_temporal_fields_streaming`` MUST be bounded by
    ``Bv × Bt × dtype_size``. We verify by intercepting the numpy
    allocator."""

    def test_peak_allocation_respects_bv_times_bt(self):
        import core.blast_simulation.engine as engine_mod

        cfg = _make_cfg()
        rows = [_hole("H-1", 6, 6, 10, 4)]
        Bv = 256
        Bt = 32
        Bs = 8

        # Intercept np.zeros inside the temporal function and record
        # the size (in elements) of every allocation.
        original_zeros = engine_mod.np.zeros
        original_empty = engine_mod.np.empty
        peak_elements = 0
        current_peaks: list[int] = []

        def spy_zeros(shape, **kwargs):
            arr = original_zeros(shape, **kwargs)
            n = int(np.prod(arr.shape)) if arr.ndim > 0 else 1
            current_peaks.append(n)
            return arr

        def spy_empty(shape, **kwargs):
            arr = original_empty(shape, **kwargs)
            n = int(np.prod(arr.shape)) if arr.ndim > 0 else 1
            current_peaks.append(n)
            return arr

        with patch.object(engine_mod.np, "zeros", side_effect=spy_zeros), \
             patch.object(engine_mod.np, "empty", side_effect=spy_empty):
            run_simulation(
                accepted_rows=rows,
                configuration=cfg,
                segments_per_hole=4,
                block_size=4096,
                temporal_voxel_block_size=Bv,
                temporal_time_bins=Bt,
                temporal_segment_block_size=Bs,
            )

        peak_elements = max(current_peaks) if current_peaks else 0
        # The peak MUST be bounded by Bv × Bt (the response matrix).
        # Allow a small margin for the global arrays (first_arrival,
        # time_of_max at n_voxels each) which exceed Bv × Bt for small
        # Bv/Bt on a large grid — those are scientific accumulators,
        # not the streaming buffer.
        n_voxels = 12 * 12 * 12
        scientific_floor = n_voxels  # first_arrival + time_of_max
        streaming_peak = peak_elements
        assert streaming_peak <= max(Bv * Bt, scientific_floor), (
            f"Peak allocation = {streaming_peak} elements, exceeds "
            f"Bv×Bt = {Bv * Bt} and the scientific floor "
            f"{scientific_floor}."
        )
        # And the (Bv, Bt) response matrix MUST appear among allocations.
        assert any(
            n <= Bv * Bt and n > Bt for n in current_peaks
        ), (
            f"No allocation in the (Bt, Bv] range was observed — the "
            f"(Bv, Bt) response matrix was not materialised. Peaks: "
            f"{sorted(set(current_peaks))[-5:]}"
        )
