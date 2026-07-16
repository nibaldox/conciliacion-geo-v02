"""
Conciliación Geotécnica v02 — Main router.

Sidebar navigation between application modules. All module-level
state initialization lives in `ui.state`; all shared CSS lives
in `ui.layout`. The actual logic for each module lives in
their respective subpackages.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from ui.modulo_conciliacion import render_modulo_conciliacion
from ui.modulo_tronadura import render_modulo_tronadura
from ui.ref_lines import render_ref_lines_uploader
from ui.layout import inject_global_css
from ui.state import init_defaults

st.set_page_config(page_title="Conciliación Geotécnica", page_icon="⛏️", layout="wide")

inject_global_css()
init_defaults()

modulo = st.sidebar.radio(
    "Módulo",
    ["⛏️ Conciliación Geotécnica", "💥 Análisis de Tronadura"],
    label_visibility="collapsed",
)

st.sidebar.divider()
with st.sidebar:
    render_ref_lines_uploader()

st.markdown(f'<div class="main-title">{modulo}</div>', unsafe_allow_html=True)

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