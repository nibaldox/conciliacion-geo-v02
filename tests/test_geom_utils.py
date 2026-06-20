"""Tests for core.geom_utils — profile deviation, area, column lookup."""
import numpy as np
import pandas as pd
import pytest

from core.geom_utils import (
    calculate_area_between_profiles,
    calculate_profile_deviation,
    find_df_column,
)


class _Profile:
    """Minimal profile stand-in exposing .distances / .elevations."""

    def __init__(self, distances, elevations):
        self.distances = np.asarray(distances, dtype=float)
        self.elevations = np.asarray(elevations, dtype=float)


class TestCalculateProfileDeviation:
    def test_identical_profiles_zero_deviation(self):
        d = [0.0, 10.0, 20.0, 30.0]
        e = [100.0, 90.0, 80.0, 70.0]
        prof = _Profile(d, e)
        devs = calculate_profile_deviation(prof, prof)
        assert devs.shape == (4,)
        assert np.allclose(devs, 0.0)

    def test_offset_profile_constant_deviation(self):
        ref = _Profile([0.0, 10.0, 20.0], [100.0, 100.0, 100.0])
        eval_ = _Profile([0.0, 10.0, 20.0], [103.0, 103.0, 103.0])
        devs = calculate_profile_deviation(ref, eval_)
        assert devs.shape == (3,)
        assert np.allclose(devs, 3.0)

    def test_none_inputs_return_empty(self):
        assert calculate_profile_deviation(None, _Profile([0], [0])).size == 0
        assert calculate_profile_deviation(_Profile([0], [0]), None).size == 0

    def test_empty_eval_returns_zeros(self):
        ref = _Profile([0.0, 10.0], [100.0, 90.0])
        eval_ = _Profile([], [])
        devs = calculate_profile_deviation(ref, eval_)
        assert devs.shape == (0,)

    def test_each_eval_point_distance_to_nearest_ref(self):
        ref = _Profile([0.0, 10.0], [0.0, 0.0])
        eval_ = _Profile([0.0, 10.0], [2.0, 2.0])
        devs = calculate_profile_deviation(ref, eval_)
        assert np.allclose(devs, 2.0)


class TestCalculateAreaBetweenProfiles:
    def test_overbreak_area_positive(self):
        # Design flat at z=100, topo below (z=97) over the whole span → over-excavation.
        d = [0.0, 10.0, 20.0]
        ref = _Profile(d, [100.0, 100.0, 100.0])
        eval_ = _Profile(d, [97.0, 97.0, 97.0])
        area_over, area_under, common_d, z_ref_i, z_eval_i = calculate_area_between_profiles(ref, eval_)
        assert area_over > 0.0
        assert area_under == 0.0
        assert common_d.size > 0
        assert z_ref_i.shape == z_eval_i.shape

    def test_underbreak_area_positive(self):
        # Topo above design → under-excavation (deuda).
        d = [0.0, 10.0, 20.0]
        ref = _Profile(d, [100.0, 100.0, 100.0])
        eval_ = _Profile(d, [103.0, 103.0, 103.0])
        area_over, area_under, _common_d, _z_ref_i, _z_eval_i = calculate_area_between_profiles(ref, eval_)
        assert area_under > 0.0
        assert area_over == 0.0

    def test_none_returns_zeros_pair(self):
        result = calculate_area_between_profiles(None, _Profile([0, 1], [0, 1]))
        assert result == (0.0, 0.0)

    def test_short_profiles_returns_zeros_pair(self):
        ref = _Profile([0.0], [100.0])
        eval_ = _Profile([0.0], [97.0])
        assert calculate_area_between_profiles(ref, eval_) == (0.0, 0.0)


class TestFindDfColumn:
    def test_exact_match(self):
        df = pd.DataFrame({"Kilos_Cargados_real": [1.0], "X": [0.0]})
        assert find_df_column(df, ["Kilos_Cargados_real", "Carga_kg"]) == "Kilos_Cargados_real"

    def test_second_candidate(self):
        df = pd.DataFrame({"Carga_kg": [1.0]})
        assert find_df_column(df, ["Kilos_Cargados_real", "Carga_kg"]) == "Carga_kg"

    def test_case_insensitive_match(self):
        df = pd.DataFrame({"kilos_cargados_real": [1.0]})
        assert find_df_column(df, ["Kilos_Cargados_real"]) == "kilos_cargados_real"

    def test_not_found_raises_by_default(self):
        df = pd.DataFrame({"X": [0.0]})
        with pytest.raises(KeyError):
            find_df_column(df, ["Kilos_Cargados_real"])

    def test_not_found_no_raise_returns_none(self):
        df = pd.DataFrame({"X": [0.0]})
        assert find_df_column(df, ["Kilos_Cargados_real"], raise_error=False) is None
