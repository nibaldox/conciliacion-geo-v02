"""Tests for the web executive PDF report (``core.web_pdf_report``).

Every case builds a real ``ReportData`` through
``core.report_data.build_report_data`` (or derives from one with
``dataclasses.replace``) so the assertions run against the same numbers the
Word report and the dashboard use. Page text is read back with ``pdftotext``;
the tests skip when that binary is not installed.
"""

import shutil
import subprocess
import types
from dataclasses import replace

import pytest

from core.report_data import ReportFilters, build_report_data
from core.web_pdf_report import build_pdf_report

PDFTOTEXT = shutil.which("pdftotext")

pytestmark = pytest.mark.skipif(PDFTOTEXT is None, reason="pdftotext not available")


def _comparison(
    section="S-01",
    sector="A",
    bench=1,
    row_type="MATCH",
    height=(15.0, 15.4, "CUMPLE"),
    angle=(60.0, 62.0, "CUMPLE"),
    berm=(8.0, 7.6, "CUMPLE"),
    level="3100",
    delta_crest=0.4,
    delta_toe=-0.3,
):
    """Build one comparison row with the persisted result-dict shape."""
    h_design, h_real, h_status = height
    a_design, a_real, a_status = angle
    b_design, b_real, b_status = berm
    return {
        "section": section,
        "sector": sector,
        "level": level,
        "bench_num": bench,
        "type": row_type,
        "height_design": h_design,
        "height_real": h_real,
        "height_dev": None if h_real is None or h_design is None else h_real - h_design,
        "height_status": h_status,
        "angle_design": a_design,
        "angle_real": a_real,
        "angle_dev": None if a_real is None or a_design is None else a_real - a_design,
        "angle_status": a_status,
        "berm_design": b_design,
        "berm_real": b_real,
        "berm_dev": None if b_real is None or b_design is None else b_real - b_design,
        "berm_status": b_status,
        "berm_min": 7.0,
        "spill_width": 1.2,
        "effective_berm": 7.0,
        "delta_crest": delta_crest,
        "delta_toe": delta_toe,
    }


SETTINGS = {
    "process": {"resolution": 0.1, "face_threshold": 28.0, "berm_threshold": 10.0},
    "tolerances": {
        "bench_height": {"neg": 2.0, "pos": 3.0},
        "face_angle": {"neg": 5.0, "pos": 5.0},
        "berm_width": {"min": 7.0},
        "crest_toe_deviation": {"neg": 1.0, "pos": 1.0},
    },
}

META = {
    "project": "Rajo Prueba",
    "author": "Autora de Prueba",
    "operation": "Operación",
    "phase": "Fase 1",
    "generated_at": "18/10/2026 12:00",
    "process": {"resolution": 0.1, "face_threshold": 28.0, "berm_threshold": 10.0},
    "design_file": "diseno.stl",
    "topo_file": "topografia.stl",
}

PLAN_INPUTS = {
    "sections": [
        {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 120.0, "sector": "A"},
        {"name": "S-02", "origin": [40.0, 20.0], "azimuth": 90.0, "length": 120.0, "sector": "B"},
    ]
}


def _sample_data():
    rows = [
        _comparison(section="S-01", sector="A", bench=1),
        _comparison(
            section="S-01",
            sector="A",
            bench=2,
            height=(15.0, 19.0, "FUERA DE TOLERANCIA"),
            angle=(60.0, 70.0, "NO CUMPLE"),
            berm=(8.0, 5.0, "NO CUMPLE"),
            delta_crest=3.6,
            delta_toe=3.1,
        ),
        _comparison(section="S-02", sector="B", bench=1, row_type="MISSING",
                    height=(15.0, None, None), angle=(60.0, None, None),
                    berm=(8.0, None, None), delta_crest=None, delta_toe=None),
        _comparison(section="S-02", sector="B", bench=2),
    ]
    return build_report_data(rows, SETTINGS, ReportFilters(), META, plan_inputs=PLAN_INPUTS)


