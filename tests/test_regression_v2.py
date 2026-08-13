"""Red regression tests for the v2 remediation blocking defects.

Each test reproduces a defect that exists at HEAD ``787a89e``. They MUST
fail before the fix and pass afterwards. Run them with ``-m regression_v2``
to scope a CI check.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

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
    persistence,
    run_simulation,
)
from core.blast_simulation.kernels import discrete_total_mass


pytestmark = pytest.mark.regression_v2


def _cfg(*, R: float, **overrides) -> SimulationConfiguration:
    """Build a minimal valid configuration with explicit support radius."""
    defaults = dict(
        simulation_configuration_version=SIMULATION_CONFIGURATION_VERSION,
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=DomainBounds(0, 0, 0, 20, 20, 20),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=TemporalMode.STATIC,
        anisotropy_mode=AnisotropyMode.ISOTROPIC,
        kernel_type=KernelType.EXPONENTIAL_INVERSE_SQUARE,
        attenuation_coefficient_1_m=0.2,
        regularization_radius_m=0.5,
        support_radius_m=R,
        coupling_efficiency=0.85,
        rock_mass=RockMassConfiguration(
            rock_unit_id="t", source="t", status="VALIDATED",
        ),
    )
    defaults.update(overrides)
    return SimulationConfiguration(**defaults)


def _one_hole() -> list[dict[str, Any]]:
    return [{
        "hole_id": "H-1", "X": 10.0, "Y": 10.0, "Z_collar": 15.0,
        "X_toe": 10.0, "Y_toe": 10.0, "Z_toe": 5.0,
        "Incl": 0.0, "Az": 0.0, "Len": 10.0, "Taco_m": 1.0,
        "descarga": 9.0, "Diam_mm": 200.0,
        "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
        "source_row_index": 0, "Retardo_ms": 0.0,
    }]


# ---------------------------------------------------------------------------
# Falla 4.1 — memoria vs NPZ divergencia por default oculto de 5 m
# ---------------------------------------------------------------------------


class TestSupportRadiusMemoryNpzParity:
    """Reproduce the audit case: changing R in the contract does not
    change the persisted NPZ because compute_field_arrays falls back to
    the hidden SIMULATION.default_support_radius_m = 5 m."""

    @pytest.mark.parametrize("R", [2.0, 5.0, 9.0])
    def test_memory_energy_matches_npz_energy_for_each_R(self, R: float, tmp_path: Path):
        cfg = _cfg(R=R)
        rows = _one_hole()
        result = run_simulation(accepted_rows=rows, configuration=cfg)
        memory_energy = result.energy_field.represented_energy_j
        memory_active = result.energy_field.active_voxels

        # Persist via the public API used by the router.
        updated, npz_path, _sha, _summary = persistence.write_atomic_simulation(
            result=result,
            accepted_rows=rows,
            configuration=cfg,
            data_dir=tmp_path,
        )
        # Reload the NPZ with allow_pickle=False and compare aggregates.
        with np.load(npz_path, allow_pickle=False) as data:
            npz_energy = float(data["energy_total"].sum())
            npz_active = int((data["energy_total"] > 0).sum())

        # The NPZ MUST match the in-memory result for the SAME R.
        # Tolerance: float32 storage gives ~1e-5 rel error.
        assert npz_energy == pytest.approx(memory_energy, rel=1e-5), (
            f"R={R}: NPZ energy {npz_energy:.2f} != memory {memory_energy:.2f}"
        )
        assert npz_active == memory_active, (
            f"R={R}: NPZ active_voxels {npz_active} != memory {memory_active}"
        )

    def test_changing_R_changes_npz_active_voxels(self, tmp_path: Path):
        """R=2 vs R=9 MUST produce different NPZ fields."""
        rows = _one_hole()
        npz_actives = {}
        for R in (2.0, 9.0):
            cfg = _cfg(R=R)
            result = run_simulation(accepted_rows=rows, configuration=cfg)
            _updated, npz_path, _sha, _sum = persistence.write_atomic_simulation(
                result=result, accepted_rows=rows, configuration=cfg,
                data_dir=tmp_path / f"R{R}",
            )
            with np.load(npz_path, allow_pickle=False) as data:
                npz_actives[R] = int((data["energy_total"] > 0).sum())
        assert npz_actives[2.0] != npz_actives[9.0], (
            f"NPZ active_voxels must differ between R=2 ({npz_actives[2.0]}) "
            f"and R=9 ({npz_actives[9.0]}); the hidden default of 5 m is leaking"
        )
        # Larger support MUST reach more voxels.
        assert npz_actives[9.0] > npz_actives[2.0]


# ---------------------------------------------------------------------------
# Falla 5.1 — soporte anisotrópico truncado
# ---------------------------------------------------------------------------


class TestAnisotropicSupportTruncation:
    """Reproduce: a tensor diag(0.25, 1, 1) with R=5 should reach a
    point at (9, 0, 0) (anisotropic distance = 4.5 m), but the current
    cubic extent [-R, R]³ truncates the search and misses it."""

    def test_anisotropic_point_inside_ellipsoid_receives_energy(self):
        # M = diag(0.25, 1, 1). Point at (9, 0, 0) relative to source:
        # Δxᵀ M Δx = 0.25 * 81 = 20.25; sqrt = 4.5 < R=5.
        tensor = (
            (0.25, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
        cfg = _cfg(
            R=5.0,
            anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
            rock_mass=RockMassConfiguration(
                rock_unit_id="t", source="t", status="VALIDATED",
                anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
                anisotropy_tensor=tensor,
            ),
        )
        # Source at (10, 10, 10) — the centre of the domain.
        # The point (19, 10, 10) is 9 m away in x → aniso distance 4.5 m.
        # Use a short vertical hole so the segment sits near (10, 10, 10).
        rows = [{
            "hole_id": "H-1", "X": 10.0, "Y": 10.0, "Z_collar": 10.5,
            "X_toe": 10.0, "Y_toe": 10.0, "Z_toe": 9.5,
            "Incl": 0.0, "Az": 0.0, "Len": 1.0, "Taco_m": 0.0,
            "descarga": 1.0, "Diam_mm": 100.0,
            "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
            "source_row_index": 0, "Retardo_ms": 0.0,
        }]
        result = run_simulation(accepted_rows=rows, configuration=cfg)
        arrays = compute_field_arrays(
            result=result, accepted_rows=rows, configuration=cfg,
        )
        centres = arrays["voxel_centres"]
        energy = arrays["energy_total"]
        # Locate the voxel whose centre is (19, 10, 10) (within dx/2).
        target = np.array([19.0, 10.0, 10.0])
        distances = np.linalg.norm(centres - target, axis=1)
        idx = int(np.argmin(distances))
        # The voxel MUST receive a positive contribution.
        assert energy[idx] > 0.0, (
            f"Anisotropic point (19,10,10) — distance to nearest voxel "
            f"centre = {distances[idx]:.3f} m — should receive energy but "
            f"got {energy[idx]:.6e} J. The support cube was truncated "
            f"to ±R instead of using M⁻¹-based extents."
        )

    def test_rotated_tensor_does_not_truncate_support(self):
        """A rotated SPD tensor must reach every point whose anisotropic
        distance is ≤ R. We rotate diag(0.25, 1, 1) by 45° around z and
        check the rotated point (0, 9, 0)*R45 = (-6.36, 6.36, 0) (which
        has anisotropic distance 4.5 m in the rotated frame)."""
        cos45 = math.sqrt(2.0) / 2.0
        sin45 = cos45
        # Build a rotated tensor: M = Rot(45) · diag(0.25,1,1) · Rot(45)ᵀ.
        # Eigenvectors point along (cos45, sin45, 0) and (-sin45, cos45, 0).
        # Equivalently, M_ij expressed in world axes has off-diagonal terms.
        # M = [[a, b, 0], [b, c, 0], [0, 0, 1]] where
        #   a = 0.25*cos² + 1*sin² = 0.25*0.5 + 0.5 = 0.625
        #   c = 0.25*sin² + 1*cos² = 0.625
        #   b = (0.25 - 1) * cos*sin = -0.75 * 0.5 = -0.375
        a = 0.625
        b = -0.375
        c = 0.625
        tensor = (
            (a, b, 0.0),
            (b, c, 0.0),
            (0.0, 0.0, 1.0),
        )
        cfg = _cfg(
            R=5.0,
            anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
            rock_mass=RockMassConfiguration(
                rock_unit_id="t", source="t", status="VALIDATED",
                anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
                anisotropy_tensor=tensor,
            ),
        )
        # Source at (10, 10, 10). Target at (10 + 9*cos45, 10 + 9*sin45, 10)
        # = (16.36, 16.36, 10) — anisotropic distance 4.5 m.
        tx = 10.0 + 9.0 * cos45
        ty = 10.0 + 9.0 * sin45
        rows = [{
            "hole_id": "H-1", "X": 10.0, "Y": 10.0, "Z_collar": 10.5,
            "X_toe": 10.0, "Y_toe": 10.0, "Z_toe": 9.5,
            "Incl": 0.0, "Az": 0.0, "Len": 1.0, "Taco_m": 0.0,
            "descarga": 1.0, "Diam_mm": 100.0,
            "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
            "source_row_index": 0, "Retardo_ms": 0.0,
        }]
        result = run_simulation(accepted_rows=rows, configuration=cfg)
        arrays = compute_field_arrays(
            result=result, accepted_rows=rows, configuration=cfg,
        )
        centres = arrays["voxel_centres"]
        energy = arrays["energy_total"]
        target = np.array([tx, ty, 10.0])
        distances = np.linalg.norm(centres - target, axis=1)
        idx = int(np.argmin(distances))
        assert energy[idx] > 0.0, (
            f"Rotated-tensor anisotropic point ({tx:.2f},{ty:.2f},10) "
            f"should receive energy but got {energy[idx]:.6e} J"
        )

    def test_identity_tensor_matches_isotropic(self):
        """The identity tensor must reproduce the isotropic kernel field
        bit-for-bit (within float32 tolerance)."""
        rows = _one_hole_identity_spot()
        cfg_iso = _cfg(R=5.0)
        result_iso = run_simulation(accepted_rows=rows, configuration=cfg_iso)
        arrays_iso = compute_field_arrays(
            result=result_iso, accepted_rows=rows, configuration=cfg_iso,
        )

        tensor_id = ((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0))
        cfg_aniso = _cfg(
            R=5.0,
            anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
            rock_mass=RockMassConfiguration(
                rock_unit_id="t", source="t", status="VALIDATED",
                anisotropy_mode=AnisotropyMode.ANISOTROPIC_TENSOR,
                anisotropy_tensor=tensor_id,
            ),
        )
        result_aniso = run_simulation(accepted_rows=rows, configuration=cfg_aniso)
        arrays_aniso = compute_field_arrays(
            result=result_aniso, accepted_rows=rows, configuration=cfg_aniso,
        )
        np.testing.assert_allclose(
            arrays_iso["energy_total"],
            arrays_aniso["energy_total"],
            rtol=1e-5, atol=1e-3,
        )


def _one_hole_identity_spot() -> list[dict[str, Any]]:
    """One short hole at the centre of the default domain."""
    return [{
        "hole_id": "H-1", "X": 10.0, "Y": 10.0, "Z_collar": 11.0,
        "X_toe": 10.0, "Y_toe": 10.0, "Z_toe": 9.0,
        "Incl": 0.0, "Az": 0.0, "Len": 2.0, "Taco_m": 0.0,
        "descarga": 2.0, "Diam_mm": 100.0,
        "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
        "source_row_index": 0, "Retardo_ms": 0.0,
    }]


# ---------------------------------------------------------------------------
# Falla 7 — chunking temporal real (no matrices densas n_vox × n_seg)
# ---------------------------------------------------------------------------


class TestTemporalChunkingBoundedMemory:
    """The temporal layer MUST NOT materialise a dense
    (n_voxels × n_segments) matrix. This test instruments the engine to
    detect any dense intermediate above a configured ceiling."""

    def test_no_dense_n_voxels_by_n_segments_materialised(self, monkeypatch):
        """Even with 100 holes × 8 segments and 8000 voxels in TEMPORAL
        mode, the peak buffer size observed MUST stay below the
        documented ``temporal_block_size`` ceiling.

        We monkeypatch ``np.column_stack`` to record the product of its
        output shape; if any column_stack produces a (n_vox, n_seg)
        matrix with n_vox × n_seg > temporal_block_size, we fail.
        """
        # Build a configuration large enough to expose the dense path.
        cfg = _cfg(
            R=5.0,
            voxel_size_m=1.0,
            domain_bounds=DomainBounds(0, 0, 0, 20, 20, 20),
            temporal_mode=TemporalMode.TEMPORAL,
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="lab",
            pulse_sigma_s=0.001,
        )
        rows = []
        for i in range(20):
            rows.append({
                "hole_id": f"H-{i:03d}", "X": float(2 + i % 18),
                "Y": float(2 + (i * 7) % 18), "Z_collar": 15.0,
                "X_toe": float(2 + i % 18), "Y_toe": float(2 + (i * 7) % 18),
                "Z_toe": 5.0, "Incl": 0.0, "Az": 0.0, "Len": 10.0,
                "Taco_m": 1.0, "descarga": 9.0, "Diam_mm": 200.0,
                "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
                "source_row_index": i, "Retardo_ms": float(i * 25),
            })

        # Instrument np.column_stack to record shape products.
        observed: list[int] = []
        original_column_stack = np.column_stack

        def _spy(arrays_list):
            result = original_column_stack(arrays_list)
            if result.ndim == 2:
                observed.append(int(result.shape[0] * result.shape[1]))
            return result

        monkeypatch.setattr(np, "column_stack", _spy)
        run_simulation(accepted_rows=rows, configuration=cfg)
        # With 8000 voxels × 160 segments the dense matrix would be 1.28M
        # elements. The chunked implementation MUST stay well below that.
        # ``temporal_block_size`` defaults to 50_000 elements.
        ceiling = 50_000
        worst = max(observed) if observed else 0
        assert worst <= ceiling, (
            f"Dense temporal buffer of {worst} elements exceeded ceiling "
            f"{ceiling} — np.column_stack materialised a full "
            f"(n_voxels × n_segments) matrix instead of chunking"
        )
