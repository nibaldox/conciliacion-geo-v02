"""Single report data model shared by the Word/PDF exporters.

Ports the web dashboard semantics (``status.ts``, ``mapping.ts``,
``Dashboard.tsx``, ``resultFilters.ts``) into pure Python so the exported
reports show exactly the numbers the on-screen dashboard shows: a profile
is judged by the worst bench of its design banks, and the weighted score is
reported alongside as a separate figure.

The module is pure — it reads the persisted comparison dicts and returns
frozen dataclasses; it performs no I/O and mutates nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Iterable, Mapping, Optional, Sequence

from core.design_achievement import (
    build_design_achievement_summary,
    build_sector_achievement_summary,
)

BENCH_TYPES = ("MATCH", "MISSING", "EXTRA")

STATUS_SEVERITY: dict[str, int] = {
    "UNKNOWN": 0,
    "CUMPLE": 1,
    "FUERA": 2,
    "NO_CUMPLE": 3,
}

_LABEL_BY_WORST = {
    "CUMPLE": "CUMPLE",
    "FUERA": "FUERA DE TOLERANCIA",
    "NO_CUMPLE": "NO CUMPLE",
    "UNKNOWN": "SIN EVALUAR",
}

_PARAMETERS = (
    ("height", "Altura de banco", "m"),
    ("angle", "Ángulo de cara", "°"),
    ("berm", "Ancho de berma", "m"),
)

_TOL_KEY = {"height": "bench_height", "angle": "face_angle", "berm": "berm_width"}

_WEB_SCORE_WEIGHTS = {"berm": 60, "angle": 10, "height": 30}


def parse_bench_status(raw: Any) -> str:
    """Normalise a backend status string to CUMPLE / FUERA / NO_CUMPLE / UNKNOWN."""
    if raw is None:
        return "UNKNOWN"
    s = str(raw).strip().upper()
    if s == "CUMPLE":
        return "CUMPLE"
    if s in ("FUERA DE TOLERANCIA", "FUERA"):
        return "FUERA"
    if s in (
        "NO CUMPLE",
        "NO_CONSTRUIDO",
        "NO CONSTRUIDO",
        "FALTA BANCO",
        "BANCO ADICIONAL",
        "EXTRA",
    ):
        return "NO_CUMPLE"
    return "UNKNOWN"


def worst_of_three(height: Any, angle: Any, berm: Any) -> str:
    """Most severe tier among the three parameter statuses (worstOfThree)."""
    worst = "UNKNOWN"
    for status in (
        parse_bench_status(height),
        parse_bench_status(angle),
        parse_bench_status(berm),
    ):
        if STATUS_SEVERITY[status] > STATUS_SEVERITY[worst]:
            worst = status
    return worst


@dataclass(frozen=True)
class ReportFilters:
    """Active report filters; every empty dimension means "all"."""

    sectors: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    benches: tuple[int, ...] = ()

    def is_empty(self) -> bool:
        return not (self.sectors or self.sections or self.levels or self.benches)


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _sector_identity(value: Any) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    return str(value)


def _depth_sector_identity(value: Any) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _section_identity(row: Mapping[str, Any]) -> tuple[str, Optional[str]]:
    return str(row.get("section", "")), _sector_identity(row.get("sector"))


def filter_comparisons(
    rows: Optional[Iterable[Mapping[str, Any]]],
    filters: ReportFilters,
) -> list[dict]:
    """Apply the report filters with the same semantics as ``filterResults``.

    Dimensions are ANDed, values within a dimension are ORed, and an empty
    dimension does not filter. ``''`` (level/sector without value) is a
    selectable value; benches match ``bench_num`` numerically.
    """
    out: list[dict] = []
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        if filters.sectors and row.get("sector") not in filters.sectors:
            continue
        if filters.sections and row.get("section") not in filters.sections:
            continue
        if filters.levels and row.get("level") not in filters.levels:
            continue
        if filters.benches and row.get("bench_num") not in filters.benches:
            continue
        out.append(dict(row))
    return out


@dataclass(frozen=True)
class BenchRow:
    """A single design/as-built bench in the report, with its worst status."""

    section: str
    sector: str
    level: str
    bench_num: Optional[int]
    type: str
    height_design: Optional[float]
    height_real: Optional[float]
    height_dev: Optional[float]
    angle_design: Optional[float]
    angle_real: Optional[float]
    angle_dev: Optional[float]
    berm_design: Optional[float]
    berm_real: Optional[float]
    berm_dev: Optional[float]
    height_status: Optional[str]
    angle_status: Optional[str]
    berm_status: Optional[str]
    spill_width: Optional[float]
    effective_berm: Optional[float]
    worst_status: str
    status_label: str


@dataclass(frozen=True)
class ProfileSummary:
    """One section/profile judged by the worst bench of its design banks."""

    section: str
    sector: str
    worst_status: str
    weighted_score: Optional[float]
    n_match: int
    n_missing: int
    n_extra: int


@dataclass(frozen=True)
class ParameterSummary:
    """Per-parameter compliance over every bench carrying a status."""

    parameter: str
    label: str
    unit: str
    cumple: int
    no_cumple: int
    pct_cumple: Optional[float]
    mean_real: Optional[float]


@dataclass(frozen=True)
class ReportData:
    """Everything the Word and PDF reports need, computed once."""

    meta: dict
    tolerances: dict
    filters: ReportFilters
    rows: tuple[BenchRow, ...]
    profiles: tuple[ProfileSummary, ...]
    profile_counts: dict
    global_weighted_score: Optional[float]
    parameters: tuple[ParameterSummary, ...]
    design_achievement: Optional[dict]
    top_deviations: tuple[dict, ...]
    depth: Optional[dict]
    counts: dict
    section_geometry: tuple = ()
    plan_inputs: Optional[dict] = None
    blast: Optional[dict] = None
    conclusions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    section_plan_states: tuple[tuple[str, Optional[str], bool, str], ...] = ()

    def resolve_section_plan_state(
        self, section: str, sector: Optional[str], infer_missing_sector: bool = True
    ) -> Optional[tuple[str, Optional[str], bool, str]]:
        """Resolve a plan section by name and sector; ambiguous identities return None."""
        name = str(section)
        sector_key = _sector_identity(sector)
        if self.filters.sections and name not in self.filters.sections:
            return name, sector_key, False, "UNKNOWN"
        if self.filters.sectors and sector_key is not None and sector_key not in self.filters.sectors:
            return name, sector_key, False, "UNKNOWN"
        candidates = [state for state in self.section_plan_states if state[0] == name]
        if sector_key is not None:
            return next((state for state in candidates if state[1] == sector_key), None)
        if not infer_missing_sector:
            return None
        return candidates[0] if len(candidates) == 1 else None


def _status_label(row_type: Any, worst: str) -> str:
    if row_type == "MISSING":
        return "NO CONSTRUIDO"
    if row_type == "EXTRA":
        return "BANCO ADICIONAL"
    return _LABEL_BY_WORST[worst]


def _bench_num(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bench_row(row: Mapping[str, Any]) -> BenchRow:
    h_status = row.get("height_status")
    a_status = row.get("angle_status")
    b_status = row.get("berm_status")
    worst = _bench_score_status(row)
    row_type = row.get("type")
    return BenchRow(
        section=str(row.get("section", "")),
        sector=str(row.get("sector", "")),
        level="" if row.get("level") is None else str(row.get("level")),
        bench_num=_bench_num(row.get("bench_num")),
        type=str(row_type),
        height_design=_as_float(row.get("height_design")),
        height_real=_as_float(row.get("height_real")),
        height_dev=_as_float(row.get("height_dev")),
        angle_design=_as_float(row.get("angle_design")),
        angle_real=_as_float(row.get("angle_real")),
        angle_dev=_as_float(row.get("angle_dev")),
        berm_design=_as_float(row.get("berm_design")),
        berm_real=_as_float(row.get("berm_real")),
        berm_dev=_as_float(row.get("berm_dev")),
        height_status=h_status if h_status is None else str(h_status),
        angle_status=a_status if a_status is None else str(a_status),
        berm_status=b_status if b_status is None else str(b_status),
        spill_width=_as_float(row.get("spill_width")),
        effective_berm=_as_float(row.get("effective_berm")),
        worst_status=worst,
        status_label=_status_label(row_type, worst),
    )


def _web_bench_score(row: Mapping[str, Any]) -> Optional[float]:
    """Return the explicit or fully supported weighted score for a matched bank."""
    raw = row.get("bench_score")
    if raw is not None:
        if isinstance(raw, Real) and not isinstance(raw, bool) and math.isfinite(raw) and 0 <= raw <= 100:
            return float(raw)
        return None
    valid_statuses = {"CUMPLE", "FUERA", "FUERA DE TOLERANCIA", "NO CUMPLE"}
    statuses = [row.get(f"{parameter}_status") for parameter in _WEB_SCORE_WEIGHTS]
    if any(not isinstance(status, str) or status.strip().upper() not in valid_statuses for status in statuses):
        return None
    score = 0.0
    for parameter, weight in _WEB_SCORE_WEIGHTS.items():
        if str(row.get(f"{parameter}_status")).strip().upper() == "CUMPLE":
            score += weight
    return score


def _bench_score_status(row: Mapping[str, Any]) -> str:
    if row.get("type") in ("MISSING", "EXTRA"):
        return "NO_CUMPLE"
    if row.get("type") != "MATCH":
        return "UNKNOWN"
    score = _web_bench_score(row)
    return "UNKNOWN" if score is None else "CUMPLE" if score >= 70 else "NO_CUMPLE"


def _web_profile_scores(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Port of ``Dashboard.tsx::computeProfileScores``: mean bench score per MATCH section."""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if row.get("type") != "MATCH":
            continue
        score = _web_bench_score(row)
        if score is not None:
            grouped.setdefault(str(row.get("section", "")), []).append(score)
    return {section: sum(scores) / len(scores) for section, scores in grouped.items()}


