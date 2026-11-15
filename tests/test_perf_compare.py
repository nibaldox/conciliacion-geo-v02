"""Unit tests for compare_json in scripts/perf/dump_results.py (no real meshes)."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "perf" / "dump_results.py"
_spec = importlib.util.spec_from_file_location("perf_dump_results", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
compare_json = _module.compare_json

NAN = float("nan")
INF = float("inf")


def _dump(face_angle: float = 30.0) -> dict:
    return {
        "git_sha": "abc1234",
        "sections": [
            {
                "name": "S-01",
                "design": {
                    "benches": [
                        {"bench_number": 1, "face_angle": 45.0},
                        {"bench_number": 2, "face_angle": 60.0},
                        {"bench_number": 3, "face_angle": face_angle},
                    ],
                    "inter_ramp_angle": None,
                },
                "topo": {"benches": []},
                "comparisons": [{"status": "CUMPLE", "ok": True}],
                "warnings": {"design": [], "topo": ["thin_profile"]},
            }
        ],
    }


def test_equal_nested_structures_return_none():
    assert compare_json(_dump(), _dump()) is None


def test_float_within_tolerance_is_equal():
    assert compare_json({"x": 1.0}, {"x": 1.0 + 1e-10}) is None


def test_float_difference_reports_full_path():
    message = compare_json(_dump(30.0), _dump(30.000001))
    assert message is not None
    assert "sections[0].design.benches[2].face_angle" in message


def test_nan_equals_nan():
    assert compare_json({"x": NAN}, {"x": NAN}) is None


def test_nan_versus_number_differs():
    message = compare_json({"x": NAN}, {"x": 1.0})
    assert message is not None
    assert "x" in message


def test_infinity_same_sign_equal_and_opposite_sign_differs():
    assert compare_json({"x": INF}, {"x": INF}) is None
    assert compare_json({"x": INF}, {"x": -INF}) is not None


def test_list_length_mismatch_reports_list_path():
    message = compare_json({"v": [1, 2]}, {"v": [1, 2, 3]})
    assert message is not None
    assert "v" in message
    assert "2" in message and "3" in message


def test_missing_dict_key_reports_key_path():
    baseline = {"sections": [{"design": {"face_angle": 1.0}}]}
    current = {"sections": [{"design": {}}]}
    message = compare_json(baseline, current)
    assert message is not None
    assert "sections[0].design.face_angle" in message


def test_int_difference_is_exact():
    assert compare_json({"n": 2}, {"n": 3}) is not None
    assert compare_json({"n": 10**17}, {"n": 10**17 + 1}) is not None
    assert compare_json({"n": 10**17}, {"n": 10**17}) is None


def test_bool_is_not_equal_to_int():
    assert compare_json({"flag": True}, {"flag": 1}) is not None


def test_string_and_none_exact():
    assert compare_json({"s": "a"}, {"s": "a"}) is None
    assert compare_json({"s": "a"}, {"s": "b"}) is not None
    assert compare_json({"s": None}, {"s": "None"}) is not None


def test_top_level_git_sha_difference_is_ignored():
    assert compare_json({"git_sha": "aaa", "sections": []}, {"git_sha": "bbb", "sections": []}) is None


def test_nested_git_sha_difference_is_not_ignored():
    message = compare_json({"x": {"git_sha": "aaa"}}, {"x": {"git_sha": "bbb"}})
    assert message is not None
    assert "x.git_sha" in message
