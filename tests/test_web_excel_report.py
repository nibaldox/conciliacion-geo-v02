"""Tests for the analytical Excel builder (contract C9, stage E5)."""
from __future__ import annotations

import dataclasses
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from openpyxl import load_workbook

from core.report_charts import STATUS_COLORS
from core.report_data import ReportFilters, build_report_data
from core.report_texts import kpi_definitions, scope_lines
from core.report_volumes import SectionExcavation
from core.web_excel_report import build_excel_report

FIXTURE = Path(__file__).parent / "fixtures" / "report_parity.json"
BASE_SHEETS = ["Léeme", "Resumen", "Bancos", "Secciones", "Sector-Nivel"]


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _data(filters: ReportFilters | None = None, rows=None, **kwargs):
    fx = _fixture()
    return build_report_data(
        fx["rows"] if rows is None else rows,
        {"tolerances": fx["tolerances"]},
        filters or ReportFilters(),
        {"project": "Proyecto Prueba", "author": "Autora", "generated_at": "2026-11-14T10:00:00"},
        **kwargs,
    )


def _book(data):
    buffer = build_excel_report(data)
    assert isinstance(buffer, io.BytesIO)
    assert buffer.tell() == 0
    return load_workbook(io.BytesIO(buffer.getvalue()))


def _table_rows(ws) -> list[dict]:
    table = next(iter(ws.tables.values()))
    cells = ws[table.ref]
    headers = [cell.value for cell in cells[0]]
    return [dict(zip(headers, (cell.value for cell in row))) for row in cells[1:]]


def _table_cells(ws) -> tuple[list[str], list[tuple]]:
    table = next(iter(ws.tables.values()))
    cells = ws[table.ref]
    return [cell.value for cell in cells[0]], list(cells[1:])


def _labelled_row(ws, label: str) -> tuple:
    for row in ws.iter_rows():
        if row[0].value == label:
            return row
    raise AssertionError(f"label {label!r} not found in sheet {ws.title!r}")


def _sheet_text(ws) -> str:
    return "\n".join(
        str(cell.value)
        for row in ws.iter_rows()
        for cell in row
        if cell.value is not None
    )


@pytest.fixture()
def book():
    return _book(_data())


def test_workbook_uses_spanish_bench_type_labels_without_internal_tokens(book):
    text = "\n".join(_sheet_text(ws) for ws in book.worksheets)
    for label in ("Comparado", "No construido", "Adicional"):
        assert label in text
    assert not re.search(r"\b(?:MATCH|MISSING|EXTRA)\b", text), text


def test_sheet_order_and_names_without_blast(book):
    assert book.sheetnames == BASE_SHEETS
    assert all(len(name) <= 31 for name in book.sheetnames)


def test_bancos_is_a_table_with_autofilter_and_frozen_header(book):
    ws = book["Bancos"]
    assert len(ws.tables) == 1
    table = next(iter(ws.tables.values()))
    assert table.autoFilter is not None
    assert table.autoFilter.ref == table.ref
    assert ws.freeze_panes == "A2"
    assert len(_table_rows(ws)) == 6


def test_bancos_rows_keep_missing_and_extra_with_nominal_level(book):
    rows = _table_rows(book["Bancos"])
    assert [row["Tipo"] for row in rows] == [
        "Comparado", "Comparado", "Comparado", "Comparado", "No construido", "Adicional",
    ]
    assert "Cota nominal" in rows[0]
    assert [row["Cota nominal"] for row in rows] == [100, 85, 70, 60, 45, None]
    assert [row["Sector"] for row in rows] == ["A", "A", "A", "B", "B", "B"]
    assert rows[4]["Estado banco"] == "NO CONSTRUIDO"
    assert rows[5]["Estado banco"] == "BANCO ADICIONAL"


