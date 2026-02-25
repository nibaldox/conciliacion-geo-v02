"""
Step 4: Results viewer — routes to the five result tabs.
"""
import streamlit as st

from ui.tabs.profiles import render_tab_profiles
from ui.tabs.table import render_tab_table
from ui.tabs.dashboard import render_tab_dashboard
from ui.tabs.ai_report import render_tab_ai
from ui.tabs.export import render_tab_export


def render_step4(config: dict) -> None:
    """Render Paso 4: results with five sub-tabs."""
    st.header("📊 Paso 4: Resultados")

    tab_profiles, tab_table, tab_dash, tab_ai, tab_export = st.tabs([
        "📈 Perfiles", "📋 Tabla Detallada", "📊 Dashboard",
        "🤖 Analista IA", "💾 Exportar"])

    with tab_profiles:
        render_tab_profiles(config)
    with tab_table:
        render_tab_table()
    with tab_dash:
        render_tab_dashboard(config)
    with tab_ai:
        render_tab_ai(config)
    with tab_export:
        render_tab_export(config)
