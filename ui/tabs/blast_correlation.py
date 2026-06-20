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
from core.blast_model import (
    compute_energy_density_along_profile,
    compute_pasadura_toe_correlation,
    fit_powder_factor_damage_model,
    predict_damage_for_pf,
)
from core.config import ADVISOR, DEFAULTS
from core.geom_utils import calculate_area_between_profiles, find_df_column
from core.section_cutter import cut_both_surfaces
from ui.filter_cache import _ensure_filter_values
from ui.tabs.export import _get_profile_pair
try:
    from core.blast_advisor import (
        format_recommendation_text,
        recommend_by_sector,
        recommend_pf_adjustment,
    )
    _HAS_BLAST_ADVISOR = True
except ImportError:
    _HAS_BLAST_ADVISOR = False

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

    model, valid = _render_powder_factor_damage_model(df_filtered_sections, use_pf_axis)
    _render_pf_recommendations(model, valid, df_filtered_sections)

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

            with st.expander("⚡ Densidad de Energía (IDW) a lo largo de la sección", expanded=False):
                _render_energy_density_along_profile(
                    blast_df, sections, mesh_design, mesh_topo,
                    cuts_cache_key=None,
                    tolerance=tolerance, fecha_corte=fecha_corte_str,
                )

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

            _render_pasadura_toe_block(blast_df, comparison_results)

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


