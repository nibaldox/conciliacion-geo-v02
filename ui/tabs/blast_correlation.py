import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
try:
    import statsmodels  # noqa: F401
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False
from core.calculo_tronadura import proyectar_pozos_en_seccion
from core.blast_correlation import (
    aggregate_powder_factor_by_group,
    compute_powder_factor,
    compute_signed_deviations,
)
from core.config import DEFAULTS
from core.geom_utils import calculate_area_between_profiles, find_df_column
from core.section_cutter import cut_both_surfaces
from ui.filter_cache import _ensure_filter_values
from ui.tabs.export import _get_profile_pair

def render_tab_blast_correlation(config: dict) -> None:
    blast_df = st.session_state.get('blast_df_clean')
    comparison_results = st.session_state.get('comparison_results')
    sections = st.session_state.get('sections', [])
    mesh_design = st.session_state.get('mesh_design')
    mesh_topo = st.session_state.get('mesh_topo')

    if blast_df is None or blast_df.empty:
        st.warning("⚠️ No se han cargado datos de pozos de tronadura. Por favor, suba el archivo de pozos de tronadura en el Módulo de Tronadura para activar este análisis.")
        return

    if not comparison_results or not sections or mesh_design is None or mesh_topo is None:
        st.warning("⚠️ Datos de conciliación insuficientes. Asegúrese de haber generado las secciones y ejecutado la conciliación en los pasos anteriores.")
        return

    st.subheader("💥 Correlación Geotécnica vs Carga Explosiva (Perforación y Voladura)")

    st.markdown(
        "Esta pestaña permite evaluar cuantitativamente el impacto de la energía explosiva "
        "en las desviaciones de sobre-excavación y deuda de material en los bancos, sectores y mallas."
    )

    tolerance = st.slider(
        "Tolerancia de Proyección de Pozos a la Sección (m):",
        min_value=5.0, max_value=30.0, value=DEFAULTS.blast_correlation_radius_m, step=1.0,
        key="corr_projection_tolerance"
    )

    use_temporal_filter = st.checkbox(
        "Filtrar pozos por fecha de tronadura (recomendado)",
        value=True,
        key="corr_use_temporal_filter",
        help="Excluye pozos tronados después del levantamiento topográfico para evitar correlaciones espurias.",
    )
    fecha_levantamiento = None
    if use_temporal_filter:
        fecha_levantamiento = st.date_input(
            "Fecha de levantamiento topográfico:",
            value=None,
            key="fecha_levantamiento",
            help="Solo se incluyen pozos tronados en o antes de esta fecha.",
        )
        if fecha_levantamiento is None:
            st.warning("⚠️ No se ha indicado fecha de levantamiento: la correlación puede incluir pozos tronados después del levantamiento, generando resultados espurios.")
    else:
        st.info("ℹ️ Filtro temporal desactivado: la correlación puede incluir pozos tronados después del levantamiento.")

    fecha_corte_str = fecha_levantamiento.isoformat() if fecha_levantamiento else None

    df_sections_calc = _get_or_compute_sections_data(
        sections, mesh_design, mesh_topo, blast_df, comparison_results,
        tolerance, fecha_corte_str,
    )

    with st.expander("🔎 Filtros del Análisis de Correlación", expanded=True):
        cols_filter = st.columns(3)
        
        all_sectors = sorted(df_sections_calc['sector'].unique().tolist())
        sel_sectors = cols_filter[0].multiselect("Filtrar por Sector:", all_sectors, default=[], key="corr_filter_sector")

        kg_col = find_df_column(blast_df, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)
        malla_candidates = ['holes_polygon', 'Nombre_Malla_Original', 'Malla', 'Polígono']
        malla_col = find_df_column(blast_df, malla_candidates, raise_error=False)
        
        all_mallas = []
        if malla_col and malla_col in blast_df.columns:
            all_mallas = sorted(blast_df[malla_col].dropna().unique().tolist())
        
        sel_mallas = cols_filter[1].multiselect("Filtrar por Malla/Polígono:", all_mallas, default=[], key="corr_filter_malla")

        unique_levels = _ensure_filter_values()['levels']
        sel_levels = cols_filter[2].multiselect("Filtrar por Nivel/Cota:", unique_levels, default=[], key="corr_filter_level")

    df_filtered_sections = df_sections_calc.copy()
    if sel_sectors:
        df_filtered_sections = df_filtered_sections[df_filtered_sections['sector'].isin(sel_sectors)]

    df_filtered_comps = pd.DataFrame(comparison_results)
    if sel_sectors:
        df_filtered_comps = df_filtered_comps[df_filtered_comps['sector'].isin(sel_sectors)]
    if sel_levels:
        df_filtered_comps = df_filtered_comps[df_filtered_comps['level'].isin(sel_levels)]

    st.markdown("---")

    col_metrics = st.columns(4)

    tot_pozos = int(df_filtered_sections['num_pozos'].sum())
    tot_charge = df_filtered_sections['total_kg'].sum()
    avg_overbreak = df_filtered_sections['area_over'].mean()

    use_pf_axis = (
        'pf_vol_avg_kgm3' in df_filtered_sections.columns
        and not df_filtered_sections['_pf_unavailable'].iloc[0] if not df_filtered_sections.empty else False
    )

    r_coef = 0.0
    r_text = "Insuficientes datos"
    r_label = "Correlación Carga vs Daño"
    if len(df_filtered_sections) > 1:
        if use_pf_axis:
            x_vals = pd.to_numeric(df_filtered_sections['pf_vol_avg_kgm3'], errors='coerce').fillna(0).values.astype(float)
            x_label = "Powder Factor (kg/m³)"
        else:
            x_vals = df_filtered_sections['total_kg'].values.astype(float)
            x_label = "Carga Explosiva (Kg crudo)"
            r_label = "Correlación Carga (kg) vs Daño"
        y_vals = df_filtered_sections['area_over'].values.astype(float)
        if np.var(x_vals) > 0 and np.var(y_vals) > 0:
            r_coef = np.corrcoef(x_vals, y_vals)[0, 1]
            if r_coef > 0.6:
                r_text = f"Fuerte Positiva (r={r_coef:.2f}) ⚠️"
            elif r_coef > 0.3:
                r_text = f"Moderada Positiva (r={r_coef:.2f}) ⚠️"
            elif r_coef < -0.3:
                r_text = f"Negativa (r={r_coef:.2f})"
            else:
                r_text = f"Débil / Nula (r={r_coef:.2f})"

    col_metrics[0].metric("Pozos Proyectados", f"{tot_pozos}")
    col_metrics[1].metric("Carga Proyectada Total", f"{tot_charge:,.0f} Kg")
    col_metrics[2].metric("Sobre-excavación Media", f"{avg_overbreak:.1f} m²")
    col_metrics[3].metric(r_label, r_text)

    if not df_filtered_sections.empty and bool(df_filtered_sections['_pf_unavailable'].iloc[0]):
        st.info("ℹ️ Powder factor no disponible: faltan columnas de burden/espaciamiento en el archivo de pozos.")

    tab_sec, tab_bnc, tab_mal = st.tabs([
        "📐 Análisis por Sección / Perfil",
        "🧱 Análisis por Banco / Nivel",
        "🕸️ Análisis por Malla / Polígono"
    ])

    with tab_sec:
        st.markdown("#### Distribución de Energía y Desviación por Sección Transversal")

        col_list = ['section', 'sector', 'num_pozos', 'total_kg', 'area_over', 'area_under', 'avg_over_break', 'avg_under_break', 'pf_vol_avg_kgm3', 'pf_area_avg_kgm2', 'energy_total_mj']
        col_list = [c for c in col_list if c in df_filtered_sections.columns]
        display_map = {
            'section': 'Sección',
            'sector': 'Sector',
            'num_pozos': 'Pozos Proyectados',
            'total_kg': 'Carga Explosiva (Kg)',
            'area_over': 'Sobre-excavación (m²)',
            'area_under': 'Deuda / Relleno (m²)',
            'avg_over_break': 'Sobre-excavación Media (m)',
            'avg_under_break': 'Deuda / Relleno Media (m)',
            'pf_vol_avg_kgm3': 'PF Vol. (kg/m³)',
            'pf_area_avg_kgm2': 'PF Área (kg/m²)',
            'energy_total_mj': 'Energía (MJ)',
        }

        df_sec_disp = df_filtered_sections[col_list].rename(columns=display_map)
        st.dataframe(df_sec_disp, use_container_width=True, height=300)

        if len(df_filtered_sections) > 1:
            if use_pf_axis:
                x_axis = "pf_vol_avg_kgm3"
                x_label = "Powder Factor Volumétrico (kg/m³)"
                title = "Correlación: Powder Factor (kg/m³) vs Sobre-excavación Media"
            else:
                x_axis = "total_kg"
                x_label = "Carga Explosiva Proyectada (Kg) — fallback sin PF"
                title = "Correlación: Carga Explosiva (Kg) vs Sobre-excavación Media"

            x_for_var = pd.to_numeric(df_filtered_sections[x_axis], errors='coerce').fillna(0).values.astype(float)
            trendline = "ols" if _HAS_STATSMODELS and len(df_filtered_sections) > 2 and np.var(x_for_var) > 0 else None
            fig_scatter = px.scatter(
                df_filtered_sections,
                x=x_axis,
                y="avg_over_break",
                color="sector",
                hover_name="section",
                labels={
                    x_axis: x_label,
                    "avg_over_break": "Sobre-excavación Media (m)",
                    "sector": "Sector"
                },
                title=title,
                trendline=trendline,
            )
            fig_scatter.update_layout(height=450)
            st.plotly_chart(fig_scatter, use_container_width=True)
            if not use_pf_axis:
                st.caption("⚠️ Scatter con Kg crudo: powder factor no disponible (faltan columnas de burden/espaciamiento).")

    with tab_bnc:
        st.markdown("#### Comportamiento Horizontal por Banco / Nivel de Cota")

        df_bench_corr = _compute_bench_correlation(sections, blast_df, df_filtered_comps, tolerance, kg_col, fecha_corte_str)
        if df_bench_corr.empty:
            st.info("No hay datos de bancos para los filtros seleccionados.")
        else:
            col_list_b = ['level', 'num_pozos', 'total_kg', 'avg_dev_crest_over', 'avg_dev_crest_under', 'avg_dev_toe_over', 'avg_dev_toe_under', 'pf_vol_avg_kgm3', 'energy_total_mj']
            col_list_b = [c for c in col_list_b if c in df_bench_corr.columns]
            display_map_b = {
                'level': 'Nivel / Cota',
                'num_pozos': 'Cantidad de Pozos',
                'total_kg': 'Carga Explosiva (Kg)',
                'avg_dev_crest_over': 'Sobre-quiebre Cresta (m)',
                'avg_dev_crest_under': 'Deuda Cresta (m)',
                'avg_dev_toe_over': 'Sobre-quiebre Pata (m)',
                'avg_dev_toe_under': 'Deuda Pata (m)',
                'pf_vol_avg_kgm3': 'PF Vol. (kg/m³)',
                'energy_total_mj': 'Energía (MJ)',
            }
            df_b_disp = df_bench_corr[col_list_b].rename(columns=display_map_b)
            st.dataframe(df_b_disp, use_container_width=True, height=300)

            fig_bench = go.Figure()
            fig_bench.add_trace(go.Bar(
                x=df_bench_corr['level'],
                y=df_bench_corr['total_kg'],
                name='Carga Explosiva (Kg)',
                marker_color='crimson',
                yaxis='y'
            ))
            fig_bench.add_trace(go.Scatter(
                x=df_bench_corr['level'],
                y=df_bench_corr['avg_dev_crest_over'],
                name='Sobre-quiebre Cresta (m)',
                mode='lines+markers',
                line=dict(color='darkorange', width=3),
                yaxis='y2'
            ))
            fig_bench.add_trace(go.Scatter(
                x=df_bench_corr['level'],
                y=df_bench_corr['avg_dev_crest_under'],
                name='Deuda Cresta (m)',
                mode='lines+markers',
                line=dict(color='steelblue', width=3, dash='dash'),
                yaxis='y2'
            ))
            if 'pf_vol_avg_kgm3' in df_bench_corr.columns:
                pf_vals = pd.to_numeric(df_bench_corr['pf_vol_avg_kgm3'], errors='coerce')
                if pf_vals.notna().any():
                    fig_bench.add_trace(go.Scatter(
                        x=df_bench_corr['level'],
                        y=pf_vals,
                        name='Powder Factor Vol. (kg/m³)',
                        mode='lines+markers',
                        line=dict(color='mediumvioletred', width=2, dash='dot'),
                        yaxis='y3',
                    ))

            yaxis3_cfg = {}
            if 'pf_vol_avg_kgm3' in df_bench_corr.columns:
                yaxis3_cfg = dict(
                    title=dict(text='Powder Factor (kg/m³)', font=dict(color='mediumvioletred')),
                    tickcolor='mediumvioletred',
                    overlaying='y',
                    side='right',
                    anchor='x',
                    position=0.97,
                )

            fig_bench.update_layout(
                title='Relación Carga Explosiva vs Desviación de Cresta por Banco (con signo)',
                xaxis=dict(title='Nivel de Banco (Cota)', type='category'),
                yaxis=dict(title=dict(text='Carga Explosiva Total (Kg)', font=dict(color='crimson')), tickcolor='crimson'),
                yaxis2=dict(
                    title=dict(text='Desviación de Cresta Media (m, con signo)', font=dict(color='darkorange')),
                    tickcolor='darkorange',
                    overlaying='y',
                    side='right',
                    zeroline=True,
                    zerolinecolor='gray',
                    zerolinewidth=1
                ),
                height=450,
                legend=dict(x=0.01, y=0.99)
            )
            if yaxis3_cfg:
                fig_bench.update_layout(yaxis3=yaxis3_cfg)
            st.plotly_chart(fig_bench, use_container_width=True)

    with tab_mal:
        st.markdown("#### Evaluación de Daño Geotécnico por Malla / Polígono de Tronadura")

        df_malla_corr = _compute_malla_correlation(sections, blast_df, df_filtered_sections, tolerance, kg_col, malla_col, fecha_corte_str)
        if df_malla_corr.empty:
            st.info("No se identificaron mallas o polígonos de tronadura válidos en los datos cargados.")
        else:
            if sel_mallas:
                df_malla_corr = df_malla_corr[df_malla_corr['malla'].isin(sel_mallas)]

            col_list_m = ['malla', 'num_pozos', 'total_kg', 'avg_dev_crest_over', 'avg_dev_crest_under', 'avg_dev_toe_over', 'avg_dev_toe_under', 'avg_overbreak', 'pf_vol_avg_kgm3', 'energy_total_mj']
            col_list_m = [c for c in col_list_m if c in df_malla_corr.columns]
            display_map_m = {
                'malla': 'Malla / Polígono',
                'num_pozos': 'Cantidad de Pozos',
                'total_kg': 'Carga Explosiva (Kg)',
                'avg_dev_crest_over': 'Sobre-quiebre Cresta (m)',
                'avg_dev_crest_under': 'Deuda Cresta (m)',
                'avg_dev_toe_over': 'Sobre-quiebre Pata (m)',
                'avg_dev_toe_under': 'Deuda Pata (m)',
                'avg_overbreak': 'Sobre-excavación Media (m)',
                'pf_vol_avg_kgm3': 'PF Vol. (kg/m³)',
                'energy_total_mj': 'Energía (MJ)',
            }
            df_m_disp = df_malla_corr[col_list_m].rename(columns=display_map_m)
            st.dataframe(df_m_disp, use_container_width=True, height=300)

            color_axis = 'pf_vol_avg_kgm3' if 'pf_vol_avg_kgm3' in df_malla_corr.columns and df_malla_corr['pf_vol_avg_kgm3'].notna().any() else 'total_kg'
            color_label = 'Powder Factor (kg/m³)' if color_axis == 'pf_vol_avg_kgm3' else 'Carga Explosiva Total (Kg)'
            fig_malla = px.bar(
                df_malla_corr,
                x='malla',
                y='avg_overbreak',
                color=color_axis,
                color_continuous_scale='YlOrRd',
                labels={
                    'malla': 'Malla de Tronadura',
                    'avg_overbreak': 'Área de Sobre-excavación Promedio (m²)',
                    color_axis: color_label,
                },
                title='Área de Sobre-excavación Promedio por Malla de Tronadura'
            )
            fig_malla.update_layout(height=450)
            st.plotly_chart(fig_malla, use_container_width=True)


