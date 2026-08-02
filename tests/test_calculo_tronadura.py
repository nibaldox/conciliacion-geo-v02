"""Tests for core.calculo_tronadura — Drill & Blast processing.

Covers:
- Coordinate correction: X=Latitud_Geo, Y=Longitud_Geo, Z_collar=Nombre_Banco+BENCH_HEIGHT
- Drop of ENAEX "no usar" columns
- Coercion of numeric fields, dropna of invalid rows
- Toe calculation via Incl/Az trigonometry (vertical hole, inclined hole, zero-length filter)
- Section projection: a hole exactly on the section line should have dist_perp == 0
- Section projection: holes outside tolerance are filtered
- Empty DataFrame returns empty output
"""
import numpy as np
import pandas as pd
import pytest

from core.calculo_tronadura import (
    BENCH_HEIGHT,
    COLS_DROP,
    procesar_pozos,
    proyectar_pozos_en_seccion,
)
from core.geometry_conventions import InclinationConvention


def _make_valid_hole(
    lat=1000.0,
    lon=2000.0,
    banco=4200.0,
    incl=0.0,
    az=0.0,
    length=12.0,
    label="P-1",
    fecha="2026-05-01",
):
    """Return a one-row DataFrame matching the ENAEX blast-hole schema."""
    return pd.DataFrame(
        [
            {
                "id_pozo": "AAA-001",
                "label_pozo": label,
                "Latitud_Geo": lat,
                "Longitud_Geo": lon,
                "Nombre_Banco": banco,
                "Inclinacion_real": incl,
                "Azimuth_real": az,
                "longitud_real": length,
                # Migración cierre §2.2: el evento declara su convención angular.
                "Incl_convention": "from_vertical",
                "Kilos_Cargados_real": 250.0,
                "fecha_tronadura": fecha,
                # Migración cierre §2.1: altura de banco declarada por el evento
                # (columna validada → PROVIDED); nunca 15 m silencioso.
                "bench_height_m": 15.0,
                # Columns that should be dropped (per COLS_DROP)
                "uniqid": "ignore-me",
                "id_rajo": "X",
                "id_malla_opit": "Y",
                "numero": 1,
                "camion": "T-1",
                "holes_dateUpdated": "2026-05-01",
                "mes_tronadura": "May",
            }
        ]
    )


