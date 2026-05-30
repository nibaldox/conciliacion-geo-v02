"""
Results tab: AI-generated executive report via streaming.
"""
import pandas as pd
import streamlit as st


def render_tab_ai(config: dict) -> None:
    df_final = pd.DataFrame(st.session_state.comparison_results)
    if df_final.empty:
        st.warning("No hay resultados para analizar.")
        return

    # Unconditional Local Advisory Engine
    _render_local_blast_advisory(df_final)
    st.markdown("---")

    st.subheader("🤖 Informe Ejecutivo (IA)")
    if not config['ai_enabled']:
        st.info("Habilita el Asistente IA en la configuración (barra lateral) "
                "para generar informes automáticos.")
        return

    if not st.button("📝 Generar Informe Ejecutivo", type="primary"):
        return

    from core.ai_reporter import generate_geotech_report

    n_total = len(df_final)
    n_compliant_h = len(df_final[df_final['height_status'] == "CUMPLE"])
    n_compliant_a = len(df_final[df_final['angle_status'] == "CUMPLE"])
    n_compliant_b = len(df_final[df_final['berm_status'] == "CUMPLE"])

    # Calculate Drill & Blast Stats
    blast_df = st.session_state.get('blast_df_clean')
    blast_stats = {}
    if blast_df is not None and not blast_df.empty:
        pasadura = (blast_df['Z_collar'] - 15.0) - blast_df['Z_toe']
        p_mean = pasadura.mean()
        p_optimal = ((pasadura >= 0.5) & (pasadura <= 1.5)).sum()
        p_pct = p_optimal / len(blast_df) * 100 if len(blast_df) > 0 else 0

        # Calculate correlation coefficient r if geotech results exist
        from core.calculo_tronadura import proyectar_pozos_en_seccion
        from core.geom_utils import find_df_column
        comparison = st.session_state.get('comparison_results', [])
        sections = st.session_state.get('sections', [])

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
            'Cumplimiento Altura':
                f"{n_compliant_h}/{n_total} ({n_compliant_h/n_total:.1%})",
            'Cumplimiento Ángulo':
                f"{n_compliant_a}/{n_total} ({n_compliant_a/n_total:.1%})",
            'Cumplimiento Berma':
                f"{n_compliant_b}/{n_total} ({n_compliant_b/n_total:.1%})",
        },
        'blast_stats': blast_stats
    }

    st.markdown("### ⏳ Analizando datos y redactando informe...")
    report_container = st.empty()
    full_report = ""

    for chunk in generate_geotech_report(
            ai_stats, config['api_key'], config['model_name'], config['base_url']):
        full_report += (chunk or "")
        report_container.markdown(full_report + "▌")

    report_container.markdown(full_report)


def _render_local_blast_advisory(df_final: pd.DataFrame) -> None:
    blast_df = st.session_state.get('blast_df_clean')
    if blast_df is None or blast_df.empty:
        return

    st.subheader("🔬 Diagnóstico de Perforación y Voladura")

    # Calculate average pasadura
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

                proj = proyectar_pozos_en_seccion(
                    blast_df,
                    origin=sec.origin,
                    azimuth=sec.azimuth,
                    length=sec.length,
                    tolerance=15.0
                )
                if not proj.empty:
                    total_kg = proj[kg_col].fillna(0).sum()
                    if avg_dev > 1.0 and total_kg > 2000:
                        st.info(f"💡 **Recomendación Voladura en {sec_name}**: Se registra daño severo en el talud ({avg_dev:.2f}m) junto con una alta concentración de carga cercana ({total_kg:.0f} Kg). Se sugiere aumentar el espaciamiento de pre-corte en un 10% o reducir el factor de carga en las primeras filas de producción.")
                        has_alert = True

    if not has_alert:
        st.success("✅ **Estabilidad Operativa**: No se detectan anomalías críticas de correlación energía-daño o desviaciones extremas de pasadura en los bancos analizados.")
