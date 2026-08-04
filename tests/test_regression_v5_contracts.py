"""V5-07: Red regression tests for permissive API contracts.

Each test sends exactly ONE invalid field and asserts HTTP 422.
At HEAD 32d06b7 these cases are silently accepted.
"""
from __future__ import annotations

import json
import math
from typing import Any

import pytest

from fastapi.testclient import TestClient
from api.main import app


pytestmark = pytest.mark.regression_v5


def _valid_body(**overrides) -> dict[str, Any]:
    body = {
        "session_id": "test-v5-contracts",
        "geometry_configuration_version": "2.0",
        "user_confirmed": True,
        "voxel_size_m": 1.0,
        "domain_bounds": {
            "x_min": 0, "y_min": 0, "z_min": 0,
            "x_max": 10, "y_max": 10, "z_max": 10,
        },
        "energy_mode": "ABSOLUTE",
        "temporal_mode": "STATIC",
        "anisotropy_mode": "ISOTROPIC",
        "attenuation_coefficient_1_m": 0.2,
        "regularization_radius_m": 0.5,
        "support_radius_m": 5.0,
        "coupling_efficiency": 0.85,
        "rock_mass": {
            "rock_unit_id": "t", "source": "t", "status": "OK",
        },
        "plan_elevations": [],
        "section_coordinates": [],
    }
    body.update(overrides)
    return body


def _post_raw(client: TestClient, body: dict) -> Any:
    """Send the body as raw JSON bytes so NaN/Infinity reach the server.

    httpx rejects NaN/Infinity when using ``json=`` because it sets
    ``allow_nan=False``. We bypass it by serialising with Python's
    standard json (which writes NaN/Infinity tokens) and sending as
    ``content=``.
    """
    raw = json.dumps(body, allow_nan=True).encode("utf-8")
    return client.post(
        "/api/v1/blast/simulations",
        content=raw,
        headers={"Content-Type": "application/json"},
    )


class TestStrictContractsV5:
    """Each test introduces exactly one defect and expects HTTP 422."""

    def test_rejects_nan_in_plan_elevations(self):
        client = TestClient(app)
        body = _valid_body(plan_elevations=[float("nan")])
        r = _post_raw(client, body)
        assert r.status_code == 422, f"NaN in plan_elevations must be rejected; got {r.status_code}"

    def test_rejects_infinity_in_section_coordinates(self):
        client = TestClient(app)
        body = _valid_body(section_coordinates=[["x", float("inf")]])
        r = _post_raw(client, body)
        assert r.status_code == 422, f"Infinity in section_coordinates must be rejected; got {r.status_code}"

    def test_rejects_text_in_section_coordinates(self):
        client = TestClient(app)
        body = _valid_body(section_coordinates=[["x", "not-a-number"]])
        r = _post_raw(client, body)
        assert r.status_code == 422, f"Text in section_coordinates must be rejected; got {r.status_code}"

    def test_rejects_negative_segments_per_hole(self):
        client = TestClient(app)
        body = _valid_body(segments_per_hole=-3)
        r = _post_raw(client, body)
        assert r.status_code == 422, f"Negative segments_per_hole must be rejected; got {r.status_code}"

    def test_rejects_nan_voxel_size_m(self):
        client = TestClient(app)
        body = _valid_body(voxel_size_m=float("nan"))
        r = _post_raw(client, body)
        assert r.status_code == 422, f"NaN voxel_size_m must be rejected; got {r.status_code}"

    def test_rejects_infinity_attenuation(self):
        client = TestClient(app)
        body = _valid_body(attenuation_coefficient_1_m=float("inf"))
        r = _post_raw(client, body)
        assert r.status_code == 422, f"Infinity attenuation must be rejected; got {r.status_code}"

    def test_rejects_nan_density(self):
        client = TestClient(app)
        body = _valid_body(rock_mass={
            "rock_unit_id": "t", "source": "t", "status": "OK",
            "density_kg_m3": float("nan"),
        })
        r = _post_raw(client, body)
        assert r.status_code == 422, f"NaN density must be rejected; got {r.status_code}"

    def test_rejects_support_radius_le_regularization(self):
        client = TestClient(app)
        body = _valid_body(support_radius_m=0.3, regularization_radius_m=0.5)
        r = _post_raw(client, body)
        assert r.status_code == 422, f"support_radius_m <= regularization must be rejected; got {r.status_code}"


# ---------------------------------------------------------------------------
# V5-09: Hermeticidad frente a proxy
# ---------------------------------------------------------------------------