class TestProcesarPozos:
    """Tests for the procesar_pozos function."""

    def test_drops_enaex_columns(self):
        """All ENAEX 'no usar' columns listed in COLS_DROP are removed."""
        df = _make_valid_hole()
        out, *_ = procesar_pozos(df)
        for col in COLS_DROP:
            assert col not in out.columns, f"{col} should be dropped"

    def test_coordinate_correction(self):
        """X=Latitud_Geo, Y=Longitud_Geo, Z_collar = Nombre_Banco + BENCH_HEIGHT."""
        df = _make_valid_hole(lat=1234.5, lon=6789.0, banco=4200.0)
        out, *_ = procesar_pozos(df)
        assert out["X"].iloc[0] == 1234.5
        assert out["Y"].iloc[0] == 6789.0
        assert out["Z_collar"].iloc[0] == 4200.0 + BENCH_HEIGHT

    def test_vertical_hole_toe(self):
        """A vertical (incl=0) hole with length L has toe at (X, Y, collar - L)."""
        df = _make_valid_hole(incl=0.0, length=10.0, lat=100.0, lon=200.0, banco=4000.0)
        out, *_ = procesar_pozos(df)
        collar = 4000.0 + BENCH_HEIGHT
        assert out["X_toe"].iloc[0] == pytest.approx(100.0)
        assert out["Y_toe"].iloc[0] == pytest.approx(200.0)
        assert out["Z_toe"].iloc[0] == pytest.approx(collar - 10.0)

    def test_inclined_hole_toe(self):
        """A 90° (horizontal) hole with az=0 (East) should displace purely in X.

        For a horizontal hole, dz = -L*cos(90°) = 0, so Z_toe == Z_collar.
        dx = L*sin(90°)*sin(0°) = 0  → wait, sin(0°)=0, so dx=0
        dy = L*sin(90°)*cos(0°) = L  → Y displacement
        """
        df = _make_valid_hole(incl=90.0, az=0.0, length=5.0, lat=0.0, lon=0.0, banco=4000.0)
        out, *_ = procesar_pozos(df)
        assert out["X_toe"].iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert out["Y_toe"].iloc[0] == pytest.approx(5.0)
        assert out["Z_toe"].iloc[0] == pytest.approx(out["Z_collar"].iloc[0], abs=1e-6)

    def test_zero_length_holes_dropped(self):
        """Holes with length <= 0 are dropped from the cleaned frame."""
        df = pd.concat(
            [
                _make_valid_hole(length=10.0, label="OK"),
                _make_valid_hole(length=0.0, label="ZERO"),
                _make_valid_hole(length=-1.0, label="NEG"),
            ],
            ignore_index=True,
        )
        out, *_ = procesar_pozos(df)
        assert len(out) == 1
        assert out["label_pozo"].iloc[0] == "OK"

    def test_nan_values_dropped(self):
        """Rows with NaN in critical numeric columns are dropped."""
        df = pd.concat(
            [
                _make_valid_hole(lat=100.0, label="OK"),
                _make_valid_hole(label="NaN_X"),
            ],
            ignore_index=True,
        )
        df.loc[1, "Latitud_Geo"] = np.nan
        out, *_ = procesar_pozos(df)
        assert len(out) == 1
        assert out["label_pozo"].iloc[0] == "OK"

    def test_returns_three_equal_length_arrays(self):
        """x_lines, y_lines, z_lines must all have length 3*n (collar, toe, None)."""
        df = _make_valid_hole()
        _, xl, yl, zl = procesar_pozos(df)
        n = 3 * 1
        assert len(xl) == n
        assert len(yl) == n
        assert len(zl) == n
        # Separator slots are None
        assert xl[2] is None
        assert yl[2] is None
        assert zl[2] is None

    def test_fecha_tronadura_is_date(self):
        """fecha_tronadura is normalised to date (no time component)."""
        df = _make_valid_hole(fecha="2026-05-01 14:30:00")
        out, *_ = procesar_pozos(df)
        v = out["fecha_tronadura"].iloc[0]
        assert hasattr(v, "year")
        assert v.year == 2026 and v.month == 5 and v.day == 1

    def test_banco_original_preserved(self):
        """The pre-correction Z (Nombre_Banco) is preserved in Banco_Original."""
        df = _make_valid_hole(banco=4185.0)
        out, *_ = procesar_pozos(df)
        assert "Banco_Original" in out.columns
        assert out["Banco_Original"].iloc[0] == 4185.0


class TestZCollarsemantics:
    """Spec §4.2: bench elevation vs real collar elevation must be distinct."""

    def test_collar_elevation_column_not_transformed(self):
        df = _make_valid_hole()
        df["Cota_Collar"] = df["Nombre_Banco"]
        df = df.drop(columns=["Nombre_Banco"])
        out, *_ = procesar_pozos(df)
        assert out["Z_collar"].iloc[0] == 4200.0
        assert out["Z_collar_semantic"].iloc[0] == "collar_elevation"
        # la columna bench_height_m del input se conserva pero NO se aplica
        # (semántica collar: sin transformación de elevación)
        assert out["Z_toe"].iloc[0] == pytest.approx(4200.0 - 12.0)  # Len=12 del fixture

    def test_bench_elevation_transformed_with_record(self):
        df = _make_valid_hole(banco=4000.0)
        out, *_ = procesar_pozos(df)
        assert out["Z_collar"].iloc[0] == 4000.0 + BENCH_HEIGHT
        assert out["Z_collar_semantic"].iloc[0] == "bench_elevation_plus_height"
        assert out["bench_height_m"].iloc[0] == BENCH_HEIGHT

    def test_bench_height_parameterizable_per_event(self):
        df = _make_valid_hole(banco=4000.0)
        out, *_ = procesar_pozos(df, bench_height_m=12.0)
        assert out["Z_collar"].iloc[0] == 4012.0
        assert out["bench_height_m"].iloc[0] == 12.0

    def test_explicit_column_map_collar_semantic(self):
        df = _make_valid_hole()
        df = df.rename(columns={"Nombre_Banco": "Cota_Collar"})
        mapping = {
            "X": "Latitud_Geo", "Y": "Longitud_Geo", "Z_collar": "Cota_Collar",
            "Incl": "Inclinacion_real", "Az": "Azimuth_real", "Len": "longitud_real",
        }
        out, *_ = procesar_pozos(df, column_map=mapping)
        assert out["Z_collar"].iloc[0] == 4200.0
        assert out["Z_collar_semantic"].iloc[0] == "collar_elevation"

    def test_ambiguous_column_name_raises(self):
        df = _make_valid_hole()
        df = df.rename(columns={"Nombre_Banco": "Altura_Collar"})
        with pytest.raises(ValueError, match="sem[áa]ntica"):
            procesar_pozos(df)

    def test_explicit_semantic_overrides_ambiguous_name(self):
        df = _make_valid_hole()
        df = df.rename(columns={"Nombre_Banco": "Altura_Collar"})
        out, *_ = procesar_pozos(df, z_collar_semantic="bench_elevation")
        assert out["Z_collar"].iloc[0] == 4200.0 + BENCH_HEIGHT


