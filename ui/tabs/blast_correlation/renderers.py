"""Streamlit renderers for the blast-correlation tab."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.blast_advisor import format_recommendation_text
from core.config import ADVISOR, BACKBREAK, DEFAULTS
from core.geom_utils import find_df_column
from ui.filter_cache import _ensure_filter_values
from ui.tabs.blast_correlation import backbreak, blocks, data, energy, multivariate, powder_factor, state, temporal


def render_tab_blast_correlation(config: dict) -> None:
    blast_df = state.get_blast_df()
    comparison_results = state.get_comparison_results()
    sections = state.get_sections()
    mesh_design = state.get_mesh_design()
    mesh_topo = state.get_mesh_topo()

    if blast_df is None or blast_df.empty:
        st.warning(
            "⚠️ No se han cargado datos de pozos de tronadura. Por favor, suba el archivo de pozos de tronadura en el Módulo de Tronadura para activar este análisis."
        )
        return

    if not comparison_results or not sections or mesh_design is None or mesh_topo is None:
        st.warning(
            "⚠️ Datos de conciliación insuficientes. Asegúrese de haber generado las secciones y ejecutado la conciliación en los pasos anteriores."
        )
        return

    st.subheader("💥 Correlación Geotécnica vs Carga Explosiva (Perforación y Voladura)")
    st.markdown(
        "Esta pestaña permite evaluar cuantitativamente el impacto de la energía explosiva "
        "en las desviaciones de sobre-excavación y deuda de material en los bancos, sectores y mallas."
    )

    tolerance = st.slider(
        "Tolerancia de Proyección de Pozos a la Sección (m):",
        min_value=5.0,
        max_value=30.0,
        value=DEFAULTS.blast_correlation_radius_m,
        step=1.0,
        key="corr_projection_tolerance",
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
            st.warning(
                "⚠️ No se ha indicado fecha de levantamiento: la correlación puede incluir pozos tronados después del levantamiento, generando resultados espurios."
            )
    else:
        st.info("ℹ️ Filtro temporal desactivado: la correlación puede incluir pozos tronados después del levantamiento.")

    fecha_corte_str = fecha_levantamiento.isoformat() if fecha_levantamiento else None

    cut_cache_key, full_cache_key = data.build_section_cache_keys(
        sections, blast_df, tolerance, fecha_corte_str
    )
    df_sections_calc = state.get_cached_sections_data(full_cache_key)
    if df_sections_calc is None:
        cuts_cache = state.get_cached_cuts(cut_cache_key)
        df_sections_calc, cuts_cache = data.compute_sections_data(
            sections,
            mesh_design,
            mesh_topo,
            blast_df,
            comparison_results,
            tolerance,
            fecha_corte_str,
            cuts_cache,
        )
        state.set_cuts_cache(cut_cache_key, cuts_cache)
        state.set_sections_cache(full_cache_key, df_sections_calc)

    with st.expander("🔎 Filtros del Análisis de Correlación", expanded=True):
        cols_filter = st.columns(3)
        all_sectors = sorted(df_sections_calc["sector"].unique().tolist())
        sel_sectors = cols_filter[0].multiselect(
            "Filtrar por Sector:", all_sectors, default=[], key="corr_filter_sector"
        )

        kg_col = data.get_kg_col(blast_df)
        malla_col = data.get_malla_col(blast_df)

        all_mallas = []
        if malla_col and malla_col in blast_df.columns:
            all_mallas = sorted(blast_df[malla_col].dropna().unique().tolist())
        sel_mallas = cols_filter[1].multiselect(
            "Filtrar por Malla/Polígono:", all_mallas, default=[], key="corr_filter_malla"
        )

        unique_levels = _ensure_filter_values()["levels"]
        sel_levels = cols_filter[2].multiselect(
            "Filtrar por Nivel/Cota:", unique_levels, default=[], key="corr_filter_level"
        )

    df_filtered_sections = df_sections_calc.copy()
    if sel_sectors:
        df_filtered_sections = df_filtered_sections[df_filtered_sections["sector"].isin(sel_sectors)]

    df_filtered_comps = pd.DataFrame(comparison_results)
    if sel_sectors:
        df_filtered_comps = df_filtered_comps[df_filtered_comps["sector"].isin(sel_sectors)]
    if sel_levels:
        df_filtered_comps = df_filtered_comps[df_filtered_comps["level"].isin(sel_levels)]

    st.markdown("---")

    col_metrics = st.columns(4)
    tot_pozos = int(df_filtered_sections["num_pozos"].sum())
    tot_charge = df_filtered_sections["total_kg"].sum()
    avg_overbreak = df_filtered_sections["area_over"].mean()

    use_pf_axis = (
        "pf_vol_avg_kgm3" in df_filtered_sections.columns
        and not df_filtered_sections["_pf_unavailable"].iloc[0]
        if not df_filtered_sections.empty
        else False
    )

    r_coef = 0.0
    r_text = "Insuficientes datos"
    r_label = "Correlación Carga vs Daño"
    if len(df_filtered_sections) > 1:
        if use_pf_axis:
            x_vals = (
                pd.to_numeric(df_filtered_sections["pf_vol_avg_kgm3"], errors="coerce")
                .fillna(0)
                .values.astype(float)
            )
            x_label = "Powder Factor (kg/m³)"
        else:
            x_vals = df_filtered_sections["total_kg"].values.astype(float)
            x_label = "Carga Explosiva (Kg crudo)"
            r_label = "Correlación Carga (kg) vs Daño"
        y_vals = df_filtered_sections["area_over"].values.astype(float)
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

    if not df_filtered_sections.empty and bool(df_filtered_sections["_pf_unavailable"].iloc[0]):
        st.info("ℹ️ Powder factor no disponible: faltan columnas de burden/espaciamiento en el archivo de pozos.")

    model, valid = _render_powder_factor_damage_model(df_filtered_sections, use_pf_axis)
    _render_pf_recommendations(model, valid, df_filtered_sections)
    mv_model = _render_multivariate_model(df_filtered_sections)
    _render_backbreak_predictor(df_filtered_sections, mv_model)
    _render_temporal_analysis(blast_df, df_filtered_sections)

    tab_sec, tab_bnc, tab_mal = st.tabs(
        [
            "📐 Análisis por Sección / Perfil",
            "🧱 Análisis por Banco / Nivel",
            "🕸️ Análisis por Malla / Polígono",
        ]
    )

    with tab_sec:
        _render_section_tab(
            df_filtered_sections,
            blast_df,
            sections,
            mesh_design,
            mesh_topo,
            use_pf_axis,
            tolerance,
            fecha_corte_str,
        )

    with tab_bnc:
        _render_bench_tab(
            blast_df,
            comparison_results,
            sections,
            df_filtered_comps,
            tolerance,
            kg_col,
            fecha_corte_str,
        )

    with tab_mal:
        _render_malla_tab(
            sections,
            blast_df,
            df_sections_calc,
            df_filtered_sections,
            tolerance,
            kg_col,
            malla_col,
            comparison_results,
            fecha_corte_str,
            sel_mallas,
        )


def _render_section_tab(
    df_filtered_sections: pd.DataFrame,
    blast_df: pd.DataFrame,
    sections: list,
    mesh_design,
    mesh_topo,
    use_pf_axis: bool,
    tolerance: float,
    fecha_corte_str: str | None,
) -> None:
    st.markdown("#### Distribución de Energía y Desviación por Sección Transversal")

    col_list = [
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
    ]
    col_list = [c for c in col_list if c in df_filtered_sections.columns]
    display_map = {
        "section": "Sección",
        "sector": "Sector",
        "num_pozos": "Pozos Proyectados",
        "total_kg": "Carga Explosiva (Kg)",
        "area_over": "Sobre-excavación (m²)",
        "area_under": "Deuda / Relleno (m²)",
        "avg_over_break": "Sobre-excavación Media (m)",
        "avg_under_break": "Deuda / Relleno Media (m)",
        "pf_vol_avg_kgm3": "PF Vol. (kg/m³)",
        "pf_area_avg_kgm2": "PF Área (kg/m²)",
        "energy_total_mj": "Energía (MJ)",
    }
    df_sec_disp = df_filtered_sections[col_list].rename(columns=display_map)
    st.dataframe(df_sec_disp, width="stretch", height=300)

    if len(df_filtered_sections) > 1:
        if use_pf_axis:
            x_axis = "pf_vol_avg_kgm3"
            x_label = "Powder Factor Volumétrico (kg/m³)"
            title = "Correlación: Powder Factor (kg/m³) vs Sobre-excavación Media"
        else:
            x_axis = "total_kg"
            x_label = "Carga Explosiva Proyectada (Kg) — fallback sin PF"
            title = "Correlación: Carga Explosiva (Kg) vs Sobre-excavación Media"

        x_for_var = (
            pd.to_numeric(df_filtered_sections[x_axis], errors="coerce")
            .fillna(0)
            .values.astype(float)
        )
        try:
            import statsmodels  # noqa: F401

            _HAS_STATSMODELS = True
        except ImportError:
            _HAS_STATSMODELS = False
        trendline = (
            "ols"
            if _HAS_STATSMODELS and len(df_filtered_sections) > 2 and np.var(x_for_var) > 0
            else None
        )
        fig_scatter = px.scatter(
            df_filtered_sections,
            x=x_axis,
            y="avg_over_break",
            color="sector",
            hover_name="section",
            labels={
                x_axis: x_label,
                "avg_over_break": "Sobre-excavación Media (m)",
                "sector": "Sector",
            },
            title=title,
            trendline=trendline,
        )
        fig_scatter.update_layout(height=450)
        st.plotly_chart(fig_scatter, width="stretch")
        if not use_pf_axis:
            st.caption("⚠️ Scatter con Kg crudo: powder factor no disponible (faltan columnas de burden/espaciamiento).")

        with st.expander("⚡ Densidad de Energía (IDW) a lo largo de la sección", expanded=False):
            _render_energy_density_along_profile(
                blast_df,
                sections,
                mesh_design,
                mesh_topo,
                tolerance=tolerance,
                fecha_corte=fecha_corte_str,
            )


def _render_bench_tab(
    blast_df: pd.DataFrame,
    comparison_results: list,
    sections: list,
    df_filtered_comps: pd.DataFrame,
    tolerance: float,
    kg_col: str | None,
    fecha_corte_str: str | None,
) -> None:
    st.markdown("#### Comportamiento Horizontal por Banco / Nivel de Cota")

    df_bench_corr = data.compute_bench_correlation(
        sections, blast_df, df_filtered_comps, tolerance, kg_col, fecha_corte_str
    )
    if df_bench_corr.empty:
        st.info("No hay datos de bancos para los filtros seleccionados.")
        return

    col_list_b = [
        "level",
        "num_pozos",
        "total_kg",
        "avg_dev_crest_over",
        "avg_dev_crest_under",
        "avg_dev_toe_over",
        "avg_dev_toe_under",
        "pf_vol_avg_kgm3",
        "energy_total_mj",
    ]
    col_list_b = [c for c in col_list_b if c in df_bench_corr.columns]
    display_map_b = {
        "level": "Nivel / Cota",
        "num_pozos": "Cantidad de Pozos",
        "total_kg": "Carga Explosiva (Kg)",
        "avg_dev_crest_over": "Sobre-quiebre Cresta (m)",
        "avg_dev_crest_under": "Deuda Cresta (m)",
        "avg_dev_toe_over": "Sobre-quiebre Pata (m)",
        "avg_dev_toe_under": "Deuda Pata (m)",
        "pf_vol_avg_kgm3": "PF Vol. (kg/m³)",
        "energy_total_mj": "Energía (MJ)",
    }
    df_b_disp = df_bench_corr[col_list_b].rename(columns=display_map_b)
    st.dataframe(df_b_disp, width="stretch", height=300)

    fig_bench = go.Figure()
    fig_bench.add_trace(
        go.Bar(
            x=df_bench_corr["level"],
            y=df_bench_corr["total_kg"],
            name="Carga Explosiva (Kg)",
            marker_color="crimson",
            yaxis="y",
        )
    )
    fig_bench.add_trace(
        go.Scatter(
            x=df_bench_corr["level"],
            y=df_bench_corr["avg_dev_crest_over"],
            name="Sobre-quiebre Cresta (m)",
            mode="lines+markers",
            line=dict(color="darkorange", width=3),
            yaxis="y2",
        )
    )
    fig_bench.add_trace(
        go.Scatter(
            x=df_bench_corr["level"],
            y=df_bench_corr["avg_dev_crest_under"],
            name="Deuda Cresta (m)",
            mode="lines+markers",
            line=dict(color="steelblue", width=3, dash="dash"),
            yaxis="y2",
        )
    )
    if "pf_vol_avg_kgm3" in df_bench_corr.columns:
        pf_vals = pd.to_numeric(df_bench_corr["pf_vol_avg_kgm3"], errors="coerce")
        if pf_vals.notna().any():
            fig_bench.add_trace(
                go.Scatter(
                    x=df_bench_corr["level"],
                    y=pf_vals,
                    name="Powder Factor Vol. (kg/m³)",
                    mode="lines+markers",
                    line=dict(color="mediumvioletred", width=2, dash="dot"),
                    yaxis="y3",
                )
            )

    yaxis3_cfg = {}
    if "pf_vol_avg_kgm3" in df_bench_corr.columns:
        yaxis3_cfg = dict(
            title=dict(text="Powder Factor (kg/m³)", font=dict(color="mediumvioletred")),
            tickcolor="mediumvioletred",
            overlaying="y",
            side="right",
            anchor="x",
            position=0.97,
        )

    fig_bench.update_layout(
        title="Relación Carga Explosiva vs Desviación de Cresta por Banco (con signo)",
        xaxis=dict(title="Nivel de Banco (Cota)", type="category"),
        yaxis=dict(
            title=dict(text="Carga Explosiva Total (Kg)", font=dict(color="crimson")),
            tickcolor="crimson",
        ),
        yaxis2=dict(
            title=dict(
                text="Desviación de Cresta Media (m, con signo)",
                font=dict(color="darkorange"),
            ),
            tickcolor="darkorange",
            overlaying="y",
            side="right",
            zeroline=True,
            zerolinecolor="gray",
            zerolinewidth=1,
        ),
        height=450,
        legend=dict(x=0.01, y=0.99),
    )
    if yaxis3_cfg:
        fig_bench.update_layout(yaxis3=yaxis3_cfg)
    st.plotly_chart(fig_bench, width="stretch")

    _render_pasadura_toe_block(blast_df, comparison_results)
    _render_stemming_crest_block(blast_df, comparison_results)
    attribution_results = blocks.build_attribution_data(
        blast_df, comparison_results, sections, tolerance
    )
    _render_attribution_block(attribution_results)


def _render_malla_tab(
    sections: list,
    blast_df: pd.DataFrame,
    df_sections: pd.DataFrame,
    df_filtered_sections: pd.DataFrame,
    tolerance: float,
    kg_col: str | None,
    malla_col: str | None,
    comparison_results: list,
    fecha_corte_str: str | None,
    sel_mallas: list,
) -> None:
    st.markdown("#### Evaluación de Daño Geotécnico por Malla / Polígono de Tronadura")

    df_malla_corr, global_score_pct = data.compute_malla_correlation(
        sections,
        blast_df,
        df_sections,
        tolerance,
        kg_col,
        malla_col,
        comparison_results,
        fecha_corte_str,
    )
    if df_malla_corr.empty:
        st.info("No se identificaron mallas o polígonos de tronadura válidos en los datos cargados.")
        return

    if sel_mallas:
        df_malla_corr = df_malla_corr[df_malla_corr["malla"].isin(sel_mallas)]

    col_list_m = [
        "malla",
        "num_pozos",
        "total_kg",
        "avg_dev_crest_over",
        "avg_dev_crest_under",
        "avg_dev_toe_over",
        "avg_dev_toe_under",
        "avg_overbreak",
        "pf_vol_avg_kgm3",
        "energy_total_mj",
        "score_pct",
    ]
    col_list_m = [c for c in col_list_m if c in df_malla_corr.columns]
    display_map_m = {
        "malla": "Malla / Polígono",
        "num_pozos": "Cantidad de Pozos",
        "total_kg": "Carga Explosiva (Kg)",
        "avg_dev_crest_over": "Sobre-quiebre Cresta (m)",
        "avg_dev_crest_under": "Deuda Cresta (m)",
        "avg_dev_toe_over": "Sobre-quiebre Pata (m)",
        "avg_dev_toe_under": "Deuda Pata (m)",
        "avg_overbreak": "Sobre-excavación Media (m)",
        "pf_vol_avg_kgm3": "PF Vol. (kg/m³)",
        "energy_total_mj": "Energía (MJ)",
        "score_pct": "Logro Diseño (%)",
    }
    st.metric("Logro Diseño Global", f"{global_score_pct}%")
    df_m_disp = df_malla_corr[col_list_m].rename(columns=display_map_m)
    st.dataframe(df_m_disp, width="stretch", height=300)

    color_axis = (
        "pf_vol_avg_kgm3"
        if "pf_vol_avg_kgm3" in df_malla_corr.columns
        and df_malla_corr["pf_vol_avg_kgm3"].notna().any()
        else "total_kg"
    )
    color_label = (
        "Powder Factor (kg/m³)"
        if color_axis == "pf_vol_avg_kgm3"
        else "Carga Explosiva Total (Kg)"
    )
    fig_malla = px.bar(
        df_malla_corr,
        x="malla",
        y="avg_overbreak",
        color=color_axis,
        color_continuous_scale="YlOrRd",
        labels={
            "malla": "Malla de Tronadura",
            "avg_overbreak": "Área de Sobre-excavación Promedio (m²)",
            color_axis: color_label,
        },
        title="Área de Sobre-excavación Promedio por Malla de Tronadura",
    )
    fig_malla.update_layout(height=450)
    st.plotly_chart(fig_malla, width="stretch")


def _render_powder_factor_damage_model(df_filtered_sections: pd.DataFrame, use_pf_axis: bool):
    st.markdown("---")
    with st.expander("📈 Modelo Cuantitativo: PF → Sobre-excavación", expanded=True):
        st.markdown(
            "Regresión lineal OLS sobre la base de datos filtrada: "
            "`Sobre-excavación = β₀ + β₁ · PF + ε`. La pendiente β₁ "
            "expresa cuántos metros de sobre-excavación se asocian, en "
            "promedio, a cada kg/m³ adicional de powder factor."
        )

        result = powder_factor.fit_pf_damage_model(df_filtered_sections, use_pf_axis)
        model = result["model"]
        valid = result["valid"]
        fig = result["fig"]
        error = result["error"]

        if error == "pf_unavailable":
            st.info("ℹ️ Powder factor no disponible: faltan columnas de burden/espaciamiento. No es posible ajustar el modelo.")
            return None, None
        if error == "insufficient":
            st.info(f"Datos insuficientes (n={len(valid)} < 5). Necesitas más secciones con PF válido para ajustar el modelo.")
            return None, valid
        if error == "unreliable":
            st.warning(f"Modelo no confiable (confianza={model['confidence']}). Revisa que los datos tengan variabilidad real en PF.")
            return model, valid

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("β₁ (m por kg/m³)", f"{model['beta1']:.4f}")
        c2.metric("p-valor", f"{model['p_value']:.4f}")
        c3.metric("R²", f"{model['r_squared']:.3f}")
        c4.metric("Confianza", model["confidence"])
        st.caption(
            f"n = {model['n']}  |  IC 95% β₁: [{model['ci_beta1_low']:.4f}, {model['ci_beta1_high']:.4f}]"
        )

        if model["is_significant"]:
            st.success(
                f"**Cada +0.1 kg/m³ de PF se asocia a {model['beta1'] * 0.1:+.3f} m de sobre-excavación** "
                f"(p = {model['p_value']:.3f}, n = {model['n']})."
            )
        else:
            st.warning(
                f"La pendiente no es estadísticamente significativa (p = {model['p_value']:.3f} ≥ 0.05). "
                "El modelo no soporta una relación causal con estos datos."
            )

        st.plotly_chart(fig, width="stretch")

        st.markdown("**Escenario: ¿qué pasa si ajusto el PF objetivo?**")
        target_pf = st.slider(
            "PF objetivo (kg/m³):",
            min_value=result["pf_min"],
            max_value=result["pf_max"],
            value=float(model["mean_pf"]),
            step=0.01,
            key="blast_corr_target_pf",
        )
        pred = powder_factor.predict_pf_damage(model, target_pf)
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
    st.markdown("---")
    with st.expander("🎯 Recomendaciones de Ajuste de Carga", expanded=True):
        if model is None or model.get("confidence") == "INSUFFICIENT":
            n = int(model.get("n", 0)) if model else 0
            p_val = float(model.get("p_value", float("nan"))) if model else float("nan")
            st.warning("Modelo sin confianza estadística suficiente para emitir recomendaciones cuantitativas.")
            st.caption(
                f"n={n} | p={p_val:.3f} | Se requiere n≥{ADVISOR.min_samples_for_advice} con variabilidad en PF."
            )
            return

        if valid is None or valid.empty:
            st.info("No hay datos válidos de PF y sobre-excavación para recomendar.")
            return

        target_ob = st.slider(
            "Sobre-excavación objetivo (m):",
            min_value=0.1,
            max_value=1.5,
            value=ADVISOR.target_overbreak_m,
            step=0.05,
            help="Sobre-excavación objetivo. El motor calculará el PF necesario para alcanzarla.",
            key="advisor_target_overbreak",
        )

        rec_result = powder_factor.build_pf_recommendations(
            model,
            valid,
            df_filtered_sections,
            target_ob,
        )
        if rec_result.get("error"):
            st.info("No hay datos válidos de PF y sobre-excavación para recomendar.")
            return

        rec_global = rec_result["rec_global"]
        df_recs = rec_result["df_recs"]
        valid_pf_mean = rec_result["valid_pf_mean"]

        st.markdown(f"### 📊 Recomendación Global (PF promedio = {valid_pf_mean:.3f} kg/m³)")
        col_r1, col_r2, col_r3 = st.columns(3)
        col_r1.metric("ΔPF objetivo", f"{rec_global['delta_pf']:+.3f} kg/m³")
        col_r2.metric("ΔPF %", f"{rec_global['delta_pf_pct']:+.1f}%")
        col_r3.metric("Factibilidad", rec_global["feasibility"])
        st.info(format_recommendation_text(rec_global, section_name="(global)"))

        st.markdown("### 🏗️ Recomendaciones por Sector")
        if not df_recs.empty:
            st.dataframe(df_recs, width="stretch", height=300)
            for row in df_recs.itertuples(index=False):
                if row.feasibility == "APPLICABLE":
                    st.success(f"**{row.group_value}**: {row.message}")
                elif row.feasibility == "CAUTION":
                    st.warning(f"**{row.group_value}**: {row.message}")
        else:
            st.info("No hay datos suficientes para recomendaciones por sector.")


def _render_multivariate_model(df_filtered_sections: pd.DataFrame):
    st.markdown("---")
    with st.expander("🧮 Modelo multivariado (PF + burden + stemming)", expanded=False):
        st.markdown(
            "Regresión lineal múltiple: "
            "`Sobre-excavación = β₀ + β_PF·PF + β_B·Burden + β_S/B·(Esp/Burden) + β_T·Taco + ε`. "
            "Aísla el efecto del burden del efecto del powder factor cuando ambas "
            "columnas están disponibles en la base de datos de pozos."
        )

        result = multivariate.build_multivariate_model(df_filtered_sections)
        model = result["model"]
        coef_rows = result["coef_rows"]
        rec = result["rec"]
        error = result["error"]

        if error == "insufficient":
            st.info(
                "ℹ️ Datos insuficientes para el modelo multivariado: se requieren al menos "
                "12 secciones con powder factor, burden, espaciamiento/burden y taco válidos."
            )
            return model

        st.dataframe(coef_rows, width="stretch", height=200)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("R²", f"{model['r_squared']:.3f}")
        c2.metric("R² ajustado", f"{model['r_squared_adj']:.3f}")
        c3.metric("p-valor (F)", f"{model['f_pvalue']:.4f}")
        c4.metric("Confianza", model["confidence"])
        st.caption(f"n = {model['n']}  |  número de condición = {model['condition_number']:.1f}")

        if model.get("collinearity_warning"):
            st.warning(f"⚠️ {model['collinearity_warning']}")

        if error == "no_burden":
            st.info("ℹ️ Burden no disponible; no es posible recomendar un ajuste de burden.")
            return model

        current_burden = float(model.get("feature_means", {}).get("burden", 0.0))
        st.markdown(f"### 🎯 Recomendación de Burden (burden actual = {current_burden:.2f} m)")
        r1, r2, r3 = st.columns(3)
        r1.metric("Burden objetivo", f"{rec['target_burden']:.2f} m")
        r2.metric("Δ Burden", f"{rec['delta_burden']:+.2f} m")
        r3.metric("Factibilidad", rec["feasibility"])
        if rec["feasibility"] == "APPLICABLE":
            st.success(rec["message"])
        else:
            st.warning(rec["message"])

    return model


def _render_backbreak_predictor(
    df_filtered_sections: pd.DataFrame,
    multivariate_model: dict | None,
) -> None:
    st.markdown("---")
    with st.expander("🔮 Predictor de Back-Break", expanded=False):
        st.markdown(
            "Estimación prospectiva del back-break esperado para un diseño de "
            "tronadura propuesto. Si el bloque anterior ajustó un modelo "
            "multivariado con suficiente confianza, la predicción usa los "
            "coeficientes calibrados con tus propios datos; de lo contrario "
            "se aplica la heurística empírica y un cross-check de "
            "Holmberg-Persson como número de sanity."
        )

        defaults = BACKBREAK

        col_a, col_b = st.columns(2)
        burden = col_a.slider(
            "Burden (m)",
            min_value=3.0,
            max_value=12.0,
            value=defaults.default_burden_m,
            step=0.1,
            key="backbreak_burden_slider",
        )
        spacing = col_b.slider(
            "Espaciamiento (m)",
            min_value=4.0,
            max_value=14.0,
            value=defaults.default_spacing_m,
            step=0.1,
            key="backbreak_spacing_slider",
        )
        col_c, col_d = st.columns(2)
        pf = col_c.slider(
            "Powder Factor (kg/m³)",
            min_value=0.10,
            max_value=1.20,
            value=defaults.pf_optimal_default_kgm3,
            step=0.05,
            key="backbreak_pf_slider",
        )
        stemming = col_d.slider(
            "Stemming (m)",
            min_value=1.0,
            max_value=12.0,
            value=defaults.default_stemming_m,
            step=0.1,
            key="backbreak_stemming_slider",
        )
        col_e, _ = st.columns(2)
        diameter = col_e.slider(
            "Diámetro (mm)",
            min_value=100,
            max_value=400,
            value=defaults.default_diameter_mm,
            step=25,
            key="backbreak_diameter_slider",
        )
        rock_factor = st.slider(
            "Factor de roca",
            min_value=defaults.rock_factor_min,
            max_value=defaults.rock_factor_max,
            value=1.0,
            step=0.05,
            key="backbreak_rock_factor_slider",
            help="Multiplicador por dureza/estructura del macizo (0.7 = blando, 1.3 = muy duro).",
        )

        try:
            pred = backbreak.compute_backbreak_prediction(
                burden,
                spacing,
                pf,
                stemming,
                diameter,
                rock_factor,
                multivariate_model,
            )
        except Exception as exc:
            st.warning(
                f"No fue posible calcular la predicción ({type(exc).__name__}). "
                "Revisa que los valores sean numéricos."
            )
            return

        m1, m2 = st.columns(2)
        m1.metric(
            "Back-break predicho",
            f"{pred.predicted_m:.2f} m",
            delta=f"IC 95% [{pred.ci_low_m:.2f}, {pred.ci_high_m:.2f}]",
        )
        method_label = (
            "Modelo multivariado" if pred.method == "multivariate" else "Heurística empírica"
        )
        m2.metric("Método", f"{method_label} · confianza {pred.confidence}")

        if pred.notes:
            with st.expander("Notas y cross-check", expanded=False):
                for n in pred.notes:
                    st.caption(f"• {n}")


def _render_pasadura_toe_block(blast_df: pd.DataFrame, comparison_results: list) -> None:
    st.markdown("---")
    st.subheader("🔗 Pasadura → Daño del Piso (delta_toe)")
    st.markdown(
        "Agrupa los pozos por cota del piso (`Z_collar - altura_banco`) y "
        "los empareja con la `delta_toe` de la conciliación geotécnica del "
        "mismo nivel. Una correlación negativa sugiere que pasaduras "
        "cortas están asociadas a mayor sobre-excavación del piso "
        "(lomo duro)."
    )

    pas_corr = blocks.build_pasadura_toe_data(blast_df, comparison_results)

    cp1, cp2, cp3 = st.columns(3)
    cp1.metric("Pearson r", f"{pas_corr['r']:.2f}")
    cp2.metric("n (bancos)", f"{pas_corr['n_benches']}")
    cp3.metric("Interpretación", pas_corr["interpretation"])

    pas_df = blocks.build_pasadura_toe_table(pas_corr)
    if not pas_df.empty:
        st.dataframe(pas_df, width="stretch", height=200)

    if pas_corr["r"] < -0.3:
        st.warning(
            f"📉 Correlación negativa (r = {pas_corr['r']:.2f}): pozos con menor "
            "pasadura → mayor sobre-excavación del piso. Confirma hipótesis de lomo duro."
        )
    elif pas_corr["r"] > 0.3:
        st.info(
            f"📈 Correlación positiva (r = {pas_corr['r']:.2f}): pasaduras largas se "
            "asocian a mayor sobre-excavación del piso. Revisa si hay sobreperforación."
        )


def _render_stemming_crest_block(blast_df: pd.DataFrame, comparison_results: list) -> None:
    st.markdown("---")
    st.subheader("🔗 Stemming → Daño de Cresta (delta_crest)")
    st.markdown(
        "Agrupa los pozos por cota del piso (`Z_collar - altura_banco`) y "
        "los empareja con la `delta_crest` de la conciliación geotécnica del "
        "mismo nivel. Una correlación negativa sugiere tacos cortos están "
        "asociados a mayor sobre-excavación de la cresta (gases venteando "
        "hacia arriba / banco soplado)."
    )

    st_corr = blocks.build_stemming_crest_data(blast_df, comparison_results)

    cs1, cs2, cs3 = st.columns(3)
    cs1.metric("Pearson r", f"{st_corr['r']:.2f}")
    cs2.metric("n (bancos)", f"{st_corr['n_benches']}")
    cs3.metric("Interpretación", st_corr["interpretation"])

    st_df = blocks.build_stemming_crest_table(st_corr)
    if not st_df.empty:
        st.dataframe(st_df, width="stretch", height=200)

    if st_corr["r"] < -0.3:
        st.warning(
            f"📉 Correlación negativa (r = {st_corr['r']:.2f}): tacos cortos → "
            "mayor sobre-excavación de cresta. Gases venteando hacia arriba, "
            "revisar longitud de taco y retacado."
        )
    elif st_corr["r"] > 0.3:
        st.info(
            f"📈 Correlación positiva (r = {st_corr['r']:.2f}): tacos largos se "
            "asocian a mayor sobre-excavación de cresta. Posible energía baja "
            "/ taco excesivo reteniendo gases."
        )


def _render_attribution_block(results: list) -> None:
    st.markdown("---")
    st.subheader("🎯 Atribución por Pozo")
    st.markdown(
        "Para cada cresta o pata con desviación significativa (|Δ| > 0.5 m) "
        "se listan los pozos dentro del radio de tolerancia, ordenados por "
        "**carga / distancia²** (IDW, mismo criterio que la densidad de "
        "energía del perfil). Permite identificar qué pozo es el "
        "responsable más probable del sobre-quiebre o la deuda observada."
    )

    if not results:
        st.info("Sin desviaciones atribuibles")
        return

    feature_labels = []
    label_to_entry = {}
    for entry in results:
        feat_es = "Cresta" if entry["feature"] == "crest" else "Pata"
        delta_m = entry["delta_m"]
        sign = "+" if delta_m > 0 else ""
        label = (
            f"{entry['section']} · Banco {entry['bench_num']} · "
            f"{feat_es} (Δ {sign}{delta_m:.2f} m)"
        )
        feature_labels.append(label)
        label_to_entry[label] = entry

    selected = st.selectbox(
        "Seleccionar feature desviado:",
        feature_labels,
        key="blast_attr_feature",
    )
    entry = label_to_entry[selected]

    df_attr = pd.DataFrame(entry["top_holes"]).rename(
        columns={
            "label_pozo": "Pozo",
            "malla": "Malla",
            "kg": "Carga (kg)",
            "distance_m": "Distancia (m)",
            "contribution_pct": "Contribución (%)",
        }
    )
    st.dataframe(df_attr, width="stretch", height=200)
    st.caption(
        f"{entry['n_candidates']} pozo(s) candidato(s) dentro del radio · "
        f"Mostrando top {len(entry['top_holes'])} ordenado por contribución "
        f"descendente."
    )


def _render_energy_density_along_profile(
    blast_df: pd.DataFrame,
    sections: list,
    mesh_design,
    mesh_topo,
    tolerance: float,
    fecha_corte: str,
) -> None:
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

    fig, z_sample = energy.build_energy_density_figure(
        blast_df,
        sel_sec,
        mesh_design,
        mesh_topo,
        tolerance,
        fecha_corte,
    )
    if fig is None:
        st.info("No hay perfil topográfico disponible para esta sección.")
        return

    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Energía acumulada por punto, radio de búsqueda = {energy.get_search_radius():.0f} m, "
        f"z de muestreo = {z_sample:.1f} m."
    )


def _render_temporal_analysis(blast_df, df_filtered_sections):
    st.markdown("---")
    with st.expander("📊 Tendencia Temporal de PF y Daño", expanded=False):
        trend_df, outliers = temporal.build_monthly_trend_data(blast_df)
        if trend_df.empty:
            st.info("Sin datos temporales disponibles (sin columna 'fecha_tronadura' con fechas válidas).")
        else:
            col_t1, col_t2 = st.columns(2)
            col_t1.metric("Meses con datos", len(trend_df))
            trend_slope = trend_df["trend_slope"].iloc[0] if "trend_slope" in trend_df.columns else np.nan
            if pd.notna(trend_slope):
                col_t2.metric("Tendencia PF (kg/m³ por mes)", f"{trend_slope:+.4f}")
            st.dataframe(trend_df, width="stretch", height=300)
            if len(trend_df) >= 2:
                st.plotly_chart(temporal.build_temporal_figure(trend_df), width="stretch")
        if not outliers.empty:
            st.warning(
                f"⚠️ {len(outliers)} pozos con PF fuera del rango IQR (1.5×): revisar carga explosiva."
            )
            preview_cols = [c for c in ["label_pozo", "pf_vol_kgm3"] if c in outliers.columns]
            if preview_cols:
                st.dataframe(outliers[preview_cols].head(10), width="stretch")

    with st.expander("🔄 Comparativa Pre/Post Campaña", expanded=False):
        campaign_date = st.date_input(
            "Fecha de inicio de campaña:", value=None, key="campaign_start_date"
        )
        if campaign_date:
            cohort = temporal.split_campaign_data(
                blast_df, campaign_date.strftime("%Y-%m-%d")
            )
            if cohort["has_campaign"]:
                before, after = cohort["before"], cohort["after"]
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("**Antes**")
                    if not before.empty:
                        pf_col_b = (
                            "pf_vol_avg_kgm3"
                            if "pf_vol_avg_kgm3" in before.columns
                            else "pf_vol_kgm3"
                            if "pf_vol_kgm3" in before.columns
                            else None
                        )
                        pf_mean_b = float(before[pf_col_b].mean()) if pf_col_b else None
                        if pf_mean_b is not None and pd.notna(pf_mean_b):
                            st.metric("PF medio", f"{pf_mean_b:.3f}")
                        st.metric("N pozos", len(before))
                    else:
                        st.info("Sin datos antes de la fecha.")
                with col_c2:
                    st.markdown("**Después**")
                    if not after.empty:
                        pf_col_a = (
                            "pf_vol_avg_kgm3"
                            if "pf_vol_avg_kgm3" in after.columns
                            else "pf_vol_kgm3"
                            if "pf_vol_kgm3" in after.columns
                            else None
                        )
                        pf_mean_a = float(after[pf_col_a].mean()) if pf_col_a else None
                        if pf_mean_a is not None and pd.notna(pf_mean_a):
                            st.metric("PF medio", f"{pf_mean_a:.3f}")
                        st.metric("N pozos", len(after))
                    else:
                        st.info("Sin datos después de la fecha.")