def _get_or_compute_sections_data(sections, mesh_design, mesh_topo, blast_df, comparison_results, tolerance, fecha_corte=None) -> pd.DataFrame:
    cut_cache_key = (
        tuple(s.name for s in sections),
        tuple(sorted(blast_df.columns)),
    )
    full_cache_key = (cut_cache_key, tolerance, fecha_corte)

    if 'blast_corr_sections_cache' in st.session_state:
        cached_key, cached_df = st.session_state.blast_corr_sections_cache
        if cached_key == full_cache_key:
            return cached_df

    cuts_cache = st.session_state.get('blast_corr_cuts_cache')
    if cuts_cache and cuts_cache[0] == cut_cache_key:
        cuts = cuts_cache[1]
    else:
        cuts = {}
        for sec in sections:
            pd_prof, pt_prof = _get_profile_pair(sec.name)
            if pd_prof is None or pt_prof is None:
                pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sec)
            if pd_prof and pt_prof:
                cuts[sec.name] = (pd_prof, pt_prof)
        st.session_state.blast_corr_cuts_cache = (cut_cache_key, cuts)

    data_rows = []
    kg_col = find_df_column(blast_df, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)

    pf_enriched = compute_powder_factor(blast_df) if not blast_df.empty else blast_df
    has_pf_input = (
        ('Burden' in blast_df.columns or 'Nombre_Malla_Original' in blast_df.columns or 'holes_polygon' in blast_df.columns)
    )

    for sec in sections:
        cut = cuts.get(sec.name)
        if not cut:
            continue
        pd_prof, pt_prof = cut

        a_over, a_under, _, _, _ = calculate_area_between_profiles(pd_prof, pt_prof)

        proj = proyectar_pozos_en_seccion(
            blast_df,
            origin=sec.origin,
            azimuth=sec.azimuth,
            length=sec.length,
            tolerance=tolerance,
            fecha_corte=fecha_corte,
        )

        num_pozos = len(proj)
        total_kg = proj[kg_col].fillna(0).sum() if (kg_col and not proj.empty) else 0.0

        signed = compute_signed_deviations(comparison_results or [], sec.name)

        proj_labeled = proj.copy()
        if not proj_labeled.empty:
            proj_labeled['section_name'] = sec.name
        pf_row = aggregate_powder_factor_by_group(
            pf_enriched, 'section_name', sec.name, proj_labeled,
        )

        data_rows.append({
            'section': sec.name,
            'sector': sec.sector,
            'num_pozos': num_pozos,
            'total_kg': total_kg,
            'area_over': a_over,
            'area_under': a_under,
            'avg_over_break': signed['avg_over'],
            'avg_under_break': signed['avg_under'],
            'pf_vol_avg_kgm3': pf_row.get('pf_vol_avg'),
            'pf_area_avg_kgm2': pf_row.get('pf_area_avg'),
            'energy_total_mj': pf_row.get('energy_total_mj', 0.0),
            'n_pf_valid': pf_row.get('n_pf_valid', 0),
        })

    df = pd.DataFrame(data_rows)
    if df.empty:
        df = pd.DataFrame(columns=[
            'section', 'sector', 'num_pozos', 'total_kg',
            'area_over', 'area_under', 'avg_over_break', 'avg_under_break',
            'pf_vol_avg_kgm3', 'pf_area_avg_kgm2', 'energy_total_mj', 'n_pf_valid',
        ])
    if 'pf_vol_avg_kgm3' in df.columns:
        if df['pf_vol_avg_kgm3'].isna().all() or (df['n_pf_valid'].fillna(0) == 0).all():
            df['_pf_unavailable'] = True
        else:
            df['_pf_unavailable'] = False
    else:
        df['_pf_unavailable'] = True

    if not has_pf_input:
        df['_pf_unavailable'] = True

    st.session_state.blast_corr_sections_cache = (full_cache_key, df)
    return df