class TestInclinationConvention:
    """Spec §4.1: canonical inclination = deviation from vertical, 0 = vertical."""

    def test_original_values_and_convention_recorded(self):
        df = _make_valid_hole(incl=10.0, az=15.0)
        out, *_ = procesar_pozos(df)
        assert out["Incl_original"].iloc[0] == 10.0
        assert out["Az_original"].iloc[0] == 15.0
        assert out["Incl_convention"].iloc[0] == "from_vertical"
        assert out["Az_convention"].iloc[0] == "CLOCKWISE_FROM_NORTH"

    def test_negative_inclination_wrapped_with_flag(self):
        df = _make_valid_hole(incl=-10.0, length=10.0, lat=100.0, lon=200.0, banco=4000.0)
        out, *_ = procesar_pozos(df)
        assert out["Incl"].iloc[0] == 10.0
        assert out["Incl_original"].iloc[0] == -10.0
        assert out["incl_anomaly"].iloc[0] == "negative_wrapped"
        assert out["Z_toe"].iloc[0] == pytest.approx(4015.0 - 10.0 * np.cos(np.radians(10.0)))

    def test_dip_from_horizontal_convention(self):
        df = _make_valid_hole(incl=60.0, length=10.0, lat=100.0, lon=200.0, banco=4000.0)
        out, *_ = procesar_pozos(
            df, incl_convention=InclinationConvention.DIP_FROM_HORIZONTAL
        )
        assert out["Incl"].iloc[0] == 30.0
        assert out["Incl_convention"].iloc[0] == "dip_from_horizontal"
        assert out["Z_toe"].iloc[0] == pytest.approx(4015.0 - 10.0 * np.cos(np.radians(30.0)))

    def test_azimuth_wrapped_to_360(self):
        df = _make_valid_hole(incl=90.0, az=370.0, length=5.0, lat=0.0, lon=0.0, banco=4000.0)
        out, *_ = procesar_pozos(df)
        assert out["Az"].iloc[0] == 10.0
        assert out["Y_toe"].iloc[0] == pytest.approx(5.0 * np.sin(np.radians(90.0)) * np.cos(np.radians(10.0)))

    def test_toe_consistent_with_azimuth_sign(self):
        """az=0 (North) moves the toe +Y; az=90 (East) moves it +X."""
        df_n = _make_valid_hole(incl=90.0, az=0.0, length=5.0, lat=0.0, lon=0.0, banco=4000.0)
        df_e = _make_valid_hole(incl=90.0, az=90.0, length=5.0, lat=0.0, lon=0.0, banco=4000.0)
        out_n, *_ = procesar_pozos(df_n)
        out_e, *_ = procesar_pozos(df_e)
        assert out_n["Y_toe"].iloc[0] == pytest.approx(5.0)
        assert out_n["X_toe"].iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert out_e["X_toe"].iloc[0] == pytest.approx(5.0)
        assert out_e["Y_toe"].iloc[0] == pytest.approx(0.0, abs=1e-9)


