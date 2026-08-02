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
from core.blast_metrics import (
    ROCK_DENSITY_DEFAULT_TM3,
    compute_influence_area_report,
    enrich_blast_dataframe,
)


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
    pf_g_per_ton_inf_avg: float = 0.0
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
            self.pf_g_per_ton_inf_avg,
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


def _assign_voronoi_global(
    df: pd.DataFrame,
    *,
    group_col: Optional[str] = None,
    boundary_polygon: Optional[list] = None,
    boundary_polygons: Optional[dict] = None,
) -> dict:
    """Global Voronoi assignment with conservation diagnostics (§2.1).

    Strategy: compute the Voronoi cells ONCE over all holes of the event
    and clip them against a single event domain (``boundary_polygon`` or
    the collar bounding box). Per-malla polygons (``boundary_polygons``
    dict) are accepted only when they are pairwise non-overlapping and
    cover all holes; overlaps and gaps are detected and reported.

    Returns a dict with area_m2 / area_status / domain_area_m2 Series
    aligned to ``df.index`` plus method, messages, assigned_area,
    residual_m2, residual_pct and conservation_ok.
    """
    n = len(df)
    nan_area = pd.Series([np.nan] * n, index=df.index, dtype=float)
    messages: list[str] = []

    if boundary_polygons is not None and group_col is not None:
        # Strategy 2 (validated): per-malla independent polygons.
        try:
            import shapely.geometry as sg
            from shapely.ops import unary_union
        except ImportError:
            messages.append("boundary_polygons requiere shapely; se usa dominio global")
            boundary_polygons = None
        if boundary_polygons is not None:
            polys = {str(k): sg.Polygon([(float(x), float(y)) for x, y in v])
                     for k, v in boundary_polygons.items()}
            overlap_ok = True
            keys = list(polys)
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    inter = polys[keys[i]].intersection(polys[keys[j]])
                    if not inter.is_empty and inter.area > 1e-6:
                        overlap_ok = False
                        messages.append(
                            f"polígonos de mallas superpuestos: {keys[i]} ∩ {keys[j]} "
                            f"= {inter.area:.2f} m²"
                        )
            union = unary_union(list(polys.values()))
            union_area = float(union.area)
            sum_areas = float(sum(p.area for p in polys.values()))
            if sum_areas - union_area > 1e-6:
                messages.append(
                    f"polígonos de mallas solapados en la unión: "
                    f"{sum_areas - union_area:.2f} m²"
                )
            # Gap detection: the event bbox (all collars) vs the union of
            # malla polygons — informative, not a conservation failure.
            x0c, y0c = df[["X", "Y"]].min()
            x1c, y1c = df[["X", "Y"]].max()
            hull = sg.box(float(x0c), float(y0c), float(x1c), float(y1c))
            gap = float(hull.area) - union_area
            if gap > 1e-6:
                messages.append(
                    f"huecos entre polígonos de mallas: {gap:.2f} m² sin asignar"
                )
            # Assign each hole to its malla's polygon and clip per-malla.
            areas = nan_area.copy()
            status = pd.Series("invalid", index=df.index, dtype=object)
            rep_parts: list[pd.DataFrame] = []
            for malla_name, poly in polys.items():
                mask = df[group_col].astype(str) == str(malla_name)
                if not mask.any():
                    messages.append(f"malla {malla_name} sin pozos")
                    continue
                rep = compute_influence_area_report(
                    df.loc[mask], boundary_polygon=boundary_polygons[malla_name],
                )
                areas.loc[mask] = rep["area_m2"]
                status.loc[mask] = rep["area_status"]
                rep_parts.append(rep)
            domain = union_area
            method = "per_malla_polygon"
            assigned = float(areas.sum())
            if not overlap_ok:
                domain = sum_areas
                messages.append("dominio definido como suma de polígonos (solapados)")
            conservation_ok = overlap_ok and abs(assigned - domain) <= domain * (
                DEFAULTS.voronoi_conservation_tolerance_pct / 100.0
            )
            result = _voronoi_result(areas, status, domain, assigned, method, messages,
                                     conservation_ok)
            if rep_parts:
                rep_all = pd.concat(rep_parts)
                result["collar_domain_status"] = rep_all["collar_domain_status"]
                result["collar_inside_domain"] = rep_all["collar_inside_domain"]
                result["collar_on_boundary"] = rep_all["collar_on_boundary"]
                result["collar_validation_message"] = rep_all["collar_validation_message"]
                ext_mask = ~rep_all["collar_inside_domain"].astype(bool).to_numpy()
                labels_all = rep_all["label_pozo"].astype(str).to_numpy() if "label_pozo" in rep_all.columns else rep_all.index.astype(str).to_numpy()
                result["outside_domain_hole_count"] = int(ext_mask.sum())
                result["outside_domain_hole_ids"] = "|".join(labels_all[ext_mask]) if ext_mask.any() else ""
                result["outside_domain_assigned_area_m2"] = float(
                    rep_all.loc[~rep_all["collar_inside_domain"].astype(bool), "area_m2"].sum()
                )
                result["invalid_coordinate_hole_count"] = int(
                    (rep_all["collar_domain_status"] == "INVALID_COORDINATES").sum()
                )
            else:
                result["collar_domain_status"] = pd.Series("INSIDE", index=df.index, dtype=object)
                result["collar_inside_domain"] = pd.Series(True, index=df.index, dtype=bool)
                result["collar_on_boundary"] = pd.Series(False, index=df.index, dtype=bool)
                result["collar_validation_message"] = pd.Series("", index=df.index, dtype=object)
                result["outside_domain_hole_count"] = 0
                result["outside_domain_hole_ids"] = ""
                result["outside_domain_assigned_area_m2"] = 0.0
                result["invalid_coordinate_hole_count"] = 0
            return result
        # fall through to the global path when shapely is missing

    # Strategy 1 (default): ONE Voronoi over the whole event, one domain.
    rep = compute_influence_area_report(df, boundary_polygon=boundary_polygon)
    method = "global_polygon" if boundary_polygon is not None else "global_bbox"
    domain = float(rep["domain_area_m2"].iloc[0]) if "domain_area_m2" in rep.columns else np.nan
    assigned = float(rep["area_m2"].sum())

    # Auditoría §3.1: external/invalid collars — explicit count, ids and
    # zero assigned area; never masked by duplicate sharing.
    inside = rep["collar_inside_domain"].astype(bool).to_numpy() if "collar_inside_domain" in rep.columns else np.ones(len(rep), dtype=bool)
    labels = df["label_pozo"].astype(str).to_numpy() if "label_pozo" in df.columns else df.index.astype(str).to_numpy()
    ext_mask = ~inside
    n_outside = int(ext_mask.sum())
    ext_ids = labels[ext_mask]
    ext_area = float(rep.loc[rep["collar_inside_domain"] == False, "area_m2"].sum()) if "collar_inside_domain" in rep.columns else 0.0  # noqa: E712
    if n_outside:
        messages.append(
            f"pozos excluidos fuera del dominio o con coordenadas inválidas: "
            f"{n_outside} ({', '.join(ext_ids[:10])}{'…' if n_outside > 10 else ''}); "
            f"reciben 0 m² y no participan del reparto"
        )

    if np.isnan(domain):
        messages.append("dominio no disponible (shapely ausente o sin suficientes sitios)")
        # Even without a domain, count outside/invalid from the report.
        _inside = rep["collar_inside_domain"].astype(bool).to_numpy() if "collar_inside_domain" in rep.columns else np.ones(len(rep), dtype=bool)
        _ext_mask = ~_inside
        _labels = df["label_pozo"].astype(str).to_numpy() if "label_pozo" in df.columns else df.index.astype(str).to_numpy()
        result = _voronoi_result(rep["area_m2"], rep["area_status"], np.nan, assigned,
                                 method, messages, False)
        result["collar_domain_status"] = rep["collar_domain_status"]
        result["collar_inside_domain"] = rep["collar_inside_domain"]
        result["collar_on_boundary"] = rep["collar_on_boundary"]
        result["collar_validation_message"] = rep["collar_validation_message"]
        result["outside_domain_hole_count"] = int(_ext_mask.sum())
        result["outside_domain_hole_ids"] = "|".join(_labels[_ext_mask]) if _ext_mask.any() else ""
        result["outside_domain_assigned_area_m2"] = float(
            rep.loc[~_inside, "area_m2"].sum() if "area_m2" in rep.columns else 0.0
        )
        result["invalid_coordinate_hole_count"] = int(
            (rep["collar_domain_status"] == "INVALID_COORDINATES").sum()
            if "collar_domain_status" in rep.columns else 0
        )
        return result
    residual = assigned - domain
    residual_pct = residual / domain * 100.0 if domain > 0 else np.nan
    conservation_ok = abs(residual_pct) <= DEFAULTS.voronoi_conservation_tolerance_pct
    if not conservation_ok:
        messages.append(
            f"conservación Voronoi falla: asignado {assigned:.2f} m² vs dominio "
            f"{domain:.2f} m² ({residual_pct:+.2f}%) — PF por área de influencia "
            "bloqueado"
        )
    result = _voronoi_result(rep["area_m2"], rep["area_status"], domain, assigned,
                             method, messages, conservation_ok)
    result["collar_domain_status"] = rep["collar_domain_status"]
    result["collar_inside_domain"] = rep["collar_inside_domain"]
    result["collar_on_boundary"] = rep["collar_on_boundary"]
    result["collar_validation_message"] = rep["collar_validation_message"]
    result["outside_domain_hole_count"] = int(n_outside)
    result["outside_domain_hole_ids"] = "|".join(ext_ids) if n_outside else ""
    result["outside_domain_assigned_area_m2"] = ext_area
    result["invalid_coordinate_hole_count"] = int(
        (rep["collar_domain_status"] == "INVALID_COORDINATES").sum()
        if "collar_domain_status" in rep.columns else 0
    )
    return result


