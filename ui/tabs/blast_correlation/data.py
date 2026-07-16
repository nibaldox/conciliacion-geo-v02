"""Pure DataFrame compute helpers for blast-geotechnical correlation."""

from typing import Tuple

import numpy as np
import pandas as pd

from core.blast_achievement import compute_design_achievement_score
from core.blast_correlation import (
    aggregate_powder_factor_by_group,
    compute_powder_factor,
    compute_signed_deviations,
)
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.config import DEFAULTS
from core.geom_utils import calculate_area_between_profiles, find_df_column
from core.section_cutter import cut_both_surfaces
from ui.blast_analysis import project_powder_factor_per_section
from ui.tabs.export import _get_profile_pair


KG_COL_CANDIDATES = [
    "Kilos_Cargados_real",
    "Kilos_Cargados",
    "Carga_kg",
    "Explosivo_kg",
]
MALLA_COL_CANDIDATES = [
    "holes_polygon",
    "Nombre_Malla_Original",
    "Malla",
    "Polígono",
]
SECTION_COLUMNS = [
    "section",
    "sector",
    "num_pozos",
    "total_kg",
    "area_over",
    "area_under",
    "avg_over_break",
    "avg_under_break",
    "pf_vol_avg_kgm3",
    "pf_area_avg_kgm2",
    "energy_total_mj",
    "n_pf_valid",
]


def get_kg_col(blast_df: pd.DataFrame) -> str | None:
    return find_df_column(blast_df, KG_COL_CANDIDATES, raise_error=False)


def get_malla_col(blast_df: pd.DataFrame) -> str | None:
    return find_df_column(blast_df, MALLA_COL_CANDIDATES, raise_error=False)


def build_section_cache_keys(
    sections: list,
    blast_df: pd.DataFrame,
    tolerance: float,
    fecha_corte: str | None,
) -> Tuple[tuple, tuple]:
    cut_cache_key = (
        tuple(s.name for s in sections),
        tuple(sorted(blast_df.columns)),
    )
    full_cache_key = (cut_cache_key, tolerance, fecha_corte)
    return cut_cache_key, full_cache_key


def _get_or_cut_profiles(
    sec,
    mesh_design,
    mesh_topo,
    cuts_cache: dict | None,
) -> Tuple[object, object]:
    pd_prof, pt_prof = None, None
    if cuts_cache is not None:
        cut = cuts_cache.get(sec.name)
        if cut:
            pd_prof, pt_prof = cut
    if pd_prof is None or pt_prof is None:
        pd_prof, pt_prof = _get_profile_pair(sec.name)
    if pd_prof is None or pt_prof is None:
        pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sec)
    return pd_prof, pt_prof


def compute_sections_data(
    sections: list,
    mesh_design,
    mesh_topo,
    blast_df: pd.DataFrame,
    comparison_results: list,
    tolerance: float,
    fecha_corte: str | None = None,
    cuts_cache: dict | None = None,
) -> Tuple[pd.DataFrame, dict]:
    """Build the per-section correlation DataFrame and update the cuts cache."""
    if cuts_cache is None:
        cuts_cache = {}

    kg_col = get_kg_col(blast_df)
    pf_enriched = compute_powder_factor(blast_df) if not blast_df.empty else blast_df
    has_pf_input = (
        "Burden" in blast_df.columns
        or "Nombre_Malla_Original" in blast_df.columns
        or "holes_polygon" in blast_df.columns
    )

    data_rows = []
    for sec in sections:
        pd_prof, pt_prof = _get_or_cut_profiles(sec, mesh_design, mesh_topo, cuts_cache)
        if pd_prof is None or pt_prof is None:
            continue
        cuts_cache[sec.name] = (pd_prof, pt_prof)

        a_over, a_under, _, _, _ = calculate_area_between_profiles(pd_prof, pt_prof)

        kernel_rows = project_powder_factor_per_section(
            blast_df,
            pf_enriched,
            [sec],
            kg_col=kg_col,
            tolerance=tolerance,
            fecha_corte=fecha_corte,
        )
        proj_row = kernel_rows[0]
        proj = proj_row["projected_df"]

        signed = compute_signed_deviations(comparison_results or [], sec.name)

        data_rows.append(
            {
                "section": sec.name,
                "sector": sec.sector,
                "num_pozos": proj_row["num_pozos"],
                "total_kg": proj_row["total_kg"],
                "area_over": a_over,
                "area_under": a_under,
                "avg_over_break": signed["avg_over"],
                "avg_under_break": signed["avg_under"],
                "pf_vol_avg_kgm3": proj_row["pf_vol_avg_kgm3"],
                "pf_area_avg_kgm2": proj_row["pf_area_avg_kgm2"],
                "energy_total_mj": proj_row["energy_total_mj"],
                "n_pf_valid": proj_row["n_pf_valid"],
            }
        )

    df = pd.DataFrame(data_rows)
    if df.empty:
        df = pd.DataFrame(columns=SECTION_COLUMNS)

    if "pf_vol_avg_kgm3" in df.columns:
        if df["pf_vol_avg_kgm3"].isna().all() or (df["n_pf_valid"].fillna(0) == 0).all():
            df["_pf_unavailable"] = True
        else:
            df["_pf_unavailable"] = False
    else:
        df["_pf_unavailable"] = True

    if not has_pf_input:
        df["_pf_unavailable"] = True

    return df, cuts_cache


