"""Shared charts for the web Word/PDF reports.

Three pure functions returning in-memory PNG bytes: parameter donuts,
compliance plan view coloured by the worst bench of each profile, and large
annotated section profiles (with optional blast holes). Every function takes
plain inputs (lists/dicts/numbers) and returns ``None`` when there is no data
to draw, so callers can simply skip the image.
"""

from __future__ import annotations

import io
import math
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
from matplotlib.patches import Rectangle
from matplotlib.transforms import Bbox
import numpy as np

STATUS_CUMPLE = "CUMPLE"
STATUS_FUERA = "FUERA"
STATUS_NO_CUMPLE = "NO_CUMPLE"
STATUS_UNKNOWN = "UNKNOWN"

STATUS_COLORS = {
    STATUS_CUMPLE: "#2E7D32",
    STATUS_FUERA: "#B26A00",
    STATUS_NO_CUMPLE: "#C62828",
    STATUS_UNKNOWN: "#64748B",
}

STATUS_LABELS_ES = {
    STATUS_CUMPLE: "Cumple",
    STATUS_FUERA: "Fuera de tolerancia",
    STATUS_NO_CUMPLE: "No cumple",
    STATUS_UNKNOWN: "Sin evaluar",
}

_STATUS_ORDER = [STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE, STATUS_UNKNOWN]

_DONUT_OK_FILL = "#A9D6AE"
_DONUT_NOK_FILL = "#F1A9A9"
_TEXT_DARK = "#1F2937"
_DESIGN_COLOR = "#1F4E9C"
_TOPO_COLOR = "#2E7D32"
_RECONCILED_TOPO_COLOR = "#E68F19"
_BLAST_COLOR = "#C2410C"
_TOL_COLOR = "#B26A00"


def parameter_pct(cumple: int, no_cumple: int) -> float:
    """Return the compliance percentage (CUMPLE over total) as a raw float.

    Uses the same definition the report table uses so ``f"{...:.1f}%"`` is
    identical in both places; returns ``0.0`` when there is no data.
    """
    total = int(cumple) + int(no_cumple)
    if total <= 0:
        return 0.0
    return int(cumple) / total * 100.0


def profile_title(profile: dict) -> str:
    """Build the section-profile title ``Sección S-01 · Sector X · ESTADO``.

    The sector fragment is only included when it carries text, so profiles
    without a sector read ``Sección S-25 · NO CUMPLE``.
    """
    parts = []
    name = profile.get("name") if isinstance(profile, dict) else None
    sector = profile.get("sector") if isinstance(profile, dict) else None
    status = profile.get("status_label") if isinstance(profile, dict) else None
    if name:
        parts.append(f"Secci\u00f3n {name}")
    if sector is not None and str(sector).strip():
        parts.append(f"Sector {str(sector).strip()}")
    if status is not None and str(status).strip():
        parts.append(str(status).strip())
    return " \u00b7 ".join(parts) if parts else "Perfil de secci\u00f3n"


_MAX_CHART_PIXELS = 40_000_000


def _fig_to_png(fig, dpi: int) -> bytes:
    """Rasterise ``fig`` to PNG bytes with exactly one draw of the figure.

    The tight bounding box (title, axis labels, legend, annotations) is
    computed from the axes decorations and passed explicitly to ``savefig``;
    asking for ``bbox_inches="tight"`` instead makes matplotlib draw every
    artist a second time, which dominated the report chart time.
    """
    fig.set_dpi(dpi)
    width_in, height_in = fig.get_size_inches()
    if not math.isfinite(width_in * height_in) or width_in * dpi * height_in * dpi > _MAX_CHART_PIXELS:
        plt.close(fig)
        raise ValueError(f"chart raster too large: {width_in:.1f} x {height_in:.1f} in at {dpi} dpi")
    renderer = fig.canvas.get_renderer()
    bbox = fig.get_tightbbox(renderer)
    if bbox is None or not np.all(np.isfinite(bbox.bounds)) or bbox.width <= 0 or bbox.height <= 0:
        bbox = Bbox.from_bounds(0, 0, *fig.get_size_inches())
    bbox = bbox.padded(0.1)
    pixels = bbox.width * dpi * bbox.height * dpi
    if not math.isfinite(pixels) or pixels > _MAX_CHART_PIXELS:
        plt.close(fig)
        raise ValueError(f"chart raster too large: {bbox.width:.1f} x {bbox.height:.1f} in at {dpi} dpi")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches=bbox, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _as_series(value) -> Optional[tuple]:
    if not value or len(value) != 2:
        return None
    x, z = value[0], value[1]
    if len(x) == 0 or len(z) == 0:
        return None
    return np.asarray(x, dtype=float), np.asarray(z, dtype=float)


