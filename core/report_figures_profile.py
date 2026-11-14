"""Cropped profile panel and locator mini-plan for the web reports (contract C7)."""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence

import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

from core.report_charts import (
    STATUS_COLORS,
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_LABELS_ES,
    STATUS_NO_CUMPLE,
    STATUS_UNKNOWN,
    _DESIGN_COLOR,
    _TEXT_DARK,
    _TOPO_COLOR,
    _cleanup_failed_figures,
    _fig_to_png,
    _new_figure,
    _section_endpoints,
    _serialized_render,
)

Shade = tuple[np.ndarray, tuple[float, float, float, float]]

MIN_FONT_PT = 7.5
OVER_EXCAVATION_COLOR = "#3b82f6"
UNDER_EXCAVATION_COLOR = "#f97316"
EXCAVATION_ALPHA = 0.35
OTHER_SECTION_COLOR = "#9CA3AF"
SHADE_ALPHA = 0.35
LOCATOR_MARGIN_FRACTION = 0.25
LOCATOR_MIN_LONG_SIDE_M = 60.0

_PROFILE_MARGINS_IN = (0.65, 0.108, 0.65, 0.25)
_PROFILE_MIN_AXES_FRACTION = 0.3
_BENCH_LABEL_PT = 7.5
_LOCATOR_LABEL_PT = 6.8
_CHAR_WIDTH_EM = 0.72
_POINTS_PER_INCH = 72.0

_STATUS_ALIASES = {
    "CUMPLE": STATUS_CUMPLE,
    "FUERA": STATUS_FUERA,
    "FUERA_DE_TOLERANCIA": STATUS_FUERA,
    "NO_CUMPLE": STATUS_NO_CUMPLE,
    "UNKNOWN": STATUS_UNKNOWN,
}


def _status_key(status: Any) -> str:
    key = "_".join(str(status or "").upper().split())
    return _STATUS_ALIASES.get(key, STATUS_UNKNOWN)


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean_series(value: Any) -> Optional[tuple[np.ndarray, np.ndarray]]:
    if value is None:
        return None
    try:
        if len(value) != 2:
            return None
        dist = np.asarray(value[0], dtype=float).ravel()
        elev = np.asarray(value[1], dtype=float).ravel()
    except (TypeError, ValueError):
        return None
    if dist.size == 0 or dist.size != elev.size:
        return None
    keep = np.isfinite(dist) & np.isfinite(elev)
    if not keep.any():
        return None
    return dist[keep], elev[keep]


def _view_window(value: Any) -> Optional[tuple[float, float, float, float]]:
    if value is None:
        return None
    try:
        if len(value) != 4:
            return None
    except TypeError:
        return None
    numbers = [n for n in (_finite(v) for v in value) if n is not None]
    if len(numbers) != 4:
        return None
    d_min, d_max, z_min, z_max = numbers
    if d_max <= d_min or z_max <= z_min:
        return None
    return d_min, d_max, z_min, z_max


def _fit_to_ratio(
    x0: float, x1: float, y0: float, y1: float, ratio: float
) -> tuple[float, float, float, float]:
    width = max(x1 - x0, 1e-6)
    height = max(y1 - y0, 1e-6)
    if width / height < ratio:
        grow = height * ratio - width
        return x0 - grow / 2.0, x1 + grow / 2.0, y0, y1
    grow = width / ratio - height
    return x0, x1, y0 - grow / 2.0, y1 + grow / 2.0


