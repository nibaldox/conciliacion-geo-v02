"""
Conciliación Geotécnica v02 — Main router.

Provides sidebar navigation between application modules:
  - Conciliación Geotécnica (existing 4-step workflow + multi-file lines)
  - Análisis de Tronadura (Drill & Blast 3D visualization)
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from ui.modulo_conciliacion import render_modulo_conciliacion
from ui.modulo_tronadura import render_modulo_tronadura
from ui.ref_lines import render_ref_lines_uploader

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

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_DEFAULTS = {
    'mesh_design': None, 'mesh_topo': None,
    'bounds_design': None, 'bounds_topo': None,
    'sections': [], 'profiles_design': [], 'profiles_topo': [],
    'params_design': [], 'params_topo': [],
    'comparison_results': [], 'step': 1,
    'pending_section_names': set(),
    'ref_line_traces': {},
    'blast_df_clean': None,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
modulo = st.sidebar.radio(
    "Módulo",
    ["⛏️ Conciliación Geotécnica", "💥 Análisis de Tronadura"],
    label_visibility="collapsed",
)

st.sidebar.divider()
with st.sidebar:
    render_ref_lines_uploader()

st.markdown(
    f'<div class="main-title">{modulo}</div>',
    unsafe_allow_html=True,
)

if modulo == "⛏️ Conciliación Geotécnica":
    st.markdown(
        '<div class="subtitle">Extracción automática de parámetros desde superficies 3D (STL)</div>',
        unsafe_allow_html=True,
    )
    render_modulo_conciliacion()

elif modulo == "💥 Análisis de Tronadura":
    st.markdown(
        '<div class="subtitle">Visualización 3D de pozos de voladura (Drill & Blast)</div>',
        unsafe_allow_html=True,
    )
    render_modulo_tronadura()