def _nice_number(value: float) -> float:
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    base = 10.0 ** exp
    for mult in (1, 2, 5, 10):
        if value <= mult * base:
            return float(mult) * base
    return 10.0 * base


def _tolerance_bounds(tol) -> Optional[tuple]:
    """Return the ``(neg, pos)`` tolerance magnitudes in metres, or ``None``.

    Accepts a scalar (symmetric band), a ``{"neg": .., "pos": ..}`` mapping
    (asymmetric band, matching the session tolerances) or a two-item
    sequence ordered ``(neg, pos)``. Non-positive or unusable values return
    ``None`` so callers simply skip the band.
    """
    if tol is None:
        return None
    neg = pos = None
    if isinstance(tol, bool):
        return None
    if isinstance(tol, (int, float)):
        value = abs(float(tol))
        neg = pos = value
    elif isinstance(tol, dict):
        neg = tol.get("neg", tol.get("min"))
        pos = tol.get("pos", tol.get("max"))
        if neg is None:
            neg = pos
        if pos is None:
            pos = neg
    elif isinstance(tol, (tuple, list)) and len(tol) == 2:
        neg, pos = tol[0], tol[1]
    if neg is None and pos is None:
        return None
    try:
        neg = abs(float(neg)) if neg is not None else 0.0
        pos = abs(float(pos)) if pos is not None else 0.0
    except (TypeError, ValueError):
        return None
    if neg <= 0 and pos <= 0:
        return None
    return neg, pos


def _bench_design_point(bench: dict, which: str) -> tuple:
    """Return the design ``(dist, z)`` for ``crest`` or ``toe`` of a bench.

    Prefers explicit design coordinates (``design_crest_dist``/``design_crest_z``
    or ``design_toe_dist``/``design_toe_z``) and falls back to the measured
    ``crest_dist``/``crest_z``/``toe_dist``/``toe_z`` pairs so bands and
    markers stay anchored to a real bench corner.
    """
    dist = bench.get(f"design_{which}_dist")
    z = bench.get(f"design_{which}_z")
    if dist is None:
        dist = bench.get(f"{which}_dist")
    if z is None:
        z = bench.get(f"{which}_z")
    return dist, z


def _bench_qualifier(bench: dict) -> str:
    """Return the Spanish qualifier for missing/extra benches (or ``""``).

    Reads the ``type`` field (``MATCH``/``MISSING``/``EXTRA``), explicit
    booleans, or the readable ``status_label`` (``NO CONSTRUIDO``,
    ``BANCO ADICIONAL``, ``FALTA BANCO``) so an unbuilt bench reads
    ``no construido`` and an extra one reads ``adicional``.
    """
    if bench.get("is_missing"):
        return "no construido"
    if bench.get("is_extra"):
        return "adicional"
    raw = " ".join(
        str(bench.get(key) or "")
        for key in ("type", "status_label", "kind", "state")
    ).upper()
    if "EXTRA" in raw or "ADICIONAL" in raw:
        return "adicional"
    if "MISSING" in raw or "NO CONSTRUIDO" in raw or "FALTA BANCO" in raw:
        return "no construido"
    return ""


def _bench_annotation_text(bench: dict) -> str:
    """Compose the bench label, qualifier and signed deviation text."""
    parts = []
    label = str(bench.get("label") or "").strip()
    if label:
        parts.append(label)
    qualifier = _bench_qualifier(bench)
    if qualifier:
        parts.append(qualifier)
    text = " \u00b7 ".join(parts)
    deviation = str(bench.get("deviation_text") or "").strip()
    if deviation:
        text = f"{text} {deviation}".strip()
    return text