def _profile_statuses(
    rows: Sequence[Mapping[str, Any]], by_sector: bool = False
) -> dict[Any, str]:
    statuses: dict[Any, str] = {}
    for row in rows:
        if row.get("type") not in BENCH_TYPES:
            continue
        section = _section_identity(row) if by_sector else str(row.get("section", ""))
        worst = _bench_score_status(row)
        previous = statuses.get(section)
        if previous is None or STATUS_SEVERITY[worst] > STATUS_SEVERITY[previous]:
            statuses[section] = worst
    return statuses


def _parameter_summaries(rows: Sequence[Mapping[str, Any]]) -> tuple[ParameterSummary, ...]:
    out: list[ParameterSummary] = []
    for parameter, label, unit in _PARAMETERS:
        status_key = f"{parameter}_status"
        real_key = f"{parameter}_real"
        cumple = 0
        no_cumple = 0
        real_sum = 0.0
        real_count = 0
        for row in rows:
            status = row.get(status_key)
            if not status or status == "-":
                continue
            if status == "CUMPLE":
                cumple += 1
            else:
                no_cumple += 1
            real = _as_float(row.get(real_key))
            if real is not None:
                real_sum += real
                real_count += 1
        denom = cumple + no_cumple
        out.append(
            ParameterSummary(
                parameter=parameter,
                label=label,
                unit=unit,
                cumple=cumple,
                no_cumple=no_cumple,
                pct_cumple=(100.0 * cumple / denom) if denom else None,
                mean_real=(real_sum / real_count) if real_count else None,
            )
        )
    return tuple(out)


