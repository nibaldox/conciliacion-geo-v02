"""Executive PDF report for the web export built from ``ReportData``.

A4-portrait Spanish dashboard of four to six pages: compliance dashboard
(scope, headline, KPI tiles, plan view, status matrix), sector comparison
when the report spans several sectors, deviation analysis, excavation
estimates, one page per persisted horizontal-deviation heatmap, and the
conclusions with aggregated warnings and KPI definitions. Per-bench,
per-section and per-hole detail belongs to the Word and Excel exports; this
document only carries aggregates of the official values.
"""

from __future__ import annotations

import io
import logging
import math
import os
import re
import threading
from collections import Counter
from dataclasses import replace
from datetime import datetime
from statistics import median
from typing import Any, Callable, Mapping, Optional, Sequence
from xml.sax.saxutils import escape

from reportlab import __file__ as reportlab_path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepInFrame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from core.report_charts import STATUS_COLORS, STATUS_LABELS_ES
from core.report_data import ReportData, parse_bench_status
from core.report_figures_analysis import (
    deviation_histograms_png,
    excavation_bars_png,
    status_matrix_png,
    trend_png,
)
from core.report_figures_heatmap import (
    HDEV_CATEGORY_ORDER,
    HDEV_COLORS,
    HDEV_LABELS_ES,
    HeatmapSummary,
    format_level_window,
    heatmap_page_png,
    heatmap_summary,
    level_window_from_geometry,
)
from core.report_figures_plan import dashboard_plan_png
from core.report_surface import plan_surface_from_mesh, sections_bounds, shaded_relief
from core.report_texts import (
    DASH,
    fmt_es,
    headline_text,
    heatmap_position_note,
    kpi_definitions,
    scope_lines,
)

logger = logging.getLogger(__name__)

PAGE_WIDTH, PAGE_HEIGHT = A4
PAGE_MARGIN = 1.5 * cm
TOP_MARGIN = 1.9 * cm
BOTTOM_MARGIN = 1.5 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * PAGE_MARGIN
CONTENT_HEIGHT = PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN
CONTENT_WIDTH_IN = CONTENT_WIDTH / 72.0

COLOR_NAVY = colors.HexColor("#1F3A5F")
COLOR_ALT_ROW = colors.HexColor("#F2F4F8")
COLOR_TILE = colors.HexColor("#F3F5F9")
COLOR_MUTED = colors.HexColor("#4B5563")
COLOR_INK = colors.HexColor("#1F2937")
COLOR_RULE = colors.HexColor("#CBD5E1")

STATUS_FILL = {
    "CUMPLE": colors.HexColor("#C8E6C9"),
    "FUERA": colors.HexColor("#FFE0B2"),
    "NO_CUMPLE": colors.HexColor("#FFCDD2"),
    "UNKNOWN": colors.HexColor("#E2E8F0"),
}

STATUS_TEXT = {
    "CUMPLE": colors.HexColor("#1B5E20"),
    "FUERA": colors.HexColor("#8A4B00"),
    "NO_CUMPLE": colors.HexColor("#8E1F1F"),
    "UNKNOWN": colors.HexColor("#334155"),
}

PROFILE_STATUS_ORDER = ("CUMPLE", "FUERA", "NO_CUMPLE")
_STATUS_SHORT = {"CUMPLE": "Cumple", "FUERA": "Fuera", "NO_CUMPLE": "No cumple", "UNKNOWN": "Sin evaluar"}

_PARAMETER_LABELS = {
    "height": ("Altura de banco", "m", 2),
    "angle": ("Ángulo de cara", "°", 1),
    "berm": ("Ancho de berma", "m", 2),
}
_PARAMETER_SHORT = {"height": "Altura", "angle": "Ángulo", "berm": "Berma"}

_TOLERANCE_ROWS = (
    ("bench_height", "altura de banco", "m", 2),
    ("face_angle", "ángulo de cara", "°", 1),
    ("berm_width", "ancho de berma", "m", 2),
    ("crest_toe_deviation", "desviación cresta-pata", "m", 2),
)
_TOLERANCE_KEY = {"height": "bench_height", "angle": "face_angle", "berm": "berm_width"}

MAX_TOP_DEVIATIONS = 10
MAX_BLAST_ROWS = 5
MAX_LISTED_HOLES = 12
NO_DATA_TEXT = "sin dato"
LEGACY_BLAST_WARNING = "Datos de pozos importados con una versión anterior: reimportar"
PF_MAIN_FORMULA = "1000*Q/(A*H*rho)"
MAX_WARNING_LINES = 12
MAX_SCOPE_LINES = 8
MAX_LEVEL_ROWS = 10
MAX_SECTORS_PER_TABLE = 4
_EXTRA_BENCH_NUMBER = 999

EXCAVATION_METHOD_LINE = (
    "volumen = área × ancho de influencia; ancho = separación real entre secciones"
)
NO_ROWS_TEXT = "No hay comparaciones para reportar con los filtros aplicados."
NO_PLAN_TEXT = "No hay geometría de secciones disponible para generar el plano en este informe."

_PLAN_HEIGHT_IN = 3.8
_MATRIX_HEIGHT_IN = 2.45
_HISTOGRAM_HEIGHT_IN = 2.75
_TREND_HEIGHT_IN = 2.95
_EXCAVATION_HEIGHT_IN = 3.7
_HEATMAP_HEIGHT_IN = 4.6

_REPORTLAB_FONTS = os.path.join(os.path.dirname(reportlab_path), "fonts")
_FONT_FILES = (
    ("GeoVera", "Vera.ttf"),
    ("GeoVera-Bold", "VeraBd.ttf"),
    ("GeoVera-Italic", "VeraIt.ttf"),
    ("GeoVera-BoldItalic", "VeraBI.ttf"),
)

_GLYPH_FALLBACKS = {
    "\u202f": "\u00a0",
    "\u2009": "\u00a0",
    "⅓": "1/3",
    "½": "1/2",
    "¼": "1/4",
    "Δ": "Desv.",
    "⚠": "!",
    "▲": "máx.",
    "▼": "mín.",
    "●": "·",
    "→": "->",
    "≥": ">=",
    "≤": "<=",
    "≈": "~",
    "−": "-",
    "…": "...",
    "—": "-",
    "–": "-",
    "×": "x",
}
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")


def _register_report_fonts(font_dir: str) -> tuple[str, str]:
    if not all(os.path.isfile(os.path.join(font_dir, filename)) for _, filename in _FONT_FILES):
        return "Helvetica", "Helvetica-Bold"
    for font_name, filename in _FONT_FILES:
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_name, os.path.join(font_dir, filename)))
    pdfmetrics.registerFontFamily(
        "GeoVera",
        normal="GeoVera",
        bold="GeoVera-Bold",
        italic="GeoVera-Italic",
        boldItalic="GeoVera-BoldItalic",
    )
    return "GeoVera", "GeoVera-Bold"


def _font_coverage(font_name: str) -> Optional[frozenset]:
    face = getattr(pdfmetrics.getFont(font_name), "face", None)
    glyphs = getattr(face, "charToGlyph", None)
    return frozenset(glyphs) if glyphs else None


_BODY_FONT, _BOLD_FONT = _register_report_fonts(_REPORTLAB_FONTS)
_ITALIC_FONT = "GeoVera-Italic" if _BODY_FONT == "GeoVera" else "Helvetica-Oblique"
_FONT_COVERAGE = _font_coverage(_BODY_FONT)
_PDF_BUILD_LOCK = threading.RLock()


def _safe(value: Any) -> str:
    """Text with the glyphs the report font lacks replaced by a readable fallback."""
    text = DASH if value is None else str(value)
    out = []
    for char in text:
        if char in _GLYPH_FALLBACKS and (
            _FONT_COVERAGE is None or ord(char) not in _FONT_COVERAGE
        ):
            out.append(_GLYPH_FALLBACKS[char])
        else:
            out.append(char)
    return "".join(out)


def _esc(value: Any) -> str:
    return escape(_safe(value))


def _num(value: Any, decimals: int = 1, unit: Optional[str] = None) -> str:
    return _safe(fmt_es(value, decimals, unit))


def _signed(value: Any, decimals: int = 1, unit: Optional[str] = None) -> str:
    text = fmt_es(value, decimals, unit)
    number = _finite(value)
    if number is not None and round(number, decimals) > 0:
        text = "+" + text
    return _safe(text)


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value) if math.isfinite(value) and value > 0 else 0


