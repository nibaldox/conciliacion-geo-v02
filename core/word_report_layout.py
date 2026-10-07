"""Presentation helpers for the geotechnical Word report.

This module owns document appearance only: page geometry, base styles,
running header/footer furniture, cover page and data-table formatting.
It performs no domain calculations and never alters report values,
statuses or metadata text.
"""

from datetime import datetime

from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Mm, Pt, RGBColor

PAGE_WIDTH_MM = 297
PAGE_HEIGHT_MM = 210
PAGE_MARGIN_MM = 15
HEADER_FOOTER_DISTANCE_MM = 7.5
HEADER_TEXT_LIMIT = 60

BASE_FONT = "Calibri"
TITLE_FONT = "Calibri Light"
REPORT_TITLE = "Informe de Conciliación Geotécnica"
COVER_DATE_FORMAT = "%d/%m/%Y"
HEADER_FILL = "1F3864"
ZEBRA_FILL = "EEF3F8"
NAVY_RGB = RGBColor.from_string("1F3864")
TEAL_RGB = RGBColor.from_string("17635F")
SLATE_RGB = RGBColor.from_string("44546A")
GRAY_RGB = RGBColor.from_string("7F7F7F")
WHITE_RGB = RGBColor.from_string("FFFFFF")

_TBL_PR_ORDER = (
    "w:tblStyle",
    "w:tblpPr",
    "w:tblOverlap",
    "w:bidiVisual",
    "w:tblStyleRowBandSize",
    "w:tblStyleColBandSize",
    "w:tblW",
    "w:jc",
    "w:tblCellSpacing",
    "w:tblInd",
    "w:tblBorders",
    "w:shd",
    "w:tblLayout",
    "w:tblCellMar",
    "w:tblLook",
)


def _configure_section(section):
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Mm(PAGE_WIDTH_MM)
    section.page_height = Mm(PAGE_HEIGHT_MM)
    section.left_margin = Mm(PAGE_MARGIN_MM)
    section.right_margin = Mm(PAGE_MARGIN_MM)
    section.top_margin = Mm(PAGE_MARGIN_MM)
    section.bottom_margin = Mm(PAGE_MARGIN_MM)
    section.header_distance = Mm(HEADER_FOOTER_DISTANCE_MM)
    section.footer_distance = Mm(HEADER_FOOTER_DISTANCE_MM)


def _configure_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = BASE_FONT
    normal.font.size = Pt(10)

    title = doc.styles["Title"]
    title.font.name = TITLE_FONT
    title.font.size = Pt(28)
    title.font.color.rgb = NAVY_RGB

    heading_specs = [
        ("Heading 1", Pt(16), NAVY_RGB, Pt(18), Pt(6)),
        ("Heading 2", Pt(13), TEAL_RGB, Pt(12), Pt(4)),
        ("Heading 3", Pt(11), SLATE_RGB, Pt(8), Pt(3)),
    ]
    for name, size, color, space_before, space_after in heading_specs:
        style = doc.styles[name]
        style.font.name = BASE_FONT
        style.font.size = size
        style.font.color.rgb = color
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = space_before
        style.paragraph_format.space_after = space_after


def _append_field(paragraph, instruction):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = f" {instruction} "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    cached = OxmlElement("w:t")
    cached.text = "1"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    for element in (fld_begin, instr_text, fld_sep, cached, fld_end):
        run._r.append(element)
    return run


def _configure_furniture(doc, project_info=None):
    section = doc.sections[0]
    header_text = REPORT_TITLE
    if project_info and project_info.get("project"):
        header_text = " ".join(str(project_info["project"]).split())
        if len(header_text) > HEADER_TEXT_LIMIT:
            header_text = header_text[: HEADER_TEXT_LIMIT - 1] + "…"
    header_paragraph = section.header.paragraphs[0]
    header_paragraph.text = ""
    header_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header_run = header_paragraph.add_run(header_text)
    header_run.font.name = BASE_FONT
    header_run.font.size = Pt(9)
    header_run.font.color.rgb = GRAY_RGB

    footer_paragraph = section.footer.paragraphs[0]
    footer_paragraph.text = ""
    footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label_run = footer_paragraph.add_run("Página ")
    _append_field(footer_paragraph, "PAGE")
    of_run = footer_paragraph.add_run(" de ")
    _append_field(footer_paragraph, "NUMPAGES")
    for run in (label_run, of_run):
        run.font.name = BASE_FONT
        run.font.size = Pt(9)
        run.font.color.rgb = GRAY_RGB


def configure_document(doc, project_info=None):
    """Configure page geometry, base styles and running furniture.

    Args:
        doc: a ``docx.Document`` instance, typically still empty.
        project_info: optional dict with ``project``/``author`` keys used
            for the running header text. No metadata is invented here.
    """
    for section in doc.sections:
        _configure_section(section)
        section.different_first_page_header_footer = True
    _configure_styles(doc)
    _configure_furniture(doc, project_info)


def _add_cover_metadata_line(doc, label, value):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(6)
    label_run = paragraph.add_run(f"{label}: ")
    label_run.bold = True
    label_run.font.size = Pt(12)
    value_run = paragraph.add_run(str(value))
    value_run.font.size = Pt(12)
    return paragraph