def _tolerance_decimals(unit: str) -> int:
    """Decimals used when rendering a tolerance value for the given unit."""
    return 1 if unit == "°" else 2


def _tolerance_text(tol: Mapping[str, Any], unit: str) -> str:
    """Human-readable tolerance for the deviation table (``mín 7.00 m``)."""
    decimals = _tolerance_decimals(unit)
    neg = _as_float(tol.get("neg"))
    pos = _as_float(tol.get("pos"))
    if neg is not None and pos is not None:
        if abs(abs(neg) - pos) < 1e-9:
            return f"± {pos:.{decimals}f} {unit}"
        return f"-{abs(neg):.{decimals}f} / +{pos:.{decimals}f} {unit}"
    minimum = _as_float(tol.get("min"))
    if minimum is not None:
        return f"mín {minimum:.{decimals}f} {unit}"
    maximum = _as_float(tol.get("max"))
    if maximum is not None:
        return f"máx {maximum:.{decimals}f} {unit}"
    return "N/A"


def _top_deviations(
    rows: Sequence[Mapping[str, Any]],
    tolerances: Mapping[str, Any],
) -> tuple[dict, ...]:
    """Bench deviations ranked by |deviation| / applicable tolerance.

    A signed ``neg``/``pos`` tolerance ranks the persisted deviation against
    the bound in its direction. A minimum-width criterion (``min``, the form
    the backend uses for the berm tolerance) ranks the shortfall below the
    minimum, ``(min - real) / min``, and only rows actually below it
    participate; the reported ``deviation`` is ``real - min`` so it keeps the
    sign and the ratio of the signed entries. The minimum is read from the
    tolerance and falls back to the row's ``<parameter>_min`` field.

    Every entry carries the keys the PDF deviation table renders
    (``parameter``, ``unit``, ``design``, ``real``, ``deviation``,
    ``tolerance``, ``status``) plus ``tolerance_text``, ``criterion``,
    ``shortfall`` and ``ratio``.
    """
    entries: list[dict] = []
    for row in rows:
        for parameter, _label, unit in _PARAMETERS:
            tol = tolerances.get(_TOL_KEY[parameter])
            tol = tol if isinstance(tol, Mapping) else {}
            design = _as_float(row.get(f"{parameter}_design"))
            real = _as_float(row.get(f"{parameter}_real"))
            status = row.get(f"{parameter}_status")
            shortfall: Optional[float] = None
            if "neg" in tol and "pos" in tol:
                dev = _as_float(row.get(f"{parameter}_dev"))
                if dev is None:
                    continue
                bound = _as_float(tol["pos"] if dev >= 0 else tol["neg"])
                if bound is None or bound <= 0:
                    continue
                ratio = abs(dev) / bound
                tolerance = bound
                criterion = "signed"
                tolerance_text = _tolerance_text(tol, unit)
            else:
                minimum = _as_float(tol.get("min"))
                if minimum is None:
                    minimum = _as_float(row.get(f"{parameter}_min"))
                if minimum is None or minimum <= 0 or real is None or real >= minimum:
                    continue
                shortfall = minimum - real
                dev = real - minimum
                ratio = shortfall / minimum
                tolerance = minimum
                criterion = "min"
                tolerance_text = f"mín {minimum:.{_tolerance_decimals(unit)}f} {unit}"
            entries.append(
                {
                    "section": str(row.get("section", "")),
                    "sector": str(row.get("sector", "")),
                    "level": "" if row.get("level") is None else str(row.get("level")),
                    "bench_num": _bench_num(row.get("bench_num")),
                    "parameter": parameter,
                    "unit": unit,
                    "design": design,
                    "real": real,
                    "deviation": dev,
                    "tolerance": tolerance,
                    "tolerance_text": tolerance_text,
                    "criterion": criterion,
                    "shortfall": shortfall,
                    "ratio": ratio,
                    "status": status,
                }
            )
    entries.sort(
        key=lambda e: (
            -e["ratio"],
            -abs(e["deviation"]),
            e["section"],
            -1 if e["bench_num"] is None else e["bench_num"],
            e["parameter"],
        )
    )
    return tuple(entries)


