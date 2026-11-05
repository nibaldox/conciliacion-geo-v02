"""Blast upload explicit date column/format contract (date_source_column + date_format)."""

import inspect
import io
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

import api.database as db
from api.routers import blast as blast_router
from core.blast_dates import (
    DATE_FORMATS,
    DATE_STATUS_INVALID,
    DATE_STATUS_MISSING,
    DATE_STATUS_VALID,
    normalize_blast_date,
    normalize_blast_dates,
)


@pytest.fixture(autouse=True)
def isolated_db(api_isolated_db):
    yield


@pytest.fixture()
def client(api_test_client):
    return api_test_client


GEOMETRY = {
    "geometry_user_confirmed": "true",
    "incl_convention": "from_vertical",
    "incl_sign_convention": "ABSOLUTE_VALUE",
    "az_convention": "CLOCKWISE_FROM_NORTH",
    "angle_unit": "degrees",
    "bench_height_m": "15.0",
    "incl_source_column": "Inclinacion_real",
    "az_source_column": "Azimuth_real",
}

NON_COLLINEAR = [(1000.0, 2000.0), (1010.0, 2000.0), (1000.0, 2010.0), (1012.0, 2022.0)]


def _csv(date_header, dates):
    lines = [f"Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real,Kilos_Cargados_real,Taco_m,{date_header}"]
    for (x, y), value in zip(NON_COLLINEAR, dates):
        lines.append(f"{x},{y},100,15.0,90.0,12.0,150.0,1.5,{value}")
    return "\n".join(lines) + "\n"


def _xlsx(header, values):
    wb = Workbook()
    ws = wb.active
    ws.title = "Pozos"
    ws.append(["Latitud_Geo", "Longitud_Geo", "Nombre_Banco", "Inclinacion_real", "Azimuth_real", "longitud_real", "Kilos_Cargados_real", "Taco_m", header])
    for (x, y), value in zip(NON_COLLINEAR, values):
        ws.append([x, y, 100, 15.0, 90.0, 12.0, 150.0, 1.5, value])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _upload(client, session_id, content, filename="pozos.csv", extra=None):
    data = {"session_id": session_id, **GEOMETRY, **(extra or {})}
    mime = "text/csv" if filename.endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return client.post(
        "/api/v1/blast/upload",
        files={"file": (filename, io.BytesIO(payload), mime)},
        data=data,
        headers={"x-session-id": session_id},
    )


def _holes(session_id):
    return db.get_settings(session_id)["blast_holes"]


def test_core_normalizes_iso_dmy_mdy_and_statuses():
    assert DATE_FORMATS == ("ISO", "DMY", "MDY")
    assert normalize_blast_date("2026-05-04", "ISO") == ("2026-05-04", "2026-05-04", DATE_STATUS_VALID)
    assert normalize_blast_date("2026-05-04T08:30:00", "ISO")[0] == "2026-05-04"
    assert normalize_blast_date(pd.Timestamp("2026-05-04 10:00"), "ISO")[0] == "2026-05-04"
    assert normalize_blast_date(datetime(2026, 5, 4), "DMY")[0] == "2026-05-04"
    assert normalize_blast_date("04/05/2026", "DMY")[0] == "2026-05-04"
    assert normalize_blast_date("04/05/2026", "MDY")[0] == "2026-04-05"
    assert normalize_blast_date("31/02/2026", "DMY") == (None, "31/02/2026", DATE_STATUS_INVALID)
    assert normalize_blast_date("2026-05-04", "DMY") == (None, "2026-05-04", DATE_STATUS_INVALID)
    assert normalize_blast_date(46000.0, "ISO") == (None, "46000.0", DATE_STATUS_INVALID)
    assert normalize_blast_date("", "DMY") == (None, None, DATE_STATUS_MISSING)
    assert normalize_blast_date(None, "MDY") == (None, None, DATE_STATUS_MISSING)
    assert normalize_blast_date(np.nan, "ISO") == (None, None, DATE_STATUS_MISSING)
    with pytest.raises(ValueError):
        normalize_blast_date("04/05/2026", "YMD")


def test_core_column_frame_reports_counts():
    frame = normalize_blast_dates(pd.Series(["04/05/2026", None, "x", "10/05/2026"]), "DMY")
    assert frame["fecha_tronadura"].tolist() == ["2026-05-04", None, None, "2026-05-10"]
    assert frame["date_status"].tolist() == ["VALID", "MISSING", "INVALID", "VALID"]


