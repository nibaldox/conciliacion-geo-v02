"""Executive PDF report for the web export built from ``ReportData``.

Renders the same numbers as the Word report (both consume the shared
``core.report_data.ReportData`` model) as an A4-portrait Spanish document:
cover, executive summary, criteria, per-parameter compliance, design
achievement by sector, largest tolerance-relative deviations, compliance
plan view and the blast summary when holes are present. Sections without
data are omitted entirely; the header carries the project name and every
page except the cover carries a ``Página X de Y`` footer.
"""

from __future__ import annotations

import io
import math
import os
import threading
from datetime import datetime
from typing import Any, Optional
from xml.sax.saxutils import escape

import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab import __file__ as reportlab_path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from core.pdf_report import _build_styles, _header_table
from core.report_charts import parameter_donuts_png, plan_view_png
from core.report_data import ReportData, parse_bench_status

PAGE_MARGIN = 2 * cm
PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 2 * PAGE_MARGIN
CONTENT_HEIGHT = PAGE_HEIGHT - 2 * PAGE_MARGIN

COLOR_NAVY = colors.HexColor("#1F3A5F")
COLOR_ALT_ROW = colors.HexColor("#F2F4F8")
COLOR_MUTED = colors.HexColor("#4B5563")

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

STATUS_LABELS = {
    "CUMPLE": "CUMPLE",
    "FUERA": "FUERA DE TOLERANCIA",
    "NO_CUMPLE": "NO CUMPLE",
    "UNKNOWN": "SIN EVALUAR",
}

PROFILE_STATUS_ORDER = ("CUMPLE", "FUERA", "NO_CUMPLE")

_PARAMETER_LABELS = {
    "height": ("Altura de banco", "m", 2),
    "angle": ("Ángulo de cara", "°", 1),
    "berm": ("Ancho de berma", "m", 2),
}

_PARAMETER_TOLERANCE_KEYS = {
    "height": "bench_height",
    "angle": "face_angle",
    "berm": "berm_width",
}

_TOLERANCE_ROWS = (
    ("bench_height", "Altura de banco", "m", 2),
    ("face_angle", "Ángulo de cara", "°", 1),
    ("berm_width", "Ancho de berma", "m", 2),
    ("crest_toe_deviation", "Desviación cresta-pie", "m", 2),
    ("inter_ramp_angle", "Ángulo entre rampas", "°", 1),
    ("overall_angle", "Ángulo global del talud", "°", 1),
)

_PROCESS_ROWS = (
    ("resolution", "Resolución de malla", "m", 2),
    ("spacing", "Espaciamiento de secciones", "m", 2),
    ("face_threshold", "Umbral de cara", "°", 1),
    ("berm_threshold", "Umbral de berma", "°", 1),
)

_MAX_DEVIATIONS_PER_PARAMETER = 5

_DEVIATION_PARAMETER_ORDER = ("height", "angle", "berm")

_REPORTLAB_FONTS = os.path.join(os.path.dirname(reportlab_path), "fonts")
_FONT_FILES = (
    ("GeoVera", "Vera.ttf"),
    ("GeoVera-Bold", "VeraBd.ttf"),
    ("GeoVera-Italic", "VeraIt.ttf"),
    ("GeoVera-BoldItalic", "VeraBI.ttf"),
)


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


_BODY_FONT, _BOLD_FONT = _register_report_fonts(_REPORTLAB_FONTS)
_PDF_BUILD_LOCK = threading.RLock()


class _NumberedCanvas(pdf_canvas.Canvas):
    """Canvas stamping the project header and the ``Página X de Y`` footer."""

    def __init__(self, *args: Any, project: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._project = project or "Proyecto no especificado"
        self._states: list[dict] = []

    def showPage(self) -> None:
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._states)
        for index, state in enumerate(self._states, start=1):
            self.__dict__.update(state)
            if index > 1:
                self._draw_chrome(index, total)
            super().showPage()
        super().save()

    def _draw_chrome(self, page: int, total: int) -> None:
        self.saveState()
        self.setStrokeColor(COLOR_NAVY)
        self.setLineWidth(0.6)
        self.setFillColor(COLOR_NAVY)
        self.setFont(_BOLD_FONT, 9)
        self.drawString(PAGE_MARGIN, PAGE_HEIGHT - 1.2 * cm, self._project[:70])
        self.setFont(_BODY_FONT, 8)
        self.setFillColor(colors.grey)
        self.drawRightString(
            PAGE_WIDTH - PAGE_MARGIN,
            PAGE_HEIGHT - 1.2 * cm,
            "Informe de conciliación geotécnica",
        )
        self.line(
            PAGE_MARGIN,
            PAGE_HEIGHT - 1.45 * cm,
            PAGE_WIDTH - PAGE_MARGIN,
            PAGE_HEIGHT - 1.45 * cm,
        )
        self.setFont(_BODY_FONT, 8)
        self.drawRightString(
            PAGE_WIDTH - PAGE_MARGIN, 1.1 * cm, f"Página {page} de {total}"
        )
        self.restoreState()


