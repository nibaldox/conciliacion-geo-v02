"""Tests for the crest_toe_deviation tolerance in the settings API."""
from __future__ import annotations

from fastapi.testclient import TestClient

DEFAULT_PAIR = {"neg": 1.0, "pos": 1.0}


class TestCrestToeDeviationDefaults:
    def test_fresh_session_returns_default_pair(self, client: TestClient):
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        tolerances = resp.json()["tolerances"]
        assert tolerances["crest_toe_deviation"] == DEFAULT_PAIR

    def test_legacy_settings_receive_default_pair(self, client: TestClient):
        headers = {"X-Session-ID": "legacy-crest-toe"}
        upd = client.put(
            "/api/v1/settings",
            json={"tolerances": {"bench_height": {"neg": 1.0, "pos": 1.5}}},
            headers=headers,
        )
        assert upd.status_code == 200
        got = client.get("/api/v1/settings", headers=headers).json()
        assert got["tolerances"]["crest_toe_deviation"] == DEFAULT_PAIR

    def test_session_isolation(self, client: TestClient):
        a = {"X-Session-ID": "crest-isolation-a"}
        b = {"X-Session-ID": "crest-isolation-b"}
        upd = client.put(
            "/api/v1/settings",
            json={"tolerances": {"crest_toe_deviation": {"neg": 2.5, "pos": 0.0}}},
            headers=a,
        )
        assert upd.status_code == 200
        got_a = client.get("/api/v1/settings", headers=a).json()
        assert got_a["tolerances"]["crest_toe_deviation"] == {"neg": 2.5, "pos": 0.0}
        got_b = client.get("/api/v1/settings", headers=b).json()
        assert got_b["tolerances"]["crest_toe_deviation"] == DEFAULT_PAIR


class TestCrestToeDeviationUpdate:
    def test_put_persists_pair_round_trip(self, client: TestClient):
        headers = {"X-Session-ID": "crest-roundtrip"}
        upd = client.put(
            "/api/v1/settings",
            json={"tolerances": {"crest_toe_deviation": {"neg": 0.8, "pos": 1.2}}},
            headers=headers,
        )
        assert upd.status_code == 200
        got = client.get("/api/v1/settings", headers=headers).json()
        assert got["tolerances"]["crest_toe_deviation"] == {"neg": 0.8, "pos": 1.2}

    def test_put_accepts_zero_and_asymmetry(self, client: TestClient):
        resp = client.put(
            "/api/v1/settings",
            json={"tolerances": {"crest_toe_deviation": {"neg": 0.0, "pos": 2.5}}},
        )
        assert resp.status_code == 200
        assert resp.json()["settings"]["tolerances"]["crest_toe_deviation"] == {
            "neg": 0.0,
            "pos": 2.5,
        }

    def test_put_preserves_sibling_tolerances(self, client: TestClient):
        headers = {"X-Session-ID": "crest-siblings"}
        seed = client.put(
            "/api/v1/settings",
            json={"tolerances": {"bench_height": {"neg": 2.0, "pos": 2.0}}},
            headers=headers,
        )
        assert seed.status_code == 200
        upd = client.put(
            "/api/v1/settings",
            json={"tolerances": {"crest_toe_deviation": {"neg": 0.5, "pos": 0.7}}},
            headers=headers,
        )
        assert upd.status_code == 200
        got = client.get("/api/v1/settings", headers=headers).json()
        assert got["tolerances"]["crest_toe_deviation"] == {"neg": 0.5, "pos": 0.7}
        assert got["tolerances"]["bench_height"] == {"neg": 2.0, "pos": 2.0}

    def test_put_negative_value_rejected(self, client: TestClient):
        resp = client.put(
            "/api/v1/settings",
            json={"tolerances": {"crest_toe_deviation": {"neg": -1.0, "pos": 1.0}}},
        )
        assert resp.status_code == 400

    def test_put_missing_key_rejected(self, client: TestClient):
        resp = client.put(
            "/api/v1/settings",
            json={"tolerances": {"crest_toe_deviation": {"neg": 1.0}}},
        )
        assert resp.status_code == 400

    def test_put_nan_rejected(self, client: TestClient):
        raw = b'{"tolerances": {"crest_toe_deviation": {"neg": NaN, "pos": 1.0}}}'
        resp = client.put(
            "/api/v1/settings",
            content=raw,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)

    def test_put_infinity_rejected(self, client: TestClient):
        raw = b'{"tolerances": {"crest_toe_deviation": {"neg": 1.0, "pos": Infinity}}}'
        resp = client.put(
            "/api/v1/settings",
            content=raw,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)
