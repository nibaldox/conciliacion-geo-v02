import io

import pandas as pd
import pytest

import api.database as db
from api.routers.process import _blast_histogram_values


def test_legacy_status_and_literal_id_and_detail(client):
    sid = db.create_session()
    headers = {'X-Session-ID': sid}
    db.save_settings(sid, {'blast_holes': [
        {'id_pozo': 'OLD', 'hole_id': '0', 'decks': [{'kg': 19, 'explosive': 'ANFO', 'taco_m': 2, 'source_row_index': 0}], 'explosive_mix': {'ANFO': 19}, 'source_row_indices': [0, 1], 'duplicate_rows_removed': 1, 'area_influence_m2': 7, 'pf_voronoi_bench_g_per_ton': None, 'pf_voronoi_bench_status': 'MISSING_FOOTPRINT'},
        {'id_pozo': 'H-2', 'X': 2},
    ]})
    for path in [f'/api/v1/blast/{sid}/summary', f'/api/v1/blast/{sid}/holes', '/api/v1/blast/holes/3d', '/api/v1/blast/definitions', '/api/v1/process/blast-correlation', '/api/v1/process/blast-correlation/damage-model']:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()['data_status'] == 'legacy_reimport_required'
        assert response.json()['algorithm_version'] is None
    summary = client.get(f'/api/v1/blast/{sid}/summary', headers=headers).json()
    assert summary['consolidation_report'] is None
    holes = client.get(f'/api/v1/blast/{sid}/holes', headers=headers).json()['holes']
    assert [h['hole_id'] for h in holes] == ['OLD', 'H-2']
    detail = client.get(f'/api/v1/blast/{sid}/holes/OLD', headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body['hole_id'] == 'OLD'
    assert body['decks'][0]['explosive'] == 'ANFO'
    assert body['explosive_mix'] == {'ANFO': 19}
    assert body['source_row_indices'] == [0, 1]
    assert body['duplicate_rows_removed'] == 1
    assert body['area_influence_m2'] == 7
    assert body['pf_voronoi_bench_status'] == 'MISSING_FOOTPRINT'


def test_detail_exposes_principal_area_provenance_and_ambiguous_ids(client):
    sid = db.create_session()
    headers = {'X-Session-ID': sid}
    db.save_settings(sid, {'blast_holes': [
        {'id_pozo': 'DUP', 'source_row_index': 0, 'pf_voronoi_bench_area_m2': 12, 'pf_voronoi_bench_area_status': 'VALID', 'pf_voronoi_bench_source': 'footprint', 'pf_voronoi_bench_warnings': ['warning']},
        {'id_pozo': 'DUP', 'source_row_index': 1},
    ]})
    response = client.get(f'/api/v1/blast/{sid}/holes/DUP', headers=headers)
    assert response.status_code == 409
    row_id = response.json()['detail']['row_ids'][0]
    response = client.get(f'/api/v1/blast/{sid}/holes/DUP', params={'row_id': row_id}, headers=headers)
    assert response.status_code == 200
    assert response.json()['pf_voronoi_bench_area_m2'] == 12
    assert response.json()['pf_voronoi_bench_area_status'] == 'VALID'
    assert response.json()['pf_voronoi_bench_source'] == 'footprint'
    assert response.json()['pf_voronoi_bench_warnings'] == ['warning']


def test_invalid_loaded_column_not_in_histogram():
    frame = pd.DataFrame({'Len': [10, 10], 'Taco_m': [12, 10]})
    assert _blast_histogram_values(frame)[1] == [0.0]


def test_histogram_rejects_stale_invalid_column_values():
    frame = pd.DataFrame({'Len': [10, 10, 10], 'Taco_m': [12, 10, 2], 'altura_carga_m': [0, 0, 8],
                          'kg_per_meter_loaded_column': [0, None, 2]})
    _, heights, loaded = _blast_histogram_values(frame)
    assert heights == [0, 8]
    assert loaded == [2]


def test_invalid_loaded_column_fallback_returns_null():
    from api.routers.blast import _compute_descarga_series
    frame = pd.DataFrame({'Len': [10, 10, 10], 'Taco_m': [12, 10, -1]})
    result = _compute_descarga_series(frame)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == 0
    assert pd.isna(result.iloc[2])


def test_correlation_propagates_partial_energy_and_mass_counts(monkeypatch):
    from api.routers import process
    from core.blast_correlation import BlastCorrelationRow
    row = BlastCorrelationRow(section_name='S', num_wells=2, total_kg=float('nan'), mean_abs_deviation=0,
                              energy_known_mj=42, n_kg_known=1, n_kg_missing=1)
    monkeypatch.setattr(process, '_resolve_blast_correlation_rows',
                        lambda *args: ([row], [{}], 5, {}, ([], [], [])))
    monkeypatch.setattr(process.db, 'get_settings', lambda sid: {})
    result = process._build_blast_correlation_sync('s', None).model_dump()['rows'][0]
    assert result['total_kg'] is None
    assert result['energy_known_mj'] == 42
    assert result['n_kg_known'] == 1
    assert result['n_kg_missing'] == 1


def test_absent_hole_identifier_is_not_an_ordinal(client):
    sid = db.create_session()
    db.save_settings(sid, {'blast_holes': [{'X': 1}, {'X': 2}]})
    holes = client.get(f'/api/v1/blast/{sid}/holes', headers={'X-Session-ID': sid}).json()['holes']
    assert [hole['hole_id'] for hole in holes] == ['sin dato', 'sin dato']


def test_projected_profile_reports_legacy_status(client):
    sid = db.create_session()
    response = client.get('/api/v1/process/profiles/0/blast-holes', headers={'X-Session-ID': sid})
    assert response.status_code == 200
    assert response.json()['data_status'] == 'legacy_reimport_required'
    assert response.json()['algorithm_version'] is None


def test_upload_marks_version_current(client):
    sid = db.create_session()
    csv = ('Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real,Kilos_Cargados_real,Taco_m,id_pozo,Nombre_Malla_Original,Tipo_Explosivo,fecha_tronadura\n'
           '1,2,100,0,0,10,19,2,H1,M1,ANFO,2026-01-01\n')
    form = {'session_id': sid, 'geometry_user_confirmed': 'true', 'incl_convention': 'from_vertical', 'incl_sign_convention': 'ABSOLUTE_VALUE', 'az_convention': 'CLOCKWISE_FROM_NORTH', 'angle_unit': 'degrees', 'bench_height_m': '15', 'incl_source_column': 'Inclinacion_real', 'az_source_column': 'Azimuth_real'}
    response = client.post('/api/v1/blast/upload', files={'file': ('p.csv', io.BytesIO(csv.encode()), 'text/csv')}, data=form, headers={'X-Session-ID': sid})
    assert response.status_code == 200, response.text
    assert response.json()['data_status'] == 'current'
    assert response.json()['algorithm_version'] == 'blast-auditable.v1'
    assert db.get_settings(sid)['blast_algorithm_version'] == 'blast-auditable.v1'


def test_consolidation_schema_is_typed(client):
    spec = client.get('/openapi.json').json()['components']['schemas']
    assert spec['BlastUploadResponse']['properties']['consolidation_report'].get('$ref', '').endswith('/BlastConsolidationReport')
    report = spec['BlastConsolidationReport']['properties']
    assert {'rows_in', 'holes_out', 'deck_rows_merged', 'version', 'warnings', 'conflicts'} <= set(report)
