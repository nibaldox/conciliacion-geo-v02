"""Paso 4: Resultados — Perfiles, tabla, dashboard, AI, export."""
import streamlit as st
import numpy as np
import plotly.graph_objects as go
import os
import tempfile
from datetime import datetime

from core import (
    export_results,
    generate_section_images_zip,
    cut_both_surfaces,
    build_reconciled_profile,
)
from core.geom_utils import calculate_profile_deviation, calculate_area_between_profiles


def render_results_section(config: dict):
    """Render the results UI (5 tabs: profiles, table, dashboard, AI, export).

    Args:
        config: dict with keys ai_enabled, api_key, model_name, base_url,
                tolerances, grid_height, grid_ref, project_info,
                face_threshold, berm_threshold, resolution.
    """
    if st.session_state.step < 4 or not st.session_state.comparison_results:
        return

    st.header("📊 Paso 4: Resultados")

    tab_profiles, tab_table, tab_dash, tab_ai, tab_export = st.tabs([
        "📈 Perfiles", "📋 Tabla Detallada", "📊 Dashboard", "🤖 Analista IA", "💾 Exportar"
    ])

    _render_tab_profiles(tab_profiles, config)
    _render_tab_table(tab_table)
    _render_tab_dashboard(tab_dash, config)
    _render_tab_ai(tab_ai, config)
    _render_tab_export(tab_export, config)


