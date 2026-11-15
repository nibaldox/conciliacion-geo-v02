"""Tests for the technical Word report builder (``core.web_word_report``)."""

import io
import time
from types import SimpleNamespace

import numpy as np
import pytest
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn

import core.web_word_report as web_word_report
from core.blast_correlation import PF_DEFINITIONS
from core.report_data import ReportFilters, build_report_data
from core.report_texts import OFFICIAL_VALUES_LINE, headline_text, kpi_definitions
from core.web_word_report import build_word_report

STATUS_LABELS = {
    "CUMPLE",
    "FUERA DE TOLERANCIA",
    "NO CUMPLE",
    "NO CONSTRUIDO",
    "BANCO ADICIONAL",
    "SIN EVALUAR",
}

TOLERANCES = {
    "bench_height": {"neg": 2.0, "pos": 2.0},
    "face_angle": {"neg": 5.0, "pos": 5.0},
    "berm_width": {"min": 7.0},
    "crest_toe_deviation": {"neg": 1.0, "pos": 1.0},
}

META = {
    "project": "Proyecto X",
    "operation": "Rajo",
    "phase": "Fase 1",
    "author": "Geotecnia",
    "generated_at": "2026-10-18T09:30:00",
    "design_filename": "design.stl",
    "topo_filename": "topo.stl",
    "process": {"resolution": 0.1, "face_threshold": 28.0},
}

SINGLE_SECTOR_CHAPTERS = [
    "1. Resumen",
    "2. Criterios y definiciones",
    "3. Análisis",
    "4. Perfiles",
    "Anexo A — Tabla de bancos",
    "Anexo B — Tronadura",
    "Anexo C — Excavación por sección",
    "5. Conclusiones y advertencias",
]


