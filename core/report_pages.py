"""Landscape profile pages of the Word report (contract C9).

``profile_pages`` plans the pages (per sector, in the defined section order,
six profiles per page) and ``add_profile_pages_docx`` writes them: one A4
landscape section per page with a 3×2 grid of cropped profiles, the locator
mini-plan and one detail table at the bottom.
"""
from __future__ import annotations

import io
import math
import struct
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping, Optional, Sequence

from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Mm, Pt, RGBColor

from core.report_charts import (
    STATUS_COLORS,
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_LABELS_ES,
    STATUS_NO_CUMPLE,
    STATUS_UNKNOWN,
)
from core.report_data import ReportData, parse_bench_status
from core.report_figures_profile import (
    OTHER_SECTION_COLOR,
    Shade,
    cropped_profile_png,
    locator_map_png,
)

PROFILES_PER_PAGE = 6
TABLE_ROWS_ON_PAGE_MAX = 8
GRID_COLUMNS = 3
DETAIL_TABLE_FONT_PT = 6.6
MIN_FONT_PT = 5.6

A4_LONG_MM = 297.0
A4_SHORT_MM = 210.0
LANDSCAPE_MARGIN_CM = 1.2
USABLE_WIDTH_CM = A4_LONG_MM / 10.0 - 2.0 * LANDSCAPE_MARGIN_CM

LOCATOR_DESCRIPTION = "Mapa de ubicación"
PROFILE_DESCRIPTION_PREFIX = "Perfil "
BELOW_MIN_MARK = "⚠ diseño < mín."
DASH = "—"

_HEADING_PT = 10.0
_SUBHEADING_PT = 7.5
_NOTE_PT = 6.0
_PROFILE_CELL_CM = 6.75
_PROFILE_BOX_CM = (6.6, 6.1)
_PROFILE_BOX_ALONE_CM = (6.6, 7.6)
_LOCATOR_CELL_CM = USABLE_WIDTH_CM - GRID_COLUMNS * _PROFILE_CELL_CM
_LOCATOR_BOX_CM = (_LOCATOR_CELL_CM - 0.2, 5.6)
_CM_PER_INCH = 2.54
_FIGURE_DPI = 170
_ROW_HEIGHT_CM = 0.42
_HEADER_FILL = "1F3864"
_SUBHEADER_FILL = "DCE6F1"
_ZEBRA_FILL = "F3F6FA"
_TEXT_HEX = "1F2937"
_MUTED_HEX = "5B6573"
_BORDER_HEX = "BFC7D1"
_WHITE_HEX = "FFFFFF"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PALETTE_COLORS = 256

_SHORT_STATUS = {
    STATUS_CUMPLE: "Cumple",
    STATUS_FUERA: "Fuera",
    STATUS_NO_CUMPLE: "No cumple",
    STATUS_UNKNOWN: "Sin evaluar",
}
_TYPE_LABELS = {"MATCH": "Comparado", "MISSING": "No construido", "EXTRA": "Adicional"}
_BENCH_STATUS_BY_TYPE = {"MISSING": "No construido", "EXTRA": "Banco adicional"}
_CREST_TOE_KEYS = ("delta_crest", "delta_toe")

_LEFT = WD_ALIGN_PARAGRAPH.LEFT
_CENTER = WD_ALIGN_PARAGRAPH.CENTER


@dataclass(frozen=True)
class ProfilePage:
    """One landscape page of profiles: its sector, sections and detail rows."""

    sector: str
    sections: tuple[str, ...]
    table_rows: tuple[dict, ...]
    table_on_next_page: bool


@dataclass(frozen=True)
class _Column:
    group: str
    label: str
    weight: float
    kind: str
    key: str = ""
    decimals: int = 2


def _sector_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text == "None" else text