# ──────────────────────────────────────────────────────────────
# Tab: Perfiles
# ──────────────────────────────────────────────────────────────
def _render_tab_profiles(tab, config: dict):
    with tab:
        show_reconciled = st.checkbox(
            "Mostrar perfil conciliado (geometría idealizada detectada)",
            value=True, key="show_reconciled")

        show_areas = st.checkbox(
            "Mostrar Áreas (Sobre-excavación / Deuda)",
            value=False, key="show_areas")

        show_semaphore = st.checkbox(
            "Visualización Semáforo (Verde=Cumple, Amarillo=Alerta, Rojo=No Cumple)",
            value=False, key="show_semaphore")

        grid_height = config['grid_height']
        grid_ref = config['grid_ref']
        tolerances = config['tolerances']

        display_sections = st.session_state.get('processed_sections', st.session_state.sections)

        for i, section in enumerate(display_sections):
            pd_prof = st.session_state.profiles_design[i]
            pt_prof = st.session_state.profiles_topo[i]

            if pd_prof is None or pt_prof is None:
                st.warning(f"⚠️ Sección {section.name}: sin intersección con una o ambas superficies")
                continue

            fig = go.Figure()

            # Design profile
            fig.add_trace(go.Scatter(
                x=pd_prof.distances, y=pd_prof.elevations,
                mode='lines', name='Diseño',
                line=dict(color='royalblue', width=2)))

            # Area Visualization
            area_over, area_under = 0.0, 0.0
            if show_areas:
                a_over, a_under, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)
                area_over, area_under = a_over, a_under

                mask_u = z_eval_i >= z_ref_i
                if np.any(mask_u):
                    fig.add_trace(go.Scatter(
                        x=np.concatenate([d_i[mask_u], d_i[mask_u][::-1]]),
                        y=np.concatenate([z_eval_i[mask_u], z_ref_i[mask_u][::-1]]),
                        fill='toself',
                        fillcolor='rgba(0,0,255,0.3)',
                        line=dict(width=0),
                        name=f'Deuda ({a_under:.1f} m²)',
                        hoverinfo='skip'
                    ))

                mask_o = z_eval_i < z_ref_i
                if np.any(mask_o):
                    fig.add_trace(go.Scatter(
                        x=np.concatenate([d_i[mask_o], d_i[mask_o][::-1]]),
                        y=np.concatenate([z_eval_i[mask_o], z_ref_i[mask_o][::-1]]),
                        fill='toself',
                        fillcolor='rgba(255,0,0,0.3)',
                        line=dict(width=0),
                        name=f'Sobre-exc. ({a_over:.1f} m²)',
                        hoverinfo='skip'
                    ))

            sec_name = section.name
            sec_comps = [c for c in st.session_state.comparison_results if c['section'] == sec_name]

            # --- Per-Bench Metrics Annotation ---
            if sec_comps:
                # Ensure we have interpolated data
                if not show_areas:
                    a_over_full, a_under_full, d_i, z_ref_i, z_eval_i = calculate_area_between_profiles(pd_prof, pt_prof)

                dx = 0.1

                hover_x, hover_y, hover_text = [], [], []
                hover_colors, hover_symbols = [], []

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
                        z_ref_slice = z_ref_i[idx_start:idx_end]
                        z_eval_slice = z_eval_i[idx_start:idx_end]
                        diff_slice = z_eval_slice - z_ref_slice

                        a_u_b = np.sum(diff_slice[diff_slice > 0]) * dx
                        a_o_b = np.sum(np.abs(diff_slice[diff_slice < 0])) * dx

                        statuses = [comp.get('height_status'), comp.get('angle_status'), comp.get('berm_status')]
                        if "NO CUMPLE" in statuses or "FALTA RAMPA" in statuses:
                            color_s = "red"
                        elif "FUERA DE TOLERANCIA" in statuses or "RAMPA (Desv. Ancho)" in statuses:
                            color_s = "orange"
                        else:
                            color_s = "green"

                        d_crest = comp.get('delta_crest')
                        d_toe = comp.get('delta_toe')
                        txt_crest = f"{d_crest:+.2f}m" if d_crest is not None else "N/A"
                        txt_toe = f"{d_toe:+.2f}m" if d_toe is not None else "N/A"

                        c_crest = "red" if d_crest and d_crest < -0.5 else "blue" if d_crest and d_crest > 0.5 else "black"
                        c_toe = "red" if d_toe and d_toe < -0.5 else "blue" if d_toe and d_toe > 0.5 else "black"

                        hover_x.append(bd.crest_distance)
                        hover_y.append(bd.crest_elevation)
                        hover_text.append(
                            f"ΔPa: <span style='color:{c_toe}'>{txt_toe}</span>"
                        )
                        hover_colors.append(color_s)
                        hover_symbols.append("circle")

                if hover_x:
                    fig.add_trace(go.Scatter(
                        x=hover_x, y=hover_y,
                        mode='markers',
                        name='Info Bancos',
                        marker=dict(
                            color=hover_colors,
                            symbol=hover_symbols,
                            size=10,
                            line=dict(color='black', width=1)
                        ),
                        text=hover_text,
                        hoverinfo='text',
                        hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.2)", font_size=15)
                    ))

            # Topo profile (semaphore or normal)
            if show_semaphore and pd_prof is not None:
                devs = calculate_profile_deviation(pd_prof, pt_prof)
                T = tolerances['bench_height']['pos']

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
            else:
                fig.add_trace(go.Scatter(
                    x=pt_prof.distances, y=pt_prof.elevations,
                    mode='lines', name='Topografía Real',
                    line=dict(color='forestgreen', width=2)))

            # Reconciled profiles
            if show_reconciled and i < len(st.session_state.params_design):
                rd, re = build_reconciled_profile(st.session_state.params_design[i].benches)
                if len(rd) > 0:
                    fig.add_trace(go.Scatter(
                        x=rd, y=re, mode='lines+markers',
                        name='Conciliado Diseño',
                        line=dict(color='royalblue', width=1.5, dash='dash'),
                        marker=dict(size=5, symbol='diamond', color='royalblue'),
                    ))

            if show_reconciled and i < len(st.session_state.params_topo):
                rd, re = build_reconciled_profile(st.session_state.params_topo[i].benches)
                if len(rd) > 0:
                    fig.add_trace(go.Scatter(
                        x=rd, y=re, mode='lines+markers',
                        name='Conciliado As-Built',
                        line=dict(color='#FF7F0E', width=2.5, dash='solid'),
                        marker=dict(size=6, symbol='diamond', color='#FF7F0E'),
                    ))

            # Mark detected benches on topo
            if i < len(st.session_state.params_topo):
                for bench in st.session_state.params_topo[i].benches:
                    fig.add_annotation(
                        x=bench.crest_distance, y=bench.crest_elevation,
                        text=f"B{bench.bench_number}",
                        showarrow=True, arrowhead=2,
                        font=dict(size=10, color="red"))

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
            st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────────────
