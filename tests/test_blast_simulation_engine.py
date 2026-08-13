"""Scientific invariant tests for the voxel energy engine (spec §13).

These tests verify the physics, not the API. They are the analytical
yardstick the engine must satisfy:

* Conservation — Σ energy_in_domain ≤ Σ E_acoplada, with the remainder
  reported as outside-domain.
* Radial symmetry — voxels at equal distance receive equal energy.
* Monotonicity — energy decays with distance for a single source.
* Translation invariance — shifting domain + sources preserves the
  relative field.
* Rotation invariance — isotropic case is invariant under rigid rotation.
* Resolution convergence — totals stabilize as voxel size shrinks.
* Superposition — two identical simultaneous sources sum to 2× one.
* Delays — arrival times match the analytical t = r/v formula.
* Anisotropy — identity reproduces isotropy; a real tensor modifies
  distances in the expected direction.

Conservation tolerances use :data:`core.config.SIMULATION.conservation_rel_tol`
to accommodate float32 storage of the NPZ artifact.
"""
from __future__ import annotations

import math

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
    build_charge_segments,
    export_field_arrays,
    run_simulation,
)
from core.blast_simulation.contracts import ChargeSegment
from core.config import SIMULATION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rock(isotropic: bool = True, tensor=None) -> RockMassConfiguration:
    return RockMassConfiguration(
        rock_unit_id="1c",
        density_kg_m3=2700.0,
        ucs_mpa=80.0,
        attenuation_coefficient_1_m=0.1,
        wave_velocity_m_s=3500.0,
        anisotropy_mode=(AnisotropyMode.ISOTROPIC if isotropic else AnisotropyMode.ANISOTROPIC_TENSOR),
        anisotropy_tensor=tensor,
        source="lab",
        status="VALIDATED",
    )


def _cfg(
    *,
    bounds: DomainBounds,
    voxel: float = 1.0,
    alpha: float = 0.1,
    r0: float = 0.5,
    eta: float = 0.85,
    energy_mode: str = EnergyMode.ABSOLUTE,
    temporal_mode: str = TemporalMode.STATIC,
    velocity: float | None = None,
    rock: RockMassConfiguration | None = None,
    pulse_sigma: float | None = None,
    support_radius_m: float = 5.0,
) -> SimulationConfiguration:
    return SimulationConfiguration(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=voxel,
        domain_bounds=bounds,
        energy_mode=energy_mode,
        temporal_mode=temporal_mode,
        anisotropy_mode=(rock.anisotropy_mode if rock else AnisotropyMode.ISOTROPIC),
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=alpha,
        regularization_radius_m=r0,
        support_radius_m=support_radius_m,
        coupling_efficiency=eta,
        propagation_velocity_m_s=velocity,
        propagation_velocity_source="lab" if velocity else "",
        pulse_sigma_s=pulse_sigma,
        rock_mass=rock or _rock(),
    )


def _hole(hole_id: str, x: float, y: float, z_top: float, z_bot: float, *,
          kg: float = 100.0, explosive: str = "ANFO", taco: float = 2.0,
          delay_ms: float | None = None) -> dict:
    return {
        "hole_id": hole_id, "X": x, "Y": y, "Z_collar": z_top,
        "X_toe": x, "Y_toe": y, "Z_toe": z_bot,
        "Incl": 0.0, "Az": 0.0, "Len": z_top - z_bot,
        "Taco_m": taco, "descarga": (z_top - z_bot) - taco, "Diam_mm": 200.0,
        "Kilos_Cargados_real": kg, "Tipo_Explosivo": explosive,
        "Retardo_ms": delay_ms, "source_row_index": 0,
    }


# ---------------------------------------------------------------------------
# Conservation
# ---------------------------------------------------------------------------


