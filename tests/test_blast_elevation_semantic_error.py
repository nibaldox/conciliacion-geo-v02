"""Unknown/ambiguous elevation semantics must be a structured 4xx, never a 500."""

import io
import json

import pytest

import api.database as db
from core.calculo_tronadura import _resolve_z_collar_semantic, procesar_pozos
from core.geometry_contract import GeometryConfigurationError

import pandas as pd


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


def _csv(z_header):
    lines = [f"Latitud_Geo,Longitud_Geo,{z_header},Inclinacion_real,Azimuth_real,longitud_real,Kilos_Cargados_real,Taco_m"]
    for x, y in NON_COLLINEAR:
        lines.append(f"{x},{y},3100,15.0,90.0,12.0,150.0,1.5")
    return "\n".join(lines) + "\n"


def _column_map(z_source):
    return {
        "X": "Latitud_Geo",
        "Y": "Longitud_Geo",
        "Z_collar": z_source,
        "Incl": "Inclinacion_real",
        "Az": "Azimuth_real",
        "Len": "longitud_real",
        "Taco_m": "Taco_m",
        "Fila": None,
    }


def _upload(client, session_id, csv_text, z_source):
    data = {"session_id": session_id, **GEOMETRY, "column_map": json.dumps(_column_map(z_source))}
    return client.post(
        "/api/v1/blast/upload",
        files={"file": ("pozos.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
        data=data,
        headers={"x-session-id": session_id},
    )


@pytest.mark.parametrize("z_header", ["Z_QA", "Z"])
def test_unknown_or_ambiguous_z_semantic_returns_structured_4xx_without_persisting(client, z_header):
    session_id = db.create_session()
    resp = _upload(client, session_id, _csv(z_header), z_header)
    assert 400 <= resp.status_code < 500, resp.text
    blocking = resp.json()["blocking_errors"]
    assert len(blocking) == 1
    assert blocking[0]["error_code"] == "Z_COLLAR_SEMANTIC_REQUIRED"
    assert blocking[0]["details"]["source_column"] == z_header
    assert blocking[0]["details"]["allowed_values"] == ["bench_elevation", "collar_elevation"]
    assert not (db.get_settings(session_id) or {}).get("blast_holes")


def test_domain_resolver_still_raises_value_error_for_unknown_source():
    with pytest.raises(ValueError):
        _resolve_z_collar_semantic("Z_QA", None)
    with pytest.raises(GeometryConfigurationError) as info:
        _resolve_z_collar_semantic("Z_QA", None)
    assert info.value.error_code == "Z_COLLAR_SEMANTIC_REQUIRED"
    assert info.value.details["source_column"] == "Z_QA"
    assert info.value.details["allowed_values"] == ["bench_elevation", "collar_elevation"]


def test_domain_resolver_accepts_explicit_semantic_for_unknown_source():
    assert _resolve_z_collar_semantic("Z_QA", "bench_elevation") == "bench_elevation"
    assert _resolve_z_collar_semantic("Z_QA", "collar_elevation") == "collar_elevation"


def test_domain_resolver_keeps_recognised_aliases():
    assert _resolve_z_collar_semantic("Nombre_Banco", None) == "bench_elevation"
    assert _resolve_z_collar_semantic("Cota_Collar", None) == "collar_elevation"


def test_domain_resolver_invalid_explicit_value_is_distinct_from_missing():
    with pytest.raises(GeometryConfigurationError) as info:
        _resolve_z_collar_semantic("Z_QA", "bogus")
    assert info.value.error_code == "Z_COLLAR_SEMANTIC_INVALID"
    assert info.value.details["allowed_values"] == ["bench_elevation", "collar_elevation"]