def _report_styles() -> dict:
    """Return the reportlab styles, extending the shared executive palette."""
    styles = dict(_build_styles())
    for style in styles.values():
        style.fontName = style.fontName.replace("Helvetica-Bold", _BOLD_FONT).replace(
            "Helvetica", _BODY_FONT
        )
    styles["bullet"] = ParagraphStyle(
        "Bullet", parent=styles["body"], leftIndent=12, bulletIndent=2, spaceAfter=2
    )
    styles["note"] = ParagraphStyle(
        "Note", parent=styles["small"], textColor=COLOR_MUTED, spaceAfter=4
    )
    styles["warn"] = ParagraphStyle(
        "Warn", parent=styles["body"], textColor=STATUS_TEXT["NO_CUMPLE"]
    )
    styles["cell_wrap"] = ParagraphStyle(
        "CellWrap", parent=styles["cell"], fontSize=8, leading=10
    )
    styles["cell_bold_small"] = ParagraphStyle(
        "CellBoldSmall", parent=styles["cell_bold"], fontSize=7.5, leading=9
    )
    styles["table_header"] = ParagraphStyle(
        "TableHeader", parent=styles["cell_bold_small"], textColor=colors.white,
        fontSize=7, leading=8,
    )
    styles["group"] = ParagraphStyle(
        "Group",
        parent=styles["h2"],
        textColor=COLOR_NAVY,
        fontSize=10.5,
        leading=13,
        spaceBefore=6,
        spaceAfter=3,
    )
    return styles


def _esc(value: Any) -> str:
    return escape("" if value is None else str(value))


def _fmt_number(value: Any, decimals: int) -> Optional[str]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return f"{number:.{decimals}f}"


def _fmt_length(value: Any) -> Optional[str]:
    number = _fmt_number(value, 2)
    return None if number is None else f"{number} m"


def _fmt_angle(value: Any) -> Optional[str]:
    number = _fmt_number(value, 1)
    return None if number is None else f"{number}°"


def _fmt_pct(value: Any) -> Optional[str]:
    number = _fmt_number(value, 1)
    return None if number is None else f"{number}%"


def _fmt_date(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        return datetime.fromisoformat(text).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text


def _status_paragraph(status: str, styles: dict) -> Paragraph:
    normalized = status if status in STATUS_LABELS else "UNKNOWN"
    return Paragraph(
        STATUS_LABELS[normalized],
        ParagraphStyle(
            f"Status{normalized}",
            parent=styles["cell_center"],
            textColor=STATUS_TEXT[normalized],
            fontSize=8,
            leading=10,
        ),
    )


def _base_table(data: list, col_widths: list, align_center_from: int = 0) -> Table:
    table = Table(data, colWidths=col_widths, hAlign="CENTER", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (align_center_from, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ALT_ROW]),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_NAVY),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _bullets(story: list, items: Any, styles: dict, style_key: str = "bullet") -> None:
    for item in items or ():
        story.append(Paragraph(_esc(item), styles[style_key], bulletText="•"))


def _cover(story: list, data: ReportData, styles: dict) -> None:
    meta = data.meta or {}
    counts = data.counts or {}
    classified_profiles = sum((data.profile_counts or {}).values())
    profile_summary = (
        f"Denominador {classified_profiles}: "
        f"CUMPLE {int((data.profile_counts or {}).get('CUMPLE', 0))} · "
        f"FUERA {int((data.profile_counts or {}).get('FUERA', 0))} · "
        f"NO CUMPLE {int((data.profile_counts or {}).get('NO_CUMPLE', 0))}"
    )
    design_file = meta.get("design_file") or meta.get("design_filename") or "No disponible en metadatos"
    topo_file = meta.get("topo_file") or meta.get("topo_filename") or "No disponible en metadatos"
    story.append(Spacer(1, 3.2 * cm))
    story.append(Paragraph("Informe de Conciliación Geotécnica", styles["title"]))
    story.append(
        Paragraph(
            "Resultados ejecutivos del cumplimiento entre el diseño y la "
            "topografía real de la excavación",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 1.4 * cm))
    cover_cell = ParagraphStyle(
        "CoverCell", parent=styles["cell_center"], fontSize=9, leading=11
    )
    story.append(
        _header_table(
            [
                ["Proyecto", "Operación", "Fase", "Fecha"],
                [
                    Paragraph(_esc(meta.get("project") or "N/A"), cover_cell),
                    Paragraph(_esc(meta.get("operation") or "N/A"), cover_cell),
                    Paragraph(_esc(meta.get("phase") or "N/A"), cover_cell),
                    Paragraph(_esc(_fmt_date(meta.get("generated_at"))), cover_cell),
                ],
            ],
            col_widths=[5.2 * cm, 4.0 * cm, 4.0 * cm, 3.6 * cm],
        )
    )
    scope_style = ParagraphStyle("CoverScope", parent=styles["body"], fontSize=9, leading=12)
    scope_rows = [
        [Paragraph("Estado de perfiles clasificados", styles["cell_bold"]), Paragraph(_esc(profile_summary), scope_style)],
        [Paragraph("Alcance", styles["cell_bold"]), Paragraph(
            _esc(f"{counts.get('n_rows', 0)} registros de banco · {counts.get('n_sections', 0)} secciones en el modelo"),
            scope_style,
        )],
        [Paragraph("Filtros aplicados", styles["cell_bold"]), Paragraph(_esc(_filters_text(data)), scope_style)],
        [Paragraph("Fuentes", styles["cell_bold"]), Paragraph(
            f"Diseño: {_esc(design_file)}<br/>Topografía: {_esc(topo_file)}", scope_style
        )],
    ]
    scope_table = Table(scope_rows, colWidths=[4.0 * cm, 12.8 * cm], hAlign="CENTER")
    scope_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), COLOR_ALT_ROW),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_NAVY),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(Spacer(1, 0.8 * cm))
    story.append(scope_table)
    story.append(Spacer(1, 0.8 * cm))
    story.append(
        Paragraph(f"<b>Elaborado por:</b> {_esc(meta.get('author') or 'N/A')}", styles["body"])
    )
    story.append(
        Paragraph(
            "Documento generado automáticamente por el módulo de conciliación "
            "geotécnica. Las cifras provienen del modelo de datos compartido con "
            "el informe Word.",
            styles["note"],
        )
    )
    story.append(PageBreak())


