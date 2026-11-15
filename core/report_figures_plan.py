"""Dashboard plan figure: section lines by status over the shaded topography."""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional

import numpy as np
from matplotlib import colormaps
from matplotlib import patheffects
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.transforms import Bbox

from core.report_charts import (
    STATUS_COLORS,
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_LABELS_ES,
    STATUS_NO_CUMPLE,
    STATUS_UNKNOWN,
    _TEXT_DARK,
    _cleanup_failed_figures,
    _fig_to_png,
    _new_figure,
    _serialized_render,
)
from core.report_surface import PlanSurface, Shade, _section_mapping, _section_points

_MARGIN_M = 30.0
_MAJOR_INTERVAL_M = 25.0
_MINOR_INTERVAL_M = 5.0
_CONTOUR_SMOOTH_M = 1.2
_MAJOR_CONTOUR_COLOR = "#4A3A29"
_MINOR_CONTOUR_COLOR = "#6E5A44"
_FRAME_COLOR = "#CBD5E1"
_SHADE_NORM = (-1.2, 1.0)
_LABEL_PAD_PX = 1.5
_STATUS_ALIASES = {
    "FUERA_DE_TOLERANCIA": STATUS_FUERA,
    "NO_CUMPLE": STATUS_NO_CUMPLE,
}
_HIGHLIGHTED = (STATUS_NO_CUMPLE, STATUS_FUERA)
_LEGEND_LOCS = (
    "lower left", "lower right", "upper left", "upper right",
    "lower center", "upper center", "center left", "center right",
)
_FURNITURE_STEPS = 12
_LABEL_TIERS = 4
_LABEL_GAP_PT = 3.0
_LINE_CLEARANCE_PT = 2.5


def _status_key(value: Any) -> str:
    if not isinstance(value, str):
        return STATUS_UNKNOWN
    key = "_".join(value.strip().upper().split())
    key = _STATUS_ALIASES.get(key, key)
    return key if key in STATUS_COLORS else STATUS_UNKNOWN


def _thousands(value: float, _pos=None) -> str:
    return f"{value:,.0f}".replace(",", "\u00a0")


def _round_scale_length(span: float) -> float:
    target = span * 0.22
    if not math.isfinite(target) or target <= 0:
        return 1.0
    base = 10.0 ** math.floor(math.log10(target))
    for mult in (5.0, 2.0, 1.0):
        if mult * base <= target:
            return mult * base
    return base


def _smoothed(z: np.ndarray, sigma_cells: float) -> np.ndarray:
    from scipy.ndimage import gaussian_filter

    hole = ~np.isfinite(z)
    if sigma_cells <= 0 or hole.all():
        return z
    weight = gaussian_filter((~hole).astype(float), sigma_cells, mode="nearest")
    total = gaussian_filter(np.where(hole, 0.0, z), sigma_cells, mode="nearest")
    smooth = np.divide(total, weight, out=np.full_like(total, np.nan), where=weight > 1e-6)
    smooth[hole] = np.nan
    return smooth


def _draw_shade(ax, shade: Shade) -> None:
    values, extent = shade
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.size == 0:
        return
    cmap = colormaps["gray"].with_extremes(bad=(1.0, 1.0, 1.0, 0.0))
    ax.imshow(
        np.ma.masked_invalid(values), extent=tuple(extent), origin="lower", cmap=cmap,
        norm=Normalize(*_SHADE_NORM), interpolation="bilinear", zorder=1,
    )


