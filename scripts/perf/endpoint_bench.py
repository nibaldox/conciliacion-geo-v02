#!/usr/bin/env python3

"""HTTP benchmark of the heavy read endpoints behind the 3D viewer and dashboard.

N simultaneous users run the read-only journey that the web app performs when an
EXISTING session is opened in the 3D viewer / dashboard. User i is bound
round-robin to one session (sessions[i % S]) and sends X-Session-ID: <session>
on every request.

Discovery (recorded in users[].discovery, not one of the timed endpoints):
  GET /api/v1/session/recovery   design_mesh_id, topo_mesh_id (as web/src/sessionRecovery.ts)
  GET /api/v1/sections           first section: sector (trimmed) and origin [x, y]

Endpoints, in this order, each timed (seconds, status_code, bytes):
  vertices_topo           GET /api/v1/meshes/{topo}/vertices?step=150000
  vertices_design         GET /api/v1/meshes/{design}/vertices?step=150000
  breaklines_design       GET /api/v1/meshes/{design}/breaklines
  contours_topo           GET /api/v1/meshes/{topo}/contours?interval=15
  roi_topo                GET /api/v1/meshes/{topo}/vertices/roi?xmin&ymin&xmax&ymax&step=60000
                          bounds = first section origin +/- 150 m
  horizontal_deviation    GET /api/v1/meshes/{topo}/horizontal-deviation?design_mesh_id&sector&longitudinal_step=2&vertical_step=1
  blast_holes_3d          GET /api/v1/blast/holes/3d
  blast_holes_3d_section  GET /api/v1/blast/holes/3d?section_id=0&corridor_m=10
  blast_session_holes     GET /api/v1/blast/{session}/holes

Repetition 1 is cold, repetition 2 is warm (--repeat). Every user waits at a
barrier before each repetition, so repetition r+1 never starts before every user
has finished repetition r. A non-2xx response or transport error is recorded for
its endpoint and the journey continues. An endpoint whose input is missing (no
design or topo mesh, or no section in the session) is recorded as skipped: no
request is sent and it counts as an error.

Response bodies are not parsed: the time is the HTTP round trip including the
body download, not the client-side JSON decode.

A background thread probes GET /api/v1/health every --probe-interval seconds
(own client, timeout 120 s) to detect event-loop stalls. Probe latency includes
failed probes; a failure is a transport error or a non-2xx status.

Run ONLY against a THROWAWAY QA instance whose sessions were seeded from a copy of
real data (see scripts/perf/load_test.py). The production host is refused. The
benchmark is read-only, but the sessions it uses must already exist.

Output: one JSON object on stdout (and in --out if given) with
  config     run parameters (the API key value is never printed)
  users      per user: user, session_id, mesh_ids, first_section, discovery,
             errors [...], repetitions {"1": {endpoint: entry}, "2": {...}}
             entry = {seconds, status_code, bytes, error?, skipped?}
  summary    repetitions {"1": {endpoint: {n, ok, p50_s, p95_s, max_s, bytes_p50}}}
             (percentiles are nearest-rank over 2xx entries only)
  probe      {n, max_s, p95_s, slow_over_1s, failures}
  totals     users, sessions, errors, http_status_counts, wall_s_per_repetition

Exit code: 0 when every request was 2xx and every endpoint was actually sent,
1 otherwise, 2 on invalid usage.

Example:
  PYTHONPATH=. .venv/bin/python scripts/perf/endpoint_bench.py --base-url http://127.0.0.1:8125 --sessions <uuid>,<uuid> --users 10 --repeat 2
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

PRODUCTION_HOSTS = frozenset({"conciliacion-api-ewbb.onrender.com"})
DEFAULT_REPEAT = 2
DEFAULT_TIMEOUT_S = 900.0
DEFAULT_PROBE_INTERVAL_S = 0.5
PROBE_TIMEOUT_S = 120.0
SLOW_PROBE_S = 1.0
VERTICES_STEP = 150000
ROI_HALF_SIZE_M = 150.0
ROI_STEP = 60000
CONTOUR_INTERVAL_M = 15
HORIZONTAL_LONGITUDINAL_STEP = 2
HORIZONTAL_VERTICAL_STEP = 1
BLAST_CORRIDOR_M = 10
ENDPOINT_NAMES = (
    "vertices_topo",
    "vertices_design",
    "breaklines_design",
    "contours_topo",
    "roi_topo",
    "horizontal_deviation",
    "blast_holes_3d",
    "blast_holes_3d_section",
    "blast_session_holes",
)
NEEDS_DESIGN = frozenset({"vertices_design", "breaklines_design", "horizontal_deviation"})
NEEDS_TOPO = frozenset({"vertices_topo", "contours_topo", "roi_topo", "horizontal_deviation"})
NEEDS_SECTION = frozenset({"roi_topo", "horizontal_deviation", "blast_holes_3d_section"})


@dataclass(frozen=True)
class Context:
    session_id: str
    design_mesh_id: str | None
    topo_mesh_id: str | None
    section: dict[str, Any] | None


@dataclass(frozen=True)
class RunConfig:
    base_url: str
    sessions: tuple[str, ...]
    users: int
    repeat: int
    endpoints: tuple[str, ...]
    timeout: float
    probe_interval: float
    api_key: str | None


@dataclass(frozen=True)
class UserRun:
    record: dict[str, Any]
    windows: dict[int, tuple[float, float]] = field(default_factory=dict)


def is_ok(entry: dict[str, Any]) -> bool:
    return is_2xx(entry.get("status_code"))


def is_2xx(status_code: Any) -> bool:
    return isinstance(status_code, int) and not isinstance(status_code, bool) and 200 <= status_code < 300


def percentile(values: Sequence[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def assign_sessions(users: int, sessions: Sequence[str]) -> list[str]:
    return [sessions[index % len(sessions)] for index in range(users)]


def parse_mesh_ids(body: Any) -> tuple[str | None, str | None]:
    if not isinstance(body, dict):
        raise ValueError("/api/v1/session/recovery: expected a JSON object")
    return _optional_id(body.get("design_mesh_id")), _optional_id(body.get("topo_mesh_id"))


def _optional_id(value: Any) -> str | None:
    return str(value) if value else None


def parse_first_section(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, list):
        raise ValueError("/api/v1/sections: expected a JSON list")
    if not body:
        return None
    first = body[0]
    if not isinstance(first, dict):
        raise ValueError("/api/v1/sections: first entry is not an object")
    origin = first.get("origin")
    if not isinstance(origin, (list, tuple)) or len(origin) < 2:
        raise ValueError("/api/v1/sections: first section has no origin [x, y]")
    try:
        x, y = float(origin[0]), float(origin[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"/api/v1/sections: first section origin is not numeric ({exc})") from exc
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("/api/v1/sections: first section origin is not finite")
    return {
        "name": str(first.get("name") or ""),
        "sector": str(first.get("sector") or "").strip(),
        "origin": [x, y],
    }


def missing_inputs(name: str, ctx: Context) -> str | None:
    if name in NEEDS_DESIGN and not ctx.design_mesh_id:
        return "no design mesh in session"
    if name in NEEDS_TOPO and not ctx.topo_mesh_id:
        return "no topo mesh in session"
    if name in NEEDS_SECTION and ctx.section is None:
        return "no sections in session"
    return None


def _require_section(ctx: Context) -> dict[str, Any]:
    if ctx.section is None:
        raise ValueError("endpoint needs a section; none in session")
    return ctx.section


def build_request(name: str, ctx: Context) -> tuple[str, dict[str, Any] | None]:
    if name == "vertices_topo":
        return f"/api/v1/meshes/{ctx.topo_mesh_id}/vertices", {"step": VERTICES_STEP}
    if name == "vertices_design":
        return f"/api/v1/meshes/{ctx.design_mesh_id}/vertices", {"step": VERTICES_STEP}
    if name == "breaklines_design":
        return f"/api/v1/meshes/{ctx.design_mesh_id}/breaklines", None
    if name == "contours_topo":
        return f"/api/v1/meshes/{ctx.topo_mesh_id}/contours", {"interval": CONTOUR_INTERVAL_M}
    if name == "roi_topo":
        origin_x, origin_y = _require_section(ctx)["origin"]
        return f"/api/v1/meshes/{ctx.topo_mesh_id}/vertices/roi", {
            "xmin": origin_x - ROI_HALF_SIZE_M,
            "ymin": origin_y - ROI_HALF_SIZE_M,
            "xmax": origin_x + ROI_HALF_SIZE_M,
            "ymax": origin_y + ROI_HALF_SIZE_M,
            "step": ROI_STEP,
        }
    if name == "horizontal_deviation":
        return f"/api/v1/meshes/{ctx.topo_mesh_id}/horizontal-deviation", {
            "design_mesh_id": ctx.design_mesh_id,
            "sector": _require_section(ctx)["sector"],
            "longitudinal_step": HORIZONTAL_LONGITUDINAL_STEP,
            "vertical_step": HORIZONTAL_VERTICAL_STEP,
        }
    if name == "blast_holes_3d":
        return "/api/v1/blast/holes/3d", None
    if name == "blast_holes_3d_section":
        return "/api/v1/blast/holes/3d", {"section_id": 0, "corridor_m": BLAST_CORRIDOR_M}
    if name == "blast_session_holes":
        return f"/api/v1/blast/{ctx.session_id}/holes", None
    raise ValueError(f"unknown endpoint: {name}")


def send(client: httpx.Client, path: str, params: dict[str, Any] | None) -> tuple[dict[str, Any], httpx.Response | None]:
    started = time.perf_counter()
    try:
        response = client.get(path, params=params)
    except Exception as exc:
        seconds = round(time.perf_counter() - started, 3)
        return {"seconds": seconds, "status_code": None, "bytes": 0, "error": f"{type(exc).__name__}: {exc}"}, None
    seconds = round(time.perf_counter() - started, 3)
    entry: dict[str, Any] = {
        "seconds": seconds,
        "status_code": response.status_code,
        "bytes": len(response.content),
    }
    if not is_ok(entry):
        entry["error"] = f"HTTP {response.status_code}: {response.text[:300]}"
    return entry, response


def discover(client: httpx.Client, session_id: str, record: dict[str, Any]) -> Context:
    recovery_entry, recovery_response = send(client, "/api/v1/session/recovery", None)
    sections_entry, sections_response = send(client, "/api/v1/sections", None)
    record["discovery"] = {"session_recovery": recovery_entry, "sections": sections_entry}
    design_id: str | None = None
    topo_id: str | None = None
    section: dict[str, Any] | None = None
    if recovery_response is not None and is_ok(recovery_entry):
        try:
            design_id, topo_id = parse_mesh_ids(recovery_response.json())
        except ValueError as exc:
            record["errors"].append(f"discovery: {exc}")
    if sections_response is not None and is_ok(sections_entry):
        try:
            section = parse_first_section(sections_response.json())
        except ValueError as exc:
            record["errors"].append(f"discovery: {exc}")
    record["mesh_ids"] = {"design": design_id, "topo": topo_id}
    record["first_section"] = section
    return Context(session_id=session_id, design_mesh_id=design_id, topo_mesh_id=topo_id, section=section)


def run_repetition(client: httpx.Client, ctx: Context, endpoints: Sequence[str]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name in endpoints:
        reason = missing_inputs(name, ctx)
        if reason is not None:
            results[name] = {
                "seconds": 0.0,
                "status_code": None,
                "bytes": 0,
                "error": f"skipped: {reason}",
                "skipped": True,
            }
            continue
        path, params = build_request(name, ctx)
        entry, _ = send(client, path, params)
        results[name] = entry
    return results


def run_user(
    index: int,
    session_id: str,
    cfg: RunConfig,
    barrier: threading.Barrier,
    transport: httpx.BaseTransport | None = None,
) -> UserRun:
    record: dict[str, Any] = {
        "user": index,
        "session_id": session_id,
        "mesh_ids": {"design": None, "topo": None},
        "first_section": None,
        "discovery": {},
        "errors": [],
        "repetitions": {},
    }
    windows: dict[int, tuple[float, float]] = {}
    headers = {"X-Session-ID": session_id}
    if cfg.api_key:
        headers["X-API-Key"] = cfg.api_key
    try:
        with httpx.Client(
            base_url=cfg.base_url,
            headers=headers,
            timeout=cfg.timeout,
            transport=transport,
        ) as client:
            ctx = discover(client, session_id, record)
            for repetition in range(1, cfg.repeat + 1):
                barrier.wait()
                started = time.perf_counter()
                record["repetitions"][str(repetition)] = run_repetition(client, ctx, cfg.endpoints)
                windows[repetition] = (started, time.perf_counter())
    except threading.BrokenBarrierError:
        record["errors"].append("barrier broken: another user failed; remaining repetitions not run")
    except Exception as exc:
        barrier.abort()
        record["errors"].append(f"client: {type(exc).__name__}: {exc}")
    return UserRun(record=record, windows=windows)


class HealthProbe:
    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        interval: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._headers = headers
        self._interval = interval
        self._transport = transport
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="health-probe", daemon=True)
        self.samples: list[tuple[float, bool]] = []

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=PROBE_TIMEOUT_S + 5.0)

    def _loop(self) -> None:
        with httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=PROBE_TIMEOUT_S,
            transport=self._transport,
        ) as client:
            while not self._stop.is_set():
                started = time.perf_counter()
                ok = False
                try:
                    ok = is_2xx(client.get("/api/v1/health").status_code)
                except Exception:
                    ok = False
                elapsed = time.perf_counter() - started
                self.samples.append((round(elapsed, 3), ok))
                self._stop.wait(max(0.0, self._interval - elapsed))


def summarize_probe(samples: Sequence[tuple[float, bool]]) -> dict[str, Any]:
    latencies = [seconds for seconds, _ in samples]
    return {
        "n": len(samples),
        "max_s": _round(max(latencies)) if latencies else None,
        "p95_s": _round(percentile(latencies, 95)),
        "slow_over_1s": sum(1 for seconds in latencies if seconds > SLOW_PROBE_S),
        "failures": sum(1 for _, ok in samples if not ok),
    }


def summarize(users: Sequence[dict[str, Any]], endpoints: Sequence[str], repeat: int) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for repetition in range(1, repeat + 1):
        key = str(repetition)
        per_endpoint: dict[str, Any] = {}
        for name in endpoints:
            entries: list[dict[str, Any]] = []
            for user in users:
                entry = user["repetitions"].get(key, {}).get(name)
                if entry is not None:
                    entries.append(entry)
            ok = [entry for entry in entries if is_ok(entry)]
            seconds = [entry["seconds"] for entry in ok]
            per_endpoint[name] = {
                "n": len(entries),
                "ok": len(ok),
                "p50_s": _round(percentile(seconds, 50)),
                "p95_s": _round(percentile(seconds, 95)),
                "max_s": _round(max(seconds)) if seconds else None,
                "bytes_p50": _int_or_none(percentile([float(entry["bytes"]) for entry in ok], 50)),
            }
        summary[key] = per_endpoint
    return summary


def _int_or_none(value: float | None) -> int | None:
    return None if value is None else int(value)


def wall_per_repetition(runs: Sequence[UserRun], repeat: int) -> dict[str, float | None]:
    wall: dict[str, float | None] = {}
    for repetition in range(1, repeat + 1):
        windows = [run.windows[repetition] for run in runs if repetition in run.windows]
        if windows:
            wall[str(repetition)] = round(max(end for _, end in windows) - min(start for start, _ in windows), 3)
        else:
            wall[str(repetition)] = None
    return wall


def iter_attempts(user: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from user["discovery"].values()
    for repetition in user["repetitions"].values():
        yield from repetition.values()


def totals(
    users: Sequence[dict[str, Any]],
    session_count: int,
    wall: dict[str, float | None],
) -> dict[str, Any]:
    codes: Counter[str] = Counter()
    errors = 0
    for user in users:
        errors += len(user["errors"])
        for entry in iter_attempts(user):
            if not is_ok(entry):
                errors += 1
            if entry.get("skipped"):
                continue
            key = "transport_error" if entry.get("status_code") is None else str(entry["status_code"])
            codes[key] += 1
    return {
        "users": len(users),
        "sessions": session_count,
        "errors": errors,
        "http_status_counts": dict(sorted(codes.items())),
        "wall_s_per_repetition": wall,
    }


def exit_status(result: dict[str, Any]) -> int:
    return 0 if result["totals"]["errors"] == 0 else 1


def run_bench(cfg: RunConfig, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    headers = {"X-API-Key": cfg.api_key} if cfg.api_key else {}
    barrier = threading.Barrier(cfg.users)
    probe = HealthProbe(cfg.base_url, headers, cfg.probe_interval, transport)
    assignments = assign_sessions(cfg.users, cfg.sessions)
    probe.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.users) as pool:
            futures = [
                pool.submit(run_user, index, session_id, cfg, barrier, transport)
                for index, session_id in enumerate(assignments, start=1)
            ]
            runs = [future.result() for future in futures]
    finally:
        probe.stop()
    users = [run.record for run in runs]
    return {
        "config": {
            "base_url": cfg.base_url,
            "sessions": list(cfg.sessions),
            "users": cfg.users,
            "repeat": cfg.repeat,
            "endpoints": list(cfg.endpoints),
            "timeout_s": cfg.timeout,
            "probe_interval_s": cfg.probe_interval,
            "api_key_sent": cfg.api_key is not None,
        },
        "users": users,
        "summary": summarize(users, cfg.endpoints, cfg.repeat),
        "probe": summarize_probe(probe.samples),
        "totals": totals(users, len(cfg.sessions), wall_per_repetition(runs, cfg.repeat)),
    }


def parse_sessions(raw: str, parser: argparse.ArgumentParser) -> tuple[str, ...]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        parser.error("--sessions must list at least one session id")
    seen: set[str] = set()
    for value in values:
        try:
            uuid.UUID(value)
        except ValueError:
            parser.error(f"invalid session id (expected UUID): {value!r}")
        if value in seen:
            parser.error(f"duplicate session id: {value}")
        seen.add(value)
    return tuple(values)


def parse_endpoints(raw: str, parser: argparse.ArgumentParser) -> tuple[str, ...]:
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        parser.error("--endpoints must list at least one endpoint")
    unknown = sorted(set(names) - set(ENDPOINT_NAMES))
    if unknown:
        parser.error(f"unknown endpoint(s): {','.join(unknown)}; valid: {','.join(ENDPOINT_NAMES)}")
    if len(set(names)) != len(names):
        parser.error("--endpoints must not repeat names")
    return tuple(name for name in ENDPOINT_NAMES if name in names)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HTTP benchmark of the heavy read endpoints for a THROWAWAY QA instance of the conciliacion API.",
        epilog=(
            "Never point this at production. Read-only, but the sessions must already exist on the QA instance "
            "(seed them with scripts/perf/load_test.py)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", required=True, help="Base URL of the QA instance, e.g. http://127.0.0.1:8125")
    parser.add_argument("--sessions", required=True, help="Comma-separated session ids (UUID) that exist on the QA instance")
    parser.add_argument(
        "--users",
        type=int,
        default=None,
        help="Simulated users, run concurrently (default: number of sessions); user i uses sessions[i %% S]",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=DEFAULT_REPEAT,
        help="Repetitions of the journey: 1 = cold, 2 = warm (default 2); all users finish r before r+1 starts",
    )
    parser.add_argument(
        "--endpoints",
        default=",".join(ENDPOINT_NAMES),
        help="Comma-separated endpoint names to run, from: " + ",".join(ENDPOINT_NAMES) + " (default: all)",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="Timeout per request in seconds (default 900)")
    parser.add_argument("--api-key", help="Optional X-API-Key header value")
    parser.add_argument(
        "--probe-interval",
        type=float,
        default=DEFAULT_PROBE_INTERVAL_S,
        help="Seconds between GET /api/v1/health probes (default 0.5)",
    )
    parser.add_argument("--out", type=Path, help="Optional path to also write the JSON result")
    return parser


def build_config(args: argparse.Namespace, parser: argparse.ArgumentParser) -> RunConfig:
    parts = urlsplit(args.base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        parser.error("--base-url must be an absolute http(s) URL")
    if parts.hostname.lower() in PRODUCTION_HOSTS:
        parser.error(f"refusing to run against production host {parts.hostname}")
    sessions = parse_sessions(args.sessions, parser)
    users = args.users if args.users is not None else len(sessions)
    if users < 1:
        parser.error("--users must be >= 1")
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")
    if args.probe_interval <= 0:
        parser.error("--probe-interval must be > 0")
    return RunConfig(
        base_url=args.base_url.rstrip("/"),
        sessions=sessions,
        users=users,
        repeat=args.repeat,
        endpoints=parse_endpoints(args.endpoints, parser),
        timeout=args.timeout,
        probe_interval=args.probe_interval,
        api_key=args.api_key,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = build_config(args, parser)
    print(
        f"endpoint bench: {cfg.base_url} users={cfg.users} sessions={len(cfg.sessions)} "
        f"repeat={cfg.repeat} endpoints={len(cfg.endpoints)} (QA instance only; read-only)",
        file=sys.stderr,
    )
    result = run_bench(cfg)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return exit_status(result)


if __name__ == "__main__":
    sys.exit(main())
