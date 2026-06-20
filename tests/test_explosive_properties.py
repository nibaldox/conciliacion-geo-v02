"""Tests for core.explosive_properties — ENAEX explosive catalog.

Covers density / energy lookups (Pirex + Enaline) and the imperial-vs-metric
diameter parser used by the 3D viewer and the ENAEX report ingest.
"""
import math

import pytest

from core.explosive_properties import (
    ENALINE_DENSITY_G_CM3,
    ENALINE_ENERGY_MJ_KG,
    PIREX_DENSITY_G_CM3,
    PIREX_ENERGY_MJ_KG,
    get_explosive_density_g_cm3,
    get_explosive_energy_mj_kg,
    parse_diameter_mm,
)


class TestExplosiveDensity:
    def test_pirex_known(self):
        assert get_explosive_density_g_cm3("Pirex-930") == pytest.approx(1.20)
        assert get_explosive_density_g_cm3("Pirex-920") == pytest.approx(1.15)
        assert get_explosive_density_g_cm3("Pirex-950") == pytest.approx(1.23)
        assert get_explosive_density_g_cm3("Pirex-970") == pytest.approx(1.25)

    def test_pirex_unknown(self):
        assert get_explosive_density_g_cm3("Pirex-999") == PIREX_DENSITY_G_CM3["Pirex-930"]
        assert get_explosive_density_g_cm3("Pirex-930 Heavy") == PIREX_DENSITY_G_CM3["Pirex-930"]

    def test_enaline(self):
        assert get_explosive_density_g_cm3("Enaline 1 1/4*12") == ENALINE_DENSITY_G_CM3
        assert get_explosive_density_g_cm3("Enaline") == ENALINE_DENSITY_G_CM3

    def test_empty(self):
        assert get_explosive_density_g_cm3("") is None
        assert get_explosive_density_g_cm3(None) is None

    def test_anfo_fallback(self):
        assert get_explosive_density_g_cm3("ANFO") is None
        assert get_explosive_density_g_cm3("Heavy ANFO") is None
        assert get_explosive_density_g_cm3("Unknown") is None


class TestExplosiveEnergy:
    def test_pirex_known(self):
        assert get_explosive_energy_mj_kg("Pirex-930") == pytest.approx(3.05)
        assert get_explosive_energy_mj_kg("Pirex-920") == pytest.approx(2.95)
        assert get_explosive_energy_mj_kg("Pirex-950") == pytest.approx(3.15)
        assert get_explosive_energy_mj_kg("Pirex-970") == pytest.approx(3.25)

    def test_enaline(self):
        assert get_explosive_energy_mj_kg("Enaline 1 1/4*12") == ENALINE_ENERGY_MJ_KG
        assert get_explosive_energy_mj_kg("Enaline") == ENALINE_ENERGY_MJ_KG

    def test_unknown_returns_none(self):
        assert get_explosive_energy_mj_kg("ANFO") is None
        assert get_explosive_energy_mj_kg("") is None
        assert get_explosive_energy_mj_kg("Desconocido") is None


class TestParseDiameter:
    def test_imperial_10_5_8(self):
        expected = 10.625 * 25.4
        assert parse_diameter_mm("10 5/8") == pytest.approx(expected, rel=1e-6)
        assert parse_diameter_mm('10 5/8"') == pytest.approx(expected, rel=1e-6)

    def test_imperial_6_1_2(self):
        expected = 6.5 * 25.4
        assert parse_diameter_mm("6 1/2") == pytest.approx(expected, rel=1e-6)
        assert parse_diameter_mm('6 1/2"') == pytest.approx(expected, rel=1e-6)

    def test_metric_270(self):
        assert parse_diameter_mm("270") == pytest.approx(270.0)
        assert parse_diameter_mm(270) == pytest.approx(270.0)
        assert parse_diameter_mm(270.0) == pytest.approx(270.0)

    def test_metric_165(self):
        assert parse_diameter_mm("165") == pytest.approx(165.0)
        assert parse_diameter_mm(165.0) == pytest.approx(165.0)

    def test_invalid_string(self):
        assert parse_diameter_mm("abc") is None
        assert parse_diameter_mm("1/0") is None
        assert parse_diameter_mm("1 / 0") is None
        assert parse_diameter_mm("") is None
        assert parse_diameter_mm(None) is None

    def test_edge_case_quarter_inch(self):
        assert parse_diameter_mm("1/4") == pytest.approx(0.25 * 25.4)

    def test_edge_case_three_quarter_inch(self):
        assert parse_diameter_mm("3/4") == pytest.approx(0.75 * 25.4)