def _excavation_bands(
    design: tuple[np.ndarray, np.ndarray],
    topo: tuple[np.ndarray, np.ndarray],
    window: Optional[tuple[float, float, float, float]],
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    order_d = np.argsort(design[0], kind="stable")
    order_t = np.argsort(topo[0], kind="stable")
    dist_d, elev_d = design[0][order_d], design[1][order_d]
    dist_t, elev_t = topo[0][order_t], topo[1][order_t]
    lo = max(float(dist_d[0]), float(dist_t[0]))
    hi = min(float(dist_d[-1]), float(dist_t[-1]))
    if window is not None:
        lo, hi = max(lo, window[0]), min(hi, window[1])
    if hi <= lo:
        return None
    grid = np.unique(np.concatenate([dist_d, dist_t, [lo, hi]]))
    grid = grid[(grid >= lo) & (grid <= hi)]
    if grid.size < 2:
        return None
    z_design = np.interp(grid, dist_d, elev_d)
    z_topo = np.interp(grid, dist_t, elev_t)
    if window is not None:
        z_design = np.clip(z_design, window[2], window[3])
        z_topo = np.clip(z_topo, window[2], window[3])
    return grid, z_design, z_topo


def _profile_axes_rect(width_in: float, height_in: float) -> tuple[float, float, float, float]:
    """Axes rectangle (figure fractions) leaving fixed-size margins for the decorations.

    The fonts do not scale with the figure, so the margins are constant in
    inches: a larger panel gives all the extra area to the axes.
    """
    left, right, bottom, top = _PROFILE_MARGINS_IN
    axes_w = width_in - left - right
    axes_h = height_in - bottom - top
    if axes_w < _PROFILE_MIN_AXES_FRACTION * width_in:
        shrink = (1.0 - _PROFILE_MIN_AXES_FRACTION) * width_in / (left + right)
        left, axes_w = left * shrink, _PROFILE_MIN_AXES_FRACTION * width_in
    if axes_h < _PROFILE_MIN_AXES_FRACTION * height_in:
        shrink = (1.0 - _PROFILE_MIN_AXES_FRACTION) * height_in / (bottom + top)
        bottom, axes_h = bottom * shrink, _PROFILE_MIN_AXES_FRACTION * height_in
    return left / width_in, bottom / height_in, axes_w / width_in, axes_h / height_in


def _bench_label_anchor(
    crest: tuple[float, float],
    toe_distance: Optional[float],
    limits: tuple[float, float, float, float],
    metres_per_point: float,
    text: str,
) -> tuple[float, float]:
    x0, x1, z0, z1 = limits
    half_w = (len(text) * _CHAR_WIDTH_EM * _BENCH_LABEL_PT / 2.0 + 3.0) * metres_per_point
    half_h = (_BENCH_LABEL_PT * 0.7 + 3.0) * metres_per_point
    gap = 3.0 * metres_per_point
    side = 1.0 if toe_distance is None or toe_distance >= crest[0] else -1.0
    x = crest[0] + side * (half_w + gap)
    z = crest[1] + half_h + gap
    if z + half_h > z1:
        z = crest[1] - half_h - gap
        x = crest[0] - side * (half_w + gap)
    x = min(max(x, x0 + half_w), x1 - half_w)
    z = min(max(z, z0 + half_h), z1 - half_h)
    return x, z


@_cleanup_failed_figures
def _build_profile_figure(
    entry: Optional[Mapping[str, Any]],
    status: Optional[str] = None,
    width_in: float = 3.6,
    height_in: float = 2.6,
):
    """Build the cropped profile panel, returning ``(fig, ax)`` or ``None``."""
    if not isinstance(entry, Mapping):
        return None
    design = _clean_series(entry.get("profile_d"))
    topo = _clean_series(entry.get("profile_t"))
    if design is None and topo is None:
        return None
    window = _view_window(entry.get("view_window"))

    if window is not None:
        x0, x1, z0, z1 = window
    else:
        present = [series for series in (design, topo) if series is not None]
        x0 = min(float(s[0].min()) for s in present)
        x1 = max(float(s[0].max()) for s in present)
        z0 = min(float(s[1].min()) for s in present)
        z1 = max(float(s[1].max()) for s in present)
        pad_x = 0.02 * max(x1 - x0, 1.0)
        pad_z = 0.02 * max(z1 - z0, 1.0)
        x0, x1, z0, z1 = x0 - pad_x, x1 + pad_x, z0 - pad_z, z1 + pad_z

    fig = _new_figure(figsize=(width_in, height_in))
    axes_rect = _profile_axes_rect(width_in, height_in)
    ax = fig.add_axes(axes_rect)
    axes_w_in = axes_rect[2] * width_in
    axes_h_in = axes_rect[3] * height_in
    x0, x1, z0, z1 = _fit_to_ratio(x0, x1, z0, z1, axes_w_in / axes_h_in)
    metres_per_point = (x1 - x0) / (axes_w_in * _POINTS_PER_INCH)

    handles = []
    if design is not None and topo is not None:
        bands = _excavation_bands(design, topo, window)
        if bands is not None:
            grid, z_design, z_topo = bands
            for gid, color, where in (
                ("over-excavation", OVER_EXCAVATION_COLOR, z_topo < z_design),
                ("under-excavation", UNDER_EXCAVATION_COLOR, z_topo > z_design),
            ):
                if where.any():
                    band = ax.fill_between(
                        grid, z_design, z_topo, where=where, interpolate=True,
                        facecolor=to_rgba(color, EXCAVATION_ALPHA),
                        edgecolor="none", linewidth=0.0, zorder=2,
                    )
                    band.set_gid(gid)
    if design is not None:
        line, = ax.plot(design[0], design[1], color=_DESIGN_COLOR, linewidth=1.1,
                        linestyle="--", zorder=4)
        line.set_gid("profile-design")
        handles.append(Line2D([0], [0], color=_DESIGN_COLOR, linewidth=1.1,
                              linestyle="--", label="Diseño"))
    if topo is not None:
        line, = ax.plot(topo[0], topo[1], color=_TOPO_COLOR, linewidth=1.2, zorder=5)
        line.set_gid("profile-topo")
        handles.append(Line2D([0], [0], color=_TOPO_COLOR, linewidth=1.2,
                              label="As-built"))
    if design is not None and topo is not None:
        handles.append(Patch(facecolor=to_rgba(OVER_EXCAVATION_COLOR, EXCAVATION_ALPHA),
                             edgecolor="none", label="Sobreexcavación"))
        handles.append(Patch(facecolor=to_rgba(UNDER_EXCAVATION_COLOR, EXCAVATION_ALPHA),
                             edgecolor="none", label="Subexcavación"))

    params_design = entry.get("params_design")
    for bench in list(getattr(params_design, "benches", None) or []):
        crest_d = _finite(getattr(bench, "crest_distance", None))
        crest_z = _finite(getattr(bench, "crest_elevation", None))
        number = getattr(bench, "bench_number", None)
        if crest_d is None or crest_z is None or number is None:
            continue
        if not (x0 <= crest_d <= x1 and z0 <= crest_z <= z1):
            continue
        text = f"B{number}"
        anchor = _bench_label_anchor(
            (crest_d, crest_z), _finite(getattr(bench, "toe_distance", None)),
            (x0, x1, z0, z1), metres_per_point, text,
        )
        marker, = ax.plot([crest_d], [crest_z], marker="o", markersize=2.6,
                          color=_DESIGN_COLOR, linestyle="none", zorder=6)
        marker.set_gid("bench-crest")
        label = ax.annotate(
            text, xy=(crest_d, crest_z), xytext=anchor, textcoords="data",
            ha="center", va="center", fontsize=_BENCH_LABEL_PT, fontweight="bold",
            color=_DESIGN_COLOR, zorder=7, annotation_clip=False,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=_DESIGN_COLOR,
                      lw=0.5, alpha=0.92),
        )
        label.set_gid("bench-label")

    name = str(entry.get("section_name") or "")
    if status is None:
        title, title_color = name, _TEXT_DARK
    else:
        key = _status_key(status)
        title = f"{name} · {STATUS_LABELS_ES[key]}"
        title_color = STATUS_COLORS[key]
    ax.set_title(title, fontsize=8.0, fontweight="bold", color=title_color, pad=3.0)

    ax.set_xlim(x0, x1)
    ax.set_ylim(z0, z1)
    ax.set_aspect("auto")
    ax.set_xlabel("Distancia en la sección (m)", fontsize=MIN_FONT_PT, labelpad=1.5)
    ax.set_ylabel("Elevación (m)", fontsize=MIN_FONT_PT, labelpad=1.5)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=7, steps=[1, 2, 5, 10], min_n_ticks=4))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=7, steps=[1, 2, 5, 10], min_n_ticks=4))
    plain = FuncFormatter(lambda value, _pos: f"{value:g}")
    ax.xaxis.set_major_formatter(plain)
    ax.yaxis.set_major_formatter(plain)
    ax.tick_params(labelsize=MIN_FONT_PT, length=2.0, width=0.5, pad=1.5)
    ax.grid(True, color="#E5E7EB", linewidth=0.4)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(0.5)
        spine.set_edgecolor("#9CA3AF")

    fig.legend(
        handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.0),
        ncol=min(2, len(handles)), fontsize=MIN_FONT_PT, frameon=False,
        handlelength=1.6, handletextpad=0.4, columnspacing=0.9, borderaxespad=0.2,
    )
    return fig, ax


