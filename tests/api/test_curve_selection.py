"""Regression tests for POST /api/v1/sections/curve (continuous XY curve).

Covers the existing API contract of ``generate_perpendicular_sections`` as
exposed by the sections router:
- interior submitted span keeps section origins strictly inside it
- an L-shaped polyline keeps piecewise origins and per-leg tangent azimuth
- reversed point order reverses origins and flips azimuths by 180 degrees
- a span shorter than ``spacing`` yields exactly one midpoint section
- asymmetric ``length_up``/``length_down`` and ``sector`` are preserved
- ``X-Session-ID`` isolates persisted sections per session (POST -> GET)

Golden values were computed independently from the documented algorithm
(spacing/2 offsets, outgoing segment at corners, mining azimuth North=0
clockwise, section azimuth = tangent azimuth + 90).
"""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

ENDPOINT = "/api/v1/sections/curve"
LIST_ENDPOINT = "/api/v1/sections"
TOL = 1e-6

SECTION_KEYS = {
    "id",
    "name",
    "origin",
    "azimuth",
    "length",
    "length_up",
    "length_down",
    "sector",
}


def _post_curve(client: TestClient, headers: dict, points, spacing, **overrides):
    payload = {
        "points": points,
        "spacing": spacing,
        "length": overrides.pop("length", 200.0),
        "length_up": overrides.pop("length_up", None),
        "length_down": overrides.pop("length_down", None),
        "sector": overrides.pop("sector", ""),
    }
    resp = client.post(ENDPOINT, json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, dict) and "sections" in body
    return body["sections"]


def _get_sections(client: TestClient, headers: dict):
    resp = client.get(LIST_ENDPOINT, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _origins(sections):
    return [tuple(s["origin"]) for s in sections]


def _azimuths(sections):
    return [s["azimuth"] for s in sections]


def _on_polyline(origin, pts, tol=TOL):
    """Perpendicular distance from an XY origin to the polyline segment chain."""
    px, py = origin
    best = math.inf
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
        cx, cy = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(px - cx, py - cy))
    return best


def _assert_section_shape(sections, expected_n):
    assert len(sections) == expected_n
    for s in sections:
        assert set(s.keys()) == SECTION_KEYS
        assert isinstance(s["origin"], list) and len(s["origin"]) == 2
        assert all(math.isfinite(v) for v in s["origin"])
        assert math.isfinite(s["azimuth"])


class TestCurveInteriorSpan:
    def test_origins_stay_inside_submitted_span(self, api_test_client):
        """Original 0..100 line, submitted interior 20..80, spacing 10:
        six sections at x=25..75, all strictly inside the submitted span
        and therefore never outside the original vertices."""
        headers = {"X-Session-ID": "curve-t11-interior"}
        sections = _post_curve(
            api_test_client, headers, [[20.0, 0.0], [80.0, 0.0]], 10.0
        )

        _assert_section_shape(sections, 6)
        expected_origins = [(25.0, 0.0), (35.0, 0.0), (45.0, 0.0),
                            (55.0, 0.0), (65.0, 0.0), (75.0, 0.0)]
        got = _origins(sections)
        for (ex, ey), (gx, gy) in zip(expected_origins, got):
            assert gx == pytest.approx(ex, abs=TOL)
            assert gy == pytest.approx(ey, abs=TOL)

        for x, _y in got:
            assert 20.0 < x < 80.0
        for x, _y in got:
            assert 0.0 < x < 100.0

        for (x0, _), (x1, _) in zip(got, got[1:]):
            assert (x1 - x0) == pytest.approx(10.0, abs=TOL)

        assert _azimuths(sections) == [pytest.approx(180.0, abs=TOL)] * 6


class TestCurveLCorner:
    def test_origins_on_piecewise_segments_with_local_azimuth(self, api_test_client):
        """L polyline (0,0)->(100,0)->(100,100), spacing 10: origins lie on
        the two legs (never on the start-end chord) and azimuth follows the
        local tangent of each leg, not the chord bisector."""
        headers = {"X-Session-ID": "curve-t11-corner"}
        points = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]]
        sections = _post_curve(api_test_client, headers, points, 10.0)

        _assert_section_shape(sections, 20)
        expected_origins = (
            [(float(x), 0.0) for x in range(5, 100, 10)]
            + [(100.0, float(y)) for y in range(5, 100, 10)]
        )
        got = _origins(sections)
        for (ex, ey), (gx, gy) in zip(expected_origins, got):
            assert gx == pytest.approx(ex, abs=TOL)
            assert gy == pytest.approx(ey, abs=TOL)

        for o in got:
            assert _on_polyline(o, points) == pytest.approx(0.0, abs=TOL)
        for x, y in got:
            assert abs(x - y) > 1e-6

        az = _azimuths(sections)
        assert az[:10] == [pytest.approx(180.0, abs=TOL)] * 10
        assert az[10:] == [pytest.approx(90.0, abs=TOL)] * 10
        assert all(abs(a - 135.0) > TOL for a in az)


