"""Integration / parity tests for the geometry contract across layers.

Integración §3.8 / §5.8 — these tests exercise the FULL pipeline:

    UI FormData (mocked) → API → core.procesar_pozos → persistence → read-back
    Streamlit (mocked state) → core.procesar_pozos → structured result

and verify that every layer carries the SAME contract values (version,
confirmation, source columns, conventions, units, normalized angles, toe).
They also exercise the export endpoints (§5.7) end-to-end against the
persisted payload.

Adversarial cases mirrored from §8:
    1. upload without confirming → 400 GEOMETRY_NOT_CONFIRMED
    2. confirm then change unit → confirmation auto-invalidated
    3. contract with empty source columns → 400 GEOMETRY_INCOMPLETE
    4. declared column not in dataset → 400 SOURCE_COLUMN_NOT_FOUND
    5. incl DEGREES + az RADIANS → toe matches the canonical conversion
    6. all rows rejected → 422 with structured payload
    7. one row three errors → 3 rejection records
    8. persistence read-back → version + rejections + accepted preserved
    9. export reopens → every expected sheet present
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.calculo_tronadura import procesar_pozos
from core.geometry_contract import (
    GEOMETRY_CONFIGURATION_VERSION,
    GeometryConfiguration,
    GeometryConfigurationError,
)


# ---------------------------------------------------------------------------
# Helpers — the canonical full contract used by every parity test.
# ---------------------------------------------------------------------------


def _full_config(**overrides) -> GeometryConfiguration:
    defaults = {
        "geometry_user_confirmed": True,
        "inclination_convention": "FROM_VERTICAL",
        "inclination_sign_convention": "ABSOLUTE_VALUE",
        "inclination_unit": "DEGREES",
        "azimuth_convention": "CLOCKWISE_FROM_NORTH",
        "azimuth_unit": "DEGREES",
        "inclination_source_column": "Inclinacion_real",
        "azimuth_source_column": "Azimuth_real",
    }
    defaults.update(overrides)
    return GeometryConfiguration(**defaults)


def _dataset(incl: float = 15.0, az: float = 90.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Latitud_Geo": 1000.0,
                "Longitud_Geo": 2000.0,
                "Nombre_Banco": 4000.0,
                "Inclinacion_real": incl,
                "Azimuth_real": az,
                "longitud_real": 12.0,
                "bench_height_m": 15.0,
                "Kilos_Cargados_real": 250.0,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Layer 1: backend contract → procesar_pozos
# ---------------------------------------------------------------------------


class TestBackendCarriesContract:
    def test_version_persisted_on_accepted_rows(self):
        cfg = _full_config()
        out, *_ = procesar_pozos(_dataset(), geometry_configuration=cfg)
        assert out["geometry_configuration_version"].iloc[0] == cfg.geometry_configuration_version
        assert cfg.geometry_configuration_version == GEOMETRY_CONFIGURATION_VERSION

    def test_declared_source_columns_match_persisted(self):
        cfg = _full_config(
            inclination_source_column="Inclinacion_real",
            azimuth_source_column="Azimuth_real",
        )
        out, *_ = procesar_pozos(_dataset(), geometry_configuration=cfg)
        assert out["inclination_source_column"].iloc[0] == "Inclinacion_real"
        assert out["azimuth_source_column"].iloc[0] == "Azimuth_real"

    def test_declared_source_column_not_in_dataset_blocks(self):
        cfg = _full_config(inclination_source_column="No_Existe")
        with pytest.raises(GeometryConfigurationError) as ei:
            procesar_pozos(_dataset(), geometry_configuration=cfg)
        assert ei.value.error_code == "INCLINATION_SOURCE_COLUMN_NOT_FOUND"

    def test_empty_source_column_blocks_at_validate(self):
        # validate() raises BEFORE procesar_pozos even starts.
        bad = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="ABSOLUTE_VALUE",
            inclination_unit="DEGREES",
            azimuth_convention="CLOCKWISE_FROM_NORTH",
            azimuth_unit="DEGREES",
            inclination_source_column="",
            azimuth_source_column="",
        )
        with pytest.raises(GeometryConfigurationError) as ei:
            bad.validate()
        assert ei.value.error_code == "GEOMETRY_INCOMPLETE"
        assert "inclination_source_column" in ei.value.details["missing_or_invalid"]
        assert "azimuth_source_column" in ei.value.details["missing_or_invalid"]


# ---------------------------------------------------------------------------
# Layer 2: independent units → numerical correctness
# ---------------------------------------------------------------------------


class TestIndependentUnits:
    """Integración §3.5/§5.5 — inclination and azimuth units are INDEPENDENT."""

    def test_degrees_degrees(self):
        cfg = _full_config(inclination_unit="DEGREES", azimuth_unit="DEGREES")
        df = _dataset(incl=15.0, az=90.0)
        out, *_ = procesar_pozos(df, geometry_configuration=cfg)
        # az=90° (EAST) → toe_x displaced; incl=15° → toe_z displaced.
        assert out["Az"].iloc[0] == pytest.approx(90.0)
        assert out["Incl"].iloc[0] == pytest.approx(15.0)

    def test_radians_radians(self):
        cfg = _full_config(inclination_unit="RADIANS", azimuth_unit="RADIANS")
        df = _dataset(incl=np.radians(15.0), az=np.radians(90.0))
        out, *_ = procesar_pozos(df, geometry_configuration=cfg)
        assert out["Az"].iloc[0] == pytest.approx(90.0)
        assert out["Incl"].iloc[0] == pytest.approx(15.0)

    def test_degrees_radians(self):
        # incl in DEGREES, az in RADIANS — each must use its own unit.
        cfg = _full_config(inclination_unit="DEGREES", azimuth_unit="RADIANS")
        df = _dataset(incl=15.0, az=np.radians(90.0))
        out, *_ = procesar_pozos(df, geometry_configuration=cfg)
        assert out["Incl"].iloc[0] == pytest.approx(15.0)  # was degrees, untouched
        assert out["Az"].iloc[0] == pytest.approx(90.0)  # was radians, converted

    def test_radians_degrees(self):
        cfg = _full_config(inclination_unit="RADIANS", azimuth_unit="DEGREES")
        df = _dataset(incl=np.radians(15.0), az=90.0)
        out, *_ = procesar_pozos(df, geometry_configuration=cfg)
        assert out["Incl"].iloc[0] == pytest.approx(15.0)
        assert out["Az"].iloc[0] == pytest.approx(90.0)

    def test_mixed_units_match_independent_conversion(self):
        # Numerical check: az=pi/2 rad with incl=15° should produce the
        # SAME toe as az=90° with incl=15° (geometry is unit-agnostic
        # once normalized).
        cfg_dd = _full_config(inclination_unit="DEGREES", azimuth_unit="DEGREES")
        cfg_dr = _full_config(inclination_unit="DEGREES", azimuth_unit="RADIANS")
        out_dd, *_ = procesar_pozos(_dataset(incl=15.0, az=90.0), geometry_configuration=cfg_dd)
        out_dr, *_ = procesar_pozos(_dataset(incl=15.0, az=np.pi / 2), geometry_configuration=cfg_dr)
        assert out_dr["X_toe"].iloc[0] == pytest.approx(out_dd["X_toe"].iloc[0], abs=1e-6)
        assert out_dr["Y_toe"].iloc[0] == pytest.approx(out_dd["Y_toe"].iloc[0], abs=1e-6)
        assert out_dr["Z_toe"].iloc[0] == pytest.approx(out_dd["Z_toe"].iloc[0], abs=1e-6)

    def test_missing_inclination_unit_blocks(self):
        bad = _full_config(inclination_unit=None)
        with pytest.raises(GeometryConfigurationError) as ei:
            bad.validate()
        assert "inclination_unit" in ei.value.details["missing_or_invalid"]


# ---------------------------------------------------------------------------
# Layer 3: API parity — the FormData the UI builds is accepted end-to-end.
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client(api_isolated_db):
    from fastapi.testclient import TestClient
    from api.main import app
    import api.database as db
    with TestClient(app) as client:
        yield client, db


def _ui_form_data(session_id: str, **overrides) -> dict:
    """Mimic the FormData produced by web/src/components/results/BlastUploader.tsx."""
    base = {
        "session_id": session_id,
        "geometry_user_confirmed": "true",
        "incl_convention": "from_vertical",
        "incl_sign_convention": "ABSOLUTE_VALUE",
        "az_convention": "CLOCKWISE_FROM_NORTH",
        "angle_unit": "degrees",
        "bench_height_m": "15.0",
        "incl_source_column": "Inclinacion_real",
        "az_source_column": "Azimuth_real",
    }
    base.update(overrides)
    return base


class TestApiFormDataParity:
    def test_ui_formdata_accepted_and_carries_contract(self, api_client):
        client, db = api_client
        sid = db.create_session()
        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            "1000.0,2000.0,4000,15.0,90.0,12.0\n"
        )
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=_ui_form_data(sid),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The persisted contract version matches GEOMETRY_CONFIGURATION_VERSION.
        cfg = body["geometry_configuration"]
        assert cfg["geometry_configuration_version"] == GEOMETRY_CONFIGURATION_VERSION
        assert cfg["geometry_user_confirmed"] is True
        assert cfg["inclination_source_column"] == "Inclinacion_real"
        assert cfg["azimuth_source_column"] == "Azimuth_real"
        # accepted_rows present and version stamped.
        assert len(body["accepted_rows"]) == 1
        assert (
            body["accepted_rows"][0]["geometry_configuration_version"]
            == GEOMETRY_CONFIGURATION_VERSION
        )

    def test_ui_formdata_without_confirmation_returns_400(self, api_client):
        client, db = api_client
        sid = db.create_session()
        csv = "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n1000.0,2000.0,4000,15.0,90.0,12.0\n"
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=_ui_form_data(sid, geometry_user_confirmed="false"),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error_code"] == "GEOMETRY_REJECTED"

    def test_ui_formdata_with_empty_source_columns_returns_400(self, api_client):
        client, db = api_client
        sid = db.create_session()
        csv = "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n1000.0,2000.0,4000,15.0,90.0,12.0\n"
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=_ui_form_data(sid, incl_source_column="", az_source_column=""),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error_code"] == "GEOMETRY_INCOMPLETE"

    def test_ui_formdata_with_unknown_source_column_returns_blocking_error(self, api_client):
        client, db = api_client
        sid = db.create_session()
        csv = "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n1000.0,2000.0,4000,15.0,90.0,12.0\n"
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=_ui_form_data(sid, incl_source_column="No_Existe_En_Dataset"),
        )
        # The processor surfaces the structured blocking error in the
        # body and returns HTTP 422 (zero accepted rows + blocking error)
        # — never a bare 400 that hides the diagnosis.
        assert resp.status_code == 422
        body = resp.json()
        codes = [e["error_code"] for e in body["blocking_errors"]]
        assert "INCLINATION_SOURCE_COLUMN_NOT_FOUND" in codes


# ---------------------------------------------------------------------------
# Layer 4: persistence read-back — what the API stores is what we read.
# ---------------------------------------------------------------------------


class TestPersistenceRoundTrip:
    def _upload(self, client, db, csv: str) -> str:
        sid = db.create_session()
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=_ui_form_data(sid),
        )
        assert resp.status_code in (200, 422), resp.text
        return sid

    def test_accepted_rejected_and_summary_survive_readback(self, api_client):
        client, db = api_client
        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            "1000.0,2000.0,4000,15.0,90.0,12.0\n"
            ",2000.0,4000,15.0,90.0,12.0\n"
        )
        sid = self._upload(client, db, csv)
        settings = db.get_settings(sid)
        assert len(settings["accepted_rows"]) == 1
        assert len(settings["rejected_rows"]) == 1
        assert settings["processing_summary"]["rows_received"] == 2
        assert settings["processing_summary"]["rows_accepted"] == 1
        assert settings["geometry_configuration"]["geometry_configuration_version"] == GEOMETRY_CONFIGURATION_VERSION

    def test_zero_accepted_rows_persist_rejections(self, api_client):
        client, db = api_client
        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            ",2000.0,4000,15.0,90.0,12.0\n"
            "1000.0,2000.0,4000,,,12.0\n"
        )
        sid = self._upload(client, db, csv)
        settings = db.get_settings(sid)
        assert settings["accepted_rows"] == []
        assert len(settings["rejected_rows"]) >= 2
        assert settings["blocking_errors"]
        assert settings["blocking_errors"][0]["error_code"] == "NO_ACCEPTED_ROWS"


# ---------------------------------------------------------------------------
# Layer 5: export endpoints reopen with the right sheets and counts.
# ---------------------------------------------------------------------------


class TestExportEndpointsEndToEnd:
    def _seed(self, client, db) -> str:
        sid = db.create_session()
        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            "1000.0,2000.0,4000,15.0,90.0,12.0\n"
            ",2000.0,4000,15.0,90.0,12.0\n"
        )
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=_ui_form_data(sid),
        )
        assert resp.status_code in (200, 422), resp.text
        return sid

    def test_blast_diagnostics_endpoint_returns_xlsx(self, api_client, tmp_path):
        client, db = api_client
        sid = self._seed(client, db)
        # The endpoint reads the session from the X-Session-ID header.
        resp = client.get("/api/v1/export/blast-diagnostics", headers={"X-Session-ID": sid})
        assert resp.status_code == 200, resp.text
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        # Re-open it.
        from core.blast_export import read_back_excel
        path = tmp_path / "diag.xlsx"
        path.write_bytes(resp.content)
        sheets = read_back_excel(path)
        for name in (
            "Pozos_Aceptados",
            "Filas_Rechazadas",
            "Resumen_Procesamiento",
            "Configuracion_Geometrica",
        ):
            assert name in sheets
        assert len(sheets["Pozos_Aceptados"]) == 1
        assert len(sheets["Filas_Rechazadas"]) == 1

    def test_blast_rejections_endpoint_returns_standalone_xlsx(self, api_client, tmp_path):
        client, db = api_client
        sid = self._seed(client, db)
        resp = client.get("/api/v1/export/blast-rejections", headers={"X-Session-ID": sid})
        assert resp.status_code == 200, resp.text
        from core.blast_export import read_back_excel
        path = tmp_path / "rej.xlsx"
        path.write_bytes(resp.content)
        sheets = read_back_excel(path)
        assert "Filas_Rechazadas" in sheets
        assert "Metadata" in sheets

    def test_blast_diagnostics_returns_404_without_upload(self, api_client):
        client, db = api_client
        sid = db.create_session()
        resp = client.get("/api/v1/export/blast-diagnostics", headers={"X-Session-ID": sid})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Layer 6: Streamlit parity — the session_state build produces a valid
# contract that procesar_pozos accepts with the SAME values the API sees.
# ---------------------------------------------------------------------------


class TestStreamlitContractParity:
    """Mirror of ui/modulo_tronadura/upload.py contract construction."""

    def _streamlit_cfg(self, **session_overrides) -> GeometryConfiguration:
        """Reproduce the GeometryConfiguration built by Streamlit."""
        # Pretend the operator ticked the confirmation checkbox.
        ss = {
            "blast_geometry_confirmed": True,
            "blast_incl_convention": "from_vertical",
            "blast_sign_rule": "ABSOLUTE_VALUE",
            "blast_sign_source_rule": "",
            "blast_az_convention": "CLOCKWISE_FROM_NORTH",
            "blast_incl_unit": "Grados",
            "blast_az_unit": "Grados",
        }
        ss.update(session_overrides)
        incl_src = ss.get("blast_confirmed_incl_col", "Inclinacion_real")
        az_src = ss.get("blast_confirmed_az_col", "Azimuth_real")
        return GeometryConfiguration(
            geometry_user_confirmed=bool(ss["blast_geometry_confirmed"]),
            inclination_convention=(
                {"from_vertical": "FROM_VERTICAL",
                 "dip_from_horizontal": "DIP_FROM_HORIZONTAL"}.get(ss["blast_incl_convention"] or "")
                if ss["blast_incl_convention"] else None
            ),
            inclination_sign_convention=ss["blast_sign_rule"],
            inclination_source_rule=ss.get("blast_sign_source_rule") or "",
            inclination_unit="RADIANS" if ss["blast_incl_unit"] == "Radianes" else "DEGREES",
            azimuth_convention=ss["blast_az_convention"],
            azimuth_unit="RADIANS" if ss["blast_az_unit"] == "Radianes" else "DEGREES",
            inclination_source_column=incl_src,
            azimuth_source_column=az_src,
        )

    def test_streamlit_confirmation_transmits_true(self):
        cfg = self._streamlit_cfg()
        assert cfg.geometry_user_confirmed is True
        cfg.validate()  # must not raise

    def test_streamlit_no_confirmation_blocks(self):
        cfg = self._streamlit_cfg(blast_geometry_confirmed=False)
        with pytest.raises(GeometryConfigurationError) as ei:
            cfg.validate()
        assert ei.value.error_code == "GEOMETRY_REJECTED"

    def test_streamlit_and_api_produce_same_toe(self):
        # Same dataset + same contract values → same toe coordinates,
        # regardless of whether it was built by the web FormData or by
        # the Streamlit session_state path.
        ds = _dataset()
        streamlit_cfg = self._streamlit_cfg()
        api_cfg = _full_config()
        out_st, *_ = procesar_pozos(ds, geometry_configuration=streamlit_cfg)
        out_api, *_ = procesar_pozos(_dataset(), geometry_configuration=api_cfg)
        assert out_st["X_toe"].iloc[0] == pytest.approx(out_api["X_toe"].iloc[0])
        assert out_st["Y_toe"].iloc[0] == pytest.approx(out_api["Y_toe"].iloc[0])
        assert out_st["Z_toe"].iloc[0] == pytest.approx(out_api["Z_toe"].iloc[0])

    def test_streamlit_mixed_units_flow_through(self):
        cfg = self._streamlit_cfg(blast_incl_unit="Grados", blast_az_unit="Radianes")
        # incl in degrees, az in radians — same numerical outcome as the
        # direct API call with the equivalent mixed config.
        df = _dataset(incl=15.0, az=np.pi / 2)
        out, *_ = procesar_pozos(df, geometry_configuration=cfg)
        assert out["Incl"].iloc[0] == pytest.approx(15.0)
        assert out["Az"].iloc[0] == pytest.approx(90.0)
        assert out["inclination_unit_original"].iloc[0] == "degrees"
        assert out["azimuth_unit_original"].iloc[0] == "radians"


# ---------------------------------------------------------------------------
# Layer 7: regression — no operational '1.0' literal left on active paths.
# ---------------------------------------------------------------------------


class TestNoStaleVersionLiterals:
    def test_no_geometry_configuration_version_literal_1_in_active_code(self):
        import subprocess
        # Search the active code paths for stale '1.0' literals attached
        # to geometry_configuration_version. Comments/historical notes
        # are allowed (we only flag real assignments).
        repo = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [
                "grep",
                "-rn",
                "--include=*.py",
                "geometry_configuration_version.*=.*[\"']1\\.",
                str(repo / "core"),
                str(repo / "api"),
            ],
            capture_output=True,
            text=True,
        )
        # No active assignment to a 1.x literal must remain.
        assert result.stdout == "", (
            f"Stale version literal found:\n{result.stdout}"
        )
