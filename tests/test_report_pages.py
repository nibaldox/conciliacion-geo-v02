"""Tests for core.report_pages — landscape profile pages of the Word report."""
import io
from types import SimpleNamespace

import numpy as np
import pytest
from docx import Document
from PIL import Image
from docx.oxml.ns import qn
from docx.table import Table

import core.report_pages as report_pages
from core.report_charts import STATUS_COLORS
from core.report_data import BenchRow, ProfileSummary, ReportData, ReportFilters
from core.report_pages import (
    DETAIL_TABLE_FONT_PT,
    MIN_FONT_PT,
    TABLE_ROWS_ON_PAGE_MAX,
    ProfilePage,
    add_profile_pages_docx,
    profile_pages,
)

A4_LONG_MM = 297
A4_SHORT_MM = 210


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


def _entry(name, sector="Norte"):
    design_d = np.array([-30.0, -15.0, -10.0, 0.0, 5.0, 15.0, 20.0, 30.0])
    design_z = np.array([140.0, 140.0, 125.0, 125.0, 110.0, 110.0, 95.0, 95.0])
    topo_d = np.linspace(-30.0, 30.0, 61)
    topo_z = np.interp(topo_d, design_d, design_z) + 1.5 * np.sin(topo_d / 4.0)
    return {
        "section_name": name,
        "sector": sector,
        "view_window": (-10.0, 15.0, 102.5, 132.5),
        "warnings": [],
        "params_design": SimpleNamespace(benches=[_bench(2, 0.0, 125.0, 5.0, 110.0)]),
        "params_topo": SimpleNamespace(benches=[_bench(2, 0.5, 124.0, 5.5, 110.5)]),
        "profile_d": (design_d, design_z),
        "profile_t": (topo_d, topo_z),
    }


def _plan_section(name, index, sector="Norte"):
    return {
        "name": name,
        "origin": [1000.0 + 20.0 * index, 5000.0 + 2.0 * index],
        "azimuth": 20.0,
        "length": 40.0,
        "length_up": 20.0,
        "length_down": 20.0,
        "sector": sector,
    }


def _row(section, sector="Norte", bench_num=2, row_type="MATCH", worst="CUMPLE", **over):
    values = dict(
        section=section,
        sector=sector,
        level="3110",
        bench_num=bench_num,
        type=row_type,
        height_design=15.0,
        height_real=14.35,
        height_dev=-0.65,
        angle_design=70.4,
        angle_real=65.0,
        angle_dev=-5.4,
        berm_design=12.4,
        berm_real=10.99,
        berm_dev=None,
        height_status="CUMPLE",
        angle_status="FUERA DE TOLERANCIA",
        berm_status="CUMPLE",
        spill_width=None,
        effective_berm=None,
        effective_berm_status=None,
        worst_status=worst,
        status_label={"CUMPLE": "CUMPLE", "NO_CUMPLE": "NO CUMPLE"}.get(worst, "SIN EVALUAR"),
        level_nominal="3110",
        design_below_min=False,
    )
    values.update(over)
    return BenchRow(**values)


def _missing_row(section, sector="Norte", bench_num=3):
    return _row(
        section, sector, bench_num, "MISSING", "NO_CUMPLE",
        height_real=None, height_dev=None, angle_real=None, angle_dev=None,
        berm_real=None, height_status=None, angle_status=None, berm_status=None,
        status_label="NO CONSTRUIDO",
    )


def _extra_row(section, sector="Norte"):
    return _row(
        section, sector, 999, "EXTRA", "NO_CUMPLE",
        height_design=None, height_dev=None, angle_design=None, angle_dev=None,
        berm_design=None, height_status=None, angle_status=None, berm_status=None,
        status_label="BANCO ADICIONAL",
    )


def _names(n, start=1):
    return [f"S-{i:02d}" for i in range(start, start + n)]