def _field(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _plan_section_items(data: ReportData) -> list:
    plan_inputs = data.plan_inputs
    raw = plan_inputs.get("sections") if isinstance(plan_inputs, Mapping) else None
    return [item for item in (raw or ()) if _field(item, "name") is not None]


def _ordered_entries(data: ReportData) -> list[tuple[str, str, Mapping[str, Any]]]:
    entries: list[tuple[str, str, Mapping[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for entry in data.section_geometry or ():
        if not isinstance(entry, Mapping) or entry.get("section_name") is None:
            continue
        identity = (str(entry["section_name"]), _sector_text(entry.get("sector")))
        if identity in seen:
            continue
        seen.add(identity)
        entries.append((identity[0], identity[1], entry))

    by_pair: dict[tuple[str, str], int] = {}
    by_name: dict[str, int] = {}
    plan = _plan_section_items(data)
    for index, item in enumerate(plan):
        name = str(_field(item, "name"))
        by_pair.setdefault((name, _sector_text(_field(item, "sector"))), index)
        by_name.setdefault(name, index)
    if not plan:
        return entries

    def rank(indexed: tuple[int, tuple[str, str, Mapping[str, Any]]]) -> tuple[int, int]:
        position, (name, sector, _entry) = indexed
        if (name, sector) in by_pair:
            return by_pair[(name, sector)], position
        return by_name.get(name, len(plan)), position

    return [item for _position, item in sorted(enumerate(entries), key=rank)]


def _row_dict(row: Any) -> dict:
    if is_dataclass(row) and not isinstance(row, type):
        return asdict(row)
    return dict(row)


def _bench_order(row: Mapping[str, Any]) -> float:
    number = _finite(row.get("bench_num"))
    return math.inf if number is None else number


def _rows_by_identity(
    data: ReportData, identities: Sequence[tuple[str, str]]
) -> dict[tuple[str, str], list[dict]]:
    name_count: dict[str, int] = {}
    for name, _sector in identities:
        name_count[name] = name_count.get(name, 0) + 1
    by_name = {name: sector for name, sector in identities if name_count[name] == 1}
    known = set(identities)
    grouped: dict[tuple[str, str], list[dict]] = {identity: [] for identity in identities}
    for row in data.rows or ():
        values = _row_dict(row)
        name = str(values.get("section", ""))
        sector = _sector_text(values.get("sector"))
        identity = (name, sector)
        if identity not in known:
            if name not in by_name or (sector and by_name[name]):
                continue
            identity = (name, by_name[name])
        grouped[identity].append(values)
    for rows in grouped.values():
        rows.sort(key=_bench_order)
    return grouped


def profile_pages(data: ReportData, *, per_page: int = PROFILES_PER_PAGE) -> tuple[ProfilePage, ...]:
    """Plan the profile pages of ``data``.

    Sectors appear in the order of their first section in the defined section
    order (``plan_inputs["sections"]``, else ``section_geometry``); inside a
    sector the sections keep that order and are cut in chunks of ``per_page``.
    Only sections present in ``section_geometry`` are paged. ``table_rows``
    are the ``data.rows`` of the page as dicts (section order, then bench
    number). The table moves to the next page when it has more than eight
    rows.
    """
    if per_page < 1:
        raise ValueError("per_page must be at least 1")
    entries = _ordered_entries(data)
    if not entries:
        return ()
    rows = _rows_by_identity(data, [(name, sector) for name, sector, _entry in entries])
    by_sector: dict[str, list[str]] = {}
    for name, sector, _entry in entries:
        by_sector.setdefault(sector, []).append(name)
    pages: list[ProfilePage] = []
    for sector, names in by_sector.items():
        for start in range(0, len(names), per_page):
            chunk = tuple(names[start:start + per_page])
            table_rows = tuple(row for name in chunk for row in rows[(name, sector)])
            pages.append(
                ProfilePage(
                    sector=sector,
                    sections=chunk,
                    table_rows=table_rows,
                    table_on_next_page=len(table_rows) > TABLE_ROWS_ON_PAGE_MAX,
                )
            )
    return tuple(pages)


def _docx_pt(size: float) -> Pt:
    return Pt(max(round(size * 2.0) / 2.0, math.ceil(MIN_FONT_PT * 2.0) / 2.0))


def _hex(color: str) -> str:
    return color.lstrip("#").upper()


def _compact(paragraph, align=None) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1.0
    if align is not None:
        paragraph.alignment = align
    _set_mark_size(paragraph, _NOTE_PT)


def _set_mark_size(paragraph, size: float) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    for existing in p_pr.findall(qn("w:rPr")):
        p_pr.remove(existing)
    run_pr = OxmlElement("w:rPr")
    mark = OxmlElement("w:sz")
    mark.set(qn("w:val"), str(int(round(_docx_pt(size).pt * 2))))
    run_pr.append(mark)
    section_pr = p_pr.find(qn("w:sectPr"))
    if section_pr is not None:
        section_pr.addprevious(run_pr)
    else:
        p_pr.append(run_pr)


def _add_run(paragraph, text: str, size: float, *, bold: bool = False,
             italic: bool = False, color: str = _TEXT_HEX):
    run = paragraph.add_run(text)
    run.font.size = _docx_pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor.from_string(_hex(color))
    return run


def _cell_text(cell, text: str, size: float, *, align=_CENTER, **style):
    paragraph = cell.paragraphs[0]
    _compact(paragraph, align)
    return _add_run(paragraph, text, size, **style) if text else None


def _set_cell_fill(cell, fill_hex: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for existing in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(existing)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), _hex(fill_hex))
    v_align = tc_pr.find(qn("w:vAlign"))
    if v_align is not None:
        v_align.addprevious(shd)
    else:
        tc_pr.append(shd)


def _insert_table_property(table, element) -> None:
    tbl_pr = table._tbl.tblPr
    for existing in tbl_pr.findall(element.tag):
        tbl_pr.remove(existing)
    followers = ("w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption", "w:tblDescription")
    order = ("w:tblBorders", "w:shd") + followers
    later = order[order.index(_prefixed(element.tag)) + 1:]
    for tag in later:
        anchor = tbl_pr.find(qn(tag))
        if anchor is not None:
            anchor.addprevious(element)
            return
    tbl_pr.append(element)


def _prefixed(tag: str) -> str:
    return "w:" + tag.rsplit("}", 1)[-1]


def _set_table_borders(table, edges: Mapping[str, Optional[str]]) -> None:
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        color = edges.get(edge)
        if color is None:
            element.set(qn("w:val"), "nil")
        else:
            element.set(qn("w:val"), "single")
            element.set(qn("w:sz"), "4")
            element.set(qn("w:space"), "0")
            element.set(qn("w:color"), color)
        borders.append(element)
    _insert_table_property(table, borders)


def _set_cell_margins(table, horizontal_twips: int, vertical_twips: int = 0) -> None:
    margins = OxmlElement("w:tblCellMar")
    for edge, value in (("top", vertical_twips), ("left", horizontal_twips),
                        ("bottom", vertical_twips), ("right", horizontal_twips)):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")
        margins.append(element)
    _insert_table_property(table, margins)


def _set_column_widths(table, widths_cm: Sequence[float]) -> None:
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, width in enumerate(widths_cm):
        table.columns[index].width = Cm(width)
    for row in table.rows:
        for index, width in enumerate(widths_cm):
            row.cells[index].width = Cm(width)


def _new_table(doc, rows: int, widths_cm: Sequence[float]):
    table = doc.add_table(rows=rows, cols=len(widths_cm))
    _set_column_widths(table, widths_cm)
    return table


def _png_size(png: bytes) -> Optional[tuple[int, int]]:
    if len(png) < 24 or not png.startswith(_PNG_SIGNATURE):
        return None
    width, height = struct.unpack(">II", png[16:24])
    return (width, height) if width > 0 and height > 0 else None


def _compress_png(png: bytes, colors: int = _PALETTE_COLORS) -> bytes:
    """Re-encode a figure PNG as an optimized palette image of the same pixel size.

    Profiles and locators are flat-coloured line art over a faint relief, so
    a coverage-based palette shows no difference at 100 % while cutting the
    embedded size by more than half. The original bytes are returned when the
    image cannot be re-encoded or would not get smaller.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as image:
            image.load()
            flat = Image.new("RGB", image.size, (255, 255, 255))
            rgba = image.convert("RGBA")
            flat.paste(rgba, mask=rgba.getchannel("A"))
            quantized = flat.quantize(
                colors=colors, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE,
            )
            output = io.BytesIO()
            quantized.save(output, format="PNG", optimize=True)
    except Exception:
        return png
    compressed = output.getvalue()
    return compressed if len(compressed) < len(png) else png


def _add_picture(paragraph, png: bytes, box_cm: tuple[float, float], description: str) -> None:
    png = _compress_png(png)
    size = _png_size(png)
    aspect = size[0] / size[1] if size else box_cm[0] / box_cm[1]
    width = min(box_cm[0], box_cm[1] * aspect)
    run = paragraph.add_run()
    run.add_picture(io.BytesIO(png), width=Cm(width), height=Cm(width / aspect))
    for doc_pr in run._r.iter(qn("wp:docPr")):
        doc_pr.set("descr", description)
        doc_pr.set("title", description)


def _landscape_section(doc):
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    _shrink_section_break(doc)
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Mm(A4_LONG_MM)
    section.page_height = Mm(A4_SHORT_MM)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Cm(LANDSCAPE_MARGIN_CM))
    return section


def _portrait_section(doc, margins: Mapping[str, Any]):
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    _shrink_section_break(doc)
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Mm(A4_SHORT_MM)
    section.page_height = Mm(A4_LONG_MM)
    for side, value in margins.items():
        if value is not None:
            setattr(section, side, value)
    return section


def _shrink_section_break(doc) -> None:
    body = doc.element.body
    paragraphs = body.findall(qn("w:p"))
    if not paragraphs:
        return
    carrier = paragraphs[-1]
    p_pr = carrier.find(qn("w:pPr"))
    if p_pr is None or p_pr.find(qn("w:sectPr")) is None or carrier.findall(qn("w:r")):
        return
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), "20")
    spacing.set(qn("w:lineRule"), "exact")
    for existing in p_pr.findall(qn("w:spacing")):
        p_pr.remove(existing)
    p_pr.find(qn("w:sectPr")).addprevious(spacing)
    run_pr = OxmlElement("w:rPr")
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "2")
    run_pr.append(size)
    p_pr.find(qn("w:sectPr")).addprevious(run_pr)


def _level_text(levels: Sequence[str]) -> str:
    labels = list(dict.fromkeys(str(level) for level in levels if str(level).strip()))
    if not labels:
        return ""

    def rank(label: str) -> tuple[int, float, str]:
        number = _finite(label)
        return (0, -number, label) if number is not None else (1, 0.0, label)

    labels.sort(key=rank)
    if len(labels) == 1:
        return f"cota {labels[0]}"
    return f"cotas {', '.join(labels[:-1])} y {labels[-1]}"


def _page_heading(data: ReportData, page: ProfilePage, number: int, total: int) -> str:
    parts = []
    if page.sector:
        parts.append(f"Sector {page.sector}")
    levels = _level_text(data.filters.levels_for(page.sector)) if data.filters else ""
    if levels:
        parts.append(levels)
    parts.append(f"página {number} de {total}")
    return "Perfiles — " + " · ".join(parts)


def _profile_statuses(data: ReportData) -> tuple[dict[tuple[str, str], str], dict[str, Optional[str]]]:
    by_pair: dict[tuple[str, str], str] = {}
    by_name: dict[str, Optional[str]] = {}
    for profile in data.profiles or ():
        name = str(_field(profile, "section"))
        status = _field(profile, "worst_status")
        by_pair[(_sector_text(_field(profile, "sector")), name)] = status
        by_name[name] = None if name in by_name else status
    return by_pair, by_name


def _page_statuses(data: ReportData, page: ProfilePage) -> dict[str, Optional[str]]:
    by_pair, by_name = _profile_statuses(data)
    return {
        name: by_pair.get((page.sector, name), by_name.get(name))
        for name in page.sections
    }


def _locator_sections(data: ReportData, page: ProfilePage) -> list[dict]:
    on_page = set(page.sections)
    sections: list[dict] = []
    for item in _plan_section_items(data):
        section: dict[str, Any] = {}
        for key in ("polyline", "origin", "azimuth", "length", "length_up", "length_down",
                    "x0", "y0", "x1", "y1"):
            value = _field(item, key)
            if value is not None:
                section[key] = value
        name = str(_field(item, "name"))
        sector = _sector_text(_field(item, "sector"))
        section["sector"] = sector
        section["name"] = "" if name in on_page and sector != page.sector else name
        sections.append(section)
    return sections


def _add_heading(doc, text: str) -> None:
    paragraph = doc.add_paragraph()
    _compact(paragraph, _LEFT)
    paragraph.paragraph_format.space_after = Pt(3)
    _add_run(paragraph, text, _HEADING_PT, bold=True, color=_HEADER_FILL)


def _legend_line(cell, parts: Sequence[tuple[str, str, bool]]) -> None:
    paragraph = cell.add_paragraph()
    _compact(paragraph, _LEFT)
    for text, color, bold in parts:
        _add_run(paragraph, text, _NOTE_PT, bold=bold, color=color)


def _fill_locator_cell(cell, data: ReportData, page: ProfilePage,
                       statuses: Mapping[str, Optional[str]], shade: Optional[Shade]) -> None:
    _cell_text(cell, "Ubicación de los perfiles de esta página", _SUBHEADING_PT,
               align=_LEFT, bold=True)
    highlighted = {name: status or STATUS_UNKNOWN for name, status in statuses.items()}
    box = _LOCATOR_BOX_CM
    png = locator_map_png(
        _locator_sections(data, page), highlighted, shade=shade,
        width_in=box[0] / _CM_PER_INCH, height_in=box[1] / _CM_PER_INCH, dpi=_FIGURE_DPI,
    )
    paragraph = cell.add_paragraph()
    _compact(paragraph, _CENTER)
    if png:
        _add_picture(paragraph, png, box, LOCATOR_DESCRIPTION)
    else:
        _add_run(paragraph, "Mapa de ubicación no disponible (secciones sin geometría en planta).",
                 _NOTE_PT, italic=True, color=_MUTED_HEX)
    marks: list[tuple[str, str, bool]] = []
    for status in (STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE, STATUS_UNKNOWN):
        if status == STATUS_UNKNOWN and status not in highlighted.values():
            continue
        marks.append(("▬ ", STATUS_COLORS[status], True))
        marks.append((f"{STATUS_LABELS_ES[status]}   ", _TEXT_HEX, False))
    _legend_line(cell, marks)
    _legend_line(cell, [("▬ ", OTHER_SECTION_COLOR, True),
                        ("Otras secciones (sin rótulo)", _TEXT_HEX, False)])
    if any(_field(entry, "view_window") is not None for entry in data.section_geometry or ()):
        _legend_line(cell, [("Perfiles a escala 1:1, recortados a los bancos de la cota "
                             "seleccionada.", _MUTED_HEX, False)])


def _add_profile_grid(doc, data: ReportData, page: ProfilePage,
                      shade: Optional[Shade]) -> None:
    entries = {
        (str(entry["section_name"]), _sector_text(entry.get("sector"))): entry
        for entry in data.section_geometry or ()
        if isinstance(entry, Mapping) and entry.get("section_name") is not None
    }
    statuses = _page_statuses(data, page)
    rows = max(1, math.ceil(len(page.sections) / GRID_COLUMNS))
    widths = [_PROFILE_CELL_CM] * GRID_COLUMNS + [_LOCATOR_CELL_CM]
    table = _new_table(doc, rows, widths)
    _set_table_borders(table, {})
    _set_cell_margins(table, 30, 20)
    box = _PROFILE_BOX_ALONE_CM if page.table_on_next_page else _PROFILE_BOX_CM
    for index, name in enumerate(page.sections):
        cell = table.cell(index // GRID_COLUMNS, index % GRID_COLUMNS)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        paragraph = cell.paragraphs[0]
        _compact(paragraph, _CENTER)
        png = cropped_profile_png(
            entries.get((name, page.sector)), status=statuses.get(name),
            width_in=box[0] / _CM_PER_INCH, height_in=box[1] / _CM_PER_INCH, dpi=_FIGURE_DPI,
        )
        if png:
            _add_picture(paragraph, png, box, f"{PROFILE_DESCRIPTION_PREFIX}{name}")
        else:
            _add_run(paragraph, f"{name} — sin perfil (la sección no corta las superficies).",
                     _NOTE_PT, italic=True, color=_MUTED_HEX)
    locator = table.cell(0, GRID_COLUMNS)
    if rows > 1:
        locator = locator.merge(table.cell(rows - 1, GRID_COLUMNS))
    locator.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    _fill_locator_cell(locator, data, page, statuses, shade)


def _number(value: Any, decimals: int, signed: bool = False) -> str:
    number = _finite(value)
    if number is None:
        return DASH
    rounded = round(number, decimals)
    text = f"{abs(rounded):.{decimals}f}".replace(".", ",")
    if rounded < 0:
        return "−" + text
    return "+" + text if signed and rounded > 0 else text


def _bench_label(row: Mapping[str, Any]) -> str:
    if row.get("type") == "EXTRA":
        return "Adic."
    number = _finite(row.get("bench_num"))
    return DASH if number is None else f"B{int(number)}"


def _parameter_status(raw: Any) -> tuple[str, Optional[str]]:
    if raw is None or not str(raw).strip():
        return DASH, None
    status = parse_bench_status(raw)
    return _SHORT_STATUS[status], STATUS_COLORS[status]


def _bench_status(row: Mapping[str, Any]) -> tuple[str, str]:
    worst = str(row.get("worst_status") or STATUS_UNKNOWN)
    worst = worst if worst in STATUS_COLORS else STATUS_UNKNOWN
    label = _BENCH_STATUS_BY_TYPE.get(str(row.get("type")), _SHORT_STATUS[worst])
    return label, STATUS_COLORS[worst]


def _detail_columns(rows: Sequence[Mapping[str, Any]]) -> list[_Column]:
    columns = [
        _Column("Sección", "", 1.7, "section"),
        _Column("Banco", "", 1.2, "bench"),
        _Column("Tipo", "", 2.2, "type"),
        _Column("Cota nominal (m)", "", 2.0, "level"),
    ]
    for group, key, decimals in (("Altura (m)", "height", 2), ("Ángulo (°)", "angle", 1)):
        columns += [
            _Column(group, "dis.", 1.3, "number", f"{key}_design", decimals),
            _Column(group, "real", 1.3, "number", f"{key}_real", decimals),
            _Column(group, "Δ", 1.3, "signed", f"{key}_dev", decimals),
            _Column(group, "est.", 1.6, "status", f"{key}_status"),
        ]
    columns += [
        _Column("Berma (m)", "dis.", 1.3, "number", "berm_design", 2),
        _Column("Berma (m)", "real", 1.3, "number", "berm_real", 2),
        _Column("Berma (m)", "est.", 1.6, "status", "berm_status"),
        _Column("Berma (m)", "aviso", 2.3, "warning"),
    ]
    if any(_finite(row.get(key)) is not None for row in rows for key in _CREST_TOE_KEYS):
        columns += [
            _Column("Cresta Δ (m)", "", 1.5, "signed", "delta_crest", 2),
            _Column("Pata Δ (m)", "", 1.5, "signed", "delta_toe", 2),
        ]
    columns.append(_Column("Estado del banco", "", 2.7, "bench_status"))
    return columns


def _write_detail_header(table, columns: Sequence[_Column]) -> None:
    index = 0
    while index < len(columns):
        column = columns[index]
        end = index
        while end + 1 < len(columns) and columns[end + 1].group == column.group:
            end += 1
        top = table.cell(0, index)
        if column.label:
            if end > index:
                top = top.merge(table.cell(0, end))
            for position in range(index, end + 1):
                sub = table.cell(1, position)
                _cell_text(sub, columns[position].label, DETAIL_TABLE_FONT_PT, bold=True)
                _set_cell_fill(sub, _SUBHEADER_FILL)
                sub.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        else:
            top = top.merge(table.cell(1, index))
        for paragraph in top.paragraphs[1:]:
            paragraph._p.getparent().remove(paragraph._p)
        _cell_text(top, column.group, DETAIL_TABLE_FONT_PT, bold=True, color=_WHITE_HEX)
        _set_cell_fill(top, _HEADER_FILL)
        top.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        index = end + 1


def _write_detail_cell(cell, column: _Column, row: Mapping[str, Any]) -> None:
    size = DETAIL_TABLE_FONT_PT
    if column.kind == "section":
        _cell_text(cell, str(row.get("section") or DASH), size, align=_LEFT, bold=True)
    elif column.kind == "bench":
        _cell_text(cell, _bench_label(row), size)
    elif column.kind == "type":
        _cell_text(cell, _TYPE_LABELS.get(str(row.get("type")), DASH), size, align=_LEFT)
    elif column.kind == "level":
        level = row.get("level_nominal")
        _cell_text(cell, str(level) if level not in (None, "") else DASH, size)
    elif column.kind in ("number", "signed"):
        _cell_text(cell, _number(row.get(column.key), column.decimals, column.kind == "signed"), size)
    elif column.kind == "status":
        text, color = (_TYPE_LABELS[str(row.get("type"))], None) if row.get("type") in ("MISSING", "EXTRA") else _parameter_status(row.get(column.key))
        _cell_text(cell, text, size, bold=color is not None, color=color or _TEXT_HEX)
    elif column.kind == "warning":
        _cell_text(cell, BELOW_MIN_MARK if row.get("design_below_min") else "", _NOTE_PT,
                   bold=True, color=STATUS_COLORS[STATUS_FUERA])
    elif column.kind == "bench_status":
        text, color = _bench_status(row)
        _cell_text(cell, text, size, bold=True, color=_WHITE_HEX)
        _set_cell_fill(cell, color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _table_legend(columns: Sequence[_Column]) -> str:
    parts = [
        "dis. = diseño",
        "Δ = real − diseño",
        "est. = estado del parámetro (Cumple · Fuera = fuera de tolerancia · No cumple)",
        f"{BELOW_MIN_MARK} = la berma de diseño es menor que el mínimo (el estado no cambia)",
    ]
    if any(column.key == "delta_crest" for column in columns):
        parts.append("Cresta Δ / Pata Δ = desviación de la cresta y de la pata respecto del diseño")
    parts += [
        "Adic. = banco adicional (no está en el diseño)",
        "No construido = banco de diseño sin banco real",
        f"{DASH} = sin dato",
    ]
    return " · ".join(parts)


def _add_detail_table(doc, rows: Sequence[Mapping[str, Any]]) -> None:
    columns = _detail_columns(rows)
    scale = USABLE_WIDTH_CM / sum(column.weight for column in columns)
    table = _new_table(doc, 2 + len(rows), [column.weight * scale for column in columns])
    _set_table_borders(table, {"top": _BORDER_HEX, "bottom": _BORDER_HEX, "insideH": _BORDER_HEX})
    _set_cell_margins(table, 40, 0)
    _write_detail_header(table, columns)
    zebra = False
    previous: Optional[tuple] = None
    for offset, row in enumerate(rows):
        identity = (row.get("section"), row.get("sector"))
        if identity != previous:
            zebra = not zebra if previous is not None else False
            previous = identity
        cells = table.rows[2 + offset].cells
        for cell, column in zip(cells, columns):
            if zebra:
                _set_cell_fill(cell, _ZEBRA_FILL)
            _write_detail_cell(cell, column, row)
    for index, table_row in enumerate(table.rows):
        table_row.height = Cm(_ROW_HEIGHT_CM)
        table_row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        tr_pr = table_row._tr.get_or_add_trPr()
        tr_pr.append(OxmlElement("w:cantSplit"))
        if index < 2:
            tr_pr.append(OxmlElement("w:tblHeader"))
    legend = doc.add_paragraph()
    _compact(legend, _LEFT)
    legend.paragraph_format.space_before = Pt(2)
    _add_run(legend, _table_legend(columns), _NOTE_PT, color=_MUTED_HEX)


def _add_subheading(doc, text: str) -> None:
    paragraph = doc.add_paragraph()
    _compact(paragraph, _LEFT)
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(2)
    _add_run(paragraph, text, _SUBHEADING_PT, bold=True)


def add_profile_pages_docx(
    doc,
    data: ReportData,
    *,
    shade: Optional[Shade] = None,
    sectors: Optional[Sequence[str]] = None,
) -> None:
    """Append the landscape profile pages of ``data`` to ``doc``.

    ``sectors`` restricts the pages to those sectors (names compared after
    trimming; ``""`` selects the sections without sector), so the caller can
    add one chapter per sector; ``None`` adds every sector. Pages are numbered
    per sector either way.

    Each page is a new A4 landscape section with a heading, a borderless 3×2
    grid of cropped profiles beside the locator mini-plan and the detail table
    of the profiles on the page; a table of more than eight rows goes alone on
    the following landscape section. A new A4 portrait section, with the
    margins of the section that preceded the pages, is left open at the end.
    Nothing is added when there is no section geometry or no page belongs to
    the requested sectors.
    """
    pages = profile_pages(data)
    if sectors is not None:
        wanted = {_sector_text(sector) for sector in sectors}
        pages = tuple(page for page in pages if page.sector in wanted)
    if not pages:
        return
    origin = doc.sections[-1]
    margins = {
        side: getattr(origin, side)
        for side in ("left_margin", "right_margin", "top_margin", "bottom_margin")
    }
    totals: dict[str, int] = {}
    for page in pages:
        totals[page.sector] = totals.get(page.sector, 0) + 1
    numbers: dict[str, int] = {}
    for page in pages:
        number = numbers[page.sector] = numbers.get(page.sector, 0) + 1
        _landscape_section(doc)
        _add_heading(doc, _page_heading(data, page, number, totals[page.sector]))
        _add_profile_grid(doc, data, page, shade)
        if page.table_on_next_page:
            _landscape_section(doc)
            _add_heading(doc, f"Detalle de perfiles de la página {number}")
        else:
            _add_subheading(doc, "Detalle de los perfiles de esta página")
        _add_detail_table(doc, page.table_rows)
    _portrait_section(doc, margins)