def _draw_contours(ax, surface: PlanSurface) -> bool:
    z = np.asarray(surface.z, dtype=float)
    if z.ndim != 2 or min(z.shape) < 2 or not np.isfinite(z).any():
        return False
    smooth = _smoothed(z, _CONTOUR_SMOOTH_M / float(surface.cell_m))
    z_min, z_max = float(np.nanmin(smooth)), float(np.nanmax(smooth))
    first = math.ceil(z_min / _MINOR_INTERVAL_M)
    last = math.floor(z_max / _MINOR_INTERVAL_M)
    ratio = round(_MAJOR_INTERVAL_M / _MINOR_INTERVAL_M)
    major = [k * _MINOR_INTERVAL_M for k in range(first, last + 1) if k % ratio == 0]
    minor = [k * _MINOR_INTERVAL_M for k in range(first, last + 1) if k % ratio != 0]
    masked = np.ma.masked_invalid(smooth)
    drawn = False
    if minor:
        contour = ax.contour(
            surface.x, surface.y, masked, levels=minor, colors=_MINOR_CONTOUR_COLOR,
            linewidths=0.3, alpha=0.5, zorder=2,
        )
        contour.set_gid("plan-contour-minor")
        drawn = True
    if major:
        contour = ax.contour(
            surface.x, surface.y, masked, levels=major, colors=_MAJOR_CONTOUR_COLOR,
            linewidths=0.75, alpha=0.9, zorder=2.1,
        )
        contour.set_gid("plan-contour-major")
        for text in ax.clabel(contour, fmt=_thousands, fontsize=7.5, inline=True, inline_spacing=2):
            text.set_gid("plan-contour-label")
            text.set_color("#3A2C1E")
            text.set_path_effects([patheffects.withStroke(linewidth=1.6, foreground="#FFFFFF", alpha=0.85)])
        drawn = True
    return drawn


def _anchored_rect(loc: str, size, pad, x_lim, y_lim) -> tuple[float, float, float, float]:
    if "left" in loc:
        x0 = x_lim[0] + pad[0]
    elif "right" in loc:
        x0 = x_lim[1] - pad[0] - size[0]
    else:
        x0 = (x_lim[0] + x_lim[1] - size[0]) / 2.0
    if "lower" in loc:
        y0 = y_lim[0] + pad[1]
    elif "upper" in loc:
        y0 = y_lim[1] - pad[1] - size[1]
    else:
        y0 = (y_lim[0] + y_lim[1] - size[1]) / 2.0
    return (x0, y0, size[0], size[1])


def _segment_touches(rect, start, end) -> bool:
    x0, y0, width, height = rect
    t0, t1 = 0.0, 1.0
    dx, dy = end[0] - start[0], end[1] - start[1]
    for p, q in ((-dx, start[0] - x0), (dx, x0 + width - start[0]),
                 (-dy, start[1] - y0), (dy, y0 + height - start[1])):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def _crossings(rects, segments, clearance: float = 0.0) -> int:
    """Number of section segments touching any of ``rects`` grown by ``clearance``."""
    grown = [
        (x0 - clearance, y0 - clearance, width + 2.0 * clearance, height + 2.0 * clearance)
        for x0, y0, width, height in rects
    ]
    return sum(
        1 for start, end in segments if any(_segment_touches(rect, start, end) for rect in grown)
    )


def _rects_overlap(first, second) -> bool:
    return (first[0] < second[0] + second[2] and second[0] < first[0] + first[2]
            and first[1] < second[1] + second[3] and second[1] < first[1] + first[3])