def _data(
    names=None,
    *,
    sectors=None,
    rows=None,
    plan_names=None,
    with_plan=True,
    statuses=None,
    filters=None,
):
    names = list(names if names is not None else _names(6))
    sectors = dict(sectors or {})
    statuses = dict(statuses or {})
    sector_of = lambda name: sectors.get(name, "Norte")
    if rows is None:
        rows = [_row(name, sector_of(name), worst=statuses.get(name, "CUMPLE")) for name in names]
    plan_names = list(plan_names if plan_names is not None else names)
    plan_inputs = None
    if with_plan:
        plan_inputs = {
            "sections": [
                _plan_section(name, index, sector_of(name))
                for index, name in enumerate(plan_names)
            ]
        }
    profiles = tuple(
        ProfileSummary(
            section=name, sector=sector_of(name),
            worst_status=statuses.get(name, "CUMPLE"),
            weighted_score=None, n_match=1, n_missing=0, n_extra=0,
        )
        for name in sorted(names)
    )
    return ReportData(
        meta={},
        tolerances={},
        filters=filters or ReportFilters(),
        rows=tuple(rows),
        profiles=profiles,
        profile_counts={},
        global_weighted_score=None,
        parameters=(),
        design_achievement=None,
        top_deviations=(),
        depth=None,
        counts={},
        section_geometry=tuple(_entry(name, sector_of(name)) for name in names),
        plan_inputs=plan_inputs,
    )


class TestProfilePages:
    def test_thirteen_sections_make_pages_of_six_six_one(self):
        pages = profile_pages(_data(_names(13)))
        assert [len(page.sections) for page in pages] == [6, 6, 1]
        assert all(isinstance(page, ProfilePage) for page in pages)
        assert [name for page in pages for name in page.sections] == _names(13)

    def test_two_sectors_never_share_a_page(self):
        names = _names(9)
        sectors = {name: "Sur" for name in names[7:]}
        pages = profile_pages(_data(names, sectors=sectors))
        assert [(page.sector, len(page.sections)) for page in pages] == [
            ("Norte", 6), ("Norte", 1), ("Sur", 2),
        ]

    def test_sector_order_is_first_appearance_in_defined_order(self):
        names = _names(4)
        sectors = {"S-01": "Sur", "S-02": "Norte", "S-03": "Sur", "S-04": "Norte"}
        pages = profile_pages(_data(names, sectors=sectors))
        assert [(page.sector, page.sections) for page in pages] == [
            ("Sur", ("S-01", "S-03")), ("Norte", ("S-02", "S-04")),
        ]

    def test_sections_follow_plan_order_not_geometry_order(self):
        geometry_order = ["S-03", "S-01", "S-02"]
        pages = profile_pages(_data(geometry_order, plan_names=["S-02", "S-03", "S-01"]))
        assert pages[0].sections == ("S-02", "S-03", "S-01")

    def test_without_plan_inputs_geometry_order_is_used(self):
        pages = profile_pages(_data(["S-03", "S-01", "S-02"], with_plan=False))
        assert pages[0].sections == ("S-03", "S-01", "S-02")

    def test_plan_sections_may_be_objects(self):
        data = _data(["S-02", "S-01"])
        objects = [SimpleNamespace(**section) for section in data.plan_inputs["sections"]]
        data = _replace(data, plan_inputs={"sections": list(reversed(objects))})
        assert profile_pages(data)[0].sections == ("S-01", "S-02")

    def test_filtered_out_sections_are_absent(self):
        pages = profile_pages(_data(["S-02", "S-04"], plan_names=_names(5)))
        assert [page.sections for page in pages] == [("S-02", "S-04")]

    def test_table_rows_are_dicts_in_section_then_bench_order(self):
        rows = [
            _row("S-02", bench_num=2),
            _missing_row("S-01", bench_num=3),
            _row("S-01", bench_num=2),
            _extra_row("S-01"),
        ]
        page = profile_pages(_data(["S-01", "S-02"], rows=rows))[0]
        assert all(isinstance(row, dict) for row in page.table_rows)
        assert [(row["section"], row["type"], row["bench_num"]) for row in page.table_rows] == [
            ("S-01", "MATCH", 2), ("S-01", "MISSING", 3), ("S-01", "EXTRA", 999),
            ("S-02", "MATCH", 2),
        ]
        assert {row["level_nominal"] for row in page.table_rows} == {"3110"}

    def test_rows_of_other_sectors_and_pages_are_excluded(self):
        names = _names(7)
        rows = [_row(name) for name in names] + [_row("S-01", "Sur")]
        pages = profile_pages(_data(names, rows=rows))
        assert [row["section"] for row in pages[0].table_rows] == names[:6]
        assert [row["section"] for row in pages[1].table_rows] == names[6:]

    def test_table_moves_to_next_page_above_eight_rows(self):
        assert TABLE_ROWS_ON_PAGE_MAX == 8
        names = _names(6)
        eight = [_row(name) for name in names] + [_missing_row("S-01"), _extra_row("S-02")]
        nine = eight + [_extra_row("S-03")]
        assert profile_pages(_data(names, rows=eight))[0].table_on_next_page is False
        assert profile_pages(_data(names, rows=nine))[0].table_on_next_page is True

    def test_per_page_is_configurable(self):
        pages = profile_pages(_data(_names(5)), per_page=2)
        assert [len(page.sections) for page in pages] == [2, 2, 1]

    def test_no_geometry_gives_no_pages(self):
        assert profile_pages(_data([])) == ()

    def test_invalid_per_page_is_rejected(self):
        with pytest.raises(ValueError):
            profile_pages(_data(_names(2)), per_page=0)