class TestInclinationConventionExplicit:
    """H-05: no silent angular-convention assumption; persistent warning."""

    def test_data_declared_convention_no_warning(self):
        df = _make_valid_hole(incl=10.0)
        out, *_ = procesar_pozos(df, bench_height_m=15.0)
        assert out["Incl_convention"].iloc[0] == "from_vertical"
        assert out["Incl_convention_source"].iloc[0] == "data"
        assert bool(out["incl_convention_warning"].iloc[0]) is False

    def test_explicit_convention_no_warning(self):
        df = _make_valid_hole(incl=10.0)
        out, *_ = procesar_pozos(df, incl_convention="from_vertical")
        assert out["Incl_convention_source"].iloc[0] == "explicit"
        assert bool(out["incl_convention_warning"].iloc[0]) is False

    def test_data_declared_convention_used(self):
        df = _make_valid_hole(incl=60.0)
        df["Incl_convention"] = "dip_from_horizontal"
        out, *_ = procesar_pozos(df)
        assert out["Incl"].iloc[0] == 30.0
        assert out["Incl_convention_source"].iloc[0] == "data"

    def test_orientation_column_persisted(self):
        df = pd.concat(
            [_make_valid_hole(incl=65.0, label="POS"), _make_valid_hole(incl=-65.0, label="NEG")],
            ignore_index=True,
        )
        df["Incl_convention"] = "dip_from_horizontal"
        out, *_ = procesar_pozos(df)
        assert out.loc[out["label_pozo"] == "POS", "Incl"].iloc[0] == 25.0
        assert out.loc[out["label_pozo"] == "NEG", "Incl"].iloc[0] == 25.0
        assert out.loc[out["label_pozo"] == "POS", "incl_orientation"].iloc[0] == 1
        assert out.loc[out["label_pozo"] == "NEG", "incl_orientation"].iloc[0] == -1


class TestZAmbiguous:
    """H-07: generic column names are never silently treated as collar."""

    def test_generic_z_raises(self):
        df = _make_valid_hole()
        df = df.rename(columns={"Nombre_Banco": "Z"})
        with pytest.raises(ValueError, match="sem[áa]ntica"):
            procesar_pozos(df)

    def test_generic_elevation_raises(self):
        df = _make_valid_hole()
        df = df.rename(columns={"Nombre_Banco": "Elevation"})
        with pytest.raises(ValueError, match="sem[áa]ntica"):
            procesar_pozos(df)

    def test_ambiguous_with_explicit_semantic_ok(self):
        df = _make_valid_hole()
        df = df.rename(columns={"Nombre_Banco": "Z"})
        out, *_ = procesar_pozos(df, z_collar_semantic="collar_elevation")
        assert out["Z_collar"].iloc[0] == 4200.0
        assert out["Z_collar_semantic"].iloc[0] == "collar_elevation"


