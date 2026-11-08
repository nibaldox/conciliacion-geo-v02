"""Residuales de puntaje: denominadores, nullable, hazards y atribución (wave 7).

Contrato: un dato faltante es ``None`` — se muestra «sin dato» y se excluye de
los denominadores; un ``0`` medido sigue siendo ``0``.
"""

import inspect
import re
from types import SimpleNamespace

import numpy as np
import openpyxl
import pandas as pd
import pytest

from core.ai_v2.builder import (
    _coerce_bench_params,
    _render_compliance_table,
    _render_stability_summary,
    build_analysis_prompt,
)
from core.bench_hazards import _evaluate_catch_bench_adequacy
from core.compliance_status import (
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_NO_CUMPLE,
)
from core.excel_writer import export_results
from core.profile_extract import BenchParams
from core.stability_analysis import assess_bench_stability, compute_section_health_score

TOLERANCES = {
    "bench_height": {"neg": 1.0, "pos": 1.0},
    "face_angle": {"neg": 2.0, "pos": 2.0},
    "berm_width": {"min": 7.0},
}


def _comp(bench_num, *, angle_status=STATUS_CUMPLE, berm_status=STATUS_CUMPLE):
    return {
        "sector": "Norte",
        "section": "S-01",
        "bench_num": bench_num,
        "type": "MATCH",
        "level": "3855",
        "height_design": 15.0,
        "height_real": 15.2,
        "height_dev": 0.2,
        "height_status": STATUS_CUMPLE,
        "angle_design": 70.0,
        "angle_real": 68.0,
        "angle_dev": -2.0,
        "angle_status": angle_status,
        "berm_design": 9.0,
        "berm_real": None if berm_status == "-" else 8.5,
        "berm_min": 7.0,
        "berm_status": berm_status,
        "spill_width": 0.0,
        "effective_berm": None if berm_status == "-" else 8.5,
        "delta_crest": 0.1,
        "delta_toe": -0.2,
        "bench_design": None,
        "bench_real": None,
        "berm_score": None if berm_status == "-" else 60,
        "angle_score": 10,
        "height_score": 30,
        "bench_score": None if berm_status == "-" else 100,
        "section_score": 85.0,
        "section_status": STATUS_CUMPLE,
    }


def _comparisons():
    return [
        _comp(1),
        _comp(2, angle_status=STATUS_NO_CUMPLE),
        _comp(3, berm_status="-"),
    ]


def _find_row(ws, label, column=1):
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=column).value == label:
            return row
    raise AssertionError(f"fila {label!r} no encontrada en {ws.title}")


def _texts(ws):
    found = []
    for row in ws.iter_rows(values_only=True):
        found.extend(str(value) for value in row if value is not None)
    return " ".join(found)


@pytest.fixture()
def workbook(tmp_path):
    out = tmp_path / "residuals.xlsx"
    export_results(
        _comparisons(),
        [SimpleNamespace(section_name="S-01", sector="Norte",
                         inter_ramp_angle=48.0, overall_angle=42.0)],
        [SimpleNamespace(section_name="S-01", sector="Norte",
                         inter_ramp_angle=47.0, overall_angle=41.0)],
        TOLERANCES,
        str(out),
    )
    return openpyxl.load_workbook(str(out))


def test_resumen_denominator_excludes_not_evaluable_berm(workbook):
    ws = workbook["Resumen"]
    row = _find_row(ws, "Ancho de berma")
    values = [ws.cell(row=row, column=col).value for col in range(1, 7)]

    assert values[1] == 2
    assert values[3] == 3
    assert "2 evaluables de 3" in str(values[4])
    assert values[5] == "100.0%"


def test_dashboard_denominator_excludes_not_evaluable_berm(workbook):
    ws = workbook["Dashboard"]
    row = _find_row(ws, "Ancho de berma")

    assert ws.cell(row=row, column=2).value == 2
    assert ws.cell(row=row, column=5).value == "100.0%"
    assert "2 de 3" in str(ws.cell(row=row, column=4).value)


def test_dashboard_global_score_uses_evaluable_denominators(workbook):
    ws = workbook["Dashboard"]
    row = _find_row(ws, "Cumplimiento General (Score Global)")

    assert ws.cell(row=row, column=2).value == "87.5%"


def test_sector_summary_berm_percentage_excludes_not_evaluable(workbook):
    ws = workbook["Resumen Ejecutivo"]
    row = _find_row(ws, "Norte")

    assert ws.cell(row=row, column=2).value == 3
    assert ws.cell(row=row, column=6).value == "100.0%"
    assert "2" in str(ws.cell(row=row, column=7).value)
    assert "de 3" in str(ws.cell(row=row, column=7).value)


def _partial_bench(**changes):
    base = dict(
        bench_number=1,
        crest_elevation=100.0,
        crest_distance=0.0,
        toe_elevation=85.0,
        toe_distance=15.0,
        bench_height=15.0,
        face_angle=70.0,
        berm_width=None,
        effective_berm_width=None,
        spill_width=0.0,
        floor_elevation=85.0,
    )
    base.update(changes)
    return BenchParams(**base)


