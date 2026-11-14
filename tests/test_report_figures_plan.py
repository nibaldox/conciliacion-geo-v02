"""Tests for core.report_figures_plan — dashboard plan figure over the shaded surface."""
import io
import math

import numpy as np
from matplotlib.colors import to_hex
from PIL import Image
import pytest

from core.report_charts import (
    STATUS_COLORS,
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_LABELS_ES,
    STATUS_NO_CUMPLE,
    STATUS_UNKNOWN,
    _clear_figure,
)
from core.report_figures_plan import _build_plan_figure, dashboard_plan_png
from core.report_surface import PlanSurface, sections_bounds, shaded_relief

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _sections(n=6, spacing=10.0, azimuth=20.0, length=90.0):
    return [
        {
            "name": f"S-{i + 1:02d}",
            "origin": [93_000.0 + spacing * i, 20_400.0 + 0.3 * spacing * i],
            "azimuth": azimuth,
            "length": length,
        }
        for i in range(n)
    ]


def _surface_for(sections):
    xmin, ymin, xmax, ymax = sections_bounds(sections, margin_m=60.0)
    x = np.arange(xmin, xmax + 1.0, 2.0)
    y = np.arange(ymin, ymax + 1.0, 2.0)
    grid_x, grid_y = np.meshgrid(x, y)
    z = 3100.0 + 0.25 * (grid_x - xmin) + 0.1 * (grid_y - ymin)
    z[:5, :5] = np.nan
    return PlanSurface(x=x, y=y, z=z, cell_m=2.0)


def _section_lines(ax):
    return [line for line in ax.lines if line.get_gid() == "plan-section"]


def _labels(ax):
    return [t for t in ax.texts if t.get_gid() == "plan-label"]


def _contours(ax, gid):
    return [c for c in ax.collections if c.get_gid() == gid]


def _contour_levels(ax, gid):
    levels = []
    for collection in _contours(ax, gid):
        levels.extend(float(v) for v in collection.levels)
    return levels


def _crosses(box, start, end):
    """True when the pixel segment start→end touches the pixel bbox (Liang–Barsky)."""
    t0, t1 = 0.0, 1.0
    dx, dy = end[0] - start[0], end[1] - start[1]
    for p, q in ((-dx, start[0] - box.x0), (dx, box.x1 - start[0]),
                 (-dy, start[1] - box.y0), (dy, box.y1 - start[1])):
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


def _furniture_boxes(ax, renderer):
    return [p.get_window_extent(renderer) for p in ax.patches if p.get_gid() == "plan-furniture"]


def _lines_crossing(ax, boxes):
    crossing = []
    for index, line in enumerate(_section_lines(ax)):
        pixels = ax.transData.transform(np.column_stack([line.get_xdata(), line.get_ydata()]))
        if any(_crosses(box, pixels[0], pixels[-1]) for box in boxes):
            crossing.append(index)
    return crossing


def _x_layout(n=40, length=40.0):
    sections = []
    for arm, (slope, azimuth) in enumerate(((0.55, 331.0), (-0.55, 29.0))):
        for i in range(n):
            x = 93_000.0 + 15.0 * i
            y = 20_400.0 + slope * 15.0 * (i - (n - 1) / 2.0)
            sections.append({
                "name": f"{'AB'[arm]}-{i + 1:02d}", "origin": [x, y],
                "azimuth": azimuth, "length": length,
            })
    return sections


def _assert_labels_clear(fig, ax):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    labels = _labels(ax)
    boxes = [t.get_window_extent(renderer) for t in labels]
    names = [t.get_text() for t in labels]
    for i, first in enumerate(boxes):
        for second in boxes[i + 1:]:
            assert not first.overlaps(second), names
    axes_box = ax.get_window_extent(renderer)
    obstacles = [ax.get_legend().get_window_extent(renderer)] + _furniture_boxes(ax, renderer)
    for name, box in zip(names, boxes):
        assert axes_box.x0 <= box.x0 and box.x1 <= axes_box.x1, name
        assert axes_box.y0 <= box.y0 and box.y1 <= axes_box.y1, name
        assert not any(box.overlaps(obstacle) for obstacle in obstacles), name


@pytest.fixture
def built():
    figures = []

    def build(*args, **kwargs):
        result = _build_plan_figure(*args, **kwargs)
        if result is not None:
            figures.append(result[0])
        return result

    yield build
    for fig in figures:
        _clear_figure(fig)


