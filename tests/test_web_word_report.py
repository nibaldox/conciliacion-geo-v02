"""Tests for the web Word report builder (``core.web_word_report``)."""

import io
import time

import numpy as np
import pandas as pd
import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Mm

from core.report_data import ReportFilters, build_report_data
from core.calculo_tronadura import procesar_pozos, proyectar_pozos_en_seccion
from core.web_word_report import (
    DETAIL_COLUMN_MM,
    _plan_sections,
    _profile_payload,
    _project_holes,
    build_word_report,
)

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
    "generated_at": "18/10/2026",
    "design_file": "design.stl",
    "topo_file": "topo.stl",
    "process": {"resolution": 0.1, "face_threshold": 28.0},
}


def _rows(n=12, sections=3, sector=""):
    rows = []
    for index in range(n):
        section = f"S-{index % sections + 1:02d}"
        status = "CUMPLE" if index % 3 else "NO CUMPLE"
        rows.append(
            {
                "section": section,
                "sector": sector,
                "level": str(3100 - index),
                "bench_num": index % 6 + 1,
                "type": "MATCH",
                "bench_score": 100.0 if status == "CUMPLE" else 60.0,
                "height_design": 15.0,
                "height_real": 15.0 + (index % 5) * 0.3,
                "height_dev": (index % 5) * 0.3,
                "angle_design": 75.0,
                "angle_real": 75.0 - (index % 4),
                "angle_dev": -(index % 4),
                "berm_design": 10.0,
                "berm_real": 9.0 + (index % 3),
                "berm_dev": -1.0 + (index % 3),
                "height_status": "CUMPLE",
                "angle_status": status,
                "berm_status": "CUMPLE",
                "spill_width": 0.5,
                "effective_berm": 9.0,
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


def _document(blob):
    return Document(io.BytesIO(blob))


def _paragraphs(doc):
    return [p.text for p in doc.paragraphs]


def _headings(doc):
    return [
        p.text
        for p in doc.paragraphs
        if p.style is not None and p.style.name == "Heading 1"
    ]


def _tables(doc):
    return [[cell.text for cell in row.cells] for table in doc.tables for row in table.rows]


def _table_with_header(doc, header):
    for table in doc.tables:
        first = [cell.text for cell in table.rows[0].cells]
        if header in first:
            return [[cell.text for cell in row.cells] for row in table.rows]
    return None


def _xml(doc):
    return doc.element.body.xml


@pytest.fixture(scope="module")
def base_blob():
    return build_word_report(_data()).getvalue()


def test_numbered_section_headings_are_stable(base_blob):
    headings = _headings(_document(base_blob))
    for expected in (
        "1. Resumen ejecutivo",
        "2. Alcance, fuentes y criterios",
        "3. Resultados por parámetro",
        "4. Logro de diseño por sector",
        "5. Mayores desviaciones comparables",
        "6. Plano de cumplimiento",
        "7. Detalle por banco",
        "8. Detalle por sección",
        "9. Análisis de perforación y tronadura",
    ):
        assert expected in headings


def test_cover_and_toc_field_present(base_blob):
    doc = _document(base_blob)
    text = "\n".join(_paragraphs(doc))
    assert "Proyecto: Proyecto X" in text
    assert "Operación: Rajo" in text
    assert "Control de revisión y aprobación" in text
    assert "Índice" in _headings(doc)
    assert 'TOC \\o "1-3" \\h \\z \\u' in _xml(doc)


def test_footer_keeps_page_x_of_y_fields(base_blob):
    doc = _document(base_blob)
    footer_xml = doc.sections[0].footer.paragraphs[0]._p.xml
    assert "PAGE" in footer_xml and "NUMPAGES" in footer_xml
    assert "Página " in doc.sections[0].footer.paragraphs[0].text


def test_executive_summary_contains_counts_score_and_conclusions(base_blob):
    doc = _document(base_blob)
    text = "\n".join(_paragraphs(doc) + [cell for row in _tables(doc) for cell in row])
    assert "Denominador del desglose" in text
    assert (
        "peor estado entre los registros de banco asociados al perfil, "
        "incluidos los faltantes y los adicionales"
    ) in text
    assert "Puntaje ponderado global (0–100)" in text
    assert "Puntaje disponible en" in text
    assert "bancos contabilizados; se considera evaluable si tiene al menos una desviación" in text
    assert "Logro de diseño global" in text
    assert "Conclusiones" in text
    assert "El modelo no registró advertencias" in text


def test_criteria_section_shows_signed_tolerances_and_no_filters(base_blob):
    rows = _tables(_document(base_blob))
    flat = [" | ".join(row) for row in rows]
    assert any("Altura de banco" in row and "−2.0 / +2.0" in row for row in flat)
    assert any("Ancho de berma" in row and "Mínimo 7.00" in row for row in flat)
    text = "\n".join(_paragraphs(_document(base_blob)))
    assert "Sin filtros." in text
    assert any("design.stl" in cell for row in _tables(_document(base_blob)) for cell in row)


def test_criteria_reports_applied_filters():
    data = _data(filters=ReportFilters(sectors=("A",), benches=(1, 2)))
    text = "\n".join(_paragraphs(_document(build_word_report(data).getvalue())))
    assert "Filtros aplicados" in text
    assert "sectores: A" in text
    assert "bancos de diseño: D1, D2" in text


def test_parameter_table_and_donut_image(base_blob):
    doc = _document(base_blob)
    assert any("Altura de banco (m)" in row for row in [" | ".join(r) for r in _tables(doc)])
    assert len(doc.inline_shapes) == 1


def test_parameter_mean_denominator_counts_only_finite_values_with_status():
    rows = _rows()
    rows[0]["height_status"] = None
    rows[2]["height_real"] = float("nan")
    rows[1]["angle_status"] = "-"
    doc = _document(build_word_report(_data(rows)).getvalue())
    table = _table_with_header(doc, "Media real (n con estado)")
    headers = table[0]
    mean_index = headers.index("Media real (n con estado)")
    height_row = next(row for row in table[1:] if row[0] == "Altura de banco (m)")
    angle_row = next(row for row in table[1:] if row[0] == "Ángulo de cara (°)")
    assert height_row[mean_index].endswith("(n=10)")
    assert angle_row[mean_index].endswith("(n=11)")


def test_design_achievement_section_has_global_row(base_blob):
    flat = [" | ".join(row) for row in _tables(_document(base_blob))]
    assert any(row.startswith("Global") for row in flat)


def test_empty_design_achievement_renders_note(monkeypatch):
    data = _data()
    object.__setattr__(data, "design_achievement", None)
    text = "\n".join(_paragraphs(_document(build_word_report(data).getvalue())))
    assert "Sin datos suficientes de logro de diseño" in text


def test_plan_section_notes_when_no_geometry(base_blob):
    text = "\n".join(_paragraphs(_document(base_blob)))
    assert "Sin geometría de secciones disponible" in text


def test_plan_image_rendered_from_plan_inputs():
    plan_inputs = {
        "sections": [
            {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0, "sector": ""},
            {"name": "S-02", "origin": [30.0, 0.0], "azimuth": 0.0, "length": 40.0, "sector": ""},
        ]
    }
    data = _data(plan_inputs=plan_inputs)
    doc = _document(build_word_report(data).getvalue())
    assert len(doc.inline_shapes) == 2
    assert "Sin geometría de secciones disponible" not in "\n".join(_paragraphs(doc))


def test_plan_sections_mark_filter_exclusions_without_reclassifying_unknown():
    plan_inputs = {"sections": [
        {"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-02", "origin": [30.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-99", "origin": [60.0, 0.0], "azimuth": 0.0, "length": 40.0},
    ]}
    data = _data(
        filters=ReportFilters(sections=("S-01",)),
        plan_inputs=plan_inputs,
    )

    sections = _plan_sections(data)

    assert [(section["name"], section["included"]) for section in sections] == [
        ("S-01", True), ("S-02", False), ("S-99", False),
    ]
    assert sections[1]["worst_status"] == "UNKNOWN"


def test_plan_sections_resolve_duplicate_names_by_sector_and_keep_ambiguous_unknown():
    rows = _rows(n=1, sections=1, sector="A") + _rows(n=1, sections=1, sector="B")
    plan_inputs = {"sections": [
        {"name": "S-01", "sector": "A", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "sector": "B", "origin": [30.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "origin": [60.0, 0.0], "azimuth": 0.0, "length": 40.0},
    ]}
    data = _data(rows, filters=ReportFilters(sectors=("A",)), plan_inputs=plan_inputs)

    sections = _plan_sections(data)

    assert [(section["sector"], section["included"], section["worst_status"]) for section in sections] == [
        ("A", True, "NO_CUMPLE"),
        ("B", False, "UNKNOWN"),
        ("", True, "UNKNOWN"),
    ]


def test_plan_section_without_sector_stays_unknown_when_same_name_geometry_is_unmatched():
    rows = _rows(n=1, sections=1, sector="A")
    plan_inputs = {"sections": [
        {"name": "S-01", "sector": "A", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "sector": "B", "origin": [30.0, 0.0], "azimuth": 0.0, "length": 40.0},
        {"name": "S-01", "origin": [60.0, 0.0], "azimuth": 0.0, "length": 40.0},
    ]}
    data = _data(rows, filters=ReportFilters(sectors=("A",)), plan_inputs=plan_inputs)

    sections = _plan_sections(data)

    assert [(section["included"], section["worst_status"]) for section in sections] == [
        (True, "NO_CUMPLE"), (False, "UNKNOWN"), (True, "UNKNOWN"),
    ]


def test_profile_table_columns_dropped_when_empty():
    rows = _rows()
    for row in rows:
        row["spill_width"] = None
        row["effective_berm"] = None
    blob = build_word_report(_data(rows)).getvalue()
    doc = _document(blob)
    header_rows = _table_with_header(doc, "Estado banco")
    assert header_rows, "profile table not found"
    headers = header_rows[0]
    assert "Derrame (m)" not in headers
    assert "Berma efectiva (m)" not in headers
    assert "Sector" not in headers
    assert "Altura diseño (m)" in headers
    text = "\n".join(_paragraphs(doc))
    assert "Columnas sin datos en esta sesión y omitidas" in text


def test_profile_table_keeps_columns_with_data():
    header_rows = _table_with_header(_document(build_word_report(_data()).getvalue()), "Estado banco")
    headers = header_rows[0]
    assert "Derrame (m)" in headers
    assert "Berma efectiva (m)" in headers
    assert "Estado banco" in headers


def test_status_column_is_labeled_never_numeric(base_blob):
    doc = _document(base_blob)
    header_rows = _table_with_header(doc, "Estado banco")
    headers = header_rows[0]
    index = headers.index("Estado banco")
    values = [row[index] for row in header_rows[1:]]
    assert values
    for value in values:
        assert value in STATUS_LABELS
        assert "✗" not in value and "✓" not in value


def test_status_cells_use_light_fill_with_dark_text(base_blob):
    doc = _document(base_blob)
    table_rows = _table_with_header(doc, "Estado banco")
    status_column = table_rows[0].index("Estado banco")
    fills = set()
    for values, row in zip(table_rows[1:], next(t for t in doc.tables if t.rows[0].cells[0].text == "Sección").rows[1:]):
        if values[status_column] not in STATUS_LABELS:
            continue
        tcPr = row.cells[status_column]._tc.tcPr
        shd = tcPr.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd")
        fills.update(element.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill") for element in shd)
    assert fills
    assert fills <= {"C9E7CB", "FBE3BF", "F6C6C6", "E2E8F0"}


def test_missing_bench_status_label_is_not_numeric():
    rows = _rows()
    rows[0]["type"] = "MISSING"
    rows[0]["height_status"] = None
    rows[0]["angle_status"] = None
    rows[0]["berm_status"] = None
    doc = _document(build_word_report(_data(rows)).getvalue())
    header_rows = _table_with_header(doc, "Estado banco")
    index = header_rows[0].index("Estado banco")
    assert "NO CONSTRUIDO" in {row[index] for row in header_rows[1:]}


def test_image_count_bounded_with_geometry():
    geometry = [
        {
            "section_name": f"S-{index + 1:02d}",
            "params_design": None,
            "profile_d": ([0.0, 10.0], [3110.0, 3125.0]),
            "profile_t": ([0.0, 10.0], [3109.5, 3124.0]),
        }
        for index in range(3)
    ]
    blob = build_word_report(_data(section_geometry=geometry)).getvalue()
    doc = _document(blob)
    assert 1 <= len(doc.inline_shapes) <= 8


def test_blast_none_renders_note(base_blob):
    text = "\n".join(_paragraphs(_document(base_blob)))
    assert "Sin datos de pozos de tronadura en esta sesión." in text


def test_synthetic_blast_renders_summary_table():
    blast = {
        "holes": [
            {"dist": 5.0, "collar_z": 3125.0, "toe_z": 3112.0, "bench_height_m": 15.0},
            {"dist": 9.0, "collar_z": 3124.0, "toe_z": 3110.0, "bench_height_m": 15.0},
        ],
        "tolerance": {"neg": 1.0, "pos": 1.0},
    }
    doc = _document(build_word_report(_data(blast=blast)).getvalue())
    flat = [" | ".join(row) for row in _tables(doc)]
    assert any("Total de pozos registrados | 2" in row for row in flat)
    assert any("Pasadura promedio" in row for row in flat)
    assert any("Tolerancia cresta-pie aplicada" in row for row in flat)
    assert "Sin datos de pozos de tronadura en esta sesión." not in "\n".join(_paragraphs(doc))


def test_design_surface_collar_elevation_is_labeled_as_estimated():
    blast = {
        "holes": [{"dist": 5.0, "collar_z": 3125.0, "toe_z": 3112.0, "Z_collar_semantic": "design_surface_estimate"}],
        "tolerance": {"neg": 1.0, "pos": 1.0},
    }
    text = "\n".join(_paragraphs(_document(build_word_report(_data(blast=blast)).getvalue())))
    assert "fue estimada desde la superficie de diseño" in text
    assert "no debe interpretarse como cota real levantada" in text


def test_blast_without_bench_height_never_prints_nan():
    blast = {
        "holes": [{"dist": 5.0, "collar_z": 3125.0, "toe_z": 3112.0}],
        "tolerance": {"neg": 1.0, "pos": 1.0},
    }
    doc = _document(build_word_report(_data(blast=blast)).getvalue())
    flat = [" | ".join(row) for row in _tables(doc)]
    assert any("No disponible sin altura de banco" in row for row in flat)
    assert not any("nan" in row.lower() for row in flat)


def test_section_details_split_non_compliant_and_annex():
    rows = _rows(n=6, sections=3)
    text = "\n".join(_paragraphs(_document(build_word_report(_data(rows)).getvalue())))
    assert "Perfiles no conformes" in text
    assert "Anexo: perfiles conformes" in text


def test_unknown_profile_is_separate_from_compliant_and_non_compliant():
    from dataclasses import replace

    data = _data(_rows(n=2, sections=2))
    profiles = list(data.profiles)
    profiles[0] = replace(profiles[0], worst_status="UNKNOWN")
    object.__setattr__(data, "profiles", tuple(profiles))
    text = "\n".join(_paragraphs(_document(build_word_report(data).getvalue())))
    assert "Perfiles con estado UNKNOWN u otro estado no clasificado (1)" in text
    assert "se muestran por separado, sin contarlos como conformes ni no conformes" in text
    assert "SIN EVALUAR (UNKNOWN): 1 perfil en el detalle" in text
    assert "Denominador del desglose: 2 perfiles" in text
    assert "no hay perfiles clasificados como CUMPLE, FUERA o NO CUMPLE" not in text


def test_ambiguous_profile_does_not_display_arbitrary_sector():
    rows = _rows(n=1, sections=1, sector="A") + _rows(n=1, sections=1, sector="B")
    geometry = [{
        "section_name": "S-01",
        "params_design": None,
        "profile_d": ([0.0, 10.0], [3110.0, 3125.0]),
        "profile_t": ([0.0, 10.0], [3109.5, 3124.0]),
    }]
    data = _data(rows, section_geometry=geometry)
    payload = _profile_payload(data, data.profiles[0])
    assert "sector" not in payload
    assert any("no se pueden atribuir a un sector" in warning for warning in data.warnings)
    text = "\n".join(_paragraphs(_document(build_word_report(data).getvalue())))
    assert "no se pueden atribuir a un sector" in text
    assert "Sector con menor logro de diseño:  (" not in text


def test_all_non_compliant_uses_two_per_page():
    rows = _rows(n=6, sections=3)
    for row in rows:
        row["angle_status"] = "NO CUMPLE"
        row["bench_score"] = 60.0
    text = "\n".join(_paragraphs(_document(build_word_report(_data(rows)).getvalue())))
    assert "Todos los perfiles presentan estado no conforme" in text
    assert "Anexo: perfiles conformes" not in text


def test_plan_accepts_api_section_objects_and_mesh_topo():
    class SectionLine:
        def __init__(self, name, origin, azimuth, length, sector):
            self.name = name
            self.origin = origin
            self.azimuth = azimuth
            self.length = length
            self.sector = sector

    class Mesh:
        def __init__(self):
            self.vertices = [
                [0.0, 0.0, 3110.0],
                [40.0, 0.0, 3115.0],
                [0.0, 40.0, 3120.0],
                [40.0, 40.0, 3125.0],
            ]

    plan_inputs = {
        "comparisons": [],
        "sections": [
            SectionLine("S-01", [0.0, 0.0], 0.0, 40.0, ""),
            SectionLine("S-02", [30.0, 0.0], 0.0, 40.0, ""),
        ],
        "mesh_topo": Mesh(),
        "grid_ref": 0.0,
    }
    doc = _document(build_word_report(_data(plan_inputs=plan_inputs)).getvalue())
    assert len(doc.inline_shapes) == 2
    assert "Sin geometría de secciones disponible" not in "\n".join(_paragraphs(doc))


def test_blast_with_float_tolerance_and_geo_holes_projects_on_profiles():
    geometry = [
        {
            "section_name": "S-01",
            "params_design": None,
            "profile_d": ([0.0, 10.0], [3110.0, 3125.0]),
            "profile_t": ([0.0, 10.0], [3109.5, 3124.0]),
        }
    ]
    blast = {
        "holes": [
            {"X": 4.0, "Y": 0.0, "Z_collar": 3126.0, "Z_toe": 3110.0, "Len": 16.0},
            {"X": 6.0, "Y": 0.0, "Z_collar": 3126.0, "Z_toe": 3110.0, "Len": 16.0},
        ],
        "tolerance": 10.0,
    }
    plan_inputs = {"sections": [{"name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 40.0}]}
    rows = _rows(n=2, sections=1)
    data = _data(rows, section_geometry=geometry, plan_inputs=plan_inputs, blast=blast)
    doc = _document(build_word_report(data).getvalue())
    flat = [" | ".join(row) for row in _tables(doc)]
    assert any("Tolerancia de proyección de pozos" in row and "±10.00 m" in row for row in flat)
    assert any("Total de pozos registrados | 2" in row for row in flat)


@pytest.mark.parametrize(
    ("inclination", "expected_toe_station"),
    [(30.0, 10.0), (0.0, 0.0)],
    ids=("inclined-hole", "vertical-hole"),
)
def test_blast_hole_report_toe_uses_projected_toe_station(inclination, expected_toe_station):
    source = pd.DataFrame([{
        "Latitud_Geo": 0.0,
        "Longitud_Geo": 0.0,
        "Nombre_Banco": 4000.0,
        "Inclinacion_real": inclination,
        "Azimuth_real": 0.0,
        "longitud_real": 20.0,
        "Incl_convention": "from_vertical",
        "bench_height_m": 15.0,
    }])
    accepted_rows = procesar_pozos(
        source,
        geometry_user_confirmed=True,
        incl_convention="from_vertical",
    )[0]
    reference = proyectar_pozos_en_seccion(
        accepted_rows,
        origin=np.array([0.0, 0.0]),
        azimuth=0.0,
        length=100.0,
        tolerance=1.0,
    ).iloc[0]
    plan_inputs = {
        "sections": [{
            "name": "S-01",
            "origin": [0.0, 0.0],
            "azimuth": 0.0,
            "length": 100.0,
        }],
    }
    data = _data(
        _rows(n=1, sections=1),
        plan_inputs=plan_inputs,
        blast={"holes": accepted_rows.to_dict(orient="records"), "tolerance": 1.0},
    )

    report_holes = _project_holes(data, "S-01")

    assert reference["dist_along_toe"] - reference["dist_along"] == pytest.approx(expected_toe_station)
    assert report_holes is not None
    assert report_holes[0]["dist"] == pytest.approx(reference["dist_along"])
    assert report_holes[0]["toe_dist"] == pytest.approx(reference["dist_along_toe"])


def test_empty_dataset_degrades_to_notes():
    data = build_report_data([], {"tolerances": dict(TOLERANCES)}, ReportFilters(), dict(META))
    doc = _document(build_word_report(data).getvalue())
    text = "\n".join(_paragraphs(doc))
    assert "No hay comparaciones en la sesión." in text
    assert "No hay bancos para tabular." in text
    assert "No hay perfiles para detallar." in text
    assert len(doc.inline_shapes) == 0


def test_size_and_time_budget_for_100_rows():
    rows = _rows(n=100, sections=12)
    data = _data(rows)
    started = time.perf_counter()
    blob = build_word_report(data).getvalue()
    elapsed = time.perf_counter() - started
    assert len(blob) < 1_500_000, f"{len(blob)} bytes exceeds the 1.5 MB budget"
    assert elapsed < 6.0, f"{elapsed:.2f}s exceeds the 6 s budget"


def _detail_geometry(sections=4):
    return [
        {
            "section_name": f"S-{index + 1:02d}",
            "params_design": None,
            "profile_d": ([0.0, 100.0], [3050.0, 3110.0]),
            "profile_t": ([0.0, 100.0], [3049.5, 3109.0]),
        }
        for index in range(sections)
    ]


def _grid_rows(doc):
    """Return, per table, the drawings found in each cell of each row."""
    grids = []
    for table in doc.tables:
        rows = [
            [cell._tc.findall(".//" + qn("w:drawing")) for cell in row.cells]
            for row in table.rows
        ]
        if rows and any(any(cell for cell in row) for row in rows):
            grids.append(rows)
    return grids


def _extents(cells):
    out = []
    for cell in cells:
        for drawing in cell:
            inline = drawing.find(qn("wp:inline"))
            extent = inline.find(qn("wp:extent")) if inline is not None else None
            if extent is not None:
                out.append((int(extent.get("cx")), int(extent.get("cy"))))
    return out


def test_detail_plots_are_side_by_side_two_per_page():
    rows = _rows(n=8, sections=4)
    for row in rows:
        row["angle_status"] = "NO CUMPLE"
        row["bench_score"] = 60.0
    doc = _document(build_word_report(_data(rows, section_geometry=_detail_geometry())).getvalue())

    grids = [grid for grid in _grid_rows(doc) if len(grid[0]) == 2]
    assert grids, "no two-column detail grid found"
    for grid in grids:
        for row in grid:
            assert all(cell for cell in row), "a detail row holds fewer than two plots"
    placed = [extent for grid in grids for row in grid for extent in _extents(row)]
    assert len(placed) == 4
    for cx, cy in placed:
        assert abs(cx - Mm(DETAIL_COLUMN_MM)) <= Mm(DETAIL_COLUMN_MM) * 0.02
        assert cy < cx, "landscape detail plot should be wider than tall"


def test_detail_grid_is_borderless():
    doc = _document(build_word_report(_data(section_geometry=_detail_geometry())).getvalue())
    grid_tables = [
        table
        for table in doc.tables
        if any(cell._tc.findall(".//" + qn("w:drawing")) for row in table.rows for cell in row.cells)
    ]
    assert grid_tables
    for table in grid_tables:
        borders = table._tbl.tblPr.find(qn("w:tblBorders"))
        assert borders is not None
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            element = borders.find(qn(f"w:{edge}"))
            assert element is not None and element.get(qn("w:val")) == "none"


def test_annex_keeps_two_compliant_profiles_side_by_side():
    doc = _document(build_word_report(_data(_rows(n=8, sections=4), section_geometry=_detail_geometry())).getvalue())
    text = "\n".join(_paragraphs(doc))
    assert "Anexo: perfiles conformes" in text
    assert "se presentan dos por página en formato compacto" in text
    grids = [grid for grid in _grid_rows(doc) if len(grid[0]) == 2]
    assert grids
    for grid in grids:
        assert len(grid) == 1, "each page carries a single row of two plots"
        assert all(any(cell for cell in row) for row in grid)
        assert sum(len(cell) for row in grid for cell in row) <= 2
    placed = [extent for grid in grids for row in grid for extent in _extents(row)]
    assert len(placed) == 4


def test_all_non_compliant_note_matches_parallel_layout():
    rows = _rows(n=8, sections=4)
    for row in rows:
        row["angle_status"] = "NO CUMPLE"
        row["bench_score"] = 60.0
    text = "\n".join(_paragraphs(_document(build_word_report(_data(rows)).getvalue())))
    assert "Todos los perfiles presentan estado no conforme" in text
    assert "a ancho completo" not in text
    assert "en paralelo" in text


def test_section_seven_starts_on_a_new_page(base_blob):
    doc = _document(base_blob)
    heading = next(p for p in doc.paragraphs if p.text == "8. Detalle por sección")
    assert heading.paragraph_format.page_break_before is True


def test_major_headings_keep_with_next(base_blob):
    doc = _document(base_blob)
    headings = [
        p
        for p in doc.paragraphs
        if p.style is not None and p.style.name in ("Heading 1", "Heading 2")
    ]
    assert len(headings) > 5
    for heading in headings:
        keep_next = heading._p.pPr.find(qn("w:keepNext"))
        assert keep_next is not None
        assert keep_next.get(qn("w:val")) in (None, "true", "1")


def test_settings_request_field_update_on_open(base_blob):
    settings = _document(base_blob).settings.element
    element = settings.find(qn("w:updateFields"))
    assert element is not None
    assert element.get(qn("w:val")) == "true"


def test_toc_keeps_spanish_placeholder_instruction(base_blob):
    text = "\n".join(_paragraphs(_document(base_blob)))
    assert "El índice se actualiza al abrir el documento en Word" in text
    assert "Ctrl+E, F9" in text
