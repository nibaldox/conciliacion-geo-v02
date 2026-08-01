"""Tests for core.explosive_properties — ENAEX explosive catalog registry.

Spec §4.4: every product must store normalized name, density, absolute
energy, RWS, VOD (if available), data source, datasheet version/date and
validation status. Unknown products return an explicit UNKNOWN state —
never a silent ANFO fallback.
"""
import pytest

from core.explosive_properties import (
    ENALINE_DENSITY_G_CM3,
    ENALINE_ENERGY_MJ_KG,
    EXPLOSIVE_PRODUCTS,
    ExplosiveProduct,
    get_explosive_density_g_cm3,
    get_explosive_energy_mj_kg,
    get_explosive_status,
    parse_diameter_mm,
    resolve_explosive,
)


class TestRegistry:
    def test_all_pirex_grades_present(self):
        for grade in ("Pirex-920", "Pirex-930", "Pirex-950", "Pirex-970"):
            assert grade in EXPLOSIVE_PRODUCTS

    def test_product_fields_complete(self):
        p = EXPLOSIVE_PRODUCTS["Pirex-930"]
        assert isinstance(p, ExplosiveProduct)
        assert p.energy_mj_kg == pytest.approx(3.05)
        assert p.density_g_cm3 == pytest.approx(1.20)
        assert p.rws is not None or p.rws is None  # optional field is present
        assert hasattr(p, "vod_m_s")
        assert p.source  # provenance always recorded
        assert p.validation_status  # never silently assumed

    def test_anfo_is_reference(self):
        p = EXPLOSIVE_PRODUCTS["ANFO"]
        assert p.energy_mj_kg == pytest.approx(3.72)
        assert p.density_g_cm3 == pytest.approx(0.80)
        assert p.rws == pytest.approx(1.0)

    def test_resolve_exact_and_family(self):
        assert resolve_explosive("Pirex-930").normalized_name == "Pirex-930"
        fam = resolve_explosive("Pirex-930 Heavy")
        assert fam.normalized_name == "Pirex-930"
        assert fam.is_exact is False

    def test_resolve_unknown_grade_is_none(self):
        assert resolve_explosive("Pirex-999") is None
        assert resolve_explosive("Desconocido-X") is None
        assert resolve_explosive("") is None
        assert resolve_explosive(None) is None


class TestExplosiveDensity:
    def test_pirex_known(self):
        assert get_explosive_density_g_cm3("Pirex-930") == pytest.approx(1.20)
        assert get_explosive_density_g_cm3("Pirex-920") == pytest.approx(1.15)
        assert get_explosive_density_g_cm3("Pirex-950") == pytest.approx(1.23)
        assert get_explosive_density_g_cm3("Pirex-970") == pytest.approx(1.25)

    def test_pirex_unknown_grade_returns_none(self):
        assert get_explosive_density_g_cm3("Pirex-999") is None

    def test_pirex_family_suffix_keeps_grade_values(self):
        assert get_explosive_density_g_cm3("Pirex-930 Heavy") == pytest.approx(1.20)

    def test_enaline(self):
        assert get_explosive_density_g_cm3("Enaline 1 1/4*12") == ENALINE_DENSITY_G_CM3
        assert get_explosive_density_g_cm3("Enaline") == ENALINE_DENSITY_G_CM3

    def test_empty(self):
        assert get_explosive_density_g_cm3("") is None
        assert get_explosive_density_g_cm3(None) is None

    def test_known_industrial_families(self):
        assert get_explosive_density_g_cm3("ANFO") == pytest.approx(0.80)
        assert get_explosive_density_g_cm3("Heavy ANFO") == pytest.approx(1.05)


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
        assert get_explosive_energy_mj_kg("Pirex-999") is None
        assert get_explosive_energy_mj_kg("ANFO") == pytest.approx(3.72)
        assert get_explosive_energy_mj_kg("") is None
        assert get_explosive_energy_mj_kg("Desconocido") is None


class TestExplosiveStatus:
    def test_status_values(self):
        assert get_explosive_status("ANFO") == "VALIDATED"
        assert get_explosive_status("Pirex-930") == "UNVALIDATED_REFERENCE"
        assert get_explosive_status("Pirex-930 Heavy") == "FAMILY_MATCH"
        assert get_explosive_status("Pirex-999") == "UNKNOWN"
        assert get_explosive_status("") == "MISSING"
        assert get_explosive_status(None) == "MISSING"


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
