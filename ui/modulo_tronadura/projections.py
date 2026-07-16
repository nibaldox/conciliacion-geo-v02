"""Pure geometric projection helpers for tronadura views."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.blast_correlation import compute_powder_factor
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.profile_compliance import compute_sector_deviations
from core.section_cutter import cut_both_surfaces
from ui.blast_analysis import project_powder_factor_per_section
from ui.tabs.export import _get_profile_pair


def get_profile_pair_or_cut(
    section_name: str,
    sections: list,
    mesh_design,
    mesh_topo,
):
    """Return the cached (design, topo) profile pair or cut them on demand."""
    pd_prof, pt_prof = _get_profile_pair(section_name)
    if (pd_prof is None or pt_prof is None) and mesh_design is not None and mesh_topo is not None:
        target = next((s for s in sections if s.name == section_name), None)
        if target is not None:
            pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, target)
    return pd_prof, pt_prof


def compute_sector_deviation_data(
    pd_prof,
    pt_prof,
    tolerance_m: float,
):
    """Sort profiles and compute sector deviations.

    Returns ``(sectors, design_d, design_e, topo_d, topo_e)`` or
    ``(None, ...)`` when profiles are unavailable.
    """
    if (
        pd_prof is None
        or pt_prof is None
        or getattr(pd_prof, "distances", None) is None
        or getattr(pt_prof, "distances", None) is None
        or pd_prof.distances.size < 2
        or pt_prof.distances.size < 2
    ):
        return None, None, None, None, None

    design_d = np.asarray(pd_prof.distances, dtype=float)
    design_e = np.asarray(pd_prof.elevations, dtype=float)
    topo_d = np.asarray(pt_prof.distances, dtype=float)
    topo_e = np.asarray(pt_prof.elevations, dtype=float)

    do = np.argsort(design_d)
    design_d, design_e = design_d[do], design_e[do]
    to = np.argsort(topo_d)
    topo_d, topo_e = topo_d[to], topo_e[to]

    sectors = compute_sector_deviations(
        design_d, design_e, topo_d, topo_e, tolerance_m=tolerance_m
    )
    return sectors, design_d, design_e, topo_d, topo_e


def project_blast_to_sections(
    df_filtered: pd.DataFrame,
    sections: list,
    *,
    kg_col: str | None,
    tolerance: float,
    fecha_corte: str | None = None,
) -> list[dict]:
    """Pure wrapper around the shared per-section PF projector.

    Returns the list of kernel rows used for geotechnical correlation.
    """
    df_filtered_pf = compute_powder_factor(df_filtered)
    return project_powder_factor_per_section(
        df_filtered,
        df_filtered_pf,
        sections,
        kg_col=kg_col,
        tolerance=tolerance,
        fecha_corte=fecha_corte,
    )


def project_holes_onto_section(
    df: pd.DataFrame,
    section,
    tolerance: float,
    fecha_corte: str | None = None,
) -> pd.DataFrame:
    """Project blast holes onto a single section plane."""
    return proyectar_pozos_en_seccion(
        df,
        origin=getattr(section, "origin"),
        azimuth=float(getattr(section, "azimuth", 0.0)),
        length=float(getattr(section, "length", 200.0)),
        tolerance=tolerance,
        fecha_corte=fecha_corte,
    )


def compute_signed_correlations(
    df_corr: pd.DataFrame,
    x_col: str,
    over_y_col: str = "Sobre-excavación_Media_m",
    under_y_col: str = "Deuda/Relleno_Media_m",
) -> tuple[float, float]:
    """Compute Pearson correlations for over/under break vs the chosen x metric."""
    df_corr_with_over = df_corr[df_corr[over_y_col] > 0]
    df_corr_with_under = df_corr[df_corr[under_y_col] < 0]

    r_over = 0.0
    r_under = 0.0

    if len(df_corr_with_over) > 1:
        xs = (
            pd.to_numeric(df_corr_with_over[x_col], errors="coerce")
            .fillna(0)
            .values.astype(float)
        )
        ys = df_corr_with_over[over_y_col].values.astype(float)
        if np.var(xs) > 0 and np.var(ys) > 0:
            r_over = np.corrcoef(xs, ys)[0, 1]

    if len(df_corr_with_under) > 1:
        xs_u = (
            pd.to_numeric(df_corr_with_under[x_col], errors="coerce")
            .fillna(0)
            .values.astype(float)
        )
        ys_u = df_corr_with_under[under_y_col].values.astype(float)
        if np.var(xs_u) > 0 and np.var(ys_u) > 0:
            r_under = np.corrcoef(xs_u, ys_u)[0, 1]

    return r_over, r_under