def _slots(size, pad, x_lim, y_lim) -> list:
    """Candidate rectangles for a box: corners, then the edges, then the interior."""
    x_hi, y_hi = x_lim[1] - pad[0] - size[0], y_lim[1] - pad[1] - size[1]
    xs = np.linspace(x_lim[0] + pad[0], max(x_hi, x_lim[0] + pad[0]), _FURNITURE_STEPS + 1)
    ys = np.linspace(y_lim[0] + pad[1], max(y_hi, y_lim[0] + pad[1]), _FURNITURE_STEPS // 2 + 1)
    inner_x = sorted(range(1, len(xs) - 1), key=lambda i: (min(i, len(xs) - 1 - i), -i))
    inner_y = sorted(range(1, len(ys) - 1), key=lambda j: (min(j, len(ys) - 1 - j), -j))
    anchors = [(xs[-1], ys[-1]), (xs[0], ys[-1]), (xs[-1], ys[0]), (xs[0], ys[0])]
    anchors += [(xs[i], y) for i in inner_x for y in (ys[-1], ys[0])]
    anchors += [(x, ys[j]) for j in inner_y for x in (xs[-1], xs[0])]
    anchors += [(xs[i], ys[j]) for j in inner_y for i in inner_x]
    return [(float(x), float(y), size[0], size[1]) for x, y in anchors]


def _best_slot(candidates, cost):
    """First candidate with the lowest cost, stopping at the first free one."""
    best, best_cost = None, None
    for candidate in candidates:
        value = cost(candidate)
        if value is None:
            continue
        if best_cost is None or value < best_cost:
            best, best_cost = candidate, value
            if value == 0:
                break
    return best, best_cost


def _padded(bbox: Bbox) -> Bbox:
    return Bbox.from_extents(
        bbox.x0 - _LABEL_PAD_PX, bbox.y0 - _LABEL_PAD_PX, bbox.x1 + _LABEL_PAD_PX, bbox.y1 + _LABEL_PAD_PX,
    )


def _thin_regular(default_boxes: list, taken: list, skip: set) -> list:
    """Every k-th label (smallest k without overlaps) that stays clear of ``taken``."""
    n = len(default_boxes)
    regular: list = []
    for k in range(1, n + 1):
        regular = [i for i in range(0, n, k) if default_boxes[i] is not None and i not in skip]
        if all(not default_boxes[a].overlaps(default_boxes[b])
               for pos, a in enumerate(regular) for b in regular[pos + 1:]):
            break
    return [i for i in regular if not any(default_boxes[i].overlaps(box) for box in taken)]


@_cleanup_failed_figures
def _build_plan_figure(
    sections,
    statuses: Optional[Mapping[str, str]],
    *,
    excluded=(),
    shade: Optional[Shade] = None,
    surface: Optional[PlanSurface] = None,
    width_in: float = 7.0,
    height_in: float = 4.2,
):
    """Build the dashboard plan figure, returning ``(fig, ax)`` or ``None``."""
    valid = []
    excluded_flags = []
    resolved_statuses = []
    excluded = set(excluded)
    for section in sections or ():
        points = _section_points(section)
        if points:
            name = (_section_mapping(section) or {}).get("name")
            valid.append(("" if name is None else str(name), points))
            excluded_flags.append(str(name) in excluded or (_section_mapping(section) or {}).get("included") is False)
            resolved_statuses.append((_section_mapping(section) or {}).get("worst_status"))
    if not valid:
        return None
    statuses = statuses or {}

    xs = [point[0] for _name, points in valid for point in points]
    ys = [point[1] for _name, points in valid for point in points]
    x_min, x_max = min(xs) - _MARGIN_M, max(xs) + _MARGIN_M
    y_min, y_max = min(ys) - _MARGIN_M, max(ys) + _MARGIN_M

    fig = _new_figure(figsize=(width_in, height_in))
    left, right = min(0.62, 0.3 * width_in), min(0.06, 0.03 * width_in)
    bottom, top = min(0.40, 0.3 * height_in), min(0.06, 0.03 * height_in)
    axes_w, axes_h = width_in - left - right, height_in - bottom - top
    ax = fig.add_axes((left / width_in, bottom / height_in, axes_w / width_in, axes_h / height_in))

    metres_per_inch = max((x_max - x_min) / axes_w, (y_max - y_min) / axes_h)
    x_mid, y_mid = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0
    x_lim = (x_mid - metres_per_inch * axes_w / 2.0, x_mid + metres_per_inch * axes_w / 2.0)
    y_lim = (y_mid - metres_per_inch * axes_h / 2.0, y_mid + metres_per_inch * axes_h / 2.0)
    x_span, y_span = x_lim[1] - x_lim[0], y_lim[1] - y_lim[0]
    metres_per_point = metres_per_inch / 72.0

    ax.set_xlim(*x_lim)
    ax.set_ylim(*y_lim)
    ax.set_aspect("equal", adjustable="box")
    ax.set_autoscale_on(False)

    if shade is not None:
        _draw_shade(ax, shade)
    has_contours = surface is not None and _draw_contours(ax, surface)
    ax.set_xlim(*x_lim)
    ax.set_ylim(*y_lim)

    keys = [_status_key(resolved if resolved is not None else statuses.get(name))
            for (name, _points), resolved in zip(valid, resolved_statuses)]
    counts = {status: sum(key == status and not excluded for key, excluded in zip(keys, excluded_flags)) for status in STATUS_COLORS}
    halo = [patheffects.withStroke(linewidth=3.0, foreground="#FFFFFF", alpha=0.9)]
    for (name, points), key, is_excluded in zip(valid, keys, excluded_flags):
        line, = ax.plot(
            [point[0] for point in points], [point[1] for point in points],
            color="#CBD5E1" if is_excluded else STATUS_COLORS[key], linewidth=0.8 if is_excluded else 1.7, solid_capstyle="butt", zorder=4, path_effects=halo,
        )
        line.set_gid("plan-section-excluded" if is_excluded else "plan-section")

    ax.set_xlabel("Este (m)", fontsize=7.5, labelpad=2)
    ax.set_ylabel("Norte (m)", fontsize=7.5, labelpad=2)
    ax.xaxis.set_major_formatter(_thousands)
    ax.yaxis.set_major_formatter(_thousands)
    ax.tick_params(direction="out", labelsize=7.5, length=2.5, width=0.6)
    ax.grid(True, color="#FFFFFF" if shade is not None else "#E2E8F0", linewidth=0.35, alpha=0.6, zorder=2.5)
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)
        spine.set_color("#64748B")

    handles = [
        Line2D([], [], color=STATUS_COLORS[status], linewidth=1.7,
               label=f"{STATUS_LABELS_ES[status]} ({counts[status]})")
        for status in (STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE)
    ]
    if counts[STATUS_UNKNOWN]:
        handles.append(Line2D(
            [], [], color=STATUS_COLORS[STATUS_UNKNOWN], linewidth=1.7,
            label=f"{STATUS_LABELS_ES[STATUS_UNKNOWN]} ({counts[STATUS_UNKNOWN]})",
        ))
    if any(excluded_flags):
        handles.append(Line2D([], [], color="#CBD5E1", linewidth=0.8, label=f"Fuera del filtro ({sum(excluded_flags)})"))
    if has_contours:
        handles.append(Line2D(
            [], [], color=_MAJOR_CONTOUR_COLOR, linewidth=0.75,
            label=f"Curva \u00edndice (cada {_MAJOR_INTERVAL_M:g} m, rotulada)",
        ))
        handles.append(Line2D(
            [], [], color=_MINOR_CONTOUR_COLOR, linewidth=0.3, alpha=0.7,
            label=f"Curva de nivel (cada {_MINOR_INTERVAL_M:g} m)",
        ))
    renderer = fig.canvas.get_renderer()
    segments = [
        (start, end) for _name, points in valid for start, end in zip(points[:-1], points[1:])
    ]
    clearance = _LINE_CLEARANCE_PT * metres_per_point

    def make_legend(loc: str):
        made = ax.legend(
            handles=handles, loc=loc, frameon=True, framealpha=0.96, edgecolor=_FRAME_COLOR,
            title="Secci\u00f3n: estado oficial", title_fontsize=7.5, fontsize=7.5, handlelength=2.4,
            borderpad=0.6,
        )
        made.set_zorder(8)
        return made

    legend = make_legend(_LEGEND_LOCS[0])
    metres_per_pixel = metres_per_inch / fig.dpi
    legend_extent = legend.get_window_extent(renderer)
    axes_extent = ax.get_window_extent(renderer)
    legend_size = (legend_extent.width * metres_per_pixel, legend_extent.height * metres_per_pixel)
    legend_pad = (
        (legend_extent.x0 - axes_extent.x0) * metres_per_pixel,
        (legend_extent.y0 - axes_extent.y0) * metres_per_pixel,
    )
    legend_loc, _cost = _best_slot(_LEGEND_LOCS, lambda loc: _crossings(
        [_anchored_rect(loc, legend_size, legend_pad, x_lim, y_lim)], segments, clearance,
    ))
    if legend_loc != _LEGEND_LOCS[0]:
        legend.remove()
        legend = make_legend(legend_loc)
    legend_rect = _anchored_rect(legend_loc, legend_size, legend_pad, x_lim, y_lim)

    bar_len = _round_scale_length(x_span)
    north_size = (0.05 * x_span, 0.215 * y_span)
    scale_size = (bar_len + 0.024 * x_span, 0.105 * y_span)
    furniture_pad = (0.01 * x_span, 0.03 * y_span)
    furniture_gap = 0.012 * x_span
    unit_size = (north_size[0] + furniture_gap + scale_size[0], north_size[1])

    def unit_rects(unit):
        on_right = unit[0] + unit[2] / 2.0 > x_mid
        on_top = unit[1] + unit[3] / 2.0 > y_mid
        north_x = unit[0] + unit[2] - north_size[0] if on_right else unit[0]
        scale_x = unit[0] if on_right else unit[0] + north_size[0] + furniture_gap
        scale_y = unit[1] + unit[3] - scale_size[1] if on_top else unit[1]
        return (
            (north_x, unit[1], north_size[0], north_size[1]),
            (scale_x, scale_y, scale_size[0], scale_size[1]),
        )

    def cost_of(rects, blocked):
        if any(_rects_overlap(rect, other) for rect in rects for other in blocked):
            return None
        return _crossings(rects, segments, clearance)

    unit, unit_cost = _best_slot(
        _slots(unit_size, furniture_pad, x_lim, y_lim),
        lambda slot: cost_of(unit_rects(slot), [legend_rect]),
    )
    if unit is None:
        unit = _anchored_rect("upper right", unit_size, furniture_pad, x_lim, y_lim)
        unit_cost = _crossings(unit_rects(unit), segments, clearance)
    north_rect, scale_rect = unit_rects(unit)
    if unit_cost:
        split_scale, scale_cost = _best_slot(
            _slots(scale_size, furniture_pad, x_lim, y_lim),
            lambda slot: cost_of([slot], [legend_rect]),
        )
        if split_scale is not None:
            split_north, north_cost = _best_slot(
                _slots(north_size, furniture_pad, x_lim, y_lim),
                lambda slot: cost_of([slot], [legend_rect, split_scale]),
            )
            if split_north is not None and scale_cost + north_cost < unit_cost:
                north_rect, scale_rect = split_north, split_scale

    stroke = [patheffects.withStroke(linewidth=2.2, foreground="#FFFFFF", alpha=0.9)]
    scale_box = Rectangle(
        scale_rect[:2], scale_rect[2], scale_rect[3],
        facecolor="#FFFFFF", edgecolor=_FRAME_COLOR, linewidth=0.4, alpha=0.9, zorder=6.5,
    )
    north_box = Rectangle(
        north_rect[:2], north_rect[2], north_rect[3],
        facecolor="#FFFFFF", edgecolor=_FRAME_COLOR, linewidth=0.4, alpha=0.9, zorder=6.5,
    )
    for box in (scale_box, north_box):
        box.set_gid("plan-furniture")
        ax.add_patch(box)
    bar_x = scale_rect[0] + 0.012 * x_span
    bar_y = scale_rect[1] + 0.03 * y_span
    bar, = ax.plot([bar_x, bar_x + bar_len], [bar_y, bar_y], color=_TEXT_DARK, linewidth=2.0,
                   solid_capstyle="butt", zorder=7)
    bar.set_gid("plan-scale-bar")
    for fraction in (0.0, 0.5, 1.0):
        tick_x = bar_x + fraction * bar_len
        ax.plot([tick_x, tick_x], [bar_y, bar_y + 0.012 * y_span], color=_TEXT_DARK, linewidth=0.9, zorder=7)
    scale_label = ax.text(
        bar_x + bar_len / 2.0, bar_y + 0.022 * y_span, f"{bar_len:g} m", ha="center", va="bottom",
        fontsize=7.5, fontweight="bold", color=_TEXT_DARK, zorder=7, path_effects=stroke,
    )
    scale_label.set_gid("plan-scale-label")
    north_x = north_rect[0] + north_rect[2] / 2.0
    north_y = north_rect[1] + 0.045 * y_span
    north = ax.annotate(
        "N", xy=(north_x, north_y + 0.14 * y_span), xytext=(north_x, north_y), ha="center", va="center",
        fontsize=7.5, fontweight="bold", color=_TEXT_DARK, zorder=7,
        arrowprops=dict(arrowstyle="-|>", color=_TEXT_DARK, linewidth=1.0),
    )
    north.set_gid("plan-north")

    axes_box = axes_extent
    obstacles = [
        _padded(legend.get_window_extent(renderer)),
        _padded(scale_box.get_window_extent(renderer)),
        _padded(north_box.get_window_extent(renderer)),
    ]
    label_stroke = [patheffects.withStroke(linewidth=1.8, foreground="#FFFFFF", alpha=0.92)]
    to_points = 72.0 / fig.dpi
    labels, slots = [], []
    for (name, points), key in zip(valid, keys):
        highlighted = key in _HIGHLIGHTED
        text = ax.text(
            points[-1][0], points[-1][1], name, fontsize=7.5, ha="center", va="center", zorder=6,
            color=STATUS_COLORS[key] if highlighted else _TEXT_DARK,
            fontweight="bold" if highlighted else "normal", path_effects=label_stroke,
        )
        text.set_gid("plan-label")
        labels.append(text)
        extent = text.get_window_extent(renderer)
        half_w_px, half_h_px = extent.width / 2.0, extent.height / 2.0
        half_w, half_h = half_w_px * to_points, half_h_px * to_points
        candidates = []
        for tier in range(_LABEL_TIERS if name else 0):
            for end, before in ((points[-1], points[-2]), (points[0], points[1])):
                dx, dy = end[0] - before[0], end[1] - before[1]
                norm = math.hypot(dx, dy) or 1.0
                ux, uy = dx / norm, dy / norm
                reach = abs(ux) * half_w + abs(uy) * half_h
                offset_m = (_LABEL_GAP_PT + reach + tier * (2.0 * reach + _LABEL_GAP_PT)) * metres_per_point
                position = (end[0] + ux * offset_m, end[1] + uy * offset_m)
                cx, cy = ax.transData.transform(position)
                box = _padded(Bbox.from_extents(
                    cx - half_w_px, cy - half_h_px, cx + half_w_px, cy + half_h_px,
                ))
                if (axes_box.x0 <= box.x0 and box.x1 <= axes_box.x1
                        and axes_box.y0 <= box.y0 and box.y1 <= axes_box.y1
                        and not any(box.overlaps(obstacle) for obstacle in obstacles)):
                    candidates.append((tier, end, position, box))
        slots.append(candidates)

    placed: dict = {}

    def place(index: int, tiers: int) -> None:
        for candidate in slots[index]:
            if candidate[0] < tiers and not any(
                candidate[3].overlaps(other[3]) for other in placed.values()
            ):
                placed[index] = candidate
                return

    flagged = [index for index, key in enumerate(keys) if key in _HIGHLIGHTED]
    priority = flagged if len(flagged) / len(valid) < 0.6 else [
        i for i in flagged if any(0 <= j < len(keys) and keys[j] == STATUS_CUMPLE for j in (i - 1, i + 1))
    ]
    for index in sorted(priority, key=lambda i: (len(slots[i]), i)):
        place(index, _LABEL_TIERS)
    for index in (0, len(valid) - 1):
        if index not in placed:
            place(index, 1)
    default_boxes = [
        next((candidate[3] for candidate in candidates if candidate[0] == 0), None)
        for candidates in slots
    ]
    for index in _thin_regular(default_boxes, [c[3] for c in placed.values()], set(placed)):
        placed[index] = next(c for c in slots[index] if c[0] == 0)

    for index, text in enumerate(labels):
        if index not in placed:
            text.remove()
            continue
        tier, end, position, _box = placed[index]
        text.set_position(position)
        if tier:
            leader, = ax.plot(
                [end[0], position[0]], [end[1], position[1]], color=STATUS_COLORS[keys[index]],
                linewidth=0.5, solid_capstyle="butt", zorder=5.5,
            )
            leader.set_gid("plan-label-leader")

    return fig, ax