def _fmt_date(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        return datetime.fromisoformat(text).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text


def _localized(text: Any) -> str:
    return _DECIMAL_POINT.sub(",", str(text))


class _NumberedCanvas(pdf_canvas.Canvas):
    """Canvas stamping the project header and the ``Página X de Y`` footer."""

    def __init__(self, *args: Any, project: str = "", generated: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._project = project or "Proyecto no especificado"
        self._generated = generated
        self._states: list[dict] = []

    def showPage(self) -> None:
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._states)
        for index, state in enumerate(self._states, start=1):
            self.__dict__.update(state)
            self._draw_chrome(index, total)
            super().showPage()
        super().save()

    def _draw_chrome(self, page: int, total: int) -> None:
        self.saveState()
        top = PAGE_HEIGHT - 1.15 * cm
        self.setFillColor(COLOR_NAVY)
        self.setFont(_BOLD_FONT, 9)
        self.drawString(PAGE_MARGIN, top, _safe(self._project)[:70])
        self.setFont(_BODY_FONT, 8)
        self.setFillColor(COLOR_MUTED)
        self.drawRightString(PAGE_WIDTH - PAGE_MARGIN, top, "Informe de conciliación geotécnica")
        self.setStrokeColor(COLOR_NAVY)
        self.setLineWidth(0.6)
        self.line(PAGE_MARGIN, top - 0.25 * cm, PAGE_WIDTH - PAGE_MARGIN, top - 0.25 * cm)
        self.setFont(_BODY_FONT, 7.5)
        if self._generated:
            self.drawString(PAGE_MARGIN, 0.95 * cm, _safe(f"Generado el {self._generated}"))
        self.drawRightString(PAGE_WIDTH - PAGE_MARGIN, 0.95 * cm, f"Página {page} de {total}")
        self.restoreState()


class _StatusBar(Flowable):
    """Stacked horizontal bar of counts; an empty total draws an outlined dash."""

    def __init__(self, segments: Sequence[tuple[int, str]], width: float, height: float = 10.0) -> None:
        super().__init__()
        self.segments = [(int(count), color) for count, color in segments if count > 0]
        self.width = width
        self.height = height

    def wrap(self, _avail_width: float, _avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        canvas = self.canv
        total = sum(count for count, _color in self.segments)
        if total <= 0:
            canvas.setStrokeColor(COLOR_RULE)
            canvas.setLineWidth(0.5)
            canvas.rect(0, 0, self.width, self.height, stroke=1, fill=0)
            canvas.setFillColor(COLOR_MUTED)
            canvas.setFont(_BODY_FONT, 7)
            canvas.drawCentredString(self.width / 2.0, self.height / 2.0 - 2.5, _safe(DASH))
            return
        x = 0.0
        for count, color in self.segments:
            width = self.width * count / total
            canvas.setFillColor(colors.HexColor(color))
            canvas.rect(x, 0, width, self.height, stroke=0, fill=1)
            label = str(count)
            if width >= pdfmetrics.stringWidth(label, _BOLD_FONT, 7) + 4:
                canvas.setFillColor(colors.white)
                canvas.setFont(_BOLD_FONT, 7)
                canvas.drawCentredString(x + width / 2.0, self.height / 2.0 - 2.5, label)
            x += width


def _report_styles() -> dict:
    """Paragraph styles of the executive report in the registered font family."""
    body = ParagraphStyle(
        "Body", fontName=_BODY_FONT, fontSize=8.5, leading=11, textColor=COLOR_INK, spaceAfter=3
    )
    cell = ParagraphStyle("Cell", parent=body, fontSize=7.5, leading=9.5, spaceAfter=0)
    styles = {
        "body": body,
        "title": ParagraphStyle(
            "Title", parent=body, fontName=_BOLD_FONT, fontSize=16, leading=20,
            textColor=COLOR_NAVY, spaceAfter=2,
        ),
        "h1": ParagraphStyle(
            "H1", parent=body, fontName=_BOLD_FONT, fontSize=13, leading=16,
            textColor=COLOR_NAVY, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "H2", parent=body, fontName=_BOLD_FONT, fontSize=9.5, leading=12,
            textColor=COLOR_NAVY, spaceBefore=7, spaceAfter=3,
        ),
        "meta": ParagraphStyle("Meta", parent=body, fontSize=7.5, leading=10, textColor=COLOR_MUTED),
        "scope": ParagraphStyle("Scope", parent=body, fontSize=7.5, leading=10, spaceAfter=0),
        "headline": ParagraphStyle(
            "Headline", parent=body, fontName=_BOLD_FONT, fontSize=12.5, leading=16,
            spaceBefore=6, spaceAfter=4,
        ),
        "note": ParagraphStyle(
            "Note", parent=body, fontSize=7, leading=9, textColor=COLOR_MUTED, spaceBefore=3,
            spaceAfter=2
        ),
        "callout": ParagraphStyle(
            "Callout", parent=body, fontName=_ITALIC_FONT, fontSize=8, leading=10.5,
            textColor=COLOR_NAVY, spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=body, leftIndent=11, bulletIndent=2, spaceAfter=2
        ),
        "warn": ParagraphStyle(
            "Warn", parent=body, leftIndent=11, bulletIndent=2, spaceAfter=2,
            textColor=STATUS_TEXT["NO_CUMPLE"],
        ),
        "cell": cell,
        "cell_center": ParagraphStyle("CellCenter", parent=cell, alignment=1),
        "cell_right": ParagraphStyle("CellRight", parent=cell, alignment=2),
        "cell_bold": ParagraphStyle("CellBold", parent=cell, fontName=_BOLD_FONT),
        "table_header": ParagraphStyle(
            "TableHeader", parent=cell, fontName=_BOLD_FONT, fontSize=7, leading=8.5,
            textColor=colors.white, alignment=1,
        ),
        "table_header_left": ParagraphStyle(
            "TableHeaderLeft", parent=cell, fontName=_BOLD_FONT, fontSize=7, leading=8.5,
            textColor=colors.white,
        ),
        "tile_label": ParagraphStyle(
            "TileLabel", parent=cell, fontName=_BOLD_FONT, fontSize=8, leading=10,
            textColor=COLOR_NAVY, spaceAfter=3,
        ),
        "tile_value": ParagraphStyle(
            "TileValue", parent=cell, fontName=_BOLD_FONT, fontSize=18, leading=22, spaceAfter=2
        ),
        "tile_note": ParagraphStyle(
            "TileNote", parent=cell, fontSize=6.8, leading=8.5, textColor=COLOR_MUTED
        ),
    }
    return styles


def _status_style(status: str, styles: dict) -> ParagraphStyle:
    return ParagraphStyle(
        f"Status{status}", parent=styles["cell_center"], fontName=_BOLD_FONT,
        fontSize=7, leading=8.5, textColor=STATUS_TEXT[status],
    )


def _grid_table(rows: list, col_widths: Sequence[float], *, header: bool = True,
                extra: Sequence[tuple] = ()) -> Table:
    table = Table(rows, colWidths=list(col_widths), hAlign="LEFT", repeatRows=1 if header else 0)
    commands: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_NAVY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    first_body = 0
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY))
        first_body = 1
    commands.append(("ROWBACKGROUNDS", (0, first_body), (-1, -1), [colors.white, COLOR_ALT_ROW]))
    commands.extend(extra)
    table.setStyle(TableStyle(commands))
    return table


def _image(png_bytes: bytes, max_width: float, max_height: Optional[float] = None) -> Image:
    reader = ImageReader(io.BytesIO(png_bytes))
    width, height = reader.getSize()
    limit = CONTENT_HEIGHT if max_height is None else max_height
    ratio = min(max_width / float(width), limit / float(height))
    return Image(
        io.BytesIO(png_bytes),
        width=float(width) * ratio,
        height=float(height) * ratio,
        hAlign="CENTER",
    )


def _figure(render: Callable[..., Optional[bytes]], *args: Any, **kwargs: Any) -> Optional[bytes]:
    try:
        return render(*args, **kwargs)
    except Exception:
        logger.exception("Report figure %s failed", getattr(render, "__name__", render))
        return None


def _figure_block(story: list, png: Optional[bytes], height_in: float, styles: dict,
                  missing: str = "Sin datos suficientes para esta figura.") -> None:
    if png:
        story.append(_image(png, CONTENT_WIDTH, max_height=height_in * 72.0))
    else:
        story.append(Paragraph(_esc(missing), styles["note"]))


def _sector_label(sector: Any) -> str:
    return f"Sector {sector}" if sector else "Sin sector"


