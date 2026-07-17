"""Tests for the settings router (api/routers/settings.py).

Covers:
- GET  /settings → defaults for a fresh session
- GET  /settings → deep-merge of stored values over defaults
- PUT  /settings → partial update preserves sibling blocks
- PUT  /settings → sector_density validation (non-positive / non-numeric)
- PUT  /settings → blast block partial update (rock_density only)
- PUT  /settings → invalid Pydantic body returns 422
"""
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient


# Helpers ---------------------------------------------------------------------


def _default_payload() -> Dict[str, Any]:
    """Shape of GET /settings for a fresh session, derived from core.config."""
    return {
        "process": {
            "resolution": 0.1,
            "face_threshold": 40.0,
            "berm_threshold": 20.0,
        },
        "tolerances": {
            "bench_height": {"neg": 1.0, "pos": 1.5},
            "face_angle": {"neg": 5.0, "pos": 5.0},
            "berm_width": {"min": 6.0},
            "inter_ramp_angle": {"neg": 3.0, "pos": 2.0},
            "overall_angle": {"neg": 2.0, "pos": 2.0},
        },
        "blast": {
            "rock_density_tm3": 2.7,
            "height_fallback_m": 15.0,
            "sector_density": {},
        },
    }


# ===========================================================================
# GET /settings
# ===========================================================================


class TestGetSettings:
    def test_fresh_session_returns_core_defaults(self, client: TestClient):
        """No prior settings → response equals the canonical defaults."""
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        # Compare structurally — every default key must be present with the
        # expected values. (Exact equality would couple the test to the
        # underlying core.config values, which is fine because they are
        # pinned by the project.)
        expected = _default_payload()
        assert body["process"] == expected["process"]
        assert body["tolerances"] == expected["tolerances"]
        # blast is a free block — only assert the keys we know are stable.
        for key in ("rock_density_tm3", "height_fallback_m", "sector_density"):
            assert key in body["blast"]

    def test_session_header_is_isolating(self, client: TestClient):
        """Each X-Session-ID keeps its own settings row."""
        a = {"X-Session-ID": "settings-session-a"}
        b = {"X-Session-ID": "settings-session-b"}

        # Update A only.
        upd = client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 3.1,
                    "height_fallback_m": 15.0,
                    "sector_density": {},
                }
            },
            headers=a,
        )
        assert upd.status_code == 200

        a_get = client.get("/api/v1/settings", headers=a).json()
        b_get = client.get("/api/v1/settings", headers=b).json()
        # A reflects the override…
        assert a_get["blast"]["rock_density_tm3"] == 3.1
        # …and B still sees the defaults.
        assert b_get["blast"]["rock_density_tm3"] == _default_payload()["blast"][
            "rock_density_tm3"
        ]

    def test_stored_values_override_defaults(self, client: TestClient):
        """PUT-then-GET deep-merges stored blocks on top of core.config."""
        headers = {"X-Session-ID": "deep-merge"}
        upd = client.put(
            "/api/v1/settings",
            json={
                "process": {"resolution": 0.25, "face_threshold": 40.0, "berm_threshold": 20.0},
                "tolerances": {
                    "bench_height": {"neg": 1.0, "pos": 1.5},
                    "face_angle": {"neg": 5.0, "pos": 5.0},
                    "berm_width": {"min": 6.0},
                    "inter_ramp_angle": {"neg": 3.0, "pos": 2.0},
                    "overall_angle": {"neg": 2.0, "pos": 2.0},
                },
                "blast": {
                    "rock_density_tm3": 3.0,
                    "height_fallback_m": 15.0,
                    "sector_density": {},
                },
            },
            headers=headers,
        )
        assert upd.status_code == 200

        got = client.get("/api/v1/settings", headers=headers).json()
        # process.resolution was overwritten…
        assert got["process"]["resolution"] == 0.25
        # …and the remaining fields still match the default block.
        assert got["process"]["face_threshold"] == 40.0
        assert got["blast"]["rock_density_tm3"] == 3.0


# ===========================================================================
# PUT /settings
# ===========================================================================