def _text(pdf_bytes):
    proc = subprocess.run(
        [PDFTOTEXT, "-layout", "-", "-"],
        input=pdf_bytes,
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode("utf-8", errors="replace")


def _pages(pdf_bytes):
    return [page for page in _text(pdf_bytes).split("\f") if page.strip()]


@pytest.fixture(scope="module")
def sample_pdf():
    return build_pdf_report(_sample_data()).getvalue()


def test_returns_seekable_pdf_buffer():
    buffer = build_pdf_report(_sample_data())
    assert buffer.seekable()
    payload = buffer.getvalue()
    assert payload.startswith(b"%PDF")
    assert payload.rstrip().endswith(b"%%EOF")


def test_expected_sections_present(sample_pdf):
    text = _text(sample_pdf)
    assert "1. Resumen ejecutivo" in text
    assert "2. Criterios" in text
    assert "3. Cumplimiento por parámetro" in text
    assert "4. Logro de diseño por sector" in text
    assert "5. Mayores desviaciones" in text
    assert "6. Plano de cumplimiento" in text


def test_depth_section_absent_when_depth_is_none(sample_pdf):
    data = _sample_data()
    assert data.depth is None
    assert "Profundidad del rajo" not in _text(sample_pdf)


def test_depth_section_present_with_depth():
    data = replace(
        _sample_data(),
        depth={"cota_piso": 3000.0, "cota_cresta": 3120.5, "profundidad": 120.5,
               "n_floors": 3, "n_crests": 4},
    )
    text = _text(build_pdf_report(data).getvalue())
    assert "Profundidad del rajo" in text
    assert "120.50 m" in text


def test_sector_section_omitted_without_design_achievement():
    data = replace(_sample_data(), design_achievement=None)
    text = _text(build_pdf_report(data).getvalue())
    assert "Logro de diseño por sector" not in text


def test_blast_section_only_with_blast(sample_pdf):
    assert "Resumen de tronadura" not in _text(sample_pdf)

    data = replace(
        _sample_data(),
        blast={
            "holes": [
                {"X": 1.0, "Y": 2.0, "Z_collar": 3100.0, "Burden": 3.5, "Esp": 4.0},
                {"X": 5.0, "Y": 6.0, "Z_collar": 3115.0, "Burden": 3.9, "Esp": 4.2},
            ],
            "tolerance": {"neg": 1.0, "pos": 1.0},
        },
    )
    text = _text(build_pdf_report(data).getvalue())
    assert "Resumen de tronadura" in text
    assert "Pozos registrados" in text
    assert "3.70 m" in text


def test_blast_missing_values_never_render_nan():
    data = replace(
        _sample_data(),
        blast={
            "holes": [
                {"X": 1.0, "Y": 2.0, "Z_collar": 3100.0, "Burden": 3.5, "Esp": 4.0},
                {"X": 5.0, "Y": None, "Z_collar": float("nan"), "Burden": None},
                {"Z_collar": "sin dato"},
            ],
            "tolerance": {"neg": 1.0, "pos": float("nan")},
        },
    )
    text = _text(build_pdf_report(data).getvalue())
    assert "Resumen de tronadura" in text
    assert "Pozos registrados" in text
    assert "nan" not in text
    assert "None" not in text
    assert "—" in text


def test_top_deviation_headers_and_values():
    data = _sample_data()
    parameters = {entry["parameter"] for entry in data.top_deviations}
    assert parameters <= {"height", "angle", "berm"}
    text = _text(build_pdf_report(data).getvalue())
    assert "Altura de banco —" in text
    assert "Ángulo de cara —" in text
    assert "Desviación (m)" in text
    assert "Desviación (°)" in text
    assert "Tolerancia (m)" in text
    assert "Tolerancia (°)" in text
    assert "Estado" in text
    assert "NO CUMPLE" in text


def test_top_deviations_grouped_per_parameter_present():
    data = _sample_data()
    grouped = {}
    for entry in data.top_deviations:
        grouped.setdefault(entry["parameter"], []).append(entry)
    assert {"height", "angle"} <= set(grouped) <= {"height", "angle", "berm"}
    text = _text(build_pdf_report(data).getvalue())
    labels = {"height": "Altura de banco", "angle": "Ángulo de cara", "berm": "Ancho de berma"}
    for parameter, entries in grouped.items():
        shown = min(len(entries), 5)
        assert f"{labels[parameter]} — {shown} de {len(entries)} mayores" in text


def test_top_deviations_limited_to_five_per_parameter():
    rows = [
        _comparison(
            section=f"S-{index:02d}",
            bench=index,
            height=(15.0, 15.0 + index, "FUERA DE TOLERANCIA"),
            angle=(60.0, None, None),
            berm=(8.0, None, None),
        )
        for index in range(1, 8)
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    assert sum(1 for entry in data.top_deviations if entry["parameter"] == "height") == 7
    text = _text(build_pdf_report(data).getvalue())
    assert "Altura de banco — 5 de 7 mayores" in text
    assert "S-07" in text
    assert "S-01" not in text
    assert "S-02" not in text


def test_top_deviation_headers_are_metres_when_only_lengths():
    rows = [
        _comparison(section="S-01", bench=1, height=(15.0, 19.4, "FUERA DE TOLERANCIA"),
                    angle=(60.0, None, None), berm=(8.0, None, None)),
        _comparison(section="S-02", bench=2, height=(15.0, 12.0, "FUERA DE TOLERANCIA"),
                    angle=(60.0, None, None), berm=(8.0, None, None)),
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    assert {entry["parameter"] for entry in data.top_deviations} == {"height"}
    text = _text(build_pdf_report(data).getvalue())
    assert "Desviación (m)" in text
    assert "Tolerancia (m)" in text
    assert "Desviación (°)" not in text
    assert "-3.00" in text


def test_page_numbering_on_every_page_except_cover(sample_pdf):
    pages = _pages(sample_pdf)
    total = len(pages)
    assert total >= 5
    assert "Página" not in pages[0]
    assert "Informe de conciliación geotécnica" not in pages[0]
    for index, page in enumerate(pages[1:], start=2):
        assert f"Página {index} de {total}" in page
        assert META["project"] in page
        assert "Informe de conciliación geotécnica" in page


def test_criteria_shows_signed_tolerances_and_filters(sample_pdf):
    text = _text(sample_pdf)
    assert "-2.00 m / +3.00 m" in text
    assert "± 5.0 °" in text
    assert "≥ 7.00 m" in text
    assert "Sin filtros" in text
    assert "Resolución de malla" in text
    assert "0.10 m" in text
    assert "diseno.stl" in text


def test_plan_section_omitted_without_geometry():
    data = replace(_sample_data(), plan_inputs=None, section_geometry=())
    text = _text(build_pdf_report(data).getvalue())
    assert "Plano de cumplimiento" not in text
    assert "5. Mayores desviaciones" in text


def test_plan_section_accepts_section_line_objects():
    section_line = types.SimpleNamespace(
        name="S-01", origin=[100.0, 200.0], azimuth=45.0, length=80.0, sector="A"
    )
    data = replace(_sample_data(), plan_inputs={"sections": [section_line]})
    text = _text(build_pdf_report(data).getvalue())
    assert "Plano de cumplimiento" in text


def test_parameter_table_and_summary_numbers(sample_pdf):
    text = _text(sample_pdf)
    assert "Altura de banco (m)" in text
    assert "Valor medio real" in text
    assert "Perfiles" in text
    assert "Total de perfiles" in text
    assert "Puntaje ponderado global" in text


def test_empty_data_still_builds_a_valid_pdf():
    data = build_report_data([], SETTINGS, ReportFilters(), META)
    payload = build_pdf_report(data).getvalue()
    assert payload.startswith(b"%PDF")
    text = _text(payload)
    assert "No hay comparaciones para reportar con los filtros aplicados." in text
    assert "No hay comparaciones en la sesión." in text
