"""Shared Spanish texts for the exported reports (contract C9)."""
from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping, Optional, Sequence

from core.blast_achievement import W_BERM, W_CREST, W_TOE
from core.report_data import BENCH_SCORE_PASS, _WEB_SCORE_WEIGHTS, ReportData
from core.report_levels import GAP_FRACTION_OF_BENCH_HEIGHT

DASH = "—"
THOUSANDS_SEPARATOR = "\u202f"
MINUS = "\u2212"
ATTACHED_UNITS = ("°", "%")
POSITION_NEAR_DESIGN_M = 0.5
MAX_LISTED_ITEMS = 12

OFFICIAL_VALUES_LINE = "Solo valores oficiales; la medición guiada no se incluye."
NO_FILTERS_LINE = "Sin filtros: todas las secciones y cotas"

_PARAMETER_SHORT = {"height": "altura", "angle": "ángulo", "berm": "berma"}
_FRACTIONS = {1.0 / 3.0: "⅓", 0.5: "½", 0.25: "¼"}


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (Real, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fmt_es(value: Any, decimals: int = 1, unit: Optional[str] = None) -> str:
    """Format a number the Spanish way; missing or non-finite values give «—»."""
    number = _finite(value)
    if number is None:
        return DASH
    rounded = round(number, decimals)
    text = f"{abs(rounded):,.{decimals}f}"
    text = text.replace(",", THOUSANDS_SEPARATOR).replace(".", ",")
    if rounded < 0:
        text = MINUS + text
    if not unit:
        return text
    return text + unit if unit in ATTACHED_UNITS else f"{text} {unit}"


def _threshold_text(value: float) -> str:
    return fmt_es(value, 0 if float(value).is_integer() else 1)


def _count(mapping: Any, key: str) -> int:
    if not isinstance(mapping, Mapping):
        return 0
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _profile_tally(data: ReportData) -> Mapping[str, Any]:
    profiles = (data.headline or {}).get("profiles")
    if isinstance(profiles, Mapping) and profiles:
        return profiles
    return data.profile_counts or {}


def _n_profiles(data: ReportData) -> int:
    tally = _profile_tally(data)
    return sum(_count(tally, key) for key in ("CUMPLE", "FUERA", "NO_CUMPLE", "UNKNOWN"))


def headline_text(data: ReportData) -> str:
    """One-sentence headline with the official profile statuses split by cause."""
    tally = _profile_tally(data)
    cumple = _count(tally, "CUMPLE")
    fuera = _count(tally, "FUERA")
    no_cumple = _count(tally, "NO_CUMPLE")
    unknown = _count(tally, "UNKNOWN")
    total = cumple + fuera + no_cumple + unknown
    if total == 0:
        return "Sin perfiles evaluados."

    noun = "perfil" if total == 1 else "perfiles"
    verb = "cumple" if total == 1 else "cumplen"
    parts = [f"{cumple} de {total} {noun} {verb}"]
    if fuera:
        parts.append(f"{fuera} fuera de tolerancia")
    if no_cumple:
        headline = data.headline or {}
        if "nc_by_geometry" in headline and "nc_only_missing_extra" in headline:
            by_geometry = _count(headline, "nc_by_geometry")
            only_missing = _count(headline, "nc_only_missing_extra")
            fail = "no cumple" if by_geometry == 1 else "no cumplen"
            parts.append(
                f"{by_geometry} {fail} por geometría y {only_missing} solo por "
                "banco no construido o adicional"
            )
        else:
            fail = "no cumple" if no_cumple == 1 else "no cumplen"
            parts.append(f"{no_cumple} {fail}")
    if unknown:
        parts.append(f"{unknown} sin evaluar")
    return "; ".join(parts) + "."


def _percent(weight: float) -> str:
    return fmt_es(weight * 100, 0)


def _fraction_text(fraction: float) -> str:
    for known, symbol in _FRACTIONS.items():
        if math.isclose(fraction, known):
            return symbol
    return fmt_es(fraction, 2)


def _parameter_denominators(data: ReportData) -> str:
    items = [
        f"{_PARAMETER_SHORT.get(p.parameter, p.label.lower())} {p.n_evaluated}"
        for p in data.parameters
        if p.n_evaluated
    ]
    return f" ({', '.join(items)})" if items else ""


def _not_compared(data: ReportData) -> str:
    counts = data.counts or {}
    missing = _count(counts, "n_missing")
    extra = _count(counts, "n_extra")
    if not (missing or extra):
        return "los bancos no construidos y los adicionales se informan aparte"
    built = "no construido" if missing == 1 else "no construidos"
    added = "adicional" if extra == 1 else "adicionales"
    verb = "se informa" if missing + extra == 1 else "se informan"
    return f"{missing} {built} y {extra} {added} {verb} aparte"


def kpi_definitions(data: ReportData) -> tuple[tuple[str, str], ...]:
    """Name and definition (with its denominator) of every KPI shown in reports."""
    n_profiles = _n_profiles(data)
    profiles_denominator = (
        f"los {n_profiles} perfiles evaluados"
        if n_profiles > 1
        else "el perfil evaluado" if n_profiles == 1 else "los perfiles evaluados"
    )
    weights = ", ".join(
        f"{_PARAMETER_SHORT[name]} {weight}"
        for name, weight in sorted(_WEB_SCORE_WEIGHTS.items(), key=lambda item: -item[1])
    )
    return (
        (
            "Perfiles por estado",
            "Cada perfil toma el estado de su peor banco; un banco no construido o "
            f"adicional cuenta como NO CUMPLE. Denominador: {profiles_denominator}.",
        ),
        (
            "Puntaje ponderado",
            f"Puntaje de 0 a 100 por banco comparado: suma los pesos ({weights}) de "
            f"los parámetros que cumplen; el banco es CUMPLE si el puntaje es ≥ "
            f"{_threshold_text(BENCH_SCORE_PASS)}. El puntaje del perfil es el promedio de sus bancos "
            "comparados y el global, el promedio de los perfiles con puntaje.",
        ),
        (
            "Logro de diseño",
            "Puntaje de 0 a 100 de la posición construida frente al diseño: cresta "
            f"{_percent(W_CREST)}, pata {_percent(W_TOE)} y berma {_percent(W_BERM)}; "
            "CUMPLE vale 1, FUERA DE TOLERANCIA 0,5 y NO CUMPLE 0. Denominador: bancos "
            "con medición de cresta, pata o berma.",
        ),
        (
            "% de cumplimiento por parámetro",
            "Bancos en CUMPLE sobre los bancos comparados con el diseño"
            f"{_parameter_denominators(data)}; {_not_compared(data)}.",
        ),
        (
            "Volúmenes de excavación",
            "Estimación, no cubicación: área de sobreexcavación o subexcavación de la "
            "sección × ancho de influencia, que es la separación real entre secciones "
            "del sector (mitad de la distancia a cada sección vecina).",
        ),
        (
            "Cota nominal",
            "Las cotas de pata cercanas de un sector se agrupan en una cota nominal: se "
            "corta donde el salto entre cotas es ≥ "
            f"{_fraction_text(GAP_FRACTION_OF_BENCH_HEIGHT)} de la altura de banco de "
            "diseño (mediana) y dos bancos de una misma sección nunca comparten cota.",
        ),
    )


def _listed(items: Sequence[Any]) -> str:
    names = [str(item) for item in items]
    if len(names) <= MAX_LISTED_ITEMS:
        return ", ".join(names)
    return ", ".join(names[:MAX_LISTED_ITEMS]) + ", …"


def _levels_text(levels: Sequence[str], *, capitalized: bool = False) -> str:
    noun = "cota" if len(levels) == 1 else "cotas"
    if capitalized:
        noun = noun.capitalize()
    return f"{noun} {', '.join(str(level) for level in levels)}"


def _filter_lines(data: ReportData) -> list[str]:
    filters = data.filters
    if filters.is_empty():
        return [NO_FILTERS_LINE]

    lines: list[str] = []
    if filters.sectors:
        for sector in filters.sectors:
            selection = filters.levels_for(sector)
            detail = _levels_text(selection) if selection else "todas las cotas"
            lines.append(f"Sector {sector}: {detail}" if sector else detail.capitalize())
    else:
        named = False
        for sector, selection in filters.levels_by_sector:
            if not selection and not filters.levels:
                continue
            if not sector:
                lines.append(
                    _levels_text(selection, capitalized=True)
                    if selection
                    else "Sin sector: todas las cotas"
                )
                continue
            named = True
            detail = _levels_text(selection) if selection else "todas las cotas"
            lines.append(f"Sector {sector}: {detail}")
        if filters.levels:
            text = _levels_text(filters.levels, capitalized=not named)
            lines.append(f"Demás sectores: {text}" if named else text)

    if filters.sections:
        count = len(filters.sections)
        label = "Sección" if count == 1 else "Secciones"
        if count > MAX_LISTED_ITEMS:
            label = f"{label} ({count})"
        lines.append(f"{label}: {_listed(filters.sections)}")
    if filters.benches:
        label = "Banco" if len(filters.benches) == 1 else "Bancos"
        lines.append(f"{label}: {_listed(filters.benches)}")
    return lines


def scope_lines(data: ReportData) -> tuple[str, ...]:
    """Scope of the report: filters, level warnings, heatmap notes, exclusions."""
    lines = _filter_lines(data)
    lines.extend(str(warning) for warning in data.level_warnings)
    lines.extend(str(note) for note in data.heatmap_notes)
    states = data.section_plan_states
    excluded = sum(1 for state in states if not state[2])
    if excluded:
        lines.append(f"Secciones excluidas por los filtros: {excluded} de {len(states)}.")
    lines.append(OFFICIAL_VALUES_LINE)
    return tuple(lines)


def heatmap_position_note(
    summary: Any, *, level_label: Optional[str] = None
) -> Optional[str]:
    """Note separating bench-shape compliance from wall position (D16)."""
    raw = summary.get("median_m") if isinstance(summary, Mapping) else getattr(summary, "median_m", None)
    median = _finite(raw)
    if median is None:
        return None
    restricted = summary.get("restricted_sections") if isinstance(summary, Mapping) else getattr(summary, "restricted_sections", False)
    section_scope = "en las secciones del informe " if restricted else ""
    if abs(median) <= POSITION_NEAR_DESIGN_M:
        signed = fmt_es(median, 1, "m")
        if round(median, 1) > 0:
            signed = "+" + signed
        return (
            f"La pared quedó {section_scope}en promedio cerca de la posición de diseño "
            f"(mediana {signed})."
        )
    where = f"en la cota {level_label} " if level_label else ""
    direction = (
        "más atrás que el diseño (sobreexcavación)"
        if median > 0
        else "más adelante que el diseño (falta excavar)"
    )
    return (
        "La forma del banco se evalúa por altura, ángulo y berma; la posición de la "
        f"pared es otra medida: {where}{section_scope}la pared quedó en promedio "
        f"~{fmt_es(abs(median), 1, 'm')} {direction}."
    )
