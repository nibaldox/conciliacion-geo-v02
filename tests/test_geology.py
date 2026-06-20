"""Tests for core.geology — Phase 11 RMR/GSI/strength helpers."""
import math
import os

import pandas as pd
import pytest

from core.geology import (
    RockMassEntry,
    estimate_rock_strength_from_gsi,
    load_rmr_table,
    lookup_rmr,
    rmr_to_gsi,
)


@pytest.fixture
def sample_rmr_csv(tmp_path):
    rows = (
        "sector,level,rmr,rqd,ucs_mpa,lithology\n"
        "Norte,100,72,85,150,Granodiorite\n"
        "Norte,115,68,80,140,Granodiorite\n"
        "Norte,130,65,75,130,Granodiorite\n"
        "Sur,110,55,60,90,Andesite\n"
        "Sur,125,52,55,85,Andesite\n"
    )
    p = tmp_path / "rmr.csv"
    p.write_text(rows)
    return str(p)


@pytest.fixture
def rmr_missing_required(tmp_path):
    p = tmp_path / "rmr_bad.csv"
    p.write_text("sector,level,rqd\nNorte,100,80\n")
    return str(p)


@pytest.fixture
def rmr_with_optional(tmp_path):
    p = tmp_path / "rmr_full.csv"
    p.write_text(
        "sector,level,rmr,rqd,ucs_mpa,lithology,j1_dip,j1_dipdir\n"
        "Norte,100,72,85,150,Granodiorite,45,90\n"
    )
    return str(p)


class TestLoadRMR:
    """Phase 11 — E.1 CSV loader for the RMR table."""

    def test_load_valid_csv(self, sample_rmr_csv):
        """Loads required + optional columns and coerces numeric types."""
        df = load_rmr_table(sample_rmr_csv)
        assert isinstance(df, pd.DataFrame)
        assert list(df['sector'].unique()) == ['Norte', 'Sur']
        assert df['level'].dtype.kind in ('i', 'f')
        assert df['rmr'].dtype.kind in ('i', 'f')
        assert len(df) == 5
        for col in ('sector', 'level', 'rmr', 'rqd', 'ucs_mpa', 'lithology'):
            assert col in df.columns

    def test_missing_required_columns_raises(self, rmr_missing_required):
        """CSV without 'rmr' → ValueError listing missing cols."""
        with pytest.raises(ValueError) as excinfo:
            load_rmr_table(rmr_missing_required)
        assert 'rmr' in str(excinfo.value)

    def test_load_includes_optional_columns_when_present(self, rmr_with_optional):
        """Optional columns (j1_dip, j1_dipdir) survive normalization."""
        df = load_rmr_table(rmr_with_optional)
        assert 'j1_dip' in df.columns
        assert 'j1_dipdir' in df.columns
        assert int(df.iloc[0]['j1_dip']) == 45


class TestLookupRMR:
    """Phase 11 — E.1 sector+level lookup with tolerance."""

    def test_exact_match(self, sample_rmr_csv):
        """Exact sector + level → returns that row verbatim."""
        df = load_rmr_table(sample_rmr_csv)
        entry = lookup_rmr(df, 'Norte', 100.0)
        assert entry is not None
        assert entry.sector == 'Norte'
        assert entry.level == pytest.approx(100.0)
        assert entry.rmr == pytest.approx(72.0)
        assert entry.rqd == pytest.approx(85.0)
        assert entry.ucs_mpa == pytest.approx(150.0)
        assert entry.lithology == 'Granodiorite'

    def test_within_tolerance(self, sample_rmr_csv):
        """level within ±5m of a row → returns that row."""
        df = load_rmr_table(sample_rmr_csv)
        entry = lookup_rmr(df, 'Norte', 118.0, level_tolerance_m=5.0)
        assert entry is not None
        assert entry.level == pytest.approx(115.0)
        assert entry.rmr == pytest.approx(68.0)

    def test_outside_tolerance_returns_none(self, sample_rmr_csv):
        """level > tolerance from any row → None."""
        df = load_rmr_table(sample_rmr_csv)
        entry = lookup_rmr(df, 'Norte', 200.0, level_tolerance_m=5.0)
        assert entry is None

    def test_no_sector_returns_none(self, sample_rmr_csv):
        """Unknown sector → None."""
        df = load_rmr_table(sample_rmr_csv)
        entry = lookup_rmr(df, 'Inexistente', 100.0)
        assert entry is None

    def test_empty_dataframe_returns_none(self):
        """Empty df → None."""
        empty = pd.DataFrame({'sector': [], 'level': [], 'rmr': []})
        assert lookup_rmr(empty, 'X', 100.0) is None
        assert lookup_rmr(None, 'X', 100.0) is None

    def test_closest_level_wins(self, sample_rmr_csv):
        """Multiple rows within tolerance → closest one is returned."""
        df = load_rmr_table(sample_rmr_csv)
        entry = lookup_rmr(df, 'Sur', 113.0, level_tolerance_m=20.0)
        assert entry is not None
        assert entry.sector == 'Sur'
        assert entry.level == pytest.approx(110.0)


class TestRMRToGSI:
    """Phase 11 — E.2 empirical RMR → GSI conversion."""

    def test_basic_conversion(self):
        """RMR=65 → GSI=60 (offset of 5)."""
        assert rmr_to_gsi(65.0) == pytest.approx(60.0)
        assert rmr_to_gsi(45.0) == pytest.approx(40.0)

    def test_clamped_above(self):
        """RMR > 100 → GSI clamped to 100."""
        assert rmr_to_gsi(120.0) == 100.0
        assert rmr_to_gsi(105.0) == 100.0

    def test_clamped_below(self):
        """RMR < 0 → GSI clamped to 0."""
        assert rmr_to_gsi(-5.0) == 0.0
        assert rmr_to_gsi(0.0) == 0.0


class TestEstimateRockStrength:
    """Phase 11 — E.2 Hoek-Brown strength estimator."""

    def test_zero_inputs_returns_fallback(self):
        """gsi<=0 or ucs<=0 → conservative (c=0, phi=30)."""
        assert estimate_rock_strength_from_gsi(0.0, 100.0) == (0.0, 30.0)
        assert estimate_rock_strength_from_gsi(70.0, 0.0) == (0.0, 30.0)
        assert estimate_rock_strength_from_gsi(-1.0, 50.0) == (0.0, 30.0)

    def test_high_gsi_reasonable_strength(self):
        """gsi=70, ucs=150 MPa → c > 0 and phi in (30°, 60°)."""
        c, phi = estimate_rock_strength_from_gsi(70.0, 150.0)
        assert c > 0.0
        assert phi > 30.0
        assert phi <= 60.0

    def test_strength_increases_with_gsi(self):
        """Higher GSI (with same UCS) → higher cohesion (rock mass tougher)."""
        c_low, _ = estimate_rock_strength_from_gsi(40.0, 100.0)
        c_high, _ = estimate_rock_strength_from_gsi(70.0, 100.0)
        assert c_high > c_low
