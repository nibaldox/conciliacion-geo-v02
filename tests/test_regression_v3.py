"""Red regression tests for the v3 canonical result remediation.

These pin the requirement that ``run_simulation`` returns the actual
scientific arrays and persistence consumes them instead of
recalculating via ``compute_field_arrays``.
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


pytestmark = pytest.mark.regression_v3


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


def _holes(n: int = 1) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        rows.append({
            "hole_id": f"H-{i:04d}", "X": 5.0, "Y": 5.0, "Z_collar": 8.0,
            "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 2.0,
            "Incl": 0.0, "Az": 0.0, "Len": 6.0, "Taco_m": 1.0,
            "descarga": 5.0, "Diam_mm": 200.0,
            "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
            "source_row_index": i, "Retardo_ms": float(i * 25),
        })
    return rows


# ---------------------------------------------------------------------------
# Falla: persistencia recalcula el campo
# ---------------------------------------------------------------------------


class TestCanonicalResultNoRecalculation:
    """The persistence layer MUST NOT call compute_field_arrays to
    recalculate the field when the result already carries the canonical
    arrays. Recalculation doubles the compute cost and risks divergence."""

    def test_run_simulation_returns_field_arrays(self):
        """run_simulation must populate result.field_arrays with the
        actual numpy arrays (not None)."""
        cfg = _cfg()
        result = run_simulation(accepted_rows=_holes(1), configuration=cfg)
        assert result.field_arrays is not None, (
            "SimulationResult.field_arrays must be populated by run_simulation"
        )
        assert "energy_total" in result.field_arrays
        assert "dominant_hole_id" in result.field_arrays

    def test_persistence_does_not_recalculate_when_arrays_present(self, tmp_path: Path):
        """When result.field_arrays is set, write_atomic_simulation MUST
        use them directly and MUST NOT call compute_field_arrays."""
        cfg = _cfg()
        rows = _holes(1)
        result = run_simulation(accepted_rows=rows, configuration=cfg)
        assert result.field_arrays is not None

        # Patch compute_field_arrays to track whether it gets called.
        with patch.object(
            persistence, "compute_field_arrays",
            wraps=persistence.compute_field_arrays,
        ) as spy:
            _updated, npz_path, _sha, _sum = persistence.write_atomic_simulation(
                result=result,
                accepted_rows=rows,
                configuration=cfg,
                data_dir=tmp_path,
            )
            assert spy.call_count == 0, (
                f"write_atomic_simulation called compute_field_arrays "
                f"{spy.call_count} times when result.field_arrays was "
                f"already populated — persistence must consume the "
                f"canonical arrays directly"
            )

        # Verify the NPZ is readable and matches the in-memory arrays.
        with np.load(npz_path, allow_pickle=False) as data:
            npz_energy = data["energy_total"]
        memory_energy = result.field_arrays["energy_total"]
        np.testing.assert_allclose(npz_energy, memory_energy, rtol=1e-6)

    def test_memory_npz_api_parity_static(self, tmp_path: Path):
        """Memory, NPZ and persistence arrays represent the SAME field."""
        cfg = _cfg()
        rows = _holes(2)
        result = run_simulation(accepted_rows=rows, configuration=cfg)

        _updated, npz_path, _sha, _sum = persistence.write_atomic_simulation(
            result=result, accepted_rows=rows, configuration=cfg,
            data_dir=tmp_path,
        )
        with np.load(npz_path, allow_pickle=False) as data:
            for key in ("energy_total", "dominant_idx", "contributing_count"):
                mem = result.field_arrays[key]
                npz = data[key]
                assert mem.shape == npz.shape, f"{key}: shape mismatch"
                assert mem.dtype == npz.dtype or mem.dtype.kind == npz.dtype.kind, (
                    f"{key}: dtype {mem.dtype} vs {npz.dtype}"
                )
                np.testing.assert_allclose(npz, mem, rtol=1e-5)

    def test_temporal_arrays_in_canonical_result(self):
        """In TEMPORAL mode the canonical result must carry
        first_arrival_s and time_of_max_s arrays."""
        cfg = _cfg(
            temporal_mode=TemporalMode.TEMPORAL,
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="lab",
            pulse_sigma_s=0.001,
        )
        result = run_simulation(accepted_rows=_holes(2), configuration=cfg)
        assert result.field_arrays is not None
        assert "first_arrival_s" in result.field_arrays
        assert "time_of_max_s" in result.field_arrays
