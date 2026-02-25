"""
Results tab: cross-section profiles with semaphore, area fill, and bench annotations.
"""
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import build_reconciled_profile
from core.geom_utils import calculate_profile_deviation, calculate_area_between_profiles


def render_tab_profiles(config: dict) -> None:
    show_reconciled = st.checkbox(
        "Mostrar perfil conciliado (geometría idealizada detectada)",
        value=True, key="show_reconciled")
    show_areas = st.checkbox(
        "Mostrar Áreas (Sobre-excavación / Deuda)",
        value=False, key="show_areas")
    show_semaphore = st.checkbox(
        "Visualización Semáforo (Verde=Cumple, Amarillo=Alerta, Rojo=No Cumple)",
        value=False, key="show_semaphore")

    display_sections = st.session_state.get('processed_sections', st.session_state.sections)

    for i, section in enumerate(display_sections):
        pd_prof = st.session_state.profiles_design[i]
        pt_prof = st.session_state.profiles_topo[i]

        if pd_prof is None or pt_prof is None:
            st.warning(f"⚠️ Sección {section.name}: sin intersección con una o ambas superficies")
            continue

        fig = _build_profile_figure(
            i, section, pd_prof, pt_prof,
            show_areas=show_areas,
            show_semaphore=show_semaphore,
            show_reconciled=show_reconciled,
            config=config)

        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_profile_figure(i, section, pd_prof, pt_prof,
                           show_areas, show_semaphore, show_reconciled, config):
    fig = go.Figure()

    # Design profile
    fig.add_trace(go.Scatter(
        x=pd_prof.distances, y=pd_prof.elevations,
        mode='lines', name='Diseño',
        line=dict(color='royalblue', width=2)))

    # Compute interpolated arrays (needed for areas and bench annotations)
    a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)

    if show_areas:
        _add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under)

    # Bench annotations
    sec_name = section.name
    sec_comps = [c for c in st.session_state.comparison_results if c['section'] == sec_name]
    if sec_comps:
        _add_bench_annotations(fig, sec_comps, d_i, z_ref_i, z_eval_i)

    # Topo / semaphore
    if show_semaphore:
        _add_semaphore_traces(fig, pd_prof, pt_prof, config)
    else:
        fig.add_trace(go.Scatter(
            x=pt_prof.distances, y=pt_prof.elevations,
            mode='lines', name='Topografía Real',
            line=dict(color='forestgreen', width=2)))

    # Reconciled profiles
    if show_reconciled and i < len(st.session_state.params_design):
        _add_reconciled_trace(fig, st.session_state.params_design[i].benches,
                              color='royalblue', label='Conciliado Diseño', dash='dash')

    if show_reconciled and i < len(st.session_state.params_topo):
        _add_reconciled_trace(fig, st.session_state.params_topo[i].benches,
                              color='#FF7F0E', label='Conciliado As-Built', dash='solid', width=2.5)

    # Bench labels on topo
    if i < len(st.session_state.params_topo):
        for bench in st.session_state.params_topo[i].benches:
            fig.add_annotation(
                x=bench.crest_distance, y=bench.crest_elevation,
                text=f"B{bench.bench_number}",
                showarrow=True, arrowhead=2,
                font=dict(size=10, color="red"))

    grid_height = config['grid_height']
    grid_ref = config['grid_ref']
    fig.update_layout(
        title=f"Sección {section.name} — {section.sector}",
        xaxis_title="Distancia (m)", yaxis_title="Elevación (m)",
        height=400,
        yaxis=dict(scaleanchor="x", scaleratio=1,
                   dtick=grid_height, tick0=grid_ref, gridcolor='lightgray'),
        xaxis=dict(gridcolor='lightgray'),
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
        margin=dict(l=60, r=20, t=40, b=40),
    )
    return fig


def _add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under):
    mask_u = z_eval_i >= z_ref_i
    if np.any(mask_u):
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_i[mask_u], d_i[mask_u][::-1]]),
            y=np.concatenate([z_eval_i[mask_u], z_ref_i[mask_u][::-1]]),
            fill='toself', fillcolor='rgba(0,0,255,0.3)',
            line=dict(width=0), name=f'Deuda ({a_under:.1f} m²)', hoverinfo='skip'))

    mask_o = z_eval_i < z_ref_i
    if np.any(mask_o):
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_i[mask_o], d_i[mask_o][::-1]]),
            y=np.concatenate([z_eval_i[mask_o], z_ref_i[mask_o][::-1]]),
            fill='toself', fillcolor='rgba(255,0,0,0.3)',
            line=dict(width=0), name=f'Sobre-exc. ({a_over:.1f} m²)', hoverinfo='skip'))


