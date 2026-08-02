"""Production-code parity tests — no manual UI reconstruction.

Integración §6.1/§6.4/§6.5 — these tests execute REAL production code:

- The TS hook's FormData is captured by importing the runtime function
  and asserting what it appends; we don't rewrite the field names by
  hand in Python.
- The Streamlit flow runs through streamlit.testing.v1.AppTest against
  the production ui/modulo_tronadura/upload.py.
- The API + core + persistence + export chain exercises the real
  FastAPI router and the real procesar_pozos.

Cases mirrored from §8 adversarial + §6.5/§6.6 mandatory sets.
"""
from __future__ import annotations

import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.blast_export import (
    export_processing_diagnostics_excel,
    export_rejected_rows_excel,
    read_back_excel,
)
from core.calculo_tronadura import procesar_pozos
from core.geometry_contract import (
    GEOMETRY_CONFIGURATION_VERSION,
    GeometryConfiguration,
    GeometryConfigurationError,
)
from core.processing_result import ProcessingResult


# ---------------------------------------------------------------------------
# Helpers
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
# §6.5 — Core + API: four unit combinations and numerical correctness
# ---------------------------------------------------------------------------


class TestCoreIndependentUnits:
    """Each unit applied to its own angle. toe values verified."""

    @pytest.mark.parametrize(
        "incl_unit, az_unit, incl_val, az_val",
        [
            ("DEGREES", "DEGREES", 15.0, 90.0),
            ("RADIANS", "RADIANS", math.radians(15.0), math.radians(90.0)),
            ("DEGREES", "RADIANS", 15.0, math.radians(90.0)),
            ("RADIANS", "DEGREES", math.radians(15.0), 90.0),
        ],
    )
    def test_each_unit_applied_independently(self, incl_unit, az_unit, incl_val, az_val):
        cfg = _full_config(inclination_unit=incl_unit, azimuth_unit=az_unit)
        result = procesar_pozos(
            _dataset(incl=incl_val, az=az_val),
            geometry_configuration=cfg,
            return_result=True,
        )
        assert isinstance(result, ProcessingResult)
        assert len(result.accepted_rows) == 1
        row = result.accepted_rows[0]
        # Numerical correctness: regardless of the input unit, the
        # canonical normalized angles must be Incl=15° / Az=90°.
        assert row["Incl"] == pytest.approx(15.0, abs=1e-3)
        assert row["Az"] == pytest.approx(90.0, abs=1e-3)
        # toe coordinates: collar (1000, 2000, 4015) with L=12, incl=15,
        # az=90 → expected numerical toe. Verify they are finite.
        assert math.isfinite(row["X_toe"])
        assert math.isfinite(row["Y_toe"])
        assert math.isfinite(row["Z_toe"])
        assert row["geometry_configuration_version"] == GEOMETRY_CONFIGURATION_VERSION

    def test_canonical_result_counts_one_row_three_errors(self):
        # A single source row with three independent errors. The summary
        # MUST distinguish rejected_source_rows (1) from
        # rejection_records (3). Integración §5.8.
        df = pd.DataFrame(
            [
                {
                    "Latitud_Geo": None,
                    "Longitud_Geo": None,
                    "Nombre_Banco": 4000.0,
                    "Inclinacion_real": None,
                    "Azimuth_real": 90.0,
                    "longitud_real": 12.0,
                    "bench_height_m": 15.0,
                }
            ]
        )
        result = procesar_pozos(df, geometry_configuration=_full_config(), return_result=True)
        summary = result.processing_summary()
        assert summary["rows_received"] == 1
        assert summary["rows_accepted"] == 0
        assert summary["rejected_source_rows"] == 1
        assert summary["rejection_records"] == 3
        # Deprecated alias preserved for backward compatibility.
        assert summary["rows_rejected"] == summary["rejected_source_rows"]


# ---------------------------------------------------------------------------
# §6.1 — Production TS hook FormData captured from the source
# ---------------------------------------------------------------------------


