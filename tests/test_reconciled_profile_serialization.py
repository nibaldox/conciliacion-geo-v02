"""Tests for the ReconciledProfile serialization surface.

Covers the additive methods added to ``core.profile_extract.ReconciledProfile``
(``summary``, ``to_dataframe``, ``to_dict``, ``from_dict``), the hardened
deprecation warning on the legacy ``build_reconciled_profile`` builder, and
the canonical ``build_reconciled_profile_v2`` re-export from the ``core``
package.

Each test class maps to one bullet of ``design.md`` section 6.
"""

import io
import json
import math
import warnings

import numpy as np
import pandas as pd
import pytest

import core
import core.param_extractor as param_extractor_mod
from core import build_reconciled_profile_v2
from core.param_extractor import BenchParams
from core.profile_compliance import build_reconciled_profile
from core.profile_extract import ReconciledPoint, ReconciledProfile


def _bench(
    num: int,
    crest_d: float,
    crest_e: float,
    toe_d: float,
    toe_e: float,
    *,
    is_ramp: bool = False,
    overhang_m: float = 0.0,
    wedge_risk: bool = False,
    toppling_risk: bool = False,
    n_detection_methods_agreeing: int = 1,
    face_angle: float = 70.0,
    berm_width: float = 9.0,
) -> BenchParams:
    """Build a minimal BenchParams with sensible defaults for serialization tests."""
    height = abs(crest_e - toe_e)
    dx = toe_d - crest_d
    if abs(dx) > 1e-9:
        angle = abs(float(np.degrees(np.arctan2(height, abs(dx)))))
    else:
        angle = 90.0
    return BenchParams(
        bench_number=num,
        crest_elevation=float(crest_e),
        crest_distance=float(crest_d),
        toe_elevation=float(toe_e),
        toe_distance=float(toe_d),
        bench_height=float(height),
        face_angle=float(angle if face_angle == 70.0 else face_angle),
        berm_width=float(berm_width),
        is_ramp=bool(is_ramp),
        overhang_m=float(overhang_m),
        wedge_risk=bool(wedge_risk),
        toppling_risk=bool(toppling_risk),
        n_detection_methods_agreeing=int(n_detection_methods_agreeing),
    )


def _populated_profile() -> ReconciledProfile:
    """3-bench profile: ascending pair + a ramp."""
    benches = [
        _bench(1, 10.0, 100.0, 15.0, 85.0, overhang_m=0.0,
               n_detection_methods_agreeing=3, berm_width=9.0),
        _bench(2, 25.0, 88.0, 30.0, 70.0, overhang_m=0.4,
               wedge_risk=True, n_detection_methods_agreeing=2,
               berm_width=11.0, face_angle=75.0),
        _bench(3, 45.0, 65.0, 50.0, 50.0, is_ramp=True, overhang_m=0.0,
               toppling_risk=True, n_detection_methods_agreeing=1,
               berm_width=15.0, face_angle=80.0),
    ]
    return build_reconciled_profile_v2(benches, source="topo")


# ---------------------------------------------------------------------------
# 1. Summary
# ---------------------------------------------------------------------------


