"""Tests for ui.filters — Sprint 0 issue B1.

Single source of truth for filtering comparison results, shared between
ui.tabs.table and ui.tabs.ai_report.
"""
from __future__ import annotations

from ui.filters import apply_comparison_filters, filters_summary


def _bank(bench_num: int = 1, sector: str = "N", section: str = "S-1", level: str = "3110", **kw) -> dict:
    base = {
        "type": "MATCH",
        "sector": sector,
        "section": section,
        "level": level,
        "bench_num": bench_num,
    }
    base.update(kw)
    return base


class TestNoFilters:
    def test_empty_active_returns_all(self):
        banks = [_bank(1), _bank(2), _bank(3)]
        assert apply_comparison_filters(banks, {}) == banks

    def test_empty_lists_returns_all(self):
        banks = [_bank(1), _bank(2), _bank(3)]
        out = apply_comparison_filters(banks, {"sector": [], "section": []})
        assert out == banks


class TestSectorFilter:
    def test_single_sector(self):
        banks = [_bank(1, sector="N"), _bank(2, sector="S"), _bank(3, sector="N")]
        out = apply_comparison_filters(banks, {"sector": ["N"]})
        assert len(out) == 2
        assert all(b["sector"] == "N" for b in out)

    def test_multiple_sectors(self):
        banks = [_bank(1, sector="N"), _bank(2, sector="S"), _bank(3, sector="E")]
        out = apply_comparison_filters(banks, {"sector": ["N", "E"]})
        assert len(out) == 2


class TestSectionFilter:
    def test_single_section(self):
        banks = [_bank(1, section="S-1"), _bank(2, section="S-2"), _bank(3, section="S-1")]
        out = apply_comparison_filters(banks, {"section": ["S-1"]})
        assert len(out) == 2
        assert all(b["section"] == "S-1" for b in out)


class TestCombinedFilters:
    def test_intersect_sector_and_section(self):
        banks = [
            _bank(1, sector="N", section="S-1"),
            _bank(2, sector="N", section="S-2"),
            _bank(3, sector="S", section="S-1"),
        ]
        out = apply_comparison_filters(banks, {"sector": ["N"], "section": ["S-1"]})
        assert len(out) == 1
        assert out[0]["bench_num"] == 1

    def test_all_three_intersect(self):
        banks = [
            _bank(1, sector="N", section="S-1", level="3110"),
            _bank(2, sector="N", section="S-1", level="3120"),
            _bank(3, sector="N", section="S-1", level="3110"),
        ]
        out = apply_comparison_filters(
            banks,
            {"sector": ["N"], "section": ["S-1"], "level": ["3110"]},
        )
        assert len(out) == 2
        assert all(b["level"] == "3110" for b in out)


class TestBenchFilter:
    def test_single_bench(self):
        banks = [_bank(1), _bank(2), _bank(3)]
        out = apply_comparison_filters(banks, {"bench": [2]})
        assert len(out) == 1
        assert out[0]["bench_num"] == 2

    def test_extra_type_excluded_by_default(self):
        """Banks with type=EXTRA have bench_num=999; they should not pass
        unless 999 is explicitly selected."""
        banks = [_bank(1), {"type": "EXTRA", "bench_num": 999, "sector": "N",
                            "section": "S-1", "level": "3110"}]
        out = apply_comparison_filters(banks, {"bench": [1, 2]})
        assert len(out) == 1
        assert out[0]["bench_num"] == 1

    def test_extra_type_included_when_explicit(self):
        banks = [_bank(1), {"type": "EXTRA", "bench_num": 999, "sector": "N",
                            "section": "S-1", "level": "3110"}]
        out = apply_comparison_filters(banks, {"bench": [999]})
        assert len(out) == 1
        assert out[0]["type"] == "EXTRA"


class TestFiltersSummary:
    def test_no_filters_returns_ninguno(self):
        assert filters_summary({}) == "ninguno"

    def test_single_filter(self):
        s = filters_summary({"sector": ["Norte"]})
        assert s == "sector=Norte"

    def test_multiple_filters_joined(self):
        s = filters_summary({"sector": ["Norte"], "bench": [1, 2]})
        assert "sector=Norte" in s
        assert "banco=1,2" in s
