"""Adversarial regression suite for Phase 1 auditable closure.

Each test demonstrates ONE blocking issue from the prompt is reproducible
WITHOUT the fix and passes WITH it. Positive and negative cases are
paired so the contract is exercised in both directions.

Covers:
  3.1 Implicit geometric confirmation
  3.2 Structured rejected_rows / zero accepted
  3.3 SQLite initialization (fixtures centralized)
  3.5 ``angle_unit`` / ``_process_blast_dataframe`` NameError
  3.6 Invalid required polygons fail-closed

Spatial regressions (< 4 collars, OUTSIDE collars, etc.) already live in
``tests/test_voronoi_conservation.py::TestCierreBloqueosFinales``.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.blast_metrics import compute_influence_area_report
from core.calculo_tronadura import procesar_pozos
from core.geometry_contract import (
    GEOMETRY_CONFIGURATION_VERSION,
    GeometryConfiguration,
    GeometryConfigurationError,
)


# ---------------------------------------------------------------------------
# 3.1 — Implicit geometric confirmation
# ---------------------------------------------------------------------------


def _one_hole_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Latitud_Geo": 1000.0,
                "Longitud_Geo": 2000.0,
                "Nombre_Banco": 4000.0,
                "Inclinacion_real": 15.0,
                "Azimuth_real": 90.0,
                "longitud_real": 12.0,
                "Kilos_Cargados_real": 250.0,
                "bench_height_m": 15.0,
            }
        ]
    )


class TestGeometricConfirmation:
    """Only ``geometry_user_confirmed is True`` enables geometry."""

    def test_explicit_true_enables_toe(self):
        cfg = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="ABSOLUTE_VALUE",
            inclination_unit="DEGREES",
            azimuth_convention="CLOCKWISE_FROM_NORTH",
            azimuth_unit="DEGREES",
        )
        out, *_ = procesar_pozos(_one_hole_df(), geometry_configuration=cfg)
        assert pd.notna(out["X_toe"].iloc[0])
        assert pd.notna(out["inclination_normalized_from_vertical_deg"].iloc[0])
        assert pd.notna(out["azimuth_normalized_clockwise_from_north_deg"].iloc[0])

    @pytest.mark.parametrize("confirm", [False, None])
    def test_explicit_false_or_none_blocks(self, confirm):
        cfg = GeometryConfiguration(geometry_user_confirmed=confirm)
        with pytest.raises(GeometryConfigurationError) as ei:
            cfg.validate()
        assert ei.value.error_code in ("GEOMETRY_REJECTED", "GEOMETRY_NOT_CONFIRMED")
        # And the processor refuses to compute toe.
        with pytest.raises(GeometryConfigurationError):
            procesar_pozos(
                _one_hole_df(),
                geometry_user_confirmed=confirm,
                incl_convention="from_vertical",
            )

    def test_legacy_unconfirmed_state_is_explicit(self):
        cfg = GeometryConfiguration()  # all defaults
        assert cfg.is_legacy_unconfirmed()
        with pytest.raises(GeometryConfigurationError) as ei:
            cfg.validate()
        assert ei.value.details.get("state") == "LEGACY_UNCONFIRMED"

    def test_partial_configuration_blocked(self):
        # inclination_convention present but unit/sign/azimuth missing.
        cfg = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
        )
        with pytest.raises(GeometryConfigurationError) as ei:
            cfg.validate()
        assert ei.value.error_code == "GEOMETRY_INCOMPLETE"
        # Required fields are surfaced explicitly.
        missing = ei.value.details.get("missing_or_invalid", {})
        assert "inclination_unit" in missing
        assert "azimuth_convention" in missing

    def test_no_angular_defaults_invented(self):
        # Even with confirmation, missing unit blocks.
        cfg = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="ABSOLUTE_VALUE",
            inclination_unit=None,
            azimuth_convention="CLOCKWISE_FROM_NORTH",
            azimuth_unit="DEGREES",
        )
        with pytest.raises(GeometryConfigurationError) as ei:
            cfg.validate()
        assert "inclination_unit" in ei.value.details["missing_or_invalid"]

    def test_source_defined_requires_rule(self):
        cfg = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="SOURCE_DEFINED",
            inclination_unit="DEGREES",
            azimuth_convention="CLOCKWISE_FROM_NORTH",
            azimuth_unit="DEGREES",
            inclination_source_rule="",
        )
        with pytest.raises(GeometryConfigurationError) as ei:
            cfg.validate()
        assert "inclination_source_rule" in ei.value.details["missing_or_invalid"]

    def test_data_column_is_not_implicit_confirmation(self):
        # A dataset-declared ``Incl_convention`` column is NOT implicit
        # operator confirmation. Without the explicit gate the geometry
        # is BLOCKED.
        df = _one_hole_df()
        df["Incl_convention"] = "from_vertical"
        with pytest.raises(GeometryConfigurationError):
            procesar_pozos(df, incl_convention="from_vertical")

    def test_degrees_and_radians_both_functional(self):
        for unit, incl_in in (("DEGREES", 15.0), ("RADIANS", 0.2618)):
            cfg = GeometryConfiguration(
                geometry_user_confirmed=True,
                inclination_convention="FROM_VERTICAL",
                inclination_sign_convention="ABSOLUTE_VALUE",
                inclination_unit=unit,
                azimuth_convention="CLOCKWISE_FROM_NORTH",
                azimuth_unit=unit,
            )
            df = _one_hole_df()
            df["Inclinacion_real"] = incl_in
            df["Azimuth_real"] = 1.5708 if unit == "RADIANS" else 90.0
            out, *_ = procesar_pozos(df, geometry_configuration=cfg)
            assert len(out) == 1, f"unit={unit} produced empty accepted frame"
            assert pd.notna(out["X_toe"].iloc[0])

    @pytest.mark.parametrize(
        "az_conv",
        [
            "CLOCKWISE_FROM_NORTH",
            "COUNTERCLOCKWISE_FROM_NORTH",
            "CLOCKWISE_FROM_EAST",
            "COUNTERCLOCKWISE_FROM_EAST",
        ],
    )
    def test_all_four_azimuth_conventions_accepted(self, az_conv):
        cfg = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="ABSOLUTE_VALUE",
            inclination_unit="DEGREES",
            azimuth_convention=az_conv,
            azimuth_unit="DEGREES",
        )
        cfg.validate()  # must not raise
        assert cfg.geometry_configuration_version == GEOMETRY_CONFIGURATION_VERSION


# ---------------------------------------------------------------------------
# 3.2 — Structured rejected_rows / zero accepted
# ---------------------------------------------------------------------------


class TestStructuredRejections:
    """Rejected rows are produced directly by the processor."""

    def _cfg(self) -> GeometryConfiguration:
        return GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="ABSOLUTE_VALUE",
            inclination_unit="DEGREES",
            azimuth_convention="CLOCKWISE_FROM_NORTH",
            azimuth_unit="DEGREES",
        )

    def test_mix_accepted_and_rejected(self):
        df = pd.DataFrame(
            [
                {
                    "Latitud_Geo": 1000.0, "Longitud_Geo": 2000.0, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": 15.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
                {
                    "Latitud_Geo": None, "Longitud_Geo": 2001.0, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": 15.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
            ]
        )
        out, _, _, _, rejections = procesar_pozos(
            df, geometry_configuration=self._cfg(), return_rejections=True
        )
        assert len(out) == 1
        assert len(rejections) == 1
        r = rejections[0]
        # Full structured diagnosis preserved.
        for key in (
            "hole_id", "source_row_index", "source_column", "original_value",
            "error_code", "rejection_reason", "affected_calculations",
            "recommended_action", "row_processing_status",
        ):
            assert key in r
        assert r["error_code"] == "INVALID_X"
        assert r["source_column"] == "Latitud_Geo"  # original source name
        assert r["row_processing_status"] == "rejected"

    def test_all_rows_rejected_still_returns_structure(self):
        df = pd.DataFrame(
            [
                {
                    "Latitud_Geo": None, "Longitud_Geo": 2000.0, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": 15.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
                {
                    "Latitud_Geo": 1000.0, "Longitud_Geo": 2001.0, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": None, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
            ]
        )
        out, _, _, _, rejections = procesar_pozos(
            df, geometry_configuration=self._cfg(), return_rejections=True
        )
        assert len(out) == 0
        assert len(rejections) == 2
        codes = sorted(r["error_code"] for r in rejections)
        assert codes == ["INVALID_Incl", "INVALID_X"]

    def test_multiple_errors_per_row(self):
        # A single row with two invalid fields produces two rejection records.
        df = pd.DataFrame(
            [
                {
                    "Latitud_Geo": None, "Longitud_Geo": None, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": 15.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
            ]
        )
        _, _, _, _, rejections = procesar_pozos(
            df, geometry_configuration=self._cfg(), return_rejections=True
        )
        assert len(rejections) == 2
        cols = sorted(r["source_column"] for r in rejections)
        assert cols == ["Latitud_Geo", "Longitud_Geo"]  # original source names captured

    def test_rejected_excluded_from_calculations(self):
        df = pd.DataFrame(
            [
                {
                    "Latitud_Geo": 1000.0, "Longitud_Geo": 2000.0, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": 15.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
                {
                    "Latitud_Geo": 1005.0, "Longitud_Geo": 2005.0, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": 120.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
            ]
        )
        out, _, _, _, rejections = procesar_pozos(
            df, geometry_configuration=self._cfg(), return_rejections=True
        )
        assert len(out) == 1
        assert len(rejections) == 1
        assert rejections[0]["error_code"] == "INCL_OUT_OF_RANGE"

    def test_rejection_disappears_after_data_fix(self):
        cfg = self._cfg()
        bad = pd.DataFrame(
            [
                {
                    "Latitud_Geo": None, "Longitud_Geo": 2000.0, "Nombre_Banco": 4000.0,
                    "Inclinacion_real": 15.0, "Azimuth_real": 90.0, "longitud_real": 12.0,
                    "Kilos_Cargados_real": 250.0,
                },
            ]
        )
        _, _, _, _, rejections = procesar_pozos(bad, geometry_configuration=cfg, return_rejections=True)
        assert len(rejections) == 1
        fixed = bad.copy()
        fixed.loc[0, "Latitud_Geo"] = 1000.0
        out, _, _, _, rejections = procesar_pozos(fixed, geometry_configuration=cfg, return_rejections=True)
        assert len(out) == 1
        assert rejections == []


# ---------------------------------------------------------------------------
# 3.2 (API surface) — response carries rejected_rows even when 0 accepted
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client(api_isolated_db):
    from fastapi.testclient import TestClient
    from api.main import app
    db_session = __import__("api.database", fromlist=["create_session"])
    with TestClient(app) as client:
        yield client, db_session


def _geometry_form() -> dict[str, str]:
    return {
        "geometry_user_confirmed": "true",
        "incl_convention": "from_vertical",
        "incl_sign_convention": "ABSOLUTE_VALUE",
        "az_convention": "CLOCKWISE_FROM_NORTH",
        "angle_unit": "degrees",
        "bench_height_m": "15.0",
    }


class TestApiResponseRejections:
    def test_zero_accepted_returns_422_with_rejected_rows(self, api_client):
        client, db = api_client
        sid = db.create_session()
        bad_csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            ",2000.0,4000,15.0,90.0,12.0\n"
            "1000.0,2000.0,4000,,,12.0\n"
        )
        data = {"session_id": sid, **_geometry_form()}
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(bad_csv.encode()), "text/csv")},
            data=data,
        )
        # 422 with structured body — never a bare 400.
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["n_holes"] == 0
        assert len(body["rejected_rows"]) >= 2  # multiple errors per row allowed
        codes = {r["error_code"] for r in body["rejected_rows"]}
        assert "INVALID_X" in codes or "INVALID_Latitud_Geo" in codes
        assert len(body["blocking_errors"]) >= 1
        assert body["geometry_configuration"]["geometry_user_confirmed"] is True

    def test_rejected_rows_survive_persistence(self, api_client):
        client, db = api_client
        sid = db.create_session()
        mixed_csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            "1000.0,2000.0,4000,15.0,90.0,12.0\n"
            ",2000.0,4000,15.0,90.0,12.0\n"
        )
        data = {"session_id": sid, **_geometry_form()}
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(mixed_csv.encode()), "text/csv")},
            data=data,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["n_holes"] == 1
        assert len(body["rejected_rows"]) == 1
        # Re-read the persisted settings — the rejections must survive.
        settings = db.get_settings(sid)
        assert "blast_upload_meta" in settings or "rejected_rows" in settings
        # ``save_blast_upload`` persists rejected_rows into the meta.
        meta = settings.get("blast_upload_meta", settings)
        # Either key works depending on where the caller stored it.
        assert settings.get("rejected_rows") is not None or meta.get("rejected_rows") is not None

    def test_no_geometry_confirmation_returns_400_with_structured_detail(self, api_client):
        client, db = api_client
        sid = db.create_session()
        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            "1000.0,2000.0,4000,15.0,90.0,12.0\n"
        )
        # geometry_user_confirmed absent → 400 with structured error.
        data = {
            "session_id": sid,
            "incl_convention": "from_vertical",
            "incl_sign_convention": "ABSOLUTE_VALUE",
            "az_convention": "CLOCKWISE_FROM_NORTH",
            "angle_unit": "degrees",
        }
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=data,
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error_code"] == "GEOMETRY_NOT_CONFIRMED"
        assert detail["details"]["state"] == "LEGACY_UNCONFIRMED"

    def test_radians_via_api(self, api_client):
        client, db = api_client
        sid = db.create_session()
        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            "1000.0,2000.0,4000,0.2618,1.5708,12.0\n"
        )
        data = {"session_id": sid, **_geometry_form()}
        data["angle_unit"] = "radians"
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=data,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["n_holes"] == 1


# ---------------------------------------------------------------------------
# 3.3 — SQLite initialization (order-independence)
# ---------------------------------------------------------------------------


class TestSQLiteInitialization:
    """The centralized fixture initializes the schema deterministically."""

    def test_isolated_db_creates_schema(self, api_isolated_db):
        import api.database as db
        # The table exists.
        conn = db.get_connection()
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        names = [r["name"] for r in rows]
        assert "sessions" in names
        assert "meshes" in names
        assert "results" in names

    def test_create_session_works_without_lifespan(self, api_isolated_db):
        # Remediación 3.3: previously raised OperationalError because the
        # schema was never created when the lifespan was skipped.
        import api.database as db
        sid = db.create_session()
        assert db.get_settings(sid) == {}


# ---------------------------------------------------------------------------
# 3.5 — ``angle_unit`` NameError / unified helper signature
# ---------------------------------------------------------------------------


class TestAngleUnitUnification:
    """The ``angle_unit`` variable is part of the helper signature / contract."""

    def test_no_dangling_angle_unit_in_module(self):
        # ``_process_blast_dataframe`` no longer exists — the helper was
        # replaced by the structured ``_build_upload_payload`` that takes
        # the contract directly.
        import api.routers.blast as mod
        assert not hasattr(mod, "_process_blast_dataframe"), (
            "_process_blast_dataframe was removed (it referenced the "
            "undefined angle_unit variable). The contract is the authority."
        )

    def test_contract_carries_angle_unit(self):
        cfg = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="ABSOLUTE_VALUE",
            inclination_unit="DEGREES",
            azimuth_convention="CLOCKWISE_FROM_NORTH",
            azimuth_unit="DEGREES",
        )
        assert cfg.angle_unit_canonical() == "degrees"
        cfg_rad = GeometryConfiguration(
            geometry_user_confirmed=True,
            inclination_convention="FROM_VERTICAL",
            inclination_sign_convention="ABSOLUTE_VALUE",
            inclination_unit="RADIANS",
            azimuth_convention="CLOCKWISE_FROM_NORTH",
            azimuth_unit="RADIANS",
        )
        assert cfg_rad.angle_unit_canonical() == "radians"


# ---------------------------------------------------------------------------
# 3.6 — Invalid required polygons fail-closed
# ---------------------------------------------------------------------------


class TestInvalidPolygonFailClosed:
    """An invalid required polygon blocks the calculation."""

    def _df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"X": [0.5, 1.5, 0.5, 1.5], "Y": [0.5, 0.5, 1.5, 1.5]}
        )

    def test_valid_polygon_works(self):
        poly = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]
        rep = compute_influence_area_report(self._df(), boundary_polygon=poly)
        assert float(rep["area_m2"].sum()) > 0
        assert (rep["area_status"] != "domain_blocked").all()

    def test_self_intersecting_blocks(self):
        # Butterfly / self-intersecting polygon. Note: shapely reports
        # area=0 for a butterfly, so the processor may classify it as
        # DEGENERATE_AREA_ZERO or SELF_INTERSECTING — both are valid
        # fail-closed responses.
        bad = [(0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0), (0.0, 0.0)]
        rep = compute_influence_area_report(self._df(), boundary_polygon=bad)
        assert (rep["area_status"] == "domain_blocked").all()
        assert (rep["area_m2"] == 0.0).all()
        assert rep["domain_error_code"].iloc[0] in (
            "DOMAIN_SELF_INTERSECTING_OR_INVALID",
            "DOMAIN_DEGENERATE_AREA_ZERO",
        )

    def test_zero_area_blocks(self):
        bad = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)]  # degenerate
        rep = compute_influence_area_report(self._df(), boundary_polygon=bad)
        assert (rep["area_status"] == "domain_blocked").all()
        assert rep["domain_error_code"].iloc[0] in (
            "DOMAIN_DEGENERATE_AREA_ZERO", "DOMAIN_TOO_FEW_VERTICES",
        )

    def test_empty_polygon_blocks(self):
        rep = compute_influence_area_report(self._df(), boundary_polygon=[])
        assert (rep["area_status"] == "domain_blocked").all()

    def test_too_few_vertices_blocks(self):
        rep = compute_influence_area_report(
            self._df(), boundary_polygon=[(0.0, 0.0), (1.0, 1.0)]
        )
        assert (rep["area_status"] == "domain_blocked").all()
        assert rep["domain_error_code"].iloc[0] == "DOMAIN_TOO_FEW_VERTICES"

    def test_non_finite_coords_block(self):
        bad = [(0.0, 0.0), (float("nan"), 1.0), (1.0, 1.0), (1.0, 0.0)]
        rep = compute_influence_area_report(self._df(), boundary_polygon=bad)
        assert (rep["area_status"] == "domain_blocked").all()
        assert rep["domain_error_code"].iloc[0] == "DOMAIN_NON_FINITE_OR_MALFORMED"

    def test_structured_diagnostic_persisted(self):
        bad = [(0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0), (0.0, 0.0)]
        rep = compute_influence_area_report(self._df(), boundary_polygon=bad)
        # ``domain_error`` is broadcast as a list per row; the first row
        # carries the structured diagnostic.
        first = rep["domain_error"].iloc[0]
        err = first[0] if isinstance(first, list) else first
        assert isinstance(err, dict)
        for key in (
            "error_code", "geometry_type", "validation_reason",
            "recommended_action", "affected_calculations",
        ):
            assert key in err
        assert err["affected_calculations"] == "Voronoi, área asignada, factor de carga"
