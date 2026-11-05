"""
Integration tests: column_mapping + calculo_tronadura end-to-end.

Tests the full flow: unknown CSV schema → auto_map → user override →
apply_mapping → procesar_pozos → 3D coordinates out.
"""

import numpy as np
import pandas as pd
import pytest
from core.column_mapping import auto_map, apply_mapping, validate_mapping
from core.calculo_tronadura import procesar_pozos


class TestEndToEndColumnMapping:
    """Full pipeline: CSV with unknown schema → mapped → processed."""

    def _make_unknown_schema_csv(self, n: int = 10) -> pd.DataFrame:
        """Simulate a CSV with English column names that the legacy
        alias detector would NOT recognize."""
        rng = np.random.default_rng(42)
        return pd.DataFrame({
            "Hole_ID": [f"H{i:04d}" for i in range(n)],
            "Easting_m": rng.uniform(92000, 92100, n),
            "Northing_m": rng.uniform(22000, 22100, n),
            "Collar_Elev": rng.uniform(3100, 3150, n),
            "Dip_deg": rng.uniform(0, 15, n),
            "Heading_deg": rng.uniform(0, 360, n),
            "Drill_Length_m": rng.uniform(10, 20, n),
            "Explosive": ["ANFO"] * n,
            "Diameter_mm": [250.0] * n,
            "Stemming_m": rng.uniform(3, 6, n),
        })

    def test_auto_map_english_schema(self):
        """auto_map should detect all 6 required fields from English column names."""
        df = self._make_unknown_schema_csv()
        result = auto_map(df.columns)
        assert result.is_complete, f"Missing: {result.missing_required}"
        assert result.mapping["X"] == "Easting_m"
        assert result.mapping["Y"] == "Northing_m"
        assert result.mapping["Z_collar"] == "Collar_Elev"
        assert result.mapping["Incl"] == "Dip_deg"
        assert result.mapping["Az"] == "Heading_deg"
        assert result.mapping["Len"] == "Drill_Length_m"

    def test_full_pipeline_with_mapping(self):
        """End-to-end: unknown CSV → auto_map → procesar_pozos → 3D coords."""
        df = self._make_unknown_schema_csv()
        result = auto_map(df.columns)
        assert result.is_complete

        # procesar_pozos with explicit column_map
        df_proc, x_lines, y_lines, z_lines = procesar_pozos(df, column_map=result.mapping, incl_convention="from_vertical", geometry_user_confirmed=True)

        # Verify output shapes
        assert len(df_proc) == 10
        assert "X" in df_proc.columns
        assert "Z_collar" in df_proc.columns
        assert "Z_toe" in df_proc.columns
        # Scatter lines: 10 holes × 3 values (collar, toe, None) = 30
        assert len(x_lines) == 30

    def test_legacy_pipeline_still_works(self):
        """Without column_map, the legacy alias detection should still work."""
        df = pd.DataFrame({
            "Latitud_Geo": [92000.0, 92010.0],
            "Longitud_Geo": [22000.0, 22010.0],
            "Nombre_Banco": [3100.0, 3110.0],
            "Inclinacion_real": [5.0, 10.0],
            "Azimuth_real": [45.0, 90.0],
            "longitud_real": [15.0, 17.0],
        })
        df_proc, _, _, _ = procesar_pozos(df, incl_convention="from_vertical", geometry_user_confirmed=True)  # no column_map
        assert len(df_proc) == 2

    def test_user_override_mapping(self):
        """User manually overrides the auto-detected mapping."""
        df = self._make_unknown_schema_csv(5)
        result = auto_map(df.columns)
        # Swap X and Y (user intentional override)
        mapping = dict(result.mapping)
        mapping["X"], mapping["Y"] = mapping["Y"], mapping["X"]
        errors = validate_mapping(mapping)
        assert errors == []
        df_proc, _, _, _ = procesar_pozos(df, column_map=mapping, incl_convention="from_vertical", geometry_user_confirmed=True)
        assert len(df_proc) == 5

    def test_partial_mapping_fails_gracefully(self):
        """Missing required field → ValueError from apply_mapping."""
        df = self._make_unknown_schema_csv(5)
        mapping = {"X": "Easting_m", "Y": "Northing_m"}  # missing 4 required
        with pytest.raises(ValueError, match="requeridos"):
            procesar_pozos(df, column_map=mapping, incl_convention="from_vertical", geometry_user_confirmed=True)

    def test_extra_unmapped_columns_preserved(self):
        """Columns not in the mapping should be preserved through the pipeline."""
        df = self._make_unknown_schema_csv(5)
        result = auto_map(df.columns)
        df_proc, _, _, _ = procesar_pozos(df, column_map=result.mapping, incl_convention="from_vertical", geometry_user_confirmed=True)
        # "Explosive" gets renamed to "Tipo_Explosivo" by the mapper
        # (it's an alias). The key point is the data is preserved.
        assert "Tipo_Explosivo" in df_proc.columns
        assert "Hole_ID" in df_proc.columns

    def test_confirmed_mapping_wins_alias_collision_and_keeps_bench_semantics(self):
        df = pd.DataFrame({
            "X": [999.0],
            "Easting_m": [100.0],
            "Northing_m": [200.0],
            "Nombre_Banco": [300.0],
            "Dip_deg": [5.0],
            "Heading_deg": [90.0],
            "Drill_Length_m": [10.0],
        })
        mapping = {
            "X": "Easting_m", "Y": "Northing_m", "Z_collar": "Nombre_Banco",
            "Incl": "Dip_deg", "Az": "Heading_deg", "Len": "Drill_Length_m",
        }

        result = procesar_pozos(
            df, column_map=mapping, preserve_invalid_mapped_rows=True,
            incl_convention="from_vertical", geometry_user_confirmed=True,
            return_result=True,
        )

        assert result.accepted_dataframe.iloc[0]["X"] == 100.0
        assert result.accepted_dataframe.iloc[0]["Z_collar"] == 300.0
        assert result.accepted_dataframe.iloc[0]["Z_collar_semantic"] == "bench_elevation_untransformed"

    def test_mapping_preserves_invalid_rows_and_design_surface_replaces_missing_z(self):
        from core.design_surface_sampling import DesignSurfaceSample

        df = pd.DataFrame({
            "East": [100.0, 101.0], "North": [200.0, 201.0],
            "Dip": [5.0, 5.0], "Heading": [90.0, 90.0],
            "DrillLength": [10.0, None], "__design_surface_z_pending": [0.0, 0.0],
        })
        mapping = {
            "X": "East", "Y": "North", "Z_collar": "__design_surface_z_pending",
            "Incl": "Dip", "Az": "Heading", "Len": "DrillLength",
        }

        result = procesar_pozos(
            df, column_map=mapping, preserve_invalid_mapped_rows=True,
            incl_convention="from_vertical", geometry_user_confirmed=True,
            design_surface_samples=(
                DesignSurfaceSample("sampled", 305.0, "test", ""),
                DesignSurfaceSample("outside", None, "test", "outside"),
            ),
            design_surface_mesh_id="mesh", design_surface_sha256="sha",
            return_result=True,
        )

        assert len(result.accepted_dataframe) == 1
        assert result.accepted_dataframe.iloc[0]["Z_collar"] == 305.0
        assert result.accepted_dataframe.iloc[0]["Z_collar_semantic"] == "design_surface_estimate"
        assert len(result.rejected_rows) == 2
        assert {row["source_column"] for row in result.rejected_rows} == {"superficie_diseno", "DrillLength"}

    def test_completely_alien_schema(self):
        """CSV with zero recognizable columns → auto_map returns all None."""
        df = pd.DataFrame({
            "foo": [1, 2], "bar": [3, 4], "qux": [5, 6],
        })
        result = auto_map(df.columns)
        assert not result.is_complete
        # "qux" should not match anything (it's alien)
        assert len(result.missing_required) >= 5

    def test_mixed_language_schema(self):
        """Some Spanish, some English columns."""
        df = pd.DataFrame({
            "Latitud_Geo": [92000.0],
            "Northing": [22000.0],
            "Cota_Collar": [3100.0],
            "Dip": [5.0],
            "Azimuth_real": [45.0],
            "Length": [15.0],
        })
        result = auto_map(df.columns)
        assert result.is_complete
        assert result.mapping["X"] == "Latitud_Geo"
        assert result.mapping["Y"] == "Northing"

    def test_fuzzy_typo_in_field_name(self):
        """Column name with a typo close to an alias."""
        df = pd.DataFrame({
            "Latitud_Goe": [92000.0],
            "Longitud_Goe": [22000.0],
            "Nombr_Banco": [3100.0],
            "Inclinacio_real": [5.0],  # missing 'n'
            "Azimut": [45.0],
            "longitd_real": [15.0],  # missing 'u'
        })
        result = auto_map(df.columns)
        # Fuzzy matching should catch most of these
        assert result.mapping["Az"] == "Azimut"