def test_bancos_numbers_are_numbers_and_none_is_empty_never_zero(book):
    rows = _table_rows(book["Bancos"])
    first, missing, extra = rows[0], rows[4], rows[5]
    assert first["Altura diseño (m)"] == 10.0
    assert first["Altura real (m)"] == 10.5
    assert first["Desv. altura (m)"] == 0.5
    assert isinstance(first["Ángulo real (°)"], (int, float))
    assert first["Desv. cresta (m)"] == 0.5
    assert missing["Desv. cresta (m)"] is None
    assert extra["Desv. pata (m)"] is None
    assert missing["Berma mínima (m)"] is None
    assert missing["Altura diseño (m)"] == 11.0
    assert missing["Altura real (m)"] is None
    assert missing["Desv. altura (m)"] is None
    assert missing["Berma real (m)"] is None
    assert missing["Estado ángulo"] is None
    assert extra["Altura diseño (m)"] is None
    assert extra["Altura real (m)"] == 6.0
    assert extra["Berma diseño (m)"] is None
    assert extra["Estado berma"] is None
    assert rows[1]["Derrame (m)"] == 0


def test_bancos_crest_toe_and_berm_min_come_from_bench_row_without_plan_inputs():
    data = _data()
    assert data.plan_inputs is None
    rows = _table_rows(_book(data)["Bancos"])
    assert rows[0]["Desv. cresta (m)"] == 0.5
    assert rows[0]["Desv. pata (m)"] == 0.2
    assert rows[1]["Desv. cresta (m)"] == -0.8
    assert rows[2]["Desv. cresta (m)"] == 1.2
    assert rows[3]["Desv. cresta (m)"] == 0
    assert rows[3]["Desv. pata (m)"] == 0
    assert rows[4]["Desv. cresta (m)"] is None
    assert rows[5]["Desv. pata (m)"] is None
    assert rows[0]["Berma mínima (m)"] == 7.0
    assert rows[4]["Berma mínima (m)"] is None


def test_bancos_ignores_plan_comparisons_for_crest_toe_and_berm_min():
    fx = _fixture()
    other = [dict(row, delta_crest=9.9, delta_toe=9.9, berm_min=9.9) for row in fx["rows"]]
    data = _data(plan_inputs={"comparisons": other, "sections": []})
    rows = _table_rows(_book(data)["Bancos"])
    assert rows[0]["Desv. cresta (m)"] == 0.5
    assert rows[0]["Desv. pata (m)"] == 0.2
    assert rows[0]["Berma mínima (m)"] == 7.0
    assert rows[4]["Desv. cresta (m)"] is None


def test_bancos_non_finite_crest_toe_stay_empty_never_zero():
    fx = _fixture()
    rows = [dict(row) for row in fx["rows"]]
    rows[0].update(delta_crest=float("nan"), delta_toe=float("inf"))
    out = _table_rows(_book(_data(rows=rows))["Bancos"])
    assert out[0]["Desv. cresta (m)"] is None
    assert out[0]["Desv. pata (m)"] is None
    assert out[1]["Desv. cresta (m)"] == -0.8


def test_bancos_design_below_min_is_si_no():
    fx = _fixture()
    rows = [dict(row) for row in fx["rows"]]
    rows[0]["berm_design"] = 5.0
    out = _table_rows(_book(_data(rows=rows))["Bancos"])
    assert out[0]["Diseño bajo el mínimo"] == "Sí"
    assert out[1]["Diseño bajo el mínimo"] == "No"


def test_bancos_status_columns_have_palette_conditional_fill(book):
    ws = book["Bancos"]
    headers, cells = _table_cells(ws)
    status_letters = {
        cells[0][index].column_letter
        for index, header in enumerate(headers)
        if header.startswith("Estado")
    }
    assert len(status_letters) >= 4
    covered: dict[str, set[str]] = {}
    for ranges, rules in ws.conditional_formatting._cf_rules.items():
        for cell_range in ranges.sqref.ranges:
            for rule in rules:
                color = rule.dxf.fill.bgColor.rgb or rule.dxf.fill.fgColor.rgb
                for letter in status_letters:
                    if cell_range.min_col <= ws[f"{letter}1"].column <= cell_range.max_col:
                        covered.setdefault(letter, set()).add(color[-6:].upper())
    palette = {
        STATUS_COLORS[key].lstrip("#").upper()
        for key in ("CUMPLE", "FUERA", "NO_CUMPLE")
    }
    assert set(covered) == status_letters
    for letter in status_letters:
        assert palette <= covered[letter]