@_serialized_render
@_cleanup_failed_figures
def dashboard_plan_png(
    sections,
    statuses: Mapping[str, str],
    *,
    excluded=(),
    shade: Optional[Shade] = None,
    surface: Optional[PlanSurface] = None,
    width_in: float = 7.0,
    height_in: float = 4.2,
    dpi: int = 150,
) -> Optional[bytes]:
    """Render the dashboard plan view as PNG bytes.

    Section lines are coloured by ``statuses[name]`` (CUMPLE, FUERA,
    NO_CUMPLE; anything else or missing is drawn as not evaluated) over the
    grey shaded relief ``shade`` and the contours of ``surface`` (index every
    25 m with labels, intermediate every 5 m, drawn on the smoothed grid).
    Section names never overlap: every non-compliant section (NO_CUMPLE or
    FUERA) is labelled first, moved to the other end of its line or further
    out with a leader when its neighbours take the spot, then the first and
    the last section, then every k-th compliant one that still fits. The
    north arrow, the round-number scale bar and the legend (Spanish status
    labels with their counts) go where they cross the fewest section lines:
    a corner when one is free, otherwise along an edge. Returns ``None``
    when no section has usable endpoints.
    """
    built = _build_plan_figure(
        sections, statuses, excluded=excluded, shade=shade, surface=surface, width_in=width_in, height_in=height_in,
    )
    if built is None:
        return None
    fig, _ax = built
    return _fig_to_png(fig, dpi)