# Tab: Tabla Detallada
# ──────────────────────────────────────────────────────────────
def _render_tab_table(tab):
    with tab:
        import pandas as pd

        if not st.session_state.comparison_results:
            return

        sort_option = st.radio(
            "Orden de la tabla:",
            ["Por Sección (Vertical)", "Por Nivel (Horizontal)"],
            horizontal=True,
            key="table_sort"
        )

        df = pd.DataFrame(st.session_state.comparison_results)

        # --- Filtering ---
        with st.expander("🔎 Filtros (Excel-style)", expanded=False):
            cols_filter = st.columns(4)

            all_sectors = sorted(list(df['sector'].unique()))
            sel_sectors = cols_filter[0].multiselect("Filtrar por Sector:", all_sectors, default=[], key="filter_sector")

            unique_levels = df['level'].unique()
            sorted_levels = sorted(unique_levels, key=lambda x: float(x) if x.replace('.', '', 1).isdigit() else -9999, reverse=True)
            sel_levels = cols_filter[1].multiselect("Filtrar por Nivel (Cota):", sorted_levels, default=[], key="filter_level")

            all_sections = sorted(list(df['section'].unique()))
            sel_sections = cols_filter[2].multiselect("Filtrar por Sección:", all_sections, default=[], key="filter_section")

            all_benches = sorted(list(df['bench_num'].unique()))
            sel_benches = cols_filter[3].multiselect("Filtrar por Banco:", all_benches, default=[], key="filter_bench")

        if sel_sectors:
            df = df[df['sector'].isin(sel_sectors)]
        if sel_levels:
            df = df[df['level'].isin(sel_levels)]
        if sel_sections:
            df = df[df['section'].isin(sel_sections)]
        if sel_benches:
            df = df[df['bench_num'].isin(sel_benches)]

        # Apply sorting
        if "Por Nivel" in sort_option:
            df['sort_level'] = pd.to_numeric(df['level'], errors='coerce').fillna(-9999)
            df = df.sort_values(by=['sort_level', 'section'], ascending=[False, True])
            cols = ['sector', 'level', 'section', 'bench_num'] + [c for c in df.columns if c not in ['sector', 'level', 'section', 'bench_num', 'sort_level', 'sort_bench']]
            df = df[cols]
        else:
            df['sort_level'] = pd.to_numeric(df['level'], errors='coerce').fillna(-9999)
            df = df.sort_values(by=['section', 'sort_level'], ascending=[True, False])
            cols = ['sector', 'section', 'bench_num', 'level'] + [c for c in df.columns if c not in ['sector', 'section', 'bench_num', 'level', 'sort_level', 'sort_bench']]
            df = df[cols]

        display_cols = {
            'sector': 'Sector', 'section': 'Sección', 'bench_num': 'Banco',
            'level': 'Nivel', 'height_design': 'H. Diseño', 'height_real': 'H. Real',
            'height_dev': 'Desv. H', 'height_status': 'Cumpl. H',
            'angle_design': 'Á. Diseño', 'angle_real': 'Á. Real',
            'angle_dev': 'Desv. Á', 'angle_status': 'Cumpl. Á',
            'berm_design': 'B. Diseño', 'berm_real': 'B. Real',
            'berm_min': 'B. Mínima', 'berm_status': 'Cumpl. B',
            'delta_crest': 'Δ Cresta', 'delta_toe': 'Δ Pata'
        }
        df_display = df.rename(columns=display_cols)

        def highlight_status(val):
            val = str(val)
            if val == "CUMPLE" or "RAMPA OK" in val:
                return 'background-color: #C6EFCE; color: #006100'
            elif val == "FUERA DE TOLERANCIA":
                return 'background-color: #FFEB9C; color: #9C5700'
            elif val == "NO CUMPLE" or "FALTA" in val:
                return 'background-color: #FFC7CE; color: #9C0006'
            elif val == "NO CONSTRUIDO":
                return 'background-color: #E0E0E0; color: #555555'
            elif val == "EXTRA" or "ADICIONAL" in val:
                return 'background-color: #E6E6FA; color: #4B0082'
            elif "RAMPA" in val:
                return 'background-color: #E6E6FA; color: #4B0082'
            return ''

        styled = df_display.style.map(highlight_status,
                                       subset=['Cumpl. H', 'Cumpl. Á', 'Cumpl. B'])
        st.dataframe(styled, width="stretch", height=400)


