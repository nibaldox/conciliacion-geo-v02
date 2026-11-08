import pytest

from core.config import EXPLOSIVE
from core.explosive_properties import (
    get_explosive_density_g_cm3,
    get_explosive_energy_mj_kg,
    get_explosive_status,
    resolve_explosive,
)


@pytest.mark.parametrize("name,product", [
    ("Pirex-930", "Pirex-930"),
    ("Pirex-920", "Pirex-920"),
    ("Pirex-950", "Pirex-950"),
    ("PIREX 50", None),
    ("Enaline 1 1/4 12", "Enaline"),
    ("Pirex-970", "Pirex-970"),
    ("Enaline 1 1/4*12", "Enaline"),
    ("pirex-920", "Pirex-920"),
])
def test_real_names_and_case_separator_variants(name, product):
    for candidate in (name, "  " + name.swapcase().replace("-", "__") + "  "):
        result = resolve_explosive(candidate)
        if product is None:
            assert result is None
            assert get_explosive_status(candidate) == "UNKNOWN"
            assert EXPLOSIVE.energy_mj_per_kg(candidate) is None
        else:
            assert result is not None
            assert result.normalized_name == product
            assert result.is_exact
            assert result.validation_status == "UNVALIDATED_REFERENCE"
            assert result.source
            assert EXPLOSIVE.energy_mj_per_kg(candidate) == result.energy_mj_kg
            assert EXPLOSIVE.density_g_per_cm3(candidate) == result.density_g_cm3


@pytest.mark.parametrize("name", ["NOT ANFO", "Emuline 8000", "Pirex-930 Heavy", "ANFO EXTRA", "NON-ANFO"])
def test_unlisted_names_do_not_provide_properties(name):
    assert resolve_explosive(name) is None
    assert get_explosive_status(name) == "UNKNOWN"
    assert get_explosive_energy_mj_kg(name) is None
    assert get_explosive_density_g_cm3(name) is None
    assert EXPLOSIVE.energy_mj_per_kg(name) is None
    assert EXPLOSIVE.density_g_per_cm3(name) is None


@pytest.mark.parametrize("name", [None, "", "   ", float("nan")])
def test_missing_names(name):
    assert resolve_explosive(name) is None
    assert get_explosive_status(name) == "MISSING"
    assert EXPLOSIVE.energy_mj_per_kg(name) is None


def test_explicit_alias_resolves_exactly():
    result = resolve_explosive(" h__anfo ")
    assert result is not None
    assert result.normalized_name == "Heavy ANFO"
    assert result.is_exact
    assert result.validation_status == "UNVALIDATED_REFERENCE"
    assert EXPLOSIVE.energy_mj_per_kg("h-anfo") == pytest.approx(3.4)
