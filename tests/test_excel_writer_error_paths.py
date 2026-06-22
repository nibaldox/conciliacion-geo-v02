"""Tests for core.excel_writer error paths — Sprint 0 issue D2.

Verifies that export failures are caught and re-raised as
ExcelWriterError instead of crashing the caller.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.excel_writer import ExcelWriterError, export_results


def test_export_raises_excel_writer_error_on_save_failure(tmp_path):
    """Simulate wb.save() raising; we expect ExcelWriterError, not OSError."""
    out = tmp_path / "out.xlsx"
    with patch("core.excel_writer.openpyxl.Workbook.save",
               side_effect=PermissionError("disk full")):
        with pytest.raises(ExcelWriterError) as ei:
            export_results(
                comparisons=[],
                params_design=[],
                params_topo=[],
                tolerances={},
                output_path=str(out),
            )
    assert "export_results" in str(ei.value)
    assert "disk full" in str(ei.value)


def test_excel_writer_error_includes_original_cause():
    """The 'from e' chain must be preserved so callers can introspect."""
    try:
        try:
            raise OSError("original cause")
        except OSError as exc:
            raise ExcelWriterError("wrapped") from exc
    except ExcelWriterError as caught:
        assert isinstance(caught.__cause__, OSError)
        assert "original cause" in str(caught.__cause__)


def test_excel_writer_error_message_identifies_failure(tmp_path):
    out = tmp_path / "out.xlsx"
    with patch("core.excel_writer._write_summary_sheet",
               side_effect=ValueError("bad data")):
        with pytest.raises(ExcelWriterError) as ei:
            export_results(
                comparisons=[{"bench_num": 1}],
                params_design=[],
                params_topo=[],
                tolerances={},
                output_path=str(out),
            )
    msg = str(ei.value)
    assert "export_results" in msg
    assert "ValueError" in msg
    assert "bad data" in msg