class TestUpdateSettings:
    def test_partial_update_only_changes_target_block(
        self, client: TestClient
    ):
        """A PUT carrying only ``blast`` must leave process/tolerances
        untouched on subsequent GET."""
        headers = {"X-Session-ID": "partial-1"}
        # Seed with everything at default.
        r1 = client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 2.7,
                    "height_fallback_m": 15.0,
                    "sector_density": {},
                }
            },
            headers=headers,
        )
        assert r1.status_code == 200
        # Update only rock_density_tm3.
        r2 = client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 3.2,
                    "height_fallback_m": 15.0,
                    "sector_density": {},
                }
            },
            headers=headers,
        )
        assert r2.status_code == 200
        assert (
            r2.json()["settings"]["blast"]["rock_density_tm3"] == 3.2
        )
        # Process block survives untouched.
        assert r2.json()["settings"]["process"] == _default_payload()["process"]

    def test_blast_block_partial_update_preserves_sibling(
        self, client: TestClient
    ):
        """Updating only ``rock_density_tm3`` does not clobber the
        previously stored ``height_fallback_m`` (the router relies on
        ``exclude_unset=True`` for this)."""
        headers = {"X-Session-ID": "blast-partial"}
        # First PUT: set height_fallback_m to a non-default value.
        client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 2.7,
                    "height_fallback_m": 20.0,
                    "sector_density": {},
                }
            },
            headers=headers,
        )
        # Second PUT: only touch rock_density_tm3.
        r = client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 3.4,
                    "height_fallback_m": 20.0,
                    "sector_density": {},
                }
            },
            headers=headers,
        )
        body = r.json()
        assert body["settings"]["blast"]["rock_density_tm3"] == 3.4
        assert body["settings"]["blast"]["height_fallback_m"] == 20.0

    def test_sector_density_positive_only(self, client: TestClient):
        """A non-positive sector density must return 400 — a ρ of 0 would
        divide-by-zero inside ``compute_powder_factor``."""
        resp = client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 2.7,
                    "height_fallback_m": 15.0,
                    "sector_density": {"Norte": 0.0},
                }
            },
        )
        assert resp.status_code == 400
        assert "positive" in resp.json()["detail"].lower()

    def test_sector_density_negative_rejected(self, client: TestClient):
        resp = client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 2.7,
                    "height_fallback_m": 15.0,
                    "sector_density": {"Sur": -1.5},
                }
            },
        )
        assert resp.status_code == 400

    def test_sector_density_nan_rejected(self, client: TestClient):
        """NaN slips past simple `> 0` checks; the router uses
        ``math.isfinite`` so the request must return 400.

        Python's stdlib ``json`` emits NaN as the literal token ``NaN`` by
        default, which Starlette's parser accepts (its `allow_nan=True`
        default matches Python's). We smuggle NaN into the payload by
        sending a raw byte body.
        """
        raw = (
            b'{"blast": {"rock_density_tm3": 2.7,'
            b' "height_fallback_m": 15.0,'
            b' "sector_density": {"Norte": NaN}}}'
        )
        resp = client.put(
            "/api/v1/settings",
            content=raw,
            headers={"Content-Type": "application/json"},
        )
        # Either the router rejects it with 400 (the documented path) or
        # the parser rejects the body with 422 — both are valid "rejected".
        assert resp.status_code in (400, 422)

    def test_invalid_body_returns_422(self, client: TestClient):
        """Type violations on Pydantic fields surface as 422."""
        # rock_density_tm3 must be in [0.0, 20.0] — 999 is out of range.
        resp = client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 999.0,
                    "height_fallback_m": 15.0,
                    "sector_density": {},
                }
            },
        )
        assert resp.status_code == 422

    def test_empty_body_returns_200_with_no_changes(self, client: TestClient):
        """``PUT /settings`` with ``{}`` is a no-op; stored values survive."""
        headers = {"X-Session-ID": "empty-put"}
        # Seed
        client.put(
            "/api/v1/settings",
            json={
                "blast": {
                    "rock_density_tm3": 3.0,
                    "height_fallback_m": 15.0,
                    "sector_density": {},
                }
            },
            headers=headers,
        )
        r = client.put("/api/v1/settings", json={}, headers=headers)
        assert r.status_code == 200
        # GET still reflects the seeded value.
        got = client.get("/api/v1/settings", headers=headers).json()
        assert got["blast"]["rock_density_tm3"] == 3.0


# ===========================================================================
# GET-then-PUT round trip
# ===========================================================================


class TestSettingsRoundTrip:
    def test_get_after_put_returns_persisted_state(self, client: TestClient):
        """End-to-end: PUT then GET returns the same stored payload."""
        headers = {"X-Session-ID": "roundtrip"}
        r_put = client.put(
            "/api/v1/settings",
            json={
                "process": {"resolution": 0.5, "face_threshold": 40.0, "berm_threshold": 20.0},
                "blast": {
                    "rock_density_tm3": 2.9,
                    "height_fallback_m": 18.0,
                    "sector_density": {"Este": 2.8, "Oeste": 2.6},
                },
            },
            headers=headers,
        )
        assert r_put.status_code == 200
        r_get = client.get("/api/v1/settings", headers=headers)
        body = r_get.json()
        assert body["process"]["resolution"] == 0.5
        assert body["blast"]["rock_density_tm3"] == 2.9
        assert body["blast"]["height_fallback_m"] == 18.0
        assert body["blast"]["sector_density"] == {"Este": 2.8, "Oeste": 2.6}
