"""Tests for the helpers extracted from procesar_pozos — Sprint 2 C4."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.calculo_tronadura import (
    _CANONICAL_COLUMN_ALIASES,
    _build_scatter_lines,
    _compute_hole_toes,
    _coerce_typed_columns,
    _resolve_column_aliases,
)


def _holes_df(**extra) -> pd.DataFrame:
    base = {
        "Latitud_Geo": [10.0, 20.0, 30.0],
        "Longitud_Geo": [100.0, 110.0, 120.0],
        "Nombre_Banco": [3110, 3110, 3100],
        "Inclinacion_real": [5.0, 10.0, 0.0],
        "Azimuth_real": [90.0, 180.0, 270.0],
        "longitud_real": [15.0, 20.0, 18.0],
    }
    base.update(extra)
    return pd.DataFrame(base)


class TestResolveColumnAliases:
    def test_required_columns_resolved(self):
        df = _holes_df()
        resolved = _resolve_column_aliases(df)
        assert resolved["X"] == "Latitud_Geo"
        assert resolved["Y"] == "Longitud_Geo"
        assert resolved["Z_collar"] == "Nombre_Banco"
        assert resolved["Incl"] == "Inclinacion_real"
        assert resolved["Az"] == "Azimuth_real"
        assert resolved["Len"] == "longitud_real"

    def test_missing_optional_returns_none(self):
        df = _holes_df()
        resolved = _resolve_column_aliases(df)
        assert resolved["Burden"] is None
        assert resolved["Esp"] is None
        assert resolved["Taco_m"] is None

    def test_alias_substitution(self):
        # Use shorter aliases instead of full names.
        df = pd.DataFrame({
            "X": [0.0], "Y": [0.0], "Z": [3110.0],
            "Inclination": [5.0], "Azimuth": [90.0], "Length": [15.0],
        })
        resolved = _resolve_column_aliases(df)
        assert resolved["X"] == "X"
        assert resolved["Incl"] == "Inclination"
        assert resolved["Len"] == "Length"


class TestCoerceTypedColumns:
    def test_numeric_coercion(self):
        df = pd.DataFrame({"X": ["1.5", "bad", "3.5"]})
        _coerce_typed_columns(df)
        assert df["X"].iloc[0] == 1.5
        assert pd.isna(df["X"].iloc[1])
        assert df["X"].iloc[2] == 3.5

    def test_int_columns_use_int64(self):
        df = pd.DataFrame({"Secuencia": [1, 2, 3]})
        _coerce_typed_columns(df)
        assert str(df["Secuencia"].dtype) == "Int64"

    def test_missing_columns_ignored(self):
        df = pd.DataFrame({"X": [1.0]})  # No Incl, no Len
        _coerce_typed_columns(df)  # Should not raise


class TestComputeHoleToes:
    def test_vertical_hole(self):
        df = pd.DataFrame({
            "X": [0.0], "Y": [0.0], "Z_collar": [3110.0],
            "Incl": [0.0], "Az": [0.0], "Len": [10.0],
        })
        _compute_hole_toes(df)
        # Vertical hole, Incl=0: dx=dy=0, dz=-Len
        assert df["X_toe"].iloc[0] == 0.0
        assert df["Y_toe"].iloc[0] == 0.0
        assert df["Z_toe"].iloc[0] == 3100.0

    def test_inclined_hole_azimuth_90(self):
        # Incl=90, Az=90: dx = L*sin(90)*sin(90) = L, dy = 0
        df = pd.DataFrame({
            "X": [0.0], "Y": [0.0], "Z_collar": [3110.0],
            "Incl": [90.0], "Az": [90.0], "Len": [10.0],
        })
        _compute_hole_toes(df)
        assert abs(df["X_toe"].iloc[0] - 10.0) < 1e-6
        assert abs(df["Y_toe"].iloc[0]) < 1e-6
        assert abs(df["Z_toe"].iloc[0] - 3110.0) < 1e-6  # cos(90)=0


class TestBuildScatterLines:
    def test_lines_have_3n_entries(self):
        df = pd.DataFrame({
            "X": [0.0, 1.0, 2.0], "Y": [0.0, 1.0, 2.0],
            "Z_collar": [100.0, 200.0, 300.0],
            "X_toe": [0.5, 1.5, 2.5], "Y_toe": [0.5, 1.5, 2.5],
            "Z_toe": [50.0, 150.0, 250.0],
        })
        x_lines, y_lines, z_lines = _build_scatter_lines(df)
        assert len(x_lines) == 9  # 3 holes × 3 points each
        assert len(y_lines) == 9
        assert len(z_lines) == 9

    def test_lines_have_none_separators(self):
        df = pd.DataFrame({
            "X": [0.0], "Y": [0.0], "Z_collar": [100.0],
            "X_toe": [0.5], "Y_toe": [0.5], "Z_toe": [50.0],
        })
        x_lines, y_lines, z_lines = _build_scatter_lines(df)
        # 1 hole → indices 0,1,2: collar, toe, None
        assert x_lines[0] == 0.0
        assert x_lines[1] == 0.5
        assert x_lines[2] is None
        assert y_lines[0] == 0.0
        assert y_lines[1] == 0.5
        assert y_lines[2] is None
        assert z_lines[0] == 100.0
        assert z_lines[1] == 50.0
        assert z_lines[2] is None


class TestCanonicalAliasesDict:
    def test_contains_required(self):
        for k in ("X", "Y", "Z_collar", "Incl", "Az", "Len"):
            assert k in _CANONICAL_COLUMN_ALIASES

    def test_contains_optional(self):
        for k in ("Burden", "Esp", "Taco_m", "Secuencia"):
            assert k in _CANONICAL_COLUMN_ALIASES
