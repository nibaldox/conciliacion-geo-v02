"""Phase 2 — contract validation tests (spec §7).

These tests exercise the closed validation surface of
:class:`core.blast_simulation.contracts.SimulationConfiguration` and
the sub-contracts it aggregates. They are the boundary that every
adversarial case (NaN, infinity, inverted bounds, invalid tensor, etc.)
must hit before reaching the engine.
"""
from __future__ import annotations

import math

import pytest

from core.blast_simulation.contracts import (
    AnisotropyMode,
    DomainBounds,
    EnergyMode,
    EnergyPropagationConfiguration,
    KernelType,
    RockMassConfiguration,
    SIMULATION_CONFIGURATION_VERSION,
    SimulationConfiguration,
    SimulationConfigurationError,
    TemporalMode,
    TemporalSimulationConfiguration,
    VoxelGridSpecification,
)


# ---------------------------------------------------------------------------
# Fixtures: a fully-confirmed canonical configuration
# ---------------------------------------------------------------------------


def _canonical_bounds() -> DomainBounds:
    return DomainBounds(
        x_min=0.0, y_min=0.0, z_min=0.0,
        x_max=50.0, y_max=50.0, z_max=15.0,
    )


def _canonical_rock() -> RockMassConfiguration:
    return RockMassConfiguration(
        rock_unit_id="1c",
        density_kg_m3=2700.0,
        ucs_mpa=80.0,
        attenuation_coefficient_1_m=0.05,
        wave_velocity_m_s=3500.0,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        source="lab",
        status="VALIDATED",
    )


def _canonical_config(**overrides) -> SimulationConfiguration:
    base = dict(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=_canonical_bounds(),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.STATIC,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=0.05,
        regularization_radius_m=0.5,
        coupling_efficiency=0.85,
        rock_mass=_canonical_rock(),
    )
    base.update(overrides)
    return SimulationConfiguration(**base)


# ---------------------------------------------------------------------------
# Confirmation gate
# ---------------------------------------------------------------------------


class TestConfirmationGate:
    def test_unconfirmed_blocks(self):
        cfg = _canonical_config(user_confirmed=None)
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert exc.value.error_code == "SIMULATION_NOT_CONFIRMED"

    def test_rejected_blocks(self):
        cfg = _canonical_config(user_confirmed=False)
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert exc.value.error_code == "SIMULATION_REJECTED"

    def test_confirmed_passes(self):
        cfg = _canonical_config(user_confirmed=True)
        assert cfg.validate() is cfg


# ---------------------------------------------------------------------------
# Version pinning
# ---------------------------------------------------------------------------


class TestVersionPinning:
    def test_wrong_simulation_version_blocked(self):
        cfg = _canonical_config(simulation_configuration_version="0.9")
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert exc.value.error_code == "SIMULATION_INVALID"
        assert "simulation_configuration_version" in exc.value.details["missing_or_invalid"]

    def test_missing_geometry_version_blocked(self):
        cfg = _canonical_config(geometry_configuration_version="")
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert "geometry_configuration_version" in exc.value.details["missing_or_invalid"]


# ---------------------------------------------------------------------------
# Closed enum literals
# ---------------------------------------------------------------------------


class TestClosedEnums:
    @pytest.mark.parametrize("bad_mode", ["absolute", "JOULES", "", None, "rel"])
    def test_invalid_energy_mode(self, bad_mode):
        cfg = _canonical_config(energy_mode=bad_mode)
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert exc.value.details["missing_or_invalid"]["energy_mode"] == bad_mode

    @pytest.mark.parametrize("bad_mode", ["static!", "DYNAMIC", None])
    def test_invalid_temporal_mode(self, bad_mode):
        cfg = _canonical_config(temporal_mode=bad_mode)
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert "temporal_mode" in exc.value.details["missing_or_invalid"]

    @pytest.mark.parametrize("bad_mode", ["ISO", "TENSOR", None])
    def test_invalid_anisotropy_mode(self, bad_mode):
        cfg = _canonical_config(anisotropy_mode=bad_mode)
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert "anisotropy_mode" in exc.value.details["missing_or_invalid"]

    def test_invalid_kernel_type(self):
        cfg = _canonical_config(kernel_type="GAUSSIAN")
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert "kernel_type" in exc.value.details["missing_or_invalid"]