def parameter_donuts_png(parameters: list, dpi: int = 150) -> Optional[bytes]:
    """Render one donut per parameter (CUMPLE vs NO CUMPLE) as PNG bytes.

    ``parameters`` is a list of dicts with ``label``, ``cumple`` and
    ``no_cumple`` counts (mirroring ``ParameterSummary``). Slice labels show
    absolute counts and the centre shows the compliance percentage formatted
    to one decimal, identical to the report table value. Values in the status
    palette keep dark text readable on the light fills. Returns ``None`` when
    the list is empty or every chart has zero rows.
    """
    if not parameters:
        return None

    items = []
    for param in parameters:
        if not isinstance(param, dict):
            continue
        label = str(param.get("label", "") or "")
        ok = int(param.get("cumple", 0) or 0)
        nok = int(param.get("no_cumple", 0) or 0)
        if ok + nok > 0:
            items.append((label, ok, nok))
    if not items:
        return None

    n = len(items)
    fig, axes = plt.subplots(1, n, figsize=(4.0 * n, 4.2))
    axes = list(np.atleast_1d(axes))

    for ax, (label, ok, nok) in zip(axes, items):
        values, slice_labels, colors = [], [], []
        if ok > 0:
            values.append(ok)
            slice_labels.append(f"Cumple\n{ok}")
            colors.append(_DONUT_OK_FILL)
        if nok > 0:
            values.append(nok)
            slice_labels.append(f"No cumple\n{nok}")
            colors.append(_DONUT_NOK_FILL)

        ax.pie(
            values,
            labels=slice_labels,
            colors=colors,
            startangle=90,
            wedgeprops={"width": 0.40, "edgecolor": "white", "linewidth": 1.6},
            textprops={"fontsize": 9, "color": _TEXT_DARK},
        )
        pct = parameter_pct(ok, nok)
        ax.text(
            0, 0, f"{pct:.1f}%\nCumple",
            ha="center", va="center", fontsize=11, fontweight="bold",
            color=_TEXT_DARK,
        )
        ax.set_title(label, fontsize=11, fontweight="bold", pad=8, color="#111827")
        ax.set_aspect("equal")

    fig.tight_layout()
    return _fig_to_png(fig, dpi)


def _section_endpoints(sec: dict) -> Optional[list]:
    poly = sec.get("polyline")
    if poly:
        pts = [(float(p[0]), float(p[1])) for p in poly]
        return pts if len(pts) >= 2 else None
    if all(k in sec for k in ("x0", "y0", "x1", "y1")):
        return [(float(sec["x0"]), float(sec["y0"])),
                (float(sec["x1"]), float(sec["y1"]))]
    origin = sec.get("origin")
    az = sec.get("azimuth")
    length = sec.get("length")
    if origin is not None and az is not None and length is not None:
        az_rad = math.radians(float(az))
        dx, dy = math.sin(az_rad), math.cos(az_rad)
        half = float(length) / 2.0
        return [(float(origin[0]) - dx * half, float(origin[1]) - dy * half),
                (float(origin[0]) + dx * half, float(origin[1]) + dy * half)]
    return None


