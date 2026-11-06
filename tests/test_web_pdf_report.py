"""Tests for the web executive PDF report built from the shared ReportData model."""

import shutil
import subprocess
import types
from dataclasses import replace

import pytest

from core.report_data import ReportFilters, build_report_data
import core.web_pdf_report as web_pdf_report
from core.web_pdf_report import _plan_sections, build_pdf_report

PDFTOTEXT = shutil.which("pdftotext")
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

requires_pdf_text = pytest.mark.skipif(
    PDFTOTEXT is None and PdfReader is None,
    reason="neither pdftotext nor pypdf is available",
)


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


def _text(pdf_bytes, *, layout=True):
    if PDFTOTEXT:
        proc = subprocess.run(
            [PDFTOTEXT, *(["-layout"] if layout else []), "-", "-"],
            input=pdf_bytes,
            capture_output=True,
            check=True,
        )
        return proc.stdout.decode("utf-8", errors="replace")
    if PdfReader is not None:
        import io

        return "\f".join(
            " ".join((page.extract_text() or "").split())
            for page in PdfReader(io.BytesIO(pdf_bytes)).pages
        )
    raise RuntimeError("neither pdftotext nor pypdf is available")


def _semantic_text(pdf_bytes):
    """Reading-order text with whitespace collapsed; for wording checks, not layout checks.

    ``pdftotext -layout`` interleaves neighbouring table cells inside a sentence and
    breaks long phrases across lines, so sentence assertions compare reading order.
    """
    if PDFTOTEXT:
        proc = subprocess.run(
            [PDFTOTEXT, "-", "-"],
            input=pdf_bytes,
            capture_output=True,
            check=True,
        )
        return " ".join(proc.stdout.decode("utf-8", errors="replace").split())
    return " ".join(_text(pdf_bytes).split())


def _pages(pdf_bytes):
    return [page for page in _text(pdf_bytes).split("\f") if page.strip()]


def _flowable_text(flowable):
    if hasattr(flowable, "getPlainText"):
        return flowable.getPlainText()
    cells = getattr(flowable, "_cellvalues", None)
    if cells is not None:
        return " ".join(_flowable_text(cell) for cell in cells)
    if isinstance(flowable, (list, tuple)):
        return " ".join(_flowable_text(item) for item in flowable)
    return str(flowable)


@pytest.fixture(scope="module")
def sample_pdf():
    return build_pdf_report(_sample_data()).getvalue()


def test_returns_seekable_pdf_buffer():
    buffer = build_pdf_report(_sample_data())
    assert buffer.seekable()
    payload = buffer.getvalue()
    assert payload.startswith(b"%PDF")
    assert payload.rstrip().endswith(b"%%EOF")


@pytest.mark.skipif(PdfReader is None, reason="pypdf not available")
def test_embedded_font_roundtrips_accents_and_keeps_a4_pages():
    import io

    reader = PdfReader(io.BytesIO(build_pdf_report(_sample_data()).getvalue()))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert "Desv. criterio" in text
    assert "Informe" in text
    assert len(reader.pages) <= 10
    assert all(
        float(page.mediabox.width) == pytest.approx(595.28, abs=0.1)
        and float(page.mediabox.height) == pytest.approx(841.89, abs=0.1)
        for page in reader.pages
    )
    if web_pdf_report._BODY_FONT == "GeoVera":
        assert "Informe de conciliación geotécnica" in text
        assert "Sección" in text
        assert web_pdf_report._report_styles()["body"].fontName == "GeoVera"
        assert web_pdf_report._report_styles()["h1"].fontName == "GeoVera-Bold"
    else:
        assert web_pdf_report._BODY_FONT == "Helvetica"
        assert web_pdf_report._BOLD_FONT == "Helvetica-Bold"
        assert web_pdf_report._report_styles()["body"].fontName == "Helvetica"
        assert web_pdf_report._report_styles()["h1"].fontName == "Helvetica-Bold"


@pytest.mark.skipif(PdfReader is None, reason="pypdf not available")
def test_concurrent_reports_keep_unicode_text_and_valid_pdf_pages():
    from concurrent.futures import ThreadPoolExecutor
    import io

    def generate_and_extract(_index):
        payload = build_pdf_report(_sample_data()).getvalue()
        reader = PdfReader(io.BytesIO(payload))
        extracted = " ".join((page.extract_text() or "") for page in reader.pages)
        expected_text = "conciliación" if web_pdf_report._BODY_FONT == "GeoVera" else "Informe"
        return payload.startswith(b"%PDF"), expected_text in extracted, len(reader.pages)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(generate_and_extract, range(8)))

    assert all(is_pdf and has_unicode and 1 <= page_count <= 10 for is_pdf, has_unicode, page_count in results)


