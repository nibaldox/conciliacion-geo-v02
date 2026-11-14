"""Nominal level grouping for exported reports.

Toe elevations of the same physical bench vary from section to section, so
the exact ``level`` of a comparison row is a poor filter key. This module
groups the levels of each sector into nominal levels.

The module is pure: it reads comparison dicts and returns frozen
dataclasses; it performs no I/O and mutates nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Mapping, Optional, Sequence

BENCH_TYPES = ("MATCH", "MISSING", "EXTRA")
DESIGN_BENCH_TYPES = ("MATCH", "MISSING")
GAP_FRACTION_OF_BENCH_HEIGHT = 1.0 / 3.0
MAX_ITEMS_PER_WARNING = 10

RowKey = tuple[str, str, int, str, str]


@dataclass(frozen=True)
class NominalLevel:
    sector: str
    label: str
    elevation: float
    min_level: float
    max_level: float
    n_sections: int
    n_rows: int


@dataclass(frozen=True)
class NominalLevelAssignment:
    levels: tuple[NominalLevel, ...]
    row_level: dict[RowKey, str]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Entry:
    level: float
    section: str
    bench_num: int
    row_type: str
    level_text: str

    @property
    def is_design_bench(self) -> bool:
        return self.row_type in DESIGN_BENCH_TYPES


def _as_finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _sector_name(value: Any) -> str:
    if value is None or not str(value).strip():
        return ""
    return str(value)


def _sector_suffix(sector: str) -> str:
    return f" (sector {sector})" if sector else ""


def _join_capped(items: Sequence[str]) -> str:
    shown = ", ".join(items[:MAX_ITEMS_PER_WARNING])
    hidden = len(items) - MAX_ITEMS_PER_WARNING
    return f"{shown} y {hidden} más" if hidden > 0 else shown


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _split_by_gap(entries: Sequence[_Entry], threshold: Optional[float]) -> list[list[_Entry]]:
    groups: list[list[_Entry]] = []
    for entry in entries:
        if groups:
            gap = entry.level - groups[-1][-1].level
            same_group = gap == 0 if threshold is None else gap < threshold
            if same_group:
                groups[-1].append(entry)
                continue
        groups.append([entry])
    return groups


def _split_same_section(group: list[_Entry]) -> list[list[_Entry]]:
    spans: dict[str, tuple[float, float]] = {}
    for entry in group:
        if not entry.is_design_bench:
            continue
        low, high = spans.get(entry.section, (entry.level, entry.level))
        spans[entry.section] = (min(low, entry.level), max(high, entry.level))
    conflicts = [span for span in spans.values() if span[0] < span[1]]
    if not conflicts:
        return [group]

    values = sorted({entry.level for entry in group})
    best: Optional[tuple[float, float]] = None
    for lower, upper in zip(values, values[1:]):
        if not any(low <= lower and upper <= high for low, high in conflicts):
            continue
        candidate = (upper - lower, upper)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return [group]

    cut = best[1]
    below = [entry for entry in group if entry.level < cut]
    above = [entry for entry in group if entry.level >= cut]
    return _split_same_section(below) + _split_same_section(above)


def _sections_sharing_design_benches(group: Sequence[_Entry]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in group:
        if entry.is_design_bench:
            counts[entry.section] = counts.get(entry.section, 0) + 1
    return [section for section, count in counts.items() if count > 1]


def _sections_with_shared_extra(group: Sequence[_Entry]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in group:
        counts[entry.section] = counts.get(entry.section, 0) + 1
    return _unique(
        entry.section
        for entry in group
        if not entry.is_design_bench and counts[entry.section] > 1
    )


def _assign_sector(
    sector: str,
    rows: Sequence[Mapping[str, Any]],
    row_level: dict[RowKey, str],
    warnings: list[str],
) -> list[NominalLevel]:
    suffix = _sector_suffix(sector)
    entries: list[_Entry] = []
    invalid_level: list[str] = []
    invalid_bench: list[str] = []
    heights: list[float] = []

    for row in rows:
        section = str(row.get("section", ""))
        height = _as_finite_float(row.get("height_design"))
        if height is not None and height > 0:
            heights.append(height)
        bench_num = _as_int(row.get("bench_num"))
        if bench_num is None:
            invalid_bench.append(section)
            continue
        raw_level = row.get("level")
        level = None if isinstance(raw_level, str) and not raw_level.strip() else _as_finite_float(raw_level)
        if level is None:
            invalid_level.append(f"{section} banco {bench_num}")
            continue
        entries.append(
            _Entry(level, section, bench_num, str(row.get("type")), str(raw_level))
        )

    if invalid_level:
        warnings.append(
            f"{len(invalid_level)} fila(s) sin cota numérica quedaron fuera de la "
            f"agrupación por cota nominal{suffix}: {_join_capped(invalid_level)}."
        )
    if invalid_bench:
        warnings.append(
            f"{len(invalid_bench)} fila(s) sin número de banco quedaron fuera de la "
            f"agrupación por cota nominal{suffix}: {_join_capped(_unique(invalid_bench))}."
        )
    if not entries:
        return []

    ordered = sorted(entries, key=lambda entry: entry.level)
    if heights:
        threshold = GAP_FRACTION_OF_BENCH_HEIGHT * median(heights)
        groups = [
            part
            for group in _split_by_gap(ordered, threshold)
            for part in _split_same_section(group)
        ]
    else:
        groups = _split_by_gap(ordered, None)
        warnings.append(
            f"Sin altura de banco de diseño válida{suffix}: las cotas no se agrupan "
            "y cada cota exacta se trata como una cota nominal."
        )

    levels: list[NominalLevel] = []
    label_by_entry: dict[_Entry, str] = {}
    for group in sorted(groups, key=lambda g: g[0].level, reverse=True):
        values = [entry.level for entry in group]
        elevation = float(median(values))
        label = str(math.floor(elevation + 0.5))
        levels.append(
            NominalLevel(
                sector=sector,
                label=label,
                elevation=elevation,
                min_level=min(values),
                max_level=max(values),
                n_sections=len({entry.section for entry in group}),
                n_rows=len(group),
            )
        )
        for entry in group:
            label_by_entry[entry] = label

        unresolved = _sections_sharing_design_benches(group)
        if unresolved:
            warnings.append(
                f"Cota nominal {label}{suffix}: {len(unresolved)} sección(es) tienen más de "
                "un banco de diseño en la misma cota exacta y no se pudieron separar: "
                f"{_join_capped(unresolved)}."
            )
        shared_extra = _sections_with_shared_extra(group)
        if shared_extra:
            warnings.append(
                f"Cota nominal {label}{suffix}: {len(shared_extra)} sección(es) tienen un "
                "banco adicional que comparte la cota nominal con otro banco de la misma "
                f"sección: {_join_capped(shared_extra)}."
            )

    for entry in entries:
        key = (sector, entry.section, entry.bench_num, entry.row_type, entry.level_text)
        row_level[key] = label_by_entry[entry]

    labels = [level.label for level in levels]
    repeated_labels = _unique(label for label in labels if labels.count(label) > 1)
    if repeated_labels:
        warnings.append(
            f"Cotas nominales con la misma etiqueta{suffix}: {_join_capped(repeated_labels)}."
        )
    return levels


def assign_nominal_levels(rows: Iterable[Mapping[str, Any]]) -> NominalLevelAssignment:
    """Group the toe levels of MATCH/MISSING/EXTRA rows into nominal levels per sector.

    Within a sector the sorted levels are cut where the gap between
    consecutive values reaches one third of the median valid
    ``height_design``. Two design benches (MATCH/MISSING) of one section
    never share a group: the group is cut at the largest gap between them.
    Without a valid ``height_design`` every exact level is its own group.
    Rows without a numeric ``level`` are left out and reported in
    ``warnings``; a missing level is never read as 0.

    The label is the group median rounded half up. ``row_level`` is keyed by
    ``(sector, section, bench_num, type, level)`` where ``level`` is
    ``str(row["level"])`` unchanged, because every EXTRA row carries the same
    ``bench_num``.
    """
    by_sector: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row.get("type") not in BENCH_TYPES:
            continue
        by_sector.setdefault(_sector_name(row.get("sector")), []).append(row)

    levels: list[NominalLevel] = []
    row_level: dict[RowKey, str] = {}
    warnings: list[str] = []
    for sector in sorted(by_sector):
        levels.extend(_assign_sector(sector, by_sector[sector], row_level, warnings))
    return NominalLevelAssignment(
        levels=tuple(levels), row_level=row_level, warnings=tuple(warnings)
    )