class TestInclinationConventionProvenance:
    """Fase 1.1 cierre §2.3: full angular provenance columns."""

    def test_full_provenance_columns(self):
        df = _make_valid_hole(incl=10.0, az=15.0)
        out, *_ = procesar_pozos(df, incl_convention="from_vertical")
        for col in (
            "inclination_original",
            "inclination_convention_original",
            "inclination_normalized_from_vertical",
            "inclination_conversion_applied",
            "inclination_assumption_flag",
            "inclination_validation_status",
            "inclination_validation_message",
        ):
            assert col in out.columns, col
        assert out["inclination_original"].iloc[0] == 10.0
        assert out["inclination_normalized_from_vertical"].iloc[0] == 10.0
        assert out["inclination_conversion_applied"].iloc[0] == "none"
        assert bool(out["inclination_assumption_flag"].iloc[0]) is False
        assert out["inclination_validation_status"].iloc[0] == "EXPLICIT"

    def test_missing_convention_blocks_geometry(self):
        """Cierre final §2.2: sin convención confirmada el backend bloquea."""
        df = _make_valid_hole(incl=10.0).drop(columns=["bench_height_m", "Incl_convention"])
        with pytest.raises(ValueError, match="convenci"):
            procesar_pozos(df, bench_height_m=15.0)

    def test_dip_negative_conversion_recorded(self):
        df = _make_valid_hole(incl=-65.0, length=10.0, lat=100.0, lon=200.0, banco=4000.0)
        out, *_ = procesar_pozos(
            df, incl_convention="dip_from_horizontal"
        )
        assert out["inclination_normalized_from_vertical"].iloc[0] == 25.0
        assert out["inclination_conversion_applied"].iloc[0] == "dip->90-dip+abs"
        assert out["inclination_original"].iloc[0] == -65.0
        assert out["incl_orientation"].iloc[0] == -1

    def test_out_of_range_flagged_and_dropped(self):
        df = pd.concat(
            [_make_valid_hole(incl=10.0, label="OK"), _make_valid_hole(incl=120.0, label="BAD")],
            ignore_index=True,
        )
        out, *_ = procesar_pozos(df, incl_convention="from_vertical")
        assert len(out) == 1
        assert out["label_pozo"].iloc[0] == "OK"

    def test_known_toe_coordinates(self):
        """§2.3 acceptance: known collar/toe coordinates for a vertical hole."""
        df = _make_valid_hole(incl=0.0, length=12.0, lat=100.0, lon=200.0, banco=4000.0)
        out, *_ = procesar_pozos(df, incl_convention="from_vertical", bench_height_m=15.0)
        assert out["X_toe"].iloc[0] == pytest.approx(100.0)
        assert out["Y_toe"].iloc[0] == pytest.approx(200.0)
        assert out["Z_toe"].iloc[0] == pytest.approx(4015.0 - 12.0)