def _compute_bench_correlation(sections, blast_df, df_comps, tolerance, kg_col, fecha_corte=None) -> pd.DataFrame:
    if df_comps.empty:
        return pd.DataFrame()

    pf_enriched = compute_powder_factor(blast_df) if not blast_df.empty else blast_df

    bench_stats = []

    unique_levels = df_comps['level'].unique().tolist()
    for lvl in unique_levels:
        df_lvl_comps = df_comps[df_comps['level'] == lvl]

        if 'delta_crest' in df_lvl_comps.columns:
            dev_crest_over_list = df_lvl_comps['delta_crest'].dropna()
            dev_crest_over_list = dev_crest_over_list[dev_crest_over_list > 0].tolist()
            dev_crest_under_list = df_lvl_comps['delta_crest'].dropna()
            dev_crest_under_list = dev_crest_under_list[dev_crest_under_list < 0].tolist()
        else:
            dev_crest_over_list = []
            dev_crest_under_list = []

        if 'delta_toe' in df_lvl_comps.columns:
            dev_toe_over_list = df_lvl_comps['delta_toe'].dropna()
            dev_toe_over_list = dev_toe_over_list[dev_toe_over_list > 0].tolist()
            dev_toe_under_list = df_lvl_comps['delta_toe'].dropna()
            dev_toe_under_list = dev_toe_under_list[dev_toe_under_list < 0].tolist()
        else:
            dev_toe_over_list = []
            dev_toe_under_list = []

        avg_dev_crest_over = float(np.mean(dev_crest_over_list)) if dev_crest_over_list else 0.0
        avg_dev_crest_under = float(np.mean(dev_crest_under_list)) if dev_crest_under_list else 0.0
        avg_dev_toe_over = float(np.mean(dev_toe_over_list)) if dev_toe_over_list else 0.0
        avg_dev_toe_under = float(np.mean(dev_toe_under_list)) if dev_toe_under_list else 0.0

        num_pozos = 0
        total_kg = 0.0
        pf_vol_avg = float('nan')
        energy_total = 0.0
        pf_area_avg = float('nan')

        lvl_float = None
        try:
            lvl_float = float(lvl)
        except ValueError:
            pass

        if lvl_float is not None:
            mask_pozos = (blast_df['Z_collar'] - lvl_float).abs() <= DEFAULTS.blast_correlation_radius_m
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
                    proj_labeled['level'] = str(lvl)
                    pf_row = aggregate_powder_factor_by_group(
                        pf_enriched, 'level', str(lvl), proj_labeled,
                    )
                    pf_val = pf_row.get('pf_vol_avg')
                    if pf_val is not None and not (isinstance(pf_val, float) and np.isnan(pf_val)):
                        pf_pool.append(pf_val)
                    pa_val = pf_row.get('pf_area_avg')
                    if pa_val is not None and not (isinstance(pa_val, float) and np.isnan(pa_val)):
                        pf_area_pool.append(pa_val)
                    energy_sum += pf_row.get('energy_total_mj', 0.0)

            num_pozos = projected_count
            total_kg = charge_sum
            if pf_pool:
                pf_vol_avg = float(np.mean(pf_pool))
            if pf_area_pool:
                pf_area_avg = float(np.mean(pf_area_pool))
            energy_total = energy_sum

        bench_stats.append({
            'level': lvl,
            'num_pozos': num_pozos,
            'total_kg': total_kg,
            'avg_dev_crest_over': avg_dev_crest_over,
            'avg_dev_crest_under': avg_dev_crest_under,
            'avg_dev_toe_over': avg_dev_toe_over,
            'avg_dev_toe_under': avg_dev_toe_under,
            'pf_vol_avg_kgm3': pf_vol_avg,
            'pf_area_avg_kgm2': pf_area_avg,
            'energy_total_mj': energy_total,
        })

    df_b = pd.DataFrame(bench_stats)
    if df_b.empty:
        return df_b

    df_b['sort_level'] = pd.to_numeric(df_b['level'], errors='coerce').fillna(-9999)
    df_b = df_b.sort_values(by='sort_level', ascending=False).reset_index(drop=True)
    return df_b.drop(columns=['sort_level'])


