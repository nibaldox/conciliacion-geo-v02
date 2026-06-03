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
                "Kilos_Cargados_real": 250.0,
                "fecha_tronadura": fecha,
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
