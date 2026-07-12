"""Tests for core.blast_attribution — per-feature blast hole attribution.

Covers the IDW-style ranking (kg / d^2) that links individual blast holes
to non-zero crest/toe deviations found in MATCH comparison rows. The
tests build a synthetic 4-hole 30×30 m box so distances and scores are
verifiable by hand.
"""
import math

import numpy as np
import pandas as pd
import pytest

from core.blast_attribution import attribute_holes_to_benches


def _hole(label, x, y, kg=200.0, malla="M-A"):
    return {
        "label_pozo": label,
        "X": float(x),
        "Y": float(y),
        "Kilos_Cargados_real": float(kg),
        "Malla": malla,
    }


def _holes_box():
    """4 holes in a 30x30 m box, distinguishable kg + distance to feature."""
    return pd.DataFrame(
        [
            _hole("H1", 10.0, 10.0, kg=200.0),  # far from feature @ (0,0): ~14.1 m
            _hole("H2", 2.0, 0.0, kg=100.0),    # closest: ~2 m, smallest kg
            _hole("H3", 6.0, 0.0, kg=300.0),    # ~6 m
            _hole("H4", 8.0, 0.0, kg=150.0),    # ~8 m
        ]
    )


def _section(name, az, origin=(0.0, 0.0)):
    return type(
        "Sec",
        (),
        {
            "name": name,
            "origin": np.array([float(origin[0]), float(origin[1])]),
            "azimuth": float(az),
            "length": 200.0,
            "sector": "",
        },
    )()


def _match_row(section, bench_num, crest_d, toe_d, delta_crest, delta_toe, bd_crest_d=20.0, bd_toe_d=0.0):
    """Build a MATCH dict with a bench_real carrying the along-profile distances."""
    bench_real = type(
        "BR",
        (),
        {
            "crest_distance": float(crest_d),
            "toe_distance": float(toe_d),
            "bench_height": 15.0,
            "face_angle": 70.0,
            "berm_width": 9.0,
        },
    )()
    bench_design = type(
        "BD",
        (),
        {
            "crest_distance": float(bd_crest_d),
            "toe_distance": float(bd_toe_d),
            "bench_height": 15.0,
            "face_angle": 70.0,
            "berm_width": 9.0,
        },
    )()
    return {
        "section": section,
        "bench_num": int(bench_num),
        "type": "MATCH",
        "level": "4200",
        "delta_crest": float(delta_crest),
        "delta_toe": float(delta_toe),
        "bench_real": bench_real,
        "bench_design": bench_design,
    }


def _single_feature_match(section_name, bench_num, crest_d, toe_d, delta_crest, delta_toe):
    """One MATCH row -> two candidate feature entries (crest + toe)."""
    return [
        _match_row(
            section=section_name,
            bench_num=bench_num,
            crest_d=crest_d,
            toe_d=toe_d,
            delta_crest=delta_crest,
            delta_toe=delta_toe,
        )
    ]


class TestGracefulAbsence:
    def test_empty_blast_df_returns_empty(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.8)
        assert attribute_holes_to_benches(pd.DataFrame(), comps, sections) == []

    def test_none_blast_df_returns_empty(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.8)
        assert attribute_holes_to_benches(None, comps, sections) == []

    def test_missing_xy_returns_empty(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.8)
        df = pd.DataFrame({"label_pozo": ["P1"], "Kilos_Cargados_real": [200.0]})
        assert attribute_holes_to_benches(df, comps, sections) == []

    def test_no_comparisons_returns_empty(self):
        sections = [_section("S1", az=0.0)]
        assert attribute_holes_to_benches(_holes_box(), [], sections) == []

    def test_no_sections_returns_empty(self):
        comps = _single_feature_match("S1", 1, 5.0, 15.0, 1.2, 0.8)
        assert attribute_holes_to_benches(_holes_box(), comps, []) == []

    def test_unknown_section_returns_empty(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("UNKNOWN", 1, 5.0, 15.0, 1.2, 0.8)
        assert attribute_holes_to_benches(_holes_box(), comps, sections) == []

    def test_non_match_rows_ignored(self):
        sections = [_section("S1", az=0.0)]
        row = _match_row("S1", 1, 5.0, 15.0, 1.2, 0.8)
        row["type"] = "MISSING"
        assert attribute_holes_to_benches(_holes_box(), [row], sections) == []


class TestMinDeviationGate:
    def test_no_deviated_rows_returns_empty(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=0.3, delta_toe=0.5)
        assert attribute_holes_to_benches(_holes_box(), comps, sections) == []

    def test_exactly_at_threshold_returns_empty(self):
        """Boundary: |delta| == min_delta_m is excluded (strict >)."""
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=0.5, delta_toe=0.5)
        assert attribute_holes_to_benches(_holes_box(), comps, sections, min_delta_m=0.5) == []

    def test_custom_threshold_raises_floor(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=0.8, delta_toe=0.1)
        results = attribute_holes_to_benches(
            _holes_box(), comps, sections, min_delta_m=0.3,
        )
        assert len(results) == 1
        assert results[0]["feature"] == "crest"


