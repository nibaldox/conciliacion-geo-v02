"""Contract: an absent berm is "not evaluable", never a zero score or a crash.

A real bench whose berm cannot be measured (``None``/``NaN``/``inf``) carries
``berm_status='-'``, ``berm_score=None`` and ``bench_score=None`` from
``_build_match_row``. Every consumer listed here must tolerate that ``None``
instead of turning it into 0 (a fake failure) or raising ``TypeError``.
"""

import math
from types import SimpleNamespace

import pandas as pd
import pytest

from core.profile_compliance import _build_match_row, compare_design_vs_asbuilt

TOL = {
    "bench_height": {"neg": 1.0, "pos": 1.0},
    "face_angle": {"neg": 1.0, "pos": 1.0},
    "berm_width": {"min": 7.0},
}

BENCH = dict(
    bench_height=15.0,
    face_angle=70.0,
    berm_width=8.0,
    bench_number=1,
    crest_elevation=115.0,
    toe_elevation=100.0,
    crest_distance=1.0,
    toe_distance=2.0,
    spill_width=0.0,
    effective_berm_width=8.0,
    floor_elevation=100.0,
    is_ramp=False,
)

SECTION = SimpleNamespace(
    section_name="S-01", sector="Norte", inter_ramp_angle=48.0, overall_angle=42.0
)


def bench(**changes):
    return SimpleNamespace(**{**BENCH, **changes})


def lower_bench(**changes):
    base = dict(
        BENCH,
        bench_number=2,
        crest_elevation=100.0,
        toe_elevation=85.0,
        floor_elevation=85.0,
    )
    base.update(changes)
    return SimpleNamespace(**base)


def params(benches):
    return SimpleNamespace(benches=benches, sector="Norte", section_name="S-01")


def _unscorable_section():
    return compare_design_vs_asbuilt(
        params([bench(), lower_bench()]),
        params([bench(berm_width=None), lower_bench()]),
        TOL,
    )


def _word_cells(path):
    from docx import Document

    document = Document(str(path))
    return [cell.text for table in document.tables for row in table.rows for cell in row.cells]


def test_section_score_excludes_match_without_bench_score():
    rows = _unscorable_section()
    scores = {row["bench_num"]: row["bench_score"] for row in rows if row["type"] == "MATCH"}

    assert scores[1] is None
    assert scores[2] == 100
    assert {row["section_score"] for row in rows} == {100.0}
    assert {row["section_status"] for row in rows} == {"CUMPLE"}


def test_section_score_stays_zero_when_no_match_is_scorable():
    rows = compare_design_vs_asbuilt(
        params([bench()]), params([bench(berm_width=None)]), TOL
    )

    assert [row["type"] for row in rows] == ["MATCH"]
    assert rows[0]["bench_score"] is None
    assert rows[0]["section_score"] == 0.0
    assert rows[0]["section_status"] == "NO CUMPLE"


def test_missing_row_tolerates_absent_design_berm():
    rows = compare_design_vs_asbuilt(params([bench(berm_width=None)]), params([]), TOL)

    assert [row["type"] for row in rows] == ["MISSING"]
    assert rows[0]["berm_design"] is None
    assert rows[0]["section_score"] == 0.0


