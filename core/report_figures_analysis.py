"""Analysis charts for the redesigned web reports (contract C7).

Four pure functions returning in-memory PNG bytes built from the aggregates of
``core.report_data.ReportData``: the section x nominal-level status matrix,
the deviation histograms with their tolerance band, the mean deviation trend
along the wall and the over/under-excavation volume bars. Each one returns
``None`` when there is nothing to draw, and a missing value is never drawn as
zero.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence

from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

from core.report_charts import (
    STATUS_COLORS,
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_LABELS_ES,
    STATUS_NO_CUMPLE,
    STATUS_UNKNOWN,
    _cleanup_failed_figures,
    _fig_to_png,
    _new_figure,
    _nice_number,
    _serialized_render,
)

OVER_COLOR = "#3b82f6"
UNDER_COLOR = "#f97316"
MISSING_FILL = "#E5E7EB"
EXTRA_COLOR = "#7E3F98"

MISSING_LABEL_ES = "No construido"
EXTRA_LABEL_ES = "Banco adicional"
NO_DATA_TEXT = "sin datos"
DASH = "\u2014"

_MISSING_HATCH = "////"
_MISSING_EDGE = "#6B7280"
_SERIES_COLOR = "#2C5B8A"
_BAND_COLOR = "#D6E4F2"
_GRID_COLOR = "#E5E7EB"
_TEXT_DARK = "#1F2937"
_TEXT_MUTED = "#6B7280"
_THIN_SPACE = "\u202f"
_MINUS = "\u2212"

_STATUS_ORDER = (STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE, STATUS_UNKNOWN)
_SEVERITY = {STATUS_UNKNOWN: 0, STATUS_CUMPLE: 1, STATUS_FUERA: 2, STATUS_NO_CUMPLE: 3}
_STATUS_ALIASES = {
    "CUMPLE": STATUS_CUMPLE,
    "FUERA": STATUS_FUERA,
    "FUERA DE TOLERANCIA": STATUS_FUERA,
    "NO CUMPLE": STATUS_NO_CUMPLE,
    "NO_CUMPLE": STATUS_NO_CUMPLE,
}

_HISTOGRAM_PANELS = (
    ("height", "Altura", "m", "bench_height"),
    ("angle", "\u00c1ngulo", "\u00b0", "face_angle"),
    ("berm", "Berma", "m", "berm_width"),
)
_TREND_PANELS = (
    ("height_dev_mean", "trend-height", "Altura", "m", "bench_height"),
    ("angle_dev_mean", "trend-angle", "\u00c1ngulo de cara", "\u00b0", "face_angle"),
)

_TICK_FONTSIZE = 6.5
_LABEL_FONTSIZE = 7.0
_TITLE_FONTSIZE = 8.0
_LEFT_IN = 0.62
_RIGHT_IN = 0.08
_TARGET_BINS = 20


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _field(entry: Any, name: str) -> Any:
    if isinstance(entry, Mapping):
        return entry.get(name)
    return getattr(entry, name, None)


def _status_key(raw: Any) -> str:
    if raw is None:
        return STATUS_UNKNOWN
    return _STATUS_ALIASES.get(str(raw).strip().upper(), STATUS_UNKNOWN)


def _decimal(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _thousands(value: float) -> str:
    return f"{int(round(abs(value))):,}".replace(",", _THIN_SPACE)


def _signed_band(tolerance: Any) -> Optional[tuple[float, float]]:
    """``(low, high)`` of a signed deviation tolerance, or ``None``.

    Only ``neg``/``pos`` tolerances describe a deviation band; a ``min`` or
    ``max`` criterion (berm width) is an absolute limit and has no band on a
    real - design axis.
    """
    if not isinstance(tolerance, Mapping):
        return None
    neg = _finite(tolerance.get("neg"))
    pos = _finite(tolerance.get("pos"))
    if neg is None and pos is None:
        return None
    low = abs(neg if neg is not None else pos or 0.0)
    high = abs(pos if pos is not None else neg or 0.0)
    if low <= 0 and high <= 0:
        return None
    return -low, high


def _band_text(band: tuple[float, float], unit: str) -> str:
    low, high = band
    if abs(abs(low) - high) < 1e-9:
        return f"Tol. \u00b1{_decimal(high)} {unit}"
    return f"Tol. {_MINUS}{_decimal(abs(low))} / +{_decimal(high)} {unit}"


def _limit_text(tolerance: Any, unit: str) -> Optional[str]:
    if not isinstance(tolerance, Mapping):
        return None
    minimum = _finite(tolerance.get("min"))
    if minimum is not None:
        return f"Sin banda: criterio\noficial = m\u00edn. {_decimal(minimum)} {unit}"
    maximum = _finite(tolerance.get("max"))
    if maximum is not None:
        return f"Sin banda: criterio\noficial = m\u00e1x. {_decimal(maximum)} {unit}"
    return None


def _spaced_positions(labels: Sequence[str], axis_width_in: float, fontsize: float) -> list[int]:
    """Indices of the labels to print so neighbours never overlap.

    The first and the last label are always kept; the step is the smallest
    one whose labels fit side by side in the axis width.
    """
    n = len(labels)
    if n == 0:
        return []
    longest = max(len(label) for label in labels)
    label_in = (longest * 0.66 + 1.2) * fontsize / 72.0
    step = max(1, math.ceil(n * label_in / max(axis_width_in, 0.1)))
    positions = list(range(0, n, step))
    if positions[-1] != n - 1:
        if len(positions) > 1:
            positions[-1] = n - 1
        elif (n - 1) * axis_width_in / n >= label_in:
            positions.append(n - 1)
    return positions


def _apply_section_ticks(ax, labels: Sequence[str], axis_width_in: float) -> None:
    positions = _spaced_positions(labels, axis_width_in, _TICK_FONTSIZE)
    ax.set_xticks(positions)
    ax.set_xticklabels([labels[index] for index in positions], fontsize=_TICK_FONTSIZE)
    ax.tick_params(axis="x", length=2.5, pad=1.5, colors=_TEXT_DARK)


def _place_axes(fig, width_in: float, height_in: float, *, bottom_in: float, top_in: float,
                left_in: float = _LEFT_IN, right_in: float = _RIGHT_IN) -> float:
    fig.subplots_adjust(
        left=left_in / width_in,
        right=1.0 - right_in / width_in,
        bottom=bottom_in / height_in,
        top=1.0 - top_in / height_in,
    )
    return width_in - left_in - right_in


def _style_axis(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#9CA3AF")
        ax.spines[side].set_linewidth(0.6)
    ax.tick_params(axis="y", labelsize=_TICK_FONTSIZE, length=2.5, colors=_TEXT_DARK)
    ax.tick_params(axis="x", labelsize=_TICK_FONTSIZE, colors=_TEXT_DARK)


def _sector_runs(sectors: Sequence[str]) -> list[tuple[str, int, int]]:
    runs: list[tuple[str, int, int]] = []
    for index, sector in enumerate(sectors):
        if runs and runs[-1][0] == sector:
            runs[-1] = (sector, runs[-1][1], index)
        else:
            runs.append((sector, index, index))
    return runs


def _draw_sector_boundaries(ax, sectors: Sequence[str]) -> list[tuple[str, int, int]]:
    runs = _sector_runs(sectors)
    if len(runs) < 2:
        return []
    for _sector, start, _end in runs[1:]:
        ax.axvline(start - 0.5, color="#374151", linewidth=0.8, zorder=4, gid="sector-boundary")
    return runs


def _level_order(labels: Sequence[Optional[str]]) -> list[Optional[str]]:
    numeric: list[tuple[float, str]] = []
    other: list[str] = []
    has_none = False
    for label in dict.fromkeys(labels):
        if label is None:
            has_none = True
            continue
        value = _finite(label)
        if value is None:
            other.append(label)
        else:
            numeric.append((value, label))
    ordered: list[Optional[str]] = [label for _value, label in sorted(numeric, reverse=True)]
    ordered.extend(sorted(other))
    if has_none:
        ordered.append(None)
    return ordered


def _level_key(raw: Any) -> Optional[str]:
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip()


@_cleanup_failed_figures
def _build_status_matrix_figure(matrix, *, width_in: float, height_in: float):
    rows = [row for row in (matrix or ()) if isinstance(row, Mapping)]
    if not rows:
        return None

    identities = list(dict.fromkeys(
        (str(row.get("section", "")), str(row.get("sector") or "")) for row in rows))
    column = {identity: index for index, identity in enumerate(identities)}
    levels = _level_order([_level_key(row.get("level_nominal")) for row in rows])
    line = {level: index for index, level in enumerate(levels)}

    cells: dict[tuple[int, int], dict] = {}
    extras: list[tuple[int, int]] = []
    counts = {status: 0 for status in _STATUS_ORDER}
    n_missing = n_extra = 0
    for row in rows:
        identity = (str(row.get("section", "")), str(row.get("sector") or ""))
        position = (column[identity], line[_level_key(row.get("level_nominal"))])
        row_type = row.get("type")
        if row_type == "EXTRA":
            n_extra += 1
            extras.append(position)
            continue
        if row_type == "MISSING":
            n_missing += 1
            cells.setdefault(position, {"missing": True, "status": None})
            continue
        status = _status_key(row.get("worst_status"))
        counts[status] += 1
        current = cells.get(position)
        if current is None or current["missing"] or _SEVERITY[status] > _SEVERITY[current["status"]]:
            cells[position] = {"missing": False, "status": status}

    n_cols, n_rows = len(identities), len(levels)
    sectors = [sector for _name, sector in identities]
    multi_sector = len(_sector_runs(sectors)) > 1
    bottom_in, top_in = 0.66, 0.26 if multi_sector else 0.08
    fig_h = min(height_in, bottom_in + top_in + max(0.42 * n_rows, 0.5))
    fig = _new_figure(figsize=(width_in, fig_h))
    ax = fig.subplots()
    axis_w = _place_axes(fig, width_in, fig_h, bottom_in=bottom_in, top_in=top_in)

    dense = axis_w / n_cols < 0.16
    pad_x = 0.0 if dense else 0.04
    pad_y = 0.05
    names = [name for name, _sector in identities]
    for (col, row_index), cell in cells.items():
        level = levels[row_index]
        patch = Rectangle(
            (col - 0.5 + pad_x, row_index - 0.5 + pad_y), 1 - 2 * pad_x, 1 - 2 * pad_y,
            linewidth=0, zorder=2, antialiased=not dense,
            gid=f"cell|{names[col]}|{DASH if level is None else level}",
        )
        if cell["missing"]:
            patch.set_facecolor(MISSING_FILL)
            patch.set_edgecolor(_MISSING_EDGE)
            patch.set_hatch(_MISSING_HATCH)
            if hasattr(patch, "set_hatch_linewidth"):
                patch.set_hatch_linewidth(0.4)
        else:
            patch.set_facecolor(STATUS_COLORS[cell["status"]])
            patch.set_edgecolor("none")
        ax.add_patch(patch)

    if dense:
        ax.vlines(np.arange(1, n_cols) - 0.5, -0.5, n_rows - 0.5, colors="white",
                  linewidth=0.5, zorder=3, snap=True, gid="cell-separator")

    cell_pt = min(axis_w / n_cols, (fig_h - bottom_in - top_in) / n_rows) * 72.0
    marker_size = float(min(6.0, max(2.6, cell_pt * 0.62)))
    for col, row_index in dict.fromkeys(extras):
        if (col, row_index) not in cells:
            ax.add_patch(Rectangle(
                (col - 0.5 + pad_x, row_index - 0.5 + pad_y), 1 - 2 * pad_x, 1 - 2 * pad_y,
                facecolor="white", edgecolor=EXTRA_COLOR, linewidth=0.5, zorder=2,
                gid="extra-cell",
            ))
        ax.plot(
            [float(col)], [float(row_index)], linestyle="none", marker="D",
            markersize=marker_size, markerfacecolor=EXTRA_COLOR,
            markeredgecolor="white", markeredgewidth=0.5, zorder=5, gid="extra-marker",
        )

    ax.set_xlim(-0.5, n_cols - 0.5)
    ax.set_ylim(n_rows - 0.5, -0.5)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([DASH if level is None else level for level in levels],
                       fontsize=_LABEL_FONTSIZE)
    ax.set_ylabel("Cota nominal", fontsize=_LABEL_FONTSIZE, color=_TEXT_DARK)
    ax.set_xlabel("Secci\u00f3n, en el orden definido", fontsize=_LABEL_FONTSIZE,
                  color=_TEXT_DARK, labelpad=2)
    _apply_section_ticks(ax, names, axis_w)
    ax.tick_params(axis="y", length=0, colors=_TEXT_DARK)
    ax.set_facecolor("#F9FAFB")
    for spine in ax.spines.values():
        spine.set_visible(False)

    for sector, start, end in _draw_sector_boundaries(ax, sectors):
        ax.text((start + end) / 2.0, -0.5, sector or "Sin sector", ha="center", va="bottom",
                fontsize=_LABEL_FONTSIZE, fontweight="bold", color=_TEXT_DARK,
                gid="sector-label")

    handles: list[Any] = [
        Patch(facecolor=STATUS_COLORS[status], edgecolor="none",
              label=f"{STATUS_LABELS_ES[status]} ({counts[status]})")
        for status in _STATUS_ORDER if counts[status]
    ]
    if n_missing:
        handles.append(Patch(facecolor=MISSING_FILL, edgecolor=_MISSING_EDGE, linewidth=0.4,
                             hatch=_MISSING_HATCH, label=f"{MISSING_LABEL_ES} ({n_missing})"))
    if n_extra:
        handles.append(Line2D([], [], linestyle="none", marker="D", markersize=4.5,
                              markerfacecolor=EXTRA_COLOR, markeredgecolor="white",
                              markeredgewidth=0.5, label=f"{EXTRA_LABEL_ES} ({n_extra})"))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False,
               fontsize=_TICK_FONTSIZE, handlelength=1.3, handleheight=0.9,
               columnspacing=1.4, borderaxespad=0.1)
    return fig


def _clean_values(values: Any) -> np.ndarray:
    cleaned = [_finite(value) for value in (values or ())]
    return np.asarray([value for value in cleaned if value is not None], dtype=float)


def _mark_no_data(ax, *, hide_axes: bool) -> None:
    ax.text(0.5, 0.5, NO_DATA_TEXT, transform=ax.transAxes, ha="center", va="center",
            fontsize=_TITLE_FONTSIZE, color=_TEXT_MUTED, style="italic")
    if hide_axes:
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_facecolor("#F9FAFB")


def _histogram_edges(values: np.ndarray, band: Optional[tuple[float, float]]) -> np.ndarray:
    low, high = float(values.min()), float(values.max())
    if band is not None:
        low, high = min(low, band[0]), max(high, band[1])
    low, high = min(low, 0.0), max(high, 0.0)
    if high - low < 1e-9:
        low, high = low - 0.5, high + 0.5
    width = _nice_number((high - low) / _TARGET_BINS)
    first = math.floor(low / width + 1e-9) * width
    count = max(1, math.ceil((high - first) / width - 1e-9))
    if first + count * width <= high:
        count += 1
    return first + width * np.arange(count + 1)


@_cleanup_failed_figures
def _build_deviation_histograms_figure(deviations, tolerances, *, width_in: float,
                                       height_in: float):
    deviations = deviations if isinstance(deviations, Mapping) else {}
    tolerances = tolerances if isinstance(tolerances, Mapping) else {}
    series = {key: _clean_values(deviations.get(key)) for key, *_rest in _HISTOGRAM_PANELS}
    if not any(len(values) for values in series.values()):
        return None

    fig = _new_figure(figsize=(width_in, height_in))
    axes = fig.subplots(1, len(_HISTOGRAM_PANELS))
    _place_axes(fig, width_in, height_in, bottom_in=0.42, top_in=0.26, left_in=0.46)
    fig.subplots_adjust(wspace=0.22)

    for index, (ax, (key, label, unit, tol_key)) in enumerate(zip(axes, _HISTOGRAM_PANELS)):
        values = series[key]
        ax.set_title(f"{label} ({unit}) \u00b7 n = {len(values)}", fontsize=_TITLE_FONTSIZE,
                     fontweight="bold", color=_TEXT_DARK, loc="left", pad=4)
        if len(values) == 0:
            _mark_no_data(ax, hide_axes=True)
            continue
        tolerance = tolerances.get(tol_key)
        band = _signed_band(tolerance)
        edges = _histogram_edges(values, band)
        counts, _edges = np.histogram(values, bins=edges)
        width = float(edges[1] - edges[0])
        filled = counts > 0
        ax.bar((edges[:-1] + width / 2.0)[filled], counts[filled], width=width * 0.92,
               color=_SERIES_COLOR, linewidth=0, zorder=3, gid="hist-bar")
        if band is not None:
            ax.axvspan(band[0], band[1], facecolor=_BAND_COLOR, edgecolor="none",
                       zorder=1, gid="tol-band")
            note = _band_text(band, unit)
        else:
            note = _limit_text(tolerance, unit)
        ax.axvline(0.0, color="#374151", linewidth=0.7, linestyle=":", zorder=4)
        margin = width * 0.6
        ax.set_xlim(float(edges[0]) - margin, float(edges[-1]) + margin)
        ax.set_ylim(0, float(counts.max()) * 1.28)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
        ax.set_xlabel(f"\u0394 real {_MINUS} dise\u00f1o ({unit})", fontsize=_LABEL_FONTSIZE,
                      color=_TEXT_DARK, labelpad=2)
        if index == 0:
            ax.set_ylabel("N.\u00ba de bancos", fontsize=_LABEL_FONTSIZE, color=_TEXT_DARK)
        ax.grid(axis="y", color=_GRID_COLOR, linewidth=0.5, zorder=0)
        ax.set_axisbelow(True)
        _style_axis(ax)
        if note:
            ax.text(0.03, 0.97, note, transform=ax.transAxes, ha="left", va="top",
                    fontsize=6.0, color=_TEXT_DARK, zorder=6,
                    bbox={"boxstyle": "round,pad=0.25", "facecolor": "white",
                          "edgecolor": "#D1D5DB", "linewidth": 0.4, "alpha": 0.9})
    return fig


@_cleanup_failed_figures
def _build_trend_figure(trend, tolerances, *, width_in: float, height_in: float):
    rows = [row for row in (trend or ()) if isinstance(row, Mapping)]
    tolerances = tolerances if isinstance(tolerances, Mapping) else {}
    series = {}
    for key, *_rest in _TREND_PANELS:
        values = [_finite(row.get(key)) for row in rows]
        series[key] = np.asarray(
            [math.nan if value is None else value for value in values], dtype=float)
    if not rows or not any(np.isfinite(values).any() for values in series.values()):
        return None

    names = [str(row.get("section", "")) for row in rows]
    sectors = [str(row.get("sector") or "") for row in rows]
    x = list(range(len(rows)))
    fig = _new_figure(figsize=(width_in, height_in))
    axes = fig.subplots(len(_TREND_PANELS), 1, sharex=True)
    multi_sector = len(_sector_runs(sectors)) > 1
    axis_w = _place_axes(fig, width_in, height_in, bottom_in=0.40,
                         top_in=0.40 if multi_sector else 0.24)
    fig.subplots_adjust(hspace=0.42)

    for ax, (key, gid, label, unit, tol_key) in zip(axes, _TREND_PANELS):
        values = series[key]
        band = _signed_band(tolerances.get(tol_key))
        title = f"{label}: \u0394 media por secci\u00f3n ({unit})"
        if band is not None:
            ax.axhspan(band[0], band[1], facecolor=_BAND_COLOR, edgecolor="none",
                       zorder=1, gid="tol-band")
            title += f" \u00b7 {_band_text(band, unit).replace('Tol.', 'banda')}"
        ax.set_title(title, fontsize=_LABEL_FONTSIZE, fontweight="bold", color=_TEXT_DARK,
                     loc="left", pad=2)
        ax.axhline(0.0, color="#374151", linewidth=0.6, linestyle=":", zorder=2)
        ax.plot(x, values, color=_SERIES_COLOR, linewidth=0.9, marker="o", markersize=2.2,
                zorder=3, gid=gid)
        finite = values[np.isfinite(values)]
        bounds = [0.0] + (list(band) if band else []) + [float(v) for v in finite]
        low, high = min(bounds), max(bounds)
        span = max(high - low, 1e-6)
        ax.set_ylim(low - 0.12 * span, high + 0.12 * span)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.set_ylabel(f"\u0394 ({unit})", fontsize=_LABEL_FONTSIZE, color=_TEXT_DARK)
        ax.grid(axis="y", color=_GRID_COLOR, linewidth=0.5, zorder=0)
        ax.set_axisbelow(True)
        _style_axis(ax)
        _draw_sector_boundaries(ax, sectors)
        if len(finite) == 0:
            _mark_no_data(ax, hide_axes=False)

    for sector, start, end in (_sector_runs(sectors) if multi_sector else ()):
        axes[0].annotate(sector or "Sin sector", xy=((start + end) / 2.0, 1.0),
                         xycoords=("data", "axes fraction"), xytext=(0, 13),
                         textcoords="offset points", ha="center", va="bottom",
                         fontsize=_LABEL_FONTSIZE, fontweight="bold", color=_TEXT_DARK)

    axes[-1].set_xlim(-0.6, len(rows) - 0.4)
    _apply_section_ticks(axes[-1], names, axis_w)
    axes[-1].set_xlabel("Secci\u00f3n, en el orden definido", fontsize=_LABEL_FONTSIZE,
                        color=_TEXT_DARK, labelpad=2)
    return fig


def _volume_total(values: Sequence[Optional[float]]) -> str:
    present = [value for value in values if value is not None]
    if not present:
        return DASH
    return f"{_thousands(math.fsum(present))} m\u00b3"


@_cleanup_failed_figures
def _build_excavation_bars_figure(excavation, *, width_in: float, height_in: float):
    entries = [entry for entry in (excavation or ()) if entry is not None]
    over = [_finite(_field(entry, "volume_over_m3")) for entry in entries]
    under = [_finite(_field(entry, "volume_under_m3")) for entry in entries]
    if not any(value is not None for value in over + under):
        return None

    names = [str(_field(entry, "section") or "") for entry in entries]
    sectors = [str(_field(entry, "sector") or "") for entry in entries]
    n_without = sum(1 for a, b in zip(over, under) if a is None or b is None)

    fig = _new_figure(figsize=(width_in, height_in))
    ax = fig.subplots()
    axis_w = _place_axes(fig, width_in, height_in, bottom_in=0.40, top_in=0.26)

    over_bars = [(index, value) for index, value in enumerate(over) if value is not None]
    under_bars = [(index, value) for index, value in enumerate(under) if value is not None]
    if over_bars:
        ax.bar([index for index, _value in over_bars], [value for _index, value in over_bars],
               width=0.78, color=OVER_COLOR, linewidth=0, zorder=3, gid="over-bar")
    if under_bars:
        ax.bar([index for index, _value in under_bars], [-value for _index, value in under_bars],
               width=0.78, color=UNDER_COLOR, linewidth=0, zorder=3, gid="under-bar")
    ax.axhline(0.0, color="#374151", linewidth=0.7, zorder=4)

    top = max([value for _index, value in over_bars], default=0.0)
    bottom = max([value for _index, value in under_bars], default=0.0)
    reach = max(top, bottom, 1e-6)
    ax.set_ylim(-max(bottom, 0.12 * reach) * 1.18, max(top, 0.12 * reach) * 1.30)

    for index, (a, b) in enumerate(zip(over, under)):
        if a is None or b is None:
            ax.text(index, 0.0, DASH, ha="center", va="center", fontsize=_LABEL_FONTSIZE,
                    fontweight="bold", color=_TEXT_MUTED, zorder=6, gid="no-volume",
                    bbox={"boxstyle": "square,pad=0.05", "facecolor": "white",
                          "edgecolor": "none"})

    title = (f"Volumen estimado por secci\u00f3n \u00b7 sobreexcavaci\u00f3n {_volume_total(over)}"
             f" \u00b7 subexcavaci\u00f3n {_volume_total(under)}")
    if n_without:
        title += f" \u00b7 {n_without} sin volumen"
    ax.set_title(title, fontsize=_TITLE_FONTSIZE, fontweight="bold", color=_TEXT_DARK,
                 loc="left", pad=4)
    ax.set_ylabel("Volumen (m\u00b3)\n\u2190 sub (\u2212) | sobre (+) \u2192",
                  fontsize=_TICK_FONTSIZE, color=_TEXT_DARK)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: _thousands(value)))
    ax.set_xlim(-0.7, len(entries) - 0.3)
    _apply_section_ticks(ax, names, axis_w)
    ax.set_xlabel("Secci\u00f3n, en el orden definido", fontsize=_LABEL_FONTSIZE,
                  color=_TEXT_DARK, labelpad=2)
    ax.grid(axis="y", color=_GRID_COLOR, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    _style_axis(ax)
    _draw_sector_boundaries(ax, sectors)

    handles: list[Any] = [
        Patch(facecolor=OVER_COLOR, edgecolor="none", label="Sobreexcavaci\u00f3n (+)"),
        Patch(facecolor=UNDER_COLOR, edgecolor="none", label="Subexcavaci\u00f3n (\u2212)"),
    ]
    if n_without:
        handles.append(Line2D([], [], linestyle="none", marker="_", markersize=7,
                              markeredgewidth=1.4, color=_TEXT_MUTED,
                              label=f"Sin volumen ({DASH})"))
    ax.legend(handles=handles, loc="upper right", ncol=len(handles), frameon=True,
              framealpha=0.9, edgecolor="#D1D5DB", fontsize=6.0, handlelength=1.2,
              columnspacing=1.2, borderpad=0.3)
    return fig


@_serialized_render
@_cleanup_failed_figures
def status_matrix_png(matrix, *, width_in: float = 7.0, height_in: float = 2.4,
                      dpi: int = 150) -> Optional[bytes]:
    """Section x nominal-level matrix coloured by the official bench status.

    ``matrix`` is ``ReportData.matrix``: columns follow its section order,
    rows are the nominal levels in descending order. Matched benches take
    the colour of ``worst_status``, benches not built are hatched and
    additional benches carry a diamond. Returns ``None`` without rows.
    """
    fig = _build_status_matrix_figure(matrix, width_in=width_in, height_in=height_in)
    if fig is None:
        return None
    return _fig_to_png(fig, dpi)


@_serialized_render
@_cleanup_failed_figures
def deviation_histograms_png(deviations, tolerances, *, width_in: float = 7.0,
                             height_in: float = 2.4, dpi: int = 150) -> Optional[bytes]:
    """Histograms of real - design for height (m), face angle (deg) and berm (m).

    ``deviations`` is ``ReportData.deviations`` and ``tolerances`` the session
    tolerances; a signed tolerance is shaded as a band, a minimum-width
    criterion is stated in the panel. Returns ``None`` when no parameter has
    a finite value.
    """
    fig = _build_deviation_histograms_figure(
        deviations, tolerances, width_in=width_in, height_in=height_in)
    if fig is None:
        return None
    return _fig_to_png(fig, dpi)


@_serialized_render
@_cleanup_failed_figures
def trend_png(trend, tolerances, *, width_in: float = 7.0, height_in: float = 2.4,
              dpi: int = 150) -> Optional[bytes]:
    """Mean height and face-angle deviation per section along the wall.

    ``trend`` is ``ReportData.trend``; a section without a mean leaves a gap
    in the line. Returns ``None`` when no section has a value.
    """
    fig = _build_trend_figure(trend, tolerances, width_in=width_in, height_in=height_in)
    if fig is None:
        return None
    return _fig_to_png(fig, dpi)


@_serialized_render
@_cleanup_failed_figures
def excavation_bars_png(excavation, *, width_in: float = 7.0, height_in: float = 2.4,
                        dpi: int = 150) -> Optional[bytes]:
    """Estimated over (+) and under (-) excavation volume per section, in m3.

    ``excavation`` is ``ReportData.excavation``. A section without a volume is
    marked with a dash and never drawn as zero. Returns ``None`` when no
    section has a volume.
    """
    fig = _build_excavation_bars_figure(excavation, width_in=width_in, height_in=height_in)
    if fig is None:
        return None
    return _fig_to_png(fig, dpi)