def test_all_empty_columns_are_dropped():
    fx = _fixture()
    rows = []
    for row in fx["rows"]:
        row = dict(row)
        row["sector"] = ""
        row["spill_width"] = None
        row["effective_berm"] = None
        row["delta_crest"] = None
        row["delta_toe"] = None
        rows.append(row)
    book = _book(_data(rows=rows))
    headers, _cells = _table_cells(book["Bancos"])
    assert "Sector" not in headers
    assert "Derrame (m)" not in headers
    assert "Berma efectiva (m)" not in headers
    assert "Desv. cresta (m)" not in headers
    assert "Desv. pata (m)" not in headers
    assert "Berma mínima (m)" in headers
    assert "Altura real (m)" in headers
    assert "Cota nominal" in headers
    assert None not in headers
    assert "Sector" not in _table_cells(book["Secciones"])[0]
    assert "Sector" not in _table_cells(book["Sector-Nivel"])[0]


def test_resumen_percentages_are_numbers_with_percent_format(book):
    ws = book["Resumen"]
    header = _labelled_row(ws, "Parámetro")
    columns = {cell.value: index for index, cell in enumerate(header) if cell.value}
    height = _labelled_row(ws, "Altura de banco")
    berm = _labelled_row(ws, "Ancho de berma")
    pct = height[columns["% cumplimiento"]]
    assert pct.value == pytest.approx(0.75)
    assert pct.number_format.endswith("%")
    assert height[columns["Evaluados (comparados)"]].value == 4
    assert height[columns["Cumple"]].value == 3
    assert height[columns["Fuera de tolerancia"]].value == 1
    assert height[columns["No cumple"]].value == 0
    assert height[columns["No comparados"]].value == 2
    assert berm[columns["% cumplimiento"]].value == pytest.approx(0.75)
    assert berm[columns["Evaluados (comparados)"]].value == 4


def test_resumen_kpis_are_numeric(book):
    ws = book["Resumen"]
    data = _data()
    assert _labelled_row(ws, "No cumple")[1].value == data.headline["profiles"]["NO_CUMPLE"]
    assert _labelled_row(ws, "Cumple")[1].value == data.headline["profiles"]["CUMPLE"]
    assert _labelled_row(ws, "No cumple por geometría")[1].value == data.headline["nc_by_geometry"]
    assert (
        _labelled_row(ws, "No cumple solo por banco no construido o adicional")[1].value
        == data.headline["nc_only_missing_extra"]
    )
    assert _labelled_row(ws, "Puntaje ponderado global (0-100)")[1].value == pytest.approx(
        data.global_weighted_score
    )
    assert _labelled_row(ws, "Logro de diseño (0-100)")[1].value == (
        data.design_achievement["global"]["global_score"]
    )
    assert _labelled_row(ws, "Bancos no construidos")[1].value == 1
    assert _labelled_row(ws, "Bancos adicionales")[1].value == 1


def test_resumen_has_two_native_charts():
    payload = build_excel_report(_data()).getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        charts = [name for name in archive.namelist() if name.startswith("xl/charts/chart")]
        assert len(charts) == 2
        assert all(b"barChart" in archive.read(name) for name in charts)


def _heading_row(ws, text: str) -> int:
    return _labelled_row(ws, text)[0].row


def _chart_anchors(ws) -> list[tuple[int, int]]:
    return sorted((chart.anchor._from.row + 1, chart.anchor._from.col + 1) for chart in ws._charts)