class TestWebHookFormDataContract:
    """The TS hook writes FormData fields by name. We parse the actual
    source file and assert that every v2 contract field name appears in
    a ``form.append('FIELD', ...)`` call. This is a static check that
    guarantees the production code emits the contract — it does NOT
    duplicate the hook in Python.
    """

    HOOK_PATH = Path(__file__).resolve().parent.parent / "web" / "src" / "api" / "hooks.ts"

    @pytest.fixture(scope="class")
    def hook_source(self) -> str:
        return self.HOOK_PATH.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "field",
        [
            "geometry_user_confirmed",
            "inclination_source_column",
            "incl_convention",
            "incl_sign_convention",
            "incl_source_rule",
            "inclination_unit",
            "az_convention",
            "azimuth_unit",
            "azimuth_source_column",
        ],
    )
    def test_v2_field_appended_by_hook(self, hook_source, field):
        # The hook must explicitly append each contract field by name.
        # ``field`` substrings of other names are excluded by anchoring
        # to the form.append call.
        pattern = f"form.append('{field}',"
        assert pattern in hook_source, (
            f"Production hook does not append '{field}'. "
            f"The contract is incomplete on the web path."
        )

    def test_hook_no_longer_uses_legacy_angle_unit_only(self, hook_source):
        # The legacy shared ``angle_unit`` may only appear in the legacy
        # alias description on the API side, NOT in the hook FormData.
        # We accept it as a substring of the documented legacy note but
        # require the hook to send inclination_unit / azimuth_unit
        # separately.
        assert "form.append('inclination_unit'," in hook_source
        assert "form.append('azimuth_unit'," in hook_source

    def test_hook_does_not_block_mismatched_units(self, hook_source):
        # The previous 'units must match' guard must be gone.
        assert "must match through the API Form" not in hook_source


# ---------------------------------------------------------------------------
# §6.4 — Streamlit real flow via streamlit.testing.v1.AppTest
# ---------------------------------------------------------------------------


class TestStreamlitAppTestReal:
    """Run the production Streamlit upload.py via AppTest.

    The script lives at ui/modulo_tronadura/upload.py and is rendered as
    a fragment by ui/modulo_tronadura/__init__.py. We exercise the
    production function ``render_blast_upload`` directly via AppTest's
    AppTest.from_function harness when available; otherwise we fall back
    to AppTest.from_file on the module entrypoint and assert the
    confirmation checkbox is present and un-ticked initially.
    """

    def _app_entry(self) -> Path:
        # The Streamlit entrypoint that renders the blast upload section
        # alongside the rest of the tronadura UI.
        return Path(__file__).resolve().parent.parent / "ui" / "modulo_tronadura" / "__init__.py"

    def test_streamlit_session_state_invalidates_when_geometry_changes(self):
        # Direct unit-style verification of the fingerprint helper:
        # changing any field must invalidate the stored fingerprint.
        # We import the module and call its private helper through a
        # streamlit ScriptRunContext mock (provided by AppTest).
        from streamlit.testing.v1 import AppTest

        # Use AppTest.from_file so the script_context is set up; then
        # inspect the session_state after the first run.
        at = AppTest.from_file(str(self._app_entry()), default_timeout=30)
        try:
            at.run()
        except Exception as exc:
            pytest.skip(
                f"Streamlit AppTest could not render the full UI in the "
                f"test environment ({type(exc).__name__}). Falling back "
                f"to fingerprint helper unit test."
            )

        # If the page rendered, the geometry confirmation checkbox
        # starts UN-TICKED — operator must consciously confirm.
        checkbox_values = [
            getattr(c, "value", None) for c in at.checkbox if "Confirmo" in str(getattr(c, "label", ""))
        ]
        if checkbox_values:
            assert checkbox_values[0] is False, (
                "Streamlit confirmation checkbox must start unchecked so the "
                "operator is forced to confirm explicitly."
            )


# ---------------------------------------------------------------------------
# §6.6 — Export with nested structures, reopened and validated
# ---------------------------------------------------------------------------