def _rows(n=12, sections=3, sector=""):
    rows = []
    for index in range(n):
        section = f"S-{index % sections + 1:02d}"
        status = "CUMPLE" if index % 3 else "NO CUMPLE"
        rows.append(
            {
                "section": section,
                "sector": sector,
                "level": str(3110 - 15 * (index // sections)),
                "bench_num": index // sections + 1,
                "type": "MATCH",
                "bench_score": 100.0 if status == "CUMPLE" else 40.0,
                "height_design": 15.0,
                "height_real": 15.0 + (index % 5) * 0.3,
                "height_dev": (index % 5) * 0.3,
                "angle_design": 75.0,
                "angle_real": 75.0 - (index % 4),
                "angle_dev": -(index % 4),
                "berm_design": 10.0,
                "berm_real": 9.0 + (index % 3),
                "berm_min": 7.0,
                "berm_dev": None,
                "height_status": "CUMPLE",
                "angle_status": "CUMPLE",
                "berm_status": status,
                "spill_width": 0.5,
                "effective_berm": 9.0,
                "delta_crest": 0.25,
                "delta_toe": -1.75,
            }
        )
    return rows


def _data(rows=None, **kwargs):
    settings = {"tolerances": dict(TOLERANCES)}
    return build_report_data(
        rows if rows is not None else _rows(),
        settings,
        kwargs.pop("filters", ReportFilters()),
        dict(META),
        **kwargs,
    )


def _document(data_or_blob):
    blob = data_or_blob if isinstance(data_or_blob, bytes) else build_word_report(data_or_blob).getvalue()
    return Document(io.BytesIO(blob))


def _paragraphs(doc):
    return [p.text for p in doc.paragraphs]


def _headings(doc, level=1):
    return [
        p.text
        for p in doc.paragraphs
        if p.style is not None and p.style.name == f"Heading {level}"
    ]


def _tables(doc):
    return [[cell.text for cell in row.cells] for table in doc.tables for row in table.rows]


def _table_with_header(doc, *headers):
    for table in doc.tables:
        first = [cell.text for cell in table.rows[0].cells]
        if all(header in first for header in headers):
            return [[cell.text for cell in row.cells] for row in table.rows]
    return None


def _all_text(doc):
    return "\n".join(_paragraphs(doc) + [cell for row in _tables(doc) for cell in row])


def _bench(number, crest_d, crest_z, toe_d, toe_z):
    return SimpleNamespace(
        bench_number=number,
        crest_distance=crest_d,
        crest_elevation=crest_z,
        toe_distance=toe_d,
        toe_elevation=toe_z,
        bench_height=crest_z - toe_z,
        face_angle=70.0,
        berm_width=10.0,
    )


def _geometry(names=("S-01", "S-02", "S-03"), sector=""):
    design_d = np.array([-30.0, -15.0, -10.0, 0.0, 5.0, 15.0, 20.0, 30.0])
    design_z = np.array([3140.0, 3140.0, 3125.0, 3125.0, 3110.0, 3110.0, 3095.0, 3095.0])
    topo_d = np.linspace(-30.0, 30.0, 61)
    topo_z = np.interp(topo_d, design_d, design_z) + 1.5 * np.sin(topo_d / 4.0)
    return [
        {
            "section_name": name,
            "sector": sector,
            "view_window": (-10.0, 15.0, 3102.5, 3132.5),
            "warnings": [],
            "params_design": SimpleNamespace(benches=[_bench(1, 0.0, 3125.0, 5.0, 3110.0)]),
            "params_topo": SimpleNamespace(benches=[_bench(1, 0.5, 3124.0, 5.5, 3110.5)]),
            "profile_d": (design_d, design_z),
            "profile_t": (topo_d, topo_z),
        }
        for name in names
    ]


def _plan_inputs(names=("S-01", "S-02", "S-03"), sector=""):
    return {
        "sections": [
            {
                "name": name,
                "origin": [1000.0 + 20.0 * index, 5000.0 + 2.0 * index],
                "azimuth": 20.0,
                "length": 40.0,
                "sector": sector,
            }
            for index, name in enumerate(names)
        ]
    }


def _heatmap(sector=""):
    cells = []
    for station in (1.0, 3.0, 5.0, 7.0, 9.0):
        for elevation, deviation, category in (
            (3111.5, 0.4, "within_tolerance"),
            (3113.5, 1.5, "overbreak_minor"),
            (3115.5, 2.5, "overbreak_moderate"),
            (3117.5, -1.2, "underbreak_minor"),
            (3119.5, None, "unmeasured"),
        ):
            cells.append(
                {
                    "deviation_m": deviation,
                    "value": deviation,
                    "unit": "m",
                    "category": category,
                    "status": "measured" if deviation is not None else "topo_missing",
                    "station_m": station,
                    "elevation_m": elevation,
                    "bench_num": 1,
                }
            )
    payload = {
        "cells": cells,
        "unit": "m",
        "thresholds": {"within": 1.0, "moderate": 1.8, "severe": 3.0},
        "resolution": {"longitudinal_step": 2.0, "vertical_step": 2.0},
        "section_names": ["S-01", "S-02", "S-03"],
        "section_stations_m": [0.0, 5.0, 10.0],
    }
    return {
        "sector": sector,
        "payload": payload,
        "params": {"bench_num": None, "longitudinal_step": 2.0, "vertical_step": 2.0},
        "created_at": "2026-10-17 12:00:00",
        "cache_key": "abc",
    }


def _blast_holes():
    holes = []
    for index in range(7):
        first = index < 4
        holes.append(
            {
                "id_pozo": f"P-{index + 1}",
                "Nombre_Malla_Original": "F8_3110_01" if first else "F8_3110_02",
                "Blast": "07-33" if first else "07-34",
                "fecha_tronadura": "2026-01-02" if first else "2026-01-09",
                "Nombre_Fase": "8",
                "Kilos_Cargados_real": 500.0 + index,
                "Tipo_Explosivo": "Pirex-930" if index % 2 else "Pirex-920",
                "pf_g_per_ton": 90.0 + index,
                "pf_g_per_ton_net": 95.0 + index,
                "pf_voronoi_bench_g_per_ton": None if index == 6 else 100.0 + index,
                "pf_voronoi_bench_status": "MISSING" if index == 6 else "VALID",
                "Z_collar": 3125.0,
                "Z_toe": 3109.0,
                "bench_height_m": 15.0,
            }
        )
    return holes


@pytest.fixture
def profile_spy(monkeypatch):
    calls = []

    def spy(doc, data, *, shade=None, sectors=None):
        calls.append(
            {
                "doc": doc,
                "data": data,
                "shade": shade,
                "sectors": sectors,
                "chapter": (_headings(doc) or [None])[-1],
                "last_text": doc.paragraphs[-1].text if doc.paragraphs else None,
            }
        )

    monkeypatch.setattr(web_word_report, "add_profile_pages_docx", spy)
    return calls


@pytest.fixture(scope="module")
def base_blob():
    return build_word_report(_data()).getvalue()


def test_chapter_order_single_sector(base_blob):
    headings = _headings(_document(base_blob))
    assert headings == ["Índice"] + SINGLE_SECTOR_CHAPTERS


def test_visible_index_lists_every_chapter_as_text(base_blob):
    doc = _document(base_blob)
    texts = _paragraphs(doc)
    start = texts.index("Índice")
    end = texts.index("1. Resumen", texts.index("1. Resumen", start + 1) + 1)
    listed = [text for text in texts[start + 1:end] if text.strip()]
    position = -1
    for chapter in SINGLE_SECTOR_CHAPTERS:
        assert chapter in listed, chapter
        assert listed.index(chapter) > position
        position = listed.index(chapter)
    assert any(text.strip().startswith("A.1") for text in listed)
    assert any(text.strip().startswith("A.2") for text in listed)


def test_no_toc_field_and_no_update_request(base_blob):
    doc = _document(base_blob)
    instructions = [el.text or "" for el in doc.element.body.iter(qn("w:instrText"))]
    assert not any("TOC" in text for text in instructions)
    assert doc.settings.element.find(qn("w:updateFields")) is None
    assert "se actualiza al abrir" not in "\n".join(_paragraphs(doc))


def test_base_pages_are_a4_portrait(base_blob):
    doc = _document(base_blob)
    for section in doc.sections:
        assert section.orientation in (None, WD_ORIENT.PORTRAIT)
        assert round(section.page_width.mm) == 210
        assert round(section.page_height.mm) == 297


def test_cover_has_control_block_and_scope_lines(base_blob):
    doc = _document(base_blob)
    text = _all_text(doc)
    assert "Proyecto: Proyecto X" in text
    assert "Elaborado por: Geotecnia" in text
    assert "Fecha: 18/10/2026 09:30" in text
    assert "Control de revisión y aprobación" in text
    assert "Sin filtros: todas las secciones y cotas" in text
    assert OFFICIAL_VALUES_LINE in text
    assert "design.stl" in text and "topo.stl" in text


def test_cover_scope_reports_filters():
    data = _data(_rows(sector="A"), filters=ReportFilters(sectors=("A",), levels=("3110",)))
    text = _all_text(_document(data))
    assert "Sector A: cota 3110" in text


def test_footer_keeps_page_x_of_y_fields(base_blob):
    doc = _document(base_blob)
    footer_xml = doc.sections[0].footer.paragraphs[0]._p.xml
    assert "PAGE" in footer_xml and "NUMPAGES" in footer_xml
    assert "Página " in doc.sections[0].footer.paragraphs[0].text


def test_summary_headline_and_kpi_table_with_denominators(base_blob):
    data = _data()
    doc = _document(base_blob)
    assert headline_text(data) in _paragraphs(doc)
    table = _table_with_header(doc, "Indicador", "Valor", "Base")
    assert table is not None
    by_name = {row[0]: row for row in table[1:]}
    assert by_name["Perfiles que cumplen"][1] == "2 de 3 (66,7%)"
    assert by_name["Perfiles que no cumplen"][1] == "1 de 3 (33,3%)"
    assert "3 perfiles evaluados" in by_name["Perfiles que cumplen"][2]
    assert "por geometría" in by_name["Perfiles que no cumplen"][2]
    assert by_name["Altura de banco: bancos que cumplen"][1] == "12 de 12 (100,0%)"
    assert "comparados" in by_name["Altura de banco: bancos que cumplen"][2]
    assert by_name["Puntaje ponderado (0–100)"][1] == "80,0"
    assert "12 de 12" in by_name["Logro de diseño (0–100)"][2]


def test_sector_comparison_table_only_with_two_sectors(base_blob, profile_spy):
    assert _table_with_header(_document(base_blob), "Sector", "Puntaje") is None
    rows = _rows(sector="Norte") + _rows(n=6, sector="Sur")
    doc = _document(_data(rows))
    table = _table_with_header(doc, "Sector", "Puntaje")
    assert table is not None
    assert [row[0] for row in table[1:]] == ["Norte", "Sur"]
    assert len(table[0]) <= 12


def test_sector_chapters_only_with_two_sectors(base_blob, profile_spy):
    single = _headings(_document(base_blob))
    assert "4. Perfiles" in single
    assert not any("sector" in heading.lower() for heading in single)

    rows = _rows(sector="Norte") + _rows(n=6, sector="Sur")
    headings = _headings(_document(_data(rows)))
    assert headings == [
        "Índice",
        "1. Resumen",
        "2. Criterios y definiciones",
        "3. Análisis",
        "4. Perfiles — sector Norte",
        "5. Perfiles — sector Sur",
        "Anexo A — Tabla de bancos",
        "Anexo B — Tronadura",
        "Anexo C — Excavación por sección",
        "6. Conclusiones y advertencias",
    ]


def test_profile_pages_called_once_with_data_and_shade(monkeypatch, profile_spy):
    sentinel = (np.zeros((2, 2)), (0.0, 1.0, 0.0, 1.0))
    monkeypatch.setattr(web_word_report, "_plan_backdrop", lambda data: ("surface", sentinel))
    monkeypatch.setattr(web_word_report, "dashboard_plan_png", lambda *args, **kwargs: None)
    data = _data(section_geometry=_geometry(), plan_inputs=_plan_inputs())
    build_word_report(data)
    assert len(profile_spy) == 1
    assert profile_spy[0]["data"] is data
    assert profile_spy[0]["shade"] is sentinel
    assert profile_spy[0]["sectors"] is None
    assert profile_spy[0]["chapter"] == "4. Perfiles"


def test_profile_pages_called_per_sector_right_after_each_chapter_heading(monkeypatch, profile_spy):
    sentinel = (np.zeros((2, 2)), (0.0, 1.0, 0.0, 1.0))
    monkeypatch.setattr(web_word_report, "_plan_backdrop", lambda data: ("surface", sentinel))
    monkeypatch.setattr(web_word_report, "dashboard_plan_png", lambda *args, **kwargs: None)
    rows = _rows(sector="Norte") + _rows(n=6, sector="Sur")
    data = _data(rows)
    build_word_report(data)
    assert [call["sectors"] for call in profile_spy] == [["Norte"], ["Sur"]]
    assert [call["chapter"] for call in profile_spy] == [
        "4. Perfiles — sector Norte",
        "5. Perfiles — sector Sur",
    ]
    assert all(call["data"] is data and call["shade"] is sentinel for call in profile_spy)
    assert profile_spy[1]["last_text"].startswith("Sector Sur")


def test_real_profile_pages_follow_their_own_sector_chapter():
    names_north, names_south = ("S-01", "S-02", "S-03"), ("S-11", "S-12", "S-13")
    rows = _rows(sector="Norte") + [
        dict(row, section=f"S-1{row['section'][-1]}") for row in _rows(n=6, sector="Sur")
    ]
    geometry = _geometry(names_north, sector="Norte") + _geometry(names_south, sector="Sur")
    doc = _document(_data(rows, section_geometry=geometry))
    texts = _paragraphs(doc)

    def chapter(title):
        return next(
            index
            for index, paragraph in enumerate(doc.paragraphs)
            if paragraph.text == title and paragraph.style.name == "Heading 1"
        )

    north, south = chapter("4. Perfiles — sector Norte"), chapter("5. Perfiles — sector Sur")
    annex = chapter("Anexo A — Tabla de bancos")
    pages = [index for index, text in enumerate(texts) if "página 1 de 1" in text.lower()]
    assert len(pages) == 2
    assert north < pages[0] < south < pages[1] < annex
    assert "Norte" in texts[pages[0]] and "Sur" in texts[pages[1]]
    assert round(doc.sections[-1].page_width.mm) == 210


def test_dashboard_plan_receives_backdrop_and_statuses(monkeypatch, profile_spy):
    seen = {}
    sentinel = (np.zeros((2, 2)), (0.0, 1.0, 0.0, 1.0))

    def fake_plan(sections, statuses, *, shade=None, surface=None, **kwargs):
        seen.update(sections=sections, statuses=dict(statuses), shade=shade, surface=surface)
        return None

    monkeypatch.setattr(web_word_report, "_plan_backdrop", lambda data: ("surface", sentinel))
    monkeypatch.setattr(web_word_report, "dashboard_plan_png", fake_plan)
    plan_inputs = _plan_inputs()
    build_word_report(_data(plan_inputs=plan_inputs))
    assert [s["name"] for s in seen["sections"]] == [s["name"] for s in plan_inputs["sections"]]
    assert seen["statuses"] == {"S-01": "NO_CUMPLE", "S-02": "CUMPLE", "S-03": "CUMPLE"}
    assert seen["shade"] is sentinel and seen["surface"] == "surface"


def test_plan_statuses_skip_names_repeated_across_sectors(monkeypatch, profile_spy):
    seen = {}
    monkeypatch.setattr(
        web_word_report,
        "dashboard_plan_png",
        lambda sections, statuses, **kwargs: seen.update(statuses=dict(statuses)),
    )
    rows = _rows(n=2, sections=2, sector="A") + _rows(n=1, sections=1, sector="B")
    build_word_report(_data(rows, plan_inputs=_plan_inputs(("S-01", "S-02"))))
    assert "S-01" not in seen["statuses"]
    assert "S-02" in seen["statuses"]


def test_real_profile_pages_are_landscape_and_document_returns_to_portrait():
    data = _data(section_geometry=_geometry(), plan_inputs=_plan_inputs())
    doc = _document(data)
    widths = [round(section.page_width.mm) for section in doc.sections]
    assert 297 in widths
    assert widths[0] == 210 and widths[-1] == 210
    headings = _headings(doc)
    assert headings.index("4. Perfiles") < headings.index("Anexo A — Tabla de bancos")
    body = doc.element.body
    children = list(body)
    annex = next(
        p._p
        for p in doc.paragraphs
        if p.text == "Anexo A — Tabla de bancos" and p.style.name == "Heading 1"
    )
    landscape_breaks = [
        index
        for index, child in enumerate(children)
        if child.find(".//" + qn("w:sectPr")) is not None
        and child.find(".//" + qn("w:pgSz")).get(qn("w:orient")) == "landscape"
    ]
    assert landscape_breaks and max(landscape_breaks) < children.index(annex)


def test_heatmap_chapter_and_landscape_page_only_with_heatmaps(base_blob, profile_spy):
    base = _document(base_blob)
    assert not any("Mapa de calor" in heading for heading in _headings(base))
    assert all(round(section.page_width.mm) == 210 for section in base.sections)

    data = _data(section_geometry=_geometry(), heatmaps=[_heatmap()])
    doc = _document(data)
    headings = _headings(doc)
    assert headings.index("4. Mapa de calor de desviación horizontal") == headings.index("3. Análisis") + 1
    assert "5. Perfiles" in headings
    widths = [round(section.page_width.mm) for section in doc.sections]
    assert widths.count(297) == 1
    assert widths[-1] == 210
    table = _table_with_header(doc, "Celdas", "Medidas")
    assert table is not None and len(table) == 2
    assert table[1][table[0].index("Celdas")] == "25"
    assert table[1][table[0].index("Medidas")] == "20"
    text = "\n".join(_paragraphs(doc))
    assert "la pared quedó en promedio" in text


def test_heatmap_absent_leaves_only_the_scope_note(profile_spy):
    note = "Mapa de calor no calculado; calcúlelo en la vista 3D para incluirlo."
    doc = _document(_data(heatmap_notes=[note]))
    assert not any("Mapa de calor" in heading for heading in _headings(doc))
    assert note in _all_text(doc)


def test_criteria_tolerances_definitions_levels_and_official_values(profile_spy):
    data = _data()
    object.__setattr__(data, "level_warnings", ("Sector X sin altura de banco de diseño válida.",))
    doc = _document(data)
    flat = [" | ".join(row) for row in _tables(doc)]
    assert any("Altura de banco" in row and "−2,0 / +2,0" in row for row in flat)
    assert any("Ancho de berma" in row and "mínimo 7,0" in row for row in flat)
    definitions = _table_with_header(doc, "Indicador", "Definición")
    assert definitions is not None
    assert [row[0] for row in definitions[1:]] == [name for name, _text in kpi_definitions(data)]
    levels = _table_with_header(doc, "Cota nominal", "Rango de cotas (m)")
    assert levels is not None and len(levels) == 5
    text = _all_text(doc)
    assert "Sector X sin altura de banco de diseño válida." in text
    assert "área × ancho de influencia" in text
    assert text.count(OFFICIAL_VALUES_LINE) >= 2


def _chapter_tables(doc, title):
    """Header rows of the tables between the level-1 heading ``title`` and the next one."""
    headers, inside = [], False
    for child in doc.element.body:
        if child.tag == qn("w:p"):
            style = child.find(qn("w:pPr") + "/" + qn("w:pStyle"))
            if style is not None and style.get(qn("w:val")) == "Heading1":
                inside = "".join(node.text or "" for node in child.iter(qn("w:t"))) == title
        elif child.tag == qn("w:tbl") and inside:
            first = child.find(qn("w:tr"))
            headers.append(
                ["".join(node.text or "" for node in cell.iter(qn("w:t"))) for cell in first.iter(qn("w:tc"))]
            )
    return headers


def test_analysis_keeps_excavation_bars_and_totals_without_the_section_table(profile_spy):
    data = _data(section_geometry=_geometry(), plan_inputs=_plan_inputs())
    doc = _document(data)
    assert len(doc.inline_shapes) == 5
    analysis = _chapter_tables(doc, "3. Análisis")
    assert analysis
    assert not any("Sección" in header and "Ancho de influencia (m)" in header for header in analysis)
    assert not any("Ancho de influencia (m)" in header for header in analysis)
    totals = _table_with_header(doc, "Secciones con volumen", "Volumen sobreexc. (m³)")
    assert totals is not None and len(totals) == 2
    assert totals[0] in analysis
    expected = data.excavation_totals
    with_volume = expected["n_sections"] - expected["n_without_volume"]
    assert totals[1][0] == f"{with_volume} de {expected['n_sections']}"
    assert any(
        text.startswith("Totales de las secciones del informe.") and "Anexo C" in text
        for text in _paragraphs(doc)
    )
    achievement = _table_with_header(doc, "Ámbito", "Logro")
    assert achievement is not None and achievement[1][0] == "Global"
    text = _all_text(doc)
    assert "Cobertura" in text
    assert "componentes faltantes" in text.lower()


def test_annex_c_holds_the_excavation_table_by_section(profile_spy):
    data = _data(section_geometry=_geometry(), plan_inputs=_plan_inputs())
    doc = _document(data)
    headings = _headings(doc)
    assert headings.index("Anexo B — Tronadura") < headings.index("Anexo C — Excavación por sección")
    annex = _chapter_tables(doc, "Anexo C — Excavación por sección")
    assert len(annex) == 1
    assert annex[0][0] == "Sección" and "Ancho de influencia (m)" in annex[0]
    table = _table_with_header(doc, "Sección", "Ancho de influencia (m)")
    assert [row[0] for row in table[1:]] == ["S-01", "S-02", "S-03", "Total"]
    assert len(table[0]) <= 12
    index = [p.text for p in doc.paragraphs]
    assert index.count("Anexo C — Excavación por sección") == 2


def test_annex_c_without_excavation_renders_a_note(base_blob):
    doc = _document(base_blob)
    assert _chapter_tables(doc, "Anexo C — Excavación por sección") == []
    assert "Sin geometría de secciones para estimar áreas y volúmenes." in _paragraphs(doc)


def test_annex_score_column_reads_bench_score_from_bench_row(profile_spy):
    from dataclasses import replace

    data = _data(_rows(n=3, sections=3))
    rows = list(data.rows)
    assert rows[0].bench_score == 40.0 and rows[1].bench_score == 100.0
    rows[0] = replace(rows[0], bench_score=85.4)
    rows[1] = replace(rows[1], bench_score=None)
    object.__setattr__(data, "rows", tuple(rows))
    table = _table_with_header(_document(data), "Estado del banco", "Puntaje")
    column = table[0].index("Puntaje")
    by_section = {row[0]: row[column] for row in table[1:]}
    assert by_section == {"S-01": "85", "S-02": "—", "S-03": "100"}


def test_conclusions_are_printed_as_the_model_wrote_them(profile_spy):
    data = _data()
    literal = ("Texto del modelo 1.5 sin reescritura.", "Sector con menor logro de diseño: Norte (64/100).")
    object.__setattr__(data, "conclusions", literal)
    texts = _paragraphs(_document(data))
    assert all(text in texts for text in literal)
    assert not hasattr(web_word_report, "_conclusion_lines")


def test_achievement_coverage_is_aggregated_not_one_line_per_bench(profile_spy):
    rows = _rows()
    for row in rows[:5]:
        row["delta_toe"] = None
    doc = _document(_data(rows))
    lines = [text for text in _paragraphs(doc) if "omponentes faltantes" in text]
    assert len(lines) == 1
    assert "pata en 5 bancos" in lines[0]


def test_empty_design_achievement_renders_note(profile_spy):
    data = _data()
    object.__setattr__(data, "design_achievement", None)
    assert "Sin datos suficientes de logro de diseño" in _all_text(_document(data))


def test_annex_tables_have_at_most_twelve_columns_and_nominal_level(profile_spy):
    rows = _rows(sector="Norte") + _rows(n=6, sector="Sur")
    doc = _document(_data(rows, blast={"holes": _blast_holes()}))
    for table in doc.tables:
        assert len(table.columns) <= 12, [cell.text for cell in table.rows[0].cells]
    annex = [
        [cell.text for cell in table.rows[0].cells]
        for table in doc.tables
        if "Banco" in [cell.text for cell in table.rows[0].cells]
        and len(table.rows) == 19
    ]
    assert len(annex) == 3
    for header in annex:
        assert "Cota nominal" in header
        assert header[:2] == ["Sector", "Sección"]
    assert [h for h in _headings(doc, 2) if h.startswith("A.")] == [
        "A.1 Geometría: altura y ángulo de cara",
        "A.1 Geometría: berma, cresta y pata (continuación)",
        "A.2 Estados",
    ]


def test_annex_reads_crest_toe_and_berm_min_from_bench_row(profile_spy):
    data = _data(_rows(n=2, sections=2))
    object.__setattr__(data, "plan_inputs", {"comparisons": [{"delta_crest": 99.0}]})
    table = _table_with_header(_document(data), "Δ cresta (m)", "Δ pata (m)")
    assert table is not None
    header, first = table[0], table[1]
    assert first[header.index("Δ cresta (m)")] == "+0,25"
    assert first[header.index("Δ pata (m)")] == "−1,75"
    assert first[header.index("Berma mínima (m)")] == "7,00"
    assert first[header.index("Berma efectiva (m)")] == "9,00"


def test_annex_none_values_render_dash_never_zero(profile_spy):
    rows = _rows(n=2, sections=2)
    rows[0].update(type="MISSING", height_real=None, angle_real=None, berm_real=None,
                   height_dev=None, angle_dev=None,
                   height_status=None, angle_status=None, berm_status=None,
                   delta_crest=None, delta_toe=float("nan"), bench_score=None)
    doc = _document(_data(rows))
    geometry = _table_with_header(doc, "Altura real (m)")
    row = next(r for r in geometry[1:] if r[geometry[0].index("Tipo")] == "No construido")
    assert row[geometry[0].index("Altura real (m)")] == "—"
    assert row[geometry[0].index("Δ altura (m)")] == "—"
    position = _table_with_header(doc, "Δ cresta (m)")
    row = position[1]
    assert row[position[0].index("Δ cresta (m)")] == "—"
    assert row[position[0].index("Δ pata (m)")] == "—"
    states = _table_with_header(doc, "Estado del banco", "Puntaje")
    row = next(r for r in states[1:] if r[states[0].index("Estado del banco")] == "NO CONSTRUIDO")
    assert row[states[0].index("Puntaje")] == "—"
    assert row[states[0].index("Altura")] == "—"
    assert states[2][states[0].index("Altura")] == "Cumple"
    for table in (geometry, position, states):
        for values in table[1:]:
            assert "None" not in values and "nan" not in [v.lower() for v in values]


def test_annex_columns_without_data_are_omitted_with_a_note(profile_spy):
    rows = _rows()
    for row in rows:
        row["spill_width"] = None
        row["effective_berm"] = None
    doc = _document(_data(rows))
    table = _table_with_header(doc, "Berma mínima (m)")
    assert "Derrame (m)" not in table[0]
    assert "Berma efectiva (m)" not in table[0]
    assert "Sector" not in table[0]
    note = next(p for p in _paragraphs(doc) if p.startswith("Columnas sin datos omitidas en esta tabla:"))
    assert "Derrame (m), Berma efectiva (m)" in note
    assert "Δ cresta (m)" not in note


def test_annex_marks_berm_design_below_minimum(profile_spy):
    rows = _rows(n=2, sections=2)
    rows[0]["berm_design"] = 6.0
    doc = _document(_data(rows))
    table = _table_with_header(doc, "Berma mínima (m)", "Diseño < mín.")
    column = table[0].index("Diseño < mín.")
    assert table[1][column] == "⚠"
    assert table[2][column] == "—"
    assert any("la berma de diseño es menor que el mínimo" in text for text in _paragraphs(doc))


def test_bench_status_column_uses_labels_and_light_fills(base_blob):
    doc = _document(base_blob)
    table = next(
        t for t in doc.tables if "Estado del banco" in [c.text for c in t.rows[0].cells]
    )
    header = [cell.text for cell in table.rows[0].cells]
    column = header.index("Estado del banco")
    fills = set()
    for row in table.rows[1:]:
        cell = row.cells[column]
        assert cell.text in STATUS_LABELS
        fills.update(shd.get(qn("w:fill")) for shd in cell._tc.tcPr.findall(qn("w:shd")))
    assert fills and fills <= {"C9E7CB", "FBE3BF", "F6C6C6", "E2E8F0"}
    scores = {row.cells[header.index("Puntaje")].text for row in table.rows[1:]}
    assert scores == {"100", "40"}


def test_missing_bench_status_label_is_not_numeric(profile_spy):
    rows = _rows()
    rows[0].update(type="MISSING", height_status=None, angle_status=None, berm_status=None)
    table = _table_with_header(_document(_data(rows)), "Estado del banco")
    index = table[0].index("Estado del banco")
    assert "NO CONSTRUIDO" in {row[index] for row in table[1:]}


def test_blast_none_renders_note(base_blob):
    assert "Sin datos de pozos de tronadura en esta sesión." in _all_text(_document(base_blob))


def test_blast_annex_is_aggregated_by_event_not_by_hole(profile_spy):
    doc = _document(_data(blast={"holes": _blast_holes()}))
    table = _table_with_header(doc, "Malla", "Pozos")
    assert table is not None
    header = table[0]
    assert len(table) == 3
    assert len(header) <= 12
    assert [row[header.index("Malla")] for row in table[1:]] == ["F8_3110_01", "F8_3110_02"]
    assert [row[header.index("Pozos")] for row in table[1:]] == ["4", "3"]
    assert table[1][header.index("Carga (kg)")] == "2\u202f006"
    assert "Pozos con FC" not in header
    assert "Todos los pozos de cada evento tienen FC." in _all_text(doc)
    assert table[1][header.index("FC (g/t)")] == "91,5"
    assert table[2][header.index("FC principal (g/t)")] == "104,5"
    assert "Pirex-920 (2); Pirex-930 (2)" == table[1][header.index("Explosivo")]
    text = _all_text(doc)
    assert "7 pozos en 2 mallas o eventos" in text
    hole_ids = [f"P-{index}" for index in range(1, 7)]
    assert not any(row and row[0] in hole_ids for row in _tables(doc))
    assert len([p for p in _paragraphs(doc) if p.startswith("Pozo P-")]) == 0


def test_blast_audit_block_keeps_definitions_coverage_and_ids(profile_spy):
    settings = {
        "tolerances": dict(TOLERANCES),
        "blast_holes": _blast_holes(),
        "blast_upload_meta": {
            "consolidation_report": {"holes_out": 7, "exact_copies_removed": 2, "deck_rows_merged": 1}
        },
    }
    data = build_report_data(_rows(), settings, ReportFilters(), dict(META))
    doc = _document(data)
    text = _all_text(doc)
    assert "1000*Q/(A*H*rho)" in text
    for definition in PF_DEFINITIONS.values():
        assert definition["formula"] in text
    assert "copias eliminadas 2" in text
    assert "Datos de pozos importados con una versión anterior: reimportar" in text
    assert "MISSING 1" in text and "VALID 6" in text
    line = next(p for p in _paragraphs(doc) if "sin dato de FC principal" in p)
    assert "1 de 7" in line and "P-7" in line and "P-1," not in line


def test_blast_audit_lists_capped_literal_hole_ids(profile_spy):
    holes = [{"id_pozo": f"H-{index:03d}", "X": 1.0, "Y": 2.0} for index in range(40)]
    doc = _document(_data(blast={"holes": holes}))
    line = next(p for p in _paragraphs(doc) if "sin dato de FC principal" in p)
    assert "40 de 40" in line
    assert "H-000" in line and "H-011" in line and "H-012" not in line
    assert "28 más" in line
    assert len(_table_with_header(doc, "Malla", "Pozos")) == 2


def test_blast_summary_metrics_table(profile_spy):
    blast = {"holes": _blast_holes(), "tolerance": {"neg": 1.0, "pos": 1.0}}
    flat = [" | ".join(row) for row in _tables(_document(_data(blast=blast)))]
    assert any(row.startswith("Total de pozos registrados | 7") for row in flat)
    assert any("Pasadura promedio" in row and "1,00 m" in row for row in flat)
    assert any("Tolerancia cresta-pata aplicada" in row and "−1,00 / +1,00 m" in row for row in flat)


def test_design_surface_collar_elevation_is_labeled_as_estimated(profile_spy):
    blast = {
        "holes": [{"dist": 5.0, "collar_z": 3125.0, "toe_z": 3112.0,
                   "Z_collar_semantic": "design_surface_estimate"}],
    }
    text = "\n".join(_paragraphs(_document(_data(blast=blast))))
    assert "fue estimada desde la superficie de diseño" in text
    assert "no debe interpretarse como cota real levantada" in text


def test_blast_without_bench_height_never_prints_nan(profile_spy):
    blast = {"holes": [{"dist": 5.0, "collar_z": 3125.0, "toe_z": 3112.0}]}
    flat = [" | ".join(row) for row in _tables(_document(_data(blast=blast)))]
    assert any("No disponible sin altura de banco" in row for row in flat)
    assert not any("nan" in row.lower() for row in flat)


def test_conclusions_and_deduplicated_warnings_with_counts(profile_spy):
    geometry = _geometry()
    geometry[0]["warnings"] = ["Perfil recortado sin datos de topografía."]
    geometry[1]["warnings"] = ["Perfil recortado sin datos de topografía."]
    data = _data(section_geometry=geometry)
    object.__setattr__(data, "warnings", ("Aviso único.", "Aviso único."))
    doc = _document(data)
    texts = _paragraphs(doc)
    start = texts.index("5. Conclusiones y advertencias")
    tail = texts[start:]
    assert "Puntaje ponderado global (0-100): 80,0." in tail
    assert not any(text.startswith("Sector con menor logro de diseño") for text in tail)
    repeated = [text for text in tail if text.startswith("Perfil recortado sin datos de topografía.")]
    assert len(repeated) == 1
    assert "2 secciones" in repeated[0] and "S-01" in repeated[0] and "S-02" in repeated[0]
    unique = [text for text in tail if text.startswith("Aviso único.")]
    assert len(unique) == 1 and "×2" in unique[0]


def test_no_warnings_renders_note(base_blob):
    assert "Sin advertencias para este informe." in _paragraphs(_document(base_blob))


def test_empty_dataset_degrades_to_notes(profile_spy):
    data = build_report_data([], {"tolerances": dict(TOLERANCES)}, ReportFilters(), dict(META))
    doc = _document(data)
    text = _all_text(doc)
    assert "Sin perfiles evaluados." in text
    assert "No hay bancos para tabular." in text
    assert "No hay comparaciones en la sesión." in text
    assert len(doc.inline_shapes) == 0
    assert _headings(doc) == ["Índice"] + SINGLE_SECTOR_CHAPTERS


def test_profile_pages_failure_degrades_to_a_note(monkeypatch):
    def broken(doc, data, *, shade=None, sectors=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(web_word_report, "add_profile_pages_docx", broken)
    doc = _document(_data(section_geometry=_geometry()))
    assert "No fue posible generar las páginas de perfiles." in _all_text(doc)
    assert round(doc.sections[-1].page_width.mm) == 210


def test_size_and_time_budget_for_100_rows(profile_spy):
    rows = _rows(n=100, sections=20)
    data = _data(rows)
    started = time.perf_counter()
    blob = build_word_report(data).getvalue()
    elapsed = time.perf_counter() - started
    assert len(blob) < 1_500_000, f"{len(blob)} bytes exceeds the 1.5 MB budget"
    assert elapsed < 6.0, f"{elapsed:.2f}s exceeds the 6 s budget"


def test_major_headings_keep_with_next(base_blob):
    doc = _document(base_blob)
    headings = [
        p
        for p in doc.paragraphs
        if p.style is not None and p.style.name in ("Heading 1", "Heading 2")
    ]
    assert len(headings) > 8
    for heading in headings:
        keep_next = heading._p.pPr.find(qn("w:keepNext"))
        assert keep_next is not None
        assert keep_next.get(qn("w:val")) in (None, "true", "1")


def test_numbers_use_spanish_decimal_comma_in_tables(base_blob):
    cells = [cell for row in _tables(_document(base_blob)) for cell in row]
    assert "15,00" in cells
    assert not any(cell.replace(".", "", 1).isdigit() and "." in cell for cell in cells)


def test_fitted_columns_never_break_a_header_word():
    headers = ("Sección", "Estado del banco", "Puntaje", "Explosivo cargado (kg)")
    widths = web_word_report._fit_weights(headers, (3.0, 3.0, 0.1, 0.1), 80.0, 7.5)
    assert sum(widths) == pytest.approx(80.0)
    for header, width in zip(headers, widths):
        longest = max(len(word) for word in header.split())
        assert width >= longest * 7.5 * 0.66 * 25.4 / 72.0 + 3.6 - 1e-6


def test_fitted_columns_keep_weights_when_everything_fits():
    widths = web_word_report._fit_weights(("A", "B"), (1.0, 3.0), 100.0, 9.0)
    assert widths == pytest.approx([25.0, 75.0])


def test_blast_event_table_omits_primary_pf_column_without_data(profile_spy):
    holes = _blast_holes()
    for hole in holes:
        hole["pf_voronoi_bench_g_per_ton"] = None
    doc = _document(_data(blast={"holes": holes}))
    table = _table_with_header(doc, "Malla", "Pozos")
    assert "FC principal (g/t)" not in table[0]
    assert "Columna sin datos omitida: FC principal (g/t)." in "\n".join(_paragraphs(doc))


def test_fitted_columns_fit_body_tokens_and_whole_nowrap_cells():
    headers = ("A", "B", "C")
    rows = [("2026-01-02", "F15_3120_GB_(06ENE) 01-02", "uno dos tres cuatro cinco seis")]
    widths = web_word_report._fit_weights(headers, (0.2, 0.2, 5.0), 120.0, 7.5, rows, nowrap=(0,))
    char = 7.5 * 0.56 * 25.4 / 72.0
    assert widths[0] >= 10 * char + 3.6 - 1e-6
    assert widths[1] >= 19 * char + 3.6 - 1e-6
    assert sum(widths) == pytest.approx(120.0)


def test_annex_parameter_statuses_are_short_with_legend(profile_spy):
    rows = _rows(n=2, sections=2)
    rows[0]["height_status"] = "FUERA DE TOLERANCIA"
    doc = _document(_data(rows))
    states = _table_with_header(doc, "Estado del banco", "Puntaje")
    assert states[1][states[0].index("Altura")] == "Fuera de tol."
    assert "Fuera de tol. = fuera de tolerancia." in "\n".join(_paragraphs(doc))


def test_sector_ranking_conclusion_only_with_several_sectors(profile_spy):
    rows = _rows(sector="Norte") + _rows(n=6, sector="Sur")
    texts = _paragraphs(_document(_data(rows)))
    assert any(text.startswith("Sector con menor logro de diseño: ") for text in texts)


def test_blast_event_table_keeps_holes_with_pf_when_some_lack_it(profile_spy):
    holes = _blast_holes()
    holes[0]["pf_g_per_ton"] = None
    holes[0]["pf_voronoi_bench_g_per_ton"] = None
    table = _table_with_header(_document(_data(blast={"holes": holes})), "Malla", "Pozos")
    header = table[0]
    assert table[1][header.index("Pozos")] == "4"
    assert table[1][header.index("Pozos con FC")] == "3"


def test_w43_word_heatmap_scope_and_date(profile_spy):
    entry = _heatmap()
    entry.update(scope_note="Alcance especial del mapa.", computed_at_text="14/11/2026 10:00", created_at="RAW_TIMESTAMP")
    doc = _document(_data(heatmaps=[entry]))
    text = "\n".join(_paragraphs(doc))
    assert text.count("Alcance especial del mapa.") >= 2
    assert "14/11/2026 10:00" in text
    assert "RAW_TIMESTAMP" not in text
    assert "18/10/2026 09:30" in text
    assert "Berma: Δ = real − mínima" in text


def test_disjoint_windows_in_word_table_and_figure_title(monkeypatch, profile_spy):
    from core.report_figures_heatmap import LevelWindow
    window = LevelWindow([(3111, 3114), (3117, 3120)])
    monkeypatch.setattr(web_word_report, "level_window_from_geometry", lambda _: window)
    captured = {}
    original = web_word_report.heatmap_page_png
    def capture(payload, **kwargs):
        captured.update(kwargs)
        return original(payload, **kwargs)
    monkeypatch.setattr(web_word_report, "heatmap_page_png", capture)
    data = _data(section_geometry=_geometry(), heatmaps=[_heatmap()], filters=ReportFilters(levels=("3125", "3104")))
    doc = _document(data)
    text = " ".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells).replace("\u00a0", " ")
    title = captured["title"].replace("\u00a0", " ")
    for interval in ("3 111–3 114", "3 117–3 120"):
        assert interval in text
        assert interval in title
    assert "ventanas" in title


def test_heatmap_figure_leaves_room_for_scope_and_notes(profile_spy):
    entry = _heatmap()
    entry["scope_note"] = "Mapa restringido a las secciones. El filtro de bancos no se aplica al mapa."
    doc = _document(_data(section_geometry=_geometry(), heatmaps=[entry]))
    landscape = [shape for shape in doc.inline_shapes if shape.height.mm > 70]
    assert landscape
    assert any(shape.height.mm <= 100.1 for shape in landscape)