def _depth_metrics(
    rows: Sequence[Mapping[str, Any]],
    depth_extractions: Optional[Mapping[tuple[str, str], Sequence[Any]]] = None,
) -> Optional[dict]:
    from core.pdf_report import _compute_depth_metrics

    metric_rows = [dict(r) for r in rows]
    if depth_extractions is not None:
        resolved_rows = []
        for row in metric_rows:
            if row.get("type") not in ("MATCH", "EXTRA"):
                continue
            section = str(row.get("section", ""))
            sector = _depth_sector_identity(row.get("sector"))
            topo_number = row.get("bench_num_topo")
            if sector is None or not isinstance(topo_number, int) or isinstance(topo_number, bool):
                return None
            benches = depth_extractions.get((section, sector))
            if benches is None:
                return None
            matches = [b for b in benches if getattr(b, "bench_number", None) == topo_number]
            if len(matches) != 1:
                return None
            bench = matches[0]
            floor = _as_float(getattr(bench, "floor_elevation", None))
            crest = _as_float(getattr(bench, "crest_elevation", None))
            if floor is None or floor <= 0 or crest is None:
                return None
            row["bench_real"] = bench
            resolved_rows.append(row)
        metric_rows = resolved_rows

    metrics = _compute_depth_metrics(metric_rows)
    return None if metrics.get("profundidad") is None else metrics