# ──────────────────────────────────────────────────────────────
# Tab: Dashboard
# ──────────────────────────────────────────────────────────────
def _render_tab_dashboard(tab, config: dict):
    with tab:
        results = st.session_state.comparison_results
        if not results:
            return

        import pandas as pd
        df = pd.DataFrame(results)

        # --- Filtering ---
        with st.expander("🔎 Filtros (Excel-style)", expanded=False):
            cols_filter = st.columns(4)

            all_sectors = sorted(df['sector'].unique().tolist())
            sel_sectors = cols_filter[0].multiselect(
                "Filtrar por Sector:", all_sectors, default=[], key="filter_sector_dash")

            unique_levels = df['level'].unique()
            sorted_levels = sorted(
                unique_levels,
                key=lambda x: float(x) if str(x).replace('.', '', 1).isdigit() else -9999,
                reverse=True)
            sel_levels = cols_filter[1].multiselect(
                "Filtrar por Nivel (Cota):", sorted_levels, default=[], key="filter_level_dash")

            all_sections = sorted(df['section'].unique().tolist())
            sel_sections = cols_filter[2].multiselect(
                "Filtrar por Sección:", all_sections, default=[], key="filter_section_dash")

            all_benches = sorted(df['bench_num'].unique().tolist())
            sel_benches = cols_filter[3].multiselect(
                "Filtrar por Banco:", all_benches, default=[], key="filter_bench_dash")

        if sel_sectors:
            df = df[df['sector'].isin(sel_sectors)]
        if sel_levels:
            df = df[df['level'].isin(sel_levels)]
        if sel_sections:
            df = df[df['section'].isin(sel_sections)]
        if sel_benches:
            df = df[df['bench_num'].isin(sel_benches)]

        filtered_results = df.to_dict('records')

        if not filtered_results:
            st.warning("⚠️ No hay resultados que coincidan con los filtros seleccionados.")
            return

        tolerances = config['tolerances']
        min_berm_width = tolerances['berm_width']['min']

        cols = st.columns(3)
        for col, (param, key, label) in zip(cols, [
            ('height', 'height_status', 'Altura de Banco'),
            ('angle', 'angle_status', 'Ángulo de Cara'),
            ('berm', 'berm_status', 'Ancho de Berma'),
        ]):
            total = len(filtered_results)
            cumple = sum(1 for r in filtered_results if r[key] == "CUMPLE")
            pct = cumple / total * 100 if total > 0 else 0
            col.metric(label, f"{pct:.0f}%", f"{cumple}/{total} cumplen")

        status_counts = {'Parámetro': [], 'CUMPLE': [], 'FUERA DE TOLERANCIA': [], 'NO CUMPLE': []}
        for key, label in [('height_status', 'Altura'), ('angle_status', 'Ángulo Cara'), ('berm_status', 'Berma')]:
            status_counts['Parámetro'].append(label)
            status_counts['CUMPLE'].append(sum(1 for r in filtered_results if r[key] == "CUMPLE"))
            status_counts['FUERA DE TOLERANCIA'].append(sum(1 for r in filtered_results if r[key] == "FUERA DE TOLERANCIA"))
            status_counts['NO CUMPLE'].append(sum(1 for r in filtered_results if r[key] == "NO CUMPLE"))

        df_status = pd.DataFrame(status_counts)
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(name='CUMPLE', x=df_status['Parámetro'], y=df_status['CUMPLE'],
                                 marker_color='#006100'))
        fig_bar.add_trace(go.Bar(name='FUERA TOL.', x=df_status['Parámetro'], y=df_status['FUERA DE TOLERANCIA'],
                                 marker_color='#9C5700'))
        fig_bar.add_trace(go.Bar(name='NO CUMPLE', x=df_status['Parámetro'], y=df_status['NO CUMPLE'],
                                 marker_color='#9C0006'))
        fig_bar.update_layout(barmode='stack', title="Cumplimiento por Parámetro",
                              height=350, margin=dict(l=40, r=20, t=40, b=40))
        st.plotly_chart(fig_bar, use_container_width=True)

        tol_h_neg = tolerances['bench_height']['neg']
        tol_h_pos = tolerances['bench_height']['pos']
        tol_a_neg = tolerances['face_angle']['neg']
        tol_a_pos = tolerances['face_angle']['pos']

        col1, col2, col3 = st.columns(3)
        with col1:
            devs_h = [r['height_dev'] for r in filtered_results if r['height_dev'] is not None]
            fig_h = go.Figure(go.Histogram(x=devs_h, nbinsx=15, marker_color='royalblue'))
            fig_h.update_layout(title="Distribución Desv. Altura (m)", height=300,
                                xaxis_title="Desviación (m)", yaxis_title="Frecuencia")
            fig_h.add_vline(x=-tol_h_neg, line_dash="dash", line_color="orange")
            fig_h.add_vline(x=tol_h_pos, line_dash="dash", line_color="orange")
            st.plotly_chart(fig_h, use_container_width=True)
        with col2:
            devs_a = [r['angle_dev'] for r in filtered_results if r['angle_dev'] is not None]
            fig_a = go.Figure(go.Histogram(x=devs_a, nbinsx=15, marker_color='forestgreen'))
            fig_a.update_layout(title="Distribución Desv. Ángulo Cara (°)", height=300,
                                xaxis_title="Desviación (°)", yaxis_title="Frecuencia")
            fig_a.add_vline(x=-tol_a_neg, line_dash="dash", line_color="orange")
            fig_a.add_vline(x=tol_a_pos, line_dash="dash", line_color="orange")
            st.plotly_chart(fig_a, use_container_width=True)
        with col3:
            berm_vals = [r['berm_real'] for r in filtered_results if r['berm_real'] is not None and r['berm_real'] > 0]
            if berm_vals:
                fig_b = go.Figure(go.Histogram(x=berm_vals, nbinsx=15, marker_color='#FF7F0E'))
                fig_b.update_layout(title="Distribución Ancho Berma (m)", height=300,
                                    xaxis_title="Ancho (m)", yaxis_title="Frecuencia")
                fig_b.add_vline(x=min_berm_width, line_dash="dash", line_color="red",
                                annotation_text="Mínimo", annotation_position="top right")
                st.plotly_chart(fig_b, use_container_width=True)