@_serialized_render
@_cleanup_failed_figures
def cropped_profile_png(
    entry: Optional[Mapping[str, Any]],
    *,
    status: Optional[str] = None,
    width_in: float = 3.6,
    height_in: float = 2.6,
    dpi: int = 150,
) -> Optional[bytes]:
    """Render one ``ReportData.section_geometry`` entry as a cropped 1:1 profile panel.

    With ``view_window`` the axes contain that window at 1:1 scale: the short
    axis is enlarged symmetrically to fit the panel and the window is never
    shrunk; without it the whole profile is shown. Over-excavation (as-built
    below design) and under-excavation are shaded only inside the window.
    Returns ``None`` when both profiles are empty.
    """
    built = _build_profile_figure(entry, status, width_in, height_in)
    if built is None:
        return None
    fig, _ax = built
    return _fig_to_png(fig, dpi)


def _plan_endpoints(section: Any) -> Optional[list[tuple[float, float]]]:
    if not isinstance(section, Mapping):
        return None
    try:
        origin = section.get("origin")
        azimuth = _finite(section.get("azimuth"))
        up = _finite(section.get("length_up"))
        down = _finite(section.get("length_down"))
        if origin is not None and azimuth is not None and up is not None and down is not None:
            ox, oy = _finite(origin[0]), _finite(origin[1])
            if ox is not None and oy is not None and up + down > 0:
                dx, dy = math.sin(math.radians(azimuth)), math.cos(math.radians(azimuth))
                return [(ox - dx * down, oy - dy * down), (ox + dx * up, oy + dy * up)]
        points = _section_endpoints(dict(section))
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not points or not all(math.isfinite(c) for p in points for c in p):
        return None
    return points


