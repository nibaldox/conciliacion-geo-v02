"""Tests for core.geometry_conventions — canonical inclination/azimuth.

Canonical convention (per project spec §4.1):
- inclination: deviation from vertical, positive degrees, 0 = vertical
- azimuth: degrees clockwise from North (N=0, E=90, S=180, W=270)
"""
import numpy as np
import pandas as pd
import pytest

from core.geometry_conventions import (
    InclinationConvention,
    normalize_azimuth,
    normalize_inclination,
    normalize_vector_components,
)


class TestNormalizeInclination:
    def test_from_vertical_is_identity(self):
        v = pd.Series([0.0, 10.0, 45.0, 90.0])
        out, meta = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert out.tolist() == pytest.approx([0.0, 10.0, 45.0, 90.0])
        assert meta["convention"] == "from_vertical"

    def test_dip_from_horizontal_converted(self):
        v = pd.Series([0.0, 30.0, 60.0, 90.0])
        out, meta = normalize_inclination(v, InclinationConvention.DIP_FROM_HORIZONTAL)
        assert out.tolist() == pytest.approx([90.0, 60.0, 30.0, 0.0])
        assert meta["conversion"] == "dip->90-dip"

    def test_negative_dip_magnitude_and_orientation(self):
        """H-04: -65° dip = magnitude 65 + orientation flag, NOT 155° (out of range)."""
        v = pd.Series([-65.0, 65.0, -30.0, 0.0])
        out, meta = normalize_inclination(v, InclinationConvention.DIP_FROM_HORIZONTAL)
        assert out.tolist() == pytest.approx([25.0, 25.0, 60.0, 90.0])
        assert "orientation_sign" in meta
        assert list(meta["orientation_sign"]) == [-1, 1, -1, 0]
        assert "orientation_field" in meta

    def test_negative_values_recorded_and_absolutized(self):
        v = pd.Series([-10.0, -5.0, 0.0, 10.0])
        out, meta = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert out.tolist() == pytest.approx([10.0, 5.0, 0.0, 10.0])
        assert meta["negative_wrapped"] == 2
        assert list(meta["orientation_sign"]) == [-1, -1, 0, 1]

    def test_out_of_range_nan(self):
        v = pd.Series([120.0, -90.0, 10.0])
        out, meta = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert pd.isna(out.iloc[0])
        assert out.iloc[2] == pytest.approx(10.0)
        assert meta["rejected_out_of_range"] == 1

    def test_nan_passthrough(self):
        v = pd.Series([np.nan, 10.0])
        out, _ = normalize_inclination(v, InclinationConvention.FROM_VERTICAL)
        assert pd.isna(out.iloc[0])
        assert out.iloc[1] == pytest.approx(10.0)


class TestNormalizeAzimuth:
    def test_from_north_cw_is_identity(self):
        v = pd.Series([0.0, 90.0, 180.0, 270.0, 360.0])
        out, meta = normalize_azimuth(v)
        assert out.tolist() == pytest.approx([0.0, 90.0, 180.0, 270.0, 0.0])
        assert meta["convention"] == "CLOCKWISE_FROM_NORTH"

    def test_wrap_negative_and_overflow(self):
        v = pd.Series([-10.0, 370.0, 720.0])
        out, _ = normalize_azimuth(v)
        assert out.tolist() == pytest.approx([350.0, 10.0, 0.0])

    def test_nan_passthrough(self):
        v = pd.Series([np.nan, 45.0])
        out, _ = normalize_azimuth(v)
        assert pd.isna(out.iloc[0])
        assert out.iloc[1] == pytest.approx(45.0)


