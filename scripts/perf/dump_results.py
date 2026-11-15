"""Deterministic dump of section pipeline outputs for result-equality gates.

Runs the cut -> extract -> guided-compare pipeline serially in section order and
serialises every output with plain JSON types. ``--out`` writes the dump;
``--compare`` recomputes in memory and checks it against a previous dump
(exit 0 when equal, 1 otherwise).
"""

from __future__ import annotations

import argparse
import enum
import json
import math
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TOLERANCE = 1e-9
IGNORED_TOP_LEVEL_KEYS = frozenset({"git_sha"})


def to_plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return to_plain(value.tolist())
    if isinstance(value, np.generic):
        return to_plain(value.item())
    if isinstance(value, enum.Enum):
        return to_plain(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_plain(getattr(value, field.name)) for field in fields(value)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"cannot serialise {type(value).__name__}")


def normalise(payload: Any) -> Any:
    return json.loads(json.dumps(to_plain(payload), allow_nan=True))


def _label(path: str) -> str:
    return path or "<root>"


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _mismatch(path: str, a: Any, b: Any) -> str:
    return f"{_label(path)}: baseline={a!r} current={b!r}"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numbers_equal(a: Any, b: Any, tol: float) -> bool:
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    x, y = float(a), float(b)
    if math.isnan(x) or math.isnan(y):
        return math.isnan(x) and math.isnan(y)
    if math.isinf(x) or math.isinf(y):
        return x == y
    return abs(x - y) <= tol


def _dict_difference(a: dict, b: dict, path: str, tol: float) -> Optional[str]:
    for key in sorted(set(a) | set(b), key=str):
        child = _join(path, str(key))
        if key not in b:
            return f"{child}: missing from current"
        if key not in a:
            return f"{child}: missing from baseline"
        message = _first_difference(a[key], b[key], child, tol)
        if message is not None:
            return message
    return None


def _sequence_difference(a: Sequence[Any], b: Sequence[Any], path: str, tol: float) -> Optional[str]:
    if len(a) != len(b):
        return f"{_label(path)}: list length baseline={len(a)} current={len(b)}"
    for index, (x, y) in enumerate(zip(a, b)):
        message = _first_difference(x, y, f"{path}[{index}]", tol)
        if message is not None:
            return message
    return None


def _first_difference(a: Any, b: Any, path: str, tol: float) -> Optional[str]:
    if isinstance(a, bool) or isinstance(b, bool):
        if isinstance(a, bool) and isinstance(b, bool) and a == b:
            return None
        return _mismatch(path, a, b)
    if _is_number(a) and _is_number(b):
        return None if _numbers_equal(a, b, tol) else _mismatch(path, a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        return _dict_difference(a, b, path, tol)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return _sequence_difference(a, b, path, tol)
    if type(a) is type(b) and a == b:
        return None
    return _mismatch(path, a, b)


def compare_json(a: Any, b: Any, tol: float = DEFAULT_TOLERANCE) -> Optional[str]:
    """Return None when ``a`` (baseline) equals ``b`` (current), else the first differing path.

    Numbers match within ``tol`` (ints exactly, NaN equals NaN, same-sign inf equal);
    strings, bools and None match exactly; lists match in order; dict key sets must match.
    A top-level ``git_sha`` key is ignored.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        a = {key: value for key, value in a.items() if key not in IGNORED_TOP_LEVEL_KEYS}
        b = {key: value for key, value in b.items() if key not in IGNORED_TOP_LEVEL_KEYS}
    return _first_difference(a, b, "", tol)


def build_dump(data_dir_arg: Optional[str], limit: Optional[int]) -> dict:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import bench_process as bench
    from api.routers.process import _extraction_to_dict
    from core import load_mesh

    data_dir = bench.resolve_data_dir(data_dir_arg)
    design_path, topo_path, sections_path = bench.input_paths(data_dir)
    sections = bench.build_sections(bench.load_section_dicts(sections_path))
    if limit is not None:
        sections = sections[:limit]

    mesh_design = load_mesh(str(design_path))
    mesh_topo = load_mesh(str(topo_path))
    tolerances = bench.default_tolerances()

    entries = []
    for section in sections:
        output = bench.run_section(mesh_design, mesh_topo, section, tolerances)
        entries.append(
            {
                "name": section.name,
                "design": _extraction_to_dict(output.design),
                "topo": _extraction_to_dict(output.topo),
                "comparisons": output.comparisons,
                "warnings": {
                    "design": list(output.warnings_design),
                    "topo": list(output.warnings_topo),
                },
            }
        )
    return normalise({"git_sha": bench.git_sha(), "sections": entries})


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic dump of section pipeline outputs.")
    parser.add_argument("--data-dir", default=None, help="default: $CONCILIACION_PERF_DATA or data/perf-real")
    parser.add_argument("--sections", type=int, default=None, help="first K sections (default all)")
    parser.add_argument("--out", type=Path, default=None, help="write the dump to this JSON file")
    parser.add_argument("--compare", type=Path, default=None, help="compare a fresh run against this dump")
    args = parser.parse_args(argv)
    if args.out is None and args.compare is None:
        parser.error("pass --out, --compare or both")
    if args.sections is not None and args.sections < 1:
        parser.error("--sections must be >= 1")

    payload = build_dump(args.data_dir, args.sections)
    count = len(payload["sections"])

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, allow_nan=True, sort_keys=True, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.out} ({count} sections, git_sha {payload['git_sha']})")

    if args.compare is not None:
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        message = compare_json(baseline, payload)
        if message is not None:
            print(f"DIFFERENT at {message}")
            return 1
        print(
            f"equal: {count} sections "
            f"(baseline git_sha {baseline.get('git_sha')}, current git_sha {payload['git_sha']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
