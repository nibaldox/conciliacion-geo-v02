"""Tests for core.report_charts — donuts, plan view and section profiles."""
import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox
from PIL import Image
import pytest

from core.report_charts import (
    STATUS_COLORS,
    _build_plan_view_figure,
    _build_section_profile_figure,
    parameter_donuts_png,
    parameter_pct,
    plan_view_png,
    profile_title,
    section_profile_png,
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _tol_bands(ax):
    bands = []
    for collection in ax.collections:
        if collection.get_gid() == "tol-band":
            bands.extend(np.asarray(path.vertices)
                         for path in collection.get_paths())
    return bands


def _bench_labels(ax):
    return [t for t in ax.texts if t.get_gid() == "bench-label"]


def _plan_labels(ax):
    return [t for t in ax.texts if t.get_gid() == "plan-label"]


def _open_size(png):
    img = Image.open(io.BytesIO(png))
    img.load()
    return img.size


def _sample_parameters():
    return [
        {"label": "Altura de banco", "cumple": 11, "no_cumple": 1},
        {"label": "Ángulo de cara", "cumple": 3, "no_cumple": 9},
        {"label": "Ancho de berma", "cumple": 7, "no_cumple": 5},
    ]


def _sample_sections():
    return [
        {"name": "S-01", "origin": [92355.0, 21003.0], "azimuth": 16.65,
         "length": 40.0, "worst_status": "CUMPLE"},
        {"name": "S-02", "polyline": [[92400.0, 21050.0], [92440.0, 21080.0]],
         "worst_status": "NO_CUMPLE"},
        {"name": "S-03", "x0": 92500.0, "y0": 21100.0, "x1": 92530.0,
         "y1": 21120.0, "worst_status": "FUERA"},
        {"name": "S-04", "origin": [92560.0, 21140.0], "azimuth": 20.0,
         "length": 40.0, "worst_status": "UNKNOWN"},
    ]


def _sample_profile():
    design_d = [0, 10, 20, 30, 40]
    design_z = [3125.0, 3110.0, 3095.0, 3080.0, 3065.0]
    topo_d = [0, 10, 20, 30, 40]
    topo_z = [3126.8, 3111.6, 3096.0, 3078.0, 3066.0]
    return {
        "name": "S-01",
        "sector": "Fase 5",
        "status_label": "NO CUMPLE",
        "design": (design_d, design_z),
        "topo": (topo_d, topo_z),
        "reconciled_topo": (topo_d, topo_z),
        "reconciled_design": (design_d, design_z),
        "tolerance_band": {"crest": 1.0, "toe": 1.0},
        "benches": [
            {"label": "B1", "crest_dist": 0.0, "crest_z": 3125.0,
             "toe_dist": 4.0, "toe_z": 3110.0, "deviation_text": "+0.9 m",
             "status": "CUMPLE"},
            {"label": "B2", "crest_dist": 17.0, "crest_z": 3110.0,
             "toe_dist": 20.0, "toe_z": 3095.0, "deviation_text": "+0.6 m",
             "status": "NO_CUMPLE"},
        ],
        "blast_holes": [
            {"dist": 3.0, "collar_z": 3127.0, "toe_z": 3108.0},
            {"dist": 15.0, "collar_z": 3112.0, "toe_z": 3093.0},
        ],
    }


class TestParameterPct:
    def test_matches_one_decimal_table_value(self):
        assert f"{parameter_pct(11, 1):.1f}%" == "91.7%"
        assert f"{parameter_pct(3, 9):.1f}%" == "25.0%"

    def test_zero_total(self):
        assert parameter_pct(0, 0) == 0.0


class TestParameterDonuts:
    def test_other_state_bucket_label_is_explicit_and_legible(self, monkeypatch):
        from core import report_charts

        observed = {}
        render = report_charts._fig_to_png

        def inspect_before_render(fig, dpi):
            observed["texts"] = [text.get_text() for ax in fig.axes for text in ax.texts]
            observed["labels"] = [
                text for ax in fig.axes for text in ax.texts
                if text.get_text().startswith("Otros estados")
            ]
            observed["centers"] = [
                text for ax in fig.axes for text in ax.texts
                if text.get_gid() == "donut-center"
            ]
            observed["colors"] = [
                patch.get_facecolor() for ax in fig.axes for patch in ax.patches
            ]
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            observed["overlaps"] = []
            observed["center_title_label_overlaps"] = []
            for ax in fig.axes:
                artists = [ax.title, *ax.texts]
                boxes = [artist.get_window_extent(renderer) for artist in artists]
                observed["overlaps"].extend(
                    (left, right)
                    for index, left in enumerate(boxes)
                    for right in boxes[index + 1:]
                    if left.overlaps(right)
                )
                center = next(text for text in ax.texts if text.get_gid() == "donut-center")
                center_box = center.get_window_extent(renderer)
                title_box = ax.title.get_window_extent(renderer)
                labels = [text for text in ax.texts if text is not center]
                observed["center_title_label_overlaps"].extend(
                    (kind, label.get_text())
                    for kind, box in (("title", title_box), ("label", None))
                    for label in (labels if kind == "label" else [ax.title])
                    if center_box.overlaps(
                        label.get_window_extent(renderer) if box is None else box
                    )
                )
            return render(fig, dpi)

        monkeypatch.setattr(report_charts, "_fig_to_png", inspect_before_render)
        png = parameter_donuts_png([{"label": "Ángulo", "cumple": 3, "no_cumple": 9}])

        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert "Otros estados\n9" in observed["texts"]
        assert "Cumple\n3" in observed["texts"]
        assert not any("No cumple" in text for text in observed["texts"])
        assert observed["labels"]
        assert observed["labels"][0].get_fontsize() == 10
        assert observed["labels"][0].get_fontweight() == "semibold"
        assert len(observed["centers"]) == 1
        assert observed["centers"][0].get_text() == "25.0%"
        assert observed["overlaps"] == []
        assert observed["center_title_label_overlaps"] == []
        assert observed["colors"] == [
            matplotlib.colors.to_rgba("#A9D6AE"),
            matplotlib.colors.to_rgba("#F1A9A9"),
        ]

    def test_returns_png_bytes(self):
        png = parameter_donuts_png(_sample_parameters())
        assert isinstance(png, bytes)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = _open_size(png)
        assert 1000 < width < 1300
        assert 220 < height < 400

    def test_deterministic(self):
        assert parameter_donuts_png(_sample_parameters()) == parameter_donuts_png(_sample_parameters())

    def test_dpi_scales_dimensions(self):
        low = _open_size(parameter_donuts_png(_sample_parameters(), dpi=100))
        high = _open_size(parameter_donuts_png(_sample_parameters(), dpi=200))
        assert high[0] > low[0]

    @pytest.mark.parametrize("empty", [[], None])
    def test_empty_returns_none(self, empty):
        assert parameter_donuts_png(empty) is None

    def test_all_zero_counts_returns_none(self):
        assert parameter_donuts_png([{"label": "X", "cumple": 0, "no_cumple": 0}]) is None


class TestPlanView:
    def test_returns_png_bytes(self):
        png = plan_view_png(_sample_sections())
        assert isinstance(png, bytes)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = _open_size(png)
        assert 1250 < width < 1750
        assert 1000 < height < 1400

    def test_with_contours_dict(self):
        sections = _sample_sections()
        xs, ys, zs = [], [], []
        for i in range(20):
            for j in range(20):
                xs.append(92350.0 + i * 20.0)
                ys.append(21000.0 + j * 12.0)
                zs.append(3100.0 + i * 1.5 + j * 1.0)
        png = plan_view_png(sections, contours={"x": xs, "y": ys, "z": zs})
        assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_with_contours_polylines(self):
        contours = [[[92350.0, 21000.0], [92450.0, 21000.0]]]
        png = plan_view_png(_sample_sections(), contours=contours)
        assert isinstance(png, bytes)

    def test_size_budget_default(self):
        png = plan_view_png(_sample_sections())
        assert png is not None and len(png) < 400_000

    def test_deterministic(self):
        assert plan_view_png(_sample_sections()) == plan_view_png(_sample_sections())

    @pytest.mark.parametrize("empty", [[], None])
    def test_empty_returns_none(self, empty):
        assert plan_view_png(empty) is None

    def test_no_geometry_returns_none(self):
        assert plan_view_png([{"name": "S-01", "worst_status": "CUMPLE"}]) is None

    def test_filtered_out_sections_are_gray_dashed_and_listed_separately(self):
        sections = [
            {**_sample_sections()[0], "included": True},
            {**_sample_sections()[1], "included": False, "worst_status": "UNKNOWN"},
        ]
        _fig, ax = _build_plan_view_figure(sections)

        included = next(line for line in ax.lines if line.get_gid() == "plan-section")
        excluded = next(line for line in ax.lines if line.get_gid() == "plan-section-excluded")
        assert included.get_color() == STATUS_COLORS["CUMPLE"]
        assert excluded.get_color() == "#9CA3AF"
        assert excluded.get_linestyle() == "--"
        assert any(text.get_text() == "Excluida por filtros (1)" for text in ax.get_legend().get_texts())
        assert any(text.get_gid() == "plan-label-excluded" for text in ax.texts)

    def test_unknown_sections_without_filter_marker_keep_unknown_color(self):
        section = {**_sample_sections()[0], "worst_status": "UNKNOWN"}
        _fig, ax = _build_plan_view_figure([section])

        line = next(line for line in ax.lines if line.get_gid() == "plan-section")
        assert line.get_color() == STATUS_COLORS["UNKNOWN"]
        assert not any("Excluida por filtros" in text.get_text() for text in ax.get_legend().get_texts())


class TestProfileTitle:
    def test_no_trailing_dash(self):
        title = profile_title({"name": "S-01", "sector": "X", "status_label": "ESTADO"})
        assert title == "Sección S-01 · Sector X · ESTADO"
        assert not title.rstrip().endswith("-")

    def test_missing_parts_dropped(self):
        assert profile_title({"name": "S-01"}) == "Sección S-01"
        assert profile_title({}) == "Perfil de sección"


class TestSectionProfile:
    def test_full_returns_png_bytes(self):
        png = section_profile_png(_sample_profile(), size="full")
        assert isinstance(png, bytes)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = _open_size(png)
        assert 1000 < width < 1500
        assert 850 < height < 1250

    def test_compact_smaller_and_within_budget(self):
        full = section_profile_png(_sample_profile(), size="full")
        compact = section_profile_png(_sample_profile(), size="compact")
        assert compact is not None and full is not None
        assert len(compact) < 120_000
        assert _open_size(compact)[0] < _open_size(full)[0]

    def test_dpi_scales_dimensions(self):
        low = _open_size(section_profile_png(_sample_profile(), dpi=100))
        high = _open_size(section_profile_png(_sample_profile(), dpi=200))
        assert high[0] > low[0]

    def test_minimal_design_only(self):
        png = section_profile_png({"name": "S-09", "design": ([0, 10], [100, 90])})
        assert isinstance(png, bytes)

    def test_blast_and_tolerance_optional(self):
        profile = _sample_profile()
        profile.pop("blast_holes")
        profile.pop("tolerance_band")
        png = section_profile_png(profile)
        assert isinstance(png, bytes)

    def test_deterministic(self):
        assert section_profile_png(_sample_profile()) == section_profile_png(_sample_profile())

    @pytest.mark.parametrize("empty", [{}, None])
    def test_empty_returns_none(self, empty):
        assert section_profile_png(empty) is None

    def test_no_geometry_returns_none(self):
        assert section_profile_png({"name": "S-01", "sector": "X"}) is None


class TestToleranceBand:
    def test_bands_lie_within_a_design_bench_extent(self):
        profile = _sample_profile()
        _fig, ax = _build_section_profile_figure(profile)
        bands = _tol_bands(ax)
        assert bands
        extents = [
            (min(b["crest_dist"], b["toe_dist"]), max(b["crest_dist"], b["toe_dist"]))
            for b in profile["benches"]
        ]
        for band in bands:
            xs = band[:, 0]
            lo, hi = float(min(xs)), float(max(xs))
            assert any(lo >= e[0] - 1e-6 and hi <= e[1] + 1e-6 for e in extents)

    def test_asymmetric_signed_tolerances(self):
        profile = {
            "name": "S-1",
            "design": ([0.0, 10.0], [100.0, 90.0]),
            "tolerance_band": {"crest": {"neg": 0.5, "pos": 1.5},
                               "toe": {"neg": 1.0, "pos": 0.25}},
            "benches": [{"label": "B1", "crest_dist": 0.0, "crest_z": 100.0,
                         "toe_dist": 10.0, "toe_z": 90.0, "status": "CUMPLE"}],
        }
        _fig, ax = _build_section_profile_figure(profile)
        band = _tol_bands(ax)[0]
        ys = band[:, 1]
        assert float(max(ys)) == pytest.approx(101.5)
        assert float(min(ys)) == pytest.approx(89.0)

    def test_scalar_tolerance_is_symmetric(self):
        profile = {
            "name": "S-1",
            "design": ([0.0, 10.0], [100.0, 90.0]),
            "tolerance_band": {"crest": 2.0, "toe": 2.0},
            "benches": [{"label": "B1", "crest_dist": 0.0, "crest_z": 100.0,
                         "toe_dist": 10.0, "toe_z": 90.0, "status": "CUMPLE"}],
        }
        _fig, ax = _build_section_profile_figure(profile)
        ys = _tol_bands(ax)[0][:, 1]
        assert float(max(ys)) == pytest.approx(102.0)
        assert float(min(ys)) == pytest.approx(88.0)

    def test_legend_labels_signed_tolerance(self):
        _fig, ax = _build_section_profile_figure(_sample_profile())
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert any("Tolerancia de altura" in text and "\u2212" in text
                   for text in labels)

    def test_no_band_without_tolerance(self):
        profile = _sample_profile()
        profile.pop("tolerance_band")
        _fig, ax = _build_section_profile_figure(profile)
        assert _tol_bands(ax) == []

    def test_missing_bench_band_uses_design_corner(self):
        profile = {
            "name": "S-1",
            "design": ([0.0, 10.0], [100.0, 90.0]),
            "tolerance_band": {"crest": {"neg": 1.0, "pos": 1.0},
                               "toe": {"neg": 1.0, "pos": 1.0}},
            "benches": [{"label": "B1", "status": "NO_CUMPLE", "type": "MISSING",
                         "design_crest_dist": 0.0, "design_crest_z": 100.0,
                         "design_toe_dist": 10.0, "design_toe_z": 90.0}],
        }
        _fig, ax = _build_section_profile_figure(profile)
        band = _tol_bands(ax)[0]
        xs = band[:, 0]
        assert (float(min(xs)), float(max(xs))) == (0.0, 10.0)


class TestBenchAnnotations:
    def _profile(self):
        return {
            "name": "S-1",
            "design": ([0.0, 40.0], [100.0, 60.0]),
            "benches": [
                {"label": "B1", "crest_dist": 0.0, "crest_z": 100.0,
                 "toe_dist": 5.0, "toe_z": 95.0, "deviation_text": "+0.2 m",
                 "status": "CUMPLE"},
                {"label": "B2", "crest_dist": 10.0, "crest_z": 95.0,
                 "toe_dist": 15.0, "toe_z": 90.0, "status": "FUERA"},
                {"label": "B3", "crest_dist": 20.0, "crest_z": 90.0,
                 "toe_dist": 25.0, "toe_z": 85.0, "status": "NO_CUMPLE",
                 "type": "MISSING"},
                {"label": "B4", "crest_dist": 30.0, "crest_z": 85.0,
                 "toe_dist": 35.0, "toe_z": 80.0, "status": "UNKNOWN",
                 "type": "EXTRA"},
            ],
        }

    def test_colors_map_to_status(self):
        _fig, ax = _build_section_profile_figure(self._profile())
        pairs = [(t.get_text(), t.get_color()) for t in _bench_labels(ax)]
        assert any(t.startswith("B1") and c == STATUS_COLORS["CUMPLE"] for t, c in pairs)
        assert any(t.startswith("B2") and c == STATUS_COLORS["FUERA"] for t, c in pairs)
        assert any(t.startswith("B3") and c == STATUS_COLORS["NO_CUMPLE"] for t, c in pairs)
        assert any(t.startswith("B4") and c == STATUS_COLORS["UNKNOWN"] for t, c in pairs)

    def test_missing_and_extra_get_qualifiers(self):
        _fig, ax = _build_section_profile_figure(self._profile())
        texts = [t.get_text() for t in _bench_labels(ax)]
        assert any(t.startswith("B3") and "no construido" in t for t in texts)
        assert any(t.startswith("B4") and "adicional" in t for t in texts)
        assert any(t.startswith("B1") and "+0.2 m" in t for t in texts)

    def test_leader_lines_kept(self):
        _fig, ax = _build_section_profile_figure(self._profile())
        leaders = [ln for ln in ax.get_lines() if ln.get_gid() == "bench-leader"]
        assert len(leaders) == len(_bench_labels(ax))
        assert leaders


class TestDeterministicLayout:
    def test_legend_inside_saved_area(self):
        _fig, ax = _build_section_profile_figure(_sample_profile())
        fig = ax.figure
        fig.set_dpi(130)
        renderer = fig.canvas.get_renderer()
        tight = Bbox.union([a.get_tightbbox(renderer) for a in fig.axes])
        legend = ax.get_legend().get_window_extent(renderer)
        assert tight.x0 <= legend.x0 and legend.x1 <= tight.x1
        assert tight.y0 <= legend.y0 and legend.y1 <= tight.y1

    def test_dimensions_stable_and_uncropped(self):
        profile = _sample_profile()
        first = _open_size(section_profile_png(profile, size="full"))
        second = _open_size(section_profile_png(profile, size="full"))
        assert first == second
        assert 1000 < first[0] < 1500
        assert 850 < first[1] < 1250


class TestPlanLabels:
    def _dense_sections(self, n=30):
        return [
            {"name": f"S-{i:02d}",
             "polyline": [[i * 10.0, 0.0], [i * 10.0 + 6.0, 4.0]],
             "worst_status": "NO_CUMPLE" if i % 3 == 0 else "CUMPLE"}
            for i in range(n)
        ]

    def test_labels_keep_non_compliant_first_and_last(self):
        sections = self._dense_sections()
        _fig, ax = _build_plan_view_figure(sections)
        labels = [t.get_text() for t in _plan_labels(ax)]
        assert "S-00" in labels and "S-29" in labels
        for sec in sections:
            if sec["worst_status"] != "CUMPLE":
                assert sec["name"] in labels

    def test_dense_labels_are_thinned(self):
        sections = self._dense_sections()
        _fig, ax = _build_plan_view_figure(sections)
        assert 0 < len(_plan_labels(ax)) < len(sections)

    def test_no_leader_lines(self):
        _fig, ax = _build_plan_view_figure(self._dense_sections())
        assert all(t.arrow_patch is None for t in _plan_labels(ax))

    def test_label_sits_beyond_outer_endpoint(self):
        sections = [
            {"name": "S-1", "polyline": [[0.0, 0.0], [40.0, 0.0]],
             "worst_status": "CUMPLE"},
            {"name": "S-2", "polyline": [[0.0, 10.0], [40.0, 10.0]],
             "worst_status": "NO_CUMPLE"},
        ]
        _fig, ax = _build_plan_view_figure(sections)
        positions = {t.get_text(): t.get_position() for t in _plan_labels(ax)}
        assert positions["S-1"][0] > 40.0
        assert positions["S-2"][0] > 40.0
        assert positions["S-1"][0] < 47.0

    def test_legend_counts_only_present_statuses(self):
        _fig, ax = _build_plan_view_figure(_sample_sections())
        texts = [t.get_text() for t in ax.get_legend().get_texts()]
        assert "Cumple (1)" in texts
        assert "No cumple (1)" in texts
        assert "Fuera de tolerancia (1)" in texts
        assert "Sin evaluar (1)" in texts



class TestRasterGuard:
    def test_construction_failure_clears_registered_figure(self, monkeypatch):
        from core import report_charts

        created = []
        make_figure = report_charts._new_figure
        make_subplots = report_charts.Figure.subplots

        def capture_figure(**kwargs):
            fig = make_figure(**kwargs)
            created.append(fig)
            return fig

        def fail_after_axes_created(fig, *args, **kwargs):
            make_subplots(fig, *args, **kwargs)
            raise RuntimeError("construction failed")

        monkeypatch.setattr(report_charts, "_new_figure", capture_figure)
        monkeypatch.setattr(report_charts.Figure, "subplots", fail_after_axes_created)
        with pytest.raises(RuntimeError, match="construction failed"):
            report_charts.plan_view_png(_sample_sections())

        assert len(created) == 1
        assert created[0].axes == []
        assert created[0].canvas is None

    def test_huge_figure_is_rejected_before_allocating(self):
        from core.report_charts import _fig_to_png

        fig, ax = plt.subplots(figsize=(400, 300))
        ax.plot([0, 1], [0, 1])
        with pytest.raises(ValueError, match="too large"):
            _fig_to_png(fig, 150)
        assert fig.axes == []
        assert fig.canvas is None

    def test_failed_save_clears_figure(self, monkeypatch):
        from core.report_charts import _fig_to_png

        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1])

        def fail_save(*_args, **_kwargs):
            raise RuntimeError("save failed")

        monkeypatch.setattr(fig, "savefig", fail_save)
        with pytest.raises(RuntimeError, match="save failed"):
            _fig_to_png(fig, 100)
        assert fig.axes == []
        assert fig.canvas is None

    def test_profile_raster_stays_bounded(self):
        png = section_profile_png(_sample_profile(), size="full", dpi=130)
        width, height = _open_size(png)
        assert width * height < 4_000_000


def test_concurrent_public_renders_are_isolated_and_deterministic():
    renderers = (
        lambda: parameter_donuts_png(_sample_parameters()),
        lambda: plan_view_png(_sample_sections()),
        lambda: section_profile_png(_sample_profile(), size="full"),
    )
    expected = [renderer() for renderer in renderers]
    with ThreadPoolExecutor(max_workers=4) as executor:
        rendered = list(executor.map(lambda i: renderers[i % len(renderers)](), range(12)))

    assert rendered == [expected[i % len(expected)] for i in range(12)]
    assert all(png.startswith(b"\x89PNG\r\n\x1a\n") for png in rendered)
    assert plt.get_fignums() == []
