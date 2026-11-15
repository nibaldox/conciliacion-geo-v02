"""Unit tests for scripts/perf/endpoint_bench.py (no real server; no sockets).

HTTP is exercised only through httpx.MockTransport, which runs in-process.
"""

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "perf" / "endpoint_bench.py"
_spec = importlib.util.spec_from_file_location("endpoint_bench", _SCRIPT)
assert _spec is not None and _spec.loader is not None
bench = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = bench
_spec.loader.exec_module(bench)

SESSION_A = "11111111-2222-4333-8444-555555555555"
SESSION_B = "66666666-7777-4888-8999-aaaaaaaaaaaa"
DESIGN = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
TOPO = "12345678-1234-4123-8123-123456789012"
SECTION = {"name": "S-01", "sector": "Norte", "origin": [1000.0, 2000.0]}


def _ctx(**overrides):
    values = {"session_id": SESSION_A, "design_mesh_id": DESIGN, "topo_mesh_id": TOPO, "section": dict(SECTION)}
    values.update(overrides)
    return bench.Context(**values)


def _ok(seconds: float = 0.1, size: int = 10) -> dict:
    return {"seconds": seconds, "status_code": 200, "bytes": size}


def _user(repetitions: dict, discovery: dict | None = None, errors: list | None = None) -> dict:
    return {
        "user": 1,
        "session_id": SESSION_A,
        "discovery": discovery or {},
        "errors": errors or [],
        "repetitions": repetitions,
    }


def _build(*argv: str):
    parser = bench.build_parser()
    args = parser.parse_args(["--base-url", "http://127.0.0.1:8125", *argv])
    return bench.build_config(args, parser)


def _sessions_arg(*sessions: str) -> list[str]:
    return ["--sessions", ",".join(sessions)]


def test_assign_sessions_round_robin_two_users_per_session():
    sessions = ("s1", "s2", "s3", "s4", "s5")
    assigned = bench.assign_sessions(10, sessions)
    assert assigned == list(sessions) * 2
    assert all(assigned.count(session) == 2 for session in sessions)


def test_assign_sessions_fewer_users_than_sessions_uses_first_ones():
    assert bench.assign_sessions(2, ("a", "b", "c")) == ["a", "b"]


def test_percentile_is_nearest_rank_and_none_when_empty():
    values = [float(value) for value in range(1, 11)]
    assert bench.percentile(values, 50) == 5.0
    assert bench.percentile(values, 95) == 10.0
    assert bench.percentile([], 50) is None
    assert bench.percentile([3.0], 95) == 3.0


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("vertices_topo", (f"/api/v1/meshes/{TOPO}/vertices", {"step": 150000})),
        ("vertices_design", (f"/api/v1/meshes/{DESIGN}/vertices", {"step": 150000})),
        ("breaklines_design", (f"/api/v1/meshes/{DESIGN}/breaklines", None)),
        ("contours_topo", (f"/api/v1/meshes/{TOPO}/contours", {"interval": 15})),
        (
            "roi_topo",
            (
                f"/api/v1/meshes/{TOPO}/vertices/roi",
                {"xmin": 850.0, "ymin": 1850.0, "xmax": 1150.0, "ymax": 2150.0, "step": 60000},
            ),
        ),
        (
            "horizontal_deviation",
            (
                f"/api/v1/meshes/{TOPO}/horizontal-deviation",
                {"design_mesh_id": DESIGN, "sector": "Norte", "longitudinal_step": 2, "vertical_step": 1},
            ),
        ),
        ("blast_holes_3d", ("/api/v1/blast/holes/3d", None)),
        ("blast_holes_3d_section", ("/api/v1/blast/holes/3d", {"section_id": 0, "corridor_m": 10})),
        ("blast_session_holes", (f"/api/v1/blast/{SESSION_A}/holes", None)),
    ],
)
def test_build_request_matches_viewer_contract(name, expected):
    assert bench.build_request(name, _ctx()) == expected


def test_build_request_rejects_unknown_endpoint():
    with pytest.raises(ValueError):
        bench.build_request("nope", _ctx())


def test_every_declared_endpoint_has_a_request_builder():
    for name in bench.ENDPOINT_NAMES:
        path, _ = bench.build_request(name, _ctx())
        assert path.startswith("/api/v1/")


def test_missing_inputs_flags_only_endpoints_that_need_them():
    no_design = _ctx(design_mesh_id=None)
    assert bench.missing_inputs("vertices_design", no_design) is not None
    assert bench.missing_inputs("breaklines_design", no_design) is not None
    assert bench.missing_inputs("horizontal_deviation", no_design) is not None
    assert bench.missing_inputs("vertices_topo", no_design) is None

    no_section = _ctx(section=None)
    assert bench.missing_inputs("roi_topo", no_section) is not None
    assert bench.missing_inputs("blast_holes_3d_section", no_section) is not None
    assert bench.missing_inputs("blast_session_holes", no_section) is None
    assert bench.missing_inputs("blast_holes_3d", no_section) is None

    no_topo = _ctx(topo_mesh_id=None)
    assert bench.missing_inputs("contours_topo", no_topo) is not None
    assert bench.missing_inputs("breaklines_design", no_topo) is None


