import json

import api.database as db


def _rows(collar_x=10.0, extra=None):
    row = {
        "hole_id": "H1", "source_row_index": 1,
        "X": collar_x, "Y": 20.0, "Z_collar": 100.0,
        "X_toe": 11.0, "Y_toe": 20.0, "Z_toe": 80.0,
        "Banco_Original": "B-100",
    }
    if extra:
        row.update(extra)
    return [row, {"hole_id": "H2", "source_row_index": 2, "X": 1.0, "Y": 2.0}]


def _get(client, session_id, query=""):
    response = client.get(f"/api/v1/blast/holes/3d{query}", headers={"X-Session-ID": session_id})
    assert response.status_code == 200
    return response.json()


def _save(session_id, rows):
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {"accepted_rows": rows, "rejected_rows": []})


def test_revision_absent_without_source_is_none(client):
    body = _get(client, "rev-empty")
    assert body["data_revision"] is None


def test_revision_changes_when_coordinates_change_with_same_ids_and_length(client):
    _save("rev-coords-a", _rows(collar_x=10.0))
    _save("rev-coords-b", _rows(collar_x=99.0))

    first = _get(client, "rev-coords-a")["data_revision"]
    second = _get(client, "rev-coords-b")["data_revision"]

    assert first is not None and second is not None
    assert first != second


def test_revision_is_deterministic_for_same_source(client):
    _save("rev-stable", _rows())

    first = _get(client, "rev-stable")["data_revision"]
    second = _get(client, "rev-stable")["data_revision"]

    assert first == second
    assert len(first) == 64


def test_revision_ignores_section_and_corridor(client):
    session_id = "rev-section-independent"
    _save(session_id, _rows())
    db.save_sections(session_id, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])

    plain = _get(client, session_id)["data_revision"]
    with_section = _get(client, session_id, "?section_id=0&corridor_m=3")["data_revision"]
    other_corridor = _get(client, session_id, "?section_id=0&corridor_m=7")["data_revision"]

    assert plain == with_section == other_corridor


def test_revision_is_isolated_per_session(client):
    _save("rev-iso-a", _rows())

    assert _get(client, "rev-iso-b")["data_revision"] is None
    assert _get(client, "rev-iso-a")["data_revision"] is not None


def test_revision_handles_legacy_nonfinite_values_deterministically(client):
    session_id = "rev-nonfinite"
    _save(session_id, _rows(extra={"Diam_mm": float("nan"), "PF": float("inf")}))

    first = client.get("/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id})
    second = _get(client, session_id)

    assert first.status_code == 200
    assert first.json()["data_revision"] is not None
    assert first.json()["data_revision"] == second["data_revision"]
    assert "NaN" not in first.text and "Infinity" not in first.text


def test_revision_distinguishes_nonfinite_from_zero(client):
    _save("rev-nan", _rows(extra={"Diam_mm": float("nan")}))
    _save("rev-zero", _rows(extra={"Diam_mm": 0.0}))

    assert _get(client, "rev-nan")["data_revision"] != _get(client, "rev-zero")["data_revision"]


def test_get_does_not_write_settings(client):
    session_id = "rev-readonly"
    _save(session_id, _rows())
    db.save_sections(session_id, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])
    before = json.dumps(db.get_settings(session_id), sort_keys=True)

    _get(client, session_id)
    _get(client, session_id, "?section_id=0&corridor_m=3")

    assert json.dumps(db.get_settings(session_id), sort_keys=True) == before


def test_revision_nan_differs_from_nonfinite_marker_object():
    from api.routers.blast import _data_revision

    nan_source = {"blast_holes": [{"custom": float("nan")}]}
    marker_source = {"blast_holes": [{"custom": {"__nonfinite__": "nan"}}]}

    assert _data_revision(nan_source) != _data_revision(marker_source)


def test_revision_inf_and_neginf_differ_from_marker_objects():
    from api.routers.blast import _data_revision

    inf_rev = _data_revision({"blast_holes": [{"custom": float("inf")}]})
    neginf_rev = _data_revision({"blast_holes": [{"custom": float("-inf")}]})

    assert inf_rev != _data_revision({"blast_holes": [{"custom": {"__nonfinite__": "inf"}}]})
    assert neginf_rev != _data_revision({"blast_holes": [{"custom": {"__nonfinite__": "-inf"}}]})
    assert inf_rev != neginf_rev


