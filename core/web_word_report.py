"""Technical Word report of the web API, driven by the frozen ``ReportData``.

Portrait A4 document for engineering readers: cover with control block and
scope, a visible index written as text, summary (headline, KPI table with
denominators, plan view, status matrix and the sector comparison when there
are several sectors), criteria and definitions, analysis figures with the
excavation totals, one landscape page per persisted heatmap, the landscape
profile pages composed by ``core.report_pages`` (one chapter per sector when
there are several), the bench annex split by theme, the blast annex aggregated
by event, the per-section excavation annex and the conclusions with
deduplicated warnings.

The module is presentation-only: it reads ``ReportData`` and never recomputes
domain values. Missing values render as «—», never as zero.
"""

from __future__ import annotations

import io
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Sequence

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Mm, Pt, RGBColor

from core.report_charts import STATUS_LABELS_ES
from core.report_data import ReportData, parse_bench_status
from core.report_figures_analysis import (
    deviation_histograms_png,
    excavation_bars_png,
    status_matrix_png,
    trend_png,
)
from core.report_figures_heatmap import (
    HDEV_CATEGORY_ORDER,
    HDEV_LABELS_ES,
    format_level_window,
    heatmap_page_png,
    heatmap_summary,
    level_window_from_geometry,
)
from core.report_figures_plan import dashboard_plan_png
from core.report_pages import add_profile_pages_docx, profile_pages
from core.report_surface import plan_surface_from_mesh, sections_bounds, shaded_relief
from core.report_texts import (
    DASH,
    OFFICIAL_VALUES_LINE,
    fmt_es,
    headline_text,
    heatmap_position_note,
    kpi_definitions,
    scope_lines,
)
from core.word_report_layout import (
    GRAY_RGB,
    REPORT_TITLE,
    _apply_table_width,
    _set_cell_fill,
    configure_document,
    style_data_table,
)

logger = logging.getLogger(__name__)

STATUS_FILL = {
    "CUMPLE": "C9E7CB",
    "FUERA": "FBE3BF",
    "NO_CUMPLE": "F6C6C6",
    "UNKNOWN": "E2E8F0",
}

STATUS_TEXT = {
    "CUMPLE": "14532D",
    "FUERA": "7A4A00",
    "NO_CUMPLE": "7F1D1D",
    "UNKNOWN": "334155",
}

A4_LONG_MM = 297
A4_SHORT_MM = 210
PORTRAIT_MARGIN_MM = 18
LANDSCAPE_MARGIN_MM = 15
PORTRAIT_WIDTH_MM = A4_SHORT_MM - 2 * PORTRAIT_MARGIN_MM
LANDSCAPE_WIDTH_MM = A4_LONG_MM - 2 * LANDSCAPE_MARGIN_MM

BODY_TABLE_PT = 9.0
COMPACT_TABLE_PT = 8.0
ANNEX_TABLE_PT = 7.5
NOTE_PT = 8.5

_TOKEN_BREAKS = re.compile(r"[\s\-]+")
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")
_HEADER_CHAR_EM = 0.66
_BODY_CHAR_EM = 0.56
_MAX_TOKEN_MM = 45.0
_MM_PER_PT = 25.4 / 72.0
_CELL_PADDING_MM = 3.6

MAX_LISTED_IDS = 12
MAX_LISTED_SECTIONS = 8
TOP_DEVIATIONS_PER_PARAMETER = 5

BELOW_MIN_MARK = "⚠ diseño < mín."
BELOW_MIN_HEADER = "Diseño < mín."
NO_SECTOR_LABEL = "Sin sector"
UNIDENTIFIED_EVENT = "Sin identificar"
NO_DATA = "sin dato"
PRIMARY_PF_KEY = "pf_voronoi_bench_g_per_ton"
PRIMARY_PF_FORMULA = "1000*Q/(A*H*rho)"
REIMPORT_WARNING = "Datos de pozos importados con una versión anterior: reimportar."

INDEX_TITLE = "Índice"
SUMMARY_TITLE = "Resumen"
CRITERIA_TITLE = "Criterios y definiciones"
ANALYSIS_TITLE = "Análisis"
HEATMAP_TITLE = "Mapa de calor de desviación horizontal"
PROFILES_TITLE = "Perfiles"
BENCH_ANNEX_TITLE = "Anexo A — Tabla de bancos"
BLAST_ANNEX_TITLE = "Anexo B — Tronadura"
EXCAVATION_ANNEX_TITLE = "Anexo C — Excavación por sección"
NO_EXCAVATION_TEXT = "Sin geometría de secciones para estimar áreas y volúmenes."
CONCLUSIONS_TITLE = "Conclusiones y advertencias"
ANNEX_HEIGHT_ANGLE_TITLE = "A.1 Geometría: altura y ángulo de cara"
ANNEX_BERM_TITLE = "A.1 Geometría: berma, cresta y pata (continuación)"
ANNEX_STATUS_TITLE = "A.2 Estados"

_TOLERANCE_ROWS = (
    ("bench_height", "Altura de banco", "m", "signed"),
    ("face_angle", "Ángulo de cara", "°", "signed"),
    ("berm_width", "Ancho de berma", "m", "min"),
    ("crest_toe_deviation", "Desviación de cresta y pata", "m", "signed"),
    ("inter_ramp_angle", "Ángulo inter-rampa", "°", "signed"),
    ("overall_angle", "Ángulo global", "°", "signed"),
)

_META_ALTERNATES = {
    "design_file": ("design_filename", "design_file_name"),
    "topo_file": ("topo_filename", "topo_file_name"),
    "generated_at": ("generated", "date"),
}

_TYPE_LABELS = {"MATCH": "Comparado", "MISSING": "No construido", "EXTRA": "Adicional"}

_PARAMETER_STATUS_TEXT = {
    "CUMPLE": "CUMPLE",
    "FUERA": "FUERA DE TOLERANCIA",
    "FUERA DE TOLERANCIA": "FUERA DE TOLERANCIA",
    "NO CUMPLE": "NO CUMPLE",
    "NO CONSTRUIDO": "NO CONSTRUIDO",
    "BANCO ADICIONAL": "BANCO ADICIONAL",
    "EXTRA": "BANCO ADICIONAL",
    "UNKNOWN": "SIN EVALUAR",
    "SIN EVALUAR": "SIN EVALUAR",
}

_SHORT_STATUS_TEXT = {"FUERA DE TOLERANCIA": "Fuera de tol."}
STATUS_LEGEND = "Fuera de tol. = fuera de tolerancia."

_COMPONENT_LABELS = {"crest": "cresta", "toe": "pata", "berm": "berma"}

_DEVIATION_PARAMETERS = (
    ("height", "Altura de banco", "m", 2),
    ("angle", "Ángulo de cara", "°", 1),
    ("berm", "Ancho de berma", "m", 2),
)

_BLAST_PRIMARY_HEADER = "FC principal (g/t)"
_BLAST_EVENT_HEADERS = (
    "Fecha", "Malla", "Tronadura", "Fase", "Pozos", "Carga (kg)",
    _BLAST_PRIMARY_HEADER, "FC (g/t)", "FC neto (g/t)", "Pozos con FC", "Explosivo",
)
_BLAST_EVENT_WEIGHTS = (1.15, 2.3, 0.9, 0.6, 0.7, 0.9, 0.9, 0.8, 0.8, 0.75, 2.4)
_BLAST_WITH_PF_HEADER = "Pozos con FC"
_BLAST_GROUP_KEYS = ("fecha_tronadura", "Nombre_Malla_Original", "Blast", "Nombre_Fase")

_PROFILE_READING_GUIDE = (
    "Cada perfil muestra el diseño y la topografía real a la misma escala horizontal y "
    "vertical; su título lleva el nombre de la sección y el estado oficial del perfil.",
    "El área sombreada en azul es sobreexcavación (la topografía quedó por detrás del "
    "diseño) y la sombreada en naranja, subexcavación (material remanente).",
    "En el miniplano, las secciones de la página van en el color de su estado y el "
    "resto en gris.",
    "La tabla al pie tiene una fila por banco seleccionado: diseño, real, Δ = real − "
    "diseño y estado por parámetro, avisos de berma y estado oficial del banco. Con más "
    "de ocho filas, la tabla pasa a la página siguiente.",
    "«—» indica un valor sin dato; nunca equivale a cero.",
)

_LEFT = WD_ALIGN_PARAGRAPH.LEFT
_CENTER = WD_ALIGN_PARAGRAPH.CENTER


@dataclass(frozen=True)
class _Chip:
    """Table cell rendered with the light fill and dark text of a status."""

    text: str
    status: str


@dataclass(frozen=True)
class _Column:
    header: str
    weight: float
    value: Callable[[Any], Any]
    optional: bool = False
    nowrap: bool = False


@dataclass(frozen=True)
class _HeatmapPage:
    sector: str
    png: bytes
    summary: Any
    level_label: Optional[str]
    note: Optional[str]
    created_at: str
    within_m: Optional[float]
    scope_note: Optional[str]


@dataclass
class _Context:
    """Everything derived once per report before any chapter is written."""

    multi_sector: bool
    sectors: tuple[str, ...]
    surface: Any = None
    shade: Any = None
    heatmaps: tuple[_HeatmapPage, ...] = ()
    pages_by_sector: dict = field(default_factory=dict)
    blast_holes: tuple = ()


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _signed(value: Any, decimals: int, unit: Optional[str] = None) -> str:
    number = _finite(value)
    if number is None:
        return DASH
    text = fmt_es(number, decimals, unit)
    return "+" + text if round(number, decimals) > 0 else text


