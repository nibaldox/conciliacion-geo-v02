"""
Shared helpers for Drill & Blast ↔ Geotechnical correlation.

Both the Excel writer and the Word report generator need to compute the
same per-section summary (number of nearby blast holes, total kg of
explosive, mean absolute deviation). This module owns that logic so the
two output formats stay in sync.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
from core.config import BLAST, DEFAULTS, EXPLOSIVE, RAMP
from core.blast_metrics import ROCK_DENSITY_DEFAULT_TM3, enrich_blast_dataframe


def _coerce_finite(value) -> float:
    """Coerce a powder-factor aggregate value to a finite float.

    ``aggregate_powder_factor_by_group`` legitimately returns ``float('nan')``
    for PF keys when projected holes exist but lack valid geometry. Since
    ``nan or 0.0`` evaluates to ``nan`` (NaN is truthy), a plain ``float(... or 0.0)``
    leaks NaN through to JSON serialisation and crashes the endpoint. Map any
    non-finite or missing value to ``0.0``; ``n_pf_valid==0`` already conveys
    "no valid PF samples".
    """
    if value is None:
        return 0.0
    f = float(value)
    return f if math.isfinite(f) else 0.0


@dataclass
class BlastCorrelationRow:
    """One row of blast-vs-geotech correlation for a single section.

    ``sector`` mirrors ``SectionLine.sector`` so consumers can group rows by
    geotechnical domain without re-joining the section list. ``rock_density_used``
    is the effective ρ (ton/m³) actually applied when computing this row's
    per-mass powder factor (``pf_g_per_ton_avg`` / ``pf_g_per_ton_net_avg``):
    a per-sector override from ``sector_density`` when present, otherwise the
    caller's global ``rock_density_tm3`` or the ``BLAST`` singleton default.
    """
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
    pf_g_per_ton_avg: float = 0.0
    pf_g_per_ton_net_avg: float = 0.0
    energy_total_mj: float = 0.0
    n_pf_valid: int = 0
    sector: str = ""
    rock_density_used: float = 0.0

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
            self.pf_g_per_ton_avg,
            self.pf_g_per_ton_net_avg,
            self.energy_total_mj,
            self.n_pf_valid,
            self.sector,
            self.rock_density_used,
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


_LENGTH_CANDIDATES = ('longitud_real', 'Len', 'Longitud', 'Length', 'Profundidad')
_INCLINATION_CANDIDATES = ('Inclinacion_real', 'Incl', 'Inclinacion', 'Inclination')


def compute_powder_factor(
    df_pozos: pd.DataFrame,
    rock_density_tm3: Optional[float] = None,
    height_fallback_m: Optional[float] = None,
) -> pd.DataFrame:
    """Compute powder factor for each blast-hole row.

    Powder factor (PF) = explosive mass normalised by the amount of rock
    broken, expressed in three complementary forms:
        PF_vol   [kg/m³]  = Kilos / (Burden × Espaciamiento × Altura_banco)
        PF_area  [kg/m²]  = Kilos / (Burden × Espaciamiento)
        energy_mj         = Kilos × energy_mj_per_kg(Tipo_Explosivo)

    Per-mass powder factor (grams of explosive per ton of rock):
        H_real           = longitud_real × cos(radians(Inclinacion_real))
        PF_g_per_ton     = (Kilos × 1000) / (Burden × Esp × H_real × ρ_roca)
        pasadura         = (Z_collar - bench_height) - Z_toe
        H_net            = H_real - pasadura   (bench height EXCLUDING sub-drill)
        PF_g_per_ton_net = (Kilos × 1000) / (Burden × Esp × H_net × ρ_roca)

    ``H_real`` is the per-hole vertical height derived from the real hole
    geometry. ``Inclinacion_real`` is the deviation FROM VERTICAL in
    degrees (0° = vertical, matching ``core.calculo_tronadura`` where the
    toe vertical offset is ``-length × cos(incl)``); the vertical height
    therefore uses ``cos``, not ``sin``.

    ``H_net`` is the vertical hole extent WITHIN the bench (collar to
    floor), i.e. the design bench height excluding the sub-drill ("sin
    pasadura"). The ``pasadura`` term reuses :func:`_pasadura` with
    ``bench_height = height_fallback_m`` (the configured bench height,
    currently 15 m). When ``Z_collar`` / ``Z_toe`` are missing or the
    resulting pasadura is NaN / negative / non-finite, pasadura falls
    back to 0 so ``H_net = H_real`` (the net metric gracefully equals the
    full metric when sub-drill is unknown). ``H_net`` is clamped to NaN
    when non-positive to avoid spurious negative powder factors. In the
    ENAEX dataset ``Z_collar = Nombre_Banco + 15``, so ``H_net ≈ 15 m``
    for every hole — ``pf_g_per_ton_net`` is therefore the design-bench-
    normalised powder factor, complementary to the primary
    ``pf_g_per_ton``.

    Per-session overrides:
        ``rock_density_tm3`` — in-situ rock bulk density (ton/m³) used as
        ``ρ_roca`` in ``PF_g_per_ton``. ``None`` (default) falls back to
        ``BLAST.rock_density_tm3`` (2.7 ton/m³), preserving the original
        behaviour.
        ``height_fallback_m`` — vertical height used when ``longitud_real``
        or ``Inclinacion_real`` is missing/invalid. ``None`` (default)
        falls back to ``BLAST.height_fallback_m`` (15.0 m).

    If Burden/Espaciamiento columns are missing, estimate them from the
    median nearest-neighbour distance (k=4) among the collars in the
    same blast pattern. Falls back gracefully when insufficient data.

    Returns a copy of df_pozos with new columns:
        pf_vol_kgm3: float or NaN
        pf_area_kgm2: float or NaN
        pf_g_per_ton: float or NaN
        pf_g_per_ton_net: float or NaN (g/ton, bench height excluding sub-drill)
        energy_mj: float (always computed if Kilos + Tipo_Explosivo available)
        burden_est_m: float (resolved Burden)
        esp_est_m: float (resolved Espaciamiento)
        height_real_m: float (per-hole vertical height used for pf_g_per_ton)
        height_net_m: float (per-hole vertical height excluding sub-drill, used
            for pf_g_per_ton_net; equals height_real_m when sub-drill unknown)
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

    length_col = first_present_column(out, _LENGTH_CANDIDATES)
    incl_col = first_present_column(out, _INCLINATION_CANDIDATES)
    length_vals = (
        pd.to_numeric(out[length_col], errors='coerce') if length_col
        else pd.Series([np.nan] * len(out), index=out.index)
    )
    incl_vals = (
        pd.to_numeric(out[incl_col], errors='coerce') if incl_col
        else pd.Series([np.nan] * len(out), index=out.index)
    )

    height_real = pd.Series(
        float(BLAST.height_fallback_m if height_fallback_m is None else height_fallback_m),
        index=out.index,
    )
    valid_h = length_vals.notna() & incl_vals.notna() & (length_vals > 0) & (incl_vals >= 0)
    height_real.loc[valid_h] = length_vals[valid_h] * np.cos(np.radians(incl_vals[valid_h]))
    out['height_real_m'] = height_real

    rho_rock = float(BLAST.rock_density_tm3 if rock_density_tm3 is None else rock_density_tm3)
    denom_gt = burden_est * esp_est * height_real * rho_rock
    pf_gt = np.where(denom_gt > 0, (kilos * 1000.0) / denom_gt, np.nan)
    out['pf_g_per_ton'] = pd.Series(pf_gt, index=out.index)

    # Per-mass powder factor normalised by the bench height EXCLUDING sub-drill
    # ("sin pasadura"). H_net is the vertical hole extent WITHIN the bench
    # (collar to floor), i.e. the design bench height minus the sub-drill. In
    # the ENAEX dataset ``Z_collar = Nombre_Banco + 15``, so H_net ≈ 15 m (the
    # design bench height) for all holes — this metric is therefore the
    # design-bench-normalised powder factor, complementary to the primary
    # ``pf_g_per_ton`` which uses the full real hole length.
    bench_h_for_pasadura = float(
        BLAST.height_fallback_m if height_fallback_m is None else height_fallback_m
    )
    height_net = height_real.copy()
    pasadura_valid = pd.Series(False, index=out.index)
    if {'Z_collar', 'Z_toe'}.issubset(out.columns):
        pasadura_raw = pd.to_numeric(_pasadura(out, bench_h_for_pasadura), errors='coerce')
        valid_pas = pasadura_raw.notna() & (pasadura_raw >= 0) & np.isfinite(pasadura_raw)
        pasadura_valid = valid_pas.fillna(False)
        height_net = height_real - pasadura_raw.where(pasadura_valid, 0.0).fillna(0.0)
    height_net = height_net.where(height_net > 0, np.nan)
    out['height_net_m'] = height_net

    denom_gt_net = burden_est * esp_est * height_net * rho_rock
    pf_gt_net = np.where(denom_gt_net > 0, (kilos * 1000.0) / denom_gt_net, np.nan)
    out['pf_g_per_ton_net'] = pd.Series(pf_gt_net, index=out.index)

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
    rock_density_tm3: Optional[float] = None,
    height_fallback_m: Optional[float] = None,
) -> dict:
    """Aggregate powder factor metrics for a group of wells.

    Parameters
    ----------
    df_pozos : DataFrame output of `compute_powder_factor`.
    group_by : column to filter on (e.g. 'section_name', 'level', 'malla').
    group_value : value of that column to keep.
    projected_pozos : DataFrame with rows considered for the aggregation.
    rock_density_tm3 : optional per-session rock density override (ton/m³).
        ``None`` defers to ``BLAST.rock_density_tm3`` inside
        :func:`compute_powder_factor`.
    height_fallback_m : optional per-session height fallback override (m).
        ``None`` defers to ``BLAST.height_fallback_m`` inside
        :func:`compute_powder_factor`.

    Returns dict with:
        pf_vol_avg: float or NaN  (kg/m³, mean)
        pf_area_avg: float or NaN (kg/m², mean)
        pf_vol_weighted: float or NaN (weighted by Kilos)
        pf_g_per_ton_avg: float or NaN (g/ton, mean)
        pf_g_per_ton_weighted: float or NaN (g/ton, weighted by Kilos)
        pf_g_per_ton_net_avg: float or NaN (g/ton, mean, bench height excl. sub-drill)
        pf_g_per_ton_net_weighted: float or NaN (g/ton, weighted by Kilos)
        energy_total_mj: float
        kg_total: float
        n_wells: int
        n_pf_valid: int  (count of rows with valid PF)
    """
    out = {
        "pf_vol_avg": np.nan,
        "pf_area_avg": np.nan,
        "pf_vol_weighted": np.nan,
        "pf_g_per_ton_avg": np.nan,
        "pf_g_per_ton_weighted": np.nan,
        "pf_g_per_ton_net_avg": np.nan,
        "pf_g_per_ton_net_weighted": np.nan,
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

    pf_enriched = compute_powder_factor(
        sub,
        rock_density_tm3=rock_density_tm3,
        height_fallback_m=height_fallback_m,
    )
    pf_vol = pd.to_numeric(pf_enriched.get('pf_vol_kgm3'), errors='coerce') if 'pf_vol_kgm3' in pf_enriched else pd.Series(dtype=float)
    pf_area = pd.to_numeric(pf_enriched.get('pf_area_kgm2'), errors='coerce') if 'pf_area_kgm2' in pf_enriched else pd.Series(dtype=float)
    pf_gt = pd.to_numeric(pf_enriched.get('pf_g_per_ton'), errors='coerce') if 'pf_g_per_ton' in pf_enriched else pd.Series(dtype=float)
    pf_gt_net = pd.to_numeric(pf_enriched.get('pf_g_per_ton_net'), errors='coerce') if 'pf_g_per_ton_net' in pf_enriched else pd.Series(dtype=float)
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

    valid_gt = pf_gt.dropna()
    out["pf_g_per_ton_avg"] = float(valid_gt.mean()) if not valid_gt.empty else float('nan')

    if kg_col and not valid_gt.empty:
        weights_gt = pf_enriched.loc[valid_gt.index, kg_col].fillna(0)
        wsum_gt = float(weights_gt.sum())
        if wsum_gt > 0:
            out["pf_g_per_ton_weighted"] = float((valid_gt * weights_gt).sum() / wsum_gt)

    valid_gt_net = pf_gt_net.dropna()
    out["pf_g_per_ton_net_avg"] = float(valid_gt_net.mean()) if not valid_gt_net.empty else float('nan')

    if kg_col and not valid_gt_net.empty:
        weights_gt_net = pf_enriched.loc[valid_gt_net.index, kg_col].fillna(0)
        wsum_gt_net = float(weights_gt_net.sum())
        if wsum_gt_net > 0:
            out["pf_g_per_ton_net_weighted"] = float(
                (valid_gt_net * weights_gt_net).sum() / wsum_gt_net
            )

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
    rock_density_tm3: Optional[float] = None,
    height_fallback_m: Optional[float] = None,
    sector_density: Optional[Dict[str, float]] = None,
) -> List[BlastCorrelationRow]:
    """Return one BlastCorrelationRow per section.

    For each section, projects blast holes within `tolerance` metres
    (default: DEFAULTS.blast_correlation_radius_m) of the section axis and
    joins with the mean absolute deviation of the matching geotech
    comparison rows.

    The returned rows also include powder-factor aggregates (PF_vol
    kg/m³, PF_area kg/m², total energy MJ, count of valid PF samples)
    computed from the projected holes via `compute_powder_factor`.

    Per-session overrides:
        ``rock_density_tm3`` / ``height_fallback_m`` — optional rock
        density (ton/m³) and height fallback (m) forwarded to
        :func:`aggregate_powder_factor_by_group` and ultimately
        :func:`compute_powder_factor`. ``None`` defers to the
        ``BLAST`` singleton defaults (2.7 ton/m³, 15.0 m), preserving
        the original behaviour.
        ``sector_density`` — optional ``{sector: rho}`` map keyed by
        :class:`SectionLine.sector` (the geotechnical domain label). When
        a section's ``sector`` is present in the map, that ρ overrides
        the caller's global ``rock_density_tm3`` for that section only;
        sectors not in the map (or an empty/``None`` map) keep falling
        back to the global ρ. The effective ρ actually applied is
        recorded on the row as ``rock_density_used`` for transparency.

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
        sec_sector = getattr(sec, "sector", "") or ""
        # Per-sector ρ override: a section whose sector is in the
        # ``sector_density`` map uses that ρ; others keep the caller's
        # global ``rock_density_tm3`` (which itself falls back to the
        # ``BLAST`` singleton inside compute_powder_factor when None).
        sec_rho = (
            sector_density.get(sec_sector)
            if sector_density and sec_sector
            else None
        )

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
                "pf_g_per_ton_avg": float('nan'),
                "pf_g_per_ton_net_avg": float('nan'),
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
                rock_density_tm3=sec_rho if sec_rho is not None else rock_density_tm3,
                height_fallback_m=height_fallback_m,
            )
        # Effective ρ applied for this row, for transparency. When a
        # sector-specific ρ was used, record it; otherwise surface the
        # caller's global value (or the BLAST default when both are None).
        eff_rho = sec_rho if sec_rho is not None else (
            rock_density_tm3 if rock_density_tm3 is not None else BLAST.rock_density_tm3
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
                pf_vol_avg_kgm3=_coerce_finite(pf_agg.get("pf_vol_avg")),
                pf_area_avg_kgm2=_coerce_finite(pf_agg.get("pf_area_avg")),
                pf_g_per_ton_avg=_coerce_finite(pf_agg.get("pf_g_per_ton_avg")),
                pf_g_per_ton_net_avg=_coerce_finite(pf_agg.get("pf_g_per_ton_net_avg")),
                energy_total_mj=_coerce_finite(pf_agg.get("energy_total_mj")),
                n_pf_valid=int(pf_agg.get("n_pf_valid") or 0),
                sector=sec_sector,
                rock_density_used=_coerce_finite(eff_rho),
            )
        )
    return rows


def classify_berm_as_ramp(berm_width: float) -> bool:
    """Return True when a berm of the given width is most likely a ramp."""
    return RAMP.min_width <= berm_width <= RAMP.max_width


def compute_monthly_trend(blast_df: pd.DataFrame, damage_col: str = 'avg_over_break') -> pd.DataFrame:
    """Aggregate PF and damage by month from a blast DataFrame.

    Requires ``fecha_tronadura`` and ``pf_vol_kgm3``. Returns a frame with
    columns ``mes`` (YYYY-MM), ``pf_promedio``, ``damage_promedio``,
    ``n_pozos``, ``trend_slope`` and ``trend_intercept``. The linear trend is
    fit with ``np.polyfit`` only when at least three months are present.
    Returns an empty frame when the required columns or valid dates are
    missing.
    """
    if (blast_df is None or blast_df.empty
            or 'fecha_tronadura' not in blast_df.columns
            or 'pf_vol_kgm3' not in blast_df.columns):
        return pd.DataFrame()

    df = blast_df.copy()
    df['_mes'] = pd.to_datetime(df['fecha_tronadura'], errors='coerce').dt.to_period('M')
    df = df[df['_mes'].notna()]
    if df.empty:
        return pd.DataFrame()

    df['pf_vol_kgm3'] = pd.to_numeric(df['pf_vol_kgm3'], errors='coerce')
    grouped = df.groupby('_mes')
    counts = grouped.size()
    agg = {
        'pf_promedio': grouped['pf_vol_kgm3'].mean(),
        'damage_promedio': (grouped[damage_col].mean()
                            if damage_col in df.columns
                            else pd.Series(np.nan, index=counts.index)),
        'n_pozos': counts,
    }
    out = pd.DataFrame(agg).reset_index()

    pf_vals = out['pf_promedio'].to_numpy(dtype=float)
    if len(out) >= 3 and not np.isnan(pf_vals).any():
        slope, intercept = np.polyfit(np.arange(len(out), dtype=float), pf_vals, 1)
        out['trend_slope'] = slope
        out['trend_intercept'] = intercept
    else:
        out['trend_slope'] = np.nan
        out['trend_intercept'] = np.nan

    out['mes'] = out['_mes'].astype(str)
    out = out[['mes', 'pf_promedio', 'damage_promedio', 'n_pozos',
               'trend_slope', 'trend_intercept']]
    return out.sort_values('mes').reset_index(drop=True)


def detect_pf_outliers_iqr(blast_df: pd.DataFrame, k: float = 1.5) -> pd.DataFrame:
    """Return rows whose ``pf_vol_kgm3`` is outside Q1 - k*IQR or Q3 + k*IQR.

    Returns an empty frame when the column is missing, fewer than four valid
    values exist, or the interquartile range is zero (no spread to flag).
    """
    if blast_df is None or blast_df.empty or 'pf_vol_kgm3' not in blast_df.columns:
        return pd.DataFrame()

    pf = pd.to_numeric(blast_df['pf_vol_kgm3'], errors='coerce')
    valid = pf.dropna()
    if len(valid) < 4:
        return pd.DataFrame()

    q1, q3 = np.quantile(valid.to_numpy(dtype=float), [0.25, 0.75])
    iqr = q3 - q1
    if iqr == 0:
        return pd.DataFrame()

    lower = q1 - k * iqr
    upper = q3 + k * iqr
    mask = pf.notna() & ((pf < lower) | (pf > upper))
    return blast_df.loc[mask].copy()


def split_campaign(blast_df: pd.DataFrame, campaign_start_date: str | None) -> dict:
    """Split blast_df into 'before' and 'after' cohorts by date.

    Returns ``{'before': df, 'after': df, 'has_campaign': bool}``. When
    ``campaign_start_date`` is None, ``fecha_tronadura`` is missing or the
    cutoff cannot be parsed, everything is returned under 'before' with
    ``has_campaign`` set to False.
    """
    empty_after = pd.DataFrame()
    if campaign_start_date is None:
        before = blast_df if blast_df is not None else pd.DataFrame()
        return {'before': before, 'after': empty_after, 'has_campaign': False}

    if (blast_df is None or blast_df.empty
            or 'fecha_tronadura' not in blast_df.columns):
        before = blast_df if blast_df is not None else pd.DataFrame()
        return {'before': before, 'after': empty_after, 'has_campaign': False}

    cutoff = pd.to_datetime(campaign_start_date, errors='coerce')
    if pd.isna(cutoff):
        return {'before': blast_df, 'after': empty_after, 'has_campaign': False}

    dates = pd.to_datetime(blast_df['fecha_tronadura'], errors='coerce')
    before_mask = dates <= cutoff
    after_mask = dates > cutoff
    return {
        'before': blast_df.loc[before_mask.fillna(False)].copy(),
        'after': blast_df.loc[after_mask.fillna(False)].copy(),
        'has_campaign': True,
    }


__all__ = [
    "BlastCorrelationRow",
    "aggregate_powder_factor_by_group",
    "classify_berm_as_ramp",
    "compute_blast_geotech_correlation",
    "compute_monthly_trend",
    "compute_powder_factor",
    "compute_signed_deviations",
    "detect_pf_outliers_iqr",
    "split_campaign",
]
