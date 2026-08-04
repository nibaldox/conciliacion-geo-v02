"""V6-01 (follow-up): cross-field scientific contract gaps that the
first V6-01 pass missed. Each test sends exactly ONE semantic defect
that the schema currently accepts but should reject with HTTP 422
before the engine runs.

The audit found these gaps after V6-01 was declared closed:

* ``temporal_mode=TEMPORAL`` without ``propagation_velocity_m_s``
  (schema accepts → HTTP 400 ``SIMULATION_INVALID``).
* ``temporal_mode=TEMPORAL`` with velocity but empty
  ``propagation_velocity_source`` (schema accepts → HTTP 400).
* Top-level ``anisotropy_mode=ANISOTROPIC_TENSOR`` with
  ``rock_mass.anisotropy_mode=ISOTROPIC`` (schema accepts → HTTP 400).
* Top-level ``anisotropy_mode=ISOTROPIC`` with
  ``rock_mass.anisotropy_mode=ANISOTROPIC_TENSOR`` + tensor supplied
  (schema accepts the contradiction).
* ``user_confirmed`` accepted as ``"true"`` / ``1`` / ``"false"`` /
  ``0`` — Pydantic lax coercion for ``bool`` accepts stringly-typed
  booleans and integers.

This file complements ``test_regression_v6_contracts.py`` (which
covers single-field type/enum/NaN defects) with the cross-field and
``StrictBool`` cases.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


pytestmark = pytest.mark.regression_v6


def _valid_body(**overrides) -> dict[str, Any]:
    body = {
        "session_id": "test-v6-cross",
        "geometry_configuration_version": "2.0",
        "user_confirmed": True,
        "voxel_size_m": 1.0,
        "domain_bounds": {
            "x_min": 0.0, "y_min": 0.0, "z_min": 0.0,
            "x_max": 10.0, "y_max": 10.0, "z_max": 10.0,
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
            "anisotropy_mode": "ISOTROPIC",
        },
        "plan_elevations": [],
        "section_coordinates": [],
    }
    body.update(overrides)
    return body


def _post_raw(client: TestClient, body: dict) -> Any:
    raw = json.dumps(body, allow_nan=True).encode("utf-8")
    return client.post(
        "/api/v1/blast/simulations",
        content=raw,
        headers={"Content-Type": "application/json"},
    )


def _assert_422_with_loc_prefix(response, *, expected_loc_prefix: tuple) -> None:
    """Assert HTTP 422 and that at least one validation error carries a
    ``loc`` whose prefix matches. The router normalises every Pydantic
    error to start with ``"body"`` so callers can rely on the FastAPI
    convention."""
    assert response.status_code == 422, (
        f"Expected HTTP 422, got {response.status_code}: {response.text[:300]}"
    )
    payload = response.json()
    details = payload.get("detail") or {}
    verrors = (
        details.get("details", {}).get("validation_errors")
        or details.get("validation_errors")
        or []
    )
    if not verrors and isinstance(details, list):
        verrors = details
    locs = [tuple(e.get("loc") or ()) for e in verrors]
    assert any(
        loc[: len(expected_loc_prefix)] == expected_loc_prefix for loc in locs
    ), (
        f"No validation error with loc prefix {expected_loc_prefix!r} in {locs!r}; "
        f"detail={details!r}"
    )


def _assert_engine_not_called(client: TestClient, body: dict) -> None:
    import api.routers.simulations as _router_mod
    with patch.object(_router_mod, "run_simulation") as spy:
        r = _post_raw(client, body)
        assert r.status_code == 422, (
            f"Expected 422 while instrumenting engine, got {r.status_code}"
        )
        assert spy.call_count == 0, (
            f"run_simulation was called {spy.call_count} times for an "
            f"invalid body — schema must reject before the engine."
        )


# ---------------------------------------------------------------------------
# V6-01.b — TEMPORAL mode cross-field requirements
# ---------------------------------------------------------------------------


class TestTemporalModeCrossField:
    """``temporal_mode=TEMPORAL`` MUST require a positive
    ``propagation_velocity_m_s`` AND a non-empty
    ``propagation_velocity_source`` — both at the schema layer so the
    failure is HTTP 422, not HTTP 400 from the engine."""

    def test_temporal_without_velocity_returns_422(self):
        client = TestClient(app)
        body = _valid_body(temporal_mode="TEMPORAL")
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(
            r, expected_loc_prefix=("body", "propagation_velocity_m_s")
        )

    def test_temporal_with_velocity_zero_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            temporal_mode="TEMPORAL",
            propagation_velocity_m_s=0.0,
            propagation_velocity_source="lab",
        )
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(
            r, expected_loc_prefix=("body", "propagation_velocity_m_s")
        )

    def test_temporal_with_negative_velocity_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            temporal_mode="TEMPORAL",
            propagation_velocity_m_s=-3500.0,
            propagation_velocity_source="lab",
        )
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(
            r, expected_loc_prefix=("body", "propagation_velocity_m_s")
        )

    def test_temporal_with_velocity_without_source_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            temporal_mode="TEMPORAL",
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="",
        )
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(
            r, expected_loc_prefix=("body", "propagation_velocity_source")
        )

    def test_temporal_with_velocity_without_source_key_returns_422(self):
        """Omit ``propagation_velocity_source`` entirely — the default
        empty string MUST still trigger the required-when-TEMPORAL
        check."""
        client = TestClient(app)
        body = _valid_body(
            temporal_mode="TEMPORAL",
            propagation_velocity_m_s=3500.0,
        )
        body.pop("propagation_velocity_source", None)
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(
            r, expected_loc_prefix=("body", "propagation_velocity_source")
        )

    def test_temporal_complete_is_accepted_at_schema_layer(self):
        """Positive control: TEMPORAL with velocity + source parses
        successfully at the schema layer."""
        from api.routers.simulations import SimulationCreateRequest
        body = _valid_body(
            temporal_mode="TEMPORAL",
            propagation_velocity_m_s=3500.0,
            propagation_velocity_source="lab",
        )
        req = SimulationCreateRequest.model_validate(body)
        assert req.propagation_velocity_m_s == 3500.0
        assert req.propagation_velocity_source == "lab"

    def test_temporal_without_velocity_does_not_run_engine(self):
        _assert_engine_not_called(
            TestClient(app), _valid_body(temporal_mode="TEMPORAL")
        )


# ---------------------------------------------------------------------------
# V6-01.c — anisotropy_mode consistency between top-level and rock_mass
# ---------------------------------------------------------------------------


class TestAnisotropyModeConsistency:
    """``SimulationCreateRequest.anisotropy_mode`` MUST equal
    ``rock_mass.anisotropy_mode``. The engine decides whether to apply
    the tensor using the TOP-LEVEL mode while persisting the nested
    one as macizo metadata; an inconsistency produces a field tagged
    isotropic that is reported as anisotropic (or vice versa)."""

    def test_top_anisotropic_rock_isotropic_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            anisotropy_mode="ANISOTROPIC_TENSOR",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ISOTROPIC",
            },
        )
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(r, expected_loc_prefix=("body",))

    def test_top_isotropic_rock_anisotropic_with_tensor_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            anisotropy_mode="ISOTROPIC",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ANISOTROPIC_TENSOR",
                "anisotropy_tensor": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
            },
        )
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(r, expected_loc_prefix=("body",))

    def test_top_isotropic_rock_isotropic_accepted(self):
        """Positive control: aligned ISOTROPIC modes parse OK."""
        from api.routers.simulations import SimulationCreateRequest
        body = _valid_body(
            anisotropy_mode="ISOTROPIC",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ISOTROPIC",
            },
        )
        req = SimulationCreateRequest.model_validate(body)
        assert req.anisotropy_mode == req.rock_mass.anisotropy_mode == "ISOTROPIC"

    def test_top_anisotropic_rock_anisotropic_with_valid_tensor_accepted(self):
        """Positive control: aligned ANISOTROPIC_TENSOR modes with a
        symmetric PD tensor parse OK (tensor requirement already
        covered by the V6-01 first pass)."""
        from api.routers.simulations import SimulationCreateRequest
        body = _valid_body(
            anisotropy_mode="ANISOTROPIC_TENSOR",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ANISOTROPIC_TENSOR",
                "anisotropy_tensor": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
            },
        )
        req = SimulationCreateRequest.model_validate(body)
        assert req.anisotropy_mode == req.rock_mass.anisotropy_mode == "ANISOTROPIC_TENSOR"


# ---------------------------------------------------------------------------
# V6-01.d — user_confirmed must be a real JSON boolean
# ---------------------------------------------------------------------------


class TestUserConfirmedStrictBool:
    """``user_confirmed`` MUST be a real JSON boolean. Pydantic lax
    coercion for ``bool`` accepts ``"true"``/``"false"`` strings and
    ``1``/``0`` integers; ``StrictBool`` rejects them so the schema
    layer returns HTTP 422."""

    @pytest.mark.parametrize(
        ("bad_value", "label"),
        [
            ("true", "string 'true'"),
            ("false", "string 'false'"),
            ("True", "string 'True'"),
            ("False", "string 'False'"),
            (1, "integer 1"),
            (0, "integer 0"),
            (1.0, "float 1.0"),
            (0.0, "float 0.0"),
        ],
    )
    def test_user_confirmed_rejects_non_bool(self, bad_value, label):
        client = TestClient(app)
        body = _valid_body(user_confirmed=bad_value)
        r = _post_raw(client, body)
        _assert_422_with_loc_prefix(
            r, expected_loc_prefix=("body", "user_confirmed")
        )

    @pytest.mark.parametrize("good_value", [True, False])
    def test_user_confirmed_accepts_real_bool(self, good_value):
        """Positive control: real JSON booleans parse OK."""
        from api.routers.simulations import SimulationCreateRequest
        body = _valid_body(user_confirmed=good_value)
        req = SimulationCreateRequest.model_validate(body)
        assert req.user_confirmed is good_value