def _build_plan_view_figure(sections: list, contours=None):
    """Build the compliance plan-view figure, returning ``(fig, ax)`` or ``None``.

    Private helper used by :func:`plan_view_png` and by the structural tests,
    which inspect the axes (lines, labels, legend) without rasterising. Each
    section label sits just beyond its outer endpoint along the section
    direction (no leader lines); dense label sets keep every non-compliant
    section plus the first, the last and every k-th one.
    """
    if not sections:
        return None

    valid = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        pts = _section_endpoints(sec)
        if pts:
            valid.append((sec, pts))
    if not valid:
        return None

    all_x = [p[0] for _s, pts in valid for p in pts]
    all_y = [p[1] for _s, pts in valid for p in pts]
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    x_margin = max((x_max - x_min) * 0.12, 15.0)
    y_margin = max((y_max - y_min) * 0.12, 15.0)
    x_min, x_max = x_min - x_margin, x_max + x_margin
    y_min, y_max = y_min - y_margin, y_max + y_margin
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0

    base_w = 10.0
    base_h = min(max(base_w * y_span / x_span, 4.5), 9.0)
    fig, ax = plt.subplots(figsize=(base_w, base_h))

    if isinstance(contours, dict) and all(k in contours for k in ("x", "y", "z")):
        try:
            from scipy.interpolate import griddata
            cx = np.asarray(contours["x"], dtype=float)
            cy = np.asarray(contours["y"], dtype=float)
            cz = np.asarray(contours["z"], dtype=float)
            if len(cx) > 200000:
                step = len(cx) // 200000
                cx, cy, cz = cx[::step], cy[::step], cz[::step]
            grid_size = int(contours.get("grid_size", 200))
            xi = np.linspace(cx.min(), cx.max(), grid_size)
            yi = np.linspace(cy.min(), cy.max(), grid_size)
            xi_grid, yi_grid = np.meshgrid(xi, yi)
            zi_grid = griddata((cx, cy), cz, (xi_grid, yi_grid), method="linear")
            interval = float(contours.get("interval", 5.0))
            grid_ref = float(contours.get("grid_ref", 0.0))
            z_max = float(np.nanmax(zi_grid))
            levels = np.arange(grid_ref, z_max + interval, interval)
            cs = ax.contour(xi_grid, yi_grid, zi_grid, levels=levels,
                            colors="#8D6E63", linewidths=0.5, alpha=0.6)
            ax.clabel(cs, fontsize=6, fmt="%.0f", colors="#5D4037")
        except Exception:
            pass
    elif isinstance(contours, list):
        for poly in contours:
            if poly and len(poly) >= 2:
                arr = np.asarray(poly, dtype=float)
                ax.plot(arr[:, 0], arr[:, 1], color="#8D6E63",
                        linewidth=0.5, alpha=0.6, zorder=1)

    counts = {s: 0 for s in _STATUS_ORDER}
    for sec, _pts in valid:
        status = sec.get("worst_status") or STATUS_UNKNOWN
        if status not in STATUS_COLORS:
            status = STATUS_UNKNOWN
        counts[status] += 1

    n_valid = len(valid)
    k = max(2, math.ceil(n_valid / 18)) if n_valid > 20 else 1
    span = max(x_span, y_span)
    placed = []
    for idx, (sec, pts) in enumerate(valid):
        status = sec.get("worst_status") or STATUS_UNKNOWN
        if status not in STATUS_COLORS:
            status = STATUS_UNKNOWN
        color = STATUS_COLORS[status]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=3.2, solid_capstyle="round", zorder=5)

        show = (idx % k == 0) or (status != STATUS_CUMPLE) or idx in (0, n_valid - 1)
        if not show:
            continue
        ex, ey = pts[-1]
        px, py = pts[-2]
        dx, dy = ex - px, ey - py
        norm = math.hypot(dx, dy) or 1.0
        ux, uy = dx / norm, dy / norm
        offset = 0.02 * span
        anchor = (ex + ux * offset, ey + uy * offset)
        nx, ny = -uy, ux
        step = 0.03 * span
        for attempt in (0, 1, -1, 2, -2):
            cand = (anchor[0] + nx * step * attempt, anchor[1] + ny * step * attempt)
            if all((cand[0] - p[0]) ** 2 + (cand[1] - p[1]) ** 2 > (step * 1.1) ** 2
                   for p in placed):
                anchor = cand
                break
        placed.append(anchor)
        angle = math.degrees(math.atan2(dy, dx))
        if angle > 90 or angle < -90:
            angle += 180
        ha = "center" if abs(ux) < 0.2 else ("left" if ux > 0 else "right")
        va = "center" if abs(uy) < 0.2 else ("bottom" if uy > 0 else "top")
        ann = ax.annotate(
            str(sec.get("name", "")), xy=anchor, xytext=anchor,
            textcoords="data", fontsize=7, fontweight="bold", color=color,
            rotation=angle, rotation_mode="anchor", ha=ha, va=va,
            zorder=7, clip_on=True,
        )
        ann.set_gid("plan-label")

    handles = [
        Line2D([0], [0], color=STATUS_COLORS[s], lw=3,
               label=f"{STATUS_LABELS_ES[s]} ({counts[s]})")
        for s in _STATUS_ORDER if counts[s] > 0
    ]
    if handles:
        ax.legend(handles=handles, loc="lower right", fontsize=8,
                  framealpha=0.9, title="Estado del perfil (peor banco)",
                  title_fontsize=8)

    ax.set_xlabel("Este (m)", fontsize=9)
    ax.set_ylabel("Norte (m)", fontsize=9)
    ax.set_title("Plano de cumplimiento por perfil (peor banco)",
                 fontsize=12, fontweight="bold")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.2)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)

    ax.annotate(
        "N", xy=(0.965, 0.95), xytext=(0.965, 0.86),
        xycoords="axes fraction", textcoords="axes fraction",
        ha="center", va="bottom", fontsize=9, fontweight="bold",
        arrowprops=dict(facecolor="black", width=2, headwidth=7, headlength=8),
    )
    bar_len = _nice_number(x_span / 5.0)
    bar_frac = bar_len / x_span
    ax.plot([0.06, 0.06 + bar_frac], [0.055, 0.055], transform=ax.transAxes,
            color="black", lw=2.5, solid_capstyle="butt", zorder=6)
    ax.text(0.06 + bar_frac / 2, 0.07, f"{bar_len:g} m", transform=ax.transAxes,
            ha="center", va="bottom", fontsize=7, color="black")

    return fig, ax


