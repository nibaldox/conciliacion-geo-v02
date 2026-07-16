"""Pure energy-density-along-profile helpers."""

from typing import Tuple

import numpy as np
import plotly.graph_objects as go

from core.blast_model import compute_energy_density_along_profile
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.config import DEFAULTS
from core.section_cutter import cut_both_surfaces
from ui.tabs.export import _get_profile_pair


def get_profile_for_section(section, mesh_design, mesh_topo):
    """Return the (design, topo) profile pair for a section, computing if needed."""
    pd_prof, pt_prof = _get_profile_pair(section.name)
    if pd_prof is None or pt_prof is None:
        pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, section)
    return pd_prof, pt_prof


def build_energy_density_figure(
    blast_df: pd.DataFrame,
    section,
    mesh_design,
    mesh_topo,
    tolerance: float,
    fecha_corte: str,
) -> Tuple[go.Figure | None, float]:
    """Build the energy-density Plotly figure for a selected section.

    Returns ``(fig, z_sample)``. ``fig`` is ``None`` when the topo profile
    has no data.
    """
    pd_prof, pt_prof = get_profile_for_section(section, mesh_design, mesh_topo)
    if not pt_prof or not pt_prof.distances.size:
        return None, 0.0

    direction = np.array(
        [np.sin(np.radians(section.azimuth)), np.cos(np.radians(section.azimuth))]
    )
    profile_xs = section.origin[0] + pt_prof.distances * direction[0]
    profile_ys = section.origin[1] + pt_prof.distances * direction[1]
    z_sample = float(np.nanmean(pt_prof.elevations)) if pt_prof.elevations.size else 0.0

    proj = proyectar_pozos_en_seccion(
        blast_df,
        origin=section.origin,
        azimuth=section.azimuth,
        length=section.length,
        tolerance=tolerance,
        fecha_corte=fecha_corte,
    )
    local_df = proj if not proj.empty else blast_df

    energy = compute_energy_density_along_profile(
        local_df,
        pt_prof.distances,
        profile_xs,
        profile_ys,
        z_sample=z_sample,
        search_radius=DEFAULTS.blast_correlation_radius_m,
    )

    fig = go.Figure()
    if pd_prof and pd_prof.distances.size:
        fig.add_trace(
            go.Scatter(
                x=pd_prof.distances,
                y=pd_prof.elevations,
                mode="lines",
                line=dict(color="royalblue", width=2),
                name="Diseño",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=pt_prof.distances,
            y=pt_prof.elevations,
            mode="lines",
            line=dict(color="forestgreen", width=2),
            name="Topografía",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pt_prof.distances,
            y=energy,
            mode="lines",
            line=dict(color="crimson", width=2),
            name="Energía IDW (kg/m²)",
            yaxis="y2",
        )
    )
    fig.update_layout(
        title=f"Densidad de Energía (IDW) — {section.name}",
        xaxis_title="Distancia a lo largo de la sección (m)",
        yaxis=dict(title="Elevación (m)", color="forestgreen"),
        yaxis2=dict(
            title="Energía (kg/m²)",
            overlaying="y",
            side="right",
            color="crimson",
        ),
        height=450,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(x=0.01, y=0.99),
    )
    return fig, z_sample


def get_search_radius() -> float:
    return DEFAULTS.blast_correlation_radius_m
