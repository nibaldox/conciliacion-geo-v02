"""Tests for core.report_figures_analysis — matrix, histograms, trend, excavation bars."""
import math

import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import to_hex
import numpy as np
import pytest

from core.report_charts import STATUS_COLORS, STATUS_LABELS_ES
from core.report_figures_analysis import (
    EXTRA_COLOR,
    MISSING_FILL,
    OVER_COLOR,
    UNDER_COLOR,
    _build_deviation_histograms_figure,
    _build_excavation_bars_figure,
    _build_status_matrix_figure,
    _build_trend_figure,
    deviation_histograms_png,
    excavation_bars_png,
    status_matrix_png,
    trend_png,
)
from core.report_volumes import SectionExcavation

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

TOLERANCES = {
    "bench_height": {"neg": 1.5, "pos": 2.5},
    "face_angle": {"neg": 5.0, "pos": 4.0},
    "berm_width": {"min": 7.0},
}


def _cell(section, level, row_type="MATCH", worst="CUMPLE", sector="", bench=1):
    return {
        "section": section,
        "sector": sector,
        "level_nominal": level,
        "bench_num": bench,
        "type": row_type,
        "worst_status": worst,
        "height_status": None,
        "angle_status": None,
        "berm_status": None,
        "design_below_min": False,
    }


def _matrix():
    return (
        _cell("S-10", "3110", worst="NO_CUMPLE", bench=2),
        _cell("S-10", "3125", worst="CUMPLE", bench=1),
        _cell("S-10", "3103", row_type="MISSING", worst="NO_CUMPLE", bench=3),
        _cell("S-02", "3125", worst="FUERA", bench=1),
        _cell("S-02", "3125", row_type="EXTRA", worst="NO_CUMPLE", bench=999),
        _cell("S-07", "3110", worst="UNKNOWN", bench=2),
    )


def _cells(fig):
    out = {}
    for patch in fig.axes[0].patches:
        gid = patch.get_gid() or ""
        if gid.startswith("cell|"):
            _, section, level = gid.split("|")
            out[(section, level)] = patch
    return out


def _excavation(section, over, under, sector=""):
    return SectionExcavation(
        section=section,
        sector=sector,
        area_over_m2=None if over is None else over / 10.0,
        area_under_m2=None if under is None else under / 10.0,
        influence_width_m=None if over is None and under is None else 10.0,
        volume_over_m3=over,
        volume_under_m3=under,
        window=None,
        source="calculate_area_between_profiles",
        assumptions=(),
        warnings=(),
    )


def _bars(ax, gid):
    return [patch for patch in ax.patches if patch.get_gid() == gid]


def _bands(ax):
    return [patch for patch in ax.patches if patch.get_gid() == "tol-band"]


def _texts(ax):
    return [text.get_text() for text in ax.texts]


class TestEmptyInputs:
    def test_status_matrix_returns_none_without_rows(self):
        assert status_matrix_png(()) is None
        assert status_matrix_png(None) is None

    def test_histograms_return_none_without_values(self):
        assert deviation_histograms_png({}, TOLERANCES) is None
        assert deviation_histograms_png(
            {"height": (), "angle": (), "berm": ()}, TOLERANCES
        ) is None
        assert deviation_histograms_png({"height": (float("nan"),)}, TOLERANCES) is None

    def test_trend_returns_none_without_values(self):
        assert trend_png((), TOLERANCES) is None
        rows = (
            {"section": "S-01", "sector": "", "height_dev_mean": None,
             "angle_dev_mean": None, "n": 0},
        )
        assert trend_png(rows, TOLERANCES) is None

    def test_excavation_returns_none_without_volumes(self):
        assert excavation_bars_png(()) is None
        assert excavation_bars_png((_excavation("S-01", None, None),)) is None