def add_cover(doc, project_info=None):
    """Add the report cover page followed by a page break.

    Reuses the existing report title and the Proyecto/Elaborado por/Fecha
    metadata labels with their ``N/A`` fallbacks. Nothing beyond the
    caller-supplied metadata is added.

    Args:
        doc: a ``docx.Document`` instance; cover content is appended at the
            current end of the body.
        project_info: optional dict with ``project``/``author`` keys.
    """
    if project_info is None:
        project_info = {}
    project = project_info.get("project", "N/A")
    author = project_info.get("author", "N/A")
    date_text = datetime.now().strftime(COVER_DATE_FORMAT)

    title_paragraph = doc.add_heading(REPORT_TITLE, 0)
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_paragraph.paragraph_format.space_before = Pt(144)
    title_paragraph.paragraph_format.space_after = Pt(36)

    _add_cover_metadata_line(doc, "Proyecto", project)
    _add_cover_metadata_line(doc, "Elaborado por", author)
    _add_cover_metadata_line(doc, "Fecha", date_text)

    doc.add_page_break()


def _get_cell_fill(cell):
    tcPr = cell._tc.tcPr
    if tcPr is None:
        return None
    for child in tcPr:
        if child.tag == qn("w:shd"):
            fill = child.get(qn("w:fill"))
            if fill and fill.lower() != "auto":
                return fill
    return None


def _set_cell_fill(cell, fill_hex):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    tcPr = cell._tc.get_or_add_tcPr()
    valign = tcPr.find(qn("w:vAlign"))
    if valign is not None:
        tcPr.insert(list(tcPr).index(valign), shd)
    else:
        tcPr.append(shd)


def _add_row_flag(row, tag):
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn(tag)) is None:
        trPr.append(OxmlElement(tag))


def _style_header_row(row):
    _add_row_flag(row, "w:cantSplit")
    _add_row_flag(row, "w:tblHeader")
    for cell in row.cells:
        _set_cell_fill(cell, HEADER_FILL)
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                run.font.bold = True
                run.font.color.rgb = WHITE_RGB
                run.font.size = Pt(9.5)


def _set_tblPr_element(tblPr, tag):
    element = tblPr.find(qn(tag))
    if element is not None:
        return element
    element = OxmlElement(tag)
    successors = {
        qn(name) for name in _TBL_PR_ORDER[_TBL_PR_ORDER.index(tag) + 1:]
    }
    for child in tblPr:
        if child.tag in successors:
            child.addprevious(element)
            return element
    tblPr.append(element)
    return element


def _apply_table_width(table, usable_width, column_weights):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    ncols = len(table.columns)
    if ncols == 0:
        return
    if column_weights:
        weights = [
            max(float(w), 0.0) for w in list(column_weights)[:ncols]
        ]
        if len(weights) < ncols:
            weights.extend([1.0] * (ncols - len(weights)))
    else:
        weights = [1.0] * ncols
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * ncols
        total = float(ncols)
    widths = [Emu(int(usable_width * w / total)) for w in weights]

    tblW = _set_tblPr_element(table._tbl.tblPr, "w:tblW")
    tblW.set(qn("w:w"), str(Emu(int(usable_width)).twips))
    tblW.set(qn("w:type"), "dxa")

    cell_mar = _set_tblPr_element(table._tbl.tblPr, "w:tblCellMar")
    for side, value in (("top", 40), ("left", 80), ("bottom", 40), ("right", 80)):
        margin = cell_mar.find(qn(f"w:{side}"))
        if margin is None:
            margin = OxmlElement(f"w:{side}")
            cell_mar.append(margin)
        margin.set(qn("w:w"), str(value))
        margin.set(qn("w:type"), "dxa")

    for idx, column in enumerate(table.columns):
        column.width = widths[idx]
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx < ncols:
                cell.width = widths[idx]


def _is_numeric_text(text):
    stripped = text.strip()
    if not stripped:
        return False
    try:
        float(stripped.replace(",", "."))
    except ValueError:
        return False
    return True


def _style_data_row(row, zebra):
    _add_row_flag(row, "w:cantSplit")
    for cell in row.cells:
        if zebra and _get_cell_fill(cell) is None:
            _set_cell_fill(cell, ZEBRA_FILL)
        for paragraph in cell.paragraphs:
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.RIGHT
                if _is_numeric_text(paragraph.text)
                else WD_ALIGN_PARAGRAPH.LEFT
            )
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                run.font.size = Pt(9)


def _usable_body_width(table):
    section = table.part.document.sections[0]
    return section.page_width - section.left_margin - section.right_margin


def style_data_table(table, column_weights=None):
    """Format a populated data table for the report body.

    Applies a navy header band that repeats on every page, zebra striping,
    compact cell spacing and width fitting. Data cells that already carry
    an explicit fill (status cells) and existing data run font colors are
    never overwritten; the header row is always rendered navy/white.

    Args:
        table: a ``docx.table.Table`` already populated with text.
        column_weights: optional sequence of relative column weights; when
            omitted columns share the usable width equally.
    """
    if len(table.rows) == 0:
        return
    _apply_table_width(table, _usable_body_width(table), column_weights)
    _style_header_row(table.rows[0])
    for row_idx, row in enumerate(table.rows[1:], start=1):
        _style_data_row(row, zebra=row_idx % 2 == 0)