def _compute_malla_correlation(sections, blast_df, df_sections, tolerance, kg_col, malla_col, fecha_corte=None) -> pd.DataFrame:
    if not malla_col or malla_col not in blast_df.columns:
        return pd.DataFrame()

    mallas = blast_df[malla_col].dropna().unique().tolist()
    pf_enriched = compute_powder_factor(blast_df) if not blast_df.empty else blast_df
    malla_stats = []

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
                proj_labeled['malla'] = str(mal)
                pf_row = aggregate_powder_factor_by_group(
                    pf_enriched, 'malla', str(mal), proj_labeled,
                )
                pf_val = pf_row.get('pf_vol_avg')
                if pf_val is not None and not (isinstance(pf_val, float) and np.isnan(pf_val)):
                    pf_pool.append(pf_val)
                energy_sum += pf_row.get('energy_total_mj', 0.0)

        avg_dev_crest_over = 0.0
        avg_dev_crest_under = 0.0
        avg_dev_toe_over = 0.0
        avg_dev_toe_under = 0.0
        avg_overbreak = 0.0

        if intersected_sections:
            df_sec_match = df_sections[df_sections['section'].isin(intersected_sections)]
            if not df_sec_match.empty:
                if 'avg_over_break' in df_sec_match.columns:
                    avg_overbreak = df_sec_match['avg_over_break'].mean()
                else:
                    avg_overbreak = df_sec_match['area_over'].mean()

            comparison_results = st.session_state.get('comparison_results', [])
            if comparison_results:
                df_comps = pd.DataFrame(comparison_results)
                df_comps_match = df_comps[df_comps['section'].isin(intersected_sections)]
                if not df_comps_match.empty:
                    if 'delta_crest' in df_comps_match.columns:
                        dc = df_comps_match['delta_crest'].dropna()
                        over_c = dc[dc > 0].tolist()
                        under_c = dc[dc < 0].tolist()
                        if over_c:
                            avg_dev_crest_over = float(np.mean(over_c))
                        if under_c:
                            avg_dev_crest_under = float(np.mean(under_c))
                    if 'delta_toe' in df_comps_match.columns:
                        dt = df_comps_match['delta_toe'].dropna()
                        over_t = dt[dt > 0].tolist()
                        under_t = dt[dt < 0].tolist()
                        if over_t:
                            avg_dev_toe_over = float(np.mean(over_t))
                        if under_t:
                            avg_dev_toe_under = float(np.mean(under_t))

        pf_vol_avg = float(np.mean(pf_pool)) if pf_pool else float('nan')
        malla_stats.append({
            'malla': str(mal),
            'num_pozos': num_pozos,
            'total_kg': total_kg,
            'avg_dev_crest_over': avg_dev_crest_over,
            'avg_dev_crest_under': avg_dev_crest_under,
            'avg_dev_toe_over': avg_dev_toe_over,
            'avg_dev_toe_under': avg_dev_toe_under,
            'avg_overbreak': avg_overbreak,
            'pf_vol_avg_kgm3': pf_vol_avg,
            'energy_total_mj': energy_sum,
        })

    return pd.DataFrame(malla_stats).reset_index(drop=True)
