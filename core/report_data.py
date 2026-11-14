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
from core.report_levels import NominalLevelAssignment, assign_nominal_levels
from core.report_volumes import (
    SectionExcavation,
    section_excavation,
    section_influence_widths,
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
    levels_by_sector: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.sectors
            or self.sections
            or self.levels
            or self.benches
            or any(selection for _sector, selection in self.levels_by_sector)
        )

    def levels_for(self, sector: str) -> tuple[str, ...]:
        """Level selection of a sector: its own entry when present, else the global one.

        A sector listed with an empty selection keeps all its levels, even
        when global ``levels`` are set.
        """
        for name, selection in self.levels_by_sector:
            if name == sector:
                return tuple(selection)
        return self.levels


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


def _level_sector(value: Any) -> str:
    return _sector_identity(value) or ""


def _nominal_level(
    row: Mapping[str, Any], assignment: NominalLevelAssignment
) -> Optional[str]:
    raw = row.get("bench_num")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        bench_num = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    key = (
        _level_sector(row.get("sector")),
        str(row.get("section", "")),
        bench_num,
        str(row.get("type")),
        str(row.get("level")),
    )
    return assignment.row_level.get(key)


def _level_matches(
    level: Any, nominal: Optional[str], selected: Sequence[str], labels: frozenset[str]
) -> bool:
    for value in selected:
        if value in labels:
            if nominal == value:
                return True
        elif level == value or (level is not None and str(level) == value):
            return True
    return False


def _filter_with_levels(
    rows: Sequence[Mapping[str, Any]],
    filters: ReportFilters,
    assignment: NominalLevelAssignment,
) -> list[dict]:
    labels_by_sector: dict[str, set[str]] = {}
    for level in assignment.levels:
        labels_by_sector.setdefault(level.sector, set()).add(level.label)
    labels = {sector: frozenset(values) for sector, values in labels_by_sector.items()}
    no_labels: frozenset[str] = frozenset()

    out: list[dict] = []
    for row in rows:
        if filters.sectors and row.get("sector") not in filters.sectors:
            continue
        if filters.sections and row.get("section") not in filters.sections:
            continue
        if filters.benches and row.get("bench_num") not in filters.benches:
            continue
        sector = _level_sector(row.get("sector"))
        nominal = _nominal_level(row, assignment)
        selected = filters.levels_for(sector)
        if selected and not _level_matches(
            row.get("level"), nominal, selected, labels.get(sector, no_labels)
        ):
            continue
        result = dict(row)
        result["level_nominal"] = nominal
        out.append(result)
    return out


def filter_comparisons(
    rows: Optional[Iterable[Mapping[str, Any]]],
    filters: ReportFilters,
) -> list[dict]:
    """Apply the report filters; levels are nominal levels (``core.report_levels``).

    Dimensions are ANDed, values within a dimension are ORed, and an empty
    dimension does not filter. ``''`` (sector without value) is a selectable
    sector; benches match ``bench_num`` numerically.

    Nominal levels are assigned over all input rows before any filtering, so
    the grouping never depends on the other filters. Every returned dict is a
    copy carrying the additive key ``level_nominal`` (the nominal label, or
    ``None`` for a row left out of the grouping); input rows are not mutated.

    Level dimension: the selection of a row is ``filters.levels_for(sector)``,
    with a missing or blank sector read as ``''``. A row passes when that
    selection is empty or holds its nominal label. Backward compatibility: a
    selected value that is not a nominal label of the row's sector is matched
    against the exact ``level`` text instead, which keeps the exact levels the
    dashboard sends today working, including ``''`` for a row without level.
    """
    materialized = [row for row in (rows or ()) if isinstance(row, Mapping)]
    return _filter_with_levels(
        materialized, filters, assign_nominal_levels(materialized)
    )


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
    effective_berm_status: Optional[str]
    worst_status: str
    status_label: str
    level_nominal: Optional[str] = None
    design_below_min: bool = False


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
    """Per-parameter compliance over the compared (MATCH) benches.

    ``cumple``, ``no_cumple`` and ``pct_cumple`` count only MATCH rows carrying
    a status for the parameter; ``n_evaluated`` is that denominator and
    ``n_not_compared`` the MISSING plus EXTRA rows reported apart.
    ``mean_real`` keeps averaging every row that carries a status.
    """

    parameter: str
    label: str
    unit: str
    cumple: int
    no_cumple: int
    pct_cumple: Optional[float]
    mean_real: Optional[float]
    n_evaluated: int = 0
    n_not_compared: int = 0


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
    nominal_levels: tuple = ()
    level_warnings: tuple[str, ...] = ()
    headline: dict = field(default_factory=dict)
    matrix: tuple[dict, ...] = ()
    deviations: dict[str, tuple[float, ...]] = field(default_factory=dict)
    trend: tuple[dict, ...] = ()
    excavation: tuple[SectionExcavation, ...] = ()
    excavation_totals: dict = field(default_factory=dict)
    sector_summaries: tuple[dict, ...] = ()

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
        effective_berm_status=row.get("effective_berm_status"),
        worst_status=worst,
        status_label=_status_label(row_type, worst),
        level_nominal=row.get("level_nominal"),
        design_below_min=_design_below_min(row),
    )