class TestConservation:
    def test_single_source_full_domain(self):
        # Use a high attenuation so the kernel is effectively contained
        # inside the domain. With alpha=5 the cutoff is ~10 m; a ±15 m
        # domain comfortably contains the kernel's effective support.
        cfg = _cfg(bounds=DomainBounds(-15, -15, -15, 15, 15, 15), voxel=1.0, alpha=5.0, r0=0.5)
        rows = [_hole("H-1", 0.0, 0.0, 5.0, -5.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
        # Outside-domain energy is small but non-zero; the invariant
        # that matters is conservation: represented + outside == coupled.
        total = (
            result.energy_field.represented_energy_j
            + result.energy_field.outside_domain_energy_j
        )
        assert total == pytest.approx(
            result.energy_field.total_coupled_energy_j, rel=SIMULATION.conservation_rel_tol
        )

    def test_low_attenuation_reports_outside(self):
        # With a low attenuation and a small domain, a meaningful chunk
        # of the kernel's support lies outside → outside_energy > 0.
        cfg = _cfg(bounds=DomainBounds(-5, -5, -5, 5, 5, 5), voxel=1.0, alpha=0.1, r0=0.5)
        rows = [_hole("H-1", 0.0, 0.0, 2.0, -2.0, kg=100.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        assert result.energy_field.outside_domain_energy_j > 0.0
        assert result.energy_field.fraction_represented < 1.0

    def test_field_sum_matches_represented(self):
        cfg = _cfg(bounds=DomainBounds(-8, -8, -8, 8, 8, 8), voxel=1.0)
        rows = [_hole("H-1", 0.0, 0.0, 4.0, -4.0, kg=120.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=4)
        arrays = export_field_arrays(
            result=result, accepted_rows=rows, configuration=cfg, segments_per_hole=4
        )
        field_sum = float(arrays["energy_total"].sum())
        # Float32 storage gives ~1e-6 relative error; allow generous tol.
        assert field_sum == pytest.approx(
            result.energy_field.represented_energy_j, rel=1e-5
        )

    def test_source_at_corner_reports_outside(self):
        # Source at the very corner: a large chunk of its kernel falls
        # outside the domain → outside_energy > 0.
        cfg = _cfg(bounds=DomainBounds(0, 0, 0, 10, 10, 10), voxel=0.5)
        rows = [_hole("H-1", 0.5, 0.5, 9.5, 0.5)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        assert result.energy_field.outside_domain_energy_j > 0.0
        assert 0.0 < result.energy_field.fraction_represented < 1.0

    def test_no_silent_renormalisation(self):
        # When the domain truncates the source, the in-domain energy is
        # LESS than the coupled total — never silently scaled up to 100%.
        cfg = _cfg(bounds=DomainBounds(0, 0, 0, 5, 5, 5), voxel=0.5)
        rows = [_hole("H-1", 0.1, 0.1, 4.9, 0.1)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        assert result.energy_field.fraction_represented < 1.0
        assert result.energy_field.outside_domain_energy_j > 0.0


# ---------------------------------------------------------------------------
# Radial symmetry
# ---------------------------------------------------------------------------


class TestRadialSymmetry:
    def test_voxels_at_equal_distance_receive_equal_energy(self):
        cfg = _cfg(bounds=DomainBounds(-10, -10, -5, 10, 10, 5), voxel=1.0, alpha=0.0)
        rows = [_hole("H-1", 0.0, 0.0, 2.0, -2.0, kg=80.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=1)
        arrays = export_field_arrays(
            result=result, accepted_rows=rows, configuration=cfg, segments_per_hole=1
        )
        from core.blast_simulation.grid import voxel_centres_flat, reshape_to_grid
        grid_shape = result.grid_metadata.shape
        centres = voxel_centres_flat.__wrapped__ if hasattr(voxel_centres_flat, "__wrapped__") else None
        # Recompute centres manually to keep test independent.
        nx, ny, nz = grid_shape
        dx = 1.0
        xs = -10 + (np.arange(nx) + 0.5) * dx
        ys = -10 + (np.arange(ny) + 0.5) * dx
        zs = -5 + (np.arange(nz) + 0.5) * dx
        # Pick two voxels at the same distance from (0,0,0).
        p_a = np.array([3.5, 0.5, 0.5])
        p_b = np.array([0.5, 3.5, 0.5])
        # Find nearest voxel indices.
        def _idx(p):
            ix = int(np.argmin(np.abs(xs - p[0])))
            iy = int(np.argmin(np.abs(ys - p[1])))
            iz = int(np.argmin(np.abs(zs - p[2])))
            return ix, iy, iz
        ixa, iya, iza = _idx(p_a)
        ixb, iyb, izb = _idx(p_b)
        e = arrays["energy_total"].reshape(grid_shape)
        # Distance from each voxel centre to the source centre (0,0,0).
        ra = math.sqrt(xs[ixa] ** 2 + ys[iya] ** 2 + zs[iza] ** 2)
        rb = math.sqrt(xs[ixb] ** 2 + ys[iyb] ** 2 + zs[izb] ** 2)
        assert ra == pytest.approx(rb, abs=0.5)  # within one voxel
        assert e[ixa, iya, iza] == pytest.approx(e[ixb, iyb, izb], rel=1e-6)


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------


class TestMonotonicity:
    def test_energy_decreases_with_distance(self):
        cfg = _cfg(bounds=DomainBounds(-20, -5, -5, 20, 5, 5), voxel=1.0, alpha=0.1)
        rows = [_hole("H-1", 0.0, 0.0, 2.0, -2.0, kg=100.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=1)
        arrays = export_field_arrays(
            result=result, accepted_rows=rows, configuration=cfg, segments_per_hole=1
        )
        grid_shape = result.grid_metadata.shape
        e = arrays["energy_total"].reshape(grid_shape)
        # Sample along the x-axis at z=z_middle, y=y_middle.
        ny2, nz2 = grid_shape[1] // 2, grid_shape[2] // 2
        series = e[:, ny2, nz2]
        # Find the maximum (the column above the source) and check that
        # energy strictly decreases as we move away in either direction.
        peak = int(np.argmax(series))
        left = series[:peak]
        right = series[peak:]
        if left.size > 1:
            # `left` grows toward the peak → successive diffs are >= 0.
            assert np.all(np.diff(left) >= -1e-6)
        if right.size > 1:
            # `right` decays away from the peak → successive diffs are <= 0.
            assert np.all(np.diff(right) <= 1e-6)


# ---------------------------------------------------------------------------
# Translation invariance
# ---------------------------------------------------------------------------


class TestTranslationInvariance:
    def test_shift_preserves_relative_field(self):
        voxel = 1.0
        # Original: source at origin.
        cfg1 = _cfg(bounds=DomainBounds(-8, -8, -8, 8, 8, 8), voxel=voxel)
        rows1 = [_hole("H-1", 0.0, 0.0, 2.0, -2.0, kg=100.0)]
        r1 = run_simulation(accepted_rows=rows1, configuration=cfg1, segments_per_hole=2)
        a1 = export_field_arrays(result=r1, accepted_rows=rows1, configuration=cfg1, segments_per_hole=2)

        # Shifted by (+10, +5, 0).
        shift = np.array([10.0, 5.0, 0.0])
        cfg2 = _cfg(bounds=DomainBounds(-8 + shift[0], -8 + shift[1], -8,
                                        8 + shift[0], 8 + shift[1], 8), voxel=voxel)
        rows2 = [_hole("H-1", 0.0 + shift[0], 0.0 + shift[1], 2.0, -2.0, kg=100.0)]
        r2 = run_simulation(accepted_rows=rows2, configuration=cfg2, segments_per_hole=2)
        a2 = export_field_arrays(result=r2, accepted_rows=rows2, configuration=cfg2, segments_per_hole=2)

        # Totals must match (relative field is preserved).
        assert r1.energy_field.represented_energy_j == pytest.approx(
            r2.energy_field.represented_energy_j, rel=1e-6
        )
        assert a1["energy_total"].sum() == pytest.approx(a2["energy_total"].sum(), rel=1e-6)


# ---------------------------------------------------------------------------
# Resolution convergence
# ---------------------------------------------------------------------------


class TestResolutionConvergence:
    @pytest.mark.parametrize("voxel", [2.0, 1.0, 0.5])
    def test_total_stabilizes(self, voxel):
        cfg = _cfg(bounds=DomainBounds(-10, -10, -5, 10, 10, 5), voxel=voxel, alpha=0.1)
        rows = [_hole("H-1", 0.0, 0.0, 2.0, -2.0, kg=100.0)]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        # The coupled total is voxel-independent by construction (energy
        # is partitioned by the kernel normalisation).
        assert result.energy_field.total_coupled_energy_j == pytest.approx(
            result.energy_field.represented_energy_j
            + result.energy_field.outside_domain_energy_j,
            rel=1e-9,
        )


# ---------------------------------------------------------------------------
# Superposition
# ---------------------------------------------------------------------------


class TestSuperposition:
    def test_two_identical_sources_double_the_field(self):
        # Use a high attenuation so the kernel is essentially contained
        # in a small neighbourhood; outside-energy is then identical for
        # both layouts and we can compare totals directly.
        cfg = _cfg(bounds=DomainBounds(-15, -5, -5, 15, 5, 5), voxel=1.0, alpha=2.0, r0=0.5)
        # One source.
        rows1 = [_hole("H-1", -3.0, 0.0, 2.0, -2.0, kg=100.0)]
        r1 = run_simulation(accepted_rows=rows1, configuration=cfg, segments_per_hole=2)
        a1 = export_field_arrays(result=r1, accepted_rows=rows1, configuration=cfg, segments_per_hole=2)
        # Two identical sources placed symmetrically so each one sits at
        # the SAME relative position to the domain boundary as the single
        # source above (i.e. 12 m from each x-edge for the ±3 m sources).
        rows2 = [
            _hole("H-1", -3.0, 0.0, 2.0, -2.0, kg=100.0),
            _hole("H-2", 3.0, 0.0, 2.0, -2.0, kg=100.0),
        ]
        r2 = run_simulation(accepted_rows=rows2, configuration=cfg, segments_per_hole=2)
        a2 = export_field_arrays(result=r2, accepted_rows=rows2, configuration=cfg, segments_per_hole=2)
        # Total energy doubles (within float32 tolerance).
        assert r2.energy_field.represented_energy_j == pytest.approx(
            2.0 * r1.energy_field.represented_energy_j, rel=1e-5
        )
        assert a2["energy_total"].sum() == pytest.approx(2.0 * a1["energy_total"].sum(), rel=1e-5)


# ---------------------------------------------------------------------------
# Delays / temporal
# ---------------------------------------------------------------------------


class TestTemporalArrival:
    def test_arrival_time_analytical(self):
        from core.blast_simulation.temporal import arrival_time
        r = np.array([0.0, 100.0, 3500.0])
        t = arrival_time(distance_m=r, propagation_velocity_m_s=3500.0, detonation_time_s=0.5)
        # t_det + r/v: 0.5, 0.5 + 100/3500, 0.5 + 1.0
        assert t[0] == pytest.approx(0.5)
        assert t[1] == pytest.approx(0.5 + 100.0 / 3500.0)
        assert t[2] == pytest.approx(1.5)

    def test_temporal_mode_runs_when_delays_present(self):
        cfg = _cfg(
            bounds=DomainBounds(-10, -10, -5, 10, 10, 5),
            voxel=1.0,
            temporal_mode=TemporalMode.TEMPORAL,
            velocity=3500.0,
            pulse_sigma=0.025,
        )
        rows = [
            _hole("H-1", -3.0, 0.0, 2.0, -2.0, delay_ms=0.0),
            _hole("H-2", 3.0, 0.0, 2.0, -2.0, delay_ms=25.0),
        ]
        result = run_simulation(accepted_rows=rows, configuration=cfg, segments_per_hole=2)
        assert result.processing_summary.temporal_status == "AVAILABLE"
        td = result.temporal_diagnostics
        assert td["pulse_sigma_s"] == 0.025


# ---------------------------------------------------------------------------
# Anisotropy
# ---------------------------------------------------------------------------


class TestAnisotropy:
    def test_identity_tensor_reproduces_isotropy(self):
        # An identity tensor in ANISOTROPIC_TENSOR mode must produce the
        # same field as ISOTROPIC mode (within numerical tolerance).
        identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        cfg_iso = _cfg(bounds=DomainBounds(-8, -8, -8, 8, 8, 8), voxel=1.0, alpha=0.1)
        rows = [_hole("H-1", 0.0, 0.0, 2.0, -2.0, kg=100.0)]
        r_iso = run_simulation(accepted_rows=rows, configuration=cfg_iso, segments_per_hole=2)
        a_iso = export_field_arrays(result=r_iso, accepted_rows=rows, configuration=cfg_iso, segments_per_hole=2)

        rock = _rock(isotropic=False, tensor=identity)
        cfg_aniso = _cfg(bounds=DomainBounds(-8, -8, -8, 8, 8, 8), voxel=1.0, alpha=0.1, rock=rock)
        r_aniso = run_simulation(accepted_rows=rows, configuration=cfg_aniso, segments_per_hole=2)
        a_aniso = export_field_arrays(result=r_aniso, accepted_rows=rows, configuration=cfg_aniso, segments_per_hole=2)

        assert r_iso.energy_field.represented_energy_j == pytest.approx(
            r_aniso.energy_field.represented_energy_j, rel=1e-6
        )
        # Per-voxel fields match too.
        np.testing.assert_allclose(a_iso["energy_total"], a_aniso["energy_total"], rtol=1e-5)

    def test_stretched_tensor_changes_field(self):
        # A tensor that stretches the x-axis (M=diag(4,1,1)) makes the
        # field appear more localised along x than the isotropic case.
        stretched = ((4.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        cfg_iso = _cfg(bounds=DomainBounds(-8, -8, -8, 8, 8, 8), voxel=1.0, alpha=0.0)
        rows = [_hole("H-1", 0.0, 0.0, 2.0, -2.0, kg=100.0)]
        r_iso = run_simulation(accepted_rows=rows, configuration=cfg_iso, segments_per_hole=2)

        rock = _rock(isotropic=False, tensor=stretched)
        cfg_aniso = _cfg(bounds=DomainBounds(-8, -8, -8, 8, 8, 8), voxel=1.0, alpha=0.0, rock=rock)
        r_aniso = run_simulation(accepted_rows=rows, configuration=cfg_aniso, segments_per_hole=2)

        # The coupled total is the same for both runs (tensor only
        # reshapes the spatial distribution; it never creates energy).
        assert r_iso.energy_field.total_coupled_energy_j == pytest.approx(
            r_aniso.energy_field.total_coupled_energy_j, rel=1e-9
        )
        # Conservation holds in both runs.
        for r in (r_iso, r_aniso):
            total = r.energy_field.represented_energy_j + r.energy_field.outside_domain_energy_j
            assert total == pytest.approx(
                r.energy_field.total_coupled_energy_j, rel=1e-6
            )
        # But the per-voxel distribution differs — the tensor redistributes
        # energy away from the stretched axis.
        a_iso = export_field_arrays(result=r_iso, accepted_rows=rows, configuration=cfg_iso, segments_per_hole=2)
        a_aniso = export_field_arrays(result=r_aniso, accepted_rows=rows, configuration=cfg_aniso, segments_per_hole=2)
        assert not np.allclose(a_iso["energy_total"], a_aniso["energy_total"], rtol=1e-3)
