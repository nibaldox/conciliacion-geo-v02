"""Pure helpers to surface Logro Diseño (cresta/pata/berma) on the dashboard.

No Streamlit, no Plotly: everything here is testable without a UI runtime.
The design-achievement metric (weighted 40/30/30 partial credit over
crest/toe/berma) is kept strictly separate from the existing geotechnical
compliance metric (3 binary parameters).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core.blast_achievement import (
    classify_achievement_delta,
    compute_design_achievement_score,
)
from core.compliance_status import STATUS_CUMPLE
from ui.tabs.blast_correlation.data import resolve_achievement_tolerances


def achievement_pct_color(pct: Optional[float], denom: Any) -> str:
    """Semantic color for a strict-percentage card.

    ``denom`` 0 (or missing pct) -> muted grey; ``pct >= 70`` green;
    ``>= 50`` orange; otherwise red. Mirrors the global card palette.
    """
    if not denom or not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return "#888888"
    if pct >= 70:
        return "green"
    if pct >= 50:
        return "orange"
    return "#B22222"


def _finite(x: Any) -> bool:
    if x is None or isinstance(x, bool):
        return False
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def _has_berm_status(row: dict) -> bool:
    s = row.get("berm_status")
    return isinstance(s, str) and s not in ("", "-")


def _is_evaluable(row: dict) -> bool:
    return _finite(row.get("delta_crest")) or _finite(row.get("delta_toe")) or _has_berm_status(row)


def _signed_mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_achievement_summary(results: List[dict], ct_tol: Optional[dict]) -> Optional[Dict[str, Any]]:
    """Global Logro Diseño summary with strict per-element percentages.

    ``ct_tol`` is normalized via ``resolve_achievement_tolerances``; the
    same signed neg/pos pair is applied to crest and toe. Strict
    percentages count CUMPLE only (FUERA / NO CUMPLE do not comply);
    rows missing the element are omitted from that element's denominator.
    Returns ``None`` when no row is evaluable — never a fake 0.
    """
    tol = resolve_achievement_tolerances(ct_tol)
    neg, pos = tol["neg"], tol["pos"]
    rows = [r for r in (results or []) if isinstance(r, dict) and _is_evaluable(r)]
    if not rows:
        return None

    score = compute_design_achievement_score(
        rows,
        crest_tolerance_neg_m=neg,
        crest_tolerance_pos_m=pos,
        toe_tolerance_neg_m=neg,
        toe_tolerance_pos_m=pos,
    )

    crest_vals = [r.get("delta_crest") for r in rows if _finite(r.get("delta_crest"))]
    toe_vals = [r.get("delta_toe") for r in rows if _finite(r.get("delta_toe"))]
    berm_rows = [r for r in rows if _has_berm_status(r)]

    def _strict(vals: List[Any]) -> tuple[int, int]:
        cumple = sum(1 for v in vals if classify_achievement_delta(v, neg, pos) == STATUS_CUMPLE)
        return cumple, len(vals)

    n_crest, d_crest = _strict(crest_vals)
    n_toe, d_toe = _strict(toe_vals)
    n_berm = sum(1 for r in berm_rows if r["berm_status"] == STATUS_CUMPLE)
    d_berm = len(berm_rows)

    return {
        "global": score["global"],
        "n_evaluable": len(rows),
        "crest_pct": int(round(n_crest / d_crest * 100)) if d_crest else 0,
        "crest_denom": d_crest,
        "toe_pct": int(round(n_toe / d_toe * 100)) if d_toe else 0,
        "toe_denom": d_toe,
        "berm_pct": int(round(n_berm / d_berm * 100)) if d_berm else 0,
        "berm_denom": d_berm,
        "ct_tol": tol,
    }


def build_parameter_breakdown_rows(results: List[dict], ct_tol: Optional[dict]) -> List[Dict[str, Any]]:
    """5 rows: the 3 geotechnical parameters + Desviación Cresta/Pata.

    The crest/toe rows use finite signed deltas only; FUERA and NO CUMPLE
    both count as No Cumple; the average is signed and formatted ``+m``.
    """
    tol = resolve_achievement_tolerances(ct_tol)
    neg, pos = tol["neg"], tol["pos"]

    rows: List[Dict[str, Any]] = []
    for key, label, real_field, unit in [
        ("height_status", "Altura de Banco", "height_real", "m"),
        ("angle_status", "Ángulo de Cara", "angle_real", "°"),
        ("berm_status", "Ancho de Berma", "berm_real", "m"),
    ]:
        valid = [r for r in (results or []) if r.get(key) and r[key] != "-"]
        total = len(valid)
        cumple = sum(1 for r in valid if r[key] == STATUS_CUMPLE)
        pct = (cumple / total * 100) if total > 0 else 0
        real_values = [r[real_field] for r in valid if r.get(real_field) is not None]
        avg_real = _signed_mean(real_values)
        rows.append({
            "Parámetro": label,
            "Total Evaluado": total,
            "Cumple": cumple,
            "No Cumple": total - cumple,
            "% Cumplimiento": f"{pct:.0f}%",
            "Promedio Real": f"{avg_real:.1f} {unit}",
        })

    for key, label in [("delta_crest", "Desviación Cresta"), ("delta_toe", "Desviación Pata")]:
        vals = [float(r[key]) for r in (results or [])
                if isinstance(r, dict) and _finite(r.get(key))]
        total = len(vals)
        cumple = sum(1 for v in vals if classify_achievement_delta(v, neg, pos) == STATUS_CUMPLE)
        pct = (cumple / total * 100) if total > 0 else 0
        avg = _signed_mean(vals)
        rows.append({
            "Parámetro": label,
            "Total Evaluado": total,
            "Cumple": cumple,
            "No Cumple": total - cumple,
            "% Cumplimiento": f"{pct:.0f}%",
            "Promedio Real": f"{avg:+.1f} m",
        })
    return rows


def build_sector_rows(results: List[dict], ct_tol: Optional[dict]) -> List[Dict[str, Any]]:
    """Per-sector rows with TWO separate metrics.

    ``% Cumplimiento`` keeps the current geotechnical semantics (3 binary
    parameters); ``Logro Diseño (%)`` is the weighted 40/30/30 partial
    credit over the sector's evaluable rows, or ``None`` when the sector
    has none (never a fake 0).
    """
    tol = resolve_achievement_tolerances(ct_tol)
    neg, pos = tol["neg"], tol["pos"]

    sector_data: Dict[str, dict] = {}
    for r in (results or []):
        if not isinstance(r, dict):
            continue
        sector = r.get("sector", "Sin Sector") or "Sin Sector"
        d = sector_data.setdefault(sector, {"cumple": 0, "no_cumple": 0, "total": 0, "rows": []})
        for key in ("height_status", "angle_status", "berm_status"):
            s = r.get(key)
            if s and s != "-":
                d["total"] += 1
                if s == STATUS_CUMPLE:
                    d["cumple"] += 1
                else:
                    d["no_cumple"] += 1
        d["rows"].append(r)

    out: List[Dict[str, Any]] = []
    for sector in sorted(sector_data):
        d = sector_data[sector]
        pct = (d["cumple"] / d["total"] * 100) if d["total"] > 0 else 0
        evaluable = [r for r in d["rows"] if _is_evaluable(r)]
        if evaluable:
            score = compute_design_achievement_score(
                evaluable,
                crest_tolerance_neg_m=neg,
                crest_tolerance_pos_m=pos,
                toe_tolerance_neg_m=neg,
                toe_tolerance_pos_m=pos,
            )
            achievement: Optional[int] = score["global"]
        else:
            achievement = None
        out.append({
            "Sector": sector,
            "Cumple": d["cumple"],
            "No Cumple": d["no_cumple"],
            "Total": d["total"],
            "% Cumplimiento": round(pct, 1),
            "Logro Diseño (%)": achievement,
        })
    return out


def build_achievement_histograms(results: List[dict], ct_tol: Optional[dict]) -> List[Dict[str, Any]]:
    """Specs for the Δ Cresta / Δ Pata histograms.

    Finite deltas only; the green band is exactly ``x0=-neg, x1=pos``.
    """
    tol = resolve_achievement_tolerances(ct_tol)
    neg, pos = tol["neg"], tol["pos"]
    specs: List[Dict[str, Any]] = []
    for key, title in [("delta_crest", "Δ Cresta (m)"), ("delta_toe", "Δ Pata (m)")]:
        values = [float(r[key]) for r in (results or [])
                  if isinstance(r, dict) and _finite(r.get(key))]
        specs.append({"title": title, "values": values, "x0": -neg, "x1": pos})
    return specs
