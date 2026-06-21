"""Tests for core.profile_compliance.compute_sector_deviations (Phase 21)."""

import numpy as np
import pytest

from core.profile_compliance import (
    SectorDeviation,
    compute_sector_deviations,
)


def _linear_profile(d0=0.0, d1=300.0, e0=100.0, e1=130.0, n=601):
    d = np.linspace(d0, d1, n)
    e = np.linspace(e0, e1, n)
    return d, e


def _hump_profile(n=601):
    d = np.linspace(0.0, 300.0, n)
    e = np.empty_like(d)
    e[d <= 100.0] = 100.0 + 0.1 * d[d <= 100.0]
    mid = (d > 100.0) & (d <= 200.0)
    e[mid] = 110.0 - 0.2 * (d[mid] - 100.0)
    e[d > 200.0] = 90.0 + 0.1 * (d[d > 200.0] - 200.0)
    return d, e


class TestComputeSectorDeviations:

    def test_clean_profile_no_deviation(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e.copy(), tolerance_m=0.3)
        assert len(sectors) >= 1
        assert all(s.classification == "compliant" for s in sectors)
        for s in sectors:
            assert s.area_above_m2 == pytest.approx(0.0, abs=1e-6)
            assert s.area_below_m2 == pytest.approx(0.0, abs=1e-6)
            assert s.net_area_m2 == pytest.approx(0.0, abs=1e-6)

    def test_uniform_overbreak(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e + 0.5, tolerance_m=0.3)
        assert len(sectors) >= 1
        assert all(s.classification == "overbreak" for s in sectors)
        for s in sectors:
            assert s.area_above_m2 > 0.0
            assert s.area_below_m2 == pytest.approx(0.0, abs=1e-6)
            assert s.mean_delta_h == pytest.approx(0.5, abs=1e-2)

    def test_uniform_underbreak(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e - 0.5, tolerance_m=0.3)
        assert len(sectors) >= 1
        assert all(s.classification == "underbreak" for s in sectors)
        for s in sectors:
            assert s.area_below_m2 > 0.0
            assert s.area_above_m2 == pytest.approx(0.0, abs=1e-6)
            assert s.mean_delta_h == pytest.approx(-0.5, abs=1e-2)

    def test_mixed_sectors(self):
        d, e = _hump_profile()
        offset = np.where(d < 100.0, 0.0, np.where(d < 200.0, 0.6, -0.6))
        topo_e = e + offset
        sectors = compute_sector_deviations(d, e, d, topo_e, tolerance_m=0.3)
        assert len(sectors) == 3
        classes = [s.classification for s in sectors]
        assert classes == ["compliant", "overbreak", "underbreak"]
        assert sectors[1].d_start == pytest.approx(100.0, abs=1.0)
        assert sectors[2].d_start == pytest.approx(200.0, abs=1.0)
        for sid, s in enumerate(sectors, start=1):
            assert s.sector_id == sid
            assert s.d_end > s.d_start

    def test_within_tolerance(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e + 0.2, tolerance_m=0.3)
        assert len(sectors) >= 1
        for s in sectors:
            assert s.classification == "compliant"
            assert s.max_delta_h == pytest.approx(0.2, abs=1e-2)

    def test_area_calculation_symmetry(self):
        d, e = _linear_profile()
        offset = np.where(d < d[-1] / 2.0, 0.6, -0.6)
        topo_e = e + offset
        sectors = compute_sector_deviations(d, e, d, topo_e, tolerance_m=0.2)
        assert len(sectors) == 1
        s = sectors[0]
        assert s.classification == "mixed"
        assert s.area_above_m2 == pytest.approx(s.area_below_m2, rel=0.02)
        assert s.net_area_m2 == pytest.approx(0.0, abs=0.5)

    def test_returns_sector_deviation_instances(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e + 0.5)
        assert len(sectors) >= 1
        assert all(isinstance(s, SectorDeviation) for s in sectors)
        s = sectors[0]
        for attr in (
            "sector_id", "d_start", "d_end", "area_above_m2", "area_below_m2",
            "net_area_m2", "classification", "mean_delta_h", "max_delta_h",
            "centroid_d", "centroid_delta_h",
        ):
            assert hasattr(s, attr)

    def test_no_overlap_returns_empty(self):
        d, e = _linear_profile(d0=0.0, d1=100.0)
        d2, e2 = _linear_profile(d0=500.0, d1=600.0)
        sectors = compute_sector_deviations(d, e, d2, e2)
        assert sectors == []

    def test_classification_thresholds(self):
        d, e = _linear_profile(d0=0.0, d1=100.0)
        sectors = compute_sector_deviations(d, e, d, e + 0.4, tolerance_m=0.3)
        assert len(sectors) == 1
        assert sectors[0].classification == "overbreak"
        sectors_ok = compute_sector_deviations(d, e, d, e + 0.25, tolerance_m=0.3)
        assert sectors_ok[0].classification == "compliant"


class TestSectorHoverData:

    _HOVER_FIELDS = (
        "sector_id", "classification", "d_start", "d_end",
        "mean_delta_h", "max_delta_h", "area_above_m2", "area_below_m2",
    )

    def test_customdata_shape(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e + 0.5, tolerance_m=0.3)
        assert len(sectors) >= 1
        customdata = np.column_stack([
            [getattr(s, f) for s in sectors] for f in self._HOVER_FIELDS
        ])
        assert customdata.shape == (len(sectors), 8)

    def test_classification_strings(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e + 0.5, tolerance_m=0.3)
        valid = {"overbreak", "underbreak", "compliant", "mixed"}
        assert len(sectors) >= 1
        assert all(isinstance(s.classification, str) for s in sectors)
        assert all(s.classification in valid for s in sectors)

    def test_hoverable_with_strict_overbreak(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e + 5.0, tolerance_m=0.3)
        assert len(sectors) >= 1
        assert all(s.classification == "overbreak" for s in sectors)
        for s in sectors:
            assert s.mean_delta_h > 0
            assert s.area_above_m2 > 0.0
            assert s.area_below_m2 == pytest.approx(0.0, abs=1e-6)

    def test_hoverable_with_strict_underbreak(self):
        d, e = _linear_profile()
        sectors = compute_sector_deviations(d, e, d, e - 5.0, tolerance_m=0.3)
        assert len(sectors) >= 1
        assert all(s.classification == "underbreak" for s in sectors)
        for s in sectors:
            assert s.mean_delta_h < 0
            assert s.area_below_m2 > 0.0
