"""Construcción pura de prompts y metadata para la pestaña IA v2."""
from __future__ import annotations

import datetime
from typing import Any

import numpy as np


def build_prompt(
    notes: str,
    sections: list[str],
    filters: dict[str, list],
    blast_trend: dict | None,
) -> str:
    """Build a human-readable prompt context from user notes and filters.

    Returns a markdown-flavored string suitable for the AI request notes
    or for displaying a prompt preview.
    """
    parts: list[str] = []
    if notes.strip():
        parts.append(f"**Notas del usuario:** {notes.strip()}")
    if sections:
        parts.append(f"**Secciones:** {', '.join(str(s) for s in sections)}")
    active_filters = [
        (label, ",".join(str(v) for v in values))
        for label, values in (
            ("sector", filters.get("sector") or []),
            ("sección", filters.get("section") or []),
            ("cota", filters.get("level") or []),
            ("banco", filters.get("bench") or []),
        )
        if values
    ]
    if active_filters:
        parts.append(
            "**Filtros activos:** "
            + "; ".join(f"{label}={vals}" for label, vals in active_filters)
        )
    if blast_trend:
        parts.append(
            f"**Tendencia de tronadura:** PF promedio "
            f"{blast_trend.get('pf_promedio', 'N/A')} kg/m³, "
            f"desviación {blast_trend.get('pf_desviacion', 'N/A')}, "
            f"{blast_trend.get('n_pozos_total', 0)} pozos."
        )
    return "\n\n".join(parts) if parts else "Sin contexto adicional."


def compute_blast_trend_metadata(
    df_pozos: Any,
    sections: list[Any],
    comparisons: list[dict],
) -> dict | None:
    """Compute ``blast_trend`` metadata for the AI prompt.

    Pulls the enriched blast-hole DataFrame and runs
    :func:`compute_blast_geotech_correlation` against the active
    sections + comparisons. Returns ``None`` when there is no blast data.
    """
    if df_pozos is None or len(df_pozos) == 0 or not sections:
        return None

    try:
        from core.blast_correlation import compute_blast_geotech_correlation
        from core.blast_metrics import compute_spacing_burden_ratio

        rows = compute_blast_geotech_correlation(df_pozos, sections, comparisons)
    except Exception:
        return None

    if not rows:
        return None

    pf_values = [
        r.pf_vol_avg_kgm3 for r in rows
        if r.pf_vol_avg_kgm3 and r.pf_vol_avg_kgm3 > 0
    ]
    n_pozos_total = sum(r.num_wells for r in rows)
    if not pf_values:
        return None

    pf_mean = float(sum(pf_values) / len(pf_values))
    pf_std = float(np.std(pf_values, ddof=0)) if len(pf_values) > 1 else 0.0

    if len(pf_values) >= 4:
        q1, q3 = np.percentile(pf_values, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = [f"{v:.2f} kg/m³" for v in pf_values if v < lo or v > hi]
    else:
        outliers = []

    ratios: dict[str, str] = {}
    try:
        sb = compute_spacing_burden_ratio(df_pozos)
        if sb.notna().any():
            ratios["S/B"] = f"{float(sb.mean()):.2f}"
    except Exception:
        pass

    return {
        "pf_promedio": round(pf_mean, 3),
        "pf_desviacion": round(pf_std, 3),
        "n_pozos_total": int(n_pozos_total),
        "trend_slope_pf_per_month": 0.0,
        "trend_direction": "estable",
        "ratios": ratios,
        "outliers": outliers,
    }


def build_metadata(
    comparisons: list[dict],
    filters_active: dict[str, list] | None,
    blast_trend: dict | None,
    project_name: str,
    active_section: str,
    notes: str = "",
) -> dict:
    """Build the metadata dict consumed by core.ai_v2.service.stream_report."""
    filters = filters_active or {}
    metadata: dict = {
        "project_name": project_name or "Sin nombre",
        "fecha_informe": datetime.date.today().isoformat(),
        "seccion": (
            ", ".join(str(s) for s in filters.get("section") or [])
            if filters.get("section")
            else active_section or "global"
        ),
        "banco": (
            ", ".join(str(b) for b in filters.get("bench") or [])
            if filters.get("bench")
            else "N/A"
        ),
    }
    if blast_trend is not None:
        metadata["blast_trend"] = blast_trend
    if notes.strip():
        metadata["user_notes"] = notes.strip()
    return metadata