class TestNormalizeVectorComponents:
    def test_vertical_hole(self):
        incl = normalize_inclination(pd.Series([0.0]), InclinationConvention.FROM_VERTICAL)[0]
        az = normalize_azimuth(pd.Series([0.0]))[0]
        vx, vy, vz = normalize_vector_components(incl, az)
        assert vx.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vy.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vz.iloc[0] == pytest.approx(-1.0, abs=1e-9)

    def test_horizontal_north(self):
        incl = normalize_inclination(pd.Series([90.0]), InclinationConvention.FROM_VERTICAL)[0]
        az = normalize_azimuth(pd.Series([0.0]))[0]
        vx, vy, vz = normalize_vector_components(incl, az)
        assert vx.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vy.iloc[0] == pytest.approx(1.0, abs=1e-9)
        assert vz.iloc[0] == pytest.approx(0.0, abs=1e-9)

    def test_horizontal_east(self):
        incl = normalize_inclination(pd.Series([90.0]), InclinationConvention.FROM_VERTICAL)[0]
        az = normalize_azimuth(pd.Series([90.0]))[0]
        vx, vy, vz = normalize_vector_components(incl, az)
        assert vx.iloc[0] == pytest.approx(1.0, abs=1e-9)
        assert vy.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert vz.iloc[0] == pytest.approx(0.0, abs=1e-9)

    def test_dip_convention_consistent(self):
        """A hole with dip=60 from horizontal equals incl=30 from vertical."""
        v1 = normalize_inclination(pd.Series([60.0]), InclinationConvention.DIP_FROM_HORIZONTAL)[0]
        v2 = normalize_inclination(pd.Series([30.0]), InclinationConvention.FROM_VERTICAL)[0]
        a1 = normalize_azimuth(pd.Series([0.0]))[0]
        c1 = normalize_vector_components(v1, a1)
        c2 = normalize_vector_components(v2, a1)
        for x, y in zip(c1, c2):
            assert x.iloc[0] == pytest.approx(y.iloc[0], abs=1e-9)


class TestSignConventions:
    """Auditoría §3.3: las políticas de signo gobiernan la normalización."""

    def test_absolute_value(self):
        v = pd.Series([-65.0, 65.0, -30.0])
        out, meta = normalize_inclination(v, "dip_from_horizontal", sign_convention="ABSOLUTE_VALUE")
        assert out.tolist() == pytest.approx([25.0, 25.0, 60.0])
        assert meta["sign_convention"] == "ABSOLUTE_VALUE"
        assert meta["sign_applied"] == "abs"

    def test_negative_is_downward_dip(self):
        v = pd.Series([-65.0, 65.0, -30.0])
        out, meta = normalize_inclination(v, "dip_from_horizontal", sign_convention="NEGATIVE_IS_DOWNWARD_DIP")
        assert out.tolist() == pytest.approx([25.0, 25.0, 60.0])
        assert meta["sign_applied"] == "negative_dip_downward"

    def test_negative_downward_incompatible_with_from_vertical(self):
        with pytest.raises(ValueError, match="incompatible"):
            normalize_inclination(pd.Series([-10.0]), "from_vertical",
                                  sign_convention="NEGATIVE_IS_DOWNWARD_DIP")

    def test_source_defined_with_rule(self):
        v = pd.Series([-65.0, 65.0])
        out, meta = normalize_inclination(v, "dip_from_horizontal", sign_convention="SOURCE_DEFINED",
                                          sign_source_rule="negative_is_downward_dip")
        assert out.tolist() == pytest.approx([25.0, 25.0])
        assert meta["sign_applied"] == "negative_dip_downward"

    def test_source_defined_without_rule_blocks(self):
        with pytest.raises(ValueError, match="sign_source_rule"):
            normalize_inclination(pd.Series([-65.0]), "dip_from_horizontal",
                                  sign_convention="SOURCE_DEFINED")

    def test_source_defined_positive_only_rejects_negative(self):
        v = pd.Series([-65.0, 65.0])
        out, meta = normalize_inclination(v, "dip_from_horizontal", sign_convention="SOURCE_DEFINED",
                                          sign_source_rule="positive_only")
        assert pd.isna(out.iloc[0])
        assert out.iloc[1] == pytest.approx(25.0)
        assert meta["rejected_negative"] == 1

    def test_negative_is_downward_dip_from_vertical(self):
        """La política de signo puede combinarse: FROM_VERTICAL + SOURCE_DEFINED+positive_only."""
        v = pd.Series([-10.0, 10.0])
        out, meta = normalize_inclination(v, "from_vertical", sign_convention="SOURCE_DEFINED",
                                          sign_source_rule="positive_only")
        assert pd.isna(out.iloc[0])
        assert out.iloc[1] == pytest.approx(10.0)


