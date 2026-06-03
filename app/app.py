"""
Aplicación Streamlit para Conciliación Geotécnica: Diseño vs As-Built
Carga superficies STL, genera secciones, extrae parámetros y exporta a Excel.
"""
import streamlit as st

from app.components.sidebar import render_sidebar_config
from app.components.upload import render_upload_section
from app.components.visualization import render_visualization_sections
from app.components.sections import render_sections_section
from app.components.processing import render_processing_section
from app.components.results import render_results_section

# ─── Page config ──────────────────────────────────────────────
st.set_page_config(page_title="Conciliación Geotécnica", page_icon="⛏️", layout="wide")

# ─── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
.main-title { font-size: 2rem; font-weight: bold; color: #2F5496; text-align: center; margin-bottom: 0.5rem; }
.subtitle { font-size: 1.1rem; color: #666; text-align: center; margin-bottom: 1.5rem; }
.metric-card {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 1rem; border-radius: 10px; text-align: center; margin: 0.5rem 0;
    border-left: 4px solid #2F5496;
}
.status-ok { background-color: #C6EFCE; color: #006100; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-warn { background-color: #FFEB9C; color: #9C5700; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-nok { background-color: #FFC7CE; color: #9C0006; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">⛏️ Conciliación Geotécnica: Diseño vs As-Built</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Extracción automática de parámetros desde superficies 3D (STL)</div>', unsafe_allow_html=True)

# ─── Session state defaults ───────────────────────────────────
defaults = {
    'mesh_design': None, 'mesh_topo': None,
    'bounds_design': None, 'bounds_topo': None,
    'sections': [], 'profiles_design': [], 'profiles_topo': [],
    'params_design': [], 'params_topo': [],
    'comparison_results': [], 'step': 1,
    'clicked_sections': [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Sidebar ──────────────────────────────────────────────────
config = render_sidebar_config()

# Pass grid_ref to session_state so visualization can use it
st.session_state['grid_ref'] = config['grid_ref']

# ─── Step 1: Upload ───────────────────────────────────────────
meshes_loaded = render_upload_section()

# ─── Step 2: Visualization + Sections ─────────────────────────
if meshes_loaded:
    render_visualization_sections()

    sections = render_sections_section()

    # ─── Step 3: Processing ───────────────────────────────────
    result = render_processing_section(config)

    # ─── Step 4: Results ──────────────────────────────────────
    if st.session_state.step >= 4 and st.session_state.comparison_results:
        render_results_section(config)

# ─── Footer ───────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    Conciliación Geotécnica v1.1 | Herramienta de análisis Diseño vs As-Built<br>
    Parámetros: Banco 15m | Cara 65°-75° | Berma 8-10m
</div>
""", unsafe_allow_html=True)
