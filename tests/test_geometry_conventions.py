"""Tests for core.geometry_conventions — canonical inclination/azimuth.

Canonical convention (per project spec §4.1):
- inclination: deviation from vertical, positive degrees, 0 = vertical
- azimuth: degrees clockwise from North (N=0, E=90, S=180, W=270)
"""
import numpy as np
import pandas as pd
import pytest

from core.geometry_conventions import (
    InclinationConvention,
    normalize_azimuth,
    normalize_inclination,
    normalize_vector_components,
)


class TestNormalizeInclination:
    def test_from_vertical_is_identity(self):
        v = pd.Series([0.0, 10.0, 45.0, 90.0])
        out, meta = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert out.tolist() == pytest.approx([0.0, 10.0, 45.0, 90.0])
        assert meta["convention"] == "from_vertical"

    def test_dip_from_horizontal_converted(self):
        v = pd.Series([0.0, 30.0, 60.0, 90.0])
        out, meta = normalize_inclination(v, InclinationConvention.DIP_FROM_HORIZONTAL)
        assert out.tolist() == pytest.approx([90.0, 60.0, 30.0, 0.0])
        assert meta["conversion"] == "dip->90-dip"

    def test_negative_values_recorded_and_absolutized(self):
        v = pd.Series([-10.0, -5.0, 0.0, 10.0])
        out, meta = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert out.tolist() == pytest.approx([10.0, 5.0, 0.0, 10.0])
        assert meta["negative_wrapped"] == 2

    def test_out_of_range_nan(self):
        v = pd.Series([120.0, -90.0, 10.0])
        out, meta = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert pd.isna(out.iloc[0])
        assert out.iloc[2] == pytest.approx(10.0)
        assert meta["rejected_out_of_range"] == 1

    def test_nan_passthrough(self):
        v = pd.Series([np.nan, 10.0])
        out, _ = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert pd.isna(out.iloc[0])
        assert out.iloc[1] == pytest.approx(10.0)


class TestNormalizeAzimuth:
    def test_from_north_cw_is_identity(self):
        v = pd.Series([0.0, 90.0, 180.0, 270.0, 360.0])
        out, meta = normalize_azimuth(v)
        assert out.tolist() == pytest.approx([0.0, 90.0, 180.0, 270.0, 0.0])
        assert meta["convention"] == "from_north_cw"

    def test_wrap_negative_and_overflow(self):
        v = pd.Series([-10.0, 370.0, 720.0])
        out, _ = normalize_azimuth(v)
        assert out.tolist() == pytest.approx([350.0, 10.0, 0.0])

    def test_nan_passthrough(self):
        v = pd.Series([np.nan, 45.0])
        out, _ = normalize_azimuth(v)
        assert pd.isna(out.iloc[0])
        assert out.iloc[1] == pytest.approx(45.0)


class TestNormalizeVectorComponents:
    def test_vertical_hole(self):
        incl = normalize_inclination(pd.Series([0.0]), InclinationConvention.FROM_VERTICAL)[0]
        az = normalize_azimuth(pd.Series([0.0]))[0]
        vx, vy, vz = normalize_vector_components(incl, az)
        assert vx.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vy.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vz.iloc[0] == pytest.approx(-1.0, abs=1e-9)

    def test_horizontal_north(self):
        incl = normalize_inclination(pd.Series([90.0]), InclinationConvention.FROM_VERTICAL)[0]
        az = normalize_azimuth(pd.Series([0.0]))[0]
        vx, vy, vz = normalize_vector_components(incl, az)
        assert vx.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vy.iloc[0] == pytest.approx(1.0, abs=1e-9)
        assert vz.iloc[0] == pytest.approx(0.0, abs=1e-9)

    def test_horizontal_east(self):
        incl = normalize_inclination(pd.Series([90.0]), InclinationConvention.FROM_VERTICAL)[0]
        az = normalize_azimuth(pd.Series([90.0]))[0]
        vx, vy, vz = normalize_vector_components(incl, az)
        assert vx.iloc[0] == pytest.approx(1.0, abs=1e-9)
        assert vy.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vz.iloc[0] == pytest.approx(0.0, abs=1e-9)

    def test_dip_convention_consistent(self):
        """A hole with dip=60 from horizontal equals incl=30 from vertical."""
        v1 = normalize_inclination(pd.Series([60.0]), InclinationConvention.DIP_FROM_HORIZONTAL)[0]
        v2 = normalize_inclination(pd.Series([30.0]), InclinationConvention.FROM_VERTICAL)[0]
        a1 = normalize_azimuth(pd.Series([0.0]))[0]
        c1 = normalize_vector_components(v1, a1)
        c2 = normalize_vector_components(v2, a1)
        for x, y in zip(c1, c2):
            assert x.iloc[0] == pytest.approx(y.iloc[0], abs=1e-9)
