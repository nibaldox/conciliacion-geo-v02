from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from matplotlib.colors import to_hex, to_rgba

from core import report_figures_heatmap as hm
from core.report_figures_heatmap import (
    HDEV_CATEGORY_ORDER,
    HDEV_COLORS,
    HDEV_LABELS_ES,
    HeatmapSummary,
    heatmap_page_png,
    heatmap_summary,
    level_window_from_geometry,
)

REPO = Path(__file__).resolve().parents[1]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _cell(station, elevation, deviation, category, bench=1):
    return {
        "deviation_m": deviation,
        "value": deviation,
        "unit": "m",
        "category": category,
        "status": "measured" if deviation is not None else "topo_missing",
        "station_m": station,
        "elevation_m": elevation,
        "bench_num": bench,
    }


def _payload(cells, **extra):
    payload = {
        "cells": cells,
        "unit": "m",
        "thresholds": {"within": 1.0, "moderate": 1.8, "severe": 3.0},
        "resolution": {"longitudinal_step": 2.0, "vertical_step": 1.0},
        "section_names": ["S-01", "S-02", "S-03"],
        "section_stations_m": [0.0, 10.0, 20.0],
    }
    payload.update(extra)
    return payload


def _sample_payload(**extra):
    cells = [
        _cell(1.0, 100.5, 0.5, "within_tolerance"),
        _cell(1.0, 101.5, -0.4, "within_tolerance"),
        _cell(3.0, 100.5, 1.5, "overbreak_minor"),
        _cell(3.0, 101.5, 2.5, "overbreak_moderate"),
        _cell(10.0, 100.5, 4.0, "overbreak_severe"),
        _cell(10.0, 101.5, None, "unmeasured"),
        _cell(15.0, 110.5, -1.2, "underbreak_minor", bench=2),
        _cell(15.0, 111.5, -2.0, "underbreak_moderate", bench=2),
        _cell(17.0, 110.5, -5.0, "underbreak_severe", bench=2),
        _cell(17.0, 111.5, None, "unassessed", bench=2),
    ]
    return _payload(cells, **extra)


def _web_categories_and_colors():
    source = (REPO / "web/src/utils/horizontalDeviation.ts").read_text(encoding="utf-8")
    order_block = re.search(
        r"HORIZONTAL_DEVIATION_CATEGORIES\s*=\s*\[(.*?)\]", source, re.S
    ).group(1)
    order = re.findall(r"'([a-z_]+)'", order_block)
    colors = dict(
        re.findall(r"([a-z_]+):\s*\['--color-hdev-[a-z-]+',\s*'(#[0-9a-fA-F]{6})'\]", source)
    )
    return order, colors


def test_category_order_and_colors_match_web_source():
    order, colors = _web_categories_and_colors()
    assert len(order) == 8
    assert list(HDEV_CATEGORY_ORDER) == order
    assert dict(HDEV_COLORS) == colors


def test_spanish_labels_match_web_locale():
    locale = json.loads((REPO / "web/src/locales/es.json").read_text(encoding="utf-8"))
    assert dict(HDEV_LABELS_ES) == locale["horizontalDeviation"]["categories"]
    assert set(HDEV_LABELS_ES) == set(HDEV_CATEGORY_ORDER)


def test_summary_is_frozen_dataclass():
    summary = heatmap_summary(_sample_payload())
    assert isinstance(summary, HeatmapSummary)
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.n_cells = 0


def test_summary_counts_whole_payload():
    summary = heatmap_summary(_sample_payload())
    assert summary.n_cells == 10
    assert summary.n_measured == 8
    assert summary.level_window is None
    assert list(summary.counts) == list(HDEV_CATEGORY_ORDER)
    assert summary.counts == {
        "within_tolerance": 2,
        "underbreak_minor": 1,
        "underbreak_moderate": 1,
        "underbreak_severe": 1,
        "overbreak_minor": 1,
        "overbreak_moderate": 1,
        "overbreak_severe": 1,
        "unmeasured": 2,
    }
    assert summary.pct_within == pytest.approx(25.0)


def test_summary_median_is_signed_and_p95_uses_absolute_values():
    summary = heatmap_summary(_sample_payload())
    assert summary.median_m == pytest.approx(0.05)
    assert summary.p95_abs_m == pytest.approx(4.65)


