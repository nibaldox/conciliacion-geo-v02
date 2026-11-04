"""Web Word report builder driven by the frozen ``ReportData`` model.

Renders the Spanish compliance report served by the web API: cover with
revision/approval block, updateable TOC field, executive summary (profiles by
worst bench, weighted score reported separately with its definition, design
achievement, deterministic conclusions and warnings), criteria and tolerances,
parameter compliance with donuts, per-sector design achievement, compliance
plan view, per-bench table with readable status labels, readable section
profiles (two per landscape page side by side for non-compliant profiles plus a
compact two-up annex) and the blast section when holes are present.

The module is presentation-only: it reads ``ReportData`` and never recomputes
domain values. A section whose input is missing keeps its numbered heading and
renders a one-line note instead of tables or images.
"""

from __future__ import annotations

import io
import math
from typing import Any, Mapping, Optional

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Mm, Pt, RGBColor

from core import report_charts
from core.report_data import ProfileSummary, ReportData, parse_bench_status
from core.word_report_layout import (
    REPORT_TITLE,
    _append_field,
    _set_cell_fill,
    configure_document,
    style_data_table,
)

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

NON_COMPLIANT = ("FUERA", "NO_CUMPLE")

PROFILE_DPI = 110

DETAIL_COLUMNS = 2

DETAIL_COLUMN_MM = 131

DETAIL_IMAGE_HEIGHT_MM = 150

DETAIL_ANNEX_HEIGHT_MM = 120

EMPTY = "—"

TOC_INSTRUCTION = 'TOC \\o "1-3" \\h \\z \\u'

_TOLERANCE_LABELS = (
    ("bench_height", "Altura de banco", "m", "signed"),
    ("face_angle", "Ángulo de cara", "°", "signed"),
    ("berm_width", "Ancho de berma", "m", "min"),
    ("crest_toe_deviation", "Desviación cresta-pie", "m", "signed"),
    ("inter_ramp_angle", "Ángulo inter-rampa", "°", "signed"),
    ("overall_angle", "Ángulo global", "°", "signed"),
)

_META_LABELS = (
    ("project", "Proyecto"),
    ("operation", "Operación"),
    ("phase", "Fase"),
    ("author", "Elaborado por"),
    ("design_file", "Archivo de diseño"),
    ("topo_file", "Archivo de topografía"),
    ("generated_at", "Generado"),
)

_META_ALTERNATES = {
    "design_file": ("design_filename", "design_file_name"),
    "topo_file": ("topo_filename", "topo_file_name"),
    "generated_at": ("generated", "date"),
}


def _parameter_status_text(status: Optional[str]) -> str:
    if status is None or not str(status).strip() or str(status).strip() == "-":
        return EMPTY
    normalized = str(status).strip().upper().replace("_", " ")
    return {
        "CUMPLE": "CUMPLE",
        "FUERA": "FUERA DE TOLERANCIA",
        "FUERA DE TOLERANCIA": "FUERA DE TOLERANCIA",
        "NO CUMPLE": "NO CUMPLE",
        "NO CONSTRUIDO": "NO CONSTRUIDO",
        "BANCO ADICIONAL": "BANCO ADICIONAL",
        "EXTRA": "BANCO ADICIONAL",
        "UNKNOWN": "SIN EVALUAR",
        "SIN EVALUAR": "SIN EVALUAR",
    }.get(normalized, normalized)


def _bench_identity(row) -> str:
    if row.bench_num is None:
        return EMPTY
    return f"{'T' if row.type == 'EXTRA' else 'D'}{row.bench_num}"

_PROFILE_COLUMNS = (
    ("section", "Sección", 0.9, lambda r: r.section or EMPTY, "text"),
    ("sector", "Sector", 0.8, lambda r: r.sector or "", "text"),
    ("bench", "Banco (D/T)", 0.8, _bench_identity, "text"),
    ("level", "Nivel", 0.7, lambda r: r.level or "", "text"),
    ("h_design", "Altura diseño (m)", 0.9, lambda r: _fmt(r.height_design, 2), "num"),
    ("h_real", "Altura real (m)", 0.9, lambda r: _fmt(r.height_real, 2), "num"),
    ("h_dev", "Desv. altura (m)", 0.9, lambda r: _fmt_signed(r.height_dev, 2), "num"),
    ("a_design", "Ángulo diseño (°)", 0.9, lambda r: _fmt(r.angle_design, 1), "num"),
    ("a_real", "Ángulo real (°)", 0.9, lambda r: _fmt(r.angle_real, 1), "num"),
    ("a_dev", "Desv. ángulo (°)", 0.9, lambda r: _fmt_signed(r.angle_dev, 1), "num"),
    ("b_design", "Berma diseño (m)", 0.9, lambda r: _fmt(r.berm_design, 2), "num"),
    ("b_real", "Berma real (m)", 0.9, lambda r: _fmt(r.berm_real, 2), "num"),
    ("b_dev", "Desv. berma (m)", 0.9, lambda r: _fmt_signed(r.berm_dev, 2), "num"),
    ("spill", "Derrame (m)", 0.9, lambda r: _fmt(r.spill_width, 2), "num"),
    ("effective", "Berma efectiva (m)", 0.9, lambda r: _fmt(r.effective_berm, 2), "num"),
    ("h_status", "Estado altura", 0.8, lambda r: _parameter_status_text(r.height_status), "text"),
    ("a_status", "Estado ángulo", 0.8, lambda r: _parameter_status_text(r.angle_status), "text"),
    ("b_status", "Estado berma", 0.8, lambda r: _parameter_status_text(r.berm_status), "text"),
    ("status", "Estado banco", 1.2, lambda r: r.status_label or EMPTY, "status"),
)


def _fmt(value: Optional[float], decimals: int) -> str:
    return EMPTY if value is None else f"{float(value):.{decimals}f}"


def _fmt_signed(value: Optional[float], decimals: int) -> str:
    return EMPTY if value is None else f"{float(value):+.{decimals}f}"


def _fmt_pct(value: Any) -> str:
    return EMPTY if value is None else f"{float(value):.1f}%"


def _is_empty_value(value: Any) -> bool:
    return value is None or str(value).strip() in ("", EMPTY, "-")


def _text(meta: Mapping[str, Any], key: str) -> str:
    for candidate in (key,) + _META_ALTERNATES.get(key, ()):
        value = meta.get(candidate)
        if value not in (None, ""):
            return str(value)
    return ""


