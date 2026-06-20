"""Stability analysis helpers (Phase 9).

Provides summary functions that operate on :class:`BenchParams`
collections produced by :mod:`core.param_extractor`. Future phases will
add Markland test, planar factor of safety, wedge analysis, etc.

These helpers are intentionally small: the goal of Phase 9 is to wire
overhang / rock-bridge / catch-bench detection into the extractor and
expose a thin aggregation layer that downstream code (report
generator, web UI, future physics modules) can call without re-parsing
the raw ``BenchParams`` list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.param_extractor import BenchParams
from core.config import STABILITY


@dataclass
class BenchStabilityAssessment:
    bench_number: int
    overhang_m: float
    overhang_severity: str
    rock_bridge_thickness_m: float
    rock_bridge_height_m: float
    catch_bench_adequate: bool
    catch_bench_ratio: float


def assess_bench_stability(bench: BenchParams) -> BenchStabilityAssessment:
    """Wrap a single bench's stability flags into a severity classification.

    Overhang severity follows :data:`core.config.STABILITY`:

    - ``overhang_m >= overhang_critical_m`` → ``'CRITICAL'`` (default 1.5 m)
    - ``overhang_m >= overhang_warning_m``  → ``'WARNING'``  (default 0.5 m)
    - otherwise                               → ``'OK'``
    """
    overhang = float(bench.overhang_m)
    if overhang >= STABILITY.overhang_critical_m:
        severity = 'CRITICAL'
    elif overhang >= STABILITY.overhang_warning_m:
        severity = 'WARNING'
    else:
        severity = 'OK'
    return BenchStabilityAssessment(
        bench_number=int(bench.bench_number),
        overhang_m=overhang,
        overhang_severity=severity,
        rock_bridge_thickness_m=float(bench.rock_bridge_thickness_m),
        rock_bridge_height_m=float(bench.rock_bridge_height_m),
        catch_bench_adequate=bool(bench.catch_bench_adequate),
        catch_bench_ratio=float(bench.catch_bench_ratio),
    )


def summarize_section_stability(benches: Iterable[BenchParams]) -> dict:
    """Aggregate stability assessment over all benches in a section.

    Returns a dict with:

    - ``n_benches_total``: count of input benches
    - ``n_overhangs_warning``: benches with ``overhang_severity == 'WARNING'``
    - ``n_overhangs_critical``: benches with ``overhang_severity == 'CRITICAL'``
    - ``n_catch_bench_adequate``: benches with ``catch_bench_adequate == True``
    - ``critical_bench_numbers``: ``bench_number`` of every critical bench
    """
    benches_list = list(benches)
    assessments = [assess_bench_stability(b) for b in benches_list]
    return {
        'n_benches_total': len(benches_list),
        'n_overhangs_warning': sum(
            1 for a in assessments if a.overhang_severity == 'WARNING'
        ),
        'n_overhangs_critical': sum(
            1 for a in assessments if a.overhang_severity == 'CRITICAL'
        ),
        'n_catch_bench_adequate': sum(
            1 for a in assessments if a.catch_bench_adequate
        ),
        'critical_bench_numbers': [
            a.bench_number for a in assessments if a.overhang_severity == 'CRITICAL'
        ],
    }