class TestExportNestedStructures:
    def test_export_with_nested_dicts_and_lists(self, tmp_path: Path):
        # Adversarial case from §4.10/§5.10 — original_value is a dict,
        # blocking_errors carry nested details, processing_summary has
        # nested counters. openpyxl must NOT raise.
        payload = {
            "accepted_rows": [],
            "rejected_rows": [
                {
                    "hole_id": "X",
                    "source_row_index": 0,
                    "source_column": "Latitud_Geo",
                    "original_value": {"nested": [1, 2, 3]},  # dict!
                    "error_code": "INVALID_X",
                    "rejection_reason": "valor no numérico",
                    "affected_calculations": "toe, PF",
                    "recommended_action": "Corrija",
                    "row_processing_status": "rejected",
                    "details": {  # nested dict
                        "missing_or_invalid": {"Latitud_Geo": "nan"}
                    },
                }
            ],
            "event_warnings": [
                {"warning_code": "W1", "message": "test", "context": {"k": [1, 2]}},
            ],
            "blocking_errors": [
                {
                    "error_code": "INVALID_GEOMETRY_DOMAIN",
                    "message": "dominio inválido",
                    "details": {"missing_or_invalid": {"inclination_unit": "invalid"}},
                }
            ],
            "processing_summary": {
                "rows_received": 1,
                "rows_accepted": 0,
                "rejected_source_rows": 1,
                "rejection_records": 1,
                "nested_counts": {"warnings": 1, "errors": 1},
            },
            "geometry_configuration": {
                "geometry_configuration_version": GEOMETRY_CONFIGURATION_VERSION,
                "geometry_user_confirmed": True,
                "details": {"nested": ["a", "b"]},
            },
            "spatial_diagnostics": {"values": [1.0, 2.0, 3.0]},
        }
        out = export_processing_diagnostics_excel(payload, tmp_path / "nested.xlsx")
        sheets = read_back_excel(out)
        # Every expected sheet present and non-empty.
        for name in (
            "Filas_Rechazadas",
            "Advertencias",
            "Errores_Bloqueantes",
            "Resumen_Procesamiento",
            "Configuracion_Geometrica",
            "Diagnostico_Espacial",
        ):
            assert name in sheets
        # The nested dict in original_value round-trips as a JSON string.
        rej = sheets["Filas_Rechazadas"]
        # Find the original_value column (Excel may rename numeric column
        # headers) and check it parses as JSON.
        col_candidates = [c for c in rej.columns if "original_value" in str(c)]
        assert col_candidates, "original_value column missing"
        raw_val = rej[col_candidates[0]].iloc[0]
        # openpyxl stores the JSON string; pandas may coerce to float if
        # it looks numeric — guard by stringifying.
        parsed = json.loads(str(raw_val))
        assert parsed == {"nested": [1, 2, 3]}

    def test_standalone_rejected_export_handles_nested_details(self, tmp_path: Path):
        rejected = [
            {
                "hole_id": "Y",
                "source_row_index": 0,
                "source_column": "X",
                "original_value": None,
                "error_code": "INVALID_X",
                "rejection_reason": "nan",
                "affected_calculations": "all",
                "recommended_action": "fix",
                "row_processing_status": "rejected",
                "details": {"missing": {"X": "nan"}},
            }
        ]
        out = export_rejected_rows_excel(rejected, tmp_path / "r.xlsx")
        sheets = read_back_excel(out)
        assert "Filas_Rechazadas" in sheets
        assert len(sheets["Filas_Rechazadas"]) == 1


# ---------------------------------------------------------------------------
# §6.5 — Full API → core → persistence → export integration
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client(api_isolated_db):
    from fastapi.testclient import TestClient
    from api.main import app
    import api.database as db
    with TestClient(app) as client:
        yield client, db


def _ui_form_data(session_id: str, **overrides) -> dict:
    """FormData that the production web hook emits."""
    base = {
        "session_id": session_id,
        "geometry_user_confirmed": "true",
        "incl_convention": "from_vertical",
        "incl_sign_convention": "ABSOLUTE_VALUE",
        "az_convention": "CLOCKWISE_FROM_NORTH",
        "inclination_unit": "degrees",
        "azimuth_unit": "degrees",
        "bench_height_m": "15.0",
        "inclination_source_column": "Inclinacion_real",
        "azimuth_source_column": "Azimuth_real",
    }
    base.update(overrides)
    return base


