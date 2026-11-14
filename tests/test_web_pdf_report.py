"""Tests for the web executive PDF report built from the shared ReportData model."""

import io
import shutil
import subprocess
import types
from dataclasses import replace

import pytest

from core.report_data import ReportFilters, build_report_data
from core.report_figures_heatmap import heatmap_summary
from core.report_texts import (
    OFFICIAL_VALUES_LINE,
    headline_text,
    heatmap_position_note,
    kpi_definitions,
)
import core.web_pdf_report as web_pdf_report
from core.web_pdf_report import build_pdf_report

PDFTOTEXT = shutil.which("pdftotext")
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

requires_pdf_text = pytest.mark.skipif(
    PDFTOTEXT is None and PdfReader is None,
    reason="neither pdftotext nor pypdf is available",
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
HEATMAP_NOTE = "Mapa de calor no calculado para el sector A; calcúlelo en la vista 3D para incluirlo."


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

SECTION_NAMES = ("S-01", "S-02", "S-03")


def _plan_inputs(sectors=("A", "A", "A")):
    return {
        "sections": [
            {"name": name, "origin": [10.0 * index, 0.0], "azimuth": 0.0, "length": 120.0, "sector": sector}
            for index, (name, sector) in enumerate(zip(SECTION_NAMES, sectors))
        ]
    }


def _geometry(sectors=("A", "A", "A"), view_window=None):
    design = ([0.0, 20.0, 30.0, 60.0], [3130.0, 3130.0, 3100.0, 3100.0])
    topo = ([0.0, 22.0, 31.0, 60.0], [3130.0, 3130.0, 3101.0, 3100.0])
    bench = types.SimpleNamespace(toe_elevation=3100.0, crest_elevation=3115.0)
    return [
        {
            "section_name": name,
            "sector": sector,
            "profile_d": design,
            "profile_t": topo,
            "view_window": view_window,
            "params_design": types.SimpleNamespace(benches=[bench]),
        }
        for name, sector in zip(SECTION_NAMES, sectors)
    ]


def _rows(sectors=("A", "A", "A")):
    first, second, third = sectors
    return [
        _comparison(section="S-01", sector=first, bench=1),
        _comparison(
            section="S-01",
            sector=first,
            bench=2,
            level="3085",
            height=(15.0, 19.0, "FUERA DE TOLERANCIA"),
            angle=(60.0, 70.0, "NO CUMPLE"),
            berm=(8.0, 5.0, "NO CUMPLE"),
            delta_crest=3.6,
            delta_toe=3.1,
        ),
        _comparison(section="S-02", sector=second, bench=1, row_type="MISSING",
                    height=(15.0, None, None), angle=(60.0, None, None),
                    berm=(8.0, None, None), delta_crest=None, delta_toe=None),
        _comparison(section="S-02", sector=second, bench=2, level="3085"),
        _comparison(section="S-03", sector=third, bench=1),
        _comparison(section="S-03", sector=third, bench=2, level="3085"),
    ]


def _cell(station, elevation, deviation, category):
    return {
        "deviation_m": deviation,
        "value": deviation,
        "unit": "m",
        "category": category,
        "status": "measured" if deviation is not None else "topo_missing",
        "station_m": station,
        "elevation_m": elevation,
        "bench_num": 1,
    }


def _heatmap_payload(shift=0.0):
    cells = [
        _cell(1.0, 3100.5, 0.5 + shift, "within_tolerance"),
        _cell(1.0, 3101.5, -0.4 + shift, "within_tolerance"),
        _cell(3.0, 3100.5, 1.5 + shift, "overbreak_minor"),
        _cell(3.0, 3101.5, 2.5 + shift, "overbreak_moderate"),
        _cell(11.0, 3100.5, 4.0 + shift, "overbreak_severe"),
        _cell(11.0, 3101.5, None, "unmeasured"),
        _cell(15.0, 3110.5, -1.2 + shift, "underbreak_minor"),
        _cell(17.0, 3110.5, 3.4 + shift, "overbreak_severe"),
    ]
    return {
        "cells": cells,
        "unit": "m",
        "thresholds": {"within": 1.0, "moderate": 1.8, "severe": 3.0},
        "resolution": {"longitudinal_step": 2.0, "vertical_step": 1.0},
        "section_names": list(SECTION_NAMES),
        "section_stations_m": [0.0, 10.0, 20.0],
    }


def _heatmap(sector="A", shift=0.0):
    return {
        "sector": sector,
        "payload": _heatmap_payload(shift),
        "params": {"bench_num": None, "longitudinal_step": 2.0, "vertical_step": 1.0},
        "created_at": "2026-11-13 10:00:00",
        "cache_key": f"key-{sector}",
    }


def _sample_data(sectors=("A", "A", "A"), heatmaps=None, heatmap_notes=(HEATMAP_NOTE,), **kwargs):
    return build_report_data(
        _rows(sectors),
        kwargs.pop("settings", SETTINGS),
        kwargs.pop("filters", ReportFilters()),
        META,
        section_geometry=_geometry(sectors, kwargs.pop("view_window", None)),
        plan_inputs=_plan_inputs(sectors),
        heatmaps=heatmaps,
        heatmap_notes=None if heatmaps else heatmap_notes,
        **kwargs,
    )


def _two_sector_data(**kwargs):
    return _sample_data(sectors=("A", "B", "B"), **kwargs)


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
        return "\f".join(
            " ".join((page.extract_text() or "").split())
            for page in PdfReader(io.BytesIO(pdf_bytes)).pages
        )
    raise RuntimeError("neither pdftotext nor pypdf is available")


def _norm(text):
    return " ".join(str(text).replace("\u202f", " ").split())


def _semantic_text(pdf_bytes):
    """Reading-order text with whitespace collapsed; for wording checks, not layout checks."""
    if PDFTOTEXT:
        proc = subprocess.run(
            [PDFTOTEXT, "-", "-"],
            input=pdf_bytes,
            capture_output=True,
            check=True,
        )
        return _norm(proc.stdout.decode("utf-8", errors="replace"))
    return _norm(_text(pdf_bytes))


def _pages(pdf_bytes):
    return [_norm(page) for page in _text(pdf_bytes, layout=False).split("\f") if page.strip()]


def _flowable_text(flowable):
    if hasattr(flowable, "getPlainText"):
        return flowable.getPlainText()
    cells = getattr(flowable, "_cellvalues", None)
    if cells is not None:
        return " ".join(_flowable_text(cell) for cell in cells)
    content = getattr(flowable, "_content", None)
    if content is not None:
        return " ".join(_flowable_text(item) for item in content)
    if isinstance(flowable, (list, tuple)):
        return " ".join(_flowable_text(item) for item in flowable)
    return str(flowable)


@pytest.fixture(scope="module")
def sample_pdf():
    return build_pdf_report(_sample_data()).getvalue()


@pytest.fixture(scope="module")
def heatmap_pdf():
    return build_pdf_report(_sample_data(heatmaps=[_heatmap()])).getvalue()


@pytest.fixture(scope="module")
def two_sector_pdf():
    return build_pdf_report(_two_sector_data()).getvalue()


def _tall_png():
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (800, 2000), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_tall_image_fits_web_content_frame():
    image = web_pdf_report._image(_tall_png(), web_pdf_report.CONTENT_WIDTH)
    assert image.drawWidth <= web_pdf_report.CONTENT_WIDTH
    assert image.drawHeight <= web_pdf_report.CONTENT_HEIGHT
    assert image.drawWidth / image.drawHeight == pytest.approx(800 / 2000)


def test_image_respects_explicit_height_budget():
    image = web_pdf_report._image(_tall_png(), web_pdf_report.CONTENT_WIDTH, max_height=100.0)
    assert image.drawHeight == pytest.approx(100.0)
    assert image.drawWidth == pytest.approx(40.0)


@requires_pdf_text
def test_build_report_with_tall_plan_keeps_page_count(monkeypatch, sample_pdf):
    monkeypatch.setattr(web_pdf_report, "dashboard_plan_png", lambda *args, **kwargs: _tall_png())
    payload = build_pdf_report(_sample_data()).getvalue()
    assert payload.startswith(b"%PDF")
    assert len(_pages(payload)) == len(_pages(sample_pdf))


@pytest.mark.parametrize("section", ["pie", "plan"])
def test_legacy_report_tall_images_fit_content_frame(monkeypatch, section):
    from core import pdf_report
    from core import report_generator
    from reportlab.platypus import Frame

    if section == "pie":
        monkeypatch.setattr(pdf_report, "_pie_chart_image_bytes", lambda comparisons: io.BytesIO(_tall_png()))
    else:
        monkeypatch.setattr(report_generator, "create_plan_view_image", lambda *args, **kwargs: io.BytesIO(_tall_png()))
    frame = Frame(0, 0, pdf_report.A4[0] - 2 * pdf_report.PAGE_MARGIN,
                  pdf_report.A4[1] - 2 * pdf_report.PAGE_MARGIN)
    story = []
    styles = pdf_report._build_styles()
    if section == "pie":
        pdf_report._build_pie_section(story, [], styles)
    else:
        pdf_report._build_plan_section(story, [], [], styles)
    image = next(item for item in story if isinstance(item, pdf_report.Image))
    assert image.drawHeight <= frame._aH
    assert image.drawWidth <= frame._aW
    assert image.drawWidth / image.drawHeight == pytest.approx(800 / 2000)


def test_returns_seekable_pdf_buffer(sample_pdf):
    buffer = build_pdf_report(_sample_data())
    assert buffer.seekable()
    payload = buffer.getvalue()
    assert payload.startswith(b"%PDF")
    assert payload.rstrip().endswith(b"%%EOF")


@pytest.mark.skipif(PdfReader is None, reason="pypdf not available")
def test_embedded_font_roundtrips_accents_and_keeps_a4_portrait_pages(sample_pdf):
    reader = PdfReader(io.BytesIO(sample_pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert "Informe" in text
    assert 4 <= len(reader.pages) <= 6
    assert all(
        float(page.mediabox.width) == pytest.approx(595.28, abs=0.1)
        and float(page.mediabox.height) == pytest.approx(841.89, abs=0.1)
        for page in reader.pages
    )
    if web_pdf_report._BODY_FONT == "GeoVera":
        assert "conciliación geotécnica" in text
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

    data = _sample_data()

    def generate_and_extract(_index):
        payload = build_pdf_report(data).getvalue()
        reader = PdfReader(io.BytesIO(payload))
        extracted = " ".join((page.extract_text() or "") for page in reader.pages)
        expected_text = "conciliación" if web_pdf_report._BODY_FONT == "GeoVera" else "Informe"
        return payload.startswith(b"%PDF"), expected_text in extracted, len(reader.pages)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(generate_and_extract, range(6)))

    assert all(is_pdf and has_unicode and page_count == 4 for is_pdf, has_unicode, page_count in results)


def test_missing_reportlab_fonts_fall_back_to_base14_fonts(tmp_path):
    assert web_pdf_report._register_report_fonts(str(tmp_path)) == ("Helvetica", "Helvetica-Bold")


def test_text_helper_replaces_glyphs_missing_from_the_report_font():
    escaped = web_pdf_report._esc("1\u202f234 m <b> ⅓")
    assert "\u202f" not in escaped
    assert "⅓" not in escaped
    assert "1/3" in escaped
    assert "&lt;b&gt;" in escaped
    assert _norm(escaped).startswith("1 234 m")
    assert web_pdf_report._esc(None) == "—"


@requires_pdf_text
def test_one_sector_without_heatmap_has_four_to_six_pages(sample_pdf):
    assert 4 <= len(_pages(sample_pdf)) <= 6


@requires_pdf_text
def test_each_heatmap_adds_one_page(sample_pdf, heatmap_pdf):
    base = len(_pages(sample_pdf))
    assert len(_pages(heatmap_pdf)) == base + 1

    two = build_pdf_report(
        _two_sector_data(heatmaps=[_heatmap("A"), _heatmap("B", shift=1.0)])
    ).getvalue()
    assert len(_pages(two)) == base + 1 + 2


@requires_pdf_text
def test_sector_comparison_page_only_with_two_or_more_sectors(sample_pdf, two_sector_pdf):
    assert "Comparación entre sectores" not in _semantic_text(sample_pdf)
    assert len(_pages(two_sector_pdf)) == len(_pages(sample_pdf)) + 1

    page = next(page for page in _pages(two_sector_pdf) if "Comparación entre sectores" in page)
    assert "Sector A" in page
    assert "Sector B" in page
    assert "Puntaje ponderado" in page
    assert "Altura" in page and "Ángulo" in page and "Berma" in page
    assert "Logro de diseño" in page
    assert "Volumen de sobreexcavación" in page
    assert "Cotas seleccionadas" in page


def test_sector_comparison_uses_dash_for_sector_without_compared_benches():
    rows = [
        _comparison(section="S-01", sector="A", bench=1),
        _comparison(section="S-02", sector="B", bench=1, row_type="MISSING",
                    height=(15.0, None, None), angle=(60.0, None, None),
                    berm=(8.0, None, None), delta_crest=None, delta_toe=None),
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    story = web_pdf_report._sector_page(data, web_pdf_report._report_styles())
    text = _norm(_flowable_text(story))

    assert "100,0% (n = 1)" in text
    assert "— (n = 0)" in text
    assert "0,0% (n = 0)" not in text


@requires_pdf_text
def test_heatmap_page_only_when_heatmaps_present_and_scope_note_otherwise(sample_pdf, heatmap_pdf):
    without = _semantic_text(sample_pdf)
    assert "Mapa de calor de desviación horizontal" not in without
    assert _norm(HEATMAP_NOTE) in _pages(sample_pdf)[0]

    with_heatmap = _semantic_text(heatmap_pdf)
    assert "Mapa de calor de desviación horizontal" in with_heatmap
    assert "no calculado" not in with_heatmap


@requires_pdf_text
def test_dashboard_has_headline_scope_and_kpi_denominators(sample_pdf):
    data = _sample_data()
    first = _pages(sample_pdf)[0]

    assert _norm(headline_text(data)) in first
    assert _norm(OFFICIAL_VALUES_LINE) in first
    assert "Sin filtros" in first
    assert "Rajo Prueba" in first
    assert "diseno.stl" in first and "topografia.stl" in first
    assert "Perfiles por estado" in first
    assert "Puntaje ponderado" in first
    assert "Logro de diseño" in first
    for parameter in data.parameters:
        assert f"n = {parameter.n_evaluated}" in first
    assert f"n = {len(data.profiles)}" in first
    assert "Vista en planta" in first
    assert "Matriz sección × cota" in first


@requires_pdf_text
def test_kpi_values_use_spanish_number_format(sample_pdf):
    data = _sample_data()
    first = _pages(sample_pdf)[0]
    score = f"{data.global_weighted_score:.1f}".replace(".", ",")
    assert score in first
    height = next(p for p in data.parameters if p.parameter == "height")
    assert f"{height.pct_cumple:.1f}".replace(".", ",") + "%" in first


@requires_pdf_text
def test_analysis_pages_have_figures_top_table_and_excavation_method(sample_pdf):
    text = _semantic_text(sample_pdf)
    assert "Distribución de desviaciones" in text
    assert "Tendencia a lo largo del talud" in text
    assert "Mayores desviaciones" in text
    assert "Sobreexcavación y subexcavación por sección" in text
    assert "volumen = área × ancho de influencia; ancho = separación real entre secciones" in text
    assert "Estimación, no cubicación" in text
    data = _sample_data()
    total = data.excavation_totals["volume_over_m3"]
    assert total is not None
    assert _norm(web_pdf_report.fmt_es(total, 0, "m³")) in text


def test_top_deviation_table_is_limited_to_ten_rows_with_nominal_level():
    rows = [
        _comparison(
            section=f"S-{index:02d}",
            bench=1,
            height=(15.0, 15.0 + index, "FUERA DE TOLERANCIA"),
            angle=(60.0, None, None),
            berm=(8.0, None, None),
        )
        for index in range(1, 15)
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    assert len(data.top_deviations) == 14
    table = web_pdf_report._top_deviations_table(data, web_pdf_report._report_styles())

    assert len(table._cellvalues) == 11
    text = _norm(_flowable_text(table))
    assert "S-14" in text and "S-05" in text
    assert "S-04" not in text
    assert "3100" in text
    assert "+14,00" in text
    assert sum(table._argW) <= web_pdf_report.CONTENT_WIDTH + 0.01
    assert all(
        header.style.textColor == web_pdf_report.colors.white
        for header in table._cellvalues[0]
    )


@requires_pdf_text
def test_heatmap_page_shows_summary_and_position_note(heatmap_pdf):
    data = _sample_data(heatmaps=[_heatmap()])
    summary = heatmap_summary(_heatmap_payload())
    note = heatmap_position_note(summary)
    assert note

    page = next(
        page for page in _pages(heatmap_pdf) if "Mapa de calor de desviación horizontal" in page
    )
    assert "Sector A" in page
    assert _norm(note) in page
    assert "Celdas medidas" in page
    assert f"{summary.n_measured} de {summary.n_cells}" in page
    assert "Dentro de ±1 m" in page
    assert "Mediana" in page
    assert "P95" in page
    assert "Máxima sobreexcavación" in page
    assert "Máxima subexcavación" in page
    assert _norm(summary.max_over["location"]) in page
    assert "Forma del banco" in page
    assert _norm(headline_text(data)) in page

    assert _norm(note) in _pages(heatmap_pdf)[0]


def test_level_table_counts_official_statuses_per_nominal_level():
    data = _sample_data()
    blocks = web_pdf_report._level_table(data, web_pdf_report._report_styles())
    rows = [
        [_flowable_text(cell) for cell in row] for row in blocks[0]._cellvalues
    ]
    assert rows[0][:4] == ["Cota nominal", "Bancos", "Cumple", "No cumple"]
    by_level = {row[0]: row for row in rows[1:]}
    assert by_level["3100"][1:7] == ["3", "2", "0", "0", "1", "0"]
    assert by_level["3085"][1:7] == ["3", "2", "1", "0", "0", "0"]
    assert list(by_level) == ["3100", "3085"]


def test_heatmap_figure_receives_level_window_and_title(monkeypatch):
    captured = {}

    def fake_heatmap(payload, **kwargs):
        captured["payload"] = payload
        captured.update(kwargs)
        return _tall_png()

    monkeypatch.setattr(web_pdf_report, "heatmap_page_png", fake_heatmap)
    data = _sample_data(
        heatmaps=[_heatmap()],
        filters=ReportFilters(levels=("3100",)),
        view_window=(10.0, 40.0, 3092.5, 3122.5),
    )
    build_pdf_report(data)

    assert captured["payload"] == _heatmap_payload()
    assert captured["level_window"] == (3100.0, 3115.0)
    assert "A" in captured["title"]
    assert "3100" in captured["title"]
    assert captured["width_in"] <= web_pdf_report.CONTENT_WIDTH / 72.0 + 1e-6


def test_heatmap_without_level_filter_has_no_level_window(monkeypatch):
    captured = {}

    def fake_heatmap(payload, **kwargs):
        captured.update(kwargs)
        return _tall_png()

    monkeypatch.setattr(web_pdf_report, "heatmap_page_png", fake_heatmap)
    build_pdf_report(_sample_data(heatmaps=[_heatmap()]))
    assert captured["level_window"] is None


def test_dashboard_plan_uses_backdrop_recipe_and_worst_status(monkeypatch):
    calls = {}
    mesh = object()

    def fake_surface(mesh_arg, *, bounds=None, **_kwargs):
        calls["mesh"] = mesh_arg
        calls["bounds"] = bounds
        return "SURFACE"

    def fake_plan(sections, statuses, **kwargs):
        calls["sections"] = [section["name"] for section in sections]
        calls["statuses"] = dict(statuses)
        calls.update(kwargs)
        return _tall_png()

    monkeypatch.setattr(web_pdf_report, "plan_surface_from_mesh", fake_surface)
    monkeypatch.setattr(web_pdf_report, "shaded_relief", lambda surface: ("SHADE", surface))
    monkeypatch.setattr(web_pdf_report, "dashboard_plan_png", fake_plan)
    data = _sample_data()
    data = replace(data, plan_inputs={**data.plan_inputs, "mesh_topo": mesh})
    build_pdf_report(data)

    assert calls["mesh"] is mesh
    assert calls["bounds"] == web_pdf_report.sections_bounds(data.plan_inputs["sections"])
    assert calls["surface"] == "SURFACE"
    assert calls["shade"] == ("SHADE", "SURFACE")
    assert calls["sections"] == list(SECTION_NAMES)
    assert calls["statuses"] == {
        profile.section: profile.worst_status for profile in data.profiles
    }


def test_dashboard_plan_drops_backdrop_when_surface_fails(monkeypatch):
    calls = {}

    def failing_surface(*_args, **_kwargs):
        raise MemoryError("grid too large")

    def fake_plan(sections, statuses, **kwargs):
        calls.update(kwargs)
        return _tall_png()

    monkeypatch.setattr(web_pdf_report, "plan_surface_from_mesh", failing_surface)
    monkeypatch.setattr(web_pdf_report, "dashboard_plan_png", fake_plan)
    data = _sample_data()
    data = replace(data, plan_inputs={**data.plan_inputs, "mesh_topo": object()})
    assert build_pdf_report(data).getvalue().startswith(b"%PDF")
    assert calls["surface"] is None
    assert calls["shade"] is None


@requires_pdf_text
def test_page_chrome_on_every_page(sample_pdf):
    pages = _pages(sample_pdf)
    total = len(pages)
    for index, page in enumerate(pages, start=1):
        assert f"Página {index} de {total}" in page
        assert META["project"] in page
        assert "Informe de conciliación geotécnica" in page


@requires_pdf_text
def test_conclusions_page_has_conclusions_criteria_and_every_definition(sample_pdf):
    data = _sample_data()
    last = _pages(sample_pdf)[-1]
    assert "Conclusiones y advertencias" in last
    for conclusion in data.conclusions:
        assert _norm(conclusion).replace(".", ",").rstrip(",") in last
    assert "Definiciones" in last
    for name, definition in kpi_definitions(data):
        assert _norm(name) in last
        assert _norm(definition).replace("⅓", "1/3") in last.replace("⅓", "1/3")
    assert "Tolerancias" in last
    assert "−2,00 m / +3,00 m" in last
    assert "± 5,0°" in last
    assert "≥ 7,00 m" in last


def test_warnings_are_deduplicated_and_counted():
    data = replace(
        _sample_data(),
        warnings=("Aviso repetido.", "Aviso repetido.", "Aviso único.", "Aviso repetido."),
    )
    lines = web_pdf_report._aggregated_warnings(data)

    assert lines.count("Aviso repetido. (×3)") == 1
    assert "Aviso único." in lines
    assert not any(line == "Aviso repetido." for line in lines)


def test_aggregated_warnings_count_incomplete_components_instead_of_listing_rows():
    rows = [
        _comparison(section=f"S-{index:02d}", delta_toe=None, berm=(8.0, None, None))
        for index in range(1, 9)
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    lines = web_pdf_report._aggregated_warnings(data)
    text = " ".join(lines)

    assert "8 de 8 bancos" in text
    assert text.startswith("Componentes faltantes")
    assert "Cobertura" in text
    assert "S-03" not in text
    assert len(lines) <= 3


def test_aggregated_warnings_count_berms_designed_below_minimum():
    rows = [
        _comparison(section=f"S-{index:02d}", berm=(2.0, 2.1, "NO CUMPLE"))
        for index in range(1, 4)
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    text = " ".join(web_pdf_report._aggregated_warnings(data))
    assert "3 bermas" in text
    assert "diseño bajo el mínimo" in text


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
def test_ambiguous_section_sector_warning_is_absent_for_unambiguous_section(sample_pdf):
    text = _semantic_text(sample_pdf)

    assert "más de una identidad de sector" not in text
    assert "no se pueden atribuir a un sector de forma inequívoca" not in text


def _blast(n_holes=40, **overrides):
    holes = [
        {
            "id_pozo": f"POZO-{index:03d}",
            "X": float(index),
            "Y": 2.0,
            "Z_collar": 3100.0 + index,
            "Burden": 3.5,
            "Esp": 4.0,
            "pf_voronoi_bench_g_per_ton": None if index % 2 else 250.0,
            "pf_voronoi_bench_status": "MISSING_FOOTPRINT" if index % 2 else "OK",
        }
        for index in range(n_holes)
    ]
    blast = {"holes": holes, "tolerance": {"neg": 1.0, "pos": 1.0}}
    blast.update(overrides)
    return blast


@requires_pdf_text
def test_blast_summary_only_with_blast_and_never_one_line_per_hole(sample_pdf):
    assert "Resumen de tronadura" not in _semantic_text(sample_pdf)

    data = replace(_sample_data(), blast=_blast())
    payload = build_pdf_report(data).getvalue()
    text = _semantic_text(payload)

    assert "Resumen de tronadura" in text
    assert "Pozos registrados" in text
    assert "3,50 m" in text
    assert "20 de 40" in text
    assert "MISSING_FOOTPRINT 20" in text
    assert "OK 20" in text
    assert text.count("POZO-") == web_pdf_report.MAX_LISTED_HOLES
    assert "y 8 más" in text
    assert "1000*Q/(A*H*rho)" in text
    from core.blast_correlation import PF_DEFINITIONS

    for definition in PF_DEFINITIONS.values():
        assert definition["formula"] in text
    assert len(_pages(payload)) == len(_pages(sample_pdf))


def test_blast_summary_table_has_at_most_five_rows():
    data = replace(_sample_data(), blast=_blast())
    rows = web_pdf_report._blast_rows(data)
    assert rows is not None
    assert 1 <= len(rows) <= 5
    assert rows[0] == ("Pozos registrados", "40")


def test_blast_rows_absent_without_holes():
    assert web_pdf_report._blast_rows(_sample_data()) is None
    assert web_pdf_report._blast_rows(replace(_sample_data(), blast={"holes": []})) is None


@requires_pdf_text
def test_design_surface_collar_elevation_is_reported_as_one_aggregated_warning():
    holes = [
        {"X": 1.0, "Y": 2.0, "Z_collar": 3100.0, "Z_collar_semantic": "design_surface_estimate"},
        {"X": 2.0, "Y": 2.0, "Z_collar": 3101.0, "z_collar_semantic": "design_surface_estimate"},
        {"X": 3.0, "Y": 2.0, "Z_collar": 3102.0},
    ]
    data = replace(_sample_data(), blast={"holes": holes, "tolerance": {"neg": 1.0, "pos": 1.0}})
    lines = web_pdf_report._aggregated_warnings(data)
    matching = [line for line in lines if "estimada desde la superficie de diseño" in line]
    assert len(matching) == 1
    assert "2 de 3 pozos" in matching[0]

    text = _semantic_text(build_pdf_report(data).getvalue())
    assert "estimada desde la superficie de diseño" in text
    assert "no es una medición de terreno" in text


@requires_pdf_text
def test_collar_estimate_warning_is_absent_without_design_surface_provenance(sample_pdf):
    text = _semantic_text(sample_pdf)
    assert "estimada desde la superficie de diseño" not in text
    assert "no es una medición de terreno" not in text


def test_legacy_blast_import_is_one_aggregated_warning_listing_capped_ids():
    data = replace(_sample_data(), blast=_blast(data_status="legacy_reimport_required"))
    lines = web_pdf_report._aggregated_warnings(data)
    matching = [line for line in lines if "reimportar" in line]
    assert len(matching) == 1
    assert matching[0].startswith(
        "Datos de pozos importados con una versión anterior: reimportar (40 pozos: POZO-000,"
    )
    assert matching[0].count("POZO-") == web_pdf_report.MAX_LISTED_HOLES
    assert "y 28 más" in matching[0]


def test_blast_audit_block_keeps_consolidation_statuses_and_missing_data_text():
    blast = {
        "holes": [{"hole_id": "H-1", "Z_collar": 3870.0, "pf_voronoi_bench_g_per_ton": None,
                   "pf_voronoi_bench_status": "MISSING"}],
        "consolidation_report": {"holes_out": 1, "exact_copies_removed": 2, "deck_rows_merged": 0},
    }
    data = replace(_sample_data(), blast=blast)
    rows = web_pdf_report._blast_rows(data)
    assert rows[-1][1].startswith("sin dato")
    text = " ".join(web_pdf_report._blast_audit_lines(data))
    assert "copias eliminadas 2" in text
    assert "MISSING 1" in text
    assert "H-1" in text
    assert "1000*Q/(A*H*rho)" in text


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
def test_missing_values_render_dash_and_never_none_or_zero():
    rows = [
        _comparison(section="S-01", bench=1, row_type="MISSING",
                    height=(15.0, None, None), angle=(60.0, None, None),
                    berm=(8.0, None, None), delta_crest=None, delta_toe=None),
    ]
    data = build_report_data(rows, SETTINGS, ReportFilters(), META)
    assert data.global_weighted_score is None
    payload = build_pdf_report(data).getvalue()
    text = _semantic_text(payload)

    assert "None" not in text
    assert "nan" not in text.lower().replace("financ", "")
    first = _pages(payload)[0]
    assert "— / 100" in first
    assert "— (n = 0)" in first
    assert "0,0%" not in first


def test_plan_section_accepts_section_line_objects():
    section_line = types.SimpleNamespace(
        name="S-01", origin=[100.0, 200.0], azimuth=45.0, length=80.0, sector="A"
    )
    data = replace(_sample_data(), plan_inputs={"sections": [section_line]})
    sections = web_pdf_report._plan_sections(data)
    assert [section["name"] for section in sections] == ["S-01"]
    assert web_pdf_report._render_plan(data).startswith(PNG_SIGNATURE)


@requires_pdf_text
def test_plan_block_explains_when_geometry_is_unavailable():
    data = replace(_sample_data(), plan_inputs=None, section_geometry=())
    payload = build_pdf_report(data).getvalue()
    text = _semantic_text(payload)
    assert "No hay geometría de secciones disponible para generar el plano" in text
    assert "Matriz sección × cota" in text


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

    sections = web_pdf_report._plan_sections(data)

    assert [(section["name"], section["included"]) for section in sections] == [
        ("S-01", True), ("S-02", False), ("S-99", False),
    ]
    assert sections[1]["worst_status"] == "UNKNOWN"
    assert web_pdf_report._plan_statuses(sections) == {"S-01": "CUMPLE"}


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

    sections = web_pdf_report._plan_sections(data)

    assert [(section["sector"], section["included"], section["worst_status"]) for section in sections] == [
        ("A", True, "CUMPLE"),
        ("B", False, "UNKNOWN"),
        ("", True, "UNKNOWN"),
    ]
    assert web_pdf_report._plan_statuses(sections) == {}


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

    sections = web_pdf_report._plan_sections(data)

    assert [(section["included"], section["worst_status"]) for section in sections] == [
        (True, "CUMPLE"), (False, "UNKNOWN"), (True, "UNKNOWN"),
    ]


@requires_pdf_text
def test_scope_lists_filters_per_sector():
    data = build_report_data(
        [_comparison(section="S-01", sector="A", bench=2)],
        SETTINGS,
        ReportFilters(sectors=("A",), sections=("S-01",), levels=("3100",), benches=(2,)),
        META,
    )
    first = _pages(build_pdf_report(data).getvalue())[0]

    assert "Alcance" in first
    assert "Sector A: cota 3100" in first
    assert "Sección: S-01" in first
    assert "Banco: 2" in first


@requires_pdf_text
def test_depth_is_one_conclusion_line_only_when_available(sample_pdf):
    assert _sample_data().depth is None
    assert "Profundidad del rajo" not in _semantic_text(sample_pdf)

    data = replace(
        _sample_data(),
        depth={"cota_piso": 3000.0, "cota_cresta": 3120.5, "profundidad": 120.5,
               "n_floors": 3, "n_crests": 4},
    )
    text = _semantic_text(build_pdf_report(data).getvalue())
    assert "Profundidad del rajo: 120,50 m" in text


@requires_pdf_text
def test_empty_data_still_builds_a_valid_pdf():
    data = build_report_data([], SETTINGS, ReportFilters(), META)
    payload = build_pdf_report(data).getvalue()
    assert payload.startswith(b"%PDF")
    text = _semantic_text(payload)
    assert "No hay comparaciones para reportar con los filtros aplicados." in text
    assert "No hay comparaciones en la sesión." in text
    assert "Sin perfiles evaluados." in text
    assert 1 <= len(_pages(payload)) <= 3


@requires_pdf_text
def test_w43_pdf_heatmap_scope_and_local_date():
    entry = _heatmap()
    entry.update(scope_note="Alcance especial del mapa.", computed_at_text="14/11/2026 10:00", created_at="RAW_TIMESTAMP")
    text = _text(build_pdf_report(_sample_data(heatmaps=[entry])).getvalue())
    assert text.count("Alcance especial del mapa.") >= 2
    assert "14/11/2026 10:00" in text
    assert "RAW_TIMESTAMP" not in text


def test_disjoint_windows_in_pdf_table_and_figure_title(monkeypatch):
    from core.report_figures_heatmap import LevelWindow
    window = LevelWindow([(3100, 3102), (3110, 3112)])
    monkeypatch.setattr(web_pdf_report, "level_window_from_geometry", lambda _: window)
    captured = {}
    original = web_pdf_report.heatmap_page_png
    def capture(payload, **kwargs):
        captured.update(kwargs)
        return original(payload, **kwargs)
    monkeypatch.setattr(web_pdf_report, "heatmap_page_png", capture)
    data = _sample_data(heatmaps=[_heatmap()], filters=ReportFilters(levels=("3100", "3085")))
    text = _text(build_pdf_report(data).getvalue()).replace("\u00a0", " ")
    assert "3 100–3 102" in text and "3 110–3 112" in text
    assert "ventanas" in captured["title"]
    assert "3 100–3 102" in captured["title"].replace("\u00a0", " ")
    assert "3 110–3 112" in captured["title"].replace("\u00a0", " ")