def _summary_section(story: list, data: ReportData, styles: dict) -> None:
    story.append(
        Paragraph(
            "El estado del perfil corresponde al peor estado entre sus registros de "
            "banco, incluidos faltantes y adicionales. Un banco emparejado cumple "
            "con 70 puntos o más; sus mediciones individuales conservan sus "
            "estados de tolerancia. El puntaje global promedio es un indicador "
            "separado de la clasificación del perfil.",
            styles["note"],
        )
    )

    if not data.rows:
        story.append(
            Paragraph("No hay comparaciones para reportar con los filtros aplicados.", styles["body"])
        )
        if data.warnings:
            story.append(Paragraph("<b>Advertencias</b>", styles["body"]))
            _bullets(story, data.warnings, styles, style_key="warn")
        return

    total = sum((data.profile_counts or {}).values())
    unclassified = sum(1 for profile in data.profiles if profile.worst_status == "UNKNOWN")
    if total == 0:
        story.append(Paragraph(
            "El modelo no aporta perfiles con estado clasificado para este resumen. "
            "No se asignan perfiles sin clasificación a NO CUMPLE.",
            styles["body"],
        ))
    else:
        story.append(Paragraph(
            f"Perfiles con estado clasificado: <b>{total}</b>. "
            "El denominador suma únicamente los estados incluidos en el modelo.",
            styles["note"],
        ))
    story.append(Paragraph(
        f"Perfiles UNKNOWN / SIN EVALUAR: <b>{unclassified}</b>; "
        "se informan por separado y quedan fuera del denominador clasificado.",
        styles["note"],
    ))
    if total > 0:
        table_rows = [
            [
                Paragraph("Estado del perfil", styles["table_header"]),
                Paragraph("Perfiles", styles["table_header"]),
                Paragraph("% del denominador", styles["table_header"]),
            ]
        ]
        style_cmds = []
        for status in PROFILE_STATUS_ORDER:
            count = int(data.profile_counts.get(status, 0))
            pct = 100.0 * count / total
            table_rows.append(
                [
                    _status_paragraph(status, styles),
                    Paragraph(str(count), styles["cell_center"]),
                    Paragraph(f"{pct:.1f}%", styles["cell_center"]),
                ]
            )
            style_cmds.append(("BACKGROUND", (0, len(table_rows) - 1), (0, len(table_rows) - 1), STATUS_FILL[status]))
        table_rows.append(
            [
                Paragraph("Total clasificado", styles["cell_bold"]),
                Paragraph(str(total), styles["cell_center"]),
                Paragraph("100.0%", styles["cell_center"]),
            ]
        )
        table = _base_table(table_rows, col_widths=[7.0 * cm, 3.0 * cm, 4.0 * cm])
        table.setStyle(TableStyle(style_cmds))
        story.append(table)
        story.append(Spacer(1, 0.3 * cm))

    counts = data.counts or {}
    story.append(
        Paragraph(
            f"Registros de banco en el modelo: <b>{counts.get('n_rows', 0)}</b> "
            f"(MATCH {counts.get('n_match', 0)}, MISSING {counts.get('n_missing', 0)}, "
            f"EXTRA {counts.get('n_extra', 0)}) en {counts.get('n_sections', 0)} "
            "secciones según el modelo.",
            styles["body"],
        )
    )
    if data.warnings:
        story.append(Paragraph("Advertencias", styles["h2"]))
        _bullets(story, data.warnings, styles, style_key="warn")

    if data.global_weighted_score is not None:
        scored_profiles = sum(1 for profile in data.profiles if profile.weighted_score is not None)
        story.append(
            Paragraph(
                f"Puntaje ponderado global (0-100): <b>{data.global_weighted_score:.1f}</b> "
                f"(media de {scored_profiles} perfiles con puntaje disponible); "
                "indicador independiente del peor estado por perfil.",
                styles["body"],
            )
        )

    achievement = (data.design_achievement or {}).get("global") or {}
    if achievement.get("global_score") is not None:
        parts = [
            f"Logro de diseño global (0-100): <b>{achievement['global_score']}</b>",
            f"cresta {_fmt_pct(achievement.get('crest_pct')) or 'N/A'} (n={achievement.get('crest_denom', 0)})",
            f"pie {_fmt_pct(achievement.get('toe_pct')) or 'N/A'} (n={achievement.get('toe_denom', 0)})",
            f"berma {_fmt_pct(achievement.get('berm_pct')) or 'N/A'} (n={achievement.get('berm_denom', 0)})",
            f"registros con algún componente disponible {achievement.get('n_evaluable', 0)}",
        ]
        story.append(Paragraph(" · ".join(parts) + ".", styles["body"]))
        coverage = achievement.get("coverage") or {}
        weight = coverage.get("weight_available_mean")
        weight_text = "sin dato" if weight is None else f"{weight:.2f}"
        story.append(Paragraph(
            f"Cobertura: evaluables {coverage.get('n_evaluable', 0)} de {coverage.get('n_rows', 0)}; "
            f"completos {coverage.get('n_complete', 0)}; peso medio disponible {weight_text}.", styles["body"]
        ))
        for row, detail in zip(data.rows, achievement.get("rows") or []):
            missing = detail.get("components_missing") or []
            if missing:
                story.append(Paragraph(
                    f"{_esc(row.section)}, banco {_esc(row.bench_num)}: componentes faltantes: {_esc(', '.join(missing))}.",
                    styles["note"],
                ))
        story.append(Paragraph(
            "Cada porcentaje de componente usa su propio n disponible. Los registros "
            "contados como evaluables pueden tener solo uno de los componentes.",
            styles["note"],
        ))

    _priority_summary(story, data, styles)

