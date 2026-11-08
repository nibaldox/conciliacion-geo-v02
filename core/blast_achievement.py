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

import math
from typing import Any, Dict, List, Optional

from core.compliance_status import STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE
from core.config import TOLERANCES


W_CREST = 0.4
W_TOE = 0.3
W_BERM = 0.3


__all__ = [
    "W_CREST",
    "W_TOE",
    "W_BERM",
    "classify_achievement_delta",
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


def np_isnan(x: float) -> bool:
    """Local NaN guard (avoids importing numpy at module load)."""
    return x != x


def _validate_tolerance(value: float, name: str) -> float:
    """Validate a tolerance value: finite and >= 0."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number >= 0, got bool {value!r}")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")
    if math.isnan(v) or math.isinf(v):
        raise ValueError(f"{name} must be finite, got {v!r}")
    if v < 0:
        raise ValueError(f"{name} must be >= 0, got {v!r}")
    return v


def classify_achievement_delta(
    delta: Optional[float],
    tolerance_neg_m: float,
    tolerance_pos_m: float,
) -> Optional[str]:
    """Public signed-side classifier shared by the score and the dashboard.

    ``delta < 0`` (deuda) is compared against ``tolerance_neg_m``;
    ``delta >= 0`` (sobre-excavación) against ``tolerance_pos_m``. Returns
    ``CUMPLE`` (inclusive within the side tolerance), ``FUERA DE
    TOLERANCIA`` (inclusive within 1.5x), ``NO CUMPLE`` (beyond), or
    ``None`` when the delta is missing / non-numeric / NaN / Inf.
    Tolerances are validated (finite, >= 0) and raise ``ValueError``.
    """
    neg = _validate_tolerance(tolerance_neg_m, "tolerance_neg_m")
    pos = _validate_tolerance(tolerance_pos_m, "tolerance_pos_m")
    if delta is None or isinstance(delta, bool):
        return None
    try:
        v = float(delta)
    except (TypeError, ValueError):
        return None
    if np_isnan(v) or math.isinf(v):
        return None
    tol = neg if v < 0 else pos
    a = abs(v)
    if a <= tol:
        return STATUS_CUMPLE
    if a <= 1.5 * tol:
        return STATUS_FUERA
    return STATUS_NO_CUMPLE


def _delta_status(delta: Optional[float], tol_neg: float, tol_pos: float) -> Optional[str]:
    """Classify a signed crest/toe deviation into the three-tier model.

    Signed-side classification: ``delta < 0`` (deuda) is compared against
    ``tol_neg`` (allowed debt magnitude); ``delta >= 0``
    (sobre-excavación) against ``tol_pos``. A side CUMPLE when
    ``abs(delta) <= tol_side`` (inclusive), is ``STATUS_FUERA`` when
    ``abs(delta) <= 1.5 * tol_side``, otherwise ``STATUS_NO_CUMPLE``.
    ``None`` / NaN / non-numeric deltas return ``None``.
    """
    return classify_achievement_delta(delta, tol_neg, tol_pos)


def _score_subset(
    rows: List[dict],
    crest_tol_neg: float,
    crest_tol_pos: float,
    toe_tol_neg: float,
    toe_tol_pos: float,
) -> Dict[str, Any]:
    """Score a list of comparison rows.

    Returns the breakdown shape consumed by callers. Note the deliberate
    divergence between the two metrics: ``score_0_100`` uses partial
    credit (CUMPLE=1.0, FUERA=0.5) so a row that is merely out of
    tolerance still contributes; ``breakdown`` counts **strict CUMPLE
    only** (FUERA rows count as 0). The two answer different questions —
    "how much of the design was achieved, with partial credit?" vs
    "how many banks fully comply?" — and callers should not expect them
    to match when FUERA rows are present.
    """
    details = []
    statuses_by_row = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        structural = row.get("type") in {"EXTRA", "MISSING"}
        statuses = {
            "crest": _delta_status(row.get("delta_crest"), crest_tol_neg, crest_tol_pos),
            "toe": _delta_status(row.get("delta_toe"), toe_tol_neg, toe_tol_pos),
            "berm": row.get("berm_status"),
        }
        tiers = (STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE)
        statuses = {key: value if not structural and value in tiers else None
                    for key, value in statuses.items()}
        weights = {"crest": W_CREST, "toe": W_TOE, "berm": W_BERM}
        available = [key for key, value in statuses.items() if value is not None]
        missing = [key for key in weights if key not in available]
        weight = sum(weights[key] for key in available)
        score = (100 * sum(weights[key] * _row_credit(statuses[key]) for key in available) / weight
                 if weight else None)
        details.append({"score": score, "components_available": available,
                        "components_missing": missing, "weight_available": weight})
        statuses_by_row.append(statuses)
    n_total = len(details)
    scores = [entry["score"] for entry in details if entry["score"] is not None]
    counts = {key: sum(status[key] is not None for status in statuses_by_row)
              for key in ("crest", "toe", "berm")}
    passing = {key: sum(status[key] == STATUS_CUMPLE for status in statuses_by_row)
               for key in counts}
    coverage = {
        "n_rows": n_total,
        "n_evaluable": len(scores),
        "n_complete": sum(len(entry["components_available"]) == 3 for entry in details),
        "weight_available_mean": (sum(entry["weight_available"] for entry in details) / n_total
                                  if n_total else None),
        "n_available": counts,
    }
    return {
        "n_total": n_total,
        "n_passing_crest": passing["crest"],
        "n_passing_toe": passing["toe"],
        "n_passing_berm": passing["berm"],
        "breakdown": {key: int(round(100 * passing[key] / counts[key])) if counts[key] else None
                      for key in counts},
        "score_0_100": int(round(sum(scores) / len(scores))) if scores else None,
        "coverage": coverage,
        "rows": details,
    }


def _resolve_tolerances(
    crest_tolerance_m: Optional[float] = None,
    toe_tolerance_m: Optional[float] = None,
    crest_tolerance_neg_m: Optional[float] = None,
    crest_tolerance_pos_m: Optional[float] = None,
    toe_tolerance_neg_m: Optional[float] = None,
    toe_tolerance_pos_m: Optional[float] = None,
) -> Dict[str, Dict[str, float]]:
    """Resolve per-side (signed) crest/toe tolerances.

    Precedence per side: signed kwarg (if present) > legacy scalar for
    the feature (if present) > ``TOLERANCES.crest_toe_deviation``. The
    legacy scalars apply symmetrically to both sides of their feature.
    All values are validated (finite, >= 0).
    """
    default = TOLERANCES.crest_toe_deviation
    crest_neg = (
        crest_tolerance_neg_m
        if crest_tolerance_neg_m is not None
        else (crest_tolerance_m if crest_tolerance_m is not None else default["neg"])
    )
    crest_pos = (
        crest_tolerance_pos_m
        if crest_tolerance_pos_m is not None
        else (crest_tolerance_m if crest_tolerance_m is not None else default["pos"])
    )
    toe_neg = (
        toe_tolerance_neg_m
        if toe_tolerance_neg_m is not None
        else (toe_tolerance_m if toe_tolerance_m is not None else default["neg"])
    )
    toe_pos = (
        toe_tolerance_pos_m
        if toe_tolerance_pos_m is not None
        else (toe_tolerance_m if toe_tolerance_m is not None else default["pos"])
    )
    return {
        "crest": {
            "neg": _validate_tolerance(crest_neg, "crest_tolerance_neg_m"),
            "pos": _validate_tolerance(crest_pos, "crest_tolerance_pos_m"),
        },
        "toe": {
            "neg": _validate_tolerance(toe_neg, "toe_tolerance_neg_m"),
            "pos": _validate_tolerance(toe_pos, "toe_tolerance_pos_m"),
        },
    }


def compute_design_achievement_score(
    comparisons: Optional[List[dict]],
    malla_to_section: Optional[Dict[str, List[str]]] = None,
    crest_tolerance_m: Optional[float] = None,
    toe_tolerance_m: Optional[float] = None,
    crest_tolerance_neg_m: Optional[float] = None,
    crest_tolerance_pos_m: Optional[float] = None,
    toe_tolerance_neg_m: Optional[float] = None,
    toe_tolerance_pos_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Weighted 0-100 design-achievement score per (per-malla) section.

    Per-row partial credit is 1 for CUMPLE, 0.5 for FUERA and 0 for
    NO CUMPLE. Available weights are renormalized per row. The global
    score is the mean of evaluable row scores; coverage is reported separately.

    crest/toe status is derived per row from ``|delta_crest|`` /
    ``|delta_toe|`` against ``crest_tolerance_m`` (default
    :data:`TOLERANCES.crest_toe_deviation['pos']`, 1.0 m — the horizontal
    overbreak tolerance, NOT the vertical bench-height tolerance). berm
    status is read directly from the row's ``berm_status`` field.

    Parameters
    ----------
    comparisons : list of dict, optional
        Reconciliation rows (output of ``compare_design_vs_asbuilt``).
        ``None`` or ``[]`` returns a nullable score without raising.
    malla_to_section : dict, optional
        ``{malla_name: [section_name, ...]}`` mapping produced by the UI
        join. When provided and non-empty, the function returns
        ``per_malla: {malla: int}`` in addition to ``global``.
    crest_tolerance_m, toe_tolerance_m : float, optional
        Override knobs for the crest/toe horizontal-deviation tolerance.
        Default :data:`TOLERANCES.crest_toe_deviation['pos']` (1.0 m —
        blast overbreak tolerance).

    Returns
    -------
    dict
        - ``global``: nullable int 0-100 percentage (mean of evaluable rows)
        - ``breakdown``: ``{crest, toe, berm}`` percentages 0-100. These
          count **strict CUMPLE only** (FUERA rows do NOT contribute);
          ``global`` uses partial credit (CUMPLE=1.0, FUERA=0.5), so the
          two can differ when out-of-tolerance rows are present.
        - ``n_total``: int, rows scored
        - ``n_passing_crest/toe/berm``: int, rows where the status equals
          ``STATUS_CUMPLE``
        - ``per_malla``: dict[str, int | None] or ``None``
        - ``rows``: row scores, available/missing components and available weight
        - ``coverage``, ``per_malla_coverage``: counts and mean available weight
    """
    tolerances = _resolve_tolerances(
        crest_tolerance_m,
        toe_tolerance_m,
        crest_tolerance_neg_m,
        crest_tolerance_pos_m,
        toe_tolerance_neg_m,
        toe_tolerance_pos_m,
    )

    comparisons = list(comparisons or [])

    crest_tol_neg = tolerances["crest"]["neg"]
    crest_tol_pos = tolerances["crest"]["pos"]
    toe_tol_neg = tolerances["toe"]["neg"]
    toe_tol_pos = tolerances["toe"]["pos"]

    overall = _score_subset(
        list(comparisons), crest_tol_neg, crest_tol_pos, toe_tol_neg, toe_tol_pos
    )

    per_malla: Optional[Dict[str, int]] = None
    per_malla_coverage = None
    if malla_to_section:
        per_malla = {}
        per_malla_coverage = {}
        for malla, sections in malla_to_section.items():
            if not sections:
                continue
            section_set = set(sections)
            sub = [r for r in comparisons if isinstance(r, dict) and r.get("section") in section_set]
            sub_score = _score_subset(
                sub, crest_tol_neg, crest_tol_pos, toe_tol_neg, toe_tol_pos
            )
            per_malla[str(malla)] = sub_score["score_0_100"]
            per_malla_coverage[str(malla)] = sub_score["coverage"]

    return {
        "global": overall["score_0_100"],
        "rows": overall["rows"],
        "coverage": overall["coverage"],
        "per_malla_coverage": per_malla_coverage,
        "breakdown": overall["breakdown"],
        "n_total": overall["n_total"],
        "n_passing_crest": overall["n_passing_crest"],
        "n_passing_toe": overall["n_passing_toe"],
        "n_passing_berm": overall["n_passing_berm"],
        "per_malla": per_malla,
        "tolerances": tolerances,
    }
