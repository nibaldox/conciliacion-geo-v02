"""
Results tab: cross-section profiles with semaphore, area fill, bench annotations,
and blast-hole overlay.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.geom_utils import calculate_profile_deviation, calculate_area_between_profiles, find_df_column
from core.profile_compliance import compute_sector_deviations
from core.stability_analysis import suggest_face_angle_for_fs


BLAST_HOLE_DISPLAY_RADIUS_M = 10.0


def render_tab_profiles(config: dict) -> None:
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
        show_spill_areas = st.checkbox(
            "Mostrar Área de Derrame",
            value=True, key="show_spill_areas",
            help="Muestra el área del material de derrame en la base de los bancos")
        show_sector_areas = st.checkbox(
            "🎯 Sectores coloreados por desviación",
            value=True, key="profile_show_sector_areas",
            help="Rellena el área entre diseño y topografía clasificada por sector: rojo=sobre-excavación, amarillo=deuda, verde=cumple.")
            
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
                value=BLAST_HOLE_DISPLAY_RADIUS_M, min_value=1.0, max_value=50.0, step=1.0,
                key="blast_tol_profile",
                help="Distancia máxima a la línea de sección")
                
    with ctrl_cols[4]:
        num_cols = st.selectbox(
            "Columnas en pantalla",
            [1, 2, 3],
            index=2,
            key="profile_grid_cols",
            help="Ajusta el número de columnas para optimizar el espacio")

    display_sections = st.session_state.get('processed_sections', st.session_state.sections)

    valid_plots = []
    for i, section in enumerate(display_sections):
        pd_prof = st.session_state.profiles_design[i]
        pt_prof = st.session_state.profiles_topo[i]

        if pd_prof is None or pt_prof is None:
            st.warning(f"⚠️ Sección {section.name}: sin intersección con una o ambas superficies")
            continue
        valid_plots.append((i, section, pd_prof, pt_prof))

    fig_cache = st.session_state.setdefault('_profile_figs', {})

    for j in range(0, len(valid_plots), num_cols):
        cols = st.columns(num_cols)
        for col_idx in range(num_cols):
            if j + col_idx < len(valid_plots):
                i, section, pd_prof, pt_prof = valid_plots[j + col_idx]
                cache_key = (
                    i,
                    id(pd_prof), id(pt_prof),
                    id(st.session_state.get('reconciled_design')),
                    id(st.session_state.get('area_fill_design')),
                    show_areas, show_spill_areas, show_semaphore,
                    show_reconciled, show_pozos, blast_tolerance,
                    show_sector_areas,
                    num_cols,
                )
                cached = fig_cache.get(i)
                if cached and cached[0] == cache_key:
                    fig = cached[1]
                else:
                    fig = _build_profile_figure(
                        i, section, pd_prof, pt_prof,
                        show_areas=show_areas,
                        show_spill_areas=show_spill_areas,
                        show_semaphore=show_semaphore,
                        show_reconciled=show_reconciled,
                        show_pozos=show_pozos,
                        blast_tolerance=blast_tolerance,
                        config=config,
                        show_sector_areas=show_sector_areas)
                    fig_cache[i] = (cache_key, fig)
                with cols[col_idx]:
                    st.plotly_chart(fig, width="stretch")
                    if show_sector_areas:
                        with st.expander("🎯 Sugerencia de ángulo de cara (FS objetivo)", expanded=False):
                            col_fs1, col_fs2, col_fs3 = st.columns(3)
                            fs_target = col_fs1.slider("Factor de seguridad objetivo", 1.0, 2.5, 1.3, 0.05, key=f"fs_target_{i}")
                            rmr = col_fs2.number_input("RMR del macizo (0-100)", 0, 100, 60, key=f"fs_rmr_{i}")
                            h = col_fs3.number_input("Altura de banco objetivo (m)", 5, 30, 15, key=f"fs_h_{i}")
                            if st.button(f"Calcular ángulo sugerido para {section.name}", key=f"fs_btn_{i}"):
                                try:
                                    angle = suggest_face_angle_for_fs(
                                        fs_target=fs_target,
                                        rock_mass_rating=rmr if rmr > 0 else None,
                                        bench_height_m=float(h),
                                    )
                                    st.success(f"Ángulo de cara máximo sugerido: **{angle:.1f}°** (FS ≥ {fs_target})")
                                except Exception as e:
                                    st.error(f"No se pudo calcular: {e}")


def _build_profile_figure(i, section, pd_prof, pt_prof,
                           show_areas, show_spill_areas, show_semaphore, show_reconciled,
                           show_pozos, blast_tolerance, config, show_sector_areas=False):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=pd_prof.distances, y=pd_prof.elevations,
        mode='lines', name='Diseño',
        line=dict(color='royalblue', width=2)))

    area_fill_design = st.session_state.get('area_fill_design') or []
    if i < len(area_fill_design):
        a_over, a_under, d_i, z_ref_i, z_eval_i = area_fill_design[i]
    else:
        a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)

    if show_sector_areas:
        _add_sector_areas_traces(fig, pd_prof, pt_prof, d_i, z_ref_i, z_eval_i, a_over, a_under)
    elif show_areas:
        _add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under)

    if show_spill_areas and i < len(st.session_state.params_topo):
        _add_spill_areas_traces(fig, st.session_state.params_topo[i].benches, pt_prof)

    sec_name = section.name
    sec_comps = [c for c in st.session_state.comparison_results if c['section'] == sec_name]
    if sec_comps:
        _add_bench_annotations(fig, sec_comps, d_i, z_ref_i, z_eval_i)

    if show_semaphore:
        _add_semaphore_traces(fig, pd_prof, pt_prof, config)
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

    reconciled_design = st.session_state.get('reconciled_design') or []
    if show_reconciled and i < len(reconciled_design):
        rd_d, re_d = reconciled_design[i]
        _add_reconciled_trace(fig, rd_d, re_d,
                               color='royalblue', label='Conciliado Diseño', dash='dash',
                               showlegend=False)

    reconciled_topo = st.session_state.get('reconciled_topo') or []
    if show_reconciled and i < len(reconciled_topo):
        rd_t, re_t = reconciled_topo[i]
        _add_reconciled_trace(fig, rd_t, re_t,
                               color='#FF7F0E', label='Conciliado As-Built', dash='solid', width=2.5,
                               show_berm_width=True, comparison_results=sec_comps,
                               topo_benches=st.session_state.params_topo[i].benches
                               if i < len(st.session_state.params_topo) else None,
                               showlegend=True)

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

    # Calculate default zoom range centered on the profiles
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

    grid_height = config['grid_height']
    grid_ref = config['grid_ref']
    
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


SECTOR_AREA_COLORS = {
    "overbreak": "rgba(220, 50, 50, 0.45)",
    "underbreak": "rgba(255, 200, 50, 0.45)",
    "compliant": "rgba(80, 200, 120, 0.35)",
    "mixed": "rgba(180, 80, 180, 0.45)",
}

_SECTOR_AREA_HOVERTEMPLATE = (
    "<b>Sector %{customdata[0]}</b><br>"
    "Clase: %{customdata[1]}<br>"
    "Rango: [%{customdata[2]:.1f}, %{customdata[3]:.1f}] m<br>"
    "Δh medio: %{customdata[4]:+.2f} m<br>"
    "Δh máx: %{customdata[5]:+.2f} m<br>"
    "Área sobre: %{customdata[6]:.2f} m²<br>"
    "Área deuda: %{customdata[7]:.2f} m²<br>"
    "<extra></extra>"
)


def _add_sector_areas_traces(fig, pd_prof, pt_prof, d_i, z_ref_i, z_eval_i, a_over, a_under):
    try:
        design_d = np.asarray(pd_prof.distances, dtype=float)
        design_e = np.asarray(pd_prof.elevations, dtype=float)
        topo_d = np.asarray(pt_prof.distances, dtype=float)
        topo_e = np.asarray(pt_prof.elevations, dtype=float)
        sectors = compute_sector_deviations(design_d, design_e, topo_d, topo_e)
    except Exception:
        sectors = []

    if not sectors:
        _add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under)
        return

    do = np.argsort(design_d)
    design_d, design_e = design_d[do], design_e[do]
    to = np.argsort(topo_d)
    topo_d, topo_e = topo_d[to], topo_e[to]

    customdata = np.empty((len(sectors), 8), dtype=object)
    for k, s in enumerate(sectors):
        customdata[k] = [
            s.sector_id, s.classification, s.d_start, s.d_end,
            s.mean_delta_h, s.max_delta_h, s.area_above_m2, s.area_below_m2,
        ]

    for k, s in enumerate(sectors):
        mask = (topo_d >= s.d_start) & (topo_d <= s.d_end)
        if not np.any(mask):
            continue
        d_clip = topo_d[mask]
        e_design_clip = np.interp(d_clip, design_d, design_e)
        e_topo_clip = topo_e[mask]
        trace_customdata = np.tile(customdata[k], (2 * len(d_clip), 1))
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_clip, d_clip[::-1]]),
            y=np.concatenate([e_design_clip, e_topo_clip[::-1]]),
            fill="toself",
            fillcolor=SECTOR_AREA_COLORS.get(s.classification, SECTOR_AREA_COLORS["compliant"]),
            line=dict(width=0),
            hoveron="fills",
            hovertemplate=_SECTOR_AREA_HOVERTEMPLATE,
            customdata=trace_customdata,
            name=f"Sector {s.sector_id} ({s.classification})",
            showlegend=False,
        ))


def _add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under):
    mask_u = z_eval_i >= z_ref_i
    if np.any(mask_u):
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_i[mask_u], d_i[mask_u][::-1]]),
            y=np.concatenate([z_eval_i[mask_u], z_ref_i[mask_u][::-1]]),
            fill='toself', fillcolor='rgba(0,0,255,0.3)',
            line=dict(width=0), name=f'Deuda ({a_under:.1f} m²)', hoverinfo='skip',
            showlegend=False))

    mask_o = z_eval_i < z_ref_i
    if np.any(mask_o):
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_i[mask_o], d_i[mask_o][::-1]]),
            y=np.concatenate([z_eval_i[mask_o], z_ref_i[mask_o][::-1]]),
            fill='toself', fillcolor='rgba(255,0,0,0.3)',
            line=dict(width=0), name=f'Sobre-exc. ({a_over:.1f} m²)', hoverinfo='skip',
            showlegend=False))


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

        bt = comp.get('bench_real')

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

            h_real = bt.bench_height if bt else None
            h_line = f"H.real: {h_real:.2f}m" if h_real is not None else "H.real: N/A"
            face_angle_real = bt.face_angle if bt else None
            face_line = f"Cara: {face_angle_real:.1f}°" if face_angle_real is not None else "Cara: N/A"

            hover_x.append(bd.crest_distance)
            hover_y.append(bd.crest_elevation)
            hover_text.append(
                f"<b>Cota {bd.toe_elevation:.0f}</b> {b_status}<br>"
                f"ΔCr: <span style='color:{c_crest}'>{txt_crest}</span><br>"
                f"ΔPa: <span style='color:{c_toe}'>{txt_toe}</span><br>"
                f"<b>{face_line}</b><br>"
                f"<b>{h_line}</b>")
            hover_colors.append(color_s)
            hover_symbols.append("circle")

    if hover_x:
        fig.add_trace(go.Scatter(
            x=hover_x, y=hover_y, mode='markers', name='Info Bancos',
            marker=dict(color=hover_colors, symbol=hover_symbols, size=10,
                        line=dict(color='black', width=1)),
            text=hover_text, hoverinfo='text',
            hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.55)", bordercolor="rgba(255,255,255,0.3)",
                             font=dict(color="white"), font_size=13),
            showlegend=False))


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
            marker=dict(color='#006100', size=3),
            showlegend=False))
    if np.any(mask_warn):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_warn], y=pt_prof.elevations[mask_warn],
            mode='markers', name='Alerta',
            marker=dict(color='#FFD700', size=4),
            showlegend=False))
    if np.any(mask_nok):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_nok], y=pt_prof.elevations[mask_nok],
            mode='markers', name='No Cumple',
            marker=dict(color='#FF0000', size=4),
            showlegend=False))


def _add_reconciled_trace(fig, rd, re, color, label, dash, width=1.5, show_berm_width=False, comparison_results=None, topo_benches=None, showlegend=True):
    if len(rd) > 0:
        fig.add_trace(go.Scatter(
            x=rd, y=re, mode='lines+markers', name=label,
            line=dict(color=color, width=width, dash=dash),
            marker=dict(size=5 if width == 1.5 else 6, symbol='diamond', color=color),
            showlegend=showlegend))
        if show_berm_width and comparison_results is not None and topo_benches is not None:
            _add_berm_width_indicators(fig, topo_benches, comparison_results)


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


def _get_or_project_pozos(blast_df, section, tolerance: float):
    cache = st.session_state.setdefault('proyectar_pozos_cache', {})
    key = (id(blast_df), tuple(section.origin), section.azimuth, section.length, tolerance)
    if key not in cache:
        cache[key] = proyectar_pozos_en_seccion(
            blast_df,
            origin=section.origin,
            azimuth=section.azimuth,
            length=section.length,
            tolerance=tolerance,
        )
    return cache[key]


def _add_blast_holes(fig, section, tolerance: float) -> None:
    df_blast = st.session_state.get('blast_df_clean')
    if df_blast is None or df_blast.empty:
        return

    projected = _get_or_project_pozos(df_blast, section, tolerance)

    if projected.empty:
        return

    kg_col = find_df_column(projected, ['Kilos_Cargados_real', 'Kilos_Cargados'], raise_error=False)
    malla_col = find_df_column(projected, ['holes_polygon', 'Nombre_Malla_Original'], raise_error=False)
    label_col = find_df_column(projected, ['label_pozo'], raise_error=False)

    x_holes, y_holes = [], []
    colors = []

    has_toe = "dist_along_toe" in projected.columns
    has_kg = kg_col is not None
    # Use itertuples for ~10x speedup over iterrows on large projected
    # DataFrames (e.g. 1000+ blast holes per section).
    for row in projected.itertuples(index=False):
        d_c = row.dist_along
        d_t = row.dist_along_toe if has_toe else d_c
        z_c = row.Z_collar
        z_t = row.Z_toe

        x_holes.extend([d_c, d_t, None])
        y_holes.extend([z_c, z_t, None])

        if has_kg:
            kg_val = getattr(row, kg_col, None)
            if pd.notna(kg_val):
                colors.append(kg_val)
                continue
        colors.append(0)

    fig.add_trace(go.Scatter(
        x=x_holes, y=y_holes,
        mode='lines',
        line=dict(color='rgba(255,100,0,0.5)', width=1.5),
        name=f'Pozos ({len(projected)})',
        hoverinfo='skip',
        showlegend=False,
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

    n = len(projected)
    empty = pd.Series([''] * n, index=projected.index)
    label_s = projected[label_col].fillna('').astype(str) if label_col else empty
    malla_s = projected[malla_col].fillna('').astype(str) if malla_col else empty
    collar_line = (
        "Collar: " + projected['Z_collar'].round().astype(int).astype(str)
        + "m | Toe: " + projected['Z_toe'].round().astype(int).astype(str) + "m"
    )
    length_line = "Largo: " + projected['Len'].round(1).astype(str) + "m"
    if kg_col:
        kg_vals = pd.to_numeric(projected[kg_col], errors='coerce')
        kg_suffix = " | " + kg_vals.round().astype('Int64').astype(str) + "kg"
        kg_suffix = kg_suffix.where(pd.notna(kg_vals), "")
        length_line = length_line + kg_suffix
    hover_labels = label_s.str.cat([malla_s, collar_line, length_line], sep="<br>")

    fig.add_trace(go.Scatter(
        x=collar_x, y=collar_z,
        mode='markers',
        marker=marker,
        name='Collars',
        text=hover_labels,
        hoverinfo='text',
        showlegend=False,
    ))


def _add_spill_areas_traces(fig, benches, pt_prof):
    legend_added = False
    for bench in benches:
        if bench.spill_width > 0.05 and bench.spill_start_elevation > 0.0:
            if bench.toe_distance > bench.crest_distance:
                toe_observed = bench.toe_distance + bench.spill_width
            else:
                toe_observed = bench.toe_distance - bench.spill_width

            d_min = min(bench.spill_start_distance, toe_observed)
            d_max = max(bench.spill_start_distance, toe_observed)
            mask = (pt_prof.distances >= d_min - 0.01) & (pt_prof.distances <= d_max + 0.01)
            topo_x = pt_prof.distances[mask]
            topo_y = pt_prof.elevations[mask]

            if len(topo_x) > 0:
                topo_pts = np.column_stack((topo_x, topo_y))
                if toe_observed > bench.spill_start_distance:
                    topo_pts = topo_pts[np.argsort(-topo_pts[:, 0])]
                else:
                    topo_pts = topo_pts[np.argsort(topo_pts[:, 0])]

                poly_x = [bench.spill_start_distance, bench.toe_distance, toe_observed] + list(topo_pts[:, 0]) + [bench.spill_start_distance]
                poly_y = [bench.spill_start_elevation, bench.toe_elevation, bench.toe_elevation] + list(topo_pts[:, 1]) + [bench.spill_start_elevation]

                fig.add_trace(go.Scatter(
                    x=poly_x, y=poly_y,
                    fill='toself', fillcolor='rgba(255, 165, 0, 0.4)',
                    line=dict(width=0),
                    name='Derrame',
                    hoverinfo='skip',
                    showlegend=not legend_added
                ))
                legend_added = True