class TestSummary:
    """Tests for ``ReconciledProfile.summary``."""

    def test_empty_profile_returns_zero_counts(self):
        prof = ReconciledProfile(
            distances=np.array([], dtype=float),
            elevations=np.array([], dtype=float),
            points=[],
        )
        s = prof.summary()
        assert s["n_benches"] == 0
        assert s["n_ramps"] == 0
        assert s["n_overhangs"] == 0
        assert s["n_wedge_risks"] == 0
        assert s["n_toppling_risks"] == 0
        assert s["n_consensus_benches"] == 0
        assert s["height_range_m"] == (0, 0)
        assert s["total_berm_width_m"] == 0.0
        assert s["max_overhang_m"] == 0.0
        assert s["source"] == "topo"

    def test_no_benches_arg_avg_face_is_none(self):
        prof = _populated_profile()
        s = prof.summary()
        assert s["avg_face_angle_deg"] is None
        assert s["n_consensus_benches"] == s["n_benches"]
        assert s["n_overhangs"] == 0
        assert s["total_berm_width_m"] == 0.0
        assert s["max_overhang_m"] == 0.0

    def test_enriched_with_benches(self):
        prof = _populated_profile()
        benches = [
            _bench(1, 10.0, 100.0, 15.0, 85.0, overhang_m=0.0,
                   n_detection_methods_agreeing=3, berm_width=9.0),
            _bench(2, 25.0, 88.0, 30.0, 70.0, overhang_m=0.4,
                   wedge_risk=True, n_detection_methods_agreeing=2,
                   berm_width=11.0, face_angle=75.0),
            _bench(3, 45.0, 65.0, 50.0, 50.0, is_ramp=True, overhang_m=0.0,
                   toppling_risk=True, n_detection_methods_agreeing=1,
                   berm_width=15.0, face_angle=80.0),
        ]
        s = prof.summary(benches=benches)
        assert s["n_benches"] == 3
        assert s["n_ramps"] == 1
        assert s["n_overhangs"] == 1
        assert s["n_wedge_risks"] == 1
        assert s["n_toppling_risks"] == 1
        assert s["n_consensus_benches"] == 2
        assert s["total_berm_width_m"] == pytest.approx(35.0, abs=1e-9)
        assert s["max_overhang_m"] == pytest.approx(0.4, abs=1e-9)
        assert isinstance(s["avg_face_angle_deg"], float)
        assert not math.isnan(s["avg_face_angle_deg"])
        expected_angle = float(np.mean([b.face_angle for b in benches]))
        assert s["avg_face_angle_deg"] == pytest.approx(expected_angle, abs=1e-6)

    def test_summary_is_json_serializable_no_benches(self):
        prof = _populated_profile()
        s = prof.summary()
        encoded = json.dumps(s, allow_nan=False)
        decoded = json.loads(encoded)
        assert decoded["n_benches"] == s["n_benches"]
        assert decoded["n_ramps"] == s["n_ramps"]
        assert decoded["height_range_m"] == list(s["height_range_m"])
        assert decoded["source"] == s["source"]
        assert decoded["avg_face_angle_deg"] is None

    def test_summary_is_json_serializable_with_benches(self):
        prof = _populated_profile()
        benches = [
            _bench(1, 10.0, 100.0, 15.0, 85.0, n_detection_methods_agreeing=3),
            _bench(2, 25.0, 88.0, 30.0, 70.0, wedge_risk=True),
            _bench(3, 45.0, 65.0, 50.0, 50.0, is_ramp=True,
                   toppling_risk=True),
        ]
        s = prof.summary(benches=benches)
        encoded = json.dumps(s)
        assert isinstance(encoded, str)

    def test_summary_has_no_numpy_scalar_leak(self):
        prof = _populated_profile()
        benches = [
            _bench(1, 10.0, 100.0, 15.0, 85.0),
            _bench(2, 25.0, 88.0, 30.0, 70.0),
        ]
        s = prof.summary(benches=benches)
        for k, v in s.items():
            assert not isinstance(v, np.integer), f"{k!r} leaked numpy int"
            assert not isinstance(v, np.floating), f"{k!r} leaked numpy float"
            assert not isinstance(v, np.ndarray), f"{k!r} leaked numpy array"
            if k == "height_range_m":
                for sub in v:
                    assert not isinstance(sub, np.floating), (
                        f"height_range_m item leaked numpy float"
                    )


# ---------------------------------------------------------------------------
# 2. to_dataframe
# ---------------------------------------------------------------------------