def test_resumen_charts_sit_next_to_their_tables(book):
    ws = book["Resumen"]
    status_row = _heading_row(ws, "Perfiles por estado")
    parameter_row = _heading_row(ws, "Cumplimiento por parámetro (sobre bancos comparados)")
    assert _chart_anchors(ws) == [(status_row, 4), (parameter_row, 10)]
    assert ws.cell(row=status_row + 1, column=3).value == "% de perfiles"
    assert ws.cell(row=status_row + 1, column=4).value is None
    assert ws.cell(row=parameter_row + 1, column=9).value == "Media real"
    assert ws.cell(row=parameter_row + 1, column=10).value is None
    for row in ws.iter_rows(min_row=status_row, max_row=parameter_row - 1, min_col=4):
        assert all(cell.value is None for cell in row)


def test_resumen_parameter_chart_stays_beside_table_without_sector_comparison():
    fx = _fixture()
    rows = [dict(row, sector="A") for row in fx["rows"]]
    ws = _book(_data(rows=rows))["Resumen"]
    parameter_row = _heading_row(ws, "Cumplimiento por parámetro (sobre bancos comparados)")
    assert _chart_anchors(ws)[1] == (parameter_row, 9)


def test_resumen_without_geometry_states_no_excavation_instead_of_zero(book):
    ws = book["Resumen"]
    text = _sheet_text(ws)
    assert "Sin geometría de secciones" in text
    with pytest.raises(AssertionError):
        _labelled_row(ws, "Volumen de sobreexcavación (m³)")


def _with_excavation(data):
    entries = (
        SectionExcavation(
            section="S-01", sector="A", area_over_m2=12.5, area_under_m2=3.0,
            influence_width_m=10.0, volume_over_m3=125.0, volume_under_m3=30.0,
            window=(0.0, 40.0, 80.0, 105.0), source="calculate_area_between_profiles",
            assumptions=("Supuesto de área de prueba.",), warnings=(),
        ),
        SectionExcavation(
            section="S-03", sector="B", area_over_m2=4.0, area_under_m2=None,
            influence_width_m=None, volume_over_m3=None, volume_under_m3=None,
            window=None, source="calculate_area_between_profiles",
            assumptions=("Supuesto de área de prueba.",),
            warnings=("Sin ancho de influencia.",),
        ),
    )
    totals = {
        "area_over_m2": 16.5, "area_under_m2": 3.0, "volume_over_m3": 125.0,
        "volume_under_m3": 30.0, "n_sections": 2, "n_without_volume": 1,
    }
    return dataclasses.replace(data, excavation=entries, excavation_totals=totals)


def test_secciones_one_row_per_profile_with_excavation():
    data = _with_excavation(_data())
    book = _book(data)
    rows = {row["Sección"]: row for row in _table_rows(book["Secciones"])}
    assert list(rows) == ["S-01", "S-02", "S-03", "S-04"]
    first = rows["S-01"]
    assert first["Sector"] == "A"
    assert first["Estado"] == "CUMPLE"
    assert first["Puntaje ponderado (0-100)"] == 100.0
    assert first["N° bancos"] == 2
    assert first["Área sobreexcavación (m²)"] == 12.5
    assert first["Área subexcavación (m²)"] == 3.0
    assert first["Ancho de influencia (m)"] == 10.0
    assert first["Volumen sobreexcavación (m³)"] == 125.0
    assert first["Volumen subexcavación (m³)"] == 30.0
    assert "40" in first["Ventana"] and "105" in first["Ventana"]
    third = rows["S-03"]
    assert third["Estado"] == "NO CUMPLE"
    assert third["Área sobreexcavación (m²)"] == 4.0
    assert third["Área subexcavación (m²)"] is None
    assert third["Volumen sobreexcavación (m³)"] is None
    assert third["Advertencias"] == "Sin ancho de influencia."
    assert rows["S-02"]["Área sobreexcavación (m²)"] is None
    assert rows["S-04"]["Puntaje ponderado (0-100)"] is None
    assert book["Secciones"].freeze_panes == "A2"

    resumen = book["Resumen"]
    assert _labelled_row(resumen, "Volumen de sobreexcavación (m³)")[1].value == 125.0
    assert _labelled_row(resumen, "Secciones sin volumen")[1].value == 1
    assert "Supuesto de área de prueba." in _sheet_text(book["Léeme"])
    assert "Área entre los perfiles de diseño y topografía" in _sheet_text(book["Léeme"])


