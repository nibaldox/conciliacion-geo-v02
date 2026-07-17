"""
Adversarial tests for core/column_mapping.py.

Covers: exact match, fuzzy match, typos, case variations, accents,
duplicates, empty columns, missing required fields, duplicate target
assignment, type coercion, and apply_mapping error cases.
"""

import pandas as pd
import pytest
from core.column_mapping import (
    auto_map,
    validate_mapping,
    apply_mapping,
    get_field_schema,
    REQUIRED_FIELDS,
    CANONICAL_FIELDS,
    MappingResult,
)


# ─── auto_map ───────────────────────────────────────────────────────────────

class TestAutoMap:
    def test_exact_match(self):
        """Exact alias match (case-insensitive)."""
        result = auto_map(["Latitud_Geo", "Longitud_Geo", "Nombre_Banco"])
        assert result.mapping["X"] == "Latitud_Geo"
        assert result.mapping["Y"] == "Longitud_Geo"
        assert result.mapping["Z_collar"] == "Nombre_Banco"
        assert result.confidence["X"] == ("exact", 1.0)

    def test_case_insensitive(self):
        result = auto_map(["latitud_geo", "LONGITUD_GEO", "nombre_banco"])
        assert result.mapping["X"] == "latitud_geo"
        assert result.mapping["Y"] == "LONGITUD_GEO"
        assert result.confidence["X"][0] == "exact"

    def test_fuzzy_match_typos(self):
        """Minor typos should still match via fuzzy."""
        result = auto_map(["Latitud_Goe", "Longitud_Goe", "Nombr_Banco"])
        assert result.mapping["X"] == "Latitud_Goe"
        assert result.mapping["Y"] == "Longitud_Goe"
        assert result.mapping["Z_collar"] == "Nombr_Banco"
        assert result.confidence["X"][0] == "fuzzy"

    def test_english_aliases(self):
        result = auto_map(["Easting", "Northing", "Elevation", "Dip", "Heading", "Length"])
        assert result.mapping["X"] == "Easting"
        assert result.mapping["Y"] == "Northing"
        assert result.mapping["Z_collar"] == "Elevation"
        assert result.mapping["Incl"] == "Dip"
        assert result.mapping["Az"] == "Heading"
        assert result.mapping["Len"] == "Length"

    def test_extra_columns_ignored(self):
        """Columns that don't match anything are left out of the mapping."""
        result = auto_map(["Easting", "Northing", "Elevation", "Dip", "Heading", "Length", "Comentarios", "Fecha"])
        assert result.mapping["X"] == "Easting"
        # extras should not appear
        assert "Comentarios" not in result.mapping.values()

    def test_missing_required(self):
        """If a required field can't be matched, it stays None."""
        result = auto_map(["Easting", "Northing"])
        assert result.mapping["X"] == "Easting"
        assert result.mapping["Z_collar"] is None
        assert result.is_complete is False
        assert "Z_collar" in result.missing_required

    def test_all_required_matched(self):
        """Happy path: all 6 required fields matched."""
        result = auto_map(["Easting", "Northing", "Elevation", "Dip", "Heading", "Length"])
        assert result.is_complete is True
        assert result.missing_required == []

    def test_no_collision(self):
        """Two canonical fields should not claim the same source column."""
        # 'X' and 'X_collar' are both aliases; if source has only 'X',
        # only one canonical field should claim it.
        result = auto_map(["X", "Y", "Z", "Dip", "Heading", "Length"])
        claimed = [v for v in result.mapping.values() if v is not None]
        # No duplicates
        assert len(claimed) == len(set(claimed))

    def test_empty_input(self):
        result = auto_map([])
        assert all(v is None for v in result.mapping.values())
        assert result.is_complete is False

    def test_normalize_accents_and_spaces(self):
        """Column names with accents / extra spaces should normalize."""
        result = auto_map(["  Latitud_Geo  ", "Longitúd_Geo"])
        # accent on "Longitúd" won't exact-match but should fuzzy-match
        assert result.mapping["X"] == "  Latitud_Geo  "

    def test_unit_suffix_in_name(self):
        """Column names with units like 'Este (m)' should still match."""
        result = auto_map(["Este (m)", "Norte (m)", "Banco", "Inclinacion", "Azimut", "Longitud (m)"])
        assert result.mapping["X"] == "Este (m)"
        assert result.mapping["Y"] == "Norte (m)"

    def test_optional_fields_auto_matched(self):
        result = auto_map(["Easting", "Northing", "Elevation", "Dip", "Heading", "Length", "Burden", "Spacing"])
        assert result.mapping["Burden"] == "Burden"
        assert result.mapping["Esp"] == "Spacing"


