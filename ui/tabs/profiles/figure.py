"""Pure Plotly figure builder for the Profiles tab.

No Streamlit calls. The orchestrator in ``tab.py`` reads session state
and passes the required inputs explicitly.
"""
import numpy as np
import plotly.graph_objects as go

from core.geom_utils import calculate_area_between_profiles
from ui.tabs.profiles.holes import add_blast_holes
from ui.tabs.profiles.spill import add_spill_areas_traces
from ui.tabs.profiles.traces import (
    add_area_traces,
    add_bench_annotations,
    add_reconciled_trace,
    add_sector_areas_traces,
    add_semaphore_traces,
)


def build_profile_figure(
    i,
    section,
    pd_prof,
    pt_prof,
    *,
    show_areas=False,
    show_spill_areas=False,
    show_semaphore=False,
    show_reconciled=False,
    show_pozos=False,
    blast_tolerance=None,
    show_sector_areas=False,
    config=None,
    area_fill_design=None,
    params_topo=None,
    comparison_results=None,
    reconciled_design=None,
    reconciled_topo=None,
    blast_df_clean=None,
    pozos_cache=None,
):
    """Return a complete Plotly figure for a single cross-section.

    All session-state dependencies are passed as explicit parameters so
    this function remains pure and testable.
    """
    if config is None:
        config = {}
    if area_fill_design is None:
        area_fill_design = []
    if params_topo is None:
        params_topo = []
    if comparison_results is None:
        comparison_results = []
    if reconciled_design is None:
        reconciled_design = []
    if reconciled_topo is None:
        reconciled_topo = []

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=pd_prof.distances, y=pd_prof.elevations,
        mode='lines', name='Diseño',
        line=dict(color='royalblue', width=2)))

    if i < len(area_fill_design):
        a_over, a_under, d_i, z_ref_i, z_eval_i = area_fill_design[i]
    else:
        a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)

    if show_sector_areas:
        add_sector_areas_traces(fig, pd_prof, pt_prof, d_i, z_ref_i, z_eval_i, a_over, a_under)
    elif show_areas:
        add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under)

    if show_spill_areas and i < len(params_topo):
        add_spill_areas_traces(fig, params_topo[i].benches, pt_prof)

    sec_name = section.name
    sec_comps = [c for c in comparison_results if c.get('section') == sec_name]
    if sec_comps:
        add_bench_annotations(fig, sec_comps, d_i, z_ref_i, z_eval_i)

    if show_semaphore:
        add_semaphore_traces(fig, pd_prof, pt_prof, config)
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode='lines', name='Topografía Real',
            line=dict(color='forestgreen', width=2),
            showlegend=True))
    else:
        fig.add_trace(go.Scatter(
            x=pt_prof.distances, y=pt_prof.elevations,
            mode='lines', name='Topografía Real',
            line=dict(color='forestgreen', width=2)))

    if show_reconciled and i < len(reconciled_design):
        rd_d, re_d = reconciled_design[i]
        add_reconciled_trace(fig, rd_d, re_d,
                             color='royalblue', label='Conciliado Diseño', dash='dash',
                             showlegend=False)

    if show_reconciled and i < len(reconciled_topo):
        rd_t, re_t = reconciled_topo[i]
        topo_benches = params_topo[i].benches if i < len(params_topo) else None
        add_reconciled_trace(fig, rd_t, re_t,
                             color='#FF7F0E', label='Conciliado As-Built', dash='solid', width=2.5,
                             show_berm_width=True, comparison_results=sec_comps,
                             topo_benches=topo_benches,
                             showlegend=True)

    if i < len(params_topo):
        for bench in params_topo[i].benches:
            fig.add_annotation(
                x=bench.crest_distance, y=bench.crest_elevation,
                text=f"B{bench.bench_number}",
                showarrow=True, arrowhead=2,
                font=dict(size=10, color="red"))
            fig.add_annotation(
                x=bench.toe_distance, y=bench.toe_elevation,
                text=f"Pa{bench.bench_number}",
                showarrow=True, arrowhead=2,
                font=dict(size=9, color="darkred"),
                ax=20, ay=0)

    if show_pozos and blast_tolerance is not None:
        add_blast_holes(fig, section, blast_tolerance, blast_df_clean, cache=pozos_cache)

    all_d = np.concatenate([pd_prof.distances, pt_prof.distances])
    all_z = np.concatenate([pd_prof.elevations, pt_prof.elevations])
    valid_d = all_d[np.isfinite(all_d)]
    valid_z = all_z[np.isfinite(all_z)]

    x_range = None
    z_range = None
    if len(valid_d) > 0 and len(valid_z) > 0:
        xmin, xmax = float(np.min(valid_d)), float(np.max(valid_d))
        zmin, zmax = float(np.min(valid_z)), float(np.max(valid_z))
        x_pad = max((xmax - xmin) * 0.05, 5.0)
        z_pad = max((zmax - zmin) * 0.05, 5.0)
        x_range = [xmin - x_pad, xmax + x_pad]
        z_range = [zmin - z_pad, zmax + z_pad]

    grid_height = config.get('grid_height', 15)
    grid_ref = config.get('grid_ref', 0)

    xaxis_dict = dict(gridcolor='lightgray')
    yaxis_dict = dict(scaleanchor="x", scaleratio=1,
                      dtick=grid_height, tick0=grid_ref, gridcolor='lightgray')

    if x_range is not None:
        xaxis_dict['range'] = x_range
    if z_range is not None:
        yaxis_dict['range'] = z_range

    fig.update_layout(
        title=f"Sección {section.name} — {section.sector}",
        xaxis_title="Distancia (m)", yaxis_title="Elevación (m)",
        height=400,
        yaxis=yaxis_dict,
        xaxis=xaxis_dict,
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
        margin=dict(l=60, r=20, t=40, b=40),
    )
    return fig
