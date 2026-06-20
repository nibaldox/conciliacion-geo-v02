"""
Shared helpers for Drill & Blast ↔ Geotechnical correlation.

Both the Excel writer and the Word report generator need to compute the
same per-section summary (number of nearby blast holes, total kg of
explosive, mean absolute deviation). This module owns that logic so the
two output formats stay in sync.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

import pandas as pd

from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.config import DEFAULTS, RAMP


# Status strings used throughout the codebase for compliance.
STATUS_CUMPLE = "CUMPLE"
STATUS_FUERA = "FUERA DE TOLERANCIA"
STATUS_NO_CUMPLE = "NO CUMPLE"
STATUS_NO_CONSTRUIDO = "NO CONSTRUIDO"
STATUS_FALTA_BANCO = "FALTA BANCO"
STATUS_EXTRA = "EXTRA"
STATUS_BANCO_ADICIONAL = "BANCO ADICIONAL"
STATUS_RAMPA_OK = "RAMPA OK"


@dataclass
class BlastCorrelationRow:
    """One row of blast-vs-geotech correlation for a single section."""
    section_name: str
    num_wells: int
    total_kg: float
    mean_abs_deviation: float
    avg_over_break: float = 0.0
    avg_under_break: float = 0.0
    n_over: int = 0
    n_under: int = 0

    def as_tuple(self) -> tuple:
        return (self.section_name, self.num_wells, self.total_kg, self.mean_abs_deviation)

    def as_signed_tuple(self) -> tuple:
        return (
            self.section_name,
            self.num_wells,
            self.total_kg,
            self.mean_abs_deviation,
            self.avg_over_break,
            self.avg_under_break,
            self.n_over,
            self.n_under,
        )


def _first_present(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """Return the first column name from `candidates` that exists in `df`."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _deviation_column(comparisons: List[dict]) -> Optional[str]:
    """Pick the preferred signed deviation column from a comparisons list.

    Prefers columns that carry sign information about the direction of the
    deviation (``delta_crest`` and ``delta_toe``). Falls back to unsigned
    deviation columns (``height_dev`` / ``angle_dev``) when the signed ones
    are not available.
    """
    if not comparisons:
        return None
    keys = [
        k for k in ("delta_crest", "delta_toe", "height_dev", "angle_dev")
        if k in comparisons[0]
    ]
    return keys[0] if keys else None


def compute_signed_deviations(
    comparisons: List[dict],
    section_name: str,
) -> dict:
    """Aggregate signed crest/toe deviations for one section.

    Returns a dict with:
        - avg_over  (float): mean of positive ``delta_crest`` (overbreak)
        - avg_under (float): mean of negative ``delta_crest`` (deuda/underbreak)
        - n_over    (int):   count of positive values
        - n_under   (int):   count of negative values

    Sign convention (verified in ``core/param_extractor.py``):
        delta_crest > 0 → sobre-excavación (topo crest ahead of design)
        delta_crest < 0 → deuda / sub-excavación (topo crest behind design)

    Falls back to ``delta_toe`` when ``delta_crest`` is not present; falls
    back to ``height_dev``/``angle_dev`` with ``abs()`` only when no signed
    column is available (in that case both counters collapse onto ``over``).
    """
    if not comparisons:
        return {"avg_over": 0.0, "avg_under": 0.0, "n_over": 0, "n_under": 0}

    sec_comps = [c for c in comparisons if c.get("section") == section_name]
    if not sec_comps:
        return {"avg_over": 0.0, "avg_under": 0.0, "n_over": 0, "n_under": 0}

    signed_col = None
    for cand in ("delta_crest", "delta_toe"):
        if any(cand in sc and sc.get(cand) is not None for sc in sec_comps):
            signed_col = cand
            break

    if signed_col:
        deltas = [sc[signed_col] for sc in sec_comps if sc.get(signed_col) is not None]
        over_vals = [d for d in deltas if d > 0]
        under_vals = [d for d in deltas if d < 0]
    else:
        for cand in ("height_dev", "angle_dev"):
            if any(cand in sc and sc.get(cand) is not None for sc in sec_comps):
                deltas = [abs(sc[cand]) for sc in sec_comps if sc.get(cand) is not None]
                over_vals = deltas
                under_vals = []
                break
        else:
            return {"avg_over": 0.0, "avg_under": 0.0, "n_over": 0, "n_under": 0}

    avg_over = float(sum(over_vals) / len(over_vals)) if over_vals else 0.0
    avg_under = float(sum(under_vals) / len(under_vals)) if under_vals else 0.0

    return {
        "avg_over": avg_over,
        "avg_under": avg_under,
        "n_over": len(over_vals),
        "n_under": len(under_vals),
    }


