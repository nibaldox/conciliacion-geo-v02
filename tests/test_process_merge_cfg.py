"""Tests for the pure process-settings merge used by the pipeline (api.routers.process)."""
from __future__ import annotations

from api.routers.process import _merge_process_cfg


def test_saved_threshold_survives_empty_override():
    settings = {"process": {"face_threshold": 35.0}}
    merged = _merge_process_cfg(settings, {"process": {}})
    assert merged["face_threshold"] == 35.0


def test_override_wins_over_saved_threshold():
    settings = {"process": {"face_threshold": 35.0}}
    merged = _merge_process_cfg(settings, {"process": {"face_threshold": 40}})
    assert merged["face_threshold"] == 40


def test_merge_does_not_mutate_inputs():
    settings = {"process": {"face_threshold": 35.0}}
    overrides = {"process": {"face_threshold": 40}}
    _merge_process_cfg(settings, overrides)
    assert settings == {"process": {"face_threshold": 35.0}}
    assert overrides == {"process": {"face_threshold": 40}}


def test_merge_without_saved_process_uses_overrides_only():
    assert _merge_process_cfg({}, {"process": {"resolution": 0.5}}) == {"resolution": 0.5}
    assert _merge_process_cfg({}, {}) == {}
