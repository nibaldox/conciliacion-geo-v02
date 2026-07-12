"""Tests for core.blast_model — quantitative blast models.

Focuses on :func:`compute_stemming_crest_correlation` (Gap 2). Mirrors
the pasadura tests at ``tests/test_blast_correlation.py:426-474`` in
shape: basic, no-data, single-bench, missing-columns.
"""
import numpy as np
import pandas as pd
import pytest


class TestComputeStemmingCrestCorrelation:
    def test_compute_stemming_crest_correlation_basic(self):
        from core.blast_model import compute_stemming_crest_correlation

        df = pd.DataFrame({
            "X": [0.0, 0.0, 10.0, 10.0, 20.0, 20.0, 30.0, 30.0],
            "Y": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "Z_collar": [4215.0, 4215.0, 4230.0, 4230.0,
                         4245.0, 4245.0, 4260.0, 4260.0],
            "Taco_m": [4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5],
        })
        comps = [
            {"level": "4200", "delta_crest": -1.5},
            {"level": "4215", "delta_crest": -1.0},
            {"level": "4230", "delta_crest": 0.5},
            {"level": "4245", "delta_crest": 1.5},
        ]
        res = compute_stemming_crest_correlation(df, comps, bench_height=15.0)
        assert res["n_benches"] == 4
        assert res["r"] < -0.9
        assert 4215.0 in res["stemming_per_bench"]
        assert 4215.0 in res["crest_per_bench"]
        assert "negativa" in res["interpretation"].lower() or "gases" in res["interpretation"].lower()

    def test_compute_stemming_crest_correlation_no_data(self):
        from core.blast_model import compute_stemming_crest_correlation

        res = compute_stemming_crest_correlation(pd.DataFrame(), [])
        assert res["r"] == 0.0
        assert res["n_benches"] == 0
        assert np.isnan(res["p_value"])
        assert "datos" in res["interpretation"].lower()

    def test_compute_stemming_crest_correlation_only_one_bench(self):
        from core.blast_model import compute_stemming_crest_correlation

        df = pd.DataFrame({
            "X": [0.0, 0.0],
            "Y": [0.0, 0.0],
            "Z_collar": [4215.0, 4215.0],
            "Taco_m": [3.0, 2.5],
        })
        comps = [{"level": "4200", "delta_crest": 0.5}]
        res = compute_stemming_crest_correlation(df, comps, bench_height=15.0)
        assert res["n_benches"] == 1
        assert res["r"] == 0.0
        assert "1" in res["interpretation"]

    def test_compute_stemming_crest_correlation_missing_columns(self):
        from core.blast_model import compute_stemming_crest_correlation

        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        comps = [{"level": "4200", "delta_crest": 0.1}]
        res = compute_stemming_crest_correlation(df, comps)
        assert res["n_benches"] == 0
        assert res["r"] == 0.0
        assert np.isnan(res["p_value"])