def test_sector_nivel_aggregates_per_sector_and_nominal_level(book):
    ws = book["Sector-Nivel"]
    rows = _table_rows(ws)
    keys = [(row["Sector"], row["Cota nominal"]) for row in rows]
    assert keys == [("A", 100), ("A", 85), ("A", 70), ("B", 60), ("B", 45), ("B", None)]
    by_key = dict(zip(keys, rows))
    a70 = by_key[("A", 70)]
    assert a70["N° secciones"] == 1
    assert a70["Comparados"] == 1
    assert a70["% cumple altura"] == 0
    assert a70["% cumple ángulo"] == 1
    assert a70["Desv. media altura (m)"] == pytest.approx(2.0)
    b45 = by_key[("B", 45)]
    assert b45["No construidos"] == 1
    assert b45["Comparados"] == 0
    assert b45["% cumple altura"] is None
    assert b45["Desv. media altura (m)"] is None
    b60 = by_key[("B", 60)]
    assert b60["Comparados no cumple"] == 1
    assert b60["% cumple berma"] == 0
    assert by_key[("B", None)]["Adicionales"] == 1
    headers, cells = _table_cells(ws)
    pct_cell = cells[0][headers.index("% cumple altura")]
    assert pct_cell.number_format.endswith("%")
    assert ws.freeze_panes == "A2"


def test_filters_are_echoed_in_leeme():
    filters = ReportFilters(
        sectors=("B",),
        sections=("S-03",),
        levels_by_sector=(("B", ("60",)),),
    )
    data = _data(filters)
    book = _book(data)
    text = _sheet_text(book["Léeme"])
    assert "Proyecto Prueba" in text
    assert "14/11/2026 10:00" in text
    assert "Sector B: cota 60" in text
    assert "Sección: S-03" in text
    for line in scope_lines(data):
        assert line in text
    assert len(_table_rows(book["Bancos"])) == 1


def test_leeme_without_filters_and_definitions(book):
    ws = book["Léeme"]
    text = _sheet_text(ws)
    assert "Sin filtros: todas las secciones y cotas" in text
    assert "bancos comparados" in text
    assert "no construidos" in text
    assert "⅓" in text
    assert "× ancho de influencia" in text
    assert "valores oficiales" in text
    assert "± 5.0 °" in text or "± 5,0 °" in text
    assert "Sin geometría de secciones" in text
    for warning in _data().level_warnings:
        assert warning in text


def test_leeme_reuses_shared_kpi_definitions_and_scope_lines():
    filters = ReportFilters(sectors=("A",), levels_by_sector=(("A", ("100", "85")),))
    for data in (_data(), _data(filters)):
        ws = _book(data)["Léeme"]
        definitions = kpi_definitions(data)
        assert len(definitions) == 6
        for name, text in definitions:
            assert _labelled_row(ws, name)[1].value == text
        values = [row[1].value for row in ws.iter_rows()]
        lines = scope_lines(data)
        assert lines
        for line in lines:
            assert values.count(line) == 1
        positions = [values.index(line) for line in lines]
        assert positions == sorted(positions)


def test_leeme_does_not_repeat_shared_texts_with_local_wording(book):
    labels = [row[0].value for row in book["Léeme"].iter_rows() if row[0].value]
    for name, _text in kpi_definitions(_data()):
        assert labels.count(name) == 1
    for dropped in ("Sectores", "Regla", "Método de volumen", "Solo valores oficiales",
                    "Puntaje ponderado global (0-100)", "Logro de diseño (0-100)"):
        assert dropped not in labels