def _design_below_min(row: Mapping[str, Any]) -> bool:
    design = _as_float(row.get("berm_design"))
    minimum = _as_float(row.get("berm_min"))
    return design is not None and minimum is not None and design < minimum


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


def compute_dashboard_weighted_score(
    rows: Iterable[Mapping[str, Any]],
) -> dict:
    """Dashboard weighted score over raw comparison rows (dicts like ``db.get_results``).

    Exact port of ``Dashboard.tsx::computeGlobalScore``: per section, the
    mean of the MATCH bench scores (``_web_bench_score``: berma 60 +
    ángulo 10 + altura 30 when CUMPLE, or the persisted ``bench_score``);
    then a simple mean across sections. This is the number the user sees
    as "Score ponderado global" in the UI, and is a different figure from
    the Logro Diseño score (``build_design_achievement_summary``).
    """
    materialized = [row for row in (rows or ()) if isinstance(row, Mapping)]
    scores = _web_profile_scores(materialized)
    global_score: Optional[float] = None
    if scores:
        global_score = round(sum(scores.values()) / len(scores), 2)
    by_section = {section: round(score, 2) for section, score in sorted(scores.items())}
    n_benches = sum(
        1
        for row in materialized
        if row.get("type") == "MATCH" and _web_bench_score(row) is not None
    )
    return {
        "global_score": global_score,
        "n_profiles": len(scores),
        "n_benches": n_benches,
        "weights": dict(_WEB_SCORE_WEIGHTS),
        "by_section": by_section,
        "definition": (
            "mean of per-section mean bench score; bench score = "
            "berm 60 + angle 10 + height 30 when CUMPLE"
        ),
    }


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
    n_not_compared = sum(1 for row in rows if row.get("type") in ("MISSING", "EXTRA"))
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
            if row.get("type") == "MATCH":
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
                n_evaluated=denom,
                n_not_compared=n_not_compared,
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


def _profile_counts(statuses: Mapping[Any, str]) -> dict:
    counts = {"CUMPLE": 0, "FUERA": 0, "NO_CUMPLE": 0}
    for status in statuses.values():
        if status in counts:
            counts[status] += 1
    return counts


def _mean_score(scores: Mapping[str, float]) -> Optional[float]:
    return sum(scores.values()) / len(scores) if scores else None


def _status_tally() -> dict:
    return {"CUMPLE": 0, "FUERA": 0, "NO_CUMPLE": 0, "UNKNOWN": 0}


def _headline(rows: Sequence[Mapping[str, Any]], statuses: Mapping[str, str]) -> dict:
    """Official statuses split by cause; ``statuses`` are the existing profile statuses."""
    profiles = _status_tally()
    for status in statuses.values():
        profiles[status] += 1
    match_by_status = _status_tally()
    failing_by_geometry: set[str] = set()
    for row in rows:
        if row.get("type") != "MATCH":
            continue
        status = _bench_score_status(row)
        match_by_status[status] += 1
        if status != "CUMPLE":
            failing_by_geometry.add(str(row.get("section", "")))
    non_compliant = [section for section, status in statuses.items() if status == "NO_CUMPLE"]
    by_geometry = sum(1 for section in non_compliant if section in failing_by_geometry)
    return {
        "profiles": profiles,
        "nc_by_geometry": by_geometry,
        "nc_only_missing_extra": len(non_compliant) - by_geometry,
        "benches": {
            "match_by_status": match_by_status,
            "missing": sum(1 for row in rows if row.get("type") == "MISSING"),
            "extra": sum(1 for row in rows if row.get("type") == "EXTRA"),
        },
    }


def _plan_sections(plan_inputs: Any) -> list[dict]:
    """Read-only view of the defined sections as ``name``/``sector``/``origin`` dicts."""
    if isinstance(plan_inputs, Mapping):
        raw = plan_inputs.get("sections")
    elif isinstance(plan_inputs, (list, tuple)):
        raw = plan_inputs
    else:
        raw = None
    sections: list[dict] = []
    for item in raw or ():
        if isinstance(item, Mapping):
            name, sector, origin = item.get("name"), item.get("sector"), item.get("origin")
        else:
            name = getattr(item, "name", None)
            sector = getattr(item, "sector", None)
            origin = getattr(item, "origin", None)
        if name is None:
            continue
        sections.append(
            {"name": str(name), "sector": _level_sector(sector), "origin": origin}
        )
    return sections