def _replace(data, **changes):
    from dataclasses import replace
    return replace(data, **changes)


def _pictures(element):
    out = []
    for doc_pr in element.iter(qn("wp:docPr")):
        out.append(doc_pr.get("descr") or "")
    return out


def _section_blocks(doc):
    return [list(section.iter_inner_content()) for section in doc.sections]


def _section_pictures(blocks):
    return [descr for block in blocks for descr in _pictures(block._element)]


def _detail_tables(blocks):
    return [
        block for block in blocks
        if isinstance(block, Table) and block.rows[0].cells[0].text == "Sección"
    ]


def _section_text(blocks):
    texts = []
    for block in blocks:
        if isinstance(block, Table):
            continue
        texts.append(block.text)
    return texts


def _is_landscape_a4(section):
    return (
        round(section.page_width.mm) == A4_LONG_MM
        and round(section.page_height.mm) == A4_SHORT_MM
        and section.orientation is not None
        and section.orientation == 1
    )


def _cell_fill(cell):
    tc_pr = cell._tc.tcPr
    shd = tc_pr.find(qn("w:shd")) if tc_pr is not None else None
    return None if shd is None else shd.get(qn("w:fill"))


def _build(data, **kwargs):
    doc = Document()
    doc.add_paragraph("Antes")
    add_profile_pages_docx(doc, data, **kwargs)
    return doc


def _media_blobs(doc):
    return [
        part.blob for part in doc.part.package.iter_parts()
        if str(part.partname).startswith("/word/media/")
    ]


def _relief_shade():
    rng = np.random.default_rng(7)
    grid_y, grid_x = np.mgrid[0:160, 0:240]
    relief = 0.5 + 0.25 * np.sin(grid_x / 9.0) * np.cos(grid_y / 13.0)
    relief = np.clip(relief + rng.normal(0.0, 0.06, relief.shape), 0.0, 1.0)
    return relief, (900.0, 1300.0, 4900.0, 5150.0)


def _two_sector_data():
    names = _names(9)
    sectors = {name: "Sur" for name in names[7:]}
    return _data(names, sectors=sectors, filters=ReportFilters(levels=("3110",)))


def _headings(doc):
    return [
        text for blocks in _section_blocks(doc) for text in _section_text(blocks)
        if text.startswith("Perfiles — ")
    ]