# ---------------------------------------------------------------------------
# Numeric sanity: NaN, inf, sign, ranges
# ---------------------------------------------------------------------------


class TestNumericSanity:
    def test_voxel_size_zero_blocked(self):
        cfg = _canonical_config(voxel_size_m=0.0)
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    def test_voxel_size_negative_blocked(self):
        cfg = _canonical_config(voxel_size_m=-1.0)
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    def test_voxel_size_nan_blocked(self):
        cfg = _canonical_config(voxel_size_m=float("nan"))
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    def test_voxel_size_inf_blocked(self):
        cfg = _canonical_config(voxel_size_m=float("inf"))
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    @pytest.mark.parametrize("eff", [-0.01, 1.01, 2.0, float("nan")])
    def test_coupling_efficiency_out_of_range(self, eff):
        cfg = _canonical_config(coupling_efficiency=eff)
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    @pytest.mark.parametrize("alpha", [-0.001, -1.0])
    def test_attenuation_negative_blocked(self, alpha):
        cfg = _canonical_config(attenuation_coefficient_1_m=alpha)
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    @pytest.mark.parametrize("r0", [0.0, -0.5])
    def test_regularization_non_positive_blocked(self, r0):
        cfg = _canonical_config(regularization_radius_m=r0)
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()


# ---------------------------------------------------------------------------
# Domain bounds
# ---------------------------------------------------------------------------


class TestDomainBounds:
    def test_inverted_x_blocked(self):
        with pytest.raises(SimulationConfigurationError) as exc:
            DomainBounds(10, 0, 0, 0, 10, 10).validate()
        assert exc.value.error_code == "DOMAIN_INVERTED"

    def test_degenerate_blocked(self):
        with pytest.raises(SimulationConfigurationError):
            DomainBounds(0, 0, 0, 0, 10, 10).validate()

    def test_nan_blocked(self):
        with pytest.raises(SimulationConfigurationError) as exc:
            DomainBounds(float("nan"), 0, 0, 10, 10, 10).validate()
        assert exc.value.error_code == "DOMAIN_NON_FINITE"

    def test_inf_blocked(self):
        with pytest.raises(SimulationConfigurationError):
            DomainBounds(0, 0, 0, float("inf"), 10, 10).validate()


# ---------------------------------------------------------------------------
# Voxel grid geometry
# ---------------------------------------------------------------------------


class TestVoxelGrid:
    def test_shape_and_volume(self):
        grid = VoxelGridSpecification(
            voxel_size_m=2.0,
            bounds=DomainBounds(0, 0, 0, 10, 10, 10),
        )
        assert grid.shape == (5, 5, 5)
        assert grid.voxel_count == 125
        assert grid.voxel_volume_m3 == 8.0

    def test_non_integer_division_floors(self):
        grid = VoxelGridSpecification(
            voxel_size_m=3.0,
            bounds=DomainBounds(0, 0, 0, 10, 10, 10),
        )
        # 10/3 = 3.33 → floor = 3
        assert grid.shape == (3, 3, 3)

    def test_zero_voxel_size_blocked(self):
        with pytest.raises(SimulationConfigurationError):
            VoxelGridSpecification(0.0, DomainBounds(0, 0, 0, 1, 1, 1)).validate()


# ---------------------------------------------------------------------------
# Anisotropy tensor
# ---------------------------------------------------------------------------


class TestAnisotropyTensor:
    def _pd_tensor(self):
        return (
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.0, 0.0, 2.0),
        )

    def test_anisotropic_without_tensor_blocks(self):
        cfg = _canonical_config(anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR)
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert "anisotropy_tensor" in exc.value.details["missing_or_invalid"]

    def test_anisotropic_with_pd_tensor_passes(self):
        rock = RockMassConfiguration(
            rock_unit_id="1c",
            density_kg_m3=2700.0,
            ucs_mpa=80.0,
            attenuation_coefficient_1_m=0.05,
            wave_velocity_m_s=3500.0,
            anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
            anisotropy_tensor=self._pd_tensor(),
            source="lab",
            status="VALIDATED",
        )
        cfg = _canonical_config(
            anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
            rock_mass=rock,
        )
        assert cfg.validate() is cfg

    def test_asymmetric_tensor_blocked(self):
        bad = ((1.0, 0.5, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        from core.blast_simulation.contracts import _is_symmetric_pd
        assert _is_symmetric_pd(bad) is False

    def test_non_pd_tensor_blocked(self):
        # eigenvalues 1, 1, -1 → indefinite
        bad = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))
        from core.blast_simulation.contracts import _is_symmetric_pd
        assert _is_symmetric_pd(bad) is False

    def test_wrong_shape_tensor_blocked(self):
        bad = ((1.0, 0.0), (0.0, 1.0))
        from core.blast_simulation.contracts import _is_symmetric_pd
        assert _is_symmetric_pd(bad) is False