def _row_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("section", "")), _level_sector(row.get("sector"))


def _ordered_identities(
    plan_sections: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[str, str]]:
    """(section, sector) identities of the rows in the defined section order.

    The order is the one of the plan sections; identities absent from the
    plan follow in order of appearance in the rows.
    """
    by_pair: dict[tuple[str, str], int] = {}
    by_name: dict[str, int] = {}
    for index, section in enumerate(plan_sections):
        by_pair.setdefault((section["name"], section["sector"]), index)
        by_name.setdefault(section["name"], index)
    identities = list(dict.fromkeys(_row_identity(row) for row in rows))
    unplanned = len(plan_sections)

    def rank(identity: tuple[str, str]) -> int:
        if identity in by_pair:
            return by_pair[identity]
        return by_name.get(identity[0], unplanned)

    return sorted(identities, key=rank)


def _matrix(
    rows: Sequence[Mapping[str, Any]],
    bench_rows: Sequence[BenchRow],
    identities: Sequence[tuple[str, str]],
) -> tuple[dict, ...]:
    position = {identity: index for index, identity in enumerate(identities)}
    order = sorted(range(len(rows)), key=lambda index: position[_row_identity(rows[index])])
    out: list[dict] = []
    for index in order:
        section, sector = _row_identity(rows[index])
        bench = bench_rows[index]
        out.append(
            {
                "section": section,
                "sector": sector,
                "level_nominal": bench.level_nominal,
                "bench_num": bench.bench_num,
                "type": bench.type,
                "worst_status": bench.worst_status,
                "height_status": bench.height_status,
                "angle_status": bench.angle_status,
                "berm_status": bench.berm_status,
                "design_below_min": bench.design_below_min,
            }
        )
    return tuple(out)


def _real_minus_design(row: Mapping[str, Any], parameter: str) -> Optional[float]:
    design = _as_float(row.get(f"{parameter}_design"))
    real = _as_float(row.get(f"{parameter}_real"))
    if design is None or real is None:
        return None
    return real - design


def _deviations(rows: Sequence[Mapping[str, Any]]) -> dict[str, tuple[float, ...]]:
    out: dict[str, tuple[float, ...]] = {}
    for parameter, _label, _unit in _PARAMETERS:
        values = (
            _real_minus_design(row, parameter)
            for row in rows
            if row.get("type") == "MATCH"
        )
        out[parameter] = tuple(value for value in values if value is not None)
    return out


def _mean(values: Sequence[float]) -> Optional[float]:
    return math.fsum(values) / len(values) if values else None


def _trend(
    rows: Sequence[Mapping[str, Any]],
    identities: Sequence[tuple[str, str]],
) -> tuple[dict, ...]:
    """Mean real − design deviation per section; ``n`` counts its MATCH rows."""
    matched: dict[tuple[str, str], list[Mapping[str, Any]]] = {
        identity: [] for identity in identities
    }
    for row in rows:
        if row.get("type") == "MATCH":
            matched[_row_identity(row)].append(row)
    out: list[dict] = []
    for section, sector in identities:
        section_rows = matched[(section, sector)]
        means = {}
        for parameter in ("height", "angle"):
            values = [_real_minus_design(row, parameter) for row in section_rows]
            means[parameter] = _mean([value for value in values if value is not None])
        out.append(
            {
                "section": section,
                "sector": sector,
                "height_dev_mean": means["height"],
                "angle_dev_mean": means["angle"],
                "n": len(section_rows),
            }
        )
    return tuple(out)


def _excavation(
    section_geometry: Sequence[Any],
    plan_sections: Sequence[Mapping[str, Any]],
    identities: Sequence[tuple[str, str]],
) -> tuple[SectionExcavation, ...]:
    """Excavation of every geometry entry whose section is in the filtered rows."""
    widths = section_influence_widths(plan_sections)
    plan_sectors: dict[str, list[str]] = {}
    for section in plan_sections:
        plan_sectors.setdefault(section["name"], []).append(section["sector"])
    row_sectors: dict[str, list[str]] = {}
    for name, sector in identities:
        row_sectors.setdefault(name, []).append(sector)
    position = {identity: index for index, identity in enumerate(identities)}

    ranked: list[tuple[int, SectionExcavation]] = []
    for entry in section_geometry:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("section_name", ""))
        sectors = row_sectors.get(name)
        if not sectors:
            continue
        raw_sector = entry.get("sector")
        if raw_sector is None:
            raw_sector = getattr(entry.get("params_design"), "sector", None)
        sector = _level_sector(raw_sector)
        if sector not in sectors:
            if sector and "" not in sectors:
                continue
            if not sector and len(sectors) == 1:
                sector = sectors[0]
        width = widths.get((sector, name))
        if (sector, name) not in widths and len(plan_sectors.get(name, ())) == 1:
            width = widths.get((plan_sectors[name][0], name))
        ranked.append(
            (
                position.get((name, sector), position[(name, sectors[0])]),
                section_excavation(
                    name,
                    sector,
                    entry.get("profile_d"),
                    entry.get("profile_t"),
                    entry.get("view_window"),
                    width,
                ),
            )
        )
    ranked.sort(key=lambda item: item[0])
    return tuple(excavation for _rank, excavation in ranked)