def compute_bench_correlation(
    sections: list,
    blast_df: pd.DataFrame,
    df_comps: pd.DataFrame,
    tolerance: float,
    kg_col: str | None,
    fecha_corte: str | None = None,
) -> pd.DataFrame:
    """Aggregate blast data and deviations per bench / level."""
    if df_comps.empty:
        return pd.DataFrame()

    pf_enriched = compute_powder_factor(blast_df) if not blast_df.empty else blast_df

    bench_stats = []
    unique_levels = df_comps["level"].unique().tolist()
    for lvl in unique_levels:
        df_lvl_comps = df_comps[df_comps["level"] == lvl]

        if "delta_crest" in df_lvl_comps.columns:
            dc = df_lvl_comps["delta_crest"].dropna()
            dev_crest_over_list = dc[dc > 0].tolist()
            dev_crest_under_list = dc[dc < 0].tolist()
        else:
            dev_crest_over_list = []
            dev_crest_under_list = []

        if "delta_toe" in df_lvl_comps.columns:
            dt = df_lvl_comps["delta_toe"].dropna()
            dev_toe_over_list = dt[dt > 0].tolist()
            dev_toe_under_list = dt[dt < 0].tolist()
        else:
            dev_toe_over_list = []
            dev_toe_under_list = []

        avg_dev_crest_over = float(np.mean(dev_crest_over_list)) if dev_crest_over_list else 0.0
        avg_dev_crest_under = float(np.mean(dev_crest_under_list)) if dev_crest_under_list else 0.0
        avg_dev_toe_over = float(np.mean(dev_toe_over_list)) if dev_toe_over_list else 0.0
        avg_dev_toe_under = float(np.mean(dev_toe_under_list)) if dev_toe_under_list else 0.0

        num_pozos = 0
        total_kg = 0.0
        pf_vol_avg = float("nan")
        energy_total = 0.0
        pf_area_avg = float("nan")

        lvl_float = None
        try:
            lvl_float = float(lvl)
        except ValueError:
            pass

        if lvl_float is not None:
            mask_pozos = (blast_df["Z_collar"] - lvl_float).abs() <= DEFAULTS.blast_correlation_radius_m
            pozos_lvl = blast_df[mask_pozos]

            projected_count = 0
            charge_sum = 0.0
            pf_pool = []
            pf_area_pool = []
            energy_sum = 0.0

            for sec in sections:
                proj = proyectar_pozos_en_seccion(
                    pozos_lvl,
                    origin=sec.origin,
                    azimuth=sec.azimuth,
                    length=sec.length,
                    tolerance=tolerance,
                    fecha_corte=fecha_corte,
                )
                if not proj.empty:
                    projected_count += len(proj)
                    if kg_col:
                        charge_sum += proj[kg_col].fillna(0).sum()
                    proj_labeled = proj.copy()
                    proj_labeled["level"] = str(lvl)
                    pf_row = aggregate_powder_factor_by_group(
                        pf_enriched, "level", str(lvl), proj_labeled
                    )
                    pf_val = pf_row.get("pf_vol_avg")
                    if pf_val is not None and not (isinstance(pf_val, float) and np.isnan(pf_val)):
                        pf_pool.append(pf_val)
                    pa_val = pf_row.get("pf_area_avg")
                    if pa_val is not None and not (isinstance(pa_val, float) and np.isnan(pa_val)):
                        pf_area_pool.append(pa_val)
                    energy_sum += pf_row.get("energy_total_mj", 0.0)

            num_pozos = projected_count
            total_kg = charge_sum
            if pf_pool:
                pf_vol_avg = float(np.mean(pf_pool))
            if pf_area_pool:
                pf_area_avg = float(np.mean(pf_area_pool))
            energy_total = energy_sum

        bench_stats.append(
            {
                "level": lvl,
                "num_pozos": num_pozos,
                "total_kg": total_kg,
                "avg_dev_crest_over": avg_dev_crest_over,
                "avg_dev_crest_under": avg_dev_crest_under,
                "avg_dev_toe_over": avg_dev_toe_over,
                "avg_dev_toe_under": avg_dev_toe_under,
                "pf_vol_avg_kgm3": pf_vol_avg,
                "pf_area_avg_kgm2": pf_area_avg,
                "energy_total_mj": energy_total,
            }
        )

    df_b = pd.DataFrame(bench_stats)
    if df_b.empty:
        return df_b

    df_b["sort_level"] = pd.to_numeric(df_b["level"], errors="coerce").fillna(-9999)
    df_b = df_b.sort_values(by="sort_level", ascending=False).reset_index(drop=True)
    return df_b.drop(columns=["sort_level"])