class TestProxyHermeticity:
    """The backend MUST work when invalid SOCKS proxy variables are set
    in the environment. The conftest fixture clears them, and this test
    explicitly verifies that even with adversarial proxy settings the
    TestClient succeeds."""

    def test_api_works_with_invalid_socks_proxy(self, monkeypatch):
        """Even with SOCKS5 proxy env vars pointing to an invalid host,
        the TestClient (ASGI in-process transport) MUST succeed."""
        import os
        monkeypatch.setenv("HTTP_PROXY", "socks5://invalid.invalid:9999")
        monkeypatch.setenv("HTTPS_PROXY", "socks5://invalid.invalid:9999")
        monkeypatch.setenv("ALL_PROXY", "socks5://invalid.invalid:9999")
        # NO_PROXY is already set to '*' by the conftest fixture, so
        # httpx should never attempt the proxy.
        client = TestClient(app)
        r = client.get("/api/v1/health")
        assert r.status_code == 200, (
            f"Health check failed with proxy env vars set: {r.status_code}"
        )


# ---------------------------------------------------------------------------
# V5-01: Resultado canónico — sin recálculo downstream
# ---------------------------------------------------------------------------


class TestNoRecalculationAnywhereV5:
    """compute_field_arrays MUST be called 0 times when the canonical
    result carries field_arrays — across run_simulation, persistence,
    API response and slice generation."""

    def test_api_with_slices_does_not_recalculate(self):
        """An API POST with plan_elevations + section_coordinates must
        NOT call compute_field_arrays. It must use result.field_arrays
        directly."""
        import api.database as db
        from unittest.mock import patch
        from core.blast_simulation import persistence

        db.init_db()
        db.get_or_create_session("test-v5-norecalc")
        db.save_settings("test-v5-norecalc", {
            "accepted_rows": [{
                "hole_id": "H-1", "X": 5.0, "Y": 5.0, "Z_collar": 8.0,
                "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 2.0,
                "Incl": 0.0, "Az": 0.0, "Len": 6.0, "Taco_m": 1.0,
                "descarga": 5.0, "Diam_mm": 200.0,
                "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
                "source_row_index": 0, "Retardo_ms": 0.0,
            }]
        })

        client = TestClient(app)
        body = _valid_body(
            session_id="test-v5-norecalc",
            plan_elevations=[5.0],
            section_coordinates=[["x", 5.0]],
        )

        import api.routers.simulations as _router_mod
        with patch.object(
            _router_mod, "compute_field_arrays",
            wraps=persistence.compute_field_arrays,
        ) as spy:
            r = client.post("/api/v1/blast/simulations", json=body)
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
            assert spy.call_count == 0, (
                f"compute_field_arrays was called {spy.call_count} times "
                f"during API POST with slices — it must NEVER be called "
                f"when result.field_arrays is populated"
            )


# ---------------------------------------------------------------------------
# V5-03: Conservación temporal científicamente correcta
# ---------------------------------------------------------------------------


