"""Reusable Logro Diseño summary (cresta/pata/berma) — pure core, no UI.

Wraps :func:`core.blast_achievement.compute_design_achievement_score` (the
weighted 0.4 crest + 0.3 toe + 0.3 berma partial-credit score) with the
report/summary semantics established by the Streamlit dashboard without
importing anything from ``ui``:

- A comparison row is *evaluable* when it has a finite signed
  ``delta_crest`` / ``delta_toe`` or a ``berm_status`` belonging to the
  three-tier model (``CUMPLE`` / ``FUERA DE TOLERANCIA`` / ``NO CUMPLE``).
  Missing measurements and non-tier statuses (``MISSING``,
  ``NO CONSTRUIDO``, …) never become compliance on their own.
- Strict crest/toe/berma percentages count ``CUMPLE`` only. Each element's
  denominator is the number of rows carrying evidence for it, so the
  percentage is ``None`` — never a fake 0 — when there is none.
- Signed means average the finite deltas of every row.
- The global score is ``None`` when no row is evaluable.
- The per-sector breakdown keeps ``''`` (rows without sector) as its own
  identity instead of a placeholder label.

All inputs come from the standard pipeline (``compare_design_vs_asbuilt``
rows persisted by ``db.save_results``); there is no I/O here.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

from core.blast_achievement import (
    classify_achievement_delta,
    compute_design_achievement_score,
)
from core.compliance_status import (
    STATUS_CUMPLE,
    STATUS_FUERA,
    STATUS_NO_CUMPLE,
)
from core.config import TOLERANCES

_TIER_STATUSES: frozenset = frozenset(
    {STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE}
)

__all__ = [
    "build_design_achievement_summary",
    "build_sector_achievement_summary",
]


def _finite(x: Any) -> bool:
    if x is None or isinstance(x, bool):
        return False
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def _is_evaluable(row: dict) -> bool:
    if _finite(row.get("delta_crest")) or _finite(row.get("delta_toe")):
        return True
    status = row.get("berm_status")
    return isinstance(status, str) and status in _TIER_STATUSES


def _resolved_tolerances(ct_tol: Optional[dict]) -> Dict[str, float]:
    """Normalize ``{'neg', 'pos'}`` against the core defaults.

    ``None`` returns the core ``TOLERANCES.crest_toe_deviation`` defaults.
    A non-mapping or non-finite/<0 value raises ``TypeError``/``ValueError``
    with a clear message; the input is never mutated.
    """
    defaults = TOLERANCES.crest_toe_deviation
    if ct_tol is None:
        return {
            "neg": float(defaults["neg"]),
            "pos": float(defaults["pos"]),
        }
    if not isinstance(ct_tol, dict):
        raise TypeError(
            "crest_toe_deviation tolerances must be a dict {'neg': float, "
            "'pos': float}, got "
            f"{type(ct_tol).__name__}"
        )
    resolved: Dict[str, float] = {}
    for key in ("neg", "pos"):
        value = ct_tol.get(key, defaults[key])
        if isinstance(value, bool):
            raise ValueError(
                f"crest_toe_deviation['{key}'] must be a number, got bool"
            )
        try:
            resolved[key] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"crest_toe_deviation['{key}'] must be a number, got {value!r}"
            ) from exc
        if not math.isfinite(resolved[key]) or resolved[key] < 0:
            raise ValueError(
                f"crest_toe_deviation['{key}'] must be finite and >= 0, "
                f"got {resolved[key]!r}"
            )
    return resolved


def _summary_for_rows(
    rows: List[dict], tol: Dict[str, float]
) -> Dict[str, Any]:
    neg, pos = tol["neg"], tol["pos"]

    score = compute_design_achievement_score(
        rows,
        crest_tolerance_neg_m=neg,
        crest_tolerance_pos_m=pos,
        toe_tolerance_neg_m=neg,
        toe_tolerance_pos_m=pos,
    )
    global_score = score["global"]
    evaluable = [r for r, detail in zip(rows, score["rows"]) if detail["score"] is not None]
    measurement_rows = [r for r in rows if r.get("type") not in {"EXTRA", "MISSING"}]

    crest_vals = [r.get("delta_crest") for r in measurement_rows if _finite(r.get("delta_crest"))]
    toe_vals = [r.get("delta_toe") for r in measurement_rows if _finite(r.get("delta_toe"))]
    berm_rows = [
        r for r in measurement_rows
        if isinstance(r, dict)
        and isinstance(r.get("berm_status"), str)
        and r["berm_status"] in _TIER_STATUSES
    ]

    crest_cumple = sum(
        1
        for v in crest_vals
        if classify_achievement_delta(v, neg, pos) == STATUS_CUMPLE
    )
    toe_cumple = sum(
        1
        for v in toe_vals
        if classify_achievement_delta(v, neg, pos) == STATUS_CUMPLE
    )
    berm_cumple = sum(1 for r in berm_rows if r["berm_status"] == STATUS_CUMPLE)

    def _pct(cumple: int, denom: int) -> Optional[int]:
        return int(round(cumple * 100.0 / denom)) if denom else None

    def _mean(vals: List[Any]) -> Optional[float]:
        return sum(float(v) for v in vals) / len(vals) if vals else None

    return {
        "global_score": global_score,
        "coverage": score["coverage"],
        "rows": score["rows"],
        "n_total": len(rows),
        "n_evaluable": len(evaluable),
        "crest_cumple": crest_cumple,
        "crest_denom": len(crest_vals),
        "crest_pct": _pct(crest_cumple, len(crest_vals)),
        "toe_cumple": toe_cumple,
        "toe_denom": len(toe_vals),
        "toe_pct": _pct(toe_cumple, len(toe_vals)),
        "berm_cumple": berm_cumple,
        "berm_denom": len(berm_rows),
        "berm_pct": _pct(berm_cumple, len(berm_rows)),
        "delta_crest_mean": _mean(crest_vals),
        "delta_toe_mean": _mean(toe_vals),
    }


def build_design_achievement_summary(
    rows: Optional[Iterable[Any]],
    ct_tol: Optional[dict],
) -> Dict[str, Any]:
    """Global Logro Diseño summary with strict per-element percentages.

    ``ct_tol`` is ``{'neg': float, 'pos': float}`` (the session's
    ``crest_toe_deviation``) or ``None`` for the core defaults; the same
    signed pair is applied to crest and toe. Returns the nullable-summary
    dict — including a completely-null shape (global score / percentages /
    means) when no row carries evidence.
    """
    tol = _resolved_tolerances(ct_tol)
    all_rows = list(rows or [])
    sanitized = [r for r in all_rows if isinstance(r, dict)]
    summary = _summary_for_rows(sanitized, tol)
    summary["n_total"] = len(all_rows)
    return summary


def build_sector_achievement_summary(
    rows: Optional[Iterable[Any]],
    ct_tol: Optional[dict],
) -> List[Dict[str, Any]]:
    """Per-sector rows using the same metric semantics.

    Sectors are ``str(row.get('sector', ''))`` with ``''`` preserved as an
    identity (never renamed). Output is sorted by sector name.
    """
    tol = _resolved_tolerances(ct_tol)
    grouped: Dict[str, List[dict]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        grouped.setdefault(str(row.get("sector", "")), []).append(row)
    return [
        {"sector": sector, **_summary_for_rows(rows_sector, tol)}
        for sector in sorted(grouped)
        for rows_sector in [grouped[sector]]
    ]
