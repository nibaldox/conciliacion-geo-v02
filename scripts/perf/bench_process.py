"""Benchmark the cut -> extract -> compare section pipeline behind POST /process.

Prints one JSON line per scenario on stdout; progress and profiler output go to stderr.

Modes:
    load     time and memory of loading the topo mesh
    process  N simultaneous simulated users, each running the full pipeline
    profile  serial run under cProfile with per-stage timings
"""

from __future__ import annotations

import argparse
import copy
import cProfile
import json
import os
import pstats
import resource
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "CONCILIACION_DATA_DIR" not in os.environ:
    os.environ["CONCILIACION_DATA_DIR"] = tempfile.mkdtemp(prefix="perf-bench-")

from api.routers.process import _guided_comparison, _section_from_dict  # noqa: E402
from core import extract_parameters, load_mesh  # noqa: E402
from core.config import DETECTION, TOLERANCES  # noqa: E402
from core.param_extractor import ExtractionResult  # noqa: E402
from core.section_cutter import cut_mesh_with_section_diagnostics  # noqa: E402

RESOLUTION_M = 0.1
DATA_DIR_ENV = "CONCILIACION_PERF_DATA"
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "perf-real"
MODES = ("load", "process", "profile")
TOP_FUNCTIONS = 15


@dataclass(frozen=True)
class SectionOutput:
    design: ExtractionResult
    topo: ExtractionResult
    comparisons: List[Dict[str, Any]]
    warnings_design: Tuple[str, ...]
    warnings_topo: Tuple[str, ...]


def resolve_data_dir(raw: Optional[str]) -> Path:
    chosen = raw or os.environ.get(DATA_DIR_ENV) or DEFAULT_DATA_DIR
    return Path(chosen).expanduser().resolve()


def input_paths(data_dir: Path) -> Tuple[Path, Path, Path]:
    paths = (data_dir / "design.stl", data_dir / "topo.stl", data_dir / "sections.json")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit(f"missing input files: {', '.join(missing)}")
    return paths