def _conclusions(
    profiles: Sequence[ProfileSummary],
    profile_counts: Mapping[str, int],
    parameters: Sequence[ParameterSummary],
    global_score: Optional[float],
    design_achievement: Optional[dict],
    counts: Mapping[str, int],
) -> tuple[str, ...]:
    out: list[str] = []
    if global_score is not None:
        out.append(f"Puntaje ponderado global (0-100): {global_score:.1f}.")
    total = len(profiles)
    if total:
        out.append(
            f"Perfiles no conformes (peor banco NO CUMPLE): {profile_counts.get('NO_CUMPLE', 0)} de {total}."
        )
    ranked = [p for p in parameters if p.pct_cumple is not None]
    if ranked:
        lowest = min(ranked, key=lambda p: p.pct_cumple if p.pct_cumple is not None else float("inf"))
        out.append(f"Parámetro con menor cumplimiento: {lowest.label} ({lowest.pct_cumple:.1f}%).")
    sectors = (design_achievement or {}).get("sectors") or []
    scored = [s for s in sectors if s.get("global_score") is not None]
    if scored:
        lowest_sector = min(scored, key=lambda s: s["global_score"])
        out.append(
            f"Sector con menor logro de diseño: {lowest_sector.get('sector', '')} "
            f"({lowest_sector['global_score']}/100)."
        )
    if counts.get("n_missing", 0):
        out.append(f"Bancos de diseño no construidos: {counts['n_missing']}.")
    if counts.get("n_extra", 0):
        out.append(f"Bancos adicionales (no presentes en el diseño): {counts['n_extra']}.")
    return tuple(out)


def _warnings(
    unfiltered_count: int,
    filtered: Sequence[Mapping[str, Any]],
    filters: ReportFilters,
) -> tuple[str, ...]:
    out: list[str] = []
    if unfiltered_count == 0:
        out.append("No hay comparaciones en la sesión.")
    elif not filtered and not filters.is_empty():
        out.append("Los filtros aplicados no coinciden con ningún banco.")
    sectors_by_section: dict[str, set[Optional[str]]] = {}
    for row in filtered:
        if row.get("type") not in BENCH_TYPES:
            continue
        section = str(row.get("section", ""))
        sectors_by_section.setdefault(section, set()).add(_sector_identity(row.get("sector")))
    ambiguous_sections = sorted(
        section for section, sectors in sectors_by_section.items() if len(sectors) > 1
    )
    if ambiguous_sections:
        out.append(
            "La agrupación actual de estados y puntajes por perfil usa el nombre de sección; "
            "estos nombres aparecen asociados a más de una identidad de sector, incluida "
            "la ausencia de sector, dentro del alcance filtrado "
            "y no se pueden atribuir a un sector de forma inequívoca: "
            + ", ".join(ambiguous_sections)
            + "."
        )
    return tuple(out)


