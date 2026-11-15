import io
import json

import pytest
from fastapi import HTTPException

import api.database as db
import api.routers.export as export
import api.routers.meshes as meshes
from api.schemas import ExportFilters
from core.config import report_tz


@pytest.mark.parametrize('endpoint,builder', [('word', '_build_word_payload_sync'), ('pdf', '_build_pdf_payload_sync'), ('images', '_build_images_zip_sync')])
def test_export_error_never_leaks_internal_exception(monkeypatch, endpoint, builder):
    from fastapi.testclient import TestClient
    from api.main import app
    monkeypatch.setattr(db, 'get_or_create_session', lambda sid: sid)
    def broken(*args):
        raise RuntimeError('sensitive-path-secret')
    monkeypatch.setattr(export, builder, broken)
    response = TestClient(app).get('/api/v1/export/' + endpoint, headers={'x-session-id': 'test'})
    assert response.status_code == 500
    assert 'sensitive-path-secret' not in response.text


def test_blank_sector_outdated_note_omits_empty_sector():
    assert export._heatmap_note('', True).startswith('Mapa de calor desactualizado')


def test_computation_timestamp_is_local_text(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'time.db')
    db.init_db()
    sid = db.create_session()
    params = {'bench_num': None, 'longitudinal_step': 1, 'vertical_step': 1}
    db.save_horizontal_deviation(sid, '', 'key', params, {'cells': []})
    monkeypatch.setattr(meshes, 'horizontal_deviation_cache_key', lambda *args: 'key')
    monkeypatch.setattr(meshes, 'horizontal_deviation_section_stations', lambda *args: ([], []))
    result = export._current_heatmaps(sid, [''])[0][0]
    from datetime import datetime, timezone
    expected = datetime.fromisoformat(result['created_at']).replace(tzinfo=timezone.utc).astimezone(report_tz()).strftime('%d/%m/%Y %H:%M')
    assert result['computed_at_text'] == expected


def test_bench_only_heatmap_is_not_a_sector_heatmap(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'test.db')
    db.init_db()
    sid = db.create_session()
    db.save_horizontal_deviation(sid, 'A', 'key', {'bench_num': 1, 'longitudinal_step': 1, 'vertical_step': 1}, {'cells': []})
    monkeypatch.setattr(meshes, 'horizontal_deviation_cache_key', lambda *args: 'key')
    assert export._current_heatmaps(sid, ['A'])[0] == []


def test_lookup_does_not_decompress_unselected_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'test.db')
    db.init_db()
    sid = db.create_session()
    params = {'bench_num': None, 'longitudinal_step': 1, 'vertical_step': 1}
    db.save_horizontal_deviation(sid, 'A', 'good', params, {'cells': []})
    db.save_horizontal_deviation(sid, 'A', 'bad', params, {'cells': []})
    conn = db.get_connection()
    conn.execute("UPDATE horizontal_deviation_results SET payload = ? WHERE cache_key = 'bad'", (b'corrupt',))
    conn.commit()
    conn.close()
    monkeypatch.setattr(meshes, 'horizontal_deviation_cache_key', lambda *args: 'good')
    monkeypatch.setattr(meshes, 'horizontal_deviation_section_stations', lambda *args: ([], []))
    assert export._current_heatmaps(sid, ['A'])[0][0]['cache_key'] == 'good'


def test_concurrent_excel_requests_keep_their_own_payload(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from api.main import app
    barrier = Barrier(2)
    monkeypatch.setattr(db, 'get_or_create_session', lambda sid: sid)
    monkeypatch.setattr(export, '_build_report_data_sync', lambda sid, project, author, operation, phase, filters, **kwargs: (export._parse_filters(filters).sections[0], ExportFilters()))
    def builder(data):
        barrier.wait(timeout=10)
        return io.BytesIO(data.encode())
    monkeypatch.setattr(export, '_load_excel_builder', lambda: builder)
    client = TestClient(app)
    def request(project):
        return client.get('/api/v1/export/excel', headers={'x-session-id': 'same'}, params={'filters': json.dumps({'section': [project]})})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(request, ['first', 'second']))
    assert [r.status_code for r in responses] == [200, 200]
    assert [r.content for r in responses] == [b'first', b'second']


def test_excel_builder_returns_independent_in_memory_payloads(monkeypatch):
    monkeypatch.setattr(export, '_load_excel_builder', lambda: lambda data: io.BytesIO(data.encode()))
    monkeypatch.setattr(export, '_build_report_data_sync', lambda sid, project, *args, **kwargs: (project, ExportFilters()))
    first, _ = export._build_excel_payload_sync('same', 'first', None, None, None, None)
    second, _ = export._build_excel_payload_sync('same', 'second', None, None, None, None)
    assert first.getvalue() == b'first'
    assert second.getvalue() == b'second'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_filter_is_bad_request(value):
    with pytest.raises(HTTPException) as exc:
        export._parse_filters(json.dumps({'blastTolerance': value}))
    assert exc.value.status_code == 400


def test_bench_and_section_scope_notes_combined_in_report(monkeypatch):
    from types import SimpleNamespace
    entry = {"sector": "A", "payload": {"section_names": ["S1", "S2"], "section_stations_m": [0, 10], "cells": [{"station_m": 0}]}}
    monkeypatch.setattr(db, "get_results", lambda _: [{"section": "S1", "sector": "A", "bench_num": 2, "type": "MATCH"}])
    monkeypatch.setattr(db, "get_settings", lambda _: {})
    monkeypatch.setattr(db, "get_sections", lambda _: [])
    monkeypatch.setattr(export, "_report_meta", lambda *args: {})
    monkeypatch.setattr(export, "_load_mesh_from_db", lambda *args: None)
    monkeypatch.setattr(export, "_build_section_geometry", lambda *args: [])
    monkeypatch.setattr(export, "_load_report_depth_extractions", lambda *args: {})
    monkeypatch.setattr(export, "_current_heatmaps", lambda *args: ([entry.copy()], []))
    monkeypatch.setattr(export, "build_report_data", lambda *args, **kwargs: SimpleNamespace(**kwargs))
    data, _ = export._build_report_data_sync("s", None, None, None, None, json.dumps({"section": ["S1"], "selectedBenchNumbers": [2]}))
    note = data.heatmaps[0]["scope_note"]
    assert "secciones del informe" in note
    assert "filtro de bancos no se aplica" in note
