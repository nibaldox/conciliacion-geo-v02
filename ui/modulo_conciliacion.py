"""
Módulo de Conciliación Geotécnica.

Wraps the existing 4-step workflow (upload → sections → analysis → results).
Reference lines (mallas) are loaded via the shared sidebar uploader.
"""
import streamlit as st

from ui.sidebar import render_sidebar
from ui.ref_lines import add_ref_lines_2d
from ui.step1_upload import render_step1
from ui.step2_sections import render_step2
from ui.step3_analysis import render_step3
from ui.step4_results import render_step4


def render_modulo_conciliacion() -> None:
    config = render_sidebar()
    st.session_state['_grid_ref'] = config['grid_ref']

    _render_ref_lines_preview()

    render_step1()

    if st.session_state.step >= 2:
        render_step2()

    if st.session_state.step >= 3 and st.session_state.sections:
        render_step3(config)

    if st.session_state.step >= 4 and st.session_state.comparison_results:
        render_step4(config)

    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; font-size: 0.8rem;">
        Conciliación Geotécnica v1.1 | Herramienta de análisis Diseño vs As-Built<br>
        Parámetros: Banco 15m | Cara 65°-75° | Berma 8-10m
    </div>
    """, unsafe_allow_html=True)


def _render_ref_lines_preview() -> None:
    traces = st.session_state.get('ref_line_traces', {})
    if not traces:
        return

    import plotly.graph_objects as go

    with st.expander(f"🗺️ Líneas de Referencia ({len(traces)} mallas)", expanded=False):
        fig = go.Figure()
        add_ref_lines_2d(fig)
        fig.update_layout(
            xaxis_title='Este (m)', yaxis_title='Norte (m)',
            yaxis=dict(scaleanchor='x', scaleratio=1),
            height=500, margin=dict(l=60, r=20, t=30, b=40),
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        )
        st.plotly_chart(fig, use_container_width=True)