def test_leeme_keeps_excel_specific_blast_scope_line():
    data = _data(blast={"holes": _holes(), "tolerance": 1.0})
    text = _sheet_text(_book(data)["Léeme"])
    assert "no se aplican a los pozos" in text
    assert "no se aplican a los pozos" not in _sheet_text(_book(_data())["Léeme"])


def test_leeme_lists_heatmap_notes():
    note = "Mapa de calor no calculado; calcúlelo en la vista 3D para incluirlo."
    data = _data(heatmap_notes=[note])
    assert note in _sheet_text(_book(data)["Léeme"])


def _holes() -> list[dict]:
    holes = []
    for index in range(40):
        holes.append({
            "Nombre_Malla_Original": "F1_3110_01", "Blast": "01",
            "fecha_tronadura": "2026-01-02", "Tipo_Explosivo": "Pirex-930",
            "Kilos_Cargados_real": 500 + index, "pf_g_per_ton": 100.0,
            "pf_vol_kgm3": 0.25, "Len": 16.0,
        })
    for index in range(10):
        holes.append({
            "Nombre_Malla_Original": "F1_3110_02", "Blast": "02",
            "fecha_tronadura": "2026-01-09", "Tipo_Explosivo": None,
            "Kilos_Cargados_real": None, "pf_g_per_ton": None,
            "pf_vol_kgm3": None, "Len": 15.0,
        })
    return holes


def test_tronadura_absent_without_blast_data():
    assert "Tronadura" not in _book(_data()).sheetnames
    assert "Tronadura" not in _book(_data(blast={})).sheetnames
    assert "Tronadura" not in _book(_data(blast={"holes": []})).sheetnames


def test_tronadura_is_a_summary_by_blast_never_a_hole_dump():
    data = _data(blast={"holes": _holes(), "tolerance": 1.0})
    book = _book(data)
    assert book.sheetnames == BASE_SHEETS + ["Tronadura", "Pozos"]
    ws = book["Tronadura"]
    assert ws.max_row < 20
    rows = {row["Malla"]: row for row in _table_rows(ws)}
    assert list(rows) == ["F1_3110_01", "F1_3110_02"]
    first, second = rows["F1_3110_01"], rows["F1_3110_02"]
    assert first["N° pozos"] == 40
    assert first["FC B×S×L (g/t)"] == pytest.approx(100.0)
    assert first["FC volumétrico medio (kg/m³)"] == pytest.approx(0.25)
    assert first["Explosivo total (kg)"] == sum(500 + index for index in range(40))
    assert first["Explosivo"] == "Pirex-930"
    assert second["N° pozos"] == 10
    assert second["FC B×S×L (g/t)"] is None
    assert second["Explosivo total (kg)"] is None
    assert second["Explosivo"] == "Sin dato"
    assert "ANFO" not in _sheet_text(ws).upper()


def test_empty_report_builds_with_base_sheets():
    data = build_report_data([], {}, ReportFilters(), {})
    book = _book(data)
    assert book.sheetnames == BASE_SHEETS
    assert len(book["Bancos"].tables) == 0
    assert "No hay comparaciones en la sesión." in _sheet_text(book["Léeme"])


def _audit_holes() -> list[dict]:
    return [
        {
            "id_pozo": "007", "hole_id": "0", "label_pozo": "A-1",
            "Nombre_Malla_Original": "F1_3110_01", "X": 100.0, "Y": 200.0, "Z_collar": 3870.0,
            "Len": 15.0, "Incl": 0.0, "Kilos_Cargados_real": 500, "Tipo_Explosivo": "Pirex-930",
            "explosive_status": "UNVALIDATED_REFERENCE", "explosive_source": "Catálogo",
            "pf_voronoi_bench_g_per_ton": 95.5, "pf_voronoi_bench_status": "VALID",
            "pf_voronoi_bench_source": "voronoi_footprint", "pf_g_per_ton": 89.0,
        },
        {
            "hole_id": "H-incomplete", "X": 101.0, "Y": 201.0, "Kilos_Cargados_real": None,
            "pf_voronoi_bench_g_per_ton": float("nan"), "pf_voronoi_bench_status": "MISSING",
        },
    ]