def load_section_dicts(path: Path) -> List[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_sections(raw: Sequence[dict]) -> list:
    return [_section_from_dict(item) for item in raw]


def default_tolerances() -> Dict[str, Dict[str, float]]:
    return copy.deepcopy(
        {
            "bench_height": TOLERANCES.bench_height,
            "face_angle": TOLERANCES.face_angle,
            "berm_width": TOLERANCES.berm_width,
            "inter_ramp_angle": TOLERANCES.inter_ramp_angle,
            "overall_angle": TOLERANCES.overall_angle,
        }
    )


def new_timings() -> Dict[str, float]:
    return {"cut": 0.0, "extract": 0.0, "compare": 0.0}


def _extract(profile: Any, section: Any) -> ExtractionResult:
    return extract_parameters(
        profile.distances,
        profile.elevations,
        section.name,
        section.sector,
        RESOLUTION_M,
        DETECTION.face_threshold,
        DETECTION.berm_threshold,
    )


def run_section(
    mesh_design: Any,
    mesh_topo: Any,
    section: Any,
    tolerances: Dict[str, Dict[str, float]],
    timings: Optional[Dict[str, float]] = None,
) -> SectionOutput:
    clock = time.perf_counter
    started = clock()
    design_cut = cut_mesh_with_section_diagnostics(mesh_design, section)
    topo_cut = cut_mesh_with_section_diagnostics(mesh_topo, section)
    if timings is not None:
        timings["cut"] += clock() - started

    design_profile = design_cut.profile
    topo_profile = topo_cut.profile
    started = clock()
    if design_profile is not None:
        p_design = _extract(design_profile, section)
    else:
        p_design = ExtractionResult(section_name=section.name, sector=section.sector)
    if topo_profile is not None:
        p_topo = _extract(topo_profile, section)
    else:
        p_topo = ExtractionResult(section_name=section.name, sector=section.sector)
    if timings is not None:
        timings["extract"] += clock() - started

    comparisons: List[Dict[str, Any]] = []
    if design_profile is not None and topo_profile is not None:
        started = clock()
        comparisons = _guided_comparison(
            p_design,
            p_topo,
            tolerances,
            (topo_profile.distances, topo_profile.elevations),
        )
        if timings is not None:
            timings["compare"] += clock() - started

    return SectionOutput(
        design=p_design,
        topo=p_topo,
        comparisons=comparisons,
        warnings_design=tuple(design_cut.warnings),
        warnings_topo=tuple(topo_cut.warnings),
    )


def run_user(
    mesh_design: Any,
    mesh_topo: Any,
    sections: Sequence[Any],
    tolerances: Dict[str, Dict[str, float]],
) -> Tuple[float, List[str]]:
    def work(section: Any) -> Optional[str]:
        try:
            run_section(mesh_design, mesh_topo, section, tolerances)
        except Exception as exc:
            return f"{section.name}: {exc!r}"
        return None

    started = time.perf_counter()
    with ThreadPoolExecutor() as executor:
        failures = [item for item in executor.map(work, sections) if item is not None]
    return time.perf_counter() - started, failures


def run_serial(
    mesh_design: Any,
    mesh_topo: Any,
    sections: Sequence[Any],
    tolerances: Dict[str, Dict[str, float]],
    timings: Dict[str, float],
) -> List[str]:
    failures: List[str] = []
    for section in sections:
        try:
            run_section(mesh_design, mesh_topo, section, tolerances, timings)
        except Exception as exc:
            failures.append(f"{section.name}: {exc!r}")
    return failures


def _load_topo_copies(topo_path: Path, users: int) -> List[Any]:
    with ThreadPoolExecutor(max_workers=users) as pool:
        return list(pool.map(lambda _: load_mesh(str(topo_path)), range(users)))


def peak_rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def steady_rss_mb() -> Optional[float]:
    try:
        with open("/proc/self/status", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except OSError:
        return None
    return None


def git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _memory_fields() -> Dict[str, Optional[float]]:
    return {"peak_rss_mb": peak_rss_mb(), "steady_rss_mb": steady_rss_mb()}


def _report_failures(failures: List[str]) -> None:
    if not failures:
        return
    print(f"{len(failures)} section(s) failed:", file=sys.stderr)
    for item in failures[:10]:
        print(f"  {item}", file=sys.stderr)


def run_load(topo_path: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    mesh_topo = load_mesh(str(topo_path))
    load_wall_s = time.perf_counter() - started
    record: Dict[str, Any] = {"load_wall_s": round(load_wall_s, 4)}
    record.update(_memory_fields())
    del mesh_topo
    return record


def run_process(
    design_path: Path,
    topo_path: Path,
    sections: Sequence[Any],
    users: int,
    distinct: bool,
) -> Dict[str, Any]:
    tolerances = default_tolerances()
    started = time.perf_counter()
    mesh_design = load_mesh(str(design_path))
    if distinct:
        topo_meshes = _load_topo_copies(topo_path, users)
    else:
        shared_topo = load_mesh(str(topo_path))
        topo_meshes = [shared_topo] * users
    load_wall_s = time.perf_counter() - started

    go = threading.Event()

    def user(mesh_topo: Any) -> Tuple[float, List[str]]:
        go.wait()
        return run_user(mesh_design, mesh_topo, sections, tolerances)

    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(user, mesh_topo) for mesh_topo in topo_meshes]
        began = time.perf_counter()
        go.set()
        outcomes = [future.result() for future in futures]
        wall_s = time.perf_counter() - began

    _report_failures([item for _, failures in outcomes for item in failures])
    record: Dict[str, Any] = {
        "load_wall_s": round(load_wall_s, 4),
        "wall_s": round(wall_s, 4),
        "per_user_max_s": round(max(elapsed for elapsed, _ in outcomes), 4),
    }
    record.update(_memory_fields())
    return record


def run_profile(
    design_path: Path,
    topo_path: Path,
    sections: Sequence[Any],
) -> Dict[str, Any]:
    tolerances = default_tolerances()
    started = time.perf_counter()
    mesh_design = load_mesh(str(design_path))
    mesh_topo = load_mesh(str(topo_path))
    load_wall_s = time.perf_counter() - started

    timings = new_timings()
    profiler = cProfile.Profile()
    profiler.enable()
    began = time.perf_counter()
    failures = run_serial(mesh_design, mesh_topo, sections, tolerances, timings)
    wall_s = time.perf_counter() - began
    profiler.disable()

    _report_failures(failures)
    print(
        f"cut {timings['cut']:.3f}s  extract {timings['extract']:.3f}s  "
        f"compare {timings['compare']:.3f}s  wall(under cProfile) {wall_s:.3f}s",
        file=sys.stderr,
    )
    pstats.Stats(profiler, stream=sys.stderr).sort_stats("tottime").print_stats(TOP_FUNCTIONS)

    record: Dict[str, Any] = {
        "load_wall_s": round(load_wall_s, 4),
        "wall_s": round(wall_s, 4),
        "per_user_max_s": round(wall_s, 4),
    }
    record.update(_memory_fields())
    return record


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark the section pipeline (POST /process).")
    parser.add_argument("--data-dir", default=None, help=f"default: ${DATA_DIR_ENV} or data/perf-real")
    parser.add_argument("--mode", choices=MODES, default="process")
    parser.add_argument("--users", type=int, default=1, help="simultaneous simulated users (process mode)")
    parser.add_argument("--distinct", action="store_true", help="each user loads its own topo mesh")
    parser.add_argument("--sections", type=int, default=None, help="first K sections (default all)")
    args = parser.parse_args(argv)
    if args.users < 1:
        parser.error("--users must be >= 1")
    if args.sections is not None and args.sections < 1:
        parser.error("--sections must be >= 1")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    data_dir = resolve_data_dir(args.data_dir)
    design_path, topo_path, sections_path = input_paths(data_dir)
    sections = build_sections(load_section_dicts(sections_path))
    if args.sections is not None:
        sections = sections[: args.sections]

    if args.mode == "load":
        users, distinct, n_sections = args.users, args.distinct, None
        measured = run_load(topo_path)
    elif args.mode == "process":
        users, distinct, n_sections = args.users, args.distinct, len(sections)
        measured = run_process(design_path, topo_path, sections, args.users, args.distinct)
    else:
        users, distinct, n_sections = 1, False, len(sections)
        measured = run_profile(design_path, topo_path, sections)

    record: Dict[str, Any] = {
        "mode": args.mode,
        "users": users,
        "distinct": distinct,
        "n_sections": n_sections,
        "load_wall_s": None,
        "wall_s": None,
        "per_user_max_s": None,
        "peak_rss_mb": None,
        "steady_rss_mb": None,
        "git_sha": git_sha(),
    }
    record.update(measured)
    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
