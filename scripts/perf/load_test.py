#!/usr/bin/env python3
"""HTTP load test for a THROWAWAY QA instance of the conciliacion API.

Simulates N concurrent users. Each user gets its own session (a fresh uuid4
sent as the X-Session-ID header) and runs the real journey in order:

  upload    POST /api/v1/meshes/upload      multipart: file + type=design, then type=topo
  sections  POST /api/v1/sections/manual    JSON list of section definitions from sections.json
            GET  /api/v1/sections           stored sections must match the file
  process   POST /api/v1/process            synchronous, no body; 409 if a run is active
            GET  /api/v1/process/status     must report "complete"
  results   GET  /api/v1/process/results    must be a non-empty list

A user stops at its first failing phase. Phase timings are wall seconds for the
whole phase; status_code is the last HTTP status of that phase (or the failing one).

NEVER run this against production. It writes data (meshes, sections, runs).
There is no session delete endpoint, so nothing is cleaned up: throw away the
QA instance's data dir afterwards. The production API host is refused.

Data dir (default data/perf-real, relative to the repo) must contain design.stl,
topo.stl and sections.json. Meshes are streamed from disk, one open file per request.

Auth: --api-key sends X-API-Key (CONCILIACION_API_KEY on the server). --auth USER:PASS
sends HTTP Basic, for a reverse proxy in front of the QA instance; the API itself
does not check it.

Output: one JSON object on stdout (and in --out if given) with:
  config   run parameters
  users    per user: user, session_id, phases {name: {seconds, status_code, ok}},
           errors [...], details (n_sections, n_results, meshes...), requests [...]
  summary  per phase: n (users that reached it), ok (passed), p50_s, p95_s, max_s
           (percentiles are nearest-rank over passing phases only)
  totals   users, errors, http_status_counts, wall_s

Exit code: 0 when there are no errors (every request 2xx and every check passed),
1 otherwise, 2 on invalid usage.

Example:
  PYTHONPATH=. .venv/bin/python scripts/perf/load_test.py --base-url http://127.0.0.1:8123 --users 2
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "perf-real"
PHASE_NAMES = ("upload", "sections", "process", "results")
PRODUCTION_HOSTS = frozenset({"conciliacion-api-ewbb.onrender.com"})
SECTION_FIELDS = ("name", "origin", "azimuth", "length", "length_up", "length_down", "sector")
COORD_TOLERANCE = 1e-6
AZIMUTH_TOLERANCE = 0.0051


class PhaseFailed(Exception):
    def __init__(self, message: str, status_code: int | None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LoadData:
    data_dir: Path
    design: Path
    topo: Path
    sections: list[dict[str, Any]]


@dataclass(frozen=True)
class RunConfig:
    base_url: str
    timeout: float
    phases: tuple[str, ...]
    stagger: float
    data: LoadData
    auth: httpx.BasicAuth | None
    api_key: str | None


class Journey:
    def __init__(self, client: httpx.Client, cfg: RunConfig, record: dict[str, Any]) -> None:
        self.client = client
        self.cfg = cfg
        self.record = record
        self.last_status: int | None = None

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        started = time.perf_counter()
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            self.last_status = None
            self._log(method, path, None, started)
            raise PhaseFailed(f"{method} {path}: {type(exc).__name__}: {exc}", None) from exc
        self.last_status = response.status_code
        self._log(method, path, response.status_code, started)
        if not 200 <= response.status_code < 300:
            raise PhaseFailed(
                f"{method} {path}: HTTP {response.status_code}: {response.text[:300]}",
                response.status_code,
            )
        return response

    def check(self, passed: bool, message: str) -> None:
        if not passed:
            raise PhaseFailed(message, self.last_status)

    def run_phase(self, name: str) -> tuple[int | None, str | None]:
        self.last_status = None
        try:
            getattr(self, name)()
        except PhaseFailed as exc:
            return exc.status_code, str(exc)
        except Exception as exc:
            return self.last_status, f"{type(exc).__name__}: {exc}"
        return self.last_status, None

    def upload(self) -> None:
        for mesh_type, path in (("design", self.cfg.data.design), ("topo", self.cfg.data.topo)):
            with path.open("rb") as handle:
                response = self.request(
                    "POST",
                    "/api/v1/meshes/upload",
                    files={"file": (path.name, handle, "application/octet-stream")},
                    data={"type": mesh_type},
                )
            body = response.json()
            self.check("mesh_id" in body, f"upload {mesh_type}: response has no mesh_id")
            self.record["details"][f"{mesh_type}_mesh_id"] = body["mesh_id"]
            self.record["details"][f"{mesh_type}_n_faces"] = body.get("n_faces")

    def sections(self) -> None:
        expected = self.cfg.data.sections
        self.request("POST", "/api/v1/sections/manual", json=expected)
        stored = self.request("GET", "/api/v1/sections").json()
        self.check(isinstance(stored, list), "GET /api/v1/sections: body is not a list")
        self.record["details"]["n_sections"] = len(stored)
        problems = compare_sections(expected, stored)
        self.check(not problems, "stored sections differ from file: " + "; ".join(problems[:5]))

    def process(self) -> None:
        body = self.request("POST", "/api/v1/process").json()
        self.check(
            body.get("status") == "complete",
            f"POST /api/v1/process: status={body.get('status')!r}",
        )
        status = self.request("GET", "/api/v1/process/status").json()
        self.check(
            status.get("status") == "complete",
            f"GET /api/v1/process/status: status={status.get('status')!r}",
        )
        self.record["details"]["process_total_sections"] = body.get("total_sections")
        self.record["details"]["process_total_results"] = body.get("total_results")

    def results(self) -> None:
        rows = self.request("GET", "/api/v1/process/results").json()
        self.check(isinstance(rows, list) and len(rows) > 0, "GET /api/v1/process/results: empty result set")
        self.record["details"]["n_results"] = len(rows)

    def _log(self, method: str, path: str, status_code: int | None, started: float) -> None:
        self.record["requests"].append(
            {
                "method": method,
                "path": path,
                "status_code": status_code,
                "seconds": round(time.perf_counter() - started, 3),
            }
        )


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _same_value(field: str, want: Any, got: Any) -> bool:
    if want is None or got is None:
        return want is None and got is None
    if field in ("name", "sector"):
        return want == got
    if field == "origin":
        if not isinstance(got, (list, tuple)) or len(got) != len(want):
            return False
        return all(_close(w, g, COORD_TOLERANCE) for w, g in zip(want, got))
    tolerance = AZIMUTH_TOLERANCE if field == "azimuth" else COORD_TOLERANCE
    return _close(want, got, tolerance)


def _close(want: Any, got: Any, tolerance: float) -> bool:
    got_number = _as_number(got)
    return got_number is not None and abs(float(want) - got_number) <= tolerance


def compare_sections(expected: list[dict[str, Any]], stored: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    if len(stored) != len(expected):
        problems.append(f"count {len(stored)} != {len(expected)}")
    for index, (want, got) in enumerate(zip(expected, stored)):
        if not isinstance(got, dict):
            problems.append(f"#{index}: stored entry is not an object")
            continue
        for field in SECTION_FIELDS:
            if not _same_value(field, want.get(field), got.get(field)):
                problems.append(
                    f"#{index} {want.get('name')} {field}: stored {got.get(field)!r}, file {want.get(field)!r}"
                )
    return problems


def run_user(index: int, cfg: RunConfig) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "user": index,
        "session_id": session_id,
        "phases": {},
        "errors": [],
        "details": {},
        "requests": [],
    }
    if cfg.stagger and index > 1:
        time.sleep((index - 1) * cfg.stagger)
    headers = {"X-Session-ID": session_id}
    if cfg.api_key:
        headers["X-API-Key"] = cfg.api_key
    try:
        with httpx.Client(
            base_url=cfg.base_url,
            headers=headers,
            timeout=cfg.timeout,
            auth=cfg.auth,
        ) as client:
            journey = Journey(client, cfg, record)
            for name in cfg.phases:
                started = time.perf_counter()
                status_code, error = journey.run_phase(name)
                record["phases"][name] = {
                    "seconds": round(time.perf_counter() - started, 3),
                    "status_code": status_code,
                    "ok": error is None,
                }
                if error is not None:
                    record["errors"].append(f"{name}: {error}")
                    break
    except Exception as exc:
        record["errors"].append(f"client: {type(exc).__name__}: {exc}")
    return record


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(users: list[dict[str, Any]], phases: tuple[str, ...]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name in phases:
        entries = [u["phases"][name] for u in users if name in u["phases"]]
        ok_seconds = [e["seconds"] for e in entries if e["ok"]]
        summary[name] = {
            "n": len(entries),
            "ok": len(ok_seconds),
            "p50_s": percentile(ok_seconds, 50),
            "p95_s": percentile(ok_seconds, 95),
            "max_s": max(ok_seconds) if ok_seconds else None,
        }
    return summary


def totals(users: list[dict[str, Any]], wall_s: float) -> dict[str, Any]:
    codes: Counter[str] = Counter()
    for user in users:
        for request in user["requests"]:
            key = "transport_error" if request["status_code"] is None else str(request["status_code"])
            codes[key] += 1
    return {
        "users": len(users),
        "errors": sum(len(u["errors"]) for u in users),
        "http_status_counts": dict(sorted(codes.items())),
        "wall_s": round(wall_s, 3),
    }


def load_sections(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: expected a non-empty JSON list")
    sections: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        try:
            origin = entry["origin"]
            sections.append(
                {
                    "name": str(entry["name"]),
                    "origin": [float(origin[0]), float(origin[1])],
                    "azimuth": float(entry["azimuth"]),
                    "length": float(entry["length"]),
                    "length_up": _optional_float(entry.get("length_up")),
                    "length_down": _optional_float(entry.get("length_down")),
                    "sector": str(entry.get("sector") or ""),
                }
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: section #{index} is invalid ({type(exc).__name__}: {exc})") from exc
    return sections


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HTTP load test for a THROWAWAY QA instance of the conciliacion API.",
        epilog=(
            "Never point this at production. Data created on the QA instance is not deleted by "
            "this script (no session delete endpoint): discard the instance's data dir afterwards."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", required=True, help="Base URL of the QA instance, e.g. http://127.0.0.1:8123")
    parser.add_argument("--users", type=int, default=10, help="Simulated users, run concurrently (default 10)")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory with design.stl, topo.stl, sections.json (default: data/perf-real in the repo)",
    )
    parser.add_argument(
        "--stagger", type=float, default=0.0, help="Seconds between user starts; user i starts at (i-1)*STAGGER"
    )
    parser.add_argument(
        "--phases",
        default=",".join(PHASE_NAMES),
        help="Comma-separated phases in run order, from: upload,sections,process,results (default: all)",
    )
    parser.add_argument("--timeout", type=float, default=900.0, help="Timeout per request in seconds (default 900)")
    parser.add_argument("--auth", metavar="USER:PASS", help="Optional HTTP Basic credentials (see module help)")
    parser.add_argument("--api-key", help="Optional X-API-Key header value (see module help)")
    parser.add_argument("--out", type=Path, help="Optional path to also write the JSON result")
    return parser


def build_config(args: argparse.Namespace, parser: argparse.ArgumentParser) -> RunConfig:
    parts = urlsplit(args.base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        parser.error("--base-url must be an absolute http(s) URL")
    if parts.hostname.lower() in PRODUCTION_HOSTS:
        parser.error(f"refusing to run against production host {parts.hostname}")
    if args.users < 1:
        parser.error("--users must be >= 1")
    if args.stagger < 0:
        parser.error("--stagger must be >= 0")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")
    phases = tuple(p.strip() for p in args.phases.split(",") if p.strip())
    if not phases or any(p not in PHASE_NAMES for p in phases) or len(set(phases)) != len(phases):
        parser.error(f"--phases must be unique names from: {','.join(PHASE_NAMES)}")
    auth = None
    if args.auth is not None:
        if ":" not in args.auth:
            parser.error("--auth must be USER:PASS")
        user, password = args.auth.split(":", 1)
        auth = httpx.BasicAuth(user, password)

    data_dir = args.data_dir if args.data_dir.is_absolute() else Path.cwd() / args.data_dir
    design = data_dir / "design.stl"
    topo = data_dir / "topo.stl"
    sections_path = data_dir / "sections.json"
    if "upload" in phases:
        for mesh in (design, topo):
            if not mesh.is_file():
                parser.error(f"missing mesh file: {mesh}")
    sections: list[dict[str, Any]] = []
    if "sections" in phases:
        if not sections_path.is_file():
            parser.error(f"missing sections file: {sections_path}")
        try:
            sections = load_sections(sections_path)
        except (ValueError, json.JSONDecodeError) as exc:
            parser.error(str(exc))

    return RunConfig(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout,
        phases=phases,
        stagger=args.stagger,
        data=LoadData(data_dir=data_dir, design=design, topo=topo, sections=sections),
        auth=auth,
        api_key=args.api_key,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = build_config(args, parser)
    print(
        f"load test: {cfg.base_url} users={args.users} phases={','.join(cfg.phases)} "
        "(QA instance only; data is not cleaned up)",
        file=sys.stderr,
    )
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [pool.submit(run_user, index, cfg) for index in range(1, args.users + 1)]
        users = [future.result() for future in futures]
    wall_s = time.perf_counter() - started

    result = {
        "config": {
            "base_url": cfg.base_url,
            "users": args.users,
            "phases": list(cfg.phases),
            "stagger_s": cfg.stagger,
            "timeout_s": cfg.timeout,
            "data_dir": str(cfg.data.data_dir),
            "sections_in_file": len(cfg.data.sections),
            "mesh_bytes": {
                "design": cfg.data.design.stat().st_size if "upload" in cfg.phases else None,
                "topo": cfg.data.topo.stat().st_size if "upload" in cfg.phases else None,
            },
        },
        "users": users,
        "summary": summarize(users, cfg.phases),
        "totals": totals(users, wall_s),
    }
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if result["totals"]["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