def _voronoi_result(areas, status, domain, assigned, method, messages, ok) -> dict:
    """Assemble the conservation diagnostics dict (§2.1)."""
    residual = (assigned - domain) if np.isfinite(domain) else np.nan
    residual_pct = residual / domain * 100.0 if np.isfinite(domain) and domain > 0 else np.nan
    return {
        "area_m2": areas,
        "area_status": status,
        "domain_area_m2": float(domain) if np.isfinite(domain) else np.nan,
        "method": method,
        "messages": " | ".join(messages) if messages else "",
        "assigned_area": assigned,
        "residual_m2": residual,
        "residual_pct": residual_pct,
        "conservation_ok": bool(ok),
    }


def compute_powder_factor(
    df_pozos: pd.DataFrame,
    rock_density_tm3: Optional[float] = None,
    height_fallback_m: Optional[float] = None,
    boundary_polygon: Optional[list] = None,
    boundary_polygons: Optional[dict] = None,
    bench_height_m: Optional[float] = None,
    bench_height_source: str = "event_provided",
    allow_bench_height_assumption: bool = False,
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
    pasadura"). The ``pasadura`` term reuses :func:`_pasadura` with the
    RESOLVED per-row bench height (event value or validated dataset
    column — never an automatic default). When ``Z_collar`` / ``Z_toe``
    are missing, or the bench height is not confirmed, ``H_net`` is
    BLOCKED (NaN): no silent pasadura=0 pass-through. ``H_net`` is
    clamped to NaN when non-positive to avoid spurious negative powder
    factors. With a declared 15 m bench (e.g. the ENAEX event), ``H_net
    ≈ 15 m`` and ``pf_g_per_ton_net`` is the design-bench-normalised
    powder factor, complementary to the primary ``pf_g_per_ton``.

    Per-session overrides:
        ``rock_density_tm3`` — in-situ rock bulk density (ton/m³) used as
        ``ρ_roca`` in ``PF_g_per_ton``. ``None`` (default) falls back to
        ``BLAST.rock_density_tm3`` (2.7 ton/m³), preserving the original
        behaviour.
        ``height_fallback_m`` — vertical height used when ``longitud_real``
        or ``Inclinacion_real`` is missing/invalid, ONLY under an
        authorised assumption (``allow_bench_height_assumption=True``);
        otherwise the height-dependent indicators are blocked.

    If Burden/Espaciamiento columns are missing, estimate them from the
    median nearest-neighbour distance (k=4) among the collars in the
    same blast pattern. Falls back gracefully when insufficient data.

    Returns a copy of df_pozos with new columns:
        pf_vol_kgm3: float or NaN
        pf_area_kgm2: float or NaN
        pf_g_per_ton: float or NaN
        pf_g_per_ton_net: float or NaN (g/ton, bench height excluding sub-drill)
        pf_g_per_ton_inf: float or NaN (g/ton, using the per-hole Voronoi
            influence area ``area_influence_m2`` instead of Burden × Esp)
        area_influence_m2: float or NaN (Voronoi/Thiessen cell area per hole)
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

    if group_col and group_col in out.columns:
        groups = out.groupby(out[group_col].astype(str), dropna=False)
    else:
        groups = [('__all__', out)]
        groups = iter(groups)

    burden_est = pd.Series([np.nan] * len(out), index=out.index)
    esp_est = pd.Series([np.nan] * len(out), index=out.index)
    influence_area = pd.Series([np.nan] * len(out), index=out.index)
    area_status = pd.Series("invalid", index=out.index, dtype=object)
    domain_area = pd.Series(np.nan, index=out.index, dtype=float)

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

    # Fase 1.1 cierre §2.1: the Voronoi influence area is computed ONCE on
    # the whole event (global domain), never per-malla against the same
    # polygon — otherwise mallas reuse the same surface and the assigned
    # area exceeds the event domain. `malla_id` remains a per-hole
    # attribute. Per-malla polygons are supported only when explicitly
    # provided AND validated as pairwise non-overlapping.
    voronoi_result = _assign_voronoi_global(
        out,
        group_col=group_col if group_col else None,
        boundary_polygon=boundary_polygon,
        boundary_polygons=boundary_polygons,
    )
    influence_area = voronoi_result["area_m2"]
    area_status = voronoi_result["area_status"]
    domain_area = voronoi_result["domain_area_m2"]
    out['voronoi_method'] = voronoi_result["method"]
    out['voronoi_validation_messages'] = voronoi_result["messages"]
    out['assigned_area_m2'] = float(voronoi_result["assigned_area"])
    out['area_residual_m2'] = float(voronoi_result["residual_m2"])
    out['area_residual_pct'] = float(voronoi_result["residual_pct"])
    out['voronoi_conservation_ok'] = bool(voronoi_result["conservation_ok"])
    # Auditoría §3.1: per-collar domain provenance propagated to the
    # operational frame.
    out['collar_domain_status'] = voronoi_result["collar_domain_status"]
    out['collar_inside_domain'] = voronoi_result["collar_inside_domain"]
    out['collar_on_boundary'] = voronoi_result["collar_on_boundary"]
    out['collar_validation_message'] = voronoi_result["collar_validation_message"]
    out['outside_domain_hole_count'] = voronoi_result["outside_domain_hole_count"]
    out['outside_domain_hole_ids'] = voronoi_result["outside_domain_hole_ids"]
    out['outside_domain_assigned_area_m2'] = voronoi_result["outside_domain_assigned_area_m2"]
    out['invalid_coordinate_hole_count'] = voronoi_result["invalid_coordinate_hole_count"]

    out['burden_est_m'] = burden_est
    out['esp_est_m'] = esp_est
    out['area_influence_m2'] = influence_area
    out['area_status'] = area_status.astype(str)
    out['domain_area_m2'] = domain_area

    # Fase 1.1 cierre §2.2: bench height with full provenance — never a
    # silent 15 m fallback. Resolution order: per-row bench_height_m
    # column (validated dataset attribute) > caller-provided
    # bench_height_m (event value) > authorised explicit assumption
    # (visible config value, flagged) > MISSING (blocked).
    if "bench_height_m" in out.columns:
        bh_col = pd.to_numeric(out["bench_height_m"], errors="coerce")
        bench_h = bh_col.where(bh_col > 0)
        bh_status = pd.Series("PROVIDED", index=out.index)
        bh_source = pd.Series("data_column", index=out.index)
        bh_message = pd.Series("", index=out.index)
        bh_assumed = pd.Series(False, index=out.index)
        invalid = bench_h.isna() & bh_col.notna()
        bh_status.loc[invalid] = "INVALID"
        bh_message.loc[invalid] = (
            "Altura de banco inválida (≤0 o no numérica): indicadores "
            "dependientes bloqueados"
        )
        missing = bh_col.isna()
        bh_status.loc[missing] = "MISSING"
        bh_message.loc[missing] = (
            "Altura de banco ausente en la columna del evento: indicadores "
            "dependientes bloqueados (sin supuesto silencioso)"
        )
        bh_assumed.loc[missing] = True
    elif bench_height_m is not None:
        try:
            bh_val = float(bench_height_m)
            is_nan = np.isnan(bh_val)
        except (TypeError, ValueError):
            bh_val, is_nan = np.nan, True
        if is_nan:
            bench_h = pd.Series(np.nan, index=out.index)
            bh_status = pd.Series("MISSING", index=out.index)
            bh_source = pd.Series(bench_height_source, index=out.index)
            bh_message = pd.Series(
                "Altura de banco ausente: indicadores dependientes bloqueados "
                "(sin supuesto silencioso). Declare bench_height_m o autorice el "
                "supuesto explícito.",
                index=out.index,
            )
            bh_assumed = pd.Series(True, index=out.index)
        elif bh_val > 0:
            bench_h = pd.Series(bh_val, index=out.index)
            bh_status = pd.Series(
                "DERIVED" if bench_height_source == "derived_from_surfaces" else "PROVIDED",
                index=out.index,
            )
            bh_source = pd.Series(bench_height_source, index=out.index)
            bh_message = pd.Series("", index=out.index)
            bh_assumed = pd.Series(False, index=out.index)
        else:
            bench_h = pd.Series(np.nan, index=out.index)
            bh_status = pd.Series("INVALID", index=out.index)
            bh_source = pd.Series(bench_height_source, index=out.index)
            bh_message = pd.Series(
                "Altura de banco inválida (≤0): indicadores dependientes bloqueados",
                index=out.index,
            )
            bh_assumed = pd.Series(True, index=out.index)
    elif allow_bench_height_assumption:
        bench_h = pd.Series(float(DEFAULTS.blast_default_bench_height), index=out.index)
        bh_status = pd.Series("EXPLICIT_ASSUMPTION", index=out.index)
        bh_source = pd.Series("default_assumption_config", index=out.index)
        bh_message = pd.Series(
            f"Supuesto explícito autorizado: altura de banco = "
            f"{DEFAULTS.blast_default_bench_height} m (configuración visible). "
            "Declare bench_height_m para limpiar el supuesto.",
            index=out.index,
        )
        bh_assumed = pd.Series(True, index=out.index)
    else:
        bench_h = pd.Series(np.nan, index=out.index)
        bh_status = pd.Series("MISSING", index=out.index)
        bh_source = pd.Series("", index=out.index)
        bh_message = pd.Series(
            "Altura de banco ausente: indicadores dependientes bloqueados "
            "(sin supuesto silencioso). Declare bench_height_m o autorice el "
            "supuesto explícito.",
            index=out.index,
        )
        bh_assumed = pd.Series(True, index=out.index)

    out['bench_height_m'] = bench_h
    out['bench_height_status'] = bh_status
    out['bench_height_source'] = bh_source
    out['bench_height_assumption_flag'] = bh_assumed
    out['bench_height_user_confirmed'] = ~(bh_status.isin(["MISSING", "INVALID"]))
    out['bench_height_validation_message'] = bh_message
    height_blocked = bench_h.isna()

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

    # §2.2: the real vertical height only exists from valid length/inclination;
    # the config fallback is only usable under an authorised assumption.
    if allow_bench_height_assumption:
        fb = BLAST.height_fallback_m if height_fallback_m is None else height_fallback_m
        height_real = pd.Series(
            float(fb) if fb > 0 else np.nan,
            index=out.index,
        )
    else:
        height_real = pd.Series(np.nan, index=out.index)
    valid_h = length_vals.notna() & incl_vals.notna() & (length_vals > 0) & (incl_vals >= 0)
    height_real.loc[valid_h] = length_vals[valid_h] * np.cos(np.radians(incl_vals[valid_h]))
    out['height_real_m'] = height_real

    rho_rock = float(BLAST.rock_density_tm3 if rock_density_tm3 is None else rock_density_tm3)
    denom_gt = burden_est * esp_est * height_real * rho_rock
    pf_gt = np.where(denom_gt > 0, (kilos * 1000.0) / denom_gt, np.nan)
    out['pf_g_per_ton'] = pd.Series(pf_gt, index=out.index)

    # Per-mass powder factor using the per-hole Voronoi influence area
    # (area_influence_m2) instead of the nominal Burden × Esp pattern area.
    denom_gt_inf = influence_area * height_real * rho_rock
    pf_gt_inf = np.where(denom_gt_inf > 0, (kilos * 1000.0) / denom_gt_inf, np.nan)
    out['pf_g_per_ton_inf'] = pd.Series(pf_gt_inf, index=out.index)

    # §2.1: when the Voronoi conservation check fails, the influence-area
    # powder factor is BLOCKED (NaN) — never reported as reliable.
    if "voronoi_conservation_ok" in out.columns:
        ok_mask = out["voronoi_conservation_ok"].astype(bool)
        if not ok_mask.all():
            out.loc[~ok_mask, "pf_g_per_ton_inf"] = np.nan

    # Auditoría §3.1: collars outside the domain (or with invalid
    # coordinates) never produce powder factor — zero area, NaN PF.
    if "collar_inside_domain" in out.columns:
        inside_mask = out["collar_inside_domain"].astype(bool)
        if not inside_mask.all():
            out.loc[~inside_mask, ["pf_vol_kgm3", "pf_g_per_ton", "pf_g_per_ton_net", "pf_g_per_ton_inf"]] = np.nan

    # Per-mass powder factor normalised by the bench height EXCLUDING sub-drill
    # ("sin pasadura"). H_net is the vertical hole extent WITHIN the bench
    # (collar to floor), i.e. the design bench height minus the sub-drill. In
    # with a declared 15 m bench (ENAEX event), H_net ≈ 15 m (the
    # design bench height) for all holes — this metric is therefore the
    # design-bench-normalised powder factor, complementary to the primary
    # ``pf_g_per_ton`` which uses the full real hole length.
    height_net = height_real.copy()
    pasadura_valid = pd.Series(False, index=out.index)
    if {'Z_collar', 'Z_toe'}.issubset(out.columns):
        # §2.2: pasadura uses the RESOLVED per-row bench height (provenance),
        # never a silent 15 m constant.
        pasadura_raw = pd.to_numeric(_pasadura(out, bench_h), errors='coerce')
        valid_pas = pasadura_raw.notna() & (pasadura_raw >= 0) & np.isfinite(pasadura_raw)
        pasadura_valid = valid_pas.fillna(False)
        height_net = height_real - pasadura_raw.where(pasadura_valid, 0.0).fillna(0.0)
    # §2.2: when the bench height is blocked (NaN), height_net stays blocked —
    # no silent "pasadura=0" pass-through.
    height_net = height_net.where(bench_h.notna())
    height_net = height_net.where(height_net > 0, np.nan)
    out['height_net_m'] = height_net

    denom_gt_net = burden_est * esp_est * height_net * rho_rock
    pf_gt_net = np.where(denom_gt_net > 0, (kilos * 1000.0) / denom_gt_net, np.nan)
    out['pf_g_per_ton_net'] = pd.Series(pf_gt_net, index=out.index)

    if 'Tipo_Explosivo' in out.columns:
        mj_per_kg = out['Tipo_Explosivo'].apply(EXPLOSIVE.energy_mj_per_kg)
    else:
        mj_per_kg = pd.Series([None] * len(out), index=out.index, dtype=object)
    # Unknown products resolve to None (spec §4.4) → NaN energy, never ANFO.
    mj_per_kg = pd.to_numeric(mj_per_kg, errors='coerce')
    out['energy_mj'] = kilos * mj_per_kg

    out = enrich_blast_dataframe(out)

    return out


def attribute_failure_to_holes(
    comp_row: dict,
    df_pozos: pd.DataFrame,
    section,
    tolerancia_z: float = 2.0,
) -> Optional[dict]:
    """Identifica los pozos de tronadura que afectaron un banco específico.

    Filtra los pozos proyectados en la sección cuyo ``Z_toe`` cae dentro del
    rango de elevación del banco (incluida la tolerancia vertical) y cuyo
    ``dist_along`` cae entre la cresta y el pie del banco. Devuelve ``None``
    cuando no hay datos de pozos o el banco real no existe.
    """
    # Importación local para evitar dependencias circulares en consumidores que
    # cargan correlación y cálculo de tronadura durante la inicialización.
    from core.calculo_tronadura import proyectar_pozos_en_seccion

    if (
        not isinstance(comp_row, dict)
        or df_pozos is None
        or not isinstance(df_pozos, pd.DataFrame)
        or df_pozos.empty
        or section is None
    ):
        return None

    bench_real = comp_row.get("bench_real")
    if bench_real is None:
        return None

    try:
        section_name = str(comp_row["section"])
        crest_elevation = float(bench_real.crest_elevation)
        toe_elevation = float(bench_real.toe_elevation)
        crest_distance = float(bench_real.crest_distance)
        toe_distance = float(bench_real.toe_distance)
        bench_num = int(bench_real.bench_number)
        tolerance = abs(float(tolerancia_z))
    except (KeyError, AttributeError, TypeError, ValueError):
        return None

    if not all(math.isfinite(value) for value in (
        crest_elevation,
        toe_elevation,
        crest_distance,
        toe_distance,
        tolerance,
    )):
        return None

    projected = proyectar_pozos_en_seccion(
        df_pozos,
        origin=getattr(section, "origin"),
        azimuth=float(getattr(section, "azimuth", 0.0)),
        length=float(getattr(section, "length", 200.0)),
    )

    z_min = min(crest_elevation, toe_elevation) - tolerance
    z_max = max(crest_elevation, toe_elevation) + tolerance
    distance_min = min(crest_distance, toe_distance) - tolerance
    distance_max = max(crest_distance, toe_distance) + tolerance

    if projected.empty or "Z_toe" not in projected or "dist_along" not in projected:
        affected = projected.iloc[0:0].copy()
    else:
        z_toe = pd.to_numeric(projected["Z_toe"], errors="coerce")
        dist_along = pd.to_numeric(projected["dist_along"], errors="coerce")
        affected = projected.loc[
            z_toe.between(z_min, z_max, inclusive="both")
            & dist_along.between(distance_min, distance_max, inclusive="both")
        ].copy()

    if affected.empty:
        return {
            "section_name": section_name,
            "bench_num": bench_num,
            "n_holes": 0,
            "holes": [],
            "pf_avg": 0.0,
            "stemming_ratio_avg": 0.0,
            "burden_avg": 0.0,
            "spacing_avg": 0.0,
            "subdrill_avg": 0.0,
            "kg_total": 0.0,
            "kg_per_meter_avg": 0.0,
        }

    bench_height = getattr(bench_real, "bench_height", None)
    try:
        bench_height = float(bench_height)
    except (TypeError, ValueError):
        bench_height = abs(crest_elevation - toe_elevation)
    if not math.isfinite(bench_height) or bench_height <= 0:
        bench_height = abs(crest_elevation - toe_elevation)

    enriched = compute_powder_factor(
        affected,
        height_fallback_m=bench_height if bench_height > 0 else None,
    )

    def _numeric_value(row: pd.Series, candidates) -> Optional[float]:
        for column in candidates:
            if column not in row.index:
                continue
            try:
                value = float(row[column])
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                return value
        return None

    def _identifier_value(value):
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        return value.item() if isinstance(value, np.generic) else value

    kg_col = kilos_column(enriched)
    holes: List[dict] = []
    for _, row in enriched.iterrows():
        hole: dict = {}
        for identifier in ("uniqid", "id_pozo"):
            if identifier in row.index:
                value = _identifier_value(row[identifier])
                if value is not None:
                    hole[identifier] = value

        pf = _numeric_value(row, ("PF", "pf_vol_kgm3"))
        burden = _numeric_value(
            row, ("burden", "Burden", "Burden_Real", "burden_est_m")
        )
        spacing = _numeric_value(
            row, ("spacing", "Esp", "Espaciamiento", "esp_est_m")
        )
        subdrill = _numeric_value(row, ("subdrill", "pasadura", "Pasadura"))
        if subdrill is None:
            z_collar = _numeric_value(row, ("Z_collar",))
            z_toe_value = _numeric_value(row, ("Z_toe",))
            if z_collar is not None and z_toe_value is not None and bench_height > 0:
                subdrill = (z_collar - bench_height) - z_toe_value

        hole.update({
            "PF": pf,
            "stemming_ratio": _numeric_value(row, ("stemming_ratio",)),
            "burden": burden,
            "spacing": spacing,
            "subdrill": subdrill,
            "kg_per_meter": _numeric_value(row, ("kg_per_meter",)),
            "X": _numeric_value(row, ("X",)),
            "Y": _numeric_value(row, ("Y",)),
            "Z_collar": _numeric_value(row, ("Z_collar",)),
            "Z_toe": _numeric_value(row, ("Z_toe",)),
        })
        holes.append(hole)

    def _average(key: str) -> float:
        values = [hole[key] for hole in holes if hole.get(key) is not None]
        return float(sum(values) / len(values)) if values else 0.0

    if kg_col:
        kg_total = float(
            pd.to_numeric(enriched[kg_col], errors="coerce").fillna(0.0).sum()
        )
    else:
        kg_total = 0.0

    return {
        "section_name": section_name,
        "bench_num": bench_num,
        "n_holes": len(holes),
        "holes": holes,
        "pf_avg": _average("PF"),
        "stemming_ratio_avg": _average("stemming_ratio"),
        "burden_avg": _average("burden"),
        "spacing_avg": _average("spacing"),
        "subdrill_avg": _average("subdrill"),
        "kg_total": kg_total,
        "kg_per_meter_avg": _average("kg_per_meter"),
    }


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
        pf_g_per_ton_inf_avg: float or NaN (g/ton, mean, Voronoi influence area)
        pf_g_per_ton_inf_weighted: float or NaN (g/ton, weighted by Kilos)
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
        "pf_g_per_ton_inf_avg": np.nan,
        "pf_g_per_ton_inf_weighted": np.nan,
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

    pf_inf = pd.to_numeric(pf_enriched.get('pf_g_per_ton_inf'), errors='coerce') if 'pf_g_per_ton_inf' in pf_enriched else pd.Series(dtype=float)
    valid_inf = pf_inf.dropna()
    out["pf_g_per_ton_inf_avg"] = float(valid_inf.mean()) if not valid_inf.empty else float('nan')

    if kg_col and not valid_inf.empty:
        weights_inf = pf_enriched.loc[valid_inf.index, kg_col].fillna(0)
        wsum_inf = float(weights_inf.sum())
        if wsum_inf > 0:
            out["pf_g_per_ton_inf_weighted"] = float(
                (valid_inf * weights_inf).sum() / wsum_inf
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


def _pasadura(df: pd.DataFrame, bench_height) -> pd.Series:
    """Sub-drill depth (m): collar minus bench floor minus toe.

    ``bench_height`` may be a float (event value) or a per-row Series
    (resolved with provenance, §2.2); NaN heights propagate as NaN.
    """
    return (df["Z_collar"] - bench_height) - df["Z_toe"]


def compute_pasadura_stats(
    df_pozos: pd.DataFrame,
    bench_height_m: Optional[float] = None,
) -> dict:
    """Aggregate sub-drill statistics for a blast-hole DataFrame.

    Cierre final §2.1: the bench height is NEVER a default — it comes
    from the event column ``bench_height_m`` (per-row), from the
    caller-provided ``bench_height_m``, or the stats are returned as
    blocked (mean NaN + ``bench_height_status``) when missing.

    Returns a dict with keys: total, mean, optimal_count, optimal_pct,
    bench_height_status, bench_height_validation_message.
    """
    if df_pozos is None or df_pozos.empty:
        return {"total": 0, "mean": 0.0, "optimal_count": 0, "optimal_pct": 0.0,
                "bench_height_status": "MISSING", "bench_height_validation_message": ""}

    if "bench_height_m" in df_pozos.columns:
        bh = pd.to_numeric(df_pozos["bench_height_m"], errors="coerce").where(
            pd.to_numeric(df_pozos["bench_height_m"], errors="coerce") > 0
        )
        status = "PROVIDED" if bh.notna().any() else "INVALID"
    elif bench_height_m is not None and float(bench_height_m) > 0:
        bh = float(bench_height_m)
        status = "PROVIDED"
    else:
        bh = np.nan
        status = "MISSING"

    pas = _pasadura(df_pozos, bh)
    lo, hi = DEFAULTS.blast_correlation_pasadura_optimal
    optimal = int(((pas >= lo) & (pas <= hi)).sum())
    total = len(df_pozos)
    message = (
        "Altura de banco no confirmada: pasadura bloqueada (sin supuesto automático)."
        if status in ("MISSING", "INVALID") else ""
    )
    return {
        "total": total,
        "mean": float(pas.mean()) if total else 0.0,
        "optimal_count": optimal,
        "optimal_pct": (optimal / total * 100.0) if total else 0.0,
        "bench_height_status": status,
        "bench_height_validation_message": message,
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
                "pf_g_per_ton_inf_avg": float('nan'),
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
                pf_g_per_ton_inf_avg=_coerce_finite(pf_agg.get("pf_g_per_ton_inf_avg")),
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
    "attribute_failure_to_holes",
    "classify_berm_as_ramp",
    "compute_blast_geotech_correlation",
    "compute_monthly_trend",
    "compute_powder_factor",
    "compute_signed_deviations",
    "detect_pf_outliers_iqr",
    "split_campaign",
]


def attribute_failure_to_holes(
    comp_row: dict,
    df_pozos: Any,
    section: Any,
    tolerancia_z: float = 2.0,
) -> Optional[dict]:
    """Identifica los pozos de tronadura que afectaron un banco específico.

    Filtra los pozos proyectados en la sección cuyo Z_toe cae dentro del
    rango de elevación del banco [crest_elevation - tol, toe_elevation + tol]
    y cuyo dist_along cae dentro de [crest_distance, toe_distance].

    Returns None si no hay datos de pozos o el banco no existe.
    """
    if df_pozos is None or len(df_pozos) == 0:
        return None

    bt = comp_row.get("bench_real")
    if bt is None:
        return None

    crest_e = float(bt.crest_elevation)
    toe_e = float(bt.toe_elevation)
    crest_d = float(bt.crest_distance)
    toe_d = float(bt.toe_distance)

    # Proyectar pozos a la sección
    try:
        df_proj = proyectar_pozos_en_seccion(df_pozos, section)
    except Exception:
        return None

    if df_proj is None or len(df_proj) == 0:
        return None

    # Filtrar pozos que caen dentro del banco (elevación + horizontal)
    z_lo = max(crest_e, toe_e) + tolerancia_z
    z_hi = min(crest_e, toe_e) - tolerancia_z
    d_lo = min(crest_d, toe_d) - tolerancia_z
    d_hi = max(crest_d, toe_d) + tolerancia_z

    has_z = "Z_toe" in df_proj.columns
    has_dist = "dist_along" in df_proj.columns

    mask = pd.Series(True, index=df_proj.index)
    if has_z:
        mask &= (df_proj["Z_toe"] <= z_lo) & (df_proj["Z_toe"] >= z_hi)
    if has_dist:
        mask &= (df_proj["dist_along"] >= d_lo) & (df_proj["dist_along"] <= d_hi)

    matched = df_proj[mask]
    if len(matched) == 0:
        return {
            "section_name": comp_row.get("section", ""),
            "bench_num": comp_row.get("bench_num", 0),
            "n_holes": 0,
            "holes": [],
            "pf_avg": 0.0,
            "stemming_ratio_avg": 0.0,
            "burden_avg": 0.0,
            "spacing_avg": 0.0,
            "subdrill_avg": 0.0,
            "kg_total": 0.0,
            "kg_per_meter_avg": 0.0,
        }

    # Extraer métricas por pozo
    holes = []
    for _, row in matched.iterrows():
        hole = {
            "id": str(row.get("uniqid", row.get("id_pozo", "?"))),
            "pf": float(row.get("pf_vol_kgm3", 0.0) or 0.0),
            "stemming_ratio": float(row.get("stemming_ratio", 0.0) or 0.0),
            "burden": float(row.get("Burden", row.get("burden_est_m", 0.0)) or 0.0),
            "spacing": float(row.get("Esp", row.get("esp_est_m", 0.0)) or 0.0),
            "subdrill": float(row.get("subdrilling_ratio", 0.0) or 0.0),
            "kg_per_meter": float(row.get("kg_per_meter", 0.0) or 0.0),
            "x": float(row.get("X", 0.0) or 0.0),
            "y": float(row.get("Y", 0.0) or 0.0),
            "z_collar": float(row.get("Z_collar", 0.0) or 0.0),
            "z_toe": float(row.get("Z_toe", 0.0) or 0.0),
        }
        holes.append(hole)

    # Agregados
    def _avg(key):
        vals = [h[key] for h in holes if h[key] != 0.0]
        return sum(vals) / len(vals) if vals else 0.0

    kg_col = kilos_column(matched) if hasattr(matched, 'columns') else None
    kg_total = float(matched[kg_col].sum()) if kg_col and kg_col in matched.columns else 0.0

    return {
        "section_name": comp_row.get("section", ""),
        "bench_num": comp_row.get("bench_num", 0),
        "n_holes": len(holes),
        "holes": holes,
        "pf_avg": _avg("pf"),
        "stemming_ratio_avg": _avg("stemming_ratio"),
        "burden_avg": _avg("burden"),
        "spacing_avg": _avg("spacing"),
        "subdrill_avg": _avg("subdrill"),
        "kg_total": kg_total,
        "kg_per_meter_avg": _avg("kg_per_meter"),
    }
