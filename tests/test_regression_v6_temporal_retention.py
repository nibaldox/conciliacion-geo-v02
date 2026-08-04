"""V6-04 follow-up: expose the three blocking findings the audit
identified after the first V6-04 pass.

Finding 1 — ``Bs`` does not control retention. The global lists
``temporal_energy_contributions`` / ``temporal_detonation_times`` /
``temporal_distances`` are populated for ALL sources and spatial blocks
BEFORE ``_compute_temporal_fields_streaming`` runs. Changing ``Bs`` only
regroups the consumer iteration; it does not bound the auxiliary memory.

Finding 2 — ``time_of_max_s`` regression. The old per-voxel adaptive
grid preserved the exact arrival for voxels with a single contributing
source (``np.isclose(t_min, t_max, atol=1e-14) → time_of_max = t_min``).
The common-grid V6-04 quantises every voxel to the nearest bin centre,
losing precision for single-source voxels.

Finding 3 — insufficient buffer instrumentation. The V6-04 test only
intercepts ``np.zeros`` / ``np.empty`` and does not observe the global
``temporal_energy_contributions`` list, its per-tuple copies, or the
allocations made by ``ndtr`` / ``np.diff`` / vectorised operations.

Additional requirement (fix #6): ``Bv``, ``Bt`` and ``Bs`` MUST be
strict positive integers — zero, negatives, floats, booleans and
strings MUST be rejected rather than silently coerced.
"""
from __future__ import annotations

from typing import Any

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


def _make_cfg(**over) -> SimulationConfiguration:
    base = dict(
        simulation_configuration_version="2.0",
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=DomainBounds(0, 0, 0, 12, 12, 12),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.TEMPORAL,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        attenuation_coefficient_1_m=0.2,
        regularization_radius_m=0.5,
        support_radius_m=5.0,
        coupling_efficiency=0.85,
        propagation_velocity_m_s=3500.0,
        propagation_velocity_source="lab",
        pulse_sigma_s=0.025,
        rock_mass=RockMassConfiguration(
            rock_unit_id="t", source="t", status="VALIDATED",
        ),
    )
    base.update(over)
    return SimulationConfiguration(**base)


def _hole(hid: str, x: float, y: float, delay_ms: float = 0.0, kg: float = 50.0) -> dict[str, Any]:
    return {
        "hole_id": hid, "X": x, "Y": y, "Z_collar": 10,
        "X_toe": x, "Y_toe": y, "Z_toe": 4,
        "Incl": 0, "Az": 0, "Len": 6,
        "Taco_m": 1, "descarga": 5, "Diam_mm": 200,
        "Kilos_Cargados_real": kg, "Tipo_Explosivo": "ANFO",
        "source_row_index": 0, "Retardo_ms": delay_ms,
    }


# ---------------------------------------------------------------------------
# Finding 2 — time_of_max_s regression for single-source voxels
# ---------------------------------------------------------------------------


class TestTimeOfMaxExactArrival:
    """For a voxel with a single contributing source, ``time_of_max_s``
    MUST equal the exact arrival time (``first_arrival_s``). The old
    per-voxel adaptive grid achieved this via the ``isclose(t_min,
    t_max)`` special case; the common-grid V6-04 lost it."""

    def test_single_source_time_of_max_matches_arrival(self):
        cfg = _make_cfg()
        result = run_simulation(
            accepted_rows=[_hole("H-1", 6, 6)],
            configuration=cfg, segments_per_hole=4,
        )
        fa = result.field_arrays["first_arrival_s"]
        tom = result.field_arrays["time_of_max_s"]
        active = np.isfinite(fa)
        n_active = int(active.sum())
        assert n_active > 0

        matches = np.sum(np.isclose(fa[active], tom[active], atol=1e-14))
        # Every active voxel has exactly one contributing source →
        # time_of_max MUST equal the arrival exactly.
        assert matches == n_active, (
            f"{matches}/{n_active} voxels have time_of_max == arrival. "
            f"Single-source voxels MUST preserve the exact arrival; "
            f"unique time_of_max values: {len(np.unique(tom[active]))}, "
            f"unique arrivals: {len(np.unique(fa[active]))}, "
            f"max error: {float(np.max(np.abs(fa[active] - tom[active]))):.6e} s."
        )

    def test_time_of_max_preserves_arrival_resolution(self):
        """The number of unique ``time_of_max_s`` values MUST be close
        to the number of unique ``first_arrival_s`` values for a
        single-source field. Quantisation to 2 bins (as observed in the
        V6-04 audit) is a regression."""
        cfg = _make_cfg()
        result = run_simulation(
            accepted_rows=[_hole("H-1", 6, 6)],
            configuration=cfg, segments_per_hole=4,
        )
        fa = result.field_arrays["first_arrival_s"]
        tom = result.field_arrays["time_of_max_s"]
        active = np.isfinite(fa)
        n_unique_arrivals = len(np.unique(fa[active]))
        n_unique_tom = len(np.unique(tom[active]))
        # Allow some quantisation slack but require that the number of
        # unique time_of_max values scales with the number of unique
        # arrivals (not collapse to 1-2 bins).
        assert n_unique_tom >= n_unique_arrivals * 0.5, (
            f"time_of_max collapsed to {n_unique_tom} unique values "
            f"(arrivals: {n_unique_arrivals}). The common-grid "
            f"quantisation is too coarse for single-source fields."
        )


# ---------------------------------------------------------------------------
# Finding 1 — no global temporal retention
# ---------------------------------------------------------------------------