def _priority_summary(story: list, data: ReportData, styles: dict) -> None:
    entries = [entry for entry in (data.top_deviations or ()) if isinstance(entry, dict)]
    if not entries:
        story.append(Paragraph(
            "No hay desviaciones prioritarias calculables con los datos y criterios disponibles.",
            styles["note"],
        ))
        return
    story.append(Paragraph("Prioridad principal por parámetro", styles["h2"]))
    for parameter in _DEVIATION_PARAMETER_ORDER:
        entry = next((item for item in entries if item.get("parameter") == parameter), None)
        if entry is None:
            continue
        label, unit, decimals = _PARAMETER_LABELS.get(parameter, (parameter, "", 2))
        bench = entry.get("bench_num")
        identity = f"Sección {_esc(entry.get('section'))}"
        if entry.get("sector"):
            identity += f" · Sector {_esc(entry.get('sector'))}"
        identity += f" · Banco {'—' if bench is None else f'B{bench}'}"
        real = _fmt_number(entry.get("real"), decimals)
        design = _fmt_number(entry.get("design"), decimals)
        deviation = _fmt_number(entry.get("deviation"), decimals)
        ratio = _fmt_number(entry.get("ratio"), 2)
        if entry.get("criterion") == "min":
            difference = (
                f"déficit vs. mínimo {abs(float(entry['deviation'])):.{decimals}f} {unit}"
                if deviation is not None else "déficit no disponible"
            )
        else:
            difference = (
                f"desviación de criterio {deviation} {unit}"
                if deviation is not None else "desviación no disponible"
            )
        status = STATUS_LABELS[parse_bench_status(entry.get("status"))]
        story.append(Paragraph(
            f"<b>{_esc(label)}</b>: {identity}; diseño {'—' if design is None else design} {unit}, "
            f"real {'—' if real is None else real} {unit}; {difference}; "
            f"base {_esc(entry.get('tolerance_text') or 'No disponible')}; índice {ratio or '—'}×; {status}.",
            styles["bullet"], bulletText="•",
        ))


def _depth_section(story: list, data: ReportData, styles: dict) -> bool:
    depth = data.depth
    if not depth or depth.get("profundidad") is None:
        return False
    rows = [
        [Paragraph("Métrica", styles["table_header"]), Paragraph("Valor", styles["table_header"])]
    ]
    for label, value in (
        ("Cota piso global", depth.get("cota_piso")),
        ("Cota cresta global", depth.get("cota_cresta")),
        ("Profundidad total", depth.get("profundidad")),
    ):
        rows.append(
            [
                Paragraph(label, styles["cell"]),
                Paragraph(_fmt_length(value) or "N/A", styles["cell_center"]),
            ]
        )
    story.append(_base_table(rows, col_widths=[7.5 * cm, 5.0 * cm], align_center_from=1))
    story.append(
        Paragraph(
            f"Calculado con {depth.get('n_floors', 0)} cotas de piso y "
            f"{depth.get('n_crests', 0)} cotas de cresta de bancos reales.",
            styles["note"],
        )
    )
    return True


def _tolerance_value(tolerance: Any, unit: str, decimals: int) -> str:
    if not isinstance(tolerance, dict):
        return "N/A"
    neg = _fmt_number(tolerance.get("neg"), decimals)
    pos = _fmt_number(tolerance.get("pos"), decimals)
    minimum = _fmt_number(tolerance.get("min"), decimals)
    maximum = _fmt_number(tolerance.get("max"), decimals)
    if neg is not None and pos is not None:
        neg_value = abs(float(tolerance["neg"]))
        pos_value = float(tolerance["pos"])
        if abs(neg_value - pos_value) < 1e-9:
            return f"± {_fmt_number(pos_value, decimals)} {unit}"
        return (
            f"-{_fmt_number(neg_value, decimals)} {unit} / "
            f"+{_fmt_number(pos_value, decimals)} {unit}"
        )
    if minimum is not None:
        return f"≥ {minimum} {unit}"
    if maximum is not None:
        return f"≤ {maximum} {unit}"
    return "N/A"


def _filters_text(data: ReportData) -> str:
    filters = data.filters
    parts = []
    if filters.sectors:
        parts.append("Sectores: " + ", ".join(filters.sectors))
    if filters.sections:
        parts.append("Secciones: " + ", ".join(filters.sections))
    if filters.levels:
        parts.append("Niveles: " + ", ".join(filters.levels))
    if filters.benches:
        parts.append("Bancos: " + ", ".join(str(b) for b in filters.benches))
    return " · ".join(parts) if parts else "Sin filtros"


def _process_text(data: ReportData) -> str:
    meta = data.meta or {}
    process = meta.get("process") or meta.get("process_settings") or {}
    if not isinstance(process, dict):
        process = {}
    merged = dict(meta)
    merged.update(process)
    parts = []
    for key, label, unit, decimals in _PROCESS_ROWS:
        value = _fmt_number(merged.get(key), decimals)
        if value is not None:
            parts.append(f"{label}: {value} {unit}")
    return " · ".join(parts) if parts else "Sin configuración de proceso registrada."