def _valid_shade(shade: Any) -> Optional[Shade]:
    if shade is None:
        return None
    try:
        array, extent = shade
        array = np.asarray(array, dtype=float)
        extent = tuple(float(v) for v in extent)
    except (TypeError, ValueError):
        return None
    if array.ndim != 2 or array.size == 0 or len(extent) != 4:
        return None
    if not all(math.isfinite(v) for v in extent) or not np.isfinite(array).any():
        return None
    return array, extent


def _round_bar_length(target: float) -> float:
    if target <= 0 or not math.isfinite(target):
        return 1.0
    base = 10.0 ** math.floor(math.log10(target))
    for mult in (5.0, 2.0, 1.0):
        if mult * base <= target:
            return mult * base
    return base


def _boxes_clear(box: tuple[float, float, float, float], others: Sequence[tuple], gap: float) -> bool:
    cx, cy, w, h = box
    return all(
        abs(cx - ox) >= (w + ow) / 2.0 + gap or abs(cy - oy) >= (h + oh) / 2.0 + gap
        for ox, oy, ow, oh in others
    )


@_cleanup_failed_figures
def _build_locator_figure(
    sections: Optional[Sequence[Mapping[str, Any]]],
    highlighted: Optional[Mapping[str, str]],
    shade: Optional[Shade] = None,
    width_in: float = 2.7,
    height_in: float = 2.1,
):
    """Build the locator mini-plan, returning ``(fig, ax)`` or ``None``."""
    if not sections or not highlighted:
        return None
    strong, others = [], []
    for section in sections:
        points = _plan_endpoints(section)
        if points is None:
            continue
        name = str(section.get("name", ""))
        if name in highlighted:
            strong.append((name, points))
        else:
            others.append(points)
    if not strong:
        return None

    xs = [p[0] for _n, pts in strong for p in pts]
    ys = [p[1] for _n, pts in strong for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    margin = LOCATOR_MARGIN_FRACTION * max(x1 - x0, y1 - y0)
    x0, x1, y0, y1 = x0 - margin, x1 + margin, y0 - margin, y1 + margin
    shortfall = LOCATOR_MIN_LONG_SIDE_M - max(x1 - x0, y1 - y0)
    if shortfall > 0:
        half = shortfall / 2.0
        x0, x1, y0, y1 = x0 - half, x1 + half, y0 - half, y1 + half
    x0, x1, y0, y1 = _fit_to_ratio(x0, x1, y0, y1, width_in / height_in)

    fig = _new_figure(figsize=(width_in, height_in))
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    w_pt = width_in * _POINTS_PER_INCH
    h_pt = height_in * _POINTS_PER_INCH
    scale = w_pt / (x1 - x0)

    def to_pt(point):
        return (point[0] - x0) * scale, (point[1] - y0) * scale

    def to_data(cx, cy):
        return x0 + cx / scale, y0 + cy / scale

    relief = _valid_shade(shade)
    if relief is not None:
        ax.imshow(relief[0], extent=relief[1], origin="lower", cmap="gray",
                  vmin=0.0, vmax=1.0, alpha=SHADE_ALPHA, interpolation="bilinear",
                  zorder=0)

    for points in others:
        line, = ax.plot([p[0] for p in points], [p[1] for p in points],
                        color=OTHER_SECTION_COLOR, linewidth=0.8,
                        solid_capstyle="butt", zorder=2)
        line.set_gid("locator-other")

    bar = _round_bar_length(0.3 * (x1 - x0))
    bar_pt = bar * scale
    north_box = (w_pt - 12.0, h_pt - 20.0, 20.0, 36.0)
    scale_box = (5.0 + bar_pt / 2.0 + 3.0, 11.0, bar_pt + 12.0, 20.0)
    occupied = [north_box, scale_box]
    for _name, points in strong:
        a, b = np.array(to_pt(points[0])), np.array(to_pt(points[-1]))
        steps = max(2, int(np.hypot(*(b - a)) // 4.0) + 1)
        for t in np.linspace(0.0, 1.0, steps):
            q = a + (b - a) * t
            occupied.append((float(q[0]), float(q[1]), 3.0, 3.0))

    placements = {}
    box_h = _LOCATOR_LABEL_PT * 1.3 + 4.0
    for name, points in strong:
        a, b = np.array(to_pt(points[0])), np.array(to_pt(points[-1]))
        length = float(np.hypot(*(b - a))) or 1.0
        u = (b - a) / length
        normal = np.array([-u[1], u[0]])
        box_w = len(name) * _CHAR_WIDTH_EM * _LOCATOR_LABEL_PT + 5.0
        reach = 0.5 * (abs(u[0]) * box_w + abs(u[1]) * box_h)
        choice = None
        for dist in (3.0, 10.0, 18.0, 26.0, 34.0, 42.0, 52.0, 62.0):
            for lateral in (0.0, 9.0, -9.0, 18.0, -18.0):
                for end, sign in ((b, 1.0), (a, -1.0)):
                    cx, cy = end + sign * u * (dist + reach) + normal * lateral
                    inside = (box_w / 2.0 + 2.0 <= cx <= w_pt - box_w / 2.0 - 2.0
                              and box_h / 2.0 + 2.0 <= cy <= h_pt - box_h / 2.0 - 2.0)
                    if inside and _boxes_clear((cx, cy, box_w, box_h), occupied, 1.0):
                        choice = (float(cx), float(cy), end, dist + abs(lateral))
                        break
                if choice:
                    break
            if choice:
                break
        if choice is None:
            cx, cy = b + u * (3.0 + reach)
            cx = min(max(cx, box_w / 2.0 + 2.0), w_pt - box_w / 2.0 - 2.0)
            cy = min(max(cy, box_h / 2.0 + 2.0), h_pt - box_h / 2.0 - 2.0)
            choice = (float(cx), float(cy), b, 0.0)
        occupied.append((choice[0], choice[1], box_w, box_h))
        placements[name] = choice

    for name, points in strong:
        key = _status_key(highlighted.get(name))
        color = STATUS_COLORS[key]
        px = [p[0] for p in points]
        py = [p[1] for p in points]
        halo, = ax.plot(px, py, color="white", linewidth=3.4,
                        solid_capstyle="butt", zorder=3)
        halo.set_gid("locator-halo")
        line, = ax.plot(px, py, color=color, linewidth=2.0,
                        solid_capstyle="butt", zorder=4)
        line.set_gid("locator-highlighted")
        cx, cy, end, offset = placements[name]
        lx, ly = to_data(cx, cy)
        if offset > 4.0:
            ex, ey = to_data(float(end[0]), float(end[1]))
            leader, = ax.plot([ex, lx], [ey, ly], color=color, linewidth=0.5, zorder=4)
            leader.set_gid("locator-leader")
        label = ax.text(
            lx, ly, name, fontsize=_LOCATOR_LABEL_PT, fontweight="bold", color=color,
            ha="center", va="center", zorder=6,
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec=color, lw=0.4, alpha=0.95),
        )
        label.set_gid("locator-label")

    bx, by = to_data(8.0, 7.0)
    ax.add_patch(Rectangle(to_data(2.0, 2.0), (bar_pt + 12.0) / scale, 19.0 / scale,
                           fc="white", ec="none", alpha=0.85, zorder=6))
    bar_line, = ax.plot([bx, bx + bar], [by, by], color=_TEXT_DARK, linewidth=1.6,
                        solid_capstyle="butt", zorder=7)
    bar_line.set_gid("scale-bar")
    bar_text = ax.text(bx + bar / 2.0, by + 3.0 / scale, f"{bar:g} m", ha="center",
                       va="bottom", fontsize=7.5, color=_TEXT_DARK, zorder=7)
    bar_text.set_gid("scale-label")

    nx, ny = to_data(w_pt - 12.0, h_pt - 34.0)
    ax.add_patch(Rectangle(to_data(w_pt - 22.0, h_pt - 38.0), 20.0 / scale, 36.0 / scale,
                           fc="white", ec="none", alpha=0.85, zorder=6))
    ax.annotate("", xy=(nx, ny + 19.0 / scale), xytext=(nx, ny), zorder=7,
                arrowprops=dict(arrowstyle="-|>", color=_TEXT_DARK, lw=0.9,
                                shrinkA=0, shrinkB=0))
    north = ax.text(nx, ny + 20.0 / scale, "N", ha="center", va="bottom",
                    fontsize=7.5, fontweight="bold", color=_TEXT_DARK, zorder=7)
    north.set_gid("north-label")

    ax.set_aspect("auto")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor("#9CA3AF")
        spine.set_linewidth(0.8)
    return fig, ax


@_serialized_render
@_cleanup_failed_figures
def locator_map_png(
    sections: Optional[Sequence[Mapping[str, Any]]],
    highlighted: Optional[Mapping[str, str]],
    *,
    shade: Optional[Shade] = None,
    width_in: float = 2.7,
    height_in: float = 2.1,
    dpi: int = 150,
) -> Optional[bytes]:
    """Render the locator mini-plan of the highlighted sections (name → status).

    The view zooms to the highlighted section lines plus a 25 % margin of the
    long side (at least 60 m on the long side) at 1:1 scale. Highlighted
    sections are drawn in their status colour with their name, the rest thin
    and grey, over an optional faint shaded relief, with a north arrow and a
    round-number scale bar. Returns ``None`` when no highlighted section has
    usable geometry.
    """
    built = _build_locator_figure(sections, highlighted, shade, width_in, height_in)
    if built is None:
        return None
    fig, _ax = built
    return _fig_to_png(fig, dpi)