# ─── validate_mapping ──────────────────────────────────────────────────────

class TestValidateMapping:
    def test_valid_complete_mapping(self):
        mapping: dict[str, str | None] = {
            "X": "Easting", "Y": "Northing", "Z_collar": "Elevation",
            "Incl": "Dip", "Az": "Heading", "Len": "Length",
        }
        errors = validate_mapping(mapping)
        assert errors == []

    def test_missing_required(self):
        mapping: dict[str, str | None] = {"X": "Easting", "Y": "Northing"}
        errors = validate_mapping(mapping)
        assert any("requeridos" in e for e in errors)

    def test_duplicate_target(self):
        mapping: dict[str, str | None] = {
            "X": "Easting", "Y": "Easting",  # same source for two fields
            "Z_collar": "Elevation", "Incl": "Dip", "Az": "Heading", "Len": "Length",
        }
        errors = validate_mapping(mapping)
        assert any("dos campos" in e for e in errors)

    def test_none_values_allowed_for_optional(self):
        mapping: dict[str, str | None] = {
            "X": "Easting", "Y": "Northing", "Z_collar": "Elevation",
            "Incl": "Dip", "Az": "Heading", "Len": "Length",
            "Burden": None, "Esp": None,
        }
        errors = validate_mapping(mapping)
        assert errors == []


# ─── apply_mapping ─────────────────────────────────────────────────────────

class TestApplyMapping:
    def _make_df(self):
        return pd.DataFrame({
            "Easting": [100.0, 200.0, 300.0],
            "Northing": [50.0, 60.0, 70.0],
            "Elevation": [1000.0, 1010.0, 1020.0],
            "Dip": [5.0, 10.0, 15.0],
            "Heading": [45.0, 90.0, 135.0],
            "Length": [10.0, 12.0, 14.0],
            "Extra": ["a", "b", "c"],
        })

    def test_basic_apply(self):
        df = self._make_df()
        mapping: dict[str, str | None] = {
            "X": "Easting", "Y": "Northing", "Z_collar": "Elevation",
            "Incl": "Dip", "Az": "Heading", "Len": "Length",
        }
        result = apply_mapping(df, mapping)
        assert "X" in result.columns
        assert "Y" in result.columns
        assert len(result) == 3

    def test_drops_nan_required(self):
        df = pd.DataFrame({
            "Easting": [100.0, None, 300.0],
            "Northing": [50.0, 60.0, 70.0],
            "Elevation": [1000.0, 1010.0, 1020.0],
            "Dip": [5.0, 10.0, 15.0],
            "Heading": [45.0, 90.0, 135.0],
            "Length": [10.0, 12.0, 14.0],
        })
        mapping: dict[str, str | None] = {
            "X": "Easting", "Y": "Northing", "Z_collar": "Elevation",
            "Incl": "Dip", "Az": "Heading", "Len": "Length",
        }
        result = apply_mapping(df, mapping)
        assert len(result) == 2  # the NaN row dropped

    def test_type_coercion_float(self):
        df = pd.DataFrame({
            "Easting": ["100.0", "200.0", "300.0"],  # strings
            "Northing": [50.0, 60.0, 70.0],
            "Elevation": [1000.0, 1010.0, 1020.0],
            "Dip": [5.0, 10.0, 15.0],
            "Heading": [45.0, 90.0, 135.0],
            "Length": [10.0, 12.0, 14.0],
        })
        mapping: dict[str, str | None] = {
            "X": "Easting", "Y": "Northing", "Z_collar": "Elevation",
            "Incl": "Dip", "Az": "Heading", "Len": "Length",
        }
        result = apply_mapping(df, mapping)
        assert result["X"].dtype.kind in "fc"  # float or complex

    def test_invalid_mapping_raises(self):
        df = self._make_df()
        mapping: dict[str, str | None] = {"X": "Easting"}  # missing required
        with pytest.raises(ValueError):
            apply_mapping(df, mapping)

    def test_preserves_extra_columns(self):
        df = self._make_df()
        mapping: dict[str, str | None] = {
            "X": "Easting", "Y": "Northing", "Z_collar": "Elevation",
            "Incl": "Dip", "Az": "Heading", "Len": "Length",
        }
        result = apply_mapping(df, mapping)
        assert "Extra" in result.columns  # extra col not in mapping, preserved