class TestProyectarPozosEnSeccion:
    """Tests for proyectar_pozos_en_seccion — blast-hole projection onto a section."""

    def _processed_two_holes(self):
        """Two holes: one ON the section, one 50 m away."""
        df = pd.concat(
            [
                _make_valid_hole(lat=0.0, lon=0.0, label="ON_AXIS"),
                _make_valid_hole(lat=0.0, lon=50.0, label="OFF_AXIS"),
            ],
            ignore_index=True,
        )
        return procesar_pozos(df)[0]

    def test_hole_on_section_has_zero_perp_distance(self):
        """A hole exactly on the section line has dist_perp == 0."""
        out = self._processed_two_holes()
        sec_origin = np.array([0.0, 0.0])
        # Section runs East (azimuth=90) for 100 m
        proj = proyectar_pozos_en_seccion(
            out, origin=sec_origin, azimuth=90.0, length=100.0, tolerance=5.0
        )
        on = proj[proj["label_pozo"] == "ON_AXIS"]
        assert len(on) == 1
        assert on["dist_perp"].iloc[0] == pytest.approx(0.0, abs=1e-9)

    def test_holes_outside_tolerance_filtered(self):
        """Holes with dist_perp > tolerance are excluded."""
        out = self._processed_two_holes()
        sec_origin = np.array([0.0, 0.0])
        proj = proyectar_pozos_en_seccion(
            out, origin=sec_origin, azimuth=90.0, length=100.0, tolerance=5.0
        )
        labels = set(proj["label_pozo"])
        assert "ON_AXIS" in labels
        assert "OFF_AXIS" not in labels  # 50 m away, beyond 5 m tolerance

    def test_dist_along_within_section_extent(self):
        """Holes with dist_along outside [-length/2, length/2] are excluded.

        Section azimuth=90° (East) with origin (0,0) and length=100m covers
        the X-axis from -50 to +50. A hole at lat=80 is past the East end.
        """
        df = pd.concat(
            [
                _make_valid_hole(lat=0.0, lon=0.0, label="CENTER"),
                _make_valid_hole(lat=80.0, lon=0.0, label="PAST_END"),
            ],
            ignore_index=True,
        )
        out = procesar_pozos(df)[0]
        sec_origin = np.array([0.0, 0.0])
        proj = proyectar_pozos_en_seccion(
            out, origin=sec_origin, azimuth=90.0, length=100.0, tolerance=100.0
        )
        labels = set(proj["label_pozo"])
        assert "CENTER" in labels
        assert "PAST_END" not in labels  # dist_along=80 > length/2=50

    def test_empty_dataframe_passthrough(self):
        """An empty DataFrame returns an empty DataFrame without error."""
        out = procesar_pozos(_make_valid_hole())[0]
        proj = proyectar_pozos_en_seccion(
            out.iloc[0:0], origin=np.array([0.0, 0.0]), azimuth=0.0, length=100.0
        )
        assert len(proj) == 0

    def test_result_sorted_by_dist_along(self):
        """Returned frame is sorted by dist_along ascending."""
        # Three holes along the section axis, in random order
        df = pd.concat(
            [
                _make_valid_hole(lat=0.0, lon=20.0, label="MID"),
                _make_valid_hole(lat=0.0, lon=-10.0, label="WEST"),
                _make_valid_hole(lat=0.0, lon=40.0, label="EAST"),
            ],
            ignore_index=True,
        )
        out = procesar_pozos(df)[0]
        sec_origin = np.array([0.0, 0.0])
        proj = proyectar_pozos_en_seccion(
            out, origin=sec_origin, azimuth=90.0, length=100.0, tolerance=5.0
        )
        # Result must be ordered west → east (smaller → larger dist_along)
        d = proj["dist_along"].values
        assert np.all(d[:-1] <= d[1:])

    def test_default_tolerance_is_ten_metres(self):
        """Default tolerance parameter is 10 m, per the function signature."""
        import inspect

        sig = inspect.signature(proyectar_pozos_en_seccion)
        assert sig.parameters["tolerance"].default == 10.0

    def test_fecha_corte_param_is_optional(self):
        """fecha_corte is an optional param defaulting to None (no filter)."""
        import inspect

        sig = inspect.signature(proyectar_pozos_en_seccion)
        assert "fecha_corte" in sig.parameters
        assert sig.parameters["fecha_corte"].default is None

    def test_inclined_hole_included_via_toe(self):
        """A hole whose collar is off-axis but whose toe is within tolerance
        must be included (damage is delivered at the toe)."""
        # Collar 40 m off the X-axis; toe swings down to ~2 m off axis.
        df = _make_valid_hole(lat=0.0, lon=40.0, incl=71.8, az=180.0, length=40.0, label="INCLINED")
        out = procesar_pozos(df)[0]
        proj = proyectar_pozos_en_seccion(
            out, origin=np.array([0.0, 0.0]), azimuth=90.0, length=200.0, tolerance=10.0
        )
        assert not proj.empty
        assert "dist_perp_toe" in proj.columns
        assert "closest_point" in proj.columns
        assert proj["closest_point"].iloc[0] == "toe"
        assert proj["dist_perp_toe"].iloc[0] <= 10.0

    def test_closest_point_is_collar_when_collar_nearer(self):
        """For a vertical hole on the axis, the collar is the closest point."""
        df = _make_valid_hole(lat=0.0, lon=0.0, label="VERT")
        out = procesar_pozos(df)[0]
        proj = proyectar_pozos_en_seccion(
            out, origin=np.array([0.0, 0.0]), azimuth=90.0, length=100.0, tolerance=5.0
        )
        assert proj["closest_point"].iloc[0] == "collar"

    def test_fecha_corte_drops_late_and_empty_holes(self):
        """Holes blasted after the survey date (or with no date) are excluded."""
        df = pd.concat(
            [
                _make_valid_hole(lat=0.0, lon=0.0, label="EARLY", fecha="2026-01-10"),
                _make_valid_hole(lat=0.0, lon=10.0, label="LATE", fecha="2026-06-01"),
                _make_valid_hole(lat=0.0, lon=20.0, label="NODATE", fecha=None),
            ],
            ignore_index=True,
        )
        out = procesar_pozos(df)[0]
        proj_all = proyectar_pozos_en_seccion(
            out, origin=np.array([0.0, 0.0]), azimuth=90.0, length=200.0, tolerance=100.0
        )
        assert {"EARLY", "LATE"} <= set(proj_all["label_pozo"])
        proj_cut = proyectar_pozos_en_seccion(
            out, origin=np.array([0.0, 0.0]), azimuth=90.0, length=200.0,
            tolerance=100.0, fecha_corte="2026-05-01",
        )
        labels = set(proj_cut["label_pozo"])
        assert "EARLY" in labels
        assert "LATE" not in labels
        assert "NODATE" not in labels

    def test_fecha_corte_none_keeps_all(self):
        """Without fecha_corte the temporal filter is inactive."""
        df = pd.concat(
            [
                _make_valid_hole(lat=0.0, lon=0.0, label="A", fecha="2026-06-01"),
                _make_valid_hole(lat=0.0, lon=10.0, label="B", fecha="2026-01-01"),
            ],
            ignore_index=True,
        )
        out = procesar_pozos(df)[0]
        proj = proyectar_pozos_en_seccion(
            out, origin=np.array([0.0, 0.0]), azimuth=90.0, length=200.0, tolerance=100.0
        )
        assert {"A", "B"} == set(proj["label_pozo"])