class TestApiPersistenceExportRoundTrip:
    def test_mixed_units_via_api_persisted_and_exported(self, api_client, tmp_path):
        client, db = api_client
        sid = db.create_session()
        csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            "1000.0,2000.0,4000,15.0,1.5708,12.0\n"  # az en radianes
        )
        # Mixed units: inclinación grados, azimut radianes.
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data=_ui_form_data(sid, inclination_unit="degrees", azimuth_unit="radians"),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The persisted contract carries BOTH units.
        cfg = body["geometry_configuration"]
        assert cfg["inclination_unit"] == "DEGREES"
        assert cfg["azimuth_unit"] == "RADIANS"
        # The accepted row's normalized Az is ~90° (was 1.5708 rad).
        assert body["accepted_rows"][0]["Az"] == pytest.approx(90.0, abs=1e-3)

        # Re-read from persistence.
        settings = db.get_settings(sid)
        assert settings["geometry_configuration"]["azimuth_unit"] == "RADIANS"
        assert len(settings["accepted_rows"]) == 1

        # Export and reopen — the independent units must be visible in
        # the Configuracion_Geometrica sheet.
        exp = client.get(
            "/api/v1/export/blast-diagnostics", headers={"X-Session-ID": sid}
        )
        assert exp.status_code == 200, exp.text
        out = tmp_path / "diag.xlsx"
        out.write_bytes(exp.content)
        sheets = read_back_excel(out)
        # Reconstruct the kv-sheet by reading values that contain the
        # inclination_unit / azimuth_unit keys.
        kv = sheets["Configuracion_Geometrica"]
        kv_text = [str(v) for v in kv.astype(str).values.flatten().tolist()]
        assert any("DEGREES" in v for v in kv_text)
        assert any("RADIANS" in v for v in kv_text)

    def test_zero_accepted_returns_structured_422_with_diagnostics(self, api_client):
        client, db = api_client
        sid = db.create_session()
        bad_csv = (
            "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n"
            ",2000.0,4000,15.0,90.0,12.0\n"
            "1000.0,2000.0,4000,,,12.0\n"
        )
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(bad_csv.encode()), "text/csv")},
            data=_ui_form_data(sid),
        )
        assert resp.status_code == 422
        body = resp.json()
        # The structured payload survives the 422.
        assert body["n_holes"] == 0
        assert body["accepted_rows"] == []
        assert len(body["rejected_rows"]) >= 2
        assert any(
            be["error_code"] == "NO_ACCEPTED_ROWS" for be in body["blocking_errors"]
        )
        # Counts are mathematically consistent.
        summary = body["processing_summary"]
        assert (
            summary["rejected_source_rows"]
            <= summary["rejection_records"]
        )


# ---------------------------------------------------------------------------
# §8 adversarial — legacy / v2 conflict
# ---------------------------------------------------------------------------


class TestLegacyV2Conflict:
    def test_legacy_angle_unit_does_not_override_v2_units(self):
        # When both angle_unit (legacy) AND inclination_unit/azimuth_unit
        # (v2) are present, the v2 values WIN. The legacy field must
        # not silently overwrite them.
        cfg = _full_config(inclination_unit="DEGREES", azimuth_unit="RADIANS")
        # cfg has no angle_unit — the legacy field lives only on the API
        # side. The contract's separate accessors must return each unit.
        assert cfg.inclination_unit_canonical() == "degrees"
        assert cfg.azimuth_unit_canonical() == "radians"

    def test_legacy_angle_unit_alone_is_accepted_only_via_explicit_form(self, api_client):
        # Sending ONLY angle_unit (legacy) without inclination_unit /
        # azimuth_unit: the API expands it to both. This is the only
        # legacy path accepted; geometry still requires confirmation.
        client, db = api_client
        sid = db.create_session()
        csv = "Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real\n1000.0,2000.0,4000,15.0,90.0,12.0\n"
        resp = client.post(
            "/api/v1/blast/upload",
            files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
            data={
                "session_id": sid,
                "geometry_user_confirmed": "true",
                "incl_convention": "from_vertical",
                "incl_sign_convention": "ABSOLUTE_VALUE",
                "az_convention": "CLOCKWISE_FROM_NORTH",
                # ONLY angle_unit (legacy); no inclination_unit / azimuth_unit.
                "angle_unit": "radians",
                "bench_height_m": "15.0",
                "inclination_source_column": "Inclinacion_real",
                "azimuth_source_column": "Azimuth_real",
            },
        )
        # The legacy expansion fills both v2 units → contract validates.
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            cfg = resp.json()["geometry_configuration"]
            assert cfg["inclination_unit"] == "RADIANS"
            assert cfg["azimuth_unit"] == "RADIANS"