def _criteria_section(story: list, data: ReportData, styles: dict) -> None:
    rows = [
        [
            Paragraph("Criterio", styles["table_header"]),
            Paragraph("Tolerancia efectiva", styles["table_header"]),
        ]
    ]
    for key, label, unit, decimals in _TOLERANCE_ROWS:
        if key not in (data.tolerances or {}):
            continue
        rows.append(
            [
                Paragraph(label, styles["cell"]),
                Paragraph(
                    _tolerance_value(data.tolerances.get(key), unit, decimals),
                    styles["cell_center"],
                ),
            ]
        )
    if len(rows) == 1:
        rows.append(
            [Paragraph("Tolerancias", styles["cell"]), Paragraph("N/A", styles["cell_center"])]
        )
    story.append(_base_table(rows, col_widths=[7.5 * cm, 7.0 * cm], align_center_from=1))
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(f"<b>Filtros aplicados:</b> {_esc(_filters_text(data))}", styles["body"])
    )
    story.append(Paragraph(f"<b>Proceso:</b> {_esc(_process_text(data))}", styles["body"]))
    story.append(Paragraph(
            "Para altura y ángulo: CUMPLE dentro de tolerancia; FUERA DE TOLERANCIA "
            "hasta 1,5 veces la tolerancia; NO CUMPLE sobre 1,5 veces, según la "
            "clasificación del modelo. Para berma, se compara el ancho con el mínimo "
            "configurado; esta regla no usa los tres tramos de tolerancia.",
        styles["note"],
    ))
    meta = data.meta or {}
    design_file = meta.get("design_file") or meta.get("design_filename") or "No disponible en metadatos"
    topo_file = meta.get("topo_file") or meta.get("topo_filename") or "No disponible en metadatos"
    story.append(
        Paragraph(
            f"<b>Fuentes:</b> diseño {_esc(design_file)} · "
            f"topografía {_esc(topo_file)}",
            styles["body"],
        )
    )


def _parameters_section(story: list, data: ReportData, styles: dict) -> None:
    parameters = [p for p in data.parameters if (p.cumple + p.no_cumple) > 0]
    if not parameters:
        story.append(
            Paragraph("No hay registros con estado de parámetro disponible para los filtros aplicados.", styles["body"])
        )
        return
    rows = [
        [
            Paragraph("Parámetro", styles["table_header"]),
            Paragraph("Criterio", styles["table_header"]),
            Paragraph("Cumple", styles["table_header"]),
            Paragraph("Otros estados", styles["table_header"]),
            Paragraph("Con estado", styles["table_header"]),
            Paragraph("% cumple", styles["table_header"]),
            Paragraph("Media real (n)", styles["table_header"]),
        ]
    ]
    for parameter in parameters:
        decimals = 2 if parameter.unit == "m" else 1
        mean = _fmt_number(parameter.mean_real, decimals)
        status_key = f"{parameter.parameter}_status"
        real_key = f"{parameter.parameter}_real"
        real_count = sum(
            1 for row in data.rows
            if getattr(row, status_key) and getattr(row, status_key) != "-"
            and getattr(row, real_key) is not None
        )
        denominator = parameter.cumple + parameter.no_cumple
        tolerance = _tolerance_value(
            (data.tolerances or {}).get(_PARAMETER_TOLERANCE_KEYS[parameter.parameter]),
            parameter.unit,
            decimals,
        )
        rows.append(
            [
                Paragraph(f"{_esc(parameter.label)} ({_esc(parameter.unit)})", styles["cell"]),
                Paragraph(_esc(tolerance), styles["cell_center"]),
                Paragraph(str(parameter.cumple), styles["cell_center"]),
                Paragraph(str(parameter.no_cumple), styles["cell_center"]),
                Paragraph(str(denominator), styles["cell_center"]),
                Paragraph(_fmt_pct(parameter.pct_cumple) or "N/A", styles["cell_center"]),
                Paragraph(
                    f"{mean} {parameter.unit} ({real_count})" if mean is not None else "N/A",
                    styles["cell_center"],
                ),
            ]
        )
    story.append(
        _base_table(
            rows,
            col_widths=[3.5 * cm, 2.7 * cm, 1.8 * cm, 2.1 * cm, 1.8 * cm, 1.6 * cm, 3.0 * cm],
            align_center_from=1,
        )
    )
    story.append(Paragraph(
        "El denominador ‘Con estado’ suma los conteos del modelo. ‘Otros estados’ "
        "agrupa estados registrados distintos de CUMPLE, incluidos FUERA DE "
        "TOLERANCIA y NO CUMPLE; no equivale solo a NO CUMPLE. Los registros sin "
        "estado no entran en ese denominador; las donas usan estos mismos conteos. "
        "La media real muestra entre paréntesis "
        "el número de valores reales disponibles con estado registrado.",
        styles["note"],
    ))

    donuts = parameter_donuts_png(
        [
            {
                "label": parameter.label,
                "cumple": parameter.cumple,
                "no_cumple": parameter.no_cumple,
            }
            for parameter in parameters
        ]
    )
    if donuts:
        story.append(Spacer(1, 0.4 * cm))
        story.append(_image(donuts, max_width=CONTENT_WIDTH))


def _berm_details(story: list, data: ReportData, styles: dict) -> None:
    if not data.rows:
        return
    story.append(Paragraph("Detalle de berma por banco", styles["h2"]))
    story.append(Paragraph(
        "La berma efectiva es un indicador separado y no modifica el estado de la berma bruta.",
        styles["note"],
    ))
    for row in data.rows:
        bench = "sin dato" if row.bench_num is None else f"{'T' if row.type == 'EXTRA' else 'D'}{row.bench_num}"
        real = _fmt_length(row.berm_real) or "sin dato"
        effective = _fmt_length(row.effective_berm) or "sin dato"
        deviation = _fmt_number(row.berm_dev, 2)
        deviation = "sin dato" if deviation is None else f"{float(deviation):+.2f} m"
        gross_status = row.berm_status or "sin dato"
        effective_status = row.effective_berm_status or "sin dato"
        text = (
            f"Sección {row.section} · Banco {bench}: berma real {real}; "
            f"estado berma {gross_status}; desviación berma {deviation}; "
            f"berma efectiva {effective}; estado berma efectiva {effective_status}."
        )
        story.append(Paragraph(_esc(text), styles["note"]))


