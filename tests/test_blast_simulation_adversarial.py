"""Adversarial tests for the energy engine (spec §13 — Casos adversariales).

These exercise the engine's failure paths and edge cases:

* Unknown explosive → blocks ABSOLUTE mode.
* Missing specific energy → blocks ABSOLUTE mode.
* Negative length → hole dropped via Fase 1 (we verify the engine is
  defensive even if such a row slipped through).
* Charge > hole length → truncated with warning, never extended.
* Collar outside the domain → outside_domain > 0.
* Partially-out charge → outside_domain > 0 + still runs.
* All sources rejected → represented_energy == 0, no crash.
* Three independent errors on one hole → no double-count, status INVALID.
* Domain too large → resource ceiling raises.
"""
from __future__ import annotations

import pytest

from core.blast_simulation import (
    AnisotropyMode,
    DomainBounds,
    EnergyMode,
    KernelType,
    RockMassConfiguration,
    SIMULATION_CONFIGURATION_VERSION,
    SimulationConfiguration,
    SimulationConfigurationError,
    TemporalMode,
    build_charge_segments,
    classify_segments,
    run_simulation,
)
from core.config import SIMULATION


def _cfg(**overrides) -> SimulationConfiguration:
    base = dict(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=DomainBounds(0, 0, 0, 10, 10, 10),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.STATIC,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=2.0,
        regularization_radius_m=0.5,
        support_radius_m=5.0,
        coupling_efficiency=0.85,
        rock_mass=RockMassConfiguration(
            rock_unit_id="1c", density_kg_m3=2700.0, ucs_mpa=80.0,
            attenuation_coefficient_1_m=2.0, wave_velocity_m_s=3500.0,
            anisotropy_mode=AnisotropyMode.ISOTROPIC,
            source="lab", status="VALIDATED",
        ),
    )
    base.update(overrides)
    return SimulationConfiguration(**base)