# ──────────────────────────────────────────────────────────────
# Tab: Analista IA
# ──────────────────────────────────────────────────────────────
def _render_tab_ai(tab, config: dict):
    with tab:
        df_final = pd.DataFrame(st.session_state.comparison_results)
        if df_final.empty:
            st.warning("No hay resultados para analizar.")
            return

        # Unconditional Local Advisory Engine
        blast_df = st.session_state.get('blast_df_clean')
        if blast_df is not None and not blast_df.empty:
            st.subheader("🔬 Diagnóstico de Perforación y Voladura")
            pasadura = (blast_df['Z_collar'] - 15.0) - blast_df['Z_toe']
            p_mean = pasadura.mean()

            has_alert = False
            if p_mean < 0.4:
                st.warning(f"⚠️ **Alerta Pasadura Corta ({p_mean:.2f}m)**: Se registra una pasadura promedio deficiente. Esto eleva el riesgo de lomos duros y pisos irregulares en el banco. Se sugiere incrementar la perforación nominal en 0.5m.")
                has_alert = True
            elif p_mean > 1.8:
                st.warning(f"⚠️ **Alerta Pasadura Excesiva ({p_mean:.2f}m)**: La sobre-perforación promedio es excesiva. Esto aumenta las vibraciones no confinadas y fractura la cresta del banco inferior. Se sugiere reducir el largo de los pozos.")
                has_alert = True

            # Check overbreak correlation
            from core.calculo_tronadura import proyectar_pozos_en_seccion
            from core.geom_utils import find_df_column
            comparison = st.session_state.get('comparison_results', [])
            sections = st.session_state.get('sections', [])
            kg_col = find_df_column(blast_df, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)

            if comparison and sections and kg_col:
                df_comp = pd.DataFrame(comparison)
                dev_col = None
                for col_name in ['delta_crest', 'height_dev']:
                    if col_name in df_comp.columns:
                        dev_col = col_name
                        break
                if dev_col:
                    df_comp['abs_dev'] = df_comp[dev_col].abs()
                    sec_grouped = df_comp.groupby('section')['abs_dev'].mean().reset_index()

                    for sec in sections:
                        sec_name = sec.name
                        match = sec_grouped[sec_grouped['section'] == sec_name]
                        if match.empty:
                            continue
                        avg_dev = match['abs_dev'].values[0]

                        proj = proyectar_pozos_en_seccion(blast_df, sec.start, sec.azimuth, sec.length, tolerance=15.0)
                        if not proj.empty:
                            total_kg = proj[kg_col].fillna(0).sum()
                            if avg_dev > 1.0 and total_kg > 2000:
                                st.info(f"💡 **Recomendación Voladura en {sec_name}**: Se registra daño severo en el talud ({avg_dev:.2f}m) junto con una alta concentración de carga cercana ({total_kg:.0f} Kg). Se sugiere aumentar el espaciamiento de pre-corte en un 10% o reducir el factor de carga en las primeras filas de producción.")
                                has_alert = True

            if not has_alert:
                st.success("✅ **Estabilidad Operativa**: No se detectan anomalías críticas de correlación energía-daño o desviaciones extremas de pasadura en los bancos analizados.")
            st.markdown("---")

        st.subheader("🤖 Informe Ejecutivo (IA)")

        ai_enabled = config['ai_enabled']
        api_key = config['api_key']
        model_name = config['model_name']
        base_url = config['base_url']

        if not ai_enabled:
            st.info("Habilita el Asistente IA en la configuración (barra lateral) para generar informes automáticos.")
        else:
            if st.button("📝 Generar Informe Ejecutivo", type="primary"):
                from core.ai_reporter import generate_geotech_report

                n_total = len(df_final)
                n_compliant_h = len(df_final[df_final['height_status'] == "CUMPLE"])
                n_compliant_a = len(df_final[df_final['angle_status'] == "CUMPLE"])
                n_compliant_b = len(df_final[df_final['berm_status'] == "CUMPLE"])

                blast_stats = {}
                if blast_df is not None and not blast_df.empty:
                    pasadura = (blast_df['Z_collar'] - 15.0) - blast_df['Z_toe']
                    p_mean = pasadura.mean()
                    p_optimal = ((pasadura >= 0.5) & (pasadura <= 1.5)).sum()
                    p_pct = p_optimal / len(blast_df) * 100 if len(blast_df) > 0 else 0

                    from core.calculo_tronadura import proyectar_pozos_en_seccion
                    from core.geom_utils import find_df_column
                    r_coef = 0.0
                    corr_interp = "No calculada"
                    kg_col = find_df_column(blast_df, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)

                    if comparison and sections and kg_col:
                        import numpy as np
                        df_comp = pd.DataFrame(comparison)
                        dev_col = None
                        for col_name in ['delta_crest', 'height_dev', 'angle_dev']:
                            if col_name in df_comp.columns:
                                dev_col = col_name
                                break
                        if dev_col:
                            df_comp['abs_dev'] = df_comp[dev_col].abs()
                            sec_grouped = df_comp.groupby('section')['abs_dev'].mean().reset_index()

                            corr_data = []
                            for sec in sections:
                                sec_name = sec.name
                                match = sec_grouped[sec_grouped['section'] == sec_name]
                                if match.empty:
                                    continue
                                avg_dev = match['abs_dev'].values[0]
                                proj_wells = proyectar_pozos_en_seccion(blast_df, sec.start, sec.azimuth, sec.length, tolerance=15.0)
                                total_kg = proj_wells[kg_col].fillna(0).sum() if not proj_wells.empty else 0
                                corr_data.append({'Kg_Explosivo': total_kg, 'Desviacion': avg_dev})

                            df_corr = pd.DataFrame(corr_data)
                            if not df_corr.empty and df_corr['Kg_Explosivo'].sum() > 0:
                                xs = df_corr['Kg_Explosivo'].values.astype(float)
                                ys = df_corr['Desviacion'].values.astype(float)
                                if len(xs) > 1 and np.var(xs) > 0 and np.var(ys) > 0:
                                    r_coef = np.corrcoef(xs, ys)[0, 1]
                                    if r_coef > 0.5:
                                        corr_interp = f"Fuerte Positiva (r={r_coef:.2f}): El sobre-quiebre está ligado directamente a la alta carga explosiva."
                                    elif r_coef < -0.5:
                                        corr_interp = f"Negativa (r={r_coef:.2f})"
                                    else:
                                        corr_interp = f"Moderada/Débil (r={r_coef:.2f}): El daño no correlaciona de forma directa con la carga explosiva de voladura."

                    blast_stats = {
                        'n_pozos': len(blast_df),
                        'pasadura_promedio': f"{p_mean:.2f}",
                        'pasadura_optima_pct': f"{p_pct:.1f}",
                        'correlacion_r': f"{r_coef:.2f}",
                        'correlacion_interpretacion': corr_interp
                    }

                ai_stats = {
                    'n_total': int(n_total),
                    'n_valid': int(len(df_final[df_final['type'] == 'MATCH'])),
                    'global_stats': {
                        'Cumplimiento Altura': f"{n_compliant_h}/{n_total} ({n_compliant_h / n_total:.1%})",
                        'Cumplimiento Ángulo': f"{n_compliant_a}/{n_total} ({n_compliant_a / n_total:.1%})",
                        'Cumplimiento Berma': f"{n_compliant_b}/{n_total} ({n_compliant_b / n_total:.1%})"
                    },
                    'blast_stats': blast_stats
                }

                st.markdown("### ⏳ Analizando datos y redactando informe...")
                report_container = st.empty()
                full_report = ""

                for chunk in generate_geotech_report(ai_stats, api_key, model_name, base_url):
                    full_report += (chunk or "")
                    report_container.markdown(full_report + "▌")

                report_container.markdown(full_report)