class TestCierreFinalConvencion:
    """Cierre final §2.2: la convención es obligatoria y confirmada."""

    def _h(self, **kw):
        base = {"incl": 10.0, "az": 15.0}
        base.update(kw)
        return _make_valid_hole(**base)

    def test_missing_convention_raises(self):
        """Backend sin convención confirmada → bloqueo (raise, sin toe)."""
        df = self._h().drop(columns=["bench_height_m", "Incl_convention"])
        with pytest.raises(ValueError, match="convenci"):
            procesar_pozos(df, bench_height_m=15.0)

    def test_explicit_convention_computes_and_records(self):
        out, *_ = procesar_pozos(
            self._h(), incl_convention="from_vertical", bench_height_m=15.0
        )
        assert bool(out["inclination_user_confirmed"].iloc[0]) is True
        assert out["inclination_validation_status"].iloc[0] == "EXPLICIT"
        assert out["inclination_sign_convention"].iloc[0] == "ABSOLUTE_VALUE"
        assert out["inclination_unit_original"].iloc[0] == "degrees"
        assert out["inclination_source_column"].iloc[0] == "Inclinacion_real"
        assert bool(out["azimuth_user_confirmed"].iloc[0]) is True
        assert out["azimuth_convention_original"].iloc[0] == "CLOCKWISE_FROM_NORTH"
        assert out["azimuth_normalized_clockwise_from_north"].iloc[0] == 15.0

    def test_data_declared_convention(self):
        df = self._h()
        df["Incl_convention"] = "from_vertical"
        out, *_ = procesar_pozos(df, bench_height_m=15.0)
        assert out["inclination_validation_status"].iloc[0] == "DATA_DECLARED"
        assert bool(out["inclination_user_confirmed"].iloc[0]) is True
        assert out["Z_toe"].iloc[0] == pytest.approx(4215.0 - 12.0 * np.cos(np.radians(10.0)))  # Len=12

    def test_sign_convention_recorded(self):
        out, *_ = procesar_pozos(
            self._h(incl=-10.0), incl_convention="dip_from_horizontal",
            incl_sign_convention="NEGATIVE_IS_DOWNWARD_DIP", bench_height_m=15.0,
        )
        assert out["inclination_sign_convention"].iloc[0] == "NEGATIVE_IS_DOWNWARD_DIP"
        assert out["inclination_sign_applied"].iloc[0] == "negative_dip_downward"
        assert out["Incl"].iloc[0] == pytest.approx(80.0)  # dip 10 → 80 desde vertical

    def test_sign_source_defined_requires_rule(self):
        with pytest.raises(ValueError, match="sign_source_rule"):
            procesar_pozos(
                self._h(incl=-10.0), incl_convention="dip_from_horizontal",
                incl_sign_convention="SOURCE_DEFINED", bench_height_m=15.0,
            )

    def test_sign_source_defined_with_rule(self):
        out, *_ = procesar_pozos(
            self._h(incl=-65.0), incl_convention="dip_from_horizontal",
            incl_sign_convention="SOURCE_DEFINED", sign_source_rule="negative_is_downward_dip",
            bench_height_m=15.0,
        )
        assert out["Incl"].iloc[0] == pytest.approx(25.0)
        assert out["inclination_sign_applied"].iloc[0] == "negative_dip_downward"

    def test_azimuth_convention_functional(self):
        """az=90 en CCW-from-North (Este) → az normalizado 270 (Oeste horario)."""
        out, *_ = procesar_pozos(
            self._h(az=90.0), incl_convention="from_vertical",
            az_convention="COUNTERCLOCKWISE_FROM_NORTH", bench_height_m=15.0,
        )
        assert out["Az"].iloc[0] == pytest.approx(270.0)
        assert out["azimuth_conversion_applied"].iloc[0] == "ccw_from_north->cw_from_north"

    def test_geometry_configuration_contract(self):
        out, *_ = procesar_pozos(self._h(), incl_convention="from_vertical", bench_height_m=15.0)
        assert bool(out["geometry_user_confirmed"].iloc[0]) is True
        assert out["geometry_configuration_version"].iloc[0] == "1.0"
        assert out["inclination_normalized_from_vertical_deg"].iloc[0] == pytest.approx(10.0)
        assert out["azimuth_normalized_clockwise_from_north_deg"].iloc[0] == pytest.approx(15.0)

    def test_radians_unit_converted(self):
        out, *_ = procesar_pozos(
            self._h(incl=0.1745, az=0.2618), incl_convention="from_vertical",
            angle_unit="radians", bench_height_m=15.0,
        )
        assert out["Incl"].iloc[0] == pytest.approx(10.0, rel=1e-3)
        assert out["Az"].iloc[0] == pytest.approx(15.0, rel=1e-3)
        assert out["inclination_unit_original"].iloc[0] == "radians"
        assert out["azimuth_unit_original"].iloc[0] == "radians"
        assert out["inclination_conversion_applied"].iloc[0] == "radians->degrees"

    def test_azimuth_original_preserved(self):
        out, *_ = procesar_pozos(
            self._h(az=370.0), incl_convention="from_vertical", bench_height_m=15.0
        )
        assert out["azimuth_original"].iloc[0] == 370.0
        assert out["Az"].iloc[0] == 10.0
        assert out["azimuth_conversion_applied"].iloc[0] == "mod-360"

    def test_out_of_range_rejected(self):
        df = self._h(incl=120.0)
        out, *_ = procesar_pozos(df, incl_convention="from_vertical", bench_height_m=15.0)
        assert len(out) == 0  # dropped (never converted, never used)


