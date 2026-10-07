from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

from core.compliance_status import STATUS_CUMPLE, STATUS_NO_CUMPLE


def _finite_score(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def compute_section_scores(
    comparisons: Iterable[Mapping[str, Any]], *, prefer_canonical: bool = False,
) -> dict[str, float]:
    rows_by_section: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in comparisons:
        if row.get("type") == "MATCH":
            rows_by_section[str(row.get("section", ""))].append(row)
    scores: dict[str, float] = {}
    for section, rows in rows_by_section.items():
        canonical = [float(row["section_score"]) for row in rows if _finite_score(row.get("section_score"))]
        consistent = len(canonical) == len(rows) and all(abs(score - canonical[0]) <= 1e-9 for score in canonical)
        benches = [float(row["bench_score"]) for row in rows if _finite_score(row.get("bench_score"))]
        if prefer_canonical and consistent:
            scores[section] = canonical[0]
        elif benches:
            scores[section] = sum(benches) / len(benches)
        elif consistent:
            scores[section] = canonical[0]
    return scores


def compute_global_compliance(comparisons: Iterable[Mapping[str, Any]]) -> tuple[float, str]:
    scores = compute_section_scores(comparisons)
    if not scores:
        return 0.0, "SIN DATOS"
    score = sum(scores.values()) / len(scores)
    return score, STATUS_CUMPLE if score >= 70 else STATUS_NO_CUMPLE
