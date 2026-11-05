"""Cache contract for ``api.database.get_settings`` and the mesh LRU bound.

The QA session stores a ~79 MB ``sessions.settings`` blob (11,184 blast
holes), so every ``/blast/*`` request used to pay a full ``json.loads`` plus
~240 MB of transient native memory. These tests pin the two properties that
make a cache safe here: no re-parse when nothing changed, and no state
leaking between requests through the returned object.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

import api.database as db


class _CountingJSON:
    def __init__(self, real):
        self._real = real
        self.loads_calls = 0

    def loads(self, *args, **kwargs):
        self.loads_calls += 1
        return self._real.loads(*args, **kwargs)

    def dumps(self, *args, **kwargs):
        return self._real.dumps(*args, **kwargs)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    db.clear_settings_cache()
    try:
        yield
    finally:
        db.clear_settings_cache()


@pytest.fixture()
def counting_json(monkeypatch):
    counter = _CountingJSON(json)
    monkeypatch.setattr(db, "json", counter)
    return counter


def _external_write(session_id, payload):
    conn = sqlite3.connect(str(db.DB_PATH))
    try:
        conn.execute(
            "UPDATE sessions SET settings = ?, "
            "settings_version = COALESCE(settings_version, 0) + 1, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(payload), session_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- red: no re-parse ---------------------------------------------------------


def test_second_read_does_not_parse_again(isolated_data_dir, counting_json):
    session_id = db.create_session()
    db.save_settings(
        session_id,
        {"process": {"resolution": 0.2}, "blast_holes": [{"X": 1.0, "Y": 2.0}]},
    )

    counting_json.loads_calls = 0
    first = db.get_settings(session_id)
    calls_after_first = counting_json.loads_calls
    assert calls_after_first == 1
    assert first == {"process": {"resolution": 0.2}, "blast_holes": [{"X": 1.0, "Y": 2.0}]}

    second = db.get_settings(session_id)
    assert counting_json.loads_calls == calls_after_first
    assert second == first


# --- invalidation on every in-process write path ------------------------------


def test_save_settings_invalidates(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(session_id, {"v": 1})
    assert db.get_settings(session_id) == {"v": 1}

    db.save_settings(session_id, {"v": 2})
    assert db.get_settings(session_id) == {"v": 2}


def test_save_blast_upload_invalidates(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(session_id, {"process": {"resolution": 0.1}})
    assert db.get_settings(session_id)["process"]["resolution"] == 0.1

    db.save_blast_upload(
        session_id,
        {
            "accepted_rows": [{"X": 1.0, "Y": 2.0, "Z_collar": 100.0}],
            "rejected_rows": [],
            "n_holes": 1,
        },
    )
    stored = db.get_settings(session_id)
    assert stored["process"]["resolution"] == 0.1
    assert stored["blast_holes"] == [{"X": 1.0, "Y": 2.0, "Z_collar": 100.0}]
    assert stored["blast_upload_meta"]["n_holes"] == 1


def test_write_from_another_connection_invalidates(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(session_id, {"v": 1})
    assert db.get_settings(session_id) == {"v": 1}

    _external_write(session_id, {"v": 2})

    assert db.get_settings(session_id) == {"v": 2}


def test_write_from_another_connection_with_same_length_invalidates(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(session_id, {"version": "aaaa"})
    assert db.get_settings(session_id) == {"version": "aaaa"}

    _external_write(session_id, {"version": "bbbb"})

    assert db.get_settings(session_id) == {"version": "bbbb"}


def test_deleted_session_is_not_served_from_cache(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(session_id, {"v": 1})
    assert db.get_settings(session_id) == {"v": 1}

    conn = sqlite3.connect(str(db.DB_PATH))
    try:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()

    assert db.get_settings(session_id) == {}


# --- mutation safety of the returned object ----------------------------------


def test_top_level_mutation_does_not_contaminate(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(session_id, {"process": {"resolution": 0.1}})

    leaked = db.get_settings(session_id)
    leaked["leak"] = True
    leaked.pop("process")
    leaked.update({"tolerances": {"bench_height": {"neg": 9.0}}})

    assert db.get_settings(session_id) == {"process": {"resolution": 0.1}}


def test_nested_process_and_tolerances_mutation_does_not_contaminate(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(
        session_id,
        {
            "process": {"resolution": 0.1, "face_threshold": 40.0},
            "tolerances": {"bench_height": {"neg": 1.0, "pos": 1.5}},
        },
    )

    leaked = db.get_settings(session_id)
    leaked["process"].update({"resolution": 0.5})
    leaked["tolerances"]["bench_height"]["neg"] = 99.0
    leaked["tolerances"]["added"] = {"neg": 1.0, "pos": 1.0}

    fresh = db.get_settings(session_id)
    assert fresh["process"] == {"resolution": 0.1, "face_threshold": 40.0}
    assert fresh["tolerances"] == {"bench_height": {"neg": 1.0, "pos": 1.5}}


def test_nested_blast_mutation_does_not_contaminate(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(
        session_id,
        {"blast": {"rock_density_tm3": 2.7, "sector_density": {"A": 2.5}}},
    )

    leaked = db.get_settings(session_id)
    leaked["blast"].update({"rock_density_tm3": 3.1})
    leaked["blast"]["sector_density"]["A"] = 9.9

    fresh = db.get_settings(session_id)
    assert fresh["blast"] == {"rock_density_tm3": 2.7, "sector_density": {"A": 2.5}}


def test_mutate_then_save_persists_only_the_explicit_write(isolated_data_dir):
    session_id = db.create_session()
    db.save_settings(session_id, {"tolerances": {"bench_height": {"neg": 1.0, "pos": 1.5}}})

    draft = db.get_settings(session_id)
    draft["tolerances"]["bench_height"]["pos"] = 2.5
    draft["process"] = {"resolution": 0.3}
    assert db.get_settings(session_id)["tolerances"]["bench_height"]["pos"] == 1.5

    db.save_settings(session_id, draft)
    saved = db.get_settings(session_id)
    assert saved["tolerances"]["bench_height"]["pos"] == 2.5
    assert saved["process"] == {"resolution": 0.3}


# --- isolation and bounds ----------------------------------------------------


def test_sessions_do_not_share_cached_settings(isolated_data_dir):
    first = db.create_session()
    second = db.create_session()
    db.save_settings(first, {"owner": "first"})
    db.save_settings(second, {"owner": "second"})

    assert db.get_settings(first) == {"owner": "first"}
    assert db.get_settings(second) == {"owner": "second"}
    assert db.get_settings(first) == {"owner": "first"}


def test_cache_is_bounded_and_evicts_least_recently_used(isolated_data_dir):
    assert 2 <= db._SETTINGS_CACHE_MAX <= 4

    session_ids = []
    for index in range(db._SETTINGS_CACHE_MAX + 2):
        session_id = db.create_session()
        db.save_settings(session_id, {"index": index})
        session_ids.append(session_id)
        db.get_settings(session_id)

    assert len(db._SETTINGS_CACHE) <= db._SETTINGS_CACHE_MAX
    assert session_ids[-1] in {key[1] for key in db._SETTINGS_CACHE}


def test_partially_filled_cache_still_bounded(isolated_data_dir, counting_json):
    session_ids = [db.create_session() for _ in range(db._SETTINGS_CACHE_MAX + 1)]
    for index, session_id in enumerate(session_ids):
        db.save_settings(session_id, {"index": index})

    counting_json.loads_calls = 0
    for session_id in session_ids:
        db.get_settings(session_id)
    assert counting_json.loads_calls == len(session_ids)

    counting_json.loads_calls = 0
    db.get_settings(session_ids[-1])
    assert counting_json.loads_calls == 0