def test_parse_mesh_ids_reads_recovery_body_and_nulls_missing_ids():
    assert bench.parse_mesh_ids({"session_id": SESSION_A, "design_mesh_id": DESIGN, "topo_mesh_id": None}) == (
        DESIGN,
        None,
    )
    assert bench.parse_mesh_ids({"design_mesh_id": "", "topo_mesh_id": TOPO}) == (None, TOPO)


def test_parse_mesh_ids_rejects_non_object():
    with pytest.raises(ValueError):
        bench.parse_mesh_ids([DESIGN])


def test_parse_first_section_trims_sector_and_keeps_origin():
    body = [{"name": "S-01", "origin": [1000, 2000.5], "sector": "  Norte ", "azimuth": 30.0}]
    assert bench.parse_first_section(body) == {"name": "S-01", "sector": "Norte", "origin": [1000.0, 2000.5]}


def test_parse_first_section_handles_empty_null_sector_and_bad_input():
    assert bench.parse_first_section([]) is None
    assert bench.parse_first_section([{"name": "S", "origin": [1, 2], "sector": None}])["sector"] == ""
    with pytest.raises(ValueError):
        bench.parse_first_section({"origin": [1, 2]})
    with pytest.raises(ValueError):
        bench.parse_first_section([{"name": "S"}])
    with pytest.raises(ValueError):
        bench.parse_first_section([{"name": "S", "origin": [1, "x"]}])
    with pytest.raises(ValueError):
        bench.parse_first_section([{"name": "S", "origin": [float("nan"), 2.0]}])


def test_summarize_percentiles_use_only_2xx_entries():
    users = [
        _user({"1": {"vertices_topo": _ok(1.0, 100)}}),
        _user({"1": {"vertices_topo": _ok(3.0, 300)}}),
        _user({"1": {"vertices_topo": {"seconds": 0.5, "status_code": 500, "bytes": 20, "error": "HTTP 500"}}}),
        _user({"1": {"vertices_topo": {"seconds": 0.0, "status_code": None, "bytes": 0, "skipped": True}}}),
    ]
    stats = bench.summarize(users, ("vertices_topo",), 1)["1"]["vertices_topo"]
    assert stats == {"n": 4, "ok": 2, "p50_s": 1.0, "p95_s": 3.0, "max_s": 3.0, "bytes_p50": 100}


def test_summarize_reports_none_for_endpoint_without_successes():
    users = [_user({"2": {"roi_topo": {"seconds": 0.2, "status_code": 422, "bytes": 5, "error": "x"}}})]
    summary = bench.summarize(users, ("roi_topo", "contours_topo"), 2)
    assert summary["2"]["roi_topo"] == {"n": 1, "ok": 0, "p50_s": None, "p95_s": None, "max_s": None, "bytes_p50": None}
    assert summary["1"]["roi_topo"]["n"] == 0
    assert summary["1"]["contours_topo"]["n"] == 0


def test_summarize_probe_counts_slow_and_failed_samples():
    samples = [(0.1, True), (0.2, True), (1.5, True), (2.0, False)]
    assert bench.summarize_probe(samples) == {
        "n": 4,
        "max_s": 2.0,
        "p95_s": 2.0,
        "slow_over_1s": 2,
        "failures": 1,
    }


def test_summarize_probe_without_samples():
    assert bench.summarize_probe([]) == {"n": 0, "max_s": None, "p95_s": None, "slow_over_1s": 0, "failures": 0}


def test_wall_per_repetition_spans_all_users_windows():
    runs = [
        bench.UserRun(record={}, windows={1: (10.0, 12.0), 2: (13.0, 14.0)}),
        bench.UserRun(record={}, windows={1: (10.5, 13.25), 2: (13.5, 15.0)}),
    ]
    assert bench.wall_per_repetition(runs, 2) == {"1": 3.25, "2": 2.0}
    assert bench.wall_per_repetition([], 1) == {"1": None}


def test_totals_count_status_codes_skips_and_errors():
    user = _user(
        {
            "1": {
                "vertices_topo": _ok(),
                "contours_topo": {"seconds": 0.1, "status_code": 500, "bytes": 3, "error": "HTTP 500"},
                "roi_topo": {"seconds": 0.1, "status_code": None, "bytes": 0, "error": "ConnectError: x"},
                "horizontal_deviation": {"seconds": 0.0, "status_code": None, "bytes": 0, "skipped": True},
            }
        },
        discovery={"session_recovery": _ok(), "sections": _ok()},
        errors=["client: RuntimeError: boom"],
    )
    result = bench.totals([user], 1, {"1": 1.0})
    assert result["errors"] == 4
    assert result["http_status_counts"] == {"200": 3, "500": 1, "transport_error": 1}
    assert result["users"] == 1
    assert result["sessions"] == 1
    assert result["wall_s_per_repetition"] == {"1": 1.0}


