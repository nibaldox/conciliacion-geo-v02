"""
Results tab: compliance dashboard with bar chart and distribution histograms.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_tab_dashboard(config: dict) -> None:
    results = st.session_state.comparison_results
    if not results:
        return

    _render_kpi_metrics(results)
    _render_stacked_bar(results)
    _render_deviation_histograms(results, config)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _render_kpi_metrics(results) -> None:
    cols = st.columns(3)
    for col, (key, label) in zip(cols, [
        ('height_status', 'Altura de Banco'),
        ('angle_status', 'Ángulo de Cara'),
        ('berm_status', 'Ancho de Berma'),
    ]):
        total = len(results)
        cumple = sum(1 for r in results if r[key] == "CUMPLE")
        pct = cumple / total * 100 if total > 0 else 0
        col.metric(label, f"{pct:.0f}%", f"{cumple}/{total} cumplen")


def _render_stacked_bar(results) -> None:
    status_counts = {'Parámetro': [], 'CUMPLE': [], 'FUERA DE TOLERANCIA': [], 'NO CUMPLE': []}
    for key, label in [
        ('height_status', 'Altura'),
        ('angle_status', 'Ángulo Cara'),
        ('berm_status', 'Berma'),
    ]:
        status_counts['Parámetro'].append(label)
        status_counts['CUMPLE'].append(sum(1 for r in results if r[key] == "CUMPLE"))
        status_counts['FUERA DE TOLERANCIA'].append(
            sum(1 for r in results if r[key] == "FUERA DE TOLERANCIA"))
        status_counts['NO CUMPLE'].append(sum(1 for r in results if r[key] == "NO CUMPLE"))

    df_status = pd.DataFrame(status_counts)
    fig_bar = go.Figure([
        go.Bar(name='CUMPLE', x=df_status['Parámetro'], y=df_status['CUMPLE'],
               marker_color='#006100'),
        go.Bar(name='FUERA TOL.', x=df_status['Parámetro'],
               y=df_status['FUERA DE TOLERANCIA'], marker_color='#9C5700'),
        go.Bar(name='NO CUMPLE', x=df_status['Parámetro'], y=df_status['NO CUMPLE'],
               marker_color='#9C0006'),
    ])
    fig_bar.update_layout(barmode='stack', title="Cumplimiento por Parámetro",
                          height=350, margin=dict(l=40, r=20, t=40, b=40))
    st.plotly_chart(fig_bar, use_container_width=True)


def _render_deviation_histograms(results, config: dict) -> None:
    tol = config['tolerances']
    col1, col2, col3 = st.columns(3)

    with col1:
        devs_h = [r['height_dev'] for r in results if r['height_dev'] is not None]
        fig_h = go.Figure(go.Histogram(x=devs_h, nbinsx=15, marker_color='royalblue'))
        fig_h.update_layout(title="Distribución Desv. Altura (m)", height=300,
                            xaxis_title="Desviación (m)", yaxis_title="Frecuencia")
        fig_h.add_vline(x=-tol['bench_height']['neg'], line_dash="dash", line_color="orange")
        fig_h.add_vline(x=tol['bench_height']['pos'], line_dash="dash", line_color="orange")
        st.plotly_chart(fig_h, use_container_width=True)

    with col2:
        devs_a = [r['angle_dev'] for r in results if r['angle_dev'] is not None]
        fig_a = go.Figure(go.Histogram(x=devs_a, nbinsx=15, marker_color='forestgreen'))
        fig_a.update_layout(title="Distribución Desv. Ángulo Cara (°)", height=300,
                            xaxis_title="Desviación (°)", yaxis_title="Frecuencia")
        fig_a.add_vline(x=-tol['face_angle']['neg'], line_dash="dash", line_color="orange")
        fig_a.add_vline(x=tol['face_angle']['pos'], line_dash="dash", line_color="orange")
        st.plotly_chart(fig_a, use_container_width=True)

    with col3:
        berm_vals = [r['berm_real'] for r in results
                     if r['berm_real'] is not None and r['berm_real'] > 0]
        if berm_vals:
            fig_b = go.Figure(go.Histogram(x=berm_vals, nbinsx=15, marker_color='#FF7F0E'))
            fig_b.update_layout(title="Distribución Ancho Berma (m)", height=300,
                                xaxis_title="Ancho (m)", yaxis_title="Frecuencia")
            fig_b.add_vline(x=config['min_berm_width'], line_dash="dash", line_color="red",
                            annotation_text="Mínimo", annotation_position="top right")
            st.plotly_chart(fig_b, use_container_width=True)