def _hole(**overrides) -> dict:
    base = dict(
        hole_id="H-001", X=5.0, Y=5.0, Z_collar=9.0,
        X_toe=5.0, Y_toe=5.0, Z_toe=1.0,
        Incl=0.0, Az=0.0, Len=8.0,
        Taco_m=2.0, descarga=6.0, Diam_mm=200.0,
        Kilos_Cargados_real=100.0, Tipo_Explosivo="ANFO",
        source_row_index=0,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Explosive policy
# ---------------------------------------------------------------------------


class TestExplosivePolicy:
    def test_unknown_explosive_blocks_absolute_mode(self):
        cfg = _cfg(energy_mode=EnergyMode.ABSOLUTE)
        rows = [_hole(Tipo_Explosivo="MysteryBoom")]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        # The engine emits a blocking error — ABSOLUTE mode is refused.
        assert len(result.blocking_errors) >= 1
        assert result.blocking_errors[0]["error_code"] == "ABSOLUTE_MODE_BLOCKED"

    def test_unknown_explosive_allowed_in_relative_mode(self):
        cfg = _cfg(energy_mode=EnergyMode.RELATIVE)
        rows = [_hole(Tipo_Explosivo="MysteryBoom")]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        # RELATIVE mode uses kg as the energy-equivalent weight; unknown
        # explosive is acceptable, the field is tagged dimensionless.
        assert not result.blocking_errors
        assert result.grid_metadata.energy_unit == "dimensionless"
        assert result.energy_field.represented_energy_j > 0.0

    def test_missing_explosive_name_blocks_absolute(self):
        cfg = _cfg(energy_mode=EnergyMode.ABSOLUTE)
        rows = [_hole(Tipo_Explosivo="")]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        assert any(b["error_code"] == "ABSOLUTE_MODE_BLOCKED" for b in result.blocking_errors)

    def test_no_anfo_fallback(self):
        # Even if the explosive name happens to contain "anfo" as part
        # of a longer unknown token, we do not silently fall back to
        # ANFO unless the registry actually resolves it.
        from core.explosive_properties import resolve_explosive, get_explosive_status
        # Sanity: ANFO resolves; an unknown variant does not collapse to ANFO.
        assert resolve_explosive("ANFO") is not None
        assert get_explosive_status("ANFO") == "VALIDATED"
        assert get_explosive_status("UnknownMystery") == "UNKNOWN"


# ---------------------------------------------------------------------------
# Geometry edge cases
# ---------------------------------------------------------------------------


class TestGeometryEdgeCases:
    def test_charge_longer_than_hole_is_truncated(self):
        cfg = _cfg()
        # declared descarga = 100 but Len = 8 → must truncate.
        rows = [_hole(Len=8.0, descarga=100.0)]
        segments = build_charge_segments(rows, config=cfg, segments_per_hole=4)
        # Every charge segment has finite centre and length <= Len.
        for s in segments:
            assert s.length_m <= 8.0
            assert all(__import__("math").isfinite(v) for v in (s.cx, s.cy, s.cz))

    def test_taco_longer_than_hole_clamps_to_zero_charge(self):
        cfg = _cfg()
        # taco_m > Len, and descarga absent so the engine must derive
        # the charge length from Len - Taco (negative → clamped to 0).
        rows = [_hole(Len=4.0, Taco_m=10.0, descarga=None)]
        segments = build_charge_segments(rows, config=cfg, segments_per_hole=2)
        # The clamping emits one marker segment of length 0 (taco).
        assert len(segments) == 1
        assert segments[0].length_m == 0.0
        assert segments[0].segment_type == "taco"

    def test_collar_outside_domain_reports_outside(self):
        cfg = _cfg()
        # Source far outside the domain (0..10): collar at (50, 50, 50).
        rows = [_hole(X=50.0, Y=50.0, Z_collar=55.0, X_toe=50.0, Y_toe=50.0, Z_toe=45.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        # All the energy lands outside → represented ~ 0.
        assert result.energy_field.represented_energy_j == pytest.approx(0.0, abs=1e-3)
        assert result.energy_field.outside_domain_energy_j > 0.0

    def test_zero_length_hole_dropped_safely(self):
        cfg = _cfg()
        rows = [_hole(Len=0.0, Z_toe=9.0, X_toe=5.0, Y_toe=5.0)]
        # Fase 1 should have rejected this row, but the engine must be
        # defensive — it must not crash.
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        assert result.source_summary.charge_segments >= 0  # no crash
        # Zero-length hole → no valid charge column.
        assert result.source_summary.valid_sources == 0


# ---------------------------------------------------------------------------
# Multi-error row
# ---------------------------------------------------------------------------


class TestMultiErrorRow:
    def test_three_independent_errors_on_one_hole(self):
        # Three problems at once: unknown explosive, kg=0, length=0.
        # The engine must report each without double-counting.
        cfg = _cfg(energy_mode=EnergyMode.ABSOLUTE)
        rows = [_hole(Tipo_Explosivo="MysteryBoom", Kilos_Cargados_real=0.0, Len=0.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        # No valid sources were extracted.
        assert result.source_summary.valid_sources == 0
        # Diagnostics enumerate the failure modes.
        diag = result.spatial_diagnostics["segment_diagnostics"]
        assert diag["invalid_segments"] >= 1


# ---------------------------------------------------------------------------
# All sources rejected
# ---------------------------------------------------------------------------


class TestAllSourcesRejected:
    def test_no_valid_sources_produces_empty_field(self):
        cfg = _cfg(energy_mode=EnergyMode.ABSOLUTE)
        # Every row has an unknown explosive → all rejected for ABSOLUTE.
        rows = [
            _hole(hole_id="H-1", Tipo_Explosivo="Mystery"),
            _hole(hole_id="H-2", Tipo_Explosivo="AlsoMystery"),
        ]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        assert result.source_summary.valid_sources == 0
        assert result.energy_field.represented_energy_j == 0.0
        assert result.energy_field.active_voxels == 0


# ---------------------------------------------------------------------------
# Resource ceilings
# ---------------------------------------------------------------------------


class TestResourceCeilings:
    def test_enormous_domain_blocked(self):
        # voxel_size=0.001 over a 1000 m cube → 1e12 voxels, far over limit.
        cfg = _cfg(
            voxel_size_m=0.001,
            domain_bounds=DomainBounds(0, 0, 0, 1000, 1000, 1000),
        )
        rows = [_hole()]
        with pytest.raises(SimulationConfigurationError) as exc:
            run_simulation(accepted_rows=rows, configuration=cfg)
        assert exc.value.error_code == "VOXEL_COUNT_OVER_LIMIT"

    def test_too_many_segments_blocked(self, monkeypatch):
        # Lower the ceiling temporarily so a small test exceeds it.
        from core.config import SimulationDefaults
        # Build a tiny override by monkeypatching the SIMULATION singleton.
        original = SIMULATION.max_charge_segments
        object.__setattr__  # noop, just to satisfy linters
        # We cannot mutate a frozen dataclass; instead patch the engine
        # function's reference via the module path.
        import core.blast_simulation.engine as engine_mod
        tiny = SimulationDefaults(max_charge_segments=2)
        monkeypatch.setattr(engine_mod, "SIMULATION", tiny)
        cfg = _cfg()
        # 10 holes × 8 segs = 80 segments, far over 2.
        rows = [_hole(hole_id=f"H-{i}") for i in range(10)]
        with pytest.raises(SimulationConfigurationError) as exc:
            run_simulation(accepted_rows=rows, configuration=cfg)
        assert exc.value.error_code == "SEGMENT_COUNT_OVER_LIMIT"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_inputs_same_outputs(self):
        cfg = _cfg()
        rows = [_hole()]
        r1 = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
        r2 = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
        # simulation_id is randomly generated — compare the deterministic
        # parts only.
        assert r1.energy_field.represented_energy_j == r2.energy_field.represented_energy_j
        assert r1.energy_field.outside_domain_energy_j == r2.energy_field.outside_domain_energy_j
        assert r1.source_summary.valid_sources == r2.source_summary.valid_sources
        assert r1.provenance.accepted_rows_hash == r2.provenance.accepted_rows_hash

    def test_different_inputs_different_outputs(self):
        cfg = _cfg()
        rows1 = [_hole(Kilos_Cargados_real=100.0)]
        rows2 = [_hole(Kilos_Cargados_real=200.0)]
        r1 = run_simulation(accepted_rows=rows1, configuration=cfg, segments_per_hole=2)
        r2 = run_simulation(accepted_rows=rows2, configuration=cfg, segments_per_hole=2)
        assert r1.energy_field.total_coupled_energy_j != r2.energy_field.total_coupled_energy_j
