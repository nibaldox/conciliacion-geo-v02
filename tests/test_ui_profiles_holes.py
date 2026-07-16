"""Tests for ui.tabs.profiles.holes (pure blast-hole helpers)."""
import pandas as pd
import pytest

from ui.tabs.profiles.holes import get_or_project_pozos


class _FakeSection:
    def __init__(self, origin, azimuth, length):
        self.origin = origin
        self.azimuth = azimuth
        self.length = length


def _make_blast_df():
    return pd.DataFrame({
        "X": [0.0],
        "Y": [0.0],
        "Z_collar": [100.0],
        "X_toe": [0.0],
        "Y_toe": [10.0],
        "Z_toe": [90.0],
    })


class TestGetOrProjectPozos:
    def test_returns_projected_dataframe(self):
        section = _FakeSection(origin=[0.0, 0.0], azimuth=0.0, length=100.0)
        blast_df = _make_blast_df()
        cache = {}

        result = get_or_project_pozos(blast_df, section, tolerance=10.0, cache=cache)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert "dist_along" in result.columns

    def test_reuses_cached_result(self):
        section = _FakeSection(origin=[0.0, 0.0], azimuth=0.0, length=100.0)
        blast_df = _make_blast_df()
        cache = {}

        result1 = get_or_project_pozos(blast_df, section, tolerance=10.0, cache=cache)
        result2 = get_or_project_pozos(blast_df, section, tolerance=10.0, cache=cache)

        assert result1 is result2
        assert len(cache) == 1

    def test_cache_key_includes_tolerance(self):
        section = _FakeSection(origin=[0.0, 0.0], azimuth=0.0, length=100.0)
        blast_df = _make_blast_df()
        cache = {}

        result1 = get_or_project_pozos(blast_df, section, tolerance=10.0, cache=cache)
        result2 = get_or_project_pozos(blast_df, section, tolerance=20.0, cache=cache)

        assert result1 is not result2
        assert len(cache) == 2