def _sector_available(data: ReportData) -> bool:
    achievement = data.design_achievement or {}
    sectors = [s for s in (achievement.get("sectors") or []) if isinstance(s, dict)]
    return bool(sectors) and any(s.get("global_score") is not None for s in sectors)


def _sector_section(story: list, data: ReportData, styles: dict) -> bool:
    achievement = data.design_achievement or {}
    sectors = [s for s in (achievement.get("sectors") or []) if isinstance(s, dict)]
    if not sectors or not any(s.get("global_score") is not None for s in sectors):
        return False
    rows = [
        [
            Paragraph("Sector", styles["table_header"]),
            Paragraph("Logro (0-100)", styles["table_header"]),
            Paragraph("Cresta % (n)", styles["table_header"]),
            Paragraph("Pie % (n)", styles["table_header"]),
            Paragraph("Berma % (n)", styles["table_header"]),
            Paragraph("Filas con algún componente", styles["table_header"]),
        ]
    ]
    for sector in sectors:
        score = sector.get("global_score")
        rows.append(
            [
                Paragraph(_esc(sector.get("sector") or "Sin sector"), styles["cell"]),
                Paragraph("N/A" if score is None else str(score), styles["cell_center"]),
                Paragraph(f"{_fmt_pct(sector.get('crest_pct')) or 'N/A'} ({sector.get('crest_denom', 0)})", styles["cell_center"]),
                Paragraph(f"{_fmt_pct(sector.get('toe_pct')) or 'N/A'} ({sector.get('toe_denom', 0)})", styles["cell_center"]),
                Paragraph(f"{_fmt_pct(sector.get('berm_pct')) or 'N/A'} ({sector.get('berm_denom', 0)})", styles["cell_center"]),
                Paragraph(str(sector.get("n_evaluable", 0)), styles["cell_center"]),
            ]
        )
    story.append(
        _base_table(
            rows,
            col_widths=[3.2 * cm, 2.3 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 3.1 * cm],
            align_center_from=1,
        )
    )
    story.append(
        Paragraph(
            "El puntaje global usa componentes disponibles por registro. ‘Filas con "
            "algún componente’ cuenta registros con al menos una desviación de cresta "
            "o pie, o un estado de berma. Cada porcentaje muestra su propio n "
            "disponible; cresta y pie usan la tolerancia efectiva de la sesión.",
            styles["note"],
        )
    )
    return True


def _deviation_table(parameter: str, entries: list, styles: dict) -> Table:
    """Small top-deviation table for one parameter, headers carrying its unit."""
    _label, unit, decimals = _PARAMETER_LABELS.get(parameter, (parameter, "", 2))
    headers = (
        "#",
        "Sección",
        "Banco",
        f"Diseño ({unit})",
        f"Real ({unit})",
        f"Desv. criterio ({unit})",
        "Base e índice",
        "Estado",
    )
    rows = [[Paragraph(_esc(header), styles["table_header"]) for header in headers]]
    style_cmds = []
    for index, entry in enumerate(entries, start=1):
        status = parse_bench_status(entry.get("status"))
        design = _fmt_number(entry.get("design"), decimals)
        real = _fmt_number(entry.get("real"), decimals)
        deviation = _fmt_number(entry.get("deviation"), decimals)
        tolerance_text = _esc(entry.get("tolerance_text") or "No disponible")
        ratio = _fmt_number(entry.get("ratio"), 2)
        criterion_label = "déficit/mínimo" if entry.get("criterion") == "min" else "|desvío|/límite"
        bench = entry.get("bench_num")
        rows.append(
            [
                Paragraph(str(index), styles["cell_center"]),
                Paragraph(_esc(entry.get("section")), styles["cell_center"]),
                Paragraph("—" if bench is None else f"B{bench}", styles["cell_center"]),
                Paragraph("—" if design is None else design, styles["cell_center"]),
                Paragraph("—" if real is None else real, styles["cell_center"]),
                Paragraph("—" if deviation is None else deviation, styles["cell_center"]),
                Paragraph(f"{tolerance_text}<br/>{criterion_label}: {ratio or '—'}×", styles["cell_center"]),
                _status_paragraph(status, styles),
            ]
        )
        row_index = len(rows) - 1
        style_cmds.append(
            ("BACKGROUND", (7, row_index), (7, row_index), STATUS_FILL[status])
        )
    table = _base_table(
        rows,
        col_widths=[
            0.7 * cm,
            1.8 * cm,
            1.2 * cm,
            1.8 * cm,
            1.8 * cm,
            3.1 * cm,
            4.0 * cm,
            2.3 * cm,
        ],
        align_center_from=0,
    )
    table.setStyle(TableStyle(style_cmds))
    return table


def _deviations_section(story: list, data: ReportData, styles: dict) -> None:
    deviations = [entry for entry in (data.top_deviations or ()) if isinstance(entry, dict)]
    if not deviations:
        story.append(
            Paragraph(
                "No hay desviaciones prioritarias calculables con los datos y criterios disponibles.",
                styles["body"],
            )
        )
        return
    grouped: dict[str, list] = {}
    for entry in deviations:
        grouped.setdefault(str(entry.get("parameter") or ""), []).append(entry)
    ordered = [parameter for parameter in _DEVIATION_PARAMETER_ORDER if grouped.get(parameter)]
    ordered += sorted(
        parameter for parameter in grouped if parameter not in _DEVIATION_PARAMETER_ORDER
    )
    story.append(
        Paragraph(
            "Prioridades ordenadas por parámetro: hasta "
            f"{_MAX_DEVIATIONS_PER_PARAMETER} mayores de cada uno, usando el índice "
            "que muestra cada fila. Altura y ángulo usan |desviación| dividido por "
            "el límite de tolerancia en el sentido del desvío. Berma usa el déficit "
            "respecto del mínimo dividido por ese mínimo, solo cuando la berma real "
            "está bajo el criterio. ‘Desv. criterio’ conserva la diferencia calculada "
            "por el modelo; diseño, real y estado provienen de la fila comparativa.",
            styles["note"],
        )
    )
    for parameter in ordered:
        entries = grouped[parameter]
        shown = entries[:_MAX_DEVIATIONS_PER_PARAMETER]
        label = _PARAMETER_LABELS.get(parameter, (parameter, "", 2))[0]
        story.append(
            Paragraph(
                f"{_esc(label or 'Parámetro')} — {len(shown)} de {len(entries)} mayores",
                styles["group"],
            )
        )
        story.append(_deviation_table(parameter, shown, styles))
        story.append(Spacer(1, 0.2 * cm))


