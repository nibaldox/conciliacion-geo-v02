"""Horizontal-deviation heatmap page of the reconciliation report.

Developed view of the wall (station along the sections x elevation) built from the
payload already computed for the 3D view. Categories, colours and Spanish labels
mirror ``web/src/utils/horizontalDeviation.ts`` and ``horizontalDeviation.categories``
of ``web/src/locales/es.json``; the category of each cell is the one carried by the
payload and is never recomputed from the deviation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from core.report_charts import (
    _cleanup_failed_figures,
    _fig_to_png,
    _new_figure,
    _serialized_render,
)

HDEV_CATEGORY_ORDER: tuple[str, ...] = (
    "within_tolerance",
    "underbreak_minor",
    "underbreak_moderate",
    "underbreak_severe",
    "overbreak_minor",
    "overbreak_moderate",
    "overbreak_severe",
    "unmeasured",
)

HDEV_COLORS: dict[str, str] = {
    "within_tolerance": "#22c55e",
    "underbreak_minor": "#facc15",
    "underbreak_moderate": "#f97316",
    "underbreak_severe": "#ef4444",
    "overbreak_minor": "#22d3ee",
    "overbreak_moderate": "#3b82f6",
    "overbreak_severe": "#1e3a8a",
    "unmeasured": "#94a3b8",
}

HDEV_LABELS_ES: dict[str, str] = {
    "within_tolerance": "Dentro de tolerancia (≤1 m)",
    "underbreak_minor": "Faltante leve (1–1,8 m)",
    "underbreak_moderate": "Faltante moderado (1,8–3 m)",
    "underbreak_severe": "Faltante severo (>3 m)",
    "overbreak_minor": "Sobreexcavación leve (1–1,8 m)",
    "overbreak_moderate": "Sobreexcavación moderada (1,8–3 m)",
    "overbreak_severe": "Sobreexcavación severa (>3 m)",
    "unmeasured": "Sin medición",
}

_UNMEASURED = "unmeasured"
_LEGEND_ORDER: tuple[str, ...] = (
    "overbreak_severe",
    "overbreak_moderate",
    "overbreak_minor",
    "within_tolerance",
    "underbreak_minor",
    "underbreak_moderate",
    "underbreak_severe",
    "unmeasured",
)
_INK = "#1F2937"
_GREY = "#6B7280"
_GRID = "#E4E8ED"
_SECTION_LINE = "#8E99A6"
_CONTEXT_BLEND = 0.72
_STATION_MATCH_TOL_M = 0.01
_SECTION_LABEL_FONTSIZE = 6.5
_LEGEND_WIDTH_IN = 2.55
_MARGIN_LEFT_IN = 0.75
_MARGIN_BOTTOM_IN = 0.55
_MARGIN_TOP_IN = 0.62
_TITLE_EXTRA_IN = 0.26
_NBSP = "\u00a0"
_MINUS = "\u2212"


@dataclass(frozen=True)
class HeatmapSummary:
    n_cells: int
    n_measured: int
    counts: dict[str, int]
    pct_within: Optional[float]
    median_m: Optional[float]
    p95_abs_m: Optional[float]
    max_over: Optional[dict]
    max_under: Optional[dict]
    level_window: Optional[tuple[float, float]]
    restricted_sections: bool = False


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class LevelWindow(tuple):
    def __new__(cls, windows):
        obj = super().__new__(cls, (windows[0][0], windows[-1][1]))
        obj.windows = tuple(windows)
        return obj


def _normalize_window(level_window: Any) -> Optional[tuple[float, float]]:
    if isinstance(level_window, LevelWindow):
        return level_window
    if level_window is None:
        return None
    try:
        low, high = level_window
    except (TypeError, ValueError):
        return None
    low, high = _finite(low), _finite(high)
    if low is None or high is None:
        return None
    return (min(low, high), max(low, high))


def _cells(payload: Any) -> list[Mapping]:
    if not isinstance(payload, Mapping):
        return []
    cells = payload.get("cells")
    if not isinstance(cells, Sequence) or isinstance(cells, (str, bytes)):
        return []
    return [cell for cell in cells if isinstance(cell, Mapping)]


def _cell_category(cell: Mapping) -> str:
    if _finite(cell.get("deviation_m")) is None:
        return _UNMEASURED
    category = cell.get("category")
    if category == "unassessed" or category not in HDEV_COLORS:
        return _UNMEASURED
    return category


def _in_window(cell: Mapping, window: Optional[tuple[float, float]]) -> bool:
    if window is None:
        return True
    elevation = _finite(cell.get("elevation_m"))
    windows = window.windows if isinstance(window, LevelWindow) else (window,)
    return elevation is not None and any(low <= elevation <= high for low, high in windows)


def _section_stations(payload: Any) -> tuple[list[str], list[float]]:
    if not isinstance(payload, Mapping):
        return [], []
    names = payload.get("section_names")
    stations = payload.get("section_stations_m")
    if not isinstance(names, Sequence) or not isinstance(stations, Sequence):
        return [], []
    if isinstance(names, (str, bytes)) or len(names) != len(stations):
        return [], []
    pairs = []
    for name, station in zip(names, stations):
        value = _finite(station)
        if value is None or name is None or str(name) == "":
            continue
        pairs.append((value, str(name)))
    pairs.sort(key=lambda pair: pair[0])
    return [name for _station, name in pairs], [station for station, _name in pairs]


def _location(names: list[str], stations: list[float], station: Optional[float]) -> Optional[str]:
    if station is None or not names:
        return None
    for name, value in zip(names, stations):
        if abs(value - station) <= _STATION_MATCH_TOL_M:
            return name
    if len(names) < 2 or station < stations[0] or station > stations[-1]:
        return None
    index = int(np.searchsorted(np.asarray(stations), station, side="right"))
    index = min(max(index, 1), len(names) - 1)
    return f"entre {names[index - 1]} y {names[index]}"


def _extreme(cell: Mapping, names: list[str], stations: list[float]) -> dict:
    station = _finite(cell.get("station_m"))
    return {
        "deviation_m": float(cell["deviation_m"]),
        "station_m": station,
        "elevation": _finite(cell.get("elevation_m")),
        "location": _location(names, stations, station),
    }


def heatmap_summary(
    payload: Optional[Mapping],
    *,
    level_window: Optional[tuple[float, float]] = None,
) -> HeatmapSummary:
    """Summarise the payload cells, restricted to ``level_window`` when given.

    Section names for ``location`` come from the optional payload keys
    ``section_names`` / ``section_stations_m`` (stations in the same origin as
    the cells' ``station_m``); without them ``location`` stays ``None``.
    """
    window = _normalize_window(level_window)
    names, stations = _section_stations(payload)
    counts = {key: 0 for key in HDEV_CATEGORY_ORDER}
    measured: list[Mapping] = []
    n_cells = 0
    for cell in _cells(payload):
        if not _in_window(cell, window):
            continue
        n_cells += 1
        counts[_cell_category(cell)] += 1
        if _finite(cell.get("deviation_m")) is not None:
            measured.append(cell)

    if not measured:
        return HeatmapSummary(n_cells, 0, counts, None, None, None, None, None, window)

    values = np.asarray([float(cell["deviation_m"]) for cell in measured], dtype=float)
    top = int(np.argmax(values))
    bottom = int(np.argmin(values))
    return HeatmapSummary(
        n_cells=n_cells,
        n_measured=len(measured),
        counts=counts,
        pct_within=100.0 * counts["within_tolerance"] / len(measured),
        median_m=float(np.median(values)),
        p95_abs_m=float(np.percentile(np.abs(values), 95)),
        max_over=_extreme(measured[top], names, stations) if values[top] > 0 else None,
        max_under=_extreme(measured[bottom], names, stations) if values[bottom] < 0 else None,
        level_window=window,
        restricted_sections=bool(payload and payload.get("report_station_ranges")),
    )


def _attr(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def level_window_from_geometry(
    section_geometry: Optional[Sequence[Any]],
) -> Optional[tuple[float, float]]:
    """(min toe, max crest) of the design benches of entries that carry a ``view_window``."""
    windows = []
    for entry in section_geometry or ():
        if not isinstance(entry, Mapping) or entry.get("view_window") is None:
            continue
        for bench in _attr(entry.get("params_design"), "benches") or ():
            toe = _finite(_attr(bench, "toe_elevation"))
            crest = _finite(_attr(bench, "crest_elevation"))
            if toe is not None and crest is not None:
                windows.append((min(toe, crest), max(toe, crest)))
    if not windows:
        return None
    merged = []
    for low, high in sorted(windows):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return LevelWindow(merged)


def _fmt(value: float, decimals: int = 2, *, sign: bool = False) -> str:
    text = f"{abs(value):,.{decimals}f}".replace(",", _NBSP).replace(".", ",")
    if value < 0:
        return _MINUS + text
    return ("+" + text) if sign else text



def format_level_window(window: Optional[tuple[float, float]]) -> str:
    """Describe every effective elevation interval, including disjoint windows."""
    if window is None:
        return "todo el muro"
    windows = window.windows if isinstance(window, LevelWindow) else (window,)
    intervals = " y ".join(f"{_fmt(low, 0)}–{_fmt(high, 0)}" for low, high in windows)
    return f"{'ventanas' if len(windows) > 1 else 'ventana'} {intervals} m"

def _positive(value: Any, fallback: float) -> float:
    number = _finite(value)
    return number if number is not None and number > 0 else fallback


def _cell_boxes(
    cells: list[Mapping], longitudinal_step: float, vertical_step: float
) -> list[Optional[tuple[float, float, float, float]]]:
    """Rebuild each cell rectangle from the cell centres of its (bench, station) column.

    The payload carries only centres: cells stack from the design toe in vertical
    slices and the last slice of a column may be thinner.
    """
    half = longitudinal_step / 2.0
    columns: dict[tuple, list[int]] = {}
    for index, cell in enumerate(cells):
        station = _finite(cell.get("station_m"))
        elevation = _finite(cell.get("elevation_m"))
        if station is None or elevation is None:
            continue
        columns.setdefault((cell.get("bench_num"), round(station, 4)), []).append(index)

    boxes: list[Optional[tuple[float, float, float, float]]] = [None] * len(cells)
    for indices in columns.values():
        indices.sort(key=lambda i: float(cells[i]["elevation_m"]))
        centres = [float(cells[i]["elevation_m"]) for i in indices]
        if len(centres) == 1:
            edges = [centres[0] - vertical_step / 2.0, centres[0] + vertical_step / 2.0]
        else:
            diffs = np.diff(centres)
            step = float(diffs[0]) if len(diffs) == 1 else float(np.median(diffs[:-1]))
            if step <= 0:
                step = vertical_step
            low = centres[0] - step / 2.0
            edges = [low + step * k for k in range(len(centres))]
            last = 2.0 * centres[-1] - edges[-1]
            edges.append(last if last > edges[-1] else edges[-1] + step)
        for k, index in enumerate(indices):
            station = float(cells[index]["station_m"])
            boxes[index] = (station - half, station + half, edges[k], edges[k + 1])
    return boxes


def _polygons(boxes: Sequence[tuple[float, float, float, float]]) -> list:
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)] for x0, x1, y0, y1 in boxes]


def _dim(color: str) -> tuple[float, float, float]:
    r, g, b = to_rgb(color)
    k = _CONTEXT_BLEND
    return (r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k)


def _add_cells(ax, boxes, colors, gid: str, zorder: float) -> None:
    if not boxes:
        return
    collection = PolyCollection(
        _polygons(boxes), facecolors=colors, edgecolors=colors, linewidths=0.15, zorder=zorder
    )
    collection.set_gid(gid)
    ax.add_collection(collection)


def _spaced_label_indices(
    names: list[str], stations: list[float], points_per_unit: float
) -> list[int]:
    kept: list[int] = []
    last_right = -math.inf
    for index, (name, station) in enumerate(zip(names, stations)):
        half = (len(name) * _SECTION_LABEL_FONTSIZE * 0.62 + 6.0) / 2.0
        centre = station * points_per_unit
        if centre - half >= last_right:
            kept.append(index)
            last_right = centre + half
    return kept


def _nice_step(span: float, target: int) -> float:
    if span <= 0:
        return 1.0
    raw = span / max(target, 1)
    power = 10.0 ** math.floor(math.log10(raw))
    for factor in (1.0, 2.0, 5.0, 10.0):
        if raw <= factor * power:
            return factor * power
    return 10.0 * power


def _mark_extreme(ax, extreme: Optional[dict], marker: str, gid: str, x_mid: float) -> bool:
    if not extreme or extreme.get("station_m") is None or extreme.get("elevation") is None:
        return False
    x, y = extreme["station_m"], extreme["elevation"]
    (line,) = ax.plot(
        [x], [y], marker=marker, ms=8.0, mfc="#FFFFFF", mec=_INK, mew=1.2, ls="none", zorder=7
    )
    line.set_gid(gid)
    to_left = x > x_mid
    label = ax.annotate(
        f"{_fmt(extreme['deviation_m'], 2, sign=True)} m",
        xy=(x, y),
        xytext=(-7 if to_left else 7, 0),
        textcoords="offset points",
        ha="right" if to_left else "left",
        va="center",
        fontsize=7.0,
        fontweight="bold",
        color=_INK,
        zorder=8,
        bbox=dict(boxstyle="round,pad=0.2", fc="#FFFFFF", ec=_INK, lw=0.5, alpha=0.92),
    )
    label.set_gid(f"{gid}-label")
    return True


@_cleanup_failed_figures
def _build_heatmap_figure(
    payload: Optional[Mapping],
    *,
    level_window: Optional[tuple[float, float]] = None,
    title: str = "",
    width_in: float = 10.5,
    height_in: float = 5.2,
):
    cells = _cells(payload)
    resolution = payload.get("resolution") if isinstance(payload, Mapping) else None
    resolution = resolution if isinstance(resolution, Mapping) else {}
    longitudinal_step = _positive(resolution.get("longitudinal_step"), 1.0)
    vertical_step = _positive(resolution.get("vertical_step"), 1.0)
    all_boxes = _cell_boxes(cells, longitudinal_step, vertical_step)
    drawable = [index for index, box in enumerate(all_boxes) if box is not None]
    if not drawable:
        return None

    window = _normalize_window(level_window)
    summary = heatmap_summary(payload, level_window=window)
    if window is not None and summary.n_cells == 0:
        return None
    names, stations = _section_stations(payload)

    groups: dict[str, tuple[list, list]] = {
        "hdev-cells-context": ([], []),
        "hdev-cells-unmeasured": ([], []),
        "hdev-cells-measured": ([], []),
    }
    for index in drawable:
        cell = cells[index]
        category = _cell_category(cell)
        if not _in_window(cell, window):
            gid, color = "hdev-cells-context", _dim(HDEV_COLORS[category])
        elif category == _UNMEASURED:
            gid, color = "hdev-cells-unmeasured", HDEV_COLORS[category]
        else:
            gid, color = "hdev-cells-measured", HDEV_COLORS[category]
        groups[gid][0].append(all_boxes[index])
        groups[gid][1].append(color)

    top_in = _MARGIN_TOP_IN + (_TITLE_EXTRA_IN if title else 0.0)
    ax_w_in = max(width_in - _MARGIN_LEFT_IN - _LEGEND_WIDTH_IN, width_in * 0.3)
    ax_h_in = max(height_in - _MARGIN_BOTTOM_IN - top_in, height_in * 0.3)
    fig = _new_figure(figsize=(width_in, height_in))
    ax = fig.add_axes(
        [
            _MARGIN_LEFT_IN / width_in,
            _MARGIN_BOTTOM_IN / height_in,
            ax_w_in / width_in,
            ax_h_in / height_in,
        ]
    )

    _add_cells(ax, *groups["hdev-cells-context"], "hdev-cells-context", 1.5)
    _add_cells(ax, *groups["hdev-cells-unmeasured"], "hdev-cells-unmeasured", 2.0)
    _add_cells(ax, *groups["hdev-cells-measured"], "hdev-cells-measured", 2.5)

    boxes = [all_boxes[index] for index in drawable]
    x_low = min(box[0] for box in boxes)
    x_high = max(box[1] for box in boxes)
    y_low = min(box[2] for box in boxes)
    y_high = max(box[3] for box in boxes)
    if stations and not payload.get("report_station_ranges"):
        x_low, x_high = min(x_low, stations[0]), max(x_high, stations[-1])
    x_pad = max((x_high - x_low) * 0.01, longitudinal_step * 0.25)
    y_pad = max((y_high - y_low) * 0.03, vertical_step * 0.5)
    ax.set_xlim(x_low - x_pad, x_high + x_pad)
    ax.set_ylim(y_low - y_pad, y_high + y_pad)

    if window is not None:
        inside = groups["hdev-cells-measured"][0] + groups["hdev-cells-unmeasured"][0]
        band_x0 = min((box[0] for box in inside), default=x_low)
        band_x1 = max((box[1] for box in inside), default=x_high)
        for low, high in (window.windows if isinstance(window, LevelWindow) else (window,)):
            outline = Rectangle(
                (band_x0, low), band_x1 - band_x0, high - low,
                facecolor="none", edgecolor=_INK, linewidth=1.3, zorder=5,
            )
            outline.set_gid("hdev-level-window")
            ax.add_patch(outline)

    x_mid = (x_low + x_high) / 2.0
    has_over = _mark_extreme(ax, summary.max_over, "^", "hdev-max-over", x_mid)
    has_under = _mark_extreme(ax, summary.max_under, "v", "hdev-max-under", x_mid)

    ax.set_xlabel("Estación a lo largo de la pared (m)", fontsize=8.0, labelpad=3)
    ax.set_ylabel("Elevación (m)", fontsize=8.0, labelpad=3)
    ax.tick_params(labelsize=7.0)
    x_step = _nice_step(x_high - x_low, 10)
    ax.set_xticks(np.arange(math.ceil(x_low / x_step) * x_step, x_high + x_step * 1e-6, x_step))
    y_step = _nice_step(y_high - y_low, 8)
    ax.set_yticks(np.arange(math.ceil(y_low / y_step) * y_step, y_high + y_step * 1e-6, y_step))
    y_decimals = 0 if y_step >= 1 else 1
    ax.xaxis.set_major_formatter(lambda value, _pos: _fmt(value, 0))
    ax.yaxis.set_major_formatter(lambda value, _pos: _fmt(value, y_decimals))
    ax.grid(axis="y", color=_GRID, linewidth=0.4, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_color("#9CA3AF")

    if names:
        x0, x1 = ax.get_xlim()
        points_per_unit = ax_w_in * 72.0 / (x1 - x0)
        labelled = _spaced_label_indices(names, stations, points_per_unit)
        secondary = ax.secondary_xaxis("top")
        secondary.set_gid("hdev-section-axis")
        secondary.set_xticks([stations[i] for i in labelled])
        secondary.set_xticklabels([names[i] for i in labelled], fontsize=_SECTION_LABEL_FONTSIZE)
        secondary.set_xticks(stations, minor=True)
        secondary.tick_params(which="major", length=4, pad=1.5)
        secondary.tick_params(which="minor", length=2)
        secondary.set_xlabel(
            "Secciones (marca menor = cada sección)", fontsize=6.5, labelpad=3, color=_GREY
        )
        for i in labelled:
            ax.axvline(
                stations[i], color=_SECTION_LINE, linewidth=0.35, linestyle=(0, (2, 3)), zorder=4
            )

    handles: list = [
        Patch(facecolor=HDEV_COLORS[key], edgecolor="#FFFFFF", linewidth=0.5, label=HDEV_LABELS_ES[key])
        for key in _LEGEND_ORDER
    ]
    if window is not None:
        handles.append(
            Patch(
                facecolor="none",
                edgecolor=_INK,
                linewidth=1.3,
                label=format_level_window(window).capitalize(),
            )
        )
        if groups["hdev-cells-context"][0]:
            handles.append(
                Patch(
                    facecolor=_dim(HDEV_COLORS["overbreak_moderate"]),
                    edgecolor="none",
                    label="Atenuado: fuera de la cota",
                )
            )
    marker_style = dict(color="none", ms=6.5, mfc="#FFFFFF", mec=_INK, mew=1.0, ls="none")
    if has_over:
        handles.append(Line2D([], [], marker="^", label="Máx. sobreexcavación (+)", **marker_style))
    if has_under:
        handles.append(Line2D([], [], marker="v", label="Máx. faltante (−)", **marker_style))
    legend = ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(1.0 + 0.12 / ax_w_in, 1.0),
        borderaxespad=0.0,
        frameon=False,
        fontsize=7.0,
        title="Desviación horizontal",
        title_fontsize=7.5,
        handlelength=1.4,
        handleheight=1.2,
        labelspacing=0.55,
        alignment="left",
    )
    legend.get_title().set_fontweight("bold")

    if title:
        fig.text(
            _MARGIN_LEFT_IN / width_in,
            1.0 - 0.08 / height_in,
            title,
            fontsize=10.0,
            fontweight="bold",
            color=_INK,
            ha="left",
            va="top",
        )
    return fig


@_serialized_render
@_cleanup_failed_figures
def heatmap_page_png(
    payload: Optional[Mapping],
    *,
    level_window: Optional[tuple[float, float]] = None,
    title: str = "",
    width_in: float = 10.5,
    height_in: float = 5.2,
    dpi: int = 150,
) -> Optional[bytes]:
    """Developed wall view (station x elevation) of the horizontal deviation as PNG bytes."""
    fig = _build_heatmap_figure(
        payload,
        level_window=level_window,
        title=title,
        width_in=width_in,
        height_in=height_in,
    )
    if fig is None:
        return None
    return _fig_to_png(fig, dpi)
