from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import numpy as np
import pytest

from core.geom_utils import calculate_area_between_profiles
from core.report_volumes import (
    SectionExcavation,
    section_excavation,
    section_influence_widths,
)

REL_TOL = 1e-6
GRID_STEP_M = 0.1

DESIGN = (np.array([0.0, 50.0]), np.array([100.0, 100.0]))
TOPO_D = np.array([0.0, 10.0, 11.0, 20.0, 21.0, 30.0, 35.0, 40.0, 50.0])
TOPO_Z = np.array([100.0, 100.0, 98.0, 98.0, 100.0, 100.0, 103.0, 100.0, 100.0])
TOPO = (TOPO_D, TOPO_Z)
OVER_AREA = 20.0
UNDER_AREA = 15.0


def _profile(distances, elevations):
    return SimpleNamespace(
        distances=np.asarray(distances, dtype=float),
        elevations=np.asarray(elevations, dtype=float),
    )


def _section(name, sector, origin, azimuth=0.0, length=100.0):
    return {
        "name": name,
        "sector": sector,
        "origin": list(origin),
        "azimuth": azimuth,
        "length": length,
    }


class TestSectionExcavationAreas:
    def test_known_overbreak_and_underbreak_areas(self):
        result = section_excavation("S-01", "Norte", DESIGN, TOPO, None, None)

        assert isinstance(result, SectionExcavation)
        assert result.section == "S-01"
        assert result.sector == "Norte"
        assert result.area_over_m2 == pytest.approx(OVER_AREA, rel=REL_TOL)
        assert result.area_under_m2 == pytest.approx(UNDER_AREA, rel=REL_TOL)
        assert result.window is None
        assert result.source == "calculate_area_between_profiles"
        assert result.warnings == ()

    def test_accepts_profile_objects_and_tuples(self):
        from_tuples = section_excavation("S-01", "", DESIGN, TOPO, None, None)
        from_objects = section_excavation(
            "S-01", "", _profile(*DESIGN), _profile(*TOPO), None, None
        )

        assert from_objects.area_over_m2 == from_tuples.area_over_m2
        assert from_objects.area_under_m2 == from_tuples.area_under_m2

    def test_matches_core_function_without_window(self):
        expected_over, expected_under = calculate_area_between_profiles(
            _profile(*DESIGN), _profile(*TOPO)
        )[:2]

        result = section_excavation("S-01", "", DESIGN, TOPO, None, None)

        assert result.area_over_m2 == pytest.approx(expected_over, rel=1e-12)
        assert result.area_under_m2 == pytest.approx(expected_under, rel=1e-12)

    def test_identical_profiles_give_measured_zero_not_none(self):
        result = section_excavation("S-01", "", DESIGN, DESIGN, None, 10.0)

        assert result.area_over_m2 == 0.0
        assert result.area_under_m2 == 0.0
        assert result.volume_over_m3 == 0.0
        assert result.volume_under_m3 == 0.0

    def test_result_is_frozen(self):
        result = section_excavation("S-01", "", DESIGN, TOPO, None, None)

        with pytest.raises(FrozenInstanceError):
            result.area_over_m2 = 1.0

    def test_assumptions_are_spanish_and_label_the_estimate(self):
        result = section_excavation("S-01", "", DESIGN, TOPO, None, 10.0)

        text = " ".join(result.assumptions)
        assert "Volumen estimado" in text
        assert "ancho de influencia" in text