def build_report_data(
    comparisons: Optional[Iterable[Mapping[str, Any]]],
    settings: Optional[Mapping[str, Any]],
    filters: ReportFilters,
    meta: Optional[Mapping[str, Any]],
    section_geometry: Optional[Sequence[Any]] = None,
    plan_inputs: Optional[dict] = None,
    blast: Optional[dict] = None,
    depth_extractions: Optional[Mapping[tuple[str, str], Sequence[Any]]] = None,
) -> ReportData:
    """Assemble the frozen report model from persisted comparison rows."""
    settings = settings or {}
    tolerances = dict(settings.get("tolerances") or {})
    unfiltered = [dict(r) for r in (comparisons or ()) if isinstance(r, Mapping)]
    filtered = filter_comparisons(unfiltered, filters)
    bench_rows = [r for r in filtered if r.get("type") in BENCH_TYPES]
    identities_with_data = {
        _section_identity(row)
        for row in unfiltered
        if row.get("type") in BENCH_TYPES
    }
    statuses_by_identity = _profile_statuses(bench_rows, by_sector=True)
    excluded_identities = (
        identities_with_data - set(statuses_by_identity)
        if not filters.is_empty()
        else set()
    )
    section_plan_states = tuple(
        (
            section,
            sector,
            (section, sector) not in excluded_identities,
            statuses_by_identity.get((section, sector), "UNKNOWN"),
        )
        for section, sector in sorted(
            identities_with_data,
            key=lambda identity: (identity[0], identity[1] or ""),
        )
    )

    rows = tuple(_to_bench_row(r) for r in bench_rows)

    statuses = _profile_statuses(bench_rows)
    scores = _web_profile_scores(bench_rows)
    profiles: list[ProfileSummary] = []
    for section in sorted(statuses):
        section_rows = [r for r in bench_rows if str(r.get("section", "")) == section]
        sector = next((str(r.get("sector", "")) for r in section_rows), "")
        profiles.append(
            ProfileSummary(
                section=section,
                sector=sector,
                worst_status=statuses[section],
                weighted_score=scores.get(section),
                n_match=sum(1 for r in section_rows if r.get("type") == "MATCH"),
                n_missing=sum(1 for r in section_rows if r.get("type") == "MISSING"),
                n_extra=sum(1 for r in section_rows if r.get("type") == "EXTRA"),
            )
        )
    profiles_t = tuple(profiles)

    profile_counts = {"CUMPLE": 0, "FUERA": 0, "NO_CUMPLE": 0}
    for status in statuses.values():
        if status in profile_counts:
            profile_counts[status] += 1

    global_score: Optional[float] = None
    if scores:
        global_score = sum(scores.values()) / len(scores)

    counts = {
        "n_rows": len(rows),
        "n_match": sum(1 for r in bench_rows if r.get("type") == "MATCH"),
        "n_missing": sum(1 for r in bench_rows if r.get("type") == "MISSING"),
        "n_extra": sum(1 for r in bench_rows if r.get("type") == "EXTRA"),
        "n_sections": len(profiles_t),
    }

    ct_tol = tolerances.get("crest_toe_deviation")
    design_achievement = {
        "global": build_design_achievement_summary(bench_rows, ct_tol),
        "sectors": build_sector_achievement_summary(bench_rows, ct_tol),
    }

    blast_data = blast
    if blast_data is None and settings.get("blast_holes"):
        blast_data = {
            "holes": settings["blast_holes"],
            "tolerance": tolerances.get("crest_toe_deviation"),
        }
    if not blast_data:
        blast_data = None

    return ReportData(
        meta=dict(meta or {}),
        tolerances=tolerances,
        filters=filters,
        rows=rows,
        profiles=profiles_t,
        profile_counts=profile_counts,
        global_weighted_score=global_score,
        parameters=_parameter_summaries(bench_rows),
        design_achievement=design_achievement,
        top_deviations=_top_deviations(bench_rows, tolerances),
        depth=_depth_metrics(bench_rows, depth_extractions),
        counts=counts,
        section_geometry=tuple(section_geometry or ()),
        plan_inputs=plan_inputs,
        blast=blast_data,
        conclusions=_conclusions(
            profiles_t, profile_counts, _parameter_summaries(bench_rows), global_score,
            design_achievement, counts,
        ),
        warnings=_warnings(len(unfiltered), filtered, filters),
        section_plan_states=section_plan_states,
    )