def test_coerce_bench_params_keeps_missing_berm_as_none():
    coerced = _coerce_bench_params({"berm_real": None, "effective_berm": None,
                                    "bench_height": 15.0})

    assert isinstance(coerced, BenchParams)
    assert coerced.berm_width is None
    assert coerced.effective_berm_width is None


def test_coerce_bench_params_keeps_measured_zero():
    coerced = _coerce_bench_params({"berm_real": 0.0, "effective_berm": 0.0})

    assert coerced.berm_width == 0.0
    assert coerced.effective_berm_width == 0.0


def test_compliance_table_counts_not_evaluable_rows_separately():
    table = _render_compliance_table(_comparisons())

    assert "Sin dato" in table
    berm_line = next(line for line in table.splitlines() if line.startswith("| BERM"))
    assert berm_line.rstrip().endswith("| 1 |")


def test_prompt_marks_missing_berm_as_sin_dato():
    results = [
        {"section": "S-01", "bench_num": 1, "type": "MATCH",
         "berm_status": "-", "berm_real": None,
         "bench_real": _partial_bench()},
    ]
    _, user = build_analysis_prompt(results)
    _, raw = build_analysis_prompt(_comparisons())

    assert "sin dato" in user.lower()
    assert "| BERM |" not in user or "Sin dato" in user or "sin dato" in user.lower()
    assert raw


def test_stability_summary_reports_missing_berm_instead_of_flagging():
    results = [
        {"section": "S-01", "bench_num": 1, "type": "MATCH",
         "bench_real": _partial_bench()},
    ]
    out = _render_stability_summary(results)

    assert "Health Score" in out or "sin dato" in out.lower()
    assert "sin dato" in out.lower()


def test_evaluate_catch_bench_tolerates_missing_berm():
    bench = _partial_bench()

    _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)

    assert bench.catch_bench_ratio is None
    assert bench.catch_bench_adequate is None
    assert bench.catch_bench_status == "-"


def test_evaluate_catch_bench_still_scores_measured_berm():
    bench = _partial_bench(berm_width=9.0, effective_berm_width=8.0)

    _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)

    assert bench.catch_bench_ratio == pytest.approx(8.0 / 9.0)
    assert bench.catch_bench_adequate is True
    assert bench.catch_bench_status != "-"


def test_assess_bench_stability_tolerates_missing_berm():
    bench = _partial_bench()
    _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)

    assessment = assess_bench_stability(bench)

    assert assessment.catch_bench_ratio is None
    assert assessment.catch_bench_adequate is None


def test_section_health_excludes_not_evaluable_berm_from_berm_component():
    missing = _partial_bench(bench_number=1, crest_distance=0.0, toe_distance=15.0)
    measured = _partial_bench(bench_number=2, berm_width=9.0,
                              effective_berm_width=8.0)
    for bench in (missing, measured):
        _evaluate_catch_bench_adequacy([bench], berm_design_min_m=6.0)

    score = compute_section_health_score("S-01", [missing, measured])

    assert score.components["berm"] == pytest.approx(8.0 / 9.0 * 100.0)


def test_attribute_failure_has_a_single_definition():
    import core.blast_correlation as module

    source = inspect.getsource(module)
    assert len(re.findall(r"^def attribute_failure_to_holes\(", source, re.M)) == 1


def test_attribute_failure_returns_holes_inside_the_section():
    import core.blast_correlation as module
    from core.section_cutter import SectionLine

    holes = pd.DataFrame([
        {
            "uniqid": "H1",
            "X": 0.3,
            "Y": 10.0,
            "Z_collar": 100.0,
            "Z_toe": 85.0,
            "Len": 15.0,
            "pf_vol_kgm3": 0.6,
            "stemming_ratio": 0.7,
            "Burden": 5.0,
            "Esp": 4.0,
            "subdrilling_ratio": 1.0,
            "kg_per_meter": 2.0,
        },
        {
            "uniqid": "H2",
            "X": 0.4,
            "Y": 14.0,
            "Z_collar": 100.0,
            "Z_toe": 85.0,
            "Len": 15.0,
            "pf_vol_kgm3": 0.4,
            "stemming_ratio": 0.5,
            "Burden": 5.0,
            "Esp": 4.0,
            "subdrilling_ratio": 1.0,
            "kg_per_meter": 2.0,
        },
        {
            "uniqid": "H3",
            "X": 40.0,
            "Y": 10.0,
            "Z_collar": 100.0,
            "Z_toe": 85.0,
            "Len": 15.0,
            "pf_vol_kgm3": 9.9,
            "stemming_ratio": 0.9,
            "Burden": 5.0,
            "Esp": 4.0,
            "subdrilling_ratio": 1.0,
            "kg_per_meter": 2.0,
        },
    ])
    section = SectionLine(
        name="S-01", origin=np.array([0.0, 0.0]), azimuth=0.0, length=100.0
    )
    bench_real = _partial_bench()
    comp_row = {"section": "S-01", "bench_num": 1, "bench_real": bench_real}

    result = module.attribute_failure_to_holes(comp_row, holes, section)

    assert result is not None
    assert result["n_holes"] == 2
    assert result["pf_avg"] == pytest.approx(0.5)
    assert {hole["id"] for hole in result["holes"]} == {"H1", "H2"}