class TestSectionExcavationWindow:
    def test_distance_window_isolates_one_of_two_equal_lumps(self):
        topo = (
            np.array([0.0, 10.0, 11.0, 20.0, 21.0, 30.0, 31.0, 40.0, 41.0, 50.0]),
            np.array([100.0, 100.0, 98.0, 98.0, 100.0, 100.0, 98.0, 98.0, 100.0, 100.0]),
        )
        full = section_excavation("S-01", "", DESIGN, topo, None, None)
        window = (0.0, 25.0, 0.0, 1000.0)

        half = section_excavation("S-01", "", DESIGN, topo, window, None)

        assert full.area_over_m2 == pytest.approx(2 * OVER_AREA, rel=REL_TOL)
        assert half.area_over_m2 == pytest.approx(OVER_AREA, rel=REL_TOL)
        assert half.area_under_m2 == pytest.approx(0.0, abs=1e-9)
        assert half.window == window

    def test_distance_window_cutting_half_the_rectangle(self):
        window = (0.0, 15.5, 0.0, 1000.0)
        depth = 2.0

        result = section_excavation("S-01", "", DESIGN, TOPO, window, None)

        assert result.area_over_m2 == pytest.approx(OVER_AREA / 2, abs=GRID_STEP_M * depth)
        assert result.area_under_m2 == pytest.approx(0.0, abs=1e-9)

    def test_distance_window_equals_core_function_on_clipped_inputs(self):
        window = (0.0, 15.5, 0.0, 1000.0)
        clipped_design = _profile([0.0, 15.5], [100.0, 100.0])
        clipped_topo = _profile([0.0, 10.0, 11.0, 15.5], [100.0, 100.0, 98.0, 98.0])
        expected_over, expected_under = calculate_area_between_profiles(
            clipped_design, clipped_topo
        )[:2]

        result = section_excavation("S-01", "", DESIGN, TOPO, window, None)

        assert result.area_over_m2 == pytest.approx(expected_over, rel=1e-12)
        assert result.area_under_m2 == pytest.approx(expected_under, abs=1e-12)

    def test_elevation_window_excludes_area_below_z_min(self):
        window = (0.0, 50.0, 99.0, 1000.0)

        result = section_excavation("S-01", "", DESIGN, TOPO, window, None)

        assert result.area_over_m2 == pytest.approx(10.5, rel=REL_TOL)
        assert result.area_under_m2 == pytest.approx(UNDER_AREA, rel=REL_TOL)

    def test_elevation_window_excludes_area_above_z_max(self):
        window = (0.0, 50.0, 0.0, 101.5)

        result = section_excavation("S-01", "", DESIGN, TOPO, window, None)

        assert result.area_over_m2 == pytest.approx(OVER_AREA, rel=REL_TOL)
        assert result.area_under_m2 == pytest.approx(11.25, rel=REL_TOL)

    def test_window_assumption_documents_elevation_handling(self):
        window = (0.0, 50.0, 99.0, 1000.0)

        result = section_excavation("S-01", "", DESIGN, TOPO, window, None)

        assert any("cota" in text.lower() for text in result.assumptions)

    def test_window_outside_profiles_gives_none(self):
        window = (200.0, 300.0, 0.0, 1000.0)

        result = section_excavation("S-01", "", DESIGN, TOPO, window, 10.0)

        assert result.area_over_m2 is None
        assert result.area_under_m2 is None
        assert result.volume_over_m3 is None
        assert result.volume_under_m3 is None
        assert result.warnings

    def test_elevation_window_outside_both_profiles_gives_none(self):
        window = (0.0, 50.0, 500.0, 600.0)

        result = section_excavation("S-01", "", DESIGN, TOPO, window, 10.0)

        assert result.area_over_m2 is None
        assert result.area_under_m2 is None
        assert result.warnings

    def test_invalid_window_gives_none(self):
        window = (25.0, 5.0, 0.0, 1000.0)

        result = section_excavation("S-01", "", DESIGN, TOPO, window, 10.0)

        assert result.area_over_m2 is None
        assert result.area_under_m2 is None
        assert result.warnings