def test_summary_maxima_and_location_strings():
    summary = heatmap_summary(_sample_payload())
    assert summary.max_over == {
        "deviation_m": 4.0,
        "station_m": 10.0,
        "elevation": 100.5,
        "location": "S-02",
    }
    assert summary.max_under == {
        "deviation_m": -5.0,
        "station_m": 17.0,
        "elevation": 110.5,
        "location": "entre S-02 y S-03",
    }


def test_summary_location_is_none_without_section_stations():
    payload = _sample_payload()
    del payload["section_names"]
    del payload["section_stations_m"]
    summary = heatmap_summary(payload)
    assert summary.max_over["deviation_m"] == 4.0
    assert summary.max_over["location"] is None
    assert summary.max_under["location"] is None


def test_summary_level_window_restricts_statistics():
    summary = heatmap_summary(_sample_payload(), level_window=(110.0, 112.0))
    assert summary.level_window == (110.0, 112.0)
    assert summary.n_cells == 4
    assert summary.n_measured == 3
    assert summary.counts["unmeasured"] == 1
    assert summary.counts["within_tolerance"] == 0
    assert summary.pct_within == pytest.approx(0.0)
    assert summary.median_m == pytest.approx(-2.0)
    assert summary.max_over is None
    assert summary.max_under["deviation_m"] == -5.0


def test_summary_level_window_bounds_are_inclusive_and_order_free():
    cells = [
        _cell(1.0, 100.0, 0.1, "within_tolerance"),
        _cell(1.0, 105.0, 0.2, "within_tolerance"),
        _cell(1.0, 105.01, 0.3, "within_tolerance"),
    ]
    assert heatmap_summary(_payload(cells), level_window=(100.0, 105.0)).n_cells == 2
    assert heatmap_summary(_payload(cells), level_window=(105.0, 100.0)).n_cells == 2


def test_summary_without_measured_cells_keeps_none():
    cells = [_cell(1.0, 100.5, None, "unmeasured"), _cell(3.0, 100.5, None, "unmeasured")]
    summary = heatmap_summary(_payload(cells))
    assert summary.n_cells == 2
    assert summary.n_measured == 0
    assert summary.pct_within is None
    assert summary.median_m is None
    assert summary.p95_abs_m is None
    assert summary.max_over is None
    assert summary.max_under is None


@pytest.mark.parametrize("payload", [None, {}, {"cells": []}])
def test_summary_on_empty_payload(payload):
    summary = heatmap_summary(payload)
    assert summary.n_cells == 0
    assert summary.n_measured == 0
    assert summary.pct_within is None
    assert summary.median_m is None
    assert set(summary.counts.values()) == {0}


def test_summary_never_reclassifies_from_deviation():
    cells = [
        _cell(1.0, 100.5, 0.2, "overbreak_severe"),
        _cell(3.0, 100.5, 0.3, "within_tolerance"),
    ]
    summary = heatmap_summary(_payload(cells))
    assert summary.counts["overbreak_severe"] == 1
    assert summary.counts["within_tolerance"] == 1
    assert summary.pct_within == pytest.approx(50.0)


def test_summary_non_finite_deviation_is_unmeasured():
    cells = [
        _cell(1.0, 100.5, float("nan"), "within_tolerance"),
        _cell(3.0, 100.5, 0.3, "within_tolerance"),
    ]
    summary = heatmap_summary(_payload(cells))
    assert summary.n_measured == 1
    assert summary.counts["unmeasured"] == 1
    assert summary.pct_within == pytest.approx(100.0)


def test_level_window_from_geometry_uses_only_entries_with_view_window():
    geometry = [
        {
            "section_name": "S-01",
            "view_window": (0.0, 40.0, 3102.5, 3132.5),
            "params_design": SimpleNamespace(
                benches=[
                    SimpleNamespace(toe_elevation=3110.0, crest_elevation=3125.0),
                    SimpleNamespace(toe_elevation=3095.0, crest_elevation=3110.0),
                ]
            ),
        },
        {
            "section_name": "S-02",
            "view_window": (0.0, 40.0, 3102.5, 3132.5),
            "params_design": {"benches": [{"toe_elevation": 3111.0, "crest_elevation": 3126.0}]},
        },
        {
            "section_name": "S-03",
            "view_window": None,
            "params_design": SimpleNamespace(
                benches=[SimpleNamespace(toe_elevation=3000.0, crest_elevation=3300.0)]
            ),
        },
    ]
    assert level_window_from_geometry(geometry) == (3095.0, 3126.0)