def _geometry_entry(entry: Any) -> Optional[dict]:
    if isinstance(entry, dict):
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


def _contours_from_mesh(
    mesh: Any, max_points: int = 60000, grid_size: int = 160, interval: float = 10.0
) -> Optional[dict]:
    if mesh is None:
        return None
    try:
        vertices = np.asarray(getattr(mesh, "vertices"), dtype=float)
    except Exception:
        return None
    if vertices.ndim != 2 or vertices.shape[1] < 3 or vertices.shape[0] < 32:
        return None
    if vertices.shape[0] > max_points:
        step = int(np.ceil(vertices.shape[0] / max_points))
        vertices = vertices[::step]
    z = vertices[:, 2]
    if not np.all(np.isfinite(z)):
        return None
    return {
        "x": vertices[:, 0].tolist(),
        "y": vertices[:, 1].tolist(),
        "z": z.tolist(),
        "grid_size": grid_size,
        "interval": interval,
        "grid_ref": float(np.floor(float(z.min()) / interval) * interval),
    }


def _plan_sections(data: ReportData) -> tuple:
    plan_inputs = data.plan_inputs
    raw = None
    contours = None
    if isinstance(plan_inputs, dict):
        raw = plan_inputs.get("sections")
        candidate = plan_inputs.get("contours")
        if isinstance(candidate, (dict, list)):
            contours = candidate
        if contours is None:
            contours = _contours_from_mesh(plan_inputs.get("mesh_topo"))
    elif isinstance(plan_inputs, list):
        raw = plan_inputs
    if not raw:
        raw = [
            geometry
            for geometry in (data.section_geometry or ())
            if isinstance(geometry, dict)
            and ("origin" in geometry or "polyline" in geometry)
        ]
    sections = []
    for entry in raw or ():
        section = _geometry_entry(entry)
        if section is None:
            continue
        name = section.get("name") or section.get("section") or section.get("section_name")
        section["name"] = "" if name is None else str(name)
        sections.append(section)

    name_counts = {}
    for section in sections:
        name_counts[section["name"]] = name_counts.get(section["name"], 0) + 1
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
    return sections, contours


def _image(png_bytes: bytes, max_width: float) -> Image:
    reader = ImageReader(io.BytesIO(png_bytes))
    width, height = reader.getSize()
    ratio = min(max_width / float(width), CONTENT_HEIGHT / float(height))
    return Image(
        io.BytesIO(png_bytes),
        width=float(width) * ratio,
        height=float(height) * ratio,
        hAlign="CENTER",
    )


def _render_plan(data: ReportData) -> Optional[bytes]:
    sections, contours = _plan_sections(data)
    if not sections:
        return None
    return plan_view_png(sections, contours=contours)


def _blast_rows(data: ReportData, styles: dict) -> Optional[list]:
    blast = data.blast
    if not isinstance(blast, dict):
        return None
    holes = [h for h in (blast.get("holes") or []) if isinstance(h, dict)]
    if not holes:
        return None

    def _values(*keys: str) -> list:
        out = []
        for hole in holes:
            for key in keys:
                raw = hole.get(key)
                if raw is None:
                    continue
                try:
                    number = float(raw)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(number):
                    continue
                out.append(number)
                break
        return out

    rows = [
        [
            Paragraph("Pozos registrados", styles["cell"]),
            Paragraph(str(len(holes)), styles["cell_center"]),
        ]
    ]
    if any(
        hole.get("Z_collar_semantic", hole.get("z_collar_semantic")) == "design_surface_estimate"
        for hole in holes
    ):
        rows.append(
            [
                Paragraph("Advertencia sobre la cota", styles["cell"]),
                Paragraph(
                    "La Z del collar de algunos pozos fue estimada desde la superficie de diseño; no es una medición de terreno ni una cota real levantada.",
                    styles["cell"],
                ),
            ]
        )
    collars = _values("Z_collar", "cota_collar", "collar_z")
    if collars:
        rows.append(
            [
                Paragraph("Cota de collar (mín. / máx.)", styles["cell"]),
                Paragraph(
                    f"{_fmt_number(min(collars), 2)} m / {_fmt_number(max(collars), 2)} m",
                    styles["cell_center"],
                ),
            ]
        )
    burdens = _values("Burden", "burden")
    if burdens:
        rows.append(
            [
                Paragraph("Burden promedio", styles["cell"]),
                Paragraph(_fmt_length(sum(burdens) / len(burdens)) or "—", styles["cell_center"]),
            ]
        )
    spacings = _values("Esp", "espaciamiento", "spacing")
    if spacings:
        rows.append(
            [
                Paragraph("Espaciamiento promedio", styles["cell"]),
                Paragraph(
                    _fmt_length(sum(spacings) / len(spacings)) or "—",
                    styles["cell_center"],
                ),
            ]
        )
    tolerance = blast.get("tolerance")
    tol_value = tolerance.get("pos") if isinstance(tolerance, dict) else tolerance
    formatted_tolerance = _fmt_length(tol_value)
    rows.append(
        [
            Paragraph("Tolerancia cresta-pie aplicada", styles["cell"]),
            Paragraph(
                f"± {formatted_tolerance}" if formatted_tolerance else "—",
                styles["cell_center"],
            ),
        ]
    )
    return rows