def _audit_data(**blast):
    return _data(blast={"holes": _audit_holes(), "tolerance": 1.0, **blast})


def test_pozos_sheet_is_a_table_with_one_row_per_hole_and_literal_ids():
    book = _book(_audit_data())
    assert book.sheetnames == BASE_SHEETS + ["Tronadura", "Pozos"]
    ws = book["Pozos"]
    assert len(ws.tables) == 1
    table = next(iter(ws.tables.values()))
    assert table.autoFilter is not None and table.autoFilter.ref == table.ref
    assert ws.freeze_panes == "A2"
    rows = _table_rows(ws)
    assert [row["Pozo"] for row in rows] == ["007", "H-incomplete"]
    assert rows[0]["Etiqueta"] == "A-1"
    assert rows[0]["Collar X (m)"] == 100.0
    assert rows[0]["Largo (m)"] == 15.0
    assert rows[0]["Explosivo cargado (kg)"] == 500
    assert rows[0]["Explosivo"] == "Pirex-930"


def test_pozos_numeric_looking_ids_stay_text():
    holes = [{"id_pozo": "6447093", "X": 1.0, "Y": 2.0}, {"id_pozo": 12, "X": 1.0, "Y": 2.0}]
    rows = _table_rows(_book(_data(blast={"holes": holes}))["Pozos"])
    assert [row["Pozo"] for row in rows] == ["6447093", "12"]


def test_pozos_missing_values_are_sin_dato_never_zero():
    rows = _table_rows(_book(_audit_data())["Pozos"])
    complete, incomplete = rows
    for header in ("Collar Z (m)", "Largo (m)", "Explosivo cargado (kg)", "Explosivo",
                   "FC principal Voronoi banco (g/t)", "Fuente FC principal", "Etiqueta"):
        assert incomplete[header] == "sin dato", header
    assert incomplete["Estado FC principal"] == "MISSING"
    assert 0 not in [value for value in incomplete.values() if not isinstance(value, str)]
    assert None not in incomplete.values()
    assert complete["Inclinación (°)"] == 0


def test_pozos_carries_pf_value_status_and_source_columns():
    rows = _table_rows(_book(_audit_data())["Pozos"])
    assert rows[0]["FC principal Voronoi banco (g/t)"] == 95.5
    assert rows[0]["Estado FC principal"] == "VALID"
    assert rows[0]["Fuente FC principal"] == "voronoi_footprint"
    assert rows[0]["Estado explosivo"] == "UNVALIDATED_REFERENCE"
    assert rows[0]["Fuente explosivo"] == "Catálogo"
    assert rows[0]["FC 1000*Q/(B*S*L_vertical*rho) (g/t)"] == 89.0


def test_pozos_keeps_pf_principal_columns_when_no_hole_has_them():
    holes = [{"hole_id": "H-1", "X": 1.0, "Y": 2.0, "Len": 10.0}]
    rows = _table_rows(_book(_data(blast={"holes": holes}))["Pozos"])
    assert rows[0]["FC principal Voronoi banco (g/t)"] == "sin dato"
    assert rows[0]["Estado FC principal"] == "sin dato"
    assert "Pata X (m)" not in rows[0]


def test_pozos_absent_without_blast_data():
    assert "Pozos" not in _book(_data()).sheetnames
    assert "Pozos" not in _book(_data(blast={"holes": []})).sheetnames


def test_leeme_audit_block_lists_pf_formulas_and_consolidation():
    from core.blast_correlation import PF_DEFINITIONS

    data = _audit_data(
        consolidation_report={"holes_out": 2, "exact_copies_removed": 3, "deck_rows_merged": 1}
    )
    ws = _book(data)["Léeme"]
    text = _sheet_text(ws)
    assert "1000*Q/(A*H*rho)" in text
    for name, definition in PF_DEFINITIONS.items():
        assert _labelled_row(ws, f"{name} ({definition['unit']})")[1].value == definition["formula"]
    assert "copias eliminadas 3" in _labelled_row(ws, "Consolidación")[1].value
    assert "MISSING: 1" in _labelled_row(ws, "Estado FC principal")[1].value
    assert "VALID: 1" in _labelled_row(ws, "Estado FC principal")[1].value