def test_level_window_from_geometry_none_without_windows():
    geometry = [
        {
            "section_name": "S-01",
            "view_window": None,
            "params_design": SimpleNamespace(
                benches=[SimpleNamespace(toe_elevation=3110.0, crest_elevation=3125.0)]
            ),
        }
    ]
    assert level_window_from_geometry(geometry) is None
    assert level_window_from_geometry([]) is None
    assert level_window_from_geometry(None) is None
    windowed_without_benches = [
        {"view_window": (0.0, 1.0, 2.0, 3.0), "params_design": SimpleNamespace(benches=[])},
        {"view_window": (0.0, 1.0, 2.0, 3.0), "params_design": None},
    ]
    assert level_window_from_geometry(windowed_without_benches) is None


def _artist(fig, gid):
    found = fig.findobj(lambda artist: artist.get_gid() == gid)
    return found[0] if found else None


def _facecolors(fig, gid):
    collection = _artist(fig, gid)
    assert collection is not None, gid
    return [to_hex(color) for color in collection.get_facecolors()]


def test_figure_axes_cover_every_cell_and_are_labelled():
    fig = hm._build_heatmap_figure(_sample_payload(), title="Sector Norte")
    ax = fig.axes[0]
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    assert x0 <= 0.0 and x1 >= 18.0
    assert y0 <= 100.0 and y1 >= 112.0
    assert "Estación" in ax.get_xlabel() and "(m)" in ax.get_xlabel()
    assert "Elevación" in ax.get_ylabel() and "(m)" in ax.get_ylabel()
    texts = [t.get_text() for t in fig.findobj(lambda a: hasattr(a, "get_text"))]
    assert any("Sector Norte" in text for text in texts)


def test_figure_cells_use_payload_category_colors_without_window():
    fig = hm._build_heatmap_figure(_sample_payload())
    measured = _facecolors(fig, "hdev-cells-measured")
    assert len(measured) == 8
    assert sorted(set(measured)) == sorted(
        {HDEV_COLORS[key] for key in HDEV_CATEGORY_ORDER if key != "unmeasured"}
    )
    unmeasured = _facecolors(fig, "hdev-cells-unmeasured")
    assert unmeasured == [HDEV_COLORS["unmeasured"]] * 2
    assert _artist(fig, "hdev-level-window") is None


def test_figure_keeps_category_even_when_deviation_disagrees():
    cells = [_cell(1.0, 100.5, 0.2, "overbreak_severe")]
    fig = hm._build_heatmap_figure(_payload(cells))
    assert _facecolors(fig, "hdev-cells-measured") == [HDEV_COLORS["overbreak_severe"]]


def test_figure_cell_rectangles_are_rebuilt_from_centres():
    fig = hm._build_heatmap_figure(_sample_payload())
    collection = _artist(fig, "hdev-cells-measured")
    first = collection.get_paths()[0].get_extents()
    assert (first.x0, first.x1) == pytest.approx((0.0, 2.0))
    assert (first.y0, first.y1) == pytest.approx((100.0, 101.0))


def test_figure_highlights_level_window_and_dims_the_rest():
    fig = hm._build_heatmap_figure(_sample_payload(), level_window=(110.0, 112.0))
    outline = _artist(fig, "hdev-level-window")
    assert outline is not None
    assert outline.get_y() == pytest.approx(110.0)
    assert outline.get_height() == pytest.approx(2.0)
    assert outline.get_facecolor()[3] == 0.0
    inside = _facecolors(fig, "hdev-cells-measured")
    assert sorted(inside) == sorted(
        [
            HDEV_COLORS["underbreak_minor"],
            HDEV_COLORS["underbreak_moderate"],
            HDEV_COLORS["underbreak_severe"],
        ]
    )
    context = _facecolors(fig, "hdev-cells-context")
    assert len(context) == 6
    assert not set(context) & set(HDEV_COLORS.values())


def test_figure_legend_has_eight_classes_with_web_labels_and_colors():
    fig = hm._build_heatmap_figure(_sample_payload())
    legend = fig.axes[0].get_legend()
    labels = [text.get_text() for text in legend.get_texts()]
    for key in HDEV_CATEGORY_ORDER:
        assert HDEV_LABELS_ES[key] in labels
    handles = {
        handle.get_label(): to_hex(handle.get_facecolor())
        for handle in legend.legend_handles
        if hasattr(handle, "get_facecolor") and handle.get_label() in HDEV_LABELS_ES.values()
    }
    assert handles == {HDEV_LABELS_ES[key]: HDEV_COLORS[key] for key in HDEV_CATEGORY_ORDER}


