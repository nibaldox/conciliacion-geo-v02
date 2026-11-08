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


PF_DEFINITIONS = {
    "pf_vol_kgm3": {"formula": "Q/(B*S*H)", "numerator": "charge_kg", "denominator": "burden*spacing*bench_height", "unit": "kg/m3", "height_source": "bench_height"},
    "pf_area_kgm2": {"formula": "Q/(B*S)", "numerator": "charge_kg", "denominator": "burden*spacing", "unit": "kg/m2", "height_source": "none"},
    "pf_g_per_ton": {"formula": "1000*Q/(B*S*L_vertical*rho)", "numerator": "charge_kg", "denominator": "burden*spacing*vertical_length*density", "unit": "g/t", "height_source": "vertical_hole_length"},
    "pf_g_per_ton_net": {"formula": "1000*Q/(B*S*H_net*rho)", "numerator": "charge_kg", "denominator": "burden*spacing*net_height*density", "unit": "g/t", "height_source": "vertical_length_minus_subdrill"},
    "pf_g_per_ton_inf": {"formula": "1000*Q/(A*L_vertical*rho)", "numerator": "charge_kg", "denominator": "influence_area*vertical_length*density", "unit": "g/t", "height_source": "vertical_hole_length"},
}


def _coerce_finite(value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return np.nan
    return f if math.isfinite(f) else np.nan


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
    avg_over_break: float = np.nan
    avg_under_break: float = np.nan
    n_over: int = 0
    n_under: int = 0
    pf_vol_avg_kgm3: float = np.nan
    pf_area_avg_kgm2: float = np.nan
    pf_g_per_ton_avg: float = np.nan
    pf_g_per_ton_net_avg: float = np.nan
    pf_g_per_ton_inf_avg: float = np.nan
    energy_total_mj: float = np.nan
    n_pf_valid: int = 0
    sector: str = ""
    rock_density_used: float = np.nan
    pf_voronoi_bench_g_per_ton_section: float = np.nan
    n_pf_voronoi_bench_valid: int = 0
    energy_coverage_kg_fraction: float = np.nan
    energy_known_mj: float = np.nan
    n_kg_known: int = 0
    n_kg_missing: int = 0

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

    from scipy.spatial import cKDTree
    coords = df_group[['X', 'Y']].apply(pd.to_numeric, errors='coerce').to_numpy(dtype=float)
    finite = np.isfinite(coords).all(axis=1)
    values = np.full(len(coords), np.nan)
    unique, inverse = np.unique(coords[finite], axis=0, return_inverse=True)
    if len(unique) >= 2:
        distances, _ = cKDTree(unique).query(unique, k=min(k + 1, len(unique)))
        values[finite] = np.median(distances[:, 1:], axis=1)[inverse]
    series = pd.Series(values, index=df_group.index)
    return series.copy(), series.copy()


def estimate_malla_footprints(df: pd.DataFrame, group_col: str, buffer_factor: float = 0.5) -> dict:
    """Estimate buffered convex hulls from unique sites, never an operational boundary."""
    from scipy.spatial import cKDTree
    from shapely.geometry import MultiPoint
    if not np.isfinite(buffer_factor) or buffer_factor < 0:
        raise ValueError("buffer_factor must be finite and nonnegative")
    result = {}
    for name, group in df.groupby(group_col, dropna=False):
        coords = group[['X', 'Y']].apply(pd.to_numeric, errors='coerce').to_numpy(dtype=float)
        coords = np.unique(coords[np.isfinite(coords).all(axis=1)], axis=0)
        hull = MultiPoint(coords).convex_hull
        if len(coords) < 3 or hull.geom_type != 'Polygon' or hull.area <= 0:
            result[name] = {'polygon': None, 'source': 'estimated_hull', 'reason': 'insufficient_noncollinear_sites'}
            continue
        distances, _ = cKDTree(coords).query(coords, k=2)
        polygon = hull.buffer(buffer_factor * float(np.median(distances[:, 1])))
        result[name] = {'polygon': list(polygon.exterior.coords), 'source': 'estimated_hull'}
    return result


_LENGTH_CANDIDATES = ('longitud_real', 'Len', 'Longitud', 'Length', 'Profundidad')
_INCLINATION_CANDIDATES = ('Inclinacion_real', 'Incl', 'Inclinacion', 'Inclination')


def _domain_area_or_nan(rep: pd.DataFrame) -> float:
    if "domain_area_m2" not in rep.columns:
        return np.nan
    values = np.asarray(pd.to_numeric(rep["domain_area_m2"], errors="coerce"), dtype=float)
    finite = values[np.isfinite(values)]
    return float(finite[0]) if finite.size else np.nan


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
    domain = _domain_area_or_nan(rep)
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
    """Calculate labeled secondary factors and the footprint-based primary PF.

    The primary factor uses explicit per-pattern polygons, an event bench
    height and an explicitly supplied session density. Estimated polygons
    are opt-in through ``estimate_malla_footprints``. Missing prerequisites
    produce NaN with a status; existing factor names retain their definitions
    in ``PF_DEFINITIONS``. Negative subdrill is inconsistent with a complete
    bench crossing and blocks net height rather than becoming zero.

    Polygon entries may be coordinate lists or dictionaries with ``polygon``
    and ``source`` keys. The primary area diagnostics are per pattern and
    coincident physical holes share their site cell. Energy is calculated
    per deck when the frozen ``decks`` field is present. Net PF status uses
    precedence: outside footprint, invalid subdrill, missing subdrill,
    invalid net height, missing inputs, then valid.
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

    burden_source = pd.Series('knn_proxy', index=out.index)
    spacing_source = pd.Series('knn_proxy', index=out.index)
    for _, gdf in (groups if group_col else [(None, out)]):
        b, sp = _knn_spacing(gdf)
        design_b = pd.to_numeric(gdf['Burden'], errors='coerce') if 'Burden' in gdf else b * np.nan
        design_s = pd.to_numeric(gdf['Esp'], errors='coerce') if 'Esp' in gdf else sp * np.nan
        design_b = design_b.where(np.isfinite(design_b) & (design_b > 0))
        design_s = design_s.where(np.isfinite(design_s) & (design_s > 0))
        burden_est.loc[gdf.index] = design_b.fillna(b)
        esp_est.loc[gdf.index] = design_s.fillna(sp)
        burden_source.loc[gdf.index] = np.where(design_b.notna(), 'design_column', 'knn_proxy')
        spacing_source.loc[gdf.index] = np.where(design_s.notna(), 'design_column', 'knn_proxy')
    out['burden_source'] = burden_source
    out['spacing_source'] = spacing_source
    out['burden_spacing_source'] = np.where(burden_source == spacing_source, burden_source, 'mixed')

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
        boundary_polygons=(boundary_polygons if boundary_polygons is not None and all(not isinstance(v, dict) for v in boundary_polygons.values()) else None),
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

    rho_rock = _coerce_finite(BLAST.rock_density_tm3 if rock_density_tm3 is None else rock_density_tm3)
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
    height_net = pd.Series(np.nan, index=out.index)
    pasadura_raw = pd.Series(np.nan, index=out.index)
    pasadura_valid = pd.Series(False, index=out.index)
    if {'Z_collar', 'Z_toe'}.issubset(out.columns):
        # §2.2: pasadura uses the RESOLVED per-row bench height (provenance),
        # never a silent 15 m constant.
        pasadura_raw = pd.to_numeric(_pasadura(out, bench_h), errors='coerce')
        valid_pas = pasadura_raw.notna() & (pasadura_raw >= 0) & np.isfinite(pasadura_raw)
        pasadura_valid = valid_pas.fillna(False)
        height_net = (height_real - pasadura_raw).where(pasadura_valid)
    # §2.2: when the bench height is blocked (NaN), height_net stays blocked —
    # no silent "pasadura=0" pass-through.
    height_net = height_net.where(bench_h.notna())
    height_net = height_net.where(height_net > 0, np.nan)
    out['height_net_m'] = height_net

    denom_gt_net = burden_est * esp_est * height_net * rho_rock
    pf_gt_net = np.where(denom_gt_net > 0, (kilos * 1000.0) / denom_gt_net, np.nan)
    out['pf_g_per_ton_net'] = pd.Series(pf_gt_net, index=out.index).where(out['collar_inside_domain'].fillna(False))
    out['pf_g_per_ton_net_status'] = np.where(pasadura_raw < 0, 'INVALID_SUBDRILL', np.where(pasadura_valid, 'VALID', 'MISSING_SUBDRILL'))

    def deck_energy(row):
        decks = row.get('decks') if 'decks' in out.columns else [{'kg': row.get(kg_col), 'explosive': row.get('Tipo_Explosivo')}]
        if not isinstance(decks, list) or not decks:
            return np.nan, np.nan, ['missing decks'], np.nan
        total = 0.0
        known = 0.0
        energy = 0.0
        complete = True
        mass_complete = True
        for deck in decks:
            if not isinstance(deck, dict):
                mass_complete = False
                complete = False
                continue
            mass = _coerce_finite(deck.get('kg'))
            specific = _coerce_finite(EXPLOSIVE.energy_mj_per_kg(deck.get('explosive')))
            if not np.isfinite(mass) or mass < 0:
                mass_complete = False
                complete = False
                continue
            total += mass
            if np.isfinite(specific):
                known += mass
                energy += mass * specific
            else:
                complete = False
        coverage = known / total if total > 0 and mass_complete else np.nan
        return (energy if complete and total > 0 else np.nan, coverage,
                [] if complete else ['unknown explosive or missing deck charge'], energy if known > 0 else np.nan)

    energy_rows = [deck_energy(row) for _, row in out.iterrows()]
    out['energy_mj'] = [x[0] for x in energy_rows]
    out['energy_coverage_kg_fraction'] = [x[1] for x in energy_rows]
    out['energy_warnings'] = [x[2] for x in energy_rows]
    out['energy_known_mj'] = [x[3] for x in energy_rows]

    principal_area = pd.Series(np.nan, index=out.index)
    principal_domain = pd.Series(np.nan, index=out.index)
    principal_assigned = pd.Series(np.nan, index=out.index)
    principal_ok = pd.Series(False, index=out.index)
    principal_inside = pd.Series(False, index=out.index)
    principal_outside = pd.Series(False, index=out.index)
    principal_source = pd.Series('', index=out.index, dtype=object)
    principal_area_status = pd.Series('invalid', index=out.index, dtype=object)
    if boundary_polygons is not None and group_col:
        for name, group in out.groupby(group_col, dropna=False):
            entry = boundary_polygons.get(name, boundary_polygons.get(str(name)))
            if entry is None:
                continue
            polygon = entry.get('polygon') if isinstance(entry, dict) else entry
            source = entry.get('source', 'unspecified') if isinstance(entry, dict) else 'unspecified'
            if polygon is None:
                continue
            principal_source.loc[group.index] = 'footprint:' + str(source)
            rep = compute_influence_area_report(group, boundary_polygon=polygon)
            area = pd.to_numeric(rep['area_m2'], errors='coerce')
            domain = _domain_area_or_nan(rep)
            assigned = area.sum(min_count=1)
            conservation = np.isfinite(domain) and domain > 0 and np.isfinite(assigned) and assigned <= domain * (1 + 1e-9)
            principal_area.loc[group.index] = area
            principal_domain.loc[group.index] = domain
            principal_assigned.loc[group.index] = assigned
            principal_ok.loc[group.index] = conservation
            principal_inside.loc[group.index] = rep['collar_inside_domain'].fillna(False)
            principal_outside.loc[group.index] = rep['collar_domain_status'].isin(['OUTSIDE', 'INVALID_COORDINATES'])
            principal_area_status.loc[group.index] = rep['area_status'].replace('duplicate_shared', 'shared_site')
    if boundary_polygons is not None and group_col:
        out.loc[(principal_source != '') & ~principal_inside, 'pf_g_per_ton_net'] = np.nan
    net_status = pd.Series('VALID', index=out.index)
    net_status.loc[~np.isfinite(out['pf_g_per_ton_net'])] = 'MISSING_INPUTS'
    net_status.loc[pasadura_valid & (height_real - pasadura_raw <= 0)] = 'INVALID_NET_HEIGHT'
    net_status.loc[~pasadura_valid] = 'MISSING_SUBDRILL'
    net_status.loc[pasadura_raw < 0] = 'INVALID_SUBDRILL'
    net_status.loc[out['collar_domain_status'].isin(['OUTSIDE', 'INVALID_COORDINATES']) | principal_outside] = 'OUTSIDE_FOOTPRINT'
    out['pf_g_per_ton_net_status'] = net_status
    out['pf_voronoi_bench_area_m2'] = principal_area
    out['pf_voronoi_bench_area_status'] = principal_area_status
    out['pf_voronoi_bench_domain_area_m2'] = principal_domain
    out['pf_voronoi_bench_assigned_area_m2'] = principal_assigned
    out['pf_voronoi_bench_conservation_ok'] = principal_ok
    status = pd.Series('VALID', index=out.index)
    status.loc[~principal_ok] = 'CONSERVATION_FAILED'
    status.loc[~np.isfinite(principal_area) | (principal_area <= 0)] = 'INVALID_AREA'
    status.loc[principal_outside] = 'OUTSIDE_FOOTPRINT'
    status.loc[~np.isfinite(kilos) | (kilos <= 0)] = 'MISSING_CHARGE'
    if rock_density_tm3 is None or not np.isfinite(rho_rock) or rho_rock <= 0:
        status[:] = 'MISSING_DENSITY'
    height_invalid = ~np.isfinite(bench_h) | (bench_h <= 0) | bh_assumed
    if 'bench_height_user_confirmed' in df_pozos:
        height_invalid |= df_pozos['bench_height_user_confirmed'].eq(False).fillna(True)
    if 'bench_height_assumption_flag' in df_pozos:
        height_invalid |= df_pozos['bench_height_assumption_flag'].eq(True).fillna(False)
    status.loc[height_invalid] = 'MISSING_BENCH_HEIGHT'
    status.loc[principal_source == ''] = 'MISSING_FOOTPRINT'
    out['pf_voronoi_bench_g_per_ton'] = (1000 * kilos / (principal_area * bench_h * rho_rock)).where(status == 'VALID')
    out['pf_voronoi_bench_status'] = status
    out['pf_voronoi_bench_unit'] = 'g/t'
    out['pf_voronoi_bench_source'] = principal_source
    out['pf_voronoi_bench_assumptions'] = [[f'density_tm3={rho_rock}', f'bench_height_m={h}', src] for h, src in zip(bench_h, principal_source)]
    out['pf_voronoi_bench_warnings'] = [[] if x == 'VALID' else [x] for x in status]

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

    Legacy arithmetic means and charge-weighted means are secondary. The
    primary section value is the ratio of total charge to total rock mass,
    restricted to rows with a valid precomputed primary factor. Existing
    full-pattern areas and factors are retained rather than recalculated.

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
        "energy_total_mj": np.nan,
        "energy_known_mj": np.nan,
        "n_kg_known": 0,
        "n_kg_missing": 0,
        "energy_coverage_kg_fraction": np.nan,
        "pf_voronoi_bench_g_per_ton_section": np.nan,
        "n_pf_voronoi_bench_valid": 0,
        "kg_total": np.nan,
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
    masses = pd.to_numeric(sub[kg_col], errors='coerce') if kg_col else pd.Series(np.nan, index=sub.index)
    known_mass = np.isfinite(masses) & (masses >= 0)
    out['n_kg_known'] = int(known_mass.sum())
    out['n_kg_missing'] = int((~known_mass).sum())
    out['kg_total'] = float(masses.sum(min_count=1)) if known_mass.all() else np.nan

    pf_enriched = sub.copy() if "area_influence_m2" in sub.columns else compute_powder_factor(
        sub, rock_density_tm3=rock_density_tm3, height_fallback_m=height_fallback_m,
    )
    if 'area_influence_m2' in sub and rock_density_tm3 is not None:
        rho = _coerce_finite(rock_density_tm3)
        for field, factors in (
            ('pf_g_per_ton', ('burden_est_m', 'esp_est_m', 'height_real_m')),
            ('pf_g_per_ton_net', ('burden_est_m', 'esp_est_m', 'height_net_m')),
            ('pf_g_per_ton_inf', ('area_influence_m2', 'height_real_m')),
            ('pf_voronoi_bench_g_per_ton', ('pf_voronoi_bench_area_m2', 'bench_height_m')),
        ):
            if field not in pf_enriched or not all(f in pf_enriched for f in factors):
                continue
            denom = pd.Series(rho, index=sub.index)
            for factor in factors:
                denom = denom * pd.to_numeric(pf_enriched[factor], errors='coerce')
            if field == 'pf_voronoi_bench_g_per_ton':
                status = pf_enriched.get('pf_voronoi_bench_status', pd.Series('', index=sub.index))
                valid = status.eq('VALID') | (status.eq('MISSING_DENSITY') & pf_enriched.get('pf_voronoi_bench_conservation_ok', pd.Series(False, index=sub.index)).fillna(False))
            else:
                valid = pd.to_numeric(pf_enriched[field], errors='coerce').notna()
            pf_enriched[field] = (1000 * masses / denom).where(valid & np.isfinite(denom) & (denom > 0) & known_mass)
            if field == 'pf_voronoi_bench_g_per_ton':
                pf_enriched.loc[valid & pf_enriched[field].notna(), 'pf_voronoi_bench_status'] = 'VALID'
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

    if 'energy_known_mj' in pf_enriched:
        known_energy = pd.to_numeric(pf_enriched['energy_known_mj'], errors='coerce')
        out['energy_known_mj'] = float(known_energy.sum(min_count=1))
    else:
        out['energy_known_mj'] = float(energy.sum(min_count=1)) if not energy.empty else np.nan
    if kg_col and 'energy_coverage_kg_fraction' in pf_enriched:
        coverage = pd.to_numeric(pf_enriched['energy_coverage_kg_fraction'], errors='coerce')
        if known_mass.all() and (masses >= 0).all() and masses.sum() > 0 and coverage.notna().all():
            out['energy_coverage_kg_fraction'] = float((masses * coverage).sum() / masses.sum())
        if out['energy_coverage_kg_fraction'] == 1 and len(energy) == len(sub) and energy.notna().all():
            out['energy_total_mj'] = float(energy.sum(min_count=1))
    if kg_col and 'pf_voronoi_bench_g_per_ton' in pf_enriched:
        pf = pd.to_numeric(pf_enriched['pf_voronoi_bench_g_per_ton'], errors='coerce')
        masses = pd.to_numeric(pf_enriched[kg_col], errors='coerce')
        valid = np.isfinite(pf) & (pf > 0) & np.isfinite(masses) & (masses > 0)
        if 'pf_voronoi_bench_status' in pf_enriched:
            valid &= pf_enriched['pf_voronoi_bench_status'].eq('VALID')
        out['n_pf_voronoi_bench_valid'] = int(valid.sum())
        if valid.any():
            out['pf_voronoi_bench_g_per_ton_section'] = float(masses[valid].sum() / (masses[valid] / pf[valid]).sum())

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
        k for k in ("delta_crest", "delta_toe")
        if any(k in row and np.isfinite(_coerce_finite(row.get(k))) for row in comparisons)
    ]
    return keys[0] if keys else None


def compute_signed_deviations(comparisons: List[dict], section_name: str) -> dict:
    """Summarize finite horizontal deltas, using toe only without crest data."""
    rows = [c for c in (comparisons or []) if c.get('section') == section_name]
    source = None
    values = []
    for candidate in ('delta_crest', 'delta_toe'):
        values = [_coerce_finite(row.get(candidate)) for row in rows]
        values = [v for v in values if np.isfinite(v)]
        if values:
            source = candidate
            break
    over = [v for v in values if v > 0]
    under = [v for v in values if v < 0]
    return {'avg_over': float(np.mean(over)) if over else np.nan,
            'avg_under': float(np.mean(under)) if under else np.nan,
            'n_over': len(over), 'n_under': len(under), 'source': source}


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
            mean_dev = np.nan

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
                "energy_total_mj": np.nan,
                "n_pf_valid": 0,
            }
        else:
            num_wells = len(proj)
            pf_agg = aggregate_powder_factor_by_group(
                df_pozos, 'section_name', sec_name, proj_labeled,
                rock_density_tm3=sec_rho if sec_rho is not None else (rock_density_tm3 if rock_density_tm3 is not None else BLAST.rock_density_tm3),
                height_fallback_m=height_fallback_m,
            )
            total_kg = pf_agg['kg_total']
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
                energy_known_mj=_coerce_finite(pf_agg.get("energy_known_mj")),
                n_kg_known=int(pf_agg.get("n_kg_known", 0)),
                n_kg_missing=int(pf_agg.get("n_kg_missing", 0)),
                n_pf_valid=int(pf_agg.get("n_pf_valid") or 0),
                pf_voronoi_bench_g_per_ton_section=_coerce_finite(pf_agg.get("pf_voronoi_bench_g_per_ton_section")),
                n_pf_voronoi_bench_valid=int(pf_agg.get("n_pf_voronoi_bench_valid") or 0),
                energy_coverage_kg_fraction=_coerce_finite(pf_agg.get("energy_coverage_kg_fraction")),
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
    if df_pozos is None or len(df_pozos) == 0 or section is None:
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
        df_proj = proyectar_pozos_en_seccion(
            df_pozos,
            origin=getattr(section, "origin", None),
            azimuth=float(getattr(section, "azimuth", 0.0)),
            length=float(getattr(section, "length", 200.0)),
        )
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

    def _num(value: Optional[float]) -> Optional[float]:
        """Coerce a hole metric to a finite float; never invent a zero."""
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    matched = df_proj[mask]
    if len(matched) == 0:
        return {
            "section_name": comp_row.get("section", ""),
            "bench_num": comp_row.get("bench_num", 0),
            "n_holes": 0,
            "holes": [],
            "pf_avg": None,
            "stemming_ratio_avg": None,
            "burden_avg": None,
            "spacing_avg": None,
            "subdrill_avg": None,
            "kg_total": None,
            "kg_per_meter_avg": None,
        }

    # Extraer métricas por pozo
    holes = []
    for _, row in matched.iterrows():
        hole = {
            "id": str(row.get("uniqid", row.get("id_pozo", "?"))),
            "pf": _num(row.get("pf_vol_kgm3")),
            "stemming_ratio": _num(row.get("stemming_ratio")),
            "burden": _num(row.get("Burden", row.get("burden_est_m"))),
            "spacing": _num(row.get("Esp", row.get("esp_est_m"))),
            "subdrill": _num(row.get("subdrilling_ratio")),
            "kg_per_meter": _num(row.get("kg_per_meter")),
            "x": _num(row.get("X")),
            "y": _num(row.get("Y")),
            "z_collar": _num(row.get("Z_collar")),
            "z_toe": _num(row.get("Z_toe")),
        }
        holes.append(hole)

    # Agregados
    def _avg(key):
        vals = [h[key] for h in holes if h[key] is not None and h[key] != 0.0]
        return sum(vals) / len(vals) if vals else None

    kg_col = kilos_column(matched) if hasattr(matched, 'columns') else None
    kg_total = (_num(matched[kg_col].sum(min_count=1))
                if kg_col and kg_col in matched.columns else None)

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
