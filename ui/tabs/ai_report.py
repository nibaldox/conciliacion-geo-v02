"""
Results tab: AI-generated executive report via streaming.
"""
import pandas as pd
import streamlit as st


def render_tab_ai(config: dict) -> None:
    st.subheader("🤖 Informe Ejecutivo (IA)")

    if not config['ai_enabled']:
        st.info("Habilita el Asistente IA en la configuración (barra lateral) "
                "para generar informes automáticos.")
        return

    if not st.button("📝 Generar Informe Ejecutivo", type="primary"):
        return

    from core.ai_reporter import generate_geotech_report

    df_final = pd.DataFrame(st.session_state.comparison_results)
    if df_final.empty:
        st.warning("No hay resultados para analizar.")
        return

    n_total = len(df_final)
    n_compliant_h = len(df_final[df_final['height_status'] == "CUMPLE"])
    n_compliant_a = len(df_final[df_final['angle_status'] == "CUMPLE"])
    n_compliant_b = len(df_final[df_final['berm_status'] == "CUMPLE"])

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
    }

    st.markdown("### ⏳ Analizando datos y redactando informe...")
    report_container = st.empty()
    full_report = ""

    for chunk in generate_geotech_report(
            ai_stats, config['api_key'], config['model_name'], config['base_url']):
        full_report += (chunk or "")
        report_container.markdown(full_report + "▌")

    report_container.markdown(full_report)
