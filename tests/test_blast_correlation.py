"""Tests for core.blast_correlation — Drill & Blast ↔ Geotechnical correlation."""
import numpy as np
import pandas as pd
import pytest

from core.blast_correlation import (
    BlastCorrelationRow,
    classify_berm_as_ramp,
    compute_blast_geotech_correlation,
    compute_pasadura_stats,
    compute_signed_deviations,
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


class TestComputeSignedDeviations:
    """Over- vs under-excavation split (sign convention: +over / -under)."""

    def test_splits_positive_and_negative(self):
        comps = [
            {"section": "S1", "delta_crest": 0.6},
            {"section": "S1", "delta_crest": 1.2},
            {"section": "S1", "delta_crest": -0.8},
            {"section": "S1", "delta_crest": None},
            {"section": "S2", "delta_crest": 5.0},
        ]
        r = compute_signed_deviations(comps, "S1")
        assert r["n_over"] == 2
        assert r["n_under"] == 1
        assert r["avg_over"] == pytest.approx(0.9)
        assert r["avg_under"] == pytest.approx(-0.8)

    def test_empty_or_missing_section(self):
        assert compute_signed_deviations([], "S1") == {
            "avg_over": 0.0, "avg_under": 0.0, "n_over": 0, "n_under": 0,
        }
        assert compute_signed_deviations([{"section": "X", "delta_crest": 1.0}], "S1")["n_over"] == 0

    def test_falls_back_to_delta_toe(self):
        r = compute_signed_deviations(
            [{"section": "S1", "delta_toe": -0.5}], "S1"
        )
        assert r["n_under"] == 1 and r["avg_under"] == pytest.approx(-0.5)


class TestBlastCorrelationRowBackwardsCompat:
    def test_as_tuple_returns_four_elements(self):
        """as_tuple must stay a 4-tuple: report_generator/excel_writer unpack it."""
        row = BlastCorrelationRow(
            "S1", 3, 1000.0, 0.5,
            avg_over_break=0.7, avg_under_break=-0.4, n_over=2, n_under=1,
        )
        sec_name, num_wells, total_kg, avg_dev = row.as_tuple()
        assert (sec_name, num_wells, total_kg, avg_dev) == ("S1", 3, 1000.0, 0.5)

    def test_as_signed_tuple_carries_new_fields(self):
        row = BlastCorrelationRow(
            "S1", 3, 1000.0, 0.5,
            avg_over_break=0.7, avg_under_break=-0.4, n_over=2, n_under=1,
        )
        signed = row.as_signed_tuple()
        assert len(signed) == 8
        assert signed[4] == 0.7 and signed[5] == -0.4
        assert signed[6] == 2 and signed[7] == 1

    def test_new_fields_default_to_zero(self):
        row = BlastCorrelationRow("S1", 0, 0.0, 0.0)
        assert row.avg_over_break == 0.0
        assert row.avg_under_break == 0.0
        assert row.n_over == 0 and row.n_under == 0

    def test_correlation_rows_carry_signed_fields(self):
        df = procesar_pozos(_valid_hole(0.0, 0.0))[0]
        sections = [_section("S1", 0.0, 0.0, 90.0)]
        comps = [
            {"section": "S1", "delta_crest": 0.8},
            {"section": "S1", "delta_crest": -0.3},
        ]
        rows = compute_blast_geotech_correlation(df, sections, comps)
        assert rows[0].num_wells == 1
        assert rows[0].avg_over_break == pytest.approx(0.8)
        assert rows[0].avg_under_break == pytest.approx(-0.3)
        assert rows[0].n_over == 1 and rows[0].n_under == 1


class TestClassifyBermAsRamp:
    def test_within_ramp_range(self):
        assert classify_berm_as_ramp(RAMP.min_width) is True
        assert classify_berm_as_ramp((RAMP.min_width + RAMP.max_width) / 2) is True
        assert classify_berm_as_ramp(RAMP.max_width) is True

    def test_outside_ramp_range(self):
        assert classify_berm_as_ramp(0.0) is False
        assert classify_berm_as_ramp(RAMP.min_width - 1) is False
        assert classify_berm_as_ramp(RAMP.max_width + 1) is False