class TestAzimuthConventions:
    """Auditoría §3.3: azimut funcional — 4 convenciones normalizadas."""

    def test_clockwise_from_north(self):
        out, meta = normalize_azimuth(pd.Series([0.0, 90.0, 180.0, 270.0]), "CLOCKWISE_FROM_NORTH")
        assert out.tolist() == pytest.approx([0.0, 90.0, 180.0, 270.0])

    def test_counterclockwise_from_north(self):
        out, _ = normalize_azimuth(pd.Series([0.0, 90.0, 180.0, 270.0]), "COUNTERCLOCKWISE_FROM_NORTH")
        # CCW: E=270 (en escala CCW) → 90 horario; W=90 → 270 horario
        assert out.tolist() == pytest.approx([0.0, 270.0, 180.0, 90.0])

    def test_clockwise_from_east(self):
        out, _ = normalize_azimuth(pd.Series([0.0, 90.0, 180.0, 270.0]), "CLOCKWISE_FROM_EAST")
        # E=0→90, S=90→180, W=180→270, N=270→0
        assert out.tolist() == pytest.approx([90.0, 180.0, 270.0, 0.0])

    def test_counterclockwise_from_east(self):
        out, _ = normalize_azimuth(pd.Series([0.0, 90.0, 180.0, 270.0]), "COUNTERCLOCKWISE_FROM_EAST")
        # CCW from E: E=0→90, N=90→0, W=180→270, S=270→180
        assert out.tolist() == pytest.approx([90.0, 0.0, 270.0, 180.0])

    def test_known_toe_azimuth_ccw_from_north(self):
        """Toe de referencia: incl=90, az_ccw=270 (Este en escala CCW) → toe +X."""
        v, _ = normalize_azimuth(pd.Series([270.0]), "COUNTERCLOCKWISE_FROM_NORTH")
        assert v.iloc[0] == pytest.approx(90.0)

    def test_wrap_360(self):
        out, _ = normalize_azimuth(pd.Series([360.0, -10.0, 370.0]), "CLOCKWISE_FROM_NORTH")
        assert out.tolist() == pytest.approx([0.0, 350.0, 10.0])

    def test_conversion_recorded(self):
        _, meta = normalize_azimuth(pd.Series([45.0]), "COUNTERCLOCKWISE_FROM_NORTH")
        assert "conversion" in meta


class TestParidadBackendAPI:
    """Auditoría §3.3: backend y API producen la misma normalización."""

    def test_parity_azimuth_and_sign(self):
        """La misma configuración → mismo az, mismo toe, mismos estados."""
        import io

        from fastapi.testclient import TestClient
        from api.main import app

        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,"
            "longitud_real,Kilos_Cargados_real,Incl_convention,bench_height_m\n"
            "100,200,4000,-65,90,12,250,from_vertical,15\n"
            "105,205,4000,-65,90,12,250,from_vertical,15\n"
        )
        client = TestClient(app)
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data={
                "session_id": "parity-1",
                "incl_convention": "dip_from_horizontal",
                "incl_sign_convention": "NEGATIVE_IS_DOWNWARD_DIP",
                "az_convention": "COUNTERCLOCKWISE_FROM_NORTH",
            },
        )
        assert resp.status_code == 200, resp.text
        holes_resp = client.get("/api/v1/blast/parity-1/holes")
        assert holes_resp.status_code == 200, holes_resp.text
        api_hole = holes_resp.json()["holes"][0]

        from core.calculo_tronadura import procesar_pozos
        import pandas as pd

        df = pd.DataFrame([{
            "Latitud_Geo": 100.0, "Longitud_Geo": 200.0, "Nombre_Banco": 4000.0,
            "Inclinacion_real": -65.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
            "Kilos_Cargados_real": 250.0, "Incl_convention": "from_vertical",
            "bench_height_m": 15.0,
        }])
        out, *_ = procesar_pozos(
            df, incl_convention="dip_from_horizontal",
            incl_sign_convention="NEGATIVE_IS_DOWNWARD_DIP",
            az_convention="COUNTERCLOCKWISE_FROM_NORTH",
        )
        # backend
        assert out["Incl"].iloc[0] == pytest.approx(25.0)  # dip 65 → 25 desde vertical
        assert out["Az"].iloc[0] == pytest.approx(270.0)   # CCW 90 (E) → 270 horario (W)
        # API persiste los mismos valores (campos clave)
        assert api_hole["inclination"] == pytest.approx(25.0)
        assert api_hole["azimuth"] == pytest.approx(270.0)