class TestBuildPlanFigure:
    def test_none_without_section_endpoints(self, built):
        assert built([], {}) is None
        assert built(None, {}) is None
        assert built([{"name": "S-01"}], {"S-01": STATUS_CUMPLE}) is None

    def test_one_line_per_section_coloured_by_status(self, built):
        sections = _sections(4)
        statuses = {
            "S-01": STATUS_CUMPLE,
            "S-02": STATUS_FUERA,
            "S-03": STATUS_NO_CUMPLE,
        }
        _fig, ax = built(sections, statuses)
        lines = _section_lines(ax)
        assert len(lines) == 4
        colours = [to_hex(line.get_color()).upper() for line in lines]
        assert colours == [
            STATUS_COLORS[STATUS_CUMPLE].upper(),
            STATUS_COLORS[STATUS_FUERA].upper(),
            STATUS_COLORS[STATUS_NO_CUMPLE].upper(),
            STATUS_COLORS[STATUS_UNKNOWN].upper(),
        ]

    def test_unrecognised_status_uses_unknown_colour(self, built):
        sections = _sections(2)
        _fig, ax = built(sections, {"S-01": "???", "S-02": None})
        colours = {to_hex(line.get_color()).upper() for line in _section_lines(ax)}
        assert colours == {STATUS_COLORS[STATUS_UNKNOWN].upper()}

    def test_compliance_status_spellings_are_accepted(self, built):
        sections = _sections(2)
        _fig, ax = built(sections, {"S-01": "FUERA DE TOLERANCIA", "S-02": "NO CUMPLE"})
        colours = [to_hex(line.get_color()).upper() for line in _section_lines(ax)]
        assert colours == [STATUS_COLORS[STATUS_FUERA].upper(), STATUS_COLORS[STATUS_NO_CUMPLE].upper()]

    def test_section_line_geometry_matches_endpoints(self, built):
        sections = [{"name": "S-01", "x0": 10.0, "y0": 20.0, "x1": 110.0, "y1": 70.0}]
        _fig, ax = built(sections, {})
        line = _section_lines(ax)[0]
        assert list(line.get_xdata()) == [10.0, 110.0]
        assert list(line.get_ydata()) == [20.0, 70.0]

    def test_limits_contain_sections_with_margin_at_equal_scale(self, built):
        sections = _sections(6)
        fig, ax = built(sections, {})
        xmin, ymin, xmax, ymax = sections_bounds(sections)
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        assert x0 <= xmin + 1e-6 and x1 >= xmax - 1e-6
        assert y0 <= ymin + 1e-6 and y1 >= ymax - 1e-6
        fig.canvas.draw()
        box = ax.get_window_extent()
        assert (x1 - x0) / box.width == pytest.approx((y1 - y0) / box.height, rel=1e-3)

    def test_figure_size_follows_arguments(self, built):
        fig, _ax = built(_sections(3), {}, width_in=5.0, height_in=3.0)
        assert tuple(fig.get_size_inches()) == pytest.approx((5.0, 3.0))

    def test_legend_has_spanish_labels_with_counts(self, built):
        sections = _sections(5)
        statuses = {
            "S-01": STATUS_CUMPLE, "S-02": STATUS_CUMPLE, "S-03": STATUS_NO_CUMPLE,
            "S-04": STATUS_FUERA,
        }
        _fig, ax = built(sections, statuses)
        texts = [t.get_text() for t in ax.get_legend().get_texts()]
        assert f"{STATUS_LABELS_ES[STATUS_CUMPLE]} (2)" in texts
        assert f"{STATUS_LABELS_ES[STATUS_FUERA]} (1)" in texts
        assert f"{STATUS_LABELS_ES[STATUS_NO_CUMPLE]} (1)" in texts
        assert f"{STATUS_LABELS_ES[STATUS_UNKNOWN]} (1)" in texts

    def test_legend_omits_unknown_when_every_section_has_status(self, built):
        sections = _sections(2)
        _fig, ax = built(sections, {"S-01": STATUS_CUMPLE, "S-02": STATUS_CUMPLE})
        texts = [t.get_text() for t in ax.get_legend().get_texts()]
        assert f"{STATUS_LABELS_ES[STATUS_CUMPLE]} (2)" in texts
        assert f"{STATUS_LABELS_ES[STATUS_NO_CUMPLE]} (0)" in texts
        assert not any(t.startswith(STATUS_LABELS_ES[STATUS_UNKNOWN]) for t in texts)

    def test_north_arrow_and_round_scale_bar(self, built):
        sections = _sections(6)
        _fig, ax = built(sections, {})
        north = [t for t in ax.texts if t.get_gid() == "plan-north"]
        assert len(north) == 1 and north[0].get_text() == "N"
        bar = [line for line in ax.lines if line.get_gid() == "plan-scale-bar"]
        assert len(bar) == 1
        xs = bar[0].get_xdata()
        length = float(xs[-1] - xs[0])
        mantissa = length / 10 ** math.floor(math.log10(length))
        assert mantissa == pytest.approx(1.0) or mantissa == pytest.approx(2.0) or mantissa == pytest.approx(5.0)
        x0, x1 = ax.get_xlim()
        assert length <= 0.35 * (x1 - x0)
        label = [t for t in ax.texts if t.get_gid() == "plan-scale-label"]
        assert len(label) == 1 and label[0].get_text() == f"{length:g} m"

    def test_axis_labels_in_spanish(self, built):
        _fig, ax = built(_sections(3), {})
        assert ax.get_xlabel() == "Este (m)"
        assert ax.get_ylabel() == "Norte (m)"

    def test_few_sections_are_all_labelled(self, built):
        sections = _sections(4, spacing=40.0)
        _fig, ax = built(sections, {})
        assert [t.get_text() for t in _labels(ax)] == ["S-01", "S-02", "S-03", "S-04"]

    def test_dense_labels_are_thinned_without_overlap(self, built):
        sections = _sections(96, spacing=6.0)
        statuses = {s["name"]: STATUS_CUMPLE for s in sections}
        statuses["S-40"] = STATUS_NO_CUMPLE
        fig, ax = built(sections, statuses)
        labels = _labels(ax)
        names = [t.get_text() for t in labels]
        assert 2 < len(names) < 96
        assert "S-01" in names and "S-96" in names
        assert "S-40" in names
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        boxes = [t.get_window_extent(renderer) for t in labels]
        for i, first in enumerate(boxes):
            for second in boxes[i + 1:]:
                assert not first.overlaps(second), names
        axes_box = ax.get_window_extent(renderer)
        for box in boxes:
            assert axes_box.x0 <= box.x0 and box.x1 <= axes_box.x1
            assert axes_box.y0 <= box.y0 and box.y1 <= axes_box.y1

    def test_thinned_labels_are_regularly_spaced(self, built):
        sections = _sections(96, spacing=6.0)
        _fig, ax = built(sections, {})
        indexes = sorted(int(t.get_text().split("-")[1]) - 1 for t in _labels(ax))
        steps = set(np.diff(indexes[:-1]).tolist())
        assert len(steps) == 1
        assert indexes[0] == 0 and indexes[-1] == 95

    def test_non_compliant_label_uses_status_colour(self, built):
        sections = _sections(4, spacing=40.0)
        _fig, ax = built(sections, {"S-02": STATUS_NO_CUMPLE, "S-01": STATUS_CUMPLE})
        by_name = {t.get_text(): t for t in _labels(ax)}
        assert to_hex(by_name["S-02"].get_color()).upper() == STATUS_COLORS[STATUS_NO_CUMPLE].upper()
        assert to_hex(by_name["S-01"].get_color()).upper() != STATUS_COLORS[STATUS_NO_CUMPLE].upper()

    def test_neighbouring_non_compliant_sections_are_all_labelled(self, built):
        sections = _sections(96, spacing=6.0)
        statuses = {s["name"]: STATUS_CUMPLE for s in sections}
        flagged = {"S-22": STATUS_NO_CUMPLE, "S-23": STATUS_FUERA, "S-25": STATUS_NO_CUMPLE,
                   "S-40": STATUS_NO_CUMPLE}
        statuses.update(flagged)
        fig, ax = built(sections, statuses)
        by_name = {t.get_text(): t for t in _labels(ax)}
        assert set(flagged) <= set(by_name)
        for name, status in flagged.items():
            assert to_hex(by_name[name].get_color()).upper() == STATUS_COLORS[status].upper()
        assert "S-01" in by_name and "S-96" in by_name
        assert len(by_name) < 96
        _assert_labels_clear(fig, ax)

    def test_run_of_non_compliant_sections_is_fully_labelled(self, built):
        sections = _sections(96, spacing=6.0)
        statuses = {s["name"]: STATUS_CUMPLE for s in sections}
        run = [f"S-{i:02d}" for i in range(30, 42)]
        statuses.update({name: STATUS_NO_CUMPLE for name in run})
        fig, ax = built(sections, statuses)
        names = {t.get_text() for t in _labels(ax)}
        assert set(run) <= names
        _assert_labels_clear(fig, ax)

    def test_majority_noncompliant_is_thinned(self, built):
        sections = _sections(96, spacing=6.0)
        fig, ax = built(sections, {s["name"]: STATUS_NO_CUMPLE for s in sections})
        assert 2 < len(_labels(ax)) < len(sections)
        _assert_labels_clear(fig, ax)

    def test_non_compliant_first_and_last_keep_their_labels(self, built):
        sections = _sections(96, spacing=6.0)
        statuses = {s["name"]: STATUS_CUMPLE for s in sections}
        statuses.update({"S-01": STATUS_NO_CUMPLE, "S-02": STATUS_NO_CUMPLE, "S-95": STATUS_FUERA})
        fig, ax = built(sections, statuses)
        names = {t.get_text() for t in _labels(ax)}
        assert {"S-01", "S-02", "S-95", "S-96"} <= names
        _assert_labels_clear(fig, ax)

    def test_displaced_label_is_tied_to_its_section_by_a_leader(self, built):
        sections = _sections(96, spacing=6.0)
        statuses = {s["name"]: STATUS_CUMPLE for s in sections}
        run = [f"S-{i:02d}" for i in range(30, 42)]
        statuses.update({name: STATUS_NO_CUMPLE for name in run})
        _fig, ax = built(sections, statuses)
        leaders = [line for line in ax.lines if line.get_gid() == "plan-label-leader"]
        assert leaders
        ends = {
            (round(float(x), 3), round(float(y), 3))
            for line in _section_lines(ax) for x, y in zip(line.get_xdata(), line.get_ydata())
        }
        for leader in leaders:
            start = (round(float(leader.get_xdata()[0]), 3), round(float(leader.get_ydata()[0]), 3))
            assert start in ends
            assert to_hex(leader.get_color()).upper() == STATUS_COLORS[STATUS_NO_CUMPLE].upper()

    def test_compliant_only_plan_has_no_leaders(self, built):
        sections = _sections(96, spacing=6.0)
        _fig, ax = built(sections, {s["name"]: STATUS_CUMPLE for s in sections})
        assert [line for line in ax.lines if line.get_gid() == "plan-label-leader"] == []

    def test_scale_bar_and_north_arrow_cross_no_section_line_when_corners_are_busy(self, built):
        sections = _x_layout()
        fig, ax = built(sections, {})
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        boxes = _furniture_boxes(ax, renderer)
        assert len(boxes) == 2
        assert _lines_crossing(ax, boxes) == []
        bar = next(line for line in ax.lines if line.get_gid() == "plan-scale-bar")
        assert _lines_crossing(ax, [bar.get_window_extent(renderer)]) == []
        axes_box = ax.get_window_extent(renderer)
        legend_box = ax.get_legend().get_window_extent(renderer)
        for box in boxes:
            assert axes_box.x0 - 1 <= box.x0 and box.x1 <= axes_box.x1 + 1
            assert axes_box.y0 - 1 <= box.y0 and box.y1 <= axes_box.y1 + 1
            assert not box.overlaps(legend_box)
        assert not boxes[0].overlaps(boxes[1])

    def test_legend_crosses_no_section_line_when_corners_are_busy(self, built):
        fig, ax = built(_x_layout(), {})
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        assert _lines_crossing(ax, [ax.get_legend().get_window_extent(renderer)]) == []

    @pytest.mark.parametrize("slope", [-0.6, 0.6])
    def test_furniture_boxes_cross_no_section_segment(self, built, slope):
        sections = [
            {
                "name": f"S-{i + 1:02d}",
                "origin": [93_000.0 + 9.0 * i, 20_400.0 + slope * 9.0 * i],
                "azimuth": 25.0 if slope < 0 else 335.0,
                "length": 60.0,
            }
            for i in range(96)
        ]
        fig, ax = built(sections, {})
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        boxes = _furniture_boxes(ax, renderer) + [ax.get_legend().get_window_extent(renderer)]
        assert _lines_crossing(ax, boxes) == []

    def test_furniture_stays_in_a_corner_when_one_is_free(self, built):
        fig, ax = built(_sections(96, spacing=6.0), {})
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        axes_box = ax.get_window_extent(renderer)
        north, = [t for t in ax.texts if t.get_gid() == "plan-north"]
        box = next(b for b in _furniture_boxes(ax, renderer)
                   if b.contains(*ax.transData.transform(north.xyann)))
        near_side = min(box.x0 - axes_box.x0, axes_box.x1 - box.x1)
        near_edge = min(box.y0 - axes_box.y0, axes_box.y1 - box.y1)
        assert near_side <= 0.03 * axes_box.width
        assert near_edge <= 0.05 * axes_box.height

    def test_labels_avoid_legend_north_arrow_and_scale(self, built):
        sections = _sections(96, spacing=6.0)
        fig, ax = built(sections, {})
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        obstacles = [ax.get_legend().get_window_extent(renderer)]
        obstacles += [p.get_window_extent(renderer) for p in ax.patches if p.get_gid() == "plan-furniture"]
        assert len(obstacles) == 3
        for label in _labels(ax):
            box = label.get_window_extent(renderer)
            assert not any(box.overlaps(obstacle) for obstacle in obstacles), label.get_text()

    @pytest.mark.parametrize("slope", [-0.6, 0.6])
    def test_legend_and_furniture_do_not_cover_sections(self, built, slope):
        sections = [
            {
                "name": f"S-{i + 1:02d}",
                "origin": [93_000.0 + 9.0 * i, 20_400.0 + slope * 9.0 * i],
                "azimuth": 25.0 if slope < 0 else 335.0,
                "length": 40.0,
            }
            for i in range(96)
        ]
        fig, ax = built(sections, {})
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        obstacles = [ax.get_legend().get_window_extent(renderer)]
        obstacles += [p.get_window_extent(renderer) for p in ax.patches if p.get_gid() == "plan-furniture"]
        for line in _section_lines(ax):
            xs = np.linspace(line.get_xdata()[0], line.get_xdata()[-1], 9)
            ys = np.linspace(line.get_ydata()[0], line.get_ydata()[-1], 9)
            pixels = ax.transData.transform(np.column_stack([xs, ys]))
            for obstacle in obstacles:
                assert not any(obstacle.contains(px, py) for px, py in pixels)
        names = [t.get_text() for t in _labels(ax)]
        assert "S-01" in names and "S-96" in names

    def test_furniture_stays_inside_the_axes(self, built):
        fig, ax = built(_sections(96, spacing=6.0), {})
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        axes_box = ax.get_window_extent(renderer)
        boxes = [ax.get_legend().get_window_extent(renderer)]
        boxes += [p.get_window_extent(renderer) for p in ax.patches if p.get_gid() == "plan-furniture"]
        for box in boxes:
            assert axes_box.x0 - 1 <= box.x0 and box.x1 <= axes_box.x1 + 1
            assert axes_box.y0 - 1 <= box.y0 and box.y1 <= axes_box.y1 + 1
        assert not boxes[0].overlaps(boxes[1]) and not boxes[0].overlaps(boxes[2])

    def test_no_surface_layers_without_inputs(self, built):
        _fig, ax = built(_sections(3), {})
        assert len(ax.images) == 0
        assert _contours(ax, "plan-contour-major") == []
        assert _contours(ax, "plan-contour-minor") == []

    def test_shade_is_drawn_in_grey_with_given_extent(self, built):
        sections = _sections(6)
        surface = _surface_for(sections)
        shade = shaded_relief(surface)
        _fig, ax = built(sections, {}, shade=shade)
        assert len(ax.images) == 1
        image = ax.images[0]
        assert image.get_extent() == pytest.approx(list(shade[1]))
        assert image.origin == "lower"
        rgba = image.cmap(image.norm(np.array([0.0, 0.5, 1.0])))
        np.testing.assert_allclose(rgba[:, 0], rgba[:, 1])
        np.testing.assert_allclose(rgba[:, 1], rgba[:, 2])
        assert rgba[0, 0] < rgba[1, 0] < rgba[2, 0]
        data = image.get_array()
        assert np.ma.is_masked(data)
        assert data.mask[0, 0]
        assert image.cmap(image.norm(data))[0, 0, 3] == 0.0

    def test_contours_major_every_25_minor_every_5(self, built):
        sections = _sections(6)
        surface = _surface_for(sections)
        _fig, ax = built(sections, {}, surface=surface)
        major = _contour_levels(ax, "plan-contour-major")
        minor = _contour_levels(ax, "plan-contour-minor")
        assert major and minor
        assert all(level % 25 == 0 for level in major)
        assert all(level % 5 == 0 and level % 25 != 0 for level in minor)
        z_min, z_max = np.nanmin(surface.z), np.nanmax(surface.z)
        assert min(major) >= z_min - 10 and max(major) <= z_max + 10
        labels = [t.get_text() for t in ax.texts if t.get_gid() == "plan-contour-label"]
        assert labels
        assert all(float(text.replace("\u00a0", "")) % 25 == 0 for text in labels)
        major_width = _contours(ax, "plan-contour-major")[0].get_linewidths()[0]
        minor_width = _contours(ax, "plan-contour-minor")[0].get_linewidths()[0]
        assert minor_width < major_width

    def test_legend_explains_contours_when_surface_given(self, built):
        sections = _sections(6)
        _fig, ax = built(sections, {}, surface=_surface_for(sections))
        texts = [t.get_text() for t in ax.get_legend().get_texts()]
        assert any("25 m" in text for text in texts)
        assert any("5 m" in text for text in texts)

    def test_sections_stay_above_surface_layers(self, built):
        sections = _sections(6)
        surface = _surface_for(sections)
        _fig, ax = built(sections, {}, shade=shaded_relief(surface), surface=surface)
        top_surface = max(
            [ax.images[0].get_zorder()]
            + [c.get_zorder() for c in _contours(ax, "plan-contour-major")]
            + [c.get_zorder() for c in _contours(ax, "plan-contour-minor")]
        )
        assert all(line.get_zorder() > top_surface for line in _section_lines(ax))

    def test_all_nan_surface_draws_no_contours(self, built):
        sections = _sections(3)
        surface = _surface_for(sections)
        empty = PlanSurface(x=surface.x, y=surface.y, z=np.full_like(surface.z, np.nan), cell_m=2.0)
        _fig, ax = built(sections, {}, shade=shaded_relief(empty), surface=empty)
        assert _contours(ax, "plan-contour-major") == []
        assert len(_section_lines(ax)) == 3


