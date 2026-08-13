"""V6-03: Real spatial chunking — no global concatenation of per-block
deposit arrays.

The V5 ``_accumulate_source`` divided the offset cube into blocks of
``spatial_voxel_block_size`` but then **retained every block's deposit
arrays** in ``deposit_idx_all`` / ``deposit_energies_all`` and
concatenated them at the end into a single per-source tuple handed to
the temporal layer. The audit's adversarial reproduction
(``block_size=1``) showed the final ``deposit_idx`` carrying 536
elements — the limit controlled local computations but NOT the largest
auxiliary retained per source.

V6-03 requires:

* No global list + ``np.concatenate`` for deposit arrays.
* The temporal layer is fed one tuple per (source, spatial-block) so
  the largest per-source auxiliary is bounded by
  ``spatial_voxel_block_size``.
* Physics parity is preserved (same ``energy_total``,
  ``dominant_idx``, ``first_arrival_s`` and ``time_of_max_s``
  regardless of ``block_size``).

The structural test runs in TEMPORAL mode so the per-block tuples are
observable through ``_compute_temporal_fields_streaming``'s
``segment_infos`` argument; it asserts that no tuple's ``dep_idx``
exceeds ``block_size``.
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


def _make_config(
    *,
    support_radius_m: float = 5.0,
    anisotropy_mode: str = AnisotropyMode.ISOTROPIC,
    anisotropy_tensor: tuple[tuple[float, ...], ...] | None = None,
    temporal_mode: str = TemporalMode.TEMPORAL,
) -> SimulationConfiguration:
    rock = RockMassConfiguration(
        rock_unit_id="t",
        source="t",
        status="VALIDATED",
        anisotropy_mode=anisotropy_mode,
        anisotropy_tensor=anisotropy_tensor,
    )
    kwargs: dict[str, Any] = dict(
        simulation_configuration_version="2.0",
        geometry_configuration_version="2.0",
        user_confirmed=True,
        voxel_size_m=1.0,
        domain_bounds=DomainBounds(0, 0, 0, 10, 10, 10),
        energy_mode=EnergyMode.ABSOLUTE,
        temporal_mode=temporal_mode,
        anisotropy_mode=anisotropy_mode,
        attenuation_coefficient_1_m=0.2,
        regularization_radius_m=0.5,
        support_radius_m=support_radius_m,
        coupling_efficiency=0.85,
        propagation_velocity_m_s=3500.0,
        propagation_velocity_source="lab",
        pulse_sigma_s=0.001,
        rock_mass=rock,
    )
    return SimulationConfiguration(**kwargs)


def _single_hole(
    *,
    x: float = 5.0,
    y: float = 5.0,
    z_collar: float = 8.0,
    z_toe: float = 2.0,
    hole_id: str = "H-1",
    retardo_ms: float = 0.0,
) -> dict[str, Any]:
    return {
        "hole_id": hole_id, "X": x, "Y": y, "Z_collar": z_collar,
        "X_toe": x, "Y_toe": y, "Z_toe": z_toe,
        "Incl": 0.0, "Az": 0.0, "Len": abs(z_collar - z_toe),
        "Taco_m": 1.0, "descarga": abs(z_collar - z_toe) - 1.0,
        "Diam_mm": 200.0, "Kilos_Cargados_real": 50.0,
        "Tipo_Explosivo": "ANFO", "source_row_index": 0,
        "Retardo_ms": retardo_ms,
    }


def _capture_segment_infos():
    """Build a (spy, captured) pair that records the ``segment_infos``
    list handed to ``_compute_temporal_fields_streaming``."""
    import core.blast_simulation.engine as engine_mod

    captured: dict[str, Any] = {}
    original = engine_mod._compute_temporal_fields_streaming

    def spy(*args, **kwargs):
        segment_infos = kwargs.get("segment_infos")
        if segment_infos is None and args:
            # positional — find by position in the original signature.
            import inspect
            sig = inspect.signature(original)
            params = list(sig.parameters.keys())
            if "segment_infos" in params:
                captured["segment_infos"] = args[params.index("segment_infos")]
        else:
            captured["segment_infos"] = segment_infos
        return original(*args, **kwargs)

    return spy, captured


# ---------------------------------------------------------------------------
# V6-03.a — Per-block streaming: largest aux respects block_size
#
# V6-04 follow-up: the spy on ``_compute_temporal_fields_streaming`` is
# no longer applicable — that function was eliminated when the global
# temporal list was removed. The "no retention" invariant is now covered
# by ``test_regression_v6_temporal_retention.py::
# TestNoGlobalTemporalRetention::test_temporal_post_pass_not_invoked``.
# The spatial chunking parity tests below remain valid.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# V6-03.b — Physics parity across block sizes (regression guard)
# ---------------------------------------------------------------------------


class TestSpatialChunkingParity:
    """The simulation result MUST be invariant under different
    ``block_size`` values. This guards the V5 parity test under the
    new per-block streaming code path."""

    @pytest.mark.parametrize(
        ("support_radius_m", "anisotropy"),
        [
            (2.0, AnisotropyMode.ISOTROPIC),
            (5.0, AnisotropyMode.ISOTROPIC),
            (5.0, AnisotropyMode.ANISOTROPIC_TENSOR),
        ],
    )
    def test_energy_field_invariant_under_block_size(
        self, support_radius_m, anisotropy
    ):
        tensor = None
        if anisotropy == AnisotropyMode.ANISOTROPIC_TENSOR:
            tensor = (
                (1.0, 0.0, 0.0),
                (0.0, 2.0, 0.0),
                (0.0, 0.0, 1.5),
            )

        def _run(block_size):
            cfg = _make_config(
                support_radius_m=support_radius_m,
                anisotropy_mode=anisotropy,
                anisotropy_tensor=tensor,
                temporal_mode=TemporalMode.TEMPORAL,
            )
            return run_simulation(
                accepted_rows=[_single_hole()],
                configuration=cfg,
                segments_per_hole=4,
                block_size=block_size,
            )

        r_small = _run(block_size=1)
        r_large = _run(block_size=10_000)
        a1 = r_small.field_arrays["energy_total"]
        a2 = r_large.field_arrays["energy_total"]
        np.testing.assert_allclose(a1, a2, rtol=1e-10, atol=1e-6)

        fa1 = r_small.field_arrays["first_arrival_s"]
        fa2 = r_large.field_arrays["first_arrival_s"]
        np.testing.assert_allclose(fa1, fa2, rtol=1e-8, atol=1e-9, equal_nan=True)

        tm1 = r_small.field_arrays["time_of_max_s"]
        tm2 = r_large.field_arrays["time_of_max_s"]
        np.testing.assert_allclose(tm1, tm2, rtol=1e-8, atol=1e-9, equal_nan=True)