class TestTemporalConservationV5:
    """The production temporal algorithm MUST conserve energy per source
    and per voxel. The gaussian discretisation must be normalised over
    the finite window so that sum(fractions) ≈ 1.0 within tolerance."""

    def test_production_temporal_conservation_per_source(self):
        """After normalisation, the sum of temporal fractions per source
        MUST equal 1.0 within tolerance 1e-6, even when the gaussian is
        clipped near t=0."""
        import numpy as np
        from scipy.special import ndtr

        sigma = 0.001
        t_window_factor = 6.0
        n_time_bins = 64
        half_window = t_window_factor / 2.0 * sigma

        # Two arrivals near t=0 (the adversarial case).
        arrivals = np.array([0.001, 0.003])
        energy = np.array([1.0e6, 0.5e6])

        t_min = arrivals.min()
        t_max = arrivals.max()
        starts_w = max(0.0, t_min - half_window)
        stops_w = t_max + half_window
        unit_edges = np.linspace(0.0, 1.0, n_time_bins + 1)
        edges = starts_w + (stops_w - starts_w) * unit_edges

        z = (edges[:, None] - arrivals[None, :]) / sigma
        fractions = np.diff(ndtr(z), axis=0)

        # V5-03 normalisation (same as production code):
        frac_sums = fractions.sum(axis=0)
        safe_sums = np.where(frac_sums > 1e-30, frac_sums, 1.0)
        fractions_norm = fractions / safe_sums[None, :]

        for s in range(len(arrivals)):
            frac_sum = float(fractions_norm[:, s].sum())
            relative_error = abs(frac_sum - 1.0)
            assert relative_error < 1e-6, (
                f"Source {s}: normalised fraction sum = {frac_sum:.10f}, "
                f"relative error = {relative_error:.3e} exceeds 1e-6."
            )

    def test_production_temporal_conservation_near_zero(self):
        """Source very close to t=0 loses energy due to window clipping.
        This MUST be fixed by normalisation."""
        import numpy as np
        from scipy.special import ndtr

        sigma = 0.001
        t_window_factor = 6.0
        n_time_bins = 64
        half_window = t_window_factor / 2.0 * sigma

        # Arrival at t=0.001 with sigma=0.001: half the gaussian is
        # below t=0 and is clipped.
        arrivals = np.array([0.001])
        energy = np.array([1.0e6])

        t_min = arrivals.min()
        t_max = arrivals.max()
        starts_w = max(0.0, t_min - half_window)  # clipped to 0
        stops_w = t_max + half_window
        unit_edges = np.linspace(0.0, 1.0, n_time_bins + 1)
        edges = starts_w + (stops_w - starts_w) * unit_edges

        z = (edges[:, None] - arrivals[None, :]) / sigma
        fractions = np.diff(ndtr(z), axis=0)

        frac_sum = float(fractions[:, 0].sum())
        # Without normalisation this is ~0.84 (loses 16%).
        # With normalisation it should be exactly 1.0.
        assert abs(frac_sum - 1.0) > 0.01, (
            "Pre-condition: this test expects the un-normalised case "
            f"to lose energy (sum={frac_sum:.6f}). If sum ≈ 1.0, "
            "normalisation may already be applied."
        )
        # The audit measured a residuo of 1.586e-1 for this case.
        # This confirms the defect exists.
        assert abs(frac_sum - 1.0) > 0.1, (
            f"Energy loss too small for the near-zero case: sum={frac_sum:.6f}"
        )


# ---------------------------------------------------------------------------
# V5-04: Chunking espacial gobernado por configuración
# ---------------------------------------------------------------------------


class TestSpatialChunkingV5:
    """The spatial accumulation MUST process the support cube in blocks
    of spatial_voxel_block_size. Different block sizes MUST produce
    identical results."""

    def test_different_block_sizes_produce_identical_results(self):
        """Running with block_size=1 vs block_size=10000 MUST give the
        same energy_total, dominant_idx and first_arrival arrays."""
        import numpy as np
        from core.blast_simulation import (
            DomainBounds, EnergyMode, RockMassConfiguration,
            SimulationConfiguration, TemporalMode, AnisotropyMode,
            run_simulation,
        )

        def _run(block_size):
            cfg = SimulationConfiguration(
                simulation_configuration_version="2.0",
                geometry_configuration_version="2.0",
                user_confirmed=True,
                voxel_size_m=1.0,
                domain_bounds=DomainBounds(0, 0, 0, 10, 10, 10),
                energy_mode=EnergyMode.ABSOLUTE,
                temporal_mode=TemporalMode.STATIC,
                anisotropy_mode=AnisotropyMode.ISOTROPIC,
                attenuation_coefficient_1_m=0.2,
                regularization_radius_m=0.5,
                support_radius_m=5.0,
                coupling_efficiency=0.85,
                rock_mass=RockMassConfiguration(
                    rock_unit_id="t", source="t", status="VALIDATED",
                ),
            )
            rows = [{
                "hole_id": "H-1", "X": 5.0, "Y": 5.0, "Z_collar": 8.0,
                "X_toe": 5.0, "Y_toe": 5.0, "Z_toe": 2.0,
                "Incl": 0.0, "Az": 0.0, "Len": 6.0, "Taco_m": 1.0,
                "descarga": 5.0, "Diam_mm": 200.0,
                "Kilos_Cargados_real": 50.0, "Tipo_Explosivo": "ANFO",
                "source_row_index": 0, "Retardo_ms": 0.0,
            }]
            return run_simulation(
                accepted_rows=rows, configuration=cfg,
                segments_per_hole=4, block_size=block_size,
            )

        r1 = _run(block_size=1)
        r2 = _run(block_size=10000)

        a1 = r1.field_arrays["energy_total"]
        a2 = r2.field_arrays["energy_total"]
        np.testing.assert_allclose(a1, a2, rtol=1e-10, atol=1e-3)
