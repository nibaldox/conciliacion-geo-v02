"""G04 — Reconciliator builder alignment between Streamlit (legacy) and API (v2).

The audit ``docs/UI_PARITY_AUDIT.md`` (Causa 2) flags that Streamlit draws the
reconciled polyline from the legacy ``build_reconciled_profile`` tuple
(crest/toe sorted by distance), while the API exposes the rich
``build_reconciled_profile_v2`` ``ReconciledProfile`` (explicit berm_top corners
+ face sampling). These tests verify that the API now exposes BOTH shapes
(``reconciled_*`` rich + ``reconciled_*_legacy`` flat arrays) and that, for the
crest/toe geometry the two shapes share, they agree.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.database as db
from core.profile_compliance import (
    build_reconciled_profile,
    build_reconciled_profile_v2,
)
from core.profile_extract import BenchParams


# The legacy builder deliberately emits a DeprecationWarning on every call;
# it is asserted explicitly in test_legacy_builder_emits_deprecation_warning
# and silenced everywhere else to keep the test summary clean.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _bench(
    num: int,
    crest_d: float,
    crest_e: float,
    toe_d: float,
    toe_e: float,
    *,
    is_ramp: bool = False,
) -> BenchParams:
    """Build a minimal BenchParams with crest above toe and crest before toe
    in distance — the well-formed bench convention used by extract_parameters."""
    height = abs(crest_e - toe_e)
    dx = toe_d - crest_d
    angle = (
        abs(float(np.degrees(np.arctan2(height, abs(dx)))))
        if abs(dx) > 1e-9
        else 90.0
    )
    return BenchParams(
        bench_number=num,
        crest_elevation=float(crest_e),
        crest_distance=float(crest_d),
        toe_elevation=float(toe_e),
        toe_distance=float(toe_d),
        bench_height=float(height),
        face_angle=float(angle),
        berm_width=0.0,
        is_ramp=bool(is_ramp),
    )


def _two_well_formed_benches() -> list[BenchParams]:
    return [
        _bench(1, 10.0, 100.0, 15.0, 85.0),
        _bench(2, 25.0, 80.0, 30.0, 65.0),
    ]


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isolated SQLite DB per test (mirrors tests/test_api.py)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def _upload_mesh(client, headers, stl_path, mesh_type="design"):
    with open(stl_path, "rb") as f:
        resp = client.post(
            "/api/v1/meshes/upload",
            files={"file": ("test.stl", f, "application/octet-stream")},
            data={"type": mesh_type},
            headers=headers,
        )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()


def _create_test_stl(filepath: str) -> str:
    with open(filepath, "w") as f:
        f.write("solid test\n")
        vertices = [(0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)]
        faces = [
            (vertices[0], vertices[1], vertices[2]),
            (vertices[0], vertices[1], vertices[3]),
            (vertices[0], vertices[2], vertices[3]),
            (vertices[1], vertices[2], vertices[3]),
        ]
        for v1, v2, v3 in faces:
            f.write("  facet normal 0 0 1\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
            f.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
            f.write(f"      vertex {v3[0]} {v3[1]} {v3[2]}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write("endsolid test\n")
    return filepath


# ---------------------------------------------------------------------------
# 1. Geometry equivalence: legacy crest/toe == v2 crest/toe typed points
# ---------------------------------------------------------------------------


class TestGeometryEquivalence:
    def test_legacy_and_v2_share_crest_geometry(self):
        benches = _two_well_formed_benches()

        legacy_d, legacy_e = build_reconciled_profile(benches)
        rich = build_reconciled_profile_v2(benches, source="design")

        crest_pts = [p for p in rich.points if p.segment_type == "crest"]
        toe_pts = [p for p in rich.points if p.segment_type == "toe"]

        # Legacy interleaves (crest, toe) per bench and sorts by distance; for
        # well-formed benches (crest_d < toe_d, non-overlapping) the even
        # indices are the crests and the odd indices are the toes.
        assert len(crest_pts) == len(legacy_d) // 2
        assert list(legacy_d[::2]) == pytest.approx([p.distance for p in crest_pts])
        assert list(legacy_e[::2]) == pytest.approx([p.elevation for p in crest_pts])
        assert list(legacy_d[1::2]) == pytest.approx([p.distance for p in toe_pts])
        assert list(legacy_e[1::2]) == pytest.approx([p.elevation for p in toe_pts])

    def test_v2_emits_extra_berm_top_legacy_does_not(self):
        # Ascending pair (next crest >= current toe) so a berm_top corner IS
        # expected. The shared _two_well_formed_benches() fixture is a
        # descending wall, for which _build_reconciled_points now correctly
        # skips berm_top (guard against descent) — so we build a local
        # ascending pair here to keep testing the "v2 emits berm_top" contract.
        benches = [
            _bench(1, 10.0, 100.0, 15.0, 85.0),
            _bench(2, 25.0, 88.0, 30.0, 70.0),
        ]
        legacy_d, _ = build_reconciled_profile(benches)
        rich = build_reconciled_profile_v2(benches, source="topo")

        berm_top = [p for p in rich.points if p.segment_type == "berm_top"]
        # The rich profile carries one berm_top corner per non-last bench that
        # the legacy polyline collapses into a straight crest-toe segment.
        assert len(berm_top) == len(benches) - 1
        assert len(rich.points) > len(legacy_d)


# ---------------------------------------------------------------------------
# 2. API exposes both shapes
# ---------------------------------------------------------------------------


class TestApiExposesBothShapes:
    def test_profile_endpoint_returns_rich_and_legacy(self, client, monkeypatch, tmp_path):
        headers = {"x-session-id": db.create_session()}
        stl_path = _create_test_stl(str(tmp_path / "mesh.stl"))
        _upload_mesh(client, headers, stl_path, "design")
        _upload_mesh(client, headers, stl_path, "topo")
        sections = [
            {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"}
        ]
        resp = client.post("/api/v1/sections/manual", json=sections, headers=headers)
        assert resp.status_code == 200

        session_id = headers["x-session-id"]
        bench_dict = {
            "bench_number": 1,
            "crest_elevation": 3900.0,
            "crest_distance": 10.0,
            "toe_elevation": 3885.0,
            "toe_distance": 15.0,
            "bench_height": 15.0,
            "face_angle": 70.0,
            "berm_width": 9.0,
            "is_ramp": False,
        }
        extraction = {
            "section_name": "S-01",
            "sector": "A",
            "benches": [bench_dict, {**bench_dict, "bench_number": 2,
                                     "crest_distance": 25.0, "toe_distance": 30.0,
                                     "crest_elevation": 3880.0, "toe_elevation": 3865.0}],
            "inter_ramp_angle": 45.0,
            "overall_angle": 45.0,
        }
        db.save_extraction(session_id, "S-01", "design", extraction)
        db.save_extraction(session_id, "S-01", "topo", extraction)

        class MockProfile:
            def __init__(self):
                self.distances = np.array([0.0, 10.0, 15.0, 25.0, 30.0])
                self.elevations = np.array([3900.0, 3900.0, 3885.0, 3880.0, 3865.0])

        import core
        monkeypatch.setattr(
            core,
            "cut_both_surfaces",
            lambda m_d, m_t, sec: (MockProfile(), MockProfile()),
        )

        resp = client.get("/api/v1/process/profiles/0", headers=headers)
        assert resp.status_code == 200, f"Profiles failed: {resp.text}"
        data = resp.json()

        # Rich shape (existing contract)
        assert "reconciled_design" in data and data["reconciled_design"] is not None
        assert "reconciled_topo" in data and data["reconciled_topo"] is not None
        assert "segments" in data["reconciled_design"]

        # New legacy shape (flat arrays, no segments)
        assert "reconciled_design_legacy" in data
        assert "reconciled_topo_legacy" in data
        legacy = data["reconciled_design_legacy"]
        assert set(legacy.keys()) == {"distances", "elevations"}
        # 2 benches * (crest + toe) = 4, + potential floor extension points
        assert len(legacy["distances"]) >= 4
        assert len(legacy["elevations"]) == len(legacy["distances"])
        # Sorted ascending by distance
        dists = legacy["distances"]
        assert all(dists[i] <= dists[i + 1] for i in range(len(dists) - 1))


# ---------------------------------------------------------------------------
# 3. Legacy sorts by distance (v2 preserves bench order)
# ---------------------------------------------------------------------------


class TestLegacySorting:
    def test_legacy_sorts_by_distance_regardless_of_input_order(self):
        benches = list(reversed(_two_well_formed_benches()))
        legacy_d, legacy_e = build_reconciled_profile(benches)
        assert all(legacy_d[i] <= legacy_d[i + 1] for i in range(len(legacy_d) - 1))

    def test_v2_preserves_bench_order(self):
        benches = list(reversed(_two_well_formed_benches()))
        rich = build_reconciled_profile_v2(benches, source="topo")
        crest_pts = [p for p in rich.points if p.segment_type == "crest"]
        # v2 does NOT sort: crests come out in bench-list order (reversed).
        assert [p.bench_number for p in crest_pts] == [2, 1]


# ---------------------------------------------------------------------------
# 4. Empty benches
# ---------------------------------------------------------------------------


class TestEmptyBenches:
    def test_legacy_empty_returns_empty_arrays(self):
        legacy_d, legacy_e = build_reconciled_profile([])
        assert len(legacy_d) == 0
        assert len(legacy_e) == 0

    def test_v2_empty_returns_empty_profile(self):
        rich = build_reconciled_profile_v2([])
        assert len(rich.distances) == 0
        assert len(rich.elevations) == 0
        assert rich.points == []

    def test_api_omits_legacy_when_no_benches(self, client, monkeypatch, tmp_path):
        headers = {"x-session-id": db.create_session()}
        stl_path = _create_test_stl(str(tmp_path / "mesh.stl"))
        _upload_mesh(client, headers, stl_path, "design")
        _upload_mesh(client, headers, stl_path, "topo")
        sections = [
            {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 20.0, "sector": "A"}
        ]
        client.post("/api/v1/sections/manual", json=sections, headers=headers)

        session_id = headers["x-session-id"]
        empty_extraction = {
            "section_name": "S-01", "sector": "A", "benches": [],
            "inter_ramp_angle": 0.0, "overall_angle": 0.0,
        }
        db.save_extraction(session_id, "S-01", "design", empty_extraction)
        db.save_extraction(session_id, "S-01", "topo", empty_extraction)

        class MockProfile:
            def __init__(self):
                self.distances = np.array([0.0, 1.0])
                self.elevations = np.array([100.0, 100.0])

        import core
        monkeypatch.setattr(
            core,
            "cut_both_surfaces",
            lambda m_d, m_t, sec: (MockProfile(), MockProfile()),
        )

        resp = client.get("/api/v1/process/profiles/0", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # No benches → neither rich nor legacy reconciled keys are emitted,
        # matching the existing guard structure in get_profile.
        assert "reconciled_design" not in data
        assert "reconciled_design_legacy" not in data
        assert "reconciled_topo" not in data
        assert "reconciled_topo_legacy" not in data


# ---------------------------------------------------------------------------
# 5. Contract: legacy builder emits DeprecationWarning
# ---------------------------------------------------------------------------


class TestDeprecationContract:
    def test_legacy_builder_emits_deprecation_warning(self):
        benches = _two_well_formed_benches()
        with pytest.warns(DeprecationWarning):
            build_reconciled_profile(benches)