def _pasadura(df: pd.DataFrame, bench_height: float) -> pd.Series:
    """Sub-drilling depth (m): collar minus bench floor minus toe."""
    return (df["Z_collar"] - bench_height) - df["Z_toe"]


def compute_pasadura_stats(df_pozos: pd.DataFrame) -> dict:
    """Aggregate sub-drilling statistics for a blast-hole DataFrame.

    Returns a dict with keys: total, mean, optimal_count, optimal_pct.
    """
    if df_pozos is None or df_pozos.empty:
        return {"total": 0, "mean": 0.0, "optimal_count": 0, "optimal_pct": 0.0}

    pas = _pasadura(df_pozos, DEFAULTS.blast_default_bench_height)
    lo, hi = DEFAULTS.blast_correlation_pasadura_optimal
    optimal = int(((pas >= lo) & (pas <= hi)).sum())
    total = len(df_pozos)
    return {
        "total": total,
        "mean": float(pas.mean()) if total else 0.0,
        "optimal_count": optimal,
        "optimal_pct": (optimal / total * 100.0) if total else 0.0,
    }


def compute_blast_geotech_correlation(
    df_pozos: pd.DataFrame,
    sections: List[Any],
    comparisons: List[dict],
    tolerance: Optional[float] = None,
) -> List[BlastCorrelationRow]:
    """Return one BlastCorrelationRow per section.

    For each section, projects blast holes within `tolerance` metres
    (default: DEFAULTS.blast_correlation_radius_m) of the section axis and
    joins with the mean absolute deviation of the matching geotech
    comparison rows.
    """
    if df_pozos is None or df_pozos.empty or not sections:
        return []

    if tolerance is None:
        tolerance = DEFAULTS.blast_correlation_radius_m

    kg_col = _first_present(
        df_pozos,
        ["Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"],
    )
    dev_col = _deviation_column(comparisons)
    df_comp = pd.DataFrame(comparisons) if comparisons else pd.DataFrame()

    rows: List[BlastCorrelationRow] = []
    for sec in sections:
        sec_name = getattr(sec, "name", str(sec))
        if dev_col and not df_comp.empty and sec_name in df_comp["section"].unique():
            mean_dev = float(df_comp.loc[df_comp["section"] == sec_name, dev_col].abs().mean())
        else:
            mean_dev = 0.0

        signed = compute_signed_deviations(comparisons or [], sec_name)

        proj = proyectar_pozos_en_seccion(
            df_pozos,
            origin=getattr(sec, "origin"),
            azimuth=float(getattr(sec, "azimuth", 0.0)),
            length=float(getattr(sec, "length", 200.0)),
            tolerance=tolerance,
        )
        if proj.empty:
            num_wells = 0
            total_kg = 0.0
        else:
            num_wells = len(proj)
            if kg_col and kg_col in proj.columns:
                total_kg = float(proj[kg_col].fillna(0).sum())
            else:
                total_kg = 0.0
        rows.append(
            BlastCorrelationRow(
                section_name=sec_name,
                num_wells=num_wells,
                total_kg=total_kg,
                mean_abs_deviation=mean_dev,
                avg_over_break=signed["avg_over"],
                avg_under_break=signed["avg_under"],
                n_over=signed["n_over"],
                n_under=signed["n_under"],
            )
        )
    return rows


def classify_berm_as_ramp(berm_width: float) -> bool:
    """Return True when a berm of the given width is most likely a ramp."""
    return RAMP.min_width <= berm_width <= RAMP.max_width