def plan_view_png(sections: list, contours=None, dpi: int = 150) -> Optional[bytes]:
    """Render the compliance plan view as PNG bytes.

    Each section dict carries ``name``, ``worst_status`` (CUMPLE, FUERA,
    NO_CUMPLE or UNKNOWN) and geometry as either ``polyline`` (list of x/y
    pairs), ``x0/y0/x1/y1`` or ``origin/azimuth/length``. Lines are coloured by
    the worst-bench status with a Spanish legend that includes per-status
    counts; each label sits just beyond the section's outer endpoint along the
    section direction (rotated to follow it, no leader lines), and dense label
    sets are thinned to every k-th section plus every non-compliant one and
    the first/last section. ``contours`` is optional: a dict with scattered
    ``x``, ``y``, ``z`` (plus optional ``interval``, ``grid_ref``,
    ``grid_size``) for topographic contour lines, or a list of x/y polylines.
    Uses equal aspect with a north arrow and a scale bar. Returns ``None`` when
    no section has usable geometry.
    """
    built = _build_plan_view_figure(sections, contours)
    if built is None:
        return None
    fig, _ax = built
    return _fig_to_png(fig, dpi)


def _build_section_profile_figure(profile: dict, size: str = "full"):
    """Build the annotated section-profile figure, returning ``(fig, ax)`` or ``None``.

    Private helper used by :func:`section_profile_png` and by the structural
    tests, which inspect the axes (tolerance-band patches, bench annotations,
    legend) without rasterising. ``size`` is ``"full"`` (one per page) or
    ``"compact"`` (annex).
    """
    if not isinstance(profile, dict) or not profile:
        return None

    design = _as_series(profile.get("design"))
    topo = _as_series(profile.get("topo"))
    rec_design = _as_series(profile.get("reconciled_design"))
    rec_topo = _as_series(profile.get("reconciled_topo"))
    benches = [b for b in (profile.get("benches") or []) if isinstance(b, dict)]
    blast = [b for b in (profile.get("blast_holes") or []) if isinstance(b, dict)]
    if not any([design, topo, rec_design, rec_topo, benches]):
        return None

    compact = size == "compact"
    figsize = (6.6, 4.6) if compact else (10.0, 8.0)
    fs = 7.5 if compact else 9.5
    fig, ax = plt.subplots(figsize=figsize)

    zs = []
    xs = []

    def _plot(series, color, label, lw, ls="-", alpha=1.0, zorder=3):
        if not series:
            return
        ax.plot(series[0], series[1], color=color, linestyle=ls, linewidth=lw,
                alpha=alpha, label=label, zorder=zorder)
        xs.extend(series[0].tolist())
        zs.extend(series[1].tolist())

    _plot(design, _DESIGN_COLOR, "Diseño", 2.0)
    _plot(topo, _TOPO_COLOR, "Topografía real", 2.0)
    _plot(rec_topo, _RECONCILED_TOPO_COLOR, "Conciliado (real)", 1.8, zorder=4)
    _plot(rec_design, _DESIGN_COLOR, "Conciliado (diseño)", 1.4, ls="--", alpha=0.6)

    band = profile.get("tolerance_band") or {}
    band_verts = []
    band_bounds = None
    for bench in benches:
        cx, cz = _bench_design_point(bench, "crest")
        tx, tz = _bench_design_point(bench, "toe")
        if cx is None or tx is None or cz is None or tz is None:
            continue
        x_lo, x_hi = (float(cx), float(tx)) if cx <= tx else (float(tx), float(cx))
        if x_hi - x_lo <= 0:
            continue
        crest_tol = _tolerance_bounds(band.get("crest"))
        toe_tol = _tolerance_bounds(band.get("toe"))
        if crest_tol is None:
            crest_tol = toe_tol
        if toe_tol is None:
            toe_tol = crest_tol
        if crest_tol is None or toe_tol is None:
            continue
        cneg, cpos = crest_tol
        tneg, tpos = toe_tol
        verts = [
            (float(cx), float(cz) + cpos),
            (float(tx), float(tz) + tpos),
            (float(tx), float(tz) - tneg),
            (float(cx), float(cz) - cneg),
        ]
        band_verts.append(verts)
        if band_bounds is None:
            band_bounds = (cneg, cpos)

    band_drawn = bool(band_verts)
    if band_drawn:
        collection = PolyCollection(band_verts, facecolors=_TOL_COLOR,
                                    edgecolors="none", alpha=0.12, zorder=1)
        collection.set_gid("tol-band")
        ax.add_collection(collection)

    blast_drawn = False
    for hole in blast:
        hx = hole.get("dist")
        collar = hole.get("collar_z")
        toe = hole.get("toe_z")
        tx = hole.get("toe_dist", hx)
        if hx is None or collar is None:
            continue
        if tx is None:
            tx = hx
        if toe is None:
            toe = collar - 1.0
        ax.plot([float(hx), float(tx)], [float(collar), float(toe)],
                color=_BLAST_COLOR, linewidth=1.4, alpha=0.5, zorder=2)
        ax.scatter([float(hx)], [float(collar)], color=_BLAST_COLOR, s=14, zorder=3)
        xs.extend([hx, tx])
        zs.extend([collar, toe])
        blast_drawn = True

    for bench in benches:
        for dist_key, z_key in (("crest_dist", "crest_z"), ("toe_dist", "toe_z")):
            z = bench.get(z_key)
            x = bench.get(dist_key)
            if z is None:
                z = bench.get(f"design_{z_key}")
            if x is None:
                x = bench.get(f"design_{dist_key}")
            if z is not None:
                zs.append(z)
            if x is not None:
                xs.append(x)

    if not zs or not xs:
        plt.close(fig)
        return None

    zmin, zmax = float(np.min(zs)), float(np.max(zs))
    z_pad = max((zmax - zmin) * 0.06, 2.0)
    zmin, zmax = zmin - z_pad, zmax + z_pad
    xmin, xmax = float(np.min(xs)), float(np.max(xs))
    x_span_raw = (xmax - xmin) or 1.0
    x_pad = max(x_span_raw * 0.04, 2.0)
    xmin, xmax = xmin - x_pad, xmax + x_pad
    min_x_span = (zmax - zmin) * 1.2
    if (xmax - xmin) < min_x_span:
        x_mid = (xmin + xmax) / 2
        xmin, xmax = x_mid - min_x_span / 2, x_mid + min_x_span / 2
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(zmin, zmax)

    x_span = (xmax - xmin) or 1.0
    y_span = (zmax - zmin) or 1.0
    base_w = 6.6 if compact else 10.0
    h_min, h_max = (3.0, 6.0) if compact else (5.0, 9.5)
    fig.set_size_inches(base_w, min(max(base_w * y_span / x_span, h_min), h_max))

    placed = []
    for bench in sorted(benches, key=lambda b: (b.get("crest_z") or 0), reverse=True):
        mx, mz = bench.get("crest_dist"), bench.get("crest_z")
        if mx is None or mz is None:
            mx, mz = _bench_design_point(bench, "crest")
        if mx is None or mz is None:
            continue
        status = bench.get("status") or STATUS_CUMPLE
        if status not in STATUS_COLORS:
            status = STATUS_UNKNOWN
        color = STATUS_COLORS[status]
        ax.scatter([mx], [mz], marker="d", s=42, color=color,
                   edgecolor="white", linewidth=0.6,
                   zorder=6 if compact else 7)
        text = _bench_annotation_text(bench)
        if compact:
            ax.annotate(text, xy=(mx, mz), xytext=(4, 4),
                        textcoords="offset points", fontsize=6.5, color=color)
            continue
        fx = (mx - xmin) / x_span
        fz = (mz - zmin) / y_span
        if fz > 0.72:
            offsets = [(0.15, -0.10), (-0.20, -0.10), (0.15, -0.20),
                       (-0.20, -0.20), (0.15, 0.04), (-0.20, 0.04)]
        else:
            offsets = [(0.15, 0.05), (-0.20, 0.05), (0.15, -0.09),
                       (-0.20, -0.09), (0.15, 0.15), (-0.20, 0.15)]
        anchor = None
        for dx, dy in offsets:
            cand = (min(max(fx + dx, 0.02), 0.98), min(max(fz + dy, 0.03), 0.94))
            if all((cand[0] - p[0]) ** 2 + (cand[1] - p[1]) ** 2 > 0.012
                   for p in placed):
                anchor = cand
                break
        if anchor is None:
            anchor = (min(max(fx + 0.02, 0.02), 0.98),
                      min(max(fz + 0.06, 0.03), 0.94))
        placed.append(anchor)
        label_x = xmin + anchor[0] * x_span
        label_z = zmin + anchor[1] * y_span
        leader = Line2D([mx, label_x], [mz, label_z], color=color, lw=0.7,
                        alpha=0.75, zorder=5)
        leader.set_gid("bench-leader")
        ax.add_line(leader)
        label = ax.text(label_x, label_z, text, fontsize=fs, color=color,
                        fontweight="bold", zorder=6)
        label.set_gid("bench-label")

    handles, labels = ax.get_legend_handles_labels()
    if band_drawn:
        neg, pos = band_bounds if band_bounds else (0.0, 0.0)
        handles.append(Rectangle((0, 0), 1, 1, facecolor=_TOL_COLOR, alpha=0.12))
        labels.append(f"Tolerancia de altura (\u2212{neg:g}/+{pos:g} m)")
    if blast_drawn:
        handles.append(Line2D([0], [0], color=_BLAST_COLOR, lw=1.6))
        labels.append("Pozos de tronadura")
    ax.legend(handles, labels, loc="best", fontsize=fs - 1.5, framealpha=0.9,
              labelspacing=0.3, handletextpad=0.4)

    ax.set_title(profile_title(profile), fontsize=fs + 2.5, fontweight="bold")
    ax.set_xlabel("Distancia (m)", fontsize=fs)
    ax.set_ylabel("Elevación (m)", fontsize=fs)
    ax.grid(True, linestyle="--", color="lightgray", alpha=0.7)
    ax.set_aspect("equal", adjustable="box")
    ax.tick_params(labelsize=fs - 0.5)

    return fig, ax