def compute_malla_correlation(
    sections: list,
    blast_df: pd.DataFrame,
    df_sections: pd.DataFrame,
    tolerance: float,
    kg_col: str | None,
    malla_col: str | None,
    comparison_results: list,
    fecha_corte: str | None = None,
) -> Tuple[pd.DataFrame, int]:
    """Aggregate blast data and deviations per malla / polígono."""
    if not malla_col or malla_col not in blast_df.columns:
        return pd.DataFrame(), 0

    mallas = blast_df[malla_col].dropna().unique().tolist()
    pf_enriched = compute_powder_factor(blast_df) if not blast_df.empty else blast_df
    malla_stats = []
    malla_to_section: dict[str, list[str]] = {}

    for mal in mallas:
        df_mal_pozos = blast_df[blast_df[malla_col] == mal]
        total_kg = df_mal_pozos[kg_col].fillna(0).sum() if kg_col else 0.0
        num_pozos = len(df_mal_pozos)

        intersected_sections = []
        pf_pool = []
        energy_sum = 0.0
        for sec in sections:
            proj = proyectar_pozos_en_seccion(
                df_mal_pozos,
                origin=sec.origin,
                azimuth=sec.azimuth,
                length=sec.length,
                tolerance=tolerance,
                fecha_corte=fecha_corte,
            )
            if not proj.empty:
                intersected_sections.append(sec.name)
                proj_labeled = proj.copy()
                proj_labeled["malla"] = str(mal)
                pf_row = aggregate_powder_factor_by_group(
                    pf_enriched, "malla", str(mal), proj_labeled
                )
                pf_val = pf_row.get("pf_vol_avg")
                if pf_val is not None and not (isinstance(pf_val, float) and np.isnan(pf_val)):
                    pf_pool.append(pf_val)
                energy_sum += pf_row.get("energy_total_mj", 0.0)

        malla_to_section[str(mal)] = list(intersected_sections)

        avg_dev_crest_over = 0.0
        avg_dev_crest_under = 0.0
        avg_dev_toe_over = 0.0
        avg_dev_toe_under = 0.0
        avg_overbreak = 0.0

        if intersected_sections:
            df_sec_match = df_sections[df_sections["section"].isin(intersected_sections)]
            if not df_sec_match.empty:
                if "avg_over_break" in df_sec_match.columns:
                    avg_overbreak = df_sec_match["avg_over_break"].mean()
                else:
                    avg_overbreak = df_sec_match["area_over"].mean()

            if comparison_results:
                df_comps = pd.DataFrame(comparison_results)
                df_comps_match = df_comps[df_comps["section"].isin(intersected_sections)]
                if not df_comps_match.empty:
                    if "delta_crest" in df_comps_match.columns:
                        dc = df_comps_match["delta_crest"].dropna()
                        over_c = dc[dc > 0].tolist()
                        under_c = dc[dc < 0].tolist()
                        if over_c:
                            avg_dev_crest_over = float(np.mean(over_c))
                        if under_c:
                            avg_dev_crest_under = float(np.mean(under_c))
                    if "delta_toe" in df_comps_match.columns:
                        dt = df_comps_match["delta_toe"].dropna()
                        over_t = dt[dt > 0].tolist()
                        under_t = dt[dt < 0].tolist()
                        if over_t:
                            avg_dev_toe_over = float(np.mean(over_t))
                        if under_t:
                            avg_dev_toe_under = float(np.mean(under_t))

        pf_vol_avg = float(np.mean(pf_pool)) if pf_pool else float("nan")
        malla_stats.append(
            {
                "malla": str(mal),
                "num_pozos": num_pozos,
                "total_kg": total_kg,
                "avg_dev_crest_over": avg_dev_crest_over,
                "avg_dev_crest_under": avg_dev_crest_under,
                "avg_dev_toe_over": avg_dev_toe_over,
                "avg_dev_toe_under": avg_dev_toe_under,
                "avg_overbreak": avg_overbreak,
                "pf_vol_avg_kgm3": pf_vol_avg,
                "energy_total_mj": energy_sum,
            }
        )

    df_out = pd.DataFrame(malla_stats).reset_index(drop=True)

    if comparison_results and not df_out.empty:
        score = compute_design_achievement_score(
            comparison_results, malla_to_section=malla_to_section
        )
        df_out["score_pct"] = df_out["malla"].map(score.get("per_malla") or {}).fillna(0).astype(int)
        global_score = int(score.get("global", 0))
    else:
        df_out["score_pct"] = 0
        global_score = 0

    return df_out, global_score
