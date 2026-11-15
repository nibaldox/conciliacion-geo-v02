from dataclasses import replace

from fastapi.testclient import TestClient

import api.database as db
import core.config as config
from api.main import app


def test_list_disabled(api_isolated_db, monkeypatch):
    monkeypatch.setattr(config, 'DEPLOY', replace(config.DEPLOY, session_list_enabled=False))
    response = TestClient(app).get('/api/v1/session/list')
    assert response.status_code == 404
    assert response.json() == {'detail': 'Not found'}


def test_disabled_list_precedes_query_validation(api_isolated_db, monkeypatch):
    monkeypatch.setattr(config, 'DEPLOY', replace(config.DEPLOY, session_list_enabled=False))
    client = TestClient(app)
    for query in ('limit=0', 'limit=x', 'limit=201'):
        response = client.get('/api/v1/session/list?' + query)
        assert response.status_code == 404
        assert response.json() == {'detail': 'Not found'}


def test_list_timestamps_are_normalized_and_bad_rows_skipped(api_isolated_db, monkeypatch, caplog):
    monkeypatch.setattr(config, 'DEPLOY', replace(config.DEPLOY, session_list_enabled=True, session_ttl_days=30))
    conn = db.get_connection()
    conn.executemany('INSERT INTO sessions(id, created_at, updated_at) VALUES (?, ?, ?)', [
        ('aware', '2026-01-01T18:00:00+03:00', '2026-01-02T18:00:00+03:00'),
        ('naive', '2026-01-01 12:00:00', '2026-01-02 12:00:00'),
        ('bad-created', 'secret-bad-timestamp', '2026-01-03 12:00:00'),
        ('bad-updated', '2026-01-01 12:00:00', 'bad-value'),
    ])
    conn.executemany('INSERT INTO meshes(id, session_id, type) VALUES (?, ?, ?)', [
        (sid + '-mesh', sid, 'design') for sid in ('aware', 'naive', 'bad-created', 'bad-updated')
    ])
    conn.commit()
    conn.close()
    response = TestClient(app).get('/api/v1/session/list')
    assert response.status_code == 200
    rows = {row['session_id']: row for row in response.json()['sessions']}
    assert set(rows) == {'aware', 'naive'}
    assert (rows['aware']['created_at'], rows['aware']['last_used_at'], rows['aware']['expires_at']) == ('2026-01-01T15:00:00Z', '2026-01-02T15:00:00Z', '2026-02-01T15:00:00Z')
    assert (rows['naive']['created_at'], rows['naive']['last_used_at'], rows['naive']['expires_at']) == ('2026-01-01T12:00:00Z', '2026-01-02T12:00:00Z', '2026-02-01T12:00:00Z')
    assert 'bad-created' in caplog.text and 'bad-updated' in caplog.text
    assert 'secret-bad-timestamp' not in caplog.text and 'bad-value' not in caplog.text


def test_list_contract(api_isolated_db, monkeypatch):
    monkeypatch.setattr(config, 'DEPLOY', replace(config.DEPLOY, session_list_enabled=True, session_ttl_days=30))
    conn = db.get_connection()
    conn.executemany('INSERT INTO sessions(id, created_at, updated_at, sections, process_status) VALUES (?, ?, ?, ?, ?)', [
        ('old', '2026-01-01 00:00:00', '2026-01-02 00:00:00', 'invalid', 'idle'),
        ('new', '2026-01-01 00:00:00', '2026-01-03 00:00:00', '[1,2]', 'completed'),
        ('no-mesh', '2026-01-01 00:00:00', '2026-01-04 00:00:00', '[]', 'idle'),
    ])
    conn.executemany('INSERT INTO meshes(id, session_id, type, filename, uploaded_at) VALUES (?,?,?,?,?)', [
        ('m1','new','design','old.stl','2026-01-01 00:00:00'),
        ('m2','new','design','new.stl','2026-01-02 00:00:00'),
        ('m3','new','topo','topo.stl','2026-01-01 00:00:00'),
        ('m4','old','design','design.stl','2026-01-01 00:00:00'),
    ])
    conn.executemany('INSERT INTO results(session_id) VALUES (?)', [('new',), ('new',)])
    conn.commit()
    conn.close()
    statements = []
    original = db.get_connection
    def traced():
        c = original()
        c.set_trace_callback(statements.append)
        return c
    monkeypatch.setattr(db, 'get_connection', traced)
    client = TestClient(app)
    result = client.get('/api/v1/session/list').json()
    assert result['ttl_days'] == 30
    rows = result['sessions']
    assert [r['session_id'] for r in rows] == ['new', 'old']
    assert rows[0] == {'session_id': 'new', 'created_at': '2026-01-01T00:00:00Z', 'last_used_at': '2026-01-03T00:00:00Z', 'expires_at': '2026-02-02T00:00:00Z', 'design_filename': 'new.stl', 'topo_filename': 'topo.stl', 'n_sections': 2, 'n_results': 2, 'process_status': 'completed'}
    assert rows[1]['n_sections'] == 0 and rows[1]['topo_filename'] is None
    assert len(client.get('/api/v1/session/list?limit=1').json()['sessions']) == 1
    assert client.get('/api/v1/session/list?limit=0').status_code == 422
    assert client.get('/api/v1/session/list?limit=201').status_code == 422
    assert client.get('/api/v1/session/list?limit=x').status_code == 422
    assert not any('settings' in s.lower() for s in statements if s.lstrip().lower().startswith('select'))
    conn = original()
    assert conn.execute('SELECT count(*) FROM sessions').fetchone()[0] == 3
    conn.close()