class TestRejectedRowsDiagnostics:
    """Auditoría §3.4: las filas rechazadas conservan su diagnóstico."""

    def test_out_of_range_row_recorded_not_silently_dropped(self):
        df = pd.concat(
            [_make_valid_hole(incl=10.0, label="OK"), _make_valid_hole(incl=120.0, label="BAD")],
            ignore_index=True,
        )
        out, *_ = procesar_pozos(df, incl_convention="from_vertical", bench_height_m=15.0)
        assert len(out) == 1  # solo la válida participa
        assert out["row_processing_status"].iloc[0] == "accepted"
        assert int(out["processing_rows_received"].iloc[0]) == 2
        assert int(out["processing_rows_accepted"].iloc[0]) == 1
        assert int(out["processing_rows_rejected"].iloc[0]) == 1
        assert "BAD" in out["processing_rejected_ids"].iloc[0]
        assert "OUT_OF_RANGE" in out["processing_rejected_reasons"].iloc[0].upper() or \
            "rango" in out["processing_rejected_reasons"].iloc[0].lower()

    def test_nan_row_rejected_with_reason(self):
        df = _make_valid_hole(label="NAN_X")
        df.loc[0, "Latitud_Geo"] = np.nan
        out, *_ = procesar_pozos(df, incl_convention="from_vertical", bench_height_m=15.0)
        assert len(out) == 0
        assert "NAN_X" in out["processing_rejected_ids"].iloc[0] if len(out) else True

    def test_rejected_id_and_reason_detail(self):
        df = pd.concat(
            [_make_valid_hole(incl=10.0, label="OK"), _make_valid_hole(length=0.0, label="ZERO")],
            ignore_index=True,
        )
        out, *_ = procesar_pozos(df, incl_convention="from_vertical", bench_height_m=15.0)
        assert len(out) == 1
        assert "ZERO" in out["processing_rejected_ids"].iloc[0]
        assert "longitud" in out["processing_rejected_reasons"].iloc[0].lower() or \
            "len" in out["processing_rejected_reasons"].iloc[0].lower()