class TestSectionExcavationMissingData:
    @pytest.mark.parametrize(
        "design, topo",
        [
            ((np.array([]), np.array([])), TOPO),
            (DESIGN, (np.array([]), np.array([]))),
            (DESIGN, (np.array([5.0]), np.array([100.0]))),
            (None, TOPO),
            (DESIGN, None),
            (DESIGN, (np.array([60.0, 80.0]), np.array([100.0, 98.0]))),
            (DESIGN, (np.array([50.0, 80.0]), np.array([100.0, 98.0]))),
            (DESIGN, (np.array([0.0, np.nan]), np.array([100.0, 98.0]))),
        ],
        ids=[
            "empty-design",
            "empty-topo",
            "single-point",
            "design-none",
            "topo-none",
            "no-overlap",
            "touching-only",
            "non-finite-leaves-one-point",
        ],
    )
    def test_unusable_profiles_give_none_and_warning(self, design, topo):
        result = section_excavation("S-01", "Norte", design, topo, None, 10.0)

        assert result.area_over_m2 is None
        assert result.area_under_m2 is None
        assert result.volume_over_m3 is None
        assert result.volume_under_m3 is None
        assert result.influence_width_m == 10.0
        assert len(result.warnings) >= 1

    def test_empty_profile_objects_give_none(self):
        result = section_excavation(
            "S-01", "", _profile([], []), _profile(*TOPO), None, 10.0
        )

        assert result.area_over_m2 is None
        assert result.area_under_m2 is None
        assert result.warnings


class TestSectionExcavationVolumes:
    def test_volume_is_area_times_width(self):
        result = section_excavation("S-01", "", DESIGN, TOPO, None, 12.5)

        assert result.influence_width_m == 12.5
        assert result.volume_over_m3 == pytest.approx(result.area_over_m2 * 12.5, rel=1e-12)
        assert result.volume_under_m3 == pytest.approx(result.area_under_m2 * 12.5, rel=1e-12)
        assert result.volume_over_m3 == pytest.approx(250.0, rel=REL_TOL)
        assert result.volume_under_m3 == pytest.approx(187.5, rel=REL_TOL)

    def test_missing_width_gives_none_volume_but_area_present(self):
        result = section_excavation("S-01", "", DESIGN, TOPO, None, None)

        assert result.area_over_m2 == pytest.approx(OVER_AREA, rel=REL_TOL)
        assert result.area_under_m2 == pytest.approx(UNDER_AREA, rel=REL_TOL)
        assert result.influence_width_m is None
        assert result.volume_over_m3 is None
        assert result.volume_under_m3 is None

    @pytest.mark.parametrize("width", [float("nan"), float("inf"), 0.0, -5.0])
    def test_unusable_width_gives_none_volume_and_warning(self, width):
        result = section_excavation("S-01", "", DESIGN, TOPO, None, width)

        assert result.area_over_m2 == pytest.approx(OVER_AREA, rel=REL_TOL)
        assert result.influence_width_m is None
        assert result.volume_over_m3 is None
        assert result.volume_under_m3 is None
        assert result.warnings