class TestStatusMatrix:
    def test_sections_keep_the_given_order(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        cells = _cells(fig)
        columns = {section: round(patch.get_x() + patch.get_width() / 2)
                   for (section, _level), patch in cells.items()}
        assert columns == {"S-10": 0, "S-02": 1, "S-07": 2}

    def test_levels_are_drawn_in_descending_order(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        ax = fig.axes[0]
        assert [label.get_text() for label in ax.get_yticklabels()] == [
            "3125", "3110", "3103"]
        cells = _cells(fig)
        bottom, top = ax.get_ylim()
        assert bottom > top
        centre = lambda key: cells[key].get_y() + cells[key].get_height() / 2
        assert centre(("S-10", "3125")) < centre(("S-10", "3110")) < centre(("S-10", "3103"))

    def test_match_cells_use_the_status_palette(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        cells = _cells(fig)
        assert to_hex(cells[("S-10", "3125")].get_facecolor()) == STATUS_COLORS["CUMPLE"].lower()
        assert to_hex(cells[("S-10", "3110")].get_facecolor()) == STATUS_COLORS["NO_CUMPLE"].lower()
        assert to_hex(cells[("S-02", "3125")].get_facecolor()) == STATUS_COLORS["FUERA"].lower()
        assert to_hex(cells[("S-07", "3110")].get_facecolor()) == STATUS_COLORS["UNKNOWN"].lower()

    def test_missing_bench_is_hatched_and_not_status_coloured(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        cells = _cells(fig)
        missing = cells[("S-10", "3103")]
        assert missing.get_hatch()
        assert to_hex(missing.get_facecolor()) == MISSING_FILL.lower()
        assert not cells[("S-10", "3125")].get_hatch()

    def test_extra_bench_is_marked_without_replacing_the_matched_cell(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        ax = fig.axes[0]
        markers = [line for line in ax.lines if line.get_gid() == "extra-marker"]
        assert len(markers) == 1
        assert list(markers[0].get_xdata()) == [1.0]
        assert to_hex(markers[0].get_markerfacecolor()) == EXTRA_COLOR.lower()
        assert to_hex(_cells(fig)[("S-02", "3125")].get_facecolor()) == STATUS_COLORS["FUERA"].lower()

    def test_empty_combinations_have_no_cell(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        assert ("S-07", "3125") not in _cells(fig)
        assert ("S-02", "3103") not in _cells(fig)

    def test_two_benches_in_one_cell_show_the_most_severe(self):
        rows = (
            _cell("S-01", "3125", worst="CUMPLE"),
            _cell("S-01", "3125", worst="NO_CUMPLE", bench=2),
        )
        fig = _build_status_matrix_figure(rows, width_in=7.0, height_in=2.4)
        assert to_hex(_cells(fig)[("S-01", "3125")].get_facecolor()) == STATUS_COLORS["NO_CUMPLE"].lower()

    def test_rows_without_nominal_level_go_to_a_dash_row_at_the_bottom(self):
        rows = (_cell("S-01", "3125"), _cell("S-01", None, bench=2))
        fig = _build_status_matrix_figure(rows, width_in=7.0, height_in=2.4)
        labels = [label.get_text() for label in fig.axes[0].get_yticklabels()]
        assert labels == ["3125", "\u2014"]

    def test_legend_uses_spanish_labels(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        legend = fig.axes[0].get_legend() or fig.legends[0]
        labels = [text.get_text() for text in legend.get_texts()]
        for status in ("CUMPLE", "FUERA", "NO_CUMPLE", "UNKNOWN"):
            assert any(label.startswith(STATUS_LABELS_ES[status]) for label in labels)
        assert any(label.startswith("No construido") for label in labels)
        assert any(label.startswith("Banco adicional") for label in labels)

    def test_section_labels_are_thinned_and_never_overlap(self):
        rows = tuple(_cell(f"S-{i:02d}", "3110") for i in range(1, 97))
        fig = _build_status_matrix_figure(rows, width_in=7.0, height_in=2.4)
        ax = fig.axes[0]
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        labels = [label for label in ax.get_xticklabels() if label.get_text()]
        assert 2 <= len(labels) < 96
        assert labels[0].get_text() == "S-01"
        boxes = sorted((label.get_window_extent(renderer) for label in labels),
                       key=lambda box: box.x0)
        for left, right in zip(boxes, boxes[1:]):
            assert left.x1 < right.x0

    def test_few_sections_are_all_labelled(self):
        fig = _build_status_matrix_figure(_matrix(), width_in=7.0, height_in=2.4)
        labels = [label.get_text() for label in fig.axes[0].get_xticklabels()]
        assert labels == ["S-10", "S-02", "S-07"]

    def test_same_section_name_in_two_sectors_gets_two_columns(self):
        rows = (
            _cell("S-01", "3125", sector="Norte"),
            _cell("S-01", "3125", sector="Sur", worst="NO_CUMPLE"),
        )
        fig = _build_status_matrix_figure(rows, width_in=7.0, height_in=2.4)
        xs = sorted(round(patch.get_x() + patch.get_width() / 2)
                    for patch in fig.axes[0].patches
                    if (patch.get_gid() or "").startswith("cell|"))
        assert xs == [0, 1]

    def test_png_signature(self):
        png = status_matrix_png(_matrix())
        assert png.startswith(PNG_SIGNATURE)


class TestDeviationHistograms:
    DEVIATIONS = {
        "height": (-3.0, -1.0, 0.2, 0.4, 1.0),
        "angle": (-12.0, -6.0, -2.0),
        "berm": (-1.9, -0.5, 0.3, 2.0),
    }

    def test_three_panels_with_n_in_each_title(self):
        fig = _build_deviation_histograms_figure(
            self.DEVIATIONS, TOLERANCES, width_in=7.0, height_in=2.4)
        titles = [ax.get_title(loc="left") for ax in fig.axes]
        assert len(titles) == 3
        assert "Altura" in titles[0] and "n = 5" in titles[0]
        assert "\u00c1ngulo" in titles[1] and "n = 3" in titles[1]
        assert "Berma" in titles[2] and "n = 4" in titles[2]

    def test_tolerance_band_limits_come_from_tolerances(self):
        fig = _build_deviation_histograms_figure(
            self.DEVIATIONS, TOLERANCES, width_in=7.0, height_in=2.4)
        height_band = _bands(fig.axes[0])
        angle_band = _bands(fig.axes[1])
        assert len(height_band) == 1 and len(angle_band) == 1
        assert height_band[0].get_x() == pytest.approx(-1.5)
        assert height_band[0].get_x() + height_band[0].get_width() == pytest.approx(2.5)
        assert angle_band[0].get_x() == pytest.approx(-5.0)
        assert angle_band[0].get_x() + angle_band[0].get_width() == pytest.approx(4.0)

    def test_band_is_fully_inside_the_x_limits(self):
        fig = _build_deviation_histograms_figure(
            {"height": (0.1, 0.2), "angle": (), "berm": ()}, TOLERANCES,
            width_in=7.0, height_in=2.4)
        low, high = fig.axes[0].get_xlim()
        assert low <= -1.5 and high >= 2.5

    def test_berm_minimum_is_stated_and_not_drawn_as_a_deviation_band(self):
        fig = _build_deviation_histograms_figure(
            self.DEVIATIONS, TOLERANCES, width_in=7.0, height_in=2.4)
        ax = fig.axes[2]
        assert _bands(ax) == []
        assert any("m\u00edn" in text and "7,0" in text for text in _texts(ax))

    def test_missing_tolerance_draws_no_band(self):
        fig = _build_deviation_histograms_figure(
            self.DEVIATIONS, {}, width_in=7.0, height_in=2.4)
        assert all(_bands(ax) == [] for ax in fig.axes)

    def test_bar_counts_add_up_to_n(self):
        fig = _build_deviation_histograms_figure(
            self.DEVIATIONS, TOLERANCES, width_in=7.0, height_in=2.4)
        for ax, key in zip(fig.axes, ("height", "angle", "berm")):
            total = sum(patch.get_height() for patch in _bars(ax, "hist-bar"))
            assert total == len(self.DEVIATIONS[key])

    def test_empty_parameter_shows_sin_datos(self):
        fig = _build_deviation_histograms_figure(
            {"height": (0.5, 1.0), "angle": (), "berm": (float("nan"),)},
            TOLERANCES, width_in=7.0, height_in=2.4)
        assert len(fig.axes) == 3
        for ax in fig.axes[1:]:
            assert "sin datos" in _texts(ax)
            assert _bars(ax, "hist-bar") == []
            assert "n = 0" in ax.get_title(loc="left")
            assert not ax.xaxis.get_visible()
        assert "sin datos" not in _texts(fig.axes[0])

    def test_non_finite_values_are_dropped(self):
        fig = _build_deviation_histograms_figure(
            {"height": (0.5, float("nan"), float("inf"), None)}, TOLERANCES,
            width_in=7.0, height_in=2.4)
        assert "n = 1" in fig.axes[0].get_title(loc="left")

    def test_png_signature(self):
        png = deviation_histograms_png(self.DEVIATIONS, TOLERANCES)
        assert png.startswith(PNG_SIGNATURE)


class TestTrend:
    ROWS = (
        {"section": "S-01", "sector": "", "height_dev_mean": -1.0, "angle_dev_mean": -6.0, "n": 2},
        {"section": "S-02", "sector": "", "height_dev_mean": None, "angle_dev_mean": None, "n": 0},
        {"section": "S-03", "sector": "", "height_dev_mean": 0.5, "angle_dev_mean": None, "n": 1},
        {"section": "S-04", "sector": "", "height_dev_mean": 0.0, "angle_dev_mean": -2.0, "n": 2},
    )

    def _line(self, fig, gid):
        for ax in fig.axes:
            for line in ax.lines:
                if line.get_gid() == gid:
                    return line
        raise AssertionError(gid)

    def test_none_is_a_gap_and_never_zero(self):
        fig = _build_trend_figure(self.ROWS, TOLERANCES, width_in=7.0, height_in=2.4)
        height = np.asarray(self._line(fig, "trend-height").get_ydata(), dtype=float)
        angle = np.asarray(self._line(fig, "trend-angle").get_ydata(), dtype=float)
        assert height[0] == -1.0 and math.isnan(height[1]) and height[2] == 0.5
        assert height[3] == 0.0
        assert angle[0] == -6.0 and math.isnan(angle[1]) and math.isnan(angle[2])
        assert angle[3] == -2.0

    def test_points_sit_on_their_section_position(self):
        fig = _build_trend_figure(self.ROWS, TOLERANCES, width_in=7.0, height_in=2.4)
        assert list(self._line(fig, "trend-height").get_xdata()) == [0, 1, 2, 3]
        labels = [label.get_text() for label in fig.axes[-1].get_xticklabels()]
        assert labels == ["S-01", "S-02", "S-03", "S-04"]

    def test_isolated_values_stay_visible_with_markers(self):
        fig = _build_trend_figure(self.ROWS, TOLERANCES, width_in=7.0, height_in=2.4)
        assert self._line(fig, "trend-height").get_marker() not in (None, "", "None")

    def test_tolerance_bands_come_from_tolerances(self):
        fig = _build_trend_figure(self.ROWS, TOLERANCES, width_in=7.0, height_in=2.4)
        height_band = _bands(fig.axes[0])
        angle_band = _bands(fig.axes[1])
        assert len(height_band) == 1 and len(angle_band) == 1
        assert height_band[0].get_y() == pytest.approx(-1.5)
        assert height_band[0].get_y() + height_band[0].get_height() == pytest.approx(2.5)
        assert angle_band[0].get_y() == pytest.approx(-5.0)
        assert angle_band[0].get_y() + angle_band[0].get_height() == pytest.approx(4.0)

    def test_parameter_without_values_shows_sin_datos(self):
        rows = tuple({**row, "angle_dev_mean": None} for row in self.ROWS)
        fig = _build_trend_figure(rows, TOLERANCES, width_in=7.0, height_in=2.4)
        assert "sin datos" in _texts(fig.axes[1])
        assert "sin datos" not in _texts(fig.axes[0])

    def test_png_signature(self):
        assert trend_png(self.ROWS, TOLERANCES).startswith(PNG_SIGNATURE)


class TestExcavationBars:
    ENTRIES = (
        _excavation("S-01", 300.0, 800.0),
        _excavation("S-02", None, None),
        _excavation("S-03", 120.0, 0.0),
        _excavation("S-04", None, 50.0),
    )

    def test_over_goes_up_and_under_goes_down_with_frozen_colours(self):
        fig = _build_excavation_bars_figure(self.ENTRIES, width_in=7.0, height_in=2.4)
        ax = fig.axes[0]
        over = _bars(ax, "over-bar")
        under = _bars(ax, "under-bar")
        assert OVER_COLOR == "#3b82f6" and UNDER_COLOR == "#f97316"
        assert sorted(patch.get_height() for patch in over) == [120.0, 300.0]
        assert sorted(patch.get_height() for patch in under) == [-800.0, -50.0, 0.0]
        assert all(to_hex(patch.get_facecolor()) == OVER_COLOR for patch in over)
        assert all(to_hex(patch.get_facecolor()) == UNDER_COLOR for patch in under)

    def test_none_volume_is_marked_and_never_drawn_as_a_bar(self):
        fig = _build_excavation_bars_figure(self.ENTRIES, width_in=7.0, height_in=2.4)
        ax = fig.axes[0]
        centres = lambda gid: sorted(
            round(patch.get_x() + patch.get_width() / 2) for patch in _bars(ax, gid))
        assert centres("over-bar") == [0, 2]
        assert centres("under-bar") == [0, 2, 3]
        marks = [text for text in ax.texts if text.get_gid() == "no-volume"]
        assert sorted(round(text.get_position()[0]) for text in marks) == [1, 3]
        assert all(text.get_text() == "\u2014" for text in marks)

    def test_totals_in_title_sum_only_present_values(self):
        fig = _build_excavation_bars_figure(self.ENTRIES, width_in=7.0, height_in=2.4)
        title = fig.axes[0].get_title(loc="left")
        assert "420 m\u00b3" in title
        assert "850 m\u00b3" in title
        assert "2 sin volumen" in title

    def test_thousands_use_a_space_separator(self):
        entries = (_excavation("S-01", 31924.4, 51471.0),)
        fig = _build_excavation_bars_figure(entries, width_in=7.0, height_in=2.4)
        title = fig.axes[0].get_title(loc="left")
        assert "31\u202f924 m\u00b3" in title and "51\u202f471 m\u00b3" in title

    def test_axis_is_symmetric_enough_to_show_both_signs(self):
        fig = _build_excavation_bars_figure(self.ENTRIES, width_in=7.0, height_in=2.4)
        low, high = fig.axes[0].get_ylim()
        assert low < -800.0 and high > 300.0

    def test_mapping_entries_are_accepted(self):
        entries = ({"section": "S-01", "sector": "", "volume_over_m3": 10.0,
                    "volume_under_m3": None},)
        fig = _build_excavation_bars_figure(entries, width_in=7.0, height_in=2.4)
        ax = fig.axes[0]
        assert len(_bars(ax, "over-bar")) == 1 and _bars(ax, "under-bar") == []

    def test_png_signature(self):
        assert excavation_bars_png(self.ENTRIES).startswith(PNG_SIGNATURE)
