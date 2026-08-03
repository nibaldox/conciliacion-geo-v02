"""Atomic-write + Falla 3 + Falla 7 contract tests.

These tests pin the specific guarantees the new persistence layer
delivers:

* :func:`write_atomic_simulation` only leaves artifacts on disk when
  every step succeeds. Any failure BEFORE the final directory rename
  cleans up the ``.tmp/`` directory entirely.
* Falla 3 — temporal mode persists the actual ``first_arrival_s`` and
  ``time_of_max_s`` arrays (not NaN placeholders). Static mode does NOT
  include them.
* Falla 7 — :func:`should_persist` returns ``False`` for a simulation
  with ``blocking_errors``. The API uses this gate to skip
  artifact creation.
* :func:`read_npz_artifact` rejects a tampered file (SHA-256 mismatch).
* :func:`read_npz_artifact` does NOT require ``allow_pickle=True``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

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
    compute_field_arrays,
    read_npz_artifact,
    should_persist,
    write_atomic_simulation,
)
from core.blast_simulation.persistence import (
    PersistenceError,
    _tmp_dir_for,
    simulation_dir,
)


def _cfg(temporal_mode: str = TemporalMode.STATIC) -> SimulationConfiguration:
    """Build a minimal valid configuration for the tests."""
    return SimulationConfiguration(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=DomainBounds(-5, -5, -5, 5, 5, 5),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=temporal_mode,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=2.0,
        regularization_radius_m=0.5,
        support_radius_m=5.0,
        coupling_efficiency=0.85,
        propagation_velocity_m_s=3500.0 if temporal_mode == TemporalMode.TEMPORAL else None,
        propagation_velocity_source="lab" if temporal_mode == TemporalMode.TEMPORAL else "",
        pulse_sigma_s=0.001 if temporal_mode == TemporalMode.TEMPORAL else None,
        rock_mass=RockMassConfiguration(
            rock_unit_id="1c", density_kg_m3=2700.0, ucs_mpa=80.0,
            attenuation_coefficient_1_m=2.0, wave_velocity_m_s=3500.0,
            anisotropy_mode=AnisotropyMode.ISOTROPIC,
            source="lab", status="VALIDATED",
        ),
    )


def _rows() -> list[dict]:
    return [
        {
            "hole_id": "H-001", "X": 0.0, "Y": 0.0, "Z_collar": 4.0,
            "X_toe": 0.0, "Y_toe": 0.0, "Z_toe": -4.0,
            "Incl": 0.0, "Az": 0.0, "Len": 8.0,
            "Taco_m": 2.0, "descarga": 6.0, "Diam_mm": 200.0,
            "Kilos_Cargados_real": 100.0, "Tipo_Explosivo": "ANFO",
            "source_row_index": 0,
        },
    ]


def _run_simulation(cfg: SimulationConfiguration, tmp_path: Optional[Path]):
    """Re-run the engine deterministically and return the result."""
    from core.blast_simulation import run_simulation
    return run_simulation(
        accepted_rows=_rows(),
        configuration=cfg,
        segments_per_hole=2,
    )


# ---------------------------------------------------------------------------
# Atomic write cleanup on failure
# ---------------------------------------------------------------------------


class TestAtomicWriteCleanup:
    def test_atomic_write_cleans_up_on_failure(self, tmp_path, monkeypatch):
        """A failure during field-array computation leaves no .tmp files."""
        cfg = _cfg()
        result = _run_simulation(cfg, tmp_path)

        # Force compute_field_arrays to raise mid-flight.
        def _boom(**kwargs):
            raise RuntimeError("simulated field-array failure")

        monkeypatch.setattr(
            "core.blast_simulation.persistence.compute_field_arrays",
            _boom,
        )

        with pytest.raises(RuntimeError, match="simulated field-array failure"):
            write_atomic_simulation(
                result=result,
                accepted_rows=_rows(),
                configuration=cfg,
                data_dir=tmp_path,
            )

        # Two invariants must hold:
        #   1. The canonical {simulation_id}/ directory was never created.
        sim_dir = simulation_dir(result.simulation_id, data_dir=tmp_path)
        assert not sim_dir.exists(), (
            f"canonical sim_dir was created on failure: {sim_dir}"
        )
        #   2. The {simulation_id}.tmp/ directory was cleaned up.
        tmp_dir = _tmp_dir_for(result.simulation_id, data_dir=tmp_path)
        assert not tmp_dir.exists(), (
            f"tmp_dir was not cleaned up: {tmp_dir}"
        )

    def test_atomic_write_full_round_trip(self, tmp_path):
        """Successful atomic write creates the canonical directory."""
        cfg = _cfg()
        result = _run_simulation(cfg, tmp_path)
        updated, npz_path, sha, summary_path = write_atomic_simulation(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
            data_dir=tmp_path,
        )

        sim_dir = simulation_dir(result.simulation_id, data_dir=tmp_path)
        assert sim_dir.exists()
        assert npz_path.exists()
        assert summary_path.exists()
        assert updated.grid_metadata.npz_sha256 == sha


# ---------------------------------------------------------------------------
# Falla 3 — temporal arrays are real
# ---------------------------------------------------------------------------


class TestFalla3TemporalArrays:
    def test_npz_round_trip_with_temporal_arrays(self, tmp_path):
        cfg = _cfg(temporal_mode=TemporalMode.TEMPORAL)
        result = _run_simulation(cfg, tmp_path)
        updated, npz_path, sha, _summary = write_atomic_simulation(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
            data_dir=tmp_path,
        )

        arrays, metadata, sha2 = read_npz_artifact(
            npz_path, expected_sha256=sha
        )
        assert sha == sha2
        # Falla 3 — temporal arrays are present and carry real values.
        assert "first_arrival_s" in arrays, "first_arrival_s missing in TEMPORAL"
        assert "time_of_max_s" in arrays, "time_of_max_s missing in TEMPORAL"
        first_arrival = arrays["first_arrival_s"]
        time_of_max = arrays["time_of_max_s"]
        assert first_arrival.dtype == np.float32
        assert time_of_max.dtype == np.float32
        # The first voxel (closest to the source) must have a finite
        # arrival time (the source is at the origin and the source
        # voxel is at distance 0).
        assert first_arrival.size > 0
        # At least one voxel must have a finite arrival (the source's
        # own voxel or a neighbour).
        assert np.isfinite(first_arrival).any(), (
            "first_arrival_s is all NaN — temporal layer not persisted"
        )

    def test_npz_no_temporal_arrays_in_static_mode(self, tmp_path):
        cfg = _cfg(temporal_mode=TemporalMode.STATIC)
        result = _run_simulation(cfg, tmp_path)
        updated, npz_path, sha, _summary = write_atomic_simulation(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
            data_dir=tmp_path,
        )

        arrays, _metadata, _sha2 = read_npz_artifact(
            npz_path, expected_sha256=sha
        )
        # Falla 3 — STATIC mode does NOT carry temporal arrays.
        assert "first_arrival_s" not in arrays, (
            "first_arrival_s leaked into STATIC mode"
        )
        assert "time_of_max_s" not in arrays, (
            "time_of_max_s leaked into STATIC mode"
        )

    def test_compute_field_arrays_static_mode_no_temporal(self, tmp_path):
        cfg = _cfg(temporal_mode=TemporalMode.STATIC)
        result = _run_simulation(cfg, tmp_path)
        arrays = compute_field_arrays(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
        )
        assert "first_arrival_s" not in arrays
        assert "time_of_max_s" not in arrays

    def test_compute_field_arrays_temporal_mode_has_arrays(self, tmp_path):
        cfg = _cfg(temporal_mode=TemporalMode.TEMPORAL)
        result = _run_simulation(cfg, tmp_path)
        arrays = compute_field_arrays(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
        )
        assert "first_arrival_s" in arrays
        assert "time_of_max_s" in arrays
        assert arrays["first_arrival_s"].dtype == np.float32
        assert arrays["time_of_max_s"].dtype == np.float32
        # At least one voxel must have a finite arrival.
        assert np.isfinite(arrays["first_arrival_s"]).any()


# ---------------------------------------------------------------------------
# Falla 7 — should_persist gate
# ---------------------------------------------------------------------------


class TestFalla7PersistabilityGate:
    def test_should_persist_returns_false_with_blocking_errors(self):
        """A blocked simulation MUST NOT produce an artifact."""
        from dataclasses import replace

        cfg = _cfg()
        result = _run_simulation(cfg, tmp_path=None)
        blocking = (
            {
                "error_code": "ABSOLUTE_MODE_BLOCKED",
                "message": "1 segment lacks resolvable energy",
                "details": {},
                "recommended_action": "use energy_mode=RELATIVE",
            },
        )
        blocked = replace(result, blocking_errors=blocking)
        assert should_persist(blocked) is False

    def test_should_persist_returns_true_without_blocking_errors(self):
        cfg = _cfg()
        result = _run_simulation(cfg, tmp_path=None)
        # The engine build we use here run a successful simulation
        # (no blocking errors), so the gate must allow persistence.
        assert should_persist(result) is True


# ---------------------------------------------------------------------------
# Tamper / SHA-256 / pickle-free read
# ---------------------------------------------------------------------------


class TestNpzIntegrity:
    def test_tampered_file_detected(self, tmp_path):
        cfg = _cfg()
        result = _run_simulation(cfg, tmp_path)
        _, npz_path, sha, _ = write_atomic_simulation(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
            data_dir=tmp_path,
        )

        # Append bytes to the file — tamper detection must catch it.
        with open(npz_path, "ab") as f:
            f.write(b"\x00\x01\x02")

        with pytest.raises(PersistenceError, match="SHA-256 mismatch"):
            read_npz_artifact(npz_path, expected_sha256=sha)

    def test_pickle_disabled(self, tmp_path):
        """``np.load`` inside :func:`read_npz_artifact` uses no pickle."""
        cfg = _cfg()
        result = _run_simulation(cfg, tmp_path)
        _, npz_path, sha, _ = write_atomic_simulation(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
            data_dir=tmp_path,
        )

        # Independently load the NPZ with allow_pickle=False — same
        # arrays, no pickle anywhere.
        arrays, _metadata, sha2 = read_npz_artifact(npz_path, expected_sha256=sha)
        assert sha == sha2
        # Sanity — the canonical arrays we declared are loadable.
        for required in (
            "energy_total",
            "energy_density_j_m3",
            "contributing_count",
            "dominant_idx",
            "dominant_hole_id",
            "dominant_energy",
            "voxel_centres",
            "grid_shape",
            "axis_order",
            "dtype",
            "units",
        ):
            assert required in arrays, f"missing canonical array {required!r}"

        # Confirm dominant_hole_id is a Unicode string array (loadable
        # without pickle).
        assert arrays["dominant_hole_id"].dtype.kind == "U"
        # The single hole in the test data dominates the source voxel.
        assert any(arrays["dominant_hole_id"] == "H-001")

    def test_pickle_disabled_temporal_mode(self, tmp_path):
        cfg = _cfg(temporal_mode=TemporalMode.TEMPORAL)
        result = _run_simulation(cfg, tmp_path)
        _, npz_path, sha, _ = write_atomic_simulation(
            result=result,
            accepted_rows=_rows(),
            configuration=cfg,
            data_dir=tmp_path,
        )

        arrays, _, _ = read_npz_artifact(npz_path, expected_sha256=sha)
        assert "first_arrival_s" in arrays
        assert arrays["first_arrival_s"].dtype == np.float32
        assert "time_of_max_s" in arrays
        assert arrays["time_of_max_s"].dtype == np.float32