def test_exit_status_is_zero_only_without_errors():
    assert bench.exit_status({"totals": {"errors": 0}}) == 0
    assert bench.exit_status({"totals": {"errors": 2}}) == 1


def test_build_config_defaults_users_to_session_count_and_canonical_endpoint_order():
    cfg = _build(*_sessions_arg(SESSION_A, SESSION_B))
    assert cfg.users == 2
    assert cfg.repeat == 2
    assert cfg.endpoints == bench.ENDPOINT_NAMES
    assert cfg.base_url == "http://127.0.0.1:8125"


def test_build_config_orders_selected_endpoints_canonically():
    cfg = _build(*_sessions_arg(SESSION_A), "--endpoints", "blast_session_holes,vertices_topo")
    assert cfg.endpoints == ("vertices_topo", "blast_session_holes")


@pytest.mark.parametrize(
    "argv",
    [
        ["--base-url", "https://conciliacion-api-ewbb.onrender.com", *_sessions_arg(SESSION_A)],
        ["--base-url", "http://CONCILIACION-API-EWBB.onrender.com", *_sessions_arg(SESSION_A)],
        ["--base-url", "ftp://127.0.0.1", *_sessions_arg(SESSION_A)],
        ["--base-url", "http://127.0.0.1:8125", "--sessions", f"{SESSION_A},{SESSION_A}"],
        ["--base-url", "http://127.0.0.1:8125", "--sessions", "not-a-uuid"],
        ["--base-url", "http://127.0.0.1:8125", "--sessions", " , "],
        ["--base-url", "http://127.0.0.1:8125", *_sessions_arg(SESSION_A), "--endpoints", "vertices_topo,nope"],
        ["--base-url", "http://127.0.0.1:8125", *_sessions_arg(SESSION_A), "--endpoints", "contours_topo,contours_topo"],
        ["--base-url", "http://127.0.0.1:8125", *_sessions_arg(SESSION_A), "--repeat", "0"],
        ["--base-url", "http://127.0.0.1:8125", *_sessions_arg(SESSION_A), "--users", "0"],
        ["--base-url", "http://127.0.0.1:8125", *_sessions_arg(SESSION_A), "--timeout", "0"],
        ["--base-url", "http://127.0.0.1:8125", *_sessions_arg(SESSION_A), "--probe-interval", "0"],
    ],
)
def test_build_config_refuses_invalid_usage(argv):
    parser = bench.build_parser()
    args = parser.parse_args(argv)
    with pytest.raises(SystemExit) as excinfo:
        bench.build_config(args, parser)
    assert excinfo.value.code == 2