def test_revision_nonfinite_differs_from_string_tokens():
    from api.routers.blast import _data_revision

    nan_rev = _data_revision({"blast_holes": [{"custom": float("nan")}]})
    inf_rev = _data_revision({"blast_holes": [{"custom": float("inf")}]})

    assert nan_rev != _data_revision({"blast_holes": [{"custom": "NaN"}]})
    assert inf_rev != _data_revision({"blast_holes": [{"custom": "Infinity"}]})


def test_revision_accepts_lone_surrogate_in_persisted_string(client):
    from api.routers.blast import _data_revision

    normal = _data_revision({"blast_holes": [{"hole_id": "H1"}]})
    surrogate = _data_revision({"blast_holes": [{"hole_id": "\ud800"}]})

    assert len(surrogate) == 64
    assert surrogate != normal


def _count_digests(monkeypatch):
    import api.routers.blast as blast_router

    calls = {"n": 0}
    original = blast_router._blast_holes_digest

    def counted(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(blast_router, "_blast_holes_digest", counted)
    return calls


def test_second_request_with_same_version_skips_digest(client, monkeypatch):
    session_id = "rev-cache-hit"
    _save(session_id, _rows())
    calls = _count_digests(monkeypatch)

    first = _get(client, session_id)
    second = _get(client, session_id)

    assert first["data_revision"] == second["data_revision"]
    assert calls["n"] == 1


def test_cached_revision_equals_uncached_calculation(client):
    from api.routers.blast import _data_revision

    session_id = "rev-cache-value"
    _save(session_id, _rows(extra={"Diam_mm": float("nan"), "PF": float("inf")}))

    _get(client, session_id)
    cached = _get(client, session_id)["data_revision"]

    assert cached == _data_revision(db.get_settings(session_id))


def test_revision_changes_after_settings_write_and_matches_uncached(client):
    from api.routers.blast import _data_revision

    session_id = "rev-cache-invalidate"
    _save(session_id, _rows(collar_x=10.0))
    before = _get(client, session_id)["data_revision"]

    _save(session_id, _rows(collar_x=42.0))
    after = _get(client, session_id)["data_revision"]

    assert before != after
    assert after == _data_revision(db.get_settings(session_id))


def test_cache_is_isolated_per_session_with_equal_versions(client):
    from api.routers.blast import _data_revision

    _save("rev-cache-iso-a", _rows(collar_x=1.0))
    _save("rev-cache-iso-b", _rows(collar_x=2.0))

    first = _get(client, "rev-cache-iso-a")["data_revision"]
    second = _get(client, "rev-cache-iso-b")["data_revision"]

    assert first != second
    assert first == _data_revision(db.get_settings("rev-cache-iso-a"))
    assert second == _data_revision(db.get_settings("rev-cache-iso-b"))


def test_revision_skips_cache_without_settings_version(client, monkeypatch):
    session_id = "rev-no-version"
    _save(session_id, _rows())
    calls = _count_digests(monkeypatch)
    monkeypatch.setattr(db, "read_settings_version", lambda _session_id: None)

    first = _get(client, session_id)
    second = _get(client, session_id)

    assert calls["n"] == 2
    assert first["data_revision"] == second["data_revision"]


def test_revision_is_not_cached_when_version_changes_mid_request(client, monkeypatch):
    session_id = "rev-cache-race"
    _save(session_id, _rows())
    original_get_settings = db.get_settings
    state = {"written": False}

    def racing_get_settings(sid):
        settings = original_get_settings(sid)
        if not state["written"]:
            state["written"] = True
            db.save_settings(sid, settings)
        return settings

    monkeypatch.setattr(db, "get_settings", racing_get_settings)
    calls = _count_digests(monkeypatch)

    first = _get(client, session_id)
    second = _get(client, session_id)

    assert calls["n"] == 2
    assert first["data_revision"] == second["data_revision"]


def test_revision_cache_is_bounded(client):
    import api.routers.blast as blast_router

    for index in range(12):
        session_id = f"rev-cache-lru-{index}"
        _save(session_id, _rows(collar_x=float(index)))
        _get(client, session_id)

    assert len(blast_router._DATA_REVISION_CACHE) <= 8