def test_extra_row_tolerates_absent_real_berm():
    rows = compare_design_vs_asbuilt(
        params([]), params([bench(berm_width=None, effective_berm_width=None)]), TOL
    )

    assert [row["type"] for row in rows] == ["EXTRA"]
    assert rows[0]["berm_real"] is None
    assert rows[0]["effective_berm"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_berm_is_not_evaluable(value):
    rows = compare_design_vs_asbuilt(
        params([bench()]), params([bench(berm_width=value)]), TOL
    )

    row = rows[0]
    assert row["berm_status"] == "-"
    assert row["berm_score"] is None
    assert row["bench_score"] is None
    assert row["berm_real"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_design_berm_is_reported_as_missing(value):
    rows = compare_design_vs_asbuilt(
        params([bench(berm_width=value)]), params([bench()]), TOL
    )
    row = rows[0]

    assert row["berm_design"] is None
    assert row["berm_real"] == 8.0
    assert row["berm_status"] == "CUMPLE"

    missing = compare_design_vs_asbuilt(params([bench(berm_width=value)]), params([]), TOL)
    assert missing[0]["berm_design"] is None


def test_word_report_renders_sin_dato_for_unscorable_match(tmp_path):
    from core import generate_word_report

    comparisons = _unscorable_section()
    out = tmp_path / "report.docx"
    generate_word_report(comparisons, [], str(out))

    assert out.exists() and out.stat().st_size > 0
    cells = _word_cells(out)
    assert "sin dato" in cells
    assert not any("nan" in cell.lower() for cell in cells)
    assert not any(cell.startswith("✗") for cell in cells)


def test_word_report_averages_ignore_non_finite_berm(tmp_path):
    from core import generate_word_report

    comparisons = _unscorable_section() + [
        {
            "type": "MATCH",
            "section": "S-01",
            "sector": "Norte",
            "bench_num": 3,
            "level": "70",
            "bench_score": 100,
            "section_score": 100.0,
            "height_status": "CUMPLE",
            "angle_status": "CUMPLE",
            "berm_status": "CUMPLE",
            "height_real": 15.0,
            "angle_real": 70.0,
            "berm_real": float("nan"),
            "height_design": 15.0,
            "angle_design": 70.0,
            "berm_design": 8.0,
        }
    ]
    out = tmp_path / "report.docx"
    generate_word_report(comparisons, [], str(out))

    cells = _word_cells(out)
    assert not any("nan" in cell.lower() for cell in cells)


def test_excel_export_tolerates_unscorable_match(tmp_path):
    from core import export_results

    comparisons = _unscorable_section()
    out = tmp_path / "export.xlsx"
    export_results(comparisons, [SECTION], [SECTION], TOL, str(out))

    assert out.exists() and out.stat().st_size > 0


def test_unified_dataframe_reports_absent_berm_as_missing():
    from core.unified_dataframe import build_unified_dataframe

    frame = build_unified_dataframe(_unscorable_section(), tolerances=TOL)
    value = frame.loc[0, "berm_width_real"]

    assert value is None or pd.isna(value)
    score = frame.loc[0, "bench_score"]
    assert score is None or pd.isna(score)


def test_pdf_breakdown_ignores_non_finite_berm():
    from core.pdf_report import _compliance_breakdown

    rows = [
        {
            "type": "MATCH",
            "section": "S-01",
            "berm_status": "CUMPLE",
            "berm_real": float("nan"),
            "height_status": "CUMPLE",
            "height_real": 15.0,
            "angle_status": "CUMPLE",
            "angle_real": 70.0,
        }
    ]
    breakdown = {item["label"]: item for item in _compliance_breakdown(rows)}

    assert breakdown["Ancho de Berma"]["avg_str"] == "N/A"


def test_report_data_marks_unscorable_match_unknown():
    from core.report_data import _bench_score_status

    row = {"type": "MATCH", "bench_score": None, "berm_status": "-"}
    assert _bench_score_status(row) == "UNKNOWN"


def _projected_frame(rows):
    return pd.DataFrame(rows)


@pytest.fixture
def blast_rows(monkeypatch):
    import core.blast_correlation as blast_correlation

    frame = _projected_frame(
        [
            {
                "uniqid": "H1",
                "pf_vol_kgm3": 0.8,
                "stemming_ratio": float("nan"),
                "Burden": 5.0,
                "Esp": None,
                "subdrilling_ratio": float("nan"),
                "kg_per_meter": float("nan"),
                "X": 0.0,
                "Y": 0.0,
                "Z_collar": 100.0,
                "Z_toe": 85.0,
                "dist_along": 5.0,
            },
            {
                "uniqid": "H2",
                "pf_vol_kgm3": 0.4,
                "stemming_ratio": 0.7,
                "Burden": 5.0,
                "Esp": 4.0,
                "subdrilling_ratio": 1.0,
                "kg_per_meter": 2.0,
                "X": 10.0,
                "Y": 0.0,
                "Z_collar": 100.0,
                "Z_toe": 85.0,
                "dist_along": 6.0,
            },
        ]
    )
    monkeypatch.setattr(
        blast_correlation, "proyectar_pozos_en_seccion", lambda *args, **kwargs: frame
    )
    bench_real = SimpleNamespace(
        crest_elevation=100.0,
        toe_elevation=85.0,
        crest_distance=0.0,
        toe_distance=15.0,
        bench_number=1,
    )
    return (
        blast_correlation,
        {"section": "S-01", "bench_num": 1, "bench_real": bench_real},
        pd.DataFrame([{"X": 0.0}]),
    )


def test_attribute_failure_keeps_missing_metrics_missing(blast_rows):
    module, comp_row, holes_frame = blast_rows

    result = module.attribute_failure_to_holes(comp_row, holes_frame, SimpleNamespace())

    assert result["n_holes"] == 2
    first = result["holes"][0]
    assert first["stemming_ratio"] is None
    assert first["spacing"] is None
    assert first["subdrill"] is None
    assert first["kg_per_meter"] is None
    assert result["pf_avg"] == pytest.approx(0.6)
    assert result["stemming_ratio_avg"] == pytest.approx(0.7)
    assert result["subdrill_avg"] == pytest.approx(1.0)
    assert result["kg_per_meter_avg"] == pytest.approx(2.0)
    assert result["kg_total"] is None


def test_attribute_failure_returns_none_when_nothing_is_measurable(blast_rows, monkeypatch):
    module, comp_row, holes_frame = blast_rows

    only_missing = _projected_frame(
        [
            {
                "uniqid": "H1",
                "pf_vol_kgm3": float("nan"),
                "stemming_ratio": None,
                "Burden": float("nan"),
                "Esp": None,
                "subdrilling_ratio": float("nan"),
                "kg_per_meter": None,
                "X": 0.0,
                "Y": 0.0,
                "Z_collar": 100.0,
                "Z_toe": 85.0,
                "dist_along": 5.0,
            }
        ]
    )
    monkeypatch.setattr(
        module, "proyectar_pozos_en_seccion", lambda *args, **kwargs: only_missing
    )

    result = module.attribute_failure_to_holes(comp_row, holes_frame, SimpleNamespace())

    assert result["n_holes"] == 1
    assert result["pf_avg"] is None
    assert result["stemming_ratio_avg"] is None
    assert result["burden_avg"] is None
    assert result["kg_per_meter_avg"] is None
