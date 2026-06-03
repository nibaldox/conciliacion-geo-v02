"""Tests for core.blast_correlation — Drill & Blast ↔ Geotechnical correlation."""
import numpy as np
import pandas as pd
import pytest

from core.blast_correlation import (
    BlastCorrelationRow,
    classify_berm_as_ramp,
    compute_blast_geotech_correlation,
    compute_pasadura_stats,
)
from core.config import RAMP
from core.calculo_tronadura import procesar_pozos


def _section(name, x, y, az, length=100.0):
    """Build a SectionLine-like object."""
    return type(
        "Sec",
        (),
        {"name": name, "origin": np.array([x, y]), "azimuth": az, "length": length, "sector": ""},
    )()


def _valid_hole(lat, lon, banco=4000.0, kg=200.0):
    return pd.DataFrame(
        [
            {
                "label_pozo": f"P-{lat:.0f}-{lon:.0f}",
                "Latitud_Geo": lat,
                "Longitud_Geo": lon,
                "Nombre_Banco": banco,
                "Inclinacion_real": 0.0,
                "Azimuth_real": 0.0,
                "longitud_real": 10.0,
                "Kilos_Cargados_real": kg,
                "fecha_tronadura": "2026-05-01",
            }
        ]
    )


class TestComputePasaduraStats:
    def test_empty_dataframe(self):
        s = compute_pasadura_stats(pd.DataFrame())
        assert s == {"total": 0, "mean": 0.0, "optimal_count": 0, "optimal_pct": 0.0}

    def test_none_input(self):
        s = compute_pasadura_stats(None)
        assert s["total"] == 0

    def test_optimal_pasadura_counted(self):
        # pasadura = (Z_collar - 15) - Z_toe. With Z_collar=4200, the formula
        # gives 4185 - Z_toe. For each row pick Z_toe such that the resulting
        # pasadura is 0.5, 1.5, 0.7, 5.0 respectively.
        df = pd.DataFrame(
            {
                "Z_collar": [4200.0, 4200.0, 4200.0, 4200.0],
                "Z_toe": [4184.5, 4183.5, 4184.3, 4180.0],  # → 0.5, 1.5, 0.7, 5.0
            }
        )
        s = compute_pasadura_stats(df)
        assert s["total"] == 4
        assert s["optimal_count"] == 3  # first three are within [0.5, 1.5]
        assert s["optimal_pct"] == pytest.approx(75.0, abs=0.1)


class TestComputeBlastGeotechCorrelation:
    def test_returns_one_row_per_section(self):
        # One hole at (0,0). Two sections: S1 passes through the hole, S2 is
        # 100 m away (beyond the 15 m default tolerance).
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        sections = [_section("S1", 0.0, 0.0, 90.0), _section("S2", 100.0, 0.0, 90.0)]
        comps = [
            {"section": "S1", "delta_crest": 0.3},
            {"section": "S2", "delta_crest": 0.5},
        ]
        rows = compute_blast_geotech_correlation(df, sections, comps)
        assert len(rows) == 2
        assert {r.section_name for r in rows} == {"S1", "S2"}
        s1, s2 = sorted(rows, key=lambda r: r.section_name)
        assert isinstance(s1, BlastCorrelationRow)
        assert s1.num_wells == 1   # hole is on S1
        assert s2.num_wells == 0   # hole is 100 m from S2 (>15 m tolerance)

    def test_no_sections_returns_empty(self):
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        assert compute_blast_geotech_correlation(df, [], []) == []
        assert compute_blast_geotech_correlation(None, [], []) == []
        assert compute_blast_geotech_correlation(pd.DataFrame(), [], []) == []

    def test_comparisons_without_deviation_column_still_work(self):
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        sections = [_section("S1", 0.0, 0.0, 90.0)]
        comps = [{"section": "S1", "height_status": "CUMPLE"}]  # no delta_crest
        rows = compute_blast_geotech_correlation(df, sections, comps)
        assert len(rows) == 1
        assert rows[0].mean_abs_deviation == 0.0


class TestClassifyBermAsRamp:
    def test_within_ramp_range(self):
        assert classify_berm_as_ramp(RAMP.min_width) is True
        assert classify_berm_as_ramp((RAMP.min_width + RAMP.max_width) / 2) is True
        assert classify_berm_as_ramp(RAMP.max_width) is True

    def test_outside_ramp_range(self):
        assert classify_berm_as_ramp(0.0) is False
        assert classify_berm_as_ramp(RAMP.min_width - 1) is False
        assert classify_berm_as_ramp(RAMP.max_width + 1) is False
