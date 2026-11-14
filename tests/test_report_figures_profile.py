"""Tests for core.report_figures_profile — cropped profile panel and locator map."""
import math
from types import SimpleNamespace

import numpy as np
from matplotlib.colors import to_hex, to_rgba
import pytest

from core.report_charts import STATUS_COLORS, STATUS_LABELS_ES
from core.report_figures_profile import (
    MIN_FONT_PT,
    OTHER_SECTION_COLOR,
    OVER_EXCAVATION_COLOR,
    UNDER_EXCAVATION_COLOR,
    _build_locator_figure,
    _build_profile_figure,
    cropped_profile_png,
    locator_map_png,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _bench(number, crest_d, crest_z, toe_d, toe_z):
    return SimpleNamespace(
        bench_number=number,
        crest_distance=crest_d,
        crest_elevation=crest_z,
        toe_distance=toe_d,
        toe_elevation=toe_z,
        bench_height=crest_z - toe_z,
        face_angle=70.0,
        berm_width=10.0,
    )


def _entry(view_window=(-10.0, 15.0, 102.5, 132.5), name="S-01", empty=False):
    design_d = np.array([-30.0, -15.0, -10.0, 0.0, 5.0, 15.0, 20.0, 30.0])
    design_z = np.array([140.0, 140.0, 125.0, 125.0, 110.0, 110.0, 95.0, 95.0])
    topo_d = np.linspace(-30.0, 30.0, 121)
    topo_z = np.interp(topo_d, design_d, design_z) + 2.0 * np.sin(topo_d / 4.0)
    if empty:
        design_d = design_z = topo_d = topo_z = np.array([])
    return {
        "section_name": name,
        "sector": "Norte",
        "view_window": view_window,
        "warnings": [],
        "params_design": SimpleNamespace(benches=[_bench(2, 0.0, 125.0, 5.0, 110.0)]),
        "params_topo": SimpleNamespace(benches=[_bench(2, 0.5, 124.0, 5.5, 110.5)]),
        "profile_d": (design_d, design_z),
        "profile_t": (topo_d, topo_z),
    }


def _axes_ratio(fig, ax):
    width_in, height_in = fig.get_size_inches()
    box = ax.get_position()
    return (box.width * width_in) / (box.height * height_in)


def _fills(ax, gid):
    return [c for c in ax.collections if c.get_gid() == gid]


def _sections(n=8, spacing=20.0):
    return [
        {
            "name": f"S-{i + 1:02d}",
            "origin": [1000.0 + spacing * i, 5000.0 + 2.0 * i],
            "azimuth": 20.0,
            "length": 40.0,
            "length_up": 20.0,
            "length_down": 20.0,
            "sector": "Norte",
        }
        for i in range(n)
    ]


def _lines(ax, gid):
    return [line for line in ax.lines if line.get_gid() == gid]


class TestCroppedProfile:
    def test_returns_none_when_both_profiles_are_empty(self):
        assert _build_profile_figure(_entry(empty=True)) is None
        assert cropped_profile_png(_entry(empty=True)) is None

    def test_returns_none_for_missing_entry(self):
        assert cropped_profile_png(None) is None
        assert cropped_profile_png({}) is None

    def test_returns_png_bytes(self):
        png = cropped_profile_png(_entry(), status="CUMPLE")
        assert isinstance(png, bytes)
        assert png.startswith(PNG_SIGNATURE)

    def test_limits_contain_window_at_one_to_one_scale(self):
        window = (-10.0, 15.0, 102.5, 132.5)
        fig, ax = _build_profile_figure(_entry(window))
        x0, x1 = ax.get_xlim()
        z0, z1 = ax.get_ylim()
        assert x0 <= window[0] + 1e-9 and x1 >= window[1] - 1e-9
        assert z0 <= window[2] + 1e-9 and z1 >= window[3] - 1e-9
        assert (x1 - x0) / (z1 - z0) == pytest.approx(_axes_ratio(fig, ax), rel=1e-6)

    def test_short_axis_is_enlarged_symmetrically_and_long_axis_kept(self):
        window = (-10.0, 15.0, 102.5, 132.5)
        _fig, ax = _build_profile_figure(_entry(window))
        x0, x1 = ax.get_xlim()
        z0, z1 = ax.get_ylim()
        assert (window[0] - x0) == pytest.approx(x1 - window[1])
        assert (window[2] - z0) == pytest.approx(z1 - window[3])
        tight_x = math.isclose(x1 - x0, window[1] - window[0])
        tight_z = math.isclose(z1 - z0, window[3] - window[2])
        assert tight_x or tight_z

    def test_wide_window_enlarges_the_vertical_axis(self):
        window = (-25.0, 25.0, 108.0, 127.0)
        fig, ax = _build_profile_figure(_entry(window))
        x0, x1 = ax.get_xlim()
        z0, z1 = ax.get_ylim()
        assert (x0, x1) == pytest.approx((window[0], window[1]))
        assert z0 < window[2] and z1 > window[3]
        assert (x1 - x0) / (z1 - z0) == pytest.approx(_axes_ratio(fig, ax), rel=1e-6)

    def test_without_window_limits_contain_whole_profile(self):
        entry = _entry(view_window=None)
        fig, ax = _build_profile_figure(entry)
        x0, x1 = ax.get_xlim()
        z0, z1 = ax.get_ylim()
        for dist, elev in (entry["profile_d"], entry["profile_t"]):
            assert x0 <= dist.min() and x1 >= dist.max()
            assert z0 <= elev.min() and z1 >= elev.max()
        assert (x1 - x0) / (z1 - z0) == pytest.approx(_axes_ratio(fig, ax), rel=1e-6)

    def test_fill_polygons_use_frozen_colours(self):
        assert OVER_EXCAVATION_COLOR == "#3b82f6"
        assert UNDER_EXCAVATION_COLOR == "#f97316"
        _fig, ax = _build_profile_figure(_entry())
        over = _fills(ax, "over-excavation")
        under = _fills(ax, "under-excavation")
        assert len(over) == 1 and len(under) == 1
        assert tuple(over[0].get_facecolor()[0]) == pytest.approx(to_rgba("#3b82f6", 0.35))
        assert tuple(under[0].get_facecolor()[0]) == pytest.approx(to_rgba("#f97316", 0.35))

    def test_fill_stays_inside_the_window(self):
        window = (-10.0, 15.0, 102.5, 132.5)
        _fig, ax = _build_profile_figure(_entry(window))
        for gid in ("over-excavation", "under-excavation"):
            for collection in _fills(ax, gid):
                for path in collection.get_paths():
                    verts = np.asarray(path.vertices)
                    assert verts[:, 0].min() >= window[0] - 1e-6
                    assert verts[:, 0].max() <= window[1] + 1e-6
                    assert verts[:, 1].min() >= window[2] - 1e-6
                    assert verts[:, 1].max() <= window[3] + 1e-6

    def test_over_excavation_is_topo_below_design(self):
        entry = _entry()
        dist = np.linspace(-30.0, 30.0, 61)
        entry["profile_d"] = (dist, np.full_like(dist, 120.0))
        entry["profile_t"] = (dist, np.full_like(dist, 118.0))
        _fig, ax = _build_profile_figure(entry)
        over_paths = [p for c in _fills(ax, "over-excavation") for p in c.get_paths()]
        under_paths = [p for c in _fills(ax, "under-excavation") for p in c.get_paths()]
        assert over_paths and not under_paths
        verts = np.asarray(over_paths[0].vertices)
        assert verts[:, 1].min() == pytest.approx(118.0)
        assert verts[:, 1].max() == pytest.approx(120.0)

    def test_no_fill_with_a_single_profile(self):
        entry = _entry()
        entry["profile_t"] = (np.array([]), np.array([]))
        fig, ax = _build_profile_figure(entry)
        assert not _fills(ax, "over-excavation") and not _fills(ax, "under-excavation")
        labels = [t.get_text() for t in fig.legends[0].get_texts()]
        assert labels == ["Diseño"]

    def test_title_has_section_name_and_spanish_status(self):
        for status in ("CUMPLE", "FUERA", "NO_CUMPLE"):
            _fig, ax = _build_profile_figure(_entry(name="S-07"), status=status)
            assert ax.get_title() == f"S-07 · {STATUS_LABELS_ES[status]}"
            assert to_hex(ax.title.get_color()) == STATUS_COLORS[status].lower()

    def test_title_accepts_row_status_spelling(self):
        _fig, ax = _build_profile_figure(_entry(), status="NO CUMPLE")
        assert ax.get_title() == "S-01 · No cumple"
        _fig, ax = _build_profile_figure(_entry(), status="FUERA DE TOLERANCIA")
        assert ax.get_title() == "S-01 · Fuera de tolerancia"

    def test_title_without_status_is_the_section_name(self):
        _fig, ax = _build_profile_figure(_entry(name="S-09"))
        assert ax.get_title() == "S-09"

    def test_legend_has_four_entries_once_and_readable(self):
        fig, ax = _build_profile_figure(_entry())
        assert ax.get_legend() is None
        assert len(fig.legends) == 1
        texts = fig.legends[0].get_texts()
        assert [t.get_text() for t in texts] == [
            "Diseño", "As-built", "Sobreexcavación", "Subexcavación",
        ]
        assert all(t.get_fontsize() >= 5.6 for t in texts)

    def test_every_text_is_at_least_min_font(self):
        assert MIN_FONT_PT >= 5.6
        fig, ax = _build_profile_figure(_entry(), status="CUMPLE")
        sizes = [t.get_fontsize() for t in ax.texts]
        sizes += [t.get_fontsize() for t in ax.get_xticklabels() + ax.get_yticklabels()]
        sizes += [ax.xaxis.label.get_fontsize(), ax.yaxis.label.get_fontsize(),
                  ax.title.get_fontsize()]
        assert min(sizes) >= 5.6

    def test_bench_label_per_design_bench_in_view(self):
        entry = _entry(view_window=None)
        entry["params_design"] = SimpleNamespace(benches=[
            _bench(1, -15.0, 140.0, -10.0, 125.0),
            _bench(2, 0.0, 125.0, 5.0, 110.0),
            _bench(3, 15.0, 110.0, 20.0, 95.0),
        ])
        _fig, ax = _build_profile_figure(entry)
        labels = [t for t in ax.texts if t.get_gid() == "bench-label"]
        assert sorted(t.get_text() for t in labels) == ["B1", "B2", "B3"]

    def test_bench_label_points_at_design_crest(self):
        _fig, ax = _build_profile_figure(_entry())
        labels = [t for t in ax.texts if t.get_gid() == "bench-label"]
        assert [t.get_text() for t in labels] == ["B2"]
        assert tuple(labels[0].xy) == pytest.approx((0.0, 125.0))

    def test_bench_outside_window_gets_no_label(self):
        entry = _entry()
        entry["params_design"] = SimpleNamespace(benches=[
            _bench(1, -15.0, 140.0, -10.0, 125.0),
            _bench(2, 0.0, 125.0, 5.0, 110.0),
        ])
        _fig, ax = _build_profile_figure(entry)
        x0, x1 = ax.get_xlim()
        z0, z1 = ax.get_ylim()
        assert not (z0 <= 140.0 <= z1 and x0 <= -15.0 <= x1)
        labels = [t.get_text() for t in ax.texts if t.get_gid() == "bench-label"]
        assert labels == ["B2"]

    def test_bench_label_never_overlaps_title(self):
        window = (-25.0, 25.0, 108.0, 125.0)
        fig, ax = _build_profile_figure(_entry(window), status="NO_CUMPLE")
        z1 = ax.get_ylim()[1]
        entry = _entry(window)
        entry["params_design"] = SimpleNamespace(benches=[_bench(2, 0.0, z1, 5.0, 110.0)])
        fig, ax = _build_profile_figure(entry, status="NO_CUMPLE")
        renderer = fig.canvas.get_renderer()
        fig.draw(renderer)
        labels = [t for t in ax.texts if t.get_gid() == "bench-label"]
        assert len(labels) == 1
        label_box = labels[0].get_window_extent(renderer)
        title_box = ax.title.get_window_extent(renderer)
        axes_box = ax.get_window_extent(renderer)
        assert not label_box.overlaps(title_box)
        assert label_box.y1 <= axes_box.y1 + 0.5
        assert label_box.x0 >= axes_box.x0 - 0.5 and label_box.x1 <= axes_box.x1 + 0.5

    def test_missing_bench_coordinates_are_skipped(self):
        entry = _entry()
        entry["params_design"] = SimpleNamespace(benches=[
            _bench(2, float("nan"), 125.0, 5.0, 110.0),
        ])
        _fig, ax = _build_profile_figure(entry)
        assert not [t for t in ax.texts if t.get_gid() == "bench-label"]

    def test_non_finite_samples_are_ignored(self):
        entry = _entry()
        dist, elev = entry["profile_t"]
        elev = elev.copy()
        elev[10:14] = np.nan
        entry["profile_t"] = (dist, elev)
        _fig, ax = _build_profile_figure(entry)
        assert all(np.isfinite(ax.get_xlim())) and all(np.isfinite(ax.get_ylim()))

    @pytest.mark.parametrize("size", [(3.6, 2.6), (8.0, 5.0), (5.0, 7.0)])
    def test_layout_leaves_no_blank_band_above_the_legend(self, size):
        fig, ax = _build_profile_figure(_entry(), "NO_CUMPLE", *size)
        renderer = fig.canvas.get_renderer()
        fig.draw(renderer)
        legend_box = fig.legends[0].get_window_extent(renderer)
        label_box = ax.xaxis.label.get_window_extent(renderer)
        gap_pt = (label_box.y0 - legend_box.y1) * 72.0 / fig.dpi
        assert 0.0 <= gap_pt <= 5.0
        assert legend_box.y0 >= 0.0
        figure_box = fig.bbox
        for box in (ax.yaxis.label.get_window_extent(renderer), ax.title.get_window_extent(renderer),
                    legend_box):
            assert figure_box.x0 <= box.x0 and box.x1 <= figure_box.x1
            assert figure_box.y0 <= box.y0 and box.y1 <= figure_box.y1
        tick_boxes = [t.get_window_extent(renderer) for t in ax.get_yticklabels() if t.get_text()]
        assert max(b.x1 for b in [ax.yaxis.label.get_window_extent(renderer)]) <= min(
            b.x0 for b in tick_boxes) + 0.5

    def test_large_panel_axes_use_the_figure_area(self):
        fig, ax = _build_profile_figure(_entry(), "CUMPLE", 8.0, 5.0)
        renderer = fig.canvas.get_renderer()
        fig.draw(renderer)
        legend_in = fig.legends[0].get_window_extent(renderer).height / fig.dpi
        box = ax.get_position()
        assert box.height * 5.0 >= 0.85 * (5.0 - legend_in)
        assert box.width * 8.0 >= 0.90 * 8.0

    def test_small_panel_axes_do_not_shrink(self):
        fig, ax = _build_profile_figure(_entry(), "CUMPLE", 3.6, 2.6)
        box = ax.get_position()
        assert box.height >= 0.65 and box.width >= 0.78

    def test_large_panel_keeps_one_to_one_scale(self):
        window = (-10.0, 15.0, 102.5, 132.5)
        fig, ax = _build_profile_figure(_entry(window), "CUMPLE", 8.0, 5.0)
        x0, x1 = ax.get_xlim()
        z0, z1 = ax.get_ylim()
        assert x0 <= window[0] + 1e-9 and x1 >= window[1] - 1e-9
        assert z0 <= window[2] + 1e-9 and z1 >= window[3] - 1e-9
        assert (x1 - x0) / (z1 - z0) == pytest.approx(_axes_ratio(fig, ax), rel=1e-6)

    def test_figure_size_follows_arguments(self):
        fig, _ax = _build_profile_figure(_entry(), width_in=4.0, height_in=3.0)
        assert tuple(fig.get_size_inches()) == pytest.approx((4.0, 3.0))


class TestLocatorMap:
    def test_returns_none_without_highlighted(self):
        assert _build_locator_figure(_sections(), {}) is None
        assert locator_map_png(_sections(), {}) is None
        assert locator_map_png([], {"S-01": "CUMPLE"}) is None
        assert locator_map_png(_sections(), {"S-99": "CUMPLE"}) is None

    def test_returns_png_bytes(self):
        png = locator_map_png(_sections(), {"S-03": "CUMPLE", "S-04": "NO_CUMPLE"})
        assert isinstance(png, bytes)
        assert png.startswith(PNG_SIGNATURE)

    def test_limits_contain_highlighted_with_quarter_margin(self):
        sections = _sections(30, spacing=20.0)
        highlighted = {f"S-{i:02d}": "CUMPLE" for i in range(5, 15)}
        fig, ax = _build_locator_figure(sections, highlighted)
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        az = math.radians(20.0)
        pts = []
        for sec in sections:
            if sec["name"] in highlighted:
                ox, oy = sec["origin"]
                assert x0 < ox < x1 and y0 < oy < y1
                pts.append((ox - 20.0 * math.sin(az), oy - 20.0 * math.cos(az)))
                pts.append((ox + 20.0 * math.sin(az), oy + 20.0 * math.cos(az)))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        long_span = max(max(xs) - min(xs), max(ys) - min(ys))
        margin = 0.25 * long_span
        assert x0 <= min(xs) - margin + 1e-6 and x1 >= max(xs) + margin - 1e-6
        assert y0 <= min(ys) - margin + 1e-6 and y1 >= max(ys) + margin - 1e-6
        assert (min(xs) - x0) == pytest.approx(x1 - max(xs))
        assert (min(ys) - y0) == pytest.approx(y1 - max(ys))
        tight_x = math.isclose(x1 - x0, max(xs) - min(xs) + 2 * margin)
        tight_y = math.isclose(y1 - y0, max(ys) - min(ys) + 2 * margin)
        assert tight_x or tight_y
        assert (x1 - x0) / (y1 - y0) == pytest.approx(_axes_ratio(fig, ax), rel=1e-6)

    def test_minimum_sixty_metres_on_the_long_side(self):
        sections = _sections(5)
        for sec in sections:
            sec["length"] = 10.0
            sec["length_up"] = 5.0
            sec["length_down"] = 5.0
        fig, ax = _build_locator_figure(sections, {"S-03": "FUERA"})
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        assert max(x1 - x0, y1 - y0) >= 60.0 - 1e-6
        assert (x1 - x0) / (y1 - y0) == pytest.approx(_axes_ratio(fig, ax), rel=1e-6)
        assert min(x1 - x0, y1 - y0) <= 60.0 + 1e-6
        ox, oy = sections[2]["origin"]
        assert (x0 + x1) / 2 == pytest.approx(ox)
        assert (y0 + y1) / 2 == pytest.approx(oy)

    def test_highlighted_lines_use_status_colour_and_are_thicker(self):
        highlighted = {"S-03": "CUMPLE", "S-04": "NO_CUMPLE", "S-05": "FUERA"}
        _fig, ax = _build_locator_figure(_sections(), highlighted)
        strong = _lines(ax, "locator-highlighted")
        others = _lines(ax, "locator-other")
        assert len(strong) == 3 and len(others) == 5
        assert sorted(to_hex(line.get_color()) for line in strong) == sorted(
            STATUS_COLORS[s].lower() for s in highlighted.values()
        )
        assert min(l.get_linewidth() for l in strong) > 2 * max(l.get_linewidth() for l in others)

    def test_non_highlighted_lines_are_grey_and_unlabelled(self):
        _fig, ax = _build_locator_figure(_sections(), {"S-03": "CUMPLE"})
        others = _lines(ax, "locator-other")
        assert len(others) == 7
        assert {to_hex(line.get_color()) for line in others} == {OTHER_SECTION_COLOR.lower()}
        red, green, blue = to_rgba(OTHER_SECTION_COLOR)[:3]
        assert red == pytest.approx(green, abs=0.06) and green == pytest.approx(blue, abs=0.06)
        labels = [t.get_text() for t in ax.texts if t.get_gid() == "locator-label"]
        assert labels == ["S-03"]

    def test_highlighted_labels_carry_name_and_status_colour(self):
        highlighted = {"S-02": "NO_CUMPLE", "S-06": "CUMPLE"}
        _fig, ax = _build_locator_figure(_sections(), highlighted)
        labels = {t.get_text(): t for t in ax.texts if t.get_gid() == "locator-label"}
        assert set(labels) == set(highlighted)
        for name, status in highlighted.items():
            assert to_hex(labels[name].get_color()) == STATUS_COLORS[status].lower()
            assert labels[name].get_fontsize() >= 5.6

    def test_labels_do_not_overlap_each_other(self):
        sections = _sections(12, spacing=6.0)
        highlighted = {f"S-{i:02d}": "CUMPLE" for i in range(3, 9)}
        fig, ax = _build_locator_figure(sections, highlighted)
        renderer = fig.canvas.get_renderer()
        fig.draw(renderer)
        boxes = [t.get_window_extent(renderer)
                 for t in ax.texts if t.get_gid() == "locator-label"]
        assert len(boxes) == 6
        axes_box = ax.get_window_extent(renderer)
        for i, box in enumerate(boxes):
            assert box.x0 >= axes_box.x0 - 1 and box.x1 <= axes_box.x1 + 1
            assert box.y0 >= axes_box.y0 - 1 and box.y1 <= axes_box.y1 + 1
            for other in boxes[i + 1:]:
                assert not box.overlaps(other)

    def test_unknown_status_falls_back_to_unknown_colour(self):
        _fig, ax = _build_locator_figure(_sections(), {"S-03": "???"})
        strong = _lines(ax, "locator-highlighted")
        assert to_hex(strong[0].get_color()) == STATUS_COLORS["UNKNOWN"].lower()

    def test_asymmetric_lengths_follow_section_distance_axis(self):
        sections = _sections(3)
        sections[1].update(azimuth=90.0, length=50.0, length_up=40.0, length_down=10.0)
        _fig, ax = _build_locator_figure(sections, {"S-02": "CUMPLE"})
        line = _lines(ax, "locator-highlighted")[0]
        ox, oy = sections[1]["origin"]
        assert sorted(line.get_xdata()) == pytest.approx([ox - 10.0, ox + 40.0])
        assert list(line.get_ydata()) == pytest.approx([oy, oy])

    def test_shade_is_drawn_faint_in_grey_and_keeps_the_zoom(self):
        highlighted = {"S-03": "CUMPLE", "S-04": "CUMPLE"}
        _fig, plain = _build_locator_figure(_sections(), highlighted)
        expected = (plain.get_xlim(), plain.get_ylim())
        shade = np.linspace(0.0, 1.0, 600).reshape(20, 30)
        shade[0, :5] = np.nan
        extent = (0.0, 5000.0, 0.0, 9000.0)
        _fig, ax = _build_locator_figure(_sections(), highlighted, shade=(shade, extent))
        assert len(ax.images) == 1
        image = ax.images[0]
        assert image.get_cmap().name == "gray"
        assert image.get_alpha() == pytest.approx(0.35)
        assert image.origin == "lower"
        assert tuple(image.get_extent()) == pytest.approx(extent)
        assert ax.get_xlim() == pytest.approx(expected[0])
        assert ax.get_ylim() == pytest.approx(expected[1])

    def test_no_image_without_shade(self):
        _fig, ax = _build_locator_figure(_sections(), {"S-03": "CUMPLE"})
        assert not ax.images

    def test_north_arrow_and_round_scale_bar(self):
        _fig, ax = _build_locator_figure(_sections(30), {f"S-{i:02d}": "CUMPLE" for i in range(5, 15)})
        north = [t for t in ax.texts if t.get_gid() == "north-label"]
        assert [t.get_text() for t in north] == ["N"]
        bars = _lines(ax, "scale-bar")
        assert len(bars) == 1
        xdata = bars[0].get_xdata()
        length = float(xdata[-1] - xdata[0])
        x0, x1 = ax.get_xlim()
        assert 0.1 * (x1 - x0) <= length <= 0.45 * (x1 - x0)
        mantissa = length / 10 ** math.floor(math.log10(length))
        assert any(math.isclose(mantissa, m) for m in (1.0, 2.0, 5.0))
        text = [t for t in ax.texts if t.get_gid() == "scale-label"]
        assert [t.get_text() for t in text] == [f"{length:g} m"]

    def test_figure_size_follows_arguments(self):
        fig, _ax = _build_locator_figure(_sections(), {"S-03": "CUMPLE"}, width_in=3.0, height_in=2.0)
        assert tuple(fig.get_size_inches()) == pytest.approx((3.0, 2.0))


def test_effective_profile_font_at_placed_width():
    import io
    from PIL import Image
    from matplotlib.text import Text
    from core.report_figures_profile import _build_profile_figure, cropped_profile_png
    from core.report_charts import _clear_figure
    entry = {"section_name": "S-01", "profile_d": ([0, 10], [100, 110]), "profile_t": ([0, 10], [101, 111])}
    width, height, dpi = 6.6 / 2.54, 6.1 / 2.54, 170
    fig, _ = _build_profile_figure(entry, width_in=width, height_in=height)
    fig.canvas.draw()
    sizes = [t.get_fontsize() for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
    pixels = Image.open(io.BytesIO(cropped_profile_png(entry, width_in=width, height_in=height, dpi=dpi))).width
    _clear_figure(fig)
    assert min(sizes) * width / (pixels / dpi) >= 6


def test_effective_locator_font_at_composer_placed_width():
    import io
    from PIL import Image
    from matplotlib.text import Text
    from core.report_figures_profile import _build_locator_figure, locator_map_png
    from core.report_pages import _LOCATOR_BOX_CM, _CM_PER_INCH, _FIGURE_DPI
    from core.report_charts import _clear_figure
    sections = [{"name": "S-01", "x0": 0, "y0": 0, "x1": 100, "y1": 100}]
    width, height = (v / _CM_PER_INCH for v in _LOCATOR_BOX_CM)
    fig, _ = _build_locator_figure(sections, {"S-01": "CUMPLE"}, width_in=width, height_in=height)
    fig.canvas.draw()
    sizes = [t.get_fontsize() for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
    pixels, height_px = Image.open(io.BytesIO(locator_map_png(sections, {"S-01": "CUMPLE"}, width_in=width, height_in=height, dpi=_FIGURE_DPI))).size
    placed_width = min(width, height * pixels / height_px)
    _clear_figure(fig)
    assert min(sizes) * placed_width / (pixels / _FIGURE_DPI) >= 6
