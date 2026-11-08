import io

import pandas as pd
import pytest

import api.database as db
from core.blast_metrics import enrich_blast_dataframe
from core.calculo_tronadura import procesar_pozos


ALGORITHM_VERSION = "blast-auditable.v1"


def _row(**changes):
    row = dict(
        id_pozo="H1", Nombre_Malla_Original="M1", Blast="B1",
        X=1.0, Y=2.0, Z_collar=100.0, Len=10.0, Incl=0.0, Az=0.0,
        Kilos_Cargados_real=100.0, Tipo_Explosivo="ANFO", Taco_m=2.0,
        fecha_tronadura="2026-01-01",
    )
    row.update(changes)
    return row


def _accepted_rows(rows):
    frame = pd.DataFrame(rows).rename(columns={
        "Z_collar": "Cota_Collar",
        "Incl": "Inclinacion_real",
        "Az": "Azimuth_real",
        "Len": "longitud_real",
    })
    result = procesar_pozos(
        frame,
        geometry_user_confirmed=True,
        incl_convention="from_vertical",
        z_collar_semantic="collar_elevation",
        return_result=True,
    )
    return result.accepted_rows


def _save_holes(session_id, records):
    db.save_settings(session_id, {
        "blast_algorithm_version": ALGORITHM_VERSION,
        "blast_holes": records,
    })


def test_pipeline_records_user_source_rows_per_deck():
    rows = _accepted_rows([
        _row(source_row_index=991, Kilos_Cargados_real=19.0, Tipo_Explosivo="ANFO"),
        _row(source_row_index=992, Kilos_Cargados_real=81.0, Tipo_Explosivo="PIREX 50"),
    ])

    assert len(rows) == 1
    assert rows[0]["source_row_indices"] == [0, 1]
    assert rows[0]["source_row_indices_user"] == [991, 992]
    assert rows[0]["source_row_index_user"] == 991


def test_detail_exposes_user_source_rows(client):
    session_id = db.create_session()
    _save_holes(session_id, [{
        "id_pozo": "H1",
        "X": 1.0, "Y": 2.0, "Z_collar": 100.0, "Len": 10.0,
        "Kilos_Cargados_real": 100.0, "Taco_m": 2.0,
        "source_row_index": 0,
        "source_row_indices": [0, 2],
        "source_row_indices_user": [991, 993],
        "decks": [
            {"kg": 19.0, "explosive": "ANFO", "taco_m": 2.0, "source_row_index": 0},
            {"kg": 81.0, "explosive": "PIREX 50", "taco_m": 2.0, "source_row_index": 2},
        ],
    }])

    response = client.get(
        f"/api/v1/blast/{session_id}/holes/H1",
        headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_row_indices"] == [0, 2]
    assert body["source_row_index_user"] == [991, 993]


def test_detail_without_user_rows_reports_null(client):
    session_id = db.create_session()
    _save_holes(session_id, [{"id_pozo": "LEGACY", "X": 1.0, "Y": 2.0, "source_row_index": 0}])

    response = client.get(
        f"/api/v1/blast/{session_id}/holes/LEGACY",
        headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200, response.text
    assert response.json()["source_row_index_user"] is None


def test_holes_3d_exposes_user_source_rows(client):
    session_id = db.create_session()
    _save_holes(session_id, [{
        "id_pozo": "H1",
        "X": 1.0, "Y": 2.0, "Z_collar": 100.0, "X_toe": 1.0, "Y_toe": 2.0, "Z_toe": 90.0,
        "Len": 10.0, "source_row_index": 0,
        "source_row_indices": [0, 1],
        "source_row_indices_user": [991, 992],
    }])

    response = client.get(
        "/api/v1/blast/holes/3d",
        headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200, response.text
    holes = response.json()["holes"]
    assert holes[0]["source_row_index_user"] == [991, 992]


def test_loaded_column_status_is_explicit_when_stemming_exceeds_length():
    frame = pd.DataFrame({
        "Kilos_Cargados_real": [100.0, 100.0],
        "Len": [10.0, 10.0],
        "Taco_m": [12.0, 2.0],
    })

    enriched = enrich_blast_dataframe(frame)

    assert enriched.loc[0, "altura_carga_warning"] == "stemming_exceeds_length"
    assert enriched.loc[0, "kg_per_meter_loaded_column_status"] == "stemming_exceeds_length"
    assert pd.isna(enriched.loc[0, "kg_per_meter_loaded_column"])
    assert enriched.loc[1, "kg_per_meter_loaded_column_status"] is None


def test_detail_propagates_loaded_column_status_from_pipeline(client):
    accepted = _accepted_rows([_row(Taco_m=12.0)])
    assert accepted[0]["kg_per_meter_loaded_column_status"] == "stemming_exceeds_length"

    session_id = db.create_session()
    _save_holes(session_id, accepted)

    response = client.get(
        f"/api/v1/blast/{session_id}/holes/H1",
        headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["altura_carga_warning"] == "stemming_exceeds_length"
    assert body["kg_per_meter_loaded_column_status"] == "stemming_exceeds_length"
    assert body["kg_per_meter_loaded_column"] is None


def test_preview_does_not_report_session_data_status(client):
    response = client.post(
        "/api/v1/blast/preview",
        files={"file": ("pozos.csv", io.BytesIO(b"id_pozo,Len\nH1,10\n"), "text/csv")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["headers"] == ["id_pozo", "Len"]
    assert "data_status" not in body
    assert "algorithm_version" not in body
