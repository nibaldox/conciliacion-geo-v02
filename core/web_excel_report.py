"""Analytical Excel workbook for the web export (contract C9, stage E5).

Consumes only the frozen ``ReportData`` model: no API, no database. Missing
values stay as empty cells and are never written as zero.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.marker import DataPoint
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from core.blast_correlation import PF_DEFINITIONS
from core.report_charts import STATUS_COLORS, STATUS_LABELS_ES
from core.report_data import ReportData
from core.report_texts import kpi_definitions, scope_lines

SHEET_README = "Léeme"
SHEET_SUMMARY = "Resumen"
SHEET_BENCHES = "Bancos"
SHEET_SECTIONS = "Secciones"
SHEET_SECTOR_LEVEL = "Sector-Nivel"
SHEET_BLAST = "Tronadura"
SHEET_HOLES = "Pozos"

MISSING_TEXT = "—"
NO_DATA_TEXT = "sin dato"
REIMPORT_WARNING = "Datos de pozos importados con una versión anterior: reimportar"
PF_MAIN_DEFINITION = "1000*Q/(A*H*rho), área de Voronoi por huella y altura de banco"
BLAST_SCOPE_NOTE = (
    "Incluye todos los pozos de tronadura del informe; los filtros de sector, sección y "
    "cota de la conciliación no se aplican a los pozos."
)
NO_GEOMETRY_NOTE = (
    "Sin geometría de secciones: este libro no incluye áreas ni volúmenes de excavación."
)

FMT_INT = "0"
FMT_M = "0.00"
FMT_DEG = "0.0"
FMT_SCORE = "0.0"
FMT_AREA = "#,##0.0"
FMT_VOLUME = "#,##0"
FMT_PCT = "0.0%"
FMT_PF = "0.0"
FMT_PF_VOL = "0.000"

_STATUS_ORDER = ("CUMPLE", "FUERA", "NO_CUMPLE", "UNKNOWN")
_PROFILE_STATUS_TEXT = {
    "CUMPLE": "CUMPLE",
    "FUERA": "FUERA DE TOLERANCIA",
    "NO_CUMPLE": "NO CUMPLE",
    "UNKNOWN": "SIN EVALUAR",
}
_STATUS_FILL_TEXTS = (
    ("CUMPLE", "CUMPLE"),
    ("FUERA DE TOLERANCIA", "FUERA"),
    ("NO CUMPLE", "NO_CUMPLE"),
    ("NO CONSTRUIDO", "NO_CUMPLE"),
    ("FALTA BANCO", "NO_CUMPLE"),
    ("BANCO ADICIONAL", "NO_CUMPLE"),
    ("SIN EVALUAR", "UNKNOWN"),
)
_TYPE_LABELS = {"MATCH": "Comparado", "MISSING": "No construido", "EXTRA": "Adicional"}
_EXTRA_BENCH_SENTINEL = 999
_PARAMETERS = (
    ("height", "altura", "m", FMT_M),
    ("angle", "ángulo", "°", FMT_DEG),
    ("berm", "berma", "m", FMT_M),
)
_TOLERANCE_LABELS = (
    ("bench_height", "Altura de banco", "m"),
    ("face_angle", "Ángulo de cara", "°"),
    ("berm_width", "Ancho de berma", "m"),
    ("inter_ramp_angle", "Ángulo interrampa", "°"),
    ("overall_angle", "Ángulo global", "°"),
    ("crest_toe_deviation", "Desviación de cresta y pata", "m"),
)
_META_LABELS = (
    ("project", "Proyecto"),
    ("operation", "Operación"),
    ("phase", "Fase"),
    ("author", "Autor"),
    ("design_filename", "Superficie de diseño"),
    ("topo_filename", "Superficie topográfica"),
)

_TITLE_FONT = Font(bold=True, size=14)
_HEADING_FONT = Font(bold=True, size=11, color="FFFFFF")
_HEADING_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(start_color="DDE6F0", end_color="DDE6F0", fill_type="solid")
_WRAP_TOP = Alignment(wrap_text=True, vertical="top")
_CHART_NEUTRAL = "1F4E79"


@dataclass(frozen=True)
class _Column:
    key: str
    header: str
    number_format: Optional[str] = None
    status: bool = False
    required: bool = False


def _hex(status: str) -> str:
    return STATUS_COLORS[status].lstrip("#").upper()


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _number_or_text(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    number = _finite(text)
    if number is None:
        return text
    return int(number) if number == int(number) else number


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _es(value: Any, decimals: int = 1) -> str:
    number = _finite(value)
    if number is None:
        return MISSING_TEXT
    return f"{number:.{decimals}f}".replace(".", ",")


def _sector_label(sector: Any) -> str:
    text = "" if sector is None else str(sector).strip()
    return text or "(sin sector)"


def _status_text(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text or text == "-":
        return None
    return {"FUERA": "FUERA DE TOLERANCIA", "EXTRA": "BANCO ADICIONAL", "MISSING": "NO CONSTRUIDO", "NO_CUMPLE": "NO CUMPLE"}.get(text, text)


def _mean(values: Sequence[float]) -> Optional[float]:
    return math.fsum(values) / len(values) if values else None


def _fraction(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def _pct_fraction(pct: Optional[float]) -> Optional[float]:
    number = _finite(pct)
    return None if number is None else number / 100.0


def _fit_widths(ws: Worksheet, widths: Mapping[int, int]) -> None:
    for index, width in widths.items():
        ws.column_dimensions[get_column_letter(index)].width = width


def _display_length(value: Any, number_format: Optional[str]) -> int:
    if value is None:
        return 0
    if isinstance(value, float):
        if number_format == FMT_PCT:
            return len(f"{value * 100:.1f}%")
        decimals = len(number_format.split(".")[1]) if number_format and "." in number_format else 0
        return len(f"{value:,.{decimals}f}")
    return max(len(line) for line in str(value).split("\n"))


def _write_table(
    ws: Worksheet,
    columns: Sequence[_Column],
    records: Sequence[Mapping[str, Any]],
    *,
    table_name: str,
    start_row: int = 1,
    missing_text: Optional[str] = None,
) -> list[_Column]:
    """Write records as an Excel table, dropping the columns empty in every row.

    Required columns are always kept. With ``missing_text`` the empty cells of
    the kept columns carry that text instead of staying blank.
    """
    kept = [
        column
        for column in columns
        if column.required
        or any(not _is_empty(record.get(column.key)) for record in records)
    ]
    if not records or not kept:
        ws.cell(row=start_row, column=1, value="Sin datos para el alcance del informe.")
        ws.column_dimensions["A"].width = 44
        return []

    widths: dict[int, int] = {}
    for index, column in enumerate(kept, start=1):
        cell = ws.cell(row=start_row, column=index, value=column.header)
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        widths[index] = len(column.header) + 4
    for offset, record in enumerate(records, start=1):
        for index, column in enumerate(kept, start=1):
            value = record.get(column.key)
            if _is_empty(value):
                if missing_text is None:
                    continue
                value = missing_text
            cell = ws.cell(row=start_row + offset, column=index, value=value)
            if column.number_format and not isinstance(value, str):
                cell.number_format = column.number_format
            widths[index] = max(widths[index], _display_length(value, column.number_format) + 2)

    last_row = start_row + len(records)
    last_letter = get_column_letter(len(kept))
    table = Table(displayName=table_name, ref=f"A{start_row}:{last_letter}{last_row}")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False
    )
    ws.add_table(table)
    ws.freeze_panes = f"A{start_row + 1}"

    for index, column in enumerate(kept, start=1):
        if not column.status:
            continue
        letter = get_column_letter(index)
        cell_range = f"{letter}{start_row + 1}:{letter}{last_row}"
        for text, status in _STATUS_FILL_TEXTS:
            color = _hex(status)
            ws.conditional_formatting.add(
                cell_range,
                CellIsRule(
                    operator="equal",
                    formula=[f'"{text}"'],
                    fill=PatternFill(start_color=color, end_color=color, fill_type="solid"),
                    font=Font(color="FFFFFF", bold=True),
                ),
            )
    _fit_widths(ws, {index: min(max(width, 8), 60) for index, width in widths.items()})
    return kept


def _heading(ws: Worksheet, row: int, text: str, span: int = 2) -> int:
    for column in range(1, span + 1):
        cell = ws.cell(row=row, column=column)
        cell.fill = _HEADING_FILL
        cell.font = _HEADING_FONT
    ws.cell(row=row, column=1, value=text)
    return row + 1


def _header_row(ws: Worksheet, row: int, headers: Sequence[str]) -> int:
    for index, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=index, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    return row + 1


def _kpi(ws: Worksheet, row: int, label: str, value: Any, number_format: Optional[str] = None) -> int:
    ws.cell(row=row, column=1, value=label)
    cell = ws.cell(row=row, column=2, value=MISSING_TEXT if _is_empty(value) else value)
    if number_format and not _is_empty(value):
        cell.number_format = number_format
    if _is_empty(value):
        cell.alignment = Alignment(horizontal="right")
    return row + 1


def _tolerance_text(tolerance: Any, unit: str) -> Optional[str]:
    if not isinstance(tolerance, Mapping):
        return None
    decimals = 1 if unit == "°" else 2
    neg = _finite(tolerance.get("neg"))
    pos = _finite(tolerance.get("pos"))
    if neg is not None and pos is not None:
        if abs(abs(neg) - pos) < 1e-9:
            return f"± {_es(pos, decimals)} {unit}"
        return f"−{_es(abs(neg), decimals)} / +{_es(pos, decimals)} {unit}"
    minimum = _finite(tolerance.get("min"))
    if minimum is not None:
        return f"mínimo {_es(minimum, decimals)} {unit}"
    maximum = _finite(tolerance.get("max"))
    if maximum is not None:
        return f"máximo {_es(maximum, decimals)} {unit}"
    return None


def _excavation_sources(data: ReportData) -> tuple[list[str], list[str]]:
    sources = list(dict.fromkeys(entry.source for entry in data.excavation if entry.source))
    assumptions = list(
        dict.fromkeys(text for entry in data.excavation for text in entry.assumptions)
    )
    return sources, assumptions


def _blast_holes(data: ReportData) -> list[Mapping[str, Any]]:
    blast = data.blast
    if not isinstance(blast, Mapping):
        return []
    holes = blast.get("holes")
    if not isinstance(holes, (list, tuple)):
        return []
    return [hole for hole in holes if isinstance(hole, Mapping)]


def _achievement_details(data: ReportData) -> list[Mapping[str, Any]]:
    """Per-bench design-achievement details, aligned with ``data.rows``."""
    details = ((data.design_achievement or {}).get("global") or {}).get("rows") or []
    if len(details) != len(data.rows):
        return []
    return [detail if isinstance(detail, Mapping) else {} for detail in details]


def _missing_components_text(details: Sequence[Mapping[str, Any]]) -> str:
    tally: dict[str, int] = {}
    for detail in details:
        for component in detail.get("components_missing") or ():
            tally[str(component)] = tally.get(str(component), 0) + 1
    if not tally:
        return "Ninguno: ningún banco tiene componentes faltantes."
    parts = "; ".join(
        f"{component} en {count} {'banco' if count == 1 else 'bancos'}"
        for component, count in tally.items()
    )
    return (
        f"{parts}. El detalle por banco está en la columna «Componentes faltantes» "
        f"de la hoja {SHEET_BENCHES}."
    )


def _is_legacy_blast(data: ReportData) -> bool:
    return (
        isinstance(data.blast, Mapping)
        and data.blast.get("data_status") == "legacy_reimport_required"
    )


def _consolidation_text(data: ReportData) -> str:
    report = data.blast.get("consolidation_report") if isinstance(data.blast, Mapping) else None
    if not isinstance(report, Mapping) or not report:
        return f"{NO_DATA_TEXT}: la sesión no guarda un informe de consolidación de pozos."
    return (
        f"pozos {report.get('holes_out', NO_DATA_TEXT)}; "
        f"copias eliminadas {report.get('exact_copies_removed', NO_DATA_TEXT)}; "
        f"filas de decks fusionadas {report.get('deck_rows_merged', NO_DATA_TEXT)}"
    )


def _pf_status_text(holes: Sequence[Mapping[str, Any]]) -> str:
    tally: dict[str, int] = {}
    for hole in holes:
        status = _hole_text(hole.get("pf_voronoi_bench_status")) or NO_DATA_TEXT
        tally[status] = tally.get(status, 0) + 1
    ranked = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    return "; ".join(f"{status}: {count}" for status, count in ranked)


def _write_readme(
    ws: Worksheet, data: ReportData, holes: Sequence[Mapping[str, Any]] = ()
) -> None:
    has_blast = bool(holes)
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 120
    ws.cell(row=1, column=1, value="Conciliación geotécnica: diseño vs. as-built").font = _TITLE_FONT
    ws.cell(row=2, column=1, value="Libro analítico de la exportación web")
    row = 4

    def line(label: str, text: Any) -> None:
        nonlocal row
        ws.cell(row=row, column=1, value=label).alignment = _WRAP_TOP
        ws.cell(row=row, column=2, value=text).alignment = _WRAP_TOP
        row += 1

    def section(title: str) -> None:
        nonlocal row
        row = _heading(ws, row + 1, title)

    row = _heading(ws, row, "Proyecto")
    meta = data.meta or {}
    for key, label in _META_LABELS:
        value = meta.get(key)
        if not _is_empty(value):
            line(label, str(value))
    generated = meta.get("generated_at")
    if _is_empty(generated):
        generated = datetime.now().isoformat(timespec="seconds")
    try:
        generated = datetime.fromisoformat(str(generated)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass
    line("Fecha de generación", str(generated))

    section("Alcance y filtros aplicados")
    for text in scope_lines(data):
        line("Alcance", text)
    counts = data.counts or {}
    line(
        "Alcance resultante",
        f"{counts.get('n_sections', 0)} secciones y {counts.get('n_rows', 0)} bancos: "
        f"{counts.get('n_match', 0)} comparados, {counts.get('n_missing', 0)} no construidos "
        f"y {counts.get('n_extra', 0)} adicionales.",
    )
    if has_blast:
        line(SHEET_BLAST, BLAST_SCOPE_NOTE)

    section("Tolerancias")
    wrote_tolerance = False
    for key, label, unit in _TOLERANCE_LABELS:
        text = _tolerance_text((data.tolerances or {}).get(key), unit)
        if text:
            line(label, text)
            wrote_tolerance = True
    if not wrote_tolerance:
        line("Tolerancias", "La sesión no informa tolerancias.")
    line(
        "Estados por parámetro",
        "CUMPLE: dentro de la tolerancia. FUERA DE TOLERANCIA: hasta 1,5 veces la tolerancia. "
        "NO CUMPLE: sobre 1,5 veces la tolerancia.",
    )

    section("Definiciones de los indicadores")
    for name, text in kpi_definitions(data):
        line(name, text)
    line(
        "Tipo de banco",
        "Comparado: banco de diseño con su banco construido. No construido: "
        "banco de diseño sin banco construido, informado como NO CONSTRUIDO. Adicional: "
        "banco construido que no está en el diseño, informado como BANCO ADICIONAL y sin número "
        "de banco de diseño.",
    )
    line(
        "Desglose de NO CUMPLE",
        "«No cumple por geometría»: perfiles NO CUMPLE con al menos un banco comparado que no "
        "cumple. «No cumple solo por banco no construido o adicional»: perfiles NO CUMPLE cuyos "
        "bancos comparados cumplen todos. Denominador: perfiles NO CUMPLE.",
    )
    line(
        "Desviaciones",
        "Desviación = valor real − valor de diseño, en metros o grados. Las desviaciones medias "
        "consideran solo bancos comparados con ambos valores.",
    )
    line(
        "Desviación de cresta y pata",
        "Distancia horizontal a lo largo de la sección entre la cresta (o la pata) construida "
        "y la de diseño, real − diseño, en metros; solo en bancos comparados.",
    )
    line(
        "Diseño bajo el mínimo",
        "«Sí» cuando la berma de diseño es menor que la berma mínima exigida; es una advertencia "
        "y no cambia el estado oficial del banco.",
    )

    achievement = (data.design_achievement or {}).get("global") or {}
    coverage = achievement.get("coverage")
    if isinstance(coverage, Mapping) and data.rows:
        section("Logro de diseño: cobertura")
        weight = _finite(coverage.get("weight_available_mean"))
        line(
            "Cobertura",
            f"Bancos evaluables {coverage.get('n_evaluable', 0)} de {coverage.get('n_rows', 0)}; "
            f"completos {coverage.get('n_complete', 0)}; peso medio disponible "
            f"{NO_DATA_TEXT if weight is None else _es(weight, 2)}. El puntaje redistribuye "
            "los pesos disponibles; los bancos parciales no son completos.",
        )
        line("Componentes faltantes", _missing_components_text(_achievement_details(data)))

    if has_blast:
        section("Tronadura: auditoría de los pozos")
        if _is_legacy_blast(data):
            line("Advertencia", REIMPORT_WARNING)
        line(
            SHEET_HOLES,
            f"{len(holes)} pozos, una fila por pozo en la hoja {SHEET_HOLES}; "
            f"«{NO_DATA_TEXT}» marca un valor faltante, que nunca se reemplaza por 0.",
        )
        line("Estado FC principal", _pf_status_text(holes))
        line("FC principal (g/t)", PF_MAIN_DEFINITION)
        for name, definition in PF_DEFINITIONS.items():
            line(f"{name} ({definition['unit']})", definition["formula"])
        line("Consolidación", _consolidation_text(data))

    if data.nominal_levels:
        section("Cotas nominales de la sesión")
    for level in data.nominal_levels:
        name = f"Cota {level.label}"
        if str(level.sector).strip():
            name += f" · sector {level.sector}"
        line(
            name,
            f"Cotas de {_es(level.min_level, 1)} a {_es(level.max_level, 1)} m; "
            f"{level.n_sections} secciones y {level.n_rows} bancos (antes de filtrar).",
        )

    section("Excavación: fuente y supuestos")
    sources, assumptions = _excavation_sources(data)
    if data.excavation:
        line("Fuente del área", "Área entre los perfiles de diseño y topografía en cada sección.")
        for assumption in assumptions:
            line("Supuesto", assumption)
        totals = data.excavation_totals or {}
        if totals.get("n_without_volume"):
            line(
                "Secciones sin volumen",
                f"{totals['n_without_volume']} de {totals.get('n_sections', len(data.excavation))} "
                "secciones no tienen volumen (falta el área o el ancho de influencia); sus celdas "
                "quedan vacías y no suman en los totales.",
            )
    else:
        line("Áreas y volúmenes", NO_GEOMETRY_NOTE)

    section("Advertencias")
    line("Valores faltantes", "Una celda vacía significa «sin dato»; nunca se reemplaza por 0.")
    for warning in data.warnings:
        line("Advertencia", warning)

    section("Hojas del libro")
    line(SHEET_SUMMARY, "Indicadores numéricos y gráficos de perfiles por estado y de cumplimiento por parámetro.")
    line(SHEET_BENCHES, "Una fila por banco, con filtros; estados coloreados con la paleta de estados.")
    line(SHEET_SECTIONS, "Una fila por perfil: estado, puntaje, bancos, áreas y volúmenes.")
    line(SHEET_SECTOR_LEVEL, "Agregados por sector y cota nominal.")
    if has_blast:
        line(SHEET_BLAST, f"Resumen por malla de tronadura; el detalle está en la hoja {SHEET_HOLES}.")
        line(
            SHEET_HOLES,
            "Una fila por pozo: identificador literal, coordenadas, largo, carga, explosivo y "
            "factores de carga con su estado y fuente.",
        )


def _add_bar_chart(
    ws: Worksheet,
    *,
    title: str,
    header_row: int,
    last_row: int,
    value_column: int,
    anchor: str,
    colors: Sequence[str],
    percent: bool = False,
) -> None:
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = title
    chart.legend = None
    chart.height = 7.5
    chart.width = 14
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    if percent:
        chart.y_axis.scaling.min = 0
        chart.y_axis.scaling.max = 1
        chart.y_axis.number_format = "0%"
        chart.y_axis.majorUnit = 0.25
    values = Reference(ws, min_col=value_column, min_row=header_row, max_row=last_row)
    labels = Reference(ws, min_col=1, min_row=header_row + 1, max_row=last_row)
    chart.add_data(values, titles_from_data=True)
    chart.set_categories(labels)
    series = chart.series[0]
    series.graphicalProperties.solidFill = colors[0]
    if len(colors) > 1:
        for index, color in enumerate(colors):
            point = DataPoint(idx=index)
            point.graphicalProperties.solidFill = color
            series.dPt.append(point)
    ws.add_chart(chart, anchor)


def _write_summary(ws: Worksheet, data: ReportData) -> None:
    ws.cell(row=1, column=1, value="Resumen de la conciliación").font = _TITLE_FONT
    counts = data.counts or {}
    ws.cell(
        row=2,
        column=1,
        value=(
            f"{counts.get('n_sections', 0)} secciones · {counts.get('n_rows', 0)} bancos "
            f"({counts.get('n_match', 0)} comparados, {counts.get('n_missing', 0)} no construidos, "
            f"{counts.get('n_extra', 0)} adicionales)"
        ),
    )
    headline = data.headline or {}
    profile_counts = dict(headline.get("profiles") or data.profile_counts or {})
    total_profiles = sum(int(profile_counts.get(status, 0) or 0) for status in _STATUS_ORDER)

    row = _heading(ws, 4, "Perfiles por estado", span=3)
    status_header = row
    row = _header_row(ws, row, ("Estado", "N° perfiles", "% de perfiles"))
    for status in _STATUS_ORDER:
        count = int(profile_counts.get(status, 0) or 0)
        ws.cell(row=row, column=1, value=STATUS_LABELS_ES[status])
        ws.cell(row=row, column=2, value=count)
        share = _fraction(count, total_profiles)
        if share is not None:
            ws.cell(row=row, column=3, value=share).number_format = FMT_PCT
        row += 1
    status_last = row - 1
    row = _kpi(ws, row, "Total de perfiles", total_profiles)

    row = _heading(ws, row + 1, "Desglose de los perfiles que no cumplen")
    row = _kpi(ws, row, "No cumple por geometría", headline.get("nc_by_geometry"))
    row = _kpi(
        ws, row, "No cumple solo por banco no construido o adicional",
        headline.get("nc_only_missing_extra"),
    )

    benches = headline.get("benches") or {}
    match_by_status = benches.get("match_by_status") or {}
    row = _heading(ws, row + 1, "Bancos")
    row = _kpi(ws, row, "Bancos en el informe", counts.get("n_rows"))
    row = _kpi(ws, row, "Bancos comparados", counts.get("n_match"))
    row = _kpi(ws, row, "Comparados que cumplen", match_by_status.get("CUMPLE"))
    row = _kpi(ws, row, "Comparados que no cumplen", match_by_status.get("NO_CUMPLE"))
    if match_by_status.get("FUERA"):
        row = _kpi(ws, row, "Comparados fuera de tolerancia", match_by_status.get("FUERA"))
    if match_by_status.get("UNKNOWN"):
        row = _kpi(ws, row, "Comparados sin evaluar", match_by_status.get("UNKNOWN"))
    row = _kpi(ws, row, "Bancos no construidos", benches.get("missing", counts.get("n_missing")))
    row = _kpi(ws, row, "Bancos adicionales", benches.get("extra", counts.get("n_extra")))

    achievement = (data.design_achievement or {}).get("global") or {}
    coverage = achievement.get("coverage") or {}
    row = _heading(ws, row + 1, "Puntajes")
    row = _kpi(ws, row, "Puntaje ponderado global (0-100)", data.global_weighted_score, FMT_SCORE)
    row = _kpi(ws, row, "Logro de diseño (0-100)", achievement.get("global_score"), FMT_SCORE)
    row = _kpi(ws, row, "Bancos evaluables para logro de diseño", coverage.get("n_evaluable"))

    row = _heading(ws, row + 1, "Cumplimiento por parámetro (sobre bancos comparados)", span=9)
    parameter_header = row
    row = _header_row(
        ws, row,
        ("Parámetro", "Unidad", "Evaluados (comparados)", "Cumple", "Fuera de tolerancia", "No cumple",
         "% cumplimiento", "No comparados", "Media real"),
    )
    for parameter in data.parameters:
        ws.cell(row=row, column=1, value=parameter.label)
        ws.cell(row=row, column=2, value=parameter.unit)
        ws.cell(row=row, column=3, value=parameter.n_evaluated)
        ws.cell(row=row, column=4, value=parameter.cumple)
        outside = sum(1 for bench in data.rows if bench.type == "MATCH" and _status_text(getattr(bench, f"{parameter.parameter}_status")) == "FUERA DE TOLERANCIA")
        ws.cell(row=row, column=5, value=outside)
        ws.cell(row=row, column=6, value=parameter.no_cumple - outside)
        pct = _pct_fraction(parameter.pct_cumple)
        if pct is not None:
            ws.cell(row=row, column=7, value=pct).number_format = FMT_PCT
        ws.cell(row=row, column=8, value=parameter.n_not_compared)
        mean_real = _finite(parameter.mean_real)
        if mean_real is not None:
            ws.cell(row=row, column=9, value=mean_real).number_format = (
                FMT_DEG if parameter.unit == "°" else FMT_M
            )
        row += 1
    parameter_last = row - 1

    row = _heading(ws, row + 1, "Excavación (estimación por secciones)")
    totals = data.excavation_totals or {}
    if data.excavation:
        row = _kpi(ws, row, "Secciones con geometría", totals.get("n_sections"))
        row = _kpi(ws, row, "Área de sobreexcavación (m²)", totals.get("area_over_m2"), FMT_AREA)
        row = _kpi(ws, row, "Área de subexcavación (m²)", totals.get("area_under_m2"), FMT_AREA)
        row = _kpi(ws, row, "Volumen de sobreexcavación (m³)", totals.get("volume_over_m3"), FMT_VOLUME)
        row = _kpi(ws, row, "Volumen de subexcavación (m³)", totals.get("volume_under_m3"), FMT_VOLUME)
        row = _kpi(ws, row, "Secciones sin volumen", totals.get("n_without_volume"))
    else:
        ws.cell(row=row, column=1, value=NO_GEOMETRY_NOTE)
        row += 1

    has_sector_table = len(data.sector_summaries) > 1
    if has_sector_table:
        row = _heading(ws, row + 1, "Comparación entre sectores", span=9)
        row = _header_row(
            ws, row,
            ("Sector", "Cota nominal", "Perfiles cumple", "Perfiles fuera de tolerancia",
             "Perfiles no cumple", "Puntaje ponderado (0-100)", "% cumple altura",
             "% cumple ángulo", "% cumple berma"),
        )
        for summary in data.sector_summaries:
            sector_counts = summary.get("profile_counts") or {}
            ws.cell(row=row, column=1, value=_sector_label(summary.get("sector")))
            ws.cell(row=row, column=2, value=", ".join(summary.get("levels") or ()) or "Todas")
            ws.cell(row=row, column=3, value=sector_counts.get("CUMPLE"))
            ws.cell(row=row, column=4, value=sector_counts.get("FUERA"))
            ws.cell(row=row, column=5, value=sector_counts.get("NO_CUMPLE"))
            score = _finite(summary.get("global_weighted_score"))
            if score is not None:
                ws.cell(row=row, column=6, value=score).number_format = FMT_SCORE
            by_parameter = {p.parameter: p for p in summary.get("parameters") or ()}
            for offset, (key, _name, _unit, _fmt) in enumerate(_PARAMETERS):
                parameter = by_parameter.get(key)
                pct = _pct_fraction(parameter.pct_cumple) if parameter else None
                if pct is not None:
                    ws.cell(row=row, column=7 + offset, value=pct).number_format = FMT_PCT
            row += 1

    _fit_widths(ws, {1: 50, 2: 16, 3: 18, 4: 16, 5: 16, 6: 18, 7: 16, 8: 16, 9: 16})

    if data.profiles:
        _add_bar_chart(
            ws,
            title="Perfiles por estado",
            header_row=status_header,
            last_row=status_last,
            value_column=2,
            anchor=f"D{status_header - 1}",
            colors=[_hex(status) for status in _STATUS_ORDER],
        )
    if data.parameters and parameter_last > parameter_header:
        _add_bar_chart(
            ws,
            title="% de cumplimiento por parámetro (bancos comparados)",
            header_row=parameter_header,
            last_row=parameter_last,
            value_column=6,
            anchor=f"{'J' if has_sector_table else 'I'}{parameter_header - 1}",
            colors=[_CHART_NEUTRAL],
            percent=True,
        )
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0


def _deviation(bench: Any, parameter: str) -> Optional[float]:
    persisted = _finite(getattr(bench, f"{parameter}_dev"))
    if persisted is not None:
        return persisted
    if bench.type != "MATCH":
        return None
    design = _finite(getattr(bench, f"{parameter}_design"))
    real = _finite(getattr(bench, f"{parameter}_real"))
    if design is None or real is None:
        return None
    return real - design


_BENCH_COLUMNS = (
    _Column("sector", "Sector"),
    _Column("section", "Sección"),
    _Column("level_nominal", "Cota nominal"),
    _Column("level", "Cota (m)"),
    _Column("bench_num", "Banco", FMT_INT),
    _Column("type", "Tipo"),
    _Column("status", "Estado banco", status=True),
    _Column("height_design", "Altura diseño (m)", FMT_M),
    _Column("height_real", "Altura real (m)", FMT_M),
    _Column("height_dev", "Desv. altura (m)", FMT_M),
    _Column("height_status", "Estado altura", status=True),
    _Column("angle_design", "Ángulo diseño (°)", FMT_DEG),
    _Column("angle_real", "Ángulo real (°)", FMT_DEG),
    _Column("angle_dev", "Desv. ángulo (°)", FMT_DEG),
    _Column("angle_status", "Estado ángulo", status=True),
    _Column("berm_design", "Berma diseño (m)", FMT_M),
    _Column("berm_real", "Berma real (m)", FMT_M),
    _Column("berm_dev", "Desv. berma (m)", FMT_M),
    _Column("berm_min", "Berma mínima (m)", FMT_M),
    _Column("berm_status", "Estado berma", status=True),
    _Column("design_below_min", "Diseño bajo el mínimo"),
    _Column("delta_crest", "Desv. cresta (m)", FMT_M),
    _Column("delta_toe", "Desv. pata (m)", FMT_M),
    _Column("spill_width", "Derrame (m)", FMT_M),
    _Column("effective_berm", "Berma efectiva (m)", FMT_M),
    _Column("effective_berm_status", "Estado berma efectiva", status=True),
    _Column("components_missing", "Componentes faltantes"),
)


def _bench_records(data: ReportData) -> list[dict]:
    records: list[dict] = []
    details = _achievement_details(data) or [{}] * len(data.rows)
    for bench, detail in zip(data.rows, details):
        bench_num = bench.bench_num
        if bench.type == "EXTRA" and bench_num == _EXTRA_BENCH_SENTINEL:
            bench_num = None
        records.append(
            {
                "sector": bench.sector.strip() or None,
                "section": bench.section,
                "level_nominal": _number_or_text(bench.level_nominal),
                "level": _number_or_text(bench.level),
                "bench_num": bench_num,
                "type": _TYPE_LABELS.get(bench.type, bench.type),
                "status": bench.status_label,
                "height_design": bench.height_design,
                "height_real": bench.height_real,
                "height_dev": _deviation(bench, "height"),
                "height_status": _status_text(bench.height_status),
                "angle_design": bench.angle_design,
                "angle_real": bench.angle_real,
                "angle_dev": _deviation(bench, "angle"),
                "angle_status": _status_text(bench.angle_status),
                "berm_design": bench.berm_design,
                "berm_real": bench.berm_real,
                "berm_dev": _deviation(bench, "berm"),
                "berm_min": bench.berm_min,
                "berm_status": _status_text(bench.berm_status),
                "design_below_min": "Sí" if bench.design_below_min else "No",
                "delta_crest": bench.delta_crest,
                "delta_toe": bench.delta_toe,
                "spill_width": bench.spill_width,
                "effective_berm": bench.effective_berm,
                "effective_berm_status": _status_text(bench.effective_berm_status),
                "components_missing": ", ".join(
                    str(component) for component in detail.get("components_missing") or ()
                )
                or None,
            }
        )
    return records


_SECTION_COLUMNS = (
    _Column("sector", "Sector"),
    _Column("section", "Sección"),
    _Column("status", "Estado", status=True),
    _Column("score", "Puntaje ponderado (0-100)", FMT_SCORE),
    _Column("n_benches", "N° bancos", FMT_INT),
    _Column("n_match", "Comparados", FMT_INT),
    _Column("n_missing", "No construidos", FMT_INT),
    _Column("n_extra", "Adicionales", FMT_INT),
    _Column("area_over", "Área sobreexcavación (m²)", FMT_AREA),
    _Column("area_under", "Área subexcavación (m²)", FMT_AREA),
    _Column("width", "Ancho de influencia (m)", FMT_M),
    _Column("volume_over", "Volumen sobreexcavación (m³)", FMT_VOLUME),
    _Column("volume_under", "Volumen subexcavación (m³)", FMT_VOLUME),
    _Column("window", "Ventana"),
    _Column("warnings", "Advertencias"),
)


def _window_text(window: Any) -> Optional[str]:
    if window is None:
        return None
    try:
        d_min, d_max, z_min, z_max = (_finite(value) for value in window)
    except (TypeError, ValueError):
        return None
    if None in (d_min, d_max, z_min, z_max):
        return None
    return (
        f"distancia {_es(d_min)} a {_es(d_max)} m; cota {_es(z_min)} a {_es(z_max)} m"
    )


def _section_records(data: ReportData) -> list[dict]:
    order = {
        name: index
        for index, name in enumerate(dict.fromkeys(str(t.get("section", "")) for t in data.trend))
    }
    profiles = sorted(
        enumerate(data.profiles),
        key=lambda item: (order.get(item[1].section, len(order)), item[0]),
    )
    by_identity = {(entry.section, entry.sector): entry for entry in data.excavation}
    by_name: dict[str, list] = {}
    for entry in data.excavation:
        by_name.setdefault(entry.section, []).append(entry)

    records: list[dict] = []
    for _index, profile in profiles:
        entry = by_identity.get((profile.section, profile.sector))
        if entry is None and len(by_name.get(profile.section, ())) == 1:
            entry = by_name[profile.section][0]
        record = {
            "sector": profile.sector.strip() or None,
            "section": profile.section,
            "status": _PROFILE_STATUS_TEXT.get(profile.worst_status, profile.worst_status),
            "score": _finite(profile.weighted_score),
            "n_benches": profile.n_match + profile.n_missing + profile.n_extra,
            "n_match": profile.n_match,
            "n_missing": profile.n_missing,
            "n_extra": profile.n_extra,
        }
        if entry is not None:
            record.update(
                {
                    "area_over": _finite(entry.area_over_m2),
                    "area_under": _finite(entry.area_under_m2),
                    "width": _finite(entry.influence_width_m),
                    "volume_over": _finite(entry.volume_over_m3),
                    "volume_under": _finite(entry.volume_under_m3),
                    "window": _window_text(entry.window),
                    "warnings": " ".join(entry.warnings) or None,
                }
            )
        records.append(record)
    return records


def _sector_level_columns() -> tuple[_Column, ...]:
    columns = [
        _Column("sector", "Sector"),
        _Column("level_nominal", "Cota nominal"),
        _Column("n_sections", "N° secciones", FMT_INT),
        _Column("n_benches", "N° bancos", FMT_INT),
        _Column("n_match", "Comparados", FMT_INT),
        _Column("n_missing", "No construidos", FMT_INT),
        _Column("n_extra", "Adicionales", FMT_INT),
        _Column("match_cumple", "Comparados cumple", FMT_INT),
        _Column("match_no_cumple", "Comparados no cumple", FMT_INT),
        _Column("match_unknown", "Comparados sin evaluar", FMT_INT),
    ]
    for key, name, _unit, _fmt in _PARAMETERS:
        columns.append(_Column(f"{key}_n", f"Evaluados {name}", FMT_INT))
        columns.append(_Column(f"{key}_pct", f"% cumple {name}", FMT_PCT))
    for key, name, unit, fmt in _PARAMETERS:
        columns.append(_Column(f"{key}_dev", f"Desv. media {name} ({unit})", fmt))
    return tuple(columns)


def _level_sort_key(label: Optional[str]) -> tuple[int, float, str]:
    if label is None:
        return (2, 0.0, "")
    number = _finite(label)
    if number is None:
        return (1, 0.0, str(label))
    return (0, -number, "")


def _sector_level_records(data: ReportData) -> list[dict]:
    groups: dict[tuple[str, Optional[str]], list] = {}
    sector_order: dict[str, int] = {}
    for bench in data.rows:
        sector = bench.sector.strip()
        sector_order.setdefault(sector, len(sector_order))
        groups.setdefault((sector, bench.level_nominal), []).append(bench)

    records: list[dict] = []
    for sector, level in sorted(
        groups, key=lambda key: (sector_order[key[0]], _level_sort_key(key[1]))
    ):
        benches = groups[(sector, level)]
        matched = [bench for bench in benches if bench.type == "MATCH"]
        record = {
            "sector": sector or None,
            "level_nominal": _number_or_text(level),
            "n_sections": len({bench.section for bench in benches}),
            "n_benches": len(benches),
            "n_match": len(matched),
            "n_missing": sum(1 for bench in benches if bench.type == "MISSING"),
            "n_extra": sum(1 for bench in benches if bench.type == "EXTRA"),
            "match_cumple": sum(1 for bench in matched if bench.worst_status == "CUMPLE"),
            "match_no_cumple": sum(
                1 for bench in matched if bench.worst_status in ("NO_CUMPLE", "FUERA")
            ),
            "match_unknown": sum(1 for bench in matched if bench.worst_status == "UNKNOWN"),
        }
        for key, _name, _unit, _fmt in _PARAMETERS:
            statuses = [getattr(bench, f"{key}_status") for bench in matched]
            evaluated = [status for status in statuses if status and status != "-"]
            cumple = sum(1 for status in evaluated if status == "CUMPLE")
            record[f"{key}_n"] = len(evaluated)
            record[f"{key}_pct"] = _fraction(cumple, len(evaluated))
            deviations = []
            for bench in matched:
                design = _finite(getattr(bench, f"{key}_design"))
                real = _finite(getattr(bench, f"{key}_real"))
                if design is not None and real is not None:
                    deviations.append(real - design)
            record[f"{key}_dev"] = _mean(deviations)
        records.append(record)
    return records


_BLAST_COLUMNS = (
    _Column("date", "Fecha"),
    _Column("mesh", "Malla"),
    _Column("blast", "Tronadura"),
    _Column("phase", "Fase"),
    _Column("n_holes", "N° pozos", FMT_INT),
    _Column("kg_total", "Explosivo total (kg)", FMT_VOLUME),
    _Column("length_mean", "Largo medio de pozo (m)", FMT_M),
    _Column("stemming_mean", "Taco medio (m)", FMT_M),
    _Column("pf_gt", "FC B×S×L (g/t)", FMT_PF),
    _Column("pf_main", "FC principal (g/t)", FMT_PF, required=True),
    _Column("pf_gt_net", "FC neto medio (g/t)", FMT_PF),
    _Column("pf_vol", "FC volumétrico medio (kg/m³)", FMT_PF_VOL),
    _Column("n_pf", "Pozos con FC", FMT_INT),
    _Column("explosive", "Explosivo"),
    _Column("n_assumed", "Pozos con explosivo de referencia no validada", FMT_INT),
)
_BLAST_GROUP_KEYS = ("fecha_tronadura", "Nombre_Malla_Original", "Blast", "Nombre_Fase")
_NO_DATA = "Sin dato"


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _hole_values(holes: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    values = (_finite(hole.get(key)) for hole in holes)
    return [value for value in values if value is not None]


def _explosive_text(holes: Sequence[Mapping[str, Any]]) -> str:
    tally: dict[str, int] = {}
    for hole in holes:
        name = _text(hole.get("Tipo_Explosivo")) or _NO_DATA
        tally[name] = tally.get(name, 0) + 1
    if len(tally) == 1:
        return next(iter(tally))
    ranked = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    return "; ".join(f"{name} ({count})" for name, count in ranked)


def _blast_records(holes: Sequence[Mapping[str, Any]]) -> list[dict]:
    groups: dict[tuple, list[Mapping[str, Any]]] = {}
    for hole in holes:
        key = tuple(_text(hole.get(name)) for name in _BLAST_GROUP_KEYS)
        groups.setdefault(key, []).append(hole)
    records: list[dict] = []
    for key in sorted(groups, key=lambda item: tuple(value or "" for value in item)):
        members = groups[key]
        date, mesh, blast, phase = key
        kilos = _hole_values(members, "Kilos_Cargados_real")
        powder = _hole_values(members, "pf_g_per_ton")
        records.append(
            {
                "date": date,
                "mesh": mesh or (None if blast else "Sin identificar"),
                "blast": blast,
                "phase": phase,
                "n_holes": len(members),
                "kg_total": math.fsum(kilos) if kilos else None,
                "length_mean": _mean(_hole_values(members, "Len")),
                "stemming_mean": _mean(_hole_values(members, "Taco_m")),
                "pf_gt": _mean(powder),
                "pf_main": _mean(_hole_values(members, "pf_voronoi_bench_g_per_ton")) if _hole_values(members, "pf_voronoi_bench_g_per_ton") else NO_DATA_TEXT,
                "pf_gt_net": _mean(_hole_values(members, "pf_g_per_ton_net")),
                "pf_vol": _mean(_hole_values(members, "pf_vol_kgm3")),
                "n_pf": len(powder) if powder else None,
                "explosive": _explosive_text(members),
                "n_assumed": sum(1 for hole in members if hole.get("explosive_assumption_flag") is True)
                or None,
            }
        )
    return records


def _write_blast(ws: Worksheet, data: ReportData, holes: Sequence[Mapping[str, Any]]) -> None:
    records = _blast_records(holes)
    ws.cell(row=1, column=1, value="Tronadura: resumen por malla").font = _TITLE_FONT
    ws.cell(row=2, column=1, value=f"{len(holes)} pozos en {len(records)} mallas o eventos.")
    ws.cell(
        row=3,
        column=1,
        value=(
            "FC B×S×L y FC principal: medias aritméticas de los factores de carga por pozo calculados en la "
f"sesión; no se recalcula aquí. El detalle por pozo está en la hoja {SHEET_HOLES}."
        ),
    )
    ws.cell(
        row=4,
        column=1,
        value=BLAST_SCOPE_NOTE,
    )
    if _is_legacy_blast(data):
        ws.cell(row=5, column=1, value=REIMPORT_WARNING)
    _write_table(ws, _BLAST_COLUMNS, records, table_name="TablaTronadura", start_row=7)


def _hole_text(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value == int(value):
            return str(int(value))
    return str(value).strip() or None


def _hole_id(hole: Mapping[str, Any]) -> Optional[str]:
    for key in ("id_pozo", "label_pozo", "hole_id"):
        text = _hole_text(hole.get(key))
        if text is not None:
            return text
    return None


_HOLE_TEXT_FIELDS = (
    ("mesh", "Nombre_Malla_Original"),
    ("blast", "Blast"),
    ("phase", "Nombre_Fase"),
    ("date", "fecha_tronadura"),
    ("explosive", "Tipo_Explosivo"),
    ("explosive_status", "explosive_status"),
    ("explosive_source", "explosive_source"),
    ("bench_height_status", "bench_height_status"),
    ("bench_height_source", "bench_height_source"),
    ("pf_main_status", "pf_voronoi_bench_status"),
    ("pf_main_source", "pf_voronoi_bench_source"),
    ("area_status", "area_status"),
)
_HOLE_NUMBER_FIELDS = (
    ("x", "X"),
    ("y", "Y"),
    ("z_collar", "Z_collar"),
    ("x_toe", "X_toe"),
    ("y_toe", "Y_toe"),
    ("z_toe", "Z_toe"),
    ("length", "Len"),
    ("inclination", "Incl"),
    ("azimuth", "Az"),
    ("stemming", "Taco_m"),
    ("kg", "Kilos_Cargados_real"),
    ("bench_height", "bench_height_m"),
    ("pf_main", "pf_voronoi_bench_g_per_ton"),
    ("area", "area_influence_m2"),
) + tuple((name, name) for name in PF_DEFINITIONS)
_PF_UNIT_FORMATS = {"g/t": FMT_PF, "kg/m3": FMT_PF_VOL, "kg/m2": FMT_M}
_HOLE_COLUMNS = (
    _Column("id", "Pozo", required=True),
    _Column("label", "Etiqueta"),
    _Column("mesh", "Malla"),
    _Column("blast", "Tronadura"),
    _Column("phase", "Fase"),
    _Column("date", "Fecha"),
    _Column("x", "Collar X (m)", FMT_M, required=True),
    _Column("y", "Collar Y (m)", FMT_M, required=True),
    _Column("z_collar", "Collar Z (m)", FMT_M, required=True),
    _Column("x_toe", "Pata X (m)", FMT_M),
    _Column("y_toe", "Pata Y (m)", FMT_M),
    _Column("z_toe", "Pata Z (m)", FMT_M),
    _Column("length", "Largo (m)", FMT_M, required=True),
    _Column("inclination", "Inclinación (°)", FMT_DEG),
    _Column("azimuth", "Azimut (°)", FMT_DEG),
    _Column("stemming", "Taco (m)", FMT_M),
    _Column("kg", "Explosivo cargado (kg)", FMT_AREA, required=True),
    _Column("explosive", "Explosivo", required=True),
    _Column("explosive_status", "Estado explosivo"),
    _Column("explosive_source", "Fuente explosivo"),
    _Column("bench_height", "Altura de banco (m)", FMT_M),
    _Column("bench_height_status", "Estado altura de banco"),
    _Column("bench_height_source", "Fuente altura de banco"),
    _Column("pf_main", "FC principal Voronoi banco (g/t)", FMT_PF, required=True),
    _Column("pf_main_status", "Estado FC principal", required=True),
    _Column("pf_main_source", "Fuente FC principal"),
    _Column("area", "Área de influencia (m²)", FMT_AREA),
    _Column("area_status", "Fuente del área de influencia"),
) + tuple(
    _Column(
        name,
        f"FC {definition['formula']} ({definition['unit']})",
        _PF_UNIT_FORMATS.get(definition["unit"], FMT_PF_VOL),
    )
    for name, definition in PF_DEFINITIONS.items()
)


def _hole_records(holes: Sequence[Mapping[str, Any]]) -> list[dict]:
    records: list[dict] = []
    for hole in holes:
        identifier = _hole_id(hole)
        label = _hole_text(hole.get("label_pozo"))
        record: dict[str, Any] = {
            "id": identifier,
            "label": label if label != identifier else None,
        }
        for key, source in _HOLE_TEXT_FIELDS:
            record[key] = _hole_text(hole.get(source))
        for key, source in _HOLE_NUMBER_FIELDS:
            record[key] = _finite(hole.get(source))
        records.append(record)
    return records


def _write_holes(ws: Worksheet, holes: Sequence[Mapping[str, Any]]) -> None:
    _write_table(
        ws, _HOLE_COLUMNS, _hole_records(holes),
        table_name="TablaPozos", missing_text=NO_DATA_TEXT,
    )


def _build_workbook(data: ReportData) -> Workbook:
    holes = _blast_holes(data)
    wb = Workbook()
    readme = wb.worksheets[0]
    readme.title = SHEET_README
    _write_readme(readme, data, holes)
    _write_summary(wb.create_sheet(SHEET_SUMMARY), data)
    _write_table(
        wb.create_sheet(SHEET_BENCHES), _BENCH_COLUMNS, _bench_records(data),
        table_name="TablaBancos",
    )
    _write_table(
        wb.create_sheet(SHEET_SECTIONS), _SECTION_COLUMNS, _section_records(data),
        table_name="TablaSecciones",
    )
    _write_table(
        wb.create_sheet(SHEET_SECTOR_LEVEL), _sector_level_columns(), _sector_level_records(data),
        table_name="TablaSectorNivel",
    )
    if holes:
        _write_blast(wb.create_sheet(SHEET_BLAST), data, holes)
        _write_holes(wb.create_sheet(SHEET_HOLES), holes)
    return wb


def build_excel_report(data: ReportData) -> io.BytesIO:
    """Build the analytical Excel workbook of the web export from ``ReportData``."""
    buffer = io.BytesIO()
    _build_workbook(data).save(buffer)
    buffer.seek(0)
    return buffer