def _add_bench_annotations(fig, sec_comps, d_i, z_ref_i, z_eval_i):
    dx = 0.1
    hover_x, hover_y, hover_text, hover_colors, hover_symbols = [], [], [], [], []

    for comp in sec_comps:
        c_type = comp.get('type', 'MATCH')

        if c_type == 'MISSING':
            bd = comp.get('bench_design')
            if bd:
                hover_x.append(bd.crest_distance)
                hover_y.append(bd.crest_elevation)
                hover_text.append(f"<b>Cota {bd.toe_elevation:.0f}</b><br>❌ NO CONSTRUIDO")
                hover_colors.append("red")
                hover_symbols.append("x")
            continue

        if c_type == 'EXTRA':
            bt = comp.get('bench_real')
            if bt:
                hover_x.append(bt.crest_distance)
                hover_y.append(bt.crest_elevation)
                hover_text.append(f"<b>Cota {bt.toe_elevation:.0f}</b><br>⚠️ BANCO ADICIONAL")
                hover_colors.append("orange")
                hover_symbols.append("triangle-up")
            continue

        bd = comp.get('bench_design')
        if not bd:
            continue

        start_dist = bd.toe_distance
        end_dist = bd.crest_distance + bd.berm_width
        idx_start = np.searchsorted(d_i, start_dist)
        idx_end = np.searchsorted(d_i, end_dist)

        if idx_end > idx_start:
            diff_slice = z_eval_i[idx_start:idx_end] - z_ref_i[idx_start:idx_end]
            a_u_b = np.sum(diff_slice[diff_slice > 0]) * dx
            a_o_b = np.sum(np.abs(diff_slice[diff_slice < 0])) * dx

            statuses = [comp.get('height_status'), comp.get('angle_status'), comp.get('berm_status')]
            if "NO CUMPLE" in statuses or "FALTA RAMPA" in statuses:
                b_status, color_s = "❌", "red"
            elif "FUERA DE TOLERANCIA" in statuses or "RAMPA (Desv. Ancho)" in statuses:
                b_status, color_s = "⚠️", "orange"
            else:
                b_status, color_s = "✅", "green"

            d_crest = comp.get('delta_crest')
            d_toe = comp.get('delta_toe')
            txt_crest = f"{d_crest:+.2f}m" if d_crest is not None else "N/A"
            txt_toe = f"{d_toe:+.2f}m" if d_toe is not None else "N/A"
            c_crest = "red" if d_crest and d_crest < -0.5 else "blue" if d_crest and d_crest > 0.5 else "black"
            c_toe = "red" if d_toe and d_toe < -0.5 else "blue" if d_toe and d_toe > 0.5 else "black"

            hover_x.append(bd.crest_distance)
            hover_y.append(bd.crest_elevation)
            hover_text.append(
                f"<b>Cota {bd.toe_elevation:.0f}</b> {b_status}<br>"
                f"ΔCr: <span style='color:{c_crest}'>{txt_crest}</span><br>"
                f"ΔPa: <span style='color:{c_toe}'>{txt_toe}</span>")
            hover_colors.append(color_s)
            hover_symbols.append("circle")

    if hover_x:
        fig.add_trace(go.Scatter(
            x=hover_x, y=hover_y, mode='markers', name='Info Bancos',
            marker=dict(color=hover_colors, symbol=hover_symbols, size=10,
                        line=dict(color='black', width=1)),
            text=hover_text, hoverinfo='text',
            hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.2)", font_size=15)))


def _add_semaphore_traces(fig, pd_prof, pt_prof, config):
    devs = calculate_profile_deviation(pd_prof, pt_prof)
    T = config['tolerances']['bench_height']['pos']

    mask_ok = devs <= T
    mask_warn = (devs > T) & (devs <= 1.5 * T)
    mask_nok = devs > 1.5 * T

    fig.add_trace(go.Scatter(
        x=pt_prof.distances, y=pt_prof.elevations,
        mode='lines', name='Topo (Traza)',
        line=dict(color='gray', width=0.5), showlegend=False))

    if np.any(mask_ok):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_ok], y=pt_prof.elevations[mask_ok],
            mode='markers', name=f'Cumple (<{T}m)',
            marker=dict(color='#006100', size=3)))
    if np.any(mask_warn):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_warn], y=pt_prof.elevations[mask_warn],
            mode='markers', name='Alerta',
            marker=dict(color='#FFD700', size=4)))
    if np.any(mask_nok):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_nok], y=pt_prof.elevations[mask_nok],
            mode='markers', name='No Cumple',
            marker=dict(color='#FF0000', size=4)))


def _add_reconciled_trace(fig, benches, color, label, dash, width=1.5):
    rd, re = build_reconciled_profile(benches)
    if len(rd) > 0:
        fig.add_trace(go.Scatter(
            x=rd, y=re, mode='lines+markers', name=label,
            line=dict(color=color, width=width, dash=dash),
            marker=dict(size=5 if width == 1.5 else 6, symbol='diamond', color=color)))