# ─── get_field_schema ──────────────────────────────────────────────────────

class TestGetFieldSchema:
    def test_returns_list_of_dicts(self):
        schema = get_field_schema()
        assert isinstance(schema, list)
        assert len(schema) == len(CANONICAL_FIELDS)
        first = schema[0]
        assert "name" in first
        assert "required" in first
        assert "aliases" in first

    def test_has_six_required(self):
        schema = get_field_schema()
        required = [s["name"] for s in schema if s["required"]]
        assert len(required) == 6


# ─── Edge cases / adversarial ──────────────────────────────────────────────

class TestAdversarial:
    def test_whitespace_only_columns(self):
        """Columns that are just whitespace should not match anything."""
        result = auto_map(["   ", "\t", "\n"])
        assert all(v is None for v in result.mapping.values())

    def test_numeric_column_names(self):
        """Column names that are numbers (e.g. from header-less CSV)."""
        result = auto_map(["1", "2", "3", "4", "5", "6"])
        # Should not crash, all should be None
        assert result.is_complete is False

    def test_duplicate_source_columns(self):
        """If the CSV has duplicate column names, dedupe gracefully."""
        result = auto_map(["Easting", "Easting", "Northing"])
        # Should not crash, should dedupe internally
        assert result.mapping["X"] == "Easting"

    def test_very_long_column_name(self):
        long_name = "Easting_" * 50
        result = auto_map([long_name])
        assert result.mapping["X"] is None  # no match, but no crash

    def test_all_none_mapping(self):
        """A completely empty mapping should fail validation."""
        errors = validate_mapping({})
        assert len(errors) > 0

    def test_apply_with_nonexistent_source(self):
        """Mapping references a column that doesn't exist in the DataFrame."""
        df = pd.DataFrame({"A": [1, 2]})
        mapping: dict[str, str | None] = {
            "X": "NotExist", "Y": "Northing", "Z_collar": "Elevation",
            "Incl": "Dip", "Az": "Heading", "Len": "Length",
        }
        # validate should pass (structure is OK) but apply should still work
        # because apply only renames columns that exist
        errors = validate_mapping(mapping)
        # It's structurally valid (no missing required, no dups)
        assert errors == []
        # apply should rename what it can
        result = apply_mapping(df, mapping)
        assert "X" not in result.columns  # source didn't exist

    def test_unicode_column_names(self):
        """Column names with unicode characters."""
        result = auto_map(["Cota_Collar", "Azimut", "Inclinación"])
        assert result.mapping["Z_collar"] == "Cota_Collar"
        assert result.mapping["Az"] == "Azimut"

    def test_mixed_case_aliases(self):
        """Aliases in various cases."""
        result = auto_map(["EASTING", "NORTHING", "eLeVaTiOn"])
        assert result.mapping["X"] == "EASTING"
        assert result.mapping["Z_collar"] == "eLeVaTiOn"