def test_leeme_audit_block_states_missing_consolidation_report():
    assert "sin dato" in _labelled_row(_book(_audit_data())["Léeme"], "Consolidación")[1].value


def test_reimport_warning_only_for_legacy_blast_data():
    warning = "Datos de pozos importados con una versión anterior: reimportar"
    legacy = _audit_data()
    assert legacy.blast["data_status"] == "legacy_reimport_required"
    book = _book(legacy)
    assert warning in _sheet_text(book["Léeme"])
    assert warning in _sheet_text(book["Tronadura"])
    current = dataclasses.replace(legacy, blast={**legacy.blast, "data_status": "current"})
    book = _book(current)
    assert warning not in _sheet_text(book["Léeme"])
    assert warning not in _sheet_text(book["Tronadura"])


def test_leeme_states_design_achievement_coverage_and_missing_components():
    fx = _fixture()
    rows = [dict(row) for row in fx["rows"]]
    rows[0]["delta_toe"] = None
    data = _data(rows=rows)
    coverage = data.design_achievement["global"]["coverage"]
    details = data.design_achievement["global"]["rows"]
    assert details[0]["components_missing"]
    book = _book(data)
    ws = book["Léeme"]
    cobertura = _labelled_row(ws, "Cobertura")[1].value
    assert f"{coverage['n_evaluable']} de {coverage['n_rows']}" in cobertura
    missing = _labelled_row(ws, "Componentes faltantes")[1].value
    for component in details[0]["components_missing"]:
        assert component in missing
    bench_rows = _table_rows(book["Bancos"])
    assert bench_rows[0]["Componentes faltantes"] == ", ".join(details[0]["components_missing"])
    for row, detail in zip(bench_rows, details):
        assert (row["Componentes faltantes"] or "") == ", ".join(detail["components_missing"])


def test_bancos_effective_berm_columns_only_when_a_row_carries_them():
    fx = _fixture()
    rows = [dict(row, effective_berm=None, effective_berm_status=None) for row in fx["rows"]]
    headers, _cells = _table_cells(_book(_data(rows=rows))["Bancos"])
    assert "Berma efectiva (m)" not in headers
    assert "Estado berma efectiva" not in headers
    rows[0].update(effective_berm=1.0, effective_berm_status="NO CUMPLE")
    bench_rows = _table_rows(_book(_data(rows=rows))["Bancos"])
    assert bench_rows[0]["Berma efectiva (m)"] == 1.0
    assert bench_rows[0]["Estado berma efectiva"] == "NO CUMPLE"
    assert bench_rows[1]["Estado berma efectiva"] is None


def test_w43_excel_vocabulary_and_three_tiers():
    import core.web_excel_report as module
    book = _book(_data())
    text = _sheet_text(book["Resumen"])
    assert "Fuera de tolerancia" in text
    assert module._status_text("EXTRA") == "BANCO ADICIONAL"
    assert module._status_text("MISSING") == "NO CONSTRUIDO"
    assert "14/11/2026 10:00" in _sheet_text(book["Léeme"])
    headers = [column.header for column in module._BLAST_COLUMNS]
    assert "FC B×S×L (g/t)" in headers
    assert "FC principal (g/t)" in headers
    assert module._blast_records([{"pf_g_per_ton": 42}])[0]["pf_main"] == "sin dato"


def test_w43_blast_primary_missing_is_explicit():
    data = _data(blast={"holes": [{"pf_g_per_ton": 42.0}]})
    row = _table_rows(_book(data)["Tronadura"])[0]
    assert row["FC principal (g/t)"] == "sin dato"
    assert row["FC B×S×L (g/t)"] == 42.0
