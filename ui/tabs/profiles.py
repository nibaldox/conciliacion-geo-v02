"""
Results tab: cross-section profiles with semaphore, area fill, bench annotations,
and blast-hole overlay.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import build_reconciled_profile
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.geom_utils import calculate_profile_deviation, calculate_area_between_profiles, find_df_column


def render_tab_profiles(config: dict) -> None:
    # 5-column layout for control parameters (compact layout)
    ctrl_cols = st.columns(5)
    
    with ctrl_cols[0]:
        show_reconciled = st.checkbox(
            "Mostrar perfil conciliado",
            value=True, key="show_reconciled",
            help="Muestra la geometría idealizada detectada")
            
    with ctrl_cols[1]:
        show_areas = st.checkbox(
            "Mostrar Áreas",
            value=False, key="show_areas",
            help="Rellena áreas de sobre-excavación y deuda de material")
            
    with ctrl_cols[2]:
        show_semaphore = st.checkbox(
            "Semáforo (Cumplimiento)",
            value=False, key="show_semaphore",
            help="Verde=Cumple, Amarillo=Alerta, Rojo=No Cumple")
            
    with ctrl_cols[3]:
        show_pozos = st.checkbox(
            "Mostrar Pozos de Tronadura",
            value=True, key="show_pozos_profile",
            help="Superpone los pozos de perforación y tronadura")
        blast_tolerance = None
        if show_pozos and st.session_state.get('blast_df_clean') is not None:
            blast_tolerance = st.number_input(
                "Tolerancia pozos (m)",
                value=10.0, min_value=1.0, max_value=50.0, step=1.0,
                key="blast_tol_profile",
                help="Distancia máxima a la línea de sección")
                
    with ctrl_cols[4]:
        num_cols = st.selectbox(
            "Columnas en pantalla",
            [1, 2, 3],
            index=2, # default to 3 columns
            key="profile_grid_cols",
            help="Ajusta el número de columnas para optimizar el espacio")

    display_sections = st.session_state.get('processed_sections', st.session_state.sections)

    # Filter valid sections/profiles first
    valid_plots = []
    for i, section in enumerate(display_sections):
        pd_prof = st.session_state.profiles_design[i]
        pt_prof = st.session_state.profiles_topo[i]

        if pd_prof is None or pt_prof is None:
            st.warning(f"⚠️ Sección {section.name}: sin intersección con una o ambas superficies")
            continue
        valid_plots.append((i, section, pd_prof, pt_prof))

    # Render dynamic grid rows
    for j in range(0, len(valid_plots), num_cols):
        cols = st.columns(num_cols)
        for col_idx in range(num_cols):
            if j + col_idx < len(valid_plots):
                i, section, pd_prof, pt_prof = valid_plots[j + col_idx]
                with cols[col_idx]:
                    fig = _build_profile_figure(
                        i, section, pd_prof, pt_prof,
                        show_areas=show_areas,
                        show_semaphore=show_semaphore,
                        show_reconciled=show_reconciled,
                        show_pozos=show_pozos,
                        blast_tolerance=blast_tolerance,
                        config=config)
                    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_profile_figure(i, section, pd_prof, pt_prof,
                           show_areas, show_semaphore, show_reconciled,
                           show_pozos, blast_tolerance, config):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=pd_prof.distances, y=pd_prof.elevations,
        mode='lines', name='Diseño',
        line=dict(color='royalblue', width=2)))

    a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)

    if show_areas:
        _add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under)

    sec_name = section.name
    sec_comps = [c for c in st.session_state.comparison_results if c['section'] == sec_name]
    if sec_comps:
        _add_bench_annotations(fig, sec_comps, d_i, z_ref_i, z_eval_i)

    if show_semaphore:
        _add_semaphore_traces(fig, pd_prof, pt_prof, config)
    else:
        fig.add_trace(go.Scatter(
            x=pt_prof.distances, y=pt_prof.elevations,
            mode='lines', name='Topografía Real',
            line=dict(color='forestgreen', width=2)))

    if show_reconciled and i < len(st.session_state.params_design):
        _add_reconciled_trace(fig, st.session_state.params_design[i].benches,
                              color='royalblue', label='Conciliado Diseño', dash='dash')

    if show_reconciled and i < len(st.session_state.params_topo):
        _add_reconciled_trace(fig, st.session_state.params_topo[i].benches,
                              color='#FF7F0E', label='Conciliado As-Built', dash='solid', width=2.5,
                              show_berm_width=True, comparison_results=sec_comps)

    if i < len(st.session_state.params_topo):
        for bench in st.session_state.params_topo[i].benches:
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
        _add_blast_holes(fig, section, blast_tolerance)

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


def _add_reconciled_trace(fig, benches, color, label, dash, width=1.5, show_berm_width=False, comparison_results=None):
    rd, re = build_reconciled_profile(benches)
    if len(rd) > 0:
        fig.add_trace(go.Scatter(
            x=rd, y=re, mode='lines+markers', name=label,
            line=dict(color=color, width=width, dash=dash),
            marker=dict(size=5 if width == 1.5 else 6, symbol='diamond', color=color)))
        if show_berm_width and comparison_results is not None:
            _add_berm_width_indicators(fig, benches, comparison_results)


def _add_berm_width_indicators(fig, benches, comparison_results):
    bt_to_design = {}
    for comp in comparison_results:
        if comp.get('type') == 'MATCH':
            bt = comp.get('bench_real')
            bd = comp.get('bench_design')
            if bt is not None and bd is not None:
                bt_to_design[id(bt)] = bd.bench_number

    for j, bench in enumerate(benches):
        bench_id = id(bench)
        if bench_id not in bt_to_design:
            continue
        design_num = bt_to_design[bench_id]
        
        # Use actual berm width from the parameters
        berm = bench.berm_width
        if berm <= 0:
            continue

        if j == 0:
            # Leading berm (before Bench 1, at its crest level)
            x1 = min(bench.toe_distance, bench.crest_distance)
            if bench.toe_distance > bench.crest_distance:
                berm_e = bench.crest_elevation
                x0 = x1 - berm
            else:
                berm_e = bench.toe_elevation
                x0 = x1 - berm
        else:
            # Intermediate berm: connects previous bench to current bench (at previous bench's toe/crest level)
            b_prev = benches[j - 1]
            x0 = max(b_prev.toe_distance, b_prev.crest_distance)
            x1 = min(bench.toe_distance, bench.crest_distance)
            
            if b_prev.toe_distance > b_prev.crest_distance:
                berm_e = b_prev.toe_elevation
            else:
                berm_e = b_prev.crest_elevation

        mid_x = (x0 + x1) / 2

        fig.add_annotation(
            x=mid_x, y=berm_e,
            text=f"B{design_num}={berm:.1f}m",
            showarrow=False,
            font=dict(size=12, color="darkorange"),
            xanchor='center', yanchor='bottom',
            align='center',
        )
        fig.add_shape(
            type="line",
            x0=x0, y0=berm_e, x1=x1, y1=berm_e,
            line=dict(color="darkorange", width=1.5, dash="dash"),
        )


def _add_blast_holes(fig, section, tolerance: float) -> None:
    df_blast = st.session_state.get('blast_df_clean')
    if df_blast is None or df_blast.empty:
        return

    projected = proyectar_pozos_en_seccion(
        df_blast,
        origin=section.origin,
        azimuth=section.azimuth,
        length=section.length,
        tolerance=tolerance,
    )

    if projected.empty:
        return

    kg_col = find_df_column(projected, ['Kilos_Cargados_real', 'Kilos_Cargados'], raise_error=False)
    malla_col = find_df_column(projected, ['holes_polygon', 'Nombre_Malla_Original'], raise_error=False)
    label_col = find_df_column(projected, ['label_pozo'], raise_error=False)

    x_holes, y_holes = [], []
    texts, colors = [], []

    for _, row in projected.iterrows():
        d_c = row['dist_along']
        d_t = row['dist_along_toe'] if 'dist_along_toe' in row else d_c
        z_c = row['Z_collar']
        z_t = row['Z_toe']

        x_holes.extend([d_c, d_t, None])
        y_holes.extend([z_c, z_t, None])

        label = str(row[label_col]) if label_col else ''
        malla = str(row[malla_col]) if malla_col else ''
        kg = f"{row[kg_col]:.0f} kg" if kg_col and pd.notna(row[kg_col]) else ''
        texts.append(f"{label}<br>{malla}<br>{kg}")

        if kg_col and pd.notna(row[kg_col]):
            colors.append(row[kg_col])
        else:
            colors.append(0)

    fig.add_trace(go.Scatter(
        x=x_holes, y=y_holes,
        mode='lines',
        line=dict(color='rgba(255,100,0,0.5)', width=1.5),
        name=f'Pozos ({len(projected)})',
        hoverinfo='skip',
        showlegend=True,
    ))

    collar_x = projected['dist_along'].values
    collar_z = projected['Z_collar'].values

    if kg_col and len(set(colors)) > 1:
        marker = dict(
            size=5,
            color=colors,
            colorscale='Hot',
            showscale=True,
            colorbar=dict(title="kg", x=1.0, len=0.4),
        )
    else:
        marker = dict(size=5, color='darkorange')

    hover_labels = projected.apply(
        lambda r: (
            f"{r[label_col] if label_col else ''}<br>"
            f"{r[malla_col] if malla_col else ''}<br>"
            f"Collar: {r['Z_collar']:.0f}m | Toe: {r['Z_toe']:.0f}m<br>"
            f"Largo: {r['Len']:.1f}m"
            + (f" | {r[kg_col]:.0f}kg" if kg_col and pd.notna(r[kg_col]) else '')
        ), axis=1)

    fig.add_trace(go.Scatter(
        x=collar_x, y=collar_z,
        mode='markers',
        marker=marker,
        name='Collars',
        text=hover_labels,
        hoverinfo='text',
        showlegend=False,
    ))