def _tolerance_value(tolerance: Any, unit: str, decimals: int) -> str:
    if not isinstance(tolerance, Mapping):
        return DASH
    neg = _finite(tolerance.get("neg"))
    pos = _finite(tolerance.get("pos"))
    if neg is not None and pos is not None:
        if abs(abs(neg) - pos) < 1e-9:
            return f"± {fmt_es(pos, decimals, unit)}"
        return f"{fmt_es(-abs(neg), decimals, unit)} / +{fmt_es(pos, decimals, unit)}"
    minimum = _finite(tolerance.get("min"))
    if minimum is not None:
        return f"≥ {fmt_es(minimum, decimals, unit)}"
    maximum = _finite(tolerance.get("max"))
    if maximum is not None:
        return f"≤ {fmt_es(maximum, decimals, unit)}"
    return DASH


def _tolerances_line(data: ReportData) -> Optional[str]:
    parts = []
    for key, label, unit, decimals in _TOLERANCE_ROWS:
        if key in (data.tolerances or {}):
            parts.append(f"{label} {_tolerance_value(data.tolerances.get(key), unit, decimals)}")
    return " · ".join(parts) if parts else None


def _geometry_entry(entry: Any) -> Optional[dict]:
    if isinstance(entry, Mapping):
        return dict(entry)
    name = getattr(entry, "name", None)
    if name is None:
        return None
    origin = getattr(entry, "origin", None)
    return {
        "name": str(name),
        "sector": getattr(entry, "sector", "") or "",
        "origin": None if origin is None else [float(value) for value in origin],
        "azimuth": getattr(entry, "azimuth", None),
        "length": getattr(entry, "length", None),
    }


def _raw_plan_sections(data: ReportData) -> Sequence[Any]:
    plan_inputs = data.plan_inputs
    raw: Any = None
    if isinstance(plan_inputs, Mapping):
        raw = plan_inputs.get("sections")
    elif isinstance(plan_inputs, (list, tuple)):
        raw = plan_inputs
    if not raw:
        raw = [
            geometry
            for geometry in (data.section_geometry or ())
            if isinstance(geometry, Mapping) and ("origin" in geometry or "polyline" in geometry)
        ]
    return raw or ()


def _plan_sections(data: ReportData) -> list[dict]:
    """Plan sections with their filter inclusion and official profile status."""
    sections = []
    for entry in _raw_plan_sections(data):
        section = _geometry_entry(entry)
        if section is None:
            continue
        name = section.get("name") or section.get("section") or section.get("section_name")
        section["name"] = "" if name is None else str(name)
        sections.append(section)

    name_counts = Counter(section["name"] for section in sections)
    for section in sections:
        state = data.resolve_section_plan_state(
            section["name"],
            section.get("sector"),
            infer_missing_sector=name_counts[section["name"]] == 1,
        )
        if state is None:
            section["included"] = True
            section["sector"] = ""
            section["worst_status"] = "UNKNOWN"
        else:
            _name, sector, included, status = state
            section["included"] = included
            section["sector"] = sector or ""
            section["worst_status"] = status
    return sections