def _render_powder_factor_damage_model(df_filtered_sections: pd.DataFrame, use_pf_axis: bool) -> tuple:
    """OLS regression: powder factor vs mean overbreak per section.

    Renders β₁, p-value, R², n, 95% CI and a confidence label. Also exposes
    a scenario slider that calls ``predict_damage_for_pf`` so the user can
    answer "¿qué pasa si subo/bajo el PF objetivo?" interactively.

    Returns
    -------
    tuple
        ``(model, valid)`` where ``model`` is the fitted regression dict
        (or ``None`` when fitting was skipped) and ``valid`` is the cleaned
        DataFrame used for fitting (or ``None`` when no data was
        available). Callers can use the returned ``model`` to render
        downstream recommendations without re-fitting.
    """
    st.markdown("---")
    with st.expander("📈 Modelo Cuantitativo: PF → Sobre-excavación", expanded=True):
        st.markdown(
            "Regresión lineal OLS sobre la base de datos filtrada: "
            "`Sobre-excavación = β₀ + β₁ · PF + ε`. La pendiente β₁ "
            "expresa cuántos metros de sobre-excavación se asocian, en "
            "promedio, a cada kg/m³ adicional de powder factor."
        )

        if not use_pf_axis:
            st.info("ℹ️ Powder factor no disponible: faltan columnas de burden/espaciamiento. No es posible ajustar el modelo.")
            return None, None

        valid = df_filtered_sections.dropna(subset=['pf_vol_avg_kgm3', 'avg_over_break']).copy()
        valid = valid[valid['pf_vol_avg_kgm3'] > 0]
        pf = valid['pf_vol_avg_kgm3'].values.astype(float)
        dmg = valid['avg_over_break'].values.astype(float)

        if len(pf) < 5:
            st.info(f"Datos insuficientes (n={len(pf)} < 5). Necesitas más secciones con PF válido para ajustar el modelo.")
            return None, valid

        model = fit_powder_factor_damage_model(pf, dmg)
        if not model['is_significant'] and model['confidence'] == 'INSUFFICIENT':
            st.warning(f"Modelo no confiable (confianza={model['confidence']}). Revisa que los datos tengan variabilidad real en PF.")
            return model, valid

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("β₁ (m por kg/m³)", f"{model['beta1']:.4f}")
        c2.metric("p-valor", f"{model['p_value']:.4f}")
        c3.metric("R²", f"{model['r_squared']:.3f}")
        c4.metric("Confianza", model['confidence'])
        st.caption(
            f"n = {model['n']}  |  IC 95% β₁: [{model['ci_beta1_low']:.4f}, {model['ci_beta1_high']:.4f}]"
        )

        if model['is_significant']:
            st.success(
                f"**Cada +0.1 kg/m³ de PF se asocia a {model['beta1'] * 0.1:+.3f} m de sobre-excavación** "
                f"(p = {model['p_value']:.3f}, n = {model['n']})."
            )
        else:
            st.warning(
                f"La pendiente no es estadísticamente significativa (p = {model['p_value']:.3f} ≥ 0.05). "
                "El modelo no soporta una relación causal con estos datos."
            )

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pf, y=dmg,
            mode='markers+text',
            text=valid['section'].astype(str).values,
            textposition='top center',
            marker=dict(size=10, color='crimson'),
            name='Secciones',
        ))

        xs_line = np.linspace(float(pf.min()), float(pf.max()), 50)
        ys_line = model['beta0'] + model['beta1'] * xs_line
        sse = float(np.sum((pf - model['mean_pf']) ** 2))
        if sse > 0:
            se_band = 1.96 * model['std_err_beta1'] * np.sqrt(
                1.0 / model['n'] + (xs_line - model['mean_pf']) ** 2 / sse
            )
            fig.add_trace(go.Scatter(
                x=np.concatenate([xs_line, xs_line[::-1]]),
                y=np.concatenate([ys_line + se_band, (ys_line - se_band)[::-1]]),
                fill='toself',
                fillcolor='rgba(220, 20, 60, 0.15)',
                line=dict(color='rgba(255, 255, 255, 0)'),
                hoverinfo='skip',
                showlegend=True,
                name='Banda IC 95%',
            ))
        fig.add_trace(go.Scatter(
            x=xs_line, y=ys_line,
            mode='lines',
            line=dict(color='darkred', width=2),
            name=f'OLS (β₁ = {model["beta1"]:.3f})',
        ))

        fig.update_layout(
            title="Regresión OLS: PF (kg/m³) vs Sobre-excavación Media (m)",
            xaxis_title="Powder Factor Volumétrico (kg/m³)",
            yaxis_title="Sobre-excavación Media (m)",
            height=450,
            margin=dict(l=40, r=20, t=50, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Escenario: ¿qué pasa si ajusto el PF objetivo?**")
        pf_min = float(min(0.05, pf.min()))
        pf_max = float(max(2.0, pf.max()))
        target_pf = st.slider(
            "PF objetivo (kg/m³):",
            min_value=pf_min, max_value=pf_max,
            value=float(model['mean_pf']),
            step=0.01,
            key="blast_corr_target_pf",
        )
        pred = predict_damage_for_pf(model, target_pf)
        pa, pb, pc = st.columns(3)
        pa.metric("PF objetivo", f"{target_pf:.2f} kg/m³")
        pb.metric("Sobre-excavación predicha", f"{pred['predicted_damage']:+.3f} m")
        pc.metric("Incertidumbre (±)", f"{pred['uncertainty_m']:.3f} m")

    return model, valid


def _render_pf_recommendations(
    model: dict | None,
    valid: pd.DataFrame | None,
    df_filtered_sections: pd.DataFrame,
) -> None:
    """Render PF-adjustment recommendations block (Phase 5).

    Consumes the fitted model from :func:`_render_powder_factor_damage_model`
    and emits global and per-sector actionable recommendations through
    :mod:`core.blast_advisor`. Degrades silently when the engine is not
    importable.
    """
    if not _HAS_BLAST_ADVISOR:
        return

    st.markdown("---")
    with st.expander("🎯 Recomendaciones de Ajuste de Carga", expanded=True):
        if model is None or model.get('confidence') == 'INSUFFICIENT':
            n = int(model.get('n', 0)) if model else 0
            p_val = float(model.get('p_value', float('nan'))) if model else float('nan')
            st.warning("Modelo sin confianza estadística suficiente para emitir recomendaciones cuantitativas.")
            st.caption(
                f"n={n} | p={p_val:.3f} | Se requiere n≥{ADVISOR.min_samples_for_advice} con variabilidad en PF."
            )
            return

        target_ob = st.slider(
            "Sobre-excavación objetivo (m):",
            min_value=0.1, max_value=1.5, value=ADVISOR.target_overbreak_m, step=0.05,
            help="Sobre-excavación objetivo. El motor calculará el PF necesario para alcanzarla.",
            key="advisor_target_overbreak",
        )

        if valid is None or valid.empty:
            st.info("No hay datos válidos de PF y sobre-excavación para recomendar.")
            return

        valid_pf_mean = float(valid['pf_vol_avg_kgm3'].mean())
        rec_global = recommend_pf_adjustment(
            model,
            current_pf=valid_pf_mean,
            target_overbreak_m=target_ob,
        )
        st.markdown(f"### 📊 Recomendación Global (PF promedio = {valid_pf_mean:.3f} kg/m³)")
        col_r1, col_r2, col_r3 = st.columns(3)
        col_r1.metric("ΔPF objetivo", f"{rec_global['delta_pf']:+.3f} kg/m³")
        col_r2.metric("ΔPF %", f"{rec_global['delta_pf_pct']:+.1f}%")
        col_r3.metric("Factibilidad", rec_global['feasibility'])
        st.info(format_recommendation_text(rec_global, section_name='(global)'))

        st.markdown("### 🏗️ Recomendaciones por Sector")
        if 'sector' in df_filtered_sections.columns:
            df_recs = recommend_by_sector(
                df_filtered_sections, model, group_col='sector',
                target_overbreak_m=target_ob,
            )
            if not df_recs.empty:
                st.dataframe(df_recs, use_container_width=True, height=300)
                for _, row in df_recs.iterrows():
                    if row['feasibility'] == 'APPLICABLE':
                        st.success(f"**{row['group_value']}**: {row['message']}")
                    elif row['feasibility'] == 'CAUTION':
                        st.warning(f"**{row['group_value']}**: {row['message']}")
            else:
                st.info("No hay datos suficientes para recomendaciones por sector.")
        else:
            st.info("Columna 'sector' no disponible en los datos.")


def _render_pasadura_toe_block(blast_df: pd.DataFrame, comparison_results: list) -> None:
    """Per-bench correlation between pasadura and delta_toe."""
    st.markdown("---")
    st.subheader("🔗 Pasadura → Daño del Piso (delta_toe)")

    st.markdown(
        "Agrupa los pozos por cota del piso (`Z_collar - altura_banco`) y "
        "los empareja con la `delta_toe` de la conciliación geotécnica del "
        "mismo nivel. Una correlación negativa sugiere que pasaduras "
        "cortas están asociadas a mayor sobre-excavación del piso "
        "(lomo duro)."
    )

    pas_corr = compute_pasadura_toe_correlation(
        blast_df, comparison_results, bench_height=DEFAULTS.blast_default_bench_height,
    )

    cp1, cp2, cp3 = st.columns(3)
    cp1.metric("Pearson r", f"{pas_corr['r']:.2f}")
    cp2.metric("n (bancos)", f"{pas_corr['n_benches']}")
    cp3.metric("Interpretación", pas_corr['interpretation'])

    if pas_corr['n_benches'] >= 2:
        pas_df = pd.DataFrame({
            'Nivel (cota)': list(pas_corr['pasadura_per_bench'].keys()),
            'Pasadura media (m)': list(pas_corr['pasadura_per_bench'].values()),
            'delta_toe (m)': list(pas_corr['toe_per_bench'].values()),
        }).sort_values('Nivel (cota)', ascending=False)
        st.dataframe(pas_df, use_container_width=True, height=200)

    if pas_corr['r'] < -0.3:
        st.warning(
            f"📉 Correlación negativa (r = {pas_corr['r']:.2f}): pozos con menor "
            "pasadura → mayor sobre-excavación del piso. Confirma hipótesis de lomo duro."
        )
    elif pas_corr['r'] > 0.3:
        st.info(
            f"📈 Correlación positiva (r = {pas_corr['r']:.2f}): pasaduras largas se "
            "asocian a mayor sobre-excavación del piso. Revisa si hay sobreperforación."
        )


def _render_energy_density_along_profile(
    blast_df: pd.DataFrame,
    sections: list,
    mesh_design,
    mesh_topo,
    cuts_cache_key: tuple,
    tolerance: float,
    fecha_corte: str,
) -> None:
    """Per-section expander: IDW energy density sampled along the topo profile."""
    if not sections or mesh_design is None or mesh_topo is None or blast_df is None or blast_df.empty:
        return

    sec_options = [s.name for s in sections]
    sel_sec_name = st.selectbox(
        "Sección para muestrear densidad de energía:",
        sec_options,
        key="blast_corr_idw_section",
    )
    sel_sec = next((s for s in sections if s.name == sel_sec_name), None)
    if sel_sec is None:
        return

    pd_prof, pt_prof = _get_profile_pair(sel_sec_name)
    if pd_prof is None or pt_prof is None:
        pd_prof, pt_prof = cut_both_surfaces(mesh_design, mesh_topo, sel_sec)
    if not pt_prof or not pt_prof.distances.size:
        st.info("No hay perfil topográfico disponible para esta sección.")
        return

    direction = np.array([np.sin(np.radians(sel_sec.azimuth)),
                         np.cos(np.radians(sel_sec.azimuth))])
    profile_xs = sel_sec.origin[0] + pt_prof.distances * direction[0]
    profile_ys = sel_sec.origin[1] + pt_prof.distances * direction[1]
    z_sample = float(np.nanmean(pt_prof.elevations)) if pt_prof.elevations.size else 0.0

    proj = proyectar_pozos_en_seccion(
        blast_df, origin=sel_sec.origin, azimuth=sel_sec.azimuth,
        length=sel_sec.length, tolerance=tolerance, fecha_corte=fecha_corte,
    )
    local_df = proj if not proj.empty else blast_df

    energy = compute_energy_density_along_profile(
        local_df, pt_prof.distances, profile_xs, profile_ys, z_sample=z_sample,
        search_radius=DEFAULTS.blast_correlation_radius_m,
    )

    fig = go.Figure()
    if pd_prof and pd_prof.distances.size:
        fig.add_trace(go.Scatter(
            x=pd_prof.distances, y=pd_prof.elevations,
            mode='lines', line=dict(color='royalblue', width=2),
            name='Diseño',
        ))
    fig.add_trace(go.Scatter(
        x=pt_prof.distances, y=pt_prof.elevations,
        mode='lines', line=dict(color='forestgreen', width=2),
        name='Topografía',
    ))
    fig.add_trace(go.Scatter(
        x=pt_prof.distances, y=energy,
        mode='lines', line=dict(color='crimson', width=2),
        name='Energía IDW (kg/m²)',
        yaxis='y2',
    ))
    fig.update_layout(
        title=f"Densidad de Energía (IDW) — {sel_sec_name}",
        xaxis_title="Distancia a lo largo de la sección (m)",
        yaxis=dict(title="Elevación (m)", color='forestgreen'),
        yaxis2=dict(
            title="Energía (kg/m²)", overlaying='y', side='right',
            color='crimson',
        ),
        height=450,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(x=0.01, y=0.99),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Energía acumulada por punto, radio de búsqueda = {DEFAULTS.blast_correlation_radius_m:.0f} m, "
        f"z de muestreo = {z_sample:.1f} m."
    )