class TestSectionInfluenceWidths:
    def test_five_sections_equally_spaced_at_ten_metres(self):
        sections = [_section(f"S-{i}", "Norte", (10.0 * i, 0.0)) for i in range(5)]

        widths = section_influence_widths(sections)

        assert set(widths) == {("Norte", f"S-{i}") for i in range(5)}
        for value in widths.values():
            assert value == pytest.approx(10.0)

    def test_uneven_spacing(self):
        sections = [
            _section("A", "Norte", (0.0, 0.0)),
            _section("B", "Norte", (10.0, 0.0)),
            _section("C", "Norte", (30.0, 0.0)),
            _section("D", "Norte", (60.0, 0.0)),
        ]

        widths = section_influence_widths(sections)

        assert widths[("Norte", "A")] == pytest.approx(10.0)
        assert widths[("Norte", "B")] == pytest.approx(15.0)
        assert widths[("Norte", "C")] == pytest.approx(25.0)
        assert widths[("Norte", "D")] == pytest.approx(30.0)

    def test_single_section_sector_gives_none(self):
        widths = section_influence_widths([_section("A", "Norte", (0.0, 0.0))])

        assert widths == {("Norte", "A"): None}

    def test_two_sectors_are_independent(self):
        sections = [
            _section("N1", "Norte", (0.0, 0.0)),
            _section("S1", "Sur", (1000.0, 0.0)),
            _section("N2", "Norte", (20.0, 0.0)),
            _section("S2", "Sur", (1040.0, 0.0)),
            _section("E1", "Este", (5000.0, 0.0)),
        ]

        widths = section_influence_widths(sections)

        assert widths[("Norte", "N1")] == pytest.approx(20.0)
        assert widths[("Norte", "N2")] == pytest.approx(20.0)
        assert widths[("Sur", "S1")] == pytest.approx(40.0)
        assert widths[("Sur", "S2")] == pytest.approx(40.0)
        assert widths[("Este", "E1")] is None

    def test_distance_is_measured_between_origins_not_line_ends(self):
        sections = [
            _section("A", "Norte", (0.0, 0.0), azimuth=90.0, length=100.0),
            _section("B", "Norte", (10.0, 0.0), azimuth=0.0, length=240.0),
            _section("C", "Norte", (20.0, 0.0), azimuth=315.0, length=60.0),
        ]

        widths = section_influence_widths(sections)

        assert widths[("Norte", "A")] == pytest.approx(10.0)
        assert widths[("Norte", "B")] == pytest.approx(10.0)
        assert widths[("Norte", "C")] == pytest.approx(10.0)

    def test_only_origin_is_required(self):
        sections = [
            {"name": "A", "sector": "Norte", "origin": [0.0, 0.0]},
            {"name": "B", "sector": "Norte", "origin": (10.0, 0.0), "azimuth": None, "length": None},
            {"name": "C", "sector": "Norte", "origin": [10.0, 30.0], "azimuth": "n/a"},
        ]

        widths = section_influence_widths(sections)

        assert widths[("Norte", "A")] == pytest.approx(10.0)
        assert widths[("Norte", "B")] == pytest.approx(20.0)
        assert widths[("Norte", "C")] == pytest.approx(30.0)

    def test_follows_input_order_not_coordinates(self):
        sections = [
            _section("A", "Norte", (0.0, 0.0)),
            _section("B", "Norte", (30.0, 0.0)),
            _section("C", "Norte", (10.0, 0.0)),
        ]

        widths = section_influence_widths(sections)

        assert widths[("Norte", "A")] == pytest.approx(30.0)
        assert widths[("Norte", "B")] == pytest.approx(25.0)
        assert widths[("Norte", "C")] == pytest.approx(20.0)

    def test_missing_sector_uses_empty_string(self):
        sections = [
            {"name": "A", "origin": [0.0, 0.0], "azimuth": 0.0, "length": 100.0},
            {"name": "B", "sector": None, "origin": [10.0, 0.0], "azimuth": 0.0, "length": 100.0},
        ]

        widths = section_influence_widths(sections)

        assert widths[("", "A")] == pytest.approx(10.0)
        assert widths[("", "B")] == pytest.approx(10.0)

    def test_section_without_geometry_gives_none_for_it_and_its_neighbours(self):
        sections = [
            _section("A", "Norte", (0.0, 0.0)),
            _section("B", "Norte", (10.0, 0.0)),
            {"name": "C", "sector": "Norte", "origin": None, "azimuth": 0.0, "length": 100.0},
            _section("D", "Norte", (30.0, 0.0)),
            _section("E", "Norte", (40.0, 0.0)),
        ]

        widths = section_influence_widths(sections)

        assert widths[("Norte", "A")] == pytest.approx(10.0)
        assert widths[("Norte", "B")] is None
        assert widths[("Norte", "C")] is None
        assert widths[("Norte", "D")] is None
        assert widths[("Norte", "E")] == pytest.approx(10.0)

    def test_coincident_origins_give_none_not_zero(self):
        sections = [
            _section("A", "Norte", (0.0, 0.0), azimuth=90.0, length=100.0),
            _section("B", "Norte", (0.0, 0.0), azimuth=0.0, length=100.0),
        ]

        widths = section_influence_widths(sections)

        assert widths[("Norte", "A")] is None
        assert widths[("Norte", "B")] is None

    def test_empty_input(self):
        assert section_influence_widths([]) == {}
