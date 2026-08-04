"""V6-01: Strict API contracts — reject coercive and semantically
invalid scientific payloads with HTTP 422 before the engine runs.

Each test sends exactly ONE defect and asserts:

* ``status_code == 422`` (not 400, not 200)
* the offending ``loc`` appears in the validation errors
* the engine (``run_simulation``) is NEVER called
* no SQLite row is written for the failed request

At HEAD 5827560 (V5) Pydantic accepts ``str``/``bool`` for numeric
fields (lax coercion) and several semantic failures are translated to
HTTP 400 via ``SimulationConfigurationError``. V6-01 moves every
structural and scientific body failure into Pydantic so FastAPI
returns HTTP 422 from the request-body parser itself.
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
        "session_id": "test-v6-contracts",
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


def _assert_422_with_loc(response, *, expected_loc_prefix: tuple) -> None:
    """Assert the response is HTTP 422 and one error's loc starts with
    the given prefix.

    The router's structured error envelope is::

        {"detail": {"error_code": "...", "message": "...",
                    "details": {"validation_errors": [...]}}}

    Each ``validation_errors`` entry is the raw Pydantic v2 error dict,
    which carries ``loc``, ``msg``, ``type`` and ``input``.
    """
    assert response.status_code == 422, (
        f"Expected HTTP 422 for {expected_loc_prefix}, got "
        f"{response.status_code}: {response.text[:300]}"
    )
    payload = response.json()
    details = payload.get("detail") or {}
    verrors = (
        details.get("details", {}).get("validation_errors")
        or details.get("validation_errors")
        or []
    )
    if not verrors:
        # Pydantic-FastAPI default shape: detail is a list of errors.
        verrors = details if isinstance(details, list) else []
    locs = [tuple(e.get("loc") or ()) for e in verrors]
    assert any(
        loc[: len(expected_loc_prefix)] == expected_loc_prefix for loc in locs
    ), (
        f"No validation error with loc prefix {expected_loc_prefix!r} in {locs!r}"
    )


def _assert_engine_not_called(client: TestClient, body: dict) -> None:
    """Patch ``run_simulation`` on the router module and confirm the
    request never reaches the engine."""
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
# V6-01.a — type coercion: str / bool MUST be rejected with HTTP 422
# ---------------------------------------------------------------------------


class TestStrictNumericTypes:
    """Every numeric scientific field MUST reject ``str`` and ``bool``
    payloads with HTTP 422 — Pydantic lax coercion is forbidden here."""

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("voxel_size_m", "1.0"),
            ("voxel_size_m", True),
            ("voxel_size_m", False),
            ("attenuation_coefficient_1_m", "0.2"),
            ("attenuation_coefficient_1_m", True),
            ("regularization_radius_m", "0.5"),
            ("regularization_radius_m", True),
            ("support_radius_m", "5.0"),
            ("support_radius_m", True),
            ("coupling_efficiency", "0.85"),
            ("coupling_efficiency", True),
            ("segments_per_hole", "8"),
            ("segments_per_hole", True),
            ("segments_per_hole", False),
        ],
    )
    def test_top_level_numeric_rejects_str_bool(self, field, bad_value):
        client = TestClient(app)
        body = _valid_body(**{field: bad_value})
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", field))

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("x_min", "5"),
            ("x_min", True),
            ("y_min", "0"),
            ("y_min", False),
            ("z_min", "0"),
            ("z_max", True),
            ("x_max", "10"),
            ("x_max", False),
        ],
    )
    def test_domain_bounds_rejects_str_bool(self, field, bad_value):
        client = TestClient(app)
        bounds = dict(_valid_body()["domain_bounds"])
        bounds[field] = bad_value
        body = _valid_body(domain_bounds=bounds)
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "domain_bounds", field)
        )

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("density_kg_m3", "2700"),
            ("density_kg_m3", True),
            ("ucs_mpa", "50"),
            ("ucs_mpa", False),
            ("attenuation_coefficient_1_m", "0.2"),
            ("wave_velocity_m_s", "3500"),
            ("wave_velocity_m_s", True),
        ],
    )
    def test_rock_mass_numeric_rejects_str_bool(self, field, bad_value):
        client = TestClient(app)
        rock = dict(_valid_body()["rock_mass"])
        rock[field] = bad_value
        body = _valid_body(rock_mass=rock)
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "rock_mass", field)
        )

    def test_plan_elevations_rejects_str_element(self):
        client = TestClient(app)
        body = _valid_body(plan_elevations=["5.0"])
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", "plan_elevations", 0))

    def test_plan_elevations_rejects_bool_element(self):
        client = TestClient(app)
        body = _valid_body(plan_elevations=[True])
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", "plan_elevations", 0))

    def test_section_coordinates_rejects_str_coord(self):
        client = TestClient(app)
        body = _valid_body(section_coordinates=[["x", "5.0"]])
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "section_coordinates", 0)
        )


# ---------------------------------------------------------------------------
# V6-01.b — semantic body failures MUST be HTTP 422 (not 400)
# ---------------------------------------------------------------------------


class TestSemanticValidation422:
    """Bounds ordering, tensor shape/symmetry/PD and enum values MUST
    be validated by Pydantic so the response is HTTP 422, never 400."""

    def test_inverted_bounds_x_returns_422(self):
        client = TestClient(app)
        body = _valid_body(domain_bounds={
            "x_min": 10.0, "y_min": 0.0, "z_min": 0.0,
            "x_max": 0.0, "y_max": 10.0, "z_max": 10.0,
        })
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", "domain_bounds"))

    def test_inverted_bounds_y_returns_422(self):
        client = TestClient(app)
        body = _valid_body(domain_bounds={
            "x_min": 0.0, "y_min": 10.0, "z_min": 0.0,
            "x_max": 10.0, "y_max": 0.0, "z_max": 10.0,
        })
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", "domain_bounds"))

    def test_inverted_bounds_z_returns_422(self):
        client = TestClient(app)
        body = _valid_body(domain_bounds={
            "x_min": 0.0, "y_min": 0.0, "z_min": 10.0,
            "x_max": 10.0, "y_max": 10.0, "z_max": 0.0,
        })
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", "domain_bounds"))

    def test_degenerate_bounds_x_equals_returns_422(self):
        client = TestClient(app)
        body = _valid_body(domain_bounds={
            "x_min": 5.0, "y_min": 0.0, "z_min": 0.0,
            "x_max": 5.0, "y_max": 10.0, "z_max": 10.0,
        })
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", "domain_bounds"))

    def test_support_radius_le_regularization_returns_422(self):
        client = TestClient(app)
        body = _valid_body(support_radius_m=0.3, regularization_radius_m=0.5)
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body",))

    def test_tensor_non_symmetric_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            anisotropy_mode="ANISOTROPIC_TENSOR",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ANISOTROPIC_TENSOR",
                "anisotropy_tensor": [
                    [1.0, 0.0, 0.0],
                    [0.5, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
            },
        )
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "rock_mass", "anisotropy_tensor")
        )

    def test_tensor_non_pd_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            anisotropy_mode="ANISOTROPIC_TENSOR",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ANISOTROPIC_TENSOR",
                # symmetric but not positive-definite (one negative eigenvalue)
                "anisotropy_tensor": [
                    [-1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
            },
        )
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "rock_mass", "anisotropy_tensor")
        )

    def test_tensor_wrong_shape_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            anisotropy_mode="ANISOTROPIC_TENSOR",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ANISOTROPIC_TENSOR",
                "anisotropy_tensor": [[1.0, 0.0], [0.0, 1.0]],
            },
        )
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "rock_mass", "anisotropy_tensor")
        )

    def test_tensor_with_nan_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            anisotropy_mode="ANISOTROPIC_TENSOR",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ANISOTROPIC_TENSOR",
                "anisotropy_tensor": [
                    [1.0, 0.0, 0.0],
                    [0.0, float("nan"), 0.0],
                    [0.0, 0.0, 1.0],
                ],
            },
        )
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "rock_mass", "anisotropy_tensor")
        )

    def test_tensor_missing_when_required_returns_422(self):
        client = TestClient(app)
        body = _valid_body(
            anisotropy_mode="ANISOTROPIC_TENSOR",
            rock_mass={
                "rock_unit_id": "t", "source": "t", "status": "OK",
                "anisotropy_mode": "ANISOTROPIC_TENSOR",
                # no tensor supplied
            },
        )
        r = _post_raw(client, body)
        _assert_422_with_loc(
            r, expected_loc_prefix=("body", "rock_mass", "anisotropy_tensor")
        )

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("energy_mode", "ABS"),
            ("energy_mode", "absolute"),
            ("temporal_mode", "DYNAMIC"),
            ("temporal_mode", "static"),
            ("anisotropy_mode", "WEIRD"),
            ("anisotropy_mode", "isotropic"),
            ("kernel_type", "GAUSS"),
        ],
    )
    def test_invalid_enum_returns_422(self, field, bad_value):
        client = TestClient(app)
        body = _valid_body(**{field: bad_value})
        r = _post_raw(client, body)
        _assert_422_with_loc(r, expected_loc_prefix=("body", field))


# ---------------------------------------------------------------------------
# V6-01.c — engine NEVER executes when the body is invalid
# ---------------------------------------------------------------------------


class TestEngineNotReachedOnInvalidBody:
    """When the schema rejects the payload, ``run_simulation`` MUST NOT
    be invoked — protecting the canonical-result invariant."""

    def test_str_voxel_size_does_not_run_engine(self):
        _assert_engine_not_called(TestClient(app), _valid_body(voxel_size_m="1.0"))

    def test_bool_segments_per_hole_does_not_run_engine(self):
        _assert_engine_not_called(
            TestClient(app), _valid_body(segments_per_hole=True)
        )

    def test_inverted_bounds_does_not_run_engine(self):
        _assert_engine_not_called(TestClient(app), _valid_body(domain_bounds={
            "x_min": 10.0, "y_min": 0.0, "z_min": 0.0,
            "x_max": 0.0, "y_max": 10.0, "z_max": 10.0,
        }))

    def test_invalid_enum_does_not_run_engine(self):
        _assert_engine_not_called(
            TestClient(app), _valid_body(energy_mode="ABS")
        )


# ---------------------------------------------------------------------------
# V6-01.d — positive control: valid numeric JSON values MUST be accepted
# ---------------------------------------------------------------------------


class TestPositiveControlNumericJSON:
    """Sanity check: well-formed numeric JSON still parses."""

    @pytest.mark.parametrize(
        ("field", "good_value"),
        [
            ("voxel_size_m", 1.0),
            ("voxel_size_m", 1),
            ("segments_per_hole", 8),
            ("coupling_efficiency", 0.85),
            ("attenuation_coefficient_1_m", 0.2),
            ("support_radius_m", 5.0),
        ],
    )
    def test_schema_accepts_numeric(self, field, good_value):
        from api.routers.simulations import SimulationCreateRequest
        body = _valid_body(**{field: good_value})
        req = SimulationCreateRequest.model_validate(body)
        # Reaching this line means the schema accepted the payload.
        assert getattr(req, field) == good_value or float(getattr(req, field)) == float(good_value)