class TestCurveReversed:
    def test_reversed_points_reverse_origins_and_flip_azimuth(self, api_test_client):
        """Same L traversed backwards: origins appear in exactly the reverse
        order and every paired azimuth differs by 180 degrees under the
        mining convention (North=0, East=90, clockwise)."""
        fwd_headers = {"X-Session-ID": "curve-t11-rev-fwd"}
        rev_headers = {"X-Session-ID": "curve-t11-rev-back"}
        fwd_pts = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]]
        rev_pts = [[100.0, 100.0], [100.0, 0.0], [0.0, 0.0]]

        fwd = _post_curve(api_test_client, fwd_headers, fwd_pts, 10.0)
        rev = _post_curve(api_test_client, rev_headers, rev_pts, 10.0)

        _assert_section_shape(fwd, 20)
        _assert_section_shape(rev, 20)

        fwd_origins = _origins(fwd)
        rev_origins = _origins(rev)
        for (rx, ry), (fx, fy) in zip(rev_origins, fwd_origins[::-1]):
            assert rx == pytest.approx(fx, abs=TOL)
            assert ry == pytest.approx(fy, abs=TOL)

        fwd_az = _azimuths(fwd)
        rev_az = _azimuths(rev)
        for fa, ra in zip(fwd_az[::-1], rev_az):
            assert (fa - ra) % 360.0 == pytest.approx(180.0, abs=TOL)

        assert rev_az[:10] == [pytest.approx(270.0, abs=TOL)] * 10
        assert rev_az[10:] == [pytest.approx(0.0, abs=TOL)] * 10


class TestCurveShortSpan:
    def test_short_span_yields_single_midpoint_section(self, api_test_client):
        """30 m span with spacing 50 collapses to exactly one section at the
        midpoint of the span, in both the POST response and the persisted
        GET readback."""
        headers = {"X-Session-ID": "curve-t11-short"}
        sections = _post_curve(
            api_test_client, headers, [[0.0, 0.0], [30.0, 0.0]], 50.0
        )

        _assert_section_shape(sections, 1)
        ox, oy = sections[0]["origin"]
        assert ox == pytest.approx(15.0, abs=TOL)
        assert oy == pytest.approx(0.0, abs=TOL)
        assert sections[0]["azimuth"] == pytest.approx(180.0, abs=TOL)

        stored = _get_sections(api_test_client, headers)
        assert len(stored) == 1
        sx, sy = stored[0]["origin"]
        assert sx == pytest.approx(15.0, abs=TOL)
        assert sy == pytest.approx(0.0, abs=TOL)


class TestCurveAsymmetricLengths:
    def test_asymmetric_lengths_and_sector_preserved(self, api_test_client):
        """length=200 with length_up=120 / length_down=80 propagates to every
        generated section, their sum equals the total length, and the sector
        name round-trips verbatim."""
        headers = {"X-Session-ID": "curve-t11-asym"}
        sector = "Sector QA T11"
        sections = _post_curve(
            api_test_client,
            headers,
            [[0.0, 0.0], [100.0, 0.0]],
            25.0,
            length=200.0,
            length_up=120.0,
            length_down=80.0,
            sector=sector,
        )

        _assert_section_shape(sections, 4)
        expected_origins = [(12.5, 0.0), (37.5, 0.0), (62.5, 0.0), (87.5, 0.0)]
        got = _origins(sections)
        for (ex, ey), (gx, gy) in zip(expected_origins, got):
            assert gx == pytest.approx(ex, abs=TOL)
            assert gy == pytest.approx(ey, abs=TOL)

        for s in sections:
            assert s["length"] == pytest.approx(200.0, abs=TOL)
            assert s["length_up"] == pytest.approx(120.0, abs=TOL)
            assert s["length_down"] == pytest.approx(80.0, abs=TOL)
            assert (s["length_up"] + s["length_down"]) == pytest.approx(
                s["length"], abs=TOL
            )
            assert s["sector"] == sector
            assert s["azimuth"] == pytest.approx(180.0, abs=TOL)


class TestCurveSessionIsolation:
    def test_sessions_keep_their_own_persisted_curves(self, api_test_client):
        """Two sessions POST different curves; each session's GET returns
        exactly its own persisted sections (full JSON equality with its POST
        response) and nothing from the other session."""
        headers_a = {"X-Session-ID": "curve-t11-session-a"}
        headers_b = {"X-Session-ID": "curve-t11-session-b"}

        post_a = _post_curve(
            api_test_client, headers_a, [[0.0, 0.0], [100.0, 0.0]], 20.0
        )
        post_b = _post_curve(
            api_test_client, headers_b, [[0.0, 0.0], [0.0, 100.0]], 20.0
        )

        _assert_section_shape(post_a, 5)
        _assert_section_shape(post_b, 5)

        get_a = _get_sections(api_test_client, headers_a)
        get_b = _get_sections(api_test_client, headers_b)
        assert get_a == post_a
        assert get_b == post_b

        assert _origins(get_a) == [
            (10.0, 0.0), (30.0, 0.0), (50.0, 0.0), (70.0, 0.0), (90.0, 0.0)
        ]
        assert _azimuths(get_a) == [pytest.approx(180.0, abs=TOL)] * 5
        for _x, y in _origins(get_a):
            assert y == pytest.approx(0.0, abs=TOL)

        assert _origins(get_b) == [
            (0.0, 10.0), (0.0, 30.0), (0.0, 50.0), (0.0, 70.0), (0.0, 90.0)
        ]
        assert _azimuths(get_b) == [pytest.approx(90.0, abs=TOL)] * 5
        for x, _y in _origins(get_b):
            assert x == pytest.approx(0.0, abs=TOL)