def section_profile_png(profile: dict, size: str = "full", dpi: int = 130) -> Optional[bytes]:
    """Render a large, annotated section profile as PNG bytes.

    ``profile`` carries ``name``, ``sector`` and ``status_label``; series as
    ``design``/``topo`` tuples ``(d[], z[])`` with optional
    ``reconciled_design``/``reconciled_topo``; ``benches`` list of dicts with
    ``label``, ``crest_dist``, ``crest_z``, ``toe_dist``, ``toe_z``,
    ``deviation_text`` and ``status`` (plus optional ``type``/``is_missing``/
    ``is_extra`` for unbuilt or extra benches and optional
    ``design_crest_dist``/``design_crest_z``/``design_toe_dist``/``design_toe_z``
    design corners); an optional ``tolerance_band`` dict with ``crest``/``toe``
    tolerances in metres (scalar for a symmetric band or ``{"neg": ..,
    "pos": ..}`` for the signed session tolerances); and an optional
    ``blast_holes`` list of dicts with ``dist``, ``collar_z`` and ``toe_z``.
    The tolerance is drawn as a translucent band along the design bench face
    (from the design crest to the design toe elevation, spanning only that
    bench's extent). Bench annotations are coloured by their status, read
    ``B3 · no construido``/``adicional`` for missing/extra benches and use
    leader lines with greedy overlap avoidance. ``size`` is ``"full"`` (one per
    page) or ``"compact"`` (annex). Returns ``None`` when there is no geometry
    to draw.
    """
    built = _build_section_profile_figure(profile, size)
    if built is None:
        return None
    fig, _ax = built
    return _fig_to_png(fig, dpi)