class TestAddProfilePagesDocx:
    def test_each_profile_page_is_a_landscape_a4_section(self):
        doc = _build(_data(_names(7)))
        sections = list(doc.sections)
        assert len(sections) == 4
        assert not _is_landscape_a4(sections[0])
        assert _is_landscape_a4(sections[1]) and _is_landscape_a4(sections[2])
        assert sections[1].page_width > sections[1].page_height
        assert sections[1].left_margin.cm == pytest.approx(1.2, abs=0.01)
        assert sections[1].top_margin.cm == pytest.approx(1.2, abs=0.01)

    def test_document_ends_in_a_new_portrait_a4_section(self):
        doc = _build(_data(_names(7)))
        last = doc.sections[-1]
        assert round(last.page_width.mm) == A4_SHORT_MM
        assert round(last.page_height.mm) == A4_LONG_MM
        assert last.orientation == 0
        assert last.left_margin == doc.sections[0].left_margin
        assert list(last.iter_inner_content()) == []

    def test_text_added_afterwards_lands_in_the_portrait_section(self):
        doc = _build(_data(_names(2)))
        doc.add_paragraph("Después")
        assert _section_text(_section_blocks(doc)[-1]) == ["Después"]

    def test_each_page_has_its_profile_pictures_and_one_locator(self):
        blocks = _section_blocks(_build(_data(_names(7))))
        first, second = _section_pictures(blocks[1]), _section_pictures(blocks[2])
        assert [d for d in first if d.startswith("Perfil ")] == [
            f"Perfil {name}" for name in _names(6)
        ]
        assert [d for d in first if d.startswith("Mapa de ubicación")] == ["Mapa de ubicación"]
        assert len(first) == 7
        assert [d for d in second if d.startswith("Perfil ")] == ["Perfil S-07"]
        assert len(second) == 2
        assert _section_pictures(blocks[0]) == [] and _section_pictures(blocks[3]) == []

    def test_profile_grid_has_three_columns_and_two_rows_without_borders(self):
        blocks = _section_blocks(_build(_data(_names(6))))[1]
        grid = next(b for b in blocks if isinstance(b, Table) and _pictures(b._element))
        assert len(grid.rows) == 2
        per_row = [
            [len(_pictures(tc)) for tc in row._tr.findall(qn("w:tc"))] for row in grid.rows
        ]
        assert per_row[0][:3] == [1, 1, 1] and per_row[1][:3] == [1, 1, 1]
        borders = grid._tbl.tblPr.find(qn("w:tblBorders"))
        assert borders is not None
        assert {edge.get(qn("w:val")) for edge in borders} == {"nil"}

    def test_exactly_one_detail_table_per_page_with_header_and_rows(self):
        rows = [_row(name) for name in _names(7)] + [_missing_row("S-02")]
        blocks = _section_blocks(_build(_data(_names(7), rows=rows)))
        first, second = _detail_tables(blocks[1]), _detail_tables(blocks[2])
        assert len(first) == 1 and len(second) == 1
        table = first[0]
        groups = list(dict.fromkeys(cell.text for cell in table.rows[0].cells))
        assert groups == [
            "Sección", "Banco", "Tipo", "Cota nominal (m)", "Altura (m)", "Ángulo (°)",
            "Berma (m)", "Estado del banco",
        ]
        subs = [cell.text for cell in table.rows[1].cells][4:16]
        assert subs == [
            "dis.", "real", "Δ", "est.", "dis.", "real", "Δ", "est.",
            "dis.", "real", "est.", "aviso",
        ]
        assert len(table.rows) == 2 + 7
        assert len(second[0].rows) == 2 + 1
        assert [row.cells[0].text for row in table.rows[2:]] == [
            "S-01", "S-02", "S-02", "S-03", "S-04", "S-05", "S-06",
        ]

    def test_detail_row_values_use_spanish_format_and_short_status(self):
        blocks = _section_blocks(_build(_data(["S-01"])))
        cells = [cell.text for cell in _detail_tables(blocks[1])[0].rows[2].cells]
        assert cells == [
            "S-01", "B2", "Comparado", "3110",
            "15,00", "14,35", "−0,65", "Cumple",
            "70,4", "65,0", "−5,4", "Fuera",
            "12,40", "10,99", "Cumple", "",
            "Cumple",
        ]

    def test_missing_values_are_dashes_never_zero(self):
        rows = [_missing_row("S-01"), _extra_row("S-01")]
        blocks = _section_blocks(_build(_data(["S-01"], rows=rows, statuses={"S-01": "NO_CUMPLE"})))
        table = _detail_tables(blocks[1])[0]
        missing = [cell.text for cell in table.rows[2].cells]
        extra = [cell.text for cell in table.rows[3].cells]
        assert missing == [
            "S-01", "B3", "No construido", "3110",
            "15,00", "—", "—", "No construido", "70,4", "—", "—", "No construido", "12,40", "—", "No construido", "",
            "No construido",
        ]
        assert extra[1:3] == ["Adic.", "Adicional"]
        assert extra[4] == "—" and extra[5] == "14,35" and extra[6] == "—"
        assert [extra[i] for i in (7, 11, 14)] == ["Adicional"] * 3
        assert extra[-1] == "Banco adicional"
        assert "0" not in {text for text in missing + extra}

    def test_status_cells_are_shaded_with_the_status_palette(self):
        rows = [_row("S-01"), _row("S-02", worst="NO_CUMPLE", berm_status="NO CUMPLE")]
        blocks = _section_blocks(_build(_data(["S-01", "S-02"], rows=rows)))
        table = _detail_tables(blocks[1])[0]
        ok, bad = table.rows[2].cells, table.rows[3].cells
        assert _cell_fill(ok[-1]) == STATUS_COLORS["CUMPLE"].lstrip("#")
        assert _cell_fill(bad[-1]) == STATUS_COLORS["NO_CUMPLE"].lstrip("#")
        assert _cell_fill(ok[0]) != STATUS_COLORS["CUMPLE"].lstrip("#")
        angle_run = ok[11].paragraphs[0].runs[0]
        assert str(angle_run.font.color.rgb) == STATUS_COLORS["FUERA"].lstrip("#")
        berm_run = bad[14].paragraphs[0].runs[0]
        assert berm_run.text == "No cumple"
        assert str(berm_run.font.color.rgb) == STATUS_COLORS["NO_CUMPLE"].lstrip("#")

    def test_design_berm_below_minimum_is_flagged(self):
        rows = [_row("S-01", design_below_min=True, berm_design=1.95)]
        blocks = _section_blocks(_build(_data(["S-01"], rows=rows)))
        cells = [cell.text for cell in _detail_tables(blocks[1])[0].rows[2].cells]
        assert cells[12] == "1,95"
        assert cells[15] == "⚠ diseño < mín."

    def test_crest_and_toe_columns_appear_only_when_rows_carry_them(self):
        data = _data(["S-01"])
        plain = _detail_tables(_section_blocks(_build(data))[1])[0]
        assert "Cresta Δ (m)" not in [cell.text for cell in plain.rows[0].cells]
        rows = [_row("S-01", delta_crest=0.84, delta_toe=None)]
        rich = _detail_tables(_section_blocks(_build(_data(["S-01"], rows=rows)))[1])[0]
        header = [cell.text for cell in rich.rows[0].cells]
        assert header[16:18] == ["Cresta Δ (m)", "Pata Δ (m)"]
        cells = [cell.text for cell in rich.rows[2].cells]
        assert cells[16:18] == ["+0,84", "—"]
        assert cells[-1] == "Cumple"

    def test_legend_line_follows_the_table(self):
        blocks = _section_blocks(_build(_data(["S-01"])))[1]
        index = next(i for i, b in enumerate(blocks) if b in _detail_tables(blocks))
        legend = blocks[index + 1].text
        for token in ("dis. = diseño", "Δ = real − diseño", "est. = estado", "⚠ diseño < mín.", "— = sin dato"):
            assert token in legend

    def test_table_fonts_respect_the_agreed_sizes(self):
        assert DETAIL_TABLE_FONT_PT == 6.6 and MIN_FONT_PT == 5.6
        blocks = _section_blocks(_build(_data(["S-01"])))[1]
        table = _detail_tables(blocks)[0]
        sizes = {
            run.font.size.pt
            for row in table.rows for cell in row.cells
            for paragraph in cell.paragraphs for run in paragraph.runs
        }
        assert sizes and min(sizes) >= MIN_FONT_PT
        assert max(sizes) == pytest.approx(6.5)

    def test_every_run_of_a_page_is_at_least_the_minimum_font(self):
        doc = _build(_data(_names(2)))
        sizes = [
            int(sz.get(qn("w:val"))) / 2.0
            for sz in doc.element.body.iter(qn("w:sz"))
        ]
        assert sizes and min(s for s in sizes if s > 1.0) >= MIN_FONT_PT

    def test_heading_names_sector_level_and_page_number(self):
        names = _names(7)
        filters = ReportFilters(levels=("3110",))
        blocks = _section_blocks(_build(_data(names, filters=filters)))
        assert _section_text(blocks[1])[0] == "Perfiles — Sector Norte · cota 3110 · página 1 de 2"
        assert _section_text(blocks[2])[0] == "Perfiles — Sector Norte · cota 3110 · página 2 de 2"

    def test_heading_omits_empty_sector_and_unfiltered_level(self):
        names = _names(2)
        data = _data(names, sectors={name: "" for name in names})
        blocks = _section_blocks(_build(data))
        assert _section_text(blocks[1])[0] == "Perfiles — página 1 de 1"

    def test_heading_lists_two_selected_levels(self):
        filters = ReportFilters(levels_by_sector=(("Norte", ("3110", "3125")),))
        blocks = _section_blocks(_build(_data(_names(1), filters=filters)))
        assert _section_text(blocks[1])[0] == "Perfiles — Sector Norte · cotas 3125 y 3110 · página 1 de 1"

    def test_overflowing_table_goes_alone_to_the_following_landscape_section(self):
        names = _names(6)
        rows = [_row(name) for name in names] + [_missing_row(name) for name in names]
        doc = _build(_data(names, rows=rows))
        blocks = _section_blocks(doc)
        assert len(blocks) == 4
        assert _detail_tables(blocks[1]) == []
        assert len(_section_pictures(blocks[1])) == 7
        assert _is_landscape_a4(doc.sections[2])
        assert _section_pictures(blocks[2]) == []
        tables = _detail_tables(blocks[2])
        assert len(tables) == 1 and len(tables[0].rows) == 2 + 12
        assert _section_text(blocks[2])[0] == "Detalle de perfiles de la página 1"

    def test_profile_status_and_shade_reach_the_figures(self, monkeypatch):
        calls = {"profiles": [], "locator": []}
        real_profile, real_locator = report_pages.cropped_profile_png, report_pages.locator_map_png

        def fake_profile(entry, **kwargs):
            calls["profiles"].append((entry["section_name"], kwargs.get("status")))
            return real_profile(entry, **kwargs)

        def fake_locator(sections, highlighted, **kwargs):
            calls["locator"].append((len(sections), dict(highlighted), kwargs.get("shade")))
            return real_locator(sections, highlighted, **kwargs)

        monkeypatch.setattr(report_pages, "cropped_profile_png", fake_profile)
        monkeypatch.setattr(report_pages, "locator_map_png", fake_locator)
        shade = (np.full((4, 4), 0.5), (900.0, 1300.0, 4900.0, 5100.0))
        names = _names(3)
        data = _data(names, plan_names=_names(5), statuses={"S-02": "NO_CUMPLE"})
        _build(data, shade=shade)
        assert calls["profiles"] == [("S-01", "CUMPLE"), ("S-02", "NO_CUMPLE"), ("S-03", "CUMPLE")]
        count, highlighted, used_shade = calls["locator"][0]
        assert count == 5
        assert highlighted == {"S-01": "CUMPLE", "S-02": "NO_CUMPLE", "S-03": "CUMPLE"}
        assert used_shade is shade

    def test_same_section_name_in_another_sector_is_not_highlighted(self, monkeypatch):
        seen = []
        real_locator = report_pages.locator_map_png

        def fake_locator(sections, highlighted, **kwargs):
            seen.append(([s["name"] for s in sections], dict(highlighted)))
            return real_locator(sections, highlighted, **kwargs)

        monkeypatch.setattr(report_pages, "locator_map_png", fake_locator)
        data = _data(["S-01"], sectors={"S-01": "Norte"})
        sections = data.plan_inputs["sections"] + [_plan_section("S-01", 4, "Sur")]
        _build(_replace(data, plan_inputs={"sections": sections}))
        names, highlighted = seen[0]
        assert names.count("S-01") == 1 and len(names) == 2
        assert highlighted == {"S-01": "CUMPLE"}

    def test_plan_section_objects_are_accepted_by_the_locator(self):
        data = _data(_names(2))
        objects = [
            SimpleNamespace(**dict(section, origin=np.array(section["origin"])))
            for section in data.plan_inputs["sections"]
        ]
        blocks = _section_blocks(_build(_replace(data, plan_inputs={"sections": objects})))
        assert "Mapa de ubicación" in _section_pictures(blocks[1])

    def test_profile_without_geometry_shows_a_note_instead_of_a_picture(self):
        data = _data(_names(2))
        geometry = list(data.section_geometry)
        geometry[1] = dict(geometry[1], profile_d=(np.array([]), np.array([])),
                           profile_t=(np.array([]), np.array([])))
        doc = _build(_replace(data, section_geometry=tuple(geometry)))
        blocks = _section_blocks(doc)[1]
        assert [d for d in _section_pictures(blocks) if d.startswith("Perfil ")] == ["Perfil S-01"]
        grid = next(b for b in blocks if isinstance(b, Table) and _pictures(b._element))
        assert "S-02 — sin perfil" in grid.rows[0].cells[1].text

    def test_empty_cells_do_not_inherit_the_body_font_height(self):
        blocks = _section_blocks(_build(_data(["S-01"])))[1]
        table = _detail_tables(blocks)[0]
        for cell in table.rows[2].cells:
            mark = cell.paragraphs[0]._p.pPr.find(qn("w:rPr"))
            assert mark is not None
            assert int(mark.find(qn("w:sz")).get(qn("w:val"))) / 2.0 <= 6.5

    def test_profiles_grow_when_the_table_leaves_the_page(self, monkeypatch):
        heights = []
        real_profile = report_pages.cropped_profile_png

        def fake_profile(entry, **kwargs):
            heights.append(kwargs["height_in"])
            return real_profile(entry, **kwargs)

        monkeypatch.setattr(report_pages, "cropped_profile_png", fake_profile)
        names = _names(6)
        _build(_data(names))
        rows = [_row(name) for name in names] + [_missing_row(name) for name in names]
        _build(_data(names, rows=rows))
        assert len(set(heights[:6])) == 1 and len(set(heights[6:])) == 1
        assert heights[6] > heights[0]

    def test_no_pages_leaves_the_document_untouched(self):
        doc = _build(_data([]))
        assert len(doc.sections) == 1
        assert [p.text for p in doc.paragraphs] == ["Antes"]

    def test_returns_none(self):
        doc = Document()
        assert add_profile_pages_docx(doc, _data(_names(1))) is None

    def test_embedded_pictures_average_at_most_40_kb(self):
        doc = _build(_data(_names(6)), shade=_relief_shade())
        blobs = _media_blobs(doc)
        assert len(blobs) == 7
        assert all(blob.startswith(b"\x89PNG\r\n\x1a\n") for blob in blobs)
        assert sum(len(blob) for blob in blobs) / len(blobs) <= 40_000
        assert max(len(blob) for blob in blobs) <= 60_000

    def test_embedded_pictures_are_palette_png_at_the_rendered_size(self, monkeypatch):
        rendered = []
        real_profile, real_locator = report_pages.cropped_profile_png, report_pages.locator_map_png

        def fake_profile(entry, **kwargs):
            png = real_profile(entry, **kwargs)
            rendered.append(png)
            return png

        def fake_locator(sections, highlighted, **kwargs):
            png = real_locator(sections, highlighted, **kwargs)
            rendered.append(png)
            return png

        monkeypatch.setattr(report_pages, "cropped_profile_png", fake_profile)
        monkeypatch.setattr(report_pages, "locator_map_png", fake_locator)
        doc = _build(_data(_names(2)), shade=_relief_shade())
        embedded = [Image.open(io.BytesIO(blob)) for blob in _media_blobs(doc)]
        assert len(embedded) == 3
        assert {image.mode for image in embedded} == {"P"}
        assert sorted(image.size for image in embedded) == sorted(
            Image.open(io.BytesIO(png)).size for png in rendered
        )
        assert sum(len(blob) for blob in _media_blobs(doc)) < 0.6 * sum(len(png) for png in rendered)

    def test_compressed_pictures_keep_the_status_colours(self):
        data = _data(_names(1), statuses={"S-01": "NO_CUMPLE"})
        doc = _build(data)
        red = tuple(int(STATUS_COLORS["NO_CUMPLE"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        for blob in _media_blobs(doc):
            pixels = np.asarray(Image.open(io.BytesIO(blob)).convert("RGB")).reshape(-1, 3)
            distance = np.abs(pixels.astype(int) - np.array(red)).sum(axis=1)
            assert distance.min() <= 12

    def test_compression_failure_keeps_the_original_picture(self, monkeypatch):
        assert report_pages._compress_png(b"not a png") == b"not a png"

    def test_picture_box_is_unchanged_by_compression(self, monkeypatch):
        sizes = []
        real_profile = report_pages.cropped_profile_png

        def fake_profile(entry, **kwargs):
            png = real_profile(entry, **kwargs)
            sizes.append(Image.open(io.BytesIO(png)).size)
            return png

        monkeypatch.setattr(report_pages, "cropped_profile_png", fake_profile)
        doc = _build(_data(_names(1)))
        extents = [
            (inline.extent.cx, inline.extent.cy)
            for inline in doc.element.body.iter(qn("wp:inline"))
        ]
        assert len(extents) == 2
        width_cm, height_cm = extents[0][0] / 360000.0, extents[0][1] / 360000.0
        assert width_cm <= 6.6 + 1e-6 and height_cm <= 6.1 + 1e-6
        assert width_cm == pytest.approx(6.6, abs=0.01) or height_cm == pytest.approx(6.1, abs=0.01)
        assert width_cm / height_cm == pytest.approx(sizes[0][0] / sizes[0][1], rel=1e-3)

    def test_sectors_keyword_adds_only_those_sectors(self):
        doc = _build(_two_sector_data(), sectors=["Norte"])
        assert _headings(doc) == [
            "Perfiles — Sector Norte · cota 3110 · página 1 de 2",
            "Perfiles — Sector Norte · cota 3110 · página 2 de 2",
        ]
        assert len(doc.sections) == 4
        pictures = [d for blocks in _section_blocks(doc) for d in _section_pictures(blocks)]
        assert [d for d in pictures if d.startswith("Perfil ")] == [
            f"Perfil {name}" for name in _names(7)
        ]

    def test_sectors_keyword_numbers_pages_per_sector(self):
        doc = _build(_two_sector_data(), sectors=["Sur"])
        assert _headings(doc) == ["Perfiles — Sector Sur · cota 3110 · página 1 de 1"]
        pictures = [d for blocks in _section_blocks(doc) for d in _section_pictures(blocks)]
        assert [d for d in pictures if d.startswith("Perfil ")] == ["Perfil S-08", "Perfil S-09"]

    def test_sectors_none_keeps_every_sector(self):
        every = _headings(_build(_two_sector_data()))
        assert every == _headings(_build(_two_sector_data(), sectors=None))
        assert len(every) == 3

    def test_one_call_per_sector_matches_a_single_call(self):
        data = _two_sector_data()
        doc = Document()
        for sector in ("Norte", "Sur"):
            doc.add_paragraph(f"Capítulo {sector}")
            add_profile_pages_docx(doc, data, sectors=[sector])
        assert _headings(doc) == _headings(_build(data))
        blocks = _section_blocks(doc)
        assert _section_text(blocks[3])[0] == "Capítulo Sur"
        last = doc.sections[-1]
        assert round(last.page_width.mm) == A4_SHORT_MM and last.orientation == 0

    def test_sector_names_are_matched_after_trimming(self):
        doc = _build(_two_sector_data(), sectors=(" Sur ",))
        assert _headings(doc) == ["Perfiles — Sector Sur · cota 3110 · página 1 de 1"]

    def test_sections_without_sector_are_selected_by_the_empty_name(self):
        names = _names(3)
        data = _data(names, sectors={"S-01": "", "S-02": "", "S-03": "Sur"})
        doc = _build(data, sectors=[""])
        pictures = [d for blocks in _section_blocks(doc) for d in _section_pictures(blocks)]
        assert [d for d in pictures if d.startswith("Perfil ")] == ["Perfil S-01", "Perfil S-02"]

    def test_unknown_or_empty_sector_selection_leaves_the_document_untouched(self):
        for selection in (["Oeste"], []):
            doc = _build(_two_sector_data(), sectors=selection)
            assert len(doc.sections) == 1
            assert [p.text for p in doc.paragraphs] == ["Antes"]
