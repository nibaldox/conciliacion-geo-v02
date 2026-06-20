"""
Shared helpers for Drill & Blast ↔ Geotechnical correlation.

Both the Excel writer and the Word report generator need to compute the
same per-section summary (number of nearby blast holes, total kg of
explosive, mean absolute deviation). This module owns that logic so the
two output formats stay in sync.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import numpy as np
import pandas as pd

from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.column_utils import first_present_column, kilos_column
from core.compliance_status import (
    STATUS_BANCO_ADICIONAL,
    STATUS_CUMPLE,
    STATUS_EXTRA,
    STATUS_FALTA_BANCO,
    STATUS_FUERA,
    STATUS_NO_CONSTRUIDO,
    STATUS_NO_CUMPLE,
    STATUS_RAMPA_OK,
)
from core.config import DEFAULTS, EXPLOSIVE, RAMP
from core.blast_metrics import enrich_blast_dataframe


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
    pf_vol_avg_kgm3: float = 0.0
    pf_area_avg_kgm2: float = 0.0
    energy_total_mj: float = 0.0
    n_pf_valid: int = 0

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
            self.pf_vol_avg_kgm3,
            self.pf_area_avg_kgm2,
            self.energy_total_mj,
            self.n_pf_valid,
        )


def _knn_spacing(df_group: pd.DataFrame, k: int = 4) -> tuple:
    """Estimate per-row spacing via median of k nearest neighbours in 2D.

    Returns (burden_est, esp_est) — both as pandas Series aligned with df_group.
    Each row gets the median distance to its k nearest neighbours. The same
    estimate is returned for burden and esp when both are missing (typical
    square pattern: B ≈ S).
    """
    if df_group.empty or len(df_group) < 2 or 'X' not in df_group.columns or 'Y' not in df_group.columns:
        empty = pd.Series([np.nan] * len(df_group), index=df_group.index)
        return empty, empty.copy()

    coords = df_group[['X', 'Y']].values.astype(float)
    n = len(coords)
    eff_k = min(k, n - 1)
    if eff_k < 1:
        empty = pd.Series([np.nan] * n, index=df_group.index)
        return empty, empty.copy()

    diffs = coords[:, None, :] - coords[None, :, :]
    dists = np.sqrt((diffs ** 2).sum(axis=2))
    np.fill_diagonal(dists, np.inf)
    kth = np.sort(dists, axis=1)[:, :eff_k]
    median_per_row = np.nanmedian(kth, axis=1)
    series = pd.Series(median_per_row, index=df_group.index)
    return series.copy(), series.copy()


def compute_powder_factor(df_pozos: pd.DataFrame) -> pd.DataFrame:
    """Compute powder factor for each blast-hole row.

    Powder factor (PF) = energy per unit volume of rock broken:
        PF_vol [kg/m³] = Kilos / (Burden × Espaciamiento × Altura_banco)
        PF_area [kg/m²] = Kilos / (Burden × Espaciamiento)
        energy_mj     = Kilos × energy_mj_per_kg(Tipo_Explosivo)

    If Burden/Espaciamiento columns are missing, estimate them from the
    median nearest-neighbour distance (k=4) among the collars in the
    same blast pattern. Falls back gracefully when insufficient data.

    Returns a copy of df_pozos with new columns:
        pf_vol_kgm3: float or NaN
        pf_area_kgm2: float or NaN
        energy_mj: float (always computed if Kilos + Tipo_Explosivo available)
        burden_est_m: float (resolved Burden)
        esp_est_m: float (resolved Espaciamiento)
        Plus the derived metrics from :func:`enrich_blast_dataframe`
        (``stemming_ratio``, ``subdrilling_ratio``,
        ``spacing_burden_ratio``, ``kg_per_meter``,
        ``volume_load_kgm3``, ``coupling_ratio``,
        ``kuznetsov_x50_cm``, ``collar_deviation_deg``,
        ``bottom_column_ratio``) whenever their source columns are
        present.
    """
    if df_pozos is None or df_pozos.empty:
        return df_pozos.copy() if df_pozos is not None else df_pozos

    out = df_pozos.copy()

    kg_col = kilos_column(out)
    kilos = pd.to_numeric(out[kg_col], errors='coerce') if kg_col else pd.Series(
        [np.nan] * len(out), index=out.index
    )

    group_candidates = ['Nombre_Malla_Original', 'holes_polygon', 'Malla']
    group_col = None
    for cand in group_candidates:
        if cand in out.columns:
            group_col = cand
            break

    bench_h = float(DEFAULTS.blast_default_bench_height)

    if group_col and group_col in out.columns:
        groups = out.groupby(out[group_col].astype(str), dropna=False)
    else:
        groups = [('__all__', out)]
        groups = iter(groups)

    burden_est = pd.Series([np.nan] * len(out), index=out.index)
    esp_est = pd.Series([np.nan] * len(out), index=out.index)

    for _, gdf in (groups if group_col else [(None, out)]):
        if 'Burden' in gdf.columns and gdf['Burden'].notna().any():
            burden_est.loc[gdf.index] = pd.to_numeric(gdf['Burden'], errors='coerce')
        else:
            b, _ = _knn_spacing(gdf)
            burden_est.loc[gdf.index] = b

        if 'Esp' in gdf.columns and gdf['Esp'].notna().any():
            esp_est.loc[gdf.index] = pd.to_numeric(gdf['Esp'], errors='coerce')
        else:
            _, s = _knn_spacing(gdf)
            esp_est.loc[gdf.index] = s

    out['burden_est_m'] = burden_est
    out['esp_est_m'] = esp_est

    denom_vol = burden_est * esp_est * bench_h
    pf_vol = np.where(denom_vol > 0, kilos / denom_vol, np.nan)
    out['pf_vol_kgm3'] = pd.Series(pf_vol, index=out.index)

    denom_area = burden_est * esp_est
    pf_area = np.where(denom_area > 0, kilos / denom_area, np.nan)
    out['pf_area_kgm2'] = pd.Series(pf_area, index=out.index)

    if 'Tipo_Explosivo' in out.columns:
        mj_per_kg = out['Tipo_Explosivo'].apply(EXPLOSIVE.energy_mj_per_kg)
    else:
        mj_per_kg = pd.Series(
            [EXPLOSIVE.energy_mj_per_kg('') for _ in range(len(out))],
            index=out.index,
        )
    out['energy_mj'] = kilos * mj_per_kg

    out = enrich_blast_dataframe(out)

    return out


def aggregate_powder_factor_by_group(
    df_pozos: pd.DataFrame,
    group_by: str,
    group_value: str,
    projected_pozos: pd.DataFrame,
) -> dict:
    """Aggregate powder factor metrics for a group of wells.

    Parameters
    ----------
    df_pozos : DataFrame output of `compute_powder_factor`.
    group_by : column to filter on (e.g. 'section_name', 'level', 'malla').
    group_value : value of that column to keep.
    projected_pozos : DataFrame with rows considered for the aggregation.

    Returns dict with:
        pf_vol_avg: float or NaN  (kg/m³, mean)
        pf_area_avg: float or NaN (kg/m², mean)
        pf_vol_weighted: float or NaN (weighted by Kilos)
        energy_total_mj: float
        kg_total: float
        n_wells: int
        n_pf_valid: int  (count of rows with valid PF)
    """
    out = {
        "pf_vol_avg": np.nan,
        "pf_area_avg": np.nan,
        "pf_vol_weighted": np.nan,
        "energy_total_mj": 0.0,
        "kg_total": 0.0,
        "n_wells": 0,
        "n_pf_valid": 0,
    }

    if df_pozos is None or df_pozos.empty or projected_pozos is None or projected_pozos.empty:
        return out

    key_col = first_present_column(projected_pozos, [group_by, 'section', 'section_name'])
    if not key_col:
        return out

    sub = projected_pozos[projected_pozos[key_col].astype(str) == str(group_value)]
    if sub.empty:
        return out

    n_wells = len(sub)
    out["n_wells"] = int(n_wells)

    kg_col = kilos_column(sub)
    kg_total = float(sub[kg_col].fillna(0).sum()) if kg_col else 0.0
    out["kg_total"] = kg_total

    pf_enriched = compute_powder_factor(sub)
    pf_vol = pd.to_numeric(pf_enriched.get('pf_vol_kgm3'), errors='coerce') if 'pf_vol_kgm3' in pf_enriched else pd.Series(dtype=float)
    pf_area = pd.to_numeric(pf_enriched.get('pf_area_kgm2'), errors='coerce') if 'pf_area_kgm2' in pf_enriched else pd.Series(dtype=float)
    energy = pd.to_numeric(pf_enriched.get('energy_mj'), errors='coerce') if 'energy_mj' in pf_enriched else pd.Series(dtype=float)

    valid_pf = pf_vol.dropna()
    out["n_pf_valid"] = int(len(valid_pf))
    out["pf_vol_avg"] = float(valid_pf.mean()) if not valid_pf.empty else float('nan')

    valid_pa = pf_area.dropna()
    out["pf_area_avg"] = float(valid_pa.mean()) if not valid_pa.empty else float('nan')

    if kg_col and not valid_pf.empty:
        weights = pf_enriched.loc[valid_pf.index, kg_col].fillna(0)
        wsum = float(weights.sum())
        if wsum > 0:
            out["pf_vol_weighted"] = float((valid_pf * weights).sum() / wsum)

    out["energy_total_mj"] = float(energy.fillna(0).sum()) if not energy.empty else 0.0

    return out


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
    """Sub-drill depth (m): collar minus bench floor minus toe."""
    return (df["Z_collar"] - bench_height) - df["Z_toe"]


def compute_pasadura_stats(df_pozos: pd.DataFrame) -> dict:
    """Aggregate sub-drill statistics for a blast-hole DataFrame.

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

    The returned rows also include powder-factor aggregates (PF_vol
    kg/m³, PF_area kg/m², total energy MJ, count of valid PF samples)
    computed from the projected holes via `compute_powder_factor`.

    Note: `total_kg` is the **raw** mass of explosive accumulated per
    section. For correlation analysis prefer `pf_vol_avg_kgm3`, which
    normalises that mass by the volume of rock broken (Burden ×
    Espaciamiento × bench height).
    """
    if df_pozos is None or df_pozos.empty or not sections:
        return []

    if tolerance is None:
        tolerance = DEFAULTS.blast_correlation_radius_m

    kg_col = kilos_column(df_pozos)
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
        proj_labeled = proj.copy()
        if not proj_labeled.empty:
            proj_labeled['section_name'] = sec_name

        if proj.empty:
            num_wells = 0
            total_kg = 0.0
            pf_agg = {
                "pf_vol_avg": float('nan'),
                "pf_area_avg": float('nan'),
                "energy_total_mj": 0.0,
                "n_pf_valid": 0,
            }
        else:
            num_wells = len(proj)
            if kg_col and kg_col in proj.columns:
                total_kg = float(proj[kg_col].fillna(0).sum())
            else:
                total_kg = 0.0
            pf_agg = aggregate_powder_factor_by_group(
                df_pozos, 'section_name', sec_name, proj_labeled,
            )
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
                pf_vol_avg_kgm3=float(pf_agg.get("pf_vol_avg") or 0.0),
                pf_area_avg_kgm2=float(pf_agg.get("pf_area_avg") or 0.0),
                energy_total_mj=float(pf_agg.get("energy_total_mj") or 0.0),
                n_pf_valid=int(pf_agg.get("n_pf_valid") or 0),
            )
        )
    return rows


def classify_berm_as_ramp(berm_width: float) -> bool:
    """Return True when a berm of the given width is most likely a ramp."""
    return RAMP.min_width <= berm_width <= RAMP.max_width
