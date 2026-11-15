import asyncio

from fastapi.testclient import TestClient

import api.database as db
from api.main import app


def insert_session(conn, sid, created, used, sections='[]', settings='{}'):
    conn.execute("INSERT INTO sessions(id, created_at, updated_at, sections, settings) VALUES (?, datetime('now', ?), datetime('now', ?), ?, ?)", (sid, created, used, sections, settings))


def test_retention_last_use_empty_and_cascades(api_isolated_db):
    conn = db.get_connection()
    assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    insert_session(conn, 'active', '-40 days', '-2 days', '[1]')
    insert_session(conn, 'expired', '-40 days', '-31 days', '[1]')
    insert_session(conn, 'empty-old', '-2 days', '-25 hours')
    insert_session(conn, 'empty-new', '-2 days', '-1 hours')
    insert_session(conn, 'sections', '-2 days', '-25 hours', '[1]')
    insert_session(conn, 'settings', '-2 days', '-25 hours', settings='{"x":1}')
    conn.execute("INSERT INTO meshes(id, session_id, type) VALUES ('m', 'expired', 'design')")
    conn.execute("INSERT INTO results(session_id) VALUES ('expired')")
    conn.execute("INSERT INTO horizontal_deviation_results(session_id, sector, cache_key, params, payload) VALUES ('expired','a','b','{}',x'01')")
    conn.commit()
    conn.close()
    assert db.cleanup_old_sessions() == 2
    conn = db.get_connection()
    assert {r[0] for r in conn.execute('SELECT id FROM sessions')} == {'active', 'empty-new', 'sections', 'settings'}
    for table in ('meshes', 'results', 'horizontal_deviation_results'):
        assert conn.execute(f"SELECT count(*) FROM {table} WHERE session_id='expired'").fetchone()[0] == 0
    conn.close()


def test_cleanup_deletes_only_expired_session_conversations(api_isolated_db):
    conn = db.get_connection()
    insert_session(conn, 'expired-ai', '-40 days', '-31 days', '[1]')
    insert_session(conn, 'active-ai', '-40 days', '-1 days', '[1]')
    conn.executemany(
        'INSERT INTO ai_conversations(conversation_id, session_id, messages) VALUES (?, ?, ?)',
        [('old-conversation', 'expired-ai', '[]'), ('live-conversation', 'active-ai', '[]')],
    )
    conn.commit()
    conn.close()
    assert db.cleanup_old_sessions() == 1
    conn = db.get_connection()
    assert [tuple(row) for row in conn.execute('SELECT conversation_id, session_id FROM ai_conversations')] == [('live-conversation', 'active-ai')]
    assert not db.session_exists('expired-ai')
    assert db.session_exists('active-ai')
    conn.close()


def test_ttl_override(api_isolated_db):
    conn = db.get_connection()
    insert_session(conn, 's', '-4 days', '-3 days', '[1]')
    conn.commit()
    conn.close()
    assert db.cleanup_old_sessions(max_age_days=2) == 1


def test_recovery_touches_session(api_isolated_db):
    conn = db.get_connection()
    insert_session(conn, 's', '-40 days', '-2 days')
    conn.commit()
    conn.close()
    assert TestClient(app).get('/api/v1/session/recovery', headers={'X-Session-ID': 's'}).status_code == 200
    conn = db.get_connection()
    assert conn.execute("SELECT updated_at > datetime('now', '-1 minute') FROM sessions WHERE id='s'").fetchone()[0] == 1
    conn.close()


def test_startup_cleanup_helper(api_isolated_db, monkeypatch, caplog):
    import api.main as main
    conn = db.get_connection()
    insert_session(conn, 'old', '-40 days', '-31 days', '[1]')
    conn.commit()
    conn.close()
    asyncio.run(main._run_startup_session_cleanup())
    assert not db.session_exists('old')
    def fail():
        raise RuntimeError('failure')
    monkeypatch.setattr(main, 'cleanup_old_sessions', fail)
    asyncio.run(main._run_startup_session_cleanup())
    assert 'failure' in caplog.text
