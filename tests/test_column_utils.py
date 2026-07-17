"""Unit tests for shared blast-hole column resolution."""

import pandas as pd
import pytest

from core.column_utils import KILOS_CANDIDATES, first_present_column, kilos_column


def test_first_present_column_uses_candidate_priority_not_dataframe_order():
    df = pd.DataFrame(columns=["Carga_kg", "Kilos_Cargados_real"])
    assert first_present_column(df, ["Kilos_Cargados_real", "Carga_kg"]) == "Kilos_Cargados_real"


def test_first_present_column_returns_none_for_empty_or_missing_columns():
    assert first_present_column(pd.DataFrame(), ["Carga_kg"]) is None
    assert first_present_column(pd.DataFrame(columns=["Otro"]), []) is None


def test_first_present_column_is_case_sensitive():
    df = pd.DataFrame(columns=["carga_kg"])
    assert first_present_column(df, ["Carga_kg"]) is None


@pytest.mark.parametrize("candidate", KILOS_CANDIDATES)
def test_kilos_column_supports_each_vendor_alias(candidate):
    df = pd.DataFrame({candidate: [100.0]})
    assert kilos_column(df) == candidate


def test_kilos_column_prefers_canonical_alias_and_handles_nan_values():
    df = pd.DataFrame(
        {"Explosivo_kg": [20.0], "Kilos_Cargados_real": [float("nan")]}
    )
    assert kilos_column(df) == "Kilos_Cargados_real"


def test_kilos_column_returns_none_when_no_alias_exists():
    assert kilos_column(pd.DataFrame({"Unrelated": [1]})) is None