class TestNoGlobalTemporalRetention:
    """The engine MUST NOT retain ``temporal_energy_contributions`` /
    ``temporal_detonation_times`` / ``temporal_distances`` as global
    lists populated for every source before the temporal consumer runs.
    The V6-04 follow-up eliminates these lists entirely by merging the
    temporal accumulation into the Bv × Bs spatial loop.

    The cleanest behavioural assertion: ``_compute_temporal_fields_streaming``
    — which consumes the global list — MUST NOT be called at all in
    TEMPORAL mode after the fix. Temporal fields are computed inline
    within the merged spatial loop."""

    def test_temporal_post_pass_not_invoked(self):
        """If the engine still builds a global segment_infos list and
        delegates to ``_compute_temporal_fields_streaming``, the spy
        fires. After V6-04 follow-up the temporal computation is inline
        and this function is never called."""
        from unittest.mock import patch
        import core.blast_simulation.engine as engine_mod

        cfg = _make_cfg()
        with patch.object(
            engine_mod, "_compute_temporal_fields_streaming"
        ) as spy:
            result = run_simulation(
                accepted_rows=[_hole("H-1", 6, 6)],
                configuration=cfg, segments_per_hole=4,
            )
            assert spy.call_count == 0, (
                "_compute_temporal_fields_streaming was called "
                f"{spy.call_count} time(s) — the global temporal list "
                "is still being built and passed as a post-pass. V6-04 "
                "follow-up requires inline temporal accumulation."
            )
        # The temporal fields MUST still be populated.
        tom = result.field_arrays["time_of_max_s"]
        assert np.any(np.isfinite(tom)), (
            "time_of_max_s is all-NaN even though the source deposited "
            "energy — inline temporal accumulation is broken."
        )

    def test_memory_does_not_scale_with_source_count(self):
        """Doubling the number of sources MUST NOT double the peak
        tracemalloc when ``Bs`` is held constant. The global list
        ``temporal_energy_contributions`` scales linearly with
        (sources × spatial_blocks); the inline approach does not."""
        import tracemalloc

        cfg = _make_cfg()

        def _peak_bytes(n_holes: int) -> int:
            rows = [
                _hole(f"H-{i}", 1 + i % 10, 1 + (i * 7) % 10)
                for i in range(n_holes)
            ]
            tracemalloc.start()
            run_simulation(
                accepted_rows=rows, configuration=cfg,
                segments_per_hole=4,
                temporal_segment_block_size=8,
            )
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return peak

        peak_2 = _peak_bytes(2)
        peak_8 = _peak_bytes(8)
        ratio = peak_8 / max(peak_2, 1)
        # Allow up to 3× for the spatial accumulators (which scale with
        # the number of deposits, not just n_voxels). The old global
        # list would push this ratio above 5× for 4× sources.
        assert ratio < 3.5, (
            f"Peak tracemalloc scales super-linearly: 2 holes → "
            f"{peak_2 / 1e6:.2f} MiB, 8 holes → {peak_8 / 1e6:.2f} MiB "
            f"(ratio {ratio:.2f}). The global temporal list is likely "
            f"still retained."
        )


# ---------------------------------------------------------------------------
# Fix #6 — strict positive-integer validation for Bv / Bt / Bs
# ---------------------------------------------------------------------------


class TestBlockSizeValidation:
    """``temporal_voxel_block_size`` (Bv), ``temporal_time_bins`` (Bt)
    and ``temporal_segment_block_size`` (Bs) MUST be strict positive
    integers. Zero, negatives, floats, booleans and strings MUST be
    rejected."""

    @pytest.mark.parametrize(
        ("param", "bad_value", "label"),
        [
            ("temporal_voxel_block_size", 0, "zero"),
            ("temporal_voxel_block_size", -1, "negative"),
            ("temporal_voxel_block_size", 1.5, "float"),
            ("temporal_voxel_block_size", True, "bool"),
            ("temporal_voxel_block_size", "64", "string"),
            ("temporal_time_bins", 0, "zero"),
            ("temporal_time_bins", -8, "negative"),
            ("temporal_time_bins", 32.0, "float"),
            ("temporal_time_bins", True, "bool"),
            ("temporal_time_bins", "64", "string"),
            ("temporal_segment_block_size", 0, "zero"),
            ("temporal_segment_block_size", -4, "negative"),
            ("temporal_segment_block_size", 8.0, "float"),
            ("temporal_segment_block_size", False, "bool"),
            ("temporal_segment_block_size", "8", "string"),
        ],
    )
    def test_invalid_block_size_rejected(self, param, bad_value, label):
        cfg = _make_cfg()
        kwargs = {param: bad_value}
        with pytest.raises((TypeError, ValueError), match=r".*must be.*positive.*int.*|.*>.*0.*"):
            run_simulation(
                accepted_rows=[_hole("H-1", 6, 6)],
                configuration=cfg, segments_per_hole=4,
                **kwargs,
            )

    @pytest.mark.parametrize(
        ("param", "good_value"),
        [
            ("temporal_voxel_block_size", 1),
            ("temporal_voxel_block_size", 4096),
            ("temporal_time_bins", 32),
            ("temporal_time_bins", 128),
            ("temporal_segment_block_size", 1),
            ("temporal_segment_block_size", 256),
        ],
    )
    def test_valid_block_size_accepted(self, param, good_value):
        cfg = _make_cfg()
        result = run_simulation(
            accepted_rows=[_hole("H-1", 6, 6)],
            configuration=cfg, segments_per_hole=4,
            **{param: good_value},
        )
        assert result.field_arrays is not None
        assert "time_of_max_s" in result.field_arrays