def _build_pdf_report_unlocked(data: ReportData) -> io.BytesIO:
    """Build the executive PDF report from ``data`` and return a seekable buffer."""
    styles = _report_styles()
    story: list = []
    project = str((data.meta or {}).get("project") or "Proyecto no especificado")

    _cover(story, data, styles)
    number = 1

    story.append(Paragraph(f"{number}. Resumen ejecutivo", styles["h1"]))
    _summary_section(story, data, styles)
    number += 1

    if data.depth and data.depth.get("profundidad") is not None:
        story.append(Paragraph(f"{number}. Profundidad del rajo", styles["h1"]))
        _depth_section(story, data, styles)
        number += 1

    story.append(PageBreak())
    story.append(Paragraph(f"{number}. Criterios", styles["h1"]))
    _criteria_section(story, data, styles)
    number += 1

    story.append(PageBreak())
    story.append(Paragraph(f"{number}. Cumplimiento por parámetro", styles["h1"]))
    _parameters_section(story, data, styles)
    _berm_details(story, data, styles)
    number += 1

    if _sector_available(data):
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(f"{number}. Logro de diseño por sector", styles["h1"]))
        _sector_section(story, data, styles)
        number += 1

    story.append(PageBreak())
    story.append(Paragraph(f"{number}. Mayores desviaciones", styles["h1"]))
    _deviations_section(story, data, styles)
    number += 1

    plan_png = _render_plan(data)
    story.append(PageBreak())
    story.append(Paragraph(f"{number}. Plano de cumplimiento", styles["h1"]))
    if plan_png:
        story.append(_image(plan_png, max_width=CONTENT_WIDTH))
    else:
        story.append(Paragraph(
            "No hay geometría de secciones disponible para generar el plano en este informe.",
            styles["body"],
        ))
    number += 1

    blast_rows = _blast_rows(data, styles)
    if blast_rows:
        story.append(PageBreak())
        story.append(Paragraph(f"{number}. Resumen de tronadura", styles["h1"]))
        story.append(
            _base_table(
                [[Paragraph("Métrica", styles["table_header"]), Paragraph("Valor", styles["table_header"])]]
                + blast_rows,
                col_widths=[7.5 * cm, 7.0 * cm],
                align_center_from=1,
            )
        )
        from core.blast_correlation import PF_DEFINITIONS

        story.append(Paragraph("PF principal (g/t): 1000*Q/(A*H*rho), área de Voronoi por huella y altura de banco.", styles["body"]))
        for name, definition in PF_DEFINITIONS.items():
            story.append(Paragraph(_esc(f"{name} ({definition['unit']}): {definition['formula']}"), styles["note"]))
        blast = data.blast or {}
        if blast.get("data_status") == "legacy_reimport_required":
            story.append(Paragraph("datos de pozos importados con una versión anterior: reimportar", styles["body"]))
        consolidation = blast.get("consolidation_report")
        if isinstance(consolidation, dict) and consolidation:
            story.append(Paragraph(_esc(
                f"Consolidación: pozos {consolidation.get('holes_out', 'sin dato')}; "
                f"copias eliminadas {consolidation.get('exact_copies_removed', 'sin dato')}; "
                f"filas de decks fusionadas {consolidation.get('deck_rows_merged', 'sin dato')}."
            ), styles["body"]))
        holes = blast.get("holes") or []
        story.append(Paragraph(f"Detalle PF principal: primeros {min(len(holes), 60)} de {len(holes)} pozos.", styles["body"]))
        for index, hole in enumerate(holes[:60]):
            if not isinstance(hole, dict):
                continue
            value = _fmt_number(hole.get("pf_voronoi_bench_g_per_ton"), 2) or "sin dato"
            name = hole.get("id_pozo") or hole.get("hole_id") or hole.get("label_pozo") or "sin dato"
            status = hole.get("pf_voronoi_bench_status") or "sin dato"
            story.append(Paragraph(_esc(f"Pozo {name}: {value} g/t; estado {status}."), styles["note"]))
            if hole.get("decks"):
                story.append(Paragraph(_esc(f"Decks {hole['decks']}; mezcla {hole.get('explosive_mix', {})}; filas {hole.get('source_row_indices', [])}; copias eliminadas {hole.get('duplicate_rows_removed', 0)}."), styles["note"]))
        number += 1

    story.append(Spacer(1, 0.6 * cm))
    story.append(
        Paragraph(
            f"Generado el {_esc(_fmt_date((data.meta or {}).get('generated_at'))) or 'N/A'} "
            "— Conciliación Geotécnica v02.",
            styles["note"],
        )
    )

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title="Informe de Conciliación Geotécnica",
        author=str((data.meta or {}).get("author") or "Conciliación Geo v02"),
        subject="Conciliación Geotécnica — Reporte Ejecutivo",
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
        return _NumberedCanvas(*args, project=project, **kwargs)

    doc.build(story, canvasmaker=_canvas_factory)
    buffer.seek(0)
    return buffer


def build_pdf_report(data: ReportData) -> io.BytesIO:
    """Build a PDF while serializing ReportLab's shared font state."""
    with _PDF_BUILD_LOCK:
        return _build_pdf_report_unlocked(data)


__all__ = ["build_pdf_report"]