def _count(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return DASH
    try:
        return fmt_es(int(value), 0)
    except (TypeError, ValueError):
        return DASH


def _share(part: int, total: int) -> str:
    if not total:
        return DASH
    return f"{part} de {total} ({fmt_es(100.0 * part / total, 1, '%')})"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _attribute(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _meta_text(meta: Mapping[str, Any], key: str) -> str:
    for candidate in (key,) + _META_ALTERNATES.get(key, ()):
        value = meta.get(candidate)
        if value not in (None, ""):
            return str(value)
    return ""


def _date_text(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return value


def _sector_label(sector: Any) -> str:
    text = str(sector or "").strip()
    return text or NO_SECTOR_LABEL


def _parameter_status_text(status: Any) -> str:
    if status is None or not str(status).strip() or str(status).strip() == "-":
        return DASH
    normalized = str(status).strip().upper().replace("_", " ")
    return _PARAMETER_STATUS_TEXT.get(normalized, normalized)


def _short_status(status: Any) -> str:
    """Parameter status in sentence case, short enough for a one-line cell."""
    text = _parameter_status_text(status)
    if text == DASH:
        return DASH
    return _SHORT_STATUS_TEXT.get(text, text.capitalize())


def _compress_png(blob: bytes, colors: int = 128):
    """Re-encode a chart PNG as an optimized palette image.

    Charts are flat-coloured line art, so palette quantization keeps them
    readable while cutting the embedded size by roughly two thirds. Returns
    ``(blob, width, height)`` so the caller never decodes the image twice.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(blob)) as image:
            image.load()
            quantized = image.convert("RGB").quantize(
                colors=colors, method=Image.MEDIANCUT, dither=Image.Dither.NONE
            )
            output = io.BytesIO()
            quantized.save(output, format="PNG", optimize=True)
            return output.getvalue(), quantized.width, quantized.height
    except Exception:
        return blob, None, None


def _add_picture_bounded(paragraph, blob: bytes, max_width, max_height, colors: int = 128):
    run = paragraph.add_run()
    blob, width, height = _compress_png(blob, colors)
    if not width or not height:
        run.add_picture(io.BytesIO(blob), width=max_width)
        return run
    scale = min(float(max_width) / width, float(max_height) / height)
    run.add_picture(
        io.BytesIO(blob),
        width=Emu(int(width * scale)),
        height=Emu(int(height * scale)),
    )
    return run


def _figure(doc, blob: Optional[bytes], max_width_mm: float, max_height_mm: float,
            colors: int = 128) -> bool:
    if not blob:
        return False
    paragraph = doc.add_paragraph()
    paragraph.alignment = _CENTER
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(2)
    _add_picture_bounded(paragraph, blob, Mm(max_width_mm), Mm(max_height_mm), colors)
    return True


def _render(function: Callable[..., Optional[bytes]], *args: Any, **kwargs: Any) -> Optional[bytes]:
    try:
        return function(*args, **kwargs)
    except Exception:
        logger.exception("Report figure %s failed", getattr(function, "__name__", function))
        return None


def _heading(doc, text: str, level: int = 1, page_break: bool = False):
    heading = doc.add_heading(text, level)
    heading.paragraph_format.keep_with_next = True
    if page_break:
        heading.paragraph_format.page_break_before = True
    return heading


def _paragraph(doc, text: str, *, size: Optional[float] = None, bold: bool = False,
               muted: bool = False, style: Optional[str] = None):
    paragraph = doc.add_paragraph(style=style)
    run = paragraph.add_run(text)
    run.bold = bold or None
    if size is not None:
        run.font.size = Pt(size)
    if muted:
        run.font.color.rgb = GRAY_RGB
    return paragraph


def _note(doc, text: str):
    paragraph = _paragraph(doc, text, size=NOTE_PT, muted=True)
    paragraph.paragraph_format.space_after = Pt(4)
    return paragraph


def _bullets(doc, lines: Sequence[str]) -> None:
    for line in lines:
        doc.add_paragraph(str(line), style="List Bullet")


def _text_mm(chars: int, font_pt: float, em: float) -> float:
    return chars * font_pt * em * _MM_PER_PT + _CELL_PADDING_MM


def _fit_weights(headers: Sequence[str], weights: Optional[Sequence[float]],
                 total_mm: float, font_pt: float,
                 rows: Sequence[Sequence[Any]] = (), nowrap: Sequence[int] = ()) -> list[float]:
    """Column widths (mm) where no header word or body token breaks.

    Word only breaks inside a word when the column is narrower than that
    word, so every column gets at least the width of its longest header word
    and of its longest body token (the whole cell text for ``nowrap``
    columns; other cells may still wrap at spaces and hyphens); the slack is taken proportionally from the other columns.
    """
    count = len(headers)
    raw = [max(float(w), 0.0) for w in list(weights or ())[:count]]
    raw += [1.0] * (count - len(raw))
    scale = total_mm / (sum(raw) or float(count))
    widths = [w * scale for w in raw]
    needed = [
        _text_mm(max((len(word) for word in str(header).split()), default=0), font_pt, _HEADER_CHAR_EM)
        for header in headers
    ]
    whole = set(nowrap)
    for values in rows:
        for index, value in enumerate(values[:count]):
            chip = isinstance(value, _Chip)
            text = value.text if chip else ("" if value is None else str(value))
            if index in whole:
                chars = max((len(line) for line in text.split("\n")), default=0)
            else:
                chars = max((len(token) for token in _TOKEN_BREAKS.split(text)), default=0)
            width = min(_text_mm(chars, font_pt, _HEADER_CHAR_EM if chip else _BODY_CHAR_EM), _MAX_TOKEN_MM)
            if width > needed[index]:
                needed[index] = width
    for _ in range(count):
        short = [i for i in range(count) if widths[i] < needed[i] - 1e-6]
        if not short:
            break
        deficit = sum(needed[i] - widths[i] for i in short)
        slack = {i: widths[i] - needed[i] for i in range(count) if widths[i] > needed[i]}
        available = sum(slack.values())
        if available <= 0:
            break
        taken = min(deficit, available)
        for i in short:
            widths[i] += (needed[i] - widths[i]) * taken / deficit
        for i, room in slack.items():
            widths[i] -= taken * room / available
    return widths


def _table(doc, headers: Sequence[str], rows: Sequence[Sequence[Any]], *,
           weights: Optional[Sequence[float]] = None, font_pt: float = BODY_TABLE_PT,
           width_mm: Optional[float] = None, left: Sequence[int] = (0,),
           nowrap: Sequence[int] = ()):
    """Add a styled data table; ``_Chip`` values become status-coloured cells."""
    table = doc.add_table(rows=1, cols=len(headers))
    for cell, header in zip(table.rows[0].cells, headers):
        cell.text = str(header)
    chips: list[tuple[Any, _Chip]] = []
    body_rows = []
    for values in rows:
        cells = table.add_row().cells
        body_rows.append(cells)
        for cell, value in zip(cells, values):
            if isinstance(value, _Chip):
                cell.text = value.text
                _set_cell_fill(cell, STATUS_FILL.get(value.status, STATUS_FILL["UNKNOWN"]))
                chips.append((cell, value))
            else:
                cell.text = DASH if value is None else str(value)
    total_mm = PORTRAIT_WIDTH_MM if width_mm is None else width_mm
    fitted = _fit_weights(headers, weights, total_mm, font_pt, rows, nowrap)
    style_data_table(table, column_weights=fitted)
    if width_mm is not None:
        _apply_table_width(table, Mm(width_mm), fitted)
    size = Pt(font_pt)
    for cell in table.rows[0].cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.size = size
    left_columns = set(left)
    for cells in body_rows:
        for index, cell in enumerate(cells):
            for paragraph in cell.paragraphs:
                paragraph.alignment = _LEFT if index in left_columns else _CENTER
                for run in paragraph.runs:
                    run.font.size = size
    for cell, chip in chips:
        color = RGBColor.from_string(STATUS_TEXT.get(chip.status, STATUS_TEXT["UNKNOWN"]))
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
                run.font.color.rgb = color
    return table


def _apply_page(section, landscape: bool) -> None:
    section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    section.page_width = Mm(A4_LONG_MM if landscape else A4_SHORT_MM)
    section.page_height = Mm(A4_SHORT_MM if landscape else A4_LONG_MM)
    margin = Mm(LANDSCAPE_MARGIN_MM if landscape else PORTRAIT_MARGIN_MM)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, margin)


def _shrink_section_break(doc) -> None:
    """Collapse the empty paragraph that carries a section break.

    A full page followed by a normal-height carrier paragraph spills onto a
    blank page; a one-point paragraph never does.
    """
    paragraphs = doc.element.body.findall(qn("w:p"))
    if not paragraphs:
        return
    carrier = paragraphs[-1]
    p_pr = carrier.find(qn("w:pPr"))
    if p_pr is None or carrier.findall(qn("w:r")):
        return
    sect_pr = p_pr.find(qn("w:sectPr"))
    if sect_pr is None:
        return
    for tag in ("w:spacing", "w:rPr"):
        for existing in p_pr.findall(qn(tag)):
            p_pr.remove(existing)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), "20")
    spacing.set(qn("w:lineRule"), "exact")
    sect_pr.addprevious(spacing)
    run_pr = OxmlElement("w:rPr")
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "2")
    run_pr.append(size)
    sect_pr.addprevious(run_pr)


def _new_section(doc, landscape: bool):
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    _shrink_section_break(doc)
    _apply_page(section, landscape)
    section.different_first_page_header_footer = False
    return section


def _plan_sections(data: ReportData) -> Sequence[Any]:
    plan_inputs = data.plan_inputs
    if not isinstance(plan_inputs, Mapping):
        return ()
    return plan_inputs.get("sections") or ()


def _plan_backdrop(data: ReportData):
    """Surface and shaded relief of the plan views, built once per report."""
    plan_inputs = data.plan_inputs
    sections = _plan_sections(data)
    mesh = plan_inputs.get("mesh_topo") if isinstance(plan_inputs, Mapping) else None
    if mesh is None or not sections:
        return None, None
    try:
        surface = plan_surface_from_mesh(mesh, bounds=sections_bounds(sections))
        shade = shaded_relief(surface) if surface is not None else None
    except Exception:
        logger.exception("Plan surface backdrop failed; figures render without relief")
        return None, None
    if surface is None:
        return None, None
    return surface, shade


def _plan_statuses(data: ReportData) -> dict[str, str]:
    """Status by section name; names repeated across sectors stay unclassified."""
    sectors_by_name: dict[str, set[str]] = {}
    for row in data.rows:
        sectors_by_name.setdefault(row.section, set()).add(row.sector or "")
    return {
        profile.section: profile.worst_status
        for profile in data.profiles
        if len(sectors_by_name.get(profile.section, ())) <= 1
    }


def _heatmap_pages(data: ReportData, multi_sector: bool) -> tuple[_HeatmapPage, ...]:
    pages: list[_HeatmapPage] = []
    for entry in data.heatmaps or ():
        if not isinstance(entry, Mapping):
            continue
        payload = entry.get("payload")
        sector = str(entry.get("sector") or "")
        try:
            geometry = [
                item
                for item in data.section_geometry or ()
                if isinstance(item, Mapping)
                and (not multi_sector or str(item.get("sector") or "") == sector)
            ]
            window = level_window_from_geometry(geometry)
            summary = heatmap_summary(payload, level_window=window)
            levels = data.filters.levels_for(sector) if window is not None else ()
            level_label = ", ".join(str(level) for level in levels) if levels else None
            title = f"Sector {sector}" if sector else ""
            if level_label:
                title = " · ".join(filter(None, (title, f"{'cotas' if len(levels) > 1 else 'cota'} {level_label}")))
            if window is not None:
                title = " · ".join(filter(None, (title, format_level_window(window))))
            png = heatmap_page_png(payload, level_window=window, title=title)
            note = heatmap_position_note(summary, level_label=level_label)
        except Exception:
            logger.exception("Heatmap page of sector %r failed", sector)
            continue
        if not png:
            continue
        thresholds = payload.get("thresholds") if isinstance(payload, Mapping) else None
        within = _finite(thresholds.get("within")) if isinstance(thresholds, Mapping) else None
        pages.append(
            _HeatmapPage(
                sector=sector,
                png=png,
                summary=summary,
                level_label=level_label,
                note=note,
                created_at=str(entry.get("computed_at_text") or ""),
                scope_note=entry.get("scope_note"),
                within_m=within,
            )
        )
    return tuple(pages)


def _blast_holes(data: ReportData) -> tuple:
    blast = data.blast
    if not isinstance(blast, Mapping):
        return ()
    return tuple(hole for hole in blast.get("holes") or () if isinstance(hole, Mapping))


def _build_context(data: ReportData) -> _Context:
    sectors = tuple(str(summary.get("sector") or "") for summary in data.sector_summaries or ())
    multi_sector = len(sectors) >= 2
    surface, shade = _plan_backdrop(data)
    pages_by_sector: dict[str, list] = {}
    try:
        for page in profile_pages(data):
            pages_by_sector.setdefault(page.sector, []).append(page)
    except Exception:
        logger.exception("Profile page layout failed")
        pages_by_sector = {}
    return _Context(
        multi_sector=multi_sector,
        sectors=sectors,
        surface=surface,
        shade=shade,
        heatmaps=_heatmap_pages(data, multi_sector),
        pages_by_sector=pages_by_sector,
        blast_holes=_blast_holes(data),
    )


def _add_cover(doc, data: ReportData) -> None:
    meta = data.meta or {}
    title = doc.add_heading(REPORT_TITLE, 0)
    title.alignment = _CENTER
    title.paragraph_format.space_before = Pt(72)
    title.paragraph_format.space_after = Pt(6)
    subtitle = _paragraph(doc, "Informe técnico", size=14, muted=True)
    subtitle.alignment = _CENTER
    subtitle.paragraph_format.space_after = Pt(24)

    generated = _date_text(_meta_text(meta, "generated_at"))
    for label, value, fallback in (
        ("Proyecto", _meta_text(meta, "project"), "No informado"),
        ("Operación", _meta_text(meta, "operation"), "No informada"),
        ("Fase", _meta_text(meta, "phase"), "No informada"),
        ("Elaborado por", _meta_text(meta, "author"), "No informado"),
        ("Fecha", generated, "No informada"),
    ):
        paragraph = doc.add_paragraph()
        paragraph.alignment = _CENTER
        paragraph.paragraph_format.space_after = Pt(4)
        label_run = paragraph.add_run(f"{label}: ")
        label_run.bold = True
        label_run.font.size = Pt(12)
        paragraph.add_run(value or fallback).font.size = Pt(12)

    _heading(doc, "Control de revisión y aprobación", 2)
    _table(
        doc,
        ("Control", "Dato"),
        [
            ("Revisión", _meta_text(meta, "revision") or "No informada"),
            ("Elaborado por", _meta_text(meta, "author") or "No informado"),
            ("Revisado por", _meta_text(meta, "reviewed_by") or "No informado"),
            ("Aprobado por", _meta_text(meta, "approved_by") or "No informado"),
            ("Fecha de emisión", generated or "No informada"),
        ],
        weights=(1.0, 2.2),
        left=(0, 1),
    )

    _heading(doc, "Alcance del informe", 2)
    scope = list(scope_lines(data))
    for entry in data.heatmaps or ():
        if isinstance(entry, Mapping) and entry.get("scope_note") and entry["scope_note"] not in scope:
            scope.append(entry["scope_note"])
    _bullets(doc, scope)
    counts = data.counts or {}
    scope_rows = []
    for key, label in (("design_file", "Superficie de diseño"), ("topo_file", "Superficie topográfica")):
        value = _meta_text(meta, key)
        if value:
            scope_rows.append((label, value))
    scope_rows += [
        ("Secciones con bancos", _count(counts.get("n_sections"))),
        ("Registros de banco", _count(counts.get("n_rows"))),
        ("Bancos comparados", _count(counts.get("n_match"))),
        ("Bancos de diseño no construidos", _count(counts.get("n_missing"))),
        ("Bancos adicionales", _count(counts.get("n_extra"))),
    ]
    _table(doc, ("Alcance", "Dato"), scope_rows, weights=(1.0, 2.2), left=(0, 1))


def _add_index(doc, entries: Sequence[tuple[str, int]]) -> None:
    _heading(doc, INDEX_TITLE, 1, page_break=True)
    for title, level in entries:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(3)
        paragraph.paragraph_format.left_indent = Mm(8 * level)
        run = paragraph.add_run(title)
        run.font.size = Pt(11 if level == 0 else 10)
        run.bold = level == 0 or None


def _profile_tally(data: ReportData) -> Mapping[str, Any]:
    profiles = (data.headline or {}).get("profiles")
    if isinstance(profiles, Mapping) and profiles:
        return profiles
    return data.profile_counts or {}


def _achievement_parts(achievement: Mapping[str, Any]) -> str:
    return " · ".join(
        f"{label} {achievement.get(f'{key}_cumple', 0)}/{achievement.get(f'{key}_denom', 0)}"
        for key, label in _COMPONENT_LABELS.items()
    )


def _kpi_rows(data: ReportData) -> list[tuple[str, str, str]]:
    tally = _profile_tally(data)
    counts = {key: int(tally.get(key, 0) or 0) for key in ("CUMPLE", "FUERA", "NO_CUMPLE", "UNKNOWN")}
    total = sum(counts.values())
    headline = data.headline or {}
    base = f"{_plural(total, 'perfil evaluado', 'perfiles evaluados')}; estado = peor banco"
    rows = [
        ("Perfiles que cumplen", _share(counts["CUMPLE"], total), base),
        ("Perfiles fuera de tolerancia", _share(counts["FUERA"], total), base),
        (
            "Perfiles que no cumplen",
            _share(counts["NO_CUMPLE"], total),
            f"{int(headline.get('nc_by_geometry', 0) or 0)} por geometría; "
            f"{int(headline.get('nc_only_missing_extra', 0) or 0)} solo por banco no "
            "construido o adicional",
        ),
    ]
    if counts["UNKNOWN"]:
        rows.append(("Perfiles sin evaluar", _share(counts["UNKNOWN"], total), base))

    scored = sum(1 for profile in data.profiles if profile.weighted_score is not None)
    rows.append(
        (
            "Puntaje ponderado (0–100)",
            fmt_es(data.global_weighted_score, 1),
            f"Promedio de {_plural(scored, 'perfil con puntaje', 'perfiles con puntaje')}",
        )
    )
    for parameter in data.parameters or ():
        rows.append(
            (
                f"{parameter.label}: bancos que cumplen",
                _share(parameter.cumple, parameter.n_evaluated),
                "Bancos comparados con el diseño; no construidos y adicionales aparte",
            )
        )

    achievement = (data.design_achievement or {}).get("global") or {}
    if achievement:
        rows.append(
            (
                "Logro de diseño (0–100)",
                fmt_es(achievement.get("global_score"), 0),
                f"{_count(achievement.get('n_evaluable'))} de "
                f"{_count(achievement.get('n_total'))} bancos con medición de cresta, "
                "pata o berma",
            )
        )
        rows.append(
            (
                "Logro de diseño: elementos en tolerancia",
                _achievement_parts(achievement),
                "Bancos en CUMPLE sobre bancos con ese dato",
            )
        )

    bench_counts = data.counts or {}
    n_rows = int(bench_counts.get("n_rows", 0) or 0)
    registers = f"de {_plural(n_rows, 'registro de banco', 'registros de banco')}"
    rows += [
        ("Bancos comparados", _count(bench_counts.get("n_match")), registers),
        ("Bancos de diseño no construidos", _count(bench_counts.get("n_missing")), registers),
        ("Bancos adicionales", _count(bench_counts.get("n_extra")), registers),
    ]
    below_min = sum(1 for row in data.rows if row.design_below_min)
    if below_min:
        rows.append(
            (
                "Bermas con diseño bajo el mínimo",
                str(below_min),
                "Advertencia; no cambia el estado oficial",
            )
        )

    totals = data.excavation_totals or {}
    n_sections = int(totals.get("n_sections", 0) or 0)
    if n_sections:
        with_volume = n_sections - int(totals.get("n_without_volume", 0) or 0)
        basis = f"Estimación; {with_volume} de {n_sections} secciones con volumen"
        rows.append(
            (
                "Sobreexcavación estimada",
                f"{fmt_es(totals.get('volume_over_m3'), 0, 'm³')} "
                f"({fmt_es(totals.get('area_over_m2'), 0, 'm²')})",
                basis,
            )
        )
        rows.append(
            (
                "Subexcavación estimada",
                f"{fmt_es(totals.get('volume_under_m3'), 0, 'm³')} "
                f"({fmt_es(totals.get('area_under_m2'), 0, 'm²')})",
                basis,
            )
        )

    depth = data.depth or {}
    if _finite(depth.get("profundidad")) is not None:
        rows.append(
            (
                "Profundidad total de la excavación",
                fmt_es(depth.get("profundidad"), 2, "m"),
                f"Cota de cresta {fmt_es(depth.get('cota_cresta'), 2)} − cota de piso "
                f"{fmt_es(depth.get('cota_piso'), 2)}",
            )
        )
    return rows


def _levels_text(levels: Sequence[Any]) -> str:
    labels = [str(level) for level in levels or () if str(level).strip()]
    return ", ".join(labels) if labels else "Todas"


def _parameter_cell(parameters: Sequence[Any], key: str) -> str:
    parameter = next((item for item in parameters or () if item.parameter == key), None)
    if parameter is None or not parameter.n_evaluated:
        return DASH
    return (
        f"{fmt_es(parameter.pct_cumple, 1, '%')}\n"
        f"{parameter.cumple}/{parameter.n_evaluated}"
    )


def _add_sector_comparison(doc, data: ReportData) -> None:
    _heading(doc, "Comparación entre sectores", 2)
    rows = []
    for summary in data.sector_summaries:
        tally = (summary.get("headline") or {}).get("profiles") or summary.get("profile_counts") or {}
        total = sum(int(tally.get(key, 0) or 0) for key in ("CUMPLE", "FUERA", "NO_CUMPLE", "UNKNOWN"))
        achievement = summary.get("design_achievement") or {}
        totals = summary.get("excavation_totals") or {}
        rows.append(
            (
                _sector_label(summary.get("sector")),
                _levels_text(summary.get("levels")),
                str(total),
                f"{int(tally.get('CUMPLE', 0) or 0)}/{total}" if total else DASH,
                fmt_es(summary.get("global_weighted_score"), 1),
                _parameter_cell(summary.get("parameters"), "height"),
                _parameter_cell(summary.get("parameters"), "angle"),
                _parameter_cell(summary.get("parameters"), "berm"),
                fmt_es(achievement.get("global_score"), 0),
                fmt_es(totals.get("volume_over_m3"), 0),
                fmt_es(totals.get("volume_under_m3"), 0),
            )
        )
    _table(
        doc,
        (
            "Sector", "Cota", "Perfiles", "Cumplen", "Puntaje", "Altura", "Ángulo",
            "Berma", "Logro", "Sobreexc. (m³)", "Subexc. (m³)",
        ),
        rows,
        weights=(1.3, 1.0, 0.9, 0.9, 0.9, 1.0, 1.0, 1.0, 0.8, 1.1, 1.1),
        font_pt=COMPACT_TABLE_PT,
    )
    _note(
        doc,
        "Cada sector se evalúa en su cota seleccionada. Altura, ángulo y berma: % de "
        "bancos comparados que cumplen y su conteo. Los sectores están en cotas "
        "distintas: la comparación es referencial.",
    )


def _add_summary(doc, data: ReportData, context: _Context) -> None:
    headline = _paragraph(doc, headline_text(data), size=12, bold=True)
    headline.paragraph_format.space_after = Pt(6)
    _table(doc, ("Indicador", "Valor", "Base"), _kpi_rows(data), weights=(1.5, 1.2, 2.2), left=(0, 2))
    _note(
        doc,
        "Puntaje ponderado, % por parámetro y logro de diseño son mediciones distintas; "
        "no se suman ni se comparan entre sí. Sus definiciones están en el capítulo de "
        "criterios.",
    )
    for page in context.heatmaps:
        if page.note:
            prefix = f"Sector {page.sector}: " if page.sector and context.multi_sector else ""
            _paragraph(doc, f"Posición de la pared (mapa de calor). {prefix}{page.note}", size=NOTE_PT + 0.5)

    sections = _plan_sections(data)
    plan = None
    if sections:
        plan = _render(
            dashboard_plan_png, sections, _plan_statuses(data),
            shade=context.shade, surface=context.surface,
        )
    _heading(doc, "Vista en planta", 2)
    if _figure(doc, plan, PORTRAIT_WIDTH_MM, 108, colors=256):
        _note(doc, "Cada sección toma el color del estado oficial de su perfil (peor banco).")
    else:
        doc.add_paragraph("Sin geometría de secciones disponible para la vista en planta.")

    _heading(doc, "Matriz de estados por sección y cota", 2)
    if _figure(doc, _render(status_matrix_png, data.matrix), PORTRAIT_WIDTH_MM, 70):
        _note(doc, "Estado oficial de cada banco, por sección en el orden definido y cota nominal.")
    else:
        doc.add_paragraph("Sin bancos para la matriz de estados.")

    if context.multi_sector:
        _add_sector_comparison(doc, data)


def _tolerance_text(tolerance: Mapping[str, Any], kind: str, decimals: int) -> Optional[str]:
    if kind == "min":
        minimum = _finite(tolerance.get("min"))
        return None if minimum is None else f"mínimo {fmt_es(minimum, decimals)}"
    neg = _finite(tolerance.get("neg"))
    pos = _finite(tolerance.get("pos"))
    if neg is None and pos is None:
        return None
    neg_text = "sin límite" if neg is None else "−" + fmt_es(abs(neg), decimals)
    pos_text = "sin límite" if pos is None else "+" + fmt_es(abs(pos), decimals)
    return f"{neg_text} / {pos_text}"


def _process_rows(meta: Mapping[str, Any]) -> list[tuple[str, str]]:
    process = meta.get("process")
    if not isinstance(process, Mapping):
        process = meta.get("process_settings")
    if not isinstance(process, Mapping):
        return []
    rows = []
    for key, value in process.items():
        if value is None or isinstance(value, (Mapping, list, tuple)):
            continue
        number = None if isinstance(value, (bool, str)) else _finite(value)
        if isinstance(value, float) and number is None:
            continue
        text = fmt_es(number, 2) if number is not None else str(value)
        rows.append((str(key).replace("_", " ").capitalize(), text))
    return rows


def _add_criteria(doc, data: ReportData, context: _Context) -> None:
    _heading(doc, "Tolerancias aplicadas", 2)
    tolerances = data.tolerances or {}
    rows = []
    for key, label, unit, kind in _TOLERANCE_ROWS:
        tolerance = tolerances.get(key)
        if not isinstance(tolerance, Mapping):
            continue
        text = _tolerance_text(tolerance, kind, 1)
        if text is not None:
            rows.append((label, text, unit))
    if rows:
        _table(doc, ("Parámetro", "Criterio", "Unidad"), rows, weights=(1.6, 1.2, 0.6))
    else:
        doc.add_paragraph("Sin tolerancias declaradas en la sesión.")

    _heading(doc, "Definición de los indicadores", 2)
    _table(doc, ("Indicador", "Definición"), list(kpi_definitions(data)), weights=(1.0, 3.2), left=(0, 1))

    _heading(doc, "Cotas nominales", 2)
    levels = list(data.nominal_levels or ())
    if levels:
        with_sector = any(str(level.sector or "").strip() for level in levels)
        headers = ["Cota nominal", "Rango de cotas (m)", "Secciones", "Registros de banco"]
        level_rows = []
        for level in levels:
            low, high = fmt_es(level.min_level, 0), fmt_es(level.max_level, 0)
            values = [
                str(level.label),
                low if low == high else f"{low} – {high}",
                str(level.n_sections),
                str(level.n_rows),
            ]
            level_rows.append([_sector_label(level.sector)] + values if with_sector else values)
        if with_sector:
            headers.insert(0, "Sector")
        _table(doc, headers, level_rows)
    else:
        doc.add_paragraph("Sin cotas nominales: no hay registros de banco.")
    _bullets(doc, [str(warning) for warning in data.level_warnings or ()])

    _heading(doc, "Volúmenes de excavación: método", 2)
    doc.add_paragraph(
        "Volumen estimado = área × ancho de influencia. El área es la diferencia entre "
        "el perfil real y el de diseño dentro del recorte de la sección; el ancho de "
        "influencia es la mitad de la distancia a cada sección vecina del mismo sector, "
        "medida entre los orígenes de las secciones (no es un parámetro fijo). Una "
        "sección sin vecina no tiene volumen. Es una estimación referencial, no una "
        "cubicación."
    )

    _heading(doc, "Valores informados", 2)
    doc.add_paragraph(OFFICIAL_VALUES_LINE)
    doc.add_paragraph(
        "El estado oficial de un banco comparado es CUMPLE o NO CUMPLE según su "
        "puntaje; FUERA DE TOLERANCIA existe solo por parámetro. Una berma cuyo diseño "
        f"es menor que el mínimo lleva el aviso «{BELOW_MIN_MARK}» sin cambiar su estado."
    )

    process_rows = _process_rows(data.meta or {})
    if process_rows:
        _heading(doc, "Ajustes de proceso", 2)
        _table(doc, ("Ajuste", "Valor"), process_rows, weights=(1.6, 1.0))


def _excavation_rows(data: ReportData, multi_sector: bool) -> list[list[str]]:
    rows = []
    for entry in data.excavation or ():
        values = [
            str(entry.section),
            fmt_es(entry.area_over_m2, 1),
            fmt_es(entry.area_under_m2, 1),
            fmt_es(entry.influence_width_m, 2),
            fmt_es(entry.volume_over_m3, 0),
            fmt_es(entry.volume_under_m3, 0),
        ]
        if multi_sector:
            values.insert(1, _sector_label(entry.sector))
        rows.append(values)
    totals = data.excavation_totals or {}
    total = [
        "Total",
        fmt_es(totals.get("area_over_m2"), 1),
        fmt_es(totals.get("area_under_m2"), 1),
        DASH,
        fmt_es(totals.get("volume_over_m3"), 0),
        fmt_es(totals.get("volume_under_m3"), 0),
    ]
    if multi_sector:
        total.insert(1, DASH)
    rows.append(total)
    return rows


def _excavation_total_row(data: ReportData) -> list[str]:
    totals = data.excavation_totals or {}
    n_sections = int(totals.get("n_sections", 0) or 0)
    with_volume = n_sections - int(totals.get("n_without_volume", 0) or 0)
    return [
        f"{with_volume} de {n_sections}",
        fmt_es(totals.get("area_over_m2"), 1),
        fmt_es(totals.get("area_under_m2"), 1),
        fmt_es(totals.get("volume_over_m3"), 0),
        fmt_es(totals.get("volume_under_m3"), 0),
    ]


def _add_excavation_annex(doc, data: ReportData, context: _Context) -> None:
    if not data.excavation:
        doc.add_paragraph(NO_EXCAVATION_TEXT)
        return
    doc.add_paragraph(
        f"{_plural(len(data.excavation), 'sección', 'secciones')} en el orden definido. "
        "Áreas de sobreexcavación y subexcavación dentro del recorte de cada sección, "
        "ancho de influencia y volúmenes estimados; los totales y el gráfico están en "
        "el capítulo de análisis."
    )
    headers = [
        "Sección", "Área sobreexc. (m²)", "Área subexc. (m²)",
        "Ancho de influencia (m)", "Volumen sobreexc. (m³)", "Volumen subexc. (m³)",
    ]
    if context.multi_sector:
        headers.insert(1, "Sector")
    _table(doc, headers, _excavation_rows(data, context.multi_sector), font_pt=COMPACT_TABLE_PT)
    _note(
        doc,
        "Volumen estimado = área × ancho de influencia (separación real entre "
        "secciones). «—»: sin área o sin sección vecina; no equivale a cero.",
    )


def _missing_components(achievement: Mapping[str, Any]) -> str:
    tally = {key: 0 for key in _COMPONENT_LABELS}
    for detail in achievement.get("rows") or ():
        for component in (detail or {}).get("components_missing") or ():
            if component in tally:
                tally[component] += 1
    parts = [
        f"{_COMPONENT_LABELS[key]} en {_plural(count, 'banco', 'bancos')}"
        for key, count in tally.items()
        if count
    ]
    if not parts:
        return "Sin componentes faltantes."
    return "Componentes faltantes: " + ", ".join(parts) + "."


def _achievement_row(label: str, achievement: Mapping[str, Any]) -> tuple:
    def element(key: str) -> str:
        denominator = int(achievement.get(f"{key}_denom", 0) or 0)
        if not denominator:
            return DASH
        return (
            f"{achievement.get(f'{key}_cumple', 0)}/{denominator} "
            f"({fmt_es(achievement.get(f'{key}_pct'), 0, '%')})"
        )

    return (
        label,
        fmt_es(achievement.get("global_score"), 0),
        element("crest"),
        element("toe"),
        element("berm"),
        _signed(achievement.get("delta_crest_mean"), 2),
        _signed(achievement.get("delta_toe_mean"), 2),
    )


def _add_design_achievement(doc, data: ReportData, context: _Context) -> None:
    _heading(doc, "Logro de diseño", 2)
    achievement = (data.design_achievement or {}).get("global") or {}
    if not achievement or not achievement.get("n_total"):
        doc.add_paragraph(
            "Sin datos suficientes de logro de diseño (se requiere al menos una "
            "desviación de cresta o pata, o un estado de berma)."
        )
        return
    rows = [_achievement_row("Global", achievement)]
    if context.multi_sector:
        for sector in (data.design_achievement or {}).get("sectors") or ():
            rows.append(_achievement_row(_sector_label(sector.get("sector")), sector))
    _table(
        doc,
        (
            "Ámbito", "Logro", "Cresta en tolerancia", "Pata en tolerancia",
            "Berma en CUMPLE", "Δ cresta media (m)", "Δ pata media (m)",
        ),
        rows,
        weights=(1.1, 0.9, 1.2, 1.2, 1.2, 1.0, 1.0),
        font_pt=COMPACT_TABLE_PT,
    )
    coverage = achievement.get("coverage") or {}
    _note(
        doc,
        f"Logro de 0 a 100. Cobertura: evaluables {_count(coverage.get('n_evaluable'))} de "
        f"{_count(coverage.get('n_rows'))} bancos; completos "
        f"{_count(coverage.get('n_complete'))}; peso medio disponible "
        f"{fmt_es(coverage.get('weight_available_mean'), 2)}. El puntaje redistribuye "
        "los pesos disponibles; un banco parcial no cuenta como completo. "
        + _missing_components(achievement),
    )


def _add_top_deviations(doc, data: ReportData) -> None:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for entry in data.top_deviations or ():
        if isinstance(entry, Mapping):
            grouped.setdefault(str(entry.get("parameter") or ""), []).append(entry)
    rows = []
    for key, label, unit, decimals in _DEVIATION_PARAMETERS:
        for entry in grouped.get(key, [])[:TOP_DEVIATIONS_PER_PARAMETER]:
            status = parse_bench_status(entry.get("status"))
            bench = entry.get("bench_num")
            rows.append(
                (
                    f"{label} ({unit})",
                    str(entry.get("section") or DASH),
                    str(entry.get("level") or DASH),
                    DASH if bench is None else str(bench),
                    fmt_es(entry.get("design"), decimals),
                    fmt_es(entry.get("real"), decimals),
                    _signed(entry.get("deviation"), decimals),
                    _DECIMAL_POINT.sub(",", str(entry.get("tolerance_text") or DASH)),
                    _Chip(STATUS_LABELS_ES.get(status, STATUS_LABELS_ES["UNKNOWN"]), status),
                )
            )
    if not rows:
        return
    _heading(doc, "Mayores desviaciones", 2)
    _table(
        doc,
        ("Parámetro", "Sección", "Cota", "Banco", "Diseño", "Real", "Δ", "Criterio", "Estado"),
        rows,
        weights=(1.6, 0.9, 0.8, 0.7, 0.8, 0.8, 0.8, 1.2, 1.3),
        font_pt=COMPACT_TABLE_PT,
    )
    _note(
        doc,
        f"Hasta {TOP_DEVIATIONS_PER_PARAMETER} registros por parámetro en el orden "
        "oficial del modelo; el orden no cambia el estado del banco. Berma: Δ = real − mínima.",
    )


def _add_analysis(doc, data: ReportData, context: _Context) -> None:
    tolerances = data.tolerances or {}
    _heading(doc, "Distribución de las desviaciones", 2)
    if _figure(doc, _render(deviation_histograms_png, data.deviations, tolerances), PORTRAIT_WIDTH_MM, 64):
        _note(doc, "Real − diseño de los bancos comparados; la banda marca la tolerancia.")
    else:
        doc.add_paragraph("Sin bancos comparados para graficar las desviaciones.")

    _heading(doc, "Tendencia a lo largo del muro", 2)
    if _figure(doc, _render(trend_png, data.trend, tolerances), PORTRAIT_WIDTH_MM, 64):
        _note(doc, "Desviación media por sección, en el orden en que están definidas.")
    else:
        doc.add_paragraph("Sin desviaciones por sección para graficar la tendencia.")

    _heading(doc, "Sobreexcavación y subexcavación por sección", 2)
    if not data.excavation:
        doc.add_paragraph(NO_EXCAVATION_TEXT)
    else:
        _figure(doc, _render(excavation_bars_png, data.excavation), PORTRAIT_WIDTH_MM, 64)
        _table(
            doc,
            (
                "Secciones con volumen", "Área sobreexc. (m²)", "Área subexc. (m²)",
                "Volumen sobreexc. (m³)", "Volumen subexc. (m³)",
            ),
            [_excavation_total_row(data)],
            font_pt=COMPACT_TABLE_PT,
            left=(),
        )
        _note(
            doc,
            "Totales de las secciones del informe. Volumen estimado = área × ancho de "
            "influencia (separación real entre secciones). El detalle por sección está "
            f"en el {EXCAVATION_ANNEX_TITLE}.",
        )

    _add_design_achievement(doc, data, context)
    _add_top_deviations(doc, data)


def _extreme_text(extreme: Optional[Mapping[str, Any]]) -> str:
    if not extreme:
        return DASH
    parts = [_signed(extreme.get("deviation_m"), 2, "m")]
    if _finite(extreme.get("station_m")) is not None:
        parts.append(f"est. {fmt_es(extreme.get('station_m'), 0, 'm')}")
    if _finite(extreme.get("elevation")) is not None:
        parts.append(f"cota {fmt_es(extreme.get('elevation'), 1)}")
    if extreme.get("location"):
        parts.append(str(extreme["location"]))
    return " · ".join(parts)


def _add_heatmap_page(doc, page: _HeatmapPage, title: Optional[str], multi_sector: bool) -> None:
    _new_section(doc, landscape=True)
    if title:
        _heading(doc, title, 1)
    if multi_sector or (page.sector and not title):
        _heading(doc, f"Sector {_sector_label(page.sector)}", 2)
    if page.scope_note:
        _note(doc, page.scope_note)
    _figure(doc, page.png, LANDSCAPE_WIDTH_MM, 100, colors=256)

    summary = page.summary
    window = summary.level_window
    if window is not None:
        scope = format_level_window(window)
        if page.level_label:
            noun = "Cotas" if "," in page.level_label else "Cota"
            scope = f"{noun} {page.level_label} ({scope})"
    else:
        scope = "Todo el muro"
    within = "Dentro de umbral" if page.within_m is None else f"Dentro de ±{fmt_es(page.within_m, 1)} m"
    measured = summary.n_measured
    counts = summary.counts or {}
    _table(
        doc,
        (
            "Ámbito", "Celdas", "Medidas", within, "Mediana (m)", "P95 |desv.| (m)",
            "Máx. sobreexcavación", "Máx. faltante",
        ),
        [
            (
                scope,
                _count(summary.n_cells),
                _count(measured),
                _share(int(counts.get("within_tolerance", 0) or 0), measured),
                _signed(summary.median_m, 2),
                fmt_es(summary.p95_abs_m, 2),
                _extreme_text(summary.max_over),
                _extreme_text(summary.max_under),
            )
        ],
        weights=(1.3, 0.7, 0.7, 1.3, 0.8, 0.9, 2.3, 2.3),
        font_pt=COMPACT_TABLE_PT,
        width_mm=LANDSCAPE_WIDTH_MM,
    )
    classes = ", ".join(
        f"{HDEV_LABELS_ES[key]}: {_count(counts.get(key, 0))}" for key in HDEV_CATEGORY_ORDER
    )
    lines = [f"Celdas por clase — {classes}."]
    if page.note:
        lines.append(page.note)
    tail = "Desviación horizontal a igual cota; positiva = sobreexcavación. Resultado calculado en la vista 3D"
    lines.append(f"{tail} ({page.created_at})." if page.created_at else f"{tail}.")
    note = _note(doc, " ".join(lines))
    note.paragraph_format.space_before = Pt(3)
    note.paragraph_format.space_after = Pt(0)


def _add_heatmaps(doc, data: ReportData, context: _Context, title: str) -> None:
    for index, page in enumerate(context.heatmaps):
        _add_heatmap_page(doc, page, title if index == 0 else None, len(context.heatmaps) > 1)
    _new_section(doc, landscape=False)


def _sector_profile_text(data: ReportData, context: _Context, summary: Mapping[str, Any]) -> str:
    sector = str(summary.get("sector") or "")
    tally = (summary.get("headline") or {}).get("profiles") or summary.get("profile_counts") or {}
    total = sum(int(tally.get(key, 0) or 0) for key in ("CUMPLE", "FUERA", "NO_CUMPLE", "UNKNOWN"))
    levels = summary.get("levels") or ()
    selection = (
        ("cota " if len(levels) == 1 else "cotas ") + ", ".join(str(level) for level in levels)
        if levels
        else "todas las cotas"
    )
    pages = len(context.pages_by_sector.get(sector, ()))
    return (
        f"Sector {_sector_label(sector)}, {selection}: "
        f"{_plural(total, 'perfil', 'perfiles')}, {int(tally.get('CUMPLE', 0) or 0)} en CUMPLE; "
        f"puntaje ponderado {fmt_es(summary.get('global_weighted_score'), 1)}. "
        f"{_plural(pages, 'página de perfiles', 'páginas de perfiles')}."
    )


_PROFILE_LAYOUT_TEXT = (
    "Perfiles en el orden en que están definidas las secciones, seis por página "
    "en hoja apaisada (recortados a la cota seleccionada cuando hay filtro de "
    "cota). Cada página lleva el "
    "miniplano de ubicación de sus perfiles y la tabla de detalle de sus bancos."
)


def _add_reading_guide(doc) -> None:
    _heading(doc, "Cómo leer las páginas de perfiles", 2)
    _bullets(doc, _PROFILE_READING_GUIDE)


def _add_profile_pages(doc, data: ReportData, context: _Context,
                       sector: Optional[str] = None) -> None:
    """Append the landscape pages of one sector, or of the whole report."""
    if sector is None:
        expected = bool(context.pages_by_sector)
        selection = {}
    else:
        expected = bool(context.pages_by_sector.get(sector.strip()))
        selection = {"sectors": [sector]}
    before = len(doc.sections)
    try:
        add_profile_pages_docx(doc, data, shade=context.shade, **selection)
    except Exception:
        logger.exception("Profile pages failed")
        if len(doc.sections) > before:
            _new_section(doc, landscape=False)
        doc.add_paragraph("No fue posible generar las páginas de perfiles.")
        return
    if len(doc.sections) > before:
        doc.sections[-1].different_first_page_header_footer = False
    elif not expected:
        doc.add_paragraph("Sin geometría de secciones disponible para las páginas de perfiles.")


def _add_profiles(doc, data: ReportData, context: _Context, title: str) -> None:
    _heading(doc, title, 1, page_break=True)
    pages = sum(len(pages) for pages in context.pages_by_sector.values())
    if pages:
        doc.add_paragraph(f"{_PROFILE_LAYOUT_TEXT} {_plural(pages, 'página', 'páginas')}.")
        _add_reading_guide(doc)
    _add_profile_pages(doc, data, context)


def _add_sector_profiles(doc, data: ReportData, context: _Context, title: str,
                         summary: Mapping[str, Any], first: bool) -> None:
    """One chapter per sector: heading, sector summary and its own pages."""
    sector = str(summary.get("sector") or "")
    _heading(doc, title, 1, page_break=True)
    if first:
        _note(doc, _PROFILE_LAYOUT_TEXT + " Cada sector tiene su propio capítulo, con sus páginas a continuación.")
        if context.pages_by_sector:
            _add_reading_guide(doc)
    doc.add_paragraph(_sector_profile_text(data, context, summary))
    _add_profile_pages(doc, data, context, sector)


def _bench_label(row) -> str:
    if row.type == "EXTRA":
        return "Adic."
    return DASH if row.bench_num is None else f"B{row.bench_num}"


def _bench_score(row) -> str:
    return fmt_es(getattr(row, "bench_score", None), 0)


def _berm_margin(row) -> Optional[float]:
    real, minimum = _finite(row.berm_real), _finite(getattr(row, "berm_min", None))
    return None if real is None or minimum is None else real - minimum


def _identity_columns(multi_sector: bool) -> list[_Column]:
    columns = [
        _Column("Sección", 1.0, lambda r: r.section or DASH),
        _Column("Cota nominal", 0.9, lambda r: r.level_nominal or r.level or DASH),
        _Column("Banco", 0.8, _bench_label),
    ]
    if multi_sector:
        columns.insert(0, _Column("Sector", 1.0, lambda r: _sector_label(r.sector)))
    return columns


def _annex_columns(multi_sector: bool) -> tuple[list[_Column], list[_Column], list[_Column]]:
    kind = _Column("Tipo", 1.3, lambda r: _TYPE_LABELS.get(r.type, r.type or DASH), nowrap=True)
    height_angle = _identity_columns(multi_sector) + [
        kind,
        _Column("Altura diseño (m)", 1.0, lambda r: fmt_es(r.height_design, 2)),
        _Column("Altura real (m)", 1.0, lambda r: fmt_es(r.height_real, 2)),
        _Column("Δ altura (m)", 1.0, lambda r: _signed(r.height_dev, 2)),
        _Column("Ángulo diseño (°)", 1.0, lambda r: fmt_es(r.angle_design, 1)),
        _Column("Ángulo real (°)", 1.0, lambda r: fmt_es(r.angle_real, 1)),
        _Column("Δ ángulo (°)", 1.0, lambda r: _signed(r.angle_dev, 1)),
    ]
    berm = _identity_columns(multi_sector) + [
        _Column("Berma diseño (m)", 1.0, lambda r: fmt_es(r.berm_design, 2)),
        _Column("Berma real (m)", 1.0, lambda r: fmt_es(r.berm_real, 2)),
        _Column("Berma mínima (m)", 1.0, lambda r: fmt_es(getattr(r, "berm_min", None), 2)),
        _Column("Real − mínima (m)", 1.0, lambda r: _signed(_berm_margin(r), 2)),
        _Column(BELOW_MIN_HEADER, 1.0, lambda r: "⚠" if r.design_below_min else DASH, optional=True),
        _Column("Derrame (m)", 1.0, lambda r: fmt_es(r.spill_width, 2), optional=True),
        _Column("Berma efectiva (m)", 1.0, lambda r: fmt_es(r.effective_berm, 2), optional=True),
        _Column("Δ cresta (m)", 1.0, lambda r: _signed(getattr(r, "delta_crest", None), 2), optional=True),
        _Column("Δ pata (m)", 1.0, lambda r: _signed(getattr(r, "delta_toe", None), 2), optional=True),
    ]
    status = _identity_columns(multi_sector) + [
        _Column("Altura", 1.5, lambda r: _short_status(r.height_status), nowrap=True),
        _Column("Ángulo", 1.5, lambda r: _short_status(r.angle_status), nowrap=True),
        _Column("Berma", 1.5, lambda r: _short_status(r.berm_status), nowrap=True),
        _Column("Berma efectiva", 1.5,
                lambda r: _short_status(r.effective_berm_status), optional=True, nowrap=True),
        _Column("Estado del banco", 1.9,
                lambda r: _Chip(r.status_label or DASH, r.worst_status), nowrap=True),
        _Column("Puntaje", 0.8, _bench_score),
    ]
    return height_angle, berm, status


def _ordered_rows(data: ReportData) -> list:
    order: dict[tuple[str, str], int] = {}
    for entry in data.matrix or ():
        order.setdefault((str(entry.get("section", "")), str(entry.get("sector") or "")), len(order))
    fallback = len(order)

    def rank(row) -> tuple:
        position = order.get((row.section, row.sector or ""), fallback)
        bench = math.inf if row.bench_num is None else row.bench_num
        return (position, row.section, bench, row.level or "")

    return sorted(data.rows or (), key=rank)


def _add_annex_table(doc, title: str, columns: Sequence[_Column], rows: Sequence[Any]) -> None:
    _heading(doc, title, 2)
    values = [[column.value(row) for column in columns] for row in rows]
    keep = [
        index
        for index, column in enumerate(columns)
        if not column.optional or any(line[index] != DASH for line in values)
    ]
    dropped = [column.header for index, column in enumerate(columns) if index not in keep]
    if dropped:
        _note(doc, "Columnas sin datos omitidas en esta tabla: " + ", ".join(dropped) + ".")
    left = tuple(index for index, kept in enumerate(keep) if columns[kept].header in ("Sector", "Sección"))
    _table(
        doc,
        [columns[index].header for index in keep],
        [[line[index] for index in keep] for line in values],
        weights=[columns[index].weight for index in keep],
        font_pt=ANNEX_TABLE_PT,
        left=left,
        nowrap=tuple(index for index, kept in enumerate(keep) if columns[kept].nowrap),
    )


def _add_bench_annex(doc, data: ReportData, context: _Context) -> None:
    rows = _ordered_rows(data)
    if not rows:
        doc.add_paragraph("No hay bancos para tabular.")
        return
    doc.add_paragraph(
        f"{_plural(len(rows), 'registro de banco', 'registros de banco')} en el orden "
        "definido de las secciones. Δ = real − diseño; «—» = sin dato. La misma tabla, "
        "con filtros, está en el Excel analítico."
    )
    height_angle, berm, status = _annex_columns(context.multi_sector)
    _add_annex_table(doc, ANNEX_HEIGHT_ANGLE_TITLE, height_angle, rows)
    _add_annex_table(doc, ANNEX_BERM_TITLE, berm, rows)
    if any(row.design_below_min for row in rows):
        _note(
            doc,
            f"⚠ en «{BELOW_MIN_HEADER}»: la berma de diseño es menor que el mínimo; el "
            "estado oficial no cambia.",
        )
    _add_annex_table(doc, ANNEX_STATUS_TITLE, status, rows)
    _note(
        doc,
        "El estado del banco es el oficial (CUMPLE con puntaje ≥ 70; berma 60, altura "
        "30, ángulo 10); un banco no construido o adicional cuenta como NO CUMPLE. "
        + STATUS_LEGEND,
    )


def _text_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _hole_id(hole: Mapping[str, Any]) -> str:
    for key in ("id_pozo", "hole_id", "label_pozo"):
        text = _text_or_none(hole.get(key))
        if text:
            return text
    return NO_DATA


def _listed_ids(holes: Sequence[Mapping[str, Any]]) -> str:
    names = [_hole_id(hole) for hole in holes[:MAX_LISTED_IDS]]
    text = ", ".join(names)
    rest = len(holes) - len(names)
    return f"{text} y {fmt_es(rest, 0)} más" if rest > 0 else text


def _hole_mean(holes: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
    values = [value for value in (_finite(hole.get(key)) for hole in holes) if value is not None]
    return math.fsum(values) / len(values) if values else None


def _explosive_text(holes: Sequence[Mapping[str, Any]]) -> str:
    tally: dict[str, int] = {}
    for hole in holes:
        name = _text_or_none(hole.get("Tipo_Explosivo"))
        if name:
            tally[name] = tally.get(name, 0) + 1
    if not tally:
        return DASH
    if len(tally) == 1:
        return next(iter(tally))
    ranked = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    return "; ".join(f"{name} ({count})" for name, count in ranked)


def _blast_events(holes: Sequence[Mapping[str, Any]]) -> list[tuple]:
    """One row per blast event (date, pattern, blast, phase); never per hole."""
    groups: dict[tuple, list[Mapping[str, Any]]] = {}
    for hole in holes:
        key = tuple(_text_or_none(hole.get(name)) for name in _BLAST_GROUP_KEYS)
        groups.setdefault(key, []).append(hole)
    rows = []
    for key in sorted(groups, key=lambda item: tuple(value or "" for value in item)):
        members = groups[key]
        date, mesh, blast, phase = key
        kilos = [v for v in (_finite(h.get("Kilos_Cargados_real")) for h in members) if v is not None]
        with_pf = sum(
            1 for hole in members
            if _finite(hole.get(PRIMARY_PF_KEY)) is not None or _finite(hole.get("pf_g_per_ton")) is not None
        )
        rows.append(
            (
                date or DASH,
                mesh or (DASH if blast else UNIDENTIFIED_EVENT),
                blast or DASH,
                phase or DASH,
                str(len(members)),
                fmt_es(math.fsum(kilos), 0) if kilos else DASH,
                fmt_es(_hole_mean(members, PRIMARY_PF_KEY), 1),
                fmt_es(_hole_mean(members, "pf_g_per_ton"), 1),
                fmt_es(_hole_mean(members, "pf_g_per_ton_net"), 1),
                str(with_pf),
                _explosive_text(members),
            )
        )
    return rows


def _blast_frame_rows(holes: Sequence[Mapping[str, Any]]) -> list[dict]:
    rows = []
    for hole in holes:
        row = {key: hole.get(key) for key in ("Z_collar", "Z_toe", "Len", "Incl", "bench_height_m") if key in hole}
        for canonical, alternates in (
            ("Z_collar", ("collar_z", "z_collar", "collar")),
            ("Z_toe", ("toe_z", "z_toe", "toe")),
        ):
            if canonical not in row:
                for alternate in alternates:
                    if alternate in hole:
                        row[canonical] = hole[alternate]
                        break
        rows.append(row)
    return rows


def _blast_metric_rows(blast: Mapping[str, Any], holes: Sequence[Mapping[str, Any]], n_events: int) -> list:
    rows = [
        ("Total de pozos registrados", fmt_es(len(holes), 0)),
        ("Mallas o eventos de tronadura", str(n_events)),
    ]
    stats = None
    try:
        import pandas as pd

        from core.blast_correlation import compute_pasadura_stats

        stats = compute_pasadura_stats(pd.DataFrame(_blast_frame_rows(holes)))
    except Exception:
        logger.exception("Sub-drill statistics failed")
    if not stats or stats.get("bench_height_status") in ("MISSING", "INVALID"):
        rows.append(("Altura de banco", "No confirmada: pasadura bloqueada (sin supuesto automático)"))
        rows.append(("Pasadura promedio", "No disponible sin altura de banco"))
    else:
        mean = _finite(stats.get("mean"))
        rows.append(("Pasadura promedio", "No disponible" if mean is None else fmt_es(mean, 2, "m")))
        rows.append(
            (
                "Pozos en pasadura óptima (0,5 a 1,5 m)",
                f"{fmt_es(stats.get('optimal_pct'), 1, '%')} "
                f"({_plural(int(stats.get('optimal_count') or 0), 'pozo', 'pozos')})",
            )
        )
    tolerance = blast.get("tolerance")
    if isinstance(tolerance, Mapping):
        text = _tolerance_text(tolerance, "signed", 2)
        if text:
            rows.append(("Tolerancia cresta-pata aplicada", f"{text} m"))
    elif _finite(tolerance) is not None:
        rows.append(("Tolerancia de proyección de pozos", f"±{fmt_es(abs(float(tolerance)), 2, 'm')}"))
    return rows


def _add_blast_audit(doc, blast: Mapping[str, Any], holes: Sequence[Mapping[str, Any]]) -> None:
    from core.blast_correlation import PF_DEFINITIONS

    _heading(doc, "Bloque de auditoría", 2)
    lines: list[str] = []
    if blast.get("data_status") == "legacy_reimport_required":
        lines.append(
            f"{REIMPORT_WARNING} Pozos afectados ({fmt_es(len(holes), 0)}): {_listed_ids(holes)}."
        )
    without_pf = [hole for hole in holes if _finite(hole.get(PRIMARY_PF_KEY)) is None]
    if without_pf:
        lines.append(
            f"Pozos {NO_DATA} de FC principal: {fmt_es(len(without_pf), 0)} de "
            f"{fmt_es(len(holes), 0)} — {_listed_ids(without_pf)}."
        )
    statuses: dict[str, int] = {}
    for hole in holes:
        status = _text_or_none(hole.get("pf_voronoi_bench_status")) or NO_DATA
        statuses[status] = statuses.get(status, 0) + 1
    ranked = sorted(statuses.items(), key=lambda item: (-item[1], item[0]))
    lines.append(
        "Estado del FC principal por pozo: "
        + ", ".join(f"{status} {fmt_es(count, 0)}" for status, count in ranked)
        + "."
    )
    consolidation = blast.get("consolidation_report")
    if isinstance(consolidation, Mapping) and consolidation:
        def reported(key: str) -> str:
            value = consolidation.get(key)
            return NO_DATA if value is None else str(value)

        lines.append(
            f"Consolidación: pozos {reported('holes_out')}; copias eliminadas "
            f"{reported('exact_copies_removed')}; filas de decks fusionadas "
            f"{reported('deck_rows_merged')}."
        )
    with_decks = [hole for hole in holes if hole.get("decks")]
    if with_decks:
        removed = sum(int(_finite(hole.get("duplicate_rows_removed")) or 0) for hole in with_decks)
        lines.append(
            f"Pozos con carga por decks: {fmt_es(len(with_decks), 0)} — "
            f"{_listed_ids(with_decks)}; copias eliminadas en esos pozos: {removed}."
        )
    estimated = [
        hole for hole in holes
        if hole.get("Z_collar_semantic", hole.get("z_collar_semantic")) == "design_surface_estimate"
    ]
    if estimated:
        lines.append(
            f"Advertencia: la cota Z del collar de {_plural(len(estimated), 'pozo', 'pozos')} "
            "fue estimada desde la superficie de diseño; no es una medición de terreno y "
            "no debe interpretarse como cota real levantada."
        )
    assumed = sum(1 for hole in holes if hole.get("explosive_assumption_flag") is True)
    if assumed:
        lines.append(
            f"Explosivo con propiedades de referencia no validada: "
            f"{fmt_es(assumed, 0)} de {fmt_es(len(holes), 0)} pozos."
        )
    _bullets(doc, lines)

    _paragraph(doc, "Definiciones de factor de carga (FC)", bold=True)
    definitions = [(f"{PRIMARY_PF_KEY} (FC principal)", PRIMARY_PF_FORMULA, "g/t")]
    definitions += [
        (name, str(definition["formula"]), str(definition["unit"]))
        for name, definition in PF_DEFINITIONS.items()
    ]
    _table(doc, ("Indicador", "Fórmula", "Unidad"), definitions, weights=(1.7, 1.8, 0.6),
           font_pt=COMPACT_TABLE_PT, left=(0, 1))
    _note(
        doc,
        "FC principal: área de Voronoi por huella y altura de banco. FC y FC neto de la "
        "tabla por evento corresponden a pf_g_per_ton y pf_g_per_ton_net. Los valores "
        "por pozo son los ya calculados en la sesión; aquí solo se promedian.",
    )


def _add_blast_annex(doc, data: ReportData, context: _Context) -> None:
    blast = data.blast
    if not isinstance(blast, Mapping):
        doc.add_paragraph("Sin datos de pozos de tronadura en esta sesión.")
        return
    holes = context.blast_holes
    if not holes:
        doc.add_paragraph("La sesión declara configuración de tronadura pero no pozos registrados.")
        return
    events = _blast_events(holes)
    doc.add_paragraph(
        f"{fmt_es(len(holes), 0)} pozos en {len(events)} mallas o eventos. Resumen por "
        "evento: el detalle por pozo no se incluye en este informe. Incluye todos los "
        "pozos de la sesión; los filtros de sector, sección y cota no los restringen."
    )
    _table(doc, ("Métrica", "Valor"), _blast_metric_rows(blast, holes, len(events)), weights=(1.8, 1.6), left=(0, 1))

    _heading(doc, "Resumen por evento", 2)
    headers = list(_BLAST_EVENT_HEADERS)
    weights = list(_BLAST_EVENT_WEIGHTS)
    primary = headers.index(_BLAST_PRIMARY_HEADER)
    note = "FC = factor de carga medio de los pozos del evento con ese dato; «—» = sin dato."
    if all(event[primary] == DASH for event in events):
        events = [event[:primary] + event[primary + 1:] for event in events]
        del headers[primary], weights[primary]
        note += f" Columna sin datos omitida: {_BLAST_PRIMARY_HEADER}."
    with_pf, holes_column = headers.index(_BLAST_WITH_PF_HEADER), headers.index("Pozos")
    if all(event[with_pf] == event[holes_column] for event in events):
        events = [event[:with_pf] + event[with_pf + 1:] for event in events]
        del headers[with_pf], weights[with_pf]
        note += " Todos los pozos de cada evento tienen FC."
    _table(
        doc, headers, events, weights=weights, font_pt=ANNEX_TABLE_PT,
        left=(0, 1, len(headers) - 1), nowrap=(0,),
    )
    _note(doc, note)
    _add_blast_audit(doc, blast, holes)


def _section_names(names: Sequence[str]) -> str:
    unique = list(dict.fromkeys(names))
    text = ", ".join(unique[:MAX_LISTED_SECTIONS])
    return text + ", …" if len(unique) > MAX_LISTED_SECTIONS else text


def _aggregated_warnings(data: ReportData) -> list[str]:
    """Report and per-section warnings, each text once with its count."""
    general: dict[str, int] = {}
    for warning in data.warnings or ():
        general[str(warning)] = general.get(str(warning), 0) + 1
    by_section: dict[str, list[str]] = {}
    for entry in data.section_geometry or ():
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("section_name") or "")
        for warning in entry.get("warnings") or ():
            by_section.setdefault(str(warning), []).append(name)
    for excavation in data.excavation or ():
        for warning in excavation.warnings or ():
            by_section.setdefault(str(warning), []).append(str(excavation.section))

    lines = [text if count == 1 else f"{text} (×{count})" for text, count in general.items()]
    for text, names in by_section.items():
        unique = list(dict.fromkeys(names))
        lines.append(
            f"{text} — {_plural(len(unique), 'sección', 'secciones')}: {_section_names(unique)}."
        )
    return lines


def _add_conclusions(doc, data: ReportData, context: _Context) -> None:
    _heading(doc, "Conclusiones", 2)
    conclusions = [str(conclusion) for conclusion in data.conclusions or ()]
    if conclusions:
        _bullets(doc, conclusions)
    else:
        doc.add_paragraph("El modelo no generó conclusiones para este informe.")
    _heading(doc, "Advertencias", 2)
    warnings = _aggregated_warnings(data)
    if warnings:
        _bullets(doc, warnings)
    else:
        doc.add_paragraph("Sin advertencias para este informe.")


def _chapter_plan(data: ReportData, context: _Context) -> list[tuple[str, int, Optional[Callable]]]:
    """Ordered ``(title, index level, writer)`` entries; writers own level-0 chapters."""
    number = 0

    def numbered(title: str) -> str:
        nonlocal number
        number += 1
        return f"{number}. {title}"

    def chapter(title: str, writer: Callable) -> tuple[str, int, Callable]:
        def write(doc) -> None:
            _heading(doc, title, 1, page_break=True)
            writer(doc, data, context)

        return (title, 0, write)

    plan: list[tuple[str, int, Optional[Callable]]] = [
        chapter(numbered(SUMMARY_TITLE), _add_summary),
        chapter(numbered(CRITERIA_TITLE), _add_criteria),
        chapter(numbered(ANALYSIS_TITLE), _add_analysis),
    ]
    if context.heatmaps:
        heatmap_title = numbered(HEATMAP_TITLE)
        plan.append((heatmap_title, 0, lambda doc: _add_heatmaps(doc, data, context, heatmap_title)))

    if context.multi_sector:
        for index, summary in enumerate(data.sector_summaries):
            title = numbered(f"{PROFILES_TITLE} — sector {_sector_label(summary.get('sector'))}")
            plan.append(
                (
                    title,
                    0,
                    lambda doc, title=title, summary=summary, first=index == 0: _add_sector_profiles(
                        doc, data, context, title, summary, first
                    ),
                )
            )
    else:
        profiles_title = numbered(PROFILES_TITLE)
        plan.append((profiles_title, 0, lambda doc: _add_profiles(doc, data, context, profiles_title)))

    plan.append(chapter(BENCH_ANNEX_TITLE, _add_bench_annex))
    if data.rows:
        plan += [(title, 1, None) for title in (ANNEX_HEIGHT_ANGLE_TITLE, ANNEX_BERM_TITLE, ANNEX_STATUS_TITLE)]
    plan.append(chapter(BLAST_ANNEX_TITLE, _add_blast_annex))
    plan.append(chapter(EXCAVATION_ANNEX_TITLE, _add_excavation_annex))
    plan.append(chapter(numbered(CONCLUSIONS_TITLE), _add_conclusions))
    return plan


def build_word_report(data: ReportData) -> io.BytesIO:
    """Render the technical Word report for ``data`` and return it as a ``BytesIO``.

    The buffer is positioned at the start so callers can stream it directly.
    Every chapter degrades to a one-line note when its input is missing.
    """
    doc = Document()
    configure_document(doc, data.meta)
    _apply_page(doc.sections[0], landscape=False)

    context = _build_context(data)
    plan = _chapter_plan(data, context)

    _add_cover(doc, data)
    _add_index(doc, [(title, level) for title, level, _writer in plan])
    for _title, _level, writer in plan:
        if writer is not None:
            writer(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
