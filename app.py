"""
Aplicación Streamlit para Conciliación Geotécnica: Diseño vs As-Built
Carga superficies STL, genera secciones, extrae parámetros y exporta a Excel.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from ui.sidebar import render_sidebar
from ui.step1_upload import render_step1
from ui.step2_sections import render_step2
from ui.step3_analysis import render_step3
from ui.step4_results import render_step4

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Conciliación Geotécnica", page_icon="⛏️", layout="wide")

st.markdown("""
<style>
.main-title { font-size: 2rem; font-weight: bold; color: #2F5496; text-align: center; margin-bottom: 0.5rem; }
.subtitle { font-size: 1.1rem; color: #666; text-align: center; margin-bottom: 1.5rem; }
.metric-card {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 1rem; border-radius: 10px; text-align: center; margin: 0.5rem 0;
    border-left: 4px solid #2F5496;
}
.status-ok  { background-color: #C6EFCE; color: #006100; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-warn{ background-color: #FFEB9C; color: #9C5700; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-nok { background-color: #FFC7CE; color: #9C0006; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="main-title">⛏️ Conciliación Geotécnica: Diseño vs As-Built</div>',
    unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Extracción automática de parámetros desde superficies 3D (STL)</div>',
    unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_DEFAULTS = {
    'mesh_design': None, 'mesh_topo': None,
    'bounds_design': None, 'bounds_topo': None,
    'sections': [], 'profiles_design': [], 'profiles_topo': [],
    'params_design': [], 'params_topo': [],
    'comparison_results': [], 'step': 1,
    'clicked_sections': [],
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
config = render_sidebar()

# Pass grid_ref into session state so step1 contour view can read it
st.session_state['_grid_ref'] = config['grid_ref']

render_step1()

if st.session_state.step >= 2:
    render_step2()

if st.session_state.step >= 3 and st.session_state.sections:
    render_step3(config)

if st.session_state.step >= 4 and st.session_state.comparison_results:
    render_step4(config)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    Conciliación Geotécnica v1.1 | Herramienta de análisis Diseño vs As-Built<br>
    Parámetros: Banco 15m | Cara 65°-75° | Berma 8-10m
</div>
""", unsafe_allow_html=True)