class TestKgFallback:
    def test_missing_kg_column_uses_fallback(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.8)
        df = pd.DataFrame({
            "label_pozo": ["H1", "H2", "H3", "H4"],
            "X": [10.0, 2.0, 6.0, 8.0],
            "Y": [10.0, 0.0, 0.0, 0.0],
        })
        results = attribute_holes_to_benches(df, comps, sections, tolerance=30.0)
        assert results, "Expected at least one deviated feature"
        for entry in results:
            assert entry["top_holes"], f"No holes attributed for {entry['feature']}"
            for hole in entry["top_holes"]:
                assert hole["kg"] == pytest.approx(1.0)
                assert hole["contribution_pct"] >= 0.0

    def test_kg_column_precedence(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.8)
        df = pd.DataFrame({
            "label_pozo": ["H1", "H2"],
            "X": [10.0, 2.0],
            "Y": [10.0, 0.0],
            "Kilos_Cargados_real": [250.0, 0.0],
            "Kilos_Cargados": [999.0, 999.0],
        })
        results = attribute_holes_to_benches(df, comps, sections, tolerance=30.0, top_n=2)
        crest = next(r for r in results if r["feature"] == "crest")
        top = crest["top_holes"][0]
        assert top["label_pozo"] == "H1"
        assert top["kg"] == pytest.approx(250.0)