# ──────────────────────────────────────────────────────────────
# Tab: Exportar
# ──────────────────────────────────────────────────────────────
def _render_tab_export(tab, config: dict):
    with tab:
        tolerances = config['tolerances']
        project_info = config['project_info']

        # --- Excel ---
        st.subheader("💾 Exportar Resultados a Excel")

        if st.button("📥 Generar Excel de Conciliación", type="primary"):
            with st.spinner("Generando Excel..."):
                output_path = os.path.join(tempfile.gettempdir(), "Conciliacion_Resultados.xlsx")
                project_info_full = {
                    'project': project_info['project'],
                    'operation': project_info['operation'],
                    'phase': project_info['phase'],
                    'author': project_info['author'],
                    'date': datetime.now().strftime("%d/%m/%Y"),
                }
                export_results(
                    st.session_state.comparison_results,
                    st.session_state.params_design,
                    st.session_state.params_topo,
                    tolerances, output_path, project_info_full,
                    df_pozos=st.session_state.get('blast_df_clean'),
                    sections=st.session_state.get('sections')
                )

                with open(output_path, "rb") as f:
                    st.download_button(
                        "⬇️ Descargar Excel",
                        f.read(),
                        file_name="Conciliacion_Diseno_vs_AsBuilt.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                    )
            st.success("✅ Excel generado exitosamente")

        st.divider()

        # --- Images ZIP ---
        st.subheader("🖼️ Exportar Imágenes de Sección")
        st.write("Genera un archivo ZIP con todos los gráficos de perfil en formato PNG.")

        if st.button("📦 Generar Imágenes (ZIP)", type="primary"):
            with st.spinner("Generando gráficos e imágenes..."):
                all_data_for_images = []
                progress_bar = st.progress(0)

                for i, sec in enumerate(st.session_state.sections):
                    pd_prof, pt_prof = cut_both_surfaces(
                        st.session_state.mesh_design,
                        st.session_state.mesh_topo,
                        sec
                    )

                    if (pd_prof and pt_prof
                            and i < len(st.session_state.params_design)
                            and i < len(st.session_state.params_topo)):
                        all_data_for_images.append({
                            'section_name': sec.name,
                            'params_design': st.session_state.params_design[i],
                            'params_topo': st.session_state.params_topo[i],
                            'profile_d': (pd_prof.distances, pd_prof.elevations),
                            'profile_t': (pt_prof.distances, pt_prof.elevations),
                        })
                    progress_bar.progress((i + 1) / len(st.session_state.sections))

                zip_bytes = generate_section_images_zip(all_data_for_images)

                st.download_button(
                    label="⬇️ Descargar Imágenes ZIP",
                    data=zip_bytes,
                    file_name="Perfiles_Secciones.zip",
                    mime="application/zip",
                )
            st.success("✅ Imágenes generadas exitosamente")

        st.divider()

        # --- DXF ---
        st.subheader("📐 Exportar Perfiles a DXF (3D)")
        st.write("Genera un archivo DXF con polilíneas 3D separadas por cumplimiento, incluyendo perfiles conciliados.")

        if st.button("📊 Generar DXF de Perfiles", type="primary"):
            with st.spinner("Generando DXF 3D de perfiles..."):
                import ezdxf
                from core.section_cutter import azimuth_to_direction

                doc = ezdxf.new('R2010')
                msp = doc.modelspace()

                doc.layers.add("DISEÑO_CUMPLE", color=3)
                doc.layers.add("DISEÑO_NO_CUMPLE", color=1)
                doc.layers.add("DISEÑO_FUERA_TOL", color=2)
                doc.layers.add("TOPO_CUMPLE", color=3)
                doc.layers.add("TOPO_NO_CUMPLE", color=1)
                doc.layers.add("TOPO_FUERA_TOL", color=2)
                doc.layers.add("CONCILIADO_DISEÑO", color=5)
                doc.layers.add("CONCILIADO_TOPO", color=6)
                doc.layers.add("ETIQUETAS", color=7)

                comp_results = st.session_state.comparison_results
                section_status = {}
                for c in comp_results:
                    sec = c.get('section', '')
                    statuses = [c.get('height_status', ''), c.get('angle_status', ''), c.get('berm_status', '')]
                    if sec not in section_status:
                        section_status[sec] = 'CUMPLE'
                    if 'NO CUMPLE' in statuses:
                        section_status[sec] = 'NO CUMPLE'
                    elif 'FUERA DE TOLERANCIA' in statuses and section_status[sec] != 'NO CUMPLE':
                        section_status[sec] = 'FUERA DE TOLERANCIA'

                progress_bar = st.progress(0)
                n_exported = 0

                for i, sec in enumerate(st.session_state.sections):
                    pd_prof, pt_prof = cut_both_surfaces(
                        st.session_state.mesh_design,
                        st.session_state.mesh_topo,
                        sec
                    )

                    if pd_prof and pt_prof:
                        safe_name = sec.name.replace("/", "_").replace("\\", "_")

                        status = section_status.get(sec.name, 'CUMPLE')
                        if status == 'NO CUMPLE':
                            layer_suffix = 'NO_CUMPLE'
                        elif status == 'FUERA DE TOLERANCIA':
                            layer_suffix = 'FUERA_TOL'
                        else:
                            layer_suffix = 'CUMPLE'

                        direction = azimuth_to_direction(sec.azimuth)
                        ox, oy = sec.origin[0], sec.origin[1]

                        def to_3d(distances, elevations):
                            return [
                                (ox + d * direction[0], oy + d * direction[1], float(e))
                                for d, e in zip(distances, elevations)
                            ]

                        def draw_3d_polyline(pts, layer):
                            for j in range(len(pts) - 1):
                                msp.add_line(pts[j], pts[j + 1], dxfattribs={'layer': layer})

                        design_3d = to_3d(pd_prof.distances, pd_prof.elevations)
                        if len(design_3d) > 1:
                            draw_3d_polyline(design_3d, f'DISEÑO_{layer_suffix}')

                        topo_3d = to_3d(pt_prof.distances, pt_prof.elevations)
                        if len(topo_3d) > 1:
                            draw_3d_polyline(topo_3d, f'TOPO_{layer_suffix}')

                        if i < len(st.session_state.params_design) and st.session_state.params_design[i].benches:
                            rd, re = build_reconciled_profile(st.session_state.params_design[i].benches)
                            if len(rd) > 0:
                                conc_d_3d = to_3d(rd, re)
                                if len(conc_d_3d) > 1:
                                    draw_3d_polyline(conc_d_3d, 'CONCILIADO_DISEÑO')

                        if i < len(st.session_state.params_topo) and st.session_state.params_topo[i].benches:
                            rt, ret = build_reconciled_profile(st.session_state.params_topo[i].benches)
                            if len(rt) > 0:
                                conc_t_3d = to_3d(rt, ret)
                                if len(conc_t_3d) > 1:
                                    draw_3d_polyline(conc_t_3d, 'CONCILIADO_TOPO')

                        mid_z = float(max(pd_prof.elevations.max(), pt_prof.elevations.max())) + 3
                        label_text = f"{safe_name} [{status}]"
                        msp.add_text(
                            label_text,
                            dxfattribs={
                                'height': 2.0,
                                'layer': 'ETIQUETAS',
                                'insert': (ox, oy, mid_z)
                            }
                        )

                        n_exported += 1

                    progress_bar.progress((i + 1) / len(st.session_state.sections))

                tmp_path = os.path.join(tempfile.gettempdir(), "Perfiles_3D.dxf")
                doc.saveas(tmp_path)

                with open(tmp_path, "rb") as f:
                    dxf_bytes = f.read()

                st.download_button(
                    label=f"⬇️ Descargar DXF 3D ({n_exported} secciones)",
                    data=dxf_bytes,
                    file_name="Perfiles_3D.dxf",
                    mime="application/dxf",
                )
            st.success(f"✅ {n_exported} perfiles exportados a DXF 3D exitosamente")