def _recording_transport(
    *,
    recovery_status: int = 200,
    failing_substring: str | None = None,
    delay: float = 0.0,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if delay:
            time.sleep(delay)
        path = request.url.path
        if path == "/api/v1/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/v1/session/recovery":
            if recovery_status != 200:
                return httpx.Response(recovery_status, json={"detail": "Session not found"})
            return httpx.Response(
                200,
                json={
                    "session_id": request.headers["X-Session-ID"],
                    "design_mesh_id": DESIGN,
                    "topo_mesh_id": TOPO,
                },
            )
        if path == "/api/v1/sections":
            return httpx.Response(200, json=[{"name": "S-01", "origin": [1000.0, 2000.0], "sector": "Norte"}])
        if failing_substring is not None and failing_substring in path:
            return httpx.Response(500, json={"detail": "boom"})
        return httpx.Response(200, content=b"0123456789")

    return httpx.MockTransport(handler), requests


def _cfg(**overrides):
    base = {
        "base_url": "http://qa.test",
        "sessions": (SESSION_A,),
        "users": 1,
        "repeat": 1,
        "endpoints": bench.ENDPOINT_NAMES,
        "timeout": 5.0,
        "probe_interval": 0.01,
        "api_key": None,
    }
    base.update(overrides)
    return bench.RunConfig(**base)


def test_journey_records_failed_endpoint_and_continues_with_the_rest():
    transport, requests = _recording_transport(failing_substring="/contours")
    run = bench.run_user(1, SESSION_A, _cfg(), threading.Barrier(1), transport)
    record = run.record
    rep = record["repetitions"]["1"]
    assert list(rep) == list(bench.ENDPOINT_NAMES)
    assert rep["contours_topo"]["status_code"] == 500
    assert rep["contours_topo"]["error"].startswith("HTTP 500")
    assert all(rep[name]["status_code"] == 200 for name in bench.ENDPOINT_NAMES if name != "contours_topo")
    assert rep["vertices_topo"]["bytes"] == 10
    assert record["mesh_ids"] == {"design": DESIGN, "topo": TOPO}
    assert record["first_section"]["sector"] == "Norte"
    assert record["errors"] == []
    roi = next(r for r in requests if r.url.path.endswith("/vertices/roi"))
    assert roi.url.params["xmin"] == "850.0"
    assert roi.url.params["step"] == "60000"
    assert all(r.headers["X-Session-ID"] == SESSION_A for r in requests)
    horizontal = next(r for r in requests if r.url.path.endswith("/horizontal-deviation"))
    assert horizontal.url.params["sector"] == "Norte"
    assert horizontal.url.params["design_mesh_id"] == DESIGN


def test_missing_mesh_ids_skip_mesh_endpoints_without_sending_them():
    transport, requests = _recording_transport(recovery_status=404)
    run = bench.run_user(1, SESSION_A, _cfg(), threading.Barrier(1), transport)
    rep = run.record["repetitions"]["1"]
    skipped = {name for name, entry in rep.items() if entry.get("skipped")}
    assert skipped == {
        "vertices_topo",
        "vertices_design",
        "breaklines_design",
        "contours_topo",
        "roi_topo",
        "horizontal_deviation",
    }
    assert rep["blast_holes_3d"]["status_code"] == 200
    assert not any("/meshes/" in r.url.path for r in requests)
    assert run.record["discovery"]["session_recovery"]["status_code"] == 404
    assert bench.totals([run.record], 1, {})["errors"] == 7


def test_users_finish_each_repetition_before_the_next_one_starts():
    transport, _ = _recording_transport(delay=0.005)
    barrier = threading.Barrier(2)
    cfg = _cfg(users=2, repeat=2, endpoints=("vertices_topo", "blast_session_holes"))
    runs = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        run = bench.run_user(index, SESSION_A, cfg, barrier, transport)
        with lock:
            runs.append(run)

    threads = [threading.Thread(target=worker, args=(index,)) for index in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(runs) == 2
    for run in runs:
        assert set(run.windows) == {1, 2}
    first_end = max(run.windows[1][1] for run in runs)
    second_start = min(run.windows[2][0] for run in runs)
    assert second_start >= first_end


def test_run_bench_produces_full_result_and_exit_status():
    transport, _ = _recording_transport()
    cfg = _cfg(
        sessions=(SESSION_A, SESSION_B),
        users=2,
        repeat=2,
        endpoints=("vertices_topo", "blast_session_holes"),
    )
    result = bench.run_bench(cfg, transport)
    assert set(result) == {"config", "users", "summary", "probe", "totals"}
    assert result["config"]["sessions"] == [SESSION_A, SESSION_B]
    assert result["config"]["api_key_sent"] is False
    assert [user["session_id"] for user in result["users"]] == [SESSION_A, SESSION_B]
    for repetition in ("1", "2"):
        for name in ("vertices_topo", "blast_session_holes"):
            assert result["summary"][repetition][name]["n"] == 2
            assert result["summary"][repetition][name]["ok"] == 2
    assert result["probe"]["n"] >= 1
    assert result["probe"]["failures"] == 0
    assert result["totals"]["errors"] == 0
    assert result["totals"]["http_status_counts"]["200"] >= 2 * (2 + 2 * 2)
    assert set(result["totals"]["wall_s_per_repetition"]) == {"1", "2"}
    assert bench.exit_status(result) == 0
    json.dumps(result)


def test_run_bench_reports_errors_when_discovery_fails():
    transport, _ = _recording_transport(recovery_status=404)
    cfg = _cfg(endpoints=("vertices_topo", "blast_session_holes"))
    result = bench.run_bench(cfg, transport)
    assert result["totals"]["errors"] == 2
    assert bench.exit_status(result) == 1


def test_health_probe_records_successes_and_failures():
    ok_transport, _ = _recording_transport()
    probe = bench.HealthProbe("http://qa.test", {}, 0.01, ok_transport)
    probe.start()
    _wait_for_samples(probe)
    probe.stop()
    assert probe.samples and all(ok for _, ok in probe.samples)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    failing = bench.HealthProbe("http://qa.test", {}, 0.01, httpx.MockTransport(refuse))
    failing.start()
    _wait_for_samples(failing)
    failing.stop()
    assert failing.samples and all(not ok for _, ok in failing.samples)
    assert bench.summarize_probe(failing.samples)["failures"] == len(failing.samples)


def _wait_for_samples(probe, timeout: float = 5.0) -> None:
    deadline = time.perf_counter() + timeout
    while not probe.samples and time.perf_counter() < deadline:
        time.sleep(0.005)