def _excavation_totals(entries: Sequence[SectionExcavation]) -> dict:
    """Sums over the non-null values only; ``None`` when a magnitude has none."""

    def total(attribute: str) -> Optional[float]:
        values = [getattr(entry, attribute) for entry in entries]
        present = [value for value in values if value is not None]
        return math.fsum(present) if present else None

    return {
        "area_over_m2": total("area_over_m2"),
        "area_under_m2": total("area_under_m2"),
        "volume_over_m3": total("volume_over_m3"),
        "volume_under_m3": total("volume_under_m3"),
        "n_sections": len(entries),
        "n_without_volume": sum(
            1
            for entry in entries
            if entry.volume_over_m3 is None or entry.volume_under_m3 is None
        ),
    }


def _sector_summaries(
    rows: Sequence[Mapping[str, Any]],
    identities: Sequence[tuple[str, str]],
    filters: ReportFilters,
    ct_tol: Any,
    excavation: Sequence[SectionExcavation],
) -> tuple[dict, ...]:
    """One summary per sector of the filtered rows, in the defined section order."""
    out: list[dict] = []
    for sector in dict.fromkeys(sector for _section, sector in identities):
        subset = [row for row in rows if _level_sector(row.get("sector")) == sector]
        statuses = _profile_statuses(subset)
        out.append(
            {
                "sector": sector,
                "levels": filters.levels_for(sector),
                "profile_counts": _profile_counts(statuses),
                "headline": _headline(subset, statuses),
                "global_weighted_score": _mean_score(_web_profile_scores(subset)),
                "parameters": _parameter_summaries(subset),
                "design_achievement": build_design_achievement_summary(subset, ct_tol),
                "excavation_totals": _excavation_totals(
                    [entry for entry in excavation if entry.sector == sector]
                ),
            }
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
    level_assignment = assign_nominal_levels(unfiltered)
    filtered = _filter_with_levels(unfiltered, filters, level_assignment)
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

    profile_counts = _profile_counts(statuses)
    global_score = _mean_score(scores)

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

    parameters = _parameter_summaries(bench_rows)
    geometry = tuple(section_geometry or ())
    plan_sections = _plan_sections(plan_inputs)
    identities = _ordered_identities(plan_sections, bench_rows)
    excavation = _excavation(geometry, plan_sections, identities)

    blast_data = blast
    if blast_data is None and settings.get("blast_holes"):
        blast_data = {
            "holes": settings["blast_holes"],
            "tolerance": tolerances.get("crest_toe_deviation"),
        }
    if blast_data:
        blast_data = dict(blast_data)
        try:
            from core.blast_hole_consolidation import BLAST_ALGORITHM_VERSION
        except ImportError:
            BLAST_ALGORITHM_VERSION = None
        version = settings.get("blast_algorithm_version")
        blast_data["data_status"] = "current" if BLAST_ALGORITHM_VERSION is not None and version == BLAST_ALGORITHM_VERSION else "legacy_reimport_required"
        consolidation = (settings.get("blast_upload_meta") or {}).get("consolidation_report")
        if consolidation:
            blast_data.setdefault("consolidation_report", consolidation)
    else:
        blast_data = None

    return ReportData(
        meta=dict(meta or {}),
        tolerances=tolerances,
        filters=filters,
        rows=rows,
        profiles=profiles_t,
        profile_counts=profile_counts,
        global_weighted_score=global_score,
        parameters=parameters,
        design_achievement=design_achievement,
        top_deviations=_top_deviations(bench_rows, tolerances),
        depth=_depth_metrics(bench_rows, depth_extractions),
        counts=counts,
        section_geometry=geometry,
        plan_inputs=plan_inputs,
        blast=blast_data,
        conclusions=_conclusions(
            profiles_t, profile_counts, parameters, global_score,
            design_achievement, counts,
        ),
        warnings=_warnings(len(unfiltered), filtered, filters),
        section_plan_states=section_plan_states,
        nominal_levels=level_assignment.levels,
        level_warnings=level_assignment.warnings,
        headline=_headline(bench_rows, statuses),
        matrix=_matrix(bench_rows, rows, identities),
        deviations=_deviations(bench_rows),
        trend=_trend(bench_rows, identities),
        excavation=excavation,
        excavation_totals=_excavation_totals(excavation),
        sector_summaries=_sector_summaries(
            bench_rows, identities, filters, ct_tol, excavation
        ),
    )