def test_helper_keyword_only_signature():
    params = inspect.signature(blast_router._build_upload_payload).parameters
    assert params["date_source_column"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["date_source_column"].default is None
    assert params["date_format"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["date_format"].default is None


def test_csv_selected_header_with_spaces_dmy_persists_provenance(client):
    session_id = db.create_session()
    content = _csv("Fecha Voladura ", ["04/05/2026", "", "31/02/2026", "10/05/2026"])
    resp = _upload(client, session_id, content, extra={"date_source_column": "Fecha Voladura ", "date_format": "DMY"})
    assert resp.status_code in (200, 422), resp.text
    holes = _holes(session_id)
    assert [h["fecha_tronadura"] for h in holes] == ["2026-05-04", None, None, "2026-05-10"]
    assert [h["date_status"] for h in holes] == ["VALID", "MISSING", "INVALID", "VALID"]
    assert holes[0]["date_original_value"] == "04/05/2026"
    assert holes[2]["date_original_value"] == "31/02/2026"
    assert all(h["date_source_column"] == "Fecha Voladura " for h in holes)
    assert all(h["date_format"] == "DMY" for h in holes)
    codes = {w["warning_code"] for w in resp.json()["event_warnings"]}
    assert {"DATE_MISSING", "DATE_INVALID"} <= codes
    assert resp.json()["n_holes"] == 4


def test_xlsx_mdy_with_excel_datetime_cell(client):
    session_id = db.create_session()
    content = _xlsx("Fecha", [datetime(2026, 5, 4), "04/05/2026", None, "99/99/2026"])
    resp = _upload(client, session_id, content, filename="pozos.xlsx", extra={"date_source_column": "Fecha", "date_format": "MDY"})
    assert resp.status_code in (200, 422), resp.text
    holes = _holes(session_id)
    assert [h["fecha_tronadura"] for h in holes] == ["2026-05-04", "2026-04-05", None, None]
    assert [h["date_status"] for h in holes] == ["VALID", "VALID", "MISSING", "INVALID"]
    assert holes[0]["date_original_value"].startswith("2026-05-04")


@pytest.mark.parametrize(
    ("extra", "header", "code"),
    [
        ({"date_source_column": "Fecha"}, "Fecha", "DATE_FORMAT_REQUIRED"),
        ({"date_source_column": "Fecha", "date_format": "YMD"}, "Fecha", "DATE_FORMAT_INVALID"),
        ({"date_source_column": "No existe", "date_format": "DMY"}, "Fecha", "DATE_COLUMN_NOT_FOUND"),
        ({"date_format": "DMY"}, "Fecha", "DATE_COLUMN_REQUIRED"),
    ],
)
def test_invalid_date_contract_is_rejected_before_persistence(client, extra, header, code):
    session_id = db.create_session()
    content = _csv(header, ["04/05/2026", "04/05/2026", "04/05/2026", "04/05/2026"])
    extra = {k: v for k, v in extra.items() if v is not None}
    resp = _upload(client, session_id, content, extra=extra)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["error_code"] == code
    assert not (db.get_settings(session_id) or {}).get("blast_holes")


def test_date_column_conflicting_with_column_map_is_rejected(client):
    session_id = db.create_session()
    content = _csv("Fecha", ["04/05/2026"] * 4)
    column_map = {
        "X": "Latitud_Geo", "Y": "Longitud_Geo", "Z_collar": "Nombre_Banco", "Incl": "Inclinacion_real",
        "Az": "Azimuth_real", "Len": "longitud_real", "Taco_m": "Taco_m", "Fila": None,
    }
    import json
    resp = _upload(
        client, session_id, content,
        extra={"column_map": json.dumps(column_map), "date_source_column": "Taco_m", "date_format": "DMY"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["error_code"] == "DATE_COLUMN_MAP_CONFLICT"
    assert not (db.get_settings(session_id) or {}).get("blast_holes")


def test_legacy_upload_without_date_fields_is_unchanged(client):
    session_id = db.create_session()
    content = _csv("fecha_tronadura", ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"])
    resp = _upload(client, session_id, content)
    assert resp.status_code in (200, 422), resp.text
    holes = _holes(session_id)
    assert [h["fecha_tronadura"] for h in holes] == ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"]
    assert all("date_status" not in h and "date_source_column" not in h for h in holes)


def test_upload_persists_and_temporal_cut_consumes_selected_dates(client):
    session_id = db.create_session()
    db.save_sections(session_id, [{"name": "S-01", "origin": [1000.0, 2000.0], "azimuth": 0.0, "length": 200.0, "sector": "A"}])
    db.save_results(session_id, [{"section": "S-01", "delta_crest": 0.3}])
    content = _csv("Fecha Voladura", ["01/05/2026", "04/05/2026", "", "10/05/2026"])
    resp = _upload(client, session_id, content, extra={"date_source_column": "Fecha Voladura", "date_format": "DMY"})
    assert resp.status_code in (200, 422), resp.text

    holes_3d = client.get("/api/v1/blast/holes/3d", headers={"x-session-id": session_id})
    assert holes_3d.status_code == 200, holes_3d.text
    attrs = [h["attributes"].get("fecha_tronadura") for h in holes_3d.json()["holes"]]
    assert attrs == ["2026-05-01", "2026-05-04", None, "2026-05-10"]

    corr = client.get(
        "/api/v1/process/blast-correlation?survey_date=2026-05-10",
        headers={"x-session-id": session_id},
    )
    assert corr.status_code == 200, corr.text
    tf = corr.json()["temporal_filter"]
    assert tf["effective_cutoff_date"] == "2026-05-03"
    assert (tf["included"], tf["excluded"], tf["missing"], tf["total"]) == (1, 2, 1, 4)

    dmg = client.get(
        "/api/v1/process/blast-correlation/damage-model?survey_date=2026-05-10",
        headers={"x-session-id": session_id},
    )
    assert dmg.status_code == 200, dmg.text
    assert dmg.json()["temporal_filter"] == tf


@pytest.mark.parametrize(
    "text",
    [
        "2026-05-04T08:30:00Z",
        "2026-05-04T08:30:00+00:00",
        "2026-05-04T23:30:00-03:00",
        "2026-05-04T23:30:00-0300",
        "2026-05-04 08:30:00+08:00",
        "2026-05-04T08:30:00.123-03:00",
        "2026-05-04T00:00:00+23:59",
        "2026-05-04T23:59:59-23:59",
        "2026-05-04T08:30+01:00",
    ],
)
def test_core_iso_datetime_with_offset_keeps_source_calendar_date(text):
    assert normalize_blast_date(text, "ISO") == ("2026-05-04", text, DATE_STATUS_VALID)


@pytest.mark.parametrize(
    "text",
    [
        "2026-05-04T08:30:00+24:00",
        "2026-05-04T08:30:00+08:60",
        "2026-05-04T08:30:00+08:99",
        "2026-05-04T08:30:00+2500",
        "2026-05-04T08:30:00+08",
        "2026-05-04T08:30:00+8:00",
        "2026-05-04T08:30:00 +08:00",
        "2026-05-04T08:30:00ZZ",
        "2026-05-04T08:30:00-03:00:00",
        "2026-05-04Z",
        "2026-05-04+08:00",
        "2026-02-30T08:30:00Z",
        "2026-05-04T25:00:00Z",
        "2026-05-04T08:61:00-03:00",
    ],
)
def test_core_malformed_or_invalid_offsets_are_rejected(text):
    assert normalize_blast_date(text, "ISO") == (None, text, DATE_STATUS_INVALID)


def test_core_offset_suffix_is_not_accepted_for_dmy_or_mdy():
    assert normalize_blast_date("04/05/2026T08:30Z", "DMY")[2] == DATE_STATUS_INVALID
    assert normalize_blast_date("04/05/2026T08:30-03:00", "MDY")[2] == DATE_STATUS_INVALID


def test_http_csv_and_xlsx_iso_offsets_persist_and_feed_temporal_cut(client):
    values = ["2026-05-01T08:00:00Z", "2026-05-04T23:30:00-03:00", "", "2026-05-10T12:00:00+08:00"]
    expected_dates = ["2026-05-01", "2026-05-04", None, "2026-05-10"]
    expected_status = ["VALID", "VALID", "MISSING", "VALID"]

    session_id = db.create_session()
    db.save_sections(session_id, [{"name": "S-01", "origin": [1000.0, 2000.0], "azimuth": 0.0, "length": 200.0, "sector": "A"}])
    db.save_results(session_id, [{"section": "S-01", "delta_crest": 0.3}])
    resp = _upload(
        client, session_id, _csv("Fecha Voladura", values),
        extra={"date_source_column": "Fecha Voladura", "date_format": "ISO"},
    )
    assert resp.status_code in (200, 422), resp.text
    holes = _holes(session_id)
    assert [h["fecha_tronadura"] for h in holes] == expected_dates
    assert [h["date_status"] for h in holes] == expected_status
    assert [h["date_original_value"] for h in holes[:2]] == values[:2]
    assert all(h["date_format"] == "ISO" for h in holes)
    assert "DATE_INVALID" not in {w["warning_code"] for w in resp.json()["event_warnings"]}

    corr = client.get(
        "/api/v1/process/blast-correlation?survey_date=2026-05-10",
        headers={"x-session-id": session_id},
    )
    assert corr.status_code == 200, corr.text
    tf = corr.json()["temporal_filter"]
    assert tf["effective_cutoff_date"] == "2026-05-03"
    assert (tf["included"], tf["excluded"], tf["missing"], tf["total"]) == (1, 2, 1, 4)

    xlsx_session = db.create_session()
    xlsx_values = ["2026-05-01T08:00:00Z", "2026-05-04T23:30:00-03:00", None, "2026-05-10T12:00:00+08:00"]
    resp = _upload(
        client, xlsx_session, _xlsx("Fecha", xlsx_values), filename="pozos.xlsx",
        extra={"date_source_column": "Fecha", "date_format": "ISO"},
    )
    assert resp.status_code in (200, 422), resp.text
    holes = _holes(xlsx_session)
    assert [h["fecha_tronadura"] for h in holes] == expected_dates
    assert [h["date_status"] for h in holes] == expected_status
    assert holes[1]["date_original_value"] == "2026-05-04T23:30:00-03:00"