class TestToDataframe:
    """Tests for ``ReconciledProfile.to_dataframe``."""

    def test_empty_profile_dataframe_shape(self):
        prof = ReconciledProfile(
            distances=np.array([], dtype=float),
            elevations=np.array([], dtype=float),
            points=[],
        )
        df = prof.to_dataframe()
        assert list(df.columns) == [
            "bench_number", "segment_type", "distance_m",
            "elevation_m", "is_ramp", "source",
        ]
        assert len(df) == 0

    def test_populated_columns_and_dtypes(self):
        prof = _populated_profile()
        df = prof.to_dataframe()
        assert list(df.columns) == [
            "bench_number", "segment_type", "distance_m",
            "elevation_m", "is_ramp", "source",
        ]
        assert len(df) == len(prof.points)
        ramp_rows = df[df["segment_type"] == "ramp"]
        assert (ramp_rows["is_ramp"] == True).all()  # noqa: E712
        non_ramp = df[df["segment_type"] != "ramp"]
        assert (non_ramp["is_ramp"] == False).all()  # noqa: E712

    def test_csv_round_trip_preserves_rows_and_columns(self):
        prof = _populated_profile()
        df = prof.to_dataframe()
        csv_text = df.to_csv(index=False)
        df_back = pd.read_csv(io.StringIO(csv_text))
        assert list(df_back.columns) == list(df.columns)
        assert len(df_back) == len(df)
        pd.testing.assert_frame_equal(
            df_back.reset_index(drop=True),
            df.reset_index(drop=True),
            check_dtype=False,
        )

    def test_to_dataframe_with_benches_adds_hazard_columns(self):
        prof = _populated_profile()
        benches = [
            _bench(1, 10.0, 100.0, 15.0, 85.0, overhang_m=0.2),
            _bench(2, 25.0, 88.0, 30.0, 70.0, wedge_risk=True),
            _bench(3, 45.0, 65.0, 50.0, 50.0, is_ramp=True,
                   toppling_risk=True),
        ]
        df = prof.to_dataframe(benches=benches)
        for col in ("overhang_m", "wedge_risk", "toppling_risk"):
            assert col in df.columns
        b1 = df[df["bench_number"] == 1]
        assert (b1["overhang_m"] == 0.2).all()
        assert (b1["wedge_risk"] == False).all()  # noqa: E712
        b2 = df[df["bench_number"] == 2]
        assert (b2["wedge_risk"] == True).all()  # noqa: E712
        b3 = df[df["bench_number"] == 3]
        assert (b3["toppling_risk"] == True).all()  # noqa: E712

    def test_to_dataframe_benches_missing_bench_number_yields_defaults(self):
        prof = ReconciledProfile(
            distances=np.array([1.0, 2.0], dtype=float),
            elevations=np.array([10.0, 5.0], dtype=float),
            points=[
                ReconciledPoint(distance=1.0, elevation=10.0,
                                bench_number=42, segment_type="crest",
                                source="topo"),
            ],
        )
        df = prof.to_dataframe(benches=[])
        assert math.isnan(df["overhang_m"].iloc[0])
        assert df["wedge_risk"].iloc[0] == False  # noqa: E712
        assert df["toppling_risk"].iloc[0] == False  # noqa: E712


# ---------------------------------------------------------------------------
# 3. to_dict / from_dict
# ---------------------------------------------------------------------------


class TestToFromDict:
    """Tests for ``ReconciledProfile.to_dict`` and ``from_dict``."""

    def test_to_dict_key_shape(self):
        prof = _populated_profile()
        d = prof.to_dict()
        assert set(d.keys()) == {"distances", "elevations", "points", "source"}
        assert isinstance(d["distances"], list)
        assert isinstance(d["elevations"], list)
        assert isinstance(d["points"], list)
        assert isinstance(d["source"], str)

    def test_to_dict_is_json_serializable(self):
        prof = _populated_profile()
        d = prof.to_dict()
        encoded = json.dumps(d)
        decoded = json.loads(encoded)
        assert decoded["source"] == "topo"
        assert len(decoded["distances"]) == len(prof.distances)
        assert len(decoded["elevations"]) == len(prof.elevations)
        assert len(decoded["points"]) == len(prof.points)
        for pt in decoded["points"]:
            assert set(pt.keys()) == {
                "bench_number", "segment_type", "distance_m",
                "elevation_m", "is_ramp", "source",
            }

    def test_round_trip_preserves_fields(self):
        prof = _populated_profile()
        d = prof.to_dict()
        restored = ReconciledProfile.from_dict(json.loads(json.dumps(d)))
        assert restored.distances.shape == prof.distances.shape
        assert restored.elevations.shape == prof.elevations.shape
        np.testing.assert_allclose(restored.distances, prof.distances)
        np.testing.assert_allclose(restored.elevations, prof.elevations)
        assert len(restored.points) == len(prof.points)
        for orig, back in zip(prof.points, restored.points):
            assert back.bench_number == orig.bench_number
            assert back.segment_type == orig.segment_type
            assert back.distance == pytest.approx(orig.distance)
            assert back.elevation == pytest.approx(orig.elevation)
            assert back.source == orig.source

    def test_from_dict_empty(self):
        prof = ReconciledProfile.from_dict({})
        assert prof.distances.shape == (0,)
        assert prof.elevations.shape == (0,)
        assert prof.points == []

    def test_from_dict_drops_unknown_fields(self):
        d = {
            "distances": [1.0, 2.0],
            "elevations": [10.0, 5.0],
            "points": [{
                "bench_number": 1, "segment_type": "crest",
                "distance_m": 1.0, "elevation_m": 10.0,
                "is_ramp": False, "source": "topo",
                "future_field": "ignored",
                "another": 99,
            }],
            "source": "topo",
            "future_top_level": "ignored",
        }
        prof = ReconciledProfile.from_dict(d)
        assert len(prof.points) == 1
        assert prof.points[0].bench_number == 1