class TestDashboardPlanPng:
    def test_none_without_sections(self):
        assert dashboard_plan_png([], {}) is None
        assert dashboard_plan_png([{"name": "S-01"}], {"S-01": STATUS_CUMPLE}) is None

    def test_png_signature_and_size(self):
        sections = _sections(8)
        surface = _surface_for(sections)
        png = dashboard_plan_png(
            sections, {"S-01": STATUS_CUMPLE, "S-02": STATUS_NO_CUMPLE},
            shade=shaded_relief(surface), surface=surface,
        )
        assert png.startswith(PNG_SIGNATURE)
        image = Image.open(io.BytesIO(png))
        image.load()
        assert 0.9 * 7.0 * 150 <= image.size[0] <= 1.1 * 7.0 * 150
        assert 0.9 * 4.2 * 150 <= image.size[1] <= 1.1 * 4.2 * 150

    def test_png_without_surface(self):
        png = dashboard_plan_png(_sections(3), {}, width_in=4.0, height_in=3.0, dpi=80)
        assert png.startswith(PNG_SIGNATURE)
        image = Image.open(io.BytesIO(png))
        assert image.size[0] <= 1.15 * 4.0 * 80


def test_effective_plan_font_at_pdf_placed_width(built):
    from matplotlib.text import Text
    sections = _sections(6)
    surface = _surface_for(sections)
    fig, _ = built(sections, {}, surface=surface)
    fig.canvas.draw()
    sizes = [t.get_fontsize() for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
    png = dashboard_plan_png(sections, {}, surface=surface)
    pixels = Image.open(io.BytesIO(png)).width
    placed_width_in = 1078 / 152
    assert min(sizes) * placed_width_in / (pixels / 150) >= 6