def _status_label(worst_status: str) -> str:
    return report_charts.STATUS_LABELS_ES.get(worst_status, report_charts.STATUS_LABELS_ES["UNKNOWN"])


def _compress_png(blob: bytes):
    """Re-encode a chart PNG as an optimized 128-colour palette image.

    Charts are flat-coloured line art, so palette quantization keeps them
    readable while cutting the embedded file size by roughly two thirds — the
    difference between a 3.5 MB and a sub-1.5 MB report. The palette is built
    without dithering: flat art gains nothing from it and the quantizer is
    faster. Returns ``(blob, width, height)`` so the caller never decodes the
    image a second time just to read its pixel size.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(blob)) as image:
            image.load()
            quantized = image.convert("RGB").quantize(
                colors=128, method=Image.MEDIANCUT, dither=Image.Dither.NONE
            )
            output = io.BytesIO()
            quantized.save(output, format="PNG", optimize=True)
            return output.getvalue(), quantized.width, quantized.height
    except Exception:
        return blob, None, None


def _add_picture_bounded(paragraph, blob: bytes, max_width, max_height):
    run = paragraph.add_run()
    blob, width, height = _compress_png(blob)
    if not width or not height:
        run.add_picture(io.BytesIO(blob))
        return run
    scale = min(float(max_width) / width, float(max_height) / height)
    run.add_picture(
        io.BytesIO(blob),
        width=Emu(int(width * scale)),
        height=Emu(int(height * scale)),
    )
    return run


def _enable_field_updates(doc) -> None:
    """Ask Word to refresh fields (TOC, page numbers) when the file opens."""
    settings = doc.settings.element
    element = settings.find(qn("w:updateFields"))
    if element is None:
        element = OxmlElement("w:updateFields")
        settings.append(element)
    element.set(qn("w:val"), "true")


def _heading(doc, text: str, level: int = 1, page_break: bool = False):
    """Add a heading that cannot be orphaned at the foot of a page.

    ``keep_with_next`` keeps the heading with the paragraph, table or image it
    introduces; ``page_break`` starts a major section on a fresh page.
    """
    heading = doc.add_heading(text, level)
    heading.paragraph_format.keep_with_next = True
    if page_break:
        heading.paragraph_format.page_break_before = True
    return heading


def _borderless_table(doc, rows: int, cols: int):
    """Add an explicit border-free table, used as the image grid frame."""
    table = doc.add_table(rows=rows, cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    tblPr = table._tbl.tblPr
    getter = getattr(tblPr, "get_or_add_tblBorders", None)
    borders = getter() if getter is not None else tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "none")
        element.set(qn("w:sz"), "0")
        element.set(qn("w:space"), "0")
        borders.append(element)
    return table


def _image_paragraph(doc, blob: bytes, max_width, max_height) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(4)
    _add_picture_bounded(paragraph, blob, max_width, max_height)


def _format_filters(filters) -> str:
    if filters is None or filters.is_empty():
        return "Sin filtros"
    parts = []
    if filters.sectors:
        parts.append("sectores: " + ", ".join(filters.sectors))
    if filters.sections:
        parts.append("secciones: " + ", ".join(filters.sections))
    if filters.levels:
        parts.append("niveles: " + ", ".join(filters.levels))
    if filters.benches:
        parts.append("bancos de diseño: " + ", ".join(f"D{b}" for b in filters.benches))
    return "; ".join(parts)


def _display_count(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return EMPTY
    try:
        number = int(value)
    except (TypeError, ValueError):
        return EMPTY
    return str(number)


def _status_counts(data: ReportData) -> dict[str, int]:
    counts = data.profile_counts or {}
    return {
        "CUMPLE": int(counts.get("CUMPLE", 0) or 0),
        "FUERA": int(counts.get("FUERA", 0) or 0),
        "NO_CUMPLE": int(counts.get("NO_CUMPLE", 0) or 0),
    }


def _add_cover(doc, meta: Mapping[str, Any], data: Optional[ReportData] = None) -> None:
    title = doc.add_heading(REPORT_TITLE, 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(96)
    title.paragraph_format.space_after = Pt(24)

    lines = [
        ("Proyecto", _text(meta, "project") or "No informado"),
        ("Operación", _text(meta, "operation") or "No informada"),
        ("Fase", _text(meta, "phase") or "No informada"),
        ("Elaborado por", _text(meta, "author") or "No informado"),
        ("Fecha", _text(meta, "generated_at") or "No informada"),
    ]
    for label, value in lines:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(4)
        label_run = paragraph.add_run(f"{label}: ")
        label_run.bold = True
        label_run.font.size = Pt(12)
        paragraph.add_run(str(value)).font.size = Pt(12)

    doc.add_paragraph()
    block = doc.add_paragraph()
    block.alignment = WD_ALIGN_PARAGRAPH.CENTER
    block.paragraph_format.space_after = Pt(4)
    heading_run = block.add_run("Control de revisión y aprobación")
    heading_run.bold = True
    heading_run.font.size = Pt(12)

    if data is not None:
        _heading(doc, "Alcance del resultado", 2)
        scope_rows = [("Filtros aplicados", _format_filters(data.filters))]
        for key, label in (("design_file", "Superficie de diseño"), ("topo_file", "Superficie topográfica")):
            value = _text(meta, key)
            if value:
                scope_rows.append((label, value))
        counts = data.counts or {}
        available_counts = [
            ("Registros de banco en el modelo", counts.get("n_rows")),
            ("Emparejados", counts.get("n_match")),
            ("No construidos", counts.get("n_missing")),
            ("Adicionales", counts.get("n_extra")),
        ]
        scope_rows.extend((label, _display_count(value)) for label, value in available_counts)
        scope_table = doc.add_table(rows=1, cols=2)
        scope_table.rows[0].cells[0].text = "Alcance"
        scope_table.rows[0].cells[1].text = "Dato disponible"
        for label, value in scope_rows:
            cells = scope_table.add_row().cells
            cells[0].text = label
            cells[1].text = value
        style_data_table(scope_table, column_weights=[1.1, 2.2])

    revision_rows = [
        ("Revisión", _text(meta, "revision") or "No informada"),
        ("Elaborado por", _text(meta, "author") or "No informado"),
        ("Revisado por", _text(meta, "reviewed_by") or "No informado"),
        ("Aprobado por", _text(meta, "approved_by") or "No informado"),
        ("Fecha de emisión", _text(meta, "generated_at") or "No informada"),
    ]
    table = doc.add_table(rows=len(revision_rows), cols=2)
    for row_idx, (label, value) in enumerate(revision_rows):
        cells = table.rows[row_idx].cells
        cells[0].text = label
        cells[1].text = str(value)
    style_data_table(table, column_weights=[1.0, 2.2])

    doc.add_page_break()


def _add_toc(doc) -> None:
    _heading(doc, "Índice", 1)
    paragraph = doc.add_paragraph()
    _append_field(paragraph, TOC_INSTRUCTION)
    note = doc.add_paragraph(
        "El índice se actualiza al abrir el documento en Word (Referencias → "
        "Actualizar tabla) o con la combinación Ctrl+E, F9."
    )
    for run in note.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor.from_string("7F7F7F")
    doc.add_page_break()


def _add_executive_summary(doc, data: ReportData) -> None:
    _heading(doc, "1. Resumen ejecutivo", 1)
    doc.add_paragraph(
        "El estado de cada perfil sigue el peor estado entre los registros de banco "
        "asociados al perfil, incluidos los faltantes y los adicionales. Un banco "
        "emparejado cumple con 70 puntos o más; sus mediciones individuales "
        "conservan sus estados de tolerancia. El puntaje global promedio y el "
        "logro de diseño son indicadores separados de la clasificación del perfil."
    )

    status_counts = _status_counts(data)
    classified_count = sum(status_counts.values())
    if classified_count:
        status_table = doc.add_table(rows=1, cols=3)
        for index, label in enumerate(("Estado del perfil", "Perfiles", "% del desglose")):
            status_table.rows[0].cells[index].text = label
        for status, label in (
            ("CUMPLE", "CUMPLE"),
            ("FUERA", "FUERA DE TOLERANCIA"),
            ("NO_CUMPLE", "NO CUMPLE"),
        ):
            count = status_counts[status]
            cells = status_table.add_row().cells
            cells[0].text = label
            cells[1].text = str(count)
            cells[2].text = f"{100.0 * count / classified_count:.1f}%"
        style_data_table(status_table, column_weights=[1.8, 0.7, 1.0])
        doc.add_paragraph(
            f"Denominador del desglose: {classified_count} perfiles con estado "
            "CUMPLE, FUERA o NO CUMPLE en el resumen del modelo. No se infiere "
            "una categoría adicional a partir de la diferencia con otros conteos."
        )
    else:
        doc.add_paragraph(
            "No hay perfiles clasificados como CUMPLE, FUERA o NO CUMPLE en el "
            "resumen disponible del modelo."
        )
    unknown_profiles = sum(
        profile.worst_status == "UNKNOWN" for profile in data.profiles
    )
    doc.add_paragraph(
        f"SIN EVALUAR (UNKNOWN): {unknown_profiles} "
        f"{'perfil' if unknown_profiles == 1 else 'perfiles'} en el detalle. "
        "Conteo directo de perfiles con ese estado; queda fuera del desglose "
        "porcentual de estados clasificados."
    )

    _heading(doc, "Indicadores complementarios", 2)
    indicator_table = doc.add_table(rows=1, cols=3)
    for index, label in enumerate(("Indicador", "Resultado", "Alcance informado")):
        indicator_table.rows[0].cells[index].text = label
    scored_profiles = sum(profile.weighted_score is not None for profile in data.profiles)
    score_cells = indicator_table.add_row().cells
    score_cells[0].text = "Puntaje ponderado global (0–100)"
    score_cells[1].text = "—" if data.global_weighted_score is None else f"{data.global_weighted_score:.1f}"
    score_cells[2].text = (
        f"Puntaje disponible en {scored_profiles} perfiles; dato separado del estado por peor banco."
        if scored_profiles
        else "Sin perfiles con puntaje disponible en el modelo."
    )

    achievement = (data.design_achievement or {}).get("global") or {}
    achievement_cells = indicator_table.add_row().cells
    achievement_cells[0].text = "Logro de diseño global (0–100)"
    score = achievement.get("global_score")
    achievement_cells[1].text = "—" if score is None else str(score)
    if score is None:
        achievement_cells[2].text = "Sin resultado disponible en el modelo."
    else:
        achievement_cells[2].text = (
            f"{_display_count(achievement.get('n_evaluable'))} de "
            f"{_display_count(achievement.get('n_total'))} bancos contabilizados; "
            "se considera evaluable si tiene al menos una desviación de cresta o pie, "
            "o un estado de berma disponible."
        )
    style_data_table(indicator_table, column_weights=[1.5, 0.9, 2.4])

    counts_row = data.counts or {}
    _heading(doc, "Alcance de la comparación", 2)
    scope_table = doc.add_table(rows=1, cols=2)
    scope_table.rows[0].cells[0].text = "Registro"
    scope_table.rows[0].cells[1].text = "Cantidad"
    for label, key in (
        ("Filas de comparación", "n_rows"),
        ("Emparejados", "n_match"),
        ("Bancos de diseño no construidos", "n_missing"),
        ("Bancos adicionales", "n_extra"),
        ("Secciones representadas en el modelo", "n_sections"),
    ):
        cells = scope_table.add_row().cells
        cells[0].text = label
        cells[1].text = _display_count(counts_row.get(key))
    style_data_table(scope_table, column_weights=[2.0, 0.8])

    if data.depth and data.depth.get("profundidad") is not None:
        _heading(doc, "Profundidad total de la excavación", 2)
        depth_table = doc.add_table(rows=1, cols=2)
        depth_table.rows[0].cells[0].text = "Métrica"
        depth_table.rows[0].cells[1].text = "Valor disponible"
        for metric, key in (
            ("Cota piso global", "cota_piso"),
            ("Cota cresta global", "cota_cresta"),
            ("Profundidad total", "profundidad"),
        ):
            cells = depth_table.add_row().cells
            value = data.depth.get(key)
            cells[0].text = metric
            cells[1].text = "—" if value is None else f"{float(value):.2f} m"
        style_data_table(depth_table, column_weights=[1.0, 1.0])
        doc.add_paragraph(
            f"Cotas de origen disponibles: {_display_count(data.depth.get('n_floors'))} de piso y "
            f"{_display_count(data.depth.get('n_crests'))} de cresta.",
            style="Caption",
        )
    else:
        doc.add_paragraph(
            "Profundidad total: no disponible en el modelo recibido.",
            style="Caption",
        )

    _heading(doc, "Conclusiones del modelo", 2)
    conclusions = [
        conclusion for conclusion in data.conclusions
        if not str(conclusion).startswith("Perfiles no conformes (peor banco NO CUMPLE):")
        and not str(conclusion).startswith("Puntaje ponderado global")
    ]
    if conclusions:
        for conclusion in conclusions:
            doc.add_paragraph(str(conclusion), style="List Bullet")
    else:
        doc.add_paragraph("No hay otras conclusiones generadas por el modelo.")

    _heading(doc, "Advertencias", 2)
    if data.warnings:
        for warning in data.warnings:
            doc.add_paragraph(str(warning), style="List Bullet")
    else:
        doc.add_paragraph("El modelo no registró advertencias para este informe.")


def _add_criteria(doc, data: ReportData) -> None:
    _heading(doc, "2. Alcance, fuentes y criterios", 1, page_break=True)

    _heading(doc, "Tolerancias aplicadas", 2)
    tolerances = data.tolerances or {}
    table = doc.add_table(rows=1, cols=3)
    headers = ("Parámetro", "Criterio", "Unidad")
    for idx, header in enumerate(headers):
        table.rows[0].cells[idx].text = header
    rendered = 0
    for key, label, unit, kind in _TOLERANCE_LABELS:
        tolerance = tolerances.get(key)
        if not isinstance(tolerance, Mapping):
            continue
        if kind == "min":
            minimum = tolerance.get("min")
            if minimum is None:
                continue
            criterion = f"Mínimo {float(minimum):.2f}"
        else:
            neg = tolerance.get("neg")
            pos = tolerance.get("pos")
            if neg is None and pos is None:
                continue
            neg_text = f"−{abs(float(neg)):.1f}" if neg is not None else "sin límite"
            pos_text = f"+{abs(float(pos)):.1f}" if pos is not None else "sin límite"
            criterion = f"{neg_text} / {pos_text}"
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = criterion
        cells[2].text = unit
        rendered += 1
    if rendered:
        style_data_table(table, column_weights=[1.4, 1.2, 0.5])
    else:
        doc.add_paragraph("Sin tolerancias declaradas en la sesión.")

    _heading(doc, "Ajustes de proceso", 2)
    process = data.meta.get("process")
    if not isinstance(process, Mapping):
        process = data.meta.get("process_settings")
    if isinstance(process, Mapping) and process:
        process_rows = [
            (key, value) for key, value in process.items()
            if value is not None and not (isinstance(value, float) and not math.isfinite(value))
        ]
    else:
        process_rows = []
    if process_rows:
        process_table = doc.add_table(rows=1, cols=2)
        process_table.rows[0].cells[0].text = "Ajuste"
        process_table.rows[0].cells[1].text = "Valor informado"
        for key, value in process_rows:
            cells = process_table.add_row().cells
            cells[0].text = str(key).replace("_", " ").capitalize()
            cells[1].text = f"{float(value):.2f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
        style_data_table(process_table, column_weights=[1.4, 1.0])
    else:
        doc.add_paragraph("No se informaron ajustes de proceso.")

    _heading(doc, "Filtros aplicados", 2)
    doc.add_paragraph("Filtros aplicados → " + _format_filters(data.filters) + ".")

    _heading(doc, "Datos de origen", 2)
    files_table = doc.add_table(rows=1, cols=2)
    files_table.rows[0].cells[0].text = "Campo"
    files_table.rows[0].cells[1].text = "Valor"
    for key, label in _META_LABELS:
        value = _text(data.meta, key)
        if not value:
            continue
        cells = files_table.add_row().cells
        cells[0].text = label
        cells[1].text = value
    if len(files_table.rows) > 1:
        style_data_table(files_table, column_weights=[1.0, 2.0])
    else:
        files_table._element.getparent().remove(files_table._element)
        doc.add_paragraph("No se informaron nombres de archivos ni metadatos de origen.")


def _add_parameter_compliance(doc, data: ReportData) -> None:
    _heading(doc, "3. Resultados por parámetro", 1)
    parameters = list(data.parameters or ())
    if not parameters:
        doc.add_paragraph("Sin resultados por parámetro en el modelo.")
        return

    table = doc.add_table(rows=1, cols=6)
    headers = (
        "Parámetro",
        "Registros contabilizados",
        "CUMPLE",
        "Otro estado*",
        "% CUMPLE",
        "Media real (n con estado)",
    )
    for idx, header in enumerate(headers):
        table.rows[0].cells[idx].text = header
    for parameter in parameters:
        accounted = parameter.cumple + parameter.no_cumple
        cells = table.add_row().cells
        cells[0].text = f"{parameter.label} ({parameter.unit})"
        cells[1].text = str(accounted) if accounted else EMPTY
        cells[2].text = str(parameter.cumple) if accounted else EMPTY
        cells[3].text = str(parameter.no_cumple) if accounted else EMPTY
        cells[4].text = _fmt_pct(parameter.pct_cumple)
        decimals = 1 if parameter.parameter == "angle" else 2
        mean = _fmt(parameter.mean_real, decimals)
        status_key = f"{parameter.parameter}_status"
        real_key = f"{parameter.parameter}_real"
        real_count = sum(
            1 for row in data.rows
            if getattr(row, status_key)
            and getattr(row, status_key) != "-"
            and getattr(row, real_key) is not None
        )
        cells[5].text = (
            EMPTY if mean == EMPTY else f"{mean} {parameter.unit} (n={real_count})"
        )
    style_data_table(table, column_weights=[1.1, 1.0, 0.55, 0.65, 0.7, 1.2])
    doc.add_paragraph(
        "* El modelo suma aquí los registros con estado distinto de CUMPLE, "
        "incluidos FUERA DE TOLERANCIA y NO CUMPLE; su conteo puede incluir "
        "filas de bancos no construidos. El porcentaje usa los registros "
        "contabilizados en esta tabla, no una estimación de mediciones válidas. "
        "La media usa los valores reales disponibles.",
        style="Caption",
    )

    donut_payload = [
        {"label": p.label, "cumple": p.cumple, "no_cumple": p.no_cumple}
        for p in parameters if p.cumple + p.no_cumple > 0
    ]
    try:
        blob = report_charts.parameter_donuts_png(donut_payload)
    except Exception:
        blob = None
    if blob:
        _heading(doc, "Distribución de estados contabilizados", 2)
        doc.add_paragraph(
            "El segmento «No cumple» del gráfico agrupa todos los estados "
            "contabilizados distintos de CUMPLE, como se explica en la nota de la tabla.",
            style="Caption",
        )
        _image_paragraph(doc, blob, Mm(220), Mm(90))
    else:
        doc.add_paragraph("No hay registros contabilizados para graficar por parámetro.")


def _add_design_achievement(doc, data: ReportData) -> None:
    _heading(doc, "4. Logro de diseño por sector", 1)
    achievement = data.design_achievement
    sectors = (achievement or {}).get("sectors") or []
    if not achievement or not sectors:
        doc.add_paragraph(
            "Sin datos suficientes de logro de diseño (se requiere evidencia de "
            "al menos una desviación de cresta o pie, o un estado de berma disponible)."
        )
        return

    table = doc.add_table(rows=1, cols=5)
    headers = ("Sector", "Puntaje (0-100)", "% Cresta-pie", "% Pie", "% Berma")
    for idx, header in enumerate(headers):
        table.rows[0].cells[idx].text = header

    global_row = achievement.get("global") or {}
    ordered = [dict(sector, sector=sector.get("sector") or "(sin sector)") for sector in sectors]
    for sector in [dict(global_row, sector="Global")] + ordered:
        cells = table.add_row().cells
        cells[0].text = str(sector.get("sector", ""))
        cells[1].text = EMPTY if sector.get("global_score") is None else f"{sector['global_score']}"
        cells[2].text = _fmt_pct(sector.get("crest_pct"))
        cells[3].text = _fmt_pct(sector.get("toe_pct"))
        cells[4].text = _fmt_pct(sector.get("berm_pct"))
    style_data_table(table, column_weights=[1.4, 1.0, 1.0, 0.9, 0.9])

    doc.add_paragraph(
        "El puntaje de logro de diseño pondera las desviaciones de cresta y pie "
        "respecto de la tolerancia declarada; los porcentajes indican la fracción "
        "de bancos dentro de tolerancia para cada métrica."
    )


def _add_priority_deviations(doc, data: ReportData) -> None:
    _heading(doc, "5. Mayores desviaciones comparables", 1, page_break=True)
    deviations = [entry for entry in data.top_deviations if isinstance(entry, Mapping)]
    if not deviations:
        doc.add_paragraph(
            "No hay desviaciones comparables calculadas con las tolerancias y valores disponibles."
        )
        return

    parameters = {
        "height": ("Altura de banco", "m", 2),
        "angle": ("Ángulo de cara", "°", 1),
        "berm": ("Ancho de berma", "m", 2),
    }
    doc.add_paragraph(
        "Se muestran hasta cinco registros por parámetro, en el orden calculado "
        "por el modelo. Este orden relativo no cambia el estado del banco. En "
        "altura y ángulo se compara la desviación con el límite aplicable; para "
        "bermas con criterio mínimo se ordena el déficit respecto del mínimo."
    )
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for entry in deviations:
        grouped.setdefault(str(entry.get("parameter") or ""), []).append(entry)
    order = ("height", "angle", "berm")
    for parameter in order + tuple(sorted(key for key in grouped if key not in order)):
        entries = grouped.get(parameter)
        if not entries:
            continue
        label, unit, decimals = parameters.get(parameter, (parameter or "Parámetro", "", 2))
        shown = entries[:5]
        _heading(doc, f"{label} — {len(shown)} de {len(entries)} registros", 2)
        table = doc.add_table(rows=1, cols=9)
        headers = (
            "Perfil", "Sector", "Nivel", "Banco", f"Diseño ({unit})",
            f"Real ({unit})", f"Diferencia ({unit})", "Criterio", "Estado",
        )
        for index, header in enumerate(headers):
            table.rows[0].cells[index].text = header
        for entry in shown:
            cells = table.add_row().cells
            bench = entry.get("bench_num")
            cells[0].text = str(entry.get("section") or EMPTY)
            cells[1].text = str(entry.get("sector") or EMPTY)
            cells[2].text = str(entry.get("level") or EMPTY)
            cells[3].text = EMPTY if bench is None else str(bench)
            cells[4].text = _fmt(entry.get("design"), decimals)
            cells[5].text = _fmt(entry.get("real"), decimals)
            cells[6].text = _fmt_signed(entry.get("deviation"), decimals)
            cells[7].text = str(entry.get("tolerance_text") or EMPTY)
            cells[8].text = _status_label(parse_bench_status(entry.get("status")))
        style_data_table(table, column_weights=[1.0, 0.8, 0.7, 0.6, 0.8, 0.8, 0.9, 1.1, 1.0])


def _plan_section_items(data: ReportData) -> list:
    plan_inputs = data.plan_inputs
    if not plan_inputs:
        return []
    raw = plan_inputs.get("sections") if isinstance(plan_inputs, Mapping) else plan_inputs
    return list(raw or [])


def _section_as_dict(item: Any) -> Optional[dict]:
    if isinstance(item, Mapping):
        return dict(item)
    name = _attribute(item, "name")
    if name is None:
        return None
    origin = _attribute(item, "origin")
    section = {
        "name": name,
        "sector": _attribute(item, "sector"),
        "azimuth": _attribute(item, "azimuth"),
        "length": _attribute(item, "length"),
    }
    if origin is not None:
        section["origin"] = [float(origin[0]), float(origin[1])]
    return section


def _plan_sections(data: ReportData) -> list:
    sections = []
    for item in _plan_section_items(data):
        section = _section_as_dict(item)
        if not section:
            continue
        name = str(section.get("name") or section.get("section_name") or "")
        if not name:
            continue
        section["name"] = name
        sections.append(section)

    name_counts = {}
    for section in sections:
        name_counts[section["name"]] = name_counts.get(section["name"], 0) + 1
    for section in sections:
        name = section["name"]
        state = data.resolve_section_plan_state(
            name,
            section.get("sector"),
            infer_missing_sector=name_counts[name] == 1,
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


def _plan_contours(data: ReportData):
    plan_inputs = data.plan_inputs
    if not isinstance(plan_inputs, Mapping):
        return None
    contours = plan_inputs.get("contours")
    if contours:
        return contours
    mesh = plan_inputs.get("mesh_topo")
    vertices = _attribute(mesh, "vertices") if mesh is not None else None
    if vertices is None:
        return None
    try:
        import numpy as np

        points = np.asarray(vertices)
        if points.ndim != 2 or points.shape[0] < 4 or points.shape[1] < 3:
            return None
        step = max(1, points.shape[0] // 30000)
        points = points[::step]
        return {
            "x": points[:, 0].tolist(),
            "y": points[:, 1].tolist(),
            "z": points[:, 2].tolist(),
            "interval": 5.0,
            "grid_ref": float(plan_inputs.get("grid_ref") or 0.0),
        }
    except Exception:
        return None


def _add_plan(doc, data: ReportData) -> None:
    _heading(doc, "6. Plano de cumplimiento", 1, page_break=True)
    sections = _plan_sections(data)
    blob = None
    if sections:
        try:
            blob = report_charts.plan_view_png(sections, contours=_plan_contours(data))
        except Exception:
            blob = None
    if not blob:
        doc.add_paragraph(
            "Sin geometría de secciones disponible para generar el plano de cumplimiento."
        )
        return
    doc.add_paragraph(
        "Plano en planta: cada perfil se colorea según el estado de su peor banco; "
        "la leyenda indica cuántos perfiles hay en cada estado."
    )
    _image_paragraph(doc, blob, Mm(235), Mm(150))


def _add_profile_table(doc, data: ReportData) -> None:
    _heading(doc, "7. Detalle por banco", 1, page_break=True)
    rows = sorted(
        data.rows or (),
        key=lambda r: (r.section, -1 if r.bench_num is None else r.bench_num, r.level),
    )
    if not rows:
        doc.add_paragraph("No hay bancos para tabular.")
        return

    values = {
        column[0]: [column[3](row) for row in rows] for column in _PROFILE_COLUMNS
    }
    kept = [
        column
        for column in _PROFILE_COLUMNS
        if any(not _is_empty_value(value) for value in values[column[0]])
    ]
    if not kept:
        doc.add_paragraph("No hay datos de bancos para tabular.")
        return

    dropped = [column[1] for column in _PROFILE_COLUMNS if column not in kept]
    if dropped:
        doc.add_paragraph(
            "Columnas sin datos en esta sesión y omitidas: " + ", ".join(dropped) + "."
        )

    table = doc.add_table(rows=1, cols=len(kept))
    for idx, column in enumerate(kept):
        table.rows[0].cells[idx].text = column[1]
    for row in rows:
        cells = table.add_row().cells
        for idx, column in enumerate(kept):
            cell = cells[idx]
            cell.text = column[3](row)
            if column[4] == "status":
                _set_cell_fill(cell, STATUS_FILL.get(row.worst_status, STATUS_FILL["UNKNOWN"]))
                color = RGBColor.from_string(STATUS_TEXT.get(row.worst_status, STATUS_TEXT["UNKNOWN"]))
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.bold = True
                        run.font.color.rgb = color
    style_data_table(table, column_weights=[column[2] for column in kept])

    doc.add_paragraph(
        "El estado por banco combina altura, ángulo y berma con la misma "
        "severidad del tablero web; los bancos sin medición no se evalúan."
    )


def _series(value: Any):
    if not value:
        return None
    try:
        distances, elevations = value[0], value[1]
    except Exception:
        return None
    if distances is None or elevations is None or len(distances) == 0 or len(elevations) == 0:
        return None
    try:
        return [float(x) for x in distances], [float(z) for z in elevations]
    except (TypeError, ValueError):
        return None


def _attribute(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _geometry_for(data: ReportData, section: str):
    for item in data.section_geometry or ():
        name = _attribute(item, "section_name") or _attribute(item, "name")
        if name is not None and str(name) == str(section):
            return item
    return None


def _tolerance_band(tolerances: Mapping[str, Any]) -> Optional[dict]:
    height = tolerances.get("bench_height") if isinstance(tolerances, Mapping) else None
    if not isinstance(height, Mapping):
        return None
    crest = height.get("pos")
    toe = height.get("neg")
    band = {}
    if crest is not None:
        band["crest"] = abs(float(crest))
    if toe is not None:
        band["toe"] = abs(float(toe))
    return band or None


def _normalise_holes(holes: Any) -> Optional[list]:
    if not holes:
        return None
    out = []
    for hole in holes:
        if not isinstance(hole, Mapping):
            continue
        dist = hole.get("dist", hole.get("dist_along", hole.get("x")))
        collar = hole.get("collar_z", hole.get("Z_collar"))
        toe = hole.get("toe_z", hole.get("Z_toe"))
        toe_dist = hole.get("toe_dist", hole.get("dist_toe"))
        if dist is None or collar is None:
            continue
        out.append(
            {
                "dist": float(dist),
                "collar_z": float(collar),
                "toe_z": None if toe is None else float(toe),
                "toe_dist": None if toe_dist is None else float(toe_dist),
            }
        )
    return out or None


def _blast_tolerance_value(blast: Mapping[str, Any]) -> float:
    tolerance = blast.get("tolerance")
    if isinstance(tolerance, Mapping):
        for key in ("pos", "neg", "min"):
            if tolerance.get(key) is not None:
                return abs(float(tolerance[key]))
        return 10.0
    if tolerance is None:
        return 10.0
    try:
        return abs(float(tolerance))
    except (TypeError, ValueError):
        return 10.0


def _project_holes(data: ReportData, section: str) -> Optional[list]:
    holes = data.blast.get("holes") if isinstance(data.blast, Mapping) else None
    if not holes:
        return None
    section_item = next(
        (
            item
            for item in _plan_section_items(data)
            if str(_attribute(item, "name") or _attribute(item, "section_name")) == str(section)
        ),
        None,
    )
    if section_item is None:
        return None
    origin = _attribute(section_item, "origin")
    azimuth = _attribute(section_item, "azimuth")
    length = _attribute(section_item, "length")
    if origin is None or azimuth is None or length is None:
        return None
    try:
        import numpy as np
        import pandas as pd

        from core.calculo_tronadura import proyectar_pozos_en_seccion

        frame = pd.DataFrame([dict(h) for h in holes if isinstance(h, Mapping)])
        if not {"X", "Y"}.issubset(frame.columns):
            return None
        projected = proyectar_pozos_en_seccion(
            frame,
            np.asarray([float(origin[0]), float(origin[1])]),
            float(azimuth),
            float(length),
            tolerance=_blast_tolerance_value(data.blast),
        )
        out = []
        for row in projected.itertuples(index=False):
            distance = getattr(row, "dist_along", None)
            collar = getattr(row, "Z_collar", None)
            toe = getattr(row, "Z_toe", None)
            toe_distance = getattr(row, "dist_along_toe", None)
            if distance is None or collar is None or pd.isna(distance) or pd.isna(collar):
                continue
            out.append(
                {
                    "dist": float(distance),
                    "collar_z": float(collar),
                    "toe_z": None if toe is None or pd.isna(toe) else float(toe),
                    "toe_dist": float(distance if toe_distance is None or pd.isna(toe_distance) else toe_distance),
                }
            )
        return out or None
    except Exception:
        return None


def _blast_holes_for(data: ReportData, section: str) -> Optional[list]:
    blast = data.blast
    if not isinstance(blast, Mapping):
        return None
    by_section = blast.get("holes_by_section")
    if isinstance(by_section, Mapping):
        return _normalise_holes(by_section.get(section))
    return _project_holes(data, section)


def _ambiguous_profile_sections(data: ReportData) -> set[str]:
    sectors_by_section: dict[str, set[str]] = {}
    for row in data.rows:
        if row.section:
            sectors_by_section.setdefault(row.section, set()).add(row.sector or "")
    return {section for section, sectors in sectors_by_section.items() if len(sectors) > 1}


def _profile_payload(data: ReportData, profile: ProfileSummary) -> Optional[dict]:
    item = _geometry_for(data, profile.section)
    if item is None:
        return None
    tolerance_band = _tolerance_band(data.tolerances or {})
    blast_holes = _blast_holes_for(data, profile.section)

    if isinstance(item, Mapping) and any(k in item for k in ("design", "topo", "benches")):
        payload = dict(item)
        payload.setdefault("name", profile.section)
        if profile.section not in _ambiguous_profile_sections(data):
            payload.setdefault("sector", profile.sector)
        else:
            payload.pop("sector", None)
        payload.setdefault("status_label", _status_label(profile.worst_status))
        if tolerance_band:
            payload.setdefault("tolerance_band", tolerance_band)
        if blast_holes and not payload.get("blast_holes"):
            payload["blast_holes"] = blast_holes
        return payload

    rows = [r for r in data.rows if r.section == profile.section]
    by_bench = {
        int(r.bench_num): r
        for r in rows
        if r.bench_num is not None and r.type == "MATCH"
    }
    benches = []
    params_design = _attribute(item, "params_design")
    source_benches = _attribute(params_design, "benches") if params_design is not None else None
    for bench in source_benches or ():
        number = _attribute(bench, "bench_number")
        row = by_bench.get(int(number)) if number is not None else None
        deviation = _fmt_signed(None if row is None else row.height_dev, 2)
        benches.append(
            {
                "label": f"B{int(number)}" if number is not None else "B?",
                "crest_dist": _attribute(bench, "crest_distance"),
                "crest_z": _attribute(bench, "crest_elevation"),
                "toe_dist": _attribute(bench, "toe_distance"),
                "toe_z": _attribute(bench, "toe_elevation"),
                "deviation_text": "" if deviation == EMPTY else f"{deviation} m",
                "status": None if row is None else row.worst_status,
            }
        )

    payload = {
        "name": profile.section,
        "status_label": _status_label(profile.worst_status),
        "design": _series(_attribute(item, "profile_d")),
        "topo": _series(_attribute(item, "profile_t")),
        "benches": benches,
    }
    if profile.section not in _ambiguous_profile_sections(data) and profile.sector:
        payload["sector"] = profile.sector
    if tolerance_band:
        payload["tolerance_band"] = tolerance_band
    if blast_holes:
        payload["blast_holes"] = blast_holes
    return payload


def _profile_image(data: ReportData, profile: ProfileSummary, size: str) -> Optional[bytes]:
    payload = _profile_payload(data, profile)
    if payload is None:
        return None
    try:
        return report_charts.section_profile_png(payload, size=size, dpi=PROFILE_DPI)
    except Exception:
        return None


def _render_profile_grid(doc, data, profiles, size, per_page, max_width, max_height) -> None:
    chunks = [profiles[i:i + per_page] for i in range(0, len(profiles), per_page)]
    for chunk_idx, chunk in enumerate(chunks):
        if chunk_idx:
            doc.add_page_break()
        n_rows = (len(chunk) + DETAIL_COLUMNS - 1) // DETAIL_COLUMNS
        table = _borderless_table(doc, n_rows, DETAIL_COLUMNS)
        for row in table.rows:
            for cell in row.cells:
                cell.width = Mm(DETAIL_COLUMN_MM)
        for idx, profile in enumerate(chunk):
            cell = table.rows[idx // DETAIL_COLUMNS].cells[idx % DETAIL_COLUMNS]
            paragraph = cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            blob = _profile_image(data, profile, size)
            if blob:
                _add_picture_bounded(paragraph, blob, max_width, max_height)
            else:
                paragraph.add_run(
                    f"Sección {profile.section}: sin geometría de sección disponible."
                )


def _add_section_details(doc, data: ReportData) -> None:
    _heading(doc, "8. Detalle por sección", 1, page_break=True)
    profiles = list(data.profiles or ())
    if not profiles:
        doc.add_paragraph("No hay perfiles para detallar.")
        return

    non_compliant = [p for p in profiles if p.worst_status in NON_COMPLIANT]
    compliant = [p for p in profiles if p.worst_status == "CUMPLE"]
    unresolved = [p for p in profiles if p.worst_status not in (*NON_COMPLIANT, "CUMPLE")]

    sectors_by_section: dict[str, set[str]] = {}
    for row in data.rows:
        if row.section and row.sector:
            sectors_by_section.setdefault(row.section, set()).add(row.sector)
    ambiguous = sorted(section for section, sectors in sectors_by_section.items() if len(sectors) > 1)
    if ambiguous:
        doc.add_paragraph(
            "Identidad de sector no resuelta para secciones con nombre repetido: "
            + ", ".join(ambiguous)
            + ". El modelo de perfiles agrupa por nombre de sección; estos detalles "
            "no permiten atribuir un sector inequívoco."
        )

    if non_compliant and not compliant and not unresolved:
        doc.add_paragraph(
            "Todos los perfiles presentan estado no conforme; para mantener un "
            "tamaño de documento razonable se muestran dos perfiles por página "
            "en paralelo en lugar de uno por página."
        )
        _render_profile_grid(
            doc, data, non_compliant, "full", 2,
            Mm(DETAIL_COLUMN_MM), Mm(DETAIL_IMAGE_HEIGHT_MM),
        )
        return

    if non_compliant:
        doc.add_paragraph(
            f"Perfiles no conformes ({len(non_compliant)}): se presentan dos por "
            "página, en paralelo, con el detalle completo de cada sección."
        )
        _render_profile_grid(
            doc, data, non_compliant, "full", 2,
            Mm(DETAIL_COLUMN_MM), Mm(DETAIL_IMAGE_HEIGHT_MM),
        )
    else:
        doc.add_paragraph("No hay perfiles no conformes en esta sesión.")

    if compliant:
        doc.add_page_break()
        _heading(doc, "Anexo: perfiles conformes", 2)
        doc.add_paragraph(
            f"Perfiles conformes ({len(compliant)}): se presentan dos por página en "
            "formato compacto."
        )
        _render_profile_grid(
            doc, data, compliant, "compact", 2,
            Mm(DETAIL_COLUMN_MM), Mm(DETAIL_ANNEX_HEIGHT_MM),
        )

    if unresolved:
        doc.add_page_break()
        _heading(doc, "Perfiles sin estado concluyente", 2)
        doc.add_paragraph(
            f"Perfiles con estado UNKNOWN u otro estado no clasificado ({len(unresolved)}): "
            "se muestran por separado, sin contarlos como conformes ni no conformes."
        )
        _render_profile_grid(
            doc, data, unresolved, "compact", 2,
            Mm(DETAIL_COLUMN_MM), Mm(DETAIL_ANNEX_HEIGHT_MM),
        )


def _blast_frame_rows(holes) -> list:
    rows = []
    for hole in holes:
        if not isinstance(hole, Mapping):
            continue
        row = dict(hole)
        for canonical, alternates in (
            ("Z_collar", ("collar_z", "z_collar", "collar")),
            ("Z_toe", ("toe_z", "z_toe", "toe")),
        ):
            if canonical not in row:
                for alternate in alternates:
                    if alternate in row:
                        row[canonical] = row[alternate]
                        break
        rows.append(row)
    return rows


def _add_blast(doc, data: ReportData) -> None:
    if isinstance(data.blast, Mapping) and data.blast.get("holes"):
        doc.add_page_break()
    _heading(doc, "9. Análisis de perforación y tronadura", 1)
    blast = data.blast
    if not isinstance(blast, Mapping):
        doc.add_paragraph("Sin datos de pozos de tronadura en esta sesión.")
        return

    holes = blast.get("holes")
    if not holes:
        doc.add_paragraph(
            "La sesión declara configuración de tronadura pero no pozos registrados."
        )
        return

    if any(
        isinstance(hole, Mapping)
        and hole.get("Z_collar_semantic", hole.get("z_collar_semantic")) == "design_surface_estimate"
        for hole in holes
    ):
        doc.add_paragraph(
            "Advertencia: la cota Z del collar de algunos pozos fue estimada desde la superficie de diseño; "
            "no es una medición de terreno y no debe interpretarse como cota real levantada."
        )

    stats = None
    try:
        import pandas as pd

        from core.blast_correlation import compute_pasadura_stats

        stats = compute_pasadura_stats(pd.DataFrame(_blast_frame_rows(holes)))
    except Exception:
        stats = None

    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Métrica"
    table.rows[0].cells[1].text = "Valor"
    total = len(holes)
    rows = [("Total de pozos registrados", str(total))]
    blocked = not stats or stats.get("bench_height_status") in ("MISSING", "INVALID")
    if blocked:
        rows.append(("Altura de banco", "No confirmada: pasadura bloqueada (sin supuesto automático)"))
        rows.append(("Pasadura promedio (sub-drilling)", "No disponible sin altura de banco"))
    else:
        mean = stats["mean"]
        mean_text = f"{mean:.2f} m" if isinstance(mean, float) and math.isfinite(mean) else "No disponible"
        rows.append(("Pasadura promedio (sub-drilling)", mean_text))
        rows.append(
            (
                "Pozos en pasadura óptima (0,5 a 1,5 m)",
                f"{stats['optimal_pct']:.1f}% ({stats['optimal_count']} pozos)",
            )
        )
    tolerance = blast.get("tolerance")
    if isinstance(tolerance, Mapping):
        neg = tolerance.get("neg")
        pos = tolerance.get("pos")
        if neg is not None or pos is not None:
            neg_text = f"−{abs(float(neg)):.2f}" if neg is not None else "sin límite"
            pos_text = f"+{abs(float(pos)):.2f}" if pos is not None else "sin límite"
            rows.append(("Tolerancia cresta-pie aplicada", f"{neg_text} / {pos_text} m"))
    elif tolerance is not None:
        rows.append(
            ("Tolerancia de proyección de pozos", f"±{_blast_tolerance_value(blast):.2f} m")
        )
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
    style_data_table(table, column_weights=[1.8, 1.2])

    doc.add_paragraph(
        "Los pozos se superponen en los perfiles de sección cuando la sesión "
        "proporciona su proyección por sección."
    )


def build_word_report(data: ReportData) -> io.BytesIO:
    """Render the web Word report for ``data`` and return it as a ``BytesIO``.

    The buffer is positioned at the start so callers can stream it directly.
    Every section degrades to a one-line note when its input is missing.
    """
    doc = Document()
    configure_document(doc, data.meta)
    _enable_field_updates(doc)

    _add_cover(doc, data.meta or {}, data)
    _add_toc(doc)
    _add_executive_summary(doc, data)
    _add_criteria(doc, data)
    _add_parameter_compliance(doc, data)
    _add_design_achievement(doc, data)
    _add_priority_deviations(doc, data)
    _add_plan(doc, data)
    _add_profile_table(doc, data)
    _add_section_details(doc, data)
    _add_blast(doc, data)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