class TestTopNLimit:
    def test_top_n_limits_results(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.0)
        results = attribute_holes_to_benches(
            _holes_box(), comps, sections, tolerance=30.0, top_n=2, min_delta_m=0.5,
        )
        crest = next(r for r in results if r["feature"] == "crest")
        assert len(crest["top_holes"]) == 2
        scores = [h["contribution_pct"] for h in crest["top_holes"]]
        assert scores == sorted(scores, reverse=True)

    def test_score_uses_floored_inverse_distance_squared(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=0.0, toe_d=15.0,
                                      delta_crest=0.0, delta_toe=1.2)
        df = pd.DataFrame({
            "label_pozo": ["near", "mid", "far"],
            "X": [0.0, 0.0, 0.0],
            "Y": [14.0, 10.0, 5.0],
            "Kilos_Cargados_real": [100.0, 100.0, 100.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=30.0, top_n=3, min_delta_m=0.5,
        )
        toe = next(r for r in results if r["feature"] == "toe")
        labels = [h["label_pozo"] for h in toe["top_holes"]]
        assert labels == ["near", "mid", "far"]

    def test_d2_floor_prevents_div_by_zero(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=0.0, toe_d=0.0,
                                      delta_crest=1.2, delta_toe=0.0)
        df = pd.DataFrame({
            "label_pozo": ["coincident"],
            "X": [0.0],
            "Y": [0.0],
            "Kilos_Cargados_real": [200.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=30.0, top_n=1, min_delta_m=0.5,
        )
        crest = next(r for r in results if r["feature"] == "crest")
        assert crest["top_holes"][0]["kg"] == pytest.approx(200.0)
        assert math.isfinite(crest["top_holes"][0]["contribution_pct"])


class TestMultiFeatureIsolation:
    def test_hole_near_two_features_appears_in_both(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=2.0, toe_d=5.0,
                                      delta_crest=1.2, delta_toe=0.8)
        df = pd.DataFrame({
            "label_pozo": ["shared", "far"],
            "X": [2.0, 50.0],
            "Y": [0.0, 50.0],
            "Kilos_Cargados_real": [300.0, 50.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=15.0, top_n=3, min_delta_m=0.5,
        )
        by_feature = {r["feature"]: r for r in results}
        assert set(by_feature) == {"crest", "toe"}
        for entry in by_feature.values():
            assert entry["top_holes"][0]["label_pozo"] == "shared"
            assert entry["n_candidates"] == 1
            assert sum(h["contribution_pct"] for h in entry["top_holes"]) == pytest.approx(100.0)

    def test_no_cross_feature_aggregation(self):
        """A hole that only matches one feature must not inflate the other."""
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=2.0, toe_d=50.0,
                                      delta_crest=1.2, delta_toe=0.8)
        df = pd.DataFrame({
            "label_pozo": ["near_crest"],
            "X": [2.0],
            "Y": [0.0],
            "Kilos_Cargados_real": [300.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=15.0, top_n=3, min_delta_m=0.5,
        )
        by_feature = {r["feature"]: r for r in results}
        assert "crest" in by_feature
        assert "toe" not in by_feature


class TestCoordinateTransform:
    def test_world_xy_azimuth_zero_is_north(self):
        """azimuth_to_direction(0) == [0, 1] -> feature world Y = +d."""
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=10.0, toe_d=20.0,
                                      delta_crest=1.2, delta_toe=0.0)
        df = pd.DataFrame({
            "label_pozo": ["north", "east"],
            "X": [0.0, 10.0],
            "Y": [10.0, 0.0],
            "Kilos_Cargados_real": [100.0, 100.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=15.0, top_n=2, min_delta_m=0.5,
        )
        crest = next(r for r in results if r["feature"] == "crest")
        top_labels = [h["label_pozo"] for h in crest["top_holes"]]
        assert top_labels[0] == "north"

    def test_world_xy_azimuth_ninety_is_east(self):
        """azimuth_to_direction(90) == [1, 0] -> feature world X = +d."""
        sections = [_section("S1", az=90.0)]
        comps = _single_feature_match("S1", 1, crest_d=10.0, toe_d=20.0,
                                      delta_crest=1.2, delta_toe=0.0)
        df = pd.DataFrame({
            "label_pozo": ["east", "north"],
            "X": [10.0, 0.0],
            "Y": [0.0, 10.0],
            "Kilos_Cargados_real": [100.0, 100.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=15.0, top_n=2, min_delta_m=0.5,
        )
        crest = next(r for r in results if r["feature"] == "crest")
        top_labels = [h["label_pozo"] for h in crest["top_holes"]]
        assert top_labels[0] == "east"


class TestTolerance:
    def test_outside_tolerance_excluded(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=10.0, toe_d=20.0,
                                      delta_crest=1.2, delta_toe=0.0)
        df = pd.DataFrame({
            "label_pozo": ["too_far"],
            "X": [100.0],
            "Y": [100.0],
            "Kilos_Cargados_real": [999.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=5.0, top_n=5, min_delta_m=0.5,
        )
        assert results == []

    def test_n_candidates_counts_all_within_radius(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.0)
        df = pd.DataFrame({
            "label_pozo": ["A", "B", "C"],
            "X": [3.0, 7.0, 100.0],
            "Y": [0.0, 0.0, 0.0],
            "Kilos_Cargados_real": [100.0, 100.0, 100.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=15.0, top_n=5, min_delta_m=0.5,
        )
        crest = next(r for r in results if r["feature"] == "crest")
        assert crest["n_candidates"] == 2


class TestResultShape:
    def test_required_fields_present(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.8)
        results = attribute_holes_to_benches(
            _holes_box(), comps, sections, tolerance=30.0, top_n=3, min_delta_m=0.5,
        )
        assert results
        for entry in results:
            assert {"section", "bench_num", "feature", "delta_m",
                    "n_candidates", "top_holes"} <= set(entry)
            assert entry["feature"] in {"crest", "toe"}
            for hole in entry["top_holes"]:
                assert {"label_pozo", "malla", "kg", "distance_m",
                        "contribution_pct"} <= set(hole)

    def test_sorted_by_contribution_descending(self):
        sections = [_section("S1", az=0.0)]
        comps = _single_feature_match("S1", 1, crest_d=5.0, toe_d=15.0,
                                      delta_crest=1.2, delta_toe=0.0)
        df = pd.DataFrame({
            "label_pozo": ["H2", "H1", "H3", "H4"],
            "X": [2.0, 10.0, 6.0, 8.0],
            "Y": [0.0, 10.0, 0.0, 0.0],
            "Kilos_Cargados_real": [100.0, 200.0, 300.0, 150.0],
        })
        results = attribute_holes_to_benches(
            df, comps, sections, tolerance=30.0, top_n=4, min_delta_m=0.5,
        )
        crest = next(r for r in results if r["feature"] == "crest")
        contribs = [h["contribution_pct"] for h in crest["top_holes"]]
        assert contribs == sorted(contribs, reverse=True)