def test_figure_marks_maxima_with_signed_values():
    fig = hm._build_heatmap_figure(_sample_payload())
    over = _artist(fig, "hdev-max-over")
    under = _artist(fig, "hdev-max-under")
    assert over.get_marker() == "^" and under.get_marker() == "v"
    assert list(over.get_xdata()) == [10.0] and list(over.get_ydata()) == [100.5]
    assert list(under.get_xdata()) == [17.0] and list(under.get_ydata()) == [110.5]
    assert _artist(fig, "hdev-max-over-label").get_text() == "+4,00 m"
    assert _artist(fig, "hdev-max-under-label").get_text() == "−5,00 m"


def test_figure_maxima_follow_the_level_window():
    fig = hm._build_heatmap_figure(_sample_payload(), level_window=(110.0, 112.0))
    assert _artist(fig, "hdev-max-over") is None
    assert _artist(fig, "hdev-max-under-label").get_text() == "−5,00 m"


def test_figure_section_names_on_secondary_axis():
    fig = hm._build_heatmap_figure(_sample_payload())
    secondary = _artist(fig, "hdev-section-axis")
    assert secondary is not None
    labels = [tick.get_text() for tick in secondary.get_xticklabels()]
    assert labels == ["S-01", "S-02", "S-03"]
    assert list(secondary.get_xticks()) == [0.0, 10.0, 20.0]


def test_figure_section_labels_are_thinned_to_avoid_overlap():
    names = [f"S-{index:02d}" for index in range(1, 97)]
    stations = [10.0 * index for index in range(96)]
    cells = [_cell(10.0 * index + 5.0, 100.5, 0.2, "within_tolerance") for index in range(95)]
    payload = _payload(cells, section_names=names, section_stations_m=stations)
    fig = hm._build_heatmap_figure(payload)
    secondary = _artist(fig, "hdev-section-axis")
    labels = [tick.get_text() for tick in secondary.get_xticklabels()]
    ticks = list(secondary.get_xticks())
    assert labels[0] == "S-01"
    assert 2 <= len(labels) <= 30
    assert set(labels) <= set(names)
    every_tick = set(ticks) | set(secondary.get_xticks(minor=True))
    assert every_tick == set(stations)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = [
        tick.get_window_extent(renderer)
        for tick in secondary.get_xticklabels()
        if tick.get_text()
    ]
    assert len(boxes) == len(ticks)
    for left, right in zip(boxes, boxes[1:]):
        assert left.x1 < right.x0


def test_figure_without_section_stations_has_no_secondary_axis():
    payload = _sample_payload()
    del payload["section_names"]
    del payload["section_stations_m"]
    fig = hm._build_heatmap_figure(payload)
    assert fig is not None
    assert _artist(fig, "hdev-section-axis") is None


def test_figure_size_follows_arguments():
    fig = hm._build_heatmap_figure(_sample_payload(), width_in=8.0, height_in=4.0)
    assert tuple(fig.get_size_inches()) == pytest.approx((8.0, 4.0))


@pytest.mark.parametrize("payload", [None, {}, {"cells": []}])
def test_figure_and_png_are_none_on_empty_payload(payload):
    assert hm._build_heatmap_figure(payload) is None
    assert heatmap_page_png(payload) is None


def test_png_signature_and_default_size():
    png = heatmap_page_png(_sample_payload(), level_window=(110.0, 112.0), title="Sector Norte")
    assert isinstance(png, bytes)
    assert png.startswith(PNG_SIGNATURE)
    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")
    assert 1200 <= width <= 1800
    assert 600 <= height <= 950


def test_png_with_only_unmeasured_cells():
    cells = [_cell(1.0, 100.5, None, "unmeasured"), _cell(3.0, 100.5, None, "unassessed")]
    png = heatmap_page_png(_payload(cells))
    assert png is not None and png.startswith(PNG_SIGNATURE)


def test_unused_color_helper_is_consistent():
    assert to_rgba(HDEV_COLORS["within_tolerance"]) == to_rgba("#22c55e")
