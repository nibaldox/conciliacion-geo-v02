"""Per-malla design-achievement score (Gap 5).

Three-tier partial-credit scoring of reconciliation rows. Consumes the
existing comparison dicts emitted by
:func:`core.profile_compliance.compare_design_vs_asbuilt` and produces a
weighted 0-100 score plus a per-element breakdown and an optional
per-malla grouping when the caller provides the malla -> section-name
mapping.

The function is purely a helper: no Streamlit, no Plotly, no I/O. All
inputs are already produced by the standard pipeline (cresta/toe/berm
deltas, berm_status, section name). Tests live in
``tests/test_blast_achievement.py``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.compliance_status import STATUS_CUMPLE, STATUS_FUERA
from core.config import TOLERANCES


W_CREST = 0.4
W_TOE = 0.3
W_BERM = 0.3


__all__ = [
    "W_CREST",
    "W_TOE",
    "W_BERM",
    "compute_design_achievement_score",
]


def _row_credit(status: Optional[str]) -> float:
    """Map a compliance status to its partial-credit value.

    - ``CUMPLE`` -> 1.0 (full credit)
    - ``FUERA DE TOLERANCIA`` -> 0.5 (half credit, inside the
      three-tier model)
    - anything else (NO CUMPLE, NO CONSTRUIDO, MISSING, None, ...) -> 0.0
    """
    if status == STATUS_CUMPLE:
        return 1.0
    if status == STATUS_FUERA:
        return 0.5
    return 0.0


def _crest_status(delta_crest: Optional[float], tol: float) -> Optional[str]:
    if delta_crest is None:
        return None
    try:
        v = float(delta_crest)
    except (TypeError, ValueError):
        return None
    if np_isnan(v):
        return None
    a = abs(v)
    if a <= tol:
        return STATUS_CUMPLE
    if a <= 1.5 * tol:
        return STATUS_FUERA
    return None


def _toe_status(delta_toe: Optional[float], tol: float) -> Optional[str]:
    if delta_toe is None:
        return None
    try:
        v = float(delta_toe)
    except (TypeError, ValueError):
        return None
    if np_isnan(v):
        return None
    a = abs(v)
    if a <= tol:
        return STATUS_CUMPLE
    if a <= 1.5 * tol:
        return STATUS_FUERA
    return None


def np_isnan(x: float) -> bool:
    """Local NaN guard (keeps the module free of a numpy import at module load)."""
    return x != x


def _score_subset(rows: List[dict], crest_tol: float, toe_tol: float) -> Dict[str, Any]:
    """Score a list of comparison rows. Returns the breakdown shape consumed by callers."""
    n_total = 0
    n_crest_cumple = 0
    n_toe_cumple = 0
    n_berm_cumple = 0
    sum_credit = 0.0

    for row in rows:
        if not isinstance(row, dict):
            continue
        crest_st = _crest_status(row.get("delta_crest"), crest_tol)
        toe_st = _toe_status(row.get("delta_toe"), toe_tol)
        berm_st = row.get("berm_status")

        crest_credit = _row_credit(crest_st)
        toe_credit = _row_credit(toe_st)
        berm_credit = _row_credit(berm_st)

        row_credit = (
            W_CREST * crest_credit
            + W_TOE * toe_credit
            + W_BERM * berm_credit
        )
        sum_credit += row_credit
        if crest_st == STATUS_CUMPLE:
            n_crest_cumple += 1
        if toe_st == STATUS_CUMPLE:
            n_toe_cumple += 1
        if berm_st == STATUS_CUMPLE:
            n_berm_cumple += 1
        n_total += 1

    if n_total == 0:
        return {
            "n_total": 0,
            "n_passing_crest": 0,
            "n_passing_toe": 0,
            "n_passing_berm": 0,
            "breakdown": {"crest": 0, "toe": 0, "berm": 0},
            "score_0_100": 0,
        }

    mean_credit = sum_credit / n_total
    score_pct = int(round(mean_credit * 100.0))

    crest_pct = int(round((n_crest_cumple / n_total) * 100.0))
    toe_pct = int(round((n_toe_cumple / n_total) * 100.0))
    berm_pct = int(round((n_berm_cumple / n_total) * 100.0))

    return {
        "n_total": n_total,
        "n_passing_crest": n_crest_cumple,
        "n_passing_toe": n_toe_cumple,
        "n_passing_berm": n_berm_cumple,
        "breakdown": {"crest": crest_pct, "toe": toe_pct, "berm": berm_pct},
        "score_0_100": score_pct,
    }


def compute_design_achievement_score(
    comparisons: Optional[List[dict]],
    malla_to_section: Optional[Dict[str, List[str]]] = None,
    crest_tolerance_m: Optional[float] = None,
    toe_tolerance_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Weighted 0-100 design-achievement score per (per-malla) section.

    Per-row partial credit: ``CUMPLE -> 1.0``, ``FUERA DE TOLERANCIA -> 0.5``,
    anything else (NO CUMPLE, NO CONSTRUIDO, MISSING, ...) -> ``0.0``. The
    aggregate is ``0.4 * crest + 0.3 * toe + 0.3 * berm`` averaged across
    rows.

    crest/toe status is derived per row from ``|delta_crest|`` /
    ``|delta_toe|`` against ``crest_tolerance_m`` (default
    :data:`TOLERANCES.bench_height['pos']`, 1.5 m). berm status is read
    directly from the row's ``berm_status`` field.

    Parameters
    ----------
    comparisons : list of dict, optional
        Reconciliation rows (output of ``compare_design_vs_asbuilt``).
        ``None`` or ``[]`` returns the zero-row shape without raising.
    malla_to_section : dict, optional
        ``{malla_name: [section_name, ...]}`` mapping produced by the UI
        join. When provided and non-empty, the function returns
        ``per_malla: {malla: int}`` in addition to ``global``.
    crest_tolerance_m, toe_tolerance_m : float, optional
        Override knobs for the crest/toe tolerance. Default
        :data:`TOLERANCES.bench_height['pos']` (1.5 m).

    Returns
    -------
    dict
        - ``global``: int 0-100 percentage (weighted average across all rows)
        - ``breakdown``: ``{crest, toe, berm}`` percentages 0-100
        - ``n_total``: int, rows scored
        - ``n_passing_crest/toe/berm``: int, rows where the status equals
          ``STATUS_CUMPLE``
        - ``per_malla``: dict[str, int] or ``None``
    """
    if not comparisons:
        empty_breakdown = {"crest": 0, "toe": 0, "berm": 0}
        return {
            "global": 0,
            "breakdown": empty_breakdown,
            "n_total": 0,
            "n_passing_crest": 0,
            "n_passing_toe": 0,
            "n_passing_berm": 0,
            "per_malla": None,
        }

    crest_tol = (
        float(crest_tolerance_m)
        if crest_tolerance_m is not None
        else float(TOLERANCES.bench_height["pos"])
    )
    toe_tol = (
        float(toe_tolerance_m)
        if toe_tolerance_m is not None
        else float(TOLERANCES.bench_height["pos"])
    )

    overall = _score_subset(list(comparisons), crest_tol, toe_tol)

    per_malla: Optional[Dict[str, int]] = None
    if malla_to_section:
        per_malla = {}
        for malla, sections in malla_to_section.items():
            if not sections:
                continue
            section_set = set(sections)
            sub = [r for r in comparisons if r.get("section") in section_set]
            sub_score = _score_subset(sub, crest_tol, toe_tol)
            per_malla[str(malla)] = sub_score["score_0_100"]

    return {
        "global": overall["score_0_100"],
        "breakdown": overall["breakdown"],
        "n_total": overall["n_total"],
        "n_passing_crest": overall["n_passing_crest"],
        "n_passing_toe": overall["n_passing_toe"],
        "n_passing_berm": overall["n_passing_berm"],
        "per_malla": per_malla,
    }