# ---------------------------------------------------------------------------
# 4. Legacy deprecation warning text
# ---------------------------------------------------------------------------


class TestLegacyDeprecationWarning:
    """The legacy builder must keep emitting DeprecationWarning with the v2
    successor and a 2-cycle removal horizon in the message."""

    def test_warning_emitted_on_legacy_call(self):
        benches = [_bench(1, 10.0, 100.0, 15.0, 85.0)]
        with pytest.warns(DeprecationWarning) as caught:
            build_reconciled_profile(benches)
        assert len(caught) >= 1
        msg = str(caught[0].message)
        assert "build_reconciled_profile_v2" in msg
        assert "2 release cycles" in msg

    def test_no_warning_when_return_v2_true(self):
        benches = [_bench(1, 10.0, 100.0, 15.0, 85.0)]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            build_reconciled_profile(benches, return_v2=True)
        deprecations = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert deprecations == [], (
            "v2 path must not emit DeprecationWarning; "
            f"got: {[str(w.message) for w in deprecations]}"
        )

    def test_warning_stacklevel_is_two(self):
        from core.profile_compliance import build_reconciled_profile as brp

        benches = [_bench(1, 10.0, 100.0, 15.0, 85.0)]
        with pytest.warns(DeprecationWarning) as caught:
            brp(benches)
        assert len(caught) >= 1
        assert caught[0].filename.endswith("test_reconciled_profile_serialization.py")


# ---------------------------------------------------------------------------
# 5. core.__init__ re-exports v2
# ---------------------------------------------------------------------------


class TestCoreReExportsV2:
    """``core`` must expose both ``build_reconciled_profile`` and
    ``build_reconciled_profile_v2`` and route to the same objects as
    ``core.param_extractor``."""

    def test_both_importable_from_core(self):
        from core import build_reconciled_profile, build_reconciled_profile_v2
        assert callable(build_reconciled_profile)
        assert callable(build_reconciled_profile_v2)

    def test_both_in_core_all(self):
        assert "build_reconciled_profile" in core.__all__
        assert "build_reconciled_profile_v2" in core.__all__

    def test_v2_identity_match_vs_param_extractor(self):
        from core.param_extractor import build_reconciled_profile_v2 as v2_legacy
        assert core.build_reconciled_profile_v2 is v2_legacy

    def test_legacy_identity_match_vs_param_extractor(self):
        from core.param_extractor import build_reconciled_profile as brp_legacy
        assert core.build_reconciled_profile is brp_legacy

    def test_param_extractor_module_reexports_v2(self):
        assert hasattr(param_extractor_mod, "build_reconciled_profile_v2")
        assert param_extractor_mod.build_reconciled_profile_v2 is build_reconciled_profile_v2


# ---------------------------------------------------------------------------
# 6. Legacy tuple contract preserved
# ---------------------------------------------------------------------------


class TestLegacyTupleContractPreserved:
    """The legacy builder must keep returning ``(np.array, np.array)`` and
    produce byte-for-byte identical output to the pre-change snapshot."""

    def test_three_bench_tuple_shape_and_dtype(self):
        benches = [
            _bench(1, 10.0, 100.0, 15.0, 85.0),
            _bench(2, 25.0, 88.0, 30.0, 70.0),
            _bench(3, 45.0, 65.0, 50.0, 50.0),
        ]
        d, e = build_reconciled_profile(benches)
        assert isinstance(d, np.ndarray)
        assert isinstance(e, np.ndarray)
        assert d.dtype == np.float64
        assert e.dtype == np.float64

    def test_three_bench_frozen_snapshot(self):
        benches = [
            _bench(1, 10.0, 100.0, 15.0, 85.0),
            _bench(2, 25.0, 88.0, 30.0, 70.0),
            _bench(3, 45.0, 65.0, 50.0, 50.0),
        ]
        d, e = build_reconciled_profile(benches)
        np.testing.assert_allclose(
            d, [10.0, 15.0, 25.0, 30.0, 45.0, 50.0]
        )
        np.testing.assert_allclose(
            e, [100.0, 85.0, 88.0, 70.0, 65.0, 50.0]
        )

    def test_empty_input_returns_empty_float_arrays(self):
        d, e = build_reconciled_profile([])
        assert isinstance(d, np.ndarray)
        assert isinstance(e, np.ndarray)
        assert d.shape == (0,)
        assert e.shape == (0,)
        assert d.dtype == np.float64
        assert e.dtype == np.float64