def _plan_statuses(sections: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Worst official status per section name; excluded or ambiguous names stay unset."""
    by_name: dict[str, set[str]] = {}
    for section in sections:
        status = section.get("worst_status") if section.get("included") else "UNKNOWN"
        by_name.setdefault(str(section.get("name", "")), set()).add(str(status or "UNKNOWN"))
    return {
        name: next(iter(statuses))
        for name, statuses in by_name.items()
        if len(statuses) == 1 and "UNKNOWN" not in statuses
    }


def _plan_backdrop(data: ReportData) -> tuple[Any, Any]:
    plan_inputs = data.plan_inputs
    if not isinstance(plan_inputs, Mapping) or plan_inputs.get("mesh_topo") is None:
        return None, None
    try:
        surface = plan_surface_from_mesh(
            plan_inputs["mesh_topo"], bounds=sections_bounds(plan_inputs.get("sections"))
        )
        shade = shaded_relief(surface) if surface is not None else None
    except Exception:
        logger.exception("Plan backdrop failed; the plan is drawn without relief")
        return None, None
    return surface, shade


def _render_plan(data: ReportData) -> Optional[bytes]:
    sections = _plan_sections(data)
    if not sections:
        return None
    surface, shade = _plan_backdrop(data)
    return _figure(
        dashboard_plan_png,
        sections,
        _plan_statuses(sections),
        shade=shade,
        surface=surface,
        width_in=CONTENT_WIDTH_IN,
        height_in=_PLAN_HEIGHT_IN,
    )


def _profile_tally(headline: Any, profile_counts: Any) -> dict[str, int]:
    profiles = headline.get("profiles") if isinstance(headline, Mapping) else None
    source = profiles if isinstance(profiles, Mapping) and profiles else (profile_counts or {})
    return {key: _count(source.get(key)) for key in (*PROFILE_STATUS_ORDER, "UNKNOWN")}


def _status_segments(tally: Mapping[str, int]) -> list[tuple[int, str]]:
    return [(tally.get(key, 0), STATUS_COLORS[key]) for key in (*PROFILE_STATUS_ORDER, "UNKNOWN")]


def _status_counts_text(tally: Mapping[str, int]) -> str:
    parts = [f"{_STATUS_SHORT[key]} {tally.get(key, 0)}" for key in PROFILE_STATUS_ORDER]
    if tally.get("UNKNOWN"):
        parts.append(f"{_STATUS_SHORT['UNKNOWN']} {tally['UNKNOWN']}")
    return " · ".join(parts)


def _pct_with_n(pct: Any, n: Any) -> str:
    return f"{fmt_es(pct, 1, '%')} (n = {_count(n)})"


def _status_key(value: Any) -> str:
    text = str(value or "")
    return text if text in STATUS_FILL else parse_bench_status(value)


def _achievement_note(achievement: Mapping[str, Any]) -> list[str]:
    parts = []
    for key, label in (("crest", "cresta"), ("toe", "pata"), ("berm", "berma")):
        parts.append(
            f"{label} {fmt_es(achievement.get(f'{key}_pct'), 0, '%')} "
            f"(n = {_count(achievement.get(f'{key}_denom'))})"
        )
    return parts


def _kpi_tiles(data: ReportData, styles: dict) -> Table:
    widths = [4.2 * cm, 3.2 * cm, 3.6 * cm, 7.0 * cm]
    pad = 6.0
    tally = _profile_tally(data.headline, data.profile_counts)
    n_profiles = sum(tally.values())
    profiles_tile = [
        Paragraph("Perfiles por estado", styles["tile_label"]),
        _StatusBar(_status_segments(tally), widths[0] - 2 * pad, 12),
        Spacer(1, 4),
        Paragraph(_esc(_status_counts_text(tally)), styles["cell"]),
        Paragraph(f"n = {n_profiles} perfiles; estado = peor banco del perfil", styles["tile_note"]),
    ]

    scored = sum(1 for profile in data.profiles if profile.weighted_score is not None)
    score_tile = [
        Paragraph("Puntaje ponderado", styles["tile_label"]),
        Paragraph(
            f"{_num(data.global_weighted_score, 1)}<font size=8 color='#4B5563'> / 100</font>",
            styles["tile_value"],
        ),
        Paragraph(f"n = {scored} perfiles con puntaje", styles["tile_note"]),
    ]

    achievement = (data.design_achievement or {}).get("global") or {}
    achievement_tile = [
        Paragraph("Logro de diseño", styles["tile_label"]),
        Paragraph(
            f"{_num(achievement.get('global_score'), 0)}<font size=8 color='#4B5563'> / 100</font>",
            styles["tile_value"],
        ),
        Paragraph(
            "<br/>".join(
                _esc(line)
                for line in (
                    f"n = {_count(achievement.get('n_evaluable'))} bancos con medición",
                    *_achievement_note(achievement),
                )
            ),
            styles["tile_note"],
        ),
    ]

    bar_width = 1.9 * cm
    label_width = 2.2 * cm
    parameter_rows = []
    for parameter in data.parameters:
        evaluated = _count(parameter.n_evaluated)
        cumple = min(_count(parameter.cumple), evaluated) if evaluated else 0
        parameter_rows.append(
            [
                Paragraph(
                    _esc(_PARAMETER_LABELS.get(parameter.parameter, (parameter.label,))[0]
                         .replace(" de banco", "").replace("Ancho de berma", "Berma")),
                    styles["cell"],
                ),
                Paragraph(
                    f"<b>{_num(parameter.pct_cumple, 1, '%')}</b> "
                    f"<font size=6.8 color='#4B5563'>(n = {evaluated})</font>",
                    styles["cell"],
                ),
                _StatusBar(
                    [(cumple, STATUS_COLORS["CUMPLE"]), (evaluated - cumple, STATUS_COLORS["NO_CUMPLE"])],
                    bar_width,
                    9,
                ),
            ]
        )
    parameters_tile: list = [Paragraph("Cumplimiento por parámetro", styles["tile_label"])]
    if parameter_rows:
        inner = Table(
            parameter_rows,
            colWidths=[label_width, widths[3] - 2 * pad - label_width - bar_width - 4, bar_width + 4],
            hAlign="LEFT",
        )
        inner.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))
        parameters_tile.append(inner)
        parameters_tile.append(Paragraph(
            "% de bancos en CUMPLE sobre los n bancos comparados; barra: verde cumple, "
            "rojo fuera de tolerancia o no cumple.",
            styles["tile_note"],
        ))
    else:
        parameters_tile.append(Paragraph(_esc(DASH), styles["cell"]))

    table = Table(
        [[profiles_tile, score_tile, achievement_tile, parameters_tile]],
        colWidths=widths, hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_TILE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEAFTER", (0, 0), (-2, -1), 4, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _meta_line(data: ReportData) -> str:
    meta = data.meta or {}
    items = (
        ("Proyecto", meta.get("project")),
        ("Operación", meta.get("operation")),
        ("Fase", meta.get("phase")),
        ("Fecha", _fmt_date(meta.get("generated_at"))),
        ("Elaborado por", meta.get("author")),
        ("Diseño", meta.get("design_file") or meta.get("design_filename")),
        ("Topografía", meta.get("topo_file") or meta.get("topo_filename")),
    )
    return " · ".join(f"{label}: <b>{_esc(value or DASH)}</b>" for label, value in items)


def _scope_box(data: ReportData, styles: dict) -> Table:
    lines = [str(line) for line in scope_lines(data)]
    for entry in data.heatmaps or ():
        if isinstance(entry, Mapping) and entry.get("scope_note") and entry["scope_note"] not in lines:
            lines.append(str(entry["scope_note"]))
    if len(lines) > MAX_SCOPE_LINES:
        hidden = len(lines) - (MAX_SCOPE_LINES - 1)
        lines = lines[: MAX_SCOPE_LINES - 2] + [
            f"… y {hidden} líneas de alcance más (detalle en el Word técnico).", lines[-1]
        ]
    body = "<br/>".join(_esc(line) for line in lines)
    table = Table(
        [[Paragraph("<b>Alcance</b>", styles["scope"]), Paragraph(body, styles["scope"])]],
        colWidths=[1.7 * cm, CONTENT_WIDTH - 1.7 * cm], hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_ALT_ROW),
        ("LINEBEFORE", (0, 0), (0, -1), 2, COLOR_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _bench_counts_line(data: ReportData) -> str:
    counts = data.counts or {}
    return (
        f"Bancos en el informe: {_count(counts.get('n_rows'))} "
        f"({_count(counts.get('n_match'))} comparados con el diseño, "
        f"{_count(counts.get('n_missing'))} no construidos y "
        f"{_count(counts.get('n_extra'))} adicionales). Puntaje, logro y % por parámetro son "
        "tres mediciones distintas: no se suman ni se comparan entre sí (definiciones en la "
        "última página)."
    )


def _dashboard_page(data: ReportData, styles: dict, heatmaps: Sequence[dict]) -> list:
    story: list = [
        Paragraph("Informe ejecutivo de conciliación geotécnica", styles["title"]),
        Paragraph(_meta_line(data), styles["meta"]),
        Spacer(1, 3),
        _scope_box(data, styles),
        Paragraph(_esc(headline_text(data)), styles["headline"]),
    ]
    if not data.rows:
        story.append(Paragraph(NO_ROWS_TEXT, styles["body"]))
        return story

    for context in heatmaps:
        if context["note"]:
            prefix = f"{_sector_label(context['sector'])}: " if len(heatmaps) > 1 else ""
            story.append(Paragraph(_esc(prefix + context["note"]), styles["callout"]))

    story.append(Paragraph("1. Indicadores", styles["h2"]))
    story.append(_kpi_tiles(data, styles))
    story.append(Spacer(1, 3))
    story.append(Paragraph(_esc(_bench_counts_line(data)), styles["note"]))

    story.append(Paragraph(
        "2. Vista en planta — secciones según el estado oficial del perfil", styles["h2"]
    ))
    _figure_block(story, _render_plan(data), _PLAN_HEIGHT_IN, styles, missing=NO_PLAN_TEXT)

    story.append(Paragraph(
        "3. Matriz sección × cota — estado oficial de cada banco", styles["h2"]
    ))
    matrix = _figure(
        status_matrix_png, data.matrix, width_in=CONTENT_WIDTH_IN, height_in=_MATRIX_HEIGHT_IN
    )
    _figure_block(story, matrix, _MATRIX_HEIGHT_IN, styles)
    tolerances = _tolerances_line(data)
    if tolerances:
        story.append(Paragraph(_esc(f"Tolerancias: {tolerances}."), styles["note"]))
    return story


def _parameter_of(summary: Mapping[str, Any], name: str) -> Any:
    return next((p for p in summary.get("parameters") or () if p.parameter == name), None)


def _sector_cells(summary: Mapping[str, Any], styles: dict, bar_width: float) -> list:
    headline = summary.get("headline") or {}
    tally = _profile_tally(headline, summary.get("profile_counts"))
    benches = headline.get("benches") if isinstance(headline.get("benches"), Mapping) else {}
    achievement = summary.get("design_achievement") or {}
    totals = summary.get("excavation_totals") or {}
    levels = summary.get("levels") or ()

    def text(value: str, style: str = "cell_center") -> Paragraph:
        return Paragraph(_esc(value), styles[style])

    cells = [
        text(", ".join(str(level) for level in levels) if levels else "todas"),
        text(str(sum(tally.values()))),
        [_StatusBar(_status_segments(tally), bar_width, 9), Spacer(1, 2),
         text(_status_counts_text(tally))],
        text(
            f"{_count(headline.get('nc_by_geometry'))} por geometría · "
            f"{_count(headline.get('nc_only_missing_extra'))} solo por banco no construido o adicional"
        ),
        text(fmt_es(summary.get("global_weighted_score"), 1)),
    ]
    for name in ("height", "angle", "berm"):
        parameter = _parameter_of(summary, name)
        cells.append(text(
            _pct_with_n(None, 0) if parameter is None
            else _pct_with_n(parameter.pct_cumple, parameter.n_evaluated)
        ))
    cells.extend([
        text(fmt_es(achievement.get("global_score"), 0)),
        text(f"{_count(benches.get('missing'))} / {_count(benches.get('extra'))}"),
        text(fmt_es(totals.get("area_over_m2"), 0, "m²")),
        text(fmt_es(totals.get("area_under_m2"), 0, "m²")),
        text(fmt_es(totals.get("volume_over_m3"), 0, "m³")),
        text(fmt_es(totals.get("volume_under_m3"), 0, "m³")),
        text(
            f"{_count(totals.get('n_without_volume'))} de {_count(totals.get('n_sections'))}"
        ),
    ])
    return cells


_SECTOR_INDICATORS = (
    "Cotas seleccionadas",
    "Perfiles evaluados",
    "Perfiles por estado",
    "Perfiles NO CUMPLE por causa",
    "Puntaje ponderado (0–100)",
    "Altura: % cumple",
    "Ángulo de cara: % cumple",
    "Berma: % cumple",
    "Logro de diseño (0–100)",
    "Bancos no construidos / adicionales",
    "Área de sobreexcavación",
    "Área de subexcavación",
    "Volumen de sobreexcavación (estimado)",
    "Volumen de subexcavación (estimado)",
    "Secciones sin volumen",
)


def _sector_top_table(data: ReportData, styles: dict) -> Optional[Table]:
    per_sector: dict[str, list[dict]] = {}
    for entry in data.top_deviations or ():
        if isinstance(entry, Mapping):
            bucket = per_sector.setdefault(str(entry.get("sector") or ""), [])
            if len(bucket) < 3:
                bucket.append(dict(entry))
    entries = [entry for sector in per_sector for entry in per_sector[sector]][:12]
    if not entries:
        return None
    return _deviation_table(data, entries, styles, numbered=False)


def _sector_page(data: ReportData, styles: dict) -> list:
    summaries = [s for s in data.sector_summaries if isinstance(s, Mapping)]
    story: list = [
        Paragraph("Comparación entre sectores", styles["h1"]),
        Paragraph(
            "Cada sector se evalúa con sus propias cotas seleccionadas. Los % por parámetro "
            "usan solo los bancos comparados con el diseño (n); un sector sin bancos "
            "comparados muestra «—», nunca 0 %.",
            styles["note"],
        ),
    ]
    label_width = 5.0 * cm
    for start in range(0, len(summaries), MAX_SECTORS_PER_TABLE):
        chunk = summaries[start:start + MAX_SECTORS_PER_TABLE]
        column = (CONTENT_WIDTH - label_width) / len(chunk)
        columns = [_sector_cells(summary, styles, min(column - 10, 4.0 * cm)) for summary in chunk]
        rows = [[Paragraph("Indicador", styles["table_header_left"])] + [
            Paragraph(_esc(_sector_label(summary.get("sector"))), styles["table_header"])
            for summary in chunk
        ]]
        for index, indicator in enumerate(_SECTOR_INDICATORS):
            rows.append(
                [Paragraph(_esc(indicator), styles["cell_bold"])] + [cells[index] for cells in columns]
            )
        story.append(_grid_table(rows, [label_width] + [column] * len(chunk)))
        story.append(Spacer(1, 6))
    story.append(Paragraph(
        _esc(f"Volúmenes: estimación, {EXCAVATION_METHOD_LINE}."), styles["note"]
    ))
    top = _sector_top_table(data, styles)
    if top is not None:
        story.append(Paragraph("Mayores desviaciones de cada sector (hasta 3)", styles["h2"]))
        story.append(top)
    return story


def _nominal_levels(data: ReportData) -> dict[tuple, str]:
    return {
        (row.section, row.sector, row.bench_num, str(row.level)): row.level_nominal
        for row in data.rows
        if row.level_nominal
    }


def _deviation_table(data: ReportData, entries: Sequence[Mapping[str, Any]], styles: dict,
                     *, numbered: bool = True) -> Table:
    nominal = _nominal_levels(data)
    multi_sector = len({str(row.sector or "") for row in data.rows}) > 1
    headers = ["#", "Sección", "Cota", "Banco", "Parámetro", "Diseño", "Real",
               "Desviación", "Tolerancia", "Índice", "Estado"]
    widths = [0.7, 1.6, 1.2, 1.3, 2.6, 1.6, 1.6, 2.0, 2.3, 1.2, 1.9]
    if not numbered:
        headers, widths = headers[1:], [widths[1] + widths[0]] + widths[2:]
    rows = [[Paragraph(header, styles["table_header"]) for header in headers]]
    commands = []
    for index, entry in enumerate(entries, start=1):
        parameter = str(entry.get("parameter") or "")
        label, unit, decimals = _PARAMETER_LABELS.get(parameter, (parameter, "", 2))
        status = _status_key(entry.get("status"))
        bench = entry.get("bench_num")
        if bench is None:
            bench_text = DASH
        elif bench == _EXTRA_BENCH_NUMBER:
            bench_text = "Adic."
        else:
            bench_text = f"B{bench}"
        key = (str(entry.get("section", "")), str(entry.get("sector", "")), bench,
               str(entry.get("level", "")))
        level = nominal.get(key) or entry.get("level") or DASH
        section = str(entry.get("section") or DASH)
        if multi_sector and entry.get("sector"):
            section = f"{entry['sector']} · {section}"
        if entry.get("criterion") == "min":
            tolerance = f"≥ {fmt_es(entry.get('tolerance'), decimals, unit)}"
        else:
            tolerance = _tolerance_value(
                (data.tolerances or {}).get(_TOLERANCE_KEY.get(parameter, "")), unit, decimals
            )
        ratio = fmt_es(entry.get("ratio"), 2)
        cells = [
            Paragraph(_esc(section), styles["cell_center"]),
            Paragraph(_esc(level), styles["cell_center"]),
            Paragraph(_esc(bench_text), styles["cell_center"]),
            Paragraph(_esc(label), styles["cell"]),
            Paragraph(_num(entry.get("design"), decimals, unit), styles["cell_right"]),
            Paragraph(_num(entry.get("real"), decimals, unit), styles["cell_right"]),
            Paragraph(_signed(entry.get("deviation"), decimals, unit), styles["cell_right"]),
            Paragraph(_esc(tolerance), styles["cell_center"]),
            Paragraph(_esc(ratio if ratio == DASH else f"{ratio}×"), styles["cell_right"]),
            Paragraph(_esc(STATUS_LABELS_ES[status]), _status_style(status, styles)),
        ]
        if numbered:
            cells.insert(0, Paragraph(str(index), styles["cell_center"]))
        rows.append(cells)
        commands.append(("BACKGROUND", (-1, index), (-1, index), STATUS_FILL[status]))
    scale = CONTENT_WIDTH / (sum(widths) * cm)
    return _grid_table(rows, [width * cm * scale for width in widths], extra=commands)


def _top_deviations_table(data: ReportData, styles: dict) -> Optional[Table]:
    entries = [entry for entry in (data.top_deviations or ()) if isinstance(entry, Mapping)]
    if not entries:
        return None
    return _deviation_table(data, entries[:MAX_TOP_DEVIATIONS], styles)


def _analysis_page(data: ReportData, styles: dict) -> list:
    n_match = _count((data.counts or {}).get("n_match"))
    story: list = [
        Paragraph("Análisis de desviaciones", styles["h1"]),
        Paragraph(
            f"4. Distribución de desviaciones — bancos comparados (n = {n_match})", styles["h2"]
        ),
    ]
    histograms = _figure(
        deviation_histograms_png, data.deviations, data.tolerances,
        width_in=CONTENT_WIDTH_IN, height_in=_HISTOGRAM_HEIGHT_IN,
    )
    _figure_block(story, histograms, _HISTOGRAM_HEIGHT_IN, styles)
    story.append(Paragraph(
        "Desviación = real − diseño; la zona sombreada es la tolerancia. La berma se evalúa "
        "contra su ancho mínimo.",
        styles["note"],
    ))

    story.append(Paragraph(
        "5. Tendencia a lo largo del talud — desviación media por sección", styles["h2"]
    ))
    trend = _figure(
        trend_png, data.trend, data.tolerances,
        width_in=CONTENT_WIDTH_IN, height_in=_TREND_HEIGHT_IN,
    )
    _figure_block(story, trend, _TREND_HEIGHT_IN, styles)

    table = _top_deviations_table(data, styles)
    total = len(data.top_deviations or ())
    shown = min(total, MAX_TOP_DEVIATIONS)
    story.append(Paragraph(f"6. Mayores desviaciones ({shown} de {total})", styles["h2"]))
    if table is None:
        story.append(Paragraph(
            "No hay desviaciones calculables con los datos y criterios disponibles.",
            styles["note"],
        ))
    else:
        story.append(table)
        story.append(Paragraph(
            "Orden: índice = |desviación| / tolerancia aplicable, de mayor a menor. En berma la "
            "desviación es real − ancho mínimo y solo participa si el ancho real está bajo el "
            "mínimo. El listado completo está en el Excel analítico.",
            styles["note"],
        ))
    return story


def _excavation_table(data: ReportData, styles: dict) -> Table:
    totals = data.excavation_totals or {}
    header = [
        Paragraph("Total del informe", styles["table_header_left"]),
        Paragraph("Sobreexcavación", styles["table_header"]),
        Paragraph("Subexcavación", styles["table_header"]),
    ]
    rows = [
        header,
        [
            Paragraph("Área entre perfiles (suma de secciones)", styles["cell"]),
            Paragraph(_num(totals.get("area_over_m2"), 0, "m²"), styles["cell_right"]),
            Paragraph(_num(totals.get("area_under_m2"), 0, "m²"), styles["cell_right"]),
        ],
        [
            Paragraph("Volumen estimado", styles["cell_bold"]),
            Paragraph(f"<b>{_num(totals.get('volume_over_m3'), 0, 'm³')}</b>", styles["cell_right"]),
            Paragraph(f"<b>{_num(totals.get('volume_under_m3'), 0, 'm³')}</b>", styles["cell_right"]),
        ],
    ]
    return _grid_table(rows, [8.0 * cm, 3.6 * cm, 3.6 * cm])


def _influence_width_line(data: ReportData) -> str:
    widths = [
        width for width in (_finite(entry.influence_width_m) for entry in data.excavation)
        if width is not None
    ]
    totals = data.excavation_totals or {}
    sections = (
        f"Secciones con geometría: {_count(totals.get('n_sections'))}; sin volumen: "
        f"{_count(totals.get('n_without_volume'))} (se muestran «—», nunca 0)."
    )
    if not widths:
        return f"Ancho de influencia: {DASH}. {sections}"
    return (
        f"Ancho de influencia usado: mediana {fmt_es(median(widths), 1, 'm')} "
        f"(mín. {fmt_es(min(widths), 1, 'm')}, máx. {fmt_es(max(widths), 1, 'm')}). {sections}"
    )


def _level_key(label: Any) -> float:
    number = _finite(label)
    return -math.inf if number is None else number


def _level_table(data: ReportData, styles: dict) -> Optional[list]:
    groups: dict[tuple[str, str], Counter] = {}
    for entry in data.matrix or ():
        if not isinstance(entry, Mapping):
            continue
        key = (str(entry.get("sector") or ""), str(entry.get("level_nominal") or DASH))
        tally = groups.setdefault(key, Counter())
        row_type = entry.get("type")
        if row_type == "MATCH":
            tally[_status_key(entry.get("worst_status"))] += 1
        elif row_type == "MISSING":
            tally["MISSING"] += 1
        elif row_type == "EXTRA":
            tally["EXTRA"] += 1
        if entry.get("design_below_min"):
            tally["BELOW_MIN"] += 1
    if not groups:
        return None
    sector_order = list(dict.fromkeys(sector for sector, _level in groups))
    ordered = sorted(groups, key=lambda key: (sector_order.index(key[0]), -_level_key(key[1])))
    multi_sector = len(sector_order) > 1
    headers = ["Cota nominal", "Bancos", "Cumple", "No cumple", "Sin evaluar",
               "No construidos", "Adicionales", "Berma con diseño bajo el mínimo"]
    if multi_sector:
        headers.insert(0, "Sector")
    rows = [[Paragraph(header, styles["table_header"]) for header in headers]]
    for sector, level in ordered[:MAX_LEVEL_ROWS]:
        tally = groups[(sector, level)]
        compared = tally["CUMPLE"] + tally["FUERA"] + tally["NO_CUMPLE"] + tally["UNKNOWN"]
        cells = [
            _esc(level),
            str(compared + tally["MISSING"] + tally["EXTRA"]),
            str(tally["CUMPLE"]),
            str(tally["NO_CUMPLE"] + tally["FUERA"]),
            str(tally["UNKNOWN"]),
            str(tally["MISSING"]),
            str(tally["EXTRA"]),
            str(tally["BELOW_MIN"]),
        ]
        if multi_sector:
            cells.insert(0, _esc(sector or DASH))
        rows.append([Paragraph(cell, styles["cell_center"]) for cell in cells])
    width = CONTENT_WIDTH / len(headers)
    out: list = [_grid_table(rows, [width] * len(headers))]
    hidden = len(ordered) - MAX_LEVEL_ROWS
    note = (
        "Cumple / No cumple: estado oficial de los bancos comparados con el diseño (puntaje ≥ 70)."
    )
    if hidden > 0:
        note += f" Se muestran {MAX_LEVEL_ROWS} cotas; {hidden} más en el Excel analítico."
    out.append(Paragraph(_esc(note), styles["note"]))
    return out


def _hole_values(holes: Sequence[Mapping[str, Any]], *keys: str) -> list[float]:
    values = []
    for hole in holes:
        for key in keys:
            number = _finite(hole.get(key))
            if number is not None:
                values.append(number)
                break
    return values


def _blast_holes(data: ReportData) -> list[Mapping[str, Any]]:
    blast = data.blast
    if not isinstance(blast, Mapping):
        return []
    return [hole for hole in (blast.get("holes") or ()) if isinstance(hole, Mapping)]


def _blast_rows(data: ReportData) -> Optional[list[tuple[str, str]]]:
    """Blast summary of at most five label/value rows; ``None`` without holes."""
    holes = _blast_holes(data)
    if not holes:
        return None
    rows = [("Pozos registrados", fmt_es(len(holes), 0))]
    collars = _hole_values(holes, "Z_collar", "cota_collar", "collar_z")
    if collars:
        rows.append((
            "Cota de collar (mín. / máx.)",
            f"{fmt_es(min(collars), 2, 'm')} / {fmt_es(max(collars), 2, 'm')}",
        ))
    burdens = _hole_values(holes, "Burden", "burden")
    if burdens:
        rows.append(("Burden promedio", fmt_es(sum(burdens) / len(burdens), 2, "m")))
    spacings = _hole_values(holes, "Esp", "espaciamiento", "spacing")
    if spacings:
        rows.append(("Espaciamiento promedio", fmt_es(sum(spacings) / len(spacings), 2, "m")))
    factors = _hole_values(holes, "pf_voronoi_bench_g_per_ton")
    middle = fmt_es(median(factors), 1, "g/t") if factors else NO_DATA_TEXT
    rows.append((
        "Factor de carga principal (mediana)",
        f"{middle} · con dato {fmt_es(len(factors), 0)} de {fmt_es(len(holes), 0)} pozos",
    ))
    return rows[:MAX_BLAST_ROWS]


def _hole_id(hole: Mapping[str, Any]) -> str:
    for key in ("id_pozo", "hole_id", "label_pozo"):
        value = hole.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return NO_DATA_TEXT


def _listed_holes(holes: Sequence[Mapping[str, Any]]) -> str:
    names = [_hole_id(hole) for hole in holes[:MAX_LISTED_HOLES]]
    text = ", ".join(names)
    hidden = len(holes) - len(names)
    if hidden > 0:
        text += f" … y {fmt_es(hidden, 0)} más (listado completo en el Excel analítico)"
    return text


def _blast_audit_lines(data: ReportData) -> list[str]:
    """Compact audit lines of the blast data: formulas, statuses, consolidation, IDs."""
    from core.blast_correlation import PF_DEFINITIONS

    holes = _blast_holes(data)
    formulas = "; ".join(
        f"{name} ({definition['unit']}) = {definition['formula']}"
        for name, definition in PF_DEFINITIONS.items()
    )
    lines = [
        f"Factor de carga principal (g/t) = {PF_MAIN_FORMULA}, con área de Voronoi por huella "
        f"y altura de banco. Otras definiciones: {formulas}."
    ]
    statuses = Counter(
        str(hole.get("pf_voronoi_bench_status") or NO_DATA_TEXT) for hole in holes
    )
    lines.append(
        "Estado del factor de carga por pozo: "
        + " · ".join(f"{status} {fmt_es(count, 0)}" for status, count in statuses.most_common())
        + "."
    )
    consolidation = (data.blast or {}).get("consolidation_report")
    if isinstance(consolidation, Mapping) and consolidation:

        def item(key: str) -> str:
            value = consolidation.get(key)
            return NO_DATA_TEXT if _finite(value) is None else fmt_es(value, 0)

        lines.append(
            f"Consolidación: copias eliminadas {item('exact_copies_removed')}; pozos "
            f"{item('holes_out')}; filas de decks fusionadas {item('deck_rows_merged')}."
        )
    without = [hole for hole in holes if _finite(hole.get("pf_voronoi_bench_g_per_ton")) is None]
    if without:
        lines.append(
            f"Pozos {NO_DATA_TEXT} de factor de carga ({fmt_es(len(without), 0)} de "
            f"{fmt_es(len(holes), 0)}): "
            f"{_listed_holes(without)}."
        )
    return lines


def _blast_block(data: ReportData, styles: dict) -> list:
    rows = _blast_rows(data)
    if not rows:
        return []
    table_rows = [[
        Paragraph("Métrica", styles["table_header_left"]),
        Paragraph("Valor", styles["table_header"]),
    ]]
    for label, value in rows:
        table_rows.append([
            Paragraph(_esc(label), styles["cell"]), Paragraph(_esc(value), styles["cell_center"])
        ])
    out: list = [
        Paragraph("Resumen de tronadura", styles["h2"]),
        _grid_table(table_rows, [8.0 * cm, 7.2 * cm]),
        Spacer(1, 2),
    ]
    out.extend(Paragraph(_esc(line), styles["note"]) for line in _blast_audit_lines(data))
    return out


def _excavation_page(data: ReportData, styles: dict) -> list:
    story: list = [
        Paragraph("Excavación respecto del diseño", styles["h1"]),
        Paragraph(
            "7. Sobreexcavación y subexcavación por sección — volumen estimado", styles["h2"]
        ),
    ]
    bars = _figure(
        excavation_bars_png, data.excavation,
        width_in=CONTENT_WIDTH_IN, height_in=_EXCAVATION_HEIGHT_IN,
    )
    _figure_block(
        story, bars, _EXCAVATION_HEIGHT_IN, styles,
        missing="Sin volúmenes estimables: falta geometría de perfiles o separación entre secciones.",
    )
    story.append(Spacer(1, 4))
    story.append(_excavation_table(data, styles))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        _esc(f"Método: {EXCAVATION_METHOD_LINE} (mitad de la distancia a cada sección vecina "
             "del sector). Estimación, no cubicación."),
        styles["body"],
    ))
    story.append(Paragraph(_esc(_influence_width_line(data)), styles["note"]))

    levels = _level_table(data, styles)
    if levels:
        story.append(Paragraph("8. Resumen por cota nominal", styles["h2"]))
        story.extend(levels)
    story.extend(_blast_block(data, styles))
    return story


def _sector_geometry(data: ReportData, sector: str, n_sectors: int) -> list:
    geometry = [entry for entry in (data.section_geometry or ()) if isinstance(entry, Mapping)]
    if n_sectors <= 1:
        return geometry
    return [entry for entry in geometry if str(entry.get("sector") or "") == sector]


def _level_label(levels: Sequence[Any]) -> Optional[str]:
    return ", ".join(str(level) for level in levels) if levels else None


def _heatmap_contexts(data: ReportData) -> list[dict]:
    """One renderable context per persisted heatmap that yields a figure."""
    contexts: list[dict] = []
    heatmaps = [entry for entry in (data.heatmaps or ()) if isinstance(entry, Mapping)]
    n_sectors = max(len(data.sector_summaries or ()), len(heatmaps))
    for entry in heatmaps:
        sector = str(entry.get("sector") or "")
        payload = entry.get("payload")
        window = level_window_from_geometry(_sector_geometry(data, sector, n_sectors))
        level = _level_label(data.filters.levels_for(sector)) if window else None
        title_parts = [_sector_label(sector)] if sector else []
        if level:
            title_parts.append(f"{'cotas' if len(data.filters.levels_for(sector)) > 1 else 'cota'} {level}")
        if window:
            title_parts.append(format_level_window(window))
        title = " · ".join(title_parts) or "Desviación horizontal diseño vs. topografía"
        png = _figure(
            heatmap_page_png, payload, level_window=window, title=title,
            width_in=CONTENT_WIDTH_IN, height_in=_HEATMAP_HEIGHT_IN,
        )
        if not png:
            continue
        summary = heatmap_summary(payload, level_window=window)
        contexts.append({
            "sector": sector,
            "entry": entry,
            "payload": payload,
            "window": window,
            "level": level,
            "png": png,
            "summary": summary,
            "note": heatmap_position_note(summary, level_label=level),
        })
    return contexts


def _within_threshold(payload: Any) -> float:
    thresholds = payload.get("thresholds") if isinstance(payload, Mapping) else None
    value = _finite(thresholds.get("within")) if isinstance(thresholds, Mapping) else None
    return value if value is not None and value > 0 else 1.0


def _extreme_text(extreme: Optional[Mapping[str, Any]]) -> str:
    if not extreme:
        return DASH
    parts = [_signed(extreme.get("deviation_m"), 2, "m")]
    if _finite(extreme.get("station_m")) is not None:
        parts.append(f"estación {fmt_es(extreme.get('station_m'), 0, 'm')}")
    if _finite(extreme.get("elevation")) is not None:
        parts.append(f"cota {fmt_es(extreme.get('elevation'), 1, 'm')}")
    if extreme.get("location"):
        parts.append(str(extreme["location"]))
    return " · ".join(parts)


def _heatmap_summary_table(context: Mapping[str, Any], styles: dict, width: float) -> Table:
    summary: HeatmapSummary = context["summary"]
    within = _within_threshold(context["payload"])
    within_label = f"Dentro de ±{fmt_es(within, 0 if float(within).is_integer() else 1)} m"
    measured_pct = 100.0 * summary.n_measured / summary.n_cells if summary.n_cells else None
    within_count = summary.counts.get("within_tolerance", 0)
    rows = [
        ("Celdas medidas",
         f"{fmt_es(summary.n_measured, 0)} de {fmt_es(summary.n_cells, 0)} "
         f"({fmt_es(measured_pct, 1, '%')})"),
        (within_label,
         f"{fmt_es(summary.pct_within, 1, '%')} ({fmt_es(within_count, 0)} celdas)"),
        ("Mediana (con signo)", _signed(summary.median_m, 2, "m")),
        ("P95 de |desviación|", fmt_es(summary.p95_abs_m, 2, "m")),
        ("Máxima sobreexcavación", _extreme_text(summary.max_over)),
        ("Máxima subexcavación", _extreme_text(summary.max_under)),
    ]
    scope = "Resumen del mapa"
    if context["window"]:
        level_text = context["level"]
        label = f"cotas {level_text}" if level_text and "," in level_text else f"cota {level_text or DASH}"
        scope = f"Resumen de {label} ({format_level_window(context['window'])})"
    table_rows = [[
        Paragraph(_esc(scope), styles["table_header_left"]),
        Paragraph("Valor", styles["table_header"]),
    ]]
    for label, value in rows:
        table_rows.append([
            Paragraph(_esc(label), styles["cell"]), Paragraph(_esc(value), styles["cell"])
        ])
    return _grid_table(table_rows, [3.6 * cm, width - 3.6 * cm])


def _heatmap_class_table(context: Mapping[str, Any], styles: dict, width: float) -> Table:
    summary: HeatmapSummary = context["summary"]
    rows = [[
        Paragraph("", styles["table_header"]),
        Paragraph("Clase", styles["table_header_left"]),
        Paragraph("Celdas", styles["table_header"]),
        Paragraph("% medidas", styles["table_header"]),
    ]]
    commands = []
    for index, key in enumerate(HDEV_CATEGORY_ORDER, start=1):
        count = summary.counts.get(key, 0)
        measured = key != "unmeasured" and summary.n_measured
        pct = 100.0 * count / summary.n_measured if measured else None
        rows.append([
            "",
            Paragraph(_esc(HDEV_LABELS_ES.get(key, key)), styles["cell"]),
            Paragraph(_num(count, 0), styles["cell_right"]),
            Paragraph(_num(pct, 1, "%"), styles["cell_right"]),
        ])
        commands.append(("BACKGROUND", (0, index), (0, index), colors.HexColor(HDEV_COLORS[key])))
    return _grid_table(rows, [0.5 * cm, width - 4.1 * cm, 1.7 * cm, 1.9 * cm], extra=commands)


def _sector_headline(data: ReportData, sector: str) -> str:
    summaries = [s for s in (data.sector_summaries or ()) if isinstance(s, Mapping)]
    if len(summaries) > 1:
        summary = next((s for s in summaries if str(s.get("sector") or "") == sector), None)
        if summary is not None:
            return headline_text(replace(
                data,
                headline=summary.get("headline") or {},
                profile_counts=summary.get("profile_counts") or {},
            ))
    return headline_text(data)


def _heatmap_page(data: ReportData, context: Mapping[str, Any], styles: dict) -> list:
    sector = context["sector"]
    summary: HeatmapSummary = context["summary"]
    heading = "Mapa de calor de desviación horizontal"
    if sector:
        heading += f" — {_sector_label(sector)}"
    entry = context["entry"]
    payload = context["payload"] if isinstance(context["payload"], Mapping) else {}
    resolution = payload.get("resolution") if isinstance(payload.get("resolution"), Mapping) else {}
    params = entry.get("params") if isinstance(entry.get("params"), Mapping) else {}
    longitudinal = resolution.get("longitudinal_step", params.get("longitudinal_step"))
    vertical = resolution.get("vertical_step", params.get("vertical_step"))
    story: list = [
        Paragraph(_esc(heading), styles["h1"]),
        Paragraph(
            _esc(
                "Vista desarrollada de la pared (estación × cota): desviación horizontal entre "
                "diseño y topografía a igual cota; positiva = sobreexcavación. Resultado "
                f"calculado en la vista 3D ({entry.get('computed_at_text') or DASH}); "
                f"celdas de {fmt_es(longitudinal, 1, 'm')} × {fmt_es(vertical, 1, 'm')}."
            ),
            styles["note"],
        ),
        _image(context["png"], CONTENT_WIDTH, max_height=_HEATMAP_HEIGHT_IN * 72.0),
        Spacer(1, 6),
    ]
    if entry.get("scope_note"):
        story.insert(1, Paragraph(_esc(entry.get("scope_note")), styles["note"]))
    left_width = 9.6 * cm
    gap = 0.4 * cm
    right_width = CONTENT_WIDTH - left_width - gap
    level = context["level"]
    shape_label = "Forma del banco (estado oficial" + (f", cota {level}" if level else "") + ")"
    within = _within_threshold(payload)
    position = (
        f"{fmt_es(summary.pct_within, 1, '%')} de las celdas medidas dentro de "
        f"±{fmt_es(within, 0 if float(within).is_integer() else 1)} m; "
        f"mediana {_signed(summary.median_m, 1, 'm')}."
    )
    right: list = [
        Paragraph(_esc(shape_label), styles["tile_label"]),
        Paragraph(_esc(_sector_headline(data, sector)), styles["cell"]),
        Spacer(1, 5),
        Paragraph("Posición de la pared (mapa de calor)", styles["tile_label"]),
        Paragraph(_esc(position), styles["cell"]),
    ]
    if context["note"]:
        right.extend([Spacer(1, 5), Paragraph(_esc(context["note"]), styles["callout"])])
    box = Table([[right]], colWidths=[right_width], hAlign="LEFT")
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_TILE),
        ("LINEBEFORE", (0, 0), (0, -1), 2, COLOR_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    left = [
        _heatmap_summary_table(context, styles, left_width),
        Spacer(1, 6),
        _heatmap_class_table(context, styles, left_width),
    ]
    layout = Table([[left, "", [box]]], colWidths=[left_width, gap, right_width], hAlign="LEFT")
    layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(layout)
    story.append(Paragraph(
        "Las clases y colores son los de la vista 3D; las celdas sin cruce único de la "
        "topografía quedan sin medición y nunca se rellenan con 0.",
        styles["note"],
    ))
    return story


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _aggregated_warnings(data: ReportData) -> list[str]:
    """Warnings deduplicated and counted; never one line per bench, section or hole."""
    lines: list[str] = []
    for text, count in Counter(str(w) for w in (data.warnings or ())).items():
        lines.append(text if count == 1 else f"{text} (×{count})")

    below_min = sum(1 for row in data.rows if row.design_below_min)
    if below_min:
        lines.append(
            f"{_plural(below_min, 'berma tiene', 'bermas tienen')} diseño bajo el mínimo "
            "exigido; su estado oficial no cambia."
        )

    achievement_rows = ((data.design_achievement or {}).get("global") or {}).get("rows") or []
    if len(achievement_rows) == len(data.rows):
        compared = [
            detail for row, detail in zip(data.rows, achievement_rows)
            if row.type == "MATCH" and isinstance(detail, Mapping)
        ]
        incomplete = sum(1 for detail in compared if detail.get("components_missing"))
        if incomplete:
            complete = len(compared) - incomplete
            lines.append(
                f"Componentes faltantes del logro de diseño: {incomplete} de {len(compared)} "
                "bancos comparados sin cresta, pata o berma. Cobertura: "
                f"{complete} completos; cada porcentaje usa su propio denominador."
            )

    totals = data.excavation_totals or {}
    without_volume = _count(totals.get("n_without_volume"))
    if without_volume:
        lines.append(
            f"{without_volume} de {_count(totals.get('n_sections'))} secciones sin volumen "
            "estimado (sin sección vecina en su sector o sin traslape de perfiles)."
        )
    excavation_warnings = Counter(
        str(warning) for entry in data.excavation for warning in (entry.warnings or ())
    )
    for text, count in excavation_warnings.most_common(3):
        lines.append(f"{text} ({_plural(count, 'sección', 'secciones')})")

    holes = _blast_holes(data)
    estimated = sum(
        1 for hole in holes
        if hole.get("Z_collar_semantic", hole.get("z_collar_semantic")) == "design_surface_estimate"
    )
    if estimated:
        lines.append(
            f"Tronadura: la cota de collar de {estimated} de {len(holes)} pozos fue estimada "
            "desde la superficie de diseño; no es una medición de terreno."
        )
    if isinstance(data.blast, Mapping) and data.blast.get("data_status") == "legacy_reimport_required":
        lines.append(f"{LEGACY_BLAST_WARNING} ({fmt_es(len(holes), 0)} pozos: {_listed_holes(holes)}).")

    if len(lines) > MAX_WARNING_LINES:
        hidden = len(lines) - (MAX_WARNING_LINES - 1)
        lines = lines[: MAX_WARNING_LINES - 1] + [
            f"… y {hidden} advertencias más (detalle en el Word técnico)."
        ]
    return lines


def _conclusion_lines(data: ReportData, heatmaps: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [_localized(conclusion) for conclusion in (data.conclusions or ())]
    depth = data.depth
    if isinstance(depth, Mapping) and _finite(depth.get("profundidad")) is not None:
        lines.append(
            f"Profundidad del rajo: {fmt_es(depth.get('profundidad'), 2, 'm')} "
            f"(cota de piso {fmt_es(depth.get('cota_piso'), 2, 'm')}, cota de cresta "
            f"{fmt_es(depth.get('cota_cresta'), 2, 'm')})."
        )
    for context in heatmaps:
        if context["note"]:
            prefix = f"{_sector_label(context['sector'])}: " if len(heatmaps) > 1 else ""
            lines.append(prefix + context["note"])
    return lines


def _conclusions_page(data: ReportData, styles: dict, heatmaps: Sequence[Mapping[str, Any]],
                      *, with_blast: bool) -> list:
    story: list = [Paragraph("Conclusiones y advertencias", styles["h1"])]
    story.append(Paragraph("Conclusiones", styles["h2"]))
    conclusions = _conclusion_lines(data, heatmaps)
    if conclusions:
        for line in conclusions:
            story.append(Paragraph(_esc(line), styles["bullet"], bulletText="•"))
    else:
        story.append(Paragraph("Sin conclusiones para el alcance del informe.", styles["note"]))

    story.append(Paragraph("Advertencias", styles["h2"]))
    warnings = _aggregated_warnings(data)
    if warnings:
        for line in warnings:
            story.append(Paragraph(_esc(line), styles["warn"], bulletText="•"))
    else:
        story.append(Paragraph("Sin advertencias.", styles["note"]))

    if with_blast:
        story.extend(_blast_block(data, styles))

    story.append(Paragraph("Criterios", styles["h2"]))
    tolerances = _tolerances_line(data)
    story.append(Paragraph(_esc(f"Tolerancias: {tolerances or DASH}."), styles["body"]))
    story.append(Paragraph(
        "Altura y ángulo: CUMPLE dentro de tolerancia, FUERA DE TOLERANCIA hasta 1,5 veces la "
        "tolerancia y NO CUMPLE sobre 1,5 veces. Berma: se compara el ancho real con el "
        "mínimo configurado.",
        styles["note"],
    ))

    story.append(Paragraph("Definiciones", styles["h2"]))
    rows = [[
        Paragraph("Indicador", styles["table_header_left"]),
        Paragraph("Definición y denominador", styles["table_header_left"]),
    ]]
    for name, definition in kpi_definitions(data):
        rows.append([
            Paragraph(_esc(name), styles["cell_bold"]), Paragraph(_esc(definition), styles["cell"])
        ])
    story.append(_grid_table(rows, [4.0 * cm, CONTENT_WIDTH - 4.0 * cm]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "El detalle por banco, sección y pozo está en el Word técnico y en el Excel "
        "analítico. Conciliación Geotécnica v02.",
        styles["note"],
    ))
    return story


def _build_pdf_report_unlocked(data: ReportData) -> io.BytesIO:
    """Build the executive PDF report from ``data`` and return a seekable buffer."""
    styles = _report_styles()
    meta = data.meta or {}
    project = str(meta.get("project") or "Proyecto no especificado")
    heatmaps = _heatmap_contexts(data) if data.rows else []

    pages: list[list] = [_dashboard_page(data, styles, heatmaps)]
    if data.rows:
        if len(data.sector_summaries or ()) > 1:
            pages.append(_sector_page(data, styles))
        pages.append(_analysis_page(data, styles))
        pages.append(_excavation_page(data, styles))
        pages.extend(_heatmap_page(data, context, styles) for context in heatmaps)
    pages.append(_conclusions_page(data, styles, heatmaps, with_blast=not data.rows))

    story: list = []
    for index, page in enumerate(pages):
        if index:
            story.append(PageBreak())
        story.append(KeepInFrame(CONTENT_WIDTH, CONTENT_HEIGHT - 2.0, page, mode="shrink"))

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title="Informe de Conciliación Geotécnica",
        author=str(meta.get("author") or "Conciliación Geo v02"),
        subject="Conciliación Geotécnica — Informe ejecutivo",
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="body",
                frames=[
                    Frame(
                        doc.leftMargin,
                        doc.bottomMargin,
                        doc.width,
                        doc.height,
                        id="content",
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
            )
        ]
    )

    def _canvas_factory(*args: Any, **kwargs: Any) -> _NumberedCanvas:
        return _NumberedCanvas(
            *args, project=project, generated=_fmt_date(meta.get("generated_at")), **kwargs
        )

    doc.build(story, canvasmaker=_canvas_factory)
    buffer.seek(0)
    return buffer


def build_pdf_report(data: ReportData) -> io.BytesIO:
    """Build a PDF while serializing ReportLab's shared font state."""
    with _PDF_BUILD_LOCK:
        return _build_pdf_report_unlocked(data)


__all__ = ["build_pdf_report"]