# ---------------------------------------------------------------------------
# Temporal sub-contract
# ---------------------------------------------------------------------------


class TestTemporalSubcontract:
    def test_temporal_without_velocity_blocks(self):
        cfg = _canonical_config(
            temporal_mode=TemporalMode.TEMPORAL,
            propagation_velocity_m_s=None,
        )
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert "propagation_velocity_m_s" in exc.value.details["missing_or_invalid"]

    def test_temporal_without_source_blocks(self):
        cfg = _canonical_config(
            temporal_mode=TemporalMode.TEMPORAL,
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="",
        )
        with pytest.raises(SimulationConfigurationError) as exc:
            cfg.validate()
        assert "propagation_velocity_source" in exc.value.details["missing_or_invalid"]

    def test_temporal_zero_velocity_blocks(self):
        cfg = _canonical_config(
            temporal_mode=TemporalMode.TEMPORAL,
            propagation_velocity_m_s=0.0,
            propagation_velocity_source="lab",
        )
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    def test_temporal_negative_sigma_blocks(self):
        cfg = _canonical_config(
            temporal_mode=TemporalMode.TEMPORAL,
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="lab",
            pulse_sigma_s=-0.01,
        )
        with pytest.raises(SimulationConfigurationError):
            cfg.validate()

    def test_static_does_not_require_velocity(self):
        cfg = _canonical_config(temporal_mode=TemporalMode.STATIC)
        assert cfg.validate() is cfg


# ---------------------------------------------------------------------------
# Sub-contracts validate independently
# ---------------------------------------------------------------------------


class TestSubcontractsIndependent:
    def test_propagation_contract_rejects_missing(self):
        with pytest.raises(SimulationConfigurationError):
            EnergyPropagationConfiguration().validate()

    def test_propagation_contract_rejects_bad_efficiency(self):
        with pytest.raises(SimulationConfigurationError):
            EnergyPropagationConfiguration(
                attenuation_coefficient_1_m=0.1,
                regularization_radius_m=0.5,
                coupling_efficiency=1.5,
            ).validate()

    def test_temporal_contract_static_ok(self):
        c = TemporalSimulationConfiguration(temporal_mode=TemporalMode.STATIC)
        assert c.validate() is c

    def test_rock_mass_negative_density_blocked(self):
        with pytest.raises(SimulationConfigurationError):
            RockMassConfiguration(density_kg_m3=-100.0).validate()

    def test_rock_mass_negative_velocity_blocked(self):
        with pytest.raises(SimulationConfigurationError):
            RockMassConfiguration(wave_velocity_m_s=-1.0).validate()


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_is_json_serializable(self):
        import json
        cfg = _canonical_config()
        d = cfg.to_dict()
        # Must round-trip through JSON without loss
        s = json.dumps(d, default=str)
        back = json.loads(s)
        assert back["simulation_configuration_version"] == SIMULATION_CONFIGURATION_VERSION
        assert back["user_confirmed"] is True
        assert back["domain_bounds"]["x_max"] == 50.0

    def test_rock_mass_tensor_serializes_as_lists(self):
        rock = RockMassConfiguration(
            density_kg_m3=2700.0,
            anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
            anisotropy_tensor=((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 2.0)),
            source="lab",
            status="VALIDATED",
        )
        d = rock.to_dict()
        assert d["anisotropy_tensor"] == [[2.0, 0.0, 0.0], [2.0, 2.0, 0.0] if False else [0.0, 2.0, 0.0], [0.0, 0.0, 2.0]]


# ---------------------------------------------------------------------------
# Determinism — same inputs, same validation
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_validation_idempotent(self):
        cfg = _canonical_config()
        first = cfg.validate().to_dict()
        second = cfg.validate().to_dict()
        assert first == second