def test_missing_reportlab_fonts_fall_back_to_base14_fonts(tmp_path):
    assert web_pdf_report._register_report_fonts(str(tmp_path)) == ("Helvetica", "Helvetica-Bold")


def test_summary_story_reports_unknown_separately_from_classified_denominator():
    rows = [
        _comparison(section="S-01", sector="A"),
        _comparison(section="S-01", sector="B", bench=2, height=(15.0, 19.0, "NO CUMPLE")),
        _comparison(section="S-02", height=(15.0, None, None), angle=(60.0, None, None), berm=(8.0, None, None)),
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    story = []

    web_pdf_report._summary_section(story, data, web_pdf_report._report_styles())
    text = _flowable_text(story)

    assert "peor estado entre sus registros de banco, incluidos faltantes y adicionales" in text
    assert "Perfiles con estado clasificado: 1" in text
    assert "Perfiles UNKNOWN / SIN EVALUAR: 1" in text
    assert "quedan fuera del denominador clasificado" in text
    assert "más de una identidad de sector" in text
    assert "no se pueden atribuir a un sector de forma inequívoca" in text


def test_design_achievement_lists_component_denominators_without_assuming_all_components():
    row = _comparison(
        section="S-01", sector="A", delta_crest=0.4, delta_toe=None,
        height=(15.0, None, None), angle=(60.0, None, None), berm=(8.0, None, None),
    )
    data = build_report_data([row], SETTINGS, ReportFilters(), META)
    story = []

    web_pdf_report._summary_section(story, data, web_pdf_report._report_styles())
    text = _flowable_text(story)

    assert "cresta 100.0% (n=1)" in text
    assert "pie N/A (n=0)" in text
    assert "berma N/A (n=0)" in text
    assert "registros con algún componente disponible 1" in text
    assert "pueden tener solo uno de los componentes" in text


def test_parameter_story_shows_criteria_and_reported_count_denominators(monkeypatch):
    data = _sample_data()
    story = []
    monkeypatch.setattr(web_pdf_report, "parameter_donuts_png", lambda _parameters: None)

    web_pdf_report._parameters_section(story, data, web_pdf_report._report_styles())
    text = _flowable_text(story)

    assert "Criterio" in text
    assert "Con estado" in text
    assert "Otros estados" in text
    assert "-2.00 m / +3.00 m" in text
    assert "no equivale solo a NO CUMPLE" in text


def test_parameter_table_headers_use_white_text_and_fit_content_width(monkeypatch):
    story = []
    styles = web_pdf_report._report_styles()
    monkeypatch.setattr(web_pdf_report, "parameter_donuts_png", lambda _parameters: None)
    web_pdf_report._parameters_section(story, _sample_data(), styles)
    table = next(item for item in story if isinstance(item, web_pdf_report.Table))

    assert sum(table._argW) <= web_pdf_report.CONTENT_WIDTH
    assert all(
        header.style.textColor == web_pdf_report.colors.white
        for header in table._cellvalues[0]
    )


def test_criteria_distinguishes_height_angle_bands_from_berm_minimum():
    story = []
    web_pdf_report._criteria_section(story, _sample_data(), web_pdf_report._report_styles())
    text = _flowable_text(story)

    assert "Para altura y ángulo" in text
    assert "Para berma, se compara el ancho con el mínimo configurado" in text
    assert "esta regla no usa los tres tramos de tolerancia" in text


@requires_pdf_text
def test_expected_sections_present(sample_pdf):
    text = _text(sample_pdf)
    assert "1. Resumen ejecutivo" in text
    assert "2. Criterios" in text
    assert "3. Cumplimiento por parámetro" in text
    assert "4. Logro de diseño por sector" in text
    assert "5. Mayores desviaciones" in text
    assert "6. Plano de cumplimiento" in text


@requires_pdf_text
def test_depth_section_absent_when_depth_is_none(sample_pdf):
    data = _sample_data()
    assert data.depth is None
    assert "Profundidad del rajo" not in _text(sample_pdf)


@requires_pdf_text
def test_depth_section_present_with_depth():
    data = replace(
        _sample_data(),
        depth={"cota_piso": 3000.0, "cota_cresta": 3120.5, "profundidad": 120.5,
               "n_floors": 3, "n_crests": 4},
    )
    text = _text(build_pdf_report(data).getvalue())
    assert "Profundidad del rajo" in text
    assert "120.50 m" in text


@requires_pdf_text
def test_sector_section_omitted_without_design_achievement():
    data = replace(_sample_data(), design_achievement=None)
    text = _text(build_pdf_report(data).getvalue())
    assert "Logro de diseño por sector" not in text


@requires_pdf_text
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


@requires_pdf_text
def test_design_surface_collar_elevation_is_labeled_as_estimated():
    data = replace(
        _sample_data(),
        blast={
            "holes": [{"X": 1.0, "Y": 2.0, "Z_collar": 3100.0, "Z_collar_semantic": "design_surface_estimate"}],
            "tolerance": {"neg": 1.0, "pos": 1.0},
        },
    )
    text = _semantic_text(build_pdf_report(data).getvalue())
    assert "Advertencia sobre la cota" in text
    assert "estimada desde la superficie de diseño" in text
    assert "no es una medición de terreno" in text


@requires_pdf_text
def test_collar_estimate_warning_is_absent_without_design_surface_provenance():
    text = _semantic_text(build_pdf_report(_sample_data()).getvalue())
    assert "Advertencia sobre la cota" not in text
    assert "no es una medición de terreno" not in text


def test_pdf_blast_rows_include_estimated_collar_warning_when_provenance_is_present():
    data = replace(
        _sample_data(),
        blast={
            "holes": [{"Z_collar": 3100.0, "z_collar_semantic": "design_surface_estimate"}],
            "tolerance": {"neg": 1.0, "pos": 1.0},
        },
    )
    rows = web_pdf_report._blast_rows(data, web_pdf_report._report_styles())
    assert rows is not None
    rendered_cells = [cell.getPlainText() for row in rows for cell in row]
    assert any("estimada desde la superficie de diseño" in cell for cell in rendered_cells)
    assert any("de algunos pozos" in cell for cell in rendered_cells)


@requires_pdf_text
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


@requires_pdf_text
def test_top_deviation_headers_and_values():
    data = _sample_data()
    parameters = {entry["parameter"] for entry in data.top_deviations}
    assert parameters <= {"height", "angle", "berm"}
    text = _text(build_pdf_report(data).getvalue())
    assert "Altura de banco —" in text
    assert "Ángulo de cara —" in text
    assert "Desv. criterio (m)" in text
    assert "Desv. criterio (°)" in text
    assert "Base e índice" in text
    assert "|desvío|/límite" in text
    assert "déficit/mínimo" in text
    assert "Estado" in text
    assert "NO CUMPLE" in text


@requires_pdf_text
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


@requires_pdf_text
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


@requires_pdf_text
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
    assert "Desv. criterio (m)" in text
    assert "Base e índice" in text
    assert "Desv. criterio (°)" not in text
    assert "-3.00" in text


@requires_pdf_text
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


@requires_pdf_text
def test_criteria_shows_signed_tolerances_and_filters(sample_pdf):
    text = _text(sample_pdf)
    assert "-2.00 m / +3.00 m" in text
    assert "± 5.0 °" in text
    assert "≥ 7.00 m" in text
    assert "Sin filtros" in text
    assert "Resolución de malla" in text
    assert "0.10 m" in text
    assert "diseno.stl" in text


@requires_pdf_text
def test_plan_section_explains_when_geometry_is_unavailable():
    data = replace(_sample_data(), plan_inputs=None, section_geometry=())
    text = _text(build_pdf_report(data).getvalue())
    assert "Plano de cumplimiento" in text
    assert "No hay geometría de secciones disponible para generar el plano" in text
    assert "5. Mayores desviaciones" in text


@requires_pdf_text
def test_plan_section_accepts_section_line_objects():
    section_line = types.SimpleNamespace(
        name="S-01", origin=[100.0, 200.0], azimuth=45.0, length=80.0, sector="A"
    )
    data = replace(_sample_data(), plan_inputs={"sections": [section_line]})
    text = _text(build_pdf_report(data).getvalue())
    assert "Plano de cumplimiento" in text


def test_plan_sections_mark_filter_exclusions_without_reclassifying_unknown():
    plan_inputs = {"sections": [
        {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-02", "origin": [30.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-99", "origin": [60.0, 0.0], "azimuth": 0.0, "length": 40.0},
    ]}
    data = build_report_data(
        [_comparison(section="S-01"), _comparison(section="S-02", sector="B")],
        SETTINGS,
        ReportFilters(sections=("S-01",)),
        META,
        plan_inputs=plan_inputs,
    )

    sections, _contours = _plan_sections(data)

    assert [(section["name"], section["included"]) for section in sections] == [
        ("S-01", True), ("S-02", False), ("S-99", False),
    ]
    assert sections[1]["worst_status"] == "UNKNOWN"


def test_plan_sections_resolve_duplicate_names_by_sector_and_keep_ambiguous_unknown():
    plan_inputs = {"sections": [
        {"name": "S-01", "sector": "A", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "sector": "B", "origin": [30.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "origin": [60.0, 0.0], "azimuth": 0.0, "length": 40.0},
    ]}
    data = build_report_data(
        [
            _comparison(section="S-01", sector="A"),
            _comparison(section="S-01", sector="B", height=(15.0, 19.0, "NO CUMPLE")),
        ],
        SETTINGS,
        ReportFilters(sectors=("A",)),
        META,
        plan_inputs=plan_inputs,
    )

    sections, _contours = _plan_sections(data)

    assert [(section["sector"], section["included"], section["worst_status"]) for section in sections] == [
        ("A", True, "CUMPLE"),
        ("B", False, "UNKNOWN"),
        ("", True, "UNKNOWN"),
    ]


def test_plan_section_without_sector_stays_unknown_when_same_name_geometry_is_unmatched():
    plan_inputs = {"sections": [
        {"name": "S-01", "sector": "A", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "sector": "B", "origin": [30.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "origin": [60.0, 0.0], "azimuth": 0.0, "length": 40.0},
    ]}
    data = build_report_data(
        [_comparison(section="S-01", sector="A")],
        SETTINGS,
        ReportFilters(sectors=("A",)),
        META,
        plan_inputs=plan_inputs,
    )

    sections, _contours = _plan_sections(data)

    assert [(section["included"], section["worst_status"]) for section in sections] == [
        (True, "CUMPLE"), (False, "UNKNOWN"), (True, "UNKNOWN"),
    ]


@requires_pdf_text
def test_parameter_table_and_summary_numbers(sample_pdf):
    text = _text(sample_pdf)
    assert "Altura de banco (m)" in text
    assert "Media real (n)" in text
    assert "Perfiles" in text
    assert "Total clasificado" in text
    assert "Puntaje ponderado global" in text


@requires_pdf_text
def test_summary_denominator_excludes_unclassified_profiles():
    rows = [
        _comparison(section="S-01"),
        _comparison(section="S-02", height=(15.0, None, None), angle=(60.0, None, None), berm=(8.0, None, None)),
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    assert len(data.profiles) == 2
    assert sum(data.profile_counts.values()) == 1

    text = _text(build_pdf_report(data).getvalue())

    assert "Perfiles con estado clasificado: 1" in text
    assert "Perfiles UNKNOWN / SIN EVALUAR: 1" in text
    assert "Total de perfiles" not in text


@requires_pdf_text
def test_cover_and_criteria_identify_filters_and_sources():
    data = build_report_data(
        [_comparison(section="S-01", sector="A", bench=2)],
        SETTINGS,
        ReportFilters(sectors=("A",), sections=("S-01",), levels=("3100",), benches=(2,)),
        META,
    )
    text = _text(build_pdf_report(data).getvalue())

    assert "Filtros aplicados" in text
    assert "Sectores: A" in text
    assert "Secciones: S-01" in text
    assert "Bancos: 2" in text
    assert "Diseño: diseno.stl" in text
    assert "Topografía: topografia.stl" in text
    assert "1,5 veces la tolerancia" in text


@requires_pdf_text
def test_ambiguous_section_sector_warning_is_visible_in_the_pdf():
    rows = [
        _comparison(section="S-01", sector="A", bench=1),
        _comparison(section="S-01", sector="B", bench=2, height=(15.0, 19.0, "NO CUMPLE")),
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)

    text = _semantic_text(build_pdf_report(data).getvalue())

    assert "estos nombres aparecen asociados a más de una identidad de sector" in text
    assert "no se pueden atribuir a un sector de forma inequívoca" in text


@requires_pdf_text
def test_ambiguous_section_sector_warning_is_absent_for_unambiguous_section():
    rows = [
        _comparison(section="S-01", sector="A", bench=1),
        _comparison(section="S-01", sector="A", bench=2),
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)

    text = _semantic_text(build_pdf_report(data).getvalue())

    assert "más de una identidad de sector" not in text
    assert "no se pueden atribuir a un sector de forma inequívoca" not in text


@requires_pdf_text
def test_parameter_denominator_and_other_statuses_are_labeled_without_claiming_measurement():
    text = _text(build_pdf_report(_sample_data()).getvalue())

    assert "Otros estados" in text
    assert "Con estado" in text
    assert "incluidos FUERA DE TOLERANCIA y NO CUMPLE" in text
    assert "no equivale solo a NO CUMPLE" in text
    assert "valores reales disponibles con estado registrado" in text


@requires_pdf_text
def test_empty_data_still_builds_a_valid_pdf():
    data = build_report_data([], SETTINGS, ReportFilters(), META)
    payload = build_pdf_report(data).getvalue()
    assert payload.startswith(b"%PDF")
    text = _text(payload)
    assert "No hay comparaciones para reportar con los filtros aplicados." in text
    assert "No hay comparaciones en la sesión." in text
